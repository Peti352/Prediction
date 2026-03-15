"""Rich CLI megjelenítés - szép terminál kimenet a predikciókhoz.

Bővítve: Kalibrált ensemble, Strength rating, H2H elemzés,
O/U összehasonlító tábla (stat% vs odds).
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from src.analysis.predictor import MatchPrediction
from src.ticket.generator import Ticket


console = Console()


def print_header():
    """Fejléc kiírása."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]TIPMIX PREDICTION SYSTEM v3[/bold cyan]\n"
            "[dim]Ensemble: Dixon-Coles + Strength + Forma | Kalibrált | 20 meccs mélyelemzés[/dim]",
            border_style="cyan",
        )
    )
    console.print()


def print_matches_table(predictions: list[MatchPrediction]):
    """Meccsek és predikciók táblázata (1X2 + O/U 1.5, 2.5, 3.5 + GG)."""
    if not predictions:
        console.print("[yellow]Nincs megjeleníthető meccs.[/yellow]")
        return

    table = Table(
        title="Meccsek és Predikciók (Ensemble)",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold white",
    )
    table.add_column("Meccs", style="bold", min_width=28)
    table.add_column("Liga", style="dim")
    table.add_column("1", justify="center", min_width=5)
    table.add_column("X", justify="center", min_width=5)
    table.add_column("2", justify="center", min_width=5)
    table.add_column("O/U 1.5", justify="center", min_width=9)
    table.add_column("O/U 2.5", justify="center", min_width=9)
    table.add_column("O/U 3.5", justify="center", min_width=9)
    table.add_column("GG/NG", justify="center", min_width=9)
    table.add_column("Tipp", justify="center", min_width=12)
    table.add_column("Q", justify="center", min_width=3)

    for pred in predictions:
        match_name = f"{pred.home_team}\nvs {pred.away_team}"

        h_color = _prob_color(pred.home_win_prob)
        d_color = _prob_color(pred.draw_prob)
        a_color = _prob_color(pred.away_win_prob)

        h_text = f"[{h_color}]{pred.home_win_prob:.0%}[/{h_color}]"
        d_text = f"[{d_color}]{pred.draw_prob:.0%}[/{d_color}]"
        a_text = f"[{a_color}]{pred.away_win_prob:.0%}[/{a_color}]"

        # O/U 1.5
        ou15_text = (
            f"[green]O:{pred.over15_prob:.0%}[/green]\n"
            f"[red]U:{pred.under15_prob:.0%}[/red]"
        )

        # O/U 2.5
        ou25_text = (
            f"[green]O:{pred.over25_prob:.0%}[/green]\n"
            f"[red]U:{pred.under25_prob:.0%}[/red]"
        )

        # O/U 3.5
        ou35_text = (
            f"[green]O:{pred.over35_prob:.0%}[/green]\n"
            f"[red]U:{pred.under35_prob:.0%}[/red]"
        )

        # GG/NG
        gg_text = (
            f"[green]GG:{pred.gg_prob:.0%}[/green]\n"
            f"[red]NG:{pred.ng_prob:.0%}[/red]"
        )

        # Tipp
        conf_color = _prob_color(pred.confidence)
        tip_text = (
            f"[bold {conf_color}]{pred.recommended_bet}[/bold {conf_color}]"
        )
        if pred.recommended_odds > 0:
            tip_text += f"\n[dim]@{pred.recommended_odds:.2f}[/dim]"

        # Minőség jelző
        q_text = _quality_indicator(pred.prediction_quality)

        table.add_row(
            match_name,
            pred.competition or "-",
            h_text,
            d_text,
            a_text,
            ou15_text,
            ou25_text,
            ou35_text,
            gg_text,
            tip_text,
            q_text,
        )

    console.print(table)
    console.print("[dim]Q = Predikció minőség (M=magas, K=közepes, A=alacsony)[/dim]")
    console.print()


def print_ou_comparison_table(predictions: list[MatchPrediction]):
    """O/U összehasonlító tábla: stat% vs odds összehasonlítás."""
    if not predictions:
        return

    table = Table(
        title="O/U Összehasonlítás (Stat% vs Odds)",
        box=box.ROUNDED,
        show_lines=True,
        title_style="bold yellow",
    )
    table.add_column("Meccs", style="bold", min_width=24)
    table.add_column("Stat", justify="center", header_style="bold green")
    table.add_column("Odds", justify="center")
    table.add_column("V", justify="center", min_width=2)
    table.add_column("Stat", justify="center", header_style="bold green")
    table.add_column("Odds", justify="center")
    table.add_column("V", justify="center", min_width=2)
    table.add_column("Stat", justify="center", header_style="bold green")
    table.add_column("Odds", justify="center")
    table.add_column("V", justify="center", min_width=2)

    console.print("[dim]                          O/U 1.5            O/U 2.5            O/U 3.5[/dim]")

    for pred in predictions:
        match_name = f"{pred.home_team}\nvs {pred.away_team}"

        odds = pred.match_odds

        # O/U 1.5
        stat15 = f"{pred.combined_stat_over15:.0%}" if pred.combined_stat_over15 > 0 else "-"
        odds15 = f"{odds.over_15:.2f}" if odds and odds.over_15 > 0 else "-"
        val15 = _value_marker(pred.combined_stat_over15, odds.over_15 if odds else 0)

        # O/U 2.5
        stat25 = f"{pred.combined_stat_over25:.0%}" if pred.combined_stat_over25 > 0 else "-"
        odds25 = f"{odds.over_25:.2f}" if odds and odds.over_25 > 0 else "-"
        val25 = _value_marker(pred.combined_stat_over25, odds.over_25 if odds else 0)

        # O/U 3.5
        stat35 = f"{pred.combined_stat_over35:.0%}" if pred.combined_stat_over35 > 0 else "-"
        odds35 = f"{odds.over_35:.2f}" if odds and odds.over_35 > 0 else "-"
        val35 = _value_marker(pred.combined_stat_over35, odds.over_35 if odds else 0)

        table.add_row(
            match_name,
            stat15, odds15, val15,
            stat25, odds25, val25,
            stat35, odds35, val35,
        )

    console.print(table)
    console.print()


def print_detailed_prediction(pred: MatchPrediction):
    """Egy meccs részletes predikciója - ensemble modell részletekkel."""
    title = f"{pred.home_team} vs {pred.away_team}"

    lines = []

    # Várható gólok
    lines.append(
        f"[bold]Várható gólok:[/bold] "
        f"{pred.expected_home_goals:.2f} - {pred.expected_away_goals:.2f}"
    )
    lines.append("")

    # Strength Ratingek
    if pred.home_stats and pred.away_stats:
        home_elo = pred.home_stats.strength_rating
        away_elo = pred.away_stats.strength_rating
        elo_diff = home_elo - away_elo
        elo_color = "green" if elo_diff > 50 else "red" if elo_diff < -50 else "yellow"
        lines.append(
            f"[bold]Strength Rating:[/bold] "
            f"{pred.home_team}: [bold]{home_elo:.0f}[/bold]  |  "
            f"{pred.away_team}: [bold]{away_elo:.0f}[/bold]  "
            f"([{elo_color}]{elo_diff:+.0f}[/{elo_color}])"
        )
        lines.append("")

    # Ensemble 1X2
    lines.append("[bold]1X2 Valószínűségek (Ensemble):[/bold]")
    lines.append(
        f"  Hazai (1): [{_prob_color(pred.home_win_prob)}]"
        f"{pred.home_win_prob:.1%}[/{_prob_color(pred.home_win_prob)}]"
    )
    lines.append(
        f"  Döntetlen (X): [{_prob_color(pred.draw_prob)}]"
        f"{pred.draw_prob:.1%}[/{_prob_color(pred.draw_prob)}]"
    )
    lines.append(
        f"  Vendég (2): [{_prob_color(pred.away_win_prob)}]"
        f"{pred.away_win_prob:.1%}[/{_prob_color(pred.away_win_prob)}]"
    )
    lines.append("")

    # Modell részletek
    lines.append("[bold]Modell részletek (1X2):[/bold]")
    lines.append(
        f"  Dixon-Coles: {pred.poisson_home:.0%} / {pred.poisson_draw:.0%} / {pred.poisson_away:.0%}"
    )
    lines.append(
        f"  STR:         {pred.elo_home:.0%} / {pred.elo_draw:.0%} / {pred.elo_away:.0%}"
    )
    lines.append(
        f"  Forma:       {pred.form_home:.0%} / {pred.form_draw:.0%} / {pred.form_away:.0%}"
    )

    agree_color = "green" if pred.model_agreement >= 0.7 else "yellow" if pred.model_agreement >= 0.5 else "red"
    lines.append(
        f"  Egyetértés:  [{agree_color}]{pred.model_agreement:.0%}[/{agree_color}]  "
        f"Minőség: [{agree_color}]{pred.prediction_quality}[/{agree_color}]"
    )
    lines.append("")

    # H2H részletek
    if pred.h2h_data and pred.h2h_data.matches_played > 0:
        h2h = pred.h2h_data
        lines.append(f"[bold]Head-to-Head ({h2h.matches_played} meccs):[/bold]")
        lines.append(
            f"  {pred.home_team} győzelmek: {h2h.home_wins}  "
            f"Döntetlen: {h2h.draws}  "
            f"{pred.away_team} győzelmek: {h2h.away_wins}"
        )
        lines.append(
            f"  H2H gólátlag: {h2h.avg_total_goals:.1f}  "
            f"Over 2.5: {h2h.over25_rate:.0%}  "
            f"GG: {h2h.gg_rate:.0%}"
        )
        if h2h.recent_trend:
            lines.append(
                f"  Utolsó meccsek: {_colorize_form(h2h.recent_trend)}"
            )
        lines.append("")

    # O/U analízis szekció
    lines.append("[bold]O/U Analízis (Dixon-Coles vs Stat vs Odds):[/bold]")
    odds = pred.match_odds

    for label, poisson_over, stat_over, odds_over, odds_under in [
        ("1.5", pred.over15_prob, pred.combined_stat_over15,
         odds.over_15 if odds else 0, odds.under_15 if odds else 0),
        ("2.5", pred.over25_prob, pred.combined_stat_over25,
         odds.over_25 if odds else 0, odds.under_25 if odds else 0),
        ("3.5", pred.over35_prob, pred.combined_stat_over35,
         odds.over_35 if odds else 0, odds.under_35 if odds else 0),
    ]:
        implied = f"{1/odds_over:.0%}" if odds_over > 1 else "-"
        odds_str = f"@{odds_over:.2f}" if odds_over > 0 else ""
        stat_str = f"{stat_over:.0%}" if stat_over > 0 else "-"

        lines.append(
            f"  O/U {label}: "
            f"DC={poisson_over:.0%}  "
            f"Stat={stat_str}  "
            f"Odds={odds_str} (implied={implied})"
        )

    lines.append("")

    # GG/NG
    lines.append(f"[bold]GG:[/bold] {pred.gg_prob:.1%}  |  "
                 f"[bold]NG:[/bold] {pred.ng_prob:.1%}")
    lines.append("")

    # Pontos eredmény top 5
    lines.append("[bold]Legvalószínűbb eredmények:[/bold]")
    for score, prob in pred.exact_scores[:5]:
        bar = "█" * int(prob * 100)
        lines.append(f"  {score:>5s}  {prob:.1%} {bar}")
    lines.append("")

    # Value bets (Ensemble)
    if pred.value_bets:
        lines.append("[bold green]Value Betek (Ensemble):[/bold green]")
        for vb in pred.value_bets:
            quality_str = ""
            q = vb.get("quality", 1.0)
            if q >= 0.95:
                quality_str = " [bold green][ERŐS][/bold green]"
            elif q >= 0.85:
                quality_str = " [yellow][KÖZEPES][/yellow]"
            lines.append(
                f"  [green]★[/green] {vb['market']}: "
                f"saját={vb['our_prob']:.1%}, "
                f"odds={vb['odds']:.2f} "
                f"(implied={vb['implied_prob']:.1%}), "
                f"edge=[bold green]+{vb['edge']:.1%}[/bold green]"
                f"{quality_str}"
            )

    # Stat Value bets
    if pred.stat_value_bets:
        lines.append("[bold yellow]Stat Value Betek:[/bold yellow]")
        for svb in pred.stat_value_bets:
            lines.append(
                f"  [yellow]★[/yellow] {svb['market']}: "
                f"stat={svb['stat_prob']:.1%}, "
                f"odds={svb['odds']:.2f} "
                f"(implied={svb['implied_prob']:.1%}), "
                f"edge=[bold yellow]+{svb['edge']:.1%}[/bold yellow]"
            )

    # Forma - bővített
    if pred.home_stats:
        hs = pred.home_stats
        lines.append("")
        lines.append(f"[bold]{pred.home_team}:[/bold]")
        lines.append(
            f"  Forma (20): {_colorize_form(hs.form_string)}  "
            f"Utolsó 5: {_colorize_form(hs.recent_form_5)}"
        )
        lines.append(
            f"  STR: {hs.strength_rating:.0f}  "
            f"Pos: {hs.league_position}  "
            f"Gól avg: {hs.avg_goals_scored:.1f} (súlyozott: {hs.weighted_avg_goals_scored:.1f})"
        )
        lines.append(
            f"  O/U: 1.5={hs.over15_rate:.0%}  "
            f"2.5={hs.over25_rate:.0%}  "
            f"3.5={hs.over35_rate:.0%}  "
            f"GG={hs.gg_rate:.0%}  "
            f"CS={hs.clean_sheet_rate:.0%}"
        )
        trend_str = f"[green]+{hs.goal_diff_trend:.1f}[/green]" if hs.goal_diff_trend > 0 else (
            f"[red]{hs.goal_diff_trend:.1f}[/red]" if hs.goal_diff_trend < 0 else "0.0"
        )
        lines.append(
            f"  Trend: {trend_str}  "
            f"Konzisztencia: {hs.scoring_consistency:.2f}"
        )

    if pred.away_stats:
        as_ = pred.away_stats
        lines.append(f"[bold]{pred.away_team}:[/bold]")
        lines.append(
            f"  Forma (20): {_colorize_form(as_.form_string)}  "
            f"Utolsó 5: {_colorize_form(as_.recent_form_5)}"
        )
        lines.append(
            f"  STR: {as_.strength_rating:.0f}  "
            f"Pos: {as_.league_position}  "
            f"Gól avg: {as_.avg_goals_scored:.1f} (súlyozott: {as_.weighted_avg_goals_scored:.1f})"
        )
        lines.append(
            f"  O/U: 1.5={as_.over15_rate:.0%}  "
            f"2.5={as_.over25_rate:.0%}  "
            f"3.5={as_.over35_rate:.0%}  "
            f"GG={as_.gg_rate:.0%}  "
            f"CS={as_.clean_sheet_rate:.0%}"
        )
        trend_str = f"[green]+{as_.goal_diff_trend:.1f}[/green]" if as_.goal_diff_trend > 0 else (
            f"[red]{as_.goal_diff_trend:.1f}[/red]" if as_.goal_diff_trend < 0 else "0.0"
        )
        lines.append(
            f"  Trend: {trend_str}  "
            f"Konzisztencia: {as_.scoring_consistency:.2f}"
        )

    console.print(Panel(
        "\n".join(lines),
        title=f"[bold]{title}[/bold]",
        border_style="blue",
    ))
    console.print()


def print_tickets(tickets: list[Ticket]):
    """Szelvényjavaslatok megjelenítése."""
    if not tickets:
        console.print("[yellow]Nincs szelvényjavaslat.[/yellow]")
        return

    console.print(Panel.fit(
        "[bold yellow]SZELVÉNYJAVASLATOK[/bold yellow]",
        border_style="yellow",
    ))
    console.print()

    for ticket in tickets:
        _print_single_ticket(ticket)


def _print_single_ticket(ticket: Ticket):
    """Egy szelvény megjelenítése."""
    if not ticket.entries:
        return

    table = Table(
        title=f"{ticket.name}",
        box=box.DOUBLE_EDGE,
        show_lines=True,
        title_style="bold yellow",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Meccs", min_width=28)
    table.add_column("Tipp", justify="center", min_width=12)
    table.add_column("Odds", justify="center", min_width=7)
    table.add_column("Valósz.", justify="center", min_width=8)
    table.add_column("Edge", justify="center", min_width=7)

    for i, entry in enumerate(ticket.entries, 1):
        match_name = f"{entry.home_team} vs {entry.away_team}"
        conf_color = _prob_color(entry.confidence)

        odds_text = f"{entry.odds:.2f}" if entry.odds > 0 else "-"
        prob_text = f"[{conf_color}]{entry.probability:.0%}[/{conf_color}]"

        edge_text = ""
        if entry.edge > 0:
            edge_text = f"[bold green]+{entry.edge:.1%}[/bold green]"
        elif entry.is_value_bet:
            edge_text = "[green]VALUE[/green]"

        table.add_row(
            str(i),
            match_name,
            f"[bold]{entry.bet_type}[/bold]",
            odds_text,
            prob_text,
            edge_text,
        )

    console.print(table)

    summary = (
        f"  Tét: [bold]{ticket.stake:,} Ft[/bold]  |  "
        f"Összesített odds: [bold]{ticket.total_odds:.2f}[/bold]  |  "
        f"Lehetséges nyeremény: [bold green]{ticket.potential_win:,.0f} Ft[/bold green]  |  "
        f"Szelvény valószínűség: {ticket.ticket_probability:.1%}"
    )
    console.print(summary)
    console.print()


def print_summary(predictions: list[MatchPrediction], tickets: list[Ticket]):
    """Összefoglaló - bővített."""
    console.print(Panel.fit(
        "[bold]ÖSSZEFOGLALÓ[/bold]",
        border_style="white",
    ))

    total_matches = len(predictions)
    value_bets = sum(len(p.value_bets) for p in predictions)
    stat_value_bets = sum(len(p.stat_value_bets) for p in predictions)
    high_conf = sum(1 for p in predictions if p.confidence >= 0.65)
    high_quality = sum(1 for p in predictions if p.prediction_quality == "magas")
    avg_agreement = (
        sum(p.model_agreement for p in predictions) / total_matches
        if total_matches > 0 else 0
    )

    console.print(f"  Elemzett meccsek: [bold]{total_matches}[/bold]")
    console.print(f"  Value bet lehetőségek (Ensemble): [bold green]{value_bets}[/bold green]")
    console.print(f"  Stat value bet lehetőségek: [bold yellow]{stat_value_bets}[/bold yellow]")
    console.print(f"  Magas konfidenciájú tippek: [bold]{high_conf}[/bold]")
    console.print(f"  Magas minőségű predikciók: [bold green]{high_quality}[/bold green]")
    console.print(f"  Átlagos modell egyetértés: [bold]{avg_agreement:.0%}[/bold]")
    console.print(f"  Generált szelvények: [bold]{len(tickets)}[/bold]")

    if tickets:
        best = max(tickets, key=lambda t: t.ticket_probability)
        console.print(
            f"\n  Legjobb szelvény: [bold yellow]{best.name}[/bold yellow] "
            f"({best.ticket_probability:.1%} valószínűség, "
            f"{best.potential_win:,.0f} Ft potenciális nyeremény)"
        )

    console.print()


def print_odds_api_status(remaining: int | None):
    """Odds API request számláló kiírása."""
    if remaining is not None:
        color = "green" if remaining > 100 else "yellow" if remaining > 20 else "red"
        console.print(f"  Odds API hátralévő kérések: [{color}]{remaining}[/{color}]")


def print_error(message: str):
    console.print(f"[bold red]HIBA:[/bold red] {message}")


def print_warning(message: str):
    console.print(f"[yellow]FIGYELEM:[/yellow] {message}")


def print_info(message: str):
    console.print(f"[dim]{message}[/dim]")


# === Segédfüggvények ===

def _prob_color(prob: float) -> str:
    """Valószínűség színkódolás."""
    if prob >= 0.65:
        return "green"
    elif prob >= 0.45:
        return "yellow"
    else:
        return "red"


def _colorize_form(form: str) -> str:
    """Forma string színezése."""
    colored = ""
    for c in form:
        if c == "W":
            colored += "[green]W[/green]"
        elif c == "D":
            colored += "[yellow]D[/yellow]"
        elif c == "L":
            colored += "[red]L[/red]"
        else:
            colored += c
    return colored


def _value_marker(stat_prob: float, market_odds: float) -> str:
    """Value marker ha value bet (stat% > implied prob + 5%)."""
    if market_odds <= 1.0 or stat_prob <= 0:
        return ""
    implied = 1.0 / market_odds
    if stat_prob - implied > 0.05:
        return "[bold green]★[/bold green]"
    return ""


def _quality_indicator(quality: str) -> str:
    """Predikció minőség jelző."""
    if quality == "magas":
        return "[bold green]M[/bold green]"
    elif quality == "közepes":
        return "[yellow]K[/yellow]"
    else:
        return "[red]A[/red]"
