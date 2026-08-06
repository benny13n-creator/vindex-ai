# Canonical Action Engine — Program Omega, Sprint 003 (2026-08-06)

Phase 2 + Phase 3's own required deliverables: the ONE Action model, and the ONE engine that fills it.

## Where it lives, and why it's not a new orchestrator

The mission named the function `refresh_case_actions(case_id)`. It is implemented as
`services/case_evolution.py::_consequence_refresh_case_actions(event)` — a CONSEQUENCE, dispatched through the
SAME `handle_case_changed` loop every other Case Evolution consequence already goes through, not a standalone
function callable from anywhere. Same interpretation of "no new orchestrator" as
[`CASE_REFRESH_ENGINE_SPEC.md`](./CASE_REFRESH_ENGINE_SPEC.md) established in Sprint 002 — `case_id` arrives as
`event.predmet_id`, not as a direct function argument a caller can invoke out-of-band.

It is wired as the **LAST** consequence on every event that already touches case facts:

```python
CONSEQUENCE_REGISTRY = {
    EventType.DOCUMENT_ACCEPTED:         [genome_refresh, timeline_entry, refresh_case_actions],
    EventType.REVIEW_ACCEPTED:           [genome_refresh, timeline_entry, review_confirmation_audit, refresh_case_actions],
    EventType.ROCISTE_ZAKAZANO:          [genome_refresh, refresh_case_actions],
    EventType.DOCUMENT_BATCH_COMPLETED:  [genome_refresh, timeline_entry, case_intelligence_summary, refresh_case_actions],
}
```

Running last is load-bearing, not incidental: `handle_case_changed`'s own sequential per-consequence loop
guarantees `genome_refresh` (and, for batches, `case_intelligence_summary`) has already completed for this same
event before `refresh_case_actions` reads `predmeti.case_dna`/`risk_engine` output — so the Action Engine never
computes against a stale Genome.

`REVIEW_REJECTED`, `NEW_CLIENT_LINKED`, and `NEW_EVIDENCE_REGISTERED` deliberately do **not** get
`refresh_case_actions` this sprint — none of them currently changes anything `_compute_target_actions` reads
(`case_dna.kontradikcije`, `predmet_dokazi`, `predmet_dokumenti`, `rocista`). Wiring it to events that can't
possibly change the target set would be dead weight, not correctness. If a future sprint makes
`NEW_EVIDENCE_REGISTERED` write to `predmet_dokazi` directly (it currently doesn't — see
`ACTION_PRODUCER_REGISTRY.md`), that event should gain `refresh_case_actions` too.

## The canonical model — ONE table, `case_actions` (migration 099)

```
Action {
  id, predmet_id, tip, razlog, dokaz (JSONB), prioritet, rok, status,
  kreirao, correlation_id, confidence, izvor_dokumenti (JSONB),
  dedupe_key, event_id, created_at, updated_at, closed_at
}
```

Maps 1:1 onto the mission's own named fields (`ID, Type, Reason, Evidence, Priority, Due Date, Status, Created
By, Correlation ID, Audit Link, Confidence, Source Documents`) — `Audit Link` is `event_id` (FK to `events`)
plus the generic `case_evolution_consequence_completed` + domain-specific `case_action_refreshed` audit rows
every consequence already produces (nothing new invented for auditing). No module besides
`_consequence_refresh_case_actions` may write to `case_actions` — enforced by convention today (RLS is
service-role-only, same as every other Case Evolution-owned table), not yet by a DB trigger.

## The 5 action types (deterministic, NEVER GPT)

| `tip` | Produced by | Trigger |
|---|---|---|
| `PRIPREMITI_PODNESAK` | Rule 1 | A `rocista` row, `status='zakazano'`, due within 30 days |
| `PRIBAVITI_DOKAZ` | Rule 2 | `identify_case_problems()` reports "Nema uploadovanih dokaza" or "Nedostaje X u spisu" |
| `PLANIRATI_ROKOVE` | Rule 4 | `identify_case_problems()` reports "N predstojećih rokova... nije prioritizovano" (N≥3) |
| `OJACATI_DOKAZE` | Rule 5 | `identify_case_problems()` reports "Dokazi slabe snage" |
| `RAZRESITI_KONTRADIKCIJU` | Rule 3 | A `case_dna.kontradikcije` entry with a non-empty `opis` |

Every rule reads either a real DB row (`rocista`, `case_dna.kontradikcije` — the latter already required to
carry a `"DOK-XX str.Y"` source location by Genome's own extraction prompt, unchanged) or
`services/risk_engine.py`'s own canonical `calculate_procesni_rizik`/`identify_case_problems` (Core
Consolidation, 2026-07-22 — the ONE established algorithm for "what's wrong with this case", reused, never
duplicated a 4th time). No rule calls an LLM. `confidence` is always `1.0` — the column exists for schema
completeness / a future non-deterministic source, not because the current one ever returns anything else.

Rule 2's "kritičan rok" text is deliberately **skipped** — a rociste inside the 0–7 day window makes
`identify_case_problems()` ALSO emit its own generic "N kritičan rok(a)..." problem text; Rule 1 already
covers that exact fact with a more precise, per-rociste signal, so Rule 2 explicitly `continue`s past it to
avoid a duplicate, less-precise `PRIPREMITI_PODNESAK`.

### A deliberately-not-implemented example: "client not contacted in 45 days"

The mission's own third worked example. Grepped for `poslednji_kontakt`/`last_contact`/`zadnja_aktivnost`/
`poslednja_aktivnost` across `services/`, `routers/`, `shared/` — no genuine "last client contact" data source
exists anywhere in the platform (only `predmeti.updated_at`-adjacent proxies in unrelated modules —
`morning_briefing.py`, `sesije.py`, `wallet_provenance.py` — none of which represent client contact). Per
Agent 4's own "no conclusion without source" mandate, this rule is **not** approximated from a misleading
proxy — named honestly as `OMEGA-005` in the debt register instead of shipped half-grounded.

## Engine, step by step (`_compute_target_actions` → `_consequence_refresh_case_actions`)

1. **Compute the target set** (`_compute_target_actions`, pure, no DB writes) — reads `predmeti.case_dna/tip`,
   `predmet_dokazi`, `predmet_dokumenti` (now including `tip_dokaza`, see below), `rocista`; runs the 5 rules;
   returns a list of `{tip, razlog, dokaz, prioritet, rok, dedupe_key, izvor_dokumenti}` dicts — the FULL set of
   actions that SHOULD be open right now, for this case, given its current facts.
2. **Reconcile against what's already open** (`_consequence_refresh_case_actions`) — reads
   `case_actions WHERE predmet_id=... AND status='open'`, diffs by `dedupe_key`:
   - In target, not in existing → **INSERT** (`status='open'`).
   - In both → **UPDATE** in place (`razlog`/`dokaz`/`prioritet`/`rok`/`updated_at`) — a fact whose details
     changed (e.g. a deadline extended) updates the SAME action, it does not close one and open another.
   - In existing, not in target → **UPDATE** `status='closed', closed_at=now()` — the fact no longer holds.
3. **Audit** — `case_action_refreshed` (domain-specific, `metadata={created, updated, closed, open_total}`),
   plus the generic `case_evolution_consequence_completed` row every consequence gets.

## Why `dedupe_key` is keyed on the FACT, not the count or the row

`_stable_key(...)` hashes semantic identity — `("rociste", rociste_id)`, `("problem", "nema_dokaza")`,
`("problem", "nedostaje", full_text)`, `("kontradikcija", opis, lokacija_1, lokacija_2)` — never a row id from
`case_actions` itself and never a raw count. This is what makes Scenario 2 (evidence added → risk removed →
action closes, not just "count decremented") and Scenario 3 (deadline extended → SAME action updated, not
closed+reopened, so its `created_at`/history survives) both fall out of the SAME reconciliation loop with no
special-casing.

## Concurrency (Scenario 5) — the partial UNIQUE index is the real safety net, not application logic

`CREATE UNIQUE INDEX idx_case_actions_open_dedupe ON case_actions(predmet_id, dedupe_key) WHERE status='open'`
(migration 099). Two concurrent refreshes for the same case racing to CREATE the same fact's action both
attempt the same insert; the DB constraint — not a lock this code takes — guarantees exactly one open row per
fact survives. `_consequence_refresh_case_actions` catches the resulting `duplicate key`/`unique` exception and
treats it as "the other concurrent refresh already created this," logging and moving on — any OTHER insert
exception still propagates and fails the consequence for the Event Bus's own retry mechanism to pick up. This
is the exact same idiom this whole engagement has used repeatedly (`idempotency_key`, `content_sha256`,
`case_evolution_consequences`'s own upsert) — no new concurrency primitive invented.

## A correctness fix made in-scope: `predmet_dokumenti` now selects `tip_dokaza`

`_consequence_case_intelligence_summary` (Sprint 002) and `routers/matter_intel.py` (pre-existing, G-028) both
query `predmet_dokumenti` WITHOUT `tip_dokaza`, meaning `calculate_procesni_rizik()`'s own `nedostajuci_dokazi`
computation always sees an empty `postojeci_tipovi` set for those callers — every expected document type reads
as permanently missing, regardless of what's actually uploaded. That's a tolerable, already-known gap (G-028)
for a READ-ONLY display value. It is NOT tolerable for THIS engine: `_compute_target_actions` turns
"nedostajuci_dokazi" into a persisted, stateful `PRIBAVITI_DOKAZ` action that a lawyer is expected to trust and
act on — a permanent false positive on every single case would violate Agent 4's own grounding mandate for the
very rule meant to demonstrate it. Fixed by adding `tip_dokaza` to `_compute_target_actions`'s own
`predmet_dokumenti` select (`services/case_evolution.py`, `_compute_target_actions`) — scoped to this one new
caller, does not touch `matter_intel.py`'s or `_consequence_case_intelligence_summary`'s own existing (still
G-028-affected) queries. Logged as `OMEGA-006` in the debt register as a pointer for a future sprint to apply
the same fix to those two remaining callers.
