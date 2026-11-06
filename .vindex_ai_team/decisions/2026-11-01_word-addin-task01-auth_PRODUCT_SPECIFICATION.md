# Product Specification - Word Add-in Task 01: Secure Authentication

**Author (role):** Product Strategist
**Date:** 2026-11-01
**Status:** Approved implementation contract; Database lifecycle confirmed, migration sequencing pending PR #66

## User Problem

The Word pane asks lawyers to paste a Vindex bearer and persists it in Office roaming settings or localStorage. Evidence: `integrations/word_addin/taskpane.html:167-169` and `adapter.js:26,43-68`. Existing-identity sign-in, no pasted API token, no persistent raw token, and Word-session-only logout are PROVEN by the founder directive. Usage incidence is UNKNOWN.

## User Story

As a lawyer using Word, I want to authenticate with my existing Vindex identity and end only this Add-in session when I log out, so I can use authorized Vindex functions without copying or storing an API token.

## Acceptance Criteria

1. Use existing Vindex/Supabase identity; no API-token field in taskpane.
2. Sign in through a same-origin Office dialog. Create an opaque session bound to server-verified identity/expiry; hold raw session in pane memory only.
3. No credential in URLs, documents, persistent browser storage, roaming settings, application/access logs, or audit metadata.
4. Word exchange requires provider success and validates signature, exact issuer/audience, nonempty subject, and present/future expiry. Do not call existing verifier helpers unchanged. Provider rejection/outage and claim uncertainty fail closed. Session expiry is at most verified source expiry or one-hour cap.
5. Missing/expired/revoked/malformed/tampered tokens, wrong issuer/audience, missing expiry, unverifiable tokens, and client-supplied identity/expiry fail closed.
6. The global rate-limit middleware must skip Bearer parsing only on the exact /api/word/ path segment, then continue through normal route/IP limiting; paths such as /api/wordsmith keep ordinary handling. The Word namespace contains only Word routes, and protected routes require a verified opaque Word session. After provider verification and before issuing a session, use the existing general API user bucket keyed by provider-confirmed user ID. After Word-session verification, enforce user policy before side effects: session management and future non-AI routes use the existing general API bucket; analysis and rewrite use the existing AI user bucket and anomaly record/check before analysis/provider work. Route operation classes are explicit, and the account-wide user bucket is shared across sessions and IPs within one worker. Because the existing limiter is process-local, a controlled pilot must prove single-worker operation or use an approved shared account counter before claiming cross-worker enforcement; deployed worker count is UNKNOWN. Do not trust client-supplied identity. Existing non-Word behavior stays unchanged.
7. Check Dialog Origin 1.1 before opening auth. Require exact origin and one-time nonce. Missing/wrong origin, wrong nonce, malformed message, or unsupported host yields no session.
8. Logout immediately clears session/results, aborts requests, stops monitoring, and suppresses stale callbacks. Revoke only this Word session; report unconfirmed revocation. Keep global web logout unchanged.
9. Every outbound provider attempt in Word operations—including embeddings, completions, optional reranking, and each retry—requires an atomic live-session claim immediately before the attempt. Disable hidden SDK retries; revoked-session failures do not retry. Recheck session before returning results.
10. If logout revocation commits before a provider-attempt claim, that attempt does not happen. A claim committed first may finish remotely, but its result never displays/applies after logout.
11. Instrument existing verifier helpers; valid, malformed, wrong-claim, and provider-outage exchanges must call none of them. Capture app/access/audit logs and assert no JWT or opaque-token substring.
12. Tests cover claims, provider failure, callback origin/nonce, repeated login, multiple panes, exact namespace-boundary and middleware verifier-call behavior, retained SlowAPI IP/route limits, general API versus AI user buckets, AI anomaly checks before analyzer/provider work, shared account buckets across IPs/sessions, token leakage, legacy-token cleanup, Word CSP, and logout before dispatch, between retries, and after dispatch.
13. Existing web login/global logout remain unchanged. Office mocks are reported separately from real host evidence.

14. On startup, clear legacy vindex_auth_token from Office roaming settings and localStorage before showing any auth state. Never read or reuse the value. Await roaming save completion; cleanup failure fails closed. Tests seed both stores and assert cleanup completes before signed-out UI.
15. Word script-src excludes unsafe-inline and unsafe-eval. Move taskpane and commands scripts into same-origin files or use a verified nonce/hash; test effective headers and Office.js on each claimed host.
16. Before public exchange exposure, prove the pre-auth limiter cannot be reset with forged X-Forwarded-For. Before a controlled pilot, prove single-worker operation or use an approved shared account counter. These current deployment properties are UNKNOWN.
17. Before Task 02 transmits selected legal text, suppress/redact retrieval query snippets from Word-path logs and test empty-result/error paths with a unique synthetic document string.
18. Database lifecycle contract: retain revoked rows until original expiry; delete expired rows through the existing daily retention job and surface cleanup failures (nominal maximum 24 hours after expiry when the job succeeds); on the existing soft account-erasure path revoke all Word sessions before reporting success and fail closed on revocation error; require hard Auth deletion to remove Word rows first under ON DELETE RESTRICT. The Database Architect confirmed these exact choices on 2026-11-02. Migration naming/authoring remains blocked until PR #66 migration 146 is resolved, this branch is synchronized with canonical main, and the next unused slot is verified.
## Priority and Success

P1 as a prerequisite to the founder-authorized Word workflow (judgment based on the directive, not measured frequency). Acceptance tests must pass and adversarial review must find no credential persistence or callback-origin bypass. Controlled sideload later verifies sign-in/out usability. No pilot rate is claimed.

## Out of Scope

Matter selection/retrieval authorization policy, legal-source verification, rewrite UX, release manifest, AppSource, production migration execution, live auth settings, paid AI calls, and main web-login changes. Per-attempt session claims govern only Word operations.
