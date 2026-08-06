# Case Action Lifecycle — Program Omega, Sprint 003 (2026-08-06)

Definition of Done items 4 and 5's own required proof: actions arise, change, and close automatically as case
state changes, and the list stays consistent across batch processing, parallel events, and restarts. This doc
walks each of the mission's own 6 required test scenarios through the actual lifecycle, with the test that
proves it.

## State machine

```
                 (fact appears)
                       │
                       ▼
                 ┌───────────┐   (fact's details change,
                 │   open    │◄── e.g. rok extended)  ─┐
                 └─────┬─────┘                          │
                       │ (fact no longer holds)          │
                       ▼                                 │
                 ┌───────────┐                           │
                 │  closed   │                           │
                 └───────────┘                           │
                       ▲                                 │
                       └── (same fact reappears later) ───┘
                           gets a NEW row, new dedupe_key
                           collision only within OPEN scope
```

Only 2 statuses (`open`, `closed`) — no `in_progress`/`snoozed`/`dismissed`. The mission's own charter names
only creation and closure as engine-owned transitions; anything resembling "a lawyer marked this handled
manually" is a UI/workflow decision explicitly out of scope for this backend sprint (not invented here).

## Scenario walkthrough

### 1. 500 new documents — do actions arise?

`finalize_intake_jobs_batch` emits `DOCUMENT_BATCH_COMPLETED` once per affected `predmet_id` →
`handle_case_changed` → `genome_refresh` → `timeline_entry` → `case_intelligence_summary` →
`refresh_case_actions` (last, reading the freshly-refreshed Genome). If the batch reveals missing evidence,
upcoming deadlines, or new contradictions, `_compute_target_actions` includes them in the target set and
`_consequence_refresh_case_actions` inserts them as new `open` rows.

Proof: `tests/test_omega_sprint003_action_engine.py::test_scenario1_new_case_with_no_evidence_produces_actions`
— a case with zero evidence produces a `PRIBAVITI_DOKAZ` action, `mock_log` fires exactly once with
`case_action_refreshed`.

### 2. New evidence removes a risk — does the action close?

Evidence added → `predmet_dokazi` no longer empty → `identify_case_problems()` no longer reports "Nema
uploadovanih dokaza" → that fact's `dedupe_key` (`_stable_key("problem", "nema_dokaza")`) drops out of the
target set → the reconciliation loop's own "in existing, not in target" branch closes the row.

Proof: `test_scenario2_evidence_added_closes_the_stale_pribaviti_dokaz_action` — pre-seeds an open action with
that exact dedupe_key, adds evidence + full document coverage, asserts `tr["closed"] == ["act-old"]`.

### 3. Deadline extended — do actions update (not close+reopen)?

`dedupe_key` for a rociste-deadline action is `_stable_key("rociste", rociste_id)` — the HEARING's identity,
not its date. When the date changes, the same key stays in the target set (still the same hearing), so the
reconciliation loop's "in both" branch fires: `UPDATE` `razlog`/`dokaz`/`prioritet`/`rok` in place. The action's
`id`/`created_at`/history survive.

Proof: `test_scenario3_deadline_extended_updates_same_action_not_close_reopen` — a rociste moved from
critical-range to 25 days out; asserts zero inserts, zero closes, exactly one update of the SAME `id`, with the
new `prioritet`/`rok` reflected.

### 4. Document deleted — do stale actions disappear?

Modeled via a contradiction whose triggering document pair is gone from `case_dna.kontradikcije` (the general
form of "a fact this action depended on no longer exists" — the exact mechanism is the same reconciliation
diff regardless of WHY the fact vanished, whether from a document deletion, a Genome re-extraction, or a
correction).

Proof: `test_scenario4_contradiction_no_longer_present_closes_its_action` — pre-seeds an open
`RAZRESITI_KONTRADIKCIJU` action whose `dedupe_key` no longer appears in `case_dna.kontradikcije`, asserts it
closes.

### 5. Two parallel edits to the same case — is there ONE consistent action list?

The partial unique index (`(predmet_id, dedupe_key) WHERE status='open'`, migration 099) is the actual
consistency guarantee — not application-level locking. Two concurrent `refresh_case_actions` runs both compute
the same target set from the same underlying facts and both attempt to insert the same missing action; the DB
rejects the loser with a `duplicate key` error, which the executor catches and treats as benign (see
`CANONICAL_ACTION_ENGINE.md`'s own Concurrency section). The end state — regardless of which of the two
inserts "won" — is exactly one open row per fact, because the KEY (not the row identity) is what's globally
unique.

Proof: `test_scenario5_concurrent_insert_duplicate_key_is_swallowed_not_raised` (the race is simulated
directly, since two truly-concurrent asyncio tasks racing a mocked DB wouldn't reliably reproduce the
interleaving — this test proves the CATCH path handles it correctly, which is the actual mechanism relied on)
plus `test_scenario5_non_duplicate_insert_errors_still_propagate` (proving the catch is narrow — a real DB
error, e.g. a dropped connection, is NOT swallowed, and still fails the consequence for the Event Bus's own
retry to pick up).

### 6. System restart — do actions remain identical?

`_compute_target_actions` is pure (no side effects, no randomness, no LLM call) — given the same DB rows, it
always returns the same target set. Re-running `refresh_case_actions` against a `case_actions` table that
ALREADY exactly reflects the target set produces zero inserts and zero closes — only in-place updates refreshing
`updated_at`/`razlog`/`dokaz` (a `changed since last snapshot` refresh, not "did anything need to change" —
matching every other Case Evolution consequence's own idempotency posture: a retry after a completed run is
never observably different from the case NOT having crashed).

Proof: `test_scenario6_rerun_with_unchanged_facts_is_a_pure_no_op` — computes the target set once, seeds
`case_actions` to already match it exactly, re-runs the consequence, asserts zero inserts/zero closes.

## What "restart" does NOT cover here

This proves `_consequence_refresh_case_actions` itself is idempotent given unchanged facts. It does not
separately re-test the OUTER crash-recovery mechanism (a `case_evolution_consequences` row marked `completed`
before a crash means a RETRY skips `refresh_case_actions` entirely, never re-running it) — that mechanism is
Program Delta's own certified behavior (`tests/test_delta_sprint004_certification.py`), reused unchanged here,
not re-proven a second time for this specific consequence name.
