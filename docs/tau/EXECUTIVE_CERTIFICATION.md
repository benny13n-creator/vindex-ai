# Executive Certification — Program Tau, Master Sprint 008, Phases 4-6

Certifies (a) whether Workspace, Commander, CIO, Morning Briefing, Court Predictor, and Hearing CC can give
contradictory information for the same case, (b) whether GPT still changes readiness/priority/risk/action/
facts anywhere in the executive layer, and (c) portfolio-scale stress behavior.

## Phase 4 — Executive Consistency

### The dependency graph, with CIO now included

```
shared/case_context.py::build_case_context()
  = THE single point that calls risk_engine + gap_engine + case_readiness together.

  ├─> routers/court_predictor.py   (Tau 005)
  ├─> routers/hearing_cc.py         (Tau 006)
  ├─> routers/case_intelligence.py  (Tau 002)
  ├─> routers/morning_briefing.py   (Tau 002)
  ├─> routers/case_commander.py     (Tau 007)
  └─> routers/cio.py                (Tau 008, THIS sprint)

routers/workspace.py (GET /api/workspace)
  reads case_actions DIRECTLY (no GPT call at all) — the SAME table build_case_context()'s own
  `active_actions` field is sourced from, so it cannot disagree with the other 6 about what's open.
```

All 6 GPT-calling executive surfaces now read `build_case_context()` for the SAME case's readiness/gaps/
actions — they cannot structurally disagree about what's canonically true for that case, only about how
they each narrate it (which is exactly the GPT-synthesis layer Phase 5 permits). `workspace.py` reads the
same underlying `case_actions` table directly. **Direct proof, not just architectural inference**: a test
feeds ONE mocked `build_case_context()` result (`CRITICAL_GAP`) through CIO's own membership test, Court
Predictor's own cap dict, Hearing CC's own cap dict, and Case Commander's own label/rank — all 4 agree.
A second test goes further: the SAME mocked context is fed into `cio.py`'s own portfolio loop AND
`case_commander.py`'s own `_kanonski_nalazi` in the same test, and both report the identical `BLOCKED`
status for the identical case (`tests/test_tau008_cio_consolidation.py::test_cio_and_case_commander_agree_on_same_case_readiness`).

### What's confirmed NOT unified, correctly

`cio.py`'s own `strategija_cilj`/`zakljucak` (raw Genome fields, no canonical equivalent, named Step-5
exception), `case_commander.py`'s own `protivnikova_strategija`/`sudska_praksa`, `court_predictor.py`'s own
`opponent_intel` cross-portfolio search — each a genuinely different-shaped signal, the same "keep bespoke,
name why" precedent established across every prior Tau sprint. Not unifying these is correct, not an
oversight.

### Named, out of this sprint's own scope: `health_index.py`

`docs/tau/EXECUTIVE_INTELLIGENCE_MAP.md`'s own Phase 1 finding — a fully independent Firm Health Score and
GPT-decided "Chief Partner" recommendation, disconnected from every canonical source — is NOT part of this
consistency guarantee. It is not migrated this sprint (mission named `cio.py` specifically), so it CAN
still disagree with the other 6 surfaces about a case's own risk level. Named explicitly in
`docs/tau/TAU_FINAL_HANDOVER.md`, not silently left as an unstated exception to this certification.

## Phase 5 — GPT Boundary

Checked whether GPT changes readiness, priority, risk, action, or facts anywhere in the executive layer
this sprint touched.

### `cio.py` (migrated this sprint) — proven adversarially, not asserted

3 adversarial tests directly attack the boundary: a poisoned response references a nonexistent
`predmet_id` (nulled, not shown); a poisoned response claims `kriticnost: 94` for a case whose own
canonical readiness is `READY` (capped to 40); a poisoned response invents a `kriticni_rok` with no
matching real deadline (nulled). A positive control confirms a REAL, canonically-backed `kriticni_rok`
survives the same check unchanged — the mechanism narrows false claims without suppressing true ones.

GPT's own remaining latitude in `cio.py` — narrative wording for `cio_preporuka`/`cio_zakljucak`, and
WHICH case to name for `najveca_prilika`/`suboptimalna_strategija`/`slicni_predmet` (no canonical
equivalent exists to check these against) — is synthesis over now-grounded facts, in-bounds per Phase 5's
own explicit allowance ("GPT sme objasniti/sintetizovati/sumirati/obrazložiti").

### Court Predictor / Hearing CC / Case Commander (prior sprints) — reconfirmed still holding

No code in this sprint touched their own GPT-boundary mechanisms; the existing test suites for all 3
re-ran clean (see Phase 9). Re-verified via the same cross-system test noted in Phase 4.

### `health_index.py` — the one still-open, unaddressed violation, named not fixed

`_compute_chief_partner` asks GPT to independently generate portfolio-wide recommended actions with zero
grounding in `case_actions`/canonical readiness — a `TAU-017`-shaped violation in a different file. Not
fixed this sprint (out of the mission's own named scope, and per this whole program's "one file at a time"
discipline). Formalized as a new debt item in `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`, prioritized
in `docs/tau/TAU_FINAL_HANDOVER.md`.

## Phase 6 — Portfolio stress

`cio.py`'s own portfolio loop is bounded by its own pre-existing `.limit(40)` on the `predmeti` fetch — the
migration does not change this cap, so the 1000-case/50,000-document/20-year-history stress scenario the
mission's own Phase 6 names is bounded by construction to at most 40 `build_case_context()` calls per
report, regardless of true portfolio size. The underlying scale guarantees (1000+ documents per case, 300+
deadlines, 50+ contradictions) are already proven at the `build_case_context()` layer itself (Tau 002/004) —
re-running them here would test the canonical function a 2nd time, not this sprint's own actual change, the
same non-redundancy discipline Tau 006/007 already established. What IS new and IS tested here: 2 cases
with DELIBERATELY DISAGREEING Genome-heuristic-vs-canonical-readiness values (proving `kriticnih_rizika`'s
own redefinition holds under a real divergence, not just a trivial case) and 2 different users' concurrent
reports not cross-contaminating (`test_concurrent_reports_for_different_users_do_not_cross_contaminate`).
Multiple courts/multiple firms/multiple users are structurally already isolated by `uid`-scoped queries,
unchanged by this migration — not re-proven redundantly.

## Verdict

Cross-system consistency holds by construction for all 6 executive surfaces named in the mission's own
Phase 4 (CIO now included, proven directly not just architecturally). The GPT boundary holds for `cio.py`
post-migration, adversarially proven with both a negative proof (false claims suppressed) and a positive
control (true claims preserved). One genuine, pre-existing, still-open violation (`health_index.py`) is
named precisely as staying outside this certification's own guarantee, not silently glossed over.
