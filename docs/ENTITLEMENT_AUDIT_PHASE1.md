# Vindex AI — Entitlement System Refactor: Phase 1 Analysis

**Status: ANALYSIS ONLY. No code has been changed. This document is the required deliverable before Phase 2 (build) begins.**

Scope covered: all 104 files in `routers/`, `api.py` (5075 lines), `shared/deps.py`, `klijenti/` (router.py + permissions.py + audit.py), `routers/plans.py`, migrations 024/051/057/060-062, `static/vindex.js` (all 23 `currentUserIsPro` call sites), `index.html` pricing modal. Every finding below is cited to a file and line. Nothing is asserted without evidence.

---

## 1. Executive summary

There is **no single source of truth** for entitlement today. Five independent, partially-overlapping mechanisms coexist:

| # | Mechanism | Where | Status |
|---|---|---|---|
| A | `profiles.is_pro` + `Depends(require_pro)` | `shared/deps.py:537-546` | **Live** — the only mechanism that actually blocks access today |
| B | `Depends(require_credits)` + `_deduct_credit`/`_deduct_n_credits` | `shared/deps.py:409-534` | **Live** — usage-metered, separate from A |
| C | `routers/plans.py` — free/starter/pro/enterprise, `korisnik_plan`/`korisnik_usage` tables | `routers/plans.py` | **Dormant** — `plan_type` is never written anywhere in the codebase (confirmed by grep across every `.py` file); `ENFORCE_LIMITS` env var defaults `false` (`plans.py:9`); migration 051's own commit comment says a resource "trenutno se još ne dešava nigde u kodu" even after the schema fix. This system has existed since migration 024 and has never gone live. |
| D | `routers/enterprise.py` team/role endpoints | `enterprise.py:8-24` (self-documented) | **Half dead** — invite/role-change/remove target `firma_clanovi`, a table that was never migrated; would 500 today. The real team system is (E). |
| E | `routers/kancelarija.py` + `shared/rbac.py` | live tables `kancelarije`/`kancelarija_clanovi` | **Live but unmetered** — real multi-seat system, zero seat-limit enforcement (any user can invite unlimited members regardless of plan) |
| F | `klijenti/` RBAC (`Role` enum, field classification, audit log) | `klijenti/permissions.py`, `klijenti/router.py`, `klijenti/audit.py` | **Live, real, but plan-independent** — genuine field-level redaction and a reviewable per-client audit log exist and work, but are not gated by subscription at all, and role comes from a *third* source (`user_roles` table) unrelated to (E)'s `kancelarija_clanovi` |
| G | `sesije.py` concurrent-session limits | `sesije.py:65-69` | **Live**, reads `is_pro` directly (1 device free, 2 PRO, unlimited founder) |

**The bigger finding**: of the ~160 AI-cost-incurring or otherwise sensitive endpoints found across the whole project, only about 25 have *any* gating. The rest — including some of the most expensive single calls in the app (`/api/predmeti/{id}/workspace` fires an LLM on every case-open, `/api/predmeti/{id}/upload` fires 3 parallel GPT-4o calls per upload, `cio.py`'s daily portfolio scan, `case_dna.py`'s Case Genome extraction, all of `learning.py`/`matter_intel.py`/`billing.py`) — are reachable by any authenticated user today regardless of plan, with zero cost control.

**Two confirmed security-relevant gaps** (not tier-sorting questions — these are bugs, found during the audit, listed here for visibility, addressed in §6):
- `GET /api/portal/predmet` (`api.py:1894`) calls GPT-4o-mini with **no `get_current_user` at all** — gated only by a bearer token in a URL query string.
- `routers/praksa.py`: `praksa_search`, `praksa_ratio` (calls GPT-4o-mini), and `sudska_praksa_grupisano` have **no authentication whatsoever**, gated only by IP rate-limiting.

---

## 2. Complete inventory

### 2a. Digitalna imovina & Usklađenost (separate product — NOT a subscription tier)

| File | Mechanism | Disposition |
|---|---|---|
| `routers/web3.py` (11 endpoints) | `Depends(require_pro)` + 1-5 credit deduction | Replace `require_pro` with `PermissionService.require(FEATURE_DIGITAL_ASSETS)`, checked against `profiles.addons` — never against `subscription_type` |
| `routers/wallet_provenance.py` | `Depends(require_pro)`, no credit cost | Same replacement |
| `routers/source_of_funds.py` | `Depends(require_pro)` + 2 credits (founder-bypassed) | Same replacement |
| `routers/csv_import.py` | `Depends(require_pro)`, no AI cost | Same replacement |
| `profiles.digitalna_imovina_aktivirano`, `digitalna_imovina_standalone` (migrations 060, 062) | booleans | **Kept conceptually**, but superseded in representation by `profiles.addons ? "digital_assets"` per your spec (§3 of your message) — see open question in §6 |

### 2b. Mechanism A — `require_pro` (36 call sites, 9 files)

`csv_import.py`(1), `drafting.py`(6: playbook×3, nacrt, podnesak, nacrti_checklist), `export.py`(2: API key create/list), `hearing_cc.py`(2), `interni.py`(3), `source_of_funds.py`(1), `wallet_provenance.py`(1), `web3.py`(11), `strategija.py`(9, combined with credit deduction on every endpoint).

**Disposition**: every one of these becomes `PermissionService.require(FEATURE_X)` where `FEATURE_X` maps to `professional` minimum (all are drafting/strategy/hearing-prep features, matching your "Professional = ~90% of value" philosophy). None belong in Basic per your explicit exclusion list.

### 2c. Mechanism B — credit/usage metering (separate axis from tier)

Real, working credit deduction exists in: `copilot.py`, `court_predictor.py` (2-3 credits/call, inconsistent founder-bypass — see §5), `digital_twin.py` (same inconsistency), `dokument.py`, `drafting.py`, `evidence_graph.py` (same inconsistency), `export.py`, `hearing_cc.py`, `multi_agent.py`, `profitabilnost.py` (deducts *after* generating, no upfront check), `strategija.py`, `strategy_simulator.py` (credit-only, deliberately *not* `require_pro`-gated), `web3.py`, `wallet_provenance.py`'s callers.

**Disposition**: this becomes the `UsageService` you specified in §4 — kept as a genuinely separate axis from `PermissionService`, exactly as you designed it. `PermissionService.require(FEATURE_X)` answers "can this account reach this feature at all," `UsageService.consume(FEATURE_X, credits=N)` answers "do they still have budget this month."

### 2d. Mechanism C — `routers/plans.py` (dormant)

**Disposition: DELETE.** Confirmed dead — `korisnik_plan.plan_type` has zero writers anywhere in the codebase; `check_feature_access()` has zero callers anywhere in the codebase; `ENFORCE_LIMITS` defaults false. Its two live call sites (`strategija.py`, `dokument.py` calling `enforce_and_increment` for tracking-only counters) get migrated to the new `UsageService`. The `korisnik_plan`/`korisnik_usage`/`plan_limits` tables become orphaned — flagged for a follow-up migration to drop them once the new system is confirmed stable (not dropped immediately, per your migration-safety requirement in §9).

### 2e. Mechanism D — `routers/enterprise.py` (half dead)

**Disposition**: delete the 4 endpoints that target the never-migrated `firma_clanovi` table (`tim/pozovi`, `tim/clanovi`, `tim/{user_id}` DELETE, `tim/uloge`) — they already 500 today, removing them changes nothing for any real user. Keep `statistike`, `kapacitet`, `predmet/delegiraj`, `predmet/delegiranja` (these work, read from the real system (E)) but route them through the new Enterprise-tier `PermissionService` check, since firm-level delegation/stats are exactly the kind of feature that belongs at Enterprise per your spec.

### 2f. Mechanism E — `routers/kancelarija.py` (real, unmetered)

**Disposition**: this becomes the technical backbone of the ENTERPRISE tier's "3 korisnika uključena + 49€/dodatni korisnik" requirement. Today `pozovi_clana` (`kancelarija.py:238`) has **no seat-limit check at all** — this needs new code, not a rename: read `subscription_type` + count active `kancelarija_clanovi` rows + compare against included-seats(3)+purchased-extra-seats before allowing an invite. This is a genuinely new capability, not a relabeling.

### 2g. Mechanism F — `klijenti/` RBAC (real, plan-independent)

**Disposition**: keep as-is functionally (it's good, working infrastructure — real field-redaction, real per-client audit log reviewable by PARTNER role). Two changes: (1) gate the module's existence behind at least `basic` tier (it's currently reachable by literally anyone with a valid token, which is fine since Basic includes "Klijenti" per your spec — so likely no change needed here beyond confirming it), (2) the Enterprise tier's "Audit" bullet can now honestly point at real infrastructure — `GET /klijenti/{id}/audit` — rather than something to build from scratch, once/if you want to widen it (see gaps below).

**Bugs found in this module** (not tier-sorting, just bugs — flagged per your "svaka funkcija mora biti mapirana" + honesty requirement, will be noted, not silently fixed without your awareness):
- Two independent role-resolution implementations exist; only one (`router.py:45-55`, keyed off `user_roles` table) is actually used. `permissions.py`'s `make_role_dependency`/`require_role`/`require_action` are unused dead code.
- Role source (`user_roles` table) is **completely disconnected** from the Kancelarija-team role (`kancelarija_clanovi.uloga`) — a user's permissions on client records and their permissions on firm/team features come from two unrelated tables today.
- Default role on any lookup miss is `ADVOKAT` (mid-privilege), not the lowest-privilege role — silent-fail-open, not silent-fail-closed.
- `GET /klijenti/{id}/relationship` returns full documents/communications with zero field-redaction and zero audit logging — bypasses both protections the rest of the module has.
- `POST /klijenti` (create) and `PUT /klijenti/{id}` (edit) never call `can_perform()` despite `ACTION_MIN_ROLE` defining minimum roles for `create_client`/presumably edit — the role check exists in data but isn't wired to these two endpoints.

### 2h. Founder/admin gates (not tier-related — out of scope for the tier refactor, listed for completeness)

`admin_dashboard.py`, `analytics.py`, `apr.py`, `auto_discovery.py`, `batch_ingest.py`, `email_notif.py`, `law_upload.py`, `portal_monitoring.py`, `product_intelligence.py`, `proof.py`, `sms.py`, `status_page.py`, `viber.py`, `waitlist.py`, `whatsapp_notif.py`, `workflow.py`, `zakon_monitoring.py` — all use `_is_founder`/`FOUNDER_EMAILS` (or a locally-redeclared duplicate of the same set — found separately declared in `sms.py`, `viber.py`, `status_page.py` instead of imported from `shared/deps.py`) for admin/cron access. **Disposition: keep as-is, consolidate the duplicated `FOUNDER_EMAILS` declarations into the one in `shared/deps.py` while touching these files anyway.** This is founder-vs-everyone, orthogonal to the customer-facing tier system.

### 2i. Features with ZERO gating today (the largest category — ~65 files)

Full list, grouped by what tier they should land in per your stated philosophy (Basic = named 8 things only; everything AI-substantial = Professional; multi-user/admin = Enterprise):

**→ PROFESSIONAL** (AI-substantial, not in your Basic list): `case_commander.py`, `case_dna.py`, `case_intelligence.py`, `case_pipeline.py`, `cio.py`, `client_twin.py`, `confidence_audit.py`, `conflict_check.py`, `corrections.py`, `cross_doc.py`, `decision_replay.py`, `doc_templates.py`, `evidence.py`, `firm_memory.py`, `health_index.py`, `intake.py` (AI extraction parts), `knowledge_base.py`, `knowledge_graph.py`, `knowledge_hygiene.py`, `knowledge_transfer.py`, `learning.py`, `matter_intel.py`, `memory_graph.py`, `morning_briefing.py`, `oblasti.py`, `outcome_intel.py`, `precedenti.py`, `style_checker.py`, `vindex_memory.py`, `voice.py`, `zadaci.py`'s `/ai-analiziraj`, `zastarelost.py`'s Guardian, `zakon_monitoring.py`'s `impact_analiza`, `region.py`'s `/ai-savet`, `api.py`'s `/api/procena`, `/api/predmeti/{id}/upload`, `/api/predmeti/{id}/ai-preporuka`, `/api/predmeti/{id}/workspace`, `klijenti/intake-wizard`.

**→ BASIC** (matches your explicit named list — CRUD/non-AI or the one named AI item): `api.py`'s Predmeti CRUD (create/list/get/patch/notes/history), `klijenti/router.py`'s core CRUD (create/list/get/edit/archive — the *feature*, not the AI intake wizard), `billing.py` + `billing_reports.py` (Finansije), `kalendar.py`/`rocista.py`/`rokovi_lanac.py` (Rokovi), `api.py`'s `/api/pitanje` + `/api/pitanje/stream` (AI pravna pitanja — already correctly `require_credits`-gated, just needs a Basic-tier credit allowance), case-law search in `praksa.py` (Sudska praksa — once the auth bug in §1 is fixed).

**→ ENTERPRISE**: `routers/kancelarija.py` (seats), the working half of `routers/enterprise.py` (delegation/stats), `klijenti/{id}/audit` (already PARTNER-only, naturally Enterprise-flavored), any future cross-firm reporting.

**→ Needs your confirmation, not obvious**: `benchmarking.py` (anonymous, opt-in, no real cost — arguably fine to leave open to all tiers), `dashboard.py`'s command_center (aggregation, no AI, arguably Basic), `notifications.py`, `portfolio.py`, `search.py`, `inbox.py`, `komentari.py`, `saradnja.py`, `client_portal.py` (client-facing, not firm-facing — token-gated already, probably stays tier-independent since it's the *client's* view, not the lawyer's), `data_export.py`/GDPR export (probably must stay available to everyone regardless of tier for legal-compliance reasons — GDPR right-to-export shouldn't be paywalled). **I have not assigned these a tier because your spec doesn't give me enough signal to be confident — flagging per your explicit instruction rather than guessing.**

---

## 3. Files changed in Phase 1 (this analysis)

- `docs/ENTITLEMENT_AUDIT_PHASE1.md` — this file (new)

**No other files touched.** Nothing else changed, per your instruction.

---

## 4. What's clean / doesn't need to change

- `shared/deps.py`'s credit-deduction primitives (`_deduct_credit`, `_deduct_n_credits`, atomic RPC-based, race-condition-safe) — these become `UsageService`'s implementation, not replaced.
- `klijenti/`'s field-classification and audit-log *mechanisms* (not their gating, which is absent) — genuinely good, keep the design.
- `api.py`'s `/api/pitanje` + `/api/pitanje/stream` — correctly implemented reference pattern for what `require_credits` should look like everywhere.

---

## 5. Inconsistencies found (bugs, not architecture questions — will be fixed as a byproduct of unifying everything through PermissionService/UsageService in Phase 2, listed here so you're aware before I touch them)

1. Founder credit-bypass is inconsistent: `court_predictor.py`'s `argument_reputation`/`judge_profile`/`opponent_intel`, `digital_twin.py`'s both endpoints, and `evidence_graph.py`'s `generisi_graf` exempt founders from the *pre-check* but still run the unconditional `_deduct_n_credits` call — founders get charged anyway on these five.
2. `export.py`: creating/listing API keys requires PRO; revoking one does not.
3. `doc_templates.py /generisi` (free) functionally duplicates `drafting.py /api/nacrt` (PRO+credit-gated) — same capability, two different monetization outcomes depending on which URL is called.
4. `FOUNDER_EMAILS` is independently redeclared (not imported) in `sms.py`, `viber.py`, `status_page.py`.
5. `strategy_simulator.py` does credit-only gating without `require_pro`, while `strategija.py` (adjacent, similar feature) does both — inconsistent pattern for materially similar features.

---

## 6. Decisions I need from you before Phase 2 starts

I can sort essentially everything above with confidence — your stated philosophy is clear enough. Three things are genuine judgment calls that change the shape of the build, not things I should silently decide:

**(1) Grandfathering for existing non-PRO users.** Your §10 says existing `is_pro=true` → `professional` automatically. Your §12 says no existing user should lose access to functions they already have. But today almost every AI feature (Case DNA, CIO, billing, Client Twin, Learning, etc.) is open to **every** authenticated user, PRO or not, because it was never gated. A literal reading of §12 means every existing account — not just PRO ones — would need to be grandfathered to at least Professional to avoid a regression, which would mean the new tier split only bites for *new* signups going forward. Is that the intent, or do you want existing non-PRO users' access reset down to Basic on cutover (a real, visible loss of functionality for them, contradicting a literal read of §12)?

**(2) The two unauthenticated cost-incurring endpoints** (`api.py:1894` `/api/portal/predmet`, and `praksa.py`'s `praksa_search`/`praksa_ratio`/`sudska_praksa_grupisano`). These are security bugs independent of the tier system — I intend to fix them (add proper auth) as part of Phase 2 regardless of tier assignment, unless you tell me otherwise, since leaving them as-is is a cost-abuse vector no matter how the entitlement system is designed.

**(3) Kancelarija seat enforcement is new code, not a rename.** Building real "3 seats included, 49€ per additional seat, block invite past that" logic is a genuine feature addition (nothing enforces seat count today). Confirming you want this built now as part of this refactor (I believe yes, per your explicit Enterprise spec, but it's meaningfully more work than relabeling an existing check, so flagging explicitly).

Everything else in this document I'm confident enough to proceed on without further questions. Waiting on (1)-(3) before starting Phase 2 (PermissionService, UsageService, Feature Matrix constants, migrations).
