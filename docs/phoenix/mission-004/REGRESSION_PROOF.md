# Mission 004 — Regression Proof

## New tests (`tests/test_phoenix_mission_004_financial_credit_gating.py`)

| Test | Proves |
|---|---|
| `test_commander_jutarnji_concurrent_calls_charge_only_once` | 2 near-simultaneous calls for the same user/day charge exactly once (real interleaving via a stateful fake table + unique-constraint simulation, same technique as Part A's CIO proof) |
| `test_nacrt_does_not_charge_on_generation_failure` | A total generation failure produces zero charge, returns balance instead |
| `test_nacrt_charges_on_genuine_success` | A genuine success still charges normally (no over-correction) |
| `test_podnesak_skips_charge_only_when_entiteti_empty` | Structural: the gate targets specifically `entiteti`, not any sub-step |

## Original-scenario rerun

`test_commander_jutarnji_concurrent_calls_charge_only_once` is a direct reproduction of the
debt item's own scenario (2 open tabs both loading the dashboard) — against the pre-fix code
this test's `await_count` assertion would be `2`, not `1`.

## No pre-existing test corrections needed this mission
