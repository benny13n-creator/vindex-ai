# Phase 2.4 — Suzana Proxy Test Report

**Date:** 11.05.2026
**Tester:** Benjamin Nađ (self-test)
**Test document:** Synthetic 20-article employment contract (Serbian, ekavica)
**Production commit:** b4d6337 (post-session-bug-fix)
**Final session ID:** `1d77d12ea4044d9297f48eb6521f6d45`
**Verdict:** 🟡 **NOT beta-gate ready** — 3/7 strict / 4/7 lenient PASS

---

## Executive Summary

Phase 2.4 ran a 7-question test battery against a realistic synthetic employment contract uploaded via the document pipeline (Phase 2.2). The contract intentionally contained ZR violations to validate detection capability.

**Top-line findings:**

- ✅ **Session bug discovered and fixed mid-test** — `validate_session` used zero-vector Pinecone query which returns 0 matches due to undefined cosine similarity on null vectors. Single-line patch (commit b4d6337) restored full functionality.
- ✅ **Article-aware chunker** detected all 20 ugovor articles flawlessly.
- ✅ **Doc-context gate bias** (Phase 2.3.1 hotfix) consistently boosted confidence to HIGH/MEDIUM.
- ✅ **Konkurentska klauzula detection (Q5)** is exemplar quality — exactly the lawyer-ready output the product needs.
- ❌ **Cross-domain hallucination (Q2)** — NDA question routed through Zakon o digitalnoj imovini, completely irrelevant for an employment contract.
- ❌ **Quantitative reasoning failure (Q3)** — missed annual prekovremeni cap (250h/year) by comparing only monthly figures.
- ❌ **Self-contradictory reasoning (Q4)** — cited rule "8–30 dana" then concluded that 15 dana violates minimum 8 dana (despite 15 > 8).

**Phase 2.5 hotfix required before beta gate.** Three system-prompt patches scoped (see separate Phase 2.5 plan).

---

## Test Setup

**Test document:** `ugovor_test.docx` generated programmatically by `phase_2_4.py` from an inline Python string. 20 articles covering full employment contract scope (probni rad, prekovremeni, plata, godišnji odmor, tajnost, konkurentska, otkazni rok, otpremnina, etc.).

**Intentional ZR violations embedded:**

- Član 13: konkurentska klauzula 3 godine (violates ZR 162 max 2 godine)
- Član 7: prekovremeni 32h/mesec → 384h/godina (violates ZR 53 max 250h/god)
- Član 16: otkazni rok 15 dana (within ZR 189 range 8–30, control case)

**Test environment:**

- Production: `vindex-ai.onrender.com` (Render free tier)
- Upload result: 21 chunks, mode `article_aware`, 20 article labels detected
- Run command: `python -X utf8 phase_2_4.py > rezultati.txt 2>&1`

---

## Mid-Test Discovery: Session Validation Bug

The first test run (session `59b96b6db85f441b8a710b9e1b8b3f7d`) experienced 404 errors on questions Q4–Q7 with response `"Sesija nije pronađena ili je istekla"` despite the session being only minutes old.

**Diagnostic via direct Pinecone query:**

- Namespace `tmp_<session_id>` existed with 21 vectors ✓
- `expires_at` metadata was in the future (24h TTL) ✓
- Zero-vector query (`vector=[0.0]*3072`) returned 0 matches ✗
- Non-zero vector query (`vector=[0.1]*3072`) returned 3 matches ✓

**Root cause:** `uploaded_doc/session.py:validate_session` used `vector=[0.0]*3072` as the probe vector. Pinecone uses cosine similarity by default, which is mathematically undefined for null vectors (division by zero norm). Pinecone returns 0 matches in this case. Q1–Q3 happened to succeed during a hot-cache window, but subsequent queries failed once the vectors transitioned out of that state.

**Fix:** Changed probe vector to `[0.1] * 3072`. Single-character change.

**Commit:** b4d6337 — *fix(session): validate_session koristio zero-vector koji Pinecone vraca prazno (cosine sim na nul vektoru je nedefinisana)*

**Post-fix retest:** All 7 questions returned 200 OK with full responses.

---

## Per-Question Analysis

### Q1 — Probni rad (ZR 36) ✅ PASS

**Question:** Da li je probni rad u ovom ugovoru u skladu sa članom 36 Zakona o radu?

**Confidence:** MEDIUM | **Top law match:** Član 601 ZOO (irrelevant retrieval)

**Agent verdict:** Probni rad 3 meseca + otkazni rok 5 dana je u skladu sa zakonom.

**Correctness:** ✅ Correct. 3 meseca < 6 meseci max (ZR 36). 5 dana otkazni rok = zakonski minimum.

**Issues:** Weak document citation. Agent references "ugovor predviđa" but doesn't use the standard `Korisnikov dokument, Član N` pattern that other questions use.

---

### Q2 — Klauzula tajnosti ❌ FAIL (CRITICAL)

**Question:** Postoji li klauzula o tajnosti i da li je u skladu sa zakonom?

**Confidence:** HIGH | **Top law match:** Član 17 ZZPL

**Agent verdict:** Output framed as digital asset services compliance — references Zakon o digitalnoj imovini Član 87 (poslovna tajna za kripto usluge), APML, NBS/KHoV nadzor, includes "compliance koraci" about identity verification for transactions ≥ 15.000 EUR.

**Correctness:** ❌ Completely off-topic. The agent treats employment NDA as if subject is a cryptocurrency service provider.

**Severity:** Critical — would catastrophically erode lawyer trust on first interaction. Pred Kikom je ovo death.

---

### Q3 — Prekovremeni rad (ZR 53) ❌ FAIL

**Question:** Šta ugovor predviđa za prekovremeni rad i da li je usklađen sa članom 53 ZR?

**Confidence:** MEDIUM | **Top law match:** Član 634 ZOO (irrelevant)

**Agent verdict:** "Ugovor predviđa 32 časa mesečno, što je u skladu sa članom 53 ZR."

**Correctness:** ❌ False. 32h/mes × 12 = 384h/god. ZR 53 annual cap is 250h. Agent only compared the weekly limit (8h/sed), missed annual cap entirely.

**Severity:** High — quantitative reasoning is core to legal analysis. Agent should flag this missed violation.

---

### Q4 — Otkazni rok (ZR 189) ❌ FAIL

**Question:** Da li otkazni rok u ovom ugovoru ispunjava minimum iz člana 189 ZR?

**Confidence:** HIGH | **Top law match:** Član 189 ZR (perfect retrieval)

**Agent verdict:** "Otkazni rok od 15 radnih dana NE ISPUNJAVA minimum iz člana 189 Zakona o radu... zakon propisuje da otkazni rok ne može biti kraći od osam niti duži od 30 dana."

**Correctness:** ❌ Self-contradictory. 15 days IS within the 8–30 range that agent itself cites. False positive on violation detection.

**Severity:** Critical — false positives are as damaging as false negatives in legal context. Lawyer relying on agent would flag a non-violation as a violation.

---

### Q5 — Konkurentska klauzula (ZR 162) ✅ PASS (EXEMPLAR)

**Question:** Postoji li konkurentska klauzula? Da li je vremenski ograničena u skladu sa članom 162 ZR?

**Confidence:** HIGH | **Top law match:** Član 162 ZR (perfect retrieval)

**Agent verdict:** *"U članu 13 korisnikovog dokumenta ugovorena konkurentska klauzula u trajanju od tri godine, što prelazi zakonski maksimum od dve godine [Zakon o radu, čl. 162, st. 1], postoji neusklađenost sa zakonom."*

**Correctness:** ✅ Perfect detection. Document citation, law citation, mathematical comparison, conclusion — all aligned.

**Notes:** This is the exemplar output. Every question should look like this. Used as North Star for Phase 2.5 acceptance criteria.

---

### Q6 — Otpremnina pri tehnološkom višku ✅ PASS

**Question:** Da li ugovor predviđa otpremninu pri tehnološkom višku?

**Confidence:** MEDIUM | **Top law match:** Član 811 ZOO (irrelevant), agent referenced ZR 158 correctly

**Agent verdict:** "Prema članu 17 korisnikovog dokumenta, zaposleni ima pravo na otpremninu u skladu sa Zakonom o radu."

**Correctness:** ✅ Correct. Document citation present, conclusion accurate.

**Notes:** Less rigorous than Q5 — doesn't verify ZR 158's actual otpremnina formula, just confirms existence of clause.

---

### Q7 — Nepovoljnije klauzule od ZR minimuma ⚠️ SOFT FAIL

**Question:** Postoji li bilo koja klauzula koja je nepovoljnija za zaposlenog od minimuma iz ZR?

**Confidence:** HIGH | **Top law match:** Član 191 ZR (somewhat relevant)

**Agent verdict:** Provides legal framework (ZR Član 9 ništavost) but doesn't enumerate concrete violations found in the document.

**Correctness:** ⚠️ Incomplete. The document has multiple potential violations (3-year konkurentska, no time limit on tajnost, 32h/mes prekovremeni) — agent had access via doc context but didn't perform the application.

**Severity:** Medium — agent provided correct legal framework but didn't apply it to the actual document. Lawyer would have to do the application manually.

---

## Scoring Summary

| # | Topic | Confidence | Grade |
|---|-------|------------|-------|
| Q1 | Probni rad ZR 36 | MEDIUM | ✅ PASS (weak citation) |
| Q2 | Klauzula tajnosti | HIGH | ❌ FAIL (cross-domain hallucination) |
| Q3 | Prekovremeni rad ZR 53 | MEDIUM | ❌ FAIL (missed annual cap) |
| Q4 | Otkazni rok ZR 189 | HIGH | ❌ FAIL (self-contradictory) |
| Q5 | Konkurentska ZR 162 | HIGH | ✅ PASS (exemplar) |
| Q6 | Otpremnina | MEDIUM | ✅ PASS |
| Q7 | Nepovoljnije klauzule | HIGH | ⚠️ SOFT FAIL (framework only) |

**Strict scoring:** 3/7 PASS (43%)
**Lenient scoring:** 4/7 PASS (57%)
**Beta-gate threshold:** 6/7 PASS minimum

---

## What's Working

1. **Document chunking** (Phase 2.1) — 100% reliable on real-world contract. All 20 articles detected with `article_aware` mode.
2. **Document retrieval** (Phase 2.3) — Doc passages correctly returned for every question.
3. **Gate bias** (Phase 2.3.1) — Confidence properly elevated when doc context present (Q2, Q4, Q5, Q7 all HIGH).
4. **ZR retrieval** — Q4, Q5, Q7 found correct ZR articles as top hits.
5. **Document citation pattern** — Q5, Q6 use "Korisnikov dokument, Član N" format correctly.
6. **Specific violation detection** — Q5 perfectly detects 3-year konkurentska klauzula violation with full reasoning chain. This is the gold standard.

---

## Issues for Phase 2.5

### Issue 1: Cross-domain hallucination (CRITICAL priority)

Agent routes questions to wrong legal framework when retrieval finds semantically related but contextually irrelevant law (e.g., NDA → Zakon o digitalnoj imovini for "poslovna tajna" keyword overlap).

### Issue 2: Quantitative reasoning failure (HIGH priority)

Agent doesn't perform unit conversion when ZR limits exist in multiple time units (weekly + monthly + annual). Only compares to most obvious unit.

### Issue 3: Self-contradictory reasoning (HIGH priority)

Agent cites legal rule with numeric range, then draws conclusion that contradicts the cited rule mathematically. No internal consistency validation.

### Issue 4: Citation inconsistency (MEDIUM priority)

Some questions use "Korisnikov dokument, Član N" format (Q5, Q6); others reference document informally (Q1). Inconsistent pattern.

---

## Next Steps

1. **Phase 2.5 hotfix** — system prompt augmentation addressing Issues 1–4. See `docs/phase-2-5-prompt-hardening-plan.md` for detailed plan.
2. **Re-run Phase 2.4 test** — same script, same questions, target ≥ 6/7 PASS.
3. **Decision gate** — if target met, beta access opens (Kika receives invitation).
4. **Known limitation deferred:** OCR not supported for scanned PDFs. User's real (scanned) contract not testable until OCR phase (post-beta).

---

## Appendix: Reproducibility

**Test script:** `phase_2_4.py` (in `legal-agent/` root, currently gitignored)
**Test document:** synthetic, generated inline in script (4621 chars, 20 articles)
**Final session ID:** `1d77d12ea4044d9297f48eb6521f6d45`
**Production commit at time of test:** b4d6337

To reproduce:

```
python -X utf8 phase_2_4.py > rezultati.txt 2>&1
```

Expected output: upload OK (21 chunks, 20 articles detected), then 7 question/answer pairs.
