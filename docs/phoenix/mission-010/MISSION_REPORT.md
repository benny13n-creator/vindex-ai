# Program Phoenix — Mission 010: Drafting RAG Grounding (CRITICAL)

**Date**: 2026-08-08
**Debt items addressed**: `LIVINGSYS-DEBT-013` (fully — the debt register's own "single most
severe finding").

## Why this mission stands alone

Unlike every prior mission, this is a single, real feature-scope change explicitly named by the
debt register as too large to bundle: porting `/api/podnesak`'s proven RAG retrieval + critique-
pass infrastructure into `/api/nacrt`'s quick-draft path. Minimum files touched given the scope:
2 production files plus 1 new shared module extracted to avoid duplicating the ported logic.

## Phase 1 — Reproduction

Confirmed `drafting/router.py::generate_draft` (backing `/api/nacrt`) asks GPT to fill fields
like `tuzba_naknada_stete`'s `pravni_osnov_clan` ("Broj člana ZOO koji se primenjuje za naknadu")
purely from the extraction prompt, with:
- zero RAG retrieval — no legal source text is ever given to the model to ground the choice
- zero critique/verification pass — the extracted value goes straight into `_popuni_sablon`
  and directly into the returned document text

The debt register's own framing: "invent a specific ZOO/ZR statute article number ... embedded
directly into real legal document text." `templates.py` line 1006 and its `pravni_osnov`/
`zakonski_clan` siblings (lines 1042, 1148) are the concrete confirmed instances.

## Phase 2 — Root cause

See `ROOT_CAUSE_ANALYSIS.md`.

## Phase 3 — Fix

- **New shared module** `shared/drafting_grounding.py` — `izvori_kontekst()` (the `[IZVOR-n]`
  formatter) and `CRITIQUE_SYSTEM` (the critique prompt) moved here as the single canonical
  owner; `routers/drafting.py` now imports both instead of defining its own copies (proven
  identical via `is` checks in the new test suite).
- **`drafting/router.py::generate_draft`** gained:
  1. A RAG retrieval step (`_RAG_AVAILABLE` guard, same shape as `court_predictor.py`'s own
     flag) — queries `retrieve_documents` with `f"{tpl['label']}: {opis[:400]}"`, builds
     `kontekst` via `izvori_kontekst()`, fails open to `kontekst=""` on any exception.
  2. The `kontekst` block injected into the extraction prompt's user message (better-grounded
     first-pass field choices when sources are available).
  3. A new sync function `_kriticki_pregled()` — a synchronous port of `_critique_and_refine_draft`
     (same prompt, same JSON schema, same fallback logic, same `(nacrt, critique_applied)`
     return shape from Mission 009) — run on the AI-generated document text BEFORE the
     deterministic compliance report is appended, so the critique model never touches
     non-GPT-generated content.
  4. `critique_applied` added to `generate_draft`'s return dict.
- **`routers/drafting.py::_normalizuj_rezultat`** now forwards `critique_applied` when present,
  so `/api/nacrt`'s response carries it exactly like `/api/podnesak`'s (Mission 009).
- **`static/vindex.js`**: the Mission 009 warning banner's trigger condition
  (`d.critique_applied === false`) was already endpoint-agnostic — only its stale comment
  (claiming the field was podnesak-only) needed updating; no functional JS change needed for the
  banner to now also cover `/api/nacrt`.
- `-014` (the "blank vs. omit field" prompt-engineering debt, deliberately named as a *separate*
  item requiring its own multi-template pass) was explicitly **not** touched — this mission's
  scope is grounding/verification only, per the debt register's own boundary.

`static/sw.js` `CACHE_NAME` bumped `vindex-v102` → `vindex-v103` (comment-only `vindex.js`
change, bumped per this engagement's standing convention regardless of triviality).

## Phase 4 — Regression tests

New file: `tests/test_phoenix_mission_010_drafting_rag_grounding.py`, 10 tests. 5 pre-existing
tests in `tests/unit/test_drafting.py` updated to disable RAG (`_RAG_AVAILABLE=False`) so they
don't attempt a real network call — none of their existing assertions needed weakening.

## Phase 5 — Original scenario rerun

`test_generate_draft_critique_neutralizes_hallucinated_article_number` directly reproduces the
debt item's exact scenario: an extraction step returns a specific, unconfirmed statute article
number (`"pravni_osnov_clan": "999"`), and proves the critique pass catches and replaces it
before the number reaches the final returned document text.

## Phase 6 — Subsystem tests

240 tests across `drafting/`, `routers/drafting.py`, `shared/drafting_grounding.py`,
`court_predictor.py`, `voice_realtime`, and the frontend structural suite: **240 passed,
0 failed.**

## Phase 7 — Full suite

See `TEST_RESULTS.md`.

## STOP GATE

No regression introduced, no architecture conflict, no ownership ambiguity, no
non-deterministic behavior, no canonical conflict, no unexpected production risk. Latency budget
increase (up to 2 additional blocking calls: RAG retrieval + critique) is an accepted, explicit
tradeoff the debt register itself named as the cost of closing a CRITICAL hallucination risk.
**PASS.**
