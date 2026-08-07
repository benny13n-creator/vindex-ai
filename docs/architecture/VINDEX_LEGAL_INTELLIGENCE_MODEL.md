# VINDEX LEGAL INTELLIGENCE MODEL v1.0

*Operation One Truth, Agent 5 (Product Architect) deliverable — 2026-08-07. Conceptual/architectural
definition only; no code was changed to produce this document.*

## What is Vindex AI's mental model of a legal case?

Grounded in `shared/case_context.py`, `services/risk_engine.py`, `shared/gap_engine.py`,
`shared/case_readiness.py`, `services/case_evolution.py`, `migrations/099_case_actions.sql`,
`routers/case_dna.py`, and the precedent set by `docs/architecture/VINDEX_CORE_CONSOLIDATION.md`
(2026-07-22, "Core Consolidation").

---

### 0. The one-sentence model

**A legal case is a growing body of Facts, tested by Evidence, scored into Risks, exposing Gaps, bound by
Obligations, driving Actions, resolved into a Strategy — and every screen in Vindex is a way of looking at
some slice of those seven things, never a new eighth thing.**

This document names the seven CORE ENTITIES, states who canonically owns each one today, flags who is
currently (or historically) reinventing it, and gives the governing rule + a test for future features.

---

## 1. Facts (Činjenice)

**Definition:** Facts are what the case *is about* — the parties, the legal theory, the narrative, the
strengths and weaknesses a lawyer would explain to a colleague in two minutes.

**Canonical owner today:** `predmeti.case_dna` (the Genome), extracted and written exclusively by
`routers/case_dna.py`. This is Core Consolidation §1.3's own declared owner — "sole source of truth about a
case's facts, theory, evidence, and strength" — and it is real: `shared/case_context.py::build_case_context()`
reads `case_dna.pravna_teorija`, `case_dna.snaga_predmeta_procent`, `case_dna.najslabija_tacka` directly,
with zero re-derivation.

**Must not be reinvented by:**
- `services/case_pipeline.py`'s mini-strategy/risk-snapshot steps — Core Consolidation §1.3 flags these as
  still not writing their findings back into Genome (open item, not closed).
- Anything that narrates a case's "story" via a fresh GPT call without reading `case_dna` first (e.g.
  `routers/strategija.py`'s modules, `routers/court_predictor.py`, `routers/digital_twin.py`) is at risk of
  producing a *second, silently divergent* factual narrative unless it is explicitly seeded from Genome via
  `build_case_context()`. Not all of these currently do this correctly — verify per-module.

---

## 2. Evidence (Dokazi)

**Definition:** Evidence is what supports (or undermines) a Fact, with a strength label and a traceable
source document.

**Canonical owner today:** `predmet_dokazi` (table), surfaced through
`shared/case_context.py::_group_dokazi()` as `evidence_graph`, populated by Evidence Vault
(`routers/evidence.py`).

**Tension already named, not fully resolved:** Core Consolidation §1.3 itself documents that Evidence
Vault's `predmet_dokazi` and Genome's own evidence-related fields (`najslabija_tacka`, ranked evidence, heat
map) were historically **two parallel representations of "what is the evidence."** The partial fix shipped
(`_extract_genome` now takes classified Evidence Vault facts as *prompt context*) — but this is Genome
*reading* evidence, not evidence and Genome sharing one row-level model. Any future feature that
independently classifies or scores evidence strength outside `predmet_dokazi.snaga` is reinventing this
entity.

**Must not be reinvented by:** any module computing its own "how strong is this evidence" label instead of
reading `predmet_dokazi.snaga`/`kategorija`.

---

## 3. Risks (Rizici)

**Definition:** Risk is a deterministic score of the case's current exposure/danger, computed from Facts +
Evidence + Obligations — never guessed.

**Canonical owner today:** `services/risk_engine.py::calculate_procesni_rizik()`. This is the strongest,
most explicitly proven entity in the whole codebase — its own docstring cites empirical proof
(`scripts/g027_risk_validation.py`) that two independent implementations (`matter_intel.py`, Cockpit)
previously computed different numbers for the same case, and it is now AR-01's flagship example: "no LLM
output may be the sole source of a business risk state."

**Confirmed current violator:** `routers/court_predictor.py` — its GPT prompt (lines ~68-85) directly
generates `procenat_min`/`procenat_max` ("šansa za uspeh") as a **freeform GPT probability estimate**, with
no call anywhere in that file into `risk_engine.py`. This is a live, second, ungrounded "how is this case
going to go" number sitting alongside the canonical `rizik_score`/`health_score`. It is architecturally the
same category of violation Core Consolidation already fixed once for Cockpit's `sledeca_akcija` and Case
Ready Score's `copilot_preporuka`.

**Likely violator, needs verification:** `routers/digital_twin.py`'s `/api/twin/simulacija` — 3
GPT-generated scenarios "with percentages" (per its own docstring) is the same shape of claim (an outcome
probability) unless it is explicitly anchored to `calculate_procesni_rizik()`'s output rather than generated
independently.

**Rule:** any percentage, score, or label answering "how risky/strong/likely-to-win is this case" that
isn't `risk_engine.py`'s output (or a narration of it) is a violation, full stop — this was already
litigated and decided platform-wide in Core Consolidation §1.1/§3 ("AI never decides, evaluates, calculates,
ranks, or classifies anything for which a deterministic algorithm exists").

---

## 4. Gaps (Rupe / Nedostaci)

**Definition:** A Gap is a specific, named thing that *should* exist in the case file but doesn't — a
missing document, an unresolved contradiction, an unmet evidentiary expectation.

**Canonical owner today:** `shared/gap_engine.py::collect_case_gaps()`. Notably this is already built
correctly as an aggregator, not a detector — it normalizes three pre-existing sources
(`identify_case_problems()` deterministic findings, `case_dna.nedostaje[]` GPT hypotheses,
`case_dna.kontradikcije[]`) into one shape, and it explicitly tags each Gap `hipoteza: True/False` so a
deterministic finding is never confused with a GPT guess. This is the model to imitate for every other
entity.

**Must not be reinvented by:** any module producing its own "missing X" list by re-deriving from raw
documents/evidence rather than calling `collect_case_gaps()`. The module's own docstring already names why
a 4th source was deliberately not invented — hold that line.

---

## 5. Obligations (Obaveze)

**Definition:** Obligations are the case's externally-imposed clock — hearing dates and procedural
deadlines that exist independent of what the lawyer wants to do.

**Canonical owner today:** split by design, not by accident, per Core Consolidation §1.5 — and this split
is a rare case where the "one table" instinct was correctly overruled:
- `rocista` (table) — scheduled hearings, feeds `risk_engine.py`'s
  `kriticni_rokovi`/`predstojeći_rokovi`/`zakasneli_rokovi`.
- `predmet_hronologija` (table) — the de facto general deadline calendar; `routers/case_dna.py::_sync_rokovi_to_hronologija`
  writes Genome-derived deadlines here so a document-extracted deadline is never a dead end.

The Core Consolidation doc's own reasoning for *not* forcing these into one "Deadline Engine" is worth
preserving verbatim as precedent: the two extraction paths read genuinely different source material (case
`opis` text at creation time vs. document text after Genome runs) at genuinely different points in the case
lifecycle — unifying storage while keeping extraction separate was the correct call, not an unfinished one.

**Must not be reinvented by:** any module computing its own "is this deadline urgent" logic instead of
reading `rocista`/`predmet_hronologija` through `risk_engine.py`'s existing day-count logic (which itself
was bug-fixed twice — BLACKSWAN-CRIT-002 for overdue hearings, Project Synapse for naive/aware datetime
comparison — meaning a third reimplementation is now also at risk of repeating already-fixed bugs).

---

## 6. Actions (Akcije)

**Definition:** An Action is a concrete, stateful "the lawyer must do X by Y" item with a lifecycle (open →
closed), derived from Facts/Evidence/Risks/Gaps/Obligations — never invented independent of them.

**Canonical owner today:** `case_actions` (table, migration 099) is the single stateful action-tracking
table; the single writer is `services/case_evolution.py` (its own consequence-dispatch loop off the Event
Bus). The migration's own table comment is explicit and should be treated as binding: *"Nijedan drugi
modul ne sme pisati direktno u ovu tabelu."* (No other module may write directly to this table.) Every row
carries a `dokaz` (evidence/source) field that is required, non-empty by convention — Core Consolidation's
"no conclusion without source" rule made structural.

This also closes what Core Consolidation §1.2 explicitly killed as a *concept*: "Sledeća akcija" (a
GPT-suggested single next step) no longer exists anywhere in the platform. What replaced it is exactly this
entity (`case_actions`) plus Gaps (§4) — a checklist of verifiable findings, not a recommendation.

**Must not be reinvented by:** any module generating its own "what should the lawyer do next" text via GPT
(this was Cockpit's `sledeca_akcija`, Case Ready Score's `copilot_preporuka`, and Matter Intel's dead
`_INTEL_SYSTEM` prompt — all three already deleted per the Elimination Table). Any NEW module doing this
today would be resurrecting a concept the founder already decided does not survive.

---

## 7. Strategy (Strategija)

**Definition:** Strategy is the one entity that is *legitimately* the lawyer's judgment call, not a
deterministic derivation — it is what the lawyer chooses to do, informed by everything above, and Vindex's
job here is to inform that judgment, never to substitute for it.

**Canonical owner today:** `routers/strategija.py` — 7 GPT-driven modules (Red Team, Litigation, AI Sudija,
Due Diligence, Pravni Revizor, Witness Analyzer, Sudija v2). Unlike every other entity, GPT output *is* the
appropriate mechanism here, because Strategy is inherently advisory reasoning, not a fact about the case.
This is the one entity where "AI may only extract, explain, translate, summarize, structure, and connect"
(Faza 3's constitutional rule) is naturally satisfied by design rather than needing enforcement — *provided*
the inputs to these modules are the canonical Facts/Evidence/Risks/Gaps/Obligations, not a freshly-reinvented
view of the case.

**Watch item, not yet a confirmed violation:** confirm each `strategija.py` module is seeded via
`build_case_context()` (or equivalent canonical reads) rather than its own bespoke Supabase queries — per
`shared/case_context.py`'s own docstring, `strategija.py` was the one module Program Tau 002 explicitly
could NOT migrate onto `build_case_context()` ("it has no `predmet_id`-driven request model at all"). That
means Strategy currently sits *outside* the canonical context pipeline entirely — worth a scoped audit,
since a Strategy module reasoning over a self-fetched, non-canonical version of the case is exactly the
drift this whole model exists to prevent, even though the *output* (strategic advice) is legitimately GPT's
to generate.

**Must not be reinvented as a fact-generator:** Strategy modules may recommend, argue, red-team, and
simulate — they may never assert a Risk number, a Gap, a Readiness state, or an Action as a side effect of
doing so. If a Strategy module's output starts getting read downstream as a case fact (e.g., its
"confidence" being stored and later displayed as if it were `risk_engine.py`'s score), that is the entity
boundary breaking.

---

## The Governing Principle

> **Everything else in the product — dashboards, Cockpit, CIO, the Genome panel, Case Commander, Digital
> Twin, Court Predictor, Copilot — is a VIEW.**
>
> A view is a way of presenting a subset or combination of the seven core entities above, for a specific
> audience or purpose (a morning digest, a pre-hearing brief, a portfolio health page).
>
> **A view must never compute a NEW fact about the case.** It may only select, combine, sort, filter, or
> narrate facts that already exist in the core model (Facts, Evidence, Risks, Gaps, Obligations, Actions,
> Strategy). If a screen shows a number, label, percentage, or status that cannot be traced to one of the
> seven canonical owners above, it is not a view — it is an unauthorized eighth source of truth, and it
> will drift.

`shared/case_context.py::build_case_context()` is the concrete embodiment of this principle already built
into the codebase: it is explicitly documented as computing nothing new except document-selection (a
visibility concern, not a business fact) and aggregation, and every field it returns carries `{value,
source, owner, refresh, timestamp}` — provenance is not optional, it is structural. Any new view-layer
feature should be built by calling this function (or the equivalent canonical readers directly), not by
querying the underlying tables a second time with different logic.

`routers/case_commander.py`'s 2026-08-06 rewrite is the second concrete precedent: it now reads
`case_actions`/`gap_engine.py`/`case_readiness.py` and restricts GPT to *explaining* two
genuinely-advisory sections — every field carries `shared/commander_schema.py`'s `{value, source, evidence,
confidence, generated_by, timestamp}` shape. This is the pattern every future "intelligence surface" should
copy.

---

## The Decision Rule: "Is this a canonical owner or a view?"

Apply this test to any new feature, endpoint, or module before writing it:

**1. Name the business fact.** State in one sentence what fact the feature is displaying or computing (e.g.,
"how strong is the evidence," "what's the next deadline," "should the lawyer worry").

**2. Ask: does one of the seven core entities above already own this fact?**
- If yes → the feature MUST read that entity's canonical function/table (directly, or via
  `build_case_context()`). It may re-shape, filter, sort, or narrate the result. **It may not recompute
  it.** This makes the feature a VIEW.
- If no → proceed to step 3.

**3. Ask: is this fact genuinely NEW — not a rephrasing, not a "smarter version," not a "more personalized
take" on an existing entity?**
- If the "new" fact is actually a Risk, Gap, Action, or Obligation wearing a different name or UI (a
  "danger score," a "priority flag," a "what's missing" list, a "next step") → it is **not** new. Route it
  through the existing owner. This is the trap Cockpit, Case Ready Score, and Matter Intel all fell into
  independently before Core Consolidation.
- If it survives this test as genuinely new (rare) → it may become an eighth canonical entity, but only
  through the same explicit process Core Consolidation itself used: name the concept, assign exactly one
  owner, document what gets deleted or repointed as a result. **A new entity is never introduced silently
  inside a "view" feature.**

**4. The GPT test (Faza 3, unconditional):** does this feature let GPT decide, evaluate, calculate, rank, or
classify anything a deterministic algorithm could instead compute from data already in the seven entities?
If yes, that is a violation regardless of how good the GPT output looks — "how well it works is
irrelevant," per Core Consolidation's own Rule. GPT's only legitimate jobs anywhere in this model are:
extract, explain, translate, summarize, structure, connect, and — uniquely, for Strategy alone —
recommend a course of action, never a fact.

**One-line version for a commit message or PR description:**
*"Does this screen show a number/label that already has an owner? If yes, call the owner. If you're not
sure it has an owner, it probably does — check the seven entities before you write a query."*

---

## Summary table

| Entity | Canonical owner (function/table) | Confirmed or likely current violator |
|---|---|---|
| Facts | `predmeti.case_dna` via `routers/case_dna.py` | `case_pipeline.py` mini-strategy/risk steps (doesn't write back) |
| Evidence | `predmet_dokazi` via `routers/evidence.py` | Historical parallel with Genome's own evidence fields, partially fixed |
| Risks | `services/risk_engine.py::calculate_procesni_rizik` | `routers/court_predictor.py` (GPT-generated `procenat_min/max`, confirmed no `risk_engine.py` call); `routers/digital_twin.py` scenario percentages (needs verification) |
| Gaps | `shared/gap_engine.py::collect_case_gaps` | None found — correctly built as aggregator already |
| Obligations | `rocista` + `predmet_hronologija` (intentionally split) | None found — split is by design, documented rationale |
| Actions | `case_actions` via `services/case_evolution.py` | None found live — prior violators (Cockpit, Case Ready Score, Matter Intel) already eliminated per Core Consolidation Faza 2 |
| Strategy | `routers/strategija.py` (7 GPT modules) | Not seeded via canonical `build_case_context()` — outside the pipeline by Tau 002's own admission; audit recommended |

---

*Document status: conceptual/architectural definition only. No code was changed to produce this document.
Grounded in direct reads of `shared/case_context.py`, `services/risk_engine.py`, `shared/gap_engine.py`,
`shared/case_readiness.py`, `services/case_evolution.py`, `migrations/099_case_actions.sql`,
`routers/case_dna.py`, `routers/case_commander.py`, `routers/digital_twin.py`, `routers/court_predictor.py`,
`routers/strategija.py`, and `docs/architecture/VINDEX_CORE_CONSOLIDATION.md`, all in the working tree as
of 2026-08-07.*
