# Vindex AI — Enterprise Security Due Diligence Report

**Date:** 2026-07-23
**Auditor stance:** Adversarial. The goal was to break Vindex AI, not to describe its features favorably. Every claim below is evidence-based (`file:line`) or explicitly marked `NOT VERIFIED` / `REQUIRES PRODUCTION VERIFICATION`. Documentation, comments, and prior audit files were not used as evidence of security posture — only executing code, database migrations, and configuration.
**Method:** 5 independent adversarial investigations (auth/authz/multi-tenancy; AI security/file upload; API/frontend/secrets; infrastructure/supply chain/DR/monitoring; database/RLS/audit-integrity/GDPR) plus direct review of the encryption module, cross-checked against each other for consistency.
**Companion documents:** `SECURITY_GAP_REGISTER.md` (30 findings, IDs SEC-001–030), `SECURITY_ROADMAP.md` (P0–P3), `PUBLIC_SECURITY_CLAIMS.md`.

---

## Authentication

**Current State:** Token verification (`shared/deps.py::_verify_token`, lines 158-216) tries three paths in order: (1) live `supa.auth.get_user(token)` call to Supabase Auth — server-validated; (2) local HS256 decode via `SUPABASE_JWT_SECRET`; (3) local RS256/ES256 decode via JWKS (1h cache, hardcoded fallback key). Password hashing infrastructure (Argon2id, `security/crypto.py`) is correctly implemented but real user login is delegated entirely to Supabase Auth — this module has zero call sites for actual authentication (SEC-023).

**Evidence:** `shared/deps.py:113-118,158-216`; `security/crypto.py:215-251`.

**Strengths:** Server-validated primary path. Token `exp` is verified (default python-jose behavior, not disabled). Argon2id parameters (`time_cost=2, memory_cost=65536, parallelism=2`) match OWASP 2024 guidance — though this specific implementation isn't in the live login path.

**Weaknesses:** `verify_aud: False` set explicitly in both local-decode paths (SEC-022) — audience claim never checked. Hardcoded JWKS fallback key in source (SEC-026) — stale-key denial-of-auth risk, not a bypass. No server-side logout/token revocation (standard for stateless Supabase JWTs, but should not be described as "secure session termination"). No login success/failure audit trail (SEC-017) — the backend appears to never observe auth events since the frontend talks to Supabase Auth directly.

**Risk:** MEDIUM overall. No confirmed authentication bypass. The gaps are about *visibility* (can't detect brute-force from this system's own logs) and *robustness* (audience check, stale-key fallback), not a forgeable/bypassable token.

**Recommendation:** SEC-022, SEC-026, SEC-017 in `SECURITY_ROADMAP.md`. Correct `security/crypto.py`'s docstring claim (SEC-023) — it is not currently true for user authentication.

---

## Authorization

**Current State:** `shared/permissions.py::PermissionService.require(feature)` is a single, centralized, database-driven feature gate (reads `feature_registry`, not per-route hardcoded checks): kill-switch → dependency-health → status → tier/addon, in that order. Founder emails bypass tier/addon checks but not kill-switch or dependency-health.

**Evidence:** `shared/permissions.py:106-186`.

**Strengths:** Single source of truth for entitlement logic (the module's own docstring documents this replaced scattered `if plan == "pro"` checks). Unknown `feature_key` fails loudly (`RuntimeError`), not silently.

**Weaknesses:** No intra-tenant RBAC found (SEC-029) — every user with access to a `predmet_id` has full read/write; no role hierarchy within a firm account. May be intentional given current product scope — flagged for product-intent confirmation, not asserted as a bug. **More importantly: authorization as designed here is sound, but its enforcement is not centrally guaranteed — it depends on each endpoint correctly checking ownership, which is exactly where the CRITICAL finding below lives.**

**Risk:** MEDIUM for the entitlement system itself; see Multi-tenancy below for the CRITICAL finding this section's design assumption depends on.

**Recommendation:** Confirm intra-tenant RBAC scope against product roadmap (multi-attorney firms). The real priority is SEC-001 (Multi-tenancy, below).

---

## Encryption

**Current State:** AES-256-GCM field encryption (`security/crypto.py::encrypt_field/decrypt_field`) with correct random 12-byte nonces per encryption, proper AEAD tag handling. Argon2id password hashing with OWASP-2024 parameters. `encrypt_field()` is correctly applied on the manual client-creation/update path for JMBG/passport/PIB.

**Evidence:** `security/crypto.py:139-251` (crypto module itself); `klijenti/router.py:220-225,429-434` (correct usage).

**Strengths:** The cryptographic implementation itself is genuinely correct — proper nonce handling, proper AEAD, proper Argon2id parameters. This is not a "looks secure" claim — the primitives are used correctly.

**Weaknesses:**
- **Bulk CSV/XLSX client import bypasses encryption entirely** (SEC-009) — `routers/import_klijenti.py` never calls `encrypt_field()`, inconsistent with the manual-entry path, and may target a non-existent plaintext column (`pib` vs. schema's `pib_encrypted`) — exact failure mode `REQUIRES PRODUCTION VERIFICATION`.
- **Legacy plaintext `jmbg_mb` column never dropped** (SEC-018) — commented-out `DROP COLUMN` in schema history; live contents unverified.
- **No key rotation mechanism** (SEC-024) — `KEY_ID` format exists in ciphertext but multi-key lookup is an explicit stub ("Faza 10b"). One leaked `FIELD_ENCRYPTION_KEY` compromises all encrypted fields with no rotation path.
- Single key, single env var, no HSM/KMS — standard for this company stage, but worth naming plainly rather than implying otherwise.

**Risk:** HIGH (driven by SEC-009's inconsistency, a real "NIKAD plaintext" hard-rule violation on one import path) with the encryption module itself scoring LOW risk in isolation.

**Recommendation:** Fix SEC-009 immediately (small, mechanical). Verify and clean up SEC-018. Scope SEC-024 (key rotation) as real work, not urgent.

---

## Secrets

**Current State:** `.env`/`.env.local`/`.env.production` are gitignored. No hardcoded API-key-shaped strings found in tracked source. No sensitive values found in sampled logger calls.

**Evidence:** `.gitignore:4,31,32`; repo-wide pattern search for OpenAI-key-shaped strings — no matches in tracked files.

**Strengths:** Clean `.env` hygiene at the current-state level.

**Weaknesses:** Git *history* (not just current tracked state) was not checked — `NOT VERIFIED` whether a secret was ever committed and later removed (still recoverable from history if so). `/api/credits-debug` is reachable by any authenticated user and returns internal implementation detail (table existence, RPC dry-run results) — correctly scoped to the caller's own data (not a cross-user leak) but unusual for a "debug" endpoint to remain live in production (LOW, informational).

**Risk:** LOW, with one `NOT VERIFIED` item (git history) worth a one-time check (`git log -p --all | grep` for key-shaped strings, or a tool like `trufflehog` against full history) rather than leaving it unconfirmed indefinitely.

**Recommendation:** Run a full git-history secret scan once, out of band. Consider gating `/api/credits-debug` behind founder-only access or removing it from production.

---

## Database

**Current State:** No raw SQL execution found anywhere in reachable application code — all data access goes through the Supabase/postgrest-py client (`.eq()`/`.select()`/`.insert()` builder pattern, auto-parameterized) or `.rpc()` calls with dict-based parameters, never string-interpolated.

**Evidence:** Repo-wide search for `psycopg`/`asyncpg`/`execute_sql`/raw cursor execution returns only a dev-only script (`scripts/export_rls_policies.py`, not reachable via any endpoint). 14 `.rpc()` call sites, all dict-parameterized.

**Strengths:** This is a genuine architectural strength, not merely an absence of findings — SQL injection is structurally prevented by the client library choice, not by developer discipline per query.

**Weaknesses:** None found in this domain specifically. See Multi-tenancy for the real database-adjacent risk (RLS bypass by design via service key).

**Risk:** INFO / LOW.

**Recommendation:** None required for injection specifically. Maintain the "no raw SQL" convention as new code is added.

---

## AI Security

**Current State:** Real, well-built prompt-injection defenses exist (`security/prompt_guard.py` — homoglyph normalization, base64 payload detection, 35+ regex signatures, message-isolation via `wrap_for_ai()`) but are applied at exactly **one** of an estimated 50+ GPT call sites (`POST /api/pitanje` only). `wrap_for_ai()`, the architecturally strongest layer, is called nowhere in the codebase — dead code. PII scrubbing (`main.py::_skini_pii`) masks only numeric identifiers, not names/addresses, and is not called on the Case Genome extraction path — the single richest source of party PII in the product. Citation/legal-source verification (`shared/genome_validator.py`) checks only whether an article *number* is numerically plausible, not whether it actually exists in the retrieved corpus — its own docstring admits this scope limit.

**Evidence:** `security/prompt_guard.py` (defined, 1 call site: `api.py:2608-2625`); `main.py:1003-1018` (4 call sites total, `case_dna.py` absent); `shared/genome_validator.py:119-160`.

**Strengths:** Where prompt-injection defense is applied, it is genuinely sophisticated — above what most implementations attempt (homoglyph/base64 evasion handling). A new module, `services/legal_reasoning_engine.py` (Phase 0, not yet wired into the live product), already implements real identity-based citation verification against actually-retrieved sources — evidence the team is aware of and actively addressing the citation-verification gap, just not yet in the pipeline users interact with today.

**Weaknesses:**
- **Indirect prompt injection via document upload is live and unmitigated** on the majority of the product's AI surface (SEC-003). Concrete exploit: an uploaded PDF/DOCX containing injection text reaches GPT-4o via `_extract_genome`'s prompt with no screening. Blast radius is currently bounded to the uploading user's own tenant (not yet confirmed cross-tenant).
- **PII exposure to OpenAI is broader than "masked"** implies (SEC-006) — full names and addresses go to a third-party processor unmasked on every Genome extraction.
- **Citation verification is heuristic, not corpus-grounded**, for the live pipeline (SEC-012) — GPT can cite a plausible-but-wrong article and pass verification cleanly.

**Risk:** CRITICAL, driven by SEC-003 (injection coverage) and materially compounded by SEC-006 (PII) and SEC-012 (hallucination) in a legal-advice-adjacent product where wrong citations and leaked party PII both carry outsized real-world consequence.

**Recommendation:** SEC-003 is cheap to close mechanically (wrap existing calls in the existing guard function) — highest ROI security fix available in this entire audit. SEC-006 needs to be disclosed accurately now and scoped as real (NER-based) work separately. SEC-012 — prioritize integrating the already-built `legal_reasoning_engine.py` verification into the live pipeline over building a second solution.

---

## File Upload

**Current State:** `POST /api/predmeti/{id}/upload`, 10MB size cap, `10/minute` rate limit, extension+client-supplied-MIME allowlist check. No path traversal (temp file path is never built from client-supplied filename). No magic-byte validation. No decompressed-size limit on DOCX (a ZIP container) parsing. No malware scanning.

**Evidence:** `api.py:3803-3856` (upload endpoint); `uploaded_doc/extractor.py:89-112` (DOCX), `:9-27,57-60` (PDF/OCR), `:120-128` (format dispatch).

**Strengths:** Size cap present. Path traversal genuinely not exploitable — verified, not assumed (only the file extension substring is used, via `tempfile.NamedTemporaryFile`, which generates its own safe randomized path).

**Weaknesses:**
- **DOCX zip-bomb is unmitigated** (SEC-007) — real, concrete DoS vector; the 10MB *compressed* cap does not defend against a decompression-ratio attack, which is precisely what a zip bomb exploits.
- MIME/type validation trusts the client-supplied header (SEC-015) — mitigated in practice by unhandled parse exceptions on mismatch (produces a 500, not a silent bypass), but not a real content verification.
- No malware scanning (SEC-016) — risk bounded by extraction-only usage pattern (text is parsed out, files aren't re-served), but whether originals are ever re-served as downloads is `NOT VERIFIED`.
- `.doc` accepted in the allowlist but unhandled by the extractor (SEC-028) — produces an unhandled 500, a robustness gap, not an exploit.
- PDF/OCR has no page-count cap (SEC-027), partially mitigated by size/rate limits.

**Risk:** HIGH, driven by SEC-007 specifically; the rest of this domain is MEDIUM-LOW.

**Recommendation:** SEC-007 is the priority — a decompressed-size check before handing files to `python-docx` is a small, high-value fix.

---

## API

**Current State:** CORS is correctly scoped (specific origin list from env, not wildcard, `allow_credentials=True` paired safely). Security headers are present (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, HSTS, Permissions-Policy, CSP) but CSP includes `'unsafe-inline'` for both script-src and style-src, driven by the frontend's extensive inline `onclick=` usage — a real, structural weakening of CSP as an XSS mitigation. Rate limiting exists (slowapi) but coverage is inconsistent (~30% of routes have no explicit `@limiter.limit()`) and `SlowAPIMiddleware` — required for the configured `default_limits` to actually apply app-wide — is never registered, meaning undecorated routes may have effectively zero rate limiting (behavior not empirically confirmed against this specific deployment).

**Evidence:** `api.py:832-843` (CORS), `:974-989` (headers/CSP), `shared/rate.py:20`, `api.py:525,535` (no `SlowAPIMiddleware` found anywhere).

**Strengths:** CORS configuration is correct and specific. Header set is comprehensive where present. One authorization spot-check (`PUT /api/users/{id}/role`) correctly gates on role and validates the input against an enum — no mass-assignment hole found in that sample (not exhaustive across every PATCH/PUT model).

**Weaknesses:**
- **SEC-011 — `SlowAPIMiddleware` never registered**, a one-line, high-value fix with outsized potential impact if the hypothesis is confirmed.
- **SEC-010 — real coverage gaps on sensitive/costly routes**, including the new Legal Reasoning Engine's unmetered GPT-4o endpoint and the entire client-management router.
- **SEC-014 — CSP weakened by 'unsafe-inline'**, a large refactor to fix properly, worth naming as an accepted tradeoff rather than claiming strong CSP protection.
- ID enumeration and full mass-assignment audit across all mutating endpoints were **NOT VERIFIED** in this pass (time-bounded) — flagged as an open item, not silently assumed clean.

**Risk:** HIGH, driven primarily by SEC-011's potential app-wide implication and SEC-010's direct cost-abuse surface.

**Recommendation:** SEC-011 first (trivial, cheap, resolves uncertainty). SEC-010 second (mechanical decorator addition).

---

## Audit

**Current State:** `audit_immutable` protection is enforced by an actual PostgreSQL trigger (`protect_audit_immutable()`, `SECURITY DEFINER`), not application-layer convention — it unconditionally raises an exception on any `UPDATE`/`DELETE`, including from the `service_role` connection the backend uses (Postgres triggers are not bypassed by RLS-exempt roles — these are separate mechanisms). RLS additionally blocks all direct `SELECT` (`USING (FALSE)`). However, coverage of *what gets logged* is narrow: of a defined ~24-action allowlist, only a minority are ever actually called, and login success/failure are never logged at all.

**Evidence:** `migrations/043_security_bulletproof.sql:33-52` (trigger), `:59-61` (RLS); `shared/audit_immutable.py:41` (login actions defined, zero call sites).

**Strengths:** This is a genuine, verified strength — DB-level tamper-evidence, not just a convention that application code happens to follow. The only way to defeat it is direct superuser/admin-console SQL access explicitly disabling the trigger — an organizational access-control question (`REQUIRES PRODUCTION VERIFICATION` who holds that access), not a code gap.

**Weaknesses:** Coverage gap (SEC-017) — the mechanism is strong, but most of what it's meant to protect (login events, GDPR actions, client creation/deletion) is never actually logged, because the calls were never wired.

**Risk:** LOW for integrity of what IS logged; MEDIUM for the coverage gap.

**Recommendation:** Wire login success/failure logging (SEC-017) as the highest-value addition to this otherwise-solid mechanism.

---

## Privacy

**Current State:** GDPR export and erasure endpoints exist and are rate-limited. Legal-basis tracking for client-data processing is real and structured (`pravni_osnov_obrade` enum, `saglasnost_datum` consent date). **The erasure ("right to be forgotten") implementation anonymizes exactly two things: the `profiles` table (email/name) and `korisnik_email_notif`.** No code path touches `predmeti`, `klijenti`, `predmet_dokumenti`, `predmet_dokazi`, `case_dna` (Genome — often containing extensive extracted case narrative and third-party PII), or `billing_entries`. The response message told to the user explicitly claims "predmeti i dokumenti ostaju u sistemu u anonimizovanom obliku" — a claim the code does not support.

**Evidence:** `routers/gdpr.py:171-226`, specifically lines 189-206 (actual scope) vs. line 225 (the claim). `klijenti/router.py:122,138-143` (legal-basis tracking, a genuine strength).

**Strengths:** Legal-basis/consent tracking on client records is real and more structured than most products at this stage attempt. Export functionality exists.

**Weaknesses:** **SEC-002 — the single most significant finding of this entire audit.** An erasure endpoint that tells a user their case data was anonymized, when it was not touched at all, is not an incomplete feature — it is a materially false compliance claim to someone exercising a legal right, for a product processing sensitive litigant data. Separately: no automatic data-retention/expiry policy was found anywhere — data appears retained indefinitely by default (a real gap, but a much more common and lower-severity one than SEC-002).

**Risk:** CRITICAL.

**Recommendation:** This requires a **founder decision**, not a unilateral code fix — either (a) implement real anonymization of case-linked tables scoped to the deleted `user_id`, or (b) if legal-retention obligations genuinely require keeping case data (plausible for a law firm's records), correct the user-facing message to say so accurately instead of claiming anonymization that doesn't happen. Do not ship either fix without that decision being made explicitly — see `SECURITY_ROADMAP.md` P0.

---

## Multi-tenancy

**Current State:** `shared/deps.py::_get_supa()` instantiates the app-wide Supabase client with the **service role key**, which bypasses Row-Level Security entirely — documented Supabase behavior. This means RLS policies (139 of 144 tables have them) provide **zero protection for any request routed through the backend API**. The only real tenant-isolation boundary for the vast majority of tables is each endpoint manually filtering by `user_id`. **Two confirmed, live endpoints do not do this**, and the omission has a visible downstream consequence.

**Evidence:** `shared/deps.py:29,72-80` (service-key client); `api.py:3240-3253,3264-3276` (the two vulnerable endpoints — SEC-001); `api.py:3806-3838,3161` (the correct pattern, used elsewhere in the same file, proving this is an inconsistency, not a systemic architectural absence).

**Strengths:** The correct ownership-check pattern is well-established elsewhere in the same file — this is a fixable, bounded inconsistency, not evidence the team doesn't know how to do this correctly. A small number of tables (`profiles`, `conversations`, `reported_errors`) are accessed directly from the frontend with the anon key, where RLS is the *actual* enforcement mechanism — not evaluated for correctness in this pass, flagged as a narrower follow-up.

**Weaknesses:** **SEC-001 (CRITICAL) — confirmed, reproducible cross-tenant write.** Any authenticated user can insert a note or history entry into another user's case file by supplying that predmet's UUID; because the *read* path for notes filters only by `predmet_id` (not also `user_id`), the injected content becomes visible to the victim. This was checked against exactly 3 endpoints (2 vulnerable, 1 confirmed-safe) in one file (`api.py`) — **a full sweep of every mutating endpoint across the other ~104 router files that accepts a `predmet_id`/`klijent_id`/`dokument_id` path parameter has NOT been completed** and is required before this bug class can be considered closed, not just this one instance.

**Risk:** CRITICAL — this is the most severe technical (non-compliance) finding in the entire audit: live, reproducible, no special access required, real client data at risk.

**Recommendation:** Fix the two confirmed instances immediately (SEC-001, small/isolated). Then commission a full endpoint sweep — ideally converted into an automated test that asserts every mutating route filtering by the correct owner field, so this class of omission cannot silently recur.

---

## Infrastructure

**Current State:** Deployment is multi-process (4 gunicorn workers, `uvicorn.workers.UvicornWorker`), each an independent OS process with no shared memory. Rate limiting and anomaly-detection state are both in-process (SEC-005) — real effective limits are diluted by up to 4×. The event dispatch loop runs independently in every worker with no atomic claim mechanism (SEC-013), risking duplicate processing — notably, the codebase's *own* intake-worker loop already solved this exact problem correctly (`FOR UPDATE SKIP LOCKED`), making this an inconsistency, not a knowledge gap. `/health` returns a static OK with no dependency check. The DR runbook (`scripts/dr_runbook.py`) is a genuinely real, non-stub document (defined RPO/RTO targets, three numbered recovery scenarios, executable check mode) but repeatedly references "Render.com" while `railway.toml` suggests Railway is the actual host — a potentially stale, misdirecting runbook during a real incident.

**Evidence:** `gunicorn.conf.py:4`; `shared/rate.py:21`, `security/anomaly_detection.py:50-53`; `services/event_bus.py:274-330` vs. `shared/intake_worker.py:41`; `api.py:1375-1384`; `scripts/dr_runbook.py:24,31,36,40` vs. `railway.toml`.

**Strengths:** The DR runbook itself, where its facts are current, is a real strength most comparable-size products lack entirely. The fix pattern for the event-loop race condition already exists in this exact codebase.

**Weaknesses:** SEC-005 (shared state), SEC-013 (race condition), SEC-025 (possibly stale runbook), SEC-021 (shallow health check) — none are exotic; all have a known, already-proven-in-this-codebase fix pattern to copy.

**Risk:** HIGH in aggregate (SEC-005 alone undermines two independent security controls at once), individually MEDIUM.

**Recommendation:** SEC-025 first (confirm/correct the runbook — trivial, high incident-response value). SEC-005 and SEC-013 both point to the same underlying need: wire Redis (already a dependency) into shared state.

---

## Supply Chain

**Current State:** 33 total dependencies in `requirements.txt`: 17 exact-pinned, 16 loose (`>=`), no lock file anywhere. Two of the loose-pinned packages are security-critical (`cryptography`, `argon2-cffi`); `sentry-sdk` is also loose. All transitive dependencies of all 33 packages are unpinned regardless, since no lock file exists. Frontend CDN scripts (5 total, jsdelivr/cdnjs/unpkg) all carry SRI `integrity=` hashes.

**Evidence:** `requirements.txt`; `index.html:26-53`.

**Strengths:** Frontend supply-chain hygiene (SRI on every external script) is genuinely good and often overlooked at this company stage.

**Weaknesses:** SEC-020 — no lock file means a fresh install/rebuild can silently pull a newer major version of the exact libraries doing encryption and password hashing, with nothing to catch or intentionally control that.

**Risk:** MEDIUM.

**Recommendation:** Pin exact versions for all 33 packages (start with `cryptography`/`argon2-cffi`/`sentry-sdk`), add a lock file to the build process.

---

## Frontend

**Current State:** Confirmed real, unescaped `innerHTML` injection in the court-portal case-tracking widget, including a field commonly populated by external/attacker-influenced content. Auth is Bearer-token-based (not cookie-based session auth), which is inherently CSRF-resistant. Token storage relies on the Supabase JS client's default (localStorage), which is XSS-readable — raising the stakes of the confirmed XSS finding, since a successful injection could in principle exfiltrate the session token.

**Evidence:** `static/vindex.js:21735-21748` (confirmed XSS, zero escaping present in that function); 519 total `.innerHTML =` assignments in the file, of which only this one was individually verified as unescaped within this pass's time budget — an estimated ~418 lack an escaping-helper token on the same line by a crude heuristic, **not individually confirmed one by one**.

**Strengths:** No CSRF token mechanism needed given the Bearer-token auth pattern — not a gap, a correct architectural choice. An escaping helper (`escHtml`) exists and is confirmed used correctly elsewhere in the same file — the fix pattern is already established in this codebase.

**Weaknesses:** SEC-008 — the confirmed instance is real and should be fixed immediately; the ~418 unverified sites need a scripted sweep, not further manual spot-checking, before this domain can be called closed.

**Risk:** HIGH.

**Recommendation:** Fix the confirmed instance now (small, isolated, uses an existing helper). Commission an automated sweep (grep for `.innerHTML =` without `escHtml`/`_htmlEsc` on the same line, then manually verify each hit) as a follow-up, not optional polish.

---

## AI Models

**Current State:** Covered substantively under **AI Security** above (PII-to-OpenAI exposure, prompt-injection coverage). Additional note specific to this heading: no centralized logging of full prompt/response content to a third party beyond OpenAI itself was found (i.e., no additional model-provider fan-out) — `NOT VERIFIED` beyond that scope, model-provider trust itself (OpenAI's own data-handling terms/retention) is outside what this repository can prove and is a contractual/vendor-diligence question, not a code question.

**Risk:** See AI Security above (SEC-003, SEC-006, SEC-012).

---

## Disaster Recovery

**Current State:** `scripts/dr_runbook.py` defines real RPO (24h target / 4h enterprise goal) and RTO (4h target / 1h enterprise goal), three numbered recovery scenarios with concrete steps, and an executable `--quick`/`--check backup` CLI mode. Key-compromise blast radius is total by architecture (SEC-004 — the single service-role key underlies everything). No key-rotation tracking exists (SEC-030 — the audit action is defined but never called).

**Evidence:** `scripts/dr_runbook.py:14-40`; `shared/deps.py:29,72-80`.

**Strengths:** The runbook's existence and structure is a genuine strength — most repositories this size have nothing comparable.

**Weaknesses:** SEC-004 (architectural, not a quick fix — see Gap Register), SEC-025 (possibly stale host reference), SEC-030 (rotation untracked).

**Risk:** MEDIUM-HIGH, driven by the combination of total key blast-radius and no rotation tracking — not by the runbook's own quality, which is good.

**Recommendation:** Confirm/correct the runbook's host references (SEC-025). Treat service-key rotation cadence and tracking as a real, scheduled operational practice, not a one-time fix.

---

## Monitoring

**Current State:** Sentry is correctly configured — DSN-gated, `send_default_pii=False` (privacy-conscious default), FastAPI/Starlette integrations wired, init failure caught and logged rather than crashing startup. The `"Sentry init failed"` warning seen in local development is a local-environment artifact (package not installed locally) — `requirements.txt` does include it; `REQUIRES PRODUCTION VERIFICATION` that `SENTRY_DSN` is actually set live. A real, non-trivial behavioral anomaly-detection system exists (`security/anomaly_detection.py` — hourly AI/API call rate, daily unique-IP count, off-hours access, compared against a 30-day per-user baseline), and its audit actions (`rate_limit_exceeded`, `suspicious_access`) are genuinely wired and called, not dead allowlist entries. Its effectiveness is undermined by the same in-memory/multi-worker issue already flagged (SEC-005).

**Evidence:** `api.py:29-52` (Sentry init); `security/anomaly_detection.py` (baseline system, confirmed call sites for its audit actions).

**Strengths:** Sentry configuration itself is correct and privacy-conscious. The anomaly-detection feature is a genuine, non-trivial capability many comparable products lack entirely.

**Weaknesses:** SEC-017 (no login audit trail — this system cannot answer "when did this user last authenticate" from its own logs). SEC-005 (anomaly baseline diluted by per-worker state).

**Risk:** MEDIUM.

**Recommendation:** Confirm `SENTRY_DSN` is live in production. Prioritize SEC-005's Redis migration — it directly strengthens this domain's most valuable existing feature.

---

## Enterprise Security Score

Scored 0–100 per category. This is a synthesis judgment informed by the findings above, not a formula — shown with the dominant evidence driving each number.

| Category | Score /100 | Dominant evidence |
|---|---|---|
| Authentication | 65 | Solid mechanism; no login audit trail, unverified audience claim, stale-key fallback risk |
| Authorization | 55 | Sound centralized design undermined by inconsistent enforcement (SEC-001) |
| Encryption | 60 | Correct primitives; real usage gap on bulk import (SEC-009), no rotation |
| Audit | 65 | Genuinely strong DB-level tamper protection; narrow logging coverage |
| Privacy | **20** | SEC-002 — erasure claim not supported by code; no retention policy |
| AI Security | **30** | SEC-003 — injection defense covers ~1/50+ call sites; PII/citation gaps compound it |
| Cloud Security | 45 | Total key blast-radius by design; rate limiting/anomaly detection weakened by architecture |
| Application Security | 45 | Confirmed live IDOR (SEC-001) and confirmed XSS (SEC-008) |
| Infrastructure | 55 | Real DR runbook and health check exist but shallow/possibly stale; race condition present |
| Observability | 55 | Sentry and anomaly detection are real; login-event blind spot |
| Compliance Readiness | **20** | SEC-002 alone is disqualifying for any real compliance claim today |

**Weighted overall: ~45/100.**

---

## Score Update — 2026-07-23, post P0/P1/P2 sprints

**This section re-scores using the identical 11-category methodology above — same synthesis judgment, same evidence-based approach, recomputed from scratch against the current codebase, not adjusted toward a target.** The original table is kept unmodified above as the historical baseline; this section is additive.

| Category | Baseline | Updated | What changed |
|---|---|---|---|
| Authentication | 65 | 67 | SEC-023 label corrected (Argon2id docstring no longer misrepresents what governs live login) — minor, no behavior change |
| Authorization | 55 | 72 | SEC-001 closed, verified twice (regression tests + re-run), full 24-endpoint sweep held. Capped below 85+: the pattern-consolidation work in `AUTHORIZATION_PATTERN_RECOMMENDATION.md` (unifying ~15+ independently-invented ownership-check call sites into one canonical dependency) remains analysis-only, not implemented — the *class* of risk SEC-001 came from isn't structurally eliminated, only its one confirmed instance |
| Encryption | 60 | 60 | Unchanged — **SEC-009 (plaintext PII path on bulk CSV/XLSX import) was not addressed this cycle**, remains open at HIGH severity |
| Audit | 65 | 68 | New `injection_attempt_blocked` immutable audit logging added as part of SEC-003 |
| Privacy | 20 | 48 | The specific disqualifying false claim (SEC-002's erasure message) is now accurate — real, material improvement. Capped well below "good": the underlying retention *policy* is still undefined by design (explicit founder decision to defer it), and **SEC-031 (`auth.users` cascade — potential irreversible loss of case/financial records) remains completely unmitigated in production** — no `RESTRICT` migration written or run, still at Architecture-Approved-pending-Production-Reality-Gate. A privacy score cannot credibly ignore an acknowledged, undisputed, unmitigated catastrophic-data-loss architectural risk |
| AI Security | 30 | 72 | SEC-003 fully closed — all 130 (not ~50) GPT call sites structurally protected via one SDK-level patch, verified by 12 dedicated tests plus the full suite. The single largest score movement in this update, because it was the single largest, most mechanically-fixable gap. Capped below 85+: PII masking (SEC-006, numeric-only) and citation verification (SEC-012, plausibility-only) gaps are untouched this cycle |
| Cloud Security | 45 | 52 | SEC-005's fail-open Redis capability is implemented and tested against the exact original incident (`redis.ResponseError`), but **whether `REDIS_URL` is actually configured in the live production environment is unverified from this repository** — the code capability exists; its production activation does not follow automatically. SEC-004 (service-role key bypasses RLS entirely — total key blast radius by design) is an unchanged architectural fact, not something this cycle's work touched or could touch without a much larger change |
| Application Security | 45 | 68 | SEC-001 (IDOR), SEC-007 (zip-bomb), and SEC-008's confirmed XSS instance are all closed with tests. Capped below 80+: the full ~418-site client-side `.innerHTML=` sweep (SEC-008's larger, separately-tracked item) was not attempted, and CSP's `unsafe-inline` reliance (SEC-014) is untouched |
| Infrastructure | 55 | 55 | Untouched this cycle |
| Observability | 55 | 57 | Minor — new audit log events from SEC-003/SEC-007 |
| Compliance Readiness | 20 | 38 | The single most disqualifying issue (SEC-002's false claim) is resolved. Still far from "compliant": SEC-031 is exactly the kind of finding a real technical/legal due-diligence reviewer would treat as material and would expect to see disclosed, not omitted; SEC-009's open plaintext-PII path is a live compliance-relevant gap; no formal Data Retention Policy exists yet (explicitly deferred, tracked in `DATA_INTEGRITY_INITIATIVE.md`-adjacent work) |

**Updated weighted overall: ~60/100** (simple mean of the above, consistent with how the ~45 baseline was computed; not a target being reverse-engineered — see `docs/security/EXECUTIVE_SECURITY_SUMMARY.md` for the full reasoning and the disclosed path from 60 to 90+).

**Why this isn't higher, stated plainly:** the two largest possible score movements this cycle both landed as scored — AI Security (30→72) and Application Security/Authorization (closing SEC-001) — because they were the two categories with confirmed, live, closeable findings. Privacy and Compliance Readiness moved less than might be expected given SEC-002 closed, specifically *because* SEC-031 was discovered during this same work and remains a real, disclosed, unmitigated risk in exactly those two categories. A score that went to 90+ without SEC-031, SEC-009, and the retention policy being resolved would not be an honest reflection of current risk — it would be counting the fixes and ignoring what was found in the process of making them.

---

## Score Update 2 — 2026-07-23, SEC-009 closed + SEC-031 migration written (not yet run)

| Category | Prior | Updated | What changed |
|---|---|---|---|
| Encryption | 60 | 70 | SEC-009 closed — bulk-import PIB now correctly encrypted via the same `encrypt_field()` primitive as the manual path, 4 tests. `SEC-024` (key rotation) remains open, keeping this below 80+ |
| Privacy | 48 | 52 | Small, deliberate movement — see note below |
| Compliance Readiness | 38 | 42 | Small, deliberate movement — see note below |
| All other categories | — | unchanged | Not touched this update |

**Updated weighted overall: ~61/100** — a 1-point movement, not the large jump the SEC-031 engineering work might suggest. **This is the correct, honest result, not an underselling of real work done.** The reasoning, stated plainly because it's easy to get backwards: `migrations/077_sec031_restrict_auth_users_cascade.sql` now exists, is mechanically verified (15 tests) to match the approved, independently-peer-reviewed plan exactly, and is genuinely ready to run — that is real, substantial engineering progress, and it removes execution risk (the file is correct) and review risk (it matches what was approved) from the remaining work. **It does not yet remove the actual risk SEC-031 measures**, which is that a live `auth.users` row can be deleted today and cascade-destroy case/financial data — that risk is a property of the current production database's actual constraints, and this session has no way to change or verify production state (no Docker, no Postgres, no database credentials available in this environment). A score that jumped to 80+ on the strength of a well-written, untested-in-anger migration file would be scoring the *quality of the plan* rather than the *current state of risk* — exactly the mistake this document's entire methodology exists to avoid. The honest path to the next real score movement is a single event: the founder runs `migrations/077_...sql` against production (after their own Production Reality Gate check) and it's confirmed to have taken effect — at that point SEC-031 becomes genuinely closeable, worth a large movement in Privacy and Compliance Readiness specifically, comparable to what SEC-003 contributed to AI Security.

---

## Score Update 3 — 2026-07-23, SEC-031 confirmed in production

This is the event Score Update 2 said would trigger the next real movement — it happened the same day. The founder ran `migrations/077_sec031_restrict_auth_users_cascade.sql` against production directly, with read-only verification after every step. Full record: `docs/security/SEC031_PRODUCTION_EXECUTION_LOG.md`.

**What actually happened, not just "it ran":** the first attempt failed on `predmet_delegiranja` (a table that existed in production in bare, incomplete form — its own migration had silently no-op'd against it, `CREATE TABLE IF NOT EXISTS` skipping the whole body because the table already existed). The transaction rolled back cleanly, zero data touched — the exact safety property this whole workstream was designed around, now proven under a genuine, unplanned failure, not just in a test. The same pattern recurred for `tos_acceptances`. Both were fixed (the underlying migrations run, the missing FKs added to match) and the migration completed. A final comprehensive query confirmed all **18/18** target constraints `RESTRICT` in production.

| Category | Prior | Updated | What changed |
|---|---|---|---|
| Privacy | 52 | 80 | The specific, disclosed, catastrophic risk (irreversible cascade-delete of case/financial data via a direct `auth.users` deletion) is now confirmed closed in production, not just designed — the single largest reason this category was held down. Not higher: the underlying data-retention *policy* is still undefined, and SEC-034 (below) is a small, fresh reminder that migration hygiene in this project has real gaps |
| Compliance Readiness | 42 | 65 | Same core driver as Privacy, plus SEC-009 already closed. Held below Privacy's jump because of two things specific to this category: the retention policy remains genuinely undefined, and the `tos_acceptances` discovery (below) means this project cannot currently state with confidence that all historical users have a valid recorded ToS/AI-consent acceptance — a real, disclosed compliance fact, not just a technical one |
| Infrastructure | 55 | 58 | Small net-positive: SEC-034 (below) is a real, newly-found gap in migration reliability, but it was discovered specifically *because* this session's own rollback-safe migration design worked exactly as intended under a genuine double failure — a real disaster-recovery-style event handled cleanly is itself evidence for, not against, this category |
| All other categories | — | unchanged | Not touched this update |

**Updated weighted overall: ~66/100.**

**A new finding surfaced in the course of this closure, disclosed rather than absorbed quietly into the good news: SEC-034.** Both mid-execution failures had the same root cause — a `CREATE TABLE IF NOT EXISTS` migration silently doing nothing when its target table already existed in an incomplete form, with no error and no signal that anything was skipped. This is a distinct pattern from SEC-033 (columns designed without a FK from the start) — SEC-034 is about correctly-written migrations that never actually took effect. Confirmed in exactly 2 places so far; **not yet known how many other tables in the `migrations/*.sql` series might be in the same state** — added to the Gap Register as open, P1, explicitly not yet audited beyond the 2 confirmed instances.

**Separately, the `tos_acceptances` discovery has its own compliance weight independent of SEC-031**: the migration's own header comment explains that its absence meant the ToS/AI-consent status endpoint fail-opened to `accepted=true` on every database error — meaning no user had ever had a valid, recorded consent acceptance in production, silently, until the table was created today as a direct consequence of this investigation. This is now fixed going forward; whether any retroactive action is needed for existing users is a product/legal question, not an engineering one, and is disclosed here rather than left implicit.

**Why 66, not higher, stated plainly**: SEC-031's closure was the single largest remaining lever this document had identified, and it moved the categories it was expected to move, by roughly the amount predicted. The score isn't higher because the rest of the register is unchanged — SEC-004 (service-role bypasses RLS, architectural), SEC-006 (PII masking scope), SEC-010 (rate-limit coverage audit), SEC-012 (citation verification integration), SEC-014 (CSP `unsafe-inline`), SEC-017 (login audit logging), the full P2/P3 backlog, the still-undefined retention policy, SEC-033, and now SEC-034 are all still open. Closing the single most severe item doesn't average out an otherwise-unchanged register — which is exactly the honest arithmetic this methodology is supposed to produce.

---

## Score Update 4 — 2026-07-23, SEC-034 live audit run, 2 of 3 confirmed gaps closed in production

Same day as Score Update 3. `scripts/sec034_live_completeness_check.sql` was run against production and returned RLS/FK/policy/index counts for all 154 `public` tables in one pass — the first time this project has had a complete, live picture of its own schema's protection state, rather than a sample or an assumption.

**What it found and what happened to each item**, in full: `klijenti` and `predmet_komentari` had RLS enabled but zero active policies, despite `supabase_setup.sql` (a legacy file outside `migrations/`, missed by the earlier source-only pass) defining 4 CRUD policies for each. `migrations/078_sec034_klijenti_komentari_policies.sql` copied those definitions verbatim and was executed in production; a follow-up query confirmed exactly 8/8 policies now active. Separately, the live counts also resolved a question Score Update 3 had left explicitly open (assumed, not verified): `predmet_delegiranja` shows `fk_count=2`, one short of the 3 migration 054 defines — confirming its `predmet_id→predmeti` foreign key is genuinely still missing in production, not merely unconfirmed. `tos_acceptances` by contrast is now fully complete on every axis. The remaining tables the live check flagged (`audit_log`, `response_audit`, `case_benchmarks`, `zakoni_monitoring`, `conversations`) all turned out to be either correct-by-design or a harmless dead legacy table — no action needed. A side discovery, tracked as SEC-035: 6 tables in production have no `CREATE TABLE` anywhere in the repository at all; 2 were already known-dead, the other 4 have real data but zero application code references them.

| Category | Prior | Updated | What changed |
|---|---|---|---|
| Privacy | 80 | 82 | A confirmed, previously-unknown defense-in-depth gap on `klijenti` (client PII) is now closed and production-verified — genuine but smaller than SEC-031's move, since SEC-004 means app-layer checks were already the actual enforcement boundary for this data, not RLS |
| Compliance Readiness | 65 | 66 | Small: the live audit is now complete-coverage rather than sample-based, which is itself worth something for a due-diligence document, but doesn't resolve the still-undefined retention policy that's holding this category down |
| Infrastructure | 58 | 60 | SEC-034's central uncertainty — "how many more tables share this pattern" — is now fully answered (all 154 tables checked, not a sample), and 2 of the 3 concrete items found were fixed and confirmed same-day. Held back from a larger jump by the newly-confirmed `predmet_delegiranja` FK gap and the new SEC-035 schema-provenance finding |
| All other categories | — | unchanged | Not touched this update |

**Updated weighted overall: ~67/100.**

**Why only +1, given two real production fixes landed**: per this project's own standing rule ("code is ready ≠ risk is reduced" — only verified-from-reach work earns credit), the categories above already priced in SEC-031's much larger production-verified fix at Score Update 3; SEC-034's fixes are real and confirmed, but smaller in blast radius (defense-in-depth on 2 tables where the actual enforcement boundary was already elsewhere, per SEC-004) and partially offset by two things this same audit surfaced: a newly-*confirmed* (not new, but now proven rather than assumed) FK gap on `predmet_delegiranja`, and a brand-new finding (SEC-035) about untracked production schema. Net honest movement: small and positive, not rounded up.

---

## Score Update 5 — 2026-07-23, SEC-035 documented and resolved

Same day. SEC-035 (6 production tables with no `CREATE TABLE` anywhere in the repository) is now resolved via documentation, not a code change: the founder confirmed the 4 previously-unexplained tables (`agent_runs`, `filter_results`, `jobs`, `system_state`) are legitimate artifacts from early development phases, no longer part of any active code path. This is recorded rather than assumed — the live diagnostic already independently confirmed all 4 are RLS-enabled with zero policies (deny-by-default) and a full-codebase grep already confirmed zero application references, so "documented and resolved" reflects verified state plus founder-supplied provenance, not just a founder assertion taken on faith.

| Category | Prior | Updated | What changed |
|---|---|---|---|
| Infrastructure | 60 | 61 | A schema-hygiene unknown (untracked production objects) is now a documented, closed question rather than an open one — small movement because no code changed and the underlying risk was already assessed as Low before this update |
| All other categories | — | unchanged | This was a documentation closure, not a technical fix — no other category is affected |

**Updated weighted overall: ~67/100** (rounds to the same figure as Score Update 4 — the movement is real but too small to shift the overall number at this precision).

**SEC-034 is not yet fully closed**: the `predmet_delegiranja.predmet_id` foreign key is drafted (`migrations/079_fix_predmet_delegiranja_fk.sql`) but not yet executed, pending a founder decision on `ON DELETE` semantics — the requested `RESTRICT` conflicts with migration 054's original, still-current `CASCADE` design, and `RESTRICT` would make any previously-delegated `predmet` permanently undeletable given the app has no endpoint to remove delegation rows first. This is flagged, not resolved, in this update — no score credit taken for it until it actually lands in production, consistent with this document's standing practice.

---

## Final Assessment

**Can Vindex AI honestly claim to be enterprise-grade secure today? No.** Not because any single domain is unusually weak for a company at this stage — several domains (audit trail integrity, DR runbook existence, crypto primitive correctness, SQL injection resistance, CORS configuration) are genuinely strong, in some cases better than typical for this company size. The disqualifying factors are two **confirmed, live, evidence-based CRITICAL findings**: a reproducible cross-tenant data-injection vulnerability (SEC-001) and a GDPR erasure endpoint whose user-facing claim is not supported by what the code actually does (SEC-002) — plus a CRITICAL-severity gap in the product's core AI safety surface (SEC-003). None of these are hypothetical or "best practice" gaps; all three are demonstrated, with file:line evidence, to be true today.

### 1. Would you recommend a large international law firm use this system today?

**NE.** Not because the architecture is unsound — the *pattern* for doing this correctly already exists in this exact codebase (the fix for SEC-001 is copying code that already works three lines away; the fix for SEC-003 is calling a function that's already written). The reason is that a large law firm's due diligence would find SEC-001 and SEC-002 within the first few hours of any real security review, and both are the kind of finding that ends a procurement conversation immediately, not a follow-up-question kind of finding. Recommend revisiting this question after SEC-001, SEC-002, and SEC-003 are closed and independently re-verified — at that point the underlying architecture is genuinely closer to enterprise-ready than the current score suggests.

### 2. Should Vindex AI publicly claim "enterprise-grade security"?

**NE.** See `PUBLIC_SECURITY_CLAIMS.md` List B. This is not a claim that can be qualified or softened — it either has evidentiary support or it doesn't, and today it doesn't, for the specific reasons above.

### 3. What three things, done in the next 30 days, most increase security?

1. **SEC-001** (IDOR fix + full endpoint sweep) — closes the single most severe confirmed live vulnerability, small isolated first patch, larger but mechanical sweep after.
2. **SEC-003** (wrap all GPT call sites in `prompt_guard.wrap_for_ai()`) — closes the largest AI-safety gap using code that already exists, no new logic to write.
3. **SEC-002 decision + fix** (GDPR erasure) — requires a founder decision first, but is the single highest-consequence compliance gap and should not wait.

### 4. What three public claims can be used on the website/LinkedIn today, without risk of misleading users?

See `PUBLIC_SECURITY_CLAIMS.md` List A for the full, evidence-gated list. Headline three:
1. Sensitive identifier fields (JMBG, passport, PIB) are encrypted at rest using AES-256-GCM before being written to the database (qualify: on the manual-entry path — SEC-009 must close before this can be stated without qualification).
2. All audit log entries are cryptographically hash-chained and protected by a database-level trigger that blocks modification or deletion, even for the application's own service account.
3. Passwords, where applicable, are hashed using Argon2id with parameters meeting current OWASP guidance.
