# CANONICAL_VALUE_MAP.md — Operation Single Brain, Mission 001

The single authoritative source for each of the 6 named values, as they stand after Phase 3
implementation (2026-08-07). "Canonical" means: this is the ONE function/column a new caller
should read from — not a survey of every place the concept is touched (see `TRUTH_REGISTRY.md`
and `DECISION_DEPENDENCY_GRAPH.md` for the full inventory this map is distilled from).

## Risk

**Canonical**: `services/risk_engine.py::calculate_procesni_rizik(dokazi, dokumenti, rocista,
tip_predmeta, expected_docs)` — pure function, zero GPT calls, zero DB I/O. Returns
`{"nivo": "Nizak"|"Srednji"|"Visok", "health_score", "nedostajuci_dokazi", "predstojeći_rokovi",
"kriticni_rocista"}`.

**Now live everywhere that renders "risk" on a screen** (closed this mission):
`routers/dashboard.py::command_center` (the app's home tab) and `routers/health_index.py`'s
Portfolio Risk component both used to read a stale/dead value instead — both now call the
canonical function live, per case, every request.

**Explicitly NOT canonical, still present, still must not be read as "current risk"**:
`predmeti.rizik` (a lawyer's own manual note — the Status panel now labels and shows ONLY this,
never silently substituting the live value); `predmet_istorija`'s `"[Rizik] {date}"` rows (a
historical snapshot cache with 2 independent, mutually-unaware writers — legitimate ONLY for a
"did risk change since last look" diff, e.g. `pad_procene`, never for "current").

## Readiness

**Canonical**: `shared/case_readiness.py::compute_case_readiness(case_actions, gaps,
genome_computed)` — deterministic 5-state enum (`READY`/`PARTIALLY_READY`/`BLOCKED`/
`CRITICAL_GAP`/`UNKNOWN`), zero GPT calls, no parameter through which a GPT value could reach it
(verified this mission via signature inspection, `test_singlebrain_phase4_scale_and_adversarial.py
::test_adversarial_readiness_has_no_gpt_input_path`).

**Consumed via**: `shared/case_context.py::build_case_context()["readiness"]`, then the shared
`CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}` constant (now genuinely single-sourced from
`shared/case_readiness.py` — closed this mission; previously 3 independently copy-pasted dict
literals in `court_predictor.py`/`digital_twin.py`/`hearing_cc.py`).

**Not eliminated, named as debt** (`SINGLEBRAIN-DEBT-001`): `services/case_pipeline.py::
calculate_case_ready_score` remains a second, live, independently-computed 0-100 readiness-
adjacent score, co-rendered on the same case screen as the canonical-capped AI panels. This
mission closed the *label* mismatch between its own two render sites (both now say "Predmet
zahteva dopunu" for the bottom bucket) but did not eliminate the score itself as a second source —
see `DUPLICATE_TRUTH_ELIMINATION_REPORT.md`.

## Priority (case_actions.prioritet)

**Canonical**: `case_actions.prioritet` — `critical`/`high`/`medium`/`low`, DB-enforced (migration
099 CHECK constraint), sole writer `services/case_evolution.py::_consequence_refresh_case_actions`.
Read-side translation for every other vocabulary: `shared/attention_priority.py`.

**Closed this mission**: Rule 3's own `tezina→prioritet` mapping (and `gap_engine.py`'s parallel
`tezina→pouzdanost` mapping) both used to silently default any unrecognized GPT `tezina` string to
their respective middle bucket. Both now go through `shared/contradiction_identity.py::
normalize_tezina()` — one canonical enum guard, fail-safe toward the most conservative bucket
("kriticna"), used by both consumers.

**Not eliminated, named as debt** (`SINGLEBRAIN-DEBT-005`): `routers/copilot.py::
_handle_predlozi` still computes its own ad hoc 3-value priority directly from deadline
proximity, bypassing `shared/attention_priority.py` entirely.

## Health

**Canonical**: `routers/health_index.py::_compute_health` — deterministic weighted sum, clamped.
GPT (`_compute_chief_partner`) produces only a separate narrative string, never fed back into the
numeric score.

**Closed this mission**: the Portfolio Risk sub-component was permanently dead (read a column
excluded from its own `.select()` by a prior fix, so it silently maxed out its score every time,
confirmed by 3 independent teams) — now computed live via `calculate_procesni_rizik`.

## Success Probability

**No single canonical source — 4 independent GPT-authored percentages by design**
(`court_predictor.py::prediktuj_ishod`, `court_predictor.py::argument_reputation`,
`digital_twin.py` ×2 endpoints, `hearing_cc.py::hearing_score`). What this mission unified is not
the *number* (each answers a genuinely different question) but the **guard discipline** around
each: every one of the 4 (`argument_reputation` was already correctly range-clamped; the other 4
call sites across 3 files were the gap) must now apply an unconditional `max(0, min(100, …))`
range clamp BEFORE the stricter, conditional `CAP_BY_READINESS` tier cap — closed this mission for
Digital Twin's 2 endpoints and Court Predictor's `prediktuj_ishod` (which also gained a
`min<=max` ordering guard it never had).

**Not eliminated, named as debt** (`SINGLEBRAIN-DEBT-010`): the readiness-tier cap itself still
silently no-ops when `build_case_context()` throws (`if case_context and not
case_context.get("error"):` skips the cap entirely on fetch failure) — the unconditional clamp
added this mission is a genuine, verified mitigation (a wild GPT number can no longer escape
0-100), but a case that is genuinely `CRITICAL_GAP` could still see up to 100% during a transient
context-fetch failure, not the tier-appropriate 50%.

## Confidence

**No single canonical source — 15 independently-verified mechanisms, most legitimately distinct
concepts** (Court Predictor's Confidence Check is the cleanest: derived purely from RAG/VKS-hit
counts and firm win-rate, GPT explicitly forbidden from stating a number at all). This mission
closed the enum-validation gap on 2 of the 15 (`routers/court_predictor.py`'s Opponent Intel
`pouzdanost` — now enum-validated AND evidence-volume-tiered so a single thin RAG hit can no
longer buy an unchallenged "visoka"; `routers/cio.py`'s top-level briefing `pouzdanost` — now
enum-validated matching its own sibling fix in `case_intelligence.py`) plus the fully-shared
`genome_kompletnost` field (`shared/genome_validator.py::compute_snaga_score` — was matched only
against the exact literal `"niska"`, silently skipping its own -15 penalty for any synonym/typo/
non-string GPT value; now enum-normalized, fail-safe toward applying the penalty when uncertain).

**Not eliminated, named as debt** (`SINGLEBRAIN-DEBT-004`): the remaining 12 confidence
mechanisms — most prominently the fully-dead `services/confidence_calibrator.py` and Confidence
Audit/Brier-score subsystem (the column it depends on, `recommendation_log.confidence_band`, is
never written by any code path), Client Twin's unenforced self-declared `pouzdanost`, and RAG/
Precedent retrieval computing 2 different confidence formulas inside the same function call.

## Importance (predmet_hronologija.vaznost) — fully reconciled this mission

Previously a genuine 3-way vocabulary mismatch, closed in full: the write path (`api.py`'s GPT
extraction prompt + `routers/intake.py`'s static templates) writes `{"kritičan", "važan",
"informativan"}`; the canonical read-side translator, `shared/attention_priority.py::
VAZNOST_TO_CANONICAL`, previously recognized only `{"kritičan", "bitan", "normalan", "ostalo"}` —
meaning every actively-written `"važan"`/`"informativan"` row silently fell through to the MEDIUM
default. Now `VAZNOST_TO_CANONICAL` covers the full actively-written vocabulary (`"važan"→HIGH`,
`"informativan"→INFORMATIONAL`). `routers/client_portal.py`'s own "upcoming critical deadlines"
query independently hardcoded a 3rd, wrong-spelling literal set (`["kritican", "vazno"]` — no
writer ever produces either spelling) that matched zero rows in practice; now derived directly
from `VAZNOST_TO_CANONICAL` itself, so it can never drift from the same source again.

## Status (predmeti.status) — partially reconciled

**Not a single canonical classifier.** Only `"aktivan"`/`"zatvoren"` are ever actually written, but
5 different modules classify "active" via 5 non-identical predicate sets. This mission closed one
specific, confirmed landmine: `routers/conflict_check.py`'s own active-status set used `"u toku"`
(space) while `cio.py`/`morning_briefing.py`/`klijenti/router.py` all already recognize `"u_toku"`
(underscore) — a case ever stored with the underscore spelling would have silently fallen out of
conflict-of-interest screening. Both spellings are now recognized by `conflict_check.py`.

**Not eliminated, named as debt** (`SINGLEBRAIN-DEBT-013`): the broader classifier-logic
fragmentation across `analytics.py`/`copilot.py` (closed = `("zatvoren","arhiviran")`),
`dashboard.py` (active = "not in a 3-value closed set"), and `cio.py`/`morning_briefing.py`/
`zakon_monitoring.py` (active = a 3-value allow-list) remains — currently low-risk only because no
writer produces a value outside `{"aktivan","zatvoren"}` today.
