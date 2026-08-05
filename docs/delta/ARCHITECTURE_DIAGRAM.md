# Updated Architecture Diagram — Program Delta, Sprint 001 (2026-08-05)

## Before this sprint

```mermaid
flowchart TD
    FI["finalize_intake_job<br/>(Program Intake, bulletproof since Sprint 007)"]
    FI -->|"direct call"| GB["_run_genome_background()<br/>(Genome)"]
    FI -->|"direct call"| EC["klasifikuj_i_sacuvaj()<br/>(Evidence Vault)"]
    FI -->|"direct call"| CC["_run_conflict_check()<br/>(Conflict check → proactive_alerts)"]

    U2["api.py::predmet_upload (Pipeline A)"] -->|"direct call"| GB
    U3["routers/rocista.py"] -->|"direct call"| GB

    style FI fill:#333,color:#fff
```

Three independent call sites each decide, for themselves, "what happens after a case changes" — no shared
mechanism, no unified idempotency story, no unified audit trail for "a consequence of a case change happened."

## After this sprint

```mermaid
flowchart TD
    FI["finalize_intake_job<br/>(Program Intake, bulletproof)"]
    FI -->|"durable event emission"| EV["events (outbox)<br/>DOCUMENT_ACCEPTED"]
    EV --> DPE["dispatch_pending_events()<br/>(Event Bus, unchanged)"]
    DPE --> HCC["handle_case_changed()<br/>Canonical Consequence Engine<br/>services/case_evolution.py"]
    HCC -->|"consequence"| GB["_run_genome_background()<br/>(Genome, UNCHANGED)"]
    HCC -->|"consequence"| TL["predmet_hronologija insert<br/>(Timeline)"]
    HCC -.->|"tracked in"| CEC[("case_evolution_consequences<br/>(migration 096)")]

    FI -->|"NOT YET migrated — named in registry"| EC["klasifikuj_i_sacuvaj()<br/>(Evidence Vault)"]
    FI -->|"NOT YET migrated — named in registry"| CC["_run_conflict_check()"]
    U2["api.py::predmet_upload (Pipeline A)"] -->|"NOT YET migrated — named in registry"| GB
    U3["routers/rocista.py"] -->|"NOT YET migrated — named in registry"| GB

    style HCC fill:#333,color:#fff
    style CEC fill:#222,color:#fff
```

## What changed, structurally

- **One canonical dispatcher** (`handle_case_changed`) now owns "what follows `DOCUMENT_ACCEPTED`" — Pipeline
  C's own Genome-refresh trigger no longer decides for itself; it emits an event and the dispatcher decides.
- **One new durable table** (`case_evolution_consequences`) makes every consequence's completion state
  independently trackable and retry-safe, without inventing a parallel event log — it hangs directly off the
  already-durable `events` table (migration 073).
- **Genome, Timeline, Evidence Vault, and the conflict-check mechanism are themselves completely untouched** —
  per the mission's own explicit prohibition. The consequence engine calls them exactly as they were called
  before, just from one canonical place instead of an ad-hoc inline call.

## What deliberately still looks like "before," named honestly

Pipeline A's own Genome trigger, `routers/rocista.py`'s own Genome trigger, and Pipeline C's own Evidence
Vault/conflict-check calls are UNCHANGED this sprint — real, existing "scattered decision" call sites,
documented in `CASE_EVOLUTION_REGISTRY.md`'s own Task 3 findings table, not migrated under this sprint's hard
2-agent budget. Migrating them is mechanical (same registry, same dispatcher, a different emission call site)
and is the natural next Delta sprint's own bounded scope.
