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

---

## Program Intake, Sprint 001 (2026-08-04) — Bulletproof Document Intake Foundation

Full narrative, forks, and mission-closure self-check: `INTAKE_ARCHITECTURE_REPORT.md`. Fixed this sprint
(tested, zero regressions across 2492 tests): Pipeline A original-file Storage preservation,
`IntakeWorker._process()`'s silent false-success bug on crash-retry, `dokument_view` audit logging, explicit
`status`/`tip_dokaza` at 3 previously-silent `predmet_dokumenti` writers. Items below are what this sprint
found but deliberately did not implement.

## INTAKE-001 — Pipeline C (`finalize_intake_job`) reports `"ok": true` even when the document insert fails after Pinecone ingest already succeeded (High)

`routers/smart_intake.py:588-689`. The entire decrypt→OCR→chunk→Pinecone→DB block is wrapped in one broad
`try/except Exception`; if all 3 fallback `predmet_dokumenti` insert variants fail, `doc_linked=False` is
honestly computed and returned as `dokument_povezan: false` in the response body — but the finalize
endpoint's overall response still says `"ok": true"` because the `predmet` (case) row and client
links/hronologija were already created successfully earlier in the same call. The result: a Pinecone
ghost-vector with zero corresponding DB row, inside an otherwise-successful case-creation response.

**Why not a direct port of Project Sentinel's existing hard-fail pattern** (`api.py:4243-4247`, HTTP 500 on
the identical failure shape): Sentinel's endpoint does exactly one thing — attach a document to an
already-existing case — so a 500 there is an honest, unambiguous total failure the caller can safely retry.
Pipeline C's endpoint does several things in one call (create case, link client, add hronologija/rok, attach
document); hard-failing at the document-insert step would misreport a case that WAS genuinely, successfully
created as a total failure, and a naive client retry of the whole finalize call risks creating a **second**
case for the same job.

**Recommended direction**: a real partial-success response contract (e.g. `"ok": true, "partial": true,
"dokument_povezan": false` with a clear frontend affordance to retry just the document-attach step against
the already-created `predmet_id`), or splitting case-creation from document-attachment into two separate
calls entirely. Either is a genuine design decision, not a bounded reliability patch.

**Why not fixed this mission**: the correct fix requires product/API-contract design work this sprint's
"bounded implementation, no new capability" discipline does not license inventing unilaterally. Whether the
frontend currently surfaces `dokument_povezan: false` to the lawyer was also not verified (backend-only
scope this sprint).

**Severity**: High — reachable on every live finalize call where the document-insert step fails.

## INTAKE-002 — Orphaned encrypted Storage blobs on Pipeline B enqueue failure, no cleanup mechanism (Medium)

`routers/smart_intake.py:129-156`. If the AES-GCM-encrypted upload to the `intake-dokumenti` bucket succeeds
but the subsequent `enqueue_intake_job` RPC throws, the blob remains in the bucket permanently with zero
reference anywhere — no `intake_jobs` row was ever created to point to it. A retry mints a fresh `uuid4()`
key, so repeated failures silently accumulate orphaned blobs. No cleanup job or Storage lifecycle policy
exists for this bucket anywhere in the codebase (grepped, confirmed zero matches).

**Recommended direction**: either a scheduled cleanup job (compare bucket listing against `intake_jobs.
storage_path` references, delete unreferenced objects older than N hours) or a Storage bucket lifecycle
policy if Supabase Storage supports one directly.

**Why not fixed this mission**: a cleanup job is new scheduled infrastructure, outside this sprint's
"no new capability" bound. Does not cause tracked-document loss — nothing a user could see ever referenced
these bytes.

**Severity**: Medium — wasted storage, not data loss or a false-success condition.

## INTAKE-003 — `intake_jobs.status`'s richer processing lineage is discarded entirely at Pipeline C finalize (Medium)

Migration 073's `intake_jobs.status` enum (`received/preprocessing/classifying/extracting/matching/
dedup_check/awaiting_review/completed/failed`) plus the Confidence Graph data captured during Phase 1A
(OCR confidence, classification method, per-entity confidence, human corrections) has zero linkage to the
`predmet_dokumenti` row created at finalize — `intake_job_id` appears nowhere in that insert's payload. Once
finalized, this richer processing history becomes permanently unlinked from the case-file document.

**Recommended direction**: add an `intake_job_id` FK column to `predmet_dokumenti` (nullable, populated only
on Pipeline C writes) so future case-file views could surface "this document's OCR confidence was X,
classification method was Y" if ever needed.

**Why not fixed this mission**: a schema/migration decision with product implications (should lawyers ever
see this data?) this sprint's document-intake-only, no-new-screens charter does not license deciding
unilaterally.

**Severity**: Medium — no functional defect today, a foreclosed-future-capability cost.

## INTAKE-004 — `routers/copilot.py:804` misreports finished documents as eternally pending (Low-Medium, found but explicitly not touched — Copilot is a forbidden module this sprint)

`status in ("na_cekanju", "greska")` is treated by Copilot as "still actionable/pending." `"greska"` is never
written anywhere in the codebase (grepped, zero hits — a dead branch). `"na_cekanju"` is the DB default that,
before this sprint's `INTAKE`-prefixed fixes, 2 writers silently fell through to forever; those 2 writers now
set an explicit real status (`sacuvano`/`demo`), which incidentally *reduces* how often this Copilot
mis-signal fires — but the underlying dead/misleading read in `copilot.py` itself is untouched, per this
sprint's own explicit forbidden-module list.

**Why not fixed this mission**: Copilot is named explicitly in this sprint's charter as a module to
document, not fix, if a problem is found there.

**Severity**: Low-Medium — a real UX inaccuracy (a lawyer's finished document shows as pending in Copilot),
but self-contained to a module this sprint has no mandate to touch.

---

## Program Intake, Sprint 002 (2026-08-05) — Atomic Document Lifecycle

Full narrative and mission-closure self-check: `DOCUMENT_LIFECYCLE_ARCHITECTURE_REPORT.md`. Fixed this sprint
(tested, zero regressions across 2512 tests): Pipeline C finalize's duplicate-case race (atomic claim,
migration 092, the sprint's #1 finding, independently confirmed by all 3 investigation forks the same day),
`write_processing_outcome()`'s silent exception swallow (reopened Sprint 001's own false-success bug shape
through a different door), Pipeline A's wider-than-known orphan-blob exposure (5 raise sites, compensating
cleanup), Pipeline B's broader-than-scoped orphan-blob trigger (every ordinary duplicate resubmit, not only
RPC failure — pre-check + compensating cleanup). Items below are what this sprint found but deliberately did
not implement.

## INTAKE-005 — Pipeline A's own Pinecone-ghost-vector risk on DB-insert failure after Pinecone success (High, same root cause as `INTAKE-001`)

`api.py`'s upload handler ingests to Pinecone before the `predmet_dokumenti` insert; if Pinecone succeeds and
the subsequent insert throws, Project Sentinel's existing hard-fail (`api.py:4279-4283`) gives the caller an
honest 500 — but the Pinecone vector itself remains permanently indexed under the persistent, shared owner
namespace, with `predmet_id` metadata pointing at a document nobody in the UI can ever see. The code's own
in-line comment already acknowledges this gap explicitly ("Pinecone vektor ostaje... best-effort cleanup nije
implementiran ovde — vidi SENTINEL_PRE_BETA_CRITICAL_PATH.md"). This is the same shape as the already-tracked
`INTAKE-001` (Pipeline C's version of the identical problem), confirmed this sprint to be equally real and
unmitigated on Pipeline A.

**Why not fixed this mission**: no Pinecone-side delete/rollback call exists anywhere in either pipeline, and
Pinecone offers no transactional coordination with Postgres — building a compensating cross-system delete is
a genuine new capability, not a bounded reliability patch, and this sprint already landed 4 other fixes the
same day. Recommended direction: a background reconciliation job that diffs Pinecone vector `predmet_id`
metadata against `predmet_dokumenti` rows and deletes orphans — new scheduled infrastructure, out of this
sprint's "no new capability" bound.

**Severity**: High — reachable on every live upload where Pinecone succeeds and the DB insert fails; identical
severity profile to `INTAKE-001`.

## INTAKE-006 — `intake_jobs.status`'s intermediate processing sub-states are declared but never written (Medium)

Migration 073's CHECK constraint already lists `classifying`/`extracting`/`matching`/`dedup_check` as valid
`intake_jobs.status` values, but `shared/intake_worker.py::_process()` never actually transitions through them
— it goes straight from `preprocessing` (set by the claim) to the terminal write, with zero intermediate
visibility. An operator looking directly at `intake_jobs` cannot currently tell whether a stuck job is mid-OCR,
mid-classification, or mid-extraction.

**Recommended direction**: have `_process()` call intermediate status-update writes (bare, non-atomic — this
is observability, not a consistency requirement, so it doesn't need RPC-level atomicity) between its own
existing OCR/classify/extract steps.

**Why not fixed this mission**: real and bounded, zero migration needed (the column and CHECK constraint
already support it), but purely optional — it serves Phase 6 observability, not Phase 2 atomicity/consistency,
and this sprint's own closing instruction is explicit that when new functionality and consistency compete,
consistency wins; this item is neither necessary for consistency nor urgent enough to add alongside the 4
consistency fixes already landed the same day.

**Severity**: Medium — a real operability gap, not a correctness defect.

## INTAKE-007 — Production-replay blind spots: forensic reconstruction gaps, not document-loss gaps (Medium)

Phase 8 (production replay) walkthrough found a cluster of gaps that all share one root cause (fire-and-forget
writes with no guarantee) rather than being independent bugs: (1) no `ocr_used`/`is_scanned` column on
Pipeline A/C's `predmet_dokumenti` row itself; (2) no `document_id` FK from Pinecone chunk metadata back to
the case-file row on either pipeline — multi-document cases can only be attributed via fuzzy filename/hash
matching; (3) two independent, uncoordinated fire-and-forget provenance systems on the same journey
(`audit_immutable` via `log_action`, `ai_forensics` via `case_context`) that can each silently no-op
independently, meaning the correlation ID meant to unify a replay can end up recorded in neither; (4) no
truncation marker on `tekst_sadrzaj` — a replay cannot distinguish a short document from a long one silently
cut at 100k characters. Full detail: `REPLAY_VALIDATION_REPORT.md`.

**Why not fixed this mission**: none of these cause document loss, duplication, or false success (the
mission's own closure-blocking conditions) — the case-file artifacts a lawyer actually needs are durable and
reconstructible on the happy path this sprint traced. Closing this gap fully requires either making
`log_action`/`ai_forensics` durable-with-retry (new infrastructure) or adding several new schema columns —
either is a genuine capability addition, not a bounded fix to stack onto this sprint's 4 already-landed
consistency fixes.

**Severity**: Medium — a real forensic/audit-completeness gap, distinct from and lower-severity than a
consistency defect.

## Documentation correction (not a new debt item)

Sprint 001's own `INTAKE_FAILURE_RECOVERY_MATRIX.md` credited `intake_jobs.status='dedup_check'` as "real
dedup infrastructure Pipeline A doesn't have." This sprint's Fork C proved `dedup_check` is a dead schema
artifact — declared in the CHECK constraint and the frontend's label strings, but no code path anywhere ever
transitions a job into it. The actual, real dedup mechanism live today is the `idempotency_key` UNIQUE index
checked inside `enqueue_intake_job`. The matrix's conclusion (Pipeline B has real dedup infrastructure Pipeline
A doesn't) was correct; its named mechanism was wrong. Corrected in place in
`INTAKE_FAILURE_RECOVERY_MATRIX.md`, not filed as a separate backlog item.

## Carried forward, unchanged (not re-litigated this sprint)

- **`INTAKE-003`** (VERIFIED as a first-class state, `predmet_dokumenti`↔`intake_jobs` FK gap) — this sprint's
  transaction-boundary and state-machine analysis confirms the gap is real (`STATE_MACHINE_SPECIFICATION.md`
  §"cross-pipeline fragmentation") but adds no new urgency; still correctly a founder/product decision, not a
  bounded reliability fix.
- **`INTAKE-004`** (Copilot's dead-branch status read) — Copilot remains an explicitly forbidden module this
  sprint too; untouched.
- **`KEYSTONE-007`** (Event Bus migration 091 not run, live multi-worker duplicate-dispatch race) — reconfirmed
  present and unapplied, confirmed this sprint to concretely affect intake's `DocumentJobFailed` handler
  specifically (duplicate `proactive_alerts` rows); still a founder action item, not something to implement
  around further.

---

## Program Intake, Sprint 003 (2026-08-05) — Canonical Document Understanding

Full narrative and mission-closure self-check: `CLASSIFICATION_ARCHITECTURE_REPORT.md`. Fixed this sprint
(tested, zero regressions across 2517 tests): Pipeline C finalize no longer lets a confidence-blind classifier
silently overwrite an already-flagged-uncertain classification (the mission's own headline finding, found by
Fork C); `GET /jobs/{job_id}` no longer silently presents a stale, contradictory classification as current
after finalize (Fork A's confirmed defect). Designed but not yet adopted in code: a full canonical 10-category
legal taxonomy (`CANONICAL_DOCUMENT_TAXONOMY.md`) and a grounding-verified confidence model
(`CONFIDENCE_SPECIFICATION.md`). Items below are what this sprint found but deliberately did not implement.

## INTAKE-008 — No confidence-gated review queue on Pipeline A or the 2 ephemeral classifiers (High)

Only `shared/intake_classify.py` (Pipeline B) has a real confidence field and `AUTO_ACCEPT_THRESHOLD`-gated
escape hatch. `routers/evidence.py::_klasifikuj_dokument` (Pipeline A's ONLY classifier, and Pipeline C's
stage-2 vocabulary-correction classifier), `api.py::_detect_doc_type`, and `routers/dokument.py::
_klasifikuj_dokaz` have no confidence field and no review-queue routing — all three silently default to
`"ostalo"`/a fixed fallback bucket on uncertainty or error, with no signal anywhere that the guess might be
wrong. This is the mission's own explicitly forbidden "third state" (silently guessed), still live on 3 of 5
classifiers after this sprint's fix.

**Why not fixed this mission**: giving these classifiers a genuine confidence-gated review path requires the
full `CONFIDENCE_SPECIFICATION.md` design actually implemented (grounding verification, structural-marker
signals, the full scoring formula) — a large, multi-file change, not a bounded patch. This sprint's own fix
(preventing an already-correct uncertainty signal from being erased) was prioritized as the more severe,
more bounded finding.

**Recommended direction**: `CONFIDENCE_SPECIFICATION.md` §3's Path 1/Path 2 scoring, applied first to
`evidence.py::_klasifikuj_dokument` since it's the classifier every pipeline eventually routes through.

**Severity**: High — the majority of live classification volume (Pipeline A, plus Pipeline C's stage-2
overwrite for confidently-classified documents) still has zero uncertainty handling.

## INTAKE-009 — `/reklasifikuj` has a code-level concurrency defect: no lock, a double-click races itself (Medium)

`routers/evidence.py::reklasifikuj` launches its classification via an unawaited `asyncio.create_task` with
no per-document lock or compare-and-swap. Two rapid calls against the same document (double-click, two
browser tabs, a retried slow request) launch two concurrent background tasks, each unconditionally
`UPDATE`-ing `tip_dokaza` — whichever lands last silently wins. The exact same race shape Sprint 002 fixed
for intake finalize, self-inflicted by the very action meant to fix a bad classification.

**Why not fixed this mission**: lower frequency than the finalize race (an admin/manual action, not an
automated high-volume path); the proper fix mirrors Sprint 002's `claim_intake_finalize` pattern (a real,
bounded, well-precedented change) but was deprioritized behind this sprint's higher-severity finding.

**Recommended direction**: an atomic claim RPC on the document row (or a simple in-process lock keyed by
`dokument_id`, given this is a low-frequency admin action, not a distributed multi-worker concern), mirroring
migration 092's `claim_intake_finalize` shape.

**Severity**: Medium — real, code-level, provable, but low-frequency and doesn't corrupt data (the DB write
itself is still atomic), only produces a nondeterministic-which-guess-wins outcome.

## INTAKE-010 — No cross-row classification-consistency check for same-hash duplicate uploads (Medium)

`source_sha256` is computed at 3 upload sites but queried back at zero — confirmed by exhaustive grep. If the
same physical file is uploaded twice (through any combination of Pipeline A/B, or once into a case and once
into Klijenti Trezor with a manually-typed different type), the system has no concept that these are "the
same document" — each row's classification is decided, displayed, and consumed by downstream `EXPECTED_DOCS`
matching completely independently, with no contradiction detection.

**Why not fixed this mission**: building real cross-row consistency checking (a reconciliation pass matching
on `source_sha256`) is a genuine new capability, not a bounded patch. No evidence of this having caused an
actual production contradiction (out of this sprint's read-only scope to query live data) — a structural gap,
not an observed incident.

**Severity**: Medium — real gap, unconfirmed real-world impact.

## INTAKE-011 — Phase 7 edge-case findings: classification-adjacent OCR/extraction gaps (Medium, explicitly OCR-adjacent per the mission's own "don't fix OCR" instruction)

Full detail: `CLASSIFICATION_ARCHITECTURE_REPORT.md` §5. Confirmed defects: `ocr_confidence` is a hardcoded
`0.6` constant (not a real measurement) and is never fed into any classifier at all — clean and barely-legible
OCR text report identical confidence; zero rotation/orientation detection anywhere in the extractor; every
classifier reads only the HEAD of a whole-file concatenated text string, so a multi-document combined PDF
(lawsuit + exhibits) or a Serbian-practice "spis" bundle is always classified as if it were exactly one
document, driven by whichever document happens to appear first in the scan; handwritten annotations on
printed documents get no mixed-content handling, silently concatenated into the same OCR output as clean
printed text with no reliability flag. One narrow additional finding: a born-digital PDF interleaved with
several blank separator pages can be miscounted into the OCR fallback path unnecessarily.

**Why not fixed this mission**: the mission's own explicit instruction — "Ne rešavati OCR. Dokazati ponašanje"
(don't fix OCR, prove behavior) — this phase's job was diagnosis, not remediation.

**Severity**: Medium — real, provable defects, but each requires OCR/extraction-layer work explicitly outside
this sprint's charter.

---

## Program Intake, Sprint 004 (2026-08-05) — Human Review Orchestration & Automatic Resumption

Full narrative and mission-closure self-check: `HUMAN_REVIEW_ARCHITECTURE_REPORT.md`. **This sprint's own
binding rule, unlike Sprints 001-003: not a research sprint — every technical problem found that could be
fixed without a new founder business decision was fixed in the same sprint.** 12 findings fixed this sprint
(full list in the architecture report), headlined by wiring up `resolve_review_queue_for_job` — a fully-built
function with zero call sites anywhere, meaning a document flagged for review could never leave that state
through any live code path — and correcting `intake_jobs.status` to actually reach `awaiting_review` instead
of unconditionally `completed`, closing a live "two sources of truth disagree" defect. Items below are the 3
findings that genuinely required a business/product decision this sprint could not make unilaterally, plus 1
adjacent gap found but out of this sprint's object of study.

## INTAKE-012 — No "reject" action exists, only "confirm as-is" (High, business decision required)

The mission's own test list names "rejection" as a scenario to prove; only the "resolve/confirm" path was
built. A genuine reject action raises a real product question: does rejecting mean re-running classification
from scratch (wasteful if the same input produces the same uncertain result), routing to fully-manual data
entry (a bigger UX commitment), or something else entirely?

**Why not fixed this mission**: each option has different UX and cost implications a founder needs to choose
between — not a bounded technical gap this sprint could close by picking one unilaterally.

**Recommended direction**: founder decision on what "reject" should concretely trigger, then implement as a
sibling endpoint to `resolve_review()` following the same idempotency/audit patterns already proven this
sprint.

**Severity**: High — a real gap in the mission's own named success criteria, correctly deferred rather than
implemented with a guessed-at behavior.

## INTAKE-013 — No way for a lawyer to directly correct the AI-detected document TYPE itself (Medium, blocked on taxonomy adoption)

`POST /entities/{id}/correct` covers 8 extraction fields; `document_type` is not among them. A lawyer can
confirm-and-proceed with an uncertain type (via `resolve_review()`) or correct other fields, but cannot
directly retype the classification.

**Why not fixed this mission**: building this requires deciding which vocabulary a manual correction writes
to — `intake_documents.document_type`'s existing 13-value English set, or the canonical Serbian taxonomy
Sprint 003 designed but has not yet adopted into the schema. Genuinely blocked on that unresolved adoption
decision (`CANONICAL_DOCUMENT_TAXONOMY.md` §6), not a bounded fix this sprint could make independently
without contradicting Sprint 003's own explicit "not yet adopted" scoping.

**Severity**: Medium — a real gap, but the confirm-as-is path already lets processing proceed; this only
blocks *changing* an uncertain type, not resolving the document.

## INTAKE-014 — `staging_memory`'s approve/reject endpoints have zero audit logging (Low, out of this sprint's object of study)

Found while auditing this sprint's own two human-decision endpoints for parity. `routers/drafting.py`'s
`staging_approve`/`staging_reject` have no `log_action` call at all — the same gap this sprint closed for
`correct_entity`/`resolve_review()`, but for a genuinely different system (approving AI-drafted content, not
reviewing uncertain input classification — see `REVIEW_QUEUE_SPECIFICATION.md` §3 for why these are kept
separate).

**Why not fixed this mission**: `staging_memory`/drafting is outside this sprint's object of study (intake
document review specifically); fixing it here would be scope creep into a different subsystem this sprint's
4-agent team was not chartered to touch.

**Severity**: Low-Medium — a real audit gap, straightforward to fix with the exact pattern this sprint just
proved twice, recommended as a quick follow-up for whichever future mission owns drafting/staging.

---

## Program Intake, Sprint 005 (2026-08-05) — Canonical Document Segmentation

Full narrative: `CANONICAL_SEGMENTATION_ARCHITECTURE_REPORT.md` and siblings. Per this sprint's own binding
rule (matching Sprint 004's precedent): every technical problem found within segmentation scope that could be
fixed without a new founder business decision was fixed in the same sprint. Fixed this sprint: a real
substring-vs-word-boundary false-positive bug in `_find_heading_keyword` (Serbian inflection could misfire on
a heading keyword mid-word), an orphan-document risk in the new per-segment retry loop (mirroring Sprint 001's
already-fixed single-document version of the same defect), and a `.maybe_single()` ambiguity bug that would
have raised on a resumed segmented job's idempotency check. Items below are the ones that genuinely required a
business/product decision or new architecture this sprint could not close unilaterally.

## INTAKE-015 — Segmentation only wired into Pipeline B (durable queue worker), not Pipelines A/A-ephemeral/C (Medium, business decision required)

The extractor's contract change (`pages` as a 4th tuple element) reaches all 4 extraction call sites
(`api.py`, `routers/dokument.py`, `shared/intake_worker.py`, `routers/smart_intake.py`), but only Pipeline B
(`shared/intake_worker.py`) was wired this sprint to actually call `segment_document()` and act on the result.

**Why not fixed this mission**: Pipeline A (`api.py`) is a synchronous HTTP request/response call — auto-
fanning a single upload into N case-file entries inline, or interrupting the response to ask "we detected 3
documents — confirm?", is a genuine product/UX decision with real interaction-design tradeoffs, not a bounded
technical gap. The Phase 1 audit itself flagged this: each of the 4 call sites may legitimately want to react
to a "multiple documents detected" result differently, given one is interactive and three are background jobs.

**Recommended direction**: founder decision on the desired interactive UX for Pipeline A specifically (silent
auto-split with a post-hoc summary vs. an explicit confirm-before-split step), then reuse `shared/
intake_segment.py`'s existing pure engine unchanged — the engine itself is already pipeline-agnostic.

**Severity**: Medium — the mission's own primary target (Pipeline B, the durable Smart Intake queue) is fully
covered; this is a real scope gap for the other 3 upload paths, correctly named rather than silently left
unaddressed.

## INTAKE-016 — No cross-run backoff/retry-claim system for segments, only bounded in-process retry (Medium, new architecture required)

A segment that fails gets up to `max_attempts` (default 2) immediate, in-process retries within the same
worker tick, then dead-letters. There is no cross-run backoff scheduling (`next_retry_at`) or claim RPC
(mirroring `claim_intake_job`'s `SELECT ... FOR UPDATE SKIP LOCKED`) for segments specifically — a
dead-lettered segment stays `failed` until a human resolves it; it is not automatically retried on a later
worker tick or after a `reap_stale_jobs`-style sweep.

**Why not fixed this mission**: a full cross-run retry-claim system for a sub-unit of a job (not the job
itself) is genuinely new architecture — the mission's own bounded-scope allowance for "functionality that
requires a completely new architecture beyond this sprint's scope."

**Recommended direction**: if dead-lettered segments prove common enough in practice to need it, extend
`intake_job_segments` with `next_retry_at` and a dedicated claim RPC following `claim_intake_job`'s own
proven pattern.

**Severity**: Medium — bounded by design; a permanently-failed segment is still visible, audited, and does not
block or lose its siblings — it simply requires a human resolve action instead of an automatic later retry.

## INTAKE-017 — `partially_failed` job status not built; collapsed into existing `awaiting_review` (Low-Medium, business decision required)

A job where some segments completed and one permanently failed routes to the existing `awaiting_review`
status rather than a new, more precise `partially_failed` status. Whether `finalize_intake_job` should ever be
allowed to create a case from an M-1-of-M segmented job is an open founder decision (mirroring Sprint 004's
own `INTAKE-012` "reject" precedent) — until decided, such a job simply cannot finalize (blocked by the
existing `status != 'completed'` gate), which is safe but may eventually need a more precise status/UX if
partial failures turn out to be common.

**Why not fixed this mission**: adding a new terminal job status requires touching `intake_jobs`'s CHECK
constraint, `_tick()`'s dispatch logic, and (potentially) a decision on whether finalize may ever proceed on
partial data — genuinely a product question, not a bounded technical one.

**Severity**: Low-Medium — safe by default (fail-closed: blocks finalization rather than risking an
incomplete case file), but the UX of "why is this job stuck" for a lawyer is currently only as precise as the
existing `awaiting_review` review-queue reasons, not a dedicated partial-failure message.

---

## Program Intake, Sprint 006 (2026-08-05) — Canonical Case Assimilation

Full narrative: `CANONICAL_CASE_ASSIMILATION_ARCHITECTURE_REPORT.md` and siblings. Same binding rule as
Sprints 004/005: every technical problem found within scope that could be fixed without a new founder
business decision was fixed in the same sprint. Fixed this sprint: a live client-name-matching bug
(`finalize_intake_job` compared a full "First Last" string against a first-name-only column, `.limit(1)` with
no disambiguation), zero audit/provenance calls for document-into-case registration, a false-success bug
(case marked finalized even when 0 of its documents linked), and finalize's structural incompatibility with
Sprint 005's own multi-segment output (`get_job_result()`'s `.maybe_single()` would have raised on any
segmented job reaching finalize or `GET /jobs/{job_id}`). A real tokenization bug in the new
`looks_like_company()` heuristic was also found and fixed during this sprint's own test-writing (replacing
dots with spaces shattered "d.o.o." into meaningless single-letter tokens).

## INTAKE-018 — No segment-content-hash dedup across two different overall uploads (Medium, new architecture required)

The same physical document (e.g. a punomoćje) re-scanned into two different bundled uploads produces two
independent segments with no shared identity — nothing detects this as a duplicate today. Whole-file dedup
(`idempotency_key`, Sprint 002) only catches an identical file re-uploaded verbatim, not the same page(s)
appearing inside two different combined PDFs.

**Why not fixed this mission**: needs a new per-segment content-hash column (`intake_job_segments` has none
today) plus a cross-job lookup mechanism — genuinely new architecture, not a bounded fix.

**Recommended direction**: add a `content_sha256` column to `intake_job_segments` (hash of the segment's own
extracted text), populated at segmentation time, with a lookup at Ownership Resolution time.

**Severity**: Medium — a real gap, but not a correctness risk today (worst case: a duplicate document filed
under a case, not a WRONG case).

## INTAKE-019 — A partially-failed finalize has no retry path once `predmet_id` is set (Medium, needs a scoping decision)

If one document in a multi-document finalize call fails to link (Phase 5 isolation correctly keeps this from
blocking siblings), `intake_jobs.predmet_id` is still set unconditionally at the end — a subsequent finalize
call for the same job short-circuits to `already_finalized` and never retries the failed document.

**Why not fixed this mission**: closing this requires deciding whether `predmet_id`-set should mean "fully
done" or "at least partially done, may still need reconciliation" — a genuine scoping question (mirrors
Sprint 005's own `INTAKE-017` `partially_failed`-status deferral) rather than a bounded technical fix.

**Recommended direction**: a dedicated reconciliation endpoint/query (segments with `assimilation_status !=
'resolved'` under an already-finalized job) rather than reopening finalize's own idempotency gate.

**Severity**: Medium — the failure is visible (per-document `povezan: false` in the original response, and
`assimilation_status='failed'` persisted on the segment row), just not self-healing without a new mechanism.

## INTAKE-020 — Case number matching is exact-only, no normalization beyond whitespace (Low, deliberate scope boundary)

`resolve_case_ownership()` does an exact string match on `broj_predmeta` after whitespace normalization —
two representations of the same case number that differ in punctuation or spacing style (e.g. "П.100/24" vs.
"П. бр. 100/24") would not match, correctly falling through to "create new" rather than guessing.

**Why not fixed this mission**: any broader normalization (stripping "бр."/"br." tokens, punctuation
variants) risks conflating two genuinely different case numbers that happen to share a prefix format — a
judgment call the mission's own conservatism mandate argues against making unilaterally.

**Severity**: Low — the safe direction (create a new case rather than mis-attach) is exactly what happens
today; this is a missed-attach-opportunity risk, not a wrong-attach risk.

---

## Program Intake, Sprint 007 (2026-08-05) — Intake Finalization – Bulletproof Intake

Full narrative: `DUPLICATE_DETECTION_REPORT.md`, `RETRY_RELIABILITY_REPORT.md`,
`CASE_NUMBER_NORMALIZATION_SPECIFICATION.md`, `SPRINT_007_MISSION_REPORT.md`. Closes all 3 debts Sprint 006
deferred (`INTAKE-018` through `INTAKE-020`) — Intake is now the bulletproof, closed subsystem the mission's
own closing instruction defines: the same document can be uploaded any number of times, processing can be
interrupted at any point, retry can happen any number of times, and the system always converges on one
document, one case, one lineage chain, one audit/provenance record. **INTAKE-018/019/020 are now CLOSED**
(kept below, struck through in spirit, for historical continuity — not re-numbered).

**~~INTAKE-018~~ — CLOSED.** Cross-upload duplicate detection built (`predmet_dokumenti.content_sha256`,
migration 095) — never filename/size/date, exactly as the mission required.

**~~INTAKE-019~~ — CLOSED.** Partial-failure retry built (`intake_jobs.assimilation_complete` +
`claim_intake_finalize`'s widened WHERE clause + `predmet_dokumenti.source_intake_job_id` crash recovery,
migration 095). A job with unresolved documents is now always retryable, and retry never creates a second
case.

**~~INTAKE-020~~ — CLOSED.** Case number normalization built (`shared/case_assimilation.py::
normalize_case_number()`, a real 3-part canonical parser) — 30+ format variants of the same case number now
resolve to one identity, verified by test.

## INTAKE-021 — Cross-upload dedup/retry mechanism only wired into Pipeline C (Medium, deliberate scope boundary)

`content_sha256`/`source_intake_job_id` are only checked/written by `finalize_intake_job`. Pipeline A
(`api.py`'s synchronous per-case upload) and Pipeline A-ephemeral (`routers/dokument.py`) have no equivalent
duplicate-detection or crash-recovery mechanism — a document uploaded twice via Pipeline A today still
produces two `predmet_dokumenti` rows.

**Why not fixed this mission**: the mission's own scope was explicitly "these three debts," and Pipeline C is
where Sprint 005/006's segmentation and Ownership Resolution work already lives — extending the same
mechanism to Pipeline A is a bounded, mechanical follow-up (the content-hash check itself is pipeline-
agnostic), not attempted here to keep this sprint's own footprint minimal (hard token budget, 2 active agents).

**Severity**: Medium — Pipeline A is the higher-traffic, interactive upload path; this gap is real but was a
deliberate, named scope boundary, not an oversight.

## INTAKE-022 — Dead-lettered documents have no automatic backoff/retry ceiling at the finalize layer (Low, deliberate scope boundary)

A document that fails every fallback insert variant across multiple manual finalize retries has no
cross-run backoff or permanent dead-letter marking specific to the assimilation stage (Sprint 005 has this
for classification; Sprint 007 does not add an equivalent here).

**Why not fixed this mission**: finalize is a lawyer-initiated action, not an automatic background loop — a
human already decides whether to retry, and each retry is cheap/safe via the content-hash idempotency check.

**Severity**: Low — bounded by design; a permanently-failing document stays visible (never silently lost),
just without an automatic ceiling on manual retries.

---

## Program Delta, Sprint 001 (2026-08-05) — Canonical Case Evolution Engine

Full narrative: `docs/delta/CASE_EVOLUTION_REGISTRY.md` and siblings (future Delta sprints: read only
`docs/delta/*`, not this whole file's history). New program — Program Intake (Sprints 001-007) made document
intake bulletproof; Program Delta builds the canonical mechanism deciding what automatically follows once a
case changes, so no module decides "what next" independently anymore. Hard token budget this sprint (2 active
agents, no subagents, no parallel analysis) — both roles executed directly.

## DELTA-001 — Only DOCUMENT_ACCEPTED has wired consequences; 7 other mapped events do not (Medium, deliberate scope boundary)

Task 1 required mapping every event that changes a predmet's state (8 named examples); Task 1's own
instruction was to prove one entry point exists, not implement all of them. Only `DOCUMENT_ACCEPTED` has a
real `CONSEQUENCE_REGISTRY` entry this sprint.

**Why not fixed this mission**: hard 2-agent token budget: this sprint proves the canonical mechanism works
end-to-end for one real event before expanding to others — matching the mission's own explicit instruction
("ne implementirati sve, samo dokazati da postoji jedan ulaz").

**Recommended direction**: each of the other 7 events already has a real, checkable `EventType` enum member;
wiring consequences for any of them is adding a `CONSEQUENCE_REGISTRY` entry + executor functions, reusing
this sprint's exact dispatcher — no new architecture needed.

**Severity**: Medium — a real scope boundary (most of Task 1's own named events have no automation yet), but
not a regression; nothing that worked before this sprint stopped working.

## DELTA-002 — 3 existing scattered "decide what's next" call sites not migrated to the canonical mechanism (Medium, deliberate scope boundary)

Pipeline A's (`api.py::predmet_upload`) and `routers/rocista.py`'s own direct `_run_genome_background()` calls,
plus Pipeline C's own Evidence-Vault-auto-classify and conflict-check direct calls, still decide "what
happens next" independently — not yet migrated to emit through the canonical Consequence Engine.

**Why not fixed this mission**: each is a real, additional, non-trivial migration (a new emission call site +
verifying no behavior/cost regression) — the hard token budget bounded this sprint to proving the mechanism
on ONE already-hardened call site (Pipeline C's Genome trigger) rather than migrating all 4 at once.

**Recommended direction**: mechanical, one call site at a time, in a future Delta sprint — same registry, same
dispatcher, different emission point.

**Severity**: Medium — real architectural debt (the mission's own closing claim, "no module decides
independently," is not yet fully true platform-wide), but each remaining call site is independently correct
and safe today, not broken.

## DELTA-003 — No rollback mechanism for a consequence sequence with genuine cross-consequence dependencies (Low, no current need)

The Canonical Consequence Engine has no rollback concept — by design, since `DOCUMENT_ACCEPTED`'s own 2
consequences (Genome refresh, Timeline entry) are independently safe to leave partially applied.

**Why not fixed this mission**: no event registered yet has consequences that require all-or-nothing
semantics; building a rollback mechanism for a case that doesn't exist yet would be speculative architecture.

**Severity**: Low — named for future awareness; revisit if/when an event with genuinely interdependent
consequences is wired.

---

## Program Delta, Sprint 002 (2026-08-05) — Canonical Event Migration I

Full narrative: `docs/delta/EVENT_MIGRATION_REPORT_SPRINT_002.md`, `docs/delta/RELIABILITY_VERIFICATION_REPORT_SPRINT_002.md`.
Migrates 4 more events onto Sprint 001's canonical mechanism (`REVIEW_ACCEPTED`, `REVIEW_REJECTED`,
`NEW_CLIENT_LINKED`, `NEW_EVIDENCE_REGISTERED`). Hard 2-agent token budget honored throughout.

## DELTA-001 — UPDATED: 5 of 8 mapped events now wired (was 1 of 8)

`REVIEW_ACCEPTED`, `REVIEW_REJECTED`, `NEW_CLIENT_LINKED`, `NEW_EVIDENCE_REGISTERED` wired this sprint,
joining `DOCUMENT_ACCEPTED` (Sprint 001). 3 events remain declared-not-wired: `DOCUMENT_MODIFIED`,
`CONFIDENCE_DROPPED`, `MANUAL_CORRECTION_APPLIED` — no proven consequence gap for any of the three (see
`CASE_EVOLUTION_REGISTRY.md`'s own per-event reasoning, unchanged from Sprint 001's own assessment, re-
confirmed not re-derived this sprint).

**Severity**: Low (downgraded from Medium) — the remaining 3 events all have an explicit "no proven need yet"
reasoning, not merely "not gotten to it."

---

## Program Delta, Sprint 003 (2026-08-05) — Canonical Event Migration II: Complete Event Convergence

Full narrative: `docs/delta/EVENT_MIGRATION_REPORT_SPRINT_003.md`, `docs/delta/ORCHESTRATOR_OWNERSHIP_REPORT_SPRINT_003.md`,
`docs/delta/RELIABILITY_VERIFICATION_REPORT_SPRINT_003.md`. Migrates the last 2 direct-orchestration call
sites (Pipeline A, `routers/rocista.py`) and wires the last event with a genuine consequence need
(`ROCISTE_ZAKAZANO`). Hard 2-agent token budget honored throughout.

---

## Program Delta, Sprint 004 (2026-08-06) — Orchestration Certification

Full narrative: `docs/delta/ORCHESTRATION_CERTIFICATION_REPORT.md`, `docs/delta/EVENT_COVERAGE_MATRIX.md`,
`docs/delta/ARCHITECTURAL_INVARIANTS_REPORT.md`, `docs/delta/END_TO_END_EVENT_VERIFICATION.md`. Forensic
verification sprint, not development — attempted to break the Case Evolution Engine's own claim of
canonicity. Found zero bypasses, zero hidden orchestrators, zero duplicate ownership. One documentation
undercount fixed (`EventType` has 20 members, not 19 as Sprint 003 stated). Hard 2-agent token budget honored.

---

## Program Omega, Master Sprint 001 (2026-08-06) — From Document Upload to Complete Case Intelligence

Full narrative: `docs/omega/OMEGA_SPRINT_001_REPORT.md`, `docs/omega/OMEGA_ARCHITECTURE_MAP.md`,
`docs/omega/OCR_AND_INTAKE_CAPACITY_REPORT.md`, `docs/omega/CASE_INTELLIGENCE_AUTOMATION_REPORT.md`. First
Omega sprint — Priority 1's own named scenario (500-document upload) drove a full-chain audit before any code
was written; found and closed 2 real capacity breaks (upload-endpoint timeout risk, missing batch-finalize),
named 2 more without attempting them.

## OMEGA-001 — CLOSED (Program Omega, Sprint 002, 2026-08-06): Case Genome now recomputes once per case per batch, not once per document

Was: if N documents finalized via `POST /jobs/finalize-batch` all resolved to the SAME `predmet_id`, each
one's own `_finalize_intake_job_core` call emitted its own `DOCUMENT_ACCEPTED` event, and Case Evolution
Engine triggered a full Genome recompute per event — up to N full recomputes for what is conceptually "one
case receiving N documents."

**Closed by**: a new canonical event, `EventType.DOCUMENT_BATCH_COMPLETED`, emitted ONCE per unique
`predmet_id` touched by a batch (not once per job) — per-job `DOCUMENT_ACCEPTED`/`NEW_EVIDENCE_REGISTERED`
emissions are UNCHANGED (evidence classification/timeline entries still happen at document granularity,
correctly), but the expensive Genome recompute now happens exactly once per case via the new event's own
`genome_refresh` consequence (reused unchanged) + `case_intelligence_summary` consequence (new). See
`docs/omega/CASE_REFRESH_ENGINE_SPEC.md` for the full mechanical detail and
`tests/test_omega_sprint002_case_intelligence.py::test_scenario1_single_case_large_batch_produces_one_summary_with_correct_diffs`
for the proof (Genome called exactly once for a 500-document single-case batch).

**Severity**: N/A (closed).

**Amendment (Program Omega, Sprint 003, 2026-08-06)**: the closure above was incomplete. Sprint 002's own new
`DOCUMENT_BATCH_COMPLETED` event correctly added ONE additional `genome_refresh`, but never suppressed the
PER-JOB `DOCUMENT_ACCEPTED` emission that `_finalize_intake_job_core` still fired unconditionally whenever
`genome_should_trigger` was true — meaning a 500-document single-case batch was actually producing 501 Genome
recomputes (500 per-job + 1 batch-level), not the claimed 1. Found via direct grep during this sprint's own
Phase 1 forensic pass, not reported by anyone. Fixed by adding a keyword-only `emit_document_accepted: bool =
True` parameter to `_finalize_intake_job_core` (default preserves the single-job endpoint's own behavior
exactly), with `finalize_intake_jobs_batch` passing `False`. This also silently removed the per-job Timeline
entry (previously produced by `DOCUMENT_ACCEPTED`'s own `timeline_entry` consequence) — caught before shipping
and fixed by adding a `timeline_entry` consequence, reusing the same executor unchanged, to
`DOCUMENT_BATCH_COMPLETED`'s own registry entry. Both fixes verified: the existing Sprint 001/002 regression
suite passes unchanged, and the true "exactly 1 Genome recompute per case per batch" claim now actually holds
end to end. Re-closed, this time genuinely.

## OMEGA-002 — No automatic Task creation from document-acceptance-noticed problems (Medium, needs a business decision)

Missing evidence, contradictions, and deadline risk are all already DETECTED (existing Risk Engine / Genome
output) but never become an automatically-created task — confirmed via Program Delta Sprint 004's own
Event Coverage Matrix (every one of the 6 Case Evolution events shows `NE` for "Tasks"), re-confirmed here.

**Why not fixed this sprint**: which detected problems warrant an auto-created task (vs. staying a passive
dashboard/case-page signal) is a real product decision, not a mechanical migration — building it blind risks
either under-automating (missing the point) or over-automating (creating noisy, unwanted tasks a lawyer didn't
ask for).

**Recommended direction**: a future, dedicated Omega sprint scoped specifically to this question, starting
with a founder decision on which problem types warrant a task.

**Severity**: Medium — the mission's own Priority 4 ("automatski rokovi i zadaci") is only half-closed
(deadlines yes, tasks-from-noticed-problems no).

---

## Program Omega, Sprint 002 (2026-08-06) — Case Intelligence Aggregation Engine

Full narrative: `docs/omega/OMEGA_SPRINT_002_REPORT.md`, `docs/omega/OMEGA_CASE_INTELLIGENCE_ARCHITECTURE.md`,
`docs/omega/CASE_REFRESH_ENGINE_SPEC.md`, `docs/omega/CASE_LEVEL_INTELLIGENCE_FLOW.md`,
`docs/omega/BATCH_INTELLIGENCE_VALIDATION_REPORT.md`. Closes `OMEGA-001` (see above) and builds the first
real case-level intelligence summary, sourced and durable.

## OMEGA-003 — Document reclassification (Scenario 5) has no defined consequence chain (Medium, needs a design decision)

`DOCUMENT_MODIFIED` remains one of the 3 declared-but-not-wired `EventType` members (unchanged since Program
Delta Sprint 001, re-confirmed by Sprint 004's own certification, unchanged by this sprint). Program Omega
Sprint 002's own Phase 5 explicitly named Scenario 5 ("document changes classification — do Genome/Timeline/
Evidence/Tasks stay synchronized?") as a required test, and it was NOT built or tested this sprint.

**Why not fixed this sprint**: this mission's own charter was Case Intelligence AGGREGATION (batch → one
refresh → one summary), not classification-change propagation — a genuinely different question requiring its
own design pass (does reclassification need a full evidence re-classification? A Genome refresh? Does the OLD
classification's own downstream effects — e.g. an evidence tag, a timeline entry — need to be reversed or
just superseded?). Attempting it blind risks either doing too little (a silent gap) or too much (new AI
capability, forbidden by this sprint's own "no new isolated functions" principle).

**Recommended direction**: a dedicated future Omega sprint wiring `DOCUMENT_MODIFIED`, starting with an
explicit design decision on what reclassification should actually trigger.

**Severity**: Medium — a real, named gap in Phase 5's own required test coverage, not silently assumed
covered.

## OMEGA-004 — No read-API for `case_intelligence_summaries` (Low, deliberately deferred)

The new `case_intelligence_summaries` table (migration 098) is durable and sourced, but no endpoint exposes it
to a lawyer or frontend — the data exists, nothing reads it back out yet.

**Why not fixed this sprint**: the mission's own "ZABRANJENO" list explicitly forbids new dashboard panels;
building a bare read endpoint without a real consumer would be premature. A natural, low-risk follow-up once
a UI surface for it is actually planned.

**Severity**: Low — no correctness risk, just an unrealized value gap.

---

## Program Omega, Sprint 003 (2026-08-06) — Autonomous Legal Office / Canonical Action Engine

Full narrative: `docs/omega/OMEGA_SPRINT_003_REPORT.md`, `docs/omega/ACTION_PRODUCER_REGISTRY.md`,
`docs/omega/CANONICAL_ACTION_ENGINE.md`, `docs/omega/ACTION_PRIORITY_MODEL.md`,
`docs/omega/CASE_ACTION_LIFECYCLE.md`. Builds the first deterministic, non-GPT Action Engine
(`services/case_evolution.py::_consequence_refresh_case_actions`, `case_actions` table, migration 099) and a
Worklist read endpoint (`routers/case_actions.py`, Phase 6). Amends `OMEGA-001` (see above — found genuinely
incomplete, now genuinely closed).

## OMEGA-005 — "Client not contacted in N days" has no deterministic data source (Low, deliberately not implemented)

The mission's own third worked example for a deterministic action rule. Grepped for
`poslednji_kontakt`/`last_contact`/`zadnja_aktivnost`/`poslednja_aktivnost` across `services/`, `routers/`,
`shared/` — no genuine "last client contact" tracking exists anywhere in the platform; only
`predmeti.updated_at`-adjacent proxies in unrelated modules (`morning_briefing.py`, `sesije.py`,
`wallet_provenance.py`), none of which represent client contact specifically.

**Why not fixed this sprint**: approximating this from an unrelated timestamp would violate Agent 4's own "no
conclusion without source" mandate for THIS specific sprint's own headline requirement (every action must have
verifiable evidence) — a rule this engine cannot honestly ground does not ship half-grounded.

**Recommended direction**: requires its own real feature (a genuine last-client-contact event/log — e.g. a
"logged a call/email/meeting" action a lawyer explicitly records) before this rule can be added truthfully.

**Severity**: Low — a named, honest gap in a nice-to-have rule, not a correctness risk in what shipped.

## OMEGA-006 — `predmet_dokumenti` queries still omit `tip_dokaza` in 2 older callers (Low, pre-existing, not touched this sprint)

`_compute_target_actions` (this sprint) fixed its OWN `predmet_dokumenti` select to include `tip_dokaza` — see
`docs/omega/CANONICAL_ACTION_ENGINE.md`'s own "correctness fix made in-scope" section for why. Two
already-existing callers were NOT touched and still carry the original G-028 gap:
`routers/matter_intel.py:66` and `services/case_evolution.py::_consequence_case_intelligence_summary` (Sprint
002). Both currently compute `nedostajuci_dokazi` as if EVERY expected document type is always missing,
regardless of what's actually uploaded — a read-only display distortion, not a stateful false positive (unlike
what `_compute_target_actions` would have inherited unfixed).

**Why not fixed this sprint**: out of this sprint's own stated scope (Action Engine correctness); fixing
`matter_intel.py` and the Sprint 002 summary executor is a 1-line change each but touches code this sprint
didn't otherwise need to touch, and both already have their own established test coverage that would need
re-verification.

**Recommended direction**: a trivial follow-up — add `tip_dokaza` to both remaining selects, re-run their own
existing test suites.

**Severity**: Low — display-only distortion (`matter_intel.py`, case-page risk card) and a possibly-inflated
`dokumenti_niska_sigurnost`-adjacent count in `case_intelligence_summaries` (Sprint 002), not a new stateful
artifact.

## OMEGA-007 — Action priority does not decay/escalate on a bare clock tick, only on a real event (Low, by design this sprint)

A `PRIPREMITI_PODNESAK` action's priority is recomputed correctly every time `refresh_case_actions` runs for
its case — but that only happens on `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO`/
`DOCUMENT_BATCH_COMPLETED`. A case that receives no new documents/reviews/hearings for weeks will show a
priority computed as of its LAST real event, even as a deadline silently crosses from `medium` into `critical`
territory purely by the calendar advancing.

**Why not fixed this sprint**: the mission's own charter defines the engine as event-driven ("Event → Canonical
Handler → Consequence → Audit"), not clock-driven; adding a daily re-tick job is a legitimately different
mechanism (a new scheduled trigger, not a new consequence) and wasn't asked for.

**Recommended direction**: a small future addition — a daily cron that calls `refresh_case_actions` for every
case with at least one open action and an approaching `rok`, OR (simpler) compute priority display-side as
`max(stored_priority, priority_by_days(rok))` at read time in the Worklist, without touching the stored row.

**Severity**: Low — priority is never WRONG in a way that hides an action (it still shows, just possibly
under-prioritized until the next event), and every `rok` date itself is always accurate.

## OMEGA-008 — 5 independent "what should I focus on today" surfaces now exist, none aware of the others (High, needs a founder-level product decision)

Phase 1's own forensic pass (`docs/omega/ACTION_PRODUCER_REGISTRY.md`) confirmed this sprint's new
`GET /api/case-actions/worklist` is the **5th** independently-built answer to essentially the same question:
Case Commander's `GET /api/commander/jutarnji` (self-described "srce platforme", GPT, cached daily),
`routers/morning_briefing.py` (GPT, emailed daily), `routers/case_intelligence.py`'s briefing endpoint (GPT,
explicitly aims to be "JEDNU preporuku"), and `routers/zadaci.py::ai_analiziraj_predmet` (hybrid, already
grounded in `risk_engine.py`, writes real `zadaci` rows) all independently answer "what does this lawyer need
to do." The new deterministic worklist does not replace, feed, or get fed by any of the other 4.

**Why not fixed this sprint**: which of the 5 becomes the lawyer's actual daily entry point (or whether they
get merged) is a product decision about trust and UX, not a mechanical migration — the new engine is
deterministic and provable in a way none of the GPT-based 4 are, which is a genuine argument for it becoming
primary, but that call is the founder's, not an autonomous sprint's.

**Recommended direction**: a founder decision on which surface(s) survive, followed by a dedicated
consolidation sprint. `routers/zadaci.py::ai_analiziraj_predmet` is the closest/cheapest to fold in first — it
already reuses `risk_engine.py`, the same foundation `case_actions` reuses (see
`docs/omega/ACTION_PRODUCER_REGISTRY.md`'s own Producer 5 entry and its "Preporuka za budući sprint" section).

**Severity**: High — not a bug, but the single largest structural fragmentation this whole engagement has
found in the "what should the lawyer do" space; left unresolved, a 6th independent surface is exactly the kind
of thing a future sprint could accidentally build next.

**Amendment (Program Omega, Sprint 004, 2026-08-06)**: the founder-level decision this item asked for arrived
as this sprint's own charter. Phase 1's fuller forensic pass (`docs/omega/WORKSPACE_SURFACE_REGISTRY.md`) found
2 MORE surfaces beyond the original 5 (CIO Daily, Notifications) — 6 independently-built widgets live on the
SAME home page (`dash_load()`, `static/vindex.js:1206`), not 5 separate ones. The Responsibility Matrix
(`docs/omega/UNIFIED_WORKSPACE_ARCHITECTURE.md`) now firmly decides all of them: the new `GET /api/workspace`
(built this sprint, absorbing `case_actions`) is canonical; Command Center/Morning Briefing/Case Commander/CIO
Daily are demoted to "postaje podmodul" (their own docstrings updated this sprint to say so, zero behavior
change); Notifications/Health Index/`proactive_alerts` stay as genuinely different functions (FYI/portfolio-
scope, not operational worklists). **The decision is made; the FRONTEND wiring that would make it visibly true
to a lawyer is not done** — see `OMEGA-012` below, the direct continuation of this item.

## OMEGA-010 — 3 independent alert/notification tables never reconciled (Medium, documented not merged)

`proactive_alerts`, `notifications`, and `case_actions` each independently store "something needs attention" —
confirmed genuinely different functions (operational vs. FYI) this sprint, not simple duplication, but no
mechanism connects them (e.g. a `case_actions` critical item does not also produce a `notifications` bell
entry). See `docs/omega/WORKSPACE_DATA_OWNERSHIP.md`, Finding 1.

**Why not fixed this sprint**: merging or cross-wiring 3 live, separately-consumed tables/schemas is a real
migration decision, not a read-side aggregation — outside Workspace's own safe, additive scope.

**Recommended direction**: a future sprint should decide whether `proactive_alerts` becomes a lower-urgency
Workspace input tier, and whether `notifications`' own independent deadline/inactivity computation should
instead be triggered by Case Evolution events.

**Severity**: Medium — no correctness risk (all 3 systems work correctly on their own), a coherence/
completeness gap.

## OMEGA-011 — At least 5 independent priority vocabularies platform-wide (Medium, locally translated not unified)

`case_actions.prioritet`, `identify_case_problems.ozbiljnost`, `notifications.priority`, `zadaci.prioritet`,
and CIO's own informal 0-100 `kriticnost` score all express the same underlying concept differently. See
`docs/omega/WORKSPACE_DATA_OWNERSHIP.md`, Finding 2.

**Why not fixed this sprint**: `routers/workspace.py::_ZADACI_PRIORITET_MAP` translates the 2 that collide
inside the new Workspace view itself (`case_actions` + `zadaci`) — the other vocabularies belong to modules
not touched this sprint.

**Recommended direction**: a platform-wide canonical priority scale with per-system translation adapters (the
same pattern already proven this sprint), applied to `notifications`/CIO/any future caller.

**Severity**: Medium — a display-consistency gap, not a correctness bug.

## OMEGA-012 — `/api/workspace` (and Sprint 003's own `/api/case-actions/worklist` before it) has zero frontend references (High, the single most consequential open item)

Confirmed by Phase 1's own grep of `static/vindex.js`: neither Sprint 003's Worklist nor this sprint's new
canonical `/api/workspace` is called anywhere in the frontend. The architecturally correct, deterministic,
sourced answer to "what does the lawyer see when they open Vindex AI" exists and is tested, but a lawyer
cannot currently see it without calling the API directly.

**Why not fixed this sprint**: rewiring the home page's own `dash_load()` — a large, legacy, un-browser-tested
function already composing 6 independent widgets — carries real production risk with no live-browser
verification available in this autonomous session. Matches this whole engagement's own established precedent:
Smart Intake's frontend gap was named and escalated for 3 full sessions before being explicitly authorized and
built in "Operation Beta Closure," never attempted blind.

**Recommended direction**: an explicit founder go-ahead for a dedicated frontend pass (with live-browser
verification, per this project's own UI-change discipline), replacing or supplementing the 4 "postaje podmodul"
widgets with a single Workspace panel.

**Severity**: High — this is the actual, literal blocker on the mission's own Definition of Done item "advokat
može otvoriti platformu i bez traženja odmah videti šta zahteva njegovu pažnju." The backend is done; the
lawyer-visible outcome is not, yet.

**Amendment (Program Omega, Final Sprint 005, 2026-08-06)**: CLOSED for the literal claim above. The
founder's own Sprint 005 charter explicitly authorized the frontend pass this item asked for.
`GET /api/workspace` is now wired into `dash_load()`/`_dashRender` (`static/vindex.js`, `wsLoad()`/
`_wsRender()`), positioned as the first substantive section a lawyer sees, right after Quick Actions. What
remains open is narrower and renamed `OMEGA-017` below: the 4 GPT narrative widgets (Command Center's own
recap, Morning Briefing, Case Commander, CIO) are demoted (docstrings corrected, zero behavior change) but
still independently exist and still render on the same page — Workspace did not replace them, it was added
alongside them.

## OMEGA-013 — 9 other call sites still write the un-castable string literal `"now()"` to timestamp columns (Medium, unverified elsewhere)

This sprint fixed `_consequence_refresh_case_actions`'s own 2 occurrences (real computed ISO timestamp instead
of the string `"now()"`, which Postgres's `timestamptz` parser does not document as equivalent to its own
special `'now'` value). 9 other files use the identical pattern (`routers/evidence.py`,
`routers/smart_intake.py`, `routers/knowledge_base.py`, `routers/sef.py`,
`routers/knowledge_transfer.py`, `routers/client_twin.py`, `services/knowledge_hygiene.py`,
`routers/knowledge_hygiene.py`) — none verified against a real Postgres instance this sprint (no live DB
available in this session). See `docs/omega/WORKSPACE_DATA_OWNERSHIP.md`, Finding 5.

**Why not fixed this sprint**: out of Workspace's own scope; a repo-wide audit of 9 unrelated, live files needs
its own verification pass (and ideally one real Postgres round-trip test settling whether `'now()'` actually
fails, rather than 9 speculative fixes).

**Recommended direction**: a small, dedicated future task — write ONE integration test against a real (or
faithfully-emulated) Postgres timestamptz column proving whether `'now()'` round-trips correctly; fix the 9
call sites uniformly if it does not.

**Severity**: Medium — if the literal genuinely fails, each affected column silently never got a valid
timestamp (a latent data-quality gap, not a crash, since none of the other 9 sites currently `.gte()`-filter
by the affected column the way this sprint's own Completed bucket does).

---

## Program Omega, Final Sprint 005 (2026-08-06) — Unified Operational Experience

Full narrative: `docs/omega/OMEGA_FINAL_SPRINT_005_REPORT.md`, `WORKSPACE_INTEGRATION_REPORT.md`,
`USER_JOURNEY_CERTIFICATION.md`, `SHADOW_WORKFLOW_AUDIT.md`, `CANONICAL_NAVIGATION_MAP.md`. Closes `OMEGA-012`
(Workspace now wired into the frontend); adds `OMEGA-014` through `OMEGA-017` below.

## OMEGA-014 — `case_actions` is empty for any case with no qualifying event since Sprint 003 shipped (Medium, script built not run)

`case_actions` populates ONLY via 4 Case Evolution events (`DOCUMENT_ACCEPTED`, `REVIEW_ACCEPTED`,
`ROCISTE_ZAKAZANO`, `DOCUMENT_BATCH_COMPLETED`) — correct by design (no new orchestrator), but it means any
predmet that existed before Sprint 003 shipped, or simply hasn't had a triggering event since, has ZERO
`case_actions` rows. Workspace shows that case as falsely clean, not because it has no risks/deadlines, but
because nothing has "touched" it through the new engine yet.

**Why not fixed this sprint**: fixing it means writing DATA (running the Action Engine's own logic against
every existing predmet) — the same standing caution this project applies to SQL migrations (founder runs
state-changing operations himself) applies here too.

**Built, not run**: `scripts/backfill_case_actions.py` — a one-time script reusing
`_consequence_refresh_case_actions` unchanged (no new algorithm), safe to re-run (already idempotent),
supports `--dry-run` and `--user-id` for a staged rollout. 4 new tests
(`tests/test_omega_sprint005_backfill_script.py`). This is WHY `_kcPanelRokovi` (the older, `case_actions`-
independent deadline panel) was deliberately KEPT this sprint rather than retired — see
`docs/omega/SHADOW_WORKFLOW_AUDIT.md`, item 5.

**Severity**: Medium — no data is wrong, some real risks/deadlines on old cases are simply not yet visible
in the new engine; the old panel remains as a safety net until the backfill runs.

## OMEGA-015 — `services.case_evolution` cannot be the first of it/`services.event_bus` imported fresh in a process (Low, worked around locally, not fixed at the source)

Found while writing this sprint's own backfill-script tests: `services/case_evolution.py` imports
`services.event_bus` at module level; `services/event_bus.py`'s own module-level `bus = EventBus()`
construction imports `handle_case_changed` back from `services.case_evolution` — a genuine circular import.
It "works" everywhere else in this codebase purely because every existing caller happens to import
`services.event_bus` (or something that does) before ever touching `services.case_evolution` directly — a
fragile, undocumented import-order dependency, not a structural guarantee.

**Why not fixed this sprint**: restructuring the module boundary between these 2 files is a real
architecture change, well outside a docs-and-one-script addition; worked around locally in this sprint's own
new test file (`tests/test_omega_sprint005_backfill_script.py`, explicit `import services.event_bus` first)
instead.

**Recommended direction**: move the `from services.case_evolution import handle_case_changed` call inside
`EventBus._register_defaults()` to a lazy/deferred import already partially used elsewhere in that same
function, or restructure so `event_bus.py` doesn't import `case_evolution` at construction time at all.

**Severity**: Low — purely a robustness/DX issue for future code that imports these 2 modules in an
unfamiliar order; no runtime behavior is wrong today.

## OMEGA-016 — Live `kalendarLoad()` dropped its own predecessor's `/api/predmeti` fallback (Low, narrow)

Found while removing the OLD, dead `kalendarLoad` (shadow-workflow cleanup, `docs/omega/SHADOW_WORKFLOW_AUDIT.md`
item 2): the old version had a fallback `fetch('/api/predmeti')` for when the global `_predmeti` array isn't
populated yet, feeding `_kalendarPredmeti` (used by the ročište-creation form's own predmet dropdown). The
live version (kept, "FAZA 1.8"-era) only assigns from `_predmeti` if it's already populated — no fallback.

**Why not fixed this sprint**: narrow, needs verifying whether `_predmeti` is reliably populated by the time
a real user reaches the calendar tab in practice before deciding whether re-adding the fallback is even
necessary — out of this sprint's Workspace-focused scope.

**Severity**: Low — only affects the ročište-creation form's own predmet dropdown, only in a specific
loading-order edge case.

## OMEGA-017 — 4 independent GPT "what needs attention" widgets still live alongside Workspace (High, renamed from `OMEGA-012`'s own remaining scope, founder decision still needed)

Now that `GET /api/workspace` is genuinely wired into the home page (this sprint), the remaining open
question from `OMEGA-008`/`OMEGA-012` is narrower but unchanged in kind: Command Center's own recap,
Morning Briefing, Case Commander, and CIO Daily are all still live, still independently compute their own
version of "what's important," and still render on the same page as Workspace — added ALONGSIDE, not
replacing them. Each already got a docstring correction in Sprint 004 (commit `4f6bad4`, no longer claims
to be canonical) — unchanged, zero behavior change, this sprint.

**Why not fixed this sprint**: same reasoning as `OMEGA-012`'s own original entry — rewriting or removing 3
live, credit-metered GPT features' own prompts/behavior without live-browser verification available in this
session is a real production risk this whole engagement consistently escalates rather than guesses at.

**Recommended direction**: an explicit founder decision on whether/how to consolidate these 4 into, or
underneath, Workspace — a product/UX call about which AI narrative (if any) survives as a companion to the
now-canonical deterministic view, not a code decision.

**Severity**: High — the last remaining piece of "one operational system, not six voices," now well down
from "6 independent surfaces, 0 wired" (Sprint 004's own starting point) to "1 canonical view wired + 4
demoted-but-present companions," but not fully resolved.

## OMEGA-018 — 8-9 independent priority/urgency vocabularies confirmed platform-wide, only 2 unified (Medium, scope larger than Sprint 004's own original estimate)

Phase 1's own fuller frontend audit this sprint (beyond Sprint 004's own "5+" estimate) confirmed, with new
file:line evidence: the case-detail Cockpit panel's own risk badge (`pred_renderCockpit`,
`static/vindex.js`, Serbian `nizak`/`srednji`/`visok` via a CSS-class-per-value convention), the Zadaci
panel's own badge (`_ZADACI_PRIORITET_BADGE`, raw `hitno`/`visoko`/`normalan`/`nisko` printed as visible
badge text), and at least 2 more independent `hitnost` vocabularies (`odmah`/`ovu_nedelju` in
briefing/Genome-adjacent code; `kriticno`/`vazno` in Genome's own `nedostaje[].hitnost`) — each with its own
hand-copied inline hex-color triplet repeated at multiple call sites rather than a shared constant. Combined
with `OMEGA-011`'s own original 5, the real count across the whole platform is closer to 8-9, not "5+."

**Partially addressed this sprint**: the new case-detail "Otvorene akcije" panel (`_predActionsLoad`,
closing the Case→Action navigation gap) deliberately reuses Workspace's own `_WS_PRIO_COLOR` constant — so
these 2 specific surfaces are now visually consistent with each other, a small proof that the translation-
at-the-boundary pattern (`_ZADACI_PRIORITET_MAP`, Sprint 004) generalizes. The other 6-7 vocabularies found
were NOT touched — unifying Cockpit's own badge rendering, the Zadaci panel's own badge, and Genome's own
`hitnost` fields each touch a different, independently-styled, live UI surface; batch-converting all of them
without live-browser verification in one pass was judged too large/risky for this sprint.

**Recommended direction**: a dedicated future pass — likely CSS-level (one shared `--priority-critical`/
`--priority-high`/etc. custom-property set) plus a small set of vocabulary-translation constants (mirroring
`_ZADACI_PRIORITET_MAP`) for each of the remaining raw Serbian vocabularies, applied one surface at a time
with visual verification.

**Severity**: Medium — no functional bug (each surface renders its own priority correctly in isolation), a
pure visual/lexical consistency gap, directly relevant to the mission's own Phase 4 ("ista stvar mora
izgledati identično na celoj platformi") — named honestly as NOT fully achieved rather than claimed done.

## OMEGA-019 — Action → Document is grounded in data but not yet a clickable UI link (Low, deliberately deferred)

Every `case_actions` row already carries its own `dokaz`/`izvor_dokumenti` source reference (Sprint 003's
own "no conclusion without source" grounding requirement, e.g. `"DOK-XX str.Y"` for contradiction actions)
— the RAW data for "which document caused this action" is present and correct end-to-end, proven by Sprint
003's own tests. Neither Workspace's own item rows nor the new case-detail "Otvorene akcije" panel
(`OMEGA`/Sprint 005) render this as a clickable "open this document" action yet — see
`docs/omega/CANONICAL_NAVIGATION_MAP.md`'s own "Deadline → Document" section.

**Why not fixed this sprint**: needs a real UI decision (open the document viewer directly? scroll to a
page? highlight a snippet?) plus wiring to whatever document-open mechanism the case-detail page already
uses elsewhere — a small but real scoped addition, not attempted given this sprint's own remaining time
budget after closing the larger Case→Action gap.

**Severity**: Low — not a dead end (the information exists and is visible as text), just not yet one click
away.

---

## Program Omega, Final Sprint 006 (2026-08-06) — Canonical Attention Engine

Full narrative: `docs/omega/OMEGA_FINAL_SPRINT_006_REPORT.md`, `ATTENTION_SURFACE_REGISTRY.md`,
`CANONICAL_ATTENTION_MODEL.md`, `ALERT_CONSOLIDATION_REPORT.md`, `ATTENTION_FLOW_CERTIFICATION.md`. Builds
`shared/attention_priority.py` (the one canonical priority model); retires a 4th, previously-uncatalogued
alert system; fixes a real bug in `routers/notifications.py`; adds `OMEGA-020` through `OMEGA-022`.

## OMEGA-020 — Up to 3 independent writes can still fire for the same real-world deadline fact (High, trigger-path redesign out of this sprint's safe scope)

`case_actions` (Sprint 003's own Rule 1), `notifications.py::_generate_notifications` (its own `hitan_rok`
branch), and `services/event_bus.py`'s own `ROK_KRITICAN` handler (→ `proactive_alerts`) each independently
query `rocista`/`predmet_hronologija` and independently decide "this deadline is urgent" — for the SAME
underlying hearing/deadline. This sprint canonicalized the VOCABULARY all 3 use to describe urgency
(`shared/attention_priority.py`) but did NOT unify the WRITE paths — a lawyer could still, in principle, see
this fact represented 3 times (Workspace, the notifications bell, and wherever `proactive_alerts` surfaces)
with 3 different item ids, from 3 independent DB queries.

**Why not fixed this sprint**: making `notifications`/`proactive_alerts` literally READ FROM `case_actions`
instead of independently querying `rocista` is a real trigger-path redesign (new consumer relationships
between existing systems) — the mission's own explicit charter for this sprint was "kanonizovati postojeće"
(canonicalize existing), not restructure write paths, which is closer to new orchestration than
consolidation and carries real regression risk for 3 live, already-tested systems.

**Recommended direction**: a dedicated future sprint — likely: `notifications.py`'s own deadline-detection
branch and the `ROK_KRITICAN` handler both retired in favor of a NEW Case Evolution consequence that, when
`case_actions` creates/updates a `PRIPREMITI_PODNESAK` action, also writes the corresponding `notifications`/
`proactive_alerts` row — one decision, two projections, matching this sprint's own Phase 4 framing exactly,
just not executed yet.

**Severity**: High — this is the literal, remaining instance of "dva mesta koja odlučuju o istom događaju"
Phase 4 named as forbidden; found and precisely characterized, not fixed.

## OMEGA-021 — Deadline "critical/urgent" day-count thresholds disagree across systems (Medium, product decision needed)

Confirmed via `docs/omega/ATTENTION_SURFACE_REGISTRY.md`'s own table: `case_actions` uses ≤3 days = critical;
`routers/notifications.py` and `routers/dashboard.py` both use ≤2 days = urgent/hitan; the now-deleted
`api.py::GET /api/notifications` used ≤3 days OR `vaznost=="kritičan"`. 3-4 different, independently-chosen
thresholds for what "critical" means, still live in different systems.

**Why not fixed this sprint**: changing a threshold changes WHEN a real lawyer sees an alert — a genuine
behavior change, not a wording synonym. This sprint's own charter forbids introducing new logic/behavior
changes blind; picking a "correct" threshold is a product decision, not a code cleanup.

**Recommended direction**: a founder-level decision on the ONE correct day-count threshold for "critical,"
applied uniformly once `OMEGA-020`'s own write-path unification happens (fixing the threshold without fixing
the write-path duplication would just make 3 systems agree on a still-triplicated decision).

**Severity**: Medium — no system is "wrong" per se (each is internally consistent), but 3-4 different
answers to "how many days is urgent" is a real behavioral inconsistency a lawyer could notice.

## OMEGA-022 — `GET /api/predmeti/{predmet_id}/workspace` name-collides with the canonical `GET /api/workspace` (Low, naming only, not functional)

Found during this sprint's own Phase 1 pass: `api.py::predmet_workspace` (a real, live, per-CASE "everything
about this case" aggregation — stranke, dokumenti, rokovi, komentari, istorija — the actual backend for the
case-detail Cockpit panel) predates and is genuinely DIFFERENT IN SCOPE from Sprint 004/005's own portfolio-
wide `GET /api/workspace` ("what needs attention across ALL my cases") — not a functional duplicate, verified
by reading both. The NAME collision itself ("Case Workspace" vs. "Workspace") is a real clarity risk for
anyone reading route lists or API docs without the historical context this debt register provides.

**Why not fixed this sprint**: renaming a live, tested, `20/minute`-rate-limited route used by the case-detail
page is a bigger, riskier change (URL contract change, frontend update required) than this sprint's own
"canonicalize wording, don't restructure routes" scope.

**Recommended direction**: a future sprint could rename `predmet_workspace`'s own route to something
collision-free (e.g. `/api/predmeti/{id}/case-file` or `/api/predmeti/{id}/overview`) alongside a frontend
update — low urgency, purely for naming clarity.

**Severity**: Low — no functional bug, no user-facing confusion (the 2 endpoints are never shown side by
side), purely a maintainer/architecture-reading clarity concern.

## DELTA-005 — Scenario 4's own worked example (Evidence → Genome → Strategy → Timeline) does not match the built architecture (Informational, no fix needed)

The mission's own Sprint 004 charter described a hypothetical evidence-update cascade into Genome/Strategy/
Timeline. The real, certified architecture does not have this cascade — `NEW_EVIDENCE_REGISTERED`'s own
consequence list is `evidence_classification` only; Genome/Timeline updates a lawyer observes "around the
same time" come from the SIBLING `DOCUMENT_ACCEPTED` event, not from evidence registration triggering them.
Strategy is never auto-triggered by any event, by any pipeline, anywhere in the platform.

**Why not fixed**: there is nothing broken to fix — this is a documentation/expectation mismatch, not a code
defect. Building an actual cascade (evidence event → triggers → genome/strategy) would be NEW orchestration
capability (one event automatically triggering another), which Architectural Invariant 7 (see
`ARCHITECTURAL_INVARIANTS_REPORT.md`) explicitly certifies does NOT happen anywhere in this engine by design
— adding it now would violate the very invariant this sprint just certified, and is explicitly forbidden by
every Delta sprint's own "migrate, don't extend" charter.

**Severity**: Informational only — not a defect, not a regression, not left "for later." Recorded so the gap
between the mission's own illustrative example and the real system is never silently assumed to be true.

## DELTA-002 — CLOSED (Sprint 003): all 7 found scattered call sites migrated, zero bypass remaining

Sprint 001 migrated 1 (Pipeline C Genome). Sprint 002 migrated 3 more (Pipeline C Evidence Vault,
conflict-check, review-audit). Sprint 003 migrates the LAST 2 (Pipeline A's own Genome + Evidence Vault
triggers, `routers/rocista.py`'s own Genome trigger) and wires `ROCISTE_ZAKAZANO` — the last event type with a
genuine consequence need. Repo-wide grep (`tests/test_delta_sprint003_full_convergence.py::
test_no_new_direct_call_bypass_of_canonical_consequence_functions`, now an enforced regression test, not just
a one-time manual check) confirms zero remaining direct callers of `_run_genome_background`,
`klasifikuj_i_sacuvaj`, or `_run_conflict_check` outside `services/case_evolution.py` and each function's own
definition (plus `routers/intake.py`'s own deliberately-unmigrated direct HTTP endpoint, a synchronous
user-initiated query, not a reactive consequence — see `ORCHESTRATOR_OWNERSHIP_REPORT_SPRINT_003.md`).

**Closed, not merely narrowed** — this is the first `DELTA-XXX` item in the whole program to reach CLOSED
status rather than being carried forward across sprints.

**Severity**: N/A (closed).

## DELTA-004 — REVIEW_REJECTED's rollback is trivial-by-construction, not general-purpose (Low, by design)

`REVIEW_REJECTED`'s own "rollback" satisfies the mission's Test 2 requirement only because no consequence was
ever registered for it that mutates the case (deliberately — see `CASE_EVOLUTION_REGISTRY.md`'s "šta se
poništava" field). This is NOT a general rollback mechanism (still absent, `DELTA-003` unchanged) — if a
future event's rejection needs to undo an ALREADY-APPLIED consequence (not just prevent one from ever
running), a real rollback mechanism would be needed then, not before.

**Severity**: Low — named for future awareness, same reasoning as `DELTA-003`, no current need.
