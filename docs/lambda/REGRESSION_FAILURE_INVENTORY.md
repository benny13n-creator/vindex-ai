# Regression Failure Inventory — Program Lambda, Certification 003A

**Baseline at sprint start**: `2,984 passed, 1 skipped, 7 failed, 22 warnings` (full suite, `python -m pytest -q`).

## Complete failure list

All 7 failures confined to a single file: `tests/test_akcija2_faza4_2026_07_24.py`.

| # | Test | Exception | First failing line |
|---|---|---|---|
| 1 | `test_batch_segments_postuje_budzet` | `AssertionError: assert 0 == 4` | `tests/test_akcija2_faza4_2026_07_24.py:52` |
| 2 | `test_batch_segments_predugacak_segment_dobija_sopstveni_batch` | `AssertionError` (same shape) | same file |
| 3 | `test_batch_segments_prazna_lista` | `AssertionError` (same shape) | same file |
| 4 | `test_ask_analiza_v2_map_reduce_ne_gubi_rizicnu_klauzulu_na_kraju` | `AssertionError` (same shape) | same file |
| 5 | `test_ask_analiza_v2_map_reduce_odbacuje_nevalidan_clause_ref` | `AssertionError` (same shape) | same file |
| 6 | `test_ask_analiza_v2_kratak_dokument_ne_ide_kroz_map_reduce` | `AssertionError` (same shape) | same file |
| 7 | `test_map_batch_neuspesan_ne_obara_celu_analizu` | `AssertionError` (same shape) | same file |

**Representative traceback** (test #1):
```
assert len(batches) == 4
AssertionError: assert 0 == 4
 +  where 0 = len(<MagicMock name='mock._batch_segments_za_map()' id='...'>)
```
Every one of the 7 follows this identical shape: a call into `main._batch_segments_za_map` or
`main.ask_analiza_v2` returns a `MagicMock()` instance instead of a real value, because `main` itself
resolves to a `MagicMock()` object instead of the real module at the moment these tests execute.

## Failure category

**Single root cause, category (C) fixture/mocking problem** — specifically an unscoped global mock leak
across test files via `sys.modules`. Not (F) real production bug, not (H) race condition, not (I) flaky test
(100% deterministic under full-suite collection, 0% under isolated-file execution — not timing-sensitive).
Full clustering evidence in `ROOT_CAUSE_ANALYSIS.md`.

## Scope confirmation

Exhaustive grep of the full suite confirms these 7 are the ONLY failures — no other file, category, or
exception shape appeared anywhere in the baseline run.
