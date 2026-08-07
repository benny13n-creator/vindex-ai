# READINESS_AUTHORITY_SPEC.md — Operation Single Brain, Mission 002

## CANONICAL_OWNER

`shared/case_readiness.py::compute_case_readiness()` — deterministic, 5-state enum
(`READY`/`PARTIALLY_READY`/`BLOCKED`/`CRITICAL_GAP`/`UNKNOWN`), zero GPT calls, sourced exclusively
from `case_actions.prioritet` (the sole-writer table, `services/case_evolution.py`) and Gap Engine
hypothesis-only findings. This does not change with this mission — it was already correctly canonical
before Mission 002; what was missing was every OTHER "how ready is this case" number respecting it.

## Why not `calculate_case_ready_score` instead

`services/case_pipeline.py::calculate_case_ready_score()` answers a genuinely different, legitimate
question — "has the case's SETUP been completed" (documents uploaded, client linked, a pipeline run,
a hearing scheduled) — not "is the case blocked from proceeding." Both questions are real and useful.
The bug was never that 2 questions existed; it was that the setup-completeness score could show a
green 100%/"ready" verdict on the SAME case where the canonical engine had already found a blocking
critical gap, with the checklist having no way to know that and no mechanism to reflect it.

## The rule this mission implements (no new scoring system — reuses the existing `CAP_BY_READINESS` pattern)

`calculate_case_ready_score()`'s numeric checklist score is now capped by the canonical readiness
status, using the exact same `shared/case_readiness.py::CAP_BY_READINESS = {CRITICAL_GAP: 50,
BLOCKED: 65}` constant already governing 4 GPT probability generators — extended to a 5th consumer,
not a new number invented for this purpose. When capped, the case-ready-score response also carries
the specific blocking reason (`case_actions.razlog` of the readiness-determining action), so the UI
can explain the cap instead of silently showing a lower number with no context.

```
shared/case_readiness.py::compute_case_readiness()
       |
       | (CANONICAL_OWNER — 5-state status + blocking reason)
       |
       +--> CAP_BY_READINESS clamp on:
       |      - court_predictor.py::prediktuj_ishod            (existing, Mission 001)
       |      - court_predictor.py::argument_reputation        (NEW this mission — DEBT-002 closed)
       |      - digital_twin.py ×2 endpoints                   (existing, Mission 001)
       |      - hearing_cc.py::hearing_score                   (existing, Mission 001)
       |      - case_pipeline.py::calculate_case_ready_score   (NEW this mission — headline fix)
       |
       +--> top_open_action() -- canonical "next action" (unchanged scope this mission)
```

## Validation rules

- `compute_case_readiness()` itself: unchanged — already zero-GPT, already enum-bounded, already
  tested (`test_singlebrain_phase4_scale_and_adversarial.py::test_adversarial_readiness_has_no_gpt_input_path`).
- `calculate_case_ready_score()`: now takes an optional `readiness_status` parameter. When the
  caller supplies a `CRITICAL_GAP`/`BLOCKED` status, the returned score is capped exactly like the
  4 GPT generators, and the returned checklist gains one additional, always-visible item stating the
  blocking reason when active. Callers that don't yet compute readiness (there are none load-bearing
  after this mission's fix — see `FRAGMENTATION_ELIMINATION_REPORT.md` §1) get the pre-mission,
  uncapped behavior unchanged — this is additive, not a breaking signature change.

## All consumers (post-fix)

| Consumer | File | Change this mission |
|---|---|---|
| `routers/case_pipeline.py` POST `/pipeline`, GET `/pipeline/status` | `routers/case_pipeline.py` | Now passes canonical readiness into the score calculation |
| `api.py` case-workspace GET | `api.py:5480-5575` | Same |
| Status panel Case Ready Score render | `static/vindex.js:10480-10526` | Renders the new blocking-reason item when present; no other frontend change needed since the score itself already carries the cap |
| Intake wizard result screen | `static/vindex.js:20610-20648` | Same score field, automatically reflects the cap — no separate fix needed (single source, per Mission 001's own already-closed label-alignment fix) |
| `court_predictor.py::argument_reputation` | `routers/court_predictor.py` | Now applies `CAP_BY_READINESS`, closing `SINGLEBRAIN-DEBT-002` |
