# Security Review — Word Add-in Task 01 Authentication

**Author (role):** Security & Privacy Architect
**Date:** 2026-11-01
**Gate state:** CONDITIONAL
**Scope:** Design review only; no source implementation, tests, network, live auth, AI calls, production access, or migrations.

## Conclusion

No Critical or High finding blocks Task 01 authentication-only source implementation. Conditions below must be satisfied before their stated closure, exposure, migration, or pilot gate. Adding a Word analysis route changes the assessment and must first meet Task 02 gates.

## Evidence and conditions

1. **MEDIUM — Legacy bearer remains stored after upgrade.** The prototype stores vindex_auth_token in Office roaming settings or localStorage (integrations/word_addin/adapter.js:26,43-68), and startup reads it (taskpane.html:304-306). Add startup cleanup in both stores before displaying auth state; never read/reuse the token and await Office roaming save completion. Seed both stores and prove cleanup precedes signed-out UI. **Effect:** Task 01 implementation may start; Task 01 cannot close until this is implemented and verified.

2. **MEDIUM — Pre-auth IP limit is bypassable under SEC-048.** The route IP key trusts leftmost X-Forwarded-For (shared/rate.py:47-67). Varying forged XFF can create fresh buckets and flood provider verification. Keep limits as defense in depth, but before public exposure/pilot prove trusted non-spoofable client-IP enforcement or an equivalent pre-auth control, and test that forged XFF cannot reset it. **Effect:** source implementation may proceed; public exchange exposure/pilot is blocked until verified.

3. **MEDIUM — Word CSP script policy is unspecified.** Global CSP permits unsafe-inline (api.py:1242-1247), and taskpane has inline JavaScript (taskpane.html:187). Define Word script-src without unsafe-inline and unsafe-eval; move taskpane/commands scripts to same-origin files or use a nonce/hash. Verify effective headers, Office.js, response chains, and framing on each claimed host. Unsupported hosts remain unclaimed. **Effect:** source work may proceed; host support and pilot claims are blocked until verified.

4. **MEDIUM — Session retention is unspecified.** Define expiry cleanup, revoked-row retention, auth.users deletion, and account-erasure handling before migration authoring. Database Architect approval remains required. Do not retain document text in the session table or audit metadata. **Effect:** blocks migration authoring and pilot until decided/reviewed.

5. **HIGH future gate — Per-attempt claims must cover real Word egress.** Existing Ambient analysis uses @llm_retry and clients without explicit max_retries=0; retrieval may call OpenAI embeddings/completions, Pinecone and optional Cohere (services/ambient_analyzer.py:59-90; app/services/retrieve.py:484-502,778-782,1433-1544). Add a claim-aware wrapper before every text-bearing provider attempt, including retries; disable hidden retries. Test claim count equals provider-call count and cover revocation before dispatch, between retries, and after dispatch. **Effect:** does not block Task 01 auth-only implementation; blocks Task 02 analysis/rewrite exposure.

6. **MEDIUM future gate — Retrieval may log legal text.** Empty-result and error paths log query[:60] (app/services/retrieve.py:990,994), and Ambient passes paragraph text into retrieval (services/ambient_analyzer.py:80-90). Redact/suppress these logs on Word paths; capture logs in empty/error tests and assert a unique synthetic document substring never appears. Check the security gap register before Task 02. **Effect:** blocks Task 02 AI exposure until fixed and verified.

7. **MEDIUM — Account and anomaly limits are process-local.** Gunicorn defaults to one worker, but WEB_CONCURRENCY and replicas are unknown (api.py:1064-1108; gunicorn.conf.py:6-8). Before pilot, prove one worker or obtain an approved shared counter. **Effect:** source implementation may proceed; pilot gate.

## Additional controls

- Keep matter routes out of Task 01. PermissionService enforces feature rights; it does not establish matter/document ownership.
- Reuse registered audit actions login_success, login_failed, and logout with channel=word and secret-free metadata; do not reuse the failed-login helper that writes a token prefix (shared/audit_immutable.py:107,301; shared/deps.py:324-356).
- Use the dedicated strict verifier, provider-confirmed identity, hash-only opaque sessions, TLS, per-request revocation checks, and scoped Word session logout. Do not claim database encryption at rest without evidence.
- Recheck PR #66 state before integration. Do not modify shared/permissions.py, central AI budget/usage modules, migration 146, or live settings.
- Existing public security claims have stale SlowAPI registration language and do not support a broad abuse-protection claim; no new public claim is authorized by this review.

## Verification

The reviewer read canonical rules, operating protocol, review gates, Security Architect charter/template, trust blueprint, finding lifecycle, gap register, public claims, AI governance rules, and relevant source. No tests were run and no files were changed by the reviewer.