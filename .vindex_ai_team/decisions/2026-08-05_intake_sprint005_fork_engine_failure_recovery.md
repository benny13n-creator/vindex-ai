# Fork Deliverable — Program Intake Sprint 005 ("Canonical Document Segmentation")
## Phase 3: Canonical Segmentation Engine + Phase 6: Partial Failure Recovery

**Scope of this fork**: the pure segmentation algorithm, its exact plug-in point in
`shared/intake_worker.py::_process()`, and the failure-recovery/status-model design needed so that a
mid-batch segment failure genuinely isolates (segments 1/2/4/5 survive, segment 3 gets its own retry
lifecycle). This is a READ-ONLY design — no files edited, no migration SQL drafted. A sibling fork owns
exactly what page-level text becomes available from the extractor and the DB-row/reprocessing-job wiring
of Phase 4/5; this document names the hand-off points to that work precisely rather than re-deriving or
duplicating it. Genome, Timeline, Deadlines, Tasks, Copilot, Strategy Engine, Firm Brain, Search are out of
scope and untouched.

**Grounding read before designing** (not re-derived, cited where load-bearing):
`docs/architecture/DOCUMENT_LIFECYCLE_ARCHITECTURE_REPORT.md`, `TRANSACTION_BOUNDARY_ANALYSIS.md` (Sprint
002 — `.rpc()` is the only atomic mechanism; everything else is idempotent-and-re-runnable, not
transactional), `HUMAN_REVIEW_ARCHITECTURE_REPORT.md`, `RESUME_WORKFLOW_SPECIFICATION.md` (Sprint 004 —
`awaiting_review`↔`completed`, `claim_intake_job`/`claim_intake_finalize` atomic-claim pattern,
`has_processing_outcome`/`delete_partial_document` as the proven crash-detection-and-clean-redo pattern),
`shared/intake_worker.py`, `shared/intake_queue.py`, `shared/intake_documents.py`, `shared/intake_classify.py`,
`uploaded_doc/extractor.py`, `migrations/073_intake_foundations.sql`, `migrations/074_intake_phase1a.sql`
(actual code and schema read in full, not paraphrased).

---

## 0. One governing principle that shapes every decision below

**A job that segments into exactly 1 (implicit) segment must be byte-for-byte behaviorally identical to
today's pre-Sprint-005 pipeline.** The overwhelming majority of intake jobs today are a single document —
this design must not create two permanently-forked code paths (an "old, no-segments" path and a "new,
segments" path) that both have to be kept correct forever. That would be exactly the kind of duplicate
business logic Program Intake's Core Consolidation principle (`docs/architecture/VINDEX_CORE_CONSOLIDATION.md`)
exists to prevent. Instead: **segmentation always runs, and the single-segment case is the degenerate
input to the SAME mechanism**, not a bypass of it. Every design choice below is checked against this.

---

## 1. Phase 3 — Canonical Segmentation Engine

### 1.1 The pure function

New module `shared/intake_segment.py`, same shape/philosophy as `shared/intake_classify.py` (a single
owned algorithm, heuristic-first, cheap, explicit about what it doesn't know) — but with **zero I/O of any
kind**: no `_get_supa()`, no `asyncio`, no imports outside the standard library + `re`. This is deliberate —
it is the one piece of Phase 3 that must be trivially unit-testable with literal in-memory input, no mocks.

```
PageText:        page_number (1-based), text (str), ocr_used (bool)
SegmentSignal:   kind (str), page_number (int), detail (str)   # what justified a candidate boundary
Segment:         start_page (int), end_page (int), signals (list[SegmentSignal])  # inclusive, 1-based

def segment_document(pages: list[PageText]) -> list[Segment]
```

Contract: `pages` is ordered, contiguous, 1-based. Output is an ordered list of `Segment` covering
`1..len(pages)` with no gaps and no overlaps. **Single-segment, empty-`signals` output is the explicit "no
split warranted" case** — not an error path, not a special return type. A 1-page input always produces
exactly this.

### 1.2 Boundary signals — reusing this codebase's own vocabulary, not inventing a new one

Four heuristic signal detectors, evaluated per page-boundary (between page N-1 and page N, for N≥2):

1. **`heading_keyword`** — reuses `shared/intake_classify.py::_HEURISTICS` verbatim (same keyword list,
   same `_HEAD_CHARS`-style head-of-page window, same Cyrillic/Latin duplication). If page N's head text
   matches one of these document-opening keywords (`TUŽBA`, `PRESUDA`, `REŠENJE`, `PUNOMOĆJE`, ...), that is
   strong evidence page N is the *start* of a new document. Reusing this list instead of a second one is a
   direct Core Consolidation decision: the same "this word means a new legal document is starting" fact
   should have one owner, not a segmentation-specific copy that could drift from the classifier's own list.
2. **`case_number_change`** — a Serbian court case-number regex (e.g. `\d+\s?(P|Rs?|Iv|K)\.?\s?\d+/\d{2,4}`)
   applied to each page's head; if page N's matched case number differs from page N-1's (both confidently
   matched), that's evidence of a new, unrelated document.
3. **`page_number_reset`** — a footer-style "Strana X od Y" / "Page X of Y" pattern; if the running page
   counter *decreases or resets to 1* relative to the previous page, that's evidence of a new document's own
   pagination starting.
4. **`blank_separator`** — a page whose extracted text is near-empty (below a small character threshold)
   sandwiched between two non-empty pages — the common artifact of a lawyer scanning a stack of separate
   physical documents with a blank sheet between them.

### 1.3 Merge + threshold — avoiding over-segmentation

- Multiple signals landing on the *same* boundary point (e.g. `heading_keyword` + `case_number_change` both
  firing between page 4 and 5) merge into **one** boundary with multiple signals attached — never multiple
  boundaries for one point.
- A cut only happens where the accumulated evidence at a boundary meets a minimum bar: **one strong signal**
  (`heading_keyword` or `case_number_change`) is sufficient alone; **weak signals** (`page_number_reset`,
  `blank_separator`) require at least two independent weak signals at the same boundary to cut alone. This
  guards against a single long contract with a per-chapter-reset footer counter being wrongly sliced into N
  fake documents — a real, plausible false-positive this threshold exists specifically to prevent.
- A `blank_separator` page is assigned to the segment that *precedes* it (trailing filler), so every page is
  covered by exactly one segment and no page is orphaned or double-counted.
- If no boundary anywhere clears the threshold, the function returns the single implicit segment — this is
  the expected, common, correct output for an ordinary single-document upload, not a fallback-on-failure.

### 1.4 Exactly where this plugs into `_process()` — before classification, per Phase 5's own instruction

Current shape (`shared/intake_worker.py::_process()`, lines 195-279):
`download+decrypt` → `_extract_text()` (one concatenated `text` string, `is_scanned`/`ocr_used` flags) →
early-return on `is_scanned` (OCR failure branch, untouched by this design — see §1.5) → `_classify(text)` →
`_extract_entities(text)` → persist → review-routing → `write_processing_outcome`.

New shape:
`download+decrypt` → extractor's small change (sibling fork's scope) returns page-level `pages: list[PageText]`
instead of one string → **`is_scanned` early-return unchanged, evaluated first, exactly as today** (a
document whose OCR failed entirely has no usable page text for segmentation to work on — segmentation is
simply moot for that path, so it is left completely alone, respecting the "don't touch OCR quality" boundary)
→ **`segment_document(pages)`** → for each `Segment` in the result: reconstruct that segment's text by joining
its page range (`"\n\n".join(p.text for p in pages[seg.start_page-1:seg.end_page])`) → run the **existing**
`_classify(segment_text)` → `_extract_entities(segment_text)` → persist as **that segment's own**
`intake_documents` row → per-segment review-routing → per-segment outcome write.

This directly satisfies the mission's own explicit Phase 5 instruction — "svaki segment ulazi u postojeci
klasifikacioni pipeline... ne klasifikovati ceo PDF" — segmentation strictly precedes classification, and
classification runs once per segment on that segment's own slice of text, never once on the whole
concatenated document.

### 1.5 Does `_process()` iterate internally, or does the job spawn N new processing units? — Recommendation: iterate internally, one job execution, N internal segment-units. Do NOT spawn N new `intake_jobs` rows.

Reasoning, weighed directly against Sprint 002/004's proven guarantees:

- **Cost.** The expensive step — download, decrypt, OCR — happens exactly once today, for one document. If
  segmentation spawned N *new* `intake_jobs` rows (e.g., "detect segments, then enqueue N follow-up jobs"),
  each new job would either (a) redundantly re-download+re-decrypt+re-OCR the *same* original blob to get its
  own copy of "its" pages — the single most expensive step in the whole pipeline, repeated N times for work
  already done once — or (b) require inventing a new mechanism to hand already-extracted page text from the
  parent job to N children (a new persistence concept — "cache OCR'd text somewhere between jobs" — that
  doesn't exist anywhere in this codebase today and is exactly the kind of new capability this design should
  avoid manufacturing to solve a problem the simpler option doesn't have).
- **Concurrency-safety surface.** `claim_intake_job`'s `SELECT...FOR UPDATE SKIP LOCKED` (migration 073) is
  the only proven claim mechanism in this codebase, and it is scoped to `intake_jobs`. Spawning N new
  `intake_jobs` rows means either giving them a `parent_job_id` and teaching *every* existing job-status
  consumer (`GET /jobs/{job_id}`, `finalize_intake_job`, `intake_queue_metrics`, the reaper, the heartbeat
  view) to understand parent/child relationships — a genuinely new orchestration concept layered on top of an
  already-proven one — or building a second, parallel claim mechanism for children. Both are larger blast
  radius and duplicate-mechanism risk than keeping the ORIGINAL job as the sole unit the existing claim/
  retry/reap machinery already understands, and adding a **smaller, additive** table underneath it instead
  (§2).
- **What Sprint 002/004 already proved stays true.** `claim_next_job("received","preprocessing")` claims the
  *job*, not "a document." Nothing about that claim's atomicity depends on the job producing exactly one
  document — it depends on the job's `id` being claimed exactly once. Keeping the original job as the sole
  claimed/retried unit for the shared download+decrypt+OCR+segment step preserves that guarantee completely
  unchanged; the *new* thing this design needs is only downstream of that point, once N segments exist.

**Recommendation, stated plainly**: `_process()` internally calls `segment_document()` once, then loops over
the resulting segments, calling the *existing* classify → extract-entities → persist logic once per segment,
all within the *one* job execution that already holds the claim. The original `intake_jobs` row's own
status/attempts/claim continues to mean exactly what it means today for the shared pre-segmentation stretch.
What changes is what happens *after* that stretch succeeds — and that is where Sprint 001's own "one document
per job" assumption genuinely breaks, addressed in §2.

**Named hand-off to the sibling Phase 4/5 fork**: `shared/intake_documents.py::get_job_result()` (used by
`routers/smart_intake.py`'s `GET /jobs/{job_id}` at line ~238) currently does
`.table("intake_documents").select("*").eq("intake_job_id", ...).maybe_single()` — a hard "exactly one
document" assumption at the query level, not just a comment. This design requires that call to become a
plain `.select(...).execute()` returning a list, and the endpoint's response shape to become a list of
per-segment views instead of one `dokument` object. This is squarely Phase 4/5 integration-layer work (API
response shape), not restated here as an implementation, only flagged as the concrete point where my design's
"N documents per job" assumption meets existing code that assumes exactly one.

---

## 2. Phase 6 — Partial Failure Recovery

### 2.1 Direct answer to the mission's own question: the existing job-status vocabulary CANNOT represent partial success, and pretending otherwise would be dishonest

`intake_jobs.status` (`received/preprocessing/awaiting_review/completed/failed`, migration 073's CHECK
constraint) is singular, per-job, mutually exclusive by construction — one row, one value, one meaning. Every
guarantee Sprint 001/002/004 proved (`has_processing_outcome`, `delete_partial_document`, the atomic-claim
finalize pattern, the reaper) is keyed on **exactly one `intake_job_id` ↔ exactly one document's lifecycle**.
There is no way to make one column simultaneously mean "3 of 5 done, 1 failed, 1 awaiting review" without
either (a) inventing a compound encoding inside a single TEXT column (a worse, harder-to-query version of the
same information already representable as rows) or (b) genuinely tracking each segment as its own row with
its own status — which is what this design does, reusing this codebase's own already-established pattern:
`intake_review_queue` and `extracted_entities` are already "one row per instance of the smaller unit,
referencing the parent `intake_documents`/`intake_jobs` row, with its own lifecycle fields." This is a
genuinely new requirement, not yet supported by anything built in Sprints 001-004 — stated exactly as
directly, not hedged.

### 2.2 New unit: `intake_job_segments` (shape, not a migration — schema authoring is out of this fork's bound)

One row per `Segment` produced by §1, for **every** job including the N=1 case (§0's governing principle —
no permanent second code path). Illustrative column shape, described in prose, not DDL:

| Column | Purpose |
|---|---|
| `id` | own identity |
| `intake_job_id` | FK to the parent job — same relationship shape as `intake_documents.intake_job_id` today |
| `segment_index` | 0-based ordinal position within this job — stable identity across a retry's re-segmentation (see §2.5's residual risk) |
| `start_page` / `end_page` | this segment's page range, from `Segment.start_page`/`end_page` |
| `boundary_signals` | `Segment.signals`, persisted verbatim — the audit trail of *why* this cut happened, directly answering the mission's "signals that justified the boundary" requirement |
| `status` | `pending → processing → completed \| awaiting_review \| failed` — this segment's OWN lifecycle, independent of siblings |
| `document_id` | FK to `intake_documents`, set once this segment's classify+extract+persist succeeds |
| `attempts` / `max_attempts` / `next_retry_at` / `last_error` | this segment's OWN retry/backoff bookkeeping, independent of the parent job's |

`intake_documents`, `extracted_entities`, `intake_review_queue`, `intake_processing_outcomes` each need one
new nullable FK column (`segment_id`, referencing `intake_job_segments`) — nullable specifically so that any
historical pre-Sprint-005 row (and, going forward, any code path that genuinely has no segment concept)
remains valid with `segment_id IS NULL`, never requiring a backfill or a breaking change to existing rows.

`has_processing_outcome` and `delete_partial_document` (`shared/intake_documents.py`) both become
**segment-scoped**: `has_processing_outcome(segment_id)` instead of `(job_id)`, `delete_partial_document`
narrowed to delete only the ONE segment's `document_id`'s children — never touching sibling segments' rows.
This is the exact same crash-detection pattern Sprint 001 proved ("document exists, outcome doesn't ⇒
previous attempt died mid-write ⇒ wipe and redo"), narrowed to the smaller unit that now needs it — a direct,
faithful generalization, not a new invention.

### 2.3 The parent job's own status — derived, not independently decided

Reusing this codebase's own established "derive, don't store" principle (`intake_queue_metrics`,
`events_outbox_metrics` — both explicitly "IZVEDENI, nikad zaseban stored red"), the parent `intake_jobs.status`
becomes a value **recomputed** from its segments' statuses immediately after any segment's terminal
transition, rather than a value the worker decides independently at the top level:

- Any segment still `pending`/`processing` → parent stays `preprocessing` (still working — unchanged meaning).
- All segments terminal, **any** segment `awaiting_review` → parent = `awaiting_review`. This is the
  **existing** value, unchanged meaning, and `finalize_intake_job`'s pre-existing gate (`status != 'completed'`)
  already correctly blocks on it — zero new blocking code, the exact trick Sprint 004 already used once.
- All segments terminal, **all** `completed` → parent = `completed`. Existing value, unchanged meaning. When
  N=1, this collapses to exactly today's behavior — the governing principle in §0 holds by construction, not
  by a special case.
- All segments terminal, **at least one** segment permanently dead-lettered (`failed`, exhausted its own
  `max_attempts`) while others are `completed`/resolved — **this is the one case current vocabulary has no
  honest value for.** Recommendation: add one new terminal value, `partially_failed`. `finalize`'s existing
  gate treats it identically to `awaiting_review` for blocking purposes (still `!= 'completed'`, still zero
  new finalize logic) — but the message shown to the lawyer must say something concretely different from
  generic "not ready yet": *N of M segments processed; segment K could not be processed after its retries —
  finalize with the M-1 available documents, or retry segment K first.* **Whether finalize is even ALLOWED to
  proceed with a partial document set is a genuine product/business decision** — mirroring exactly the shape
  of this arc's own already-deferred `INTAKE-012` ("what should reject concretely do?") — correctly out of
  this fork's design authority, named here rather than guessed at.

Recomputation mechanism: a small, pure-relative-to-DB-state function (bare `.select()` on
`intake_job_segments` + a conditional `.update()` on `intake_jobs` — **not** wrapped in an RPC), called
immediately after every segment-level terminal write, mirroring exactly how `_tick()` today calls
`mark_job_awaiting_review`/`mark_job_completed` right after `_process()` returns. This is safe without
transactional wrapping for the same reason Transaction Boundary Analysis §1 already established for this
whole codebase: recomputation is a pure re-derivation from already-committed segment rows, safely re-runnable
by any caller, at any time, with no compensating action ever needed — two segments finishing concurrently and
both triggering a recompute is fine, whichever runs last simply re-derives and writes the same correct answer.

### 2.4 The one thing the current `_process()` shape must change to satisfy the mission's own test literally

Today, a single unguarded exception anywhere in `_process()` propagates to `_tick()`'s `except Exception` →
`mark_job_failed(job_id, ...)` for the **whole job** (`shared/intake_worker.py` lines 133-139). If segment 3's
`classify()` call raises and this shape is left untouched, the exception aborts the entire segment loop —
segments 4 and 5 never even get attempted this run, and the *whole job* goes through job-level retry, which
(per §2.5) means redoing OCR and re-attempting segments 1/2/4/5 that had already succeeded. That is **not**
genuine partial-failure isolation — it would only *look* like segments aren't "lost" (their rows survive) while
the actual behavior still aborts the run over one bad segment, exactly the shape this document was told to be
skeptical of.

**Fix, load-bearing to this whole design**: the per-segment classify→extract→persist stretch must be wrapped
in its **own** try/except, *inside* the segment loop. A segment's exception is caught right there, that
segment is marked `failed` with its own backoff (§2.6), and **the loop continues to the next segment** — 4 and
5 still get processed in the same run 3 failed in. Only an exception in the *shared, pre-segmentation* stretch
(download/decrypt/OCR/`segment_document()` itself, which happens once for all segments and genuinely has no
per-segment granularity to isolate) should still propagate to `_tick()`'s existing whole-job retry path,
unchanged from today.

### 2.5 Retrying one failed segment later — what it actually costs, stated honestly

A segment's `next_retry_at` becoming due does **not** mean the ORIGINAL job gets re-claimed via
`claim_next_job` — that query only matches `status='received'`, and this job is sitting in `awaiting_review`/
`partially_failed` by then. The correct analog, mirroring `claim_intake_job`'s own proven shape rather than
inventing something unrelated: a new, small, dedicated claim — `claim_intake_segment_retry`, same
`SELECT...FOR UPDATE SKIP LOCKED` pattern, scoped to `intake_job_segments` rows where
`status='failed' AND attempts < max_attempts AND next_retry_at <= now()` — returning the claimed segment row
(with its parent `intake_job_id`, `start_page`, `end_page`).

**The honest cost, stated plainly rather than hidden**: no per-page OCR text is persisted anywhere between
steps today (Sprint 001's own reasoning for why whole-document retry is "cheap" — "tekst dokumenta se ionako
nigde ne perzistira između koraka" — still applies, unchanged). Retrying **only** segment 3 therefore still
requires re-downloading, re-decrypting, and re-running OCR on the **entire original file** to regenerate page
3's text — there is no cheaper path without a genuinely new capability (persisting per-page OCR output
somewhere), which this fork does not invent, matching this sprint's own bounded-scope discipline. What IS
saved by scoping the retry to one segment: the freshly-regenerated pages are re-segmented (deterministic,
pure — §1.1), and only the segment ordinally matching the *claimed* segment's `segment_index` is reprocessed
(classify+extract+persist) — segments 1/2/4/5, already `completed`, are **not** touched, not reprocessed, not
re-persisted. Their existing `intake_documents`/`extracted_entities` rows stand untouched throughout.

**Residual risk, named rather than hidden** (matching this arc's own established pattern — Sprint 002 did the
same for its atomic-claim fix's narrowed window): `segment_document()` is deterministic given identical page
text, and OCR of the same bytes should be stable — but if a retry's fresh OCR pass produces even slightly
different text and that shifts a boundary signal, the retry's re-segmentation could produce a *different*
segment count or ranges than the original attempt, breaking the ordinal `segment_index` match. Recommendation:
detect this specific case (retry's fresh segment count ≠ original stored segment count) and **do not attempt
to guess a mapping** — route the whole job to `awaiting_review` with a distinct reason
(e.g. `segmentation_unstable_on_retry`) instead, since silently reprocessing under a wrong page-range
assumption is worse than asking a human to look. This is a narrow, low-probability edge case (OCR
non-determinism on identical input bytes is uncommon, not impossible), tracked honestly rather than assumed
away.

### 2.6 Per-segment retry/backoff — reuse the existing formula, not the existing RPC

`shared/intake_queue.py::mark_job_failed` does two things that are currently fused: (1) a **pure** backoff
calculation (`_BACKOFF_BASE_S * 2**attempts`, capped at `_BACKOFF_CAP_S`, lines 149-154) and (2) an I/O call
into `fail_intake_job`, an RPC hardcoded to the `intake_jobs` table plus an atomic audit+outbox write.

**Recommendation**: extract (1) into a small pure helper (e.g. `_compute_backoff(attempts, max_attempts) ->
tuple[bool, str | None]`, returning `is_dead_letter` and `next_retry_at`), used by *both* the existing
`mark_job_failed` (unchanged behavior, unchanged callers) and a new `mark_segment_failed(segment_id, error,
attempts, max_attempts)`. The **formula** is one owned concept reused twice — Core Consolidation's own
standard — while the **write** is intentionally *not* forced through the same RPC, because a segment failure
today has no audit+outbox obligation of its own to bundle atomically: a bare `.update()` on
`intake_job_segments` is the correct-weight mechanism, exactly matching Transaction Boundary Analysis's own
conclusion that bare, independently-committed calls are the right tool when nothing else must commit
alongside them. If segment-level audit parity is wanted later, `intake_audit_log` needs no schema change to
support it — it already accepts a `before`/`after` JSONB payload, so a segment's terminal transition can be
logged against the **parent** `intake_job_id` with `segment_index` embedded in the payload, the same technique
Sprint 004 used for `dokument_review_resolved`. Not required to satisfy this mission's own named test, but
free to add without new infrastructure.

`reap_stale_jobs`'s reaper needs a narrow companion, `reap_stale_segments`, scoped to `intake_job_segments`
rows stuck in `processing` past a staleness threshold (a `processing_started_at`-equivalent column, mirroring
`intake_jobs.claimed_at` exactly) — a worker crashing mid-segment must not leave that ONE segment permanently
stuck, without affecting the reaper's existing, unchanged behavior for jobs stuck in the shared
pre-segmentation stretch (`preprocessing`), which continues to use the existing whole-job reap path exactly
as today, since no segment rows exist yet at that point for a crash that early.

---

## 3. Mission closure self-check (this fork's own scope only)

- **Segment 3 of 5 fails, 1/2/4/5 not lost** → True by construction: the per-segment try/except (§2.4) never
  lets one segment's exception unwind the loop or trigger any code path that deletes/reprocesses a sibling
  segment's already-`completed` rows.
- **Each segment has its own independent lifecycle** → True: `intake_job_segments.status` +
  `attempts`/`next_retry_at`/`last_error`, independent of the parent job's derived status and of every
  sibling segment.
- **Fits the existing job-status vocabulary, or needs a genuine new one?** → Answered directly, not hedged:
  the existing 5 values are insufficient for the "some succeeded, one permanently failed" case; one new
  terminal value (`partially_failed`) is the minimum honest addition, and even that reuses the *existing*
  finalize-blocking trick rather than adding new blocking logic.
- **Retry reuses the existing pattern where it genuinely fits, and is honest where it doesn't** → the backoff
  *formula* is reused (extracted, not duplicated); the *write* is deliberately not forced through the
  whole-job RPC (different shape, no shared atomicity need); the true cost of a segment-scoped retry (a full
  OCR re-pass, because no cheaper per-page caching capability exists) is stated plainly, not implied away.
- **No design here merely looks like isolation while still aborting the whole job** → the one place today's
  code would do exactly that (`_process()`'s single unguarded try/except around the whole classify/extract/
  persist stretch) is explicitly identified and named as the one change this design requires (§2.4) — not
  glossed over as "already fine."

## 4. What this fork deliberately leaves to the sibling Phase 4/5 fork, and what it leaves to a founder

**Sibling fork's job (integration layer)**: the extractor's exact page-level exposure mechanism; migration
authoring for `intake_job_segments` and the four new nullable `segment_id` columns; rewiring
`get_job_result()`/`GET /jobs/{job_id}` from `.maybe_single()` to a list-returning shape; a segment-level
resolve endpoint (or extending the existing one) for the `awaiting_review`-per-segment case; wiring
`claim_intake_segment_retry` and `reap_stale_segments` into `IntakeWorker._tick()`'s actual loop.

**Founder decision, correctly not guessed at here** (same shape as this arc's own already-deferred
`INTAKE-012`): is `finalize_intake_job` even allowed to create a case from a `partially_failed` job (M-1 of M
documents), or must every segment reach `completed` first? This fork's design supports either answer — the
`partially_failed` status and the per-segment document rows exist either way — but which behavior is correct
is a product question about what an advokat should be allowed to do with an incomplete batch, not a technical
one this fork can resolve unilaterally.
