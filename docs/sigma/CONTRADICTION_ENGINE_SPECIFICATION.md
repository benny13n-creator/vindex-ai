# Contradiction Engine Specification — Program Sigma, Master Sprint 002 (2026-08-06)

Phase 5 deliverable: if a new document disputes an old one, the old fact must never be deleted; a change
must be registered as ACTIVE/SUPERSEDED/CONTRADICTED/UNKNOWN, and every change must be auditable.

## What already satisfies this, structurally, before any new code

- **"Nikada ne brisati staru činjenicu" (never delete an old fact)**: satisfied by construction.
  `predmet_genome_history` (`routers/case_dna.py:461-476`) persists the FULL prior Genome object — including
  its own `kontradikcije` list — before every overwrite, confirmed append-only (no UPDATE/DELETE against
  this table anywhere in the repo). The complete history of every contradiction Genome has ever reported for
  a case is already preserved, permanently, with a `verzija` number and `trigger_event`. This was not
  previously understood clearly as satisfying this requirement (Sprint 001's own `SIGMA-002` framed the gap
  narrowly as "diff precision," not "history preservation") — this sprint's own forensic audit confirms the
  history itself was never actually at risk.
- **"Svaka promena mora biti auditabilna" (every change must be auditable)**: `_consequence_refresh_case_actions`
  writes a `case_action_refreshed` audit entry via `shared/audit_immutable.py::log_action` on every Case
  Evolution refresh, including counts of created/updated/closed `RAZRESITI_KONTRADIKCIJU` actions
  (`services/case_evolution.py:771-780`) — already wired, already tested.

## A real, previously-unknown bug found and fixed this sprint

`services/case_evolution.py`'s own Rule 3 (`RAZRESITI_KONTRADIKCIJU`, the existing canonical
"this contradiction needs resolution" action) and `routers/case_dna.py::_compute_delta`'s own churn
detection BOTH derived identity from a Genome-extracted contradiction's free-text `opis` field — GPT prose,
re-extracted fresh on every refresh, not a diff of the model's own prior output. Any rephrasing of the
IDENTICAL underlying contradiction between 2 refreshes:
- made `_compute_delta` report a false "1 eliminated + 1 new" churn (`SIGMA-002`, Sprint 001), and
- made Rule 3's own reconcile loop see the old `dedupe_key` as gone (closes the action) and the new
  `dedupe_key` as new (creates a fresh one) — **a live functional bug, confirmed this sprint by direct code
  reading**: an open `RAZRESITI_KONTRADIKCIJU` action would flicker closed+reopened across every Genome
  refresh even when nothing about the underlying contradiction actually changed.

**Fixed**: `shared/contradiction_identity.py` (new) — ONE shared identity function, anchored on
`(lokacija_1, lokacija_2)` (the formulaic "DOK-XX str.Y" document/page citations Genome's own extraction
prompt already requires for every contradiction), order-independent, falling back to `opis` only when
neither location is present. Used by BOTH consumers — `routers/case_dna.py::_compute_delta` and
`services/case_evolution.py`'s own Rule 3 — one identity, not two independent patches, per this sprint's
own founding principle. Does not touch the GPT extraction prompt/contract — only how the already-extracted
fields are used for downstream identity matching. **11 new tests**
(`tests/test_sigma_sprint002_contradiction_identity.py`) prove: reworded-but-identical contradictions
produce the same identity/dedupe_key (the actual bug, reproduced and proven fixed); order-independence;
genuinely different contradictions still produce different identities (no over-suppression); `_compute_delta`
no longer reports false churn on rewording, while still correctly detecting real eliminations/additions.

## The ACTIVE/SUPERSEDED/CONTRADICTED/UNKNOWN status model — designed, not fully implemented

The mission asks for an explicit status registered on every contradiction-relevant fact. Today,
`case_actions.status` for a `RAZRESITI_KONTRADIKCIJU` action is binary (`open`/`closed`) — when Genome's
latest `kontradikcije` list no longer contains a contradiction that previously had an open action, the
reconcile loop closes it, but nothing distinguishes WHY: a lawyer resolved it, a new document superseded the
disputed fact, or Genome simply failed to re-detect it this refresh (a false negative, not a real
resolution). The mission's own 4-state vocabulary maps naturally onto this:

| State | Meaning | Where it would live |
|---|---|---|
| ACTIVE | Contradiction currently present in Genome's latest extraction, action open | `case_actions.status='open'`, tip=`RAZRESITI_KONTRADIKCIJU` — already exists |
| CONTRADICTED | Same as ACTIVE — this sprint treats "contradicted" and "active dispute" as the same state (the mission's own vocabulary lists both; the current architecture has one open state, not two) | Same row |
| SUPERSEDED | The disputed fact was resolved because a NEWER document corrected/clarified the record (not merely "no longer detected") | **Not currently distinguishable from a false negative — see gap below** |
| UNKNOWN | Genome stopped reporting a previously-flagged contradiction with no clear resolution evidence | **Not currently distinguishable from SUPERSEDED — same gap** |

**Why the SUPERSEDED/UNKNOWN split was not implemented this sprint**: distinguishing them requires knowing
WHY a contradiction disappeared from Genome's latest extraction — which needs either (a) Genome's own
extraction prompt to explicitly reason about and report resolution status per contradiction (a live
GPT-prompt/contract change, the same category of risk `SIGMA-002` was originally deferred for), or (b) a
new deterministic cross-check (e.g., comparing which specific document caused the contradiction to
disappear) that does not currently exist anywhere and would be new algorithmic surface area. Both are real
future work, not a same-sprint mechanical fix. Recorded as `SIGMA-010`.

## What this sprint delivers for Phase 5, honestly scoped

1. **A real, previously-flickering bug fixed** — the closest thing to "silently prikriva/briše" (silently
   hides/erases) a contradiction's own identity that existed in the codebase, closed with tests.
2. **Confirmation that "never delete" was already true** — `predmet_genome_history`'s own append-only
   design, not previously credited clearly for satisfying this requirement.
3. **A precise, actionable design** for the full 4-state model (this document), with the exact reason the
   SUPERSEDED/UNKNOWN split needs either a prompt change or new cross-check logic — not implemented blind.
