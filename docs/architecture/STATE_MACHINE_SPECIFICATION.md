# Document Lifecycle State Machine Specification — Program Intake Sprint 002 (2026-08-05)

Phase 4 requirement: a single canonical state machine for a document's lifecycle. Full narrative: Fork B,
`.vindex_ai_team/decisions/2026-08-05_intake_sprint002_fork_transaction_boundaries_state_machine.md` §4.

## Canonical states

```
UPLOADED → STORED → QUEUED → PROCESSING → OCR_COMPLETE → EXTRACTED → PERSISTED → INDEXED → VERIFIED → COMPLETED
                                    ↓
                        FAILED → RETRY → FAILED_FINAL → REVIEW_REQUIRED
```

No document may ever be in state `UNKNOWN`.

## Mapping each pipeline's actual signals onto the canonical model

| Canonical state | Pipeline A | Pipeline B | Pipeline C |
|---|---|---|---|
| UPLOADED | Implicit (`file.read()` succeeded, no persisted marker) | Implicit, same | N/A — inherits B's already-completed job |
| STORED | `_original_storage_path` non-null (local var, folds into final row) | `intake_jobs.storage_path`, persisted at `enqueue_intake_job` time — same instant as QUEUED, same row | Reads B's already-stored blob; no new STORED state |
| QUEUED | **No representation** — no queue concept on this pipeline | `intake_jobs.status='received'` | N/A |
| PROCESSING | **No representation** — synchronous, the HTTP request itself is the processing window | `intake_jobs.status` declares `preprocessing/classifying/extracting/matching/dedup_check` in its CHECK constraint, but `_process()` only ever actually sets `preprocessing` — the other 4 are dormant, never written | N/A — synchronous like A |
| OCR_COMPLETE | **No representation** — `is_scanned`/`ocr_used` are local booleans only | Same — local booleans, not persisted as a transition | Same, and this pipeline **redundantly re-runs OCR** B's worker already did |
| EXTRACTED | Ephemeral doc-type detection only, not a Confidence Graph | **Genuinely represented** — `intake_documents`+`extracted_entities` rows existing IS extraction-complete | Reuses B's already-extracted entities via `get_job_result` — correct reuse |
| PERSISTED | `predmet_dokumenti` row exists, hard-checked (Sentinel) | N/A — Pipeline B never writes `predmet_dokumenti` | `predmet_dokumenti` row exists, honest but not hard-checked (`doc_linked`, `INTAKE-001`) |
| INDEXED | Collapsed into the same write as PERSISTED (`status="indeksirano"` vs `"sacuvano"`) | N/A | Same collapse as A |
| VERIFIED | **No representation on any pipeline** — nothing distinguishes "a human confirmed this" from "AI produced it, unreviewed," except the adjacent-but-narrower `intake_review_queue.resolved_at` (B/C only) | (same) | (same) |
| COMPLETED | Implicit — HTTP 200, no further state | `intake_jobs.status='completed'` — real, atomic, but answers "is the queue job done," not "is the case-file document done" (3-way fragmentation, Sprint 001, unchanged) | Implicit — HTTP 200 with `"ok": true"`, now protected against silently co-existing with a duplicate (fixed this sprint) |
| FAILED/RETRY/FAILED_FINAL | N/A — no retry mechanism, one attempt per call | `intake_jobs.status='failed'` after `max_attempts`, real, atomic, exponential backoff | N/A — and (pre-fix) an actual user retry of a failed finalize was exactly the dangerous case, now guarded |
| REVIEW_REQUIRED | N/A | `intake_review_queue` row with `resolved_at IS NULL` — the one canonical state B represents cleanly | Inherited from B; finalize can proceed even with an unresolved review item (soft gap, not scored — a UX/product question, not this sprint's transactional-boundary charter) |

## Classifying the gaps

1. **Purely representational** (the fact already exists in control flow, just never given a name) —
   STORED-vs-QUEUED on B, OCR_COMPLETE-vs-EXTRACTED on all three, PERSISTED-vs-INDEXED on A/C. **No migration
   needed**: these are answerable today as a computed/derived view, since the underlying conditions already
   coincide at the exact same instant. Matches this codebase's established preference (Pricing Matrix,
   `intake_queue_metrics`, `events_outbox_metrics` — "IZVEDENI, nikad zaseban stored red").
2. **Genuinely absent, not derivable from anything that exists today** — PROCESSING's intermediate sub-states
   (declared in the schema, never written — a real, bounded, zero-migration code fix, tracked as `INTAKE-006`,
   deferred as optional/observability, not required for consistency). VERIFIED as a first-class state (requires
   a genuinely new column — already correctly deferred as a founder-decision item, `INTAKE-003`).
3. **Cross-pipeline fragmentation no view can paper over** — Pipeline A's `predmet_dokumenti` row and Pipeline
   B's `intake_jobs` row are two different rows in two different tables with no FK between them until Pipeline
   C's finalize runs, and even then only at the case level (`intake_jobs.predmet_id`), never at the
   document-row level (no `intake_job_id` column exists on `predmet_dokumenti` — `INTAKE-003`, unchanged).

## Recommendation

**Do not add a new `lifecycle_state` column.** Category 1's gaps are answerable today with a derived view —
consistent with this sprint's own closing instruction to prefer consistency over new capability, and with
this codebase's established discipline. The one category-2 item worth closing without a founder decision
(wiring up the already-declared `classifying`/`extracting`/`matching`/`dedup_check` values inside `_process()`)
is deferred as `INTAKE-006` — real, bounded, but optional (observability, not correctness), and this sprint
prioritized the 4 fixes that directly close proven consistency defects over this one, per the charter's own
"prefer consistency over new capability" tie-breaker (this item is neither — it's pure visibility).

**VERIFIED and the `predmet_dokumenti`↔`intake_jobs` FK gap (`INTAKE-003`) are not re-litigated** — both
already correctly identified and deliberately deferred by Sprint 001 as founder/product decisions requiring
an actual new column; this sprint's transaction-boundary analysis confirms the gap is real but adds no new
urgency beyond what Sprint 001 already recorded.
