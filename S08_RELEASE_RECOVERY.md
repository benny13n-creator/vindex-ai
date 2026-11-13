# Release B cutover and recovery

Release base `2cf0c237bdb2e5996086b53eeaac57bf1ee84d9f`. The candidate preserves the P0 head reader and Release A. The only S08 change to the audit writer forwards three expected confirmation SQLSTATEs to the deadline decision layer.

## Before authorizing the cutover

Obtain an authorized schema and privilege inventory for the live gateway. Reproduce the PostgreSQL and PostgREST versions, exposed schemas, authenticator membership, effective table, column, sequence and function privileges, audit RLS, and the installed document deletion RPC. Compare the validated 126 foreign key, 043 immutable trigger, 081 partial unique index and 147 privileges before and after migration 148. The rehearsal uses repository migrations and representative grants. Its grants do not establish what is deployed.

The application has no verified confirmation maintenance switch. Before approving the migration, identify an ingress control that can block POST requests to both `/api/rokovi/{rok_id}/potvrdi` and `/api/rokovi/{rok_id}/ispravi` on every reachable host. Include any worker or alternate writer of `rok_potvrdjen`. Rehearse the block and drain in-flight requests. Test the direct service hostname as well as the public hostname. If any path stays open, halt before migration or merge.

## Authorized operator sequence

1. Pin the reviewed commit and SQL file. Capture the effective ACL and policy baseline, the audit tail, and the active app SHA. Keep the historical seq 1568 incident visible separately from continuity of new rows.
2. Activate the rehearsed block and drain writers. Apply the exact migration 148 in its single transaction. Verify the two trigger definitions, invoker mode, empty search path, expected backend role and unchanged existing ACLs before merging or deploying.
3. Deploy the reviewed application commit while the block stays active. An app-first interval lacks the transactional fence. A SQL-first interval with the old app can turn expected trigger outcomes into generic audit-write failures and cannot mark a legitimate re-review.
4. Verify the deployed SHA. Use an explicitly approved synthetic path for cross-tenant, duplicate, withdrawal and re-review checks and verify the chain from the captured tail. Confirm that the gateway returns the expected codes to the application. Reopen traffic only after all checks pass.

On any failure keep the block active and prefer a forward fix. Before SQL commit, roll back the transaction. If a separately approved post-commit SQL rollback is necessary, drop only `trg_s08_guard_rok_confirmation` on `public.audit_immutable`, `trg_s08_stamp_document_invalidation` on `public.events`, then their two S08 functions, in one transaction. Keep P0, the prior RLS, grants, constraints and triggers, and every audit row. Reopen only once equivalent transactional source protection has been verified.
