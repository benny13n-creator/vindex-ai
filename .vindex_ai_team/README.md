# Vindex AI Internal Engineering Organization

**This directory has zero runtime presence in the product.** Nothing in `.vindex_ai_team/` is
imported by, called by, or deployed with Vindex AI. It is a developer-only intelligence layer — a
structured, named, adversarial engineering process that Claude Code (and any human contributor)
follows when doing non-trivial work on this repository, so that the rigor this project has already
proven the value of (the 2026-07-23 security audit sprint, Program 1's 8-revision architecture
review, the 2026-08-02 forensic implementation audit) is a standing structure, not something
reinvented, informally, per conversation.

Start at `ORG_CHART.md` for the 12 roles and the rules that make them an organization rather than a
checklist. This file covers how the organization actually gets *used*.

---

## How Claude Code uses this daily

**This organization is not 12 separate running processes.** Nothing here executes on its own. Every
role is *invoked* — either by Claude Code adopting the role directly (reading the charter, producing
the artifact, in the current session, with full context), or by spawning a fresh subagent briefed
with the charter as its prompt.

**The honest limitation, stated plainly rather than glossed over:** Claude Code's `Agent` tool
invokes a fixed set of subagent types (`general-purpose`, `Explore`, `Plan`, and a few others) unless
this environment has separately configured custom subagent types via `.claude/agents/*.md` — a
mechanism this organization does not assume or depend on, because its exact schema was not
available to verify with confidence at the time this organization was built. Every one of the 12
roles is therefore invoked one of two ways, and each charter states explicitly which:

1. **Direct adoption** (roles 1, 2, 3, 6, 7, 8 as the default path, 9, 10, 12) — Claude Code reads
   the charter, acts as that role for this pass, and produces the required artifact. Used when the
   role needs continuity with the rest of the conversation (an ongoing design discussion, iterative
   implementation) or judgment calls that benefit from the full context already in play.
2. **Fresh subagent, charter-as-prompt** (roles 4 and 5 always; 6, 8, 11 for a dedicated adversarial
   pass) — Claude Code spawns a subagent via the `Agent` tool with `subagent_type: "general-purpose"`
   (and `model: "opus"` for anything consequential), and constructs the prompt from: the charter
   file's content, the specific artifact under review, and an explicit scope boundary. **This exact
   mechanism has already been used successfully 6 times in this repository's history** — twice for
   Program 1's red-team reviews, once for SEC-031's original peer review, and four times in parallel
   for the 2026-08-02 forensic audit's section-by-section coverage. It is proven, not speculative.

**Why fresh, not a fork:** a fork inherits the same context and framing bias as whoever built the
thing under review. This defeats the purpose of adversarial review specifically. Every veto-holding
role (Red Team, Security) must be invoked fresh when doing a genuine adversarial pass.

## Worked example — how a new Vindex AI feature request flows through this team

Say the founder asks for: *"Let's add a feature where the AI drafts a settlement demand letter
automatically after Case Genome reaches a certain confidence threshold."*

1. **Product Strategist** (Claude Code, direct): writes `PRODUCT_SPECIFICATION.md`. Asks: which
   user problem does this solve (a lawyer forgetting to draft demand letters promptly? a genuine
   time-saver on a known-frequent task?), which segment benefits, is this MVP or premature (does
   Case Genome's confidence scoring already reliably support gating a legal document's generation
   on it — check `docs/architecture/CASE_GENOME_REALITY_VALIDATION_REPORT.md` before assuming yes).
2. **Solution Architect** (Claude Code, direct): writes `TECHNICAL_DESIGN.md`. Checks: does the
   Drafting Engine (`drafting/`, `routers/drafting.py`) already have the right shape for this, or
   does it need a new trigger mechanism tied to Case Genome's confidence field? Names the AI call
   site, whether it's a new one or reuses an existing drafting flow.
3. **AI System Architect** (Claude Code, direct, since this is squarely AI-architecture territory):
   writes `AI_DESIGN_REVIEW.md`. Checks chokepoint coverage (this is a chat-completions call, so
   `_patch_prompt_guard` covers it), PII handling (does the demand-letter prompt include the
   opposing party's name and address — yes, almost certainly — is `_skini_pii` in this specific
   call's path, and does `_skini_pii` even cover names — no, per SEC-006 — flag this explicitly
   rather than let it pass silently), hallucination risk (a demand letter with a fabricated damages
   figure or a hallucinated case citation is a severe real-world harm — what's the Response Firewall
   equivalent for this specific output type, given Program 1 isn't implemented yet).
4. **Database Architect**: N/A (no schema change) — Solution Architect states this explicitly,
   Database Architect review is skipped, not silently — the design doc records why.
5. **Security & Privacy Architect** (fresh subagent, since this touches PII and an AI-generated
   legal document with real consequences if wrong): writes `SECURITY_REVIEW.md`. Flags: is this
   feature auditable (does it need a new `AUDITABLE_ACTIONS` entry — almost certainly yes, "an AI
   drafted and sent/queued a legal document" is exactly the kind of action this project's audit
   discipline says must be traceable), does the confidence-threshold gate need to be provably
   correct given `KNOWN_RELIABILITY_RISKS.md`'s documented fail-open bug in `verify_genome()`.
6. **Red Team** (fresh subagent, `model: opus`, mandatory): writes `RED_TEAM_REPORT.md`. Attacks:
   what happens if Case Genome's confidence score is wrong (fail-open bug, again, from a different
   angle) and a demand letter goes out with a fabricated fact; what happens with 1000 documents in
   one predmet and the drafting prompt exceeds context; what happens if two demand letters
   auto-generate for the same matter under concurrent triggers (no `FOR UPDATE SKIP LOCKED` on this
   path — check).
7. **AI CTO**: since this is a new capability, not just a config change, writes
   `ARCHITECTURE_DECISION.md` — does this belong inside the existing Drafting Engine or does it need
   its own trigger service; final recommendation, with the Red Team and Security findings addressed
   or explicitly deferred with founder sign-off.
8. **UX/UI Experience Architect** (Claude Code, direct): writes `UX_SPECIFICATION.md` — critically,
   given the AI-decides-vs-AI-helps boundary this project has already drawn
   (`VINDEX_AI_PRODUCT_PHILOSOPHY_v1.0.md`), this almost certainly needs an explicit human-review
   step before the letter is actually sent, not full automation — the UX spec should make that
   review step the obvious, fast, trustworthy default path, not an afterthought checkbox.
9. **Backend/Frontend Engineering** (Claude Code, direct): implement per the approved design,
   `IMPLEMENTATION_PLAN.md` naming the new `AUDITABLE_ACTIONS` entry explicitly.
10. **QA Engineering** (Claude Code direct, or fresh subagent for an adversarial pass on failure
    modes specifically): `QA_REPORT.md` — happy path, the confidence-threshold boundary, concurrent
    trigger, a Genome refresh mid-draft.
11. **Release Governance** (Claude Code, direct): `RELEASE_APPROVAL.md` — checklist verified, gaps
    named if any are accepted rather than closed, founder sign-off recorded for the AI-generates-a-
    legal-document risk class specifically (this is exactly the kind of feature Program 1's eventual
    Decision Engine, once built, would govern — noting that dependency explicitly, even though
    Program 1 isn't implemented yet, is itself valuable institutional memory for `known_risks.md`).

Every artifact above gets filed in `decisions/` per its naming convention, and anything that
generalizes (a new rejected alternative, a newly-discovered risk) gets added to the relevant
`memory/*.md` file — this worked example itself should be replaced with the first *real* feature
run through this process, once one happens.

## Limitations, stated honestly

- **This organization has not yet been exercised on a real feature end-to-end.** It is built from
  the patterns this project's real history already proved work (the security audit sprints, Program
  1's revisions, the forensic audit) — but a structure inferred from past successes is not the same
  as a structure validated by its own first real use. Treat the first real workflow run through this
  as a test of the organization itself, and update `memory/known_risks.md` with whatever friction
  it surfaces.
- **The custom-subagent-type mechanism (`.claude/agents/*.md`) is not used here**, deliberately,
  because its exact schema was not confidently verified at the time of writing — this organization
  uses the proven charter-as-prompt-to-a-fresh-agent mechanism instead. If a future session
  confirms the custom-subagent schema, migrating the veto-holding roles (Red Team, Security) to
  first-class custom subagent types would be a reasonable, low-risk upgrade — the charter content
  wouldn't need to change, only how it's registered.
- **This does not replace the founder's authority.** Every gate this organization enforces is a gate
  that was already, informally, this project's actual practice — the organization makes it
  consistent and named, it does not add a new layer of approval beyond what already existed.
- **Some roles will feel like overhead for a genuinely tiny change** (a copy fix, a one-line bug
  fix with no security implication). The workflows account for this — `bugfix_hotfix_workflow.md`'s
  non-security path is intentionally lighter than the New Feature workflow — but the organization
  errs toward "still produce a small artifact" rather than "skip the gate entirely," because this
  project's own history (SEC-001 through SEC-073) is full of findings that started as "this is a
  small, obviously-safe change."

## Future expansion possibilities

- A **Localization/Legal-Content Accuracy Architect** role, specific to Serbian legal content
  correctness (ZPP/ZKP citation accuracy, court-terminology correctness) — distinct from the AI
  System Architect's general LLM-architecture concerns, this would own whether generated legal
  content is *substantively* correct for Serbian practice, closer to a subject-matter-expert review
  than a systems-architecture one.
- A **Pilot/Customer Success Liaison** role, feeding real pilot-user friction (per the Pilot Success
  Framework's Rule A/B/C and Evidence Matrix) directly into the Product Strategist's inputs, rather
  than the Product Strategist having to go find that evidence itself each time.
- Once a formal custom-subagent-type mechanism is confirmed available, migrating Red Team, Security
  & Privacy Architect, and QA Engineering to genuinely independent, directly-invokable subagent
  types (rather than charter-as-prompt) would reduce the setup overhead of each invocation.
- A lightweight script that checks whether a `decisions/` artifact chain is complete for a given
  feature branch before it's mergeable — turning `RELEASE_APPROVAL.md`'s checklist from a manually-
  verified document into a mechanically-checkable one.
