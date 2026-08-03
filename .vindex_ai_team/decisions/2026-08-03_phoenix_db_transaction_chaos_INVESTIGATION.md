# Project Phoenix — Phase 2: Database Transaction Chaos (Investigation, read-only)

**Scope**: deadlock/lock contention, lost connection mid-operation, duplicate key/constraint violations,
and constraint violations on tonight's newly-added insert call sites. No code changed. Every claim below
is cited to file:line or a direct grep executed during this investigation.

---

## 1. Deadlock / lock contention

**Row-locking inventory**: repo-wide grep for `FOR UPDATE`/`SKIP LOCKED` across `migrations/*.sql` finds
exactly ONE real row-lock use: `claim_intake_job` (`migrations/073_intake_foundations.sql:198-219`),
which deliberately uses `SELECT ... FOR UPDATE SKIP LOCKED` — by Postgres design, `SKIP LOCKED` means
a competing claim never blocks/waits on another transaction's lock, so **classic deadlock is
structurally impossible here** (skips instead of waiting). All other `FOR UPDATE` grep hits are RLS
policies (`... FOR UPDATE USING (...)`), an unrelated Postgres concept (row-level security policy
scope, not locking).

**Caller-side handling**: `shared/intake_queue.py::claim_next_job` (`intake_queue.py:79-84`) has **no
try/except at all** around the RPC call — any exception (including a hypothetical connection-level
error) propagates straight up. Traced the caller chain: `shared/intake_worker.py::_tick()`
(`intake_worker.py:99-126`) calls it un-guarded at line 107; `_tick()` itself is only guarded around
`_process()`+`mark_job_completed()` (lines 113-123), NOT around the `claim_next_job` call itself — but
`IntakeWorker._run()`'s outer loop (`intake_worker.py:85-91`) wraps the ENTIRE `_tick()` call in a
catch-all `except Exception: logger.exception(...); did_work = False`. **Verdict: LOW.** Detection: yes
(logged). Retry: implicit, via the next poll tick (`poll_interval_s`), not a dedicated backoff. Rollback:
N/A (`claim_intake_job` is a single atomic `UPDATE...RETURNING`, nothing partial to roll back).
Recovery: yes — a job that failed to claim simply stays `received` and is retried by the next tick, or
by any other worker process. Consistent: yes. Not idempotent in the strict sense but doesn't need to be
(nothing was mutated).

**`shared/audit_immutable.py::_build_and_insert`'s retry loop** (`audit_immutable.py:251-284`) is
correctly narrow: it only retries on `_is_unique_violation` (`"23505"`/`"duplicate key"`,
`audit_immutable.py:192-194`) or falls back once on `_is_missing_column_error` (`"42703"`/`"does not
exist"`, `:197-206`). A genuine deadlock (Postgres code `40P01`, message `"deadlock detected"`) matches
**neither** check — `if not _is_unique_violation(e): raise` (`:279-280`) re-raises immediately, with NO
retry. This is correct, conservative behavior (no infinite-loop risk from blindly retrying an
unclassified error), but it also means a real deadlock on this INSERT-only, trigger-protected table
(vanishingly rare in practice, since INSERT-vs-INSERT deadlocks require contention on the same unique
index entries — which already surfaces as `23505`, not `40P01`) would silently drop ONE audit entry
(caught one level up by `log_action`'s own try/except, `audit_immutable.py:104-109`, logged at warning
level, returns `None`) without any retry or escalation. **Verdict: LOW** (theoretical exposure, correct
conservative design, real-world trigger condition is essentially unreachable for this specific table).

---

## 2. Lost connection mid-operation

**Confirmed intact**: the "ghost document" fix (Project Sentinel) is still present and correct —
`api.py:4252-4256`: `if not _dok_id: raise HTTPException(status_code=500, detail="Dokument je
otpremljen, ali nije uspešno sačuvan u sistemu...")`, placed immediately after the `predmet_dokumenti`
insert attempt (`api.py:4207-4250`) and BEFORE the classify/genome-refresh/GPT-analysis blocks that
follow. Re-verified this gates ALL downstream work — nothing after this line can execute without a real
`_dok_id`.

**`api.py::kreiraj_predmet`** (`api.py:3140-3200`, exact lines shifted by tonight's Ledger edits but
structure unchanged): sequence is `predmeti` insert (atomic, single statement, `api.py:~3145`) → durable
`PREDMET_KREIRAN` event insert (try/except, warning-only on failure, correctly does NOT block the
response) → audit insert (`asyncio.create_task`, fire-and-forget). **If the connection drops between
the predmeti insert and the event insert**: the predmet row itself is fully committed and consistent
(single atomic statement) — the ONLY consequence is the same already-documented, already-tracked
Sentinel finding (Case Pipeline never triggers) — no NEW class of bug here, correctly scoped as
`SENT-001`/pre-existing, not a fresh Phoenix finding.

**Checked for OTHER instances of the ghost-document class of bug** (expensive/user-visible work
proceeding after an unchecked insert failure) in tonight's Migration-mission additions:
- `routers/copilot.py::_handle_akcija_rok`/`_handle_akcija_beleska`: single insert, wrapped in its own
  try/except that returns an honest `{"uspeh": False, ...}` on failure — no downstream work proceeds
  past a failed insert. **Correct.**
- `routers/copilot.py::_handle_naplati_radnju` (`copilot.py:964-972`): the `billing_entries` insert is
  wrapped in try/except that `raise HTTPException(500, ...)` on failure (`copilot.py:969-972`) — correct,
  no ghost state possible (nothing downstream reads `kreirana_id` if the insert failed, since the
  exception raises before that variable would be read).
- `routers/evidence.py::klasifikuj_i_sacuvaj` (Mission Migration): the `predmet_dokumenti` UPDATE and
  `predmet_dokazi` INSERT are two INDEPENDENT try/except blocks by design (Reliability fix comment,
  `evidence.py:162-167`, predates tonight) — if the UPDATE fails, the classification result (`tip_dokaza`
  etc.) is lost for that document, but this is a **logged, non-silent** partial failure (each block logs
  its own warning), not a ghost-success — the caller (`api.py`'s background task) never surfaces a false
  "classified" signal to the user because classification itself has no direct user-facing success
  indicator (it's a background enrichment step, no HTTP response depends on it completing). **Verdict:
  LOW** — acceptable given the feature's own fire-and-forget nature, but WORTH NOTING the newly-added
  `log_action_sync("evidence_klasifikacija", ...)` call (Mission Migration) fires unconditionally after
  the `predmet_dokumenti` UPDATE succeeds (`evidence.py:~183-191`), meaning if the UPDATE fails, no audit
  entry is created either — consistent (no false audit for a failed classification), not a bug.

**No new ghost-document-class bug found.** Sentinel's fix remains the correct, sufficient answer for the
one place this pattern was real (parallel expensive GPT calls proceeding blind past a failed insert);
every other multi-step sequence checked either fails fast before expensive work, or has no user-facing
"success" claim that could become false.

---

## 3. Duplicate key / constraint violation

**Constraint inventory** (representative, not exhaustive — `UNIQUE` constraints exist across dozens of
migrations): `audit_immutable`'s partial `UNIQUE(prev_hash)` for rows after seq=32 (migration 081) —
**correctly handled** via `_build_and_insert`'s retry-with-fresh-prev_hash loop (§1 above). `intake_jobs
.idempotency_key` — **correctly handled**: `enqueue_intake_job` RPC (`migrations/073_intake_foundations.sql:158-164`)
explicitly checks for an existing row with the same idempotency_key FIRST and returns its ID instead of
inserting a duplicate — this is idempotency-by-design at the RPC level, not exception handling.
`pinecone_capacity_snapshots`'s `UNIQUE (snapshot_date, namespace)` (`migrations/087...sql`) — **not
traced this pass** (lower-traffic admin-panel feature, out of budget for this investigation).

**Newly-discovered real gap**: `routers/copilot.py::_handle_akcija_povezi_klijenta`
(`copilot.py:691-705`) does a classic check-then-insert: `SELECT ... WHERE predmet_id=X AND
klijent_id=Y` (`:691-693`) → `if existing.data: return already-linked message` (`:694-695`) → `INSERT`
(`:697-702`). This is a genuine TOCTOU race: two near-simultaneous requests (a lawyer double-clicking,
or a retried request after a slow response) can both pass the SELECT check before either INSERTs,
and the composite PK (`predmet_id, klijent_id` per the comment at `:683-685`) means the SECOND insert
raises a duplicate-key violation. **This IS caught** — the insert is wrapped in
`try/except Exception: return {"uspeh": False, "odgovor": "Greška pri povezivanju klijenta."}`
(`:703-705`) — so the user gets an honest failure message, not a raw 500 or a silent false-success.
**Verdict: LOW-MEDIUM.** Not a reliability defect (no crash, no silent failure, no data corruption —
the constraint itself prevents the duplicate row) but a real UX polish gap: the error message says
"greška pri povezivanju" (generic failure) instead of the more accurate and reassuring "already linked"
— the SAME outcome the non-race path returns as a SUCCESS message (`:694-695`). A lawyer hitting this
race gets told their action failed when it actually succeeded (via the other concurrent request). Not
flagged as a fix target for this investigation (read-only), but worth a coordinator's attention as a
cheap, low-risk polish item: catching the specific duplicate-key case and returning the same "already
linked" message the pre-check path uses.

---

## 4. Constraint violations on tonight's newly-added audit inserts

Checked `shared/audit_immutable.py::log_action`/`log_action_sync` (the sink for every one of Mission
Ledger's and Mission Migration's new audit calls, e.g. `routers/copilot.py`'s 5 new `log_action` calls,
`routers/court_predictor.py`'s 7). **Confirmed safe by construction**: `log_action` (`:100-118`) and
`log_action_sync` (`:120-137`) each wrap their single call to `_build_and_insert` in a bare
`try/except Exception: logger.warning(...); return None` — this is a SINGLE, side-effect-free INSERT
statement (no other table touched by the same function call), so any constraint violation here
(hypothetically — `audit_immutable` has no constraint that application-level data could realistically
violate beyond the already-handled `prev_hash` uniqueness) can only ever fail that one audit row, never
partially corrupt anything else. **Verdict: none — no exposure found.** This directly confirms Mission
Migration's own claim that the fail-soft audit pattern is safe was correct, re-verified independently
here rather than taken on faith.

---

## Summary table

| # | Scenario | Detect | Retry | Rollback | Recovery | Audit | User notice | Consistent | Idempotent | Severity |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Deadlock on `claim_intake_job` | Yes (logged) | Implicit (next tick) | N/A (atomic) | Yes | Partial (log only) | N/A (background) | Yes | N/A | LOW |
| 1b | Deadlock on `audit_immutable` insert | Yes (logged) | No (correctly narrow) | N/A | Partial (1 row lost) | N/A (it IS the audit) | No | Yes | N/A | LOW |
| 2 | Lost connection, upload ghost-doc | Yes (fixed, Sentinel) | N/A (fails fast) | N/A (nothing to roll back) | User must retry | Yes | Yes (honest 500) | Yes | Yes | Resolved |
| 3 | Duplicate key, `predmet_klijenti` race | Yes (caught) | No | N/A (constraint prevents dup) | User must retry | Yes (on success path only) | Yes (but misleading message) | Yes | Yes | LOW-MEDIUM |
| 4 | Constraint violation on new audit inserts | Yes | No (not needed) | N/A | Yes (fail-soft) | N/A | N/A (silent by design, non-critical) | Yes | Yes | None found |

---

## Single most severe finding (for coordinator)

**None of the 4 areas produced a Critical or High finding.** The most concrete, previously-undocumented
finding is the `predmet_klijenti` check-then-insert TOCTOU race in
`routers/copilot.py::_handle_akcija_povezi_klijenta` (`copilot.py:691-705`) — under concurrent/retried
requests, the loser of the race gets a generic "greška pri povezivanju klijenta" failure message even
though the client WAS successfully linked (by the winning request). This is NOT a silent failure, NOT
data corruption, and NOT a crash — the composite primary key constraint does its job and the exception
is caught — but it is a real, reproducible instance of the system giving a lawyer a *falsely negative*
outcome message for an action that actually succeeded, the mirror image of the false-*positive* bugs
prior missions found and fixed. Recommend (not implemented, read-only investigation): catch the specific
duplicate-key exception and return the same "already linked" success message the pre-check path uses.
