# P0.2 Verification — 30Q Deterministic Re-Run

**Run date:** 2026-05-10
**Branch:** main
**Commit (HEAD):** b96d12829a1870d903759fb828a6ef2436c67494
**Expected commit:** b96d128
**Mode:** READ-ONLY verification
**Prior:** Run 1 = 19✅/11⚠️/0❌ (2026-05-07, commit b96d128)

---

## Pre-flight

- HEAD = b96d12829a1870d903759fb828a6ef2436c67494 → match: **YES**
- Working tree clean: **PARTIAL** — `.claude/scheduled_tasks.lock` (scheduler metadata, not code) and `docs/VINDEX_HALLUCINATION_FREE_TEST.md` (docs) modified; all untracked are result/diagnostic `.txt` and `docs/` files; **no production code modified** → accepted, consistent with Run 1 pre-flight
- PINECONE_HOST: `https://vindex-ai-t8z679r.svc.aped-4627-b74a.pinecone.io`
- PINECONE_INDEX_NAME: `vindex-ai`
- Pinecone vector count: **17,688** (expected 17,688) ✓
- OpenAI sanity probe: **OK** (dim=3072, text-embedding-3-large)

---

## Run 2

- Started: ~2026-05-10T10:43:42
- Finished: 2026-05-10T10:51:19
- Wall time: ~457s (~7m 37s)
- Totals: **19✅ / 11⚠️ / 0❌**

| Q# | Status | Band | Top-1 source | Time (s) |
|----|--------|------|--------------|----------|
| Q01 | ✅ | HIGH | KZ / Član 210 | 22.9 |
| Q02 | ⚠️ | MEDIUM | KZ / Član 204 | 20.0 |
| Q03 | ✅ | HIGH | KZ / Član 379 | 15.4 |
| Q04 | ⚠️ | MEDIUM | KZ / Član 365 | 13.1 |
| Q05 | ✅ | HIGH | KZ / Član 208 | 16.9 |
| Q06 | ✅ | HIGH | ZR / Član 67 | 13.9 |
| Q07 | ⚠️ | MEDIUM | ZBS / Član 512 | 16.3 |
| Q08 | ✅ | HIGH | KZ / Član 194 | 19.9 |
| Q09 | ✅ | HIGH | KZ / Član 19 | 13.1 |
| Q10 | ✅ | HIGH | KZ / Član 246a | 15.6 |
| Q11 | ✅ | HIGH | ZOO / Član 200 | 20.8 |
| Q12 | ✅ | HIGH | ZOO / Član 371 | 13.7 |
| Q13 | ✅ | HIGH | ZOO / Član 124 | 14.0 |
| Q14 | ✅ | LOW | ZR / Član 69 | 9.9 |
| Q15 | ⚠️ | MEDIUM | ZOO / Član 348 | 11.6 |
| Q16 | ✅ | HIGH | ZR / Član 189 | 14.2 |
| Q17 | ⚠️ | MEDIUM | ZR / Član 179 | 13.0 |
| Q18 | ⚠️ | MEDIUM | ZR / Član 197 | 15.0 |
| Q19 | ✅ | HIGH | ZR / Član 115 | 22.2 |
| Q20 | ⚠️ | MEDIUM | ZR / Član 36 | 12.8 |
| Q21 | ✅ | HIGH | PZ / Član 40 | 12.5 |
| Q22 | ✅ | HIGH | PZ / Član 160 | 12.9 |
| Q23 | ✅ | HIGH | PZ / Član 171 | 10.7 |
| Q24 | ✅ | HIGH | PZ / Član 311 | 12.2 |
| Q25 | ⚠️ | MEDIUM | ZN / Član 8 | 13.0 |
| Q26 | ✅ | HIGH | ZPP / Član 446 | 10.6 |
| Q27 | ⚠️ | MEDIUM | ZPP / Član 420 | 18.1 |
| Q28 | ✅ | HIGH | ZDI / Član 2 | 13.8 |
| Q29 | ⚠️ | MEDIUM | ZDI / Član 2 | 12.5 |
| Q30 | ⚠️ | MEDIUM | ZOO / Član 162 | 11.1 |

---

## Run 3

- Started: ~2026-05-10T10:52:53
- Finished: 2026-05-10T11:00:30
- Wall time: ~457s (~7m 37s)
- Totals: **19✅ / 11⚠️ / 0❌**

| Q# | Status | Band | Top-1 source | Time (s) |
|----|--------|------|--------------|----------|
| Q01 | ✅ | HIGH | KZ / Član 210 | 16.7 |
| Q02 | ⚠️ | MEDIUM | KZ / Član 204 | 18.5 |
| Q03 | ✅ | HIGH | KZ / Član 379 | 14.2 |
| Q04 | ⚠️ | MEDIUM | KZ / Član 365 | 14.6 |
| Q05 | ✅ | HIGH | KZ / Član 208 | 19.3 |
| Q06 | ✅ | HIGH | ZR / Član 67 | 15.5 |
| Q07 | ⚠️ | MEDIUM | ZBS / Član 512 | 15.6 |
| Q08 | ✅ | HIGH | KZ / Član 194 | 24.8 |
| Q09 | ✅ | HIGH | KZ / Član 19 | 10.7 |
| Q10 | ✅ | HIGH | KZ / Član 246a | 15.5 |
| Q11 | ✅ | HIGH | ZOO / Član 200 | 22.9 |
| Q12 | ✅ | HIGH | ZOO / Član 371 | 18.2 |
| Q13 | ✅ | HIGH | ZOO / Član 124 | 12.8 |
| Q14 | ✅ | LOW | ZR / Član 69 | 9.0 |
| Q15 | ⚠️ | MEDIUM | ZOO / Član 348 | 10.1 |
| Q16 | ✅ | HIGH | ZR / Član 189 | 16.9 |
| Q17 | ⚠️ | MEDIUM | ZR / Član 179 | 13.1 |
| Q18 | ⚠️ | MEDIUM | ZR / Član 21 | 12.4 |
| Q19 | ✅ | HIGH | ZR / Član 115 | 16.6 |
| Q20 | ⚠️ | MEDIUM | ZR / Član 36 | 11.7 |
| Q21 | ✅ | HIGH | PZ / Član 40 | 11.5 |
| Q22 | ✅ | HIGH | PZ / Član 160 | 14.6 |
| Q23 | ✅ | HIGH | PZ / Član 171 | 9.7 |
| Q24 | ✅ | HIGH | PZ / Član 311 | 11.1 |
| Q25 | ⚠️ | MEDIUM | ZN / Član 8 | 12.1 |
| Q26 | ✅ | HIGH | ZPP / Član 446 | 10.3 |
| Q27 | ⚠️ | MEDIUM | ZPP / Član 420 | 19.3 |
| Q28 | ✅ | HIGH | ZDI / Član 2 | 14.2 |
| Q29 | ⚠️ | MEDIUM | ZDI / Član 2 | 15.9 |
| Q30 | ⚠️ | MEDIUM | ZOO / Član 134 | 13.9 |

---

## Determinism Matrix (Run 1 vs Run 2 vs Run 3)

| Q# | R1 status | R2 status | R3 status | R1 band | R2 band | R3 band | Match |
|----|-----------|-----------|-----------|---------|---------|---------|-------|
| Q01 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q02 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q03 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q04 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q05 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q06 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q07 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q08 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q09 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q10 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q11 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q12 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q13 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q14 | ✅ | ✅ | ✅ | LOW | LOW | LOW | ✓ |
| Q15 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q16 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q17 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q18 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ † |
| Q19 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q20 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q21 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q22 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q23 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q24 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q25 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q26 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q27 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q28 | ✅ | ✅ | ✅ | HIGH | HIGH | HIGH | ✓ |
| Q29 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ |
| Q30 | ⚠️ | ⚠️ | ⚠️ | MEDIUM | MEDIUM | MEDIUM | ✓ † |

† Article varies within ⚠️ MEDIUM band — status and band are stable, top-1 article drifts between plausible ZR/ZOO candidates (expected stochastic behaviour for mobing/beneficium-ordinis edge queries with no expected article enforced).

**Divergent questions (status or band change):** none

---

## Final Verdict

- Run 2 = 19✅/11⚠️/0❌ ? **YES**
- Run 3 = 19✅/11⚠️/0❌ ? **YES**
- Status determinism (R1=R2=R3 for all 30 Q) ? **YES**
- Band determinism (R1=R2=R3 for all 30 Q) ? **YES**
- **P0.2 VERIFIED: YES**

---

## Notes

**Q05 (prevara / KZ 208):** Fully deterministic across all 3 runs — HIGH, score=0.656, Član 208 every time. The semantic expansion + `_izracunaj_skor` +80 boost + post-Cohere override are all firing consistently.

**Q18 (mobing):** Top-1 article alternates between Član 197 (R2) and Član 21 (R1, R3). No expected article is enforced for Q18 (`exp_art=None`), so both are scored as ⚠️ MEDIUM regardless. Status stable.

**Q30 (beneficium ordinis):** Top-1 article alternates between Član 162 (R2) and Član 134 (R1, R3). Both are ZOO MEDIUM — correct hedge behaviour. Status stable.

**Latency:** All questions completed in 9–25s range. No outliers (no question >25s). Both runs completed in ~457s wall time. Q08 (nasilje u porodici) was the slowest at 19.9s / 24.8s across runs — likely a longer LLM response for this multi-part question.

**OpenAI quota:** No 429 / quota errors in either run. Stable throughout.

**Pinecone:** 17,688 vectors confirmed exact match to expected count.

---

## OpenAI Cost

~$0.70–$1.00 total for both runs (60 questions × ~3,500 input tokens + ~300 output tokens at GPT-4o pricing; embedding cost negligible).

---

## Next Action

P0.2 is verified. Proceed to prod push (P0.4) or next fix batch:
1. **Q7 hint** — KZ 289 vs KZ 512 stochastic ⚠️ ("Kazna za vožnju u pijanom stanju?") — candidate for next targeted hint
2. **FIX-7 port** — `analyze_documents()` from `multi_query_rag.py` into production pipeline
3. **FIX-3 port** — pass `sub_queries` as `combined_query` to `_cohere_rerank()`
4. **Dead code cleanup** — delete `multi_query_rag.py` + `example_multi_rag.py`
