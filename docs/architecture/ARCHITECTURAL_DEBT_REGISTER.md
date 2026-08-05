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
