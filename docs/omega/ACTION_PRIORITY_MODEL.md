# Action Priority Model — Program Omega, Sprint 003 (2026-08-06)

Phase 5's own required deliverable: the ONE priority computation, and why it is not, and cannot become, a GPT
judgment call.

## The 5 levels

`case_actions.prioritet ∈ {critical, high, medium, low, informational}` (migration 099's own CHECK constraint —
the DB itself refuses any other value, not just application-level discipline).

`low` is reserved in the schema but not currently produced by any of the 5 rules — no rule's own worked
example in the mission charter maps to it, and inventing a use for an unused level would be exactly the kind
of "designing for hypothetical future requirements" this whole engagement avoids. It exists so a future rule
doesn't need a migration to use it.

## How each rule assigns priority — every one traceable to a real number or a real classification, never a guess

| `tip` | Priority source | Rule |
|---|---|---|
| `PRIPREMITI_PODNESAK` | `_priority_by_days(dani_preostalo)` | `dani ≤ 3 → critical`, `dani ≤ 7 → high`, else `medium` (bounded to ≤30 days by Rule 1's own inclusion filter — a rociste further out never becomes a target action at all yet) |
| `PRIBAVITI_DOKAZ` ("Nema uploadovanih dokaza") | Fixed `critical` | Zero evidence on a case is always critical — not a computed value, a direct classification of `identify_case_problems()`'s own "kritican" `ozbiljnost` for this specific problem |
| `PRIBAVITI_DOKAZ` ("Nedostaje X u spisu") | Fixed `high` | Mirrors `identify_case_problems()`'s own "vazan" `ozbiljnost` for this problem class |
| `PLANIRATI_ROKOVE` | Fixed `high` | Mirrors `identify_case_problems()`'s own "vazan" `ozbiljnost` |
| `OJACATI_DOKAZE` | Fixed `informational` | Mirrors `identify_case_problems()`'s own "info" `ozbiljnost` |
| `RAZRESITI_KONTRADIKCIJU` | `{"kriticna": "critical", "vazna": "high", "manja": "medium"}.get(k["tezina"], "medium")` | Genome's own `tezina` classification on the contradiction object itself — not re-derived, read directly |

Two independent sources feed this table, both already-established, deterministic, sourced values:
`services/risk_engine.py::identify_case_problems()`'s own `ozbiljnost` field (Core Consolidation, 2026-07-22),
and Genome's own `case_dna.kontradikcije[].tezina` classification. `_priority_by_days` is the only NEW
computation this sprint adds, and it's a pure day-count comparison against `rocista.datum` — no judgment, no
model call.

## Why priority is NOT determined by GPT (the mission's own explicit Phase 5 constraint)

Every value above is either a fixed constant tied to an already-deterministic upstream classification, or a
3-branch day-count comparison. There is no prompt, no `chat.completions.create` call, no free-text
interpretation anywhere in `_compute_target_actions`'s own priority assignment. This mirrors AR-01
(`services/risk_engine.py`'s own docstring: "nijedan LLM izlaz ne sme biti jedini izvor poslovnog stanja") —
priority is business state, same category as risk level or deadline status, and inherits the same rule.

## Ordering — used by the Worklist (Phase 6), not stored on the row

`routers/case_actions.py::_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3,
"informational": 4}`, paired with `rok` (ascending, missing `rok` sorts last) as the tiebreak. This is a VIEW
concern — how to order a list for display — not a WRITE concern, so it lives in the read-only worklist router,
not in the Action Engine itself. Both `GET /api/case-actions/worklist` and `GET
/api/case-actions/predmeti/{predmet_id}` use the exact same `_sort_key`, so a case's actions are ordered
identically whether viewed as part of the cross-case worklist or the single-case view — one ordering, one
owner, matching Core Consolidation's own "1 koncept = 1 vlasnik = 1 algoritam = 1 istina" principle.

## What this model deliberately does not do

- Does not weigh "priority across cases" (e.g. is Case A's `high` more urgent than Case B's `high` because
  Case A is a bigger client) — every action's priority is computed purely from ITS OWN case's facts. Cross-case
  weighting would require a case-importance signal that does not exist anywhere in the platform today
  (deliberately not invented here, same discipline as `OMEGA-005`).
- Does not decay priority over time on its own (e.g. a `medium` rociste-deadline action does not silently
  become `high` as days pass without a refresh). It is recomputed correctly on the NEXT `refresh_case_actions`
  run for that case — which happens on every `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO`/
  `DOCUMENT_BATCH_COMPLETED` event for that case, but not on a bare clock tick. A case that receives no new
  events for weeks will show a stale priority until its next real event. No daily re-tick job exists yet —
  named as a gap for a future sprint (worklist correctness under case inactivity), not addressed here.
