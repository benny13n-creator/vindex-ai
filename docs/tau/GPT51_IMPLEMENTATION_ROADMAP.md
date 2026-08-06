# GPT-5.1 Implementation Roadmap — Program Tau, Master Sprint 001, Agent 8

**Date**: 2026-08-06
**Role**: Phase 2 (synthesis) + Phase 3 (critical/unnecessary/risk classification) + Phase 4 scope
decision, produced by reading all 7 prior deliverables in `docs/tau/` in full and cross-checking their
claims against the code changes made in this same sprint, not by re-deriving the analysis from scratch.

---

## 0. Blocking prerequisite — resolve before ANY model string changes

Agent 2 (`GPT51_INTEGRATION_ANALYSIS.md`, Section 0) found conflicting external signals: OpenAI's own Help
Center states GPT-5.1 "will continue to be available through the API" with advance retirement notice; a
lower-authority third-party source claims GPT-5.1 was retired from ChatGPT on 2026-03-11 and that API
calls may now silently fall back to a different model. **This could not be resolved from repo state or
within this sprint's scope.**

**This is a founder decision, not an engineering one.** Confirm the exact, current, non-deprecated model
ID (ideally a dated snapshot, not a generic alias) against `https://platform.openai.com/docs/deprecations`
before any call site's `model=` literal is changed. Nothing in this sprint depends on that confirmation
happening first — Phase 4 below deliberately touched zero model strings — but no future sprint should
either, until this is resolved.

## 1. Synthesis — what the 7 reports agree on

Cross-referencing all 7 deliverables surfaces one consistent theme, stated independently by Agents 1, 3,
5, and 6 without prompting each other (forks ran in parallel, not sequentially): **the platform's biggest
GPT-5.1 readiness risk is not the model, it's architecture the model would sit on top of.**

- Agent 3: 4 different, incomplete context-assembly functions — no GPT call site sees documents + Genome
  + evidence together (`TAU-001`).
- Agent 5 (independently) + Agent 1 (independently): 3 more live modules beyond Case Commander still let
  GPT invent facts/priorities the way Case Commander did before Sigma 005 (`TAU-002`, `TAU-003`, `TAU-004`).
- Agent 6: model tiering is real and load-bearing, but a uniform GPT-5.1 swap would break 2 things
  silently (cost misreporting, tight synchronous timeouts) if done without care.
- Agent 4 + Agent 2 (independently): the security/audit posture (`shared/ai_client.py`'s SDK-class-level
  patch) already transfers to any future model with zero changes — this is the one area that is already
  fully ready, not a risk.

Agent 7's test strategy and Agent 5's boundary policy both converge on the same underlying principle
already established in `docs/sigma/GPT_BOUNDARY_POLICY.md`: **a smarter model does not relax an
architectural restriction.** GPT-5.1 reasoning better does not make it safe to let GPT decide priority —
that boundary is structural, not capability-gated, and the 4 modules named in `TAU-002`–`TAU-004` still
need the same fix Case Commander already got, independent of which model eventually powers them.

## 2. Classification (Phase 3)

| Finding | Class | Why |
|---|---|---|
| `ai_forensics.py` docstring overclaim | **Critical-if-relied-on, trivial to fix** | A false claim in a compliance-relevant docstring; zero behavior risk to correct |
| `shared/cost.py` silent pricing fallback | **Necessary, low-risk** | Directly prevents silently wrong `api_costs` data for ANY future unrecognized model string, not just GPT-5.1 |
| Missing DC-014/DC-015 registry entries | **Necessary, low-risk, pre-existing gap** | Two independent agents (Agent 7, and this synthesis) found the registry drifted from Sigma 005's own code; the registry's whole purpose is to not drift |
| Guard not proven model-agnostic | **Necessary, low-risk, directly serves the mission** | Proves — not assumes — that swapping the model string later doesn't bypass security/audit; zero cost to add now |
| `TAU-001` (no unified context builder) | **Proven necessary, NOT low-risk — deferred** | Real architecture project; rushing it now risks a shallow fix and false confidence |
| `TAU-002`/`TAU-003`/`TAU-004` (GPT still invents decisions in 3 more modules) | **Proven necessary, NOT low-risk — deferred** | Each is a multi-file migration on the scale of Sigma 005 itself; `TAU-004` (`strategija.py`, 11 call sites) is the largest single one found in this sprint |
| `TAU-005` (Responses API guard gap) | **Correctly not urgent** | Zero live Responses API call sites exist; this is a tripwire for a future PR, not a bug today |
| `TAU-006` (strict structured outputs unused) | **Available improvement, not required** | No current code depends on schema enforcement; opt-in, not a fix |
| `TAU-007` (shadow-comparison harness) | **Correctly blocked** | Building a comparison harness against an unconfirmed model ID (Section 0) would be wasted work |
| Actually swapping any `model=` string to GPT-5.1 | **Explicitly NOT done this sprint** | Blocked by Section 0; also outside "implement only proven-necessary changes" — no call site's current model choice was shown to be inadequate, only potentially upgradeable |

## 3. What changed this sprint (Phase 4 — implemented, tested, all proven-necessary and model-choice-independent)

1. `security/ai_forensics.py` docstring corrected from "potpuna rekonstrukcija... čak i godinama kasnije"
   to accurately describe hash-only integrity verification (Agent 4's finding).
2. `shared/cost.py::estimate_cost` now logs a warning when falling back to gpt-4o pricing for an
   unrecognized model string, instead of silently misreporting spend (Agent 6's finding).
3. `docs/architecture/DECISION_CONTRACTS.md` + `DECISION_REGISTRY.md`: added `DC-014`
   (`_kanonski_nalazi`) and `DC-015` (`_kanonski_prioritet_i_rizici`), closing a registry-drift gap Agent 7
   found (Sigma 005's own canonical functions were never DC-registered). Also corrected the
   `DECISION_REGISTRY.md` fragmentation table's stale "Case Commander (3)" entry — Sigma 005 already
   closed that fragmentation; the table hadn't been updated to say so.
4. `tests/test_decision_registry_completeness.py`: added `test_dc014_*`/`test_dc015_*`, bumped the
   drift-tripwire count from 13 to 15.
5. `tests/test_sec003_llm_wrapper.py`: added `TestGuardIsModelAgnostic`, a parametrized test proving
   `_patch_prompt_guard` blocks prompt injection identically for `model="gpt-4o"`, `"gpt-4o-mini"`,
   `"gpt-5.1"`, and an arbitrary future model string — closing the one real gap Agent 7 found in the
   guard's own test coverage (it never varied the model string before this sprint).

**Nothing else changed.** No `model=` literal anywhere in the ~130 production call sites was touched. No
new AI call site was added. No new dependency was introduced.

## 4. What stays exactly the same, and why

- **Every model string** (`gpt-4o`/`gpt-4o-mini`) — unchanged, per Section 0 and the mission's own explicit
  "ne menjati model globalno" instruction.
- **Chat Completions API surface** — unchanged; the SDK/transport layer already supports a model-string
  swap without a Responses API migration, so there is nothing to prepare here beyond `TAU-005`'s tripwire.
- **The existing `gpt-4o`/`gpt-4o-mini` tiering** — confirmed real and load-bearing (Agent 6); a future
  GPT-5.1 adoption should extend this pattern (add a 3rd tier for genuine multi-step reasoning), not
  flatten it into a uniform swap.
- **`shared/ai_client.py`'s guard/provenance interception** — confirmed structurally model-agnostic
  (Agent 2, Agent 4) and now proven so by a test (Section 3.5), so it needs zero changes to keep working
  under any future model choice.
- **Case Commander's Sigma 005 architecture** — unchanged; it remains the reference pattern the deferred
  items (`TAU-002`–`TAU-004`) should each be migrated onto when their own dedicated sprints happen.

## 5. What's deferred (see `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`, "Program Tau, Master Sprint
001" section, for full detail on each)

`TAU-001` (no unified case-context builder — High, the anchor item for any future reasoning-layer work),
`TAU-002` (`case_intelligence.py`/`copilot.py` GPT-fallback next-action — Medium), `TAU-003`
(`morning_briefing.py` zero `case_actions` awareness — Medium-High), `TAU-004` (`strategija.py`'s 3-way
GPT-invented risks/gaps/next-steps, 11 call sites — Critical, largest remaining single violation),
`TAU-005` (Responses API guard gap — Low today, tripwire), `TAU-006` (strict structured outputs unused —
Low, available lever), `TAU-007` (shadow-comparison harness — Informational, blocked on Section 0).

None of these were rushed into this sprint. This mirrors the same discipline Sigma 004 applied to
`SIGMA-018` (name it, don't rush it) — the difference this sprint is that Section 0's own unresolved model
identity makes rushing any of these doubly premature: fixing `TAU-004` against a to-be-confirmed GPT-5.1
target before that target is confirmed would risk redoing the work.

## 6. Where GPT-5.1 (or whatever the confirmed current model is) actually brings value

Per Agent 5's `LEGAL_AI_BOUNDARY_POLICY.md` and Agent 6's cost analysis, in order of evidenced fit:

1. `services/legal_reasoning_engine.py` — already the strongest evidence-grounding pattern in the
   codebase (SOURCE-n citations built only from real retrieved tuples); this is the template, not a
   greenfield choice.
2. `strategija.py`'s synthesis calls, once `TAU-004` closes the fact-invention gap — multi-step reasoning
   over already-canonical facts is exactly where a stronger reasoning model earns its cost.
3. `routers/court_predictor.py`, IF a live-model evaluation (Agent 7's shadow/replay methodology, once
   Section 0 is resolved) shows genuine output-quality improvement — cost tolerance exists structurally
   (not a hot loop), but this is not yet proven, only plausible.

## 7. Where it must not be used, regardless of model capability

Creating a `case_action`; changing `prioritet`/`hitnost`/readiness status; asserting something is missing
or resolved; bypassing `case_actions`/`gap_engine`/`case_readiness`/`identify_case_problems` with an
independently-derived equivalent — per `LEGAL_AI_BOUNDARY_POLICY.md`. Also: every `gpt-4o-mini`
classification/extraction call site (Agent 6) — a reasoning model buys nothing there but latency and cost;
`commander_quick_check`/`commander_checklist` (Sigma 005) are the extreme, already-proven version of this
argument — the right answer for a pattern-matching task is sometimes "call no model at all."

## 8. Certification against the mission's own Definition of Done

| Requirement | Status |
|---|---|
| Complete map of AI architecture exists | **Yes** — `AI_ARCHITECTURE_MAP.md`, 138 call sites, 56 files, grep-verified |
| Every AI input/output is known | **Yes, at the map level** — deep-read for the 5 highest-stakes sites; the other ~130 are inventoried by file/model/endpoint, not each individually read line-by-line (stated limitation, `AI_ARCHITECTURE_MAP.md` §"What this deliverable does NOT claim") |
| Know where GPT-5.1 brings value | **Yes** — Section 6 above, evidenced, not speculative |
| Know where it must not be used | **Yes** — Section 7 above, architectural not capability-gated |
| Implemented changes pass all tests | **Yes** — see Phase 5 regression run |
| No regression of existing security principles | **Yes** — the guard/audit layer was proven (not assumed) model-agnostic; nothing in Phase 4 touched security-relevant code paths except to make an existing gap more visible (`shared/cost.py`) or an existing docstring more accurate |

**This sprint does not claim GPT-5.1 is now integrated.** It claims the platform's AI architecture is now
fully mapped, its readiness gaps are named and classified (not guessed at), the model-identity question is
correctly escalated rather than assumed, and the small set of changes that were both proven necessary and
low-risk are implemented and tested. The founder's own framing applies here exactly as it did to Sigma
005: the goal was never "adopt a new model faster" — it was "know, precisely, what adopting it would
actually require."
