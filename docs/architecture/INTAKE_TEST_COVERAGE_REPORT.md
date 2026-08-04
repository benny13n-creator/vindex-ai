# Intake Test Coverage Report — Program Intake Sprint 001 (2026-08-04)

Phase 7 requirement: provable tests for the bounded fixes actually implemented this sprint. Full suite run
after every fix: **2492 passed, 1 skipped (pre-existing, unrelated), zero regressions.**

## New test files this sprint

| File | Fix under test | Tests |
|---|---|---|
| `tests/test_intake_original_file_storage.py` | Pipeline A original-file Storage preservation | `test_upload_stores_original_file_and_writes_real_storage_path` — encryption invoked with raw bytes, real dereferenceable `storage_path` written, not the old label. `test_upload_still_succeeds_and_falls_back_to_session_label_when_storage_upload_fails` — a Storage-layer exception does not abort the request (best-effort by design); `storage_path` honestly falls back to the old label rather than claiming success it didn't achieve. |
| `tests/test_intake_worker_phase1a.py` (extended, not new file) | `IntakeWorker._process()` false-success fix | `test_process_skips_already_processed_job_idempotent` (updated) — skip now requires BOTH document existence AND `has_processing_outcome()`, not document existence alone. `test_process_partial_document_without_outcome_is_deleted_and_reprocessed` (new) — the direct regression test for the sprint's most severe finding: document exists, outcome doesn't → partial state deleted, full clean reprocessing occurs (redownload, fresh `create_document`, outcome actually written this time). |
| `tests/test_intake_documents.py` (extended, not new file) | `has_processing_outcome()`/`delete_partial_document()` helpers | `test_has_processing_outcome_true_when_row_exists`, `test_has_processing_outcome_false_when_no_row`, `test_delete_partial_document_deletes_children_before_parent` (verifies FK-safe delete order — `extracted_entities`/`intake_review_queue` before `intake_documents`, since no `ON DELETE CASCADE` exists per migration 074). |
| `tests/test_intake_dokument_view_audit.py` | `dokument_view` audit logging | `test_preview_logs_dokument_view_audit_action` — `log_action("dokument_view", ...)` fires with correct `user_id`/`resource_id`/`metadata` on a successful preview. `test_preview_404_does_not_log_audit_action` — no audit entry for a document that was never actually viewed (ownership check failed). |
| `tests/test_intake_status_writers.py` | Explicit `status`/`tip_dokaza` at 3 writer sites | `test_intake_kreiraj_links_document_with_explicit_status` — wizard reference-link writes `status="sacuvano"`, never falls to `na_cekanju`. `test_kreiraj_demo_predmet_document_has_explicit_demo_status` — demo stub writes `status="demo"`, deliberately distinct from real-document values. `test_promote_staged_draft_sets_tip_dokaza_deterministically` — approved-draft promotion writes `tip_dokaza="podnesak"` without any new AI call. |

## Coverage against the mission's own explicit minimum test list

| Required scenario | Covered by |
|---|---|
| Upload success | `test_upload_stores_original_file_and_writes_real_storage_path`; pre-existing `test_sentinel_reliability_fixes.py` |
| Upload failure | `test_upload_raises_honest_error_when_document_insert_fails_after_pinecone_success` (pre-existing, Sentinel) |
| OCR success | Pre-existing `test_intake_worker_phase1a.py::test_process_success_path_no_review_when_all_confident` |
| OCR timeout/failure | Pre-existing `test_process_ocr_failed_routes_to_review_fail_soft_not_exception` |
| Storage timeout | `test_upload_still_succeeds_and_falls_back_to_session_label_when_storage_upload_fails` (new) |
| Worker restart | `test_process_partial_document_without_outcome_is_deleted_and_reprocessed` (new — the exact crash-mid-processing scenario a worker restart triggers) |
| Retry | `test_process_partial_document_without_outcome_is_deleted_and_reprocessed` (new); `test_process_skips_already_processed_job_idempotent` (updated, true-completion retry path) |
| Duplicate upload | Not newly tested this sprint — Pipeline A has no dedup logic by design (§ Failure Recovery Matrix); Pipeline B's `dedup_check` job stage predates this sprint and was not modified |
| Parallel upload / race condition | Not newly tested this sprint — `claim_next_job`'s `SELECT...FOR UPDATE SKIP LOCKED` atomicity predates this sprint (Phase 1A) and was not modified; this sprint's fix is orthogonal (what happens *after* a valid claim, on crash-retry) |
| Rollback | N/A — confirmed no multi-statement transactions exist in any of the 3 pipelines (each write is independently committed), so there is no rollback semantics to test; documented in Failure Recovery Matrix |
| Power-failure simulation | `test_process_partial_document_without_outcome_is_deleted_and_reprocessed` is the direct proxy — a partial-write-then-crash state, which is exactly what a power failure mid-processing produces |

**Gaps honestly noted, not silently skipped**: duplicate-upload and parallel-upload/race-condition tests
were not added because this sprint did not modify the code paths responsible for either guarantee (Pipeline
B's claim atomicity and dedup-check stage both predate this sprint unchanged) — adding tests for unmodified
code is not this sprint's job and risks false confidence about scope. Rollback has no applicable code to test
against (no transactions exist to roll back).
