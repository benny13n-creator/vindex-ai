# Performance Impact Report — Program Tau, Master Sprint 005

**Scope**: `routers/court_predictor.py`'s 7 GPT-calling endpoints, before and after migration onto
`shared/case_context.py::build_case_context()`. This document's BEFORE section is written pre-migration
(Phase 1 baseline); the AFTER section is completed once Phase 2 migration is implemented and measured.

## Correction to a prior sprint's own claim, made before any other analysis

Tau Sprint 004's own `GPT_COST_ANALYSIS.md` stated Court Predictor "re-feeds prior result `[:8000]` chars
on 3 chained calls." Direct re-verification this sprint found this is **not accurate**: every `[:8000]`
occurrence in the current file (4 of them) truncates what gets written to the `predictor_analize` audit
table, not something fed back into a subsequent GPT call. **All 7 endpoints make exactly one GPT call
each** — no chaining exists anywhere in this file. Corrected here rather than propagated forward.

## BEFORE (baseline, pre-migration)

| Endpoint | Model | max_tokens | Est. input tokens | Cost/call | Calls |
|---|---|---|---|---|---|
| `prediktuj_ishod` | gpt-4o | 1500 | ~1,000-1,600 | ~$0.018 | 1 |
| `battle_report` | gpt-4o | 2000 | ~1,000-1,600 | ~$0.023 | 1 |
| `hearing_prep_brief` | gpt-4o | 1000 | ~500-900 | ~$0.012 | 1 |
| `argument_reputation` | gpt-4o | 2000 | ~1,500-2,800 | ~$0.027 | 1 |
| `judge_profile` | gpt-4o | 1500 | ~1,800-2,300 | ~$0.028 | 1 |
| `opponent_intel` | gpt-4o | 1500 | ~1,200-1,700 | ~$0.020 | 1 |
| `confidence_check` | gpt-4o-mini | 150 | ~250-400 | ~$0.0002 | 1 |

**Estimated current monthly cost** (1000-case firm, 2 calls/case/month average across all 7 endpoints,
stated assumption): ≈$40/month for this file's own call volume — small relative to the rest of the
platform (Tau 004's own `strategija.py` orchestrator alone was ~$0.20/run).

**Context today**: none of the 7 endpoints reads `predmet_id` for case data — confirmed fresh this sprint,
no exceptions found beyond Tau 004's own documented finding (`TAU-011`). `opponent_intel` runs a
cross-portfolio `ilike` search on case descriptions (not a single-case fetch by `predmet_id`).

## AFTER (post-migration) — estimated, not measured against a live model

`prediktuj_ishod`/`battle_report` use `build_case_context(..., include_documents=True)` (full mode) since
their own reasoning task is directly about the case's evidentiary strength. The remaining 5 endpoints use
lightweight mode (`include_documents=False`) — readiness/Genome/gaps/actions/deadlines text only, no
document fetch.

| Endpoint | Context mode | Added input (typical case) | Added input (worst case, 15-doc cap) | Cost delta (typical) |
|---|---|---|---|---|
| `prediktuj_ishod` | Full | ~300-900 tokens (canonical-state summary + a few doc excerpts) | ~5,600 tokens (15 docs × 1,500-char budget, Document Visibility Engine's own pre-existing cap) | +~$0.001-0.003 typical; +~$0.014 worst case |
| `battle_report` | Full | Same shape | Same | +~$0.001-0.003 typical; +~$0.014 worst case |
| `hearing_prep_brief` | Lightweight | ~50-150 tokens | Same (no document layer at all) | +~$0.0003-0.0009 |
| `argument_reputation` | Lightweight | ~50-150 tokens | Same | +~$0.0003-0.0009 |
| `judge_profile` | Lightweight, consistency-check only | ~0 (the sud check is a return-value comparison, not injected prompt text) | — | ~$0 |
| `opponent_intel` | Lightweight | ~50-150 tokens | Same | +~$0.0003-0.0009 |
| `confidence_check` | Lightweight, feeds existing deterministic score | ~0 (no new GPT prompt text — readiness participates in `_calc_confidence_nivo`'s own score, not a prompt addition) | — | ~$0 |

**The worst-case bound is already controlled by Tau Sprint 002's own Document Visibility Engine** (15-document
cap, 1,500-char-per-document excerpt budget, 500/1000-document scale already certified) — reused as-is,
not re-implemented or loosened. The worst-case ~75% cost increase on `prediktuj_ishod` only occurs when a
case's own document excerpt budget is fully exhausted (many documents); most cases will see the smaller,
typical-case delta.

**Revised monthly estimate**: ≈$42-48/month (was ≈$40/month), under the same stated assumption — a modest
increase concentrated in the 2 full-context endpoints, near-zero for the other 5.

**Latency**: `build_case_context()`'s own fetch is a set of parallel DB queries, not a 2nd GPT call — adds
one additional round-trip depth (same pattern documented in Tau 002's own `CONTEXT_PERFORMANCE_ANALYSIS.md`),
not additional model latency. All 7 endpoints already run on 25-second timeouts with headroom under their
own baseline GPT call time; not measured against a live deployment this sprint, flagged as an assumption
rather than a verified fact.

## Optimization considered and rejected (Phase 6's own "if there's a chance without quality loss, implement it")

Using lightweight mode for `prediktuj_ishod`/`battle_report` too (matching the other 5) was considered and
rejected — document evidence is central to what these 2 endpoints exist to analyze; stripping it would be
an optimization that costs quality, which Phase 6 explicitly rules out ("ne menjaj kvalitet"). No other
optimization opportunity was found beyond what Tau Sprint 002 already built into the Document Visibility
Engine, reused here rather than re-implemented.
