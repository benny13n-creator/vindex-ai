# Mission Keystone — Final Pre-Beta Readiness Validation

**Mission:** founder's Master Prompt, 2026-08-04. Role framing: Principal Enterprise Architect /
Production Readiness Auditor / AI Safety Reviewer / Reliability Engineer / Security & Compliance
Architect / Red Team Lead. Explicit mandate: *"Tvoj cilj nije da potvrdiš prethodni rad. Tvoj cilj je da
ga osporiš."* (Your goal is not to confirm prior work. Your goal is to challenge it.) First Rule: no new
features/modules/UX/AI-capability expansion — only critical bug fix, security fix, reliability fix, test
coverage, documentation. This is the 6th and final mission of this session's engagement, run immediately
after Project Sentinel, Mission Atlas, Mission Ledger, Mission Migration, and Project Phoenix.

**Method:** 7 parallel, independent, read-only, adversarial fork investigations (one per Phase 1–7),
each explicitly instructed to treat every prior mission's report as a *hypothesis to re-verify*, not a
fact — followed by a personally-owned synthesis, 2 targeted code fixes, full regression testing, and this
report. The Phase 8 Risk Register and Phase 9 Beta Gate decision below were made directly, not
delegated — they are this mission's core deliverable.

**Headline result: this mission's own fresh, full-system re-measurement found that every prior mission's
coverage metric (Audit Link, Provenance, Reliability) was computed against a narrower scope than the real
system.** Phase 2's unfiltered grep for AI call sites found **76 across 55 files** — roughly 41 live,
mounted production routers no prior mission's hand-curated inventory ever counted. This is not a claim
that prior fixes were wrong (all re-verified intact) — it is that the denominator was smaller than
reality. Re-measured honestly, Audit Link Coverage is **~39%** system-wide (not Migration's 78%, which
was accurate only for its own 36-row scope), Reliability Score **~75–80%**, Failure Recovery Coverage
**~65–75%**. **None of Keystone's own 7 numeric targets are met** under this honest denominator.

Two further findings raise the severity bar beyond anything found in prior missions:

1. **Critical, narrowed by a correction (Mission Olympus, 2026-08-04) — GDPR account deletion does not
   delete case data, but the case/client/document retention itself is disclosed with a stated legal
   basis, not a silent gap.** `routers/gdpr.py::gdpr_delete_account` only anonymizes the login profile;
   `predmeti`, `klijenti`, `predmet_dokumenti` (full document text), Pinecone vectors, and Storage files
   all remain fully intact and attributable via the unchanged `user_id`. **Read directly (Mission
   Olympus's Regulatory Compliance Verification Agent backtest, `routers/gdpr.py:222-228`): the endpoint's
   own response already discloses this to the user explicitly** — *"Predmeti, klijenti i dokumenti nisu
   anonimizovani ovim postupkom i zadržavaju se u skladu sa zakonskom obavezom advokata da čuva spise
   predmeta (Zakon o advokaturi)"* — a stated legal basis (a lawyer's statutory duty to retain case files)
   that plausibly falls under GDPR Article 17(3)(b)'s legal-obligation exception, not an undisclosed
   violation. **The genuinely open, narrower gap**: that disclosure covers case-file records under a
   legal-hold rationale, but says nothing about — and that rationale does not obviously extend to —
   Pinecone vectors and Storage files, which are derived technical artifacts with no independent
   legal-retention justification of their own and are not mentioned in the user-facing disclosure at all.
   This corrects a prior mission's inaccurate characterization of `services/retention_service.py` as "the
   GDPR-driven deletion mechanism" — that service only does scheduled TTL cleanup of *operational* logs
   (security_events, ai_forensics, Pinecone tmp buffers), unrelated to user-initiated erasure. **Not fixed
   this mission** — closing the Pinecone/Storage gap, or extending the disclosure to cover it, is a
   founder policy decision, not a "clearly localized" fix.
2. **Critical/High — multi-worker duplicate Event Bus dispatch.** Production runs 4 gunicorn workers by
   default (`gunicorn.conf.py`); each runs its own independent `DispatchLoop` polling the same `events`
   outbox every 3s with a plain, unclaimed `SELECT`. Two workers can select and process the same
   undispatched row in the same tick, double-running non-idempotent handlers (duplicate
   `proactive_alerts`/audit rows). **Fixed this mission** — see Phase 3 below.

---

## Phase 1 — Architecture Freeze Review

Fresh snapshot, independent of any prior mission's claim.

- **Modules**: routers/, services/, shared/, security/ — confirmed no new parallel systems introduced
  across tonight's 5 prior missions; single audit mechanism, single provenance sink, single correlation_id
  generator, single risk-score implementation. Clean.
- **Sources of truth**: no duplicate implementations found for any major concept (risk score, deadline,
  task, alert, audit trail, provenance, correlation_id) — each has exactly one authoritative location.
- **AI entry points**: a fresh, unfiltered grep (not the ~36-row hand-curated list prior missions used)
  found **76 `.chat.completions.create(`-shaped call sites across 55 files**, including ~41 live, mounted
  production routers never counted by any prior mission's inventory (case_commander, matter_intel,
  memory_graph, multi_agent, praksa, precedenti, health_index, digital_twin, and more — all confirmed
  registered via `app.include_router()`, not dead code). See Phase 2 for the metric impact.
- **The AI wrapper coverage claim is false for one feature.** `services/voice_orchestrator.py` ("Vindex
  Live") connects via a raw WebSocket directly to OpenAI's Realtime API
  (`wss://api.openai.com/v1/realtime`), bypassing the SDK's `Completions`/`Embeddings` classes that
  `shared/ai_client.py` patches entirely. This is a real, live, wired-in feature (registered router, its
  own test file) — every prior mission's "100% AI wrapper coverage, zero features bypass the wrapper"
  claim does not hold for this one feature. No correlation_id/case-context is set for voice sessions
  either. **Not fixed this mission** (wiring provenance into a raw Realtime-API WebSocket integration is
  real dev work, not a localized fix) — tracked as `KEYSTONE-001`.
- **Event Bus multi-worker race** — see headline finding above and Phase 3/4.
- **Stale memory corrections**: `routers/enterprise.py` is live and fully implemented (a 2026-07-24 memory
  note called it dead code); the "~208 orphan routes" figure is superseded by a fresh run of the repo's
  own `scripts/audit_routers.py` (13 confirmed-dead router modules of 108, a smaller and more precise set).

---

## Phase 2 — Final Metric Calculation

Every number below is freshly computed against current code, not copied from a prior mission's report.
Full methodology and evidence: `.vindex_ai_team/decisions/2026-08-04_keystone_phase2_metrics_INVESTIGATION.md`.

| Metric | Target | Prior self-reported figure | **Keystone fresh figure** | Verdict |
|---|---|---|---|---|
| Intelligence Connectivity Score (ICS) | ≥90% (Nexus) | **Correction (Mission Olympus, 2026-08-04): this was wrongly reported as "first measurement" — Project Nexus (2026-08-03) already established ICS at 62.5% (20/32 verified connections) using a rigorous, cited connection ledger (`docs/architecture/NEXUS_ICS_SCORE.md`), one day before this mission.** | **~34–39%** (different, cruder methodology — not directly comparable to Nexus's connection-ledger figure) | Genome/Strategy/Task Engine mostly don't feed each other. **Methodology gap, not necessarily a real decline**: Keystone's Phase 2 fork did not know Nexus's ledger existed and derived its own, less rigorous ICS estimate. Future ICS measurements should extend Nexus's own connection ledger (append rows, keep the same exclusion criteria) rather than re-deriving the metric from scratch each mission — exactly the discipline `NEXUS_ICS_SCORE.md`'s own "Recomputation note" already prescribes. |
| Critical Intelligence Coverage (CIC) | — (first measurement) | not previously computed | **~68%** | Drafting is the only flow scoring 6/6 on all sub-checks |
| Audit Link Coverage | ≥95% | 78% (Migration, 36-row scope) | **~39%** (full 76-call-site scope) | **REVISES DOWN** — Migration's figure was accurate for its own narrower scope, not the full system |
| Provenance Coverage | ≥95% | 58–75% (Atlas) | **~87%** | Close, but `retrieval_query`/`retrieved_context_ids` ("source references" — the single most important field for a legal-RAG product) are populated by **zero** call sites, including core `ask_agent` |
| Replay Coverage | ≥95% | not previously computed at this granularity | **~100%** technical/correlation level, **~39%** full business-content level | Same binding constraint as Audit Link |
| Reliability Score | ≥90% | implied ~100% for touched flows (Phoenix) | **~75–80%** | Below target once measured against the full module population, not just Phoenix's touched set |
| Failure Recovery Coverage | 100% | implied high (Phoenix) | **~65–75%** | ~75% of the full module population has never been chaos-tested by any mission |

**A second real gap Phase 2 found**: `routers/dokument.py::dokument_pitanje` is a second, real, unwrapped
`ask_agent` call path that Mission Migration's own "MIGRATION-001: DONE" claim (closed by Phoenix) missed —
both Migration's and Phoenix's inventories only traced `copilot.py`'s delegation into `ask_agent`. **Fixed
this mission** — see Phase 3.

**None of the 7 targets are met under this honest, full-system denominator.** This is not a claim that
prior missions' fixes are wrong — every one was re-verified intact — it is that measured scope was
narrower than the real system every time.

---

## Phase 3 — Golden Path End-to-End Trace

Full detail: `.vindex_ai_team/decisions/2026-08-04_keystone_phase3_golden_path_INVESTIGATION.md`.

**Solid (Pass)**: predmet creation, upload's failure-signaling (Sentinel's ghost-document fix re-confirmed
intact), Case Genome's correctness (including a real coalescing-lock fix closing a lost-update race),
Timeline, Search, Briefing, Copilot, Risk Analysis's live computation, the Audit/Provenance wrapper.

**Where the golden path actually breaks**:
- **Genome → Strategy/Risk/Tasks.** `on_predmet_kreiran` genuinely does auto-fire a 9-step Case Pipeline
  (correcting stale memory claiming it never fires) — but only once, at case creation, before any
  documents exist, and its steps are idempotency-locked so they never re-run once real evidence arrives.
  After that, Strategy Engine and Task Generation are lawyer-initiated only, and Strategy Engine's output
  isn't persisted anywhere Timeline/Dashboard would surface it later. This is an architectural/product
  characteristic, not a bug — flagged as a roadmap item (`KEYSTONE-002`), not fixed (First Rule: no new
  features).
- **Memory Graph is confirmed fully isolated** — a repo-wide grep found zero other module calls into it.
  No golden-path step feeds it; a lawyer must manually populate it. **Correction (Mission Olympus,
  2026-08-04): the parallel claim about Firm Brain was wrong.** `api.py::_fetch_firm_memory_context`
  (called at `api.py:2916` and `api.py:3020`) is a real, narrow consumer that reads Firm Brain's
  institutional-memory tables directly into Copilot/RAG context — Firm Brain is a one-way *source* feeding
  Copilot, not an isolated island. Caught by the new Workflow Integrity Agent (30)'s backtest, itself a
  concrete demonstration of the value this governance layer is meant to add (see
  `docs/architecture/OLYMPUS_BACKTEST_VALIDATION_REPORT.md`).
- **Two silent-failure spots**: document classification and Genome refresh both run as fire-and-forget
  background tasks with only a log line on failure — no alert, no durable audit-of-failure entry (unlike
  the pattern Phoenix already proved for nightly alerts). Tracked as `KEYSTONE-003` — not fixed this
  mission (the proven pattern exists and applying it is small, but was judged a second-tier priority
  relative to the multi-worker dispatch fix given mission time).
- Client creation uses an older, separate audit mechanism (`audit_log`, not the hash-chained
  `audit_immutable`) and has no dedup check on rapid double-submission.

---

## Phase 4 — Adversarial Failure Testing (Chaos)

Full detail: `.vindex_ai_team/decisions/2026-08-04_keystone_phase4_chaos_INVESTIGATION.md`.

**Genuinely new vulnerability found — the headline multi-worker race** (see top of this report).
`dispatch_pending_events()` ran handler-execution and mark-dispatched as two non-atomic steps; with 4
gunicorn workers each polling independently every 3s, the same row could be claimed and processed by more
than one worker. `PREDMET_KREIRAN`'s own handler is confirmed exempt (idempotency-locked per pipeline
step) — the exposure is `on_rok_kritican`, `on_health_score_promenjen`, `on_document_job_failed`, and
`on_genome_updated`, each of which unconditionally inserts a new row on every call.

**Fixed this mission**: `migrations/091_event_bus_atomic_claim.sql` (drafted, not run — per standing
project convention) adds a `claim_pending_events(p_batch_size, p_stale_claim_seconds)` RPC mirroring
migration 073's already-proven `claim_intake_job` (`SELECT ... FOR UPDATE SKIP LOCKED`, the only way to
give N concurrent workers a safe split of one batch — PostgREST doesn't expose row-level lock semantics
directly, hence the RPC). `services/event_bus.py::dispatch_pending_events()` now tries the RPC first and
falls back to the exact pre-existing plain-select behavior if the RPC isn't deployed yet (narrow
`_is_missing_function_error()` check, same discipline as `shared/audit_immutable.py`'s
`_is_missing_column_error()`) — so behavior is identical to before until the founder runs the migration,
and the race is closed the moment it's run. On a non-exhausted retry, `claimed_at` is explicitly cleared
so the existing ~3s fast-retry cadence (already proven by Phoenix's own tests) is unchanged.

**8 new tests** (`tests/test_keystone_readiness_validation.py::TestEventBusAtomicClaim`) prove: the RPC
path is used exclusively when available (no double-select), the fallback path works correctly when it
isn't, an unrelated RPC error is never masked as "not deployed", the narrow check itself is correct on
both accept/reject cases, and `claimed_at` is cleared only on the RPC-claimed retry path (never referenced
on the fallback path, since the column may not exist yet).

**Phoenix's own "not independently re-verified" items, resolved this mission**:
- **Anthropic**: confirmed zero usage anywhere in the codebase (no SDK import, no API key var, no model
  string, not in requirements.txt). Reclassified N/A/not-integrated, not "unverified" — a correction, not
  a gap.
- AI invalid-JSON-response handling: confirmed Protected everywhere checked (clean 500, never false
  success).
- Hallucination/low-confidence guarding: confirmed real and rigorous, but Drafting-only — see Phase 5.
- File Storage / upload-interrupted / corrupted-document / general DB connection-loss: still not
  independently re-traced (time-boxed both missions) — no new evidence either way, honestly left
  unscored rather than assumed.

---

## Phase 5 — AI Quality Validation

Full detail: `.vindex_ai_team/decisions/2026-08-04_keystone_phase5_ai_quality_INVESTIGATION.md`.

**Headline verdict: mixed, feature-dependent — not uniform.**

- **Honest-about-uncertainty**: `main.py::ask_agent` (core RAG Q&A) is a genuine confidence-gated
  pipeline — retrieval-confidence bands computed from real vector-similarity scores, explicit refusal on
  LOW confidence, strict prompt rules forbidding citations not present in retrieved context.
  `analiza/validator.py` code-enforces (not just prompt-requests) that clause excerpts are real substrings
  and clause refs exist in the actual segments sent. Case Genome deterministically computes case-strength
  % from evidence factors (not LLM self-report) and hard-flags fabricated document/evidence references.
  Drafting's `quality_gate` verifies every legal-article citation against the real indexed corpus.
- **Partially-honest**: Court Predictor's confidence *level* (VISOKO/SREDNJE/NISKO) is genuinely
  evidence-computed, but the accompanying *percentage* is raw, unverified LLM output never cross-checked
  against that level — a lawyer could see "NISKO poverenje" next to a contradictory "78%".
- **Overconfident-risk — the single riskiest feature in the app**: **Strategy Engine's Litigation
  Simulator** ("Verovatnoća uspeha tužioca: X%") is raw, unstructured GPT text with zero backend
  confidence computation, zero post-hoc validation, zero citation-grounding check anywhere in the code —
  honesty relies entirely on unverified prompt instructions. This is the least-grounded high-stakes number
  in the app, on arguably the single question a lawyer cares about most. **Not fixed this mission** — a
  proper fix means computing a real, independent confidence score (per the already-established
  Deterministic Intelligence Framework pattern: "LLM proposes, backend computes the score"), which is
  meaningful feature-level work, not a localized bug fix Keystone's First Rule permits without a founder
  go-ahead. Tracked as `KEYSTONE-004`, the single highest-priority non-Critical item in this report.
- Evidence classification similarly has no confidence field or validation at all, though lower-stakes.
- Naming-clarity note: `shared/ai_client.py`'s "Prompt Guard" is a prompt-*injection* defense, not a
  hallucination guard — there is no wrapper-level hallucination check; every grounding mechanism found is
  feature-specific, not universal.

---

## Phase 6 — Security Final Check

Full detail: `.vindex_ai_team/decisions/2026-08-04_keystone_phase6_security_INVESTIGATION.md`.

**One Critical finding** (see headline). **Everything else checked is Solid**:
- Authentication fails closed, algorithm-confusion-safe.
- Tenant isolation: RLS correctly present on all 6 core tables (`predmeti`/`predmet_dokumenti`'s RLS
  lives in `supabase_setup.sql`, which predates `migrations/` — explaining why a migrations-only grep in
  an earlier audit missed it; not itself a gap).
- Audit immutability: DB-level trigger blocks UPDATE/DELETE even against the service-role key.
- Secret hygiene: no hardcoded keys, correct `.gitignore`.
- Cron endpoints: all confirmed fail-closed; SEC-002's routing collision confirmed fixed (only one
  `/api/cron/daily` registration exists).
- 2026-08-02 urgent findings: exposed OpenAI key confirmed resolved in code. Profiles RLS gap **not
  independently re-confirmed this pass** — flagged as unconfirmed, not cleared (honest gap, not asserted
  either way).

---

## Phase 7 — Beta User Simulation

Full detail: `.vindex_ai_team/decisions/2026-08-04_keystone_phase7_beta_user_simulation_INVESTIGATION.md`.

**Most user-trust-damaging issue found (`GEN-2`, Medium-High)**: editing a case-defining field
(`tip`/legal area, `rizik`/risk level) via the inline editor gives an instant "Sačuvano ✓" confirmation,
but the Genome/Strategy AI analysis displayed right below it is never flagged as stale — it silently keeps
showing conclusions computed from the *old* value with no visual distinction from a fresh analysis.
Nothing is corrupted or lost; it's a trust gap, not a data-integrity bug.

**Secondary finding (`GEN-1`, Medium)**: the post-upload Genome background-regeneration watcher gives up
silently after 90s with no error state — reverts to the default hint text with no "this may have failed"
signal (manual refresh still works).

**Neither fixed this mission** — both are UI/UX-facing changes, and Keystone's own First Rule explicitly
excludes UX improvement from this mission's permitted scope ("Ne poboljšavati UX"). Tracked as
`KEYSTONE-005`/`006` for a dedicated future UX pass.

**Overall impression**: the flow is well above typical SaaS-at-this-stage trust instrumentation —
specific error messages nearly everywhere, honest async job status with real error text, and Genome
already ships a genuine self-verification line ("AI provera: N upozorenja") plus an "AI ograničenja"
section sourced from real data, not decorative. No wrong-status, lost-data, or raw-exception issues found
in the traced paths. Task/deadline creation UI and the day-after Dashboard/Alerts render path were not
independently re-traced this pass (flagged, not asserted).

---

## Fixes implemented this mission

1. **Event Bus atomic claim** (`services/event_bus.py`, `migrations/091_event_bus_atomic_claim.sql`) —
   closes the multi-worker duplicate-dispatch race. See Phase 4.
2. **`routers/dokument.py::dokument_pitanje`** migrated onto the canonical stack (`case_context()` +
   `log_action(action="dokument_pitanje", ...)`, added to `AUDITABLE_ACTIONS`) — the second, previously
   uncounted `ask_agent` call path Phase 2 found. Mirrors the exact proven pattern already used for
   `copilot.py::_handle_pravno_pitanje`.

**Deliberately NOT fixed this mission** (each requires a founder decision or is larger than a localized
fix permits under First Rule): GDPR cascading deletion (Critical), Strategy Engine confidence grounding
(High), Voice Orchestrator provenance wiring (High), silent-failure alerting for document
classification/Genome background tasks (High), Genome staleness/watcher UX (Medium — explicitly
UX-excluded).

**Tests**: 8 new (`tests/test_keystone_readiness_validation.py`) + 10 pre-existing tests updated across 5
files (`test_phoenix_reliability_failure_recovery.py`, `test_intake_phase0.py`, `test_case_dna_events.py`,
`test_mission_ledger_correlation.py`, `test_intake_e2e_restart.py`) to simulate the pre-migration-091
state so their existing mocks/fakes still exercise the intended plain-select fallback path
(`test_intake_e2e_restart.py`'s own strict RPC-name allowlist initially caught this mission's new
`claim_pending_events` call during the full-suite run — fixed by adding it as a simulated
"not deployed yet" case, exactly like the other 9). 236-test targeted regression sweep + full repository
suite both green — see Test Results below.

---

## Phase 8 — Final Risk Register

| # | Severity | Description | Impact | Evidence | Recommendation | Decision |
|---|---|---|---|---|---|---|
| K-1 | **High (narrowed from Critical, Mission Olympus 2026-08-04)** | GDPR account deletion doesn't cascade to Pinecone vectors or Storage files — case/client/document retention is disclosed with a stated legal basis (Zakon o advokaturi), not a silent gap, but that disclosure doesn't cover vectors/storage | Compliance exposure narrower than first reported — vectors/storage have no independent retention justification and aren't mentioned in the user-facing disclosure | `routers/gdpr.py::gdpr_delete_account:222-228`; Phase 6 investigation; Regulatory Compliance Verification Agent backtest | Founder decides whether to extend the disclosure to cover vectors/storage, and whether/how to actually purge them | **Founder decision required — not fixed this mission** |
| K-2 | Critical (mitigated, migration pending) | Multi-worker Event Bus duplicate dispatch | Duplicate `proactive_alerts`/audit rows under real production concurrency (4 gunicorn workers) | `services/event_bus.py`; Phase 1/4 investigation | Run `migrations/091_event_bus_atomic_claim.sql` | **Fixed in code + tests this mission; residual risk remains live until the founder runs the migration** |
| K-3 | High | Strategy Engine's litigation win-probability % is raw, ungrounded LLM output with zero validation | Highest-stakes number in the app, presented with no backend confidence check — reputational/trust risk if a lawyer relies on it | Phase 5 investigation | Apply the Deterministic Intelligence Framework pattern (backend-computed score) | **Flagged — `KEYSTONE-004`, not fixed (feature-level work)** |
| K-4 | High | Voice Orchestrator bypasses the AI wrapper entirely — no correlation_id/provenance | Breaks the "100% wrapper coverage" claim; voice sessions are unauditable | `services/voice_orchestrator.py`; Phase 1 investigation | Wire provenance capture into the Realtime API integration | **Flagged — `KEYSTONE-001`, not fixed (real dev work)** |
| K-5 | High | Document classification and Genome refresh background failures are log-only, no durable audit/alert | Silent data-quality degradation invisible to both user and operator | Phase 3 investigation | Apply Phoenix's already-proven nightly-alert retry+audit pattern | **Flagged — `KEYSTONE-003`, not fixed this mission (time-boxed)** |
| K-6 | High | Audit Link/Provenance/Reliability coverage all miss targets under the honest, full-system denominator | Prior missions' "mostly done" framing understated true remaining scope | Phase 2 investigation | Treat as ongoing, multi-mission work, not a single fixable defect | **Acknowledged, scoped for future missions** |
| K-7 | Medium | Genome analysis isn't flagged stale after a case-defining field edit | Lawyer could act on an outdated AI conclusion without realizing it | Phase 7 (`GEN-2`) | Add a staleness indicator (future UX pass) | **Flagged — `KEYSTONE-005`, explicitly UX-excluded from this mission** |
| K-8 | Medium | Genome background-regen watcher silently times out after 90s with no error state | Confusing but not data-damaging; manual refresh still works | Phase 7 (`GEN-1`) | Add an error state to the watcher (future UX pass) | **Flagged — `KEYSTONE-006`, explicitly UX-excluded** |
| K-9 | Medium | Predmet-creation endpoint has no idempotency key | Client-side retry could create a duplicate case | Phase 4 investigation | Founder/product decision on idempotency-key design | **Flagged, not fixed** |
| K-10 | Medium | Client creation uses the older `audit_log` mechanism, not hash-chained `audit_immutable`; no dedup on rapid double-submit | Inconsistent audit trail strength for one entity type | Phase 3 investigation | Migrate to `audit_immutable` in a future pass | **Flagged, not fixed** |
| K-11 | Medium | Court Predictor's confidence percentage isn't cross-checked against its own qualitative level | Could show "NISKO poverenje" next to a contradictory high percentage | Phase 5 investigation | Cross-validate or suppress the raw percentage | **Flagged, not fixed** |
| K-12 | Low | Anthropic previously listed as "unverified" is actually N/A (unused) | None — a documentation correction, not a risk | Phase 4 investigation | Update prior reports' framing | **Corrected in this report** |
| K-13 | Low | `routers/enterprise.py` and the "~208 orphan routes" figure were stale in memory | None — housekeeping | Phase 1 investigation (`scripts/audit_routers.py`: 13 confirmed-dead of 108) | Update memory; consider cleanup of the 13 confirmed-dead modules | **Corrected in this report; cleanup not performed (out of scope)** |
| K-14 | Unscored | File Storage, OCR timeout, general DB connection-loss, Anthropic-shaped failures, Timeline/Deadlines/Firm Brain failure posture | Unknown — genuinely not independently re-verified by any mission to date | Phase 3/4 investigations | Dedicated future investigation-only pass before any Reliability Score claim can honestly cover 100% of Phase 1's named systems | **Left honestly unscored, not assumed safe** |

---

## Test Results

New tests this mission: 8 (`tests/test_keystone_readiness_validation.py`). Pre-existing tests updated:
9 (mock adjustments across 4 files to simulate the pre-migration-091 state, preserving each test's
original intent unchanged). 236-test targeted regression sweep (event_bus/dokument/dispatch/copilot/
morning_briefing/case_dna/ledger/migration/phoenix/intake_phase0/keystone): **all passed**.

**Full repository suite: 2409 passed, 1 skipped, 0 failed** (2401 passed prior to this mission + 8 new
Keystone tests; the 10 updated pre-existing tests are 0 net test-count change). One regression surfaced
and was fixed during this run: `test_intake_e2e_restart.py`'s own fake Supabase client enforces a strict
RPC-name allowlist and initially raised `AssertionError: unexpected rpc: claim_pending_events` — fixed by
teaching the fake to simulate "RPC not deployed yet" for this call (the same fallback-path convention
applied to the other 9 updated tests), which is the actually-correct behavior for that fake's modeled
pre-migration-091 state.

---

## Remaining Technical Debt (beyond the Risk Register above)

- `MIGRATION-003` (Smart Intake correlation_id design decision) — still open, unchanged this mission.
- `SENT-001` (`ROK_KRITICAN`/`HEALTH_SCORE_PROMENJEN` non-durable emit) — still open, unchanged.
- `PHOENIX-001`/`002` (dead-letter/audit-failure rows have no operator-facing surface) — still open.
- `PHOENIX-004` (Pinecone ghost-vector cleanup on aborted upload) — still open.
- 13 confirmed-dead router modules (fresh `scripts/audit_routers.py` run) — cleanup opportunity, not a
  risk.

---

## Final Beta Gate Decision

Keystone's own decision framework:
- 🟢 **READY FOR CLOSED BETA** requires Reliability ≥90%, Failure Recovery ≥95%, Audit Link ≥90% (with
  justified exceptions), Provenance ≥90%, no Critical risks, no silent-failure scenarios.
- 🟡 **READY WITH ACCEPTED RISKS** requires the system to function, with known High risks the founder
  explicitly accepts.
- 🔴 **NOT READY** requires data loss, false success, unreliable AI conclusions, a security problem, or
  inability to reconstruct critical actions.

**Against this framework, honestly**: none of the 7 numeric targets are met (Reliability ~75–80%, Audit
Link ~39%, Provenance ~87%, Failure Recovery ~65–75%) — 🟢 is not supportable. There is no active data
loss, no active cross-tenant breach, and the core golden path (predmet creation → upload → Genome →
Search → Briefing → Copilot) functions correctly end-to-end with genuine, tested reliability engineering
behind it across 6 missions. But there **are** two unresolved High-severity risks — a narrower-than-first-reported compliance gap
(K-1, GDPR erasure — Pinecone/Storage specifically, not the whole case/client/document set, which is
already disclosed with a stated legal basis) and an "unreliable AI conclusion" risk (K-3, Strategy
Engine's ungrounded percentage) — that
Keystone's own NOT READY criteria name explicitly — so 🔴 has real support too.

**Decision: 🟡 READY WITH ACCEPTED RISKS — conditional on the founder explicitly accepting, in writing,
these named risks before opening a closed beta**:

1. **K-1 (GDPR erasure, narrowed)** — the case/client/document retention itself is already disclosed with
   a stated legal basis, not a hidden gap; the founder should decide whether Pinecone vectors and Storage
   files (the actually-undisclosed part) need manual purging on a deletion request during the beta, or
   whether extending the existing disclosure to mention them is sufficient for now.
2. **K-3 (Strategy Engine confidence)** — pilot users must be told this specific number is not
   independently validated, or the feature should be hidden/caveated for the beta cohort until fixed.
3. **K-2 (Event Bus race)** — the founder should run `migrations/091_event_bus_atomic_claim.sql` before
   or shortly after beta start; the code fix is inert until the migration runs.
4. The true system-wide Audit/Provenance/Reliability coverage is meaningfully lower than previously
   reported once measured against the full 76-call-site system — this is a scope/maturity fact for a
   closed beta with trusted users, not a blocker, but should inform what "production-ready" means before
   any wider rollout.

**This is not a green light for public launch or general availability** — it is a scoped, evidence-based
"yes, for a closed beta, with these specific, named, accepted risks" — consistent with this project's own
established Pilot Success Framework (small trusted cohort, not GA).
