# Review A — ns2b/ocr-jpeg @ befe2300 (base dd619e9a)

VERDICT: GO WITH NOTES — F1 must be fixed before merge. It is a one-line fix, and 46/46 tests still pass with it.
Review worktree: C:/vindex-ns2b/review-a (detached at befe2300; clean after the mutations, sha256-verified). Scripts and synthetic files: ns2b/ocr-jpeg/review_a/.

## Findings (by severity)
F1 HIGH, PROVEN: the parser fails open on a segment length of 0 or 1, which defeats the check on both the photo path and the PDF path.
  uploaded_doc/extractor.py:395-396: `if ... int.from_bytes(duzina) < 2: return None`. The docstring says that when the parser returns None, libjpeg would reject the file anyway. That is false here. libjpeg skip_variable and Pillow `_safe_read(size<=0)` both accept length 0/1 as an empty segment and carry on decoding.
  Input: the measured OOM case (40 MP 7744x5164 progressive 4:4:4, 229 MiB of coefficients) with the 4 bytes `FF FE 00 00` inserted after SOI.
  Results:
    - Original file: REJECTED (estimate 238 MiB).
    - Crafted file: `_jpeg_okvir`=None, then extract_image ACCEPTED and ran OCR, with peak working set +241 MiB locally. The author measured ~494 MiB for this file in the 512 MiB container, i.e. OOM.
    - COM length 1 and APP15 length 0 behave the same way.
    - PDF: the same file as an xref image gives `_odbij_jpeg_u_pdf` NOT REJECTED, and MuPDF renders it.
  Fix (verified in review-a, then restored): `if len(duzina) < 2: return None` and `n = max(0, L - 2)`. With it, all three crafted variants are estimated at 157 MiB and rejected, and 46/46 tests pass. Add a test for this.
F2 MEDIUM, PROVEN (crafted PDFs only): further blind spots in the PDF pre-raster check, on top of the known baseline-CMYK HOLD.
  (a) Filter chain `[/ASCIIHexDecode /DCTDecode]`: the 40 MP progressive 4:4:4 image is NOT REJECTED and renders. This is documented in the docstring.
  (b) Inline image (`BI /F /DCT ID ... EI`) in the content stream: get_images returns 0 images, so it is NOT REJECTED, and it renders (mean pixel 127). This is NOT documented.
  (c) Images in annotation appearance streams: not listed by get_images (INFERRED). Recommendation: document (b) and (c) next to the HOLD. Fixing them is a scope decision.
F3 MEDIUM, PROVEN, pre-existing (not a regression): extract_image (extractor.py:893-918) calls `Image.open` with no format allowlist. A 2.2 MB LZW CMYK TIFF 7744x5164 renamed `.jpg` was ACCEPTED, with peak working set +347 MiB. The new estimate covers JPEG only, and api.py:5872 checks only the client's content_type.
  Minimal fix: `Image.open(path, formats=("JPEG", "MPO", "PNG"))`. This is outside the approved decision, so it needs a founder decision.
F4 LOW, PROVEN (numeric, ns2b/ocr-jpeg/review_a/tab.py): legitimate-looking inputs that get rejected. All of them are consistent with the author's measured OOM peaks. The draft floor (A4@300) means no downscaling between 15 and 34.8 MP.
  - Baseline CMYK 17.5–34.7 MP: 18 MP gives 154 MiB, A4@500dpi gives 207, Letter@600 gives 288, all REJECTED.
  - A4@600 CMYK 4960x7016 gives 74 (accepted), but 4961x7016 is REJECTED. The rule is non-monotonic and sensitive to boundary sizes.
  - Progressive 4:4:4 above ~22.4 MP: a 24 MP camera file gives 160 REJECTED.
  - Phone files are all accepted: 12/24/40 MP baseline or progressive 4:2:0 come out at 19–124 MiB.
  The user message tells the user to save the file again. Acceptable as true positives, not false rejections.
F5 LOW, PROVEN: mutation `px <= MAX_OCR_PIXELS` → `<` (extractor.py:437) survives. It only changes the result at exactly 15,000,000 px, so it is nearly equivalent. The other 7/8 of my mutations were killed: `<=granica`, `d[0] < nf`, draft order, CMYK ×5, threshold 160, resize term, worker max_attempts.
F6 UNKNOWN: SOF3 lossless (in _JPEG_SOF) and 12-bit precision with Pillow 12.3 / libjpeg-turbo 3. Lossless decoding may ignore draft scaling, so the estimate would assume a downscaled decode that does not happen. I could not test this: there is no lossless encoder available locally.

## Checklist items
1. Parser: sees the same markers as libjpeg for FF fill bytes, junk bytes, RST/TEM, duplicate SOF, hierarchical SOF, bad sampling, truncated files, and MPO frame 0. PROVEN by tests plus my probes. The one exception is F1. An exception inside the parser goes to `except Exception`, which returns "invalid image": fail-closed, PROVEN by reading the code.
2. Entry points: PIL and fitz are imported only in uploaded_doc/extractor.py (PROVEN, grep). The callers are:
   - api.py:6029 and routers/dokument.py:261: return 413.
   - intake_worker (this is also the Smart Intake path): dead-letter.
   - drafting: docx/txt only.
   necitljive_strane_pdf converts a DSLE into None.
3. The estimate follows the real path: same `math.ceil` target as `_u_granici_ocr`, and the same (8,4,2,1) choice as Pillow 12.3 `JpegImageFile.draft`, read from source. draft("L") changes only RGB (CMYK stays 4 B/px), and the no-draft branch applies when px ≤ 15 MP. PROVEN by reading the code. I did not re-measure the author's ±2 MiB claim.
4. See F4.
5. Error handling:
   - The 413 message is plain Serbian with no memory figures. The reason (dimensions only) goes only to the log. PROVEN: code reading plus the 2 route tests.
   - Worker: extract runs before create_document (intake_worker.py:274 vs 286). `isinstance` is exact. `max_attempts = attempts + 1` means `new_attempts >= max`, i.e. dead-letter, and nothing is marked processed (PROVEN). Other jobs are not affected.
   - Side effect (INFERRED, acceptable): the pre-existing zip-bomb, 40 MP and page-limit DSLE now also dead-letter immediately.
6. Revert befe2300 is clean (PROVEN, diff 0db59e19..befe2300): `_mupdf_dekodiran_raster`, `get_image_rects` and the `dpi` variable are all removed. The only remaining mention is in the docstring. `_odbij_jpeg_u_pdf` calls only get_images, xref_get_key and xref_stream_raw. It is called under the lock before the first rasterization in extract_pdf:683, _ocr_strane_pdf:589 and necitljive:791. No dead code.
7. Tests: `pytest -p no:randomly tests/test_ns2b_ocr_jpeg_koeficijenti.py` gives 46 passed. Without OPENAI_API_KEY in the environment, 2 route tests fail at import (OpenAIError). That is environment-only; with a dummy key they pass.

Not done: measurements in a 512 MiB container, the full test suite, and anything touching production.
