# Program Gamma — Domain Inventory: Strategy Engine / Court Predictor / Legal Reasoning Engine

**Mission:** Masterprompt 003, "Canonical Decision Engine — Eliminate Entire Classes of Decision
Fragmentation." Read-only investigation. No code/git changes made. Lens: not code duplication (Program
Alpha), not AI-value non-determinism (Program Beta) — whether a BUSINESS OR LEGAL DECISION (a conclusion a
lawyer acts on: risk, next step, case readiness, warning, recommendation, strategic assessment, status,
fact classification, contradiction, escalation) is independently produced by more than one module.

**Scope:** `strategija.py` + `routers/strategija.py` (9 endpoints), `routers/court_predictor.py` (6
endpoints), `services/legal_reasoning_engine.py` + `routers/legal_reasoning.py`.

**Prior art read in full before writing this file** (not re-derived, only extended from the new lens):
`docs/architecture/BUSINESS_LOGIC_INVENTORY.md`, `SOURCE_OF_TRUTH_REGISTRY.md`, `DUPLICATE_DECISION_REPORT.md`
(Program Alpha), `AI_DECISION_GRAPH.md`, `EVIDENCE_CHAIN_REGISTRY.md`, `CONFIDENCE_MODEL_SPECIFICATION.md`,
`HALLUCINATION_ELIMINATION_REPORT.md`, `AI_REASONING_PIPELINE.md` (Program Beta),
`ARCHITECTURAL_DEBT_REGISTER.md` (both, esp. `PROGBETA-001`/`PROGBETA-003`), plus the 3 same-domain Beta
domain forks (`2026-08-04_beta_domain_legal_reasoning_strategy_INVENTORY.md`,
`..._genome_memory_firmbrain_INVENTORY.md`, `..._copilot_briefing_drafting_INVENTORY.md`), plus
`docs/architecture/VINDEX_2_1_ARCHITECTURE_ROADMAP.md`'s D20.1/D23 ("status predmeta" source-of-truth
principle, 2026-07-19/20 — pre-existing prior art on exactly this mission's "status/spremnost" question).

**What is NOT re-litigated here** (already diagnosed, cited not re-derived):
- **PROGBETA-001**: Strategy Engine's 4 independent litigation-percentage generators (litigation,
  sudija-v2 ×2, v2/analiza, kompletna-analiza's presuda step) — zero backend computation on any of them.
- **PROGBETA-003**: Strategy Engine's zero backend citation verification (all 9 endpoints, prompt-only).
- Court Predictor's `confidence_check` `nivo`/`procenat` split — already fixed by Program Alpha, confirmed
  as the reference deterministic-scoring pattern.

**What this file adds**: Beta's own domain fork explicitly scoped its Court Predictor read to
`confidence_check` only ("Court Predictor's already-fixed `confidence_check` (reference pattern)" — its
only mention of the file). **Court Predictor's other 5 endpoints (`/analiza`, `/battle-report`,
`/hearing-prep`, `/judge-profile`, `/argument-reputation`) were never audited by Program Beta at all.**
Reading them under the Gamma decision-lens finds the single largest new-instance count of this mission.

---

## Finding 1 (Critical, NEW) — "sledeći preporučeni korak / strategijska procena" has at least 8 independent, unreconciled generators, not the 4 Beta counted

Beta's `AI_REASONING_PIPELINE.md`/`DUPLICATE_DECISION_REPORT.md` framed the Strategy Engine problem as "4
independent litigation-percentage generators" — a confidence-number problem. Reframed as a **decision**
("what should this lawyer do / what is the strategic direction of this case"), the fragmentation is wider
and spans two entire routers, not one:

| # | Producer | Field(s) | Vocabulary | file:line |
|---|---|---|---|---|
| 1 | Strategy Engine `/kompletna-analiza` Synthesis (korak 6) | `strateski_stav` | `NASTAVITI_TUZBU \| PREGOVARATI_NAGODBU \| OJACATI_ODBRANU \| DOPUNITI_DOKUMENTACIJU \| ODUSTATI` | `strategija.py:590,600` |
| 2 | Strategy Engine `/kompletna-analiza` Synthesis, same call | `prioritetni_akcioni_plan.{hitno_crveno,vazno_zuto,preporuceno_zeleno}` | free-text action list | `strategija.py:591-595` |
| 3 | Strategy Engine `/kompletna-analiza` korak_2 (Due Diligence, internal) | `preporuka` | `POTPISATI \| PREGOVARATI \| ODBITI \| DOPUNITI \| PODNETI \| ISPRAVITI_PA_PODNETI \| NE_PODNETI \| PRIHVATITI` | `strategija.py:489-491,501,506` |
| 4 | Strategy Engine `/v2/analiza` | `sledeci_koraci[].{korak,rok,prioritet}` | free-text | `routers/strategija.py:363` |
| 5 | Court Predictor `/api/predictor/analiza` | `preporucena_strategija` | free-text | `routers/court_predictor.py:79,217` |
| 6 | Court Predictor `/api/predictor/battle-report` | "## PREPORUCENA STRATEGIJA" prose section | free-text | `routers/court_predictor.py:266-267` |
| 7 | Court Predictor `/api/predictor/judge-profile` | `strateska_preporuka` | free-text | `routers/court_predictor.py:742` |
| 8 | Court Predictor `/api/predictor/argument-reputation` | `preporuka` (per-argument) + `preporuceni_redosled` + `alternativni_argumenti` | free-text | `routers/court_predictor.py:581,587-588` |
| — | Case Genome (`routers/case_dna.py`, cross-reference, Beta's own domain) | `strategija.{primarni_cilj,rezervni_plan,scenariji}` + `strategija_osnova` + `upozorenja[]` + `nedostaje[]` | free-text | `case_dna.py:110-123` |
| — | Task Engine (`routers/zadaci.py::ai_analiziraj_predmet`, Beta's own domain) | task `{naziv,opis,prioritet}` suggestions | free-text | (Beta search/tasks fork) |

None of these 8 Strategy/Court-Predictor generators, nor Genome's `strategija`/`strategija_osnova`, nor Task
Engine's suggestions, **read any of the others' output**. Confirmed by grep: `strategija.py` and
`routers/strategija.py` contain **zero** references to `genome`/`case_dna`/`snaga_predmeta`, and
`court_predictor.py` never calls into `strategija.py`, `case_dna.py`, or `zadaci.py`. A lawyer who runs the
same case through, say, `/kompletna-analiza` and Court Predictor's `/battle-report` (both PRO features
explicitly marketed as complementary — not a hypothetical, adjacent-menu-items workflow) can receive a
`strateski_stav` of `NASTAVITI_TUZBU` from one and a "PREPORUCENA STRATEGIJA" prose section recommending
settlement from the other, with **zero system-level cross-check, warning, or reconciliation** anywhere in
the code path of either.

**Why this is worse than PROGBETA-001's framing, not a duplicate of it**: PROGBETA-001 is about a *number*
(win probability). This finding is about the *recommendation itself* — the thing a lawyer actually acts on.
A confidence number that disagrees is a data-quality problem; a strategic recommendation that disagrees
(`NASTAVITI_TUZBU` vs. a settlement recommendation, or Due Diligence's own `PREGOVARATI` vs. Synthesis's
`NASTAVITI_TUZBU` for the *same orchestrator run*, see Finding 2) is a decision a lawyer could relay to a
client. This is the mission's own named decision category ("preporuka za korisnika",
"sledeći preporučeni korak") in its most literal form.

**Root cause, per Program Alpha's own pattern taxonomy** (`DUPLICATE_DECISION_REPORT.md` Pattern A):
each PRO feature (Court Predictor, Strategy Engine) was built as an independently-shippable product surface
with its own prompt, not against a shared "recommendation" concept — structurally identical to Pattern A's
finding that "this codebase has no enforced convention... that would catch this at write-time."

**Recommended direction (not implemented, per this mission's read-only scope)**: this is squarely Phase 6
(canonical pipeline design) territory, same as PROGBETA-001 — a single `shared/strategic_recommendation.py`
concept that Genome, Strategy Engine's Synthesis step, and Court Predictor's advisory endpoints all *feed
into or read from*, rather than each independently asking an LLM "what should this lawyer do." Scoped
larger than PROGBETA-001 (8+ call sites across 2 routers + Genome + Task Engine, vs. PROGBETA-001's 4) —
not a same-session patch.

---

## Finding 2 (High, NEW) — the Synthesis step's own conflict-detection is exactly the LLM-executed-rule defect Program Beta already fixed for its sibling field, left unfixed here

`strategija.py:762-816`, `_ORK_SYNTHESIS_SYSTEM` (`strategija.py:576-600`). The Synthesis JSON schema has
two structurally identical fields:

- `sistemsko_upozorenje` — **fixed by Program Beta** (2026-08-04, same day): the code now counts
  `confidence == "NISKA"` across the 5 prior steps itself (`strategija.py:788-815`) and overwrites whatever
  the LLM returned. Documented in-code at lines 770-787 as the canonical example of "LLM rezonuje, platforma
  računa."
- `detektovani_konflikti` — **the sibling field the same fix did not touch.** The Synthesis prompt itself
  instructs (`strategija.py:582`): *"Identifikuj KONFLIKTE između koraka. Primeri: Revizor kaže SPREMAN ZA
  UPOTREBU ali Red Team identifikuje VISOKA ranjivost zbog iste klauzule; Due Diligence kaže NEPRIHVATLJIV
  ali Sudija pretpostavlja valjanost dokumenta."* This is a real, structurally checkable comparison — every
  one of the 5 prior steps returns a machine-readable categorical field (`korak1.ocena`,
  `korak2.ukupna_ocena`/`preporuka`, `korak4.ukupna_ranjivost`, `korak5.presuda.izreka`) — but the
  comparison is performed **entirely by the LLM's own prose judgment inside the same call that also
  produces `strateski_stav`**, not computed in code, unlike its sibling field 20 lines below it in the same
  function.

**Confirmed structurally checkable, concretely**: `korak1["ocena"]` (`SPREMAN ZA UPOTREBU`/`POTREBNE
IZMENE`/`NEUPOTREBLJIV`, `strategija.py:473,477`) and `korak2["preporuka"]` (`POTPISATI`/`PREGOVARATI`/
`ODBITI`/.../`NE_PODNETI`, `strategija.py:501,506`) and `korak4["ukupna_ranjivost"]` (`NISKA`/`SREDNJA`/
`VISOKA`, `strategija.py:547,551`) are all constrained-vocabulary enums returned as plain JSON keys already
present in `kontekst` when Synthesis is called (`strategija.py:765`) — a deterministic incompatibility check
(e.g., `korak1.ocena == "SPREMAN ZA UPOTREBU" and korak4.ukupna_ranjivost == "VISOKA"` → flag) is directly
buildable using the exact same pattern Program Beta just proved out one field over, in the same function,
same session boundary.

**Severity**: High, not Critical — `detektovani_konflikti` is advisory prose in an already-PRO-gated,
already-expensive (8 GPT-4o calls) feature, not a system-of-record write. But it is the most on-the-nose
possible instance of "eliminate the cause, not the symptom" being satisfied for one field and not its
neighbor in the same commit — exactly the kind of finding Program Alpha's Phase 7 regression check
("did the number of local decisions decrease?") is designed to catch, here caught one level down (within a
single mission's own fix, not across missions).

---

## Finding 3 (Medium, NEW) — "document readiness" is independently assessed twice inside the same orchestrator run, unreconciled with each other or with the standalone single-module endpoints

`/strategija/revizor` (standalone, `strategija.py:280-297,300-314`) asks the same question as
`/kompletna-analiza`'s korak_1 (`strategija.py:457-477`) — "is this document ready to use" — via **two
separate prompts, two separate GPT calls, two separate output shapes** (`_REVIZOR_SYSTEM` returns free
prose ending in "OCENA DOKUMENTA: SPREMAN ZA UPOTREBU / POTREBNE IZMENE / NEUPOTREBLJIV"; `_ORK_REVIZOR_SYSTEM`
returns the same 3-way enum as a JSON field `ocena`). Same pattern for Due Diligence:
`/strategija/due-diligence` (standalone, `_DUE_DILIGENCE_SYSTEM`, prose ending "Ukupna ocena: BEZBEDAN /
RIZIČAN / NEPRIHVATLJIV", `strategija.py:199`) vs. `/kompletna-analiza`'s korak_2 (`_ORK_DUE_DILIGENCE_SYSTEM`,
JSON `ukupna_ocena`, `strategija.py:502,506`).

If a lawyer runs a document through the standalone `/revizor` endpoint and later through
`/kompletna-analiza` (which re-runs the same conceptual check as its first step, on the same or similar
input), nothing guarantees — or even checks — that the two `ocena` values agree. Both are raw LLM
self-report with a differently-worded prompt for the identically-named decision.

**Distinction from `PROGBETA-001`**: PROGBETA-001 is 4 generators of *one number* (win probability) within
`strategija.py`. This is 2 generators each of *two different categorical decisions* (document readiness,
due-diligence risk category), and the duplication is specifically the standalone-endpoint-vs-orchestrator-
step pattern — the same underlying "F7.1 AI Pravni Revizor"/"F5.4 Due Diligence" logic was written twice
(once as its own endpoint, once inline in the orchestrator) rather than the orchestrator calling the
already-existing `pravni_revizor_sync`/`due_diligence_analiza_sync` functions and parsing their prose, or
the standalone endpoints being refactored to return the same JSON shape the orchestrator step now defines.
Root cause matches Program Alpha's Pattern A almost exactly (a second implementation written instead of a
call to the first), just inside a domain Alpha didn't flag because Alpha's own note on Strategy Engine's 9
endpoints (`BUSINESS_LOGIC_INVENTORY.md` #28) concluded "1 per module — clean, boilerplate repetition ≠
duplicated logic" — true for the *implementation*, but this finding is that the underlying *business
question* (is this document ready?) is asked twice with two independently-tunable prompts, which is a
decision-fragmentation problem Alpha's structural-duplication lens was not built to see.

---

## Finding 4 (Medium, answers the mission's explicit "spremnost predmeta" question) — Pravni Revizor's document readiness is NOT a duplicate of "status predmeta"/case readiness, but the mission's question surfaces a pre-existing, already-tracked architectural principle this domain was never checked against

Direct answer to the mission's question: **no, Strategy Engine's Pravni Revizor `ocena`
(`SPREMAN ZA UPOTREBU`/`POTREBNE IZMENE`/`NEUPOTREBLJIV`) does not duplicate Genome's `genome_kompletnost`
or Dashboard's `status`.** They answer genuinely different questions at different scopes:

- Pravni Revizor `ocena`: is *this one submitted document/draft* ready to file/use (a legal-quality
  judgment on a piece of text).
- Genome `genome_kompletnost` (`case_dna.py:126,147`): does the AI extraction have *enough source material*
  to be confident in its own output (`"visoka ako imas 3+ dokumenata sa jasnim cinjenicama"`) — a
  self-assessed data-sufficiency signal, not a legal-quality judgment.
- Dashboard `status` (`routers/dashboard.py:399-407`, confirmed by direct read): `zdrav`/`upozorenje`/
  `kriticno`, a pure projection of `services/risk_engine.py::calculate_procesni_rizik`'s `nivo` — single
  author, already canonical per `SOURCE_OF_TRUTH_REGISTRY.md`. Confirmed clean, not a new authorship
  conflict.

**However**, this question is not new to the codebase — `docs/architecture/VINDEX_2_1_ARCHITECTURE_ROADMAP.md`
already names this exact concern as a **standing architectural principle** (D20.1, 2026-07-20, founder-quoted:
*"Ako postoje dva: problem. Ako postoje tri: ozbiljan problem. Ako postoje četiri: arhitektonski dug koji će
se stalno vraćati."*) and D23, tracking "jedan izvor istine za status predmeta" with **3 already-named
candidates**: Kanban `_KANBAN_FAZE`, a proposed (unbuilt) lifecycle status, and Genome `genome_kompletnost`
as "TREĆI kandidat koji delimično preklapa 'koliko je predmet zreo/spreman'" — explicitly **Blocked** pending
an architectural decision (D23), not implemented either way.

**What this fork adds to that registry, not previously checked**: Strategy Engine and Court Predictor were
never evaluated against D20.1's own rule before this mission. They do **not** add a 4th candidate for
"status predmeta" (their outputs are per-document/per-analysis-run, not persisted per-predmet state, so
D20.1's specific "who is the one author of the predmet's status" question doesn't apply to them) — but
Finding 1 above (`strateski_stav` + the 7 sibling recommendation generators) is the exact same D20.1
pattern (*"jedan poslovni koncept = jedan izvor istine"*) applied to a different concept ("strateška
preporuka" instead of "status") that D20.1's own registry did not enumerate, because D20.1 was written
2026-07-19/20, before `/kompletna-analiza` (F10) and Court Predictor's advisory endpoints existed in their
current form. **Recommendation**: extend D20.1's registry with a 5th tracked concept — "jedan izvor istine
za stratešku preporuku" — using this file's Finding 1 table as the evidence base.

---

## Finding 5 (Medium, NEW) — Court Predictor's `boja`/`pouzdanost_profila` are LLM-self-graded categorical outputs Program Beta's own principle would flag, undiagnosed because Beta never read this file

`routers/court_predictor.py::argument_reputation` (`/api/predictor/argument-reputation`): the prompt
(`_ARG_REPUTATION_SYSTEM`, lines 573-595) instructs the model to derive `boja` from `uspesnost_procena`
by a stated rule ("boja: 'zelena' ako >=65, 'žuta' ako 35-64, 'crvena' ako <35"), but the response is
returned to the caller as `**rezultat` (`court_predictor.py:710`) — **the raw LLM JSON, unvalidated,
unrecomputed**. Nothing in the endpoint checks that `boja` actually matches the rule for the `uspesnost_procena`
the same call also returned. Identical pattern for `judge_profile`'s `pouzdanost_profila`
(`'visoka'`/`'srednja'`/`'niska'`, stated rule "10+ odluka"/"5-9"/"<5", `court_predictor.py:743,747`) against
`ukupno_odluka_analizirano` — also returned raw, unchecked.

**This is exactly the defect class Program Beta named and fixed once** (`/kompletna-analiza`'s
`sistemsko_upozorenje`, `AI_REASONING_PIPELINE.md` step 5, `CONFIDENCE_MODEL_SPECIFICATION.md`'s governing
rule: "ne izmišlja 'confidence %' ili drugu vrednost koja se stvarno ne računa nigde") — but Program Beta's
own Confidence Model registry never lists these two fields, because its domain fork's Court Predictor
coverage was scoped to `confidence_check` only (confirmed: `2026-08-04_beta_domain_legal_reasoning_strategy_
INVENTORY.md` names `confidence_check` as the file's sole Court Predictor reference). Both are cheap,
mechanical fixes (a 2-line `if uspesnost_procena >= 65: boja = "zelena"` override after the JSON parse,
same shape as `sistemsko_upozorenje`'s fix) — not a design question, unlike Finding 1/3.

---

## Finding 6 (Low, forward-looking, not a live duplicate) — Legal Reasoning Engine's `Claim` nodes are explicitly, deliberately not wired to anything yet — confirmed non-issue today, real risk at Phase 1+

`services/legal_reasoning_engine.py:1-23` states the founder's own binding Phase 0 constraint verbatim:
*"Genome's argumenti_za/argumenti_protiv/kontradikcije fields are NOT touched by this module — that
migration is explicitly Phase 1, not Phase 0."* Confirmed by reading `routers/legal_reasoning.py` in full:
manual-trigger-only (`POST .../reasoning-graph/generate`), zero automatic trigger, zero downstream consumer
reads `reasoning_graph`/`reasoning_nodes`/`reasoning_edges` anywhere else in the codebase (grep confirms no
other router or service imports from `legal_reasoning_engine.py` besides its own router). LRE's `Claim`
node type (`services/legal_reasoning_engine.py:392`) is conceptually adjacent to Strategy Engine's
`strateski_stav` and Genome's `strategija` (all three are "a legal conclusion reached from case facts"),
but produces zero user-facing text by explicit design and has no live consumer — **not** a current instance
of Finding 1's pattern.

**Why this is worth recording rather than skipping**: Finding 1 already shows this codebase adds
recommendation-producing surfaces (Court Predictor's 5 non-`confidence_check` endpoints, `/kompletna-analiza`
F10) without checking for an existing canonical source first. LRE is explicitly the module the founder's own
definition (`services/legal_reasoning_engine.py:7-13`) names as the intended "centralni sloj između Case
Genome i svih viših AI modula" for exactly this kind of conclusion. **When Phase 1 wires LRE's `Claim`
nodes to a consumer, the correct order of operations is: LRE becomes the canonical source Strategy
Engine/Court Predictor's recommendation endpoints read from — not a 9th independent generator alongside
Finding 1's 8.** This is the single most important forward-looking guardrail this fork can hand to whoever
scopes LRE Phase 1.

---

## Cross-reference: does `strateski_stav` conflict with Genome, Task Engine, or Copilot? (mission's literal question, answered directly)

- **Genome's own `strategija` field** — yes, conflict is structurally possible and unchecked (Finding 1).
  Zero grep hits for genome/case_dna in either `strategija.py` or `routers/strategija.py` confirms
  `strateski_stav` is generated with zero knowledge Genome's `strategija_osnova`/`strategija.primarni_cilj`
  exists for the same case.
- **Task Engine's suggestions** (`zadaci.py::ai_analiziraj_predmet`) — lower risk than Genome. Per Beta's
  own search/tasks domain fork, Task Engine's suggestions are deliberately narrow and threshold-derived
  (inactivity, unbilled amount, missing documents) — operationally different in kind from `strateski_stav`'s
  case-direction enum (file-suit vs. settle vs. strengthen-defense). Overlap is more plausible at the
  `prioritetni_akcioni_plan.hitno_crveno`/`vazno_zuto` level (Finding 1, row 2), which is closer in shape to
  a task list, but still zero code path connects them.
- **Copilot's advice** (`main.py::ask_agent`) — no conflict mechanism exists because no data path exists:
  Copilot answers point-in-time legal questions from the indexed corpus (per Beta's Copilot/Briefing/Drafting
  fork, its evidence chain is the platform's strongest) and does not read or write `strateski_stav` or any
  Strategy Engine output. Not a duplicate in the authorship sense — simply two unconnected surfaces, lower
  risk than Genome specifically because Copilot is Q&A-shaped, not recommendation-shaped, for any given call.

---

## Severity ranking (this fork's own findings only, for the parent's cross-fork prioritization)

| Rank | Finding | Why this rank |
|---|---|---|
| 1 | Finding 1 — 8 independent "next step / strategic direction" generators | Largest new-instance count this mission; literal match to the mission's own named decision categories; spans 2 routers + Genome + Task Engine |
| 2 | Finding 2 — `detektovani_konflikti` left LLM-executed while sibling field `sistemsko_upozorenje` was just fixed in the same function, same day | Cheapest fix of anything in this file (mirrors an already-proven pattern 20 lines away); highest "should never have been possible" signal |
| 3 | Finding 3 — document-readiness/due-diligence-risk asked twice (standalone vs. orchestrator step) | Real, same root cause as Alpha's Pattern A, narrower blast radius than Finding 1 |
| 4 | Finding 5 — Court Predictor `boja`/`pouzdanost_profila` LLM-self-graded despite a stated, checkable rule | Mechanical fix, but undiagnosed because Beta's own Court Predictor coverage was incomplete — worth flagging as a process gap, not just a code gap |
| 5 | Finding 4 — D20.1/D23 registry should gain a 5th tracked concept ("strateška preporuka") | Not itself a new defect — a registry-completeness recommendation |
| 6 | Finding 6 — LRE `Claim` nodes, forward-looking guardrail | Zero live impact today; highest-leverage preventive note for Phase 1 scoping |

---

## Summary for parent

**New decision-fragmentation instances found beyond Program Beta's existing diagnosis (`PROGBETA-001`,
`PROGBETA-003`): 6 findings**, the largest being **Finding 1: at least 8 independent, unreconciled
generators of "what should this lawyer do / what is this case's strategic direction"** — a materially wider
instance of the exact pattern Beta named for confidence numbers (PROGBETA-001's "4 independent litigation-
percentage generators"), because the new lens asks about the *recommendation itself*, not just the *number*
attached to it, and includes Court Predictor's 5 non-`confidence_check` endpoints, which Program Beta's own
domain fork never read (it scoped Court Predictor to `confidence_check` only).

**Most severe finding**: Finding 1. It is the mission's own named decision category
("preporuka za korisnika", "sledeći preporučeni korak", "strategijska procena") found fragmented across 8+
independently-authored call sites in the exact two routers this fork was scoped to read, none of which
consult each other, none of which consult Genome's or Task Engine's independently-authored equivalents
either. Finding 2 is a close second by a different measure — not the widest blast radius, but the single
clearest "this should have been impossible" instance, since the fix for its sibling field was written in
this exact function, this exact mission day, and simply didn't extend one field further.

**Direct answers to the mission's two explicit questions**:
1. *Does `strateski_stav` conflict with or duplicate any recommendation produced elsewhere?* Yes — Genome's
   own `strategija`/`strategija_osnova` (zero shared code path, confirmed by grep), and 7 further generators
   within Strategy Engine/Court Predictor itself (Finding 1). Task Engine and Copilot are lower-risk but
   still structurally unconnected.
2. *Does "status predmeta"/"spremnost predmeta" get computed independently by Pravni Revizor vs. elsewhere?*
   No — Pravni Revizor's `ocena` is a per-document judgment, genuinely distinct in scope from Genome's
   `genome_kompletnost` (data-sufficiency) and Dashboard's `status` (risk-engine projection, already
   canonical). But the mission's question surfaces that `VINDEX_2_1_ARCHITECTURE_ROADMAP.md`'s D20.1/D23
   already tracks "status predmeta" as a 3-candidate open architectural question (pre-dating this mission,
   2026-07-19/20) — this domain doesn't add a 4th candidate to *that* registry, but Finding 1 shows the same
   D20.1 principle applies, unaddressed, to a *different* concept ("strateška preporuka") the registry never
   named.
