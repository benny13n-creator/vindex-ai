# DUPLICATE_TRUTH_ELIMINATION_REPORT.md — Operation Single Brain, Mission 001

Ledger of every duplicate-truth / fragmented-truth finding from Phase 1 (10 forensic teams,
`docs/singlebrain/TRUTH_REGISTRY.md`, `DECISION_DEPENDENCY_GRAPH.md`, `CROSS_MODULE_CONSISTENCY_
REPORT.md`, `AI_BOUNDARY_CERTIFICATION.md`), marked CLOSED (fixed + regression-tested this
mission) or DEFERRED (named as `SINGLEBRAIN-DEBT-XXX` in `docs/architecture/
ARCHITECTURAL_DEBT_REGISTER.md`). Every CLOSED item below cites its fix commit-worthy location and
its regression test. Nothing here is asserted without a test proving it.

## CLOSED (18 items)

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 | Case-header risk field ("Rizik (ručno)") silently fell back to showing the AI-computed Cockpit value whenever the manual field was empty (the default state for every case) — Red Team's own flagship reproduction | `static/vindex.js` `pred-s-rizik` render — removed the `\|\| cockpit.procena_rizika` fallback | `test_status_panel_risk_no_longer_falls_back_to_cockpit_value` |
| 2 | A second, previously-uncatalogued hijack of the same DOM slot: document-analysis rendering regex-matched a risk word out of GPT's free-text output and overwrote the case-header risk field via `_pred_setRizik()` | Removed both call sites + the now-fully-dead function | `test_document_analysis_no_longer_hijacks_case_header_risk` |
| 3 | `routers/dashboard.py::command_center` (the app's actual home tab) read a stale, up-to-24h `predmet_istorija` risk cache while every sibling live surface was current | Rewritten to call `calculate_procesni_rizik` live per case | `test_cc_visok_rizik_reflects_live_data_not_stale_cache` |
| 4 | `routers/matter_intel.py` selected `predmet_dokumenti` WITHOUT `tip_dokaza` — missing-evidence detection always reported every expected doc type missing regardless of what was uploaded | Added `tip_dokaza` to the `.select()` | `test_matter_intel_selects_tip_dokaza` |
| 5 | `api.py::predmet_workspace` (Cockpit) had the identical missing-`tip_dokaza` bug — confirmed by Team 6 to have literally told a lawyer a document was missing when it was uploaded | Added `tip_dokaza` to the `.select()` | `test_predmet_workspace_selects_tip_dokaza` |
| 6 | `routers/ccc.py`'s `predmet_dokazi` query had no `deleted_at` filter, unlike 3 sibling canonical-risk consumers — a soft-deleted evidence row still counted toward risk | Added `.is_("deleted_at", "null")` | `test_ccc_dokazi_query_excludes_soft_deleted` |
| 7 | Health Index's "Portfolio Risk" component was permanently dead — read `predmeti.rizik_nivo`, a column already correctly excluded from its own `.select()` by a prior fix, so it always scored maximum regardless of actual risk | Computed live via `calculate_procesni_rizik` | `test_health_index_portfolio_risk_reflects_live_high_risk_cases` |
| 8 | `kontradikcije[].tezina` flowed unvalidated into `case_actions.prioritet` — an out-of-enum GPT string silently downgraded to `medium`, potentially keeping a genuinely critical contradiction out of `BLOCKED` readiness | `shared/contradiction_identity.py::normalize_tezina()`, fail-safe to `"kriticna"` | `test_case_evolution_rule3_unrecognized_tezina_does_not_silently_downgrade` |
| 9 | Same raw field, second independent silent-default in `shared/gap_engine.py`'s `tezina→pouzdanost` mapping | Same `normalize_tezina()` | `test_gap_engine_unrecognized_tezina_does_not_silently_downgrade` |
| 10 | `digital_twin.py::kreiraj_simulaciju` had only the conditional readiness-tier cap on scenario `verovatnoca`, no unconditional 0-100 clamp | Added unconditional clamp before the tier cap | `test_digital_twin_kreiraj_simulacija_has_unconditional_probability_clamp` |
| 11 | `digital_twin.py::sta_ako_analiza` — same gap | Same fix | `test_digital_twin_sta_ako_has_unconditional_probability_clamp` |
| 12 | `court_predictor.py::prediktuj_ishod` — same gap, plus no `min<=max` ordering check on `procenat_min`/`procenat_max` | Unconditional clamp + ordering swap | `test_court_predictor_has_unconditional_probability_clamp_and_ordering_fix` |
| 13 | Opponent Intel's `pouzdanost` was mostly GPT self-declared — forced to `"niska"` only when data was literally zero; one thin RAG hit let a `"visoka"` claim pass unchecked | Enum-validated + evidence-volume-tiered (<3 real hits caps `"visoka"`→`"srednja"`) | `test_opponent_intel_pouzdanost_is_enum_validated_and_evidence_tiered` |
| 14 | `genome_kompletnost`'s -15 penalty in `compute_snaga_score()` only fired for the exact literal `"niska"` — a synonym/typo/non-string value silently skipped the penalty | Enum-normalized, fail-safe to applying the penalty when uncertain; absent field still correctly no-ops (preserves tested baseline) | `test_compute_snaga_score_unrecognized_kompletnost_still_applies_penalty` |
| 15 | `_CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}` independently copy-pasted in 3 files | Single `CAP_BY_READINESS` constant in `shared/case_readiness.py`, all 3 files import it | `test_cap_by_readiness_is_a_single_shared_constant` |
| 16 | `routers/conflict_check.py`'s active-status set used `"u toku"` (space) while 3 other modules recognize `"u_toku"` (underscore) — a landmine for conflict-of-interest screening | Both spellings recognized | `test_conflict_check_recognizes_underscore_u_toku_as_active` |
| 17 | `routers/client_portal.py`'s "upcoming critical deadlines" query filtered on `["kritican", "vazno"]` — spellings no real writer produces; this client-facing section matched zero rows in practice | Derived from `VAZNOST_TO_CANONICAL` instead of a 4th hardcoded vocabulary | `test_client_portal_kriticni_rokovi_filter_uses_canonical_vaznost_words`, `test_client_view_kriticni_rokovi_filter_uses_real_writer_spelling` |
| 18 | `VAZNOST_TO_CANONICAL` had no key for `"važan"`/`"informativan"` — both actively written by `api.py`'s GPT extraction prompt and `routers/intake.py` — silently mis-tiered as MEDIUM | Added both keys (`"važan"→HIGH`, `"informativan"→INFORMATIONAL`) | `test_vaznost_to_canonical_covers_all_actively_written_values` |
| 19 | Case Ready Score's own 2 render sites showed different labels ("Predmet zahteva dopunu" vs "Predmet u pripremi") for the identical bottom score bucket | Aligned both to the same label | `test_case_ready_score_low_bucket_label_matches_across_render_sites` |
| 20 | CIO's top-level briefing `pouzdanost` was GPT self-declared and never validated, unlike its own sibling fix in `case_intelligence.py` | Enum-validated, fail-safe to `"niska"` | `test_cio_top_level_pouzdanost_is_enum_validated` |

(Table numbered 1-20 for readability; 18 distinct code changes — items 8/9 and 10/11 are each one
fix reaching two call sites.)

## DEFERRED — named as debt, not silently dropped

See `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` for `SINGLEBRAIN-DEBT-001` through
`-014`, each with the specific evidence citation from Phase 1's forensic reports. Summary:

- **Structural, large-scope** (deliberately not attempted this pass — each would need its own
  dedicated investigation, not a mechanical fix): Case Readiness's 2 live co-rendered sources
  (canonical `case_readiness.py` vs. `case_pipeline.py::calculate_case_ready_score`); the
  remaining 12 of 15 Confidence mechanisms (including 2 fully-dead subsystems); Portfolio
  Case-Strength Aggregation divergence between `health_index.py`/`cio.py`; the broader
  `predmeti.status` 5-way classifier fragmentation.
- **Compounding/edge-case gaps in fixes already made**: the readiness-tier cap silently no-ops
  when `build_case_context()` throws (the new unconditional clamp mitigates but doesn't fully
  close this); `court_predictor.py::argument_reputation` is range-clamped but not readiness-capped.
- **Known, self-acknowledged, pre-existing**: two independent notification generators; `GET
  /briefing/poslednji`'s frozen snapshot with no staleness marker; `predmet_istorija`'s `"[Rizik]"`
  cache tag's 2 independent writers (currently safe — every live reader this mission touched
  correctly treats it as historical-only, never "current").
- **Not investigated this mission at all**: Kanban board's closed-case visibility; CIO's
  `neprimecena_kontradikcija` re-hallucinating an already-computable fact; Strategy's
  `_advisory_provenance()` disclosure object computed but never rendered; `routers/copilot.py::
  _handle_predlozi`'s priority-engine bypass.

## What "single brain" means after this mission, honestly

The deterministic backbone (`risk_engine.py` → `case_evolution.py` → `case_readiness.py` →
`CAP_BY_READINESS` → frontend) is a genuine, cycle-free, single-sourced pipeline, confirmed
independently by 4 parallel research passes in Phase 1 and re-confirmed against 100-contradiction/
1000-document synthetic scale in Phase 4. Every fragmentation this mission's own founder mandate
asked to hunt for ("makar jednu situaciju gde dva modula različito tumače isti predmet") that was
found IN that backbone or in its immediate GPT-boundary guards was closed. What remains
fragmented — Confidence's long tail, the 2 co-rendered readiness scores, the status classifier
sprawl — sits mostly OUTSIDE that backbone, in independently-evolved advisory features that were
never claimed to share one engine. That distinction is the actual scope boundary this report draws,
not a claim that zero fragmentation remains anywhere in the platform.
