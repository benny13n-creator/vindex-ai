# Vindex AI — Internal AI Engineering Organization: Org Chart

**What this is:** a permanent, developer-only intelligence layer inside this repository. It has
zero runtime presence in the Vindex AI product — no route imports it, no service calls it, it
never touches a request from an actual user. It exists so that every future non-trivial change to
Vindex AI passes through the same structured, adversarial, evidence-based process this repository
already used — informally, ad hoc, rebuilt from scratch each time — for the Trust Architecture
Blueprint, the Program 1 (AI Governance Layer) specification, and the 2026-08-02 forensic audit.
This directory makes that process a first-class, reusable structure instead of something reinvented
per conversation.

**How this differs from what already exists:** this repo already has real engineering process —
`docs/security/FINDING_LIFECYCLE.md` (9-stage maturity model), `docs/security/SECURITY_GAP_REGISTER.md`
(the evidence register), the Blueprint's own governing rule against ungoverned scope creep. This
organization does not replace any of that. It gives each *role* in that process a name, a charter,
explicit authority boundaries, and a designated output document — so "someone should red-team this"
stops being an instinct one person has to remember to apply, and becomes a named, checkable step.

---

## The fifteen roles

| # | Role | Charter | Authority | Vetoes? |
|---|---|---|---|---|
| 1 | AI CTO / Chief Architect | `agents/01_ai_cto_chief_architect.md` | Approves/rejects architecture; coordinates the rest | Yes — architecture |
| 2 | Product Strategist | `agents/02_product_strategist.md` | Defines the problem/user value; sets priority | No — but nothing proceeds without its output |
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
| 14 | Compliance / Enterprise Readiness | `agents/14_compliance_enterprise_readiness.md` | Assesses commercial/procurement/operational readiness per customer segment | No — advisory to the founder only |
| 15 | Security Verification Engineer | `agents/15_security_verification_engineer.md` | Verifies a declared control has an actual, executable Runtime Witness — not just a Policy-layer declaration | No independent veto — routes findings through Agent 05/Red Team |

## The rules that make this an organization, not a checklist

1. **No agent approves its own work.** The Solution Architect cannot sign off on its own design; the
   Backend Engineer cannot sign off on its own implementation. Every output needs a *different*
   role's review before the workflow advances.
2. **The Security Agent and the Red Team Agent can both block, independently, at any stage** — not
   only at their designated workflow step. If either raises a CRITICAL finding, work stops until it
   is resolved or a human (the founder) explicitly accepts the residual risk in writing.
3. **Architecture changes require the AI CTO's sign-off**, not just the Solution Architect's — the
   Solution Architect designs within existing architecture; changing the architecture itself is a
   CTO-level decision, same distinction the Blueprint already draws between Program-level fixes and
   Blueprint-level principles.
4. **Every non-trivial decision produces a written artifact** (a filled-out template from
   `templates/`), filed under `decisions/`, in this project's own established style: problem stated
   before solution, alternatives named and rejected with reasons, evidence cited by file:line where
   the claim is about the current codebase, not invented.
5. **Never optimize only for speed.** This organization's entire reason to exist is that this
   repository has already been burned by "looks right on paper" once (SEC-031's pre-review draft,
   Program 1 Revision 1's "firewall dressed as governance") and caught it every time only because
   someone applied a slower, adversarial pass. Speed is not the thing being protected here.
6. **Long-term maintainability outranks short-term convenience.** An agent that recommends the
   fast, disposable path over the one that fits how this codebase already does things
   (`shared/audit_immutable.py`'s hash chain, `shared/deps.py`'s ownership-check pattern, the
   monkeypatch-chokepoint technique) must say so explicitly and justify it — silently diverging
   from an established pattern is itself a red-team-catchable finding (see the pattern-consistency
   diagnosis in `docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md`'s executive summary).

## What this organization is NOT

- **Not 12 separate always-running processes.** Nothing in `.vindex_ai_team/` executes on its own.
  Every role is *invoked* — by Claude Code, acting as the role for one pass, per `README.md`'s
  "How Claude Code uses this daily" section.
- **Not a replacement for the founder.** Release Governance's sign-off gate does not remove the
  founder's own authority — it means nothing reaches the founder for a final call without already
  having passed every gate that doesn't require the founder's judgment specifically (the way
  Program 1's spec reached the founder only after peer review, not before).
- **Not a guarantee of correctness.** It is a structure that makes it much harder for a bad idea to
  survive unchallenged — not a proof that every idea it approves is right.
