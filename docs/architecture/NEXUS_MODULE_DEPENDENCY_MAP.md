# Complete Module Dependency Map

**Mission:** Project Nexus, 2026-08-03. For every module: inputs, outputs, dependencies, data owner.
Complements `docs/architecture/NEXUS_INTELLIGENCE_GRAPH.md`'s event-flow view with an explicit
ownership lens — directly answering Phase 5's "who creates/modifies/reads/doesn't know" question.

---

## Data ownership rules (Phase 5, founder's explicit rule set) — verified against current code

| Concept | Declared owner | Verified? |
|---|---|---|
| Case facts | Case Genome (`case_dna`) | **Yes** — Evidence Vault correctly flows INTO Genome as input, not a competing store (confirmed, `routers/case_dna.py`'s own comments state this explicitly and the current code honors it) |
| Conclusions | Strategy Engine (`identify_case_problems` + Genome's own `strategija`/`zakljucak`) | **Partially, now more so** — was violated by Task Engine's independent 5th detector (fixed this mission) and Case Command Center's independent health-score reimplementation (fixed this mission) |
| Interaction | Copilot | **Yes** — Copilot's own case analysis is a chat answer, not written back as a competing fact store; now also reads Genome (Project Synapse) rather than re-deriving |
| Organizational knowledge | Firm Brain (`precedenti.py`) + Firm DNA (`firm_dna` table) | **Yes** |
| Long-term relationships | Memory Graph | **N/A** — the module is dead; the rule is unviolated only because nothing uses it at all |

## Per-module inventory

| Module | Inputs | Outputs | Depends on | Data owner (per Phase 5 rule) |
|---|---|---|---|---|
| `routers/smart_intake.py` | Raw file uploads | `intake_jobs`, `predmet_dokumenti`, entity rows | OCR, Classification, Extraction | — (an intake pipeline, not a fact owner) |
| `routers/case_dna.py` | All case documents + Evidence Vault facts | `case_dna` JSON | Evidence Vault, `shared/genome_validator.py` | **Case facts** |
| `routers/case_intelligence.py` | Case Genome, `lessons_learned`, `firm_dna`, `case_patterns`, `proactive_alerts`, `decision_log`, `client_twin_profili`, `knowledge_profiles` (8 sources, one of which — `knowledge_profiles` — is structurally always empty, see Top 20 Breakpoints) | Synthesized briefing | Case Genome | Consumer only, not an owner |
| `routers/precedenti.py` | Closed cases of same type/area, chronology, Case Genome (as of Project Synapse) | Firm-experience narrative | Case Genome | Consumer, contributes to Organizational Knowledge |
| `routers/outcome_intel.py` | All cases of same type, chronology-derived win/loss | Win-rate statistics | — (does NOT yet read Case Genome — a known, documented, not-yet-fixed gap) | Consumer only |
| `predictor` router (Judge/Opponent) | Manually-typed name, that entity's case history | Tendency analysis | — (does not read Case Genome; does not read Smart Intake's already-extracted names) | Consumer only |
| `routers/copilot.py` | Free text + case rows + Case Genome (as of Project Synapse) | Chat response | Case Genome, Semantic Search, ~20 other handler functions | **Interaction** |
| `services/risk_engine.py` | `predmet_dokazi`, `predmet_dokumenti.tip_dokaza`, `rocista` | `health_score`, `otkriveni_problemi` (the canonical algorithm) | — | Deterministic conclusions source |
| `routers/matter_intel.py` | Same as risk_engine (calls it directly) | Health score display, now also emits 2 Event Bus events (this mission) | `services/risk_engine.py`, `services/event_bus.py` | Consumer + Event producer |
| `routers/ccc.py` (Case Command Center) | Same underlying tables as Matter Intel | Aggregated one-call dashboard view | `services/risk_engine.py` (**as of this mission** — previously reimplemented independently) | Consumer only, now correctly |
| `routers/zadaci.py` | Manual CRUD + (`ai_analiziraj_predmet`) `predmet_dokazi`/`predmet_dokumenti`/`rocista`/`identify_case_problems` (as of this mission) | Task rows | `services/risk_engine.py` (as of this mission) | Consumer, writes actionable rows |
| `services/event_bus.py` | Emitted events (in-process + durable outbox) | Handler side-effects (alerts, audit log, Case Pipeline trigger) | — | Orchestration layer, not a fact owner |
| `routers/memory_graph.py` | Manual relationship entry (dead endpoint) | Cross-case query answers | Nothing writes to it in practice | Declared owner of Long-term relationships, but non-functional |
| `app/services/retrieve.py` | Every ingestion path's chunked text | Similarity-ranked passages | Pinecone | Infrastructure, not a fact owner |
| `services/quality_gate.py` | Generated draft text | `confidence_score`, citation-existence verification | Statute corpus lookup | Guardrail, not a fact owner |
| `services/legal_reasoning_engine.py` | Pre-retrieved sources with SOURCE-n IDs | Constrained-citation legal reasoning | Semantic search | Guardrail/reasoning, isolated from Genome/Briefing (a known gap — neither of those two reaches this stronger anti-hallucination mechanism) |
| `routers/web3.py` / `wallet_provenance.py` | Blockchain/wallet data | Compliance findings | — | Deliberately sealed, zero cross-pollination with core-legal modules (confirmed, correct) |

## "Who doesn't know" — confirmed gaps (cross-reference `NEXUS_TOP_20_BREAKPOINTS.md` for full detail)

- Outcome Intelligence and Judge/Court/Opponent predictors don't know Case Genome exists for the same
  case they're analyzing (Copilot and Firm Brain were fixed this engagement; these two were not).
- `predmeti.tuzilac`/`tuzeni` don't know Smart Intake already extracted the judge/opponent names that
  would populate them.
- The durable audit/outbox system doesn't know about `PREDMET_KREIRAN` — the one truly in-process-only
  `emit()` call site in the entire repository (see Top 20 Breakpoints #2).
