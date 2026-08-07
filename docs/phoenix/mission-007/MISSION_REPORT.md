# Program Phoenix — Mission 007: Case Evolution Consequence Chain Integrity

**Date**: 2026-08-07
**Debt items addressed**: `LIVINGSYS-DEBT-011` (partial — `timeline_entry` closed;
`genome_refresh`, `review_confirmation_audit`, `review_rejection_audit`,
`case_intelligence_summary` remain open, reasoning below), `LIVINGSYS-DEBT-016` (fully closed).

## Why these 2 were grouped

Both live entirely inside `services/case_evolution.py`'s consequence-registry architecture —
minimum files touched, same canonical source.

## Phase 1 — Reproduction

- `-011`: confirmed 5 of 9 consequence executors lack an inner idempotency guard beneath the
  outer claim, per the debt register's own prior finding. Re-verified `_consequence_
  timeline_entry` specifically: a plain `.insert()`, no dedup key, no pre-check.
- `-016`: confirmed `CONSEQUENCE_REGISTRY[EventType.NEW_EVIDENCE_REGISTERED]` contains only
  `evidence_classification` — no `refresh_case_actions`.

## Phase 2 — Root cause

See `ROOT_CAUSE_ANALYSIS.md`.

## Phase 3 — Fix

- `-011` (`timeline_entry`): before inserting, checks for an identical `(predmet_id, dogadjaj)`
  row created within the same `_CONSEQUENCE_STALE_PENDING_SECONDS` (300s) window this module
  already reclaims stale claims on — the exact same "identical content, recent window" idiom
  already proven for `LIVINGSYS-DEBT-043` (`rocista.py`, Mission 005). No migration
  (`predmet_hronologija` has no `event_id` column to key on directly).
- `-016`: added `ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions)`
  to `NEW_EVIDENCE_REGISTERED`'s registry entry — reuses the exact same executor
  `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO` already register, zero new logic.

**Not attempted this mission, with reasoning** (the remaining 4 of 5 `-011` executors):
- `genome_refresh`: the debt register's own suggested check ("verzija didn't already bump") is
  ambiguous in practice — `before_verzija` is captured fresh at the START of each invocation,
  so it cannot by itself detect "did an EARLIER attempt for this same event already succeed."
  A real fix needs either persisting the original snapshot as part of the claim row (a schema
  change to `case_evolution_consequences`) or a different mechanism entirely — genuine new
  design work, not a mechanical port of the `timeline_entry`/`evidence_classification` pattern.
  Confirmed lower urgency than `timeline_entry`: the debt register's own Chaos-team finding
  explicitly states "final `case_dna` content not corrupted" for this executor — the harm is
  wasted GPT cost, not a user-visible duplicate.
- `review_confirmation_audit`/`review_rejection_audit`: write to `audit_immutable`, an
  append-only hash-chain table by design — a "check before insert" dedup query would need to
  reason about hash-chain positions, a different and more delicate mechanism than a plain
  content-match check. Deferred rather than risk a subtly wrong guard on an immutable audit
  ledger.
- `case_intelligence_summary`: migration 098's own comment already claims a `(predmet_id,
  event_id)` uniqueness invariant that isn't actually DB-enforced (a documentation/reality
  mismatch named by a prior mission, not re-investigated here) — the correct fix is arguably
  adding the missing `UNIQUE` constraint via migration, which this engagement's coordinator
  never authors-and-runs without founder execution.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_007_case_evolution_chain_integrity.py`, 3 tests.

## Phase 5 — Original scenario rerun

`test_timeline_entry_skips_duplicate_insert_on_reclaim` directly reproduces the crash-then-
reclaim scenario (an identical row already exists in the window) and confirms no 2nd insert
fires. `test_new_evidence_registered_now_includes_refresh_case_actions` confirms the registry
entry is now present.

## Phase 6 — Subsystem tests

106 tests across 10 files touching `case_evolution.py`'s registry/timeline/genome logic:
**106 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
