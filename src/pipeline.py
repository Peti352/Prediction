"""Headless prediction pipeline - Rich/print nélküli feldolgozás.

A main.py és a Telegram bot közös alapja. Visszaadja a nyers adatokat
megjelenítés nélkül.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from src.analysis.predictor import MatchPrediction, PredictionEngine
from src.analysis.stats import (
    calculate_league_averages_from_matches,
    calculate_strength,
    calculate_team_stats,
)
from src.config import (
    ODDS_API_KEY,
    SUPPORTED_LEAGUES,
    fuzzy_match_teams,
)
from src.scrapers.odds_api import MatchEvent, MatchOdds, OddsAPIClient
from src.scrapers.sofascore import SofascoreClient
from src.ticket.generator import Ticket, TicketGenerator

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """A teljes pipeline eredménye."""
    predictions: list[MatchPrediction] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    total_matches: int = 0
    matched_with_odds: int = 0
    odds_requests_remaining: int | None = None
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


def _collect_sofascore_matches(
    sofascore: SofascoreClient,
    competition: str | None,
) -> list[dict]:
    """Sofascore meccsek lekérdezése."""
    logger.info("Sofascore meccsek lekérdezése...")
    matches = sofascore.get_scheduled_matches()

    if competition:
        matches = [m for m in matches if m["league_code"] == competition]

    logger.info("  %d meccs találva a Sofascore-on", len(matches))
    return matches


def _collect_odds(
    odds_client: OddsAPIClient,
    league_codes: list[str],
    skip_odds: bool,
) -> dict[str, list[tuple[str, str, str, MatchOdds]]]:
    """Oddsok lekérdezése ligánként."""
    if skip_odds:
        return {}

    if not ODDS_API_KEY or ODDS_API_KEY == "your_key_here":
        logger.warning("Nincs beállítva Odds API kulcs! Odds nélkül dolgozunk.")
        return {}

    logger.info("Odds API lekérdezés...")
    odds_by_league = {}

    for code in league_codes:
        league_info = SUPPORTED_LEAGUES.get(code)
        if not league_info:
            continue

        sport_key = league_info["odds_api_sport_key"]
        parsed = odds_client.get_parsed_odds_for_sport(sport_key)
        if parsed:
            odds_by_league[code] = parsed
            logger.info("  %s: %d meccs oddsokkal", code, len(parsed))

    return odds_by_league


def _try_tippmixpro_fallback() -> dict[str, list[tuple[str, str, MatchOdds]]]:
    """TippmixPro fallback odds lekérdezés."""
    logger.info("TippmixPro fallback próba...")
    try:
        from src.scrapers.tippmixpro import TippmixProScraper
        scraper = TippmixProScraper()
        matches = scraper.get_matches()

        if matches:
            logger.info("  %d meccs a TippmixPro-ról", len(matches))
            return {"MIXED": [(f"tp_{i}", h, a, o) for i, (h, a, o) in enumerate(matches)]}
    except Exception as e:
        logger.warning("TippmixPro fallback sikertelen: %s", e)

    return {}


def _fuzzy_match_events(
    sofascore_matches: list[dict],
    odds_by_league: dict[str, list[tuple[str, str, str, MatchOdds]]],
) -> list[MatchEvent]:
    """Sofascore események ↔ Odds API események összekapcsolása."""
    events = []

    for sf_match in sofascore_matches:
        league_code = sf_match["league_code"]
        odds_list = odds_by_league.get(league_code, [])

        matched_odds = MatchOdds()
        best_score = 0.0

        for _eid, odds_home, odds_away, odds_data in odds_list:
            home_score = fuzzy_match_teams(sf_match["home_team"], odds_home)
            away_score = fuzzy_match_teams(sf_match["away_team"], odds_away)
            combined = (home_score + away_score) / 2

            if combined > best_score and combined >= 0.65:
                best_score = combined
                matched_odds = odds_data

        # TippmixPro fallback
        if matched_odds.home_win == 0 and "MIXED" in odds_by_league:
            for _eid, tp_home, tp_away, tp_odds in odds_by_league["MIXED"]:
                home_score = fuzzy_match_teams(sf_match["home_team"], tp_home)
                away_score = fuzzy_match_teams(sf_match["away_team"], tp_away)
                combined = (home_score + away_score) / 2
                if combined > best_score and combined >= 0.60:
                    best_score = combined
                    matched_odds = tp_odds

        event = MatchEvent(
            home_team=sf_match["home_team"],
            away_team=sf_match["away_team"],
            home_team_id=sf_match["home_team_id"],
            away_team_id=sf_match["away_team_id"],
            kickoff=datetime.fromtimestamp(sf_match.get("start_timestamp", 0)),
            competition=sf_match.get("league_name", ""),
            league_code=league_code,
            sofascore_event_id=sf_match.get("event_id", 0),
            odds=matched_odds,
        )
        events.append(event)

    return events


def _analyze_and_predict(
    sofascore: SofascoreClient,
    events: list[MatchEvent],
) -> tuple[list[MatchPrediction], list[str]]:
    """Statisztikai elemzés és predikciók készítése.

    Returns:
        (predictions, errors)
    """
    engine = PredictionEngine()
    predictions = []
    errors = []
    league_matches_cache: dict[str, list[dict]] = {}

    for event in events:
        try:
            home_matches = sofascore.get_team_last_n_matches(
                event.home_team_id, n=10
            )
            away_matches = sofascore.get_team_last_n_matches(
                event.away_team_id, n=10
            )

            league_code = event.league_code
            if league_code not in league_matches_cache:
                league_matches_cache[league_code] = []
            league_matches_cache[league_code].extend(home_matches)
            league_matches_cache[league_code].extend(away_matches)

            league_avg = calculate_league_averages_from_matches(
                league_matches_cache[league_code]
            )
            league_avg.competition_code = league_code

            home_stats = calculate_team_stats(
                event.home_team, event.home_team_id, home_matches, league_code,
            )
            home_stats = calculate_strength(home_stats, league_avg)

            away_stats = calculate_team_stats(
                event.away_team, event.away_team_id, away_matches, league_code,
            )
            away_stats = calculate_strength(away_stats, league_avg)

            odds = event.odds if event.odds.home_win > 0 else None
            pred = engine.predict(
                home_stats=home_stats,
                away_stats=away_stats,
                league_avg=league_avg,
                odds=odds,
            )
            pred.competition = event.competition
            pred.match_odds = event.odds

            predictions.append(pred)

        except Exception as e:
            msg = f"{event.home_team} vs {event.away_team}: {e}"
            logger.warning("Hiba: %s", msg)
            errors.append(msg)

    return predictions, errors


def run_prediction_pipeline(
    competition: str | None = None,
    skip_odds: bool = False,
) -> PipelineResult:
    """A teljes predikciós pipeline futtatása.

    Args:
        competition: Liga kód szűrés (pl. "PL", "BL1"). None = minden liga.
        skip_odds: Ha True, odds lekérdezés kihagyása.

    Returns:
        PipelineResult az összes eredménnyel.
    """
    result = PipelineResult()

    sofascore = SofascoreClient()
    odds_client = OddsAPIClient()

    # 1) Meccsek gyűjtése
    sf_matches = _collect_sofascore_matches(sofascore, competition)
    if not sf_matches:
        logger.warning("Nem találtunk elemezendő meccseket.")
        return result

    # 2) Oddsok lekérdezése
    league_codes = list({m["league_code"] for m in sf_matches})
    odds_by_league = _collect_odds(odds_client, league_codes, skip_odds)

    # TippmixPro fallback
    if not odds_by_league and not skip_odds:
        tp_odds = _try_tippmixpro_fallback()
        if tp_odds:
            odds_by_league.update(tp_odds)

    result.odds_requests_remaining = odds_client.requests_remaining

    # 3) Fuzzy matching
    events = _fuzzy_match_events(sf_matches, odds_by_league)
    result.total_matches = len(events)
    result.matched_with_odds = sum(1 for e in events if e.odds.home_win > 0)
    logger.info(
        "%d meccs összesen, %d oddsokkal párosítva",
        result.total_matches, result.matched_with_odds,
    )

    # 4) Elemzés és predikció
    predictions, errors = _analyze_and_predict(sofascore, events)
    result.predictions = predictions
    result.errors = errors

    if not predictions:
        logger.warning("Nem sikerült predikciót készíteni.")
        return result

    # 5) Szelvény generálás
    generator = TicketGenerator()
    result.tickets = generator.generate_tickets(predictions)

    return result
