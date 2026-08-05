# Atomicity Verification Report — Program Intake Sprint 002 (2026-08-05)

Phase 2 requirement: prove no combination of failures leaves a ghost/orphan DB record, blob, vector, audit
row, provenance row, or queue job. Full narrative and citations: `.vindex_ai_team/decisions/
2026-08-05_intake_sprint002_fork_atomicity_orphan_audit.md` (Fork A, the source of this table).

**Verdict key**: ✅ ORPHAN-SAFE (mechanism cited) · 🔧 FIXED THIS SPRINT · 🟡 DEFERRED (tracked, reasoned) ·
⬜ N/A (structurally doesn't apply)

| # | Artifact type | Pipeline A | Pipeline B | Pipeline C | Event Bus |
|---|---|---|---|---|---|
| 1 | Ghost/orphan DB record | ✅ FK-protected (`predmet_dokumenti.predmet_id NOT NULL REFERENCES ... ON DELETE CASCADE`, ownership pre-validated) | 🔧 **Fixed** — `write_processing_outcome`'s silent swallow could leave a `completed` job with no outcome row (reopened Sprint 001's own bug shape); now propagates via `raise_on_error=True` | ✅ FK-protected; see #7 for a different, non-FK defect in this same code region | ⬜ (events don't FK-reference intake sub-tables) |
| 2 | Orphan blob | 🔧 **Fixed** — 5 downstream raise sites could orphan the just-uploaded original with zero tracking; now compensating-deleted on any exception | 🔧 **Fixed** — orphaned on every ordinary duplicate resubmit, not only RPC failure; now pre-checked and compensating-deleted | ⬜ reuses B's blob, uploads nothing new | ⬜ |
| 3 | Orphan vector | 🟡 **Deferred, `INTAKE-005`** — self-documented in code, no Pinecone-side rollback exists on either pipeline; new capability, not a bounded fix | ⬜ worker never touches Pinecone (Phase 1A scope boundary) | 🟡 **Already known, `INTAKE-001`**, unchanged — same reasoning as `INTAKE-005` | ⬜ |
| 4 | Orphan audit | ✅ `_dok_id` guard structurally guarantees non-None before the audit call | ✅ FK-protected (`intake_audit_log.intake_job_id NOT NULL REFERENCES`), written in the SAME RPC transaction as the job row it describes | ✅ both audit-adjacent writes execute after `predmet_id` is already validated | 🟡 **Already known, `KEYSTONE-007`** — duplicate alert possible (a duplicate, not a ghost — the referenced job is real), migration 091 not run |
| 5 | Orphan provenance | ✅ same guard as #4 — `case_context()` only ever runs after `_dok_id` is proven non-None | ⬜ no `case_context()` used at classify-time (structurally can't be stale — no `document_id` exists yet) | ✅ same construction-guaranteed pattern as #4 | ⬜ |
| 6 | Orphan queue job | ⬜ no queue on this pipeline | ✅ reap → retry → `max_attempts` → dead-letter is a complete, terminal chain; no infinite non-terminal loop possible | ⬜ doesn't own job-status lifecycle beyond one field | ✅ `MAX_DISPATCH_ATTEMPTS` dead-letters into a terminal, provably-marked state |
| 7 | Ghost case/document combination | ⬜ never creates a `predmet`, only attaches to one pre-validated to exist | ⬜ never creates/attaches a `predmet` | 🔧 **Fixed — the sprint's #1 finding**: the literal "FK to nothing" shape was already safe, but a check-then-act race could silently create a full *duplicate* case (not a ghost of a nonexistent one) — fixed via `claim_intake_finalize` atomic claim (migration 092) | ⬜ |

## Cross-pipeline notes

- **One narrow open question, not a confirmed defect** (Fork A §B6-race): `reap_stale_jobs`'s 300-second
  wall-clock threshold cannot distinguish "worker crashed" from "worker genuinely still alive, mid-retry past
  the threshold." If a worker is legitimately slow (OpenAI backoff) past 300s, the reaper could reset the job
  to `received` while the original is still running, and a second worker could then claim and reprocess it
  concurrently — `intake_documents` has no unique constraint on `intake_job_id` (only a non-unique index), so
  this could in theory produce two rows for one job. No evidence this has actually fired; flagged for
  awareness, not fixed, since it's a generic property of any claimed-at-based reaper design, not something this
  codebase does distinctively wrong.
- **Positive, confirmed-clean result**: all 4 of the queue's own RPCs (`enqueue_intake_job`, `claim_intake_job`,
  `complete_intake_job`, `fail_intake_job`) are `SECURITY DEFINER`, `REVOKE ALL FROM PUBLIC` — never reachable
  from anon/authenticated roles, matching the established `deduct_credit()` precedent. The new
  `claim_intake_finalize` RPC (migration 092) follows the identical grant pattern.
- **Positive, confirmed-clean result**: the Pinecone namespace scheme (`rag_owner_namespace`) remains
  consistent across every write site touched or re-verified this sprint — no drift found, matching Sprint
  001's own earlier confirmation.

## Summary

Of 7 artifact-type × 4 pipeline-surface combinations that structurally apply (28 cells above, 12 marked N/A):
**4 real defects found this sprint, all 4 fixed and regression-tested**; **2 pre-existing gaps reconfirmed
accurate and deliberately deferred** (`INTAKE-001`/new `INTAKE-005`, same root cause, different pipeline); **1
pre-existing gap reconfirmed** (`KEYSTONE-007`, a founder action item, not this sprint's to fix); **1 narrow
open question** flagged for awareness, not a confirmed defect. Every remaining gap has a named severity, a
named reason it wasn't fixed, and a tracking ID — none silently dropped.
