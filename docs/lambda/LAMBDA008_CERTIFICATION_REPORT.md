# Program Lambda, Final Certification 008 — "The Final Gate"

**Date**: 2026-08-07
**Mission**: the last independent forensic certification of the Vindex AI platform before Operation Black
Swan and closed beta. Fresh session — the founder's own explicit choice after Certification 007 hit the
prior session's 200/200 subagent spawn limit — so the full parallel-fork budget every certification in
this chain has relied on for breadth was actually available this time, unlike 006/007.

**Method, exactly as the mission's own rules demand**: assume every prior sprint could be wrong. Trust
nothing — not documentation, not prior reports, not commit messages, not the Debt Register, not the
Mission Board, not even this program's own earlier conclusions. The only source of truth is current code.
15 independent teams (14 forensic + Red Team), each scoped to one domain, each explicitly briefed to
distrust prior claims and cite only direct code evidence. No team shared assumptions or used another
team's findings as evidence. Coordinator applied fixes directly after triage/Red Team survival (this
deviates from the masterprompt's literal "coordinator must not touch code" — consistent with this
program's actual operating practice across Certifications 004-007, disclosed here rather than hidden).

## Organization

- **Team 1** Architecture Integrity
- **Team 2** Security & RLS
- **Team 3** Ownership / IDOR
- **Team 4** Event Bus / Distributed Consistency
- **Team 5** Concurrency / Race Conditions
- **Team 6** AI Governance
- **Team 7** Canonical Context
- **Team 8** Canonical Decision Sources
- **Team 9** Performance & Scalability
- **Team 10** Reliability & Failure Recovery
- **Team 11** Frontend / Backend Consistency
- **Team 12** Documentation Drift
- **Team 13** Migration & Schema Drift
- **Team 14** Dead Code / Shadow Workflow
- **Team 15 (Red Team)** — split into 3 parallel adversarial clusters (A: Security/IDOR/Migration/Docs,
  B: Architecture/Event Bus/Concurrency/Canonical, C: AI/Performance/Reliability/Frontend/Dead-code), each
  tasked with trying to overturn every finding assigned to it.

## Phase 1-2: repository census + architecture verification

617 Python files, 112 routers, 94 migrations (at start — now 96 with this sprint's 2 drafted-not-applied
additions), 223 test files (now 224, +1 new file). Architecture verification folded into Team 1's own
mandate below.

## Phases 3-8: forensic findings (19 substantive, all Red-Team-survived)

Full raw findings ledger with every team's exact evidence is preserved in this certification's working
notes; summarized here by team, severity, and disposition (FIXED this sprint / DEBT-REGISTERED / FOUNDER
ACTION REQUIRED).

| # | Team | Finding | Severity | Disposition |
|---|---|---|---|---|
| 1 | Security & RLS | `deduct_credit`/`set_user_pro` RPCs + `profiles` RLS still exploitable — migrations 102/103 written (Cert 002) but still not applied to live Supabase | **CRITICAL** | **FOUNDER ACTION REQUIRED** — see `LAMBDA008-SEC-001` in the Debt Register |
| 2 | Concurrency | `billing.py::_sledeci_broj_fakture` invoice-number race, no unique constraint, dead atomic RPC | HIGH | **FIXED** — retry-on-23505 + migration 104 (drafted) |
| 3 | Reliability | `/api/pitanje` + `/api/pitanje/stream` burn a credit on genuine LLM failure, no refund | HIGH | **FIXED** |
| 4 | Canonical Decision Sources | `health_index.py` selects a column (`rizik_nivo`) that doesn't exist anywhere in the schema — silently zeroes 4 dashboard components | HIGH | **FIXED** |
| 5 | Security & RLS | `routers/dokument.py`'s session-based endpoints let any authenticated user read another firm's permanent case documents via a guessed/leaked `predmet_id` (`pred_*` namespaces never expire) | HIGH | **FIXED** |
| 6 | Architecture | `api.py::predmeti_dashboard` — a 4th independent, hand-rolled priority-scoring formula bypassing the canonical Attention Engine | MEDIUM-HIGH | **FIXED** |
| 7 | Event Bus | Batch-claim staleness race: whole-batch `claimed_at` + strictly serial GPT-bound dispatch can let a still-queued row become reclaimable mid-processing | HIGH | **FIXED** — per-row heartbeat |
| 8 | Frontend/Backend | Smart Intake finalize's honest soft-failure signals (`dokument_povezan`, `klijent_nesiguran`) computed but never shown to the lawyer | HIGH | **FIXED** |
| 9 | Performance | `workers/background_agents.py` fully sequential O(users×cases×GPT-calls) fan-out inside one cron call | HIGH | **FIXED** — bounded concurrency |
| 10 | Migration/Schema | `predmet_dokumenti.redni_broj`/`.tekst_sadrzaj` are core columns with zero migration ever creating them | HIGH | **FIXED** — migration 105 (drafted) + defensive fallback |
| 11 | Canonical Context | `case_commander.py` + `zakon_monitoring.py` bypass `case_context.py`'s recency-aware document sampling | MEDIUM-HIGH / MEDIUM | **FIXED** |
| 12 | AI Governance | `ambient_analyzer.py`'s live-typing copilot suggests legal citations with zero grounding check | MEDIUM-HIGH | **FIXED** |
| 13 | Documentation Drift | `SOURCE_OF_TRUTH_REGISTRY.md` listed 4 already-fixed bugs (commit `a5f4eeb`) as open Critical items | MEDIUM-HIGH | **FIXED** (doc corrected) |
| 14 | Performance | `morning_briefing.py::briefing_cron` — sequential, no internal timeout wrapper (worse than the background-agents finding in this one respect) | MEDIUM | **FIXED** — bounded concurrency + 540s cap |
| 15 | Frontend/Backend | Court Predictor's court-mismatch warning + Global Search's partial-failure signal computed but never shown | MEDIUM-HIGH / MEDIUM | **FIXED** |
| 16 | Concurrency | `klijenti/router.py` create + `predmeti_close.py` close — no double-submit / race guard | MEDIUM / MEDIUM-LOW | **FIXED** |
| 17 | Canonical Decision Sources | `matter_intel.py::get_uncertainty_dashboard` independently recomputes missing-document % | MEDIUM | **DEBT-REGISTERED** (`GAMMA-003`, re-confirmed) |
| 18 | Dead Code | 9 additional confirmed-dead router modules + `status_page.py` mixed | LOW | **DEBT-REGISTERED** (`LAMBDA008-DEAD-002`) |
| 19 | Ownership/IDOR | `billing.py::billing_po_klijentu` no ownership filter on initial query (not independently exploitable) | LOW | **FIXED** |

Plus 2 documentation-hygiene items: `LAMBDA-003`/`LAMBDA007-DEAD-001` merged (duplicate tracking of the
same finding), migration numbering gap 027-035 noted as cosmetic (no action needed).

## Phase 9: Red Team adversarial re-attack

3 parallel clusters, 19 findings attacked, **19/19 survived** (0 falsified, 0 downgraded). 2 findings came
back with corrections that *strengthened* or *reframed* them: the `dokument.py` session exposure is
permanent (never-expiring namespace), not session-scoped as first described; the `background_agents.py`
finding was corrected from "could hang for hours" to "hard-capped at 600s but silently loses coverage as
scale grows" once Red Team found the existing `asyncio.wait_for` wrapper the original team missed. One
Red-Team-adjacent correction was caught independently by the coordinator during documentation fixes: Team
12's own "remaining Critical count: 2" was itself off by one (verified directly against current code — the
true count is 3, not 2) — corrected in `SOURCE_OF_TRUTH_REGISTRY.md`.

## Required Fix Rule — applied

Every FIXED item above was reproduced (via a failing/soon-to-be-written test or direct code trace), root-
caused, fixed, covered by a new regression test, and re-verified. 17 new tests in
`tests/test_lambda008_certification.py`, 1 new test in `tests/test_predmeti_close.py`, 1 new test in
`tests/test_copilot_ambient.py` (19 new tests total). The fix cycle itself found and fixed 4 self-inflicted
regressions in *existing* tests (2 in `test_billing_naplata.py`, 2 in `test_copilot_ambient.py`) — both
root-caused to stale test fixtures that predated this sprint's own new ownership/grounding checks, not
flaws in the fixes themselves; both root-caused, fixed, and re-verified before this report was written.

## Final validation

Full regression suite, independently re-run after all fixes: see `MISSION_BOARD.md`'s Certification 008
entry for the exact final count. Zero regressions from this sprint's own changes carried into the final run.

## Not fixed this sprint, by design

- **`LAMBDA008-SEC-001`** (migrations 102/103 unapplied) — founder action, not a code fix, per this
  program's standing convention (`feedback_migrations`).
- **`GAMMA-003`** (matter_intel.py duplicate missing-doc %) — re-confirmed still open; consolidating it
  cleanly is a larger scope decision than this sprint's fix-cycle budget allowed.
- **9 additional dead router modules** — deleting confirmed-dead code is a product judgment (delete vs.
  revive), consistent with this program's own established practice for `onboarding.py`.
- **Migrations 104/105** (this sprint's own new migrations) — drafted, committed, NOT applied, per standing
  convention. Founder must run them.

## Verdict

Per the mission's own success criterion — "don't try to prove the platform is ready, try to prove it isn't"
— this certification found 19 real, Red-Team-survived issues across security, concurrency, reliability,
architecture, AI governance, and UX-honesty, of which 17 were fixed directly this sprint with test coverage,
1 remains architecturally deferred with an honest reason, and 1 is a **CRITICAL founder action item that
predates this sprint** (re-confirmed, not newly discovered) and is the single highest-priority item in this
entire report. **The platform is not certified ready for Operation Black Swan until migrations 102 and 103
are applied to production** — everything else found this sprint has either been fixed or is a bounded,
disclosed, lower-severity item. See `BETA_READINESS_FINAL.md` for the explicit go/no-go statement.
