# Segmentation Edge Case Validation Report — Program Intake Sprint 005 (2026-08-05)

Mission requirement (Phase 7): mandatory testing across single/multi-document, blank pages, rotated pages,
duplicate pages, mixed document types, incomplete last document, incorrectly-OCR'd pages, and very large PDFs
(300–500 pages) — proving segmentation *behavior*, not improving OCR itself.

## Pure engine tests — `tests/test_intake_segment.py` (18 tests, all passing)

| Test | Edge case proven |
|---|---|
| `test_single_page_is_always_one_segment` | Single document |
| `test_ordinary_multi_page_document_stays_one_segment` | Ordinary multi-page document, no false split |
| `test_boilerplate_pouka_o_pravnom_leku_does_not_trigger_false_split` | Named mission false-positive: a rešenje's own "Pouka o pravnom leku" footer mentioning "žalba" mid-sentence |
| `test_inflected_form_of_heading_keyword_does_not_falsely_trigger_split` | **Real bug found and fixed this sprint**: Serbian inflection ("zahtevu") vs. the heading keyword ("ZAHTEV") — word-boundary matching required, plain substring containment is unsafe |
| `test_quoted_case_number_and_court_in_appellate_reasoning_does_not_split` | An appellate rešenje quoting the lower court's case number inline — quoted history, not new identity |
| `test_punomocje_attached_annex_does_not_auto_split_alone` | A punomoćje annex with thin evidence routes to review, not silent auto-split |
| `test_two_documents_with_new_letterhead_and_case_number_auto_splits` | Multi-document (2), auto-split on 2 strong signals |
| `test_ten_documents_each_correctly_bounded` | Multi-document (10), all boundaries correct |
| `test_mixed_document_types_all_correctly_identified_as_separate` | Mixed document types in one bundle |
| `test_blank_separator_page_assigned_to_preceding_segment_not_orphaned` | Blank pages between documents — assigned, never orphaned |
| `test_duplicate_pages_no_page_lost_or_double_counted` | Duplicate pages — every page accounted for exactly once |
| `test_page_counter_reset_corroborates_a_split_with_new_heading` | Page-counter reset as corroborating evidence |
| `test_page_counter_alone_without_heading_is_only_corroborating_not_sufficient` | Page-counter alone is not sufficient to auto-split |
| `test_incomplete_last_document_still_gets_its_own_segment` | Incomplete last document (bundle cut off) still gets its own identity |
| `test_large_pdf_300_pages_no_page_lost_or_duplicated` | Very large PDF (300 pages) |
| `test_large_pdf_500_pages_with_20_bundled_documents_all_pages_accounted_for` | Very large PDF (500 pages, 20 bundled documents) |
| `test_garbled_ocr_text_degrades_to_no_split_not_a_false_split` | Incorrectly-OCR'd/garbled text — degrades to conservative "keep as one," never a false split |
| `test_uncertain_boundaries_never_overlaps_confirmed_segments` | Confirmed splits and uncertain-but-thin boundaries are mutually exclusive, never double-counted |

**Rotated pages**: this sprint's engine operates on already-extracted TEXT, not page images/geometry — a
rotated page's effect on segmentation is whatever effect it has on OCR text quality, which is exactly what
`test_garbled_ocr_text_degrades_to_no_split_not_a_false_split` covers (garbled/degraded text → conservative
no-split, never a false split). Per the mission's own explicit instruction ("do not improve OCR — prove
segmentation behavior"), rotation-specific OCR quality is out of this sprint's object of study; the
segmentation engine's *response* to degraded text from any cause (rotation included) is proven.

## Worker integration tests — `tests/test_sprint005_segmentation_worker.py` (6 tests, all passing)

Exercise the REAL engine (not a mocked one) against the real `shared/intake_worker.py::_process()`/
`_process_segments()` orchestration:

| Test | Proves |
|---|---|
| `test_ordinary_multi_page_upload_creates_no_segment_rows_stays_one_document` | Byte-for-byte pre-Sprint-005 behavior for the common case — zero `intake_job_segments` rows |
| `test_two_bundled_documents_produce_two_segments_and_two_documents` | Multi-document hand-off: 2 segments → 2 independent `intake_documents` rows via the existing classification pipeline |
| `test_one_segment_permanently_failing_does_not_lose_or_block_its_sibling` | Partial failure recovery (Phase 6) — retry, then dead-letter, sibling unaffected |
| `test_resume_skips_already_completed_segment_only_processes_pending_one` | Resume after crash — already-resolved segments never reprocessed or duplicated |
| `test_thin_segmentation_evidence_routes_to_review_without_splitting` | Mission's own conservatism mandate, at the worker level: thin evidence stays whole AND routes to human review |

## Regression suite

Full suite (`python -m pytest tests/ -q`) run at the end of this sprint's implementation pass. The extractor
contract change (`tuple[str, bool, bool]` → `tuple[str, bool, bool, Optional[list[str]]]`) rippled into 42
pre-existing test failures across 12 files (direct unpacking or hardcoded 3-tuple mock `return_value`s) — all
identified and fixed as a mechanical consequence of the contract change, not a design defect. **Confirmed final
result: 2555 passed, 1 skipped, 0 failed** (includes the 24 new Sprint 005 tests) — zero unresolved
regressions from this sprint's changes.

## Success criteria checked against this report

- One canonical segmentation system exists — `shared/intake_segment.py`, one entry point, no competing logic.
- No page lost, no page duplicated — proven directly (duplicate-pages test, large-PDF tests, boundary-overlap
  test).
- Every segment has an identity — see `SEGMENT_IDENTITY_SPECIFICATION.md`.
- Every segment enters the existing classification pipeline — proven (`test_two_bundled_documents_...`).
- Partial failure does not bring down the whole upload — proven (`test_one_segment_permanently_failing_...`).
- All technical problems found within segmentation scope that are solvable were implementation-fixed — see
  Mission Report §1 (the inflected-keyword false positive, the orphan-document retry guard, the
  `.maybe_single()` resume-ambiguity bug).
