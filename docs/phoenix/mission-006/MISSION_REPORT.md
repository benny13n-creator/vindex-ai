# Program Phoenix — Mission 006: Evidence Quality Signals

**Date**: 2026-08-07
**Debt items closed**: `LIVINGSYS-DEBT-009`, `LIVINGSYS-DEBT-022`.

## Why these 2 were grouped

Same file (`routers/evidence.py`), same underlying function (`_klasifikuj_dokument`/
`klasifikuj_i_sacuvaj`), same theme: making the evidence-classification pipeline's own
confidence/failure state genuinely visible instead of silently absent.

## Phase 1 — Reproduction

- `-009`: confirmed `_klasifikuj_dokument`'s except block returns a fallback dict
  (`tip_dokaza:"ostalo"`) indistinguishable from a genuine classification, and
  `reklasifikuj` fires classification via `asyncio.create_task` (fire-and-forget) then
  immediately charges a credit, before the background task has even started.
- `-022`: confirmed the GPT classification prompt never asked for a confidence value at all.

## Phase 2 — Root cause

Both stem from the same design gap: the classification pipeline was built to always produce
SOME usable `tip_dokaza` (a legitimate design goal — never block the evidence matrix on an AI
hiccup), but in doing so made every degraded/uncertain result look identical to a fully
successful, fully confident one, with zero signal anywhere for a future reader (human or code)
to tell them apart.

## Phase 3 — Fix

- `-009`: the failure fallback now sets `ai_tags["_klasifikacija_greska"] = True` (existing
  JSONB column, no migration) — `tip_dokaza` stays the same safe "ostalo" default, but the
  failure is no longer silent. `klasifikuj_i_sacuvaj` now returns its result (was always
  `None`) so a synchronous caller can inspect it. `reklasifikuj` now awaits classification
  synchronously (matching every other GPT-consuming endpoint's own request/response
  convention in this codebase) and skips the charge specifically on genuine failure.
  `_consequence_evidence_classify` (the event-driven path) now logs a warning when the
  persisted classification carries the failure flag, closing the debt item's own explicit ask
  ("threaded through `_klasifikuj_dokument` → `_consequence_evidence_classify`'s
  verification").
- `-022`: added `"pouzdanost": "visoka"|"srednja"|"niska"` to the classification prompt,
  enum-guarded (fail-safe to `"niska"` for any unrecognized/missing value — same direction as
  every sibling GPT-confidence guard elsewhere in this engagement), folded into the existing
  `ai_tags` column as `_klasifikacija_pouzdanost`.

Scoping note: the debt register's own framing for `-022` mentioned "a review-queue UX
decision for low-confidence results" as part of a full fix — that specific workflow (an accept/
reject queue mirroring Smart Intake's own) is explicitly NOT built here; this fix closes the
"confidence gate" (a real, validated confidence signal now exists and is persisted) without
inventing a new review workflow, which remains a separate, later product decision.

No new algorithm, no migration.

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_006_evidence_quality_signals.py`, 7 tests, plus 1 more
verifying the `static/sw.js` cache bump (this mission touched `vindex.js`).

## Phase 5 — Original scenario rerun

Direct reproductions of both a genuine GPT failure and a genuine success confirm the failure
flag/confidence value are set correctly in each case, and that `reklasifikuj` charges/doesn't
charge accordingly.

## Phase 6 — Subsystem tests

211 tests across 18 files touching `evidence.py`/`case_evolution.py`'s evidence-classification
paths: **211 passed, 0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. **PASS.**
