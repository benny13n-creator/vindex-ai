# AI Architecture Map — Program Tau, Master Sprint 001, Agent 1

**Scope**: every OpenAI call site in the live application (routers/, services/, shared/, drafting/, nacrti/, klijenti/, app/, api.py, main.py, strategija.py, web3_compliance.py). Test files, one-off scripts (`scripts/`, `diag_*.py`, `ingest_*.py`, `scrape_*.py`, `build_*.py`, `debug_rag.py`), and `security/ai_forensics.py` (consumes provenance, doesn't call GPT) are excluded from the count below but noted where relevant.

**Method**: `grep -rn 'model\s*=\s*"'` across the live-app tree, cross-checked file-by-file. This is a verification pass done fresh for this sprint — no prior sprint's stated call-site count was assumed correct.

## Headline numbers

- **138 distinct call sites** with an explicit `model=` kwarg, across **56 files**. This is close to (and confirms as roughly accurate) the `~130 pozivnih mesta` estimate already written in `shared/ai_client.py`'s own docstring (line 16-17) — that docstring was not blindly trusted, it was independently re-derived.
- **Models observed**: `gpt-4o` and `gpt-4o-mini` only for chat completions (zero occurrences of `gpt-5`, `o1`, `o3` anywhere in live app code — this is a from-scratch integration, not an upgrade of a partial rollout). `text-embedding-3-large` for RAG embeddings (`app/services/retrieve.py:69,486` — the one live-app embedding call site; all other `text-embedding-3-large` hits are in one-off ingest/diag scripts). `whisper-1` (transcription) and `tts-1` (synthesis) in `routers/voice.py`. `rerank-multilingual-v3.0` in `app/services/retrieve.py:1231` is a **Cohere** reranker, not OpenAI — flagged so it isn't miscounted as a GPT call site by later agents.
- **Every one of the 138 sites is structurally intercepted** by `shared/ai_client.py::_patch_prompt_guard()` (patches `Completions.create`/`AsyncCompletions.create` at the SDK class level, before any router import). This single mechanism gives two guarantees for free, regardless of whether the call site's own author knew about them: (1) SEC-003 prompt-injection blocking on every `user`-role message, (2) Mission Atlas AI Provenance capture (`shared/ai_provenance.py` + `security/ai_forensics.py`) — module/operation name, prompt hashes, token usage, latency, correlation id — written for every call, success or failure. This means "does an audit trail exist" is already answered **yes, structurally, for all 138 sites** — GPT-5.1 readiness work does not need to build this from scratch, only verify it still fires correctly under the new SDK surface (Agent 2's scope).

## Per-file inventory (call-site counts, live app only)

| File | Sites | Model(s) | Endpoint(s) exposed |
|---|---|---|---|
| `routers/court_predictor.py` | 7 | gpt-4o ×6, gpt-4o-mini ×1 | `/api/predictor/*` (8 endpoints) |
| `routers/copilot.py` | 7 | gpt-4o-mini (all) | copilot chat/analysis handlers |
| `strategija.py` | 11 | gpt-4o (all) | `/api/strategija/*` |
| `web3_compliance.py` | 9 | gpt-4o (all) | `routers/web3.py` |
| `app/services/retrieve.py` | 8 | gpt-4o-mini ×7, rerank (Cohere, not OpenAI) ×1 | RAG query pipeline (internal, no direct router) |
| `api.py` | 7 | gpt-4o ×3, gpt-4o-mini ×4 | legacy top-level endpoints |
| `main.py` | 5 | gpt-4o ×4, gpt-4o-mini ×1 | legacy top-level endpoints |
| `routers/case_dna.py` | 2 | gpt-4o | `/case-dna`, `/case-dna/compare` |
| `routers/case_commander.py` | 2 (post-Sigma-005) | gpt-4o / gpt-4o-mini | `/commander/*` (see docs/sigma/, already migrated onto canonical sources) |
| `routers/case_intelligence.py` | 1 | gpt-4o | `/api/intelligence/predmeti/{id}/briefing` — see risk note below |
| `routers/drafting.py` | 5 | gpt-4o-mini ×3, gpt-4o ×2 | `/drafting/*` |
| `drafting/router.py` | 1 | gpt-4o | drafting engine core |
| `routers/morning_briefing.py` | 3 | gpt-4o ×1, gpt-4o-mini ×2 | daily briefing (independent synthesis — flagged in Sigma 004, out of that sprint's scope) |
| `routers/multi_agent.py` | 3 | gpt-4o-mini ×1, gpt-4o ×2 | `/multi-agent/run`, `/run-parallel`, `/pipeline` |
| `services/legal_reasoning_engine.py` | 1 | gpt-4o | Legal Reasoning Engine chain generation — citation-grounded (see deep dive) |
| `services/case_pipeline.py` | 3 | gpt-4o-mini | 9-step Case Pipeline auto-classification |
| `services/learning_engine.py` | 3 | gpt-4o-mini ×2, gpt-4o ×1 | Firm DNA / lessons-learned extraction |
| `services/ambient_analyzer.py` | 1 | gpt-4o-mini | ambient/background analysis |
| `services/agent_tasks/precedents_radar.py` | 1 | gpt-4o-mini | scheduled precedent radar |
| `shared/intake_classify.py` / `shared/intake_extract.py` | 2 | gpt-4o-mini | Smart Intake pipeline |
| `nacrti/checklist_engine.py` | 1 | gpt-4o-mini | checklist generation |
| `klijenti/router.py` | 1 | gpt-4o-mini | client-facing endpoint |
| `routers/{cio,client_twin,cross_doc,decision_replay,digital_twin,doc_templates,dokument,evidence,evidence_graph,health_index,hearing_cc,integracije,intake,knowledge_base,knowledge_transfer,memory_graph,oblasti,outcome_intel,precedenti,praksa,profitabilnost,region,strategy_simulator,style_checker,voice,zadaci,zastarelost,zakon_monitoring,corrections}.py` | 1-4 each | gpt-4o / gpt-4o-mini (+ whisper-1/tts-1 in voice.py) | see live-caller signal table below |

*(Full per-line file:line list available via `grep -rn 'model\s*=\s*"' routers/ services/ shared/ drafting/ nacrti/ klijenti/ app/ api.py main.py strategija.py web3_compliance.py` — not reproduced in full here for length; every count above is grep-verified, not estimated.)*

## Deep dives — highest-stakes call sites (read in full, not just grepped)

### `routers/case_commander.py` — already migrated (Sigma 005)
Documented exhaustively in `docs/sigma/CASE_COMMANDER_ARCHITECTURE_MAP.md` / `docs/sigma/CASE_COMMANDER_DECISION_REGISTRY.md`. 6 of 8 former GPT decision surfaces now read `case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py` directly; the 2 remaining GPT calls are tagged `gpt_advisory` via `shared/commander_schema.py`. **This is the reference pattern the rest of this sprint should generalize, not reinvent.**

### `routers/case_intelligence.py::_pozovi_briefing_api` (line 38-49) — **risk flag**
System prompt `_BRIEFING_SYSTEM` (line 53 on) explicitly asks GPT for:
```json
{"sledeci_korak": "<JEDNA najhitnija konkretna akcija>", "razlog": "...", "kljucni_rizici": [...]}
```
i.e. GPT is still asked to **invent a single next action** by synthesizing across Lessons Learned / Firm DNA / Knowledge Profiles / Court Predictor / Decision Log — the exact shape of decision Program Sigma has been systematically removing from Case Commander. This module (`Case Intelligence Briefing`, `POST /api/intelligence/predmeti/{id}/briefing`) is a **separate file from Case Commander** and was **not in Sigma 005's scope** (mission named Case Commander specifically). Read the code as it stands today, not from memory: the prompt has not been changed to a canonical-read pattern. Whether some caller-side logic elsewhere discards or re-ranks this `sledeci_korak` against `case_actions` before display was not traced in this pass (out of Agent 1's scope — this is a mapping deliverable, not a fix). **Flagging for Phase 2/3 synthesis and Agent 5 (Legal AI Governance)**: this is a second, still-live "AI invents the next step" surface outside Case Commander's now-closed scope, and should not be assumed already fixed just because a same-named class of bug was fixed elsewhere in a prior sprint.

### `services/legal_reasoning_engine.py::_build_reasoning_prompt` / `_pozovi_reasoning_api` (line 137-199)
The **strongest existing anti-hallucination pattern in the codebase**, worth Agent 5/8 studying as the model for how GPT-5.1 reasoning should be grounded: citations are built as `SOURCE-n` identifiers **exclusively** from `izvori` (real, already-retrieved `{zakon, clan, score}` tuples from `retrieve.py`), never from free text. Raw retrieved passages (`context_docs`) are given as unlabeled "background reading only" — GPT may read them to understand the law but can only cite via a `SOURCE-n` id, and any citation GPT invents that isn't in the real list "has no valid SOURCE-n to attach to and is dropped downstream" (comment at line 143-145, corroborated by `generate_reasoning_graph`'s chain validation, not independently re-verified line-by-line in this pass). This is evidence-grounding-by-construction, not by GPT's own good behavior — the same design principle Case Commander's `commander_schema.py` now enforces structurally.

### `strategija.py` (11 sites) and `web3_compliance.py` (9 sites)
Highest per-file call counts outside the RAG pipeline. Not deep-read line-by-line in this pass (budget prioritized case_commander/case_intelligence/legal_reasoning_engine as the decision-critical ones). Flagged for Agent 3 (context engineering) and Agent 5 (governance) to examine directly — 11 and 9 call sites respectively in a single file each is itself a signal worth checking for internal duplication, the same pattern Case Commander had.

## Live-caller signal (candidate dead code — NOT confirmed, grep-only pass)

Sigma 005 proved (via full frontend grep + 2 independent forks) that all 8 Case Commander GPT surfaces had zero live callers. The same check was **not** done exhaustively for the other 137 call sites in this pass — only a fast, single-pass grep of `static/vindex.js` for each router's own endpoint path fragment, which is directional, not conclusive (generic path fragments like `/simulacija` or `/preporuka` produce noisy matches). Zero-hit results below are **candidates for a follow-up dead-code check**, not confirmed dead:

**Zero grep hits** (worth a real Sigma-005-style verification pass before anyone assumes they're live): `klijenti/{id}/analiziraj`, `/replay` (decision_replay.py), `digital-twin` path segment, `/cross-exam` (hearing_cc.py), `knowledge-transfer/profili`, `/dodaj-vezu` + `memory-graph` (memory_graph.py), `/oblasti/krivicno|privredno|radno`, `/region/ai-savet|podrska`, `/style-checker` + `/profil/gradi`, `/rokovi/guardian`, `/zakon-monitoring` + `/impact-analiza`, `/knowledge/save|search` (knowledge_base.py), `/multi-agent` (though `/run-parallel` got 1 hit — internally inconsistent, needs a real look), `/strategy-simulator` + `/nova-partija` + `/sledeci-potez`, `/hearing-prep`.

**Confirmed-live signal** (multiple specific hits): `case-dna` (16), `zastarelost` (15), `precedenti` (8), `outcome-intel` (8), `profitabilnost` (7), `battle-report` (5), `generisi`/doc-templates (4), `simulacija` (4, ambiguous between digital_twin and strategy_simulator — not disambiguated in this pass).

If Program Tau's later phases (Phase 4 implementation) touch any of the zero-hit files, treat "is this endpoint actually reachable from the UI" as an open question requiring the same rigor Sigma 005 applied to Case Commander — do not assume live, do not assume dead, verify.

## What this deliverable does NOT claim

- It does not claim to have read every one of the 138 call sites' full prompt text — only grep-verified their existence, model, and file location, plus deep-read the ~5 highest-stakes ones.
- It does not claim the zero-grep-hit endpoints above are confirmed dead — only that they're candidates, on weaker evidence than the Sigma 005 Case Commander finding.
- It does not evaluate GPT-5.1 API compatibility (Agent 2's scope), context completeness (Agent 3's scope), security/data-flow (Agent 4's scope), or cost (Agent 6's scope).
