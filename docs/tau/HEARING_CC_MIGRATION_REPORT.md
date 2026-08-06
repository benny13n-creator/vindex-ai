# Hearing Command Center Migration Report — Program Tau, Master Sprint 006, Phase 4

Pilot application of `docs/tau/MIGRATION_TEMPLATE.md` against `routers/hearing_cc.py` — the richest
bespoke context builder found in Phase 1's census (`_load_all_context`, previously 8 tables).

## Step 0 — Forensic re-verification findings

- `predmet_id` is a required field on both `HearingCCReq` and `CrossExamRequest` (`min_length=1`).
- `hearing_command_center`'s own live frontend caller (`static/vindex.js::hccGeneriši`) **always** sends a
  real `activePredmetId` — the UI blocks the call entirely otherwise ("Otvorite predmet pre generisanja
  brifinga."). A genuinely different live-traffic shape than Court Predictor's own conditional case (Tau
  005) — this module's real usage is unconditionally case-linked, so the migration didn't need Court
  Predictor's "enrich only if present" branching for this endpoint.
- `cross_examination`'s own live frontend caller was searched for directly (`grep -n "cross-exam"
  static/vindex.js`) and **not found** — this endpoint currently has no live UI caller at all. Migrated
  anyway for completeness (the mission's own "no half migration" rule applies to the whole file), but this
  is a genuine finding, not assumed: same "invisible feature" shape found repeatedly earlier in this
  engagement, not something this sprint's own scope authorizes fixing (connecting a dead frontend feature
  isn't a context migration).
- Old bespoke fetch (8 tables): `predmeti`, `predmet_klijenti`, `predmet_dokumenti` (**filenames only, no
  text**), `predmet_beleske`, `predmet_istorija`, `predmet_hronologija`, `predmet_komentari` (fetched but
  **never read** by `_build_prompt` — dead code), `rocista` (with `vreme`/`napomena`, columns the canonical
  contract doesn't carry).

## What migrated cleanly (canonical replaces bespoke)

| Old bespoke fetch | Canonical replacement | Notes |
|---|---|---|
| `predmet_hronologija` | `timeline` | Verbatim same 3 columns, same ordering — a direct swap. |
| `predmet_dokumenti` (filenames only) | `relevant_documents` | Strict improvement: real excerpts via the pre-existing Document Visibility Engine, not just names. |
| *(nothing — new content)* | `key_facts` (Genome), `contradictions`, `missing_evidence`, `active_actions`, `readiness` | This module never had Genome/gap access before — same category of addition Tau 002/005 made for their own consumers. |
| `predmet_komentari` | *(dropped entirely)* | Confirmed dead code (fetched, never rendered by `_build_prompt`) — removed per Phase 8's "fix everything that can be fixed" mandate, not migrated. |

## What did NOT migrate cleanly — named, not worked around (Factory Step 5)

- **`predmet_beleske` (attorney's own case notes) and `predmet_istorija` (recent AI Q&A on this case)** —
  no equivalent field exists anywhere in `build_case_context()`'s 13-field contract. Decision: **kept as
  separate bespoke fetches alongside the new canonical call** (same precedent as `court_predictor.py`'s own
  `opponent_intel`, Tau 005) — real, valuable content the canonical contract simply doesn't carry yet.
  Worth a future `TAU-013`-style contract-expansion candidate, not this sprint's problem to solve.
- **`predmet_klijenti` (resolved client names via a join to `klijenti`)** — canonical `participants` only
  carries `stranka`/`protivnik`/`klijent_id` strings from the `predmeti` row itself, no name resolution.
  Kept as a separate bespoke fetch for the same reason.
- **`rocista` with `vreme`/`napomena`** — canonical `deadlines` reads the same table but projects only
  `sud`/`datum`/`status`. The "PREĐAŠNJA ROČIŠTA" section's own value comes specifically from the
  hearing-time and note fields canonical doesn't carry. Decision: kept the existing bespoke `rocista` fetch
  for THIS display purpose; canonical context is still fetched (for Genome/gaps/etc.), its own `deadlines`
  field is simply not separately rendered since the richer bespoke version already covers that need — not
  a duplicate query for the same purpose, a wider fetch whose one redundant field is unused by choice.
- **Full `predmeti.*` row** — canonical `case_identity` only projects `id/naziv/tip_postupka/sud/status/
  vrednost_spora`; the module's own opening block needs `opis/rizik/tuzilac/tuzeni/oblast`, none of which
  canonical carries. Kept the bespoke `select("*")`. This means `build_case_context()`'s own internal
  `predmeti` fetch is a redundant 2nd read of the same row — accepted, same tradeoff `case_intelligence.py`'s
  own code comment already blessed ("one redundant predmeti row read... is an acceptable cost").

## GPT boundary added (Factory Step 4)

`hearing_score` (GPT's own 0-100 hearing-readiness self-assessment) is now deterministically capped at
50/65 when canonical readiness is `CRITICAL_GAP`/`BLOCKED` — reusing Tau 005's own exact thresholds for
platform-wide consistency (not a newly-invented number). Proven adversarially: a poisoned GPT response
claiming `hearing_score=95` against a `CRITICAL_GAP` case is still forced down to 50
(`test_hearing_command_center_caps_score_on_critical_gap_even_if_gpt_disagrees`).

## Tests

16 new tests (`tests/test_tau006_hearing_cc_migration.py`) covering the fail-soft fetch, the formatter, full-
mode document injection, the adversarial cap-override proof, graceful degradation when
`build_case_context()` fails, `cross_examination`'s lightweight-mode injection, and a concurrency test
(2 different cases' briefings computed via `asyncio.gather` don't cross-contaminate their own readiness
caps). 34 pre-existing tests in `tests/test_hearing_cc.py` updated for the new `_load_all_context`/
`_build_prompt` shapes (dropped keys, new `case_context_blok` parameter) — all still assert the same
observable behavior, not loosened.

## Migration completeness (Factory Step 7)

Full `supa.table()` inventory post-migration: exactly 5 calls remain (`predmeti`, `predmet_klijenti`,
`predmet_beleske`, `predmet_istorija`, `rocista`) — all 5 are the deliberately-kept Step 5 exceptions above,
each with a stated reason. `predmet_hronologija`, the old `predmet_dokumenti`, and `predmet_komentari` are
confirmed gone.

## Phase 6 — Token/memory certification (measured, not guessed)

Real `tiktoken` (`encoding_for_model("gpt-4o")`) encoding of actual prompt strings produced by the actual
`_build_prompt` functions — the pre-migration version loaded standalone from `git show HEAD` (before this
sprint's own commit), the post-migration version from the current `routers/hearing_cc.py` — for one
representative mid-size case (12 documents, 6 hearings, 10 notes, 4 AI-history entries, 8 chronology
events, `tip_postupka="radni"`):

| Metric | Before | After | Delta |
|---|---|---|---|
| User prompt tokens | 1,558 | 2,771 | +1,213 |
| System prompt tokens (incl. alignment suffix) | 135 | 261 | +126 |
| **Total prompt tokens** | **1,693** | **3,032** | **+1,339 (+79.1%)** |
| In-memory context payload (JSON-serialized bytes) | 5,605 | 23,048 | +17,443 (+311.2%) |
| GPT calls per invocation | 1 | 1 | unchanged (confirmed by code inspection) |

**Cost delta** (OpenAI's published gpt-4o input rate, $2.50/1M input tokens): **+$0.0033/call** for this
representative case. `max_tokens=4000` (the JSON response cap) is unchanged, so output cost is unaffected.

**Worst case** (Document Visibility Engine's own 15-document cap, every section maxed — 10 missing-evidence
items, 10 contradictions, 5 open actions, 20 timeline events, 15 documents at the full 1,500-char excerpt
budget): the `case_context_blok` alone measures **1,614 tokens** (≈$0.004/call at the same input rate). The
old bespoke `dokumenti` section stayed cheap regardless of document count (filenames only, ~5-10
tokens/document) — so the worst-case delta is driven entirely by the new Genome/gaps/document-excerpt
content this module never had before, not by a regression in how documents themselves are handled.

**Memory growth is expected and structural, not a leak**: the 311% in-memory delta is the canonical
context's own richer payload (Genome, gaps, actions, real document excerpts) held in memory for the
duration of one request — the same category of growth Tau 005 already measured and accepted for
`court_predictor.py`'s own full-context endpoints, not a new concern this migration introduces.

**Latency**: not independently measured this sprint (no live DB access from this environment) — flagged as
an assumption, not a verified fact, consistent with this program's own established practice (Tau
004/005 made the same disclosure). Structurally: `_load_all_context`'s 5 queries and
`build_case_context()`'s own 7 queries run **concurrently** (`asyncio.gather` at the call site, and
`build_case_context()`'s own internal `_fetch_raw` is itself a parallel gather) — wall-clock addition is
bounded by the slower of the two query sets, not their sum, the same reasoning Tau 002/005 already
established for this pattern.

## Verdict

The Factory pattern from `docs/tau/CANONICAL_CONTEXT_FACTORY.md` applied cleanly for 2 of the module's own
8 original bespoke fetches (straight swap) and added 5 genuinely new context dimensions the module never
had. 4 of the 8 needed Step 5's "keep bespoke, name why" treatment rather than a pure swap — this is exactly
the outcome the Factory's own design anticipated (a template to instantiate with judgment, not a mechanical
find-and-replace), not a failure of the pattern.
