# Mission Keystone — Phase 5: AI Quality Validation Investigation

**Date:** 2026-08-04. **Method:** direct code reading (prompts, response-parsing, confidence/validation
logic) for every major AI feature. Read-only — no fixes applied here.

**Central question:** "Ako AI nije siguran, da li sistem to priznaje, ili proizvodi lažnu sigurnost?"
**Answer: it depends entirely on which feature you ask.** The system is NOT uniformly honest or
uniformly overconfident — it ranges from genuinely best-practice engineering to genuinely risky raw
LLM self-report, feature by feature. This is the headline finding of this investigation.

---

## Wrapper level — `shared/ai_client.py`'s "Prompt Guard"

**Naming risk, not a functional bug**: the global patch (`_patch_prompt_guard()`) that intercepts every
`Completions.create`/`AsyncCompletions.create` call is a **prompt-injection defense** (SEC-003,
`security/prompt_guard.py::analyze`, blocks on `risk_score` above a threshold) — it inspects
*incoming* user-role text for injection attacks, and separately captures AI Provenance (Mission
Atlas). **It does nothing to check outgoing model responses for fabricated content.** A reader who
assumes "every AI call passes through Prompt Guard" therefore might wrongly assume hallucination
guarding is universal and structural — it is not. There is no wrapper-level hallucination check at
all; every hallucination-guard mechanism found below is feature-specific, not centralized.

---

## Core RAG Q&A — `main.py::ask_agent` (Copilot's `pravno_pitanje` delegates here)

**Verdict: Honest-about-uncertainty — the strongest example in the codebase.**

Explicitly named in its own docstring "Hallucination-free confidence-gated pipeline v3.0" (`main.py:3136`).
1. **Hallucination guard**: prompt rule "NIKADA ne parafraziraš zakonski tekst — citiraj doslovno ili ne
   citiraj uopšte" (`main.py:1437`); "citiraj ISKLJUČIVO članove navedene u bloku 'DOSTUPNI ZAKONI'... NE
   citiraj članove iz opšteg znanja" (`main.py:2321-2322`, `3548`); case-law citation line must be
   omitted entirely if no matching context entry exists — "ZABRANJENO: navoditi raspon ili praksu iz
   sopstvenog znanja ako nije u kontekstu" (`main.py:1780`).
2. **Confidence handling**: retrieval confidence (`HIGH`/`MEDIUM`/`LOW`) computed independently in
   `app/services/retrieve.py` from actual vector similarity score (`top_score`), not from the LLM.
3. **Source attribution**: `retrieve.py::_build_izvori` (`:700`) extracts deduplicated source refs
   directly from real Pinecone matches; `_build_match_breakdown` (`:721`) is an "Explainable Retrieval"
   layer stating *why* each source was surfaced.
4. **Missing evidence detection**: `LOW` confidence triggers an explicit refusal path
   (`main.py:3255-3264`, "LOW confidence refusal" logged), not a normal-looking confident answer.
5. **Uncertainty propagation**: confidence band gates the entire response — `MEDIUM` still narrows
   behavior (`main.py:3348`), `confidence`/`confidence_detail`/`izvori` are all returned alongside the
   answer (`main.py:3513-3515`), not discarded after use.

One real gap: embedding failure degrades to a clean `LOW`/empty-izvori result (`retrieve.py:1659-1663`,
fail-soft, not a crash) — good — but this was only made fail-soft in a prior session (CELINA 1 comment,
`retrieve.py:1648-1653`); confirms the design intent is deliberate, not accidental.

---

## Legal Document Analysis — `analiza/validator.py` (schema seen at `main.py:3640-3693`)

**Verdict: Honest-about-uncertainty — best grounding ENFORCEMENT (code-checked, not just prompt-requested).**

- `validate_clause_excerpts()` (`analiza/validator.py:142`) checks every `clause_excerpt` is an actual
  substring of the real segmented document — catches a fabricated quote structurally, not by asking the
  model to self-police.
- `validate_clause_refs()` (`:186`) checks every `clause_ref` actually exists among the segments sent to
  the model — catches an invented reference ID.
- `validate_law_refs()` (`:289`) checks cited laws against a known list (soft flag if unrecognized,
  reused directly by `shared/genome_validator.py`, see below — confirmed no duplicate implementation).
- Prompt itself is explicit: "NE izmišljaj ID-jeve koji nisu u segmentima" (`main.py:3697`), "Ako ne
  možeš da citiraš doslovno — postavi null" (`main.py:3699`, i.e. explicitly permits admitting nothing
  rather than fabricating).
- **Gap**: the per-finding `"confidence": <0-100>` value itself (`main.py:3666`) is still raw LLM
  self-report, not independently computed — the excerpt/ref/law-name dimensions are grounded, the
  numeric confidence dimension is not. Smaller gap than everywhere else in this report because the
  content it's attached to (excerpt, ref) is independently verified even if the number isn't.

---

## Case Genome — `routers/case_dna.py` + `shared/genome_validator.py`

**Verdict: Honest-about-uncertainty.**

- `compute_snaga_score()` (`genome_validator.py:173`) computes `snaga_predmeta_procent` (case strength
  %) **deterministically from `snaga_faktori`**, explicitly NOT from the LLM's own self-reported number —
  its own docstring documents WHY: a Reality Validation batch (2026-07-18, 6 synthetic cases) found all
  6 returned an *identical* 65%/"srednja" regardless of wildly different content, traced to a literal
  numeric example (`"snaga_predmeta_procent": 65`) in the system prompt that GPT anchored on/copied — a
  real, previously-proven prompt-anchoring bug, fixed by moving computation to the backend.
- `verify_genome()` (`:262`) hard-flags: evidence-ranking entries (`dokazi_rang`) referencing a document
  that doesn't exist among the case's real documents (`:80`); contradiction locations (`kontradikcije`)
  referencing a `DOK-XX` number that doesn't exist (`:95`); soft-flags unrecognized law citations and
  article numbers outside a plausible range for the law type (catches an obviously invented article like
  "član 5000", `:138-170`).
- **Uncertainty propagation confirmed**: `genome_kompletnost == "niska"` (low evidence completeness)
  applies an explicit, visible `-15` penalty factor to the strength score (`:198-203`) — thin evidence
  measurably lowers the number instead of the model producing a confident score regardless of input
  volume.
- Decision gate: `require_review` (hard flags) / `approve_with_warning` (soft flags) / `approve` — genome
  still saves in all three cases (advisory, not blocking), but the flag is visible and durable.

---

## Court Predictor — `routers/court_predictor.py`

**Verdict: Partially-honest — internally inconsistent.**

- `confidence_check` endpoint's `nivo` (VISOKO/SREDNJE/NISKO, `:1085` `_calc_confidence_nivo`) is **100%
  deterministically computed** from real signals: RAG hit count, VKS Supreme Court precedent count,
  firm's own historical win-rate from `case_patterns`, and evidence count (`:1020-1082`) — genuinely
  evidence-grounded, not LLM self-report.
- But the same endpoint's `procenat` (the specific percentage shown alongside `nivo`) is raw GPT
  self-report (`:1169-1195`, defaults to 50 on failure, otherwise whatever the model returns, clamped to
  [0,100]) — **not cross-checked against `nivo` for consistency.** A lawyer could see "NISKO poverenje"
  (low confidence) displayed next to e.g. "78%" with no code path preventing that contradiction.
- `prediktuj_ishod`'s own prompt (`:66-83`) is well-designed for false-precision avoidance: forces a
  `procenat_min`/`procenat_max` **range** rather than a point value, explicit rule "Nikad ne garantuj
  ishod — uvek navedi procenat KAO OPSEG i objasni nesigurnost" — but the range itself is still
  fundamentally unverified LLM self-report underneath the improved presentation.

---

## Strategy Engine — `strategija.py` (6 GPT-calling modules via `routers/strategija.py`)

**Verdict: Overconfident-risk — the single riskiest feature found in this investigation.**

`red_team_analiza_sync`, `litigation_simulator_sync`, `ai_judge_mode_sync`, `due_diligence_analiza_sync`,
`pravni_revizor_sync`, `witness_analyzer_sync` (`strategija.py:204-315` and beyond) all return **raw,
unstructured GPT text** (`return (resp.choices[0].message.content or "").strip()`) with **zero backend
confidence computation, zero post-hoc validation, zero citation-grounding check** anywhere in
`routers/strategija.py` or `strategija.py` (confirmed: `grep -i "confidence|pouzdan|halucinacij"` on
`routers/strategija.py` returns nothing).

The only honesty mechanism here is **prompt instruction, unverified in code**:
`_LITIGATION_SYSTEM` (`strategija.py:124-149`) does instruct "Ako nemaš dovoljno podataka za pouzdan
procenat — navedi 'Nedovoljno podataka za pouzdanu procenu'" and "NIKADA nemoj navesti procenat bez
obrazloženja ZAŠTO je toliki", and `_DUE_DILIGENCE_SYSTEM` (`:171`) instructs "nikada ne izmišljaj
članove" — but nothing in the code checks whether the model actually followed these instructions. No
`verify_genome`-style flag, no `validate_law_refs`-style law check (unlike Genome, which reuses that
exact function), no citation-verification (unlike Drafting's `quality_gate`).

**Litigation Simulator's "Verovatnoća uspeha tužioca: X%"** is therefore the single least-grounded
high-stakes number in the entire application — a lawyer can be shown "73% šanse za uspeh" that is 100%
the model's own self-assessment, with no independent computation or validation behind it, on arguably the
single question ("what are my odds of winning") a lawyer using this product cares about most. Every other
percentage-producing feature in this app (Genome's `snaga_score`, Court Predictor's `nivo`, Drafting's
`confidence_score`) has *some* independently-computed or independently-verified component; Strategy
Engine has none.

---

## Evidence Classification — `routers/evidence.py`

**Verdict: Overconfident-risk, lower stakes than Strategy Engine.**

The classification schema (`_CLASSIFY_SYSTEM`, `:26-50`) requests `tip_dokaza`, `pravni_elementi`,
`ai_tags`, `kljucne_cinjenice` — **no confidence field at all**, and no post-hoc validation of any of
these against the source document text (`grep -i "confidence|pouzdan"` on this file: zero matches).
The classification result feeds into Genome's `dokazi_rang` (Genome validates that the *document name*
referenced actually exists, per above — but never validates that the *classification itself*
(`tip_dokaza`) is correct). Lower-stakes than Strategy Engine because a wrong evidence-type tag is more
visibly/cheaply correctable by a lawyer glancing at the document than a fabricated win-probability
percentage is.

---

## Drafting — `services/quality_gate.py` (feeds `routers/drafting.py::_stage_draft_for_review`)

**Verdict: Honest-about-uncertainty for the citation-hallucination dimension specifically.**

`evaluate_draft_quality()` (`:66`) computes `confidence_score = 0.6 * citation_score + 0.4 *
completeness_score`. Critically, `citation_score` is **not** LLM self-report — every "Član N" citation
found in the AI-generated draft is verified against the actual indexed legal corpus via a real RAG
lookup (`_verify_citation` → `app.services.retrieve._direktan_fetch_clana`, `:50-57`) — a genuine,
code-enforced hallucination check for legal citations specifically, mirroring the same principle as
Genome's `compute_snaga_score`. `completeness_score` is a weaker keyword heuristic, but the module's own
docstring is transparent about this ("lakša ali POŠTENA provera... transparentno nazvana
'citation_score', ne predstavljena kao nešto šire" — `:16-19`). Gated: only drafts scoring
`>= _APPROVAL_CONFIDENCE_THRESHOLD` (0.85, `routers/drafting.py:1076`) can be lawyer-approved/promoted.

---

## Copilot — `routers/copilot.py`

No confidence-handling code of its own — it's a thin dispatcher that delegates actual AI work to
`ask_agent` (`pravno_pitanje`), `strategija.py` (its strategy-related actions), or writes directly (its
CRUD-style handlers: `akcija_rok`, `akcija_beleska`, etc., which don't generate open-ended legal
conclusions). Not an independent AI-quality risk; it inherits whichever underlying feature's grounding
level applies (strong via `ask_agent`, weak via Strategy Engine, depending on which action fires).

---

## Uncertainty propagation across features (Q5, cross-feature view)

**Propagates correctly within**: Genome (evidence completeness → strength-score penalty), `ask_agent`
(retrieval confidence band → response gating/refusal). **Does NOT propagate across features**: Evidence
classification produces no confidence signal at all, so Genome's `dokazi_rang` check can confirm a
referenced document *exists* but has no signal about whether that document's *classification* was itself
uncertain. Strategy Engine and Court Predictor's `prediktuj_ishod` treat whatever text a lawyer pastes in
as ground truth regardless of its own thinness — there is no shared, system-wide "evidence quality" score
that flows between features; each feature's honesty (or lack of it) is siloed to itself.

---

## Overall verdict summary

| Feature | Verdict |
|---|---|
| `ask_agent` (core RAG Q&A) | **Honest-about-uncertainty** — confidence-gated, explicit refusal on LOW, strict citation-to-context-only rules |
| Legal Document Analysis (`analiza/validator.py`) | **Honest-about-uncertainty** — code-enforced excerpt/ref/law-ref validation |
| Case Genome | **Honest-about-uncertainty** — deterministic score, hard/soft-flagged fabrication, evidence-completeness penalty |
| Drafting (`quality_gate`) | **Honest-about-uncertainty** for citations specifically — real RAG-verified citation check |
| Court Predictor | **Partially-honest** — `nivo` is grounded, `procenat` is raw and unreconciled with it |
| Strategy Engine | **Overconfident-risk** — riskiest feature in the app; zero grounding, prompt-instruction-only honesty |
| Evidence classification | **Overconfident-risk** — zero confidence field, zero validation, lower stakes |
| Copilot | Not independently assessed — inherits underlying feature's grounding |
| Wrapper level (`ai_client.py`) | No hallucination guard exists here at all — naming ("Prompt Guard") could mislead a reader into assuming otherwise |
