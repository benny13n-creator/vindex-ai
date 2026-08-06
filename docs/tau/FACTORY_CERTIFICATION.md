# Factory Certification — Program Tau, Master Sprint 006

Certifies whether the Canonical Context Migration Factory (`docs/tau/CANONICAL_CONTEXT_FACTORY.md` +
`docs/tau/MIGRATION_TEMPLATE.md`) actually generalizes, per Phase 5 (adversarial review), Phase 7
(simulation against 3 further modules, none migrated), Phase 8 (immediate fixes), and Phase 9 (regression).

## Phase 5 — Adversarial review verdict

Attacked the pilot migration (`routers/hearing_cc.py`) directly, since it's the only module this sprint
actually changed:

| Attack | Result |
|---|---|
| Poisoned GPT response (`hearing_score=95`) against a `CRITICAL_GAP` case | Held — deterministic cap forces 50, proven by `test_hearing_command_center_caps_score_on_critical_gap_even_if_gpt_disagrees` |
| Nonexistent case (`build_case_context()` returns `predmet_not_found`) | Held — formatter returns `""`, endpoint still correctly 404s via `_load_all_context`'s own independent check |
| Missing Genome (`key_facts.value is None`) | Held — Genome section skipped cleanly, no crash |
| Bare/incomplete case (nothing populated anywhere) | Held — renders a minimal-but-valid header, no crash |
| OCR-garbled document text (control characters, malformed content) | Held — treated as a plain string, no special parsing to break |
| Concurrent requests for 2 different cases | Held — no cross-contamination, each gets its own cap (`asyncio.gather`-based test) |
| Replay (identical call twice) | Held — identical capped output both times |
| Process-restart / determinism | Held by construction — no module-level mutable state was introduced (`_CAP_BY_READINESS` is a read-only constant); inherits `shared/case_context.py`'s own pre-existing no-cache, no-randomness guarantee |
| 1000 documents / 300 deadlines / 50 contradictions | **Not re-tested this sprint** — already proven at the `build_case_context()` layer itself (`tests/test_tau002_case_context.py::test_select_documents_{500,1000}_scale_every_document_accounted_for`, `tests/test_tau004_extreme_scale.py::test_300_deadlines_not_silently_dropped` / `test_50_contradictions_not_silently_capped`). `hearing_cc.py`'s own migration adds no NEW document/deadline/contradiction handling logic of its own — it calls the same canonical function these tests already certify, so re-running them here would test `build_case_context()` a 2nd time, not this sprint's own change. |

**Verdict: the pattern survived every attack directed at code this sprint actually wrote.** The scale
guarantees are correctly inherited, not re-proven redundantly.

## Phase 7 — Factory validation: 3 modules simulated, none migrated

Per the mission's own explicit instruction ("Nemoj ih migrirati. Samo simuliraj migraciju."), 3 further
modules were read and the Factory template applied on paper — no code changed for any of them.

### `routers/case_commander.py`

**A genuinely different migration shape than `hearing_cc.py`'s own "add missing context" case.**
`_kanonski_nalazi()` already independently calls `services/risk_engine.py::calculate_procesni_rizik`/
`identify_case_problems`, `shared/gap_engine.py::collect_case_gaps`, and
`shared/case_readiness.py::compute_case_readiness` — the exact same functions `build_case_context()` calls
internally — against its own separately-fetched data set, to re-derive readiness/gaps from scratch. This
means a real migration here wouldn't just ADD fields, it would **replace a duplicate computation with the
canonical one's already-computed output**, eliminating a genuine drift risk (2 independent fetches of
conceptually the same rows could silently diverge if one query changes and the other doesn't). Step 3 mode:
lightweight (the 2 GPT-advisory fields — `protivnikova_strategija`/`sudska_praksa` — need no document
excerpts). Step 4 boundary: already satisfied at a stronger level than most modules — Sigma 005's own GPT
Boundary Policy already restricts GPT to exactly those 2 fields, everything else deterministic; migrating
context wouldn't need a NEW boundary, just sourcing the existing one from the canonical computation instead
of a parallel one. Step 5: the `rokovi` table (a 4th independent corroboration of the rokovi/rocista split
`TAU-013` already named, after `decision_replay.py`, `digital_twin.py`, `zadaci.py` below) has no canonical
equivalent — would stay bespoke.

**This finding changed the Factory template itself** — see `MIGRATION_TEMPLATE.md`'s new Step 0 checklist
item on checking for duplicate computation, not just duplicate fetch, added directly as a result of this
simulation.

### `routers/digital_twin.py`

A clean, simple case — closer in shape to `hearing_cc.py`'s own "add context to a prompt" category than
`case_commander.py`'s duplicate-computation category. `_dohvati_kontekst_predmeta` fetches `predmeti`
(narrow projection), `rokovi` (not `rocista` — a 3rd independent rokovi/rocista corroboration),
`predmet_dokumenti` (filenames only), `predmet_komentari`. Step 3 mode: lightweight (a "what-if" hypothesis
simulation doesn't need raw document excerpts). Step 4 boundary: `nova_verovatnoca_uspeha` (a 0-100
post-hypothesis success probability) is structurally identical to Court Predictor's win-probability and
`hearing_cc.py`'s `hearing_score` — a 3rd confirmed candidate for the exact same deterministic-cap
mechanism, strong evidence this specific boundary shape (cap a GPT-claimed percentage against canonical
readiness) generalizes across the platform, not just within one file's own endpoints.

### `routers/zadaci.py::ai_analiziraj_predmet`

A "near-miss" case: this endpoint's own code comment (dated 2026-08-03, Project Nexus) already documents
that it was deliberately grounded in `calculate_procesni_rizik`/`identify_case_problems` directly — the
SAME duplicate-computation shape `case_commander.py` has, but already partially self-aware of the problem
its own comment describes solving. Migrating this module would mostly be "swap the source of an already-
correct pattern" (call `build_case_context()` and read its `missing_evidence`/`contradictions` instead of
calling `identify_case_problems` a 2nd, independent time) rather than fixing an active grounding gap — lower
urgency than `case_commander.py`, but same mechanical elimination-of-duplication value. Genuinely NOT
case-context concerns, correctly kept bespoke: `billing_entries` (unbilled-amount detection) and `zadaci`
(task-staleness) — neither maps to anything in the canonical contract, nor should it.

### Template changes made as a direct result of this phase

One: the Step 0 "check for duplicate computation" addition to `MIGRATION_TEMPLATE.md`, described above.
No other template change was needed — Steps 1-7 as written accommodated all 3 simulated shapes (context-
injection, duplicate-computation-elimination, and the hybrid near-miss) without further adjustment.

## Phase 8 — Immediate fixes

The only immediately-fixable, non-architectural issue found and applied this sprint: `hearing_cc.py`'s own
dead `predmet_komentari` fetch (queried, never rendered) — removed as part of the Phase 4 migration itself
(see `docs/tau/HEARING_CC_MIGRATION_REPORT.md`). No other safe, non-architectural fix was surfaced by
Phase 1's census or Phase 7's simulations that fell within this sprint's own scope — Phase 7's 3 modules
were explicitly not to be migrated, and the census's own newly-found items (`api.py`'s 2 undocumented
bespoke endpoints, `drafting/router.py`'s missing `predmet_id` parameter, etc.) are migration-scale findings
for a future sprint, not immediate fixes.

**One test-infrastructure fragility found and worked around, not fixed globally**: `tests/test_hearing_cc.py`'s
own pre-existing `_make_supa()` helper picks which mocked table-row to return via a global call counter
("the 1st `execute()` call gets the case row") — reliable for a single isolated request, but genuinely
order-fragile under `asyncio.to_thread`'s real thread scheduling when 2 requests share one mock back-to-back
(confirmed by direct reproduction: a replay test using this helper twice flaked once, passed in isolation).
Worked around in this sprint's own new replay test via a deterministic, `.eq("id", ...)`-keyed mock instead
(`_make_multi_supa`, also used for the concurrency test). Not fixed platform-wide — `_make_supa()` still
works correctly for every pre-existing single-call test that uses it; rewriting a widely-reused test helper
is out of this sprint's own scope.

## Phase 9 — Regression certification

Full suite result: see `docs/tau/TAU_006_REPORT.md` for the exact before/after count. `hearing_cc.py`-scoped
suite: 53 passed (34 pre-existing, updated for the new `_load_all_context`/`_build_prompt` shapes, 0
loosened; 19 new — migration, adversarial, concurrency, replay), stable across 5 consecutive runs.
Concurrency, replay, and adversarial ("hallucination" — the poisoned-GPT-response cap-override test) cases
are all covered above. Stress (extreme scale) is inherited from the canonical layer's own already-proven
tests, not redundantly re-run.

## Overall Factory verdict

The Canonical Context Migration Pattern (`CANONICAL_CONTEXT_FACTORY.md`) held across all 4 modules examined
this sprint in detail (1 migrated — `hearing_cc.py`; 3 simulated — `case_commander.py`, `digital_twin.py`,
`zadaci.py`), spanning 3 genuinely different shapes: pure context-injection (`hearing_cc.py`,
`digital_twin.py`), duplicate-computation-elimination (`case_commander.py`), and a near-miss hybrid
(`zadaci.py`). The pattern needed exactly one refinement (Step 0's duplicate-computation check), made
during this sprint, not deferred. This is enough evidence to proceed with `TAU_007_HANDOVER.md`'s own
proposal for a systematic rollout — the template is proven, not just asserted.
