# Audit & Provenance Verification Report — Program Intake Sprint 004 (2026-08-05)

Phase 5 requirement: every human decision must produce an audit record, a provenance record, a correlation
ID, a timestamp, the prior state, the new state, and the reason for the change. Nothing may be lost.

## 1. Before this sprint — both human-decision endpoints had zero audit trail

Confirmed by direct code read and repo-wide grep (Sprint 004 Fork A §5): `correct_entity()`
(`shared/intake_documents.py`, called from `POST /entities/{id}/correct`) — no `log_action` call anywhere.
`resolve_review_queue_for_job` — never called at all, so the question of its audit trail was moot. Contrast
with `staging_memory`'s approve/reject endpoints, which... **also have no audit call** (confirmed this
sprint, a genuine gap noted but out of scope — `staging_memory` is not this sprint's object, per the boundary
decision in `REVIEW_QUEUE_SPECIFICATION.md` §3).

## 2. What now exists

### `entity_corrected` (new `AUDITABLE_ACTIONS` entry)
Logged at `POST /entities/{id}/correct` immediately after the correction succeeds:
- **user_id**: the correcting lawyer.
- **resource_type/resource_id**: `"entity"` / the entity's id.
- **metadata**: `{entity_type, reason}` — the field that changed and the lawyer's own stated reason (already
  an optional input to `correct_entity`, previously captured only in `intake_processing_outcomes.
  correction_reason`, never in the immutable audit ledger).
- **correlation_id**: inherited automatically from the request-scoped context (`shared/ai_provenance.py`'s
  existing middleware-set contextvar) — no new plumbing required.
- **Prior/new state**: the correction itself is already durably recorded in `extracted_entities.value` (never
  overwritten) vs. `.corrected_value` (the addition) — the audit row's timestamp anchors *when* this
  particular correction happened relative to everything else in the immutable ledger.

### `dokument_review_resolved` (new `AUDITABLE_ACTIONS` entry)
Logged at `POST /jobs/{id}/review/resolve`:
- **user_id**: the resolving lawyer.
- **resource_type/resource_id**: `"intake_job"` / the job id.
- **metadata**: `{prior_status, job_status_advanced, review_resolved_now}` — the job's status *before* this
  call, and whether this specific call was the one that actually changed anything (distinguishing "I just
  resolved this" from "someone/something already had" — directly answers the mission's "prior state / new
  state" requirement without inventing a new schema).
- **correlation_id**: same automatic inheritance.

### `job_awaiting_review` (new `intake_audit_log` event type, worker-side)
`mark_job_awaiting_review()` writes this via the existing `intake_queue.write_audit()` helper — the exact
same mechanism `complete_intake_job`/`fail_intake_job`'s RPC-embedded audit inserts already use for their own
transitions, applied here for consistency even though this specific write is a bare (non-RPC) update. This
closes a **second** audit gap: before this sprint, the moment a job's classification became uncertain had NO
audit trace at all (only the eventual `resolved_at` timestamp, with nothing marking when the uncertainty
itself arose).

## 3. Correlation ID continuity — verified, not assumed

The correlation-ID middleware (`api.py::correlation_id_middleware`, established prior sprints) sets a
request-scoped contextvar before any route handler runs. Both new `log_action` calls in this sprint use
`log_action`'s own default behavior (read `current_correlation_id()` when not explicitly passed) — meaning a
single correlation ID threads through: the original upload request → the worker's background processing
(inherited via `asyncio.create_task`'s context-copy semantics, established Sprint 001) → the review
escalation → the lawyer's correction/resolve action (a NEW request, with its OWN freshly-minted correlation
ID, correctly — a human's later action is a genuinely separate causal event, not a continuation of the
original upload's ID) → the eventual finalize call. This is honestly reported as **two correlation IDs across
the full lifecycle, not one** — the upload-through-processing chain shares one ID; the human-review-through-
finalize chain shares a second. Merging them into a single ID spanning a human's real-world response time
(which could be minutes, hours, or days) would misrepresent a correlation ID's actual purpose (one logical
request-triggered chain of causally-connected work), not correctly implement it.

## 4. Provenance — scoped to what "provenance" means for a non-AI action

`shared/ai_provenance.py::case_context()` is specifically for AI-calling operations — the wrapper records
which case/document an LLM call was made in service of. Neither `correct_entity` nor `resolve_review` calls
an LLM at all — applying `case_context()` here would be a category error (it exists to answer "why did the AI
say this," not "what did the human do"). This sprint's interpretation, consistent with the mission's own
framing ("svaka ljudska odluka mora imati... provenance zapis"): for a human decision, the audit_immutable
row itself — with its resource_id, prior/new state metadata, and correlation ID — **is** the provenance record.
No separate provenance table/mechanism was invented, since the audit ledger already durably answers "what
changed, who changed it, when, and in the context of which request chain."

## 5. Nothing lost — verified

- Original entity values: never overwritten (`corrected_value` is additive, unchanged design from Phase 1A).
- Review escalation reason: durable in `intake_review_queue.reason`, now also human-readable in the frontend.
- Resolution actor and timestamp: `intake_review_queue.resolved_by`/`resolved_at`, both written atomically
  with the resolution itself.
- The moment uncertainty arose: now durable via the new `job_awaiting_review` audit-log event (§2), closing
  the one remaining "when did this actually become uncertain" gap.

## 6. What remains a genuine, documented gap (not this sprint's to fix)

`staging_memory`'s approve/reject endpoints have no audit logging at all — found this sprint, correctly left
untouched since `staging_memory` is outside this sprint's object of study (drafting/Strategy-adjacent). Noted
in the debt register, not silently ignored.
