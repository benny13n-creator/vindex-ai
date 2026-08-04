# PROGRAM GAMMA — Domain Inventory: Case Genome + Evidence Vault + Downstream Decision Consumers

**Mission:** Masterprompt 003, "Canonical Decision Engine — Eliminate Entire Classes of Decision
Fragmentation." **Lens:** not code duplication (Program Alpha) and not AI-value non-determinism
(Program Beta) — whether a BUSINESS OR LEGAL DECISION (a conclusion a lawyer reads and acts on) is
independently produced by more than one module.
**Scope:** Case Genome (`routers/case_dna.py`), Evidence Vault (`routers/evidence.py`), and — per this
fork's explicit mandate — every module that reads or conceptually re-derives Genome/Evidence Vault's
output. **Method:** read-only. No code/git changes.

**Prior art read in full before this fork wrote anything**, not re-derived: `docs/architecture/
BUSINESS_LOGIC_INVENTORY.md`, `SOURCE_OF_TRUTH_REGISTRY.md`, `DUPLICATE_DECISION_REPORT.md`,
`CANONICAL_ARCHITECTURE_REPORT.md` (Program Alpha); `AI_DECISION_GRAPH.md`, `EVIDENCE_CHAIN_REGISTRY.md`,
`CONFIDENCE_MODEL_SPECIFICATION.md`, `HALLUCINATION_ELIMINATION_REPORT.md` (Program Beta);
`shared/genome_validator.py`; both prior domain forks for this exact file pair (`2026-08-04_alpha_domain_
genome_memory_strategy_INVENTORY.md`, `2026-08-04_beta_domain_genome_memory_firmbrain_INVENTORY.md`).

**Headline finding, stated up front:** Alpha's and Beta's Genome/Memory/Strategy domain forks both scoped
themselves to `case_dna.py` + `genome_validator.py` + `firm_memory.py` + `memory_graph.py` + `strategija.py`
— i.e., Genome itself and its immediate siblings. Neither fork walked the actual *consumers* of Genome's
output (`routers/case_commander.py`, `routers/case_intelligence.py`, `routers/evidence_graph.py`,
`routers/matter_intel.py`'s Uncertainty/Pre-Flight endpoints, `services/case_pipeline.py`'s strategy step).
This fork did, per its mandate, and found that the two decision types Alpha/Beta already flagged as having
multiple authors inside Genome itself (case strength, "next action") are **substantially worse** once the
consumer layer is included — not 2 authors, but up to 4 and 7 respectively — and that a third decision type
neither prior mission examined at all ("contradiction between evidence") has 4 independent authors none of
which reference each other.

---

## 1. Decision-by-decision inventory (every Gamma-listed decision type found in scope)

### 1.1 Procesni rizik / case risk / case quality / case readiness — **4 independent producers**

| # | Author | File:line | Method | Reused elsewhere? |
|---|---|---|---|---|
| 1 | `services/risk_engine.py::calculate_procesni_rizik` | (canonical per Alpha's `SOURCE_OF_TRUTH_REGISTRY.md`, "Clean") | Deterministic, tallies `predmet_dokazi`/documents/rocista | Yes — Dashboard, Matter Intel's own main endpoint, `zadaci.py`, `case_pipeline.py` steps 7/8 (explicitly, by comment, to stop a prior duplicate — see §3) |
| 2 | Case Genome `snaga_predmeta_procent` | `shared/genome_validator.py::compute_snaga_score`, called `case_dna.py:304` | Deterministic arithmetic over LLM-extracted `snaga_faktori` | Yes — Genome UI, Copilot, feeds Health Index (§1.1a below) |
| 3 | Matter Intel **Uncertainty Dashboard** `uncertainty_score` | `routers/matter_intel.py:267-434`, dimensions computed `320-375` | 5 ad hoc heuristic dimensions (`cinjenicna/procesna/pravna/protivnicka/finansijska`, each 0-100) + a `gpt-4o-mini` prose gloss (`386-424`) | **No** — does not call `calculate_procesni_rizik` (imported at file top, line 22, but never referenced inside this endpoint) and does not read `case_dna`/Genome at all |
| 4 | Matter Intel **Pre-Flight Check** `status`/`score` | `routers/matter_intel.py:445-468` (prompt schema), `561-582` (call) | Fully raw `gpt-4o` output — `status: spreman\|potrebna_paznja\|nije_spreman`, `score: 0-100`, zero backend computation | **No** — no `calculate_procesni_rizik`, no `compute_snaga_score`, no `case_dna` read |

**Why this is worse than what Alpha/Beta already flagged:** Alpha's `SOURCE_OF_TRUTH_REGISTRY.md` marked
Genome's strength % "Clean, but see UI-perception note" against Risk Engine's number (2 legitimate
single-authors, no dual-authorship, just a labeling gap). That verdict is only true if the consumer layer
is excluded. Once Matter Intel's own two other endpoints (Uncertainty, Pre-Flight — same file, same router,
same "Matter Intelligence Dashboard" product surface per the file's own docstring) are included, the same
predmet can show a lawyer **4 different "how strong/ready/risky is this case" numbers**, computed by 4
different methods, on 4 different screens, none referencing the other three. #3 and #4 are the most severe
because they don't even attempt reuse — #3 imports the canonical function and doesn't call it in this
endpoint; #4 doesn't import it at all. Neither has a `compute_*()`-style deterministic post-processor of
the kind `CONFIDENCE_MODEL_SPECIFICATION.md` names as the mandatory pattern for exactly this shape of
value ("Da li već postoji ekstrahovan, slučaj-specifičan signal iz kog se broj može izračunati? Ako da →
napiši compute_*() funkciju").

**Positive, confirmed-clean sub-finding within Uncertainty Dashboard:** its `cinjenicna` (factual
uncertainty) dimension (`matter_intel.py:320-325`) DOES correctly reuse `shared/constants.py::EXPECTED_DOCS`
(the same canonical missing-document registry Alpha confirmed clean) — only the other 4 dimensions and the
final score are freestanding.

### 1.2 Kontradikcija između dokaza / contradiction between evidence — **4 independent producers**

| # | Author | File:line | Scope | Validated? | Audited? |
|---|---|---|---|---|---|
| 1 | Case Genome `kontradikcije` | `case_dna.py` (`_GENOME_SYSTEM`, lines 83-85) | Whole case, all docs | Yes — `_validate_kontradikcije_lokacije`, `genome_validator.py:102-123` (hard-flags a DOK-XX that doesn't exist among case documents) | Yes — `ai_provenance.case_context()` |
| 2 | Compare Docs `kontradikcije` | `case_dna.py:1007-1107` (`_COMPARE_SYSTEM`) | 2 named documents | Yes (Program Beta addition) — `validate_dok_reference()`, `genome_validator.py:269-297`, invoked `case_dna.py:1089-1091` | Yes (Program Beta addition) |
| 3 | Evidence Graph `OSPORAVA` edge | `routers/evidence_graph.py:38-59` (prompt), `111-160` (`_pozovi_gpt`) | Whole case: documents + `predmet_komentari` + `rocista`, up to 30 nodes/50 edges | **No** — no DOK-XX-style existence check, no reuse of `genome_validator.py` at all | **No** — grepped the whole file: zero `ai_provenance`/`case_context`/`log_action` references |
| 4 | Case Commander cross-case `kontradikcija` finding | `routers/case_commander.py:488-594`, esp. prompt lines 528-554 | **Across ALL active predmeti at once** — "protivrečnosti unutar jednog predmeta ili između beleški i dokumenta" | **No** — free JSON, no existence check against any document/note | **No** — zero `ai_provenance`/`case_context`/`log_action` in the file |

None of the 4 reference each other's output, and #3/#4 don't even reuse the validator function (`
validate_dok_reference`) that #1/#2 already prove works for exactly this claim shape ("does the referenced
document/entity actually exist in scope"). This is a decision type **neither Alpha's nor Beta's Genome-
domain forks inventoried at all** — Alpha's registry and Beta's decision graph both stop at Compare Docs;
Evidence Graph and Case Commander are absent from both. A lawyer opening 3 different screens for the same
case (Genome tab, Evidence Graph tab, this morning's Case Commander briefing) can get 3 different answers
to "does this case contain a contradiction," with a 4th, differently-scoped answer if they run Compare on
two specific documents.

### 1.3 Sledeći preporučeni korak / next recommended action / preporuka za korisnika — **6-7 independent producers**

| # | Author | File:line | Grounded in canonical risk_engine? | Audited? |
|---|---|---|---|---|
| 1 | `services/risk_engine.py::identify_case_problems` | canonical (Alpha: Clean) | — (it IS the canonical signal) | via callers |
| 2 | Genome `najslabija_tacka.preporuka` + `strategija.*` | `case_dna.py` (`_GENOME_SYSTEM` 105-122) | No — raw GPT, `PROGBETA-004` still open per Beta | Yes (`case_context`) |
| 3 | `routers/zadaci.py::ai_analiziraj_predmet` | `zadaci.py:491-` (`_otkriveni_problemi = identify_case_problems(...)`, line 622) | **Yes** — Beta's own "positive reference pattern": deterministic problems computed BEFORE the LLM call and injected with a "don't invent beyond this" instruction | Yes (`case_context`, line ~645) |
| 4 | Case Intelligence Briefing `sledeci_korak` | `routers/case_intelligence.py:36-78` (schema), `318-383` (endpoint) | No — reads Genome's `najslabija_tacka.preporuka`/`strategija`/`nedostaje`/`upozorenja` as unstructured TEXT (`_build_context_text`, lines 190-313) alongside lessons/firm_dna/case_patterns/alerts/decision_log, then does **one more** unconstrained `gpt-4o` synthesis pass to produce yet another single recommendation, written to `decision_log` | **No** — zero `ai_provenance`/`case_context`/`log_action` in the file |
| 5 | Case Commander `commander_analiza`'s "PREPORUCENI POTEZ" | `case_commander.py:36-62` (mandatory report section), `217-277` | **No** — built from raw `predmeti`/`rokovi`/`predmet_dokumenti`/`predmet_komentari` tables (`_dohvati_predmet_kontekst`, 78-136); confirmed by full read that this file never imports `risk_engine` or reads `case_dna` anywhere | No |
| 6 | Case Commander `commander_quick_check` ("3 najhitnija upozorenja/akcije") | `case_commander.py:280-333` | No | No |
| 7 | Case Commander `commander_jutarnji`'s cross-case `prioritet` ("koji JEDAN predmet treba da bude prioritet danas") | `case_commander.py:488-594`, prompt lines 528-554 | No | No |
| 8 | `services/case_pipeline.py::_step_strategija` ("Preporučena strategija" + "Sledeći koraci") | `case_pipeline.py:351-415` | No — free GPT-4o-mini prose at case-creation time, written to `predmet_istorija` with a **hardcoded, unmeasured** `"confidence": "MEDIUM"` label (line 407) | No |

Note steps 7/8 of `case_pipeline.py`'s OWN earlier pipeline (`_step_risk_snapshot`, `_step_copilot_
preporuka`, lines 500-625) are the **positive counter-example already fixed** by Core Consolidation
(2026-07-22): their docstrings explicitly say a prior independent GPT-4o-mini "next action" call was
removed in favor of `identify_case_problems`, and code confirms it. That makes it stranger, not better,
that `_step_strategija` — five steps earlier in the exact same file, exact same pipeline run, exact same
predmet — was never given the same treatment; it still runs its own unconnected "Preporučena strategija /
Sledeći koraci" GPT call.

**This is the single most fragmented decision type found in this domain.** Beta's `AI_DECISION_GRAPH.md`
named Strategy Engine's 4-generator win-probability split as "NAJOZBILJNIJI nalaz misije" (the mission's
most serious finding) for that domain. "Next recommended action" in the Genome-consumer layer has 6-7
generators, only 1 of which (`zadaci.py`) is proven grounded in the canonical signal, and the other 6 don't
even reference Genome's own already-computed `najslabija_tacka.preporuka`/`strategija` — they either
re-read Genome as loose prose and re-synthesize (Case Intelligence) or skip Genome and risk_engine entirely
and re-derive from raw tables (Case Commander ×3, Case Pipeline's strategy step).

### 1.4 Prioritet dokaza / evidence priority / evidence strength — **2 independent producers, different granularity**

| # | Author | File:line | Grain | Method | Vocabulary |
|---|---|---|---|---|---|
| 1 | Evidence Vault `predmet_dokazi.snaga` | `routers/evidence.py::_snaga_iz_lokacije`, `163-185` | Per extracted fact (`kljucne_cinjenice[i]`) | Deterministic given grounding: `jaka` only if `_lociraj_tvrdnju` found the claim verbatim AND length in `[20,100]` chars (Program Beta fix) | `jaka \| srednja` |
| 2 | Genome `dokazi_rang[].snaga_score`/`zvezdice` | `case_dna.py` (`_GENOME_SYSTEM` 101-104) | Per document | Raw GPT; only internally cross-checked against the OVERALL `snaga_predmeta_procent` (`_validate_snaga_konzistentnost`, `genome_validator.py:229-266`) — **never cross-checked against Evidence Vault's own per-fact `snaga` for the same document's facts** | `0-100 score` / `1-5 zvezdice` |

Both answer "how strong is this evidence for this case," at different grain, with different vocabularies,
in different UI panels (Evidence Vault vs. Genome tab), with zero reconciliation — the exact "kontradikcija
moguća, nepotvrđeno" shape Beta's `AI_DECISION_GRAPH.md` Phase 7 table already names for `snaga_predmeta_
procent` vs. `dokazi_rang` (an internal Genome check, which exists) but does NOT name for Evidence Vault's
`snaga` vs. Genome's `dokazi_rang` (a cross-module check, which does not exist). Lower severity than §1.1-
1.3 because the two values are legitimately different questions (fact-level vs. document-level), but a
document rated 5 stars in Genome whose constituent facts are all `srednja` (unverified) in Evidence Vault
would show no warning anywhere that the two signals disagree.

### 1.5 Klasifikacija činjenica / fact classification — 1 canonical direction, not fully closed

Evidence Vault extracts `kljucne_cinjenice` per document at upload time (`evidence.py::_klasifikuj_
dokument`, `gpt-4o-mini`). Genome separately extracts `stranke/svedoci/vestaci/finansije/datumi_kljucni`
case-wide at refresh time (`case_dna.py`, `gpt-4o`) from the **same raw documents**. Core Consolidation
Sec 1.3 (2026-07-22) made this partially one-directional: Genome's `_fetch_dokazi_kontekst` (`case_dna.py:
166-185`) now injects Evidence Vault's already-extracted facts as advisory context ("koristi kao dodatni
kontekst, ne izmišljaj nove ako se ne poklapaju sa tekstom"). This is a real, confirmed improvement (not
re-litigated from scratch — Alpha/Beta both note it) but it does not make Evidence Vault authoritative:
Genome is still free to, and by construction does, run its own independent extraction pass over the same
source text rather than being constrained to reconcile with Evidence Vault's already-grounded
(`_lociraj_tvrdnju`-verified) facts. **Not ranked Critical** — advisory injection is a real mitigation, not
a placebo — but it is a one-way suggestion, not a single source of truth, and is the reason §1.4's per-fact
vs. per-document evidence-strength split can happen at all.

### 1.6 Značaj dokumenta / document significance — clean, single-sourced

`datumi_kljucni[].znacaj` (`kriticno|bitno|informativno`) and `dokazi_rang` (1-5 stars) are both computed
only inside Genome; no other module in scope independently re-derives per-document or per-date
significance. Raw-GPT status is already tracked by Beta (`CONFIDENCE_MODEL_SPECIFICATION.md`, `heatmap`/
`najslabija_tacka.kriticnost` row) — not re-flagged here since it is not a *multi-author* problem, which is
this fork's specific lens.

### 1.7 Procesno upozorenje / procedural warning — **3 independent producers**

Genome `upozorenja` (`case_dna.py`, list of raw-GPT strings) vs. Case Commander `quick-check`'s "3
najhitnija upozorenja" (`case_commander.py:280-333`, free GPT-4o-mini text) vs. Matter Intel Pre-Flight's
`kriticna_upozorenja` (`matter_intel.py:445-468/561-582`, raw GPT list). Three independent "what should
worry the lawyer right now" text lists for the same predmet, no shared source, no cross-reference, no
component reuses another's already-computed warnings.

### 1.8 Promena rizika / promena prioriteta / potreba za eskalaciju — mixed: 2 clean, 1 fragmented

- **Promena rizika (risk change):** `case_dna.py::_compute_delta`/`_delta_significant` (lines 315-402) is a
  deterministic, single-owner, well-designed mechanism — compares old vs. new Genome snapshot, computes
  `snaga_delta`/`kontr_eliminisane`/`nt_kriticnost_delta`/`nedostaje_delta`, decides significance via named
  thresholds. **Clean**, a genuinely good pattern, no second author found.
- **Potreba za eskalaciju (escalation need):** `case_dna.py::_maybe_alert_require_review` (417-447), driven
  by `verify_genome()`'s deterministic `odluka`. **Clean**, single-sourced, non-spamming (fires only on
  transition into `require_review`).
- **Promena prioriteta (priority change):** Case Commander's cross-case `prioritet` (§1.3, row 7 —
  "which ONE case should be priority today") is the only "priority" decision found in scope, and it is
  **not** a change/delta computation at all — it's a fresh raw-GPT judgment every morning, with no
  reference to risk_engine's `health_score`, Genome's `snaga_predmeta_procent`, or any deadline-criticality
  signal already computed elsewhere in the platform (`ccc.py`, `matter_intel.py`'s `kriticni_rokovi`).
  **Fragmented / ungrounded**, not a "second author of the same computation" so much as "zero-author,
  freestanding LLM opinion" for a decision that 3+ deterministic ingredients already exist to ground.

---

## 2. Audit/Provenance status across the newly-examined consumer layer

Program Beta's `EVIDENCE_CHAIN_REGISTRY.md` states Compare Docs was, before that mission's fix, "the only
AI call [in its scope] with zero of three [provenance/evidence/UI] links." That claim was true **only**
for `case_dna.py` itself. Confirmed by direct grep of each file (no `ai_provenance`/`case_context`/
`log_action` reference found in any of the four):

| File | AI-decision endpoints | Provenance wrapping |
|---|---|---|
| `routers/evidence_graph.py` | `/generisi` (nodes/edges incl. `OSPORAVA` contradiction edges) | **None** |
| `routers/case_commander.py` | `/analiza`, `/quick-check`, `/checklist`, `/jutarnji` (4 distinct GPT operations) | **None** |
| `routers/case_intelligence.py` | `/briefing` (`sledeci_korak` synthesis) | **None** |
| `routers/matter_intel.py` | `/uncertainty`, `/preflight` (2 of this file's 3 AI-adjacent endpoints — the third, the main endpoint, correctly delegates to `risk_engine` and needs no LLM provenance) | **None** |

That is 4 files, 7 distinct AI-decision-producing endpoints, all with zero of the three evidence-chain
links Beta's own registry treats as the platform standard (`case_context()` provenance, an evidence/
validation check, a UI trust signal) — a materially larger gap than the single `compare_docs` instance
Beta found and fixed, because Beta's fork never walked this consumer layer.

---

## 3. What is already good in this domain (not re-litigated, cited as the reuse target)

- `shared/genome_validator.py::validate_dok_reference` (generalized by Program Beta specifically so a
  third caller beyond Genome/Compare could reuse it, per its own docstring) is the ready-made fix for
  §1.2's Evidence Graph and Case Commander gaps — **zero new mechanism needed, pure wiring**, same
  conclusion Beta reached for `compare_docs` itself.
- `services/case_pipeline.py`'s steps 7/8 (`_step_risk_snapshot`, `_step_copilot_preporuka`) prove the
  exact fix pattern needed for §1.1/§1.3 already works in this codebase: their docstrings document a prior
  independent GPT call being deleted in favor of calling `risk_engine` directly, with an explicit comment
  ("ne izmišljaj drugaciji broj") against ever re-introducing a second one.
- `case_dna.py::_compute_delta`/`_maybe_alert_require_review` (§1.8) are genuinely clean, single-owner
  decision mechanisms — the model to replicate for §1.3's "priority" gap, not a new design problem.

---

## 4. Prioritized findings (severity for `CANONICAL_MIGRATION_PLAN.md`-style triage)

| Rank | Finding | Decision type | # authors | Why this rank |
|---|---|---|---|---|
| 1 | "Next recommended action" — 6-7 independent generators, only 1 grounded | preporuka / next action | 6-7 | Largest fragmentation found in this fork; worse than Beta's own "most serious finding" (Strategy Engine, 4 generators) for the structurally identical defect class; 2 of the 8 producers (Case Commander's 3 endpoints, effectively) don't read Genome OR risk_engine at all despite both existing and being reusable |
| 2 | "Contradiction between evidence" — 4 independent generators, 2 with zero validation | kontradikcija | 4 | A decision type neither Alpha nor Beta inventoried at all in this domain; the fix (`validate_dok_reference`) already exists and is proven, making this pure-wiring severity-1-in-effort but severity-2-in-impact |
| 3 | "Case strength/readiness/risk" — 4 independent per-case numbers, 2 with zero reuse of any canonical signal | procesni rizik / spremnost | 4 | Escalates Alpha's "Clean, UI-perception note" verdict to a real dual-authorship-class problem once Matter Intel's own other two endpoints are included |
| 4 | Zero provenance/audit across 4 files, 7 endpoints | (cross-cutting) | — | Same class Beta fixed for `compare_docs`, now confirmed present at 7x the scale in the unwalked consumer layer |
| 5 | "Procedural warning" — 3 independent text lists | upozorenje | 3 | Same shape as #2, lower stakes (advisory prose, not a structured claim) |
| 6 | Evidence priority — 2 producers, different grain, never cross-checked | prioritet dokaza | 2 | Real but lower severity — different granularity means disagreement is plausible, not necessarily wrong; the gap is the absence of a warning when they diverge |
| 7 | Fact classification — one-way advisory only, not authoritative | klasifikacija činjenica | 2 (softened) | Already partially mitigated by Core Consolidation Sec 1.3; flagged for completeness, not urgent |
| 8 | Hardcoded `"confidence": "MEDIUM"`/`"HIGH"` labels in `predmet_istorija` inserts (`case_pipeline.py:407`, `matter_intel.py:596`) | (adjacent to Beta's confidence-model scope) | — | Same defect class as Beta's already-tracked "heuristic 0.85 fixed" finding (a design constant mislabeled as a measurement), lower priority than the ones above |

---

## Summary for parent

**Decisions in scope with a Gamma-listed name found in this domain: 10** (procesni rizik/case quality/
readiness combined as one row per the table's own grouping, kontradikcija, next action/preporuka, prioritet
dokaza, klasifikacija činjenica, značaj dokumenta, procesno upozorenje, promena rizika, promena prioriteta,
potreba za eskalaciju).

**Decisions with 2+ independent authors: 7 of 10** — case strength/readiness/risk (4 authors), contradiction
between evidence (4 authors), next recommended action (6-7 authors — the worst), evidence priority (2,
different grain), fact classification (2, softened by one-way injection), procedural warning (3), priority
change (effectively 0-grounded freestanding LLM opinion, not a "second author" of an existing computation
so much as a decision with no canonical author at all despite 3+ deterministic ingredients already existing
to ground it). **3 of 10 are clean, single-sourced**: document significance, risk-change delta, escalation
need — all three inside `case_dna.py` itself, all three good patterns to replicate.

**Most severe single finding:** the "next recommended action" fragmentation (§1.3) — up to 8 independent
producers across `case_dna.py`, `zadaci.py`, `case_intelligence.py`, `case_commander.py` (×3 endpoints), and
`case_pipeline.py`, of which `case_commander.py`'s three endpoints and `case_pipeline.py`'s `_step_
strategija` don't read Genome or the canonical `risk_engine` signal at all — despite `case_pipeline.py`
itself containing, five steps earlier in the same file, documented proof that this exact defect class was
already found and fixed once (steps 7/8). This is a materially worse instance of the same shape Program
Beta already called its own mission's most serious finding (Strategy Engine's 4-generator win-probability
split), found here specifically because this fork's mandate — walk Genome's actual downstream consumers,
not just Genome and its immediate siblings — was not covered by either prior mission's domain scoping.

**Second most severe:** "contradiction between evidence" (§1.2, 4 authors) — notable because the fix
mechanism (`genome_validator.py::validate_dok_reference`, already generalized by Program Beta for exactly
this kind of reuse) already exists and is proven in production for 2 of the 4 producers; extending it to
the other 2 (`evidence_graph.py`, `case_commander.py`) is wiring, not invention — the same "systemic fix
already exists, just not applied everywhere" pattern both prior missions independently converged on as the
dominant root cause in this codebase.
