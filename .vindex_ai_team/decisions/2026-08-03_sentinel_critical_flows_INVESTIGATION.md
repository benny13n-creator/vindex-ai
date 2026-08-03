# Project Sentinel — Phase 1: Forenzički Audit Kritičnih Tokova

**Status**: READ-ONLY investigation. No code changed. Every claim below is backed by a
file:line citation or a live, executed verification command (shown inline) — nothing here
is inferred from function/file names, docstrings, or comments alone.

---

## 0. Most severe finding (headline)

**Two FastAPI routes are registered for the exact same path+method: `GET /api/search`** —
`routers/search.py:232` (`global_search`) and `api.py:3080` (`global_search`, a second,
independently-written implementation). Verified by loading the real `app` object and
enumerating `app.routes`:

```
duplicate (path, method) pairs: 1
('/api/search', 'GET') -> ['routers.search.global_search', 'api.global_search']
```

Starlette matches routes in registration order and stops at the first match.
`app.include_router(search_router)` executes at `api.py:701`; the inline `@app.get("/api/search")`
at `api.py:3080` executes later in the same module load. **`routers.search.global_search` always
wins; `api.py`'s own ~130-line `global_search` (predmet_komentari full-text search, etc.) is
dead code — unreachable by any real HTTP request, silently, with no error, no warning, no test
failure.** This is the same anti-pattern already recorded once this engagement
(`docs/security/` SEC-002, the `/api/cron/daily` dispatcher collision) — this is now a
**second confirmed instance**, meaning it is a recurring class of bug, not a one-off. Confirmed
this is the *only* duplicate (path, method) pair anywhere in the live route table (full scan run,
1 result).

**Recommendation**: not fixed here (read-only phase) — flag as a Critical Flow Integrity item for
Phase implementation, and consider a permanent CI check that fails the build on duplicate
(path, method) route registration, since this has now recurred once already.

---

## 1. Event Bus — real producer/consumer wiring for all 12 `EventType` values

This cuts across nearly every flow below, so it is established once here (`services/event_bus.py`
defines 12 `EventType`s; `_register_defaults()` at `event_bus.py:196-201` subscribes only 5 of
them to any handler):

| EventType | Real producer? | Real consumer? | Verified state |
|---|---|---|---|
| `PREDMET_KREIRAN` | ✅ `api.py:3263-3265` (in-memory `emit()`, fire-and-forget) | ✅ `on_predmet_kreiran` → `run_case_pipeline` | Wired, but **no durable outbox** — pure in-process `asyncio.create_task`; a crash/restart between `emit()` and task completion silently drops the entire Case Pipeline trigger with zero record it was ever supposed to run (known from Project Nexus, re-confirmed here) |
| `DOKUMENT_UPLOADOVAN` | ❌ zero producers found anywhere in the repo (`grep -rn EventType.DOKUMENT_UPLOADOVAN`) | ✅ `on_dokument_uploadovan` registered | Dead consumer — wired to nothing that ever fires it |
| `ROK_DODAN` | ❌ none | ❌ none | Fully dead enum value — no producer, no consumer, exists only as a name |
| `ROK_KRITICAN` | ✅ `routers/matter_intel.py:166` | ✅ `on_rok_kritican` (Project Synapse wiring) | Wired (in-memory only, same restart-loss caveat as above) |
| `ROCISTE_ZAKAZANO` | ❌ none (only appears as a `DecisionType` string constant in `services/decision_log.py:29`, unrelated enum) | ❌ none | Fully dead |
| `STRATEGIJA_GENERISANA` | ❌ none | ❌ none | Fully dead — Strategy Engine (§5 below) never emits this despite the name implying it should |
| `ANALIZA_ZAHTEVANA` | ❌ none | ❌ none | Fully dead |
| `HEALTH_SCORE_PROMENJEN` | ✅ `routers/matter_intel.py:153` | ✅ `on_health_score_promenjen` | Wired (Project Synapse) |
| `GENOME_UPDATED` | ✅ `routers/case_dna.py:529-530` — **durable outbox**, direct INSERT into `events` table | ✅ `on_genome_updated` via `dispatch_pending_events()` poll loop | The only event type that is genuinely durable end-to-end |
| `DOCUMENT_JOB_ENQUEUED` | ✅ `migrations/073_intake_foundations.sql:173-174`, RPC-level durable INSERT | ❌ **zero subscribers** (`_handlers[DOCUMENT_JOB_ENQUEUED] == []`) | Real event, dispatched (marked `dispatched_at`), does **nothing** |
| `DOCUMENT_JOB_COMPLETED` | ✅ `migrations/073_intake_foundations.sql:244-245` | ❌ zero subscribers | Same — dispatched, no-op |
| `DOCUMENT_JOB_FAILED` | ✅ `migrations/073_intake_foundations.sql:279-280` (fires when an intake job exhausts all retry attempts) | ❌ **zero subscribers** | **Most severe of this group**: a document that permanently fails OCR/classification/extraction after all retries produces a real, durable event — and it is dispatched by the poll loop and marked handled with literally zero effect. No alert, no notification, no `proactive_alerts` row. The lawyer has no way to learn a specific upload silently died forever, other than manually reopening that document's status. |

**Net**: of 12 declared event types, only 4 (`PREDMET_KREIRAN`, `ROK_KRITICAN`,
`HEALTH_SCORE_PROMENJEN`, `GENOME_UPDATED`) have both a real producer and a real consumer. 3 are
fully dead (never produced or consumed). 1 has a consumer but no producer. **3 have real
producers whose events are dispatched and silently discarded** — `DOCUMENT_JOB_FAILED` being a
genuine, live, currently-occurring silent-failure path for the OCR/Upload flow (§3below).

---

## 2. Flow: Novi predmet (New Case)

- **Entry**: `POST /api/predmeti` → `kreiraj_predmet()`, `api.py:3241-3256`
- **Terminal write**: `predmeti` row insert (`api.py:3249-3255`)
- **Event**: `EventType.PREDMET_KREIRAN` emitted `api.py:3264-3265`, wrapped in its own
  try/except (`api.py:3266-3267`) that only logs a warning on failure — **the HTTP response to
  the lawyer already returned 200 with the new case before this runs**, so if `emit()` itself
  throws, the case exists in the DB but the Case Pipeline (§below) silently never fires, and
  the lawyer sees a normal success response with no indication anything is missing.
- **Service**: `services/case_pipeline.py::run_case_pipeline` (via `on_predmet_kreiran`)
- **Downstream**: 9 pipeline steps write independently to `predmet_istorija`, `predmet_hronologija`,
  `rocista`-derived risk snapshot, etc. (see `case_pipeline.py:159-670`); `PipelineResult` return
  value is **discarded** by the event handler (`event_bus.py:104`, return value of
  `run_case_pipeline` never captured) — this is fine because every step persists its own result
  directly to DB, but it means there is no single row anywhere recording "pipeline ran for this
  predmet_id, here's the aggregate result" for the auto-triggered path (only the manual
  `routers/case_pipeline.py:53-54` endpoint captures and returns it).
- **Audit**: `predmet_create` written via `shared/audit_immutable.py::log_action`
  (`api.py:3273-3279`, fire-and-forget `asyncio.create_task`) — `predmet_create` **is** in
  `AUDITABLE_ACTIONS` (§7below), so this one is genuinely captured.
- **Failure mode if `run_case_pipeline` itself raises before entering its internal per-step
  try/excepts** (e.g. the `predmeti` lookup at `case_pipeline.py:682-691` raises because of a
  transient DB error): caught by `EventBus.publish`'s wrapper (`event_bus.py:219-223`), logged as
  `logger.error`, **no retry, no alert, no record that the pipeline never ran at all** — the case
  simply has no pipeline output and nothing tells anyone why.

---

## 3. Flow: Upload dokumenta + OCR

Two structurally different upload paths exist in this codebase — this matters, they have
different reliability properties:

### 3a. Ad-hoc / temporary session upload (`/api/dokument/upload`)
- **Entry**: `routers/dokument.py:159-303`
- **OCR**: `uploaded_doc/extractor.py::extract()` (`dokument.py:199`) — on `is_scanned=True` with
  no usable text, raises `HTTPException 422` **synchronously to the caller** (`dokument.py:206-216`)
  with a specific, actionable Serbian-language message. This path has no retry and needs none —
  it's a real-time request, the lawyer sees the failure immediately and can act (rescan, paste
  text manually).
- **Terminal state**: Pinecone `tmp_<session_id>` namespace (24h TTL), **not** linked to any
  `predmet_id` yet — this is the "analyze before you commit to a case" flow.
- **Classification**: fire-and-forget background task (`dokument.py:273-280`) — if it fails, only
  a warning is logged (`dokument.py:278`); the manual re-trigger endpoint
  `POST /api/dokument/klasifikuj-sesija` (`dokument.py:435-455`) exists as the recovery path, but
  nothing tells the lawyer the background classification failed in the first place — they'd only
  notice by checking and finding it missing.
- **Ingest failure**: Pinecone `429`/storage-full errors are explicitly caught and downgraded to
  "continue without indexing" (`dokument.py:244-249`) — correctly fail-soft, text is still
  extracted and usable for direct Q&A even if RAG indexing failed.

### 3b. Durable Smart Intake pipeline (`shared/intake_worker.py`, `shared/intake_queue.py`, `routers/smart_intake.py`)
- **Entry**: intake job created via `enqueue_intake_job` RPC (durable outbox row + `intake_jobs`
  row, `migrations/073_intake_foundations.sql:170-174`)
- **Processing**: `IntakeWorker._process()` (`intake_worker.py:128-204`) — decrypt (AESGCM,
  Trezor pattern) → OCR/extract → classify → extract entities → review-queue routing
- **OCR failure handling — explicitly fail-soft by design** (`intake_worker.py:156-171`): a
  scanned/unreadable document does **not** raise — it's saved with
  `document_type="other", confidence=0.0`, gets a `review_queue` entry tagged `"ocr_failed"`, and
  `write_processing_outcome` records it — the job still completes successfully rather than
  retrying (correct: retrying the identical image produces the identical failure). This is a
  genuinely well-designed recovery path — detection, user-visibility-via-review-queue, and audit
  (`processing_outcomes`) are all present.
- **True failure path** (`intake_worker.py:113-123`): any other exception → `mark_job_failed`
  (increments `attempts`, retries up to `max_attempts=5`) → on final exhaustion, the RPC behind
  `mark_job_failed` inserts a durable `DocumentJobFailed` event
  (`migrations/073_intake_foundations.sql:279-280`). **This event has zero subscribers (§1
  above)** — so the one genuinely "give up, this document failed permanently" signal in the whole
  intake system is produced correctly, marked dispatched correctly, and then does nothing. No
  `proactive_alerts` row, no notification. Confirmed by code path, not assumption: `EventBus`
  only registers handlers for `ROK_KRITICAN/PREDMET_KREIRAN/DOKUMENT_UPLOADOVAN/
  HEALTH_SCORE_PROMENJEN/GENOME_UPDATED` (`event_bus.py:196-201`); `DocumentJobFailed` is not
  among them.
- **Finalize into a real case**: `routers/smart_intake.py:373` `finalize_intake_job` — writes
  `predmet_dokumenti` (`smart_intake.py:654-687`, with a documented multi-variant insert fallback
  for schema drift) and triggers `_run_genome_background` (`smart_intake.py:698`) — this is a
  genuinely idempotent finalize (`smart_intake.py:338-344` comment describes the earlier bug where
  a second finalize call for the same job would silently create a duplicate case; fixed).

---

## 4. Flow: Genome analiza (Case Genome)

- **Entry points (all converge on the same function)**: `routers/case_dna.py:786`
  (`POST /{predmet_id}/case-dna/refresh`, manual), `routers/rocista.py:171-176` (auto after a
  hearing is added), `routers/smart_intake.py:698` (auto after finalize), plus the upload flow.
  All funnel through `_run_genome_background` → `_do_genome_refresh` (`case_dna.py:603-754`).
- **Concurrency control**: an in-process `_genome_refresh_inflight`/`_genome_refresh_rerun` set
  coalesces overlapping triggers for the same `predmet_id` (`case_dna.py:607-632`, documented
  2026-08-03 Zero-Touch Case fix) — **explicitly documented as NOT covering multiple worker
  processes**, only a single process. Confirmed limitation, not a hidden one.
- **Terminal write**: `predmeti.case_dna` JSON column (`case_dna.py:708-714`)
- **Event**: durable-outbox `GENOME_UPDATED` insert (`case_dna.py:529-530`, via `_emit_genome_event`)
  → `on_genome_updated` writes an `audit_immutable` row (`event_bus.py:149-178`) — this is the one
  fully-wired, fully-durable, fully-audited path in the whole event system.
- **Consumers of `case_dna`**: `routers/copilot.py` (Project Synapse wiring, confirmed this
  engagement), `routers/precedenti.py` (same), `routers/intelligence_timeline.py:62,158` (confirmed
  by direct read this session). **NOT read by**: `routers/morning_briefing.py` (§6below),
  `routers/strategija.py` (§5below) — confirmed by grep, zero matches for `case_dna` in either file.
- **Failure mode — the significant one**: `_do_genome_refresh`'s outermost try/except
  (`case_dna.py:753-754`) swallows **any** exception with only a `logger.warning`. Because every
  trigger of this function is itself a fire-and-forget background task (`asyncio.create_task`,
  never awaited by the HTTP response), **if the process restarts or crashes mid-refresh** (e.g. a
  deploy lands seconds after a lawyer uploads a document), the document is safely in
  `predmet_dokumenti`, but the Genome update that was supposed to follow it silently never
  happens and — critically — **nothing retries it, and nothing tells the lawyer**. The upload
  endpoint itself already returned success before this background task even started. This is a
  real, currently-live "silent state divergence after a crash" gap, matching the mission's Phase
  3 "Event Bus prekid" / "Transakcija prekinuta" scenario class exactly.
- **User-facing honesty of failure**: `genome.get("greska")` (LLM-call failure, e.g. malformed
  JSON or provider error) is correctly distinguished from success by `_extract_genome`
  (`case_dna.py:274`, `:312`) and was, until this same engagement's Project Nexus mission, **not**
  checked by the frontend before showing a success toast — now fixed (`static/vindex.js`,
  committed `847a6da`). Server-side handling of this particular failure class was already correct;
  only the frontend toast was wrong, and that is now closed.

---

## 5. Flow: Risk analiza

- **Canonical implementation**: `services/risk_engine.py::calculate_procesni_rizik` — pure
  function, no I/O, no LLM call (`risk_engine.py:21-140`). Confirmed single source of truth,
  actively enforced this engagement (Project Nexus closed 2 of its own violations this same
  night in `routers/ccc.py` and `routers/zadaci.py`).
- **Real callers, confirmed by grep**: `routers/matter_intel.py`, `routers/ccc.py`,
  `routers/zadaci.py`, `services/case_pipeline.py:526,585` (risk snapshot + copilot_preporuka
  steps). All pass `dokazi`/`dokumenti`/`rocista` freshly queried from DB — no caching, so no
  staleness risk, at the cost of re-querying the same 3 tables from multiple call sites per
  request (a performance, not correctness, concern).
- **`identify_case_problems`** (`risk_engine.py:157-211`): the single next-action algorithm,
  confirmed used by `case_pipeline.py:611`, `routers/zadaci.py` (Project Nexus fix). **Not** used
  by `routers/morning_briefing.py` (§6) or `routers/strategija.py` (§7) — both independently
  derive their own "what matters today" judgment without reference to this function.
- **Failure mode**: `calculate_procesni_rizik` has no I/O, so it cannot itself fail at runtime
  except on malformed input (e.g., `r.get("datum")` shapes) — and that per-row failure is already
  caught with a bare `except: pass` at `risk_engine.py:93-94` (silently skips a malformed
  ročište's date rather than crashing the whole calculation — reasonable degrade, but a
  ročište with a bad date is silently excluded from `predstojeći`/`kriticni_rokovi` counts with
  no log line to reveal it happened).

---

## 6. Flow: Strategy Engine

- **Entry points**: `routers/strategija.py` — 8 separate endpoints (`/red-team`, `/litigation`,
  `/sudija`, `/due-diligence`, `/revizor`, `/witness`, `/sudija-v2`, `/kompletna-analiza`,
  `/v2/analiza`), each a stateless GPT call.
- **Critical finding — Strategy Engine is a dead-end island, confirmed by code**: none of these
  endpoints accept or persist a `predmet_id`. `StrategijaRequest`/`StrategijaV2Request`
  (`strategija.py:51-53`, `:~300s`) take only free-text `tekst`/`opis_predmeta`. The GPT result is
  returned directly in the HTTP response and **never written to any table** — not
  `predmet_istorija`, not `case_dna`, not `predmet_hronologija`. Confirmed: no `.insert(` call
  exists anywhere in `strategija.py` tied to a case.
  - This directly violates this mission's own Phase 4 ownership rule ("Strategy Engine = pravni
    zaključci") in the strict sense that a "zaključak" (conclusion) that cannot be retrieved
    again, is not linked to a case, and cannot be reconstructed later is not really owned by
    anything — it is produced and discarded.
  - Consequence for Phase 5/7 (Source of Truth / E2E): a lawyer who runs Red Team or Litigation
    Simulator on a case gets zero record in that case's Timeline, Genome, or Briefing. Firm Brain
    never learns from it. Downstream AI calls (Copilot, Briefing) cannot reference "what strategy
    was already proposed for this case" because there is no such record to read.
  - Contrast: `case_pipeline.py::_step_strategija` (`case_pipeline.py:351-415`) **does** persist
    its own (lighter, GPT-4o-mini) strategy generation into `predmet_istorija` — meaning there are
    now genuinely two different "AI strategy" code paths in the product: one persisted and
    idempotent (pipeline's lite version), one fully ephemeral and unlimited-use (the dedicated
    Strategy Engine module) — with no cross-reference between them.
- **Provenance**: only `asyncio.create_task(_audit(user["user_id"], "red_team", ""))`
  (`strategija.py:77`, and equivalent per-endpoint) — a lightweight, non-hash-chained log call
  (`shared/deps.py::_audit`, not `shared/audit_immutable.py::log_action`). None of these action
  names (`red_team`, `strategija_v2`, etc.) appear in `AUDITABLE_ACTIONS` (§8below), so even if
  someone swapped `_audit` for `log_action` expecting durability, it would silently no-op.

---

## 7. Flow: Briefing (Morning Briefing)

- **Entry**: `GET /api/briefing/daily` → `_generiši_briefing` (`routers/morning_briefing.py:79-`)
- **Data sourced directly from raw tables**: `predmeti`, `rokovi`, `rocista`, `klijenti`
  (`morning_briefing.py:87-121`) — confirmed by direct read, **zero references to `case_dna`,
  `risk_engine`, or `identify_case_problems` anywhere in this 1131-line file** (grep for all three
  terms: 0 matches).
- **AI judgment is fully free-form**: the GPT prompt (`morning_briefing.py:178-197`) asks the
  model to independently decide "kakav dan predstoji — mirno/zauzeto/kritično" and which 2-4
  actions matter most, from a plain data dump — with no grounding in the deterministic
  `calculate_procesni_rizik`/`identify_case_problems` output used everywhere else in the product.
  This is a genuine Phase 6 (Hallucination Hardening) gap: **the AI call most directly framed as
  "tell the lawyer what matters today" is the one call in the audited set with the least
  deterministic grounding**, and it can structurally disagree with what Matter Intel/CCC/Cockpit
  say about the same case on the same day, since they all read `calculate_procesni_rizik` and
  this does not.
- **Failure mode**: not traced in depth this pass — flagged as a follow-up item, not a confirmed
  gap, given time budget for this investigation.

---

## 8. Flow: Timeline

- **Entry**: `GET /{predmet_id}/intelligence-timeline` (`routers/intelligence_timeline.py:56`)
- Confirmed to **read `case_dna` directly** (`intelligence_timeline.py:62,158`) — this flow is
  correctly wired to the canonical Genome, unlike Briefing/Strategy Engine above. Aggregates
  `predmet_istorija`/`predmet_hronologija`/`case_dna` into one unified view — a genuine example of
  "connect, don't build," already done.

---

## 9. Flow: Deadline Engine (`rokovi_lanac`) vs. hearing dates (`rocista`)

- **Entry**: `POST /api/rokovi/lanac` (`routers/rokovi_lanac.py:389`) — a deterministic,
  rule-based (ZPP statute) legal deadline-chain calculator, no LLM involved.
- **Terminal write**: `predmet_hronologija` (if `predmet_id` given, `rokovi_lanac.py:421-437`) —
  confirmed persisted, not ephemeral, unlike Strategy Engine.
- **Important distinction confirmed by reading both call sites**: `predmet_hronologija` (written
  here) and `rocista` (read by `calculate_procesni_rizik` as its "hearing dates" input,
  `risk_engine.py:24,70-94`) are **different tables representing different concepts** — a
  deadline chain entry does not feed the Risk Engine's `kriticni_rokovi`/`health_score`
  computation at all. This appears to be by design (deadline-chain events are procedural
  calendar items, not hearing dates), not a bug — flagged here for completeness, not as a defect.
- **No event emitted after insert** — `ROK_DODAN` (the seemingly-designed-for-this event type)
  is never fired here (confirmed, §1) — but since `ROK_DODAN` has zero consumers anyway, this
  costs nothing today; it would matter only if a consumer were later added and this producer
  were forgotten.
- **`routers/rocista.py:171-176`**, by contrast, **does** trigger `_run_genome_background` after
  adding a hearing — confirmed connected.

---

## 10. Flow: Task Engine (`zadaci.py`)

Already deeply audited and fixed this same engagement (Project Nexus, commit `847a6da`):
`ai_analiziraj_predmet` now grounds both its GPT prompt and its GPT-failure fallback in
`calculate_procesni_rizik`/`identify_case_problems` rather than an independent 5th
missing-document heuristic. Not re-traced in this pass — see `docs/architecture/
NEXUS_ORCHESTRATION_REPORT.md` Change 2 for the full record. No new findings surfaced here this
pass.

---

## 11. Flow: Alerts (`proactive_alerts`)

- **Producers, all confirmed**: `on_rok_kritican` (`event_bus.py:66-95`),
  `on_health_score_promenjen` (`event_bus.py:126-146`), Genome Intelligence Delta
  (`case_dna.py:734-744`), `_maybe_alert_require_review` (`case_dna.py:417-`, referenced at
  `:749`).
- **Consumer/read side**: `routers/notifications.py` (`GET /notifications`, `:256`) and
  `routers/morning_briefing.py` (`get_proactive_alerts`, `:774-803`) both read this table —
  confirmed two independent read paths for the same alert data, which is fine (different
  surfaces), not a duplication of logic.
- **Gap, restated from §1/§3**: `DOCUMENT_JOB_FAILED` should be a producer into this same table
  (a permanently-failed document upload is exactly the kind of thing `proactive_alerts` exists
  for) and currently is not — the event fires, dispatches, and does nothing.

---

## 12. Flow: Firm Brain (`firm_memory.py`)

- **Entry points**: exclusively manual save endpoints — `/dodaj`, `/sudija/sacuvaj`,
  `/klijent/sacuvaj` (`routers/firm_memory.py:150,429,528`). **No automatic producer found**:
  grepped the whole repo for calls into `firm_memory` write paths from Case Pipeline, Genome,
  Case Close, or Outcome Intelligence — none found in this pass. This is reported at **medium
  confidence** (a targeted, not exhaustive, search) rather than a confirmed defect — it may be
  intentional (organizational knowledge is meant to be lawyer-curated, not auto-mined) but is
  worth the founder explicitly confirming, since a permanently-empty-unless-manually-fed Firm
  Brain would materially undercut the "organizational knowledge" ownership claim in Phase 4.
- **Read side**: `GET /kontekst-za-ai` (`firm_memory.py:250`) — confirmed referenced from
  `api.py` and `routers/proof.py` per repo-wide grep; not traced further this pass.

---

## 13. Flow: Memory Graph (`memory_graph.py`)

- **Entry points**: `POST /dodaj-vezu`, `GET /entitet/{type}/{id}`, `GET /upit`,
  `GET /preporuka/{predmet_id}` (`routers/memory_graph.py:97,141,210,296`).
- Not traced to depth this pass beyond confirming these 4 endpoints exist and are the only
  entry surface — flagged as a follow-up item for a deeper pass given time budget.

---

## 14. Flow: Semantic Search (`search.py` / duplicate `api.py` route)

Covered in full at §0 above — the headline finding for this entire investigation.

---

## 15. Flow: Copilot

- Already partially audited this engagement (Project Synapse) — `_handle_analiza_predmeta`
  (`routers/copilot.py`) confirmed reading `case_dna` (Genome) for its context. Not re-traced in
  depth this pass; no new findings surfaced.

---

## 16. Flow: Audit

- **Canonical sink**: `shared/audit_immutable.py` — cryptographic hash-chain, INSERT-only,
  `verify_chain_integrity()` available (`audit_immutable.py:130-146`).
- **Critical finding**: `log_action`/`log_action_sync` (`audit_immutable.py:86-127`) **silently
  no-op** — `return None`, debug-level log only, no exception, no signal to the caller — for any
  `action` string not in the fixed `AUDITABLE_ACTIONS` allowlist (`audit_immutable.py:56-81`).
  Confirmed the allowlist contains: predmet CRUD, dokument CRUD, klijent create/delete, auth
  events, export/deletion, admin actions, exactly 4 AI-related actions
  (`ai_analiza_complete`, `ai_kompletna_analiza_complete`, `genome_refresh`,
  `reasoning_graph_generated`), security events, and one autonomous-agent action.
  **Not present**: any Strategy Engine action name, Copilot interactions, Morning Briefing
  generation, Case Pipeline step execution, Task Engine's `ai_analiziraj_predmet`. A developer
  who calls `log_action("strategija_v2", ...)` believing it will be durably hash-chained gets
  silent, undetectable non-persistence — the function signature gives no indication this call
  can be a no-op.
- This is the single clearest, most concrete Phase 9 (AI Provenance) finding: the *mechanism*
  for durable AI-decision audit already exists and works correctly for the 4 actions it covers —
  the gap is that most of the platform's actual AI call sites were never added to its allowlist,
  not that the audit system itself is broken.

---

## 17. Flow: Dashboard

- Not traced to depth this pass (`routers/dashboard.py`, 451 lines) — flagged as a follow-up
  item given time budget; no findings claimed here.

---

## 18. Flow: Notification (push / email / whatsapp / sms)

- `routers/push.py` confirmed to handle a `410 Gone` subscription-expiry case explicitly
  (`push.py:102`) — a real, specific failure mode correctly handled, not a generic catch-all.
  Email/WhatsApp/SMS channels not traced to depth this pass — flagged as a follow-up item.
- Cross-reference: memory already records a prior confirmed gap in this area
  (`korisnik_viber_profil` table missing user_id linking, per project memory) — not re-verified
  in this pass, still presumed open unless contradicted by a future check.

---

## Summary of confirmed, code-verified findings (this document only)

| # | Finding | Severity | Confidence |
|---|---|---|---|
| 1 | `GET /api/search` registered twice (`routers/search.py` + `api.py`); `api.py`'s own implementation is 100% dead code | High | Confirmed (live route-table dump) |
| 2 | `DOCUMENT_JOB_FAILED` — real, durable, dispatched event with zero subscribers; a permanently-failed document upload produces no user-facing signal at all | High | Confirmed (code + migration) |
| 3 | 3 of 12 `EventType` values (`ROK_DODAN`, `ROCISTE_ZAKAZANO`, `ANALIZA_ZAHTEVANA`) are fully dead — no producer, no consumer, anywhere | Low | Confirmed |
| 4 | `DOKUMENT_UPLOADOVAN` has a registered consumer but zero producers | Low | Confirmed |
| 5 | Strategy Engine (`strategija.py`, 8 endpoints) persists nothing — every "legal conclusion" it produces is discarded the moment the HTTP response is sent; not linked to any `predmet_id`; not fed to Genome/Firm Brain/Timeline | High | Confirmed |
| 6 | Morning Briefing computes case urgency/priority independently of `calculate_procesni_rizik`/`identify_case_problems` — can structurally disagree with every other surface in the product about the same case | Medium-High | Confirmed |
| 7 | `audit_immutable.log_action` silently no-ops for any action not in a small, stale `AUDITABLE_ACTIONS` allowlist — Strategy Engine, Copilot, Briefing, Case Pipeline, Task Engine AI calls are all structurally excluded from durable audit | High | Confirmed |
| 8 | Genome background refresh (`_do_genome_refresh`) has no durable retry — a process crash/restart between document upload and refresh completion silently drops the Genome update with no record and no user notification | Medium | Confirmed |
| 9 | Firm Brain appears to have no automatic producer (manual-only population) | Medium | Medium confidence — targeted search only, not exhaustive |
| 10 | `risk_engine.py`'s per-ročište date parsing swallows malformed dates with a bare `except: pass`, no log line | Low | Confirmed |

Not yet traced to comparable depth (explicitly flagged, not claimed clean): Firm Brain producer
side (deeper pass needed), Memory Graph, Dashboard, Notification channels beyond push's 410
handling, Briefing's own failure-mode handling.
