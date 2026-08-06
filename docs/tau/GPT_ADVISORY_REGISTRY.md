# GPT Advisory Registry — Program Tau, Master Sprint 003

Every field across the platform that is legitimately `GPT Advisory` after this sprint's migration — no
canonical owner exists or is appropriate, and each is now either structurally tagged (`shared/commander_schema.py`
via Case Commander, `strategija.py::_advisory_provenance`) or documented here as an accepted, deliberate
exception. This is the "keep advisory reasoning only where appropriate" half of Phase 3 — a registry, not
a to-do list.

## Structurally tagged (response carries explicit `gpt_advisory`/`_ai_advisory` provenance)

| Field(s) | File | Tag mechanism |
|---|---|---|
| `protivnikova_strategija`, `sudska_praksa` | `case_commander.py` | `shared/commander_schema.py::gpt_advisory_field` (Sigma 005) |
| Portfolio-wide kontradikcije/nepovezani dokumenti | `case_commander.py::_cross_case_analiza` | Same |
| All 9 endpoint responses | `strategija.py` | `_advisory_provenance()` (this sprint, additive `_ai_advisory` key) |
| `relevantne_lekcije`, `komunikacioni_savet`, `potvrdjeni_obrasci` | `case_intelligence.py` | `_ai_provenance` sidecar (this sprint, additive) |
| `procena`, `prednosti`, `cilj` | `copilot.py` | Not yet wrapped in a response-level tag (see "Documented, not yet tagged" below) |

## Documented, not (yet) structurally tagged — accepted this sprint, named for a future pass

These fields have no live restructuring path this sprint (LIVE frontend consumers, per
`AI_DECISION_SURFACE_MAP.md`'s own live-caller correction) that would let a full `commander_schema.py`-style
wrap happen without also touching `index.html`/`vindex.js`. They ARE legitimately advisory (no canonical
competitor), just not machine-taggable without a coordinated frontend change — out of this sprint's own
scope (a UI change, not a decision-boundary fix).

| Field(s) | File | Why advisory | Why not tagged this sprint |
|---|---|---|---|
| `procena`, `prednosti` | `copilot.py::_handle_analiza_predmeta` | Narrative synthesis, no competing canonical decision | Live frontend reads these as plain values (`d.procena`, `d.prednosti[]`) |
| `cilj`, `faze[].koraci` (plan structure) | `copilot.py::_handle_plan_predmeta` | Generative planning — legitimate "drafting assistance" per `LEGAL_AI_BOUNDARY_POLICY.md` | Same |
| `relevantne_lekcije`/`potvrdjeni_obrasci`'s own reference-grounding | `case_intelligence.py` | Built from real fetched rows but not reference-validated against them (no `validate_dok_reference`-style check) | Flagged as a hallucination-risk gap, not fixed this sprint — see `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` |
| `faze[].koraci[].prioritet` | `copilot.py::_handle_plan_predmeta` | No `case_actions` equivalent for per-step plan priority | Named in `DECISION_OWNERSHIP_MATRIX.md`'s own "still GPT (unowned)" table — genuinely no redirect target exists |

## Chat-context, no fixed UI slot to compete with a canonical value

| Field(s) | File | Why |
|---|---|---|
| Intake agent recommendation ("Prihvatiti / odbiti / zatražiti više informacija") | `multi_agent.py` | Asked before any `predmet_id` exists in realistic use — no canonical owner possible by construction |
| Litigation agent risk assessment ("Nizak / Srednji / Visok") | `multi_agent.py` | Free text in an open chat; own prompt already bans a numeric percentage to avoid false precision |
| Router persona selection | `multi_agent.py::_pozovi_router_api` | A routing decision, not a business decision |

## Pre-existing, larger fragmentations (not this sprint's to fix, cross-referenced not re-litigated)

| Field(s) | File | Tracking |
|---|---|---|
| `procenat_min`/`procenat_max` (win probability) | `court_predictor.py` | `PROGBETA-001`, `docs/architecture/DECISION_REGISTRY.md`'s Fragmented table (5-way) |
| `OSPORAVA` contradiction edges | `evidence_graph.py` | `DECISION_CONSISTENCY_REPORT.md` (4-way, pre-existing) |
