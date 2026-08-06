# Canonical Reasoning Certification — Program Tau, Master Sprint 007, Phases 4-5

Certifies (a) whether Genome, Case Context, Case Actions, Gap Engine, Readiness, Court Predictor, Hearing
CC, and Commander are now aligned, and (b) whether GPT still decides priority/readiness/next-step/risk/facts
anywhere touched by this sprint or its own census.

## Phase 4 — Cross-system verification

### The dependency graph, as it stands after this sprint

```
Genome (case_dna, GPT-extracted)
  └─> shared/gap_engine.py::collect_case_gaps (normalizes Genome + risk_engine, computes nothing new)
services/risk_engine.py::calculate_procesni_rizik / identify_case_problems (deterministic)
  └─> shared/gap_engine.py::collect_case_gaps
case_actions (table, written by services/case_evolution.py)
  └─> shared/case_readiness.py::compute_case_readiness (reads case_actions + gaps)
  └─> shared/case_readiness.py::top_open_action (reads case_actions directly)

shared/case_context.py::build_case_context()
  = THE single point that calls risk_engine + gap_engine + case_readiness together,
    for one case, and exposes their output as readiness/missing_evidence/contradictions/active_actions.

  ├─> routers/court_predictor.py   (Tau 005 — reads build_case_context() directly)
  ├─> routers/hearing_cc.py         (Tau 006 — reads build_case_context() directly)
  ├─> routers/case_intelligence.py  (Tau 002 — reads build_case_context() directly)
  ├─> routers/morning_briefing.py   (Tau 002 — loops build_case_context() lightweight)
  └─> routers/case_commander.py     (Tau 007, THIS sprint — reads build_case_context() directly,
                                      single-case AND now also loops it for the portfolio digest)
```

Because all 5 consumer modules now call the SAME `build_case_context()` for the SAME case, they
structurally cannot disagree with each other about readiness/gaps for that case at that point in time — not
because each was individually checked to agree, but because there is only one computation to disagree
with. This is the actual meaning of "aligned" this phase set out to verify.

### Verified, not assumed

- **Vocabulary consistency**: `court_predictor.py` and `hearing_cc.py` were found (this phase) to hardcode
  `"CRITICAL_GAP"`/`"BLOCKED"` as raw string literals in their own deterministic-cap dicts, instead of
  importing `shared/case_readiness.py`'s own constants — `case_commander.py` already imported them. A latent
  drift risk (a rename at the source would silently desync the 2 hardcoded modules) — **fixed this sprint**,
  both now import `CRITICAL_GAP`/`BLOCKED`/`READY` from the canonical module. Proven by
  `tests/test_tau007_case_commander_consolidation.py::test_readiness_cap_dicts_use_canonical_constants_not_string_literals`
  and a direct cross-system test (`test_same_case_context_agrees_across_court_predictor_hearing_cc_commander`)
  feeding one mocked `build_case_context()` result through all 3 modules' own interpretation logic and
  confirming identical agreement.
- **`case_commander.py`'s own `_READINESS_RANK`** covers all 5 canonical states (`READINESS_STATES`) —
  verified by direct set-equality test, not assumed complete.
- **Genome (`case_dna`)** remains the sole producer `gap_engine.py` reads from — unchanged this sprint,
  reconfirmed architecturally exempt (a producer, not a consumer, migrating it would be circular — same
  finding Tau 006's own census already made).

### What's NOT unified, and why that's correct, not a gap

`opponent_intel`'s cross-portfolio search (Court Predictor), `confidence_check`'s firm-wide aggregation
(Court Predictor), and `case_commander.py`'s own 2 GPT-advisory fields (`protivnikova_strategija`,
`sudska_praksa`) are deliberately NOT sourced from `build_case_context()` — each is a genuinely different-
shaped signal (cross-case, firm-wide, or has no canonical source at all), the same "keep bespoke, name why"
precedent established in Tau 005/006. Not unifying these is correct, not an oversight.

## Phase 5 — GPT Boundary Audit

Checked whether GPT determines priority, readiness, next-step, risk, or facts anywhere this sprint's own
census covered (`docs/tau/REASONING_REGISTRY.md`).

### Confirmed: GPT does not decide any of these 5 things in any module this sprint touched

`case_commander.py` (migrated this sprint): all 6 canonical fields
(`status_predmeta`/`readiness_status`/`nedostaje`/`rizici`/`preporuceni_potez`/`vremenski_pritisak`) are
built BEFORE the GPT call and never re-read from its output — proven adversarially
(`test_gpt_advisory_cannot_override_canonical_readiness`: a poisoned advisory response explicitly tries to
smuggle a `readiness_status`/`prioritet` claim into the JSON; the returned result is unaffected). GPT's own
role in this file is restricted to exactly 2 fields (`protivnikova_strategija`, `sudska_praksa`) which have
no canonical source and are always tagged `gpt_advisory`, never asserted as fact — Sigma 005's own GPT
Boundary Policy, reconfirmed intact after migration, not weakened by it. `court_predictor.py`/`hearing_cc.py`
(Tau 005/006): reconfirmed their own deterministic caps still hold post this sprint's own constant-import
fix (regression-tested, unchanged behavior).

### One real, still-open finding: `routers/cio.py`

GPT independently invents `kriticnost` (a 0-100 urgency score), `najveci_rizik`, `kriticni_rok`, and
`cio_preporuka` (a single recommended action) from raw portfolio signals — not from `case_actions`/
`identify_case_problems`/`compute_case_readiness`. This is a genuine violation of this sprint's own Phase 5
rule ("GPT sme samo da rezonuje... nikad da odlučuje prioritet/rizik").

**Not fixed this sprint.** This is not a fresh discovery — the file's own header comment already documents
it as a deliberate, previously-escalated decision (Program Omega Sprint 004): "the canonical answer to
'what should the lawyer do today' is `GET /api/workspace`; this module remains a supplementary strategic
perspective... out of safe scope" at that time, because it is a live, billed feature and changing a live
GPT prompt's own behavior/shape carries real user-facing risk that deserves its own dedicated, careful
sprint — not a same-sprint addition squeezed into a mission whose own named target was `case_commander.py`.
Re-confirmed as still open, still real, and named explicitly here rather than silently re-deferred without
comment. Priority candidate for `docs/tau/TAU_008_HANDOVER.md`.

### 2 findings confirmed NOT actionable, correctly exempt

`strategija.py`'s own GPT-invented `sledeci_koraci[].prioritet` — no `predmet_id` exists on any endpoint in
this file (self-documented, pre-existing across 3 prior Tau sprints), so there is no canonical per-case
state to check this against; the tool is fundamentally a standalone "paste your case text" simulator, not a
tracked-case reasoning surface. `case_dna.py`'s own `nedostaje[].hitnost` — GPT-advisory, but confirmed
(via `shared/attention_priority.py`'s own docstring) not wired into `case_actions`/Workspace as an
autonomous decision; it's Genome's own internal signal, not a boundary violation.

## Verdict

Cross-system alignment (Phase 4) holds by construction for every module reading `build_case_context()`,
with one real drift-risk found and fixed (hardcoded vocabulary in 2 modules). The GPT boundary (Phase 5)
holds for `case_commander.py` post-migration and for the 2 prior Tau sprints' own migrated modules,
adversarially proven not just asserted. One genuine, pre-existing, still-open violation (`cio.py`) is named
precisely rather than silently carried forward without comment — its own risk profile (live, billed,
previously deliberately deferred) means fixing it deserves its own sprint, per this program's own repeated
discipline of not rushing a live-feature change into an unrelated mission's scope.
