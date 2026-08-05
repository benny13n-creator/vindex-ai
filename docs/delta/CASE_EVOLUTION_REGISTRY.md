# Case Evolution Registry — Program Delta (living document, updated each sprint)

**Sprint 001** (2026-08-05) wired `DOCUMENT_ACCEPTED`. **Sprint 002** (2026-08-05, "Canonical Event Migration
I") wires 4 more: `REVIEW_ACCEPTED`, `REVIEW_REJECTED`, `NEW_CLIENT_LINKED`, `NEW_EVIDENCE_REGISTERED`.

**Read this file first for any future Program Delta sprint** — per the founder's own closing instruction,
future Delta work should read only `docs/delta/*` (this registry + prior sprint reports), not re-derive the
full Nexus→Sentinel→Atlas→Ledger→Migration→Intake history. This is the living source of truth for every
event that changes a `predmet`'s state and what automatically follows.

**One event, one definition** — every row below has exactly one owner, one canonical entry point
(`services/case_evolution.py::handle_case_changed`, registered per event type in
`services/event_bus.py::EventBus._register_defaults`), and no other module may independently decide
consequences for it.

---

## DOCUMENT_ACCEPTED — WIRED (Sprint 001)

| Field | Value |
|---|---|
| Naziv | `DOCUMENT_ACCEPTED` (`services/event_bus.py::EventType.DOCUMENT_ACCEPTED`) |
| Vlasnik | `services/case_evolution.py::handle_case_changed` — the ONE canonical dispatcher; no other module decides consequences for this event type |
| Ulaz | Emitted durably (`events` table insert, never in-process-only `emit()`) by `routers/smart_intake.py::finalize_intake_job`, once per finalize call, when 1+ documents were successfully linked into a case. Payload: `{"dokumenti": [filenames], "trigger": "smart_intake_finalize", "correlation_id": ...}` |
| Posledice (ordered) | 1. `genome_refresh` — reuses `routers/case_dna.py::_run_genome_background()` unchanged; verified independently (not self-reported) by confirming `predmeti.case_dna.verzija` incremented. 2. `timeline_entry` — one `predmet_hronologija` row per event (not per document — matches Genome's own existing per-finalize-call coalescing) |
| Idempotency pravila | Keyed by the event's own durable `events.id` (`event_id`), never `correlation_id` (which can span multiple distinct operations). One row per `(event_id, consequence_name)` in `case_evolution_consequences` (migration 096), `UNIQUE(event_id, consequence_name)` DB-enforced. A consequence already `completed` is never re-executed |
| Audit | `log_action("case_evolution_consequence_completed", ...)` per consequence, carrying the event's own `correlation_id` — added to `AUDITABLE_ACTIONS` this sprint |
| Retry | Handled entirely by the EXISTING Event Bus durable-outbox retry/dead-letter mechanism (`dispatch_pending_events`, `MAX_DISPATCH_ATTEMPTS=5`, migration 073/091) — no new retry machinery built; a failed consequence propagates its exception so that mechanism's own retry takes over, and the NEXT attempt's `handle_case_changed` call skips every already-`completed` consequence |
| Rollback ponašanje | None needed by design — each consequence is independently idempotent and safe to leave partially applied (a completed `genome_refresh` with a still-pending `timeline_entry` is a valid, non-corrupt intermediate state; the next retry simply finishes the remaining consequence) |
| Success kriterijum | Every consequence in the registry for this event ends in `case_evolution_consequences.status='completed'`, each with its own verified `result_ref` and its own audit row sharing the event's `correlation_id` |

## REVIEW_ACCEPTED — WIRED (Sprint 002)

| Field | Value |
|---|---|
| Naziv | `REVIEW_ACCEPTED` (`services/event_bus.py::EventType.REVIEW_ACCEPTED`) |
| Vlasnik | `services/case_evolution.py::handle_case_changed` — same canonical dispatcher, no separate mechanism |
| Ulaz | Emitted durably by `routers/smart_intake.py::resolve_job_review` (`POST /jobs/{job_id}/review/resolve`) every time a human confirms a low-confidence classification/extraction — both BEFORE the job's first finalize (`predmet_id` still `None`, the common case) and for a post-finalize correction (`predmet_id` already set — this sprint FIXED a bug where this branch previously returned early without even resolving the review, see Event Migration Report). Payload: `{"intake_job_id", "prior_status", "job_status_advanced", "review_resolved_now", "trigger"}` |
| Posledice (ordered) | 1. `genome_refresh` — REUSES `DOCUMENT_ACCEPTED`'s own executor UNCHANGED (no new Genome capability); no-ops (`skipped_no_predmet_id`) pre-finalize. 2. `timeline_entry` — REUSES `DOCUMENT_ACCEPTED`'s own executor, parameterized via `payload["timeline_opis"]`; no-ops pre-finalize. 3. `review_confirmation_audit` — writes the domain-specific `dokument_review_resolved` audit row (migrated from a direct in-process `asyncio.create_task(log_action(...))` call this sprint), runs unconditionally |
| Idempotency pravila | Identical mechanism to `DOCUMENT_ACCEPTED` — `(event_id, consequence_name)` keyed, `case_evolution_consequences` |
| Audit | `dokument_review_resolved` (domain-specific, this sprint) + generic `case_evolution_consequence_completed` per consequence |
| Retry | Same Event Bus retry/dead-letter mechanism, unchanged |
| Rollback ponašanje | None needed — pre-finalize acceptance has no consequence to roll back (both no-op); post-finalize acceptance's genome/timeline consequences are independently safe to leave partially applied, same reasoning as `DOCUMENT_ACCEPTED` |
| Success kriterijum | Same shape as `DOCUMENT_ACCEPTED` — every consequence `completed` with a verified `result_ref` |

## REVIEW_REJECTED — WIRED (Sprint 002) — first canonical definition, previously blocked (`INTAKE-012`)

| Field | Value |
|---|---|
| Naziv | `REVIEW_REJECTED` (`services/event_bus.py::EventType.REVIEW_REJECTED`) |
| Vlasnik | `services/case_evolution.py::handle_case_changed` |
| Ulaz | Emitted durably by `routers/smart_intake.py::reject_job_review` (`POST /jobs/{job_id}/review/reject`, NEW this sprint — the mission's own "napraviti jednu definiciju" instruction). Blocked (409) if the job is already finalized — rollback of an already-created case is a genuine business decision, out of scope. Payload: `{"intake_job_id", "review_resolved_now", "job_status_rejected", "trigger"}` |
| Posledice | ONLY `review_rejection_audit` — writes `dokument_review_rejected`. Deliberately NO `genome_refresh`/`timeline_entry` — see "šta se poništava" below |
| Šta se poništava | The automatic status-advance accept would have triggered — `intake_jobs.status` goes to `'rejected'` (migration 097, new CHECK value), NEVER `'completed'`, so finalize's existing status gate stays permanently closed for this job |
| Šta ostaje | The original `extracted_entities` value, UNCHANGED — same immutability principle as `correct_entity` (never delete, only add a correction) |
| Šta se replanira | NOTHING automatically — a human must call `POST /entities/{id}/correct` with the right value, or re-upload. Automatic re-OCR/re-classification is a genuinely new capability, correctly out of this sprint's scope |
| Šta ulazi u audit | `dokument_review_rejected`, carrying `review_resolved_now`/`job_status_rejected` |
| Šta dobija novi correlation_id | The `REVIEW_REJECTED` event's own `correlation_id`, inherited from the request context exactly like every other emission this sprint |
| Idempotency / Retry | Same mechanism as every other wired event |
| Rollback ponašanje | Trivial by construction — nothing was ever applied to the case (job never reached `'completed'`), so there is nothing TO roll back. This IS the mission's own "Rollback posledica" test, satisfied by never having created a consequence to undo |
| Success kriterijum | `review_rejection_audit` completed; `intake_jobs.status='rejected'`; finalize permanently blocked for this job until a human corrects and/or re-uploads |

## NEW_CLIENT_LINKED — WIRED (Sprint 002)

| Field | Value |
|---|---|
| Naziv | `NEW_CLIENT_LINKED` (`services/event_bus.py::EventType.NEW_CLIENT_LINKED`) |
| Vlasnik | `services/case_evolution.py::handle_case_changed` |
| Ulaz | Emitted durably by `routers/smart_intake.py::finalize_intake_job`, same trigger condition as the direct call it replaces (`if klijent_ime:`, unconditional on whether the `predmet_klijenti` insert itself succeeded — exact behavior preserved). Payload: `{"klijent_id", "klijent_ime", "protivna_strana", "trigger"}` |
| Posledice | `conflict_check` — REUSES `routers/intake.py::_run_conflict_check` + `shared/proactive_alerts.py::create_proactive_alert` UNCHANGED (migrated from a direct in-process `asyncio.create_task(_conflict_check_bg())` call) |
| Idempotency pravila | `(event_id, consequence_name)` keyed, same mechanism |
| Audit | Generic `case_evolution_consequence_completed`; the underlying `proactive_alerts` insert (when a conflict is found) carries its own trace |
| Retry | Event Bus retry/dead-letter — a genuine RELIABILITY IMPROVEMENT over the code this replaces: the old in-process task silently dropped a failure forever (logged, never retried); a failed `conflict_check` consequence now propagates and gets retried up to `MAX_DISPATCH_ATTEMPTS=5` before dead-lettering, never silent |
| Rollback ponašanje | None needed — a conflict-check alert is additive (informs the lawyer), never mutates the case itself |
| Success kriterijum | `conflict_check` completed with `result_ref` in `{"no_conflict", "conflict_alert_created", "skipped_no_klijent_ime"}` |

## NEW_EVIDENCE_REGISTERED — WIRED (Sprint 002)

| Field | Value |
|---|---|
| Naziv | `NEW_EVIDENCE_REGISTERED` (`services/event_bus.py::EventType.NEW_EVIDENCE_REGISTERED`) |
| Vlasnik | `services/case_evolution.py::handle_case_changed` |
| Ulaz | Emitted durably by `routers/smart_intake.py::finalize_intake_job`, PER DOCUMENT (unlike `DOCUMENT_ACCEPTED`'s once-per-call granularity — evidence classification is inherently per-document, matching the call it replaces). Payload deliberately does NOT carry the document's extracted text (would duplicate a ~100KB blob into the durable outbox per document) — `{"dokument_id", "naziv", "trigger"}` only |
| Posledice | `evidence_classification` — REUSES `routers/evidence.py::klasifikuj_i_sacuvaj` UNCHANGED (migrated from a direct in-process `asyncio.create_task(asyncio.to_thread(...))` call). Re-reads `tekst_sadrzaj` from the SAME `predmet_dokumenti` row the event's own `dokument_id` points to, rather than trusting payload — the row finalize just inserted moments before emitting |
| Idempotency pravila | `(event_id, consequence_name)` keyed, same mechanism. `event_id` differs per document (one durable outbox row per document), so no cross-document collision |
| Audit | Generic `case_evolution_consequence_completed` |
| Retry | Event Bus retry/dead-letter mechanism — same reliability improvement as `NEW_CLIENT_LINKED` above (the old fire-and-forget task silently dropped failures) |
| Verifikacija | Does NOT trust `klasifikuj_i_sacuvaj`'s own "no exception" — re-reads `predmet_dokumenti.klasifikovan_at` before/after and raises if still unset, same discipline as `genome_refresh`'s own `verzija` check |
| Rollback ponašanje | None needed — classification is idempotent (re-running writes the same derived fields) |
| Success kriterijum | `evidence_classification` completed with `result_ref` = the `dokument_id`, or a named `skipped_*` reason (`skipped_no_dokument_id`, `skipped_document_not_found`, `skipped_no_tekst_sadrzaj`) |

## The remaining 3 mapped events — still DECLARED, NOT WIRED

| Event | Where it would originate | Why not wired yet |
|---|---|---|
| `DOCUMENT_MODIFIED` | A document's classification/content changes post-acceptance (no current mechanism supports re-classifying an already-filed document) | No existing trigger point to hang this off of yet — building one is new functionality |
| `CONFIDENCE_DROPPED` | A document/entity's confidence falls below `AUTO_ACCEPT_THRESHOLD` (Sprint 003's own Confidence Graph) | No consequence currently exists beyond the already-correct review-queue routing (Sprint 003/004) — nothing proven to be missing yet |
| `MANUAL_CORRECTION_APPLIED` | `shared/intake_documents.py::correct_entity()` | Already writes its own `write_processing_outcome`/audit trail (Sprint 004) — no additional consequence identified as missing |

## Task 3 finding: existing scattered "what happens next" call sites

Found by direct grep for `_run_genome_background`, `create_proactive_alert`, and inline task/alert-creation
patterns, scoped to Agent 1's allowed systems (Intake, Human Review, Genome, Timeline, Event Bus) — repo-wide
platform analysis explicitly out of scope:

| Call site | What it decides | Migrated? |
|---|---|---|
| `routers/smart_intake.py::finalize_intake_job` — Genome refresh | Direct `asyncio.create_task(_genome_bg())` | **Yes** (Sprint 001) — durable `DOCUMENT_ACCEPTED` |
| `routers/smart_intake.py::finalize_intake_job` — Evidence Vault auto-classify | Direct `asyncio.create_task(_evidence_classify_bg())` | **Yes** (Sprint 002) — durable `NEW_EVIDENCE_REGISTERED` |
| `routers/smart_intake.py::finalize_intake_job` — conflict-check | Direct `asyncio.create_task(_conflict_check_bg())` | **Yes** (Sprint 002) — durable `NEW_CLIENT_LINKED` |
| `routers/smart_intake.py::resolve_job_review` — review-confirmation audit | Direct `asyncio.create_task(log_action("dokument_review_resolved", ...))` | **Yes** (Sprint 002) — durable `REVIEW_ACCEPTED` |
| `api.py::predmet_upload` (Pipeline A, per-case upload) — Genome refresh | Direct `_run_genome_background()` call, same shape as the one migrated in Pipeline C | No — Pipeline A remains out of scope (mirrors Program Intake's own "Pipeline C first" precedent); a real, named follow-up (`DELTA-002`) |
| `routers/rocista.py` (hearing scheduling) — Genome refresh trigger | Direct `_run_genome_background()` call | No — same reasoning, same follow-up (`DELTA-002`) |

**Why Pipeline A/`rocista.py` still weren't migrated this sprint**: both are a DIFFERENT feature surface
(case upload / hearing scheduling) than any of this sprint's 4 named events (Intake finalize, Human Review,
client-linking, evidence-registration) — migrating them is mechanical (same event type, same registry,
different emission call site) but correctly named as a bounded future Delta sprint rather than expanded into
under this sprint's hard 2-agent budget.
