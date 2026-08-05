# End-to-End Event Verification — Program Delta, Sprint 004 (2026-08-06)

Orchestration Certification, Phase 4. For each of the mission's 4 required scenarios: replay, retry,
correlation continuity, provenance continuity, audit continuity — each claim traced to a specific test, not
asserted narratively. Where the mission's own worked example doesn't match the real architecture, that
mismatch is stated plainly (see Scenario 4).

## Scenario 1 — New Predmet → Upload → OCR → Classification → Genome → Timeline → Audit → Search → Dashboard

| Step | Real mechanism | Proof |
|---|---|---|
| Upload → OCR → Classification | `finalize_intake_job`/`predmet_upload_auto_analyze`'s own primary, synchronous pipeline (unchanged by Program Delta — Program Intake's own domain, Sprints 001-007) | `tests/test_sprint002_pipeline_a_orphan_cleanup.py`, `tests/test_sprint007_bulletproof_intake.py`, unaffected by this program |
| → durable `DOCUMENT_ACCEPTED`/`NEW_EVIDENCE_REGISTERED` emission | `emit_durable`, called from both pipelines | `tests/test_delta_sprint003_full_convergence.py::test_pipeline_a_upload_endpoint_emits_both_events_durably` |
| → raw row → real dispatch → Genome + Timeline + Audit, ALL THE WAY, not hand-built | **NEW this sprint** — no prior sprint ever proved the full chain from a raw `events` row through the REAL `dispatch_pending_events()` to a completed consequence | `tests/test_delta_sprint004_certification.py::test_full_chain_raw_event_row_through_real_dispatch_to_completed_consequence` |
| Replay (same row reprocessed) | Idempotency check, `(event_id, consequence_name)` keyed | `test_full_chain_replay_same_row_produces_no_duplicate_work` |
| Retry after crash (real dispatch, not hand-built) | Second `dispatch_pending_events()` call resumes from the incomplete consequence | `test_full_chain_crash_after_one_consequence_real_dispatch_retry_resumes` |
| Correlation continuity, raw row to audit | Same `correlation_id` string, traced from the inserted row to every `log_action` call | `test_full_chain_correlation_id_flows_from_raw_row_to_audit_call` |
| Search | Synchronous Pinecone ingest, part of the PRIMARY upload action, before the event is even emitted | Unchanged since before Program Delta — `uploaded_doc/ingest.py`, exercised in the same Pipeline A/C tests above |
| Dashboard | N/P — query-time aggregation, nothing to "refresh" | See Event Coverage Matrix |

**Verdict: fully proven**, including the one genuine gap this certification closed (the raw-row-through-real-
dispatch chain).

## Scenario 2 — Review Required → Human Review → Accepted → Genome Refresh → Timeline → Audit → Alerts

| Step | Real mechanism | Proof |
|---|---|---|
| Review Required (low-confidence flagged) | Program Intake Sprint 003/004's own mechanism, unchanged | Pre-existing test suite, unaffected |
| Human Review → Accepted | `resolve_job_review` → `intake_documents.resolve_review()` (state change) → durable `REVIEW_ACCEPTED` emission | `tests/test_sprint004_review_resolve.py`, `tests/test_delta_sprint002_event_migration.py` |
| → Genome Refresh → Timeline → Audit, exactly once | `handle_case_changed`, reusing `DOCUMENT_ACCEPTED`'s own executors | `tests/test_delta_sprint002_event_migration.py::test_scenario1_review_accepted_genome_timeline_audit_exactly_once` |
| Replay / crash+retry | Same `(event_id, consequence_name)` mechanism, proven for a 3-consequence event (the largest registry entry) | `test_scenario5_crash_after_first_review_accepted_consequence_retry_resumes`, `test_scenario6_replay_shares_correlation_id_and_produces_no_new_audit` |
| Alerts | **NE** — never existed for `REVIEW_ACCEPTED`, correctly not invented | See Event Coverage Matrix |

**Verdict: fully proven** for every consequence that actually exists. The mission's own worked example lists
"Alerts" as a step; the real, certified architecture has none for this event — stated plainly, not silently
reconciled.

## Scenario 3 — Client Link → Conflict Check → Audit → Firm Brain

| Step | Real mechanism | Proof |
|---|---|---|
| Client Link | `finalize_intake_job`'s own `predmet_klijenti` insert (primary action) → durable `NEW_CLIENT_LINKED` emission | `tests/test_ztc_conflict_check_autowiring.py::test_finalize_emits_new_client_linked_durably` |
| → Conflict Check → Audit | `_consequence_conflict_check`, reusing `_run_conflict_check`/`create_proactive_alert` unchanged | `tests/test_delta_sprint002_event_migration.py::test_scenario3_client_linked_replayed_produces_same_result` |
| Replay (same event twice) | Proven: `_run_conflict_check` and `create_proactive_alert` each called exactly once across 2 dispatches | Same test |
| Firm Brain | **NE** — no auto-population mechanism exists platform-wide (confirmed: zero Firm Brain references in `services/`) | Pre-existing, previously-documented gap (`WOW-003`), not created by this program |

**Verdict: fully proven** for the consequence that exists (conflict-check + audit). Firm Brain step in the
mission's own example does not correspond to any built mechanism anywhere in the platform — named honestly,
not fabricated.

## Scenario 4 — Evidence Update → Evidence Classification → Genome → Strategy → Timeline → Audit

**This scenario's own worked example does not match the real, certified architecture — the most important
finding of this phase.**

| Step named in the mission | What actually happens | Why |
|---|---|---|
| Evidence Classification | `_consequence_evidence_classify`, verified via `klasifikovan_at` | `tests/test_delta_sprint002_event_migration.py` (executor tests), `tests/test_delta_sprint003_full_convergence.py` (parallel test) |
| → Genome | **DOES NOT HAPPEN as a consequence of `NEW_EVIDENCE_REGISTERED`.** Genome refresh only happens because `DOCUMENT_ACCEPTED` is ALSO emitted, separately, from the same `finalize_intake_job`/`predmet_upload_auto_analyze` call — a sibling event, not a downstream trigger of evidence registration | Architectural Invariant 7 — consequences never cascade into further business events |
| → Strategy | **DOES NOT EXIST for ANY event.** Strategy Engine remains exclusively user-invoked (`POST /api/strategija/*`); no event in `CONSEQUENCE_REGISTRY` has ever triggered it | Confirmed by reading `CONSEQUENCE_REGISTRY` directly — no Strategy import or call anywhere in `services/case_evolution.py` |
| → Timeline | Same clarification as Genome — `DOCUMENT_ACCEPTED`'s own `timeline_entry` is what actually produces a Timeline row, not evidence registration itself | Event Coverage Matrix |
| → Audit | **DA** — `evidence_classification`'s own generic audit row | `tests/test_delta_sprint002_event_migration.py` |

**Verdict: the audit step is proven; the Genome/Strategy/Timeline cascade described in the mission's own
example was never built and does not exist.** In the COMMON case (a document accepted with evidence
classification enabled), a lawyer WOULD observe Genome and Timeline updating "around the same time" as
evidence classification — but this is two INDEPENDENT sibling events firing from the same trigger point, not
evidence classification causing Genome/Strategy to run. Building an actual evidence→Genome→Strategy cascade
would be new orchestration logic (an event triggering another event), explicitly forbidden by every Delta
sprint's own charter ("ne uvoditi nove... mogućnosti — migrirati, ne proširivati") and by Architectural
Invariant 7 above. This certification reports the mismatch rather than silently building the cascade to make
the scenario "pass."

## Summary

3 of 4 scenarios match the mission's own worked example exactly (once "Alerts"/"Firm Brain" are correctly
marked N/A for the events that never had them). Scenario 4 does not match — evidence classification does not
cascade into Genome/Strategy/Timeline, by design (Architectural Invariant 7). This is reported as a finding,
not corrected by adding new orchestration capability, per the sprint's own explicit prohibition against new
functionality.
