# Document Lifecycle Architecture Report — Program Intake Sprint 002 (2026-08-05)

**Charter**: "Atomic Document Lifecycle" — one document, one identity, one lifecycle, one truth. No half-commit,
no half-rollback, no ghost/orphan artifact of any kind. Builds directly on Program Intake Sprint 001
(2026-08-04), which proved the system no longer produces false "success" states — this sprint proves it
cannot leave a document in a half-consistent state either.

**Active team**: Chief Systems Architect, Reliability & Failure Recovery Engineer, Evidence & Consistency
Auditor, Security & Trust Auditor, Database & Transaction Integrity Reviewer. All other roles STANDBY, no
Mission Olympus governance phase — same deliberate narrower-scope pattern as Sprint 001.

**Forbidden this sprint**: OCR quality, Case Genome, Decision Engine, Strategy Engine, Copilot, Briefing,
Timeline, Search, Alerts, Tasks, Dashboard, Firm Brain. Findings there are documented, not fixed.

## 0. Method

Three parallel read-only forensic forks investigated: (A) Atomicity & orphan-object audit across all 3
pipelines and the Event Bus, systematically checking 7 artifact types (ghost DB record, orphan blob, orphan
vector, orphan audit, orphan provenance, orphan queue job, ghost case/document combination); (B) Transaction
boundary analysis and canonical state machine design; (C) Idempotency audit and production replay validation.
Full fork outputs: `.vindex_ai_team/decisions/2026-08-05_intake_sprint002_fork_*.md`.

**All three forks independently converged on the same root defect** — Pipeline C's finalize endpoint has an
exploitable check-then-act race that can silently create a full duplicate legal case (case + client + deadline
+ document + Pinecone vectors) under concurrent retry. Three independent investigations reaching the identical
conclusion the same day is the strongest possible internal-consistency signal this session's methodology
produces (matching the "3-way convergence = automatically highest severity" pattern established in earlier
missions this engagement) — this became the sprint's #1 fix.

## 1. What "atomic" actually means in this codebase (the load-bearing finding)

Before anything else could be designed, Fork B proved (not assumed) exactly where real atomicity exists today:

- **`.rpc()` calling a `plpgsql` function is the ONLY mechanism in this codebase capable of multi-statement
  atomicity.** Confirmed: `supabase==2.28.3`/`postgrest==2.28.3` expose no `BEGIN`/`COMMIT` primitive over
  PostgREST; a repo-wide grep for `psycopg2|asyncpg|BEGIN;|\.transaction\(` found one unrelated tooling-script
  hit. Any future multi-step atomicity requirement anywhere in this codebase must be pushed into a Postgres
  function — it cannot be orchestrated from Python.
- **4 RPCs already do this correctly**: `enqueue_intake_job`, `claim_intake_job`, `complete_intake_job`,
  `fail_intake_job` (all migration 073) — each is one `plpgsql` function body, confirmed atomic by reading the
  actual function definitions, not by trusting their names.
- **Everything else — dozens of call sites across all 3 pipelines — is a bare, independently-committed
  `.insert()/.update()/.delete()`.** A sequence of N such calls in one Python function (Pipeline C's finalize
  has 6-8 of them) is N independent transactions, not one. This is the load-bearing fact the rest of this
  report is built on: **this codebase achieves consistency through idempotent, re-runnable steps compensating
  for the absence of rollback, not through transactions wrapping sequences of writes.** `delete_partial_document`
  (Sprint 001) already demonstrates this pattern correctly — deleting already-gone rows by id is a no-op, not
  an error, making it safely re-runnable even without a transaction wrapping the 3 deletes inside it.

## 2. The sprint's central finding: Pipeline C finalize's duplicate-case race

`routers/smart_intake.py::finalize_intake_job`'s own docstring claimed idempotency via a check
(`if job.get("predmet_id"): return already_finalized`), but the column that check reads was only **written** as
the last, unwrapped statement in a 700-line function, after every side effect (predmet insert, client link,
deadline, document, Pinecone ingest) had already independently committed. Two finalize calls for the same
`job_id` close enough together — a double-click, or a frontend timeout retry firing while the first call is
still running server-side (a realistic trigger given this endpoint's own multi-second, multi-GPT-call shape) —
both read `predmet_id=NULL`, both pass the guard, and both run the entire body independently, silently
duplicating a full legal case with no `intake_jobs` row ever pointing back to the loser's object graph.

This is a strictly worse shape than Sprint 001's already-tracked `INTAKE-001` (ghost vector, one lost/mis-signaled
artifact) — it silently creates one full duplicate case file, in an advokatski system of record.

**Fix** (migration 092, drafted not applied): `claim_intake_finalize` RPC, mirroring `claim_intake_job`'s own
`SELECT...FOR UPDATE SKIP LOCKED` pattern exactly — atomically claims the finalize slot (a new
`finalizing_at` column) before any side effect runs. A concurrent second call sees the claim fail and is told,
honestly, one of two distinct things: "already finalized" (if `predmet_id` is now set) or "finalization in
progress, retry shortly" (HTTP 409) — never allowed to silently duplicate. Full detail: `ATOMICITY_VERIFICATION_REPORT.md`.

## 3. What else this sprint fixed

- **`write_processing_outcome()`'s silent exception swallow** (Fork A §B1, Fork B §3.3) — this write is the
  *only* signal Sprint 001's `has_processing_outcome()` trusts as proof a job's processing genuinely finished.
  It was, by original design, allowed to fail silently (best-effort, for `correct_entity()`'s legitimate reason —
  the actual correction there already succeeded before this write runs). But `IntakeWorker._process()` shared
  the same function, meaning a transient DB blip on this one write could let a job reach `status='completed'`
  with real document/entity rows but no outcome row — reopening Sprint 001's own headline bug shape through a
  different door. Fixed via a new `raise_on_error` parameter: `_process()`'s two call sites now request it,
  `correct_entity()`'s does not — the exception now propagates to `_tick()`'s already-proven retry/dead-letter
  machinery for the one caller that actually needs the guarantee, without changing behavior for the other.
- **Pipeline A's orphan-blob exposure, wider than known** (Fork A §A2) — Sprint 001's original-file Storage
  write has 5 distinct downstream raise sites (safety-limit, unreadable-scan, empty-text, Pinecone failure,
  Sentinel hard-fail) that could each leave the just-uploaded encrypted blob permanently orphaned, with *zero*
  tracking infrastructure (worse than Pipeline B's `INTAKE-002`, which at least has a job row). Fixed via a
  compensating cleanup: the entire OCR→Pinecone→DB stretch is now wrapped so that any exception triggers a
  best-effort delete of the just-uploaded blob before the same original error re-raises unchanged.
- **Pipeline B's orphan-blob trigger, broader than scoped** (Fork C, Phase 5 #2) — the original `INTAKE-002`
  was scoped around an RPC-failure edge case; Fork C proved the ordinary sequential duplicate resubmit (no
  failure needed) *always* re-uploaded a fresh blob under a new key even though `enqueue_intake_job` would then
  just return the pre-existing job id, orphaning the new blob on every single duplicate submission. Fixed via
  a pre-upload existence check (skip the Storage write entirely when a job for this content+user already
  exists) plus a compensating delete for the narrower true-concurrent-race case that can still throw.

## 4. What this sprint deliberately deferred (with reasoning)

- **`INTAKE-005`**: Pipeline A's own Pinecone-ghost-vector risk (Fork A §A3) — the same shape as `INTAKE-001`
  but on Pipeline A specifically; the code itself already documents this gap in a comment ("Pinecone vektor
  ostaje... best-effort cleanup nije implementiran ovde"). No compensating Pinecone delete exists on either
  pipeline; implementing one is a genuine new capability (a Pinecone-side delete-on-DB-failure call), which
  this sprint's "no new capability" bound does not license adding unilaterally alongside 4 other fixes already
  landed the same day.
- **`INTAKE-006`**: `intake_jobs.status`'s intermediate values (`classifying`/`extracting`/`matching`/
  `dedup_check`) are declared in the schema's CHECK constraint but never actually written by any code path —
  a real, bounded, zero-migration fix (wire up existing dormant capability), but genuinely optional: it serves
  observability, not consistency, and this sprint's own closing instruction is explicit that consistency wins
  when the two compete.
- **`INTAKE-007`**: a cluster of production-replay blind spots (Fork C Phase 8) — no `ocr_used` column on
  Pipeline A/C's `predmet_dokumenti`, no `document_id` FK from Pinecone chunk metadata back to the case-file
  row, two independent fire-and-forget provenance systems (`audit_immutable` and `ai_forensics`) that can each
  silently no-op with no cross-check, no truncation marker on `tekst_sadrzaj`. None of these cause document
  loss or false success — the gap is specifically in *forensic replay*, not in the case-file artifacts a
  lawyer actually needs. Grouped as one tracked item since they share one root cause (fire-and-forget writes
  with no guarantee, not a bounded bug).
- **Documentation correction, not a defect**: Sprint 001's own `INTAKE_FAILURE_RECOVERY_MATRIX.md` credited
  `dedup_check` as "real dedup infrastructure Pipeline A doesn't have" — Fork C proved this status value is a
  dead schema artifact (declared, never set). The actual dedup mechanism is the `idempotency_key` UNIQUE index.
  The matrix's conclusion was right; its named mechanism was wrong. Corrected in place, not re-argued as a bug.
- **A narrow residual risk from this sprint's own fix #1**: the atomic claim converts "concurrent duplicate,
  any time, unbounded" into "sequential duplicate, only if the final `predmet_id` write itself fails AND a
  retry arrives after the 120-second staleness window." A materially smaller window than before, tracked as an
  open note (not a new ticket) in the Risk Register rather than claimed as a total fix.
- **Not re-litigated, correctly unchanged**: `INTAKE-003` (VERIFIED as a first-class state, `predmet_dokumenti`
  ↔ `intake_jobs` FK) and `INTAKE-004` (Copilot's dead-branch status read, forbidden module) — both already
  correctly deferred by Sprint 001 as founder/product decisions, not bounded reliability fixes.

## 5. Mission closure self-check (against the charter's own success criteria)

- No ghost object can arise → Fixed for the sprint's 2 most severe findings (duplicate case, orphan blobs on
  both pipelines). One known, pre-existing, documented gap remains open (`INTAKE-005`, Pinecone ghost vector),
  deferred with reasoning, not silently ignored.
- Every document has a complete lifecycle → True for the reachable happy path on all 3 pipelines; genuine
  observability gaps (`INTAKE-006`) and replay blind spots (`INTAKE-007`) remain, neither of which causes an
  inconsistent *state*, only an incomplete *audit trail* of a state that is itself consistent.
- Lifecycle state machine is singular → A canonical model is now designed and every pipeline's actual signals
  mapped onto it (`STATE_MACHINE_SPECIFICATION.md`), but full canonicalization (one shared state column across
  all 3 pipelines) is not implemented — the representational gaps are answerable by a derived view without a
  migration; the deeper cross-pipeline fragmentation (`predmet_dokumenti` ↔ `intake_jobs`, `INTAKE-003`) remains
  a founder-decision item, unchanged from Sprint 001's own correct deferral.
- Rollback leaves no inconsistent state → Confirmed: no multi-statement transactions exist to roll back from
  in the first place (§1); consistency is achieved through idempotent re-processing (Sprint 001's
  `delete_partial_document` pattern), which this sprint extended to 2 more failure classes.
- Retry is idempotent → True for job claiming (proven, RPC-atomic), true for Storage+enqueue (fixed this
  sprint), true for `_process()`'s full completion signal (fixed this sprint), true for finalize (fixed this
  sprint, narrowed residual risk noted above).
- Replay is provable → Partially — the case-file artifacts a lawyer needs are durable and reconstructible; the
  forensic "prove exactly what happened and why" layer has real, documented gaps (`INTAKE-007`).
- All tests pass, zero regressions → Confirmed: 2512 passed, 1 skipped (pre-existing, unrelated), 0 failed,
  full suite, after all 4 fixes (was 2502 going into this sprint).

Full detail in the companion documents: `ATOMICITY_VERIFICATION_REPORT.md`, `STATE_MACHINE_SPECIFICATION.md`,
`TRANSACTION_BOUNDARY_ANALYSIS.md`, `FAILURE_INJECTION_REPORT.md`, `REPLAY_VALIDATION_REPORT.md`, updated
`ARCHITECTURAL_DEBT_REGISTER.md`.
