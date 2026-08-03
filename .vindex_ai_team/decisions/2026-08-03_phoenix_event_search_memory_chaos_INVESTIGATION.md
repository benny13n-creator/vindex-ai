# Project Phoenix — Event Bus / Search / Memory Graph / Notification Chaos Investigation

**Scope**: read-only, adversarial. Every claim below is a direct code trace (file:line), not an
assumption. No fixes implemented.

---

## 1. Event Bus — lost/duplicate/delayed event, consumer crash, retry exhaustion

**Headline finding (CRITICAL, previously undiscovered): the durable-outbox retry mechanism cannot
actually retry handler failures — it only retries infrastructure-level dispatch failures.**

Traced `services/event_bus.py::dispatch_pending_events` (`:349-406`) exactly:

```python
try:
    await bus.publish_async(event)          # :388
    await _mark_dispatched(supa, row_id)    # :389
    dispatched += 1
except Exception as exc:                    # :391 — only reachable if publish_async ITSELF raises
    errored += 1
    ... dispatch_attempts += 1, last_error = str(exc) ...
```

`bus.publish_async` (`:294-299`):
```python
async def publish_async(self, event: Event) -> None:
    handlers = self._handlers.get(event.type, [])
    if not handlers:
        return
    await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
```

`return_exceptions=True` means `asyncio.gather` **captures every handler's exception into its result
list and never raises them** — `await bus.publish_async(event)` at `dispatch_pending_events:388`
**cannot fail due to a handler throwing**, full stop. Combined with the fact that every registered
handler (`on_genome_updated`, `on_predmet_kreiran`, `on_rok_kritican`, `on_health_score_promenjen`,
`on_document_job_failed`) ALSO wraps its own body in `try/except Exception: logger.warning(...)`
(confirmed for all 5, `event_bus.py:73-238`) — there are now **two independent layers that swallow
handler failures**, and neither surfaces anything to `dispatch_pending_events`'s own except block.

**Consequence, proven by code, not hypothesis**: if `on_genome_updated` has a bug and always throws
for a specific Genome payload (or any handler fails for any reason), `dispatch_pending_events` takes
the **success** path every time — `_mark_dispatched` runs, `dispatched_at` is set, `dispatched += 1`.
The event is marked permanently handled after exactly ONE attempt, regardless of whether the handler
actually did anything. **`dispatch_attempts`/`last_error` (the columns migration 073 added specifically
for this purpose) are dead code for the failure class they were built for** — they only increment if
`bus.publish_async` itself raises (never happens, per above) or if `_mark_dispatched`'s own UPDATE
fails (a genuine Supabase-down scenario, not a handler bug).

This means: **there is no retry exhaustion problem in the sense of "retries forever" — the actual
problem is the opposite and worse: a permanently-broken handler retries ZERO times and is silently
marked successful.** For `GENOME_UPDATED` specifically, this means a bug in `on_genome_updated` would
leave the Genome update UNAUDITED (no `audit_immutable` row despite `genome_refresh` being in
`AUDITABLE_ACTIONS`) with **zero trace that anything went wrong** beyond a `logger.warning` line no
dashboard reads. For `PREDMET_KREIRAN`, the same mechanism would leave the Case Pipeline silently
un-run for that predmet, permanently, marked as "dispatched."

**Detection**: partial — a log line exists, but nothing polls/alerts on it. **Retry**: effectively
none for handler failures (contradicts the module's own docstring claim, `event_bus.py:350-352`,
"greška na jednom redu ne sme da blokira ostale u batch-u" — true, but only because the retry path for
that exact scenario is unreachable). **Rollback**: N/A (nothing to roll back, but nothing to
complete either). **Recovery**: none — a human would have to notice a specific predmet has no Genome/
pipeline output and manually re-trigger. **Audit**: none for the failure itself. **User notification**:
none. **Consistent final state**: technically yes (no orphan/duplicate rows), but a `dispatched_at`
timestamp now falsely certifies work that never happened — this is itself a data-integrity problem
(the outbox's own bookkeeping is wrong). **Idempotent**: moot — it never re-runs.

`ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` (Sentinel's `SENT-001`, still open): confirmed unchanged —
still `emit()`'d purely in-process (`routers/matter_intel.py`), no durable-outbox row at all, so this
specific dispatch-loop bug doesn't even apply to them (they're not in the durable path yet) — their own,
separately-documented non-durability gap stands as-is.

**Severity: CRITICAL.** This is a structural flaw in the reliability mechanism this whole engagement
has repeatedly relied on as "the proven durable pattern" (Sentinel's PREDMET_KREIRAN fix, Genome's own
template status) — worth fixing directly in Project Phoenix's Phase 3, not just documenting.

---

## 2. Search — index unavailable, embedding failure, partial indexing

**`routers/search.py::global_search`** (`:232-283`) — confirmed NOT semantic/embedding-based (matches
Sentinel's prior finding): all 7 per-type searches (`_search_predmeti`, `_search_klijenti`, etc.) are
plain Postgres `ilike`/`or_` queries, no Pinecone/embedding call anywhere in this file.

```python
results = await asyncio.gather(*tasks.values(), return_exceptions=True)
grouped: dict[str, list] = {}
for tip, res in zip(tasks.keys(), results):
    if isinstance(res, Exception):
        logger.warning("[SEARCH] tip=%s greška: %s", tip, res)
        grouped[tip] = []
    else:
        grouped[tip] = res
```
(`:273-280`) — confirmed: if e.g. `_search_dokumenti` throws (a real DB error on that one table), it
is caught, logged, and **silently converted to an empty list, structurally indistinguishable from "no
matching documents."** No `degraded`/`greska` flag is added anywhere in the returned payload
(`:282-283`, the response is just `{"q", "ukupno", **grouped}`). A lawyer searching for a document
during a `predmet_dokumenti` outage sees "0 results" with no way to know the system failed rather than
genuinely finding nothing. **Detection**: log-only. **User notification**: none — this is a real,
code-confirmed silent failure. **Severity: HIGH** (same class Sentinel already flagged for other
RAG-degrade paths, now confirmed for the actual live search endpoint too).

**Pinecone-backed RAG retrieval** (`app/services/retrieve.py`, used by Copilot/Strategy/Genome/Court
Predictor): traced all 7 Court Predictor GPT-calling endpoints' RAG call sites specifically (Mission
Migration's own recent touch points) — **all 7 correctly wrap their RAG call in a local try/except that
degrades to an empty context block** (`routers/court_predictor.py::_rag_praksa_blok:104-127` — "Nikad
ne baca" per its own docstring, confirmed; and the other 4 endpoints' direct `retrieve_sudska_praksa`
calls at `:641`, `:787`, `:948`, and confidence_check's own RAG step are each individually wrapped in
`try/except Exception: _sentry_capture(...); logger.warning(...)`, confirmed by direct read). **No
uncaught-exception risk found here** — this part of the hypothesis in the directive did NOT hold up;
reporting the negative result explicitly rather than forcing a finding. **Severity: none (confirmed
correct)**.

---

## 3. Memory Graph — graph update failure, context unavailable

**`routers/memory_graph.py::dodaj_vezu`** (`:97-138`): a single atomic INSERT (one row represents both
directions of the edge via `from_type`/`from_id`/`to_type`/`to_id` fields — **no bidirectional dual-row
write exists**, so the "partial edge write" risk hypothesized in the directive does not apply to this
schema; reporting this as a ruled-out hypothesis, not a confirmed finding). On failure: caught,
`raise HTTPException(status_code=500, detail=str(e))` (`:138`) — **clean, visible failure**, no silent
swallow, no partial state possible (single-row atomicity). **Detection**: yes (500 to caller).
**Rollback**: N/A (atomic single insert). **Recovery**: user can retry the same POST (idempotent in
effect — worst case a duplicate edge row, not a corruption). **Audit**: none (not in
`AUDITABLE_ACTIONS`, but also not a Mission Ledger/Atlas/Migration target — Memory Graph is a
confirmed-inert feature per Project Nexus, out of scope here). **Severity: LOW** — this endpoint is
correctly, simply built; its real problem (documented already, unrelated to failure recovery) is that
almost nothing calls it automatically.

`graph_upit`/`graf_preporuka` (`:210-293`, `:296-404`): both wrap their GPT calls in
`except HTTPException: raise` + `except Exception: _sentry_capture(e); raise HTTPException(500, ...)`
— clean, visible failure, correctly re-raises rather than swallowing. **Severity: none (confirmed
correct)**.

---

## 4. Notification — email failure, alert queue failure, background worker crash

**Two distinct paths, different risk levels:**

**On-demand** (`routers/morning_briefing.py::send_briefing_email`, `:402-421`): calls
`_pošalji_briefing_email`, which **never raises** — returns `bool` (`:351-368`, catches its own SMTP
exception and returns `False`). The endpoint correctly forwards this: `return {"ok": sent, ...}`
(`:421`) — **the failure IS surfaced to the caller**, assuming the frontend actually checks `ok`
(not verified this pass — frontend behavior out of scope for a backend chaos investigation).
**Severity: LOW** if frontend checks `ok`, otherwise a silent-UI gap — flagged, not confirmed either
way.

**Nightly cron path** (`routers/morning_briefing.py`, the per-user loop around `:740-776`) — **two
separate, sequential failure points with different severities**:
1. **Alert INSERT** (`:741-756`) — wrapped in `try/except Exception: logger.debug(...)`. If this
   fails, the underlying critical condition (e.g., a critical deadline) is captured NOWHERE — no
   retry, no dead-letter, **debug-level log only** (easy to miss even by an engineer watching logs,
   since `debug` is typically filtered out of production log levels). **This is the actual "lost
   alert" scenario the directive asked about — confirmed CRITICAL**: if this specific insert fails,
   the lawyer has no durable record a critical condition was ever detected, and no compensating
   signal exists anywhere (not in `audit_immutable`, not in a separate dead-letter table, nothing).
2. **Email send** (`:758-771`) — wrapped in `try/except Exception: logger.error(...)`, no retry, no
   dead-letter. **Severity: MEDIUM, not CRITICAL** — unlike (1), the underlying alert is ALREADY
   durably in `proactive_alerts` by the time email is attempted (step 1 runs first and independently),
   so an email failure here means "the lawyer isn't proactively pinged" but NOT "the alert is lost" —
   they will still see it if they open the app. A real gap (no retry/dead-letter for a transient SMTP
   hiccup), but bounded, not data-loss.

**Severity summary for Notification**: Alert-insert failure = **CRITICAL** (true silent data loss,
debug-only log). Email-send failure = **MEDIUM** (degraded delivery, not data loss). On-demand email
= **LOW** (correctly surfaced to caller, contingent on unverified frontend behavior).

---

## Summary table

| Area | Scenario | Detection | Retry | Recovery | Audit | User notice | Consistent | Idempotent | Severity |
|---|---|---|---|---|---|---|---|---|---|
| Event Bus | Handler failure marked as dispatched success | Log-only | **None (bug, not by design)** | None | None | None | Technically yes, but bookkeeping lies | N/A | **CRITICAL** |
| Search | One `ilike` sub-search fails | Log-only | None | N/A | None | **None — silent empty result** | Yes | Yes (read-only) | HIGH |
| Search | RAG/Pinecone failure in Court Predictor | Yes, per-endpoint | None (graceful degrade) | N/A | None | Implicit (context just thinner) | Yes | Yes | None (confirmed correct) |
| Memory Graph | Edge insert fails | Yes (500) | None | User can retry | None (out of scope) | Yes (HTTP 500) | Yes | Effectively yes | LOW |
| Notification | Nightly alert INSERT fails | **Debug-log only** | None | None | None | **None — true silent loss** | Yes (no partial row) | N/A | **CRITICAL** |
| Notification | Nightly email send fails | Error-log | None | Alert still visible in-app | None | None (but underlying alert survives) | Yes | N/A | MEDIUM |
| Notification | On-demand email send fails | Yes (`ok: false`) | None | User can retry | None | Yes, if frontend checks `ok` | Yes | Yes | LOW |

## Single most severe finding (for coordinator)

**The durable-outbox retry mechanism (`dispatch_pending_events`) cannot retry handler failures at
all** — `bus.publish_async`'s `asyncio.gather(..., return_exceptions=True)` swallows every handler
exception before it ever reaches the surrounding try/except that's supposed to increment
`dispatch_attempts`/`last_error` and enable retry. A permanently-failing `on_genome_updated` or
`on_predmet_kreiran` handler gets marked `dispatched_at` (success) after exactly one silent failure —
the Genome update or Case Pipeline trigger is lost forever with zero durable trace, and the very
retry-count columns this system was built around (migration 073) never actually increment for this
failure class. This directly contradicts the "GENOME_UPDATED is the fully-durable template event"
conclusion every prior mission (Sentinel, Ledger, Migration) relied on — it's durable against
*process crashes*, but not against *handler bugs*, and no prior investigation traced far enough into
`publish_async`'s `return_exceptions=True` to catch this. Second-most-severe: nightly alert-insert
failures are debug-logged only, with zero durable trace of the underlying critical condition — genuine
silent data loss for the exact scenario proactive_alerts exists to prevent.
