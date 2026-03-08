# TipMix Prediction - AI Agent Team

## Overview

Specializált AI ágensek csapata a TipMix Prediction System v2 fejlesztéséhez és karbantartásához. Minden ágens a sport-predikciós domain kontextusában dolgozik.

## Team Members

| Agent | Role | Subagent Type | Skill | Fókusz terület |
|-------|------|---------------|-------|----------------|
| **Researcher** | API kutatás, liga adatok | `Explore` / `general-purpose` | `research-skill.md` | Sofascore/Odds API endpointok, liga ID-k |
| **Coder** | Implementáció, bugfix | `general-purpose` | `code-skill.md` | Scraperek, Poisson modell, stats |
| **Reviewer** | Kód review, QA | `general-purpose` | `review-skill.md` | API robusztusság, edge case-ek |
| **Architect** | Rendszertervezés | `Plan` | `architect-skill.md` | Pipeline design, adatfolyam |
| **Tester** | Tesztelés, validáció | `Bash` | `test-skill.md` | API integráció, predikció pontosság |
| **DocWriter** | Dokumentáció | `general-purpose` | `docwriter-skill.md` | PRD, README, API docs |

## Projekt kontextus

### Tech stack
- Python 3.11+, requests, cloudscraper, BeautifulSoup4, Selenium
- NumPy, SciPy (Poisson), Rich (CLI)
- Sofascore API, The Odds API, TippmixPro scraping

### Fő modulok
```
src/
├── config.py              # Liga mapping, fuzzy match, beállítások
├── main.py                # Pipeline orchestráció
├── scrapers/
│   ├── sofascore.py       # Sofascore API kliens
│   ├── odds_api.py        # The Odds API kliens + dataclass-ok
│   └── tippmixpro.py      # TippmixPro Selenium fallback
├── analysis/
│   ├── stats.py           # TeamStats, O/U ráták, liga átlagok
│   └── predictor.py       # Poisson motor, value bet azonosítás
├── display/
│   └── cli.py             # Rich CLI táblák, O/U összehasonlítás
└── ticket/
    └── generator.py       # Szelvénygenerátor (4 típus, 11 piac)
```

### Kritikus korlátok
- Sofascore rate limit: 2s/request, 403 → cloudscraper fallback
- Odds API: 500 req/hó limit, 6h cache TTL
- Fuzzy matching threshold: 0.65 (csapatnév párosítás)
- Poisson gól-mátrix: 8x8 (max 7 gól)

## Delegation Protocol

1. Feladat beérkezése
2. Domain azonosítás (scraper / stats / display / config)
3. Megfelelő agent(ek) kiválasztása
4. Párhuzamos delegálás ahol lehetséges
5. Eredmények szintézis és visszajelzés

## Parallel Execution Rules

- **Researcher + Architect** → párhuzamosítható (API kutatás + design)
- **Coder** → szekvenciális (scraper → stats → predictor → display)
- **Tester** → Coder után (API válasz validálás, predikció ellenőrzés)
- **Reviewer** → Coder után (rate limit, error handling, edge case-ek)
- **DocWriter** → párhuzamosítható a Testerrel
