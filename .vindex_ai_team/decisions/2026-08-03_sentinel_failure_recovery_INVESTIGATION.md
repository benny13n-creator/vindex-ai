# Project Sentinel — Phase 3: Failure Recovery Investigation

**Read-only investigation. No code changed.** Every claim below is grounded in a code citation
(`file:line`), obtained by tracing the actual execution path, not inferred from naming or comments.
Where a claim could not be verified against code in this pass, it is marked `UNVERIFIED` rather than
asserted.

Severity scale: **CRITICAL** (silent data loss or false success signal reaches the user) / **HIGH**
(real defect, detectable but unrecovered, could confuse a lawyer or corrupt case state) / **MEDIUM**
(real gap, low blast radius or rare trigger) / **LOW** (cosmetic / best-practice only).

---

## 1. OCR servis nedostupan

**Path traced**: `uploaded_doc/extractor.py::extract_pdf` (`extractor.py:168-201`) — OCR fallback wrapped
in `try/except ImportError` and `except Exception`, both branches call `_log_ocr_error(...)` and fall
through to `return "", True, False` (`extractor.py:194-201`).

- **Detekcija**: yes — `except Exception as e: logger.error(...); _log_ocr_error(...)` (`extractor.py:197-199`).
- **Korisnik obavešten**: yes, clearly — both call sites (`routers/dokument.py:206-216`,
  `api.py:4214-4218`) turn `is_scanned=True` into an explicit HTTP 422 with actionable Serbian-language
  guidance ("Ponovo skenirajte u 300 DPI...", "Koristite digitalni PDF..."). This is one of the
  best-handled failure paths in the codebase.
- **Retry**: none automatic, but the message tells the user exactly what manual retry looks like.
- **Rollback**: nothing to roll back — failure occurs before any DB/Pinecone write (`extract` runs
  before chunking/ingestion in both call sites).
- **Audit**: `_log_ocr_error()` writes somewhere (name implies a log/table) — **UNVERIFIED**: did not
  trace `_log_ocr_error`'s destination this pass; if it's log-only (not a queryable table), OCR failure
  rate is invisible to any dashboard.
- **Nastavak rada**: yes — user can re-upload with a better scan or paste text manually.

**Verdict: LOW.** Well-handled. Only gap: confirm `_log_ocr_error` is queryable, not just a log line.

---

## 2. LLM timeout (OpenAI/GPT poziv)

**Path traced**: every GPT call site in the critical flows uses one of two patterns:
(a) `@llm_retry` decorator (`shared/llm_retry.py` — not re-read this pass, established earlier this
engagement as "max 3 pokušaja sa exponential backoff-om za rate-limit/5xx/timeout/connection greške",
e.g. `services/case_pipeline.py:33-37`, `api.py:4494-4535`), and
(b) an explicit `asyncio.wait_for(..., timeout=N)` wrapper (e.g. `services/case_pipeline.py:254-265`
20s, `:387-397` 25s, `:465-479` 20s; `api.py:4411-4420` RAG 4s, `api.py:4447-4454` 6s/4s).

- **Detekcija**: yes, both layers — `llm_retry` catches and retries transient errors; `wait_for` raises
  `asyncio.TimeoutError` on hard timeout, always caught by an enclosing `except Exception`
  (e.g. `services/case_pipeline.py:325-328`, `api.py:4429-4432` catches `TimeoutError` specifically then
  falls through to generic `Exception`).
- **Korisnik obavešten**: **partial**. In `case_pipeline.py`, a step timeout becomes
  `StepResult(..., StepStatus.FAILED, str(exc)[:120])` (e.g. `:328`) — this IS surfaced in
  `PipelineResult.to_dict()`'s `koraci` list, but nothing in the product currently confirmed to render
  that list to the lawyer (Case Pipeline's 9-step output is written to `predmet_istorija` under
  `[Pipeline]` tag — surfacing depends on UI reading that tag, **UNVERIFIED** whether any current screen
  displays it). In `api.py`'s `predmet_upload_auto_analyze`, a procena/hronologija/metapodaci timeout is
  swallowed into `_pr`/`_hr`/`_meta` being an `Exception` object (`api.py:4537-4542`,
  `return_exceptions=True`), and the endpoint still returns HTTP 200 with `"auto_analyzed":
  bool(procena_tekst)` (`api.py:4700`) — the boolean IS correct/honest, but there is no single
  human-readable "3 of 3 AI calls failed" signal; a partial failure (e.g. procena succeeded,
  hronologija timed out) returns 200 with `hronologija_count: 0`, indistinguishable in the payload shape
  from "GPT correctly found zero deadlines in this document."
- **Retry**: automatic via `llm_retry` (up to 3x); no user-triggered re-run button confirmed for a fully
  failed step short of re-uploading the whole document.
- **Rollback**: N/A — GPT calls don't have side effects to roll back until their result is inserted, and
  those inserts are individually guarded (see partial-write findings in §9 below).
- **Audit**: no dedicated table of "AI call failed" events found; `logger.warning`/`_sentry_capture` only
  (`services/case_pipeline.py:326`, `:413`, `:495`). Sentry capture means this IS visible to an engineer
  monitoring Sentry, but not to the lawyer or via an in-product audit trail.
- **Nastavak rada**: yes for pipeline steps (idempotency markers mean a future retrigger — e.g. another
  document upload — will attempt the failed step again, since only SUCCESS markers block re-run,
  confirmed by reading `_step_strategija`/`_step_hcc`/`_step_risk_snapshot`'s idempotency checks, e.g.
  `case_pipeline.py:357-367`). But nothing in the read code re-triggers a failed pipeline automatically —
  it only re-runs if a NEW `PREDMET_KREIRAN`-adjacent event fires it again, and this event only fires
  once per case (§9).

**Verdict: MEDIUM.** Retry/backoff exists and steps are individually idempotent-resumable, but there is
no proactive re-trigger and no single honest "something failed" signal at the top-level API response —
only a same-shape 200 whether the AI genuinely found nothing or genuinely failed.

---

## 3. OpenAI greška (API error / exception, non-timeout)

Same code paths as §2 — `llm_retry` treats "rate-limit/5xx/timeout/connection greške" identically
(per its established doc comment); a hard 4xx (e.g. invalid request, content policy) is NOT in that
retry list and falls straight to the surrounding `except Exception`, same downstream handling as a
timeout (becomes a `FAILED` StepResult or an `Exception` object in a `gather(..., return_exceptions=True)`
tuple). No differentiated handling found for "OpenAI said no" vs. "OpenAI was unreachable" — both
degrade identically. **Verdict: MEDIUM**, same reasoning as §2 — the failure is contained and
non-corrupting, but invisible to the lawyer as a specific, actionable message.

---

## 4. Embedding servis nedostupan

**Path traced**: `app/services/retrieve.py::_ugradi_query` (`retrieve.py:605-611`) has **no try/except
of its own** — `_get_embeddings().embed_query(query)` (`:609`) raises straight through on failure.

- Callers differ sharply in how they treat this:
  - **Optional RAG enrichment** (law-hint retrieval, praksa injection during document upload):
    wrapped in `asyncio.wait_for(..., timeout=4-7s)` + broad `except Exception` at the call site
    (`api.py:4411-4420` → `except Exception: logger.warning("[P2.1] RAG greška — nastavljamo bez RAG")`;
    `api.py:4447-4467` similarly for praksa). These degrade gracefully — the document is still processed,
    just without law-citation enrichment, and the user is never told enrichment was skipped.
  - **`routers/search.py`**: confirmed this endpoint does NOT call `_ugradi_query` at all — it is a
    pure SQL/`ilike` keyword search across `predmeti/klijenti/dokumenti/zadaci/billing/hronologija/
    beleske` tables (`routers/search.py:38-231`), not a semantic/embedding search. So "Semantic Search"
    as a named critical flow in the Sentinel charter does not correspond to this endpoint — the
    embedding-backed retrieval lives in `app/services/retrieve.py`, consumed by Copilot/Precedenti/
    document-upload RAG, not by a standalone user-facing "search" screen. **This is a naming mismatch
    worth flagging to the founder**, not a reliability bug per se.
- **Korisnik obavešten**: no — every confirmed call site treats embedding failure as "silently proceed
  without this optional context." For flows where the embedding-backed retrieval IS the primary value
  (Copilot's precedent lookup, Precedenti page) — **UNVERIFIED this pass** whether those call sites also
  silently degrade to "no precedents found" (indistinguishable from a genuine empty result) or surface
  the error; given the consistent pattern elsewhere, silent degradation is the likely default and should
  be verified before beta.
- **Retry**: none found.
- **Audit**: none found beyond `logger.warning`.

**Verdict: HIGH.** Not because of data loss, but because of Beta Gate question 5 ("Može li kritična
greška ostati neprimećena?") — a lawyer relying on Copilot/Precedenti during an OpenAI/embedding outage
would see "no relevant precedents" and could reasonably read that as a real finding rather than a
service outage. Needs a explicit `degraded: true` / `napomena` field threaded through to the response
wherever embedding-backed retrieval silently falls back to empty.

---

## 5. Pinecone greška

**Path traced**: two ingestion call sites both distinguish "storage full" (429/quota) from other
errors, but diverge in what they do next:
- `routers/dokument.py:244-252` (tmp session upload): on non-429 error, re-raises as
  `HTTPException(500, ...)` — clean, visible failure, no partial DB write (this endpoint doesn't write
  to `predmet_dokumenti` at all, it's the ad-hoc Q&A flow).
- `api.py:4251-4277` (predmet-attached upload): on 429/storage-full, continues with `_pinecone_ok=False,
  count=0` and later stores the document with `"status": "sacuvano"` instead of `"indeksirano"`
  (`api.py:4304`) — **this is a correct, honest degraded-state marker**, visible in the document's own
  `status` field. On a non-429 Pinecone error, raises `HTTPException(500, ...)` (`api.py:4277`) — clean
  abort, occurs BEFORE the `predmet_dokumenti` insert (`:4279+`), so no orphan is created by this
  particular failure mode.
- **Read-path Pinecone failures** (querying, not ingesting) — e.g. `_pretraga_praksa`,
  `_retrieve_documents` — consistently wrapped in the same `wait_for` + broad `except Exception` →
  silent-degrade pattern as §4.

**Verdict: MEDIUM.** Write-path (ingestion) failure handling is good — distinguishes quota-exceeded
from hard failure, and hard failure aborts cleanly before any DB inconsistency. Read-path (query)
failure handling shares the same "invisible silent degrade" issue as §4.

---

## 6. Supabase greška (DB poziv otkazuje)

This is the most common failure mode in the codebase by volume, and handling is **inconsistent by
call-site convention**, not by a single policy:
- **User-facing single-entity reads** (e.g. `pred_row = supa.table("predmeti").select(...).single()`)
  — if Supabase raises, it is almost always uncaught at the local level and propagates to the
  **global exception handler** (`api.py:850-900`), which DOES catch it, logs via `logger.exception`, and
  returns a generic `{"greska": "Interna greška servera. Pokušajte ponovo.", "status": "error"}` at
  HTTP 500 (`api.py:895-900`). This is a real, non-silent failure — the user sees an error — but the
  message is generic and there's no differentiation between "your input was bad" and "the database is
  down" and no per-failure audit trail entry (only Redis errors and prompt-injection get a distinct
  branch in that handler, `api.py:883-892` / `:861-877`; a raw `postgrest.exceptions.APIError` falls
  into the final generic branch).
- **Background/fire-and-forget writes** (audit log inserts, decision_log inserts, proactive_alerts
  inserts) — near-universally wrapped in local `try/except Exception: logger.warning(...)` at the
  point of the `asyncio.create_task(...)` call itself, e.g. `api.py:3273-3284` (audit),
  `api.py:4319-4331` (audit), `services/event_bus.py:66-95` (`on_rok_kritican`, its own internal
  try/except). **Caveat repeatedly confirmed this pass**: wrapping `asyncio.create_task(coro())` in a
  `try/except` only catches errors thrown while *scheduling* the task (essentially never) — it does
  NOT catch exceptions raised *inside* the coroutine once it's running as an independent Task. The
  actual protection against DB errors happening inside these background writes must live inside the
  coroutine itself. Spot-checked: `log_action` (used at `api.py:3275`, `:4322`) — **UNVERIFIED this
  pass** whether `shared/audit_immutable.py::log_action` has its own internal try/except; if it does
  not, a Supabase outage during predmet-creation would produce an "Unhandled exception in Task" logged
  by asyncio's default handler, with **zero corresponding audit or alert**, and the founder's own audit
  trail — the very system meant to prove provenance for Phase 5/9 — would have a silent gap during
  exactly the kind of outage a Beta Gate is meant to catch. **Flagging as the single most important
  follow-up verification for whoever picks up Phase 5/9 work.**

**Verdict: HIGH** (pending the `log_action` internal-try/except verification above — if unverified
claim resolves to "no internal try/except," raise to **CRITICAL**, since it would mean the audit system
itself has a blind spot precisely when things are going wrong).

---

## 7. Event Bus prekid (handler baca izuzetak / proces se restartuje usred leta)

Already established this engagement (Project Nexus) and reconfirmed by re-reading `services/event_bus.py`
this pass:
- `EventBus.publish()` (`event_bus.py:209-231`) schedules each handler as an independent
  `loop.create_task(_run())`, where `_run()` has its own `try/except Exception: logger.error(...)`
  (`:219-223`) — so a handler THROWING is contained (logged, doesn't crash the caller or other
  handlers). This part is solid.
- A handler NOT throwing but the **process restarting mid-execution** (deploy, crash, OOM) is a
  different story per event type:
  - `DOCUMENT_JOB_ENQUEUED/COMPLETED/FAILED` and `GENOME_UPDATED` are written via direct DB insert into
    the durable `events` table (per `event_bus.py:40-50` comments) and recovered by
    `dispatch_pending_events()` (`:274-330`) on the next poll (`DispatchLoop`, 3s interval,
    `:352-392`) — a mid-flight crash loses nothing; the row is simply un-dispatched until the loop
    comes back.
  - `PREDMET_KREIRAN` is emitted exclusively via `emit()` → `bus.publish()`
    (`api.py:3263-3267`) — **pure in-memory, zero durable-outbox backing**. If the process restarts
    between the `emit()` call returning and `on_predmet_kreiran`'s `run_case_pipeline(...)` completing
    (`event_bus.py:98-107`), the entire 9-step Case Pipeline (deadlines, initial strategy, HCC briefing,
    risk snapshot, Copilot recommendation) silently never runs for that case, with **no record anywhere
    that it was supposed to** — the predmet row itself has no "pipeline_pending" flag, so nothing can
    detect this after the fact short of a human noticing the case has no Case Ready Score history.
  - `ROK_KRITICAN` and `HEALTH_SCORE_PROMENJEN` are likewise emitted via the in-memory `emit()` path
    only (confirmed by grep — no direct `events` table insert found for these two in this pass) — same
    exposure: a crash between emit and handler completion means a critical-deadline alert or a
    health-score-drop alert silently never reaches `proactive_alerts`.

**Verdict: CRITICAL** for `PREDMET_KREIRAN` (already tracked as NEX-004 from Project Nexus — this pass
independently reconfirms it and additionally identifies that `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN`
share the exact same non-durable exposure, which was not previously scoped as its own item). A crash at
the wrong instant means a lawyer never gets told about a critical deadline, with no compensating signal.

---

## 8. Transakcija prekinuta (multi-step DB write interrupted partway)

This codebase does not use explicit multi-table Postgres transactions from Python (every `.insert()`/
`.update()` call via the Supabase client is its own atomic single statement) — so "transaction
interrupted" in practice means "a *sequence* of independent inserts gets partway through." Concretely
confirmed instances:

- **`kreiraj_predmet`** (`api.py:3241-3286`): insert `predmeti` row (atomic, always fully succeeds or
  fully fails) → emit `PREDMET_KREIRAN` (try/except, warning-only on failure, §7 above) → fire-and-forget
  audit log (try/except around `create_task`, same caveat as §6). If the emit or audit step fails, the
  predmet row itself is completely fine (already committed) — the "interruption" only affects the two
  downstream side effects, and the endpoint still returns 200 with the new predmet
  (`api.py:3286`) regardless of whether either side effect succeeded. **This is a correct, defensible
  design** (the core resource write is atomic and always consistent) but means the RESPONSE gives the
  user zero signal about whether the automation chain behind their new case actually started.

- **`predmet_upload_auto_analyze`** (`api.py:4145-4704`) — the sequence is: Pinecone ingest (can fail
  hard → clean abort, §5) → `predmet_dokumenti` insert (`:4282-4315`, wrapped in
  `try/except Exception: logger.warning(...); _dok_id stays None`) → classify/genome-refresh
  (gated on `if _dok_id:`, correctly skipped if the insert failed) → **procena/hronologija/metapodaci
  GPT calls and their own separate inserts proceed unconditionally, NOT gated on `_dok_id`**
  (`:4489-4647` — no `if _dok_id` check anywhere in this block). **Confirmed CRITICAL finding**: if the
  `predmet_dokumenti` insert fails (line 4314's `except` branch) AFTER Pinecone ingestion already
  succeeded, the endpoint produces:
  1. A permanent Pinecone vector under the case's real `_owner_ns` namespace, tagged with this
     `predmet_id`, that will surface in ALL future RAG retrieval for this case (Copilot, precedent
     search, future document analysis) — indistinguishable from a properly-registered document.
  2. A `predmet_istorija` row tagged `[Auto-analiza] {filename}` (`:4573-4579`) containing a full GPT
     legal assessment of a document that **does not exist** in `predmet_dokumenti` — so the case's
     document list (whatever UI reads `predmet_dokumenti`) will never show this file, yet the case's
     history/timeline will contain an AI analysis that references it by name.
  3. Possibly `predmet_hronologija` rows (`:4622`) and a `[Metapodaci]` `predmet_istorija` row
     (`:4637-4643`) — same ghost-document exposure.
  4. The endpoint still returns HTTP 200 with `"auto_analyzed": true` and the full `procena_tekst`
     (`:4693-4704`) — **the user receives a complete success response for an upload the system failed
     to durably record as a document.**
  This is the textbook Beta Gate failure: "Može li korisnik dobiti lažnu potvrdu uspeha?" → **YES**,
  confirmed by code, not hypothetical.

**Verdict: CRITICAL.** This is the highest-value finding of this investigation — recommend gating the
entire procena/hronologija/metapodaci block on `if _dok_id:`, matching the pattern already correctly
used for classify/genome-refresh two blocks earlier in the same function.

---

## 9. Delimično upisan predmet ("novi predmet" flow specifically)

Covered above under §8 — the `predmeti` row itself is a single atomic insert and cannot be "partially"
written; the exposure is entirely in the *pipeline* that's supposed to follow it (§7's `PREDMET_KREIRAN`
durability gap) and, for document-carrying cases, the ghost-document scenario in §8. No additional
distinct finding beyond those two.

---

## 10. Oštećen PDF (corrupted/unparseable upload)

**Path traced**: `uploaded_doc/extractor.py::extract_pdf` (`:150`) calls `pypdf.PdfReader(str(path))`
and iterates `reader.pages` (`:156`) with **no try/except around PDF parsing itself** — only the OCR
fallback branch (triggered after successful parsing determines the PDF is scanned) has exception
handling (§1). `extract()` (`:301-311`) has no top-level catch-all either.

- **Detekcija**: indirect — a genuinely malformed PDF that makes `pypdf` raise (not the "scanned, no
  text" case, but an actual parse error) is NOT caught locally; it propagates to the endpoint
  (`routers/dokument.py:199` / `api.py:4204`, both only catch `DocumentSafetyLimitExceeded`
  specifically) and from there to the **global exception handler** (`api.py:850-900`), which DOES catch
  it and returns a clean HTTP 500.
- **Korisnik obavešten**: yes, but poorly — generic `"Interna greška servera. Pokušajte ponovo."`
  (`api.py:896`), which is materially worse guidance than the excellent, specific message given for the
  "scanned PDF" case (§1) even though both are "this file can't be read" from the user's perspective.
  "Pokušajte ponovo" (try again) is actively misleading for a corrupted file — retrying won't help.
- **Retry**: none meaningful — same file will fail the same way.
- **Rollback**: none needed — failure occurs before any DB/Pinecone write in both call sites.
- **Audit**: no — generic exceptions in the global handler are `logger.exception`'d only, no
  `audit_immutable` entry (contrast with the prompt-injection branch, which does log to
  `audit_immutable`, `api.py:867-875`).
- **Nastavak rada**: yes — user can try a different file.

**Verdict: MEDIUM.** Contained and non-corrupting (confirmed no partial write precedes this failure),
but the user-facing message quality regresses sharply compared to the adjacent, better-handled scanned-
PDF case, and there's no audit trail of how often this happens.

---

## 11. Konfliktni podaci (two documents / two AI passes produce contradictory facts)

**No contradiction-detection mechanism found for document-level facts within a single case.** Searched
`case_dna.py`, `evidence.py`/`evidence_graph.py`, and the broader `services/` tree for
konflikt/contradiction/protivrečnost handling:
- `services/knowledge_hygiene.py:196-207` has a "konfliktni" concept, but it operates on **Firm Brain
  cross-case learned factors** (e.g. two learned patterns about win rates disagreeing), not on
  documents within one case.
- `services/learning_engine.py:824-888` checks for `rag_kontradikcija` — but this is precedent-vs-
  precedent (does a newer court decision contradict an older one the strategy relies on), not
  document-vs-document within a case's own evidence.
- Each document uploaded to a case gets its own independent `[Auto-analiza]`, `[Metapodaci]`, and
  (if applicable) `predmet_hronologija` entries (`api.py:4571-4624`, `:4630-4643`) — there is no
  reconciliation step comparing, e.g., a monetary amount extracted from document A against one
  extracted from document B for the same case, or flagging that two documents disagree about a date or
  party name. Downstream consumers (Copilot, Case Genome, Briefing) that read from `predmet_istorija`
  would see both entries with no flag distinguishing "consistent corroborating evidence" from
  "contradictory evidence requiring a lawyer's judgment call."

**Verdict: HIGH.** This is a genuine, unaddressed gap directly on-charter for Sentinel's stated mission
("Može li AI doneti zaključak bez dokazivog porekla?" extends naturally to "can AI reasoning silently
paper over a contradiction its own inputs contain?"). Not CRITICAL only because no evidence was found
that any current flow actively surfaces a wrong number/date to the user as fact without any human
review step in between (all of these feed advisory text a lawyer reads, not an automated action) — but
this margin shrinks as more automation (Strategy Engine, Task Engine) is built on top of these facts.

---

## 12. Prekid mreže (client disconnects mid-request)

**No explicit `request.is_disconnected()` check found anywhere in the traced endpoints.** Starlette/
FastAPI's default behavior is to keep running the handler coroutine to completion even after the
client's TCP connection drops — meaning:
- All DB writes and Pinecone ingestion in `predmet_upload_auto_analyze` / `dokument_upload` complete
  server-side regardless of whether the browser is still there to receive the response. This is
  actually **good** for the "no work is lost" half of reliability.
- The flip side: no idempotency key is generated or accepted for uploads (`generate_session_id()`,
  `uploaded_doc/session.py`, produces a fresh random ID per call — confirmed by its use at
  `api.py:4246` and `routers/dokument.py:230` with no client-supplied nonce). If a lawyer's browser
  times out mid-upload and they resubmit (a very plausible real-world action), the second request
  runs the entire pipeline again independently: a second Pinecone ingestion, a second
  `predmet_dokumenti` row with a new `redni_broj` (`api.py:4283-4293` computes `_next_rn` fresh each
  call), a second full GPT procena/hronologija/metapodaci pass, and (if the case's genome-refresh
  background task from the first attempt is still in its 3-second `asyncio.sleep` window,
  `api.py:4346-4357`) potentially two overlapping Genome refreshes for the same case. The result is a
  duplicate document entry, doubled AI spend, and a doubled `predmet_istorija` history for what the
  lawyer experiences as "the upload failed once, so I tried again" — with no dedup by content hash
  (a `source_sha256` IS computed at `api.py:4238` but confirmed **not used anywhere for dedup**, only
  stored in `source_meta` sent to Pinecone).

**Verdict: MEDIUM-HIGH.** Not data loss, but a concrete duplicate-processing exposure matching Beta
Gate question 7 ("Može li isti događaj biti obrađen više puta?") — answer is **YES** for this specific,
very plausible retry-after-timeout scenario, with no idempotency guard despite the ingredients for one
(`source_sha256`) already being computed and discarded.

---

## Summary table

| # | Scenario | Verdict | Single most important fact |
|---|----------|---------|------------------------------|
| 1 | OCR unavailable | LOW | Best-handled failure path in the codebase — clear, actionable user message |
| 2 | LLM timeout | MEDIUM | Retried + idempotent-resumable, but no honest "AI call failed" signal in API response shape |
| 3 | OpenAI error (non-timeout) | MEDIUM | Same handling as timeout; no differentiation |
| 4 | Embedding service down | HIGH | Silent degrade to "no results" — indistinguishable from a genuine empty result |
| 5 | Pinecone error | MEDIUM | Write-path handles quota-vs-hard-failure correctly; read-path silently degrades |
| 6 | Supabase error | HIGH (pending verification, could be CRITICAL) | Fire-and-forget audit/decision-log writes may have zero exception handling *inside* the task — the audit system itself could have a blind spot exactly when things break |
| 7 | Event Bus interruption | CRITICAL | `PREDMET_KREIRAN`, `ROK_KRITICAN`, `HEALTH_SCORE_PROMENJEN` are all pure in-memory with zero durable-outbox backing — a crash at the wrong instant loses them silently |
| 8 | Transaction interrupted | CRITICAL | Document upload: if `predmet_dokumenti` insert fails after Pinecone succeeds, user still gets full HTTP 200 "success" with a real AI analysis of a document that doesn't exist in the case's document list |
| 9 | Partial predmet write | (same as #8) | `predmeti` insert itself is atomic; exposure is entirely downstream |
| 10 | Corrupted PDF | MEDIUM | Caught by global handler (not silent), but generic/misleading message vs. the excellent scanned-PDF message |
| 11 | Conflicting data | HIGH | No contradiction-detection exists for facts extracted from different documents in the same case |
| 12 | Network interruption | MEDIUM-HIGH | No upload idempotency despite `source_sha256` already being computed — retry-after-timeout duplicates the entire pipeline |

**Single most severe, most concretely proven finding: #8 (Transaction interrupted / partial write in
`predmet_upload_auto_analyze`, `api.py:4279-4704`).** It is the one scenario in this investigation with
a fully-traced, unambiguous code path proving a false success signal reaches the user (`"auto_analyzed":
true`, HTTP 200) while the system's own record of the document is missing — precisely the failure mode
Sentinel's Beta Gate is designed to catch. Recommended fix (not implemented this pass, per read-only
directive): gate the procena/hronologija/metapodaci block on the same `if _dok_id:` check already
correctly used two blocks earlier in the same function for classify/genome-refresh.
