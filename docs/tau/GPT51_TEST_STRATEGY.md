# GPT-5.1 Test Strategy — Program Tau, Master Sprint 001 (Agent 7)

**Scope**: Phase 1 analysis only. This document defines HOW any future GPT-5.1
integration work must be tested — it does not implement any test yet, and it
does not touch application code. Every claim below about existing test
infrastructure is grounded in files read directly during this analysis, not
assumed from memory.

---

## 1. What already exists (precedent this strategy builds on)

Vindex AI already has three independent, working test patterns for
AI-boundary enforcement. GPT-5.1 testing should extend these, not invent a
fourth parallel philosophy.

### 1.1 Structural provenance/consumption tests
`tests/test_sigma_sprint005_commander_consolidation.py` (16 tests) proves,
at the unit level, that `routers/case_commander.py`'s canonical fields
(`_kanonski_nalazi`, `_kanonski_prioritet_i_rizici`) always carry
`{value, source, evidence, confidence, generated_by, timestamp}`
(`shared/commander_schema.py`), that GPT-advisory fields never carry
`evidence`, and — the load-bearing test —
`test_cross_case_analiza_prioritet_ignores_gpt_and_uses_case_actions`
(line 227) directly proves GPT's own JSON output for a removed field
(`prioritet`) is structurally impossible to use even if the model tries to
return it, because the prompt no longer asks for it and the code path
never reads that key from the GPT response. This is the strongest pattern
in the repo: **don't test that GPT behaves; test that the code can't
listen even if it misbehaves.**

### 1.2 Reference-existence (anti-hallucination) validators
`shared/genome_validator.py` — `validate_dok_reference` (line 269),
`validate_graph_edge_references` (line 300), `validate_predmet_reference`
(line 331) — all share one principle: a GPT-cited reference (a DOK-XX
number, a graph node id, a predmet ID prefix) must exist in a known set
built from real data BEFORE the GPT call. `validate_predmet_reference` also
now fuzzy-checks the cited `predmet_naziv` against the real name for that
prefix (line 354-362), catching cross-case misattribution, not just
invented IDs. Covered by `tests/test_genome_validator.py`. This is a
**reference-existence check, not a truth check** — it cannot prove a GPT
claim is correct, only that it isn't pointing at something that doesn't
exist. Any GPT-5.1 output that cites a document/case/entity by ID must run
through the matching validator in this module (or a new one following the
identical shape) before being trusted enough to display.

### 1.3 Decision Registry drift tripwire
`docs/architecture/DECISION_REGISTRY.md` + `tests/test_decision_registry_completeness.py`
(13 `test_dcNNN_*` tests, DC-001..DC-013) mechanically prove that every
function the registry *claims* is "the canonical source" for a named
business decision still exists, is importable, and hasn't been silently
renamed/deleted (see file docstring, line 3-15 — it explicitly disclaims
detecting a *new* undeclared decision, since that needs static analysis
infra the repo doesn't have). **Gap found during this analysis**: Case
Commander's own canonical functions (`_kanonski_nalazi`,
`_kanonski_prioritet_i_rizici`, added Sigma Sprint 005, 2026-08-06) are
NOT yet DC-numbered entries in `DECISION_REGISTRY.md` — the registry was
last updated 2026-08-04 (Program Gamma), two days before Sigma 005 shipped.
This is a pre-existing gap, not a GPT-5.1 problem, but any GPT-5.1 work
that touches Case Commander should close it as a byproduct (flagged for
Agent 8 / Phase 3, not fixed here — Phase 1 is analysis-only).

### 1.4 The structural enforcement point neither of the above needed to know about
`shared/ai_client.py::_patch_prompt_guard` (line 268) intercepts
`Completions.create`/`AsyncCompletions.create` **at the OpenAI SDK class
level**, before any router-specific code runs — every one of the ~130 call
sites in the app is guarded and provenance-logged (`shared/ai_provenance.py`
+ `security/ai_forensics.py`) without needing to individually opt in. Tested
by `tests/test_sec003_llm_wrapper.py` (12 tests: patch installed once and
shared across independently-constructed clients, injection blocking,
multimodal content-part extraction, system-only messages skipped, etc.).
**This is the single most important existing asset for GPT-5.1 testing**:
a model swap to GPT-5.1 does not require re-wiring per-call security or
provenance capture, because both are attached to the SDK class, not to the
model string. Any GPT-5.1 test plan should assume this guard fires
identically regardless of which model name is passed in `kwargs["model"]`,
and should add exactly one test confirming that (Section 2.3).

SDK version confirmed: `openai==2.29.0` (`requirements.txt` line 4).

---

## 2. Mandatory test categories

### 2.1 Hallucination testing
**Pattern**: feed a fixed, minimal, fully-known context (a synthetic
`ctx`/`podaci` dict, same shape as `_ctx()` in
`test_sigma_sprint005_commander_consolidation.py` line 57) to any GPT-5.1
call site, mock the model response with a deliberately-poisoned answer
(a fact, ID, or number NOT present in the input), and assert the poisoned
claim never reaches the returned payload as anything other than a
`gpt_advisory`-tagged, evidence-less field — or, where a grounding
validator exists (Section 1.2), assert it is flagged/dropped.
- For any field wrapped in `canonical_field`/`gpt_advisory_field`
  (`shared/commander_schema.py`): assert `source != "gpt_advisory"` never
  happens for a value that didn't come from a canonical function call —
  this is a code-path test (mock the deterministic function, assert its
  return value round-trips unchanged), not a model-behavior test.
- For any field that cites an ID (predmet, DOK-XX, graph node): assert the
  matching `validate_*_reference` function is actually invoked on the
  GPT-5.1 output path, with a test where the mocked GPT response cites an
  ID outside the known set and the flag list comes back non-empty.

### 2.2 Evidence verification
Every response object returned from an endpoint that mixes canonical and
GPT-advisory data must pass a **shape assertion**: every top-level field
matches `{value, source, evidence, confidence, generated_by, timestamp}`
(mirrors `test_canonical_field_shape`, line 28), AND every field where
`generated_by` is a GPT model name must have `evidence is None` OR
`evidence` points at a canonical source that can itself be independently
re-verified. Recommend a single shared pytest helper (e.g.
`tests/_commander_schema_asserts.py::assert_response_shape(payload)`) so
every future endpoint touching `commander_schema.py` reuses one assertion
instead of hand-rolling the same shape check per test file — this
directly serves the mission's "no AI answer without provenance" rule by
making the check impossible to forget.

### 2.3 Regression testing
Full existing suite (2,791 passed / 1 skipped / 0 failed as of Sigma Sprint
005, per `.vindex_ai_team/METRICS.md`) must be re-run and stay green after
ANY model-string change. Specifically must-not-regress files, found via
grep for `case_commander`, `openai`, and `AsyncMock`/`patch.object` around
GPT calls:
- `tests/test_sigma_sprint005_commander_consolidation.py` — the boundary
  contract itself.
- `tests/test_celina2_predictor_commander_2026_07_24.py` — pre-existing
  Case Commander behavior Sigma 005 deliberately preserved.
- `tests/test_sec003_llm_wrapper.py` — the guard/provenance interception
  layer; must keep intercepting regardless of model name.
- `tests/test_genome_validator.py` — the anti-hallucination validators.
- `tests/test_decision_registry_completeness.py` — canonical-source
  existence tripwire.
- `tests/test_gpt_reranker.py` — a DIFFERENT GPT use case (search
  re-ranking, not case reasoning) with its own fallback-on-error tests
  (`test_gpt_rerank_gpt_error_fallback`, `test_gpt_rerank_invalid_json_fallback`,
  line 72/85) — a reminder that GPT-5.1 rollout is not limited to Case
  Commander; each of the ~90 files a repo-wide grep surfaced with direct
  OpenAI calls is a candidate regression point (full inventory is Agent 1's
  `AI_ARCHITECTURE_MAP.md`, not duplicated here).
- New test to add (not yet implemented, per Phase 1 no-code rule): one
  parametrized test asserting `_patch_prompt_guard`'s interception fires
  for a call with `model="gpt-5.1"` exactly as it does for `model="gpt-4o"`
  — closes the one real gap this analysis found in the guard's own test
  coverage (`tests/test_sec003_llm_wrapper.py` never varies the model
  string).

### 2.4 GPT-4o vs GPT-5.1 comparison methodology
Do NOT run both models live in production and pick a winner by user
exposure — that would make the comparison itself a new, unaudited source
of truth. Recommended staged approach:
1. **Shadow logging** (no user-visible change): for a bounded pilot set of
   call sites, after the real (GPT-4o) call returns and is used normally,
   fire a second, fire-and-forget GPT-5.1 call with identical input, log
   both outputs (reusing `shared/ai_provenance.py`'s existing
   `correlation_id` plumbing to link the pair) but never surface the
   GPT-5.1 output to a user or let it affect any `canonical_field`/action.
2. **Offline replay harness**: a script (explicitly NOT part of the pytest
   suite, since it costs money and calls a live model) that replays a fixed
   corpus of past real `ai_provenance` records' `user_prompt_hash`-linked
   inputs (or, if raw prompts aren't retained, a curated synthetic set)
   through both models and diffs outputs for hallucination-validator
   flag rate, schema-shape compliance, and — where ground truth exists
   (e.g. an already-resolved predmet) — factual agreement.
3. **Promotion gate**: a model only moves from shadow to live once (a) the
   full regression suite in 2.3 passes with the model swapped in for a
   given call site, and (b) the offline replay shows the hallucination
   validator flag rate for GPT-5.1 is not worse than the existing GPT-4o
   baseline for that call site's own historical inputs.

### 2.5 What's mockable-and-fast vs what needs a live model
| Testable now, in CI, mocked, deterministic | Needs a live model, slower, costs money |
|---|---|
| Schema shape (`{value, source, evidence, ...}`) | Actual hallucination *rate* under real GPT-5.1 |
| Prompt-guard/provenance interception fires regardless of model string | Output quality/tone comparison |
| Grounding validators reject an out-of-set reference | Whether GPT-5.1 respects a narrowed prompt's boundary in practice (vs. `_cross_case_analiza`'s prompt simply not asking) |
| Fail-soft behavior on GPT exception (`test_cross_case_analiza_survives_total_gpt_failure_with_canonical_findings`) | Latency/token-cost delta at the new model's pricing |
| Decision Registry existence tripwire | Shadow-mode agreement rate (Section 2.4 step 2) |

Recommendation: the left column runs on every commit (already does, via
`pytest`); the right column runs in the offline replay harness (2.4 step 2)
on a schedule (e.g. weekly, or triggered manually before a promotion
decision) — never inside the standard CI regression suite, matching how
`tests/test_gpt_reranker.py`'s own tests already mock the OpenAI response
rather than calling it live.

---

## 3. Summary for Agent 8 (Implementation Roadmap)

No code or test files should be written from this document directly. The
one concrete near-term action this analysis surfaces for Phase 3/4
triage: (a) add DC-numbered entries to `DECISION_REGISTRY.md` for Sigma
005's canonical functions (pre-existing gap, unrelated to GPT-5.1 but
touches the same files), and (b) add the single missing model-string-
parametrized guard test noted in 2.3. Everything else in this document is
strategy for work that has not yet been authorized.
