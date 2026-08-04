# Canonical Migration Plan — Program Alpha, Phase 5

**Rule governing this plan**: *"Svaka migracija mora smanjiti složenost. Nikada povećati."* Every item
below states, explicitly, what complexity metric it reduces (implementation count, call-site count, or
authoritative-source count) — not "this looks cleaner," a checkable claim, verified in
`SYSTEM_HARDENING_REPORT.md`'s Phase 7 regression analysis after implementation.

**Sequencing rule**: cheapest/lowest-risk first, to build confidence and leave the highest-blast-radius
change (the correlation-ID middleware) for last among the items actually attempted, with the most
context and the most passing tests behind it by the time it's touched.

**Scope decision for this mission**: 15 findings identified in `DUPLICATE_DECISION_REPORT.md`. **8 were
scheduled for implementation this mission** (Tier 1, below) — mechanical, well-scoped, complexity-reducing,
each independently testable. **7 were deliberately deferred from the start** (Tier 2/3) — each requires
either a founder design decision or is large enough that attempting it within this mission's remaining
budget would risk the "one at a time, full regression check, revert if it gets more complicated"
discipline this mission's own charter demands.

**A further, 8th item (item 7, SMTP consolidation) was pulled back mid-implementation** — the diagnostic
fork's "well-precedented" characterization didn't survive contact with the actual code (see item 7's own
note below): 4 of the 5 call sites have genuine, non-duplicate functional differences (PDF attachments,
a raw-message-object signature, Reply-To + image attachments, plain-text fallback). Forcing them onto one
narrow signature would have either lost real capability or grown into a redesign — exactly the
complexity-*increasing* outcome this plan's own governing rule forbids. **This is the mission's own
"one at a time, revert if it gets more complicated" discipline working as intended, not a failure** —
caught before any half-migrated code was committed, not after. **7 of the original 8 Tier 1 items were
actually implemented.**

---

## Tier 1 — implemented this mission, in this order

| Order | Item | Complexity reduction claim | Risk |
|---|---|---|---|
| 1 | `routers/case_dna.py`'s 2 inline `uuid.uuid4()` → `new_correlation_id()` | 3 correlation-id-minting call sites → 1 | Trivial |
| 2 | `routers/gdpr.py`'s dead `_al.log(...)` call — remove | Deletes a call to a nonexistent method, silently swallowed by a bare except | Trivial |
| 3 | Embedding model — 5 ingestion routers import `EMBEDDING_MODEL` from `retrieve.py` instead of hardcoding the string | 6 independent string literals → 1 constant | Low — zero behavior change (values already identical) |
| 4 | Court Predictor — delete the second GPT call for `procenat`; derive it deterministically from `nivo` | 2 confidence-number implementations → 1; removes an entire GPT call site | Low-Medium — changes response shape's number source, not its presence |
| 5 | Retire `response_audit`/`app/services/audit_log.py::log_response` — remove all 5 call sites, the table stays but is no longer written | 2 audit mechanisms for the same data → 1; removes 5 unnecessary Supabase writes per relevant request | Low — confirmed write-only, zero readers |
| 6 | Canonical `create_proactive_alert()` — extract, migrate all 11 call sites | 11 independent insert implementations → 1 | Medium — most files touched, but mechanical, mirrors `log_action`'s already-proven shape |
| 7 | ~~Canonical `send_email()`~~ — **scope-corrected during implementation, see note below** | ~~5 → 1~~ | Was rated Medium, actually higher once the real code was read |
| 8 | Correlation-ID middleware — read/set `shared/ai_provenance.py`'s own request context instead of an independent `ContextVar` | 2 disconnected correlation-id systems → 1; closes the gap between internal traceability (4 prior missions' work) and the one externally-visible id | **Highest** — global middleware, every request; done last, with maximum confidence from items 1-7 behind it |

**Deliberately NOT attempted this mission (Tier 2 — real, scoped, but requires more than mechanical
migration)**:

| Item | Why deferred |
|---|---|
| Document classification unification (2 taxonomies → 1) | Requires a taxonomy decision (which of the 13-type/9-type vocabularies wins, or a mapping layer) and touches migration 074's CHECK constraint — a schema-adjacent decision, not purely mechanical |
| Entity extraction unification (2 pipelines → 1) | Same category, lower urgency (no active correctness bug today) |
| Firm memory unification (dead-but-complete vs. live-but-incomplete) | Real behavioral change to what Copilot sees (adds judge/client memory) — needs a explicit decision that this expanded context is wanted now, not silently changed as a side effect of a "cleanup" |
| Pinecone namespace registry | Needs a design decision (constants module vs. DB-backed registry) before implementation |
| "Critical deadline" threshold unification | Needs the `ccc.py` 30-day-window discrepancy resolved first (is it a different concept or a real inconsistency?) — a judgment call, not mechanical |
| Strategy Engine litigation % grounding | Already tracked as a founder decision (`KEYSTONE-004`) — a new deterministic-scoring design, not a canonicalization |
| Evidence auto-strength hardcode | Same category as above — needs a real per-fact confidence design |

Each deferred item is fully specified (root cause, evidence, recommended direction) in
`DUPLICATE_DECISION_REPORT.md` and tracked with a fresh ID in `ARCHITECTURAL_DEBT_REGISTER.md` — deferred,
not dropped.

---

## Per-item implementation notes

**Item 1-2**: pure deletions/substitutions, no new code paths, no test changes expected beyond confirming
existing tests still pass.

**Item 3**: change `model="text-embedding-3-large"` (5 files) to `model=EMBEDDING_MODEL` with an import
from `app.services.retrieve`. Zero behavior change today; the whole point is making a *future* model
change safe by construction.

**Item 4**: `court_predictor.py`'s `_calc_confidence_nivo()` already computes `nivo` from real counts.
Add a deterministic `nivo → procenat` band mapping (e.g., a fixed range per level) directly in that
function; delete the separate GPT-4o-mini call and its prompt. This is the clearest "delete code, don't
add reconciliation logic" case in this plan — Program Alpha's own principle 5 (Evidence Before Opinion)
is best satisfied by having one real author, not two authors plus a referee.

**Item 5**: delete `log_response`/`_write` from `app/services/audit_log.py` (keep the module for `_al.log`
callers if any remain after item 2 — confirm none do), remove the 5 call sites
(`drafting.py:559,603`, `api.py:2772,2920,3032`). Leave the `response_audit` table itself in place (a
schema drop is out of scope — Database Architect (08)'s veto domain, not this mission's), just stop
writing to it. Resolve `services/retention_service.py`'s `TABLES_EXCLUDED_PENDING_RETENTION_DECISION`
comment to state "retired, no longer written" rather than leaving it as an open question.

**Item 6**: new function `create_proactive_alert(user_id, tip, naslov, opis, urgentnost, predmet_id=None)`
in `shared/` (mirroring `shared/audit_immutable.py::log_action`'s shape: named parameters catch a typo'd
field at the Python level, internal retry + durable-failure-audit built in once). Migrate all 11 call
sites (`services/event_bus.py` ×3, `routers/case_dna.py` ×3 — this also fixes the confirmed
column-name bug, `routers/zakon_monitoring.py` ×2, `routers/morning_briefing.py` ×1 — absorbing
Phoenix's existing retry logic into the canonical function rather than losing it, `routers/smart_intake.py`
×1, `routers/workflow.py` ×1, `routers/zadaci.py` ×1).

**Item 7 — scope-corrected during implementation, not completed this mission**: the diagnostic fork
characterized this as "well-precedented" because `client_portal.py` already imports and reuses
`email_notif.py::_smtp_send`. Reading the actual code at the other 4 sites found this was optimistic:
`_smtp_send(to_addr, subject, html)`'s narrow signature only covers `client_portal.py`'s exact shape.
The other 4 have genuinely different, legitimate needs, not copy-paste laziness:
- `billing.py::_send_email_smtp` attaches a PDF invoice (`pdf_bytes`, `pdf_filename`) — a real parameter
  `_smtp_send` doesn't have.
- `morning_briefing.py::_smtp_send` (same name, different function — itself worth noting as a minor,
  separate naming collision) takes a pre-built `MIMEMultipart` message directly, not `(to_addr, subject,
  html)`.
- `support.py` sends `MIMEMultipart("mixed")` with an optional screenshot image attachment and a
  `Reply-To` header, to every address in `FOUNDER_EMAILS` in a loop with per-recipient error isolation.
- `waitlist.py` attaches both a plain-text AND an html part (`_smtp_send` only attaches html).

Forcing all 4 onto `_smtp_send`'s narrow signature would either silently drop real capability
(attachments, Reply-To, plain-text fallback) or require expanding that signature enough that it stops
being "removing a duplicate" and starts being a redesign — exactly the kind of complexity-*increasing*
change Program Alpha's own rule forbids ("Nikada povećati" złożoność). **Deliberately not implemented
this mission.** The real, narrower duplicate worth fixing here — noted for a future, dedicated pass — is
the SMTP *connection/auth boilerplate* (env-var reads + `ehlo()`/`starttls()`/`login()`), which genuinely
is copy-pasted 5 times with no functional difference, distinct from the *message construction*, which
correctly differs per caller and should stay caller-owned. See `ARCHITECTURAL_DEBT_REGISTER.md` for the
correctly-scoped follow-on item.

**Item 8**: `api.py`'s `correlation_id_middleware` currently mints via `str(_uuid.uuid4())` and stores in
its own `_correlation_id_var`. Change it to call `shared/ai_provenance.py::set_request_context()` (or
read `current_correlation_id()` if context is already set by that point in the request lifecycle) so the
value written to the `X-Correlation-ID` response header is the SAME value `audit_immutable`/
`ai_forensics`/`events` actually record. Requires careful ordering verification: does the middleware run
before or after `get_current_user`'s own context-setting code (`shared/deps.py:306`, `api.py:3128`)? If
the middleware runs first (typical FastAPI middleware ordering — before route dependencies), it should be
the one to CALL `set_request_context()`, and the auth-layer code should be updated to no longer
independently mint one if the middleware already has.

---

## Explicit non-goals for this mission (per the charter's own prohibition list)

- No new business logic introduced anywhere, including inside the canonical functions this plan creates —
  each one's logic is copied/consolidated from what already exists, not invented.
- No new helper created where a canonical service already exists to extend instead.
- No new Event type, no new AI pipeline, no new API route.
- No "good enough" partial migrations left in the code — every Tier 1 item either fully replaces all its
  call sites or is not counted as done.
