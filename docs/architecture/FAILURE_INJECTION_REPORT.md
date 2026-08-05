# Failure Injection Report — Program Intake Sprint 002 (2026-08-05)

Phase 7 requirement: simulate DB rollback, storage timeout, OCR crash, worker restart, queue duplication,
network interruption, power loss, Pinecone failure, mid-step exception, retry storm — prove the system stays
consistent. Each scenario below is backed by a regression test (file:test name cited), not a narrative claim
alone. Full test files: `tests/test_sprint002_*.py`, `tests/test_intake_*.py`.

| Scenario | Pipeline(s) affected | Consistency outcome | Proof |
|---|---|---|---|
| DB rollback | All | N/A as a literal event — no multi-statement transactions exist to roll back (`TRANSACTION_BOUNDARY_ANALYSIS.md` §1). Consistency instead comes from idempotent re-processing. | `tests/test_intake_documents.py::test_delete_partial_document_deletes_children_before_parent` |
| Storage timeout/failure (upload) | A | Best-effort, non-blocking on A (established Sprint 001); B now pre-checks before writing and compensates on failure | `tests/test_intake_original_file_storage.py::test_upload_still_succeeds_and_falls_back_to_session_label_when_storage_upload_fails`, `tests/test_sprint002_pipeline_b_orphan_prevention.py::test_enqueue_failure_deletes_the_just_uploaded_blob` |
| OCR crash (safety-limit / unreadable / empty) | A | Orphan-blob compensating cleanup fires on all 3 raise sites | `tests/test_sprint002_pipeline_a_orphan_cleanup.py::test_safety_limit_exceeded_deletes_orphan_blob`, `::test_empty_text_deletes_orphan_blob` |
| Worker restart mid-job | B | Stale-job reaper reclaims; the specific dangerous crash window (after `create_document`, before `write_processing_outcome`) now correctly triggers full clean-slate reprocessing instead of false-complete | `tests/test_intake_worker_phase1a.py::test_process_partial_document_without_outcome_is_deleted_and_reprocessed`, `::test_process_propagates_outcome_write_failure_instead_of_swallowing` |
| Queue duplication (2 enqueue calls, same content) | B | Job-row duplication structurally impossible (`idempotency_key` UNIQUE index); pre-check now also prevents the Storage-blob side of the duplication | `tests/test_sprint002_pipeline_b_orphan_prevention.py::test_duplicate_resubmit_skips_storage_upload_entirely` |
| Network interruption (downstream RAG/AI calls) | A, C | Caught, logged, flow continues degraded — pre-existing, unchanged, reconfirmed | (pre-existing) `tests/test_sentinel_reliability_fixes.py` |
| Power loss (abrupt kill, proxy: partial-write-then-crash) | B | Same proof as "worker restart" — a crash mid-`_process()` is indistinguishable from a power loss from the job's perspective; the fix covers both | `tests/test_intake_worker_phase1a.py::test_process_partial_document_without_outcome_is_deleted_and_reprocessed` |
| Pinecone failure (quota/429, and generic) | A, C | `pinecone_ok` flag honestly threaded into `status`; a **generic** (non-quota) Pinecone exception now also triggers orphan-blob cleanup before the 500 propagates | `tests/test_sprint002_pipeline_a_orphan_cleanup.py::test_pinecone_failure_after_successful_storage_write_deletes_orphan_blob` |
| Exception between two steps (DB insert fails after Pinecone succeeds) | A | Sentinel's pre-existing hard-fail (honest 500) now ALSO triggers the orphan-blob cleanup for the original file | `tests/test_sprint002_pipeline_a_orphan_cleanup.py::test_predmet_dokumenti_insert_failure_deletes_orphan_blob` |
| Retry storm (double-click / rapid repeated finalize calls) | C | **The sprint's central fix**: atomic claim means only one concurrent call can ever run the case-creation side effects; all others are turned away honestly (already-finalized or in-progress), never allowed to duplicate | `tests/test_sprint002_finalize_atomic_claim.py` (all 3 tests) |
| Cleanup mechanism itself failing (compensating delete throws) | A, B | The original error must still reach the client unchanged — cleanup failure is logged only, never masks or replaces the real response | `tests/test_sprint002_pipeline_a_orphan_cleanup.py::test_cleanup_failure_does_not_mask_the_original_error`, `tests/test_sprint002_pipeline_b_orphan_prevention.py::test_enqueue_failure_cleanup_itself_failing_does_not_mask_original_error` |

## Scenarios explicitly NOT newly injected this sprint, with reasoning

- **Two job rows for one document, both processed in parallel** (a hypothesized queue-duplication shape) — Fork
  C proved this cannot occur through the upload path for the same user+content (unique index); the only way two
  independent rows can exist for identical bytes is two *different* users, which is correct concurrent
  behavior, not a bug, and was not artificially forced into a failure test.
- **Full Postgres-level rollback semantics** — no code path in this codebase uses a multi-statement transaction
  outside the 5 RPCs, so there is no rollback behavior to inject a failure into beyond what the RPC-level tests
  already cover (`test_intake_phase0.py`'s existing RPC tests, extended this sprint for `claim_finalize`).

## Result

Every named scenario in the mission's own minimum list has a concrete, passing regression test proving the
system either (a) never entered an inconsistent state in the first place, or (b) self-heals back to a
consistent state on the next retry/reap cycle. No scenario was found where the system is left in a state that
cannot be classified as one of: successfully completed, honestly failed, or safely retryable.
