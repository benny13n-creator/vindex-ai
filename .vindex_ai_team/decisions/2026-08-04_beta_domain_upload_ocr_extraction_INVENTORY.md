# Program Beta — Domain Inventory: Upload / OCR / Extraction / Classification

**Scope**: AI-reasoning-specific questions (facts/inference separation, evidence chains, confidence
determinism, hallucination vectors) for the document-intake pipeline. Builds on, does not duplicate,
Program Alpha's own structural-duplication audit of the same pipeline (same day,
`2026-08-04_alpha_domain_document_pipeline_INVENTORY.md`). Read-only. No code/git changes.

---

## AI operation inventory

| Operation | Model/temp | Input | Output | Data sources read | Audit/provenance | Confidence source |
|---|---|---|---|---|---|---|
| OCR (`uploaded_doc/extractor.py::extract`) | N/A — `pytesseract.image_to_string()`, no LLM | Scanned file | Raw text | The file only | None | **None returned by the function at all** — caller (`intake_worker.py:181`) hardcodes `0.6` as an explicitly-commented placeholder |
| Heuristic classification (`intake_classify.py::classify_heuristic`) | N/A, pure keyword match | First 400 chars of text | `(doc_type, 0.85)` | The document text only | via caller | **Fixed constant `0.85`** — not computed from evidence, a flat "heuristic match = 85% sure" assumption |
| LLM classification fallback (`intake_classify.py::classify_llm`) | `gpt-4o-mini`, temp not set (default) | First 3000 chars | `(doc_type, confidence)` | The document text only | via caller | **Model's own self-report**, explicitly documented as such in the docstring ("dolazi direktno iz modelovog samoprocenjivanja... ne predstavljeno kao egzaktna mera") — honest labeling, still non-deterministic |
| Entity extraction, regex path (`intake_extract.py`) | N/A, deterministic regex | Document text | `(value, confidence)` per field | The document text only | via caller | **Formula-derived** (0.9–0.97 based on match significance) — genuinely deterministic |
| Entity extraction, LLM fallback (`intake_extract.py`) | `gpt-4o-mini`, temp `0.1` | Document text | `{entity: {value, confidence}}` | The document text only | via caller | Model self-report, but **explicitly tagged** `extraction_method: "llm"` vs `"regex"` in the output — see positive pattern below |
| Evidence classification (`routers/evidence.py::_klasifikuj_dokument`) | `gpt-4o-mini`, temp `0` | Doc name + first 1500 chars | `tip_dokaza`, `pravni_elementi`, `ai_tags`, `kljucne_cinjenice` | The document text only | `log_action_sync("evidence_klasifikacija")` | **No confidence field requested or returned at all** |
| Evidence key-fact location grounding (`routers/evidence.py::_lociraj_tvrdnju`) | N/A, deterministic substring/whitespace-normalized match | LLM-extracted claim text + source document text | Page/paragraph/offset, or all-`None` if not found | The document text + the claim | N/A (feeds `predmet_dokazi` row) | N/A — this IS the grounding mechanism, not a confidence producer |

---

## Facts vs. Inference vs. Recommendation

**Mixed, not systematically separated.** Classification (`tip_dokaza`) and entity extraction
(`ai_tags`/typed entities) are correctly treated as FACTS-shaped outputs (structured fields, not prose) —
this is good design by construction, not an accident. But **`kljucne_cinjenice`** ("key facts") from
Evidence's classifier is a genuine blur: it's LLM-*paraphrased* prose presented as "facts," with no
inherent marker distinguishing "this is verbatim from the document" from "this is the model's summary of
what it read." `_lociraj_tvrdnju`'s location-grounding is the *only* thing that retroactively
distinguishes the two — if it finds an exact/near-exact match, the "fact" is genuinely traceable to source
text; if it returns all-`None`, the "fact" is really an inference (a paraphrase), not a verified fact, but
**nothing in the stored data or the UI currently surfaces this distinction to the lawyer** — a found-vs-
not-found location result is stored, but not used to relabel the claim's epistemic status.

**Recommendations are absent from this pipeline** (correctly — intake/classification doesn't recommend
anything, it just establishes facts). No violation here.

---

## Evidence Chain trace

**Document → OCR → Extraction → Classification → `predmet_dokumenti.tip_dokaza`**: traceable end-to-end
at the STORAGE level (each step writes to a real row, `dokument_id` links them), but **the confidence/
certainty information is lost at every hop**:
- OCR's real per-word confidence (available from `pytesseract.image_to_data()`, not used) never enters
  the chain at all — replaced by a flat, hardcoded `0.6`.
- Classification's confidence (heuristic `0.85` or LLM self-report) is used to decide review-queue
  routing upstream (`intake_classify.py`) but **is not itself stored on `predmet_dokumenti`** — once
  `tip_dokaza` is written, nothing downstream (Genome, risk_engine's missing-doc detector) can tell
  whether that classification was a confident heuristic hit or a low-confidence LLM guess.
- **Verdict: Broken, not Complete.** The chain exists for the *value* (what type is this document) but
  not for the *epistemic status* of that value (how sure are we) — a downstream consumer treats a
  0.31-confidence LLM guess and a 0.85-confidence heuristic hit identically, because only the former is
  persisted past the classification step.

**Evidence's `kljucne_cinjenice` → `predmet_dokazi`**: Complete for the subset where `_lociraj_tvrdnju`
finds a match (page/paragraph/offset are real, checkable coordinates back into the source document) —
this is a genuine, working Evidence Chain for that subset. **Broken for the rest**: `snaga` (strength) is
hardcoded to `"srednja"` regardless of whether the location was actually found — meaning a claim that
`_lociraj_tvrdnju` COULD NOT verify (all-`None` location, i.e. likely a paraphrase, not a verbatim fact)
is stored with the exact same "strength" label as one that was verified byte-for-byte in the source
document. **This is the single most concrete, fixable Evidence Chain gap in this domain**: the grounding
check already runs and already produces a real signal (found vs. not-found) — that signal is just
discarded instead of feeding `snaga`.

---

## Confidence audit

| Value | Deterministic? | Reproducible? | Verdict |
|---|---|---|---|
| OCR confidence | No — hardcoded `0.6` | Trivially (always the same number) — but meaningless | **Fake** — a magic number masquerading as a measurement |
| Heuristic classification confidence | No — hardcoded `0.85` | Same | **Fake**, though honestly a design constant, not presented as measured |
| LLM classification confidence | No | No — model self-report varies run to run for the same input | **Non-deterministic by nature**, but honestly labeled as such in code comments (not hidden) |
| Regex extraction confidence | **Yes** — formula from match significance | Yes | **Genuinely deterministic** — the positive example in this domain |
| LLM extraction confidence | No | No | Non-deterministic, but **correctly tagged** `extraction_method` so a downstream consumer CAN discount it if it chooses to (most don't, but the field exists) |
| Evidence classification confidence | **N/A — doesn't exist** | N/A | Not a fake value, but a real gap: no confidence signal at all for `tip_dokaza`/`pravni_elementi` |
| Evidence "strength" (`snaga`) | No — hardcoded `"srednja"` | Trivially, meaninglessly | **Fake**, and the domain's worst offender — a real, cheap, already-computed signal (`_lociraj_tvrdnju`'s found/not-found result) exists and is simply not used |

---

## Hallucination vectors, systemic-first

1. **Evidence classification's `tip_dokaza`/`pravni_elementi`/`ai_tags`: zero grounding check.** Unlike
   `kljucne_cinjenice` (which has `_lociraj_tvrdnju`), nothing verifies the classified type or extracted
   legal elements against the actual document text — the model could return a type or element with no
   basis in the document and nothing would catch it. **Systemic opportunity, not a prompt fix**: this
   exact codebase already has TWO proven, working "verify against source text, fail soft to null" patterns
   — `_lociraj_tvrdnju` itself (this file) and `analiza/validator.py::validate_clause_excerpts` (Drafting's
   quality gate, cited by this file's own docstring as the shared design principle). Extending the *same*
   pattern to `pravni_elementi` (each element could be checked for presence of its key terms in the
   document text, the same way clause excerpts are checked) is a genuine systemic option, not a new
   invention — worth a future mission's dedicated pass.
2. **`snaga` hardcoded regardless of grounding result** (detailed above) — the systemic fix already
   exists in the same function; it's a matter of *using* `_lociraj_tvrdnju`'s own return value, not
   building a new mechanism.
3. **OCR confidence is fabricated** — `pytesseract.image_to_data()` (not currently used) returns real
   per-word confidence scores; switching from `image_to_string()` to `image_to_data()` and aggregating
   would replace the `0.6` placeholder with a genuinely OCR-engine-computed value. Not urgent (OCR text
   itself isn't a "reasoning" defect — it's a measurement gap), but directly relevant to Program Beta's
   Principle 4 (deterministic core) since this is exactly the kind of value that "sistem računa" should
   own, not a hardcoded guess.

**No shape matching Court Predictor's specific bug (an independent second AI call producing a number that
contradicts a deterministic one next to it) was found in this domain** — this domain's confidence problems
are "missing or fake," not "duplicated and contradictory."

---

## Summary for parent

**AI operations inventoried**: 7 (OCR, heuristic classification, LLM classification, regex extraction,
LLM extraction, Evidence classification, Evidence location-grounding). **Confidence values found
non-deterministic or fake**: 4 of 7 have a real problem — OCR (fabricated), heuristic classification
(magic-number constant), Evidence classification (missing entirely), Evidence `snaga` (fabricated,
worst offender since a real signal already exists and is discarded). **Evidence Chain gaps found**: 2 —
classification confidence isn't persisted past the classification step (so downstream consumers can't
tell a confident heuristic hit from an unsure LLM guess), and `snaga` ignores `_lociraj_tvrdnju`'s own
already-computed grounding result. **Single highest-priority systemic fix opportunity**: derive `snaga`
from `_lociraj_tvrdnju`'s found/not-found result (and optionally match quality — exact vs.
whitespace-normalized) instead of a hardcoded constant — this is the domain's own version of the
Court-Predictor-shaped fix (deterministic value derived from an already-computed signal, not a new
mechanism), the cheapest and most directly analogous fix to today's already-proven pattern.
