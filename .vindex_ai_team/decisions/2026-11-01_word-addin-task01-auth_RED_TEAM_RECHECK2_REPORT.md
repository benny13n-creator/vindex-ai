# Red Team Re-review - Word Add-in Task 01 Authentication

**Author (role):** Red Team / Devil's Advocate (fresh, non-fork review)
**Date:** 2026-11-01
**Scope:** Third design iteration and current source. No files were edited and no tests, live auth, AI, production, or network services were used.

## Verdict

**BLOCKING** — one MEDIUM design contract gap remains.

## RT-07 — Global API rate middleware still invokes the excluded verifier before Word route dispatch

**Severity:** MEDIUM

**Evidence:** The technical design forbids using `shared.deps::verify_token_local` on the Word exchange path (`TECHNICAL_DESIGN.md:15`). However, `api.py:1168-1180` has `user_rate_limit_middleware` process every `/api/*` request with an Authorization Bearer header and call imported `verify_token_local(token)` before route dispatch.

**Failure scenario:** A standard Bearer-token exchange reaches the existing verifier before the dedicated Word verifier. The helper does not authorize the request, so this is not an authentication bypass, but it violates the no-helper contract and adds an unaddressed token parsing/logging path.

**Smallest correction:** Add a narrowly scoped `/api/word/*` carveout before the middleware's Bearer parsing branch. Retain route/IP limits. After Word-session verification, apply user limits using server-derived session identity. Keep all non-Word routes unchanged. Avoid moving the credential to a body merely to evade middleware.

**Acceptance:** Instrument `api._verify_token`, `shared.deps._verify_token`, and `verify_token_local`; valid, malformed, wrong-claim, and provider-outage Word exchanges invoke none. Capture logs and assert no JWT/opaque-token substring. Verify IP/route limits still apply to Word auth, per-session limits apply after session authentication, and unrelated routes preserve current behavior.

## Other requested checks

At the design level, the previous two HIGH findings are now addressed: Word HTML entries replace the inherited CSP, remove X-Frame-Options only on Word pages, preserve Supabase `connect-src`, and keep unrelated routes unchanged; each external Word provider attempt/retry requires a live-session claim, hidden SDK retries are disabled, revocation is non-retryable, and outputs are suppressed after logout. Dialog Origin 1.1 runtime gating and origin/nonce fail-closed handling are specified. The verifier contract and `shared/permissions.py` avoidance are explicit.

The current code still has no Task 01 source implementation. The analyzer/retrieval pipeline has retries and optional Cohere-to-GPT fallback; all actual Word call paths must be covered by the promised guards before they are exposed. No files were changed by this reviewer and no tests were run.
