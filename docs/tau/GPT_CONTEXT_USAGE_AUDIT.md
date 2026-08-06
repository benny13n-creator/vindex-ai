# GPT Context Usage Audit — Program Tau, Master Sprint 005, Phase 7

**Requirement**: prove the migration is not bypassed, duplicated, or partial. No GPT call in
`routers/court_predictor.py` may build its own Case Context.

## Every `supa.table()` call in the file, post-migration, classified

| Line(s) | Table | Purpose | Keyed by `predmet_id`? | Verdict |
|---|---|---|---|---|
| 334, 523, 909, 1074, 1244, 1516 | `predictor_analize` | Write-only audit record insert | write, not read | Not a context source — audit trail, unchanged from before migration |
| 668 | `hearing_briefovi` | Write-only audit record insert | write, not read | Same |
| 1171 | `predmeti` | Cross-portfolio opponent-name search (`opponent_intel`) | No — keyed by `user_id` + `ilike` text pattern | **Deliberate exception, not a bypass** — genuinely different shape than single-case context (searches ALL cases, not one), kept as-is per the grounding-design spec, now supplemented (not replaced) by `build_case_context()` for the CURRENT case specifically |
| 1437, 1589 | `case_patterns` | Firm-wide win-rate aggregation (`confidence_check`, `learning_stats`) | No — keyed by `user_id` + `tip_spora` | Same reasoning — portfolio/firm-wide signal, not single-case context; `learning_stats` is confirmed exempt from `TAU-011`'s own scope entirely (no GPT call) |
| 1574 | `predictor_analize` | Read for stats aggregation (`learning_stats`) | No | Exempt, non-GPT endpoint |
| 1628 | `recommendation_log` | Read for stats aggregation (`learning_stats`) | No | Exempt, non-GPT endpoint |

**Zero single-case bespoke context fetches remain anywhere in this file.** Every one of the 7 GPT-calling
endpoints that needs single-case context now gets it exclusively via `_dohvati_case_context_ako_postoji`
→ `shared/case_context.py::build_case_context()` — confirmed by this line-by-line inventory, not sampled.

## Every GPT call site, confirmed reading from the ONE canonical source or explicitly exempt

| Endpoint | Uses `build_case_context()`? | Mode |
|---|---|---|
| `prediktuj_ishod` | Yes | Full (`include_documents=True`) |
| `battle_report` | Yes | Full |
| `hearing_prep_brief` | Yes | Lightweight |
| `argument_reputation` | Yes | Lightweight |
| `judge_profile` | Yes (for the sud consistency check only — no case-description field exists to inject further, see `COURT_PREDICTOR_FORENSIC_REPORT.md`) | Lightweight |
| `opponent_intel` | Yes (alongside its own, differently-shaped cross-portfolio search) | Lightweight |
| `confidence_check` | Yes (readiness feeds the existing deterministic score, `_calc_confidence_nivo`) | Lightweight |

## No new context builder, wrapper, or predictor was created

- `_case_context_blok()` — formats `build_case_context()`'s own already-fetched fields into prompt text.
  Same category as `case_commander.py`'s own `_formatiraj_kontekst` / `case_intelligence.py`'s own
  `_build_context_text` — a presentation function over the ONE canonical source's own output, not a 2nd
  source.
- `_dohvati_case_context_ako_postoji()` — a 6-line fail-soft `try/except` wrapper around exactly one
  `build_case_context()` call, reused so 7 call sites don't repeat the same error handling. Calls the
  canonical function directly, computes nothing of its own, holds no state.
- `_rag_praksa_blok()` — pre-existing (Program Celina, 2026-07-24), not new; only its return signature
  changed (added a structured list alongside the existing text block, for `TAU-014`'s own fix).
- No new GPT wrapper: `_pozovi_predictor_api`/`_pozovi_battle_report_api`/etc. are all pre-existing,
  unmodified in their own call signature to OpenAI.
- No new predictor logic: `_calc_confidence_nivo` is the SAME pre-existing deterministic function (Program
  Alpha, 2026-08-04), extended with one new optional parameter (`readiness_status`) that participates in
  the same score, not a parallel scoring system.

## Verdict

Migration is complete for the specific claim `TAU-011` made (no `predmet_id`-keyed single-case context
fetch remained unmigrated) and does not introduce any parallel context/decision system anywhere in this
file. The 2 remaining non-`predmet_id`-keyed queries (`opponent_intel`'s cross-portfolio search,
`confidence_check`'s firm-wide aggregation) are confirmed, by direct inspection, to be genuinely
different-shaped signals the canonical single-case contract was never meant to replace — not overlooked
bypasses.
