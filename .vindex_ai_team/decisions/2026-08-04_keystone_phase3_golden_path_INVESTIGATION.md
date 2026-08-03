# Mission Keystone — Phase 3: Golden Path End-to-End Trace (read-only investigation)

Traced the actual code path (not the idealized pipeline name list) by reading real router/service
code and following real function calls. No fixes applied. All findings below are grounded in
file:line citations from the current repo state (2026-08-04).

---

## 1. Novi klijent

**File**: `klijenti/router.py:211` (`POST /klijenti`, `create_klijent`).

- Result exists: Yes — `supa.table("klijenti").insert(row)` (line 249-251).
- Ownership: Yes — `user_id` set from the authenticated user (line 224).
- Correlation: **No** — no `case_context()`/correlation_id anywhere in this handler. Reasonable:
  no AI call happens here, and Mission Ledger's design only auto-fills correlation_id for AI-call
  contexts; a plain CRUD create was never in scope for that mechanism.
- Audit: Partial — `log_event(akcija=Akcija.CREATE, ...)` (line 254-258) writes to the **access-log**
  audit table (`shared/audit.py`'s `log_event`), NOT the hash-chained `audit_immutable` table Mission
  Ledger/Migration standardized on for business actions. This is a genuinely different, older audit
  mechanism — client creation is not part of the `AUDITABLE_ACTIONS` immutable-audit allowlist.
- Provenance: N/A — no AI call.
- No duplicates: **Gap** — no idempotency key/dedup check on client creation; two rapid duplicate
  submissions (e.g. a lawyer double-clicking "create client" from a slow UI) would create two
  `klijenti` rows with identical data, no unique constraint observed on (user_id, ime, prezime, email).
  Not verified against the DB schema directly (would need the migration that created `klijenti`) —
  flagged as **not fully verified**, not asserted as fact.
- No data loss: `asyncio.create_task(log_event(...))` (line 254) is fire-and-forget — if it fails, the
  client row itself is unaffected (already committed before the task is scheduled), so no data loss on
  the primary record, only on the access-log entry.

**Verdict: Partial.** Client creation itself is solid (durable, ownership-scoped). Its audit trail uses
a different, older mechanism than the rest of the golden path (`audit_log`, not `audit_immutable`) —
worth knowing for anyone querying "show me every action on this case" expecting one unified table.

---

## 2. Kreiranje predmeta

**File**: `api.py:3135-3220` (`POST /api/predmeti`, `kreiraj_predmet`).

- Result exists: Yes, durable `predmeti` row insert.
- Ownership: Yes, `user_id` scoped.
- Correlation: Yes — Mission Ledger wired this to emit a durable `PREDMET_KREIRAN` event (direct
  `events` table insert, not in-process `emit()`) carrying `correlation_id`.
- Audit: Yes (Mission Ledger/Sentinel `AUDITABLE_ACTIONS`).
- Provenance: N/A (no AI call at creation itself).
- No duplicates: Not re-verified this pass (out of this investigation's specific scope; would need to
  check for a unique-name-per-user constraint, which likely doesn't exist by design — two cases can
  legitimately share a name).
- No data loss: The durable-outbox design (not in-process `emit()`) means even if the API process
  crashes right after the DB commit, `dispatch_pending_events()` will still deliver `PREDMET_KREIRAN`.

**Verdict: Pass.** Solid — this is the most mature step in the whole chain (3 prior missions'
combined hardening).

### The critical downstream connection: `PREDMET_KREIRAN` → Case Pipeline

`services/event_bus.py:108-118` (`on_predmet_kreiran`) calls `services/case_pipeline.py:674`
(`run_case_pipeline`) — **this DOES fire automatically**, contradicting the older
`project_case_genome_forensic_audit.md` memory note ("Case Pipeline's 9-step process never
auto-fires") for at least this one trigger path. That memory is now **stale** for this specific claim
— re-verified today, the wiring exists and runs.

**BUT — a load-bearing detail the old finding's "it's fixed" framing would miss**: `run_case_pipeline`
fires at `PREDMET_KREIRAN` time, i.e. **before any documents are uploaded**. Reading its 9 steps
(`services/case_pipeline.py:159-751`):
- `_step_analiza_dokumenata` (line 159): returns `SKIPPED` if no docs — always true at this point.
- `_step_ekstrakcija_rokova` (line 219), `_step_strategija` (line 351): both operate ONLY on
  `predmet.naziv`/`predmet.opis` (case title/description text), never on document content — by
  design, this is explicitly a "lite," idempotent, day-zero pass, not a full analysis.
- `_step_risk_snapshot` (line 500): correctly delegates to the single canonical `risk_engine.py`
  (Core Consolidation) rather than computing its own number — good design, re-confirmed live.
- Every step is **idempotent via a marker check** (`predmet_istorija` rows tagged `[Pipeline:rokovi]`,
  `[Strategija Pipeline]`, `[Rizik] {date}`) — meaning **this pipeline does not naturally re-run when
  real documents are uploaded later**, because the guard clauses find a marker already present (for
  `rokovi`/`strategija`, which are one-time, not per-day) and skip.

---

## 3-4. Upload više dokumenata → OCR

**File**: `api.py:4078` (`POST /api/predmeti/{predmet_id}/upload`, `predmet_upload_auto_analyze`).

- Result exists: Yes — `predmet_dokumenti` row (line 4226-4244), Pinecone vector (line 4183-4208).
- Ownership: Yes, `user_id`/`predmet_id` scoped throughout.
- Correlation: Not explicit at the upload-write level itself, but the downstream AI analysis calls
  (procena/hronologija, line ~4436+) run inside `case_context()` per Mission Migration.
- Audit: Yes — `dokument_upload` (line 4266-4278), pre-existing and in `AUDITABLE_ACTIONS`.
- Provenance: Yes for the AI analysis calls that follow (wrapper-captured).
- No duplicates: `source_sha256` is computed (line 4169) but **not used for dedup** — confirmed still
  true today (matches Sentinel's `SENT-008`, unchanged) — uploading the same file twice creates two
  full `predmet_dokumenti` rows + two Pinecone vectors, each independently classified/genome'd.
- No data loss: **Fixed by Project Sentinel, re-confirmed today** — `api.py:4258-4262` raises HTTP 500
  immediately if `_dok_id` is falsy (the "ghost document" fix), before any downstream classification/
  genome/AI-analysis work. Residual gap, explicitly commented in the code itself (line 4248-4257): if
  the `predmet_dokumenti` insert fails AFTER the Pinecone ingest already succeeded, the Pinecone vector
  is not cleaned up — a real, named, still-open gap (orphan vector), not silent (the code comment
  points at `SENTINEL_PRE_BETA_CRITICAL_PATH.md`).

OCR itself: `extract()` (from `uploaded_doc.extractor`, called line 4135) raises
`DocumentSafetyLimitExceeded` (handled, line 4136-4144) or returns `is_scanned=True` for an unreadable
scan (handled, line 4145-4149, clear HTTP 422 to the user) — both failure modes surface as an honest
error to the caller, not a silent pass-through. **Verdict: Pass** for the failure-signaling contract;
**Partial** for OCR itself (not independently re-traced deeper than this call site this pass — retry/
backoff internals of `extract()` not re-read).

---

## 5-6. Classification → Extraction

**File**: `api.py:4280-4289` → `routers/evidence.py::klasifikuj_i_sacuvaj` (fire-and-forget background
task, `asyncio.create_task(asyncio.to_thread(...))`).

- Result exists: Yes, `predmet_dokumenti.tip_dokaza` + `predmet_dokazi` rows.
- Ownership: Yes.
- Correlation: Yes — wired by Mission Migration (`case_context()` + `log_action_sync`, the
  worker-thread-safe variant, confirmed still correct today — no `asyncio.create_task(log_action(...))`
  regression reintroduced).
- Audit: Yes — `evidence_klasifikacija` (Mission Migration).
- Provenance: Yes (wrapper-captured GPT call).
- No duplicates: Runs once per upload call; a duplicate-upload (per #3-4 above) produces a duplicate
  classification too, same root cause, not a separate bug.
- No data loss: Fire-and-forget — if this task raises, nothing surfaces to the user (the upload
  response has already been sent by this point in the code, line ~4289 is after the response-shaping
  logic begins). **This is a real, silent-degradation gap**: a classification failure is invisible to
  both the lawyer and to any monitoring surface unless someone is reading application logs. Distinct
  from the fixed “ghost document” bug — this is a downstream *enrichment* step, not the document
  record itself, but its failure is currently unobservable at the product layer (no alert, no
  audit-of-failure entry, unlike Project Phoenix's nightly-alert-insert fix which added exactly this
  kind of durable failure record for a different subsystem).

**Verdict: Partial** — works when it works, but failure is silent to the user/operator layer.

---

## 7. Case Genome

**File**: `api.py:4292-4304` (fires `_genome_bg()` 3s after upload) → `routers/case_dna.py:629`
(`_run_genome_background`) → `:661` (`_do_genome_refresh`).

- Result exists: Yes, `predmeti.case_dna` JSON column updated (line 737-743).
- Ownership: Yes.
- Correlation: Yes, `case_context()` (line 715-718).
- Audit: Yes, `_emit_genome_event` (line 745-748) — durable outbox insert with `correlation_id`, fixed
  this cycle by Project Phoenix's re-raise/dead-letter work on the consumer side
  (`on_genome_updated`, `services/event_bus.py:207`).
- No duplicates/races: **Explicitly and carefully handled** — an in-process coalescing lock
  (`_genome_refresh_inflight`/`_genome_refresh_rerun`, line 646-658) collapses concurrent triggers for
  the same `predmet_id` into one re-run, closing a real lost-update race the code's own comment
  documents finding (attributed to a "Zero-Touch Case investigation, 2026-08-03, BETA-002/Scenario F"
  — a prior session's work this investigation did not otherwise touch, re-confirmed intact today).
  Explicitly documented residual limitation: in-process only, does not coalesce across separate worker
  processes if the app ever runs multi-process — stated honestly in the code comment, not hidden.
- No data loss: Wrapped in try/except at the top level (line 782-783) — a genuine failure here is
  logged but does not raise past this function (this background task has no caller awaiting it, so
  there's nothing to propagate to). Same silent-to-the-user-and-operator shape as classification above.

**Verdict: Pass** for correctness/consistency (the coalescing fix is genuinely good engineering);
**Partial** for observability (same silent-background-failure pattern as classification).

### The critical downstream connection: does Genome refresh trigger Risk/Strategy/Deadlines?

**No.** `_do_genome_refresh` (case_dna.py:661-783) only: updates `case_dna`, emits `GENOME_UPDATED`
(audit-only consumer), inserts a `proactive_alerts` row if the delta is significant, calls
`_maybe_alert_require_review`, and calls `_sync_rokovi_to_hronologija` (line 732 — this DOES feed the
Timeline, see #9 below). It does **not** call `run_case_pipeline` again, does not call
`_step_strategija`/`_step_risk_snapshot` again, and does not trigger `zadaci.py`'s task generation.

**This is where the golden path, as named in the mission brief, actually breaks**: the mission's
diagram implies Genome → Risk Analysis → Strategy Engine flow automatically once real case content
exists. In the real code, Risk Analysis is a live, correct, on-demand computation (`risk_engine.py`,
re-read anytime via Dashboard/Matter Intel — not stale, just not "pushed" by Genome), but **Strategy
Engine's full analysis and Task Generation are lawyer-initiated, separate endpoints**
(`routers/strategija.py`, `routers/zadaci.py:492` `/ai-analiziraj/{predmet_id}`) that a user must
click into. The only automatic "strategy" a case ever gets is Pipeline's day-zero lite pass from the
case description alone (see #2), which is idempotency-locked from ever re-running once real evidence
exists.

**This is a real, product-relevant gap** — not a bug (nothing crashes, no data is lost), but a
disconnect between the "AI keeps this case's intelligence current" mental model the golden path
implies and what the code actually does (initial-only auto-pass, then manual for anything deeper).

---

## 8. Risk Analysis

**Files**: `services/risk_engine.py` (canonical, per Core Consolidation Sec 1.1), surfaced via
`routers/dashboard.py`/`routers/matter_intel.py`.

- Computed on-demand from live DB state each time it's read (not cached/stale) — confirmed by
  `_step_risk_snapshot`'s own comment (case_pipeline.py:500-511) explicitly stating there is now
  exactly one algorithm, read not recomputed independently.
- Ownership/ ownership scoping: inherited from whatever endpoint reads it — not independently
  re-verified this pass beyond the case_pipeline call site.
- Audit/provenance: N/A — deterministic calculation, not an AI call, correctly not routed through
  `ai_forensics`.

**Verdict: Pass** — but only reachable by a user actively viewing Dashboard/Matter Intel; not "pushed"
anywhere (no alert-on-risk-increase beyond the existing `on_health_score_promenjen` threshold-alert
at <30, `services/event_bus.py:138-159`, unchanged from Phoenix).

---

## 9. Strategy Engine

**File**: `routers/strategija.py` (9 GPT-calling endpoints, all migrated onto `case_context()` +
`log_action` by Mission Ledger).

- **Not auto-triggered from Genome or Upload** (see #7's finding). A lawyer must explicitly call one of
  the 9 endpoints.
- Once called: correlation/audit/provenance all confirmed wired (re-verified Ledger's work is still
  intact — no regression found).
- Persistence: `SENT-003` (Strategy Engine persistence — link legal conclusions to `predmet_id`) was
  still `NEEDS_SCOPING` as of Phoenix's own board update — **re-confirmed still true today**: every
  Strategy Engine call's rich output is returned to the caller and audited, but not written back into
  any case-level field Timeline/Genome/Dashboard would read. A lawyer who runs Strategy Engine and
  doesn't screenshot/save the response has no way to see it again except via the audit log's raw
  metadata (not a designed retrieval path).

**Verdict: Partial** — correct and safe when invoked, not connected into the automatic case lifecycle,
and its output isn't persisted anywhere a later Timeline/Dashboard view would surface it.

---

## 10. Timeline

**File**: `routers/intelligence_timeline.py:56` (`GET /{predmet_id}/intelligence-timeline`) — a
read-only synthesis endpoint, not a write step.

- Reads from `predmet_hronologija`, which IS populated by Genome refresh's
  `_sync_rokovi_to_hronologija` call (case_dna.py:732) — **this connection is real and confirmed**.
- Ownership: scoped via `get_current_user` + predmet_id path param (not independently re-verified for
  a cross-tenant check at the SQL/RLS level this pass).

**Verdict: Pass** — correctly wired to Genome's output, no gap found.

---

## 11. Deadlines

Covered by `_step_ekstrakcija_rokova` (day-zero, case_pipeline.py:219) and Genome's own
`_sync_rokovi_to_hronologija` (case_dna.py:732, fires on every genome refresh, i.e. every real
document upload — this is more current than Strategy Engine's equivalent gap). `ROK_KRITICAN` alerting
exists (`on_rok_kritican`, event_bus.py:73) but **remains non-durable** (`SENT-001`, re-confirmed
unchanged — still `emit()`'d in-process, not via the durable outbox `PREDMET_KREIRAN`/`GENOME_UPDATED`
now use).

**Verdict: Partial** — the data pipeline (extraction → hronologija) is genuinely more current/connected
than Strategy Engine's, but the alert on a critical deadline is one process crash away from silently
not firing (same gap Sentinel identified and Phoenix left open by design, pending a dedup-safety
check before conversion).

---

## 12. Task Generation

**File**: `routers/zadaci.py:492` (`POST /ai-analiziraj/{predmet_id}`) — **manual, lawyer-initiated**,
not triggered by Genome/upload/pipeline. Audited (`zadaci_ai_analiza_complete`, Mission Atlas).

**Verdict: Partial** — same shape as Strategy Engine: correct and audited when invoked, not part of the
automatic chain the golden path narrative implies.

---

## 13. Evidence Analysis

Covered by #5-6 above (classification) plus `routers/evidence_graph.py` (relationship/graph view over
already-classified evidence) — not independently re-traced deeper this pass; presumed consistent with
#5-6's findings (silent background-failure risk, otherwise correctly wired) since it reads the same
`predmet_dokazi` data classification populates.

**Verdict: Not independently re-verified beyond the classification step it depends on.**

---

## 14. Briefing

`routers/morning_briefing.py` — two genuinely separate endpoints, confirmed (again) this pass:
on-demand briefing (works standalone) and `nightly_intelligence_run` (Phoenix-hardened alert-insert
retry + durable failure audit). Both wired to `case_context()`/audit per Ledger/Migration.
**Verdict: Pass** — thoroughly re-verified by the immediately preceding Project Phoenix mission; no
new regression found on re-check.

---

## 15. Copilot

`routers/copilot.py` — all business-mutating handlers plus `ask_agent`/Drafting now migrated (Phoenix).
**Verdict: Pass**, consistent with Phoenix's closing state, spot-checked not fully re-derived from
scratch this pass (would duplicate Phoenix's own just-completed work).

---

## 16. Firm Brain / 17. Memory Graph

**Files**: `routers/firm_memory.py`, `routers/memory_graph.py`.

Both expose only manual CRUD-style endpoints (`/dodaj`, `/dodaj-vezu`, `/pretrazi`, `/upit`,
`/kontekst-za-ai`, etc.) — **confirmed via a repo-wide grep that ZERO other module imports or calls
into either router's functions** (`grep -rn "from routers.memory_graph import\|from routers.firm_memory
import"` across the whole repo returns nothing outside the routers' own files and their tests).

**This means "Firm Brain" and "Memory Graph" are NOT part of the automatic golden path at all** — they
are standalone features a lawyer must manually populate and query. No step in Upload → Genome →
Strategy → Briefing → Copilot writes into either of them. This reconfirms (as still true today, not
stale) the substance of the "thin/unconnected" characterization in prior session memory
(`project_case_genome_forensic_audit.md`'s "zero connection to Firm DNA/Learning" finding) — the
specific mechanism has been re-verified independently this pass via direct grep, not merely cited.

**Verdict: Gap** — the golden path's own diagram lists these as pipeline steps; in the real system they
are isolated islands with no automatic feed.

---

## 18. Search

`routers/search.py::global_search` — re-verified consistent with Project Phoenix's just-completed
`nepotpuno` degraded-signal fix; reads `predmet_dokumenti.tekst_sadrzaj`/`tip_dokaza` (correctly, per
Phoenix's fix), not the dead `uploaded_documents` table. **Verdict: Pass.**

---

## 19. Alerts

`proactive_alerts` table — populated by Genome delta (case_dna.py:763-773), health-score threshold
(event_bus.py:146-155), rok_kritican (event_bus.py:91-99, non-durable per #11), document-job-failure
(event_bus.py:191-200), and nightly cron (Phoenix-hardened). **Verdict: Pass** for the durable paths,
**Partial** carried forward for `ROK_KRITICAN`'s non-durability (same `SENT-001`, not new).

---

## 20. Dashboard

Reads live from `predmeti`/`risk_engine`/`proactive_alerts` — a read-model, not a write step; no new
finding beyond what feeds it (already covered above).

---

## 21-22. Audit / AI Provenance

Both re-confirmed structurally sound and NOT re-derived from scratch this pass (would duplicate the
last 4 missions' direct, extensively-tested work): `shared/ai_client.py`'s wrapper (100% coverage,
re-confirmed indirectly via every AI-calling step traced above going through `case_context()`),
`shared/audit_immutable.py`'s hash chain, `security/ai_forensics.py`. **Verdict: Pass**, inherited
confidence from Atlas/Ledger/Migration/Phoenix's own extensive, repeatedly-adversarially-re-verified
work — no reason found this pass to doubt it, but also no NEW independent stress applied to it here
(that's this same Mission Keystone's Phase 2/4 work, not this Phase 3 trace).

---

## Summary verdict table

| # | Step | Verdict |
|---|---|---|
| 1 | Novi klijent | Partial (different audit mechanism, no dedup) |
| 2 | Kreiranje predmeta | Pass |
| 3-4 | Upload + OCR | Pass (failure signaling) / Partial (OCR internals, dedup) |
| 5-6 | Classification/Extraction | Partial (silent background failure) |
| 7 | Case Genome | Pass (correctness) / Partial (observability) |
| 8 | Risk Analysis | Pass (not push-notified) |
| 9 | Strategy Engine | Partial (not auto-chained, not persisted) |
| 10 | Timeline | Pass |
| 11 | Deadlines | Partial (alert non-durable) |
| 12 | Task Generation | Partial (not auto-chained) |
| 13 | Evidence Analysis | Not independently re-verified beyond #5-6 |
| 14 | Briefing | Pass |
| 15 | Copilot | Pass |
| 16-17 | Firm Brain / Memory Graph | **Gap** (isolated, zero automatic feed) |
| 18 | Search | Pass |
| 19 | Alerts | Pass / Partial (ROK_KRITICAN) |
| 20 | Dashboard | Pass (read-model) |
| 21-22 | Audit / Provenance | Pass (inherited, not re-derived) |
