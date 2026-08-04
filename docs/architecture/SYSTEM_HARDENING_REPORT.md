# System Hardening Report — Program Alpha, Phase 7 + Phase 8

**Mission's own success test, restated**: *"Misija nije uspešna zato što su testovi prošli. Uspešna je
samo ako su dokazano ispunjeni sledeći kriterijumi: smanjen broj kanonskih implementacija, smanjen broj
poslovnih pravila, smanjen broj izvora istine, smanjen broj paralelnih tokova, smanjen broj fallback-ova,
smanjen broj heuristika, povećana determinističnost, povećana dokazivost, povećana održivost."* Tests
passing is necessary, not sufficient. This report is the actual proof.

---

## Phase 7 — Regression Analysis (did complexity actually decrease?)

### Duplicate-implementation count, before → after this mission

| Concept | Before | After | Reduction |
|---|---|---|---|
| `proactive_alerts` insert | **12** independent call sites, 0 shared helper | **1** canonical function (`shared/proactive_alerts.py::create_proactive_alert`), 12 call sites now call it | 12 → 1 |
| Embedding model identifier (ingestion) | **9** independent hardcoded `"text-embedding-3-large"` string literals in live application code (5 routers found by the original diagnostic + 4 more — `api.py` ×2, `uploaded_doc/ingest.py`, `drafting/playbook.py`, `interni_stavovi.py` — found by Mission Olympus's Architecture Review Agent during Phase 9 governance review, corrected in the same pass rather than left half-fixed) | **1** canonical constant (`app/services/retrieve.py::EMBEDDING_MODEL`), imported by all 9 live call sites | 9 → 1 (live application scope) |
| Court Predictor confidence number | **2** independent authors (`_calc_confidence_nivo`'s deterministic score, and a separate, unchecked GPT-4o-mini call for `procenat`) | **1** author (`_procenat_iz_score()`, a pure function of the same score) | 2 → 1 |
| Business audit trail for AI-call quality data | **2** overlapping mechanisms (`audit_immutable`/`ai_forensics` + the write-only, zero-reader `response_audit`/`app/services/audit_log.py`) | **1** (`audit_immutable`/`ai_forensics` only) | 2 → 1 |
| Request correlation ID (client-visible) | **2** fully independent, unlinked mechanisms (`api.py`'s own `_correlation_id_var` middleware + `shared/ai_provenance.py`, disconnected) | **1** (`shared/ai_provenance.py`, the middleware now reads/writes into it) | 2 → 1 |
| Correlation ID minting call sites | **3** (1 canonical `new_correlation_id()` + 2 ad hoc inline `uuid.uuid4()` in `case_dna.py`) | **1** (canonical only) | 3 → 1 |

**Scope note on the embedding-model count**: a repo-wide grep also finds `"text-embedding-3-large"`
hardcoded in ~14 standalone scripts at the repo root and in `scripts/` (`debug_rag.py`, `diag_a6_prod.py`,
`diag_crypto_coverage.py`, `ingest_glossary_vasp_casp.py`, `ingest_kz.py`, `ingest_laws.py`,
`ingest_misljenja.py`, `scrape_zdi_mca.py`, `scripts/ingest_*.py`, `scripts/proof_direct.py`,
`scripts/smoke_test_sp.py`). **Confirmed, not assumed**: none of these are imported by any live
application module (`grep`'d for imports of each — zero hits outside the file itself) — they are
manually-run, one-off data-ingestion/diagnostic tools, not part of the request-serving application this
mission's stress-test framing (10,000 predmeta, 100 parallel AI analyses) concerns. Deliberately left
out of the "9 → 1" count above and not modified — the count above is honestly scoped to live application
code, not silently inflated by excluding inconvenient hits, nor silently deflated by including irrelevant
ones.

**6 distinct classes of duplicate/competing implementation eliminated this mission, reducing 30 combined
independent/duplicate call sites and mechanisms down to 6 canonical ones** (12+9+2+2+2+3 — the embedding-
model count of 9, not the originally-diagnosed 5, reflects Mission Olympus's own Phase 9 governance
review catching 4 additional live call sites the diagnostic phase missed, corrected in the same pass —
see the "Governance Review Outcome" section of `CANONICAL_ARCHITECTURE_REPORT.md`).

### Files and lines — net change

`git diff --stat` (excluding the pre-existing, unrelated `migrations/smart_contract_analyses.sql`
modification; includes the 4 additional embedding-model call sites fixed during Phase 9 governance
review — see below): **29 files changed, 331 insertions(+), 603 deletions(-)** — net **-272 lines** in
tracked files. Plus one new canonical module, `shared/proactive_alerts.py` (86 lines), which *replaces*
12 independent implementations rather than adding a 13th. **Net result: application code shrank by
approximately 186 lines while eliminating 6 classes of duplication** — direct evidence that this mission
reduced complexity rather than just moving it around.

**2 files deleted entirely**: `app/services/audit_log.py` (130 lines — `log_response`/`_write`/`_get_supa`/
`_sha`, fully orphaned once its 5 call sites were migrated to the canonical `ai_forensics` mechanism) and
`test_audit_b1.py` (167 lines — a standalone smoke-test script for the now-retired `response_audit`
mechanism, not part of the actual pytest-collected suite, confirmed via `pytest.ini`'s `testpaths = tests`).

**1 dead ContextVar removed**: `api.py`'s `_correlation_id_var`, confirmed to have exactly 2 readers in
the whole codebase (both inside the middleware that defined it) before removal.

**1 dead, always-failing code path removed**: `routers/gdpr.py`'s `_al.log(...)` call, which invoked a
method that did not exist on `app/services/audit_log.py`, raised `AttributeError` on every single
execution, silently swallowed by a bare `except Exception: pass` — a real bug, not just dead code, now
gone along with the whole module.

### Fallbacks and heuristics

- **Fallbacks removed**: the 2 inline `uuid.uuid4()` fallback mints in `case_dna.py` (no longer needed —
  the canonical `new_correlation_id()` is now the single call in both the try and except branches).
- **Fallbacks correctly preserved, not removed**: `shared/proactive_alerts.py`'s and the correlation-id
  middleware's own graceful-degradation paths (missing-function/missing-header fallbacks) are legitimate
  compatibility behavior, not duplicate business logic — kept per this mission's own distinction between
  "a fallback masking a duplicate decision" (removed) and "a fallback handling a genuinely absent
  dependency" (correct to keep).
- **Heuristics removed**: Court Predictor's raw-GPT-guessed confidence percentage — a textbook "opinion
  presented as measurement" heuristic — replaced by a deterministic function of already-computed evidence
  counts.

### Determinism and provability — before/after

- Court Predictor's confidence percentage: was **non-deterministic** (a fresh LLM call could return a
  different number for the identical input) → now **fully deterministic** (same score, same percentage,
  every time — proven by `tests/test_program_alpha_canonical_architecture.py`'s
  `test_procenat_is_deterministic_function_of_score_not_llm`).
- The externally-visible `X-Correlation-ID` header: was **unprovable** against internal records (0%
  match rate, confirmed by direct code trace — the header's value was never read by anything) → now
  **provably identical** to what `audit_immutable`/`ai_forensics`/`events` actually record for the same
  request (proven by `test_middleware_sets_the_canonical_ai_provenance_context`).
- A permanently-failing `proactive_alerts` insert: was **silently lost** at 10 of 12 call sites (only
  Project Phoenix's own `morning_briefing.py` fix had retry+durable-audit) → now **durably recorded** at
  all 12, uniformly (proven by `test_exhausted_retries_writes_durable_audit_and_returns_false`).

---

## Phase 8 — Architectural Stress Test (Future Failure Analysis)

Per the founder's own addendum: for each item actually implemented, does it hold unchanged at 10 users,
500 users, 5,000 users, 50,000 predmeta, and when maintained by someone who wasn't part of building it?
If not, it should have been rejected in favor of a simpler, canonical alternative — this section is that
check, applied honestly *after* implementation (the items below all passed; nothing here was rejected in
hindsight, but the check is shown working, not asserted).

| Item | 10 users | 500 users | 5,000 users | 50,000 predmeta | Unfamiliar future maintainer |
|---|---|---|---|---|---|
| `case_dna.py` correlation-id mint fix | Identical — pure function substitution, no I/O, no state | Identical | Identical | Identical (no per-predmet cost) | One canonical minting function to find via grep — self-evident |
| `gdpr.py` dead-code removal | Identical — the code never executed | Identical | Identical | Identical | One fewer confusing "safety net that does nothing" to puzzle over |
| Embedding model constant | Identical | Identical | Identical | **Improves specifically at this scale** — a future `EMBEDDING_MODEL` change now updates all 6 call sites atomically instead of silently diverging if only some hardcoded literals get updated, which is exactly the failure mode that gets *more* likely (more files, more contributors) at real scale | The constant's name and single origin are self-documenting; no historical knowledge needed |
| Court Predictor `nivo`/`procenat` | Identical behavior, one fewer GPT call | Identical | **Improves** — one fewer OpenAI call per confidence-check request reduces real cost and latency proportionally to volume, and eliminates a whole class of contradiction bugs regardless of request volume | N/A (per-request, not per-predmet) | The docstring on `_procenat_iz_score` explains the *why* (the exact contradiction it prevents) — a maintainer doesn't need to have seen the original bug to understand the invariant |
| `response_audit` retirement | Identical — table already had 0 readers | Identical | **Improves** — removes a wasted Supabase write per relevant AI call (5 call sites) that returned zero value, a cost that scaled with volume for no benefit | N/A | One fewer competing "where do I look for what happened" answer to reconcile |
| `create_proactive_alert()` | Identical | Identical — no shared lock/queue, each call is an independent `asyncio` task exactly as before | **Holds** — per-call retry/backoff (0.5s/1.0s, jittered by real request timing) creates no synchronized retry storm even under high concurrent alert volume (e.g. a mass nightly run across many users); stateless, no new bottleneck introduced | **Improves** — the historical wrong-column-name bug (silently broken for an unknown period) is now structurally impossible at any future call site, since a typo'd parameter is a Python `TypeError`, not a silent Postgres schema mismatch | The module's own docstring names the exact historical bug that justifies its existence — a maintainer 2 years from now doesn't need to excavate git history to understand why this function has named parameters and internal retry |
| Correlation-ID middleware unification | Identical | Identical | Identical — `contextvars` are already `asyncio.Task`-isolated per request under FastAPI's model; this fix doesn't change that isolation, only ensures ONE id is used consistently within it, at zero additional cost | N/A (per-request) | **The value of this fix increases specifically with scale** — a founder personally reading every log at 10 users doesn't need correlation ids nearly as much as a support team investigating one ticket out of thousands at 5,000 users does; the code comment states this exact reasoning |

**No item was found to require future large refactoring or fail to hold at scale** — each either holds
identically or specifically *improves* as volume grows, which is the intended direction (a fix whose
value is concentrated at low volume and irrelevant at high volume would be a warning sign this framework
is designed to catch; none of the 7 items implemented this mission show that shape).

### The one honest exception — found, not fixed, explicitly flagged

**`api.py::_require_auth`'s correlation/user-context stamp is currently inert**, for a reason this
mission's stress-test discipline surfaced directly: every one of its 11 call sites invokes it via
`await asyncio.to_thread(_require_auth, authorization)`, and a `contextvars` mutation made *inside* a
`to_thread`-offloaded function does not propagate back to the awaiting coroutine (confirmed empirically —
see `ARCHITECTURAL_DEBT_REGISTER.md` for the reproduction). This means the correlation-id unification
fixed above works correctly for the majority of endpoints (those using `shared/deps.py::get_current_user`,
a genuine `async def` FastAPI dependency with no thread hop), but the 11 `_require_auth`-based endpoints
still don't get a correctly-stamped `user_id`/reused-`correlation_id` in their own request context —
**this holds identically at every scale (10 through 50,000+)**, because it's a per-request architectural
gap, not a volume-triggered one. Deliberately not fixed in this same pass — the correct fix (converting
`_require_auth` to `async def`, removing the thread offload) touches 11 call sites and deserves its own
dedicated, tested pass, not a bolt-on to an already-large mission. See
`ARCHITECTURAL_DEBT_REGISTER.md`'s `ALPHA-001`.
