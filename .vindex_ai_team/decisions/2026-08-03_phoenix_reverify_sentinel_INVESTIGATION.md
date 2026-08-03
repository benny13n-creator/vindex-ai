# Project Phoenix — Adversarial Re-verification of Sentinel's Failure-Recovery Investigation

**Read-only. No code changed.** Adversarial mandate: every claim below was an attempt to prove the
system broken, not to confirm prior work. Where an attack didn't pan out, that is stated explicitly as
a verified-safe result, not silently omitted.

Context: Sentinel's original 12-scenario investigation
(`.vindex_ai_team/decisions/2026-08-03_sentinel_failure_recovery_INVESTIGATION.md`) was written BEFORE
Mission Ledger (correlation_id unification across Event Bus/Audit/AI Provenance) and Mission Migration
(case_context()/log_action wiring into ~19 more AI call sites) existed. Re-verified against current code.

---

## Scenario-by-scenario re-verification

### §1 OCR unavailable — **STILL ACCURATE**
No code touched by Ledger/Migration affects this path. Not re-traced in depth (out of this fork's
scope); no reason to believe it changed.

### §2 LLM timeout — **STILL ACCURATE, one new data point**
`api.py`'s upload endpoint's 3 parallel GPT calls (procena/hronologija/metapodaci) are now wrapped in
`with _ai_case_ctx(predmet_id=..., document_id=_dok_id, module_name="api_upload", ...)` (`api.py:4485-4495`),
added by Mission Migration. Confirmed this wrap does **not** change the `return_exceptions=True`
gather semantics at all — a single sub-call timing out still doesn't affect the others, and the
"no single honest top-level failure signal" gap Sentinel found is **unchanged**. The new `case_context()`
wrap only affects what gets written to `ai_forensics`/audit for calls that succeed; it does not add or
remove any error-handling.

### §3 OpenAI error (non-timeout) — **STILL ACCURATE**
Same reasoning as §2 — unaffected by any of the 3 later missions.

### §4 Embedding service down — **STILL ACCURATE**
`app/services/retrieve.py::_ugradi_query` untouched by Ledger/Migration/Atlas's embedding-provenance
patch (Atlas added *capture*, not error handling, to `Embeddings.create`). Confirmed:
`shared/ai_client.py::_tracked_embed`/`_tracked_aembed` (Atlas's embedding wrapper) re-raises on failure
after capturing provenance (`shared/ai_client.py` — the `except Exception as exc: _capture_embedding_provenance(...); raise`
pattern) — so an embedding failure still propagates exactly as before; Atlas's wrapper adds an
observability side-channel, not a behavior change. Sentinel's "silent degrade to no results" finding is
**unchanged and confirmed still true** — Mission Ledger/Migration didn't touch any RAG caller's
exception-handling.

### §5 Pinecone error — **STILL ACCURATE**
Write-path/read-path handling (`api.py`'s Pinecone ingestion block, still at the same relative position
before the `predmet_dokumenti` insert) is untouched by the 3 later missions. Confirmed unchanged.

### §6 Supabase error — **RESOLVED FAVORABLY (was "HIGH, pending verification, could be CRITICAL")**
Sentinel's own report flagged this as its single most important unverified item: *does
`shared/audit_immutable.py::log_action` have its own internal try/except, or would a Supabase outage
during a fire-and-forget `asyncio.create_task(log_action(...))` produce an "Unhandled exception in Task"
with zero audit trace?*

**Directly verified now**: `log_action` (`shared/audit_immutable.py:103-140`) wraps its entire body,
including the call to `_build_and_insert`, in `try/except Exception as e: logger.warning(...); return None`
(lines 135-140). `log_action_sync` has the identical structure (lines 143-165). **This means
`asyncio.create_task(log_action(...))` can never produce an unhandled-task-exception, regardless of
what Supabase does** — the coroutine itself always returns cleanly (`None` on failure), it just doesn't
raise. Sentinel's own worst-case hypothesis (the audit system going silent exactly when things break)
does not materialize. **Verdict downgraded from "HIGH, could escalate to CRITICAL" to confirmed-safe.**
This resolves cleanly — Sentinel was right to flag it as unverified rather than assume either way, and
the resolution is favorable.

One residual, genuinely new observation from this pass (see "New findings" below): the *fallback logic*
Mission Ledger added on top of this (the "try wide with correlation_id, fall back narrow" idiom) is
itself correctly exception-safe in `shared/audit_immutable.py`, but the SAME idiom was copied into 2
other files with a **less careful** fallback condition — see Finding P-1.

### §7 Event Bus interruption — **PARTIALLY STALE — the CRITICAL half was fixed, confirmed in current code**
Sentinel's own report was written mid-investigation, before Sentinel's own implementation phase. Directly
re-verified against current code:
- **`PREDMET_KREIRAN`**: `api.py::kreiraj_predmet` (`api.py:3175-3192`) now writes DIRECTLY to the durable
  `events` table (`_get_supa().table("events").insert(...)`) instead of calling `emit()`/`bus.publish()`
  in-process. **Confirmed fixed** — matches the in-code comment's own claim. The crash-loses-the-pipeline
  exposure Sentinel found no longer exists for this event type.
- **`ROK_KRITICAN` / `HEALTH_SCORE_PROMENJEN`**: confirmed **STILL** emitted exclusively via the in-memory
  `emit()` path (`services/event_bus.py::emit`, called from `routers/matter_intel.py`) — no durable outbox
  producer exists for either. **Sentinel's finding for these two is STILL ACCURATE, unfixed.** This
  matches Sentinel's own subsequent scoping (`SENT-001`, deferred pending a dedup-safety check on
  `matter_intel.py`'s alert logic before converting to durable outbox) — correctly still open, not a
  regression, not silently dropped.

### §8 / §9 Transaction interrupted / ghost document — **STALE — the CRITICAL finding was fixed, confirmed in current code**
Directly re-verified: `api.py:4252-4256` now has `if not _dok_id: raise HTTPException(500, "Dokument je
otpremljen, ali nije uspešno sačuvan u sistemu — analiza nije pokrenuta. Pokušajte ponovo.")`,
placed immediately after the `predmet_dokumenti` insert attempt and BEFORE any of the
audit/classify/genome-refresh/GPT-analysis blocks. **Confirmed: the false-success path Sentinel proved
no longer exists.** The endpoint now fails loudly instead. One **explicitly documented, not hidden**
residual gap: the Pinecone vector ingested before the DB insert failure is not cleaned up (comment at
`api.py:4249-4251` states this plainly) — this is a known, named, deliberately-deferred item, not a new
silent gap.

### §10 Corrupted PDF — **STILL ACCURATE**
`uploaded_doc/extractor.py` untouched by the 3 later missions. Generic error message ("Pokušajte
ponovo") for a genuinely corrupt file is unchanged.

### §11 Conflicting data — **STILL ACCURATE**
No contradiction-detection mechanism was added by Ledger/Atlas/Migration (correctly out of scope for
all 3 — none claimed to address this). Confirmed still absent.

### §12 Network interruption / upload retry duplication — **STILL ACCURATE**
`source_sha256` is still computed (`api.py`, same relative location) and still not used for dedup.
Unchanged by the 3 later missions. **One new, related observation**: Mission Ledger's design means a
duplicate retry-after-timeout upload would now ALSO produce a duplicate `ai_forensics` row and a
duplicate `dokument_ai_analiza_complete` audit entry, correctly correlation-linked to whichever of the
two duplicate HTTP requests triggered them — i.e., the NEW audit/provenance infrastructure faithfully
records the duplicate as two distinct, individually well-formed events, rather than silently merging or
corrupting anything. This is arguably a **positive** side-finding: the duplicate-processing exposure
Sentinel found is unchanged in kind, but it is now MORE observable after the fact (a human/tool querying
`ai_forensics`/`audit_immutable` by `predmet_id` would see 2 clearly-timestamped, clearly-costed AI
analysis events for what should have been one upload) — this doesn't fix the duplication, but it makes
the duplication detectable where it previously would have been invisible except via `predmet_dokumenti`
row count. Noting this as context for whoever picks up `SENT-008`, not claiming it as a fix.

---

## New findings — failure modes in infrastructure that didn't exist when Sentinel wrote its report

### Finding P-1 (MEDIUM-LOW) — Inconsistent fallback-narrowing across 4 near-identical "try wide, fall back narrow" blocks

Mission Ledger/Atlas introduced the same idiom in 4 places to handle pre-migration schema absence
(`correlation_id` column not yet added): attempt an insert WITH the new column, and on failure, retry
WITHOUT it.

| Location | Fallback condition |
|---|---|
| `shared/audit_immutable.py::_build_and_insert` (`:269-274`) | **Narrow** — `_is_missing_column_error(exc)` (Postgres 42703 / "does not exist" specifically) |
| `routers/case_dna.py::_emit_genome_event` (`:555-560`) | **Broad** — bare `except Exception:` |
| `api.py::kreiraj_predmet`'s durable event insert (`:3185-3190`) | **Broad** — bare `except Exception:` |
| `security/ai_forensics.py::log_provenance_from_wrapper` (`:293-297`) | **Broad** — bare `except Exception:` |

**Why this matters, concretely**: `shared/audit_immutable.py`'s narrow version exists specifically
because a broad catch was proven (by a real, pre-existing regression test,
`test_build_and_insert_does_not_retry_on_unrelated_errors`) to silently perform an extra, pointless retry
attempt on a genuinely unrelated error (e.g. a connection reset) instead of propagating immediately. The
other 3 locations have the exact same latent behavior: on ANY exception from the wide attempt — not just
a missing column — they will attempt a second insert (without `correlation_id`) before giving up. Since
all 4 are wrapped in an outer fail-soft handler that never lets this reach the calling business logic,
**this is not a crash risk or data-loss risk** — the practical impact is limited to: (a) one wasted extra
DB round-trip during a genuine outage in 3 of 4 fire-and-forget writes, and (b) a real, undocumented
behavioral inconsistency between 4 copies of "the same idiom," which is exactly the kind of thing that
erodes confidence in "is this actually one canonical pattern or four accidental variations" — directly
relevant to Phoenix's own observability/consistency mandate.

**Severity: MEDIUM-LOW.** Not a functional defect (every path already fails soft), but a genuine,
concrete inconsistency worth normalizing — recommend reusing `shared/audit_immutable.py::
_is_missing_column_error` (already exported, already correct) in the other 3 call sites rather than
each maintaining its own bare-except copy of the same idea.

### Finding P-2 (VERIFIED SAFE, not a bug) — contextvar leakage across concurrent requests/tasks

Attempted to break: does a fire-and-forget `asyncio.create_task(log_action(...))` risk reading a
correlation_id from a *different*, later request if it outlives its parent? **No** — `asyncio.create_task`
captures a `contextvars.Context` snapshot at creation time (Python's documented behavior since 3.7); a
concurrently-running or later request's `set_request_context()` call mutates only *that other request's*
own context, never the already-copied one inside an in-flight background task. Each HTTP request already
runs in its own ASGI-spawned Task/Context from the start. Confirmed correct, no finding.

### Finding P-3 (VERIFIED SAFE, not a bug) — `case_context()` isolation across `asyncio.gather`+`asyncio.to_thread` siblings

Attempted to break: does wrapping 3 concurrent `asyncio.to_thread(...)` calls (api.py's upload
procena/hronologija/metapodaci) in ONE shared `with case_context(...):` risk any of the 3 sibling threads
seeing a stale or cross-contaminated context if they interleave? **No** — `asyncio.to_thread` internally
copies the calling context via `contextvars.copy_context()` at the moment each `to_thread(...)` call is
made (all 3 calls are made synchronously, back-to-back, while still inside the `with` block, before any
`await` yields control) — so all 3 worker threads get an identical, correct, independent snapshot of the
same `case_context()` values. Confirmed correct, no finding.

### Finding P-4 (VERIFIED SAFE, not a bug) — `log_action_sync` in a `to_thread` worker with no event loop

Directly re-checked `routers/evidence.py::klasifikuj_i_sacuvaj` (the function Mission Migration's own
report flagged as having caught a real `asyncio.create_task`-in-worker-thread bug during its own testing,
fixed by switching to `log_action_sync`). Confirmed the fix is real and correctly applied
(`routers/evidence.py:179-186` calls `log_action_sync(...)` as a plain synchronous call, not wrapped in
`asyncio.create_task`). Further stress-tested per this fork's own directive: if `_get_supa()` itself
raises inside `_build_and_insert` (called synchronously from `log_action_sync`), the exception is caught
by `log_action_sync`'s own `try/except Exception as e: logger.warning(...); return None` (`shared/
audit_immutable.py:161-165`) — confirmed fail-soft, cannot propagate and crash the classification job.
No finding — Mission Migration's fix holds up under adversarial re-checking.

### Finding P-5 (LOW, observational) — all 21 `log_action` call sites confirmed genuinely non-blocking

Grepped every `log_action(` call site across `routers/copilot.py`, `routers/court_predictor.py`,
`routers/drafting.py`, `routers/evidence.py`, `routers/strategija.py`, `routers/zadaci.py`,
`routers/morning_briefing.py`, `api.py`, and `services/event_bus.py`: **21 of 22 total call sites** use
`asyncio.create_task(log_action(...))` (structurally non-blocking by construction — `create_task`
schedules and returns immediately). The **1 exception**, `services/event_bus.py:216`
(`on_genome_updated`), correctly `await`s `log_action(...)` directly — but `on_genome_updated` itself
only ever runs as a fire-and-forget event-handler task (via `bus.publish_async()` inside the durable
dispatch poller, or `bus.publish()`'s own `loop.create_task(_run())` wrapper), never synchronously in the
path of a user-facing HTTP response. **No blocking risk found anywhere.**

---

## Summary for the coordinator

Of Sentinel's 12 original scenarios: **2 were CRITICAL findings that are now confirmed FIXED in current
code** (§7's `PREDMET_KREIRAN` durability, §8's upload false-success/ghost-document) — both fixes
directly verified by reading the current file:line, not assumed from commit messages. **1 was resolved
favorably** (§6's Supabase/audit-blind-spot worry — `log_action` is confirmed internally exception-safe).
**9 of 12 are STILL ACCURATE, unchanged** — Ledger/Atlas/Migration correctly didn't touch failure-recovery
behavior outside the AI-provenance/audit domain, matching their own stated scope. **1 new inconsistency**
(Finding P-1) was found in the NEW correlation_id infrastructure itself — real but low-severity (fail-soft
either way, just inconsistent narrowing). **3 additional adversarial attempts against the new
infrastructure (P-2/P-3/P-4) did not find a bug** — reported as verified-safe rather than invented.

**Single most severe NEW finding** (something Sentinel could not have known about, since the code didn't
exist yet): **Finding P-1** — 3 of the 4 new "try wide correlation_id insert, fall back narrow" blocks
(`case_dna.py::_emit_genome_event`, `api.py::kreiraj_predmet`, `security/ai_forensics.py::
log_provenance_from_wrapper`) use a bare `except Exception:` fallback instead of the narrowly-scoped
`_is_missing_column_error()` check that `shared/audit_immutable.py` already correctly uses — the same
class of over-broad-except-clause risk this codebase has hit before (proven by a real regression test
during Mission Ledger's own work), just not yet normalized across all 4 copies. Not a crash or
data-loss risk (everything here is already wrapped in an outer fail-soft handler) — a code-consistency
finding, not a reliability incident.
