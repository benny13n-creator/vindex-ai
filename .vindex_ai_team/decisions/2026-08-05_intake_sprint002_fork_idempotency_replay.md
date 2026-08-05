# Program Intake Sprint 002 — Fork C: Idempotency Audit & Production Replay

**Date:** 2026-08-05
**Lens:** Reliability & Failure Recovery Engineer + Evidence & Consistency Auditor
**Scope:** Read-only investigation. No code changed. Builds on Sprint 001 (2026-08-04)'s
`INTAKE_ARCHITECTURE_REPORT.md`, `INTAKE_SOURCE_OF_TRUTH_MATRIX.md`, `INTAKE_FAILURE_RECOVERY_MATRIX.md`,
and this sprint's own Fork A (`2026-08-05_intake_sprint002_fork_atomicity_orphan_audit.md`) and Fork B
(`2026-08-05_intake_sprint002_fork_transaction_boundaries_state_machine.md`), read before writing this —
where this fork's findings converge with theirs, that's flagged explicitly, not re-derived as if new.

**Verdict key:** IDEMPOTENT (mechanism cited) · NOT IDEMPOTENT — CONFIRMED DEFECT (mechanism + trigger cited)
· NOT IDEMPOTENT BY DESIGN, ACCEPTABLE (reasoned, not assumed).

---

## Phase 5 — Idempotency Audit

### 1. Pipeline A upload — `api.py:4061` `predmet_upload_auto_analyze`

**Verdict: NOT IDEMPOTENT BY DESIGN, ACCEPTABLE for row/vector/blob creation — but with a real,
previously-unquantified resource-exhaustion tail the "by design" framing undersells.**

Read `api.py:4059-4267` in full. There is no content-hash check, no filename+size check, and no
idempotency key anywhere on this path — `hashlib.sha256(raw).hexdigest()` is computed
(`api.py:4198`, `source_meta["source_sha256"]`) but only ever *stored* as Pinecone chunk metadata,
never *queried* against existing rows before inserting. Confirmed against Sprint 001's own framing
("by design, no dedup logic exists") and `LD-005`/Finding #4 in `.vindex_ai_team/MISSION_BOARD.md:128`
("Smart Intake has exact-hash dedup; `api.py`'s reachable per-case upload does not").

For an identical file double-submitted N times to the same `predmet_id`:
- N independent `intake-dokumenti` Storage blobs (fresh `uuid4().hex` key each call, `api.py:4127`).
- N independent Pinecone chunk sets in the same shared owner namespace (no content-based skip).
- N independent `predmet_dokumenti` rows (`redni_broj` increments each time, `api.py:4192-4203`).
- N independent background `klasifikuj_i_sacuvaj` calls, N Genome-refresh background tasks (out of
  scope this sprint, noted only).
- **N independent `UsageService.consume(...)` calls** (`api.py:4523`) — i.e. **N billing-quota debits**
  for a single accidental double-click storm, plus **3×N GPT-4o calls** (procena + hronologija +
  metapodaci run in parallel per call, `api.py:4508-4514`). This is the resource-exhaustion angle the
  brief asked about, and it is real: a double-click by one lawyer is not "2 documents," it's "2 documents
  + 6 GPT-4o calls + 2 quota debits," silently.

**On `@limiter.limit("10/minute")` (`api.py:4059`) actually preventing this at N=100**: it does not, and
it cannot by construction. `api.py:545` builds its `limiter` via `build_limiter(_get_real_ip)`
(`shared/rate.py:47-56,89`) — the rate-limit key is the **caller's IP address**, not the user, not the
`predmet_id`, not the file hash. It throttles *volume from one address*, it does not detect or prevent
*duplication of one document*. Two back-to-back clicks from the same browser (2 requests, same IP,
well under 10/minute) sail through with zero friction and produce 2 full duplicate rows/vectors/blobs/
billing-debits. At the stated N=100, the limiter does cap *burst rate* (≥10 minutes wall-clock for a
single IP to place 100 calls, assuming it doesn't also trip Redis fail-open noise), but nothing stops
the total eventually landing — it is a throttle on speed, not a bound on count, and is orthogonal to
the actual duplication question. Verdict nuance: the *existing* duplication (no dedup logic) is a
reasonable, arguably correct product choice for "attach a fresh, explicit user action to an existing
case" (Sprint 001's framing stands) — but the **billing/GPT-cost compounding** this enables was not
previously quantified and is the sharper version of this finding.

### 2. Pipeline B upload+enqueue — `routers/smart_intake.py:92` `upload_intake_documents`

**Verdict: IDEMPOTENT for the job row (real prevention, not just downstream flagging) — but NOT
IDEMPOTENT for the Storage blob, on every duplicate submission, not only on RPC failure.**

`enqueue_intake_job` (`migrations/073_intake_foundations.sql:145-178`) runs a `SELECT ... WHERE
idempotency_key = p_idempotency_key` **before** the `INSERT`, and returns the existing `job_id` if found
(`:159-164`) — this is real pre-creation prevention, not a downstream "flag it after the fact" stage.
The key is `f"{user['user_id']}:{content_sha256}"` (`smart_intake.py:151`), so the same user
double/N-submitting *identical bytes* always maps to the same key.

**The `dedup_check` status the brief asks about is a dead schema artifact, not implemented
infrastructure.** Grepped the entire repo for `dedup_check`: it exists only as (a) a `CHECK` constraint
value and `_VALID_STATUSES`/`in_progress_statuses` tuple entry (`shared/intake_queue.py:33,135`,
`migrations/073_intake_foundations.sql:74-75`), (b) a frontend label string (`static/vindex.js:20946`),
and (c) prose in docs. **No code anywhere ever transitions a job into `dedup_check`** — grepped every
`claim_next_job(...)` call site (`shared/intake_worker.py:107`, 3 test files) and none targets it, and
`IntakeWorker._process()` (`shared/intake_worker.py:128-225`) never references it. Sprint 001's Failure
Recovery Matrix (`INTAKE_FAILURE_RECOVERY_MATRIX.md:20`) calling this "real dedup infrastructure Pipeline
A doesn't [have]" overstates it: the *actual* dedup mechanism live today is the `idempotency_key` unique
index (`idx_intake_jobs_idempotency`, `migrations/073_intake_foundations.sql:105-106`), not the
`dedup_check` stage, which is unused. This is a correction to Sprint 001's own record, not a new bug —
worth fixing in the matrix's own wording, not in code (out of this sprint's read-only bound to act on).

**New finding — Storage blob duplication on Pipeline B is unconditional, not merely an enqueue-failure
edge case (`INTAKE-002`'s originally-scoped trigger).** Read `smart_intake.py:126-156` in order:
content hash computed (`:126`) → **Storage encrypt+upload with a fresh `uuid.uuid4().hex` key
(`:127-141`) happens first** → *then* `enqueue_job(...)` is called (`:144-156`), which is where the
idempotency check lives. Two consequences, both real:
- **Sequential re-submit after the first request already completed** (ordinary retry, no race needed):
  the second call's Storage upload still runs and succeeds (a brand-new blob at a brand-new key), *then*
  `enqueue_intake_job` finds the existing row and returns the **old** `job_id` without ever recording the
  new blob's key anywhere. The new blob is orphaned **on every single duplicate submission**, not only
  when the RPC throws. This sharpens `INTAKE-002` with a second, much more common real-world trigger
  (plain double-submit) than the one it was originally scoped around (RPC infra failure).
- **True concurrent double-submit** (2 near-simultaneous requests, same content, same user): both
  Storage uploads succeed independently; both call `enqueue_intake_job` concurrently. The pre-check
  `SELECT` in the RPC (`migrations/073_intake_foundations.sql:159-164`) is not itself atomic against a
  second concurrent transaction — but the `UNIQUE INDEX ... WHERE idempotency_key IS NOT NULL`
  (`:105-106`) is the real backstop: the loser's `INSERT` raises a `23505` unique-violation inside the
  `SECURITY DEFINER` function, which has no exception handler for it, so the RPC call itself raises.
  `intake_queue.enqueue_job` (`shared/intake_queue.py:55-64`) propagates that exception up to
  `upload_intake_documents`'s per-file `try/except` (`smart_intake.py:153-156`), which reports
  `{"ok": False, "greska": "Greška pri prijemu dokumenta."}` for that file. **Net effect: true-race
  duplication of the *job row* is impossible (DB constraint), but the loser gets a user-visible failure
  response instead of a graceful "already in progress" — and still leaves its own already-uploaded
  Storage blob permanently orphaned**, since the code only logs+skips on the *upload* exception path
  (`:139-142`), not on a subsequent enqueue failure for an already-succeeded upload.

### 3. `IntakeWorker.claim_next_job` — does row-locking prevent double-processing of *duplicate rows*?

**Verdict: question's premise mostly doesn't arise in practice — IDEMPOTENT for the scenario that can
actually occur; the hypothesized "2 job rows, same document, 2 workers" case is structurally prevented
upstream, not by `claim_next_job` itself.**

Correctly distinguishing the two questions per the brief: `SELECT ... FOR UPDATE SKIP LOCKED`
(`migrations/073_intake_foundations.sql:198-219`) only prevents two workers from claiming the *same row*
concurrently — verified true, and it says nothing about two *different* rows. But per finding #2 above,
two distinct `intake_jobs` rows for the *same* uploaded content by the *same* user cannot exist (unique
index on `idempotency_key`) — so the specific "2 duplicate job rows silently both processed in parallel"
failure mode the brief hypothesizes cannot arise through this upload path for that case. Where two
*legitimately independent* rows for the same file bytes **can** exist — two different users uploading
the identical file (different `idempotency_key`, since it's `user_id:content_sha256`) — that is correct,
not duplication: each is a distinct user's distinct case/document, and `claim_next_job` processing them
in parallel on two different workers is exactly intended concurrent behavior, not a bug.

### 4. Pipeline C finalize — `routers/smart_intake.py:373` `finalize_intake_job`

**Verdict: NOT IDEMPOTENT — CONFIRMED DEFECT under concurrent retry (real, exploitable race window);
IDEMPOTENT only for sequential retry-after-response. This fork's single most important finding, and it
independently reconfirms — does not merely repeat — a finding both Fork A (§C-bonus) and Fork B (§3.4)
already flagged the same day: three independent reads converging on the identical root cause is a strong
signal this is real, not a misreading.**

The endpoint's own docstring (`smart_intake.py:378-381`) claims "Idempotentno: ako je posao vec
finalizovan (`intake_jobs.predmet_id` popunjen), vraca postojeci predmet umesto da pravi duplikat" — and
the **check** for that is real (`smart_intake.py:402-403`: `if job.get("predmet_id"): return {"ok": True,
"predmet_id": job["predmet_id"], "already_finalized": True}`). The defect is in the **write**, not the
check: `intake_jobs.predmet_id` is only updated at `smart_intake.py:733-735`
(`supa.table("intake_jobs").update({"predmet_id": predmet_id}).eq("id", job_id).execute()`) — the
**very last statement before the response is built**, *after* every side effect has already run:
`predmeti` insert (`:449-464`), `klijenti`/`predmet_klijenti` insert (`:481-514`), conflict-check
background task fire (`:515-556`), `predmet_hronologija` deadline insert (`:559-572`), full
decrypt→OCR→chunk→Pinecone→`predmet_dokumenti` insert (`:576-689`), Genome-refresh and Evidence
auto-classify background task fires (`:691-731`).

There is no lock, no atomic claim-and-mark (no `UPDATE ... WHERE predmet_id IS NULL RETURNING`
equivalent to `claim_intake_job`'s own pattern one file over), and Supabase's REST client exposes no
`SELECT ... FOR UPDATE` here even if someone wanted it. This is a textbook check-then-act TOCTOU window:
two finalize calls for the **same `job_id`** arriving close enough together (both plausible triggers
named in the brief — a double-click, or a frontend timeout firing an automatic retry while the first
call is *still running* server-side, which is exactly the multi-second/multi-GPT-call shape this endpoint
has) both read `job.predmet_id` as `NULL`, both pass the `status == "completed"` check, and **both run
the entire body independently** — two `predmeti` rows, two client links, two deadline rows, two
`predmet_dokumenti` rows, two Pinecone ingests, two Evidence-classify background tasks. Whichever
request's `UPDATE ... predmet_id` statement commits last "wins" the `intake_jobs.predmet_id` pointer;
the other predmet_id's entire object graph (case + client + deadline + document + vectors) is now a
live, fully-formed, **orphaned duplicate case** with no `intake_jobs` row ever pointing back to it — a
strictly worse shape than Sprint 001's `INTAKE-001`/`INTAKE-002` (those lose or mis-signal one artifact;
this silently creates one full duplicate legal case file). For genuinely sequential retry (client waits
for the full response before retrying), this is safely idempotent — by the time a second call could
arrive, `predmet_id` has already been written. The risk is specifically the concurrent/overlapping-retry
window, which is real given the endpoint's own multi-second synchronous shape.

### 5. Event Bus handlers — `services/event_bus.py`, especially `on_document_job_failed`

**Verdict: NOT IDEMPOTENT — CONFIRMED DEFECT, and the precondition for it to actually fire twice
(migration 091 not run) is itself confirmed live, not hypothetical.**

`on_document_job_failed` (`services/event_bus.py:193-248`) resolves `uploaded_by`/`predmet_id` from
`intake_jobs` (`:207-215`) and calls `create_proactive_alert(...)` (`:222-242`) unconditionally on every
invocation — no dedup check (no "does an alert for this `intake_job_id` already exist" query) anywhere in
`create_proactive_alert` itself (`shared/proactive_alerts.py:50-98`, read in full: it is a plain retry-
wrapped `INSERT`, nothing else). Two dispatches of the identical `DocumentJobFailed` event row therefore
produce two distinct `proactive_alerts` rows for one real failure.

Whether that can happen today: `dispatch_pending_events()` (`services/event_bus.py:436-550`) first tries
`claim_pending_events` (migration 091's atomic `SELECT ... FOR UPDATE SKIP LOCKED` claim, per
`_is_missing_function_error`'s own comment at `:425-433`); if that RPC isn't deployed, it **silently
falls back to a plain `SELECT ... WHERE dispatched_at IS NULL` with no lock at all**
(`:469-478`), and only calls `_mark_dispatched` (`:553-559`) **after** `bus.publish_async(event)` has
already fully run the handler (`:499-501`). Migration 091 not being run is already tracked as
`KEYSTONE-007` (per project memory and Sprint 001) — confirmed present but unapplied at
`migrations/091_event_bus_atomic_claim.sql`. Given production runs 4 gunicorn workers each polling the
same `events` table every ~3s (per the function's own docstring, `:443-454`), the window between one
worker's plain `SELECT` and its later `_mark_dispatched` is wide open to a second worker's `SELECT`
picking up the same undispatched row and running the same handler concurrently — this is a **live**
exposure today, not a theoretical one, and `on_document_job_failed` is a concrete, confirmed-non-
idempotent handler that would produce a real duplicate `proactive_alerts` row if it fires.

(Not separately re-audited here, out of this fork's Phase-5 named scope: `on_rok_kritican`,
`on_predmet_kreiran`, `on_dokument_uploadovan`, `on_health_score_promenjen`, `on_genome_updated` — the
brief named `on_document_job_failed` specifically as the intake-relevant handler; the others touch
Deadlines/Genome/forbidden modules this sprint.)

### 6. `log_action` audit calls — duplicate rows for a duplicate real-world action

**Verdict: NOT A DEFECT. Duplicate `audit_immutable` rows for two genuinely-duplicate real actions are
the correct, honest behavior of an append-only ledger — reasoned through deliberately, not assumed.**

`audit_immutable` is explicitly documented as an append-only, hash-chained ledger
(`shared/audit_immutable.py:5-17`): "Tabela: audit_immutable (INSERT-only — nikad UPDATE/DELETE)". Its
job is to record that an action *occurred*, not to model whether the user considered two occurrences
"the same." `log_action(...)` (`:127-165`) is called exactly once per handler invocation, unconditionally
— on Pipeline A's `dokument_upload` call site (`api.py:4288-4297`) there is no internal retry loop around
the `log_action` call itself, so one real HTTP request that reaches that line produces exactly one audit
row; the *only* way to get two rows is two real HTTP requests that each actually completed far enough to
reach that call site — i.e., two real uploads (per finding #1, Pipeline A has no dedup, so this is already
an accepted, by-design consequence one layer up, not a bug introduced by the audit layer). Since each of
those two requests represents a genuinely distinct real-world occurrence (two separate `predmet_dokumenti`
rows really were created), two audit rows describing two real creations is accurate, not duplicated
noise. This would only become a genuine defect if a *single* real action produced two `log_action` calls
for the *same* resulting row/resource_id — which was not found anywhere in Pipeline A's, B's, or C's
reachable code (no retry-wrapped `log_action` call site exists on any of the three journeys).

---

## Phase 8 — Production Replay

**Chosen journey**: a lawyer uploads a signed, scanned contract PDF to an **existing** case via
**Pipeline A** (`api.py:4061`). OCR succeeds (it was scanned, `ocr_used=True`), Pinecone ingest succeeds,
`predmet_dokumenti` insert succeeds. Using only what the code actually persists (traced line-by-line
above and below, not invented):

### What would exist afterward

| Table/system | Row(s) | What it contains | What it does NOT contain |
|---|---|---|---|
| `predmet_dokumenti` | 1 row (`api.py:4192-4227`) | `predmet_id`, `user_id`, `naziv_fajla`, `storage_path` (real Storage key if the best-effort original-file save succeeded, else the old non-dereferenceable `session/{id}` label), `pinecone_namespace`, `status="indeksirano"`, `velicina_kb`, `redni_broj`, `tekst_sadrzaj` (OCR text truncated to 100,000 chars) | **No `ocr_used`/`is_scanned` column at all** — whether this document went through OCR is not recoverable from this row. **No `correlation_id` column.** No truncation marker — if the source text was >100k chars, the row gives no sign that what's stored is a partial copy. |
| `intake-dokumenti` Storage bucket | 1 encrypted blob at `{user.id}/{predmet_id}/{uuid4}{suffix}` (`api.py:4127`) | The original file bytes, AES-GCM encrypted | Nothing pointing back to it except `predmet_dokumenti.storage_path` — if that best-effort write failed, the blob (if it even got created) is unreferenced |
| Pinecone (`_owner_ns` namespace) | N chunk vectors | `predmet_id`, `kancelarija_id`, `type="case_doc"`, `origin`/`origin_chain`, `source_filename`, `source_format`, `source_sha256`, `is_scanned` (chunk-level, `api.py:4198-4225`) | **No `document_id`/`dok_id` field anywhere in chunk metadata** — cannot be joined back to the specific `predmet_dokumenti.id` row by foreign key on either Pipeline A or C (verified same gap in `smart_intake.py:583-621`'s `extra_metadata`). If a case has 2+ documents, attributing a given chunk to a given row requires fuzzy matching on `source_filename`/`source_sha256`, which can be ambiguous (two uploads with the same filename) |
| `audit_immutable` | 1 `dokument_upload` row, **if** the fire-and-forget task completed (`api.py:4288-4297`, `asyncio.create_task(log_action(...))`, not awaited) | `resource_id=_dok_id`, `user_id`, `ip`, `metadata={predmet_id, naziv_fajla}`, `correlation_id` (inherited from the request's root-minted id, `api.py:985-1008`) | Not guaranteed to exist at all — no dead-letter/retry mechanism of its own if the background task's DB write fails; only a `logger.warning` (`api.py:4298`, "nije kritično" pattern repeated throughout) |
| `ai_forensics` | 3 rows (procena, hronologija, metapodaci — `api.py:4508-4522`'s parallel GPT-4o calls, globally intercepted by `shared/ai_client.py:306-324`'s `_guarded_create` patch) | `predmet_id`, `document_id=_dok_id`, `module_name="api_upload"`, `operation_name="procena_hronologija_metapodaci"`, `correlation_id` (same id as the audit row above, inherited via `case_context()`, `api.py:4507-4520`), `status`/`error_message` (captures failures too, `shared/ai_client.py:206-207`) | **Also fire-and-forget** (`shared/ai_client.py:210-217`, `loop.create_task(coro)`, swallowed at DEBUG level on its own failure) — the *second* independent best-effort provenance system on this journey, not just the audit one; both can silently no-op on a crash/DB blip with zero trace |
| `predmet_istorija` | 1-2 rows (`api.py:4540-4549` auto-procena, `api.py:4626-4635`-ish metapodaci) | `predmet_id`, `user_id`, free-text `pitanje` (mentions filename), `odgovor`, `confidence` | **No `document_id` FK, no `correlation_id` column** — links back to a specific document only via matching the filename string embedded in `pitanje`'s text |
| `predmet_hronologija` | 0-50 rows (`api.py:4592-4593`) | `predmet_id`, `user_id`, `dokument_naziv` (free text), `datum(_iso)`, `dogadjaj`, `akter`, `vaznost` | Same — no FK to the document row, no correlation_id |
| Case Genome / Evidence classification | background writes (out of scope this sprint — `case_dna`, `predmet_dokazi`/`tip_dokaza` update) | — | Not traced further per charter |

### Can the full journey be reconstructed from persisted data alone?

**Partially, and the gaps cluster in a specific, useful pattern: everything that is a required write for
the case file to function (the document row, the Storage blob, the Pinecone chunks) is durable; almost
everything that would let an auditor *prove what happened and why* (that OCR ran, that this specific
request is the one that produced this row, that the AI calls succeeded or why they didn't) rides on
fire-and-forget writes with no guarantee and no failure-visible trace of their own.**

Confirmed still true from Sprint 001 (`INTAKE_SOURCE_OF_TRUTH_MATRIX.md:9`): OCR's own output is not
durably preserved beyond the 100k-char truncated copy in `tekst_sadrzaj` — re-confirmed by direct read
of `api.py:4227` (`_tekst_preview = text[:100_000]`), not merely restated.

**Additional blind spots this replay-specific framing surfaces that Sprint 001's audit-trail analysis did
not specifically name:**

1. **Whether OCR ran at all is not recorded on the case-file row itself.** `predmet_dokumenti` has no
   `ocr_used`/`is_scanned` column on Pipeline A or C (only Pipeline B's separate `intake_documents` table
   has `ocr_confidence`, per the existing matrix) — the *only* place `is_scanned` is recorded for a
   Pipeline A/C document is inside Pinecone chunk metadata, a different system entirely, and only at
   chunk granularity, not exposed as a queryable document-level fact anywhere.
2. **No foreign key from Pinecone chunks to `predmet_dokumenti.id`, on either Pipeline A or C** — verified
   by reading both `extra_metadata` dicts in full (`api.py:4204-4213`, `smart_intake.py:610-621`); neither
   includes `document_id`/`dok_id`. For a single-document case this is unambiguous by construction; for a
   multi-document case it is not — reconstruction falls back to fuzzy `source_filename`/`source_sha256`
   matching, which is not a hard guarantee.
3. **Two independent, unrelated fire-and-forget provenance systems on the same journey, not one.** The
   `audit_immutable` write (`log_action`) and the three `ai_forensics` writes (`_capture_chat_provenance`)
   are each individually best-effort with no cross-check between them — a crash or transient error can
   silently drop either (or both) with only a DEBUG/WARNING log line, meaning the *correlation_id itself*,
   the one thing meant to unify a replay across systems, can end up recorded in neither durable table for
   a given document even though the document row itself was created successfully.
4. **No truncation marker.** If `text` exceeds 100,000 characters, `tekst_sadrzaj` is silently cut with no
   flag anywhere indicating that what's stored is partial — a replay reading this field cannot tell
   "the whole document was short" from "the document was long and this is missing 40% of it."
5. **AI-call partial failure is invisible at the case-file layer even though it's captured one layer
   down.** If all 3 parallel GPT calls in the auto-analysis step raise, `ai_forensics` *does* capture each
   as `status="error"` (verified, `shared/ai_client.py:206-207`, `:318-323`) — correcting an initial
   hypothesis in this fork's own draft — but `predmet_istorija`/`predmet_hronologija` simply gain zero new
   rows, and nothing in those tables (or in `predmet_dokumenti`) indicates "auto-analysis ran and failed"
   versus "auto-analysis was never attempted" versus "the document had nothing extractable." Reconstructing
   *that* distinction requires already knowing to cross-reference `ai_forensics` by `document_id`, which
   is undocumented as the intended read path anywhere in the codebase's own comments.
6. **`redni_broj` collisions are visible as a symptom, not a cause.** Two documents sharing a
   `redni_broj` (the Failure Recovery Matrix's own acknowledged "benign best-effort race") is observable
   from `predmet_dokumenti` directly, but nothing in persisted data indicates it was a race rather than a
   genuine data-entry anomaly — the *why* is lost, only the *what* survives.

None of the above are "document lost" in Sprint 001's sense — the case-file artifacts a lawyer actually
needs (the document, its text, its index) all durably exist on the happy path traced here. The gap is
specifically in **forensic replay**: proving after the fact, from data alone, exactly which request did
what, whether every step actually ran as claimed, and why a downstream field is empty when it is.

---

## Files read for this analysis (traceability)

`api.py` (4059-4267, 4320-4610ish, 985-1030, imports at 543-545), `routers/smart_intake.py` (1-180,
350-756), `shared/intake_queue.py` (full), `shared/intake_worker.py` (full), `shared/rate.py` (full),
`shared/ai_provenance.py` (full), `shared/ai_client.py` (154-334), `shared/audit_immutable.py` (1-230),
`shared/proactive_alerts.py` (50-100), `services/event_bus.py` (193-260, 340-560), `routers/evidence.py`
(188-230), `migrations/073_intake_foundations.sql` (full), `migrations/091_event_bus_atomic_claim.sql`
(existence confirmed, not run), `docs/architecture/INTAKE_ARCHITECTURE_REPORT.md`,
`INTAKE_SOURCE_OF_TRUTH_MATRIX.md`, `INTAKE_FAILURE_RECOVERY_MATRIX.md`, and this sprint's own Fork A and
Fork B reports (for convergence-checking §4 above, not re-derivation).

**Explicitly not touched, per charter**: OCR quality, Case Genome, Decision Engine, Strategy Engine,
Copilot, Briefing, Timeline, Search, Alerts, Tasks, Dashboard, Firm Brain — noted only where this fork's
own traced code paths intersected them (Genome/Evidence background-task fire points, not their internals).
