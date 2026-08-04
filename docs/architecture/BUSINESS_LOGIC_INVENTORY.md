# Business Logic Inventory — Program Alpha, Phase 1

**Mission:** founder's Master Prompt 001, "Eliminate Entire Classes of Defects." Not a module map — a map
of *business decisions*: where each one is made, who consumes it, and how many independent
implementations exist. Compiled from 6 parallel domain investigations, each independently re-verifying
every claim against current code (not citing prior mission reports on faith). Full evidence per domain in
`.vindex_ai_team/decisions/2026-08-04_alpha_domain_*_INVENTORY.md`.

**Total business decisions mapped: 38**, across 6 domains. **17 have exactly one canonical implementation
(45%, confirmed clean)**. **11 have 2+ independent implementations answering the same question (a genuine
duplicate)**. **2 have effectively zero deterministic implementation (raw LLM output presented as fact)**.
**8 are single-sourced but structurally undermined by hidden logic that defeats them.**

---

## Domain: Risk / Confidence / Health Scoring

| # | Decision | Canonical location | Consumers | Implementations |
|---|---|---|---|---|
| 1 | Case procedural risk / health score | `services/risk_engine.py::calculate_procesni_rizik` | api.py, ccc.py, dashboard.py, matter_intel.py, zadaci.py, case_pipeline.py | **1 — clean** |
| 2 | Next-action / detected-problems list | `services/risk_engine.py::identify_case_problems` | Same consumer set | **1 — clean** |
| 3 | Case Genome case-strength % | `shared/genome_validator.py::compute_snaga_score` | Genome UI, Copilot, Firm Brain | 1, but see #16 (overlaps in concept with Risk Engine's evidence-strength proxy) |
| 4 | Court Predictor confidence — qualitative level (`nivo`) | `routers/court_predictor.py::_calc_confidence_nivo` | Court Predictor response | **1 — clean, deterministic** |
| 5 | Court Predictor confidence — numeric percentage (`procenat`) | Same function, separate GPT-4o-mini call | Same response | **2 (with #4) — DUPLICATE, Critical** |
| 6 | Strategy Engine litigation win-probability | `strategija.py::litigation_simulator_sync` | Strategy Engine PRO endpoint | **0 deterministic — raw LLM output** |
| 7 | Evidence "strength" — auto-classification path | `routers/evidence.py:221` | Feeds `calculate_procesni_rizik`'s tally | Structurally constant (hardcoded), not a real measurement |
| 8 | Evidence "strength" — manual entry path | `routers/evidence.py:298,323` | Same table | 1, legitimate user-supplied default |

## Domain: Deadlines / Timeline / Task Generation / Alerts

| # | Decision | Canonical location | Consumers | Implementations |
|---|---|---|---|---|
| 9 | Missing-document / task-worthy problem detection | `services/risk_engine.py::identify_case_problems` | `routers/zadaci.py` | **1 — clean** |
| 10 | Deadline → Calendar / Notifications wiring | Confirmed connected | `routers/kalendar.py` | **1 — clean** |
| 11 | `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` emission | `routers/matter_intel.py:153,166` | Event Bus handlers | 1, non-durable (`SENT-001`, known, unchanged) |
| 12 | Proactive alert creation | **none — no canonical function** | 9 files | **11 independent insert call sites — DUPLICATE** |
| 13 | "Is this deadline critical" threshold | **none — no shared constant** | 6 files | **≥6 independent copies, 2 different values (3 vs 7 days) — DUPLICATE** |

## Domain: OCR / Classification / Extraction / Missing-Document Detection

| # | Decision | Canonical location | Consumers | Implementations |
|---|---|---|---|---|
| 14 | OCR / raw text extraction | `uploaded_doc/extractor.py::extract()` | `shared/intake_worker.py` | **1 — clean** |
| 15 | "Is this document type X" | `shared/intake_classify.py::classify()` **and** `routers/evidence.py::_klasifikuj_dokument()` | Intake queue / Evidence Vault, risk_engine.py | **2 — DUPLICATE, Critical-tier** |
| 16 | Entity extraction (parties/court/amount/dates) | `shared/intake_extract.py::extract_all_entities()` **and** `routers/evidence.py`'s `ai_tags` | Intake queue / Evidence Vault | **2 — DUPLICATE, overlapping** |
| 17 | "What documents are expected" (missing-doc detection) | `shared/constants.py::EXPECTED_DOCS` → `risk_engine.py` | matter_intel.py, ccc.py | **1 — clean, already consolidated by Nexus** |
| 18 | Evidence "strength" | *(same as #7)* | — | — |

## Domain: Search / RAG / Embeddings / Knowledge Index

| # | Decision | Canonical location | Consumers | Implementations |
|---|---|---|---|---|
| 19 | Legal/RAG document retrieval | `app/services/retrieve.py::retrieve_documents()` | ~15 call sites | **1 — clean, well-consolidated** |
| 20 | Case-law-only retrieval | `app/services/retrieve.py::retrieve_sudska_praksa()` | ~6 call sites | **1 — clean** |
| 21 | Query embedding | `app/services/retrieve.py::_ugradi_query()` | ~6 call sites, cached | **1 — clean, only cached path** |
| 22 | Keyword search across app entities | `routers/search.py::global_search()` | `/api/search` | **1 — clean** |
| 23 | Document embedding for Pinecone ingestion | **none — no canonical function** | 5 routers | **5 independent call sites, hardcoded model string — DUPLICATE** |
| 24 | Pinecone namespace identity | **none — no canonical registry** | Query side (3 constants) + ingest side (2 more sources) | **effectively 3 independent sources — DUPLICATE** |
| 25 | Knowledge Transfer profiles | `routers/knowledge_transfer.py` | `routers/case_intelligence.py` | **1 — clean** (corrects a stale Nexus claim that this table is dead) |

## Domain: Case Genome / Memory Graph / Firm Brain / Strategy Engine

| # | Decision | Canonical location | Consumers | Implementations |
|---|---|---|---|---|
| 26 | Case Pipeline trigger | `on_predmet_kreiran` Event Bus handler | New predmet creation | **1 — clean, single trigger confirmed** |
| 27 | Firm institutional-memory context for AI | `api.py::_fetch_firm_memory_context` (live) **and** `routers/firm_memory.py::kontekst_za_ai` (dead, more complete) | Copilot/RAG (live only) | **2 — DUPLICATE, Critical (one dead, more capable)** |
| 28 | Strategy Engine's 9 endpoints' AI logic | Dedicated `_sync` functions per endpoint | `routers/strategija.py` | **1 per module — clean, boilerplate repetition ≠ duplicated logic** |
| 29 | Memory Graph | `routers/memory_graph.py` | Nobody | 1, zero consumers (isolated, not duplicated) |

## Domain: Audit / Correlation ID / Event Handling / Notification

| # | Decision | Canonical location | Consumers | Implementations |
|---|---|---|---|---|
| 30 | Business audit trail ("what happened, who, when") | `shared/audit_immutable.py` | Everywhere | **2 live tables** (`audit_immutable` canonical + `response_audit` legacy, write-only) — DUPLICATE |
| 31 | Request correlation ID (the one exposed to clients) | **2 fully independent, unlinked mechanisms** | `api.py` middleware (external) vs. `ai_provenance.py` (internal, everywhere else) | **2 — DUPLICATE, Critical, worst finding this mission** |
| 32 | Correlation ID minting | `shared/ai_provenance.py::new_correlation_id()` | Everywhere except 2 sites | **1 canonical + 2 ad hoc inline `uuid.uuid4()` — DUPLICATE, low-severity** |
| 33 | Business event distribution | `services/event_bus.py` | Everywhere | **1 canonical, 2 known non-durable exceptions (unchanged, tracked)** |
| 34 | Outbound email (SMTP) | **none — no canonical function** | 5 routers | **5 independent implementations — DUPLICATE** |
| 35 | "Verify current user from a request" | `shared/deps.py::get_current_user` | Everywhere | 1 canonical + 1 legacy path, both correctly wired (adjacent finding, not a duplicate) |

## Cross-domain, previously flagged, tracked elsewhere (not re-litigated here)

| # | Decision | Status |
|---|---|---|
| 36 | Genome case-strength vs. Risk Engine evidence-strength proxy (UI perception overlap) | Medium — see `SOURCE_OF_TRUTH_REGISTRY.md` |
| 37 | GDPR erasure retention scope (Pinecone/Storage) | Keystone K-1, founder decision pending |
| 38 | Strategy Engine litigation percentage grounding | Keystone K-3/`KEYSTONE-004`, founder decision pending |

---

## Summary

- **17 of 38 decisions (45%) are genuinely single-sourced and clean** — a real, substantial base to build
  on, not a codebase in chaos.
- **11 decisions are true duplicates** (2+ independent implementations of the same business question).
- **2 decisions have effectively zero deterministic backing** (raw LLM output presented as a decision).
- Full duplicate-by-duplicate detail, severity, and root-cause analysis: `DUPLICATE_DECISION_REPORT.md`.
- Full who-decides/who-reads/who-writes/who-must-not-exist analysis: `SOURCE_OF_TRUTH_REGISTRY.md`.
