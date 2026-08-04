# Architecture Review — Program Alpha (Masterprompt 001, "Eliminate Entire Classes of Defects")

**Agent**: 17 — Architecture Review Agent (`.vindex_ai_team/agents/17_architecture_review_agent.md`)
**Date**: 2026-08-04
**Invocation**: fresh subagent, `general-purpose`/`opus`, per `AI_GOVERNANCE_ARCHITECTURE.md` rule 1 — the
change under review was produced by the currently-active session, so a fork was not permitted.
**Format**: 7 fields, per `.vindex_ai_team/AGENT_COMMUNICATION_PROTOCOL.md`
**Gate vocabulary**: `APPROVED` / `APPROVED WITH CONDITIONS` / `BLOCKED`, per `QUALITY_GATES.md` row 17.

---

## 1. Scope

### Reviewed (read directly in the working tree, not taken from the mission brief on faith)

Full uncommitted diff of the working tree (`git diff` + untracked additions), 27 modified/deleted files
and 2 new files:

| Item | Files read |
|---|---|
| 1 — correlation-id minting | `routers/case_dna.py:525-536` |
| 2 — dead `_al.log` removal | `routers/gdpr.py` (diff) |
| 3 — embedding model constant | `routers/auto_discovery.py`, `batch_ingest.py`, `knowledge_base.py`, `law_upload.py`, `proof.py`; `app/services/retrieve.py:69`; plus a repo-wide sweep for residual authors |
| 4 — Court Predictor `nivo`/`procenat` | `routers/court_predictor.py:1025-1262`; `static/vindex.js:3536-3556` (the consumer) |
| 5 — `response_audit` retirement | deleted `app/services/audit_log.py`, `test_audit_b1.py`; `routers/drafting.py`, `api.py`, `services/retention_service.py`, `tests/test_retention_service.py`, `tests/test_credits_supabase.py`, `tests/test_doc_pitanje_api.py`, `tests/test_uploaded_doc_api.py` |
| 6 — canonical proactive alerts | new `shared/proactive_alerts.py` (full); all 12 migrated call sites in `services/event_bus.py`, `routers/case_dna.py`, `zakon_monitoring.py`, `morning_briefing.py`, `smart_intake.py`, `workflow.py`, `zadaci.py`; `shared/audit_immutable.py` allowlist diff |
| 7/8 — correlation-ID middleware | `api.py:981-1010`, `api.py:3094-3115`, `api.py:3155-3165`; `shared/deps.py:300-315`; `shared/ai_provenance.py:1-130` |

Governance/design artifacts: `docs/architecture/CANONICAL_MIGRATION_PLAN.md`,
`DUPLICATE_DECISION_REPORT.md`, `SOURCE_OF_TRUTH_REGISTRY.md`, `SYSTEM_HARDENING_REPORT.md`,
`VINDEX_CORE_CONSOLIDATION.md`.

### Independently executed (not asserted)

- Full pytest suite: `python -m pytest tests -q` → **2420 passed, 1 skipped, 0 failed** (314.9s).
- New test file `tests/test_program_alpha_canonical_architecture.py` + the two tests the mission
  rewrote → 37 passed.
- **Empirical probe of item 8's load-bearing assumption** (a `contextvars` mutation made inside
  `@app.middleware("http")` must propagate into the route's dependency and handler): built a minimal
  FastAPI app using the real `shared/ai_provenance.py` and the mission's exact middleware body, ran it
  against installed Starlette 1.3.1, both with an incoming `X-Correlation-ID` and without. Header,
  dependency-visible id, and handler-visible id matched in both cases. **Item 8's mechanism is real, not
  assumed.**

### Explicitly NOT reviewed

- **Production Reality Gate** — no assertion here about live production behavior; all verification is
  code-and-test-level, per `feedback_engineering_rigor_methodology`'s own rule that this is not this
  agent's call.
- **Security/privacy consequences of retiring `response_audit`** — whether losing a (write-only) audit
  surface has any compliance implication is Agent 05/27's domain, deliberately not adjudicated here.
- **Reliability semantics** of the new nested retry (Finding A-4) are flagged and routed, not
  adjudicated — Agent 20's charter.
- `migrations/smart_contract_analyses.sql` is modified in the working tree but pre-dates this mission
  (present in the session-start snapshot); not attributed to Program Alpha and not reviewed.
- The 7 Tier 2/3 deferrals were not re-adjudicated — only whether their deferral is honestly recorded.

---

## 2. Findings

### Verified as genuinely single-owner (no finding — recorded so the Director sees what was checked)

- **P-1 — Court Predictor confidence (item 4) is now genuinely one author.** `_procenat_iz_score()` is
  the sole producer of `procenat`, derived from the same `score` `_calc_confidence_nivo()` returns; a
  repo-wide grep confirms `_calc_confidence_nivo` has exactly one caller and no second percentage author
  exists. The GPT prompt now explicitly forbids emitting a number. `nivo`/`procenat` contradiction is
  structurally impossible.
- **P-2 — The `procenat` field's *meaning* changed, and the change is a correction, not a drift.** The
  old prompt asked the LLM for *"šansu uspeha"* (chance of success); the new value is *confidence in the
  analysis*, derived from evidence volume. I checked the actual consumer: `static/vindex.js:3547` renders
  it beside the label `"<nivo> POUZDANOST"` — i.e. the UI has always framed this as confidence, and the
  old LLM number was the mislabeled one. This is the one place a "same field name, silently diverged
  meaning" defect (this agent's charter's `ccc.py::health_score` precedent) could have been introduced;
  it was not.
- **P-3 — `shared/proactive_alerts.py` does not duplicate `shared/audit_immutable.py`.** It *calls* it
  (`shared/proactive_alerts.py:80-85`). Dependency direction is correct and acyclic
  (`event_bus` → `proactive_alerts` → `audit_immutable` → `ai_provenance`); no cycle, no new inappropriate
  coupling, no parallel audit mechanism started.
- **P-4 — Item 5 leaves no orphan.** `app/services/audit_log.py` deleted outright; a repo-wide sweep
  finds zero remaining `from app.services import audit_log`, zero `log_response`, zero
  `.table("response_audit")` in non-test code. `tests/test_retention_service.py:297-314` was inverted into
  a *guard against reintroduction* — the right shape for a retirement.
- **P-5 — Item 8 is mechanically real.** Verified empirically (see Scope). The old `_correlation_id_var`
  is fully removed, not merely unused, and a test asserts its absence (`test_program_alpha_...py:82-88`).
- **P-6 — The Event Bus `if not _ok: raise RuntimeError(...)` pattern is not dead code.** All three
  handlers' `except Exception` blocks re-raise (`services/event_bus.py:107-111, 163-167, 208-212`), so the
  outer `dispatch_pending_events()` retry genuinely sees the failure. This was checked because a
  swallowing `except` would have made the whole design intent inert.
- **P-7 — The SMTP pullback (item 7) is documented, not merely asserted.**
  `CANONICAL_MIGRATION_PLAN.md:93-115` names each of the 4 divergent call sites and its specific
  non-duplicate requirement, and the plan's header (lines 19-27) frames the pullback as the "revert if it
  gets more complicated" rule working. It even narrows the *real* residual duplicate (SMTP
  connection/auth boilerplate, distinct from message construction). This is the honest shape.

### Findings requiring action

- **A-1 (Medium) — `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` does not exist, but three
  artifacts cite it as the authoritative home for this mission's deferred work.** It is named as: (a) the
  tracked home of `ALPHA-001`; (b) the location of the empirical reproduction of the `asyncio.to_thread`
  contextvar-isolation behavior; (c) the register where all **7 deferred Tier 2/3 findings** are "tracked
  with a fresh ID — deferred, not dropped." None of that exists. On the brief's direct question — is the
  `_require_auth` limitation glossed over? — **no, the prose disclosure is genuinely thorough and honest**
  (a dedicated, named section in `SYSTEM_HARDENING_REPORT.md` and a 12-line code comment that states the
  limitation at the exact call site). The defect is narrower but real: the *tracked* artifact the
  disclosure hands off to is missing, so a debt item with an assigned ID has no record, and the
  "deferred, not dropped" claim covering 7 further findings is currently unsupported by any artifact.
  This falls squarely under this agent's Responsibilities bullet on technical debt left behind
  unregistered, and under `OPERATING_PROTOCOL.md`'s "a phase's artifact is the only proof that phase
  happened."

- **A-2 (Medium) — The embedding-model concept is *not* single-owner after this change, and
  `SYSTEM_HARDENING_REPORT.md` claims it is.** The 5 targeted routers now correctly import
  `app/services/retrieve.py::EMBEDDING_MODEL`. But live runtime code still contains **three independent
  private definitions and three inline literals** of the same value. The most significant is
  `uploaded_doc/ingest.py:29-36`, which hardcodes both the model **and** `dimensions=3072` and is *the*
  uploaded-document ingestion path — reached from `api.py:4077`, `routers/dokument.py:176`,
  `routers/drafting.py:260`, `routers/smart_intake.py:591`. The diagnostic's framing ("5 ingestion
  routers") missed a genuine sixth ingestion author. This is a **pre-existing gap, not a regression
  introduced by this mission** — but the hardening report's row asserts a future model change "now
  updates all 6 call sites atomically," which is not true, and `SOURCE_OF_TRUTH_REGISTRY.md:23` still
  classifies this concept as `Latent` with the same incomplete 5-site scope. A governance document
  overstating a canonicalization is the precise failure mode this board exists to catch.

- **A-3 (Low) — `routers/case_dna.py:527-536`'s fallback is now non-functional for the case it exists to
  handle.** The `except Exception:` branch re-imports the very module (`shared.ai_provenance`) whose
  import could have raised in the `try`. If the `ImportError` path ever fires, the fallback raises too;
  the previous `str(uuid.uuid4())` fallback was import-free. The architectural direction (one minting
  function) is correct and should stand — the defect is that the guard is now decorative.

- **A-4 (Low, routed to Agent 20 — Reliability & Chaos) — retry policy for one operation now has two
  owners.** `create_proactive_alert()` retries 3× internally with backoff
  (`shared/proactive_alerts.py:32,57-74`); the three Event Bus handlers then raise on exhaustion so
  `dispatch_pending_events()`'s outer retry/dead-letter retries the whole handler. Net effect during a
  Supabase outage: 3×N attempts and **one `proactive_alert_insert_failed` audit row per outer attempt**
  (audit amplification exactly when the audit trail matters most). This is not a duplicate
  *implementation* — the inner one is canonical and there is only one — so it is not a source-of-truth
  violation and this agent does not block on it. But the layering deserves an explicit owner decision
  rather than being an emergent property of two independently-correct fixes meeting.

- **A-5 (Low) — documentation drift within the mission's own artifacts.** `CANONICAL_MIGRATION_PLAN.md:41`
  says "migrate all 11 call sites" while the same document's item-6 note and
  `shared/proactive_alerts.py`'s docstring both say 12; the actual count is 12 (3+3+2+1+1+1+1). Separately,
  the plan instructed "keep the module for `_al.log` callers if any remain"; the module was deleted
  outright. The deletion is *correct* (verified zero remaining callers) but the plan text was never
  reconciled to the decision actually taken.

- **A-6 (Low) — `predictor_analize` now stores two different meanings under one format.** Rows written
  before today with `tip_analize="confidence_check"` carry an LLM-estimated *success chance* in the
  `PROCENAT: X%` token of the `analiza` string; rows written from now on carry a deterministic
  *confidence* percentage in the identical token (`routers/court_predictor.py:1234`). The only reader
  found is a history/display query (`court_predictor.py:1286`), so present-day impact is display-only —
  but any future analytics over that column silently mixes two definitions. Worth one sentence in the
  debt register alongside A-1, not a code change.

---

## 3. Evidence

| Finding | Evidence |
|---|---|
| P-1 | `routers/court_predictor.py:1028-1041` (`_procenat_iz_score`), `:1043-1097` (`_calc_confidence_nivo` returns `score`), `:1182-1185`, `:1187-1201` (prompt forbids a number); repo-wide grep: `_calc_confidence_nivo` has exactly 1 non-test caller |
| P-2 | Old prompt (removed, `git diff routers/court_predictor.py`): `"Proceni šansu uspeha za sledeći predmet"`; consumer label `static/vindex.js:3547` renders `d.procenat` beside `"' + d.nivo_pouzdanosti + ' POUZDANOST"` |
| P-3 | `shared/proactive_alerts.py:80-85` imports and calls `shared.audit_immutable.log_action`; no reverse import exists |
| P-4 | `git status`: `D app/services/audit_log.py`, `D test_audit_b1.py`; repo-wide grep for `log_response` / `from app.services import audit_log` / `.table("response_audit")` → 0 non-test hits; `tests/test_retention_service.py:297-314` (assertion inverted to `hits == []`) |
| P-5 | Empirical probe (scratchpad `ctxvar_probe.py`, Starlette 1.3.1): header/dependency/handler ids matched in both incoming-header and minted cases; `api.py:981-1010`; `shared/deps.py:305-313`; `tests/test_program_alpha_canonical_architecture.py:82-88` |
| P-6 | `services/event_bus.py:107-111`, `:163-167`, `:208-212` — each `except Exception as exc:` ends in bare `raise` |
| P-7 | `docs/architecture/CANONICAL_MIGRATION_PLAN.md:19-27` and `:93-115` |
| **A-1** | `ls docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md` → No such file; `find . -iname "*DEBT_REGISTER*"` → 0 results. Citations: `docs/architecture/SYSTEM_HARDENING_REPORT.md:115`; `docs/architecture/CANONICAL_MIGRATION_PLAN.md:60` ("tracked with a fresh ID in `ARCHITECTURAL_DEBT_REGISTER.md` — deferred, not dropped"); `api.py:3097-3098` (code comment: "see ARCHITECTURAL_DEBT_REGISTER.md"). Honest-disclosure counter-evidence: `SYSTEM_HARDENING_REPORT.md:109-121` ("The one honest exception — found, not fixed, explicitly flagged"); `api.py:3096-3107` |
| **A-2** | Residual runtime authors: `uploaded_doc/ingest.py:29-36`; `drafting/playbook.py:15`; `interni_stavovi.py:15`; `api.py:2054`; `api.py:2126`. Canonical: `app/services/retrieve.py:69`. Ingestion-path callers of the missed site: `api.py:4077,4169`, `routers/dokument.py:176,241`, `routers/drafting.py:260,284`, `routers/smart_intake.py:591`. Overclaim: `SYSTEM_HARDENING_REPORT.md`, "Embedding model constant" row ("updates all 6 call sites atomically"); stale scope: `SOURCE_OF_TRUTH_REGISTRY.md:23` |
| **A-3** | `routers/case_dna.py:526-536` — `except Exception:` body begins `from shared.ai_provenance import new_correlation_id` |
| **A-4** | `shared/proactive_alerts.py:32,57-74,76-86`; `services/event_bus.py:90-111,148-167,196-212` |
| **A-5** | `docs/architecture/CANONICAL_MIGRATION_PLAN.md:41` ("11 call sites") vs. `:110-118` and `shared/proactive_alerts.py:6-9` ("12"); `CANONICAL_MIGRATION_PLAN.md:74-79` ("keep the module…") vs. `git status: D app/services/audit_log.py` |
| **A-6** | `routers/court_predictor.py:1234` (write), `:1286` (only reader) |
| Test evidence | `python -m pytest tests -q` → `2420 passed, 1 skipped in 314.90s` |

---

## 4. Risk Classification

| ID | Severity | Rationale |
|---|---|---|
| A-1 | **Medium** | No runtime impact. Governance integrity: a mission whose stated discipline is "deferred, not dropped" currently has 8 deferred items (ALPHA-001 + 7 Tier 2/3) with no tracked home, and three artifacts — one of them production source — cite a file that does not exist. |
| A-2 | **Medium** | No behavior change today (all values identical). Risk is the exact latent shape the mission set out to eliminate: a future embedding-model change updates 5 of ≥10 runtime authors, silently corrupting retrieval for the uploaded-document path. Aggravated, not caused, by a governance document asserting the gap is closed. |
| A-3 | **Low** | Only fires on an `ImportError` of a core shared module — a condition under which the process is already broken. |
| A-4 | **Low** | Degrades an outage, does not cause one. Correctness is unaffected; only attempt count and audit-row volume. |
| A-5 | **Low** | Documentation-only. |
| A-6 | **Low** | Display-only today; becomes Medium only if `predictor_analize` is ever used analytically. |

**No Critical or High finding.** Specifically: **no new duplicate source of truth and no new parallel
system were introduced by this mission's own changes** — the question this agent's veto exists to answer.
Every consolidation examined (items 1, 4, 5, 6, 8) genuinely reduced the authoritative-source count and
none created a second mechanism under a new or identical name.

---

## 5. Recommendation

### `APPROVED WITH CONDITIONS`

Per `QUALITY_GATES.md` rule 1, this is **not a pass** — it is contingent on the two named, checkable
conditions below being verified before the Director's final recommendation, not assumed satisfied.

**Condition 1 (closes A-1)** — either create `docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`
containing `ALPHA-001` (with the empirical `asyncio.to_thread` contextvar reproduction the hardening
report says lives there), the 7 deferred Tier 2/3 items with IDs, and A-6; **or** remove all three
citations to it (`SYSTEM_HARDENING_REPORT.md:115`, `CANONICAL_MIGRATION_PLAN.md:60`, `api.py:3097-3098`)
and relocate the content. Creating the register is strongly preferred — the disclosure prose is already
written and honest; only the tracked artifact is missing. Verifiable by `ls`.

**Condition 2 (closes A-2)** — correct `SYSTEM_HARDENING_REPORT.md`'s "all 6 call sites atomically"
claim to the true scope, and register the residual runtime authors (`uploaded_doc/ingest.py` first —
it is a genuine ingestion path the diagnostic missed — plus `drafting/playbook.py:15`,
`interni_stavovi.py:15`, `api.py:2054`, `api.py:2126`) as a tracked debt item. **A code fix is not
required for this gate**; an accurate claim and a tracked item are. Verifiable by re-reading the row and
the register.

**Not conditions** (advisory, non-blocking): A-3 (one-line fix), A-4 (route to Agent 20 for an explicit
retry-ownership decision), A-5 (reconcile the plan's own counts).

**Why not `BLOCKED`**: this agent's veto is reserved for a genuine architectural regression — a *new*
duplicate source of truth or a *new* parallel system. None exists. A-2 is a pre-existing gap the mission
narrowed but did not close; A-1 is a missing artifact, not a code defect. Blocking on either would be the
kind of judgment the charter's Forbidden section rules out.

**Why not `APPROVED`**: a governance artifact asserting a canonicalization is complete when it demonstrably
is not (A-2), and a register cited by production source code that does not exist (A-1), are both
evidenced defects in this mission's own deliverables — not stylistic preferences.

---

## 6. Confidence

| Claim | Confidence | Basis |
|---|---|---|
| No new duplicate source of truth introduced (the veto question) | **High** | Every one of the 6 targeted concepts read directly at every call site; full test suite green; item 8's mechanism verified empirically rather than reasoned about |
| A-1 (register missing) | **High** | Filesystem-verified in two ways (`ls`, repo-wide `find`); the three citations quoted verbatim |
| A-2 (embedding model not single-owner) | **High** | Repo-wide grep enumerated every author; `uploaded_doc/ingest.py`'s callers traced to 4 live routers |
| P-2 (meaning change is a correction, not drift) | **Medium-High** | Verified against the one frontend consumer found. I did not exhaustively enumerate every possible API consumer (mobile/integrations, if any exist) |
| A-4 (retry amplification) | **Medium** | Read from code; not exercised under a simulated outage. Chaos verification is Agent 20's, not this pass's |
| Items 1, 2, 5 (low-stakes substitutions/deletions) | **High** | Small, fully-read diffs with grep-confirmed zero residue |
| Anything about production behavior | **N/A — explicitly not claimed** | Out of charter (`Production Reality Gate`) |

---

## 7. Open Questions

1. **Was `ARCHITECTURAL_DEBT_REGISTER.md` intended to be created this mission and simply missed, or is
   it a planned future artifact that was cited prematurely?** The distinction matters for whether
   Condition 1 is a 10-minute omission or a scope decision. Cannot be resolved from the evidence
   available.
2. **Who owns retry policy for a canonical write helper that is called from inside a retrying
   dispatcher?** (A-4.) This is a design decision, not a defect — needs Agent 20 and/or Agent 01, not
   this agent. Filed rather than silently dropped.
3. **Does `drafting/playbook.py` / `interni_stavovi.py` / `uploaded_doc/ingest.py` write to the same
   Pinecone index as `retrieve.py` reads from?** If yes, A-2's future-risk severity is higher than
   Medium (a model change would corrupt retrieval, not merely diverge). I did not trace index/namespace
   ownership for each — out of this pass's time box, and adjacent to the deferred "Pinecone namespace
   registry" Tier 2 item.
4. **Should the `response_audit` table now be dropped, and does its retirement have any compliance
   consequence?** Explicitly out of this agent's charter (Database Architect 08 / Compliance 27).
   Flagged so it is not lost between charters.
5. **`shared/proactive_alerts.py:81` uses fire-and-forget `asyncio.create_task(...)` without retaining a
   reference to the task.** Inherited unchanged from Project Phoenix's proven pattern, so not a
   regression and not raised as a finding — but generalizing it from one call site to twelve multiplies
   whatever exposure it carries (task GC, loss on loop shutdown). Reliability's call, not architecture's.

---

**Gate state: `APPROVED WITH CONDITIONS`**
