"""Statisztikai elemzés modul - bővített verzió.

Csapatforma, gólátlagok, hazai/vendég erő, O/U ráták (1.5, 2.5, 3.5).
Bővített: ELO rating, időszúlyozott statisztikák, mélyebb H2H elemzés.
Sofascore adatformátumra optimalizálva.
"""

import math
from dataclasses import dataclass, field

from src.config import (
    STRENGTH_DEFAULT_RATING,
    STRENGTH_HOME_ADVANTAGE,
    STRENGTH_K_FACTOR,
    TIME_DECAY_FACTOR,
    H2H_RECENCY_DECAY,
)


@dataclass
class TeamStats:
    """Egy csapat összesített statisztikái."""
    team_name: str = ""
    team_id: int | None = None
    competition_code: str = ""

    # Forma (utolsó N meccs)
    matches_played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    form_string: str = ""  # Pl. "WWDLW"

    # Gólok
    goals_scored: int = 0
    goals_conceded: int = 0
    avg_goals_scored: float = 0.0
    avg_goals_conceded: float = 0.0

    # Időszúlyozott gólátlagok (újabb meccsek nagyobb súllyal)
    weighted_avg_goals_scored: float = 0.0
    weighted_avg_goals_conceded: float = 0.0

    # Hazai/Vendég bontás
    home_matches: int = 0
    home_wins: int = 0
    home_draws: int = 0
    home_losses: int = 0
    home_goals_scored: int = 0
    home_goals_conceded: int = 0
    avg_home_goals_scored: float = 0.0
    avg_home_goals_conceded: float = 0.0

    away_matches: int = 0
    away_wins: int = 0
    away_draws: int = 0
    away_losses: int = 0
    away_goals_scored: int = 0
    away_goals_conceded: int = 0
    avg_away_goals_scored: float = 0.0
    avg_away_goals_conceded: float = 0.0

    # Tabella
    league_position: int = 0
    league_points: int = 0

    # Számított erősségek
    attack_strength: float = 1.0
    defense_strength: float = 1.0
    home_attack_strength: float = 1.0
    home_defense_strength: float = 1.0
    away_attack_strength: float = 1.0
    away_defense_strength: float = 1.0

    # Over/Under és GG statisztikák
    over15_rate: float = 0.0      # Meccsek %-a ahol 1.5+ gól volt
    over25_rate: float = 0.0      # Meccsek %-a ahol 2.5+ gól volt
    over35_rate: float = 0.0      # Meccsek %-a ahol 3.5+ gól volt
    gg_rate: float = 0.0          # Meccsek %-a ahol mindkét csapat szerzett gólt
    clean_sheet_rate: float = 0.0 # Kapott gól nélküli meccsek %-a

    # Meccs gól történet (statisztikai O/U-hoz)
    match_goals_history: list[int] = field(default_factory=list)

    # ELO rating
    strength_rating: float = STRENGTH_DEFAULT_RATING

    # Haladó statisztikák
    scoring_consistency: float = 0.0   # Gólszerzés konzisztenciája (alacsonyabb szórás = jobb)
    conceding_consistency: float = 0.0 # Gólkapás konzisztenciája
    first_half_goals_ratio: float = 0.0  # Első félidei gólok aránya
    comeback_rate: float = 0.0         # Hátrányból visszajövés %-a
    win_to_nil_rate: float = 0.0       # Kapott gól nélküli győzelmek %-a

    # Utolsó 5 meccs formája (rövidtávú trend)
    recent_form_5: str = ""
    recent_form_points_5: float = 0.0  # Pont/meccs az utolsó 5-ből

    # Gólkülönbség trend
    goal_diff_trend: float = 0.0  # Pozitív = javuló, negatív = romló


@dataclass
class HeadToHead:
    """Két csapat egymás elleni statisztikái - bővített."""
    matches_played: int = 0
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    avg_total_goals: float = 0.0
    last_results: list[str] = field(default_factory=list)

    # Bővített H2H
    avg_home_goals: float = 0.0    # A hazai csapat átlagos góljai H2H-ban
    avg_away_goals: float = 0.0    # A vendég csapat átlagos góljai H2H-ban
    over25_rate: float = 0.0       # H2H-ban hány % over 2.5
    gg_rate: float = 0.0           # H2H-ban hány % mindkét csapat szerzett gólt
    home_win_rate: float = 0.0     # Hazai győzelmi arány
    draw_rate: float = 0.0         # Döntetlen arány
    away_win_rate: float = 0.0     # Vendég győzelmi arány
    recent_trend: str = ""         # Utolsó 5 H2H eredmény
    dominance_score: float = 0.0   # -1 (vendég dominál) - +1 (hazai dominál)


@dataclass
class LeagueAverages:
    """Liga átlagok a Poisson modellhez."""
    competition_code: str = ""
    avg_home_goals: float = 1.5
    avg_away_goals: float = 1.2
    avg_total_goals: float = 2.7
    total_matches: int = 0


# === ELO Rating Rendszer ===

def strength_expected_score(rating_a: float, rating_b: float, home_advantage: float = STRENGTH_HOME_ADVANTAGE) -> float:
    """Várható eredmény ELO alapján (0.0 - 1.0)."""
    dr = rating_a - rating_b + home_advantage
    return 1.0 / (10.0 ** (-dr / 400.0) + 1.0)


def strength_goal_diff_multiplier(goal_diff: int) -> float:
    """Gólkülönbség szorzó az ELO frissítéshez."""
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    elif gd == 2:
        return 1.5
    elif gd == 3:
        return 1.75
    else:
        return 1.75 + (gd - 3) / 8.0


def strength_update(
    rating: float,
    expected: float,
    actual: float,
    goal_diff: int,
    k_factor: float = STRENGTH_K_FACTOR,
) -> float:
    """ELO rating frissítés egy meccs alapján."""
    g = strength_goal_diff_multiplier(goal_diff)
    return rating + k_factor * g * (actual - expected)


def strength_to_probabilities(
    home_elo: float,
    away_elo: float,
    home_advantage: float = STRENGTH_HOME_ADVANTAGE,
) -> tuple[float, float, float]:
    """ELO ratingekből 1X2 valószínűségek.

    Returns:
        (home_win_prob, draw_prob, away_win_prob)
    """
    we_home = strength_expected_score(home_elo, away_elo, home_advantage)
    we_away = 1.0 - we_home

    # Döntetlen valószínűség becslése az ELO különbségből
    elo_diff = abs(home_elo + home_advantage - away_elo)
    # Kisebb különbség = nagyobb döntetlen esély (empirikus formula)
    draw_base = 0.28 * math.exp(-elo_diff / 600.0)
    draw_prob = max(0.10, min(0.35, draw_base))

    home_win = we_home * (1.0 - draw_prob)
    away_win = we_away * (1.0 - draw_prob)

    # Normalizálás
    total = home_win + draw_prob + away_win
    return home_win / total, draw_prob / total, away_win / total


def calculate_team_strength(
    team_id: int | None,
    team_name: str,
    matches: list[dict],
    initial_rating: float = STRENGTH_DEFAULT_RATING,
) -> float:
    """Csapat ELO ratingjének kiszámítása a meccs történetből.

    A legrégebbi meccstől halad az újabbak felé.
    """
    rating = initial_rating

    # Fordított sorrend (legrégebbitől az újabbig)
    sorted_matches = sorted(
        matches,
        key=lambda m: m.get("start_timestamp", 0),
    )

    for match in sorted_matches:
        home_team_id = match.get("home_team_id", match.get("homeTeam", {}).get("id"))
        away_team_id = match.get("away_team_id", match.get("awayTeam", {}).get("id"))
        home_team_name = match.get("home_team", match.get("homeTeam", {}).get("name", ""))

        home_goals = match.get("home_goals")
        away_goals = match.get("away_goals")
        if home_goals is None or away_goals is None:
            continue

        hg, ag = int(home_goals), int(away_goals)
        is_home = home_team_id == team_id or home_team_name == team_name
        is_away = not is_home and (away_team_id == team_id)

        if not is_home and not is_away:
            # Név alapú ellenőrzés
            away_team_name = match.get("away_team", match.get("awayTeam", {}).get("name", ""))
            if away_team_name == team_name:
                is_away = True
            else:
                continue

        if is_home:
            scored, conceded = hg, ag
            advantage = STRENGTH_HOME_ADVANTAGE
        else:
            scored, conceded = ag, hg
            advantage = -STRENGTH_HOME_ADVANTAGE

        # Eredmény (1=win, 0.5=draw, 0=loss)
        if scored > conceded:
            actual = 1.0
        elif scored == conceded:
            actual = 0.5
        else:
            actual = 0.0

        goal_diff = scored - conceded
        # Az ellenfél ratingjét nem tudjuk pontosan, átlagot használunk
        opponent_rating = initial_rating
        expected = strength_expected_score(rating, opponent_rating, advantage)
        rating = strength_update(rating, expected, actual, abs(goal_diff))

    return rating


# === Csapat Statisztikák ===

def calculate_team_stats(
    team_name: str,
    team_id: int | None,
    matches: list[dict],
    competition_code: str = "",
) -> TeamStats:
    """Csapat statisztikáit számítja ki a Sofascore meccs-történetből.

    Bővített: 20 meccs, időszúlyozás, ELO, trendek.

    Args:
        team_name: A csapat neve
        team_id: Sofascore csapat ID
        matches: Sofascore meccs lista (get_team_last_n_matches formátum)
        competition_code: Liga kód
    """
    stats = TeamStats(
        team_name=team_name,
        team_id=team_id,
        competition_code=competition_code,
    )

    if not matches:
        return stats

    form_chars = []
    over15_count = 0
    over25_count = 0
    over35_count = 0
    gg_count = 0
    clean_sheets = 0
    win_to_nil_count = 0

    # Időszúlyozáshoz
    scored_list = []
    conceded_list = []
    goal_diffs = []

    # Félidei gólok
    first_half_goals_total = 0
    total_goals_for_ht = 0

    # Comeback tracking
    behind_count = 0
    comeback_count = 0

    for i, match in enumerate(matches):
        # Sofascore formátum: home_goals / away_goals közvetlenül
        home_goals = match.get("home_goals")
        away_goals = match.get("away_goals")

        if home_goals is None or away_goals is None:
            # Fallback: football-data.org formátum
            score = match.get("score", {}).get("fullTime", {})
            home_goals = score.get("home")
            away_goals = score.get("away")

        if home_goals is None or away_goals is None:
            continue

        home_goals = int(home_goals)
        away_goals = int(away_goals)
        total_goals = home_goals + away_goals

        # Melyik csapat vagyunk?
        home_team_id = match.get("home_team_id", match.get("homeTeam", {}).get("id"))
        away_team_id = match.get("away_team_id", match.get("awayTeam", {}).get("id"))
        home_team_name = match.get("home_team", match.get("homeTeam", {}).get("name", ""))
        away_team_name = match.get("away_team", match.get("awayTeam", {}).get("name", ""))

        is_home = home_team_id == team_id or home_team_name == team_name
        is_away = away_team_id == team_id or away_team_name == team_name

        if not is_home and not is_away:
            continue

        stats.matches_played += 1
        stats.match_goals_history.append(total_goals)

        if is_home:
            scored = home_goals
            conceded = away_goals
        else:
            scored = away_goals
            conceded = home_goals

        scored_list.append(scored)
        conceded_list.append(conceded)
        goal_diffs.append(scored - conceded)

        stats.goals_scored += scored
        stats.goals_conceded += conceded

        # Eredmény
        if scored > conceded:
            result = "W"
            stats.wins += 1
            if conceded == 0:
                win_to_nil_count += 1
        elif scored == conceded:
            result = "D"
            stats.draws += 1
        else:
            result = "L"
            stats.losses += 1

        form_chars.append(result)

        # Félidei gólok
        ht_home = match.get("ht_home_goals")
        ht_away = match.get("ht_away_goals")
        if ht_home is not None and ht_away is not None:
            if is_home:
                first_half_goals_total += int(ht_home)
            else:
                first_half_goals_total += int(ht_away)
            total_goals_for_ht += scored

        # Comeback tracking (félidőben hátrányban volt-e)
        if ht_home is not None and ht_away is not None:
            ht_scored = int(ht_home) if is_home else int(ht_away)
            ht_conceded = int(ht_away) if is_home else int(ht_home)
            if ht_scored < ht_conceded:
                behind_count += 1
                if scored >= conceded:  # Visszajött legalább döntetlenre
                    comeback_count += 1

        # Hazai/Vendég bontás
        if is_home:
            stats.home_matches += 1
            stats.home_goals_scored += scored
            stats.home_goals_conceded += conceded
            if result == "W":
                stats.home_wins += 1
            elif result == "D":
                stats.home_draws += 1
            else:
                stats.home_losses += 1
        else:
            stats.away_matches += 1
            stats.away_goals_scored += scored
            stats.away_goals_conceded += conceded
            if result == "W":
                stats.away_wins += 1
            elif result == "D":
                stats.away_draws += 1
            else:
                stats.away_losses += 1

        # Over/Under és GG számlálók
        if total_goals > 1:
            over15_count += 1
        if total_goals > 2:
            over25_count += 1
        if total_goals > 3:
            over35_count += 1
        if home_goals > 0 and away_goals > 0:
            gg_count += 1
        if conceded == 0:
            clean_sheets += 1

    # Átlagok számítása
    n = stats.matches_played
    if n > 0:
        stats.avg_goals_scored = stats.goals_scored / n
        stats.avg_goals_conceded = stats.goals_conceded / n
        stats.over15_rate = over15_count / n
        stats.over25_rate = over25_count / n
        stats.over35_rate = over35_count / n
        stats.gg_rate = gg_count / n
        stats.clean_sheet_rate = clean_sheets / n
        stats.form_string = "".join(form_chars[:20])

        # Win to nil
        stats.win_to_nil_rate = win_to_nil_count / n

        # Utolsó 5 meccs forma
        recent_5 = form_chars[:5]
        stats.recent_form_5 = "".join(recent_5)
        if recent_5:
            points_5 = sum({"W": 3, "D": 1, "L": 0}.get(c, 0) for c in recent_5)
            stats.recent_form_points_5 = points_5 / len(recent_5)

        # Időszúlyozott átlagok (exponenciális súlycsökkenés)
        weights = [math.exp(-TIME_DECAY_FACTOR * i) for i in range(n)]
        total_weight = sum(weights)
        if total_weight > 0:
            stats.weighted_avg_goals_scored = sum(
                s * w for s, w in zip(scored_list, weights)
            ) / total_weight
            stats.weighted_avg_goals_conceded = sum(
                c * w for c, w in zip(conceded_list, weights)
            ) / total_weight

        # Gólszerzés konzisztenciája (szórás)
        if n > 1:
            mean_scored = stats.avg_goals_scored
            mean_conceded = stats.avg_goals_conceded
            stats.scoring_consistency = math.sqrt(
                sum((s - mean_scored) ** 2 for s in scored_list) / n
            )
            stats.conceding_consistency = math.sqrt(
                sum((c - mean_conceded) ** 2 for c in conceded_list) / n
            )

        # Félidei gól arány
        if total_goals_for_ht > 0:
            stats.first_half_goals_ratio = first_half_goals_total / total_goals_for_ht

        # Comeback ráta
        if behind_count > 0:
            stats.comeback_rate = comeback_count / behind_count

        # Gólkülönbség trend (utolsó 5 vs előző 5)
        if len(goal_diffs) >= 10:
            recent_gd = sum(goal_diffs[:5]) / 5
            older_gd = sum(goal_diffs[5:10]) / 5
            stats.goal_diff_trend = recent_gd - older_gd

    if stats.home_matches > 0:
        stats.avg_home_goals_scored = stats.home_goals_scored / stats.home_matches
        stats.avg_home_goals_conceded = stats.home_goals_conceded / stats.home_matches

    if stats.away_matches > 0:
        stats.avg_away_goals_scored = stats.away_goals_scored / stats.away_matches
        stats.avg_away_goals_conceded = stats.away_goals_conceded / stats.away_matches

    # ELO rating számítás
    stats.strength_rating = calculate_team_strength(team_id, team_name, matches)

    return stats


def calculate_league_averages_from_matches(
    all_matches: list[dict],
) -> LeagueAverages:
    """Liga átlag számítás az összegyűjtött meccs adatokból.

    Args:
        all_matches: Sofascore formátumú meccsek listája

    Returns:
        LeagueAverages a Poisson modellhez
    """
    avg = LeagueAverages()

    total_home_goals = 0
    total_away_goals = 0
    match_count = 0
    seen = set()

    for match in all_matches:
        # Duplikáció szűrés event_id alapján
        event_id = match.get("event_id")
        if event_id and event_id in seen:
            continue
        if event_id:
            seen.add(event_id)

        home_goals = match.get("home_goals")
        away_goals = match.get("away_goals")

        if home_goals is None or away_goals is None:
            continue

        total_home_goals += int(home_goals)
        total_away_goals += int(away_goals)
        match_count += 1

    if match_count > 0:
        avg.avg_home_goals = total_home_goals / match_count
        avg.avg_away_goals = total_away_goals / match_count
        avg.avg_total_goals = avg.avg_home_goals + avg.avg_away_goals
        avg.total_matches = match_count

    return avg


def calculate_league_averages(standings: list[dict]) -> LeagueAverages:
    """Liga átlagokat számít a tabella adatokból (legacy kompatibilitás)."""
    avg = LeagueAverages()

    if not standings:
        return avg

    total_home_goals = 0
    total_away_goals = 0
    total_matches = 0

    for entry in standings:
        played = entry.get("playedGames", 0)
        gf = entry.get("goalsFor", 0)
        ga = entry.get("goalsAgainst", 0)
        total_matches += played
        total_home_goals += gf
        total_away_goals += ga

    if total_matches > 0:
        actual_matches = total_matches // 2
        if actual_matches > 0:
            avg.avg_total_goals = total_home_goals / actual_matches
            avg.avg_home_goals = avg.avg_total_goals * 0.55
            avg.avg_away_goals = avg.avg_total_goals * 0.45
            avg.total_matches = actual_matches

    return avg


def calculate_strength(
    stats: TeamStats, league_avg: LeagueAverages
) -> TeamStats:
    """Kiszámítja a csapat támadó és védekező erősségét a liga átlaghoz képest.

    Bővített: időszúlyozott átlagok használata.
    """
    if league_avg.avg_home_goals > 0 and league_avg.avg_away_goals > 0:
        # Használjuk az időszúlyozott átlagokat ha van
        scored_avg = stats.weighted_avg_goals_scored if stats.weighted_avg_goals_scored > 0 else stats.avg_goals_scored
        conceded_avg = stats.weighted_avg_goals_conceded if stats.weighted_avg_goals_conceded > 0 else stats.avg_goals_conceded

        # Általános erősség
        stats.attack_strength = (
            scored_avg / league_avg.avg_total_goals * 2
            if league_avg.avg_total_goals > 0 else 1.0
        )
        stats.defense_strength = (
            conceded_avg / league_avg.avg_total_goals * 2
            if league_avg.avg_total_goals > 0 else 1.0
        )

        # Hazai erősség
        if stats.home_matches > 0:
            stats.home_attack_strength = (
                stats.avg_home_goals_scored / league_avg.avg_home_goals
            )
            stats.home_defense_strength = (
                stats.avg_home_goals_conceded / league_avg.avg_away_goals
            )
        else:
            stats.home_attack_strength = stats.attack_strength
            stats.home_defense_strength = stats.defense_strength

        # Vendég erősség
        if stats.away_matches > 0:
            stats.away_attack_strength = (
                stats.avg_away_goals_scored / league_avg.avg_away_goals
            )
            stats.away_defense_strength = (
                stats.avg_away_goals_conceded / league_avg.avg_home_goals
            )
        else:
            stats.away_attack_strength = stats.attack_strength
            stats.away_defense_strength = stats.defense_strength

    return stats


def calculate_head_to_head(
    matches: list[dict], home_team_id: int, away_team_id: int
) -> HeadToHead:
    """Head-to-head statisztikák számítása - bővített."""
    h2h = HeadToHead()

    total_home_goals = 0
    total_away_goals = 0
    over25_count = 0
    gg_count = 0

    for match in matches:
        home_id = match.get("home_team_id", match.get("homeTeam", {}).get("id"))
        away_id = match.get("away_team_id", match.get("awayTeam", {}).get("id"))

        home_goals = match.get("home_goals")
        away_goals = match.get("away_goals")

        if home_goals is None or away_goals is None:
            score = match.get("score", {}).get("fullTime", {})
            home_goals = score.get("home")
            away_goals = score.get("away")

        if home_goals is None or away_goals is None:
            continue

        hg, ag = int(home_goals), int(away_goals)

        ids = {home_id, away_id}
        if home_team_id not in ids or away_team_id not in ids:
            continue

        h2h.matches_played += 1
        h2h.avg_total_goals += hg + ag

        total_goals = hg + ag
        if total_goals > 2:
            over25_count += 1
        if hg > 0 and ag > 0:
            gg_count += 1

        if home_id == home_team_id:
            total_home_goals += hg
            total_away_goals += ag
            if hg > ag:
                h2h.home_wins += 1
                h2h.last_results.append("W")
            elif hg == ag:
                h2h.draws += 1
                h2h.last_results.append("D")
            else:
                h2h.away_wins += 1
                h2h.last_results.append("L")
        else:
            total_home_goals += ag
            total_away_goals += hg
            if ag > hg:
                h2h.home_wins += 1
                h2h.last_results.append("W")
            elif ag == hg:
                h2h.draws += 1
                h2h.last_results.append("D")
            else:
                h2h.away_wins += 1
                h2h.last_results.append("L")

    n = h2h.matches_played
    if n > 0:
        h2h.avg_total_goals /= n
        h2h.avg_home_goals = total_home_goals / n
        h2h.avg_away_goals = total_away_goals / n
        h2h.over25_rate = over25_count / n
        h2h.gg_rate = gg_count / n
        h2h.home_win_rate = h2h.home_wins / n
        h2h.draw_rate = h2h.draws / n
        h2h.away_win_rate = h2h.away_wins / n
        h2h.recent_trend = "".join(h2h.last_results[:5])

        # Dominancia score: -1 (vendég) ... +1 (hazai)
        h2h.dominance_score = (h2h.home_wins - h2h.away_wins) / n

    return h2h


def update_stats_from_standings(stats: TeamStats, standings: list[dict]) -> TeamStats:
    """Tabella adatokból frissíti a csapat statisztikáit."""
    for entry in standings:
        team = entry.get("team", {})
        if team.get("id") == stats.team_id or team.get("name") == stats.team_name:
            stats.league_position = entry.get("position", 0)
            stats.league_points = entry.get("points", 0)
            break
    return stats
