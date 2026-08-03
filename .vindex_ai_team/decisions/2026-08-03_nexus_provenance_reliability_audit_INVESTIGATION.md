# Project Nexus — AI Provenance & Reliability Audit

Read-only. All claims grounded in direct file reads this session; no code changed.

---

## PART A — AI Action Provenance (7-field capture audit)

Legend: **Y** = captured and stored, **P** = partially/implicitly captured, **N** = not captured anywhere.

| AI call site | user | timestamp | input reference | model | prompt version | output hash | confidence |
|---|---|---|---|---|---|---|---|
| **Case Genome** (`routers/case_dna.py::_extract_genome`) | P | P | N | N | N | N | P |
| **AI Briefing** (`routers/case_intelligence.py`) | Y | P | N | N | N | N | Y |
| **Smart Intake extraction** (`shared/intake_extract.py`) | P | P | Y | P | N | N | Y |
| **Document classification** (`shared/intake_classify.py`) | P | P | Y | P | N | N | Y |
| **AI Drafting** (`routers/drafting.py`) | Y | P | N | N | N | N | Y |
| **Evidence Vault classification** (`routers/evidence.py::klasifikuj_i_sacuvaj`) | Y | P | Y | N | N | N | N |

### Case Genome
- `user`: **P** — the genome blob (`predmeti.case_dna`) has no embedded "generated_by" field; ownership is only implicit via the parent `predmeti.user_id` row, not stored as AI-output provenance.
- `timestamp`: **P** — no explicit timestamp inside the `case_dna` JSON itself, but `_save_genome_history` (called every refresh, `case_dna.py:856`) snapshots the prior version, and `on_genome_updated` (`services/event_bus.py:149`) writes a `genome_refresh` row to the immutable audit log with its own DB-default `created_at` — so a timestamp exists one hop away, not on the object itself.
- `input reference`: **N** — no array of `predmet_dokumenti` IDs that were actually fed into a given Genome version is stored; only a doc count (`_genome_docs_count`) and a Serbian filename-based header inside the combined GPT prompt text, not persisted separately.
- `model`: **N** — `"gpt-4o"` is a hardcoded string literal in `_pozovi_genome_api` (`case_dna.py:209`), never written into the stored `genome` dict.
- `prompt version`: **N** — `_GENOME_SYSTEM` is a plain Python string constant with no version identifier anywhere in this repo.
- `output hash`: **N** — the raw JSON response is parsed and reshaped (`compute_snaga_score` overwrites 3 fields) before storage; nothing hashes the original or final output.
- `confidence`: **P** — no single numeric "confidence in this analysis" field exists, but `genome_kompletnost` (visoka/srednja/niska) is a self-reported completeness signal, and `_verifikacija` (Faza 1.3, `shared/genome_validator.py::verify_genome`, zero GPT calls, rule-based) produces a categorical `odluka` (approve/approve_with_warning/require_review) that functions as a real, deterministic confidence gate on top of the LLM output.

### AI Briefing
- `user`: **Y** — `decision_log` insert (`case_intelligence.py:346`) explicitly stores `user_id`.
- `timestamp`: **P** — not explicit in the insert dict; relies on `decision_log`'s DB-default `created_at` (confirmed pattern: `services/decision_log.py`'s own insert also omits an explicit timestamp field).
- `input reference`: **N** — `predmet_id` is stored, but no reference to which of the 8 aggregated data sources' specific rows fed the answer (e.g., which `lessons_learned` IDs).
- `model`: **N** — `"gpt-4o"` hardcoded (`case_intelligence.py:41`), never stored.
- `prompt version`: **N** — same as Genome, no versioning concept exists.
- `output hash`: **N**.
- `confidence`: **Y** — `pouzdanost_briefinga` (visoka/srednja/niska) is both returned to the caller AND explicitly persisted into `decision_log.kontekst.pouzdanost` (`:353`) — the only call site of the 6 audited that stores its own confidence signal in the SAME durable record as the rest of its provenance.

### Smart Intake extraction (`shared/intake_extract.py`)
- `user`: **P** — entities are linked via `document_id` → `intake_documents.intake_job_id` → `intake_jobs.uploaded_by`; no direct `user_id` column on `extracted_entities` itself (traceable, not stored redundantly).
- `timestamp`: **P** — DB-default `created_at`, not explicit in application code.
- `input reference`: **Y** — `extracted_entities.document_id` is a real foreign key back to the exact source document (`shared/intake_documents.py::insert_entities`).
- `model`: **P** — `extraction_method` (`"regex"` or `"llm"`, `shared/intake_extract.py:247/250/253/267`) is stored per entity — a coarse model-class signal, not the specific model string (`"gpt-4o-mini"`, hardcoded at `:211`, never persisted).
- `prompt version`: **N**.
- `output hash`: **N**.
- `confidence`: **Y** — per-entity `confidence` (0-1 float) is a first-class stored column, the richest confidence capture of all 6 sites audited.

### Document classification (`shared/intake_classify.py` → `shared/intake_documents.py::create_document`)
- `user`: **P** — same traceability-not-redundancy pattern as extraction, via `intake_job_id`.
- `timestamp`: **P** — DB-default only.
- `input reference`: **Y** — `intake_documents.intake_job_id` FK.
- `model`: **P** — `classification_method` stored (same regex/llm coarse signal), not the literal model string (`"gpt-4o-mini"`, `intake_classify.py:98`).
- `prompt version`: **N**.
- `output hash`: **N**.
- `confidence`: **Y** — `classification_confidence` + separately-tracked `ocr_confidence`, both real stored columns (`shared/intake_documents.py:37-39`).

### AI Drafting (`routers/drafting.py`)
- `user`: **Y** — `_stage_draft_for_review` (`:199`) stores `user_id` and `kancelarija_id` on the `staging_memory` row.
- `timestamp`: **P** — DB-default only (no explicit timestamp field in the insert dict at `:217-228`).
- `input reference`: **N** — the draft's own generated text is stored (`tekst`), but no reference to which RAG-retrieved source chunks / prior documents informed generation.
- `model`: **N** — `"gpt-4o-mini"`/`"gpt-4o"` hardcoded across 4 separate call sites in this file (`:376,637,725,740,792`), never stored on the staging row.
- `prompt version`: **N**.
- `output hash`: **N**.
- `confidence`: **Y** — `confidence_score` (from `services/quality_gate.py::evaluate_draft_quality`) is a real, stored, computed value (not self-reported by the LLM — see Part B item 8 for how it's computed) that gates whether an approved draft is promoted to the searchable case record (`_APPROVAL_CONFIDENCE_THRESHOLD = 0.85`).

### Evidence Vault classification (`routers/evidence.py::klasifikuj_i_sacuvaj`)
- `user`: **Y** — `predmet_dokazi` rows explicitly store `user_id` (`:199`).
- `timestamp`: **P** — DB-default only.
- `input reference`: **Y** — `predmet_dokazi.dokument_id` FK to the exact source document (`:198`).
- `model`: **N** — model string never stored (confirmed via `_klasifikuj_dokument`, not independently re-checked in full but no storage call anywhere in `klasifikuj_i_sacuvaj` writes a model field).
- `prompt version`: **N**.
- `output hash`: **N**.
- `confidence`: **N** — the closest field, `predmet_dokazi.snaga` ("strength": jaka/srednja/slaba), is **hardcoded to `"srednja"` for every single row** (`:202`), not derived from any LLM-reported confidence — this is the one call site of the 6 where NO real confidence signal reaches storage at all, even though `_klasifikuj_dokument`'s own return dict may contain richer signal upstream (not traced further — out of this audit's scope, flagging precisely what's persisted, not what's computed and discarded).

### Cross-cutting Part A finding
**No call site of the 6 audited stores `model`, `prompt version`, or `output hash` anywhere.** This is a uniform gap, not specific to any one module — every AI call in this repository hardcodes its model string in Python source and has zero prompt-versioning or output-fingerprinting concept. `confidence` and `input reference`, by contrast, are well-captured in the Smart Intake pipeline (extraction, classification) and partially in Drafting/Briefing, but structurally absent in Case Genome (no confidence number, only a categorical completeness/verification signal) and functionally absent in Evidence Vault (a hardcoded placeholder, not real signal).

---

## PART B — Reliability / Failure-Mode Audit

### 1. OCR fails
**Verdict: handled well.** `DocumentSafetyLimitExceeded` (zip-bomb/decompression-bomb/pixel-count guards) raises a specific exception caught by callers and turned into a clear HTTP 413 with a Serbian user-facing message (confirmed at `api.py`'s upload endpoint: `"Fajl je odbijen — sadržaj posle raspakivanja prelazi bezbednosni limit."`). A genuinely unreadable scan produces `is_scanned=True` with empty text, surfaced as HTTP 422: `"Tekst nije čitljiv ni optičkim prepoznavanjem (OCR)..."` (fixed wording, Operation Lawyer Day). Both are real HTTP errors with actionable messages, not silent failures.

### 2. LLM call times out
**Verdict: handled well for retry, handled POORLY for post-exhaustion UX in at least one confirmed case.** `shared/llm_retry.py`'s `@llm_retry` decorator: max 3 attempts, exponential backoff (1-8s), retries only transient errors (429/5xx/timeout/connection — NOT 400/401), `reraise=True` after exhaustion — the original exception propagates to the caller. For Case Genome specifically, the caller (`_extract_genome`, `case_dna.py:309-312`) catches this and returns `{"greska": str(exc)}`, which the endpoint stores and returns with HTTP 200 (not an error status).

**Confirmed silent-failure bug in the frontend**: `static/vindex.js::_voice_refresh_case_dna` (`:17053-17081`) never checks `data.case_dna.greska` — it unconditionally shows `showToast('Procena predmeta ažurirana' ..., kontr ? 'warn' : 'ok')` (a success/neutral toast) even when the refresh genuinely failed. The separate render function `_caseDnaRender` (`:17370-17375`) DOES correctly check `dna.greska` and hides the panel — but by then the lawyer has already been told, via toast, that the assessment "was updated." Net effect: on a genuine LLM failure, a lawyer sees a green "success" notification and then nothing appears — a confusing, silently-contradictory UX, not a clean error.

### 3. Embedding/Pinecone service unavailable
**Verdict: handled well, consistently.** Confirmed across at least 2 independent ingestion paths (`api.py`'s per-case upload, `routers/smart_intake.py`'s finalize): both wrap `ingest_session(...)` in try/except, set a local `pinecone_ok = False` on failure, and still complete the document insert with `"status": "sacuvano"` instead of `"indeksirano"` — the document is never lost, just marked as not-yet-searchable. No user-facing error is shown for this specific failure (it's treated as a soft-degrade, consistent with the rest of this codebase's fail-soft philosophy for auxiliary enrichment), which is a reasonable, deliberate choice given the document itself is never lost.

### 4. Event lost (in-process Event Bus path)
**Verdict: confirmed real gap — the one true in-process `emit()` call site has zero durability.** `api.py:3264`'s `emit(EventType.PREDMET_KREIRAN, ...)` calls `bus.publish()`, which (per `services/event_bus.py`) only does `loop.create_task(_run())` — a fire-and-forget in-memory asyncio task with **no corresponding row written to the durable `events` table** (unlike `GENOME_UPDATED`/`DOCUMENT_JOB_*`, which use a separate direct-insert-to-outbox pattern specifically to survive a restart). If the process crashes or is redeployed between the `emit()` call and `on_predmet_kreiran`'s completion (which triggers the entire Case Pipeline — chronology, risk, strategy, etc.), the event is genuinely and silently lost: no retry, no record it was ever supposed to happen, no way for any monitoring to detect the gap. The `try/except` around the `emit()` call itself (`api.py:3262-3267`) only catches synchronous errors (e.g., import failure) — it cannot catch or detect a later async handler crash.

### 5. Database transaction fails mid-write
**Verdict: confirmed — no rollback exists anywhere in this pattern; partial failure is silent by design (fail-soft), which is a deliberate tradeoff, not an oversight, but genuinely leaves inconsistent data.** Traced Smart Intake's `finalize_intake_job`: `predmeti` insert (or attach), then klijent lookup/link, deadline/`predmet_hronologija` insert, document/`predmet_dokumenti` insert, Pinecone ingest — each wrapped in its OWN independent try/except, none transactional, no compensating rollback if a later step fails after an earlier one succeeds. This is consistent throughout the codebase (the same pattern appears in `api.py`'s older upload path). The response DOES honestly report partial success (`klijent_dodat`, `rok_dodat`, `dokument_povezan` booleans) — so the lawyer isn't lied to about what happened, but nothing automatically retries a failed sub-step, and there's no alert if, say, the deadline insert silently failed while the case was created successfully.

### 6. Lawyer uploads a genuinely bad/corrupted PDF
**Verdict: handled well, traced end to end.** `extract_pdf` raises `DocumentSafetyLimitExceeded` for a bomb-shaped file, or returns `is_scanned=True` for genuinely unreadable content; both propagate as clear HTTP 413/422 errors with specific Serbian messages, confirmed at both `api.py`'s and `smart_intake.py`'s upload endpoints (LD-001 fix, Operation Lawyer Day, extended this to also cover image formats).

### 7. Document has internally conflicting information
**Verdict: this is a designed, working capability, not a gap.** Case Genome's `kontradikcije` field is explicitly designed to detect and surface this (`_GENOME_SYSTEM` prompt: `"kontradikcije": [{"opis": "Tacno sta se kosi...", "lokacija_1":..., "lokacija_2":..., "tezina": "kriticna|vazna|manja"}]`), with an explicit anti-hallucination instruction not to guess a location if one isn't clearly stated in the text. `shared/genome_validator.py::verify_genome` additionally has a rule-based `_validate_kontradikcije_lokacije` check (zero GPT calls) that verifies claimed contradiction locations actually appear in the source documents before trusting them.

### 8. AI hallucination (false citation/fact)
**Verdict: two real, distinct guardrail mechanisms exist — stronger than a bare prompt instruction, though neither is a full fact-verification system.**
- **Quality Gate citation existence check** (`services/quality_gate.py::evaluate_draft_quality` → `_verify_citation`): every "Član N" (Article N) citation extracted from a generated draft is checked against the real statute corpus via `_direktan_fetch_clana` — a genuine existence lookup, not just an LLM self-report. A citation to an article that doesn't actually exist lowers `citation_score`, which feeds `confidence_score`, which gates promotion into the searchable case record (`_APPROVAL_CONFIDENCE_THRESHOLD = 0.85`). Scope limit: verifies the article NUMBER exists, not that the draft's characterization of what it says is accurate.
- **Legal Reasoning Engine's SOURCE-n/FACT-n identity constraint** (`services/legal_reasoning_engine.py`): a structurally stronger mechanism — the model is given only pre-retrieved sources, each assigned a `SOURCE-n` ID, and instructed it may cite ONLY these IDs, never invent a new one. Confirmed via `_build_reasoning_prompt` (`:137-165`) and `_retrieval_agreement` (`:202`, computes how well cited sources match actual retrieval). This makes fabricating a citation structurally harder (there's no slot for an invented "SOURCE-99"), not merely discouraged by instruction.

Neither mechanism reaches Case Genome or the AI Briefing — both of those trust GPT-4o's own output directly with only a prompt instruction ("Ne halucinuj... Izvlaci SAMO ono sto pise u dokumentima") and no structural or lookup-based verification. This is a real, uneven distribution of hallucination protection across the 6 audited call sites, not present everywhere.

### 9. Confidence drops (beyond Smart Intake's per-entity `needs_review`)
**Verdict: one more real instance found, beyond the already-known entity-level flagging.** `routers/drafting.py`'s `confidence_score < 0.85` genuinely blocks a DIFFERENT code path — not user-facing review, but automatic promotion into the firm's searchable knowledge base (`_promote_staged_draft_to_pinecone` is simply never called below threshold; the draft stays in `staging_memory` marked approved-but-not-indexed). Case Genome's `_verifikacija.odluka == "require_review"` is the third instance — an advisory status stored on the Genome itself, but confirmed (per this session's own prior context, not re-verified in depth here) to be non-blocking: the Genome still saves and displays regardless of this status. No confirmed instance where low confidence blocks an ACTION outright (only Drafting's Pinecone-promotion gate) — everything else is either per-field review flagging (Smart Intake) or purely advisory/informational (Genome verification).

---

## Summary tables

### Part A — uniform gaps across all 6 AI call sites
| Field | Verdict |
|---|---|
| `model` | Never stored anywhere — always hardcoded in Python source |
| `prompt version` | No versioning concept exists in this repository at all |
| `output hash` | Never computed anywhere |
| `input reference` | Strong in Smart Intake (extraction, classification) and Evidence Vault (real FK); absent in Genome, Briefing, Drafting |
| `confidence` | Strong in Smart Intake (per-entity/per-doc) and Drafting (gates an action); structurally absent in Genome (categorical only) and Evidence Vault (hardcoded placeholder) |
| `user` | Explicit in Briefing/Drafting/Evidence Vault; only traceable-not-redundant in Genome/Smart Intake |
| `timestamp` | Everywhere relies on implicit DB-default columns, never explicit in application code |

### Part B — failure-mode verdicts
| # | Scenario | Verdict |
|---|---|---|
| 1 | OCR fails | Handled well |
| 2 | LLM timeout | Retry handled well; **post-exhaustion frontend UX confirmed broken for Genome refresh** (false success toast) |
| 3 | Pinecone unavailable | Handled well, consistent fail-soft pattern |
| 4 | Event lost (in-process bus) | **Confirmed real gap** — zero durability for the one true in-process emit site |
| 5 | DB transaction fails mid-write | No rollback exists anywhere (deliberate fail-soft tradeoff); partial failure is truthfully reported in the response but nothing retries or alerts |
| 6 | Bad/corrupted PDF | Handled well, clear end-to-end errors |
| 7 | Conflicting document info | Designed, working capability (Genome's `kontradikcije` + rule-based location verification) |
| 8 | AI hallucination | Two real guardrails exist (citation-existence check, SOURCE-n/FACT-n constraint) but neither covers Genome or Briefing |
| 9 | Confidence drops | Real per-entity/per-draft handling exists; only Drafting's Pinecone-promotion gate blocks an action outright |
