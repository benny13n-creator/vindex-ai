# Agent Communication Protocol — Mission Olympus Governance Board

**What this adds**: the pre-existing 15-role organization's agents each write to their own bespoke
template (`templates/RED_TEAM_REPORT.md`, `templates/SECURITY_REVIEW.md`, etc.) — reasonable for a small,
stable set of long-established roles. The mission charter for this new board requires something stricter:
**every one of the 19 new agents uses the identical 7-field report format**, so the Enterprise AI
Director's aggregation step (Phase G2) can process any board's report mechanically, without a bespoke
parser per role. Existing agents (01–15) are unchanged — this protocol governs only Agents 16–34's
outputs (plus Agents 05/14's outputs *when invoked as part of a Mission Olympus review*, which already
happen to fit this shape closely).

## The mandatory 7-field format (verbatim from the founder's own mission charter)

Every report from Agents 17–34 (all review-board roles except the Director itself, whose output is the
aggregation, not a review) contains exactly these 7 sections, in this order:

1. **Scope** — what was actually reviewed (file list, mission name, specific change), and explicitly what
   was *not* reviewed (time-boxed exclusions, out-of-charter items) — matching this engagement's own
   established honesty norm ("not independently re-verified this pass" is a valid, required statement,
   not a gap to hide).
2. **Findings** — one entry per finding, each independently citable.
3. **Evidence** — file:line, test name, or document citation per finding. **No finding without evidence
   is permitted to appear in this section** — an unevidenced concern belongs in Open Questions instead.
4. **Risk Classification** — Critical / High / Medium / Low, per finding, using this project's existing
   4-tier vocabulary (`docs/security/FINDING_LIFECYCLE.md`'s own severity tiers, reused here rather than
   inventing a 5th vocabulary).
5. **Recommendation** — this agent's own gate state, per `QUALITY_GATES.md`'s table for this role.
6. **Confidence** — High / Medium / Low, stated honestly per finding or for the report as a whole where a
   single confidence level applies — this is new relative to the existing organization's templates, added
   specifically because Mission Olympus's roster includes agents measuring genuinely uncertain things
   (AI grounding, legal substantive correctness) where confidence itself is information the Director needs.
7. **Open Questions** — anything the agent could not resolve with the evidence available (time-boxed
   scope, missing test coverage, a founder decision required) — filed here, never silently dropped.

## Filing convention

`decisions/YYYY-MM-DD_<mission-or-change-name>_<AGENT_NAME>_REVIEW.md` — e.g.,
`decisions/2026-08-04_olympus_backtest_ai_grounding_agent_REVIEW.md`. Mirrors the existing
`decisions/` naming convention (`YYYY-MM-DD_<mission>_<TYPE>.md`) already used throughout this repository.

## Invocation mechanism

Same honest limitation already stated in `README.md`: this environment's `Agent` tool does not currently
expose the 19 new roles as first-class custom subagent types with individually-scoped tool access (that
would require `.claude/agents/*.md` frontmatter files, a mechanism `README.md` already declined to depend
on for the same reason in 2026-08-02, and this mission does not revisit that decision — see
`AI_GOVERNANCE_ARCHITECTURE.md`'s explicit non-goals). Every Agent 16–34 role is invoked the same two ways
`README.md` already established for Agents 01–15:

1. **Direct adoption** — Claude Code reads the charter file, acts as that role for one pass, in the
   current session. Appropriate for Agent 16 (Enterprise AI Director — needs continuity across the whole
   aggregation) and any role where the review benefits from context already in the conversation.
2. **Fresh subagent, charter-as-prompt** (`subagent_type: general-purpose`, `model: opus` for anything
   consequential) — **mandatory, never a fork**, for every veto-holding role (17, 18, 19, 20, 21, 22, 23,
   24, 25, 26, 27, 28, 30, 31, 32, 33) reviewing a change that agent (or the session that produced it) had
   any hand in — per `AI_GOVERNANCE_ARCHITECTURE.md` rule 1 ("no agent reviews own work") and the same
   fork-inherits-framing-bias reasoning `agents/04_red_team_devils_advocate.md` already states.

**Standard prompt structure for a fresh-subagent invocation** (mirrors `agents/04_...`'s own "How to
invoke this role" section, generalized):
1. Full context brief — the agent has zero prior knowledge of this conversation.
2. The charter file's full content (its Role/Responsibilities/Required inputs/Output/Authority/Forbidden
   sections), read in full, not summarized.
3. The specific artifact/change under review, by file path or diff, read in full.
4. The explicit scope boundary — what this specific pass covers vs. what's out of scope (a full audit vs.
   a narrowing falsification-only re-check, per `ESCALATION_RULES.md`'s existing distinction).
5. The mandatory 7-field output format, verbatim.

## How the Enterprise AI Director aggregates

Reads every filed report for the change under review, builds the `GOVERNANCE_AGGREGATION.md` table (one
row per invoked agent: gate state, headline finding if any, confidence), and checks for any `BLOCKED`/
`VULNERABLE`/`DEGRADED`-at-Critical-severity state per `QUALITY_GATES.md`. Does not re-adjudicate a
board's own finding — the Director aggregates and routes, it does not overrule (only the founder can, per
`DECISION_ESCALATION_POLICY.md`).

## No agent talks to another agent directly

Every hand-off happens through a filed artifact in `decisions/`, read by the next agent (or the Director)
— never an informal, unrecorded "agent A told agent B." This is `OPERATING_PROTOCOL.md`'s existing rule
("a phase's artifact is the only proof that phase happened"), restated as binding for inter-agent
communication specifically, since Mission Olympus's boards run largely in parallel and have no other
synchronization mechanism.
