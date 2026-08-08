# FINAL BETA GATE CERTIFICATE

> ## ⚠ SUPERSEDED IN PART — 2026-08-08 (updated same day)
>
> The §1 verdict below (**CONDITIONAL GO**) is **withdrawn**. Current status:
>
> # CREDIT-RACE BLOCKER = CLOSED (database verified) · BETA = GO ELIGIBLE pending one build check
>
> **Migration 107 is independently verified applied in production** — 6/6
> read-only catalog checks, 2026-08-08. The credit race is closed at the
> database layer, the atomic refund functions exist, and `CREATE OR REPLACE`
> did not reopen the migration-102 lockdown.
>
> **One item remains before an unconditional GO**, and it is deliberately not
> rounded away: three CRITICAL/HIGH findings from this operation are
> **application-code** fixes (`0561e6c`, `4e6e4f1`), not SQL. Chief among them,
> `consume()` used to route the *dominant* 1-credit price to `deduct_credit`,
> whose failure return is `0` and never `-1` — so if production runs a build
> older than `0561e6c`, that path stays exploitable **despite** migration 107.
> Verified by opening `GET /api/credits-debug` on production: a `credit_rpc`
> key means the fixed build is live; the old `deduct_credit_rpc` key means it
> is not. See `PRODUCTION_MIGRATION_107_VERIFICATION.md`.
>
> The historical NO-GO reasoning is retained below for the record.
>
> ---
>
> ### (historical, 2026-08-08 earlier) BETA GATE = NO-GO
>
> Read-only production catalog verification on 2026-08-08 established that the
> F5 credit-race fix this certificate treated as "code complete, pending one
> migration" was **never deployed** — the fix had been written into an
> already-applied migration, which produces no artifact for an operator to
> run. The vulnerable function body was confirmed live in production.
>
> Subsequent adversarial and second-order review then found the fix, once
> written correctly, still left the **dominant** code path open
> (`n_credits == 1` → `deduct_credit`, whose failure return is `0`, never
> `-1`, making the 402 unreachable), plus a second unlimited free-credit
> primitive reachable by any authenticated user (`/api/credits-debug`).
>
> All are now fixed in code. What remains outstanding is **evidence**:
> migration 107 has been reported applied but not yet independently verified
> against the production catalog.
>
> | Item | Verified |
> |---|---|
> | Migration 102 (RPC lockdown) | ✅ independently verified, catalog |
> | Migration 103 (profiles columns) | ✅ independently verified, catalog |
> | Migration 107 (credit race) | ❌ founder-reported only |
>
> Authoritative current documents:
> `BETA_GATE_BLOCKER_CLOSURE_REPORT.md` · `CREDIT_SYSTEM_FORENSIC_AUDIT.md` ·
> `CREDIT_RACE_TEST_MATRIX.md` · `CREDIT_REFUND_CHAOS_REPORT.md` ·
> `CREDIT_SECOND_ORDER_AUDIT.md` · `PRODUCTION_MIGRATION_107_VERIFICATION.md`
>
> The sections below are retained unaltered as the historical record of the
> 2026-08-08 Final Beta Gate operation. They are not rewritten to pretend the
> blocker never existed. Sequence actually observed:
> `DISCOVERED → FIXED IN CODE (wrong mechanism) → NOT DEPLOYED → PRODUCTION
> VERIFIED FAIL → FIXED IN NEW MIGRATION → ADVERSARIALLY ATTACKED → 2 MORE
> CRITICALS FOUND → FIXED → awaiting PRODUCTION VERIFICATION → BLOCKER CLOSED`

---


**Operation:** Final Beta Gate — Zero-Trust / Production Readiness
**Date:** 2026-08-08
**Scope:** Vindex AI, full codebase, post-Program Phoenix / Phoenix Closure
**Mandated central question:** *Would you trust a real lawyer to use Vindex AI
tomorrow with real cases and real client data?*

---

## 1. Executive Verdict

**Conditional GO.**

Vindex AI is safe enough, coherent enough, and reliable enough to expose to a
small closed beta of real lawyers with real cases **once the two conditions
in §17 are met** (one migration run, one credential provided — both already
requested, neither newly introduced by this operation). Absent those two
conditions, the answer is narrower: safe for beta with the explicit
understanding that one CRITICAL billing-integrity fix is not yet live in
production, and two long-standing infrastructure verifications remain
unconfirmed.

This is not a rounded-up "the tests are green" verdict. 18 real, previously
undiscovered defects were found and fixed this operation, including one
CRITICAL (free AI usage under concurrent load) and six HIGH severity
(Genome data loss, RAG knowledge-base corruption, cross-screen truth
divergence on hearings, a stale-data race in the primary case-load path, a
false compliance claim on client deletion, silent credit loss on AI
failure). Four real gaps remain open, honestly disclosed as
infrastructure-blocked, not force-closed to make this report look cleaner.

## 2. Test Baseline

- **Start of this operation:** 3,393 passed, 1 skipped, 0 failed (Phoenix
  Closure's own certified baseline, commit `e9e4021`).
- **End of Phase 8 (all fixes applied):** 3,443 passed, 1 skipped, 0 failed.
- **Net new tests added this operation:** 50 (regression + adversarial
  coverage for all 18 fixes).
- Git history: `d5fe903` (batch 1, 11 findings), `c1f582b` (batch 2, 6
  findings), `040edc2` (batch 3, F9) — all pushed to `main`.

## 3. Teams Used (Phase 1)

10 independent forensic teams, each briefed identically (zero-trust,
"try to break Vindex AI," no team allowed to assume another's conclusion),
covering all 20 lettered domains from the masterprompt:

| Team | Domains | Key finding |
|---|---|---|
| A | Security, tenant isolation | F1: tmp_ namespace ownership gap |
| B | Auth, Billing | F5: CRITICAL credit-race |
| C | Data integrity, Concurrency | F16: staging_approve double-submit |
| D | AI safety | F2: Genome data-loss guard gap |
| E | Case Genome, cross-module truth | F11: hearing_cc risk divergence |
| F | Failure injection, ingestion, event bus | F6: no-refund-on-failure |
| G | Notifications, frontend/backend contract | F18: CRITICAL Workspace leak |
| H | UX workflow, scale/performance | F22: Digital Twin disclosure gap |
| I | Deployment, audit trail, session/cache | F12: false audit-chain claim |
| J | Full lawyer-day workflow trace | F26: hearing reschedule silence |

**Methodology honesty note:** these were code-level forensic audits (static
reading + targeted, mocked unit-test reproduction of each hypothesized bug),
not live execution against a running Vindex AI instance with real
Supabase/OpenAI/Pinecone credentials — this agent has never had access to
those. Every fix in this certificate was verified by writing a test that
reproduces the failure mode against the actual production code path with
dependencies mocked at the I/O boundary, then confirming the fix closes it
and the full suite stays green. This is the same verification standard
every prior mission in this engagement (Program Phoenix, Black Swan, Living
System, Singular Intelligence, One Truth, Single Brain) used, for the same
structural reason. It is real verification, not merely code review — but it
is not the same as live traffic against production infrastructure, and
Phases 2/6 below are scoped accordingly.

## 4. Attack Classes Covered

Tenant-isolation IDOR, TOCTOU credit races, silent-write-over-good-data,
double-submit/idempotency, cross-screen truth divergence, missing
audit-chain wiring, unguarded GPT output fields, missing failure-path
refunds/disclosures, notification-group partial-write, stale-cache/race in
primary UI load paths, cap/truncation invisibility, hardcoded-secret
fallback.

## 5-7. Findings: Discovered / Fixed / Not Fixed

**29 findings discovered** (10 teams' full reports preserved in the working
findings tracker). **18 fixed** this operation (2 CRITICAL, 6 HIGH, 9
MEDIUM/MEDIUM-HIGH, 1 LOW) — see commit messages `d5fe903`, `c1f582b`,
`040edc2` for the itemized list with file:line and test names.

**11 not fixed**, each with an explicit, non-euphemistic reason:

| ID | Why open |
|---|---|
| F3 | Prompt-injection defense on free-text Genome fields needs a multi-template hardening pass across ~12 prompts — same class Phoenix Closure's `-014` already left open for the identical reason. |
| F8 | 6 of 8 Case-Evolution event types lack a missing-event reaper — the acknowledged remainder of Phoenix Closure's own `-042`. Confirmed live-reachable from the highest-traffic path (document upload) this operation, raising urgency, not changing disposition. |
| F9 group residuals | F10 (creation dedup check-then-insert window) already disclosed as a narrowed-not-closed limitation by 3 prior missions; no new information this operation. |
| F13 | Documented, not fixed — `predmet_delete`/`dokument_delete` are reserved `AUDITABLE_ACTIONS` entries with no live endpoint yet; comment added so a future implementer doesn't miss the wiring requirement. |
| F15 | Auth tokens in `localStorage` — standard Supabase-JS SPA default, not a bounded fix (would require httpOnly-cookie auth architecture). Disclosed as accepted risk. |
| F23 | Hard-refresh case-context loss needs a `#predmet=<id>` URL scheme touching core navigation/init — adjacent to the F19 case-switch race just hardened; changing it without dedicated adversarial testing risks reintroducing that bug class. Next-mission-sized. |
| F24 | Case Commander's cap-disclosure gap is dormant — confirmed no live frontend caller exists yet (standing finding from 2 prior missions). Becomes urgent only once wired up. |
| Migrations 102/103 | **Not new to this operation** — outstanding since Operation Black Swan (2026-08-02). `SUPABASE_DB_URL` (read-only) requested repeatedly across at least 4 subsequent missions, never provided. Resurfaced here per standing instruction to keep resurfacing it. |

## 8. Security Verdict

**No exploitable CRITICAL/HIGH tenant-isolation vulnerability remains
undisclosed.** F1 (tmp_ namespace cross-tenant document read) and F18
(cross-screen deadline leak, not tenant-isolation but a real trust breach)
both fixed and tested. No privilege escalation found by any of the 10
teams. No private-context leakage found. F15 (localStorage tokens) is a
disclosed structural risk, not a new finding requiring action before beta.

## 9. AI-Safety Verdict

**No unguarded critical AI output reaches a lawyer unlabeled.** F11 closed
the 4th recurrence of the "guarded headline field, missed sibling field"
pattern (hearing_cc's `risk_breakdown.overall`). F4 closed the last 3 AI
surfaces (drafting, CIO, case_dna) missing the `ai_generated` disclosure
marker. F3 (prompt-injection defense) remains open — this is the one
AI-safety item genuinely deferred, not closed; it does not let GPT silently
become a source of truth (all deterministic fields remain guarded), but a
crafted document's free-text could still influence Genome narrative fields
without a defense-in-depth prompt hardening pass.

## 10. Data-Integrity Verdict

**No destructive failure path found undisclosed.** F2 (Genome overwrite on
extraction failure) and F16 (duplicate Pinecone ingestion) were the two
real data-corruption risks found; both fixed and adversarially tested
(double-approve race explicitly reproduced and closed). No silent data loss
found by any team beyond these two, both closed.

## 11. Reliability Verdict

**No critical race/retry-duplication/false-success remains unfixed.** F16,
F17, F19 (all races) and F6, F9 (both false-success-adjacent silent
undercounts) all closed with adversarial reproduction tests. F8 (event
reaper coverage) is the one reliability gap left open, disclosed above.

## 12. Legal Workflow Verdict

Deadlines/hearings: F26+F27 close the specific reschedule-silence and
archived-case-leak bugs Team J's full lawyer-day trace found — Dashboard
and Workspace now agree about the same hearing after a reschedule, and
closed cases no longer appear on the Calendar or in the weekly digest.
Evidence grounding: no gap found by any team (RAG grounding confirmed live
for both drafting paths). Case state coherence: F18's Workspace leak was
the one real gap, closed. Provenance: F4/F20 close the remaining disclosure
gaps.

## 13. Billing Verdict

**F5 is the headline item and is NOT fully closed in production yet** — see
§17. No other duplicate-charge or free-privilege-escalation path found by
any team. F6 closes the one silent-credit-loss-on-failure gap found.

## 14. UX Verdict

F22 (Digital Twin disclosure), F7 (storage-write disclosure), F20 (4
backend disclosure fields with no frontend consumer), F21 (grouped
notification partial mark-read), F25 (dashboard cap disclosure) all closed.
F23 (hard-refresh context loss) is the one UX gap left open, disclosed
above — real but bounded to a specific, known-recoverable-by-navigation
scenario (not a data-loss or silent-wrong-data risk, a "have to click back
in" annoyance).

## 15. Scale Verdict

**Not independently load-tested this operation** (no live infrastructure
access — see §3's methodology note). F25 makes Dashboard's primary case
query's behavior at scale explicit and disclosed (1000-case cap, `.order()`
now deterministic) instead of relying on an invisible PostgREST default.
F24 (Case Commander's own cap) remains undisclosed but dormant (no live
caller). No new scale characteristics measured; this is a known,
carried-forward limitation of every mission in this engagement, not new
here.

## 16. Full-Suite Results

Phase 10 mandated double-run, back-to-back, zero file edits between runs:

- **Run 1:** 3,443 passed, 1 skipped, 0 failed (357.60s)
- **Run 2:** 3,443 passed, 1 skipped, 0 failed (372.42s)

**Exact match. No nondeterminism observed.**

## 17. Remaining Founder Decisions / Actions Required

1. **Run the updated `migrations/smart_contract_analyses.sql` against the
   live database.** This is the ONLY step remaining to close F5 (CRITICAL)
   in production — the code fix is complete, tested, and pushed, but per
   this engagement's standing rule the agent drafts migrations and never
   applies them. Until this runs, the credit-race F5 describes is still
   live in production.
2. **Provide `SUPABASE_DB_URL` (read-only)** to allow independent
   verification of migrations 102/103's live effect — requested across at
   least 5 prior missions since Operation Black Swan (2026-08-02), still
   outstanding.
3. Five founder product decisions carried forward, unrelated to this
   operation's own findings (from Phoenix Closure, still open):
   CIO 40-case cap size/ordering; per-feature `cooldown_seconds` values;
   autosave/draft-recovery architecture investment; upload progress-bar
   investment; Memory Graph/Firm Memory UI-or-retire decision.

## 18. Remaining Infrastructure Dependencies

F3 (prompt-injection hardening pass), F8 (event-reaper coverage design),
F23 (deep-link URL-state architecture) — each named in §5-7 with its own
specific scope, none blocking beta, all recommended as the next mission's
starting point.

## 19. GO / NO-GO

**GO for closed beta**, conditioned on founder action item #1 in §17 being
completed before real client credits/billing are exposed to real users (the
code is safe to deploy immediately; the database is not yet in the safe
state the code assumes until that migration runs). Item #2 does not block
beta — it blocks *independent verification* of an already-founder-reported-
resolved item, a separate and lower-priority thread.

## 20. Final Statement

The goal was never to prove Vindex AI is perfect — 11 items remain
honestly open. The goal was to prove it is safe enough, coherent enough,
reliable enough, and useful enough to expose to real lawyers, having
genuinely tried to break it first. Ten independent teams tried. Eighteen
real ways to break it were found and closed, each with a reproduction test
that fails without the fix and passes with it. Four real ways remain open,
named, and scoped for the next mission — not hidden inside a passing test
count.

**Would you trust a real lawyer to use Vindex AI tomorrow with real cases
and real client data? Yes — once the one migration in §17 runs.**
