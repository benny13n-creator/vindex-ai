# Performance / Scaling Audit — Program Lambda, Master Sprint 001

Adversarial audit: does the platform actually handle 500/1,000/5,000/10,000 documents, or a large
portfolio? Code-level + existing-test-level, no live load-testing environment available.

## Findings

| # | Finding | Status | Severity |
|---|---|---|---|
| 1 | `shared/case_context.py::_fetch_raw`'s own `predmet_dokumenti` query had no `.limit()` and selected full `tekst_sadrzaj` for every row unconditionally. The existing 500/1000-document tests only ever exercised `_select_documents()` on an in-memory list built by the test — never this SQL query. At 5,000-10,000 real document rows, this single query would pull that many full-text rows over the network before any bounding logic ran. The claimed "proven at 1,000" did not actually generalize to 5,000/10,000. | **FIXED this sprint** — split into a metadata-only query (all rows, no `tekst_sadrzaj`) for the existing selection algorithm, then a 2nd, targeted query fetching text for ONLY the ~15 documents actually selected. Zero change to selection behavior or output shape — proven by a new excerpt-content test that would have caught the fix's own first implementation bug (see below). | High → Closed |
| 2 | While writing the fix's own proof test, discovered the fix's first implementation silently failed against the EXISTING test suite's own fake Supabase double (missing `.in_()` support) — all 27 pre-existing tests in `test_tau002_case_context.py` still passed despite document excerpts going empty, because none of them asserted on excerpt CONTENT, only count/id/naziv. | **FIXED this sprint** — added `.in_()` to the test fixture and a new test asserting real excerpt text content, closing a real, previously-invisible test-coverage gap in the same pass | — (test-coverage gap, not a production bug) |
| 3 | `routers/health_index.py` and `routers/dashboard.py::command_center` both fetch all of a user's `predmeti` rows with no `.limit()`; `health_index.py` additionally selects the full `case_dna` JSONB blob per row | Named as `LAMBDA-005` (addendum to `TAU-018`), not fixed — bundled into `health_index.py`'s own already-planned future consolidation sprint rather than patched in isolation | Low-Medium |
| 4 | `case_commander.py` (`.limit(20)`) and `cio.py` (`.limit(40)`) portfolio loops | Confirmed caps still in place, no regression since Tau 007/008 | — |
| 5 | Genome extraction's own `_GENOME_MAX_DOCS=25` cap | Confirmed still enforced at the query level | — |
| 6 | N+1 query patterns in 4 spot-checked files (`billing_reports.py`, `evidence_graph.py`, `cross_doc.py`, `case_dna.py`) | None found | — |

## Verdict

The mission's own explicitly-named gap (5,000/10,000 documents) turned out to be real, not a false alarm —
found, fixed, and proven this sprint, without changing any observable behavior (same documents selected,
same excerpts, same response shape). The fix's own proof process caught a 2nd, genuinely valuable finding:
an existing test suite that looked thorough (27 tests, 500/1000-document coverage) had a real, silent blind
spot in what it actually verified. Both are now closed. One smaller, lower-urgency scaling finding (#3) is
named and deliberately deferred to a larger planned consolidation rather than patched piecemeal.
