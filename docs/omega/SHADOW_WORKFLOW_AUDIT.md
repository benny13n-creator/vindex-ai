# Shadow Workflow Audit — Program Omega, Final Sprint 005 (2026-08-06)

Phase 2's own required deliverable. Sprint 004 found 12 surfaces, 3 alert systems, 5+ priority models
and made firm stays/submodule/retire decisions for each — but decision is not elimination. This sprint's
own charter is blunter: "ako postoje dva mesta koja prikazuju istu stvar: jedno mora prestati da
postoji." This document records every shadow workflow found THIS sprint (some newly discovered, not
in Sprint 004's own registry) and exactly what was done about each — eliminated, or named with a
concrete reason it wasn't safe to eliminate blind.

## Eliminated this sprint

### 1. Two complete `_dashRender` implementations — one silently dead (frontend)

`static/vindex.js` had `function _dashRender(d,bd,inboxData){...}` (the original home-page renderer)
and, ~400 lines later, a plain reassignment `_dashRender = function(d, bd, inboxData) {...}` (marked
`/* FAZA 1.8 — Komandni centar: Sphere-inside + greeting + 4-col */`). In JavaScript, the later plain
assignment silently overwrites the earlier `function`-declared binding — by the time `dash_load()` ever
calls `_dashRender(...)`, only the SECOND one has ever run. The first (~180 lines) was 100% dead code,
undetected until this sprint because nothing ever threw an error — it just quietly never executed.

**Consequence found alongside it**: the dead version was the ONLY one that ever produced 3 DOM
containers (`#briefing-card`/`#briefing-content` for Morning Briefing, `#cc-ai-nalazi` for Case
Commander's findings, `#hi-widget` for Health Index) that 3 separate async loader functions
(`loadBriefing`, `_ccCaricaAiAnaliza`, `_healthIndexLoad`) look up by `document.getElementById(...)`
and silently no-op if missing. **This means 3 of Sprint 004's own "6 confirmed-live home page widgets"
were actually already fully invisible** — Sprint 004's own `WORKSPACE_SURFACE_REGISTRY.md` verified
"live" by finding matching code/div-ids SOMEWHERE in the file, not by confirming they were in the
actually-executing render path. A real, if narrow, verification gap in that registry, corrected here.

**Eliminated**: the entire dead `_dashRender` v1 body, plus its exclusive-caller descendants
(`_ccBrifingHtml`, `_ccCaricaAiAnaliza`, `loadBriefing`, `_renderBriefing`, `toggleBriefing`,
`posaljiBriefingEmail`) — ~440 lines removed, zero behavior change (none of it ran). Health Index's own
container was RESTORED into the live `_dashRender` (Sprint 004 explicitly wanted it kept, its
disappearance was an accident of an unrelated refactor, not a decision). Morning Briefing's/Case
Commander's own in-app cards were NOT restored — their content is now redundant with the new Workspace
section (see below), and their own genuinely-still-live channels (Morning Briefing's automatic daily
email cron; Case Commander's own on-demand endpoints) are completely unaffected.

### 2. Two complete `kalendarLoad` implementations — same exact pattern, second instance

Identical shape: `function kalendarLoad() {...}` (original) shadowed by a later `kalendarLoad =
function() {...}`. Verified the old version's own exclusive callee (`_kalendarRender`) is STILL called
by the live version (via `_kalRenderActive`), so only `kalendarLoad` v1 itself (~40 lines) was dead —
narrower than the dashboard case. **Eliminated**: the old `kalendarLoad` v1 body only; every helper it
shared with the live version (`_kalendarRender`, `_kalRenderActive`, `_kalRenderGrid`, `kalSetView`,
`kalMesecPrev/Next/Today`, `kalDayClick`) untouched, confirmed still reachable.

**A real, narrower gap found alongside this one, NOT fixed** (out of this sprint's Workspace-focused
scope, named instead): the live `kalendarLoad` dropped the old version's own fallback
`fetch('/api/predmeti')` for when the global `_predmeti` isn't populated yet — the ročište-creation
form's own predmet dropdown (`_kalendarPredmeti`) could show empty in that specific timing case. Named
as `OMEGA-016`.

### 3. `_kcPanelPreporuke` ("Preporuke" panel) — text rephrasing of facts Workspace now shows sourced

Rendered `d.ai_preporuke`, Command Center's own rule-based text recap (already named in Sprint 004's
`WORKSPACE_DATA_OWNERSHIP.md` as a "should eventually link to Workspace" candidate). Zero unique
information — every fact it restated (rokovi, rizik, dokumenti, neaktivnost) is either already covered
by `_kcPanelRokovi`/`_kcPanelAktivni` (unchanged, kept — see "Not eliminated" below) or now shown,
sourced and clickable, by the new Workspace section. **Eliminated**: the function and its one caller.

### 4. `routers/inbox.py`'s own `rociste`/`rok` item generation — a THIRD independent alert computation

**Newly discovered this sprint, not in Sprint 004's own registry** (that registry was scoped to
"action producers"/"workspace surfaces" by name — `/api/inbox` fell outside both keyword searches).
`GET /api/inbox` (`routers/inbox.py`, "Vindex OS — PRIORITET 3", live on the SAME home page as
Workspace, in its own "Inbox — Prioritetne stavke" section) independently queried `rocista` and
`predmet_hronologija` and computed its OWN priority-sorted hearing/deadline list under a 6th vocabulary
(`kriticno`/`visok`/`srednji`/`nizak`) — the most literal possible instance of "dva mesta koja
prikazuju istu stvar": both endpoints deterministic, both reading overlapping source tables, both
rendered on the identical page.

**Eliminated**: the `rociste`/`rok` item-generation blocks and their DB queries, from `routers/inbox.py`
directly (not just hidden on the frontend) — `case_actions`/Workspace is the newer, sourced,
lifecycle-managed engine; it wins. 6 now-invalid tests removed/rewritten in `tests/test_inbox.py`
(`rociste`-today/future, `rok`-kritican/bitan/ordinary, kriticno-sorts-first).

**A second-order bug found and fixed in the same pass**: the frontend's own Inbox rendering filtered
`stavke` for `prioritet === 'kriticno' || 'visok'` ONLY — but `dokument`/`naplata`/`neaktivan` (the 3
categories that remain, genuinely non-duplicated) were ALWAYS `srednji`/`nizak`, meaning this filter had
ALWAYS excluded them, even before this sprint — they were computed every page load and never once shown.
Fixed: the section now shows its own remaining categories (relabeled "Ostalo za pregled"), completing a
previously-silently-broken feature rather than just deleting more code.

## Decided, NOT eliminated — with a concrete reason

### 5. `_kcPanelRokovi` ("Današnji rokovi" panel) — kept as a Workspace coverage safety net

Genuinely overlaps with Workspace's own Danas/Kritično buckets for hearing/deadline items (both
ultimately read `rocista`). **Not eliminated**, because of a real, verified coverage gap: `case_actions`
only populates via 4 specific Case Evolution events — any predmet that existed before Sprint 003 shipped,
or hasn't had a qualifying event since, has ZERO `case_actions` rows, and Workspace would show it as
falsely empty. `_kcPanelRokovi` reads `rocista` directly, with no such dependency — it is the honest
safety net until `scripts/backfill_case_actions.py` (built this sprint, named `OMEGA-014`) is actually
run. Removing it now would be a real regression, not a cleanup, for any case the backfill hasn't
reached yet.

### 6. `proactive_alerts` / `notifications` — different function (FYI vs. operational), not merged

Re-confirmed this sprint, unchanged from Sprint 004's own Responsibility Matrix: these are ambient,
passive "something changed" signals (the bell icon, global on every page), not a verifiable operational
worklist. Genuinely different concept from `case_actions`. Not touched.

### 7. Command Center's own `predmet_istorija["[Rizik]"]` trend detector — verified NOT a duplicate

Investigated closely this sprint (not just cited from Sprint 004): reads a HISTORY of past logged risk
assessments to detect "did risk get worse between two successive readings" — a trend-over-time
comparison, genuinely different from `risk_engine.py`'s own live deterministic score. Not a fixable
duplicate on closer inspection; left unchanged (Sprint 004's own `WORKSPACE_DATA_OWNERSHIP.md`, Finding
3, re-confirmed).

### 8. Case Commander / Morning Briefing / CIO Daily — GPT narrative layers, demoted not deleted

Sprint 004's own Responsibility Matrix decision ("postaje podmodul") stands, unchanged this sprint —
Sprint 004 already corrected each module's own self-description (Case Commander's "srce platforme"
claim was factually superseded — fixed, docstring only, committed `4f6bad4`). This sprint did not touch
any GPT prompt or remove any endpoint either — rewriting 3 live, credit-metered GPT features' own
behavior without live-browser verification is a real production risk this whole engagement has
consistently escalated rather than guessed at (see `OMEGA-012`/`OMEGA-017` in the Debt Register).

## Summary

| # | Shadow workflow | Verdict | Where |
|---|---|---|---|
| 1 | `_dashRender` v1 (dead, shadowed) | **Eliminated** | `static/vindex.js` |
| 2 | `kalendarLoad` v1 (dead, shadowed) | **Eliminated** | `static/vindex.js` |
| 3 | `_kcPanelPreporuke` (text dup of Workspace) | **Eliminated** | `static/vindex.js` |
| 4 | `/api/inbox`'s own rociste/rok computation | **Eliminated** | `routers/inbox.py` |
| 5 | `_kcPanelRokovi` (deadline panel) | **Kept** — Workspace coverage gap not yet backfilled | `static/vindex.js` |
| 6 | `proactive_alerts`/`notifications` | **Kept** — different function (FYI, not operational) | backend |
| 7 | Command Center's risk-trend detector | **Kept** — verified not a duplicate | `routers/dashboard.py` |
| 8 | Case Commander/Morning Briefing/CIO widgets | **Kept, demoted** — live GPT features, not touched blind | `routers/*.py` |
