"""Szelvény generátor - fogadási szelvény összeállítás.

A predikciók alapján összeállítja a legjobb szelvényjavaslatokat:
- Biztos szelvény (alacsony odds, magas konfidencia)
- Value szelvény (Poisson value betek)
- Stat Value szelvény (statisztikai O/U alapú)
- Rizikós szelvény (magasabb odds, nagyobb nyeremény)
"""

from dataclasses import dataclass, field
from functools import reduce
from operator import mul

from src.analysis.predictor import MatchPrediction
from src.config import (
    MIN_CONFIDENCE,
    TICKET_MAX_MATCHES,
    TICKET_MIN_MATCHES,
    TICKET_RISKY_MIN_ODDS,
    TICKET_SAFE_MAX_ODDS,
)


@dataclass
class TicketEntry:
    """Egy tétel a szelvényen."""
    home_team: str
    away_team: str
    competition: str
    bet_type: str
    odds: float
    probability: float
    confidence: float
    edge: float = 0.0
    is_value_bet: bool = False


@dataclass
class Ticket:
    """Egy teljes szelvényjavaslat."""
    name: str
    entries: list[TicketEntry] = field(default_factory=list)
    total_odds: float = 1.0
    stake: int = 500
    potential_win: float = 0.0
    avg_confidence: float = 0.0
    ticket_probability: float = 0.0

    def calculate(self):
        """Szelvény értékek újraszámítása."""
        if not self.entries:
            return
        self.total_odds = reduce(mul, [e.odds for e in self.entries], 1.0)
        self.potential_win = self.stake * self.total_odds
        self.avg_confidence = sum(e.confidence for e in self.entries) / len(self.entries)
        self.ticket_probability = reduce(mul, [e.probability for e in self.entries], 1.0)


class TicketGenerator:
    """Szelvény összeállító motor."""

    def generate_tickets(
        self, predictions: list[MatchPrediction]
    ) -> list[Ticket]:
        """Szelvényjavaslatok generálása."""
        if not predictions:
            return []

        tickets = []

        # 1) Biztos szelvény
        safe = self._generate_safe_ticket(predictions)
        if safe and len(safe.entries) >= TICKET_MIN_MATCHES:
            tickets.append(safe)

        # 2) Value szelvény (Poisson)
        value = self._generate_value_ticket(predictions)
        if value and len(value.entries) >= TICKET_MIN_MATCHES:
            tickets.append(value)

        # 3) Stat Value szelvény (statisztikai O/U)
        stat_value = self._generate_stat_value_ticket(predictions)
        if stat_value and len(stat_value.entries) >= TICKET_MIN_MATCHES:
            tickets.append(stat_value)

        # 4) Rizikós szelvény
        risky = self._generate_risky_ticket(predictions)
        if risky and len(risky.entries) >= TICKET_MIN_MATCHES:
            tickets.append(risky)

        # Fallback
        if not tickets:
            fallback = self._generate_fallback_ticket(predictions)
            if fallback and fallback.entries:
                tickets.append(fallback)

        return tickets

    def _generate_safe_ticket(
        self, predictions: list[MatchPrediction]
    ) -> Ticket:
        """Biztos szelvény: magas konfidencia, alacsonyabb oddsok."""
        ticket = Ticket(name="Biztos szelvény", stake=1000)
        candidates = []

        for pred in predictions:
            entry = self._best_safe_entry(pred)
            if entry and entry.confidence >= MIN_CONFIDENCE + 0.10:
                candidates.append(entry)

        candidates.sort(key=lambda e: e.confidence, reverse=True)
        ticket.entries = candidates[:TICKET_MAX_MATCHES]
        ticket.calculate()
        return ticket

    def _generate_value_ticket(
        self, predictions: list[MatchPrediction]
    ) -> Ticket:
        """Value szelvény: Poisson value betek."""
        ticket = Ticket(name="Value szelvény", stake=500)
        candidates = []

        for pred in predictions:
            for vb in pred.value_bets:
                entry = TicketEntry(
                    home_team=pred.home_team,
                    away_team=pred.away_team,
                    competition=pred.competition,
                    bet_type=vb["market"],
                    odds=vb["odds"],
                    probability=vb["our_prob"],
                    confidence=pred.confidence,
                    edge=vb["edge"],
                    is_value_bet=True,
                )
                candidates.append(entry)

        candidates.sort(key=lambda e: e.edge, reverse=True)
        ticket.entries = candidates[:TICKET_MAX_MATCHES]
        ticket.calculate()
        return ticket

    def _generate_stat_value_ticket(
        self, predictions: list[MatchPrediction]
    ) -> Ticket:
        """Stat Value szelvény: statisztikai O/U alapú value betek."""
        ticket = Ticket(name="Stat Value szelvény", stake=500)
        candidates = []

        for pred in predictions:
            for svb in pred.stat_value_bets:
                entry = TicketEntry(
                    home_team=pred.home_team,
                    away_team=pred.away_team,
                    competition=pred.competition,
                    bet_type=svb["market"],
                    odds=svb["odds"],
                    probability=svb["stat_prob"],
                    confidence=pred.confidence,
                    edge=svb["edge"],
                    is_value_bet=True,
                )
                candidates.append(entry)

        candidates.sort(key=lambda e: e.edge, reverse=True)
        ticket.entries = candidates[:TICKET_MAX_MATCHES]
        ticket.calculate()
        return ticket

    def _generate_risky_ticket(
        self, predictions: list[MatchPrediction]
    ) -> Ticket:
        """Rizikós szelvény: magasabb oddsok."""
        ticket = Ticket(name="Rizikós szelvény", stake=300)
        candidates = []

        for pred in predictions:
            entry = self._best_risky_entry(pred)
            if entry:
                candidates.append(entry)

        candidates.sort(
            key=lambda e: e.probability * e.odds, reverse=True
        )
        ticket.entries = candidates[:TICKET_MAX_MATCHES]
        ticket.calculate()
        return ticket

    def _generate_fallback_ticket(
        self, predictions: list[MatchPrediction]
    ) -> Ticket:
        """Fallback szelvény."""
        ticket = Ticket(name="Vegyes szelvény", stake=500)
        candidates = []

        for pred in predictions:
            entry = self._best_overall_entry(pred)
            if entry:
                candidates.append(entry)

        candidates.sort(key=lambda e: e.confidence, reverse=True)
        ticket.entries = candidates[:TICKET_MAX_MATCHES]
        ticket.calculate()
        return ticket

    def _best_safe_entry(self, pred: MatchPrediction) -> TicketEntry | None:
        """Legjobb biztos tipp egy meccshez."""
        options = self._all_options(pred)
        safe = [
            o for o in options
            if o.probability >= MIN_CONFIDENCE
            and 1.01 < o.odds <= TICKET_SAFE_MAX_ODDS
        ]
        if not safe:
            safe = [o for o in options if o.probability >= MIN_CONFIDENCE + 0.15]
        return max(safe, key=lambda e: e.confidence, default=None)

    def _best_risky_entry(self, pred: MatchPrediction) -> TicketEntry | None:
        """Legjobb rizikós tipp egy meccshez."""
        options = self._all_options(pred)
        risky = [
            o for o in options
            if o.odds >= TICKET_RISKY_MIN_ODDS and o.probability >= 0.25
        ]
        if not risky:
            risky = [o for o in options if 0.25 <= o.probability <= 0.50]
        return max(risky, key=lambda e: e.probability * e.odds, default=None)

    def _best_overall_entry(self, pred: MatchPrediction) -> TicketEntry | None:
        """Legjobb általános tipp egy meccshez."""
        options = self._all_options(pred)
        valid = [o for o in options if o.probability > 0.40]
        return max(valid, key=lambda e: e.confidence, default=None)

    def _all_options(self, pred: MatchPrediction) -> list[TicketEntry]:
        """Összes fogadási opció egy meccshez (11 piac)."""
        options = []
        base = dict(
            home_team=pred.home_team,
            away_team=pred.away_team,
            competition=pred.competition,
        )
        odds = pred.match_odds

        # 1X2
        options.append(TicketEntry(
            **base,
            bet_type="1 (Hazai)",
            odds=odds.home_win if odds and odds.home_win > 1 else self._prob_to_odds(pred.home_win_prob),
            probability=pred.home_win_prob,
            confidence=pred.home_win_prob,
        ))
        options.append(TicketEntry(
            **base,
            bet_type="X (Döntetlen)",
            odds=odds.draw if odds and odds.draw > 1 else self._prob_to_odds(pred.draw_prob),
            probability=pred.draw_prob,
            confidence=pred.draw_prob * 0.9,
        ))
        options.append(TicketEntry(
            **base,
            bet_type="2 (Vendég)",
            odds=odds.away_win if odds and odds.away_win > 1 else self._prob_to_odds(pred.away_win_prob),
            probability=pred.away_win_prob,
            confidence=pred.away_win_prob,
        ))

        # Over/Under 1.5
        options.append(TicketEntry(
            **base,
            bet_type="Over 1.5",
            odds=odds.over_15 if odds and odds.over_15 > 1 else self._prob_to_odds(pred.over15_prob),
            probability=pred.over15_prob,
            confidence=pred.over15_prob,
        ))
        options.append(TicketEntry(
            **base,
            bet_type="Under 1.5",
            odds=odds.under_15 if odds and odds.under_15 > 1 else self._prob_to_odds(pred.under15_prob),
            probability=pred.under15_prob,
            confidence=pred.under15_prob,
        ))

        # Over/Under 2.5
        options.append(TicketEntry(
            **base,
            bet_type="Over 2.5",
            odds=odds.over_25 if odds and odds.over_25 > 1 else self._prob_to_odds(pred.over25_prob),
            probability=pred.over25_prob,
            confidence=pred.over25_prob,
        ))
        options.append(TicketEntry(
            **base,
            bet_type="Under 2.5",
            odds=odds.under_25 if odds and odds.under_25 > 1 else self._prob_to_odds(pred.under25_prob),
            probability=pred.under25_prob,
            confidence=pred.under25_prob,
        ))

        # Over/Under 3.5
        options.append(TicketEntry(
            **base,
            bet_type="Over 3.5",
            odds=odds.over_35 if odds and odds.over_35 > 1 else self._prob_to_odds(pred.over35_prob),
            probability=pred.over35_prob,
            confidence=pred.over35_prob,
        ))
        options.append(TicketEntry(
            **base,
            bet_type="Under 3.5",
            odds=odds.under_35 if odds and odds.under_35 > 1 else self._prob_to_odds(pred.under35_prob),
            probability=pred.under35_prob,
            confidence=pred.under35_prob,
        ))

        # GG/NG
        options.append(TicketEntry(
            **base,
            bet_type="GG",
            odds=odds.gg if odds and odds.gg > 1 else self._prob_to_odds(pred.gg_prob),
            probability=pred.gg_prob,
            confidence=pred.gg_prob,
        ))
        options.append(TicketEntry(
            **base,
            bet_type="NG",
            odds=odds.ng if odds and odds.ng > 1 else self._prob_to_odds(pred.ng_prob),
            probability=pred.ng_prob,
            confidence=pred.ng_prob,
        ))

        return options

    @staticmethod
    def _prob_to_odds(prob: float) -> float:
        """Valószínűségből becsült odds."""
        if prob > 0:
            return round(1.0 / prob, 2)
        return 2.0
