# NS3-B independent adversarial review — dfae3dbe (base da345f26)
Worktree C:/vindex-ns3/review-b (detached, kept). Probes: scratchpad/ns3/img-format/rb_probe{1..4}.py, rb_mut.py, data in rb_data/.
Memory numbers are Windows in-process peak_wset deltas, not production RSS (INFERRED, not prod proof).

## VERDICT: GO WITH NOTES (no blocking defect in the NS3-B diff)

## Attack results on the image path (all PROVEN by execution unless labeled)
- CMYK TIFF 7000x5700 renamed .jpg -> extract(): DocumentSafetyLimitExceeded before open, delta +1 MiB (was +347 MiB class).
- JPEG SOI + TIFF body (`FF D8 FF` + TIFF) -> Pillow(formats=JPEG,PNG) UnidentifiedImageError. JPEG-LS (`FFD8 FFF7`) -> rejected. PNG sig + GIF junk -> rejected.
- MPO: small 800x600 frame0 + 40 MP frame1 -> delta 96 MiB == identical to plain 800x600 JPEG and MPO+tiny frame (96 MiB = OCR baseline). Later frames never decoded. MPO with progressive 4:4:4 30 MP frame0 -> rejected by JPEG estimate (200 MiB > 150) before decode.
- JPEG content named .png (progressive 30 MP, and CMYK 30 MP) -> rejected by the JPEG estimate (200 / 258 MiB). Guard is content-based (_jpeg_okvir), so it runs regardless of suffix.
- APNG 4 frames x 40 MP: same peak as single-frame PNG (only default frame decoded).
- Hierarchical SOF5 / lossless SOF3 synthetic headers: open, then fail on decode (OSError -> invalid_image, no false success).
- Entry points: only one enqueue_job site (routers/smart_intake.py:240); routers/dokument.py:33 allows only .pdf/.docx; drafting uses extract_docx/extract_txt only; no other PIL/pytesseract users besides extractor/intake_worker. Finalize (smart_intake.py:1743) re-runs extract() -> check applies (defense in depth). No bypass via another image route found.
- Ordering: api.py:5976-5980 raises 415 right after read, before any storage/tempfile; smart_intake.py:191-194 returns ok:false before sha/storage/enqueue. PROVEN by reading + author tests (extract/encrypt/enqueue mocks at correct import sites: function-local imports resolve module attrs at call time).
- Worker: DocumentSafetyLimitExceeded -> mark_job_failed(attempts, attempts+1) -> is_dead_letter True on first attempt (intake_queue.py:154-155). PROVEN by reading.
- Targeted tests: 120 passed (5 files, -p no:randomly, OPENAI_API_KEY=x).

## Findings (ranked)
1. [P2, PROVEN, OUT OF NS3-B SCOPE -> Task A] PDF route decodes embedded non-JPEG rasters unguarded. A genuine PDF with a Flate CMYK 7000x5700 image (288 KiB) -> extract() delta +434 MiB (peak 502 MiB). A TIFF+minimal-PDF polyglot named .pdf passes pypdf (1 page) and MuPDF opens it as TIFF (is_pdf=False) with the same +434 MiB -> the polyglot is NOT a unique bypass of NS3-B; it is the known "raster of non-JPEG image in PDF not measured" gap (extractor.py comment at ~L338). Reachable via /api/predmeti/{id}/upload (10 MB) and Smart Intake (25 MB).
2. [P3, PROVEN by reading] Legacy UI misreports the new 415: static/vindex.js:20534-20535 shows hard-coded "Podržani formati: PDF, DOCX" (implies photos unsupported; ignores detail=PORUKA_NIJE_JPEG_PNG). V2 Dosije (v2/features/dosije/view.js:304 -> v2/platform/errors.js:49) shows "Ova vrsta fajla nije podržana. Prihvataju se PDF, DOCX, DOC, JPG i PNG." — true but not actionable for a ".jpg" that is really TIFF. Smart Intake legacy + frontend-v2-ng show `greska` verbatim (truthful). No client breaks on 415 (both map it explicitly).
3. [P3, PROVEN by reading, pre-existing NS2b] frontend-v2-ng/src/prijem-predmeta.js:185 renders failed jobs as "Obrada nije uspela posle više pokušaja" and never shows last_error — untrue for the 1-attempt dead-letter. Affects only image jobs stored before deploy (new ones are rejected at entry). Legacy poll shows last_error (vindex.js:22170).
4. [P3, PROVEN measurement, pre-existing] PNG is covered by the 40 MP pixel count, not by a memory estimate: RGBA 6320x6320 -> +283 MiB, I;16 -> +207 MiB (both > the 150 MiB JPEG budget). NS2b comment says 40 MP PNG was measured safe in prod topology — ASSUMED here, not re-verified.
5. [P3, PROVEN] Test gaps (my mutations): M1 drop formats= on the OCR Image.open (extractor.py:951) SURVIVED; M3 JPEG sig -> `FF D8` SURVIVED; M8 PNG sig -> `\x89PNG` SURVIVED. M1/M3/M8 are equivalent inside extract_image (Pillow _accept needs FFD8FF / full 8-byte sig and the signature gate precedes), but for the entry checks a weakened signature would store + enqueue non-image bytes (ends as invalid_image, no false success). Killed: M2 probe formats, M4/M5 suffix scope, M6 +TIFF, M7 generic message. All restored, sha256 verified.
6. [UNKNOWN, NS2b scope] Real lossless JPEG (SOF3): the estimate assumes draft() DCT scaling; whether libjpeg-turbo in Pillow 12.3 honors scaling for lossless is untested (no encoder available).
7. [Note] api.py:5979 logs client filename at WARNING — consistent with existing lines 6057/6061, not new exposure class.

No cross-user leakage path introduced (checks are pure byte checks before any per-user I/O). No new formats, no new UI components, PDF/DOCX branches untouched by the diff.
