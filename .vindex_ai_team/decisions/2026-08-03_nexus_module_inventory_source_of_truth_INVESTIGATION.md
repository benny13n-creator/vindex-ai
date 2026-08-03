# Project Nexus — Module Inventory & Source-of-Truth Investigation

Read-only. All claims grounded in direct file reads this session; no code changed.

---

## PART A — Module inventory

### A1. Background tasks / cron jobs

| Job | Trigger | Reads | Writes | Failure handling |
|---|---|---|---|---|
| `IntakeWorker` (`shared/intake_worker.py`) | In-process loop, started at `api.py:824` FastAPI startup | `intake_jobs` (claim via RPC) | job status, `intake_documents`, `extracted_entities` | Per-job try/except, retry/backoff, dead-letter after max_attempts (confirmed prior session) |
| Event Bus `DispatchLoop` (`services/event_bus.py`) | Same startup hook, `api.py:825` | `events` table (durable outbox) | dispatches to registered handlers, marks `dispatched_at` | Per-row try/except, `dispatch_attempts`/`last_error` tracked, never blocks the batch |
| **`POST /api/cron/daily`** (`api.py:1502`) | **External** — Render.com cron, once/day 07:00 UTC, protected by `X-Cron-Secret` (fails closed if secret unset) | `chain_anchors` (idempotency: skips if run <60min ago, alerts if stale >36h) | 10 sub-modules, see below | Each of the 10 modules independently try/except + `asyncio.wait_for` timeout; one module's failure never blocks the rest |

`cron_daily`'s 10 modules, in order: (1) Workflow escalations, (2) Zakon monitoring (Mondays only), (3)
Memory cleanup (`memory_entries`), (4) Portal.sud.rs monitoring, (5) **Workflow escalations again**,
(6) Email reminders, (7) Onboarding emails, (8) Weekly summary (Mondays only), (9) SEC-002 retention
cleanup, (10) Background action agents (`workers/background_agents.py`).

**Finding**: Module 1 (`api.py:1571-1575`) and Module 5 (`api.py:1675-1690`) both call the exact same
`routers.workflow._check_escalations()` — confirmed via direct read, not a false-positive from similar
naming. Traced the function itself (`routers/workflow.py:519-555`): it flips each escalated row's
`status` from `"aktivan"` to `"eskaliran"` immediately after notifying, and its own query filters on
`.eq("status", "aktivan")` — so the second call structurally finds zero rows left to escalate and sends
no duplicate notifications. **Not a live notification-spam bug** (self-healing via the status
transition), but a confirmed, real case of dead/duplicate execution: every single daily cron run
performs one entirely redundant DB query + function call for no effect, and the identical "Modul N:
Workflow eskalacije" comment on both blocks suggests a copy-paste artifact from prior reorganization
that was never cleaned up.

No other background jobs found beyond these three plus the `workers/background_agents.py` module
(fired inside cron_daily's Module 10, not independently scheduled).

### A2. Task Engine as an intelligence node — confirmed a 5th independent reasoning path

`POST /api/zadaci/ai-analiziraj/{predmet_id}` (`routers/zadaci.py:491-664`) is a real, reachable,
GPT-based (`gpt-4o-mini`) endpoint that independently checks for missing power-of-attorney, missing
key documents, unbilled amounts >50,000 RSD, and >14-day inactivity, then creates real `zadaci` (task)
rows from the model's JSON output (with a heuristic non-AI fallback if the GPT call fails). **This is
architecturally separate from and does not call `services/risk_engine.py::identify_case_problems`** —
the function explicitly documented elsewhere in this codebase as *"jedini algoritam za sledeću akciju u
celoj platformi"* (Core Consolidation Sec 1.2, "the only next-action algorithm platform-wide"). Unlike
Copilot's `_handle_analiza_predmeta` (a dead-end chat answer, already found and left as a documented
gap by a prior mission), this one **writes persisted, actionable database rows** based on independent,
non-deterministic GPT judgment about missing documents — using its own ad hoc heuristic (checking
`predmet_dokumenti.naziv_fajla` existence generally) rather than the canonical, deterministic
`EXPECTED_DOCS`-based comparison `identify_case_problems` already performs. This is the most
consequential Phase-5-relevant finding in this investigation: a real, reachable, side-effect-producing
duplicate of the platform's declared "only algorithm."

### A3. Audit Trail — `decision_log` and `audit_immutable` are correctly complementary, not duplicates

- `shared/audit_immutable.py`: hash-chained, tamper-evident, security/compliance-focused (GDPR erasure,
  document uploads, admin actions) — already known from a prior mission's audit (~20% of its defined
  action taxonomy actually fires).
- `services/decision_log.py`: a **different** table (`decision_log`, migration 036), explicitly framed
  in its own header as *"Core infrastruktura za Legal Operating Memory — organizaciona inteligencija"*
  — records WHY a lawyer made a choice (with alternatives considered), read back by the AI Briefing as
  one of its 8 data sources. Distinct `DecisionType` taxonomy (strategija_odabrana, dokument_prilozen,
  rok_dodat, podnesak_generisan, argument_odabran, nagodba_razmatrana, veštačenje_zatraženo, etc.) —
  none overlapping with `audit_immutable`'s security-action taxonomy.

**Verdict: correctly layered, not a duplicate audit system.** One proves compliance/security events
happened (tamper-evident); the other captures institutional reasoning for future AI context. No
refactor needed.

### A4. Storage systems

| System | Purpose | Evidence |
|---|---|---|
| Supabase Postgres | Primary relational store — every table referenced throughout this engagement | — |
| Supabase Storage | Encrypted file blobs, 2 confirmed buckets: `"intake-dokumenti"` (Smart Intake uploads) and `"portal-uploads"` (client portal uploads) | `grep` for `storage.from_(` across `routers/`, `shared/`, `uploaded_doc/`, `api.py` |
| Pinecone | Vector embeddings for semantic search/RAG | Namespace strategy already confirmed by a prior mission (`rag_owner_namespace`, per-firm-or-user) — not re-verified in depth this pass |
| Redis (Upstash) | **Narrow-purpose only**: rate-limiting counters (`shared/rate.py`), fail-open to in-memory if Redis errors | Confirmed via `grep` — no general caching layer, no session store, no intelligence-data cache found anywhere else in the repo |

No other storage system (no separate cache DB, no local disk persistence for intelligence data) found.

---

## PART B — Source-of-Truth duplication audit

### B1. `predmet_dokazi` (Evidence Vault) vs. Case Genome — correctly layered, NOT a duplicate

`routers/case_dna.py`'s own comments confirm the current, intended architecture directly:
*"predmet_dokazi... sada TECE U Genome kao kontekst"* (line 11, "now FLOWS INTO Genome as context") and
*"Evidence Vault (predmet_dokazi) vise ne sme [biti izolovani vlasnik istine]"* (line 168, "Evidence
Vault may no longer be an isolated owner of truth"). Confirmed still true in the current code: Genome
reads `predmet_dokazi` (lines 175, 480, 487) explicitly as an *input* to its own synthesis, not a
competing fact store. **No newer code across tonight's many missions reintroduced a duplicate
extraction path here** — verified clean.

### B2. Case-strength / score duplication — TWO genuine violations found, one confirmed clean

- **`snaga_predmeta_procent`** (Case Genome, `shared/genome_validator.py::compute_snaga_score`,
  deterministic) vs. **`health_score`** (Matter Intelligence, `services/risk_engine.py`, deterministic,
  different inputs — evidence strength + missing docs + critical hearings) — confirmed **genuinely
  different concepts**, not an accidental duplicate: one measures case merit, the other measures
  process/administrative risk. Correctly distinct.

- **`routers/ccc.py::_compute_health`** — a **confirmed real duplicate**, not a distinct concept. Its
  own docstring states *"Isti algoritam kao matter_intel.py"* ("same algorithm as matter_intel.py") —
  it reimplements Matter Intelligence's exact `rizik_score`/`health_score` formula locally instead of
  calling `services/risk_engine.py::calculate_procesni_rizik`, with one silent divergence: CCC
  hardcodes `nedostajuci_count = 0` ("CCC ne računa nedostajuće ovde — konzervativna nula"), meaning
  its `health_score` can and will differ from Matter Intelligence's real one for any case with actual
  missing documents — **under the identical field name `"health_score"`**. Confirmed reachable (1
  frontend reference in `vindex.js` to `/api/ccc/`), not dead code. This is the clearest Phase-5
  violation found: two live endpoints can return two different numbers for the same declared concept,
  for the same case, depending which one a consumer calls.

- **Copilot's `verovatnoca_uspeha`** (now enriched with Genome context per a prior mission tonight) and
  **`routers/digital_twin.py`'s `nova_verovatnoca_uspeha`** — a third, independently-computed
  "probability of success" number, confirmed to exist (`routers/digital_twin.py:104,331,359`) but NOT
  deeply traced this pass (time-boxed) — flagged as needing the same scrutiny as `ccc.py` received, not
  confirmed clean or dirty.

### B3. Deadline facts — `predmet_hronologija` vs. `rokovi_lanac.py` — correctly layered, NOT a duplicate

`routers/rokovi_lanac.py`'s own header confirms its role: computes a **chain of derived procedural
deadlines** from one trigger-act date, then **writes those derived deadlines AS ROWS into
`predmet_hronologija`** (confirmed: "Opciono upisuje rokove direktno u predmet_hronologija"). It is a
writer/populator of the canonical timeline table, not a second, competing table or source of truth.
Confirmed clean — no refactor needed.

---

## Summary table

| # | Finding | Category | Severity |
|---|---|---|---|
| A1 | `cron_daily` calls `_check_escalations()` twice (Modules 1 and 5) | Duplicate execution (self-healing, not notification-spam) | Low-Medium — wasted work, confusing code, not user-facing |
| A2 | `zadaci.py::ai_analiziraj_predmet` is a 5th independent, GPT-based, side-effect-producing "missing item" detector, bypassing the platform's declared sole deterministic algorithm | **Duplicated reasoning, real side effects** | **High** — creates real tasks from non-deterministic judgment where a canonical, deterministic source already exists |
| A3 | `decision_log` vs `audit_immutable` | Correctly layered | None — not a defect |
| B1 | `predmet_dokazi` vs Case Genome | Correctly layered | None — not a defect |
| B2a | `snaga_predmeta_procent` vs `health_score` | Correctly distinct concepts | None — not a defect |
| B2b | `routers/ccc.py`'s own `health_score` reimplementation | **Confirmed duplicate under identical field name** | **High** — two live endpoints, two possible answers, same declared concept |
| B2c | `digital_twin.py`'s `nova_verovatnoca_uspeha` | Uncertain — not deeply traced | Needs follow-up, not confirmed either way |
| B3 | `predmet_hronologija` vs `rokovi_lanac.py` | Correctly layered | None — not a defect |
