# Mission 003 — Regression Proof

## New tests (`tests/test_phoenix_mission_003_institutional_memory.py`)

| Test | Proves |
|---|---|
| `test_firm_memory_all_vaznost_orderings_are_descending` | All 5 real call sites (comments excluded) use `desc=True` |
| `test_kontekst_za_ai_returns_high_importance_memories_first` | Behavioral: a high-importance memory now appears before a low-importance one in the actual AI-context string, using a stateful fake that genuinely sorts (not a passthrough mock) |
| `test_memory_graph_reuses_canonical_kancelarija_helper` | `memory_graph._get_firma_id is` the canonical `get_kancelarija_id` function object (identity, not just behavior) |
| `test_memory_graph_has_no_local_duplicate_definition` | The local duplicate definition is structurally gone |
| `test_semantic_registry_has_probability_concept` | `PROBABILITY` is registered, in `ALL_CONCEPTS`, and lookups resolve correctly |
| `test_risk_engine_logs_malformed_hearing_date` | A malformed date now produces a warning log line, while the function still returns a valid result (behavior unchanged) |

## Original-scenario rerun

`test_kontekst_za_ai_returns_high_importance_memories_first` is a direct behavioral
reproduction of the debt item's own worst-case example — the AI-context endpoint specifically.
`test_risk_engine_logs_malformed_hearing_date` directly reproduces "a `rokovi` row with a
malformed `datum`" and confirms the log line now fires.

## No pre-existing test corrections needed this mission

All 4 fixes were either purely additive (`-017`) or behavior-preserving (`-055`'s logging,
`-052`'s identical-behavior import swap, `-008`'s sort direction only affecting output order
which no pre-existing test asserted an exact order for).
