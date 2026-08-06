# Canonical Navigation Map — Program Omega, Final Sprint 005 (2026-08-06)

Phase 3's own required deliverable: prove the lawyer can move Upload → Review → Case → Action →
Deadline → Document → Workspace without losing context, and that no click ends in a dead end.

## The chain, link by link — verified against actual code, not assumed

```
Upload  ──▶  Document  ──▶  Review  ──▶  Case  ──▶  Action  ──▶  Deadline  ──▶  Document  ──▶  Workspace
```

### Upload → Document → Review

`routers/smart_intake.py` (Program Intake, multiple prior sprints) — proven extensively by this whole
engagement's own existing test suite, not re-verified from scratch here. Frontend: upload triggers a
job, `intake_job_status`/review-resolution UI drives the human confirmation step.

### Review → Case (Prihvatanje)

Confirmed intact by this sprint's own forensic pass: `static/vindex.js` (finalize POST call, `_si*`
namespace) → on success, `_siShowRecap()` renders a "magic moment" summary (Program Omega Sprint 001's
own deliverable) → an explicit `onclick="siGoToPredmet(id)"` button, labeled "Nastavi na predmet →" →
`siGoToPredmet(id)` switches to the Predmeti tab and calls `pred_select(id)` with full context
(`activePredmetId` set, case detail view opened, scrolled into view). **No dead end** — this link was
already correctly built, confirmed not broken by anything in Sprints 002-005.

### Case → Action — the one real gap found, and closed this sprint

**Found**: before this sprint, `case-actions` had **zero** references anywhere in `static/vindex.js`
(confirmed by grep). A lawyer who opened a specific case saw Cockpit's own risk/problem cards
(`pred_renderCockpit`, freshly recomputed from `identify_case_problems` on every load) but had NO way to
see that SAME case's own tracked, stateful `case_actions` rows — the persistent, lifecycle-managed
(open→closed) action list Sprint 003 built and Workspace aggregates on the home page. To see "does this
case have an open action," a lawyer had to leave the case entirely and go back to the home Workspace
panel, then search for the case again — a genuine "slepa ulica" by the mission's own definition.

**Closed this sprint**: `_predActionsLoad(predmetId)` (new, `static/vindex.js`), called from
`pred_select(id)` alongside the existing `matter_intel_load()`/`_stagingLoad()` auto-loads. Fetches `GET
/api/case-actions/predmeti/{predmet_id}` (Sprint 003's own existing, already-tested endpoint — no new
backend capability) and renders a compact "Otvorene akcije" panel directly in the case detail view
(`index.html`'s own `#pred-actions-section`, next to the Cockpit panel), reusing Workspace's own
`_WS_PRIO_COLOR` priority-color mapping for visual consistency (Phase 4). A lawyer now sees, without
leaving the case, exactly which of that case's own actions are still open.

**Deliberately not done**: merging this new panel INTO Cockpit's own "Otkriveni problemi" card. They
show genuinely different things — Cockpit shows freshly-recomputed raw facts; the new panel shows the
STATEFUL, tracked `case_actions` records (with their own lifecycle/audit trail) — conflating them would
itself be a new shadow-workflow risk, not a fix.

### Action → Deadline

Every `PRIPREMITI_PODNESAK` action (Rule 1, `_compute_target_actions`) already carries its own `rok`
field, sourced directly from the triggering `rocista` row — shown both in Workspace's own item rows and
in the new case-detail "Otvorene akcije" panel (both render `item.rok`/`a.rok`). No separate navigation
step needed — the deadline is inline on the action itself, by design (Sprint 003's own model).

### Deadline → Document

Every action's own `dokaz`/`izvor_dokumenti` field (Sprint 003's own grounding requirement — "no
conclusion without source") carries the originating document reference where applicable (contradiction
actions carry `"DOK-XX str.Y"` locations; missing-evidence actions carry the `identify_case_problems`
finding text). Not rendered as a clickable document-open link in the UI yet — the RAW source data is
present and correct end-to-end (proven by Sprint 003's own tests), but there is no dedicated "open this
exact document at this exact page" UI action wired to it. Named as a small, real, deliberately-deferred
follow-up (`OMEGA-019`, Debt Register) — distinct from a dead end (the information IS there, just not
yet clickable), not attempted this sprint given remaining time budget.

### Document → Workspace

Any document-triggered event (`DOCUMENT_ACCEPTED`, `DOCUMENT_BATCH_COMPLETED`) flows automatically
through Case Evolution → Action Engine → `case_actions`, and the NEXT `GET /api/workspace` call (no
manual refresh, no cache) reflects it — proven end-to-end this sprint by
`tests/test_omega_sprint005_full_chain_to_workspace.py`, which drives the REAL `dispatch_pending_events()`
(not a shortcut) from a raw outbox row all the way to a Workspace read.

## Dead-end sweep (Phase 6, summarized here since it's directly load-bearing for this map)

A dedicated forensic pass cross-referenced:
- Every distinct `onclick="fn(...)"` target in `static/vindex.js` (104 found) against actual function
  declarations — **zero missing** (one false-positive match, `if`, from parsing an inline conditional,
  not a real dead handler).
- Every distinct `fetch(BASE_URL+'/api/...')` path prefix (132 found) against `routers/*.py` + `api.py`'s
  own registered routes — **zero unmatched**. No evidence of the frontend calling a deleted route.
- Placeholder/"coming soon" UI: only the already-known global search (`⌘K`, explicitly labeled "dolazi
  uskoro") and one loading-state string — no broader stub-feature pattern found.

**Conclusion**: this codebase does NOT have a widespread dead-link/orphaned-handler problem — the
one genuine, mission-relevant dead end was the Case→Action link, now closed. The `_dashRender`/
`kalendarLoad` shadow-code findings (`SHADOW_WORKFLOW_AUDIT.md`) are a different failure mode (working
code silently never running, not a broken link) — both fixed separately.
