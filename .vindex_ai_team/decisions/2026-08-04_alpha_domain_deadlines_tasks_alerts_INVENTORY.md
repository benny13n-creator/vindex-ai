# Program Alpha — Domain Inventory: Deadlines / Timeline / Task Generation / Alerts

Read-only investigation. No code changed.

## Decision table

| Business decision | Canonical location | Consumers | # implementations |
|---|---|---|---|
| Missing-document / task-worthy problem detection | `services/risk_engine.py::identify_case_problems` | `routers/zadaci.py::ai_analiziraj_predmet` (confirmed still routes through it, line 618/625 — Nexus's fix intact) | 1 (canonical, confirmed) |
| Deadline → Calendar, Deadline → Notifications wiring | Confirmed still connected per re-check | `routers/kalendar.py`, notification paths | 1 |
| `ROK_KRITICAN` / `HEALTH_SCORE_PROMENJEN` emission | `routers/matter_intel.py:153,166` via plain in-process `emit()` | Event Bus in-process handlers only | 1, but **not durable** (`SENT-001`, confirmed still open, unchanged since Sentinel/Keystone) |
| **Proactive alert creation** (`proactive_alerts` insert) | **NONE — no canonical function exists** | 9 files, 11 independent call sites | **11** |
| **"Is this deadline critical/urgent" threshold** | **NONE — no shared constant/function** | 6 files, each with its own inline magic number | **≥6 independent copies, 2 different threshold values (3 and 7 days)** |

## Hidden logic / duplication found

### 1. No canonical alert-creation service — the single highest-value finding in this domain

11 independent `supa.table("proactive_alerts").insert({...})` call sites, zero shared helper:
`services/event_bus.py` (3: `on_rok_kritican`, `on_health_score_promenjen`, `on_document_job_failed`),
`routers/case_dna.py` (3), `routers/zakon_monitoring.py` (2), `routers/morning_briefing.py` (1),
`routers/smart_intake.py` (1), `routers/workflow.py` (1), `routers/zadaci.py` (1).

**Historical proof this is a real, not theoretical, risk**: `routers/case_dna.py:758-763`'s own comment
documents that one of its 3 insert sites used wrong column names (`tekst_alerta`/`tip_alerta`/`hitnost`
instead of the real schema's `naslov`/`opis`/`tip`/`urgentnost`) and **silently failed on every single
call for the entire time the feature existed**, undetected until a 2026-07-18 "Reality Validation" pass
caught it by accident. Nothing prevents a *future* call site from drifting the same way — there is no
canonical function whose signature would catch a wrong field name at one shared point instead of eleven
independent ones.

**Reliability inconsistency this same gap causes today**: Project Phoenix (2026-08-03) added retry +
durable-audit-on-exhaustion specifically to `morning_briefing.py`'s own nightly alert-insert loop — a
**local patch to one call site**, not a canonical fix. The other 10 call sites still silently swallow a
failed insert with only a `logger.debug`/`logger.warning` line (`workflow.py:88`, `zadaci.py:134`,
`zakon_monitoring.py:277,559`, `case_dna.py:919` even uses a bare `except: pass`) — the exact same silent
-data-loss shape Phoenix's own report named as "the exact scenario proactive_alerts exists to prevent."
Phoenix fixed the symptom at the one call site its mission happened to touch; the cause (no canonical
service) means the same defect class still lives at 10 other call sites today.

### 2. "Deadline is critical" threshold duplicated with inconsistent values

The magic number for "how many days until a deadline counts as urgent/critical" is inlined independently
in at least 6 files, with at least 2 different actual values in active use:
- `routers/zastarelost.py:445-446`: `<=3` → "kritično", `<=7` → "hitno" (two-tier)
- `routers/morning_briefing.py:135`: `2 < days <= 7` → "rokovi_uskoro"
- `routers/matter_intel.py:333`: `0 <= days <= 7` → counted toward `kriticni_rokovi`
- `routers/ccc.py:146`: `0 <= dana <= 7`
- `routers/ccc.py:89`: `0 <= dana <= 30` (a materially different, wider window — worth confirming with
  Architecture Review whether this is a deliberately different concept, e.g. "upcoming" vs. "critical", or
  an actual inconsistency; not resolved in this pass, flagged for the canonicalization plan to investigate)
- `routers/cio.py:299`: `dana_do <= 7`

No shared constant (e.g. `KRITICNI_ROK_DANA = 7`) or shared function exists anywhere in `shared/`/
`services/`. A founder decision to change the threshold today would require finding and editing at least
6 call sites by hand, with a high chance of missing one (classic magic-number-drift risk).

## Source-of-truth violations

- **Alert creation**: no single author. 9 different modules each independently decide "this is
  alert-worthy" and independently construct the DB row. Per Program Alpha's Principle 2 (Single Source of
  Truth) and Principle 4 (No Duplicate Decisions), this is a direct violation — the "this needs an alert"
  decision and the "here's how you write an alert" mechanism are both un-owned.
- **Deadline criticality**: no single author for the "critical/urgent" *classification* itself (as
  distinct from the underlying days-until-deadline *calculation*, which Nexus already canonicalized in
  `risk_engine.py`). The calculation is centralized; the threshold applied to its result is not.
- **Task generation**: single source of truth confirmed intact (`identify_case_problems`) — no violation
  found here this pass.

## Prioritized recommendations (for Phase 5 synthesis, not implemented in this pass)

1. **Highest priority**: extract a canonical `create_proactive_alert()` function (natural home:
   `shared/` or `services/`, mirroring `shared/audit_immutable.py::log_action`'s own shape — a single
   function with named parameters, internal retry + durable-failure-audit built in once, not per call
   site) and migrate all 11 call sites onto it. This would have prevented the `tekst_alerta` bug
   structurally (a typo'd parameter name is a Python `TypeError` at the call site, not a silent Postgres
   schema-mismatch swallowed by a broad `except`), and would close Phoenix's reliability gap for the other
   10 call sites in one change instead of ten.
2. **Second priority**: extract a shared `KRITICNI_ROK_DANA` constant (or a canonical
   `je_rok_kritican(dana_do: int) -> bool` function) and migrate the 6 inline-threshold sites onto it —
   resolves the magic-number-drift risk and forces an explicit decision on the `ccc.py:89` 30-day-window
   discrepancy instead of leaving it ambiguous.
3. Not urgent, not attempted this pass: whether `SENT-001` (non-durable `ROK_KRITICAN`/
   `HEALTH_SCORE_PROMENJEN` emission) should finally be converted to the durable outbox — unchanged
   status, still gated on the dedup-safety verification named since Project Sentinel.

## Summary for parent

Decisions mapped: 5 (missing-doc/task detection, deadline→calendar/notification wiring, ROK_KRITICAN/
HEALTH_SCORE_PROMENJEN emission, proactive alert creation, deadline-criticality classification). New
duplicates found (not already fixed by a prior mission): **2 significant ones** — (1) 11 independent
`proactive_alerts` insert call sites with no canonical function, including a historical proof-of-risk
(a silent, months-long schema-mismatch bug) and an active reliability inconsistency (Phoenix's retry/audit
fix only covers 1 of 11 call sites); (2) the "critical deadline" day-threshold duplicated with 2 different
values across ≥6 files. Both are genuine "no single source of truth" violations per Program Alpha's own
Principle 2/4, not already addressed by any prior mission. **Single highest-priority canonicalization
target: extract `create_proactive_alert()` and migrate all 11 call sites onto it** — highest blast radius
(reliability + correctness), clearest single fix, mirrors an already-proven pattern
(`shared/audit_immutable.py::log_action`) rather than inventing a new one.
