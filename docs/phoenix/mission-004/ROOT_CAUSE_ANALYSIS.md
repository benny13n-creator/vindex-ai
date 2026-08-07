# Mission 004 — Root Cause Analysis

## Common root cause

Financial-correctness patterns (claim-based race protection, success-gated charging) are
proven and correct where they exist in this codebase, but were never audited across every
credit-charging call site as a category — each endpoint's own author reasoned about failure
modes locally, without a checklist cross-referencing already-fixed siblings in the same or
adjacent files.

## Per-item detail

- **`-006`**: `cio_daily` and `commander_jutarnji` are structurally near-identical
  (cache-check → generate → charge → persist, both backed by a `UNIQUE(user_id, datum)` table).
  Part A's own Team 8 (Data Integrity Chaos) found and fixed CIO's instance; this mission's own
  Wave 4 (Concurrency Chaos) independently found `commander_jutarnji`'s instance and explicitly
  named it "the unfixed twin." Sibling-file propagation of a proven fix was never systematized.
- **`-002`/`-027`**: `analiza()`'s success-gated pattern predates `nacrt()`/`podnesak()`'s
  authorship (or was added to `analiza()` specifically without a follow-up pass over its 2
  siblings in the same file) — the file itself is internally inconsistent about its own
  charging convention.

## Why the fix differs slightly between `-002` and `-027`

`-002`'s failure mode is genuinely binary — `generate_draft()` returns either a real result or
an explicit `{"status":"error",...}`, so gating on `status=="success"` is a complete,
correct check. `-027`'s `podnesak()` has 3 independent, individually-recoverable sub-steps —
gating on the SAME "any sub-step failed" bar as `-002` would over-correct (skip charging for a
draft that's still substantially useful, just missing a citation or two), so the fix instead
targets specifically the one sub-step (entity extraction) whose failure genuinely makes the
output closest to worthless — a proportionate response to a genuinely different failure shape,
not an inconsistency between the two fixes.

## Why `-006`'s fix needs no "claim a stale row" step (unlike CIO's)

`cio_daily`'s cache has an explicit 6-hour TTL — a same-day cache HIT can still be considered
stale and need re-claiming. `commander_jutarnji`'s cache check is purely `.eq("datum", danas)`
with no time-window logic at all — a row for today is unconditionally treated as fresh forever.
This means the "claim a stale-or-absent row" 2-step dance CIO needed collapses to a single
"claim via INSERT" step here, since there is no "stale but present" case to additionally handle.
