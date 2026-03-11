"""Telegram üzenet formázás - MarkdownV2 kompatibilis output.

Kezeli a 4096 karakteres üzenet limitet és a speciális karakterek escape-elését.
"""

import re

from src.analysis.predictor import MatchPrediction
from src.pipeline import PipelineResult
from src.ticket.generator import Ticket

# Telegram MarkdownV2 speciális karakterek
_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"


def escape_md(text: str) -> str:
    """MarkdownV2 speciális karakterek escape-elése."""
    return re.sub(r"([" + re.escape(_ESCAPE_CHARS) + r"])", r"\\\1", str(text))


def split_message(text: str, max_len: int = 4096) -> list[str]:
    """Üzenet darabolás 4096 karakter limiten belül.

    Sorok mentén vág, nem közepén.
    """
    if len(text) <= max_len:
        return [text]

    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            if current:
                parts.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line

    if current:
        parts.append(current)

    return parts


def _fmt_odds(value: float) -> str:
    return escape_md(f"{value:.2f}")


def _fmt_pct(value: float) -> str:
    return escape_md(f"{value:.0%}")


def _fmt_pct1(value: float) -> str:
    return escape_md(f"{value:.1%}")


def format_daily_report(result: PipelineResult) -> str:
    """Napi teljes elemzés formázás."""
    if not result.predictions:
        return escape_md("Nem találtunk mai meccseket az elemzett ligákban.")

    lines = [
        "*TIPMIX PREDICTION SYSTEM*",
        f"_{escape_md(result.timestamp.strftime('%Y.%m.%d %H:%M'))}_",
        "",
        f"Elemzett meccsek: *{result.total_matches}*",
        f"Oddsokkal párosítva: *{result.matched_with_odds}*",
        "",
    ]

    # Meccsek
    lines.append("*PREDIKCIÓK*")
    lines.append("")

    for pred in result.predictions:
        lines.append(_format_prediction_short(pred))
        lines.append("")

    # Value bets összefoglaló
    value_count = sum(len(p.value_bets) for p in result.predictions)
    stat_value_count = sum(len(p.stat_value_bets) for p in result.predictions)

    if value_count > 0 or stat_value_count > 0:
        lines.append("*VALUE BETEK*")
        for pred in result.predictions:
            home = escape_md(pred.home_team)
            away = escape_md(pred.away_team)
            for vb in pred.value_bets:
                market = escape_md(vb["market"])
                odds_s = _fmt_odds(vb["odds"])
                edge_s = _fmt_pct1(vb["edge"])
                lines.append(
                    f"⭐ {home} vs {away}: "
                    f"{market} @{odds_s} "
                    f"\\(edge: \\+{edge_s}\\)"
                )
            for svb in pred.stat_value_bets:
                market = escape_md(svb["market"])
                odds_s = _fmt_odds(svb["odds"])
                edge_s = _fmt_pct1(svb["edge"])
                lines.append(
                    f"📊 {home} vs {away}: "
                    f"{market} @{odds_s} "
                    f"\\(edge: \\+{edge_s}\\)"
                )
        lines.append("")

    # Szelvények
    if result.tickets:
        lines.append(_format_tickets_section(result.tickets))

    return "\n".join(lines)


def format_tickets(tickets: list[Ticket]) -> str:
    """Szelvényjavaslatok formázás."""
    if not tickets:
        return escape_md("Nincs szelvényjavaslat.")

    return _format_tickets_section(tickets)


def format_value_bets(result: PipelineResult) -> str:
    """Csak value betek formázás."""
    if not result.predictions:
        return escape_md("Nincs mai elemzés.")

    lines = ["*VALUE BET LEHETŐSÉGEK*", ""]

    has_value = False

    for pred in result.predictions:
        home = escape_md(pred.home_team)
        away = escape_md(pred.away_team)

        for vb in pred.value_bets:
            has_value = True
            market = escape_md(vb["market"])
            odds_s = _fmt_odds(vb["odds"])
            our_s = _fmt_pct(vb["our_prob"])
            impl_s = _fmt_pct(vb["implied_prob"])
            edge_s = _fmt_pct1(vb["edge"])
            lines.append(
                f"⭐ *{home} vs {away}*\n"
                f"   {market} @{odds_s}\n"
                f"   Saját: {our_s} "
                f"vs Implied: {impl_s}\n"
                f"   Edge: *\\+{edge_s}*"
            )
            lines.append("")

        for svb in pred.stat_value_bets:
            has_value = True
            market = escape_md(svb["market"])
            odds_s = _fmt_odds(svb["odds"])
            stat_s = _fmt_pct(svb["stat_prob"])
            impl_s = _fmt_pct(svb["implied_prob"])
            edge_s = _fmt_pct1(svb["edge"])
            lines.append(
                f"📊 *{home} vs {away}*\n"
                f"   {market} @{odds_s}\n"
                f"   Stat: {stat_s} "
                f"vs Implied: {impl_s}\n"
                f"   Edge: *\\+{edge_s}*"
            )
            lines.append("")

    if not has_value:
        lines.append(escape_md("Ma nem találtunk value bet lehetőséget."))

    return "\n".join(lines)


def format_league_report(result: PipelineResult, league_code: str) -> str:
    """Egy liga elemzése."""
    league_name = _get_league_name(league_code)

    league_preds = [
        p for p in result.predictions
        if p.competition and (
            p.competition == league_name
            or league_code.upper() in p.competition.upper()
        )
    ]

    if not league_preds:
        return escape_md(f"Nem találtunk mai meccseket a(z) {league_name} ligában.")

    lines = [f"*{escape_md(league_name)}*", ""]

    for pred in league_preds:
        lines.append(_format_prediction_short(pred))
        lines.append("")

    return "\n".join(lines)


def _format_prediction_short(pred: MatchPrediction) -> str:
    """Egy meccs rövid formázása."""
    home = escape_md(pred.home_team)
    away = escape_md(pred.away_team)

    # Tipp
    tip = escape_md(pred.recommended_bet)
    odds_str = ""
    if pred.recommended_odds > 0:
        odds_str = f" @{_fmt_odds(pred.recommended_odds)}"

    # 1X2
    h = _fmt_pct(pred.home_win_prob)
    d = _fmt_pct(pred.draw_prob)
    a = _fmt_pct(pred.away_win_prob)

    lines = [
        f"⚽ *{home} vs {away}*",
        f"   1X2: {h} / {d} / {a}",
        f"   O/U 2\\.5: {_fmt_pct(pred.over25_prob)} / {_fmt_pct(pred.under25_prob)}",
        f"   GG/NG: {_fmt_pct(pred.gg_prob)} / {_fmt_pct(pred.ng_prob)}",
        f"   Tipp: *{tip}*{odds_str}",
    ]

    # Value betek jelölése
    if pred.value_bets:
        lines.append(f"   ⭐ {len(pred.value_bets)} value bet")
    if pred.stat_value_bets:
        lines.append(f"   📊 {len(pred.stat_value_bets)} stat value bet")

    return "\n".join(lines)


def _format_tickets_section(tickets: list[Ticket]) -> str:
    """Szelvények szekció formázás."""
    lines = ["*SZELVÉNYJAVASLATOK*", ""]

    for ticket in tickets:
        if not ticket.entries:
            continue

        lines.append(f"🎫 *{escape_md(ticket.name)}*")
        stake_s = escape_md(f"{ticket.stake:,}")
        lines.append(f"   Tét: {stake_s} Ft")

        for i, entry in enumerate(ticket.entries, 1):
            home = escape_md(entry.home_team)
            away = escape_md(entry.away_team)
            bet = escape_md(entry.bet_type)
            odds_s = _fmt_odds(entry.odds) if entry.odds > 0 else "\\-"
            edge_str = ""
            if entry.edge > 0:
                edge_str = f" \\+{_fmt_pct1(entry.edge)}"

            lines.append(f"   {i}\\. {home} vs {away}")
            lines.append(f"      {bet} @{odds_s}{edge_str}")

        total_s = _fmt_odds(ticket.total_odds)
        win_s = escape_md(f"{ticket.potential_win:,.0f}")
        lines.append(f"   Össz odds: *{total_s}* → {win_s} Ft")
        lines.append("")

    return "\n".join(lines)


def _get_leagues() -> dict:
    """Lazy import to avoid circular dependency."""
    from src.config import SUPPORTED_LEAGUES
    return SUPPORTED_LEAGUES


def _get_league_name(code: str) -> str:
    """Liga név lookup."""
    leagues = _get_leagues()
    info = leagues.get(code.upper())
    return info["name"] if info else code
