# TRUTH_REGISTRY.md — Operation Single Brain, Team 1

Every value in the platform representing risk, priority, readiness, confidence, strength, health,
probability, urgency, importance, verification, credibility, quality, severity, completeness, or status —
independently re-verified from current code (2026-08-07), not trusted from Operation One Truth's own
same-day registry. Several entries below revise that prior report's counts upward; several confirm fixes
landed the same day, hours before this audit ran.

## Summary table

| Category | Independent sources found | Risk | Named by Operation One Truth? |
|---|---|---|---|
| Risk | 8 | Critical (formula unified; manual column, stale cache, 2 dead composites, 1 silently-dead sub-score sit beside it) | Partially — undercounted |
| Priority / Urgency | ~13 vocabularies (translation layer covers ~9 cleanly) | Medium — 1 confirmed live gap | Yes, mostly |
| Readiness | 4 (2 live + 1 dead + 1 different-domain) | High — 2 co-render on the case page | Yes |
| Confidence | 15 | Critical / most fragmented category | Undercounted by more than half |
| Strength | 5 | Medium | Partially — 1 new occurrence |
| Health | 1 (compromised by 2 of its own inputs) | Low-Medium | Not separately named |
| Probability | 5 (4 GPT + 1 alias) | High, unchanged | Yes |
| Importance | 1 column, 3-way vocabulary mismatch | **High — new finding** | **No** |
| Verification | 4 live + 1 dead | Medium | Partially |
| Credibility | 0 | None — the concept doesn't exist as data | N/A |
| Quality | 1 (naming-collision with Confidence/Completeness) | Low | No — new territory |
| Severity | 3 | Medium — revises a prior "closed" verdict | Partially |
| Completeness | 3 | Low-Medium | No — new territory |
| Status | ~14+ domains + 1 same-entity collision | Medium — plus a newly-found live classifier mismatch | Partially |

## 1. Risk

Canonical formula: `services/risk_engine.py::calculate_procesni_rizik` (`:21-140`), 11+ call sites, zero GPT.
Sitting beside it: `predmeti.rizik` (manual column, no CHECK constraint, wins over the live Cockpit value at
`static/vindex.js:11905`); a `predmet_istorija` `"[Rizik] {date}"` cache tag (2 independent writers,
`api.py:5426-5459` and `services/case_pipeline.py:535-598`); a dead-but-reachable 5-axis "uncertainty"
composite in `matter_intel.py::get_uncertainty_dashboard` (`:320-390`, no frontend caller); and — new this
mission — Health Index's "Portfolio Risk" sub-component (`routers/health_index.py:182`), which reads
`p.get("rizik_nivo")`, a column the same file's own `.select()` (`:73-81`) deliberately excludes because it
doesn't exist on `predmeti`. This sub-score is **always 0 → always scores its maximum (15/15)** regardless
of actual portfolio risk. Confirmed independently by 3 separate teams (Truth Registry, Cross-Module
Consistency, Evidence Provenance).

**Confirmed fixed since Operation One Truth's own same-day report**: `routers/ccc.py`'s duplicate deadline
loop and `matter_intel.py::get_uncertainty_dashboard`'s naive-datetime bug are both resolved.

## 2. Priority / Urgency

`shared/attention_priority.py` is a genuine, working consolidation of ~9 vocabularies into one canonical
scale. Confirmed live gap: `routers/copilot.py::_handle_predlozi` (`:960-1050`) still bypasses it entirely
with its own 3-value ad hoc priority computed straight from deadline proximity.

## 3. Readiness

**Now confirmed a 3-way collision, not 2-way**: `shared/case_readiness.py::compute_case_readiness` (canonical,
5-state enum, zero GPT calls) vs. `services/case_pipeline.py::calculate_case_ready_score` (independent 0-100
checklist, rendered live on the case page) vs. `routers/matter_intel.py::preflight_check` (fully GPT-native
3-state status, confirmed still dead/unreachable from the frontend, but a live landmine via direct API call).
New finding: `calculate_case_ready_score`'s own single value is labeled inconsistently across its own two
render sites — `"zahteva dopunu"` at `static/vindex.js:10502` vs. `"Predmet u pripremi"` at `:20617-20619`
for the identical bottom score bucket.

## 4. Confidence — the most fragmented category, 15 sources not 7

1. Court Predictor Confidence Check — deterministic, GPT forbidden from stating the number
2. Court Predictor Judge Profile `pouzdanost_profila` — GPT-proposed, backend-overridden
3. Court Predictor Opponent Intel `pouzdanost` — mostly GPT self-declared
4. `services/confidence_calibrator.py` — fully dead code
5. Case Intelligence `pouzdanost_briefinga` — deterministic (correctly fixed, the best precedent)
6. Genome `genome_kompletnost` — fully GPT self-declared, silently feeds a -15 penalty into the "canonical"
   strength score
7. `shared/genome_validator.py::verify_genome` — deterministic, advisory-only
8. **[NEW]** CIO weekly briefing `pouzdanost` (`routers/cio.py`) — GPT self-declared, **never overridden**,
   unlike its own sibling fix in `case_intelligence.py`
9. **[NEW]** Client Twin `pouzdanost` — GPT self-declared, rule stated only in prompt text, never enforced
10. **[NEW]** Lessons-Learned `pouzdanost` — deterministic, sample-size-based, its own distinct thresholds
11. **[NEW]** Gap Engine per-gap `pouzdanost` — a hitnost→pouzdanost lookup map
12. **[NEW]** RAG/Precedent retrieval — **2 different formulas computed in the same function call**
    (`app/services/retrieve.py:663-669` and `:672-697`), one English 3-tier, one Serbian 4-tier
13. **[NEW]** Document Intake's 3-layer confidence sub-pipeline (OCR/classification/extraction), a 14th
    distinct vocabulary (raw 0.0-1.0 float)
14. **[NEW]** Document Auto-Link matching confidence — ad hoc, only 2 possible values (95/74)
15. **[NEW, structurally dead]** Confidence Audit / Brier-score calibration system — the column it depends
    on (`recommendation_log.confidence_band`) is defined but **never written by any code path**; the entire
    feature operates on zero rows

Also: `confidence_score` as a literal field name is independently reused by `services/quality_gate.py` for a
semantically unrelated drafting-quality question — a naming collision, not a data collision, but a real trap
for future engineers.

## 5. Strength

Base value single-sourced and genuinely canonical (`case_dna.snaga_predmeta_procent`, backend-recomputed
from `snaga_faktori`, not GPT's raw self-report). Two independent portfolio-level aggregations diverge
(`health_index.py` vs `cio.py`, different inclusion criteria). New this mission: `routers/evidence.py::
_snaga_iz_lokacije` is a per-claim evidence-strength scorer using the identical `jaka/srednja/slaba`
vocabulary as the case-level score, and its output directly feeds `risk_engine.py`'s canonical formula as an
input — meaning a "strength" fragmentation risk sits one hop upstream of the otherwise-unified risk engine.

## 6. Health

Single generation site (`routers/health_index.py::_compute_health`), genuinely not fragmented against a
second "health" computation — but internally compromised: its Portfolio Risk sub-component is silently dead
(§1) and its Case Strength sub-component inherits §5's aggregation ambiguity.

## 7. Probability (success/outcome)

4 independent GPT-generated percentages (Digital Twin ×2, Court Predictor's `prediktuj_ishod`, Hearing CC's
`hearing_score`), none cross-checked against each other or against Genome's own strength score. Only
Copilot's `verovatnoca_uspeha` is deduplicated (a direct alias of `genome.snaga_predmeta_procent`).

## 8. Importance — new category, not covered by Operation One Truth at all

`predmet_hronologija.vaznost` has **three non-matching vocabularies** for what should be one column, one
meaning: the write-time validator (`api.py:4914-4924`) only accepts `{"kritičan","važan","informativan"}`;
the canonical read-side translator (`shared/attention_priority.py::VAZNOST_TO_CANONICAL`, `:102-104`) only
recognizes `{"kritičan","bitan","normalan","ostalo"}` — meaning any row written with the write-path's own
`"važan"` or `"informativan"` has no matching translator key and silently falls through to a MEDIUM default;
`routers/client_portal.py` uses a third, diacritic-stripped spelling set entirely (`"kritican"`/`"vazno"`/
`"interni"`). This is exactly the "hidden fragmentation" pattern the founder mandate asked to hunt for, and
it was not visible to Operation One Truth's own audit.

## 9. Verification

4 live, genuinely non-competing grounding-check mechanisms (Genome's `verify_genome`, 3 sibling
hallucinated-reference validators, a citation-verification check, an evidence-location check) plus the dead
Confidence Audit calibration subsystem from §4.15.

## 10. Credibility

Zero computed occurrences anywhere in the platform. Not a fragmentation risk — the concept simply doesn't
exist as data.

## 11. Quality

One live, well-scoped, actively-enforced mechanism (`services/quality_gate.py::evaluate_draft_quality`,
gates AI-drafted document approval at ≥0.85). Its only issue: the field is literally named
`confidence_score` and does triple duty as the Quality/Confidence/Completeness signal for the same feature
under three different conceptual names.

## 12. Severity

Contradiction *identity* tracking is genuinely solid. New finding, revising Operation One Truth's own
"Category 9 — no fix needed" verdict: `routers/cio.py`'s `neprimecena_kontradikcija` field asks GPT to
re-derive a judgment ("a critical contradiction not yet addressed") that is already mechanically computable
by filtering `case_dna.kontradikcije[]` for `tezina=="kriticna"` with no matching resolved action — a fresh
LLM call re-inventing an already-canonical fact.

## 13. Completeness

3 independent occurrences in genuinely different domains (Genome extraction quality / one AI-drafted
document / whole-case intake readiness) — no same-object collision, but 2 of the 3 double as Confidence
signals under different names, and there's no shared translation layer the way Priority has one.

## 14. Status — largest raw vocabulary count; one confirmed same-entity collision, new this mission

`predmeti.status` is classified by **5 non-identical predicate sets** across different modules: only
`"aktivan"`/`"zatvoren"` are ever actually written, but `analytics.py`/`copilot.py` treat closed as
`("zatvoren","arhiviran")`; `dashboard.py` treats active as "not in a 3-value closed set"; `cio.py`/
`morning_briefing.py`/`zakon_monitoring.py` filter active as a 3-value allow-list that includes 2 values
(`"u_toku"`, `"pending"`) **never actually written to this column anywhere in the codebase**; and
`routers/conflict_check.py` defines a 6th classifier using the literal string `"u toku"` (space) where every
other module spells the intended value `"u_toku"` (underscore) — currently harmless only because nothing
writes either spelling today, but a live landmine the moment any richer status value is ever introduced,
since it would silently diverge the conflict-of-interest screening's own active/closed determination from
every other module's. This finding — the divergent *classification logic* layered on top of the column, as
opposed to its already-known missing migration provenance — was not examined by Operation One Truth at all.

## Categories with fragmentation Operation One Truth did NOT already name

Confidence (8 of 15 sources entirely new), Importance (the whole category), Status (the classifier-logic
finding, as opposed to the provenance finding), Severity (CIO's re-hallucination), Risk (Health Index's dead
sub-score, Matter Intel's dead composite), Verification (the structurally-dead calibration subsystem).
