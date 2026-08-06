# GPT Context Map — Program Tau, Master Sprint 004, Phases 1-2

**Method**: fresh re-verification of Tau 001's own 56-file/138-site count (unchanged, grep-confirmed
2026-08-06), cross-checked against `shared/case_context.py::build_case_context()` usage specifically.

## Canonical Case Context Builder adoption — the headline number

**Exactly 2 files call `build_case_context()`**: `routers/case_intelligence.py` (full mode) and
`routers/morning_briefing.py` (lightweight `include_documents=False` mode). `routers/copilot.py` reuses
only the Document Visibility Engine's private sub-helpers (`_select_documents`/`_excerpt`), not the full
builder — it still runs its own separate, narrower `case_dna`/`case_actions` queries. `routers/case_commander.py`
has zero import of `shared.case_context` at all — its own pre-Tau-002 bespoke builder
(`_dohvait_predmet_kontekst`/`_formatiraj_kontekst`) remains fully independent.

## HIGH-RISK FINDING — 17+ case-linked files, each with an independent bespoke context fetch

Every file below has both a real `predmet_id`-keyed DB pattern and ≥1 GPT call, confirmed NOT importing
`shared.case_context`:

| File | predmet_id refs | GPT calls | Context builder |
|---|---|---|---|
| `court_predictor.py` | 29 | 7 | **See below — special case, `predmet_id` never used for context** |
| `drafting.py` | 27 | 5 | inline per-endpoint fetch |
| `matter_intel.py` | 40 | 2 | inline fetch |
| `hearing_cc.py` | 18 | 2 | `_load_all_context` — a genuinely rich 7-table bespoke builder, a real 3rd independent "gather everything about a case" implementation, never reconciled with the canonical one |
| `evidence_graph.py` | 17 | 1 | inline fetch (documents+comments only — no evidence/actions/readiness) |
| `multi_agent.py` | 19 | 3 | inline fetch (already documented, Tau 002's own registry, "richest existing approximation," still independent) |
| `digital_twin.py`, `decision_replay.py`, `strategy_simulator.py` | 18-20 each | 1-2 each | not deep-read this pass |
| `case_dna.py` | 75 | 2 | exempt by category — this IS Genome's own construction step |
| `health_index.py`, `outcome_intel.py`, `precedenti.py`, `zastarelost.py`, `evidence.py`, `doc_templates.py`, `zadaci.py` | 6-21 each | 1 each | not individually classified this pass |

## THE headline finding of this sprint — `court_predictor.py`

All 7 endpoints accept `predmet_id` on their request model, but grep-confirmed it is used **exclusively**
for audit/provenance plumbing (`_ai_case_ctx`, `decision_log` inserts) — **never** to query
`predmeti`/`case_dna`/`predmet_dokazi`/`case_actions`. The actual GPT reasoning input comes entirely from
other request-body fields the caller supplies fresh on every call (`opis_predmeta`, `cinjenicni_opis`,
`dokazi`). A lawyer can pass a real, tracked `predmet_id` and the AI's prediction never touches that case's
current Genome, documents, evidence, or open actions — if the case has since been updated, these 7
endpoints have no way to know.

## Pipeline stage breakdown (INPUT → CONTEXT → PROMPT → MODEL → OUTPUT → DECISION → USER), highest-stakes sites

| Site | Context source | Decision computed from |
|---|---|---|
| `case_intelligence.py::case_intelligence_briefing` | `build_case_context()` full + 5 enrichment queries | Code (Tau 003) — GPT restricted to 3 advisory fields |
| `copilot.py::_handle_analiza_predmeta` | Bespoke (`case_dna` + Document Visibility Engine sub-helpers) | Code (Tau 003) |
| `case_commander.py::commander_analiza` | Bespoke, pre-Tau-002, unmigrated | Code (Sigma 005) — zero live callers |
| `court_predictor.py::prediktuj_ishod` | **None from the case record** — Pinecone RAG precedent search only | Not cross-checked against `risk_engine.py` or any canonical source |
| `hearing_cc.py::hearing_command_center` | `_load_all_context`, own 7-table bespoke builder | Not read this pass |

## Context quality vs. the mission's own 15-item checklist

Checked against `build_case_context()`'s 13-field contract plus `case_commander.py`'s own separate builder.

| Status | Items |
|---|---|
| **Fully covered (8)** | Timeline, Documents, Deadlines, Contradictions, Missing evidence, Case Actions, Readiness, Parties |
| **Narrow slice (2)** | Genome (`key_facts` is only 3 of ~10 real `case_dna` sub-fields — `snaga_faktori`/`strategija`/`finansije`/`heatmap`/`upozorenja`/`zakljucak` all exist on the record but aren't surfaced past `case_intelligence.py`'s own separate, richer rendering); Previous hearings (present in the raw `rocista` fetch, but undifferentiated from upcoming — **fixed this sprint**, see Phase 9 below) |
| **Exists elsewhere, not wired in (4)** | OCR metadata (`intake_documents.ocr_confidence` + a real unused FK path via `predmet_dokumenti.source_intake_job_id`); Client history (`client_twin_profili`, already read by `case_intelligence.py`'s own separate query); Previous strategies (`case_patterns`/`lessons_learned`/`decision_log`, same situation); Judge history (`firm_memory.py`, but this is the SAME pre-existing tracked debt item `ALPHA-005`, not new) |
| **Genuinely doesn't exist anywhere (1)** | Court data beyond the court's own name string — no structured court-level dataset (jurisdiction rules, filing deadlines per court) exists in this platform at all |

**One more precise finding**: `build_case_context()`'s `deadlines` field reads only `rocista` (its own code
comment: "canonical deadline source since Sigma Sprint 005"). `case_commander.py`'s own unmigrated builder
still separately reads a 2nd table, `rokovi`, for the same concept — never reconciled, never merged.

## What was fixed this sprint (Phase 9, see `TAU_004_REPORT.md` for full list)

`deadlines` now carries a `proslo` (past/upcoming) boolean per row, computed from `datum` vs. today — closes
the "Previous hearings, narrow slice" finding above without adding a new data source.

## What was named, not fixed (see `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`, `TAU-011`..`TAU-016`)

The 17+-file migration backlog, `court_predictor.py`'s context gap, the Case Context contract's 4
not-wired-in items, `rokovi`/`rocista` reconciliation, and the genuine court-data collection gap are all too
large or too risky for this sprint's own "fix everything safely fixable without changing architecture"
mandate — each is named precisely rather than rushed.
