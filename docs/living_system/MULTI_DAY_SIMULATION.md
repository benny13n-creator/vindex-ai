# Operation Living System — Days 2-3: Interruption, Concurrency, and Scale

3 read-only agents simulated interrupted work, concurrent staff edits, and a busy established
firm at scale. Disposition key: **FIXED** / **DEBT** / **CONFIRMED CLEAN** as in
`LAWYER_DAY_SIMULATION.md`.

## Day 2 — Interrupted work: browser refresh, crash, network outage, retry

| Finding | Severity | Disposition |
|---|---|---|
| Service Worker auto-reload on deploy (`controllerchange` → `window.location.reload()`) silently destroys in-progress Intake Wizard/drafting state — no persistence, no warning, and it's an *involuntary* reload the lawyer didn't trigger | HIGH | DEBT (`LIVINGSYS-DEBT-005`) |
| AI credit charged even when generation silently degrades/fails, confirmed at 3 call sites (`/api/nacrt`, `/api/podnesak`, `/api/commander/analiza`) — the correct pre-deduct/refund or success-gated pattern exists elsewhere in this same codebase but was never extended here | HIGH | DEBT (`LIVINGSYS-DEBT-002`, `-027`, and Case Commander's own instance folded into `LIVINGSYS-DEBT-006`) |
| No idempotency guard on user-triggered retries for drafting staging (`staging_memory` insert has no dedupe key) | MEDIUM-HIGH | DEBT (`LIVINGSYS-DEBT-031`) |
| Zero dedup on document re-upload by hash or filename on Pipeline A (same finding as the Day-1 doc-intake report, independently reconfirmed) | MEDIUM-HIGH | DEBT (`LIVINGSYS-DEBT-020`, same item) |
| Service Worker's `offline: true` flag is dead code — no single consistent "you are offline" app state (each feature's own generic error handles it adequately in practice) | LOW | DEBT (`LIVINGSYS-DEBT-032`) |
| `execQuery()`'s network-drop handling, upload-flow error recovery, Copilot chat error recovery, the 2 endpoints with real pre-deduct/refund logic, Service Worker's network-first API routing | — | **CONFIRMED CLEAN** |

## Day 2 — Parallel hands: secretary, partner, and lawyer on the same case

| Finding | Severity | Disposition |
|---|---|---|
| Case core-field inline-edit (`tuzeni`/`rizik`/`vrednost_spora`/etc.) has a real, working optimistic-concurrency guard (`if_updated_at`) already built into the backend — but the live frontend editor never sends it, so it's dead protection, not missing protection | HIGH | DEBT (`LIVINGSYS-DEBT-007`) |
| A third case-status writer (`routers/learning.py`'s outcome endpoint, fired automatically right after case close) bypasses the `.neq()` race guard both sibling status-writers already have, and writes no audit trail | MEDIUM | DEBT (`LIVINGSYS-DEBT-033`) |
| `zadaci` (manually-assigned staff tasks) status changes have zero concurrency guard — a different table from the already-protected `case_actions` | MEDIUM-HIGH | DEBT (`LIVINGSYS-DEBT-034`) |
| Client-info corrections can silently flow into AI-drafted document text via a stale browser-side snapshot (`window._predFull`) that's never re-fetched before draft generation | MEDIUM | DEBT (`LIVINGSYS-DEBT-035`) |
| No live-update mechanism on the case workspace — visible staleness (not silent loss) when two tabs are open on the same case | LOW, characterization not a bug | Noted, no action needed |
| Kanban `faza` transitions, case close/reopen guards, `case_actions` update/close race protection, strategy endpoints (confirmed fully stateless, no lost-update risk exists) | — | **CONFIRMED CLEAN** |

## Day 3 — A busy, established firm at scale (~1000 docs, ~100 hearings, large portfolio)

| Finding | Severity | Disposition |
|---|---|---|
| Daily email reminder cron never filtered by `predmeti.status` — a deadline on an archived/closed case was proactively emailed to the lawyer's inbox exactly like an active one; the single most trust-damaging instance of the archived-case-leak class since it's an outbound push, not a dashboard the lawyer opens by choice | CRITICAL | **FIXED** (Fix L2) |
| CIO daily report hard-caps the portfolio at 40 cases, ordered oldest-updated-first (the most-neglected cases), and presents the truncated, biased sample as the true portfolio total with no disclosure | CRITICAL | DEBT (`LIVINGSYS-DEBT-003`) |
| Command Center's "today's hearings"/"next 7 days"/"<48h urgent" panels leaked archived-case hearings/deadlines onto the app's actual home tab | HIGH | **FIXED** (Fix L7) |
| Firm Memory's `.order("vaznost")` sorts alphabetically ascending — LOW-importance memories before HIGH-importance ones — at all 4 query sites including the one that feeds the AI advice context directly, silently starving GPT of the most important judge/client facts once a firm has more memories than the query limit | HIGH | DEBT (`LIVINGSYS-DEBT-008`) |
| `case_actions` operational worklist ("what must I do today") includes archived/closed cases — no consequence executor exists for case closure/archival that would close out lingering open actions | MEDIUM-HIGH | DEBT (`LIVINGSYS-DEBT-036`) |
| AI Deadline Guardian scans deadlines with zero case-status awareness | MEDIUM | DEBT (`LIVINGSYS-DEBT-037`) |
| Calendar: 200-row cap with no truncation signal, plus the same archived-case leak, on the one screen whose entire job is "don't let a lawyer miss a hearing" | MEDIUM (cap) / HIGH (silent-failure variant, see `CHAOS_RESULTS.md`) | DEBT (`LIVINGSYS-DEBT-038`) |
| Dashboard's historical "risk worsened since last look" diff can silently lose coverage at scale (300-row global cap) — does not affect the *current* risk value shown, only the change-alert | LOW-MEDIUM | DEBT (`LIVINGSYS-DEBT-039`) |
| Dashboard's live risk computation (uncapped), `case_actions` worklist priority/lifecycle (minus the archived-case leak above), `case_intelligence.py`'s AI briefing context builder's token-budget discipline, reactivation correctness for status-filtered views, bulk status-change race guards | — | **CONFIRMED CLEAN** |

## Summary

Days 2-3 surfaced 2 fixed findings (1 CRITICAL, 1 HIGH) plus 15 deferred findings. The strongest
recurring pattern across all 3 waves: **declared protections that were never wired up** — a real
`if_updated_at` guard the frontend never sends, a real refund-on-failure pattern only 2 of 5
AI-credit endpoints use, a real status-filter pattern only 2 of 6 archived-case-touching queries
apply. This mirrors the exact "declared control ≠ enforced control" principle this engagement's
earlier missions (Forensic Remediation, Program Lambda) already established as the platform's
single most recurring failure signature.
