# DEPRECATION_PLAN.md — Operation Singular Intelligence, Mission 001

Per the mission's Acceptance Criterion "Deprecated concepts are either removed or explicitly marked."
Nothing in this mission's scope warranted outright removal (every fragmented source found still
answers a question some lawyer-facing feature genuinely needs) — the plan below is entirely
"explicitly marked," not deletion.

## Marked this mission (implemented)

| Concept | What changed | Where |
|---|---|---|
| Genome hero panel's risk-framed strength label | "Visok rizik"/"Srednji rizik" → "Slaba pozicija"/"Srednja pozicija" (strength-framed, no risk vocabulary collision); threshold aligned 65→60 to match Copilot's already-correct framing of the same shared field | `static/vindex.js` (2 render sites) |
| Firm Health Index cache | Silent up-to-1h staleness → explicit `iz_kesa`/`generated_at` disclosure, "· keširano" UI indicator, matching `cio.py`'s own established pattern | `routers/health_index.py`, `static/vindex.js` |
| Chief Partner Directive | Undisclosed independent GPT recommendation → explicit "AI predlog, nezavisan od Workspace liste zadataka" disclosure | `static/vindex.js` |
| CIO "Preporuka za danas" | Same undisclosed pattern → same disclosure added | `static/vindex.js` |
| `dna.tip_spora` ghost field | Referenced a field that never existed → corrected to the real field (`pravna_teorija.pravni_identitet`) | `static/vindex.js` |
| Court Predictor's "Preporuke prihvaćeno/Odbijeno" | Always-0 numbers rendered as if real → hidden until `recommendation_log` could plausibly contain real data (currently: never, since its insert path is dead — see debt) | `static/vindex.js` |
| Genome refresh endpoint's response | Could claim success and show new data on a failed DB write → now honestly reports which genome is actually persisted, with an explicit `case_dna_persisted` flag | `routers/case_dna.py` |
| `routers/zadaci.py`'s risk-formula input | Missing soft-delete filter (silent divergence from every sibling caller) → aligned | `routers/zadaci.py` |
| `web3_compliance.py`'s 4 compliance scores | Unguarded GPT output, frontend risk-inversion fallback → server-side clamp/enum-guard added, fail-safe direction chosen per scale (risk scale → VISOK, goodness scale → NIZAK) | `web3_compliance.py` |

## Named as debt, not removed or renamed (see `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`, `SINGULAR-DEBT-001` through `-012`)

These require either a larger consolidation (risk of introducing a new regression if rushed), a
product/UX decision outside a mechanical fix's scope, or DB migrations the coordinator does not run.
Full citations in the debt register; summary:

- **`SINGULAR-DEBT-001`**: the "Recommendation" concept's 3-4 independent generators
  (`_step_copilot_preporuka`, `_handle_predlozi`, `zastarelost.py`'s thresholds, Case Commander vs.
  the AI Briefing panel's redundant twin design) — the mission's own headline deferred item, full
  architecture already specified in `DECISION_ARCHITECTURE.md`.
- **`SINGULAR-DEBT-002`**: `strategy_simulator.py`'s unguarded `rizik_score`/`verovatnoca` — dead
  code (zero frontend callers), same risk class as other confirmed-dead landmines.
- **`SINGULAR-DEBT-003`**: `recommendation_log`'s dead insert path (column-name mismatch,
  `tip`/`tekst` vs. the real `tip_preporuke`/`tekst_preporuke`) plus its own zero callers — the
  platform's entire recommendation-outcome learning loop has been non-functional since inception.
  Reactivating it is a feature-completion project, not a truth-fragmentation fix.
- **`SINGULAR-DEBT-004`**: `zastarelost.py`'s 2 different urgency-threshold ladders in the same
  file — a landmine (zero live callers today, not a live contradiction).
- **`SINGULAR-DEBT-005`**: `predmeti.oblast` vs. `oblast_prava` — a duplicate pair for the same fact,
  with `oblast_prava` having zero confirmed application-code writer (6 AI modules plausibly always
  reading an empty string).
- **`SINGULAR-DEBT-006`**: `predmeti.vrednost_spora` (manual) vs. `case_dna.finansije.*`
  (AI-extracted) — two unreconciled "money at stake" sources.
- **`SINGULAR-DEBT-007`**: `knowledge_profiles.ukupno_predmeta`/`win_rate` — same manual-override-
  silently-overwritten-by-AI pattern as the already-known `predmeti.rizik` case, on a table neither
  prior mission examined.
- **`SINGULAR-DEBT-008`**: `case_dna.py`'s refresh writes `predmet_hronologija` unconditionally
  before the `case_dna` UPDATE, with no rollback on failure — Fix 5 (this mission) stopped the
  response from LYING about the outcome, but the underlying cross-table atomicity gap (calendar can
  still show deadlines from a genome version that was never saved) is not closed.
- **`SINGULAR-DEBT-009`**: Confidence remains ~16 legitimately-distinct mechanisms, unified only by
  a guard CONTRACT (this mission's Truth Contract), not a shared formula — carried forward from
  Single Brain Mission 002's own `SINGLEBRAIN2-DEBT-004`, plus 1 new source found
  (`firm_memory.py::_apply_trust`).
- **`SINGULAR-DEBT-010`**: `predmeti.status`'s 5-way classifier fragmentation — unchanged, full spec
  in `docs/singlebrain/CASE_STATUS_CANONICAL_MODEL.md`.
- **`SINGULAR-DEBT-011`**: the readiness-tier cap still fails open when `build_case_context()`
  throws (`SINGLEBRAIN-DEBT-010`/`SINGLEBRAIN2-DEBT-005`) — carried forward unchanged for the third
  mission in a row, same reason: no safe default cap value without risking a different failure mode.
- **`SINGULAR-DEBT-012`**: `health_score` naming collision across 3 unrelated domains — naming trap,
  not a data bug, unchanged.

## Explicit non-goal

Per this mission's own Core Rule 3 ("DO NOT replace existing proven engines"), none of the above
DEFERRED items propose replacing `risk_engine.py`, `case_readiness.py`, `genome_validator.py`, or
`attention_priority.py` — every deferred item is either a consolidation of DUPLICATE next-action/
recommendation logic onto those already-canonical engines, or a disclosure/labeling fix, never a new
scoring formula.
