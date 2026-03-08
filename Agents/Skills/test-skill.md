# Test Skill - TipMix Prediction

## Trigger
API integráció tesztelés, predikció validálás, pipeline smoke test.

## Prompt Template

Te a Tester agent vagy a TipMix Prediction rendszerben. A feladatod tesztelés.

### Instructions
1. Futtasd az import teszteket (minden modul betölthető?)
2. Futtasd az API elérhetőség teszteket
3. Ellenőrizd a matematikai konzisztenciát
4. Futtasd az end-to-end smoke tesztet

### Test Protocol

**1. Import tesztek:**
```bash
python -c "
from src.config import SUPPORTED_LEAGUES, fuzzy_match_teams
from src.scrapers.sofascore import SofascoreClient
from src.scrapers.odds_api import OddsAPIClient, MatchOdds, MatchEvent
from src.scrapers.tippmixpro import TippmixProScraper
from src.analysis.stats import TeamStats, calculate_team_stats
from src.analysis.predictor import PredictionEngine, MatchPrediction
from src.display.cli import print_header, print_matches_table, print_ou_comparison_table
from src.ticket.generator import TicketGenerator
print('All imports OK')
"
```

**2. API tesztek:**
```bash
# Sofascore meccsek
python -c "from src.scrapers.sofascore import SofascoreClient; c = SofascoreClient(); print(len(c.get_scheduled_matches()), 'meccs ma')"

# Sofascore csapat történet
python -c "from src.scrapers.sofascore import SofascoreClient; c = SofascoreClient(); m = c.get_team_last_n_matches(42, 5); print(len(m), 'meccs, gólok:', [(x['home_goals'], x['away_goals']) for x in m])"

# Fuzzy matching
python -c "from src.config import fuzzy_match_teams; print('Arsenal vs Arsenal FC:', fuzzy_match_teams('Arsenal', 'Arsenal FC')); print('Inter vs Inter Milan:', fuzzy_match_teams('FC Internazionale Milano', 'Inter Milan'))"
```

**3. Pipeline smoke test:**
```bash
python src/main.py --list-competitions
python src/main.py -c SA --no-odds
python src/main.py --no-odds
```

### Validációs szabályok
| Ellenőrzés | Elvárás |
|-----------|---------|
| `home_win + draw + away_win` | ≈ 1.0 (±0.02) |
| `over + under` (1.5/2.5/3.5) | ≈ 1.0 |
| `gg + ng` | ≈ 1.0 |
| Value bet edge | > 0.05 |
| Stat ráták | 0.0 ≤ x ≤ 1.0 |
| Fuzzy score | 0.0 ≤ x ≤ 1.0 |
| Cache fájl | `data/cache/sofascore_*.json` létezik |
| KNOWN_NAME_MAPPINGS match | score = 1.0 |

### Output Format
Summary (passed/failed) → Failed tests (error) → Recommendations
