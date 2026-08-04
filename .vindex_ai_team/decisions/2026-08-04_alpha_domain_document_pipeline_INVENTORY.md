# Program Alpha — Domain Inventory: OCR / Classification / Extraction / Missing-Document Detection

**Scope**: every business decision in this codebase that OCRs a document, classifies its type, extracts
structured data from it, or decides which documents are "missing" for a case. Read-only, no code/git
touched. All claims verified against current code, not cited from memory of prior mission reports.

---

## Decision inventory

| Decision | Canonical location | Consumers | # independent implementations |
|---|---|---|---|
| OCR / raw text extraction from a file | `uploaded_doc/extractor.py::extract()` | `shared/intake_worker.py` (only call site found) | **1 — genuinely canonical** |
| "Is this document type X" (classification) | **TWO**: `shared/intake_classify.py::classify()` AND `routers/evidence.py::_klasifikuj_dokument()` | Intake staging queue (former); `predmet_dokumenti`/`predmet_dokazi`, Evidence Vault UI, `risk_engine.py`'s missing-doc detector (latter) | **2 — real duplicate, see below** |
| Entity extraction (parties/court/amount/dates) | **TWO, overlapping**: `shared/intake_extract.py::extract_all_entities()` AND `routers/evidence.py::_klasifikuj_dokument()`'s `ai_tags` | Intake staging queue (former); Evidence Vault `predmet_dokazi.ai_tags` (latter) | **2 — real duplicate, see below** |
| "What documents are expected for case type X" (missing-doc detection) | `shared/constants.py::EXPECTED_DOCS` → `services/risk_engine.py`'s single detector function | `routers/matter_intel.py`, `routers/ccc.py` — both import the same constant and call the same function | **1 — genuinely canonical, already consolidated by a prior mission** |
| Evidence "strength" (`predmet_dokazi.snaga`) | Nowhere — hardcoded literal | Evidence matrix UI | **0 real implementations — a hardcoded constant masquerading as a computed value** (already known: Nexus 2026-08-03, re-confirmed by Mission Olympus's backtest 2026-08-04, unchanged) |

---

## Finding #1 (highest priority): two independent AI classification pipelines for the same question

**`shared/intake_classify.py::classify()`** and **`routers/evidence.py::_klasifikuj_dokument()`** both
answer "what type of document is this?" for the same document, via two completely separate AI calls,
with:
- **Different taxonomies**: intake's is `lawsuit/response/appeal/judgment/contract/invoice/power_of_attorney/
  evidence/email/court_decision/enforcement/legal_opinion/other` (13 English types, defined by migration
  074's CHECK constraint). Evidence's is `sudska_odluka/podnesak/ugovor/dopis/medicinska_dokumentacija/
  finansijska_dokumentacija/javna_isprava/vestacki_nalaz/ostalo` (9 Serbian types, defined inline in the
  prompt string, no DB constraint found).
- **Different prompts, different system messages, different models called independently** — two GPT-4o
  (-mini) calls per document for the same underlying question, real duplicated AI cost.
- **Different confidence semantics**: intake's classifier returns a real confidence score (heuristic 0.85,
  or the model's own self-rating). Evidence's classifier returns **no confidence score at all**.

**This is not an unnoticed bug — it is a known, previously-patched symptom.** A prior mission (Lawyer
Zero, LZ-002, 2026-08-03 — comment at `routers/smart_intake.py:703-725`) found that `predmet_dokumenti.
tip_dokaza` was being written by intake's classifier using the WRONG vocabulary (the column expects
Evidence's Serbian taxonomy), starving `risk_engine.py`'s missing-document detector. **The fix applied
was to add a second write** — auto-trigger Evidence's classifier to run *after* intake's finalize and
overwrite the field with the correct vocabulary. This works today (confirmed: `smart_intake.py:726-736`),
but it is a **local patch, not a canonical fix** — it did not remove the cause (two independent
classifiers), it added a second one to correct the first one's output, held together by write-ordering.

**Why this matters under Program Alpha's own stress-test framing**: today this "second write wins" pattern
works because both writes happen in predictable sequence inside one finalize flow. At 10,000 predmeta /
100 parallel AI analyses / 20 workers (this mission's own stress-test scenario), nothing guarantees that
ordering holds — a slow evidence-classification background task, a retry, or a future code path that reads
`tip_dokaza` between the two writes would see the wrong-vocabulary intermediate state. The current design
has exactly one implicit invariant (`evidence classify always finishes after intake classify`) enforced by
nothing but call order in one function.

**Recommended canonicalization** (not implemented by this fork — Phase 5's decision): retire
`shared/intake_classify.py`'s classification role entirely; have the intake pipeline call
`routers/evidence.py`'s classifier (or a shared function both import) as the ONE classification step,
writing directly in the correct vocabulary the first time. Intake's own heuristic keyword pre-check
(`classify_heuristic`) is a real, valuable, cheap optimization — it should be preserved, but feeding INTO
the canonical classifier's taxonomy, not maintaining a parallel one. This removes an entire AI call per
document (real cost + latency win) and removes the "second write must always run after the first"
fragility entirely.

---

## Finding #2: overlapping entity extraction, two pipelines

`shared/intake_extract.py::extract_all_entities()` (regex-first, LLM-fallback-per-field, 8 typed entities:
case_number/judge/plaintiff/defendant/court/deadline/amount/law_cited) and `routers/evidence.py`'s
`ai_tags` (free-text JSON: stranke/datumi/iznosi/sud_organ/referenca) extract overlapping information
(parties, court, amounts, dates) from the same document text via two independent mechanisms. Intake's is
the more rigorous design (deterministic regex candidates preferred over LLM per its own documented
rationale) — Evidence's is a single unstructured LLM call with no regex pre-check and no per-field
confidence at all.

**Lower priority than Finding #1** (the two systems don't directly overwrite each other's output the way
the classifiers do — they write to different tables/fields, so there's no active correctness bug today,
only duplicated AI cost and two places a future engineer must remember to update if entity-extraction
logic changes). Recommended: fold Evidence's `ai_tags` extraction into a call to intake's canonical
`extract_all_entities()`, keeping only Evidence-specific fields (like `referenca`, if genuinely distinct
from `case_number`) as an addition, not a parallel implementation.

---

## What is already canonical (verified, not assumed)

- OCR/text extraction: single implementation, single call site.
- Missing-document detection: single canonical constant (`EXPECTED_DOCS`) and single detector function,
  correctly reused by both consumers (`matter_intel.py`, `ccc.py`) — this was itself the product of a
  prior mission's fix (Nexus, 2026-08-03) and remains correctly consolidated today.

## Hidden logic / magic numbers found (not full duplicates, but real instances of Phase 3's target)

- `_HEAD_CHARS = 400` (intake heuristic keyword-scan window) and confidence `0.85` — defined once, in one
  place, not copy-pasted. Not a violation.
- `ocr_confidence=(0.6 if ocr_used else None)` in `intake_worker.py:181` — an honestly-commented, known
  placeholder ("OCR bez eksplicitnog skora danas — konzervativna fiksna vrednost"), not a hidden
  fabrication. A real future-work item, not urgent.
- `predmet_dokazi.snaga = "srednja"` hardcoded, `routers/evidence.py:221` — already tracked by prior
  missions (Nexus, Keystone K-3-adjacent, Mission Olympus's Agent 23/26 charters both name it explicitly
  as a re-check target). Not new, still open.

---

## Summary for the parent report

**Total decisions mapped**: 5 (OCR, classification, entity extraction, missing-doc detection, evidence
strength). **New duplicates found this pass**: 2 real ones (classification, entity extraction) — both
previously unaddressed at the architectural level despite one being partially patched (LZ-002). **Single
highest-priority canonicalization target in this domain**: unify document classification onto ONE
implementation (retire the intake-side classifier's independent taxonomy/AI call, keep only its heuristic
pre-filter, route into Evidence's classifier as the canonical decision-maker) — this is a Critical-tier
Program Alpha finding because it currently masks a real, if narrow, race-condition-shaped fragility behind
implicit call-order sequencing, not just a cost/duplication concern.
