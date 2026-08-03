# Workflow Interruption Report

**Mission:** Operation Lawyer Day, 2026-08-03. Every interruption found during the full-day simulation
(`LAWYER_DAY_REPORT.md`), root-caused and classified P0-P3 per the mission's own severity scale:
P0 = blocks beta, P1 = makes a lawyer leave Vindex, P2 = workflow annoyance, P3 = technical debt.

---

## Finding #1 — Photo upload rejected on the only upload path a lawyer can actually reach

**Severity: P0. FIXED tonight (small, safe, fully verifiable per this mission's own implementation
criteria).**

- **User problem**: a lawyer with phone photos of a document (an extremely common real scenario — a
  client hands over paper, the lawyer photographs it) cannot get those photos into a case anywhere in
  the app. Upload fails immediately with "Podržani formati: PDF, DOCX."
- **Technical cause**: `POST /api/predmeti/{id}/upload` (`api.py:4133`) — the only document-upload
  endpoint a lawyer can reach today (Smart Intake, which already supports images, has zero frontend
  callers — Finding #2) — validated uploads against `_ALLOWED_MIMES`/`_ALLOWED_SUFFIXES`
  (`api.py:4124-4131`), which included only PDF/DOCX/DOC. Night Shift M-001 (2026-08-02) built real
  image-OCR support (`uploaded_doc/extractor.py::extract_image`) and wired it into Smart Intake's own
  upload validation, then declared "photo upload now works end to end" as a removed Beta Critical Path
  blocker — but never updated THIS endpoint, the one that actually matters for a real lawyer today.
- **Evidence**: `api.py:4124-4131` (pre-fix allowlist); `uploaded_doc/extractor.py:301-311` (`extract()`
  already dispatches `.jpg/.jpeg/.png` to `extract_image()`); `extract_image()`'s own docstring
  (`extractor.py:247-256`) explicitly names "api.py's auto-analyze upload" as a caller needing zero
  special-casing — the fix was anticipated but never applied here.
- **Affected files**: `api.py` (the endpoint's allowlist + one misleading error-message string).
- **Risk**: none identified — `extract_image()` already has its own safety guards (pixel-count cap,
  OCR failure handling) independent of this endpoint.
- **Difficulty**: trivial — widen two `set` literals, matching an already-proven pattern from
  `smart_intake.py`'s own `_ALLOWED_UPLOAD_SUFFIXES`.
- **Estimated impact**: closes a Beta Critical Path scenario (#3, "upload PDF or photo") that was
  previously *claimed* closed but wasn't, for the only path real users actually exercise.
- **Possible solution, implemented**: added `image/jpeg`/`image/png` to `_ALLOWED_MIMES` and
  `.jpg`/`.jpeg`/`.png` to `_ALLOWED_SUFFIXES`; corrected the OCR-failure error message (previously said
  "Skenirani PDF" — now format-neutral, since it now legitimately fires for images too).
- **Regression risk**: none — 5 new tests confirm images are now accepted, PDFs remain accepted
  unchanged, and genuinely unsupported formats are still rejected before reaching `extract()`. Full
  suite: 2311 passed, 1 skipped, 0 failed (was 2306 before this fix).

## Finding #2 — Smart Intake has no frontend entry point

**Severity: P0. NOT implemented — correctly re-confirmed as an active Blocker Report, not a small/safe
fix, per this mission's own instruction to escalate rather than guess.**

- **User problem**: the newer, better-designed document pipeline (structured per-document review,
  confidence-corrected entity extraction, true batch upload with exact-duplicate detection, multi-
  document-to-one-case attach) is completely unreachable. A lawyer's real day runs entirely on an
  older, cruder pipeline instead.
- **Technical cause / Evidence / Affected files**: unchanged since this engagement's prior
  investigation — see `.vindex_ai_team/decisions/2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md`
  for full detail. Re-verified true during this mission's simulation, not re-investigated from scratch.
- **Risk**: building new UI blind conflicts with this project's established design-review discipline.
- **Difficulty**: large — genuine new frontend surface (upload screen, async job/review UI, finalize
  confirmation), not a wiring task.
- **Estimated impact**: the single highest-leverage open item in this entire multi-night engagement —
  everything built to improve intake quality since Night Shift is inert until this ships.
- **Possible solution**: not decided — three options laid out in the existing Blocker Report, awaiting
  founder input.
- **Regression risk**: N/A, not implemented.

## Finding #3 — No true batch upload on the reachable per-case upload path

**Severity: P2 (workflow annoyance — the workflow completes, just inefficiently). Not implemented,
per this mission's own instruction to only implement P0/P1.**

- **User problem**: 20 scanned documents arriving for one case require 20 separate upload actions
  through the only reachable path, instead of one batch action.
- **Technical cause**: `api.py:4133`'s endpoint accepts exactly one `UploadFile` per call — no list
  parameter, unlike Smart Intake's `List[UploadFile]` batch contract (`smart_intake.py:96`).
- **Evidence**: `api.py:4138` (`file: UploadFile = File(...)`, singular) vs. `smart_intake.py:96`
  (`files: List[UploadFile] = File(...)`).
- **Affected files**: `api.py`.
- **Risk**: converting this endpoint to accept a list would meaningfully change its contract (currently
  synchronous, does inline LLM analysis per call) — not a small change given the endpoint's size and
  complexity (200+ lines of inline RAG/chunking/multi-LLM-call logic per document).
- **Difficulty**: medium-large if attempted directly on this endpoint; trivial if Smart Intake's
  existing batch contract becomes reachable instead (Finding #2).
- **Estimated impact**: real but bounded — a lawyer CAN still get all 20 documents in today, just via
  repeated single actions.
- **Possible solution**: solved for free once Finding #2 ships — not worth a parallel, narrower fix on
  the older endpoint.
- **Regression risk**: N/A, not implemented.

## Finding #4 — No duplicate-file detection on the reachable upload path

**Severity: P2. Not implemented.**

- **User problem**: uploading the same file twice to a case (easy to do by accident during a busy batch
  intake) silently creates two `predmet_dokumenti` rows instead of being caught.
- **Technical cause**: `api.py:4133`'s endpoint has no content-hash check before inserting.
- **Evidence**: Smart Intake computes `content_sha256` and uses it as an idempotency key
  (`smart_intake.py:126`, `shared/intake_queue.py:41`) — this endpoint computes a `source_sha256` too
  (`api.py:4226`) but only stores it in Pinecone metadata, never checks it against existing documents
  first.
- **Affected files**: `api.py`.
- **Risk**: low — an additive pre-insert check.
- **Difficulty**: small (a `.eq()` lookup against existing `predmet_dokumenti` by a stored hash column,
  which doesn't currently exist on this table for this endpoint's inserts).
- **Estimated impact**: low-frequency real annoyance, not a blocker.
- **Possible solution**: add a hash-based existing-document check before insert, mirroring Smart
  Intake's idempotency pattern. Not attempted tonight — not P0/P1 by this mission's own classification.
- **Regression risk**: N/A, not implemented.

## Finding #5 — No single "hearing-prep export package"

**Severity: P2 (real friction, but every underlying capability already works — pure aggregation gap,
not a blocked backend). Not implemented.**

- **User problem**: preparing for tomorrow's hearing requires visiting 4+ separate views (Litigation
  Intelligence for judge/opponent research, Case Genome/AI Briefing for arguments and risk, Calendar for
  deadlines, drafted documents' own export) instead of one bundled download.
- **Technical cause**: no endpoint or UI composes these already-working views into one artifact.
- **Evidence**: confirmed absent in `routers/export.py`, `routers/data_export.py`, `routers/rocista.py`,
  and the Litigation Intelligence pane itself (`index.html:3065-3131`, ends with cross-reference links,
  no export button).
- **Affected files**: none yet — would be new, additive code (a new export endpoint composing existing
  data sources), not a fix to existing code.
- **Risk**: low technically; the only real design question is what the bundle should contain and in
  what format (a product decision, not urgent enough to escalate as a blocker tonight).
- **Difficulty**: medium — would touch several existing read-only endpoints to compose one document.
- **Estimated impact**: meaningful quality-of-life improvement, not a blocker — nothing is inaccessible,
  just scattered.
- **Possible solution**: a future, purpose-built "prepare for hearing" export combining existing reads.
  Not attempted tonight — genuinely P2, not P0/P1.
- **Regression risk**: N/A, not implemented.

## Finding #6 — No lawyer-facing audit/activity log viewer

**Severity: P2/P3. Not implemented.**

- **User problem**: a lawyer cannot review their own account/case activity history from within the app.
- **Technical cause**: `shared/audit_immutable.py`'s log is written to (document uploads, GDPR actions)
  but never rendered anywhere in the UI.
- **Evidence**: `vindex.js`'s only two `/api/audit/*` references (`:2626` calibration, `:21075` sync) are
  unrelated to an activity-log viewer.
- **Affected files**: none yet — would be new UI + a new read endpoint over an existing table.
- **Risk**: low.
- **Difficulty**: small-medium (a list view over an already-populated table).
- **Estimated impact**: a reasonable end-of-day expectation, not something today's simulation found any
  workflow strictly blocked by.
- **Possible solution**: a simple activity-history panel in Settings, reading `audit_immutable`'s table
  directly. Not attempted tonight — P2/P3, not P0/P1.
- **Regression risk**: N/A, not implemented.

## Finding #7 — Case archiving only reachable from the case LIST view, not case-detail

**Severity: P2/P3 (minor navigation friction — the action is fully reachable, just from an unexpected
place). Not implemented.**

- **User problem**: a lawyer finishing work on one specific case, while viewing it, cannot archive it
  from that screen — they must return to the case list and use bulk-select.
- **Technical cause**: `pred_bulkAkcija('arhiviranje')` (`vindex.js:10174-10184`) is only wired to the
  list view's bulk-selection bar (`pred-bulk-bar`), not to any button inside the case-detail panel.
- **Evidence**: `routers/predmeti_close.py:295` confirms the backend action itself has no such
  restriction — this is purely a frontend wiring gap.
- **Affected files**: `index.html`/`vindex.js` (a single button addition to the case-detail view,
  calling the same existing function with a one-item array).
- **Risk**: none.
- **Difficulty**: trivial.
- **Estimated impact**: minor.
- **Possible solution**: add a button in the case-detail view calling the existing `pred_bulkAkcija`
  function scoped to the currently-open case. Not implemented tonight — genuinely P2, and this
  mission's own instruction is to implement only P0/P1.
- **Regression risk**: N/A, not implemented.

## Finding #8 — Team comments (`predmet_komentari`) excluded from global search

**Severity: P3. Not implemented.**

- **User problem**: a lawyer searching for something a teammate wrote in a case comment won't find it
  via the global search box.
- **Technical cause**: `routers/search.py` covers `predmet_beleske` (private notes) but has no branch
  for `predmet_komentari` (team comments).
- **Evidence**: no `predmet_komentari` reference anywhere in `routers/search.py`; confirmed both tables
  are otherwise fully live and separately CRUD-wired (`index.html:922-923` "Beleške", explicitly private
  per its own tooltip; `index.html:1489` "Komentari tima", explicitly team-visible) — **these are NOT a
  duplicate needing unification, contrary to this mission's initial working hypothesis**: the UI's own
  copy confirms they serve genuinely different, intentional purposes (private working notes vs.
  team-visible comments). The only real gap is search coverage, not architecture.
- **Affected files**: `routers/search.py` (would need a new branch, same pattern as the existing 7
  types).
- **Risk**: low — same tenant-scoping care this engagement has applied to every other search extension
  (verify `predmet_komentari`'s actual scoping columns before copying a pattern blind, per this
  engagement's own repeated lesson).
- **Difficulty**: small.
- **Estimated impact**: minor.
- **Possible solution**: extend search with an 8th type. Not implemented tonight — P3, not P0/P1.
- **Regression risk**: N/A, not implemented.

---

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Photo upload rejected on the reachable upload path | P0 | **FIXED tonight** |
| 2 | Smart Intake has no frontend entry point | P0 | Blocker Report (pre-existing, re-confirmed) |
| 3 | No true batch upload on the reachable path | P2 | Documented, resolved for free once #2 ships |
| 4 | No duplicate-file detection on the reachable path | P2 | Documented |
| 5 | No hearing-prep export bundle | P2 | Documented |
| 6 | No lawyer-facing audit log viewer | P2/P3 | Documented |
| 7 | Case archiving not reachable from case-detail view | P2/P3 | Documented |
| 8 | Team comments excluded from global search | P3 | Documented |

One finding this mission's investigation initially suspected (`beleske`/`komentari` as a duplicate
needing unification) was resolved by direct evidence as NOT a duplicate — both serve distinct,
intentional purposes per the UI's own copy. Recorded under Finding #8 rather than a separate "Unify
Systems" entry, since no merge is warranted.
