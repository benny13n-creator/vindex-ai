# S08 — Source action integrity

Date: 2026-11-07. Base: `da50b0203a90e9d9dbc9226e7492e4c303c61500`.
Initial tracked/untracked Git status was clean. Work is local only.

## Reproduction (RED)

Command: `python -m pytest tests/test_s08_withdrawn_source.py::test_withdrawn_direct_post_repeated_no_write -q`

Before router changes: **1 failed**, exit 1. A direct HTTP POST to
`/api/rokovi/r-1/potvrdi` returned 200 with `odluka_zabelezena: true` and
`stanje_odluke: CONFIRMED`, instead of 409. Fixture: owned Genome candidate,
retained canonical `dokument_naziv=source.pdf`, `dokument_id=NULL`, no matching
document in its tenant/case. This is withdrawn under the existing
`shared.rokovi.izvor_povucen()` contract, not a new inference rule.

## Minimal correction

Only application file changed: `routers/rok_odluka.py`.
Ownership projection now includes `dokument_id,dokument_naziv`. Before a first
confirmation of an eligible Genome candidate, query matching document names
under BOTH `user_id` and `predmet_id`, then use `izvor_povucen()`.
Proven withdrawal => 409 before audit write. Required check failure, including
missing response data => 503 before audit write. No decision or reminder is
scheduled in either case. Existing rejection/correction gates remain.
Already-confirmed rows retain the existing re-review/idempotency branch.
`shared/rokovi.py` needed no change.

Projection assumes migration 126 columns (already relied on by Genome writing
and correction paths); `vrsta` remains conditional on migration 129. This task
did not inspect a live schema or execute migrations. Pre-126 databases are not
proven supported; a missing column fails closed with 503. Updated the existing
projection assertion to require provenance fields while still checking both
129 modes.

## Evidence (GREEN)

New HTTP tests: **11 passed**, independently run by the adversarial reviewer.
They cover repeated withdrawn POSTs (409, zero writes), source read failure
(503, zero writes), duplicate names, explicit same-name/unrelated document
deletion transitions, unresolved origin, non-Genome source, repeated confirmed
request without new write, re-review after confirmation, A/B access, and a
deterministic race demonstration. FK nulling is explicitly emulated, not tested
against Postgres.

Combined command:

```text
python -m pytest tests/test_s08_withdrawn_source.py tests/test_ns2b_c_odbijen_rok_ostaje_odbijen.py tests/test_n03_deadline_gates.py tests/test_g3_ispravka_roka_integritet.py tests/test_ns2_a2_potvrda_samo_rok.py tests/test_n4_ispravka_roka.py tests/test_n4_rokovi_izvori.py tests/test_mir001_t07_dogadjaj_posledica.py tests/test_ns006_t8_case_actions.py tests/test_wave2_2d_source_invalidation.py tests/test_b8_rok_izvor_identitet.py -q --disable-warnings
```

Result: **282 passed, 9 skipped, 2 xfailed, 14 warnings**, exit 0.
An initial regression run found one exact-projection assertion that required
updating for the new fields; final run has no unexpected failures.

Skip audit command: `python -m pytest tests/test_n03_deadline_gates.py tests/test_mir001_t07_dogadjaj_posledica.py -q --disable-warnings -rs`.
Result: **134 passed, 9 skipped, 2 xfailed**. All nine skips are OCR golden-case
tests in `test_mir001_t07_dogadjaj_posledica.py`: Tesseract is unavailable.
They are NOT PASS. Two existing strict expected failures are N03-FD2 claim
identity and N03-FD6 automatic source-based suspension; neither is fixed here.
`git diff --check` passed.

## A/B authorization and unknown provenance

Real FastAPI routes and ownership filters run against the existing in-memory
Supabase harness; authentication is synthetic A/B tokens, external networking
is blocked. B confirming A's candidate => 404; A confirming B's candidate =>
404. A's source check ignores B's same-name document even with the same case
ID, and ignores A's same-name document in another case: 409 with zero audit
writes. These are local authorization proofs, not live RLS/token proofs.

A remaining same-name document does not establish source identity. A NULL ID
with that remaining name stays unknown and is not blocked as proven withdrawn.
A missing source name and non-Genome rows likewise do not establish withdrawal.
Successful confirmation expresses the human decision, not verified source
existence or factual correctness. Rename/import/manual corruption outside the
existing producer contract has not been independently resolved.

## Independent adversarial review and residual race

A separate read-only reviewer checked the diff and independently ran the new
tests: no new cross-tenant bypass found; existing confirmed re-review semantics
preserved. Reviewer requested explicit deletion-transition tests and accurate
schema documentation; both are included.

**No atomic protection is proven.** Row/source reads and audit insert are
separate operations. `test_residual_delete_between_check_and_write` deletes the
source (emulated FK NULL) immediately before the real confirmation writer and
demonstrates 200/CONFIRMED. Deletion can also occur after the row snapshot while
it still contains a non-NULL document ID. A repeated read or process-local lock
would not establish database-wide atomicity. Closing this requires a coordinated
transaction/locking protocol with document deletion and decision writing, beyond
this minimal router patch. No migration or such guarantee is introduced.

## Delivery status

**PARTIAL** under the strict aggregate acceptance criteria: the reproducible
sequential missing server guard is fixed locally with green targeted/regression
evidence, but concurrent deletion can still permit confirmation, and nine OCR
regressions were not executable. Do not interpret this as race-safe end-to-end
source integrity or a production verification. No push, merge, deployment,
production data access, migration, or autonomy activation was performed.

The local S08 commit includes this report; its exact SHA is supplied in the
delivery message (a commit cannot include its own SHA without changing it).

## Final concurrency closure — 2026-11-07

Closure base: `f73fa0d3e8acd88dbc2bc920b332b4812287c76f`, branch
`codex/miroslav-s08`, clean initial worktree. This section supersedes the
historical PARTIAL finding above for the local candidate with migration 148.

### Reproduction and transaction order

1. Request C reads the owned Genome candidate with document D still linked
   (or reads D as the last same-name witness when the FK is already NULL).
2. Request D deletes the document, sets the candidate FK to NULL where linked,
   and commits. No same-name witness remains in the tenant and case.
3. C appends `rok_potvrdjen` using the earlier result. Before the migration,
   the insert succeeds. The isolated database test reproduced this across
   sessions with the guard disabled and then restored it.

Migration 148 guards the actual audit INSERT. The invoker trigger locks the
owned candidate with FOR NO KEY UPDATE and reads it under READ COMMITTED.
For a linked document, the 126 FK makes deletion wait for that candidate lock
or makes confirmation see the newly null FK. For a null FK, confirmation
must pin a tenant- and case-scoped matching document with FOR SHARE through
commit. One remaining same-name document preserves the existing unknown
provenance behavior. The precheck in the HTTP route still provides early
feedback. The transaction provides the concurrency guarantee.

The candidate lock also serializes duplicate confirmations. The losing first
request reports the existing decision without a new audit row or downstream
tasks. An explicitly requested re-review still requires a document
invalidation newer than the latest confirmation. Document invalidation events
are stamped when inserted, after DELETE, so a deletion that started earlier
but waited for confirmation still produces the warning. Prior confirmations
remain in the chain and retain their decision semantics. Migration 081 and
the existing audit retry continue to resolve hash-head collisions. The guard
uses invoker permissions and adds no grants. The route uses the canonical
owned UUID when addressing text audit resource IDs.

### Verification

PostgreSQL 17.9 ran on loopback in a fresh, disposable local cluster. The
fixture applies repository migrations 043, 073, 081, 090, 126, 137 and 148
over minimal synthetic base tables. Competing sessions used distinct
PostgreSQL backends and the tests observed `pg_blocking_pids` before releasing
the blocker. The deletion path uses the migration 137 RPC. Test grants in the
disposable fixture model the backend role and are separate from the candidate.

| Required check | Result | Evidence |
| --- | --- | --- |
| Delete before confirmation | PASS | Both FK and null-FK last witness paths reject with zero writes |
| Confirmation before delete | PASS | Both deletion paths wait, then complete after confirmation commits |
| Two concurrent confirmations | PASS | The second waits and yields the existing decision, one confirmation row |
| Two same-name documents | PASS | One remaining in-scope witness allows unknown provenance |
| Database failure | PASS | Revoked source read aborts INSERT, HTTP mapping returns 503 |
| User A/B isolation | PASS | Foreign deadline and foreign same-name witness cannot authorize |
| Confirmation idempotency | PASS | Concurrent duplicate, HTTP replay and re-review replay |
| Immutable hash-chain | PASS | Python hash recomputation, UPDATE guard and competing writer collision/retry |
| Earlier confirmed deadlines | PASS | Prior confirmation survives deletion and a valid re-review appends once |

Targeted S08 run: **22 passed**. Combined local regression suite:
**293 passed, 9 skipped, 2 xfailed**. No unexpected failures. The nine OCR
skips and two pre-existing N03 expected failures described above remain
outside the final concurrency proof. `git diff --check` passed.

Reproduction command in the dedicated cluster (roles `anon`,
`authenticated`, and `service_role BYPASSRLS` created in that cluster):
`$env:S08_TEST_PG_PORT='56408'; python -m pytest tests/test_s08_postgres_concurrency.py tests/test_s08_withdrawn_source.py -q`.

### Scope and residual risks

**S08_PROVEN_FIXED_LOCAL** for the candidate as tested. Migration
`migrations/148_s08_confirmation_source_fence.sql` is required for the
database guarantee. Hosted schema, role permissions, PostgREST and production
clock alignment were not exercised. The real SQL proof and the HTTP error
mapping tests were run separately. A competing multi-row writer can cause a
PostgreSQL deadlock or timeout, in which case the failed audit transaction
rolls back. Same-name survivors still provide no proof of identity. No
production execution, push, merge, deployment or NS007 activation.
