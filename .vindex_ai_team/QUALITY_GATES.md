# Quality Gates — Mission Olympus Extension

**What this adds to `REVIEW_GATES.md`**: that file's table covers the pre-existing 15-role organization's
6 gate-holding roles. This file adds the fixed state vocabulary for the 19 new Mission Olympus roles (plus
the 2 reused roles, listed for completeness), so `GOVERNANCE_FINAL_RECOMMENDATION.md` can be verified
mechanically against this table, the same discipline `REVIEW_GATES.md` already established. **All 4 rules
at the bottom of `REVIEW_GATES.md` apply unchanged to every row below** — this file only adds rows, it
does not add new rules.

| Agent | States | Blocking states | Where defined |
|---|---|---|---|
| Enterprise AI Director (16) | (no fixed enum — aggregates others' states into `RECOMMEND MERGE` / `DO NOT RECOMMEND MERGE`) | `DO NOT RECOMMEND MERGE` (if any invoked board reports a blocking state) | `agents/16_enterprise_ai_director.md`, `REVIEW_PIPELINE.md` Phase G4 |
| Architecture Review Agent (17) | `APPROVED`, `APPROVED WITH CONDITIONS`, `BLOCKED` | `BLOCKED` (architectural regression, new duplicate source-of-truth) | `agents/17_architecture_review_agent.md` |
| Backend Engineering Review Agent (18) | `APPROVED`, `APPROVED WITH CONDITIONS`, `BLOCKED` | `BLOCKED` (correctness defect: race condition, transaction gap, false success) | `agents/18_backend_engineering_review_agent.md` |
| Frontend Engineering Review Agent (19) | `APPROVED`, `APPROVED WITH CONDITIONS`, `BLOCKED` | `BLOCKED` (false-success message, silent data loss visible to user) | `agents/19_frontend_engineering_review_agent.md` |
| Security Review Agent (05, reused) | `APPROVED`, `CONDITIONAL`, `BLOCKED` | `BLOCKED`; `CONDITIONAL` blocks final recommendation until its condition is met | `agents/05_security_privacy_architect.md` (unchanged) |
| Reliability & Chaos Agent (20) | `PROTECTED`, `PARTIAL`, `VULNERABLE` | `VULNERABLE` (matches the vocabulary Keystone Phase 4 already used — deliberate reuse, not a new convention) | `agents/20_reliability_chaos_agent.md` |
| AI Quality Auditor (21) | `CONSISTENT`, `DEGRADED`, `BLOCKED` | `BLOCKED` (contradiction between two AI outputs about the same case) | `agents/21_ai_quality_auditor.md` |
| AI Explainability Agent (22) | `EXPLAINABLE`, `PARTIALLY EXPLAINABLE`, `BLOCKED` | `BLOCKED` (a high-stakes conclusion with no traceable reasoning at all) | `agents/22_ai_explainability_agent.md` |
| AI Grounding Agent (23) | `GROUNDED`, `PARTIALLY GROUNDED`, `BLOCKED` | `BLOCKED` (a fabricated number or an unearned confidence score on a high-stakes output — the exact Keystone K-3 shape) | `agents/23_ai_grounding_agent.md` |
| AI Evaluation & Benchmark Agent (24) | `PASS`, `REGRESSION`, `BLOCKED` | `BLOCKED` (a measured regression against the LEC v1 benchmark corpus) | `agents/24_ai_evaluation_benchmark_agent.md` |
| Legal Domain Expert (25) | `APPROVED`, `APPROVED WITH CONDITIONS`, `BLOCKED` | `BLOCKED` (substantive legal/terminology error) | `agents/25_legal_domain_expert.md` |
| Evidence Integrity Agent (26) | `TRACEABLE`, `PARTIALLY TRACEABLE`, `BLOCKED` | `BLOCKED` (a load-bearing factual claim with no traceable source) | `agents/26_evidence_integrity_agent.md` |
| Regulatory Compliance Verification Agent (27) | `COMPLIANT`, `CONDITIONAL`, `BLOCKED` | `BLOCKED`, same weight as Security's `BLOCKED` — deliberately identical vocabulary since it routes through the same veto path | `agents/27_regulatory_compliance_verification_agent.md` |
| Product Consistency Agent (28) | `CONSISTENT`, `GAPS FOUND`, `BLOCKED` | `BLOCKED` (only for a severe, user-trust-damaging expectation gap — most `GAPS FOUND` are non-blocking, logged to `MISSION_BOARD.md`) | `agents/28_product_consistency_agent.md` |
| Beta Experience Agent (29) | (no fixed enum — narrative UX report only, feeds Product Consistency (28) and Frontend Review (19)) | N/A — no independent veto | `agents/29_beta_experience_agent.md` |
| Workflow Integrity Agent (30) | `CONNECTED`, `PARTIAL`, `BROKEN` | `BROKEN` (a claimed end-to-end flow that does not actually connect) | `agents/30_workflow_integrity_agent.md` |
| Metrics Guardian (31) | `SOUND`, `METHODOLOGICALLY QUESTIONABLE`, `BLOCKED` | `BLOCKED` (a metric about to be published/reported with an unsound or inconsistent-with-prior-runs denominator — the exact Keystone ICS/CIC shape) | `agents/31_metrics_guardian.md` |
| Performance & Scalability Agent (32) | `ACCEPTABLE`, `DEGRADED`, `BLOCKED` | `BLOCKED` (a regression severe enough to affect production usability) | `agents/32_performance_scalability_agent.md` |
| Observability Agent (33) | `OBSERVABLE`, `PARTIALLY OBSERVABLE`, `BLOCKED` | `BLOCKED` (a change that would produce a genuinely silent failure — no log, no audit, no correlation) | `agents/33_observability_agent.md` |
| Technical Debt Curator (34) | (no fixed enum — classifies/prioritizes `MISSION_BOARD.md` entries, advisory) | N/A — no independent veto | `agents/34_technical_debt_curator.md` |
| Compliance / Enterprise Readiness (14, reused) | (no fixed enum — advisory only, unchanged) | N/A | `agents/14_compliance_enterprise_readiness.md` (unchanged) |

## Rules (inherited from `REVIEW_GATES.md`, restated for this extended table)

1. A `CONDITIONAL`/`APPROVED WITH CONDITIONS`/`PARTIAL` state is not a pass — it is contingent on a named,
   checkable condition, verified before the final recommendation, not assumed satisfied.
2. A blocking state from **any** row above halts the pipeline at Phase G1/G2 (`REVIEW_PIPELINE.md`) — it
   does not wait for Phase G4 to notice.
3. Only the founder can convert a blocking state into a proceed decision, in writing
   (`DECISION_ESCALATION_POLICY.md`).
4. A missing report for any board the Director selected in Phase G0 is treated as that board's blocking
   state — identical to `REVIEW_GATES.md` rule 4, extended here.
