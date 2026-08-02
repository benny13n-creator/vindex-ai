# Workflow — Bugfix / Hotfix

For a confirmed defect in already-shipped behavior — not a new feature, not an architecture change.

```
Confirmed defect (reproducible, evidenced — file:line, not "seems broken")
  │
  ▼
Is this security-relevant (a vulnerability, an access-control gap, a data-exposure risk)?
  │
  ├── YES ──► follow docs/security/FINDING_LIFECYCLE.md directly:
  │           Observation → Finding (evidence + SEC-ID) → Confirmed Risk (impact analysis)
  │           → Remediation Candidate (fix design + rollback plan) → BOTH Peer Review
  │           (Red Team, fresh agent) AND Production Reality Gate must pass →
  │           Implementation → Verified Fix → Production Verified → Closed.
  │           This is not optional process for security bugs — it is this project's
  │           own existing, proven methodology (SEC-031 is the reference example of
  │           a finding that completed all 9 stages).
  │
  └── NO ───► Backend/Frontend Engineering fixes directly, with:
              - A regression test proving the specific bug is fixed (QA Engineering)
              - A check for sibling instances of the same bug class elsewhere in the
                codebase (this project's own repeated practice — e.g. SEC-001's fix
                included "a full sweep of all 24 {predmet_id}-scoped mutation
                endpoints," not just the two originally-broken ones)
              - Release Governance's normal gate, abbreviated in writing but not skipped
```

## The one rule that applies to every hotfix, no exceptions

**Never fix only the reported instance without checking for sibling instances of the same root
cause.** This project's own history is the evidence for why: SEC-001's fix swept all 24 similarly-
shaped endpoints, not just the 2 originally reported; SEC-034's fix ran a full 154-table live
diagnostic, not a single-table patch; the forensic audit's "narrow, inconsistent application of an
already-correct pattern" diagnosis is exactly the failure mode a sibling-instance check exists to
close. A hotfix that doesn't ask "where else does this exact pattern appear" is not actually done,
even if the reported symptom is gone.

## Hotfix urgency does not waive the veto roles for security-relevant fixes

A live, actively-exploited vulnerability may compress the *timeline* (same-day fix, same-day
founder-executed remediation, matching SEC-031's actual production-execution precedent) — it does
not compress the *process*. Peer review still happens; it happens fast, not never.
