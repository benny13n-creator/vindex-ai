# Database Architect Review - Word Add-in Task 01 Authentication

**Date:** 2026-11-02
**Verdict:** APPROVED WITH CONDITIONS
**Scope:** Proposed session registry, lifecycle, authorization boundary, dispatch claims, and unapplied migration. No production database or live service was accessed.

The registry is suitable as a narrow additive migration. Follow-up confirmation on 2026-11-02: the revised Product Specification AC18 and Technical Design §8/Database Impact adopt the exact retention and account-erasure behavior below. The lifecycle condition is closed; migration naming and authoring remain gated on PR #66 migration 146 reconciliation as specified below. Runtime GDPR revocation and cleanup acceptance remain required.

## Schema contract

- Create one public.word_sessions table with UUID primary key, user_id UUID NOT NULL, token hash, created_at, expires_at, nullable revoked_at, and nullable last_dispatch_claimed_at.
- Add a named foreign key to auth.users(id) ON DELETE RESTRICT. Hard Auth deletion must remove Word session rows first; RESTRICT intentionally prevents orphaning.
- Generate at least 32 random bytes per opaque token; store only its lowercase 64-character SHA-256 hex digest under a global unique constraint. Return the raw token once and keep it only in taskpane memory.
- Enforce expires_at > created_at and expires_at <= created_at + interval '1 hour'; application expiry is the earlier of verified source expiry and one hour after issue.
- Add a nonpartial user_id index for FK/account-erasure operations, an expires_at cleanup index, and a partial (user_id, expires_at) index for active rows (revoked_at IS NULL). The unique hash constraint supplies the lookup index.

## Retention and account erasure

- Retain revoked rows through their original expires_at; expired rows become cleanup-eligible at expiry.
- Add expired-session cleanup to the existing daily retention job. If that job succeeds, nominal maximum physical retention after expiry is 24 hours. Track and surface cleanup failures.
- The current account endpoint in routers/gdpr.py soft-anonymizes profile fields and does not delete auth.users. It must revoke all of that user's Word sessions before reporting erasure success and fail closed if revocation fails.
- A future hard Auth deletion must explicitly remove that user's Word session rows before attempting deletion. Other existing Auth foreign-key restrictions may also apply.
- Audit records keep only non-secret session row ID, channel, reason, and correlation ID; they must not FK to the session row or contain token material.

## Per-attempt dispatch claim

Immediately before each external provider attempt, conditionally update the session row using server-derived session ID, user ID, and token hash, with predicates revoked_at IS NULL and expires_at > clock_timestamp(). Update last_dispatch_claimed_at and commit before dispatch.

Revocation and claim update the same row, so row-lock serialization decides the winner. A committed revocation first makes the claim return no row; a committed claim first authorizes only that one attempt. No returned row or any database error means no provider call. Require a new claim for every provider and every application retry, disable hidden SDK retries, and do not hold a database transaction open during provider work.

## Database privileges and migration behavior

Enable RLS with no anon or authenticated policies. Explicitly revoke default table privileges and grant only the server-side service_role the operations required for session validation, issue, revoke, account erasure, and cleanup. RLS is defense in depth; the backend service role remains trusted.

Use plain CREATE TABLE, failing loudly if the target already exists. Do not use CREATE TABLE IF NOT EXISTS because SEC-034 documents a silent no-op failure mode.

Local migration files currently reach 145. PR #66 is open/Draft and owns migration 146; do not modify its files. Do not name or author the Word migration until PR #66 is resolved, this branch is synchronized with canonical main, and the next unused slot is verified. If 146 is merged, use 147 only after checking for competing assignments and apply/verify 146 first. If PR #66 closes unmerged, explicitly release or reassign 146 rather than assuming it is free. A read-only live-schema preflight is required before any founder-run application; no live schema was accessed in this review.

## Rollback and acceptance

Before rollback, disable or redeploy away from Word routes and cleanup code; then remove claim/revoke functions, indexes, and table without CASCADE. This invalidates Word sessions only and does not affect web sessions or legal records.

Acceptance checks must cover token entropy and hash-only storage; expiry boundaries; FK deletion behavior; privileges; cleanup eligibility and failure reporting; soft-erasure revocation; concurrent claim/revoke ordering; one fresh claim per provider attempt and retry; and secret-free audit metadata.

No migration, database connection, production action, network call, or test run was performed by this review.
