# Event Coverage Matrix — Program Delta, Sprint 004 (2026-08-06)

Orchestration Certification, Phase 1 (Complete Event Census) + Phase 3 (Consequence Certification). Every
claim below is verified against live code, run at certification time — not narrative, not documentation
copied forward:

```
python -c "from services.event_bus import EventType, bus; ..."
```
`services.event_bus.EventType` has **20 members** (not 19 — Sprint 003's own registry text undercounted by
one; corrected in `CASE_EVOLUTION_REGISTRY.md` by this sprint, see Self-Consistency section of the
Certification Report).

## Phase 1 — Complete Event Census

| Event | Emitted by | Durable? | Handler(s) | Uses Event Bus | Uses Case Evolution Engine | Audit | Provenance | correlation_id |
|---|---|---|---|---|---|---|---|---|
| `DOCUMENT_ACCEPTED` | `routers/smart_intake.py::finalize_intake_job`, `api.py::predmet_upload_auto_analyze` | ✔ (`emit_durable`) | `handle_case_changed` | ✔ | ✔ | ✔ generic + underlying writes | ✔ `result_ref` per consequence | ✔ |
| `REVIEW_ACCEPTED` | `routers/smart_intake.py::resolve_job_review` | ✔ | `handle_case_changed` | ✔ | ✔ | ✔ `dokument_review_resolved` + generic | ✔ | ✔ |
| `REVIEW_REJECTED` | `routers/smart_intake.py::reject_job_review` | ✔ | `handle_case_changed` | ✔ | ✔ | ✔ `dokument_review_rejected` + generic | ✔ | ✔ |
| `NEW_CLIENT_LINKED` | `routers/smart_intake.py::finalize_intake_job` | ✔ | `handle_case_changed` | ✔ | ✔ | ✔ generic + `proactive_alerts` | ✔ | ✔ |
| `NEW_EVIDENCE_REGISTERED` | `routers/smart_intake.py::finalize_intake_job`, `api.py::predmet_upload_auto_analyze` | ✔ | `handle_case_changed` | ✔ | ✔ | ✔ generic | ✔ verified via `klasifikovan_at` | ✔ |
| `ROCISTE_ZAKAZANO` | `routers/rocista.py::kreiraj_rociste` | ✔ | `handle_case_changed` | ✔ | ✔ | ✔ generic | ✔ verified via `verzija` | ✔ |
| `PREDMET_KREIRAN` | `api.py::kreiraj_predmet` | ✔ | `on_predmet_kreiran` → `run_case_pipeline` | ✔ | ✘ — owned by Case Pipeline, a DIFFERENT, independently-proven-idempotent orchestrator (Project Sentinel, 2026-08-03) | partial — Case Pipeline has its own step markers, not `case_evolution_consequences` | n/a to Case Evolution | ✔ (durable emission carries it) |
| `GENOME_UPDATED` | `routers/case_dna.py` (Genome's own internal emission, after every refresh) | ✔ | `on_genome_updated` | ✔ | ✘ — this is Genome's OWN "I changed" announcement, downstream of every `genome_refresh` consequence, not a separate business event Case Evolution needs to react to | ✔ (`genome_refresh` audit action) | ✔ | ✔ |
| `DOCUMENT_JOB_FAILED` | `fail_intake_job` RPC (migration 073, SQL-level insert) | ✔ | `on_document_job_failed` | ✔ | ✘ — Intake job-lifecycle infrastructure, resolves job owner and writes a `proactive_alerts` row; predates Program Delta, not a `predmet`-state-changing business event in Case Evolution's own sense | n/a (proactive_alerts insert failure IS durably tracked) | n/a | ✔ (row's own correlation_id, if present) |
| `ROK_KRITICAN` | `routers/matter_intel.py` (in-process `emit()`, **NOT durable**) | ✘ | `on_rok_kritican` | ✔ (in-memory only) | ✘ | partial (best-effort, no dead-letter) | n/a | ✔ (via `emit()`'s own `current_correlation_id()` fallback) |
| `HEALTH_SCORE_PROMENJEN` | `routers/matter_intel.py` (in-process `emit()`, **NOT durable**) | ✘ | `on_health_score_promenjen` | ✔ (in-memory only) | ✘ | partial (best-effort, no dead-letter) | n/a | ✔ |
| `DOKUMENT_UPLOADOVAN` | **NEVER** (confirmed by repo-wide grep — a registered handler with zero production emitters) | n/a | `on_dokument_uploadovan` (dead code — never runs) | n/a | ✘ | n/a | n/a | n/a |
| `ROK_DODAN` | **NEVER** (only appears in test files simulating a generic broken-handler scenario) | n/a | none | n/a | ✘ | n/a | n/a | n/a |
| `STRATEGIJA_GENERISANA` | **NEVER** | n/a | none | n/a | ✘ | n/a | n/a | n/a |
| `ANALIZA_ZAHTEVANA` | **NEVER** | n/a | none | n/a | ✘ | n/a | n/a | n/a |
| `DOCUMENT_JOB_ENQUEUED` | Intake job lifecycle marker only (migration 073 RPC) | ✔ (row exists) | none | n/a (unknown-type path in `dispatch_pending_events`, marked dispatched, no handler runs) | ✘ | n/a | n/a | n/a |
| `DOCUMENT_JOB_COMPLETED` | Intake job lifecycle marker only | ✔ (row exists) | none | n/a (same as above) | ✘ | n/a | n/a | n/a |
| `DOCUMENT_MODIFIED` | never (declared, no trigger point exists yet) | n/a | none | n/a | ✘ (declared-not-wired, Case Evolution's own domain) | n/a | n/a | n/a |
| `CONFIDENCE_DROPPED` | never (declared, no proven consequence gap) | n/a | none | n/a | ✘ (declared-not-wired) | n/a | n/a | n/a |
| `MANUAL_CORRECTION_APPLIED` | never (declared, `correct_entity()` already logs its own outcome directly) | n/a | none | n/a | ✘ (declared-not-wired) | n/a | n/a | n/a |

**Zero unclassified events** — all 20 members have a determined owner, emission status, and Case-Evolution-
domain verdict.

## Finding — `DOCUMENT_JOB_ENQUEUED`/`DOCUMENT_JOB_COMPLETED` reach `dispatch_pending_events` with NO handler

Both are durably written (Smart Intake job lifecycle RPCs, migration 073) and DO flow through
`dispatch_pending_events()` — but `bus._handlers` has an empty list for both, so `bus.publish_async()` returns
immediately (`if not handlers: return`) without error. This is **not a bypass** (no business consequence is
silently skipped — none was ever defined for these two purely-informational lifecycle markers) but it IS
worth naming precisely: unlike `DOKUMENT_UPLOADOVAN`/`ROK_DODAN`/etc. (never even emitted), these two ARE
emitted and dispatched, just to nobody. Confirmed harmless by reading `dispatch_pending_events`'s own code —
an event with zero handlers is marked `dispatched_at` and treated as fully successful, not retried, not
dead-lettered (correct: there is nothing to fail).

## Phase 3 — Consequence Certification, per business event

Legend: **DA** = this consequence exists and is proven; **NE** = does not exist, with reason; **N/P** = not
applicable to this event's own nature.

### DOCUMENT_ACCEPTED

| Effect | Verdict | Evidence |
|---|---|---|
| Genome | **DA** | `_consequence_genome_refresh`, verified via `case_dna.verzija` before/after |
| Timeline | **DA** | `_consequence_timeline_entry`, verified via inserted row id |
| Alerts | **NE** | No alert was ever produced by document acceptance in any pre-migration code path; inventing one now would be a new capability, forbidden by every Delta sprint's own charter |
| Tasks | **NE** | Same reasoning — no task-creation ever existed for this event |
| Audit | **DA** | `case_evolution_consequence_completed` per consequence |
| Search | **N/P** | Pinecone ingestion happens SYNCHRONOUSLY as the primary upload action, BEFORE this event is even emitted (search must be immediately available, cannot lag behind async dispatch) — not a reactive consequence by design |
| Dashboard | **N/P** | Dashboards are query-time aggregations (health scores, case lists) — nothing is "refreshed"; there is no materialized dashboard artifact for any event to invalidate |
| Firm Brain | **NE** | No auto-population mechanism exists platform-wide (confirmed: zero references to Firm Brain in `services/`) — a pre-existing, previously-documented gap (`WOW-003`, Project Synapse 2026-08-03), not a Case Evolution regression |
| Memory Graph | **NE** | No writer exists platform-wide (Operation Invisible Features, `IF-005`, 2026-08-03 — Memory Graph's only writer is itself dead) |

### REVIEW_ACCEPTED

| Effect | Verdict | Evidence |
|---|---|---|
| Genome | **DA** (conditional) | Reuses `DOCUMENT_ACCEPTED`'s own executor; runs for real only when `predmet_id` is set (post-finalize correction), no-ops otherwise — both outcomes proven by test |
| Timeline | **DA** (conditional) | Same conditional shape |
| Alerts | **NE** | Never existed for this event |
| Tasks | **NE** | Never existed |
| Audit | **DA** | `dokument_review_resolved` (domain-specific) + generic |
| Search / Dashboard / Firm Brain / Memory Graph | **N/P** / **N/P** / **NE** / **NE** | Same reasoning as `DOCUMENT_ACCEPTED` |

### REVIEW_REJECTED

| Effect | Verdict | Evidence |
|---|---|---|
| Genome | **NE** | Deliberately absent — a rejection means nothing was ever applied to the case (`intake_jobs.status` never reaches `'completed'`), so nothing needs refreshing. This is the mission's own "rollback" test, satisfied by never creating a consequence to undo |
| Timeline | **NE** | Same reasoning |
| Alerts | **NE** | Never existed |
| Tasks | **NE** | Never existed |
| Audit | **DA** | `dokument_review_rejected` |
| Search / Dashboard / Firm Brain / Memory Graph | **N/P** / **N/P** / **NE** / **NE** | Same reasoning |

### NEW_CLIENT_LINKED

| Effect | Verdict | Evidence |
|---|---|---|
| Genome | **NE** | Never existed — client-linking and Genome refresh are architecturally independent; `DOCUMENT_ACCEPTED` (a sibling event, co-emitted from the same `finalize_intake_job` call) is what actually refreshes Genome, not this event |
| Timeline | **NE** | Never existed for client-linking specifically |
| Alerts | **DA** (conditional) | `conflict_check` consequence — creates a `sukob_interesa` alert only when a real conflict is detected; `no_conflict`/`skipped_no_klijent_ime` are the non-alert outcomes, both proven by test |
| Tasks | **NE** | Never existed |
| Audit | **DA** | Generic `case_evolution_consequence_completed` + the underlying `proactive_alerts` row's own trace |
| Search / Dashboard | **N/P** | Same reasoning |
| Firm Brain | **NE** | No auto-population mechanism exists (same platform-wide gap) |
| Memory Graph | **NE** | Same platform-wide gap |

### NEW_EVIDENCE_REGISTERED

| Effect | Verdict | Evidence |
|---|---|---|
| Genome | **NE — important architectural clarification** | This event's OWN consequence list does NOT include `genome_refresh`. When a document is finalized, Genome refresh happens because `DOCUMENT_ACCEPTED` is ALSO emitted (a separate, sibling event, from the same `finalize_intake_job`/`predmet_upload_auto_analyze` call) — not because `NEW_EVIDENCE_REGISTERED` triggers it. **Consequences never cascade into further business events in this architecture** (see Architectural Invariants Report) — this is intentional, not a gap |
| Timeline | **NE** | Same clarification — `DOCUMENT_ACCEPTED`'s own `timeline_entry` covers "document accepted", not evidence-specific narrative |
| Strategy | **NE** | Strategy Engine is, and remains, exclusively user-invoked (`POST /api/strategija/*`) — auto-triggering AI strategy generation from an evidence event would be a genuinely NEW AI capability, explicitly forbidden by every Delta sprint's own charter. This directly answers the mission's own worked Scenario 4 example ("Evidence Update → ... → Strategy → ...") — that chain does NOT exist in the real architecture, and building it was never in scope |
| Alerts | **NE** | Never existed |
| Tasks | **NE** | Never existed |
| Audit | **DA** | Generic `case_evolution_consequence_completed` |
| Search / Dashboard | **N/P** | Same reasoning |
| Firm Brain / Memory Graph | **NE** | Same platform-wide gap |

### ROCISTE_ZAKAZANO

| Effect | Verdict | Evidence |
|---|---|---|
| Genome | **DA** | `genome_refresh`, reused unchanged |
| Timeline | **NE** | `kreiraj_rociste` never produced a Timeline entry before Sprint 003's migration — none invented now |
| Alerts / Tasks | **NE** | Never existed |
| Audit | **DA** | Generic `case_evolution_consequence_completed` |
| Search / Dashboard / Firm Brain / Memory Graph | **N/P** / **N/P** / **NE** / **NE** | Same reasoning as above |

## Honest summary of this certification pass

Every "DA" above traces to a named function and a named test. Every "NE" has a reason rooted in either (a)
the consequence never existed in the pre-migration code being replaced, or (b) the capability doesn't exist
anywhere in the platform yet (Firm Brain, Memory Graph auto-population — both pre-existing, previously-
documented gaps, not created or worsened by Program Delta). The mission's own worked Scenario 4 example
(Evidence → Genome → Strategy → Timeline) does NOT match the real, built architecture — stated plainly here
rather than silently reconciled, per the mission's own "ne prihvatam pretpostavke" instruction.
