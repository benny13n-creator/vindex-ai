# Escalation Rules

Consolidates every charter's individual "Escalation" section into one decision tree. When in doubt
about who resolves a disagreement, this file is the reference — individual charters state the same
rules in context but this is the canonical version.

## The core principle
**No agent overrides a veto-holding role's blocking verdict except the founder, in writing.** Not
the AI CTO, not Release Governance, not a more senior-sounding role — none of the roles in this
organization outrank a veto. Veto roles are: Red Team, Security & Privacy Architect, Database
Architect (destructive migrations only), QA Engineering (release-blocking only), Release Governance
(final).

## Escalation paths

| Situation | Escalates to | Resolution mechanism |
|---|---|---|
| Red Team returns BLOCKING | Founder | Fix the finding, or founder writes an explicit risk-acceptance record (filed alongside the `RED_TEAM_REPORT.md`, not verbal) |
| Security & Privacy Architect returns BLOCKED | Founder | Same as above; a `CONDITIONAL` status's named condition is met and re-verified before proceeding, not waived |
| Database Architect vetoes a destructive migration | Founder | Founder either accepts the SEC-031-style safe-migration methodology (impact analysis → peer review → dry run) or explicitly authorizes a faster path in writing, accepting the stated risk |
| AI CTO and Solution Architect disagree on architectural fit | AI CTO's judgment is final at this level, but if the Solution Architect believes the CTO is factually wrong (e.g., about whether an existing system already does this), that specific factual claim gets verified against actual code before the disagreement is treated as a judgment call rather than a checkable fact |
| Product Strategist and Solution Architect disagree on scope | AI CTO arbitrates — scope-vs-architecture tension is exactly the kind of cross-cutting call the CTO role exists for |
| UX/UI Experience Architect and Security & Privacy Architect disagree (a UX shortcut vs. a security requirement) | Security wins, always — stated explicitly in `agents/07_ux_ui_experience_architect.md`'s own charter, restated here because it's a common enough tension to name in the general rule set, not bury in one charter |
| QA Engineering finds the feature doesn't fit `PRODUCT_SPECIFICATION.md`'s actual acceptance criteria, even though it passes its own tests | Product Strategist — this is a spec-fit problem, not a QA problem, though QA still blocks release on it |
| Any role disagrees with a prior *closed* decision recorded in `memory/architecture_decisions.md`, `memory/rejected_ideas.md`, or `memory/security_decisions.md` | Do not silently re-litigate. State the new argument explicitly and why it's different from what was already considered — matching `memory/rejected_ideas.md`'s own template requirement for a stated "trigger to revisit," not just "I think differently now" |

## What "in writing" means in practice

A decision, override, or risk-acceptance is "in writing" when it exists as a dated entry in a
`decisions/*.md` file or a `memory/*.md` file — not a chat message alone, not a verbal "sounds
good." This mirrors this project's own standing rule that every important decision requires written
reasoning, applied here as a mechanical requirement, not a preference.

## CLOSED findings are locked (founder rule, added 2026-08-02)

Once a Red Team (or Security & Privacy Architect) finding is marked CLOSED/FULLY CLOSED after a
falsification attempt genuinely tried and failed to break it, it does not get re-opened by another
review pass "just to be sure." This applies even inside a rapid multi-revision cycle like the
2026-08-02 forensic remediation plan's Epic B, which went through 3 BLOCKING verdicts before its
core mechanism (the `Limiter` collapse) was confirmed sound on 7 independent falsification attempts.

- **BLOCKING finding →** may return to Red Team after the fix, as many times as the fix itself
  changes.
- **CLOSED finding →** locked. It reopens only if the underlying code or architecture it was
  verified against changes — never as a side effect of a later, unrelated review pass "checking
  everything again."
- **A narrowing pass earns a narrowing scope.** Each successive Red Team pass on the same artifact
  should be told explicitly what remains open (per the artifact's own Red Team reports) and
  instructed to attempt exactly those items — not to re-derive the whole surface from scratch. This
  is what keeps a legitimate multi-pass convergence (Epic B: 4 Critical → 1 High → 1 High, narrowing
  each time) from degrading into the "Revision 7, 8, 9… analysis paralysis" the founder has
  explicitly warned against more than once in this project's history.
- **A pass that finds nothing new is a real result, not a non-result.** If a falsification-only
  pass, told to attempt exactly N named things, fails to break all N, the artifact moves forward —
  it does not trigger a further, broader pass "to double check." The founder's own framing for this:
  a pass structured as "assume the fix is wrong; try to prove exactly these N specific things; if
  you can't, mark CLOSED" is what prevents the loop from becoming unbounded.

## Terminal closing tests (founder rule, added 2026-08-02, second addition same day)

When a single item inside an artifact has gone through several real (not manufactured) BLOCKING
cycles — the 2026-08-02 forensic remediation plan's Epic B went through 4, each one finding a
genuine structural defect, not a nitpick — the founder may set an explicit **terminal closing
test** for the next pass: a small, precisely-named set of things to attempt, with a stated rule that
survival closes the item for the whole mission, not just for that pass.

- This is different from an ordinary narrowing pass. An ordinary pass narrows scope but leaves the
  door open for another pass afterward. A terminal test is the founder deciding, explicitly, that
  *this* is the last architecture-track check for *this* item — pass it, and the item graduates out
  of the Red Team loop entirely; it does not return to Red Team again absent a genuine
  implementation deviation from the approved spec (which is a QA-track concern from that point,
  Phase 6/7 of `OPERATING_PROTOCOL.md`, not an architecture-track reopening).
- A terminal test is warranted specifically when the *fix itself* has changed in kind, not just in
  detail — e.g. Epic B's Revision 5 didn't just correct two numbers, it replaced the bypass-
  prevention model and the limit-sizing model. That is a new design being checked, which is why one
  more pass is legitimate rigor rather than the "Revision 7, 8, 9…" pattern the founder has warned
  against elsewhere — the fix that reaches CLOSED under a terminal test is a materially different
  fix than the one Revision 1 shipped, not the same one re-approved five times.
- The pass itself must still be genuinely adversarial, not a rubber stamp — the founder's own
  framing for Epic B's terminal test named concrete, falsifiable questions (can a *future* route
  change silently defeat the mechanism, not just do the 5 known routes hold; does each limit tier
  have a stated attack-prevented/workload-supported rationale, not just a number; does a named
  enterprise-scale scenario actually hold) rather than "look it over once more."

## Escalation does not mean delay-by-default

Escalating to the founder should happen as soon as a blocking condition is identified — not batched
up and presented at the end of a long workflow. The founder resolving a Phase 3 block before Phase 4
even starts is cheaper for everyone than discovering the same block during Phase 7's final checklist.
