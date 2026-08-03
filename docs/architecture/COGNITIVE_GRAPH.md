# Cognitive Graph

**Mission:** Project Synapse, founder's Master Prompt, 2026-08-03. A knowledge-flow map of every
intelligence-producing subsystem in the repository — not an API map. For each node: what knowledge
enters, what leaves, who consumes it, who currently ignores it. Grounded in a fresh audit
(`.vindex_ai_team/decisions/2026-08-03_synapse_cognitive_audit_INVESTIGATION.md`), not prior reports.

---

## Core reasoning nodes (produce a synthesized legal judgment)

| Node | Knowledge in | Knowledge out | Consumed by | Ignored by (should consume, doesn't) |
|---|---|---|---|---|
| **Case Genome** (`routers/case_dna.py`) | All case documents (up to 25 most recent), Evidence Vault facts | `pravna_teorija`, `snaga_predmeta`, `najslabija_tacka`, `strategija`, `kontradikcije`, `nedostaje` — the richest single synthesis in the repo | AI Briefing, CIO, **Copilot's case-analysis (fixed this mission)**, **Firm Brain (fixed this mission)** | Outcome Intelligence, Judge/Court Profiler still re-derive from scratch (see Cognitive Islands Report) |
| **AI Briefing** (`routers/case_intelligence.py`) | Case Genome, lessons_learned, firm_dna, case_patterns, proactive_alerts, decision_log, client_twin_profili, knowledge_profiles (8 sources) | One synthesized `sledeci_korak`/`kljucni_rizici`/`komunikacioni_savet` | Case-detail UI button (wired 2 missions ago) | Nothing downstream — a terminal node by design (this is meant to be the lawyer-facing answer, not an input to something else) |
| **Firm Brain / Similar Cases** (`routers/precedenti.py`) | Closed cases of the same type/area, their history/chronology, **Case Genome (fixed this mission)** | Firm-experience narrative | Winning Strategy Brief (wired last mission), Litigation Intelligence tab | — |
| **Outcome Intelligence** (`routers/outcome_intel.py`) | All cases of the same type, win/loss classification from chronology | Win-rate statistics, success/risk factors | Winning Strategy Brief, Litigation Intelligence tab | Case Genome (not yet read — flagged as a remaining opportunity, not fixed this mission; see Orchestration Report) |
| **Judge & Court Profiler / Opponent Intelligence** (`predictor` router) | Manually-typed judge/court/opponent name, that entity's case history | Tendency/style analysis | Litigation Intelligence tab | Case Genome (same gap as above); Smart Intake's already-extracted judge/opponent entities (never written to `predmeti.tuzilac`/`tuzeni` — a data-plumbing gap, not a reasoning gap, see Cognitive Islands Report) |
| **Copilot's case analysis** (`routers/copilot.py::_handle_analiza_predmeta`) | Raw case rows (notes/documents/chronology/history), **Case Genome (fixed this mission)** | Conversational case-strength answer | Chat UI only — output not persisted anywhere | Nothing downstream (dead-end by design — a chat answer, not a stored artifact) |
| **Matter Intelligence / Risk Analysis** (`services/risk_engine.py`) | `predmet_dokazi`, `predmet_dokumenti.tip_dokaza`, `rocista` | `health_score`, `procesni_rizik`, `otkriveni_problemi` (the platform's one deterministic next-action source) | Matter Intel bar (always-visible), Case Pipeline, **Event Bus (fixed this mission — see below)** | — |

## Intake / extraction nodes (produce structured facts from raw documents)

| Node | Knowledge in | Knowledge out | Consumed by | Ignored by |
|---|---|---|---|---|
| **OCR** (`uploaded_doc/extractor.py`) | Raw PDF/DOCX/TXT/image bytes | Plain text (+ `is_scanned`/`ocr_used` flags) | Every downstream node in this table | — |
| **Document Classification** (`shared/intake_classify.py`) | OCR text | Coarse `document_type` + confidence | Smart Intake finalize, chronology labeling | — |
| **Entity Extraction** (`shared/intake_extract.py`) | OCR text | `case_number`/`judge`/`plaintiff`/`defendant`/`court`/`deadline`/`amount`/`law_cited` entities with confidence | Smart Intake's review UI, chronology/deadline writing | **`predmeti.tuzilac`/`tuzeni` columns — extracted but never written there (Cognitive Island #1, Orchestration Report's flagged-not-fixed item)** |
| **Evidence Classification** (`routers/evidence.py`) | Document text | `tip_dokaza`, `pravni_elementi`, `kljucne_cinjenice`, `ai_tags` | Case Genome (as context), Matter Intel's missing-doc detector | — |
| **Semantic/Vector Search** (`app/services/retrieve.py::retrieve_documents`) | Every ingestion path's chunked text (Smart Intake, older upload, draft staging/approval) | Similarity-ranked passages | **The single best-connected node found in this audit** — 15+ consumers across `api.py`, Copilot, court predictor, drafting, knowledge graph, multi-agent, ambient analyzer, learning engine, legal reasoning, quality gate, voice tools, web3 | Nothing — genuinely not an island |

## Notification / alert nodes

| Node | Knowledge in | Knowledge out | Consumed by | Ignored by |
|---|---|---|---|---|
| **Event Bus** (`services/event_bus.py`) | Emitted events from any trigger point | Fires registered handlers | See Cognitive Islands Report for the full emit/handler matrix — 2 of 12 event types were healthy before this mission; **now 4 of 12, after wiring `HEALTH_SCORE_PROMENJEN` and `ROK_KRITICAN`** | 3 `DOCUMENT_JOB_*` events still emit with zero handler; 4 event types fully dead on both ends (documented, not fixed — see Orchestration Report) |
| **Email deadline reminders** (`email_notif.py`) | `predmet_hronologija` deadline rows | Email at 7/3/1 days out | Lawyer's inbox | — |
| **Proactive alerts** (`proactive_alerts` table) | Now fed by Genome deltas, low health score, critical deadlines (as of this mission) | In-app alert | Notification bell | — |

## Sinks and sealed modules (not defects, distinct categories)

| Node | Category | Why |
|---|---|---|
| **Usage Analytics** (`routers/analytics.py`, `routers/product_intelligence.py`) | Pure one-way sink | Confirmed: no AI subsystem reads `usage_events` back to inform a recommendation. A founder-only business dashboard, correctly not part of the reasoning graph. |
| **Web3 / Digital Asset Compliance** (`routers/web3.py`, `wallet_provenance.py`) | Deliberately sealed | Confirmed zero references to `predmet_id`/`case_dna`/`predmeti` — by design, not a gap (prior product decision to gate this as a separate module). |
| **Contract Analysis** | Does not exist as a distinct node | Confirmed by absence — `tip_dokaza="ugovor"` (generic classification) is the only signal; no dedicated subsystem to map. |
| **Knowledge Profiles** (`knowledge_profiles` table, read by AI Briefing) | Phantom data source | Its only writer is `routers/knowledge_transfer.py`, itself confirmed dead code (Operation Invisible Features). Structurally always empty for any real firm — the Briefing reads it, but it never has anything to find. |
| **Memory Graph** (`routers/memory_graph.py`) | Fully dead | Real query logic, zero frontend, zero data-writer beyond its own equally-dead manual-entry endpoint — confirmed unchanged from Operation Invisible Features. |

---

## What changed this mission

Three edges added to this graph, all verified with tests and zero regressions:
1. Matter Intelligence → Event Bus (`HEALTH_SCORE_PROMENJEN`, `ROK_KRITICAN` now actually emitted).
2. Case Genome → Copilot's case analysis (reads Genome as context instead of re-deriving blind).
3. Case Genome → Firm Brain (same pattern).

Everything else in this graph is the CURRENT state, not a proposal — see `INTELLIGENCE_PROPAGATION_MAP.md`
for the ideal event-chain design and `COGNITIVE_ISLANDS_REPORT.md` for every remaining gap, each
either connected this mission or explicitly documented per the mission's own rule.
