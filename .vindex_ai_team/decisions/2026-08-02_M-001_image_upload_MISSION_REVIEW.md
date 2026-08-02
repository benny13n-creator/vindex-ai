# Mission Review — M-001: Image Upload Support

**Mission Board entry:** `MISSION_BOARD.md`, M-001, priority 1.
**Executed by:** Autonomous Night Shift (founder's Master Prompt v1.0), 2026-08-02.
**Status:** DONE.

---

## Architecture Decision

### Root cause (Phase 1-2: understand before implementing)
Confirmed via direct code reading (not assumption): two independent gaps, not one, both had to be
fixed for image upload to actually work end to end.

1. `uploaded_doc/extractor.py::extract()` dispatched only `.pdf`/`.docx`/`.txt` — no image handler
   existed at all.
2. `shared/intake_worker.py::_guess_suffix()` — the function that decides which extension a
   downloaded blob gets before `extract()` ever sees it — recognized only `.pdf`/`.docx`/`.txt` and
   otherwise **defaulted to `.pdf`**. Fixing (1) alone would have been silently useless: an image job
   would still be guessed as `.pdf`, handed to `pypdf.PdfReader` on raw JPEG bytes, and fail
   identically on every retry — the exact "two functionally-dependent changes, only one fixed" defect
   class this project's Definition-of-Done rule was written to catch (see
   `decisions/2026-08-02_mission001_predmet_klijenti_ARCHITECTURE_DECISION.md`, Revision 3).
3. A third gap, found while reading the actual upload endpoint: `routers/smart_intake.py`'s
   `upload_intake_documents` performed **no suffix/type validation at all** — any file was silently
   accepted, enqueued, and would only fail deep in the background worker with no clear signal to the
   uploader why.

### Alternatives considered
- **Fix only the extractor, assume the worker's suffix-guessing would "just work."** Rejected —
  verified directly that it would not (see point 2 above); this is exactly the kind of unverified
  assumption this project's evidence discipline exists to catch.
- **Add generic MIME-sniffing (e.g. `python-magic`) instead of trusting client-supplied
  filename/mime.** Rejected as unnecessary scope expansion for this mission — the existing codebase's
  own established pattern (`_guess_suffix`, `_ALLOWED_SUFFIXES` elsewhere) already trusts
  filename/mime-type with a safe default fallback; matching that existing pattern is "minimum code
  required," introducing a new dependency for stronger sniffing is not justified by this mission's
  scope.
- **Reuse `fitz`/pymupdf to rasterize the image (mirroring the PDF-OCR path).** Rejected — unnecessary
  indirection; a standalone image is already a raster image, PIL opens it directly with no
  intermediate rasterization step needed.

### Security review
- **Decompression-bomb guard added** (`MAX_IMAGE_PIXELS = 40_000_000`, ~40MP) — same reasoning as the
  existing SEC-007 DOCX zip-bomb guard and PDF page-count cap: PIL exposes declared pixel dimensions
  via `.size` before decoding pixel data, so the check runs before any expensive operation touches the
  buffer. Comfortably above any real phone/scanner photo (typical 8-24MP).
- **Encryption path unaffected** — images flow through the exact same `_encrypt`/AESGCM/Supabase
  Storage path as every other Smart Intake upload; no new code path bypasses encryption-at-rest.
- **No new attack surface on the extraction side** — `extract_image` fails closed (`is_scanned=True,
  ocr_used=False`, empty text) on any exception, matching `extract_pdf`'s existing fail-soft
  contract exactly; a malformed/corrupt file cannot raise an unhandled exception into the worker.

### Dependency review
No new third-party dependencies. `Pillow` (PIL) and `pytesseract` were already required by the
existing PDF-OCR path; this mission reuses both, refactored into two small shared helpers
(`_ocr_image`, `_detect_ocr_lang`) so the PDF-OCR and image-OCR code paths can never silently drift
from each other — a factoring justified by removing ~30 lines of exact duplication, not a speculative
abstraction.

### Workflow review
Traced the full path end to end before considering this done: upload → suffix validation (new) →
storage encryption (unchanged) → queue (unchanged) → worker downloads+decrypts (unchanged) →
`_guess_suffix` (fixed) → `extract()` dispatch (fixed) → `extract_image()` (new) → classification/
entity extraction (unchanged, operates on returned text identically regardless of source format).

---

## Implementation

| File | Change |
|---|---|
| `uploaded_doc/extractor.py` | Added `extract_image()`, `IMAGE_SUFFIXES`, `MAX_IMAGE_PIXELS` guard; factored shared OCR logic (`_ocr_image`, `_detect_ocr_lang`) out of `extract_pdf`'s OCR branch, used by both; `extract()` dispatch updated. |
| `shared/intake_worker.py` | `_guess_suffix()` now recognizes `.jpg`/`.jpeg`/`.png` filenames and `image/jpeg`/`image/png` MIME types, with the same `.pdf` final fallback preserved for genuinely unknown types. |
| `routers/smart_intake.py` | Added `_ALLOWED_UPLOAD_SUFFIXES` and an upfront suffix check in `upload_intake_documents` — unsupported files rejected immediately, per-file, in the same response, instead of silently enqueued. `.doc` deliberately excluded (SEC-028, separately tracked, not newly accepted here). |

**Minimum code required** — no rewrites, no speculative abstractions. The one factoring
(`_ocr_image`/`_detect_ocr_lang`) removes existing duplication rather than adding new structure.

---

## QA Report

### User Scenario Test (required, per this project's Definition-of-Done rule)
```
Scenario: a lawyer uploads a phone photo of a document served on their client.
1. Lawyer selects a .jpg file in the Smart Intake upload dialog.
2. POST /api/smart-intake/documents accepts it (suffix check passes) -> 202,
   job_id returned immediately, same as a PDF upload.
3. Background worker downloads+decrypts, correctly guesses ".jpg" (not ".pdf"),
   routes to extract_image().
4. extract_image() runs OCR (same Serbian+Latin+English language detection
   as the PDF path), returns extracted text.
5. Classification + entity extraction proceed identically to any other
   document, using the OCR'd text.
6. Lawyer sees the same job-status view (GET /jobs/{id}) with tip/confidence/
   entities -- no different code path, no special-cased UI needed.

PASS -- verified via tests/test_smart_intake_upload_validation.py (upload
acceptance) + tests/test_extractor_image.py (OCR pipeline) + 
tests/test_intake_worker_guess_suffix.py (the suffix-guessing link between them,
which is exactly the piece that would have silently broken this scenario if
fixed in isolation).
```

### Failure scenarios exercised
- Corrupt/non-image file uploaded with a `.jpg` name → fails cleanly (`is_scanned=True`, no unhandled
  exception), same contract as a corrupt PDF.
- Oversized image (declared pixel dimensions past the cap) → `DocumentSafetyLimitExceeded` raised
  before OCR runs, propagates through the worker exactly like the existing PDF-page-count/DOCX
  zip-bomb guards do (retried to `max_attempts`, then dead-lettered — a pre-existing worker behavior
  for all non-transient safety-limit exceptions, not something this mission changes or needs to fix).
- OCR yields too little text (<100 chars) → treated as failed, same threshold and same downstream
  review-queue routing as a failed PDF OCR.
- Unsupported file type (`.exe`) → rejected immediately at upload time, never enqueued.
- `.doc` specifically → still rejected (not newly accepted) — SEC-028 remains a separate, tracked gap.
- Mixed batch (one valid image, one invalid file) → each reported independently; one failure doesn't
  affect the other.

### Regression suite
170 tests across `tests/*intake*`, `tests/*extractor*`, `tests/*uploaded_doc*`, `tests/*smart_intake*`
— all passing, zero regressions. 18 new tests added (6 `extract_image`, 7 `_guess_suffix`, 5 upload
validation) — all passing.

### Rollback strategy
Pure application code, no schema/migration, no data touched. Revert the 3 changed files' diff to roll
back completely; the system returns to today's status quo (images silently unsupported), which is
safe, if undesirable — identical low-risk profile to Mission 001 earlier this session.

---

## Regression Report
Zero regressions found. Full related-suite run: 170 passed (152 pre-existing + 18 new), 0 failed.
Full-file diff kept minimal: 3 production files touched, no unrelated changes.

---

## Lessons Learned / Anti-pattern Update
**Confirms, does not introduce, a known anti-pattern this project now has a name for**: a fix applied
at only one of several functionally-dependent points produces no observable improvement (Definition
of Done rule, adopted earlier this session from Mission 001). Here: fixing the extractor alone, or
the worker's suffix-guessing alone, or the upload endpoint's validation alone, would each have shipped
a change that looked complete and did nothing for the actual user scenario. All three were required
and are the *same user-facing functionality* (Mission 001's ticket-boundary rule), so they were
correctly scoped as one mission, not three.

**New, worth tracking as a small follow-up (not blocking, not this mission's scope):** OCR accuracy
on phone photos will likely be materially affected by EXIF orientation (a photo taken in portrait
orientation but stored with a rotation flag, rather than physically rotated pixels) — this repo's OCR
pipeline does not currently correct for EXIF orientation on any path. Flagged for M-007 (OCR Accuracy
Improvements) once that mission has real evidence to scope against, not fixed speculatively here.

---

## Founder Summary
Image upload now works end to end on the Smart Intake path — the #1 priority from the Beta Critical
Path document. The fix required three coordinated changes (extractor, worker suffix-guessing, upload
validation), not one; fixing only the most obvious one (the extractor) would have shipped a change
that looked complete and left the actual scenario broken, which is exactly the trap this project's
Definition-of-Done rule exists to catch. Same-format-support for `.doc` remains a known, separate,
already-tracked gap (SEC-028) — deliberately not touched here. No schema changes, no new dependencies,
170 tests green, local commit only per Night Shift protocol (not pushed).
