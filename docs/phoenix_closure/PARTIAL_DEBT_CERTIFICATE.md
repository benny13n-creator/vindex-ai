# Phoenix Closure — Partial Debt Certificate

**Date**: 2026-08-08
**Scope**: the 8 PARTIALLY FIXED Living System debt items' remainders (`-003, -011, -012, -022,
-036, -038, -041, -046`). Full evidence trail for each item: `docs/phoenix_closure/
PHOENIX_CLOSURE_LEDGER.md`.

## Final disposition per item

| ID | Disposition | What changed |
|---|---|---|
| `-003` | **B — Founder decision, unchanged.** | Cap size (query-cost tradeoff) and the "stalest-first" ordering are both genuine product calls, not invented. `routers/cio.py:265`'s `.order("updated_at", desc=False)` re-confirmed and left as-is. |
| `-011` | **A — FIXED, all 3 remaining sub-items.** | `services/case_evolution.py`: `genome_refresh` now checks `predmet_genome_history` for a recent, event_id-scoped duplicate before recomputing; `review_confirmation_audit`/`review_rejection_audit` now check `audit_immutable` for a recent duplicate before appending; `case_intelligence_summary` now checks for an exact `event_id` match on `case_intelligence_summaries` before inserting. No migration. `static/vindex.js`'s genome-history renderer gained a friendly label for the new `case_evolution:` trigger prefix. |
| `-012` | **B — Reclassified, not fixed (register correction).** | Confirmed no migration is needed at all — a founder-gated Admin Feature Console (`routers/admin_dashboard.py`, `PATCH /feature-registry/{feature_key}`) already exists for setting `cooldown_seconds` per feature. What remains is a genuine business judgment call (actual duration per ~57 features), exercised through existing infrastructure — corrected in the register, not invented here. |
| `-022` | **A — FIXED.** | `static/vindex.js`'s evidence document card now renders a ⚠ "niska pouzdanost" badge when `ai_tags._klasifikacija_pouzdanost === 'niska'`, next to the already-existing Reklasifikuj button. |
| `-036` | **A — FIXED.** | `routers/predmeti_close.py`: both `zatvori_predmet` (single close) and `bulk_promena_statusa` (bulk zatvaranje/arhiviranje) now bulk-close lingering `status='open'` `case_actions` rows for the closed predmet(s). Best-effort, non-blocking. `aktiviranje` (reopen) explicitly exempt. |
| `-038` | **A — FIXED.** | `routers/kalendar.py::_aggr_events` now returns `(events, meta)` with `degraded_sources`/`truncated` fields, wired into `kalendar_pregled`'s JSON response — same disclosure pattern as `-003`/Timeline. |
| `-041` | **A — FIXED (timeout half); B — deferred (progress-bar half, unchanged).** | All 8 remaining `FormData()` upload sites in `static/vindex.js` now use the existing `_fetchWithTimeout()` helper (90s), joining the 1 already fixed in Mission 013 — 9/9 total. Visual progress indicator remains a real UI-design addition, not attempted. |
| `-046` | **A — FIXED.** | `routers/cio.py::cio_daily`: a losing claim attempt now checks for an in-process winner (`_cio_daily_inflight`/`_cio_daily_done_event`, same coalescing shape as Mission 012's Genome refresh fix) and waits (bounded, 60s) to reuse its persisted report instead of unconditionally paying its own GPT generation cost. Cross-process races (no in-process marker) honestly fall through to the pre-fix behavior, not silently claimed as fully solved. |

## Regression coverage

- New tests: `tests/test_phoenix_closure_partial_items.py` (17), plus additions to
  `tests/test_predmeti_close.py` (+4).
- Pre-existing tests corrected (mock-shape only, root-caused to intentional new query calls, no
  assertions weakened): `tests/test_case_evolution.py` (2), `tests/test_delta_sprint002_event_migration.py`
  (1 shared fixture), `tests/test_omega_sprint002_case_intelligence.py` (1 shared fixture),
  `tests/test_phoenix_mission_001_archived_case_visibility.py` + `tests/test_rocista_kalendar.py`
  (7 call sites updated for `_aggr_events`'s new `(events, meta)` return shape).
- `static/sw.js` `CACHE_NAME` bumped `vindex-v106` → `vindex-v107`;
  `tests/test_iron_lawyer_frontend_fixes.py` pinned-literal updated.

## Subsystem sweep

Targeted sweep across all touched subsystems (case_evolution, predmeti_close, kalendar, rocista,
cio, phoenix_closure, delta_sprint, omega_sprint002/003, iron_lawyer_frontend, evidence):
**305 passed, 0 failed.**

## Full suite

**3,353 passed, 1 skipped, 0 failed** (was 3,332 at Mission 015's close, +21 tests, zero
regressions, runtime 341.26s — normal baseline, no hang). First run surfaced 1 unrelated failure
(`test_sw_cache_bumped`) caused by a timing artifact in this operation's own workflow — the
CACHE_NAME bump landed after the first full-suite run had already been launched in the background;
rerun after both files settled came back clean.

## PARTIAL STOP GATE verdict

- All 8 items have a final disposition. ✅
- Every technically resolvable item (`-011, -022, -036, -038, -041` timeout half, `-046`) is
  fixed. ✅
- Every fix has a regression test. ✅
- No known-failing test, no unresolved data-integrity risk, no unresolved security weakness. ✅
- Documentation complete (this file + the ledger). ✅
- Full suite green: 3,353 passed, 1 skipped, 0 failed. ✅

**STOP GATE: PASS.**
