# EXTREME_SCENARIO_REPORT — Operation Black Swan, Mission 001

Findings mapped to the mission's own 17 named scenarios plus AI Attack / Human Attack. "FIXED" items have
test coverage in `tests/test_blackswan_mission001.py`; "DEBT" items are in
`docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md`'s Black Swan section with explicit reasoning.

**Scenario 1 — 500 lawyers start simultaneously**: `_get_supa()`'s thread-unsafe lazy singleton produced 50
distinct Supabase clients instead of 1 under a real concurrent burst (Team 1). **FIXED** — `threading.Lock`.

**Scenario 2 — 20 firms × 1000 documents**: tenant-blind FIFO intake queue starves later firms (Team 2,
**DEBT-001**, architectural); unvalidated deadline extraction auto-accepts a contract-expiry date as a real
court deadline (Team 2, **DEBT-002**); exact-hash-only duplicate detection (Team 2, **DEBT-003**).

**Scenario 3 — OpenAI becomes slow, not down**: AI concurrency semaphore's 30s queue-timeout exception
bypassed the credit-refund check entirely (Team 3, **FIXED**); a 25s-per-attempt hardcoded OpenAI timeout is
shorter than this mission's own 30-60s slow-window, meaning 3 retries can hold a semaphore slot 76-84s
(Team 3, **FIXED** the refund side; the underlying capacity-collapse is **DEBT-018**).

**Scenario 4 — OpenAI returns timeout/malformed/partial/retry-storm/rate-limit randomly**: `copilot.py`'s
credit-consumption had zero refund path anywhere in the file, a new call site never covered by the prior
certification's identical fix elsewhere (Team 3, **FIXED**). 4 other GPT call sites (case_dna, court_
predictor, ambient_analyzer, llm_retry) verified genuinely fail-safe under the same attack.

**Scenario 5 — Supabase briefly loses connectivity**: `faktura_create`'s billing_entries UPDATE had no
try/except at all — a blip landing there left a permanent orphan invoice (Team 4, **CRITICAL, FIXED**);
`kreiraj_predmet`'s events-outbox insert on a blip silently and permanently lost the entire Case Pipeline
trigger for that case (Team 4, **FIXED** via retry + reconciliation sweep); Event Bus dispatch double-
executed a handler on a blip landing between execution and mark-dispatched (Team 4, **DEBT-009**, 4
handlers need idempotency keys); Genome refresh's audit-trail event silently lost on a blip (Team 4 + Team
5, **DEBT-010**).

**Scenario 6 — worker dies mid-operation**: Genome refresh, Event dispatch, Intake finalize, Billing,
Notification creation all simulated at 3 crash points each. Event Bus's own claim-heartbeat (from the prior
certification) re-verified to hold under this exact scenario. Billing's orphan-invoice gap re-confirmed via
a SECOND, independent trigger mechanism (Team 5) — same **CRITICAL, FIXED** item as Scenario 5. Genome's
audit-trail loss re-confirmed (Team 5) — same **DEBT-010**.

**Scenario 7 — two users edit the same case**: Kanban board's `update_kanban_faza` had zero concurrency
guard — a lost update with the losing caller's own response claiming false success (Team 1, **FIXED** via
an `if_faza` optimistic-concurrency precondition, both backend and frontend). The prior certification's own
`if_updated_at` protection on the general case-update endpoint was found to have zero live frontend callers
— protecting nothing (named, not separately actioned — that endpoint's OTHER protection, whitelisted-
fields-only, was independently verified safe for the tab-conflict scenario it actually faces).

**Scenario 8 — 10 AI agents process the same case**: manual Genome-refresh button bypassed the background
trigger's own in-process coalescing guard entirely — 2 concurrent manual refreshes produced duplicate
version numbers and a losing caller's response that lied about what was actually saved (Team 1, **FIXED**).
The coalescing guard's own cross-worker-process limitation (self-disclosed in its own code comment) was
independently re-confirmed real by 2 teams (**DEBT-011**).

**Scenario 9 — 50 parallel events for one case**: Event Bus's SKIP-LOCKED claim + per-consequence unique-
constraint claim held under direct simulation — no new finding at the Event Bus layer itself; the residual
risk is entirely the cross-process Genome-coalescing gap above (**DEBT-011**).

**Scenario 10 — 10,000 documents / 50,000 pages / thousands of deadlines on one case**: `case_context.py`'s
canonical AI-context builder had an unbounded `predmet_hronologija` query — simulated 500 sequential
actions showed 101.7x row-fetch growth and 16.1x per-call slowdown over one session (Team 7, **FIXED** via
bounded, recency-ordered queries). Other direct document/timeline queries outside this canonical path
remain unbounded (**DEBT-005**, partially addressed).

**Scenario 11 — upload/refresh/delete/restore/rename/merge/split simultaneously**: merge, split, and hard
delete (both case and document) confirmed **not to exist anywhere in the codebase** (grep-verified, not
guessed) — the real lifecycle is status-based only. Reopen-vs-close race produces a self-contradictory
permanent record: case reads "open" while `predmet_hronologija` permanently shows "closed, outcome: X"
(Team 6, **CRITICAL-adjacent HIGH, FIXED** via the same `.neq()` guard pattern used elsewhere). Upload
completing into an already-closed case (**DEBT-014**) and a cosmetic stale-name-in-response race on rename-
vs-refresh (**DEBT-015**) both named, not fixed.

**Scenario 12 — 12 hours without closing the app**: the same unbounded `predmet_hronologija` query as
Scenario 10 is the dominant finding here too (Team 7, **FIXED**, same fix). A 1-hour cache-staleness window
on the Firm Health Index dashboard is a deliberate, reasonable TTL tradeoff, not a bug. No memory/cache leak
found within a single session; Event Bus backlog stays at 0 for any plausible single-lawyer rate (but no
monitoring exists if it didn't — **DEBT-006**).

**Scenario 13 — 3 firms on completely different cases**: **zero new cross-tenant leaks found**, across
context/cache/ownership/AI/notification leak categories, all actively tested via real multi-threaded/multi-
tenant reproduction, not just code reading (Team 8). Both previously-known-fixed leaks (document-namespace
ownership, AI-context cache) re-verified still fixed.

**Scenario 14 — bad documents (wrong/duplicate/corrupted/empty/OCR-error/wrong-date)**: the deadline-
plausibility gap (**DEBT-002**, shared with Scenario 2) and corrupted-file wasteful-retry (**DEBT-004**,
low severity) are the findings here; zero-byte and blank-PDF handling both verified genuinely fail-soft.

**Scenario 15 — 30-day abandonment, then return**: the mission's other CRITICAL finding — overdue deadlines
vanish from risk score, canonical priority, AND case actions (3 independent code copies of the same bug),
plus a 4th manifestation in the notification-regeneration logic that silently deletes evidence of a missed
deadline rather than surfacing it (Team 9). **All 4 manifestations FIXED** this mission. Genome's own lack
of a staleness timestamp (**DEBT-007**) and the invisible `agent_recommendations` feature (**DEBT-008**)
both named as related but separate debt.

**Scenario 16 — thousands of notifications/events/AI calls**: starvation, deadlock, and livelock all
actively simulated at 5,000-row scale and **ruled out** — the Event Bus's existing hardening genuinely
holds under real load (Team 10). One real finding: no backpressure/admission-control mechanism exists, so
sustained arrival above the 4-worker drain capacity causes genuinely unbounded backlog growth (not a retry-
logic bug) — **DEBT-006** (monitoring) covers detecting this; the backpressure mechanism itself is a larger
architectural item not separately numbered here (see `STRESS_TEST_REPORT.md`).

**Scenario 17 — worst possible day, everything at once**: covered by Team 14's dedicated cross-subsystem
work — see `SYSTEM_SURVIVABILITY_REPORT.md` for the 4 combined-stressor findings, 3 of which were genuinely
invisible to every single-scenario team and only surfaced by deliberately combining stressors.

**AI Attack**: 7 confirmed cases of fabricated/manipulated GPT output reaching an unguarded field or the
lawyer's screen (Team 11) — see `docs/blackswan/BLACK_SWAN_REPORT.md` and the Debt Register's `-019`/`-020`/
`-021` entries for the 3 not fixed this mission (court_predictor.py's missing guard, the Forensic Audit
validator's excerpt-support gap, Genome's advisory-not-blocking require_review verdict).

**Human Attack**: 6 confirmed findings from ordinary chaotic usage (Team 12) — an unhardened second upload
path that double-bills real credits on retry, 3 more double-submit gaps on task/hearing/evidence creation,
and a whole-form last-write-wins bug on client record edits. All named as **DEBT-012/013**, deferred for
fix-cycle time on well-understood, low-risk follow-ups, not architectural difficulty.
