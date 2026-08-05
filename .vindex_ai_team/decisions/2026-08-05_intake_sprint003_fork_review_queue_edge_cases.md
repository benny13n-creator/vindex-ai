# Program Intake Sprint 003 — Fork C (Reliability & Failure Recovery Engineer)
## Phase 5 (Review Queue) + Phase 7 (Edge Case Validation)

**Date**: 2026-08-05. Read-only investigation, no code changes. Builds on `INTAKE_ARCHITECTURE_REPORT.md`
(Sprint 001), `INTAKE_FAILURE_RECOVERY_MATRIX.md` (Sprint 001), `DOCUMENT_LIFECYCLE_ARCHITECTURE_REPORT.md`
(Sprint 002) — not re-derived here. Mission principle under test: every document ends in exactly one of two
states — **Canonically Classified** or **Review Required**. A third state ("silently guessed") must not exist.

**Headline finding (read this first)**: the third forbidden state does not just exist in the 3 classifiers
that never had a review queue — it also **actively reasserts itself inside the one pipeline that does it
correctly**. Pipeline C's finalize writes Pipeline B's confidence-gated `document_type` into
`predmet_dokumenti.tip_dokaza` first, then an unconditional background task overwrites that exact same column
with a second, confidence-blind classifier's guess — with no check of whether the original classification was
low-confidence or whether its review-queue entry was ever resolved. See §1.5.

---

## Phase 5 — Review Queue behavior audit

### 1.1 `shared/intake_classify.py` (Pipeline B) — HAS a real, functioning escape hatch

- `AUTO_ACCEPT_THRESHOLD = 0.90` (`shared/intake_documents.py:23`).
- `shared/intake_worker.py:202-222`: after `classify()` returns `{document_type, confidence, method}`, the
  worker builds `low_confidence_fields` and prepends `"document_type"` if
  `classification["confidence"] < AUTO_ACCEPT_THRESHOLD` (`intake_worker.py:219-220`), then calls
  `intake_documents.create_review_queue_entry(job_id, document_id, "low_confidence_extraction",
  low_confidence_fields)` (`intake_worker.py:222`). This is real and verified working as designed — not just
  asserted by the design doc.
- Two independent classification methods feed this: `classify_heuristic()` (`intake_classify.py:56-68`,
  fixed 0.85 confidence on keyword hit — below the 0.90 auto-accept bar, so even a heuristic-matched
  classification still routes to review by construction) and `classify_llm()` (`intake_classify.py:82-122`,
  confidence is the model's own self-reported number, explicitly documented as such in the code comment at
  line 85-86: *"confidence dolazi direktno iz modelovog samoprocenjivanja"*).
- OCR failure gets its own hatch, separately: `intake_worker.py:177-200` — `document_type='other'`,
  `confidence=0.0`, `create_review_queue_entry(..., "ocr_failed", [])`.

### 1.2 `routers/evidence.py::_klasifikuj_dokument` (Pipeline A's only classifier, and Pipeline C's stage-2
overwrite) — NO escape hatch of any kind

- The LLM prompt (`evidence.py:26-55`) does not request a confidence value at all — the JSON schema it asks
  for is `tip_dokaza`, `pravni_elementi`, `ai_tags`, `kljucne_cinjenice`. There is no number anywhere in this
  function's output that could be compared against a threshold.
- On any exception (timeout, malformed JSON, API error), it silently returns a fixed fallback dict with
  `"tip_dokaza": "ostalo"` (`evidence.py:85-93`) — a default-category guess, not a "review required" signal.
  No review-queue table is written by this module (grep-confirmed: `intake_review_queue` never appears in
  `routers/evidence.py`).
- This is Pipeline A's *only* classifier (`api.py:4334-4341` calls `klasifikuj_i_sacuvaj` directly as the
  sole classification step — no confidence-gated first pass exists on Pipeline A at all).

### 1.3 `api.py::_detect_doc_type` — NO escape hatch, not even LLM-based

- Pure keyword-count heuristic (`api.py:3539-3548`): counts `_PRESUDA_MARKERS`/`_UGOVOR_MARKERS` hits in the
  first 3000 chars and returns exactly one of 3 hardcoded strings — `"presuda"`, `"ugovor"`, or `"opsti"`
  (the fallback when neither wins). There is no numeric confidence anywhere in this function, so there is no
  way for it to express uncertainty even in principle — every call returns a definite answer.
- Confirmed ephemeral (matches Sprint 001's characterization): called at `api.py:4191` only to select which
  AI analysis prompt template to run (`_PRESUDA_SYSTEM_PROMPT` vs. the general `_PROCENA_SYSTEM_PROMPT`
  path); never writes to `predmet_dokumenti`. Consequence: a wrong silent guess here doesn't corrupt the
  permanent record, but it *does* silently select the wrong AI analysis template for the lawyer's document
  with zero visible signal that the type-detection might be wrong.

### 1.4 `routers/dokument.py::_klasifikuj_dokaz` — NO escape hatch; the one field that looks like a
confidence signal is not one

- LLM self-reports `snaga_dokaza` as a string enum (`"visoka"|"srednja"|"niska"`, prompt at
  `dokument.py:93-104`) — this describes the **evidentiary strength of the document**, not the classifier's
  confidence in its own `tip_dokaza` guess. Two different concepts are conflated into one field; there is no
  proxy confidence signal for the type classification itself anywhere in this function's output.
- On exception, fallback dict sets `tip_dokaza="ostalo"`, `snaga_dokaza="niska"` (`dokument.py:111-118`) —
  same silent-default-category shape as §1.2.
- Confirmed ephemeral: only ever returned in an HTTP response (`klasifikuj-sesija` endpoint,
  `dokument.py:467-468`) or logged inside a fire-and-forget background task
  (`dokument.py:273-280`, result only reaches `logger.info`) — never written to `predmet_dokumenti`.

### 1.5 Does anything surface `intake_review_queue` beyond the job-status endpoint? — No.

Repo-wide grep for `intake_review_queue` (excluding docs/migrations/tests) hits exactly one production code
file: `shared/intake_documents.py` (write side) plus its one read call site,
`routers/smart_intake.py:217-264` (`GET /jobs/{job_id}`, the `potrebna_provera` field at line 260-263). No
case-file view, no `predmet_dokumenti` list/detail endpoint, and no frontend code outside Smart Intake's own
job-status screen ever queries this table. A document that was flagged for review and never gets that specific
job-status screen revisited has its review flag effectively invisible for the rest of its life in the system.

### 1.6 Does the low-confidence signal survive into `predmet_dokumenti`? — No, and it is actively
**overwritten**, not just discarded.

Two independent things both need documenting here, and they compound:

**(a) Finalize itself never carries the confidence number or the review-pending state.** At finalize
(`routers/smart_intake.py:409-502`), `document = result["document"]` comes from
`intake_documents.get_job_result(job_id)`, which also returns `result["review"]` — but finalize's local
variable unpacking only reads `document` and `entities` (line 483-484); `result["review"]` is fetched and then
never inspected. There is no check anywhere in `finalize_intake_job` for whether an unresolved
`intake_review_queue` row exists for this job, and no HTTP 409/warning is raised if one does — a lawyer can
finalize a document whose classification was flagged `low_confidence_extraction` exactly as easily as a
high-confidence one. `doc_type = document.get("document_type") or "other"` (line 502) takes Pipeline B's
classification value bare; none of the `_dok_row_base`/insert-variant dicts (`smart_intake.py:736-762`)
include `classification_confidence`, `intake_job_id`, or any review-flag column. This is the specific
mechanism behind Sprint 001's `INTAKE-003` ("Confidence Graph data... becomes permanently unlinked from the
case-file document") — confirmed here as applying specifically and directly to the classification-confidence
signal, not just entity-level data.

**(b) Even the bare `document_type` value that *does* survive (a) gets overwritten by a confidence-blind
second classifier, unconditionally, every time.** `routers/smart_intake.py:778-811` — a background task
(`_evidence_classify_bg`, added "Operation Lawyer Zero LZ-002", 2026-08-03) fires via
`asyncio.create_task` immediately after the `predmet_dokumenti` insert, calling
`routers/evidence.py::klasifikuj_i_sacuvaj` (the exact classifier audited in §1.2 — no confidence field, no
review queue) which runs its own independent LLM classification and `UPDATE`s the same `dokument_id`'s
`tip_dokaza` column (`evidence.py:210-215`). This fires **unconditionally** — there is no check of Pipeline
B's `classification_confidence`, no check of whether an `intake_review_queue` entry exists or was resolved,
no skip-if-already-under-review logic. The code comment at `smart_intake.py:787-796` explains this was added
specifically to fix a *different* problem (vocabulary mismatch between `intake_classify.py`'s English taxonomy
and `matter_intel.py`'s Serbian `EXPECTED_DOCS` vocabulary) — a real and legitimate fix for that problem, but
its side effect is that the one pipeline with a genuine confidence-gated classifier has its permanent-record
`tip_dokaza` value silently handed off to a classifier with zero uncertainty-handling, every single time,
regardless of how the first classifier felt about its own answer. **Net effect: even on Pipeline C, the
review-queue signal that correctly identified "I'm not sure" never has a chance to reach the permanent
record even in principle — it's structurally overwritten before a lawyer could act on it via any path other
than that one job-status screen (§1.5), and finalize doesn't wait for or check that screen's resolution
either (§1.6a).**

---

## Phase 7 — Edge Case Validation

Legend: **CONFIRMED DEFECT** = produces a confident-looking wrong answer with no escape hatch, provable from
static code. **CONFIRMED ACCEPTABLE DEGRADATION** = already degrades honestly (review-queue routing, or a
documented existing gap). **GENUINELY UNKNOWN** = cannot be determined by reading code alone; would need an
actual file run through the real pipeline, out of this fork's read-only scope.

### (1) Scanned court judgment (image-based PDF) — does OCR confidence feed classification confidence?

**CONFIRMED DEFECT (architectural)**: they are not just independent — `ocr_confidence` itself is not a
measurement of anything. `shared/intake_worker.py:210` and `:232`: `ocr_confidence=(0.6 if ocr_used else
None)` — a hardcoded constant, not derived from Tesseract output at all. The extractor calls
`pytesseract.image_to_string()` (`uploaded_doc/extractor.py:115`), which returns plain text with **no**
per-word/per-page confidence data (that would require `image_to_data()`, never called anywhere in this repo).
So: clean OCR text and barely-readable OCR text that both clear the `>100 chars` bar (`extractor.py:188`,
`:292`) report the exact same `ocr_confidence=0.6` to the classifier's caller, and `classify()`
(`intake_classify.py:125-133`) never receives or uses `ocr_confidence` as an input at all — it only ever sees
the extracted text string. There is no mechanism by which poor OCR quality could lower classification
confidence or trigger review beyond the blunt binary `is_scanned` gate.

### (2) Badly-scanned/noisy document (garbled OCR text)

**MIXED — partially confirmed defect, partially genuinely unknown.** Confirmed via code: no garbled-text
detector of any kind exists pre-classification (no perplexity check, no dictionary-word-ratio check, no
non-alphanumeric-ratio check) — `classify_llm()` sends whatever text it's given straight to GPT-4o-mini
(`intake_classify.py:92-106`) with no quality gate. The heuristic layer (`classify_heuristic`,
`intake_classify.py:56-68`) is structurally safe against garbage (it can only ever match if the specific
uppercase Cyrillic/Latin keyword substrings happen to appear, near-impossible by chance in OCR noise), so
garbled text reliably falls through to the LLM. What the LLM actually does when handed OCR garbage — whether
it produces a confident wrong `document_type` + high self-reported confidence, or honestly reports low
confidence/`"other"` — is a real LLM-behavior question this fork cannot answer from static reading; it depends
on GPT-4o-mini's actual behavior on degraded input, not on anything this codebase controls or tests.
**Genuinely unknown, needs a real garbled-scan sample run through `classify_llm()`.**

### (3) Rotated-page scan — any rotation detection/correction?

**CONFIRMED DEFECT**: zero matches anywhere in `uploaded_doc/extractor.py` for rotation/orientation/OSD
handling (grep-verified). `_ocr_image()` (`extractor.py:103-120`) does grayscale/contrast/median-filter
preprocessing only — no `pytesseract.image_to_osd()` call, no PIL `.rotate()` call, nothing. `fitz`'s
`page.get_pixmap()` (`extractor.py:180`) will respect a PDF's own `/Rotate` page attribute if one is declared
in the file, but that is PyMuPDF's own unrelated default rendering behavior, not anything this code adds or
can rely on for a raw scanned image with no such metadata, or for a standalone rotated photo through
`extract_image()` (no PDF wrapper exists there at all to carry rotation metadata). A rotated scan degrades
into the same undetected path as case (2) — the code has no way to distinguish "this failed because it's
sideways" from "this failed because the scan is just bad."

### (4) Multiple distinct documents combined into one uploaded PDF (lawsuit + exhibits)

**CONFIRMED DEFECT — the most concretely provable finding in this set.** Text extraction concatenates every
page into a single string (`extract_pdf`, `extractor.py:154-166`: `"\n\n".join(pages)`), with no document-
boundary detection anywhere in `uploaded_doc/chunker.py` either (`chunk_document`, `chunker.py:123-179`,
operates purely on regex article-density/recursive-token-count chunking of the whole string — no concept of
"this is actually N source documents"). Every classifier that ever writes `document_type`/`tip_dokaza` reads
only the *head* of this concatenated string: `classify_heuristic` reads the first 400 chars
(`intake_classify.py:41,63`), `classify_llm` reads the first 3000 (`intake_classify.py:92`),
`_klasifikuj_dokument` reads the first 1500 (`evidence.py:79`, sliced from a caller-supplied `text[:2000]` at
`api.py:4339` / full text at `smart_intake.py:807`), `_klasifikuj_dokaz` reads the first 2000
(`dokument.py:91`). A combined "tužba + prilozi" PDF is therefore classified based **solely** on whichever
document physically appears first in the file. Every subsequent document in the bundle silently inherits that
first classification (or is truncated out of the LLM's view entirely) with no signal anywhere that the upload
might actually contain multiple, differently-typed documents. No table in the schema (`intake_jobs`,
`intake_documents`, `predmet_dokumenti`) has any concept of a 1-to-many upload-to-document relationship — the
data model itself assumes 1 upload = 1 document throughout all 3 pipelines.

### (5) Incomplete document (missing pages, cuts off mid-sentence)

**CONFIRMED ACCEPTABLE DEGRADATION for classification specifically; a real but out-of-scope gap for
extraction/completeness generally.** No completeness check exists anywhere (`MAX_PDF_PAGES=500`,
`extractor.py:93`, is a DoS ceiling, not a floor or completeness signal). But because every classifier in §
(4) above only ever reads the *head* of the document, a document missing pages at the *end* — the realistic
real-world case (court forgot to scan the last page, or an upload got truncated) — has essentially zero
effect on `document_type` classification confidence, since none of the 4 classifiers read that far into the
text regardless of whether it's actually there. This scenario is a real gap for entity extraction and
document *completeness* generally (a missing signature page, missing verdict paragraph, etc.) but that is
`shared/intake_extract.py`'s territory, not document-type classification — flagged as an adjacent known gap,
not analyzed further here per this fork's classification-quality scope.

### (6) Blank pages mixed into a scan

**SPLIT finding.** OCR path: **CONFIRMED ACCEPTABLE DEGRADATION** — blank pages are gracefully filtered,
`"\n\n".join(p for p in ocr_pages if p)` (`extractor.py:187`) drops any page whose OCR text is empty, so blank
pages don't pollute the extracted text on the scanned-PDF path. Born-digital path: **CONFIRMED DEFECT (narrow
severity)** — `avg_chars = total_chars / max(len(reader.pages), 1)` (`extractor.py:161`) divides by the *full*
page count including blank pages, which contribute 0 to `total_chars`. A real born-digital legal document
interleaved with several blank separator/cover pages (common in Serbian court scanning conventions — a blank
page inserted between distinct procedural steps in a single PDF, still born-digital text on the content pages)
can be pulled below the `<30 chars/page` threshold (`extractor.py:163`) and get misrouted into the OCR
fallback path even though it never needed OCR — wasteful, and since OCR re-reads the same content through a
different (lossier) extraction path, this can change what text the classifier actually sees. Requires enough
blank pages relative to content pages to trigger; not a common-case failure, but a real, code-provable one.

### (7) Handwritten notes/annotations on a printed document

**CONFIRMED DEFECT (same shape as case 2, worse-characterized): no mixed-content awareness exists anywhere.**
`_ocr_image()` (`extractor.py:103-120`) runs standard Tesseract OCR (printed-text-oriented engine mode by
default; no handwriting model is configured or available) uniformly across the whole page image — there is no
region detection, no separate handling for a handwritten margin note vs. the typed body text. Whatever garbage
Tesseract produces for the handwritten region is silently concatenated into the same text as the clean printed
OCR output, with no flag distinguishing "this part is unreliable." Confirmed via §(1): the resulting
`ocr_confidence` is still the same hardcoded `0.6` regardless of what fraction of the page is
handwriting-induced noise — the one field that could theoretically carry this signal structurally cannot,
because it isn't measuring anything real to begin with.

### (8) "Combined spis" — a Serbian-practice case-file bundle as one physical scan

**CONFIRMED DEFECT — identical mechanism to case (4), same citations.** No table or code path anywhere in
this repo has any concept of "this one upload is a container of N logical documents." A spis is always forced
through exactly one `document_type`/`tip_dokaza` decision, driven by whichever document happens to appear
first in the physical scan order, for the same head-only-reading reason documented in §(4). This is not a
distinct defect from (4) — it is the same architectural gap, viewed through the specific Serbian-court-practice
scenario the mission asked to check by name. (Fork B may independently cover the practice-specific framing;
the underlying code mechanism is this one.)

---

## Summary table

| # | Scenario | Verdict |
|---|---|---|
| 1 | OCR confidence → classification confidence | CONFIRMED DEFECT — fully decoupled; `ocr_confidence` is a hardcoded constant, not a measurement |
| 2 | Garbled OCR text | MIXED — no pre-classification quality gate (confirmed); LLM's actual behavior on garbage input is unknown, needs a real-file test |
| 3 | Rotated-page scan | CONFIRMED DEFECT — zero rotation/OSD handling anywhere; degrades into case 2's undetected path |
| 4 | Multi-document combined PDF | CONFIRMED DEFECT — all 4 classifiers read only the head of the whole-file concatenated text; no document-boundary concept anywhere |
| 5 | Incomplete document (missing pages) | CONFIRMED ACCEPTABLE DEGRADATION for classification (head-only reading is unaffected); real gap for extraction/completeness, out of scope |
| 6 | Blank pages | SPLIT — OCR path gracefully filters (acceptable); born-digital `avg_chars` calc can misfire into unneeded OCR (narrow confirmed defect) |
| 7 | Handwritten notes on printed doc | CONFIRMED DEFECT — no mixed-content awareness; same fake-constant confidence issue as case 1 |
| 8 | Combined "spis" bundle | CONFIRMED DEFECT — same mechanism as case 4, Serbian-practice framing |

## Phase 5 summary

| Classifier | Pipeline(s) | Confidence field? | Escape hatch? | On uncertainty, does today |
|---|---|---|---|---|
| `shared/intake_classify.py` | B | Yes, real (heuristic 0.85 fixed / LLM self-reported) | Yes — `AUTO_ACCEPT_THRESHOLD=0.90` → `intake_review_queue` | Correctly routes to review |
| `routers/evidence.py::_klasifikuj_dokument` | A (only classifier), C (stage-2, overwrites B's value) | No | No | Silently returns `"ostalo"` on error; on Pipeline C, unconditionally overwrites B's confidence-gated value regardless of B's confidence or review status |
| `api.py::_detect_doc_type` | ephemeral, prompt-routing only | No | No | Always returns one of 3 fixed buckets; wrong guess silently picks the wrong analysis template |
| `routers/dokument.py::_klasifikuj_dokaz` | ephemeral, Q&A only | `snaga_dokaza` (evidence strength, not classification confidence) | No | Silently returns `"ostalo"`/`"niska"` on error |

Review-queue surfacing: only `GET /api/smart-intake/jobs/{job_id}` (`routers/smart_intake.py:217-264`) reads
`intake_review_queue`. No case-file/document view anywhere else does. Finalize
(`routers/smart_intake.py:409-502`) neither checks for an unresolved review entry nor carries the confidence
number into `predmet_dokumenti` — and whatever `document_type` value *does* survive finalize is then
unconditionally overwritten by the confidence-blind Pipeline A/C classifier (`smart_intake.py:778-811`) every
single time, regardless of the original confidence or review state (§1.6b). This is a sharper and more severe
characterization of Sprint 001's already-tracked `INTAKE-003` than "discarded" — the signal is not just lost,
it is actively replaced by a worse one.

No code was modified. No files outside `.vindex_ai_team/decisions/` were touched.
