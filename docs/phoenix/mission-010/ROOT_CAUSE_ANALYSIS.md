# Mission 010 — Root Cause Analysis

## Root cause

`drafting/router.py` (the quick single-shot `/api/nacrt` path) and `routers/drafting.py`'s own
`/api/podnesak` logic (the case-scoped, richer path) were built as genuinely separate surfaces
by explicit founder decision (Core Consolidation Sec 1.4: "interim ownership, NOT merged,
pilot-gated"). `/api/podnesak` was built later and gained RAG retrieval + a critique pass as
part of its own hardening (FAZA 3, 2026-07-24). `/api/nacrt` never received the equivalent
upgrade — not because it was judged unnecessary, but because the 2 paths are intentionally kept
separate pending the founder's empirical pilot comparison, and nobody had yet done the
mechanical work of porting the newer path's safety infrastructure back into the older one.

The result: a field like `pravni_osnov_clan` asks GPT to pick a specific ZOO article number
"from general knowledge," with the SAME underlying GPT-4o model that, on `/api/podnesak`, would
have RAG context to ground that exact kind of claim in and a 2nd pass to catch it if it didn't.
Same model, same failure mode, but only one of the two surfaces had the safety net.

## Why this is a real feature-scope change, not a mechanical fix

- `generate_draft()` is synchronous (runs inside `asyncio.to_thread` from its one caller) while
  `_critique_and_refine_draft` is async — a straight import would have required either making
  `generate_draft` async (touching its call site and every internal blocking call) or writing a
  synchronous port. Chose the sync port: smaller blast radius, zero call-site changes anywhere
  in `routers/drafting.py::nacrt()`.
- `drafting/router.py` cannot import from `routers/drafting.py` (the reverse import already
  exists: `routers/drafting.py` does `from drafting.router import generate_draft`) — a naive
  "just import `_critique_and_refine_draft`" would have created a circular import. Solved by
  extracting the 2 pieces of shared logic (`izvori_kontekst`, `CRITIQUE_SYSTEM`) into a new
  `shared/drafting_grounding.py` module both surfaces import from — the single-canonical-owner
  pattern this whole engagement already applies elsewhere, not a new architectural idea.
- Real added latency: up to 2 more blocking LLM calls (RAG retrieval + critique) on top of the
  existing extraction call — the debt register itself named this as an accepted, unavoidable
  cost of closing a CRITICAL hallucination risk, not something to optimize away in this mission.

## Why `-014` was not touched

`-014` (extraction prompts instructing "return blank" instead of "omit unknown fields," which
defeats the `[FIELD — POPUNITI]` visible-placeholder fallback) is a real, systemic, but
*separate* defect — different mechanism (missing-field disclosure, not hallucination), different
fix shape (prompt text across ~12 templates in 2 files), and the debt register explicitly listed
it as its own item with its own "not fixed this mission" note. Bundling it into this mission
would have widened the blast radius of an already-large change; it remains the standing #1
recommendation for the next mission touching drafting prompts.
