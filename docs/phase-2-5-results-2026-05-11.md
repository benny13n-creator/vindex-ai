# Phase 2.5 Results — Prompt Hardening
**Datum:** 2026-05-11  
**Deploy SHA:** 4bfd0b9  
**Tests:** 64/64 pass  
**30Q:** 20/8/2 (baseline maintained)  
**Verdict:** ❌ NEEDS-ITERATE (4/7 PASS, target ≥ 6/7)

---

## Per-pitanje gradacija (Q1–Q7)

| Q | Pitanje | Faza 2.4 | Faza 2.5 | Napomena |
|---|---------|----------|----------|----------|
| Q1 | Probni rad (ZR čl. 36) | FAIL | **PASS** | Tačan zaključak (3m ≤ 6m). Citiranje dokumenta i dalje neformalno ("U korisnikovom dokumentu") umesto "Korisnikov dokument, Član N" |
| Q2 | Tajnost/NDA | FAIL | **FAIL** | I dalje citira ZDI čl. 87. Patch 1 (domain constraint) se verovatno injektovao, ali ga GPT-4o ignorisao jer je zakon retrieval vratio ZDI sa score 0.6101 (HIGH) |
| Q3 | Prekovremeni (ZR čl. 53) | FAIL | **FAIL** | Nema 32×12=384>250 konverzije. Retrieval vratio ZR 53 tekst koji sadrži samo 8h/ned i 32h/mes limite; godišnji cap od 250h/god nije u retrieved tekstu |
| Q4 | Otkazni rok (ZR čl. 189) | FAIL | **FAIL** | Konflikt jedinica: "15 radnih dana je kraći od minimuma 8 kalendarskih dana" — model meša radne i kalendarske dane, vodi do pogrešnog zaključka |
| Q5 | Konkurentska klauzula | PASS | **PASS** | Tačno: 3 god > 2 god ZR čl. 162 limit |
| Q6 | Otpremnina | PASS | **PASS** | Tačno. Koristio "Korisnikov dokument, Član 17" format — Patch 4 deluje za ovaj slučaj |
| Q7 | Nepovoljniji uslovi | PASS | **PASS** | Tačno identifikuje problemove |

**Ukupno:** 4/7 PASS (pre: 3-4/7) — **BETA-GATE NIJE PROŠAO**

---

## Analiza neuspelih patch-eva

### Patch 1 (domain constraint) — delimično efektivan
- Problem: LLM ignorisao constraint "NE ANALIZIRAJ kroz ZDI" kada je retrieval vratio ZDI čl. 87 sa HIGH score-om
- Root cause: Retrieval-level bug — zakon retrieval vraća ZDI za "tajnost" pitanja bez obzira na tip dokumenta
- Fix: Retrieval-level filter ili re-ranking koji za employment contract kontekst deprioritizuje ZDI
- Napomena: Patch 1 radi za slučajeve gde retrieval NE vraća pogrešan zakon

### Patch 2 (kvantitativna provera) — neefektivan za Q3
- Problem: Retrieved ZR čl. 53 tekst sadrži samo "8h/ned i 32h/mes" — bez godišnjeg cap-a od 250h
- Root cause: Chunking/retrieval ne vraća ceo ZR 53 (više paragrafa); godišnji limit je u zasebnom chunku koji nije retrieved
- Fix: Retrieval fix (ensure multi-paragraph articles are retrieved together) ili proširiti query da eksplicitno traži "godišnji limit prekovremeni"

### Patch 3 (contradiction guard) — neefektivan za Q4
- Problem: Q4 sadrži "radnih dana" vs "kalendarskih dana" — model pokušava da konvertuje jedinice i greši
- Root cause: ZR čl. 189 kaže "8 dana" (kalendarskih), ugovor kaže "15 radnih dana"; model ne zna da je 15 radnih ≈ 21 kalendarskih > 8 → zapravo compliant, ali pravi grešku u poređenju
- Fix: Dodate instrukcije za normalizaciju jedinica pre poređenja; ili eksplicitno navesti da "radnih dana" > "kalendarskih dana" za isti broj

### Patch 4 (citation format) — delimično efektivan
- Q6: Koristio "Korisnikov dokument, Član 17" ✓
- Q1: I dalje "U korisnikovom dokumentu" ✗ (MEDIUM confidence → drugi flow)
- Q5/Q7: Nisu direktno citirali doc (analizirali zakon) → nije primenljivo

---

## Šta radi

1. **Patch 4** funkcioniše za HIGH confidence odgovore koji direktno citiraju dokument (Q6)
2. **Patch 2/3 logika** bila bi ispravna kada bi retrieval doneo pravi zakonski tekst
3. **30Q baseline** sačuvan (20/8/2) — svi patch-evi su doc-context only
4. **64/64 unit tests** prolaze

---

## Preporučeni follow-up (iteracija)

**P1 (visok prioritet) — Q2 fix:**
Retrieval-level: za employment contract kontekst, filtrirati ili re-rankovati ZDI matches dole. Alternativa: post-processing filter koji zamenjuje ZDI čl. 87 citiranja u employment contract kontekstu sa ZR/ZOO odgovorima.

**P2 (visok prioritet) — Q4 fix:**
Dopuniti Patch 3 instrukcije:
```
Kada se poredi broj u "radnim danima" sa zakonskim opsegom u "kalendarskim danima":
KONVERTUJ: 1 radni dan = 1 kalendarski dan (konzervativno); ne pokušavaj konverziju.
ILI: Navedi eksplicitno "15 radnih dana > 8 dana (min) → u opsegu."
```

**P3 (srednji prioritet) — Q3 fix:**
Proširiti query za prekovremeni da uključi "godišnji limit" ili "250 sati" u multi-query expansion. Alternativa: dodati ZR 53 (svi paragrafi) kao LAW_HINT sa godišnjim cap-om.

---

## Deploy informacije

- Commit SHA: 4bfd0b9
- Branch: main
- Deploy: Render auto-deploy
- Testovi: 64/64 pass (11 novih unit testova)
