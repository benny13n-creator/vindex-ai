# Current State — Vindex AI Engineering Organization

**Last updated:** 2026-08-02. Update this file at the end of any workflow that changes the state
below — it is meant to stay current, not become a historical log (that's `project_memory.md`'s job).

## Governing documents, in hierarchy order
1. `docs/architecture/VINDEX_TRUST_ARCHITECTURE_BLUEPRINT.md` — the constitution (adopted 2026-08-01)
2. `docs/architecture/VINDEX_TRUST_ARCHITECTURE_TRACEABILITY.md` — maps existing docs to the
   Blueprint's 10 capabilities, defines 5 Programs (P1-P5) and their dependency order
3. `docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md` — Program 1 (AI Governance
   Layer), currently **Stage 4 (Remediation Candidate)** per the Finding Lifecycle, 8 revisions deep
4. `docs/security/SECURITY_MATURITY_DASHBOARD.md` — SSOT for security maturity
5. `docs/security/SECURITY_GAP_REGISTER.md` — SEC-001 through SEC-073 as of 2026-08-02
6. `docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md` — full-codebase implementation audit,
   score 52/100, 37 new findings

## What is currently open, in priority order

1. **SEC-037** (Critical) — live OpenAI key in git history. **Action required independent of
   everything else: rotate now.**
2. **SEC-038** (Critical, pending live confirmation) — `profiles` RLS policy has no column
   restriction; frontend writes to it directly. **Action required: 30-second live test, then fix.**
3. **Program 1**, Stage 4 → 5: needs one more *targeted* falsification re-check (scoped only to
   Revision 8's 4 fixes: chokepoint per-surface coverage, Durable Audit ACK, `decide_response`'s
   corrected formula, RiskScoring/AnomalyDetection contract) — not a new full audit. Then founder
   re-sign-off. Then Stage 5, then Programs P3→P2→P1→P4 implementation order (P5 parallel) per the
   Traceability doc.
4. **Forensic audit Phase 1 items** (see the audit doc's own 3-phase prioritization) — not yet
   started as of this writing; this is genuinely new work, not a continuation of Program 1.

## What NOT to reopen without a new, specific reason
- Program 1's Revisions 1-6 settled questions (Escalation-Only Invariant, Untrusted Provider
  Principle's option (a) choice, the Realtime API's session-level governance model) — re-litigating
  these from scratch each session is exactly the "Revision 7, 8, 9…" paralysis the founder
  explicitly rejected.
- The Blueprint's own Part I principles — these are the constitution, not a per-feature negotiation.

## Active organizational structure
This file's existence, and the rest of `.vindex_ai_team/`, was created 2026-08-02 in response to an
explicit founder directive to build a permanent internal AI engineering organization. It has not
yet been exercised on a real feature end-to-end — the first real workflow run through this
structure should be treated as a validation of the structure itself, and this file (plus
`rejected_ideas.md`/`known_risks.md`) should be updated with whatever friction that run surfaces.
