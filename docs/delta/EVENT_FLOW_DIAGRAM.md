# Event Flow Diagram — Program Delta, Sprint 001 (2026-08-05)

## The canonical flow, for any event with a populated `CONSEQUENCE_REGISTRY` entry

```mermaid
flowchart TD
    A["Case Changed<br/>(e.g. finalize_intake_job links a document)"] --> B["Durable emission<br/>INSERT INTO events (event_type, predmet_id, payload, correlation_id)"]
    B --> C["dispatch_pending_events()<br/>(existing, unchanged — migration 073/091 atomic claim)"]
    C --> D["bus.publish_async(event)<br/>(existing, unchanged)"]
    D --> E["handle_case_changed(event)<br/>services/case_evolution.py — THE canonical dispatcher"]
    E --> F{"event.event_id set?"}
    F -- "No" --> F1["Refuse to run — raise<br/>(no durable idempotency key)"]
    F -- "Yes" --> G["Determine Consequences<br/>CONSEQUENCE_REGISTRY[event.type]"]
    G --> H["For each consequence, in order:"]
    H --> I{"Already status='completed'<br/>for (event_id, name)?"}
    I -- "Yes" --> H
    I -- "No" --> J["Execute<br/>mark_pending → run executor"]
    J --> K{"Executor raised?"}
    K -- "Yes" --> K1["mark_failed → re-raise<br/>(dispatch_pending_events' own retry/dead-letter takes over)"]
    K -- "No" --> L["Verify<br/>(executor's OWN return value is already a verified result_ref —\nnever the wrapped function's self-report, e.g. genome_refresh\nre-reads case_dna.verzija independently)"]
    L --> M["mark_completed(event_id, name, result_ref)"]
    M --> N["Audit<br/>log_action('case_evolution_consequence_completed', correlation_id=event.correlation_id, ...)"]
    N --> H
    H -- "all consequences done" --> O["Complete<br/>(implicit — function returns; case left fully consistent)"]
```

## DOCUMENT_ACCEPTED, concretely (this sprint's one wired event)

```mermaid
flowchart LR
    U["finalize_intake_job<br/>(routers/smart_intake.py)"] -->|"1 or more documents linked"| EV["events row:<br/>DOCUMENT_ACCEPTED"]
    EV --> HCC["handle_case_changed"]
    HCC --> GR["genome_refresh<br/>reuses _run_genome_background()<br/>(Genome untouched, unchanged)"]
    HCC --> TL["timeline_entry<br/>predmet_hronologija insert"]
    GR -->|"verzija incremented?"| GRv{"Verify"}
    GRv -- "yes" --> GRc["completed, result_ref=new verzija"]
    GRv -- "no" --> GRf["failed → retry via Event Bus"]
    TL -->|"row inserted?"| TLv{"Verify"}
    TLv -- "yes" --> TLc["completed, result_ref=row id"]
    TLv -- "no" --> TLf["failed → retry via Event Bus"]
```

## What did NOT change

The durable outbox (`events` table), the atomic claim (`claim_pending_events`, migration 091), the
retry/dead-letter loop (`dispatch_pending_events`, `MAX_DISPATCH_ATTEMPTS=5`), and correlation_id propagation
(`shared/ai_provenance.py`) are all **reused exactly as they existed before this sprint** — Program Delta adds
exactly one new layer (`services/case_evolution.py` + `case_evolution_consequences`, migration 096) on top of
proven, already-hardened infrastructure, per this sprint's own "hard token budget" discipline (build the
canonical orchestration mechanism, not a new event system).
