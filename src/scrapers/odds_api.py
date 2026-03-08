"""The Odds API kliens - oddsok lekérdezése.

Elsődleges odds forrás. Free tier: 500 request/hó.
Cache: 6 óra TTL a kérések minimalizálásához.

Piacok: h2h (1X2), totals (O/U 2.5), alternate_totals (O/U 1.5, 3.5).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime

import requests

from src.config import (
    CACHE_DIR,
    CACHE_TTL_HOURS,
    ODDS_API_BASE_URL,
    ODDS_API_KEY,
    REQUEST_TIMEOUT,
)


@dataclass
class MatchOdds:
    """Egy meccs oddsai (több bookmaker átlaga)."""
    home_win: float = 0.0
    draw: float = 0.0
    away_win: float = 0.0
    over_15: float = 0.0
    under_15: float = 0.0
    over_25: float = 0.0
    under_25: float = 0.0
    over_35: float = 0.0
    under_35: float = 0.0
    gg: float = 0.0
    ng: float = 0.0
    bookmaker: str = ""


@dataclass
class MatchEvent:
    """Egy meccs esemény Sofascore + Odds API adatokkal."""
    home_team: str = ""
    away_team: str = ""
    home_team_id: int = 0       # Sofascore ID
    away_team_id: int = 0       # Sofascore ID
    kickoff: datetime = field(default_factory=datetime.now)
    competition: str = ""
    league_code: str = ""
    sofascore_event_id: int = 0
    odds: MatchOdds = field(default_factory=MatchOdds)


class OddsAPIClient:
    """The Odds API kliens."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or ODDS_API_KEY
        self._session = requests.Session()
        self._requests_remaining = None

    def _cache_key(self, url: str, params: dict) -> str:
        """Cache fájl neve."""
        key_str = f"{url}_{json.dumps(params, sort_keys=True)}"
        url_hash = hashlib.md5(key_str.encode()).hexdigest()
        return f"oddsapi_{url_hash}.json"

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

    def _save_cache(self, cache_key: str, data):
        """Cache-be mentés."""
        cache_file = CACHE_DIR / cache_key
        try:
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def _request(self, url: str, params: dict, use_cache: bool = True) -> list | dict | None:
        """HTTP GET kérés cache-sel és request counter-rel."""
        cache_key = self._cache_key(url, params)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached

        params["apiKey"] = self.api_key

        try:
            resp = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)

            # Request számláló követése
            remaining = resp.headers.get("x-requests-remaining")
            if remaining is not None:
                self._requests_remaining = int(remaining)

            if resp.status_code == 200:
                data = resp.json()
                if use_cache:
                    self._save_cache(cache_key, data)
                return data
            elif resp.status_code == 401:
                raise ValueError("Érvénytelen Odds API kulcs!")
            elif resp.status_code == 429:
                raise ValueError("Odds API rate limit elérve!")

        except requests.RequestException:
            pass

        return None

    @property
    def requests_remaining(self) -> int | None:
        """Hátralévő API kérések száma a hónapban."""
        return self._requests_remaining

    def get_odds_for_sport(
        self,
        sport_key: str,
        markets: str = "h2h,totals",
        regions: str = "eu",
    ) -> list[dict]:
        """Oddsok lekérdezése egy sport/liga összes meccsére.

        Args:
            sport_key: Odds API sport kulcs (pl. "soccer_epl")
            markets: Piacok vesszővel elválasztva
            regions: Régió (eu, uk, us)

        Returns:
            Meccsek listája odds adatokkal.
        """
        url = f"{ODDS_API_BASE_URL}/sports/{sport_key}/odds/"
        params = {
            "markets": markets,
            "regions": regions,
            "oddsFormat": "decimal",
        }

        data = self._request(url, params)
        if data is None:
            return []

        return data if isinstance(data, list) else []

    def get_event_odds(
        self,
        sport_key: str,
        event_id: str,
        markets: str = "alternate_totals",
        regions: str = "eu",
    ) -> dict | None:
        """Egy meccs részletes oddsai (O/U 1.5, 3.5 stb.).

        FIGYELEM: Takarékosan használd! 500 req/hó limit.
        """
        url = f"{ODDS_API_BASE_URL}/sports/{sport_key}/events/{event_id}/odds"
        params = {
            "markets": markets,
            "regions": regions,
            "oddsFormat": "decimal",
        }

        return self._request(url, params)

    def parse_event_odds(self, event: dict) -> MatchOdds:
        """Odds API event objektumból MatchOdds kinyerése.

        Több bookmaker oddsát átlagolja.
        """
        odds = MatchOdds()
        bookmakers = event.get("bookmakers", [])
        if not bookmakers:
            return odds

        h2h_odds = []  # [(home, draw, away), ...]
        totals_odds = {}  # {point: [(over, under), ...]}

        for bm in bookmakers:
            for market in bm.get("markets", []):
                market_key = market.get("key", "")
                outcomes = market.get("outcomes", [])

                if market_key == "h2h":
                    h, d, a = 0.0, 0.0, 0.0
                    for o in outcomes:
                        if o.get("name") == "Home" or o.get("name") == event.get("home_team"):
                            h = o.get("price", 0.0)
                        elif o.get("name") == "Draw":
                            d = o.get("price", 0.0)
                        elif o.get("name") == "Away" or o.get("name") == event.get("away_team"):
                            a = o.get("price", 0.0)
                    if h > 0:
                        h2h_odds.append((h, d, a))

                elif market_key in ("totals", "alternate_totals"):
                    for o in outcomes:
                        point = o.get("point", 0)
                        price = o.get("price", 0.0)
                        name = o.get("name", "")
                        if point not in totals_odds:
                            totals_odds[point] = {"over": [], "under": []}
                        if name == "Over":
                            totals_odds[point]["over"].append(price)
                        elif name == "Under":
                            totals_odds[point]["under"].append(price)

        # H2H átlagolás
        if h2h_odds:
            odds.home_win = sum(h for h, _, _ in h2h_odds) / len(h2h_odds)
            odds.draw = sum(d for _, d, _ in h2h_odds) / len(h2h_odds)
            odds.away_win = sum(a for _, _, a in h2h_odds) / len(h2h_odds)

        # Totals átlagolás
        for point, values in totals_odds.items():
            over_prices = values["over"]
            under_prices = values["under"]
            avg_over = sum(over_prices) / len(over_prices) if over_prices else 0
            avg_under = sum(under_prices) / len(under_prices) if under_prices else 0

            if point == 1.5:
                odds.over_15 = avg_over
                odds.under_15 = avg_under
            elif point == 2.5:
                odds.over_25 = avg_over
                odds.under_25 = avg_under
            elif point == 3.5:
                odds.over_35 = avg_over
                odds.under_35 = avg_under

        # Bookmaker info
        if bookmakers:
            odds.bookmaker = bookmakers[0].get("title", "")

        return odds

    def get_parsed_odds_for_sport(
        self, sport_key: str
    ) -> list[tuple[str, str, str, MatchOdds]]:
        """Oddsok lekérdezése és parse-olása egy ligához.

        Returns:
            Lista: (event_id, home_team, away_team, MatchOdds)
        """
        events = self.get_odds_for_sport(sport_key)
        results = []

        for event in events:
            event_id = event.get("id", "")
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            odds = self.parse_event_odds(event)
            results.append((event_id, home, away, odds))

        return results
