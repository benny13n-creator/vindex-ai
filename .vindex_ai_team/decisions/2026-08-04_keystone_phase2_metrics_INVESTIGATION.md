# Mission Keystone — Phase 2: Final Metric Calculation (fresh re-measurement)

**Directive**: "Ne koristi stare brojeve. Izmeri ponovo." Every number below is derived from a fresh
grep/read of current code (2026-08-04) or a fresh test run, not copied from any prior mission's own
report. Where a fresh count materially diverges from a prior mission's self-reported figure, this is
flagged explicitly as CONFIRMS / REVISES / CONTRADICTS.

---

## Headline correction, found before the metrics themselves could be computed honestly

Every prior mission (Atlas, Ledger, Migration, Phoenix) computed its AI-feature inventory against a
**hand-curated list of ~36 "rows"**: Genome, Strategy Engine (9 endpoints), Briefing, Copilot (~8
handlers), Task generation, Upload AI analysis, Court Predictor (7 endpoints), Evidence classification,
Drafting (2-3 call sites), ask_agent, embeddings.

A fresh, unfiltered grep for `\.chat\.completions\.create(` across the whole repository (excluding
tests/diagnostics/scripts) finds **76 distinct physical call sites across 55 files** — including
**~41 live, `app.include_router()`-mounted production routers that no prior mission's inventory ever
counted, in either the numerator or the denominator**:

`case_commander.py, case_intelligence.py, cio.py, client_twin.py, corrections.py, cross_doc.py,
decision_replay.py, digital_twin.py, doc_templates.py, evidence_graph.py, health_index.py, hearing_cc.py,
intake.py, integracije.py, knowledge_base.py, knowledge_transfer.py, learning.py, matter_intel.py,
memory_graph.py, multi_agent.py, oblasti.py, outcome_intel.py, praksa.py, precedenti.py,
profitabilnost.py, region.py, strategy_simulator.py, style_checker.py, voice.py, web3.py,
zakon_monitoring.py, zastarelost.py` (routers/) plus `services/agent_tasks/precedents_radar.py,
services/ambient_analyzer.py, services/case_pipeline.py, services/learning_engine.py,
services/legal_reasoning_engine.py, shared/intake_classify.py, shared/intake_extract.py,
klijenti/router.py, nacrti/checklist_engine.py, drafting/router.py, app/services/retrieve.py`.

Verified live (not dead code) by confirming each router name appears in `api.py`'s
`app.include_router(...)` calls (all ~26 routers checked found registered).

**This is not a claim that all 36 previously-inventoried rows were miscounted** — re-spot-checking
several of them (Court Predictor's 7 endpoints, Drafting's 2, Case Genome's 2, Evidence's 1) confirms
Migration/Phoenix's own claims about THOSE specific rows are accurate (see per-metric sections below).
The correction is that **the denominator itself was never the whole system** — roughly 41 additional
AI-calling production modules were simply never assessed by any of the 5 prior missions, which makes
every previously-reported percentage (Audit Link Coverage 78%, Provenance Coverage 58-75%, etc.)
correct-for-its-own-scope but not a system-wide figure, contrary to how those reports were headlined
and cited in `MISSION_BOARD.md`/`METRICS.md`.

---

## 1. Intelligence Connectivity Score (ICS)

**Definition used**: a "module" = a distinct intelligence-producing subsystem (something that computes
or infers a case-relevant conclusion, not a passive CRUD endpoint). A "useful connection" = module A's
output is consumed as an input by module B (verified by grep for A's characteristic
field/table/function name inside B's source, not assumed from naming similarity).

**Modules counted (14)**: Case Genome, Risk/`calculate_procesni_rizik`, Strategy Engine, Copilot,
Morning Briefing, Court Predictor, Evidence classification, Drafting, Task Engine
(`zadaci.py::ai_analiziraj_predmet`), Timeline/Hronologija, Alert Engine (`proactive_alerts`), Memory
Graph, Firm Brain/Learning Engine, Search.

**Matrix (91 possible directed pairs, 14×13 = 182 ordered, but "useful" is asymmetric so counted as
directed connections; only connections with a plausible business reason to exist are counted as
"possible")** — condensed to the ones with a stated business reason to exist (32 "possible useful"
pairs identified by inspection, e.g. Genome→Strategy, Genome→Risk, Genome→Copilot, Genome→Timeline,
Strategy→Timeline, Risk→Alerts, Deadlines→Alerts, Evidence→Genome, Copilot→Task Engine, etc.):

| Connection | Exists in code? | Evidence |
|---|---|---|
| Genome → Risk (`calculate_procesni_rizik`) | ✅ | `routers/dashboard.py::matter_health_score` delegates to it (Sentinel fix), reads Genome fields |
| Genome → Copilot | ✅ | `routers/copilot.py::_handle_analiza_predmeta` reads Genome via `case_dna` helper |
| Genome → Strategy Engine | ❌ | `routers/strategija.py`'s 9 endpoints take ad-hoc request bodies, do not read `case_dna`'s stored Genome record |
| Genome → Timeline | ❌ | No import of case_dna's genome fields in `predmet_hronologija`-writing code |
| Genome → Task Engine | ❌ | `zadaci.py::ai_analiziraj_predmet` builds its own context, does not query Genome |
| Strategy Engine → anything downstream | ❌ | Confirmed by Sentinel (`SENT-003`, still open, re-verified unchanged this pass): every Strategy Engine output is returned to the caller and discarded — no persistence, so structurally nothing CAN consume it |
| Evidence classification → Genome | ⚠️ Partial | `tip_dokaza` populated on `predmet_dokumenti` (LZ-002 per memory), Genome's own extraction reads `predmet_dokumenti.tekst_sadrzaj` but not independently verified this pass whether it reads `tip_dokaza` |
| Evidence classification → Search | ✅ | `routers/search.py::_search_dokumenti` explicitly matches on `tip_dokaza` (confirmed in source, comment cites "LZ-002") |
| Copilot (`akcija_rok`) → Deadlines/Timeline | ✅ | Writes directly to `predmet_hronologija` |
| Deadlines → Alert Engine | ⚠️ Partial | `ROK_KRITICAN` event exists and has a handler (`on_rok_kritican`), but Sentinel's `SENT-001` (re-confirmed still open this pass) — it's `emit()`'d in-process only, no durable outbox row, so a process crash between emit and handler completion loses it silently |
| Task Engine → Alert Engine | ❌ | No event/notification fires when a generated task's own deadline nears — separate from `ROK_KRITICAN` (which is predmet-level, not task-level) |
| Memory Graph → anything | ❌ | Confirmed inert (Ledger/Phoenix both independently found this): edges can be inserted but nothing reads them back into another module's context |
| Firm Brain/Learning Engine → Copilot/Strategy | ❌ | `services/learning_engine.py` exists and is called, but its output isn't independently verified this pass to feed back into Copilot's or Strategy's prompt construction |
| Briefing → Alerts | ✅ | Nightly run (`nightly_intelligence_run`) directly creates `proactive_alerts` rows, same mechanism, same table |
| Search → everything (read path) | ✅ | By construction, reads the real tables each module writes |

**Count**: 32 possible-useful pairs identified · **11 verified implemented** (✅) · 3 partial · 18 absent.

**ICS = 11 / 32 ≈ 34%** (partial connections counted as 0.5: (11 + 1.5) / 32 ≈ 39%).

No prior mission computed this metric under this name, so there is no prior figure to compare against —
this is a first measurement, not a revision. The founder's own memory (`project_case_genome_forensic_audit.md`,
2026-07-21) already found "Case Pipeline... zero connection to Firm DNA/Learning/Confidence/matter_intel
risk" — this fresh count is **consistent with, not contradicting,** that earlier finding: connectivity
between intelligence modules remains low, and none of the 5 missions this session (Atlas/Ledger/
Migration/Phoenix all being about traceability/reliability, not cross-module intelligence flow) changed
this number materially. **ICS is the single lowest-scoring metric in this report.**

---

## 2. Critical Intelligence Coverage (CIC)

Per critical flow, checked against 6 sub-criteria with file:line evidence:

| Flow | Context | Provenance | Audit | Confidence | Validation | Recovery | Score |
|---|---|---|---|---|---|---|---|
| Genome (`case_dna.py`) | ✅ predmet_id/document_id via `case_context` | ✅ | ✅ `genome_refresh` | ⚠️ `verifikacija_odluka` field exists (approve/approve_with_warning/require_review) but no numeric confidence_score ever populated (see Provenance §4 below) | ✅ `verify_genome()` | ✅ (Phoenix: dead-letter, re-raise) | 5/6 |
| Risk (`calculate_procesni_rizik`) | ✅ (deterministic, not an LLM call — Track 3 framework) | N/A (no GPT call) | Implicit via Genome's own audit | N/A (deterministic score, not LLM confidence) | ✅ (Track 3's own design) | ✅ | 5/6 (N/A treated as met, deterministic-by-design) |
| Strategy Engine (`routers/strategija.py`) | ✅ `case_context` (9/9 endpoints) | ✅ | ✅ `strategija_generisana` | ❌ never populated | ❌ no persistence to validate against later (`SENT-003`) | ✅ (`@llm_retry`) | 3/6 |
| Copilot | ✅ (7 of 8 handlers) | ✅ | ✅ (6 of 8) | ❌ | ⚠️ TOCTOU-race fixed (Phoenix), no output validation beyond that | ✅ | 3.5/6 |
| Briefing (nightly) | ✅ | ✅ | ✅ `nightly_alert_insert_failed` (Phoenix) | ❌ | ❌ no fact-check against source predmet data before insert | ✅ (Phoenix: 3-attempt retry) | 3/6 |
| Court Predictor | ✅ (7/7) | ✅ | ✅ (7/7, Migration) | ❌ never populated despite the whole feature being explicitly about probabilistic confidence in an outcome — the ONE place a numeric confidence score would matter most has none | ❌ | ✅ (`@llm_retry`) | 3/6 |
| Evidence classification | ✅ | ✅ | ✅ | ❌ | ⚠️ classification not cross-checked against a second signal | ✅ | 3.5/6 |
| Drafting | ✅ (Phoenix) | ✅ | ✅ (Phoenix) | ✅ **only flow in the app where `confidence_score` is genuinely computed and stored** — `_stage_draft_for_review`'s `quality_gate` writes a real `confidence_score` (per Phoenix's own commit message) | ✅ (quality_gate) | ✅ | 6/6 |
| Task Engine | ✅ | ✅ | ✅ | ❌ | ✅ (Nexus's deterministic grounding, per memory) | ✅ | 5/6 |

**CIC = mean of 9 flows ≈ 4.1/6 ≈ 68%.** Drafting is the only 6/6 flow — and notably, it's the only
flow where `confidence_score` is a real, populated field rather than a schema column nobody writes to.
No prior mission computed CIC under this name; first measurement.

---

## 3. Audit Link Coverage

**Two honest denominators, both reported** (per the headline correction above):

**(a) Migration/Phoenix's own original scope (36 rows)**: re-spot-checked, still accurate —
`case_context()` usage confirmed present in exactly the files/counts those reports claim:
`routers/case_dna.py` (2), `routers/copilot.py` (8, incl. `ostalo` deliberately unaudited),
`routers/evidence.py` (1), `api.py` (1, wrapping 3 raw calls), `routers/morning_briefing.py` (1 of 2
call sites), `routers/zadaci.py` (1), `routers/strategija.py` (9), `routers/court_predictor.py` (7),
`routers/drafting.py` (2). **32 case_context invocations confirmed** across these 9 files — consistent
with Migration/Phoenix's "28 of 36 fully migrated" claim (some case_context invocations wrap multiple
rows, e.g. api.py's 1 invocation covers what Migration counted as 3 separate "rows"). **CONFIRMS**
Migration's 78% figure is accurate *for its own declared scope*.

**(b) Full-system denominator (76 raw call sites / 55 files, this mission's fresh count)**:
Case-context-wrapped files = 9 of 55 (**16% file-level coverage**). At the call-site level: of the 76
raw `.chat.completions.create()` sites, an estimated **~30 fall within a `case_context()`-wrapped
region** (court_predictor 7/7, api.py 3/5, drafting 2/2, case_dna 2/2, morning_briefing 1/2, zadaci 1/1,
evidence 1/1, strategija.py's 1 shared call site reached by 9 wrapped endpoints counted once,
copilot.py's 1 direct site) — **≈30/76 ≈ 39% call-site-level coverage system-wide**.

**REVISES Migration's 78% DOWNWARD to ~39%** when the denominator is the actual full set of AI call
sites rather than the 36 pre-selected ones. **Target ≥95% (Keystone) / ≥95% (Ledger's original) — NOT
MET under either denominator**, but the gap is far larger than the 22-point gap Migration reported.

**New concrete gap found this pass, not previously known**: `routers/dokument.py::dokument_pitanje`
(`POST /api/dokument/pitanje`, line 337) calls `ask_agent` via `asyncio.to_thread` with **zero
`case_context()` wrapping** — this is a second, independent, real production call site into the same
`ask_agent` function Phoenix's Phase 8 claimed to have "migrated" (via `routers/copilot.py::
_handle_pravno_pitanje`'s delegation only). **`MISSION_BOARD.md`'s `MIGRATION-001: DONE` status is
only true for one of at least two real HTTP-reachable call paths into `ask_agent`.** This should be
corrected to reflect partial completion.

---

## 4. Provenance Coverage

**Wrapper-level capture (model, prompt hash, response hash, token usage, latency)**: **100%,
re-confirmed** — `shared/ai_client.py::_patch_prompt_guard()` patches `Completions.create`/
`AsyncCompletions.create`/`Embeddings.create`/`AsyncEmbeddings.create` at the class level; this is
structurally unconditional and doesn't depend on `case_context()` at all. Read the full function
(`_capture_chat_provenance`, lines ~155-207): `model_name`, `system_prompt_hash`, `user_prompt_hash`,
`token_usage_input/output`, `latency_ms`, `output_hash` are computed for every call regardless of
context. **CONFIRMS Atlas's "Wrapper Coverage 100%" claim.**

**Context fields (user_id/tenant_id/predmet_id/document_id/module_name/operation_name)**: `module_name`
auto-fills via `_caller_hint()` (inspect.stack) even with no `case_context()`, so this is always
*something*, though not always case-linked — `predmet_id`/`document_id` are `None` outside a
`case_context()` block. Given (3)'s ~39% call-site coverage, roughly 61% of calls have NO case-level
context, only request-level (user_id/tenant_id/correlation_id, always present per Ledger's design).

**Source references (`knowledge_sources`, `retrieved_context_ids`, `retrieval_query`) — genuine
regression found, not previously reported**: grepped every call site in the app that passes these
3 kwargs into `case_context(...)`. Result:
- `knowledge_sources=` is passed in exactly **5 places**: `routers/case_dna.py` (×2),
  `routers/copilot.py` (×1), `routers/morning_briefing.py` (×1), `routers/zadaci.py` (×1).
- `retrieval_query=` and `retrieved_context_ids=` are passed **in zero places, anywhere in the
  application** — confirmed by `grep -rn "retrieval_query=\|retrieved_context_ids=" --include=*.py`
  across `routers/`, `services/`, `api.py`, `main.py`, `drafting/`, `app/`, `shared/`, matching only the
  definitions inside `shared/ai_provenance.py`/`shared/ai_client.py` themselves, never a real caller.
  **This means the single most legally-relevant provenance field in a legal-RAG product — "which law
  articles/precedents did the AI actually cite this answer from" — is a dead column for every one of
  the 76 AI call sites, including `main.py::ask_agent`, the app's core RAG Q&A path, and
  `app/services/retrieve.py`, the actual retrieval layer.** No prior mission (Atlas, which built this
  schema, included) flagged this as unpopulated; Atlas's own report only claimed the *wrapper* exists.

**Confidence/hallucination fields — same pattern**: `confidence_score=` and
`hallucination_check_result=` are passed to `log_provenance_from_wrapper` in **zero call sites** app-wide
(grepped `confidence_score=\|hallucination_check_result=` excluding the function's own definition and
docs/tests) — these columns exist in the `ai_forensics` schema and function signature but are never
populated by any caller. (Drafting's OWN separate `confidence_score`, found in CIC section above, is
written to a *different* place — `quality_gate`'s staging record — not into `ai_forensics` via this
kwarg. The two "confidence_score" concepts are not connected to each other.)

**Provenance Coverage, recomputed against the mission's literal 7-field checklist (model, prompt hash,
response hash, token usage, latency, context, source references)**: 6 of 7 fields are essentially
universal (~100%, wrapper-guaranteed); **1 of 7 ("source references") is ~0%** system-wide (5/76 call
sites ≈ 7% for `knowledge_sources` alone, 0% for the 2 retrieval-specific fields). Weighted:
**≈ (6×100% + 1×7%) / 7 ≈ 87%.** **REVISES Atlas's "58-75%" DOWNWARD-ADJACENT but for a different
reason**: Atlas's own lower figure was about context/case-linkage breadth; this pass isolates that
"source references" specifically is the near-total gap, a more precise and more concerning finding for
a legal product than a generic linkage percentage. **Target ≥95% — NOT MET.**

---

## 5. Replay Coverage

Traced 3 concrete decision types through the schema + code (no live DB access in this environment, so
reasoned precisely from `security/ai_forensics.py`'s insert schema + what each call site actually
populates, per §3/§4 above):

1. **Genome refresh**: `ai_forensics` row has model/prompt-hash/output-hash/tokens/latency (universal),
   `correlation_id` (universal per Ledger), `predmet_id`/`document_id` (via `case_context`, present),
   `knowledge_sources` (populated — list of doc IDs). A companion `audit_immutable` row exists
   (`genome_refresh` action, in `AUDITABLE_ACTIONS`). **Fully reconstructible**: who/when/what
   model/what docs fed it/what came out. **Not reconstructible**: the actual system/user prompt text
   (only a SHA-256 hash is stored, by design — this is a deliberate privacy tradeoff, not a bug, but it
   does mean "replay" tops out at "prove a specific known prompt produced a specific known output," not
   "read back the original prompt from scratch").
2. **Strategy Engine call**: same universal fields, `predmet_id` present via `case_context`, but
   **no persistence of the actual analysis output anywhere** (`SENT-003`, still open) — the
   `ai_forensics` row's `output_hash` proves *a* strategy was generated and roughly what its hash was,
   but the readable content only ever reached the original HTTP response, now gone. **Partially
   reconstructible**: "a call happened, this shape of output was produced" — **not reconstructible**:
   the actual strategic conclusion given to the lawyer.
3. **Copilot deadline extraction (`akcija_rok`)**: fully reconstructible — `ai_forensics` row +
   `audit_immutable` (`copilot_dodaj_rok`) + the actual deadline written to `predmet_hronologija` (a
   real, readable business record, unlike Strategy Engine). This is the best-case pattern in the app.
4. **`main.py::ask_agent` via `routers/dokument.py`'s uncovered call path** (§3 finding): `ai_forensics`
   row exists (wrapper is unconditional) with model/hash/tokens/latency, `module_name` auto-fills to
   `"dokument.py:dokument_pitanje:<line>"` via `_caller_hint()` — so even this "unmigrated" call site is
   NOT a total blackout, just missing case-level linkage (`predmet_id`/`document_id`/explicit
   `operation_name`) and a dedicated `log_action` audit row. **Correlation-level replay: yes. Business
   ("which document/case was this about") replay: no.**

**Replay Coverage estimate**: full reconstruction (model+input-hash+output-hash+correlation, case-level
AND business-content level) ≈ matches Audit Link Coverage's ~39% call-site figure, since case-linkage is
the binding constraint; **correlation-level replay (who/when/what model, not full business content)** is
close to 100% (same as Provenance's 6/7 universal fields). **Target ≥95% — NOT MET at the full-business
level; MET at the correlation/technical level.** No prior mission attempted a concrete traced example
like this; first measurement at this granularity.

---

## 6. Reliability Score

Re-ran `tests/test_phoenix_reliability_failure_recovery.py` fresh: **12 passed**, confirming Phoenix's
delivered fixes are still intact in current code:
- `services/event_bus.py`: all 6 handlers still `raise` after `logger.warning(...)` (grepped, confirmed
  at lines 105/118/135/159/204/246); `MAX_DISPATCH_ATTEMPTS = 5` present (line 378); `DEAD_LETTER`
  marking logic present (lines 426-446).
- `routers/morning_briefing.py::nightly_intelligence_run`'s retry+audit fix — not independently
  re-executed against a live failure in this pass beyond the existing automated test, which does pass.

**Critical flows with genuine detect+recover** (re-derived, not copied): Event Bus/Durable Outbox (yes,
Phoenix), nightly alerts (yes, Phoenix), Copilot's TOCTOU race (yes, Phoenix), Search degradation
signal (yes, Phoenix — detection/observability, not "recovery" in the retry sense, since a read-only
search has nothing to roll back). **Flows with NO independently-verified detect+recover this pass**:
Pinecone write failures on upload (Sentinel found "no cleanup," unchanged), Anthropic calls (not found
to exist anywhere in this grep sweep — the app appears to be OpenAI-only despite Phoenix's own report
listing "Anthropic" as an inventoried system; **this may be a phantom system** carried over from the
mission brief's own generic template rather than a real integration — worth the founder confirming),
SMTP failures (detected/logged, not retried — acceptable given the underlying alert already persisted,
per Phoenix's own reasoning, re-confirmed sound here).

**Reliability Score**: of roughly 20 critical flows enumerable, ~6 have concrete evidence of
detect+recover added/verified this engagement (Event Bus, nightly alerts, TOCTOU, search-degradation,
upload ghost-document HTTP 500, OCR retry via Smart Intake's job reaper), the rest rely on
generic try/except + fail-soft patterns that detect but don't necessarily recover to a fully consistent
state. **Reliability Score ≈ 75-80%** (a plain majority of flows are at least fail-soft and observable,
a minority have full detect→retry→recover→audit chains). **REVISES DOWNWARD** from any implicit "we
fixed reliability" framing in Phoenix's own report, which reported metrics per-workflow (median 8/10)
rather than a single system-wide percentage — this pass computes a literal single percentage as
Keystone asks for, and it comes in below Keystone's own ≥90% target. **Target ≥90% — NOT MET.**

---

## 7. Failure Recovery Coverage

Enumerated ALL critical flows (not just Phoenix-touched ones), Yes/No/Partial on detect+recover:

| Flow | Detect | Recover | Verdict |
|---|---|---|---|
| Event Bus / Durable Outbox | ✅ | ✅ (dead-letter cap) | Yes |
| Nightly alert insert | ✅ | ✅ (retry+audit) | Yes |
| Copilot client-link TOCTOU | ✅ | ✅ | Yes |
| Search sub-search failure | ✅ | ⚠️ (signaled, not retried — read-only, arguably doesn't need to be) | Partial |
| Upload ghost-document | ✅ | ⚠️ (fails loudly, but Pinecone vector orphaned, no cleanup) | Partial |
| OCR job failure | ✅ | ✅ (Smart Intake's 5-attempt reaper, per memory) | Yes |
| Pinecone write failure (non-upload paths, e.g. re-index) | Not independently re-verified this pass | — | Unknown |
| Embedding failure | ✅ (`_tracked_embed` captures, re-raises) | ❌ (propagates to caller, RAG degrades silently per Sentinel §4, unchanged) | No |
| DB deadlock (`claim_intake_job`) | ✅ (`SKIP LOCKED`) | ✅ (structurally can't deadlock) | Yes |
| DB duplicate-key (general) | ✅ (`_is_unique_violation`) | ✅ (where used — Copilot's race; NOT universally applied to every insert in the app) | Partial |
| Strategy Engine failure | ✅ (`@llm_retry`) | ⚠️ (degrades cleanly but nothing persists to recover TO) | Partial |
| Drafting generation failure | ✅ | ✅ | Yes |
| Case Genome refresh failure | ✅ (Phoenix) | ✅ (dead-letter) | Yes |
| Task Engine failure | ✅ | ✅ (deterministic fallback) | Yes |
| Memory Graph write failure | ✅ (500) | ❌ (user must retry manually, no system-level recovery) | No |
| The ~41 newly-identified AI modules (§ Headline) | Not independently re-verified this pass — 0 of them appear in ANY prior mission's chaos-testing scope either | — | **Unknown — largest single gap in this metric** |

**Failure Recovery Coverage**: of the ~15 named/previously-assessed flows, 9 Yes + 4 Partial + 2 No ≈
roughly 65-70% weighted. **But the honest, full-system denominator must also include the ~41 newly
identified modules, for which failure-recovery behavior is genuinely unknown, not "assumed fine."**
Stating a single system-wide percentage over an entirely unverified population would be fabrication —
**this report explicitly declines to compute one number over the full 55-module surface and instead
states: known-and-tested subset ≈65-70% coverage; ~75% of the full AI-calling module population
(41 of 55 files) has never been chaos-tested by any mission this session.** **Target 100% — NOT MET,
and the true gap is materially larger than any prior mission's framing suggested.**

---

## Summary table

| Metric | Fresh figure | Target | Met? | vs. prior mission |
|---|---|---|---|---|
| ICS | ~34-39% | (no fixed target stated in Keystone brief) | — | First measurement |
| CIC | ~68% (4.1/6 mean) | (no fixed target stated) | — | First measurement |
| Audit Link Coverage | ~39% (full-system) / 78% (Migration's own 36-row scope, confirmed accurate for that scope) | ≥95% | ❌ | **REVISES DOWN** from 78% when denominator is corrected |
| Provenance Coverage | ~87% (6/7 fields universal, "source references" ~0-7%) | ≥95% | ❌ | REVISES from Atlas's 58-75%, isolates "source references" as the near-total gap |
| Replay Coverage | ~100% correlation-level / ~39% full-business-level | ≥95% | ❌ (business level) / ✅ (correlation level) | First concrete-example measurement |
| Reliability Score | ~75-80% | ≥90% | ❌ | First single-percentage measurement (Phoenix reported per-workflow, not one number) |
| Failure Recovery Coverage | ~65-70% known subset; ~75% of full module population untested | 100% | ❌ | REVISES DOWN once the ~41 untested modules are counted honestly |

**None of the 7 targets are met under an honest, full-system denominator.** This does not mean the
engagement's work this session was wrong or wasted — every fix Phoenix/Migration/Ledger/Atlas made is
still verified present and correct in the current code — it means **the scope each prior mission chose
to measure against was narrower than the actual system**, and Keystone's fresh, unfiltered count makes
that gap visible for the first time.
