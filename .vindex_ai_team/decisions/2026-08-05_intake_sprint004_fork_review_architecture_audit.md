# Review Architecture Audit — Program Intake Sprint 004, Phase 1 (2026-08-05)

Charter: "Human Review Orchestration & Automatic Resumption." READ-ONLY investigation, no edits made. Confirms
and extends the sprint lead's own pre-identified defect (`resolve_review_queue_for_job` has zero call sites),
then maps every other human-confirmation surface in the codebase per the 6 numbered questions in the brief.

---

## 0. Headline confirmation (not re-derived, independently re-verified)

Repo-wide grep for `resolved_at|resolve_review_queue_for_job` across all `.py` files returns exactly 4 hits,
all inside `shared/intake_documents.py`:

- Line 216: `get_job_result()` — reads unresolved rows (`is_("resolved_at","null")`), does not write.
- Line 273: `async def resolve_review_queue_for_job(...)` — the function definition itself.
- Line 280, 282: the function body's own `.update(...).is_("resolved_at","null")` call.

**Zero call sites anywhere else in the codebase** — not in `routers/smart_intake.py` (`correct_entity`
endpoint, line 289-321, or `finalize_intake_job`, line 431-933), not in `shared/intake_worker.py`, not in any
test file that exercises live behavior (only `tests/test_intake_documents.py` calls it directly as a unit
test of the function in isolation — confirmed by reading that test file's imports, it does not exercise any
endpoint that would call it as a side effect). Confirmed defect, exactly as briefed: there is no live code path
that ever marks an `intake_review_queue` row resolved.

---

## 1. Every "needs human confirmation" surface, platform-wide

Found via broad grep (`potvrd|review|odobri|approve|confirm|resolved_at|low_confidence|nesigurn`) across
`routers/`, `shared/`, `services/`. **Six independent systems**, each with its own table, status vocabulary,
and resolution mechanism — no shared abstraction between any of them:

| # | System | Table | Status field | Resolved via | Resolution wired? |
|---|---|---|---|---|---|
| 1 | Smart Intake review queue | `intake_review_queue` (migration 074) | `resolved_at IS NULL` | `resolve_review_queue_for_job()` | **No — dead code (§0)** |
| 2 | Drafting Staging Memory | `staging_memory` (migration 088) | `status` (`pending`→`approved`/`rejected`) + `is_lawyer_approved` bool | `POST /api/staging/{id}/approve`, `POST /api/staging/{id}/reject` (`routers/drafting.py:1043-1106`) | **Yes — fully wired, live, has frontend (`static/vindex.js:21383-21414`+)** |
| 3 | Agent Recommendations (Copilot) | `agent_recommendations` | `status` (`pending`→other) | `_resolve()` (`routers/agent_notifications.py:63-103`) | Yes — wired (Copilot is out of this sprint's scope, noted only for completeness) |
| 4 | Lessons Learned (Learning Engine/Firm DNA) | `lessons_learned` | `status_lekcije` (`predlog_ai`→`usvojena_praksa`/`odbijena`) | `PATCH /lessons/{id}/potvrdi` (`routers/learning.py:1030-1102`) | Yes — wired (Firm Brain-adjacent, out of scope, noted only for completeness) |
| 5 | Status Page incidents | (status_page table) | `resolved_at` | `routers/status_page.py:64,107,120` | Yes — unrelated domain (ops incidents, not AI output), noted only because it matched the grep |
| 6 | Predmet documents generic "na_cekanju" | `predmet_dokumenti.status` | `na_cekanju`/`greska`/etc. | Multiple writers (Sprint 001 Fork 3 finding, already tracked) | Partial — this is a storage-status field, not a review-approval concept; listed because `copilot.py:804` and comments in `routers/intake.py:232-236` and `routers/smart_intake.py` (Sprint 001 comments) treat it adjacently |

**Direct answer to the brief's Phase-2 question**: **Yes, `staging_memory`/`is_lawyer_approved` (row 2) is
structurally a second, fully independent, and — unlike Smart Intake's — a *working* review queue.** It has its
own table, own status vocabulary (`pending`/`approved`/`rejected`, distinct from `intake_review_queue`'s
`resolved_at IS NULL` boolean-shaped state), own two-endpoint resolution API, own frontend section
(`static/vindex.js:21383` "DRAFT STAGING/APPROVAL"), own audit call (`log_action(action="drafting_generisan",
...)`, `routers/drafting.py:236-241`), and a second independent confidence gate on top of the approval itself
(`_APPROVAL_CONFIDENCE_THRESHOLD = 0.85` at `routers/drafting.py:247`, checked in `staging_approve` at
line 1066, separate from `intake_documents.AUTO_ACCEPT_THRESHOLD = 0.90`). It reviews a **different kind of AI
output** (generated draft text destined for the firm's Pinecone knowledge base) than Smart Intake's review
queue (extracted document fields destined for a case file) — different domain, but structurally the same
"AI produced something uncertain, a human must confirm before it becomes permanent" pattern, built and wired
independently, with its own confidence threshold, own status vocabulary, own audit call. If Phase 2's
canonicalization goal is "exactly ONE canonical review queue," this is the second live contender the mission
needs to explicitly decide about (merge, keep separate as a different domain, or declare Smart Intake's as the
canonical shape and retrofit staging_memory to match) — not a hypothetical, a shipped, working, parallel
system as of today.

Rows 3 and 4 (`agent_recommendations`, `lessons_learned`) are additional, independently-built,
independently-resolved "human confirms AI output" systems, surfaced only because the brief's grep terms hit
them — both sit inside explicitly out-of-scope modules this sprint (Copilot, Firm Brain/Learning), so not
analyzed further, only flagged as existing so Phase 2 knows the true count before scoping "exactly one."

---

## 2. Does `finalize_intake_job` actually block on `classification_uncertain`?

**No. Confirmed by direct read of `routers/smart_intake.py:431-933` — it never blocks, only tags the response.**

- Line 521-523: `review = result["review"]`; `classification_uncertain = bool(review) and "document_type" in
  low_confidence_fields`.
- The **only** behavioral branch gated on `classification_uncertain` is at line 858-874: it skips scheduling
  `_evidence_classify_bg` (the Evidence Vault re-classification background task), so Pipeline B's uncertain
  guess isn't silently overwritten by a more-confident-looking second guess. That is the full extent of the
  blocking behavior.
- Everything else in the function — creating the `predmeti` row (line 581-592), linking the client (line
  595-637), running the conflict check (line 659-677), adding the deadline (line 680-697), chunking/embedding
  the document into Pinecone and inserting `predmet_dokumenti` (line 700-802), and writing `intake_jobs.
  predmet_id` (line 887-896, the field that makes the case permanently exist) — **runs unconditionally,
  regardless of `classification_uncertain`.**
- The function returns HTTP 200 with `"ok": True` (line 920) and the case is fully created either way; `
  klasifikacija_nesigurna`/`nesigurna_polja` (line 931-932) are informational fields on an already-successful
  response, not a gate.
- This matches `docs/architecture/STATE_MACHINE_SPECIFICATION.md:31`'s own prior finding, verbatim: "finalize
  can proceed even with an unresolved review item (soft gap, not scored — a UX/product question, not this
  sprint's transactional-boundary charter)." That doc correctly called this a known, named, deliberately
  deferred gap — Sprint 004's brief is right that this is exactly the gap to close now.

**Implication for Sprint 004**: real blocking behavior does not exist today and must be **added**, not just
resumed. There is no dormant "block" switch to flip — the function has never refused to finalize on low
confidence at any point in its history. Any new gate needs a decision on shape (hard block returning
409/422 vs. soft warning requiring an explicit `force=true`/acknowledgment flag) — that is a product-shape
question, not investigated further here per the brief's read-only/no-recommendations framing, but flagged as
the one place a business-shape choice, not a bug fix, is genuinely needed.

---

## 3. Stuck documents / jobs with no path forward

**3a. `intake_review_queue` has no TTL, reminder, or escalation mechanism at all.**
Full column list, `migrations/074_intake_phase1a.sql:95-106`: `id, intake_job_id, document_id, reason,
low_confidence_fields, resolved_at, resolved_by, created_at`. No `expires_at`, no `reminder_sent_at`, no
`escalated_at`, no severity/priority column. The only index (`migrations/074_intake_phase1a.sql:111`) is a
partial index on unresolved rows for fast lookup — a performance aid, not an aging/escalation mechanism.
Combined with §0 (nothing ever sets `resolved_at`), an unresolved row today sits **forever**, with zero
automated follow-up of any kind — no cron, no digest email, no dashboard alert count found in any grep for
`intake_review_queue` outside the files already covered by `REVIEW_QUEUE_SPECIFICATION.md`'s own audit
(confirmed: that spec doc's §2 already independently found the same "GET /jobs/{id} is the only read site"
result I re-confirmed via frontend grep in §4 below).

**3b. `reap_stale_jobs` explicitly excludes `awaiting_review`, and `awaiting_review` is never reached.**
`shared/intake_queue.py:150-173`, `reap_stale_jobs()`'s `in_progress_statuses` tuple (line 156) is
`("preprocessing", "classifying", "extracting", "matching", "dedup_check")` — `awaiting_review` and
`completed`/`failed` are deliberately not in this list (the docstring at line 151 even says "ne-terminalnom,
ne-awaiting_review statusu"), which is correct *if* `awaiting_review` were ever reached, since a job legitimately
waiting on a human is not "stuck" in the reaper's sense.

But it is never reached. Confirmed two ways:
- `shared/intake_worker.py::_tick()` (line 99-126) calls `_process(job)` then **unconditionally**
  `intake_queue.mark_job_completed(job_id)` (line 115) on any non-exception return from `_process`.
  `_process()` (line 128-238) itself never calls any status-transition function other than the initial
  `claim_next_job("received", "preprocessing")` in `_tick` — it creates `intake_review_queue` rows (line 188,
  222) when confidence is low, but never touches `intake_jobs.status`.
- `shared/intake_queue.py:31-34`'s `_VALID_STATUSES` tuple lists `awaiting_review` as a legal value (so the
  DB CHECK constraint / RPC layer would accept it), but grepping the whole repo for the literal string
  `awaiting_review` outside `intake_queue.py`'s own declaration and comments finds no writer anywhere.

**Net effect (confirms the brief's suspicion in item 3 and matches `STATE_MACHINE_SPECIFICATION.md:23`'s
prior finding that `classifying/extracting/matching/dedup_check` are dormant): `awaiting_review` is dormant
in exactly the same way — declared in the schema, never written, by any code path, ever.** A low-confidence
job is marked `intake_jobs.status = 'completed'` (via the unconditional `mark_job_completed` in `_tick`) at
the exact same moment its `intake_review_queue` row is created with `resolved_at = NULL` — see §6 below for
why this is the concrete "two disagreeing truths" instance the brief asked about.

---

## 4. Frontend audit (`static/vindex.js`)

Grep for `/entities/|/jobs/|potrebna_provera|nesiguran|smart-intake|klasifikacija_nesigurna` locates every
relevant call site:

- `static/vindex.js:21131`, `:21162` — `GET /api/smart-intake/jobs/{id}` polling (`_siPollJobs`,
  `_siFetchCompletedDetails`); reads `d.potrebna_provera` into `sf.review` (lines 21142, 21170).
- `static/vindex.js:21223-21244` (`_siRenderReview`) — for each extracted entity with `needs_review: true`,
  renders an editable `<input>` + a "Sačuvaj" (Save) button (line 21230-21233). This **is** a real, live,
  working UI for the human-correction half of the loop.
- `static/vindex.js:21251-21273` (`siCorrectEntity`) — the Save button's handler; calls
  `POST /api/smart-intake/entities/{entityId}/correct` (line 21257), on success sets `ent.needs_review = false`
  **client-side only** (line 21265) — it does not re-fetch or re-derive this from the server, and given §0,
  the server-side `intake_review_queue` row for that job is never actually resolved regardless of how many
  entities get corrected this way.
- `static/vindex.js:21241-21243` — displays the review reason/fields banner (`⚠ Proverite: ...`) sourced from
  `sf.review.polja`, i.e. `potrebna_provera.polja` from the API — this is a **passive display only**, not a
  gate.
- `static/vindex.js:21306` — `POST /api/smart-intake/jobs/{id}/finalize` (`siFinalize`). Critically, the
  "Kreiraj predmet" button (`si-btn-next`) is enabled unconditionally at `static/vindex.js:21248`
  (`document.getElementById('si-btn-next').disabled = false;`) immediately after rendering the review list,
  **regardless of whether any `needs_review` entities remain uncorrected.** There is no client-side gate
  mirroring the (nonexistent) server-side one from §2 — a lawyer can click through to case creation with
  flagged fields still showing the yellow "needs review" state.
- `klasifikacija_nesigurna`/`nesigurna_polja` (the finalize response fields Sprint 003 added,
  `routers/smart_intake.py:931-932`) — **zero matches** anywhere in `static/vindex.js`. Confirmed dead signal:
  the backend computes and returns it, but no frontend code reads it. `_siShowRecap`
  (`static/vindex.js:21345-21370`) only surfaces `needs_review` counts computed from entity-level data already
  fetched during Step 3 (line 21351-21352, 21360-21362) — a different, narrower signal that predates and does
  not depend on the finalize response's `klasifikacija_nesigurna` field at all.

**Answer to the brief's precise question**: there is genuine frontend surface for *entity-level* correction
(the Save button, wired end-to-end to `correct_entity`), but **zero frontend surface of any kind for
"resolve this review as done"** — no button, no icon, no state anywhere in `vindex.js` that would call
`resolve_review_queue_for_job` if it were wired up server-side. If Sprint 004 wires the backend function into
an existing call site (most naturally: have `correct_entity` call it once all of a job's flagged entities are
corrected, or have `finalize_intake_job` call it on successful finalize), **no new frontend needs to be built
for that specific resolution action** — the existing Save-button flow and Finalize-button flow are the only
two plausible trigger points, and both already exist and already call the right endpoints; only their backend
handlers need the missing call added. A frontend gap does exist, but it's a different one: nothing tells the
lawyer, in the UI, that review resolution never actually completed (see §6) — that's a "surface the true
state" gap, not a "missing action button" gap.

---

## 5. Audit / provenance / correlation ID on the human-correction path

`shared/intake_documents.py::correct_entity()` (line 223-270) and its only caller,
`POST /api/smart-intake/entities/{entity_id}/correct` (`routers/smart_intake.py:289-321`), call **exactly
one** persistence side-effect beyond the entity update itself: `write_processing_outcome(...)` (line 257-267),
which inserts into `intake_processing_outcomes` (an analytics/accuracy table, per its own docstring at
`shared/intake_documents.py:108-137` — "founder-ov eksplicitan zahtev... za buduće podešavanje
pragova/heuristika," i.e. built for threshold-tuning analytics, not for audit/provenance).

**Confirmed missing, all three**:
- **No `log_action`/`log_action_sync` call** (`shared/audit_immutable.py:127`, `:167`) anywhere in
  `correct_entity()` or the router endpoint — contrast directly with `routers/drafting.py:236-241`'s
  `_stage_draft_for_review`, which does call `log_action(action="drafting_generisan", ...)` for the
  structurally analogous "AI output, human will review" moment in the staging_memory system (§1, row 2).
  Even if it were added, `"entity_corrected"`/similar is **not present** in `AUDITABLE_ACTIONS`
  (`shared/audit_immutable.py:96-121`, full list checked) — `log_action` silently no-ops for any action not
  in that allowlist (per its own docstring), so wiring this in requires both the call *and* a new allowlist
  entry, a small, bounded, no-new-architecture change.
- **No correlation ID** — `shared.ai_provenance.current_correlation_id()` is the established pattern (used by
  `log_action_sync`, `shared/ai_client.py`, `routers/case_dna.py`, `routers/evidence.py`, and 15+ other files
  per repo-wide grep), but `intake_documents.py` never imports or calls it anywhere in the file.
- **No provenance/lineage record** — contrast with `routers/drafting.py`'s staging promotion
  (`_promote_staged_draft_to_pinecone`, line 250-269), which writes `origin`/`parent_id`/`origin_chain`
  metadata (`shared/vector_origin.py`'s `ORIGIN_LAWYER_VERIFIED`/`ORIGIN_AI_GENERATED`) precisely to record
  that a human verified this specific value. `correct_entity` has no equivalent — the only record that a human
  changed a value is `extracted_entities.corrected_value` + `.reviewed` (the row itself, no separate lineage
  entry) and the best-effort, non-authoritative `intake_processing_outcomes` analytics row.

`shared/intake_queue.py::write_audit()` (line 218-238) — the append-only `intake_audit_log` table used
elsewhere in the Smart Intake pipeline (worth noting since it's a plausible existing sink) — is also never
called from `correct_entity` or its endpoint; grepping its only call sites confirms it's used exclusively by
`intake_queue.py`'s own job-lifecycle functions (enqueue/claim/complete/fail), not by anything in
`intake_documents.py`.

---

## 6. Canonical state-machine violation: the two disagreeing "is this done" signals

Direct, concrete confirmation of the brief's suspicion, built entirely from facts established in §2/§3 above:

For any job where `_process()` (`shared/intake_worker.py:128-238`) writes at least one `intake_review_queue`
row (low confidence classification and/or extraction — line 188 for OCR failure, line 222 for low-confidence
fields) but does **not** throw an exception:

1. `_tick()` (`shared/intake_worker.py:99-126`) still calls `mark_job_completed(job_id)` unconditionally
   (line 115) — no branch checks whether a review row was just created. `intake_jobs.status` becomes
   `'completed'`.
2. The `intake_review_queue` row created in the same `_process()` call has `resolved_at = NULL` and (per §0)
   will **never** transition to non-NULL through any live code path.

**Result: two separate tables disagree, permanently, about whether the same unit of work is done.**
`intake_jobs.status = 'completed'` says "the queue considers this job finished" — and it's not wrong by its
own narrow definition (the worker did finish its attempt, in the sense of not crashing). `intake_review_queue`
with `resolved_at IS NULL` says "a human still needs to look at this" — also not wrong. Nothing reconciles the
two. This is exactly the pattern `docs/architecture/STATE_MACHINE_SPECIFICATION.md:29` already named for the
COMPLETED row of its table ("answers 'is the queue job done,' not 'is the case-file document done' (3-way
fragmentation, Sprint 001, unchanged)") — this audit adds a precise fourth instance of the same shape: queue-
done vs. review-done, not just queue-done vs. case-file-done.

Consequence downstream: `finalize_intake_job`'s only status gate (`routers/smart_intake.py:468-469`) is
`if job["status"] != "completed": raise 409`. Since `status='completed'` is reached regardless of outstanding
review (point 1 above), **the only gate that exists today actively permits — never blocks — finalizing a job
with an unresolved review.** Combined with §2's finding (no separate `classification_uncertain` block exists
either), there is currently no status value, no gate, and no code path anywhere that prevents a job with an
unresolved `intake_review_queue` row from being finalized into a permanent case.

Per `docs/architecture/STATE_MACHINE_SPECIFICATION.md`'s own canonical model (COMPLETED / REVIEW_REQUIRED /
FAILED_FINAL as the only valid terminal states), a job in this state is simultaneously claiming COMPLETED
(via `intake_jobs.status`) while genuinely being in REVIEW_REQUIRED (via the unresolved `intake_review_queue`
row) — the exact "third state" (silently treated as done when it isn't) the mission's own stated principle
(`docs/architecture/REVIEW_QUEUE_SPECIFICATION.md:3-4`) forbids, just one layer up from where Sprint 003 fixed
it (Sprint 003 closed the *classification-value* version of this problem inside finalize; this is the
*job-status* version of the same problem, one level higher in the stack, still fully open).

---

## Summary table — confirmed defect vs. working-as-designed

| Claim | Status |
|---|---|
| `resolve_review_queue_for_job` has zero call sites | **Confirmed defect** (re-verified, §0) |
| `staging_memory`/`is_lawyer_approved` is a second, independent, working review-queue system | **Confirmed working-as-designed, but structurally a second canonical system** — Phase 2 decision needed (§1) |
| `finalize_intake_job` blocks on `classification_uncertain` | **Confirmed false — it only skips one background re-classification task; case creation proceeds unconditionally** (§2) |
| `intake_review_queue` has TTL/reminder/escalation | **Confirmed false — no such columns exist at all** (§3a) |
| `awaiting_review` status is ever reached | **Confirmed false — dormant, same shape as the already-known `classifying`/`extracting`/`matching`/`dedup_check` gap** (§3b) |
| `reap_stale_jobs` mishandles `awaiting_review` | **Not a defect on its own terms (correctly excludes it) — but moot, since the status is never reached anyway** (§3b) |
| Frontend has an entity-correction UI | **Confirmed working** — Save button wired to `/entities/{id}/correct` (§4) |
| Frontend has a "resolve review" UI | **Confirmed absent — no button/state exists that would call `resolve_review_queue_for_job`** (§4) |
| Frontend surfaces `klasifikacija_nesigurna`/`nesigurna_polja` | **Confirmed dead — computed server-side, never read client-side** (§4) |
| `correct_entity` has audit/provenance/correlation ID | **Confirmed absent on all three counts** — contrast with `staging_memory`'s working equivalent (§5) |
| `intake_jobs.status='completed'` and unresolved `intake_review_queue` can coexist | **Confirmed — the concrete disagreeing-truths instance the brief predicted** (§6) |

## Files read/cited (for the fixing pass)

`routers/smart_intake.py`, `shared/intake_documents.py`, `shared/intake_worker.py`, `shared/intake_queue.py`,
`shared/audit_immutable.py`, `routers/drafting.py`, `routers/agent_notifications.py`, `routers/learning.py`,
`routers/morning_briefing.py`, `routers/evidence.py`, `migrations/074_intake_phase1a.sql`, `static/vindex.js`,
`docs/architecture/STATE_MACHINE_SPECIFICATION.md`, `docs/architecture/REVIEW_QUEUE_SPECIFICATION.md`.
