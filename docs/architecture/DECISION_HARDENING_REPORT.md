# Decision Hardening Report — Program Gamma (Masterprompt 003), Phase 8-9

## Phase 8 — Future Failure Analysis

**Assumption**: 50 AI agents, 500-5,000 users, 20 new features, 100 new
workflows. **Question**: can anyone accidentally implement a new decision
outside the Decision Registry? **Answer, stated honestly: yes, today,
nothing structurally prevents it.**

### Why the honest answer is "yes"

This repository has no static-analysis CI gate, no pre-commit hook, and no
type-level enforcement mechanism that could detect "this new function
computes a business decision that duplicates an existing one." Claiming
otherwise would violate this mission's own explicit prohibition ("brojevi
bez metodologije") — a guardrail that isn't real is worse than no
guardrail, because it creates false confidence. This report states exactly
what protection exists, and exactly what doesn't, so a future mission
doesn't have to re-discover the gap.

### What DOES exist after this mission (real, verifiable protections)

1. **`DECISION_REGISTRY.md`** — for the first time, a single place that
   names every canonical decision function AND every known fragmented
   decision. Before this mission, the closest equivalent
   (`SOURCE_OF_TRUTH_REGISTRY.md`, Program Alpha) covered structural
   duplication, not decision authorship specifically — a narrower lens
   that missed all 12+ "next action" producers, since none of them are
   literal code duplicates of each other (each has its own prompt, own
   schema, own vocabulary).
2. **`tests/test_decision_registry_completeness.py`** — mechanically
   verifies every function the registry claims is canonical still exists,
   is importable, and is callable. This catches silent renames/deletions
   that would make the registry lie about the codebase. It does NOT catch
   a brand-new undeclared decision — that limitation is stated in the test
   file's own docstring, not hidden.
3. **The `DECISION_REGISTRY.md` registration rule itself** — a documented
   process convention (check the registry before writing new decision
   logic), the same shape as every other process rule this session has
   relied on (the founder's own "prove systemic first" addendum, Program
   Alpha's Pattern-A convention). Process rules in this codebase have a
   real track record of being followed (Program Alpha's own SMTP
   abandonment, Program Beta's PROGBETA-001 deferral) — but a process rule
   is not a technical control, and this report does not claim it is one.

### What does NOT exist, named honestly

- No CI pipeline was confirmed to exist in this repository during this
  mission (no `.github/workflows/` evidence encountered in any of this
  session's 10+ prior missions' file-system exploration). A "CI
  validacija" guardrail, as the masterprompt's Phase 8 literally requests,
  cannot be built without first confirming what CI infrastructure (if any)
  actually runs on this repo — recommending one without verifying is
  exactly the kind of unfounded claim this mission's own prohibitions
  forbid ("brojevi bez metodologije," "poredjenje sa nepotvrdjenim
  merenjem").
- No linter rule, no AST-based static check, no import-graph analyzer
  exists to catch "this new function's return shape matches an existing
  canonical decision's shape." Building one is a real, scoped, feasible
  future project (Python's `ast` module + a list of known decision-shaped
  return-value patterns) — but it is new infrastructure, and this
  mission's own prohibitions bar "dodavanje novih AI funkcionalnosti" and
  bar scope creep beyond what was diagnosed. Named as `GAMMA-007` (see
  `ARCHITECTURAL_DEBT_REGISTER.md`), not built.
- No runtime enforcement (e.g. a decorator that requires registration)
  exists — building one would touch every existing decision function
  (13 of them, cutting across 8 files) purely to add a guard, which is
  exactly the "refaktorisanje koje povećava složenost" this mission's own
  prohibitions bar when the reason is process enforcement, not a proven
  bug.

### Concrete failure scenario at scale, worked through honestly

At 5,000 users / 100 new workflows, the realistic failure mode is not "a
malicious bypass" — it's the same organic pattern that produced all 12+
"next action" producers already documented: a new PRO feature (like Court
Predictor or Case Commander were, in their time) gets built as an
independent product surface with its own GPT prompt, because the engineer
building it doesn't know `risk_engine.py::identify_case_problems` already
answers a related question, or doesn't realize their new "recommendation"
field is conceptually the same decision as Strategy Engine's
`strateski_stav`. **This is not a technical failure to prevent with a
smarter check — it is a discoverability failure.** `DECISION_REGISTRY.md`'s
real contribution is making the existing decisions discoverable in one
place for the first time; its real limitation is that discoverability only
helps an engineer who checks it.

## Phase 9 — the guardrail actually recommended

Given the above, the honest, proportionate recommendation is:

1. **Immediate (done this mission)**: the registry + completeness test.
2. **Next, cheap, real (not done this mission — scoped for a future pass,
   `GAMMA-007`)**: a lightweight `scripts/audit_decision_registry.py`
   (same style as the existing `scripts/audit_routers.py`) that greps new
   router/service files for GPT-call patterns producing enum/percentage/
   recommendation-shaped output and cross-references against
   `DECISION_REGISTRY.md`'s known decision names — a heuristic flag for a
   human reviewer, not a hard gate, matching this codebase's own
   `audit_routers.py` precedent (documented as having real false positives
   and blind spots, useful anyway).
3. **Not recommended without further founder scoping**: a hard CI/pre-
   commit gate, since no CI infrastructure was confirmed to exist, and
   building one is a decision beyond this mission's charter (introducing
   process infrastructure, not eliminating a decision-fragmentation class).

## Cross-reference to Olympus governance (Phase 10)

The Mission Olympus governance layer (built 2026-08-04, exercised live
twice already this session — Program Alpha's Phase 9, Program Beta's Phase
10) is itself the closest thing this platform has to Phase 8's requested
guardrail: Architecture Review and Decision Consistency Auditor-shaped
review of any future large change would, per this session's own track
record (4+ real findings caught in 2 prior live exercises), likely catch a
new decision-fragmentation instance before merge — but only for changes
large enough to trigger a full governance review, not for a single new
endpoint added without one. This is named as the most realistic present-day
guardrail, with its own honest limitation stated, not oversold.
