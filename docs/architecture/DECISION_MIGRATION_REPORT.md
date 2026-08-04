# Decision Migration Report — Program Gamma (Masterprompt 003), Phase 6

Concrete before/after for every code change this mission made, in the order
implemented, each with its own test evidence — same discipline as Program
Alpha's `CANONICAL_MIGRATION_PLAN.md`: one canonicalization at a time, full
test suite after each, revert if it gets more complicated than diagnosed.
None did.

## 1. `case_intelligence.py::case_intelligence_briefing` — live bug fix (not a canonicalization, a correctness fix)

**Before**: `_gather_case_data`'s `proactive_alerts` query selected
`tekst_alerta, tip_alerta, hitnost` — none of which exist on the real table
(`tip, naslov, opis, urgentnost` per `migrations/036_decision_log.sql`).
The enclosing `asyncio.gather` had no `return_exceptions=True`, so this
almost certainly 500'd the endpoint on every call — an endpoint wired to a
live UI button since Mission IF-002 (2026-08-03).

**After**: query corrected to real column names; `return_exceptions=True`
added with per-query exception logging and graceful degradation; rendering
code (`_build_context_text`) corrected to read `opis`/`urgentnost`.

**Hardened after Olympus Faza 10 governance review (2026-08-04)**: the
initial fix put the ownership-check query (`predmeti`, the only
authorization check in this function) inside the same fail-soft gather as
the 5 enrichment queries — Security Review found a transient DB error on
that specific query would then silently report as "Predmet nije pronadjen"
(404) instead of a real error (500), losing visibility (fail-closed, not a
security bypass, but an observability regression). Moved to its own
awaited call before the gather, matching `evidence_graph.py`'s established
pattern. Separately, Architecture Review found the original `SimpleNamespace(data=None)`
substitution was a **third** independent idiom for "gather with partial
failure" in this codebase (`evidence_graph.py` and `matter_intel.py` each
already had their own) — replaced with `matter_intel.py::_d()`, an
existing shared helper built for exactly this shape (Faza 2.2, 2026-07-18),
reused rather than a fourth idiom added.

**Tests**: `tests/test_case_intelligence_briefing_alerts_fix.py` (3 new) —
proves correct column usage, proves the endpoint survives a sub-query
failure (negative control reproducing the exact pre-fix shape), proves
correct rendering. All 3 re-verified passing against the refactored
implementation.

**Why first**: found independently by 2 domain forks, confirmed the single
most severe finding in this mission by the Risk/Task/Dashboard/Alerts fork
— a broken decision endpoint is worse than a duplicated one.

## 2. Evidence Chain widening — `evidence_graph.py` + `case_commander.py` (DC-009 migration)

**Before**: both files had zero of the three Evidence Chain links
(provenance/evidence-validation/UI trust signal) Program Beta's own
registry treats as the platform standard — the exact class Beta fixed for
`compare_docs`, found here at ~2x the scale (2 more files/endpoints,
7 total across the full consumer layer per the Genome/Evidence/Compare
fork, of which this mission closed 2).

**After**:
- `shared/genome_validator.py` gained 2 new functions generalizing
  `validate_dok_reference`'s "referenced entity must exist in scope"
  principle to 2 new ID schemes: `validate_graph_edge_references` (graph
  node ids) and `validate_predmet_reference` (predmet ID prefixes).
- `evidence_graph.py::generisi_graf` wrapped in `case_context()`, its
  output evidence-checked, `_evidence_check` added to the response and
  persisted alongside the graph.
- `case_commander.py::_cross_case_analiza` wrapped in `case_context()`,
  its `nalazi`/`prioritet` fields evidence-checked against the actual set
  of predmeti analyzed, `_evidence_check` added to the response.

**Hardened after Olympus Faza 10 governance review (2026-08-04)**, 4
separate findings, all fixed same pass:
1. **Dead-signal regression (Evidence Integrity + Security, 2 reviewers
   converged)**: `_evidence_check` was computed and even persisted for both
   new call sites but never read by the frontend — unlike `compare_docs`'s
   own correctly-wired version. Worse, Evidence Graph's reload endpoint
   (`get_graf`) didn't return the persisted flag at all, so it existed only
   for the instant after generation and was then permanently unrecoverable.
   Fixed: `get_graf` now returns `_evidence_check` from the persisted
   `podaci`; `evidenceGraph_generiši`/`evidenceGraph_load` now surface a
   warning toast when flagged; Case Commander's morning-briefing UI now
   marks the specific flagged finding items (not a generic banner) with an
   inline warning.
2. **Attribution gap (Evidence Integrity)**: `validate_predmet_reference`
   originally checked only that a referenced predmet ID prefix *exists* —
   a finding with a real prefix but *misattributed* to the wrong predmet's
   name/facts (GPT confusing two cases in the same portfolio) was
   architecturally invisible. Now also checks `predmet_naziv` against the
   real naziv for that prefix (fuzzy, case-insensitive) when both are
   present — signature changed from a bare `set` of prefixes to a
   `dict[prefix, naziv]`.
3. **Missing Sentry visibility (Architecture Review)**: both new
   evidence-check `except` blocks logged via `logger.warning` only, unlike
   the `compare_docs` reference implementation and `case_commander.py`'s
   own 4 other exception sites in the same file — both now also call
   `_sentry_capture()`.
4. **Case Commander invariant note (Decision Consistency Auditor)**: no
   code defect found, but the auditor flagged that `poznati`/`predmeti_txt`
   sharing consistency is currently enforced only incidentally (single
   caller, shared local variable) — worth a comment if this function ever
   gains a second caller. Not fixed (no live bug), noted for future
   maintainers.

**Tests**: `tests/test_genome_validator.py` (+10 new total: 4 for
`validate_graph_edge_references`, 6 for `validate_predmet_reference`
including the new attribution-mismatch cases), `tests/test_gamma_evidence_check_wiring.py`
(6 total: flags-invented-node, approves-valid-graph, flags-invented-predmet,
approves-valid-cross-case, flags-misattributed-naziv, plus the `_delta_hitnost`
unit test from item 5 below).

**Why this scope, not the full 7-endpoint consumer layer**: `case_commander.py`'s
other 3 endpoints and `matter_intel.py`'s 2 endpoints have different output
shapes than `_cross_case_analiza`/`generisi_graf` — wiring all 7 correctly
in one pass risked exactly the "rushed, under-verified" pattern this
session's own discipline exists to prevent. The 2 done here are (a) the
domain's most-used single call sites (the daily morning briefing, and
Evidence Graph's only AI endpoint) and (b) a clean proof the pattern
generalizes to a 3rd ID scheme without modification to the underlying
principle. The remaining 5 are named, prioritized, deferred (`GAMMA-003`/
`GAMMA-004`).

## 3. `strategija.py` — Synthesis conflict detection (DC-011)

**Before**: `detektovani_konflikti` was decided entirely by the Synthesis
LLM's own prose judgment, despite the prompt itself naming 2 structurally-
checkable example conflicts using categorical fields (`korak1.ocena`,
`korak4.ukupna_ranjivost`, etc.) already present in the function's own
`kontekst` variable — the identical shape to `sistemsko_upozorenje`, fixed
in this exact function, this exact mission-day, by Program Beta, 20 lines
above.

**After**: 2 named categorical co-occurrence checks now run in code and
append (not replace) to whatever the LLM's own `detektovani_konflikti` list
contains — preserving the LLM's genuine semantic-level conflict detection
(which requires prose understanding no enum comparison can replicate) while
guaranteeing the 2 structurally-checkable cases are never missed.

**Refined after Olympus Faza 10 governance review (2026-08-04, 3 independent
findings converging on this one change — Workflow Integrity, AI Governance,
Legal Domain Expert)**:
1. **Duplicate-listing risk closed**: the Synthesis prompt (`_ORK_SYNTHESIS_SYSTEM`
   rule 2) still named the exact 2 conflict examples now hardcoded in
   code — Program Beta's own precedent (removing the equivalent
   `sistemsko_upozorenje` prompt rule the same day) was not initially
   applied here. Fixed: the prompt now explicitly tells the LLM these 2
   combinations are handled deterministically and to focus on genuinely
   semantic conflicts instead, removing the risk of the same finding
   appearing twice in different words.
2. **False-positive/alert-fatigue risk reduced**: rule 1's wording softened
   from an assertive "↔ nekonzistentna ocena" framing to a hedged "moguća
   napetost — proverite," since the prompt's own example qualifies this
   pairing with "zbog iste klauzule" (a causal link the code cannot verify)
   and a well-drafted document supporting a substantively weak case is
   legally normal, not a defect.
3. **Category-error risk closed**: rule 2 (Due Diligence NEPRIHVATLJIV vs.
   AI Sudija TUZBA USVOJENA) is now gated on `korak2.preporuka` being
   litigation-shaped (`PODNETI`/`ISPRAVITI_PA_PODNETI`/`NE_PODNETI`) —
   Korak 5 (the simulated judge) runs unconditionally even for
   transactional (non-litigation) matters, where comparing against a
   fabricated lawsuit verdict would be a category error, not a legal
   disagreement.

**Tests**: `tests/test_strategija_sistemsko_upozorenje.py` (+5 new total) —
proves both conflict rules fire correctly, proves the LLM's own findings
are preserved (additive, not overwritten), proves no false positive when
categories don't collide, proves rule 2 does NOT fire for a transactional
(contract-shaped) matter even when the same categorical values co-occur.

## 4. `routers/court_predictor.py` — derived categorical fields (DC-012)

**Before**: `argument_reputation`'s `boja` field and `judge_profile`'s
`pouzdanost_profila` (5-9 decision band specifically) were returned raw
from the LLM despite the prompt stating a checkable derivation rule for
each — the identical defect class Program Beta named and fixed for
`sistemsko_upozorenje`, undiagnosed here because Beta's own domain fork
scoped its Court Predictor coverage to `confidence_check` only.

**After**: `boja` is now derived in code from the same `uspesnost_procena`
number the call already returns, for every item in `argumenti_analiza`.
`pouzdanost_profila`'s previously-uncovered middle band (5-9 odluke, which
fell through the existing `if`/`elif` and silently passed the raw LLM value
through) now has an explicit `else` branch.

**Hardened after Olympus Faza 10 governance review (2026-08-04, AI
Governance)**: the initial `boja` fix only recomputed when `uspesnost_procena`
was already an `int`/`float` — since `response_format=json_object` only
guarantees valid JSON, not that a field matches its documented schema type,
a numeric-string value (`"72"` instead of `72`) would have silently skipped
recomputation and let the raw, potentially-inconsistent LLM `boja` through
unchanged. Now attempts a safe numeric coercion first.

**Tests**: `tests/test_court_predictor_deterministic_derived_fields.py`
(2 new) — proves an internally-inconsistent raw LLM `boja` gets corrected,
proves the middle confidence band is no longer a passthrough.

## 5. `routers/case_dna.py` — deduplicated alert-urgency formula (DC-006)

**Before**: `hitnost = "hitna" if snaga_d >= 15 or delta_obj.get("kontr_nove", 0) > 1 else "normalna"`
existed byte-identically at 2 call sites (auto-refresh and manual-refresh
paths) — not a live bug (identical code cannot diverge), but exactly the
"two independent authors, one edit from silent divergence" shape this
mission is chartered to eliminate, sitting directly beside `_delta_significant`/
`_delta_alert_text`, which were ALREADY correctly extracted as shared
helpers in the same file.

**After**: extracted to `_delta_hitnost(delta)`, both call sites updated.

**Tests**: `tests/test_gamma_evidence_check_wiring.py::test_delta_hitnost_extracted_helper_matches_original_formula`
(1 new) — proves the extracted function reproduces the exact original
formula (both threshold branches).

## Rollout discipline followed

Each of the 5 items above was implemented, tested, and verified independently
(full targeted test run after each — 137 tests green across all touched
files before the full-suite run). None required a revert. None grew in
scope beyond its original diagnosis. This mirrors Program Alpha's own
"one canonicalization at a time" discipline exactly, applied here to a
different (decision-fragmentation, not structural-duplication) defect
class.

## Explicitly not migrated — full reasoning in `DECISION_CONSUMER_MAP.md` and `ARCHITECTURAL_DEBT_REGISTER.md`

Nothing in the "Fragmented" table of `DECISION_REGISTRY.md` beyond the 5
items above was touched. This is deliberate, not an oversight — see
`DECISION_CONSISTENCY_REPORT.md`'s closing section for the mission's own
honest accounting of what remains open and why.
