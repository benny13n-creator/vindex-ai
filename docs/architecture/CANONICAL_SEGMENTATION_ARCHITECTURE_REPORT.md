# Canonical Segmentation Architecture Report — Program Intake Sprint 005 (2026-08-05)
## "Canonical Document Segmentation"

Mission: one uploaded file is not always one legal document. A single PDF can bundle a podnesak, a presuda,
prilozi, dokazi, and a punomoćje. This sprint builds the ONE system that decides how many separate legal
documents a single upload actually contains, before classification ever runs — replacing "one file = one
document" as the standing pipeline assumption.

**Governing rule, checked at every design decision below**: never split incorrectly on thin evidence. A
wrongly-split legal filing is worse than one correctly-unsplit bundle. Every threshold in this sprint's design
is tuned toward that asymmetry, not toward splitting often.

---

## Phase 1 — Segmentation Audit (what already existed)

Full audit: `.vindex_ai_team/decisions/2026-08-05_intake_sprint005_fork_segmentation_audit.md`. Summary of
confirmed findings:

1. **`uploaded_doc/extractor.py::extract_pdf()` already builds a per-page `list[str]` internally**, both for
   born-digital PDFs (via `pypdf`) and OCR'd PDFs (via `fitz`+`pytesseract`) — and discards it at the final
   `"\n\n".join(pages)` return. This is the single most important prerequisite fact: making segmentation
   possible does not require touching how the extractor *reads* a PDF, only what it *returns*.
2. **DOCX/TXT/single-image have no page concept to reuse.** DOCX pagination is a rendering-time computation,
   not stored in the OOXML the extractor reads; TXT is a flat string; a photographed image is one page by
   construction. Segmentation is therefore necessarily PDF-first — a structural absence for the other formats,
   not a gap this sprint left unfixed.
3. **`uploaded_doc/chunker.py` is a separate concern, not a segmentation signal.** Chunking presupposes one
   already-identified document and slices it into RAG-sized pieces; segmentation discovers how many documents
   exist in the first place. They operate on opposite sides of the document-identity question.
4. **Two previously-undocumented existing "splitting" mechanisms were found and are explicitly NOT reused:**
   - `analiza/segmenter.py` — a real, shipped "Document Segmentation Engine," but for sub-document structural
     units (a contract clause, a judgment section) feeding Forensic Legal Audit / Evidence Vault grounding
     (migration `080_predmet_dokazi_grounding.sql`). A different axis of the word "segment" entirely — this
     sprint's new module (`shared/intake_segment.py`) deliberately does not import from or extend it, and its
     own docstring states the distinction explicitly to prevent the two concepts colliding in a future reader's
     vocabulary.
   - `scripts/ingest_bilten*.py` — a real, working "1 PDF → N documents" splitter, but for bulk court-bulletin
     RAG-corpus ingestion, keyed to one publication's fixed editorial marker (`"аутор сентенце:"`). Proof that
     page-list preservation from `pypdf` is cheap, and a cautionary example that a fixed-marker approach does
     not generalize to an arbitrary lawyer's combined upload.
5. **No schema or UI multi-document awareness exists.** Migration `074_intake_phase1a.sql`'s own table comment
   states *"1:1 sa intake_jobs u Fazi 1A (nema batch-multi-document logike još)"* — the schema's own author
   already flagged this at design time. `static/vindex.js`'s multi-file wizard UI is "N separate files," not
   "1 file containing N documents" — orthogonal to this sprint, unaffected by it.
6. **All 4 extraction call sites share one identical 3-tuple contract**, immediately treated as one atomic
   string: `api.py:4164`, `routers/dokument.py:199`, `shared/intake_worker.py:202`, `routers/smart_intake.py:813`
   — confirming a single natural insertion point (the shared `extract()` contract), not four independent patches.

---

## Phase 3 — Canonical Segmentation Engine (what this sprint built)

**One module, one function, zero I/O**: `shared/intake_segment.py::segment_document(pages: list[PageText]) ->
list[Segment]`. Pure — no `_get_supa()`, no `asyncio`, no network — trivially unit-testable with literal
in-memory input (17 dedicated tests in `tests/test_intake_segment.py`, all mission-mandated edge cases).

**Governing principle**: a job that segments into exactly 1 (implicit) segment is byte-for-byte behaviorally
identical to pre-Sprint-005 processing. Segmentation always *runs* when a per-page breakdown exists, but the
single-segment case is the N=1 instance of the same general algorithm — not a separate "did we even try"
branch anywhere in the engine or its caller.

**Algorithm** (full detail in `CANONICAL_SEGMENTATION_SIGNAL_SPECIFICATION.md`):
1. Detect candidate boundary signals at every page transition (heading keyword change, case-number change,
   page-counter reset, blank-page separator).
2. Apply the combination rule — only 2+ strong signals, or 1 strong + 1+ corroborating, confirm an actual cut.
   Anything thinner is surfaced separately via `uncertain_boundaries()` for human review, never silently
   resolved either way.
3. Build the final segment list from confirmed cuts — every page belongs to exactly one segment, in order, no
   gaps, no overlaps (proven directly by `tests/test_intake_segment.py::test_duplicate_pages_no_page_lost_or_double_counted`
   and the 300/500-page large-PDF tests).

### Contract change that made this possible

`uploaded_doc/extractor.py`'s shared `extract()` contract changed from `tuple[str, bool, bool]` to
`tuple[str, bool, bool, Optional[list[str]]]` across all four format handlers (`extract_pdf`, `extract_docx`,
`extract_txt`, `extract_image`) — the 4th element is the per-page text list for PDF (born-digital and OCR
paths both now return their pre-join `pages`/`ocr_pages` list instead of discarding it), and `None` for
DOCX/TXT/image (a structural absence, documented as such, not a discard).

All 4 call sites were updated to accept the new 4th element (`_pages`, ignored, for 3 of them) — this was a
mechanical, contract-wide change with a real ripple: 42 pre-existing tests across ~12 files that unpacked the
old 3-tuple or mocked it with a hardcoded 3-tuple `return_value` needed updating. All were found and fixed;
the full regression suite passes with zero unresolved failures (see Edge Case Validation Report).

### Scope decision: which pipelines actually segment

Of the 4 call sites, **only Pipeline B (`shared/intake_worker.py`, the durable queue worker) was wired to act
on the new per-page data this sprint.** `api.py` (Pipeline A, synchronous per-case upload), `routers/
dokument.py` (Pipeline A-ephemeral), and `routers/smart_intake.py`'s finalize re-extraction all now receive
the 4th tuple element but discard it (`_pages`), exactly as before this sprint for those 3 call sites.

**Why this is a deliberate scope boundary, not an oversight**: Pipeline B is the only one of the 4 that is a
background job with its own durable per-document lifecycle (`intake_jobs`/`intake_documents`) — segmentation's
own identity/status model (Phase 4/6 below) was designed around that lifecycle. Pipeline A is a synchronous
HTTP request/response call; auto-fanning a single upload into N case-file entries inline, or interrupting the
response to ask "we detected 3 documents — confirm?", is a genuine product/UX decision (matches the audit's
own Phase-1 observation: "each of the 4 call sites may legitimately want to react to a 'multiple documents
detected' result differently"). Extending segmentation to Pipelines A/A-ephemeral/C is recorded in the
Architectural Debt Register as a named, deferred item — not a bounded technical gap this sprint could close
unilaterally without a founder call on product behavior for an interactive upload.

### Persistence layer

New table `intake_job_segments` (migration `093_intake_job_segments.sql`) — see `SEGMENT_IDENTITY_SPECIFICATION.md`
for the full field-by-field design and the reasoning that merged two independently-proposed fork designs into
one schema. New module `shared/intake_segments.py` owns segment lifecycle CRUD, mirroring `shared/
intake_queue.py`'s own job-lifecycle pattern one level down (segments within a job, not jobs within the
queue).

**Only ever populated for a job that segments into 2+ documents.** A job that stays one whole document (the
overwhelmingly common case) writes zero rows to `intake_job_segments` — this is what keeps the single-document
path byte-for-byte identical to pre-Sprint-005 behavior, verified directly by
`tests/test_sprint005_segmentation_worker.py::test_ordinary_multi_page_upload_creates_no_segment_rows_stays_one_document`.

---

## Phase 5 — Classification Hand-off

Every segment enters the *existing* classification pipeline unchanged: `IntakeWorker._classify()` /
`_extract_entities()` — the same functions, called once per segment instead of once per job. No second
classifier was introduced. `shared/intake_worker.py::_process_segments()` is the new orchestration loop; it
calls the same `intake_documents.create_document()` / `insert_entities()` / `create_review_queue_entry()` /
`write_processing_outcome()` functions the single-document path already used, per segment.

---

## Related documents

- `CANONICAL_SEGMENTATION_SIGNAL_SPECIFICATION.md` — Phase 2, full signal vocabulary and combination table.
- `SEGMENT_IDENTITY_SPECIFICATION.md` — Phase 4, schema and identity fields.
- `SEGMENTATION_FAILURE_RECOVERY_REPORT.md` — Phase 6, partial failure isolation and resume.
- `SEGMENTATION_EDGE_CASE_VALIDATION_REPORT.md` — Phase 7, full test inventory and results.
- `USER_AUTOMATION_GAIN_REPORT_SPRINT005.md` — before/after manual-step accounting.
- `SPRINT_005_MISSION_REPORT.md` — Fixed / Canonicalized / Deferred, founder-facing summary.
