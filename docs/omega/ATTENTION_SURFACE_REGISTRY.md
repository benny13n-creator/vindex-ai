# Attention Surface Registry — Program Omega, Final Sprint 006 (2026-08-06)

Phase 1's own required deliverable: absolutely every mechanism, repo-wide, that determines priority,
urgency, color, order, warnings, badges, or dashboard ordering. Builds on Sprint 004/005's own findings
(`OMEGA-010`/`011`/`017`/`018`) — re-verified with fresh file:line citations — plus this sprint's own
dedicated forensic pass, which found 3 previously-uncatalogued items. Every claim below cites a file:line
actually read.

## Priority/urgency VOCABULARIES (word-scales for "how important")

| # | Vocabulary | Values | File:line | Status |
|---|---|---|---|---|
| 1 | `case_actions.prioritet` | critical/high/medium/low/informational | `migrations/099_case_actions.sql` (CHECK constraint) | **CANONICAL ANCHOR** — see `CANONICAL_ATTENTION_MODEL.md` |
| 2 | `identify_case_problems.ozbiljnost` | kritican/vazan/info | `services/risk_engine.py:157` | Source (Core Consolidation, 2026-07-22) — mapped to canonical |
| 3 | `notifications.priority` (`NOTIF_TIPOVI`) | urgent/high/normal/low/info | `routers/notifications.py:28-52` | Mapped to canonical this sprint |
| 4 | `notifications` row-level `prioritet` field | (was) hitan/normalan/info — **a real bug** | `routers/notifications.py:181,222` (pre-fix) | **Fixed this sprint** — see `ALERT_CONSOLIDATION_REPORT.md` |
| 5 | `zadaci.prioritet` | hitno/visoko/normalan/nisko | `migrations/045_firm_intelligence.sql` (CHECK constraint) | Mapped to canonical (Sprint 004, formalized this sprint) |
| 6 | CIO `kriticnost` | 0-100 numeric | `routers/cio.py` (`_CIO_SYSTEM` prompt) | GPT-advisory, documented not migrated |
| 7 | Cockpit risk `nivo` | nizak/srednji/visok | `static/vindex.js::pred_renderCockpit` | Different concept (case RISK, not action priority) — documented, not merged |
| 8 | Genome `nedostaje[].hitnost` | kriticno/vazno/pozeljno | `routers/case_dna.py:120` (extraction prompt) | GPT-advisory, documented not migrated |
| 9 | `_delta_hitnost` (Genome-change alert) | hitna/normalna | `routers/case_dna.py:405-414` | Different concept (diff significance) — already deduplicated once (Program Gamma) |
| 10 | `routers/inbox.py` internal sort vocabulary | kriticno/visok/srednji/nizak | `routers/inbox.py:40` | Mapped to canonical this sprint |
| 11 | `api.py::predmet_workspace`'s `_VAZNOST_ORDER` | kritičan/bitan/normalan/ostalo | `api.py:5195` (pre-fix line) | Mapped to canonical this sprint |
| 12 | `api.py`'s (retired) `GET /api/notifications` inline scale | visoka/srednja/niska | `api.py:5612` (pre-fix line, now deleted) | **Retired this sprint** (whole endpoint removed, dead) |
| 13 | `routers/strategija.py` GPT prompt field | hitan/normalan/opciono | `routers/strategija.py:363` | GPT-advisory, on-demand, documented not migrated |

**13 independent vocabularies confirmed** — more than the "8-9" `OMEGA-018` originally estimated. 5 are
now mechanically DERIVED from the one canonical model (`shared/attention_priority.py`, this sprint); 1
buggy one is fixed; 1 dead one is deleted; the remaining 6 are GPT-advisory or measure a genuinely
different concept (risk level, diff significance) — documented, not force-merged.

## ORDER/SORT mechanisms (repo-wide `_ORDER = {...}` dicts and equivalent sort keys)

Confirmed via `grep -rn "_ORDER\s*=\s*{"` across every `.py` file:

| Dict | File:line | Fate this sprint |
|---|---|---|
| `_PRIORITY_ORDER` | `routers/case_actions.py:37` (pre-fix) | Now `= shared.attention_priority.CANONICAL_ORDER` directly |
| `_PRIORITET_ORDER` | `routers/inbox.py:40` (pre-fix) | Now derived from `INBOX_TO_CANONICAL` |
| `PRIORITY_ORDER` | `routers/notifications.py:54` (pre-fix) | Now derived from `NOTIFICATIONS_TO_CANONICAL` |
| `_VAZNOST_ORDER` | `api.py:5195` (pre-fix) | Now derived from `VAZNOST_TO_CANONICAL` |
| `{"visoka":0,"srednja":1,"niska":2}` (inline, unnamed) | `api.py:5612` (pre-fix) | Deleted with its whole (dead) endpoint |
| `_ZADACI_PRIORITET_MAP` | `routers/workspace.py:50` (pre-fix) | Now `= shared.attention_priority.ZADACI_TO_CANONICAL` directly |
| `_WS_PRIO_COLOR` | `static/vindex.js:1676` | Frontend copy of `CANONICAL_COLOR` — JS/Python can't literally share a constant, kept in sync by comment cross-reference |
| `_TIER_ORDER` | `shared/permissions.py:59` | **Not attention-related** (subscription tier, not case/action priority) — excluded |

## A 4th independent, previously-uncatalogued alert/notification system found this sprint

`GET /api/notifications` (`api.py:5511-5619`, pre-fix line numbers) — docstring: *"Computed notifications
— bez novog DB table-a."* Fully separate from `routers/notifications.py`'s DB-backed `GET
/notifications` (the one the frontend's own `notif_load()` actually calls, confirmed
`static/vindex.js:10952`-adjacent). Computed its own 3 notification types (upcoming rokovi, risk-level
changes — duplicating `routers/dashboard.py`'s own risk-trend detector — and "case with no linked
client"), its own 9th priority vocabulary. **Confirmed zero frontend callers** — grepped
`static/vindex.js` for `/api/notifications`, no matches. **Retired this sprint** — see
`ALERT_CONSOLIDATION_REPORT.md`.

## A name-colliding, but NOT functionally duplicating, "workspace" concept found this sprint

`GET /api/predmeti/{predmet_id}/workspace` (`api.py:4944`, `predmet_workspace`) — a real, live,
per-CASE "everything about this case" aggregation (stranke, dokumenti, rokovi, komentari, beleske,
komunikacija, istorija, sudska praksa preview) — the actual backend for the case-detail Cockpit panel.
Pre-dates and is genuinely different in SCOPE from the new portfolio-wide `GET /api/workspace` (Sprint
004/005 — "what needs attention across ALL my cases"). Confirmed already correctly grounded in the
canonical `risk_engine.py` functions for its own risk/problem display (its own `_COCKPIT_SYSTEM` GPT
prompt explicitly instructs the model NOT to decide risk/priority itself, `api.py:5057-5067` area — a
positive example of AR-01 compliance, not a violation). Its own `_VAZNOST_ORDER` sort dict is now
canonicalized (see above). The NAME collision itself is a legitimate, if lower-severity, finding —
documented, not renamed this sprint (renaming a live, tested route is a bigger, riskier change than
this sprint's own scope; named as a debt item).

## GPT prompts that output a priority/urgency/severity field (non-deterministic sources, by design)

- `routers/strategija.py:363` — `sledeci_koraci[].prioritet: "hitan"|"normalan"|"opciono"`, on-demand
  simulation output.
- `routers/case_dna.py:120` — Genome extraction prompt, `nedostaje[].hitnost: "kriticno"|"vazno"|"pozeljno"`.
- `routers/cio.py`'s own `_CIO_SYSTEM` prompt — `kriticnost: 0-100`.
- `api.py`'s own `_COCKPIT_SYSTEM` prompt (`api.py:5057-5067`) — explicitly instructs the model NOT to
  decide priority itself ("NE odredjuj ga sam, samo objasni ZASTO") — cited as a POSITIVE example, not
  a violation; already AR-01-compliant.

None of these are migrated onto the canonical model this sprint (mission's own explicit rule: no new AI
logic, no touching live GPT prompts without live-browser verification) — documented per Phase 1's own
"repo-wide, no exceptions" mandate, decision recorded in `CANONICAL_ATTENTION_MODEL.md`.

## Warning/badge producers not yet covered above

- Genome's own `case_dna.upozorenja`/`najslabija_tacka` fields (`routers/case_dna.py`) — GPT-advisory,
  embedded in the same JSON object Core Consolidation already treats as canonical for FACTS
  (`kontradikcije`, `datumi_kljucni`) but not for these opinion fields — unchanged, same reasoning as
  Sprint 003's own `ACTION_PRODUCER_REGISTRY.md` Producer 6.
- `routers/health_index.py`'s own `_compute_weak_signals`/`inst_risks` — firm-level (portfolio, not
  per-case) warning producer, consistent scope with Sprint 004's own "different scope, kept" verdict.

## Deadline/urgency day-count thresholds — confirmed INCONSISTENT across systems

| System | Threshold for "critical/hitan" | File:line |
|---|---|---|
| `case_actions` Rule 1 (`_priority_by_days`) | ≤3 days = critical, ≤7 = high | `services/case_evolution.py::_priority_by_days` |
| `routers/notifications.py`'s own `hitan_rok` | ≤2 days | `routers/notifications.py:174` (`in_2_iso`) |
| `routers/dashboard.py`'s own `hitni_rokovi` | ≤2 days | `routers/dashboard.py` (`in_2_iso`) |
| `api.py`'s (retired) computed notifications | ≤3 days OR `vaznost=="kritičan"` | `api.py` (deleted this sprint) |

**Not reconciled this sprint** — these are 3-4 different, independently-chosen day-count thresholds for
what "critical" means, all still live in different systems. Named as a debt item
(`OMEGA-021`, Debt Register) rather than silently unified — changing a threshold changes WHEN a real
lawyer sees an alert, a behavior change beyond "canonicalize existing wording," judged too risky to
guess at without a product decision on which threshold is actually correct.
