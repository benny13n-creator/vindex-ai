# Vindex AI — Technical Finding & Change Lifecycle

**Date:** 2026-07-23 (revised same day — extended from 6 to 9 stages, scope broadened beyond security)
**Status:** Methodology document. Formalizes a pattern this project has already been following informally since the security audit began — writing it down so it stays consistent as more people and more findings enter the process, per founder's explicit request: *"Mislim da ste došli do tačke gde treba formalizovati nivoe nalaza."*
**Scope:** despite living in `docs/security/` (where it was first needed), this lifecycle is intended for **every** significant technical decision in this project — not just security findings. The founder's own framing: *"Sada kada imate FINDING_LIFECYCLE, ja bih ga koristio za sve. Ne samo security... LRE, Genome, Draft Engine, Case Genome, Risk Engine, Performance, UX."* A change to the Legal Reasoning Engine's confidence scoring, a Case Genome schema change, a Draft Engine prompt-safety change, or a performance-critical query rewrite all carry the same underlying risk this lifecycle exists to manage: a plan that sounds right on paper turning into code before its claims are checked. The location of this file does not limit its scope.

**Purpose:** prevent a document from silently turning into code. Every finding must pass through each stage explicitly — skipping a stage (especially "does the plan match reality" before "implement") is exactly how a correct-on-paper fix causes a real incident. **"Verified Fix" is deliberately not the same stage as "confirmed working in production"** — tests passing and a migration being logically correct is a different claim from "this is actually fine in the live environment, monitored, with no surprises" — collapsing those two into one stage is itself a common source of false confidence.

---

## The nine stages

| # | Stage | Definition | Who can move it forward | Example from this project |
|---|---|---|---|---|
| 1 | **Observation** | A pattern is noticed — not yet proven to be a problem, not yet scoped | Anyone, informally | "Several tables seem to use `TEXT` owner columns without an FK" (pre-SEC-033) |
| 2 | **Finding** | The problem is demonstrated with evidence (file:line, reproducible) and given an ID | Whoever demonstrates it, recorded in the relevant register (`SECURITY_GAP_REGISTER.md` for security; an equivalent register for other domains once adopted there) | SEC-031 the moment the first `ON DELETE CASCADE` chain was traced |
| 3 | **Confirmed Risk** | The *impact* is proven, not just the existence — blast radius mapped, what's actually at stake, what's still unverified vs. confirmed | Impact analysis document, evidence-cited | `SEC031_IMPACT_ANALYSIS.md` — 56-table blast radius, GDPR-endpoint interaction ruled out |
| 4 | **Remediation Candidate** | A concrete plan exists — design, migration/implementation plan, proof of the plan's own claims, rollback strategy | Migration safety plan + proof package | `SEC031_MIGRATION_SAFETY_PLAN.md`, `SEC031_FK_GRAPH.md`, `SEC031_PRODUCTION_ASSUMPTIONS.md`, `SEC031_MIGRATION_DRY_RUN.md` |
| 5 | **Architecture Approved** | An independent reviewer (a different person, or a different model instance with no prior context on the finding) has checked the plan for logical soundness, and it has passed the **Production Reality Gate** — the plan's assumptions about the live environment are confirmed, not just assumed. The design is approved; nothing has been built yet | Independent reviewer + environment verification, founder sign-off | SEC-031, after this round of correction — peer review found and closed 3 real gaps (`user_knowledge`, `conversations`, lock analysis); Production Reality Gate still open |
| 6 | **Implementation** | Code/migration is actually being written, following the approved design — this is its own tracked stage specifically so "we have an approved plan" and "someone is currently writing the code" aren't silently treated as the same fact | Whoever implements | Not yet reached for SEC-031 |
| 7 | **Verified Fix** | Implemented, automated tests pass (regression suite, new tests for this specific fix), rollback has been exercised (not just written) — but only proven in a controlled environment (local/CI/staging), not yet observed under real production conditions | Whoever implements + runs the verification | SEC-001 (implemented, 6 regression tests, full suite green) |
| 8 | **Production Verified** | The fix has run in the actual production environment and been confirmed correct there — not inferred from staging or tests. For a schema change, this means the live migration ran clean and the expected before/after behavior was observed for real, with monitoring in place for the specific failure modes the plan identified | Whoever deploys + monitors | Not yet reached for SEC-001 either, strictly speaking — SEC-001's fix is deployed, but this lifecycle didn't exist yet when it shipped, so it was never formally checked off at this stage. Worth doing retroactively as the first real use of stage 8. |
| 9 | **Closed** | The finding is retired — no further tracking needed. Only reachable from stage 8, after enough time/monitoring has passed to be confident the fix is durable, not just that it worked on day one | Founder or whoever owns the register | None yet — no finding in this project has completed the full nine stages |

## The two gates that matter most

**Peer Review Gate** (between stage 4 and 5): a reviewer who did not author the plan checks it for logical gaps, unstated assumptions, or claims that sound right but aren't verified. For anything touching irreversible operations (schema changes, data deletion, financial records, or — outside security — an LRE confidence-scoring change that could silently mislead a lawyer, a Genome schema change that could corrupt case history), this should be a genuinely independent pass — not the same reasoning process re-reading its own work, which tends to confirm itself. A fresh model instance with no prior context on the finding, given only the finished documents and explicitly instructed to try to falsify the claims rather than confirm them, is a practical way to get this for AI-assisted work — it can't inherit the framing bias of whoever built the plan, the way a second pass by the same reasoning would. **When this was actually run for SEC-031, it worked exactly as intended**: the independent reviewer found a real counter-example (`user_knowledge`), a real factual error (the `auth.users` lock claim), and a real scope gap (two unchecked SQL files) — none of which the original analysis had caught on its own. That is the gate doing its job, not a failure of the original analysis.

**Production Reality Gate** (also between stage 4 and 5, alongside peer review): everything a plan can prove *from the repository* has been proven — but some questions (does production's live schema match the repo, does the platform do anything undocumented, does an out-of-repo operational process depend on current behavior) cannot be answered by more code inspection, no matter how thorough. These must be answered by checking the actual environment before a plan is "Architecture Approved." A plan that has passed peer review but not this gate is not ready for implementation — it's ready to be checked against reality.

**Both gates must pass before stage 6 (Implementation) starts.** Passing one without the other is a false sense of readiness — a peer-reviewed plan built on a wrong assumption about production is still wrong; a production-verified assumption feeding into a logically flawed plan is still flawed.

**The stage 7 / stage 8 split exists for the same reason the two gates exist**: a green test suite proves the fix is logically correct given the assumptions the tests encode — it does not prove those assumptions matched reality, or that nothing about the live environment behaves differently than staging. Treating "tests pass" as "done" skips exactly the kind of gap this whole methodology exists to catch.

---

## Current findings, positioned on this scale (2026-07-23 snapshot, post-peer-review)

| Finding | Stage | Notes |
|---|---|---|
| SEC-001 | **7 — Verified Fix** (not formally re-checked at stage 8, since this lifecycle postdates it) | Implemented, tested, full suite green; live in production per prior session confirmation, but never formally passed through a stage-8 production-verification step under this framework |
| SEC-002 | **4 — Remediation Candidate** | Retention matrix + minimum-safe message fix proposed; not yet peer-reviewed or approved |
| SEC-003 | **2 — Finding** | Documented, fix is well-understood (wrap existing calls) but no plan document written yet |
| SEC-031 | **5 — Architecture Approved, pending Production Reality Gate** | Full proof package complete and independently peer-reviewed; 3 real gaps found and closed same day (`user_knowledge` added to Tier A, `conversations` added to Tier A, lock analysis corrected). Peer Review Gate substantively passed. **Production Reality Gate remains open** — explicitly the founder's own next step (read-only `information_schema` checks, staging run), not further repo analysis |
| SEC-032 | **2 — Finding** | Documented, low priority, no plan needed yet given small scope |
| SEC-033 | **1 — Observation → formally opened as its own initiative** | Pattern confirmed across 4+ feature areas; deliberately not advanced further yet — see `DATA_INTEGRITY_INITIATIVE.md` |

Everything else in `SECURITY_GAP_REGISTER.md` (SEC-004 through SEC-030, excluding the above) sits at **Stage 2 — Finding**: documented with evidence, not yet promoted to an impact analysis or remediation plan.

---

## What this document does not do

Does not itself move any finding forward a stage — it's the scale, not a decision. Does not replace the Gap Register (which stays the single list of all security findings); this document explains how a finding — in security or any other domain — is expected to mature over time, and gives a shared vocabulary so "we have a plan," "we're ready to implement," and "this works in production" don't get treated as the same statement. Does not yet have an equivalent register for non-security domains (LRE, Genome, Draft Engine, etc.) — adopting this lifecycle there would likely start with whatever tracking document each of those areas already uses, positioned against these same nine stages, rather than inventing a new register per domain.
