# Beta Lockdown — Tenant Isolation / Audit / Search / Refresh Investigation

Read-only. All claims grounded in direct file reads; no code changed.

---

## 1. Tenant isolation spot-check

**CRITICAL FINDING — real, live, exploitable cross-tenant data leak (IDOR):**

`GET /api/zadaci/predmet/{predmet_id}` (`routers/zadaci.py:380-402`, `zadaci_za_predmet`) has **zero
ownership verification**. It takes `predmet_id` directly from the URL and returns `select("*")` on
`zadaci` filtered ONLY by `.eq("predmet_id", predmet_id)` (line 393-395) — no `.eq("user_id", ...)`
(the table has none), no `.eq("dodeljen_uid", uid)`/`.eq("kreirao_uid", uid)`, no `.eq("kancelarija_id",
...)`, and critically **no prior check that `predmet_id` even belongs to the calling user**. Any
authenticated user who obtains another firm's `predmet_id` (a leaked URL, a support ticket, a shared
screenshot — UUIDs aren't brute-forceable, but they do leak through normal channels) can call this
endpoint and receive that firm's complete task list: names, descriptions, deadlines, status,
`dodeljen_uid`.

This is a genuine outlier, not a systemic issue: every comparable endpoint in the SAME file does check
ownership first — e.g. `routers/zadaci.py:495-503` (2 lines above a second, correctly-scoped
`predmet_id`-only task query at line 527-532) does `.eq("id", predmet_id).eq("user_id", uid)` on
`predmeti` before touching `zadaci`. `zadaci_za_predmet` is the one place this check was skipped.

**Recommended fix** (not implemented — read-only investigation): add the same
`.eq("id", predmet_id).eq("user_id", uid)` ownership check against `predmeti` before running the
`zadaci` query, mirroring line 495-503 exactly. Small, safe, matches an established in-file pattern —
a strong candidate for this mission's "smallest safe change" bar, and should be the highest-priority
security fix of this entire mission given it's live and exploitable today, not theoretical.

### Everything else checked: correctly scoped, no other issues found

- **`routers/search.py`** — all 7 branches re-confirmed: `predmeti`/`klijenti`/`dokumenti`/`billing`/
  `hronologija`/`beleske` use `.eq("user_id", uid)` (lines 42, 62, 97, 146, 165, and one more — grep
  confirmed 5 distinct `user_id` hits across these); `zadaci` correctly uses
  `.or_("kreirao_uid.eq.{uid},dodeljen_uid.eq.{uid}")` (`:126`), a documented, deliberate strict subset
  of its RLS policy's full firm-wide grant. No issue.
- **`routers/case_dna.py`** — every entry point (`_do_genome_refresh`, `refresh_case_dna`,
  `get_case_dna`, `case_dna_history`, `compare` endpoint) re-verifies `predmeti.eq("id",
  predmet_id).eq("user_id", uid)` before touching child tables (`predmet_dokumenti`,
  `predmet_dokazi`, `predmet_hronologija`, `predmet_genome_history`) that are then queried by
  `predmet_id` alone. This is the standard, defensible "verify parent once, trust non-guessable
  child-id scoping" pattern used consistently across this codebase — not a leak, PROVIDED the
  ownership check always runs first on every path. One structural soft spot: `_do_genome_refresh`
  (`case_dna.py` ~line 653) doesn't hard-return if its own `.eq("user_id", uid)` check on `predmeti`
  finds no match (it falls through with `stari_genome = {}`) and would still fetch/analyze
  `predmet_dokumenti` by `predmet_id` alone regardless. **Not exploitable via any current call site**
  (every caller — Smart Intake finalize, `api.py`'s upload endpoint, `rocista.py` — derives
  `predmet_id` from a case the SAME request already validated), and it's a background task with no
  HTTP response to leak into — but it's a defense-in-depth gap worth hardening (an early `return` on
  ownership-check failure) rather than a live vulnerability. Documented for completeness, not ranked
  alongside the `zadaci` IDOR above.
- **`routers/evidence.py`** — `klasifikuj_i_sacuvaj`, `get_evidence_summary`, `create_dokaz`,
  `delete_dokaz`, and the source-preview endpoint all check `predmeti.eq("id",
  predmet_id).eq("user_id", uid)` before reading/writing `predmet_dokumenti`/`predmet_dokazi`; the
  delete endpoint additionally scopes the delete itself by `.eq("id", dokaz_id).eq("user_id", uid)`
  directly (`:322`) — tightest possible scoping. No issue.
- **`routers/case_intelligence.py`** (`_gather_case_data`, wired tonight as IF-002) — all 8 parallel/
  sequential queries scoped: `predmeti` (`.eq("id",...).eq("user_id",...)`), `lessons_learned`,
  `firm_dna`, `case_patterns`, `proactive_alerts` (both `user_id` AND `predmet_id`), `decision_log`
  (both), `client_twin_profili` (`.eq("klijent_id",...).eq("user_id",...)`), `knowledge_profiles`. No
  issue — this genuinely new capability was wired correctly.
- **`routers/gdpr.py`** — both `gdpr_export` and `gdpr_delete_account` derive `uid`/`email` exclusively
  from `Depends(get_current_user)` (JWT-derived); no request body/path/query parameter anywhere
  accepts a client-supplied user identifier. Structurally impossible to target another user's data. No
  issue.
- **`routers/predmeti_close.py`** — `bulk_promena_statusa` (archiving/status changes) double-scopes:
  the ownership-verification SELECT and the actual UPDATE both carry `.eq("user_id",
  uid).in_("id", ids)` (`:317-322`, `:334-339`). An attacker-supplied ID for another user's case is
  silently excluded from `existing`, never modified. No issue.
- **`api.py:4133`'s upload endpoint** (fixed for images this mission) — ownership check
  (`.eq("id", predmet_id).eq("user_id", user.id).single()`, `:4163`) runs first; every subsequent
  insert into `predmet_dokumenti`/`predmet_hronologija`/`predmet_istorija` explicitly carries
  `"user_id": user.id` on the row itself. No issue.

## 2. Audit log integration coverage

`shared/audit_immutable.py::AUDITABLE_ACTIONS` defines 24 action types. Grepping every `log_action(`/
`log_action_sync(` call site across the repo (excluding tests) found these are **actually triggered**:

| Action | Triggered from | Note |
|---|---|---|
| `rate_limit_exceeded` | `api.py:1045` | |
| `predmet_create` | `api.py:3275` (`POST /api/predmeti` only) | **NOT logged** from `routers/intake.py`'s `intake_kreiraj` (the primary AI-assisted case-creation endpoint) or from Smart Intake's finalize — case creation via the CRM Intake Wizard, the path a lawyer actually uses per this engagement's Lawyer Day simulation, is invisible to audit. |
| `dokument_upload` | `api.py:4322` (the reachable per-case upload path) | **NOT logged** from Smart Intake's finalize (moot — unreachable anyway). |
| `genome_refresh` | `services/event_bus.py:157`, via the `GENOME_UPDATED` event | Fires for every Genome refresh regardless of trigger path (Smart Intake, `api.py` upload, `rocista.py`) — this one is fully, consistently audited. |
| `AGENT_AUTONOMOUS_EXECUTION` | `workers/background_agents.py:181` | |
| `reasoning_graph_generated` | `routers/legal_reasoning.py:38` | |
| `suspicious_access` | `security/anomaly_detection.py:253` | |
| `login_failed`-adjacent | `shared/deps.py:261` | |
| (misc) | `routers/strategy_simulator.py:329,442` | **This router is confirmed dead code** (Operation Invisible Features census) — its audit calls never fire in practice. |

**Never triggered anywhere in production code** despite being defined in `AUDITABLE_ACTIONS`:
`predmet_update`, `predmet_delete`, `predmet_view`, `dokument_delete`, `dokument_view`,
`dokument_download`, `klijent_create`, `klijent_delete`, `login_success`, `logout`,
`password_change`, `2fa_enable`, `2fa_disable`, `admin_access`, `user_role_change`,
`firm_settings_change`, `ai_analiza_complete`, `ai_kompletna_analiza_complete`,
`injection_attempt_blocked`, `api_key_rotation`. Roughly 80% of the defined audit taxonomy is
aspirational, not active.

**Important correction to Lawyer Day's finding**: that report said "no lawyer-facing audit log
viewer exists" — true for an account-wide activity log, but **incomplete**. `routers/
intelligence_timeline.py` (`GET /api/predmeti/{id}/intelligence-timeline`, confirmed called from
`vindex.js:18008`) aggregates 6 sources into a per-case "life of the case" view, and one of those
sources IS `audit_immutable` — its own header comment explicitly says it was extended to include
audit entries as "the one remaining 'history' table not yet part of this flow." So **case-scoped**
audit visibility (for whichever actions are actually logged: `predmet_create` when created via `POST
/api/predmeti`, `dokument_upload`, `genome_refresh`) DOES reach a lawyer today, via the case timeline,
not a dedicated audit page. The real gap is narrower than previously stated: (a) most action types are
never logged at all, and (b) there's no cross-case/account-wide view — not "no audit visibility
exists."

## 3. Search integration completeness

- **Evidence Vault's richer fields** (`predmet_dokazi.kljucne_cinjenice`/`pravni_elementi`) — confirmed
  NOT in `routers/search.py`'s type list (`_VALID_VRSTE` has no `dokazi`/`evidence` entry). Only
  `predmet_dokumenti.tip_dokaza` (a coarser field on a different table) is searchable. Real, minor gap.
- **Case Genome content** (`predmeti.case_dna` JSON) — confirmed NOT searchable. A lawyer cannot search
  for a legal theory, weak point, or strategy Genome identified. Real, minor gap.
- **Billing entries** — confirmed ALREADY searchable (`_search_billing`, `routers/search.py:142-149`,
  `.eq("user_id", uid)`, correctly scoped) — this was already live before tonight, not a gap.
- **Drafted documents (`nacrti`/`podnesak`)** — more nuanced than "not searchable, full stop." A real,
  well-designed persistence pipeline exists: every generated draft is immediately staged (fire-and-
  forget, `routers/drafting.py::_stage_draft_for_review`, `:199-228`) into `staging_memory` with an
  automatic confidence score; `POST /api/staging/{id}/approve` then promotes it into
  `predmet_dokumenti` with `tekst_sadrzaj` populated (`drafting.py:300-309`) — at which point it
  becomes searchable via the EXISTING `_search_dokumenti` branch, with zero additional search-side
  work needed. **The gap is that the entire staging/approval workflow is invisible from the frontend**:
  grepped `vindex.js` for "staging" — zero matches, anywhere. A lawyer generates and exports a draft
  (confirmed reachable, DOCX export works) but the review-and-commit-to-the-case-record step never
  happens, so the draft never enters the permanent case file and never becomes searchable. This is a
  new, well-evidenced hidden-feature finding, same shape as this engagement's other findings: real,
  working backend, zero frontend caller.

## 4. "Survives refresh/reload" — code-level proxy

- **Smart Intake job state**: `intake_jobs` (Postgres-backed queue table, per this engagement's
  established architecture knowledge) — genuinely DB-backed, survives reload structurally (moot in
  practice since the UI to reach it doesn't exist, but the persistence itself is sound).
- **In-progress draft text**: confirmed DB-backed, not in-memory-only. `_stage_draft_for_review`
  (`drafting.py:199`) fires automatically right after generation, before any lawyer action — the full
  draft text and an AI-computed confidence score are in `staging_memory` immediately. A page reload
  would not lose the generated text (though, per Finding #3, there's no UI to go find it again either).
- **AI Workspace mode/sub-panel selection**: confirmed **in-memory only**. `aiwsSetMode()`
  (`vindex.js:2323-2371`) sets a plain JS variable (`_aiwsMode = mode`) and toggles DOM visibility —
  no `localStorage` write, no URL hash/query-param update anywhere in the function. A lawyer deep in
  the Litigation Intelligence or Strategy pane who reloads the page (or whose session refreshes) is
  returned to whatever the default initial view is, not back to where they were. Real, minor UX
  finding — not a data-loss risk (nothing typed into those panes is lost per the point above, for
  drafts specifically), but a navigation-state loss.

---

## Summary table

| # | Area | Verdict |
|---|---|---|
| 1a | `zadaci_za_predmet` tenant isolation | **CRITICAL — real, live IDOR, no ownership check at all** |
| 1b | Every other checked endpoint (8 files) | Correctly scoped; one defense-in-depth soft spot noted (Genome background-task early-return), not currently exploitable |
| 2 | Audit coverage | ~20% of defined actions actually fire; case creation via the real-world path (`intake_kreiraj`) is unaudited; case-scoped audit visibility DOES exist via the Intelligence Timeline (corrects Lawyer Day's overly broad claim) |
| 3 | Search completeness | Evidence Vault rich fields and Genome content not searchable (minor); drafts have a real, working search-integration PATH that's unreachable because the staging/approval UI doesn't exist (new hidden-feature finding) |
| 4 | Refresh/reload survival | Draft text is DB-backed (safe); AIWS mode selection is in-memory only (lost on reload, minor) |
