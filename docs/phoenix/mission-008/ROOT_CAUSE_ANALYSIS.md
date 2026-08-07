# Mission 008 — Root Cause Analysis

## Common root cause

All 3 items share the same shape: a proactive-surface display (notification bell, case
Timeline, firm-wide Calendar) computed its own local signal instead of consulting — or fully
reconciling against — a field the backend already computed correctly, and that local signal
drifted from reality under normal, non-adversarial use (a 2nd device, a 2nd code path writing
the same fact, a classification function built before all 3 narrative call sites existed).

## `-050` — notification read-state

`_notifRead` (a `localStorage`-backed `Set`) was introduced as the read-state source before
`GET /notifications` returned a real per-row `procitano` field was leaned on for anything beyond
optimistic same-session UI updates. The write side (`mark_read`/`mark_all_read`) correctly
updates both the server row and `_notifRead` together, so a single-device, single-tab session
never observed drift — the gap only manifests cross-device (desktop marks read, mobile still
shows it unread and counts it in the badge) or cross-browser-profile, which is precisely the
class of bug that doesn't show up in a same-machine manual test pass.

## `-051` — duplicate closure Timeline entry

`intelligence_timeline.py` step 7's comment-free unconditional `if predmet.get("status") ==
"zatvoren"` block was written to guarantee closure is ALWAYS visible on the Timeline even if
`predmet_hronologija` has no matching row for some historical/edge-case closure path. That
defensive intent was correct, but it didn't anticipate that `predmeti_close.py` (the normal,
common closure path) already writes exactly the row it was trying to guarantee — so for every
case closed the normal way, both step 4 and step 7 contributed a "Predmet zatvoren" entry.

## `-053` — narrative entries misclassified as deadlines

`_klasifikuj_dogadjaj` was written when `predmet_hronologija` only held 2 kinds of content:
AI-extracted procedural deadlines and zastarelost warnings — a 2-bucket classifier was
completely correct for that world. 3 more call sites were added later
(`predmeti_close.py`'s closure note, `rocista.py`'s follow-up note, `ugovor_zastupanja.py`'s
engagement note), each a legitimate use of the same shared table for a genuinely different kind
of fact (a narrative record, not an action item with a due date), without a corresponding update
to the one function responsible for classifying `predmet_hronologija` rows for calendar display.

## Why these are safe, bounded fixes (not new algorithms)

- `-050`'s reconciliation is a pure set-union against a field the backend already computed and
  returns — reuses existing infrastructure, adds no query, no migration.
- `-051`'s guard reuses the exact `hron_r.data` step 4 already fetched — no 2nd query.
- `-053`'s 3rd bucket matches literal, known, fixed prefixes rather than attempting a generic
  "is this a deadline" classifier — a genuine unknown deadline text still safely defaults to
  `rok_dokument`, its pre-mission behavior.
