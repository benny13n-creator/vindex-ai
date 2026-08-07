# Mission 008 — Test Results

## New tests: `tests/test_phoenix_mission_008_notification_timeline_calendar_consistency.py`

| Test | Verifies |
|---|---|
| `test_klasifikuj_dogadjaj_case_closure_is_napomena` | Case-closure text classified `napomena` |
| `test_klasifikuj_dogadjaj_hearing_followup_is_napomena` | Hearing follow-up text classified `napomena` |
| `test_klasifikuj_dogadjaj_ugovor_zastupanja_is_napomena` | Engagement-letter text classified `napomena` |
| `test_klasifikuj_dogadjaj_zastarelost_unaffected` | Pre-existing zastarelost classification unchanged |
| `test_klasifikuj_dogadjaj_real_deadline_stays_rok_dokument` | Genuine deadline text still defaults `rok_dokument` |
| `test_intelligence_timeline_skips_synthesized_closure_when_hronologija_already_has_one` | No duplicate closure entry when hronologija row exists |
| `test_intelligence_timeline_still_synthesizes_when_no_hronologija_closure_row` | Synthesized entry still fires when no matching row |
| `test_intelligence_timeline_open_case_unaffected` | Open case never synthesizes a closure entry |
| `test_notif_load_merges_server_procitano_into_local_read_set` | Cross-device read-state reconciliation present |

**Result: 9 passed, 0 failed.**

## Subsystem tests (kalendar/intelligence_timeline/notifications/rocista/frontend structural)

**Result: 126 passed, 0 failed.**

## Full repository regression suite

| | Passed | Skipped | Failed |
|---|---|---|---|
| Baseline (post-Mission 007) | 3,257 | 1 | 0 |
| Post-Mission 008 | 3,266 | 1 | 0 |

Net +9 (exactly the new mission tests). **Zero regressions.** (395.54s)

## Red Team self-check

1. **Notification merge — can it hide a genuinely new unread notification?** No — the merge
   only ever adds ids where `n.procitano === true`; a freshly-generated unread notification has
   `procitano === false` and is never added to `_notifRead`, so it still counts and displays as
   unread.
2. **Notification merge — race between a same-device optimistic mark-read and the next
   `notif_load()`?** `mark_read`/`mark_all_read` already add to `_notifRead` synchronously
   before the network call resolves; the next `notif_load()` merge is idempotent (`Set.add` on
   an id already present is a no-op), so no ordering issue.
3. **Timeline dedup — could it suppress a LEGITIMATE 2nd "Predmet zatvoren"-prefixed entry, e.g.
   if a case is closed, reopened, and closed again?** Reopening sets `status` away from
   `"zatvoren"`, so step 7 doesn't fire on the reopened case; on the 2nd real closure,
   `predmeti_close.py` writes a 2nd hronologija row and step 4 already surfaces it — the guard
   only ever suppresses step 7's OWN synthesized entry, never a 2nd real hronologija row, so
   both real closures still appear in the Timeline exactly once each.
4. **Calendar napomena bucket — could a real deadline whose text happens to start with one of
   the 3 prefixes get miscategorized?** All 3 prefixes are Serbian narrative-sentence openers
   ("Predmet zatvoren", "Follow-up ročište", "Ugovor o zastupanju zaključen") that only this
   engagement's own 3 known write sites ever produce verbatim at the start of a `dogadjaj`
   string (verified via `grep` across the whole `routers/`/`services/` tree, see Mission 008's
   reproduction phase) — no deadline-generation code path (`intake.py`'s legal-timeline
   templates, `rokovi_lanac.py`, `smart_intake.py`, `copilot.py`) produces text starting with
   any of them.

No break found. **Mission 008 STOP GATE: PASS.**
