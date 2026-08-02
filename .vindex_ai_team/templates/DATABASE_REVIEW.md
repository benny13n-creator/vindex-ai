# Database Review — [Change Name]

**Author (role):** Database Architect
**Date:**

## Change Summary
New table(s) / column(s) / migration — exact SQL, drafted for founder review (never auto-run, per
this project's standing rule).

## Owner/Creator Column Check
Every new owner/creator column: type is `UUID`, real FK to `auth.users(id)`, explicit `ON DELETE`
behavior stated and justified (default: `RESTRICT`, per migration 077's precedent — a `CASCADE`
choice must be justified in writing, not assumed). No exceptions deferred to "a future integrity
audit" — SEC-033's whole point is that deferral is how this pattern recurred four times already.

## Cascade / Blast-Radius Analysis
If this touches `auth.users` or any frequently-referenced table: full FK graph, informed by
`docs/security/SEC031_FK_GRAPH.md`'s methodology. What breaks if a user account is deleted? What's
touched transitively?

## Silent No-Op Check
Does this use `CREATE TABLE IF NOT EXISTS` or similar against a table that might already exist in
incomplete form? Per SEC-034 — verify with a live check, don't assume a clean slate.

## RLS Policy
Stated, understanding it is defense-in-depth for the direct-browser-write cases, not the tenant-
isolation enforcement mechanism (that's `.eq("user_id", ...)` application-layer discipline, per
SEC-004). Explicit column restriction stated if the table will ever receive a direct client-side
write (the SEC-038 lesson).

## Retention / Lifecycle
Does this data need a retention/deletion policy? Is one already implemented
(`services/retention_service.py`) or does this require a new one?

## Rollback Plan
Stated explicitly, following the SEC-031 methodology: dry run first, read-only verification after
each step, founder executes.

## Verdict
APPROVED / APPROVED WITH CONDITIONS / BLOCKED (destructive migration veto).
