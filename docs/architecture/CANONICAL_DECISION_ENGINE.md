# Canonical Decision Engine — Program Gamma (Masterprompt 003)

**Eliminate Entire Classes of Decision Fragmentation.** Executive summary
and entry point for the 7 companion documents this mission produced.

## Governing principle

> Platforma sme imati više UI ekrana, više AI agenata, više workflow-a, više
> API-ja. Ali sme imati samo jednu odluku za isti skup činjenica. Ako ista
> činjenica može proizvesti različit rezultat u različitim modulima,
> arhitektura nije završena.

This mission is not about making Strategy Engine, Copilot, or Briefing
better. It is successful only when it becomes structurally impossible for
two different modules to reach different conclusions from the same facts
without the system noticing — not fully achieved this session (the scale
found makes that a multi-mission effort), but the detection mechanism now
exists where it didn't before, and the mission's own scale of finding is
itself the evidence for why this charter was needed.

## What this mission found (see `DECISION_GRAPH.md`, `DECISION_CONSISTENCY_REPORT.md`)

5 parallel domain investigations, explicitly built to extend — not repeat —
Program Alpha's structural-duplication lens and Program Beta's AI-reasoning-
defect lens, inventoried every business/legal decision platform-wide. The
result is the largest single finding of this entire multi-mission session:

**"Sledeći preporučeni korak" (next recommended action) has no single owner
anywhere in the platform — 18 independent, unreconciled producers**
(full enumeration: `ARCHITECTURAL_DEBT_REGISTER.md`'s `GAMMA-001`), spanning
Case Genome, Strategy Engine (3 internal generators), Court Predictor
(4 endpoints), Copilot (3 intents), Case Commander (3 endpoints), Case
Intelligence, and Case Pipeline's step 5 — none of which read any of the
others' output. This is not a new problem this mission invented — it
extends a founder-documented, already-open architectural question
(`G030_NEXT_ACTION_DECISION_MODEL.md`, 2026-07-22, which named 3 competing
authorities and left the decision unresolved) with 16 more producers G-030's
own investigation never examined (because it predates several of the
features involved), while also confirming one of G-030's original 3
authorities (Matter Intel) has since been resolved by an intervening
mission (Project Synapse, 2026-08-03) — not still open.

Close behind: litigation win-probability (5 generators, extending Program
Beta's own PROGBETA-001 finding), document/case readiness (2 structurally
incompatible mechanisms — a calibrated float vs. an ungrounded categorical
LLM self-report), and "contradiction between evidence" (4 generators,
a decision type neither Program Alpha nor Program Beta inventoried at all).

## What was implemented this mission (bounded, safe, fully tested)

1. **Fixed a live production bug**: `case_intelligence.py`'s "next step"
   endpoint was almost certainly 500ing on every call (wrong `proactive_
   alerts` column names, the same mistake class already fixed once
   elsewhere in this repo) — reachable from a UI button since 2026-08-03.
2. **Widened the proven Evidence Chain pattern to 2 more AI-decision
   endpoints** (`evidence_graph.py`, `case_commander.py`'s daily briefing)
   using a newly-generalized `shared/genome_validator.py` function family
   — the same "referenced entity must exist in scope" principle, proven a
   3rd and 4th time across 3 different ID schemes (DOK-XX numbers, graph
   node ids, predmet-ID prefixes).
3. **Closed 2 "should have been impossible" gaps**: Strategy Engine's
   `detektovani_konflikti` field was left LLM-decided in the exact same
   function where its sibling field (`sistemsko_upozorenje`) was fixed to
   be code-computed by Program Beta hours earlier the same day; Court
   Predictor's `boja`/`pouzdanost_profila` fields were raw LLM output
   despite each prompt stating a checkable derivation rule.
4. **Deduplicated a genuine "two authors, one edit from divergence" risk**:
   Case Genome's alert-urgency formula, byte-identical at 2 call sites.

All 5 shipped with new/extended tests (38 new tests across 6 files, including
the governance-driven hardening in Phase 10 below: `test_
case_intelligence_briefing_alerts_fix.py`, `test_gamma_evidence_check_
wiring.py`, `test_court_predictor_deterministic_derived_fields.py`,
`test_decision_registry_completeness.py`, plus extensions to
`test_genome_validator.py` and `test_strategija_sistemsko_upozorenje.py`), full suite
green after every change.

## The Decision Registry — the mission's headline deliverable

`DECISION_REGISTRY.md` formalizes, for the first time, a pattern this
codebase has organically re-invented 4 times since 2026-07-18
(`compute_snaga_score` → Court Predictor's confidence fix → this mission's
`_delta_hitnost`/DC-009 family/DC-011/DC-012): **compute the decision once,
in code, from already-available signals; let every consumer read the same
answer.** 13 canonical decisions are now catalogued with full contracts
(`DECISION_CONTRACTS.md`); every known fragmented decision is catalogued
alongside them, not hidden. The registration rule (check the registry
before writing new decision logic) is the practical, honestly-scoped answer
to the founder's own closing directive — 3 questions, restated as this
platform's standing check for any future feature:

> Da li uvodi novu poslovnu odluku? Ako uvodi, da li ta odluka već postoji u
> Decision Registry-ju? Ako ne postoji, da li zaista treba da bude nova
> odluka ili je samo drugačiji prikaz postojeće?

## Design sketch for the fragmented decisions — NOT implemented, a starting shape not a full spec

**Olympus Faza 10 governance nalaz (2026-08-04, Chief Systems Architect)**:
an earlier draft of this section called the sketch below "fully specified."
It is not — it names the target shape and the proven pattern to build it
on, but does not work through how each of the 18 producers' genuinely
different OUTPUT SHAPES map onto it (Copilot's PLAN intent returns a
multi-step task list; Court Predictor's 4 endpoints each return a
domain-specific structured payload — `battle-report`'s prose section is not
`judge-profile`'s `strateska_preporuka` field; Case Pipeline's step 5 writes
directly to a `predmet_istorija` row, not an API response). A genuine
complete spec would show at least one concrete per-producer adapter, not
just the target dict shape — corrected here rather than left overclaiming.

The founder's own charter forbids treating "next recommended action"'s
18-producer fragmentation as something to patch locally. The correct
target, grounded in the one pattern already proven to work at this exact
shape (`risk_engine.py`, consumed cleanly by 6+ modules with zero
divergence for years):

```
shared/recommendation_engine.py (NOT built — designed here)
  │
  ├── compute_next_action(predmet_id, supa) -> {
  │       "akcija": str,               # the single recommended next step
  │       "prioritet": "kritican"|"vazan"|"koristan",   # ONE vocabulary
  │       "izvor_signali": [...],      # which deterministic findings drove it
  │       "objasnjenje": str,          # why, in terms of izvor_signali
  │   }
  │
  ├── Tier 1 (deterministic, no LLM): reuse identify_case_problems (DC-002)
  │   as the FACT layer -- this already works, already has 1 clean consumer
  │   (Task Engine) proving the pattern.
  │
  ├── Tier 2 (LLM reasons over Tier 1's facts, does not re-derive them):
  │   ONE prompt, injected with Tier 1's findings + an explicit "do not
  │   contradict these" instruction -- the exact shape ai_analiziraj_predmet
  │   (zadaci.py) already proves works, generalized to be the platform's
  │   single recommendation voice instead of Task Engine's private one.
  │
  └── Every current producer (Genome's strategija/nedostaje, Strategy
      Engine's strateski_stav, Court Predictor's 4 advisory endpoints,
      Copilot's PLAN/PREDLOZI/brza_procena_koraci, Case Commander's 3
      endpoints, Case Intelligence, Case Pipeline step 5) becomes a
      CONSUMER of compute_next_action's output, formatted for its own UI
      surface -- not a re-deriver.
```

**Why not built this mission**: this is a genuine product-identity decision
(G-030's own framing: "dashboard with several AI opinions" vs. "one command
center"), gated on a founder call about which of the 18 existing surfaces
survive as distinct UI presentations of ONE answer vs. which get retired
entirely — not a technical decision this mission is chartered to make
unilaterally. The design above exists so that whenever that founder
decision is made, implementation can start from a proven pattern and a
named list of per-producer adapter work, not from a blank page — but the
adapter work itself (18 of them) is real, unestimated effort, not a detail.

## Phase 10 — Olympus governance verdict

10 fresh, independent agents (the founder's own 10 named roles: Chief
Systems Architect, Decision Consistency Auditor, Architecture Review, AI
Governance, Evidence Integrity, Security, Reliability, Workflow Integrity,
Legal Domain Expert, Metrics Guardian) reviewed the implementation. **No
BLOCKED verdicts.** 1 clean PASS (Reliability, no crash bugs found), 1
clean APPROVED (Decision Consistency Auditor, all 3 "now consistent" claims
verified end-to-end), 8 APPROVED WITH CONDITIONS.

**Strongest convergence signal (3 independent reviewers, automatically
Critical per the mission's own rule)**: Workflow Integrity, AI Governance,
and Legal Domain Expert all independently flagged the same defect from
different angles — the Synthesis prompt still named the exact 2 conflict
examples the new code now hard-codes, and one of the 2 hardcoded checks
risked firing on legally coherent, non-contradictory scenarios. Fixed: the
prompt was updated (mirroring Program Beta's own precedent for the sibling
field), the wording softened from assertive to hedged, and the
litigation-vs-transactional category-error gap closed with an explicit
scope guard.

**Second-strongest convergence (2 reviewers)**: Evidence Integrity and
Security both independently found `_evidence_check` was computed but never
read by the frontend for the 2 new call sites — fixed (toast + inline
marker + persisted-reload fix). Architecture Review and Security both
flagged process/idiom inconsistencies in `case_intelligence.py`'s new
code — fixed (ownership check moved out of the fail-soft gather; a third
gather-failure idiom replaced with the existing shared helper).

**Individual findings, all fixed same pass**: Evidence Integrity's
attribution-check gap (`validate_predmet_reference` checked existence, not
misattribution) closed with a real-naziv cross-check. AI Governance's
`boja` numeric-string coercion gap closed. Architecture Review's missing
`_sentry_capture()` calls added to both new evidence-check exception
handlers. Metrics Guardian's inconsistent "12+" producer-count arithmetic
across 3 documents reconciled to one methodology-transparent number (18,
full enumeration in `ARCHITECTURAL_DEBT_REGISTER.md`'s `GAMMA-001`).
Chief Systems Architect's 2 findings (a missing debt entry for
`genome_validator.py`'s scope drift; the design sketch overclaiming "fully
specified") both corrected.

No systemic problem was left unaddressed silently — every finding above
was either fixed in this same pass (the large majority) or logged as an
explicit, reasoned `GAMMA-00X` deferral (Case Commander's `poznati`/
`predmeti_txt` invariant note from Decision Consistency Auditor — no live
bug, a maintainability note for a future second caller).

## Success metrics (per the mission's own mandate — not commit/line counts)

| Metric | Count |
|---|---|
| Eliminated parallel decisions | 4 — `case_intelligence.py`'s broken endpoint (restored to 1 working decision from 0 working ones), Strategy Engine's `detektovani_konflikti` (2 structural conflicts now guaranteed-caught vs. 0), Court Predictor's `boja`/`pouzdanost_profila` (2 fields, raw→derived), Genome's alert-urgency (2 authors→1) |
| Migrated consumers | 2 — `evidence_graph.py::generisi_graf`, `case_commander.py::_cross_case_analiza`, onto the DC-009 evidence-check family |
| Canonical decisions now formally registered | 13 (`DECISION_REGISTRY.md`) — not newly built, formally catalogued for the first time |
| Decision Contracts written | 13 (`DECISION_CONTRACTS.md`) |
| Decisions with a provable Evidence Chain | +2 this mission (Evidence Graph, Case Commander's cross-case findings) — 4 of 13 canonical decisions now have one (DC-003/007/008/009) |
| Decisions with Audit + Provenance | +2 this mission (same 2 endpoints) |
| AI decisions moved to a deterministic layer | 4 — the same 4 counted under "eliminated parallel decisions," reframed: each moved a previously-raw-LLM categorical field to code-derived |
| Architectural rules preventing future bypass | 2 — `DECISION_REGISTRY.md`'s registration rule (process) + `tests/test_decision_registry_completeness.py` (mechanical drift detector) — explicitly NOT claiming a CI/static-analysis gate that does not exist (`DECISION_HARDENING_REPORT.md`) |

**Explicitly not claimed**: this mission did not eliminate the 18-producer
"next action" fragmentation, the 5-producer win-probability fragmentation,
or the document-readiness/classification-taxonomy problems — each is fully
diagnosed, prioritized, and either designed (next-action) or explicitly
gated on a founder/reliability decision (the rest), per
`ARCHITECTURAL_DEBT_REGISTER.md`'s new Program Gamma section.

## Reading order for the other 7 documents

`DECISION_REGISTRY.md` (Phase 1, the catalog) → `DECISION_GRAPH.md` (Phase
2, source-vs-consumer map) → `DECISION_CONTRACTS.md` (Phase 5, the 13
formal contracts) → `DECISION_CONSUMER_MAP.md` (Phase 6, who was migrated)
→ `DECISION_CONSISTENCY_REPORT.md` (Phase 7, the mission's own pass/fail
test, answered honestly) → `DECISION_MIGRATION_REPORT.md` (Phase 6, the
concrete before/after for every code change) → `DECISION_HARDENING_REPORT.md`
(Phase 8-9, future-failure analysis and the honest limits of the guardrail
built).
