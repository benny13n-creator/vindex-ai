# Mission Report — Program Intake Sprint 005 (2026-08-05)
## "Canonical Document Segmentation"

Per this sprint's own required deliverable shape: three sections. Full technical detail in the companion
documents (`CANONICAL_SEGMENTATION_ARCHITECTURE_REPORT.md` and siblings); this report is the founder-facing
summary.

---

## Section 1 — Popravljeno u ovom sprintu (Fixed this sprint)

1. **One canonical segmentation system now exists** (`shared/intake_segment.py`) where none did before — a
   pure, deterministic engine that decides how many separate legal documents a single uploaded PDF actually
   contains, before classification ever runs on any of them.
2. **The extractor's page-level text, which existed internally but was always discarded, is now preserved.**
   `uploaded_doc/extractor.py::extract_pdf()` built a per-page list for both born-digital and OCR'd PDFs and
   threw it away at the final join — this sprint changed the shared `extract()` contract so that data survives
   to the one pipeline that needs it, with zero behavior change for the 3 pipelines that don't (yet) act on it.
3. **A real false-positive bug, found during this sprint's own integration testing, fixed the same day it was
   found.** `_find_heading_keyword` used plain substring containment, so an ordinary continuation sentence
   containing an inflected form of a heading keyword (Serbian is heavily inflected — "zahtevu" contains
   "zahtev") would misfire as if a new document's heading had appeared. Fixed to word-boundary matching, with
   a dedicated regression test.
4. **An orphan-document defect the codebase already fixed once (Sprint 001) was prevented from reappearing in
   the new per-segment retry path.** The new in-process retry loop reuses the existing
   `delete_partial_document()` cleanup primitive rather than reinventing it, so a mid-attempt failure after a
   document was already created cannot leave a duplicate behind on retry.
5. **A resume-time `.maybe_single()` ambiguity bug was found and fixed before it ever shipped.** A resumed
   segmented job could have 2+ `intake_documents` rows sharing one `intake_job_id`; the old single-document
   idempotency check's `.maybe_single()` call would have raised on exactly that case. The idempotency check
   now looks up segment existence first, via a plain list query, routing segmented jobs to their own correct
   resume logic before the single-document check ever runs.
6. **Every segment has a full, unique identity and its own lifecycle** — new table `intake_job_segments`
   (migration `093`), reconciling two independently-designed proposals into one schema that owns both identity
   fields and status/lifecycle fields, with zero new columns needed on the existing
   `intake_documents`/`extracted_entities`/`intake_review_queue` tables.
7. **Partial failure isolation is real, not aspirational.** The old code had one try/except around the entire
   classify→extract→persist stretch, assuming exactly one document; the new per-segment loop gives each
   segment its own try/except, its own bounded in-process retry, and its own dead-letter path — proven by a
   dedicated test where one segment fails permanently and its sibling still completes correctly.
8. **The mission's own conservatism mandate is implemented as a real, tested combination rule, not a slogan.**
   Thin segmentation evidence (one lone strong signal, or 2+ corroborating with none strong) never triggers a
   guess in either direction — the document stays whole AND a human is asked to confirm via a new
   `segmentation_uncertain` review reason, at both the pure-engine level and the worker-integration level.
9. **42 pre-existing tests, rippled by the extractor contract change, found and fixed across 12 files** — the
   full regression suite passes with zero unresolved failures from this sprint's changes (exact before/after
   counts in Section 3).

## Section 2 — Namerno odloženo (Deliberately deferred, with reasoning)

Full detail for all three: `ARCHITECTURAL_DEBT_REGISTER.md`, entries `INTAKE-015` through `INTAKE-017`.

1. **Segmentation only wired into Pipeline B (the durable queue worker), not Pipelines A/A-ephemeral/C.**
   Pipeline A is a synchronous HTTP request/response call — auto-fanning a single upload into N case entries,
   or interrupting the response to ask for confirmation, is a genuine interaction-design decision the mission's
   own Phase 1 audit flagged as pipeline-specific, not something this sprint could pick unilaterally.
2. **No cross-run backoff/retry-claim system for segments** — only bounded (default 2) immediate in-process
   retries within one worker tick. A full claim/backoff RPC mirroring `claim_intake_job`'s own pattern is
   genuinely new architecture beyond this sprint's bounded scope, per the mission's own explicit allowance for
   that category of deferral.
3. **A distinct `partially_failed` job status was not built** — collapsed into the existing `awaiting_review`
   status instead. Whether `finalize_intake_job` may ever create a case from an M-1-of-M segmented job is an
   open founder product decision (mirroring Sprint 004's own `INTAKE-012` "reject" precedent); until decided,
   such a job simply cannot finalize (safe, fail-closed default via the existing status gate, zero new
   blocking code).

None of these three block the mission's own success criteria — every segment still reaches exactly one of
`completed` / `awaiting_review` / `failed`, no page is ever lost or duplicated, and no upload is ever silently
mis-segmented; these are about which pipelines segment yet and how precisely a partial failure is surfaced,
not about documents getting stuck or corrupted.

## Section 3 — Merljivo poboljšanje platforme (Measurable improvement)

| Metric | Before this sprint | After this sprint |
|---|---|---|
| Systems that split a bundled upload into separate legal documents for case intake | 0 (two unrelated systems existed for other purposes — sub-document clause segmentation, and bulletin-specific RAG-corpus splitting — neither applicable) | 1 canonical system |
| Page-level text preserved past extraction | Never (discarded at `"\n\n".join(pages)` in both PDF paths) | Preserved for every PDF extraction, consumed by Pipeline B |
| Manual steps for a lawyer to correctly process a genuinely bundled 2-document PDF (Pipeline B) | 6 (notice a problem, diagnose it's 2 documents, manually split, re-upload, wait, re-verify) | 1 (review the already-correctly-split, already-classified result) — see `USER_AUTOMATION_GAIN_REPORT_SPRINT005.md` |
| Manual steps for an ordinary single-document upload | 0 | 0 (unchanged by design — the conservatism mandate, made measurable) |
| Segments with a unique, durable identity before classification | N/A (concept did not exist) | 100% — every segment has `id`/`intake_job_id`/`segment_index`/`start_page`/`end_page`/`reason`/`confidence` before it is ever classified |
| A single segment's permanent failure aborting its siblings' processing | Would have (single unguarded try/except around the whole job) | Never (per-segment try/except, proven by dedicated test) |
| Dedicated segmentation test coverage | 0 | 18 pure-engine tests + 6 worker-integration tests = 24 new tests, all passing |
| Real false-positive bugs found and fixed via this sprint's own testing | N/A | 1 (inflected-keyword substring match), plus 1 orphan-document retry guard and 1 resume-ambiguity bug prevented before shipping |
| Full regression suite | 42 tests broken by the extractor contract change, across 12 files, at the moment the change was made | All 42 fixed same-session; full suite at sprint close: **2555 passed, 1 skipped, 0 failed** (includes 24 new Sprint 005 tests) |

**Concrete effect for a real lawyer using Pipeline B**: before this sprint, uploading a bundled multi-document
PDF produced one confused classification and one entity-extraction result mixing two documents' worth of
case numbers, parties, and dates — with no signal that anything was wrong, and no path forward except the
lawyer's own unprompted realization and manual re-work outside the product. After this sprint: the same
upload is automatically recognized as containing separate documents (when the evidence is strong enough to be
sure), each classified and extracted correctly and independently, with every partial failure isolated to just
the one affected document — and when the evidence is real but too thin to be sure, the document stays whole
and the lawyer is pointed at exactly the page and signal in question, rather than left to notice on their own.

**Platform state at the end of this sprint, honestly assessed**: a real capability gap (bundled uploads
silently mis-processed as one document) is closed for the pipeline the mission targeted, with the pipeline-
agnostic engine itself ready for the other 3 upload paths pending a named, deliberately-deferred product
decision. Zero competing segmentation implementations exist. Zero regressions from a contract change that
touched the shared extraction library used by all 4 upload paths.
