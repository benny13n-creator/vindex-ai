# Program Alpha — Domain Inventory: Case Genome / Memory Graph / Firm Brain / Strategy Engine

Read-only investigation. No code changed.

## Decision table

| Decision | Canonical origin | Consumers | # implementations |
|---|---|---|---|
| Case strength (`snaga_predmeta_procent`/`snaga_predmeta`) | `shared/genome_validator.py::compute_snaga_score` (deterministic, from LLM-extracted `snaga_faktori`) | Case Genome panel, `routers/case_dna.py` | **2 — see Finding 2 below** |
| Evidence strength proxy (`snaga_dokaza`/`snaga_pct`) | `services/risk_engine.py::calculate_procesni_rizik` (deterministic, from `predmet_dokazi.snaga` tally) | Matter Intel widget (`static/vindex.js:18455-18457`), `routers/matter_intel.py` | 1 (but see Finding 2 — overlaps in concept with the row above) |
| Process risk (`procesni_rizik`/`health_score`) | `services/risk_engine.py::calculate_procesni_rizik` | Dashboard, Matter Intel, CCC (per Nexus's own prior consolidation) | 1 — canonical, confirmed single implementation |
| Case Pipeline trigger | `on_predmet_kreiran` handler (Event Bus), fires the 9-step pipeline once at case creation | New predmet creation only | 1 trigger point confirmed — no other code path independently fires pipeline-shaped work (grepped for `run_case_pipeline`/pipeline step function names outside the handler; none found) |
| Firm institutional-memory context for AI | **See Finding 1 — 2 independent implementations** | Copilot/RAG (live); nothing (dead) | **2** |
| Strategy Engine's 9 endpoints' AI logic | Each endpoint delegates to a dedicated `_sync` function (`red_team_analiza_sync`, `litigation_simulator_sync`, etc.) — not inlined per-endpoint | `routers/strategija.py` | 1 per module, correctly delegated — not a duplicate (see note below) |
| Memory Graph | `routers/memory_graph.py` | Nobody — confirmed still fully isolated | 1, zero consumers (unchanged from Nexus/Olympus) |

## Finding 1 (Critical) — Two independent "firm memory for AI" implementations, one dead, one live and cruder

- **Live**: `api.py::_fetch_firm_memory_context` (lines 1253-1330+, called at `api.py:2916` and `api.py:3020` from Copilot). Queries `memory_entries` (general) + `partner_profiles` only. Own inline keyword-based relevance ranking (`_mem_relevance_score`), `confidence >= 0.5` filter, top-5.
- **Dead**: `routers/firm_memory.py::kontekst_za_ai` (`GET /kontekst-za-ai`, lines 252-350+). Own docstring: *"Poziva se iz AI pipeline-a pre generisanja odgovora. Output se injectuje u system prompt."* — **false as written**: grepped the entire repo (`.py`, `.js`) for any caller of this endpoint — **zero callers found**. This version is strictly more complete: it also reads `judge_patterns` and `client_memory` tables (judge win-rate, client settlement preferences, risk profile) that the live `api.py` version never touches at all.

**Consequence**: Copilot's actual AI answers never benefit from judge/client institutional memory, even though a canonical-looking, more complete retrieval implementation for exactly that already exists in the codebase — it's just never called. This is precisely the "No Hidden Logic" + "No Duplicate Decisions" violation this mission's charter names: business logic (context retrieval for AI) lives ad hoc in `api.py` instead of the dedicated `routers/firm_memory.py` module that already claims (falsely) to be the canonical entry point.

## Finding 2 (Medium) — Two different "how strong is this case" numbers, no explicit differentiation

`compute_snaga_score` (Genome) and `calculate_procesni_rizik`'s `snaga_dokaza`/`snaga_pct` (Risk Engine) answer a closely related question — "how strong is the evidence/case" — with different formulas and different inputs (Genome: LLM-extracted weighted factors; Risk Engine: raw `predmet_dokazi.snaga` tally). Risk Engine's number is directly rendered to the user (`static/vindex.js`'s Matter Intel widget) as `snaga_dokaza`, with no label distinguishing it from Genome's own, richer `snaga_predmeta_procent` shown elsewhere for the same predmet. A lawyer could see two different "strength" signals for the same case with no explanation of why they differ. **Not a formula bug** — Risk Engine's docstring is explicit this is a fast, always-available proxy, not a replacement for Genome's deeper analysis — but the *lack of UI differentiation* is a real source-of-truth-perception risk worth fixing (e.g., relabeling Matter Intel's field to "Osnovna procena dokaza" vs. Genome's "AI analiza snage predmeta").

## No new violations found

- Case Pipeline: single trigger point confirmed, no competing trigger.
- Strategy Engine: the 7-step wrapper (validate → audit → praksa-context → AI call → bill → error-handle) is repeated per endpoint, but the actual AI logic is properly delegated to named `_sync` functions, not copy-pasted — this is boilerplate repetition, not duplicated business logic, and out of this mission's stated scope (which targets business-decision duplication, not code-shape repetition).
- Memory Graph: still confirmed fully isolated, unchanged.
- No new magic-number/heuristic duplication found in Genome/Strategy beyond what prior missions already documented (Strategy Engine's ungrounded confidence — Keystone K-3, out of this fork's scope, already tracked as `KEYSTONE-004`).

## Prioritized recommendation

**Highest priority**: retire `routers/firm_memory.py::kontekst_za_ai` OR make it the actual canonical implementation and have `api.py::_fetch_firm_memory_context` call it instead of reimplementing retrieval inline — the latter is preferable since `kontekst_za_ai`'s data (judge/client memory) is strictly more valuable and currently completely unused by the one live AI consumer that needs exactly this kind of context.

## Summary
**Decisions mapped**: 7. **New duplicates found**: 2 (1 Critical — dead-vs-live firm-memory retrieval; 1 Medium — case-strength UI perception overlap). **Highest-priority canonicalization target**: unify `api.py::_fetch_firm_memory_context` and `routers/firm_memory.py::kontekst_za_ai` into one real implementation, wired into Copilot, incorporating judge/client memory that's currently extracted, stored, and never used.
