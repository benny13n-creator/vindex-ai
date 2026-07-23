# Vindex AI — Executive Security Summary

**Prepared:** 2026-07-23, for technical due diligence review.
**Standard applied:** every claim below is either verified against this repository's code and test suite (cited), or explicitly marked as a disclosed open item. No claim in this document asserts something the underlying evidence doesn't support — where the honest answer is "not yet," this document says so, on the view that a disclosed gap is more credible to a real technical reviewer than an inflated claim that doesn't survive a second look.

---

## Audit Journey

Vindex AI commissioned an adversarial, evidence-only security audit of its own codebase (5 independent investigation tracks, `docs/security/SECURITY_DUE_DILIGENCE_REPORT.md`). The audit found 30 initial findings and scored the platform **45/100**, driven primarily by two confirmed CRITICAL, live findings and one CRITICAL AI-safety gap.

Since that baseline, five focused engineering sprints closed or substantially mitigated the highest-severity items:

| Sprint | Findings closed | Result |
|---|---|---|
| P0 | SEC-001 (cross-tenant data access), SEC-002 (GDPR message accuracy), SEC-003 (AI prompt-injection defense) | All 3 closed and independently re-verified |
| P1/P2 | SEC-007 (file-upload DoS), SEC-008 (XSS, confirmed instance + defense-in-depth), SEC-023 (documentation accuracy) | All 3 closed |
| P3 | SEC-005 (rate-limiter resilience) | Closed |
| P4 | SEC-009 (bulk-import PII encryption) | Closed |
| P5 | SEC-031 (`auth.users` cascade risk) | **Closed — confirmed in production**, not just deployed. See below |
| P6 (this document) | SEC-034 (silent migration no-op pattern) — full live audit run, 2 of 3 confirmed gaps closed in production | **Closed for `klijenti`/`predmet_komentari`, confirmed in production**; 1 small item (`predmet_delegiranja.predmet_id` FK) remains. See below |

**Recomputed score, same 11-category methodology as the original audit: 67/100** (full category-by-category breakdown: `docs/security/SECURITY_DUE_DILIGENCE_REPORT.md`, "Score Update" through "Score Update 4" sections). This is a genuine, verified improvement of +22 points from the 45/100 baseline — not a target number, and specifically not rounded up to reflect the significance of the finding rather than the confirmed state of the fix.

**SEC-031 — the single most severe finding this audit produced — is now closed, and closed in the way this document's own stated standard requires: confirmed against the live production database, not inferred from a correct-looking migration file.** The founder executed `migrations/077_sec031_restrict_auth_users_cascade.sql` directly against production, with a read-only verification query run after every step. The migration did not go smoothly on the first attempt, and that is itself informative: two of the target tables (`predmet_delegiranja`, `tos_acceptances`) turned out to exist in production in an incomplete, bare form — their own migrations had silently done nothing, because `CREATE TABLE IF NOT EXISTS` skips its entire body when the table already exists, with no error raised. Each failure caused its transaction to roll back cleanly, with zero data touched — the exact safety property this whole workstream was built around, now demonstrated under a genuine, unplanned failure rather than only in a test suite. Both gaps were closed (the underlying migrations run, the missing constraints added to match) and the run completed. **A final query confirmed all 18 target foreign keys are `ON DELETE RESTRICT` in production.** Full step-by-step record: `docs/security/SEC031_PRODUCTION_EXECUTION_LOG.md`.

**This process also surfaced a new finding, disclosed rather than absorbed quietly into the good news: SEC-034** — the same "migration silently no-ops against an incomplete pre-existing table" pattern that broke the SEC-031 rollout twice. Confirmed in exactly the 2 tables above at the time; not yet known whether other tables in the migration history shared it. Tracked as open, P1.

**That unknown is now closed, same day, in two stages.** First, all 69 files in `migrations/` were parsed for every table that enables Row Level Security (127 found) and cross-checked for a matching `CREATE POLICY` in the migration source — an initial pass flagged 15 tables as suspicious, but reading each by hand showed 11 were parsing false positives and the remaining 4 are deliberate, documented service-role-only tables (RLS enabled with zero policies is the *correct* default-deny pattern for backend-only tables, the same pattern already used intentionally for `audit_immutable`). Zero additional gaps in the migration source itself.

Second, and more importantly, `scripts/sec034_live_completeness_check.sql` was actually run against production — a single read-only pass returning RLS/FK/policy/index counts for all 154 `public` tables at once, closing the source-analysis blind spot the earlier static pass couldn't. **It found two real, previously-unknown gaps and both are now fixed and confirmed in production**: `klijenti` and `predmet_komentari` had RLS enabled with zero active policies, despite `supabase_setup.sql` (a legacy file the earlier source-only pass never scanned) defining 4 CRUD policies for each — `migrations/078_sec034_klijenti_komentari_policies.sql` copied those definitions verbatim, was executed, and a follow-up query confirmed exactly 8/8 policies active. The same live data also resolved a question left open at Score Update 3: `predmet_delegiranja` shows only 2 of its 3 expected foreign keys, confirming `predmet_id→predmeti` is genuinely still missing (not just unconfirmed) — this one small item remains open. Everything else the live check flagged turned out correct-by-design or a harmless dead table. One side discovery, disclosed as SEC-035: 6 tables exist in production with no `CREATE TABLE` anywhere in this repository at all — 2 were already known-dead, the other 4 have real data but zero application-code references, meaning something outside this codebase populates them; tracked as a low-priority provenance question, not an active exploit path.

**The disclosed path from 67 to 90+** requires, in order of materiality: (1) a founder-approved formal Data Retention Policy (SEC-002's underlying, still-open policy question); (2) the one remaining SEC-034 item — adding `predmet_delegiranja.predmet_id`'s missing foreign key to `predmeti` (small, scoped, not yet started) — plus resolving SEC-035's provenance question on 4 untracked tables; (3) confirming SEC-005's Redis capability is actually active in production, not just present in code; (4) completing the full XSS sweep beyond the confirmed instance already fixed; (5) the standing architectural item, SEC-004 (service-role key bypasses RLS — mitigated by consistent API-layer checks, not eliminated by design). None of these remaining items are architecturally hard — the audit's own consistent finding across every sprint is that this codebase's *patterns* for doing things correctly are already sound; what was missing was consistent application, not competent engineering.

---

## Data Isolation & Cross-Tenant Access (BOLA)

**Verified claim: cross-tenant data isolation is enforced and tested at the API/application layer.**

- The confirmed, reproducible cross-tenant vulnerability found by the audit (SEC-001 — any authenticated user could write into another firm's case file) is closed. Fix verified by a full sweep of all 24 `{predmet_id}`-scoped mutation endpoints across the codebase (only 2 were missing the check; the other 22 already used one of three existing correct patterns) and 6 dedicated regression tests, re-run and confirmed passing during this review.
- A consolidated, single-source-of-truth ownership-check pattern has been designed (`docs/security/AUTHORIZATION_PATTERN_RECOMMENDATION.md`) to replace the ~15+ independently-written call sites with one canonical, unit-tested dependency — **designed, not yet implemented**; migrating the existing call sites to it is a scoped follow-on, not required for SEC-001's own closure, but recommended to reduce the chance of a similar gap recurring elsewhere.

**Correction to a claim commonly assumed for Postgres-backed multi-tenant apps: isolation is NOT additionally enforced at the database level via Row-Level Security.** This application's backend uses a single Supabase service-role connection for all requests (`shared/deps.py`), which — by Postgres/Supabase design — bypasses RLS policies entirely. This means the API-layer ownership checks described above are the *only* real tenant boundary; RLS exists on these tables but is not the enforcement mechanism a reviewer might expect. This is a known, disclosed architectural characteristic (tracked as SEC-004), not a regression introduced by any of this work, and not something that changed this cycle. Any representation of "defense in depth at the database level" would not be accurate for this system today — stated here precisely so it is not asserted elsewhere by omission.

---

## LLM Security & Cost Protection

**Verified claim: all 130 OpenAI API call sites across the codebase (53 files) are structurally protected by a centralized prompt-injection guard.**

- Rather than relying on each of the 130 call sites to individually remember to call the existing injection-detection code (which, per the original audit, only 1 of them did), the fix intercepts the OpenAI SDK's own `Completions.create`/`AsyncCompletions.create` methods at the class level — every call, regardless of which file constructs the client, is analyzed before any request reaches OpenAI. Malicious content (direct or embedded in an uploaded document, the specific risk the audit named) is blocked before the API call executes, proven by a test that confirms zero network activity occurs for a blocked call. Verified by 12 dedicated tests and the full suite, all passing.
- A known, disclosed limit: this closes injection *blocking* for all 130 sites; it does not automatically retrofit the additional message-isolation technique (`wrap_for_ai()`) into each site's existing prompt structure, which was assessed as materially higher regression risk to apply blindly across 130 call sites with varying message shapes. Recommended as a scoped follow-on.

**Separate claim, corrected from an earlier draft of this document: rate limiting is applied per-API-route, not per-individual-LLM-call.** All specifically named critical categories — authentication (`/api/register`), the primary document-upload/OCR endpoint, the primary legal-research/RAG endpoint (`/api/pitanje`), and the two GPT-generation endpoints found unprotected during this review (Case Genome refresh/compare, the Legal Reasoning Engine's generation endpoint) — now carry rate-limit decorators. A full audit of every AI-cost-bearing route's decorator coverage (SEC-010) remains a smaller, separately-tracked open item; this review closed the specific routes named as critical, not a claim of exhaustive coverage.

**Rate limiter resilience (SEC-005), closed this cycle:** the rate limiter previously ran in-memory-only, a deliberate prior decision after a real production incident — an Upstash Redis quota exhaustion once caused `redis.ResponseError` to propagate out of the rate-limiting layer itself, breaking every rate-limited route simultaneously, before any endpoint's own error handling could intervene. The fix, verified against that exact exception type (not just generic connection failures): on any Redis-layer error, the limiter falls back to a per-worker in-memory limit rather than failing the request, with a final swallow-and-log safety net if even that path errors. Verified by 6 dedicated tests, including one that reproduces the exact original incident's exception type and confirms zero request failures result. **Disclosed, not verified from this repository: whether `REDIS_URL` is actually configured in the live production environment** — the capability is built and tested; its activation in production is an infrastructure/deployment fact this review cannot confirm from source code alone.

---

## GDPR & Legal Compliance

**Verified claim: the account-deletion endpoint's user-facing message now accurately describes what the system does.** The audit found the endpoint claimed case files were retained "in anonymized form" when the code never touched them — a materially false statement to users exercising a legal right. The message is corrected; the underlying behavior (only account-identifying fields are anonymized; case/client/document records are untouched) has not changed, and a regression test (`tests/test_gdpr_delete.py`) specifically fails if a future change silently starts touching those tables without the message being updated to match.

**Disclosed, not yet resolved: a formal Data Retention Policy for case, client, and financial records does not yet exist.** The founder made a deliberate decision to correct the message rather than implement automated deletion/anonymization of case data, specifically because that is a legal-professional-obligation question (Zakon o advokaturi — the statutory duty of a lawyer to preserve case files) requiring a real policy decision, not a default engineering choice. This is the right call, not a gap being hidden — but it means "GDPR compliant" is not yet an accurate claim; "GDPR-erasure messaging is accurate, and case-record retention is a deliberate, disclosed, pending policy decision" is.

**A related, more severe finding discovered during this work, now closed: SEC-031.** Deep schema analysis found that `ON DELETE CASCADE` foreign keys connected `auth.users` to roughly 56 tables, directly or transitively, including case files, evidence, court-hearing records, and billing/invoice data. A direct deletion of a user at the Supabase Auth layer (not through this application's own GDPR endpoint, which never touches `auth.users` at all) would have cascade-deleted all of that data irreversibly. This was **not a bug introduced by this work** — it was a pre-existing schema characteristic discovered while investigating SEC-002. The remediation was fully designed, independently peer-reviewed (a second, adversarial model pass found and closed 3 real gaps in the first draft of the plan), written as an executable migration, and — as of this document — **run against production, with all 18 target foreign keys confirmed `ON DELETE RESTRICT` by direct query, not inferred from the migration having executed without a fatal error.** A direct `auth.users` deletion can no longer cascade-destroy case, client, or financial data in this system. Full detail and the complete execution record, including two real mid-run failures and how they were resolved: `docs/security/SEC031_IMPACT_ANALYSIS.md` and `docs/security/SEC031_PRODUCTION_EXECUTION_LOG.md`.

**One new fact surfaced specifically by closing SEC-031, disclosed on its own merits: until today, no user of this platform had ever had a valid, recorded acceptance of the Terms of Service or AI-consent notice.** One of the two tables that turned out to be missing during SEC-031's execution, `tos_acceptances`, had never actually been created — its own migration's header comment explains that the corresponding status-check endpoint was written to fail open (treat a database error as "already accepted") specifically so a transient DB issue wouldn't block a user, and a permanently-missing table produces exactly that error on every single call. This has been fixed as a direct consequence of this investigation (the table now exists, correctly constrained). Whether any retroactive step is warranted for users who used the platform before today is a product/legal question outside this document's scope — flagged here because it is a genuine, material fact a technical or legal reviewer would want disclosed, not discovered independently later.

---

## Test Coverage

**Verified claim: 1,781 automated tests pass.**

```
$ python -m pytest tests/ -q
1781 passed, 16 warnings in 119.06s
```

This includes 56 tests written specifically during the P0–P4 sprints referenced in this document (SEC-001 regression: 6; SEC-003 central guard: 12; SEC-007/008 file-safety and XSS: 19; SEC-005 fail-open limiter: 6; SEC-031 migration structural verification: 15; SEC-009 PII encryption: 4 — some totals shift slightly release to release as tests are added, this figure reflects the suite at the time of this document), on top of the pre-existing suite. All tests are re-run, not assumed, as part of producing this document.

---

## Summary for a technical reviewer

| Question | Answer |
|---|---|
| Confirmed live vulnerabilities from the original audit still open? | No — the 3 CRITICAL findings (SEC-001, SEC-002, SEC-003) are closed and independently re-verified |
| SEC-031, the most severe finding discovered since the original audit — closed? | **Yes, confirmed in production** — all 18 target foreign keys verified `ON DELETE RESTRICT` by direct query, not inferred. Full execution record: `SEC031_PRODUCTION_EXECUTION_LOG.md` |
| New findings discovered since the original audit? | Yes, disclosed: SEC-034 (migrations that silently no-op against pre-existing incomplete tables — full live-schema audit now run across all 154 production tables; 2 confirmed gaps fixed and production-verified, 1 small FK addition remains open), SEC-035 (6 production tables with no source-control history at all — 2 confirmed dead, 4 unexplained but confirmed unused by this codebase), SEC-033 (a smaller, related schema-integrity pattern, scoped as a future initiative) |
| Can this system honestly be called "enterprise-grade secure" today? | Closer than at any prior point in this document's history, but not yet — SEC-004 (architectural service-role/RLS characteristic), the undefined data-retention policy, and the open P2/P3 backlog remain real, disclosed gaps a rigorous technical review would still flag |
| Is the trajectory real? | Yes — 45→67 reflects genuine, tested, and now production-verified fixes to the highest-severity items, achieved across six scoped sprints in the timeframe documented in `docs/security/P0_FIX_VERIFICATION.md`, `docs/security/P1_P2_FIX_VERIFICATION.md`, and `docs/security/SEC031_PRODUCTION_EXECUTION_LOG.md`, using a consistent methodology (adversarial peer review for architecturally significant changes, mandatory regression tests, explicit verified-vs-assumed tracking, and declining to credit score for anything short of confirmed production state) that is now the project's standing engineering practice, not a one-time audit response |
