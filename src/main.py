"""TipMix Prediction System v2 - fő belépési pont.

Workflow:
1. Sofascore: mai meccsek lekérdezése (szűrés támogatott ligákra)
2. Odds API: oddsok lekérdezése ligánként
3. Fuzzy matching: Sofascore események ↔ Odds API események összekapcsolása
4. Sofascore: mindkét csapat utolsó 10 meccsének lekérdezése
5. Stats: O/U 1.5, 2.5, 3.5 %-ok számítása
6. Poisson predikció + stat O/U összehasonlítás oddsokkal
7. Value bet azonosítás
8. Display: O/U összehasonlító tábla + szelvényjavaslatok

Futtatás:
    python src/main.py
    python src/main.py -c PL
    python src/main.py -c PL --detailed
"""

import argparse
import sys
from pathlib import Path

# Projekt root hozzáadása a path-hoz
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.progress import Progress, SpinnerColumn, TextColumn

from src.analysis.predictor import MatchPrediction, PredictionEngine
from src.analysis.stats import (
    LeagueAverages,
    calculate_league_averages_from_matches,
    calculate_strength,
    calculate_team_stats,
)
from src.config import (
    ODDS_API_KEY,
    SUPPORTED_LEAGUES,
    find_best_match,
    fuzzy_match_teams,
)
from src.display.cli import (
    console,
    print_detailed_prediction,
    print_error,
    print_header,
    print_info,
    print_matches_table,
    print_odds_api_status,
    print_ou_comparison_table,
    print_summary,
    print_tickets,
    print_warning,
)
from src.scrapers.odds_api import MatchEvent, MatchOdds, OddsAPIClient
from src.scrapers.sofascore import SofascoreClient
from src.scrapers.tippmixpro import TippmixProScraper
from src.ticket.generator import TicketGenerator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TipMix Prediction System v2 - Focimeccs előrejelzés",
    )
    parser.add_argument(
        "-c", "--competition",
        type=str,
        default=None,
        help=f"Liga kód szűrés (pl. PL, BL1, SA). Elérhető: {', '.join(SUPPORTED_LEAGUES.keys())}",
    )
    parser.add_argument(
        "-d", "--detailed",
        action="store_true",
        help="Részletes predikció minden meccshez",
    )
    parser.add_argument(
        "--no-odds",
        action="store_true",
        help="Odds lekérdezés kihagyása",
    )
    parser.add_argument(
        "--list-competitions",
        action="store_true",
        help="Elérhető ligák listázása",
    )
    return parser.parse_args()


def list_competitions():
    """Elérhető ligák listázása."""
    from rich.table import Table

    table = Table(title="Elérhető ligák")
    table.add_column("Kód", style="bold cyan")
    table.add_column("Liga neve")
    table.add_column("Sofascore ID", style="dim")
    table.add_column("Odds API key", style="dim")

    for code, info in SUPPORTED_LEAGUES.items():
        table.add_row(
            code,
            info["name"],
            str(info["sofascore_tournament_id"]),
            info["odds_api_sport_key"],
        )

    console.print(table)


def collect_sofascore_matches(
    sofascore: SofascoreClient,
    competition: str | None,
) -> list[dict]:
    """Sofascore meccsek lekérdezése."""
    print_info("Sofascore meccsek lekérdezése...")
    matches = sofascore.get_scheduled_matches()

    if competition:
        matches = [m for m in matches if m["league_code"] == competition]

    if matches:
        print_info(f"  {len(matches)} meccs találva a Sofascore-on")
    else:
        print_warning("Nem találtunk meccseket a Sofascore-on.")

    return matches


def collect_odds(
    odds_client: OddsAPIClient,
    league_codes: list[str],
    skip_odds: bool,
) -> dict[str, list[tuple[str, str, str, MatchOdds]]]:
    """Oddsok lekérdezése ligánként.

    Returns:
        {league_code: [(event_id, home, away, MatchOdds), ...]}
    """
    if skip_odds:
        return {}

    if not ODDS_API_KEY or ODDS_API_KEY == "your_key_here":
        print_warning(
            "Nincs beállítva Odds API kulcs! Odds nélkül dolgozunk.\n"
            "  Regisztrálj: https://the-odds-api.com/\n"
            "  ODDS_API_KEY=your_key a .env fájlba"
        )
        return {}

    print_info("Odds API lekérdezés...")
    odds_by_league = {}

    for code in league_codes:
        league_info = SUPPORTED_LEAGUES.get(code)
        if not league_info:
            continue

        sport_key = league_info["odds_api_sport_key"]
        parsed = odds_client.get_parsed_odds_for_sport(sport_key)
        if parsed:
            odds_by_league[code] = parsed
            print_info(f"  {code}: {len(parsed)} meccs oddsokkal")

    return odds_by_league


def try_tippmixpro_fallback() -> dict[str, list[tuple[str, str, MatchOdds]]]:
    """TippmixPro fallback odds lekérdezés."""
    print_info("TippmixPro fallback próba...")
    scraper = TippmixProScraper()
    matches = scraper.get_matches()

    if matches:
        print_info(f"  {len(matches)} meccs a TippmixPro-ról")
        # Nem tudjuk liga kódra szétválasztani, mindent "MIXED"-ként kezelünk
        return {"MIXED": [(f"tp_{i}", h, a, o) for i, (h, a, o) in enumerate(matches)]}

    return {}


def fuzzy_match_events(
    sofascore_matches: list[dict],
    odds_by_league: dict[str, list[tuple[str, str, str, MatchOdds]]],
) -> list[MatchEvent]:
    """Sofascore események ↔ Odds API események összekapcsolása fuzzy matching-gel.

    Returns:
        MatchEvent lista (Sofascore adatok + oddsok).
    """
    events = []

    for sf_match in sofascore_matches:
        league_code = sf_match["league_code"]
        odds_list = odds_by_league.get(league_code, [])

        # Megkeressük a legjobb odds párosítást
        matched_odds = MatchOdds()
        best_score = 0.0

        for _eid, odds_home, odds_away, odds_data in odds_list:
            # Mindkét csapatnevet hasonlítjuk
            home_score = fuzzy_match_teams(sf_match["home_team"], odds_home)
            away_score = fuzzy_match_teams(sf_match["away_team"], odds_away)
            combined = (home_score + away_score) / 2

            if combined > best_score and combined >= 0.65:
                best_score = combined
                matched_odds = odds_data

        # TippmixPro fallback: ha nincs odds, próbáljuk a MIXED-et
        if matched_odds.home_win == 0 and "MIXED" in odds_by_league:
            for _eid, tp_home, tp_away, tp_odds in odds_by_league["MIXED"]:
                home_score = fuzzy_match_teams(sf_match["home_team"], tp_home)
                away_score = fuzzy_match_teams(sf_match["away_team"], tp_away)
                combined = (home_score + away_score) / 2
                if combined > best_score and combined >= 0.60:
                    best_score = combined
                    matched_odds = tp_odds

        from datetime import datetime

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


def analyze_and_predict(
    sofascore: SofascoreClient,
    events: list[MatchEvent],
) -> list[MatchPrediction]:
    """Statisztikai elemzés és predikciók készítése."""
    engine = PredictionEngine()
    predictions = []

    # Liga átlagok cache
    league_matches_cache: dict[str, list[dict]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Meccsek elemzése...", total=len(events))

        for event in events:
            progress.update(
                task,
                description=f"Elemzés: {event.home_team} vs {event.away_team}",
            )

            try:
                # Hazai csapat utolsó 10 meccs
                home_matches = sofascore.get_team_last_n_matches(
                    event.home_team_id, n=10
                )

                # Vendég csapat utolsó 10 meccs
                away_matches = sofascore.get_team_last_n_matches(
                    event.away_team_id, n=10
                )

                # Liga átlag számítás az összegyűjtött meccsekből
                league_code = event.league_code
                if league_code not in league_matches_cache:
                    league_matches_cache[league_code] = []
                league_matches_cache[league_code].extend(home_matches)
                league_matches_cache[league_code].extend(away_matches)

                league_avg = calculate_league_averages_from_matches(
                    league_matches_cache[league_code]
                )
                league_avg.competition_code = league_code

                # Csapat statisztikák
                home_stats = calculate_team_stats(
                    event.home_team,
                    event.home_team_id,
                    home_matches,
                    league_code,
                )
                home_stats = calculate_strength(home_stats, league_avg)

                away_stats = calculate_team_stats(
                    event.away_team,
                    event.away_team_id,
                    away_matches,
                    league_code,
                )
                away_stats = calculate_strength(away_stats, league_avg)

                # Predikció
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
                print_warning(
                    f"  Hiba: {event.home_team} vs {event.away_team}: {e}"
                )

            progress.advance(task)

    return predictions


def main():
    args = parse_args()
    print_header()

    # Ligák listázása
    if args.list_competitions:
        list_competitions()
        return

    # Liga szűrés validálás
    if args.competition and args.competition not in SUPPORTED_LEAGUES:
        print_error(
            f"Ismeretlen liga kód: {args.competition}\n"
            f"Elérhető: {', '.join(SUPPORTED_LEAGUES.keys())}"
        )
        sys.exit(1)

    sofascore = SofascoreClient()
    odds_client = OddsAPIClient()

    # 1) Meccsek gyűjtése Sofascore-ról
    console.rule("[bold]1. Meccsek gyűjtése (Sofascore)[/bold]")
    sf_matches = collect_sofascore_matches(sofascore, args.competition)

    if not sf_matches:
        print_warning("Nem találtunk elemezendő meccseket.")
        console.print(
            "[dim]Tipp: Próbáld egy konkrét ligával: "
            "python src/main.py -c PL[/dim]"
        )
        return

    # 2) Oddsok lekérdezése
    console.rule("[bold]2. Oddsok lekérdezése[/bold]")
    league_codes = list({m["league_code"] for m in sf_matches})
    odds_by_league = collect_odds(odds_client, league_codes, args.no_odds)

    # TippmixPro fallback ha nincs odds
    if not odds_by_league and not args.no_odds:
        tp_odds = try_tippmixpro_fallback()
        if tp_odds:
            odds_by_league.update(tp_odds)

    # Odds API státusz kiírás
    print_odds_api_status(odds_client.requests_remaining)

    # 3) Fuzzy matching: Sofascore ↔ Odds API
    console.rule("[bold]3. Adatok összefésülése[/bold]")
    events = fuzzy_match_events(sf_matches, odds_by_league)
    matched_with_odds = sum(1 for e in events if e.odds.home_win > 0)
    print_info(f"  {len(events)} meccs összesen, {matched_with_odds} oddsokkal párosítva")
    console.print()

    # 4) Elemzés és predikció
    console.rule("[bold]4. Statisztikai elemzés és predikció[/bold]")
    predictions = analyze_and_predict(sofascore, events)

    if not predictions:
        print_warning("Nem sikerült predikciót készíteni.")
        return

    console.print()

    # 5) Eredmények megjelenítése
    console.rule("[bold]5. Predikciók[/bold]")
    print_matches_table(predictions)

    # O/U összehasonlító tábla
    print_ou_comparison_table(predictions)

    if args.detailed:
        for pred in predictions:
            print_detailed_prediction(pred)

    # 6) Szelvény generálás
    console.rule("[bold]6. Szelvényjavaslatok[/bold]")
    generator = TicketGenerator()
    tickets = generator.generate_tickets(predictions)
    print_tickets(tickets)

    # 7) Összefoglaló
    console.rule("[bold]7. Összefoglaló[/bold]")
    print_summary(predictions, tickets)


if __name__ == "__main__":
    main()
