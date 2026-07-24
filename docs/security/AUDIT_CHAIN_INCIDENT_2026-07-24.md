# Audit Chain Verification — Incident Report (2026-07-24)

**Status: RESOLVED. No evidence of tampering. Two independent bugs found and fixed.**

## How this was found

Celina 5, Task 3 required a working backup-verification drill
(`scripts/verify_backup_restore.py`). Its very first live run against
production called the existing `verify_chain_integrity()` function and it
reported `"ok": false, "broken_at_seq": 17"` — a possible tamper signal on
the `audit_immutable` table, the hash-chained, INSERT-only audit log
introduced in migration 043 (2026-07-07).

This is exactly what a verification drill is for. Both issues below were
found by direct, read-only inspection of the live `audit_immutable` table
(358 rows total at the time of this report) — no data was altered as part
of this investigation.

## Finding 1 — false positive: timestamp round-trip formatting (fixed)

`_compute_entry_hash()` hashes `created_at` as a plain string. At write
time (`_build_and_insert()`), the string comes from Python's
`datetime.now(timezone.utc).isoformat()`, which always produces 6-digit
microsecond precision (e.g. `...990920+00:00`).

At verification time, the same value is read back from Postgres via
PostgREST. Postgres's default text serialization for `timestamptz`
**strips trailing zero digits** from the fractional-seconds part — so
`.990920` comes back as `.99092`. Any row whose microsecond value happens
to end in one or more zero digits (~1 in 10, by chance) therefore
recomputes to a different hash than the one stored at write time, even
though nothing about the row was ever changed.

Confirmed by direct reproduction: recomputing seq=17's hash with the
string exactly as returned by PostgREST does **not** match the stored
`entry_hash`; recomputing with the trailing zero padded back to 6 digits
matches exactly.

**Fix**: `shared/audit_immutable.py::_normalize_ts_for_hash()` pads the
fractional-seconds part back to 6 digits before recomputing the hash
during verification only. Write-time hashing is untouched. This is a
read-only, non-destructive fix — no stored rows were modified.

## Finding 2 — genuine issue, not tampering: concurrent-write race (fixed going forward)

After fixing Finding 1, verification proceeded past seq=17 and stopped
again at **seq=32**, this time with a genuine `prev_hash` mismatch (not a
formatting artifact).

Direct inspection:

| seq | created_at | prev_hash |
|---|---|---|
| 30 | 2026-07-18T21:34:52.007865+00:00 | — |
| 31 | 2026-07-18T21:35:17.**682603**+00:00 | = seq 30's entry_hash |
| 32 | 2026-07-18T21:35:17.**68522**+00:00 | = seq 30's entry_hash (same as seq 31, not seq 31's entry_hash) |

Rows 31 and 32 were written **2.6 milliseconds apart**. `_build_and_insert()`
performs "read the last hash, then insert" as two unsynchronized steps
(a classic TOCTOU race). Under concurrent execution — most likely two
`genome_refresh` events firing close together during a batch/reindex
operation — both reads happened before either insert committed, so both
rows computed their `prev_hash` from the same prior entry (seq 30). The
chain forked instead of staying linear.

A full scan of all 358 rows (not just the first break encountered) found
**exactly one** such fork (seq=32) and **zero** `entry_hash` content
mismatches anywhere else in the table. There is no evidence of any actual
modification or deletion of audit data.

**Fix (prevents recurrence)**:
- `migrations/081_audit_immutable_prev_hash_unique.sql` — a partial
  unique index on `prev_hash` for all rows with `seq > 32`. The one
  historical duplicate (seq 31/32) is deliberately excluded from the
  index rather than silently rewritten — `audit_immutable` is
  INSERT-only and its own protection trigger (migration 043) refuses
  UPDATE/DELETE even on this row, correctly. **This migration has not
  yet been applied — the founder needs to run it in Supabase**, per this
  project's standing convention that migrations are never run
  automatically.
- `shared/audit_immutable.py::_build_and_insert()` now retries (up to 5
  attempts) on a `23505` unique-violation, re-reading a fresh `prev_hash`
  each time, so a future race loses cleanly instead of forking silently.
- `shared/audit_immutable.py::_verify_chain_sync()` now carries a
  `_KNOWN_EXPLAINED_BREAKS` allowlist containing only seq=32, with this
  document as the citation. Without this, `verify_chain_integrity()`
  would have stayed permanently blind to everything after seq=32 forever
  — it hard-stops on the first break by design, which is correct for an
  *unexplained* break but would have silently defeated the audit log's
  entire purpose for all ~340 rows written since 2026-07-18. Any new,
  undocumented break (either type) still hard-stops verification exactly
  as before.

## What this means for prior "chain intact" results

Every `verify_chain_integrity()` call made before this fix (including via
`GET /api/admin/security/audit-verify` and `security/chain_anchor.py`) was
unreliable in both directions:
- A `"ok": true` result did not actually prove anything past the first
  row whose microseconds happened to end in a non-zero digit that was
  also lucky enough to not hit the seq=32 fork region — in practice, for
  a 358-row table, essentially none of them constituted a real full
  verification once the table grew past ~17 rows.
- Conversely, if anyone had noticed and investigated a `"ok": false"`
  result before now, they would have had to do exactly this manual
  forensic work to distinguish false alarm from real incident — this
  document is that work, done once, so it doesn't need repeating.

Both bugs are now fixed. Going forward, `verify_chain_integrity()` is a
sound check again, and it will correctly flag any *new* unexplained break
as a hard failure — including anything past seq=32.

## Action items

- [ ] Founder: run `migrations/081_audit_immutable_prev_hash_unique.sql`
      in Supabase.
- [x] Timestamp false-positive fixed (`shared/audit_immutable.py`).
- [x] Retry-on-race fix applied to `_build_and_insert()`.
- [x] Known-break allowlist added so verification isn't permanently
      blind past seq=32.
- [x] Full-table scan confirmed: 1 explained fork, 0 content tampering,
      out of 358 rows.
