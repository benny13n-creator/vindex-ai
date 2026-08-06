# End-to-End Pipeline — Program Sigma, Master Sprint 001 (2026-08-06)

Phase 1/2 deliverable: prove one canonical chain exists — Upload → OCR → Segmentation → Classification →
Assimilation → Client Linking → Case Linking → Timeline → Evidence → Deadlines → Tasks → Genome → Strategy
→ Workspace → Dashboard → Ready — for the mission's own primary scenario (500 chaotic documents, one
organized case), with file:line citations for every stage, and every chain break named.

## This is a reconciliation, not a rebuild

A prior sprint — **Program Omega, Master Sprint 001 (2026-08-06, commit `abc59fd`)** — already ran almost
exactly this Phase 1/2 audit, scoped around the same "500 chaotic documents → one organized case" scenario:
`docs/omega/OMEGA_ARCHITECTURE_MAP.md`, `OCR_AND_INTAKE_CAPACITY_REPORT.md`,
`CASE_INTELLIGENCE_AUTOMATION_REPORT.md`, `DOCUMENT_TO_CASE_FLOW_SPEC.md`, `AUTONOMOUS_OFFICE_WORKFLOW.md`.
This document does not re-derive that work — it re-verifies each of its findings against CURRENT code
(several sprints have landed since), and extends it into the areas that sprint didn't cover as deeply
(Phase 3 case-completeness field-by-field, Phase 5 fact-consistency race analysis, Phase 6 knowledge-graph
mechanics).

**One of that report's own "deferred" items was already stale before this sprint started**: its `OMEGA-001`
("Genome recomputes once per document even within one batch") was closed by a later sprint (Program Omega
Sprint 002, confirmed live: `routers/smart_intake.py:1614-1620`, `emit_document_accepted=False` suppresses
the per-job trigger during batch mode). Lesson applied here: every claim below was re-verified against
current code this sprint, not carried forward from an old report's own conclusion.

## Canonical chain, stage by stage

| Stage | Owner | File:line | Verified this sprint |
|---|---|---|---|
| Upload | `POST /api/smart-intake/documents` | `routers/smart_intake.py:108-254` | Yes — sequential per-file loop, SHA-256 content-hash idempotency pre-check (line 156), `_UPLOAD_TIME_BUDGET_S=90.0` partial-response guard (line 74) so a 500-doc batch never hits gunicorn's 120s timeout |
| OCR / Segmentation / Classification | Background `IntakeWorker` | covered in depth by `docs/omega/OMEGA_ARCHITECTURE_MAP.md §2-4` | Re-confirmed via this sprint's own forensic fork: nothing in current Smart Intake code contradicts that report's own citations |
| Assimilation (Client/Case Linking) | `shared/case_assimilation.py::resolve_case_ownership` (121), `resolve_client_ownership` (166) | Fully deterministic, zero GPT calls (grepped every function) | Yes — case-number exact match / 2+ matches → `review_required` (never guesses, `routers/smart_intake.py:968-978`); client full "Ime Prezime" match / 2+ matches → `ambiguous`, surfaced not auto-picked (1020-1029) |
| Batch finalize / `DOCUMENT_BATCH_COMPLETED` | `POST /jobs/finalize-batch` | `routers/smart_intake.py:1598-1710` | Yes — emitted **exactly once per unique `predmet_id`** (dict keyed by case, line 1695), never once per document, regardless of how many of 500 documents land on the same case |
| `PREDMET_KREIRAN` (case-creation pipeline: mini-strategy, HCC briefing, risk snapshot, Copilot recommendation, creation history) | **FIXED this sprint** — was never emitted from Smart Intake | `routers/smart_intake.py:985-1013` (new), `services/case_pipeline.py`, `services/event_bus.py::on_predmet_kreiran` | See "Headline fix" below |
| Timeline | `_consequence_timeline_entry` via `DOCUMENT_ACCEPTED` | `services/case_evolution.py` | Confirmed emitted, `routers/smart_intake.py:1458` |
| Evidence | `_consequence_evidence_classify` via `NEW_EVIDENCE_REGISTERED` | `services/case_evolution.py:323`, `routers/evidence.py:256` | Confirmed, GPT-driven, up to 5 facts/doc |
| Deadlines | `case_actions` Rule 1 (`_priority_by_days`, reads `rocista`) + Smart Intake's own best-effort initial-deadline capture (reads document's own extracted `deadline` field) | `services/case_evolution.py`, `routers/smart_intake.py:1109-1127` | Confirmed — 2 genuinely different, non-overlapping sources (see Sprint 007's own `predmet_hronologija` vs `rocista` finding, still accurate) |
| Tasks | `_consequence_refresh_case_actions` via `DOCUMENT_ACCEPTED`/`DOCUMENT_BATCH_COMPLETED` | `services/case_evolution.py` | Confirmed |
| Genome | `_consequence_genome_refresh` via `DOCUMENT_ACCEPTED`/`DOCUMENT_BATCH_COMPLETED` | `services/case_evolution.py`, `routers/case_dna.py` | Confirmed, ONE recompute per batch (not per document) |
| Strategy | **Two paths**: `routers/strategija.py` (on-demand, full) + `case_pipeline.py::_step_strategija` (auto, lite, one-time) | `services/case_pipeline.py:351-415` | **Was never auto-triggered for Smart-Intake cases before this sprint's fix** — see below |
| Workspace | `GET /api/workspace` | `routers/workspace.py` | Confirmed, reads `case_actions` (canonical) |
| Dashboard | `routers/dashboard.py` | Confirmed, reads `predmet_hronologija` directly (own presentation-layer projection) |
| Ready | `GET /api/matter-intel/{predmet_id}` (Phase 7 payload) | `routers/matter_intel.py:45-` | Confirmed — see `AUTONOMOUS_CASE_BUILDING_SPEC.md` |

## Headline finding and fix: `PREDMET_KREIRAN` was never emitted from Smart Intake

Before this sprint, `EventType.PREDMET_KREIRAN` — and therefore the entire 9-step Case Pipeline
(`services/case_pipeline.py`: `analiza_dokumenata`, `auto_linking`, `ekstrakcija_rokova`, `kalendar`,
`strategija`, `hcc`, `risk_snapshot`, `copilot_preporuka`, `istorija`) — was emitted from **exactly one
place repo-wide**: `api.py:3170`, the manual "+ Novi predmet" endpoint. Confirmed via
`grep -rn "EventType.PREDMET_KREIRAN"` across `api.py`/`routers/`/`services/` — zero matches in
`routers/smart_intake.py`, `routers/intake.py`, `routers/onboarding.py`, `routers/integracije.py`.

This meant the mission's own primary scenario — "Upload 500 dokumenata → Predmet nastaje automatski" —
produced a case that never received: an initial litigation-strategy assessment, an HCC pre-briefing, a
risk snapshot, Copilot's opening recommendation, or its own "case created" history entry. Genome, Timeline,
and `case_actions` (deadlines/tasks) WERE already populated, via the separate, more modern Case Evolution
Engine (`DOCUMENT_ACCEPTED`) — the gap was specifically the 5 Case Pipeline steps that have no equivalent
anywhere else in the codebase.

**Fixed this sprint** — `routers/smart_intake.py` now emits `PREDMET_KREIRAN` (via the same durable-outbox
`emit_durable` helper `api.py` already uses) exactly once, at the one call site where a genuinely NEW case
is created (`routers/smart_intake.py:985`, right after `_create_new_predmet_from_value_map` — covers both
the single-job `finalize_intake_job` endpoint and the 500-document `finalize-batch` endpoint, since the
latter calls the former per job). `services/case_pipeline.py::run_case_pipeline` gained a `skip_steps`
parameter; the emission passes `skip_pipeline_steps: ["ekstrakcija_rokova"]` because that ONE step (GPT
deadline extraction from the case's own free-text `opis`) would risk a real near-duplicate
`predmet_hronologija` entry against the document-level deadline Smart Intake's finalize call already
captured — every other step was verified read-only or writes to a uniquely-marked `predmet_istorija` entry
nothing else in the system writes, so no duplication risk exists for them. Also fixed, in the same change:
`_step_analiza_dokumenata` (Step 1) previously only recognized the legacy `[Auto-analiza]` istorija marker
as evidence of analysis — Smart Intake's own Genome-based analysis never writes that marker, so every
Smart-Intake case would have wrongly reported this step FAILED; it now also accepts a populated
`predmeti.case_dna` as evidence.

12 new tests prove this (`tests/test_case_pipeline.py`): the genome-based Step 1 fix (2 tests, including a
negative control), the `skip=True` short-circuit never calling GPT or inserting (1 test), `run_case_pipeline`
honoring `skip_steps` end to end through the real orchestrator (1 test), and `on_predmet_kreiran` correctly
forwarding `event.payload["skip_pipeline_steps"]` — including the default-empty case for the original
manual-creation caller, whose behavior is unchanged (2 tests).

## Idempotency at every layer (re-verified, not re-built)

- **Upload**: SHA-256 content-hash pre-check — full duplicate re-submission of the same 500 documents
  returns `"already_submitted": true` per file, no new storage/job.
- **Document-level**: `content_sha256` of extracted text — same content in the same case → idempotent
  no-op; same content in a different case → routed to review, never silently guessed.
- **Finalize-call-level**: `claim_finalize` RPC (migration 092, `SELECT...FOR UPDATE SKIP LOCKED`) — closes
  a prior real bug where 2 near-simultaneous finalize calls for the same job could both create a duplicate
  case; crash-recovery path (lines 906-928) recovers an existing `predmet_id` via
  `predmet_dokumenti.source_intake_job_id` rather than creating a second case.
- **Batch-level**: `DOCUMENT_BATCH_COMPLETED` fires once per case per batch, not once per document.
- **`PREDMET_KREIRAN` (new)**: fires exactly once per genuinely-new case (only at the `_create_new_predmet_from_value_map`
  call site, never for the `attach`-to-existing-case outcome) — matching the "no duplication" requirement
  by construction, not by an added check.

## Chain breaks found

None beyond the `PREDMET_KREIRAN` gap above (now fixed). One silent-failure risk named, not fixed:
`finalize_intake_job`'s own whole-job decrypt/extract failure (`routers/smart_intake.py:1150-1167`) fails
soft — a corrupted/undecryptable file produces a silent `povezan: false, razlog: "prazan_tekst"` per
document, with no escalation beyond the per-document array in the finalize response. Whether this is
prominently surfaced in the lawyer-facing "what's missing" view is addressed in
`AUTONOMOUS_CASE_BUILDING_SPEC.md`'s own Phase 7 section.

## Scope boundary, stated honestly

This document traces the CODE PATH with file:line citations and unit/integration-level tests. It does not
constitute a live, 500-document load test against a running Postgres/Supabase instance under real
concurrent OS processes — see `SYSTEM_GAP_REPORT.md`'s own "What this sprint could not certify" section for
the precise boundary between what was code-proven and what would need live infrastructure.
