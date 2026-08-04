# Program Beta — Domain Inventory: Copilot / Morning Briefing / Drafting

Read-only investigation. No code/git changes made. All claims verified against current code.

## AI operation inventory

| Operation | Model/temp | Data source | Confidence | Audit/provenance | Fallback |
|---|---|---|---|---|---|
| `main.py::ask_agent` (Copilot `pravno_pitanje`) | gpt-4o / gpt-4o-mini per topic, varies | `retrieve_documents()` (Pinecone zakoni), sudska praksa, mišljenja | **Deterministic** — `get_confidence_level()` on cosine score vs. named thresholds (`CONFIDENCE_HIGH_THRESHOLD=0.65`, `CONFIDENCE_MEDIUM_THRESHOLD=0.52`); separate deterministic 0-100 `_calculate_confidence()` (similarity+result-count+query-specificity weighted sum) | `case_context()`/`log_action` (via `copilot.py::_handle_pravno_pitanje`) | LOW confidence → instant refusal, **zero LLM call** (code-enforced, `main.py:3255`) |
| Article-citation hard refusal (`main.py:3220-3252`) | N/A (deterministic lookup) | `_direktan_fetch_clana()` against indexed corpus | N/A (binary: found/not found) | logged `[HALUCINATION_GUARD]` | explicit citation not in corpus → hard refusal, model never sees the question |
| `_handle_akcija_rok` (Copilot deadline extraction) | gpt-4o-mini, temp=0 | Free-text lawyer message only | **None** — no confidence field on the extracted `vaznost`/`datum_iso` | `case_context()` + `log_action("copilot_dodaj_rok")` | Extraction failure → user-facing error; no validation the extracted date is plausible |
| `_handle_akcija_beleska`, `_handle_akcija_povezi_klijenta`, `_handle_naplati_radnju` | gpt-4o-mini, temp=0 (not individually re-verified line-by-line, same shape confirmed via `_handle_akcija_rok`'s sibling structure) | Free-text lawyer message | None | `case_context()` + `log_action` (per-action names, confirmed via Mission Migration) | Same pattern |
| `_ai_prioritizacija_alertova` (Morning Briefing prose) | gpt-4o-mini, **temp=0.3** | The `alerts` list already computed/stored (titles+descriptions only) | None | Not individually audited (feeds into the nightly run's own audit) | On error, falls back to raw `linije[:3]` (the unprocessed alert list) — a real, good fallback |
| `_drafting_generate` (deep draft generation) | Not re-traced this pass (out of this fork's time-box — flagged, not asserted) | Case documents + templates | N/A | `case_context()`/`log_action("drafting_nacrt")` (Program Alpha/Phoenix) | Not verified |
| `services/quality_gate.py::evaluate_draft_quality` | N/A — deterministic, no LLM call | The draft text itself + real indexed legal corpus | **Fully deterministic**: `confidence = 0.6*citation_score + 0.4*completeness_score`, both formula components documented and reproducible | N/A (a scoring function, not an AI call) | Citation-verification batch failure → neutral `0.5`, never blocks |

## Facts vs. Inference vs. Recommendation — real gap found

`_handle_akcija_rok` (and by the same pattern, the other Copilot "akcija" handlers) extract `vaznost`
("kritičan"/"bitan"/"normalan" — a **classification/inference**, not a directly-stated fact in most
messages) and `datum_iso` (sometimes a literal fact, sometimes an inferred relative-date conversion) via
one undifferentiated GPT call, then write the result to `predmet_hronologija` with `akter: "Copilot (AI)"`
as the only source marker. **The response given back to the lawyer does not distinguish "I read this date
directly from your message" from "I inferred this urgency level."** Both look equally authoritative once
written. This is a direct, confirmed instance of Program Beta's Principle 2 violation (Facts ≠ Inference ≠
Recommendation, not distinguished).

## Evidence Chain findings

- **`ask_agent`'s law-citation chain is genuinely solid, code-enforced end to end**: a cited article either
  exists in the indexed corpus (hard-inject the real text, force HIGH confidence) or the system refuses
  before the LLM is ever called. This is the strongest Evidence Chain in the domain — a real model to
  replicate, not a documentation claim to trust blindly (confirmed by reading the actual refusal logic).
- **Morning Briefing's prose summary has a real, if narrow, chain gap**: `_ai_prioritizacija_alertova`'s
  prompt gives the model only the alert titles/descriptions and asks for a "prioritized recommendation" —
  there is no instruction forbidding the model from stating a fact not present in the given alerts, and no
  post-hoc check that the output doesn't introduce a claim (a count, a date, a name) beyond what was
  passed in. Lower severity than a hallucinated legal citation (this text is a courtesy summary, not the
  authoritative alert data itself, which is separately, correctly stored via `create_proactive_alert`), but
  a real, confirmed gap in the "explain from what" chain.
- **Drafting's `quality_gate` verifies EVERY legal-article citation in a draft** (not just the first —
  confirmed by reading `_extract_article_citations`, which returns the full deduplicated set), against
  the real indexed corpus, via `asyncio.gather` batch verification. **But it only checks article citations
  — case-fact fabrication (a wrong party name, date, or amount the draft states) is entirely unchecked.**
  `_completeness_score` only checks for the PRESENCE of keyword categories (does the word "sud" appear
  anywhere), never their correctness against source documents. A draft stating the wrong hearing date
  would score identically to one stating the correct date, as long as *a* date-shaped mention of "sud"
  exists somewhere in the text.

## Confidence audit

- **`ask_agent`'s confidence bands and `_calculate_confidence`'s 0-100 score**: fully deterministic, named
  thresholds, documented formula. **Clean.**
- **`quality_gate`'s `confidence_score`**: fully deterministic, documented formula
  (`0.6*citation+0.4*completeness`), reproducible. **Clean — and the single best confidence-model example
  in this domain** (its own module docstring explicitly documents why it's a fair proxy, not a full Legal
  Reasoning Engine, and names that honestly).
- **Copilot's extracted `vaznost`/`datum_iso`**: **no confidence value at all** — not flagged as a gap by
  omission, but a real one: an urgency classification with no signal of how sure the extraction was.
- **`_ai_prioritizacija_alertova`**: no confidence value (a prose-generation task, arguably doesn't need
  one, but also has no grounding check — see Evidence Chain above).

## Hallucination vectors, systemic-vs-local recommendations

1. **Highest-priority systemic fix opportunity in this domain**: `services/quality_gate.py`'s
   citation-verification mechanism (`_extract_article_citations` + `_verify_citation`, both operating on
   arbitrary text, not coupled to Drafting's specific document shape) is a **strong, proven, reusable
   candidate** to extend to any other AI feature that can output a legal-article citation — Strategy
   Engine and Case Genome both generate legal reasoning text and neither currently routes through this or
   an equivalent check (confirmed by this domain's own file list — neither imports from
   `services/quality_gate.py`). This is exactly the "a systemic solution already exists, reuse it, don't
   invent a new one" case this mission's own rules prioritize highest.
2. Copilot's akcija handlers conflating fact-extraction and inference (see above) — the systemic fix is
   architectural, not a prompt patch: the extraction JSON schema should separate `datum_iso` (fact,
   directly quotable from source text if present) from `vaznost` (inference, should carry its own
   confidence or at minimum a visible "AI proceni" marker distinguishing it from a literal quote).
3. Morning Briefing's prose-summary grounding gap — lower priority (courtesy text, not authoritative data);
   the systemic fix, if pursued, would be a prompt-level "cite only what's given" instruction PLUS a
   cheap deterministic post-check (e.g., verify no numeral in the output exceeds what's derivable from the
   input alert count) — genuinely low-stakes enough that a documented, deliberate non-fix may be the right
   call rather than added complexity.

## Summary for parent

**Operations inventoried**: 8 (ask_agent + its hard-refusal guard, 4 Copilot akcija handlers as one
pattern-class, Morning Briefing's AI prose, Drafting's generation call, `quality_gate`'s scoring).
**Non-deterministic/ungrounded confidence values found**: 0 numeric hallucinated confidence in this
domain specifically (unlike Strategy Engine/Court Predictor elsewhere) — this domain's real gap is
**missing** confidence/grounding markers (Copilot's extraction, Briefing's prose), not fabricated ones.
**Evidence chain gaps**: 2 confirmed (Briefing's prose grounding; Drafting's case-fact-vs-citation
coverage gap in `quality_gate`). **Single highest-priority systemic fix opportunity**: generalize
`quality_gate`'s citation-verification mechanism for reuse by Strategy Engine/Genome — a proven,
non-invented mechanism already exists, closing exactly the class of "AI invents a legal citation" defect
this mission's Phase 5 targets, without adding new AI capability (pure reuse).