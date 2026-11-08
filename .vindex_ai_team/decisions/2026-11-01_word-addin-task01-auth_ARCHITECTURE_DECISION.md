# Architecture Decision Record - Word Add-in Task 01 Authentication

**Author (role):** AI CTO / Chief Architect
**Date:** 2026-11-01
**Status:** Red Team FREEZE READY; Security CONDITIONAL; Database lifecycle confirmed; migration numbering held for PR #66
**Finding lifecycle:** Stage 4 - Remediation Candidate

## Problem

The Word prototype accepts and persists a pasted bearer (`integrations/word_addin/taskpane.html:167-169`; `adapter.js:26,43-68`). Global logout affects every session. Existing auth can fall back after provider errors and does not enforce the full Word exchange claim contract. Global rate-limit middleware parses every API Bearer before routing. Current response middleware sets `X-Frame-Options: SAMEORIGIN` and CSP `frame-ancestors 'none'` on Word pages. Results may render after logout.

## Proposed Solution

Use existing Vindex identity in a same-origin Office dialog configured without persistence or URL-session detection. A Word-specific exchange verifier requires provider confirmation and a valid signature plus exact issuer/audience/subject/future expiry; it has no fallback and does not call existing verifier helpers unchanged. The global user_rate_limit_middleware skips JWT parsing only under the exact /api/word/ segment and continues through SlowAPI IP/route limits. After authentication, a Word post-auth guard applies the existing general API bucket to session management/non-AI operations and the existing AI user bucket plus anomaly record/check to analysis/rewrite, keyed by server-derived account identity before side effects. Session exchange receives the general bucket after provider identity verification and before issuance. All non-Word middleware behavior stays unchanged.

Exchange for a random opaque Word session stored hash-only; expiry is capped by verified source expiry. Require Dialog Origin 1.1, exact origin, and a nonce; fail closed without verifiable origin. For Word HTML entry responses, replace the inherited CSP with one Word-scoped effective policy, remove X-Frame-Options only there, preserve Supabase connections, and leave all unrelated route policies unchanged.

Word routes validate the session and pass server-derived identity into existing `PermissionService.require(feature)`, avoiding `shared/permissions.py`. Logout revokes only this session. Every outbound provider attempt in the Word analysis/retrieval path, including embeddings, completions, optional reranking, and retries, requires a fresh atomic claim. Disable SDK-hidden retries; retry only in app code with a new claim. If revocation commits first, no attempt starts; if claim wins first, that attempt may complete but its result is suppressed. Add a reviewed, unapplied session migration only after Database Architect approval.

## Affected Systems

`integrations/word_addin`; narrow Word auth/session router and registration; `api.py::user_rate_limit_middleware` Word-only token-parse carveout; Word-entry response headers; later Word analyzer/retrieval dispatch hooks; one unapplied session migration; existing Supabase Auth, `PermissionService`, `UsageService`, audit. Do not edit `shared/permissions.py`, central AI budget/usage modules, migration 146, global auth behavior, or production settings. Recheck PR #66 and migration numbering before code.

## Risks

- **HIGH:** Auth, origin, or binding error could authorize another user. Use provider-confirmed identity, strict signed claims, no fallback, hash-only sessions, origin+nonce checks, and independent tests.
- **HIGH:** Duplicate CSP or remaining X-Frame-Options can block Word; replace policy only on Word entry responses and verify response chains.
- **HIGH:** Existing middleware may parse a token before the dedicated verifier, and an unclassified Word AI route could receive the general API quota and bypass anomaly checks. Skip only the parser for the exact Word segment, retain SlowAPI IP/route limits, and apply explicit general/AI post-auth policy with anomaly checks before side effects; prove zero legacy-helper calls.
- **HIGH:** Hidden SDK retries could send legal text after revocation. Disable SDK retries for Word, claim every attempt, and stop on revocation.
- **HIGH:** Logout cannot recall already-dispatched work. Clear/abort locally and suppress output.
- **HIGH:** Session FK/retention/cleanup/claim require Database review; no migration execution.
- **MEDIUM:** Hosts without Dialog Origin 1.1 fail closed and remain unsupported.
- **MEDIUM:** PR #66 is open/Draft; use mocks and make no live cost-protection claim.

- **MEDIUM:** Upgrade may leave vindex_auth_token in roaming/local storage. Purge both stores before rendering auth state and await completion.
- **MEDIUM:** Current pre-auth IP limits trust caller-controlled X-Forwarded-For (SEC-048). Keep defense-in-depth limits but prove a non-spoofable exchange control before public exposure.
- **MEDIUM:** Do not carry unsafe-inline or unsafe-eval into the Word CSP; externalize Word scripts or provide verified nonce/hash.
- **MEDIUM:** Database Architect conditionally approved the lifecycle contract: retain revoked rows to expiry; daily cleanup after expiry with failures surfaced (nominal maximum 24 hours after expiry when successful); revoke all Word sessions before soft-erasure success and fail closed; remove rows before hard Auth deletion under ON DELETE RESTRICT. Database Architect confirmed this contract on 2026-11-02. Resolve PR #66, synchronize this branch with canonical main, and verify the next unused slot before naming or authoring the Word migration; do not assume 146 is free if PR #66 closes unmerged.
- **HIGH future gate:** Every Word provider attempt, including retries, must use a fresh atomic claim and disable hidden SDK retries.
- **MEDIUM future gate:** Retrieval logs query snippets; redact Word-selected text before Task 02 exposes analysis.
## Alternatives

Reject persisted refresh tokens, global logout, missing-origin fallback, local verifier fallback, existing middleware JWT parsing on Word tokens, a single request-level claim for all retries, shared permission changes, and Microsoft identity.

## Recommendation

Red Team is FREEZE READY and Security is CONDITIONAL. Task 01 source implementation may proceed, but legacy-token purge must be implemented and verified before Task 01 closes. Database lifecycle condition is closed. Migration authoring remains blocked while PR #66 reserves 146; resolve it, synchronize this branch, and verify the next unused slot first. Public exposure and pilot remain blocked by their named conditions. If any provider path cannot claim each attempt or middleware still parses Word tokens through existing helpers, do not expose the Word route.

## Sign-off

- [x] Red Team re-review (FREEZE READY)
- [x] Security review (CONDITIONAL)
- [ ] Database Architect review (pending)
- [x] Founder-authorized scope covers Word auth and narrow server integration; production migration/release is not authorized.
