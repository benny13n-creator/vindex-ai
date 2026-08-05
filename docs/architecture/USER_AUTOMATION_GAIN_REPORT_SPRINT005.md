# User Automation Gain Report — Program Intake Sprint 005 (2026-08-05)

Mandatory metric: before this sprint, how many manual steps did a lawyer perform when entering a
multi-document PDF? After this sprint, how many does the system now do? Provable scenarios only, no marketing
estimates.

## Scenario: a lawyer uploads one 5-page PDF containing a tužba (pages 1–3) and a punomoćje (pages 4–5),
## via Pipeline B (the durable Smart Intake queue worker — the only pipeline this sprint wired to segment)

### Before Sprint 005

The system had no concept of "this file contains 2 documents." `IntakeWorker._process()` always created
exactly one `intake_documents` row per `intake_jobs` row, classified against the whole 5-page concatenated
text, and extracted entities from the whole text as one input.

Manual steps a lawyer had to perform:
1. Notice, on their own, that the classification/extracted fields look wrong or incomplete (the system
   classified the *whole* 5 pages as one type, likely biased toward whichever document's content dominated,
   with entity extraction confused by two documents' worth of case numbers/parties/dates mixed together).
2. Manually determine that the file actually contains 2 separate documents.
3. Manually split the PDF into 2 separate files themselves (outside the product, using their own PDF tooling).
4. Re-upload the punomoćje as a second, separate file.
5. Wait for the second file to classify/extract independently.
6. Manually verify BOTH resulting documents are now individually correct.

**Manual steps: 6** (notice, diagnose, split, re-upload, wait, re-verify) — none of which the system offered
any assistance for; the lawyer had to recognize the problem existed at all before doing anything about it.

### After Sprint 005

`segment_document()` detects the case-number change + new heading (ПУНОМОЋЈЕ) at page 4 — 2 strong signals,
clears the auto-split bar. `_process_segments()` creates 2 `intake_job_segments` rows and runs the existing
classification pipeline independently on each: segment 1 (pages 1–3) classifies as the tužba with its own
correct entities; segment 2 (pages 4–5) classifies as the punomoćje with its own correct entities. Both
`intake_documents` rows exist under the same `intake_job_id`, each with its own identity, confidence, and
review routing if either is individually uncertain.

Manual steps a lawyer now performs:
1. Review the (correctly split, correctly classified) results — the same "review if uncertain" step that
   already existed for a single document, now scoped per-document instead of conflated across two.

**Manual steps: 1.**

### Automation gain

**5 of 6 manual steps eliminated** for this scenario (notice-there's-a-problem, diagnose-it's-2-documents,
manually split the file, re-upload the second file, and wait-for-a-second-independent-processing-round are all
now done by the system automatically, in the same single upload). The one remaining step — reviewing the
result — is not automation debt; it is the same human-in-the-loop confirmation the product already requires
for any uncertain classification, now correctly scoped to the actual document boundaries instead of a
conflated whole-file result.

## Scenario: a lawyer uploads an ordinary single-document PDF (the overwhelmingly common case)

### Before and after Sprint 005: identical — 0 additional manual steps, 0 additional automated steps.

This is the governing conservatism principle made measurable: `segment_document()` still runs, finds no
confirmed signals, and the job proceeds through the exact same single-document code path as before this
sprint (zero `intake_job_segments` rows written — proven by
`tests/test_sprint005_segmentation_worker.py::test_ordinary_multi_page_upload_creates_no_segment_rows_stays_one_document`).
The User Automation Gain for the common case is correctly **zero**, not a regression, and not a false claim of
improvement where none exists — the mission's own "prove it" standard applied to itself.

## Scenario: thin segmentation evidence (a case number changes but no other signal corroborates it)

### Before Sprint 005: 0 manual steps changed — the system had no way to notice anything at all; a real
second document's presence, if any, could only ever be caught by the lawyer's own unprompted inspection.

### After Sprint 005: the document stays whole (conservatism mandate — never guess), but now surfaces a
`segmentation_uncertain` review entry naming the exact page and evidence found. The lawyer's own inspection
step is now **prompted and pointed at the exact page**, rather than unprompted and unaided.

**This is not counted as a "manual step eliminated"** (a human still decides), but it is a genuine
UAG-adjacent improvement worth naming honestly: an unprompted, unaided inspection became a prompted, evidence-
directed one — the same category of improvement Sprint 004 delivered for low-confidence classification in
general, now extended to segmentation-specific evidence.
