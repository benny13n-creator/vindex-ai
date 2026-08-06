# Case Commander Consolidation — Program Tau, Master Sprint 007, Phase 3

Migrates `routers/case_commander.py` off its own independent 2nd (and, for the portfolio digest, 3rd)
computation of risk/gaps/readiness onto `shared/case_context.py::build_case_context()`'s own already-computed
output — closing `PARALLEL_REASONING_AUDIT.md`'s own Finding 1 (this file's own instance) and Findings 2-4
(within-file duplication, a confidence-mapping bug, and a Genome-blind portfolio ranking), all specific to
this file.

## Forensic pre-check: live frontend caller status, re-verified not assumed

`grep -n "/api/commander/" static/vindex.js` finds exactly one hit — a comment, not a `fetch()` call. All 5
endpoints (`analiza`, `quick-check`, `checklist`, `jutarnji`, `jutarnji/refresh`) are confirmed dead in the
live frontend today, extending and re-confirming Sigma 005's own prior claim rather than trusting it
unchecked. This gave real freedom to reshape internals without live-UI risk — used conservatively anyway
(field names/shapes preserved) since a non-frontend consumer could still exist.

## What changed

### `_kanonski_nalazi` (single-case: `commander_analiza`, `commander_quick_check`)

Before: called `calculate_procesni_rizik`/`identify_case_problems`/`collect_case_gaps`/`compute_case_readiness`
directly on data `_dohvati_predmet_kontekst` fetched independently (`case_actions`, `predmet_dokazi`, `rocista`
— 3 of that function's own 7 queries, existing SOLELY to feed this now-removed computation).

After: `await build_case_context(predmet_id, uid, supa, include_documents=False)` (lightweight mode — no
document excerpts needed for readiness/gaps text), wrapped in an inline `try/except` (no new helper function
— literal, per this sprint's own explicit "ne praviti novi helper/wrapper" instruction — `_kanonski_nalazi`
itself became `async` and calls `build_case_context()` directly at its own single call site). On failure or a
`predmet_not_found` error: degrades to `UNKNOWN` readiness, empty gaps, empty actions — never raises.

The 3 now-unnecessary bespoke fetches (`case_actions`, `dokazi`, `rocista`) were removed from
`_dohvati_predmet_kontekst` entirely — they had no other consumer in the file.

### 2 behavior changes, both named, both correctness improvements not regressions

1. **`nedostaje` now includes ALL of `missing_evidence`**, not the old narrower 3-of-5-gap-type filter
   (`NEMA_DOKAZA`/`NEDOSTAJE_DOKUMENT`/`GENOME_NEDOSTAJE` only). The old filter silently excluded
   `KRITICAN_ROK`/`PREDSTOJECI_ROKOVI`-classified items — an unintentional gap in the pre-migration code,
   not a deliberate design choice (`PARALLEL_REASONING_AUDIT.md` Finding 2). Fixed as a byproduct of reading
   the canonical field wholesale rather than re-filtering it.
2. **`rizici`'s own confidence mapping is now correct.** The old code used a binary rule
   (`"visoka" if ozbiljnost=="kritican" else "srednja"`); `shared/gap_engine.py`'s own canonical mapping
   ALSO grants `"visoka"` to `"vazan"`, not just `"kritican"` — meaning the SAME underlying
   `identify_case_problems` finding could disagree with itself between `case_commander.py`'s own `rizici`
   field (`"srednja"`) and `nedostaje` field (`"visoka"`) for a `"vazan"`-severity problem
   (`PARALLEL_REASONING_AUDIT.md` Finding 3). `rizici` is now reconstructed by filtering the already-computed
   `missing_evidence` list on its own `izvor == "identify_case_problems"` tag — same source, same content,
   ONE confidence rule instead of two disagreeing ones, and zero 2nd call to `identify_case_problems`.

### `_kanonski_prioritet_i_rizici` / `_dohvati_sve_predmete_za_analizu` (portfolio: `commander_jutarnji`)

Before: `compute_case_readiness(actions, [])` — an ALWAYS-EMPTY `gaps` argument, meaning the portfolio-wide
"which case needs attention today" ranking had zero Genome/contradiction/missing-evidence awareness, the
least-informed readiness computation of the whole 6-module family found in Phase 2 (`PARALLEL_REASONING_AUDIT.md`
Finding 4).

After: `_dohvati_sve_predmete_za_analizu` loops `build_case_context(p["id"], uid, supa, include_documents=False)`
across all fetched active cases (`asyncio.gather`, same established pattern `morning_briefing.py` already
uses for its own portfolio digest) and attaches each case's own real `readiness`/`active_actions` onto the
predmet dict. `_kanonski_prioritet_i_rizici` now only READS the pre-attached `_readiness`, never computes it
— a genuine completeness fix (real gap-awareness in portfolio prioritization for the first time), not just a
duplication removal. The old bespoke `case_actions` batch fetch (`.in_("predmet_id", predmet_ids)`) was
removed — no longer needed, its one consumer now reads `active_actions` from `build_case_context()` instead.

**A new, deliberate default**: when `_readiness` is missing (a per-case `build_case_context()` failure, or
this key genuinely absent), the case defaults to `UNKNOWN`, not a guessed `READY` — the old code's own
implicit `compute_case_readiness(actions, [])` default (`genome_computed=True` by that function's own
signature default) silently treated "we have no signal" as "this case is fine." `UNKNOWN` is the more
honest, more conservative default. Named explicitly, not silently changed.

## What did NOT change

`rokovi` table fetch (GPT-formatting text only, no canonical equivalent — the SAME `TAU-013` rokovi/rocista
split independently confirmed a 5th time across this whole program). `predmet_dokumenti`/`predmet_komentari`
fetches (GPT-formatting text, out of this sprint's own reasoning-consolidation scope — a Tau-006-Factory-
style context-injection concern, not a duplicate-computation concern). The 2 genuinely GPT-advisory fields
(`protivnikova_strategija`, `sudska_praksa`) and their own system prompt — untouched, still explicitly
scoped to exactly those 2 questions with no canonical source (Sigma 005's own GPT Boundary Policy, confirmed
still correct in Phase 5). `commander_checklist`'s own generic procedural template generation — untouched,
not part of the risk/readiness/gaps reasoning family.

## Migration completeness (structural proof, not asserted)

`tests/test_tau007_case_commander_consolidation.py::test_no_direct_calls_to_duplicated_reasoning_functions`
walks the file's own AST (not a string grep — a comment mentioning these names doesn't produce a false
pass) and confirms zero `Call` nodes anywhere invoke `calculate_procesni_rizik`, `identify_case_problems`,
`collect_case_gaps`, or `compute_case_readiness`. A full `supa.table()` inventory confirms `case_actions`,
`predmet_dokazi`, `rocista` are gone; only `predmeti`/`rokovi`/`predmet_dokumenti`/`predmet_komentari`
(GPT-formatting text, no canonical equivalent) and the write/cache tables (`commander_analize`,
`commander_jutarnji`) remain.

## Tests

19 new tests (`tests/test_tau007_case_commander_consolidation.py`): end-to-end endpoint wiring against a
mocked `build_case_context()`, fail-soft degradation, a GPT-boundary adversarial test (a poisoned advisory
response tries to smuggle a fake `readiness_status`/`prioritet` claim — proven inert, since those fields are
built before the GPT call and never re-read from its output), concurrency (2 cases via `asyncio.gather` don't
cross-contaminate), replay stability, and the 2 structural AST-based completeness proofs above. 44
pre-existing tests updated across `tests/test_sigma_sprint005_commander_consolidation.py` (mock
`build_case_context` instead of passing raw bespoke-fetched fixtures; `_readiness` now attached explicitly
per portfolio-ranking test fixture) and `tests/test_celina2_predictor_commander_2026_07_24.py` (1 fixture
given an explicit `_readiness: READY` to preserve its own original "nothing deterministic to report" intent
now that an absent `_readiness` correctly defaults to `UNKNOWN`).
