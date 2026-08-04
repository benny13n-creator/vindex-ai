# PROGRAM BETA — Domain Inventory: Case Genome + Memory Graph + Firm Brain

**Mission:** Masterprompt 002, "Deterministic AI & Evidence-First Architecture."
**Scope:** Case Genome (`routers/case_dna.py`, `shared/genome_validator.py`), Memory Graph, Firm Brain (`routers/firm_memory.py`).
**Method:** Read-only code inspection. No edits, no git commands, no fixes.
**Prior art read first:** `2026-08-04_alpha_domain_genome_memory_strategy_INVENTORY.md` (Program Alpha, same domain, different lens — duplicate-implementation focus, not re-derived here).

---

## 1. AI Operation Inventory

### 1.1 `_extract_genome` (Case Genome full extraction) — `routers/case_dna.py:222-`, GPT call at `_pozovi_genome_api` (203-219)
- **Input:** up to 25 documents' `tekst_sadrzaj` (4500 chars/doc, 60000 total char cap — `_GENOME_MAX_*` constants, explicitly documented as reported-not-hidden limits), plus advisory `predmet_dokazi` context (`_fetch_dokazi_kontekst`, non-blocking).
- **Output:** large structured JSON — parties, witnesses, experts, finances, dates, deadlines, contradictions, arguments for/against, strength score/factors, heatmap, ranked evidence, weakest point, strategy, missing evidence, warnings, conclusion, completeness rating.
- **Prompt:** `_GENOME_SYSTEM` (~lines 60-145). Contains genuine, specific anti-hallucination instructions: "Izvlaci SAMO ono sto pise u dokumentima. Nikad ne izmisljaj." Explicit anti-anchoring instruction telling the model the `0` shown for `snaga_predmeta_procent` is a placeholder, not a target, and two different cases must not get the same number "iz navike ili default." For `kontradikcije` location fields: exact `DOK-XX str.Y` only if the page is literally visible in text, else `DOK-XX` alone, else empty — "NIKAD ne nagadjaj ili izmisljaj lokaciju."
- **Model/params:** `gpt-4o`, `temperature=0.1`, `response_format=json_object`, `max_tokens=4000`, 60s timeout, wrapped in `@llm_retry`.
- **Data source:** case documents only (no cross-case retrieval, no Firm Brain injection into this prompt).
- **Audit/provenance:** wrapped in `shared.ai_provenance.case_context()` at both call sites (lines 715, 868) — confirmed via grep, this is Mission Atlas's provenance wrapper, already applied here.
- **Fallback/retry:** `@llm_retry` decorator; outer function has its own try/except independent of the retry-wrapped inner call.
- **Confidence:** `snaga_predmeta_procent` is **NOT** the raw GPT output — it is silently overwritten post-hoc by `compute_snaga_score()` (`case_dna.py:299-304`), which is 100% deterministic backend arithmetic (see §4). This is the single strongest positive finding in this domain.

### 1.2 `_pozovi_genome_api` post-processing — `shared/genome_validator.py`
- `compute_snaga_score(genome)`: deterministic, zero-GPT. `baseline 50 + neto_uticaj(snaga_faktori)`, clamped 0-100, categorized (`≥75` jaka / `<35` slaba / else srednja), with an auto-appended `-15` visible penalty factor when `genome_kompletnost == "niska"`.
- `verify_genome(genome, docs)`: zero-GPT, zero-I/O, never raises. Four independent checks, each self-isolated (try/except swallows its own failure without blocking the others): document-name match for `dokazi_rang`, `DOK-XX` location match for `kontradikcije`, law-reference soft-check (reuses `analiza/validator.py::validate_law_refs`), internal strength-consistency check, and a v2 addition — `_validate_clan_brojevi`, a plausible-range check on cited article numbers (`_USTAV_MAX_CLAN_APPROX=250`, `_ZAKON_MAX_CLAN_APPROX=1200`) that is **explicitly documented as not confirming the article exists** — "to bi zahtevalo pravni korpus/graf, eksplicitno van obima."

### 1.3 `compare_docs` / `_pozovi_compare_api` (two-document comparison) — `routers/case_dna.py:987-1067`
- **Input:** two full documents (up to 10000 chars each — deliberately larger per-doc budget than Genome's, since only 2 docs are ever in scope, per code comment at line 1046-1048).
- **Output:** `razlike_kljucne`, `kontradikcije`, `slicnosti`, `koji_je_jaci_dokaz` (which is the stronger evidence — an inference-shaped judgment), `preporuka_advokata` (a raw recommendation), `zakljucak`.
- **Prompt:** `_COMPARE_SYSTEM` (lines 149-160) — six lines, no anti-hallucination instructions, no anti-anchoring instructions, no "cite only if visible" rule of the kind `_GENOME_SYSTEM` has for its contradiction locations.
- **Model/params:** `gpt-4o`, `temperature=0.1`, `response_format=json_object`, `max_tokens=1500`, 30s timeout, `@llm_retry`.
- **Audit/provenance:** **none found.** No `ai_provenance.case_context()`, no `log_action`, no correlation_id wiring anywhere in `compare_docs` or `_pozovi_compare_api` — confirmed absent by grep across the whole file (the only `ai_provenance` references in `case_dna.py` are at lines 528, 535, 715, 868, all inside Genome code paths).
- **Confidence/validation:** **none.** The parsed JSON (`analiza`) is returned to the caller completely raw — no `compute_snaga_score`-style post-processing, no `verify_genome`-style check, no confidence field of any kind, no document-existence check on citation-shaped output.
- **Frontend:** `static/vindex.js:17918` `_voice_compare_docs` — renders `koji_je_jaci_dokaz` and `preporuka_advokata` as plain markdown text with **no warning block, no confidence indicator, no equivalent of Genome's "AI provera" / "AI ograničenja" trust signals.**

### 1.4 Firm Brain — `routers/firm_memory.py` (758 lines, fully read for this audit)
- **Zero AI/GPT calls of any kind.** Grepped for `openai|gpt-|chat_completion` — no matches. This file is a pure CRUD/retrieval layer over `memory_entries`, `judge_patterns`, `client_memory`.
- `kontekst_za_ai` (line 252): confirmed dead per Program Alpha audit (zero callers) — assembles a context string for consumption by an *external* AI call, does not itself call an LLM.
- `_apply_trust` (line 63): deterministic. `confidence` is a stored field defaulting to `1.0`, decremented by nothing, boosted only by `potvrdi_memoriju` (line 698) — 3+ unique human confirmations add `+0.2`, capped at `1.0`. **This confidence value is 100% human-sourced/human-confirmed, never LLM self-reported.** Expiry (`zastarela`) is computed from a stored `expires_at` date, not inferred.
- **Verdict:** Firm Brain is not itself an AI-reasoning surface. It's a deterministic memory store; the hallucination risk (if any) lives entirely in whichever downstream module *reads* `kontekst_za_ai`-shaped data and feeds it into a prompt — and per the Alpha audit, the only live consumer (`api.py::_fetch_firm_memory_context`) is a separate, cruder, independently-implemented path, not this file's own function.

### 1.5 Memory Graph
Re-confirmed (not re-derived from scratch) per Program Alpha's finding: fully isolated, zero consumers, zero active AI operations. Excluded from further Beta analysis on that basis — there is nothing to audit for determinism/evidence/confidence in code nothing calls.

---

## 2. Facts / Inference / Recommendation Classification

Both `_GENOME_SYSTEM` and `_COMPARE_SYSTEM` schemas group fields in a way that reads as Facts/Inference/Recommendation **implicitly**, via naming and grouping — but **neither schema carries an explicit per-field category tag**, and neither the backend response nor the frontend renderer labels which output field is which category.

| Category | Genome fields (implicit) | Compare fields (implicit) |
|---|---|---|
| FACT | `stranke`, `svedoci`, `vestaci`, `finansije`, `datumi_kljucni`, `rokovi_kriticni` | `slicnosti` |
| INFERENCE | `kontradikcije`, `heatmap`, `dokazi_rang`, `najslabija_tacka`, `snaga_predmeta*` | `razlike_kljucne`, `kontradikcije`, `koji_je_jaci_dokaz` |
| RECOMMENDATION | `strategija`, `nedostaje`, `upozorenja` | `preporuka_advokata` |

**Finding (Medium, Genome):** structural separation exists in spirit (the schema's own grouping), matching Program Beta's Principle 2 intent, but is not machine-checkable or UI-enforced as distinct categories. A reusable pattern (not an invention) since the grouping already exists — the gap is surfacing it, not creating it.

**Finding (Medium-High, Compare):** same implicit-only gap as Genome, but **without any of Genome's compensating validation layer** — `koji_je_jaci_dokaz` and `preporuka_advokata` are inference/recommendation-shaped outputs rendered in the UI with zero visual distinction from the fact-shaped `slicnosti`/`razlike_kljucne` fields next to them (§1.3, §5).

---

## 3. Evidence Chain Trace

**Traced claim:** Genome's headline "case strength %" (`snaga_predmeta_procent`).

`document.tekst_sadrzaj` → GPT extraction into `snaga_faktori` (per-case, LLM-synthesized, not hardcoded) → `compute_snaga_score()` deterministic arithmetic over those factors → `snaga_predmeta_procent`/`snaga_predmeta` category → `verify_genome()` runs 4 independent consistency/existence checks against the same source documents → `_verifikacija.odluka` written alongside the genome → **saved regardless of `odluka`** (confirmed via direct code read: `verify_genome`'s own docstring states `"'require_review' je status, ne blokada"`, and the caller "NASTAVLJA da snima genom bez obzira na odluku").

**Backend verdict: partially traceable, non-blocking.** The score itself is reproducible and its inputs are inspectable (`snaga_faktori` is visible, not hidden), and 4 real consistency checks run against real source documents — but a `require_review` result does not prevent the genome from being persisted or served.

**Frontend verdict (confirmed by direct code read, `static/vindex.js:17430-17490`): materially closes the backend gap.** `_verifikacija.odluka` is rendered as a hard-to-miss, non-collapsible amber warning block (green "✓ nema upozorenja" only when clean) listing up to 8 actual flag reasons, deliberately placed outside the collapsible "detalji" wrapper — code comment: "sakriti trust signal iza klika bi poništilo razlog zašto je uopšte napravljen vidljivim." A separate, adjacent "AI ograničenja" block renders `_analiza_osnov` (document/fact/element counts) and `nedostaje` (missing doc types) using **zero new AI calls** — pure counting, explicitly commented as such. Founder-quoted rationale in the code: "AI zna šta nema."

**Combined verdict for Genome: end-to-end traceable in practice.** The mechanism is advisory not a hard gate at the DB layer, but the UI layer is honest and prominent enough that a low-confidence genome is not presented to a lawyer as equally authoritative as a high-confidence one. This is a real, shipped implementation of Program Beta's Explainability-by-Design principle, not aspirational.

**Traced claim:** Compare's `koji_je_jaci_dokaz`.

`document A + document B` → GPT judgment → returned raw → rendered raw. **No evidence chain exists.** No check that the claimed stronger document is actually one of the two compared (trivially true here since only 2 are ever in scope, but no check on *why* — no equivalent of Genome's `_validate_dokazi_rang`/`_validate_kontradikcije_lokacije` pattern applied to `razlike_kljucne`'s implicit citations). **Verdict: not traceable — this is the one clear evidence-chain gap in the domain.**

---

## 4. Confidence Audit

| Value | Computation | Deterministic? | Reproducible? |
|---|---|---|---|
| `snaga_predmeta_procent` (Genome) | `compute_snaga_score()`, backend arithmetic over LLM-extracted `snaga_faktori` | Yes | Yes — same facts, same score |
| `heatmap` dimensions (Genome) | Raw GPT output, **not** post-processed by any `compute_*` function found in `genome_validator.py` or `case_dna.py` | **No** | **No** — unverified, likely same anchoring risk class `compute_snaga_score` was built to fix |
| `dokazi_rang.snaga_score`/`zvezdice` (Genome) | Raw GPT output; only cross-checked for *consistency* against the overall score (`_validate_snaga_konzistentnost` soft-flags a ≥2-star deviation) — not computed independently | **No** (soft-checked, not computed) | Partial |
| `najslabija_tacka.kriticnost` (Genome) | Raw GPT output, no independent computation or check found | **No** | **No** |
| `_verifikacija.odluka` (Genome) | `verify_genome()`, fully deterministic, zero GPT | Yes | Yes |
| Firm Brain `confidence` (memory_entries) | Human-set default 1.0, human-confirmation-boosted only | Yes | Yes |
| Compare `analiza` (all fields) | No confidence value exists at all | N/A | N/A |

**Highest-value unresolved item:** `heatmap` and `najslabija_tacka.kriticnked` are the two Genome confidence-shaped values with **no deterministic backend computation and no consistency check**, unlike `snaga_predmeta_procent` (fully fixed) and `dokazi_rang` stars (at least soft-checked). These are the same class of defect `compute_snaga_score` was built to eliminate in the 2026-07-18 Reality Validation incident, left unaddressed in this file for two adjacent fields.

---

## 5. Hallucination Vector Scan

| # | Vector | Where | Existing systemic mechanism that could close it | Recommendation |
|---|---|---|---|---|
| 1 | Fabricated `heatmap` dimension score | Genome extraction | None currently applied; `compute_snaga_score`'s pattern (deterministic backend scoring from extracted factors) is the exact precedent, already proven twice in this codebase (here, and later independently re-invented for Court Predictor per Program Alpha) | **Systemic** — extend the same pattern to heatmap; do not invent a new mechanism |
| 2 | Fabricated `najslabija_tacka.kriticnost` | Genome extraction | Same as above | **Systemic** — same extension |
| 3 | Invented article number (plausible but non-existent) | Genome `relevantni_zakoni`/`_validate_clan_brojevi` | Explicitly out of scope today per the validator's own docstring ("zahteva pravni korpus/graf"); this is the same class of gap Drafting's `quality_gate` citation-existence check was built for (per this fork's directive) — **not yet independently verified in this fork whether `quality_gate`'s corpus lookup is reusable here**, flagged for the domain that owns Drafting/`quality_gate` to confirm feasibility | **Systemic candidate, unconfirmed** — investigate whether `quality_gate`'s corpus is reusable before building a new one |
| 4 | Invented `koji_je_jaci_dokaz` reasoning, no source grounding | `compare_docs` | `_validate_dokazi_rang`/`_validate_kontradikcije_lokacije` pattern already exists in `genome_validator.py` for structurally identical claims (a claim that references a specific document) | **Systemic** — reuse `genome_validator.py` functions against `compare_docs` output; this is the single largest gap in the domain since the fix already exists in-repo |
| 5 | Invented `preporuka_advokata` presented with no recommendation label | `compare_docs` | None dedicated; Genome's implicit field-grouping convention could be extended, but no UI trust-signal precedent exists yet for Compare specifically | **Local-leaning** — smallest fix is a frontend label/warning block modeled on Genome's, not a new backend mechanism |
| 6 | No audit/provenance trail for `compare_docs` | `compare_docs` | `shared.ai_provenance.case_context()` — already used at two other call sites in this exact file | **Systemic, trivial** — wrap the existing call the same way `_extract_genome` already is; zero new mechanism required |

**Cross-reference to Court Predictor confidence bug (Program Alpha):** confirmed same-shape defect exists twice more in this domain (`heatmap`, `najslabija_tacka.kriticnost` — vector #1, #2 above), and confirmed the deterministic-scoring fix pattern **pre-dates** Court Predictor's fix (`compute_snaga_score`'s docstring explicitly cites `analiza/validator.py` Sloj 10 as the original precedent, calling itself "nastavak istog principa, ne nova ideja"). This means the correct framing for Phase 6/7 is not "apply the Court Predictor fix here" but "this is the third occurrence of a fix pattern that already existed twice before Court Predictor — treat it as a standing platform principle, not a one-off precedent to port."

---

## 6. Summary Table

| Operation | Model | Temp | Deterministic post-processing | Evidence validation | Audit/provenance | UI trust signal |
|---|---|---|---|---|---|---|
| Genome extraction | gpt-4o | 0.1 | Partial (strength score only) | Yes (`verify_genome`, 4 checks) | Yes (`case_context`) | Yes (2 blocks) |
| Compare docs | gpt-4o | 0.1 | None | None | **None** | **None** |
| Firm Brain | — (no AI calls) | — | N/A (pure CRUD) | N/A | N/A | Trust metadata shown (`_trust.upozorenje`) |
| Memory Graph | — | — | — | — | — | — (isolated, unused) |

---

## Priority Systemic Fix Opportunity

**`compare_docs` is the domain's clearest gap, and every needed mechanism already exists elsewhere in the same file/codebase — this is wiring, not invention:**
1. Wrap the GPT call in `shared.ai_provenance.case_context()` (already used twice in `case_dna.py`).
2. Run its output through the same document-existence/location-validation pattern `genome_validator.py` already applies to structurally identical claims (`_validate_dokazi_rang`-style check against `koji_je_jaci_dokaz`).
3. Give the frontend a warning block modeled on Genome's non-collapsible `_verifikacija` pattern, rather than rendering `preporuka_advokata`/`koji_je_jaci_dokaz` as unlabeled plain text.

This satisfies the mission's "prove systemic isn't achievable before patching locally" rule in the negative direction — a systemic fix (reuse) is trivially achievable here, so no local-patch justification would be needed.
