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

from src.config import SUPPORTED_LEAGUES
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
from src.pipeline import run_prediction_pipeline


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

    # Pipeline futtatása
    console.rule("[bold]1. Meccsek gyűjtése (Sofascore)[/bold]")
    print_info("Pipeline indítása...")

    result = run_prediction_pipeline(
        competition=args.competition,
        skip_odds=args.no_odds,
    )

    if not result.predictions:
        print_warning("Nem találtunk elemezendő meccseket vagy nem sikerült predikciót készíteni.")
        console.print(
            "[dim]Tipp: Próbáld egy konkrét ligával: "
            "python src/main.py -c PL[/dim]"
        )
        return

    # Hibák kiírása
    for error in result.errors:
        print_warning(f"  Hiba: {error}")

    # Odds API státusz
    print_odds_api_status(result.odds_requests_remaining)

    print_info(
        f"  {result.total_matches} meccs összesen, "
        f"{result.matched_with_odds} oddsokkal párosítva"
    )
    console.print()

    # Eredmények megjelenítése
    console.rule("[bold]5. Predikciók[/bold]")
    print_matches_table(result.predictions)
    print_ou_comparison_table(result.predictions)

    if args.detailed:
        for pred in result.predictions:
            print_detailed_prediction(pred)

    # Szelvény javaslatok
    console.rule("[bold]6. Szelvényjavaslatok[/bold]")
    print_tickets(result.tickets)

    # Összefoglaló
    console.rule("[bold]7. Összefoglaló[/bold]")
    print_summary(result.predictions, result.tickets)


if __name__ == "__main__":
    main()
