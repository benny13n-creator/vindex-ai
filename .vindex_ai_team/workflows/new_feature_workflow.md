# Workflow — New Feature

```
Idea
  │
  ▼
Product Strategist ──────────────► PRODUCT_SPECIFICATION.md
  │
  ▼
Solution Architect ──────────────► TECHNICAL_DESIGN.md
  │
  ├──► AI System Architect review (only if the design includes an AI component) ──► AI_DESIGN_REVIEW.md
  ├──► UX/UI Experience Architect review (only if user-facing) ──► UX_SPECIFICATION.md
  ├──► Database Architect review (only if schema/migration involved) ──► DATABASE_REVIEW.md
  │
  ▼
Security & Privacy Architect ────► SECURITY_REVIEW.md          [VETO]
  │
  ▼
Red Team / Devil's Advocate ─────► RED_TEAM_REPORT.md          [VETO]
  │
  ▼
AI CTO / Chief Architect ────────► ARCHITECTURE_DECISION.md    (required only if architecturally
  │                                                              significant — see note below)
  ▼
Backend Engineering ─────────────► IMPLEMENTATION_PLAN.md, then diff
Frontend Engineering ─────────────► diff (if UX_SPECIFICATION.md exists)
  │
  ▼
QA Engineering ───────────────────► QA_REPORT.md                [BLOCKS release]
  │
  ▼
Release Governance ───────────────► RELEASE_APPROVAL.md          [FINAL GATE]
  │
  ▼
Founder (deploy / push, per this project's existing auto-push convention)
```

## Gate logic, stated precisely

- **Security and Red Team both run regardless of feature size.** A tiny feature gets a tiny review
  (a paragraph, not a 10-page report) — but it does not skip the gate. The forensic audit's own
  finding pattern (a correct control applied narrowly and inconsistently) is exactly what happens
  when "this is too small to need review" becomes the default judgment call.
- **A CRITICAL or HIGH finding from either Security or Red Team stops the workflow.** It does not
  proceed to Implementation until resolved, or the founder explicitly, individually accepts the
  residual risk in writing (filed as its own decision record, not a verbal aside).
- **The AI CTO's `ARCHITECTURE_DECISION.md` step is conditional, not universal.** It fires when the
  Solution Architect's design changes something `VINDEX_CORE_CONSOLIDATION.md` already consolidated,
  introduces a new cross-cutting pattern, or touches one of the systems named in the Architecture
  Bible as foundational (Case Genome, the Legal Reasoning Engine, the in-progress AI Governance
  Layer, the entitlement system). A copy change or a bugfix does not need this step — the Solution
  Architect's own design doc states explicitly whether it believes this step is required, and the
  AI CTO can also self-invoke if it disagrees with that call.
- **QA blocks release, not implementation.** A feature can be implemented and iterated on before
  QA's full pass; it cannot reach Release Governance without one.
- **No role approves its own output.** Every arrow above crosses to a different role.

## Worked precedent already in this repository

This exact shape, informally, is what actually happened for the Trust Architecture Blueprint and
Program 1 (AI Governance Layer): idea (founder) → specification (multiple revisions, each
incorporating founder-as-Product-Strategist feedback) → architecture design (Solution/AI System
Architect work, across 8 revisions) → security review (folded into the design process itself, since
the whole document *is* a security architecture) → red team (an independent fresh-agent pass, twice
— once full-scope, once falsification-only) → and it is currently sitting at Stage 4 of the Finding
Lifecycle, one targeted re-check away from Stage 5, deliberately not yet at Implementation. See
`docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md`'s full revision history for the
complete, real trace of this workflow already having run once, before this document existed to name
it.
