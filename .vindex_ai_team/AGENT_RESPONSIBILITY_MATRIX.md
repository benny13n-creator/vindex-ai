# Agent Responsibility Matrix (RACI) — Mission Olympus Governance Board

RACI for the 21 review-board roles (19 new + Agents 05/14 reused) against every governance activity a
"major change" (per `AI_GOVERNANCE_ARCHITECTURE.md`'s threshold) can trigger. **R**esponsible = does the
review and produces the artifact. **A**ccountable = owns the final call for that activity and answers to
the founder for it. **C**onsulted = provides input the Responsible party must incorporate before
finalizing. **I**nformed = receives the finished artifact, does not act on it further.

The Enterprise AI Director (16) is **Accountable** for every row below except its own aggregation step
(where the founder is Accountable) — this is deliberate: Olympus's whole design principle is that no
review agent is accountable for its own domain to itself, only to the Director, who in turn answers to
the founder. This mirrors `ESCALATION_RULES.md`'s existing principle that no role outranks a veto except
the founder, extended to non-veto accountability too.

| Activity | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Route a completed change to the correct boards | Enterprise AI Director (16) | Founder | — | All active boards for that change |
| Architecture soundness of a completed change | Architecture Review Agent (17) | Enterprise AI Director (16) | AI CTO (01) if the change touches CTO-approved architecture | All other active boards |
| Backend/API/DB/event/transaction correctness | Backend Engineering Review Agent (18) | Enterprise AI Director (16) | Database Architect (08) if a migration is involved | Architecture Review (17), Reliability & Chaos (20) |
| Frontend/UI correctness, false-success messages | Frontend Engineering Review Agent (19) | Enterprise AI Director (16) | Beta Experience Agent (29) | Product Consistency (28) |
| RLS/auth/authz/OWASP/secrets/audit-immutability | Security Review Agent (05) | Enterprise AI Director (16) | Regulatory Compliance Verification (27) | All active boards — a Security BLOCKED halts everything, per `ESCALATION_RULES.md` |
| Retry/rollback/recovery/idempotency/dead-letter/chaos | Reliability & Chaos Agent (20) | Enterprise AI Director (16) | Backend Engineering Review (18), Observability (33) | Metrics Guardian (31) |
| AI response-level quality, cross-version consistency | AI Quality Auditor (21) | Enterprise AI Director (16) | AI System Architect (06) | AI Grounding (23) |
| AI explainability — sources, citations, limitations | AI Explainability Agent (22) | Enterprise AI Director (16) | AI Grounding Agent (23), Evidence Integrity (26) | Legal Domain Expert (25) |
| AI grounding — evidence-based, no fabricated numbers | AI Grounding Agent (23) | Enterprise AI Director (16) | AI Explainability Agent (22), Metrics Guardian (31) if a confidence score is a reported metric | AI Quality Auditor (21) |
| Benchmark measurement — precision, regression, model comparison | AI Evaluation & Benchmark Agent (24) | Enterprise AI Director (16) | AI Quality Auditor (21) | Technical Debt Curator (34) |
| Legal logic/terminology/workflow substantive correctness | Legal Domain Expert (25) | Enterprise AI Director (16) | Evidence Integrity Agent (26) | Product Consistency (28) |
| Factual claims traceable to document/page/paragraph | Evidence Integrity Agent (26) | Enterprise AI Director (16) | Legal Domain Expert (25), AI Grounding (23) | AI Explainability (22) |
| GDPR/AI Act/retention/audit regulatory obligation | Regulatory Compliance Verification Agent (27) | Enterprise AI Director (16), escalates to Founder on Critical | Security Review (05), Compliance/Enterprise Readiness (14) | All active boards |
| Automatic-workflow expectation gaps | Product Consistency Agent (28) | Enterprise AI Director (16) | Workflow Integrity Agent (30) | UX/UI Experience Architect (07) |
| Black-box lawyer-experience simulation | Beta Experience Agent (29) | Enterprise AI Director (16) | Frontend Engineering Review (19) | Product Consistency (28) |
| End-to-end named-process connectivity | Workflow Integrity Agent (30) | Enterprise AI Director (16) | Product Consistency (28), Architecture Review (17) | Metrics Guardian (31) |
| Metric methodology soundness (ICS/CIC/Reliability/Audit/Provenance/Replay/Recovery) | Metrics Guardian (31) | Enterprise AI Director (16) | Whichever agent originally computed the metric under review | All active boards + `METRICS.md`'s maintainer |
| Latency/throughput/concurrency/cost | Performance & Scalability Agent (32) | Enterprise AI Director (16) | Backend Engineering Review (18) | Technical Debt Curator (34) |
| Logs/metrics/tracing/correlation/alerting | Observability Agent (33) | Enterprise AI Director (16) | Reliability & Chaos Agent (20) | Metrics Guardian (31) |
| Technical debt classification and priority | Technical Debt Curator (34) | Enterprise AI Director (16) | Architecture Review (17) | Founder (via `MISSION_BOARD.md`) |
| Commercial/procurement/operational readiness | Compliance / Enterprise Readiness (14) | Founder (advisory-only, per its existing charter) | Regulatory Compliance Verification (27) | Enterprise AI Director (16) |
| Final merge recommendation | Enterprise AI Director (16) | **Founder** | Every board invoked for this change | Everyone |

## Overlap check (mission target: 0)

Every row above has exactly one Responsible party. No two agents share Responsible status for the same
activity. Where two agents' scopes are conceptually adjacent (Explainability/Grounding, Product
Consistency/Workflow Integrity, Backend Review/Database Architect, Compliance/Regulatory Compliance
Verification), the distinguishing question is stated explicitly in `AI_GOVERNANCE_ARCHITECTURE.md`'s
per-role description and repeated in each pair's own agent charter file's "Explicitly not this agent's
job" section. **Overlap count: 0**, verified by this table having exactly 21 distinct Responsible-column
values, one per role.

## Coverage check (mission target: 0 uncovered areas)

Every one of Mission Olympus's founder-specified layers and named agents (Layer 1 through 6, all 19 new
roles plus the 2 reused roles) appears as the Responsible party in at least one row above. **Uncovered
areas: 0** among the founder-specified scope. Known, explicitly-acknowledged gaps *beyond* the
founder-specified scope (not a failure of this matrix, a fact about what was never in scope): the
pre-existing 15-role organization's feature-development activities (Product Discovery, UX Specification,
etc.) are intentionally not duplicated here — see `AGENT_CATALOG.md` Part A for those.
