"""Statisztikai elemzés modul.

Csapatforma, gólátlagok, hazai/vendég erő, O/U ráták (1.5, 2.5, 3.5).
Sofascore adatformátumra optimalizálva.
"""

from dataclasses import dataclass, field


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


@dataclass
class HeadToHead:
    """Két csapat egymás elleni statisztikái."""
    matches_played: int = 0
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    avg_total_goals: float = 0.0
    last_results: list[str] = field(default_factory=list)


@dataclass
class LeagueAverages:
    """Liga átlagok a Poisson modellhez."""
    competition_code: str = ""
    avg_home_goals: float = 1.5
    avg_away_goals: float = 1.2
    avg_total_goals: float = 2.7
    total_matches: int = 0


def calculate_team_stats(
    team_name: str,
    team_id: int | None,
    matches: list[dict],
    competition_code: str = "",
) -> TeamStats:
    """Csapat statisztikáit számítja ki a Sofascore meccs-történetből.

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

    for match in matches:
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

        stats.goals_scored += scored
        stats.goals_conceded += conceded

        # Eredmény
        if scored > conceded:
            result = "W"
            stats.wins += 1
        elif scored == conceded:
            result = "D"
            stats.draws += 1
        else:
            result = "L"
            stats.losses += 1

        form_chars.append(result)

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
        stats.form_string = "".join(form_chars[:10])

    if stats.home_matches > 0:
        stats.avg_home_goals_scored = stats.home_goals_scored / stats.home_matches
        stats.avg_home_goals_conceded = stats.home_goals_conceded / stats.home_matches

    if stats.away_matches > 0:
        stats.avg_away_goals_scored = stats.away_goals_scored / stats.away_matches
        stats.avg_away_goals_conceded = stats.away_goals_conceded / stats.away_matches

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
    """Kiszámítja a csapat támadó és védekező erősségét a liga átlaghoz képest."""
    if league_avg.avg_home_goals > 0 and league_avg.avg_away_goals > 0:
        # Általános erősség
        stats.attack_strength = (
            stats.avg_goals_scored / league_avg.avg_total_goals * 2
            if league_avg.avg_total_goals > 0 else 1.0
        )
        stats.defense_strength = (
            stats.avg_goals_conceded / league_avg.avg_total_goals * 2
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
    """Head-to-head statisztikák számítása."""
    h2h = HeadToHead()

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

        if home_id == home_team_id:
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
            if ag > hg:
                h2h.home_wins += 1
                h2h.last_results.append("W")
            elif ag == hg:
                h2h.draws += 1
                h2h.last_results.append("D")
            else:
                h2h.away_wins += 1
                h2h.last_results.append("L")

    if h2h.matches_played > 0:
        h2h.avg_total_goals /= h2h.matches_played

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
