# P0 audit continuity incident — seq 1568

## Evidence boundary

The supplied independent read-only production observation reported 29,032 rows. At seq 1568 (2026-07-28 15:06:29 UTC), prev_hash is the 64-zero genesis sentinel and does not equal entry_hash at seq 1567. Seq 1569 points to entry_hash at seq 1568. This establishes a broken link and a continuation from the new anchor. The separately documented seq 32 incident remains separate. The operator reported the 081 partial unique index with predicate seq > 32. This hotfix did not query production.

PROVEN / STATIC + LOCAL_TEST: verified main swallowed head read errors and proceeded with genesis. Local RED uses the real PostgREST SDK with scripted HTTP responses. The prior independent ISOLATED_POSTGRES reproduction passed the real writer through a failed SELECT and appended a new genesis at seq 33, with and without the S08 guard. The partial index excludes the original genesis entry, so it can admit the first repeated genesis after the index cutoff.

INFERRED: the observed production signature is consistent with that failure mode. UNKNOWN: the historical initiating request, role, transport/DB failure, and integrity of the complete payloads and chain. Preserve original rows and available logs. Recompute individual hashes and segment continuity from a read-only snapshot, with evidence custody and timestamp normalization, then correlate request/DB logs around the reported UTC time. No seq 1568 verifier exception was added.

## Hotfix

Both writers now abort before INSERT on head read error or invalid response. A nonempty response must have one 64-character lowercase hex hash. The installed SDK can normalize an empty HTTP body to an empty list, so genesis additionally requires an explicit exact count of zero on the empty path. Normal appends still read only the tail. The existing 23505 retry re-reads the head and is unchanged. There is no migration.

Critical caller review: confirmation and rejection report HTTP 503 without an audit ID; the audited export withholds the archive; hearing deletion requires an audit intent before the irreversible step, while its completion event can still evidence deletion if the final audit append fails. Hearing edits and intake type correction retain their existing compensation behavior and report 503 on audit failure. Best-effort telemetry still logs loss and returns its existing result. No callers were modified. Tests that seed existing audit rows now supply a valid-shaped digest.

Roll forward with the fixed writer. A rollback artifact must retain F1. If that is impossible, pause writes that would use the unsafe writer until a corrected build is available. Keep immutable rows, triggers, grants and verifier exceptions intact.
