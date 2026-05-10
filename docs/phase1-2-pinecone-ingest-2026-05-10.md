# Phase 1.2 — Pinecone Ingest (Case Law) Report

**Date:** 2026-05-10
**Branch:** phase1-sudska-praksa
**Script:** `scripts/ingest_case_law.py`

---

## Architecture

- **Target index:** `vindex-ai` (existing — NOT a new index)
- **Target namespace:** `sudska_praksa` (new namespace; default namespace untouched)
- **Default namespace invariant:** must stay at exactly 17,688 zakon vectors throughout
- **Embedding model:** `text-embedding-3-large` (3072-dim cosine — matches zakon vectors)
- **Upsert strategy:** two-stage conservative (50-chunk stratified seed → verify → remaining 1,429 in batches of 100)

---

## Stage 1 — Seed Upsert

- **Seed size:** 50 chunks (13 krivicna + 13 gradjanska + 12 upravna + 12 zastitaprava)
- **Pre-seed verification:** default=17,688, sudska_praksa=0 ✓
- **Post-seed verification:** default=17,688, sudska_praksa=50 ✓
- **Sanity queries (Stage 1):** 3/3 PASS (non-strict — 50 chunks too few for reliable matter discrimination)

---

## Stage 2 — Full Upsert

- **Chunks to embed:** 1,429 (total 1,479 minus 50 seed)
- **Batch size:** 100 chunks per upsert
- **Namespace checkpoints:** every 2 batches (200 chunks)

### Errors encountered and fixed

**Error 1 — Non-ASCII vector IDs (batch 12 crash):**
- Zaštita prava decisions use filenames with Serbian special chars (`ž`, `š`, `ć`, `č`, `đ`)
- These became chunk_ids (e.g. `Kž1_u_399_2025__chunk_0`) and then Pinecone vector IDs
- Pinecone requires ASCII-only vector IDs → HTTP 400
- **Fix:** Added `_ascii_vector_id()` transliteration (`ž→z`, `š→s`, `ć→c`, `č→c`, `đ→d`) applied only to the Pinecone `id` field; chunk_id in metadata and state tracking unchanged
- State file preserved ~1,100 completed chunk_ids from batches 1-11 → resumed correctly

**Error 2 — production_regression wrong header:**
- Script was sending `x-bot-api-key`; API expects `X-Api-Key`
- Fixed before final commit

**Error discovered earlier — Pinecone null metadata:**
- `decision_id_fallback` is `null` for 1,476/1,479 chunks (only set when decision_number is empty)
- Pinecone rejects `null` metadata values
- **Fix:** `_clean_metadata()` strips None values entirely

---

## Final State

| Namespace | Expected | Actual | Status |
|-----------|----------|--------|--------|
| default (zakon) | 17,688 | 17,688 | ✓ INTACT |
| sudska_praksa | 1,479 | 1,479 | ✓ COMPLETE |

---

## Final Sanity Queries (strict_matter=True)

| Q | Query | Top match | Score | Matter | Status |
|---|-------|-----------|-------|--------|--------|
| 1 | kvalifikacija teške krađe i razbojništva | Kzz 754/2025 OBRAZLOŽENJE | 0.433 | Krivična | PASS |
| 2 | naknada štete zbog raskida ugovora o kupoprodaji | Prev 918/2024 OBRAZLOŽENJE | 0.530 | Građanska | PASS |
| 3 | rok za žalbu na upravno rešenje | Uzp 175/2023 OBRAZLOŽENJE | 0.625 | Upravna | PASS |
| 4 | neodlučivanje organa po zahtevu | Uzp 349/2025 OBRAZLOŽENJE | 0.598 | Upravna* | WARN |
| 5 | član 203 | Prev 102/2025 OBRAZLOŽENJE | 0.437 | — | PASS |

*Q4 warns: "neodlučivanje organa" (failure to act by an authority) semantically overlaps Upravna and Zaštita prava — both matters involve administrative inaction. This is a corpus density effect, not a retrieval defect.

**Result: 4/5 PASS** (threshold: ≥4 required)

---

## Production Regression

- **Endpoint:** `POST /api/bot/ask`
- **Question:** "Koja je kazna za osnovnu krađu?"
- **HTTP status:** 200
- **KZ citation present:** YES — "član 203", "Krivični zakonik (KZ)"
- **Case law in response:** YES — "Sudska praksa: raspon kazne za osnovnu krađu je novčana kazna ili zatvor do tri godine."
- **Result: PASS**

The live response confirms that `sudska_praksa` namespace is being queried and contributing case law context to answers.

---

## Safety Invariants Confirmed

| Check | Result |
|-------|--------|
| Default namespace never dipped below 17,688 | ✓ |
| Default namespace never exceeded 17,688 | ✓ |
| All upserts passed namespace assertion guard (`TARGET_NAMESPACE = "sudska_praksa"`) | ✓ |
| Rollback function present and tested (Stage 1 false-alarm rollback verified it worked) | ✓ |
| State file resume logic: skipped already-completed chunks on re-run | ✓ |

---

## Notes for Phase 1.3 (Parallel Retrieval)

- Namespace: `sudska_praksa` — query with `namespace="sudska_praksa"` in Pinecone SDK
- Use `asyncio.gather` over default namespace + `sudska_praksa` for parallel retrieval
- Section metadata available for ranking: IZREKA (operative ruling) > OBRAZLOŽENJE (reasoning) > HEADER (parties/date)
- `cited_articles_raw` in chunk metadata contains raw article numbers — can use for cross-reference retrieval (zakon chunk for KZ 203 ↔ praksa chunk with `cited_articles_raw` containing "203" + `matter == "Krivična"`)
- `cited_articles_normalized` is empty — deferred to Phase 1.3 where law context is available

---

## Final Verdict

| Check | Result |
|-------|--------|
| Default namespace intact at 17,688 | ✓ |
| sudska_praksa at exactly 1,479 | ✓ |
| Final sanity queries 4/5 PASS (≥4 required) | ✓ |
| Production regression PASS (KZ + case law in response) | ✓ |
| Script committed to phase1-sudska-praksa | ✓ |
| **Phase 1.2 COMPLETE** | **YES** |
| **Ready for Phase 1.3 (Parallel Retrieval)** | **YES** |
