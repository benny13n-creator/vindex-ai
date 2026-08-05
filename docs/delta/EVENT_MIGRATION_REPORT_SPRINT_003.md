# Canonical Event Migration Report II — Program Delta, Sprint 003 (2026-08-05)

"Canonical Event Migration II — Complete Event Convergence". Closes the last 2 direct-orchestration call
sites named across Sprints 001-002 (`DELTA-002`), plus wires the one remaining event type
(`ROCISTE_ZAKAZANO`) that had zero consequences until now.

## Task 1 — Pipeline A (`api.py::predmet_upload_auto_analyze`)

Found exactly 3 direct background calls at this endpoint's document-upload path:

1. **`dokument_upload` audit log** (`asyncio.create_task(log_action(...))`) — deliberately NOT migrated. This
   is the PRIMARY audit record of the upload action itself, not a reactive consequence of a case-changing
   event — the same category as `finalize_intake_job`'s own direct `document_assimilated` audit call, which
   Sprint 001 also left untouched. Migrating primary-action audit logging into Case Evolution would blur the
   distinction between "the action happened" (always logged directly, synchronously in intent) and "what
   automatically follows" (Case Evolution's own domain) — a real architectural boundary, not an oversight.
2. **Evidence Vault auto-classify** (`asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))`) —
   MIGRATED. Replaced with a durable `NEW_EVIDENCE_REGISTERED` emission, reusing the EXISTING
   `_consequence_evidence_classify` executor (Sprint 002) unchanged.
3. **Genome auto-refresh** (`asyncio.create_task(_genome_bg())`, with a `asyncio.sleep(3)` heuristic "wait for
   classification to write tip_dokaza") — MIGRATED. Replaced with a durable `DOCUMENT_ACCEPTED` emission,
   reusing the EXISTING `_consequence_genome_refresh` + `_consequence_timeline_entry` executors (Sprint 001)
   unchanged.

**A real, intended side effect of convergence, not scope creep**: Pipeline A's uploads now ALSO produce a
Timeline entry (`_consequence_timeline_entry`, part of `DOCUMENT_ACCEPTED`'s own canonical consequence set) —
something Pipeline A never did before. This is not a new capability being introduced; it is the exact same
canonical definition of "what happens when a document is accepted" that Pipeline C has had since Sprint 001,
now correctly applied uniformly. Convergence means every pipeline gets the SAME treatment for the SAME event
type — that is the sprint's own stated goal, not an accidental expansion.

**Ordering, honestly characterized, not oversold**: the two emissions are made in a fixed order (evidence
first, genome second, both `await`-ed sequentially before either sees the response return) so that a
single-worker or low-concurrency dispatch processes classification before the genome refresh reads
`tip_dokaza`. This is NOT a hard guarantee — under multi-worker concurrent dispatch (Mission Keystone's own
4-gunicorn-worker finding), the two events could still be claimed and processed by different workers out of
order. This is honestly no weaker than the `asyncio.sleep(3)` heuristic it replaces (which had no guarantee
either — classification could legitimately take longer than 3 seconds under load) and arguably better (not
time-based/racy against a slow GPT call). See Reliability Verification Report for the full reasoning; a hard
ordering guarantee was NOT built, per this sprint's own "migrate, don't extend" mandate.

## Task 2 — `routers/rocista.py`

Found exactly 1 direct Genome trigger, at `kreiraj_rociste` (`POST /api/rocista`): `asyncio.create_task(
_rociste_genome_bg())`, with its own `asyncio.sleep(2)` heuristic. MIGRATED — replaced with a durable
`ROCISTE_ZAKAZANO` emission. `rocista.py` no longer imports or calls `_run_genome_background` at all, per the
mission's own literal instruction ("rocista.py ne sme znati kako se osvežava Genome. Sme samo emitovati
događaj.") — confirmed by grep: zero remaining references to `_run_genome_background` in `routers/rocista.py`.

`EventType.ROCISTE_ZAKAZANO` existed in the Event Bus enum since before Program Delta but had ZERO handlers
and was NEVER emitted anywhere in the repo (confirmed by repo-wide grep before wiring it) — this is the FIRST
time this event type has ever done anything. Not "migrating a working mechanism," but "finally connecting a
dead declaration to real behavior" — the same "infrastructure exists, was never connected" pattern this whole
engagement has found repeatedly since Mission Atlas (2026-08-03).

Two other candidate sites in `rocista.py`, checked and correctly NOT migrated:
- `azuriraj_rociste` (PATCH, rescheduling) has NO Genome trigger at all today — adding one now would be a NEW
  consequence for an endpoint that never had it, forbidden ("Ne uvoditi nove Genome mogućnosti").
- `hearing_followup` writes `predmet_beleske`/`predmet_hronologija`/`predmet_istorija` directly and
  synchronously — but this IS the endpoint's own primary requested action (the lawyer explicitly asks to
  record a follow-up, and the write happens in the same response), not a reactive consequence of a
  case-changing event. Same category as `finalize_intake_job`'s own document-linking work, correctly left
  direct in every prior sprint too.

## Task 3 — Registry Audit

`services/event_bus.py::EventType` has 19 members. Compared every one against `CONSEQUENCE_REGISTRY` and the
written `CASE_EVOLUTION_REGISTRY.md`:

- **6 have wired consequences** (`DOCUMENT_ACCEPTED`, `REVIEW_ACCEPTED`, `REVIEW_REJECTED`,
  `NEW_CLIENT_LINKED`, `NEW_EVIDENCE_REGISTERED`, `ROCISTE_ZAKAZANO`) — all 6 documented in
  `CASE_EVOLUTION_REGISTRY.md`, all 6 confirmed subscribed to `handle_case_changed` in
  `EventBus._register_defaults`. Zero drift in either direction.
- **3 are declared-not-wired within Case Evolution's own domain** (`DOCUMENT_MODIFIED`, `CONFIDENCE_DROPPED`,
  `MANUAL_CORRECTION_APPLIED`) — unchanged reasoning from Sprint 001, re-confirmed not re-derived.
- **10 belong to a different, established, pre-existing system**, listed explicitly in
  `CASE_EVOLUTION_REGISTRY.md`'s own new "Registry Audit" section this sprint — no drift found; no registered
  event that no longer exists in code (nothing was ever removed from `CONSEQUENCE_REGISTRY` since Sprint 001,
  only added to).

Automated, not just narrative: `tests/test_delta_sprint003_full_convergence.py` encodes this comparison as a
test that will fail on any future drift (`test_registry_100_percent_matches_event_bus_wiring`,
`test_every_consequence_registry_event_documented_in_case_evolution_registry_md`) — the registry's own "100%
accurate" claim is now enforced by CI, not just true at the moment this report was written.

## Task 4 — Orchestrator Ownership Sweep

Repo-wide grep for the 3 functions Case Evolution's own executors wrap
(`_run_genome_background(`, `klasifikuj_i_sacuvaj(`, `_run_conflict_check(`), searching every `.py` file
outside `tests/`:

- `_run_genome_background(` — found ONLY in its own definition (`routers/case_dna.py`) and its one canonical
  caller (`services/case_evolution.py`). Zero remaining direct callers anywhere else.
- `klasifikuj_i_sacuvaj(` — same result: definition + one canonical caller only.
- `_run_conflict_check(` — definition (`routers/intake.py`) + one canonical caller
  (`services/case_evolution.py`) + ONE deliberate exception: `routers/intake.py`'s own
  `POST /api/intake/conflict-check` HTTP endpoint, a direct, synchronous, user-initiated query (see Task 2's
  own `hearing_followup` reasoning above for the same category distinction) — not migrated, and correctly so.

`create_proactive_alert(` direct callers found in `routers/morning_briefing.py`, `routers/workflow.py`,
`routers/zadaci.py`, `routers/zakon_monitoring.py`, `routers/case_dna.py` — explicitly NOT swept further this
sprint. Each is a DIFFERENT feature's own primary alerting logic (Morning Briefing's own daily digest,
Workflow's own workflow alerts, Task Engine's own task alerts, Law Monitoring's own regulatory alerts,
Genome's own internal delta-significant alert, all pre-existing, none newly discovered as bypassing Case
Evolution) — auditing all of them is explicitly OUT of this sprint's scope ("Bez globalne analize" is a hard
budget constraint, not a suggestion), and none of them are reactive consequences of the 6 events Case
Evolution's own registry owns.

## Task 5 — Canonical Ownership Verification

For each of the 6 wired events, confirmed by direct code inspection AND by
`tests/test_delta_sprint003_full_convergence.py::test_1_all_wired_events_share_the_same_dispatcher`: exactly
ONE handler (`handle_case_changed`) is subscribed per event type in `EventBus._handlers` — no event type has
two owners. One orchestrator (`services/case_evolution.py`), one definition per event
(`CONSEQUENCE_REGISTRY`), one retry mechanism (the Event Bus's own `dispatch_pending_events`), one audit model
(`case_evolution_consequences` + `log_action`), one provenance/correlation chain (`event.correlation_id`,
inherited from the request context at emission time, unchanged since Mission Ledger 2026-08-03).

## What did NOT change

Genome, Timeline, Evidence Vault, the conflict-check matching logic, and the Event Bus's own durable
outbox/atomic-claim/retry/dead-letter machinery are all reused UNCHANGED — this sprint added zero new AI
functions, zero new Genome/Timeline/Alert/Task capabilities. Every migrated consequence executor this sprint
touches was ALREADY built in Sprint 001 or 002; Sprint 003's own code changes are limited to emission call
sites (`api.py`, `routers/rocista.py`) and 2 new registry entries wiring EXISTING executors to a 6th event
type.
