# Forensic Gap Certification — Program Sigma, Master Sprint 003 (2026-08-06)

Phase 6 (Case Impact) and Phase 7 (Forensic Certification — assume the Gap Engine can't find gaps, try to
prove it) deliverable.

## Phase 6 — Case Impact: does a lawyer see what's missing, why, and what triggered it?

Every Gap record `shared/gap_engine.py` produces carries `zasto` (why the system thinks something's
missing) and `ocekivano`/`pronadjeno` (what triggered the suspicion) by construction — satisfying the
mission's own "šta nedostaje / zašto je važno / koji dokument ili činjenica je izazvala sumnju" requirement
at the RECORD level, for every gap this sprint's aggregation covers.

**Wiring into existing consumers, confirmed this sprint**:
- `case_actions` (Workspace/Dashboard's own canonical source) — `identify_case_problems`' own findings and
  Genome's own contradictions already flow into `case_actions` via `_compute_target_actions`'s existing
  Rules 2-5, now sharing ONE classifier with `shared/gap_engine.py` (see below) instead of two independent
  ones.
- `routers/copilot.py` — both `_handle_analiza_predmeta` and `_handle_plan_predmeta` now read Genome's own
  `nedostaje[]` via `shared/gap_engine.py` instead of independently re-deriving (this sprint's own headline
  fix).
- `routers/case_intelligence.py` (AI Briefing) — already correctly read `genome.get("nedostaje")` directly,
  unchanged, confirmed as the model both Copilot handlers now follow too.

**Not yet wired**: `shared/gap_engine.py::collect_case_gaps` (the full 3-source aggregation, including
`hipoteza`/`pouzdanost` fields) has no dedicated read endpoint of its own yet — today, each consumer reads
gap data through its OWN existing channel (case_actions, Genome directly), not through one unified
`GET /predmeti/{id}/gaps`-style endpoint. Building that endpoint is a real, valuable, but genuinely new
piece of API surface — recorded as `SIGMA-017`, low risk, mechanical, deferred only because this sprint's
own time budget prioritized closing the live "3 independent generators" bug over adding new read surface.

## Phase 7 — Forensic Certification: trying to break the Gap Engine

### Attempt 1: false-positive gaps?

`identify_case_problems`' own findings cannot be false positives by construction (deterministic comparison
against actual data). Genome's own `nedostaje[]`/`kontradikcije[]` CAN be — this is inherent to any
GPT-derived finding, correctly marked `hipoteza: True` by `shared/gap_engine.py`, never asserted as fact.
No NEW false-positive risk was introduced by this sprint's own aggregation — it re-labels, never
re-derives.

### Attempt 2: missed gaps?

Confirmed, not fixed: `DOCUMENT_EXPECTATION_ENGINE.md`'s own 4 worked examples (contract→annex,
appeal→filing proof, decision→delivery receipt, expert opinion→report) are ALL currently undetectable by
any mechanism, existing or new this sprint. This is Phase 3/4's own honestly-named gap, not fixed this
sprint (see those documents' own reasoning).

### Attempt 3: duplicates between gap sources?

**Confirmed, and fixed — the most significant Phase 7 finding, found in code THIS sprint itself wrote.**
`shared/gap_engine.py::gaps_from_case_problems` (built earlier this same sprint) independently re-derived
the exact same text-classification cascade `services/case_evolution.py::_compute_target_actions`'s own
Rule 2 already used — two independent if/elif chains over the identical `identify_case_problems()` output
strings. This is precisely the "no parallel algorithms" violation this program's own founding principle
exists to prevent, discovered by turning Phase 7's own forensic-certification lens on this sprint's OWN
new code, not just pre-existing code. **Fixed in the same sprint it was introduced**: extracted into
`shared/gap_engine.py::classify_case_problem`, now the ONE classifier both `gaps_from_case_problems` and
`case_evolution.py`'s own Rule 2 call — a pure refactor, zero behavior change, proven by re-running the full
pre-existing `case_actions` test suite unchanged (all pass) plus 2 new dedicated tests confirming both
consumers share the one function.

### Attempt 4: contradictions between gap sources?

Genome's own `nedostaje[]` (holistic) and `identify_case_problems`' own `nedostajuci_dokazi` (category-list-
based) could theoretically disagree about whether "evidence is missing" for the same case — this is not a
bug, it's 2 genuinely different questions ("what would help, holistically" vs. "does at least one document
of expected category X exist") answered by 2 deliberately-different mechanisms, already documented as
such in `GAP_ENGINE_REGISTRY.md`. `collect_case_gaps` surfaces both, does not force them into false
agreement — a lawyer seeing 2 gap records about "missing evidence" from 2 different angles is accurate
information, not duplication, as long as each is clearly attributed to its own `izvor`.

### Attempt 5: unstable results between 2 runs?

`identify_case_problems`' own findings are fully deterministic — stable by construction. Genome's own
`nedostaje[]`/`kontradikcije[]` are GPT-derived and NOT guaranteed stable run-to-run in their own PHRASING
— but, thanks to Program Sigma Sprint 002's own `contradiction_identity` fix, `kontradikcije`-sourced Gap
records now carry a STABLE `dedupe_key` across rephrasing (proven by this sprint's own
`test_gaps_from_contradictions_carries_stable_dedupe_key`). `nedostaje[]`-sourced Gap records do NOT yet
have an equivalent stable identity — the exact same class of instability Sprint 002 fixed for contradictions
still applies to Genome's own missing-evidence list. Named as `SIGMA-015` (already introduced in
`LEGAL_HYPOTHESIS_ENGINE.md`, reiterated here as a direct Phase 7 finding, not just a status-lifecycle
prerequisite).

## Certification verdict

Per the mission's own rule ("Sprint nije završen dok se svi popravljivi problemi ne uklone"): the one
CONCRETE, popravljiv problem this sprint's own forensic pass found — 3 independent "missing items"
generators, 2 of them inside `routers/copilot.py` — is fixed, tested, zero regressions. A second,
self-introduced duplication (the classifier cascade) was caught by applying the same certification standard
to this sprint's own new code and fixed in the same sprint, not left for a future one. What remains open
(`SIGMA-012` through `SIGMA-017`) all require either a deliberate founder-authorized architectural staging
decision already on record (`SIGMA-012`), new GPT-prompt-extension work needing live verification
(`SIGMA-013`), product-level false-positive-tolerance decisions (`SIGMA-014`), or schema decisions
following an already-proven pattern but not yet designed in full (`SIGMA-015`/`016`/`017`) — none judged
safe to implement blind within this sprint's own remaining time.
