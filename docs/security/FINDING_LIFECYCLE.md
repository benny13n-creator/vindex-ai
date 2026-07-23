# Vindex AI — Security & Integrity Finding Lifecycle

**Date:** 2026-07-23
**Status:** Methodology document. Formalizes a pattern this project has already been following informally since the security audit began — writing it down so it stays consistent as more people and more findings enter the process, per founder's explicit request: *"Mislim da ste došli do tačke gde treba formalizovati nivoe nalaza."*

**Purpose:** prevent a document from silently turning into code. Every finding must pass through each stage explicitly — skipping a stage (especially "does the plan match reality" before "implement") is exactly how a correct-on-paper fix causes a real incident.

---

## The six stages

| # | Stage | Definition | Who can move it forward | Example from this project |
|---|---|---|---|---|
| 1 | **Observation** | A pattern is noticed — not yet proven to be a problem, not yet scoped | Anyone, informally | "Several tables seem to use `TEXT` owner columns without an FK" (pre-SEC-033) |
| 2 | **Finding** | The problem is demonstrated with evidence (file:line, reproducible) and given an ID | Whoever demonstrates it, recorded in `SECURITY_GAP_REGISTER.md` | SEC-031 the moment the first `ON DELETE CASCADE` chain was traced |
| 3 | **Confirmed Risk** | The *impact* is proven, not just the existence — blast radius mapped, what's actually at stake, what's still unverified vs. confirmed | Impact analysis document, evidence-cited | `SEC031_IMPACT_ANALYSIS.md` — 56-table blast radius, GDPR-endpoint interaction ruled out |
| 4 | **Remediation Candidate** | A concrete plan exists — design, migration plan, proof of the plan's own claims, rollback strategy | Migration safety plan + proof package | `SEC031_MIGRATION_SAFETY_PLAN.md`, `SEC031_FK_GRAPH.md`, `SEC031_PRODUCTION_ASSUMPTIONS.md`, `SEC031_MIGRATION_DRY_RUN.md` |
| 5 | **Approved Change** | An independent reviewer (a different person, or a different model instance with no prior context on the finding) has checked the plan and it has passed a **Production Reality Gate** — the plan's assumptions about the live environment are confirmed, not just assumed | Independent reviewer + environment verification, founder sign-off | Not yet reached for SEC-031 — this is the current gate |
| 6 | **Verified Fix** | Implemented, tested in the real environment (not just staging in theory), regression suite passes, and — for anything with a rollback story — the rollback itself has been exercised, not just written | Whoever implements + runs the verification | SEC-001 (implemented, 6 regression tests, full suite green) |

## The two gates that matter most

**Peer Review Gate** (between stage 4 and 5): a reviewer who did not author the plan checks it for logical gaps, unstated assumptions, or claims that sound right but aren't verified. For anything touching irreversible operations (schema changes, data deletion, financial records), this should be a genuinely independent pass — not the same reasoning process re-reading its own work, which tends to confirm itself. A fresh model instance with no prior context on the finding, given only the finished documents, is a practical way to get this for AI-assisted work — it can't inherit the framing bias of whoever built the plan, the way a second pass by the same reasoning would.

**Production Reality Gate** (also between stage 4 and 5, alongside peer review): everything a plan can prove *from the repository* has been proven — but some questions (does production's live schema match the repo, does the platform do anything undocumented, does an out-of-repo operational process depend on current behavior) cannot be answered by more code inspection, no matter how thorough. These must be answered by checking the actual environment before a plan is "Approved." A plan that has passed peer review but not this gate is not ready for implementation — it's ready to be checked against reality.

**Both gates must pass before stage 6 starts.** Passing one without the other is a false sense of readiness — a peer-reviewed plan built on a wrong assumption about production is still wrong; a production-verified assumption feeding into a logically flawed plan is still flawed.

---

## Current findings, positioned on this scale (2026-07-23 snapshot)

| Finding | Stage | Notes |
|---|---|---|
| SEC-001 | **6 — Verified Fix** | Implemented, tested, full suite green |
| SEC-002 | **4 — Remediation Candidate** | Retention matrix + minimum-safe message fix proposed; not yet peer-reviewed or approved |
| SEC-003 | **2 — Finding** | Documented, fix is well-understood (wrap existing calls) but no plan document written yet |
| SEC-031 | **4 — Remediation Candidate, at the gate into 5** | Full proof package complete (impact analysis, remediation design, migration safety plan, FK graph, production assumptions, migration dry run). **Blocked on both gates**: Peer Review (in progress — see companion independent review) and Production Reality Gate (read-only production verification not yet performed, is explicitly the founder's own next step, not further repo analysis) |
| SEC-032 | **2 — Finding** | Documented, low priority, no plan needed yet given small scope |
| SEC-033 | **1 — Observation → being formally opened as its own initiative** | Pattern confirmed across 4+ feature areas; deliberately not advanced further yet — see `DATA_INTEGRITY_INITIATIVE.md` |

Everything else in `SECURITY_GAP_REGISTER.md` (SEC-004 through SEC-030, excluding the above) sits at **Stage 2 — Finding**: documented with evidence, not yet promoted to an impact analysis or remediation plan.

---

## What this document does not do

Does not itself move any finding forward a stage — it's the scale, not a decision. Does not replace the Gap Register (which stays the single list of all findings); this document explains how a Gap Register row is expected to mature over time, and gives a shared vocabulary for where any given finding actually stands, so "we have a plan" and "we're ready to implement" don't get treated as the same statement.
