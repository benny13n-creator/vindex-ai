# Mission Review — ZTC-002: Case Genome silent document cap + concurrent-refresh race (Scenario G + F)

**Mission Board entry:** `MISSION_BOARD.md`, ZTC-002.
**Executed by:** Operation Autonomous Law Office (BETA-002), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### Scenario G — the bug was worse than the hypothesis
Going in, the hypothesis was "expensive reprocessing on large cases." The actual finding was more
specific and more serious: `_GENOME_MAX_DOCS = 25` (`routers/case_dna.py`), and both places that fetch
documents for Genome analysis queried `.order("redni_broj").limit(_GENOME_MAX_DOCS)` — **ascending**,
i.e. upload order. For any case with more than 25 documents, only the **first 25 ever uploaded** were
ever considered — document #30, #100, #300 (which could be the final judgment, the decisive piece of
evidence, anything) was silently invisible to Case Genome forever, with no signal to the lawyer that
this truncation was happening.

Worse: the reported `_genome_docs_preskoceno` ("documents skipped") count was computed as
`len(docs) - _GENOME_MAX_DOCS` **inside** `_extract_genome`, where `docs` was the caller's *already
DB-limited-to-25* list — so this number was reporting `25 - 25 = 0` for exactly the cases where real
truncation was occurring. The one piece of the system that looked like it would tell you truncation
happened could never actually detect it for the case that mattered.

### Fix
1. Order by `redni_broj DESC` instead of ascending, at both call sites (`_do_genome_refresh` and
   `refresh_case_dna`) — when truncation is unavoidable, the most recent filings/decisions are
   considered rather than only the earliest ones. GPT still sees each document's real `redni_broj` in
   its per-document header, so presentation order doesn't affect comprehension.
2. Added a true, separate count query (`count="exact"`, not the already-limited fetch) and threaded
   it into `_extract_genome` as `ukupno_u_predmetu`, so `_genome_docs_preskoceno` reports the actual
   number of documents excluded from analysis, not an artifact of the query's own limit.
3. Logs a warning when truncation occurs, so it's discoverable in production logs even before any
   future UI surfaces it to the lawyer directly.

**Not attempted**: a smarter document-selection heuristic (e.g. "always keep the first filing plus
the N most recent"). Flipping to pure recency is a defensible, low-risk default improvement over pure
upload-order, but choosing the *ideal* subset for legal relevance is a product/domain judgment call,
not an engineering one — surfacing the truncation accurately (so it's at least visible) was treated as
the safe, uncontroversial part of this fix; refining the selection heuristic further is a smaller
follow-on if the founder wants to prioritize it.

### Scenario F — race condition, made worse by ZTC-001
No debounce or coalescing existed anywhere on Genome refresh. Every trigger (`api.py`, `rocista.py`,
`smart_intake.py`) independently does a full read-modify-write: load `case_dna`, recompute via a full
LLM call, `verzija = stari_verzija + 1`, write back — with **no version check on the write**. Two
concurrent triggers for the same `predmet_id` can both read the same `verzija`, both compute the same
next version, and whichever write lands last silently wins; the other's contribution to the *current*
Genome state is lost until the next trigger fires (self-healing eventually, but a real window of
incorrect data). This risk becomes materially more frequent the moment ZTC-001 (multi-document
batches attaching to one case) ships, since each attached document independently schedules its own
Genome refresh for the *same* case in quick succession.

### Fix
An in-process coalescing wrapper: `_run_genome_background` (the public name every caller already
uses) now just tracks which `predmet_id`s are currently refreshing; a trigger arriving while one is
already in flight for the same case sets a "run once more" flag and returns immediately instead of
running a fully parallel second execution. Since a full refresh always re-reads *all* current
documents (never incremental), running it once and then once more (if needed) produces the same end
state as running every trigger separately — minus the lost-update race and the redundant GPT calls.
The actual refresh logic (previously the whole body of `_run_genome_background`) was renamed to
`_do_genome_refresh` with no behavior change; existing callers and existing tests
(`tests/test_case_dna_events.py`) needed no changes since the public function name and signature are
unchanged.

**Explicitly not claimed as a complete fix**: this is a same-process, in-memory guard (a Python
`set`), not a database-level lock — it does not coalesce triggers arriving in different worker
processes. Documented in the code comment as a real, known limitation rather than presented as fully
solved.

---

## Implementation
`routers/case_dna.py` — `_extract_genome` gains `ukupno_u_predmetu` param; both document-fetch call
sites order `desc=True` and pass a true count; `_run_genome_background` becomes a coalescing wrapper
around the renamed `_do_genome_refresh`.

---

## QA Report

### User Scenario Test
```
Scenario G: a case has 40 documents; Genome refreshes.
Before: documents #26-40 (including the 3 most recent filings) never
reach Genome's analysis, and the platform reports "0 documents skipped" --
looks complete, isn't.
After: documents #16-40 (25 most recent) are analyzed; the platform
correctly reports 15 documents skipped.
PASS -- tests/test_ztc_genome_scale_and_race.py::test_extract_genome_reports_true_skipped_count_when_provided

Scenario F: a lawyer's batch upload finalizes 3 documents into the same
case within a few seconds of each other.
Before: 3 independent Genome refreshes could race; one document's
contribution to the current Genome state could be silently lost.
After: the 2nd and 3rd triggers, if they arrive while the 1st is still
running, coalesce into exactly one extra run instead of racing.
PASS -- tests/test_ztc_genome_scale_and_race.py::test_concurrent_trigger_for_same_predmet_is_coalesced_not_dropped
```

### Regression suite
8 new tests, all passing (3 for the truncation-accuracy fix, 1 for descending-order + true-count
wiring, 3 for the coalescing wrapper, 1 confirming different cases never block each other). Full
suite: 2306 passed, 1 skipped, 0 failed.

### Rollback strategy
Pure application code. `_do_genome_refresh` rename is internal (module-private, `_`-prefixed) — no
external caller references it directly. Revert restores prior ascending-order, no-coalescing behavior.

---

## Lessons Learned
Same shape as this session's other findings (LZ-001, LZ-002): a signal that *looks* like it reports a
problem (`_genome_docs_preskoceno`) was actually reporting the wrong thing for exactly the cases where
it mattered most — because it was computed from data the caller had already silently truncated before
the reporting code ever saw it. Worth restating as a standing check: when a "here's what we skipped"
counter exists, verify it's counting against the *true* total, not an already-filtered intermediate.

## Founder Summary
Case Genome no longer silently loses track of a case's most recent documents once it passes 25 total,
and now accurately reports when documents are excluded instead of a wrong "nothing skipped" number.
Concurrent Genome refreshes for the same case (which the batch-upload fix above makes routine) no
longer race in a way that can silently drop a document's contribution to the case analysis. 8 new
tests, zero regressions.
