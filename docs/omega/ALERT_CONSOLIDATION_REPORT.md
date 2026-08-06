# Alert Consolidation Report — Program Omega, Final Sprint 006 (2026-08-06)

Phase 4's own required deliverable: prove whether the alert tables genuinely need to exist. If not,
remove them. If they must, designate one canonical and the rest as projections. Never let two systems
decide the same event.

## The count going in: 4, not 3

`OMEGA-010` named 3: `proactive_alerts`, `notifications`, `case_actions`. This sprint's own Phase 1 pass
found a 4th: `api.py`'s own `GET /api/notifications` — a fully self-contained, computed-on-the-fly alert
list (no table of its own, but its own independent priority decisions nonetheless).

## Verdict per system

### `api.py::GET /api/notifications` — DOES NOT NEED TO EXIST. Removed.

Confirmed: zero frontend callers (grepped `static/vindex.js`, no matches), zero writes (pure read/
compute), zero other backend callers (grepped the whole repo for `get_notifications` — the only 2 hits
are this function's own declaration and the unrelated, differently-scoped `routers/notifications.py::
get_notifications`). The cleanest possible elimination: nothing in the platform depends on it, deleting
it changes zero observable behavior for any real user. **Deleted, not just unwired** — ~110 lines
removed from `api.py`.

### `proactive_alerts` — MUST exist. Designated CONSUMER-facing internal projection, not canonical.

4 real readers confirmed (`routers/case_intelligence.py`, `routers/decision_replay.py`,
`routers/matter_intel.py`, `routers/morning_briefing.py`) and ~10 real writers (event handlers,
`case_dna.py`, `zakon_monitoring.py`, `zadaci.py`, `workflow.py`, `case_evolution.py` — Sprint 003's own
`ACTION_PRODUCER_REGISTRY.md`, Producer 2, re-confirmed unchanged). This is internal, cross-module
plumbing — other BACKEND code consults it, not a lawyer-facing surface on its own. Removing it would
break 4 real features. **Kept**, not touched.

### `notifications` (DB table, `routers/notifications.py`) — MUST exist. The lawyer-facing bell icon.

Confirmed live on every page (`static/vindex.js::notif_load()`), genuinely different function from
`case_actions` (ambient "something changed" awareness vs. a tracked, lifecycle-managed operational
action) and from `proactive_alerts` (user-facing vs. internal-only). **Kept**, its own real bug fixed
this sprint (see below).

### `case_actions` — the canonical SOURCE for the one concept all 3 remaining systems touch.

Deterministic, sourced, lifecycle-managed (Sprint 003). Designated canonical for "what does the lawyer
need to DO" — the concept `notifications`' own `rok`/`hitan_rok` types and `proactive_alerts`' own
`ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` handlers both ALSO independently detect from the same underlying
`rocista`/`predmet_hronologija` tables.

## Two decisions about the SAME event — found and characterized, not silently merged

A single real-world fact — "this hearing is in 2 days" — currently produces **up to 3 independent
writes**: a `case_actions` row (via `_compute_target_actions`'s own Rule 1, triggered by
`ROCISTE_ZAKAZANO`/`DOCUMENT_ACCEPTED` events), a `notifications` row (via
`_generate_notifications`'s own `hitan_rok` branch, triggered by its own 6-hour refresh cycle), and
potentially a `proactive_alerts` row (via the `ROK_KRITICAN` event handler, `services/event_bus.py`).
**This is precisely the "dva mesta koja odlučuju o istom događaju" pattern Phase 4 forbids** — found,
not hidden.

**Why not fully unified this sprint**: making `notifications`/`proactive_alerts` literally READ FROM
`case_actions` instead of independently querying `rocista` is a real trigger-path redesign — a bigger,
riskier change than "canonicalize existing wording" (this sprint's own explicit charter: no new
algorithm, no new logic, only consolidate what exists). The 3 systems' own day-count thresholds for
"urgent" also currently DISAGREE (`ATTENTION_SURFACE_REGISTRY.md`'s own table: ≤2 vs ≤3 days) — unifying
the write paths without first resolving which threshold is correct risks silently changing WHEN a lawyer
gets alerted, a real behavior change this sprint's own mission explicitly forbids introducing blind.

**What WAS done this sprint, safely**: the VOCABULARY all 3 systems use to describe urgency is now one
canonical scale (`shared/attention_priority.py`) — so even though 3 writes can still happen for the same
fact, they now at least AGREE on what "critical" means in principle, and a lawyer reading
`case_actions`-sourced Workspace and the `notifications` bell icon side by side sees the same color/word
for the same underlying urgency level, not 2 different vocabularies describing possibly-different
severities for what should be the same fact.

## A real, independent bug found and fixed in `notifications.py` itself

Two of `_generate_notifications`'s own 2 item-generation blocks wrote a row-level `"prioritet"` value
that was NOT a member of `PRIORITY_ORDER`'s own vocabulary (`"hitan"`/`"normalan"` instead of
`"urgent"`/`"high"`/`"normal"`/`"low"`/`"info"`). Because `_grupiraj_notifikacije`'s own sort key does
`n.get("prioritet") or NOTIF_TIPOVI.get(tip, {}).get("priority", "normal")` — a truthy-but-WRONG
`prioritet` value always won over the correct tip-based fallback. Concretely: **every `hitan_rok`
notification silently sorted as if it were `"normal"` priority** (`PRIORITY_ORDER.get("hitan", 2) == 2`,
the exact same rank as `"normal"`), meaning an urgent 2-day-away hearing reminder never actually
surfaced above an ordinary 7-day reminder in the bell icon's own list — a real, live, previously-unknown
bug, found as a direct consequence of building the canonical translation layer (the mismatch became
impossible to miss once every vocabulary had to be written down in one place to be translated).

**Fixed**: both blocks now derive `prioritet` from `NOTIF_TIPOVI[tip]["priority"]` — the SAME lookup
`trigger_notifikacija()` (this file's own other insertion path) already correctly used — one source of
truth (`tip`), not a second hand-typed value. Proven by
`tests/test_omega_sprint006_canonical_attention.py::test_hitan_rok_notification_gets_high_priority_not_the_old_broken_value`
and `test_grupiraj_notifikacije_sorts_hitan_rok_before_ordinary_rok`.

## Summary

| System | Verdict | Action |
|---|---|---|
| `api.py::GET /api/notifications` | Does not need to exist | **Deleted** |
| `proactive_alerts` | Must exist, internal projection | Kept, unchanged |
| `notifications` (DB table) | Must exist, user-facing | Kept, own row-level bug fixed |
| `case_actions` | Canonical source | Kept, unchanged, now feeds the shared vocabulary all others translate through |

**Named, not hidden**: up to 3 writes can still occur for the same real-world deadline fact
(`case_actions`, `notifications`, `proactive_alerts`), and their day-count thresholds for "urgent" still
disagree. This is `OMEGA-020`/`OMEGA-021` in the Debt Register — a genuine, bounded gap this sprint could
not safely close without either a product decision (which threshold is correct) or a larger trigger-path
redesign, both explicitly out of this sprint's own "canonicalize existing, build nothing new" charter.
