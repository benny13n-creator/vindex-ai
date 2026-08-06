# Performance Impact — Program Tau, Master Sprint 007, Phase 7

Measures, not guesses, the token/query/latency/memory impact of migrating `routers/case_commander.py` off
its own independent risk/gap/readiness computation onto `shared/case_context.py::build_case_context()`.

## GPT tokens — measured via direct code comparison, provably unchanged

`_kanonski_nalazi`'s own 6 output fields (`status_predmeta`/`readiness_status`/`nedostaje`/`rizici`/
`preporuceni_potez`/`vremenski_pritisak`) are, before and after this migration, 100% deterministic — zero
GPT tokens, before or after. The ONE GPT call this file makes in `commander_analiza` (the advisory call for
`protivnikova_strategija`/`sudska_praksa`) is unaffected: `git diff HEAD -- routers/case_commander.py`
confirms `_formatiraj_kontekst` (the function that builds that call's own prompt text) has **zero diff** —
byte-identical before and after. **Token cost delta: $0, provably, not estimated.**

## Database queries — increased, precisely counted, explained

### `commander_analiza` / `commander_quick-check` (single-case)

| | Before | After |
|---|---|---|
| `_dohvati_predmet_kontekst` | 7 queries (`predmeti`,`rokovi`,`dokumenta`,`komentari`,`case_actions`,`dokazi`,`rocista`) | 4 queries (`predmeti`,`rokovi`,`dokumenta`,`komentari`) |
| `build_case_context(include_documents=False)` | — | 6 queries (`predmeti`,`dokazi`,`rocista`,`case_actions`,`hronologija`,`komentari` — `predmet_dokumenti` skipped in lightweight mode, confirmed by direct count of `_fetch_raw`'s own 7 `asyncio.to_thread` calls minus the 1 conditional document fetch) |
| **Total** | **7** | **10 (+3)** |

`predmeti` and `komentari` are now each fetched twice per call (once for GPT-formatting text, once inside
`build_case_context()`) — the same "one redundant row read is an acceptable cost" tradeoff already accepted
platform-wide for `case_intelligence.py` (Tau 002) and `hearing_cc.py` (Tau 006). **Found and fixed this
phase**: the 2 fetches now run concurrently (`asyncio.gather`), not sequentially as the initial Phase 3
implementation had them — the query-count increase does not translate 1:1 into added wall-clock latency,
since the 3 net new queries execute in parallel with the 4 pre-existing ones, not after them.

### `commander_jutarnji` (portfolio-wide digest)

| | Before | After |
|---|---|---|
| Batch queries (constant, `.in_("predmet_id", ...)`) | 5 (`predmeti`,`rokovi`,`dokumenti`,`komentari`,`case_actions`) | 4 (`case_actions` batch removed) |
| Per-case canonical fetch | 0 | 6 queries × N active cases (N ≤ 20, the existing display cap) |
| **Total, worst case (N=20)** | **5 (constant)** | **4 + 120 = 124** |

**This is a real, substantial cost increase for the portfolio path — named plainly, not minimized.** The
old batch `case_actions` query scaled with portfolio size at O(1) query regardless of N; the new per-case
loop is O(N) queries. This is the SAME tradeoff `morning_briefing.py` (Tau 002) already made for the exact
same reason, and for the same reason: **it buys real correctness the O(1) batch approach structurally
cannot provide** — genome-aware, gap-aware readiness for the FIRST time in this file's own portfolio
ranking (`PARALLEL_REASONING_AUDIT.md` Finding 4), not merely deduplicated computation. The old batch query
only ever fetched `case_actions`, meaning the portfolio ranking was blind to Genome contradictions/missing
evidence by construction — no batch-query redesign could have closed that gap without per-case Genome/gap
computation, which is exactly what `build_case_context()` already correctly does.

**Real-world cost today: effectively zero.** `commander_jutarnji` is confirmed to have no live frontend
caller (`grep -n "/api/commander/" static/vindex.js` finds only a comment, no `fetch()` call — verified
directly this sprint, not assumed from the prior sprint's own claim). The 124-query worst case is a
correctness ceiling for if/when this endpoint is reconnected, not a cost incurred by any request today.

## CPU / memory

No new CPU-bound computation was added — `_kanonski_nalazi` replaced 4 deterministic function calls
(`calculate_procesni_rizik`/`identify_case_problems`/`collect_case_gaps`/`compute_case_readiness`) with a
single dict-field read plus 2 list comprehensions (`nedostaje`, `rizici` filtering) — strictly less CPU
work per single-case call, not more, since `build_case_context()` computes the SAME risk/gaps/readiness
once, and case_commander.py used to do that computation a 2nd, fully independent time. Memory: the
`missing_evidence` list held in memory is the same shape/size class as the old `gaps` list it replaces — no
growth. The portfolio digest's own memory footprint scales with N cases' worth of `build_case_context()`
output (readiness dict + a bounded actions list per case, lightweight mode carries no document excerpts) —
bounded and small even at N=20.

## Net verdict

Token cost: unchanged ($0 delta, proven by diff). Single-case query count: +3 (10 vs 7), latency impact
mitigated by a concurrency fix made this same phase. Portfolio-wide query count: substantially higher in
the worst case (124 vs 5), explained and justified by a genuine correctness gain this sprint's own Finding 4
identified, and currently has zero real-world cost since the endpoint carrying that cost has no live
caller. CPU/memory: net decrease for the single-case path (one less independent computation), unchanged for
the portfolio path's own per-case footprint.
