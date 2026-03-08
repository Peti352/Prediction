# Product Requirements Document (PRD)

## Project Name
TipMix Prediction System v2

## Version
v2.0

## Date
2026-03-08

---

## 1. Overview

Focimeccs-előrejelző rendszer, amely **Sofascore** statisztikákra, **Poisson-modellre** és **The Odds API** oddsokra építve azonosít value bet lehetőségeket. A fókusz az **Over/Under 1.5 / 2.5 / 3.5** piacok statisztikai összehasonlítása a fogadóirodai oddsokkal, kiegészítve 1X2 és GG/NG predikcióval.

## 2. Problem Statement

A fogadók többsége megérzés alapján tipppel, nem használ statisztikai modellt. A meglévő predikciós eszközök vagy túl egyszerűek (csak 1X2), vagy drágák. A rendszer ingyenes adatforrásokból (Sofascore, The Odds API free tier) épít fel egy Poisson-alapú modellt, amely a statisztikai valószínűséget összeveti a bookmaker oddsokkal, és kiemeli a value bet lehetőségeket - ahol a tényleges esély magasabb, mint amit az odds tükröz.

## 3. Goals & Objectives

- [x] Sofascore API integráció (mai meccsek + csapat utolsó 10 meccs)
- [x] The Odds API integráció (1X2, O/U 1.5/2.5/3.5 oddsok)
- [x] TippmixPro fallback scraper
- [x] Poisson-modell O/U 1.5, 2.5, 3.5 valószínűségekkel
- [x] Statisztikai O/U ráták (tényleges meccs történetből)
- [x] Value bet azonosítás 11 piacon (stat% vs implied prob)
- [x] O/U összehasonlító tábla (stat% vs odds, ★ jelölés)
- [x] 4 szelvénytípus: Biztos, Value, Stat Value, Rizikós
- [ ] Telegram bot értesítések value betekről
- [ ] Historikus teljesítmény tracking (ROI mérés)
- [ ] Több liga támogatása (Eredivisie, Championship, CL)

## 4. Target Audience

- Sportfogadók, akik adatvezérelt döntéseket akarnak hozni
- Tippmix/TippmixPro felhasználók
- Hobbi statisztikusok, akik érdeklődnek a Poisson-modell iránt

## 5. Functional Requirements

### 5.1 Core Features

| Feature | Description | Priority | Status |
|---------|-------------|----------|--------|
| Sofascore meccsek | Mai meccsek lekérdezése 5 ligából | P0 | Done |
| Sofascore csapat statisztikák | Utolsó 10 meccs, gólok, H/V bontás | P0 | Done |
| Odds API integráció | 1X2 + O/U totals oddsok | P0 | Done |
| Fuzzy team matching | Sofascore ↔ Odds API csapatnév párosítás | P0 | Done |
| Poisson O/U 1.5/2.5/3.5 | Gól-mátrixból számított valószínűségek | P0 | Done |
| Statisztikai O/U ráták | Tényleges meccs történetből számított %-ok | P0 | Done |
| Value bet azonosítás | 11 piac: stat% vs odds implied prob | P0 | Done |
| O/U összehasonlító tábla | Stat% vs Odds, ★ value marker | P0 | Done |
| Szelvénygenerátor | Biztos, Value, Stat Value, Rizikós | P0 | Done |
| TippmixPro fallback | Selenium scraper backup odds forrás | P1 | Done |
| Liga szűrés CLI | `-c PL` / `-c SA` stb. | P1 | Done |
| Részletes nézet | `--detailed` Poisson vs Stat vs Odds analízis | P1 | Done |
| Cache rendszer | 6 óra TTL, MD5 hash alapú fájl cache | P1 | Done |
| Telegram bot | Value bet értesítések | P2 | Planned |
| ROI tracking | Historikus teljesítmény mérés | P2 | Planned |

### 5.2 User Stories

- Mint fogadó, szeretném látni a mai meccsek O/U statisztikáit, hogy tudjam melyik meccsen érdemes Over/Under-re fogadni.
- Mint fogadó, szeretném összehasonlítani a tényleges statisztikai valószínűséget a bookmaker oddsokkal, hogy megtaláljam a value beteket.
- Mint fogadó, szeretnék szelvényjavaslatokat kapni (biztos/value/rizikós), hogy ne kelljen egyenként elemezni minden meccset.
- Mint fogadó, szeretném egy paranccsal lekérni egy liga összes meccsét predikciókkal.

## 6. Non-Functional Requirements

- **Performance:** Max 2 perc 30+ meccs teljes elemzése (Sofascore rate limit: 2s/request)
- **API takarékosság:** Odds API 500 req/hó - 6 óra cache TTL, liga szintű lekérdezés
- **Robusztusság:** Sofascore 403 → cloudscraper fallback; Odds API unavailable → TippmixPro fallback; minden forrás fail → Poisson only mód
- **Offline mód:** Cache-elt adatokkal 6 órán belül offline futtatható
- **Karbantarthatóság:** Moduláris architektúra, minden adatforrás cserélhető

## 7. Technical Architecture

### 7.1 Tech Stack

- **Nyelv:** Python 3.11+
- **HTTP:** requests + cloudscraper (Sofascore 403 bypass)
- **Scraping:** BeautifulSoup4 + Selenium (TippmixPro fallback)
- **Matematika:** NumPy + SciPy (Poisson eloszlás)
- **CLI:** Rich (táblázatok, színkódolás, progress bar)
- **Konfig:** python-dotenv (.env fájl)

### 7.2 System Diagram

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Sofascore API    │    │  The Odds API    │    │  TippmixPro      │
│  (meccsek+stat)   │    │  (oddsok, fő)    │    │  (oddsok, fb)    │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         └───────────┬───────────┴───────────────────────┘
                     ▼
          ┌──────────────────┐
          │  Fuzzy Match +    │  ← difflib.SequenceMatcher (0.65 threshold)
          │  Data Merge       │  ← KNOWN_NAME_MAPPINGS fallback
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │  Stats Engine     │  ← TeamStats (O/U 1.5/2.5/3.5, GG, forma)
          │  + Poisson Model  │  ← Gól-mátrix (8x8), 11 piac
          │  + Value Bet      │  ← stat% vs implied prob (5% edge)
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │  Ticket Generator │  ← 4 szelvénytípus
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │  Rich CLI Display │  ← O/U tábla, ★ value marker
          └──────────────────┘
```

## 8. Data Model

### Fő Dataclass-ok

```
TeamStats
├── team_name, team_id, competition_code
├── matches_played, wins/draws/losses, form_string
├── goals_scored/conceded, avg_goals_scored/conceded
├── home_*/away_* (bontás)
├── attack_strength, defense_strength (liga átlaghoz képest)
├── over15_rate, over25_rate, over35_rate
├── gg_rate, clean_sheet_rate
└── match_goals_history: list[int]

MatchOdds
├── home_win, draw, away_win
├── over_15/under_15, over_25/under_25, over_35/under_35
├── gg, ng
└── bookmaker

MatchEvent
├── home_team, away_team, home_team_id, away_team_id
├── kickoff, competition, league_code
├── sofascore_event_id
└── odds: MatchOdds

MatchPrediction
├── 1X2 probs (Poisson)
├── O/U 1.5/2.5/3.5 probs (Poisson)
├── combined_stat_over15/25/35 (tényleges %)
├── value_bets: list[dict]
├── stat_value_bets: list[dict]
├── confidence, recommended_bet
└── home_stats, away_stats, match_odds
```

## 9. CLI Interface

| Parancs | Leírás |
|---------|--------|
| `python src/main.py` | Összes liga, mai meccsek |
| `python src/main.py -c PL` | Csak Premier League |
| `python src/main.py -c SA --detailed` | Serie A, részletes O/U analízis |
| `python src/main.py --no-odds` | Oddsok nélkül (csak Poisson) |
| `python src/main.py --list-competitions` | Elérhető ligák listázása |

### Támogatott ligák

| Kód | Liga | Sofascore ID | Odds API key |
|-----|------|-------------|--------------|
| PL | Premier League | 17 | soccer_epl |
| BL1 | Bundesliga | 35 | soccer_germany_bundesliga |
| SA | Serie A | 23 | soccer_italy_serie_a |
| PD | La Liga | 8 | soccer_spain_la_liga |
| FL1 | Ligue 1 | 34 | soccer_france_ligue_one |

## 10. Projekt struktúra

```
TIPMIX PREDICTION/
├── .env                          # ODDS_API_KEY
├── requirements.txt              # Python függőségek
├── PRD.md                        # Ez a dokumentum
├── Agents/                       # AI Agent konfigurációk
│   ├── team.md                   # Csapat áttekintés
│   ├── coder.md / reviewer.md / ...
│   └── Skills/                   # Skill prompt template-ek
├── data/cache/                   # API response cache (6h TTL)
└── src/
    ├── config.py                 # Liga mapping, fuzzy match, beállítások
    ├── main.py                   # CLI belépési pont, workflow orchestráció
    ├── scrapers/
    │   ├── sofascore.py          # Sofascore API kliens
    │   ├── odds_api.py           # The Odds API kliens + dataclass-ok
    │   └── tippmixpro.py         # TippmixPro Selenium fallback
    ├── analysis/
    │   ├── stats.py              # TeamStats, O/U ráták, liga átlagok
    │   └── predictor.py          # Poisson motor, value bet azonosítás
    ├── display/
    │   └── cli.py                # Rich CLI táblák, O/U összehasonlítás
    └── ticket/
        └── generator.py          # Szelvénygenerátor (4 típus, 11 piac)
```

## 11. Success Metrics

- **Value bet hit rate:** Value betként jelölt tippek hány %-a nyer (cél: >55%)
- **ROI:** Hosszú távú befektetés megtérülés a value bet szelvényeken (cél: pozitív)
- **Lefedettség:** Mai meccsek hány %-ánál sikerül odds párosítás (cél: >80%)
- **Futási idő:** Teljes pipeline < 3 perc 30 meccsre

## 12. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Sofascore API 403 blokkolás | High | Medium | cloudscraper fallback, User-Agent rotáció |
| Odds API 500 req/hó limit | Medium | High | 6h cache, liga szintű lekérdezés (nem meccs szintű) |
| Csapatnév eltérés (fuzzy fail) | Medium | Medium | KNOWN_NAME_MAPPINGS dict + 0.65 threshold |
| TippmixPro oldal változás | Low | High | Többféle CSS selector, API endpoint próba |
| Sofascore API struktúra változás | High | Low | Defensív JSON parsing, fallback default értékek |
| Poisson modell pontatlansága | Medium | Medium | Stat O/U ráták mint második vélemény |

## 13. Jövőbeli fejlesztések

- [ ] Telegram bot: automatikus value bet értesítések
- [ ] Historikus tracking: predikciók vs tényleges eredmények mentése
- [ ] ROI dashboard: havi/heti teljesítmény kimutatás
- [ ] Több liga: Eredivisie, Championship, Champions League, Conference League
- [ ] xG (Expected Goals) integráció Sofascore-ból
- [ ] Sérülés/hiányzó játékos figyelembevétele
- [ ] Asian Handicap piac támogatás
- [ ] Web UI (Streamlit vagy FastAPI + React)
- [ ] Multi-bookmaker odds összehasonlítás (legjobb odds keresés)

---

*TipMix Prediction System v2 - Sofascore + Odds API + Poisson*
