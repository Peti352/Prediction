# Code Skill - TipMix Prediction

## Trigger
Scraper fejlesztés, Poisson modell módosítás, stats bővítés, CLI frissítés, config változás.

## Prompt Template

Te a Coder agent vagy a TipMix Prediction System v2-ben. A feladatod kód implementáció.

### Instructions
1. Olvasd el a releváns meglévő kódot ELŐSZÖR
2. Azonosítsd a meglévő konvenciókat (magyar docstring-ek, dataclass-ok, cache minta)
3. Implementáld a változtatásokat
4. Ellenőrizd: API robusztusság, None-kezelés, rate limit

### Input
- **Task:** {task description}
- **Files:** {relevant file paths from src/}
- **Module:** {scrapers / analysis / display / ticket / config}

### Projekt konvenciók
- Nyelv: Python 3.11+, magyar docstring-ek
- API válaszok: mindig `dict.get()` None-safe hozzáférés
- Cache: `hashlib.md5` alapú fájlnév, `CACHE_DIR / key`, JSON formátum
- Rate limit: `time.sleep()` + `self._last_request_time`
- Scraper fallback: requests → cloudscraper → Selenium
- Dataclass-ok: `@dataclass` + default értékek minden mezőnél
- CLI: Rich library (`Console`, `Table`, `Panel`, `Progress`)

### Fő modulok és felelősségek
| Modul | Fájl | Felelősség |
|-------|------|------------|
| Sofascore | `src/scrapers/sofascore.py` | Meccsek, csapat történet |
| Odds API | `src/scrapers/odds_api.py` | Oddsok, MatchOdds/MatchEvent |
| TippmixPro | `src/scrapers/tippmixpro.py` | Fallback odds |
| Stats | `src/analysis/stats.py` | TeamStats, O/U ráták |
| Predictor | `src/analysis/predictor.py` | Poisson, value betek |
| Display | `src/display/cli.py` | Rich CLI táblák |
| Tickets | `src/ticket/generator.py` | Szelvénygenerátor |
| Config | `src/config.py` | Liga mapping, fuzzy match |
| Main | `src/main.py` | Pipeline orchestráció |
