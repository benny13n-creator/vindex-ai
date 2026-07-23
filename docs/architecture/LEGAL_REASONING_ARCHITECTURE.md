# Legal Reasoning Engine — Architecture

**Status:** Design gate — no implementation until the founder reviews this document. Nothing in this document is executed by writing it.
**Date:** 2026-07-23
**Trigger:** Founder review of the Core Consolidation sprint proposed a next major initiative (Legal Reasoning Engine → Argument Graph → Precedent Engine → Adversarial Review → Draft Quality Score) and required this document first, with an explicit condition: *"Ako taj dokument pokaže da se novi engine prirodno uklapa u postojeću arhitekturu, tek onda bih dao zeleno svetlo za implementaciju."*

---

## 0. Definition (founder's own words, kept verbatim as the source of truth)

> Legal Reasoning Engine je centralni sloj između Case Genome i svih viših AI modula. Njegova odgovornost nije da piše tekst niti da donosi konačne preporuke, već da iz strukturiranih činjenica, dokaza i pravnih izvora izgradi proverljiv Reasoning Graph koji eksplicitno povezuje činjenice, pravne elemente, norme i privremene pravne zaključke sa nivoom pouzdanosti. Svi ostali sistemi (Argument Graph, Precedent Engine, Risk Engine, Draft Engine i Adversarial Review) koriste isti Reasoning Graph kao jedini izvor pravnog rezonovanja, čime se eliminiše dupliranje logike i obezbeđuje konzistentnost celog sistema.

Restated as a boundary test (same format as `AR-01`):

- **LRE is:** a transformer. Facts + evidence + legal sources → a structured, inspectable graph of claims and their support.
- **LRE is not:** a rule engine (it doesn't mechanically apply fixed if/then logic like `risk_engine.py`), not a text generator (no prose output), not an orchestrator (it doesn't decide what happens next — it produces a substrate other things read).
- **Four distinct questions, four distinct owners** (founder's framing, preserved exactly):
  - Case Genome → *"Šta znamo?"*
  - Legal Reasoning Engine → *"Šta iz toga logički proizlazi?"*
  - Argument Graph → *"Kako to branimo?"*
  - Draft Engine → *"Kako to pišemo?"*

---

## 1. The single biggest risk this design must not create

Case Genome's extraction (`routers/case_dna.py::_extract_genome`, `_GENOME_SYSTEM` prompt) **already produces primitive, semi-structured reasoning today**: `argumenti_za`, `argumenti_protiv`, `kontradikcije`, `snaga_faktori` (each with `faktor`/`uticaj`/`opis`) are GPT-4o-generated interpretations of facts, not raw facts themselves. If LRE is bolted on without touching this, Vindex ends up with **two independently GPT-derived reasoning outputs about the same case** — Genome's own argument lists and LRE's Reasoning Graph — which can disagree. That is precisely the "one concept, two owners" bug this whole session has been closing, now at risk of being reintroduced one layer up.

**This document takes the position that Genome's argument-shaped fields must be deprecated in favor of reading LRE's Reasoning Graph, not run in parallel with it.** This is flagged as an open decision in §11, not silently assumed — it is a real, disruptive change to an existing, production-verified subsystem (Case Genome), and needs explicit sign-off.

## 2. A second thing worth naming before the design: LRE is AI, not deterministic

`risk_engine.py` earns the name "engine" because it is pure Python — same input always produces the same output, no model call. LRE cannot work that way: deciding whether Fact F12 satisfies Legal Element E4 under Article 154 requires legal judgment, which is not mechanical. LRE's Claim/confidence output is a **sophisticated, structured GPT interpretation**, not an objective computation.

This is fully compliant with AR-01 as written — "structure" and "connect" are explicitly allowed AI behaviors — but the *shape* of the output (a graph with confidence scores) will read as more authoritative than a paragraph of prose. Every downstream consumer (§9) must treat Reasoning Graph edges the same way the Genome Verification Layer already treats Genome itself: visible, inspectable, labeled as AI-derived, never silently promoted to "fact." The existing Trust Layer pattern (`_verifikacija`, "AI je proverio sopstvenu procenu" narrative) is the right template to reuse here, not reinvent — see §3.

---

## 3. Where it plugs into the existing pipeline

```
Document upload → OCR → Evidence Vault classify (predmet_dokazi)
                              │
                              ▼
                    Case Genome extraction (_extract_genome)
                    [already reads Evidence Vault facts — Core
                     Consolidation Sec 1.3, 2026-07-22]
                              │
                              ▼
                    ★ LEGAL REASONING ENGINE ★
                    reads: Genome (facts/theory/parties/evidence)
                         + predmet_dokazi (raw evidence rows)
                         + retrieve.py (relevant statutes/case law)
                    writes: Reasoning Graph (new artifact, §5)
                              │
              ┌───────────────┼───────────────┬───────────────┬──────────────┐
              ▼               ▼               ▼               ▼              ▼
       Argument Graph   Precedent Engine   Risk Engine*   Draft Engine   Adversarial
       (future)         (future)           (existing,     (future)      Review
                                            see §9 note)                 (future)
```

LRE sits **after** Genome, **before** every "higher" consumer. It does not replace Genome (Genome remains the sole owner of case *facts*, per Sec 1.3) — it is the first consumer of Genome that exists purely to reason over those facts, and the last producer before anything client-facing happens.

---

## 4. Existing modules reused (no reimplementation)

| Module | What LRE reads from it |
|---|---|
| `routers/case_dna.py` (Case Genome) | Extracted facts, parties, evidence summary, `datumi_kljucni`, `predmet_dokazi`-derived context already wired in via Sec 1.3 |
| `predmet_dokazi` (Evidence Vault) | Raw classified facts (`tvrdnja`, `pravni_element`, `kategorija`) — same table Genome already reads |
| `app/services/retrieve.py::retrieve_documents` | The "Relevant legal sources" input — this is the existing multi-technique RAG engine (HyDE, Cohere rerank, CRAG loop, `LAW_HINTS` routing across ~30 statutes). LRE does **not** get its own retrieval pipeline; it calls this one, the same way `api.py::pitanje` does. |
| `shared/genome_validator.py` (Verification Layer) | Structural pattern to copy, not code to call directly — LRE needs its own advisory, non-blocking sanity layer over the Reasoning Graph (§8), built the same way `verify_genome()` was: deterministic checks over already-generated AI output, never blocking. |
| `services/event_bus.py` | Durable outbox pattern (`GENOME_UPDATED`'s exact mechanism — direct insert into `events` table, dispatched by `dispatch_pending_events()`) — LRE emits the same way (§7). |
| `shared/audit_immutable.py` | LRE runs get logged the same way `genome_refresh`/`ai_analiza_complete` already are. |

## 5. New modules introduced

- **`routers/legal_reasoning.py`** (or `services/legal_reasoning_engine.py` for the core function + a thin router) — the engine itself.
- **Reasoning Graph data model** (new, not an extension of any existing schema):
  ```
  Node types: Fact | LegalElement | Norm (statute article) | Claim
  Edge types: supports (Fact → LegalElement) | satisfies (LegalElement → Norm)
             | creates (Norm → Claim)
  Every Claim carries: confidence (0–1), source_facts (list), source_norms (list)
  ```
  This is a genuinely new artifact — it is not a Genome field. Storage question is open, see §11.
- **A Reasoning Graph Verification layer** (advisory, non-blocking) — same shape as `genome_validator.py`: are cited facts real (exist in Genome/predmet_dokazi)? Are cited articles ones the retrieval engine actually returned (no invented citations)? This is not optional — the retrieval engine's own `LAW_HINTS` calibration work makes hallucinated citations a known, named risk class in this codebase already; LRE inherits that risk and must inherit the mitigation pattern too.

## 6. APIs changed or added

- **New:** `POST /api/predmeti/{id}/reasoning-graph/generate` — triggers generation (mirrors `case-dna/refresh`).
- **New:** `GET /api/predmeti/{id}/reasoning-graph` — read current graph (mirrors `GET case-dna`).
- **New:** `GET /api/predmeti/{id}/reasoning-graph/history` — versioned, mirrors `case-dna/history` / `predmet_genome_history`.
- **Changed (pending §11 decision):** if Genome's `argumenti_za`/`argumenti_protiv`/`kontradikcije` fields are deprecated per §1, `GET case-dna` responses and every frontend reader of those fields (Genome panel in `index.html`/`vindex.js`) need a coordinated migration — this is not a small, isolated change; it touches a production-verified, currently-live surface.

## 7. Events emitted

New `EventType.REASONING_GRAPH_UPDATED` (string value e.g. `"ReasoningGraphUpdated"`), inserted directly into the `events` outbox table exactly like `GENOME_UPDATED` — **not** through `bus.publish()` directly, for the same documented reason (`_emit_genome_event`'s own comment: avoids the handler firing twice, once in-process and once via the dispatch poller). Natural trigger: on `GENOME_UPDATED` dispatch, a new handler (`on_genome_updated_generate_reasoning`, alongside the existing `on_genome_updated` in `event_bus.py`) queues LRE regeneration — keeping Genome→Reasoning Graph freshness event-driven, not manually triggered, consistent with how Genome itself became auto-firing this session (Sec 1.1–1.6 work, D3/D9).

## 8. Data written back to Genome

**Recommendation: none.** The Reasoning Graph is a downstream, derived artifact — writing it back into `case_dna` would violate the same "one concept, one owner" principle this document is trying to protect (Genome owns facts; a graph of *inferences about* facts is a different concept, per the founder's own four-question framing in §0). It should be its own row/table, versioned independently, referencing a Genome version the way Strategy Simulator now tags `genome_verzija` (Core Consolidation precedent, Sec — Strategy Simulator audit trail work, `simulator_partije`).

## 9. How it avoids duplicating logic — and what has to change to comply

Avoiding duplication isn't automatic just because LRE exists — every consumer has to actually be rewired to use it instead of reasoning independently:

- **Case Genome extraction** must stop generating `argumenti_za`/`argumenti_protiv`/`kontradikcije` as free GPT output once LRE exists (§1) — otherwise this is duplication #1, day one.
- **Strategy Simulator** (`routers/strategy_simulator.py`) currently builds its own adversarial scenarios from raw Genome data via its own GPT-4o call — once LRE exists, it should argue *against Claims in the Reasoning Graph*, not re-derive its own understanding of the case from scratch. This is a real behavioral change to a production-verified, audit-tagged subsystem (Sec 1.3/G-033 work) — sequencing matters, see §12.
- **Risk Engine*** (marked with an asterisk in the diagram, §3): `risk_engine.py` is deterministic and reads `predmet_dokazi`/`predmet_dokumenti`/`rocista` directly — it should **not** be rewired to depend on LRE's GPT-derived confidence scores, or it stops being deterministic and AR-01-compliant. It may *display alongside* Reasoning Graph confidence as a separate, clearly-labeled signal, but the two must not merge into one number. Flagged explicitly so this isn't assumed by a future implementer.
- **Future Argument Graph, Precedent Engine, Draft Engine, Adversarial Review**: each must be built to *consume* the Reasoning Graph as their primary legal-reasoning input, not to independently prompt GPT with raw Genome data the way every current AI feature in this codebase does. This is the actual point of building LRE first — skipping it and building Argument Graph directly against Genome would recreate exactly the fragmentation this document exists to prevent.

## 10. How success gets measured

Per the founder's own standard from the Core Consolidation review (real numbers, not descriptions):

- **Latency:** Reasoning Graph generation time, measured, not estimated (the Core Consolidation sprint's own gap — no timing instrumentation existed — should be fixed starting with this feature, not retrofitted later).
- **Token/cost:** GPT-4o call count and prompt/completion token size for LRE generation, compared against the *combined* token cost of what it replaces (Genome's argument-generation portion + Strategy Simulator's from-scratch reasoning, once §9's rewiring happens) — the honest comparison is LRE's cost vs. the sum of what it consolidates, not LRE's cost in isolation.
- **Quality:** This codebase already has infrastructure for exactly this — the LEC (Legal Evaluation Corpus, `[[project_smart_intake_architecture]]`) built for Smart Intake validation is the right existing tool to extend, not a new one to build. A Reasoning Graph's Claims should be checkable against a small set of real, lawyer-reviewed cases the same way retrieval quality was calibrated (`retrieve.py`'s "30Q benchmark" precedent).
- **Coverage:** % of Genome facts that appear as graph nodes; % of Claims with at least one cited Norm that the retrieval engine actually returned (not invented) — this second number is the hallucination-guard metric and should be the one that blocks a release if it regresses.

---

## 11. Open decisions — founder sign-off required, not silently resolved here

1. **Does LRE deprecate Genome's `argumenti_za`/`argumenti_protiv`/`kontradikcije`?** This document recommends yes (§1), but that is a real, disruptive change to a production-verified, currently-live feature with its own frontend rendering (`index.html` Genome panel) — needs explicit approval, not implied by this doc.
2. **Storage for the Reasoning Graph:** new table (`predmet_reasoning_graph`, relational, queryable per-node) vs. a single jsonb blob (simpler, matches Genome's own pattern, harder to query individual claims). Relational is more honest to "verifiable graph" but is a bigger migration.
3. **Does Strategy Simulator get rewired to consume the Reasoning Graph in the same rollout, or later?** §9 argues it should, eventually — but coupling it to LRE's first release risks destabilizing a subsystem that was just made audit-traceable this session (G-033). Recommend: LRE ships standalone first, Strategy Simulator rewiring is a separate, explicitly-scoped follow-up.
4. **Confidence score calibration:** a 0–1 confidence number from GPT is only meaningful if it's been checked against real outcomes — otherwise it's decoration that *looks* deterministic (the same trap `compute_snaga_score` was built to fix once already, Sec 1.3 history). Needs an explicit calibration step before confidence scores are shown to a lawyer as anything other than "AI's own estimate, unverified."

## 12. Suggested rollout (phases, not a commitment — sequencing needs founder approval same as everything else this session)

1. **Phase 0 — narrowest possible slice:** LRE generates a Reasoning Graph for one case, read-only, not wired into anything, not replacing Genome's existing fields yet. Purely to validate the data model and get real output in front of the founder before any other system depends on it.
2. **Phase 1:** Decision on §11.1 (deprecate Genome's argument fields or not); wire the Genome panel to read from the Reasoning Graph if yes.
3. **Phase 2:** Argument Graph / Precedent Engine / Draft Engine / Adversarial Review built as consumers, in the order the founder ranked them (★★★★★ ×4, then Draft Quality Score).
4. **Phase 3:** Strategy Simulator rewiring (§11.3), only after Phase 2 proves the Reasoning Graph is stable and trusted.

Same discipline as every G-item closed this session: one phase at a time, review-gated, no implementation before the founder says go on Phase 0 specifically.
