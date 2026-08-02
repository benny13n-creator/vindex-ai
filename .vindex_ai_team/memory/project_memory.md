# Project Memory — Institutional Knowledge

**Purpose:** the narrative record of how this project's engineering discipline actually developed —
not what's true right now (see `current_state.md`) or a specific decision (see
`architecture_decisions.md`/`security_decisions.md`), but the *history that explains why the
current process looks the way it does*. Read this when a new contributor (human or AI) needs to
understand why a rule exists, not just that it exists.

## How this project's rigor actually developed

This project did not start with the process this organization now formalizes. It developed it
incrementally, each time in direct response to a specific, concrete failure:

- **2026-07-23**: a 5-parallel-track adversarial audit found the platform's security posture at
  45/100, including two confirmed CRITICAL, live, exploitable findings (SEC-001, cross-tenant data
  write). This is the origin of the evidence-only, "never assume, always verify against code"
  discipline that now governs every review in this project.
- **2026-07-23**, same day, SEC-031 (the `auth.users` CASCADE risk) became the reference example
  for what "peer review done right" looks like — an independent reviewer found a real
  counter-example, a real factual error, and a real scope gap in the original remediation plan
  that the original analysis had missed entirely. This is the origin of the "always use a fresh,
  non-fork agent for adversarial review" rule — a second pass by the same reasoning tends to
  confirm itself, not falsify it.
- **2026-07-23**, `docs/security/FINDING_LIFECYCLE.md` was written specifically because the founder
  recognized a document could silently turn into code without its claims ever being checked against
  reality — the 9-stage model, and specifically the Stage 7/8 split (tests pass vs. confirmed in
  production), exists because collapsing those two into one stage is itself a common source of
  false confidence.
- **2026-07-24**, the audit-chain integrity *verifier itself* was found to have two bugs, undetected
  for 2.5 weeks, only caught by the first real live drill. Lesson institutionalized: a mechanism
  that has never been exercised against live data is a claim, not a verified property — this is why
  drills are scheduled recurring events in this project, not one-time builds.
- **2026-08-01**, the founder adopted the Trust Architecture Blueprint and immediately used it to
  challenge Claude's own proposed implementation order for the 5 Trust Architecture Programs — the
  order was wrong (P2 was scheduled before P1 despite Classification being a stage *inside* P1's own
  pipeline), and the correction came from the founder asking "if you designed this from scratch
  today, would you still choose this order," not from a technical re-analysis alone. Lesson: a
  good architectural question, asked at the right moment, catches what a technical review alone
  might not.
- **2026-08-01/02**, Program 1's architecture specification went through 8 revisions, each triggered
  by a specific, named critique — not because the process was inefficient, but because each pass
  found something genuinely real: a firewall pair mistaken for governance (no single decision-maker),
  a dead formula parameter, a chokepoint that covered one API surface out of five, a sync/async gap
  that would have made the fix for one Critical finding silently inapplicable to the majority of
  call sites. The founder's own framing, worth preserving verbatim: *"Pre mesec dana najveći rizik
  bio je: 'Krenućemo prerano.' Sada je najveći rizik suprotan: 'Nikada nećemo krenuti.'"* — the
  discipline that produces 8 careful revisions is the same discipline that must eventually say
  "this is done, ship it," or it becomes its own failure mode. Revision 8's targeted (not full)
  re-check, explicitly scoped to avoid "Revision 7, 8, 9…" paralysis, is the concrete mechanism this
  project uses to balance the two risks.
- **2026-08-02**, a full-codebase forensic implementation audit (not a document review) found the
  codebase's dominant failure mode was not incompetence but **narrow, inconsistent application of
  an already-correct pattern** — a diagnosis that reframes most of this organization's charters:
  the highest-leverage security/quality work in this project is usually not inventing a new control,
  it's checking whether an existing correct one was actually applied everywhere it should have been.

## Why this organization (`.vindex_ai_team/`) exists
Every one of the lessons above was learned the expensive way — by a specific failure surfacing in a
specific review. This organization exists to make each lesson a standing, checkable step in a named
role's charter, so the next contributor (human or AI) doesn't have to independently rediscover why
"never let an agent review its own work" or "a fresh agent, not a fork, for adversarial review" or
"check for sibling instances of the same bug, not just the reported one" are the rules — they can
read this file once and inherit the reasoning.
