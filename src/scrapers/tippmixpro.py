"""TippmixPro scraper - fallback odds forrás.

Selenium headless browser-rel scrapeli a TippmixPro.hu oldalt.
Csak akkor használjuk, ha az Odds API nem elérhető/kimerült.
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from src.config import (
    REQUEST_TIMEOUT,
    TIPPMIXPRO_BASE_URL,
    USER_AGENT,
)
from src.scrapers.odds_api import MatchOdds


class TippmixProScraper:
    """TippmixPro.hu scraper (fallback odds forrás)."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
        })

    def get_matches(self) -> list[tuple[str, str, MatchOdds]]:
        """Meccsek és oddsok scrapelése TippmixPro-ról.

        Returns:
            Lista: (home_team, away_team, MatchOdds)
        """
        # 1) Próbáljuk a JSON API-t
        matches = self._try_api_endpoint()
        if matches:
            return matches

        # 2) Fallback: HTML scraping
        matches = self._try_html_scraping()
        if matches:
            return matches

        # 3) Selenium fallback
        return self._try_selenium()

    def _try_api_endpoint(self) -> list[tuple[str, str, MatchOdds]]:
        """JSON API endpoint próba."""
        api_urls = [
            f"{TIPPMIXPRO_BASE_URL}/api/offer/football",
            f"{TIPPMIXPRO_BASE_URL}/api/v1/events/football",
            f"{TIPPMIXPRO_BASE_URL}/api/sportsbetting/offer",
        ]

        for url in api_urls:
            try:
                resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200 and resp.headers.get(
                    "content-type", ""
                ).startswith("application/json"):
                    data = resp.json()
                    return self._parse_api_response(data)
            except (requests.RequestException, json.JSONDecodeError):
                continue

        return []

    def _parse_api_response(self, data: dict | list) -> list[tuple[str, str, MatchOdds]]:
        """API válasz parse-olása."""
        matches = []
        events = data if isinstance(data, list) else data.get("events", data.get("matches", []))

        for event in events:
            if not isinstance(event, dict):
                continue

            home = event.get("homeTeam", event.get("home", {})  )
            away = event.get("awayTeam", event.get("away", {}))

            home_name = home.get("name", home) if isinstance(home, dict) else str(home)
            away_name = away.get("name", away) if isinstance(away, dict) else str(away)

            if not home_name or not away_name:
                continue

            odds = MatchOdds()

            # Odds kinyerése
            outcomes = event.get("odds", event.get("outcomes", {}))
            if isinstance(outcomes, dict):
                odds.home_win = float(outcomes.get("1", outcomes.get("home", 0)))
                odds.draw = float(outcomes.get("X", outcomes.get("draw", 0)))
                odds.away_win = float(outcomes.get("2", outcomes.get("away", 0)))
                odds.over_25 = float(outcomes.get("over25", outcomes.get("over_2_5", 0)))
                odds.under_25 = float(outcomes.get("under25", outcomes.get("under_2_5", 0)))
            elif isinstance(outcomes, list):
                for o in outcomes:
                    name = o.get("name", "").lower()
                    price = float(o.get("odds", o.get("price", 0)))
                    if name in ("1", "home"):
                        odds.home_win = price
                    elif name in ("x", "draw"):
                        odds.draw = price
                    elif name in ("2", "away"):
                        odds.away_win = price

            odds.bookmaker = "TippmixPro"
            matches.append((home_name, away_name, odds))

        return matches

    def _try_html_scraping(self) -> list[tuple[str, str, MatchOdds]]:
        """HTML oldalról scraping."""
        urls = [
            f"{TIPPMIXPRO_BASE_URL}/fogadas/labdarugas",
            f"{TIPPMIXPRO_BASE_URL}/sport/football",
            TIPPMIXPRO_BASE_URL,
        ]

        for url in urls:
            try:
                resp = self._session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    matches = self._parse_html(resp.text)
                    if matches:
                        return matches
            except requests.RequestException:
                continue

        return []

    def _parse_html(self, html: str) -> list[tuple[str, str, MatchOdds]]:
        """HTML parse-olás BeautifulSoup-pal."""
        soup = BeautifulSoup(html, "html.parser")
        matches = []

        # Többféle selector próba
        selectors = [
            "div.event-row",
            "tr.match-row",
            "div.match",
            "[data-event]",
        ]

        for selector in selectors:
            rows = soup.select(selector)
            if not rows:
                continue

            for row in rows:
                match = self._parse_row(row)
                if match:
                    matches.append(match)

            if matches:
                break

        return matches

    def _parse_row(self, row) -> tuple[str, str, MatchOdds] | None:
        """Egy meccs sor parse-olása."""
        # Csapatnevek keresése
        teams = row.select(".team-name, .participant, .competitor")
        if len(teams) < 2:
            text = row.get_text(" ", strip=True)
            parts = re.split(r"\s+[-–vs.]+\s+", text)
            if len(parts) < 2:
                return None
            home_name = parts[0].strip()
            away_name = parts[1].strip()
        else:
            home_name = teams[0].get_text(strip=True)
            away_name = teams[1].get_text(strip=True)

        if not home_name or not away_name:
            return None

        # Odds keresés
        odds = MatchOdds(bookmaker="TippmixPro")
        odds_elements = row.select(".odds-value, .odd, .price, [data-odds]")

        if len(odds_elements) >= 3:
            try:
                odds.home_win = float(odds_elements[0].get_text(strip=True).replace(",", "."))
                odds.draw = float(odds_elements[1].get_text(strip=True).replace(",", "."))
                odds.away_win = float(odds_elements[2].get_text(strip=True).replace(",", "."))
            except (ValueError, IndexError):
                pass

        return (home_name, away_name, odds)

    def _try_selenium(self) -> list[tuple[str, str, MatchOdds]]:
        """Selenium headless fallback."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument(f"user-agent={USER_AGENT}")

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(30)

            try:
                driver.get(f"{TIPPMIXPRO_BASE_URL}/fogadas/labdarugas")
                time.sleep(3)  # JS renderelés

                html = driver.page_source
                return self._parse_html(html)
            finally:
                driver.quit()

        except Exception:
            return []
