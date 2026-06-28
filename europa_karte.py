from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import folium
import requests


# ============================================================
# EINSTELLUNGEN
# ============================================================

OUTPUT_HTML = Path("europa_route_map.html")
OUTPUT_PNG = Path("europa_route_map_8k.png")
ROUTE_CACHE = Path("route_cache.json")
STOPS_CSV = Path("stops.csv")

PNG_WIDTH = 7680
PNG_HEIGHT = 4320

USE_OSRM_ROUTING = True
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
REQUEST_DELAY_SECONDS = 0.5

# Europa-Ausschnitt
EUROPE_BOUNDS = [[34.0, -12.5], [72.5, 32.0]]

# Fallback: Diese Verbindungen werden auch dann als Fähre/Seeweg behandelt,
# wenn leg_type_to_next in der CSV leer ist.
SEA_CROSSING_NAME_PAIRS = {
    # historische Fallback-Paare; bei neuen Hafen-Stopps wird das sauber über
    # leg_type_to_next in stops.csv gesteuert.
    ("Pembrokeshire", "Nantes"),
}


# ============================================================
# DESIGN: LAND-FARBEN FÜR ROUTE
# ============================================================

COUNTRY_COLORS = {
    "Germany": "#ff4d3d",
    "Denmark": "#00aaff",
    "Sweden": "#ffd400",
    "Norway": "#b84dff",
    "Finland": "#ffb000",
    "Estonia": "#ff7a00",
    "Latvia": "#ff4fa3",
    "Lithuania": "#ffdd33",
    "Poland": "#ff8c1a",
    "Netherlands": "#2bd67b",
    "Belgium": "#1e90ff",
    "United Kingdom": "#b45cff",
    "Ireland": "#00c875",
    "France": "#2898ff",
    "Spain": "#ff7b00",
    "Portugal": "#ffd000",
    "Italy": "#3bd650",
    "Slovenia": "#00d8ff",
    "Croatia": "#00bfff",
    "Bosnia and Herzegovina": "#00ffaa",
    "Serbia": "#8e7cff",
    "Hungary": "#ff66cc",
    "Czechia": "#ff3366",
}

FERRY_ROUTE_COLOR = "#0066ff"


# ============================================================
# DESIGN: PIN-FARBEN + SYMBOLE NACH ORTSTYP
# ============================================================

TYPE_STYLES = {
    "Stadt": {
        "color": "#e51b23",
        "text_color": "#ffffff",
        "symbol": "🏙",
        "label": "Stadt",
    },
    "Nationalpark": {
        "color": "#178f43",
        "text_color": "#ffffff",
        "symbol": "🌲",
        "label": "Nationalpark",
    },
    "Fotospot": {
        "color": "#7b2cff",
        "text_color": "#ffffff",
        "symbol": "📷",
        "label": "Fotospot",
    },
    "Fähre": {
        "color": "#0066ff",
        "text_color": "#ffffff",
        "symbol": "⛴",
        "label": "Fähre / Hafen",
    },
    "Camping": {
        "color": "#facc15",
        "text_color": "#111827",
        "symbol": "⛺",
        "label": "Camping / Übernachtung",
    },
    "Transit": {
        "color": "#6b7280",
        "text_color": "#ffffff",
        "symbol": "•",
        "label": "Transit",
    },
}

TYPE_ALIASES = {
    "city": "Stadt",
    "stadt": "Stadt",
    "park": "Nationalpark",
    "nationalpark": "Nationalpark",
    "nature park": "Nationalpark",
    "regional nature park": "Nationalpark",
    "fotospot": "Fotospot",
    "photo": "Fotospot",
    "photo spot": "Fotospot",
    "fotos": "Fotospot",
    "fähre": "Fähre",
    "faehre": "Fähre",
    "ferry": "Fähre",
    "hafen": "Fähre",
    "harbor": "Fähre",
    "camping": "Camping",
    "camping/übernachtung": "Camping",
    "uebernachtung": "Camping",
    "übernachtung": "Camping",
    "transit": "Transit",
}


CSV_FIELDS = [
    "order",
    "name",
    "lat",
    "lon",
    "country",
    "type",
    "tags",
    "nights",
    "must_sees",
    "notes",
    "show_label",
    "leg_type_to_next",
    "leg_note_to_next",
]


# ============================================================
# DEFAULT-ROUTE, FALLS stops.csv NOCH NICHT EXISTIERT
# ============================================================

DEFAULT_STOPS: List[Dict[str, Any]] = [
    {"order": 1, "name": "Vaihingen an der Enz", "lat": 48.9340, "lon": 8.9590, "country": "Germany", "type": "Stadt", "tags": "Start|Heimatbasis", "nights": 0, "must_sees": "", "notes": "Startpunkt", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 2, "name": "Hamburg", "lat": 53.5511, "lon": 9.9937, "country": "Germany", "type": "Stadt", "tags": "Geschichte|Kultur|Hafen", "nights": 2, "must_sees": "Speicherstadt|Elbphilharmonie|Hafen", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 3, "name": "Copenhagen", "lat": 55.6761, "lon": 12.5683, "country": "Denmark", "type": "Stadt", "tags": "Kultur|Stadt", "nights": 2, "must_sees": "Nyhavn|Rosenborg|Christiania", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 4, "name": "Gothenburg", "lat": 57.7089, "lon": 11.9746, "country": "Sweden", "type": "Stadt", "tags": "Küste|Kultur", "nights": 2, "must_sees": "Schärenküste|Haga", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 5, "name": "Stockholm", "lat": 59.3293, "lon": 18.0686, "country": "Sweden", "type": "Stadt", "tags": "Geschichte|Kultur|Schären", "nights": 3, "must_sees": "Gamla Stan|Schären|Vasa Museum", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 6, "name": "Oslo", "lat": 59.9139, "lon": 10.7522, "country": "Norway", "type": "Stadt", "tags": "Kultur|Fjord", "nights": 2, "must_sees": "Opernhaus|Vigelandpark|Fjord", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 7, "name": "Hardangervidda National Park", "lat": 60.0000, "lon": 7.5000, "country": "Norway", "type": "Nationalpark", "tags": "Wandern|Astrofotografie|Landschaft", "nights": 3, "must_sees": "Hochebene|Wandern|Astrofotografie", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 8, "name": "Bergen", "lat": 60.3913, "lon": 5.3221, "country": "Norway", "type": "Stadt", "tags": "Kultur|Fjord|Geschichte", "nights": 2, "must_sees": "Bryggen|Fløyen|Fjordtour", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 9, "name": "Ålesund", "lat": 62.4722, "lon": 6.1495, "country": "Norway", "type": "Fotospot", "tags": "Küste|Architektur|Fotospot", "nights": 2, "must_sees": "Jugendstil|Aksla|Fjordlandschaft", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 10, "name": "Trondheim", "lat": 63.4305, "lon": 10.3951, "country": "Norway", "type": "Stadt", "tags": "Geschichte|Kultur", "nights": 2, "must_sees": "Nidarosdom|Bakklandet", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 11, "name": "Lofoten", "lat": 68.1525, "lon": 13.6094, "country": "Norway", "type": "Fotospot", "tags": "Nordlichter|Fotospot|Landschaft|Milchstraße", "nights": 5, "must_sees": "Reine|Haukland Beach|Nordlichter", "notes": "Sehr wichtiger Foto- und Landschaftsstopp", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 12, "name": "North Cape", "lat": 71.1725, "lon": 25.7840, "country": "Norway", "type": "Fotospot", "tags": "Nordkap|Fotospot|Mitternachtssonne", "nights": 1, "must_sees": "Mitternachtssonne|Nordkapplateau", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 13, "name": "Helsinki", "lat": 60.1699, "lon": 24.9384, "country": "Finland", "type": "Stadt", "tags": "Kultur|Fährhafen", "nights": 2, "must_sees": "Dom|Suomenlinna|Design District", "notes": "Fährverbindung nach Tallinn", "show_label": "yes", "leg_type_to_next": "Fähre", "leg_note_to_next": "Helsinki → Tallinn"},
    {"order": 14, "name": "Tallinn", "lat": 59.4370, "lon": 24.7536, "country": "Estonia", "type": "Stadt", "tags": "Geschichte|Kultur|Altstadt", "nights": 2, "must_sees": "Altstadt|Toompea", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 15, "name": "Soomaa National Park", "lat": 58.4300, "lon": 25.0000, "country": "Estonia", "type": "Nationalpark", "tags": "Moor|Wildnis|Natur", "nights": 2, "must_sees": "Moore|Kanufahren|Wildnis", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 16, "name": "Riga", "lat": 56.9496, "lon": 24.1052, "country": "Latvia", "type": "Stadt", "tags": "Geschichte|Kultur|Jugendstil", "nights": 2, "must_sees": "Altstadt|Jugendstilviertel", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 17, "name": "Vilnius", "lat": 54.6872, "lon": 25.2797, "country": "Lithuania", "type": "Stadt", "tags": "Geschichte|Kultur", "nights": 2, "must_sees": "Altstadt|Užupis|Gediminas", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 18, "name": "Torun", "lat": 53.0138, "lon": 18.5984, "country": "Poland", "type": "Stadt", "tags": "Geschichte|Altstadt", "nights": 1, "must_sees": "Altstadt|Kopernikus|Weichsel", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 19, "name": "Spreewald", "lat": 51.8600, "lon": 14.0300, "country": "Germany", "type": "Nationalpark", "tags": "Natur|Kanu|Kultur", "nights": 2, "must_sees": "Kanäle|Lehde|Kahnfahrt", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 20, "name": "Harz National Park", "lat": 51.7700, "lon": 10.6200, "country": "Germany", "type": "Nationalpark", "tags": "Wandern|Sternenhimmel|Natur", "nights": 2, "must_sees": "Brocken|Wandern|Sternenhimmel", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 21, "name": "Amsterdam", "lat": 52.3676, "lon": 4.9041, "country": "Netherlands", "type": "Stadt", "tags": "Kultur|Geschichte|Kanäle", "nights": 2, "must_sees": "Grachten|Rijksmuseum|Jordaan", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 22, "name": "Brussels", "lat": 50.8503, "lon": 4.3517, "country": "Belgium", "type": "Stadt", "tags": "Kultur|Geschichte|EU", "nights": 1, "must_sees": "Grand Place|Atomium", "notes": "Etappe nach Norwich als See-/Fährverbindung visualisiert", "show_label": "yes", "leg_type_to_next": "Fähre", "leg_note_to_next": "Belgien/Frankreich → England"},
    {"order": 23, "name": "Norwich", "lat": 52.6309, "lon": 1.2974, "country": "United Kingdom", "type": "Stadt", "tags": "Geschichte|Kultur", "nights": 1, "must_sees": "Cathedral|Norfolk Broads", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 24, "name": "Glasgow", "lat": 55.8642, "lon": -4.2518, "country": "United Kingdom", "type": "Stadt", "tags": "Kultur|Stadt", "nights": 2, "must_sees": "Kelvingrove|West End", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 25, "name": "Fort William", "lat": 56.8198, "lon": -5.1052, "country": "United Kingdom", "type": "Fotospot", "tags": "Highlands|Fotospot|Wandern", "nights": 2, "must_sees": "Ben Nevis|Glen Nevis", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 26, "name": "Cairngorms National Park", "lat": 57.0800, "lon": -3.6700, "country": "United Kingdom", "type": "Nationalpark", "tags": "Wandern|Wildlife|Landschaft", "nights": 3, "must_sees": "Highlands|Wandern|Wildlife", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 27, "name": "Skye", "lat": 57.5350, "lon": -6.2260, "country": "United Kingdom", "type": "Fotospot", "tags": "Fotospot|Landschaft|Küste", "nights": 4, "must_sees": "Old Man of Storr|Quiraing|Fairy Pools", "notes": "", "show_label": "yes", "leg_type_to_next": "Fähre", "leg_note_to_next": "Schottland → Irland"},
    {"order": 28, "name": "Dublin", "lat": 53.3498, "lon": -6.2603, "country": "Ireland", "type": "Stadt", "tags": "Kultur|Geschichte|Fährhafen", "nights": 2, "must_sees": "Trinity College|Temple Bar|Howth", "notes": "", "show_label": "yes", "leg_type_to_next": "Fähre", "leg_note_to_next": "Irland → Wales"},
    {"order": 29, "name": "Pembrokeshire", "lat": 51.8000, "lon": -4.9000, "country": "United Kingdom", "type": "Nationalpark", "tags": "Küste|Wandern|Natur", "nights": 3, "must_sees": "Coast Path|St Davids|Strände", "notes": "", "show_label": "yes", "leg_type_to_next": "Fähre", "leg_note_to_next": "UK → Frankreich"},
    {"order": 30, "name": "Nantes", "lat": 47.2184, "lon": -1.5536, "country": "France", "type": "Stadt", "tags": "Kultur|Stadt", "nights": 1, "must_sees": "Machines de l’île|Altstadt", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 31, "name": "Landes de Gascogne Regional Nature Park", "lat": 44.3500, "lon": -0.7500, "country": "France", "type": "Nationalpark", "tags": "Natur|Küste|Wald", "nights": 2, "must_sees": "Pinienwald|Dünen|Seen", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 32, "name": "Barcelona", "lat": 41.3851, "lon": 2.1734, "country": "Spain", "type": "Stadt", "tags": "Kultur|Architektur|Stadt", "nights": 3, "must_sees": "Sagrada Família|Gotisches Viertel|Montjuïc", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 33, "name": "Valencia", "lat": 39.4699, "lon": -0.3763, "country": "Spain", "type": "Stadt", "tags": "Kultur|Küste|Stadt", "nights": 2, "must_sees": "Ciudad de las Artes|Altstadt|Albufera", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 34, "name": "Seville", "lat": 37.3891, "lon": -5.9845, "country": "Spain", "type": "Stadt", "tags": "Geschichte|Kultur|Stadt", "nights": 2, "must_sees": "Alcázar|Kathedrale|Triana", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 35, "name": "Lisabon", "lat": 38.7223, "lon": -9.1393, "country": "Portugal", "type": "Stadt", "tags": "Kultur|Küste|Fotospot", "nights": 3, "must_sees": "Alfama|Belém|Miradouros", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 36, "name": "Porto", "lat": 41.1579, "lon": -8.6291, "country": "Portugal", "type": "Stadt", "tags": "Kultur|Küste|Geschichte", "nights": 2, "must_sees": "Ribeira|Dom Luís I|Douro", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 37, "name": "Peneda-Gerês National Park", "lat": 41.7800, "lon": -8.1700, "country": "Portugal", "type": "Nationalpark", "tags": "Wandern|Natur|Berge", "nights": 3, "must_sees": "Wandern|Wasserfälle|Bergdörfer", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 38, "name": "Santillana del Mar", "lat": 43.3890, "lon": -4.1080, "country": "Spain", "type": "Stadt", "tags": "Geschichte|Kultur", "nights": 1, "must_sees": "Altstadt|Altamira", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 39, "name": "Pyrenees National Park", "lat": 42.8800, "lon": -0.1200, "country": "France", "type": "Nationalpark", "tags": "Wandern|Sternenhimmel|Milchstraße|Berge", "nights": 3, "must_sees": "Berge|Wandern|Sternenhimmel", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 40, "name": "Toulouse", "lat": 43.6047, "lon": 1.4442, "country": "France", "type": "Stadt", "tags": "Kultur|Stadt", "nights": 1, "must_sees": "Altstadt|Garonne|Raumfahrt", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 41, "name": "Verdon Regional Nature Park", "lat": 43.7400, "lon": 6.3600, "country": "France", "type": "Nationalpark", "tags": "Landschaft|Fotospot|Wandern", "nights": 2, "must_sees": "Gorges du Verdon|Lac de Sainte-Croix", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 42, "name": "Nice", "lat": 43.7102, "lon": 7.2620, "country": "France", "type": "Stadt", "tags": "Küste|Kultur|Stadt", "nights": 2, "must_sees": "Promenade des Anglais|Altstadt|Colline du Château", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 43, "name": "Genoa", "lat": 44.4056, "lon": 8.9463, "country": "Italy", "type": "Stadt", "tags": "Geschichte|Hafen|Kultur", "nights": 1, "must_sees": "Altstadt|Hafen|Palazzi dei Rolli", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 44, "name": "Portofino", "lat": 44.3036, "lon": 9.2099, "country": "Italy", "type": "Fotospot", "tags": "Küste|Fotospot|Wandern", "nights": 1, "must_sees": "Hafen|Wanderwege|Küste", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 45, "name": "Vernazza", "lat": 44.1347, "lon": 9.6850, "country": "Italy", "type": "Fotospot", "tags": "Küste|Fotospot|Cinque Terre", "nights": 1, "must_sees": "Cinque Terre|Hafen|Aussichtspunkte", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 46, "name": "Florence", "lat": 43.7696, "lon": 11.2558, "country": "Italy", "type": "Stadt", "tags": "Geschichte|Kunst|Kultur", "nights": 2, "must_sees": "Dom|Uffizien|Ponte Vecchio", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 47, "name": "Bologna", "lat": 44.4949, "lon": 11.3426, "country": "Italy", "type": "Stadt", "tags": "Kultur|Essen|Geschichte", "nights": 1, "must_sees": "Arkaden|Piazza Maggiore|Türme", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 48, "name": "Milan", "lat": 45.4642, "lon": 9.1900, "country": "Italy", "type": "Stadt", "tags": "Kultur|Stadt|Architektur", "nights": 2, "must_sees": "Dom|Navigli|Brera", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 49, "name": "Bergamo", "lat": 45.6983, "lon": 9.6773, "country": "Italy", "type": "Stadt", "tags": "Geschichte|Kultur|Fotospot", "nights": 1, "must_sees": "Città Alta|Stadtmauer", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 50, "name": "Ljubljana", "lat": 46.0569, "lon": 14.5058, "country": "Slovenia", "type": "Stadt", "tags": "Kultur|Stadt|Transit", "nights": 2, "must_sees": "Altstadt|Burg|Flussufer", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 51, "name": "Zagreb", "lat": 45.8150, "lon": 15.9819, "country": "Croatia", "type": "Stadt", "tags": "Kultur|Geschichte", "nights": 1, "must_sees": "Oberstadt|Kathedrale", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 52, "name": "Sarajevo", "lat": 43.8563, "lon": 18.4131, "country": "Bosnia and Herzegovina", "type": "Stadt", "tags": "Geschichte|Kultur", "nights": 2, "must_sees": "Baščaršija|Geschichte|Aussicht", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 53, "name": "Belgrade", "lat": 44.7866, "lon": 20.4489, "country": "Serbia", "type": "Stadt", "tags": "Geschichte|Kultur|Donau", "nights": 2, "must_sees": "Festung|Donau/Sava|Skadarlija", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 54, "name": "Budapest", "lat": 47.4979, "lon": 19.0402, "country": "Hungary", "type": "Stadt", "tags": "Geschichte|Kultur|Thermalbad", "nights": 3, "must_sees": "Parlament|Burgviertel|Thermalbäder", "notes": "", "show_label": "yes", "leg_type_to_next": "Straße", "leg_note_to_next": ""},
    {"order": 55, "name": "Prague", "lat": 50.0755, "lon": 14.4378, "country": "Czechia", "type": "Stadt", "tags": "Geschichte|Kultur|Altstadt", "nights": 3, "must_sees": "Altstadt|Karlsbrücke|Burg", "notes": "Endpunkt der aktuellen Route", "show_label": "yes", "leg_type_to_next": "", "leg_note_to_next": ""},
]


# ============================================================
# DATEN LADEN / CONFIG
# ============================================================

def create_default_stops_csv(path: Path = STOPS_CSV) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS, delimiter=";")
        writer.writeheader()
        for stop in DEFAULT_STOPS:
            writer.writerow({field: stop.get(field, "") for field in CSV_FIELDS})
    print(f"Neue Konfigurationsdatei erstellt: {path.resolve()}")


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    value_str = str(value).strip().lower()
    if value_str in {"1", "true", "yes", "ja", "y", "j"}:
        return True
    if value_str in {"0", "false", "no", "nein", "n"}:
        return False
    return default


def parse_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).replace(",", ".")))
    except ValueError:
        return default


def parse_float(value: Any) -> float:
    return float(str(value).strip().replace(",", "."))


def normalize_type(stop_type: Any) -> str:
    raw = str(stop_type or "").strip()
    key = raw.lower()
    return TYPE_ALIASES.get(key, raw if raw in TYPE_STYLES else "Stadt")


def get_type_style(stop_type: Any) -> Dict[str, str]:
    normalized = normalize_type(stop_type)
    return TYPE_STYLES.get(normalized, TYPE_STYLES["Stadt"])


def split_list(value: Any) -> List[str]:
    if value is None:
        return []
    value_str = str(value).strip()
    if not value_str:
        return []
    raw_items = value_str.replace("\r", "\n").replace("|", "\n").split("\n")
    return [item.strip() for item in raw_items if item.strip()]


def load_stops_from_csv(path: Path = STOPS_CSV) -> List[Dict[str, Any]]:
    if not path.exists():
        create_default_stops_csv(path)

    stops: List[Dict[str, Any]] = []

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        sample = file.read(4096)
        file.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t") if sample else csv.excel
        reader = csv.DictReader(file, dialect=dialect)

        required = {"order", "name", "lat", "lon", "country"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise RuntimeError(f"In {path} fehlen Spalten: {', '.join(sorted(missing))}")

        for row in reader:
            if not row.get("name", "").strip():
                continue

            stop_type = normalize_type(row.get("type", "Stadt"))

            stops.append({
                "order": parse_float(row["order"]),
                "name": row["name"].strip(),
                "lat": parse_float(row["lat"]),
                "lon": parse_float(row["lon"]),
                "country": row["country"].strip(),
                "type": stop_type,
                "tags": row.get("tags", "").strip(),
                "nights": parse_int(row.get("nights"), 0),
                "must_sees": row.get("must_sees", "").strip(),
                "notes": row.get("notes", "").strip(),
                "show_label": parse_bool(row.get("show_label", "yes"), True),
                "leg_type_to_next": row.get("leg_type_to_next", "").strip(),
                "leg_note_to_next": row.get("leg_note_to_next", "").strip(),
            })

    stops.sort(key=lambda x: x["order"])

    if len(stops) < 2:
        raise RuntimeError("Es müssen mindestens 2 Stops in stops.csv stehen.")

    for index, stop in enumerate(stops, start=1):
        stop["number"] = index
        style = get_type_style(stop.get("type"))
        stop["type_color"] = style["color"]
        stop["type_text_color"] = style["text_color"]
        stop["type_symbol"] = style["symbol"]
        stop["type_label"] = style["label"]

    return stops


# ============================================================
# CACHE
# ============================================================

def load_cache() -> Dict[str, List[List[float]]]:
    if not ROUTE_CACHE.exists():
        return {}

    try:
        return json.loads(ROUTE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        print("Cache konnte nicht gelesen werden. Neuer Cache wird erstellt.")
        return {}


def save_cache(cache: Dict[str, List[List[float]]]) -> None:
    ROUTE_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============================================================
# ROUTING
# ============================================================

def html_escape(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def direct_line(start: Tuple[float, float], end: Tuple[float, float], steps: int = 80) -> List[List[float]]:
    lat1, lon1 = start
    lat2, lon2 = end
    points = []

    for i in range(steps + 1):
        t = i / steps
        lat = lat1 + (lat2 - lat1) * t
        lon = lon1 + (lon2 - lon1) * t
        points.append([lat, lon])

    return points


def is_direct_crossing_leg(stop_a: Dict[str, Any], stop_b: Dict[str, Any]) -> bool:
    """
    True für Etappen, die nicht über OSRM-Straßenrouting laufen sollen,
    sondern als direkte gestrichelte Verbindung erscheinen.
    Das umfasst Fähren/Seewege und den Eurotunnel-Autozug.
    """
    leg_type = str(stop_a.get("leg_type_to_next", "")).strip().lower()
    crossing_keywords = [
        "fähre", "faehre", "ferry", "see", "sea", "schiff", "boot",
        "eurotunnel", "tunnel", "channel tunnel", "autozug", "leshuttle",
    ]
    if any(word in leg_type for word in crossing_keywords):
        return True

    name_pair = (stop_a["name"], stop_b["name"])
    return name_pair in SEA_CROSSING_NAME_PAIRS


# Rückwärtskompatibel: der Rest des Codes nutzt diesen Namen.
def is_ferry_leg(stop_a: Dict[str, Any], stop_b: Dict[str, Any]) -> bool:
    return is_direct_crossing_leg(stop_a, stop_b)


def leg_type_label(stop_a: Dict[str, Any], stop_b: Dict[str, Any]) -> str:
    value = str(stop_a.get("leg_type_to_next", "")).strip()
    value_lower = value.lower()

    if any(word in value_lower for word in ["eurotunnel", "tunnel", "channel tunnel", "autozug", "leshuttle"]):
        return "Eurotunnel / Autozug"

    if is_ferry_leg(stop_a, stop_b):
        return "Fähre / Seeweg"

    return value if value else "Straße"


def get_osrm_route(
    start: Tuple[float, float],
    end: Tuple[float, float],
    cache_key: str,
    cache: Dict[str, List[List[float]]],
) -> Tuple[List[List[float]], bool]:
    if cache_key in cache:
        route = cache[cache_key]
        if route and len(route) >= 2:
            return route, True

    if not USE_OSRM_ROUTING:
        return direct_line(start, end), False

    lat1, lon1 = start
    lat2, lon2 = end

    url = (
        f"{OSRM_URL}/"
        f"{lon1},{lat1};{lon2},{lat2}"
        f"?overview=full"
        f"&geometries=geojson"
        f"&steps=false"
        f"&alternatives=false"
        f"&radiuses=70000;70000"
    )

    try:
        response = requests.get(
            url,
            timeout=60,
            headers={"User-Agent": "europe-roadtrip-route-map/1.0"},
        )
        response.raise_for_status()

        data = response.json()

        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM-Code: {data.get('code')}")

        routes = data.get("routes", [])
        if not routes:
            raise RuntimeError("Keine Route gefunden")

        coords_lonlat = routes[0]["geometry"]["coordinates"]
        coords_latlon = [[lat, lon] for lon, lat in coords_lonlat]

        if len(coords_latlon) < 2:
            raise RuntimeError("OSRM-Route hat zu wenige Punkte")

        cache[cache_key] = coords_latlon
        save_cache(cache)

        time.sleep(REQUEST_DELAY_SECONDS)
        return coords_latlon, True

    except Exception as exc:
        print(f"OSRM fehlgeschlagen für {cache_key}: {exc}")
        return direct_line(start, end), False


# ============================================================
# POPUP / DARSTELLUNG
# ============================================================

def numbered_icon(number: int, stop: Dict[str, Any]) -> folium.DivIcon:
    color = stop.get("type_color", TYPE_STYLES["Stadt"]["color"])
    text_color = stop.get("type_text_color", "#ffffff")

    html = f"""
    <div style="
        width: 28px;
        height: 28px;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        background: {color};
        border: 3px solid white;
        box-shadow: 0 2px 9px rgba(0,0,0,0.50);
        display: flex;
        align-items: center;
        justify-content: center;
    ">
        <div style="
            transform: rotate(45deg);
            color: {text_color};
            font-weight: 900;
            font-size: 11px;
            font-family: Arial, sans-serif;
        ">{number}</div>
    </div>
    """
    return folium.DivIcon(html=html, icon_size=(34, 34), icon_anchor=(14, 28))


def build_popup_html(stop: Dict[str, Any], next_stop: Dict[str, Any] | None) -> str:
    must_sees = split_list(stop.get("must_sees", ""))
    tags = split_list(stop.get("tags", ""))

    tags_html = ""
    if tags:
        tag_items = "".join(f"<span class='tag-pill'>{html_escape(tag)}</span>" for tag in tags)
        tags_html = f"""
        <div class="popup-section">
            <div class="popup-heading">Tags</div>
            <div class="tag-row">{tag_items}</div>
        </div>
        """

    must_see_html = ""
    if must_sees:
        items = "".join(f"<li>{html_escape(item)}</li>" for item in must_sees)
        must_see_html = f"""
        <div class="popup-section">
            <div class="popup-heading">Must-Sees</div>
            <ul>{items}</ul>
        </div>
        """

    notes = str(stop.get("notes", "")).strip()
    notes_html = ""
    if notes:
        notes_html = f"""
        <div class="popup-section">
            <div class="popup-heading">Notizen</div>
            <div class="popup-notes">{html_escape(notes).replace(chr(10), '<br>')}</div>
        </div>
        """

    nights = stop.get("nights", 0)
    nights_text = "noch offen" if nights == 0 else f"{nights} Nacht" + ("" if nights == 1 else "e")

    next_leg_html = ""
    if next_stop is not None:
        leg_label = leg_type_label(stop, next_stop)
        leg_note = str(stop.get("leg_note_to_next", "")).strip()
        ferry_class = " ferry-leg" if is_ferry_leg(stop, next_stop) else ""
        note_html = f"<div class='leg-note'>{html_escape(leg_note)}</div>" if leg_note else ""
        next_leg_html = f"""
        <div class="popup-section">
            <div class="popup-heading">Etappe zum nächsten Ziel</div>
            <div class="next-leg{ferry_class}">
                <b>{html_escape(leg_label)}</b>: {stop['number']} → {next_stop['number']}<br>
                {html_escape(stop['name'])} → {html_escape(next_stop['name'])}
                {note_html}
            </div>
        </div>
        """

    color = stop.get("type_color", TYPE_STYLES["Stadt"]["color"])
    text_color = stop.get("type_text_color", "#ffffff")

    return f"""
    <div class="popup-card">
        <div class="popup-title">{html_escape(stop['type_symbol'])} {stop['number']}. {html_escape(stop['name'])}</div>
        <div class="popup-subtitle">{html_escape(stop.get('country', ''))}</div>

        <div class="popup-grid">
            <div class="popup-key">Typ</div>
            <div class="popup-value">
                <span class="type-badge" style="background:{color}; color:{text_color};">
                    {html_escape(stop['type_symbol'])} {html_escape(stop.get('type_label', stop.get('type', '')))}
                </span>
            </div>
            <div class="popup-key">Nächte</div>
            <div class="popup-value">{html_escape(nights_text)}</div>
        </div>

        {tags_html}
        {must_see_html}
        {notes_html}
        {next_leg_html}
    </div>
    """


def add_route_line(
    m: folium.Map,
    locations: List[List[float]],
    color: str,
    tooltip: str,
    dashed: bool,
) -> None:
    if not locations or len(locations) < 2:
        return

    dash = "10,10" if dashed else None

    folium.PolyLine(
        locations=locations,
        color="#111111",
        weight=8,
        opacity=0.75,
        dash_array=dash,
        smooth_factor=0,
        tooltip=tooltip,
    ).add_to(m)

    folium.PolyLine(
        locations=locations,
        color=color,
        weight=4.8,
        opacity=1.0,
        dash_array=dash,
        smooth_factor=0,
        tooltip=tooltip,
    ).add_to(m)


def add_label(m: folium.Map, stop: Dict[str, Any]) -> None:
    if not stop.get("show_label", True):
        return

    folium.map.Marker(
        [stop["lat"], stop["lon"]],
        icon=folium.DivIcon(
            icon_size=(1, 1),
            icon_anchor=(-8, 14),
            html=f"""
            <span class="small-label">
                <span class="label-symbol">{html_escape(stop['type_symbol'])}</span>
                {stop['number']}. {html_escape(stop['name'])}
            </span>
            """,
        ),
    ).add_to(m)


def add_legend(m: folium.Map) -> None:
    type_rows = "".join(
        f"""
        <div class="legend-row">
            <span class="legend-dot" style="background:{style['color']}; color:{style['text_color']};">{html_escape(style['symbol'])}</span>
            <span>{html_escape(style['label'])}</span>
        </div>
        """
        for style in TYPE_STYLES.values()
    )

    legend_html = f"""
    <div class="map-legend">
        <div class="legend-title">Legende</div>
        {type_rows}
        <div class="legend-divider"></div>
        <div class="legend-route"><span class="legend-line solid"></span> Straße / Landroute</div>
        <div class="legend-route"><span class="legend-line dashed"></span> Fähre / Seeweg / Eurotunnel</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))


def build_map() -> folium.Map:
    stops = load_stops_from_csv(STOPS_CSV)
    cache = load_cache()

    m = folium.Map(
        location=[54.0, 9.0],
        zoom_start=4,
        tiles="CartoDB Voyager",
        prefer_canvas=True,
        width="100%",
        height="100%",
        control_scale=True,
        zoom_control=True,
    )

    print("\nZeichne vollständige Route:")
    print("Es wird ausschließlich die Reihenfolge aus stops.csv verbunden.\n")

    segment_count = 0

    for idx in range(len(stops) - 1):
        stop_a = stops[idx]
        stop_b = stops[idx + 1]

        number_a = stop_a["number"]
        number_b = stop_b["number"]

        start = (stop_a["lat"], stop_a["lon"])
        end = (stop_b["lat"], stop_b["lon"])

        ferry_leg = is_ferry_leg(stop_a, stop_b)
        leg_label = leg_type_label(stop_a, stop_b)
        color = FERRY_ROUTE_COLOR if ferry_leg else COUNTRY_COLORS.get(stop_b["country"], "#ff0000")
        tooltip = f"{number_a} → {number_b}: {stop_a['name']} → {stop_b['name']} | {leg_label}"

        if ferry_leg:
            route = direct_line(start, end)
            is_osrm = False
            dashed = True
        else:
            cache_key = f"{number_a:03d}-{number_b:03d}_{stop_a['name']}_to_{stop_b['name']}"
            route, is_osrm = get_osrm_route(start, end, cache_key, cache)
            dashed = False

        add_route_line(m=m, locations=route, color=color, tooltip=tooltip, dashed=dashed)
        segment_count += 1

        print(
            f"{number_a:02d}-{number_b:02d}: "
            f"{stop_a['name']} -> {stop_b['name']} | "
            f"{leg_label} | "
            f"{'OSRM' if is_osrm else 'Fallback/direkt'} | "
            f"Punkte: {len(route)}"
        )

    print(f"\nGezeichnete Routensegmente: {segment_count} von {len(stops) - 1}\n")

    for idx, stop in enumerate(stops):
        next_stop = stops[idx + 1] if idx < len(stops) - 1 else None
        popup = folium.Popup(
            build_popup_html(stop, next_stop),
            max_width=390,
            min_width=300,
        )

        folium.Marker(
            location=[stop["lat"], stop["lon"]],
            icon=numbered_icon(stop["number"], stop),
            tooltip=f"{stop['type_symbol']} {stop['number']}. {stop['name']} ({stop['type_label']})",
            popup=popup,
        ).add_to(m)

        add_label(m, stop)

    m.fit_bounds(EUROPE_BOUNDS, padding=(10, 10))
    add_legend(m)

    css = """
    <style>
        html, body {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
            background: #d8e1e5;
        }

        .folium-map {
            width: 100vw !important;
            height: 100vh !important;
        }

        .leaflet-container {
            font-family: Arial, sans-serif;
        }

        .small-label {
            display: inline-block;
            width: max-content;
            max-width: none;
            font-family: Arial, sans-serif;
            font-size: 10px;
            font-weight: 700;
            line-height: 1.15;
            color: #111;
            background: rgba(255,255,255,0.90);
            border: 1px solid rgba(0,0,0,0.25);
            border-radius: 5px;
            padding: 2px 5px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.25);
            white-space: nowrap;
        }

        .label-symbol {
            margin-right: 2px;
        }

        .popup-card {
            font-family: Arial, sans-serif;
            color: #111827;
            min-width: 280px;
            max-width: 370px;
        }

        .popup-title {
            font-size: 16px;
            font-weight: 900;
            margin-bottom: 2px;
        }

        .popup-subtitle {
            font-size: 12px;
            color: #4b5563;
            margin-bottom: 10px;
        }

        .popup-grid {
            display: grid;
            grid-template-columns: 76px 1fr;
            gap: 5px 8px;
            margin-bottom: 10px;
        }

        .popup-key {
            font-size: 11px;
            color: #6b7280;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        .popup-value {
            font-size: 12px;
            font-weight: 700;
        }

        .type-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 3px 9px;
            font-size: 11px;
            font-weight: 900;
            box-shadow: 0 1px 3px rgba(0,0,0,0.18);
        }

        .popup-section {
            margin-top: 9px;
            padding-top: 8px;
            border-top: 1px solid #e5e7eb;
        }

        .popup-heading {
            font-size: 12px;
            font-weight: 900;
            color: #111827;
            margin-bottom: 4px;
        }

        .tag-row {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }

        .tag-pill {
            display: inline-block;
            border-radius: 999px;
            background: #f3f4f6;
            color: #1f2937;
            border: 1px solid #d1d5db;
            padding: 2px 7px;
            font-size: 11px;
            font-weight: 700;
        }

        .popup-card ul {
            padding-left: 18px;
            margin: 4px 0 0 0;
        }

        .popup-card li {
            margin-bottom: 3px;
            font-size: 12px;
        }

        .popup-notes {
            font-size: 12px;
            line-height: 1.35;
            color: #374151;
            white-space: normal;
        }

        .next-leg {
            font-size: 12px;
            line-height: 1.35;
            background: #f3f4f6;
            border-left: 4px solid #9ca3af;
            border-radius: 6px;
            padding: 6px 8px;
        }

        .next-leg.ferry-leg {
            background: #eff6ff;
            border-left-color: #0066ff;
        }

        .leg-note {
            margin-top: 3px;
            color: #4b5563;
            font-size: 11px;
        }

        .map-legend {
            position: fixed;
            left: 14px;
            bottom: 18px;
            z-index: 9999;
            background: rgba(255,255,255,0.94);
            border: 1px solid rgba(0,0,0,0.22);
            border-radius: 10px;
            box-shadow: 0 3px 14px rgba(0,0,0,0.25);
            padding: 10px 12px;
            font-family: Arial, sans-serif;
            font-size: 11px;
            color: #111827;
        }

        .legend-title {
            font-size: 12px;
            font-weight: 900;
            margin-bottom: 6px;
        }

        .legend-row {
            display: flex;
            align-items: center;
            gap: 7px;
            margin: 4px 0;
            font-weight: 700;
        }

        .legend-dot {
            width: 20px;
            height: 20px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            font-size: 11px;
        }

        .legend-divider {
            border-top: 1px solid #d1d5db;
            margin: 8px 0;
        }

        .legend-route {
            display: flex;
            align-items: center;
            gap: 7px;
            margin: 4px 0;
            font-weight: 700;
        }

        .legend-line {
            width: 34px;
            height: 0;
            border-top: 4px solid #0066ff;
            display: inline-block;
        }

        .legend-line.solid {
            border-top-color: #111111;
        }

        .legend-line.dashed {
            border-top-style: dashed;
            border-top-color: #0066ff;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(css))

    return m


# ============================================================
# PNG EXPORT
# ============================================================

def export_png_with_selenium(
    html_path: Path,
    png_path: Path,
    width: int = PNG_WIDTH,
    height: int = PNG_HEIGHT,
    wait_seconds: int = 15,
) -> None:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=options)

    try:
        driver.set_window_size(width, height)
        driver.get(html_path.resolve().as_uri())

        print(f"Warte {wait_seconds} Sekunden, bis Kartenkacheln geladen sind ...")
        time.sleep(wait_seconds)

        driver.save_screenshot(str(png_path.resolve()))
        print(f"PNG gespeichert: {png_path.resolve()}")

    finally:
        driver.quit()


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("Erstelle Europakarte ...")
    stops = load_stops_from_csv(STOPS_CSV)
    print(f"Geladene Ziele aus {STOPS_CSV}: {len(stops)}")

    m = build_map()

    m.save(str(OUTPUT_HTML.resolve()))
    print(f"HTML gespeichert: {OUTPUT_HTML.resolve()}")

    try:
        print("Exportiere PNG ...")
        export_png_with_selenium(
            html_path=OUTPUT_HTML,
            png_path=OUTPUT_PNG,
            wait_seconds=18,
        )
    except Exception as exc:
        print("PNG-Export fehlgeschlagen.")
        print(exc)
        print("Die HTML-Datei wurde trotzdem erstellt.")


if __name__ == "__main__":
    main()
