# Mission Review — LD-001: Fix photo upload on the actually-reachable upload path

**Mission Board entry:** `MISSION_BOARD.md`, LD-001.
**Executed by:** Operation Lawyer Day (BETA-004), 2026-08-03.
**Status:** DONE.

---

## Architecture Decision

### The finding, and why it corrects a previous claim
Night Shift's M-001 (2026-08-02) declared "photo upload now works end to end" as a removed Beta
Critical Path blocker (scenario #3). That was true for the code it touched — `uploaded_doc/extractor.py`
gained real image-OCR support, and `routers/smart_intake.py`'s own upload validation was widened to
accept it. What M-001 did not check: whether the endpoint it fixed is one a lawyer can actually reach.
It is not (`ZTC-000`, this engagement's standing Blocker Report) — Smart Intake has zero frontend
callers. `api.py:4133`'s `POST /api/predmeti/{id}/upload` is the only document-upload path reachable
from the app today, and its own `_ALLOWED_MIMES`/`_ALLOWED_SUFFIXES` allowlist was never updated. A
lawyer with phone photos of a document — found during this mission's full-day workflow simulation, not
by re-auditing M-001 directly — could not upload them anywhere in the app, three sessions after the
underlying capability was declared shipped.

### Why this was small, safe, and fully verifiable (this mission's own bar for same-night implementation)
`uploaded_doc/extractor.py::extract()` already dispatches `.jpg/.jpeg/.png` to `extract_image()`
(`extractor.py:301-311`) with the exact same `(text, is_scanned, ocr_used)` return contract
`api.py:4192` already consumes for PDF/DOCX. `extract_image()`'s own docstring
(`extractor.py:247-256`) explicitly names *"api.py's auto-analyze upload"* as a caller that needs zero
special-casing — the fix was designed to reach this exact endpoint and simply never got applied here.
This made the change a pure allowlist widening, not new logic.

### A second, smaller fix bundled in (same ticket, per this project's own scope rule)
The endpoint's OCR-failure error message said "Skenirani PDF — ..." (Scanned PDF — ...), which would
now also fire for a failed image OCR and be misleading. Reworded to be format-neutral. Same user-facing
error path, same fix.

---

## Implementation
`api.py` — `_ALLOWED_MIMES` gains `image/jpeg`/`image/png`; `_ALLOWED_SUFFIXES` gains
`.jpg`/`.jpeg`/`.png`; the OCR-failure error message reworded.

---

## QA Report

### User Scenario Test
```
Scenario: a lawyer photographs a document a client just handed them and
uploads it to the case they're already viewing.
Before: HTTP 415, "Podržani formati: PDF, DOCX" -- no workaround anywhere
in the reachable app.
After: accepted exactly like a PDF, reaches the same OCR -> RAG-enriched
analysis -> chronology -> evidence-classification -> Case Genome pipeline
this endpoint already runs for PDF/DOCX.

PASS -- tests/test_lawyerday_predmet_upload_images.py, 5/5:
- .jpg accepted, reaches extract()
- .png accepted, reaches extract()
- genuinely unsupported format (.exe) still rejected with 415 BEFORE
  reaching extract() -- proves the guard was widened, not removed
- .pdf's existing acceptance unaffected by the widening
- direct assertion that both new MIME types and both new suffixes are
  present, guarding against an accidental future revert of this exact fix
```

### Regression suite
5 new tests, all passing. Full suite: 2311 passed, 1 skipped, 0 failed (was 2306 before this mission's
work).

### Rollback strategy
Pure application code — two `set` literal widenings plus a string change. No schema/migration. Revert
restores the pre-fix (broken) behavior exactly.

---

## Lessons Learned
A "beta blocker removed" claim needs to be checked against the path a real user actually exercises, not
just the path the fixing mission happened to touch. M-001 was correct about the code it wrote; it was
wrong (silently, for three sessions) about whether that code was reachable. Worth a standing check for
any future "we fixed X" claim in this engagement: which endpoint does the *frontend* actually call for
this scenario, and is it the one that got fixed?

## Founder Summary
A lawyer can now upload a phone photo of a document to a case — the one upload path the app's UI
actually uses. This corrects a beta-blocker claim from three sessions ago that turned out to only be
true for an endpoint no lawyer can reach. 5 new tests, zero regressions.
