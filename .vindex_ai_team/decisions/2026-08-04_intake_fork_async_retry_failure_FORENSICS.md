# Intake Fork — Async/Retry/Failure-Recovery Forensics

**Mission**: Program Intake, Sprint 001, "Bulletproof Document Intake Foundation." Scope: UPLOAD → OCR →
VALIDATION → STORAGE only. Read-only, no code/git changes. Explicitly does not touch or deeply investigate
Decision Engine/Copilot/Strategy/Firm Brain/Briefing/Dashboard/Search/Alerts/Timeline/Deadlines/Task
Engine/Memory Graph.

**Method**: direct source read of every file in the intake path (`api.py`'s legacy upload endpoint,
`routers/smart_intake.py`, `shared/intake_worker.py`, `shared/intake_queue.py`,
`shared/intake_documents.py`, `services/event_bus.py`, `migrations/073_intake_foundations.sql`,
`migrations/091_event_bus_atomic_claim.sql`, `gunicorn.conf.py`), cross-checked against prior missions'
own decision docs (Phoenix, Keystone, Sentinel, Nexus, Program Alpha/Beta domain inventories, Mission
Olympus governance reviews) so this report does not re-derive what is already proven — it cites and
extends. All line numbers verified against the current file state at investigation time, not quoted from
memory of another report.

---

## 0. Topology — THREE independent "process this document" pipelines, not one

This is the mission's central structural finding: there is no single intake pipeline. There are three,
sharing some infrastructure but each with a materially different failure-recovery story.

| Pipeline | Entry point | Processing model | Durability primitive |
|---|---|---|---|
| **A — Legacy auto-analyze** | `POST /api/predmeti/{predmet_id}/upload` (`api.py:4061`) | Fully synchronous inside the HTTP request: OCR → Pinecone ingest → `predmet_dokumenti` insert, all inline | **None** for the pipeline itself — no job row, no outbox row. Only 3 side-effects are backgrounded, via raw `asyncio.create_task` (fire-and-forget, zero durability): audit log (`api.py:4254`), Evidence auto-classify (`api.py:4269`), Genome refresh (`api.py:4278-4289`) |
| **B — Smart Intake worker** | `POST /api/smart-intake/documents` (`routers/smart_intake.py:92`) | Async: upload → Storage → `intake_jobs` row (202 response) → `IntakeWorker` background loop (`shared/intake_worker.py`) does OCR → classify → extract | `intake_jobs` table (migration 073) — real Postgres-backed queue with atomic claim (`FOR UPDATE SKIP LOCKED`), exponential-backoff retry, dead-letter, and a stale-job reaper |
| **C — Smart Intake finalize** | `POST /api/smart-intake/jobs/{job_id}/finalize` (`routers/smart_intake.py:373`) | Fully synchronous inside the HTTP request: a **second**, independent decrypt+OCR+chunk+Pinecone-ingest+`predmet_dokumenti`-insert pass over the SAME file B's worker already processed once | **None** for this second processing pass — same shape as Pipeline A. Side-effects (conflict-check, Genome refresh, Evidence auto-classify) are the same raw `asyncio.create_task` pattern (`smart_intake.py:564,700,735`) |

Underneath B and C's handlers (and A's `PREDMET_KREIRAN`-adjacent flows elsewhere in the codebase, out of
this mission's scope), a fourth mechanism exists purely as a downstream consumer, not an intake-specific
system: the **Event Bus durable outbox** (`events` table, `services/event_bus.py`) — `intake_jobs`' own
RPCs (`enqueue_intake_job`/`complete_intake_job`/`fail_intake_job`, migration 073) write outbox rows in the
same transaction as the job-status change, and `dispatch_pending_events()` (`services/event_bus.py:436`)
polls and dispatches them every 3s (`DispatchLoop`, `services/event_bus.py:569-612`).

**Net count of independent async/retry mechanisms touching intake**: **4** — (1) Pipeline A's raw
fire-and-forget `asyncio.create_task` (no durability at all), (2) `intake_jobs`' own claim/retry/reap
queue (real durability), (3) the Event Bus's separate claim/retry/dead-letter outbox (real durability, but
architecturally distinct from #2, feeding off events #2's own RPCs also write), (4) Pipeline C's second raw
fire-and-forget `asyncio.create_task` layer for its own side effects. This is exactly the "two independent
job/retry systems for the same underlying concern" pattern the mission brief asked to check for — except
it is worse than two: it is four, three of which have zero relationship to each other's failure/retry
semantics.

---

## 1. Async flow inventory — per-flow crash recoverability

### 1.1 Pipeline A (`api.py:4061` `predmet_upload_auto_analyze`)

| Step | Mechanism | Crash between "started" and "done" |
|---|---|---|
| File read, safety-limit check, OCR (`extract()`) | Inline, synchronous | Request just fails/aborts; nothing was persisted yet — safe, no orphan (`api.py:4113-4141`) |
| Pinecone chunk+ingest (`ingest_session`) | Inline, synchronous | If the process dies here, a vector may already be in Pinecone with **no** corresponding `predmet_dokumenti` row yet — this is the documented, still-open "ghost vector" gap (see §4) |
| `predmet_dokumenti` insert | Inline, synchronous | If this fails (Supabase error, or the process dies before it runs), Sentinel's 2026-08-03 fix (`api.py:4243-4247`) makes the request fail loudly with HTTP 500 rather than silently continuing — confirmed still present, re-verified this pass |
| Audit log / Evidence classify / Genome refresh | `asyncio.create_task` fire-and-forget (`api.py:4254`, `4269`, `4278-4289`) | **Unrecoverable if the process dies between task creation and completion.** No row anywhere records "this was supposed to happen." Same shape as Project Nexus's 2026-08-03 finding for `PREDMET_KREIRAN`'s `emit()` (`.vindex_ai_team/decisions/2026-08-03_nexus_provenance_reliability_audit_INVESTIGATION.md:93`) — new call sites, same defect class, not previously enumerated for these 3 specific tasks in the upload endpoint |

### 1.2 Pipeline B (`routers/smart_intake.py:92` upload, `shared/intake_worker.py` processing)

| Step | Mechanism | Crash recoverability |
|---|---|---|
| Storage upload (`smart_intake.py:129-142`) | Inline, synchronous, precedes job creation | **NEW FINDING (§4.1)**: succeeds-but-enqueue-fails leaves a permanently orphaned encrypted blob, no reference, no cleanup |
| `enqueue_intake_job` RPC (`smart_intake.py:144-156`) | Atomic (job row + audit + outbox event in one transaction, migration 073) | Safe — either the whole transaction lands or none of it does |
| Worker claim (`claim_intake_job` RPC, `FOR UPDATE SKIP LOCKED`) | `shared/intake_queue.py:72-86` | Safe — genuinely atomic, cannot double-claim |
| Worker processing (`_process()`, `shared/intake_worker.py:128-204`) | In-process, no per-step durability | **NEW FINDING (§4.2)**: a crash between document-row creation and function return produces a silently truncated "completed" job |
| Stale-claim recovery | `reap_stale_jobs()`, `shared/intake_queue.py:129-152`, called every 30 ticks (`_DEFAULT_REAP_EVERY_N_TICKS=30`, `intake_worker.py:35`) at `stale_after_s=300` default | Real and working — re-confirmed (also independently confirmed by Phoenix 2026-08-03 as "the single most reliable AI-adjacent subsystem" in this engagement) |
| Dead-letter | `fail_intake_job` RPC, `status='failed'` after `max_attempts` (default 5) | Real — confirmed via migration 073 body |

### 1.3 Pipeline C (`routers/smart_intake.py:373` `finalize_intake_job`)

Same synchronous-inline shape as Pipeline A for the decrypt→OCR→chunk→Pinecone→DB sequence
(`smart_intake.py:588-689`), but with one materially worse property than Pipeline A: **no hard-fail on DB
insert failure**. See §4.3.

### 1.4 Event Bus durable outbox (feeds handlers off both B's and C's side-effects, and A's `emit()`
in-process calls elsewhere in the codebase, out of scope here)

`dispatch_pending_events()` (`services/event_bus.py:436-550`) is genuinely durable for what it dispatches:
retried up to `MAX_DISPATCH_ATTEMPTS=5` (`:422`), dead-lettered with an explicit `"DEAD_LETTER after N
attempts"` marker (`:518-531`) rather than silently marked success — this is Project Phoenix's headline fix
(2026-08-03), re-confirmed correct and unchanged by direct read of the current file (`publish_async()`
correctly propagates handler exceptions via `:364-367`, all 6 registered handlers `raise` after logging).

**But this mechanism is currently exposed to a live multi-worker duplicate-dispatch race** — see §2.

---

## 2. Migration 091 — status and live exposure

`migrations/091_event_bus_atomic_claim.sql` adds `claim_pending_events()` (atomic `SELECT ... FOR UPDATE
SKIP LOCKED` RPC, mirroring migration 073's `claim_intake_job`) specifically because **production runs 4
gunicorn workers by default** (`gunicorn.conf.py:4`, `workers = int(os.getenv("WEB_CONCURRENCY", 4))`), and
**each worker starts its own independent `IntakeWorker` and `DispatchLoop`** inside FastAPI's own startup
hook (`api.py:821-831`, `_start_smart_intake_background_loops`) — confirmed by direct read, not inferred.
Without an atomic claim, 2+ of those 4 independent `DispatchLoop`s can select the same undispatched `events`
row in the same ~3s poll tick and both run non-idempotent handlers (`on_rok_kritican`,
`on_health_score_promenjen`, `on_document_job_failed`, `on_genome_updated` — all unconditionally INSERT on
every call), producing duplicate `proactive_alerts`/`audit_immutable` rows for one real business event.

**Is it live?** `dispatch_pending_events()` (`services/event_bus.py:459-477`) tries the RPC first; on a
"function not found" error (`_is_missing_function_error`, `:425-433`, matching PGRST202/42883) it silently
falls back to the old plain-`SELECT` behavior — i.e. **the code degrades gracefully to the pre-fix, racy
behavior if the migration has not been run**, by explicit design (the migration's own header, verified:
"Per standing project convention: this migration is DRAFTED, NOT applied. The founder runs migrations
himself.").

**This investigation could not directly query production** (read-only, no live DB access) to confirm
whether migration 091 has actually been run. Every other same-day mission that looked at this question
(`.vindex_ai_team/decisions/2026-08-04_alpha_governance_backend_review.md:282`,
`2026-08-04_alpha_governance_reliability_review.md:291`) reports the identical conclusion: **could not
determine from the codebase alone; treated as NOT applied** (matching the migration's own "drafted, not
applied" header and `MISSION_BOARD.md`'s still-open `KEYSTONE-007` item, "Run
`migrations/091_event_bus_atomic_claim.sql` in production" — status `NEEDS_SCOPING — founder action`,
unresolved as of this pass). **This report adopts the same posture: migration 091's fix is treated as
NOT LIVE until the founder confirms otherwise** — meaning the multi-worker duplicate-dispatch race described
above is the current, live, exposed behavior in production, not a theoretical pre-fix state.

A same-day governance review (`alpha_governance_backend_review.md`, F-5) also found a **residual defect
in the post-091 state itself**: `create_proactive_alert()`'s internal blocking retry can push a dispatch
batch's wall-clock time past migration 091's 30-second stale-claim window, re-opening the same race even
after the migration is run — reported fixed in that same mission via a `retry_internally=False` parameter
(confirmed present at `services/event_bus.py:107,183,241`). Not independently re-verified by this
read-only pass (out of this mission's file set), but the citation is accurate to what that report claims.

---

## 3. Retry mechanics summary

| Failure class | Retries? | Backoff | Max attempts | After exhaustion |
|---|---|---|---|---|
| Pipeline B: OCR/classify/extract failure inside `_process()` (any uncaught exception) | Yes, via `intake_jobs` | Exponential, `30s * 2^attempts`, capped at 3600s (`shared/intake_queue.py:28-29,110`) | 5 (default `max_attempts`) | `status='failed'` (dead-letter), a `DocumentJobFailed` outbox event fires, `on_document_job_failed` (`services/event_bus.py:193-248`) creates a `proactive_alerts` row so the lawyer is actually notified — this specific chain is durable end-to-end (job dead-letter → outbox → alert), confirmed by direct read |
| Pipeline B: worker crash mid-job (orphaned claim) | Yes, via `reap_stale_jobs` → same `mark_job_failed` path | Same as above once reaped | Same | Same — reaper feeds the identical retry/dead-letter mechanism, not a separate one |
| Event Bus: handler exception on a durable outbox row | Yes | Fixed 3s poll interval (no exponential backoff — a deliberate choice, not a gap) | 5 (`MAX_DISPATCH_ATTEMPTS`) | Dead-letter with `last_error` tagged `"DEAD_LETTER after N attempts"`, `logger.critical` fires — **but no operator-facing surface** (a human must query the `events` table to notice), a gap already named by Phoenix (2026-08-03) and unchanged |
| Pipeline A/C: OCR failure, Pinecone hard-failure, DB insert failure | **No** | N/A | N/A | Immediate HTTP error to the caller; the lawyer must manually retry the whole upload |
| Pipeline A/C fire-and-forget side-effects (audit/Genome/Evidence-classify/conflict-check) | **No** | N/A | N/A | Silent loss on process death; on a live process, each has its own inner try/except that only logs |

---

## 4. New findings this pass (not previously documented in `.vindex_ai_team/decisions/` or
`docs/architecture/`, confirmed by grep before being asserted as new)

### 4.1 — Orphaned Storage blob on enqueue failure (Pipeline B)

`routers/smart_intake.py:129-156`: the encrypted file is uploaded to the `intake-dokumenti` Storage bucket
**before** `intake_queue.enqueue_job()` is called. If the upload succeeds but the subsequent
`enqueue_intake_job` RPC call throws (transient Postgres/Supabase error, connection drop,
`SECURITY DEFINER` function error, etc. — caught generically at `smart_intake.py:153-156`), the encrypted
blob at `storage_key` (`smart_intake.py:127`, `f"{user['user_id']}/{uuid.uuid4().hex}"`) remains in Storage
**permanently, with zero reference anywhere** — no `intake_jobs` row was ever created to point at it. The
user is told `{"ok": false, "greska": "Greška pri prijemu dokumenta."}` and, if they retry, a **new**
`uuid4()` key is minted (line 127), so a repeatedly-failing enqueue silently accumulates orphaned encrypted
blobs. Grepped the full codebase: **no cleanup job or lifecycle policy references the `intake-dokumenti`
bucket at all** (only the 2 call sites that write/read it, `smart_intake.py:58,131` and
`intake_worker.py:214`). This is a genuine, low-frequency (requires storage-upload-succeeds-then-enqueue-
fails, a narrow window) but real orphaned-resource class, distinct from the already-known Pinecone
ghost-vector gap.

### 4.2 — Silent partial-completion in `IntakeWorker._process()` on crash-mid-processing (Pipeline B)

`shared/intake_worker.py:128-204`. Processing order: `create_document()` (`:176-183`, writes the
`intake_documents` row) → `insert_entities()` (`:184`) → optionally `create_review_queue_entry()` (`:193`,
only if any field is below `AUTO_ACCEPT_THRESHOLD=0.90`) → `write_processing_outcome()` (`:197-200`).

The function's own idempotency guard (`:137-140`):
```python
existing = await intake_documents.get_job_result(job_id)
if existing["document"] is not None:
    logger.info(...)
    return
```
is explicitly designed (per its own docstring, `:128-133`) to prevent a **second** `intake_documents`/
`extracted_entities` row from being written if a retry re-runs a job whose previous attempt already got as
far as writing the document row. It correctly prevents duplication. **It does not distinguish "previous
attempt fully finished, just never called `mark_job_completed`" from "previous attempt crashed 1 line after
`create_document()` returned."** In the second case, the retry's early return skips `insert_entities()`,
`create_review_queue_entry()`, and `write_processing_outcome()` entirely — and because `_process()` returns
without raising, `_tick()` (`:113-116`) immediately calls `intake_queue.mark_job_completed(job_id)`. The
job is marked `status='completed'` — indistinguishable, from the queue's own bookkeeping, from a fully
successful run.

**Concrete consequence**: a document that was correctly classified (the one write that DID land) but whose
extracted entities (parties, court, dates, deadlines, amounts) were never inserted — and, worse, whose
low-confidence fields (the entire reason `intake_review_queue` exists) never reach the review queue,
because that INSERT is skipped by the same early return. No exception, no `last_error`, no `dead_letter`
counter increment, no log line distinguishing this from a clean, complete, high-confidence job. This is a
genuine silent-data-loss / false-success mechanism sitting inside the one subsystem an earlier mission
(Project Phoenix, 2026-08-03) characterized as "the single most reliable AI-adjacent subsystem found this
engagement" — the reaper and retry infrastructure around it are real and correctly re-verified here, but
the thing they retry into has this gap. Grepped all prior `.vindex_ai_team/decisions/` and
`docs/architecture/` files for `get_job_result`/"early exit"/"rani izlaz"/"early return": **zero hits** —
this is not a previously-flagged risk.

**Trigger window**: any process death (redeploy, OOM kill, `gunicorn.conf.py`'s own `max_requests=1000`
worker recycle, host restart) landing after `create_document()` returns but before `_process()`'s own
return — a real, non-trivial fraction of the function's total wall-clock time (OCR is already done by this
point; what remains is classification[already written]+entity extraction+review routing+telemetry, which
for LLM-fallback entity extraction can itself take multiple seconds per field, `shared/intake_extract.py`,
not independently re-verified this pass but consistent with Program Beta's own 2026-08-04 characterization
of the same call).

### 4.3 — Pipeline C (`finalize_intake_job`) has the SAME DB-insert-failure exposure Sentinel fixed in
Pipeline A, but WITHOUT the fix

`api.py`'s Pipeline A hard-fails (HTTP 500) if `predmet_dokumenti` insert fails after a successful Pinecone
ingest — this is Project Sentinel's 2026-08-03 "ghost document" fix, re-confirmed present and correct at
`api.py:4243-4247`.

`routers/smart_intake.py:373`'s `finalize_intake_job` performs the **identical** sequence — Pinecone
ingest (`:627-641`) before a 3-variant `predmet_dokumenti` insert attempt loop (`:674-687`) — but the
entire "Dokument: decrypt → tekst → chunk → Pinecone → predmet_dokumenti" block is wrapped in one broad
`try/except Exception` (`:588-689`) that only logs a warning on any failure, including a total
`predmet_dokumenti` insert failure across all 3 fallback variants. `doc_linked` is correctly computed as
`False` in that case (`:687`) and **is honestly returned** to the caller as `dokument_povezan: false`
(`:768`) — this is not a silent HTTP-200-with-no-signal failure the way the pre-Sentinel Pipeline A bug
was. But unlike Pipeline A, the request as a whole still succeeds (`"ok": true`, a `predmet` row IS
created) — the lawyer's document may have a live orphaned Pinecone vector (same class as Pipeline A's
already-documented, still-open gap) with **no** corresponding database row, inside a predmet that was
otherwise successfully created, and whether the frontend actually reads and surfaces `dokument_povezan` to
the lawyer was **not verified this pass** (frontend code out of this mission's read-only backend scope;
same "contingent on frontend" caveat pattern Phoenix used for the on-demand Briefing `ok` field). This is
the same known defect class (Pinecone-ghost-vector-on-DB-insert-failure) at a **second, previously
unexamined call site** — not a new class of bug, but a real, previously unconfirmed second instance of it
with a materially different response contract (soft warning + honest flag vs. hard 500) than the call site
that has actually been reviewed for it.

---

## 5. Failure-scenario walkthrough (as requested by the mission brief)

| Scenario | Pipeline A (legacy) | Pipeline B (Smart Intake worker) | Pipeline C (finalize) |
|---|---|---|---|
| **Upload interrupted** (client disconnects mid-upload) | Request aborts before any persistence — safe, no orphan | `UploadFile` read fails before Storage upload — safe, no orphan | N/A (no file upload at finalize time — operates on the already-persisted job) |
| **OCR crash / corrupt file** | `extract()` raises inside try/except → clean HTTP error (`api.py:4119-4134`); `DocumentSafetyLimitExceeded` handled explicitly (413) | Fail-soft by design: `is_scanned=True` routes to `document_type='other'`, `confidence=0.0`, review queue — job completes normally, not treated as a retryable error (`intake_worker.py:156-171`) — correct, since the same image will fail identically on retry | Re-runs `extract()` a second time on the same file (`smart_intake.py:601`); an exception here is swallowed by the outer broad `except` (`:688-689`) — `doc_linked=False`, finalize still succeeds |
| **Storage upload crash/timeout** | N/A (Storage is not used for this legacy path — Pinecone is the only external store) | Caught explicitly (`smart_intake.py:139-142`) → clean per-file error in the response array, job never created — safe, no orphan on THIS failure mode | N/A |
| **Storage succeeds, job/DB write fails** | N/A | **§4.1 — new finding**: orphaned encrypted blob, zero reference, zero cleanup | N/A |
| **Worker/process restart mid-OCR** | No worker — a mid-request process restart just aborts the HTTP connection; nothing was persisted yet if before Pinecone ingest, ghost-vector risk if after (§4/known) | Reaper (`reap_stale_jobs`, 300s default) recovers the claim safely; **but §4.2's silent-truncation bug can trigger if the crash landed after `create_document()`** | N/A (finalize doesn't run in a worker loop; a mid-request crash here has the same profile as Pipeline A) |
| **DB insert fails, Pinecone already ingested** | Hard 500 (Sentinel fix, re-confirmed) — user sees honest failure, vector orphaned (known, open) | N/A (worker's `_process()` doesn't touch Pinecone at all — only classify/extract into Postgres) | **§4.3 — soft warning, request still succeeds `"ok": true`**, vector orphaned, `dokument_povezan: false` returned but frontend-surfacing unverified |
| **Pinecone quota/429** | Soft-degrade: `status='sacuvano'` instead of `'indeksirano'`, upload still succeeds (`api.py:4186-4193`) | N/A | Soft-degrade identically (`smart_intake.py:642-644`) |
| **Network timeout mid-Pinecone-call** | Falls into the generic `except Exception` at `api.py:4186-4193`; only 429/storage-full messages are treated as soft-degrade, anything else (including a raw timeout, which won't match those substrings) hard-fails the whole upload (500) | N/A | Any exception soft-degrades (broader catch than Pipeline A — `pe` at `:642-644` catches everything, not just 429/storage-full) |
| **Disk full during tempfile write** | Uncaught `OSError` from `tmp.write(raw)` (`api.py:4116-4118`, inside a bare `try/finally`, not `try/except`) propagates to FastAPI's default 500 handler — consistent (nothing persisted yet), but the error message returned to the lawyer would be a raw exception string, not a clean domain error | Same `OSError` shape in `_process()` (`intake_worker.py:145-147`) — propagates up through `_process()`'s caller, caught by `_tick()`'s own `try/except` (`:113-123`), correctly routed into the normal `mark_job_failed` retry/backoff path — **better-handled here than in Pipeline A**, because it goes through the job's existing retry machinery instead of surfacing as a raw 500 | Same tempfile pattern (`smart_intake.py:597-599`) inside the broad outer `except` — soft-degrades to `doc_linked=False`, same as any other exception in that block |
| **Worker restart while multiple gunicorn workers run** | N/A | **§2 — Event Bus race, live until migration 091 is confirmed run**; `intake_jobs`' own claim (migration 073, always-on since it long predates 091) is unaffected — only the separate `events` outbox dispatch is exposed | Same Event Bus exposure applies to whatever outbox events finalize's own side-effects might indirectly trigger |
| **Full process restart (redeploy) mid-flight** | Any in-flight request is simply lost from the HTTP client's perspective (connection reset); whatever had already been durably written (DB rows) survives, anything only in the 3 fire-and-forget tasks does not | `intake_jobs` rows survive (Postgres), reaper recovers orphaned claims after `stale_after_s` — but see §4.2 for what "recovers" can silently mean | Same profile as Pipeline A — nothing about finalize's own work survives a mid-request restart beyond whatever had already committed to Postgres/Pinecone |

---

## 6. Summary for parent

**Independent async/retry mechanisms found**: **4** — Pipeline A's raw fire-and-forget `asyncio.create_task`
(zero durability), the `intake_jobs` Postgres-backed queue (real claim/retry/reap/dead-letter, migration
073, genuinely robust — re-confirmed, matches Phoenix's prior characterization), the Event Bus durable
outbox (`events` table, real retry/dead-letter since Phoenix's 2026-08-03 fix, but exposed to a live
multi-worker duplicate-dispatch race), and Pipeline C's own second raw fire-and-forget layer duplicating
Pipeline A's pattern at a different call site. These four do not coordinate with each other in any way —
a document processed through Pipeline B/C can be duplicated by the Event Bus race while Pipeline A's
equivalent flow has no such protection to even need, because it has no durable row at all for the
processing step itself.

**Migration 091 status**: **treated as NOT LIVE in production.** Its own file header says "DRAFTED, NOT
applied — the founder runs migrations himself"; `MISSION_BOARD.md`'s `KEYSTONE-007` item requesting it be
run is still open (`NEEDS_SCOPING — founder action`); two independent same-day governance reviews
(2026-08-04) explicitly state they could not confirm it from the codebase and treated it as unapplied. This
investigation reached the identical conclusion independently and adopts the same posture. Until run, the
code's own designed fallback (`services/event_bus.py:459-477`) means the pre-fix, racy plain-`SELECT`
dispatch behavior is what actually executes in production today, every 3 seconds, on all 4 gunicorn
workers.

**Single most severe failure-recovery gap found this pass**: **§4.2 — `IntakeWorker._process()`'s
idempotency early-return silently truncates a retried job after a crash landing between document-creation
and function-return**, marking it `status='completed'` with zero extracted entities and zero review-queue
escalation, indistinguishable from a genuinely clean run, with no error, log line, or dead-letter trace
anywhere. This is more severe than the already-known, already-documented Pinecone ghost-vector gap (which
at least leaves an honest failure signal in Pipeline A, or a correctly-flagged `dokument_povezan: false` in
Pipeline C) because it produces a **false positive** — a job that reports itself as fully, successfully
processed while having silently dropped the majority of its actual output — inside the specific subsystem
this codebase's own prior missions have repeatedly relied on as the reliability benchmark for the rest of
intake.
