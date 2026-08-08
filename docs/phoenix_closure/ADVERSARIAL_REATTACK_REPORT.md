# Phoenix Closure — Phase 5 Adversarial Re-Attack Report

**Date**: 2026-08-08
**Scope**: every claimed closure from Phase 3 (6 fixes) and Phase 4 (9 fixes) — an attempt to
DISPROVE each, not confirm it, per the operation's own instruction: *"The Red Team must attempt to
DISPROVE every claimed closure. They are not there to confirm it."*

## Attack surface covered

Tenant isolation, stale state, concurrent/duplicate execution, failed DB writes, GPT-poisoning
(where applicable), cross-module truth divergence, cache contamination, frontend/backend
disagreement — applied per-fix, only where the fix's own surface makes that vector meaningful (not
every vector applies to every fix; e.g. GPT-poisoning is not relevant to a pure disclosure field).

## Finding 1 (REAL, FIXED) — `-035` case-switch race in `_buildPredmetKontekst`

**Attack**: user opens Case A (context re-fetch begins, in flight), navigates to Case B before the
fetch resolves (`pred_loadDetail` correctly sets `window._predFull` to Case B's data). Case A's
fetch then resolves and — in the original implementation — unconditionally overwrote
`window._predFull` with Case A's data, silently reintroducing wrong-case content into Case B's
context. This is **worse** than the bug `-035` was fixing (a stale snapshot of the SAME case),
since it's now a **wrong case's** data leaking into an active context.

**Fix**: `_fetchedForId` is captured at fetch-start; the overwrite is now gated on
`activePredmetId === _fetchedForId`, so a stale in-flight response for an abandoned case can never
clobber the currently-active case's data. Proof:
`tests/test_phoenix_closure_open_items.py::test_build_predmet_kontekst_guards_against_case_switch_during_fetch`.

## Finding 2 (test gap, closed) — `-046` winner-crash-mid-generation path was untested

**Attack**: the in-process winner's own `_generiši_cio_izvestaj` call genuinely raises (not just
times out). Does the `finally` block still release the waiting loser? Does the loser correctly
detect the still-empty placeholder row and fall back to its own generation, rather than returning a
broken/empty response?

**Result**: code reading confirmed the `finally` block already runs regardless of whether the
`except` clause re-raised, and the loser's own `if _fresh.data and _fresh.data.get("izvestaj")`
guard already correctly treats an empty placeholder as "not ready" and falls back — this was
already correct by construction, just not explicitly tested. Added
`tests/test_phoenix_closure_partial_items.py::test_cio_daily_loser_falls_back_when_inflight_winner_crashes`
to lock this in.

## Finding 3 (reasoned through, confirmed safe by design, no fix needed) — `-046` early wake-up race

**Attack**: `done_event.set()` fires immediately after `_generiši_cio_izvestaj` returns, which is
*before* the winner's own `UsageService.consume()` + "Snimi" persist step runs. A loser woken at
exactly this instant would read the row while it's still the empty placeholder.

**Result**: this is real, but non-harmful — the loser's own guard (`_fresh.data.get("izvestaj")`
must be truthy) means an early wake-up simply falls through to the loser generating its own report
(the exact pre-fix behavior), never returns an incorrect/empty response. A narrow missed-
optimization window, not a correctness bug. Already covered by Finding 2's own test (same code
path: event fires, row still placeholder, loser correctly falls back).

## Finding 4 (inherited characteristic, disclosed, not a new regression) — `-042`'s reaper has no atomicity guarantee

**Attack**: two overlapping cron invocations of `reap_missing_rociste_events` could both see the
same missing hearing and both insert a backfill `ROCISTE_ZAKAZANO` event (a plain SELECT-then-
INSERT, no `UNIQUE` constraint on the `events` table for this key).

**Result**: this exact non-atomic pattern is inherited unchanged from the already-accepted
`reap_missing_pipeline_events` this mission's own fix was explicitly modeled on — not a new
regression introduced by `-042`. Severity is low (daily cron, `min_age_minutes=10` guard already
reduces overlap likelihood) and, notably, even a duplicate backfilled event is now caught
downstream by `-011`'s own new `genome_refresh` dedup (event-scoped, would treat the 2nd event's
consequence as a duplicate reclaim within the window) — a genuine defense-in-depth improvement this
same operation already shipped. Disclosed here, not fixed — fixing the reaper's own atomicity would
require a migration (a `UNIQUE` constraint), the same class of infra dependency already correctly
deferred elsewhere in this operation.

## Findings that did NOT hold up (attacked, disproved as real issues)

- **`-011` XSS via embedded `event_id` in the genome-history trigger label**: the new
  `case_evolution:{event_id}` string is mapped to the friendly literal `'automatski'` before ever
  reaching the DOM (`static/vindex.js`'s history renderer), and even the raw fallback path already
  goes through `escHtml()`. No injection surface.
- **`-011` cross-event conflation via a coarse dedup key**: this was the ORIGINAL design flaw
  self-caught and fixed during implementation (documented in the ledger) — the shipped version
  scopes the dedup key to the specific `event_id`, not a shared label. Verified via
  `test_genome_refresh_different_event_ids_are_not_conflated`.
- **`-020`/`-036` cross-tenant leakage**: both re-verified to filter by `user_id` (and `-036`
  additionally by `predmet_id`) at the exact query that matters — no cross-tenant data exposure.
- **`-025`/`-026` disclosure fields creating a new GPT-trust boundary**: both are purely additive,
  server-controlled (not GPT-generated) fields — no new poisoning surface introduced.
- **`-023` OCR confidence computation crashing on malformed `pytesseract` output**: `image_to_data`
  is a hard library contract (same-length columns guaranteed); even in a hypothetical malformed
  case, `_ocr_image`'s existing outer try/except (already wrapping the `eng`-fallback retry) fails
  safe to `("", None)`, never propagates an unhandled exception.

## Verdict

1 real regression found and fixed (`-035`'s case-switch race — the most severe finding, since it
could have introduced wrong-case data into a legal drafting context, arguably worse than what it
replaced). 1 real gap in test coverage closed (not a code bug). 2 theoretical risks reasoned through
and confirmed safe by the fixes' own existing design. 1 inherited, disclosed, low-severity
characteristic left as-is, consistent with established precedent and out of this mission's bounded
scope to fix (would need a migration).

**No fix from Phase 3 or Phase 4 was withdrawn or reverted as a result of this pass** — the one real
bug found was in a fix's implementation detail (a race condition), not in its underlying premise,
and was corrected in place.
