"""Predikciós motor - Poisson modell alapú focimeccs előrejelzés.

A Poisson eloszlás segítségével becsli a gólszámokat,
majd ebből számítja a különböző piacok valószínűségeit.
Bővített: O/U 1.5, 2.5, 3.5 + statisztikai O/U ráták.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import poisson

from src.analysis.stats import HeadToHead, LeagueAverages, TeamStats
from src.config import POISSON_MAX_GOALS, VALUE_BET_THRESHOLD
from src.scrapers.odds_api import MatchOdds


@dataclass
class MatchPrediction:
    """Egy meccs teljes predikciója."""
    home_team: str = ""
    away_team: str = ""
    competition: str = ""

    # Poisson paraméterek
    expected_home_goals: float = 0.0
    expected_away_goals: float = 0.0

    # 1X2 valószínűségek
    home_win_prob: float = 0.0
    draw_prob: float = 0.0
    away_win_prob: float = 0.0

    # Over/Under 1.5 (Poisson)
    over15_prob: float = 0.0
    under15_prob: float = 0.0

    # Over/Under 2.5 (Poisson)
    over25_prob: float = 0.0
    under25_prob: float = 0.0

    # Over/Under 3.5 (Poisson)
    over35_prob: float = 0.0
    under35_prob: float = 0.0

    # GG/NG
    gg_prob: float = 0.0
    ng_prob: float = 0.0

    # Statisztikai O/U ráták (tényleges meccs történetből)
    home_stat_over15: float = 0.0
    home_stat_over25: float = 0.0
    home_stat_over35: float = 0.0
    away_stat_over15: float = 0.0
    away_stat_over25: float = 0.0
    away_stat_over35: float = 0.0
    combined_stat_over15: float = 0.0
    combined_stat_over25: float = 0.0
    combined_stat_over35: float = 0.0

    # Top 5 legvalószínűbb pontos eredmény
    exact_scores: list[tuple[str, float]] = field(default_factory=list)

    # Gól-mátrix
    goal_matrix: np.ndarray = field(default_factory=lambda: np.zeros((1, 1)))

    # Value bets (Poisson alapú)
    value_bets: list[dict] = field(default_factory=list)

    # Stat value bets (statisztikai O/U alapú)
    stat_value_bets: list[dict] = field(default_factory=list)

    # Meta
    confidence: float = 0.0
    recommended_bet: str = ""
    recommended_odds: float = 0.0

    # Input statisztikák referencia
    home_stats: TeamStats | None = None
    away_stats: TeamStats | None = None

    # Odds referencia
    match_odds: MatchOdds | None = None


class PredictionEngine:
    """Poisson-modell alapú predikciós motor."""

    def __init__(self, max_goals: int = POISSON_MAX_GOALS):
        self.max_goals = max_goals

    def predict(
        self,
        home_stats: TeamStats,
        away_stats: TeamStats,
        league_avg: LeagueAverages,
        h2h: HeadToHead | None = None,
        odds: MatchOdds | None = None,
    ) -> MatchPrediction:
        """Teljes meccs predikció."""
        pred = MatchPrediction(
            home_team=home_stats.team_name,
            away_team=away_stats.team_name,
            home_stats=home_stats,
            away_stats=away_stats,
            match_odds=odds,
        )

        # 1) Várható gólok
        pred.expected_home_goals = self._calculate_expected_goals(
            home_stats, away_stats, league_avg, is_home=True
        )
        pred.expected_away_goals = self._calculate_expected_goals(
            away_stats, home_stats, league_avg, is_home=False
        )

        # H2H korrekció
        if h2h and h2h.matches_played >= 3:
            pred.expected_home_goals, pred.expected_away_goals = (
                self._h2h_adjustment(
                    pred.expected_home_goals,
                    pred.expected_away_goals,
                    h2h,
                )
            )

        # Minimum 0.2 gól
        pred.expected_home_goals = max(0.2, pred.expected_home_goals)
        pred.expected_away_goals = max(0.2, pred.expected_away_goals)

        # 2) Gól-mátrix (Poisson)
        pred.goal_matrix = self._build_goal_matrix(
            pred.expected_home_goals, pred.expected_away_goals
        )

        # 3) Piacok valószínűségei
        self._calculate_1x2(pred)
        self._calculate_over_under_15(pred)
        self._calculate_over_under_25(pred)
        self._calculate_over_under_35(pred)
        self._calculate_gg_ng(pred)
        self._calculate_exact_scores(pred)

        # 4) Statisztikai O/U ráták
        self._calculate_statistical_ou(pred)

        # 5) Value bet elemzés
        if odds:
            self._find_value_bets(pred, odds)
            self._find_stat_value_bets(pred, odds)

        # 6) Konfidencia és ajánlás
        self._calculate_confidence(pred)
        self._generate_recommendation(pred, odds)

        return pred

    def _calculate_expected_goals(
        self,
        attacking_team: TeamStats,
        defending_team: TeamStats,
        league_avg: LeagueAverages,
        is_home: bool,
    ) -> float:
        """Várható gólszám számítása."""
        if is_home:
            attack = attacking_team.home_attack_strength
            defense = defending_team.away_defense_strength
            league_rate = league_avg.avg_home_goals
        else:
            attack = attacking_team.away_attack_strength
            defense = defending_team.home_defense_strength
            league_rate = league_avg.avg_away_goals

        if attack == 0:
            attack = 1.0
        if defense == 0:
            defense = 1.0
        if league_rate == 0:
            league_rate = 1.3

        expected = attack * defense * league_rate

        # Forma korrekció
        form = attacking_team.form_string[:5]
        if form:
            form_factor = self._form_factor(form)
            expected *= form_factor

        return expected

    def _form_factor(self, form_string: str) -> float:
        """Forma korrekciósfaktor (0.85 - 1.15)."""
        if not form_string:
            return 1.0

        points = sum(
            {"W": 3, "D": 1, "L": 0}.get(c, 0) for c in form_string
        )
        max_points = len(form_string) * 3
        form_ratio = points / max_points

        return 0.85 + form_ratio * 0.30

    def _h2h_adjustment(
        self,
        exp_home: float,
        exp_away: float,
        h2h: HeadToHead,
    ) -> tuple[float, float]:
        """H2H finomhangolás (max ±10%)."""
        n = h2h.matches_played
        if n < 3:
            return exp_home, exp_away

        home_rate = h2h.home_wins / n
        away_rate = h2h.away_wins / n

        home_adj = max(0.90, min(1.10, 1.0 + (home_rate - 0.5) * 0.2))
        away_adj = max(0.90, min(1.10, 1.0 + (away_rate - 0.5) * 0.2))

        return exp_home * home_adj, exp_away * away_adj

    def _build_goal_matrix(
        self, exp_home: float, exp_away: float
    ) -> np.ndarray:
        """Poisson gól-mátrix."""
        home_probs = [
            poisson.pmf(i, exp_home) for i in range(self.max_goals + 1)
        ]
        away_probs = [
            poisson.pmf(i, exp_away) for i in range(self.max_goals + 1)
        ]
        return np.outer(home_probs, away_probs)

    def _calculate_1x2(self, pred: MatchPrediction):
        """1X2 valószínűségek."""
        matrix = pred.goal_matrix
        n = matrix.shape[0]

        home_win = 0.0
        draw = 0.0
        away_win = 0.0

        for i in range(n):
            for j in range(n):
                if i > j:
                    home_win += matrix[i, j]
                elif i == j:
                    draw += matrix[i, j]
                else:
                    away_win += matrix[i, j]

        total = home_win + draw + away_win
        if total > 0:
            pred.home_win_prob = home_win / total
            pred.draw_prob = draw / total
            pred.away_win_prob = away_win / total

    def _calculate_over_under_15(self, pred: MatchPrediction):
        """Over/Under 1.5 valószínűségek."""
        matrix = pred.goal_matrix
        n = matrix.shape[0]

        under = 0.0
        for i in range(n):
            for j in range(n):
                if i + j <= 1:
                    under += matrix[i, j]

        pred.under15_prob = under
        pred.over15_prob = 1.0 - under

    def _calculate_over_under_25(self, pred: MatchPrediction):
        """Over/Under 2.5 valószínűségek."""
        matrix = pred.goal_matrix
        n = matrix.shape[0]

        under = 0.0
        for i in range(n):
            for j in range(n):
                if i + j <= 2:
                    under += matrix[i, j]

        pred.under25_prob = under
        pred.over25_prob = 1.0 - under

    def _calculate_over_under_35(self, pred: MatchPrediction):
        """Over/Under 3.5 valószínűségek."""
        matrix = pred.goal_matrix
        n = matrix.shape[0]

        under = 0.0
        for i in range(n):
            for j in range(n):
                if i + j <= 3:
                    under += matrix[i, j]

        pred.under35_prob = under
        pred.over35_prob = 1.0 - under

    def _calculate_gg_ng(self, pred: MatchPrediction):
        """GG/NG valószínűségek."""
        matrix = pred.goal_matrix
        n = matrix.shape[0]

        ng = 0.0
        for i in range(n):
            ng += matrix[0, i]
        for j in range(n):
            ng += matrix[j, 0]
        ng -= matrix[0, 0]

        pred.ng_prob = min(ng, 1.0)
        pred.gg_prob = 1.0 - pred.ng_prob

    def _calculate_exact_scores(self, pred: MatchPrediction):
        """Top 5 legvalószínűbb pontos eredmény."""
        matrix = pred.goal_matrix
        n = matrix.shape[0]

        scores = []
        for i in range(n):
            for j in range(n):
                scores.append((f"{i}-{j}", matrix[i, j]))

        scores.sort(key=lambda x: x[1], reverse=True)
        pred.exact_scores = scores[:5]

    def _calculate_statistical_ou(self, pred: MatchPrediction):
        """Statisztikai O/U ráták a TeamStats-ból (tényleges meccs történet)."""
        hs = pred.home_stats
        aws = pred.away_stats

        if hs:
            pred.home_stat_over15 = hs.over15_rate
            pred.home_stat_over25 = hs.over25_rate
            pred.home_stat_over35 = hs.over35_rate

        if aws:
            pred.away_stat_over15 = aws.over15_rate
            pred.away_stat_over25 = aws.over25_rate
            pred.away_stat_over35 = aws.over35_rate

        # Kombinált: két csapat átlaga
        if hs and aws:
            pred.combined_stat_over15 = (hs.over15_rate + aws.over15_rate) / 2
            pred.combined_stat_over25 = (hs.over25_rate + aws.over25_rate) / 2
            pred.combined_stat_over35 = (hs.over35_rate + aws.over35_rate) / 2

    def _find_value_bets(self, pred: MatchPrediction, odds: MatchOdds):
        """Poisson value bet azonosítás (11 piac)."""
        pred.value_bets = []

        markets = [
            ("1 (Hazai)", pred.home_win_prob, odds.home_win),
            ("X (Döntetlen)", pred.draw_prob, odds.draw),
            ("2 (Vendég)", pred.away_win_prob, odds.away_win),
            ("Over 1.5", pred.over15_prob, odds.over_15),
            ("Under 1.5", pred.under15_prob, odds.under_15),
            ("Over 2.5", pred.over25_prob, odds.over_25),
            ("Under 2.5", pred.under25_prob, odds.under_25),
            ("Over 3.5", pred.over35_prob, odds.over_35),
            ("Under 3.5", pred.under35_prob, odds.under_35),
            ("GG", pred.gg_prob, odds.gg),
            ("NG", pred.ng_prob, odds.ng),
        ]

        for name, our_prob, market_odds in markets:
            if market_odds <= 1.0 or our_prob <= 0:
                continue

            implied_prob = 1.0 / market_odds
            edge = our_prob - implied_prob

            if edge > VALUE_BET_THRESHOLD:
                pred.value_bets.append({
                    "market": name,
                    "our_prob": our_prob,
                    "implied_prob": implied_prob,
                    "odds": market_odds,
                    "edge": edge,
                    "expected_value": our_prob * market_odds - 1.0,
                })

        pred.value_bets.sort(key=lambda x: x["edge"], reverse=True)

    def _find_stat_value_bets(self, pred: MatchPrediction, odds: MatchOdds):
        """Statisztikai value bet azonosítás (stat% vs odds)."""
        pred.stat_value_bets = []

        markets = [
            ("Stat O1.5", pred.combined_stat_over15, odds.over_15),
            ("Stat U1.5", 1.0 - pred.combined_stat_over15 if pred.combined_stat_over15 > 0 else 0, odds.under_15),
            ("Stat O2.5", pred.combined_stat_over25, odds.over_25),
            ("Stat U2.5", 1.0 - pred.combined_stat_over25 if pred.combined_stat_over25 > 0 else 0, odds.under_25),
            ("Stat O3.5", pred.combined_stat_over35, odds.over_35),
            ("Stat U3.5", 1.0 - pred.combined_stat_over35 if pred.combined_stat_over35 > 0 else 0, odds.under_35),
        ]

        for name, stat_prob, market_odds in markets:
            if market_odds <= 1.0 or stat_prob <= 0:
                continue

            implied_prob = 1.0 / market_odds
            edge = stat_prob - implied_prob

            if edge > VALUE_BET_THRESHOLD:
                pred.stat_value_bets.append({
                    "market": name,
                    "stat_prob": stat_prob,
                    "implied_prob": implied_prob,
                    "odds": market_odds,
                    "edge": edge,
                })

        pred.stat_value_bets.sort(key=lambda x: x["edge"], reverse=True)

    def _calculate_confidence(self, pred: MatchPrediction):
        """Összesített konfidencia számítás."""
        max_prob = max(pred.home_win_prob, pred.draw_prob, pred.away_win_prob)

        data_quality = 1.0
        if pred.home_stats and pred.home_stats.matches_played < 5:
            data_quality *= 0.7
        if pred.away_stats and pred.away_stats.matches_played < 5:
            data_quality *= 0.7

        pred.confidence = max_prob * data_quality

    def _generate_recommendation(
        self, pred: MatchPrediction, odds: MatchOdds | None
    ):
        """Legjobb fogadási ajánlás generálása."""
        # Ha van value bet, azt ajánljuk
        if pred.value_bets:
            best = pred.value_bets[0]
            pred.recommended_bet = best["market"]
            pred.recommended_odds = best["odds"]
            return

        # Ha van stat value bet
        if pred.stat_value_bets:
            best = pred.stat_value_bets[0]
            pred.recommended_bet = best["market"]
            pred.recommended_odds = best["odds"]
            return

        # Legnagyobb valószínűségű kimenetel
        options = [
            ("1 (Hazai)", pred.home_win_prob, odds.home_win if odds else 0),
            ("X (Döntetlen)", pred.draw_prob, odds.draw if odds else 0),
            ("2 (Vendég)", pred.away_win_prob, odds.away_win if odds else 0),
        ]

        if pred.over25_prob > 0.60:
            options.append(
                ("Over 2.5", pred.over25_prob, odds.over_25 if odds else 0)
            )
        if pred.under25_prob > 0.60:
            options.append(
                ("Under 2.5", pred.under25_prob, odds.under_25 if odds else 0)
            )
        if pred.gg_prob > 0.60:
            options.append(("GG", pred.gg_prob, odds.gg if odds else 0))
        if pred.ng_prob > 0.60:
            options.append(("NG", pred.ng_prob, odds.ng if odds else 0))

        best = max(options, key=lambda x: x[1])
        pred.recommended_bet = best[0]
        pred.recommended_odds = best[2]
