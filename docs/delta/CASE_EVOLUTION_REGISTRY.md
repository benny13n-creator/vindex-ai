# Case Evolution Registry — Program Delta, Sprint 001 (2026-08-05)

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

## The other 7 mapped events — DECLARED, NOT WIRED (Task 1's own explicit instruction: prove one entry point exists, do not implement all)

Each of these has a real `EventType` value (`services/event_bus.py`) — a genuine "one entry point exists"
claim, checkable by anyone (the enum member exists, `CONSEQUENCE_REGISTRY.get(EventType.X, [])` returns `[]`
today, meaning: no consequences are wired, but if/when they are, they go through this SAME dispatcher, never
a new one).

| Event | Where it would originate | Why not wired this sprint |
|---|---|---|
| `DOCUMENT_MODIFIED` | A document's classification/content changes post-acceptance (no current mechanism supports re-classifying an already-filed document) | No existing trigger point to hang this off of yet — building one is new functionality, out of this sprint's scope |
| `NEW_CLIENT_LINKED` | `predmet_klijenti` insert (Program Intake Sprint 006's Ownership Resolution, or the older CRM wizard) | Consequences (if any — e.g. conflict-check?) already exist as a direct call in `finalize_intake_job` (Zero-Touch Case's own conflict-check background task) — migrating that specific call is a bounded future Delta task, named not attempted here to keep this sprint's footprint to the one proven event |
| `NEW_EVIDENCE_REGISTERED` | Evidence Vault auto-classify (`routers/evidence.py::klasifikuj_i_sacuvaj`, already auto-triggered from finalize) | Same reasoning — an existing direct call, a real Task 3 finding (see below), not migrated this sprint |
| `CONFIDENCE_DROPPED` | A document/entity's confidence falls below `AUTO_ACCEPT_THRESHOLD` (Sprint 003's own Confidence Graph) | No consequence currently exists beyond the already-correct review-queue routing (Sprint 003/004) — nothing proven to be missing yet |
| `MANUAL_CORRECTION_APPLIED` | `shared/intake_documents.py::correct_entity()` | Already writes its own `write_processing_outcome`/audit trail (Sprint 004) — no additional consequence identified as missing |
| `REVIEW_ACCEPTED` | `shared/intake_documents.py::resolve_review()` (Sprint 004) | Already advances `intake_jobs.status` correctly (Sprint 004's own fix) — no additional consequence identified as missing |
| `REVIEW_REJECTED` | No "reject" action exists yet (Sprint 004's own `INTAKE-012`, still an open founder decision) | Cannot wire consequences for an action that doesn't exist yet — blocked on `INTAKE-012`, not this sprint's own gap |

## Task 3 finding: existing scattered "what happens next" call sites (documented, not all migrated)

Found by direct grep for `_run_genome_background`, `create_proactive_alert`, and inline task/alert-creation
patterns, scoped to Agent 1's allowed systems (Intake, Event Bus, Genome, Timeline, Task Engine, Alert
Engine) — repo-wide platform analysis explicitly out of scope:

| Call site | What it decides | Migrated to the canonical mechanism this sprint? |
|---|---|---|
| `routers/smart_intake.py::finalize_intake_job` — Genome refresh | Direct `asyncio.create_task(_genome_bg())` | **Yes** — replaced with a durable `DOCUMENT_ACCEPTED` emission this sprint |
| `routers/smart_intake.py::finalize_intake_job` — Evidence Vault auto-classify | Direct `asyncio.create_task(_evidence_classify_bg())` | No — left as-is; this is `NEW_EVIDENCE_REGISTERED`'s own future consequence, not migrated this sprint (bounded scope, hard token budget) |
| `routers/smart_intake.py::finalize_intake_job` — conflict-check | Direct `asyncio.create_task(_conflict_check_bg())` | No — this is `NEW_CLIENT_LINKED`'s own future consequence, same reasoning |
| `api.py::predmet_upload` (Pipeline A, per-case upload) — Genome refresh | Direct `_run_genome_background()` call, same shape as the one migrated in Pipeline C | No — Pipeline A is out of THIS sprint's bounded scope (mirrors Program Intake Sprint 006/007's own "Pipeline C first" precedent); a real, named follow-up |
| `routers/rocista.py` (hearing scheduling) — Genome refresh trigger | Direct `_run_genome_background()` call | No — same reasoning, a real, named follow-up |

**Why only Pipeline C's own Genome trigger was migrated this sprint**: it is the one call site directly
downstream of Program Intake's own just-declared-bulletproof `finalize_intake_job`, giving the clearest,
lowest-additional-risk proof that the canonical mechanism works end-to-end for a real, already-hardened
pipeline. Migrating Pipeline A/`rocista.py`'s own equivalent calls is mechanical (same event type, same
consequence registry, different emission call site) but is correctly named as a bounded future task rather
than attempted blind under this sprint's hard 2-agent budget.
