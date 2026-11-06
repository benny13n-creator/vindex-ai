# Implementation Plan - Word Add-in Task 01: Secure Authentication

**Date:** 2026-11-02
**Branch:** codex/word-addin-implementation
**Base:** aaea99a42906017fcbf3bbecdac02c01cc05fdde
**Scope:** authentication/session boundary only. No selected-text analysis, matter APIs, model calls, migration execution, deployment, or live auth access.

## Problem and evidence

The prototype accepts a pasted Vindex bearer, stores it in Office roaming settings/localStorage, reads it at startup, and places inline JavaScript under a global CSP that permits unsafe-inline. There is no Word-scoped session registry or Word-specific auth endpoint. The global user-rate middleware parses all Authorization bearer values before routing. The Add-in's account token handling must change without changing web login or global logout.

## Decision

Use the existing Supabase Auth identity in a same-origin Office dialog. Use a memory-only Supabase client with persistence and URL-session detection disabled. Bind one dialog result to an in-memory nonce and exact expected origin under DialogOrigin 1.1. Exchange the short-lived Supabase access token with a Word-only backend verifier; return a 32-byte-random opaque session token whose SHA-256 hash alone is stored server-side. Cap Word-session expiry at the earlier of verified source expiry and one hour. Word logout revokes only its current session.

The Database Architect confirmed lifecycle semantics. Keep the Word migration unnamed and unauthored while PR #66 is open/Draft and reserves 146. Resolve PR #66, synchronize the branch, and verify the next slot before authoring. Source tests use deterministic mocks and never contact live Supabase.

## Planned changes

1. Extract the existing public Supabase URL/publishable key into a same-origin shared browser config used by both the unchanged main login flow and the Word auth dialog.
2. Replace the Word pasted-token form with a same-origin dialog launch and memory-only session state. Clear legacy vindex_auth_token from both localStorage and Office roaming settings before rendering auth state; await roaming save and fail closed on cleanup error.
3. Add a narrow Word auth router/service for session exchange, current-session validation and revocation. Require successful Supabase get_user and strict signature/claim checks with exact configured signing-key selection; never fall back to the existing generic verifier. Store only token hashes, apply existing account API rate limits using server-derived identity, and use secret-free immutable audit events.
4. Change api.py only at the exact /api/word/ parser boundary and Word HTML headers. The carveout skips only generic bearer parsing and continues through the middleware chain. Existing API routes and global login/logout behavior remain unchanged. Word HTML gets a replacing CSP with no unsafe-inline/unsafe-eval, plus scoped framing headers.
5. Add authentication-focused deterministic tests for valid and invalid identity, missing/expired/revoked sessions, wrong user/claims/key, provider failure, nonce/origin/callback errors, repeated login, independent panes, cleanup completion/failure, logout races and secret-free logs.
6. Keep the taskpane's AI actions unavailable until Task 02 supplies a Word-session-aware selected-text API; do not send document text or call any AI provider in Task 01.

## Acceptance and gates

Task 01 can close only when legacy-token cleanup, authentication route tests, token-hash/session lifecycle tests, callback binding, rate-limit boundary and scoped CSP tests pass, with source-derived identities and no token leakage. Database-backed runtime behavior remains pending the migration; the Word migration cannot be named until PR #66 is resolved and numbering is reverified. Real Word host behavior is NOT_RUN until controlled Windows sideload; Mac and web hosts remain NOT_RUN. Public exchange exposure and controlled pilot remain blocked by SEC-048 trusted-IP proof and process-local limiter deployment evidence. PR #66 remains an open/Draft AI cost-protection dependency; no live paid model calls are permitted.

## File scope

Expected files: integrations/word_addin/* auth/taskpane assets; static shared Supabase public config and the existing static login's config reference only; routers/word_auth.py; api.py's narrow middleware/router/header integration; targeted Word auth tests; and this plan/evidence. Do not touch shared/permissions.py, shared/ai_budget.py, shared/usage.py, migration 146, deployment configuration, or Claude's workspace.
