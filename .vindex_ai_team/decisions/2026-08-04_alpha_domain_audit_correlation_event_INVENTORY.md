# Program Alpha — Domain Inventory: Audit / Correlation ID / Event Handling / Notification

Read-only investigation. No code, git, or fix changes made.

## Decision table

| Business decision | Canonical location | # implementations found | Status |
|---|---|---|---|
| "What happened, who did it, when" (business audit trail) | `shared/audit_immutable.py` (hash-chained, `AUDITABLE_ACTIONS` allowlist) | **2 live tables**: `audit_immutable` (canonical) + `response_audit` (legacy, write-only, see below) | Duplicate, one is dead weight |
| Request correlation ID | **2 fully independent mechanisms**, never linked | 2 | **Critical — worst finding in this domain** |
| Correlation ID *minting* (fresh UUID) | `shared/ai_provenance.py::new_correlation_id()` | 1 canonical + 2 ad hoc inline `uuid.uuid4()` calls | Duplicate, low-severity |
| Business event distribution | `services/event_bus.py` (`emit()` in-process + durable outbox) | 1 canonical mechanism, 2 known non-durable exceptions (pre-existing, unchanged) | Known, tracked (`SENT-001`) |
| Outbound email sending (SMTP) | **None — no canonical function exists** | **5 independent implementations** | Duplicate, moderate severity |
| "Verify the current user from a request" | `shared/deps.py::get_current_user` | 1 canonical + 1 separate legacy path (`api.py::_require_auth`), both correctly wired into the same correlation-context setter | Adjacent finding, flagged for the security-domain fork, not deep-dived here |

---

## Finding 1 (Critical) — Two fully independent, unlinked correlation-ID systems

**This directly contradicts the parent investigation's assumption that `shared/ai_provenance.py::new_correlation_id()` is the sole correlation-id source. It is not.**

`api.py:986-996` defines and installs its own, completely separate mechanism:
```python
_correlation_id_var: _cv.ContextVar[str] = _cv.ContextVar("correlation_id", default="")

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(_uuid.uuid4())
    _correlation_id_var.set(cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response
```
This is genuine, global, first-class HTTP middleware — it runs on **every single request** and is the
value returned to the client in the `X-Correlation-ID` response header (the one piece of correlation
infrastructure actually exposed outside the process).

Meanwhile, `shared/ai_provenance.py`'s own request-scoped context (the one Mission Ledger built and every
subsequent mission wired `log_action`/Event Bus/`case_context()` into) is set from a **completely
different code path** — not middleware, but inline inside the two `get_current_user`-shaped auth
functions (`shared/deps.py:306`, `api.py:3128`).

**Confirmed by direct read: `_correlation_id_var` (the middleware's value) is set once and never read
anywhere else in the codebase** — `grep -rn "_correlation_id_var"` returns exactly 2 lines, both inside
the middleware itself (the declaration and the `.set()` call). It has no consumer. Its only observable
effect is the `X-Correlation-ID` response header sent to the client.

**The practical consequence**: if a lawyer, support engineer, or the founder takes the `X-Correlation-ID`
value from an API response (or a browser network tab) and tries to use it to look up "what happened for
this request" in `audit_immutable`, `ai_forensics`, or `events` — **it will never match anything**,
because every one of those tables is stamped with `ai_provenance.py`'s independently-generated id, not the
middleware's. The single piece of correlation infrastructure actually visible outside the backend is
disconnected from the correlation infrastructure 4 prior missions (Ledger, Migration, Phoenix, Keystone)
spent significant effort wiring end-to-end internally. Replay Coverage, as externally observable via the
one header a client can actually see, is currently 0% — even though Keystone measured ~100% at the
internal, code-level correlation dimension.

**Why this is exactly a Program Alpha "eliminate the pattern, not the symptom" case**: patching this by
making the middleware read from `ai_provenance.py` instead of minting its own value would fix the symptom.
The actual pattern that allowed this to happen — a new correlation concept being introduced via a global
FastAPI middleware, completely independently of the existing `shared/ai_provenance.py` module, with no
registry anywhere stating "this is the one correlation mechanism, nothing else may mint one" — is what
needs to not be possible again.

## Finding 2 (Medium) — Two ad hoc inline UUID mints bypass the canonical minting function

`routers/case_dna.py:534,536`:
```python
correlation_id = current_correlation_id() or str(uuid.uuid4())   # line 534
...
correlation_id = str(uuid.uuid4())                                 # line 536, except-branch fallback
```
Functionally harmless (produces an equally valid UUID) but architecturally inconsistent — the canonical
`new_correlation_id()` exists specifically so there is one function to change if minting logic ever needs
to evolve (e.g., adding a prefix, a timestamp component, structured logging metadata). This file bypasses
it twice.

## Finding 3 (Medium-High) — `response_audit` / `app/services/audit_log.py::log_response` is legacy,
## write-only, duplicate-purpose weight, actively still being written to

`response_audit` captures `latency_ms`, `confidence`, `response_hash`, `top_article`/`top_law`,
`query_hash` — per-AI-call quality/observability metadata. `ai_forensics` (Mission Atlas's canonical
provenance capture, confirmed via `security/ai_forensics.py:56,68,127,149,203,205,252,263`) captures
`latency_ms`, `confidence_score`, `response_hash`, and more — the same conceptual fields, for the same
class of call.

**Confirmed via `grep -rn "response_audit"` across the entire codebase: `response_audit` is
write-only.** Its only reader anywhere is `test_audit_b1.py`, a standalone manual verification script at
the repo root, not part of the application. `services/retention_service.py`'s own comments independently
confirm it: *"response_audit -- NEMA migraciju u migrations/ (samo u legacy audit_log.py)"* and it sits in
`TABLES_EXCLUDED_PENDING_RETENTION_DECISION` — already flagged by a prior mission as an unresolved
question, not something this fork is newly discovering, but confirmed still true and still unresolved.

**Still actively written to today**: `routers/drafting.py:559,603` and `api.py:2772,2920,3032` all still
call `_al.log_response(...)` on every request to those endpoints — meaning this dead-end table keeps
growing, with real per-request cost (an extra Supabase write via `asyncio.create_task`), for data nothing
reads.

## Finding 4 (Low-Medium, but a live bug, not just duplication) — `gdpr.py`'s "dual audit write" is illusory

`routers/gdpr.py:200-206`:
```python
try:
    from app.services import audit_log as _al
    _al.log(uid, "gdpr_account_deleted", {...})
except Exception:
    pass
```
**`app/services/audit_log.py` has no `log` function or attribute — only `log_response` and internal
helpers** (confirmed by reading the full 130-line file: `_get_supa`, `_sha`, `log_response`, `_write`, and
nothing else). This call raises `AttributeError` on every single execution, silently swallowed by the
bare `except Exception: pass`. **This is not actually a dual-write architecture — it is a single, working
write to `audit_immutable`'s `gdpr_erasure` action, plus dead code that has never once succeeded**,
disguised as a second audit mechanism by the swallow-all except block. A previous fork (Mission Olympus's
backtest) characterized this as "writes to two mechanisms" — that characterization is incorrect; only one
write has ever actually occurred.

## Finding 5 (Medium) — 5 independent SMTP-sending implementations, no canonical email service

`grep -rln "smtplib" routers/` finds SMTP code in `billing.py`, `email_notif.py`, `morning_briefing.py`,
`support.py`, `waitlist.py` — **5 separate `smtplib.SMTP(...)` blocks**, each its own function, no shared
canonical sender (`client_portal.py` is the one correct exception — it imports and reuses
`email_notif.py::_smtp_send` rather than reimplementing). All 5 correctly read the same
`EMAIL_SMTP_HOST`/`EMAIL_SMTP_PORT` env vars (naming is consistent — one thing that *didn't* drift), but
each has its own timeout value, hardcoded independently: **15s (billing), 15s (email_notif), 20s
(morning_briefing), 15s (support), 12s (waitlist)** — a small, concrete, visible symptom of the same
underlying pattern (no canonical `send_email()` function anyone is required to use), and each presumably
duplicates its own MIME-construction and error-handling logic (not exhaustively diffed here, but the
timeout inconsistency alone proves independent implementation, not shared code).

## Event Bus — no new findings, prior missions' state confirmed unchanged

`grep`'d all in-process `emit()` call sites: only `routers/matter_intel.py`'s `HEALTH_SCORE_PROMENJEN` and
`ROK_KRITICAN` remain non-durable (`SENT-001`, tracked, unchanged since Sentinel/Keystone). No new
non-durable emit path has appeared. `routers/case_dna.py`'s `GENOME_UPDATED` correctly, deliberately
avoids both `emit()` and a second in-process publish, per its own comment, to prevent double-handling —
confirmed sound, not a new finding.

## Source-of-truth verdict for this domain

**"What happened, who did it, when" — NOT single-sourced.** Two tables (`audit_immutable`,
`response_audit`) both persist records for overlapping AI-call-quality concepts, with `response_audit`
contributing nothing anything reads. **Recommendation: retire `app/services/audit_log.py::log_response`
and the `response_audit` table entirely** — `ai_forensics` (Atlas's provenance capture, already active on
every one of `response_audit`'s 5 call sites via the global AI wrapper) is the correct, actually-read,
actively-maintained canonical mechanism for this exact data. This is not a case where the two serve
genuinely distinct purposes — the field overlap is close to total, and one side has zero readers.

**"What correlation ID identifies this request" — NOT single-sourced, and the externally-visible one is
the disconnected one.** This is the domain's highest-priority finding.

---

## Recommendations, prioritized

1. **(Highest priority) Unify the two correlation-ID systems.** `api.py`'s `correlation_id_middleware`
   should read/set `shared/ai_provenance.py`'s own request context (or the module should be extended so
   the middleware calls into it directly) instead of maintaining a second, disconnected ContextVar — so
   the `X-Correlation-ID` a client actually sees matches what `audit_immutable`/`ai_forensics`/`events`
   actually recorded. This is the single highest-value canonicalization in this entire domain: it doesn't
   just remove duplicate code, it closes the gap between what this engagement has spent 4 missions proving
   is internally traceable and what is actually, externally, provably traceable.
2. **Retire `response_audit`/`log_response`.** Remove the 5 call sites (`drafting.py` ×2, `api.py` ×3),
   delete `app/services/audit_log.py::log_response`/`_write`, resolve
   `TABLES_EXCLUDED_PENDING_RETENTION_DECISION`'s `response_audit` entry as "table retired, not merely
   excluded." Confirm nothing else depends on it first (the grep above found nothing, but a final check
   belongs to whoever implements this).
3. **Fix or remove `gdpr.py`'s dead `_al.log(...)` call.** Either implement a real `log()` function on
   `audit_log.py` if a genuinely distinct purpose is wanted (not recommended, given Finding 3's
   retirement recommendation), or simply delete the dead `try/except`-wrapped call — it currently does
   nothing but burn a stack-unwind on every account deletion.
4. **Consolidate the 5 SMTP-sending implementations into one canonical `send_email()`.**
   `routers/email_notif.py::_smtp_send` is the best candidate to promote to canonical (already reused
   correctly by `client_portal.py`) — migrate `billing.py`, `morning_briefing.py`, `support.py`,
   `waitlist.py` onto it.
5. **(Lower priority) Route `case_dna.py`'s 2 inline `uuid.uuid4()` fallbacks through
   `new_correlation_id()`.** Trivial, low-risk, but closes the "more than one way to mint an id" gap
   completely.
