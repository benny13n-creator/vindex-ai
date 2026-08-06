# Case Evolution Registry — the canonical registry for `services/case_evolution.py` (living document, updated by whichever program extends the engine)

Built by Program Delta (Sprints 001-004); extended by Program Omega starting Sprint 002 — the Case Evolution
Engine itself is a shared, canonical piece of infrastructure, not owned exclusively by the program that built
it. Any future program adding a wired event updates THIS file, the same way Delta's own sprints did.

**Sprint 001** (2026-08-05) wired `DOCUMENT_ACCEPTED`. **Sprint 002** (2026-08-05, "Canonical Event Migration
I") wired 4 more: `REVIEW_ACCEPTED`, `REVIEW_REJECTED`, `NEW_CLIENT_LINKED`, `NEW_EVIDENCE_REGISTERED`.
**Sprint 003** (2026-08-05, "Canonical Event Migration II — Complete Event Convergence") wires the last
remaining event (`ROCISTE_ZAKAZANO`) and migrates the last 2 direct-orchestration call sites (Pipeline A's own
Genome/Evidence triggers, `routers/rocista.py`'s own Genome trigger) — see `EVENT_MIGRATION_REPORT_SPRINT_003.md`
and `ORCHESTRATOR_OWNERSHIP_REPORT_SPRINT_003.md` for full detail. Sprint 004 forensically CERTIFIED all 6
events wired at that point had zero bypasses. **Program Omega, Sprint 002** (2026-08-06, "Case Intelligence
Aggregation Engine") wires a 7th event, `DOCUMENT_BATCH_COMPLETED` — see its own WIRED section below and
`docs/omega/CASE_REFRESH_ENGINE_SPEC.md` for full detail. This registry's own repeated Task-3-style audits
have confirmed, every time, that the remaining `EventType` members are either dead (never emitted, no handler
— out of Case Evolution's domain) or already owned by a different, established, pre-existing orchestrator
(Case Pipeline, decision_log, proactive_alerts direct handlers) — not hidden Case Evolution bypasses.

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
| Ulaz | Emitted durably (`events` table insert, never in-process-only `emit()`) by `routers/smart_intake.py::finalize_intake_job`, once per finalize call, when 1+ documents were successfully linked into a case, AND, as of Sprint 003, by `api.py::predmet_upload_auto_analyze` (Pipeline A's own per-case upload, one document per call — replaces its own direct `asyncio.create_task(_genome_bg())`, which used a crude `asyncio.sleep(3)` heuristic this migration removes entirely). Payload: `{"dokumenti": [filenames], "trigger": "smart_intake_finalize"|"pipeline_a_upload", "correlation_id": ...}` — a real, intended side effect of convergence: Pipeline A uploads now ALSO produce a Timeline entry, which they never did before Sprint 003 (not new capability — the exact same canonical consequence set Pipeline C already gets) |
| Posledice (ordered) | 1. `genome_refresh` — reuses `routers/case_dna.py::_run_genome_background()` unchanged; verified independently (not self-reported) by confirming `predmeti.case_dna.verzija` incremented. 2. `timeline_entry` — one `predmet_hronologija` row per event (not per document — matches Genome's own existing per-finalize-call coalescing). 3. `refresh_case_actions` — added Program Omega Sprint 003 (2026-08-06), runs LAST so it always reads a freshly-refreshed Genome; reconciles `case_actions` (migration 099) against `_compute_target_actions`'s own deterministic rule output — see `docs/omega/CANONICAL_ACTION_ENGINE.md` |
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
| Posledice (ordered) | 1. `genome_refresh` — REUSES `DOCUMENT_ACCEPTED`'s own executor UNCHANGED (no new Genome capability); no-ops (`skipped_no_predmet_id`) pre-finalize. 2. `timeline_entry` — REUSES `DOCUMENT_ACCEPTED`'s own executor, parameterized via `payload["timeline_opis"]`; no-ops pre-finalize. 3. `review_confirmation_audit` — writes the domain-specific `dokument_review_resolved` audit row (migrated from a direct in-process `asyncio.create_task(log_action(...))` call this sprint), runs unconditionally. 4. `refresh_case_actions` — added Program Omega Sprint 003 (2026-08-06), REUSES the same executor as `DOCUMENT_ACCEPTED`, runs LAST |
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
| Ulaz | Emitted durably by `routers/smart_intake.py::finalize_intake_job`, same trigger condition as the direct call it replaces (`if klijent_ime:`, unconditional on whether the `predmet_klijenti` insert itself succeeded — exact behavior preserved). Payload: `{"klijent_id", "klijent_ime", "protivna_strana", "trigger"}`. Pipeline A (`api.py::predmet_upload_auto_analyze`) never had an equivalent client-link/conflict-check step of its own (confirmed by Sprint 003's own Task 1 sweep — it links a document to an ALREADY-existing case, never a new client), so this event remains Pipeline C-only, correctly not extended to Pipeline A (nothing there to migrate) |
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
| Ulaz | Emitted durably by `routers/smart_intake.py::finalize_intake_job` (per document), AND, as of Sprint 003, by `api.py::predmet_upload_auto_analyze` (Pipeline A's own per-case upload, one document per call — replaces its own direct `asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))`). Payload deliberately does NOT carry the document's extracted text (would duplicate a ~100KB blob into the durable outbox per document) — `{"dokument_id", "naziv", "trigger"}` only, `trigger` distinguishes `"smart_intake_finalize"` vs `"pipeline_a_upload"` |
| Posledice | `evidence_classification` — REUSES `routers/evidence.py::klasifikuj_i_sacuvaj` UNCHANGED (migrated from a direct in-process `asyncio.create_task(asyncio.to_thread(...))` call). Re-reads `tekst_sadrzaj` from the SAME `predmet_dokumenti` row the event's own `dokument_id` points to, rather than trusting payload — the row finalize just inserted moments before emitting |
| Idempotency pravila | `(event_id, consequence_name)` keyed, same mechanism. `event_id` differs per document (one durable outbox row per document), so no cross-document collision |
| Audit | Generic `case_evolution_consequence_completed` |
| Retry | Event Bus retry/dead-letter mechanism — same reliability improvement as `NEW_CLIENT_LINKED` above (the old fire-and-forget task silently dropped failures) |
| Verifikacija | Does NOT trust `klasifikuj_i_sacuvaj`'s own "no exception" — re-reads `predmet_dokumenti.klasifikovan_at` before/after and raises if still unset, same discipline as `genome_refresh`'s own `verzija` check |
| Rollback ponašanje | None needed — classification is idempotent (re-running writes the same derived fields) |
| Success kriterijum | `evidence_classification` completed with `result_ref` = the `dokument_id`, or a named `skipped_*` reason (`skipped_no_dokument_id`, `skipped_document_not_found`, `skipped_no_tekst_sadrzaj`) |

## ROCISTE_ZAKAZANO — WIRED (Sprint 003) — first-ever consequence, event type pre-dates Program Delta

| Field | Value |
|---|---|
| Naziv | `ROCISTE_ZAKAZANO` (`services/event_bus.py::EventType.ROCISTE_ZAKAZANO`) — existed in the Event Bus enum since before Program Delta but had ZERO handlers and was NEVER emitted anywhere (confirmed by repo-wide grep, Sprint 003's own Task 3 audit) — a genuinely dead event type until this sprint, not a previously-working mechanism |
| Vlasnik | `services/case_evolution.py::handle_case_changed` |
| Ulaz | Emitted durably by `routers/rocista.py::kreiraj_rociste` (`POST /api/rocista`), replacing its own direct `asyncio.create_task(_rociste_genome_bg())` (which used a crude `asyncio.sleep(2)` heuristic, now removed entirely). Payload: `{"sud", "datum", "trigger": "rociste_created"}` |
| Posledice | 1. `genome_refresh` — REUSES `DOCUMENT_ACCEPTED`'s own executor UNCHANGED (no new Genome capability). No `timeline_entry`: `kreiraj_rociste` never produced one before this sprint, so none is invented now (per Sprint 003's own "migrate, don't extend" mandate). 2. `refresh_case_actions` — added later the same sprint (Program Omega Sprint 003, Canonical Action Engine) once the new deterministic action model existed; a new hearing directly feeds Rule 1 (`PRIPREMITI_PODNESAK`) |
| Idempotency / Retry / Audit | Identical mechanism to every other wired event — `(event_id, consequence_name)` keyed, Event Bus retry/dead-letter, generic `case_evolution_consequence_completed` audit |
| Rollback ponašanje | None needed — same reasoning as `DOCUMENT_ACCEPTED`'s own `genome_refresh` |
| Success kriterijum | `genome_refresh` completed with a verified `result_ref` (the new `case_dna.verzija`) |
| Deliberately NOT migrated in the same pass | `routers/rocista.py::azuriraj_rociste` (PATCH, rescheduling) has NO current Genome trigger at all — adding one now would be a NEW consequence for an endpoint that never had it, forbidden under "migrate, don't extend"; `hearing_followup` writes its own `predmet_hronologija`/`predmet_beleske`/`predmet_istorija` rows directly and synchronously as its PRIMARY requested action (not a reactive consequence of a case-changing event — same category as `finalize_intake_job`'s own document-linking work), correctly left untouched |

## DOCUMENT_BATCH_COMPLETED — WIRED (Program Omega, Sprint 002, 2026-08-06) — new event type, batch-scoped

| Field | Value |
|---|---|
| Naziv | `DOCUMENT_BATCH_COMPLETED` (`services/event_bus.py::EventType.DOCUMENT_BATCH_COMPLETED`) — new this sprint, not a pre-existing dead declaration |
| Vlasnik | `services/case_evolution.py::handle_case_changed` |
| Ulaz | Emitted durably by `routers/smart_intake.py::finalize_intake_jobs_batch` (`POST /jobs/finalize-batch`), ONCE per unique `predmet_id` touched by the batch — never once per job/document. Payload carries the emitter's own already-verified batch facts (`dokumenata_dodato`, `dokumenti_za_proveru`, `rokovi_dodati`, `job_ids`) PLUS a "before" Genome snapshot (`pre_verzija`, `pre_kontradikcije`, `pre_dogadjaji`) captured at emission time, before any refresh runs — durable, so it survives a crash/retry unchanged |
| Posledice (ordered) | 1. `genome_refresh` — REUSES `DOCUMENT_ACCEPTED`'s own executor UNCHANGED. 2. `timeline_entry` — added Program Omega Sprint 003 (2026-08-06); REUSES `DOCUMENT_ACCEPTED`'s own executor, parameterized via `payload["timeline_opis"]` — closes a real gap Sprint 003 found: once per-job `DOCUMENT_ACCEPTED` emission is suppressed during batch processing (see `emit_document_accepted` below), batch-processed documents would otherwise get ZERO timeline entries. 3. `case_intelligence_summary` — diffs `case_dna.kontradikcije`/`datumi_kljucni` against the payload's own "before" snapshot, calls Core Consolidation's own canonical `calculate_procesni_rizik`/`identify_case_problems` (never a second competing algorithm), writes one durable, sourced row to `case_intelligence_summaries` (migration 098) plus a domain-specific `case_intelligence_refreshed` audit row. 4. `refresh_case_actions` — added Program Omega Sprint 003, runs LAST |
| `emit_document_accepted` fix (Program Omega Sprint 003) | `_finalize_intake_job_core` gained a keyword-only `emit_document_accepted: bool = True` parameter (default preserves single-job endpoint behavior); `finalize_intake_jobs_batch` passes `False`, so a 500-document single-case batch no longer ALSO fires 500 separate `DOCUMENT_ACCEPTED` genome_refreshes on top of this event's own one — the true fix completing `OMEGA-001`'s closure (see `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`'s own amendment) |
| Idempotency pravila | Identical `(event_id, consequence_name)` mechanism. Ordering WITHIN one event's own consequence list is a hard sequential guarantee (`handle_case_changed`'s own for-loop) — `case_intelligence_summary` is guaranteed to run AFTER `genome_refresh` completes for the SAME event, so it always reads freshly-refreshed `case_dna` |
| Retry / crash recovery | A crash after `genome_refresh` completes but before `case_intelligence_summary` finishes does NOT redo the Genome recompute on retry (already marked `completed`) — only the summary step reruns, matching the mission's own "nastavlja gde je stalo" requirement |
| Why this closes `OMEGA-001` | Program Omega Sprint 001 found Genome recomputing once per finalize call within a same-case batch (up to N times for N documents). This event is emitted ONCE per case per batch (not per job), so a 500-document single-case batch now produces exactly ONE Genome recompute, not 500 |
| Rollback ponašanje | None needed — each consequence is independently idempotent and safe to leave partially applied, same reasoning as every other wired event |
| Success kriterijum | Both consequences `completed`; one `case_intelligence_summaries` row exists, every number in it traceable to a real underlying query or the emitter's own already-verified payload (Agent 3's own "no conclusion without source" rule) |

## The remaining 3 mapped events — still DECLARED, NOT WIRED

| Event | Where it would originate | Why not wired yet |
|---|---|---|
| `DOCUMENT_MODIFIED` | A document's classification/content changes post-acceptance (no current mechanism supports re-classifying an already-filed document) | No existing trigger point to hang this off of yet — building one is new functionality |
| `CONFIDENCE_DROPPED` | A document/entity's confidence falls below `AUTO_ACCEPT_THRESHOLD` (Sprint 003's own Confidence Graph) | No consequence currently exists beyond the already-correct review-queue routing (Sprint 003/004) — nothing proven to be missing yet |
| `MANUAL_CORRECTION_APPLIED` | `shared/intake_documents.py::correct_entity()` | Already writes its own `write_processing_outcome`/audit trail (Sprint 004) — no additional consequence identified as missing |

## Registry Audit — every `EventType` member accounted for (updated, Program Omega Sprint 002)

`services/event_bus.py::EventType` has **21 members total** (was 20 as of Program Delta Sprint 004's own
certification; Program Omega Sprint 002, 2026-08-06, added `DOCUMENT_BATCH_COMPLETED`, the 21st — see its own
WIRED section above). Pinned going forward by `tests/test_delta_sprint004_certification.py::
test_event_type_total_member_count_matches_documentation`, which fails if the enum ever changes without this
doc being updated. This registry documents the **7** that are wired to Case Evolution's own domain — a
business event whose consequence is "what should automatically follow." The other 14 are explicitly NOT Case
Evolution's domain, listed here so "100% match" means something precise rather than silently ignoring them:

| Event | Real owner | Why it's NOT a Case Evolution gap |
|---|---|---|
| `PREDMET_KREIRAN` | `services/event_bus.py::on_predmet_kreiran` → `services/case_pipeline.py::run_case_pipeline` | A separate, established, already-proven-idempotent orchestrator (Project Sentinel, 2026-08-03) — folding Case Pipeline into Case Evolution would be a major architecture change, correctly out of a 2-agent sprint's scope, not a hidden bypass |
| `DOKUMENT_UPLOADOVAN` | `services/event_bus.py::on_dokument_uploadovan` (writes a `decision_log` entry) | Has a registered handler; confirmed by grep to be NEVER actually emitted anywhere in the repo — dead code, not a Case Evolution gap |
| `ROK_DODAN` | No production handler | Appears ONLY in test files simulating a generic broken-handler scenario (`tests/test_phoenix_reliability_failure_recovery.py`); never emitted in real code |
| `ROK_KRITICAN` | `services/event_bus.py::on_rok_kritican` → `shared/proactive_alerts.py` | Emitted in-process (`routers/matter_intel.py`) — Project Sentinel's own still-open `SENT-001` (durability gap), a KNOWN, previously-documented finding, not newly discovered here and not this sprint's scope to close |
| `STRATEGIJA_GENERISANA` | None | No handler, never emitted — fully dead |
| `ANALIZA_ZAHTEVANA` | None | No handler, never emitted — fully dead |
| `HEALTH_SCORE_PROMENJEN` | `services/event_bus.py::on_health_score_promenjen` → `shared/proactive_alerts.py` | Has its own registered handler; same durability profile as `ROK_KRITICAN` (`SENT-001`) |
| `GENOME_UPDATED` | `services/event_bus.py::on_genome_updated` (writes audit) | Already durably emitted (`routers/case_dna.py`), already has its own dedicated handler since Faza 1.2 (2026-07-18) — its own established mechanism, not a gap |
| `DOCUMENT_JOB_ENQUEUED` | Intake job lifecycle marker (migration 073 RPC) | Purely informational, no handler, reaches `dispatch_pending_events` and is marked dispatched with zero effect — not a "case changed, what follows" business event |
| `DOCUMENT_JOB_COMPLETED` | Intake job lifecycle marker (migration 073 RPC) | Same reasoning as `DOCUMENT_JOB_ENQUEUED` |
| `DOCUMENT_JOB_FAILED` | `services/event_bus.py::on_document_job_failed` | The one job-lifecycle event with a REAL consequence (a `proactive_alerts` row) — already has its own dedicated handler since Project Sentinel (2026-08-03), unrelated to Case Evolution's own 6 events |
| `DOCUMENT_MODIFIED` | none — declared, not wired | Case Evolution's own domain, no proven consequence gap yet (see table above) |
| `CONFIDENCE_DROPPED` | none — declared, not wired | Same |
| `MANUAL_CORRECTION_APPLIED` | none — declared, not wired | Same |

**Result: registry is accurate.** Every `EventType` with a genuine, currently-needed reactive consequence
(6 of 20) is wired to `handle_case_changed` and documented above. No registry entry names a consequence that
doesn't exist in code, and no wired consequence in code is undocumented (enforced by
`tests/test_delta_sprint004_certification.py::test_registry_100_percent_matches_event_bus_wiring` and
`tests/test_delta_sprint003_full_convergence.py::test_every_consequence_registry_event_documented_in_case_evolution_registry_md`,
both of which fail on future drift).

## Task 3 finding, historical: scattered "what happens next" call sites, ALL NOW MIGRATED

Found by direct grep for `_run_genome_background`, `klasifikuj_i_sacuvaj`, `_run_conflict_check`,
`create_proactive_alert`, and inline task/alert-creation patterns, across all 3 Delta sprints combined:

| Call site | What it decided | Migrated? |
|---|---|---|
| `routers/smart_intake.py::finalize_intake_job` — Genome refresh | Direct `asyncio.create_task(_genome_bg())` | **Yes** (Sprint 001) — durable `DOCUMENT_ACCEPTED` |
| `routers/smart_intake.py::finalize_intake_job` — Evidence Vault auto-classify | Direct `asyncio.create_task(_evidence_classify_bg())` | **Yes** (Sprint 002) — durable `NEW_EVIDENCE_REGISTERED` |
| `routers/smart_intake.py::finalize_intake_job` — conflict-check | Direct `asyncio.create_task(_conflict_check_bg())` | **Yes** (Sprint 002) — durable `NEW_CLIENT_LINKED` |
| `routers/smart_intake.py::resolve_job_review` — review-confirmation audit | Direct `asyncio.create_task(log_action("dokument_review_resolved", ...))` | **Yes** (Sprint 002) — durable `REVIEW_ACCEPTED` |
| `api.py::predmet_upload_auto_analyze` (Pipeline A) — Evidence Vault auto-classify | Direct `asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))` | **Yes** (Sprint 003) — durable `NEW_EVIDENCE_REGISTERED` |
| `api.py::predmet_upload_auto_analyze` (Pipeline A) — Genome refresh | Direct `asyncio.create_task(_genome_bg())`, `asyncio.sleep(3)` heuristic | **Yes** (Sprint 003) — durable `DOCUMENT_ACCEPTED` |
| `routers/rocista.py::kreiraj_rociste` — Genome refresh | Direct `asyncio.create_task(_rociste_genome_bg())`, `asyncio.sleep(2)` heuristic | **Yes** (Sprint 003) — durable `ROCISTE_ZAKAZANO` |

**Zero remaining direct-call bypass of the 3 functions Case Evolution's own executors wrap**
(`_run_genome_background`, `klasifikuj_i_sacuvaj`, `_run_conflict_check`) — proven by repo-wide grep, enforced
by `tests/test_delta_sprint003_full_convergence.py::test_no_new_direct_call_bypass_of_canonical_consequence_functions`.
The ONE remaining direct caller of `_run_conflict_check` outside `services/case_evolution.py` is
`routers/intake.py`'s own pre-existing `POST /api/intake/conflict-check` HTTP endpoint — a user-initiated,
synchronous query-and-answer action (a lawyer explicitly asks "check now", gets an immediate response), not a
reactive consequence of a case-changing event, deliberately NOT migrated (see Orchestrator Ownership Report).
