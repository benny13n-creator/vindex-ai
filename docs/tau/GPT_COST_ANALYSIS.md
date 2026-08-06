# GPT Cost Analysis — Program Tau, Master Sprint 004, Phase 7 (+ Phase 5 scale tests)

**Pricing source**: `shared/cost.py`'s own current table — `gpt-4o`: $0.0025/1K input, $0.0100/1K output;
`gpt-4o-mini`: $0.00015/1K input, $0.0006/1K output.

## Per-flow cost estimates (highest-stakes call sites, read directly not guessed)

| Flow | File | Model | Input (est.) | max_tokens (output cap) | Cost/call (worst case) |
|---|---|---|---|---|---|
| Genome extraction | `case_dna.py::_pozovi_genome_api` | gpt-4o | ≤60,000 chars (~15,000 tok) — **hard-capped by design** (`_GENOME_MAX_TOTAL_CHARS`, Program Celina 2026-07-24) | 4,000 | **~$0.078** (15,000/1000×$0.0025 + 4000/1000×$0.01) |
| Case Commander analiza | `case_commander.py` | gpt-4o (kompletna/rizici) or gpt-4o-mini | ~2,500 tok (8,000-char doc budget + case text) | 1,500 | ~$0.021 (gpt-4o) |
| Copilot analiza | `copilot.py::_handle_analiza_predmeta` | gpt-4o-mini | ~1,500 tok | 1,200 | ~$0.0009 |
| Copilot plan | `copilot.py::_handle_plan_predmeta` | gpt-4o-mini | ~2,000 tok | 2,000 | ~$0.0015 |
| Strategija kompletna-analiza | `strategija.py::orkestrator_kompletna_analiza_sync` | gpt-4o | 8 sequential calls, ~2,000 tok input each | ~2,000-3,000 each | **~$0.20 for the whole 8-call run** (own docstring: "8 GPT-4o poziva") |
| Court Predictor (per endpoint) | `court_predictor.py` | gpt-4o (5 of 6) | ~1,500-2,000 tok, re-feeds prior result `[:8000]` chars on 3 chained calls | 1,000-2,000 | ~$0.015-0.025/call |
| Legal Reasoning Engine | `legal_reasoning_engine.py` | gpt-4o | Bounded by construction: `context_docs[:4]` × `[:500]` chars ≈ 500 tok + fact/source lists | — | Low, deliberately context-engineered (Tau 001's own finding, unchanged) |

## Cost at scale

### (a) A single 500-document case, highest-cost relevant flow (Genome extraction)
**Genome extraction cost does NOT scale with document count past 25.** `_GENOME_MAX_DOCS = 25`,
`_GENOME_MAX_TOTAL_CHARS = 60000` (`routers/case_dna.py:190-192`) cap the extraction call regardless of
whether the case has 25 or 5,000 documents — a 500-document case costs the same ~$0.078 per Genome refresh
as a 25-document case. This is a deliberate, already-shipped design (Program Celina, 2026-07-24), confirmed
still in place, not a new finding.

### (b) A hypothetical 1000-case law firm, monthly spend
**Stated assumption** (not hidden): 1 Genome refresh/case/month, 4 Copilot/Case-Intelligence-style calls/
case/month, 10% of cases run a full `kompletna-analiza` once/month.

```
1,000 cases × $0.078 (Genome)                         = $78
1,000 cases × 4 calls × ~$0.01 avg (Copilot/CI mix)    = $40
100 cases (10%) × $0.20 (kompletna-analiza)            = $20
─────────────────────────────────────────────────────────────
Estimated monthly GPT spend                            ≈ $138/month
```

This is a rough, assumption-stated estimate for planning purposes, not a billing-grade forecast — actual
usage patterns (how often lawyers actually trigger each flow) are not measured anywhere in the codebase
today (no per-flow call-frequency telemetry found).

## Optimization recommendations (quality-preserving only, not implemented this sprint)

1. **Model tiering already correct** — Tau 001's own `GPT51_COST_OPTIMIZATION.md` confirmed `gpt-4o`/
   `gpt-4o-mini` tiering is real and load-bearing; nothing to change here.
2. **No caching exists anywhere** (Tau 001's own finding, still true) — the single best candidate remains
   `morning_briefing.py`'s daily cron loop (Batch API), unchanged recommendation, not implemented (out of
   scope, no evidence it's needed yet at current usage).
3. **Genome extraction's own cap is the platform's best existing cost-control pattern** — worth using as
   the template if any other flow (e.g. `strategija.py`'s 8-call orchestrator) is ever found to need a
   similar hard ceiling; not proposed as a change here since no evidence of runaway cost was found.

## Phase 5 — extreme scale test results (`tests/test_tau004_extreme_scale.py`, 4 tests, all pass)

| Scenario | Result |
|---|---|
| 300 deadlines (`rocista`) | **No bug** — `shared/case_context.py::_fetch_raw` has no `.limit()` on this query; all 300 rows reach `build_case_context()`'s own `deadlines` field, confirmed by test, not just code-read. |
| 50 contradictions | **No bug** — `shared/gap_engine.py::gaps_from_contradictions` has no capping slice; all 50 reach the raw `contradictions` field. (Tau 003's own `[:4]`-style caps in `case_intelligence.py`/`copilot.py` are DISPLAY-layer truncation for a lawyer-facing summary, not data loss at the `case_context` layer — this distinction is confirmed, not assumed.) |
| 20-year-old case | **No bug** — `date.fromisoformat` subtraction handles 20-years-past and 20-years-future dates correctly (Python's `date` type has no practical overflow risk in this range); `morning_briefing.py::_dani_do`'s own fail-soft `except: return 999` correctly absorbs malformed dates too. |

**No real bug found during Phase 5 scale testing.** 500/1000-document scale was already proven in Tau
Sprint 002 (`tests/test_tau002_case_context.py`) — not re-tested here.
