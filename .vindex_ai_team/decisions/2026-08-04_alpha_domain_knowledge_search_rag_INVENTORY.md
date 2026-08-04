# Program Alpha — Domain Inventory: Search / RAG / Embeddings / Knowledge Index

**Scope**: every search, embedding-generation, RAG-retrieval, and knowledge-index decision point in the
codebase. Read-only, no code/git changes made. All findings verified against current code (grep + direct
read), not inherited from prior mission reports without re-checking.

---

## 1. Decision inventory

| Decision | Canonical origin | Consumers | # implementations |
|---|---|---|---|
| Legal/RAG document retrieval (zakoni/praksa/mišljenja + case-scoped namespaces) | `app/services/retrieve.py::retrieve_documents()` | ~15 call sites: `main.py::ask_agent`, `routers/drafting.py`, `routers/oblasti.py`, `routers/integracije.py`, `routers/multi_agent.py` (×2), `services/ambient_analyzer.py`, `services/legal_reasoning_engine.py`, `shared/voice_tools.py`, `api.py` (×3) | **1 — genuinely canonical, well-consolidated** |
| Case-law-only retrieval | `app/services/retrieve.py::retrieve_sudska_praksa()` | `routers/copilot.py` (×2), `routers/court_predictor.py`, `routers/praksa.py` (×2), `services/agent_tasks/precedents_radar.py` | **1 — canonical** |
| Query embedding (for retrieval) | `app/services/retrieve.py::_ugradi_query()` → `_get_embeddings().embed_query()`, cached via `_embed_cache` | `routers/praksa.py`, `routers/strategija.py`, `routers/knowledge_graph.py`, `services/learning_engine.py`, `web3_compliance.py`, `api.py` | **1 — canonical, and the only cached path** |
| Keyword search across app entities (predmeti/klijenti/dokumenti/billing/hronologija/beleske/zadaci) | `routers/search.py::global_search()` | Single endpoint, `/api/search` | **1 — canonical** (Project Phoenix's `nepotpuno` degraded-search marker confirmed present at `routers/search.py:275-293`) |
| Document embedding (for Pinecone ingestion) | **No canonical function** — 5 independent call sites | `routers/auto_discovery.py`, `routers/batch_ingest.py`, `routers/knowledge_base.py`, `routers/law_upload.py`, `routers/proof.py` | **5 — see Finding A** |
| Pinecone namespace identity (which namespace is valid/queryable) | **No canonical registry** — 3 hardcoded constants on the query side, 2 independently-constructed/validated lists on the ingest side | Query side: `retrieve.py`'s `_ZAKONI_NS`/`_PRAKSA_NS`/`_MISLJENJA_NS`. Ingest side: `auto_discovery.py` (free-text, admin-supplied), `batch_ingest.py` (its own `ALLOWED_NAMESPACES` set) | **effectively 3 independent sources of truth — see Finding B** |
| Knowledge Transfer profiles (`knowledge_profiles` table) | `routers/knowledge_transfer.py` — full CRUD + extraction | `routers/case_intelligence.py` (reads, counts) | **1 — see Correction C, this is NOT the phantom/dead table Project Nexus reported** |

---

## 2. Finding A — no canonical embedding-generation function for document ingestion (Medium-High)

`app/services/retrieve.py` defines exactly one canonical embedding path for **queries**
(`_ugradi_query()` → `_get_embeddings()` → `OpenAIEmbeddings(model=EMBEDDING_MODEL)`, where
`EMBEDDING_MODEL = "text-embedding-3-large"`, `retrieve.py:69`). But every **ingestion** call site
independently calls the raw OpenAI SDK and re-hardcodes the model name as a string literal:

- `routers/auto_discovery.py:164` — `model="text-embedding-3-large"`
- `routers/batch_ingest.py:54` — `model="text-embedding-3-large"`
- `routers/knowledge_base.py:55` — `model="text-embedding-3-large"`
- `routers/law_upload.py:83` — `model="text-embedding-3-large"`
- `routers/proof.py:101` — `model="text-embedding-3-large"`

**Currently harmless by coincidence, not by design**: all 6 values (5 ingest sites + 1 canonical
constant) happen to match today. But nothing enforces this — a future change to `EMBEDDING_MODEL` in
`retrieve.py` (a routine-looking config change) would **silently** create a vector-space mismatch between
newly-ingested documents and query embeddings. This is exactly the class of defect Program Alpha exists
to eliminate structurally: not a bug today, a bug **waiting to be introduced by a normal-looking future
change**, with no test or type system positioned to catch it (embedding-model mismatches don't raise
errors — they silently degrade retrieval quality, the hardest class of bug to detect in production).

**Root architectural pattern**: no single canonical `get_embedding_model_name()` (or equivalent) that
every embed call site — query and document — is required to import. `EMBEDDING_MODEL` exists but is not
enforced as the *only* source.

## 3. Finding B — no canonical registry of valid Pinecone namespaces (Medium)

Query side (`retrieve.py`) hardcodes 3 namespace constants. Ingest side has **two more, independent,
un-synchronized sources**:
- `routers/auto_discovery.py:242,404` — namespace is **admin-supplied free text** (`body.namespace`) or a
  default constructed as `f"zakon_{zemlja.lower()}"` — no validation against any canonical list at all.
- `routers/batch_ingest.py:180,195` — validates against its own local `ALLOWED_NAMESPACES` set, distinct
  from `retrieve.py`'s constants.

**The real risk this creates**: nothing guarantees symmetry between "a namespace documents can be
ingested into" and "a namespace `retrieve_documents()`/`_pretraga_ns()` actually queries." An admin using
`auto_discovery.py`'s free-text namespace field to ingest a document into a typo'd or novel namespace
string produces a **write that succeeds** and a **read that silently never happens** — full,
successfully-ingested documents that are permanently unreachable by any query path, with no error
anywhere in the pipeline to surface this. This is a "write success, permanently orphaned data" defect
class, not a hypothetical one — `auto_discovery.py`'s own free-text field makes it trivially reachable by
a normal admin action, not just a hypothetical misconfiguration.

**Root architectural pattern**: namespace identity is not a single source of truth (an enum, a DB table,
or a shared constants module) — it is duplicated as hardcoded query-side constants plus independently-
validated (or unvalidated) ingest-side strings.

## 4. Finding C — correction to Project Nexus's finding: `knowledge_profiles` is NOT a phantom table

Project Nexus (2026-08-03) reported: *"`knowledge_profiles` is a phantom data source inside the AI
Briefing... its only writer is confirmed dead code."* **Re-verified today: this is stale, not currently
accurate.** `routers/knowledge_transfer.py` ("Knowledge Transfer System — Faza 5") is a real, live,
registered router (`api.py:646,741`, mounted at `/api/knowledge`) with a full, non-dead CRUD lifecycle:
create profile, add source, run extraction, query history, deactivate. It writes to `knowledge_profiles`
in at least 3 places (insert at `knowledge_transfer.py:134`, update at `:319`, plus source/extraction
writes). `routers/case_intelligence.py:166,373` reads and counts these profiles as `knowledge_profila`.
**This appears to be a genuinely different, newer feature than whatever Nexus examined** (Nexus's report
specifically named "AI Briefing" as the consumer; the actual consumer today is `case_intelligence.py`, a
different router) — most likely `knowledge_transfer.py` was built after Nexus's 2026-08-03 audit, or
Nexus examined a different, now-superseded code path. **Not a Program Alpha duplicate-logic finding** —
flagged here as a factual correction so this stale claim doesn't keep propagating uncorrected into future
mission reports, consistent with this engagement's own standing discipline of re-verifying rather than
citing.

## 5. Confirmed still-accurate: provenance fields exist end-to-end but are never populated

`retrieval_query`/`retrieved_context_ids` are real, first-class parameters threaded correctly through the
entire provenance chain — `shared/ai_provenance.py:83-84,102-103` → `shared/ai_client.py:204-205,255` →
`security/ai_forensics.py:214-215,271-272`. **But grep across the entire codebase finds zero call sites
that actually pass a value for either parameter** — the pipe is fully built and connected end-to-end, and
nothing flows through it. `retrieve_documents()` itself returns a rich `retrieval_meta` dict (match
scores, source IDs) to every one of its ~15 callers, but none of them thread that metadata into
`case_context()`'s matching parameters. Confirms Mission Keystone's Phase 2 finding is still accurate
today, not stale.

## 6. Not a finding — genuinely canonical, worth naming as a positive pattern

`retrieve_documents()`/`retrieve_sudska_praksa()`/`_ugradi_query()` are a real, single-source-of-truth
success story: ~20+ call sites across routers/services all import from one module, no competing
reimplementation of HyDE generation, CRAG expansion, GPT/Cohere reranking, or confidence scoring exists
anywhere else in the codebase. This is what Finding A/B's fix should look like once applied to the
ingestion side — not a new pattern to invent, an existing one to extend.

## 7. `services/voice_orchestrator.py` — no independent retrieval logic found

Confirmed via direct grep: zero references to embed/retrieve/pinecone in this file. Voice sessions
("Vindex Live," per Mission Keystone's Phase 1 finding that this feature bypasses the canonical AI
wrapper for chat completions) do not perform RAG retrieval at all currently — narrows, does not
contradict, Keystone's finding (the wrapper-bypass is real; a *duplicate retrieval* concern specifically
is not, since there's no retrieval here to duplicate).

## 8. `routers/dokument.py::dokument_pitanje` — confirmed correctly routed

Still delegates to `ask_agent` (`dokument.py:340`), wrapped in `case_context()` since Mission Keystone's
fix — uses the same canonical retrieval path as Copilot's `pravno_pitanje`, not a separate one. No
regression found.

---

## Prioritized recommendations (diagnostic only — no fix applied this pass)

1. **Finding A (embedding model duplication)** — highest priority: cheap, mechanical fix (import
   `EMBEDDING_MODEL` from `retrieve.py` in the 5 ingest files instead of re-hardcoding the string), zero
   behavior change today, eliminates a real latent-defect class.
2. **Finding B (namespace registry)** — medium priority, larger scope: needs a real design decision (a
   shared constants module? a DB-backed registry?) before implementation, not a one-line fix.
3. **Finding 5 (unpopulated provenance fields)** — already tracked by Mission Keystone's own report; not
   re-scoped here, just re-confirmed still open.
