# GPT-5.1 Integration Analysis — Program Tau, Master Sprint 001, Agent 2

**Scope**: OpenAI SDK implementation as it exists in the repo today, and what a GPT-5.1 (or successor) integration would actually require. Analysis only — no code changed.

---

## 0. CRITICAL — verify the target model is still current before any implementation work

A web search (2026-08-06, see Sources) indicates **GPT-5.1 was retired from ChatGPT on 2026-03-11**, with the current model line at GPT-5.3/5.4/5.5. Sources disagree on the *API's* lifecycle specifically:

- OpenAI's own Help Center article states GPT-5.1 "will continue to be available through the OpenAI API" with advance notice before any future API retirement.
- A third-party blog (dev.to, lower authority, unverified against a primary source in this session) claims API calls to `gpt-5.1` now silently fall back to a newer model with no error and no version signal.

**I could not verify which of these is correct against an authoritative source within this task's scope.** This is a material fact for the mission: if the model this sprint is named after is being (or already was) silently routed away from at the API layer, that changes the risk calculus of "compatibility gap" analysis below, and the founder should confirm the exact model ID intended (a dated snapshot like `gpt-5.1-2026-XX-XX` if one exists, not a generic alias) directly against `https://platform.openai.com/docs/deprecations` before Phase 4 implementation starts. **Do not treat this analysis as confirmation that `gpt-5.1` is the right model string to target.**

---

## 1. Pinned SDK version

`requirements.txt:4` — `openai==2.29.0`. This is a current v2.x SDK line; it supports both the Chat Completions and Responses APIs at the client-library level. The pinned version itself is not a blocker for a newer model — no SDK bump is needed to *call* GPT-5.1-class models, since new models under an existing SDK major version are normally just a `model=` string change at the transport level.

## 2. API surface in use: Chat Completions only, no Responses API

Grepped the full repo for `.responses.create(` — **zero hits**. Every one of the ~90 files that make OpenAI calls uses `client.chat.completions.create(...)` (or `AsyncCompletions`/`Completions` via the shared wrapper). Confirmed via direct reads of `routers/case_commander.py:627`, `routers/case_intelligence.py:41`, `main.py:4070-4074`, among others.

This matters structurally, not just stylistically: **`shared/ai_client.py`'s `_patch_prompt_guard()` (lines 268-389) monkey-patches `openai.resources.chat.completions.completions.Completions.create` / `AsyncCompletions.create` at the class level** — this is the single choke point that (a) runs every outbound prompt through Prompt Guard (SEC-003) before it reaches OpenAI, and (b) captures AI Provenance (Mission Atlas, 2026-08-03) for every call. **This patch targets the Chat Completions classes specifically. It does NOT patch `openai.resources.responses`.** If any future code — including a GPT-5.1 migration — calls `client.responses.create(...)` instead, it would bypass both Prompt Guard and AI Provenance capture entirely, silently. This is the single most important integration-compatibility finding in this report and should be treated as a hard constraint: **either GPT-5.1 stays on Chat Completions, or `shared/ai_client.py` gets a second patch for the Responses resource before any Responses-API call site is added.**

## 3. Structured outputs: loose JSON mode is the dominant pattern, not strict schema enforcement

`response_format={...}` appears at 60 call sites (grep, `*.py`). Sampled directly:

- `routers/case_commander.py:635`, `routers/case_intelligence.py:47`, `main.py:4073` and the overwhelming majority of the 60 sites use **`response_format={"type": "json_object"}`** — OpenAI's older "loose JSON mode," which only guarantees syntactically valid JSON, not schema conformance. The model can still omit required keys, use wrong types, or invent extra fields; nothing at the API layer stops it.
- `main.py:2445-2459` (and 3 more schemas at lines 2493, 2538, 2583) is the **one exception**: uses `"type": "json_schema"` with an actual JSON Schema body — but **`"strict": False`** is set explicitly (`main.py:2449`). Non-strict `json_schema` mode is still advisory, not enforced by the API; it does not give the hard guarantees OpenAI's *strict* structured outputs mode provides.
- No call site in the ~130 production call sites uses `strict: True` or the SDK's `.parse()`/Pydantic `response_model=` convenience path (confirmed via targeted grep for `beta.chat.completions.parse` / `response_model=` — zero hits outside this search's own false positives).

**Implication for GPT-5.1**: if the goal is to reduce hallucination risk in the "advanced reasoning layer," strict structured outputs (`strict: True` + real JSON Schema) is a proven, available lever that this codebase has never actually turned on anywhere. That is a candidate for Phase 4, but only where downstream code already expects the shape it would enforce — see Agent 7's test strategy and Agent 5's boundary policy before touching any specific call site.

## 4. Tool/function calling: not used in any legal-reasoning call site

Grep for `tools=[` / `tool_choice` across `*.py`: the only hit is `services/voice_orchestrator.py`, which is the voice-interaction subsystem, not part of Case Genome/Evidence Chain/Case Commander/Case Readiness. Every legal-analysis GPT call in this codebase is single-shot prompt-in/JSON-out. GPT-5.1 does not require tool calling to function; this is a "nothing to migrate" finding, not a gap.

## 5. Streaming: not used anywhere relevant

Grep for `stream=True`: one hit, `scripts/ingest_ofac_sdn.py`, an offline ingestion script unrelated to case-facing AI calls. No user-facing endpoint streams a GPT response. No compatibility concern.

## 6. Model strings: hardcoded literals at ~130 call sites, not centralized

Every call site hardcodes its own model string — `"gpt-4o"` or `"gpt-4o-mini"` — directly in the `chat.completions.create(model=...)` call (confirmed via grep sample of 100+ matches spanning `api.py`, `main.py`, every file in `routers/`, `services/`, `shared/`). **There is no single constant or config value that controls "the model" application-wide.** This is directly relevant to the mission's own explicit constraint ("Ne menjati model globalno" / do not change the model globally): today, that constraint is satisfied *by construction* — there is no global switch to accidentally flip. The cost is that adopting GPT-5.1 selectively (the mission's actual goal — GPT-5.1 as a reasoning layer *above* specific deterministic systems, not everywhere) means editing call sites one at a time, deliberately, which is slower but matches the mission's own "no blanket swap" instruction. Introducing a central model-routing constant is itself a design decision Agent 8's roadmap should weigh, not something to do incidentally here.

## 7. Compatibility gaps / required changes for a GPT-5.1 adoption (repo-verified only)

1. **No code change is required to call a `gpt-5.1`-class model string through the existing Chat Completions call sites** — the transport layer (`client.chat.completions.create(model=..., messages=..., response_format=...)`) is model-agnostic at the SDK level. This is a repo-verified structural fact, not a claim about the model's behavior or quality.
2. **Do not add any `client.responses.create(...)` call site without first extending `shared/ai_client.py`'s guard/provenance patch to cover the Responses resource** — otherwise that call site silently loses SEC-003 prompt-injection protection and Mission Atlas provenance logging, the two structural guarantees the rest of this codebase relies on.
3. Adopting strict structured outputs (`strict: True`) at any given call site is possible today with the pinned SDK, but is a per-call-site opt-in — there's no evidence any code currently depends on OpenAI enforcing schema conformance, so this is an *available improvement*, not a blocker.
4. Whatever model string is ultimately chosen must be confirmed against OpenAI's live deprecations page per Section 0 above — this is a prerequisite, not a nice-to-have, given the retirement signal found.

---

## Answer to the three questions asked

- **Pinned SDK version**: `openai==2.29.0` (`requirements.txt:4`).
- **API surface in use**: Chat Completions exclusively (`chat.completions.create`), zero use of the Responses API, across all ~90 files with OpenAI calls.
- **Drop-in vs. deeper change**: For the transport call itself, a **drop-in model-string change** at each chosen call site — the SDK version and API surface already support it. The real risk is *architectural*, not transport-level: (a) confirm the model string is actually current (Section 0), and (b) if GPT-5.1's own API is Responses-API-preferred going forward, migrating call sites there would silently bypass Prompt Guard and AI Provenance unless `shared/ai_client.py` is extended first. Neither of those is a "small" change — they're exactly the kind of thing Phase 3 should classify as critical-if-in-scope.

---

## Sources (external claims, Section 0 and 7.4 only — everything else in this report is repo-verified)

- [GPT-5.5 Model | OpenAI API](https://developers.openai.com/api/docs/models/gpt-5.5)
- [Retiring GPT-4o and other ChatGPT models | OpenAI Help Center](https://help.openai.com/en/articles/20001051-retiring-gpt-4o-and-other-chatgpt-models)
- [Deprecations | OpenAI API](https://developers.openai.com/api/docs/deprecations)
- [GPT-5.1 Was Retired on March 11 — Here's What Broke in Your LLM App (dev.to, third-party, unverified)](https://dev.to/clawgenesis/gpt-51-was-retired-on-march-11-heres-what-broke-in-your-llm-app-1eep)
