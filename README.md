# TipMix Prediction System v2

Focimeccs-előrejelző rendszer **Sofascore** statisztikákra, **Poisson-modellre** és **The Odds API** oddsokra építve. Azonosítja a value bet lehetőségeket, ahol a tényleges statisztikai esély magasabb, mint amit a fogadóiroda odds tükröz.

## Telepítés

```bash
# 1. Repó klónolása
git clone https://github.com/Peti352/Prediction.git
cd Prediction

# 2. Virtuális környezet létrehozása és aktiválása
python -m venv .venv
source .venv/bin/activate       # Mac / Linux
# .venv\Scripts\activate        # Windows

# 3. Függőségek telepítése
pip install -r requirements.txt

# 4. .env fájl létrehozása
cp .env.example .env
```

### Odds API kulcs beállítása (opcionális)

A rendszer Odds API kulcs nélkül is működik (Sofascore + Poisson), de oddsokkal együtt value beteket is azonosít.

1. Regisztrálj ingyenesen: https://the-odds-api.com/ (500 request/hó)
2. Szerkeszd a `.env` fájlt:
   ```
   ODDS_API_KEY=ide_a_kulcsod
   ```

---

## Használat

```bash
# Összes mai meccs (minden támogatott liga)
python src/main.py

# Csak egy liga
python src/main.py -c PL

# Részletes O/U analízis minden meccshez
python src/main.py -c SA --detailed

# Oddsok nélkül (csak Sofascore + Poisson)
python src/main.py --no-odds

# Elérhető ligák listázása
python src/main.py --list-competitions
```

### CLI paraméterek

| Paraméter | Rövid | Leírás |
|-----------|-------|--------|
| `--competition PL` | `-c PL` | Liga szűrés |
| `--detailed` | `-d` | Részletes predikció minden meccshez |
| `--no-odds` | | Odds lekérdezés kihagyása |
| `--list-competitions` | | Támogatott ligák listázása |

### Támogatott ligák

| Kód | Liga | Ország |
|-----|------|--------|
| `PL` | Premier League | Anglia |
| `BL1` | Bundesliga | Németország |
| `SA` | Serie A | Olaszország |
| `PD` | La Liga | Spanyolország |
| `FL1` | Ligue 1 | Franciaország |

---

## Mit csinál a rendszer?

### Adatgyűjtés
1. **Sofascore API** - Mai meccsek lekérdezése + mindkét csapat utolsó 10 meccsének statisztikái
2. **The Odds API** - Fogadóirodai oddsok (1X2, Over/Under, GG/NG)
3. **TippmixPro** - Fallback odds forrás, ha az Odds API nem elérhető

### Elemzés
- **Poisson-modell**: Várható gólszámból gól-mátrixot épít (8x8), ebből számolja az összes piac valószínűségét
- **Statisztikai O/U ráták**: A csapatok utolsó 10 meccsének tényleges Over/Under arányai
- **Value bet azonosítás**: Ha a számított valószínűség >5%-kal magasabb mint az odds implied probability-je

### Piacok (11 db)
| Piac | Leírás |
|------|--------|
| 1 / X / 2 | Hazai győzelem / Döntetlen / Vendég győzelem |
| Over/Under 1.5 | 2+ gól / 0-1 gól |
| Over/Under 2.5 | 3+ gól / 0-2 gól |
| Over/Under 3.5 | 4+ gól / 0-3 gól |
| GG / NG | Mindkét csapat szerez gólt / Nem |

### Kimenet
1. **Meccsek tábla** - 1X2, O/U 1.5/2.5/3.5, GG/NG valószínűségek
2. **O/U összehasonlító tábla** - Stat% vs Odds, ★ = value bet
3. **Szelvényjavaslatok** - 4 típus:
   - **Biztos szelvény** - Magas konfidencia, alacsony odds (tét: 1000 Ft)
   - **Value szelvény** - Poisson value betek (tét: 500 Ft)
   - **Stat Value szelvény** - Statisztikai O/U alapú value betek (tét: 500 Ft)
   - **Rizikós szelvény** - Magas odds, nagy potenciális nyeremény (tét: 300 Ft)
4. **Összefoglaló** - Value bet lehetőségek, magas konfidenciájú tippek száma

---

## Architektúra

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Sofascore API    │    │  The Odds API    │    │  TippmixPro      │
│  (meccsek+stat)   │    │  (oddsok, fő)    │    │  (oddsok, fb)    │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         └───────────┬───────────┴───────────────────────┘
                     ▼
          ┌──────────────────┐
          │  Fuzzy Match      │  ← Csapatnév párosítás (threshold: 0.65)
          │  + Data Merge     │
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │  Stats Engine     │  ← O/U 1.5/2.5/3.5 ráták, forma, erősség
          │  + Poisson Model  │  ← Gól-mátrix (8x8), 11 piac
          │  + Value Bet      │  ← stat% vs implied prob (5% edge)
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │  Ticket Generator │  ← 4 szelvénytípus
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │  Rich CLI Display │  ← Színes táblák, ★ value marker
          └──────────────────┘
```

### Projekt struktúra

```
Prediction/
├── .env.example              # API kulcs sablon
├── .gitignore
├── requirements.txt          # Python függőségek
├── PRD.md                    # Product Requirements Document
├── README.md                 # Ez a fájl
├── Agents/                   # AI Agent konfigurációk (fejlesztéshez)
│   ├── team.md
│   ├── coder.md / reviewer.md / architect.md / ...
│   └── Skills/
├── data/cache/               # API response cache (automatikus, gitignored)
└── src/
    ├── config.py             # Liga mapping, fuzzy match, beállítások
    ├── main.py               # CLI belépési pont, pipeline orchestráció
    ├── scrapers/
    │   ├── sofascore.py      # Sofascore API kliens
    │   ├── odds_api.py       # The Odds API kliens + MatchOdds/MatchEvent
    │   └── tippmixpro.py     # TippmixPro Selenium fallback
    ├── analysis/
    │   ├── stats.py          # TeamStats, O/U ráták, liga átlagok
    │   └── predictor.py      # Poisson motor, value bet azonosítás
    ├── display/
    │   └── cli.py            # Rich CLI táblák, O/U összehasonlítás
    └── ticket/
        └── generator.py      # Szelvénygenerátor (4 típus, 11 piac)
```

---

## Hogyan működik a Poisson-modell?

1. **Várható gólok kiszámítása** mindkét csapatnak:
   ```
   Hazai xG = hazai_támadóerő × vendég_védekezés_gyengeség × liga_hazai_átlag × forma_faktor
   ```
2. **Gól-mátrix építése** Poisson-eloszlással (0-7 gól mindkét oldalon = 8x8 mátrix)
3. **Valószínűségek kinyerése** a mátrixból:
   - 1X2: hazai gól > vendég / egyenlő / vendég > hazai cellák összege
   - O/U 2.5: cellák ahol i+j ≤ 2 (under) vs i+j > 2 (over)
   - GG: cellák ahol i > 0 ÉS j > 0
4. **Value bet**: ha `saját_valószínűség - (1 / odds) > 5%`

## Statisztikai O/U vs Poisson O/U

A rendszer kétféleképpen becsli az Over/Under valószínűségeket:

| Módszer | Alapja | Mikor jobb? |
|---------|--------|-------------|
| **Poisson** | Matematikai modell (várható gólok) | Ha a csapatok erőssége eltér a történelmi átlagtól |
| **Statisztikai** | Utolsó 10 meccs tényleges eredményei | Ha a csapat "stílusa" konzisztens (pl. mindig gólgazdag) |

A **Stat Value szelvény** akkor jelöl value betet, ha a statisztikai ráta (★) magasabb mint az odds implied probability-je.

---

## Fontos tudnivalók

### API limitek
- **Sofascore**: Nincs hivatalos API, 2 másodperc várakozás kérések között. Ha 403-at ad, `cloudscraper`-rel próbálja újra.
- **The Odds API**: Ingyenes tier = **500 request/hónap**. A rendszer 6 órás cache-t használ. Egy futtatás ~5-10 requestet használ (ligánként 1).
- **TippmixPro**: Csak fallback, ha az Odds API nem elérhető.

### Cache
- Az API válaszok a `data/cache/` mappában tárolódnak (6 óra TTL)
- Ugyanaz a lekérdezés 6 órán belül nem hív újra API-t
- Cache törlés: `rm -rf data/cache/*`

### Mikor nincs meccs?
- A rendszer a **mai napra** kér meccseket a Sofascore-ról
- Ha egy liga kóddal (`-c PL`) nincs ma meccs, üres eredményt ad - próbálj másik ligát
- Hétvégén általában minden ligában vannak meccsek

### Odds nélküli mód
Ha nincs Odds API kulcs vagy lejárt a havi limit:
- A rendszer **működik** odds nélkül is
- Poisson valószínűségek és statisztikai ráták megjelennek
- Value bet azonosítás NEM működik (nincs mihez hasonlítani)
- Szelvényjavaslatok becsült oddsokkal készülnek

### Pontosság
- A Poisson-modell egy **egyszerűsített statisztikai modell**, nem garantál nyereséget
- A value bet = ahol a modell szerint az esély jobb mint amit az odds tükröz
- Hosszú távon a value betek pozitív ROI-t céloznak, de rövid távon bármi történhet
- A rendszer **eszköz a döntéshozatalhoz**, nem pénznyomtató gép

---

## Frissítés

```bash
cd Prediction
git pull
pip install -r requirements.txt
```

---

## Tech stack

| Komponens | Technológia |
|-----------|-------------|
| Nyelv | Python 3.11+ |
| HTTP | requests + cloudscraper |
| Scraping | BeautifulSoup4 + Selenium |
| Matematika | NumPy + SciPy (Poisson) |
| CLI | Rich (táblák, színek, progress) |
| Konfig | python-dotenv |
