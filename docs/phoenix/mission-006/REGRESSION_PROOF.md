# Mission 006 — Regression Proof

## New tests (`tests/test_phoenix_mission_006_evidence_quality_signals.py`)

| Test | Proves |
|---|---|
| `test_klasifikuj_dokument_marks_genuine_failure` | A genuine OpenAI-client failure sets the `_klasifikacija_greska` flag while keeping `tip_dokaza="ostalo"` |
| `test_klasifikuj_dokument_genuine_success_has_no_failure_flag` | A real success carries no failure flag and does carry the validated confidence value |
| `test_reklasifikuj_skips_charge_on_genuine_failure` | The endpoint does not charge when classification fails |
| `test_reklasifikuj_charges_on_genuine_success` | The endpoint still charges normally on success (no over-correction) |
| `test_consequence_evidence_classify_logs_on_degraded_classification` | Structural: the event-driven path checks and logs the failure flag |
| `test_klasifikuj_dokument_enum_guards_unrecognized_pouzdanost` | A poisoned/out-of-schema confidence value fails safe to `"niska"` |
| `test_classify_system_prompt_asks_for_pouzdanost` | The prompt itself requests the field |
| `test_frontend_reklasifikuj_reads_real_response` | The frontend caller reads the real response instead of assuming success |

## Original-scenario rerun

`test_reklasifikuj_skips_charge_on_genuine_failure`/`test_reklasifikuj_charges_on_genuine_success`
directly reproduce both halves of the debt item's own scenario and confirm the correct branch.

## No pre-existing test corrections needed this mission

211 pre-existing tests across 18 files all passed unmodified.
