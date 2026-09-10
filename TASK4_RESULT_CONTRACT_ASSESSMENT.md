# TASK 4 — Structured case evolution result contract (assessment)

Mandate asks for a FACT / CONSEQUENCE / PROPOSED ACTION / DEADLINE distinction with provenance. Investigated by reading `services/case_evolution.py::_compute_target_actions` (L845-1058, the pure/deterministic function that produces every `case_actions` row) in full, plus live samples already captured in Task 0/2/3.

## What already exists (PROVEN, live samples from Task 0/2/3)

Every `case_actions` row already carries a real, structured contract:

| Field | Role | Example (live) |
|---|---|---|
| `tip` | PROPOSED ACTION (enum-shaped: `PRIBAVITI_DOKAZ`, `PLANIRATI_ROKOVE`, `OJACATI_DOKAZE`, `RAZRESITI_KONTRADIKCIJU`, `PRIPREMITI_PODNESAK`) | `"PRIBAVITI_DOKAZ"` |
| `razlog` | CONSEQUENCE, human-readable ("why this action exists") | `"Nedostaje pisanu komunikaciju u spisu"` |
| `dokaz` | provenance payload, shape varies per rule | `{"izvor":"identify_case_problems","problem":"..."}` |
| `rok` | DEADLINE, when the rule has one | populated for `PRIPREMITI_PODNESAK` (sourced from `rocista.datum`, never GPT-guessed — L883-920); `null` for the other 4 action types |
| `dedupe_key` | stable identity across refreshes (per-category or per-entity hash, not per-count — L922-924) | `"4d04b471b0522f7c2b01bed1"` |
| `confidence` | numeric confidence | `1.0` (deterministic rules currently always emit 1.0 — no rule in `_compute_target_actions` computes anything else) |
| `correlation_id` | **event-level provenance** — links the row back to the specific `events` outbox row that produced/last-touched it | live-matched exactly between an event and its resulting action in Task 0 §B and Task 2 |
| `izvor_dokumenti` | **fact-level provenance** (which underlying document/location caused this) | populated ONLY for `RAZRESITI_KONTRADIKCIJU` (Rule 3, L1046-1056, itself sourced from A002/A003's provenance work); **`[]` (empty) for the other 4 action types** in every live sample captured tonight |

FACT itself is deliberately NOT duplicated into the action row — it stays in `predmet_dokazi`/`predmet_dokumenti`/`rocista`, referenced by id where such an id exists (`rociste_id`, `dokument_id_1/2`). This is a defensible design (single source of truth for the fact, per this repo's own "1 koncept = 1 vlasnik" principle already established elsewhere) rather than a gap.

## Confirmed gap (live-observed, not hypothetical)

**Fact-level provenance (`izvor_dokumenti`) is populated for exactly 1 of 5 action types.** For `PRIBAVITI_DOKAZ`/`PLANIRATI_ROKOVE`/`OJACATI_DOKAZE` (Rule 2, sourced from `identify_case_problems`/`calculate_procesni_rizik`), the `dokaz` payload carries only a category-level `problem` string, never a specific document/fact id. In both live `case_actions` rows captured in Task 2/3, `izvor_dokumenti` is `[]`.

This is a real traceability gap for a lawyer asking "which fact/document is this action about, specifically?" for 4 of 5 action types — but **it may not be a bug so much as an honest reflection of the underlying rule's own nature**: `identify_case_problems`/`calculate_procesni_rizik` are case-level aggregate risk computations (e.g. "case has no written-communication evidence at all"), not computations over one specific fact, so there may genuinely be no single fact id to attribute. Confirming whether this is fixable (attribute to "the set of facts considered," if any) vs. inherent to the rule's own math needs its own dedicated investigation into `services/risk_engine.py::identify_case_problems`, not attempted in this pass to avoid a redesign without adversarial review — same rigor standard already required of every other change tonight.

## Recommendation (documented, not implemented this pass)

Do not redesign the schema. The existing contract already satisfies the mandate's ask at the "one action, one correlation_id, one dedupe_key, one confidence" level, and does so live-proven. The one real, disclosed gap (fact-level provenance for 4/5 action types) is a scoped follow-up: read `risk_engine.py::identify_case_problems`, determine whether a specific `predmet_dokazi`/`predmet_dokumenti` id set can be honestly attributed per problem type, and only then decide whether to populate `izvor_dokumenti` for those rules too. Attempting that blind, at the tail of a long sprint, without live A/B verification would risk exactly the kind of "confident but wrong redesign" this project's own engineering-rigor rule exists to prevent.

## TASK 4 GATE DECISION

**PASS WITH DISCLOSED GAP.** Core contract (action/reason/deadline/dedupe/confidence/event-provenance) exists and is live-proven. Fact-level provenance is real but partial (1/5 action types); documented, not silently claimed complete, not blindly "fixed."
