# Event Flow Diagram — Program Delta (living document, updated each sprint)

Sprint 001 (2026-08-05) established the canonical flow below for `DOCUMENT_ACCEPTED`. Sprint 002 (2026-08-05,
"Canonical Event Migration I") reused the EXACT SAME flow for 4 more event types. Sprint 003 (2026-08-05,
"Canonical Event Migration II — Complete Event Convergence") migrates the LAST 2 direct-orchestration call
sites (Pipeline A, `routers/rocista.py`) and wires the LAST event with a genuine consequence need
(`ROCISTE_ZAKAZANO`) — no diagram change needed for the mechanism itself here either; only new concrete flows
(below) and a "before/after, full picture" diagram showing zero remaining bypass paths.

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

## The 4 events wired in Sprint 002, concretely

```mermaid
flowchart LR
    subgraph RA["REVIEW_ACCEPTED"]
        U1["resolve_job_review<br/>(routers/smart_intake.py)"] -->|"review confirmed"| EV1["events row:<br/>REVIEW_ACCEPTED"]
        EV1 --> HCC1["handle_case_changed"]
        HCC1 --> GR1["genome_refresh<br/>(REUSED from DOCUMENT_ACCEPTED —<br/>no-ops pre-finalize)"]
        HCC1 --> TL1["timeline_entry<br/>(REUSED, payload-parameterized text)"]
        HCC1 --> RCA["review_confirmation_audit<br/>dokument_review_resolved"]
    end

    subgraph RR["REVIEW_REJECTED"]
        U2["reject_job_review<br/>(NEW endpoint)"] -->|"review rejected"| EV2["events row:<br/>REVIEW_REJECTED"]
        EV2 --> HCC2["handle_case_changed"]
        HCC2 --> RRA["review_rejection_audit<br/>dokument_review_rejected<br/>(ONLY consequence — no genome/timeline)"]
    end

    subgraph CL["NEW_CLIENT_LINKED"]
        U3["finalize_intake_job<br/>(client linked)"] --> EV3["events row:<br/>NEW_CLIENT_LINKED"]
        EV3 --> HCC3["handle_case_changed"]
        HCC3 --> CC["conflict_check<br/>REUSES _run_conflict_check +<br/>create_proactive_alert, UNCHANGED"]
    end

    subgraph EA["NEW_EVIDENCE_REGISTERED"]
        U4["finalize_intake_job<br/>(per accepted document)"] --> EV4["events row:<br/>NEW_EVIDENCE_REGISTERED"]
        EV4 --> HCC4["handle_case_changed"]
        HCC4 --> EC["evidence_classification<br/>REUSES klasifikuj_i_sacuvaj, UNCHANGED<br/>re-reads tekst_sadrzaj, verifies klasifikovan_at"]
    end
```

## The 2 events wired in Sprint 003, concretely

```mermaid
flowchart LR
    subgraph PA["Pipeline A upload — DOCUMENT_ACCEPTED + NEW_EVIDENCE_REGISTERED"]
        U1["predmet_upload_auto_analyze<br/>(api.py, per-case upload)"] -->|"1. evidence first"| EV1["events row:<br/>NEW_EVIDENCE_REGISTERED"]
        U1 -->|"2. genome second"| EV2["events row:<br/>DOCUMENT_ACCEPTED"]
        EV1 --> HCC1["handle_case_changed"]
        EV2 --> HCC2["handle_case_changed"]
        HCC1 --> EC["evidence_classification<br/>(REUSED from Sprint 002, unchanged)"]
        HCC2 --> GR["genome_refresh (REUSED)"]
        HCC2 --> TL["timeline_entry (REUSED —<br/>NEW for Pipeline A: it never<br/>produced one before)"]
    end

    subgraph RZ["ROCISTE_ZAKAZANO — first-ever wiring"]
        U2["kreiraj_rociste<br/>(routers/rocista.py)"] --> EV3["events row:<br/>ROCISTE_ZAKAZANO"]
        EV3 --> HCC3["handle_case_changed"]
        HCC3 --> GR2["genome_refresh (REUSED,<br/>ONLY consequence — no timeline,<br/>this endpoint never had one)"]
    end
```

## What did NOT change

The durable outbox (`events` table), the atomic claim (`claim_pending_events`, migration 091), the
retry/dead-letter loop (`dispatch_pending_events`, `MAX_DISPATCH_ATTEMPTS=5`), and correlation_id propagation
(`shared/ai_provenance.py`) are all **reused exactly as they existed before Sprint 001** — Program Delta adds
exactly one new layer (`services/case_evolution.py` + `case_evolution_consequences`, migration 096) on top of
proven, already-hardened infrastructure. Sprint 002 adds one small refactor on top of that same layer —
`services/event_bus.py::emit_durable()` — factoring Sprint 001's own single emission idiom into one shared
function instead of copying its try/except/fallback boilerplate at each of the 4 new call sites (and
retrofitting `DOCUMENT_ACCEPTED`'s own Sprint-001 emission site to use it too) — still no new retry/dead-letter
machinery, just one fewer copy of the same code. Sprint 003 uses `emit_durable()` at 2 more call sites
(`api.py`, `routers/rocista.py`) and wires 2 EXISTING consequence executors (`genome_refresh`,
`evidence_classification`) to a 6th event type (`ROCISTE_ZAKAZANO`) — zero new consequence logic, zero new
Genome/Timeline/Evidence capability, zero new retry/audit/provenance machinery. Every reusable piece built in
Sprints 001-002 was reused, not rebuilt, a 3rd consecutive sprint.
