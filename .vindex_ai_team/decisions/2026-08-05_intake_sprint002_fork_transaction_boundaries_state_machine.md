# Program Intake Sprint 002 — Fork B (Chief Systems Architect lens)
## Ownership Mapping, Transaction Boundary Analysis, Canonical Lifecycle State Machine

**Date**: 2026-08-05
**Scope**: Phase 1 (ownership mapping), Phase 3 (transaction boundary analysis), Phase 4 (canonical lifecycle
state machine design). Read-only investigation, no code changes. Builds directly on Program Intake Sprint 001
(2026-08-04) — `docs/architecture/INTAKE_ARCHITECTURE_REPORT.md`, `INTAKE_SOURCE_OF_TRUTH_MATRIX.md`,
`INTAKE_FAILURE_RECOVERY_MATRIX.md` — not re-derived from scratch. Forbidden modules (OCR quality, Genome,
Decision Engine, Strategy, Copilot, Briefing, Timeline, Search, Alerts, Tasks, Dashboard, Firm Brain) are
mentioned only where they intersect the intake journey, never analyzed on their own terms.

---

## 0. Headline verdict up front

Sprint 001's Failure Recovery Matrix claim — **"No multi-statement transaction exists — each INSERT/UPDATE is
independently committed... there is no partial-transaction state to roll back from"** — is **half right, and
the half that's wrong matters**.

- **TRUE** for every write against `predmet_dokumenti`, `predmet_klijenti`, `predmet_hronologija`,
  `intake_documents`, `extracted_entities`, `intake_review_queue`, `intake_processing_outcomes`, `klijenti` —
  every one of these is a bare `supa.table(...).insert()/.update()/.delete()`, independently committed, no
  rollback capability, confirmed by direct grep across all 5 named files (§3.1).
- **FALSE** for the `intake_jobs` queue mechanics themselves. `enqueue_intake_job`, `claim_intake_job`,
  `complete_intake_job`, `fail_intake_job` (migration 073) are genuinely atomic — single `plpgsql` function
  bodies, one implicit Postgres transaction each, confirmed by reading the actual `CREATE OR REPLACE FUNCTION`
  bodies (§3.2). Sprint 001's own Failure Recovery Matrix elsewhere correctly credits these RPCs with atomicity
  ("atomska Upload Transaction") — the "Rollback" row's blanket statement just doesn't carry that nuance
  through, and a reader taking that row alone would wrongly conclude nothing in this codebase is transactional.
- **NEW, not previously documented**: Pipeline C's finalize (`smart_intake.py:373-769`) writes its own
  idempotency marker (`intake_jobs.predmet_id`) as a **bare, unwrapped, LAST-step `.update()`** — after 6-8
  other non-atomic writes already committed. If that specific write fails, the endpoint raises unhandled and
  every prior write (predmet, client, deadline, document, Pinecone vectors) is already permanent, but the
  job-level idempotency check that's supposed to prevent a duplicate retry (`if job.get("predmet_id"): return
  already_finalized`) still reads `NULL`. A lawyer who understandably retries after seeing an error gets a
  **second full predmet created from the same document** — case, client link, deadline, and Pinecone chunks,
  all duplicated. This is a sharper and more dangerous variant of the same defect class as `INTAKE-001`
  (deferred, ghost vector) and is detailed in §3.4 as this fork's primary new finding.
- **NEW, narrower**: `IntakeWorker._process()`'s own completion signal (`write_processing_outcome`, the exact
  mechanism Sprint 001 built to fix the "false success" bug) is itself allowed to fail silently by explicit
  design, and that failure does **not** block `mark_job_completed`. The invariant Sprint 001 relies on
  ("`intake_jobs.status='completed'` implies `intake_processing_outcomes` has a row") is therefore
  probabilistic, not guaranteed — detailed in §3.3. Low severity (no user-facing data is lost), but the
  invariant as stated is not actually airtight.

---

## 1. Phase 1 — Ownership mapping

Canonical journey: Upload → Storage → Metadata → Queue → Worker(claim) → OCR → Extraction → Persistence →
Vector → Audit → Finalize. Not every stage applies to every pipeline; "N/A" is itself informative.

### Pipeline A — synchronous per-case upload (`api.py:4061` `predmet_upload_auto_analyze`)

| Stage | Creates | Modifies | Completes | Deletes | Confirms success (concrete signal, not "didn't throw") |
|---|---|---|---|---|---|
| Upload | `api.py:4109` `file.read()` into memory | — | — | — | `len(raw) <= _MAX_UPLOAD_BYTES` check (4110); no persistence yet |
| Storage | `api.py:4127-4141` — encrypted upload to `intake-dokumenti` bucket, reusing `smart_intake.py::_encrypt`/`_STORAGE_BUCKET` | — | `_original_storage_path` var set on success | never | **Real signal**: `_original_storage_path` is `None` on failure, a real key on success (4127 comment: "storage_path never lies"). Best-effort — failure does not abort the request |
| Metadata | folded into Persistence row (no separate metadata stage) | — | — | — | — |
| Queue | N/A — no queue on this pipeline | — | — | — | — |
| Worker(claim) | N/A — synchronous, no worker | — | — | — | — |
| OCR | `api.py:4150` `extract(tmp_path)` — text held in-memory only, never persisted as a durable artifact (matches Sprint 001 Source-of-Truth Matrix's "OCR text: gap, not duplication") | — | — | tempfile deleted in `finally` (4165-4168) | `is_scanned` flag (4160); hardcoded `ocr_confidence=0.6` when used elsewhere (Program Beta finding, unchanged) — **not a real measurement**, a known coverage gap |
| Extraction | `_detect_doc_type(text)` (4177, ephemeral, prompt-routing only, never persisted — Sprint 001 §2 confirms this is one of the 2 ephemeral classifiers) | — | — | — | No confidence-graph equivalent on this pipeline — extraction here means "pick a prompt," not "extract fields" |
| Persistence | `api.py:4241-4267` `predmet_dokumenti` insert (CREATE and COMPLETE happen in the **same statement** — `status` is set at insert time, 4256, never updated afterward by this pipeline) | `routers/evidence.py::klasifikuj_i_sacuvaj` (different writer, background task, 4301-4310) later `UPDATE`s `tip_dokaza` | Row itself, at insert | Not found in reviewed code (no delete path for `predmet_dokumenti` located in Pipeline A) | **Real signal**: `_dok_id` non-null, **hard-checked** — `api.py:4279-4283` raises HTTP 500 if the insert didn't yield an id (Project Sentinel precedent). This is the one hard-fail checkpoint on this pipeline |
| Vector | `ingest_session(...)` `api.py:4198-4223` into `_owner_ns` (`rag_owner_namespace`) | — | — | never (no ghost-vector cleanup) | **Real signal, not just "didn't throw"**: `_pinecone_ok` flag is threaded into the `status` column itself (`"indeksirano"` vs `"sacuvano"`, 4256) — the DB row honestly encodes whether indexing actually happened |
| Audit | `asyncio.create_task(log_action("dokument_upload", ...))` `api.py:4287-4299`; `dokument_view` added Sprint 001 at `api.py:4849-4859` | — | — | never (append-only `audit_immutable`) | **No confirmation at all** — fire-and-forget task, `log_action` swallows its own errors internally (`shared/audit_immutable.py:139`: "Vraća ID... ili None ako upis nije uspeo... NIKAD ne blokira"); caller never checks the return value or awaits the task, so an audit-write failure is invisible even in logs unless `log_action`'s own internal logging catches it |
| Finalize | N/A — this pipeline has no separate finalize step, the upload endpoint *is* the finalize | — | — | — | — |

### Pipeline B — durable-queue upload (`routers/smart_intake.py:92` upload) + `shared/intake_worker.py` (worker)

| Stage | Creates | Modifies | Completes | Deletes | Confirms success |
|---|---|---|---|---|---|
| Upload | `smart_intake.py:118` `f.read()` | — | — | — | Suffix/size/empty checks (110-124) before any write |
| Storage | `smart_intake.py:129-138` encrypted upload to `intake-dokumenti` | — | — | never (orphan risk, `INTAKE-002`, Sprint 001, unchanged) | **Real signal**: `storage_key` only passed to `enqueue_job` after `bucket.upload()` returns without exception (129-142); no post-upload existence re-check |
| Metadata | `smart_intake.py:165-173` `.update({"original_filename","mime_type"})` on the just-created job — a **second, non-atomic follow-up write**, explicitly NOT part of the `enqueue_intake_job` RPC transaction (comment 158-164: "menjanje potpisa RPC-a koji je već u produkciji") | Same call | — | — | Best-effort — failure logged, non-fatal; extractor falls back to guessing suffix from filename/mime being `None`, defaulting to `.pdf` (`intake_worker.py:263`) |
| Queue | `intake_queue.enqueue_job()` → `enqueue_intake_job` RPC (`smart_intake.py:144-156`) | — | Job row created **and** idempotency-checked in the same RPC call | never | **Genuinely atomic real signal**: RPC returns `v_job_id`; idempotency key collision returns the *existing* id instead of creating a duplicate (migration 073:159-164) |
| Worker(claim) | — | `claim_intake_job` RPC flips `status` and sets `claimed_at` (`intake_queue.py:72-86`) | — | — | **Atomic, race-proof**: `SELECT...FOR UPDATE SKIP LOCKED` inside one `plpgsql` function (migration 073:198-219) — confirmed two workers cannot claim the same row |
| OCR | `IntakeWorker._download_and_decrypt` + `_extract_text` (`intake_worker.py:163-175`) — text in-memory only, same non-persistence gap as Pipeline A | — | — | tempfile always deleted (`finally`, 171-175) | `is_scanned`/`ocr_used` booleans only; same hardcoded `0.6` confidence issue as Pipeline A when OCR is used (202) |
| Extraction | `intake_documents.create_document()` (bare insert, `intake_worker.py:197-204`) + `insert_entities()` (bare bulk insert, 205) — this **is** the real Confidence Graph, unlike Pipeline A | `correct_entity()` (`intake_documents.py:204-251`) — 10-second-fix path, separate endpoint, not part of this sequence | — | `delete_partial_document()` (`intake_documents.py:157-169`) — used by the idempotency-repair path, not normal completion | **Real per-field signal**: `extracted_entities.confidence` per entity, `intake_documents.classification_confidence` for the doc type — genuine Confidence Graph, not a boolean |
| Persistence | Same `create_document()` call above — Pipeline B has no separate "attach to case" persistence step (that's Pipeline C's job) | — | — | — | — |
| Vector | N/A — Pipeline B never touches Pinecone; that happens only at Pipeline C finalize | — | — | — | — |
| Audit | `intake_queue.write_audit()` (`intake_queue.py:197-217`) — **separate, parallel** audit table `intake_audit_log`, no `correlation_id` column, no cross-reference to `audit_immutable` (Sprint 001 Source-of-Truth finding, unchanged, confirmed by this fork's read of the same file) | — | — | never (append-only) | Best-effort, wrapped try/except, logs warning on failure (216-217) |
| Finalize | N/A on this pipeline — job reaches `status='completed'` via `complete_intake_job` RPC (`intake_worker.py:115`), but "finalized into a real case" is Pipeline C's separate job | — | `complete_intake_job` RPC — atomic status+audit+outbox in one transaction (migration 073:230-247) | — | **Atomic real signal**: same RPC pattern as enqueue |

### Pipeline C — finalize (`routers/smart_intake.py:373` `finalize_intake_job`)

| Stage | Creates | Modifies | Completes | Deletes | Confirms success |
|---|---|---|---|---|---|
| Upload/Storage/Queue/Worker/OCR(job)/Extraction | Already done by Pipeline B before finalize is ever called — finalize reads `intake_jobs`/`intake_documents`/`extracted_entities`, does not re-create them | — | — | — | Guarded by `job["status"] != "completed"` check (403) at 403-404 |
| OCR (re-run) | **Re-decrypts and re-extracts the same file from scratch** (`smart_intake.py:595-606`, reusing `IntakeWorker._download_and_decrypt`) — the job's already-classified text from Pipeline B's `_process()` is **not reused**, matching Sprint 001's Source-of-Truth finding "OCR text: not persisted anywhere as a durable artifact" | — | — | tempfile deleted (602-606) | Same `is_scanned`/`ocr_used` flags, discarded again after this call |
| Persistence (predmet) | `predmet` insert (468-476) OR attach to existing (432-441, `body.predmet_id` present) | — | Row created at insert, no further completion step | never found | **Hard-checked**: `if not pred_r.data: raise HTTPException(500)` (477-478) — real checkpoint |
| Persistence (client) | `klijenti` insert if not found (499-507) | — | — | never | Best-effort, wrapped, logged only (523-524) — **not** hard-checked |
| Persistence (link) | `predmet_klijenti` insert (516-522) | — | — | never | Same try/except as client (486-524) |
| Persistence (deadline) | `predmet_hronologija` insert (571-581) | — | — | never | Best-effort (`rok_dodat` flag reflects real outcome, 567-584) |
| Vector | `ingest_session(...)` into `_owner_ns` (626-644) | — | — | never | `pinecone_ok` flag threaded into `status` column exactly like Pipeline A (666) |
| Persistence (document) | `predmet_dokumenti` insert, 3 fallback variants (674-687) | — | `doc_linked` flag set from this result | never | `doc_linked = bool(dok_ins and dok_ins.data)` — **honest but not hard-checked**; overall response still returns `"ok": true` even if this is `False` (`INTAKE-001`, Sprint 001, unchanged, confirmed) |
| Audit | `_track_event(...)` best-effort (741-757) | — | — | never | Wrapped in bare `except: pass` (756-757) — **weakest audit confirmation of any pipeline**, not even a logged warning |
| **Finalize marker** | — | `intake_jobs.update({"predmet_id": predmet_id})` (**737-739**) | This is the ONLY completion signal for the whole finalize operation — the idempotency check at the top of the function (400-401) reads this exact column | never | **Bare update, NOT wrapped in try/except, NOT part of any RPC.** This is this fork's primary new finding — see §3.4 |

---

## 2. Cross-cutting ownership notes (not new vs. Sprint 001, restated for completeness)

- `predmet_dokumenti.status` is set once, at INSERT, on every one of the 6 writers Sprint 001 catalogued
  (confirmed again here for A/C/wizard/onboarding/drafting) — none of them later `UPDATE` it. There is no
  "in-progress → done" transition visible on this column on any pipeline; it is a single write-once field
  disguised as a lifecycle field.
- `tip_dokaza`/`klasifikovan_at` ARE modified after initial insert — by `routers/evidence.py::klasifikuj_i_sacuvaj`
  (the shared classifier UPDATE, confirmed at `routers/evidence.py:210` area) — this is the **only** genuine
  post-insert modification of a `predmet_dokumenti` row found across all 3 pipelines and the 3 secondary
  writers (wizard/onboarding/drafting).
- No delete path for `predmet_dokumenti` rows was found in any of the files reviewed for this fork. `evidence.py`
  soft-delete patterns elsewhere in the app were not checked (out of this fork's file scope) — flagged as an
  open question, not a claim either way.

---

## 3. Phase 3 — Transaction Boundary Analysis

### 3.1 Every `.execute()`/`.rpc()` across the 5 named files, classified

Grepped exhaustively (`\.execute\(\)|\.rpc\(|supa\.table\(` and `_get_supa\(\)\.table\(`) across `api.py`
(intake-relevant section only), `routers/smart_intake.py`, `shared/intake_worker.py`, `shared/intake_documents.py`,
`shared/intake_queue.py`.

**Genuinely atomic (RPC, confirmed by reading the function body, one `plpgsql` block = one implicit transaction):**

| RPC | Called from | Function body location | What's inside the one transaction |
|---|---|---|---|
| `enqueue_intake_job` | `intake_queue.py:56-64` | `migrations/073_intake_foundations.sql:145-178` | idempotency check + `intake_jobs` insert + `intake_audit_log` insert + `events` outbox insert — 3 statements, 1 transaction |
| `claim_intake_job` | `intake_queue.py:80-84` | `073:198-219` | `SELECT...FOR UPDATE SKIP LOCKED` + `UPDATE...RETURNING` — 1 statement, atomic by Postgres row-lock semantics |
| `complete_intake_job` | `intake_queue.py:94-96` | `073:230-247` | status UPDATE + audit insert + outbox insert — 3 statements, 1 transaction |
| `fail_intake_job` | `intake_queue.py:113-121` | `073:260-292` | branch on dead-letter vs retry, each branch does UPDATE + audit insert (+ outbox insert on dead-letter only) — 1 transaction per call |

All 4 are `SECURITY DEFINER`, `REVOKE ALL FROM PUBLIC` / `GRANT ... TO service_role` only (073:345-354) — never
reachable from anon/authenticated roles, matching the `deduct_credit()` pattern the migration's own comments
cite as precedent (073:35).

**Bare, independently-committed, NOT atomic with anything before or after them** (representative, not
exhaustive — every row in Phase 1's tables above that says "insert"/"update"/"delete" without "RPC" is one of
these):

`intake_documents.py`: `create_document` (44-57), `insert_entities` (60-75), `create_review_queue_entry`
(78-93), `write_processing_outcome` (96-140, itself wrapped in a swallowing try/except — see §3.3),
`delete_partial_document` (157-169, itself a **sequence of 3** independently-committed deletes),
`correct_entity` (204-251, itself 3 sequential writes: select, update, then a call into
`write_processing_outcome`), `resolve_review_queue_for_job` (254-265).

`smart_intake.py`: the `original_filename`/`mime_type` follow-up update (165-173), all of Pipeline C's writes
(§1 table above, 432-739) except the 4 RPC calls it doesn't use at all — **Pipeline C uses zero RPCs**, every
single write in the entire finalize flow is a bare Supabase client call.

`api.py`: every write in Pipeline A (§1 table) — also zero RPC usage.

### 3.2 Does `supabase-py` expose a multi-statement transaction primitive?

No. `requirements.txt:10` pins `supabase==2.28.3`; confirmed installed `postgrest==2.28.3` (`pip show`). Neither
package exposes a `BEGIN`/`COMMIT`/session-transaction API over PostgREST — PostgREST itself executes each HTTP
request as a single implicit transaction and has no concept of a client-held multi-request transaction. A
codebase-wide grep for `psycopg2|asyncpg|BEGIN;|begin_transaction|\.transaction\(` across all `.py` files
(excluding tests) found exactly one hit, in `scripts/export_rls_policies.py` — an unrelated one-off tooling
script, not part of the running application. **Confirmed: `.rpc()` calling a `plpgsql` function is the ONLY
way this codebase can get atomicity across more than one statement.** Any future requirement for true
multi-step atomicity in the intake journey (or anywhere else) must be pushed into a Postgres function — it
cannot be orchestrated from Python, full stop, given the current dependency stack.

### 3.3 IntakeWorker._process() — the invariant Sprint 001 built is not fully airtight

Sprint 001's fix (`intake_worker.py:137-161`, `intake_documents.py::has_processing_outcome`) uses "does
`intake_processing_outcomes` have a row" as the sole signal that a job's processing genuinely finished,
specifically because `write_processing_outcome()` is (by explicit design, per its own docstring at
`intake_documents.py:107-109`, "best-effort... greška ovde ne sme da obori obradu") the **last** statement in
both branches of `_process()` (177-192 for the OCR-failed branch, 194-225 for the normal branch).

But `write_processing_outcome()` itself (96-140) wraps its own insert in a try/except that **logs a warning and
returns, swallowing the exception** (139-140) rather than propagating it. Trace the consequence:

1. `_process()` calls `write_processing_outcome(...)` as its final line (218-221 / 189-191).
2. If that insert throws (network blip, transient DB error, anything), the exception is caught **inside**
   `write_processing_outcome`, never reaches `_process()`.
3. `_process()` therefore returns normally — `_tick()`'s `try: await self._process(job)` block sees no
   exception (`intake_worker.py:113-116`).
4. `_tick()` proceeds to call `await intake_queue.mark_job_completed(job_id)` — the atomic `complete_intake_job`
   RPC — marking the job `status='completed'`.
5. `claim_intake_job` only ever claims rows in `status='received'` (migration 073:211). A `completed` job is
   never reclaimed, so `has_processing_outcome()` is never checked again for this job.

Net effect: the exact invariant Sprint 001 states as the fix ("job=completed implies processing_outcome
exists") does not actually hold in this one case — it holds **only when `write_processing_outcome` itself
succeeds**, which the code deliberately allows to not happen. This is narrower and lower-severity than the bug
Sprint 001 fixed, for a specific reason: by the time `write_processing_outcome` runs, `create_document()` and
`insert_entities()` (and, if applicable, `create_review_queue_entry()`) have **already** committed successfully
— the user-facing correctness of the document (its classification, its Confidence Graph, its review routing)
is already complete and correct. The only thing silently lost is the founder's own explicitly-requested
future-tuning analytics row (`intake_processing_outcomes` — "ne za analitiku danas nego za fino podešavanje
pragova... za mesec dana", `intake_documents.py:28-31`) for that one job. No document is lost, duplicated, or
left in an ambiguous state from a lawyer's point of view. Flagged here because Sprint 001's own stated
invariant is the thing being checked for precision, not because this is a user-facing defect — the correct
characterization is "the completion-signal write is not itself transactional with the completion state it's
supposed to prove," which is exactly the kind of claim this fork was asked to verify rather than accept.

`delete_partial_document()` (157-169) is itself a sequence of 3 independently-committed deletes (`extracted_entities`
→ `intake_review_queue` → `intake_documents`, FK-order-correct per its own docstring). If a crash happens
mid-sequence — e.g., after the `extracted_entities` delete commits but before the `intake_documents` delete
runs — the next retry's `has_processing_outcome()` check still correctly returns `False` (nothing about that
outcome changed), so `delete_partial_document()` runs again; deleting already-gone rows by id is a no-op, not
an error. This is a genuinely self-healing design **despite** having no transaction wrapping it — worth naming
explicitly as the pattern Phase 4 should generalize (idempotent, re-runnable steps compensating for the absence
of rollback), not an accident.

### 3.4 Pipeline C finalize — the sharpest live gap this fork found

Walking the exact sequence at `smart_intake.py:373-769` (full detail in §1's Pipeline C table):

1. `predmet` insert or attach (432-479) — **hard-checked**, raises 500 if it fails, nothing committed on
   failure. Clean boundary.
2. `klijenti` find-or-create + `predmet_klijenti` link (482-524) — best-effort, wrapped, non-fatal on failure.
   If this fails, step 1's predmet is **already committed** — case exists without the client link. Honest via
   `klijent_dodat: bool(klijent_ime)` in the response (766), not silently hidden.
3. Conflict-check background task (546-564) — fire-and-forget `asyncio.create_task`, no confirmation signal at
   all, by design (non-blocking per its own comment 526-539).
4. `predmet_hronologija` (deadline) insert (571-584) — best-effort, `rok_dodat` flag honest.
5. Decrypt → OCR → chunk → Pinecone ingest (588-644) — best-effort, `pinecone_ok` flag threaded into the
   document row's `status` (666), same honest pattern as Pipeline A.
6. `predmet_dokumenti` insert, 3 fallback variants (674-687) — `doc_linked` flag honest but **not hard-checked**
   at the top level; this is `INTAKE-001` (Sprint 001, deferred, unchanged) — the response still says
   `"ok": true` even if `doc_linked=False`.
7. Evidence classify background task (725-735) — fire-and-forget.
8. **`intake_jobs.update({"predmet_id": predmet_id}).eq("id", job_id).execute()` (737-739)** — bare call, no
   try/except around it, not an RPC. This single line is the **entire idempotency mechanism** for the finalize
   endpoint: the function's own opening check (400-401) is `if job.get("predmet_id"): return {"ok": True,
   "predmet_id": ..., "already_finalized": True}`.
9. `_track_event` analytics (741-757) — wrapped in bare `except: pass`.

**If step 8 throws** — and nothing in the code prevents that; it's a plain network-dependent Supabase call
identical in shape to a dozen other calls in this same function that already have try/except around them —
the exception propagates unhandled out of `finalize_intake_job`. FastAPI's default handling turns that into an
HTTP 500 (no custom handler was found intercepting this specific path). By this point steps 1, 2/4/5/6
(whichever succeeded) are **permanently committed**: a real `predmet` row, possibly a real client + link, a
possible deadline, indexed Pinecone vectors, and a `predmet_dokumenti` row all exist. The lawyer sees an error
response. If the lawyer (or the frontend, on a 500) retries the same `POST /jobs/{job_id}/finalize` call, the
opening idempotency check reads `job.get("predmet_id")` — still `NULL`, because the one write that would have
set it is exactly the write that just failed. **The entire 700-line function runs again from scratch**: a
second `predmet` is created (or, if `body.predmet_id` was already supplied for the *original* call and the
retry omits it because the client doesn't know a case was already made, a *second new* predmet; if the retry
resends the same `body.predmet_id`, attach-mode still creates a second client link, second deadline, second
document, second Pinecone ingest — attach-mode does not deduplicate against an already-attached document
either). This produces exactly the "document/case duplicated" failure shape this sprint's charter treats as a
defect class, and it is **not** covered by Sprint 001's Failure Recovery Matrix "Duplicate upload (same file
twice)" row, which reasons about uploading the same file twice through Pipeline B, not about retrying a single
finalize call after its own last write fails. It is a distinct scenario from `INTAKE-001` (which is about the
*document-attach* sub-step failing while the case creation succeeds, producing an honest `doc_linked: False`)
— this is about the *finalize-marker* write itself failing, which produces a **silent, undetectable, full
duplicate** on the very next retry, with the response the first time being an honest-looking failure (500) that
actually masks a mostly-successful operation.

**Concrete comparison to the pattern already proven in this same codebase**: `enqueue_intake_job`'s entire
reason for existing as an RPC (rather than a bare insert) is precisely to make job-creation atomic with its own
idempotency key check (migration 073:159-164, "Idempotentna preko idempotency_key"). Finalize's job-completion
marker never received the equivalent treatment — it's the same shape of problem (a state-transition write that
must be atomic with the check that prevents duplicate execution) solved one way in Pipeline B/upload and left
unsolved in Pipeline C/finalize, in the same file, written by the same author, eight months apart in the same
sprint history. This is not a design philosophy gap; it looks like the specific write at line 737-739 was
simply never revisited once the rest of the finalize flow's easier failure modes (doc-link, conflict-check,
Pinecone) were handled with best-effort wrapping.

### 3.5 Summary: the transaction boundary as it actually exists today

- **One boundary per RPC call** — `enqueue_intake_job`, `claim_intake_job`, `complete_intake_job`,
  `fail_intake_job` — each is one Postgres transaction, confirmed atomic by reading the function bodies, and
  each is the exclusive means of achieving any multi-statement atomicity anywhere in this codebase (no
  competing mechanism exists, §3.2).
- **One boundary per bare `.insert()/.update()/.delete()` call** — everything else, dozens of call sites across
  all 3 pipelines, each independently committed the instant it returns, with zero grouping.
- **Nothing spans multiple bare-call boundaries.** A sequence of N bare calls in one Python function (Pipeline
  C finalize has 6-8 of them) is N independent transactions, not one — Sprint 001's blanket statement is
  correct in mechanism, the finding above (§3.4) is about a specific, previously-unflagged consequence of that
  mechanism: the LAST call in that sequence being the idempotency marker, unguarded, is a materially worse
  failure mode than "later steps didn't run" — it's "later steps ran, the marker that says so didn't, and nothing
  stops a full re-run."

---

## 4. Phase 4 — Canonical Lifecycle State Machine design (design only, not implemented)

### 4.1 Proposed canonical states

`UPLOADED → STORED → QUEUED → PROCESSING → OCR_COMPLETE → EXTRACTED → PERSISTED → INDEXED → VERIFIED →
COMPLETED`, with `FAILED → RETRY → FAILED_FINAL → REVIEW_REQUIRED` as the off-ramp branch.

### 4.2 Mapping each pipeline's actual current signals onto the canonical model

| Canonical state | Pipeline A (today) | Pipeline B (today) | Pipeline C (today) |
|---|---|---|---|
| UPLOADED | Implicit — `file.read()` succeeded, no persisted marker | Implicit — same | N/A (inherits B's job) |
| STORED | `_original_storage_path` non-null (local var only, **not persisted as a distinct state** — folds directly into the final `predmet_dokumenti` row) | `intake_jobs.storage_path` persisted at `enqueue_intake_job` time — but that same RPC call also sets `status='received'`, so **STORED and QUEUED are the same instant, same row, indistinguishable** | Reads B's already-stored blob; no new STORED state |
| QUEUED | **No representation at all** — this pipeline has no queue concept | `intake_jobs.status='received'` | N/A |
| PROCESSING | **No representation** — synchronous, the HTTP request itself IS the processing window, nothing external can observe "in progress" | `intake_jobs.status` in (`preprocessing`,`classifying`,`extracting`,`matching`,`dedup_check`) — Pipeline B is the only one with a real intermediate signal here, though the current code only actually uses `preprocessing`; `classifying`/`extracting`/`matching`/`dedup_check` are declared in the CHECK constraint and `_VALID_STATUSES` but **never actually set** by `_process()` (confirmed — `_process()` goes straight from claimed `preprocessing` to the terminal write, no intermediate status updates found in `intake_worker.py`) | N/A — synchronous like A |
| OCR_COMPLETE | **No representation** — `is_scanned`/`ocr_used` are local booleans, never written anywhere as a state | Same — local booleans only, not persisted as a state transition | Same, and this pipeline **redundantly re-runs OCR** that Pipeline B's worker already did (§1 table) — an OCR_COMPLETE state, if it existed and were reused, would let finalize skip this entirely |
| EXTRACTED | Ephemeral doc-type detection only (`_detect_doc_type`), not a Confidence Graph, not persisted as "extraction done" | **This is the one pipeline that genuinely has this state** — `intake_documents` + `extracted_entities` rows existing IS extraction-complete, but the signal is "do these rows exist," not an explicit status value | Reads B's already-extracted entities via `get_job_result` (406-410) — genuine reuse, good |
| PERSISTED | `predmet_dokumenti` row exists (`_dok_id` non-null, hard-checked) | N/A — Pipeline B never writes `predmet_dokumenti`, that's Pipeline C's job entirely | `predmet_dokumenti` row exists (`doc_linked`, **not** hard-checked — §3.4) |
| INDEXED | `status="indeksirano"` vs `"sacuvano"` on the SAME row as PERSISTED — again, two canonical states collapsed into one write | N/A | Same collapse as A |
| VERIFIED | **No representation on any pipeline** — nothing distinguishes "a human confirmed this is correct" from "the AI produced a result and nobody has looked at it yet," except indirectly: `intake_review_queue.resolved_at` (Pipeline B/C only) marks a *review* as resolved, which is adjacent but not the same concept as verifying the whole document |
| COMPLETED | Implicit — HTTP 200 response with no further state anywhere | `intake_jobs.status='completed'` (real, atomic, via `complete_intake_job`) — **but this answers "is the queue job done," not "is the case-file document done"** (Source-of-Truth Matrix's 3-way fragmentation, unchanged) | Implicit — HTTP 200 with `"ok": true`, and **as shown in §3.4, this can be reached honestly while a prior call also silently created a duplicate** |
| FAILED / RETRY / FAILED_FINAL | N/A — no retry mechanism exists (each call is one attempt) | `intake_jobs.status='failed'` after `max_attempts` via `fail_intake_job` — real, atomic, exponential backoff (`intake_queue.py:100-127`) | N/A — no retry mechanism, and (per §3.4) an actual retry-by-the-user of a failed finalize is exactly the dangerous case |
| REVIEW_REQUIRED | N/A | `intake_review_queue` row with `resolved_at IS NULL` — real, this is the one canonical state Pipeline B represents cleanly and explicitly | Inherited from B; finalize can proceed even with an unresolved review item (not checked at 403-410) — worth flagging as a soft gap, not scored here since it's a UX/product question outside this fork's transactional-boundary charter |

### 4.3 Where the canonical model has real gaps vs. where it's just unlabeled

Three different kinds of gap showed up, and they need different treatment:

1. **Purely representational gaps** (the state already logically exists in the code's control flow, it's just
   not written anywhere as a value) — STORED-vs-QUEUED on Pipeline B (both set by the same RPC call), OCR_COMPLETE
   vs EXTRACTED on all three pipelines (both are "did this in-memory step finish," never persisted), PERSISTED
   vs INDEXED on A/C (both set in the same `status` write). These can be answered by a **computed/derived view**,
   not a new column — e.g. a view could report `'queued'` the instant `intake_jobs.status='received'` exists and
   `'stored'` the instant `storage_path` is non-null, because today those two conditions are always true at
   the exact same instant anyway. Deriving them doesn't add information the system doesn't have; it just gives
   two names to one fact. **No migration needed** for these — reuse over new capability, matching Sprint 001's
   own established discipline (Pricing Matrix, `intake_queue_metrics` view precedent, migration 073's own
   comment "IZVEDENI, nikad zaseban stored red").

2. **Genuinely absent, not derivable from anything that exists today**: PROCESSING's intermediate sub-states
   (`classifying`/`extracting`/`matching`/`dedup_check`) are declared in the schema's CHECK constraint but never
   actually written by any code path — there is no way to derive "the worker is currently in the classification
   step" from data that doesn't exist. Same for VERIFIED as a genuinely distinct state from "AI produced a
   result": nothing in any of the 3 pipelines captures "a human looked at this specific document and confirmed
   it," as opposed to "a review-queue item tied to some low-confidence fields got resolved" (a related but
   narrower fact). **These would require either (a) actually using the already-declared intermediate
   `intake_jobs.status` values the schema already supports — zero migration, pure code change to
   `_process()` to call `claim_next_job`-style intermediate updates between OCR/classify/extract, which is a
   real but bounded implementation option — or (b) a new explicit `verified_at`/`verified_by` column if VERIFIED
   needs to be a first-class case-file concept, which genuinely cannot be derived from existing data.**

3. **Cross-pipeline fragmentation that a single computed view cannot paper over**: the state machine as
   proposed assumes one canonical object flowing through one lifecline. In reality, Pipeline A's
   `predmet_dokumenti` row and Pipeline B's `intake_jobs` row are **two different rows in two different tables
   with no foreign key between them** until Pipeline C's finalize runs (and even then, only `intake_jobs.predmet_id`
   points at the case, never at the specific `predmet_dokumenti` row that resulted — confirmed no
   `intake_job_id` column exists on `predmet_dokumenti`, matching Sprint 001's `INTAKE-003` finding, unchanged).
   A genuinely canonical state machine that covers "one document, one lifecycle, regardless of which pipeline
   it entered through" **cannot be built as a view over the current schema** — it would require either a shared
   `intake_job_id` FK on `predmet_dokumenti` (the exact gap `INTAKE-003` already names) or accepting that
   Pipeline A's synchronous documents simply skip most of the canonical model's early states by design (they
   go from nonexistent to COMPLETED in one HTTP request, which is a legitimate scope, not a bug, for an
   "attach one file to an existing case" action).

### 4.4 Recommendation

**Do not add a new `lifecycle_state` column.** The representational gaps (category 1) are answerable today with
a derived view, consistent with this codebase's established preference (Pricing Matrix, `intake_queue_metrics`,
`events_outbox_metrics`) and consistent with this sprint's own closing instruction to prefer consistency over
new capability. The one category-2 gap worth actually closing — using the already-declared intermediate
`intake_jobs.status` values — is a **code change inside `_process()`**, not a schema change: the column and its
CHECK constraint already exist (migration 073:74-75 already lists `classifying`/`extracting`/`matching`/
`dedup_check`), they are simply never written. That is squarely a "wire up dormant capability" fix, the same
shape as several of Sprint 001's own fixes, and would give real-time visibility into which processing sub-step
a stuck job is in — currently invisible even to an operator looking directly at the `intake_jobs` table.

The one gap this fork will NOT recommend closing without a founder decision: VERIFIED as a first-class state
and the `predmet_dokumenti` ↔ `intake_jobs` FK (`INTAKE-003`). Both are real, both require an actual new column,
and both were already correctly identified and deliberately deferred by Sprint 001 as product/architecture
questions rather than bounded reliability fixes. This fork's transaction-boundary analysis does not change that
calculus — it confirms the gap is real (§4.2/4.3) but doesn't add new urgency beyond what Sprint 001 already
recorded.

The one item this fork adds to the sprint's action list that Sprint 001 did not have: **§3.4's Pipeline C
finalize-marker write is a bounded, mechanically well-precedented fix** (wrap the finalize sequence's
state-completing writes — at minimum, the `intake_jobs.predmet_id` update — in a new RPC modeled directly on
`enqueue_intake_job`'s own idempotency-key pattern, or at minimum wrap just that one line in a try/except that
re-raises with enough context to make the resulting 500 distinguishable from a total failure). This wasn't
flagged by Sprint 001 (whose Failure Recovery Matrix scenario for "duplicate" was framed around re-uploading a
file, not retrying finalize) and is, in this fork's assessment, the single highest-value transactional-integrity
finding in this analysis — narrower in scope than `INTAKE-001`/`INTAKE-002` (both already tracked and
deferred), but describes a failure mode those two tickets don't cover: a full case duplication triggered by the
exact behavior (retry after an error) a lawyer would naturally do.

---

## 5. Files read for this analysis (for traceability)

`docs/architecture/INTAKE_ARCHITECTURE_REPORT.md`, `INTAKE_SOURCE_OF_TRUTH_MATRIX.md`,
`INTAKE_FAILURE_RECOVERY_MATRIX.md`; `api.py:4040-4520` and `4820-4864`; `routers/smart_intake.py` (full file,
769 lines); `shared/intake_worker.py` (full file, 292 lines); `shared/intake_documents.py` (full file, 266
lines); `shared/intake_queue.py` (full file, 218 lines); `migrations/073_intake_foundations.sql` (full file);
`migrations/074_intake_phase1a.sql` (full file); `migrations/016_evidence_vault.sql:1-40`;
`routers/intake.py:210-259`; `routers/onboarding.py:255-291`; `routers/drafting.py:295-329`;
`shared/audit_immutable.py:127-157`; `requirements.txt:10`; installed `pip show supabase postgrest` (both
2.28.3); repo-wide grep for `psycopg2|asyncpg|BEGIN;|begin_transaction|\.transaction\(` (one unrelated hit,
`scripts/export_rls_policies.py`).
