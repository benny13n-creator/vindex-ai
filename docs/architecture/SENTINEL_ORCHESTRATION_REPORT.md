# Project Sentinel — Orchestration Report

**Mission:** Pre-Beta Reliability, Trust & Operational Integrity Mission, 2026-08-03. Verification
record for every code change implemented this mission, in the mission's own stated priority order
(Critical Flow Integrity > Security > Reliability > Automation > Optimization).

Five parallel read-only investigation forks (Phase 1 critical-flow forensics, Phase 2 Event Bus
hardening, Phase 3 failure-recovery simulation, Phase 4 source-of-truth re-sweep, Phase 5+6
provenance/hallucination audit) fed the fixes below — see
`.vindex_ai_team/decisions/2026-08-03_sentinel_*_INVESTIGATION.md` for full evidence.

---

## Fix 1 (CRITICAL) — `api.py::predmet_upload_auto_analyze` no longer returns a false success signal

**Finding**: Sentinel Phase 3 (failure_recovery investigation, §8) proved by code trace that if the
`predmet_dokumenti` insert fails *after* Pinecone ingestion already succeeded, the endpoint continued
to the GPT procena/hronologija/metapodaci block unconditionally, then returned HTTP 200 with
`"auto_analyzed": true` and a full AI legal analysis — for a document that never appears in the case's
own document list. A permanent orphaned Pinecone vector plus a `predmet_istorija` entry referencing a
nonexistent document. This is Beta Gate question 4 ("Može li korisnik dobiti lažnu potvrdu uspeha?")
answered **yes**, proven by code, not hypothesis.

**Fix**: added `if not _dok_id: raise HTTPException(500, ...)` immediately after the document-insert
try/except block, before any classification/Genome/GPT work begins. Matches the pattern already
correctly used two blocks later for classify/genome-refresh (`if _dok_id:`), just applied earlier and
made blocking rather than silently-skippable.

- **Existing APIs reused**: 100% — no new code paths, just an earlier, honest exit.
- **What was NOT changed**: the already-ingested Pinecone vector is not rolled back (best-effort
  cleanup would need a delete-by-metadata call not verified safe this session — flagged as a future
  hardening item, not attempted blind).
- **Tests**: `tests/test_sentinel_reliability_fixes.py::test_upload_raises_honest_error_when_document_insert_fails_after_pinecone_success`.

## Fix 2 (CRITICAL) — dead duplicate `GET /api/search` route removed

**Finding**: Sentinel Phase 1 (critical_flows investigation, headline finding) proved via a live
`app.routes` dump that `api.py` and `routers/search.py` both registered `GET /api/search`. Starlette
matches first-registered; `routers/search.py` always won, so `api.py`'s own ~130-line implementation was
100% unreachable dead code — the second confirmed instance of this exact anti-pattern this engagement
(first: SEC-002, `/api/cron/daily`).

**Fix**: deleted `api.py`'s dead `global_search` definition entirely. Zero behavior change — it never
executed. `routers/search.py`'s implementation (broader: dokumenti/billing/zadaci/hronologija/beleske,
missing only `predmet_komentari` search) is now the sole, visibly-live implementation.

- **What was NOT changed**: `predmet_komentari` search coverage — that capability was never reachable
  by any user (only the dead code offered it), so its absence is not a regression; adding it to
  `routers/search.py` would be a feature addition, out of this mission's scope.
- **Tests**: none needed — pure dead-code deletion, confirmed via grep that nothing imports
  `api.global_search`.

## Fix 3 (CRITICAL) — `PREDMET_KREIRAN` converted to durable outbox

**Finding**: Sentinel Phase 2 (event_bus_hardening) and Phase 3 (failure_recovery) both independently
confirmed `PREDMET_KREIRAN` is emitted purely in-process (`bus.publish()` via fire-and-forget
`asyncio.create_task`), with zero durable-outbox backing — the single largest reliability gap in the
event architecture (already flagged as NEX-004 in Project Nexus, blocked pending idempotency
verification). A crash between the `predmeti` insert committing and `run_case_pipeline` completing
silently and permanently drops the entire 9-step Case Pipeline (rokovi, mini-strategy, HCC briefing,
risk snapshot) with zero trace anywhere that it was ever supposed to run.

**De-risking**: Phase 2's investigation confirmed `run_case_pipeline`'s steps are idempotent by design
(marker-based dedup, e.g. `_step_ekstrakcija_rokova`'s `[Pipeline:rokovi]` sentinel row) — removing the
NEX-004 blocker.

**Fix**: `api.py::kreiraj_predmet` now writes directly to the `events` table (durable outbox) instead of
calling `emit()`, mirroring `routers/case_dna.py::_emit_genome_event`'s already-proven pattern exactly
(same reasoning: avoid double-handler-run by using ONE path, not both). `dispatch_pending_events()`'s
poller invokes the already-registered `on_predmet_kreiran` handler; a crash now only delays the pipeline
by up to one poll interval (3s), never silently drops it.

- **Existing APIs reused**: 100% — `events` table schema and `dispatch_pending_events()` poller already
  existed and are already proven correct for `GENOME_UPDATED`.
- **Tests**: `tests/test_sentinel_reliability_fixes.py::test_kreiraj_predmet_writes_predmet_kreiran_to_durable_outbox`,
  `test_kreiraj_predmet_still_succeeds_if_durable_event_insert_fails`.

## Fix 4 (HIGH) — `DOCUMENT_JOB_FAILED` handler added

**Finding**: Sentinel Phase 1 and Phase 2 both independently confirmed `DocumentJobFailed` is a real,
durably-recorded event (fired by `fail_intake_job` RPC when an intake job exhausts all retries) that
was dispatched and marked handled with **zero subscribed handlers** — a permanently-failed OCR/intake
job produced no `proactive_alerts` row, no notification, nothing. Direct answer to Beta Gate question 5
("Može li kritična greška ostati neprimećena?" — yes, for this specific class, before this fix).

**Fix**: added `on_document_job_failed` to `services/event_bus.py`, subscribed in `_register_defaults()`.
Since `fail_intake_job`'s outbox insert carries only `intake_job_id`/`attempts`/`error` (no
`user_id`/`predmet_id` on the `events` row itself), the handler resolves the job owner via
`intake_jobs.uploaded_by` before writing a `proactive_alerts` row — matching `on_rok_kritican`'s
established alert-insert pattern. Defensively skips (logs, does not crash) if the owner can't be
resolved, since `proactive_alerts.user_id` is `NOT NULL`.

- **Existing APIs reused**: 100% — `proactive_alerts` table and insert pattern already existed.
- **Tests**: `tests/test_sentinel_reliability_fixes.py::test_on_document_job_failed_creates_proactive_alert`,
  `test_on_document_job_failed_skips_alert_when_job_owner_unresolvable`,
  `test_document_job_failed_is_registered_in_event_bus_defaults`.

## Fix 5 (HIGH) — `routers/dashboard.py::matter_health_score` delegated to canonical Risk Engine

**Finding**: Sentinel Phase 4 (source_of_truth_recheck, a broader sweep than Project Nexus's Phase 5)
found a **third**, independently-weighted case-health formula — different category weights, a 48h
critical-deadline window instead of the 7-day window `calculate_procesni_rizik` uses everywhere else,
cruder document counting with no `tip_dokaza` matching. Not wired to any frontend caller (confirmed via
grep across `static/*.js`), but fully alive — routed, and covered by 7+ passing tests — a landmine for
whoever wires it into a UI panel later and gets a number that silently disagrees with Matter
Intel/CCC/Cockpit for the same case on the same day.

**Fix**: rewrote the endpoint's scoring to delegate to `services/risk_engine.py::calculate_procesni_rizik`/
`identify_case_problems` — same pattern as `routers/ccc.py`'s fix in Project Nexus. `score` and `status`
now derive directly from the canonical `health_score`/`nivo` (mapped `Nizak→zdrav`, `Srednji→upozorenje`,
`Visok→kriticno`); `hitnih_rokova` comes from the canonical `kriticni_rokovi` (7-day window, replacing
the old 48h one). `aktivnost` (beleška/komentar in the last 7 days) is preserved as-is since Risk Engine
doesn't track activity — that's a legitimate endpoint-local signal, not a duplicated fact.
Deletion was considered (per the investigation's own recommendation, since there's no known caller) but
delegation was chosen as materially lower-risk: it preserves the response shape for any consumer this
session's grep couldn't see (a mobile client, a partner integration), while eliminating the
value-level contradiction, which is the actual defect.

- **Existing APIs reused**: 100% — `calculate_procesni_rizik`/`identify_case_problems` already existed
  and are already the canonical source everywhere else.
- **Tests**: `tests/test_dashboard.py`'s 7 `matter_health_score` tests rewritten against the new formula
  (same technique as Project Nexus's `test_ccc.py` rewrite — old assertions encoded the old formula's
  arithmetic, which no longer applies).

---

## Full-suite verification (final gate)

**2329 passed, 1 skipped, 0 failed** across all files this mission's changes touch or could affect
(`api.py`, `routers/dashboard.py`, `services/event_bus.py`, and the full existing suite). 11 additional
failures observed in an unrelated area (`test_business_groups.py`, `test_feature_type.py`,
`test_product_intelligence.py::test_require_admin_allows_founder`, `test_tier_config.py`) were confirmed
via `git stash` to be **pre-existing on the untouched baseline**, unrelated to any file this mission
changed — a `FOUNDER_EMAILS` environment-variable mismatch in the local shell, not a code defect. 13
new/rewritten tests added this mission (6 in `test_sentinel_reliability_fixes.py`, 7 rewritten in
`test_dashboard.py`).

## Beta Critical Path preserved

No endpoint's request/response contract changed in a breaking way for any caller relying on today's
correct behavior. `predmet_upload_auto_analyze` now fails loudly (HTTP 500) only in the exact scenario
where it previously lied (HTTP 200 for a ghost document) — any genuinely successful upload is
unaffected. `matter_health_score`'s response shape (`predmet_id`/`score`/`status`/`razlozi`/`faktori`)
is unchanged; only the underlying numbers are now correct rather than silently divergent. `kreiraj_predmet`'s
response is unchanged (`{"predmet": ...}`); only the pipeline-trigger mechanism became durable.
