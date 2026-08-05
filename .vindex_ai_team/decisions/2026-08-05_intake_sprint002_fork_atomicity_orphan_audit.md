# Program Intake Sprint 002 — Fork A: Atomicity & Consistency Audit

**Date:** 2026-08-05
**Scope:** Read-only investigation. No code changed. Builds on Sprint 001
(2026-08-04)'s pipeline map — see `docs/architecture/INTAKE_ARCHITECTURE_REPORT.md`,
`INTAKE_FAILURE_RECOVERY_MATRIX.md`, and the 3 raw fork reports in this directory
dated 2026-08-04.

**Verdict key:** ✅ ORPHAN-SAFE (cites the mechanism) · 🔴 CONFIRMED DEFECT (new) ·
🟡 ALREADY KNOWN (matches Sprint 001's INTAKE-001/002) · ⬜ N/A (structurally
doesn't apply to this pipeline)

---

## Summary table

| # | Artifact type | Pipeline A (api.py sync upload) | Pipeline B (smart_intake upload + worker) | Pipeline C (finalize) | Event Bus |
|---|---|---|---|---|---|
| 1 | Ghost/orphan DB record | 🟡 known-shape, see §A1 (blob-orphan sibling, not a DB-row FK ghost) | 🔴 **NEW**: "completed" job with silently-missing `intake_processing_outcomes` row (§B1) | ✅ FK-protected (§C1); but see duplicate-row risk in §C-bonus | ⬜ (events don't reference intake sub-tables by FK) |
| 2 | Orphan blob | 🔴 **NEW DEFECT** — wider exposure than INTAKE-002, no queue to ever reference it (§A2) | 🟡 ALREADY KNOWN = INTAKE-002, confirmed still accurate (§B2) | ⬜ reuses B's blob, uploads nothing new | ⬜ |
| 3 | Orphan vector | 🔴 **CONFIRMED DEFECT**, self-documented in code, no rollback (§A3) | ⬜ worker never touches Pinecone | 🟡 ALREADY KNOWN = INTAKE-001, confirmed still accurate (§C3) | ⬜ |
| 4 | Orphan audit | ✅ guarded by `if _dok_id:` using the real inserted id, no staleness path (§A4) | ✅ FK-protected `intake_audit_log.intake_job_id` (§B4) | ✅ `log_action`/`_track_event` always fire with a real, already-committed `predmet_id` (§C4) | 🟡 ALREADY KNOWN = KEYSTONE-007 duplicate-alert risk, not a ghost reference (§EB4) |
| 5 | Orphan provenance | ✅ Sentinel hard-fail guarantees `_dok_id` non-None before `case_context()` runs (§A5) | ⬜ no `case_context()` used at all — structurally can't be stale (document doesn't exist yet at classify-time) (§B5) | ✅ same guard pattern as A, `dokument_id` always real when used (§C5) | ⬜ (Genome handler out of sprint scope) |
| 6 | Orphan queue job | ⬜ no queue in this pipeline | ✅ reap → retry → dead-letter chain is complete and terminal (§B6); narrow race noted, not a defect (§B6-race) | ⬜ doesn't own job lifecycle beyond one field | ✅ `MAX_DISPATCH_ATTEMPTS` dead-letters into terminal `dispatched_at` (§EB6) |
| 7 | Ghost case/document combo | ⬜ never creates a `predmet`, only attaches to a pre-validated existing one | ⬜ never creates/attaches a `predmet` | ✅ FK-protected, cannot exist (§C7); but see **new duplicate-predmet defect**, different shape, in §C-bonus | ⬜ |

**Two new findings beyond the 7 categories, both material:**
- **§B1** — a swallowed exception can leave a `intake_jobs.status='completed'` job with entities/document written but **no** `intake_processing_outcomes` row, permanently, with no retry path back to it. This is the exact bug shape Sprint 001 fixed, reintroduced through a different door.
- **§C-bonus** — Pipeline C's finalize idempotency guard (`intake_jobs.predmet_id`) is written **last**, unprotected by try/except, after every other write has already committed. A failure on that single last write causes a **duplicate predmet** (with duplicate client link, rok, document, vector) on retry, not an orphan — the opposite failure mode, but equally an atomicity violation Sprint 002's charter should care about.

---

## Pipeline A — `api.py:4063 predmet_upload_auto_analyze` (synchronous)

### §A1 — Ghost/orphan DB record
Not applicable in the strict "FK points at nothing" sense: `predmet_dokumenti.predmet_id`
and `.user_id` are both `NOT NULL REFERENCES ... ON DELETE CASCADE`
(`supabase_setup.sql:336-346`), so Postgres itself refuses any insert whose
`predmet_id` doesn't exist. The predmet is validated to exist by an explicit
`.single()` fetch at the very top of the handler (`api.py:4091-4093`) before
anything else runs, so this table can never hold a row pointing at nothing.
Verdict: ✅ ORPHAN-SAFE for the DB-row shape. The real defect in this pipeline
is the **blob**, not the row — see §A2.

### §A2 — Orphan blob — 🔴 CONFIRMED DEFECT (new, sibling of INTAKE-002)
Read `api.py:4113-4267` directly, per the brief. Order of operations:

1. `api.py:4132-4139` — encrypt + upload the **original file** to
   `intake-dokumenti` bucket, storage key `{user.id}/{predmet_id}/{uuid}{suffix}`.
   Comment at `api.py:4113-4126` explicitly frames this as Sprint 001's new
   best-effort addition, "if it fails, don't block the rest of the flow."
2. `api.py:4143-4171` — OCR/extract. **Three** distinct raise sites here:
   `DocumentSafetyLimitExceeded` → 413 (`4151-4159`), `is_scanned` → 422
   (`4160-4164`), empty text → 422 (`4170-4171`).
3. `api.py:4188-4223` — chunk + Pinecone ingest. One more raise site:
   non-storage/429 exception → 500 (`4216-4223`).
4. `api.py:4228-4267` — `predmet_dokumenti` insert (try/except, sets `_dok_id`
   or leaves it `None` on failure — swallowed, not re-raised).
5. `api.py:4279-4283` — Project Sentinel hard-fail: `if not _dok_id: raise
   HTTPException(500, ...)`.

**The defect:** if the storage upload at step 1 succeeds (`_original_storage_path`
set), and *any* of the five raise sites in steps 2-5 fires, the function exits
via `HTTPException` with the encrypted blob already sitting in
`intake-dokumenti` — and **nothing in this pipeline ever references that
storage key again**. Unlike Pipeline B's INTAKE-002 (where at least an
`intake_jobs` row might exist to eventually be inspected/reaped), Pipeline A
has **no queue, no job row, no tracking mechanism of any kind** for this
storage key outside the one local Python variable that dies with the
request. This is a strictly wider exposure window than INTAKE-002 (5 raise
sites instead of 1 RPC call) with a weaker safety net (zero infrastructure vs.
at least a job row). The client does get an honest HTTP error in all 5 cases
(413/422/500), so the user isn't lied to about the request's outcome — but
the blob orphan itself is invisible to everyone, forever. No cleanup job
exists anywhere in the repo that scans `intake-dokumenti` for unreferenced
keys.

Recommend tracking this as a new backlog item (suggest `INTAKE-004`) — same
root shape as `INTAKE-002`, worse blast radius.

### §A3 — Orphan vector — 🔴 CONFIRMED DEFECT (self-documented in code)
Pinecone ingest (`api.py:4198-4223`) happens **before** the `predmet_dokumenti`
insert (`4228-4267`) and Sentinel's hard-fail check (`4279-4283`). The
in-code comment at `api.py:4269-4278` states this explicitly and is worth
quoting verbatim as the authoritative acknowledgment: *"Pinecone vektor
ostaje (best-effort cleanup nije implementiran ovde — vidi
SENTINEL_PRE_BETA_CRITICAL_PATH.md)"* — i.e., the author who wrote Project
Sentinel already knew and accepted this gap. Verified: there is no
Pinecone-side delete/rollback call anywhere in this function, and no
background reconciliation job in the repo that diffs Pinecone against
`predmet_dokumenti`. The window is real: Pinecone `ingest_session()` succeeds
→ `predmet_dokumenti` insert throws (network blip, RLS surprise, whatever) →
`_dok_id` stays `None` → Sentinel raises 500 → the vector is permanently
indexed under the **persistent, shared owner namespace** (`_owner_ns`, e.g.
`kancelarija_{id}` or `user_{id}` — not a throwaway per-session namespace),
where it will keep surfacing in that office's future RAG retrievals with
`predmet_id` metadata pointing at a document nobody in the UI can ever see,
forever. This is architecturally the same shape as `INTAKE-001` (Pipeline C)
but occurring earlier/more directly (Pinecone-then-DB order, not
DB-then-second-independent-Pinecone-pass), and it's the one Sprint 001 itself
flagged as a known limitation, not a fresh discovery — but the brief asked
specifically whether it's still real and unmitigated: confirmed, yes.

### §A4 — Orphan audit — ✅ ORPHAN-SAFE
`api.py:4287-4299`: the `log_action("dokument_upload", ..., resource_id=_dok_id,
...)` fire-and-forget task is wrapped in `if _dok_id:` and this code is only
reachable *after* Sentinel's hard-fail check has already passed (i.e., control
flow cannot reach line 4287 with `_dok_id=None` — the function would have
raised at line 4280 first). `_dok_id` itself is assigned exactly once, from
`_ins.data[0]["id"]` (`api.py:4265`), the real value Postgres returned for the
row that was just committed — there is no code path that reassigns it to a
stale or synthetic value afterward. The `asyncio.create_task` firing
unawaited is a general "did the event loop get to run it before shutdown"
risk shared by every fire-and-forget task in this codebase, not something
specific to this audit call, and out of this fork's scope.

### §A5 — Orphan provenance — ✅ ORPHAN-SAFE
`shared/ai_provenance.py::case_context(predmet_id=predmet_id,
document_id=_dok_id, ...)` is opened at `api.py:4513`, which is textually and
causally **after** Sentinel's hard-fail block (`4279-4283`). Since that block
unconditionally raises when `_dok_id` is `None`, and FastAPI unwinds the
function on that exception, there is no execution path that reaches line
4513 with a `None`/stale `_dok_id` — the brief's hypothesized "could `_dok_id`
be somehow stale" doesn't materialize because the single assignment site
(`4265`) and the single guard site (`4280`) are the only two places that
touch the variable before it's consumed. `case_context` itself
(`shared/ai_provenance.py:76-111`) is a plain contextvar scope with restore-on-exit
— it doesn't persist or dereference anything on its own; the actual
persistence happens in `security/ai_forensics.py` (not read in depth, out of
this fork's declared scope, but the input it receives here is proven sound).

### Pipeline A — category 6/7
⬜ N/A — no queue infrastructure in this endpoint at all (fully synchronous,
in-request); and it never creates a `predmet` row, only attaches a document to
one already validated to exist via the `.single()` fetch at the top
(`api.py:4091-4093`), so category 7's "case rolled back mid-multi-insert"
shape cannot occur here.

---

## Pipeline B — `routers/smart_intake.py:92` upload + `shared/intake_worker.py` `_process()`

### §B1 — Ghost/orphan DB record — 🔴 CONFIRMED DEFECT (new)
All four Phase 1A tables are FK-protected against classic "points at nothing"
ghosts: `intake_documents.intake_job_id`, `extracted_entities.document_id`,
`intake_review_queue.intake_job_id`/`document_id`, and
`intake_processing_outcomes.intake_job_id` are all
`NOT NULL REFERENCES ...` (migration `074_intake_phase1a.sql:43,70,97-98,121`),
and every write in `_process()` (`shared/intake_worker.py:185-221`) supplies
an id obtained from a prior successful insert in the same call — so a literal
"references something nonexistent" ghost cannot happen via this code path.

The real defect is subtler and matches the shape the brief asked me to be
skeptical about. `write_processing_outcome()`
(`shared/intake_documents.py:96-140`) is the **one** step in the entire
Sprint-001-hardened idempotency design that is wrapped in its own
try/except and **swallows** the exception (`shared/intake_documents.py:139-140`,
logs a warning, does not re-raise). Everywhere else in `_process()`
(`create_document`, `insert_entities`, `create_review_queue_entry`), an
exception propagates naturally up through `_process()` → `_tick()`'s except
block (`shared/intake_worker.py:117-123`) → `mark_job_failed()` → retry →
`has_processing_outcome()` correctly detects the incomplete state on the next
attempt and calls `delete_partial_document()` to clean up and reprocess from
scratch. That is exactly Sprint 001's fix, and it works for every failure
site **except this one**.

If the `intake_processing_outcomes` insert itself throws (DB blip, RLS
surprise, connection drop — the same class of transient failure the rest of
the design defends against), the exception dies inside
`write_processing_outcome()`'s own try/except, `_process()` returns
**normally**, and `_tick()` (`shared/intake_worker.py:113-116`)
unconditionally calls `mark_job_completed(job_id)` — moving the job to the
terminal `status='completed'` state. From that point on:
- `claim_next_job()` only claims from `status='received'` — this job is
  never reclaimed.
- `reap_stale_jobs()` only scans non-terminal statuses — `'completed'` is
  excluded.
- `has_processing_outcome()`, the function Sprint 001 built specifically to
  detect this exact situation, would correctly return `False` for this job —
  but nothing ever calls it again, because nothing ever revisits a
  `'completed'` job.

Net effect: a job with a real `intake_documents` row and real
`extracted_entities` rows (not ghosts — every FK is valid), permanently
marked `completed`, that never got its `intake_processing_outcomes` row —
silently indistinguishable from full success to anyone reading
`intake_jobs.status`, and permanently invisible to the one function built to
catch exactly this. This is the same failure *shape* Program Intake Sprint
001 closed out as its headline fix (crash before the outcome write → false
success), reappearing through a different door (the outcome write itself
failing, rather than a crash before it's attempted). Recommend tracking as a
new backlog item (suggest `INTAKE-005`): either stop swallowing the exception
in `write_processing_outcome()` (let it propagate so `_tick()`'s existing
retry path handles it — it already knows what to do), or have `_tick()`
independently re-verify `has_processing_outcome()` before calling
`mark_job_completed()`.

### §B2 — Orphan blob — 🟡 ALREADY KNOWN = INTAKE-002, reconfirmed accurate
`routers/smart_intake.py:129-156`: storage upload (`129-142`) happens, then
`intake_queue.enqueue_job()` (`144-156`) is called; if the RPC throws, the
exception is caught, logged, and appended to the per-file `results` list as
`ok: False` — but the already-uploaded encrypted blob is never deleted and no
`intake_jobs` row was ever created to reference it. Re-read and reconfirmed:
this is exactly Sprint 001's `INTAKE-002` description, unchanged. One nuance
worth recording: the client-facing response for this specific file *does*
say `ok: False` (unlike the ghost paths elsewhere), so the lawyer is not
told the upload succeeded — but the orphaned ciphertext still sits in the
bucket forever, discoverable only by a bucket-vs-`intake_jobs` reconciliation
job that does not exist today.

### §B3 — Orphan vector
⬜ N/A. `_process()` (`shared/intake_worker.py:128-225`) never imports or
calls anything from `uploaded_doc/ingest.py` or touches Pinecone — Phase 1A
is deliberately classification/extraction only (per the module's own
docstring, `shared/intake_worker.py:10-15`, and migration 074's framing that
Phase 1A "ostavlja dokument nepovezan sa predmet_id"). Pinecone indexing for
Smart-Intake-originated documents only happens later, in Pipeline C's
finalize step (§C3).

### §B4 — Orphan audit — ✅ ORPHAN-SAFE
`intake_audit_log.intake_job_id` is `NOT NULL REFERENCES public.intake_jobs(id)`
(migration `073_intake_foundations.sql:119`). Every write to this table goes
through the four atomic RPCs (`enqueue_intake_job`, `claim_intake_job`
[implicitly via its own audit rows — actually only enqueue/complete/fail
write audit rows, claim does not], `complete_intake_job`, `fail_intake_job`),
each of which inserts the audit row in the **same transaction** as the
`intake_jobs` row it describes (migration `073`, functions at lines
145-178, 230-247, 260-292). A ghost audit row referencing a nonexistent job
is therefore not just unlikely but transactionally impossible — the audit
insert and the job insert/update either both commit or both roll back
together.

### §B5 — Orphan provenance
⬜ N/A, and safely so. Neither `shared/intake_classify.py` nor
`shared/intake_extract.py` nor `shared/intake_worker.py` import
`shared.ai_provenance.case_context` at all (confirmed via repo-wide grep —
only 18 files use it and none are in this pipeline). This isn't an oversight
worth flagging as a gap: at the time these LLM calls run (`_classify`,
`_extract_entities`, `shared/intake_worker.py:271-278`), no
`intake_documents` row exists yet — `create_document()` is called *after*
classification returns (`shared/intake_worker.py:197-204`). There is
structurally no valid `document_id` to attach at call time, so the absence of
`case_context()` here cannot produce a stale/orphan reference — it simply
means these specific AI calls carry no case-level provenance today, which is
a Phase-1A scope gap (mentioned only for completeness), not an atomicity
defect.

### §B6 — Orphan queue job — ✅ ORPHAN-SAFE, with one noted race (not a confirmed defect)
Traced the full lifecycle: `enqueue_intake_job` → `received` → `claim_intake_job`
→ `preprocessing` → (`_process()` runs) → either `mark_job_completed` →
`completed`, or (on exception) `mark_job_failed` → `fail_intake_job` RPC
(migration `073:260-292`) which either reschedules (`status='received'`,
`next_retry_at` set, `claimed_at` cleared) or, once
`new_attempts >= max_attempts` (default 5), sets `status='failed'` — a
genuine terminal dead-letter state, with its own audit row and outbox event.
Separately, `reap_stale_jobs()` (`shared/intake_queue.py:129-152`) catches
jobs stuck in any non-terminal in-progress status
(`preprocessing/classifying/extracting/matching/dedup_check`) whose
`claimed_at` is older than 300s and routes them through the exact same
`mark_job_failed` path — so a worker that crashes mid-`_process()` cannot
leave a job stuck forever; it always eventually reaches either `received`
(retry) or `failed` (dead-letter), and dead-letter is reachable within
`max_attempts` cycles. **No infinite non-terminal loop is possible** given
this design. Verdict: ✅ ORPHAN-SAFE.

One structural race is worth recording as an open question, not a confirmed
defect (I did not observe it happen, only that nothing prevents it): the
300s stale threshold is a fixed wall-clock guess, and `_process()`'s
classify/extract steps do call OpenAI with their own internal
retry/backoff (`shared/intake_classify.py:28`, `shared/intake_extract.py:32`,
mentioning "backoff-om za rate-limit/5xx/timeout/connection greške"). If a
worker is genuinely still alive and legitimately mid-retry past the 300s
mark (not crashed), `reap_stale_jobs()` cannot distinguish "crashed" from
"slow" — it will reset the job to `received`, a second worker can then
`claim_next_job` and reprocess it concurrently with the still-running
original. `intake_documents` has no unique constraint on `intake_job_id`
(migration `074:41-55` — only a non-unique index at line 60), so this could
in theory produce two `intake_documents` rows for one job. This is the same
category of "premature reap vs. genuinely-slow-not-dead worker" risk that is
generically inherent to any claimed_at-based reaper design, not something
this codebase does distinctively wrong — flagging for awareness, not as a
confirmed defect, since I have no evidence it has actually fired.

### Pipeline B — category 7
⬜ N/A — this pipeline never creates or references a `predmet` row at all;
Phase 1A leaves documents deliberately unlinked from any case (migration
074's own stated design boundary).

---

## Pipeline C — `routers/smart_intake.py:373 finalize_intake_job` (synchronous)

### §C1 — Ghost/orphan DB record — ✅ ORPHAN-SAFE (for the "points at nothing" shape)
Same FK as §A1: `predmet_dokumenti.predmet_id NOT NULL REFERENCES
public.predmeti(id) ON DELETE CASCADE` (`supabase_setup.sql:338`). The
`predmet` row is either freshly inserted with a checked non-empty result
(`smart_intake.py:468-479`, raises 500 on failure before `predmet_id` is ever
used) or fetched-and-verified-existing in the attach-to-existing branch
(`432-441`, 404s if not found before `predmet_id` is used). Either way,
`predmet_id` is guaranteed valid by the time the 3-variant fallback insert
loop (`675-687`) runs. Verdict: ✅ ORPHAN-SAFE for this specific shape. See
§C-bonus below for a different, real atomicity problem in this same
function.

### §C2 — Orphan blob
⬜ N/A as a *new* risk here — this endpoint does not upload anything new to
`intake-dokumenti`; it downloads and decrypts the blob Pipeline B already
wrote (`smart_intake.py:595`, reusing
`shared.intake_worker.worker._download_and_decrypt`). If that blob doesn't
exist (e.g., because it was already an INTAKE-002 orphan, or for any other
reason), the outer try/except at `588-689` catches the failure, logs it, and
`doc_linked` stays `False` — this is the known, already-documented
`INTAKE-001` degraded-but-non-crashing path, not a new orphan-producing
action.

### §C3 — Orphan vector — 🟡 ALREADY KNOWN = INTAKE-001, reconfirmed accurate
Reread `smart_intake.py:586-689` end to end. Confirmed Sprint 001's
description is accurate: Pinecone ingest (`626-644`) happens, then a
**3-variant fallback insert loop** into `predmet_dokumenti`
(`674-687`) is attempted; if Pinecone succeeded but *all three* insert
variants throw, `dok_ins` stays `None`, `doc_linked = bool(dok_ins and
dok_ins.data)` correctly evaluates `False` (honest signal, no lie there) —
but the whole `dokument link/ingest` block is wrapped in one outer
try/except (`588...689`) that swallows this as non-fatal, and the function
continues on to write `intake_jobs.predmet_id` and return `{"ok": True, ...}`
regardless. The already-committed `predmet` (and possibly client/rok) makes
the overall response correctly `"ok": true` from the *case-creation*
perspective, but the Pinecone vector is now a ghost under the same
persistent `_owner_ns` namespace description as §A3 — no rollback, no
tracking, confirmed still real and unmitigated as of this read.

### §C4 — Orphan audit — ✅ ORPHAN-SAFE
Two audit-adjacent writes in this function: the analytics `_track_event`
fire-and-forget task (`smart_intake.py:741-757`) and the conflict-check
proactive alert (`smart_intake.py:546-564`). Both execute using `predmet_id`
that was resolved and validated earlier in the function (either freshly
inserted with a checked result, or fetched-and-verified) — there is no code
path in this function that reaches either of these blocks with an unset or
stale `predmet_id`, since both are lexically after the predmet
creation/attach block (`429-479`) which would have already raised on
failure.

### §C5 — Orphan provenance — ✅ ORPHAN-SAFE
The Evidence Vault background classify task (`_evidence_classify_bg`,
`smart_intake.py:725-735`) reads `dokument_id = dok_ins.data[0]["id"]`
directly inside the task closure — and this task is only ever scheduled
inside `if doc_linked:` (`smart_intake.py:692`), which is only `True` when
`dok_ins.data` was non-empty. So by construction, the `dokument_id` passed
into `klasifikuj_i_sacuvaj` here is always a real, already-committed row id;
there's no path where this fires with a `None`/stale id.

### §C6
⬜ N/A — this endpoint reads `intake_jobs.status` (must already be
`'completed'`, checked at `smart_intake.py:403-404`) but doesn't drive the
job through the classify/extract state machine itself; the only job-table
write it performs is stamping `predmet_id` at the very end
(`737-739`), which is unconditional metadata, not a status transition.

### §C7 — Ghost case/document combination — ✅ ORPHAN-SAFE for the literal shape asked about
Same FK argument as §C1 — a `predmet_dokumenti` row cannot reference a
non-committed/rolled-back `predmet`, full stop, regardless of which endpoint
writes it. But see the next section for a **different**, real defect this
investigation turned up in the same code region.

### §C-bonus — 🔴 CONFIRMED DEFECT (new): non-atomic finalize, idempotency marker written last, unprotected
This doesn't fit neatly into any of the 7 named categories (it produces a
**duplicate real case**, not a ghost/orphan), but it's a direct atomicity
violation in exactly the code this fork was asked to audit, so it belongs in
this report.

`finalize_intake_job`'s *only* re-entry guard is at the top:
`smart_intake.py:400-401` — `if job.get("predmet_id"): return {"ok": True,
"predmet_id": job["predmet_id"], "already_finalized": True}`. That field is
written **exactly once**, at `smart_intake.py:737-739`:
```python
await asyncio.to_thread(
    lambda: supa.table("intake_jobs").update({"predmet_id": predmet_id}).eq("id", job_id).execute()
)
```
This call is the **last** state-changing line in the function (only
best-effort analytics tracking follows it), and — unlike literally every
other write in this function — it is **not** wrapped in a try/except. By
this point the function has already, as separate, already-committed REST
calls (this is Supabase/PostgREST, not a single DB transaction spanning the
whole endpoint):
- inserted a new `predmeti` row (or attached to an existing one),
- possibly inserted/linked a `klijenti` row,
- possibly inserted a `predmet_hronologija` (rok) row,
- possibly inserted a `predmet_dokumenti` row and a Pinecone vector,
- scheduled two background tasks (genome refresh, evidence classify).

If the final `intake_jobs` update throws (transient DB error, timeout,
connection drop — the same ordinary transient-failure class this whole audit
has been probing), the function raises unhandled and FastAPI returns a 500
to the lawyer. **But the case was already fully created.** The lawyer, seeing
a failure, has every reason to retry the finalize call. On retry:
`job.get("predmet_id")` is still empty (that's exactly what failed to
write), so the idempotency guard at line 400 does **not** fire, and the
entire function runs again from scratch — inserting a **second** `predmeti`
row (the `naziv`/`opis` generation logic at `444-479` has no dedup check
against "did I already make one of these for this job"), a second rok entry,
a second `predmet_dokumenti` row, and a second Pinecone vector. The client
lookup at `486-497` does dedupe by `ilike("ime", ...)` so a duplicate
*client* is avoided, but the **case itself** duplicates.

This is the mirror image of `INTAKE-001`/`INTAKE-002`: instead of a resource
existing with nothing pointing at it, here a real, fully-formed, user-visible
case gets silently duplicated because the one field used to detect
"already done" is the least-protected write in the whole call chain. Given
this function's own docstring explicitly claims "Idempotentno: ako je posao
vec finalizovan ... vraca postojeci predmet umesto da pravi duplikat"
(`smart_intake.py:381-384`), this is a real gap between that stated guarantee
and what the code actually does under a late transient failure. Recommend
tracking as a new backlog item (suggest `INTAKE-006`) — the fix shape is
straightforward (write `intake_jobs.predmet_id` earlier / atomically with the
`predmeti` insert, or wrap the final update so a failure there is treated as
non-fatal to the already-returned result rather than as grounds for client
retry) but implementing it is out of this fork's read-only scope.

---

## Event Bus (`services/event_bus.py`, migration 091 drafted-not-run)

Scope note: only the two event types genuinely fired by the intake pipelines
(`DocumentJobFailed`, and the enqueue/complete events which have zero
subscribed handlers today — confirmed via `_register_defaults`,
`services/event_bus.py:308-314`, which only subscribes
`DOCUMENT_JOB_FAILED` among the three `DOCUMENT_JOB_*` types; `ENQUEUED` and
`COMPLETED` events are written to the outbox and marked dispatched with no
handler ever running, i.e. inert by design today, not orphaned — they simply
have no consumer) were investigated. Genome-related handlers
(`on_genome_updated`) were noted but not investigated further per the
sprint's explicit "don't deep-dive Genome" boundary.

### §EB4 — Orphan audit — 🟡 ALREADY KNOWN = KEYSTONE-007, confirmed real for intake specifically
`on_document_job_failed` (`services/event_bus.py:193-248`) resolves
`job.uploaded_by`/`predmet_id` from a **fresh read** of the real
`intake_jobs` row (`208-214`) at handler-execution time, then unconditionally
`INSERT`s a new `proactive_alerts` row (via `create_proactive_alert`,
non-idempotent by design per the comment at
`services/event_bus.py:16-18`/migration 091's own framing). Since migration
091 (atomic `claim_pending_events`) is confirmed drafted-but-not-run
(per Sprint 002's own context and `_is_missing_function_error` fallback path
at `services/event_bus.py:425-433`, `459-477`), the pre-existing plain-SELECT
dispatch is what's live, and — with the documented 4-gunicorn-worker setup —
two workers can genuinely both pick up the same `DocumentJobFailed` row in
one 3s tick and both fire this handler, producing two `proactive_alerts`
rows for one real, still-existing failed job. This is not an "orphan" in
the strict sense (the `job_id`/`predmet_id` referenced are real and still
exist) — it's a duplicate, not a ghost — so it's recorded here for
completeness rather than as a new category-4 finding. Matches `KEYSTONE-007`
exactly; confirmed the intake-specific instance of it is real and live.

### §EB6 — Orphan queue job (applied to the `events` outbox itself) — ✅ ORPHAN-SAFE
`dispatch_pending_events()` (`services/event_bus.py:436-550`) has a genuine
terminal dead-letter path: `MAX_DISPATCH_ATTEMPTS = 5`
(`services/event_bus.py:422`); once `attempts >= MAX_DISPATCH_ATTEMPTS`, the
row is stamped `dispatched_at` (terminal — the poller's own claim query
filters on `dispatched_at IS NULL`) with `last_error` prefixed
`"DEAD_LETTER after N attempts: ..."` (`508-531`) — a row can never spin
forever; it always reaches a terminal, provably-marked state within 5
attempts. Verdict: ✅ ORPHAN-SAFE.

### §EB1/§EB2/§EB3/§EB5/§EB7
⬜ N/A — the Event Bus doesn't create, delete, or reference `predmet_dokumenti`/
`intake_documents`/storage blobs/Pinecone vectors/`predmet` rows directly
for any intake-related event; its only intake-adjacent side effect is the
`proactive_alerts` write covered in §EB4.

---

## Consolidated new-finding list (for whoever triages Sprint 002's backlog)

| Suggested ID | One-line | Location | Severity shape |
|---|---|---|---|
| INTAKE-004 (new, sibling of 002) | Pipeline A orphans the just-uploaded encrypted original in `intake-dokumenti` on any of 5 distinct post-upload failure paths, with zero tracking infrastructure (worse than INTAKE-002, which at least has a job row) | `api.py:4113-4283` | Orphan blob, silent, permanent |
| INTAKE-005 (new) | A job can reach terminal `status='completed'` with real `intake_documents`/`extracted_entities` rows but a missing `intake_processing_outcomes` row, because `write_processing_outcome()` swallows its own exception instead of letting `_tick()`'s existing retry machinery handle it | `shared/intake_documents.py:96-140`, `shared/intake_worker.py:113-116` | Reintroduces Sprint 001's headline bug shape through a different door |
| INTAKE-006 (new) | `finalize_intake_job`'s idempotency marker (`intake_jobs.predmet_id`) is the least-protected write in the function — a transient failure on that one line, after everything else already committed, produces a full duplicate case on client retry, contradicting the function's own idempotency claim in its docstring | `routers/smart_intake.py:400-401`, `737-739` | Duplicate real resource, not an orphan — opposite failure mode |

**Reconfirmed as accurate, unchanged:** `INTAKE-001` (Pipeline C ghost
vector on 3-variant insert exhaustion, §C3), `INTAKE-002` (Pipeline B orphan
blob on enqueue RPC failure, §B2), `KEYSTONE-007` (Event Bus multi-worker
duplicate dispatch, intake-specific instance confirmed live at §EB4).

**No fixes were implemented.** This fork is read-only per its charter.
