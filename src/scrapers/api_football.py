"""football-data.org API kliens - megbízható cloud-kompatibilis adatforrás.

Sofascore fallback ha a Sofascore blokkolja a cloud szerver IP-jét.

Ingyenes tier: 10 request/perc - bőven elég.
Regisztráció: https://www.football-data.org/client/register
Nincs szezon korlátozás!

Env változó: FOOTBALL_DATA_KEY
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
)

logger = logging.getLogger(__name__)

# football-data.org liga kódok (megegyeznek a mi kódjainkkal)
_LEAGUE_CODES = {
    "PL": "PL",     # Premier League
    "BL1": "BL1",   # Bundesliga
    "SA": "SA",      # Serie A
    "PD": "PD",      # La Liga (Primera Division)
    "FL1": "FL1",    # Ligue 1
}

_LEAGUE_NAMES = {
    "PL": "Premier League",
    "BL1": "Bundesliga",
    "SA": "Serie A",
    "PD": "La Liga",
    "FL1": "Ligue 1",
}


class FootballDataClient:
    """football-data.org API kliens - Sofascore fallback."""

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key: str = ""):
        import os
        self.api_key = api_key or os.getenv("FOOTBALL_DATA_KEY", "")
        self._session = requests.Session()
        self._session.headers.update({
            "X-Auth-Token": self.api_key,
        })
        self._last_request_time = 0.0

    @property
    def is_available(self) -> bool:
        """Van-e API kulcs beállítva."""
        return bool(self.api_key) and self.api_key != "your_key_here"

    def _rate_limit(self):
        """10 req/perc - 2 mp szünet kérések között (burst engedélyezett)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < 2.0:
            time.sleep(2.0 - elapsed)
        self._last_request_time = time.time()

    def _cache_key(self, url: str, params: dict) -> str:
        key_str = f"fdata_{url}_{json.dumps(params, sort_keys=True)}"
        return f"fdata_{hashlib.md5(key_str.encode()).hexdigest()}.json"

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

    def _request(self, endpoint: str, params: dict | None = None, use_cache: bool = True) -> dict | None:
        url = f"{self.BASE_URL}/{endpoint}"
        params = params or {}
        cache_key = self._cache_key(url, params)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        self._rate_limit()

        try:
            resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                data = resp.json()
                if use_cache:
                    self._save_cache(cache_key, data)
                return data
            elif resp.status_code == 429:
                logger.warning("football-data.org rate limit - várakozás...")
                time.sleep(60)
                return None
            else:
                logger.warning("football-data.org %d: %s", resp.status_code, endpoint)

        except requests.RequestException as e:
            logger.warning("football-data.org request hiba: %s", e)

        return None

    def get_scheduled_matches(self, date: str | None = None) -> list[dict]:
        """Mai meccsek lekérdezése a támogatott ligákból.

        Returns:
            Sofascore-kompatibilis formátumú meccs lista.
        """
        if not self.is_available:
            logger.info("football-data.org kulcs nincs beállítva, fallback kihagyva")
            return []

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        logger.info("football-data.org meccsek lekérdezése: %s", date)
        all_matches = []

        for league_code, fd_code in _LEAGUE_CODES.items():
            data = self._request(f"competitions/{fd_code}/matches", {
                "dateFrom": date,
                "dateTo": date,
            })

            if not data or "matches" not in data:
                continue

            for match in data["matches"]:
                home = match.get("homeTeam", {})
                away = match.get("awayTeam", {})

                all_matches.append({
                    "event_id": match.get("id", 0),
                    "home_team": home.get("name", ""),
                    "home_team_id": home.get("id", 0),
                    "away_team": away.get("name", ""),
                    "away_team_id": away.get("id", 0),
                    "tournament_id": 0,
                    "league_code": league_code,
                    "league_name": _LEAGUE_NAMES.get(league_code, ""),
                    "start_timestamp": _parse_utc_date(match.get("utcDate", "")),
                    "_source": "football_data",
                })

        logger.info("football-data.org: %d meccs találva", len(all_matches))
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

        data = self._request(f"teams/{team_id}/matches", {
            "status": "FINISHED",
            "limit": n,
        })

        if not data or "matches" not in data:
            return []

        matches = []
        for match in data["matches"]:
            home = match.get("homeTeam", {})
            away = match.get("awayTeam", {})
            score = match.get("score", {})
            full_time = score.get("fullTime", {})
            half_time = score.get("halfTime", {})

            home_goals = full_time.get("home")
            away_goals = full_time.get("away")

            if home_goals is None or away_goals is None:
                continue

            match_data = {
                "event_id": match.get("id", 0),
                "home_team": home.get("name", ""),
                "home_team_id": home.get("id", 0),
                "away_team": away.get("name", ""),
                "away_team_id": away.get("id", 0),
                "home_goals": int(home_goals),
                "away_goals": int(away_goals),
                "tournament_id": 0,
                "start_timestamp": _parse_utc_date(match.get("utcDate", "")),
            }

            # Félidei eredmény
            ht_home = half_time.get("home")
            ht_away = half_time.get("away")
            if ht_home is not None and ht_away is not None:
                match_data["ht_home_goals"] = int(ht_home)
                match_data["ht_away_goals"] = int(ht_away)

            matches.append(match_data)

        # Legutóbbi meccsek elöl (fordított időrend)
        matches.sort(key=lambda m: m.get("start_timestamp", 0), reverse=True)
        return matches[:n]


def _parse_utc_date(utc_date_str: str) -> int:
    """UTC dátum stringből UNIX timestamp."""
    if not utc_date_str:
        return 0
    try:
        # "2026-03-15T15:00:00Z" formátum
        dt = datetime.fromisoformat(utc_date_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, AttributeError):
        return 0
