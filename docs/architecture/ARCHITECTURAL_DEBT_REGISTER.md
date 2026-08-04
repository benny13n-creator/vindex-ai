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

---

# Program Beta (Masterprompt 002, 2026-08-04) — Deferred Items

**ID namespace note (self-correction, found by Olympus Faza 10 governance review, Metrics Guardian):**
this mission's docs originally used `BETA-001` through `BETA-005` for the items below. Those IDs were
already in live use in `.vindex_ai_team/MISSION_BOARD.md` as Founder's Master Prompt IDs for 5 unrelated
missions the day before (Zero-Touch Case, Invisible Features, Lawyer Day, Beta Readiness Audit, Expose-
Complete-Polish). Renamed to `PROGBETA-00X` across all Program Beta docs to eliminate the collision.
**Lesson for future missions**: check `MISSION_BOARD.md`'s existing ID usage before minting a new backlog
prefix, not just `ARCHITECTURAL_DEBT_REGISTER.md`'s.

## PROGBETA-001 — Strategy Engine's 4 independent litigation-percentage generators (Critical-tier, supersedes `KEYSTONE-004`)

Updates and supersedes the `KEYSTONE-004` entry above with a materially more precise diagnosis: NOT one
raw-LLM percentage but **4 independent, unreconciled generators** (`/litigation` prose, `/sudija-v2` ×2
prose, `/v2/analiza` JSON, `/kompletna-analiza` JSON) — worse than Court Predictor's pre-fix state (2
unreconciled authors). Court Predictor's proven pattern (deterministic score → level + %) is directly
portable in principle, but Strategy Engine is missing 2 of its 4 input signals entirely: no VKS-specific
search call anywhere in `strategija.py`, no `case_patterns` firm-history query (used by 6 other files
platform-wide, never here) keyed on `tip_postupka`. RAG hit count IS already fetched but unscored.

**Recommended direction**: a new `shared/litigation_confidence.py::compute_litigation_score()`, modeled on
`_calc_confidence_nivo()`/`_procenat_iz_score()`, consumed by all 4 call sites. Requires first adding the
2 missing signal calls (VKS search, `case_patterns` query) — this is why it's Phase 7 work, not a
same-session patch to one endpoint (which would leave 3 other unreconciled generators in place).

**Severity**: Critical — highest-priority open item from Program Beta.

---

## PROGBETA-002 — RAG provenance threading across ~15+ call sites (Medium-High)

`app/services/retrieve.py`'s `retrieval_meta` (izvori, confidence) is returned by every call but never
threaded into `shared/ai_provenance.py::case_context()`'s already-existing, already-connected
`retrieval_query`/`retrieved_context_ids` parameters, by any of its ~15+ callers (Copilot, Strategy Engine,
LRE, Drafting). Confirmed independently 3 times same day (Program Alpha's own domain audit + 2 Program
Beta forks). Mechanism exists end-to-end (`ai_provenance.py` → `ai_client.py` → `security/ai_forensics.py`)
— pure wiring, not new infrastructure.

**Why not fixed this mission**: 15+ heterogeneous call sites carry real risk of inconsistent application
(a missed site) if rushed inside an already-large mission — deserves its own fully-tested pass.

**Severity**: Medium-High — single highest-leverage fix in the platform (benefits every RAG-based AI
feature at once), but wide blast radius if done carelessly.

---

## PROGBETA-003 — `quality_gate` citation-verification generalization for Strategy Engine/Genome (Medium)

`services/quality_gate.py`'s `_extract_article_citations`/`_verify_citation` already operate on arbitrary
text (not Drafting-specific by construction) and verify every legal-article citation against the real
indexed corpus. Neither Strategy Engine (9 endpoints, zero backend citation verification, purely
prompt-instructed) nor Genome routes through it or an equivalent.

**Why not fixed this mission**: portability was identified as plausible but NOT confirmed by reading the
actual integration code at 2 new call sites — needs that confirmation before wiring, not an assumption.

**Severity**: Medium — reuse candidate, not a new-mechanism build.

---

## PROGBETA-004 — Genome `heatmap`/`najslabija_tacka.kriticnost` deterministic scoring (Medium)

Unlike `compute_snaga_score()` (which reuses already-extracted, case-specific `snaga_faktori`), these 2
fields have no equivalent already-extracted per-dimension factor list to aggregate from.

**Why not fixed this mission**: would require first redesigning Genome's extraction schema to return
explicit per-dimension factors, THEN writing a `compute_*()` over them — a schema redesign, not just a
post-processor addition. Larger than it looked from the initial fork finding.

**Severity**: Medium — same defect class as `compute_snaga_score` was built to fix, unaddressed here.

---

## PROGBETA-005 — Copilot akcija handlers fact/inference schema separation (Medium)

`_handle_akcija_rok` and siblings extract `datum_iso` (fact) and `vaznost` (inference/classification) via
one undifferentiated GPT call, written to `predmet_hronologija` with no source-marker distinguishing the
two. Requires a JSON schema change across 4 handler functions, not a prompt tweak.

**Severity**: Medium — real Facts≠Inference violation, but writes to a system-of-record table (higher
stakes than Strategy Engine's un-persisted prose), should not be rushed.

---

## PROGBETA-006 — Evidence Vault `snaga` fix makes a previously-dead `risk_engine.py` branch reachable, no backfill (NEW, found by Olympus Faza 10 governance review, Evidence Integrity)

Program Beta's own `_snaga_iz_lokacije()` fix (implemented this mission) makes `services/risk_engine.py`'s
`"Jaka"` branch (`jaka_pct >= 0.5` → `rizik_score -= 20`) reachable for the first time at scale — before
this fix, `snaga` was hardcoded `"srednja"` for every AI-classified row, so that branch was structurally
unreachable for the dominant (auto-classification) path. Existing `predmet_dokazi` rows written before this
deploy stay frozen at the old default; only new rows can reach `"jaka"`. Consequence: a predmet's displayed
`procesni_rizik`/`health_score` can shift purely from vintage (old vs. new documents), not from a real
change in the case.

**Why not fixed this mission**: a backfill (recompute `snaga` for all existing `predmet_dokazi` rows via
`_lociraj_tvrdnju` against already-stored document text) is a genuine migration-shaped operation — its own
bounded task, not an extension of this mission's 3 canonicalizations.

**Recommended direction**: either run a one-time backfill job, or explicitly accept and document the
vintage-skew as a known, bounded transitional artifact (resolves naturally as documents get re-uploaded/
re-classified over time).

**Severity**: Medium — real, but bounded and self-healing over time; not a correctness bug, a consistency
transition.

---

## PROGBETA-007 — `compare_docs`'s `dok_res` query has no explicit ordering; response labels assume alignment with `n1`/`n2` (NEW, found by Olympus Faza 10 governance review, AI Grounding; PRE-EXISTING, not introduced by Program Beta)

`routers/case_dna.py::compare_docs`: the `predmet_dokumenti.in_("redni_broj", [n1, n2])` query has no
`.order()`; `parts` (sent to the LLM) are built from a locally re-sorted copy, but the response's
`dok_1`/`dok_2` labels use the raw, unsorted `docs[0]`/`docs[1]`. Supabase gives no ordering guarantee on
`.in_()` — the UI could theoretically label the wrong document under the wrong DOK number. Does not affect
`validate_dok_reference()`'s correctness (set membership is order-independent), but undermines the
"known documents" trust story Program Beta's evidence-check work builds on.

**Why not fixed this mission**: pre-existing (not part of this session's 3 changes), flagged as non-blocking
by the reviewing agent — fixing it means touching query/sort logic outside this mission's AI-reasoning
scope.

**Severity**: Low-Medium — real but narrow (2-document endpoint, single sort call away from a fix).

---

## PROGBETA-008 — `DokazReq.snaga` has no enum/`Literal` constraint (NEW, found by Olympus Faza 10 governance review, Evidence Integrity; PRE-EXISTING, adjacent, now more consequential)

`routers/evidence.py`'s manual-entry `DokazReq.snaga: str = "srednja"` accepts any string — an arbitrary
value silently falls out of `risk_engine.py::snaga_count`'s bucketing (neither `"jaka"` nor otherwise
recognized). Pre-existing gap, not introduced by Program Beta, but more consequential now that `snaga` is a
genuinely load-bearing risk-scoring input (see `PROGBETA-006`).

**Severity**: Low — narrow (manual-entry path only), simple fix (`Literal["jaka","srednja","slaba"]`) when
picked up.

---

# Program Gamma (Masterprompt 003, 2026-08-04) — Deferred Items

Founder's Master Prompt 003: "Canonical Decision Engine — Eliminate Entire Classes of Decision
Fragmentation." Full context, contracts, and the design sketch for the largest item below:
`docs/architecture/CANONICAL_DECISION_ENGINE.md`, `DECISION_CONSISTENCY_REPORT.md`.

## GAMMA-001 — "Next recommended action" has no single owner: 18 independent, unreconciled producers (Critical, needs a founder product decision)

The single largest finding of this multi-mission session. **Methodology, self-corrected after Olympus Faza
10 governance review (Metrics Guardian found the mission's own original "12+" claim was internally
inconsistent — 3 different sub-totals across 3 documents that didn't sum to 12, and an independent tally
from the raw fork evidence suggested materially more).** The table below is the single reconciled
enumeration; every other document (`CANONICAL_DECISION_ENGINE.md`, `DECISION_REGISTRY.md`) now cites this
count rather than restating its own breakdown.

| # | Producer | Field/output | Source fork(s) |
|---|---|---|---|
| 1 | Case Genome | `strategija`/`nedostaje`/`najslabija_tacka.preporuka` | A, B, C, D |
| 2 | Strategy Engine `/kompletna-analiza` Synthesis | `strateski_stav` + `prioritetni_akcioni_plan` | B |
| 3 | Strategy Engine `/kompletna-analiza` Due Diligence (internal, korak2) | `preporuka` | B |
| 4 | Strategy Engine `/v2/analiza` | `sledeci_koraci` | B, C |
| 5 | Court Predictor `/analiza` | `preporucena_strategija` | B |
| 6 | Court Predictor `/battle-report` | prose "PREPORUCENA STRATEGIJA" section | B |
| 7 | Court Predictor `/judge-profile` | `strateska_preporuka` | B |
| 8 | Court Predictor `/argument-reputation` | `preporuka`/`preporuceni_redosled` | B |
| 9 | Copilot PLAN intent | `koraci[].prioritet` + plan text | D |
| 10 | Copilot PREDLOZI intent | `predlozi[]` | D |
| 11 | Copilot `ask_agent` (via PRAVNO_PITANJE) | `brza_procena_koraci` | D |
| 12 | Case Commander `/analiza` | "PREPORUCENI POTEZ" | A, C |
| 13 | Case Commander `/quick-check` | "3 najhitnija upozorenja/akcije" | A, C |
| 14 | Case Commander `/jutarnji` (cross-case) | `prioritet` (which ONE case today) | A, C |
| 15 | Case Intelligence `/briefing` | `sledeci_korak` | A, C |
| 16 | Case Pipeline step 5 (`_step_strategija`) | "Preporučena strategija"/"Sledeći koraci" | A, E |
| 17 | Cockpit `prioritet` (G-029, pre-existing) | named as authority #1 in `G030_NEXT_ACTION_DECISION_MODEL.md` | D, citing G-030 |
| 18 | Case Ready Score `copilot_preporuka` | named as authority #3 in G-030 | D, citing G-030 |

**Note on G-030's original 3 authorities**: G-030 (2026-07-22) named Cockpit, Matter Intel, and Case Ready
Score. Matter Intel is **not** included in the 18 above — Program Gamma's own regression check (Fork C)
confirmed Matter Intel's main endpoint now correctly delegates to `services/risk_engine.py` (canonicalized
by an intervening mission, Project Synapse, 2026-08-03, after G-030 was written) — one of G-030's original
3 has since been resolved, not still open. The other 2 (Cockpit, Case Ready Score) remain open and are
counted above (#17, #18).

Task Engine (`zadaci.py::ai_analiziraj_predmet`) and Matter Intel's main endpoint are confirmed clean
(share the canonical `identify_case_problems`/`calculate_procesni_rizik` root) and are correctly excluded
from this count — they are the reference pattern, not part of the problem.

None of the 18 producers read any of the others' output.

**Why not fixed this mission**: a genuine product-identity decision (G-030's own framing: "dashboard with
several AI opinions" vs. "one command center") — which of 18 existing product surfaces survive as distinct
UI presentations of one shared answer, and which get retired, is not a technical call this mission is
chartered to make unilaterally.

**Recommended direction, fully designed**: `shared/recommendation_engine.py::compute_next_action()`, Tier 1
(deterministic, reuse `identify_case_problems`) + Tier 2 (one constrained LLM reasoning pass over Tier 1's
facts, the exact shape `zadaci.py::ai_analiziraj_predmet` already proves works) — every current producer
becomes a consumer, formatted for its own UI surface. Full design: `CANONICAL_DECISION_ENGINE.md`.

**Severity**: Critical — the platform's largest open decision-fragmentation class.

## GAMMA-002 — `routers/cio.py:148` reads Genome's raw `nedostaje.hitnost` instead of the canonical `identify_case_problems` output (Medium)

Aggregates a raw-GPT field into a portfolio-wide daily count, when the canonical deterministic source
(DC-002) is available and already used by 6+ other consumers. A concrete instance of the exact gap
`DECISION_REGISTRY.md`'s registration rule exists to prevent going forward, found (not created) during
Phase 6 consumer mapping.

**Severity**: Medium — not user-facing-broken, but a real "known-better source available, not used" gap.

## GAMMA-003 — `matter_intel.py`'s Uncertainty Dashboard and Pre-Flight Check don't use the canonical risk engine, and have zero Evidence Chain (High)

Both endpoints live in the same file as `calculate_procesni_rizik` (imported at the top, used correctly by
the file's own main endpoint) but compute their own independent case-strength/readiness numbers — the
Uncertainty Dashboard's `uncertainty_score` from 5 ad hoc heuristic dimensions plus a GPT prose gloss, the
Pre-Flight Check's `status`/`score` fully raw GPT. Neither is provenance-wrapped.

**Why not fixed this mission**: this is a DC-001 migration (a real behavioral change to what number the
lawyer sees), not a DC-009 wiring fix like Evidence Graph/Case Commander received — needs its own bounded
pass to verify the migration doesn't silently change what "risk" means for these 2 specific views.

**Severity**: High — 2 of the 4 independent "case strength/readiness" producers found this mission, in the
same file as the canonical source, not calling it.

## GAMMA-004 — Case Commander's other 3 endpoints (`/analiza`, `/quick-check`, `/checklist`) have zero Evidence Chain (Medium-High)

`_cross_case_analiza` (this mission's DC-009 migration target) is one of 4 AI-decision operations in this
file; the other 3 remain unwrapped, unvalidated.

**Why not fixed this mission**: different output shapes than `_cross_case_analiza` — wiring all 4 correctly
in one pass risked exactly the rushed, under-verified pattern this session's discipline exists to prevent.

**Severity**: Medium-High — same class as the fixed instance, proven cheap to close, just not yet done for
these 3.

## GAMMA-005 — `case_intelligence.py::case_intelligence_briefing` has no provenance wrapping (Medium)

This mission fixed the live 500 bug (wrong `proactive_alerts` column names) in this endpoint but did not
add `case_context()` provenance — adding both in one pass would have widened a bounded correctness fix into
a second, riskier change.

**Severity**: Medium — the endpoint now works; it still isn't audit-traceable.

## GAMMA-006 — `ask_agent`'s recommendation is case-specific in fact but tagged case-agnostic in the audit trail (Medium)

`routers/copilot.py::_handle_pravno_pitanje` prepends real predmet context to the question sent to
`ask_agent`, producing a genuinely case-tailored `brza_procena_koraci` recommendation — but the
`case_context()` call passes no `predmet_id`, on a rationale that conflates "the function signature has no
predmet_id parameter" with "the output is not case-specific." Any future audit-log reconstruction of "what
has the AI recommended about predmet X" will silently miss every `ask_agent`-sourced recommendation made
through Copilot. Distinct from `PROGBETA-002` (RAG provenance) — this is about `predmet_id` itself.

**Severity**: Medium — a real, previously-undocumented provenance gap, not user-facing.

## GAMMA-007 — No CI/static-analysis guardrail against a new undeclared decision (Medium, honestly scoped)

`DECISION_REGISTRY.md`'s registration rule is a process convention, not a technical control — no CI
pipeline was confirmed to exist in this repository, and no AST-based static check was built to catch a new
GPT call producing a decision-shaped output outside the registry.

**Recommended direction**: `scripts/audit_decision_registry.py`, same style/limitations as the existing
`scripts/audit_routers.py` (a heuristic flag for human review, not a hard gate).

**Why not fixed this mission**: new infrastructure, out of scope for a mission whose own charter bars
adding capability beyond what was diagnosed. Full reasoning: `DECISION_HARDENING_REPORT.md`.

**Severity**: Medium — real gap, honestly named rather than papered over with an unverified claim.

## GAMMA-008 — Case Pipeline's step 6 is a free, automatic, unlabeled shadow of the paid `hearing_cc.py` Hearing Command Center (High)

`services/case_pipeline.py::_step_hcc` and `routers/hearing_cc.py` both literally use "HCC" as their
name/tag and both answer "is the lawyer ready for this hearing" — one is PRO-only, 3 credits, `gpt-4o`,
case-type-specific (5 prompt variants), 12-field structured brief with its own risk assessment; the other
is free, automatic (fires for any predmet with a hearing in 90 days), `gpt-4o-mini`, single generic prompt,
3-5 line note. Neither references the other. A lawyer could receive the free lite version's advice and
never realize a materially deeper, paid analysis exists one click away.

**Severity**: High — both paths are reachable and both actually run (unlike `ALPHA-005`'s dead-code case),
unlabeled and unreconciled.

## GAMMA-009 — Document/case readiness has 2 structurally incompatible representations, no shared vocabulary (High)

`services/quality_gate.py::evaluate_draft_quality`'s `confidence_score` (deterministic float, calibrated,
named 0.85 approval threshold) and Strategy Engine's Pravni Revizor `ocena` (pure GPT, zero RAG, 3-value
categorical self-report) answer the identical question — "is this legal document ready to use" — for what
can be the exact same text (nothing prevents pasting a Drafting-generated nacrt into Pravni Revizor's
free-text field). No code link between the two features.

**Recommended direction**: not simply "reuse `quality_gate`" — its citation-verification half generalizes
(`PROGBETA-003`) but its completeness-scoring half is Drafting-shape-specific; needs a genuine design
decision on which representation (calibrated float vs. categorical) becomes canonical, or a mapping layer.

**Severity**: High — reachable by an ordinary user workflow, not hypothetical.

## GAMMA-010 — "How urgent is this" has 6+ independently-defined vocabularies, plus a literal field-name collision (Medium)

At least 6 unreconciled 3-value urgency taxonomies exist for one concept across Copilot's akcija handlers,
Genome's `nedostaje[].hitnost`, Copilot PLAN's `nedostaje[].hitnost` (same field name, incompatible enum —
`kriticno|vazno|pozeljno` vs. `visoka|srednja|niska`), Copilot PLAN's `koraci[].prioritet`, Copilot
PREDLOZI's `predlozi[].prioritet`, and `ask_agent`'s `brza_procena_koraci[].prioritet`.

**Why not fixed this mission**: fixing the field-name collision specifically requires a vocabulary decision
(which enum wins, or a mapping layer) — the same discipline Program Alpha applied to `ALPHA-003`'s taxonomy
question, not a blind rename.

**Severity**: Medium — real Facts≠Inference-adjacent confusion risk, not yet observed causing a live
incident.

## GAMMA-011 — `shared/genome_validator.py`'s module docstring/name no longer matches its own contents (Low, found by Olympus Faza 10 governance review)

By the end of Program Gamma, 3 of the module's 6 public functions (`validate_dok_reference`,
`validate_graph_edge_references`, `validate_predmet_reference`) have nothing to do with Case Genome except
by historical accident of file location — they are a generic "referenced entity must exist in scope"
family, reused by Compare Docs, Evidence Graph, and Case Commander. The module's own docstring still opens
"Genome Verification Layer." Chief Systems Architect's governance review noted the module's own docstring
defends this ("a future third caller is legitimate use, not a scope violation") but observed that's a
self-serving argument by the party doing the widening, not an independent architectural judgment — and
that this is the one corner of this mission where a debt entry should have existed and didn't, until now.

**Recommended direction**: extract the 3 reference-validation functions into `shared/reference_validation.py`
(or similar), leaving `genome_validator.py` genuinely Genome-scoped. Not done this mission — a pure
reorganization with no behavior change is exactly the kind of "refactoring for its own sake" this mission's
own charter is cautious about doing without a concrete trigger; recommended as the trigger for whenever a
4th caller of this family appears, not urgent standalone work.

**Severity**: Low — no functional risk, a naming/documentation-accuracy debt only.

## Carried forward, reframed (not new, sharpened this mission)

- **`ALPHA-003`** (document classification, 2 taxonomies) — traced to the exact mechanism: `evidence.py`'s
  correct-vocabulary classifier runs as an unawaited `asyncio.create_task` with silently-swallowed failure,
  meaning its "win" over `intake_classify.py`'s wrong-vocabulary classifier is probabilistic, not
  guaranteed — a sharper diagnosis of the same already-tracked item, not a new one.
- **`ALPHA-005`** (firm memory, dead vs. live) — sharpened to name the specific orphaned decisions (judge
  win-rate %, judge procedural preference, client settlement posture) and connect them to Court Predictor's
  separate, ungrounded confidence number answering a related question with no real data at all — a
  cross-mission linkage (`ALPHA-005` ↔ Program Alpha's Court Predictor finding) neither prior mission
  documented.
- **`PROGBETA-001`** (Strategy Engine's 4 litigation-percentage generators) — now confirmed to have a 5th:
  `case_pipeline.py::_step_strategija`, auto-fired at case creation, which also happens to be the sole
  satisfier of the Case Ready Score's "Strategija generisana" checklist item — the least rigorous of 5
  assessments is the one silently marked "done."
