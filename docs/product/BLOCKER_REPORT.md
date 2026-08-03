# Blocker Report

**Mission:** Operation Beta Lockdown, 2026-08-03. Every remaining Beta blocker, ranked, explained,
reproducible, with a concrete implementation plan where one exists. One critical finding was small,
safe, and fully verifiable — fixed tonight (`BL-001`) rather than merely reported, per this mission's
own "smallest safe change" rule. Everything else below was deliberately NOT implemented, per the same
rule's other half: anything not low-risk/fully-testable/zero-regression gets a blocker report instead.

---

## BLOCKER-1 (was live until tonight): `zadaci_za_predmet` cross-tenant task leak

**Status: FIXED tonight (BL-001).** Included here for completeness and reproducibility, since it was
the single most severe finding of this mission.

- **Reproduction (pre-fix)**: `GET /api/zadaci/predmet/{any_other_firms_predmet_id}` with a valid,
  authenticated token belonging to ANY user returned that firm's complete task list — no ownership
  check existed at all.
- **Root cause**: `routers/zadaci.py:380-402` was the one endpoint in its own file that skipped the
  ownership-verification pattern every sibling endpoint already used.
- **Fix**: added `predmeti.eq("id", predmet_id).eq("user_id", uid)` before the `zadaci` query,
  mirroring `ai_analiziraj_predmet`'s existing pattern 90 lines below in the same file.
- **Verification**: 4 new tests, one confirmed via negative control to fail against the pre-fix code
  (proving the test suite would have caught this had it existed earlier). Full suite: 2315 passed, 1
  skipped, 0 failed.
- **Regression risk**: none — additive check, matches an established in-file pattern exactly.

## BLOCKER-2: Smart Intake has no frontend entry point

**Status: NOT implemented — founder decision required.**

- **Reproduction**: open the app as any lawyer; there is no button, page, or menu item anywhere that
  calls `POST /api/smart-intake/documents` or any of its sibling endpoints. Confirmed by exhaustive
  grep of every frontend file, repeated across three separate missions tonight with the same result.
- **Root cause**: the newer, structurally superior document-intake pipeline (per-document confidence-
  gated review, true batch upload, exact-hash duplicate detection, multi-document-to-one-case attach)
  was built end-to-end on the backend and never connected to any UI.
- **Why not fixed tonight**: this requires genuine new frontend surface (an upload screen, an async
  job/review UI, a finalize/confirmation step) — not a wiring task. Building it blind conflicts with
  this project's own UI-style discipline and represents a real product decision (does this replace the
  older upload paths, coexist alongside them, or deprecate them over time).
- **Implementation plan** (for the founder to choose from, not decided here):
  1. New, dedicated Smart Intake UI flow as the primary "start a new case" entry point.
  2. Repoint the existing `/api/predmeti/{id}/upload` button to call Smart Intake's endpoints,
     adding a lightweight review/confirm step.
  3. Do nothing yet; this report stands as the record.
- **Estimated impact if resolved**: the single highest-leverage open item in this entire multi-night
  engagement — every recent quality improvement to intake lives here, inert until this ships.
- **Full detail**: `.vindex_ai_team/decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md`.

## BLOCKER-3: Draft staging/approval pipeline has no frontend entry point

**Status: NOT implemented — same root shape as BLOCKER-2, newly found this mission.**

- **Reproduction**: generate a draft via the AI Workspace's "nacrti"/"podnesak" mode, export it as
  DOCX (this part works) — the draft never appears anywhere else in the case (not in the document list,
  not in search). Grepping `vindex.js` for "staging" returns zero matches anywhere.
- **Root cause**: `routers/drafting.py::_stage_draft_for_review` (`:199-228`) already stages every
  generated draft into `staging_memory` with a computed confidence score, and
  `POST /api/staging/{id}/approve` (`:300-309`) already promotes an approved draft into
  `predmet_dokumenti` with `tekst_sadrzaj` populated — at which point it's automatically searchable via
  the existing document-search branch, zero additional work needed. None of this is reachable from the
  UI.
- **Why not fixed tonight**: same reasoning as BLOCKER-2 — a real review/approval UI is a frontend
  build, not a wiring fix, and smaller in scope than Smart Intake but not zero-risk to improvise
  blind (a confidence-gated approval flow is exactly the kind of UX this project's own AI-output
  discipline says shouldn't be rushed).
- **Implementation plan**: a lightweight "pending drafts" list (reads `staging_memory` for the current
  case) with an approve/reject action calling the already-built endpoint. Smaller than Smart Intake's
  UI — a single list view plus one action button, not a multi-step wizard.
- **Estimated impact**: currently, every drafted document is effectively ephemeral (exists only as a
  downloaded file) rather than becoming a permanent, searchable part of the case record.

## BLOCKER-4: Two competing client-CSV-import implementations

**Status: NOT implemented — founder decision required.** Full detail: `docs/product/CURRENT_STATE.md`
§1. The dead implementation is the SAFER one (preview + confirm); the live one is a riskier one-shot
import. Replacing, augmenting, or leaving as-is are all real product choices.

## BLOCKER-5: Two competing WhatsApp-notification systems

**Status: NOT implemented — founder decision required.** Full detail: `docs/product/CURRENT_STATE.md`
§2. The live system already covers the core need; the dead one adds granularity with no evidence of
demand — reads as a deletion candidate, not a reconnection one, but that's a call for the founder, not
this mission.

## BLOCKER-6: Memory Graph cannot be safely wired without a data-population decision

**Status: NOT implemented — founder decision required.** Unchanged since Operation Invisible Features'
investigation. Shipping a query UI alone would show every real user a permanently empty graph, since
its only data-writer endpoint is also dead. Needs a decision: manual population UX, or automatic
extraction from existing case data (new AI logic, out of any "connect existing" mission's scope).

---

## Everything else found tonight and in prior operations: P2/P3, correctly not implemented

See `docs/product/WORKFLOW_GAPS.md` for the full list (hearing-prep export bundle, account-wide audit
log viewer, case-detail archiving button, duplicate-file detection on the reachable upload path, team
comments missing from search, AI Workspace mode not surviving reload). None of these block a lawyer from
completing a workflow — they're friction, not dead ends — and per this mission's own rule, only P0/P1
items get implemented same-night; everything else is backlog.
