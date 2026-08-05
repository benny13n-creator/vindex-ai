# Orchestrator Ownership Report — Program Delta, Sprint 003 (2026-08-05)

Task 5's own required deliverable: for every event Case Evolution Engine owns, prove one owner, one
orchestrator, one definition, one retry mechanism, one audit model, one provenance chain, one correlation
chain. If two owners exist for the same concern, the sprint is not done.

## The 6 wired events — one owner each, verified

| Event | Owner (the ONLY subscriber to `handle_case_changed`) | Verified by |
|---|---|---|
| `DOCUMENT_ACCEPTED` | `services/case_evolution.py::handle_case_changed` | `EventBus._handlers[DOCUMENT_ACCEPTED] == [handle_case_changed]` |
| `REVIEW_ACCEPTED` | same | same |
| `REVIEW_REJECTED` | same | same |
| `NEW_CLIENT_LINKED` | same | same |
| `NEW_EVIDENCE_REGISTERED` | same | same |
| `ROCISTE_ZAKAZANO` | same | same |

`tests/test_delta_sprint003_full_convergence.py::test_1_all_wired_events_share_the_same_dispatcher` asserts
this directly against the live `EventBus._handlers` dict, not a narrative claim — will fail if a future change
ever adds a second handler for any of these 6 event types.

## One definition per event — no duplicate consequence logic

Every consequence executor is a named, singular function in `services/case_evolution.py`
(`_consequence_genome_refresh`, `_consequence_timeline_entry`, `_consequence_review_confirmation_audit`,
`_consequence_review_rejection_audit`, `_consequence_conflict_check`, `_consequence_evidence_classify`) — no
event's own consequence logic is duplicated anywhere else. Where two DIFFERENT events need the same
consequence (`REVIEW_ACCEPTED` and `DOCUMENT_ACCEPTED` both need `genome_refresh`/`timeline_entry`;
`ROCISTE_ZAKAZANO` also needs `genome_refresh`), the SAME executor function is reused by reference in
`CONSEQUENCE_REGISTRY` — never copy-pasted, never reimplemented.

## One retry mechanism — the Event Bus's own, unchanged since Sprint 001

Every consequence's failure propagates to `dispatch_pending_events`'s own `MAX_DISPATCH_ATTEMPTS=5`
retry/dead-letter loop (migration 073/091, Project Phoenix 2026-08-03). No sprint has ever built a second
retry mechanism alongside it — confirmed again this sprint: the 2 new emission call sites (`api.py`,
`routers/rocista.py`) contain zero retry logic of their own; they emit once, durably, and the SAME outer
mechanism owns everything downstream.

## One audit model

Every consequence gets a `case_evolution_consequence_completed` audit row (generic, per-consequence) via the
SAME `handle_case_changed` post-consequence step. Domain-specific audit actions
(`dokument_review_resolved`, `dokument_review_rejected`) are themselves modeled as ordinary consequences
(`review_confirmation_audit`, `review_rejection_audit`) — not a parallel audit path, just another named
consequence in the same registry, subject to the same idempotency/retry/verification rules as every other one.

## One provenance / correlation chain

Every emission call site (`finalize_intake_job`, `resolve_job_review`, `reject_job_review`,
`predmet_upload_auto_analyze`, `kreiraj_rociste`) reads `correlation_id` from the SAME source —
`shared/ai_provenance.py::current_correlation_id()`, propagated through `services/event_bus.py::emit_durable`
into the durable outbox row, then into `Event.correlation_id`, then into every consequence's own audit row.
One id, one chain, unchanged mechanism since Mission Ledger (2026-08-03) — Sprint 003 adds 2 more emission
sites using it, builds nothing new.

## Deliberately NOT unified — named, not hidden

Three categories of code intentionally remain OUTSIDE Case Evolution Engine, each with a specific,
defensible reason (not a gap this sprint failed to close):

1. **Primary-action writes, not reactive consequences.** `finalize_intake_job`'s own document-linking insert,
   `hearing_followup`'s own beleška/hronologija/istorija writes, `dokument_upload`'s own audit log call — all
   are the literal thing the endpoint promised to do, executed synchronously, in the same request/response.
   Case Evolution Engine owns what AUTOMATICALLY follows a change, not the change itself.
2. **A different, already-established orchestrator.** `PREDMET_KREIRAN` → Case Pipeline
   (`services/case_pipeline.py::run_case_pipeline`), proven independently idempotent by Project Sentinel
   (2026-08-03). Folding two independently-proven orchestration systems into one is a real architecture
   decision with real risk, correctly out of a 2-agent sprint's bounded scope — named here, not silently
   ignored.
3. **A user-initiated synchronous query, not an automatic reaction.** `routers/intake.py`'s own
   `POST /api/intake/conflict-check` — a lawyer explicitly asks "check for a conflict right now" and gets an
   immediate answer. There is no "case changed" event here to react to; the check IS the request.

## Conclusion

No event with a genuine, currently-needed reactive consequence has more than one owner. The 3 categories of
code correctly left outside Case Evolution Engine are not orchestrators of case state at all (by the terms of
the mission's own final closing instruction — a "legitimate business event that independently orchestrates
state") — they are either primary actions, a different already-proven orchestrator, or a direct query.
Ownership is unambiguous for every event this registry claims to own.
