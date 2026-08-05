# Human Review Architecture Report — Program Intake Sprint 004 (2026-08-05)

**Charter**: "Human Review Orchestration & Automatic Resumption" — the last link between automation and the
lawyer. Not a "review screen." A canonical human-intervention system: every document that cannot be reliably
processed must be stopped, carry a clear reason, be verifiable, automatically resume after human confirmation,
and never lose history. **This sprint's own binding rule, unlike Sprints 001-003: it is not a research sprint.
Every technical problem found that can be fixed without a new founder business decision must be fixed in the
same sprint — backlog is only for business/regulatory decisions or work requiring genuinely new architecture.**

**Active team**: Chief Systems Architect, Legal Domain Expert, Reliability & Failure Recovery Engineer,
Evidence & Consistency Auditor — the smallest team of any sprint in this arc. All other roles STANDBY.

**Forbidden to implement**: OCR improvements, Genome, Copilot, Strategy Engine, Timeline, Tasks, Search,
Dashboard, Firm Brain, Alerts, Voice, Memory Graph. Findings there: documented, not fixed.

## 1. The central finding

Before this sprint, `shared/intake_documents.py::resolve_review_queue_for_job` — a fully-implemented,
correctly-designed function that marks a review resolved — **had zero call sites anywhere in the codebase**
(confirmed by repo-wide grep). A document could be flagged `Review Required` and then remain there
**permanently**, with no code path back to `COMPLETED`. Compounding this: `intake_jobs.status='awaiting_review'`
was declared in the schema (migration 073) but never actually written by any code — every job, confident or
not, reached `status='completed'` unconditionally, while a separate `intake_review_queue` row simultaneously
claimed the same job still needed human attention. **Two sources of truth disagreeing about the same fact** —
precisely the defect class this whole Program Intake arc exists to eliminate.

`routers/smart_intake.py::finalize_intake_job` never checked either signal: it created the permanent case
record regardless of outstanding review. The platform's review queue was, in effect, decorative — flagged,
displayed once on one screen, structurally incapable of stopping anything or ever being marked done.

## 2. What this sprint found and fixed (Phase 1 audit → immediate repair, per this sprint's own binding rule)

| # | Finding | Fix |
|---|---|---|
| 1 | `resolve_review_queue_for_job` — dead code, zero callers | New canonical endpoint `POST /jobs/{job_id}/review/resolve` wires it up — the first and only real caller |
| 2 | `intake_jobs.status='awaiting_review'` — declared, never written | `IntakeWorker._process()` now returns whether review is needed; `_tick()` sets `awaiting_review` instead of `completed` when true |
| 3 | `finalize_intake_job` never blocked on outstanding review | **No new blocking code needed** — its pre-existing `status != "completed"` gate now naturally rejects `awaiting_review` jobs, since they're no longer silently marked `completed` |
| 4 | `finalize`'s block message was generic/unhelpful for this case | Message now names the exact unblocking action (`POST .../review/resolve`) when the job is specifically `awaiting_review` |
| 5 | Generic `low_confidence_extraction` reason didn't distinguish "the type itself is unclear" from "a few fields are unclear" | Worker now uses the schema-declared-but-dormant `classification_uncertain` reason specifically when `document_type` is among the uncertain fields |
| 6 | `correct_entity()` (`/entities/{id}/correct`) had zero audit logging | Added `log_action("entity_corrected", ...)`, correlation ID inherited automatically |
| 7 | No audit action existed for review resolution at all | Added `"dokument_review_resolved"` to `AUDITABLE_ACTIONS`, logged with prior status, resolution outcome |
| 8 | **Frontend**: `_siJobsStillActive()` would have polled `awaiting_review` jobs forever, since it only excluded `completed`/`failed` | Fixed to also exclude `awaiting_review` |
| 9 | **Frontend**: the poll handlers only fetched document/entity/review data when `status === 'completed'` — an `awaiting_review` document would show no data at all | Widened both gates to include `awaiting_review` |
| 10 | **Frontend**: `_siRenderReview()`'s own document list filtered `status === 'completed'` only — an `awaiting_review` document would be **completely invisible** on the one screen meant to show it | Widened to include `awaiting_review` — found and fixed as a direct consequence of shipping fix #2/#3 responsibly, not a pre-existing bug |
| 11 | **Frontend**: no UI action existed to call the new resolve endpoint | The existing "Kreiraj predmet" click (from the review screen the lawyer has already seen, with correction capability already present) now resolves any outstanding review before calling finalize — no new screen needed, the existing one already discharges the human-confirmation requirement |
| 12 | Review reason shown to the lawyer was just a list of field names, no explanation of *why* | Added a reason→Serbian-label map (`_SI_REVIEW_REASON_LABELS`), surfaced alongside the field list |

**Findings #8-10 are a direct illustration of why this sprint's own binding rule matters**: fixing the backend
state machine correctly (#2/#3) would, by itself, have silently broken the frontend (jobs polling forever,
invisible on the review screen) — a worse outcome than before the fix. Finding them and fixing them in the
same pass, rather than declaring the backend fix "done" and filing the frontend gap as a follow-up, is exactly
what this sprint's charter demands.

## 3. What this sprint found and deliberately did NOT fix (genuine business decisions, not technical avoidance)

- **What should "reject" concretely do?** The mission's own test list names "rejection" as a scenario to
  prove. A lawyer's "confirm as-is" path (resolve) is fully built. A genuine "no, this is wrong, don't accept
  it" path raises a real product question this sprint cannot answer unilaterally: does rejection mean
  re-running classification from scratch, routing to fully-manual data entry, or something else? Each has
  different UX and cost implications. **This is a business decision, correctly out of this sprint's scope**,
  tracked in the debt register.
- **Correcting the AI-detected document type value itself.** `POST /entities/{id}/correct` only covers 8
  extraction fields (case_number, judge, plaintiff, defendant, court, deadline, amount, law_cited) —
  `document_type` is not among them (confirmed, Sprint 003's own inventory). A lawyer can confirm-and-proceed
  with an uncertain type via resolve, or correct other fields, but cannot directly retype the document's
  classification through this mechanism. Building this requires deciding which vocabulary a manual correction
  writes to (`intake_documents.document_type`'s English set, or the canonical taxonomy Sprint 003 designed but
  hasn't adopted) — genuinely blocked on that unresolved adoption decision, not a bounded technical fix.
- **`staging_memory` (drafting/Strategy-adjacent approval)** — a second, fully-working "human confirms AI
  output" system exists for approving AI-drafted content (different confidence threshold, different status
  vocabulary, different object entirely — approving generated OUTPUT, not reviewing uncertain INPUT
  classification). Not unified with the intake review queue: it answers a genuinely different question, for a
  genuinely different kind of document. See `REVIEW_QUEUE_SPECIFICATION.md` §3 for the full justification.

## 4. Mission closure self-check

- No document ends in an unknown/permanently-blocked state → **True for the reachable review path** — every
  document now provably resolves to `COMPLETED`, `REVIEW_REQUIRED` (now genuinely escapable), or `FAILED_FINAL`
  (the existing dead-letter mechanism, unchanged, already proven in Sprint 001/002).
- Exactly one canonical Review Queue → True for intake classification review specifically (the object this
  sprint's charter concerns); `staging_memory` is a deliberately separate, justified system for a different
  question.
- Exactly one way to escalate → True — `create_review_queue_entry` with one of 3 deterministic reasons, no
  free text.
- Exactly one way to resume → True — `resolve_review()`, the sole path back from `awaiting_review`.
- Resume is idempotent → True, proven (`tests/test_intake_documents.py`'s concurrency tests).
- Human decisions have full audit trail → True for the two human-decision endpoints this sprint touched
  (`correct_entity`, the new resolve endpoint); genuinely new gaps found and closed, not pre-existing gaps
  merely documented.
- All found technical problems in scope fixed → **Yes — all 12 findings in §2, including 3 found only as a
  consequence of correctly shipping the others.**
- No new duplicate business logic → Confirmed — the fix reuses `_VALID_STATUSES`' already-declared
  `awaiting_review` value, `finalize`'s already-existing status gate, and `resolve_review_queue_for_job`'s
  already-existing (merely unwired) function. Nothing new was invented that didn't already have a designed,
  dormant home.
- All tests pass without regressions → 2530 passed, 1 skipped, 0 failed (one pre-existing test's mock needed
  updating for `_process()`'s new return contract — not a product regression, a test-harness fix).
