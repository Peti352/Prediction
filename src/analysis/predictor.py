"""Predikciós motor - Kalibrált ensemble modell focimeccs előrejelzéshez.

Modellek:
1. Dixon-Coles korrigált Poisson modell
2. Strength rating alapú valószínűségek (rövid távú erősségmutató)
3. Időszúlyozott forma modell

v4: Probability kalibráció, per-market súlyok, szigorúbb value bet,
    prediction vs betting confidence szétválasztás, single bet fókusz.
"""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import poisson

from src.analysis.stats import (
    HeadToHead,
    LeagueAverages,
    TeamStats,
    strength_to_probabilities,
)
from src.config import (
    CALIBRATION_MAX_PROB,
    CALIBRATION_MIN_PROB,
    CALIBRATION_SHRINKAGE,
    DIXON_COLES_RHO,
    ENSEMBLE_WEIGHTS_1X2,
    ENSEMBLE_WEIGHTS_GGNG,
    ENSEMBLE_WEIGHTS_OU,
    POISSON_MAX_GOALS,
    VALUE_BET_MAX_ODDS,
    VALUE_BET_MIN_CONFIDENCE,
    VALUE_BET_MIN_EDGE,
    VALUE_BET_MIN_ODDS,
)
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

    # 1X2 valószínűségek (Ensemble)
    home_win_prob: float = 0.0
    draw_prob: float = 0.0
    away_win_prob: float = 0.0

    # Egyes modellek 1X2 valószínűségei (átláthatóság)
    poisson_home: float = 0.0
    poisson_draw: float = 0.0
    poisson_away: float = 0.0
    strength_home: float = 0.0
    strength_draw: float = 0.0
    strength_away: float = 0.0
    form_home: float = 0.0
    form_draw: float = 0.0
    form_away: float = 0.0

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

    # Ensemble részletek
    model_agreement: float = 0.0  # Modellek közötti egyetértés (0-1)
    prediction_quality: str = ""   # "magas" / "közepes" / "alacsony"

    # Szétválasztott confidence
    betting_confidence: float = 0.0  # Fogadási megbízhatóság (szigorúbb)

    # Single bet ajánlások
    best_single_bet: dict = None     # Legjobb single tipp
    best_value_single: dict = None   # Legjobb value single

    # H2H referencia
    h2h_data: HeadToHead | None = None


class PredictionEngine:
    """Ensemble predikciós motor - Dixon-Coles + ELO + Forma."""

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
        """Teljes meccs predikció ensemble modellel."""
        pred = MatchPrediction(
            home_team=home_stats.team_name,
            away_team=away_stats.team_name,
            home_stats=home_stats,
            away_stats=away_stats,
            match_odds=odds,
            h2h_data=h2h,
        )

        # === 1. MODELL: Dixon-Coles Poisson ===
        pred.expected_home_goals = self._calculate_expected_goals(
            home_stats, away_stats, league_avg, is_home=True
        )
        pred.expected_away_goals = self._calculate_expected_goals(
            away_stats, home_stats, league_avg, is_home=False
        )

        # H2H korrekció a lambda-kra
        if h2h and h2h.matches_played >= 3:
            pred.expected_home_goals, pred.expected_away_goals = (
                self._h2h_goal_adjustment(
                    pred.expected_home_goals,
                    pred.expected_away_goals,
                    h2h,
                )
            )

        # Minimum 0.2 gól
        pred.expected_home_goals = max(0.2, pred.expected_home_goals)
        pred.expected_away_goals = max(0.2, pred.expected_away_goals)

        # Dixon-Coles korrigált gól-mátrix
        pred.goal_matrix = self._build_dixon_coles_matrix(
            pred.expected_home_goals, pred.expected_away_goals
        )

        # Poisson 1X2
        self._calculate_1x2_from_matrix(pred)
        pred.poisson_home = pred.home_win_prob
        pred.poisson_draw = pred.draw_prob
        pred.poisson_away = pred.away_win_prob

        # O/U és GG/NG (ezek a mátrixból jönnek, nem az ensemble-ből)
        self._calculate_over_under_15(pred)
        self._calculate_over_under_25(pred)
        self._calculate_over_under_35(pred)
        self._calculate_gg_ng(pred)
        self._calculate_exact_scores(pred)

        # === 2. MODELL: Strength Rating ===
        pred.strength_home, pred.strength_draw, pred.strength_away = strength_to_probabilities(
            home_stats.strength_rating, away_stats.strength_rating
        )

        # === 3. MODELL: Forma ===
        pred.form_home, pred.form_draw, pred.form_away = self._form_based_prediction(
            home_stats, away_stats
        )

        # === ENSEMBLE KOMBINÁLÁS (per-market súlyokkal) ===
        self._ensemble_combine(pred, h2h)

        # === PROBABILITY KALIBRÁCIÓ ===
        self._calibrate_probabilities(pred)

        # Statisztikai O/U ráták
        self._calculate_statistical_ou(pred)

        # Value bet elemzés (kalibrált valószínűségekből)
        if odds:
            self._find_value_bets(pred, odds)
            self._find_stat_value_bets(pred, odds)

        # Konfidencia (prediction + betting külön)
        self._calculate_confidence(pred)
        self._generate_recommendation(pred, odds)

        return pred

    # === Dixon-Coles Modell ===

    def _dixon_coles_correction(
        self,
        home_goals: int,
        away_goals: int,
        lambda_home: float,
        mu_away: float,
        rho: float = DIXON_COLES_RHO,
    ) -> float:
        """Dixon-Coles korrekció alacsony gólszámú meccsekre.

        Az alap Poisson modell feltételezi a gólok függetlenségét,
        de a valóságban az alacsony gólszámú eredmények (0-0, 1-0, 0-1, 1-1)
        korrelálnak egymással. A rho paraméter ezt korrigálja.
        """
        if home_goals == 0 and away_goals == 0:
            return 1.0 - lambda_home * mu_away * rho
        elif home_goals == 0 and away_goals == 1:
            return 1.0 + lambda_home * rho
        elif home_goals == 1 and away_goals == 0:
            return 1.0 + mu_away * rho
        elif home_goals == 1 and away_goals == 1:
            return 1.0 - rho
        else:
            return 1.0

    def _build_dixon_coles_matrix(
        self, exp_home: float, exp_away: float
    ) -> np.ndarray:
        """Dixon-Coles korrigált gól-mátrix."""
        n = self.max_goals + 1
        matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(n):
                base_prob = poisson.pmf(i, exp_home) * poisson.pmf(j, exp_away)
                correction = self._dixon_coles_correction(
                    i, j, exp_home, exp_away
                )
                matrix[i, j] = base_prob * max(0.0, correction)

        # Normalizálás (a korrekció miatt a teljes összeg eltérhet 1-től)
        total = matrix.sum()
        if total > 0:
            matrix /= total

        return matrix

    def _calculate_expected_goals(
        self,
        attacking_team: TeamStats,
        defending_team: TeamStats,
        league_avg: LeagueAverages,
        is_home: bool,
    ) -> float:
        """Várható gólszám számítása - időszúlyozott erősségekkel."""
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

        # Forma korrekció (utolsó 5 meccs, nagyobb súly)
        form = attacking_team.recent_form_5 or attacking_team.form_string[:5]
        if form:
            form_factor = self._form_factor(form)
            expected *= form_factor

        # Gólkülönbség trend korrekció
        if attacking_team.goal_diff_trend != 0:
            trend_factor = 1.0 + attacking_team.goal_diff_trend * 0.03
            trend_factor = max(0.90, min(1.10, trend_factor))
            expected *= trend_factor

        # Konzisztencia korrekció
        # Inkonzisztens gólszerzés = nagyobb bizonytalanság
        if attacking_team.scoring_consistency > 1.5:
            expected *= 0.97  # Kicsit csökkentjük ha nagyon változékony

        return expected

    def _form_factor(self, form_string: str) -> float:
        """Időszúlyozott forma korrekciósfaktor (0.82 - 1.18).

        Újabb meccsek nagyobb súlyt kapnak.
        """
        if not form_string:
            return 1.0

        total_weighted = 0.0
        total_weight = 0.0

        for i, char in enumerate(form_string):
            points = {"W": 3, "D": 1, "L": 0}.get(char, 0)
            weight = math.exp(-0.15 * i)  # Exponenciális súlycsökkenés
            total_weighted += points * weight
            total_weight += weight

        if total_weight == 0:
            return 1.0

        weighted_ratio = total_weighted / (total_weight * 3)
        return 0.82 + weighted_ratio * 0.36

    # === ELO Modell ===
    # (Az ELO számítás a stats.py-ban van, itt csak a valószínűségeket használjuk)

    # === Forma Modell ===

    def _form_based_prediction(
        self,
        home_stats: TeamStats,
        away_stats: TeamStats,
    ) -> tuple[float, float, float]:
        """Forma alapú 1X2 valószínűségek.

        Az utolsó 5-10 meccs eredményeiből számol, figyelembe véve:
        - Hazai/vendég forma külön
        - Pont/meccs arány
        - Győzelmi/vereségi sorozatok
        """
        # Hazai csapat hazai formája
        home_form_score = self._calculate_form_score(home_stats, is_home=True)
        # Vendég csapat vendég formája
        away_form_score = self._calculate_form_score(away_stats, is_home=False)

        # Nyers erőviszonyok formából
        home_power = home_form_score * 1.1  # Hazai pálya szorzó
        away_power = away_form_score

        total = home_power + away_power
        if total == 0:
            return 0.4, 0.25, 0.35

        home_ratio = home_power / total
        away_ratio = away_power / total

        # Döntetlen valószínűsége a forma egyensúlyából
        form_diff = abs(home_ratio - away_ratio)
        draw_prob = max(0.15, 0.30 - form_diff * 0.4)

        home_win = home_ratio * (1.0 - draw_prob)
        away_win = away_ratio * (1.0 - draw_prob)

        # Normalizálás
        total = home_win + draw_prob + away_win
        return home_win / total, draw_prob / total, away_win / total

    def _calculate_form_score(
        self, stats: TeamStats, is_home: bool
    ) -> float:
        """Forma pontszám (0.0 - 3.0)."""
        if stats.matches_played == 0:
            return 1.5

        # Utolsó 5 meccs pont/meccs
        recent_ppg = stats.recent_form_points_5 if stats.recent_form_points_5 > 0 else 1.5

        # Hazai/vendég specifikus teljesítmény
        if is_home and stats.home_matches > 0:
            specific_ppg = (
                stats.home_wins * 3 + stats.home_draws
            ) / stats.home_matches
        elif not is_home and stats.away_matches > 0:
            specific_ppg = (
                stats.away_wins * 3 + stats.away_draws
            ) / stats.away_matches
        else:
            specific_ppg = recent_ppg

        # Súlyozott: 60% utolsó 5, 40% hazai/vendég specifikus
        return recent_ppg * 0.6 + specific_ppg * 0.4

    # === Ensemble (per-market súlyok) ===

    def _ensemble_combine(
        self,
        pred: MatchPrediction,
        h2h: HeadToHead | None,
    ):
        """Modellek kombinálása per-market súlyokkal."""
        w = ENSEMBLE_WEIGHTS_1X2

        # H2H modell (ha van elég adat, recency-vel súlyozva)
        if h2h and h2h.matches_played >= 3:
            h2h_home = h2h.home_win_rate
            h2h_draw = h2h.draw_rate
            h2h_away = h2h.away_win_rate
        else:
            # Ha nincs H2H, a strength-nek adjuk a súlyt
            h2h_home = pred.strength_home
            h2h_draw = pred.strength_draw
            h2h_away = pred.strength_away

        # Stat modell (O/U trendekből)
        stat_home, stat_draw, stat_away = self._stats_based_1x2(pred)

        # Súlyozott összeg (1X2 per-market súlyokkal)
        models = [
            (pred.poisson_home, pred.poisson_draw, pred.poisson_away, w["poisson"]),
            (pred.strength_home, pred.strength_draw, pred.strength_away, w["strength"]),
            (pred.form_home, pred.form_draw, pred.form_away, w["form"]),
            (h2h_home, h2h_draw, h2h_away, w["h2h"]),
            (stat_home, stat_draw, stat_away, w["stats"]),
        ]

        combined_home = sum(h * wt for h, _, _, wt in models)
        combined_draw = sum(d * wt for _, d, _, wt in models)
        combined_away = sum(a * wt for _, _, a, wt in models)

        # Normalizálás
        total = combined_home + combined_draw + combined_away
        if total > 0:
            pred.home_win_prob = combined_home / total
            pred.draw_prob = combined_draw / total
            pred.away_win_prob = combined_away / total

        # Modellek közötti egyetértés - direction + magnitude
        all_home_probs = [h for h, _, _, _ in models]
        all_away_probs = [a for _, _, a, _ in models]

        if len(all_home_probs) > 1:
            home_std = np.std(all_home_probs)
            away_std = np.std(all_away_probs)
            avg_std = (home_std + away_std) / 2
            pred.model_agreement = max(0.0, 1.0 - avg_std * 5)

    # === Probability Kalibráció ===

    def _calibrate_probabilities(self, pred: MatchPrediction):
        """Szélsőséges valószínűségek visszahúzása a realitás felé.

        Shrinkage: húzza a valószínűségeket az átlag felé, csökkenti az
        overconfidence-t. A piac baseline: H=0.45, D=0.27, A=0.28.
        """
        baseline = {"home": 0.45, "draw": 0.27, "away": 0.28}
        s = CALIBRATION_SHRINKAGE

        # 1X2 shrinkage
        pred.home_win_prob = pred.home_win_prob * (1 - s) + baseline["home"] * s
        pred.draw_prob = pred.draw_prob * (1 - s) + baseline["draw"] * s
        pred.away_win_prob = pred.away_win_prob * (1 - s) + baseline["away"] * s

        # Clamp szélsőséges értékek
        pred.home_win_prob = max(CALIBRATION_MIN_PROB, min(CALIBRATION_MAX_PROB, pred.home_win_prob))
        pred.draw_prob = max(CALIBRATION_MIN_PROB, min(CALIBRATION_MAX_PROB, pred.draw_prob))
        pred.away_win_prob = max(CALIBRATION_MIN_PROB, min(CALIBRATION_MAX_PROB, pred.away_win_prob))

        # Normalizálás
        total = pred.home_win_prob + pred.draw_prob + pred.away_win_prob
        if total > 0:
            pred.home_win_prob /= total
            pred.draw_prob /= total
            pred.away_win_prob /= total

        # O/U kalibráció (shrinkage 50% felé)
        ou_baseline = 0.50
        for attr_o, attr_u in [
            ("over15_prob", "under15_prob"),
            ("over25_prob", "under25_prob"),
            ("over35_prob", "under35_prob"),
        ]:
            over_val = getattr(pred, attr_o)
            calibrated = over_val * (1 - s) + ou_baseline * s
            calibrated = max(CALIBRATION_MIN_PROB, min(CALIBRATION_MAX_PROB, calibrated))
            setattr(pred, attr_o, calibrated)
            setattr(pred, attr_u, 1.0 - calibrated)

        # GG/NG kalibráció
        gg_baseline = 0.48
        pred.gg_prob = pred.gg_prob * (1 - s) + gg_baseline * s
        pred.gg_prob = max(CALIBRATION_MIN_PROB, min(CALIBRATION_MAX_PROB, pred.gg_prob))
        pred.ng_prob = 1.0 - pred.gg_prob

    def _stats_based_1x2(
        self, pred: MatchPrediction
    ) -> tuple[float, float, float]:
        """Statisztikai mutatókból 1X2 becslés."""
        hs = pred.home_stats
        aws = pred.away_stats

        if not hs or not aws:
            return 0.4, 0.25, 0.35

        # Gólszerzés vs kapott gólok alapú erőviszony
        home_power = (hs.weighted_avg_goals_scored or hs.avg_goals_scored) - (
            aws.weighted_avg_goals_scored or aws.avg_goals_scored
        ) * 0.3
        away_power = (aws.weighted_avg_goals_scored or aws.avg_goals_scored) - (
            hs.weighted_avg_goals_scored or hs.avg_goals_scored
        ) * 0.3

        # Clean sheet / win to nil arányok
        home_def_bonus = hs.clean_sheet_rate * 0.2
        away_def_bonus = aws.clean_sheet_rate * 0.2

        home_score = max(0.1, home_power + home_def_bonus + 0.5)
        away_score = max(0.1, away_power + away_def_bonus + 0.5)

        total = home_score + away_score
        home_ratio = home_score / total
        away_ratio = away_score / total

        draw_prob = max(0.15, 0.28 - abs(home_ratio - away_ratio) * 0.3)
        home_win = home_ratio * (1.0 - draw_prob)
        away_win = away_ratio * (1.0 - draw_prob)

        total = home_win + draw_prob + away_win
        return home_win / total, draw_prob / total, away_win / total

    # === H2H Korrekciók ===

    def _h2h_goal_adjustment(
        self,
        exp_home: float,
        exp_away: float,
        h2h: HeadToHead,
    ) -> tuple[float, float]:
        """H2H finomhangolás a várható gólokra.

        Bővített: gólátlagok és dominancia alapú korrekció.
        Max ±15% korrekció több meccs alapján.
        """
        n = h2h.matches_played
        if n < 3:
            return exp_home, exp_away

        # Korrekció erőssége a meccsszámtól függ
        # 3 meccs: max ±8%, 5+: max ±12%, 10+: max ±15%
        max_adj = min(0.15, 0.05 + n * 0.01)

        # H2H gólátlagok vs aktuális várható
        if h2h.avg_home_goals > 0:
            h2h_home_ratio = h2h.avg_home_goals / max(0.5, (h2h.avg_home_goals + h2h.avg_away_goals) / 2)
            home_adj = 1.0 + (h2h_home_ratio - 1.0) * 0.3
        else:
            home_adj = 1.0

        if h2h.avg_away_goals > 0:
            h2h_away_ratio = h2h.avg_away_goals / max(0.5, (h2h.avg_home_goals + h2h.avg_away_goals) / 2)
            away_adj = 1.0 + (h2h_away_ratio - 1.0) * 0.3
        else:
            away_adj = 1.0

        # Dominancia korrekció
        dom = h2h.dominance_score  # -1 ... +1
        home_adj += dom * 0.05
        away_adj -= dom * 0.05

        # Clamp
        home_adj = max(1.0 - max_adj, min(1.0 + max_adj, home_adj))
        away_adj = max(1.0 - max_adj, min(1.0 + max_adj, away_adj))

        return exp_home * home_adj, exp_away * away_adj

    # === Mátrix alapú számítások ===

    def _calculate_1x2_from_matrix(self, pred: MatchPrediction):
        """1X2 valószínűségek a gól-mátrixból."""
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

        # Kombinált: két csapat súlyozott átlaga (hazai kissé nagyobb súly)
        if hs and aws:
            pred.combined_stat_over15 = hs.over15_rate * 0.55 + aws.over15_rate * 0.45
            pred.combined_stat_over25 = hs.over25_rate * 0.55 + aws.over25_rate * 0.45
            pred.combined_stat_over35 = hs.over35_rate * 0.55 + aws.over35_rate * 0.45

    # === Value Bet Elemzés ===

    def _find_value_bets(self, pred: MatchPrediction, odds: MatchOdds):
        """Value bet azonosítás - kalibrált valószínűségekből, szigorú szűrőkkel."""
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
            # Szigorú szűrők
            if market_odds < VALUE_BET_MIN_ODDS or market_odds > VALUE_BET_MAX_ODDS:
                continue
            if our_prob <= 0:
                continue

            implied_prob = 1.0 / market_odds
            edge = our_prob - implied_prob

            if edge > VALUE_BET_MIN_EDGE:
                ev = our_prob * market_odds - 1.0
                quality = 0.8 + pred.model_agreement * 0.2

                # Warning flag: magas edge de alacsony confidence
                warning = ""
                if edge > 0.15 and pred.betting_confidence < 0.50:
                    warning = "magas_edge_alacsony_conf"
                elif pred.model_agreement < 0.40:
                    warning = "gyenge_egyetertes"

                pred.value_bets.append({
                    "market": name,
                    "our_prob": our_prob,
                    "implied_prob": implied_prob,
                    "odds": market_odds,
                    "edge": edge,
                    "expected_value": ev,
                    "quality": quality,
                    "warning": warning,
                })

        pred.value_bets.sort(key=lambda x: x["edge"] * x.get("quality", 1.0), reverse=True)

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

    # === Konfidencia és Ajánlás ===

    def _calculate_confidence(self, pred: MatchPrediction):
        """Prediction confidence + Betting confidence külön számítás."""
        max_prob = max(pred.home_win_prob, pred.draw_prob, pred.away_win_prob)

        # === Prediction Confidence ===
        data_quality = 1.0
        if pred.home_stats:
            if pred.home_stats.matches_played < 5:
                data_quality *= 0.7
            elif pred.home_stats.matches_played < 10:
                data_quality *= 0.85
        if pred.away_stats:
            if pred.away_stats.matches_played < 5:
                data_quality *= 0.7
            elif pred.away_stats.matches_played < 10:
                data_quality *= 0.85

        agreement_factor = 0.85 + pred.model_agreement * 0.15

        consistency_factor = 1.0
        if pred.home_stats and pred.away_stats:
            avg_consistency = (
                pred.home_stats.scoring_consistency +
                pred.away_stats.scoring_consistency
            ) / 2
            if avg_consistency > 1.5:
                consistency_factor = 0.92

        pred.confidence = max_prob * data_quality * agreement_factor * consistency_factor

        # === Betting Confidence (szigorúbb) ===
        # A betting confidence figyelembe veszi hogy a piac ellen fogadunk-e
        betting_base = pred.confidence * 0.85  # Alapból konzervatívabb

        # Ha van odds adat, a piaci implied prob is számít
        if pred.match_odds and pred.match_odds.home_win > 0:
            # Mennyire tér el a modellünk a piactól
            market_home = 1.0 / pred.match_odds.home_win if pred.match_odds.home_win > 1 else 0.33
            market_away = 1.0 / pred.match_odds.away_win if pred.match_odds.away_win > 1 else 0.33
            model_diff = abs(pred.home_win_prob - market_home) + abs(pred.away_win_prob - market_away)
            # Ha nagyon eltérünk a piactól, csökkentjük a betting confidence-t
            market_penalty = max(0.7, 1.0 - model_diff * 0.5)
            betting_base *= market_penalty

        pred.betting_confidence = min(pred.confidence, betting_base)

        # Predikció minőség besorolás
        if pred.confidence >= 0.60 and pred.model_agreement >= 0.65:
            pred.prediction_quality = "magas"
        elif pred.confidence >= 0.45:
            pred.prediction_quality = "közepes"
        else:
            pred.prediction_quality = "alacsony"

    def _generate_recommendation(
        self, pred: MatchPrediction, odds: MatchOdds | None
    ):
        """Legjobb fogadási ajánlás + single bet ajánlások."""
        all_options = []

        # 1X2 opciók
        _1x2 = [
            ("1 (Hazai)", pred.home_win_prob, odds.home_win if odds else 0),
            ("X (Döntetlen)", pred.draw_prob, odds.draw if odds else 0),
            ("2 (Vendég)", pred.away_win_prob, odds.away_win if odds else 0),
        ]
        all_options.extend(_1x2)

        # O/U opciók
        if odds:
            for name, prob, o in [
                ("Over 2.5", pred.over25_prob, odds.over_25),
                ("Under 2.5", pred.under25_prob, odds.under_25),
                ("GG", pred.gg_prob, odds.gg),
                ("NG", pred.ng_prob, odds.ng),
            ]:
                if prob > 0.40 and o > 1.0:
                    all_options.append((name, prob, o))

        # Legjobb overall tipp
        if pred.value_bets:
            best = pred.value_bets[0]
            pred.recommended_bet = best["market"]
            pred.recommended_odds = best["odds"]
        elif pred.stat_value_bets:
            best = pred.stat_value_bets[0]
            pred.recommended_bet = best["market"]
            pred.recommended_odds = best["odds"]
        else:
            best = max(all_options, key=lambda x: x[1])
            pred.recommended_bet = best[0]
            pred.recommended_odds = best[2]

        # === Single Bet ajánlások ===
        # Best single: legmagasabb prob * odds score
        valid_singles = [(n, p, o) for n, p, o in all_options if o > 1.0]
        if valid_singles:
            # Legjobb single (legmagasabb valószínűség, biztonságos)
            best_single = max(valid_singles, key=lambda x: x[1])
            pred.best_single_bet = {
                "market": best_single[0],
                "prob": best_single[1],
                "odds": best_single[2],
                "ev": best_single[1] * best_single[2] - 1.0,
            }

            # Legjobb value single (legjobb EV)
            best_value = max(valid_singles, key=lambda x: x[1] * x[2] - 1.0)
            ev = best_value[1] * best_value[2] - 1.0
            if ev > 0:
                pred.best_value_single = {
                    "market": best_value[0],
                    "prob": best_value[1],
                    "odds": best_value[2],
                    "ev": ev,
                }
