"""Konfigurációs beállítások a TipMix Prediction System v3-höz.

Sofascore (meccs statisztikák) + The Odds API (oddsok) + football-data.org (fallback).
"""

import os
from difflib import SequenceMatcher
from pathlib import Path

from dotenv import load_dotenv

# .env betöltése
load_dotenv(Path(__file__).parent.parent / ".env")

# === Sofascore konfiguráció ===
SOFASCORE_BASE_URL = "https://www.sofascore.com/api/v1"
SOFASCORE_REQUEST_DELAY = 2  # másodperc a kérések között

# === The Odds API konfiguráció ===
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"

# === football-data.org konfiguráció (Sofascore fallback) ===
FOOTBALL_DATA_KEY = os.getenv("FOOTBALL_DATA_KEY", "")

# === Telegram Bot konfiguráció ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# Engedélyezett Telegram user ID-k (vesszővel elválasztva)
TELEGRAM_ALLOWED_USERS: list[int] = [
    int(x.strip()) for x in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    if x.strip().isdigit()
]

# === TippmixPro konfiguráció (fallback) ===
TIPPMIXPRO_BASE_URL = "https://www.tippmixpro.hu"

# === Cache beállítások ===
PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_HOURS = 6  # Odds API cache: 6 óra

# === HTTP beállítások ===
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# === Predikciós beállítások ===
FORM_MATCHES = 20          # Utolsó N meccs a formához (mélyelemzés)
POISSON_MAX_GOALS = 7      # Poisson eloszlás max gól
MIN_CONFIDENCE = 0.55      # Minimum konfidencia szelvényhez
VALUE_BET_THRESHOLD = 0.05 # Minimum edge a value bet-hez (5%)

# === Strength Rating beállítások (korábban "ELO") ===
# Rövid távú erősségmutató 20 meccsből, NEM valódi ELO
STRENGTH_DEFAULT_RATING = 1500
STRENGTH_K_FACTOR = 30
STRENGTH_HOME_ADVANTAGE = 100

# === Dixon-Coles beállítások ===
DIXON_COLES_RHO = -0.13    # Alacsony gólszámú korrelációs faktor

# === Ensemble súlyok (piac-specifikus) ===
# 1X2 piaci súlyok
ENSEMBLE_WEIGHTS_1X2 = {
    "poisson": 0.40,       # Dixon-Coles modell (1X2-re a legerősebb)
    "strength": 0.25,      # Erősség rating
    "form": 0.20,          # Forma alapú becslés
    "h2h": 0.05,           # H2H (kis súly - zajos, kis minta)
    "stats": 0.10,         # Statisztikai trendek
}

# Over/Under piaci súlyok
ENSEMBLE_WEIGHTS_OU = {
    "poisson": 0.45,       # Dixon-Coles (gól piacon a legerősebb)
    "stats": 0.30,         # Stat O/U ráták (itt fontos)
    "form": 0.15,          # Forma
    "strength": 0.10,      # Erősség rating
}

# GG/NG piaci súlyok
ENSEMBLE_WEIGHTS_GGNG = {
    "poisson": 0.40,       # Dixon-Coles
    "stats": 0.35,         # GG/NG stat ráták
    "form": 0.15,          # Forma
    "strength": 0.10,      # Erősség rating
}

# === Probability Calibration (shrinkage) ===
# Szélsőséges valószínűségek visszahúzása a realitás felé
CALIBRATION_SHRINKAGE = 0.12  # 12% shrinkage az átlag felé
CALIBRATION_MIN_PROB = 0.03   # Minimum 3% bármely kimenetelre
CALIBRATION_MAX_PROB = 0.92   # Maximum 92% bármely kimenetelre

# === Időszúlyozás ===
TIME_DECAY_FACTOR = 0.05   # Exponenciális súlycsökkenés régebbi meccsekre
H2H_RECENCY_DECAY = 0.10   # H2H meccsek időbeli súlycsökkenése

# === Value Bet szűrők (szigorúbb) ===
VALUE_BET_MIN_ODDS = 1.25       # Minimum odds value bethez
VALUE_BET_MAX_ODDS = 8.00       # Maximum odds (túl magas = gyanús)
VALUE_BET_MIN_CONFIDENCE = 0.45 # Minimum betting confidence
VALUE_BET_MIN_EDGE = 0.05       # Minimum calibrated edge (5%)

# === Odds szűrők (alacsony odds tippek kiszűrése) ===
MIN_ODDS_SINGLE = 1.50          # Minimum odds single tipphez
MIN_ODDS_COMBO = 1.30           # Minimum odds kombi tételhez
MIN_ODDS_VALUE = 1.70           # Minimum odds value bethez
MIN_ODDS_DISPLAY = 1.25         # Minimum odds megjelenítéshez

# === Szelvény beállítások ===
TICKET_MIN_MATCHES = 3
TICKET_MAX_MATCHES = 6       # Csökkentve 8-ról (rövidebb kombik jobbak)
TICKET_CONSERVATIVE_MAX_ODDS = 1.60  # Konzervatív tipp max odds
TICKET_RISKY_MIN_ODDS = 2.50         # Rizikós tipp min odds

# === Adatminőség szűrők ===
MIN_MATCHES_FOR_PREDICTION = 5  # Minimum meccs történet predikcióhoz
MIN_MATCHES_FOR_CONFIDENCE = 10 # Minimum meccs magas konfidenciához

# === Meccs szűrők ===
EXCLUDED_KEYWORDS = [
    "U17", "U18", "U19", "U20", "U21", "U23",
    "Reserve", "Reserves", "Youth", "Academy",
    "Women", "Frauen", "Femmes", "Femenino", "Feminino",
    "Friendly", "Club Friendly",
    "Amateur", "Amateure",
]

# === Támogatott ligák ===
# Top ligák (magas adatminőség) + másodvonalbeli ligák
SUPPORTED_LEAGUES = {
    # === Top 5 liga (high quality) ===
    "PL": {
        "name": "Premier League",
        "sofascore_tournament_id": 17,
        "odds_api_sport_key": "soccer_epl",
        "quality": "high",
    },
    "BL1": {
        "name": "Bundesliga",
        "sofascore_tournament_id": 35,
        "odds_api_sport_key": "soccer_germany_bundesliga",
        "quality": "high",
    },
    "SA": {
        "name": "Serie A",
        "sofascore_tournament_id": 23,
        "odds_api_sport_key": "soccer_italy_serie_a",
        "quality": "high",
    },
    "PD": {
        "name": "La Liga",
        "sofascore_tournament_id": 8,
        "odds_api_sport_key": "soccer_spain_la_liga",
        "quality": "high",
    },
    "FL1": {
        "name": "Ligue 1",
        "sofascore_tournament_id": 34,
        "odds_api_sport_key": "soccer_france_ligue_one",
        "quality": "high",
    },
    # === Erős másodvonalbeli ligák (medium quality) ===
    "PPL": {
        "name": "Primeira Liga",
        "sofascore_tournament_id": 238,
        "odds_api_sport_key": "soccer_portugal_primeira_liga",
        "quality": "medium",
    },
    "ERE": {
        "name": "Eredivisie",
        "sofascore_tournament_id": 37,
        "odds_api_sport_key": "soccer_netherlands_eredivisie",
        "quality": "medium",
    },
    "BEL": {
        "name": "Belgian Pro League",
        "sofascore_tournament_id": 38,
        "odds_api_sport_key": "soccer_belgium_first_div",
        "quality": "medium",
    },
    "TURK": {
        "name": "Süper Lig",
        "sofascore_tournament_id": 52,
        "odds_api_sport_key": "soccer_turkey_super_league",
        "quality": "medium",
    },
    "SCO": {
        "name": "Scottish Premiership",
        "sofascore_tournament_id": 36,
        "odds_api_sport_key": "soccer_scotland_premiership",
        "quality": "medium",
    },
    "ELC": {
        "name": "Championship",
        "sofascore_tournament_id": 18,
        "odds_api_sport_key": "soccer_efl_champ",
        "quality": "medium",
    },
    "BL2": {
        "name": "2. Bundesliga",
        "sofascore_tournament_id": 44,
        "odds_api_sport_key": "soccer_germany_bundesliga2",
        "quality": "medium",
    },
    "SER": {
        "name": "Serie B",
        "sofascore_tournament_id": 53,
        "odds_api_sport_key": "soccer_italy_serie_b",
        "quality": "medium",
    },
    "NB1": {
        "name": "OTP Bank Liga",
        "sofascore_tournament_id": 156,
        "odds_api_sport_key": "soccer_hungary_nb1",
        "quality": "medium",
    },
    # === Nemzetközi ===
    "UCL": {
        "name": "Champions League",
        "sofascore_tournament_id": 7,
        "odds_api_sport_key": "soccer_uefa_champs_league",
        "quality": "high",
    },
    "UEL": {
        "name": "Europa League",
        "sofascore_tournament_id": 679,
        "odds_api_sport_key": "soccer_uefa_europa_league",
        "quality": "high",
    },
    "UECL": {
        "name": "Conference League",
        "sofascore_tournament_id": 17015,
        "odds_api_sport_key": "soccer_uefa_europa_conference_league",
        "quality": "medium",
    },
}

# Inverz lookup-ok
SOFASCORE_ID_TO_LEAGUE = {
    v["sofascore_tournament_id"]: code
    for code, v in SUPPORTED_LEAGUES.items()
}
ODDS_API_KEY_TO_LEAGUE = {
    v["odds_api_sport_key"]: code
    for code, v in SUPPORTED_LEAGUES.items()
}

# === Ismert csapatnév eltérések (Sofascore ↔ Odds API manuális mapping) ===
KNOWN_NAME_MAPPINGS = {
    "Wolverhampton": "Wolverhampton Wanderers",
    "Wolves": "Wolverhampton Wanderers",
    "Nottingham Forest": "Nottingham Forest",
    "Brighton": "Brighton and Hove Albion",
    "Tottenham Hotspur": "Tottenham Hotspur",
    "AFC Bournemouth": "Bournemouth",
    "West Ham United": "West Ham United",
    "Newcastle United": "Newcastle United",
    "Manchester United": "Manchester United",
    "Manchester City": "Manchester City",
    "Borussia Mönchengladbach": "Borussia Monchengladbach",
    "1. FSV Mainz 05": "FSV Mainz 05",
    "FC Internazionale Milano": "Inter Milan",
    "FC Internazionale": "Inter Milan",
    "SSC Napoli": "Napoli",
    "SS Lazio": "Lazio",
    "AC Milan": "AC Milan",
    "AS Roma": "Roma",
    "ACF Fiorentina": "Fiorentina",
    "Hellas Verona FC": "Hellas Verona",
    "Paris Saint-Germain": "Paris Saint Germain",
    "Olympique de Marseille": "Marseille",
    "Olympique Lyonnais": "Lyon",
    "AS Monaco": "Monaco",
    "RC Strasbourg Alsace": "Strasbourg",
    "Stade Rennais FC 1901": "Rennes",
    "Club Atlético de Madrid": "Atletico Madrid",
    "Real Sociedad de Fútbol": "Real Sociedad",
    "Real Betis Balompié": "Real Betis",
    "RC Celta de Vigo": "Celta Vigo",
    "Rayo Vallecano de Madrid": "Rayo Vallecano",
}

# Inverz mapping is
_INVERSE_NAME_MAPPINGS = {v: k for k, v in KNOWN_NAME_MAPPINGS.items()}
KNOWN_NAME_MAPPINGS.update(_INVERSE_NAME_MAPPINGS)

# === Fuzzy matching threshold ===
FUZZY_MATCH_THRESHOLD = 0.65


def fuzzy_match_teams(name1: str, name2: str) -> float:
    """Két csapatnév hasonlóságát számítja ki (0.0 - 1.0)."""
    if name1.lower() == name2.lower():
        return 1.0

    mapped = KNOWN_NAME_MAPPINGS.get(name1, "")
    if mapped.lower() == name2.lower():
        return 1.0
    mapped = KNOWN_NAME_MAPPINGS.get(name2, "")
    if mapped.lower() == name1.lower():
        return 1.0

    return SequenceMatcher(
        None, name1.lower(), name2.lower()
    ).ratio()


def find_best_match(
    name: str, candidates: list[str], threshold: float = FUZZY_MATCH_THRESHOLD
) -> str | None:
    """Megkeresi a legjobb egyezést a jelöltek között."""
    best_score = 0.0
    best_match = None

    for candidate in candidates:
        score = fuzzy_match_teams(name, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= threshold:
        return best_match
    return None
