# Canonical Case Context Contract — Program Tau, Master Sprint 002, Phase 2

**Implementation**: `shared/case_context.py::build_case_context(predmet_id, uid, supa)`
**Contract version**: `1.0.0` (`shared/case_context.py::CONTRACT_VERSION`)

## Why this exists

`CONTEXT_BUILDER_REGISTRY.md` (Phase 1) found 4+ independent, hand-rolled context-assembly functions,
each with a different blind spot, and zero that gave GPT documents + Genome + evidence + actions together.
This contract is the single structure that replaces them. It is not a new fact-computation system — every
field below reads an already-canonical source directly (see the "owner" column). This module computes
zero new business facts; it only assembles and, for documents specifically, selects what's visible in a
given call (Phase 3).

## The 13 fields

| Field | Type | Source (canonical owner) | Refresh |
|---|---|---|---|
| `case_identity` | dict | `predmeti` table | real-time read-through |
| `participants` | dict | `predmeti` table (stranka/protivnik/klijent_id) | real-time read-through |
| `procedural_status` | dict | `predmeti.status` + `shared/case_readiness.py` | real-time |
| `timeline` | list | `predmet_hronologija` | event-driven (`services/case_evolution.py` writes it) |
| `key_facts` | dict\|None | `predmeti.case_dna` (Genome) | on Genome refresh (`routers/case_dna.py`) |
| `evidence_graph` | dict | `predmet_dokazi` | real-time read-through |
| `contradictions` | list | `shared/gap_engine.py::gaps_from_contradictions` | on Genome refresh |
| `missing_evidence` | list | `shared/gap_engine.py::collect_case_gaps` (minus contradictions) | real-time, pure function |
| `deadlines` | list | `rocista` | real-time read-through |
| `active_actions` | list | `case_actions` (open only) | event-driven (`case_evolution.py` writes it) |
| `readiness` | dict | `shared/case_readiness.py::compute_case_readiness` | real-time, pure function |
| `relevant_documents` | dict | `predmet_dokumenti` + Document Visibility Engine Layer 4 | real-time per call, deterministic |
| `document_summaries` | list | Layer 4 excerpts (deterministic truncation, NOT a GPT call) | real-time per call |
| `audit_metadata` | dict | `shared/case_context.py` (self-reporting) | generated fresh every call |

Every one of the 13 fields is wrapped in `context_field(value, source, owner, refresh)`
(`shared/case_context.py:100-110`), which also stamps a `timestamp` — Phase 2's own explicit requirement
("Svako polje mora imati: izvor, vlasnika, način osvežavanja"), enforced structurally, the same idiom
Sigma Sprint 005 established for `shared/commander_schema.py`.

## What this module reuses, and does not reinvent (the mission's own "ZABRANJENO" list)

- `services/risk_engine.py::calculate_procesni_rizik` / `identify_case_problems` — unchanged, called
  directly (`DC-001`/`DC-002`).
- `shared/gap_engine.py::collect_case_gaps` — unchanged, called directly (Sigma Sprint 003).
- `shared/case_readiness.py::compute_case_readiness` / `top_open_action` — unchanged, called directly
  (Sigma Sprint 004).
- `routers/cross_doc.py::_uzorkuj_dokument` — unchanged, called directly for within-document sampling
  (Program Celina, 2026-07-24) — Phase 3's own document-selection logic (`_select_documents`) is new (it
  answers a different question, WHICH documents to include, not how to sample WITHIN one), but the actual
  text-sampling algorithm is not duplicated.
- Zero GPT calls anywhere in this module. `document_summaries` is a deterministic excerpt preview, not a
  new AI call — satisfies the mission's explicit "GPT sažimanje kao zamena za strukturirane podatke" ban
  by construction (there is no summarization step to ban).

## What `predmet.case_dna` alone could not give us: `evidence_graph`, `active_actions`, `deadlines`

The historical bug this contract fixes is exactly this: every prior builder read SOME subset of
{Genome, documents, evidence, actions, deadlines} and treated it as the whole picture. `case_dna` alone
(what `case_intelligence.py` used) has no live view of `case_actions` or `predmet_dokazi` — it's a
point-in-time GPT extraction, not a live table. `build_case_context()` reads all of them in one
`asyncio.gather` (`_fetch_raw`, `shared/case_context.py:117-176`) every call, so there is never a version
of "the facts" inside this contract that diverges from what `case_actions`/`rocista`/`predmet_dokazi`
themselves say right now (Phase 4's own synchronization requirement — see
`docs/tau/GPT51_IMPLEMENTATION_ROADMAP.md`-equivalent verification in this sprint's own report).

## Non-goals (explicitly out of scope, documented so a future sprint doesn't assume otherwise)

- **Not a replacement for Genome computation itself** (`routers/case_dna.py`'s own extraction call) —
  `key_facts` READS `case_dna`, it does not compute it.
- **Not a replacement for `case_actions`' own write path** (`services/case_evolution.py`) — `active_actions`
  READS open rows, it does not create/update them.
- **Not a caching layer** — every `build_case_context()` call re-fetches from Supabase. No result is
  stored or reused across calls. This is a deliberate simplicity/correctness tradeoff (Phase 7's own
  determinism/no-stale-cache requirement) over a performance optimization; Phase 6 addresses cost/latency
  separately, without introducing a cache that could serve stale facts after a Genome refresh or a new
  document upload mid-session.
