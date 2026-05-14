# Phase 1.3 — Q7 Nondeterminism Investigation

**Date:** 2026-05-10  
**HEAD:** ccac0a504b6dc15a54ece3dfa2b641d62e51f18b  
**Branch:** phase1-sudska-praksa  
**Scope:** Determine whether 30Q result 19✅/10⚠️/1❌ is deterministic.

---

## Pre-flight

```
git rev-parse HEAD  → ccac0a504b6dc15a54ece3dfa2b641d62e51f18b  ✓
git status --porcelain → only untracked files, no modified tracked files  ✓
```

---

## Per-Question Results Across 3 Runs

| Q | Topic | R1 (ccac0a5) | R2 | R3 |
|---|-------|-------------|----|----|
| 1 | Osnovna krađa | ✅ HIGH 0.655 Član 210 | ✅ HIGH 0.655 Član 210 | ✅ HIGH 0.655 Član 210 |
| 2 | Krađa vs razbojništvo | ⚠️ MEDIUM 0.520 Član 204 | ⚠️ MEDIUM 0.520 Član 204 | ⚠️ MEDIUM 0.520 Član 204 |
| 3 | Teška krađa | ✅ HIGH 0.662 Član 379 | ✅ HIGH 0.662 Član 379 | ✅ HIGH 0.662 Član 379 |
| 4 | Pronevera u službi | ⚠️ MEDIUM 0.590 Član 365 | ⚠️ MEDIUM 0.590 Član 365 | ⚠️ MEDIUM 0.590 Član 365 |
| 5 | Prevara iznad milion | ✅ HIGH 0.656 Član 208 | ✅ HIGH 0.656 Član 208 | ✅ HIGH 0.656 Član 208 |
| 6 | Uslovna osuda | ✅ HIGH 0.665 Član 67 | ✅ HIGH 0.665 Član 67 | ✅ HIGH 0.665 Član 67 |
| **7** | **Vožnja u pijanom** | **❌ HIGH 0.684 Član 56** | **❌ HIGH 0.684 Član 56** | **⚠️ MEDIUM 0.643 Član 512** |
| 8 | Nasilje u porodici | ✅ HIGH 0.708 Član 194 | ✅ HIGH 0.708 Član 194 | ✅ HIGH 0.708 Član 194 |
| 9 | Nužna odbrana | ✅ HIGH 0.741 Član 19 | ✅ HIGH 0.741 Član 19 | ✅ HIGH 0.741 Član 19 |
| 10 | Opojne droge | ✅ HIGH 0.710 Član 246a | ✅ HIGH 0.710 Član 246a | ✅ HIGH 0.710 Član 246a |
| 11 | Nematerijalna šteta | ✅ HIGH 0.701 Član 200 | ✅ HIGH 0.701 Član 200 | ✅ HIGH 0.701 Član 200 |
| 12 | Zastarelost | ✅ HIGH 0.668 Član 371 | ✅ HIGH 0.668 Član 371 | ✅ HIGH 0.668 Član 371 |
| 13 | Raskid ugovora | ✅ HIGH 0.684 Član 124 | ✅ HIGH 0.684 Član 124 | ✅ HIGH 0.684 Član 124 |
| 14 | Regres osiguravajuće | ✅ LOW 0.508 Član 69 | ✅ LOW 0.508 Član 69 | ✅ LOW 0.508 Član 69 |
| 15 | Novacija obligacije | ⚠️ MEDIUM 0.591 Član 348 | ⚠️ MEDIUM 0.591 Član 348 | ⚠️ MEDIUM 0.591 Član 348 |
| 16 | Otkazni rok | ✅ HIGH 0.697 Član 189 | ✅ HIGH 0.697 Član 189 | ✅ HIGH 0.697 Član 189 |
| 17 | Otpremnina | ⚠️ MEDIUM 0.642 Član 179 | ⚠️ MEDIUM 0.642 Član 179 | ⚠️ MEDIUM 0.642 Član 179 |
| 18 | Mobing | ⚠️ MEDIUM 0.589 Član 21 | ⚠️ MEDIUM 0.589 Član 21 | ⚠️ MEDIUM 0.589 Član 21 |
| 19 | Naknada za bolovanje | ✅ HIGH 0.683 Član 115 | ✅ HIGH 0.683 Član 115 | ✅ HIGH 0.683 Član 115 |
| 20 | Probni rad | ⚠️ MEDIUM 0.610 Član 36 | ⚠️ MEDIUM 0.610 Član 36 | ⚠️ MEDIUM 0.610 Član 36 |
| 21 | Razvod braka | ✅ HIGH 0.687 Član 40 | ✅ HIGH 0.687 Član 40 | ✅ HIGH 0.687 Član 40 |
| 22 | Izdržavanje deteta | ✅ HIGH 0.662 Član 160 | ✅ HIGH 0.662 Član 160 | ✅ HIGH 0.662 Član 160 |
| 23 | Zajednička svojina | ✅ HIGH 0.669 Član 171 | ✅ HIGH 0.669 Član 171 | ✅ HIGH 0.669 Član 171 |
| 24 | Usvojenje | ✅ HIGH 0.689 Član 311 | ✅ HIGH 0.689 Član 311 | ✅ HIGH 0.689 Član 311 |
| 25 | Nasledni red | ⚠️ MEDIUM 0.648 Član 8 | ⚠️ MEDIUM 0.648 Član 8 | ⚠️ MEDIUM 0.648 Član 8 |
| 26 | Rok za žalbu | ✅ HIGH 0.706 Član 446 | ✅ HIGH 0.706 Član 446 | ✅ HIGH 0.706 Član 446 |
| 27 | Revizija | ⚠️ MEDIUM 0.641 Član 420 | ⚠️ MEDIUM 0.641 Član 420 | ⚠️ MEDIUM 0.641 Član 420 |
| 28 | Virtuelna valuta | ✅ HIGH 0.807 Član 2 | ✅ HIGH 0.807 Član 2 | ✅ HIGH 0.807 Član 2 |
| 29 | Smart contract | ⚠️ MEDIUM 0.579 Član 2 | ⚠️ MEDIUM 0.579 Član 2 | ⚠️ MEDIUM 0.579 Član 2 |
| **30** | **Beneficium ordinis** | **⚠️ MEDIUM 0.636 Član 231** | **⚠️ MEDIUM 0.543 Član 409** | **⚠️ MEDIUM 0.643 Član 263** |

**Totals:**

| Run | ✅ | ⚠️ | ❌ |
|-----|-----|-----|-----|
| R1 (ccac0a5) | 19 | 10 | 1 |
| R2 | 19 | 10 | 1 |
| R3 | 19 | 11 | 0 |

---

## Verdict

**NON-DETERMINISTIC**

Two questions vary across the three runs:

1. **Q7** — status varies: ❌ (R1, R2) / ⚠️ (R3). Score and top_article both change.
2. **Q30** — status is stable ⚠️ across all runs, but score and top_article differ each run.
   All other 28 questions produce bit-identical status, score, and top_article in all three runs.

---

## Q7 Deep Analysis

### Question and ground truth

- **Question text (run_test_30q.py QUESTIONS[6]):** `"Kazna za vožnju u pijanom stanju?"`
- **Expected article:** `"289"` (KZ 289 — neispravno upravljanje vozilom pod dejstvom alkohola)
- **Expected law:** `"KZ"`

### Per-run Q7 results

| Run | Band | Score | top_article | cited_in_resp | Status |
|-----|------|-------|-------------|---------------|--------|
| R1 (ccac0a5) | HIGH | 0.6836 | Član 56 | ['53','53','295'] | ❌ |
| R2 | HIGH | 0.6836 | Član 56 | ['53','53','295'] | ❌ |
| R3 | MEDIUM | 0.643 | Član 512 | (not checked — MEDIUM path exits early) | ⚠️ |
| pre-Phase-1.3 baseline (q5fix_run1) | MEDIUM | 0.6426 | Član 512 | (MEDIUM) | ⚠️ |

### R2 Q7 full response snippet (500 chars)

```
[✓] STATUSNA POTVRDA: Doslovno citiran — član direktno pronađen u bazi zakona RS.

--- HIJERARHIJA IZVORA
Lex specialis: Krivični zakonik (KZ) ima prednost nad ZOO za ovu oblast.

--- PRAVNI ZAKLJUČAK
Postoji verovatan pravni osnov za izricanje kazne za vožnju u pijanom stanju prema
Krivičnom zakoniku (KZ) čl. 53 i čl. 295, uz ispunjenje zakonskih uslova.
Vrsta odgovornosti: krivična odgovornost
Šta podnosilac MORA dokazati — postojanje krivičnog dela vožnje pod uticajem alkohola i ugrožavanje j
```

### Raw top-3 Pinecone matches for Q7 (stable across all runs)

```
1. zakonik o krivicnom postupku · Član 512  (score: 0.6426)
2. zakonik o krivicnom postupku · Član 425a (score: 0.6387)
3. KZ                           · Član 53   (score: 0.6291)
```

KZ 289 is **not present** in the raw top-3. The correct article is semantically distant
from the colloquial query "vožnja u pijanom stanju" in the embedding space.

### How the baseline ⚠️ was classified — exact evaluator logic

From `run_test_30q.py _self_eval()`:

```python
if confidence == "MEDIUM":
    return "⚠️", f"MEDIUM: hedged odgovor | meta-član: {top_article} | očekivano: Član {exp_art}"
```

When Q7 `confidence == "MEDIUM"` (score < 0.65), the evaluator returns ⚠️ regardless of
which article was cited or how wrong it is. There is no article-match check for MEDIUM band.

When Q7 `confidence == "HIGH"` (score ≥ 0.65), the evaluator checks:

```python
art_m = re.search(r"(\d+[a-zA-Z]?)", top_article or "")
meta_art = art_m.group(1) if art_m else ""
cited_in_resp = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", response)
if exp_art == meta_art or exp_art in cited_in_resp:
    return "✅", ...
return "❌", ...
```

`exp_art = "289"` is neither the meta article (Član 56) nor in `cited_in_resp` (['53','53','295']).
→ **❌**.

The ⚠️/❌ flip is therefore determined entirely by whether `confidence == "MEDIUM"` or
`"HIGH"`, i.e. whether the zakon top score falls below or above the HIGH threshold (0.65).

### Root cause of the nondeterminism

The CRAG loop in `_jedan_retrieval_krug()` calls an LLM judge (stochastic) to decide
relevance for each doc. For Q7, the FIX1 intent decomposition generates sub-queries like
"koji zakon reguliše vozačku kaznu?" which retrieve **KZ 56** (ancillary penalty — driving
license revocation, score 0.6836). The CRAG judge sometimes accepts KZ 56 as relevant
(→ score stays 0.6836, HIGH, ❌) and sometimes rejects it (→ falls back to ZKP 512 at
0.643, MEDIUM, ⚠️).

The switch point is `CONFIDENCE_HIGH_THRESHOLD = 0.65`. KZ 56 sits at 0.6836 — safely
above 0.65 — so whenever CRAG keeps it, the band locks to HIGH. ZKP 512 sits at 0.643 —
safely below 0.65 — so whenever CRAG drops KZ 56, the band locks to MEDIUM.

**Phase 1.3 did not introduce this nondeterminism.** The pre-Phase-1.3 baseline run
(q5fix_run1) produced the same MEDIUM/⚠️ result (score 0.6426, Član 512) as R3. Phase 1.3
changes (praksa append in Faza 6) do not affect CRAG scoring or the confidence band
calculation — those complete before Faza 6 runs.

### Why KZ 289 is never retrieved

"Vožnja u pijanom stanju" is colloquial Serbian. KZ 289 ("Neispravno upravljanje vozilom
u saobraćaju") uses formal language and references "alkohol ili psihoaktivne supstance"
without the colloquial phrase. The embedding distance to "pijano stanje" is insufficient
to place KZ 289 in the top 10 Pinecone matches for this query.

**Fix recommendation (Phase 1.5):** Add a law-hint for KZ 289:
`"saobraćaj", "vožnja", "alkohol", "pijano"` → KZ 289 priority retrieval.

---

## Q30 Variance (Status-Stable, Score-Volatile)

Q30 "Šta je beneficium ordinis?" status is ⚠️ in all three runs (MEDIUM band), but
top_article and score vary because HyDE fallback is stochastic (CRAG first says "NOT
RELEVANT", then HyDE generates a hypothetical document and re-retrieves). HyDE output
is an LLM generation — different each run → different doc set → different top_article.

| Run | Score | top_article |
|-----|-------|-------------|
| R1 | 0.636 | Član 231 (ZN) |
| R2 | 0.543 | Član 409 (ZOO) |
| R3 | 0.643 | Član 263 (ZOO) |

Status stays ⚠️ in all cases because all scores are MEDIUM band (< 0.65). Not a
correctness concern; never affects the ✅/❌ counts.

---

## Summary

| Question | Varies? | Nature |
|----------|---------|--------|
| Q7 | **YES** — status ❌↔⚠️ | CRAG judge stochastically accepts/rejects KZ 56 at 0.6836 |
| Q30 | YES — score/article only, status stable ⚠️ | HyDE re-retrieval is stochastic |
| Q1–Q6, Q8–Q29 (excl. Q30) | NO | Fully deterministic across 3 runs |

The pipeline is **non-deterministic** due to two LLM-driven mechanisms — CRAG judge
and HyDE generation — neither of which is seeded. Only Q7's binary ❌/⚠️ status is
affected.

**New baseline for Phase 1.3:** 19✅ / (10–11)⚠️ / (0–1)❌, depending on CRAG luck
for Q7. The stable 28-question core is fully deterministic.

---

*Generated by investigation run — read-only analysis, no source modifications.*
