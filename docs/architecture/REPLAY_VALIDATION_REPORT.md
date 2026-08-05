# Replay Validation Report — Program Intake Sprint 002 (2026-08-05)

Phase 8 requirement: reconstruct one real document's full journey (every event, status change, audit record,
provenance record, correlation ID) from persisted data alone. Any unreconstructable step is a defect. Full
narrative: Fork C, `.vindex_ai_team/decisions/2026-08-05_intake_sprint002_fork_idempotency_replay.md`, Phase 8.

## Chosen journey

A lawyer uploads a signed, scanned contract PDF to an existing case via Pipeline A. OCR succeeds, Pinecone
ingest succeeds, `predmet_dokumenti` insert succeeds — the happy path, using only what the code actually
persists (not application logs, which may rotate or be lost).

## What exists afterward, and what it can/cannot answer

| System | Persisted | Cannot answer |
|---|---|---|
| `predmet_dokumenti` | Full row incl. real Storage key (Sprint 001 fix), Pinecone namespace, status, truncated `tekst_sadrzaj` | Whether OCR ran at all (no `ocr_used`/`is_scanned` column on this pipeline); whether `tekst_sadrzaj` is the whole document or a silently-truncated 100k-char slice |
| `intake-dokumenti` Storage | The original encrypted blob, now durable (Sprint 001) | Nothing else — no lifecycle metadata on the object itself |
| Pinecone chunks | Rich chunk-level metadata (`predmet_id`, `origin`, `source_sha256`, `is_scanned`) | No `document_id` FK back to the specific `predmet_dokumenti.id` row — for a multi-document case, attribution falls back to fuzzy filename/hash matching |
| `audit_immutable` | `dokument_upload` row with `correlation_id`, if the fire-and-forget task actually completed | Not guaranteed to exist — no dead-letter/retry of its own if the background write fails, only a log warning |
| `ai_forensics` | 3 provenance rows (procena/hronologija/metapodaci) with the SAME `correlation_id`, `document_id`, and — importantly — `status`/`error_message` capturing failures too | Also fire-and-forget, independently of the audit row above — the two systems can each silently no-op with no cross-check |
| `predmet_istorija`/`predmet_hronologija` | Free-text rows mentioning the filename | No `document_id` FK, no `correlation_id` column — links back only via matching filename text |

## Blind spots this replay-specific framing surfaces (beyond what Sprint 001's audit-trail analysis named)

1. Whether OCR ran at all is not recorded on the case-file row itself on Pipeline A/C (only Pipeline B's
   separate `intake_documents` table has this).
2. No FK from Pinecone chunks to `predmet_dokumenti.id` on either Pipeline A or C — verified by reading both
   `extra_metadata` dicts in full.
3. Two independent, unrelated fire-and-forget provenance systems on the same journey (`audit_immutable` via
   `log_action`, `ai_forensics` via `case_context`) — a crash can silently drop either or both, meaning the
   correlation ID meant to unify a replay can end up recorded in neither durable table for a given document.
4. No truncation marker on `tekst_sadrzaj` — a replay cannot tell "the document was short" from "the document
   was long and 40% of it is missing."
5. AI-call partial failure IS captured one layer down (`ai_forensics.status="error"`, verified — correcting an
   initial hypothesis in this fork's own draft) but is invisible at the case-file layer — nothing in
   `predmet_dokumenti`/`predmet_istorija` distinguishes "auto-analysis ran and failed" from "never attempted"
   from "nothing extractable."
6. A `redni_broj` collision (the Failure Recovery Matrix's own acknowledged benign race) is visible as a
   symptom in the data, but nothing persisted indicates it was a race rather than a genuine anomaly — the *why*
   is lost, only the *what* survives.

## Verdict

**Partial reconstruction, in a specific and useful pattern**: every artifact a lawyer actually needs for the
case to function (the document, its text, its Pinecone index) is durable and reconstructible end to end,
confirmed by this replay walkthrough. Everything that would let an auditor *prove exactly what happened and
why* — that OCR ran, that a specific request produced a specific row, why a downstream field is empty — rides
on fire-and-forget writes with no guarantee and, in several cases, no failure-visible trace of their own.

**This is not a "document lost" finding** (Sprint 001's closure-blocking condition) — it is a forensic-replay
gap, a different and lower-severity category. Tracked as `INTAKE-007` (`ARCHITECTURAL_DEBT_REGISTER.md`),
deferred: closing it fully would mean either making `log_action`/`ai_forensics` durable-with-retry (new
infrastructure, a genuine capability addition) or adding several new columns (`ocr_used`, a Pinecone→document
FK, a truncation flag) — none of which this sprint's 4 already-landed fixes should be stacked with in the same
pass, per the sprint's own bounded-implementation discipline.
