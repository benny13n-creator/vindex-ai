# TASK 0 — CASE EVOLUTION SPINE: CURRENT-STATE FORENSIC CONTRACT

Branch: `case-evolution-spine` @ `3cd603eb` (matches `origin/main` at start of this task; no push, no deploy performed).
Method: static code read + LIVE runtime test against a local server (port 8994, same `.env`/DB as production-shaped schema) using an isolated service-role-created test account. No founder data touched. Test artifacts (2 predmeti, 1 test user `731be489-e41b-49f3-93fd-42d547c5f982`) left in place for inspection; not cleaned up because `auth.admin.delete_user` is rate-limited on this Supabase project from earlier sessions (non-blocking, informational).

Evidence discipline: PROVEN = live runtime evidence cited below. INFERRED = code-read only, not runtime-verified in this pass. UNKNOWN = not yet investigated.

---

## A. Event contract — PROVEN (infrastructure is real, not dead code)

- `services/event_bus.py` is a durable outbox-pattern bus: `emit()` (L446), `emit_durable()` (L570), `dispatch_pending_events()` (L659), `start_dispatch_loop()` (L924).
- `api.py` `_start_smart_intake_background_loops()` (`@app.on_event("startup")`, ~L854-867) calls `start_dispatch_loop()` at boot, alongside the intake worker, on the same event loop (ADR-0002).
- **PROVEN live**: starting the app locally prints `[EVENT_BUS] dispatch loop pokrenut (poll=3.0s)` and `[INTAKE_WORKER] ... pokrenut` in the startup log; `/health` returns 200. The loop is genuinely running, not dead code.
- `event_bus.py` L364 imports and calls `services/case_evolution.py::handle_case_changed` — this is the ONLY path into the Consequence Engine; `case_evolution.py` never calls back into `event_bus`.

## B. Document upload path — PROVEN WORKING END-TO-END (corrects prior audit)

**Prior finding under review** (previous night's audit): `predmet_upload_auto_analyze` had "0 pogodaka" for event_bus/case_evolution references, i.e. document upload never triggers the Consequence Engine.

**This is WRONG.** The prior audit's grep window covered roughly the first ~250 lines of the function body and missed the tail.

- `api.py:5654` `predmet_upload_auto_analyze` (POST `/api/predmeti/{id}/upload`), at **lines 5990-6035** (well past the ~250-line window the prior audit checked), calls:
  - `emit_durable(EventType.NEW_EVIDENCE_REGISTERED, ...)` (~L6012)
  - `emit_durable(EventType.DOCUMENT_ACCEPTED, ...)` (~L6024)
  - both wrapped in non-fatal try/except that logs a warning on failure (so a bus failure never blocks the upload response to the user).

**Live proof** (test predmet `ed8b5d12-e04e-43a1-a4b3-1f39d488e4f0`, test user `731be489-...`, Professional-tier):
1. Baseline `GET /api/case-actions/predmeti/{id}` → `broj_akcija: 0`.
2. `POST /api/predmeti/{id}/upload` with a real PDF (tužba text: parties, ugovor, 15-day rok, vrednost spora) → `200`.
3. ~7-13s later, `GET /api/case-actions/predmeti/{id}` → `broj_akcija: 1`:
   ```json
   {"id":"5bf00666-79cc-4fa9-9838-4accdff7908a","tip":"PRIBAVITI_DOKAZ",
    "razlog":"Nedostaje pisanu komunikaciju u spisu","prioritet":"high",
    "status":"open","correlation_id":"503fa399-a199-48e9-b34a-e30279336721",
    "confidence":1.0,"created_at":"2026-09-10T22:24:13Z"}
   ```
This is a real row from `case_actions`, written by `services/case_evolution.py:1175` (the sole INSERT point for that table), reached via `event_bus` dispatch of the event emitted by the upload endpoint. **DOCUMENT → EVENT → EVOLUTION → CASE ACTION is PROVEN live for the auto-analyze upload path.**

Full causal chain, read directly from the `events` outbox table for this predmet (4 rows, all cleanly dispatched, `dispatch_attempts: 0`, `last_error: null`):

| event_type | created_at | dispatched_at | correlation_id |
|---|---|---|---|
| `predmet_kreiran` | 22:23:51.82 | 22:23:58.43 | `cc29fe44...` |
| `NewEvidenceRegistered` | 22:23:58.93 | 22:24:21.34 | `503fa399...` |
| `DocumentAccepted` | 22:23:59.14 | 22:24:16.16 | `503fa399...` |
| `GenomeUpdated` | 22:24:11.30 | 22:24:14.63 | `c7b46da3...` |

`NewEvidenceRegistered`/`DocumentAccepted` share the upload's `correlation_id` (`503fa399-...`) — the same `correlation_id` that appears on the resulting `case_actions` row shown above. This is a complete, correlation-ID-linked, runtime-proven chain: **upload → 2 events emitted → genome refresh event → case_actions insert**, not a coincidence or an unrelated background process.

Constraint discovered along the way (not a bug, a product gate): upload requires **Professional tier or higher** (`PermissionService.require("predmet_upload_ai")`) and **PDF/DOCX only** (415 on `.txt`) — both enforced correctly, just not obviously documented for a live test.

## C. Manual evidence path — PROVEN MISSING (confirms prior finding, now with runtime proof)

- `routers/evidence.py:309` `add_dokaz` (POST `/api/evidence/predmeti/{id}/dokaz`) — read in full (L309-397). Its body calls only `shared/evidence_write.py::upisi_dokaz`. No call to `event_bus`, `emit`, `emit_durable`, or `case_evolution` anywhere in the function or its imports.
- `shared/evidence_write.py::upisi_dokaz`/`upisi_dokaze` (L489-604+) — grepped for `case_evolution|emit|durable|case_action`: zero hits. Docstring/comment at L505-521 confirms the call direction is `case_evolution → evidence_write` (idempotency marker `predmet_dokumenti.klasifikovan_at` is checked by `case_evolution` *before* calling this function), never the reverse.

**Live proof** (fresh predmet `0a5960ee-862b-45c1-ae22-2280f501ce8a`, same Professional-tier test user):
1. Baseline `case_actions`: `broj_akcija: 0`.
2. `POST /api/evidence/predmeti/{id}/dokaz` with a real fact (`"Tuženi AD Vodovod nije odgovorio na tužbu u roku od 15 dana..."`, `snaga: "jaka"`) → `200 {"ok":true,"id":"52380cf0-...","snaga":"jaka","snaga_izvor":"covek",...}`. The evidence write itself succeeds.
3. Polled `case_actions` every 5s for 30s → **`broj_akcija: 0` the entire time.** No event ever fires, no evolution run, no case action, no trace.

**This is the confirmed, live-verified gap**: a lawyer manually entering a fact — the single most basic "I learned something about my case" action — produces zero downstream effect. It sits in `predmet_dokazi` but never reaches the Consequence Engine. This is the exact target of Task 2.

## D. `case_actions` write-point — PROVEN single writer

- `services/case_evolution.py:1175` — `supa.table("case_actions").insert(r).execute()` — the ONLY insert into this table in the entire codebase (confirmed by repo-wide grep, unchanged from prior audits). No other router, service, or script writes to it directly. This is a clean single-owner contract — good news, nothing to fix here structurally; the gap is entirely about what triggers a run, not about a second writer.

## E. Deadlines/rokovi — INFERRED, likely Task 6 = legitimate STOP territory

- **PROVEN**: no `rokovi`, `deadlines`, or `predmet_rokovi` table exists in the live schema (`PGRST205` "Could not find the table" for all three, checked live via PostgREST schema cache).
- `rocista` (hearings) is a real, separate table (`routers/rocista.py`) — distinct concept from statute-of-limitations/response deadlines.
- The `case_actions` row observed in section B carries a `"rok": null` field — i.e. deadline is a *column on a case action*, not a first-class scheduled entity, and in the one live sample produced it was not populated even though the source PDF explicitly stated "Rok za odgovor na tužbu je 15 dana."
- This is consistent with prior memory findings `project_blk1_deadline_safety_closed` (rok fabrication fixed by never reading an untrusted threshold at write time) and `project_blk3_email_reminders` (no scheduler wired to `/api/cron/daily`, SMTP not live at runtime).
- **Not yet investigated at full rigor in this pass**: whether any extractor attempts to populate `case_actions.rok` from document dates at all, and whether anything reads/surfaces it once populated. Marked UNKNOWN pending Task 6's own dedicated investigation — flagging now that the honest expectation, given no dedicated table and no confirmed extractor/scheduler pairing, is that Task 6 will legitimately need to STOP per the mandate's own explicit allowance rather than force an unsafe deadline feature into existence overnight.

## F. AI context freshness — UNKNOWN (not re-investigated this pass; carries forward prior finding)

Prior audit's finding (not re-verified live in this session due to time budget): `kontekst_predmeta` flag in `/api/pitanje` correctly reflects whether matter context was used, but does not guarantee freshly-added facts (e.g. the manual `add_dokaz` entry from section C, which never triggers re-embedding/re-indexing since it never reaches the Consequence Engine) are actually present in the prompt. Given section C's proof that manual evidence never fires an event, it is now **more strongly suspected** that a fact added via `add_dokaz` would not be reflected in the next AI answer until some other path re-indexes it — but this needs its own live A/B test (ask a question before/after a manual `add_dokaz` call) to move from INFERRED to PROVEN. Not done in this pass.

## G. Transaction/atomicity — UNKNOWN (not investigated this pass)

Not examined this pass: whether `evidence_write` + `event_bus.emit_durable` + `case_evolution`'s eventual `case_actions` insert share any transactional boundary, or whether a crash between steps can strand state (e.g. evidence written, event row written but never dispatched, or event dispatched but evolution partially applied). Given `emit_durable` is described as an "outbox pattern," some durability is architecturally intended, but retry/idempotency-under-failure was not live-tested (no induced failure in this pass).

## H. Duplicate/competing mechanisms — UNKNOWN (not investigated this pass)

Not searched this pass for a second, competing event/consequence mechanism outside `event_bus.py`/`case_evolution.py` (e.g. `services/case_pipeline.py` and `routers/case_pipeline.py` appeared in the repo-wide grep for `case_actions` and were not read in this pass — worth checking they don't duplicate `handle_case_changed`'s responsibility).

---

## Task 0 Adversarial Check (mandated 5-point check)

1. **"The event bus is dead code / never actually runs."** — FALSIFIED. Live startup log shows the dispatch loop starting and polling; a live document upload produced a live `case_actions` row within ~13s, which is only possible if the loop is genuinely dispatching.
2. **"case_evolution is already called from successful document ingestion."** — CONFIRMED TRUE, with runtime evidence (section B). This reverses the prior audit's conclusion; the prior audit's grep window was too narrow, not the code itself.
3. **"Manual evidence entry already reaches the Consequence Engine some other way (e.g. a background reconciler)."** — FALSIFIED, now with direct outbox-table proof (not just absence-of-effect). Queried `events` table for the test predmet (`0a5960ee-862b-45c1-ae22-2280f501ce8a`) directly: it contains exactly **one** row, `event_type: "predmet_kreiran"` (from case creation), cleanly `dispatched_at` ~5s after `created_at`. **There is no event row at all for the manual `add_dokaz` call** — not a queued-but-undispatched row, not a failed-dispatch row with `last_error` set. This proves the gap is a **missing producer** (the route never calls `emit_durable`), not a broken consumer/dispatcher. Task 2's fix is therefore exactly and only: add one `emit_durable(EventType.NEW_EVIDENCE_REGISTERED, ...)` call into `routers/evidence.py::add_dokaz`, matching the proven-working shape at `api.py:6012`. No dispatcher-side work needed.
4. **"case_actions has more than one writer, so the contract is already fragile."** — FALSIFIED. Single INSERT point confirmed (section D), consistent with all prior audits on this point.
5. **"Deadlines are already tracked somewhere else under a different name."** — PARTIALLY CONFIRMED / PARTIALLY OPEN. `rocista` tracks hearings (a real, different concept). `case_actions.rok` is the only deadline-shaped column found and it was NOT populated in the one live sample despite an explicit statutory deadline being present in the source document — suggests deadline extraction, if it exists at all, did not fire for this document, or fires on a different signal than the one tested. Not fully resolved; carried into Task 6 as an open question rather than asserted either way.

## Follow-up not yet done (honest gap disclosure)

(a) is now RESOLVED — see Adversarial Check item 3 above (direct `events` table query, missing producer confirmed). Still open: (b) live A/B test of `/api/pitanje` freshness before/after a manual fact add; (c) read `services/case_pipeline.py` / `routers/case_pipeline.py` for a possible duplicate mechanism.

## TASK 0 GATE DECISION

**PASS WITH CORRECTIONS.** The event/evolution spine is real infrastructure, not vaporware — it works end-to-end for the document-upload path, live-proven. The prior audit's "document path is 0% wired" claim is **retracted** by this evidence. The manual-evidence-path gap is **confirmed live**, not just inferred, and is the single highest-value, most concretely scoped fix available (Task 2's exact target: add one `emit_durable(EventType.NEW_EVIDENCE_REGISTERED, ...)` call, matching the shape already proven correct in the upload path at `api.py:6012`, into `routers/evidence.py::add_dokaz`).

Recommended immediate next step: Task 2 (wire `add_dokaz` → event contract) is now the best-evidenced, lowest-risk, highest-value next action — it reuses an already-proven event shape and dispatch mechanism, it does not require inventing new infrastructure, and it closes the exact gap this dossier just proved live.

Recommended before Task 6: resolve the section-E open question (a) above — check the outbox table directly — since it changes what "fix deadlines" even means.

No push. No deploy. All testing done against a local server + isolated test account; founder's data and account untouched.
