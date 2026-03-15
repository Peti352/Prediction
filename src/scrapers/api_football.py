"""API-Football fallback kliens - megbízható cloud-kompatibilis adatforrás.

Használat: Ha a Sofascore blokkolja a cloud szerver IP-jét (Railway, stb.),
ez az API szolgáltatja a meccs adatokat.

Ingyenes tier: 100 request/nap - bőven elég a napi elemzéshez.
Regisztráció: https://www.api-football.com/ (vagy https://rapidapi.com/api-sports/api/api-football)

Env változó: API_FOOTBALL_KEY
"""

import hashlib
import json
import logging
import time
from datetime import datetime

import requests

from src.config import (
    CACHE_DIR,
    CACHE_TTL_HOURS,
    REQUEST_TIMEOUT,
    SUPPORTED_LEAGUES,
)

logger = logging.getLogger(__name__)

# API-Football liga ID-k
_LEAGUE_IDS = {
    "PL": 39,    # Premier League
    "BL1": 78,   # Bundesliga
    "SA": 135,   # Serie A
    "PD": 140,   # La Liga
    "FL1": 61,   # Ligue 1
}

# Inverz: API-Football league ID -> liga kód
_LEAGUE_ID_TO_CODE = {v: k for k, v in _LEAGUE_IDS.items()}

# Liga nevek
_LEAGUE_NAMES = {
    "PL": "Premier League",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "PD": "La Liga",
    "FL1": "Ligue 1",
}


class APIFootballClient:
    """API-Football kliens - Sofascore fallback."""

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str = ""):
        import os
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY", "")
        self._session = requests.Session()
        self._session.headers.update({
            "x-apisports-key": self.api_key,
        })
        self._requests_today = 0

    @property
    def is_available(self) -> bool:
        """Van-e API kulcs beállítva."""
        return bool(self.api_key) and self.api_key != "your_key_here"

    def _cache_key(self, url: str, params: dict) -> str:
        key_str = f"apifb_{url}_{json.dumps(params, sort_keys=True)}"
        return f"apifb_{hashlib.md5(key_str.encode()).hexdigest()}.json"

    def _get_cached(self, cache_key: str) -> dict | None:
        cache_file = CACHE_DIR / cache_key
        if cache_file.exists():
            age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
            if age_hours < CACHE_TTL_HOURS:
                try:
                    return json.loads(cache_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
        return None

    def _save_cache(self, cache_key: str, data: dict):
        cache_file = CACHE_DIR / cache_key
        try:
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def _request(self, endpoint: str, params: dict, use_cache: bool = True) -> dict | None:
        url = f"{self.BASE_URL}/{endpoint}"
        cache_key = self._cache_key(url, params)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        try:
            resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            self._requests_today += 1

            if resp.status_code == 200:
                data = resp.json()
                if data.get("errors"):
                    logger.warning("API-Football hiba: %s", data["errors"])
                    return None
                if use_cache:
                    self._save_cache(cache_key, data)
                return data
            else:
                logger.warning("API-Football %d: %s", resp.status_code, endpoint)

        except requests.RequestException as e:
            logger.warning("API-Football request hiba: %s", e)

        return None

    def get_scheduled_matches(self, date: str | None = None) -> list[dict]:
        """Mai meccsek lekérdezése a támogatott ligákból.

        Returns:
            Sofascore-kompatibilis formátumú meccs lista.
        """
        if not self.is_available:
            logger.info("API-Football kulcs nincs beállítva, fallback kihagyva")
            return []

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        logger.info("API-Football meccsek lekérdezése: %s", date)
        all_matches = []

        for league_code, league_id in _LEAGUE_IDS.items():
            # Aktuális szezon meghatározása
            year = datetime.now().year
            month = datetime.now().month
            season = year if month >= 7 else year - 1

            data = self._request("fixtures", {
                "league": league_id,
                "season": season,
                "date": date,
            })

            if not data or "response" not in data:
                continue

            for fixture in data["response"]:
                teams = fixture.get("teams", {})
                home = teams.get("home", {})
                away = teams.get("away", {})
                fixture_info = fixture.get("fixture", {})

                all_matches.append({
                    "event_id": fixture_info.get("id", 0),
                    "home_team": home.get("name", ""),
                    "home_team_id": home.get("id", 0),
                    "away_team": away.get("name", ""),
                    "away_team_id": away.get("id", 0),
                    "tournament_id": league_id,
                    "league_code": league_code,
                    "league_name": _LEAGUE_NAMES.get(league_code, ""),
                    "start_timestamp": fixture_info.get("timestamp", 0),
                    "_source": "api_football",
                })

        logger.info("API-Football: %d meccs találva", len(all_matches))
        return all_matches

    def get_team_last_n_matches(
        self, team_id: int, n: int = 20
    ) -> list[dict]:
        """Csapat utolsó N meccsének lekérdezése.

        Returns:
            Sofascore-kompatibilis formátumú meccs lista.
        """
        if not self.is_available:
            return []

        data = self._request("fixtures", {
            "team": team_id,
            "last": n,
        })

        if not data or "response" not in data:
            return []

        matches = []
        for fixture in data["response"]:
            teams = fixture.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            goals = fixture.get("goals", {})
            score = fixture.get("score", {})
            fixture_info = fixture.get("fixture", {})

            home_goals = goals.get("home")
            away_goals = goals.get("away")

            if home_goals is None or away_goals is None:
                continue

            match_data = {
                "event_id": fixture_info.get("id", 0),
                "home_team": home.get("name", ""),
                "home_team_id": home.get("id", 0),
                "away_team": away.get("name", ""),
                "away_team_id": away.get("id", 0),
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "tournament_id": fixture.get("league", {}).get("id"),
                "start_timestamp": fixture_info.get("timestamp", 0),
            }

            # Félidei eredmény
            halftime = score.get("halftime", {})
            ht_home = halftime.get("home")
            ht_away = halftime.get("away")
            if ht_home is not None and ht_away is not None:
                match_data["ht_home_goals"] = int(ht_home)
                match_data["ht_away_goals"] = int(ht_away)

            matches.append(match_data)

        return matches

    def get_head_to_head(
        self, team1_id: int, team2_id: int, last: int = 10
    ) -> list[dict]:
        """Head-to-head meccsek lekérdezése.

        Returns:
            Sofascore-kompatibilis formátumú meccs lista.
        """
        if not self.is_available:
            return []

        data = self._request("fixtures/headtohead", {
            "h2h": f"{team1_id}-{team2_id}",
            "last": last,
        })

        if not data or "response" not in data:
            return []

        matches = []
        for fixture in data["response"]:
            teams = fixture.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            goals = fixture.get("goals", {})
            fixture_info = fixture.get("fixture", {})

            home_goals = goals.get("home")
            away_goals = goals.get("away")

            if home_goals is None or away_goals is None:
                continue

            matches.append({
                "event_id": fixture_info.get("id", 0),
                "home_team": home.get("name", ""),
                "home_team_id": home.get("id", 0),
                "away_team": away.get("name", ""),
                "away_team_id": away.get("id", 0),
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "start_timestamp": fixture_info.get("timestamp", 0),
            })

        return matches
