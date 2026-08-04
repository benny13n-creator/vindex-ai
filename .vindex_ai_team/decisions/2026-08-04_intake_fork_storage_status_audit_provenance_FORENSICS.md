# Intake Fork — Document Status / Correlation ID / Audit / Provenance / Storage Forensics

**Program Intake, Sprint 001 — "Bulletproof Document Intake Foundation."** Scope: UPLOAD → OCR →
VALIDATION → STORAGE only, read-only. Does not re-derive Program Beta's AI-confidence findings
(`docs/architecture/CONFIDENCE_MODEL_SPECIFICATION.md`, `EVIDENCE_CHAIN_REGISTRY.md`) or Program
Alpha's dual-classifier finding (`2026-08-04_alpha_domain_document_pipeline_INVENTORY.md`) — both cited
where relevant, not repeated. All claims verified against current code/migrations, file:line cited.

---

## 0. Two disconnected upload pipelines exist — establishes which one this report traces

Two entirely separate systems both write to `predmet_dokumenti` and both call themselves "intake":

1. **`POST /api/predmeti/{predmet_id}/upload`** (`api.py:4061-4063`, handler `predmet_upload_auto_analyze`)
   — the only one reachable from the product UI today. Synchronous: OCR → chunk → Pinecone → DB row →
   AI analysis, all inside one HTTP request plus a few fire-and-forget background tasks.
2. **Smart Intake Engine** (`routers/smart_intake.py`, `shared/intake_worker.py`, `shared/intake_queue.py`,
   `shared/intake_classify.py`, `shared/intake_extract.py`, tables `intake_jobs`/`intake_documents`/
   `extracted_entities`/`intake_review_queue`/`intake_processing_outcomes`, migrations 073/074) — async
   job queue with genuinely superior reliability engineering (claim/retry/dead-letter, append-only
   `intake_audit_log`, real encrypted Supabase Storage persistence). **Has no frontend entry point**
   (confirmed pre-existing finding, `2026-08-03_ZTC-FRONTEND_smart_intake_wiring_BLOCKER_REPORT.md`,
   independently re-confirmed here: `api.py:4049` comment, router registered at `api.py:583,678`,
   background loops started at `api.py:822`, zero UI callers found for `/api/smart-intake/documents`).

**This report traces path #1 as "the document's journey"** — it is the one a real lawyer's upload
actually takes. Path #2 is described only where its (better) design highlights what #1 is missing.

---

## 1. Document status — NOT one source of truth, several overlapping and partially-dead signals

**Base column**, `supabase_setup.sql:336-346`:
```
predmet_dokumenti.status  TEXT NOT NULL DEFAULT 'na_cekanju'
```
No CHECK constraint — any string is legal. Five known writers, three real behaviors:

| Writer | File:line | Sets `status`? | Value(s) |
|---|---|---|---|
| Main upload (reachable) | `api.py:4220` | Yes | `"indeksirano"` (Pinecone ok) / `"sacuvano"` (Pinecone full/failed) |
| Smart Intake finalize (unreachable) | `routers/smart_intake.py:666` | Yes | Same two values, same logic |
| Drafting — AI draft saved as doc | `routers/drafting.py:314` | Yes | Always `"indeksirano"` |
| Intake Wizard — link pre-uploaded doc to new predmet | `routers/intake.py:228-243` | **No** | Falls to DB default `'na_cekanju'`, forever |
| Onboarding — demo document row | `routers/onboarding.py:274-277` | **No** | Falls to DB default `'na_cekanju'`, forever |

**Consumer**, `routers/copilot.py:804`:
```python
cekaju = [d for d in dok if d.get("status") in ("na_cekanju", "greska")]
```
treats `"na_cekanju"` as "still waiting, actionable." No writer anywhere in the codebase ever sets
`"greska"` (grepped, zero hits) — that branch is dead. Worse: `"na_cekanju"` is **not actually a
processing-in-progress signal** anywhere in this pipeline (OCR/Pinecone/DB-write all happen synchronously
inside one request in path #1 — nothing is ever asynchronously "pending" at this column). It is really
"this insert path never bothered to set the column" — true for wizard-linked and demo documents, which
are otherwise completely finished, fully real documents. Copilot's consumer therefore misreports finished
documents as eternally pending.

**A second, independent "is this document ready" signal exists on the same table**: `tip_dokaza` /
`klasifikovan_at` (added by `migrations/016_evidence_vault.sql:5-9`, comment at line 12-19 confirms no
soft-delete/lifecycle concept was ever added to this table). These are written by a **fire-and-forget
background task** (`api.py:4266-4274`, `asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))`)
that can finish seconds after, or never (best-effort, uncaught exceptions only logged — `shared/
intake_worker.py`... no — `routers/evidence.py:228-229` `except Exception as exc: logger.warning(...)`,
swallowed). A document can therefore be `status="indeksirano"` (done, per the first signal) while
`klasifikovan_at IS NULL` (not done, per the second) indefinitely, and nothing joins the two into one
lifecycle state. This is the storage-layer twin of Program Alpha's already-documented dual-classifier
finding (`2026-08-04_alpha_domain_document_pipeline_INVENTORY.md` Finding #1) — cited, not re-derived.

**A third, fully separate status enum exists on a different table** for path #2:
`intake_jobs.status IN ('received','preprocessing','classifying','extracting','matching','dedup_check',
'awaiting_review','completed','failed')` (`migrations/073_intake_foundations.sql:73-75`) — richer and
better-designed than `predmet_dokumenti.status`, but **its lineage is discarded at finalize**: grepped
`routers/smart_intake.py` for `intake_job_id` — zero occurrences in the `predmet_dokumenti` insert dict
(`smart_intake.py:660-668`). Once a Smart Intake job finalizes into a case document, the row carries no
FK back to the `intake_jobs`/`intake_documents`/`extracted_entities` row that produced it — the Confidence
Graph, OCR confidence, classification method, and any human corrections captured during Phase 1A become
permanently unlinked from the case-file document. (Moot today only because path #2 is unreachable — but
this is exactly the kind of hidden invariant Program Alpha's stress-test framing warns about: `[Finding #1]`
of that report already names the identical shape for classification-write-ordering.)

**Verdict: NOT one canonical status owner.** Three independently-lifecycled fields
(`predmet_dokumenti.status`, `predmet_dokumenti.klasifikovan_at`, `intake_jobs.status`) each answer
"where is this document" for overlapping subsets of documents, with no reconciliation and one confirmed
dead/misleading consumer read (`copilot.py:804`).

---

## 2. Correlation ID — survives the reachable path, but through one documented "inert" call and one
   `asyncio.create_task` boundary that is correct only by accident of timing

**Root mint point**: `correlation_id_middleware` (`api.py:985-1008`), runs before all route
dependencies/auth, calls `set_request_context(correlation_id=request.headers.get("X-Correlation-ID"))`
(`api.py:1005`) directly in the request's own coroutine (no thread hop) — this is the one call that
actually lands in `_request_ctx` for the request. Echoed back via `X-Correlation-ID` response header
(`api.py:1007`).

**Known dead branch**: `_require_auth` (`api.py:3071-3117`, used by the upload endpoint at `api.py:4082`)
also calls `set_request_context()` (`api.py:3113`), but only inside `await asyncio.to_thread(_require_auth,
...)` — a contextvar mutation made *inside* a `to_thread`-offloaded function does not propagate back to
the awaiting coroutine (documented in-place as a "KNOWN LIMITATION," `api.py:3097-3110`). This call is a
no-op from the endpoint's perspective. It happens to be harmless only because the middleware already set
the real value first — if the middleware were ever removed or reordered, this endpoint would silently
lose its correlation_id with no test currently proving otherwise.

**Full journey for one document through `api.py:4061` (`predmet_upload_auto_analyze`)**:
1. Middleware mints/reuses `cid` → `_request_ctx` (`api.py:1005`). **Alive.**
2. `_require_auth` via `to_thread` — its internal re-set is inert (`api.py:3113`, see above). **Alive
   (unaffected).**
3. OCR (`uploaded_doc/extractor.py::extract`, called `api.py:4120`) — no `case_context()`, no read of
   `cid` at all; the extraction step itself produces no provenance record of any kind. **Ambient only —
   never captured.**
4. Pinecone ingest (`uploaded_doc/ingest.py::ingest_session`, called `api.py:4171`) — same: no
   `case_context()`, no correlation_id attached to the vector metadata block built at `api.py:4173-4184`.
   **Ambient only — never captured.**
5. `predmet_dokumenti` insert (`api.py:4226/4228`) — plain DB insert, no correlation_id column on this
   table at all (schema has none). **Not carried into storage.**
6. `log_action("dokument_upload", ...)` fired via `asyncio.create_task(...)` (`api.py:4254-4261`), not
   awaited. `log_action` defaults to `current_correlation_id()` when not passed explicitly
   (`shared/audit_immutable.py:152-157`). `asyncio.create_task` copies the current `contextvars.Context`
   at task-creation time (`api.py:4254` runs inside the original request coroutine, after step 1, so the
   copy is correct) — **cid correctly reaches this one audit row.** This is the ONLY point in the entire
   journey where the correlation_id is durably persisted anywhere.
7. Evidence classification background task (`asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj,
   ...))`, `api.py:4269-4272`) — same create_task timing argument applies, so the thread inherits `cid`.
   Inside, `case_context(predmet_id=..., document_id=..., module_name="evidence",
   operation_name="klasifikacija")` (`shared/intake_worker... ` — correction: `routers/evidence.py:206`)
   wraps only the classification GPT call itself, **inheriting** (not overriding) `cid` per
   `ai_provenance.py:93`'s "explicit override or request-level id" rule. The `log_action_sync
   ("evidence_klasifikacija", ...)` call (`routers/evidence.py:224-227`) is placed *after* the `with`
   block has already exited (`case_context`'s `finally` at `ai_provenance.py:110-111` has already reset
   `_case_ctx`) — it still gets `cid` correctly (via the surviving `_request_ctx`), but loses the
   predmet_id/document_id case-scoping for that specific audit call; not a correlation-id break, a minor
   context-narrowing.
8. Genome auto-refresh background task (`api.py:4278-4289`) — separate `asyncio.create_task`, same
   inheritance mechanics, not traced further (Case Genome named out-of-scope per mission brief).
9. Post-upload AI analysis (procena/hronologija/metapodaci, `api.py:4477-4486`) — explicitly wrapped in
   its own `case_context(predmet_id=predmet_id, document_id=_dok_id, module_name="api_upload",
   operation_name="procena_hronologija_metapodaci")` (`api.py:4476-4480`), correctly inheriting `cid`.

**Verdict: correlation_id is never dropped/regenerated on the reachable path** — every step either
inherits it correctly or simply never touches provenance infrastructure at all (steps 3-5). The real gap
is not "a new id gets minted," it's "most of the journey (OCR, chunking, Pinecone ingest, the DB row
itself) has no correlation_id-bearing record to begin with," covered in §3-4 below.

---

## 3. Audit trail (`shared/audit_immutable.py::log_action`/`log_action_sync`) — one call for the whole
   journey, three real gaps

**Every `log_action`/`log_action_sync` call reachable from one document's upload-to-storage journey**:

| Step | Call | File:line |
|---|---|---|
| Upload complete (row exists) | `log_action("dokument_upload", ...)` | `api.py:4254-4261` |
| Evidence classification complete | `log_action_sync("evidence_klasifikacija", ...)` | `routers/evidence.py:224-227` |

That is the **entire list** for UPLOAD→OCR→VALIDATION→STORAGE. Confirmed by direct grep: zero
`log_action`/`log_action_sync` occurrences anywhere in `shared/intake_worker.py`, `shared/
intake_classify.py`, `shared/intake_extract.py`, `shared/intake_queue.py`, or `routers/smart_intake.py`
(path #2's only audit trail is the separate, non-`audit_immutable` `intake_audit_log` table, written by
the `enqueue_intake_job`/`complete_intake_job`/`fail_intake_job` RPCs — `migrations/
073_intake_foundations.sql:117-137,170-171,241-245,276-289` — a durable but entirely parallel mechanism
with no `correlation_id` column and no cross-reference to `audit_immutable`).

**Real gaps on the reachable path**:
1. **OCR itself produces no audit record.** `"dokument_upload"` fires only after OCR has already
   succeeded and the DB row exists — a scanned/unreadable document that gets rejected at `api.py:4130-4134`
   (`422 Tekst nije čitljiv ni optičkim prepoznavanjem`) leaves **zero trace** in `audit_immutable`. There
   is no way to later answer "how many uploads failed OCR this month" from the audit log — only from
   application logs (`logger.warning`), which are not queryable/immutable/retained the same way.
2. **Pinecone ingest failure is not itself audited**, only reflected indirectly in the `status` column's
   value (`api.py:4220`, `"sacuvano"` instead of `"indeksirano"`) — `_pinecone_ok=False` (`api.py:4190`)
   never appears in `dokument_upload`'s `metadata` dict (`api.py:4260`, only `predmet_id`/`naziv_fajla`).
   A forensic reader of `audit_immutable` cannot distinguish a fully-indexed upload from a
   text-only-saved one without joining back to the live `predmet_dokumenti.status` (which, per §1, is
   itself not a reliable single source of truth).
3. **View/download are in the allowlist and have UI labels, but are never called.**
   `"dokument_view"`/`"dokument_download"` are both in `AUDITABLE_ACTIONS`
   (`shared/audit_immutable.py:60`) and both have a human-readable label already wired for a timeline UI
   (`routers/intelligence_timeline.py:35-36`) — but grepping the entire codebase for either action string
   as a `log_action(...)` call site returns zero matches. The actual read/download endpoint,
   `predmet_dokument_preview` (`api.py:4783-4826`), never calls `log_action` at all. For a legal-document
   product, "who viewed this evidence and when" is exactly the kind of record a lawyer or compliance
   reviewer would expect to be able to pull — it does not exist today despite the plumbing already
   existing on both ends (allowlist + UI label) and only the actual call site missing.

---

## 4. Provenance (`shared/ai_provenance.py::case_context()`) — same two AI calls covered, everything
   else uncovered

Grepped every `case_context(` call site platform-wide (34 hits). Only two apply to this pipeline's
UPLOAD→OCR→VALIDATION→STORAGE scope:
- `routers/evidence.py:206` — wraps the classification GPT call only (`predmet_id`, `document_id`,
  `module_name="evidence"`, `operation_name="klasifikacija"`).
- `api.py:4477-4480` — wraps the post-upload procena/hronologija/metapodaci GPT calls
  (`module_name="api_upload"`, `operation_name="procena_hronologija_metapodaci"`).

**Not wrapped, confirmed absent**:
- OCR (`uploaded_doc/extractor.py::extract`) — not an AI call, so `case_context()` doesn't strictly apply,
  but it also means OCR produces no `ai_forensics` row of any kind (no per-document OCR provenance at
  all, consistent with Program Beta's separately-covered finding that OCR confidence itself is a hardcoded
  `0.6` placeholder — `intake_worker.py:181`, cited not re-derived).
- Pinecone chunk/embed step (`uploaded_doc/chunker.py::chunk_document`, `uploaded_doc/ingest.py::
  ingest_session`) — no wrap.
- `predmet_dokumenti` DB insert itself — no wrap (not an AI call, but also the point where `status`/
  `pinecone_namespace`/`storage_path` get frozen into the row with no provenance link to the request that
  produced them beyond the row's own `user_id`/`created_at`).
- Smart Intake's `intake_classify.py`/`intake_extract.py` (path #2) — zero `case_context` usage found by
  grep, consistent with §3's audit-trail finding: path #2 has its own island of state (`intake_audit_log`)
  disconnected from the platform's canonical provenance/audit primitives entirely.

**Verdict**: provenance coverage on the reachable path exactly matches audit-trail coverage (§3) — the
two AI-calling steps are wrapped, the four non-AI or background steps (OCR, chunk/embed, DB write,
view/download) are not. This is a real but narrow gap: it is the same "no per-step record for non-LLM
processing steps" gap under two different systems, not two independent gaps.

---

## 5. Storage tracing — Pinecone namespace consistent; Supabase Storage is the sprint's most severe finding

**Pinecone namespace**: consistent across every reachable write site checked.
`shared/kancelarija_utils.py::rag_owner_namespace(user_id, kancelarija_id)` produces `_owner_ns`, used
identically at `api.py:4103,4219` (upload) and `routers/drafting.py:314` (`owner_ns`, AI-draft-saved-as-doc).
Real, current, no drift found between what's written to Pinecone metadata and what's written to
`predmet_dokumenti.pinecone_namespace`.

**Supabase Storage bucket — the actual uploaded file is never persisted on the reachable path.**
Grepped `uploaded_doc/*.py` (the module used by `api.py:4061`'s entire OCR/chunk/ingest flow) for any
`.storage.from_(` / bucket call: **zero matches**. The raw file bytes (`raw = await file.read()`,
`api.py:4109`) are written to a `tempfile.NamedTemporaryFile` (`api.py:4116-4118`) purely to let `extract()`
read them, then the temp file is deleted in the `finally` block (`api.py:4135-4138`). Only the *extracted
text* (`tekst_sadrzaj`, truncated to 100k chars, `api.py:4197,4226`) and Pinecone vector chunks survive.
The `storage_path` column value written at `api.py:4215` — `f"session/{session_id}"` — **does not point
to any object that exists in Supabase Storage**; it is a label with no corresponding stored artifact.
Confirmed by `predmet_dokument_preview` (`api.py:4783-4826`, the only document-content-read endpoint):
its own docstring says "Vraća tekst dokumenta" (`api.py:4789`) and its two data sources are
`tekst_sadrzaj` (`api.py:4808`) and a Pinecone-chunk reconstruction fallback (`api.py:4811-4817`) — there
is no third path that ever reads from Storage, because nothing was ever written there for this pipeline.

**By contrast**, path #2 (Smart Intake, unreachable) does this correctly: encrypts the raw bytes
(`_encrypt()`, `routers/smart_intake.py:79-89`, same AES-GCM pattern as the Klijenti Trezor) and uploads
to a real bucket (`_STORAGE_BUCKET = "intake-dokumenti"`, `smart_intake.py:58`; `bucket.upload(...)`,
`smart_intake.py:131-138`; bucket itself created at `migrations/073_intake_foundations.sql:362-364`). This
is strictly better engineering, sitting entirely behind a pipeline no lawyer can reach today.

**Practical consequence**: on the only pipeline a user can actually use, the original PDF/DOCX/scanned
image a lawyer uploads is discarded within the same HTTP request that accepted it. If OCR mis-extracted a
figure/table, if the extracted-text truncation (100k chars, `api.py:4197`) cut off part of a long
document, or if a lawyer simply wants to see the literal scanned original later (a routine need for
evidentiary documents), there is no way to retrieve it — not from Storage (nothing there), not from the
DB (only truncated extracted text), not from Pinecone (only embedding chunks, not the source bytes).

---

## Summary for parent

**Status ownership**: NOT one canonical source of truth. `predmet_dokumenti.status` (5 writers, 3 real
behaviors, DB-default `'na_cekanju'` silently misused as "never touched" by 2 of 5 insert paths, one dead
consumer branch — `copilot.py:804`), `predmet_dokumenti.klasifikovan_at` (independent, best-effort
background-task-written second lifecycle signal), and `intake_jobs.status` (a third, richer status enum
on an entirely separate table whose lineage — `intake_job_id` — is discarded at finalize) all coexist
unreconciled.

**Correlation ID**: survives the entire reachable upload journey without ever being dropped or
silently re-minted — every step either correctly inherits it (via `asyncio.create_task`'s context-copy
semantics landing after the middleware's mint) or simply has no provenance/audit call to attach it to at
all. One documented-in-place dead code path (`_require_auth`'s internal `set_request_context()` call,
`api.py:3097-3117`) is currently harmless only because the middleware runs first; it is a latent trap, not
a live break.

**Most severe observability/integrity gap found**: **the original uploaded file is never stored anywhere**
on the only pipeline a lawyer can actually use — `uploaded_doc/` has zero Supabase Storage calls, the temp
file is deleted after text extraction, and `predmet_dokumenti.storage_path` is a non-dereferenceable label.
This is worse than an audit-log gap: it is unrecoverable data loss of the literal legal document, on a
product whose core promise is being the reliable system of record for exactly these files. The
better-engineered alternative (real encrypted Storage persistence, richer status enum, durable
`intake_audit_log`) already exists in the codebase (`routers/smart_intake.py`) but is wired to no frontend
entry point, so it protects zero real documents today.

**Second-most severe**: the audit trail for the reachable path is exactly two events wide
(`dokument_upload`, `evidence_klasifikacija`) for a journey with at least five real steps (OCR, chunk,
Pinecone ingest, DB write, view/download) — OCR failures, Pinecone-ingest failures, and every document
view/download leave no record in `audit_immutable` despite `dokument_view`/`dokument_download` already
being allowlisted with UI labels ready and simply never called.
