# IDOR Matrix — Program Lambda, Certification 002

Every endpoint examined during the two API Penetration sweeps (routers a-m, routers n-z + `api.py`), with a
final status. Per the mission's own closure rule, every row ends in exactly one of: **CERTIFIED** (checked,
already correct, no change made), **FIXED** (bug found, fixed this sprint, regression test added),
**ARCHITECTURAL DEBT** (bug found, not fixed this sprint, tracked in the debt register).

287 endpoints/handlers were checked line-by-line across the a-m sweep alone; 260 were CERTIFIED SAFE with no
change needed. Reproducing all 260 rows here would not add signal — they are listed by file in the coverage
note at the bottom. This table lists every row that is FIXED or ARCHITECTURAL DEBT, i.e. every row that
matters for a beta-readiness decision.

## FIXED this sprint

| # | Endpoint / function | File:line | Bug | Fix |
|---|---|---|---|---|
| 1 | `GET /api/billing/po-klijentu/{klijent_id}` | `routers/billing.py:983-986` | `predmeti` fetch filtered by `klijent_id`-derived ids only, no `user_id` — returned another firm's real case names/status if `klijent_id` was guessed | Added `.eq("user_id", uid)` |
| 2 | `POST /api/billing/entries` | `routers/billing.py:220-226` | `predmet_id` inserted into `billing_entries` with zero ownership check | Added ownership pre-check, 404 if not owned |
| 3 | `POST /api/billing/timer/start` | `routers/billing.py:362-365` | Same as #2, for `timer_sessions` | Added ownership pre-check, 404 if not owned |
| 4 | `POST /api/intake/kreiraj` | `routers/intake.py:194-201` | `predmet_klijenti` insert linked an attacker-supplied `klijent_id` with no ownership check — a foreign client could be planted onto an attacker's new case | Verify `klijenti.eq(id,..).eq(user_id,uid)` before insert; silently skip if not owned |
| 5 | `POST /api/intake/from-template` | `routers/intake.py:784-792` | Same as #4 | Same fix |
| 6 | `GET /api/memory-graph/preporuka/{predmet_id}` | `routers/memory_graph.py:316-322` | `predmeti` fetch had **no tenant filter at all** — any authenticated user could read any case's naziv/tip/status/opis by guessing a UUID, and have it fed into a GPT prompt | Added `.eq("user_id", uid)` |
| 7 | `POST /api/agents/run` (billing agent) | `routers/multi_agent.py:588-608` | `billing_ctx` block queried `billing_entries` by `predmet_id` alone, unconditional on the earlier ownership check — leaked real invoice line items/amounts into the GPT prompt and response for a foreign case | Gated on new `predmet_verifikovan` flag set only when ownership was proven |
| 8 | `POST /api/agents/run` (deadline agent) | `routers/multi_agent.py:611-619` | Same pattern for `rocista` — leaked hearing schedule/notes | Same fix |
| 9 | `POST /copilot/chat` intent PREDLOZI | `routers/copilot.py:922-930` | `predmet_hronologija`/`predmet_dokumenti`/`predmet_beleske` fetched unconditional on the sibling `pred_r` ownership check — real deadlines/document names for a foreign case surfaced as "predlozi" | Restructured to run the 3 follow-up queries only after ownership is confirmed |
| 10 | `POST /copilot/chat` intent POVEZI_KLIJENTA | `routers/copilot.py:799-867` | `predmet_klijenti` insert never verified `predmet_id` ownership (client-side lookup was correctly scoped, but the target case wasn't) | Added ownership pre-check, clean failure response if not owned |
| 11 | `POST /copilot/chat` intent DODAJ_ROK | `routers/copilot.py:680-725` | `predmet_hronologija` insert, unverified `predmet_id` (write-side pollution, same root cause as #9's read path) | Added ownership pre-check |
| 12 | `POST /copilot/chat` intent KREIRAJ_BELEŠKU | `routers/copilot.py:743-782` | Same as #11, for `predmet_beleske` | Same fix |
| 13 | `POST /copilot/chat` intent NAPLATI_RADNJU | `routers/copilot.py:1102-1166` | Same as #11, for `billing_entries` | Same fix |
| 14 | `POST /evidence/predmeti/{predmet_id}/dokaz` | `routers/evidence.py:342-367` | Optional `dokument_id` body field stored as an FK with no check it belongs to the same `predmet_id` | Verify `dokument_id` against `predmet_id` before storing, else null it |
| 15 | `POST /api/predictor/analiza` | `routers/court_predictor.py:337-346` | `predictor_analize` insert stored `payload.predmet_id` verbatim, no ownership check (write-side FK pollution — no disclosure, since all reads are `user_id`-scoped) | New shared `_verifikovan_predmet_id()` helper, applied at all 7 insert sites in this file |
| 16 | `POST /api/predictor/battle-report` | `routers/court_predictor.py:527-537` | Same as #15 | Same fix |
| 17 | `POST /api/predictor/hearing-prep` | `routers/court_predictor.py:671-706` | Same, for `hearing_briefovi` | Same fix |
| 18 | `POST /api/predictor/argument-reputation` | `routers/court_predictor.py:913-922` | Same as #15 | Same fix |
| 19 | `POST /api/predictor/judge-profile` | `routers/court_predictor.py:1078-1087` | Same as #15 | Same fix |
| 20 | `POST /api/predictor/opponent-intel` | `routers/court_predictor.py:1248-1257` | Same as #15 | Same fix |
| 21 | `POST /api/predictor/confidence-check` | `routers/court_predictor.py:1548-1557` | Same as #15 | Same fix |
| 22 | `POST /corrections/capture` | `routers/corrections.py:283` | Optional `predmet_id` stored on `ai_corrections` with no ownership check (write-side pollution) | Verify ownership, null if foreign |
| 23 | `POST /api/smart-intake/entities/{entity_id}/correct` | `routers/smart_intake.py:522+` | **No ownership check at all** — any authenticated user could correct another user's `extracted_entities` row by id | 3-hop ownership chain check added: `extracted_entities.document_id → intake_documents.intake_job_id → intake_jobs.uploaded_by == uid` |
| 24 | `POST /api/predmeti/{predmet_id}/confirm-links` | `api.py:5320-5357` | `klijent_ids` from the request body linked to a predmet with no check they belong to the caller — a two-step cross-tenant PII leak once linked (client name/company surfaces via `get_predmet`) | Verify every id against `klijenti.eq(user_id,uid).in_(id,...)` before linking |
| 25 | `DELETE /api/zadaci/{zadatak_id}` (admin branch) | `routers/zadaci.py:360-375` | **Vertical privilege escalation**: any user can self-service-create their own `kancelarija` (becoming its admin), then delete **any task in any other firm** by guessing/observing a UUID — the admin branch deleted by primary key alone, no `kancelarija_id` scope | Admin branch now requires `.eq("kancelarija_id", firma["kancelarija_id"])` in addition to the primary key |
| 26 | `POST /api/workflow/pokreni` | `routers/workflow.py:212-222` | `workflow_templates` fetched by `template_id` alone — any firm could read (and start a workflow from) another firm's private template content | Added visibility filter: system templates (`kancelarija_id IS NULL`) OR the caller's own firm |
| 27 | `deduct_credit(p_user_id UUID)` RPC | `supabase_setup.sql:117-148` | `SECURITY DEFINER`, **explicitly granted to `authenticated`**, no ownership check in the function body — any logged-in user could drain any other user's credits to 0 directly via PostgREST, bypassing the FastAPI backend entirely | `migrations/102_lambda002_rpc_ownership_lockdown.sql`: `REVOKE ALL ... FROM PUBLIC/anon/authenticated`, `GRANT ... TO service_role` only (SQL migration — not yet applied to live Supabase, see report) |
| 28 | `set_user_pro(p_email, p_is_pro)` RPC | `migrations/061_fix_missing_profiles_columns.sql:66-74` | `SECURITY DEFINER`, **zero GRANT/REVOKE ever existed** (Postgres default = PUBLIC-executable) — any authenticated user could grant themselves free permanent PRO, or strip a victim's PRO status by email | Same migration 102 fix |
| 29 | `profiles` UPDATE (direct Supabase write, no FastAPI route — `static/vindex.js` uses the public anon key directly) | `supabase_setup.sql:38-41` | RLS `UPDATE` policy (`USING (auth.uid() = id)`) restricts which ROW a user may update, not which COLUMNS — no `WITH CHECK`, no column scope. Any authenticated user could set `is_pro`/`plan`/`trial_kraj` on their own row directly from the browser (`supabase.from('profiles').update({is_pro:true}).eq('id', myUid)`) for a free, permanent PRO upgrade — same monetary-impact shape as #28, a different door. **Missed by this sprint's own first-pass triage** despite being reported by the Database & RLS Auditor fork; caught on a manual re-review pass before commit. | `migrations/103_lambda002_profiles_column_lockdown.sql`: column-level `REVOKE UPDATE ... FROM authenticated/anon` + `GRANT UPDATE (full_name) ... TO authenticated` (the only column the frontend's own single `profiles` write path actually needs) — not yet applied to live Supabase |

## ARCHITECTURAL DEBT (found, not fixed this sprint)

| # | Endpoint / function | File:line | Bug | Debt entry |
|---|---|---|---|---|
| 30 | `POST /v1/webhook/clio` | `routers/integracije.py:275-314` | `vindex_user_id` taken directly from the attacker-controlled webhook body; only gated by a platform-wide shared HMAC secret, not a per-user credential | `LAMBDA-OWN-001` |
| 31 | `/api/dokument/pitanje`, `/analiza`, `/rokovi`, `/klasifikuj-sesija` | `routers/dokument.py` (full file) | Pinecone `session_id` has no `user_id` binding anywhere — any caller who obtains a valid session_id (unguessable 128-bit UUID, but no secondary check if ever leaked) gets full read access to that document's content/analysis/deadlines | Pre-existing `SEC-039` (High), re-confirmed not re-opened |

## NEEDS-DEEPER-LOOK, defense-in-depth-only, no live exploit path confirmed

| # | Function | File:line | Note |
|---|---|---|---|
| — | `deduct_n_credits`, `get_activity_averages`, `get_next_broj_fakture` RPCs | `migrations/smart_contract_analyses.sql`, `044_anomaly_detection.sql`, `003_billing.sql` | Same missing-`REVOKE`-from-`PUBLIC` pattern as #27/#28 but never had an explicit `GRANT TO authenticated` — locked down as defense-in-depth in the same migration 102, not because a live exploit was proven |
| — | `case_evolution.py` 5 event-consequence executors | `services/case_evolution.py:136,186,711,418,293` | Trust `event.user_id`/`predmet_id` from the durable outbox without re-verifying at dispatch time; not exploitable today (no ownership-reassignment code path exists in the repo), see `EVENT_OWNERSHIP_REPORT.md` |
| — | `intake.py:967` / `hearing_cc.py:198` nested `predmet_klijenti(klijenti(...))` joins | `routers/intake.py`, `routers/hearing_cc.py` | No explicit `klijenti.user_id` filter on the joined side; not independently exploitable now that every insert into `predmet_klijenti` in the repo verifies `klijent_id` ownership first (fixes #4/#5/#10/#24 above close the only planting paths found) — a defense-in-depth improvement, not a live gap |

## Coverage note

Full per-endpoint SAFE detail (260 rows, a-m sweep) and the n-z + `api.py` sweep's own SAFE rows were produced
by the auditor forks across every router file in the repo, including every file recently touched by Tau
005-008 and Lambda 001 (`case_commander.py`, `court_predictor.py`, `hearing_cc.py`, `cio.py`,
`digital_twin.py`, `client_portal.py`) — no regression was found in any of them. Background worker coverage
(13 functions), storage coverage (21 paths), and RLS/RPC coverage (197 policies + 19 functions) are detailed
in their own reports (`EVENT_OWNERSHIP_REPORT.md`, `STORAGE_SECURITY_REPORT.md`, `RLS_CERTIFICATION.md`).
