# Intake Duplicate Logic Register — Program Intake Sprint 001 (2026-08-04)

Phase 3 requirement: find duplicate upload paths, OCR flows, storage flows, retry mechanisms, status
machines. Every claim below is grepped/read-verified, not assumed. Full narrative: `INTAKE_ARCHITECTURE_REPORT.md`.

## Upload paths — 3, confirmed (not duplication, divergent evolution)

`api.py:4061` (Pipeline A), `routers/smart_intake.py:92`+`373` (Pipeline B/C). Not true duplication in the
"copy-pasted logic" sense — Pipeline B/C is a materially different, newer architecture (durable queue vs.
synchronous). Both are live and both are needed for their respective product flows today (§1 of the
Architecture Report). Not collapsed this sprint — a product decision, not a bounded fix.

## OCR call sites — 3, confirmed (corrects Program Alpha's own prior inventory, which claimed 1)

`shared/intake_worker.py::_extract_text` (Pipeline B), `api.py` inline (Pipeline A), `routers/dokument.py`
inline (ephemeral session Q&A upload, not part of any of the 3 case-file pipelines). All 3 call the same
underlying `uploaded_doc/extractor.py::extract()` — the duplication is in the 3 separate call *sites*
(tempfile-write-then-delete boilerplate repeated 3 times), not in 3 separate OCR *implementations*. Low
severity — the shared core function is already the single source of OCR logic.

## Document classifiers — 4 independent implementations, 2 that matter

| Classifier | Vocabulary | Persists to DB? | Status |
|---|---|---|---|
| `shared/intake_classify.py` | English, 13-type | Yes — `intake_documents.document_type` | Participates in the classifier race (below) |
| `routers/evidence.py::_klasifikuj_dokument` | Serbian, 9-type | Yes — `predmet_dokumenti.tip_dokaza` | Participates in the classifier race (below) |
| `api.py::_detect_doc_type` | 3-way keyword heuristic | **No** — ephemeral, prompt-routing only | Cost/maintenance duplication only, not a correctness bug |
| `routers/dokument.py::_klasifikuj_dokaz` | 4th taxonomy, GPT-4o-mini | **No** — ephemeral session Q&A only | Cost/maintenance duplication only, not a correctness bug |

**The classifier race** (Program Gamma Fork E, re-confirmed live and byte-identical this sprint):
`shared/intake_worker.py:173` writes English-vocabulary `document_type` synchronously via
`intake_documents.create_document()`; `routers/smart_intake.py:676` (finalize) writes this into
`predmet_dokumenti.tip_dokaza` synchronously as one of 3 fallback insert variants; `routers/smart_intake.py:
725-735` then fires `routers/evidence.py::klasifikuj_i_sacuvaj` (the correct Serbian vocabulary) via an
**unawaited** `asyncio.create_task` — fire-and-forget, no retry, failure only logged
(`except Exception as ce: logger.warning(...)`). Whichever finishes last wins, non-deterministically. Not
fixed this sprint (`ALPHA-003` shape — a vocabulary/ownership decision requiring a real design call, not a
bounded reliability patch).

## Retry mechanisms — 1 real, correctly scoped (not duplicated)

Only Pipeline B (`shared/intake_queue.py`) has retry logic — atomic claim, exponential backoff, stale-job
reaper, dead-letter. Pipelines A and C are synchronous, single-attempt by design (a failed request just
returns an error to the caller, who can manually retry). This is not duplication — it's one retry mechanism,
correctly scoped to the one pipeline architecturally suited to have one.

## Status machines — 2, serving different purposes (not a collision, see Source of Truth Matrix)

`predmet_dokumenti.status` (free-text, no CHECK constraint, 3 real values in practice:
`indeksirano`/`sacuvano`/`na_cekanju`-as-fallback, plus the new `demo` this sprint) and `intake_jobs.status`
(migration 073's real 9-value enum: `received/preprocessing/classifying/extracting/matching/dedup_check/
awaiting_review/completed/failed`). Different audience (case-file view vs. worker queue state), not the same
concept represented twice. Full detail: `INTAKE_SOURCE_OF_TRUTH_MATRIX.md`.

## Six independent writers of `predmet_dokumenti`

Full table in `INTAKE_ARCHITECTURE_REPORT.md` §2 — not repeated here to avoid the sprint's own governing
principle (one fact, one place) applied to its own documentation.

## What this sprint did NOT find (positive, confirmed-clean results)

- **Pinecone namespace**: `rag_owner_namespace(user_id, kancelarija_id)` used identically at every write
  site (`api.py:4103/4219`, `smart_intake.py`, `drafting.py:314`) — no drift, no duplicate namespace schemes.
- **Encryption scheme**: Pipeline A (this sprint) and Pipeline B both now use the exact same
  `_encrypt()`/`_STORAGE_BUCKET` — not a second independent encryption implementation, a genuine reuse.
- **Correlation ID minting**: exactly one mint point (`correlation_id_middleware`), no competing minter found
  anywhere in the intake journey.
