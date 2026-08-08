# Phoenix Closure — Open Items Certificate

**Date**: 2026-08-08
**Scope**: the 12 OPEN Living System debt items (`-005, -014, -020, -023, -025, -026, -028, -030,
-035, -039, -042, -049`). Full evidence trail for each item: `docs/phoenix_closure/
PHOENIX_CLOSURE_LEDGER.md`.

## Core principle applied

Per the operation's own rule: *"OPEN does NOT mean optional. If the item is technically solvable
with the existing architecture, you are REQUIRED to solve it."* Every item was re-investigated
against CURRENT code (not the register's prior write-up) before being left untouched. Several were
more resolvable than previously assessed — this certificate names each reclassification with its
evidence, not just the outcome.

## Final disposition per item

| ID | Disposition | What changed |
|---|---|---|
| `-005` / `-030` | **A — PARTIALLY FIXED.** | `static/vindex.js`: a single `window._hasUnsavedWork` flag, event-delegated on genuine `input` events in the 3 known drafting fields (never fires for `_predAutoFill`'s own programmatic auto-fill). Gates a new `beforeunload` warning and defers (doesn't skip forever) the SW `controllerchange` force-reload. Full autosave/persistence architecture remains a genuine, correctly-deferred product decision. |
| `-014` | **C — re-confirmed blocked.** | `drafting/router.py::_popuni_sablon`'s empty-string handling is explicitly documented as intentional. No bounded fix exists that doesn't risk turning every GPT-correctly-blank field into an incorrect placeholder across ~12 templates. Not attempted — inventing an unsafe blanket change was explicitly forbidden. |
| `-020` | **A — FIXED.** | `api.py::predmet_upload_auto_analyze` now computes `content_sha256` (reusing Smart Intake's already-applied migration-095 `predmet_dokumenti` column, no new migration), checks for a prior match, and returns a non-blocking `"mozda_duplikat"` field. Zero upload-behavior change. |
| `-023` | **A — FIXED, reclassified.** | `pytesseract` was already a dependency; `intake_worker.py` already threaded `ocr_confidence` into an already-applied column, just hardcoded to `0.6`/`0.0`. `uploaded_doc/extractor.py::_ocr_image` now calls `pytesseract.image_to_data` for a real mean word-confidence (0.0-1.0), threaded through `extract`'s shared 5-tuple return contract into every `intake_worker.py` call site. Scoped to Smart Intake; Pipeline A's separate OCR path has no equivalent column, named as a future extension. |
| `-025` | **A — PARTIALLY FIXED (narrow).** | Full Case Commander schema parity remains a genuine infra decision, deferred. A single additive `"ai_generated": true` key added to Digital Twin (×2), Court Predictor, and hearing_cc (×2) response dicts — closes the binary "is this AI-advisory" gap. |
| `-026` | **A — FIXED, reclassified.** | `shared/case_context.py` already computed `top_open_action` internally (for `audit_metadata`'s dedupe key) but discarded the object. Now a real top-level contract field (`CONTRACT_VERSION` 1.1.0 → 1.2.0, additive). Digital Twin/Court Predictor surface it read-only next to their own AI recommendation — disclosure, not the reconciliation mechanism the register correctly refused to invent. |
| `-028` | **A — FIXED, reclassified.** | Not the same blocker as `-012` after all — `-031`'s existing recent-duplicate check (staging-insert, AFTER the GPT call) doesn't stop the GPT call itself from running on a retry. The identical check now also gates the TOP of `nacrt()`/`podnesak()`, before generation starts. |
| `-035` | **A — FIXED.** | `static/vindex.js::_buildPredmetKontekst` re-fetches fresh predmet+stranke data (the same endpoint `pred_loadDetail` already uses) immediately before building AI-drafting context, replacing a snapshot loaded once when the case was first opened and never refreshed. |
| `-039` | **A — FIXED.** | Same disclosure split as `-003`/Mission 014: `routers/dashboard.py::command_center` gained `"pad_procene_truncated"`; the 300-row cap itself (a real cost tradeoff) is untouched, still the founder's call. |
| `-042` | **A (1/7) + C (6/7) — PARTIALLY FIXED.** | `ROCISTE_ZAKAZANO` shares `PREDMET_KREIRAN`'s exact simple 1:1 "row exists vs. event exists" detection shape — new `reap_missing_rociste_events` (`services/event_bus.py`) added, wired into the daily cron. The other 6 event types are each conditional on a different sub-entity action, confirmed genuinely needing their own per-type design, not a cheap parameterization. |
| `-049` | **B — re-confirmed blocked.** | `routers/memory_graph.py` (4 routes) / `routers/firm_memory.py` (11 routes) confirmed registered and healthy — zero broken code, purely an absent frontend. Build UI vs. retire backend remains the founder's call. |

## A note on reclassification

4 items (`-023`, `-026`, `-028`, `-020`) were previously deferred on a premise this operation
disproved with direct code evidence: `-023`'s "new capability" framing missed that the capability
(and its persistence column) already existed; `-026`'s "not actionable" framing was right about
reconciliation but missed the disclosure-only option; `-028`'s "same blocker as `-012`" framing
conflated two genuinely separate mechanisms; `-020`'s "needs a product decision" framing missed the
non-blocking-disclosure third option. None of these are the previous missions being wrong to defer
at the time — each is a case where a later, more targeted investigation found a narrower path the
original triage pass didn't have the budget to find. This is disclosed explicitly, not presented as
"the register was mistaken."

## Regression coverage

- New tests: `tests/test_phoenix_closure_open_items.py` (38).
- Pre-existing test corrections: extensive, from `-023`'s change to `uploaded_doc/extractor.py`'s
  shared `extract()` return contract (4-tuple → 5-tuple) — a genuinely wide-blast-radius shared
  function used by 4+ call sites and mocked directly in 18 test files (~30 individual call-site
  fixes). One file (`test_sprint002_pipeline_a_orphan_cleanup.py`) was found to be silently passing
  for the WRONG reason after the change — a `ValueError` from bad tuple-unpacking was being
  swallowed by the SAME outer exception handler the test's own intended failure (Pinecone
  unreachable, DB insert failure, etc.) was supposed to trigger, so `pytest.raises(HTTPException)`
  was accidentally matching an unrelated bug. Caught only by explicitly re-running this file after
  the extractor change instead of trusting its earlier, now-stale "passed" result — the exact kind
  of silent regression this operation's Phase 6 full-suite-twice requirement exists to catch.
- All other call sites (7 test files, ~15 lines) mechanically updated to the new 5-tuple shape.
- `static/sw.js` `CACHE_NAME` bumped `vindex-v107` → `vindex-v108`;
  `tests/test_iron_lawyer_frontend_fixes.py` pinned-literal updated to match.

## Full suite

**3,391 passed, 1 skipped, 0 failed** (was 3,353 at Phase 3's close, +38 tests, zero regressions,
runtime 363.72s — normal baseline). First run surfaced 2 failures
(`test_blackswan_mission001.py::test_morning_briefing_surfaces_missed_deadlines`,
`test_iron_lawyer_frontend_fixes.py::test_sw_cache_bumped`) — both timing artifacts from file edits
still landing while that background run was in flight (confirmed by isolated reruns passing
immediately); a clean rerun after all edits settled came back fully green.

## STOP GATE verdict

- All 12 items have a final disposition. ✅
- Every technically resolvable item (9 of 12, fully or partially) is fixed. ✅
- Every fix has a regression test. ✅
- The 2 genuinely-blocked items (`-014`, `-049`) and the 6/7 infra-blocked sub-items of `-042` have
  named, evidence-backed blocking reasons — none invented, none force-closed. ✅
- No known-failing test, no unresolved data-integrity risk, no unresolved security weakness. ✅
- Documentation complete (this file + the ledger + register updates). ✅

**STOP GATE: PASS.**
