"""Konfigurációs beállítások a TipMix Prediction System v2-höz.

Sofascore (meccs statisztikák) + The Odds API (oddsok) + TippmixPro (fallback).
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
FORM_MATCHES = 10          # Utolsó N meccs a formához
POISSON_MAX_GOALS = 7      # Poisson eloszlás max gól
MIN_CONFIDENCE = 0.55      # Minimum konfidencia szelvényhez
VALUE_BET_THRESHOLD = 0.05 # Minimum edge a value bet-hez (5%)

# === Szelvény beállítások ===
TICKET_MIN_MATCHES = 3
TICKET_MAX_MATCHES = 8
TICKET_SAFE_MAX_ODDS = 1.60     # "Biztos" tipp max odds
TICKET_RISKY_MIN_ODDS = 2.50    # "Rizikós" tipp min odds

# === Támogatott ligák ===
# Minden ligánál: Sofascore tournament ID + The Odds API sport key
SUPPORTED_LEAGUES = {
    "PL": {
        "name": "Premier League",
        "sofascore_tournament_id": 17,
        "odds_api_sport_key": "soccer_epl",
    },
    "BL1": {
        "name": "Bundesliga",
        "sofascore_tournament_id": 35,
        "odds_api_sport_key": "soccer_germany_bundesliga",
    },
    "SA": {
        "name": "Serie A",
        "sofascore_tournament_id": 23,
        "odds_api_sport_key": "soccer_italy_serie_a",
    },
    "PD": {
        "name": "La Liga",
        "sofascore_tournament_id": 8,
        "odds_api_sport_key": "soccer_spain_la_liga",
    },
    "FL1": {
        "name": "Ligue 1",
        "sofascore_tournament_id": 34,
        "odds_api_sport_key": "soccer_france_ligue_one",
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
    # Sofascore név → Odds API név (ahol a fuzzy match nem működik)
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
    """Két csapatnév hasonlóságát számítja ki (0.0 - 1.0).

    Először a KNOWN_NAME_MAPPINGS-ben keres, utána fuzzy matching.
    """
    # Exact match
    if name1.lower() == name2.lower():
        return 1.0

    # Known mapping
    mapped = KNOWN_NAME_MAPPINGS.get(name1, "")
    if mapped.lower() == name2.lower():
        return 1.0
    mapped = KNOWN_NAME_MAPPINGS.get(name2, "")
    if mapped.lower() == name1.lower():
        return 1.0

    # Fuzzy match
    return SequenceMatcher(
        None, name1.lower(), name2.lower()
    ).ratio()


def find_best_match(
    name: str, candidates: list[str], threshold: float = FUZZY_MATCH_THRESHOLD
) -> str | None:
    """Megkeresi a legjobb egyezést a jelöltek között.

    Returns:
        A legjobb egyező név, vagy None ha nincs elég jó egyezés.
    """
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
