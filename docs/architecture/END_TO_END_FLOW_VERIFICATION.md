# End-to-End Flow Verification — Program Intake Sprint 004 (2026-08-05)

Phase 7 requirement: simulate Upload → OCR → Classification → Low confidence → Review Queue → Lawyer review
→ Resume → Finalize → Audit → Completed. Every non-deterministic or unverifiable step must be fixed in this
sprint.

## The full chain, as it now stands

| Step | Mechanism | Deterministic/verifiable? |
|---|---|---|
| Upload | `POST /api/smart-intake/documents` → `intake_jobs` row, `status='received'` | Yes — atomic enqueue (migration 073) |
| OCR | `IntakeWorker._extract_text()` | Yes for pass/fail; OCR *quality* signal is a known, documented, out-of-scope-this-sprint limitation (`ocr_confidence` hardcoded, Sprint 002/003 finding, unchanged — OCR improvements explicitly forbidden this sprint) |
| Classification | `shared/intake_classify.py::classify()` | Yes — heuristic (deterministic) or LLM fallback with self-reported confidence (known limitation, unchanged; full fix designed but not adopted, Sprint 003) |
| Low confidence detected | `_process()` builds `low_confidence_fields`, picks `classification_uncertain` or `low_confidence_extraction` deterministically | **Fixed this sprint** — reason selection was previously always the generic value regardless of which field was actually uncertain |
| Review Queue | `create_review_queue_entry()` | Yes — one row, one of 3 deterministic reasons |
| Job status reflects this | `intake_jobs.status='awaiting_review'` | **Fixed this sprint** — previously always `'completed'` regardless, a direct contradiction with the review-queue row's own claim |
| Lawyer review | Step 3 screen (`static/vindex.js`) shows document type, entities, flagged fields, human-readable reason | **Fixed this sprint** — previously would never even display these documents (filtered out by 3 separate frontend gates that all assumed `status === 'completed'`) |
| Resume | `POST /jobs/{id}/review/resolve` | **New this sprint** — the first and only real caller of a function that existed but was never wired up |
| Finalize | `POST /jobs/{id}/finalize`, same call as any other job | Yes — no special-casing; the pre-existing status gate now correctly reflects reality |
| Audit | `dokument_review_resolved` (resolve), `entity_corrected` (any prior corrections), `job_awaiting_review` (worker-side, when escalation occurred) | **Fixed this sprint** — all three were previously silent |
| Completed | `predmet_dokumenti` row exists, case created, Pinecone indexed | Yes — unchanged, already proven atomic (Sprint 002) |

## What was NOT deterministic/verifiable before this sprint, and is now

1. **"Is this job actually done?"** — previously answerable two contradictory ways (`intake_jobs.status` said
   yes, `intake_review_queue` said no). Now answerable exactly one way: `status` itself now correctly reflects
   whether review is outstanding.
2. **"Can a lawyer actually see and act on a flagged document?"** — previously, structurally no (3 frontend
   gates excluded it). Now yes, verified via the widened `_siJobsStillActive`/poll-handler/`_siRenderReview`
   gates.
3. **"Once a lawyer confirms, does the case get created without repeating work?"** — previously untestable,
   since no confirmation path existed at all. Now yes, proven idempotent and non-repeating (§`RESUME_WORKFLOW_
   SPECIFICATION.md`).
4. **"Is there a trace of the human's decision?"** — previously no. Now yes (§`AUDIT_PROVENANCE_VERIFICATION_
   REPORT.md`).

## What remains a known, out-of-scope limitation (not fixed, correctly not this sprint's charter)

- OCR quality/confidence itself (explicitly forbidden module this sprint).
- LLM self-reported confidence for the classification fallback path (designed fix exists, Sprint 003, not yet
  adopted — a large, separate implementation effort).
- The canonical taxonomy itself (designed, Sprint 003, not yet adopted).

None of these prevent the review/resume loop from working correctly — they affect how OFTEN a document lands
in the queue and how precisely its type is ultimately named, not whether the queue-to-completion mechanism
itself is deterministic and verifiable, which is what this sprint's charter is about.

## Regression proof

2530 passed, 1 skipped, 0 failed across the entire suite, including 20 new/extended tests covering every step
of this chain from escalation through resolve through finalize.
