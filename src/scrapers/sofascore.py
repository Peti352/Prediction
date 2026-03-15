"""Sofascore API kliens - meccsek és statisztikák lekérdezése.

A Sofascore nyilvános API-ját használja:
- Mai meccsek lekérdezése (szűrés támogatott ligákra)
- Csapat utolsó N meccsének lekérdezése (gólstatisztikák)
- Csapat keresés név alapján

Cloud szerveren (Railway) a Sofascore blokkolhat, ezért:
- cloudscraper elsődleges használata
- Több User-Agent rotálás
- Részletes hiba logolás
"""

import hashlib
import json
import logging
import random
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

logger = logging.getLogger(__name__)

# User-Agent rotálás a blokkolás elkerülésére
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


class SofascoreClient:
    """Sofascore API kliens meccsekhez és statisztikákhoz."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": random.choice(_USER_AGENTS),
            "Referer": "https://www.sofascore.com/",
            "Origin": "https://www.sofascore.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,hu;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        self._cloud_session = None
        self._last_request_time = 0.0
        self._use_cloudscraper_first = True  # Cloud szervereken fontos

    def _get_cloud_session(self):
        """Cloudscraper session - elsődleges cloud szervereken."""
        if self._cloud_session is None and cloudscraper:
            self._cloud_session = cloudscraper.create_scraper(
                browser={
                    "browser": "chrome",
                    "platform": "windows",
                    "desktop": True,
                }
            )
            self._cloud_session.headers.update({
                "Referer": "https://www.sofascore.com/",
                "Origin": "https://www.sofascore.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
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

        Stratégia:
        1. Cache ellenőrzés
        2. Cloudscraper (elsődleges - cloud szerveren fontos)
        3. Requests fallback
        4. Részletes hiba logolás
        """
        cache_key = self._cache_key(url)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        self._rate_limit()

        # 1. próba: cloudscraper (jobban működik cloud szervereken)
        if self._use_cloudscraper_first:
            cloud = self._get_cloud_session()
            if cloud:
                try:
                    resp = cloud.get(url, timeout=REQUEST_TIMEOUT)
                    logger.debug("Sofascore cloudscraper %s -> %d", url.split("/")[-1], resp.status_code)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            if use_cache:
                                self._save_cache(cache_key, data)
                            return data
                        except json.JSONDecodeError:
                            logger.warning("Sofascore JSON decode hiba (cloudscraper): %s", url)
                    else:
                        logger.warning("Sofascore cloudscraper %d: %s", resp.status_code, url)
                except Exception as e:
                    logger.warning("Sofascore cloudscraper hiba: %s - %s", type(e).__name__, e)

        # 2. próba: sima requests
        try:
            # Rotáljuk a User-Agent-et minden kérésnél
            self._session.headers["User-Agent"] = random.choice(_USER_AGENTS)
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
            logger.debug("Sofascore requests %s -> %d", url.split("/")[-1], resp.status_code)

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if use_cache:
                        self._save_cache(cache_key, data)
                    return data
                except json.JSONDecodeError:
                    logger.warning("Sofascore JSON decode hiba (requests): %s", url)
            elif resp.status_code == 403:
                logger.warning("Sofascore 403 Forbidden - valószínűleg IP blokkolás: %s", url)
            else:
                logger.warning("Sofascore requests %d: %s", resp.status_code, url)

        except requests.RequestException as e:
            logger.warning("Sofascore requests hiba: %s - %s", type(e).__name__, e)

        return None

    def get_scheduled_matches(self, date: str | None = None) -> list[dict]:
        """Mai (vagy adott dátumú) meccsek lekérdezése.

        Args:
            date: Dátum YYYY-MM-DD formátumban. None = ma.

        Returns:
            Támogatott ligák meccsei.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        logger.info("Sofascore scheduled matches lekérdezés: %s", date)
        url = f"{SOFASCORE_BASE_URL}/sport/football/scheduled-events/{date}"
        data = self._request(url, use_cache=True)

        if not data:
            logger.warning("Sofascore nem válaszolt vagy üres válasz")
            return []

        if "events" not in data:
            logger.warning("Sofascore válaszban nincs 'events' kulcs. Kulcsok: %s", list(data.keys()))
            return []

        logger.info("Sofascore összes event: %d", len(data["events"]))

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

        logger.info("Támogatott ligák meccsek: %d", len(matches))
        return matches

    def get_team_last_n_matches(
        self, team_id: int, n: int = 20
    ) -> list[dict]:
        """Csapat utolsó N befejezett meccsének lekérdezése.

        Args:
            team_id: Sofascore csapat ID
            n: Hány meccset kérünk (alapértelmezett: 20 a mélyelemzéshez)

        Returns:
            Meccsek listája.
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

                match_data = {
                    "event_id": event.get("id"),
                    "home_team": home_team.get("name", ""),
                    "home_team_id": home_team.get("id"),
                    "away_team": away_team.get("name", ""),
                    "away_team_id": away_team.get("id"),
                    "home_goals": int(home_goals),
                    "away_goals": int(away_goals),
                    "tournament_id": unique_tournament.get("id"),
                    "start_timestamp": event.get("startTimestamp", 0),
                }

                # Félidei eredmény ha elérhető (trendekhez)
                ht_home = home_score.get("period1")
                ht_away = away_score.get("period1")
                if ht_home is not None and ht_away is not None:
                    match_data["ht_home_goals"] = int(ht_home)
                    match_data["ht_away_goals"] = int(ht_away)

                matches.append(match_data)

                if len(matches) >= n:
                    break

            page += 1
            # Max 5 oldal (20 meccshez több oldal kellhet)
            if page >= 5:
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
