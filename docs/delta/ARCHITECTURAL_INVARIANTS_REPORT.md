# Architectural Invariants Report — Program Delta, Sprint 004 (2026-08-06)

Orchestration Certification, Phase 6. For each of the 6 Case-Evolution-owned events, prove: one orchestrator,
one definition, one audit, one provenance chain, one correlation chain, one replay path, one retry path. If
more than one exists anywhere, the architecture is not canonical.

## Invariant 1 — One event, one orchestrator

`bus._handlers[et] == [handle_case_changed]` for all 6 events, verified programmatically (not narrated):

```
DOCUMENT_ACCEPTED         -> ['handle_case_changed']
REVIEW_ACCEPTED           -> ['handle_case_changed']
REVIEW_REJECTED           -> ['handle_case_changed']
NEW_CLIENT_LINKED         -> ['handle_case_changed']
NEW_EVIDENCE_REGISTERED   -> ['handle_case_changed']
ROCISTE_ZAKAZANO          -> ['handle_case_changed']
```

Enforced going forward by `tests/test_delta_sprint004_certification.py::test_one_owner_per_wired_event_type`
(direct assertion against the live `EventBus._handlers` dict) and
`tests/test_delta_sprint003_full_convergence.py::test_1_all_wired_events_share_the_same_dispatcher`.

## Invariant 2 — One definition per consequence, reuse not duplication

Every consequence executor is a single named function in `services/case_evolution.py`. Where multiple events
need the SAME consequence, the SAME function object is referenced (not copied):

- `_consequence_genome_refresh` — used by `DOCUMENT_ACCEPTED`, `REVIEW_ACCEPTED`, `ROCISTE_ZAKAZANO`
- `_consequence_timeline_entry` — used by `DOCUMENT_ACCEPTED`, `REVIEW_ACCEPTED`
- `_consequence_evidence_classify` — used by `NEW_EVIDENCE_REGISTERED`
- `_consequence_conflict_check` — used by `NEW_CLIENT_LINKED`
- `_consequence_review_confirmation_audit` / `_consequence_review_rejection_audit` — one each, `REVIEW_ACCEPTED`/`REVIEW_REJECTED`

No Genome-refresh logic, evidence-classification logic, or conflict-check logic exists anywhere else in the
codebase outside these named functions (proven by the repo-wide bypass tests — Phase 5, below).

## Invariant 3 — One retry path

Every consequence failure propagates out of `handle_case_changed` unchanged, reaching
`dispatch_pending_events`'s own single retry/dead-letter mechanism (`MAX_DISPATCH_ATTEMPTS=5`, migration
073/091). No sprint has ever built a second retry mechanism. Confirmed this sprint by the new
`test_full_chain_crash_after_one_consequence_real_dispatch_retry_resumes` test, which drives the REAL
`dispatch_pending_events()` function (not a hand-built `Event`) through a simulated crash-and-retry and
observes the SAME retry semantics apply — no parallel or divergent retry logic was found anywhere in
`services/case_evolution.py`.

## Invariant 4 — One audit model

Every consequence gets exactly one `case_evolution_consequence_completed` row via `handle_case_changed`'s own
post-consequence step. Domain-specific audit actions (`dokument_review_resolved`, `dokument_review_rejected`)
are themselves modeled as ordinary named consequences in the SAME registry — not a parallel audit path.
Confirmed: zero direct `log_action(...)` calls exist anywhere in the codebase for these two specific action
strings outside `services/case_evolution.py` (the string appears once more, in a comment in
`routers/smart_intake.py`, documenting the migration — not a live call).

## Invariant 5 — One provenance / correlation chain

Every emission call site reads `correlation_id` from the same source
(`shared/ai_provenance.py::current_correlation_id()`, via `services/event_bus.py::emit_durable`), and that id
survives unchanged from the `events` table row through `Event.correlation_id` into every consequence's own
audit call. Proven at the RAW-ROW level (not just the hand-built-`Event` level, which is all prior sprints
ever proved) by this sprint's new
`test_full_chain_correlation_id_flows_from_raw_row_to_audit_call` — a row inserted with
`correlation_id="corr-real-1"` produces `log_action` calls whose OWN `correlation_id` kwarg is the identical
string, with no intermediate hop regenerating or dropping it.

## Invariant 6 — One replay path, deterministic

Replaying the identical event (same `event_id`) through `handle_case_changed` — whether via a hand-built
`Event` (Sprints 001-003's own tests) or via a REAL `dispatch_pending_events()` call re-processing the same
row (this sprint's own new proof) — always produces the SAME outcome: already-`completed` consequences are
skipped, zero new writes occur, zero new audit rows are created. Both entry points converge on the identical
`(event_id, consequence_name)` idempotency check — there is only one replay path, not two independently-
behaving ones.

## Invariant 7 — Consequences never cascade into further business events

A structural invariant this certification checked and now enforces: no consequence executor in
`services/case_evolution.py` emits a further Event Bus event. Verified by grepping the module's own source for
`emit_durable(`, `bus.publish(`, `bus.publish_async(`, `event_bus.emit(` — zero matches. This is WHY
`NEW_EVIDENCE_REGISTERED` and `DOCUMENT_ACCEPTED` never trigger each other despite both originating from the
same `finalize_intake_job` call (see Event Coverage Matrix) — each event's consequence list is a fixed, flat
set, never a cascading graph. This was a deliberate design choice from Sprint 001 onward (never explicitly
named as an "invariant" in writing before this sprint) — stated here for the first time as a certified
architectural property, not merely an incidental fact. Enforced going forward by
`tests/test_delta_sprint004_certification.py::test_consequences_never_emit_further_business_events`.

## What is deliberately NOT covered by these invariants — named, not hidden

The 14 `EventType` members outside Case Evolution's own domain (see Event Coverage Matrix) have their OWN
separate ownership stories — Case Pipeline (`PREDMET_KREIRAN`), Genome's own audit handler (`GENOME_UPDATED`),
Intake job-lifecycle handling (`DOCUMENT_JOB_FAILED`), and 2 events with a KNOWN, pre-existing, still-open
durability gap (`ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN`, Project Sentinel's `SENT-001`, not this sprint's own
finding and not closed here — a different program's own tracked debt). These invariants apply strictly to the
6 events Case Evolution Engine actually owns; extending them to the other 14 would require folding
independently-established systems together, a real architecture decision outside a 2-agent certification
sprint's scope.

## Conclusion

All 7 invariants hold, verified by code inspection AND by tests that exercise the REAL dispatch path (not
just hand-built event objects) for the first time this program. No invariant violation was found. The
architecture, as certified, is canonical for the 6 events it claims ownership of.
