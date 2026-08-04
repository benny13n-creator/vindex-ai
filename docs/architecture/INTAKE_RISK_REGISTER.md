# Intake Risk Register — Program Intake Sprint 001 (2026-08-04)

Prioritized by real-world reachability (all 3 pipelines are confirmed live — §0 of the Architecture Report)
and by how directly each risk maps to the mission's own 5 closure-blocking conditions. **Fixed** items are
tested; **Deferred** items are backlogged in `ARCHITECTURAL_DEBT_REGISTER.md` as `INTAKE-00X` with reasoning.

| # | Risk | Pipeline(s) | Severity (pre-sprint) | Status |
|---|---|---|---|---|
| 1 | `IntakeWorker._process()` false-success on crash between `create_document()` and `write_processing_outcome()` — job marked `completed` with zero entities, zero review escalation, indistinguishable from real success | B | **Critical** — directly matches the mission's named worst-case forbidden condition | **Fixed** — `has_processing_outcome()` + `delete_partial_document()`, regression-tested |
| 2 | Original uploaded file never stored anywhere — tempfile deleted after OCR, `storage_path` a non-dereferenceable label | A | **Critical** — direct "dokument može nestati" | **Fixed** — reuses Pipeline B's encryption/bucket, best-effort |
| 3 | Pipeline C: total `predmet_dokumenti` insert failure after Pinecone success still returns `"ok": true"` (ghost vector, no DB row) | C | High | **Deferred**, `INTAKE-001` — Sentinel's hard-fail pattern isn't a safe direct port here (case row already created earlier in the same call; a 500 would misreport genuine partial success as total failure and risk a duplicate-creating retry) |
| 4 | Orphaned encrypted blobs in `intake-dokumenti` bucket when `enqueue_intake_job` RPC fails after Storage upload succeeds | B | Medium | **Deferred**, `INTAKE-002` — cleanup job is new infrastructure, out of "no new capability" bound |
| 5 | 2 `predmet_dokumenti` writers (`intake.py` wizard-link, `onboarding.py` demo stub) silently fell to the misleading `na_cekanju` DB default forever | A (adjacent) | Medium | **Fixed** — explicit `status="sacuvano"`/`"demo"` |
| 6 | `drafting.py` promotion writer left `tip_dokaza` permanently NULL — no classification path touches lawyer-approved drafts | A (adjacent) | Medium | **Fixed** — deterministic `tip_dokaza="podnesak"`, no new AI call |
| 7 | `dokument_view`/`dokument_download` already allowlisted in `AUDITABLE_ACTIONS` with UI labels wired, but the actual preview endpoint never called `log_action` | A | Low-Medium (observability gap, not data-loss) | **Fixed** for `dokument_view`. `dokument_download` has no separate endpoint identified this sprint — not applicable |
| 8 | Classifier race: English-vocab synchronous write vs. Serbian-vocab unawaited-background write, non-deterministic winner | A, C | High (pre-existing) | **Deferred, unchanged** — `ALPHA-003`/Gamma Fork E, vocabulary decision not a bounded fix |
| 9 | Migration 091 (Event Bus atomic dispatch claim) not run — live multi-worker duplicate-dispatch race for non-idempotent handlers | Cross-cutting | High (pre-existing) | **Deferred, unchanged** — `KEYSTONE-007`, founder action item |
| 10 | `predmet_dokumenti.status` and `intake_jobs.status` diverge permanently at finalize (lineage discarded) | B/C | Medium (pre-existing) | **Deferred**, `INTAKE-003` — genuine architecture question, not this sprint's to decide unilaterally |
| 11 | `routers/copilot.py:804` misreports finished wizard-linked/demo documents as eternally pending (dead `"greska"` branch, `"na_cekanju"` not a real pending signal on Pipeline A) | A (Copilot-side) | Low-Medium | **Documented only** — Copilot is an explicitly forbidden-to-fix module this sprint. `INTAKE-004` |
| 12 | 4-way document-type classifier duplication (2 ephemeral, non-persisting classifiers add cost/maintenance overhead with zero correctness impact) | A | Low | **Documented only** — `ALPHA-003` shape, not urgent |
| 13 | 3 separate OCR call sites repeat tempfile-write-then-delete boilerplate around one shared `extract()` core | A, B | Low | **Documented only** — cosmetic, not correctness-affecting |
| 14 | Correlation-ID coverage: most of the intake journey (OCR, chunking, Pinecone ingest, the DB row itself) has no audit/provenance record to attach a correlation ID to in the first place | A, B, C | Medium | **Documented only** — a coverage gap, not a defect; addressing it fully is closer to Phase 6 observability infrastructure than a bounded Phase 7 fix |
| 15 | Pipeline B/C's `intake_audit_log` table and the canonical `audit_immutable` table are two disconnected audit systems (no shared correlation_id column, no cross-reference) | B, C | Medium | **Documented only** — unifying them is new infrastructure design work |

**Risks 1 and 2 were the two directly named in the mission's own closure-blocking conditions and are the two
fixed with highest priority.** Risks 3-4 were seriously considered for a fix and explicitly declined with
reasoning rather than silently skipped, per this session's established deferral discipline. Risks 8-15 are
pre-existing, already-tracked-elsewhere, or explicitly out of this sprint's forbidden-module/no-new-capability
bounds.
