# Context Performance Analysis — Program Tau, Master Sprint 002, Phase 6

**Scope**: measure/estimate token, document-count, latency, and cost impact of the Phase 5 migration; document
the pruning/relevance-ranking/caching decisions already built into `shared/case_context.py`. No new GPT
calls were added anywhere in this sprint — every cost figure below is a **database read** cost, not a
token cost, unless stated otherwise.

## 1. Query count impact, per migrated flow

| Flow | Before (queries) | After (queries) | Delta | Parallelized? |
|---|---|---|---|---|
| `copilot.py::_handle_analiza_predmeta` | 5 | 5 | 0 (same query, wider `select`) | Yes (`asyncio.gather`, unchanged) |
| `copilot.py::_handle_plan_predmeta` | 4 | 4 | 0 (same query, wider `select`) | Yes (unchanged) |
| `case_intelligence.py::_gather_case_data` | 6 (1 predmet + 5 gather) | 6 + 7 nested = **13** | +7 | Partially — the new `build_case_context()` call runs alongside the other 5 in the outer `gather`, but its own 7 sub-queries are a 2nd round-trip depth nested inside that one task |
| `morning_briefing.py::_generiši_briefing` | 4 | 4 + (≤10 × 6) = **up to 64** | up to +60 | Yes — all ≤10 `build_case_context(include_documents=False)` calls run concurrently via `asyncio.gather`, and each one's own 6 sub-queries also run concurrently |

**Copilot's own delta is zero** — this is a query-shape change (wider `select`, `tekst_sadrzaj` added),
not an additional round trip. **Case Intelligence's delta is bounded and one-time per briefing** (+7
queries, one extra round-trip depth). **Morning Briefing's delta is the one genuinely worth watching** —
up to 60 additional queries per user per daily briefing generation. The cron job (`POST
/api/briefing/cron`) fans this out across every user, so at N users the added query volume is up to `60N`
per run.

## 2. Why the Morning Briefing cost was accepted as-is, not deferred

Per Tau Sprint 001's own `GPT51_COST_OPTIMIZATION.md` finding: `morning_briefing.py`'s cron job already
runs on a schedule (06:00 UTC daily) with hours of runway before the digest needs to reach anyone — it is
the single most latency-tolerant call site in the platform, "a structurally safer place to trial higher
latency... without any UX cost." The added queries are read-only, indexed lookups (`predmet_id`/`id`
equality, no table scans), and Postgres/Supabase is built for exactly this kind of bursty, short-lived read
load. `include_documents=False` already removes the single most expensive part of `build_case_context`
(the document fetch + excerpt loop) for this specific caller — the remaining 6 queries per case are all
small, single-table, indexed reads.

**If this ever becomes a real bottleneck** (large user bases, many active cases each): the documented
alternative is a single bulk query — `case_actions`/`rocista` fetched once per user with an `.in_(predmet_id,
[...])` filter instead of N separate `build_case_context()` calls — trading the Case Context Contract's own
reuse-by-construction guarantee for a hand-rolled batch path. Not implemented this sprint (no evidence yet
that it's needed — this is a "watch it," not a "fix it," per this program's own established discipline of
not solving unproven problems).

## 3. Token/character budget accounting

| Field/flow | Budget | Where |
|---|---|---|
| `_select_documents` — documents per `build_case_context` call | ≤`MAX_DOCS_INCLUDED` (15), 5 always-recent + stride sample | `shared/case_context.py:76-78` |
| `_excerpt` — chars per document (default) | 1500 | `shared/case_context.py:75` (`DOC_EXCERPT_BUDGET_PER_DOC`) |
| `copilot.py`'s own document section | ≤5 docs × 800 chars = ≤4000 chars | Deliberately smaller than the default — copilot is a lightweight assistant, not a full dossier |
| `case_intelligence.py`'s own new sections | ≤4 docs × 500 chars + terse evidence/action/deadline rows ≈ ≤2500 chars | Bounded specifically to protect the pre-existing `context_text[:10000]` hard cut from starving lessons/firm-DNA/decisions content |
| `morning_briefing.py`'s own readiness annotation | 1 short string (`readiness: STATUS`) per case line | Effectively free — no document text involved (`include_documents=False`) |

**No GPT `max_tokens` (output budget) changed anywhere in this sprint.** All figures above are input-side
(what goes INTO the prompt), consistent with this sprint's own zero-new-GPT-calls constraint.

## 4. Cost impact (GPT/token spend)

**Zero direct token-cost increase from this sprint.** No model was swapped, no new GPT call was added, no
`max_tokens` was raised. The only prompt-size changes are: `copilot.py`/`case_intelligence.py` now include
MORE input text per existing call (document excerpts they didn't send before) — a real, small increase in
input tokens per call, bounded by the budgets in §3 above, and directly justified by Tau Sprint 001's own
`CASE_CONTEXT_ARCHITECTURE.md` finding that these exact calls were reasoning over incomplete context. This
is the cost of fixing the actual problem the mission was chartered to fix, not incidental bloat.

## 5. Relevance ranking / pruning (already built, documented here for Phase 6 completeness)

`_select_documents`'s own recency-first-plus-stride-sample selection (`DOCUMENT_VISIBILITY_ENGINE.md`) IS
this sprint's context-pruning mechanism — it is not a separate Phase 6 feature bolted on afterward. There
is no keyword/embedding-based relevance ranking (no query to rank against in a generic context-assembly
call); recency + deterministic full-set coverage was judged the right default given no vector index exists
over case documents specifically (Pinecone/RAG in this codebase indexes case LAW, not case documents).

## 6. Caching — explicitly not implemented, and why

`CANONICAL_CASE_CONTEXT_CONTRACT.md`'s own "Non-goals" section already states this decision and its
reasoning: every `build_case_context()` call re-fetches fresh from Supabase, with no cache layer. This is a
deliberate correctness choice (Phase 7's own no-stale-data requirement — a Genome refresh or new document
upload must be reflected on the very next call, not after a cache TTL expires) over a performance
optimization. Given the query counts in §1 are all small, indexed, single-table reads (not expensive
joins or aggregations), the correctness cost of introducing a cache was judged to outweigh the performance
benefit at current scale.
