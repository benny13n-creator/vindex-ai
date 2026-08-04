# Program Beta — Domain Inventory: Legal Reasoning Engine / Strategy Engine / Court Predictor

Read-only investigation. No code/git changes made. All claims verified against current code
(`strategija.py`, `routers/strategija.py`, `routers/court_predictor.py`, `shared/genome_validator.py`,
`services/legal_reasoning_engine.py`, `docs/architecture/LEGAL_REASONING_ARCHITECTURE.md`).

## AI operation inventory — Strategy Engine (9 endpoints, `routers/strategija.py` + `strategija.py`)

| Endpoint | Function | Model/temp | RAG/data source | Confidence/percentage | Provenance |
|---|---|---|---|---|---|
| `POST /strategija/red-team` | `red_team_analiza_sync` | gpt-4o / 0.3 | `_fetch_praksa_ctx` (Pinecone, k=3) | Qualitative only: "Ukupna ranjivost: NISKA/SREDNJA/VISOKA", self-reported prose, no backend check | `case_context()` + `log_action` |
| `POST /strategija/litigation` | `litigation_simulator_sync` | gpt-4o / 0.2 | `_fetch_praksa_ctx` (k=3) | **Raw LLM prose "Verovatnoća uspeha tužioca: X%"** — RAG hits fetched but never counted/scored, purely prompt-calibrated ("VAŽNO — KALIBRACIJA PROCENATA" instructs the model, nothing in code checks compliance) | `case_context()` + `log_action` |
| `POST /strategija/sudija` | `ai_judge_mode_sync` | gpt-4o / 0.1 | `_fetch_praksa_ctx` (k=3) | Qualitative only: "Preliminarni stav" enum, no percentage | `case_context()` + `log_action` |
| `POST /strategija/due-diligence` | `due_diligence_analiza_sync` | gpt-4o / 0.1 | `_fetch_zakon_ctx` (k=4) | Qualitative: "BEZBEDAN/RIZIČAN/NEPRIHVATLJIV", self-reported | `case_context()` + `log_action` |
| `POST /strategija/revizor` | `pravni_revizor_sync` | gpt-4o / 0.15 | **None** — no RAG call at all | Qualitative self-reported ocena | `case_context()` + `log_action` |
| `POST /strategija/witness` | `witness_analyzer_sync` | gpt-4o / 0.2 | None | Qualitative "OCENA POUZDANOSTI", self-reported | `case_context()` + `log_action` |
| `POST /strategija/sudija-v2` | `ai_judge_v2_sync` (3 chained calls: tužilac→branilac→presuda) | gpt-4o / 0.3, 0.3, 0.1 | None | **Two independent raw LLM percentages**: "PROCENA USPEHA TUŽBE: X%" and "PROCENA ODBRANE: X%", produced by two separate unreconciled prompts | `case_context()` + `log_action` |
| `POST /strategija/kompletna-analiza` (F10 orchestrator) | `orkestrator_kompletna_analiza_sync` (8 GPT-4o calls) | gpt-4o, varies 0.1-0.3 | **None** — no `_fetch_praksa_ctx`/`_fetch_zakon_ctx` call anywhere in the 6-step chain | Prompt-level `"confidence": VISOKA\|SREDNJA\|NISKA` enum per step (schema-constrained, not code-validated) + **raw LLM int `"procena_uspeha_tuzilac": 50`** in the presuda step + orchestrator-level `"opsta_confidence"` whose ≥2-steps-NISKA aggregation rule is executed *by the Synthesis LLM call itself*, not computed in code | `case_context()` + `log_action` |
| `POST /strategija/v2/analiza` | inline in router, `_V2_SYSTEM` | gpt-4o / 0.1, `response_format=json_object` | **None** — no RAG fetch in this endpoint | **Raw LLM int `procena_uspeha.procenat` (0-100)**, fully isolated from every other percentage source in this domain | `case_context()` + `log_action` |

**Every one of the 9 endpoints returns raw GPT prose or GPT-authored JSON directly as `rezultat`/`analiza`
with no post-hoc structural separation of FACTS vs. INFERENCE vs. RECOMMENDATION** — response bodies are
either a single prose string keyed `"rezultat"`, or (v2/analiza, kompletna-analiza) a JSON object whose
field *names* imply structure (`kljucni_rizici`, `sledeci_koraci`) but whose *content* is undifferentiated
model prose per field, not labeled by evidentiary status.

## Confidence audit — the core finding

**Four independent, unreconciled percentage generators exist for what is conceptually one value
("probability this case succeeds"), none of which talk to each other or to any shared score:**
1. `/litigation`'s "Verovatnoća uspeha tužioca: X%" (raw prose)
2. `/sudija-v2`'s "PROCENA USPEHA TUŽBE: X%" / "PROCENA ODBRANE: X%" (raw prose, two more numbers)
3. `/v2/analiza`'s `procena_uspeha.procenat` (raw JSON int)
4. `/kompletna-analiza`'s `procena_uspeha_tuzilac` (raw JSON int, step 5 of the orchestrator)

If a lawyer ran the same case description through more than one of these four endpoints, they could see
four materially different, arbitrarily-precise percentages for the same underlying case, with no code
anywhere reconciling them. This is the same defect class Program Alpha fixed in Court Predictor
(`KEYSTONE-004`/K-3) — confirmed still present, and confirmed **worse** than Court Predictor's pre-fix
state: Court Predictor had one percentage generator with a "two authors" problem (level vs. number); this
domain has **four independently-authored percentage generators**, all still fully LLM-guessed, zero
backend computation on any of them.

## Court Predictor's fix (already implemented, verified as the reusable reference pattern)

`routers/court_predictor.py::confidence_check` (lines ~1020-1219): `_calc_confidence_nivo()` scores 0-9
from real countable signals — RAG hits (≥15→+3/≥5→+2), VKS hits (≥5→+3/≥2→+1), firm history from
`case_patterns` table (uzoraka≥5→+2/>0→+1), evidence count (≥4→+1) — then `_procenat_iz_score()` derives
BOTH the qualitative level (NISKO/SREDNJE/VISOKO) AND a 20-80%-bounded percentage from that *same* score.
The GPT call (`_pozovi_confidence_api`, temp 0.2) is scoped to free-text `razlog_kratko`/`kljucni_rizik`
only, explicitly instructed "NE navodi procenat ni broj" — the model cannot touch the number.

## Is this pattern reusable for Strategy Engine this session? — No, not as a local patch

Signal availability comparison:
- **RAG hit count**: Strategy Engine already fetches this for `/litigation`, `/red-team`, `/sudija`
  (`_fetch_praksa_ctx`, k=3) but never counts/scores it — a real, cheap, currently-unused signal.
  `/due-diligence` fetches a *different* RAG context (`_fetch_zakon_ctx`, statutes not case law). `/revizor`,
  `/witness`, `/sudija-v2`, `/kompletna-analiza`, `/v2/analiza` fetch **no RAG context at all today**.
- **VKS-specific hit count**: Court Predictor calls a separate VKS-scoped search Strategy Engine does not
  currently call anywhere in this domain.
- **`case_patterns` firm win/loss history**: confirmed via grep — used by `court_predictor.py`,
  `learning_engine.py`, `case_intelligence.py`, `cio.py`, `benchmarking.py`, `knowledge_hygiene.py`. **Never
  queried anywhere in `strategija.py` or `routers/strategija.py`.** `StrategijaRequest` does carry
  `tip_postupka`, which is exactly the dispute-type key `case_patterns` is scoped by — plausible to wire,
  not currently wired.
- **Evidence count**: Court Predictor's `ConfidenceCheckRequest` has an explicit `dokazi` field.
  `StrategijaRequest`/`StrategijaV2Request`/`OrkestratorRequest` have no equivalent structured evidence
  field — only free-text `tekst`/`opis_predmeta`. No evidence-count signal exists today without a request
  schema change.

**Conclusion**: a real deterministic score is buildable (RAG hits + a new VKS search call + a new
`case_patterns` query keyed on `tip_postupka`), but it does not exist today, and it would need to be wired
into **four separate call sites**, not one — a materially larger change than the single-function Court
Predictor fix. This confirms, rather than refutes, Program Alpha's prior deferral: this is a Phase 6
(canonical pipeline design) + Phase 7 (bounded implementation) item, not a same-session local patch. Per
this mission's own rule (prove a systemic fix isn't reasonably achievable before any local patch), the
right target is **one shared deterministic litigation-confidence scorer** (a `shared/` module function
analogous to `_calc_confidence_nivo`/`_procenat_iz_score`) that all four call sites invoke, not four
separate prompt patches.

## Legal Reasoning Engine — SOURCE-n/FACT-n citation grounding

Verified in `docs/architecture/LEGAL_REASONING_ARCHITECTURE.md` + `services/legal_reasoning_engine.py` +
`routers/legal_reasoning.py`: citations (`SOURCE-n`) are built exclusively from
`retrieve_documents()`'s own `retrieval_meta["izvori"]` — a deduplicated, identity-based
`{zakon, clan, score}` list of actually-retrieved statute hits. A citation GPT invents that isn't in that
list has no valid `SOURCE-n` to attach to and is dropped before reaching the graph. This is a genuine,
proven, live deterministic-grounding mechanism (fixed 2026-07-23), directly analogous to Drafting's
`quality_gate` citation verification.

**Critical gap: this mechanism is wired only into Drafting** (`routers/drafting.py`, `templates/podnesci.py`)
— confirmed by grep, zero references in `strategija.py`, `routers/strategija.py`, or
`routers/court_predictor.py`. Strategy Engine's "zakonski osnov" citations (member/article numbers
appearing throughout red_team, due_diligence, revizor, and all 6 orchestrator steps) rely **purely on
prompt instructions** ("ANTI-HALUCINACIJA PRAVILA: citiraj iz sopstvenog stručnog znanja... to NIJE
halucinacija, to je tvoja stručnost") with **zero backend verification against the indexed corpus**. This
is a real, live hallucination vector: an invented "čl. 205 ZUP" or a fabricated "presuda" reference can
reach the user unchecked — exactly the class of defect Drafting's `quality_gate` and LRE's `SOURCE-n`
already solve elsewhere in the codebase, just not connected here.

## `shared/genome_validator.py::compute_snaga_score` — second confirmed deterministic pattern

Verified: baseline 50 + net impact of already-extracted `snaga_faktori` (case-specific, not requested
fresh from the LLM), clamped `[0,100]`, category (jaka/srednja/slaba) derived from the same number. Built
2026-07-18 specifically to replace a prior GPT-self-reported percentage that anchored identically at 65%
across dramatically different test cases (Reality Validation batch finding). Confirms the general
principle both fixes share: **compute the number from already-extracted, case-specific factors; never ask
the LLM for the number directly.**

## Hallucination vectors — prioritized

1. **[Highest]** Strategy Engine's 4 independent ungrounded percentage generators (see Confidence audit
   above) — systemic fix is one shared scorer function, not 4 prompt patches. Requires new signal wiring
   (VKS search call, `case_patterns` query) not currently present in this domain — Phase 6/7 scope.
2. **[High]** Strategy Engine legal citations have zero backend verification against the indexed corpus,
   unlike Drafting (`quality_gate`) and LRE (`SOURCE-n`) — both proven mechanisms exist and are reusable;
   this is a genuine "systemic solution already exists, wire it in, don't invent a new one" case.
3. **[Medium]** `/kompletna-analiza`'s cross-step confidence aggregation (`sistemsko_upozorenje` trigger
   when ≥2 steps report `confidence: NISKA`) is specified as a hard rule in the Synthesis prompt but
   **executed by the LLM, not computed in code** — the rule could silently not fire on a technically-correct
   input the model reasons about differently than the rule states. A cheap deterministic post-check
   (count `confidence == "NISKA"` across the 5 prior JSON results in code, before/independent of the
   Synthesis call) would remove this from LLM discretion entirely.
4. **[Low]** No endpoint in this domain labels output as FACT vs. INFERENCE vs. RECOMMENDATION — all 9 are
   undifferentiated prose or prose-in-JSON-shaped-fields. Lower priority than #1/#2 because none of these
   9 endpoints write directly to a system-of-record table the way Copilot's akcija handlers do (per the
   sibling Copilot/Briefing/Drafting inventory) — the immediate risk is a misread lawyer, not silent data
   corruption.

## Summary for parent

**Operations inventoried**: 9 Strategy Engine endpoints (red_team, litigation, sudija, due_diligence,
revizor, witness, sudija_v2, kompletna_analiza [8 internal GPT-4o calls], v2/analiza) + Court Predictor's
already-fixed `confidence_check` (reference pattern) + LRE's `SOURCE-n` mechanism + `compute_snaga_score`.

**Non-deterministic confidence/percentage values found**: **4 independent raw-LLM percentage generators**
in Strategy Engine (litigation, sudija-v2 ×2, v2/analiza, kompletna-analiza's presuda step) — none
cross-checked against each other or any real signal. This is the domain's single highest-priority finding,
confirmed fresh against current code and confirmed **worse** than Court Predictor's pre-fix state (4
unreconciled authors vs. Court Predictor's 2).

**Evidence chain gaps**: Strategy Engine's legal citations (member/article numbers) have zero backend
verification against the indexed corpus — reusable fixes already exist elsewhere (Drafting's
`quality_gate`, LRE's `SOURCE-n`) but are not wired into this domain.

**Can the litigation percentage be fixed with the Court Predictor pattern this session?** **No.** The
pattern (deterministic score → both level and %) is directly reusable in principle, but Strategy Engine is
currently missing 2 of Court Predictor's 4 input signals entirely (VKS-specific search, `case_patterns`
firm history — RAG hit count is the only signal already present but unused), and the ungrounded-percentage
bug exists independently in **4 separate call sites**, not 1. A same-session local patch to `/litigation`
alone would leave 3 other unreconciled percentage generators in place — exactly the kind of partial fix
Program Beta's addendum rule is designed to prevent. Recommend Phase 6 design a single shared
litigation-confidence scorer consumed by all 4 sites, scoped as a bounded Phase 7 implementation item, not
a same-session patch.
