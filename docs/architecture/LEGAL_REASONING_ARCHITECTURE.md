# Legal Reasoning Engine — Architecture

**Status:** Phase 0 implemented (commit `b5c210a`), migration not yet run. **Phase 0.5 (Reality Calibration) is the current gate** — Phase 1 does not start until LRE beats Genome on real cases, not synthetic ones. Nothing past Phase 0 is executed by writing this document.
**Date:** 2026-07-23 (Phase 0.5 added same day, founder review of Phase 0 delivery)
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

## 1. The single biggest risk this design must not create — RESOLVED (founder decision, 2026-07-23)

Case Genome's extraction (`routers/case_dna.py::_extract_genome`, `_GENOME_SYSTEM` prompt) **already produces primitive, semi-structured reasoning today**: `argumenti_za`, `argumenti_protiv`, `kontradikcije`, `snaga_faktori` (each with `faktor`/`uticaj`/`opis`) are GPT-4o-generated interpretations of facts, not raw facts themselves. If LRE is bolted on without touching this, Vindex ends up with **two independently GPT-derived reasoning outputs about the same case** — Genome's own argument lists and LRE's Reasoning Graph — which can disagree.

**Decision: responsibility migration, not field deletion.** Genome's existing fields are not deleted now. Going forward, ownership splits cleanly:

| Stays in Genome (describes) | Moves to LRE (concludes) |
|---|---|
| facts, entities, evidence, timeline, relationships | arguments, counterarguments, contradictions, legal conclusions, confidence |

**Genome never reasons again. Genome describes. LRE concludes.** This is a clean, permanent responsibility line, not a temporary one. The mechanical migration (Genome's extraction prompt stops generating `argumenti_za`/`argumenti_protiv`/`kontradikcije`, frontend Genome panel stops reading them, LRE becomes the read path instead) is Phase 1 work (§12) — **Phase 0 does not touch Genome's extraction at all**, it is purely additive and unwired, so this decision has no effect on Genome until Phase 1 is explicitly approved.

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
  This is a genuinely new artifact — it is not a Genome field.

  **Storage: RESOLVED (founder decision, 2026-07-23) — relational, not jsonb.** A jsonb blob cannot answer "find every argument based on Article 154," "find every contradiction of type X," "find every claim with confidence < 0.6" without a full-table scan and application-side parsing — unacceptable at scale. Canonical storage is six relational tables (schema in §5b); jsonb may exist only as a derived cache/export, never as the source of truth.

### 5a. Versioning and provenance — added requirement (founder, 2026-07-23)

The Reasoning Graph is not a single artifact overwritten in place — it is a **versioned object**, the same way Genome already is (`predmet_genome_history`), but at node granularity, not whole-object granularity:

```
Reasoning Graph v1 → advokat dodaje dokaz → Reasoning Graph v2 → nova presuda → Reasoning Graph v3
```

Every node must carry: when it was created, what triggered its creation/change, and which event produced that trigger. This is not new infrastructure — it reuses the Event Bus (durable outbox, `services/event_bus.py`) and the audit trail (`shared/audit_immutable.py`) exactly as they already exist. Schema support for this is included from Phase 0 onward (not retrofitted later) — see `reasoning_graph.trigger_event`/`verzija` and per-node `created_from_event_id` in §5b.

### 5b. Schema (six tables, per founder's explicit instruction — no jsonb primary storage)

```
reasoning_graph      — one row per (predmet_id, verzija): header/version record
reasoning_nodes      — Fact | LegalElement | Norm | Claim rows, typed
reasoning_edges      — supports | satisfies | creates, references two nodes
reasoning_evidence   — links a Fact node to its source (predmet_dokazi row / document)
reasoning_sources    — links a Norm node to its source (retrieve.py hit: statute article, citation)
reasoning_confidence — one row per Claim node, the weighted formula's components (§10a), not just a number
```

Full DDL: `migrations/076_legal_reasoning_engine.sql` (written, not run — founder runs migrations, per standing project rule).
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

### 10a. Confidence formula — RESOLVED (founder decision, 2026-07-23)

Not "GPT says 91%" — that has no value in front of a lawyer. Confidence is a weighted combination of deterministic and AI factors:

```
confidence = 0.35 × evidence_coverage      (deterministic — computable from Genome/predmet_dokazi)
           + 0.30 × retrieval_agreement    (deterministic — was the cited Norm actually returned by retrieve.py?)
           + 0.20 × precedent_support      (deterministic-ish — sudska_praksa namespace hit count/score for this claim)
           + 0.15 × model_certainty        (AI-reported, GPT's own self-assessment — intentionally the smallest weight)
```

Three of four components are computable without trusting GPT's self-report; `model_certainty` is capped at 15% specifically so a confident-sounding hallucination cannot dominate the score. Each component is stored separately in `reasoning_confidence` (§5b), not collapsed into the single number until display time — so the formula itself stays auditable and re-weightable without regenerating the graph.

## 10. How success gets measured

Per the founder's own standard from the Core Consolidation review (real numbers, not descriptions):

- **Latency:** Reasoning Graph generation time, measured, not estimated (the Core Consolidation sprint's own gap — no timing instrumentation existed — should be fixed starting with this feature, not retrofitted later).
- **Token/cost:** GPT-4o call count and prompt/completion token size for LRE generation, compared against the *combined* token cost of what it replaces (Genome's argument-generation portion + Strategy Simulator's from-scratch reasoning, once §9's rewiring happens) — the honest comparison is LRE's cost vs. the sum of what it consolidates, not LRE's cost in isolation.
- **Quality:** This codebase already has infrastructure for exactly this — the LEC (Legal Evaluation Corpus, `[[project_smart_intake_architecture]]`) built for Smart Intake validation is the right existing tool to extend, not a new one to build. A Reasoning Graph's Claims should be checkable against a small set of real, lawyer-reviewed cases the same way retrieval quality was calibrated (`retrieve.py`'s "30Q benchmark" precedent).
- **Coverage:** % of Genome facts that appear as graph nodes; % of Claims with at least one cited Norm that the retrieval engine actually returned (not invented) — this second number is the hallucination-guard metric and should be the one that blocks a release if it regresses.

---

## 11. Open decisions — ALL RESOLVED (founder, 2026-07-23)

1. **Genome's argument fields:** responsibility migration, not deletion — see §1. Genome describes, LRE concludes. Mechanical migration deferred to Phase 1.
2. **Storage:** relational, six tables, no jsonb as canonical store — see §5a/§5b.
3. **Strategy Simulator:** **not touched in Phase 0 or Phase 1.** Founder's framing: *"Simulator je potrošač. LRE je proizvođač. Prvo napravi proizvođača. Tek onda menjaj potrošače."* Moved later in the rollout than originally drafted — see §12.
4. **Confidence calibration:** weighted formula, not a raw GPT number — see §10a.

## 12. Rollout (Phase 0 approved 2026-07-23 — everything after Phase 0 still needs its own explicit go)

1. **Phase 0 — APPROVED, implemented 2026-07-23.** One case, read-only, wired to nothing, relational schema live from the start (not retrofitted). **Explicit founder condition, binding for this phase: LRE must not generate any user-facing text. Output is exclusively the internal, structured Reasoning Graph — no prose, not even a summary.** Reason (founder's own): generating text immediately would make it impossible to objectively evaluate reasoning quality in isolation from writing quality; validating the graph first means Draft Engine can later be a pure "translator" of already-validated reasoning into legal language, not a second place where reasoning quality gets silently re-decided.
   - **Success metric for Phase 0 is not "does it run."** It is: *does LRE produce a materially better reasoning model of the case than Genome's current `argumenti_za`/`kontradikcije` fields do* — judged by the founder against real output, not by test coverage alone.
   - **Implementation:** `migrations/076_legal_reasoning_engine.sql` (6 tables, written not run — founder runs migrations), `services/legal_reasoning_engine.py` (orchestrator + `compute_confidence` per Sec 10a's exact weights), `routers/legal_reasoning.py` (manual-trigger-only: `POST .../reasoning-graph/generate`, `GET .../reasoning-graph`, `GET .../reasoning-graph/history`), `reasoning_graph_generated` added to `AUDITABLE_ACTIONS`. 17 unit tests, full suite 1704 passed. **Not yet run against a live case** — the migration has to be applied first; that first real run is the actual Phase 0 evaluation moment, not the passing test suite.
   - **Retrieval agreement fixed 2026-07-23 (was substring matching, now identity-based) — see Phase 0.5 section below for the full fix.**
1.5. **Phase 0.5 — Reality Calibration (added 2026-07-23, gates Phase 1).** The question stops being *"does it run"* and becomes *"is it actually better than what it's meant to replace."* Not implementation work — an empirical evaluation, same discipline this project has used every time before merging or replacing a system (G-027/G-030/G-034 precedent: measure before architecting, never assume).

   **Method:** 20–30 REAL cases (anonymized if needed — synthetic/calibration-batch cases are explicitly excluded, they were already shown in this project's own history, G-027's validation, to distort results toward artifacts of the test data rather than real signal). For each case, three independent outputs are compared side by side:
   - **(A) Today's Genome** — its existing `argumenti_za`/`argumenti_protiv`/`kontradikcije`.
   - **(B) New LRE** — its Reasoning Graph, rendered into the same comparable shape.
   - **(C) An experienced lawyer's own read of the case** — the gold standard. This column cannot be generated by either AI system or by an implementer; it requires an actual lawyer's judgment on the actual case file.

   **Metrics (not "is it nicely written" — concrete, scoreable per case):**

   | Metric | Genome | LRE | Lawyer |
   |---|---|---|---|
   | Correctly identified key facts | | | |
   | Correctly identified contradictions | | | |
   | Correctly linked evidence | | | |
   | Missed material elements | | | |
   | False conclusions | | | |
   | Usefulness for drafting a submission | | | |

   **Gate condition (binding, not advisory):** if LRE does not beat Genome on these metrics across the real-case sample, Phase 1 (migrating the frontend / deprecating Genome's argument fields) does not happen. A prettier architecture is not sufficient justification for replacing a working system — the replacement has to be measurably better at the thing it's replacing.

   **Hard requirement before this phase can produce a trustworthy result — DONE (2026-07-23), not deferred.** Founder's explicit methodological objection: measuring Phase 0.5 with the substring version, then fixing retrieval scoring, then re-measuring makes it impossible to tell whether quality changed because of LRE or because of the new confidence model — "menjaš instrument kojim meriš eksperiment usred eksperimenta." Fixed before any Phase 0.5 run: `retrieval_agreement` now reads `app.services.retrieve.retrieve_documents()`'s own `retrieval_meta["izvori"]` — a deduplicated, identity-based `{zakon, clan, score}` list per actually-retrieved statute hit that already existed in `retrieve.py` and was simply unused in the first Phase 0 cut. Citations (`SOURCE-n`) are now built exclusively from this list; a citation GPT invents that isn't in it has no valid `SOURCE-n` to attach to and is dropped before it reaches the graph. `retrieval_agreement` is the average retrieval score of the specific citations used — traceable as `Reasoning Node → Evidence ID → Legal Source ID → Retrieved Citation ID`, never a text-overlap guess. Same review pass also caught and fixed a related bug: `reasoning_sources` rows were storing a blanket top-1 `(zakon, clan, score)` on every Norm node regardless of which citation it actually was — now stores each source's own values.

   **Evaluation framework — built, not a one-off script (founder, 2026-07-23): `evaluation/phase_0_5/`** (`metrics.py`, `run.py`, `compare.py`, `report.py`, `datasets/`, `outputs/`) — reusable for future evaluations (LRE v2, Precedent Engine, Draft Engine, Adversarial Review). Full process in `evaluation/phase_0_5/README.md`. Key design points, all founder-specified:
   - **Blind A/B.** The lawyer reviews "Analysis A" / "Analysis B" with no indication of source; the real Genome↔LRE mapping lives in a separate key file (`outputs/keys/`), revealed only by `compare.py`, only after scoring — eliminates confirmation bias.
   - **Curated dataset, not automatic selection.** `datasets/dataset_manifest.template.json` has 8 profile slots (simple/complex civil, labor, enforcement, family, contradictory evidence, weak documentation, heavy documentation) for the founder to fill with real, non-synthetic predmet_ids — "ako uzmeš samo prvih 30, možeš dobiti potpuno iskrivljenu sliku."
   - **7th metric added:** *"Da li LRE menja odluku advokata?"* — tracked separately from the averaged 1–5 metrics as the most direct value signal (founder: *"To je pravi dokaz vrednosti"*).
   - Real case data (client facts, evidence) never reaches git — `outputs/` and any real dataset manifest are gitignored; only code and the empty template are tracked.
   - 11 unit tests (blind-label coverage/variance, score-sheet shape, aggregation math including a real caught-and-fixed bug: `isinstance(True, int)` is `True` in Python, which silently misrouted the boolean "changed reasoning" metric into the numeric averaging branch before the fix). Full suite: 1717 passed.

2. **Phase 1 (gated on Phase 0.5 passing):** Execute the Genome responsibility migration (§1) — stop generating argument fields in `_extract_genome`, migrate the Genome panel to read from the Reasoning Graph.
3. **Phase 2:** Argument Graph / Precedent Engine / Draft Engine / Adversarial Review built as consumers, founder's ranked order.
4. **Phase 3 (moved later than originally drafted):** Strategy Simulator rewiring — explicitly last, after the graph is proven stable across real consumers, not just proven to exist.

Same discipline as every G-item closed this session: one phase at a time, review-gated. Phase 0 has a green light. Phase 1 onward does not yet.
