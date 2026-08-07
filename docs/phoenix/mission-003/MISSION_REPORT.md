# Program Phoenix — Mission 003: Institutional Memory & Canonical Registry Cleanup

**Date**: 2026-08-07
**Debt items closed**: `LIVINGSYS-DEBT-008`, `LIVINGSYS-DEBT-052`, `LIVINGSYS-DEBT-017`,
`LIVINGSYS-DEBT-055`.

## Why these 4 were grouped

Same "institutional knowledge / canonical truth infrastructure" architecture: Firm Memory,
Memory Graph, the Semantic Registry, and the Risk Engine's own data-quality signal are all part
of the platform's shared, cross-case truth layer, and each item is a small, mechanical,
minimum-risk fix per the debt register's own characterization — the natural "quick wins"
grouping.

## Phase 1 — Reproduction

- `-008`: confirmed 5 (not the debt register's originally-counted 4) `.order("vaznost")` call
  sites in `routers/firm_memory.py`, all using Supabase's default ascending sort against the
  enum `{"visoka", "normalna", "niska"}` — alphabetically LOW before HIGH.
- `-052`: confirmed `routers/memory_graph.py::_get_firma_id` is a byte-identical duplicate of
  `shared/kancelarija_utils.py::get_kancelarija_id`, missed by the 2026-07-26 consolidation that
  correctly updated `firm_memory.py`/`corrections.py` to import the canonical version.
- `-017`: confirmed `shared/semantic_registry.py::ALL_CONCEPTS` has no `PROBABILITY` entry,
  despite `docs/singular/TRUTH_CONTRACT.md`'s own `## Probability` section documenting 4 named
  generators and their shared guard contract.
- `-055`: confirmed `services/risk_engine.py::calculate_procesni_rizik`'s hearing-date parsing
  loop has a bare `except Exception: pass`, with 2 prior real bugs (per its own code comments)
  already found hiding behind this exact pattern.

## Phase 2 — Root cause

- `-008`: nobody had checked whether Supabase's default ascending order actually matched
  business intent for a hand-written 3-value enum with no natural alphabetical/importance
  correlation.
- `-052`: the 2026-07-26 consolidation's own audit scope covered `firm_memory.py`/
  `corrections.py`; `memory_graph.py` was either not built yet or not in scope at that time and
  was never revisited.
- `-017`: `semantic_registry.py` was built by the mission immediately preceding this one
  (Operation Singular Intelligence Mission 001), and Probability was a documented Truth Contract
  concept that simply wasn't ported into the newer, more mechanical registry file in the same
  pass.
- `-055`: this exact loop has a documented history (in its own comments) of silently hiding 2
  real bugs behind a bare except; the loop's OWN pattern was never revisited to close the
  general case (any future malformed-data instance), only the 2 specific instances already
  found.

## Phase 3 — Fix

- `-008`: all 5 call sites changed to `.order("vaznost", desc=True)`.
- `-052`: `memory_graph.py` now imports `get_kancelarija_id` from
  `shared/kancelarija_utils.py`, aliased to `_get_firma_id` so all 4 existing call sites are
  unchanged; the local duplicate function definition is removed.
- `-017`: added a `PROBABILITY` `ConceptOwnership` entry mirroring `CONFIDENCE`'s multi-owner
  shape (no single function owns it — 4+ legitimate independent generators, unified by a shared
  guard contract), added to `ALL_CONCEPTS`.
- `-055`: added a module-level logger to `risk_engine.py`; the except block now logs a warning
  with the hearing's id/malformed datum before continuing — behavior (silent exclusion from
  scoring) is explicitly UNCHANGED, only visibility is added, per the debt item's own
  "log + counter, don't change behavior" framing.

No new algorithm anywhere.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_003_institutional_memory.py`, 6 tests.

## Phase 5 — Original scenario rerun

`test_kontekst_za_ai_returns_high_importance_memories_first` directly reproduces the debt
item's own flagship scenario (a firm with mixed-importance memories, feeding the AI context
endpoint) and confirms the high-importance fact now appears before the low-importance one in
the generated context string. `test_risk_engine_logs_malformed_hearing_date` reproduces a
malformed-date hearing and confirms the previously-silent drop is now logged.

## Phase 6 — Subsystem tests

301 tests across 19 files touching `risk_engine.py`/`firm_memory.py`/`memory_graph.py`/
`semantic_registry.py`: **301 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
