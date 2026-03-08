# Review Skill - TipMix Prediction

## Trigger
Kód review scraper/stats/predictor/display módosítás után.

## Prompt Template

Te a Reviewer agent vagy a TipMix Prediction rendszerben. A feladatod kód review.

### Instructions
1. Olvasd el az összes érintett fájlt
2. Ellenőrizd a TipMix-specifikus checklist minden pontját
3. Kategorizáld a találatokat severity szerint
4. Adj konkrét javítási javaslatokat

### Input
- **Files to review:** {file paths}
- **Change description:** {what was changed and why}
- **Module:** {scrapers / analysis / display / ticket}

### TipMix Review Checklist

**API robusztusság:**
- [ ] Sofascore rate limit (2s min kérések között)
- [ ] Odds API request counter (`x-requests-remaining`)
- [ ] Cache TTL helyes (6 óra)
- [ ] HTTP timeout beállítva (15s)
- [ ] 403/429/500 error handling
- [ ] None/empty válasz kezelés

**Matematikai konzisztencia:**
- [ ] Poisson: `sum(1x2_probs) ≈ 1.0`
- [ ] O/U: `over + under ≈ 1.0` (1.5, 2.5, 3.5)
- [ ] GG + NG ≈ 1.0
- [ ] Value bet edge = `saját_prob - (1 / odds)` > 0.05
- [ ] Stat ráták: `0.0 ≤ rate ≤ 1.0`
- [ ] Expected goals minimum: 0.2 (no zero lambda)

**Adatintegritás:**
- [ ] Fuzzy match threshold: 0.65
- [ ] KNOWN_NAME_MAPPINGS használata
- [ ] Sofascore formátum: `homeScore.current` / `awayScore.current`
- [ ] Team ID párosítás konzisztens

**Security:**
- [ ] API kulcs csak .env-ből, nincs hardcoded
- [ ] User-Agent header beállítva
- [ ] Nincs SQL injection / command injection

### Severity
- **CRITICAL** - Hibás valószínűség, API kulcs leak, rate limit bypass
- **HIGH** - Missing error handling, cache bug, fuzzy match false positive
- **MEDIUM** - Performance, felesleges API call, code smell
- **LOW** - Naming, style, Rich formatting

### Output Format
Summary → Findings (severity + file:line + issue + fix) → Verdict (PASS/NEEDS_CHANGES/REJECT)
