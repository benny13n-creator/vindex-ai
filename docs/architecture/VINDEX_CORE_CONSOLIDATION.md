# Vindex AI — Core Consolidation

**Status:** ACTIVE — governing document for all architecture work going forward.
**Date:** 2026-07-22
**Supersedes:** `TRUST_LAYER_BETA_FREEZE_2026-07-19.md`'s "no more code until beta feedback" rule, and the G-027/G-030/G-034 "measure before merging" discipline — **except** for Document Pipeline consolidation (§1.4), which explicitly keeps that discipline by the founder's own instruction.
**Trigger:** `vindex_forensic_product_audit` (2026-07-22, code-only 15-part audit) found that risk, next-action, and document drafting are each independently reimplemented 3 times with no shared code. The founder read this and introduced the principle below the same day, explicitly choosing to prioritize consolidation over the previously-planned pilot-first sequencing.

---

## The Rule

**Jedan poslovni koncept = jedan vlasnik = jedan algoritam = jedan izvor istine.**

If we find two owners, two algorithms, two models, two tables, or two truths for the same business concept — that is not a feature. It is a bug. How well each implementation works is irrelevant. If they do the same thing, one must disappear or change responsibility.

This document is Faza 1 (Ownership Map) plus previews of Faza 2 (elimination table), Faza 3 (constitutional AI rule), Faza 4 (six pillars), Faza 5 (deprecation rule), and Faza 6 (commit gate) — all definition, no code deleted yet, per the founder's own sequencing: *"Pre nego što se obriše i jedna linija koda, moramo definisati ko poseduje šta."*

---

## Faza 1 — Ownership Map

Each entry below states the concept, the declared owner, current violators (verified against code, not assumption), and what changes.

### 1.1 Rizik (Risk)

- **Owner:** `services/risk_engine.py::calculate_procesni_rizik` — already true today, already deterministic.
- **Compliant today:** `routers/matter_intel.py`, Cockpit's workspace endpoint in `api.py` (both read `risk_engine.py`'s output).
- **Violators (confirmed):**
  - `services/case_pipeline.py`'s own risk-snapshot step calls GPT-4o-mini independently instead of `risk_engine.py`. Feeds Case Ready Score's `copilot_preporuka`.
- **Target:** the case pipeline's risk-snapshot step is repointed to call `risk_engine.py::calculate_procesni_rizik` directly. Its GPT call, if kept at all, may only *explain* the already-computed level — never re-derive it. This is the smallest, most mechanical item on this map: one call site, one proven pattern (G-027) to reapply.

### 1.2 Sledeća akcija (Next Action) — **concept eliminated**

- **Decision (already made, not open for re-litigation):** "next action" as a suggestion-generating concept does not survive. It is replaced by two deterministic outputs:
  - **Administrativni status** — spreman / nije spreman (ready / not ready). Case Ready Score's existing 0–100 readiness computation is the closest existing building block.
  - **Otkriveni problemi** — a checklist of concrete, deterministic findings (e.g. "nedostaje odgovor tuženog," "ostalo 7 dana do roka," "nije dodat veštak"). Not a suggestion — an analysis. The lawyer decides what to do about it.
- **Owner of the new model:** `routers/matter_intel.py::_compute_next_action` is the nearest existing deterministic engine and becomes the basis for "Otkriveni problemi." It already reuses `risk_engine.py`'s signals and has zero AI exposure — the one component on this entire map that already matches the target shape.
- **Deprecated under this decision:**
  - Cockpit's `sledeca_akcija`/`prioritet` (`api.py::_fetch_cockpit_ai`) — free-form GPT, `prioritet` fully GPT-decided with no deterministic backing. The clearest AR-01 violation found in the audit (previously logged separately as G-029).
  - Case Ready Score's `copilot_preporuka` (`services/case_pipeline.py::_step_copilot_preporuka`) — GPT-generated recommendation text, gated behind a manual trigger.
  - `routers/matter_intel.py`'s own dead `_INTEL_SYSTEM` GPT prompt constant (never referenced — leftover from a prior GPT-based version of this exact router, already replaced once).
- **Not affected:** `routers/workflow.py::sledeci_korak` — confirmed by G-030 discovery to be a different concept entirely (progression through an explicitly-started, firm-authored template), never shown on the same screen as the other three. Out of scope for this consolidation.

### 1.3 Case Genome

- **Owner:** `routers/case_dna.py` / `predmeti.case_dna` — sole source of truth about a case's facts, theory, evidence, and strength.
- **Violators (confirmed):**
  - Evidence Vault (`routers/evidence.py`) keeps its own extracted claims in `predmet_dokazi`, which Genome never reads — a parallel, uncross-referenced "what is the evidence" representation.
  - `services/case_pipeline.py`'s mini-strategy and risk-snapshot steps do not write their findings back to Genome — they produce their own disconnected output.
  - The header comment in `routers/case_dna.py:3-5` already *claims* Genome is read by "all other AI functions before analysis" — confirmed false for the case pipeline, learning engine, confidence calibrator, and firm memory (zero references found).
- **Target:** OCR/Evidence Vault findings stop being a parallel truth and become **events** — Genome is the write-target, not a competing store. This is the largest single item on this map; it requires an actual data-flow change (Evidence Vault → event → Genome update), not just a call-site swap.

### 1.4 Dokumenti (Document drafting) — **explicit exception, stays empirical**

- **Status: interim ownership assigned 2026-07-22 (docstrings only, no merge, no code deletion).**
- **Corrected architecture** (found during implementation — more precise than the original forensic audit's "three independent siblings" framing): `drafting/router.py` is a plain business-logic module (no FastAPI router of its own); `routers/drafting.py` imports and wraps it at `POST /api/nacrt`, AND separately hosts its own `POST /api/podnesak` logic against `templates/podnesci.py`. So there are two route-hosting files, not three, but three genuinely distinct generation mechanisms:
  - **`POST /api/nacrt`** (`drafting/router.py` + `drafting/templates.py`, 17 types) — quick single-shot draft, no case/RAG context, deterministic template fill.
  - **`POST /api/podnesak`** (`routers/drafting.py` + `templates/podnesci.py`, 12 types) — RAG-augmented (sudska praksa retrieval), tied to an open predmet, deterministic template fill. **6 types are exact duplicates of `/api/nacrt`'s registry** (`tuzba_naknada_stete`, `tuzba_radni_spor`, `tuzba_razvod`, `prigovor_platni_nalog`, `krivicna_prijava`, `predlog_privremena_mera`) — same type key, different template text, no shared code.
  - **`POST /api/doc-templates/generisi`** (`routers/doc_templates.py`, 7 types) — fully freeform GPT-4o, no deterministic assembly step at all. Its 7 templates use different id strings (`tuzba-opstinska` vs `tuzba_naknada_stete`) but every one conceptually overlaps with the other two registries.
- **What "interim ownership" means here, concretely:** each file now carries a header docstring stating its actual distinct scope (context depth, RAG vs. no-RAG, deterministic vs. freeform) and an explicit freeze — no new template type may be added to any of the three registries if that type already exists in another. This is documentation, not a merge: it stops the duplication from *growing*, it does not resolve what already exists.
- **Founder's instruction, preserved as-is:** do not merge now, do not pick a winner. After pilot data exists, one survives — chosen empirically, same discipline as G-027/G-030/G-034, not by intuition. *"Prvo: A, B, C dobijaju ownership. Posle pilota: preživljava jedan."*

### 1.5 Rokovi (Deadlines) — done to the extent safe without a redesign

- **Corrected picture (found during implementation):** deadlines were fragmented three ways, not two. `predmet_hronologija` is the actual, already-used calendar table (Cockpit's "Hitni rokovi" card reads it, `case_pipeline._step_kalendar` checks it, case_pipeline's step3 already writes into it — extracted from the predmet's own `opis` text at creation time). `rocista` is a separate concept (scheduled hearings, feeds `risk_engine.py`'s `kriticni_rokovi`/`predstojeći_rokovi`). Genome's `rokovi_kriticni` (extracted from uploaded *documents*, richer than opis-text extraction) lived only inside the `case_dna` jsonb blob — **never written anywhere queryable**, invisible to Cockpit, Health Index, and risk scoring alike.
- **Why a full "Deadline Engine" wasn't built now:** `case_pipeline`'s step3 runs at case-creation time, before any documents typically exist — it cannot "read from Genome" as the original plan assumed, because Genome doesn't exist yet at that point in the flow. The two extraction paths are not actually redundant — they read from different source material (opis text vs. document text) at different points in the case lifecycle. Forcing them into one engine today would require redesigning pipeline ordering, out of scope for a same-day fix.
- **What was done instead (real, shipped fix):** `routers/case_dna.py::_sync_rokovi_to_hronologija` — every Genome refresh now writes its `rokovi_kriticni` findings into `predmet_hronologija` (deduplicated by `(dogadjaj, datum_iso)`), the same table case_pipeline's step3 already uses. This makes `predmet_hronologija` the de facto single deadline calendar in practice — a document-derived deadline is no longer a dead end. The two *extraction* mechanisms remain separate (correctly, given the timing constraint above); the *storage* is now unified.
- **Still open:** `rocista` (hearings) remains a third, separate table by design (different concept — a hearing is not a generic deadline) and is unaffected by this change.

### 1.6 Audit / Istorija (Timeline) — done, corrected the original plan

- **Correction found during implementation:** the original plan assumed a unified Timeline API needed to be built from scratch. It already existed — `GET /api/predmeti/{predmet_id}/intelligence-timeline` (`routers/intelligence_timeline.py`), aggregating 5 sources (predmet creation, `predmet_dokumenti`, `rocista`, `predmet_hronologija`, `predmet_genome_history`) into one sorted, icon/color-coded feed. This is the Timeline pillar (Faza 4) — it just wasn't named as such before. Building a second one would have been the exact mistake this whole consolidation exists to prevent.
- **What was actually missing:** `audit_immutable` (the hash-chained, compliance-relevant log) was the one source not yet merged into this feed. Added as a 6th source: `predmet_*`-scoped actions match `resource_id = predmet_id` directly; `dokument_*`-scoped actions (whose `resource_id` is the *document* id, not the predmet id) are matched via the document id list already collected for the "Dokumenti" section, avoiding a second round-trip design and any JSON-metadata filtering.
- **What was deliberately not done:** the hash-chain integrity mechanism (`verify_chain_integrity`) is untouched — the two tables keep their different guarantees (tamper-evident vs. not); this is a read-layer merge only, matching the founder's own framing ("one query surface, not four").
- **Coverage note carried forward, not solved here:** `audit_immutable`'s own allowlist is still only partially wired (Part 9/14 of the forensic audit) — this section surfaces whatever *is* logged, it does not increase what gets logged.

---

## Faza 2 — Elimination Table (executed 2026-07-22, Sec 1.1–1.6)

| Koncept | Owner | Ostali implementacije | Status |
|---|---|---|---|
| Rizik | `risk_engine.py` | case pipeline's own GPT risk snapshot | **Done.** `_step_risk_snapshot` now calls `calculate_procesni_rizik` directly; the independent GPT call is gone. Commit `96a44ac`. |
| Sledeća akcija | *(no owner — concept removed)* | Cockpit `sledeca_akcija`, Case Ready Score `copilot_preporuka`, dead `_INTEL_SYSTEM` prompt, Matter Intel's own `_compute_next_action` | **Done.** All replaced by the single `identify_case_problems()` function; dead prompt deleted; UI surfaces (Cockpit card, `pred-crs-copilot`) now render deterministic output. Commit `96a44ac`. G-029 and G-030 closed in the Gap Register as a result. |
| Case Genome | `case_dna.py` | Evidence Vault's parallel `predmet_dokazi` truth | **Done, narrower scope than planned.** `_extract_genome` now takes already-classified Evidence Vault facts as prompt context (`_fetch_dokazi_kontekst`). Commit `0c786fd`. **Not done** (explicitly out of scope, documented): case pipeline's mini-strategy/risk output still doesn't write back into Genome — this is a smaller residual item, not the "largest single item" originally assumed. |
| Dokument | *(interim, still pilot-gated)* | Pipeline A / B / C | **Interim ownership assigned, no merge** — exactly as planned. Each file now documents its real scope and a freeze on new overlapping types. Commit `998e26f`. Resolution stays pilot-gated per explicit founder instruction. |
| Rokovi | `predmet_hronologija` (de facto, not a new engine) | Genome's `rokovi_kriticni` extraction, case pipeline's own deadline extraction | **Storage unified, extraction deliberately NOT unified.** A dedicated Deadline Engine was scoped and rejected — case pipeline's step3 runs before documents exist, so it cannot read from Genome at that point in the lifecycle; the two extraction paths read genuinely different source material at different times. What shipped: `_sync_rokovi_to_hronologija` writes Genome-derived deadlines into the same calendar table case pipeline already uses. Commit `8f714e1`. |
| Istorija / Audit | `routers/intelligence_timeline.py` (pre-existing, not built new) | `predmet_hronologija`, `audit_immutable` | **Done — corrected the plan.** A unified Timeline endpoint already existed (`GET /api/predmeti/{id}/intelligence-timeline`, 5 sources). `audit_immutable` was the one missing source; added as a 6th. Building a new endpoint would have been a duplicate-implementation mistake, caught before it happened. Commit `7cd24d6`. |

All six rows closed 2026-07-22. Brutal-audit verification pass (same day) found and fixed one defect (`identify_case_problems`'s `tip_predmeta` parameter was accepted but never used) and corrected several planning assumptions in this document to match what was actually built (see each row above) — see the audit's own findings in the final report delivered to the founder.

---

## Faza 3 — Constitutional AI Rule

Extends AR-01 (previously proven only for risk, via G-027) into a platform-wide rule:

**AI never decides, evaluates, calculates, ranks, or classifies anything for which a deterministic algorithm exists.**

**AI may only:** extract, explain, translate, summarize, structure, and connect.

Any GPT call whose output is a business fact used downstream without a deterministic backing (a risk level, a priority, a readiness score, a next step) is, by definition, a violation of this rule and belongs in the Faza 2 elimination table.

---

## Faza 4 — Vindex Core: Six Pillars

Everything else in the codebase must be a plugin against one of these six. A module that cannot name which pillar it serves is a candidate for the Faza 5 deprecation process.

1. **Case Genome** — Istina (truth)
2. **Workflow Engine** — Stanje (state)
3. **Risk Engine** — Analitika (analytics)
4. **Document Engine** — Izvršenje (execution)
5. **Timeline** — Istorija (history)
6. **Automation Engine** — Akcije (actions)

---

## Faza 5 — Deprecation Rule

A module goes to **DEPRECATION → DELETE** if it:
- has no owner,
- duplicates an owner,
- has no caller/user,
- has no test, or
- has no stated reason to exist.

No exceptions made on sentiment. Applied one module at a time, through the same review-gated cycle as every G-item this project has closed so far — analyze, propose the minimal change, get explicit confirmation, implement, verify, close.

---

## Faza 6 — Development Gate

No commit is accepted going forward unless it can answer:

1. Ko je vlasnik? (Who is the owner?)
2. Da li već postoji vlasnik? (Does an owner already exist?)
3. Da li uvodim novi poslovni koncept? (Am I introducing a new business concept?)
4. Da li dupliram postojeći? (Am I duplicating an existing one?)
5. Da li AI odlučuje ili samo objašnjava? (Does the AI decide, or only explain?)
6. Koji modul će biti obrisan zbog ovoga? (What module gets deleted because of this?)

If the honest answer to #6 is "none" on a change that touches an existing concept, that is itself a signal of new technical debt, not a pass.

---

## Method note (founder's explicit instruction, preserved verbatim in spirit)

Do not walk the codebase asking "what looks redundant, delete it." That is dangerous. Walk it asking **"what business concept does this code own?"** If the answer doesn't exist, or two different answers exist, that is an objective reason to refactor — not a feeling that something is "ugly." This is what keeps the outcome of this consolidation a *simpler* system, not merely a *smaller* one.

---

## Sequencing

Talas 1 (single sources of truth) → Talas 2 (remove parallel implementations) → Talas 3 (architecture cleanup: deprecation, dead code, dead routes, dead prompts, unused tables/columns — only after confirming non-use) → Talas 4 (RLS verification, E2E tests on core flows, OCR/Genome performance tests, UX polish, pilot with real lawyers — pilot is now the *last* step, not the first).

**Talas 1 status: complete (2026-07-22).** All six §1 items closed and verified — see the Faza 2 Elimination Table above for exact outcomes, including two places where implementation corrected the original plan (Sec 1.3's scope was narrower than assumed; Sec 1.6 discovered a pre-existing Timeline endpoint instead of building a new one) and one place where a planned unification was deliberately rejected for a documented reason (Sec 1.5's Deadline Engine — timing constraint, not an oversight).

**Talas 2 (remove parallel implementations)** is largely already achieved as a side effect of Talas 1 for risk and next-action (there is nothing left to remove — the parallel implementations were deleted outright, not just repointed). Document drafting (§1.4) remains the one deliberately-deferred exception. **Talas 3 and Talas 4 have not been started** and are the logical next step whenever the founder chooses to continue.
