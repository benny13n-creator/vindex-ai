# Workflow — Architecture Change

For changes to an existing architectural pattern itself (not a new feature built within the
existing pattern) — e.g., changing how ownership checks work, changing the audit-log schema,
changing the chokepoint mechanism, consolidating two overlapping systems.

```
Observation (a pattern is inconsistent, duplicated, or no longer fits — per
docs/security/FINDING_LIFECYCLE.md's Stage 1)
  │
  ▼
AI CTO / Chief Architect ─────► names the problem explicitly, decides if this
  │                              warrants a formal initiative (per
  │                              docs/security/DATA_INTEGRITY_INITIATIVE.md's
  │                              own precedent — naming an epic without
  │                              solving it immediately is a legitimate output)
  ▼
Solution Architect ───────────► TECHNICAL_DESIGN.md, with an explicit
  │                              "alternatives considered and rejected" section —
  │                              this is non-negotiable for architecture changes,
  │                              per Program 1's own §1.1 (the chokepoint options
  │                              table) and §1.4 (rejecting the event-loop bridge)
  ▼
Security & Privacy Architect ─► SECURITY_REVIEW.md                    [VETO]
AI System Architect (if AI-related) ─► AI_DESIGN_REVIEW.md
Database Architect (if schema-related) ─► DATABASE_REVIEW.md          [VETO on destructive changes]
  │
  ▼
Red Team / Devil's Advocate ──► RED_TEAM_REPORT.md                    [VETO]
  │  (fresh, non-fork agent — mandatory for architecture changes, not optional)
  ▼
AI CTO / Chief Architect ─────► ARCHITECTURE_DECISION.md, final
  │                              recommendation
  ▼
Founder sign-off ─────────────► required, always, for architecture changes —
                                 no exception smaller than this exists in this
                                 workflow (mirrors Program 1's own Stage 5 gate:
                                 independent peer review AND founder sign-off,
                                 neither substituting for the other)
  │
  ▼
Implementation proceeds only after founder sign-off is recorded
```

## Why architecture changes get their own workflow, not just the New Feature one

A new feature can be wrong in a way that's cheap to fix (revert the feature). An architecture
change, once other code depends on it, is expensive to unwind — this is the same reasoning this
project already applies to migrations (`docs/security/SEC031_MIGRATION_SAFETY_PLAN.md`'s whole
premise) extended to non-database architecture. The extra step here, versus the New Feature
workflow, is that **founder sign-off is mandatory and explicit for every architecture change**, not
conditional on the AI CTO's judgment of significance — because by definition, if this workflow was
invoked at all, the AI CTO already judged it significant enough to be an architecture change, not a
feature.

## Revision discipline

An architecture change under active adversarial review should follow Program 1's own demonstrated
pattern: each red-team-driven revision states what changed and why, preserves the reasoning for
rejected alternatives (so a later reviewer doesn't re-propose something already tried and rejected
for a stated reason), and does not reopen findings the current red-team pass wasn't asked to
re-examine — a full re-audit at every revision is how "Revision 7, 8, 9…" analysis paralysis
happens, and this project's own founder has explicitly named that failure mode and rejected it.
