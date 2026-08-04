# Architectural Debt Register — Program Alpha, Phase 3/5 Output

Every finding this mission identified but did not implement, with a real reason (a founder decision
needed, a scope that would risk the "one at a time, revert if more complicated" discipline, or a design
question larger than a canonicalization). Deferred, not dropped — each item below is fully specified so a
future mission can pick it up without re-deriving the diagnosis.

---

## ALPHA-001 — `_require_auth`'s request context is inert due to `asyncio.to_thread` isolation (NEW, Critical-adjacent)

**Found while implementing** the correlation-ID middleware unification (Tier 1, item 8), not by the
original diagnostic pass — a genuine example of implementation work surfacing a deeper issue than the
initial audit found.

**The bug**: `api.py::_require_auth` is a plain `def` (synchronous) function, invoked at all 11 of its
call sites as `await asyncio.to_thread(_require_auth, authorization)`. It calls
`shared/ai_provenance.py::set_request_context(user_id=..., correlation_id=...)` internally — but a
`contextvars` mutation made *inside* a `to_thread`-offloaded function does not propagate back to the
awaiting coroutine. **Confirmed empirically** (not just from documentation) with a minimal reproduction:

```python
cv = contextvars.ContextVar('test', default='DEFAULT')
def sync_setter():
    cv.set('SET_IN_THREAD')
async def main():
    await asyncio.to_thread(sync_setter)
    print(cv.get())  # prints 'DEFAULT', not 'SET_IN_THREAD'
```

**Consequence**: for the 11 endpoints using `_require_auth` (not `shared/deps.py::get_current_user`,
which is a genuine `async def` FastAPI dependency with no thread hop and does NOT have this problem),
`user_id` is never actually stamped into the request-scoped context any downstream `case_context()`/
`log_action()`/`current_correlation_id()` call would read. The correlation-ID fix (Tier 1 item 8) still
provides real value here — the middleware, which runs in the main coroutine *before* the thread hop,
already sets the correlation_id — but `user_id`-in-context specifically remains a gap for these 11
endpoints.

**Why not fixed this pass**: the correct fix is converting `_require_auth` to `async def` and removing
the `to_thread` offload (matching `get_current_user`'s already-correct shape) — but this touches 11 call
sites, and requires first confirming `_verify_token`/JWT verification inside it isn't genuinely CPU-heavy
enough to justify the thread offload in the first place (not verified this mission). A rushed conversion
risks either blocking the event loop on JWT verification (if it turns out to be non-trivial CPU work) or
introducing a subtle bug across 11 endpoints in an already-large mission — exactly the "one at a time,
revert if it gets more complicated" discipline this mission's own charter warns against violating.

**Recommendation for the fix, when scoped**: (1) benchmark `_verify_token`'s actual CPU cost; (2) if
negligible, convert `_require_auth` to `async def`, remove the `to_thread` wrapper at all 11 call sites,
verify with a real request that `current_correlation_id()`/`user_id`-in-context is now correct
end-to-end; (3) if not negligible, keep the thread offload but have `_require_auth` **return** the
correlation_id/user_id so the calling coroutine can explicitly call `set_request_context()` itself after
the thread returns — a less elegant but safe alternative that doesn't touch the CPU/threading tradeoff.

**Severity**: real, but scale-independent (per `SYSTEM_HARDENING_REPORT.md`'s Phase 8 analysis — this
gap is identical at 10 users and 50,000 predmeta, not a volume-triggered risk). Not blocking for the items
actually shipped this mission.

---

## ALPHA-002 — SMTP consolidation, correctly abandoned mid-implementation

Originally scoped as Tier 1 item 7 (consolidate 5 independent SMTP-sending implementations into one
`send_email()`, promoting `email_notif.py::_smtp_send`). Pulled back after reading the actual code: 4 of
the 5 call sites have genuine, non-duplicate functional differences —

- `billing.py::_send_email_smtp` attaches a PDF invoice (`pdf_bytes`, `pdf_filename`).
- `morning_briefing.py::_smtp_send` (a same-named, different function) takes a pre-built `MIMEMultipart`
  object directly, not `(to_addr, subject, html)`.
- `support.py` sends `MIMEMultipart("mixed")` with an optional screenshot attachment and a `Reply-To`
  header, looped across every `FOUNDER_EMAILS` address with per-recipient error isolation.
- `waitlist.py` attaches both a plain-text AND an html part (`_smtp_send` only attaches html).

**The correctly-scoped fix, for a future pass**: extract only the SMTP *connection/authentication*
boilerplate (env-var reads + `ehlo()`/`starttls()`/`login()`) into one shared low-level primitive (e.g.
`shared/smtp.py::get_smtp_connection()`), leaving each caller's message *construction* — which correctly
differs per caller — untouched. This is a real, still-open duplicate (5 independent copies of identical
connection/auth code), just narrower than "one `send_email()` for everything." Also requires reconciling
5 different hardcoded timeout values (15s/15s/20s/15s/12s) into one canonical value or a parameter — an
explicit decision point, not something to silently average.

**Severity**: Low-Medium. Real duplication, no active correctness bug, no data-loss risk.

---

## ALPHA-003 — Document classification: two independent AI taxonomies (Critical-tier, largest deferred item)

`shared/intake_classify.py::classify()` (13-type English taxonomy, migration 074's CHECK constraint) and
`routers/evidence.py::_klasifikuj_dokument()` (9-type Serbian taxonomy, prompt-only, no DB constraint)
both answer "what type of document is this?" via two separate GPT calls. A prior mission (Lawyer Zero,
LZ-002, 2026-08-03) found intake's classifier wrote the wrong vocabulary to `predmet_dokumenti.tip_dokaza`
and patched it by having Evidence's classifier run SECOND and overwrite the field — the actual cause (two
classifiers) was never removed, only its symptom papered over with call-order sequencing.

**Why this matters under this mission's own stress-test framing**: the "second write wins" pattern
currently works only because both writes happen in a predictable sequence inside one finalize flow. At
real concurrency (this mission's own 10,000-predmeta/100-parallel-AI-analyses/20-worker stress-test
scenario), nothing structurally guarantees that ordering holds.

**Recommended direction**: retire `intake_classify.py`'s independent classification role; keep its cheap
heuristic keyword pre-filter (`classify_heuristic`) as a genuine optimization, but have it feed INTO
Evidence's classifier as the one canonical decision-maker, not maintain a parallel taxonomy.

**Why not fixed this mission**: requires a real taxonomy decision (which vocabulary wins, or a mapping
layer) and touches migration 074's schema constraint — a design decision, not a mechanical migration.

**Severity**: Critical-tier per the original domain audit, but correctly deferred — this is exactly the
kind of item Program Alpha's own "revert if it gets more complicated" discipline says should NOT be
rushed into an already-large mission.

---

## ALPHA-004 — Entity extraction: two overlapping pipelines (lower priority than ALPHA-003)

`shared/intake_extract.py::extract_all_entities()` (regex-first, LLM-fallback, 8 typed entities) and
`routers/evidence.py`'s `ai_tags` (unstructured LLM call, no regex pre-check, no per-field confidence)
extract overlapping information (parties, court, amounts, dates) via two independent mechanisms. Unlike
ALPHA-003, these write to *different* tables/fields — no active overwrite conflict today, only duplicated
AI cost and two places a future engineer must remember to update in sync.

**Recommended direction**: fold Evidence's `ai_tags` extraction into a call to intake's canonical
`extract_all_entities()`, keeping only genuinely Evidence-specific fields as an addition.

**Severity**: Medium. Real duplication, no active correctness bug.

---

## ALPHA-005 — Firm memory for AI: dead-but-more-capable vs. live-but-cruder implementation (Critical-tier)

`api.py::_fetch_firm_memory_context` (live, called from Copilot) queries only `memory_entries` and
`partner_profiles`. `routers/firm_memory.py::kontekst_za_ai` (its own docstring claims it's "called from
the AI pipeline" — confirmed FALSE, zero callers found anywhere) is strictly MORE complete: it also reads
`judge_patterns` and `client_memory` (judge win-rate, client settlement preferences, risk profile) that
the live version never touches at all.

**Consequence**: Copilot's actual AI answers never benefit from judge/client institutional memory, even
though a more complete retrieval implementation for exactly that already exists in the codebase, unused.

**Recommended direction**: make `routers/firm_memory.py::kontekst_za_ai` (or its logic) the actual
canonical implementation, and have `api.py::_fetch_firm_memory_context` call it instead of reimplementing
retrieval inline.

**Why not fixed this mission**: this is a real BEHAVIORAL CHANGE (Copilot's context would meaningfully
expand to include judge/client memory it currently never sees) — not a pure refactor, and Program Alpha's
own charter forbids adding capability disguised as cleanup. Needs an explicit founder go-ahead that this
expanded context is wanted now, not a silent side effect of a "duplicate removal."

**Severity**: Critical-tier (two authors of "what does the AI know about this firm's history"), but
correctly gated on a product decision, not a mechanical migration.

---

## ALPHA-006 — No canonical Pinecone namespace registry (Medium)

Query side (`app/services/retrieve.py`) hardcodes 3 namespace constants. Ingest side has 2 more,
independent, un-synchronized sources: `routers/auto_discovery.py` accepts admin-supplied free-text
namespaces with zero validation; `routers/batch_ingest.py` validates against its own separate
`ALLOWED_NAMESPACES` set. **Real risk**: a document can be successfully ingested into a namespace nothing
ever queries — a "write success, permanently orphaned data" defect class, trivially reachable via
`auto_discovery.py`'s free-text field.

**Why not fixed this mission**: needs a design decision (a shared constants module vs. a DB-backed
registry) before implementation, not a one-line fix.

---

## ALPHA-007 — "Critical deadline" threshold duplicated with 2 different values (Medium)

At least 6 files independently inline the "how many days until a deadline is critical" threshold, with
2 different actual values in active use (3-day and 7-day windows in different files; `routers/ccc.py` also
has a 30-day window whose relationship to the others — a deliberately different concept, or a real
inconsistency — was not resolved this mission).

**Why not fixed this mission**: needs the `ccc.py` 30-day discrepancy investigated and resolved first — a
judgment call, not a mechanical extraction.

---

## Carried forward, unchanged from prior missions (not re-investigated this mission's scope)

- **`KEYSTONE-004`** — Strategy Engine's litigation win-probability percentage remains raw, ungrounded
  LLM output with zero backend validation (Court Predictor's OWN analogous bug was fixed this mission —
  Strategy Engine's is architecturally similar but larger in scope, since Strategy Engine has no
  deterministic scoring layer at all to derive a percentage from, unlike Court Predictor's `nivo`).
- **`SENT-001`** — `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` non-durable Event Bus emission, still open,
  unchanged. **Reconfirmed from a new angle by this mission's own governance review** (Mission Olympus's
  Reliability & Chaos Agent, finding F-1): `on_rok_kritican`/`on_health_score_promenjen` are invoked
  solely via the in-process `emit()`/`bus.publish()` path (`routers/matter_intel.py`), whose own `_run()`
  wrapper catches every handler exception and only logs it — never re-raises further. This mission
  initially added a `raise` to these handlers on a `create_proactive_alert()` failure, with a comment
  incorrectly claiming it would reach `dispatch_pending_events()`'s outer retry/dead-letter mechanism —
  corrected in-code (`services/event_bus.py`) once the review caught it. The `raise` itself was kept
  (harmless, consistent with every other handler's re-raise-after-log discipline, and becomes correct the
  day `SENT-001` is finally closed) but the comment no longer overstates what it currently does. Only
  `on_document_job_failed` (genuinely durable-outbox-connected via `fail_intake_job`'s `events` insert) has
  a `raise` that reaches the real dead-letter mechanism today.
- **`KEYSTONE-002`** — Genome → Strategy/Risk/Tasks connectivity gap; Memory Graph fully isolated
  (Firm Brain corrected to "has one narrow real consumer," see the Mission Olympus backtest correction).

## Housekeeping note

Court Predictor's confidence percentage evidence-scoring formula (`_procenat_iz_score`) intentionally
never claims 0% or 100% certainty (bounded 20-80%) — a deliberate, conservative design choice for a legal
confidence estimate, not an oversight; worth preserving in any future related work.
