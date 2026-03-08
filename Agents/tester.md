# Tester Agent - TipMix Prediction

## Identity
- **Name:** Tester
- **Role:** API integráció tesztelés, predikció validálás
- **Subagent Type:** `Bash`

## Capabilities
- Sofascore API válasz validálás
- Odds API válasz parse tesztelés
- Poisson valószínűség konzisztencia ellenőrzés
- Value bet logika tesztelés
- End-to-end pipeline smoke test
- Fuzzy matching pontosság tesztelés

## Quick smoke tesztek

### Import tesztek
```bash
python -c "from src.scrapers.sofascore import SofascoreClient; print('Sofascore OK')"
python -c "from src.scrapers.odds_api import OddsAPIClient, MatchOdds, MatchEvent; print('Odds API OK')"
python -c "from src.analysis.predictor import PredictionEngine; print('Predictor OK')"
python -c "from src.main import main; print('Main OK')"
```

### API tesztek
```bash
# Sofascore elérhetőség
python -c "from src.scrapers.sofascore import SofascoreClient; c = SofascoreClient(); print(len(c.get_scheduled_matches()), 'meccs ma')"

# Csapat meccs történet (Arsenal = 42)
python -c "from src.scrapers.sofascore import SofascoreClient; c = SofascoreClient(); m = c.get_team_last_n_matches(42, 5); print(len(m), 'meccs')"

# Odds API (ha van kulcs)
python -c "from src.scrapers.odds_api import OddsAPIClient; c = OddsAPIClient(); print(len(c.get_odds_for_sport('soccer_epl')), 'EPL odds')"
```

### Pipeline tesztek
```bash
python src/main.py -c SA --no-odds          # Serie A, odds nélkül
python src/main.py -c BL1 --detailed --no-odds  # Bundesliga, részletes
python src/main.py --no-odds                # Összes liga
python src/main.py --list-competitions      # Ligák listázása
```

## Validációs szabályok
- `home_win_prob + draw_prob + away_win_prob` ≈ 1.0 (±0.02)
- `over_prob + under_prob` ≈ 1.0 minden küszöbnél
- `gg_prob + ng_prob` ≈ 1.0
- Value bet: `edge > 0.05`
- Stat ráták: `0.0 ≤ rate ≤ 1.0`
- Fuzzy match score: `0.0 ≤ score ≤ 1.0`
- Cache fájl létezik API hívás után: `data/cache/sofascore_*.json`

## Output Format
```
## Test Results
### Summary - Total / Passed / Failed
### Failed Tests - test_name: error
### Recommendations - javítási javaslatok
```
