# NS3-A independent review — PDF raster pre-check (extractor.py)

Subject: ns3/pdf-ocr d7a4e4a8/88c593a0/76d54093 (base da345f26). Worktree C:/vindex-ns3/review-a @76d54093.
Measurements: in-process on **Windows, psutil peak_wset / RSS**, pymupdf 1.28.2 — NOT production Linux/gunicorn; treat as relative, not absolute prod MiB.

## VERDICT: GO WITH NOTES
The fix correctly and accurately kills the *proven* class (full-page CMYK/RGB/progressive JPEG + raw-stream raster OOM). It is cheap, has no false rejections of ordinary legal docs, and tests are strong. It does **not** make the W=1/512 MiB worker OOM-proof against uploads: one declared residual is exploitable at trivial nesting, and there is one undeclared CPU-DoS.

## What holds (PROVEN, my fixtures + probes)
- Recording device does **not** decode / does not fill the store. Check peak ≤ ~2 MiB for image PDFs, ≤22 MiB worst (poly/pdf_c30 = JPEG-header read), store stays 0; render of same page adds +85–176 MiB. extractor.py:525-586, test_provera_ne_dekodira (3000x4000 JPEG: check +0, render +34).
- Estimate ≥ actual and tight: across ~30 fixtures est vs render peak within +0..+3 MiB (RGB/gray/raw); CMYK conservative. Rejections at real cost: ok_rgb600 est174/render176, ok_cmyk400 est153/render156, fl_cmyk_7000x5700 est316, pdf_c30 CMYK30MP est250.
- No false rejection of ordinary docs: phone 12/16 MP JPEG, A4/Letter 300 dpi RGB/gray/CMYK, 600 dpi bitonal (CCITT-class Flate 1-bit), 16-bit RGB, 300-page 150-dpi scan, DeviceN n=8 — all ACCEPTED. Only ≥600-dpi RGB and ≥400-dpi CMYK full-page scans rejected (genuinely heavy; declared residual).
- Bypass paths from the prompt are covered: images via nested Form XObject in patterns, annotation /AP/N, tiling pattern fill, filter chains (AHx+DCT, Flate+DCT), encrypted empty-pw, broken-xref/repair, OCG-off, TIFF+PDF polyglot (→PORUKA_NIJE_PDF), inline BI across 64 KiB boundary and in strings — all rejected-or-safe in my runs. JPX declared-huge-vs-tiny: device reads real codestream dims, safe.
- Cost: check 0.00–0.01 s typical; 300-page digital PDF 0.08 s, +1 MiB. No memory DoS from the check itself.
- Mutations (my own, CRLF-correct, byte+sha256 restore verified): M1 inline-scan→[] = 8 failed; M2 image-cache=0 = 16 failed; M3 reject disabled = 14 failed; M4 mask-layer stek=0 = 2 failed. All killed. Author's 33 tests pass (82 with ns2b). (Note: naive LF replacements silently no-op on this CRLF file — a real mutation-harness trap, cf. feedback_mutation_harness_binary_mode.)

## FINDINGS

### N1 — Nested transparency groups bypass the estimate and OOM the worker (HIGH, PROVEN; author-DECLARED residual, shown exploitable)
The recording device (FzDevice2) overrides fill_image/clip only, not begin/end_group, so transparency-group layers are never counted; estimate stays at bare page raster (66 MiB) while MuPDF allocates ~75 MiB (page-size RGBA layer) **per nested group** at render.
Measured (render peak over pre-check RSS, in-proc Windows): groups_4 **+316**, _12 **+913**, _16 **+1212**, _20 **+1511** MiB. Source files 2–5 KB, well under the 25 MB upload cap, ACCEPT with est=66.
Concrete input: a 1-page PDF whose Contents is `/G Do` with G a chain of N full-page Form XObjects each `/Group<</S/Transparency/I true/K true>>` drawing the next + a fill. At N≈4 (≈2.3 KB) prod base ~240 + ~316 ⇒ >512 ⇒ OOM-kill — the exact failure this patch exists to prevent, via a path it explicitly leaves uncounted (extractor.py:499-503 residual note). ExtGState /SMask luminosity groups are the same class. Benign single page /Group (Word/LibreOffice export) is safe (+141 MiB) — this needs adversarial nesting, so it is a DoS note, not a normal-user regression.
Fix direction: count group pushes (begin_group/begin_mask) as page-size layers in the device, like clip_image_mask already does; or cap nesting depth of transparency groups during the scan.

### N2 — Exponential non-stream object graph = CPU-DoS under the global OCR lock (MEDIUM, PROVEN; UNDECLARED)
`_tokovi_sadrzaja_strane` memoizes only **streams** (`vidjeni.add(num)` sits inside the `pdf_is_stream` branch, extractor.py:644-648); a dict/array referenced by many parents is re-walked every time. A chain of N dicts each `<</a X 0 R /b X 0 R>>` reachable via annotation /AP/N (or Resources) → 2^N traversal. The `dubina>64` guard (line 642) does not help: depth stays = nesting (≤22), branching is the blow-up.
Measured (check only): dag_16 **0.52 s**, dag_20 **8.2 s**, dag_22 **33 s** — clean 2^n; ~2 KB file. dag_26 ≈ 10 min. Runs inside `_RASTER_OCR_LOCK`, which serializes *all* rasterization/OCR in the process ⇒ one crafted 2 KB upload stalls every document the worker handles.
Fix direction: add visited-set memoization for all object numbers (dicts/arrays too), or a global node-visit budget.

### N3 — Threshold is brittle for heavy-but-legitimate scans (LOW, INFERRED; author-declared)
400-dpi A4 CMYK (est 153) and ≥600-dpi RGB/CMYK full-page scans are rejected. Defensible (they really peak 156–176 MiB), but a firm whose scanner defaults to 400-dpi colour will hit PORUKA_PREVELIK_JPEG_PDF on otherwise-valid filings. Message is plain, accurate Serbian and distinct from PORUKA_PDF_NEPROVERLJIV / PORUKA_NIJE_PDF (reviewed 356-363, 508-511, 282). No code change required; product awareness only.

## Messages / status (PROVEN by reading + tests)
PORUKA_* are plain Serbian, accurate, three distinct causes: too-large (413/PREVELIK_JPEG_PDF), unverifiable (PDF_NEPROVERLJIV), not-a-PDF (NIJE_PDF). Worker-terminal via DocumentSafetyLimitExceeded, re-raised past the generic except (1084, 1209), no retry loop. Locks released after reject (test_ponovna_obrada: _DOKUMENT_LOCK/_RASTER_OCR_LOCK both free).

Bottom line: merge the fix for its scope, but do not describe it as "uploads can no longer OOM the worker" — N1 (declared) and N2 (undeclared) remain. N2 ideally fixed before beta; N1 is a known residual to track.

---
## Re-review of delta cc0a6d6f (N1/N2 fix) — read-only, in-process Windows probes, existing fixtures only
VERDICT: GO WITH NOTES
- Tests: 88/88 pass (ns3_a + ns2b), `-p no:randomly`.
- N1 CLOSED (PROVEN): groups_4 now REJECT est 356 (render measured at 76d54093: +316); groups_20 REJECT est 1551 (render +1511). The estimate is above the measured render in both cases; the check itself costs +0 MiB.
- N2 CLOSED (PROVEN): dag_16/dag_22 now take 0.00 s (were 0.5 s / 33 s). Each indirect object is visited once (`nov()`, extractor.py ~671-682), so the walk is linear; the 20k budget sits behind that.
- Ordinary docs (PROVEN): phone12, cmyk300, gray600, bitonal600 and the 300-page scan (0.08 s) are still ACCEPTED. Page-level /Group + 12 MP scan ACCEPT est 139 (render was +141, so it is accurate). The gstate luminosity soft mask + 12 MP scan is ACCEPTED at est 142 (render was +143).
- Accounting by reading (INFERRED, not separately probed): layer area is clipped to the page (`_sloj`), so /Matrix scale or tiny-bbox tricks can't make a layer exceed page size. Sibling groups pop on end_group, so they don't add up. Patterns, annotations and Type3 go through the same fz_run_page device. Image /SMask goes through clip_image_mask, which is unchanged and already counted. The budget is per page, so a big digital document would only hit it if a single page referenced more than 20k objects (unlikely for ordinary pages; not measured).
- NOTE (LOW, PROVEN for this fixture): tg_2lvl_phone12 (page group + one nested knockout form group around a 12 MP scan) is now REJECTED at est 217, but its measured render was +177 MiB. So the estimate is about 40 MiB conservative when a knockout group is open while an image is drawn: `prolazno` already includes `stek`, and the ×9 B/px knockout factor is high. That causes false rejections for this shape. Non-knockout nested groups compute to about 130 (accepted) by the formula. This only matters if real exports use nested knockout groups; worth one real Word/LibreOffice sample before beta.
- Scope note: I deliberately did not build new adversarial variants in this pass. The bypass items above are covered by reading the code, not by new probes.
