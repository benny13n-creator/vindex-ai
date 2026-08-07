# Mission 008 — Regression Proof

## Fix 1 — `notif_load` read-state reconciliation

**Claim**: merging server `procitano` into `_notifRead` is additive-only and cannot make an
already-read notification look unread, nor can it desync the badge from what the dropdown
actually shows.

- The merge is a one-directional `.add()` into the existing `Set` — no removal path exists in
  this change, so a notification this device already knows is read (via its own prior
  `mark_read` call, before a page reload) stays read regardless of what the server returns.
- `notif_render()`'s unread computation (`_notifData.filter(n => !_notifRead.has(n.id))`) is
  unchanged — the fix only ever grows the set it already filters against, so badge count and
  dropdown contents stay derived from the same single source, avoiding a "badge says N but
  dropdown lists a different N" split.
- `test_notif_load_merges_server_procitano_into_local_read_set` proves the merge code path is
  present in `notif_load()`'s body and persists to `localStorage`.

## Fix 2 — Timeline closure de-duplication

**Claim**: the guard only suppresses the synthesized entry when a genuinely matching
hronologija row exists, and never suppresses it for a case that lacks one.

- `test_intelligence_timeline_skips_synthesized_closure_when_hronologija_already_has_one`
  proves exactly 1 "Predmet zatvoren"-titled event renders when the hronologija row is present.
- `test_intelligence_timeline_still_synthesizes_when_no_hronologija_closure_row` proves the
  synthesized entry still appears when the hronologija scan found nothing — the pre-mission
  defensive guarantee ("closure is always visible even without a matching row") is preserved
  unchanged.
- `test_intelligence_timeline_open_case_unaffected` proves an open (`status != "zatvoren"`)
  case never synthesizes a closure entry, matching pre-mission behavior exactly.

## Fix 3 — Calendar narrative classification

**Claim**: only the 3 known narrative prefixes are reclassified; every other classification
outcome, including genuine deadlines and zastarelost warnings, is unchanged.

- `test_klasifikuj_dogadjaj_zastarelost_unaffected` proves the pre-existing `rok_zastarelost`
  path is untouched.
- `test_klasifikuj_dogadjaj_real_deadline_stays_rok_dokument` proves a deadline text that isn't
  one of the 3 known narrative prefixes still defaults to `rok_dokument` exactly as before this
  mission — no real deadline can be silently downgraded to "just a note."
- The 3 positive-match tests (`case_closure`/`hearing_followup`/`ugovor_zastupanja`) confirm all
  3 sources named in the debt item are now covered.
- Pre-existing tests `test_aggr_events_hronologija_zastarelost` and
  `test_aggr_events_hronologija_rok_dokument` (in `tests/test_rocista_kalendar.py`) needed no
  modification and continue to pass unchanged, confirming this endpoint's existing behavior for
  non-narrative hronologija content is untouched.

## Subsystem regression

126 tests across all files touching `kalendar.py`, `intelligence_timeline.py`,
`notifications.py`, `rocista.py`, and the frontend structural suite (including the `node
--check` syntax gate on `vindex.js`): **126 passed, 0 failed** — no pre-existing test needed
modification.

## Full-suite regression

See `TEST_RESULTS.md` for the exact before/after counts.
