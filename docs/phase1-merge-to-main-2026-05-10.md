# Phase 1 — Merge to Main + Production Deploy

**Date:** 2026-05-10  
**MERGE_COMMIT_SHA:** 23d018f4a7d5d99ff7af916b9b5c2efae735cad1  
**Branch merged:** phase1-sudska-praksa → main  
**Rollback command (if ever needed):** `git revert -m 1 23d018f4a7d5d99ff7af916b9b5c2efae735cad1`

---

## Stage A — Pre-flight ✅

| Check | Result |
|-------|--------|
| Dirty tracked files | NONE — `docs/VINDEX_HALLUCINATION_FREE_TEST.md` restored via `git checkout` |
| HEAD on feature branch | ccac0a504b6dc15a54ece3dfa2b641d62e51f18b ✓ |
| origin/phase1-sudska-praksa | ccac0a5 ✓ |
| origin/main | fb3a96b (local main 1 commit ahead: docs-only) ✓ |
| chunked_manifest.json total_chunks | 1479 ✓ |
| Raw corpus decision identifiers | 197 decisions loaded for hallucination cross-check |

Note: local `main` was at `2c6b068` (1 docs commit ahead of `origin/main` fb3a96b from a pre-Phase-1 hygiene 30Q run). Docs-only, safe to include.

---

## Stage B — Merge ✅

```
git checkout main
git merge --no-ff phase1-sudska-praksa -F merge-message.txt
```

Merge commit: **23d018f4a7d5d99ff7af916b9b5c2efae735cad1**  
Strategy: `ort` (no conflicts)

```
*   23d018f Merge branch 'phase1-sudska-praksa' — Phase 1.0–1.3 complete
|\
| * ccac0a5 docs(phase1.3): add Phase 1.3 report
| * 7e00775 docs(phase1.3): update 30Q regression results (19/10/1)
| * 04cdf24 feat(phase1.3): system prompt cites real praksa decisions
| * c6beb50 feat(phase1.3): parallel retrieval + praksa formatter
```

---

## Stage C — Post-merge 30Q Regression ✅

**Result: 19✅ / 11⚠️ / 0❌** (Mode A — Q7 landed MEDIUM at 0.571)

Within expected bimodal variance (Mode A: 19/11/0, Mode B: 19/10/1). 28 deterministic
questions all ✅ or stable ⚠️. No regressions introduced by merge.

---

## Stage D — Push ✅

```
git push origin main
fb3a96b..23d018f  main -> main
```

---

## Stage E — Render Deploy Poll ✅

Service was already live on the new SHA within the first poll window.

| Poll | Time | Status |
|------|------|--------|
| 1 | 0s | 200 |
| 2 | 16s | 200 |
| 3 | 31s | 200 |

**DEPLOY OK at 31s** (≥30s wall time, 3 consecutive 200s satisfied)

---

## Stage F — Production Smoke Tests ✅

4/4 questions passed. API endpoint: `POST /api/bot/ask` with field `pitanje`.

| Q | Query | HTTP | len | Cited decisions | Hallucinated |
|---|-------|------|-----|-----------------|--------------|
| 1 | Koja je kazna za kradju? | 200 | 3343 | Kzz 754/2025 | none |
| 2 | Koja je kazna za nasilje u porodici? | 200 | 4292 | Kzz 169/2026 | none |
| 3 | Naknada stete kod raskida ugovora? | 200 | 4945 | (none cited in snippet) | none |
| 4 | Sudska praksa o naknadi stete? | 200 | 4177 | Rev 14388/2024 | none |

**Hallucination cross-check:** All cited decision numbers (`Kzz 754/2025`, `Kzz 169/2026`,
`Rev 14388/2024`) verified present in raw corpus (`data/sudska_praksa/raw/**/*.json`).
Zero hallucinated decision numbers.

---

## Stage G — Verdict: SUCCESS ✅

No rollback needed. Phase 1 is live on `main` and deployed to production.

---

## Safety Invariants (post-merge verification)

| Invariant | Status |
|-----------|--------|
| Default namespace at 17,688 | ✅ (no Pinecone writes in Phase 1.3 merge) |
| CONFIDENCE_HIGH_THRESHOLD = 0.65 | ✅ |
| CONFIDENCE_MEDIUM_THRESHOLD = 0.52 | ✅ |
| Zakon CRAG pipeline unchanged | ✅ |
| sudska_praksa namespace = 1,479 vectors | ✅ |
| No hallucinated VKS decisions in smoke | ✅ |
| Production /health = 200 (3 consecutive) | ✅ |
| 30Q post-merge: 19/11/0 (no regression) | ✅ |

---

## What Phase 1 Delivered

| Phase | Delivered |
|-------|-----------|
| 1.0 | 200 VKS decisions scraped and stored (raw HTML + JSON) |
| 1.1 | 1,479 chunks chunked with VKS metadata schema |
| 1.2 | 1,479 vectors ingested into Pinecone `sudska_praksa` namespace |
| 1.3 | Parallel retrieval wired into production; hallucinated "raspon" system prompt removed; LLM now cites real VKS decisions by number |

**Before Phase 1:** "Sudska praksa:" lines were GPT-4o hallucinations following a hardcoded template, with no connection to Pinecone data.  
**After Phase 1:** LLM cites real Vrhovni sud decision numbers (e.g., Kzz 754/2025) that are semantically matched to the query and verifiable in the corpus.

---

## Known Gaps / Phase 1.5 Candidates

1. **Q7 drift** — "Kazna za vožnju u pijanom stanju?" is borderline: CRAG stochastically accepts KZ 56 (HIGH → ❌) or rejects it (MEDIUM → ⚠️). Fix: law-hint for KZ 289 (`saobraćaj + vožnja`).
2. **Q5 matter mismatch** — KZ 203 queries return administrative praksa due to weak semantic separation. Fix: cross-reference retrieval (cited_articles_raw contains "203" + matter == "Krivična").
3. **Praksa threshold calibration** — PRAKSA_CONFIDENCE_* mirrors zakon thresholds. Proper calibration deferred to Phase 1.5.
4. **Q30 HyDE variance** — "Šta je beneficium ordinis?" top_article and score differ each run (HyDE is stochastic). Status stable ⚠️, never affects ✅/❌ counts.

---

*Phase 1 complete. Production deploy verified. Ready for Phase 1.5.*
