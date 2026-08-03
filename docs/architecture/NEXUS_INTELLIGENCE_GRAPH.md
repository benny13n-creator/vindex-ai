# Vindex Intelligence Graph

**Mission:** Project Nexus, founder's Master Prompt, 2026-08-03. Complete data-flow inventory in the
founder's requested format (`Source | Event | Data Produced | Consumers | Status`). Extends, not
replaces, `docs/architecture/COGNITIVE_GRAPH.md` (Project Synapse, same day) — this table adds the
explicit event-oriented columns and the modules Synapse's node-based graph didn't individually list
(Task Engine, Case Command Center, background jobs). Every row grounded in a direct code read this
session or Synapse's, not assumed.

---

| Source | Event | Data Produced | Consumers | Status |
|---|---|---|---|---|
| Document Upload (Smart Intake / older path) | `DocumentUploaded` (implicit — no named event, just the HTTP call) | Encrypted blob, `intake_jobs`/`predmet_dokumenti` row | OCR | OK |
| OCR (`uploaded_doc/extractor.py`) | — | Plain text, `is_scanned`/`ocr_used` flags | Classification, Extraction, Semantic Search (via chunking) | OK |
| Document Classification (`shared/intake_classify.py`) | — | `document_type` + confidence | Smart Intake finalize, Chronology labeling | OK |
| Entity Extraction (`shared/intake_extract.py`) | — | `case_number`/`judge`/`plaintiff`/`defendant`/`court`/`deadline`/`amount`/`law_cited` + per-field confidence | Smart Intake review UI, Chronology/Deadline writer | **Partial** — extracted judge/court/opponent never reach `predmeti.tuzilac`/`tuzeni` (see Top 20 Breakpoints #1) |
| Case Genome (`routers/case_dna.py`) | `GenomeUpdated` (durable outbox) | `pravna_teorija`/`snaga_predmeta`/`najslabija_tacka`/`strategija`/`kontradikcije`/`nedostaje` | AI Briefing, CIO, Copilot (fixed, Project Synapse), Firm Brain (fixed, Project Synapse) | OK |
| Facts (Evidence Vault, `routers/evidence.py`) | — | `tip_dokaza`/`pravni_elementi`/`kljucne_cinjenice` | Case Genome (as input context), Matter Intelligence's missing-doc detector | OK |
| Arguments / Contradictions (inside Case Genome) | — | `kontradikcije[]` with location + severity | AI Briefing, lawyer-facing panel | OK — has a rule-based location-verification check (`shared/genome_validator.py`) |
| Risk Analysis (`services/risk_engine.py::calculate_procesni_rizik`) | — | `health_score`/`procesni_rizik`/`nedostajuci_dokazi`/`kriticni_rokovi` (+ `kriticni_rocista`, added this mission) | Matter Intelligence, Case Command Center (**fixed this mission** — was an independent, silently-diverging reimplementation), Event Bus (**fixed this mission** — now emits 2 real alerts) | OK, was Partial |
| Strategy Engine (`identify_case_problems`) | — | `otkriveni_problemi[]` (deterministic, "the only next-action algorithm platform-wide") | Matter Intelligence, Case Command Center, Task Engine (**fixed this mission** — was bypassed by a 5th independent GPT detector) | OK, was **High-severity gap** |
| Timeline (`predmet_hronologija` + `intelligence_timeline.py`) | — | Chronological event list, includes audit entries | Calendar, Risk Analysis, case-scoped audit view | OK |
| Deadline Detection (`routers/rokovi_lanac.py`) | — | Derived procedural deadline chains, written into `predmet_hronologija` | Calendar, Notifications | OK — correctly a writer/populator of the canonical timeline, not a competing table |
| Task Creation (`routers/zadaci.py`) | — | `zadaci` rows (manual CRUD) + AI-created rows (`ai_analiziraj_predmet`) | Task list UI, Notifications | OK, **fixed this mission** (AI-created rows now grounded in `identify_case_problems` instead of independently guessing from filenames) |
| Alert System (`proactive_alerts` + Event Bus handlers) | `HEALTH_SCORE_PROMENJEN`, `ROK_KRITICAN` (**fixed this mission — were defined, handled, never emitted**) | In-app alert rows | Notification bell | OK, was **High-severity gap** |
| Firm Brain (`routers/precedenti.py`) | — | Similar-case narrative | Winning Strategy Brief (prior mission), Litigation Intelligence tab | OK — now also reads Case Genome (fixed, Project Synapse) |
| Memory Graph (`routers/memory_graph.py`) | — | Cross-case relationship query results | Nothing — zero frontend, zero data-writer beyond its own dead manual-entry endpoint | **Dead** — unchanged, founder decision needed |
| Semantic Search (`app/services/retrieve.py::retrieve_documents`) | — | Similarity-ranked passages | 15+ consumers across the repo (confirmed the best-connected node in the whole system) | OK |
| Similar Cases (part of Firm Brain, `precedenti.py`) | — | Ranked list of similar closed cases | Winning Strategy Brief | OK |
| Copilot Context (`routers/copilot.py`) | — | Conversational routing + case analysis | Chat UI only | OK — case analysis now reads Genome (fixed, Project Synapse); output still not persisted anywhere (a deliberate dead-end, chat is ephemeral by design) |
| AI Briefing (`routers/case_intelligence.py`) | — | Synthesized next-step recommendation | Case-detail UI button, Winning Strategy Brief | OK |
| Dashboard (Case Command Center, `routers/ccc.py`) | — | Aggregated one-call view of a case | Case-detail dashboard UI | OK, **fixed this mission** (was silently divergent health_score + always-wrong missing-document list, both now delegate to the canonical `calculate_procesni_rizik`) |
| Audit Ledger (`shared/audit_immutable.py` + `services/decision_log.py`) | `GenomeUpdated`'s handler, GDPR actions, document uploads | Hash-chained security log (`audit_immutable`) + institutional-reasoning log (`decision_log`) | Compliance review, AI Briefing (reads `decision_log`) | OK — confirmed correctly complementary, not duplicate systems |
| Notifications (email cron, in-app alerts) | — | Emails, alert rows | Lawyer's inbox, notification bell | OK |

---

## Legend for Status column
- **OK** — data reaches its intended consumer(s), verified by direct code read.
- **Partial** — reaches SOME intended consumers but not others, or the underlying signal has a known
  accuracy gap.
- **Dead** — produced but consumed nowhere.
- **Fixed this mission** — was Partial/gap, connected/repaired as part of Project Nexus (see
  `docs/architecture/NEXUS_ORCHESTRATION_REPORT.md` for verification detail — reuses Project Synapse's
  `ORCHESTRATION_REPORT.md` naming convention for this mission's own changes).

## What changed this mission (summary)
Three real "Status: Partial/gap → OK" transitions: Risk Analysis/Task Creation (the 5th independent
missing-document detector eliminated), Alert System (2 dead event emissions connected), and the
Dashboard row (a silently-diverging duplicate formula eliminated). One reliability fix not visible in
this table's shape: the Case Genome refresh frontend no longer shows a false "success" toast on a
genuine LLM failure.
