# Omega Architecture Map — Program Omega, Master Sprint 001 (2026-08-06)

Obligatory audit, produced before any code was written, per the mission's own explicit instruction. Traces
the full advocate-facing chain — Upload → OCR → Segmentation → Classification → Case Assimilation → Case
Evolution Engine → Case Genome → Timeline → Deadlines → Tasks → Evidence → Alerts → Firm Brain → Copilot
Context → AI Briefing → Search Index → Audit → Dashboard — as INPUT → PROCESS → DECISION → CONSEQUENCE → USER
VALUE for each real link in the chain. Every claim below is grounded in code read during this sprint (file
paths given), not assumed from prior session memory.

## 1. Upload

| | |
|---|---|
| INPUT | 1-N files (`POST /api/smart-intake/documents`, `files: List[UploadFile]`) |
| PROCESS | Per file, sequentially, inside ONE HTTP request: suffix validation → read bytes → size check → content-hash idempotency pre-check → AES-GCM encrypt → Supabase Storage upload → `enqueue_job` RPC (durable, atomic) |
| DECISION | Reject unsupported suffix / oversized / empty file (per file, doesn't abort the batch); reuse an existing job if `idempotency_key` (user+content-hash) already exists |
| CONSEQUENCE | One durable `intake_jobs` row per accepted file, status `'received'`, immediately visible to the background `IntakeWorker` |
| USER VALUE | Immediate 202 + per-file `job_id` — the lawyer never waits for OCR to get a response |
| **BREAK FOUND, FIXED THIS SPRINT** | For large batches (Priority 1's own 500-document scenario), this synchronous per-file loop could exceed gunicorn's 120s worker timeout, killing the connection mid-batch with no structured partial-progress response. Fixed: a 90s time-budget check now returns a clean, resumable `{"nastavlja": true, "preostali_fajlovi": [...]}` response before the real timeout hits — see `OCR_AND_INTAKE_CAPACITY_REPORT.md`. |

## 2. OCR / Extraction

| | |
|---|---|
| INPUT | `intake_jobs` row, `status='received'` |
| PROCESS | `IntakeWorker._tick()` claims ONE job at a time (`claim_next_job`, atomic), decrypts, calls `uploaded_doc/extractor.py::extract()` (OCR for scans, text extraction for native PDFs/DOCX) |
| DECISION | Route to `preprocessing`/`classifying`/`extracting` status chain; safety-limit/empty-text failures raise a clear, typed error |
| CONSEQUENCE | `intake_jobs.status` advances; extracted text held for the next stage |
| USER VALUE | No lawyer action needed — happens entirely in the background |
| Scaling note | One job per worker tick, adaptive polling (no wait if more work exists) — throughput is bounded by total OCR/GPT time across all jobs, not broken by count alone (unlike the synchronous upload endpoint above) |

## 3. Document Segmentation

| | |
|---|---|
| INPUT | Extracted text of one uploaded file |
| PROCESS | Program Intake Sprint 005's own segmentation — detects whether one uploaded PDF actually contains MULTIPLE distinct documents (a "haotična fascikla" scanned as one file) and splits into `intake_job_segments` rows |
| DECISION | One document vs. N documents per uploaded file — never assumes "1 PDF = 1 document" (the mission's own explicit requirement, already built pre-Omega) |
| CONSEQUENCE | Each segment gets its own classification/extraction pass, its own eventual `predmet_dokumenti` row |
| USER VALUE | A scanned bundle of 10 different filings in one PDF becomes 10 correctly-separated documents, not one garbled blob |

## 4. Classification

| | |
|---|---|
| INPUT | Extracted text (per document/segment) |
| PROCESS | Pipeline B's confidence-gated classifier (document type, entities) |
| DECISION | Confidence ≥ `AUTO_ACCEPT_THRESHOLD` → auto-accept; below → `Review Required` (`intake_review_queue`), NEVER silently guessed (Program Intake Sprint 003's own central invariant) |
| CONSEQUENCE | `document_type`, extracted entities, confidence scores stored; low-confidence documents block finalize until a human resolves or explicitly rejects (`REVIEW_ACCEPTED`/`REVIEW_REJECTED`, Program Delta Sprint 002) |
| USER VALUE | The lawyer is told EXACTLY which documents need a look, not left to guess |

## 5. Case Assimilation (Ownership Resolution)

| | |
|---|---|
| INPUT | A classified document + its extracted case number/client name |
| PROCESS | `shared/case_assimilation.py` — deterministic content-hash duplicate check, case-number canonical matching, client-name matching (never a filename/date heuristic) |
| DECISION | Attach to an existing `predmet`, create a new one, or route to Review Required if evidence is ambiguous — NEVER guesses (Program Intake Sprint 006's own central invariant) |
| CONSEQUENCE | `predmet_dokumenti` row created, linking the document to exactly one case |
| USER VALUE | 500 chaotic documents converge onto the RIGHT existing cases automatically — this is the mechanism that makes "1 postojeći predmet" in the mission's own example possible |

## 6. Case Evolution Engine (the canonical orchestrator, certified Program Delta Sprint 004)

| | |
|---|---|
| INPUT | A durable event: `DOCUMENT_ACCEPTED`, `NEW_EVIDENCE_REGISTERED`, `NEW_CLIENT_LINKED`, `REVIEW_ACCEPTED`, `REVIEW_REJECTED`, `ROCISTE_ZAKAZANO` |
| PROCESS | `services/case_evolution.py::handle_case_changed` — ONE dispatcher, `(event_id, consequence_name)`-keyed idempotency, reused across every emission site |
| DECISION | Which consequences apply to this event type (`CONSEQUENCE_REGISTRY`) |
| CONSEQUENCE | Genome refresh, Timeline entry, Evidence classification, conflict-check alert, or a domain-specific audit row — depending on event type, per the certified Event Coverage Matrix |
| USER VALUE | ONE place decides "what happens next" — certified, in Program Delta Sprint 004, to have zero bypasses |
| **BREAK FOUND, FIXED THIS SPRINT** | No batch orchestration existed on top of this — each of up to 500 separately-uploaded files needed its own manual `POST .../finalize` call, and the Case Evolution Engine itself was never the problem (it was never reachable at scale in the first place). Fixed: `POST /jobs/finalize-batch` (see §12 below). |

## 7. Case Genome

| | |
|---|---|
| INPUT | `genome_refresh` consequence, triggered by `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO` |
| PROCESS | `routers/case_dna.py::_run_genome_background` — full GPT-based recompute: facts, parties, contradictions (`kontradikcije`), case strength |
| DECISION | Runs asynchronously, once per triggering event (never once per document within a multi-document finalize call — Sprint 001's own coalescing design) |
| CONSEQUENCE | `predmeti.case_dna` updated, `verzija` incremented (independently verified, not self-reported), `GENOME_UPDATED` emitted for audit |
| USER VALUE | The case "gets smarter" automatically as documents arrive — the mission's own central question ("da li predmet postaje pametniji?") |
| Scaling note, NOT fixed this sprint | If 500 documents all belong to ONE case and each is finalized as its own separate `DOCUMENT_ACCEPTED` event (still true even after this sprint's batch-finalize endpoint, which loops per-job), Genome recomputes in full up to 500 times for one case. Named honestly in `OCR_AND_INTAKE_CAPACITY_REPORT.md`, not silently fixed — de-duplicating this would mean changing `_finalize_intake_job_core`'s own emission behavior, a bigger, riskier change than this sprint's own scope allowed. |

## 8. Timeline

| | |
|---|---|
| INPUT | `timeline_entry` consequence (`DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`) |
| PROCESS | One `predmet_hronologija` row per triggering event |
| CONSEQUENCE | Case history is visible without the lawyer manually logging "document received" |
| USER VALUE | Automatic chronology — no manual note-taking for routine document receipt |

## 9. Deadlines

| | |
|---|---|
| INPUT | `finalize_intake_job`'s own deadline-extraction step (`value_map.get("deadline")`), independent of Case Evolution's own event consequences |
| PROCESS | If a deadline was extracted with sufficient confidence, a `predmet_hronologija`/deadline row is inserted directly as part of the SAME finalize call (a primary action, not a reactive consequence — same category as document-linking itself) |
| DECISION | Confidence-gated; low-confidence extractions do not silently create a deadline |
| USER VALUE | `rok_dodat: true` in the finalize response — now aggregated across the WHOLE batch in `finalize-batch`'s own summary this sprint |

## 10. Tasks

| | |
|---|---|
| STATUS | **NOT auto-created by any of the 6 Case Evolution events** (confirmed, Program Delta Sprint 004's own Event Coverage Matrix — every `NE` verdict for "Tasks" across all 6 events). Task creation exists (`routers/zadaci.py`) but is either lawyer-initiated or driven by a SEPARATE, older AI analysis endpoint (`ai_analiziraj_predmet`), not wired to document acceptance |
| USER VALUE TODAY | None automatic — a real, honest gap against the mission's own Prioriet 4 ("automatski rokovi i zadaci") |

## 11. Evidence

| | |
|---|---|
| INPUT | `evidence_classification` consequence (`NEW_EVIDENCE_REGISTERED`) |
| PROCESS | `routers/evidence.py::klasifikuj_i_sacuvaj` — evidence-type tagging (`tip_dokaza`), reused unchanged since Sprint 002 |
| CONSEQUENCE | `predmet_dokumenti.tip_dokaza` set, feeding `services/risk_engine.py`'s own missing-evidence detector |
| USER VALUE | "7 nedostajućih dokaza" in the mission's own example is computable TODAY by calling `identify_case_problems()` per case — reused, not invented, by this sprint's new batch summary (see §12) |

## 12. Alerts

| | |
|---|---|
| INPUT | `conflict_check` consequence (`NEW_CLIENT_LINKED`) |
| CONSEQUENCE | `proactive_alerts` row when a real conflict is found |
| STATUS | The ONLY automatic alert tied to document/case-change events today; deadline-risk alerts (`ROK_KRITICAN`) exist but are NOT durably/reliably wired (Project Sentinel's still-open `SENT-001`, unrelated to this sprint) |

## 13. Firm Brain / Memory Graph

| | |
|---|---|
| STATUS | **Confirmed, again, zero auto-population mechanism exists anywhere in `services/`** (re-verified this sprint by the same grep Program Delta Sprint 004 already ran) — a pre-existing, previously-documented gap (`WOW-003`, Operation Invisible Features `IF-005`), not created or worsened by Omega |

## 14. Copilot Context / AI Briefing

| | |
|---|---|
| STATUS | Both READ Case Genome as context (Project Synapse, 2026-08-03) — they benefit automatically from every Genome refresh a document triggers, with NO additional wiring needed. This is the one link in the chain where "document arrives → downstream intelligence updates" already works end-to-end, for free, via Genome as the shared source of truth |

## 15. Search Index

| | |
|---|---|
| PROCESS | Pinecone ingestion happens SYNCHRONOUSLY as part of the PRIMARY upload/finalize action (before any Case Evolution event is even emitted) |
| USER VALUE | A document is searchable immediately, not lagging behind async event processing — by design, not an oversight (Program Delta Sprint 004's own certified finding) |

## 16. Audit

| | |
|---|---|
| STATUS | Comprehensive across every step in this chain — `log_action` at primary-action sites, `case_evolution_consequence_completed` per Case Evolution consequence, all correlation_id-linked (certified, Program Delta Sprint 004) |

## 17. Dashboard

| | |
|---|---|
| STATUS | Query-time aggregation — nothing to "refresh," no materialized artifact any event needs to update (certified, Program Delta Sprint 004) |

## Where the chain genuinely breaks, ranked

1. **Upload endpoint timeout risk for large batches** — FIXED this sprint (§1).
2. **No batch-level finalize/summary** — FIXED this sprint (§6, §12).
3. **Genome recomputes once per document even within a same-case batch** — NOT fixed this sprint, named honestly (§7).
4. **No automatic Task creation from document acceptance** — NOT fixed this sprint, a real Priority 4 gap (§10).
5. **Firm Brain/Memory Graph auto-population** — pre-existing, unrelated to Omega, not attempted.

Full detail on each: `OCR_AND_INTAKE_CAPACITY_REPORT.md`, `CASE_INTELLIGENCE_AUTOMATION_REPORT.md`.
