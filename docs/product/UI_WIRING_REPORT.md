# UI Wiring Report

**Mission:** Operation Beta Closure, 2026-08-03. Exact record of every frontend wiring change made —
no backend code was touched; every endpoint used already existed, was already tested, and is unchanged.

---

## Priority 1: Smart Intake — document-first case creation (new panel)

**Backend used, unchanged**: `routers/smart_intake.py` — `POST /api/smart-intake/documents` (batch
upload), `GET /api/smart-intake/jobs/{id}` (status + Confidence Graph, one call), `POST
/api/smart-intake/entities/{id}/correct` (10-second correction), `POST
/api/smart-intake/jobs/{id}/finalize` (create-or-attach, per `ZTC-001`'s `predmet_id` parameter).

**New entry points** (`index.html`): a second toolbar button "+ Iz dokumenta" next to the existing
"+ Novi predmet", and a second button "Otpremi dokumenta" next to "Otvori novi predmet" in the
Predmeti tab's empty state — both call `siOtvori()`. The existing name-first CRM Intake Wizard
(`intakeOtvori()`) is untouched; this is a parallel, additive entry point, not a replacement.

**New panel** (`index.html`): `#si-overlay`, reusing the existing Intake Wizard's `.intake-overlay`/
`.intake-panel`/`.intake-upload-zone`/`.intake-field`/`.intake-back-btn`/`.intake-next-btn` classes so
it reads as native UI, not a redesign. 3 steps: Upload → Processing → Review & Confirm.

**New JS** (`static/vindex.js`, ~340 lines): `siOtvori`/`siZatvori`/`siConfirmClose` (open/close with a
dirty-state guard), `siFilesSelected`/`siDropFiles`/`_siAddFiles`/`siRemoveFile` (multi-file staging,
client-side format/size validation matching the backend's own `_ALLOWED_UPLOAD_SUFFIXES`/25MB limit),
`siUploadAndProceed` (batch upload), `_siPollJobs`/`_siRenderProcessingList` (adaptive-interval status
polling — see Security/Performance note below), `_siRenderReview`/`siCorrectEntity` (per-entity
confidence display + inline correction for `needs_review` fields), `siFinalize`/`siGoToPredmet`
(sequenced finalize — first job creates the case, every subsequent job attaches via `predmet_id`, then
navigates directly into the newly created case).

**Workflow completed end-to-end** (traced against real code, matching this engagement's Beta
Acceptance Test scenarios): create/select case → upload PDFs → upload phone photos → upload multiple
files into ONE case → review extracted information with per-field confidence → correct low-confidence
fields → approve (finalize) → continue working (lands directly in the new case's detail view) — all
without leaving the app.

## Priority 2: Draft staging/approval — minimal review UI

**Backend used, unchanged**: `routers/drafting.py` — `GET /api/staging/predmet/{id}` (list pending
drafts for a case), `POST /api/staging/{id}/approve`, `POST /api/staging/{id}/reject`.

**New UI** (`index.html`): a "Nacrti na čekanju odobrenja" section in the case-detail view's existing
Case Intelligence area (same location as the AI Briefing button wired earlier tonight), hidden when
empty, populated automatically when a case is opened.

**New JS**: `_stagingLoad` (fetches and renders on case open, via the same `pred_select` hook that
already loads Matter Intelligence), `_stagingRender`, `stagingApprove`, `stagingReject`. Approval
surfaces the backend's own message verbatim, including the honest case where `confidence_score < 0.85`
(approved but not yet added to the searchable case record) — no UI claim is made beyond what the
backend actually did.

**Deliberately minimal, per this mission's Priority 2 instruction** ("expose it, build only the
minimum production-ready UI"): a list with two buttons, no wizard, no polling — the staging data is
already present by the time a case is opened (drafts are staged automatically on generation), so no
async status tracking is needed here unlike Smart Intake's job pipeline.

## Priority 3: Workflow continuity

- Smart Intake's finalize step ends by navigating directly into the created/updated case
  (`siGoToPredmet`) — reusing the exact `pred_load()` + `pred_select(id)` pattern already established
  by Quick Intake (`qiKreiraj`) and the CRM Wizard (`intakePipelineDone`), not inventing a new
  navigation convention.
- Draft staging surfaces automatically the moment a case is opened — no separate menu, no manual
  refresh, matching the same auto-load pattern as Matter Intelligence and Case Genome's own panels.

## Priority 4: Feature discoverability

Both Smart Intake and draft staging were, before tonight, the two highest-value confirmed-dead
capabilities in the entire application (per `docs/product/FEATURE_COMPLETION_MATRIX.md`'s Level 3
findings). Both are now exposed. No other production-ready, tested, secure capability was identified
as needing exposure within this mission's time budget beyond what `docs/product/BLOCKER_REPORT.md`
already tracks as founder-decision-gated (client CSV import, WhatsApp notifications, Memory Graph).

## Priority 5: UX polish

Not attempted, per the mission's own explicit ordering ("Only after priorities 1–4... Never redesign
the application"). Priorities 1-2 consumed this mission's full scope at the quality bar this engagement
has maintained all night.

---

## Security notes (Mandatory Security checklist)

- **Tenant isolation**: inherited entirely from the backend, which derives `user_id` from the JWT via
  `get_current_user` on every endpoint used — no client-supplied identifier is ever trusted. No new
  backend surface was added, so no new isolation risk was introduced.
- **Authorization**: same — every call includes the existing `Authorization: Bearer` header pattern
  already used throughout `vindex.js`.
- **Audit logging**: unchanged — `dokument_upload` is logged by the same backend code path Smart
  Intake's finalize already used (per this engagement's prior audit-coverage findings, this specific
  action type is already in the audited set).
- **Search integration**: a finalized Smart Intake document becomes searchable via the already-existing
  `_search_dokumenti` branch (same table, same fields) — no search-side change needed. An approved
  draft (when `confidence_score >= 0.85`) becomes searchable the same way.
- **Error handling**: every new fetch call has a try/catch with a user-visible, non-technical error
  message (`_friendlyErr`, `showToast`) — matching this codebase's established convention, not a new
  pattern.
- **Permission model**: unchanged — no new permission tier was introduced; the endpoints used already
  gate on `get_current_user` exactly as they did before tonight.
- **Rate-limit awareness (new consideration this mission)**: `GET /jobs/{id}` is rate-limited to
  60/minute per user. A naive fixed-interval poll across a real Workflow-3-sized batch (~20 files)
  would exceed that. `_siPollJobs` uses an adaptive interval
  (`Math.max(4000, activeJobCount * 1200)` ms) that scales down request frequency for large batches and
  speeds up automatically as fewer jobs remain active — a defensive measure against a self-inflicted
  rate-limit trip, not a backend change.

## Testing notes (Mandatory Tests checklist)

No backend code changed this mission — the existing, already-comprehensive Python test suite for
`smart_intake.py` and `drafting.py` (built across this engagement's prior operations, e.g.
`tests/test_lz002_evidence_autoclassify.py`, `tests/test_ztc_scenario_b_attach.py`,
`tests/test_smart_intake_upload_validation.py`) remains the correctness guarantee for every endpoint
this UI calls, and passes unchanged: 2315 passed, 1 skipped, 0 failed. This repo has no automated
frontend test harness (confirmed repeatedly this engagement); verification for the new JS was
`node --check` (syntax validity, passed) plus manual logic review against the exact backend response
shapes read directly from `routers/smart_intake.py` and `routers/drafting.py` before writing any
frontend code — not assumed from memory of earlier sessions.
