# Mission 003 — Root Cause Analysis

## Common root cause

All 4 findings are "institutional knowledge infrastructure built/extended incrementally,
without a systematic sweep back over already-shipped code when a new convention (canonical
tenant-resolution helper, canonical semantic registry) or a new enum's natural sort order was
introduced." None are logic errors in the traditional sense — each is a place where a
reasonable default (alphabetical sort, a locally-convenient duplicate, an incomplete registry
port, a bare except copied from a working pattern elsewhere) silently diverged from actual
intent.

## Per-item detail

- **`-008`**: Supabase's `.order(col)` defaults to ascending with no compile-time or runtime
  warning that this might not match a hand-rolled enum's intended importance order — a
  footgun with no natural guard against it beyond manual review, which this specific
  code apparently never got until this mission's Red Team pass.
- **`-052`**: consolidation efforts (like the 2026-07-26 one) are necessarily scoped to the
  files known to have the problem AT THE TIME — `memory_graph.py` either postdates that sweep
  or wasn't flagged by whatever detection method found the original 2 duplicates.
- **`-017`**: `semantic_registry.py`'s own docstring says it's "a machine-readable index of
  TRUTH_CONTRACT.md" — the human document and the machine index were built in the same mission
  but evidently not cross-checked 1:1 for completeness before that mission closed.
- **`-055`**: a bare `except: pass` is a common, low-effort way to make a loop "safe" against
  malformed input during initial development; the cost (silent data loss) only becomes visible
  much later, and by the time 2 real bugs were found and fixed INSIDE that except's blast
  radius, the except itself was never revisited as the actual root enabler of both.

## Why these fixes are genuinely minimum-risk

- `-008`: `desc=True` is a parameter Supabase's own query builder already supports — no new
  capability, purely a call-site change.
- `-052`: import + delete, the exact remediation the 2026-07-26 consolidation already
  established as correct for this exact bug class.
- `-017`: purely additive (a new tuple entry) — cannot break any existing lookup.
- `-055`: adds a `logger.warning` call inside an already-existing except block; the control
  flow (catch and continue) is completely unchanged.
