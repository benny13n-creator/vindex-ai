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

## OMEGA-020 — Up to 3 independent writes can still fire for the same real-world deadline fact (PARTIALLY CLOSED, Final Sprint 007 — corrected scope, `proactive_alerts` leg remains High)

**UPDATE — Program Omega, Final Sprint 007 (2026-08-06):** `case_actions` → `notifications` is now a single
canonical write with a reconciled projection (`_consequence_project_case_actions_to_notifications`,
`services/case_evolution.py`, migration 101's own `dedupe_key`/partial-UNIQUE-index pattern, mirroring
migration 099). This closes the specific duplication this item originally warned about for the
Workspace/bell-icon pair.

**Correction to this item's own original assumption**: the original text above proposed retiring
`notifications.py`'s own deadline-detection branch entirely. Deeper investigation this sprint (tracing
every writer of `predmet_hronologija`, and `kreiraj_rociste`'s own actual insert statements) found that
assumption too narrow — `predmet_hronologija` is written by ~14 different files (contract deadlines,
Genome-extracted deadlines, document-extracted deadlines, a dedicated deadline-chain feature) that
`case_actions`' own Rule 1 never reads (it reads `rocista`, hearings only). Retiring `notifications.py`'s
own detection would have been a real coverage regression. **`notifications.py`'s own `predmet_hronologija`
detection was deliberately kept, unchanged** — see `docs/omega/CANONICAL_NOTIFICATION_ENGINE.md` for the
full reasoning.

**Remains open**: the `proactive_alerts` leg (`services/event_bus.py::on_rok_kritican`) is still an
independent write for the hearing-deadline fact, not unified with `case_actions`/`notifications` this
sprint — same original reasoning (different channel/consumer, not the same table) now formally documented
rather than merged. Its OWN internal duplicate-insert risk is tracked separately as `OMEGA-023`.

**Severity**: downgraded from High to Medium for the remaining scope — the specific duplication Phase 4
named as forbidden (Workspace vs. bell icon) is closed; the remaining `proactive_alerts` divergence is a
different-channel design choice, not an unresolved duplicate of the same UI surface.

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

---

## Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification & Trigger Engine

Full narrative: `docs/omega/OMEGA_FINAL_SPRINT_007_REPORT.md`, `TRIGGER_REGISTRY.md`,
`CANONICAL_NOTIFICATION_ENGINE.md`, `EVENT_LIFECYCLE_SPECIFICATION.md`,
`NOTIFICATION_DEDUPLICATION_REPORT.md`, `FORENSIC_CERTIFICATION_REPORT.md`. Fixes 2 real bugs
(`notifications.prioritet` schema drift, `routers/sms.py` dedup); builds
`_consequence_project_case_actions_to_notifications` (migration 101); amends `OMEGA-020` (partially
closed); adds `OMEGA-023` through `OMEGA-027`.

## OMEGA-023 — `proactive_alerts` has no DB-enforced dedup; its check-before-emit is a TOCTOU race (Medium, Final Sprint 007)

`shared/proactive_alerts.py::create_proactive_alert` (Program Alpha, 2026-08-04) is the canonical WRITE
PATH for `proactive_alerts` but performs an unconditional insert with no `dedupe_key`/unique-index concept.
Dedup instead happens at the 2 CALLERS that emit `ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN`
(`routers/matter_intel.py::_maybe_emit_health_and_deadline_events`, lines 145-171): each queries for an
existing UNREAD alert of the same type before calling `emit()`. This is a real, application-level
check-then-act race — 2 near-simultaneous case-opens for the same predmet could both pass the check before
either insert lands, producing 2 alert rows.

**Why not fixed this sprint**: a proper fix (a `dedupe_key` column + partial UNIQUE index on
`proactive_alerts`, mirroring migrations 099/101, plus updating both emitting call sites) is a real, safely
plannable change — but a new migration + 2 call-site updates, tested with the same rigor as this sprint's
SMS fix, exceeded the remaining time budget once the primary mission target (the `notifications`
projection) was proven correct.

**Recommended direction**: migration N — `proactive_alerts` gets a `dedupe_key` column + partial UNIQUE
index (`user_id, dedupe_key WHERE procitana=FALSE`), matching the now-2x-proven pattern; both emitters
build a stable key (e.g. `f"rok_kritican:{predmet_id}"`) instead of a pre-insert SELECT.

**Severity**: Medium — real race, but low practical frequency (requires near-simultaneous case-opens by
the same user for the same case).

## OMEGA-024 — `on_document_job_failed` has no consequence-ledger idempotency guard (Low, Final Sprint 007)

Unlike every `CONSEQUENCE_REGISTRY`-registered consequence, `on_document_job_failed`
(`services/event_bus.py:229-`) is a direct Event Bus subscriber with no `(event_id, consequence_name)`
completion check. A duplicate `events` row for the same failed intake job (e.g. a retried
`fail_intake_job` RPC call) could produce 2 `proactive_alerts` rows.

**Why not fixed this sprint**: genuinely rare trigger condition (requires a duplicate terminal-failure
event for the same job), and folding a direct Event Bus handler into the `CONSEQUENCE_REGISTRY` idiom
would be a small architectural change warranting its own review, not a same-sprint drive-by edit.

**Severity**: Low — rare trigger condition, single-alert consequence (not a cascading failure).

## OMEGA-025 — Log-after-send pattern in email/SMS reminders is not crash-atomic (Low, Final Sprint 007)

Both `email_notif.py` and `sms.py` send the message FIRST, then write the durable log row that prevents a
resend. A crash between those 2 steps could cause a duplicate send on the next cron run. Pre-existing in
both patterns; not introduced or worsened by this sprint's SMS fix (the fix closed the "2 separate,
successful runs" gap, not the "crash mid-run" gap, which is a different and smaller risk).

**Why not fixed this sprint**: closing this fully needs a different delivery architecture (log a "sending"
state before dispatch, reconcile after) — a real redesign, not a canonicalization.

**Severity**: Low — requires a crash in the exact window between send and log-write, on top of an already
rare double-invocation scenario.

## OMEGA-026 — `notification_log`/`email_notif_log` have no DB unique constraint (Medium, Final Sprint 007)

Confirmed via `migrations/048_reliability_hardening.sql:108-127`: both tables have regular (non-unique)
indexes only. Their own dedup (this sprint's SMS fix, and email's pre-existing pattern) is a
SELECT-then-INSERT application-level check — safe against sequential re-invocations, not safe against 2
truly concurrent invocations racing past the SELECT before either INSERT commits.

**Why not fixed this sprint**: both tables intentionally allow multiple legitimate rows per user/day (e.g.
a `deferred_quiet_hours` row followed later by a `sent` row for the same underlying reminder) — a naive
unique constraint would break that legitimate pattern. Designing the correct constraint shape (e.g. unique
on `(user_id, tip)` only among `delivery_status IN ('sent','deferred_quiet_hours')` rows) is a real schema
decision needing care, not a mechanical canonicalization.

**Recommended direction**: a partial UNIQUE index scoped correctly to "active" delivery statuses, once
designed and reviewed.

**Severity**: Medium — real gap, low practical exposure (both cron endpoints run on a fixed external
schedule, not naturally concurrent; exposure is an overlapping manual re-run).

## OMEGA-027 — `proactive_alerts.urgentnost` is a 4th, previously-uncatalogued priority vocabulary (Low, Final Sprint 007)

Found during this sprint's own Forensic Certification pass (Phase 8): `proactive_alerts.urgentnost`
(`hitna`/`normalna`/`visoka`, `shared/proactive_alerts.py`) is not among the 13 vocabularies Sprint 006's
own `ATTENTION_SURFACE_REGISTRY.md` catalogued, and is not in `shared/attention_priority.py`'s own
translation tables.

**Why not fixed this sprint**: `proactive_alerts` is a different table/consumer from the canonical
action-priority domain (see `OMEGA-023`'s own channel-separation reasoning) — merging its vocabulary in
would be scope creep beyond this sprint's own notification/trigger focus, and is itself contingent on
`OMEGA-023`'s own dedup fix landing first.

**Severity**: Low — documentation gap, not a functional bug; named so a future sprint doesn't have to
re-discover it.

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

---

## Program Sigma, Master Sprint 001 (2026-08-06) — Autonomous Legal Matter Construction Engine

Full narrative: `docs/sigma/SIGMA_MASTER_SPRINT_001_REPORT.md`, `END_TO_END_PIPELINE.md`,
`CASE_CONSTRUCTION_ENGINE.md`, `LEGAL_KNOWLEDGE_FLOW.md`, `AUTONOMOUS_CASE_BUILDING_SPEC.md`,
`SYSTEM_GAP_REPORT.md`. Fixes the mission's own primary-scenario chain break (`PREDMET_KREIRAN` never
emitted from Smart Intake — the platform's own dominant case-creation path never triggered mini-strategy/
HCC briefing/risk snapshot/Copilot recommendation/creation history); adds `SIGMA-001` through `SIGMA-004`.

## SIGMA-001 — Client-linking failure during Smart Intake finalize is silently swallowed (Medium)

`routers/smart_intake.py:1002-1058`'s own call to `shared/case_assimilation.py::resolve_client_ownership`
is wrapped in a bare, non-fatal try/except (line 1059) — a case can be fully complete by every other
measure (documents, Genome, deadlines, case_actions) with ZERO linked client and nothing anywhere flags
this as a failure vs. "genuinely no client mentioned in the uploaded documents."

**Why not fixed this sprint**: correctly surfacing this needs a product decision on WHERE/HOW to flag it —
a new Dashboard warning, a Case Ready Score deduction, an automatic retry, or a manual "link client" nudge
are all different UX choices with different implementation shapes, not a single mechanical fix.

**Recommended direction**: a founder-level decision on the right surfacing mechanism, then a small,
well-scoped follow-up.

**Severity**: Medium — real, silent data-completeness gap for a field the mission's own Phase 3 explicitly
requires, but not a data-loss or duplication bug.

## SIGMA-002 — Genome's contradiction diff matches by text prefix, not stable identity (Medium)

`routers/case_dna.py::_compute_delta` (lines 323-324) matches `kontradikcije` entries between Genome
refreshes by `opis[:60]` string-prefix set membership. Since each refresh is a full fresh GPT extraction
(not a diff of the model's own prior output), a semantically-identical contradiction phrased even slightly
differently between 2 calls registers as a false "1 eliminated + 1 new" churn rather than "unchanged."

**Why not fixed this sprint**: this is a live, GPT-facing extraction/diff contract — changing the matching
strategy (e.g. embedding similarity, or requiring the model to echo a stable per-contradiction ID) is a
real algorithm change requiring its own design and live-browser verification, out of a certification
sprint's own safe scope.

**Severity**: Medium — affects alert accuracy (`_delta_significant`'s own gating) for the mission's own
"Dodati dokument koji ruši prethodnu tvrdnju → Kontradikcija registrovana" scenario; the registration
mechanism itself works, its precision across repeated calls is what's bounded.

## SIGMA-003 — Document processing failures during finalize never reach the case-detail "what's missing" view (Low-Medium)

`routers/smart_intake.py:1150-1167`'s own whole-job decrypt/extract failure fails soft, producing a
per-document `povezan: false, razlog: "prazan_tekst"` entry ONLY in the finalize HTTP response itself — not
surfaced anywhere in `GET /api/matter-intel`'s own "what's missing" payload a lawyer sees when later
opening the case.

**Why not fixed this sprint**: needs a new persisted "processing failures" field/query on the case, a real
(if small) feature addition rather than a wiring connection.

**Severity**: Low-Medium — a lawyer who doesn't watch the upload response closely has no later way to
discover a specific document silently failed to process, directly relevant to the mission's own Phase 7
"šta nedostaje" requirement.

## SIGMA-004 — No DB-enforced uniqueness for client/case-number/document-content matching during intake (Medium)

Confirmed via migration grep: zero unique indexes on `klijenti(user_id, ime, prezime)`,
`predmeti(user_id, broj_predmeta)`, or `predmet_dokumenti(user_id, content_sha256)` —
`migrations/095_intake_bulletproofing.sql:26-28` creates a non-unique index for the last one. All 3
"find-or-create" mechanisms (`shared/case_assimilation.py`, `routers/smart_intake.py`'s own content-hash
check) are SELECT-then-INSERT application logic — the same TOCTOU race class this program has now found
repeatedly (`OMEGA-023`, `OMEGA-026`). Two truly concurrent finalize requests (e.g. 2 browser tabs) racing
on the same new client/case-number/document content could each pass their own check and both insert.

**Why not fixed this sprint**: each of the 3 tables needs its own schema review — `predmet_dokumenti` needs
`deleted_at`-scoping and cross-case-review-path interaction confirmed first; `klijenti`/`predmeti`
uniqueness needs product scoping decisions (case-insensitive matching? per-user only, or per-firm?) that
aren't mechanical. A single batch-upload request (up to 500-1000 documents) is NOT exposed to this race —
`finalize_intake_jobs_batch` calls `_finalize_intake_job_core` sequentially per job — only genuinely
separate, concurrent requests are.

**Recommended direction**: a dedicated future sprint, one migration + scoping decision per table, following
the now-twice-proven `dedupe_key` + partial UNIQUE index pattern (migrations 099/101).

**Severity**: Medium — real gap, bounded exposure (requires genuinely concurrent separate requests, not a
single large batch), same severity class as `OMEGA-023`/`026`.

---

## Program Sigma, Master Sprint 002 (2026-08-06) — Autonomous Evidence & Timeline Reconstruction Engine

Full narrative: `docs/sigma/SIGMA_MASTER_SPRINT_002_REPORT.md`, `TIMELINE_REGISTRY.md`,
`EVIDENCE_GRAPH_SPECIFICATION.md`, `CANONICAL_FACT_ENGINE.md`, `CONTRADICTION_ENGINE_SPECIFICATION.md`,
`TIMELINE_FORENSIC_REPORT.md`. Fixes 4 real bugs: a contradiction-identity flicker (shared/
contradiction_identity.py, closing `SIGMA-002`'s own precision gap for real) and 3 instances of an invalid
`"now()"` literal timestamp (`predmet_dokazi.deleted_at`, `predmet_dokumenti.klasifikovan_at` ×2 call
sites). Adds `SIGMA-005` through `SIGMA-010`.

## SIGMA-002 — CLOSED (was: Genome contradiction diff matches by text prefix, not stable identity)

**UPDATE — Program Sigma, Master Sprint 002 (2026-08-06):** Closed. `shared/contradiction_identity.py`
(new) anchors identity on `(lokacija_1, lokacija_2)` — the document/page citations Genome's own extraction
prompt already requires — instead of the free-text `opis`, used by both `routers/case_dna.py::_compute_delta`
and `services/case_evolution.py`'s own Rule 3 (`RAZRESITI_KONTRADIKCIJU`). Closing this ALSO fixed a
previously-unknown live bug in Rule 3 itself (see below) — the original deferral reasoning ("a live
GPT-facing extraction-contract change") turned out to be based on an incomplete read of the fix's own scope:
the actual fix touches only downstream identity matching on already-extracted fields, never the GPT prompt.
11 new tests (`tests/test_sigma_sprint002_contradiction_identity.py`).

## SIGMA-005 — `predmet_hronologija` conflates 2 different semantics under one schema (Low-Medium)

`services/case_evolution.py::_consequence_timeline_entry` (the one Case-Evolution-owned writer) never sets
`datum`/`datum_iso` — pure narrative log. All 14 other writers set `datum_iso` — dated-event entries. Same
table, same schema, distinguished only by whether `datum_iso` happens to be null.

**Why not fixed this sprint**: a schema split (2 tables, or a `tip` discriminator column + reader updates)
is a real migration + read-path changes across ~25 confirmed projection sites, out of a
certification-plus-targeted-fix sprint's own scope.

**Severity**: Low-Medium — works correctly today (readers already handle both shapes), a clarity/
maintainability concern more than a functional one.

## SIGMA-006 — Legal Reasoning Engine's own Evidence Graph is never auto-triggered by Case Evolution (Medium)

`migrations/076_legal_reasoning_engine.sql`'s own `reasoning_nodes`/`reasoning_edges`/`reasoning_evidence`
schema, populated by `services/legal_reasoning_engine.py::generate_reasoning_graph`, is a complete, working
evidence-to-claim graph — but only reachable via an explicit on-demand endpoint
(`POST /{predmet_id}/reasoning-graph/generate`), never wired into `DOCUMENT_ACCEPTED`/
`DOCUMENT_BATCH_COMPLETED`. A case built entirely through Smart Intake has zero reasoning-graph rows unless
a lawyer separately requests one.

**Why not fixed this sprint**: auto-firing a substantial GPT-driven graph-generation operation on every
document acceptance is a genuine new automatic AI-cost/latency commitment per document — a product decision
about cost/value tradeoff, not a mechanical wiring fix.

**Severity**: Medium — real capability, real gap in autonomy for the mission's own stated goal.

## SIGMA-007 — No FK linking evidence to the timeline point it belongs to (Medium-High)

No table anywhere links a `predmet_dokazi` row to a specific `predmet_hronologija` entry. A lawyer cannot
query "show me the evidence for THIS timeline event" — only the whole case's evidence and the whole case's
timeline, separately.

**Why not fixed this sprint**: requires new extraction/matching logic (matching evidence's own extracted
date/context against nearby timeline entries) that doesn't exist anywhere to reuse — new algorithmic
surface area, not a wiring connection, per this sprint's own founding principle against parallel algorithms.

**Recommended direction**: a nullable FK on `predmet_dokazi` → `predmet_hronologija.id`, populated at
evidence-classification time once a matching algorithm is designed.

**Severity**: Medium-High — the most significant Phase 7 finding; directly relevant to the mission's own
"jedinstvena vremenska linija" goal.

## SIGMA-008 — No per-evidence contradiction linkage (Medium)

Contradictions live only at the whole-case Genome level (`case_dna.kontradikcije`) — no column on
`predmet_dokazi` records "this specific evidence item is contested by document Y." `klasifikuj_i_sacuvaj`
performs whole-document classification, not cross-document contradiction comparison at the evidence-item
level.

**Why not fixed this sprint**: same reasoning as `SIGMA-007` — new matching logic, not existing-mechanism reuse.

**Severity**: Medium.

## SIGMA-009 — No revision/supersede/void semantics for `predmet_hronologija` entries (Medium)

Strictly append-only, zero UPDATE/DELETE call sites confirmed repo-wide. A later document cannot modify,
close, or void an earlier timeline entry — only add a new one.

**Why not fixed this sprint**: a minimal additive schema extension is feasible (`status`, `superseded_by`,
`voided_at` columns, default-active for existing rows) but the harder question — which lawyer/system action
actually triggers a supersede/void, and how a lawyer discovers a prior entry was superseded — needs product
input before implementation.

**Recommended direction**: see `CANONICAL_FACT_ENGINE.md`'s own "Recommended direction" section — a
starting schema sketch is already provided there.

**Severity**: Medium — real gap against the mission's own explicit Phase 3 requirement, bounded by the fact
that "never delete an old fact" is already satisfied by construction (append-only IS a valid, if minimal,
way to never lose data).

## SIGMA-010 — No SUPERSEDED-vs-UNKNOWN distinction when a contradiction stops being detected (Low-Medium)

When Genome's latest extraction no longer contains a previously-flagged contradiction, `case_actions`'
own `RAZRESITI_KONTRADIKCIJU` action closes — but nothing distinguishes "a lawyer resolved it," "a newer
document superseded the disputed fact," or "Genome simply failed to re-detect it this refresh" (a false
negative).

**Why not fixed this sprint**: distinguishing these needs either a live GPT-prompt/contract change (Genome
reasoning about ITS OWN resolution status per contradiction) or new deterministic cross-check logic that
doesn't currently exist — both real future work, not a same-sprint mechanical fix.

**Severity**: Low-Medium — the CLOSE itself is now stable and correctly identified (thanks to `SIGMA-002`'s
own closure); only the WHY of the close is unresolved.

## SIGMA-011 — 7 more `"now()"` literal-timestamp call sites exist outside the Evidence/Timeline domain (Medium, repo-wide sweep recommended)

While fixing the 3 Evidence Graph instances of this bug class, a repo-wide grep for the literal pattern
`"now()"` found 7 more call sites, all outside this sprint's own Timeline/Evidence/Contradiction scope:
`routers/client_twin.py:205,326`, `routers/knowledge_base.py:317`, `routers/knowledge_hygiene.py:179`,
`routers/knowledge_transfer.py:326,461`, `routers/sef.py:302`, `services/knowledge_hygiene.py:302,340` —
all writing `updated_at`/`status` fields the same broken way.

**Why not fixed this sprint**: none of these touch the Timeline/Evidence/Contradiction domain this sprint's
own mission scoped work to — Client Twin, Knowledge Base/Hygiene/Transfer, and SEF integration are
unrelated features. Fixing them requires the same care (confirm column type, confirm no test depends on the
literal, verify no other consumer expects a specific broken-but-tolerated shape) this sprint gave its own 3
fixes — bundling unrelated fixes into an already-large sprint risks both scope creep and under-verified
changes.

**Recommended direction**: a small, dedicated, mechanical cleanup sprint — same fix shape at each of the 7
sites (`datetime.now(timezone.utc).isoformat()` in place of the string literal `"now()"`), following the
now-4-times-proven pattern (Sprint 004's `case_actions.closed_at`, this sprint's 3 Evidence Graph fixes).

**Severity**: Medium — each site is a plausible live bug (rejected update or unusable stored value,
depending on the exact column and Postgres version's error-handling), same reasoning as this sprint's own
3 fixed instances, but unconfirmed against any one of these 7 specifically (no time was spent this sprint
verifying each column's actual type or checking whether client_twin/knowledge_base/knowledge_transfer/sef
have any test coverage that would need updating alongside the fix).

---

## Program Sigma, Master Sprint 003 (2026-08-06) — Legal Gap & Missing Evidence Engine

Full narrative: `docs/sigma/SIGMA_MASTER_SPRINT_003_REPORT.md`, `GAP_ENGINE_REGISTRY.md`,
`DOCUMENT_EXPECTATION_ENGINE.md`, `CHAIN_COMPLETENESS_SPECIFICATION.md`, `LEGAL_HYPOTHESIS_ENGINE.md`,
`FORENSIC_GAP_CERTIFICATION.md`. Fixes a live bug: 3 independent "missing evidence" generators
(`case_dna.nedostaje[]` plus 2 fully independent GPT calls inside `routers/copilot.py`) consolidated to 1,
via new `shared/gap_engine.py`. Also fixes a duplication this sprint itself introduced (a 2nd independent
text-classification cascade) in the same sprint it was written. Adds `SIGMA-012` through `SIGMA-017`.

## SIGMA-012 — Legal Reasoning Engine's own unsatisfied-LegalElement signal is discarded, not surfaced (Medium, deliberately not wired)

`services/legal_reasoning_engine.py::generate_reasoning_graph` only accepts a reasoning chain with
`>=1 fact AND >=1 norm` — any `LegalElement` GPT considers unsupported is silently `continue`-skipped
(lines ~328-332), never recorded anywhere. This is the one place in the codebase structurally positioned to
detect "this legal element has zero supporting evidence."

**Why not fixed this sprint**: the module's own docstring records an explicit, founder-stated Phase 0
constraint (2026-07-23): "Wired to nothing: no automatic trigger, no downstream consumer reads this yet.
Manual generation only." Surfacing this signal to the new Gap Engine would make it that module's first-ever
downstream consumer, directly overriding a deliberate, documented architectural staging decision — not this
sprint's call to make.

**Recommended direction**: whichever future sprint the founder authorizes to open "Phase 1" of the Legal
Reasoning Engine itself (the docstring's own language already anticipates this) should change the discard
to a record, feeding `shared/gap_engine.py` as a 4th normalizer.

**Severity**: Medium — real, valuable signal currently thrown away, but correctly gated behind an existing
founder decision, not a bug.

## SIGMA-013 — No document-to-document expectation reasoning exists (Medium-High)

Confirmed: nothing reasons "this contract references Annex B, is it present?" / "this is an appeal, is
there proof of filing?" — Genome's own `nedostaje[]` is holistic case-level judgment, `EXPECTED_DOCS` is
case-TYPE-level, neither is document-to-document.

**Why not fixed this sprint**: requires either a new GPT-prompt extension (Genome's own single extraction
pass, reasoning about referenced-but-absent companions) or new deterministic text-pattern matching — real
new algorithmic surface area needing live-browser verification before shipping, not a mechanical fix.

**Recommended direction**: extend Genome's own existing extraction call (not a new GPT call) with a new
output field for referenced-but-missing companions, normalized into `shared/gap_engine.py` as a new
`GAP_TIP_OCEKIVANI_PRILOG` type. See `DOCUMENT_EXPECTATION_ENGINE.md` for the full design.

**Severity**: Medium-High — this is the mission's own headline value proposition (the founder's own worked
examples: "nema dokaza o uručenju," "postoji ugovor, ali nema aneksa") and remains unbuilt.

## SIGMA-014 — No chain-completeness/pairing checks exist (decision↔delivery, appeal↔filing, punomoćje) (Medium-High)

Confirmed: `routers/ugovor_zastupanja.py` has zero check for whether a case has a power of attorney linked;
no file anywhere pairs a decision with a delivery receipt or an appeal with proof of filing.

**Why not fixed this sprint**: each pairing is a real legal-domain rule with real false-positive risk (not
every case needs a punomoćje; pairing appeal→filing-proof needs reliable document-pair classification) —
needs a founder-level decision on acceptable false-positive tolerance before shipping, matching this
program's own repeated discipline of not guessing at legal-correctness-sensitive product decisions.

**Recommended direction**: punomoćje presence (the simplest, lowest-risk of the 4 examples) once case-type
scoping is decided; document-pair chains share `SIGMA-013`'s own extraction-extension mechanism. See
`CHAIN_COMPLETENESS_SPECIFICATION.md`.

**Severity**: Medium-High — same headline-value-proposition reasoning as `SIGMA-013`.

## SIGMA-015 — Genome's own `nedostaje[]` has no stable identity across refreshes (Medium)

Unlike `kontradikcije[]` (fixed in Program Sigma Sprint 002 via `shared/contradiction_identity.py`),
Genome's own missing-evidence list has no anchor comparable to `lokacija_1`/`lokacija_2` — 2 refreshes
describing the same missing document in different words would be indistinguishable from 2 different
findings.

**Why not fixed this sprint**: unlike contradictions (which already had a formulaic citation field to
anchor on), `nedostaje[]` items may not always carry an equally stable field — needs the same kind of
careful design Sprint 002 did for contradictions, not assumed to be a trivial copy-paste of that fix.

**Recommended direction**: audit whether `nedostaje[].dokument` (the expected document's own name/category)
is stable enough to anchor on directly, or whether a new field needs adding to Genome's own extraction
output first.

**Severity**: Medium — a prerequisite for `SIGMA-016`'s own status lifecycle to mean anything reliable.

## SIGMA-016 — No persisted hypothesis-status lifecycle for Gap records (Medium)

`shared/gap_engine.py`'s own `hipoteza: bool` field satisfies the "never assert as fact" half of Phase 5's
own requirement; there is no persisted OPEN/CONFIRMED/REJECTED/RESOLVED/SUPERSEDED status anywhere — every
Gap is recomputed fresh on every read, no row records a lawyer having acted on one.

**Why not fixed this sprint**: depends on `SIGMA-015` (a stable identity to attach status to); also needs an
architecture decision (new `case_gaps` table vs. extending `case_actions.status`'s own CHECK constraint) —
a real design choice, not mechanical.

**Recommended direction**: a new `case_gaps` table modeled directly on the already-proven
`lessons_learned.status_lekcije` pattern (migration 039) — same `status`/separate-`pouzdanost`/
`potvrdio`/`potvrdjeno_at` shape — reconciled via the same target-vs-existing-diff idiom already proven 3
times (`case_actions` migration 099, `notifications` migration 101). See `LEGAL_HYPOTHESIS_ENGINE.md`.

**Severity**: Medium — real gap against the mission's own explicit Phase 5 requirement, bounded by the fact
that the "never silently confirm" half is already satisfied.

## SIGMA-017 — No unified read endpoint for the full Gap Engine aggregation (Low)

`shared/gap_engine.py::collect_case_gaps` (all 3 sources, full record shape including `hipoteza`/
`pouzdanost`) has no dedicated API endpoint — each existing consumer reads gap data through its own
pre-existing channel instead.

**Why not fixed this sprint**: mechanical, low-risk, but genuinely new API surface (route + response schema
+ frontend consideration) — deferred in favor of closing the live 3-generators bug within this sprint's own
time budget.

**Severity**: Low — no correctness risk, a real but non-urgent completeness gap.

---

## Program Sigma, Master Sprint 004 (2026-08-06) — Legal Case Readiness & Action Planning Engine

Full narrative: `docs/sigma/SIGMA_MASTER_SPRINT_004_REPORT.md`, `CASE_READINESS_MODEL.md`,
`ACTION_OWNERSHIP_REGISTRY.md`, `ACTION_EVIDENCE_CHAIN.md`, `LEGAL_OPERATIONAL_FLOW.md`,
`READINESS_FORENSIC_REPORT.md`. Fixes 2 live "AI-invented recommendation" bugs
(`routers/case_intelligence.py`'s AI Briefing, `routers/copilot.py::_handle_analiza_predmeta`) via new
`shared/case_readiness.py`. Builds the Legal Readiness Model (Phase 4) without becoming a 5th competing
readiness system. Adds `SIGMA-018` and `SIGMA-019`.

## SIGMA-018 — CLOSED (was: `routers/case_commander.py` is an entire module of 8 independent, evidence-less GPT recommendation generators)

**UPDATE — Program Sigma, Master Sprint 005 (2026-08-06):** Closed. A dedicated follow-up sprint (exactly
the "own dedicated future sprint" this item recommended) migrated all 6 genuinely-duplicated surfaces
(NEDOSTAJE/RIZICI/PREPORUCENI POTEZ/VREMENSKI PRITISAK per-case, plus RIZICI/PRIORITET portfolio-wide) to
read `case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py` directly — see
`docs/sigma/CASE_COMMANDER_DECISION_REGISTRY.md` for the full before/after. The 3 remaining GPT surfaces
(protivnikova strategija, sudska praksa, portfolio-wide kontradikcije/nepovezani dokumenti) have no
canonical equivalent to redirect to and are now structurally tagged `gpt_advisory` (never presented as
fact) via new `shared/commander_schema.py`.

**Why the originally-cited blocker ("each prompt needs its own live-browser verification pass") no longer
applied**: this sprint's own forensic re-verification found ALL 8 surfaces have ZERO live frontend callers
today (a correction to `docs/omega/SHADOW_WORKFLOW_AUDIT.md`'s own claim that the backend endpoints
"remain unaffected" by an earlier dead-code removal) — meaning no live user could be affected by the
migration, removing the exact risk that justified deferring this item in Sprint 004.

**Original text preserved below for history.**

---

**[CLOSED]** `routers/case_commander.py` is an entire module of 8 independent, evidence-less GPT recommendation generators (High, needs its own dedicated future sprint)

Confirmed this sprint via direct forensic fork investigation: `_COMMANDER_SYSTEM` (lines 36-62) independently
GPT-generates `NEDOSTAJE` (duplicates Gap Engine/Genome/`identify_case_problems`), `RIZICI` (duplicates
`risk_engine`), `PREPORUCENI POTEZ` (duplicates `case_actions`' own next-best-action), and `VREMENSKI
PRITISAK` (duplicates Rule 1/`rocista`) — from its own `_dohvati_predmet_kontekst` (lines 78-136), which
reads `predmeti`/`rokovi`/`predmet_dokumenti`/`predmet_komentari` DIRECTLY, never `case_actions`, `case_dna`,
or `identify_case_problems`. Also independently GPT-generating: `commander_quick_check` (line 282),
`commander_checklist` (line 338), `_cross_case_analiza`'s own portfolio-level `"prioritet"` object (lines
488-620, "koji JEDAN predmet treba da bude prioritet danas" — a 2nd fully independent portfolio-
prioritization surface alongside `cio.py`'s own), and `commander_jutarnji` (line 630) — a 3rd. None of the 8
surfaces has ANY evidence-chain discipline (`ACTION_EVIDENCE_CHAIN.md`'s own Phase 3 requirement) — no
`dokaz`-equivalent field, no stable identity, no dedupe protection.

**Why not fixed this sprint**: rewiring 8 independent GPT prompts to read canonical sources instead of raw
data is not a same-sprint, safely-completable fix — each prompt needs its own live-browser verification
pass (the exact discipline this whole engagement has applied to every GPT-facing change), and Case
Commander is evidently a substantial, actively-maintained feature (multiple sub-endpoints, portfolio-wide
analysis) whose behavior a rushed rewrite could visibly change for real users mid-sprint.

**Recommended direction**: its own dedicated future sprint — likely structured exactly like this whole
Program Sigma series (forensic audit already done here, fix in a focused follow-up), migrating each of the
8 surfaces to read `case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py` instead of independently
re-deriving, one surface at a time with its own test coverage.

**Severity**: High — the single largest, most concrete "parallel recommendation system" found in this
entire program's own 4-sprint history to date.

## SIGMA-019 — Workspace has no dedicated "ŠTA NEDOSTAJE" (missing-evidence) bucket (Medium)

`GET /api/workspace` (`routers/workspace.py:164-238`) covers DANAS/BLOKIRA/ČEKA/ZAVRŠENO via its own 6
buckets, but has no bucket surfacing `shared/gap_engine.py`'s own broader Gap Engine output directly —
missing-evidence items today only appear indirectly via `PRIBAVITI_DOKAZ` `case_actions` rows mixed into
the priority buckets; Gap Engine's own `hipoteza: True` (GPT-advisory, not yet backed by a deterministic
action) findings are not surfaced anywhere in Workspace at all.

**Why not fixed this sprint**: correctly building this requires a portfolio-wide fetch of Genome's own
`case_dna` across every case in a lawyer's workspace (not just the currently-open one), a real new query
pattern with genuine performance implications for a live, every-page-load endpoint — needs a load/latency
check before shipping, not a mechanical bucket addition.

**Recommended direction**: extend `routers/workspace.py::get_workspace` with a 7th bucket populated via
`shared/gap_engine.py::collect_case_gaps`, filtered to exclude anything already represented by an open
`PRIBAVITI_DOKAZ` action (avoiding double-display of the same fact) — the aggregation mechanism already
exists; what's missing is the portfolio-wide fetch/filter logic and a performance verification pass.

**Severity**: Medium — a real completeness gap against this sprint's own explicit Phase 6 requirement,
bounded by the fact that missing-evidence items ARE still visible (just mixed into other buckets, not in
their own dedicated one).

---

## Program Sigma, Master Sprint 005 (2026-08-06) — Case Commander Consolidation & Operational Brain Unification

Full narrative: `docs/sigma/SIGMA_005_REPORT.md`, `CASE_COMMANDER_ARCHITECTURE_MAP.md`,
`CASE_COMMANDER_DECISION_REGISTRY.md`, `GPT_BOUNDARY_POLICY.md`, `OPERATIONAL_BRAIN_CERTIFICATION.md`.
Closes `SIGMA-018` — migrates `routers/case_commander.py` from independent GPT decision-making to reading
`case_actions`/`shared/gap_engine.py`/`shared/case_readiness.py` directly, via new
`shared/commander_schema.py` (the CASE_COMMANDER_RESPONSE_SCHEMA). No new debt items — the sprint's own
forensic re-verification found the module has zero live frontend callers, removing the risk profile that
justified Sprint 004's own deferral.

## Program Tau, Master Sprint 001 (2026-08-06) — GPT-5.1 Integration Readiness

Full narrative: `docs/tau/GPT51_IMPLEMENTATION_ROADMAP.md` and the 7 other `docs/tau/*.md` analysis
deliverables. 8-agent forensic analysis of the whole AI call surface (138 call sites, 56 files) ahead of a
potential GPT-5.1 adoption. Implemented only proven-necessary, model-choice-independent hygiene fixes this
sprint (`ai_forensics.py` docstring correction, `shared/cost.py` silent-fallback warning, 2 new DC entries
for Sigma 005's own Case Commander functions, 1 new model-agnostic guard test) — no model string changed,
no new AI call added, per the mission's own explicit constraint. Six real findings were proven but
deliberately NOT implemented this sprint, each scoped larger than a hygiene fix and each meriting its own
dedicated future sprint the way Case Commander got in Sigma 005:

## TAU-001 — CLOSED (Program Tau, Master Sprint 002, 2026-08-06): was "No unified 'complete case context' builder exists"

**UPDATE — Program Tau, Master Sprint 002 (2026-08-06):** Closed. `shared/case_context.py::build_case_context()`
is now the single canonical Case Context Contract (13 fields, each carrying `{value, source, owner,
refresh, timestamp}`), and its Document Visibility Engine solves the "500 documents" problem directly:
`test_select_documents_500_scale_every_document_accounted_for`/`..._1000_scale_...` prove every document
is either in the bounded Layer 4 sample or listed with a working Layer 5 (`get_document_full_text`)
retrieval path — set-equality proven, not asserted. 3 of the 4 mission-named mandatory modules
(`copilot.py`, `case_intelligence.py`, `morning_briefing.py`'s flagship call site) now read from it; the
4th (`strategija.py`) was found to not be a context builder at all (no `predmet_id` on any request model)
and is correctly excluded, not silently skipped. See `docs/tau/CANONICAL_CASE_CONTEXT_CONTRACT.md`,
`DOCUMENT_VISIBILITY_ENGINE.md`, `AI_ENTRY_POINT_MIGRATION_REPORT.md`. Original entry preserved below.

**[CLOSED]** No unified "complete case context" builder exists (High)

**Found by**: Agent 3 (Context Engineering), Program Tau Master Sprint 001.

**What**: 4 independent, hand-rolled context-assembly functions feed GPT calls across the platform —
`case_commander.py::_formatiraj_kontekst` (10 of ≤20 fetched documents, 2000 chars/doc, Genome/evidence
fetched but never included in GPT-facing text), `case_intelligence.py::_build_context_text` (full Genome,
zero documents, zero evidence), `copilot.py` (document filenames only, content column excluded from the
query), `morning_briefing.py` (zero documents/Genome/evidence — metadata only). None gives GPT documents +
Genome + evidence together. For the mission's own named "500 documents" scale scenario, 490+ documents are
invisible to every one of these endpoints — not sampled, not summarized, never fetched.

**Why it matters for GPT-5.1 specifically**: a stronger reasoning model does not compensate for missing
input — it reasons more confidently over the same incomplete context, which is a bigger risk than a weaker
model doing the same. Unifying/completing case context is a prerequisite for a genuine "reasoning layer
above deterministic systems," not a follow-on nice-to-have.

**Why deferred**: this is a context-engine design project (arguably reusing `cross_doc.py`'s existing
stride-based sampler, which already solves the same problem in an unrelated endpoint family), not a
hygiene fix. Rushing it risks exactly the kind of quality/testing shortfall the founder's "brutal
precision" instruction exists to prevent.

**Severity**: High — this is the anchor item any future GPT-5.1 reasoning-layer sprint should resolve
first, per Agent 3/8's own recommendation.

## TAU-002 — `case_intelligence.py`/`copilot.py`'s "canonical override" is a GPT-fallback, not a removal (Medium)

**Found by**: Agent 5 (Legal AI Governance), Program Tau Master Sprint 001; independently corroborated by
Agent 1.

**What**: both modules' next-action logic calls `top_open_action(case_actions)` and uses it when an open
action exists — but falls back to GPT's own invented guess when `case_actions` is empty. Prior sprints'
own documentation described these as "migrated" (Sprint 004); this sprint found, from current code, that
the GPT-invention path is dormant, not removed. Same problem class Sigma 005 fixed structurally in Case
Commander via prompt narrowing, not applied here.

**Severity**: Medium — narrower in scope than TAU-001/TAU-004, a plausible small follow-up sprint on its
own (2 files, already-identified fallback branches to remove).

## TAU-003 — `morning_briefing.py` has zero `case_actions` awareness (Medium-High)

**UPDATE — Program Tau, Master Sprint 002 (2026-08-06):** Partially addressed, not closed. The flagship
`_generiši_briefing` call site now shows each case's canonical `readiness.status` alongside its name
(`shared/case_context.py::build_case_context(..., include_documents=False)`) — GPT is no longer reasoning
about a fully blind case list. **The core finding below is still true**: "Danas zahteva pažnju"/"Preporuka
za danas" are still GPT-authored, not read from `case_actions` — Tau 002's own mission was context
*visibility*, not decision-*authorship* boundary (that remains this item's own open concern; see
`docs/tau/AI_ENTRY_POINT_MIGRATION_REPORT.md`'s explicit scope-boundary note). Original entry below is
otherwise unchanged and still accurate for the recommendation-authorship question.

**Found by**: Agent 5 (Legal AI Governance) and Agent 3 (Context Engineering), Program Tau Master Sprint 001.

**What**: `routers/morning_briefing.py`'s "Danas zahteva pažnju" (2-4 prioritized actions) and "Preporuka
za danas" are built purely from raw context text (rokovi/predmeti/ročišta strings) with no `case_actions`
read or override at all — the same shape of violation `case_commander.py` had before Sigma 005, in a
module that was flagged as out-of-scope back in Sigma 004 and remains unfixed.

**Severity**: Medium-High — a daily-digest surface a lawyer reads every morning presenting an
independently-invented priority list is a direct instance of the exact risk this whole Sigma/Tau program
exists to close.

## TAU-004 — `strategija.py`'s `_V2_SYSTEM` independently invents risks/gaps/next-steps (Critical)

**UPDATE — Program Tau, Master Sprint 002 (2026-08-06):** Scoping correction, finding otherwise unchanged.
Tau 002's own forensic re-verification found `routers/strategija.py` has **no `predmet_id` field on any
of its 7 request models** — it is a "paste your own case text" tool with zero DB access to real case
records, not a case-ID-driven endpoint (`docs/tau/CONTEXT_BUILDER_REGISTRY.md`). This means a future fix
for THIS item cannot simply redirect `_V2_SYSTEM`'s output to `case_actions`/`gap_engine` the way Case
Commander was fixed in Sigma 005 — there is no `predmet_id` to look those up BY yet. Whoever picks up this
item will need `TAU-009` (below) resolved first, or will need to scope the fix to only the (theoretical)
future `predmet_id`-driven invocation mode. The underlying finding — GPT invents risks/gaps/next-steps in
one JSON call with its own priority vocabulary — remains fully valid for however `strategija.py` is called
today.

**Found by**: Agent 5 (Legal AI Governance) and Agent 1 (AI Architecture Auditor), Program Tau Master
Sprint 001.

**What**: `strategija.py`'s `_V2_SYSTEM` prompt (~L349-371) asks GPT for `kljucni_rizici`,
`nedostajuci_dokazi`, and `sledeci_koraci` (each carrying its own `prioritet`) in a single JSON call, with
no `case_actions`/`gap_engine`/`identify_case_problems` read anywhere in the file — a 3-way independent
duplicate of exactly the categories Sigma 005 consolidated in Case Commander. `strategija.py` also has the
second-highest OpenAI call-site count in the codebase (11 sites, per Agent 1).

**Severity**: Critical — the largest single remaining instance of the fragmentation class this whole
Sigma/Tau program has been closing sprint by sprint. Strong candidate to be the next dedicated
consolidation sprint after this one, using Case Commander's Sigma 005 migration as the direct template
(reuse `shared/gap_engine.py`/`shared/case_readiness.py`/`shared/commander_schema.py`, do not reinvent).

## TAU-005 — `ai_client.py`'s guard/provenance patch does not cover the Responses API (Low today, blocking if ever triggered)

**Found by**: Agent 2 (OpenAI Integration) and Agent 4 (Security), Program Tau Master Sprint 001.

**What**: `shared/ai_client.py::_patch_prompt_guard` patches `Completions.create`/`AsyncCompletions.create`
at the SDK class level — it does not patch `openai.resources.responses`. Zero call sites use the Responses
API today (grep-confirmed, zero hits for `.responses.create(`), so this is not a live gap. It becomes one
the moment any future code — including a GPT-5.1 migration, if GPT-5.1's own API surface prefers
Responses — adds a `client.responses.create(...)` call site without first extending the guard.

**Severity**: Low today (dormant), but must be treated as a hard prerequisite — not an afterthought — the
moment any Responses API call site is proposed. Not scheduled; tracked so it isn't forgotten.

## TAU-006 — Strict structured outputs never enabled anywhere (Low, available lever)

**Found by**: Agent 2 (OpenAI Integration), Program Tau Master Sprint 001.

**What**: 60 call sites use loose `{"type": "json_object"}` mode (no schema conformance guarantee); the
one call site using `"type": "json_schema"` (`main.py`) sets `"strict": False`. No call site anywhere uses
OpenAI's `strict: True` structured-outputs mode or the SDK's `.parse()`/`response_model=` convenience path.

**Severity**: Low — not a defect, an unused hallucination-reduction lever. Candidate for opt-in adoption
per call site once a specific consumer is proven ready to depend on the stricter guarantee (Agent 7's
test-strategy scope, not implemented here).

## TAU-007 — No GPT-4o vs. GPT-5.1 shadow-comparison harness exists yet (Informational — blocked on Section 0)

**Found by**: Agent 7 (Testing Strategy), Program Tau Master Sprint 001.

**What**: Agent 7 designed (not implemented) a 3-stage methodology — shadow logging, offline replay,
promotion gate — for safely comparing model output without letting the comparison itself become a new
source of truth. Building it is explicitly blocked on resolving `GPT51_INTEGRATION_ANALYSIS.md`'s Section
0 (confirming the actual current, non-deprecated model ID) — building a comparison harness against a
possibly-already-retired model would be wasted effort.

**Severity**: Informational — correctly sequenced as blocked, not forgotten.

## Program Tau, Master Sprint 002 (2026-08-06) — Canonical Case Context Engine

Full narrative: `docs/tau/TAU_MASTER_SPRINT_002_REPORT.md` and its 5 sibling deliverables in `docs/tau/`.
Closes `TAU-001` (see updated entry above). Partially addresses `TAU-003` (readiness context now visible;
decision-authorship boundary still open). Amends `TAU-004`'s own scoping given the `strategija.py` finding
below. 2 new debt items:

## TAU-008 — Document Visibility Engine's Layer 5 is not wired into any live GPT tool-calling loop (Low)

**Found by**: this sprint's own Phase 3 implementation, flagged explicitly rather than silently left
implicit.

**What**: `shared/case_context.py::get_document_full_text()` is implemented, tested, and proven to
correctly retrieve any document not included in a given call's Layer 4 excerpt sample. It is not yet
called automatically by any consumer's own GPT tool-calling loop when a lawyer's query names a document
outside that sample — Tau Sprint 001 already found tool calling essentially unused in legal-reasoning
call sites platform-wide, so wiring this live is a materially larger, separate change than proving the
retrieval mechanism itself works.

**Severity**: Low — the guarantee this sprint required ("no document permanently invisible, always
retrievable on demand") holds structurally; this item is about making that retrieval automatic for an end
user, not about a missing safety property.

## TAU-009 — `routers/strategija.py` has no `predmet_id`-driven invocation mode (feature gap, not defect)

**Found by**: Phase 1 forensic sweep (Program Tau Master Sprint 002), resolving an open question Tau
Sprint 001 itself left unresolved.

**What**: none of `strategija.py`'s 7 request models can reference an existing case by id — every call
requires the caller to paste case text directly. This blocks `TAU-004`'s own eventual fix (there is no
`predmet_id` to read `case_actions`/`gap_engine` findings BY) and blocks this module from ever using the
Canonical Case Context Contract the way the other 3 mandatory Phase 5 modules now do.

**Severity**: not a defect — `strategija.py` was apparently designed as a text-in/text-out tool
deliberately. Tracked because 2 other debt items (`TAU-004`) depend on it being resolved first; a founder
decision on whether a `predmet_id` mode is actually wanted is a prerequisite, not an engineering call.

## Program Tau, Master Sprint 003 (2026-08-06) — Canonical AI Decision Boundary

Full narrative: `docs/tau/SPRINT_003_REPORT.md` and its 5 sibling deliverables in `docs/tau/`. Closes
`TAU-002` and `TAU-003` (see updated entries below). Confirms `TAU-004`'s own severity/blocker (`TAU-009`)
still stands, unchanged. 1 new debt item.

## TAU-002 — CLOSED (Program Tau, Master Sprint 003, 2026-08-06): was "case_intelligence.py/copilot.py's 'canonical override' is a GPT-fallback, not a removal"

**UPDATE — Program Tau, Master Sprint 003 (2026-08-06):** Closed. Both files' `sledeci_korak` overrides
are now unconditional — `case_intelligence.py`/`copilot.py::_handle_analiza_predmeta` no longer even ask
GPT for this field; when `case_actions` has nothing open, an honest "Nema otvorenih akcija" statement
replaces the old GPT fallback. Proven by
`test_briefing_states_no_open_action_instead_of_falling_back_to_gpt_program_tau_003` and
`test_analiza_predmeta_states_no_open_action_instead_of_falling_back_to_gpt_program_tau_003`. Original entry
preserved below.

**[CLOSED]** `case_intelligence.py`/`copilot.py`'s "canonical override" is a GPT-fallback, not a removal (Medium)

## TAU-003 — CLOSED for the flagship call site (Program Tau, Master Sprint 003, 2026-08-06): was "morning_briefing.py has zero case_actions awareness"

**UPDATE — Program Tau, Master Sprint 003 (2026-08-06):** Closed for `_generiši_briefing` (the flagship,
highest-visibility call site — `GET /api/briefing/daily` + the cron job). "Danas zahteva pažnju"/"Ključni
rok"/"Preporuka za danas" are now built entirely in code from `case_actions`/`rocista`/`rokovi`, ranked by
`shared/attention_priority.py::canonical_sort_key` — GPT is asked for exactly one opening sentence,
structurally incapable of reaching the 3 decision-bearing sections (proven by
`test_gpt_cannot_inject_fake_actions_into_danas_zahteva_paznju_program_tau_003`, a direct poisoned-response
attack). `_ai_prioritizacija_alertova` was already correctly scoped (unchanged). `today_focus` remains
unmigrated — see `TAU-010` below. Original entry preserved below.

**[CLOSED for `_generiši_briefing`]** `morning_briefing.py` has zero `case_actions` awareness (Medium-High)

## TAU-010 — `morning_briefing.py::today_focus` still lets GPT pick freely, with an inconsistent fallback (Medium)

**Found by**: Phase 1 forensic sweep (Program Tau Master Sprint 003), a "bonus finding" not part of the
original TAU-003 scope.

**What**: `today_focus`'s system prompt ("izaberi JEDNU najvazniju akciju") lets GPT choose freely among
supplied candidates on the success path, with zero deterministic ranking beforehand. The EXCEPTION fallback
path, by contrast, IS deterministic (`hitni_rokovi[0]`, earliest-deadline-first, since the underlying query
uses `.order("datum")`) — meaning the two paths can legitimately disagree about what "most important" means,
and nothing catches it. Not fixed this sprint (out of the flagship-call-site scope this sprint prioritized);
the fix pattern is already established by `_generiši_briefing`'s own Tau 003 migration (reuse
`top_open_action`/`canonical_sort_key`, apply the same "GPT phrases, doesn't decide" restructure here too).

**Severity**: Medium — `today_focus` is, like the rest of `morning_briefing.py`, confirmed DEAD/no-UI
(`docs/tau/AI_DECISION_SURFACE_MAP.md`'s own live-caller re-verification), so there is no live user-facing
risk today; tracked so the inconsistency doesn't get inherited by a future feature that wires this endpoint
into a real UI without first fixing it.

## Program Tau, Master Sprint 004 (2026-08-06) — Canonical Legal Reasoning & GPT-5.5 Intelligence Layer

Full narrative: `docs/tau/TAU_004_REPORT.md` and its 5 sibling deliverables in `docs/tau/`. 6 new debt
items, none rushed — this sprint's own scope (the whole platform's GPT reasoning pipeline, not 4 files)
surfaced findings far larger than one sprint could safely fix; each below is named precisely instead.

## TAU-011 — CLOSED (Program Tau, Master Sprint 005, 2026-08-06): was "court_predictor.py's predmet_id is accepted but never used to fetch case context"

**UPDATE — Program Tau, Master Sprint 005 (2026-08-06):** Closed. All 7 endpoints now call
`shared/case_context.py::build_case_context()` (via a thin, fail-soft wrapper,
`_dohvati_case_context_ako_postoji`) whenever `predmet_id` is present. `prediktuj_ishod`/`battle_report`
use full mode (real document excerpts, since evidentiary strength is their whole job); the other 5 use
lightweight mode. Re-proven fresh before any code changed (Phase 1's own forensic re-verification, not
assumed from the original finding) — see `docs/tau/COURT_PREDICTOR_FORENSIC_REPORT.md`. A genuinely new
finding from the deeper pass: the live frontend's own main "Predikcija ishoda" tool sends NO `predmet_id`
at all (`stratPokreni()`'s own payload) — only `battle_report`'s own separate function conditionally sends
one (`activePredmetId`, when available). The migration is therefore conditional by design: real case
context is used when available, current (pre-migration) behavior is preserved exactly when it isn't — not
a forced requirement that broke the tool's own general-purpose "paste your case text" use case. 21 new
tests (`tests/test_tau005_court_predictor_migration.py`), including a direct adversarial proof that a
canonically CRITICAL_GAP case cannot receive a confident high win-probability even when GPT itself returns
one. Original entry preserved below.

**[CLOSED]** `court_predictor.py`'s `predmet_id` is accepted but never used to fetch case context (Critical)

**Found by**: Phase 1 forensic pipeline map, Program Tau Master Sprint 004 — the sprint's own single most
surprising finding.

**What**: all 7 endpoints (`prediktuj_ishod`, `battle_report`, `hearing_prep_brief`, `argument_reputation`,
`judge_profile`, `opponent_intel`, `confidence_check`) accept `payload.predmet_id`, but it is used
exclusively for audit/provenance plumbing (`_ai_case_ctx`, `decision_log` inserts) — never to query
`predmeti`/`case_dna`/`predmet_dokazi`/`case_actions`. The actual reasoning input is whatever free text the
caller supplies fresh in the request body every call. A lawyer passing a real, tracked case ID gets a
prediction that never reflects that case's current Genome, documents, evidence, or open actions — if the
case has since changed, these endpoints have no way to know.

**Severity**: Critical — this is a live, paid, heavily-used feature family producing legal predictions that
silently ignore the platform's own tracked truth about the case they claim to be about. Not fixed this
sprint: wiring `build_case_context()` (or a scoped subset) into 7 endpoints' existing prompt-construction
logic, without regressing any of them, is a Sigma-005-scale project requiring its own dedicated sprint with
full per-endpoint testing, not a Phase 9 patch.

## TAU-012 — 14+ more case-linked files never migrated onto `build_case_context()` (High)

**UPDATE — Program Tau, Master Sprint 007 (2026-08-06):** `case_commander.py` is migrated (see
`docs/tau/CASE_COMMANDER_CONSOLIDATION.md`) — not via the Factory's own context-injection template, but via
the SECOND migration shape Tau 006's own simulation predicted: duplicate-computation-elimination.
`case_commander.py` no longer independently calls `calculate_procesni_rizik`/`identify_case_problems`/
`collect_case_gaps`/`compute_case_readiness` (structurally proven by an AST walk, not a string grep —
`tests/test_tau007_case_commander_consolidation.py::test_no_direct_calls_to_duplicated_reasoning_functions`).
Count revised from 15+ to 14+. `zadaci.py::ai_analiziraj_predmet` remains the one other confirmed instance
of this specific duplicate-computation sub-case — see `docs/tau/REASONING_REGISTRY.md` and
`docs/tau/PARALLEL_REASONING_AUDIT.md` (Tau 007's own broader reasoning census, which additionally found 3
MORE modules in this same family not previously named here: `api.py::predmet_workspace`, `matter_intel.py`,
`ccc.py`, `dashboard.py`). Next-sprint priority order: `docs/tau/TAU_008_HANDOVER.md` (supersedes
`TAU_007_HANDOVER.md`, which proposed this exact migration and is now executed).

**UPDATE — Program Tau, Master Sprint 006 (2026-08-06):** `hearing_cc.py` — this entry's own "sharpest
instance" — is migrated (see `docs/tau/HEARING_CC_MIGRATION_REPORT.md`), via the newly-built and now-proven
**Canonical Context Migration Factory** (`docs/tau/CANONICAL_CONTEXT_FACTORY.md` + `MIGRATION_TEMPLATE.md`).
Count revised from 16+ to 15+. A fresh, from-source census (`docs/tau/GPT_MODULE_CENSUS.md`) found the
remaining backlog is more precisely ~17 candidates at endpoint/module granularity (finer than this entry's
original file-level count) — including 2 not on the original list at all (`api.py::predmet_workspace`,
`api.py::predmet_ai_preporuka`). 3 further modules were simulated against the Factory (not migrated) this
sprint — `case_commander.py`, `digital_twin.py`, `zadaci.py::ai_analiziraj_predmet` — see
`docs/tau/FACTORY_CERTIFICATION.md`. Next-sprint priority order and rollout plan: `docs/tau/TAU_007_HANDOVER.md`
(supersedes the prior sprint's own `TAU_006_HANDOVER.md`, which proposed building the Factory this sprint
built).

**UPDATE — Program Tau, Master Sprint 005 (2026-08-06):** `court_predictor.py` is migrated (`TAU-011`
closed) and is no longer part of this count. Count revised from 17+ to 16+; the file list below is
otherwise unchanged and none of it was touched this sprint (out of scope by the mission's own explicit
"jedini cilj ovog sprinta je Court Predictor" instruction).

**Found by**: Phase 1 forensic pipeline map, Program Tau Master Sprint 004.

**What**: `drafting.py`, `matter_intel.py`, ~~`hearing_cc.py`~~ (migrated, Tau 006), `evidence_graph.py`,
`multi_agent.py`, `digital_twin.py`, `decision_replay.py`, `strategy_simulator.py`, `health_index.py`,
`outcome_intel.py`, `precedenti.py`, `zastarelost.py`, `evidence.py`, `doc_templates.py`, `zadaci.py` each
has its own independent, bespoke `predmet_id`-keyed context fetch — confirmed via grep, none imports
`shared.case_context`. ~~`case_commander.py`~~ (migrated, Tau 007) and `zadaci.py::ai_analiziraj_predmet`
are a genuinely different sub-case (Tau 006 finding, Tau 007 additionally found `api.py::predmet_workspace`/
`matter_intel.py`/`ccc.py`/`dashboard.py` belong to the same sub-case): each independently calls
`services/risk_engine.py`/`shared/gap_engine.py`/`shared/case_readiness.py` directly — the SAME functions
`build_case_context()` calls internally — meaning their own migration eliminates duplicate computation, not
just adds missing fields. See `docs/tau/GPT_MODULE_CENSUS.md` (Tau 006) and `docs/tau/REASONING_REGISTRY.md`
(Tau 007) for the fresh, endpoint-level census superseding this list's own file-level granularity.

**Severity**: High — this is the same fragmentation Tau 002 built `build_case_context()` to end, just not
yet finished. A full migration of 17+ files is explicitly out of "fix everything safely fixable without
changing architecture" — each file needs its own careful, tested migration (see Sigma 005's Case Commander
treatment as the template), not a batch change.

## TAU-013 — Case Context contract missing 4 checklist items with data that already exists elsewhere (Medium)

**Found by**: Phase 2 context-quality audit, Program Tau Master Sprint 004, against the mission's own
15-item checklist.

**What**: OCR metadata (`intake_documents.ocr_confidence`, plus an unused real FK path via
`predmet_dokumenti.source_intake_job_id`), Client history (`client_twin_profili`), Previous strategies
(`case_patterns`/`lessons_learned`/`decision_log`) all have real, already-collected data that
`case_intelligence.py` reads through its own separate extra queries — none is part of the canonical
13-field `build_case_context()` contract itself. Separately: `deadlines` reads only `rocista`;
`case_commander.py`'s own unmigrated builder still separately reads a 2nd table, `rokovi`, for the same
"date the lawyer must act by" concept — never reconciled. (Judge history's own gap — `firm_memory.py`,
dead — is the SAME pre-existing `ALPHA-005`, not counted as new here.)

**UPDATE — Program Tau, Master Sprint 006 (2026-08-06):** the `rokovi`/`rocista` split independently
corroborated 3 more times this sprint's own Phase 1 census + Phase 7 simulation: `decision_replay.py`,
`zadaci.py::ai_analiziraj_predmet`, and `digital_twin.py` all separately query `rokovi` alongside canonical
`deadlines`' own `rocista` source — 4 independent files total now confirmed. `docs/tau/TAU_007_HANDOVER.md`
recommends this now warrants its own small, focused future sprint (contract-expansion vs. `rokovi`
deprecation decision) rather than continuing to accumulate as a side-finding of unrelated migrations.

**Severity**: Medium — expanding the canonical contract's own schema is a real, valuable, and safe
ADDITIVE change (new dict keys, no breaking change for existing consumers) — but deciding exactly how
`case_intelligence.py`'s own redundant fetches should fold into the contract, and resolving `rokovi` vs
`rocista`, deserves its own careful pass, not a rushed schema change appended to an already-large sprint.

## TAU-014 — CLOSED (Program Tau, Master Sprint 005, 2026-08-06): was "court_predictor.py's win-probability cites no specific precedent"

**UPDATE — Program Tau, Master Sprint 005 (2026-08-06):** Closed, via the exact fix this entry's own
original text recommended. `_rag_praksa_blok()` now returns `tuple[str, list[dict]]` — the existing text
block plus a structured `[{"sud": ..., "broj": ...}, ...]` list of what was actually retrieved. Both
`prediktuj_ishod` and `battle_report` now return this as `koriscena_praksa` in their own response. Deliberately
does NOT ask GPT to self-cite which precedent it used (would introduce a new hallucination-grounding
validation problem, closer to a parallel mechanism than this entry's own "same shape, new field, no new
mechanism" recommendation) — instead honestly reports what was searched/found, letting the reader judge
plausibility themselves. Proven by `test_prediktuj_ishod_koriscena_praksa_is_actual_rag_results_not_gpt_claim`
in `tests/test_tau005_court_predictor_migration.py`. `PROGBETA-001`'s own broader 5-way win-probability
fragmentation is unaffected — still open, still a separate concern. Original entry preserved below.

**[CLOSED]** `court_predictor.py`'s win-probability cites no specific precedent (Medium)

**Found by**: Phase 4 Legal Reasoning Verification, Program Tau Master Sprint 004
(`docs/tau/LEGAL_REASONING_VERIFICATION.md`).

**What**: `procenat_min`/`procenat_max`'s own prompt allows GPT to lean on retrieved sudska praksa, but the
required JSON schema has no field for which specific retrieved precedent(s) informed the number, and the
retrieved `decision_number` is never linked back to the returned percentage. A lawyer reading "55-70%" has
no way to know whether any real precedent drove that number. Recommended fix (not implemented): add a
`koriscena_praksa: [str]` field, reference-checked against the retrieved set the same way
`validate_dok_reference` already checks a `DOK-XX` claim — same shape, new field, no new mechanism.

**Severity**: Medium — deliberately bundled with `TAU-011` (both live in `court_predictor.py`, both need
their own dedicated sprint) rather than patched in isolation mid-diagnosis of the bigger context-gap issue.
Also cross-references the pre-existing `PROGBETA-001` 5-way win-probability fragmentation
(`docs/architecture/DECISION_REGISTRY.md`) — even consolidating that fragmentation to one generator
wouldn't close this specific gap unless that generator also starts citing its own sources.

## TAU-015 — SEC-003 prompt guard's threshold may pass a subtler injection attempt (Medium-High)

**Found by**: Phase 6 adversarial testing, Program Tau Master Sprint 004 (`tests/test_tau004_adversarial.py`).

**What**: `shared/ai_client.py`'s prompt guard uses a cumulative risk-score threshold (`BLOCK_THRESHOLD =
0.90`) that requires a dense, multi-pattern injection payload to trigger blocking — confirmed still
correctly blocking the existing test suite's own proven "loud" payload (no regression), but a shorter,
single-phrase injection attempt scored below threshold during exploratory testing and would reach the real
API unblocked.

**Severity**: Medium-High — not fixed this sprint. Tuning a security-relevant threshold (lowering it, or
adding a new pattern) without extensive false-positive testing against real Serbian legal text (which can
legitimately contain phrases like "ignoriši prethodnu presudu") risks over-blocking legitimate use — this
needs its own dedicated security-focused pass with a proper test matrix, not a same-sprint reaction to one
exploratory finding.

## TAU-016 — 3 smaller adversarial gaps found, none exploited, all named (Low-Medium)

**Found by**: Phase 6 adversarial testing, Program Tau Master Sprint 004.

**What**: (1) two near-identical `predmet_dokazi` rows are silently double-counted by
`shared/case_context.py::_group_dokazi` — no duplicate-detection exists. (2) `timeline`
(`predmet_hronologija`) has zero chronological-plausibility validation — an event dated before its own
logical predecessor passes through silently. (3) Statute/article citation grounding is sharply
inconsistent: `services/legal_reasoning_engine.py` structurally cannot cite an ungrounded statute (SOURCE-n
built only from real RAG retrieval), but `strategija.py`/`copilot.py`/`case_commander.py` have zero such
mechanism, and `shared/genome_validator.py::_validate_clan_brojevi` is confirmed a soft plausibility
range-check only (catches an impossible article number for a given law type), not a real existence check.

**Severity**: Low-Medium each — none represents an active exploit today (all are honest gaps, not
regressions), grouped here rather than as 3 separate entries since none is independently urgent enough to
warrant its own dedicated sprint; worth revisiting together if a future sprint targets evidence-integrity
or citation-grounding specifically.

## TAU-017 — CLOSED (Program Tau, Master Sprint 008, 2026-08-06): was "routers/cio.py GPT independently decides priority/risk with no deterministic grounding"

**UPDATE — Program Tau, Master Sprint 008 (2026-08-06):** Closed. `cio.py` migrated onto
`build_case_context()` (`docs/tau/EXECUTIVE_CONSOLIDATION.md`) — every `_kompaktan_predmet` signal
(readiness, gaps, contradictions, deadlines) now reads the canonical, gap_engine/case_readiness-normalized
source instead of raw `case_dna` fields directly, closing a 3rd, previously-unknown deadline source
(`case_dna.rokovi_kriticni`, alongside the already-known `rocista`/`rokovi` split) along the way.
`portfolio_zdravlje.kriticnih_rizika` now uses the platform's own canonical CRITICAL_GAP/BLOCKED definition
instead of Genome's own ad hoc kriticnost≥85 heuristic. GPT's own remaining latitude
(`najveci_rizik`/`kriticni_rok`/etc.) is now checked, not trusted: every `predmet_id` GPT references is
validated against the real portfolio (reusing `shared/genome_validator.py::validate_predmet_reference`,
the same function `case_commander.py::_cross_case_analiza` already uses); `najveci_rizik.kriticnost` is
capped when the referenced case's own canonical readiness is READY; `kriticni_rok` is cross-checked against
that case's own real canonical deadlines. All 3 proven adversarially (poisoned GPT responses), plus a
positive control confirming a real, canonically-backed claim survives unchanged. 20 new tests
(`tests/test_tau008_cio_consolidation.py`). Original entry preserved below.

**[CLOSED]** `routers/cio.py` GPT independently decides priority/risk with no deterministic grounding (Medium-High)

**Found by**: Phase 5 GPT Boundary Audit, Program Tau Master Sprint 007 (`docs/tau/CANONICAL_REASONING_CERTIFICATION.md`).

**What**: `cio.py`'s own system prompt asks GPT to independently invent `kriticnost` (a 0-100 urgency
score), `najveci_rizik`, `kriticni_rok`, and `cio_preporuka` (a single recommended action for today) from
raw portfolio signals — not from `case_actions`/`identify_case_problems`/`compute_case_readiness`, the
platform's own canonical sources for exactly these concepts. This is not a new discovery — the file's own
header comment already documents it as a deliberate, previously-escalated deferral (Program Omega Sprint
004: "the canonical answer is `GET /api/workspace`; this module remains a supplementary strategic
perspective... out of safe scope"). Re-confirmed still open, still real, during this sprint's own broader
GPT Boundary Audit — named explicitly here (a formal, numbered debt item) rather than left as a comment
only future readers of this one file would find.

**Severity**: Medium-High — a genuine GPT Boundary Policy violation (Sigma 005's own principle, which
`case_commander.py` itself now fully honors after Tau 007's own migration) in a LIVE, BILLED module. Not
fixed by Tau 007 (out of that sprint's own named scope — `case_commander.py` specifically) or any prior
sprint, deliberately: changing a live GPT prompt's own behavior/output shape carries real user-facing risk
that deserves its own dedicated, careful sprint with live-traffic verification first (same discipline Tau
005/006/007 each applied to their own single-file targets), not a bolt-on to an unrelated mission.
Prioritized in `docs/tau/TAU_008_HANDOVER.md`.

## TAU-018 — `routers/health_index.py` is a fully independent Firm Health Score + GPT-decided "Chief Partner" recommendation system (High)

**Found by**: Phase 1 Executive Census, Program Tau Master Sprint 008 (`docs/tau/EXECUTIVE_INTELLIGENCE_MAP.md`).

**What**: a complete, independent 6-component "Firm Health Score" (0-100) — Deadline Pressure / Case
Strength / Billing / Client Engagement / Portfolio Risk / Caseload — entirely hand-rolled, zero use of any
canonical engine. Case Strength reads Genome's own `case_dna.snaga_predmeta_procent` directly (the same
bypass `cio.py` had before Tau 008); Portfolio Risk reads a raw `predmeti.rizik_nivo` column directly, never
`calculate_procesni_rizik`. `_compute_chief_partner` asks GPT to independently generate "3 concrete actions
a partner would take today," fed only by this file's own bespoke `alerts` list — never `case_actions`,
never Workspace, never Case Commander. This is a live, GPT-decided, fully independent "what should the firm
do today" recommendation system running alongside `case_actions`/Workspace, feeding on a wholly separate
scoring model — the same class of violation `TAU-017` named for `cio.py`, in a different file, with its own
additional independent scoring layer `cio.py` didn't have.

**Severity**: High — confirmed live (`_healthIndexLoad`, wired in `dash_load()`). Not fixed this sprint
(Tau 008's own named scope was `cio.py` specifically, per this whole program's "one file at a time"
discipline). Likely a larger migration effort than `cio.py` itself, since it requires reconciling an entire
independent scoring model, not just swapping a context source — see `docs/tau/TAU_FINAL_HANDOVER.md` for
why this is named as the single highest-priority target for any future consolidation work, not folded into
a quick follow-on.

## LAMBDA-001 — Supabase client has no explicit request timeout, inheriting the library's own 120-second default (Medium-High)

**Found by**: Reliability Auditor, Program Lambda Master Sprint 001.

**What**: `shared/deps.py::_get_supa` calls `create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)` with no
`ClientOptions` — confirmed via direct package introspection that `supabase-py`'s own default
(`postgrest_client_timeout=120`) applies, unexamined, to every single Supabase call this platform makes.
Contrast: every GPT call in this codebase uses an explicit, deliberately short timeout (e.g. `timeout=25.0`
on `_pozovi_*_api` functions across ~90+ files). If Supabase degrades (slow, not fully down), a request can
hang for up to 2 minutes — indistinguishable from a frozen page to a lawyer waiting on it, and far worse
than any other timeout in this codebase.

**Why not fixed this sprint**: the blast radius is the entire platform — every single Supabase call, not
one file. Choosing a safe replacement value requires knowing the real distribution of this app's own
Supabase call durations in production (a large batch write, a bulk export, a big portfolio query could
legitimately take longer than a typical request); guessing a number (e.g. "30 seconds") without that data
risks introducing a NEW failure mode — legitimate slow-but-successful operations start failing that
previously would have succeeded. This is exactly the kind of platform-wide, unverifiable-without-production-
data change this program's own standing discipline (e.g. `TAU-015`'s own prompt-guard threshold, left
untouched for the identical reason) says not to guess at.

**Severity**: Medium-High — a real gap, not yet an incident, but the single largest "silent hang" risk
found this sprint. Recommend: instrument actual Supabase call-duration distribution in production first
(a metric, not a guess), then set an explicit, data-justified timeout (likely well under 120s for the vast
majority of calls, with a small number of legitimately-longer operations carrying their own override).

## LAMBDA-002 — `evidence_graph.py`'s GPT-asserted `OSPORAVA` (contradicts) edges are reference-validated but not truth-validated (Medium)

**Found by**: AI Reasoning Auditor, Program Lambda Master Sprint 001.

**What**: GPT decides which evidence nodes contradict each other (`OSPORAVA` edges). `validate_graph_edge_references`
correctly checks that both referenced nodes actually exist (a real, working hallucination guard against
inventing a fake node) — but nothing checks whether an asserted contradiction between two REAL nodes is
actually a true contradiction. Structurally softer than the numeric-cap gaps this whole program has closed
elsewhere (Court Predictor/Hearing CC/CIO/Digital Twin): there is no existing deterministic ground truth
(no "these 2 facts canonically contradict" source) to check the claim against, unlike a readiness status
that already exists independently of GPT's own output.

**Why not fixed this sprint**: no safe fix exists without inventing a NEW verification mechanism (explicitly
forbidden — "Zabranjeno: ... paralelna logika"), and this whole program's own standing discipline is to
close gaps by reusing/grounding against an EXISTING canonical source, not to build a new one under sprint
pressure. Closing this properly would require either a 2nd-pass GPT self-consistency check (a real design
question: does that introduce its own hallucination-validation problem, the same category of risk this
program has repeatedly avoided for other fields) or accepting it as a permanent, disclosed limitation of
what evidence-graph contradiction detection can prove.

**Severity**: Medium — no live exploit, a real but bounded epistemic gap (same category, lower severity,
as `TAU-012`'s risk_engine family — a genuine gap named, not a fresh security hole).

## LAMBDA-003 — `routers/onboarding.py`'s richer onboarding system sits fully dead behind a much thinner live one (Medium, product decision needed)

**Found by**: Legal Workflow/UX/Product Auditor, Program Lambda Master Sprint 001.

**What**: `routers/onboarding.py` (5 endpoints — `/stanje`, `/korak`, `/kompletiran`, `/demo-predmet`,
`/checklist`) has zero callers anywhere in `static/vindex.js` or `index.html`, confirmed by direct grep, not
the dead-route audit script's own claim. The LIVE onboarding mechanism is a separate, much simpler
welcome-overlay (`onboardingCheck()`/`onboardingDismiss()`) gated by `localStorage`, posting to a completely
different endpoint (`/api/auth/onboarding/complete`) outside this router entirely. The dead router's own
`/demo-predmet` endpoint name suggests a demo-case auto-creation feature for new users — exactly the kind of
thing that would help a first-day beta lawyer get oriented, currently unused.

**Why not fixed this sprint**: this is real, un-invested backend capability sitting disconnected — but
wiring it in is a PRODUCT decision (does the founder want a demo-case-driven onboarding flow before beta,
or is the existing thin overlay sufficient?), not a bug fix. The mission's own explicit prohibition
("dodavanje novih funkcionalnosti") forbids building new frontend wiring for this under this sprint's own
adversarial-audit charter, even though the backend already exists. Flagging for a founder decision, not
guessing at the answer.

**Severity**: Medium — not broken (the live thin overlay works), but a real missed-value gap worth a
deliberate yes/no before beta, not an accidental discovery after.

**Merged with `LAMBDA007-DEAD-001`** (Program Lambda, Final Certification 008, 2026-08-07): Certification
007 independently rediscovered this exact finding — same 5 endpoints, same root cause, same live
replacement at `api.py:2424` — under a separate ID, without cross-checking this already-open entry first.
This is now the single tracked entry for `routers/onboarding.py`; `LAMBDA007-DEAD-001` below is kept only
as a historical record pointing back here, not a second open item.

## LAMBDA-004 (addendum to `SEC-004`) — no systematic cross-route ownership (IDOR) regression suite exists (Medium-High, process gap)

**Found by**: Security Auditor, Program Lambda Master Sprint 001, re-confirming `SEC-004`'s own prior
recommendation was never built.

**What**: `tests/` has exactly 3 ownership-test files, each scoped to one PAST incident
(`test_sec001_predmet_ownership.py`, `test_doc_templates_ownership.py`,
`test_beta_lockdown_zadaci_predmet_idor.py`) — not a systematic sweep covering every `predmet_id`/
`klijent_id`/`dokument_id`-scoped mutation route. This engagement's own history shows this exact bug class
(a missing ownership check on a resource-scoped endpoint) recurring across many independent sprints (SEC-001
→ `zadaci.py` (`BL-001`) → `copilot.py`, each found by a DIFFERENT reviewer looking at a DIFFERENT file) —
the absence of a standing regression mechanism means the next instance will most likely be found by a beta
user, not a test. This sprint's own spot-check (5-8 endpoints, including the recently-Tau-modified
`hearing_cc.py`) found no NEW live instance — but a spot-check is not the same guarantee a systematic sweep
would provide.

**Why not fixed this sprint**: building a genuinely systematic, low-false-positive ownership-sweep test
(one that enumerates every resource-scoped route automatically rather than being hand-written per incident)
is itself a real testing-infrastructure investment, not a "found and fixed one bug" task — the mission's
own "Zabranjeno: kozmetički refaktoring... optimizacije bez dokaza" bar argues against building new test
infrastructure speculatively within an audit sprint whose own job was finding problems, not building
prevention systems. Recommend as its own small, focused future task.

**Severity**: Medium-High — a process gap with a proven track record of letting real bugs through, not a
currently-known live vulnerability.

## LAMBDA-005 (addendum to `TAU-018`) — `health_index.py`/`dashboard.py::command_center` fetch all of a user's own `predmeti` rows with no `.limit()` (Low-Medium)

**Found by**: Performance Auditor, Program Lambda Master Sprint 001.

**What**: Both endpoints fetch every `predmeti` row for a user unconditionally — `health_index.py`
additionally selects the full `case_dna` JSONB blob per row. A real cost at 1,000+ cases for a single firm,
distinct from `health_index.py`'s already-tracked `TAU-018` finding (independent scoring model + GPT-decided
recommendations) — this is a scaling concern in the SAME file, not the same bug.

**Why not fixed this sprint**: `health_index.py` is already named as this program's own #1 priority for a
full future consolidation sprint (`TAU-018`) — bounding this ONE query in isolation, ahead of that larger
migration, risks a throwaway fix that gets redone (or conflicts with) whatever shape the eventual
consolidation takes. Bundling this observation into the SAME future sprint rather than patching it now.

**Severity**: Low-Medium — no case in this platform's own current scale is anywhere near 1,000 cases per
firm yet; a real but not urgent finding.

## LAMBDA-OWN-001 — `routers/integracije.py::post_webhook_clio` trusts an attacker-controlled `vindex_user_id` in the webhook body (Medium, architecture decision needed)

**Found by**: API Penetration Auditor, Program Lambda Certification 002 (Ownership & IDOR Certification).

**What**: `POST /v1/webhook/clio` (`routers/integracije.py:275-314`) authenticates the REQUEST via a single
shared `CLIO_WEBHOOK_SECRET` HMAC signature, then reads `user_id = payload.get("vindex_user_id")` straight
from the attacker-controlled JSON body and inserts a `predmeti` row owned by that id (`:301-313`). The HMAC
proves "this call came from someone who knows the platform-wide Clio secret" — it does NOT prove "this call
is authorized to act as this specific Vindex user." Anyone holding `CLIO_WEBHOOK_SECRET` (any firm with Clio
integration enabled, today) can create a `predmeti` row attributed to an ARBITRARY other Vindex user by
setting `vindex_user_id` to their id. Impact is CREATE-only (no existing data is read, modified, or deleted)
— a victim gets a spurious "Clio predmet" they didn't create, not a disclosure of their real data. The
sibling endpoint `POST /v1/predmeti` (`:255-272`) is NOT affected — it correctly derives `user_id` from
`key_row["user_id"]`, the caller's own resolved API-key identity, not a body field.

**Why not fixed this sprint**: closing this properly means redesigning the Clio integration's own auth model
— today it is ONE shared secret for the whole platform with a body field naming the target user; the correct
shape is a PER-CONNECTION credential (an API key or OAuth token issued to one specific Vindex user's Clio
connection, with `user_id` derived from THAT credential the same way `/v1/predmeti` already does it, never
from the request body). That is a scoped but real architecture change to how Clio connections are
provisioned/stored, not a one-line ownership filter — the mission's own "no guessing at a fix, no new
capabilities" rule argues against inventing a per-connection credential scheme inside a certification sprint
whose job is finding and minimally fixing, not redesigning an integration's auth model.

**Severity**: Medium — real and provably exploitable by anyone with `CLIO_WEBHOOK_SECRET`, but bounded to
CREATE-only spurious-row pollution with no cross-tenant read/write of existing data, and gated behind a
secret that is not broadly distributed (Clio integration is opt-in, not default-enabled).

## LAMBDA003-AUTH-001 — auth fallback silently skips live revocation check on any Supabase-side exception (ACCEPTED RISK)

**Found by**: Authorization Architect + Adversarial Certification, Program Lambda Certification 003.

**What**: `shared/deps.py::_verify_token` (~line 216-244) tries a live `supa.auth.get_user(token)` call first
(would immediately catch a server-revoked session), but on ANY exception (a bare `except Exception`, no type
filtering, no re-raise) falls through to `verify_token_local(token)` — a function whose own docstring states
it has no live revocation check and is "NOT sufficient for authorization" alone. `get_current_user()`, the
dependency gating every protected route, uses exactly this fallback chain as its sole verification path — the
documented safety invariant ("authorization is done exclusively by `get_current_user` further down the
chain") is factually false, since `get_current_user` IS the described-as-insufficient fallback.

**Reproduction trace**: revoke a user's Supabase session while their JWT is still unexpired → the next
`auth.get_user()` call throws for any transient reason (network blip, Supabase-side hiccup) → local
signature+expiry-only verification silently accepts the token, granting continued access for the remainder
of the JWT's lifetime. **Not attacker-triggerable on demand** — requires an external fault condition on
Supabase's own side.

**Why ACCEPTED RISK, not fixed**: closing this is a genuine security-vs-availability policy decision. Failing
closed on any Supabase outage (reject every request while `auth.get_user` is degraded) closes this narrow
revocation-lag window but takes the whole platform down for EVERY user during any Supabase-side blip, not
just revoked ones. The current fallback trades a narrow, external-fault-gated exposure window for platform
availability. This is the founder's call, the same class of decision `LAMBDA-001` (Supabase timeout) was
correctly deferred for — no production data exists on real Supabase fault frequency/duration to make this
tradeoff concrete.

**Severity**: Medium in theory, low in practice — requires an external fault the attacker cannot trigger, and
is bounded to already-revoked-but-unexpired tokens (typical JWT lifetime, not indefinite).

## LAMBDA003-EVT-001 — TOCTOU race in Canonical Consequence Engine's dedup check, same-tenant only (ARCHITECTURAL DEBT)

**Found by**: Event Bus Isolation + Adversarial Certification, Program Lambda Certification 003.

**What**: `services/case_evolution.py:1039-1052` — the per-(event, consequence) idempotency check is
read-then-write across two separate round trips (`_get_consequence_status` read, then `_mark_pending`, an
`upsert` that overwrites rather than blocking on an existing row), not one atomic claim. Under genuine
concurrent redispatch of the SAME event (requires migration 091's atomic-claim RPC being unapplied live —
`KEYSTONE-007` — OR a handler running longer than that RPC's own 30-second stale-claim window), two
concurrent calls can both pass the read-check before either writes `pending`, and both then execute the
consequence — gated only by whether that specific executor happens to be independently idempotent (only
verified for `_consequence_genome_refresh`, not the full `CONSEQUENCE_REGISTRY`). Independently re-verified:
the race stays strictly within one event's own `(event_id, consequence_name)` identity — no shared mutable
state exists that could let this cross into a different user's/predmet's event.

**Why not fixed this sprint**: the correct fix (a `INSERT ... ON CONFLICT DO NOTHING` claim for the fresh
case, plus a conditional `UPDATE ... WHERE status IN ('failed', 'stale-pending')` reclaim for retry/crash
-recovery cases — achievable via `supabase-py`'s `ignore_duplicates=True` upsert mode, no new migration
needed since the table already has `created_at`/`updated_at` and a `UNIQUE(event_id, consequence_name)`
constraint) requires choosing a staleness-cutoff NUMBER for "how long is a pending claim still legitimately
running vs. abandoned." Choosing this without production data on real executor runtime distributions is the
exact "guessing a number" pattern this engagement has repeatedly refused to do (`LAMBDA-001`'s own precedent).

**Severity**: Low-Medium — same-tenant duplicate side-effect only (a duplicated notification/audit row, not a
security leak), requires a narrow, hard-to-trigger concurrency window.

## LAMBDA003-RLS-001 — `kancelarija_clanovi` RLS enabled with zero policies, recursively breaks 10 dependent policies (ARCHITECTURAL DEBT, confirmed not exploitable)

**Found by**: Database Security + Adversarial Certification, Program Lambda Certification 003.

**What**: `migrations/018_kancelarija.sql:48` enables RLS on `kancelarija_clanovi` with zero `CREATE POLICY`
ever written for it. 10 policies across 9 tables (`firm_style_profile`, `zadaci`, `memory_entries`,
`partner_profiles`, `judge_patterns`, `client_memory`, `memory_graph_edges`, `workflow_templates`,
`workflow_instances`, `workflow_steps`) build a "user is a firm member" branch via a subquery against this
table, which for `authenticated`/`anon` roles always returns 0 rows since the table itself has no policy to
allow the read — permanently `false`-ing that branch, even for real firm members. No `SECURITY DEFINER
is_member_of()` helper (the standard Postgres pattern avoiding this exact trap) exists anywhere in the repo.

**Direction is over-restrictive, not under-restrictive — cannot leak data.** Confirmed not exploitable: the
entire backend uses the service-role client (bypasses RLS entirely); the only anon-key client
(`static/vindex.js`) touches none of the 9 affected tables.

**Why not fixed this sprint**: a correct fix needs a new `SECURITY DEFINER is_member_of()` helper and 10
policy updates — a real RLS-architecture decision, made non-urgent by RLS already being decorative for the
actual request path (service-role bypass, per `migrations/059`'s own comment: "defense-in-depth, not real
app logic").

**Severity**: Low — not exploitable, purely a correctness/defense-in-depth gap.

## LAMBDA003-AUTH-002 — "firm admin" defined inconsistently across `kancelarija.py` vs. `zadaci.py`/`workflow.py` (ARCHITECTURAL DEBT, drift risk not confirmed bypass)

**Found by**: Vertical Privilege Escalation, Program Lambda Certification 003.

**What**: `routers/kancelarija.py:66-68` (`_get_firma_for_admin`) treats only literal `kancelarije.admin_uid
== uid` as admin. `routers/zadaci.py:83-112`/`routers/workflow.py:45-72` instead treat
`uloga in ("admin", "partner")` as admin — a broader principal set. No evidence a "partner"-role member can
currently reach a `kancelarija.py`-gated owner-only action (that file never consults
`kancelarija_clanovi.uloga`), so this is not a confirmed bypass today — but it is real definitional drift that
could become exploitable the next time a new admin-gated action reuses the wrong helper's notion of "admin."

**Why not fixed this sprint**: unifying "admin" needs a single source-of-truth decision (strict owner-only,
or role-inclusive?) applied consistently — a design choice, not a patch.

**Severity**: Low today, Medium if left unaddressed as more admin-gated features are added.

## LAMBDA003-TEST-001 — `sys.modules["main"]` mock leak between test files (CLOSED — FIXED, Program Lambda Certification 003A)

**Found by**: coordinator, during Program Lambda Certification 003's own full-regression verification (not a
mission-charter finding — pytest hygiene, not a product or security defect).

**What**: `tests/test_doc_pitanje_api.py` and `tests/test_uploaded_doc_api.py` both install a `MagicMock()`
into `sys.modules["main"]` at module-COLLECTION time (`sys.modules.setdefault("main", _mock_main)`), and
never restored it. Since pytest collects every test file before executing any of them, this mock is already
installed by the time any earlier-alphabetically-executing file's tests run — `tests/
test_akcija2_faza4_2026_07_24.py`'s tests, which do a plain `import main`, silently get the mock instead of
the real module, causing `main._batch_segments_za_map(...)` to return a `MagicMock()`. Confirmed pre-existing
(the hazard is self-documented in `tests/test_ask_agent_gate_bias.py`'s own docstring, predating this sprint)
and confirmed unrelated to any of this sprint's code changes (affected file passes 23/23 in isolation).

**Partial mitigation applied this sprint**: added a `teardown_module` hook to both offending files, restoring
`sys.modules` after their own tests finish — real protection for tests executing after them, but doesn't fix
`test_akcija2_faza4_2026_07_24.py` since the pollution happens at collection time, before teardown can run.

**Why not fully fixed in Certification 003**: a complete fix appeared at the time to require restructuring
these 2 files' own mocking strategy — a larger, out-of-scope change against that sprint's own discipline
against unrelated refactoring, so it was correctly deferred rather than guessed at.

**CLOSED in Program Lambda, Certification 003A (2026-08-06)**: a dedicated regression-recovery sprint, run
under a strict "at least 2 independent investigations must agree on root cause before implementation" rule,
found a smaller, lower-risk fix than the one originally estimated: moving the 5 `sys.modules.setdefault(...)`
calls in both files from bare module level into a `setup_module(module)` hook — the exact missing counterpart
to the `teardown_module` hook already added, deferring the mutation to immediately before each file's own
first test executes instead of at collection time. Verified safe because the one endpoint under test that
touches `main` (`routers/dokument.py::dokument_pitanje`) does its own function-body-local re-import, resolved
fresh at call time, independent of `api.py`'s own top-level binding order. 2 independent investigations
converged on the root cause; a 3rd, dedicated forensic-review fork tried to disprove the fix and found no
flaw (verified standalone-file correctness, `-k`-filter correctness, no skip/xfail shortcuts, no other latent
instance of the same bug class). Full suite: 2,991 passed, 1 skipped, 0 failed (was 2,984/1/7) — exact +7/-0
delta, zero collateral regressions. Full detail: `docs/lambda/ROOT_CAUSE_ANALYSIS.md`,
`docs/lambda/FIX_JUSTIFICATION.md`, `docs/lambda/REGRESSION_CERTIFICATION_REPORT.md`.

**Severity**: was Low (test-infrastructure only, zero production impact) — now resolved, N/A.

## LAMBDA004-AI-001 — zero explicit OpenAI timeout across ~63 client construction sites (Medium-High, needs production data)

**Found by**: AI Systems Reliability Engineer, Program Lambda Certification 004.

**What**: no file passes `timeout=` to `OpenAI()`/`AsyncOpenAI()` construction or any individual `.create()`
call, anywhere in the repo. SDK default (`openai==2.29.0`): up to 10 minutes per attempt, plus the SDK's own
internal `max_retries=2` sitting underneath `shared/llm_retry.py`'s own 3 application-level attempts — a
materially longer and less predictable worst-case latency than the retry decorator's own "max 3 attempts"
framing implies.

**Why not fixed this sprint**: choosing a single blanket timeout value across ~63 heterogeneous call sites
(a quick classification call vs. a large Map-Reduce synthesis call have very different realistic latency
profiles) without production latency-distribution data is the exact "guessing a number" pattern this
engagement has repeatedly refused to do (`LAMBDA-001`'s own precedent for the Supabase client timeout).

**Recommended next step**: instrument first (latency logging/metrics around the highest-traffic call sites),
then set timeouts from real p99 data, likely tiered by call shape rather than one blanket value.

**Severity**: Medium-High — the single most likely "found nothing until it's in production under load" gap
this certification surfaced, but not independently confirmed to have caused any incident yet.

## LAMBDA004-NOTIF-001 — `notifications` polling system lacks `proactive_alerts`'s own durability guarantees (Medium, product decision needed)

**Found by**: Reliability Architect + Chaos Engineer, Program Lambda Certification 004.

**What**: two parallel, independent notification-creation systems exist with different reliability
guarantees. `shared/proactive_alerts.py::create_proactive_alert` (event-bus-driven) retries up to 3 attempts
and writes a durable `proactive_alert_insert_failed` audit entry on exhaustion — a lost alert is never
silent. `routers/notifications.py::_generate_notifications` (polling-driven, generates rok/neaktivnost
alerts on page load) has no such protection — a bare `try/except: logger.error(...); return 0`, indistinguishable
from "nothing new to notify."

**Why not fixed this sprint**: a genuinely different, narrower-scoped system than the one first suspected
(an earlier investigation pass named a dead function, `trigger_notifikacija`, before the live equivalent was
found) — retrofitting it needs its own scoped decision (match `create_proactive_alert`'s own pattern, or
consolidate the two systems onto one path), not a rushed patch bundled into this sprint.

**Severity**: Medium — no confirmed production incident, a structural asymmetry found by audit.

## LAMBDA004-DB-001 — `content_sha256` document dedup is application-level only, narrow TOCTOU (Low, unconfirmed exploitable)

**Found by**: Database Reliability Engineer, Program Lambda Certification 004.

**What**: `predmet_dokumenti.content_sha256` (migration 095) is backed by a plain, non-unique index — dedup
enforced via a SELECT-then-INSERT check, not a DB constraint. Two finalize calls for identical document
content, same user, within a narrow concurrent window, could theoretically both pass the check before either
insert lands — structurally the same shape as the now-fixed `LAMBDA003-EVT-001`, narrower in practice
(requires identical content + genuinely concurrent timing).

**Why not fixed this sprint**: not verified exploitable, narrower and lower-priority than the confirmed
findings this sprint actually fixed.

**Severity**: Low.

## LAMBDA004-EVT-002 — Event Bus dead-letter has no active alerting/paging (Low-Medium, new capability needed)

**Found by**: Distributed Systems Engineer, Program Lambda Certification 004.

**What**: `dispatch_pending_events` correctly stops retrying after `MAX_DISPATCH_ATTEMPTS=5`, writes an
explicit `"DEAD_LETTER after N attempts"` marker, and logs at CRITICAL — durable and provable, never silent.
But this is purely passive (queryable/log-visible only) — nothing actively pages a human, despite the log
message's own text asserting manual intervention is needed.

**Why not fixed this sprint**: closing this is a genuinely NEW capability (an alerting/paging integration),
explicitly out of this sprint's "no new capabilities" charter, not a bug fix.

**Severity**: Low-Medium — recoverability itself is not at risk, only operator visibility into WHEN manual
intervention is actually needed.

## LAMBDA004-MEM-001 — Genome background refresh doesn't coalesce across gunicorn worker processes (Low, pre-existing, self-documented)

**Found by**: Reliability Architect, Program Lambda Certification 004 (re-confirmed, not newly discovered).

**What**: `routers/case_dna.py::_run_genome_background`'s in-process coalescing (`_genome_refresh_inflight`
sets) prevents a same-process lost-update race for concurrent triggers on the same case, but explicitly does
NOT coalesce across separate gunicorn worker processes — the code's own docstring already names this gap.

**Why not fixed this sprint**: pre-existing, self-documented, no confirmed incident from it; a genuinely
larger cross-process coordination problem (would likely need a DB-level lock or a dedicated coordination
mechanism), not a bounded fix.

**Severity**: Low — worth revisiting only if worker-process count or Genome-refresh trigger frequency ever
makes the race window practically relevant.

## LAMBDA005-AI-001 — Genome's own `snaga_predmeta_procent` is not capped by case readiness, unlike 3 downstream consumers (Medium, architecture decision needed)

**Found by**: AI Reasoning fork, Program Lambda Certification 005 (Full-Day Operational Simulation) — the
mission's own explicit "assume the previous sprint was wrong" charter meant re-checking whether the
deterministic-cap pattern (`_CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}`, proven in
`routers/court_predictor.py`, `routers/hearing_cc.py`, `routers/digital_twin.py`) had reached every GPT-
adjacent confidence surface. It has not.

**What**: `shared/genome_validator.py::compute_snaga_score()` computes the canonical `snaga_predmeta_procent`
deterministically from `snaga_faktori` (not raw GPT self-report — already fixed by the 2026-07-18 Reliability
Patch) plus a flat -15 penalty when `genome_kompletnost == "niska"`. It has zero awareness of
`shared/case_readiness.py`'s own 5-state model (`compute_case_readiness`) — confirmed by grep, no reference
to `case_readiness`/`CRITICAL_GAP`/`BLOCKED` anywhere in `routers/case_dna.py`. So a case with an open
`case_actions` row at `prioritet == "critical"` (readiness = CRITICAL_GAP) can still show `snaga_predmeta_procent`
as high as 100 if `snaga_faktori` sum positively — the exact class of overconfident number the cap pattern
exists to prevent elsewhere. `routers/copilot.py::_handle_analiza_predmeta`'s own `verovatnoca_uspeha` simply
reads this value directly from Genome (`genome.get("snaga_predmeta_procent")`), so it inherits the gap
unchanged; so does every other consumer that reads `case_dna.snaga_predmeta_procent` (Case Intelligence AI
Briefing, Workspace, etc.).

**Why not fixed this sprint**: this is NOT the same shape as the 3 existing cap call sites. Those apply the
cap locally, at the moment of their OWN GPT call, to their OWN returned value — cheap and local because
`case_actions`/readiness data is already available to them at call time. Genome computation itself cannot do
the same: `compute_case_readiness` requires `case_actions`, and `case_actions` rows are themselves populated
by a pipeline stage that runs AFTER a Genome refresh — capping inside `compute_snaga_score` at genome-
computation time would mean reading readiness data that, for a fresh case, doesn't exist yet (a circular
dependency, not a bounded fix). The alternative — replicating the readiness pipeline
(`calculate_procesni_rizik` + `identify_case_problems` + `collect_case_gaps` + `compute_case_readiness`)
inline in `copilot.py` alone — would create a 4th independent, narrower reimplementation of logic
`shared/case_context.py::build_case_context()` already assembles correctly, an active violation of this
program's own "1 concept = 1 owner = 1 algorithm = 1 truth" Core Consolidation principle. The architecturally
correct fix (migrate `_handle_analiza_predmeta` onto `build_case_context()` wholesale, or add a genuinely new
post-hoc "cap the STORED value once case_actions exist" pass) is a larger, riskier change than this sprint's
scope for a value that already IS deterministic and explainable, just not readiness-aware.

**Recommended next step**: a founder/architecture decision on which of the 2 alternatives above is correct,
then implement it as its own scoped sprint — not bundled into a certification sprint that found it.

**Severity**: Medium — no confirmed user-facing incident; a real but narrower version of the same overconfidence
class the cap pattern already closed for 3 other surfaces.

## LAMBDA005-UX-001 — 4 independent code paths read/filter deadline data with no shared owner (Low-Medium, structural observation)

**Found by**: UX/Workflow fork, Program Lambda Certification 005.

**What**: `routers/kalendar.py`, `routers/notifications.py`, `routers/morning_briefing.py`, and Workspace's
own canonical view each independently query and filter deadline/rok data for display — 4 parallel
implementations of "what deadlines does this user need to see," not one canonical source with 4 renderings.
This sprint's own notifications.py fix (excluding closed/archived cases from rok/hitan_rok notifications,
see the code change in this same sprint) had to be applied to exactly ONE of these 4 paths — the other 3 were
not audited for the identical gap as part of this fix, since confirming or fixing all 4 is a larger,
cross-cutting consolidation, not a single bug fix.

**Why not fixed this sprint**: the Core Consolidation principle (Program Tau, 2026-07-22) exists precisely
for this shape of problem, but applying it here means designing one canonical deadline-reader (likely
`shared/case_context.py`-adjacent) and migrating 4 call sites — out of scope for a certification sprint whose
job is to find and fix bounded defects, not run a consolidation project.

**Recommended next step**: audit `routers/kalendar.py` and `routers/morning_briefing.py` specifically for the
same "no closed/archived case exclusion" gap just fixed in `notifications.py` — if confirmed present, that
narrower fix (not a full consolidation) may be worth doing as its own bounded follow-up sprint.

**Severity**: Low-Medium — the confirmed instance of this pattern (notifications.py) is fixed; the other 3
paths are unaudited, not confirmed broken.

## LAMBDA005-PERF-001 — `main.py`'s `ask_agent` cache has no content-based invalidation (Low-Medium, feature not a bug)

**Found by**: Full-Day Operational Simulation fork, Program Lambda Certification 005.

**What**: the tenant-scoped cache fixed in Certification 003 (`_CACHE_TTL = 6h`, `_CACHE_TTL_DB = 7 days`)
is correctly scoped per-tenant/per-case now, but still purely time-based — a cached AI answer can reference
stale case state (new documents uploaded, Genome refreshed) for up to its full TTL window with no hook into
`services/event_bus.py`'s own durable event stream to purge affected cache keys when the underlying case
actually changes.

**Why not fixed this sprint**: this is a genuinely new capability (event-driven cache invalidation keyed by
predmet_id), not a bug in the existing tenant-scoping fix — implementing it means touching the same
recently-hardened cache code a second time this engagement without a specific proven incident driving it.

**Severity**: Low-Medium — bounded by the existing TTLs (never permanently stale), no confirmed user-facing
incident.

## LAMBDA005-UX-002 — Digital Twin simulations are served without a staleness signal (Low, product decision needed)

**Found by**: Full-Day Operational Simulation fork, Program Lambda Certification 005.

**What**: `GET /api/twin/{predmet_id}` (`routers/digital_twin.py::dohvati_simulacija`) returns the most
recently saved `twin_simulacije` row verbatim (`select("*")`, includes `created_at`), with no comparison
against how much the underlying case has changed since that simulation was generated (new documents, Genome
refresh, etc.) — a lawyer could be shown a simulation based on meaningfully outdated case facts with no
signal that a re-run might change the outcome.

**Why not fixed this sprint**: whether/how to signal staleness (an age threshold? a comparison against
Genome's own `verzija`? an auto-regenerate trigger?) is a product decision, not an engineering bug — the raw
data needed to build any of these (`created_at` is already returned) is already present.

**Severity**: Low — no incorrect behavior, a missing product affordance.

## LAMBDA006-EVT-001 — `_mark_completed`'s own bookkeeping write is unprotected against a transient failure right after a successful executor (Low-Medium, narrow window)

**Found by**: Database Reliability fork, Program Lambda Certification 006 (Chaos Engineering Certification).

**What**: `services/case_evolution.py::handle_case_changed` — `await _mark_completed(event.event_id, c.name,
result_ref)` runs OUTSIDE the `try/except` that wraps `await c.executor(event)`. If the executor succeeds but
the immediately-following `_mark_completed` write itself fails (a transient Supabase connection drop between
the two calls — narrower and rarer than this sprint's own CRITICAL staleness-mismatch fix, but the same shape),
the consequence row stays `'pending'`. A later retry (governed by the same `ConsequenceClaimPending`/staleness
mechanism this sprint just hardened) re-invokes the executor from scratch. For an idempotent executor
(`_consequence_genome_refresh`'s own before/after `verzija` check) this is merely wasteful. For a non-idempotent
one — `_consequence_timeline_entry` does a plain `predmet_hronologija` INSERT with no dedup key — a second run
produces a genuine duplicate row (a duplicate "document accepted" Timeline entry).

**Why not fixed this sprint**: closing this properly needs either (a) making every executor idempotent
(touches multiple executor implementations, a broader change than this single bookkeeping call site), or (b) a
bounded retry specifically around `_mark_completed` itself (narrower, but risks its own new inconsistency if
the retry ALSO fails — e.g. does the loop then treat it as a genuine executor failure via `_mark_failed`, which
would be misleading since the executor itself didn't fail?). Neither is a small, obviously-safe edit under this
sprint's own time budget, unlike this sprint's other 4 fixes.

**Recommended next step**: scope this as its own small follow-up: add a bounded retry (2-3 attempts) around
`_mark_completed` specifically, and give `_consequence_timeline_entry` (and any other non-idempotent executor)
a dedup key the same way `case_evolution_consequences` itself already has one, closing the residual duplicate-
row risk even if the bookkeeping write eventually gives up.

**Severity**: Low-Medium — requires 2 independent, closely-timed failures (executor succeeds, THEN the very
next write fails) to trigger, unlike the sprint's own CRITICAL finding which needed only one (a worker crash
anywhere in a 30-300s window).

## LAMBDA006-SEC-001 — `ai_cache`'s RLS policy exists only as a code comment, not a tracked migration (Low, unverifiable from code alone)

**Found by**: Database Reliability fork, Program Lambda Certification 006.

**What**: `main.py` (lines 168-180) documents an `ai_cache` RLS policy as a comment instructing "run this once
in the SQL editor manually" — it is not a tracked file under `migrations/`. There is no repo-level evidence
this was ever actually applied to production. Same "declared control ≠ enforced control" gap shape named
elsewhere in this program's own governance work. Blast radius is limited (the cache holds only PII-stripped
question/answer pairs, per `main.py`'s own cache-key design already re-verified sound this sprint), but the
policy's actual live state is unverifiable from the repo alone.

**Why not fixed this sprint**: converting this into a tracked migration file is straightforward, but per this
project's own standing convention the coordinator never runs migration SQL — writing the file without founder
awareness that a NEW migration now exists (separate from this sprint's other zero-migration fixes) risks it
sitting unnoticed. Flagging for the founder to convert deliberately, matching how migrations 102/103 were
handled in Certification 002.

**Severity**: Low — narrow blast radius, but worth closing given how cheap the fix is once acknowledged.

## LAMBDA006-INTAKE-001 — Full-day-of-work: no unique constraint on `predmet_dokumenti(predmet_id, redni_broj)`, a read-then-write TOCTOU under parallel upload (Medium, needs a migration)

**Found by**: Upload/Intake Chaos fork, Program Lambda Certification 006, directly matching the mission's own
"500 documents, parallel upload" scenario.

**What**: document ordering (`redni_broj`) is computed via `SELECT MAX(redni_broj)... + 1` in Python
(`api.py`, ~line 4328), then inserted as a separate statement — a classic read-then-write race. Confirmed via
`migrations/` that `predmet_dokumenti` has no unique constraint on `(predmet_id, redni_broj)`. Under genuinely
concurrent uploads for the same case (this mission's own explicit scenario), multiple requests can read the
same MAX before any commits, producing silently duplicate `redni_broj` values — no error, just two documents
both labeled "DOK-05," a real (if cosmetic-severity) confusion risk for evidence citations that reference a
document by its number.

**Why not fixed this sprint**: the correct fix is a DB-level unique constraint (`UNIQUE(predmet_id,
redni_broj)`) plus a retry-on-conflict loop in the app code (mirroring the already-proven atomic-claim pattern
used everywhere else in this program) — this needs a new migration, and per this project's own standing
convention the coordinator never runs migration SQL. Writing the app-side retry loop without the DB constraint
backing it would not actually close the race (same TOCTOU, just a narrower window).

**Recommended next step**: a migration adding the unique constraint, paired with a small retry-on-
`IntegrityError`/23505 loop around the insert (bounded, 2-3 attempts, reusing the exact numbering-conflict
shape `_try_claim_consequence` and friends already established for other tables this program).

**Severity**: Medium — real under the mission's own explicitly-named "parallel upload" scenario, but cosmetic
in impact (duplicate labels, not lost/corrupted data).

## LAMBDA006-GOV-001 — fire-and-forget `log_action` calls have no drain guarantee during an ordinary graceful shutdown (Low-Medium, architecture decision needed)

**Found by**: coordinator direct investigation, Program Lambda Certification 006 (the 6th forensic fork slot
could not be spawned — session hit its subagent limit — so this area was investigated directly instead of
via fork).

**What**: `shared/audit_immutable.py::log_action` is called via `asyncio.create_task(log_action(...))`
(fire-and-forget) at 36 call sites across 16 files, including this sprint's own new `intake_kreiraj` audit
call. `api.py`'s own `@app.on_event("shutdown")` handler (confirmed by reading it directly) only awaits 2
NAMED background loops (`stop_worker()`, `stop_dispatch_loop()`) — it has no mechanism to track or await
arbitrary orphaned tasks spawned from within request handlers elsewhere. This is not only a violent-crash
risk: an ORDINARY graceful shutdown (SIGTERM, a routine deploy) can plausibly return an HTTP response to the
client (the request handler's own coroutine completes) while its own `log_action` task is still in flight
(e.g. waiting on a Supabase round-trip) — if the process's shutdown grace period expires before that
orphaned task finishes, the audit entry is silently dropped even though the operation it was auditing already
succeeded and was already returned to the caller.

**Why not fixed this sprint**: closing this properly needs either (a) converting all 36 fire-and-forget call
sites to `await` inline (changes the latency profile of every one of those request handlers, a broad and
risky change to make under one sprint), or (b) a proper task-tracking/draining mechanism in the shutdown
handler (a real, non-trivial engineering project — collecting every `asyncio.create_task` platform-wide into
a tracked set, not a one-line fix).

**Recommended next step**: an architecture decision on (a) vs (b) above, scoped as its own sprint — likely (b)
for the small number of genuinely audit-critical call sites (case creation, ownership changes) while leaving
best-effort telemetry-style logs as fire-and-forget.

**Severity**: Low-Medium — requires unlucky timing (shutdown grace period expiring mid-flight on a specific
background task) to trigger, and the operation itself is never lost, only its audit trail entry.

## LAMBDA006-PIPE-001 — Case Pipeline steps 3/5's own marker-check is TOCTOU-safe for sequential retries but not concurrent invocation (Low-Medium, narrow trigger)

**Found by**: Genome/Workspace/Case Actions Chaos fork, Program Lambda Certification 006.

**What**: `services/case_pipeline.py::run_case_pipeline` has no lock/claim of its own; up to 4 call sites can
invoke it for the same `predmet_id` (an automatic `PREDMET_KREIRAN` event handler — notably NOT routed through
Case Evolution's own `_try_claim_consequence` atomic-claim layer, since it predates that mechanism — plus a
manual re-run endpoint and 2 direct fire-and-forget calls in `routers/intake.py`). Steps 3
(`_step_ekstrakcija_rokova`) and 5 (`_step_strategija`) each guard against re-running via a SELECT-then-INSERT
marker check in `predmet_istorija` — safe for a sequential retry (the marker is already committed by the time
a second attempt's SELECT runs), but a classic TOCTOU under genuine CONCURRENT invocation: 2 calls can both
pass the "no marker yet" SELECT before either INSERTs, producing duplicate `predmet_hronologija`/
`predmet_istorija` rows. Concrete trigger: a case auto-created via `intake.py` (background pipeline fires
immediately) plus a user clicking "re-run pipeline" within the same few seconds, while step 3/5's own GPT call
is still in flight. `api.py`'s own existing comment ("even a rare duplicate dispatch doesn't create duplicate
rows") is accurate only for the sequential-retry case, not the concurrent one — the comment doesn't currently
distinguish them.

**Why not fixed this sprint**: the correct fix mirrors this program's own now-repeatedly-proven atomic-claim
pattern (`_try_claim_consequence`, `claim_intake_finalize`, `claim_pending_events`) — routing the Case
Pipeline's own step markers through an equivalent atomic check-and-claim rather than a SELECT-then-INSERT. This
is the SAME shape of fix as this sprint's own CRITICAL finding and this sprint's Smart Intake finalize fix, but
applying it here means touching a 4-call-site-invoked, older pipeline this sprint did not otherwise scope in —
better done as its own deliberate follow-up than squeezed in at the end of an already-large sprint.

**Severity**: Low-Medium — impact is bounded (duplicate rokovi/strategy entries, not data corruption or
security), and the trigger window (concurrent pipeline invocation within seconds, not just any retry) is
narrower than this sprint's own CRITICAL finding.

## LAMBDA006-GEN-001 — Genome deadline corrections don't supersede stale `predmet_hronologija` rows, only add new ones (Low-Medium, product decision needed)

**Found by**: Genome/Workspace/Case Actions Chaos fork, Program Lambda Certification 006.

**What**: `routers/case_dna.py::_sync_rokovi_to_hronologija` is insert-only — it dedups against existing
`predmet_hronologija` rows by an exact `(dogadjaj, datum_iso)` string-tuple match, and only ever adds new rows
for tuples not already present. If a LATER Genome refresh corrects a previously-extracted deadline (a
different date or wording for the same underlying real-world event — e.g. a corrected filing deadline after a
better-quality document is uploaded), the old, now-wrong row is never updated or removed — it persists
alongside the new, correct one with no supersession flag, so a stale and a current deadline coexist
indistinguishably in the calendar/hronologija view.

**Why not fixed this sprint**: whether/how to identify "this new deadline supersedes that old one" (same
event, corrected date — vs. a genuinely NEW, additional deadline) is a product/domain decision requiring a
stable identity concept for "the same underlying deadline" (analogous to `shared/contradiction_identity.py`'s
own already-solved problem for contradictions, but not yet built for deadlines) — not a bounded engineering
fix available this sprint.

**Recommended next step**: a founder/architecture decision on whether to build a deadline-identity matcher
(mirroring `contradiction_identity.py`'s own precedent) that lets a refresh mark a prior row superseded rather
than only ever adding new ones.

**Severity**: Low-Medium — no data loss (both rows remain visible), but a real "which deadline is actually
correct" confusion risk for the mission's own explicitly-named Calendar/Audit consistency surface.

## LAMBDA007-DEAD-001 — MERGED INTO `LAMBDA-003` (historical record only, not a second open item)

**Merged by**: Program Lambda, Final Certification 008 (2026-08-07), Documentation Drift team — this entry
independently rediscovered `LAMBDA-003` (same file, same 5 endpoints, same root cause) under a separate ID
without cross-checking the debt register first. See `LAMBDA-003` above for the single tracked entry. Kept
below verbatim as the historical record of how this was found the second time, not as an open action item.

**Found by**: coordinator direct investigation, Program Lambda Certification 007 (Enterprise Beta
Certification) — the session's subagent spawn limit (200/200) was reached during Certification 006, so
Certification 007 was scoped down to a direct, non-forked investigation rather than the mission's own
originally-envisioned parallel-fork breadth; disclosed here explicitly, not hidden.

**What**: `scripts/audit_routers.py` (a pre-existing, untracked heuristic tool already in the repo, built to
investigate the already-known `[[project_platform_anatomy_report_2026_07_24]]` "~208 unconfirmed orphan
routes" concern) flagged 13 router modules with zero detected in-repo callers. Spot-checking a sample found
the heuristic has real false positives — `routers/oblasti.py` and `routers/ugovor_zastupanja.py` are both
genuinely called by the frontend via dynamically-constructed fetch URLs the script's static string-matching
doesn't recognize (`fetch(BASE_URL + '/api/oblasti/' + _oblastTrenutna, ...)`, a percent-encoded Serbian
Latin path for `ugovor-zastupanja`) — so the raw 13-module list must NOT be treated as a confirmed dead-code
list. One instance, however, IS confirmed genuinely dead: `routers/onboarding.py`'s own 5 endpoints
(`/api/onboarding/stanje`, `/korak`, `/kompletiran`, `/demo-predmet`, `/checklist`) have zero frontend
callers, while the frontend's actual working onboarding-completion call
(`static/vindex.js:15103::apiFetch('/api/auth/onboarding/complete', ...)`) hits a COMPLETELY SEPARATE
standalone endpoint defined directly in `api.py:2424` — two independent onboarding systems, one live, one
fully built and registered but orphaned.

**Why not fixed this sprint**: deleting `routers/onboarding.py`'s dead endpoints is functionally safe (nothing
calls them), but whether they represent abandoned work-in-progress worth reviving, or genuinely superseded
code safe to delete, is a product judgment the coordinator should not make unilaterally.

**Recommended next step**: (1) a founder decision on deleting `routers/onboarding.py`'s dead endpoints (or
reviving them if the richer flow — step tracking, demo-predmet, checklist — was meant to replace the simpler
`api.py` one and never got wired up). (2) The remaining 12 heuristically-flagged modules (`agent_notifications`,
`auto_discovery`, `import_klijenti`, `knowledge_hygiene`, `knowledge_transfer`, `region`, `status_page`,
`strategy_simulator`, `style_checker`, `whatsapp_notif`, plus the 2 confirmed false positives already ruled
out) need individual verification the same way `onboarding` just got, not a blanket assumption either way —
this is exactly the "~208 unconfirmed" claim from the Platform Anatomy Report, narrowed to 13 candidates by an
existing tool but still not resolved to a final confirmed list.

**Severity**: Low — dead code carries maintenance confusion risk, not a functional or security risk; the
platform behaves correctly today either way.

---

## Program Lambda, Final Certification 008 (2026-08-07) — "The Final Gate"

Fresh session, full parallel-fork budget (the 200/200 spawn-limit constraint that scoped down
Certifications 006/007 does not apply here). 14 independent forensic teams + 3 Red Team adversarial
clusters. 21 substantive findings, 19/19 survived adversarial falsification (2 corrected on survival — see
`docs/lambda/LAMBDA008_CERTIFICATION_REPORT.md` for full methodology and the complete findings ledger).
Most findings were fixed directly this sprint (see commit history and `LAMBDA008_CERTIFICATION_REPORT.md`
for the full fix list: dokument.py session ownership check, billing.py klijent_id filter + invoice-number
race fix, predmeti_close.py/klijenti double-submit guards, /api/pitanje credit-refund-on-error,
health_index.py dead-column fix, predmeti_dashboard canonical-priority migration, event_bus batch-claim
heartbeat, case_commander.py/zakon_monitoring.py/multi_agent.py recency ordering, ambient_analyzer.py
citation grounding, background_agents.py/morning_briefing.py bounded concurrency, 3 frontend soft-failure
wiring fixes, SOURCE_OF_TRUTH_REGISTRY.md correction, LAMBDA-003/LAMBDA007-DEAD-001 merge). Items below are
the ones NOT fixed this sprint — genuine product/architecture decisions or explicitly deferred.

### LAMBDA008-SEC-001 — migrations 102/103 (RESOLVED 2026-08-07, founder-reported, not independently technically verified)

**Found by**: Team 2 (Security & RLS), re-confirmed independently by Team 3 (Ownership/IDOR) and Team 13
(Migration/Schema Drift); survived Red Team A adversarial review. Re-confirmed still open as of Operation
Black Swan, Mission 001 (same day).

**What it was**: `deduct_credit`/`set_user_pro` SECURITY DEFINER RPCs (`supabase_setup.sql:117-148`,
`migrations/061_fix_missing_profiles_columns.sql:66-74`) had no ownership check and were callable by any
authenticated user — a real, live credit-drain / free-permanent-PRO exploit. Same for `profiles`' own UPDATE
RLS policy (no column scope). Fixes existed since Certification 002
(`migrations/102_lambda002_rpc_ownership_lockdown.sql`, `103_lambda002_profiles_column_lockdown.sql`) but
were confirmed still unapplied across 3 separate certifications/missions (002 → Lambda 008 → Black Swan 001,
all same day, 2026-08-07).

**Resolution**: founder reports both migrations were run against production Supabase later on 2026-08-07.
**This status update is based on the founder's own report, not independent technical verification** — the
coordinator does not have `SUPABASE_DB_URL` (direct Postgres connection, would allow a read-only catalog-
privilege check) or an anon-level key (would allow testing the actual PostgREST-level rejection) in this
environment; only the service-role key is available, which bypasses RLS/GRANT restrictions by design and so
cannot distinguish "locked down" from "still open" by calling anything with it. The founder was offered a
safe, read-only verification path (share `SUPABASE_DB_URL` for a catalog-only query, zero risk to
production data) and explicitly chose to proceed on their own report instead. Recorded here exactly as that
— a founder-reported resolution, not a coordinator-verified one — consistent with this program's own
evidence-honesty discipline (name the actual confidence level, don't round up).

**If this is ever revisited**: the exact read-only verification query and the exact PostgREST-level
rejection test are both described in migrations 102/103's own trailing comments ("KRITIČNO — RUČNA PROVERA
POSLE OVE MIGRACIJE").

### LAMBDA008-GAMMA-003-reconfirm — `routers/matter_intel.py`'s own missing-document % recompute (Medium, still open, unchanged from prior tracking)

**Found by**: Team 8 (Canonical Decision Sources), re-verifying already-tracked `GAMMA-003`.

**What**: `get_uncertainty_dashboard` (`routers/matter_intel.py:267`) independently recomputes a missing-
document percentage via its own `_EXPECTED_DOCS` set-difference (lines 320-325), in the same file that
already imports `calculate_procesni_rizik` for its main endpoint — a second, parallel implementation of
logic `risk_engine.py` already owns. Confirmed genuinely still live and unfixed, not stale documentation.

**Why not fixed this sprint**: consolidating this cleanly (feeding into the 5-dimension `uncertainty_score`
blended with GPT prose) is more than a mechanical delegation — same class of scope decision the original
`GAMMA-003` entry already deferred. Not attempted blind under this certification's own fix-cycle time
budget.

### LAMBDA008-DEAD-002 — 9 additional confirmed-dead router modules, beyond `onboarding.py` (Low, product decisions needed)

**Found by**: Team 14 (Dead Code/Shadow Workflow), re-running `scripts/audit_routers.py` and resolving all
10 modules Certification 007 left unconfirmed; survived Red Team C spot-check (0 false positives).

**What**: `agent_notifications.py`, `auto_discovery.py` (admin-only by design), `knowledge_hygiene.py`,
`knowledge_transfer.py`, `region.py`, `strategy_simulator.py`, `style_checker.py` — all confirmed zero
frontend callers, genuinely dead. `import_klijenti.py` and `whatsapp_notif.py` are confirmed genuine
shadows of live systems (already tracked as `IF-003`/`IF-004`, founder decision pending, status unchanged).
`status_page.py` is MIXED: `GET /api/status/public` is live (Certification 007's own open follow-up, now
resolved) but `GET/POST /api/status/incidents` + resolve endpoint are dead within the same module.

**Why not fixed this sprint**: per this program's own established practice (`LAMBDA-003`/`LAMBDA007-DEAD-
001` above), deleting confirmed-dead code is a product judgment (delete vs. revive), not a unilateral
engineering fix — consistent with not guessing at `onboarding.py`'s fate either.

**Recommended next step**: a single founder pass over this list plus `LAMBDA-003`/`onboarding.py` — either
"delete all of these" or name which ones represent unfinished work worth reviving. `status_page.py`'s dead
incident-management endpoints specifically may be worth reviving (an admin incident-reporting UI is a small,
well-scoped addition if desired) rather than deleting outright.

**Severity**: Low — dead code, no functional or security risk.

---

## Operation Black Swan, Mission 001 (2026-08-07) — "The Day Everything Goes Wrong"

14 independent chaos teams, each instructed to actually RUN reproduction scripts (mocked I/O, real
application code) rather than just read code, hunting for what breaks under 500-concurrent-lawyer load,
bulk uploads, OpenAI degradation, DB blips, worker crashes, conflicting concurrent actions, long sessions,
cross-tenant contention, 30-day abandonment, event floods, AI manipulation, and chaotic human usage — plus
a dedicated cross-subsystem combined-stressor team. ~40 findings, most CONFIRMED via actual reproduction.
Full findings ledger and methodology: `docs/blackswan/BLACK_SWAN_REPORT.md`. The 2 CRITICAL findings
(orphan-invoice write path, systemic overdue-deadline invisibility across 3 code copies) and the highest-
impact HIGH findings (~13 items: `_get_supa()` thread-safety, kanban lost-update, duplicate Genome refresh,
3 AI-credit-refund gaps, bulk-status reopen race, unbounded `predmet_hronologija` fetch, silently-lost
Case Pipeline trigger, 3 AI-output range-clamping gaps, hallucination-guard field-scope + ASCII bypass)
were all fixed directly with test coverage this mission — see commit history and
`docs/blackswan/BLACK_SWAN_REPORT.md`. Items below are the ones NOT fixed, each with a specific reason.

### BLACKSWAN-DEBT-001 — Tenant-blind FIFO intake queue (Medium-High, architectural)

**Found by**: Team 2 (Upload Storm), simulated 20 firms × 1000 documents across 4 workers.

**What**: `claim_intake_job` (migration 073) claims strictly `ORDER BY created_at`, zero tenant/
`kancelarija_id` partitioning; `intake_worker.py` processes exactly 1 job at a time per worker singleton
(`WEB_CONCURRENCY=4` default → max 4 documents extracting system-wide at once). Simulated: the 20th firm's
first document isn't claimed until 19,000 other firms' jobs drain — pure global FIFO, no per-tenant
fairness.

**Why not fixed**: a real fix needs either per-tenant round-robin claiming (a schema/RPC change to
`claim_intake_job`) or a worker-pool-per-tenant model — both are architectural changes bigger than this
mission's fix-cycle budget, not a contained bug fix.

### BLACKSWAN-DEBT-002 — Deadline-extraction plausibility check missing (Medium-High)

**Found by**: Team 2. `shared/intake_extract.py::extract_deadline` picks the first date near a legal
keyword within a 100-char window with no plausibility check. Reproduced: a "valid until 2030" contract-
expiry clause near "otkaz" auto-accepted (confidence 0.95, threshold 0.90) and filed as a real actionable
court deadline. Same weak point Team 9's CRITICAL abandonment findings independently surfaced — deadline
handling is this platform's single most recurring fragility across this mission.

**Why not fixed**: needs new extraction-quality heuristics (date-type classification: statutory deadline
vs. contract term vs. unrelated date) — new capability, not a contained fix, and risks false negatives
(missing a real deadline) if rushed.

### BLACKSWAN-DEBT-003 — Duplicate document detection scope (Medium)

Team 2: dedup is exact-byte-hash + same-user only (grep-confirmed, no other logic exists). A rescanned
copy, a resaved PDF, or the same document uploaded by a colleague at the same firm is not detected. Needs
perceptual/content-similarity hashing (new capability) or at minimum firm-wide (not just same-user) hash
scoping — a real product-tradeoff decision (false-positive risk), not fixed this mission.

### BLACKSWAN-DEBT-004 — Corrupted-file wasteful retry (Low)

Team 2: a corrupted (non-PDF-bytes) upload isn't fail-soft like OCR failure — it goes through the full
exponential-backoff retry cycle before dead-lettering, despite being a deterministic failure that will
never succeed on retry. Wasteful, not user-facing broken. Small, contained fix (classify `PdfStreamError`
as non-retryable) — not done this mission purely due to fix-cycle time budget, safe to pick up next.

### BLACKSWAN-DEBT-005 — Unbounded document/timeline fetches outside case_context.py (Medium-High, partially addressed)

Team 2 (PLAUSIBLE-UNCONFIRMED, live Supabase cap unverifiable) + this mission's own fix to
`shared/case_context.py`'s `predmet_hronologija`/`rocista` queries (now bounded, see BLACKSWAN-HIGH-007 in
commit history). **Still open**: `routers/case_dna.py::_sync_rokovi_to_hronologija` and other direct
`predmet_dokumenti`/`rocista` queries outside `case_context.py` remain unbounded — this mission fixed the
single highest-traffic canonical path, not every call site.

### BLACKSWAN-DEBT-006 — No Event Bus backlog/dead-letter monitoring (Medium)

Team 7 + Team 10: drain capacity (~16.7 events/sec) vastly exceeds any single-lawyer rate and even a
realistic bulk-upload burst self-recovers — but nothing in the codebase monitors or alerts on undispatched-
row count or dead-letter count; `logger.critical` on dead-letter is the only signal, never aggregated into
a dashboard. Needs real observability infrastructure (a metrics endpoint + alerting), out of a single
mission's contained-fix scope.

### BLACKSWAN-DEBT-007 — Case Genome carries no staleness signal (Medium)

Team 9: `case_dna` has only an integer `verzija` counter, no timestamp anywhere in the payload or the GET
response. A 30-day-old Genome displays with zero "last computed" indicator. Same shape as the already-
tracked UI-perception note in `SOURCE_OF_TRUTH_REGISTRY.md` — needs a schema field addition + frontend
display change, deliberately not rushed alongside this mission's other fixes.

### BLACKSWAN-DEBT-008 — `agent_recommendations` has zero frontend consumer (Low, product decision)

Team 9: `background_agents.py`'s own output table has no UI anywhere (grep-confirmed). 30 days of
background AI work accumulates invisibly — wasted compute, not a bug. Same class as the already-tracked
`LAMBDA008-DEAD-002` dead-router list — a founder decision (build the UI, or stop running these agents),
not an engineering fix.

### BLACKSWAN-DEBT-009 — Event Bus handler idempotency gaps (Medium)

Team 4 + Team 5: `on_rok_kritican`/`on_predmet_kreiran`/`on_dokument_uploadovan`/`on_health_score_promenjen`
have no per-event idempotency key — a `_mark_dispatched` blip after a handler already ran a real side
effect causes a duplicate `proactive_alerts` INSERT on reclaim/retry. Reproduced (Team 4): handler fired
twice for one durable event. Needs a dedupe key added to each handler's own insert (`create_proactive_alert`
already supports one per Certification-era work elsewhere) — a real, contained fix, deferred only for fix-
cycle time, not difficulty.

### BLACKSWAN-DEBT-010 — Genome audit-trail gap on outbox-insert failure (Medium)

Team 4 + Team 5 (2 independent confirmations): `_emit_genome_event`'s own try/except silently swallows a
failed `events` insert by design ("never fail the main request") — the live Genome data is correct, but
that version's `audit_immutable` hash-chain entry never gets written, and nothing reconciles `events`
against `case_dna.verzija`. Compliance/audit-trail gap, not user-visible data loss. Needs the same
reap-and-backfill pattern this mission already built for `BLACKSWAN-HIGH-008` (missing pipeline events),
applied to Genome versions — a natural next mission, not done here due to time budget.

### BLACKSWAN-DEBT-011 — Cross-worker-process Genome-refresh coalescing gap (Medium, self-disclosed pre-existing)

Team 1 + Team 12 (2 independent confirmations): the in-process coalescing guard this mission just extended
to the manual refresh endpoint (`BLACKSWAN-HIGH-003`) is plain in-memory Python state, inherently
process-local under gunicorn's multiple worker processes — the code's own comment already discloses this.
A full fix needs a DB-level advisory lock or claim row, a bigger change than the in-process guard extension
done this mission.

### BLACKSWAN-DEBT-012 — Duplicate-submission gaps on 4 more endpoints (Medium)

Team 12: `routers/dokument.py::dokument_upload` (no idempotency check at all, unlike the well-hardened
smart_intake upload path — double-bills real credits on retry), `routers/zadaci.py::kreiraj_zadatak`,
`routers/rocista.py::kreiraj_rociste` (also emits a durable consequence-triggering event, doubling the
downstream effect), `routers/evidence.py::add_dokaz` — all lack the 5s-window dedup pattern this mission's
`billing.py`/`klijenti.py`/`predmeti` fixes already established elsewhere. Same fix shape, not applied here
purely due to fix-cycle time budget (4 more call sites), not difficulty — a natural, low-risk follow-up.

### BLACKSWAN-DEBT-013 — `klijenti/router.py::update_klijent` whole-form last-write-wins (Medium)

Team 12: writes every non-None field from the request; the frontend (`crmSacuvaj`) always submits the
complete form, never a diff. Two tabs editing different fields on the same client silently revert each
other. Contrasts with `api.py::update_predmet`, which is correctly safe (whitelists only fields present in
the request body). Fix is either a frontend diff-submission change or backend field-presence detection —
deferred for fix-cycle time.

### BLACKSWAN-DEBT-014 — Upload not blocked by a closing case (Medium)

Team 6: `api.py::predmet_upload_auto_analyze`'s ownership check never filters on case status; racing an
in-flight upload against `zatvori_predmet` lets the upload complete into an already-closed case with zero
error. Needs a status check added to the upload path — small, contained, deferred for time budget.

### BLACKSWAN-DEBT-015 — Genome-refresh response echoes stale case name (Low, cosmetic)

Team 6: `refresh_case_dna` reads `naziv` once at entry purely to echo in the response; a rename landing
mid-refresh means the response shows the pre-rename name even though the DB already has the new one. No
data corruption, cosmetic only.

### BLACKSWAN-DEBT-016 — Cross-tenant resource-contention noisy-neighbor (Medium-High, architectural)

Team 14 (combined-stressor finding): every blocking call (OpenAI AND every Supabase `.execute()`) runs via
`asyncio.to_thread`, sharing Python's single process-wide default `ThreadPoolExecutor` — zero per-tenant
isolation, and Genome-refresh's own OpenAI call doesn't even touch the existing AI semaphore (only
`ask_agent`'s `pokreni()` does). Reproduced: one firm's bulk-upload load pushed an unrelated firm's fast,
unrelated read latency up 17.9x on a 20-core dev machine. Needs a dedicated thread pool sized/scoped per
purpose (or per-tenant), or extending the AI semaphore's reach to cover the Genome-refresh path too — a
real architectural change, correctly not attempted as a quick patch.

### BLACKSWAN-DEBT-017 — Ordinary-concurrency TOCTOU on every 5s-window dedup check (Medium, architectural)

Team 14: this mission's own (and prior sprints') 5s-window check-then-insert dedup pattern (predmeti,
klijenti, intake, fakture) is defeated by ordinary concurrency alone — 2 simultaneous requests both see an
empty dedup-check result and both insert, no DB blip needed. This is the same known, documented tradeoff
this pattern's own prior-sprint comments already name ("a check-then-insert mitigation, not a full atomic
guarantee") — re-confirmed real under this mission's own reproduction, not a new discovery, but flagged
here as the item a future mission should close with real DB-level unique constraints + retry-on-conflict
(the pattern this mission's own `BLACKSWAN-CRIT-001`/billing.py fix demonstrates), applied systematically.

### BLACKSWAN-DEBT-018 — Semaphore hold-time coupled to LLM retry backoff (High, architectural)

Team 14 (combined-stressor finding, the mission's own standout emergent bug): `api.py::pokreni()` holds its
8-slot AI-concurrency semaphore for the entire `fn` duration, including `llm_retry`'s own up-to-3x backoff
— OpenAI degradation directly multiplies semaphore hold time, which then couples into the 30s queue-wait
timeout. Reproduced: 500 concurrent lawyers + degraded (not failed) OpenAI → 415/500 (83%) got a 503 purely
from queue-timeout, though every simulated call eventually succeeded on its own. This mission's own credit-
refund fixes (`BLACKSWAN-HIGH-004`) correctly ensure a 503 under this exact scenario no longer silently
loses money — but the underlying capacity-collapse itself is unfixed. A real fix needs either releasing the
semaphore slot during backoff sleep (letting another request's attempt use the freed capacity) or a
separate, shorter-lived semaphore scoped to just the actual network call, not the whole retry sequence —
correctly identified as a deeper architectural change, not attempted as a quick patch given the risk of
introducing a new race in the retry/semaphore interaction without careful design.

### BLACKSWAN-DEBT-019 — `court_predictor.py` has zero citation-verification code (High, AI governance)

Team 11 (AI Attack): unlike `main.py::ask_agent`'s hard-refusal guard, `court_predictor.py::prediktuj_ishod`
has no citation-verification code at all. Reproduced: a fabricated court decision citation absent from the
retrieved context reached the API response verbatim. Needs the same T6-style guard `main.py` already has,
adapted to this module's own citation shape (`koriscena_praksa`) — a real, scoped fix, deferred for fix-
cycle time in this mission, not architectural difficulty. High priority for the next mission.

### BLACKSWAN-DEBT-020 — Forensic Legal Audit validator doesn't verify claim-excerpt support (Medium-High, AI governance)

Team 11: `analiza/validator.py::run_post_parse_validation` only checks that a cited `clause_excerpt` string
is PRESENT in the source document text — never that the finding's own narrative claim is actually supported
by that excerpt. Reproduced 2 ways: an empty-excerpt finding short-circuits validation entirely (survives
unchecked, scored risk=100); a genuine verbatim excerpt paired with an invented narrative ("already 3 months
in arrears") also survives. Needs either a second LLM-based support-verification pass (cost/complexity
tradeoff) or a stricter structural rule (reject empty excerpts outright, require the narrative to quote/
reference specific excerpt terms) — a design decision, not a mechanical fix, correctly deferred.

### BLACKSWAN-DEBT-021 — Genome's `require_review` verdict is advisory, not blocking (Medium, product decision)

Team 11: `verify_genome()` correctly DETECTS a fabricated `dokazi_rang` entry citing a nonexistent document,
a `kontradikcije` entry pointing at a nonexistent document ID, and a fake law-article citation — but the
`require_review` verdict never blocks the write; all three still land verbatim in the live `case_dna`
column, gated only by a UI-rendered amber warning badge a lawyer could ignore. Whether a flagged Genome
should be allowed to save at all (vs. held for confirmation) is a genuine product/UX decision — not
guessed at unilaterally, same standing as this platform's other advisory-vs-blocking AI-governance
questions (`PROGBETA-003`, `SENT-005`).

**Severity summary across this mission's 21 debt items**: 1 High (`BLACKSWAN-DEBT-018`), 2 High-adjacent
(`-016`, `-019`), remainder Medium/Medium-High/Low. None are CRITICAL — both CRITICAL findings this mission
produced were fixed directly, per the mission's own STOP RULE.

## Operation Iron Lawyer, Master Sprint 001 (2026-08-07) — "Human-Centered Operational Certification"

21 independent teams (Alpha through Uniform) audited the LAWYER's experience using the platform (not the
platform's correctness) via direct code tracing of static/vindex.js and index.html — no live browser tool
was available in this environment, disclosed explicitly as a methodology constraint. Scope was
constitutionally UI/UX-only per the mission's own FORBIDDEN list: no business logic, legal rules, AI
reasoning, Genome, Event Bus, AI Governance, Security/RLS/Ownership, or Audit changes. 41 confirmed findings
were fixed directly this sprint (see docs/ironlawyer/IRON_LAWYER_FINDINGS.md for the full list with
file:line evidence); the following 13 require a founder/product decision or are too broad for a
same-sprint safe patch and are named here instead.

### IRONLAWYER-DEBT-001 — Case Commander: fully-built, billed feature with zero frontend entry point (High, product decision needed)

Team Gamma: routers/case_commander.py implements 4 complete, permission-gated, billed endpoints
(/api/commander/analiza, /quick-check, /checklist, /jutarnji), registered as a professional-tier,
cost-tracked feature in the feature registry (migrations/064/065). Zero frontend code anywhere in
static/vindex.js calls any of them — confirmed independently by 2 sibling forensic passes before this one
(Program Sigma Sprint 005, Program Omega Sprint 005's own dead-code removal). A paying customer cannot ever
trigger a feature they may be billed for. Two resolutions exist (wire up a UI trigger, or delist the feature
from the sellable registry/pricing) — which one is a product decision, not unilaterally resolved here.

### IRONLAWYER-DEBT-002 — 9 more backend routers follow the identical dead-feature pattern (Low-Medium, product decision needed)

Team Romeo: routers/region.py, style_checker.py, knowledge_hygiene.py, knowledge_transfer.py,
strategy_simulator.py, auto_discovery.py, agent_notifications.py, a second onboarding.py flow (distinct
from the live one), and whatsapp_notif.py all have zero live frontend callers, verified by grep across
every .html/.js file. Plus a fully-built duplicate CSV client-import wizard (routers/import_klijenti.py,
richer column-mapping UX) sitting unused alongside the live, cruder klijenti/router.py import. Whether to
wire these up or retire them as backend cleanup is a product decision spanning multiple sprints' worth of
scope — named as a pattern here, not resolved feature-by-feature.

### IRONLAWYER-DEBT-003 — 5-7 unreconciled "case strength/risk" scores on one screen (Critical/High, product decision needed — highest-priority item this sprint)

Teams Bravo, Charlie, Mike, and Oscar independently converged on the same finding: a single case's "how is
it going" is answered by CCC's health badge, Matter Intel's Ocena zdravlja, Cockpit's Procena rizika, a
manually-editable Rizik field, Case Genome's Snaga predmeta %, Case Ready Score, Digital Twin's 3 scenario
probabilities, and Copilot's Verovatnoća uspeha — 5-7 independently-sourced numbers, no shared label
vocabulary, no cross-reference, all using similar %/badge visual language. A lawyer cannot answer "is this
case actually strong?" without holding all of them in their head and guessing which is authoritative. Two
small UI-only mitigations shipped this sprint (the manual Rizik field relabeled "Rizik (ručno)" with a
pointer to the AI badge; Cockpit's problem list points to Rokovi/Dokazi) — but the real fix requires picking
ONE canonical "case strength" surface and demoting the rest, a product decision on which surface wins,
correctly not made unilaterally by a UX-fix sprint.

### IRONLAWYER-DEBT-004 — AI prediction confidence-checking gated behind a paid credit (High, billing decision needed)

Team Oscar: Court Predictor's base result shows a bare probability with no uncertainty framing; a
reliability/confidence check only appears if the lawyer spends an additional credit on "Proveri pouzdanost
predikcije." A lawyer who doesn't know to click that button sees a naked number with no warning it's an
estimate. Changing what's billed vs. free is a business-logic/credit-consumption decision, out of this
sprint's UI-only scope — flagged, not touched.

### IRONLAWYER-DEBT-005 — Systemic lack of ARIA/keyboard accessibility across the dynamic app (High, needs a dedicated sprint)

Team Quebec: zero aria-label/role/tabindex attributes anywhere in static/vindex.js (the file that renders
the entire authenticated app); 63 div onclick/span onclick controls with no keyboard affordance at all,
including the dashboard's own primary case-navigation rows. This sprint fixed the highest-value instance
(kc-panel-row/kc-sphere-quad dashboard navigation — role="button" tabindex="0" plus a new delegated
Enter/Space keydown handler) and one icon-only button's missing label, but full remediation across 63+
instances plus a real audit of screen-reader flow is out of a same-sprint safe-patch budget. Also noted:
button styling has only 12% adoption of the shared vx-btn component class (119 total buttons, 14 using it),
and ~26 parallel one-off badge class families exist for what is conceptually one "status pill" component —
a design-system consolidation opportunity, not a defect, named here for visibility.

### IRONLAWYER-DEBT-006 — No request timeout/retry on ~300 fetch() call sites (High, needs a dedicated sprint)

Team Uniform: zero AbortController/timeout wrapper exists anywhere in static/vindex.js — every fetch call
can hang indefinitely on a stalled connection (e.g. a lawyer on 3G in a courthouse basement), with no escape
except a browser-default multi-minute socket timeout or a force-quit. A shared fetchWithTimeout helper was
NOT added this sprint (a systemic change across ~300 call sites is too large a surface for a same-sprint
safe patch without risking subtle behavioral regressions on slow-but-legitimate requests) — named as the
highest-value follow-up item from the Extreme Personas team's findings.

### IRONLAWYER-DEBT-007 — Case list silently truncates at 200 of N with no indicator (High, needs a backend contract change)

Team Uniform: pred_load() fetches /api/predmeti with no limit/offset; the backend defaults to 200. For a
500-case lawyer, 300 cases are invisible with zero "showing 200 of 500" signal, no pagination, no in-list
filter beyond 4 sort pills. A correct fix needs the backend to expose a total count and the frontend to add
pagination/filtering — a real feature addition, not a copy/label fix, named as debt rather than guessed at
with an unverified partial patch.

### IRONLAWYER-DEBT-008 — No draft/progress persistence across reload or crash mid-flow (High, needs careful design)

Team Uniform: zero beforeunload handler and zero sessionStorage persistence of in-progress wizard state
anywhere in static/vindex.js. A lawyer 4 steps into Smart Intake (client picked, documents uploaded, AI
analysis run) who gets interrupted (laptop sleeps, tab reloads, crash) loses everything with no warning and
no recovery path. This is a real data-loss risk, not cosmetic — named as urgent debt rather than shipped as
a rushed, undertested sessionStorage implementation this sprint's time budget couldn't properly verify.

### IRONLAWYER-DEBT-009 — Case-detail "Pregled" tab is a 313-line kitchen-sink screen (Medium, structural redesign)

Teams Bravo, Echo, and Hotel: the default case-detail landing tab mixes read state (status/risk/deadlines)
with administrative actions (contract generation, client portal management, case closing) in one continuous
scroll, with deadlines alone appearing in 5 separate widgets. A genuine information-architecture redesign
(split "at a glance" from "admin actions"), not a same-sprint patch — named as debt, cross-referenced to
IRONLAWYER-DEBT-003's score-consolidation question since the two overlap on the same screen.

### IRONLAWYER-DEBT-010 — identify_case_problems wording doesn't disclose overdue items are folded into "next 7 days" (Medium, needs a backend string/field change)

Team November: the deterministic risk engine's own problem text ("N kritičan rok(a) u narednih 7 dana")
includes already-overdue deadlines (folded in by a prior mission's fix) but the string doesn't say so, and
neither /workspace nor /matter-intel exposes a separate zakasneli_rokovi count to the frontend. This sprint
added a UI-only fallback (Cockpit points to the Rokovi tab when the adjacent "Hitni rokovi" card would
otherwise contradict a reported critical deadline) but the underlying wording ambiguity needs a backend
text/field change, outside this sprint's UI-only mandate — flagged for handoff, not touched.

### IRONLAWYER-DEBT-011 — No manual chronology entry exists (Medium, product decision needed)

Team Lima: case chronology is exclusively AI/system-generated (document extraction, ZPP deadline-chain
save, lifecycle events) — a lawyer cannot log "client called re: settlement, 5.8." directly. Adding manual
entry is a new capability, not a UI polish item, and needs a product decision on scope (a full note-taking
feature vs. a lightweight chronology-only add) before implementation.

### IRONLAWYER-DEBT-012 — 3 of 5 case-creation code paths are dead/hidden (Medium, product decision needed)

Team Delta: pred_kreiraj()/#pred-new-modal (a plain single-field quick-create), qiOtvori() (Quick Intake
with client search), and bulkOtvori() (CSV bulk import) are fully implemented but have zero reachable
trigger anywhere in the shipped UI — confirmed by grep. Whether to promote them to visible entry points
(there's a real case for a fast single-field create path) or delete them as abandoned code is a product
decision on the case-creation flow's intended shape, not resolved unilaterally here.

### IRONLAWYER-DEBT-013 — Most AI response types render as undifferentiated text (Medium, incremental work)

Teams Papa and Kilo: Copilot's structured-response renderer only special-cases 6 of ~20 backend intent
types (this sprint upgraded the fallback to render markdown and a backend-provided deep-link button, a real
improvement, but the other 14+ intents still don't get bespoke structured cards); SUDSKA_PRAKSA citations
aren't clickable back to source documents. Both are incremental, well-scoped follow-up work for a future
sprint, not blocking.

**Severity summary across this mission's 13 debt items**: 1 Critical/High (IRONLAWYER-DEBT-003, the
unreconciled-scores finding, independently found by 4 teams), 6 items graded High or High-adjacent (-001,
-004, -005, -006, -007, -008), remainder Medium/Low-Medium. None require a business-logic, security,
AI-governance, or backend-architecture change to close on their own — -001/-002/-004 are product/pricing
decisions, -003/-009/-011/-012 are product/UX decisions, -005/-006/-007/-008 are real engineering work
correctly not rushed, -010/-013 need backend cooperation outside this sprint's UI-only mandate.

## Operation One Truth (2026-08-07) — "Canonical Legal Intelligence Consistency Certification"

7 independent teams (Intelligence Consistency, Data Truth, AI Boundary, UX Trust, Product Architect,
Database Integrity, Red Team) forensically audited the platform's #1 remaining pre-beta trust risk, first
surfaced as `IRONLAWYER-DEBT-003`: does a single legal case have exactly ONE canonical interpretation of
its own state, or can different modules claim different things about the same case? Full findings:
`docs/onetruth/INTELLIGENCE_SURFACE_MAP.md`, `docs/onetruth/ONE_TRUTH_ARCHITECTURE_MAP.md`. 12 duplicate-
truth/AI-boundary defects were fixed with test coverage this mission (see
`docs/onetruth/ONE_TRUTH_CERTIFICATION_REPORT.md` for the full list); the following 12 require a product
decision or are real engineering scope beyond a same-sprint safe patch, named here instead.

### ONETRUTH-DEBT-001 — Genome verification (`verify_genome()`) is advisory-only, never blocks a write (High, AI-governance decision needed)

Agent 3 (AI Boundary): `shared/genome_validator.py::verify_genome()` correctly DETECTS a bad Genome
(hallucinated document reference, internally inconsistent score) via `_verifikacija.odluka`, but a
`require_review` decision never blocks the write — the Genome still saves, version still increments. This
mission exposed the decision downstream (`shared/case_context.py`'s new `key_facts.genome_verifikacija_
odluka` field, so AI consumers CAN check it), but did not make verification enforcement itself block a
write — that is a genuine product/AI-governance decision (does a flagged Genome get held for confirmation,
or does the lawyer just see a warning badge?), not resolved unilaterally by a consistency-fix mission.

### ONETRUTH-DEBT-002 — Case readiness has 2 live, unreconciled sources on the same screen (High, product decision needed)

Agent 1: `shared/case_readiness.py::compute_case_readiness` (canonical, used to cap AI outputs across 5
modules) and `services/case_pipeline.py::calculate_case_ready_score` (an independent weighted checklist —
docs/klijenti/rokovi/strategija-tag/rizik-tag/rociste) both answer "is this case ready," using overlapping
Serbian vocabulary ("spreman"/"ready"), rendered as adjacent widgets on the same case-detail page. Which
checklist should be authoritative is a product decision about what "ready" actually means to a lawyer, not
a technical merge.

### ONETRUTH-DEBT-003 — Success-probability fragmentation across Digital Twin/Court Predictor/Hearing CC (High, product decision needed)

Agent 1: 4 independently-prompted GPT percentages answer "will this case succeed" (Digital Twin's 2
sub-features, Court Predictor's `prediktuj_ishod`, Hearing CC's `hearing_score`) — each readiness-capped at
the extremes but never cross-checked against each other or against Genome's own `snaga_predmeta_procent`.
Only Copilot's `ANALIZA_PREDMETA` has been fixed (aliased directly to Genome) — the model to replicate, but
doing so for the other 4 means deciding whether Digital Twin/Court Predictor/Hearing CC should show
Genome's number instead of generating their own, a product behavior change beyond a consistency patch.

### ONETRUTH-DEBT-004 — Confidence/Pouzdanost has 7 independently-coded scales (Medium, architecture decision needed)

Agent 1: the single most fragmented category found — Court Predictor's own 2 internal confidence scales, a
fully dead `services/confidence_calibrator.py` (zero callers anywhere), Case Intelligence's own briefing-
confidence formula, Judge Profile's odluke-count formula, Opponent Intel's mostly-GPT-self-declared scale,
Genome's own `genome_kompletnost`, and `genome_validator.py::verify_genome`'s 3-state decision. None share
a scale. Unlike risk/readiness/probability, none currently co-render in direct visible contradiction on one
screen — lower urgency, but a real target for a future consolidation sprint.

### ONETRUTH-DEBT-005 — `predmeti.case_dna`/`kanban_faza`/`oblast` have no migration provenance (High, disaster-recovery risk)

Agent 6 (Database Integrity): these 3 columns are read/written by dozens of call sites but were never
created by any file in `migrations/` — added directly to live Supabase outside the tracked migration
system, the identical disease `migrations/105` already fixed once for `predmet_dokumenti` the same day. A
fresh/disaster-recovery environment built from `migrations/` alone would have Kanban permanently break
(every drag-move 500s) and Genome 500 on every read. A backfill migration declaring these columns (matching
`migrations/105`'s own pattern) should be drafted and run by the founder — not attempted here per this
project's standing convention that migrations are drafted, never run, by the coordinator.

### ONETRUTH-DEBT-006 — `predmeti.oblast_prava` is read by 6 AI features but never written (Medium, needs per-file verification)

Agent 6: `routers/cio.py`, `case_intelligence.py`, `decision_replay.py`, `services/agent_tasks/
precedents_radar.py`, `court_portal_watcher.py` all read `predmeti.oblast_prava` for AI-context practice-
area signals — no `predmeti` INSERT/UPDATE path anywhere ever writes it (the correctly-populated column for
this concept is `predmeti.oblast`, a different name). A full repo grep found `oblast_prava` is ALSO a
legitimate, correctly-populated column on several OTHER tables (`lessons_learned`, `case_benchmarks`,
`confidence_audit` records, `style_checker` results) — meaning the naive fix ("just swap to `oblast`
everywhere") is unsafe without verifying, file by file, which `.select()` calls actually target `predmeti`
vs. a different table. Deferred rather than risk a rushed, under-verified swap across 5+ files.

### ONETRUTH-DEBT-007 — Case-strength portfolio aggregation computed independently by Health Index and CIO (Medium)

Agent 1: `routers/health_index.py::_compute_health` and `routers/cio.py::_generiši_cio_izvestaj` both
independently loop over active cases averaging `case_dna.snaga_predmeta_procent`, with different
case-inclusion criteria (Health Index's raw try/except vs. CIO's requirement that `build_case_context()`
successfully computed `key_facts`) — can diverge for the same portfolio, both render on the dashboard.

### ONETRUTH-DEBT-008 — Copilot's PREDLOZI intent bypasses both canonical priority and canonical next-action (Medium, narrow blast radius)

Agent 1: `routers/copilot.py::_handle_predlozi` computes its own ad hoc priority (pure deadline proximity)
and its own next-action suggestions directly from raw queries, bypassing both `shared/attention_priority.py`
and `case_actions`/`shared/case_readiness.py::top_open_action` — a 6th priority vocabulary and a 4th
next-action generator, live only in this one Copilot intent. Narrow scope (one chat intent), not fixed this
mission given the broader fixes prioritized.

### ONETRUTH-DEBT-009 — Notification generation still has 2 independent, non-identical sources (Medium, residual after this mission's fix)

Agent 2 / this mission's own fix: `routers/notifications.py::_generate_notifications`'s rok/hitan_rok block
(sourced from `predmet_hronologija`) and `services/case_evolution.py`'s canonical projection (sourced from
`rocista` via `case_actions`) are NOT a strict subset relationship — `predmet_hronologija` includes
document-extracted deadlines with no corresponding `rocista` row. This mission fixed the CONFIRMED
CRITICAL bug (the two systems' generators destructively colliding — the delete-then-regenerate cycle used
to wipe out the other system's dedupe-tracked rows) by scoping the delete to exclude dedupe_key-bearing
rows. What remains, deferred: the two systems can still independently generate a notification for the same
underlying rociste-derived deadline from two different queries, producing 2 visible bell-icon rows instead
of 1 — a duplicate-visibility issue, not a data-loss/contradiction issue. Also corrected this mission:
`services/case_evolution.py`'s own docstring falsely claimed this generator was "retired" — verified false
by direct trace (this mission's Principle 0), corrected in place.

### ONETRUTH-DEBT-010 — Case Commander + 9 more orphan routers, zero frontend entry point (carried forward, unchanged)

Same finding as `IRONLAWYER-DEBT-001`/`-002` — re-confirmed still open by this mission's Agent 1 (Case
Commander) and Agent 6 (the DB-layer symptom: `commander_analize`/`predictor_analize`/`hearing_briefovi`
tables written on every AI call across 6+ call sites, never read back by anything — wasted OpenAI spend
plus a false "history is tracked" signal for engineers). Not re-litigated here; still a product/backend
decision, not a consistency-mission fix.

### ONETRUTH-DEBT-011 — `services/confidence_calibrator.py` is fully dead code (Low)

Agent 1: zero callers anywhere in the repo (confirmed by grep), a near-duplicate of Court Predictor's own
live `_calc_confidence_nivo`/`_procenat_iz_score`. Safe to delete; not done this mission to keep the diff
scoped to consistency fixes, not cleanup.

**Severity summary across this mission's 12 debt items**: 3 High (`-001`, `-002`, `-003`, `-005` — 4 items
graded High), remainder Medium/Low. None require an immediate fix to keep the platform safe to use — the
CRITICAL live bugs this mission found (Dashboard's stale risk cache, the notification-deletion collision,
CCC's discarded-canonical-value regression) were fixed directly, per the same STOP RULE discipline every
prior certification in this program has followed.

---

# Operation Single Brain, Mission 001 — Debt Register (2026-08-07)

20 real fixes landed this mission (full ledger: `docs/singlebrain/DUPLICATE_TRUTH_ELIMINATION_REPORT.md`).
The 14 items below are what Phase 1's 10 forensic teams found that this mission did NOT close, each with
its citation back to the specific forensic report. See `docs/singlebrain/FINAL_SINGLE_BRAIN_CERTIFICATE.md`
for why the mission's own "zero fragmentation" bar is honestly not met while these remain open.

### SINGLEBRAIN-DEBT-001 — Case Readiness has 2 live, co-rendered sources (High)

`shared/case_readiness.py::compute_case_readiness` (canonical, deterministic, zero GPT) and `services/
case_pipeline.py::calculate_case_ready_score` (an independent 0-100 weighted checklist) are both live,
both rendered on the case screen (`static/vindex.js:10543`, `:11954`), and never cross-checked against each
other. The single highest-value remaining item — most likely of everything in this register to visibly
contradict itself in front of a lawyer on the same screen. Not attempted this mission: consolidating these
is a genuine design decision (which becomes the canonical 0-100/5-state source, what happens to the other's
existing callers) larger than a mechanical fix. Evidence: `docs/singlebrain/DECISION_DEPENDENCY_GRAPH.md`
§"Case Readiness — two independent, live, unreconciled systems".

### SINGLEBRAIN-DEBT-002 — `court_predictor.py::argument_reputation` is range-clamped but not readiness-capped (Medium)

Unlike the 4 other success-probability generators this mission hardened, `argument_reputation`'s scores are
confirmed range-clamped (0-100) but never checked against `CAP_BY_READINESS` — a `CRITICAL_GAP` case could
still see an uncapped-by-readiness argument-reputation score. Evidence: `docs/singlebrain/
DECISION_DEPENDENCY_GRAPH.md` Success Probability table.

### SINGLEBRAIN-DEBT-003 — Portfolio Case-Strength Aggregation diverges between health_index.py and cio.py (Medium)

Two independently-coded portfolio-level averages of the same underlying per-case strength value, different
inclusion filters — confirmed not fixed this mission. Evidence: `docs/singlebrain/TRUTH_REGISTRY.md` §5,
`DECISION_DEPENDENCY_GRAPH.md` duplicate-computation red flag #5.

### SINGLEBRAIN-DEBT-004 — 12 of 15 Confidence mechanisms remain unreconciled (Medium-High, bundle)

This mission closed 3 of 15 (Opponent Intel's `pouzdanost`, CIO's top-level `pouzdanost`, `genome_
kompletnost`). Not closed: `services/confidence_calibrator.py` (fully dead code, near-duplicate of Court
Predictor's live logic); the Confidence Audit/Brier-score calibration subsystem (structurally dead — its
own dependency column `recommendation_log.confidence_band` is never written by any code path); Client
Twin's `pouzdanost` (GPT self-declared, rule stated only in prompt text, never enforced); Lessons-Learned's
`pouzdanost` (deterministic but its own distinct thresholds, not reconciled with the others); Gap Engine's
per-gap `pouzdanost` (a `hitnost→pouzdanost` lookup, separate scale); RAG/Precedent retrieval computing 2
different confidence formulas inside the same function call (`app/services/retrieve.py:663-669` and
`:672-697`, one English 3-tier, one Serbian 4-tier); Document Intake's 3-layer OCR/classification/
extraction confidence sub-pipeline (raw 0.0-1.0 float, a 14th distinct vocabulary); Document Auto-Link's ad
hoc matching confidence (only 2 possible values, 95/74). Large enough in aggregate to warrant its own scoped
mission per `FINAL_SINGLE_BRAIN_CERTIFICATE.md`'s own recommendation, not a bundled fix here. Evidence:
`docs/singlebrain/TRUTH_REGISTRY.md` §4.

### SINGLEBRAIN-DEBT-005 — `routers/copilot.py::_handle_predlozi` bypasses the canonical priority engine (Medium)

Computes its own ad hoc 3-value priority directly from deadline proximity instead of `shared/
attention_priority.py` or `case_actions.prioritet` — a confirmed-live bypass, narrow scope (one chat
intent). Evidence: `docs/singlebrain/DECISION_DEPENDENCY_GRAPH.md` §"Confidence, Priority, Gaps...".

### SINGLEBRAIN-DEBT-006 — `predmet_istorija`'s `"[Rizik] {date}"` cache tag still has 2 independent writers (Low)

`api.py:5426-5459` and `services/case_pipeline.py:535-598` both write this historical snapshot,
unaware of each other. Currently low-risk: every live reader this mission touched or verified correctly
treats the tag as historical-only (never "current"), so the dual-writer situation cannot currently produce
a visible contradiction — but it remains 2 sources for what should be 1 write path. Evidence: `docs/
singlebrain/DECISION_DEPENDENCY_GRAPH.md` duplicate-computation red flag #9.

### SINGLEBRAIN-DEBT-007 — `GET /api/portfolio`'s stale risk cache pattern is confirmed dead/orphaned (Low)

Same stale-cache bug class as the now-fixed `command_center`, but this endpoint has zero confirmed frontend
callers — no live user impact, kept unfixed to avoid touching dead code this mission didn't need to.
Evidence: `docs/singlebrain/DECISION_DEPENDENCY_GRAPH.md` Risk Level §"Displays".

### SINGLEBRAIN-DEBT-008 — Strategy's `_advisory_provenance()` disclosure object is computed but never rendered (Low)

Every `routers/strategija.py` GPT response carries a transparency/disclosure object; confirmed by direct
grep of `static/vindex.js` that it is never displayed anywhere. A "missing UX," not a truth conflict — no
lawyer currently sees two different answers, they just don't see the disclosure that exists. Evidence:
`docs/singlebrain/DECISION_DEPENDENCY_GRAPH.md` §"Strategy".

### SINGLEBRAIN-DEBT-009 — `routers/matter_intel.py::preflight_check`/`get_uncertainty_dashboard` remain a live landmine (Low-Medium)

Confirmed zero frontend callers (dead in normal use), but both are GPT-native and reachable via direct API
call — `preflight_check`'s own `status`/`score` ARE already clamped/enum-validated (`BLACKSWAN-AI-001`), so
the live risk is narrower than "unguarded GPT output," but the endpoint's mere existence as an unreconciled
3rd readiness-adjacent system (Team 2's "2C — Dead" classification) is itself the debt. Evidence: `docs/
singlebrain/DECISION_DEPENDENCY_GRAPH.md` §"Case Readiness" 2C.

### SINGLEBRAIN-DEBT-010 — Readiness-tier cap silently no-ops when `build_case_context()` throws (Medium)

Compounding gap across the 3 sites this mission added unconditional 0-100 clamps to
(`digital_twin.py` ×2, `court_predictor.py::prediktuj_ishod`): `if case_context and not
case_context.get("error"):` skips the readiness-tier cap entirely on a transient DB/context-fetch failure.
The unconditional clamp added this mission is a genuine, verified mitigation (a wild GPT number can no
longer escape 0-100 even during a context-fetch failure) but a genuinely `CRITICAL_GAP` case could still
see up to 100% instead of the tier-appropriate 50% during that failure window. Not fixed this mission: no
safe default cap value could be picked without guessing at product intent (capping unconditionally on ANY
context-fetch error, even for a healthy case, risks the opposite failure mode — understating a strong
case's real probability due to an unrelated transient error). Evidence: `docs/singlebrain/
AI_BOUNDARY_CERTIFICATION.md` gap #6.

### SINGLEBRAIN-DEBT-011 — Kanban board's closed-case visibility not investigated this mission (Unknown severity)

Carried forward from this mission's own TIER 2 triage list, never independently verified true or false this
session — named here so it isn't silently dropped, not because it's confirmed. Needs its own dedicated
investigation before any fix is attempted (risk of behavior change to a visible, frequently-used board).

### SINGLEBRAIN-DEBT-012 — CIO's `neprimecena_kontradikcija` re-hallucinates an already-computable fact (Medium)

`routers/cio.py`'s prompt asks GPT to find "a critical contradiction not yet addressed" purely from raw
context, even though this is mechanically computable by filtering `case_dna.kontradikcije[]` for
`tezina=="kriticna"` (now normalized via `normalize_tezina()`, closed this mission) cross-referenced against
whether a `RAZRESITI_KONTRADIKCIJU` action is still open. `validate_predmet_reference` mitigates by
nullifying the block if the named case isn't real, but does not verify the named case actually HAS an open
critical contradiction. Not fixed this mission: would require new cross-portfolio aggregation logic, closer
to "new algorithm" territory than a mechanical guard — a scope call, not an oversight. Evidence: `docs/
singlebrain/TRUTH_REGISTRY.md` §12 (revises Operation One Truth's own prior "no fix needed" verdict on this
exact field).

### SINGLEBRAIN-DEBT-013 — `predmeti.status` classifier fragmentation beyond the `u_toku` fix (Medium)

This mission closed one specific, confirmed landmine (`conflict_check.py`'s `"u toku"`/`"u_toku"` spelling
gap). The broader fragmentation remains: `analytics.py`/`copilot.py` treat closed as `("zatvoren",
"arhiviran")`; `dashboard.py` treats active as "not in a 3-value closed set"; `cio.py`/`morning_briefing.py`/
`zakon_monitoring.py` filter active as a 3-value allow-list. Currently low-risk only because no writer
produces any value outside `{"aktivan","zatvoren"}` today — a landmine for the day a richer status value is
introduced, not a live bug now. Evidence: `docs/singlebrain/TRUTH_REGISTRY.md` §14.

### SINGLEBRAIN-DEBT-014 — Court Predictor's own capped `procenat_min`/`procenat_max` never actually rendered (Low)

The ordering/clamp fix this mission made to `prediktuj_ishod` is correct groundwork, but Team 2 confirmed
the computed-and-capped number structurally never reaches the lawyer through the single-module `/analiza`
UI flow (only free-text narrative renders there) — a "wasted work" finding, not a truth-inconsistency, but
worth naming since it means the fix's real-world visibility is currently zero outside the "Kompletna
Analiza" orchestrator view, which shows a different percentage. Evidence: `docs/singlebrain/
DECISION_DEPENDENCY_GRAPH.md` §"Success Probability" note.

**Severity summary across these 14 items**: 1 High (`-001`), 6 Medium (`-002`, `-003`, `-005`, `-010`,
`-012`, `-013`), 1 Medium-High bundle (`-004`), 5 Low (`-006`, `-007`, `-008`, `-009`, `-014`), 1 Unknown
(`-011`, not investigated). None are confirmed live data-loss or crash risks — the CRITICAL-adjacent live
bugs this mission found (stale Command Center risk cache, dead Health Index sub-score, missing-evidence
false positives, the client-portal deadline query matching zero rows) were fixed directly, per the same
STOP RULE discipline every prior certification in this program has followed.

---

# Operation Single Brain, Mission 002 — Debt Register (2026-08-07)

5 real fixes landed this mission (full ledger: `docs/singlebrain/FRAGMENTATION_ELIMINATION_REPORT.md`),
closing the specific reproduced contradiction that motivated the mission plus the most serious unguarded-
AI-output finding across both Single Brain missions. The 12 items below are what 6 forensic teams found
that this mission did NOT close, each cited to its specific forensic source. See `docs/singlebrain/
SINGLE_BRAIN_MISSION_002_FINAL_CERTIFICATE.md` for the honest scorecard against this mission's own 5
stated acceptance criteria.

### SINGLEBRAIN2-DEBT-001 — Next Action has 3-4 independent generators (High)

`shared/case_readiness.py::top_open_action()` (canonical) coexists with `services/case_pipeline.py::
_step_copilot_preporuka` (independently re-derives "what to do" via `identify_case_problems()`, rendered
directly beside the Case Ready Score checklist on the same screen area as the AI Briefing panel's
`top_open_action()`-derived answer elsewhere), `routers/copilot.py::_handle_predlozi` (own ad hoc
priority/next-step generator bypassing `case_actions` entirely — its granular items aren't rendered, only
a summary count, narrowing but not eliminating the exposure), and `routers/zastarelost.py` (its own
independent deadline-urgency thresholds, parallel to but not sharing `case_evolution.py::_priority_by_days`
— currently harmless only because the cutoffs happen to coincide today). A genuinely new category Mission
001 never separately mapped as its own concept. Evidence: `docs/singlebrain/SINGLE_BRAIN_DECISION_MAP.md`
§"Next Action", Team 1's Decision Authority Map.

### SINGLEBRAIN2-DEBT-002 — Case Genome's case-strength score surfaces unlabeled as a de facto "risk"/"success" metric (High — clearest remaining Criterion 5 violation)

`case_dna.snaga_predmeta_procent` (case-strength, argument quality) surfaces in 3 lawyer-facing places
that read like a DIFFERENT metric than `risk_engine.py`'s own "rizik": CIO's portfolio panel, Copilot's
"Verovatnoća uspeha", and — most directly — the Case Genome hero panel's own thresholds
(`static/vindex.js:17202-17207`) which label the case "Visok rizik"/"Srednji rizik"/"Povoljna pozicija"
straight from this score, one click from the Pregled tab where the deterministic risk badge lives. Same
word, two unrelated formulas. Likely the fastest of the 12 deferred items to fix (a labeling change plus
a staleness timestamp, not a data-flow rewrite) — named as the 2nd highest-leverage starting point for
the next mission. Evidence: Team 4's Frontend Truth Audit, Team 6's UX walkthrough (both independently
found this).

### SINGLEBRAIN2-DEBT-003 — Portfolio case-strength aggregation still diverges (Medium, carried forward unchanged from SINGLEBRAIN-DEBT-003)

`health_index.py` and `cio.py` still use different population filters when averaging `snaga_predmeta_
procent` across the portfolio. Re-confirmed unchanged by Team 1. Evidence: `docs/singlebrain/
SINGLE_BRAIN_DECISION_MAP.md` §"Case Strength".

### SINGLEBRAIN2-DEBT-004 — Confidence means 4 different things on one case page (Medium)

RAG source-grounding confidence, Genome completeness-as-confidence proxy, the Sveobuhvatna Procena
report's own independent confidence verdict, and firm-wide historical calibration bands all coexist —
none share a scale. Evidence: Team 4's Frontend Truth Audit.

### SINGLEBRAIN2-DEBT-005 — Readiness-tier cap still fails open on context-fetch error (Medium, = SINGLEBRAIN-DEBT-010, unchanged)

Re-confirmed still open by Team 3 at all 7 call sites (`court_predictor.py` ×4 post this mission's own
fix, `digital_twin.py` ×2, `hearing_cc.py` ×1) — `_dohvati_case_context_ako_postoji()` swallows any
`build_case_context()` exception and returns `None`, silently skipping the tier cap (the separate
unconditional 0-100 clamp still applies as a floor/ceiling). Not fixed this mission for the same reason
Mission 001 named: no safe default cap value could be picked without risking a different failure mode
(a healthy case's probability wrongly understated by an unrelated transient error).

### SINGLEBRAIN2-DEBT-006 — Case Commander remains dead code (High leverage, not a bug)

`routers/case_commander.py` is, by design, the platform's most architecturally correct consumer of all 8
decision concepts this mission mapped — zero independent GPT decisions, reads `build_case_context()`
exclusively. Confirmed zero live frontend callers (Team 1). The best-designed consolidation is invisible
to lawyers while the fragmented sources are what's actually rendered. This mission's own #1 recommendation
for the next mission — wiring it up would directly address `SINGLEBRAIN2-DEBT-001` and Mission 001's still-
open `SINGLEBRAIN-DEBT-001` — but explicitly NOT attempted here, since doing so before finishing this
mission's own readiness-cap fix would have created a new, immediately-visible 3-way collision instead of
resolving one.

### SINGLEBRAIN2-DEBT-007 — `predmeti.status` classifier fragmentation, 5-way (Medium)

5 different modules classify "is this case active" with non-identical predicate logic; only 2 values
(`"aktivan"`/`"zatvoren"`) are ever actually written, so currently low-risk, but a landmine the day a
3rd status value is introduced. Full specification for the fix: `docs/singlebrain/
CASE_STATUS_CANONICAL_MODEL.md`. Not implemented this mission — evidence: Team 5's Database Truth Audit.

### SINGLEBRAIN2-DEBT-008 — `health_score` naming collision across 3 unrelated domains (Low)

Firm-wide Health Index score, `risk_engine.py`'s per-case inverse-of-risk number, and Web3's AML
documentation-completeness score all share the literal field name `health_score`. Each is internally
single-sourced within its own domain (no live data divergence found) — a naming trap for future
engineers, not a duplicate-truth bug. Not fixed (rename would touch many call sites for a naming-only
issue). Evidence: Team 1's Decision Authority Map.

### SINGLEBRAIN2-DEBT-009 — DB CHECK constraints missing on readiness-adjacent columns (Medium)

No CHECK constraint on `predmeti.status`, `predmeti.rizik`, `predmeti.kanban_faza` (unconfirmable live),
`case_actions.confidence` (no 0.0-1.0 range check, currently constant-by-accident not by guarantee),
`predmet_istorija.confidence` (~8 independent insert sites using literal `"LOW"/"MEDIUM"/"HIGH"` strings,
no shared constant). The one clean counter-example (`case_actions.tip`/`prioritet`/`status`, migration
099) proves the pattern is achievable. Requires migrations — per this engagement's standing convention,
drafted but never run by the coordinator; the founder runs migrations. Evidence: Team 5's Database Truth
Audit.

### SINGLEBRAIN2-DEBT-010 — Shadow columns, zero migration provenance (Medium, carried forward unchanged)

`predmeti.kanban_faza`, `case_dna`, `oblast`, `oblast_prava` have no provenance in `migrations/*.sql` nor
`supabase_setup.sql`/`supabase_migration*.sql` — independently re-confirmed by Team 5, matching Operation
One Truth's own prior finding (`docs/onetruth/INTELLIGENCE_SURFACE_MAP.md`). Separately: `predmeti`,
`predmet_istorija` themselves DO have real provenance, but only in `supabase_setup.sql`, which `scripts/
audit_state.py`'s own live-vs-migration checker doesn't scan (only globs `migrations/`) — a blind spot in
the audit tooling itself, distinct from the shadow-column risk.

### SINGLEBRAIN2-DEBT-011 — `GET /api/portfolio` stale cache + `matter_intel.py`'s dead uncertainty dashboard (Low, carried forward unchanged)

Both confirmed still dead/orphaned (zero frontend callers, re-verified by Team 5 and Team 2 respectively)
— low practical risk, but each is a live landmine via direct API call. Not fixed this mission.

### SINGLEBRAIN2-DEBT-012 — `predmet_health_log.rizik_label` confirmed dead (Low)

Write-only column — written daily alongside `health_score` but the one SELECT that exists against this
table explicitly excludes it. Independently re-confirmed by Team 5. Schema cleanup (dropping the column
or wiring a reader), not attempted this mission.

**Severity summary across these 12 items**: 2 High (`-001`, `-002`), 5 Medium (`-003`, `-004`, `-005`,
`-007`, `-009`), 1 High-leverage-not-a-bug (`-006`), 4 Low (`-008`, `-010`, `-011`, `-012`). None are
confirmed live data-loss or crash risks. `-001`/`-002`/`-006` together point at the same next mission's
natural starting point: wire up Case Commander, carefully, after first confirming it wouldn't create new
visible contradictions against the systems this mission and Mission 001 already fixed.

---

# Operation Singular Intelligence, Mission 001 — Debt Register (2026-08-07)

8 real fixes landed this mission (full ledger: `docs/singular/DEPRECATION_PLAN.md`), including the
single worst AI-boundary gap found across this engagement's 3 prior Single Brain/Singular Intelligence
missions (the Web3/MiCA compliance suite's risk-inversion bug). The 12 items below are what 6 forensic
teams found that this mission did NOT close, each cited to its forensic source. See `docs/singular/
SINGULAR_INTELLIGENCE_CERTIFICATE.md` for the honest scorecard against this mission's own 6 stated
acceptance criteria.

### SINGULAR-DEBT-001 — Recommendation has 3-4 independent generators, including a redundant Case Commander/AI Briefing twin (High, headline item)

`shared/case_readiness.py::top_open_action()` (canonical) coexists with `services/case_pipeline.py::
_step_copilot_preporuka` (independent, renders "Copilot preporuka" beside the Case Ready Score
checklist), `routers/copilot.py::_handle_predlozi` (independent, granular items not rendered), and
`routers/zastarelost.py`'s own thresholds (`SINGULAR-DEBT-004`). Additionally, Team C's Decision
Architecture Audit found `routers/case_commander.py`'s canonical core is a REDUNDANT TWIN of
`routers/case_intelligence.py`'s already-live "AI Briefing" panel (both independently converged on the
same design: `build_case_context()` core + 2 quarantined GPT fields) — Case Commander is not filling an
empty slot, wiring it up naively would add a 3rd voice, not consolidate. Full architecture with 2 safe
activation paths (consolidate-first vs. activation-absorbs-consolidation): `docs/singular/
DECISION_ARCHITECTURE.md`. Not implemented this mission — the single highest-leverage next step, with
its diagnosis already complete.

### SINGULAR-DEBT-002 — `strategy_simulator.py`'s `rizik_score`/`verovatnoca` unguarded (High, dead code)

Red Team Attack 2: zero clamp/enum-guard, reproduced with a poisoned response (`rizik_score: 999999999`,
a fabricated certainty enum) passing straight through. `/api/simulator/*` confirmed zero frontend
callers today — same risk class as other confirmed-dead landmines (`SINGLEBRAIN-DEBT-009`,
`matter_intel.py::preflight_check`). Not fixed (dead code, lower priority than live findings).

### SINGULAR-DEBT-003 — `recommendation_log`'s dead insert path (Medium, structural)

`services/learning_engine.py::log_recommendation` inserts columns `tip`/`tekst` against a table whose
real columns (migration 037) are `tip_preporuke`/`tekst_preporuke` — every insert has always failed,
masked by a bare `except Exception`. `log_recommendation` also has zero callers anywhere in the
codebase. The platform's entire recommendation-outcome learning loop (`confidence_auditor.py`,
`decision_replay.py`, Court Predictor's stats panel) has been permanently starved since inception.
This mission fixed the one live UI consequence (the stats panel's misleading always-0/0 display, § Fix
7) but did NOT reactivate the underlying pipeline — that is a feature-completion project (wire a real
caller, fix the column names, decide what "accepted/rejected" means operationally), not a truth-
fragmentation fix, and is out of this mission's scope by its own Core Rule 1.

### SINGULAR-DEBT-004 — `routers/zastarelost.py`'s 2 different urgency-threshold ladders in the same file (Medium)

`/guardian/analyze` (≤3/≤7/≤14 days) vs. `/guardian/scan` (≤2/≤5/≤14 days, different bottom label) —
a 3-day-out deadline is "kritično" on one endpoint, only "hitno" on the other. Both confirmed zero
frontend callers today — a landmine, not a live contradiction. Evidence: Team A's Semantic Mapping
(independently found by 3 of 4 sub-forks).

### SINGULAR-DEBT-005 — `predmeti.oblast` vs `predmeti.oblast_prava` duplicate pair, one orphaned (Medium)

Two columns for the same fact ("area of law"). `oblast` is written (`api.py:3644-3660`) and read by 7
modules; `oblast_prava` is read by 6 DIFFERENT AI modules (`cio.py`, `case_intelligence.py`,
`precedents_radar.py`, `court_portal_watcher.py`, `decision_replay.py`, `knowledge_transfer.py`) but has
**zero confirmed application-code writer** anywhere — those 6 modules are plausibly always reading an
empty string. Mission 002 already flagged both as "shadow columns, zero migration provenance"
(`SINGLEBRAIN2-DEBT-010`) but did not identify the duplicate-pair-with-orphan-writer structure. Evidence:
Team E's Database Reality Audit.

### SINGULAR-DEBT-006 — `predmeti.vrednost_spora` vs `case_dna.finansije.*` (Medium)

Two unreconciled "money at stake in this case" sources — one manual (`api.py:3651`), one AI-extracted
(`routers/case_dna.py:70-77`). Nothing reconciles them; several call sites defensively read
`predmet.get("vrednost_spora") or predmet.get("vrednost")` where the bare `vrednost` key has no
confirmed writer (likely dead residue of a pre-rename column). Evidence: Team E.

### SINGULAR-DEBT-007 — `knowledge_profiles.ukupno_predmeta`/`win_rate`, same manual-override pattern as `predmeti.rizik` (Medium)

A user types both directly at profile creation with no validation; a separate GPT extraction endpoint
silently OVERWRITES the same columns whenever it returns a value, with no provenance flag for human-
typed vs. AI-derived and no reconciliation. Structurally identical to the already-known `predmeti.rizik`
pattern, found this mission on a table neither prior mission examined (migration 040). Evidence: Team E.

### SINGULAR-DEBT-008 — `case_dna.py` refresh's cross-table staleness with `predmet_hronologija` (Low-Medium, partially mitigated)

`_sync_rokovi_to_hronologija()` writes freshly-extracted deadlines into `predmet_hronologija`
UNCONDITIONALLY, before the `case_dna` UPDATE, with no rollback on failure. This mission's Fix 5 stopped
the endpoint's RESPONSE from lying about the outcome (`case_dna_persisted` flag, honest genome returned)
but did not close the underlying gap: the real, UI-facing "Hitni rokovi" calendar can still show
deadlines from a Genome version that was never actually saved to `predmeti.case_dna`, which itself still
shows the old version. A full fix needs either a DB transaction wrapping both writes or a compensating
rollback of the hronologija rows on `case_dna` UPDATE failure. Evidence: Team E, reproduced in
`tests/test_singular_intelligence_phase4_adversarial.py::test_attack4_stale_case_dna_cache_cannot_override_failed_write`
(proves the RESPONSE is now honest; does not prove the calendar rows were rolled back, because they
aren't).

### SINGULAR-DEBT-009 — Confidence remains ~16 legitimately-distinct mechanisms (Medium, carried forward + 1 new source)

Unified only by this mission's Truth Contract GUARD requirement (enum-validate, fail-safe to least
confident), not a shared formula — by design, not an oversight (see `TRUTH_CONTRACT.md` §Confidence).
Carried forward from `SINGLEBRAIN2-DEBT-004`. New 16th source found this mission: `routers/
firm_memory.py::_apply_trust`, a 0.0-1.0 trust float, currently backend-only (no frontend caller).

### SINGULAR-DEBT-010 — `predmeti.status`'s 5-way classifier fragmentation (Medium, unchanged)

Carried forward from `SINGLEBRAIN2-DEBT-007`, full specification in `docs/singlebrain/
CASE_STATUS_CANONICAL_MODEL.md`, not re-attempted this mission.

### SINGULAR-DEBT-011 — Readiness-tier cap still fails open on `build_case_context()` error (Medium, unchanged, 3rd mission in a row)

Carried forward from `SINGLEBRAIN-DEBT-010`/`SINGLEBRAIN2-DEBT-005`, re-confirmed still open by Team B
at all 7+ call sites (`court_predictor.py` now ×5 post this mission's own `argument_reputation` fix,
`digital_twin.py` ×2, `hearing_cc.py` ×1). Not fixed for the same reason stated twice before: no safe
default cap value without risking a different failure mode (understating a healthy case's probability
due to an unrelated transient error).

### SINGULAR-DEBT-012 — `health_score` naming collision across 3 unrelated domains (Low, unchanged)

Firm-wide Health Index, `risk_engine.py`'s per-case inverse-of-risk field, and Web3's "Documentation
Health Score" all share the literal field name — each internally single-sourced within its own domain,
a naming trap not a data bug. Carried forward from `SINGLEBRAIN2-DEBT-008`, unchanged.

**Severity summary across these 12 items**: 2 High (`-001`, `-002`), 6 Medium (`-003`, `-005`, `-006`,
`-007`, `-009`, `-010`, `-011` — 7 items graded Medium), 2 Low/Low-Medium (`-004` graded Medium above,
`-008`, `-012`). None are confirmed live data-loss or crash risks; `-008` is the closest (a UI-visible
calendar/Genome mismatch is possible but requires a DB write failure to trigger, and the response no
longer lies about it when it does). `-001` is the clear next-mission starting point, with its full
architecture already specified — a future mission can execute directly rather than re-diagnose.

---

## Operation Singular Intelligence, Master Mission 002 (Part A) — 2026-08-07

Full report: `docs/singular2/MISSION_002_PART_A_REPORT.md`. 8 read-only teams re-audited the entire
repo from zero; 12 real, reproduced contradictions fixed (each with a genuine proof test, none
inventing a new algorithm — every fix reuses an existing canonical function/constant/DB constraint).
3 items formally deferred as debt:

### SINGULAR2-DEBT-001 — `vaznost` narrow-filter fragmentation (Medium)

9+ files still do a bare `== "kritičan"` check on `predmet_hronologija.vaznost` instead of reading
`shared/attention_priority.py::VAZNOST_TO_CANONICAL` (which Mission 002 itself just extended with
`"kljucan"`/`"info"` — see Fix 1 in the mission report). Each site has its own existing,
independently-reasoned threshold (cf. this register's own note above `SINGULAR2-DEBT` about
`ATTENTION_SURFACE_REGISTRY.md`'s "3-4 different, independently-chosen thresholds for what
'critical' means"). A blind mechanical find-replace across 9+ files without live-browser
verification of each one's own product intent is a separate, larger piece of work than a Part A
mechanical fix — not attempted this mission.

### SINGULAR2-DEBT-002 — `multi_agent.py` vs. `strategija.py` percentage-hedging philosophy (Low)

The two modules phrase GPT-generated success percentages with genuinely different confidence
tones/hedging language for the same underlying kind of claim. This is a prompt-tone/methodology
question, not a code defect — needs a founder/product decision on which philosophy is correct, not
a mechanical merge. Not attempted this mission.

### SINGULAR2-DEBT-003 — `case_actions`/CIO races narrowed, not fully eliminated (Low)

Mission 002's own Fixes 8 (`services/case_evolution.py::_consequence_refresh_case_actions`) and 12
(`routers/cio.py::cio_daily`) both close the reproduced lost-update/double-charge scenarios via
optimistic concurrency using existing columns/constraints, but neither achieves full cross-worker
serialization — a genuinely simultaneous write can still have "whichever call reaches the DB last
wins" as its outcome (correct, not corrupting, but not literally impossible contention). Full
elimination would need a session-scoped Postgres advisory lock, which means moving the reconcile
logic into a stored procedure — a real migration needing founder execution + live-DB verification,
neither available to the coordinator per this engagement's standing rule. Not attempted blind.

---

## Operation Living System (2026-08-07) — "A Day in the Life of a Law Firm"

Full reports: `docs/living_system/`. 14 read-only agents (4 Day-1 golden-path teams, 2 Day-2
interruption/concurrency teams, 1 Day-3 scale team, 3 chaos-engineering teams, 4 Red Team groups
covering all 20 named systems) simulated a law firm's actual working days rather than testing
endpoints in isolation. ~70 findings reproduced; 7 fixed this mission with regression proof (see
`docs/living_system/FIX_LOG.md`: Copilot readiness-cap, email-cron archived-case leak, billing
TOCTOU, Copilot deadline vocabulary, Client Portal collaborator-token bug, Genome frontend
false-success, Command Center archived-case leak). The remaining ~63 are named below, grouped by
theme, each with the reasoning for why a safe same-mission fix was not attempted.

**Numbering note**: findings are numbered in the order fixed/deferred during the mission's own
fix cycle, not by theme — grouped by theme below for readability.

### Archived-case leak family (same root cause as 2 already-fixed sites)

**LIVINGSYS-DEBT-003 (CRITICAL)** — CIO's daily portfolio report hard-caps at 40 cases, ordered
oldest-updated-first (the most-neglected cases), and presents the truncated, biased sample as the
true portfolio total with no `total_in_db`/`truncated` disclosure anywhere in the response or UI.
Not fixed this mission: raising or removing the cap changes real query cost at scale (a genuine
perf tradeoff, not a one-line fix) and the *ordering* bias needs a product decision (should the
sample favor recently-active or highest-risk cases, not just "not oldest") — a blind fix risked
trading one bias for another without founder input on which cases should represent the portfolio
when not all can be shown.

**LIVINGSYS-DEBT-036 — PARTIALLY FIXED** (Program Phoenix, Mission 001, 2026-08-07). The
lawyer-facing VISIBILITY harm is closed: `get_worklist`'s `predmeti` fetch now excludes
archived/closed cases at the query level, so `_fetch_open_actions` is never even asked about
them. Proof: `test_worklist_excludes_archived_case`. The underlying DATA HYGIENE gap remains
OPEN and unattempted: no consequence executor exists for case closure/archival that would close
out lingering `case_actions` rows in the database itself — a closed case's open action row still
has `status='open'` forever, merely invisible on this one board now rather than actually
resolved. Still real feature work for a future mission.

**LIVINGSYS-DEBT-037 — FIXED** (Program Phoenix, Mission 001, 2026-08-07). `guardian_scan` now
fetches `predmeti(id,status)` and excludes deadlines belonging to a positively-confirmed
archived/closed case. Proof: `tests/test_phoenix_mission_001_archived_case_visibility.py::
test_guardian_scan_excludes_deadline_on_archived_case`. Full report: `docs/phoenix/mission-001/`.

**LIVINGSYS-DEBT-038 — PARTIALLY FIXED** (Program Phoenix, Mission 001, 2026-08-07). The
archived-case leak in `_aggr_events` is closed (both the `rocista` and `predmet_hronologija`
loops now exclude positively-confirmed archived cases, while an unresolvable `predmet_id` still
fails open per a pre-existing test's own proven requirement). Proof:
`test_aggr_events_excludes_archived_case_hearing_and_deadline`. The 200-row cap with no
truncation signal AND the silent-partial-failure variant (`return_exceptions=True` with no
`degraded` flag) remain OPEN — not attempted this mission, still the standing next-mission
priority for this file.

### AI-credit-charged-on-failure family

**LIVINGSYS-DEBT-002 — FIXED** (Program Phoenix, Mission 004, 2026-08-07). `nacrt()` now gates
`UsageService.consume(...)` on `rezultat.get("status")=="success" and rezultat.get("data")`,
calling `UsageService.balance(...)` on failure instead — the exact pattern the sibling
`analiza()` already used. `generate_draft()`'s failure paths all converge on the same
`{"status":"error",...}` shape (verified: gating on `status` alone, not per-document-type
logic, correctly covers every failure path since none of them raise or return a different
shape). Proof: `tests/test_phoenix_mission_004_financial_credit_gating.py::
test_nacrt_does_not_charge_on_generation_failure` + `test_nacrt_charges_on_genuine_success`.

**LIVINGSYS-DEBT-006 — FIXED** (Program Phoenix, Mission 004, 2026-08-07). `commander_jutarnji`
now claims today's row via `INSERT` before generating/charging, relying on the table's existing
`UNIQUE(user_id, datum)` (migration 057) as the race-breaker — same idiom as CIO `/daily`'s own
fix, simplified since this table's cache has no time-based staleness window (no "claim a stale
row" step needed). Proof: `test_commander_jutarnji_concurrent_calls_charge_only_once` (real
interleaving via a stateful fake table).

**LIVINGSYS-DEBT-027 — FIXED** (Program Phoenix, Mission 004, 2026-08-07). `podnesak()` now
gates the charge on `entiteti` (extracted facts) being non-empty — the one sub-step whose
complete failure makes the draft closest to worthless; RAG/VKS/enrichment degrading
individually still charges, matching this item's own "Medium, not High" distinction from
`-002`. Proof: `test_podnesak_skips_charge_only_when_entiteti_empty`.

**LIVINGSYS-DEBT-012 (High)** — near-universal absence of `cooldown_seconds` (3 of ~60
`feature_registry` rows have one) plus a real TOCTOU race in `UsageService.consume()` for the few
that do. **Requires a migration** (seeding `cooldown_seconds` values for ~57 rows) — outside the
coordinator's authority per this engagement's standing "founder runs migrations" rule. The TOCTOU
component (reading "last call" before the corresponding insert commits) is a separate, smaller
fix that could be done without a migration — named as a distinct sub-item for a future mission
that doesn't need to wait on the migration to close at least that half.

### Drafting hallucination/quality family

**LIVINGSYS-DEBT-013 (CRITICAL)** — `/api/nacrt`'s quick-draft path (`drafting/templates.py`,
`drafting/router.py::generate_draft`) asks GPT to invent a specific ZOO/ZR statute article number
with zero RAG retrieval and zero critique pass, embedded directly into real legal document text.
The mission's single most severe finding. Not fixed this mission: the sibling `/api/podnesak`
path already has both RAG retrieval (`_izvori_kontekst`) and a critique pass
(`_critique_and_refine_draft`) — porting that infrastructure into the quick-draft path is a real
feature-scope change (new retrieval calls, new latency budget, new prompt engineering), not a
minimum-risk mechanical fix. Standing #1 recommendation for the next mission, with the exact
reusable infrastructure already named.

**LIVINGSYS-DEBT-014 (High)** — both drafting paths' extraction prompts explicitly instruct GPT
to return `""` (not omit the key) for unmentioned fields, which defeats `_popuni_sablon`'s
`[FIELD — POPUNITI]` visible-placeholder fallback (that fallback only fires on a genuinely
*absent* key). Confirmed systemic across ~12 podnesak types. Not fixed this mission: the correct
fix is prompt-level (stop instructing "or blank," start instructing "omit unknown fields") across
every one of ~12 templates in `templates/podnesci.py` plus `drafting/templates.py` — a real
multi-file prompt-engineering pass needing its own verification budget, not a single-function
patch.

**LIVINGSYS-DEBT-015 — FIXED** (Program Phoenix, Mission 009, 2026-08-07).
`_critique_and_refine_draft` now returns `(nacrt, critique_applied)` instead of a bare string —
`critique_applied` is `False` for both silent-degradation paths (exception; problem reported but
no fix text returned), `True` only when the pass genuinely verified the draft clean or fixed it.
`/api/podnesak`'s response gained the field; the frontend shows a conditional warning banner when
`False`. Proof: `tests/test_phoenix_mission_009_hallucination_disclosure.py::
test_critique_and_refine_draft_signals_false_on_exception` + 3 companion tests. Full report:
`docs/phoenix/mission-009/`. (`-013`/`-014`, the deeper RAG-grounding gap this pass checks
against, remain open for Mission 010.)

### Concurrency/idempotency family

**LIVINGSYS-DEBT-007 — FIXED** (Program Phoenix, Mission 002, 2026-08-07).
`_predInlineEdit`'s `doSave()` now sends `if_updated_at` from `window._predFull.predmet.
updated_at`, handles a `409` with a clear message + span revert, and `update_predmet` now
returns the new `updated_at` so the frontend's cache stays fresh for the next edit. Proof:
`tests/test_phoenix_mission_002_concurrency_guards.py::test_pred_inline_edit_sends_if_updated_at`
+ 2 companion tests. Full report: `docs/phoenix/mission-002/`.

**LIVINGSYS-DEBT-033 — FIXED** (Program Phoenix, Mission 002, 2026-08-07). `learning.py`'s
status write now carries `.neq("status", novi_status)` and writes a `predmet_hronologija` audit
entry on a successful (non-raced) close, matching `predmeti_close.py`'s own siblings. Proof:
`test_learning_outcome_guards_close_against_concurrent_reopen`.

**LIVINGSYS-DEBT-034 — FIXED** (Program Phoenix, Mission 002, 2026-08-07). `zadaci.py`'s
`StatusUpdate` gained an optional `if_updated_at` field (same opt-in shape as
`update_predmet`'s own); `azuriraj_status` applies it as a precondition and disambiguates
404-vs-409. Frontend: a new `_zadaciCacheById` cache feeds `zadaci_setStatus`'s own
`if_updated_at`. Proof: `test_azuriraj_status_rejects_stale_write_with_409`.

**LIVINGSYS-DEBT-035 (Medium)** — client-info corrections can silently flow into AI-drafted
document text via a stale browser-side snapshot (`window._predFull`) never re-fetched before
draft generation — a data-quality risk in generated legal text, not outright data loss. Needs a
product decision (re-fetch on every draft vs. a staleness warning) more than a mechanical fix.

**LIVINGSYS-DEBT-010 — FIXED** (Program Phoenix, Mission 005, 2026-08-07). Rather than porting
`claim_finalize()`'s RPC (would need a new migration), both `resolve_job_review`/
`reject_job_review` now gate their `emit_durable(...)` call on the already-existing
`result["review_resolved_now"]` boolean — a genuine retry (already resolved) now emits zero
new events. Proof: `tests/test_phoenix_mission_005_evidence_event_idempotency.py::
test_resolve_job_review_skips_event_emission_on_retry` + 2 companion tests.

**LIVINGSYS-DEBT-042 (High)** — 7 of 8 Case-Evolution event types have no reaper for a lost
durable-outbox insert (only `PREDMET_KREIRAN` has one, `reap_missing_pipeline_events`). A single
generic reaper (parameterized by event type) could plausibly cover all 7 — this is genuine new
infrastructure (a new cron-invoked function), not a mechanical fix, and needs its own design
pass on how to detect "should have emitted an event but didn't" per event type before
implementation.

**LIVINGSYS-DEBT-011 — PARTIALLY FIXED** (Program Phoenix, Mission 007, 2026-08-07).
`timeline_entry` now checks for an identical `(predmet_id, dogadjaj)` row created within the
existing `_CONSEQUENCE_STALE_PENDING_SECONDS` (300s) window before inserting — the same
"identical content, recent window" idiom already proven for `-043`. No migration. Proof:
`tests/test_phoenix_mission_007_case_evolution_chain_integrity.py::
test_timeline_entry_skips_duplicate_insert_on_reclaim`. Full report: `docs/phoenix/mission-007/`.
**Still open**: `genome_refresh` (needs a schema-level snapshot, not a mechanical port —
reasoning in `docs/phoenix/mission-007/ROOT_CAUSE_ANALYSIS.md`), `review_confirmation_audit`/
`review_rejection_audit` (append-only hash-chain semantics, needs a different guard shape),
`case_intelligence_summary` (real fix is a missing `UNIQUE` migration, not application code).

**LIVINGSYS-DEBT-043 — FIXED** (Program Phoenix, Mission 005, 2026-08-07). `kreiraj_rociste` now
checks for an identical `(predmet_id, sud, datum, vreme)` row created in the last 30 seconds
before inserting — reusing only existing columns, no migration. A match returns the existing
row with no new insert and no duplicate event. Proof:
`test_kreiraj_rociste_returns_existing_row_on_immediate_retry`.

**LIVINGSYS-DEBT-044 (Medium)** — `redni_broj` (document sequence number, used in AI-generated
DOK-XX citations) can collide under concurrent `finalize` calls to the same case — a citation-
ambiguity risk, not data loss. Would need either a DB sequence/unique constraint (migration) or a
per-`predmet_id` application-level lock — deferred pending a decision on which mechanism fits
this codebase's existing concurrency idioms.

**LIVINGSYS-DEBT-045 (Medium)** — Genome's in-process coalescing guard has a false-failure blind
spot causing up to 3 redundant refreshes for 2 concurrent document uploads (wasted GPT cost,
final `case_dna` content not corrupted). Fixing requires either awaiting the coalesced rerun
properly or relaxing `_consequence_genome_refresh`'s verification to tolerate "someone else's
concurrent run already advanced verzija" — a nuanced behavior change needing its own test matrix.

**LIVINGSYS-DEBT-046 (Low/Medium)** — CIO `/daily`'s already-fixed credit-charge race still lets
every concurrent requester pay the full GPT compute cost before losing the claim (cost-only, not
correctness); `/run` (force regenerate) has no claim/lock at all, sharing `-012`'s exposure.

### Silent failure / false success family (not yet fixed)

**LIVINGSYS-DEBT-009 — FIXED** (Program Phoenix, Mission 006, 2026-08-07). A real failure signal
(`ai_tags["_klasifikacija_greska"]`, existing JSONB column, no migration) is now threaded
through `_klasifikuj_dokument` → `klasifikuj_i_sacuvaj` (now returns its result, was always
`None`) → both `reklasifikuj` (now awaits synchronously and skips the charge on genuine
failure, matching every other GPT-consuming endpoint's own request/response convention) and
`_consequence_evidence_classify` (now logs a warning when the persisted classification is
degraded). Proof: `tests/test_phoenix_mission_006_evidence_quality_signals.py::
test_reklasifikuj_skips_charge_on_genuine_failure` + 3 companion tests.

**LIVINGSYS-DEBT-048 — FIXED** (Program Phoenix, Mission 001, 2026-08-07). Added
`.eq("status", "zakazano")` to `get_matter_intel`'s `rocista` query, matching `dashboard.py`/
`health_index.py`'s own pattern exactly. Proof:
`test_matter_intel_rocista_query_filters_zakazano_status`. Full report:
`docs/phoenix/mission-001/`.

**LIVINGSYS-DEBT-047 — FIXED** (Program Phoenix, Mission 009, 2026-08-07). Took the disclosure
path named as the plausible quick win: each `argumenti_analiza` item now carries
`"rag_grounded": bool`, tracked from which of the first 5 arguments' retrieval calls actually
returned decision matches (text-matched, fails safe to `False`). Frontend shows a ⚠ note under
any argument marked ungrounded. RAG retrieval scope itself is unchanged (still only the first 5
of up to 10 — extending it remains a real latency/cost tradeoff, not attempted here). Proof:
`tests/test_phoenix_mission_009_hallucination_disclosure.py::
test_argument_reputation_arguments_beyond_fifth_never_grounded`. Full report:
`docs/phoenix/mission-009/`.

### Data quality / trust family (not yet fixed)

**LIVINGSYS-DEBT-008 — FIXED** (Program Phoenix, Mission 003, 2026-08-07). All 5 (not 4, per a
recount during reproduction) `.order("vaznost")` call sites in `routers/firm_memory.py` now use
`desc=True`. Proof: `tests/test_phoenix_mission_003_institutional_memory.py::
test_kontekst_za_ai_returns_high_importance_memories_first`. Full report:
`docs/phoenix/mission-003/`.

**LIVINGSYS-DEBT-016 — FIXED** (Program Phoenix, Mission 007, 2026-08-07). Added
`ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions)` to
`CONSEQUENCE_REGISTRY[EventType.NEW_EVIDENCE_REGISTERED]`, reusing the exact same executor
`DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO` already register. Proof:
`tests/test_phoenix_mission_007_case_evolution_chain_integrity.py::
test_new_evidence_registered_now_includes_refresh_case_actions`. Full report:
`docs/phoenix/mission-007/`.

**LIVINGSYS-DEBT-017 — FIXED** (Program Phoenix, Mission 003, 2026-08-07). Added a
`PROBABILITY` `ConceptOwnership` entry to `shared/semantic_registry.py`, mirroring
`CONFIDENCE`'s multi-owner shape and naming all known generators including the unfixed
`strategy_simulator.py` violator. Proof: `test_semantic_registry_has_probability_concept`.

**LIVINGSYS-DEBT-020 (High)** — zero duplicate-content detection on Pipeline A's main document
upload endpoint (`api.py`), unlike Smart Intake's own content-hash dedup. Needs a product decision
(silently skip vs. surface "this looks like a duplicate, upload anyway?") before a mechanical fix
— not purely technical.

**LIVINGSYS-DEBT-021 (High)** — unvalidated GPT chronology extraction feeds directly into the
urgent-deadline notification system with no human-review gate, and a single malformed date drops
an entire extraction batch silently. Fixing means either per-row insert (not bulk, so one bad row
doesn't kill the batch) or a validation pass before insert — both plausible, bounded fixes for a
future mission.

**LIVINGSYS-DEBT-022 — PARTIALLY FIXED** (Program Phoenix, Mission 006, 2026-08-07). The
"confidence gate" itself is closed: `_CLASSIFY_SYSTEM` now asks for `pouzdanost`
(`"visoka"|"srednja"|"niska"`), enum-guarded fail-safe to `"niska"`, persisted into the
existing `ai_tags` column. Proof:
`test_klasifikuj_dokument_enum_guards_unrecognized_pouzdanost`. The review-queue UX (an
accept/reject workflow for low-confidence results, mirroring Smart Intake's own) remains a
SEPARATE, unattempted product decision — this fix makes the confidence signal exist and be
trustworthy, not what a lawyer sees/does with a low-confidence result, which was never in this
mission's minimum-risk scope.

**LIVINGSYS-DEBT-055 — FIXED** (Program Phoenix, Mission 003, 2026-08-07). The except block in
`services/risk_engine.py`'s hearing-date loop now logs a warning (hearing id + malformed
`datum`) before continuing — behavior (silent exclusion) explicitly unchanged, only visibility
added. Proof: `test_risk_engine_logs_malformed_hearing_date`.

**LIVINGSYS-DEBT-050 — FIXED** (Program Phoenix, Mission 008, 2026-08-07). `notif_load()` now
merges the server's own `procitano` field into `_notifRead` on every load (additive-only, never
un-reads a locally-known-read id), so read-state reconciles across devices instead of staying
`localStorage`-only. No migration, no new backend surface. Proof:
`tests/test_phoenix_mission_008_notification_timeline_calendar_consistency.py::
test_notif_load_merges_server_procitano_into_local_read_set`. Full report:
`docs/phoenix/mission-008/`.

**LIVINGSYS-DEBT-051 — FIXED** (Program Phoenix, Mission 008, 2026-08-07).
`intelligence_timeline.py`'s step 7 now skips the synthesized "Predmet zatvoren" entry when
step 4's hronologija scan already found a matching row (reuses `hron_r.data`, no 2nd query);
the defensive fallback for closure paths that don't write a hronologija row is preserved. Proof:
`tests/test_phoenix_mission_008_notification_timeline_calendar_consistency.py::
test_intelligence_timeline_skips_synthesized_closure_when_hronologija_already_has_one`.

**LIVINGSYS-DEBT-052 — FIXED** (Program Phoenix, Mission 003, 2026-08-07).
`routers/memory_graph.py` now imports `shared/kancelarija_utils.py::get_kancelarija_id`
(aliased `_get_firma_id`, all 4 call sites unchanged); the local duplicate is removed. Proof:
`test_memory_graph_reuses_canonical_kancelarija_helper`.

**LIVINGSYS-DEBT-053 — FIXED** (Program Phoenix, Mission 008, 2026-08-07). Added a `napomena`
bucket to `_klasifikuj_dogadjaj`, matched by the 3 known narrative-source prefixes ("Predmet
zatvoren", "Follow-up ročište", "Ugovor o zastupanju zaključen") — bounded prefix match, a
genuine unmatched deadline text still safely defaults to `rok_dokument`. Wired through
`kalendar.py`'s emoji logic and `vindex.js`'s list/grid/day-detail renderers plus a new
`.kal-ev-napomena` CSS rule. Proof:
`tests/test_phoenix_mission_008_notification_timeline_calendar_consistency.py::
test_klasifikuj_dogadjaj_case_closure_is_napomena` + 2 companion tests. Full report:
`docs/phoenix/mission-008/`.

**LIVINGSYS-DEBT-054 (Medium)** — `faktura_create` never validates `predmet_id` matches the
billed entries' actual case — any of a user's own entries can be invoiced under an arbitrary case
ID, silently corrupting per-case reporting (not the invoice amount itself).

**LIVINGSYS-DEBT-023 (Low)** — no OCR quality/confidence signal (garbled-but-nonempty scans are
indistinguishable from clean extractions). Would need real work with `pytesseract`'s
`image_to_data` confidence output — a new capability, not a fix.

### Reachability / product-scope family (real, but currently zero live user impact)

**LIVINGSYS-DEBT-049 (High, product not correctness)** — Memory Graph + Firm Memory's entire
CRUD/query surface (judge profiles, client profiles, partner profiles, graph queries/
recommendations) has zero UI entry points. Real, substantial engineering investment with no
current lawyer-facing risk since it's unreachable — a product/roadmap decision (build the UI, or
formally retire the backend), not a bug fix.

**LIVINGSYS-DEBT-005 (High)** — Service Worker's `controllerchange` handler force-reloads the
page on every deploy with zero check for in-progress form state (Intake Wizard, drafting) and no
`beforeunload` warning anywhere in the 23,000-line frontend. A real fix needs a firm-wide
autosave/state-persistence architecture decision (what gets persisted, to `localStorage` or a
draft-recovery endpoint, and for how long) — explicitly the kind of new-system design this
mission's own rules say not to invent blind under a "minimum-risk fix" mandate.

### Infra/reliability family (not yet fixed)

**LIVINGSYS-DEBT-040 (Medium)** — Dashboard/Workspace Supabase calls have no per-call timeout
(bounded by the client library's own ~120s default, not infinite, but no fast-fail). Would need
`asyncio.wait_for` wrapping across the highest-traffic endpoints' 10+ parallel queries each —
bounded but broad, deferred.

**LIVINGSYS-DEBT-041 (Low-Medium)** — no upload progress indicator or explicit app-level timeout
for slow/large file uploads. A frontend UX addition (`XMLHttpRequest.upload.onprogress` or
similar), not a correctness fix.

### Consolidated low-severity items

**LIVINGSYS-DEBT-018 through -019, -024 through -026, -028 through -032, -039, -056 through -063**
— ~20 additional LOW/cosmetic findings (notification frontend field gaps, CIO empty-state
wording, Digital Twin fail-soft cap bypass, disclosure-label inconsistency across AI surfaces,
Digital Twin's dead `GET /api/twin/{id}` endpoint, Case Commander's computed-but-unenforced
`hard_flags` — moot while that router itself has zero live callers per prior missions' own
confirmed finding, `billing.py::profitabilnost.py`'s RLS-reliant tenant filter needing live-DB
verification, per-source silent-failure gaps in Health Index's weak-signals block, Dashboard's
historical risk-diff coverage at scale, drafting's missing server-side cooldown). Full individual
detail in each Wave's own report under `docs/living_system/`; not itemized further here to keep
this register's own length proportionate to severity — none are correctness-critical, all are
real and traceable to their source report.

**Severity summary across all 63 Living System items**: 2 CRITICAL (`-003`, `-013`), 15 High
(`-002, -005 through -012, -014 through -017, -020 through -022, -036, -038, -042, -047 through
-049`), remainder Medium/Low. Zero silently dropped — every item traces to a specific reproduced
finding in one of the 14 source reports under `docs/living_system/`.

**Program Phoenix progress** (autonomous elimination program, began 2026-08-07 immediately after
this ledger was written — see `docs/phoenix/` for full per-mission deliverables and
`.vindex_ai_team/MISSION_BOARD.md` for the running program log): Mission 001 closed
`LIVINGSYS-DEBT-037` and `-048` fully, and made partial (visibility-only, not data-hygiene)
progress on `-036` and `-038`. This section's individual item entries above are updated in place
as each is closed — check the item's own entry for current status rather than this summary line,
which is not re-counted after every mission.
