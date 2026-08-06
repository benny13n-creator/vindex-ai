# Court Predictor Forensic Report — Program Tau, Master Sprint 005, Phase 1

**Purpose**: re-prove `TAU-011` from scratch, not assume it. Full line-by-line read of
`routers/court_predictor.py` (1401 lines), all 7 GPT-calling endpoints plus the 2 non-GPT ones
(`get_faktori`, `learning_stats`) for completeness. No code changed by this task.

**Verdict up front**: `TAU-011`'s claim holds for all 7 endpoints — `predmet_id` is never used to fetch
that specific case's own context (Genome/documents/evidence/actions) in any of them. Two endpoints
(`opponent_intel`, `confidence_check`) do make real DB queries that inform the GPT prompt, but both are
keyed by `user_id`/other fields, not `predmet_id` — genuinely portfolio-wide or firm-wide signals, not
"this case's" data. No hidden GPT call sites were found beyond the 7 already known. No caching/memoization
of case data exists anywhere in this file — every call does a fresh RAG search and fresh GPT call.

---

## 1. `prediktuj_ishod` (`POST /api/predictor/analiza`, line 130-229)

- **Request model** (`PredictorRequest`, line 48-55): `opis_predmeta`, `tip_postupka`, `cinjenicni_opis`,
  `dokazi: list[str]`, `suprotna_strana_argumenti`, `sud`, `predmet_id`.
- **`predmet_id` uses**: line 183 `_ai_case_ctx(predmet_id=payload.predmet_id, ...)` (audit/provenance
  only); line 194 `predictor_analize` INSERT (write, not read); line 203 `log_action(resource_id=...)`
  (audit only). **Zero read queries keyed by `predmet_id`.**
- **DB queries**: none that read case data. Only the write-only `predictor_analize` insert above.
- **What reaches GPT**: `payload.opis_predmeta`/`cinjenicni_opis`/`dokazi`/`suprotna_strana_argumenti`/`sud`
  (all caller-supplied text, line 157-176) + `_rag_praksa_blok` (Pinecone precedent search, line 154-155).
- **TAU-011 confirmed**: yes, unambiguously.

## 2. `battle_report` (`POST /api/predictor/battle-report`, line 298-389)

- **Request model** (`BattleReportRequest`, line 234-243): `predmet_id`, `tip_postupka`, `opis_predmeta`,
  `sud`, `sudija`, `protivnicki_adv`, `protivnik_naziv`, `vrednost_spora`, `dokazi`.
- **`predmet_id` uses**: line 351 `_ai_case_ctx` (audit); line 358 insert (write); line 368 `log_action`
  (audit). **Zero read queries.**
- **What reaches GPT**: entirely caller-supplied payload fields (line 327-344) + RAG (line 324-325).
- **TAU-011 confirmed**: yes.

## 3. `hearing_prep_brief` (`POST /api/predictor/hearing-prep`, line 441-511)

- **Request model** (`HearingPrepRequest`, line 394-400): `predmet_id`, `rociste_naziv`, `datum_rocista`,
  `tip_postupka`, `opis_predmeta`, `poslednji_podnesak`.
- **`predmet_id` uses**: line 474 `_ai_case_ctx` (audit); line 477-486 **conditional** insert into
  `hearing_briefovi` (`if payload.predmet_id:`, write only); line 489 `log_action` (audit). **Zero read
  queries** — the conditional at line 477 only gates whether a WRITE happens, never triggers a read.
- **What reaches GPT**: `payload.rociste_naziv`/`datum_rocista`/`tip_postupka`/`opis_predmeta`/
  `poslednji_podnesak` (line 463-467), no RAG call in this endpoint at all.
- **TAU-011 confirmed**: yes.

## 4. `argument_reputation` (`POST /api/predictor/argument-reputation`, line 615-737)

- **Request model** (`ArgumentReputationRequest`, line 562-566): `tip_spora`, `argumenti: list[str]`,
  `sud`, `predmet_id`.
- **`predmet_id` uses**: line 679 `_ai_case_ctx` (audit); line 714 insert (write); line 724 `log_action`
  (audit). **Zero read queries.**
- **What reaches GPT**: `payload.tip_spora`/`argumenti`/`sud` (line 664-671) + per-argument RAG search
  (line 634-661, up to 5 separate Pinecone calls, one per argument).
- **TAU-011 confirmed**: yes.

## 5. `judge_profile` (`POST /api/predictor/judge-profile`, line 791-884)

- **Request model** (`JudgeProfileRequest`, line 742-746): `ime_sudije`, `sud`, `tip_postupka`,
  `predmet_id`. **Note: no `opis_predmeta`/case-description field exists on this model at all** — this
  endpoint is architecturally about a court/judge, not a specific case, by its own request shape.
- **`predmet_id` uses**: line 839 `_ai_case_ctx` (audit); line 863 insert (write); line 873 `log_action`
  (audit). **Zero read queries.**
- **What reaches GPT**: `payload.sud`/`ime_sudije`/`tip_postupka` + RAG search (line 809-819).
- **TAU-011 confirmed**: yes, though with a caveat worth carrying into Phase 2 — since this endpoint's own
  request model has no case-description field, it's a genuinely different shape from the other 6 (similar
  to `strategija.py`'s own architectural difference found in Tau 002/003). A judge/court profile is not
  inherently "about" one case the way a prediction is — migrating this one onto `build_case_context()`
  needs its own judgment call about what, if anything, case context adds here.

## 6. `opponent_intel` (`POST /api/predictor/opponent-intel`, line 939-1045)

- **Request model** (`OpponentIntelRequest`, line 889-894): `protivnik_naziv`, `protivnicki_adv`,
  `tip_postupka`, `predmet_id`, `poznate_informacije`.
- **`predmet_id` uses**: line 1008 `_ai_case_ctx` (audit); line 1022 insert (write); line 1032 `log_action`
  (audit). **Zero read queries keyed by `predmet_id`.**
- **DB query that DOES happen** (line 956-963): `supa.table("predmeti").select("naziv, status, opis")
  .eq("user_id", uid).ilike("opis", f"%{payload.protivnik_naziv[:30]}%").limit(5)` — a cross-portfolio
  name search for OTHER cases mentioning this opponent, keyed by `user_id` + a text pattern match on
  `opis`, NOT by `payload.predmet_id`. This is real, useful signal (an internal case-history lookup) but
  it is not "this case's own context" — it's "other cases that might mention this same opponent."
- **What reaches GPT**: the above internal history block (if any matches) + RAG search (line 974-989) +
  caller-supplied fields.
- **TAU-011 confirmed**: yes, for the specific claim (current case's own context never fetched by
  `predmet_id`) — with the same nuance Tau 004 already noted: a real `predmeti` query does happen, just
  not the one TAU-011 is about.

## 7. `confidence_check` (`POST /api/predictor/confidence-check`, line 1147-1294)

- **Request model** (`ConfidenceCheckRequest`, line 1050-1055): `tip_spora`, `opis_predmeta`, `sud`,
  `predmet_id`, `dokazi`.
- **`predmet_id` uses**: line 1234 `_ai_case_ctx` (audit, wraps only the final GPT call); line 1261 insert
  (write); line 1271 `log_action` (audit). **Zero read queries keyed by `predmet_id`.**
- **DB query that DOES happen** (line 1187-1195): `supa.table("case_patterns").select("faktor,pobede,
  porazi,uzoraka").eq("user_id", uid).eq("tip_spora", payload.tip_spora).order("uzoraka", desc=True)
  .limit(10)` — a FIRM-WIDE win-rate aggregation for this case TYPE, keyed by `user_id` + `tip_spora`, not
  `predmet_id`. Real, deterministic signal (feeds `_calc_confidence_nivo`/`_procenat_iz_score`, both
  already fully code-computed — this endpoint's own numeric output has NO GPT-decided number at all, only
  a short "razlog"/"kljucni_rizik" text field comes from GPT, per its own explicit design comment at line
  1217-1218: "SAMO kratko obrazloženje/rizik, NIKAD procenat").
- **TAU-011 confirmed for the case-context claim** — but this endpoint is architecturally the platform's
  own best-designed one in this file: the numeric confidence score is deterministic (`DC-004`, unchanged),
  and only a short qualitative explanation comes from GPT.

## Non-GPT endpoints (confirmed, not part of TAU-011's scope)

- `get_faktori` (line 516-557): static hardcoded data, no DB, no GPT.
- `learning_stats` (line 1299-1401): pure DB aggregation (`predictor_analize` count,
  `case_patterns`/`recommendation_log` win-rate math), zero GPT calls.

## Additional hunting (per this sprint's own Phase 1 mandate)

- **No other GPT-calling functions exist in this file** beyond the 7 endpoints' own `_pozovi_*_api` retry
  wrappers — confirmed by a full read, not just a grep.
- **No conditional path where `predmet_id` triggers a real context fetch** in any circumstance — every
  `if payload.predmet_id:` branch found (only `hearing_prep_brief`'s, line 477) gates a WRITE, never a READ.
- **No caching/memoization of case data** anywhere in this file — every request re-runs RAG + GPT fresh;
  there is no module-level or request-scoped cache that could serve a stale case snapshot.

## Summary table

| Endpoint | `predmet_id` used for real context fetch? | Other DB query present? | Keyed by `predmet_id`? |
|---|---|---|---|
| `prediktuj_ishod` | No | No | — |
| `battle_report` | No | No | — |
| `hearing_prep_brief` | No | No | — |
| `argument_reputation` | No | No | — |
| `judge_profile` | No | No | — (also has no case-description field at all) |
| `opponent_intel` | No | Yes — `predmeti` cross-portfolio search | No (keyed by `user_id`+`opis` pattern) |
| `confidence_check` | No | Yes — `case_patterns` firm-wide aggregation | No (keyed by `user_id`+`tip_spora`) |

**TAU-011 holds for all 7 endpoints.** No new hidden path was found beyond what Tau 004's own faster pass
already reported. The one genuinely new detail this deeper pass adds: `judge_profile`'s own request model
structurally has no case-description field at all, making it architecturally different from the other 6 —
this matters directly for how Phase 2's migration should treat it (see `docs/tau/GPT_CONTEXT_USAGE_AUDIT.md`).
