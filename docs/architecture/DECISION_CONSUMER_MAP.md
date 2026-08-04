# Decision Consumer Map — Program Gamma (Masterprompt 003), Phase 6

For each canonical decision (`DECISION_REGISTRY.md`), who actually consumes
it today, and — for the 3 evidence-check decisions this mission newly
canonicalized (DC-009) — who was migrated onto it this session vs. who
remains an independent, unmigrated author.

## Already-canonical, multi-consumer (no migration needed — cite as reference)

| Decision | Consumers |
|---|---|
| DC-001 `calculate_procesni_rizik` | `ccc.py`, `dashboard.py::matter_health_score`, `matter_intel.py` (main endpoint), `zadaci.py::ai_analiziraj_predmet`, `case_pipeline.py` steps 7/8, `event_bus.py`'s `HEALTH_SCORE_PROMENJEN` |
| DC-002 `identify_case_problems` | `dashboard.py`, `zadaci.py::ai_analiziraj_predmet` (both the prompt-injection AND its own fallback path), `case_pipeline.py` step 8, `cio.py`'s reuse (partial — see gap below) |
| DC-013 `create_proactive_alert` | Every alert-producing module platform-wide (Program Alpha canonicalization — no known holdout) |

## Migrated THIS SESSION (Program Gamma, DC-009 — reference existence validators)

| Consumer | Before | After |
|---|---|---|
| `case_dna.py::compare_docs` | Already migrated (Program Beta) | Unchanged — the original reference implementation |
| `evidence_graph.py::generisi_graf` | Zero of 3 Evidence Chain links | `case_context()` provenance + `validate_graph_edge_references()` + `_evidence_check` in response, this mission |
| `case_commander.py::_cross_case_analiza` | Zero of 3 Evidence Chain links | `case_context()` provenance + `validate_predmet_reference()` on `nalazi[]`/`prioritet` + `_evidence_check`, this mission |

## Explicitly NOT migrated this session (documented, not silently skipped)

| Consumer | Why not this session |
|---|---|
| `case_commander.py`'s other 3 endpoints (`/analiza`, `/quick-check`, `/checklist`) | Zero provenance too, per the Genome/Evidence/Compare fork's finding — but each has a different output shape than `_cross_case_analiza`; wiring all 3 correctly needs its own pass, not a rushed copy-paste. `GAMMA-004`. |
| `matter_intel.py`'s Uncertainty Dashboard / Pre-Flight Check (2 endpoints) | Zero provenance, AND don't even import the canonical `calculate_procesni_rizik` they sit next to in the same file — this is a bigger fix than adding provenance (it's DC-001 migration, not DC-009). `GAMMA-003`. |
| `case_intelligence.py::case_intelligence_briefing` | Fixed the live 500 bug (schema mismatch) this session — provenance wrapping was NOT added, since the bug fix was already a meaningful, bounded, tested change; adding provenance too would have widened this session's single fix into two. `GAMMA-005`. |

## Decisions where "migration" means something harder than wiring — designed, not attempted

| Decision | Why migration ≠ wiring |
|---|---|
| "Next recommended action" (12+ producers) | There is no single canonical function yet to migrate consumers TO — this is a design/consolidation problem (`CANONICAL_DECISION_ENGINE.md` §Deferred), not a wiring problem like DC-009 was. Attempting a "migration" here would mean picking a winner among 12 competing product surfaces without a founder decision — explicitly out of scope per this mission's own prohibition on product-identity calls. |
| Litigation win-probability (5 generators) | Same shape — `PROGBETA-001`'s own conclusion (a shared scorer needs 2 new signals wired first) still holds; Case Pipeline step 5 adds a 6th caller to design for, not migrate. |
| Document classification (`ALPHA-003`) | The "correct" classifier already exists (`evidence.py`'s) — this isn't a missing canonical source, it's a reliability problem (unawaited fire-and-forget, silent failure). Migrating consumers wouldn't fix it; fixing the reliability shape would. Different kind of work, still deferred (`ALPHA-003`, unchanged). |
| Firm memory judge-favorability (`ALPHA-005`) | The canonical source is `firm_memory.py::kontekst_za_ai`, but wiring Copilot onto it is a genuine capability expansion (Copilot would start using real judge win/loss data it doesn't use today), not a pure refactor — explicitly gated on a founder go-ahead per Program Alpha's own original finding, unchanged by Gamma. |

## Consistency gap NOT closed by this mission's migrations (named, not hidden)

`routers/cio.py:148` aggregates Genome's raw-GPT `nedostaje.hitnost` into a portfolio-wide count — it does NOT consume DC-002's `identify_case_problems` output for the same signal, even though DC-002 is the canonical "what's missing" source and is available. This is exactly the shape of gap `DECISION_REGISTRY.md`'s registration rule is designed to prevent going forward — flagged here as an existing instance found during Phase 6 mapping, tracked as `GAMMA-002` (see `ARCHITECTURAL_DEBT_REGISTER.md`).
