# Agent Catalog — All 34 Roles

Single source of truth for every role across both organizations: the pre-existing 15-role
feature-development organization (`ORG_CHART.md`, built 2026-08-02) and the 19 new Mission Olympus
review-board roles (built 2026-08-04). See `AI_GOVERNANCE_ARCHITECTURE.md` for the design rationale and
layer structure; this file is the flat, complete reference table.

## Part A — Pre-existing Feature-Development Organization (unchanged, Agents 01–15)

| # | Role | Charter | Authority | Vetoes? |
|---|---|---|---|---|
| 1 | AI CTO / Chief Architect | `agents/01_ai_cto_chief_architect.md` | Approves/rejects architecture; coordinates the rest | Yes — architecture |
| 2 | Product Strategist | `agents/02_product_strategist.md` | Defines the problem/user value; sets priority | No |
| 3 | Solution Architect | `agents/03_solution_architect.md` | Designs the technical shape once product is approved | No |
| 4 | Red Team / Devil's Advocate | `agents/04_red_team_devils_advocate.md` | Attacks the proposal | **Yes — absolute** |
| 5 | Security & Privacy Architect | `agents/05_security_privacy_architect.md` | Assesses security/privacy impact | **Yes — absolute** |
| 6 | AI System Architect | `agents/06_ai_system_architect.md` | Owns all LLM/RAG/agent architecture decisions | Yes — AI-specific |
| 7 | UX/UI Experience Architect | `agents/07_ux_ui_experience_architect.md` | Designs the lawyer-facing workflow | No |
| 8 | Database Architect | `agents/08_database_architect.md` | Reviews schema/migration safety | Yes — destructive migrations |
| 9 | Backend Engineering | `agents/09_backend_engineering.md` | Implements the approved design | No |
| 10 | Frontend Engineering | `agents/10_frontend_engineering.md` | Implements the approved UX spec | No |
| 11 | QA Engineering | `agents/11_qa_engineering.md` | Verifies it actually works, including failure paths | Yes — release-blocking |
| 12 | Release Governance | `agents/12_release_governance.md` | Final gate before anything ships | **Yes — absolute, final** |
| 13 | Standup Reporter | `agents/13_standup_reporter.md` | Reports status; produces nothing new | No |
| 14 | Compliance / Enterprise Readiness | `agents/14_compliance_enterprise_readiness.md` | Commercial/procurement/operational readiness per customer segment | No — advisory only |
| 15 | Security Verification Engineer | `agents/15_security_verification_engineer.md` | Verifies a declared control has an actual Runtime Witness | No independent veto — routes through 05/Red Team |

**When this organization is used**: a new feature request, an architecture change, a bugfix — anything
starting from Phase 0 of `OPERATING_PROTOCOL.md`, before implementation exists.

## Part B — Mission Olympus Enterprise AI Governance Board (NEW, Agents 16–34)

**When this organization is used**: reviewing a *completed* change (a diff, a mission's output, a
migration) before it merges — see `AI_GOVERNANCE_ARCHITECTURE.md`'s routing table for which boards a
given change requires.

| # | Layer | Role | Charter | Authority | Vetoes? | Reuses/extends |
|---|---|---|---|---|---|---|
| 16 | 1 — Executive Orchestrator | Enterprise AI Director | `agents/16_enterprise_ai_director.md` | Routes to boards, aggregates reports, issues final merge recommendation | No independent veto — aggregates others' vetoes | Distinct from Agent 01 (feature-pipeline CTO) |
| 17 | 2 — Engineering Board | Architecture Review Agent | `agents/17_architecture_review_agent.md` | Reviews completed-change architecture, duplicates, tech debt | Yes — architectural regression | Complements Agent 01 (pre-implementation) |
| 18 | 2 — Engineering Board | Backend Engineering Review Agent | `agents/18_backend_engineering_review_agent.md` | Reviews API/DB/event/transaction/concurrency correctness | Yes — correctness defect | Never reviews Agent 09's own work |
| 19 | 2 — Engineering Board | Frontend Engineering Review Agent | `agents/19_frontend_engineering_review_agent.md` | Reviews UI code, state, UX consistency, false-success messages | Yes — false-success/data-loss defect | Never reviews Agent 10's own work |
| 05 | 2 — Engineering Board | Security Review Agent | *(reused)* `agents/05_security_privacy_architect.md` | RLS, auth, authz, OWASP, secrets, encryption, audit immutability | **Yes — absolute** | No new agent — existing charter is already this exact scope |
| 20 | 2 — Engineering Board | Reliability & Chaos Agent | `agents/20_reliability_chaos_agent.md` | Retry, rollback, recovery, idempotency, race conditions, dead-letter, chaos injection | Yes — unrecoverable failure mode | Formalizes Sentinel/Phoenix/Keystone's ad hoc chaos-fork pattern |
| 21 | 3 — AI Excellence Board | AI Quality Auditor | `agents/21_ai_quality_auditor.md` | Response-level consistency, cross-version stability, contradictions | Yes — quality regression | Distinct from Agent 06 (architecture-level) |
| 22 | 3 — AI Excellence Board | AI Explainability Agent | `agents/22_ai_explainability_agent.md` | Can the AI explain its conclusion — sources, citations, limitations | Yes — unexplainable high-stakes output | Distinct from Grounding (23) |
| 23 | 3 — AI Excellence Board | AI Grounding Agent | `agents/23_ai_grounding_agent.md` | Every conclusion evidence-based; no fabricated numbers/confidence | Yes — ungrounded high-stakes output | Distinct from Explainability (22) |
| 24 | 3 — AI Excellence Board | AI Evaluation & Benchmark Agent | `agents/24_ai_evaluation_benchmark_agent.md` | Standardized benchmark measurement, precision, regression, model comparison | Yes — quality regression vs. benchmark | **Uses existing LEC v1 corpus — no new benchmark set** |
| 25 | 4 — Legal Intelligence Board | Legal Domain Expert | `agents/25_legal_domain_expert.md` | Legal logic, terminology, lawyer workflow fit, usability | Yes — substantive legal error | Fulfills `README.md`'s 2026-08-02 proposed-but-unbuilt role |
| 26 | 4 — Legal Intelligence Board | Evidence Integrity Agent | `agents/26_evidence_integrity_agent.md` | Every claim traceable to document/page/paragraph | Yes — untraceable factual claim | Narrower/more mechanical than Grounding (23) |
| 27 | 4 — Legal Intelligence Board | Regulatory Compliance Verification Agent | `agents/27_regulatory_compliance_verification_agent.md` | GDPR/AI Act/retention/audit obligation code-level verification | **Yes — routes through Security veto path for Critical findings** | Narrower sibling of Agent 14 (advisory-only) |
| 28 | 5 — Product Board | Product Consistency Agent | `agents/28_product_consistency_agent.md` | Expectation-gap: what should happen automatically but doesn't | Yes — broken automatic workflow | Distinct from Workflow Integrity (30) |
| 29 | 5 — Product Board | Beta Experience Agent | `agents/29_beta_experience_agent.md` | Black-box lawyer simulation, no code reading, UX report only | No independent veto — feeds Product/UX findings | Formalizes Sentinel/Keystone Phase-7 pattern |
| 30 | 5 — Product Board | Workflow Integrity Agent | `agents/30_workflow_integrity_agent.md` | End-to-end named process trace, module-to-module connectivity gaps | Yes — broken connectivity in a claimed end-to-end flow | Distinct from Product Consistency (28) |
| 31 | 6 — Platform Intelligence Board | Metrics Guardian | `agents/31_metrics_guardian.md` | Validates ICS/CIC/Reliability/Audit/Provenance/Replay/Recovery methodology | Yes — methodologically unsound metric claim | Directly descended from this mission's own ICS/CIC correction |
| 32 | 6 — Platform Intelligence Board | Performance & Scalability Agent | `agents/32_performance_scalability_agent.md` | Latency, throughput, concurrency limits, DB growth, AI-call cost | Yes — unacceptable performance regression | **Zero historical precedent — see backtest report** |
| 33 | 6 — Platform Intelligence Board | Observability Agent | `agents/33_observability_agent.md` | Logs, metrics, tracing, correlation, alerting, diagnosability | Yes — silent-failure-producing change | Descended from Phoenix's `PHOENIX-001`/`002` findings |
| 34 | 6 — Platform Intelligence Board | Technical Debt Curator | `agents/34_technical_debt_curator.md` | Classifies/prioritizes debt in the existing `MISSION_BOARD.md` registry | No independent veto — advisory prioritization | **Owns the existing registry — does not create a second one** |
| 14 | 4 — Legal Intelligence Board (advisory) | Compliance / Enterprise Readiness | *(reused)* `agents/14_compliance_enterprise_readiness.md` | Commercial/procurement/operational readiness | No — advisory only | Distinct from Agent 27 (code-checkable regulatory verification) |

**Total roles actively participating in Mission Olympus's board: 21** (19 new + Agents 05 and 14 reused
by explicit reference). **Total roles across both organizations: 34** (15 existing + 19 new).

## Numbering convention

Agents 01–15: pre-existing feature-development organization, unchanged. Agents 16–34: Mission Olympus's
new review-board roles, added 2026-08-04. No agent number is reused; no two agents share a charter file.
