# Intake Flow Diagram — Program Intake Sprint 001 (2026-08-04)

Full narrative and citations: `INTAKE_ARCHITECTURE_REPORT.md`. This is the canonical map of all three live
upload pipelines as of this sprint's fixes.

## Pipeline A — attach document to existing case (synchronous)

```mermaid
flowchart TD
    A["POST /api/predmeti/{id}/upload<br/>api.py:4061"] --> B{File guards<br/>MIME/size}
    B -->|reject| B1[HTTP 415/413]
    B -->|ok| C["Encrypt + upload original<br/>to intake-dokumenti bucket<br/>(NEW this sprint, best-effort)"]
    C -->|fail| C1["storage_path falls back to<br/>old session/{id} label — honest, not silent"]
    C -->|ok| D["storage_path = real key"]
    C1 --> E
    D --> E["OCR extract (tempfile, deleted after)"]
    E -->|scanned/unreadable| E1[HTTP 422]
    E -->|ok| F["Chunk + Pinecone ingest<br/>owner namespace"]
    F -->|quota/429| F1["pinecone_ok=false,<br/>status=sacuvano"]
    F -->|ok| G["status=indeksirano"]
    F1 --> H
    G --> H["INSERT predmet_dokumenti<br/>(Sentinel: hard-fail 500 if this fails<br/>after Pinecone already succeeded)"]
    H --> I["log_action(dokument_upload)<br/>fire-and-forget"]
    I --> J["Background: evidence classify<br/>(unawaited asyncio.create_task,<br/>silent-fail — known race, Gamma Fork E)"]
    I --> K["3 parallel GPT calls:<br/>procena / hronologija / metapodaci"]
    K --> L[HTTP 200 response]
```

## Pipeline B — document-first intake, durable queue

```mermaid
flowchart TD
    A["POST /api/smart-intake/documents<br/>smart_intake.py:92"] --> B["Encrypt (_encrypt)<br/>upload to intake-dokumenti bucket"]
    B -->|upload fails| B1[HTTP error, nothing enqueued]
    B -->|upload ok| C["enqueue_intake_job RPC<br/>→ intake_jobs row, status=received"]
    C -->|RPC fails| C1["ORPHANED BLOB<br/>(INTAKE-002, deferred)<br/>no cleanup job exists"]
    C -->|ok| D["IntakeWorker background loop<br/>(one per gunicorn worker)"]
    D --> E["claim_next_job<br/>SELECT...FOR UPDATE SKIP LOCKED<br/>atomic, race-safe"]
    E --> F["_process(job)"]
    F --> G{"existing = get_job_result(job_id)<br/>document exists?"}
    G -->|no| H[Download+decrypt, OCR, classify, extract]
    G -->|yes, outcome exists too| I["TRUE idempotent skip<br/>(FIXED this sprint)"]
    G -->|yes, outcome MISSING| J["delete_partial_document<br/>(FIXED this sprint —<br/>was the false-success bug)"]
    J --> H
    H --> K["create_document + insert_entities<br/>+ review_queue if low-confidence"]
    K --> L["write_processing_outcome<br/>(the TRUE completion signal)"]
    L --> M["mark_job_completed"]
    F -->|any exception before L| N["mark_job_failed<br/>retry with backoff, then dead-letter"]
```

## Pipeline C — finalize (second synchronous pass over B's already-processed file)

```mermaid
flowchart TD
    A["POST /api/smart-intake/jobs/{id}/finalize<br/>smart_intake.py:373"] --> B["Create predmet (case)<br/>+ client links + hronologija/rok"]
    B --> C["Re-download+decrypt+OCR+chunk<br/>SAME file B's worker already processed"]
    C --> D["Pinecone ingest (owner namespace)"]
    D -->|fail| D1[pinecone_ok=false, status=sacuvano]
    D -->|ok| E[status=indeksirano]
    D1 --> F
    E --> F["3-variant fallback INSERT<br/>predmet_dokumenti"]
    F -->|ALL 3 fail| F1["doc_linked=false<br/>(honest) BUT response still<br/>'ok': true — INTAKE-001, deferred"]
    F -->|any succeeds| G["doc_linked=true"]
    F1 --> H
    G --> H["Background: Genome refresh<br/>+ Evidence classify<br/>(unawaited create_task)"]
    H --> I["HTTP 200: {ok:true, dokument_povezan}"]
```

## Cross-cutting: Event Bus durable outbox (underneath all three)

```mermaid
flowchart LR
    A[Any pipeline writes events row] --> B["4x gunicorn workers,<br/>each own DispatchLoop"]
    B --> C{"Migration 091<br/>(atomic claim) applied?"}
    C -->|NO — current prod state,<br/>KEYSTONE-007 open| D["Plain SELECT dispatch —<br/>live duplicate-dispatch race<br/>for non-idempotent handlers"]
    C -->|yes, not yet run| E[Atomic claim, race-free]
```
