# Program Phoenix — Mission 008: Notification/Timeline/Calendar Display Consistency

**Date**: 2026-08-07
**Debt items addressed**: `LIVINGSYS-DEBT-050` (fully), `LIVINGSYS-DEBT-051` (fully),
`LIVINGSYS-DEBT-053` (fully).

## Why these 3 were grouped

All 3 are "the platform's own state is correct on the server, but a proactive-surface display
(bell badge / Timeline / Calendar) shows a lawyer something misleading" — same root category
(display trusts an incomplete or unreconciled local signal instead of the canonical server
state), same fix shape (make the display read/reconcile against the field that was already
correct), minimum files touched (3: `static/vindex.js`, `routers/intelligence_timeline.py`,
`routers/kalendar.py` + `static/vindex.css`).

## Phase 1 — Reproduction

- `-050`: confirmed `notif_load()` (`static/vindex.js`) populates `_notifData` straight from
  `GET /notifications` (which already returns each row's real `procitano` field) but
  `notif_render()`'s unread computation only ever consults `_notifRead`, a `Set` sourced from
  `localStorage`. A notification marked read via `mark_read`/`mark_all_read` on one device
  updates the server row but never touches another device's `localStorage` — that other device
  keeps showing it (and counting it in the badge) as unread indefinitely.
- `-051`: confirmed `routers/intelligence_timeline.py`'s step 4 (hronologija) already surfaces
  the exact "Predmet zatvoren — Ishod: ..." row `routers/predmeti_close.py` writes on closure,
  and step 7 unconditionally appends a 2nd synthesized "Predmet zatvoren" entry whenever
  `predmet.status == "zatvoren"`, with no check for the row already rendered in step 4.
- `-053`: confirmed `routers/kalendar.py::_klasifikuj_dogadjaj` has only 2 buckets
  (`rok_zastarelost` / `rok_dokument` default) — narrative hronologija entries like
  `"Predmet zatvoren — Ishod: ..."`, `"Follow-up ročište: ..."` (`routers/rocista.py`), and
  `"Ugovor o zastupanju zaključen — Klijent: ..."` (`routers/ugovor_zastupanja.py`) all fall
  into the `rok_dokument` default and render on the Calendar with the same "Rok" label/color as
  a genuine filing deadline.

## Phase 2 — Root cause

See `ROOT_CAUSE_ANALYSIS.md`.

## Phase 3 — Fix

See `FIX_LOG.md` for the exact diffs. Summary:
- `-050`: `notif_load()` now merges `n.procitano === true` into `_notifRead` (additive-only —
  never un-reads an id the current device already knows is read) and persists the merge back to
  `localStorage`, so a badge/read-state that's correct on the server becomes correct on every
  device on next load.
- `-051`: step 7 now only synthesizes the closure entry when step 4's hronologija scan found no
  row whose `dogadjaj` starts with `"Predmet zatvoren"`.
- `-053`: added a `napomena` bucket to `_klasifikuj_dogadjaj`, matched by the 3 known narrative
  prefixes (bounded, not a generic heuristic — a genuine deadline text can never be
  misclassified). Wired through the emoji/label/color logic in both `routers/kalendar.py` and
  `static/vindex.js`'s list/grid/day-detail renderers, plus a new `.kal-ev-napomena` CSS rule.

`static/sw.js` `CACHE_NAME` bumped `vindex-v100` → `vindex-v101` (this mission touched
`vindex.js`/`vindex.css`).

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_008_notification_timeline_calendar_consistency.py`, 9
tests.

## Phase 5 — Original scenario rerun

- `test_intelligence_timeline_skips_synthesized_closure_when_hronologija_already_has_one`
  directly reproduces the double-entry scenario and confirms only 1 closure event renders.
- `test_klasifikuj_dogadjaj_case_closure_is_napomena` /
  `..._hearing_followup_is_napomena` / `..._ugovor_zastupanja_is_napomena` directly reproduce
  the mislabeling for all 3 known narrative sources.
- `test_notif_load_merges_server_procitano_into_local_read_set` confirms the cross-device
  reconciliation code path exists and runs on every load.

## Phase 6 — Subsystem tests

126 tests across all files touching `kalendar.py`, `intelligence_timeline.py`,
`notifications.py`, `rocista.py`, and the frontend structural suite
(`test_iron_lawyer_frontend_fixes.py`, includes a `node --check` syntax gate on
`vindex.js`): **126 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
