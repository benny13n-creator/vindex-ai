# Vindex AI — Executive Security Summary

**Prepared:** 2026-07-23, for technical due diligence review.
**Standard applied:** every claim below is either verified against this repository's code and test suite (cited), or explicitly marked as a disclosed open item. No claim in this document asserts something the underlying evidence doesn't support — where the honest answer is "not yet," this document says so, on the view that a disclosed gap is more credible to a real technical reviewer than an inflated claim that doesn't survive a second look.

---

## Audit Journey

Vindex AI commissioned an adversarial, evidence-only security audit of its own codebase (5 independent investigation tracks, `docs/security/SECURITY_DUE_DILIGENCE_REPORT.md`). The audit found 30 initial findings and scored the platform **45/100**, driven primarily by two confirmed CRITICAL, live findings and one CRITICAL AI-safety gap.

Since that baseline, four focused engineering sprints closed or substantially mitigated the highest-severity items:

| Sprint | Findings closed | Result |
|---|---|---|
| P0 | SEC-001 (cross-tenant data access), SEC-002 (GDPR message accuracy), SEC-003 (AI prompt-injection defense) | All 3 closed and independently re-verified |
| P1/P2 | SEC-007 (file-upload DoS), SEC-008 (XSS, confirmed instance + defense-in-depth), SEC-023 (documentation accuracy) | All 3 closed |
| P3 | SEC-005 (rate-limiter resilience) | Closed |
| P4 (this document) | SEC-009 (bulk-import PII encryption) | Closed. SEC-031's remediation migration written and tested — **not yet run in production**, see below |

**Recomputed score, same 11-category methodology as the original audit: 61/100** (full category-by-category breakdown: `docs/security/SECURITY_DUE_DILIGENCE_REPORT.md`, "Score Update" and "Score Update 2" sections). This is a genuine, verified improvement of +16 points from the 45/100 baseline — not a target number, and deliberately not inflated to reflect the amount of engineering effort in this last sprint rather than the amount of actual risk reduced. That distinction matters enough to state plainly:

**SEC-031's migration is written, is mechanically verified to match the approved, peer-reviewed plan exactly (15 tests), and is ready to run — but it has not been run.** `migrations/077_sec031_restrict_auth_users_cascade.sql` converts the dangerous `auth.users` cascade chain (below) from `CASCADE` to `RESTRICT` for the 19 constraints identified as necessary and sufficient to protect the full ~56-table blast radius. This development environment has no database access of any kind (no Docker, no local Postgres, no production credentials), so nothing in this cycle of work could execute it or confirm its effect on the live schema — that step is, deliberately, the founder's own to perform, after their own read-only verification query confirms production's actual current constraint state matches what this migration assumes. **The score reflects this honestly: SEC-031 contributed almost no score movement this cycle**, because the risk it measures — a live database that can still cascade-delete case and financial records today — is unchanged by writing correct code that hasn't been run yet. The score movement that did happen this cycle came from SEC-009, which this session could fully verify end-to-end (the fix, its test, and its effect are all containable within this codebase and test suite, no external system required).

**The disclosed path from 61 to 90+** requires, in order of materiality: (1) the founder running `migrations/077_sec031_restrict_auth_users_cascade.sql` against production after their own Production Reality Gate check — this single event is worth the largest remaining score movement, comparable to what closing SEC-003 contributed to AI Security; (2) a founder-approved formal Data Retention Policy (SEC-002's underlying, still-open policy question); (3) confirming SEC-005's Redis capability is actually active in production, not just present in code; (4) completing the full XSS sweep beyond the confirmed instance already fixed. None of these remaining items are architecturally hard — the audit's own consistent finding across every sprint is that this codebase's *patterns* for doing things correctly are already sound; what was missing was consistent application, not competent engineering.

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

**A related, more severe finding discovered during this work, disclosed in full: SEC-031.** Deep schema analysis found that `ON DELETE CASCADE` foreign keys connect `auth.users` to roughly 56 tables, directly or transitively, including case files, evidence, court-hearing records, and billing/invoice data. A direct deletion of a user at the Supabase Auth layer (not through this application's own GDPR endpoint, which does not touch `auth.users` at all) would cascade-delete all of that data irreversibly. This is **not a bug introduced by this work** — it is a pre-existing schema characteristic this work discovered while investigating SEC-002. The remediation has been fully designed, independently peer-reviewed (a second, adversarial model pass found and closed 3 real gaps in the first draft of the plan), and — as of this update — **written as a real, executable migration file** (`migrations/077_sec031_restrict_auth_users_cascade.sql`) with 15 tests mechanically confirming it matches the approved plan exactly. **What remains, stated precisely rather than rounded up: the migration has not been run against production.** This development environment has no database connectivity of any kind, so nothing in this workstream could execute or verify it against the live schema — running it, after the founder's own read-only confirmation that production's actual constraint state matches what the migration assumes, is the one remaining step, and it is deliberately not something this work claims to have done. Full detail: `docs/security/SEC031_IMPACT_ANALYSIS.md` and the accompanying migration-plan documents in the same directory, including `migrations/077_sec031_restrict_auth_users_cascade.sql` itself. This is disclosed here specifically because omitting it, or rounding "code is ready" up to "risk is closed," would make the "GDPR & Compliance" section of this document misleading.

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
| New findings discovered since the original audit? | Yes, disclosed: SEC-031 (unmitigated in production; remediation migration written, tested, and ready — execution pending), SEC-033 (a smaller, related schema-integrity pattern, scoped as a future initiative) |
| Can this system honestly be called "enterprise-grade secure" today? | Not yet — SEC-031's underlying risk is unchanged until the migration actually runs; the kind of finding a rigorous buyer's technical review would flag as blocking, disclosed here rather than after the fact |
| Is the trajectory real? | Yes — 45→61 reflects genuine, tested, re-verified fixes to the highest-severity items, achieved across four scoped sprints in the timeframe documented in `docs/security/P0_FIX_VERIFICATION.md` and `docs/security/P1_P2_FIX_VERIFICATION.md`, using a consistent methodology (adversarial peer review for architecturally significant changes, mandatory regression tests, explicit verified-vs-assumed tracking, and — this update — declining to credit score for code that hasn't been run yet) that is now the project's standing engineering practice, not a one-time audit response |
