# Architecture + Integration Audit — Program Lambda, Master Sprint 001

Adversarial forensic sweep: does any module recompute existing canonical data, build its own context, let
GPT decide instead of deterministic logic, or bypass the Event Engine? Data integrity: duplicate events,
lost events, lost documents, orphan records, broken lineage. Read-only investigation, findings triaged
after.

## Findings

| # | Finding | Status | Severity |
|---|---|---|---|
| 1 | `KEYSTONE-007` — event dispatch dedup depends on migration `091_event_bus_atomic_claim.sql` being applied in production; if not, 4 gunicorn workers can double-dispatch the same event | Re-confirmed still open, unchanged | High |
| 2 | `SENT-001` — `HEALTH_SCORE_PROMENJEN`/`ROK_KRITICAN` still emitted via in-process-only `emit()`, not the durable outbox; a crash between emission and handler loses the alert silently | Re-confirmed still open, unchanged | High |
| 3 | `client_portal.py`'s upload endpoint returned a false "ok:True, uspešno dostavljen" to the client even when the DB record insert failed after the storage upload succeeded — the lawyer would never see the document | **FIXED this sprint** (compensating delete + honest error, same pattern `smart_intake.py` already uses) | High → Closed |
| 4 | `TAU-012`'s file list (`zadaci.py`, `api.py::predmet_workspace`, `matter_intel.py`, `ccc.py`, `dashboard.py`, `health_index.py`) re-verified accurate — no new member found beyond what's already tracked | Confirmed, not stale | — |
| 5 | Orphan-on-delete risk (deleting a mature case with real children) — the only `predmeti.delete()` call site is a compensating rollback fired only on immediate post-creation failure, before children exist | Checked, not a live risk | — |
| 6 | `correlation_id` propagation through `services/case_evolution.py`'s own consequence handlers | Confirmed still holding | — |

## Verdict

One real, live, previously-undiscovered "false success" bug was found and fixed this sprint (#3) — the
single most consequential finding of this audit, since it directly matches the mission's own explicit
integrity concern ("nema izgubljenih dokumenata"). #1 and #2 are pre-existing, already-tracked findings,
re-confirmed accurate rather than assumed stale — neither improved nor regressed since last checked. No new
parallel-reasoning module was found beyond the already-tracked `TAU-012` family.
