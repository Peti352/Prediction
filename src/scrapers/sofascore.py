"""Sofascore API kliens - meccsek és statisztikák lekérdezése.

A Sofascore nyilvános API-ját használja:
- Mai meccsek lekérdezése (szűrés támogatott ligákra)
- Csapat utolsó N meccsének lekérdezése (gólstatisztikák)
- Csapat keresés név alapján
"""

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import requests

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

from src.config import (
    CACHE_DIR,
    CACHE_TTL_HOURS,
    REQUEST_TIMEOUT,
    SOFASCORE_BASE_URL,
    SOFASCORE_REQUEST_DELAY,
    SOFASCORE_ID_TO_LEAGUE,
    USER_AGENT,
)


class SofascoreClient:
    """Sofascore API kliens meccsekhez és statisztikákhoz."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": "https://www.sofascore.com/",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._cloud_session = None
        self._last_request_time = 0.0

    def _get_cloud_session(self):
        """Cloudscraper session 403 fallback-hez."""
        if self._cloud_session is None and cloudscraper:
            self._cloud_session = cloudscraper.create_scraper()
            self._cloud_session.headers.update({
                "Referer": "https://www.sofascore.com/",
                "Accept": "application/json",
            })
        return self._cloud_session

    def _rate_limit(self):
        """Rate limit betartása (min SOFASCORE_REQUEST_DELAY mp kérések között)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < SOFASCORE_REQUEST_DELAY:
            time.sleep(SOFASCORE_REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    def _cache_key(self, url: str) -> str:
        """Cache fájl neve az URL-ből."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"sofascore_{url_hash}.json"

    def _get_cached(self, cache_key: str) -> dict | None:
        """Cache-ből olvasás."""
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
        """Cache-be mentés."""
        cache_file = CACHE_DIR / cache_key
        try:
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def _request(self, url: str, use_cache: bool = True) -> dict | None:
        """HTTP GET kérés rate limit-tel és cache-sel.

        Ha 403-at kap, cloudscraper-rel próbálja újra.
        """
        cache_key = self._cache_key(url)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        self._rate_limit()

        try:
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 403:
                # Fallback: cloudscraper
                cloud = self._get_cloud_session()
                if cloud:
                    self._rate_limit()
                    resp = cloud.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                data = resp.json()
                if use_cache:
                    self._save_cache(cache_key, data)
                return data

        except (requests.RequestException, json.JSONDecodeError):
            pass

        return None

    def get_scheduled_matches(self, date: str | None = None) -> list[dict]:
        """Mai (vagy adott dátumú) meccsek lekérdezése.

        Args:
            date: Dátum YYYY-MM-DD formátumban. None = ma.

        Returns:
            Támogatott ligák meccsei. Minden elem:
            {
                "event_id": int,
                "home_team": str, "home_team_id": int,
                "away_team": str, "away_team_id": int,
                "tournament_id": int, "league_code": str,
                "league_name": str, "start_timestamp": int,
            }
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        url = f"{SOFASCORE_BASE_URL}/sport/football/scheduled-events/{date}"
        data = self._request(url, use_cache=True)

        if not data or "events" not in data:
            return []

        matches = []
        for event in data["events"]:
            tournament = event.get("tournament", {})
            unique_tournament = tournament.get("uniqueTournament", {})
            tournament_id = unique_tournament.get("id")

            # Csak támogatott ligák
            if tournament_id not in SOFASCORE_ID_TO_LEAGUE:
                continue

            league_code = SOFASCORE_ID_TO_LEAGUE[tournament_id]
            home_team = event.get("homeTeam", {})
            away_team = event.get("awayTeam", {})

            matches.append({
                "event_id": event.get("id"),
                "home_team": home_team.get("name", ""),
                "home_team_id": home_team.get("id"),
                "away_team": away_team.get("name", ""),
                "away_team_id": away_team.get("id"),
                "tournament_id": tournament_id,
                "league_code": league_code,
                "league_name": unique_tournament.get("name", ""),
                "start_timestamp": event.get("startTimestamp", 0),
            })

        return matches

    def get_team_last_n_matches(
        self, team_id: int, n: int = 10
    ) -> list[dict]:
        """Csapat utolsó N befejezett meccsének lekérdezése.

        Args:
            team_id: Sofascore csapat ID
            n: Hány meccset kérünk (max ~20 oldalanként)

        Returns:
            Meccsek listája, mindegyik:
            {
                "event_id": int,
                "home_team": str, "home_team_id": int,
                "away_team": str, "away_team_id": int,
                "home_goals": int, "away_goals": int,
                "tournament_id": int,
            }
        """
        matches = []
        page = 0

        while len(matches) < n:
            url = f"{SOFASCORE_BASE_URL}/team/{team_id}/events/last/{page}"
            data = self._request(url, use_cache=True)

            if not data or "events" not in data:
                break

            events = data["events"]
            if not events:
                break

            for event in events:
                home_score = event.get("homeScore", {})
                away_score = event.get("awayScore", {})

                home_goals = home_score.get("current")
                away_goals = away_score.get("current")

                # Csak befejezett meccsek score-ral
                status = event.get("status", {})
                if status.get("type") != "finished" or home_goals is None or away_goals is None:
                    continue

                home_team = event.get("homeTeam", {})
                away_team = event.get("awayTeam", {})
                tournament = event.get("tournament", {})
                unique_tournament = tournament.get("uniqueTournament", {})

                matches.append({
                    "event_id": event.get("id"),
                    "home_team": home_team.get("name", ""),
                    "home_team_id": home_team.get("id"),
                    "away_team": away_team.get("name", ""),
                    "away_team_id": away_team.get("id"),
                    "home_goals": int(home_goals),
                    "away_goals": int(away_goals),
                    "tournament_id": unique_tournament.get("id"),
                })

                if len(matches) >= n:
                    break

            page += 1
            # Max 3 oldal (biztonsági limit)
            if page >= 3:
                break

        return matches[:n]

    def search_team(self, query: str) -> list[dict]:
        """Csapat keresés név alapján.

        Returns:
            Találatok listája: [{"id": int, "name": str, "country": str}, ...]
        """
        url = f"{SOFASCORE_BASE_URL}/search/all?q={query}"
        data = self._request(url, use_cache=False)

        if not data:
            return []

        results = []
        # A keresés eredmény "teams" kulcs alatt van
        teams = data.get("teams", [])
        for team in teams:
            results.append({
                "id": team.get("id"),
                "name": team.get("name", ""),
                "country": team.get("country", {}).get("name", ""),
            })

        return results
