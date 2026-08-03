# Mission Keystone — Phase 1: Architecture Freeze Review (Investigation)

**Method note**: every claim below was independently re-verified by direct Glob/Grep/Read against the
current repo state (2026-08-04), not copied from `docs/architecture/*.md` or `.vindex_ai_team/
MISSION_BOARD.md`. Where a prior claim is confirmed, that's stated explicitly with file:line. Where a
prior claim is wrong, stale, or was never quite true, that's stated plainly under "Corrections to prior
mission claims" — per Keystone's own mandate ("ne pretpostavljati da prethodne misije nisu pogrešile").

---

## 1. Modules inventory (real counts, not estimates)

| Category | Count | Path |
|---|---|---|
| Routers | 109 files in `routers/` (+ 2 legacy business-logic modules living in repo root, see §3) | `routers/*.py` |
| Services | 14 | `services/*.py` |
| Shared | 29 | `shared/*.py` |
| Security | 11 | `security/*.py` |
| Core entry points | 2 | `api.py` (5,576 lines — the actual FastAPI app, `app = FastAPI(...)`) and `main.py` (4,124 lines — houses `ask_agent`/`ask_nacrt`/`ask_analiza`/`ask_analiza_v2`, imported by `api.py`) |
| Registered HTTP routers (confirmed) | **108** (verified via `scripts/audit_routers.py`, fresh run this mission) — `app.include_router(...)` called **111 times** in `api.py` for **111 distinct router variable names**, no duplicate registrations found |
| Root-level clutter (NOT part of the running app) | ~60 files: `diag_*.py`, `ingest_*.py`, `smoke_*.py`, `run_*q*.py`, `verify_*.py`, `test_*.py` (root-level, distinct from `tests/`), one-off `build_*.py`/`fetch_articles*.py`/`chunker_case_law.py` scripts. None imported by `api.py`. Not a reliability risk (dead weight, not live code), but genuine repo hygiene debt — flagged, not fixed (out of Keystone's "don't build/clean" scope unless it poses a risk, and it doesn't). |

**108 routers checked, 92 confirmed live (found ≥1 caller), 13 flagged `MRTVI` (zero found caller) + 1
flagged `MOZDA SPOLJNI` (webhook, expected to have no internal caller) by a fresh run of
`scripts/audit_routers.py`** (a real, pre-existing, static-analysis tool in this repo — heuristic, string-
match based, has false negatives for dynamically-constructed paths, but the best available ground truth):

- **MRTVI (13)**: `agent_notifications`, `auto_discovery`, `import_klijenti`, `knowledge_hygiene`,
  `knowledge_transfer`, `oblasti`, `onboarding`, `region`, `status_page`, `strategy_simulator`,
  `style_checker`, `ugovor_zastupanja`, `whatsapp_notif`.
- **MOZDA SPOLJNI (1)**: `routers.viber` (`/viber/webhook` — externally triggered, correctly not expected
  to have an internal caller).

## 2. Critical flows map

Traced by direct grep/read, not asserted from memory:

| Flow | Entry point(s) |
|---|---|
| Client/predmet creation | `api.py::kreiraj_predmet` |
| Document upload | `api.py::predmet_upload_auto_analyze` |
| OCR | Smart Intake pipeline (`shared/intake_worker.py`, `routers/smart_intake.py`) |
| AI classification/extraction | `routers/evidence.py::klasifikuj_i_sacuvaj`, Smart Intake extraction |
| Case Genome | `routers/case_dna.py::_extract_genome` / `_emit_genome_event` |
| Risk Analysis | `services/risk_engine.py::calculate_procesni_rizik` (single definition, confirmed §3) |
| Strategy Engine | `routers/strategija.py` (thin HTTP layer) → root-level `strategija.py` (`_pozovi_strategija_api`, the actual GPT-calling business logic — see §3, this is NOT a duplicate) |
| Timeline | `predmet_hronologija` table, written from multiple flows |
| Deadlines | `ROK_KRITICAN`/`ROK_DODAN` events, `predmet_hronologija` |
| Task generation | `routers/zadaci.py::ai_analiziraj_predmet` |
| Evidence | `routers/evidence.py` |
| Briefing | `routers/morning_briefing.py` (`briefing_cron` — on-demand — and `nightly_intelligence_run` — scheduled, these are two distinct endpoints, confirmed still true post-Phoenix) |
| Copilot | `routers/copilot.py` (multiple `_handle_*` handlers) |
| Firm Brain | Not independently traced this pass (out of time budget — flag for a future pass, don't assert) |
| Memory Graph | `shared/`-level graph edge writes, out of this pass's depth budget |
| Search | `routers/search.py::global_search` |
| Alerts | `proactive_alerts` table, written from `routers/morning_briefing.py` and `services/event_bus.py::on_document_job_failed` |
| Dashboard | `routers/dashboard.py::matter_health_score` (delegates to `calculate_procesni_rizik`, confirmed by Project Sentinel, not re-traced line-by-line this pass) |

## 3. Sources of truth

| Concept | Owner location | Duplicate risk found? |
|---|---|---|
| Case risk/health score | `services/risk_engine.py:21::calculate_procesni_rizik` — **exactly one definition in the entire repo**, confirmed by grep | **No.** (Two unrelated files matched a broad `risk.*score` grep — `security/prompt_guard.py`'s `risk_score` is prompt-injection-detection scoring, a completely different concept; not a duplicate.) |
| AI audit log | `shared/audit_immutable.py` — **exactly one** `log_action`/`log_action_sync` implementation in the repo | **No.** |
| AI provenance/forensics sink | `security/ai_forensics.py::log_provenance_from_wrapper` — **exactly one** sink writing to `ai_forensics` | **No.** |
| correlation_id | `shared/ai_provenance.py::new_correlation_id()` is the canonical generator. `routers/case_dna.py:536` also calls `str(uuid.uuid4())` directly — **verified this is NOT a competing generator**: it's an explicitly-documented, narrow fallback (`current_correlation_id() or str(uuid.uuid4())`) used only when `_emit_genome_event` runs outside any request/case context (e.g. a background job), with its own in-code comment citing the prior duplicate this exact pattern replaced (`ATLAS-004`, already closed). | **No** (confirmed correctly implemented, not a regression). |
| Strategy Engine business logic | Root-level `strategija.py` (`_pozovi_strategija_api` + 8 `_sync` functions) is the ONLY implementation; `routers/strategija.py` is a thin HTTP wrapper that imports and calls into it (`from strategija import (...)` at `routers/strategija.py:28`) | **No** — verified this is a legitimate two-layer design (HTTP layer + business logic layer), not a duplicate, despite the confusing near-identical naming and the business-logic half living in repo root instead of a `services/`-style directory. Same pattern confirmed for `web3_compliance.py` (root) / `routers/web3.py`. |
| Event durable-outbox dispatch | **Single `DispatchLoop` class** (`services/event_bus.py:487`) — but see §7, a serious open question about how many *instances* of it run concurrently in production. |

## 4. AI entry points (fresh verification, not cited from Atlas/Migration)

**Confirmed via fresh grep**: `shared/ai_client.py::_patch_prompt_guard()` patches
`Completions.create`/`AsyncCompletions.create`/`Embeddings.create`/`AsyncEmbeddings.create` **at the
class level** (`Completions.create = _guarded_create`, `shared/ai_client.py:347-348`), not on a specific
client instance — meaning ANY code that calls `some_client.chat.completions.create(...)` goes through the
wrapper regardless of which `client` object it holds. This is called unconditionally at
**module-import time**, `api.py:26` (`_patch_prompt_guard()` — bare call, not inside a function), which
runs before the app can serve any request. **Confirmed true, not just re-stated.**

Verified this holds even for the two "hidden" business-logic modules in repo root
(`strategija.py::_pozovi_strategija_api`, `web3_compliance.py::_pozovi_web3_api`) — both call
`client.chat.completions.create(**kwargs)`, which is covered by the same class-level patch.

**No Anthropic SDK usage found anywhere in the codebase** (`grep -rl anthropic` outside `tests/` and
`.vindex_ai_team/` returns nothing) — despite Project Phoenix's own Failure Inventory listing "Anthropic"
as an external dependency with a row in its table. **This is a correction**: the app does not currently
call Anthropic/Claude at all; that row in Phoenix's inventory describes a dependency that doesn't
currently exist in this codebase (possibly aspirational/future, or a holdover from the mission brief's
own generic template). Flagged for Phoenix's own report to be corrected, though re-verified from THIS
mission's evidence, not assumed.

**⚠️ MAJOR FINDING — a real AI entry point bypasses the wrapper entirely, previously unflagged by any of
the 5 prior missions:**

`services/voice_orchestrator.py` ("Vindex Live" — voice-to-action, wired and live: imported by
`routers/voice_realtime.py`, registered in `api.py` as `voice_realtime_router`, has its own test file
`tests/test_voice_realtime.py`) connects **directly via raw WebSocket** to
`wss://api.openai.com/v1/realtime` (`services/voice_orchestrator.py:46,211`) using the `websockets`
library — **not** the OpenAI Python SDK's `Completions`/`Embeddings` classes at all. This means:

1. The live audio conversation itself (every user utterance, every model response, every
   function-call decision the Realtime model makes) generates **zero `ai_forensics` rows, zero
   `log_action` audit entries, zero correlation_id** — it is completely outside every provenance/audit
   mechanism built across Atlas/Ledger/Migration/Phoenix. Every prior mission's "100% wrapper coverage,
   zero features bypass `shared/ai_client.py`" claim (repeated verbatim across Atlas's and Migration's
   reports) is **not true** for this feature. It was missed because all 4 prior missions' AI-entry-point
   sweeps grepped for `Completions.create`/`chat.completions` call patterns, and this feature uses a raw
   JSON-over-WebSocket protocol instead — a different shape their greps didn't catch.
2. `routers/voice_realtime.py` never calls `set_request_context()`/`case_context()` (confirmed: zero
   matches for either in that file) — so even the ONE tool this voice agent can invoke that DOES go
   through the SDK wrapper (`kreiraj_nacrt` → `shared/voice_tools.py::_tool_kreiraj_nacrt` →
   `drafting/router.py::generate_draft` → `_call_openai` → `Completions.create`, which the class-level
   patch DOES capture into `ai_forensics`) has **no correlation_id, no case/predmet linkage** — the
   `ai_forensics` row exists but can't be tied back to a specific case the way every HTTP-driven Drafting
   call now can (per Phoenix's own migration of `routers/drafting.py::nacrt`).
3. `shared/voice_tools.py::_tool_dodaj_belesku` (the one voice tool that mutates data — inserts a
   `predmet_beleske` row) has a correct ownership check (mirrors the documented SEC-001 pattern) but
   **no `log_action` audit call**. Verified this is NOT a voice-specific regression: the equivalent HTTP
   endpoint (`api.py:3481::dodaj_belesku`) also has no audit entry for plain case notes — so this is a
   pre-existing, consistent gap across both paths, not something voice introduced alone. Worth a shared
   fix, not a voice-specific one.
4. The voice session does have a real, working **Human-in-the-Loop confirmation gate**
   (`requires_confirmation`/`vindex.confirmation_required`/`vindex.confirm_tool_call`,
   `services/voice_orchestrator.py:146-178`) for any tool with `mutates_data=True` — this is a genuine,
   separate safety control, not a substitute for provenance/audit, but worth noting it's not an
   unguarded voice-to-database pipeline either.

**Severity**: this is a real, previously-undiscovered gap in the provenance/audit chain every mission
tonight has been building toward closing. It does not cause data loss or silent failure in the sense
Phoenix's chaos matrix tests for (tool execution still works, still fails soft, still has the HITL gate)
— but it is a genuine hole in "every AI decision can be reconstructed from system records," which is
Mission Ledger/Atlas's core promise. Recommend Keystone's Phase 8 risk register carry this as **High**,
not Critical (no data loss, no false success, but a real observability/compliance gap for a
production-facing, tool-executing AI feature).

## 5. Event flow current-state (re-verified against current code, not memory)

- `EventType` enum (`services/event_bus.py:31`): confirmed unchanged in shape from Ledger/Migration's
  description — `PREDMET_KREIRAN`, `DOKUMENT_UPLOADOVAN`, `ROK_DODAN`, `ROK_KRITICAN`,
  `ROCISTE_ZAKAZANO`, `STRATEGIJA_GENERISANA`, `ANALIZA_ZAHTEVANA`, `HEALTH_SCORE_PROMENJEN`,
  `GENOME_UPDATED`, plus Smart Intake's `DOCUMENT_JOB_*` types.
- **Project Phoenix's fix is confirmed still present and unchanged**: all 6 handlers still re-raise after
  logging; `publish_async()` (`services/event_bus.py:302`) still inspects `gather()`'s results and
  re-raises on handler failure; `MAX_DISPATCH_ATTEMPTS = 5` (`services/event_bus.py:378`) still gates the
  dead-letter path. Read directly, not assumed from the Phoenix report.
- **⚠️ NEW FINDING, not examined by any prior mission — a real multi-process concurrency gap in the
  durable outbox dispatcher:**
  - `gunicorn.conf.py:4`: `workers = int(os.getenv("WEB_CONCURRENCY", 4))` — **4 worker processes by
    default**, each a separate OS process (`UvicornWorker`).
  - `start_dispatch_loop()` is called from `api.py:832` (a FastAPI startup hook) — meaning **every one of
    the 4 worker processes independently instantiates and runs its own `DispatchLoop`**, each polling the
    `events` table every 3 seconds.
  - `dispatch_pending_events()` (`services/event_bus.py:380-435`) claims rows with a **plain**
    `SELECT * FROM events WHERE dispatched_at IS NULL ORDER BY created_at LIMIT batch_size` — **no
    `FOR UPDATE SKIP LOCKED`, no atomic claim, no advisory lock, no per-worker row reservation**. Compare
    directly to `shared/intake_worker.py`, whose own docstring (line 41) explicitly documents using
    `FOR UPDATE SKIP LOCKED` for exactly this reason ("nema potrebe za spoljnim leader-election-om").
  - **Consequence**: in a real multi-worker deployment (which `WEB_CONCURRENCY=4`'s default strongly
    suggests is the actual production topology, not a hypothetical), multiple processes can read the
    same un-dispatched row in the same ~3s window and **both run the handler and both attempt
    `_mark_dispatched`** before either commits — a genuine risk of a single business event being
    processed 2-4× (duplicate `audit_immutable` rows for one Genome refresh, duplicate
    `proactive_alerts` rows for one failed job), and the `dispatch_attempts` counter Phoenix's dead-letter
    logic depends on can be read-stale across processes (each process computes
    `attempts = row.dispatch_attempts + 1` from its own possibly-stale read, so the count doesn't
    reliably reach `MAX_DISPATCH_ATTEMPTS` in lockstep either).
  - This does **not** contradict Phoenix's fix — the fix (re-raise + dead-letter) is correct and needed
    regardless — but Phoenix's own analysis implicitly treated the dispatch loop as a single logical
    process. It is not, under the codebase's own default configuration. Recommend Keystone's risk
    register carry this as **Critical or High** (duplicate side effects across 4 processes, not just a
    single-process retry-storm risk Phoenix already closed) — the exact severity depends on whether
    production actually runs with `WEB_CONCURRENCY > 1` (not independently confirmed by this investigation
    — Render/hosting config wasn't found in the repo, only the `Procfile`/`gunicorn.conf.py` defaults
    that make it the code's own out-of-the-box behavior).

## 6. Background processes

- `services/event_bus.py::DispatchLoop` — started via `start_dispatch_loop()` at `api.py:832` (FastAPI
  startup event). See §5 for the multi-worker concern.
- `shared/intake_worker.py::IntakeWorker` — same `asyncio.create_task`-based loop pattern, but **does**
  use `FOR UPDATE SKIP LOCKED` for its job claim (confirmed by its own docstring), making it safe under
  the same multi-worker topology that the Event Bus's dispatch loop is not.
- `routers/morning_briefing.py::nightly_intelligence_run` (`/api/briefing/nightly-intelligence`) — not a
  Python-side background loop; triggered externally via `X-Cron-Secret` header, documented in its own
  docstring as intended for `cron-job.org`, no evidence of a competing internal scheduler.
- `routers/morning_briefing.py::briefing_cron` (`/api/briefing/cron`) — a second, older, simpler
  cron-triggered endpoint, confirmed distinct from `nightly_intelligence_run` (this distinction caused a
  real test bug earlier in Project Phoenix this same session — now fixed).

## 7. External dependencies

OpenAI (Chat Completions + Embeddings via SDK; Realtime API via raw WebSocket, see §4), Pinecone,
Supabase/PostgreSQL, SMTP (for nightly/on-demand email), Sentry (`shared/sentry.py`, used for exception
capture in `voice_orchestrator.py` and elsewhere). **No Anthropic dependency currently exists in the
code** (see §4 correction).

## 8. Duplicate/orphan/abandoned-implementation findings

- **`uploaded_documents`**: confirmed still dormant, exactly as Mission Migration-era comments describe.
  The only remaining reference in the live codebase (`routers/search.py:79`) is a code **comment**
  explaining the historical dead-end, not a live query — the actual search code queries
  `predmet_dokumenti`. No correction needed here; prior claim holds.
- **`routers/enterprise.py`**: ⚠️ **correction to a prior claim.** The persistent memory record
  (`project_platform_anatomy_report_2026_07_24`) states "`enterprise.py` mrtav kod" (dead code) as a key
  finding from the 2026-07-24 Platform Anatomy Report. **This is not true of the current codebase.**
  `routers/enterprise.py` is imported (`api.py:637`) and registered (`app.include_router(enterprise_router)`,
  `api.py:732`) with 4 real, fully-implemented endpoints (`/api/enterprise/statistike`, `/kapacitet`,
  `/predmet/delegiraj`, `/predmet/delegiranja`) doing genuine Supabase queries and firm-level aggregation
  — read `firma_statistike` in full, confirmed it is not a stub/placeholder. Either the July report was
  wrong, or the module was reactivated/completed since — either way, the "dead code" label in memory is
  now stale and should be corrected.
- **Orphan routes**: the memory record's "~208 orphan routes (unconfirmed)" figure (from the same July
  Platform Anatomy Report) is superseded by this repo's own existing `scripts/audit_routers.py` tool,
  freshly re-run this mission: **13 confirmed dead router modules + 1 expected-external webhook**, out of
  108 registered — a much smaller and more precise number than 208 (likely because 208 was counting
  individual endpoint paths across a cruder heuristic, not router modules). The specific *set* has also
  changed since a stale `STATE_AUDIT.md` snapshot dated 2026-07-19 (which listed 14, including
  `case_intelligence` and `gdpr` — this fresh run shows those two now have a found caller, while
  `agent_notifications` is newly flagged dead). Recommend memory be updated to point at this tool's live
  output rather than either historical number.
- **No new parallel systems found** across the 5 prior missions tonight: exactly one audit mechanism
  (`shared/audit_immutable.py`), exactly one provenance sink (`security/ai_forensics.py`), exactly one
  correlation_id generator with one documented, narrow, non-duplicating fallback, exactly one risk-score
  computation. The 5-mission engagement's own repeated "no duplicates found" self-assessment is
  **confirmed accurate** for everything it actually looked at — the gaps found this pass
  (Voice Realtime's wrapper bypass, the dispatch loop's multi-worker race) are places prior missions
  **didn't look**, not places they looked and got wrong.

## 9. Corrections to prior mission claims (summary)

1. **Atlas/Migration's "100% AI wrapper coverage, zero features bypass `shared/ai_client.py`"** — not
   true. `services/voice_orchestrator.py`'s direct WebSocket connection to OpenAI's Realtime API is a
   real, live, wired-in exception. See §4.
2. **Phoenix's Failure Inventory listing "Anthropic" as an external dependency** — no Anthropic usage
   exists anywhere in the current codebase; this row describes something that isn't actually there.
3. **Memory's "`enterprise.py` mrtav kod"** (Platform Anatomy Report, 2026-07-24) — wrong as of current
   state; the module is live, wired, and fully implemented. See §8.
4. **Memory's "~208 orphan routes (unconfirmed)"** — superseded by a fresh, tool-verified, much smaller
   and more precise figure (13 dead router modules of 108, + 1 expected webhook). See §8.
5. **Implicit assumption across all of Sentinel/Atlas/Ledger/Migration/Phoenix that the Event Bus's
   durable outbox dispatch is a single logical process** — not examined against this repo's own
   `WEB_CONCURRENCY=4` default and the dispatch loop's lack of an atomic row claim (unlike Smart Intake's
   proven `FOR UPDATE SKIP LOCKED` pattern). Not previously flagged as a risk by any prior mission. See §5.
