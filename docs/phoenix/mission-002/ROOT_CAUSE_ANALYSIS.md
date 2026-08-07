# Mission 002 — Root Cause Analysis

## Common root cause

All 3 findings are the same architectural gap named repeatedly across this engagement's prior
missions: **a proven concurrency-safety pattern exists in the codebase, but propagating it to
every relevant call site was never systematically verified** — each new editable field/table
was built independently, sometimes copying the pattern (case close, Kanban `faza`), sometimes
not (case core fields' frontend, `zadaci`, `learning.py`'s status write).

## Per-item detail

- **`-007`**: `update_predmet`'s `if_updated_at` support (Program Lambda Certification 004) was
  added specifically because a Chaos Engineer fork found the blind last-write-wins bug — but
  that same certification's own scope was the BACKEND fix; wiring every frontend caller to
  actually send the new precondition was implicitly assumed done, not verified against the live
  caller. This is exactly the "declared control ≠ enforced control" pattern the Forensic
  Remediation Mission named as this platform's single most recurring failure signature.
- **`-033`**: `learning.py`'s outcome-recording endpoint was built to ALSO close the case as a
  side effect (a reasonable design — recording an outcome implies the case is done), but its
  author copied only the `.update({"status": "zatvoren"})` call, not the concurrency guard or
  audit-trail write that the two OTHER status-closing call sites (`predmeti_close.py`) already
  had at the time this endpoint's status-write code was likely written or last touched.
- **`-034`**: `zadaci` is architecturally a sibling of `case_actions` (both are "actionable work
  item" tables) but was built independently, before or without `case_actions`'
  `_consequence_refresh_case_actions`'s own optimistic-concurrency fix (Operation Singular
  Intelligence Mission 002) existed as a pattern to copy.

## Why `if_updated_at` (optimistic concurrency) and not a lock

Consistent with every prior concurrency fix in this engagement (`case_actions`, CIO `/daily`,
billing entries): Postgres advisory locks don't fit this codebase's per-call PostgREST execution
model (no held-open transaction spanning multiple Python-side calls). Optimistic concurrency via
an existing `updated_at` column is the established, zero-migration-needed idiom.

## Why `-033`'s guard is non-fatal but `-007`/`-034`'s are surfaced to the user

`update_predmet` and `azuriraj_status` are both direct, synchronous user actions where the user
is actively waiting for a save confirmation — a silent clobber there is a direct, immediate data-
loss experience. `learning.py`'s status close is a SIDE EFFECT of recording a learning outcome;
if a concurrent reopen already won, the case is already in a state a colleague deliberately
chose, and forcing this endpoint's own close to error out (rather than the outcome-recording
itself, which is this endpoint's actual purpose) would be a worse UX for no correctness benefit —
consistent with this endpoint's existing pattern of treating every side-effect step as best-
effort/non-fatal.
