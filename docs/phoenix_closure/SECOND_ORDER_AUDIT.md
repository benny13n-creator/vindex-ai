# Phoenix Closure — Phase 7 Second-Order Audit

**Date**: 2026-08-08
**Scope**: every fix from Phase 3 (6), Phase 4 (9), and Phase 5's own correction (`-035`'s race
fix) — audited against the operation's own second-order questions, not "does it work" (already
proven in Phases 3-6) but "did fixing it introduce a DIFFERENT problem."

## Method

Each fix checked against: duplicate business logic, new truth source, bypassed canonical engine,
weakened security for UX, altered billing semantics, introduced race, stale cache, changed API
contract, GPT made more authoritative, removed validation, failure-looks-like-success, increased
query cost, new migration requirement.

## Findings requiring no action (checked, clean)

- **Duplicate business logic**: none. Every dedup fix (`-011`'s 3 executors, `-028`) reuses the
  exact idiom/window constant already proven for `-031`/`-043`, not a parallel implementation.
  `-042`'s reaper reuses `PREDMET_KREIRAN`'s exact detection template.
- **New truth source**: none. `-026`'s `top_open_action` reads the SAME `case_actions` already
  fetched for `readiness`; `-036`'s bulk-close reuses the SAME `case_actions.status` column
  `workspace.py` already reads; `-020`'s dedup check reuses Smart Intake's own `content_sha256`
  column and lookup shape verbatim.
- **Bypassed canonical engine**: none. `-042`'s reaper inserts into `events` directly (not via
  `emit_durable()`) — verified this is NOT a new bypass: `reap_missing_pipeline_events`, the
  already-shipped reaper this fix was explicitly modeled on, does the identical raw insert (a
  background repair job intentionally doesn't go through the same path a live HTTP request does;
  `dispatch_pending_events()` picks up either shape identically).
- **Weakened security for UX**: none. No auth/permission check was loosened anywhere. `-020`'s and
  `-036`'s new queries are correctly `user_id`/`predmet_id`-scoped (re-verified in Phase 5).
- **Altered billing semantics**: none. `-046` only changes WHETHER a loser generates its own report
  vs. reuses the winner's — the charge/no-charge decision (winner pays, loser never does) is
  unchanged. `-028`'s early-return path uses the same `UsageService.balance()` (no charge) the
  existing failure paths already use, not a new billing branch.
- **Introduced a race**: `-035`'s own case-switch race was the Phase 5 finding, already fixed and
  covered above that. No other fix introduces a new race — `-011`'s dedup checks are a
  belt-and-suspenders safety net behind the OUTER atomic claim (`_try_claim_consequence`), which
  already prevents true concurrent execution of the same executor for the same `event_id`.
- **Stale cache**: none introduced. No fix added a new cache layer.
- **Changed API contract**: several ADDITIVE changes only (`-038`'s `degraded_sources`/`truncated`,
  `-039`'s `pad_procene_truncated`, `-020`'s `mozda_duplikat`, `-025`'s `ai_generated`, `-026`'s
  `top_open_action`, `shared/case_context.py`'s `CONTRACT_VERSION` 1.1.0 → 1.2.0) — no existing key
  removed or retyped anywhere, consistent with the operation's own additive-only mandate.
- **GPT made more authoritative**: none. No fix changes how GPT output is trusted, clamped, or
  validated — `-023`'s OCR confidence is a *pytesseract* signal, not an LLM output.
- **Removed a validation**: none found.
- **Failure looks like success**: checked specifically for `-036`/`-011`'s best-effort side-writes
  (case_actions bulk-close, audit-log dedup) — both correctly log-and-continue on failure without
  claiming a false success for the SIDE-EFFECT itself; the PRIMARY operation's own success/failure
  is untouched, matching the established non-blocking-side-effect contract this codebase already
  uses (e.g. the pre-existing hronologija insert in the same function).
- **Increased query cost significantly**: `-038`'s truncation signal reuses the LENGTH of
  already-`.limit(200)`-fetched data (no new query) rather than adding a `count="exact"` query like
  `-003`/`-039` did — actually cheaper than the established pattern, not more expensive. `-020`'s
  one new indexed-lookup-shaped SELECT per upload mirrors Smart Intake's own already-proven-cheap
  usage of the same column. `-023`'s `image_to_data` vs. `image_to_string` is the same single
  Tesseract OCR pass with richer output, not a second OCR run.
- **New migration requirement**: zero. Every fix reuses an already-applied column or table
  (`content_sha256` migration 095, `trigger_event`/`event_id` on existing tables, `case_actions`'s
  existing `status` column). This was explicitly re-verified per item in the ledger, not assumed.

## Conclusion

No second-order regression found beyond the one already caught and fixed in Phase 5 (`-035`'s
case-switch race). All 15 fixes (6 from Phase 3, 9 from Phase 4) pass this audit clean.
