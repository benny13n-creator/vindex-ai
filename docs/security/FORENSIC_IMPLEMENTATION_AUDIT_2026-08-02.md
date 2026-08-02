# Vindex AI — Forensic Implementation Security & Privacy Audit

**Date:** 2026-08-02
**Method:** Implementation audit, not a document review and not a penetration test. Every claim
below is backed by code read directly from this repository (`C:\Users\Benny\moj_prvi_agent\src\moj_prvi_agent\legal-agent`,
branch `main`), cited `file:line`. Existing documentation in `docs/` was used only as a
cross-check — where it disagrees with the code, the code wins, and the disagreement is stated
explicitly. Where something cannot be verified from the repository (typically: live Supabase/Render
project configuration), this report says so — it does not guess. Findings are marked
✓ IMPLEMENTED / ⚠ PARTIAL / ✗ MISSING throughout.

**Relationship to existing security documentation:** this project already maintains
`docs/security/SECURITY_GAP_REGISTER.md` (36 findings, SEC-001 through SEC-036, most closed),
`docs/SECURITY_MATURITY_DASHBOARD.md`, `docs/security/STRIDE_THREAT_MODEL.md`, and
`docs/security/PUBLIC_SECURITY_CLAIMS.md`. This audit re-verified a sample of prior SEC-XXX
findings directly against current code (noted inline where a prior finding is confirmed still
open or confirmed fixed) and surfaces **37 new findings** (numbered continuing the existing
sequence, SEC-037 through SEC-073) that were not previously tracked — several found via git
history and cross-router sweeps that the original five-track audit did not cover.

**Two findings require action independent of this report's own timeline** (already flagged to the
founder directly when discovered):
- **SEC-037** — a live-looking OpenAI API key is present in git history (commit `dc29b76`), removed
  from the working tree in a later commit but not from history. Recommended: rotate immediately.
- **SEC-038** — the `profiles` table's UPDATE policy has no column restriction and the frontend
  performs a direct client-side write to it; `profiles` holds every subscription-entitlement column.
  Recommended: a 30-second live test, then fix regardless of outcome.

---

## Executive Summary

Vindex AI's security engineering, where it has been deliberately invested (the 2026-07-23–26 audit
sprints: cross-tenant ownership checks, prompt-injection guarding, audit-log immutability,
rate-limiter fail-open behavior, XSS sanitization), is genuinely sound and independently verified
sound again by this pass. The pattern that repeats across nearly every domain in this report is
different from "the team doesn't know how to build this correctly" — they clearly do, and have
proven it (the Trezor document-encryption path, the `klijenti/` RBAC module, the
`audit_immutable` hash chain, the API-security ownership discipline measured at 95/100 sampled
endpoints). The repeating failure mode is **narrow, inconsistent application of a correct pattern**:
one upload path encrypts, three don't; one router sanitizes free text, eighty-four don't; one
comparison uses `hmac.compare_digest`, a dozen use `!=`; one table gets a `SELECT`-only grant with
`SECURITY DEFINER` RPCs for writes (`user_credits`), the structurally identical `profiles` table
does not. This is a process gap (no systematic check that a new table/router/upload path repeats
the established pattern), not a competence gap — and it is the same diagnosis this project's own
`docs/security/AUTHORIZATION_PATTERN_RECOMMENDATION.md` already reached for ownership checks
specifically, now shown to generalize across the whole codebase.

**The single largest structural fact, already known and disclosed by this project (SEC-004), that
this audit re-confirms and traces forward into new consequences:** the backend holds exactly one
Supabase client, built with the service-role key (`shared/deps.py:29,72-81`), for all application
traffic. Every one of the 148 tables' Row-Level-Security policies is inert for API requests. Tenant
isolation is 100% application-layer discipline with no database backstop. This is not new — it is
the reason SEC-001 (the original cross-tenant write bug) was possible, and this audit found three
more instances of the same root cause under new names (SEC-039, SEC-040, SEC-059).

**What is genuinely good, stated plainly so it isn't lost in a findings list:** the audit-log
immutability mechanism (trigger + hash chain) is real and correctly designed; the prompt-injection
guard is structurally comprehensive for its one covered surface; CI runs real blocking scans
(gitleaks, bandit, semgrep, pip-audit); the client-vault document encryption is well-built; the
`_q_hash`/response-hash pattern for AI query logging is a genuinely privacy-preserving design;
CORS is a real allowlist, not a wildcard; ownership checks are correct on 95% of sampled mutating
endpoints. This is not a codebase built without security awareness — it is one where the awareness
has not yet been made structural everywhere it needs to be.

---

## 1. Authentication

| Feature | Status | Evidence |
|---|---|---|
| Login flow (email+password) | ✗ NOT IN THIS BACKEND — delegated to Supabase Auth client-side | `static/vindex.js:629` `signInWithPassword`; no `/api/login` route exists |
| Registration | ✓ IMPLEMENTED | `api.py:2299-2377`, rate-limited 5/minute |
| JWT verification | ✓ IMPLEMENTED (HS256 + RS256/ES256 via JWKS) | `shared/deps.py:158-213,216-245,272-299` |
| JWKS handling / key rotation | ⚠ PARTIAL | 1h cache but hardcoded fallback key, no `kid` matching (`shared/deps.py:113-118,141-144`) — see SEC-026 |
| Refresh tokens | ✗ NOT IN THIS BACKEND | Handled by `supabase-js` client-side |
| Session lifetime | ✗ Not controlled by this codebase | No TTL config; `verify_aud: False` (`shared/deps.py:188,205`) |
| Token invalidation / logout | ⚠ PARTIAL — dead code | `api.py:2452-2469` has zero callers; frontend `doLogout()` never calls it — see SEC-042 |
| Password hashing | ✗ Built, unused | Argon2id (`security/crypto.py:227-265`) has zero call sites; real login is Supabase-delegated |
| MFA / 2FA | ✗ MISSING, publicly claimed | `static/security.html:79` claims it; no enrollment/challenge/AAL code exists anywhere — see SEC-044 |
| Password reset | ✓ IMPLEMENTED (Supabase, client-side) | `static/vindex.js:585,597,605` |
| Brute-force protection (login) | ✗ Cannot exist in this codebase | Login never reaches this backend |
| Session/device limit | ✓ IMPLEMENTED | `routers/sesije.py:26-28,84-148` |
| Machine auth (API keys) | ⚠ PARTIAL — plaintext | See SEC-043 |
| Machine auth (cron/webhook/bot) | ✓ IMPLEMENTED, fail-closed | Multiple sites, verified |
| Client-portal token auth | ✓ IMPLEMENTED, well-built | HMAC-SHA256, `hmac.compare_digest`, hash-only persistence, DB revocation |

### AUTH-1 (structural, not a defect) — Real user authentication is entirely outside this codebase

This backend can prove token *verification*; it cannot prove password storage, password policy,
login rate limiting/lockout, or refresh-token rotation — those are Supabase project settings,
**unable to verify from implementation**. Any external questionnaire answer on these topics must
be sourced from the live Supabase dashboard, not this repo. **Recommendation:** export the
Supabase Auth configuration into a version-controlled snapshot (mirroring the pattern
`scripts/export_rls_policies.py` already establishes for RLS) and assert it in CI.

### SEC-037 — Live OpenAI API key in git history — **CRITICAL, act independent of this report**

`git show dc29b76:.env` returns a complete, live-format `OPENAI_API_KEY=sk-proj-…` value. Removed
from the working tree at `c6c4135`, but history is not rewritten — `.gitignore:4` prevents
recurrence, not disclosure. Independently confirmed by two separate agents in this audit. Anyone
who has ever cloned this repository can extract it in one command.
**Impact:** direct billing fraud; if org-scoped, broader account exposure.
**Remediation:** rotate at the OpenAI console now; audit usage back to the commit date; decide
whether to rewrite git history (`git filter-repo`, force-push, coordinate with all clone holders)
given the ~475MB `.git` directory and any existing forks/mirrors.
**Complexity:** Trivial to rotate; Medium to purge history.

### SEC-038 — `profiles` table UPDATE policy has no column restriction; client writes to it directly — **CRITICAL pending live confirmation**

`supabase_setup.sql:39-40`: `CREATE POLICY "Korisnici azuriraju sopstveni profil" ON public.profiles
FOR UPDATE USING (auth.uid() = id);` — no `WITH CHECK`, no column list, and no `GRANT UPDATE (...)`
narrowing it anywhere in `migrations/*.sql`. `static/vindex.js:702` performs a live client-side
write to this exact table using the browser's authenticated session:
`sb.from('profiles').update({ full_name: fullName }).eq('id', currentUser.id)`.
`profiles` holds every entitlement column read by `PermissionService`
(`shared/permissions.py:149-183`): `is_pro`, `subscription_type`, `addons`,
`subscription_expires_at`, `subscription_seats_extra` (`migrations/063_entitlement_system.sql:29-34`).

**If** the `authenticated` Postgres role holds the table-level UPDATE privilege on `profiles` (as
it demonstrably must for the `full_name` write above to function, absent an unlisted column-level
grant restricting it — Postgres requires table-level or column-level UPDATE privilege independent
of RLS), any authenticated user can, from the browser console:
```js
supabase.from('profiles').update({is_pro:true, subscription_type:'enterprise',
  addons:['digital_assets_standalone','digital_assets'],
  subscription_expires_at:'2099-01-01', subscription_seats_extra:99}).eq('id', myUid)
```
and self-grant every paid tier and addon.

**Contrast proving this is an oversight, not a design choice:** the structurally identical
`user_credits` table is correctly locked down — `GRANT SELECT` only (`supabase_setup.sql:78`), all
writes forced through `SECURITY DEFINER` RPCs. The same discipline was never applied to `profiles`.

**Verification limit, stated honestly:** whether `authenticated` additionally holds a
column-restricted grant that isn't visible in this migration file (e.g., applied by hand in the
Supabase Dashboard, which `scripts/export_rls_policies.py:8-15` documents as this project's actual
process for live RLS/grant state) is Supabase project state, not repo state. **Recommended: a
30-second live test before triage** — attempt the update above against a non-production test
account. The policy definition itself is unambiguous and should be corrected regardless of the
test's outcome.

**Remediation:** `FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id)` plus
`REVOKE UPDATE ON public.profiles FROM authenticated; GRANT UPDATE (full_name) ON public.profiles
TO authenticated;` — or remove the client-side write entirely and route `full_name` through the
existing server-side pattern already used correctly at `api.py:2400-2412` (`onboarding_complete`,
field-allowlisted). Per this project's own migration-safety convention, the founder runs the SQL.
**Complexity:** Low.

### SEC-042 — Token revocation not enforced; `/api/logout` is dead code

`shared/deps.py:216-245` (`_verify_token`): if the live Supabase `get_user(token)` call returns an
empty user (exactly what happens after `admin.sign_out`), the code falls through to
`verify_token_local` — an offline signature check that has no way to know the token was revoked.
`POST /api/logout` (`api.py:2452-2469`), the only real revocation path, has zero callers —
`doLogout()` in the frontend calls only client-side session teardown. **A revoked token remains
fully valid until its natural expiry.** **Remediation:** wire the frontend to call
`/api/logout`; treat "SDK reached Supabase, got no user" as a hard reject, reserving the
local-decode fallback for genuine SDK/network exceptions. **Complexity:** Low.

### SEC-026 (confirmed still open) — Hardcoded JWKS fallback key, no `kid` matching, duplicated

`shared/deps.py:113-118` and `api.py:249-254` each independently hardcode the same ES256 public
key as a JWKS-fetch-failure fallback; key selection matches on `alg`/`kty`, never on `kid`. Not
independently exploitable (the `alg`-confusion classic doesn't apply — the HS256 branch uses a
separate secret), but a real stale-key/duplicated-maintenance risk. **Complexity:** Low-Medium.

### SEC-044 — 2FA publicly claimed, not implemented

`static/security.html:79`: *"Opciona dvofaktorska autentifikacija (2FA) putem Supabase TOTP."* No
`mfa`/`totp`/`enroll`/`challenge`/`aal2` code exists anywhere. `shared/audit_immutable.py:65`
defines `2fa_enable`/`2fa_disable` audit actions that nothing ever emits. This is exactly the
failure mode `docs/EVIDENCE_BASED_CLAIMS_POLICY.md` exists to prevent, materially relevant for
legal-sector sales/DPA diligence. **Remediation:** remove the claim, or implement it.
**Complexity:** Low (remove) / Medium-High (implement).

---

## 2. Authorization

**Measured discipline:** 90 router files + `api.py` + `klijenti/router.py` enumerated (576
endpoints, 311 mutating). A 22-file deep sample of 100 mutating endpoints, each read by hand:
**95/100 have a verifiable ownership or authorization boundary.** The failures are concentrated and
specific, not systemic.

| Feature | Status | Evidence |
|---|---|---|
| Per-endpoint auth dependency | ✓ IMPLEMENTED | 17 exceptions, all verified as intentional (portal-HMAC/API-key/cron-secret/webhook-HMAC) |
| Ownership validation (predmet-scoped) | ⚠ CORRECT but duplicated ~15× by hand | `AUTHORIZATION_PATTERN_RECOMMENDATION.md`'s proposed consolidation (`verify_predmet_ownership`) does not exist in code |
| Entitlement/tier control | ✓ IMPLEMENTED | `shared/permissions.py:106-186`, DB-driven |
| RBAC — CRM (klijenti) | ✓ IMPLEMENTED | `klijenti/permissions.py:28-118` |
| RBAC — firm membership | ✓ IMPLEMENTED, tenant-scoped | `routers/kancelarija.py` |
| RBAC — `shared/rbac.py` | ✗ Dead module | Zero importers — see SEC-073 |
| Agent isolation | ✗ Dead module | `security/agent_isolation.py` zero enforcement call sites — see SEC-073 |
| Platform admin authorization | ⚠ PARTIAL | Email-claim-based, not DB-role-based — see SEC-046-admin below |
| Tenant isolation model | ⚠ PARTIAL — app-layer only | Same SEC-004 fact as elsewhere |
| Database-level RLS | ⚠ Exists, bypassed, unverifiable live | 147 policies never execute for app traffic |
| IDOR — GET endpoints | ✓ IMPLEMENTED | Only 2 unscoped, both public reference data |
| IDOR — mutating endpoints | ⚠ 5 confirmed gaps | SEC-039, SEC-040, SEC-059 below |
| Privilege escalation | ✗ 2 confirmed paths | SEC-038, SEC-041 |

### SEC-039 — Document-session IDOR exposes privileged uploaded documents cross-tenant

`uploaded_doc/session.py:35-64` (`validate_session`) checks only that a Pinecone namespace exists
and hasn't expired — **it never takes or checks a `user_id`.** Consumers:
`POST /api/dokument/pitanje` (`routers/dokument.py:337-361`), `/analiza` (`:369-394`),
`/klasifikuj-sesija` (`:436-450`, no validation of the caller at all beyond generic auth),
`/rokovi` (`:459-473`). `namespace_prefix` is caller-supplied and accepts `"pred_"`, whose
namespaces never expire.
**Attack:** any authenticated user who learns another lawyer's `session_id` (browser history,
shared screenshot, a support-ticket paste, a proxy log) can `POST /api/dokument/pitanje` with that
`session_id` and `namespace_prefix: "pred_"` and receive a summary of the victim's uploaded filing.
`session_id` is a `uuid4().hex`, so not brute-forceable — exposure requires prior ID disclosure,
which lowers likelihood without eliminating impact.
**Remediation:** persist `(session_id → user_id)` at upload time and enforce it in
`validate_session`, or bind to the already-implemented `rag_owner_namespace()` pattern instead of a
bare session id. **Complexity:** Medium.

### SEC-040 — Cross-tenant write on Smart Intake entity correction

`routers/smart_intake.py:211-243` (`POST /entities/{entity_id}/correct`) authenticates the caller
but `shared/intake_documents.py:175-222`'s lookup/update (`:191,198-201`) filters only on
`entity_id` — no `user_id`/`uploaded_by` check, unlike its two sibling endpoints in the same file
(`:172,365`), which are correctly scoped. **Attack:** an attacker who obtains an `entity_id`
(returned in `/jobs/{job_id}` responses) can silently overwrite another user's extracted deadline/
party/amount and mark it `reviewed=true`, suppressing the low-confidence review prompt — so the
victim's next `finalize` creates a predmet from attacker-controlled data. Falsified deadlines in a
legal-deadline product is a severe integrity failure. **Remediation:** join
`extracted_entities → intake_documents → intake_jobs.uploaded_by` and filter on the caller.
**Complexity:** Low.

### SEC-041 — Global role assignment endpoint has no tenant boundary

`klijenti/router.py:1107-1127` (`PUT /api/users/{target_user_id}/role`) requires PARTNER role but
performs an **unconditional** upsert into `user_roles` — no check that `target_user_id` shares a
firm with the caller (`user_roles` has no `kancelarija_id` column at all). Any PARTNER-role user
(or founder) can change any other user's role in any firm — strip a competitor's confidential-field
access, or grant an accomplice `HIGHLY_CONFIDENTIAL` access in a firm they can already reach.
**Aggravating:** three separate, inconsistent role vocabularies exist across
`klijenti/permissions.py`, `routers/kancelarija.py`, and the dead `shared/rbac.py` — documented as
already known to have caused one bug (`routers/kancelarija.py:44-51`). **Remediation:** add
`kancelarija_id` to `user_roles`, require target to be an active member of the caller's firm;
consolidate to one role vocabulary. **Complexity:** Medium.

### SEC-059 — Mass assignment lets CSV import set `klijenti.user_id` to an arbitrary value

`routers/import_klijenti.py:151-213`: the column-mapping whitelist (`VINDEX_POLJA`) is returned to
the client as a UI hint but **never enforced** on `/api/klijenti/import/execute` — any mapped
column name is written directly into the insert dict, including `user_id`. Compounded by
`klijenti.user_id` being untyped `TEXT NOT NULL` with **no foreign key**
(`supabase_setup.sql:570`) — an injected value isn't even validated as a real user — and by SEC-004
(the insert runs under service-role, so the `klijenti_insert` RLS policy never evaluates regardless).
**Attack:** an authenticated user POSTs a CSV mapping `user_id` to the victim's UUID; rows land in
the victim's CRM under the victim's identity, or fields like `pib_encrypted` are set directly to
bypass encryption. Rate-limited 5/min but otherwise open to any authenticated user.
**Remediation:** enforce the whitelist (`if vindex_polje not in VINDEX_POLJA: continue`); separately,
type `klijenti.user_id` as `uuid` with an `auth.users` FK (`ON DELETE RESTRICT`), matching the
pattern migration 077 already established. **Complexity:** Trivial (whitelist) / Medium (schema).

### SEC-045-admin (contained, not exploited here) — Platform admin authority is a mutable email claim, not a stored role

`shared/deps.py:33-42,59-60` (`FOUNDER_EMAILS`/`_is_founder`) gates 16 sites by JWT email claim.
Whether a user can change their own email to a founder address depends on Supabase
email-change-confirmation settings — **unable to verify from implementation.** No audit trail
distinguishes which founder performed which action. **Remediation:** move to a DB-backed role,
keep the env var only as bootstrap. **Complexity:** Medium.

### SEC-004 (confirmed still open, expanded) — RLS is not the enforcement mechanism for any application traffic

`shared/deps.py:29,72-81`, `api.py:119,162`, `app/services/audit_log.py:47-49` — every Supabase
client in this codebase is built from `SUPABASE_SERVICE_KEY`. No anon-key + user-JWT client exists
anywhere. All 148 tables' RLS policies are inert for API traffic; the four direct browser writes
(`profiles`, `conversations`, `reported_errors` via `static/vindex.js`) are the only place RLS is
load-bearing — and for `profiles` that protection is exactly the SEC-038 defect. `routers/komentari.py:86`,
`smart_intake.py:167-169`, and `proof.py:52` all state this explicitly in their own comments — it
is a known, accepted architectural fact, not a hidden one, but this audit found three new concrete
consequences of it (SEC-039, SEC-040, SEC-059) beyond the original SEC-001.
`docs/security/AUTHORIZATION_PATTERN_RECOMMENDATION.md`'s proposed `verify_predmet_ownership`
consolidation remains **designed but not implemented**.

### SEC-073 — Dead authorization modules create a false impression of enforcement

`shared/rbac.py` (6-role/20-permission matrix, zero importers) and
`security/agent_isolation.py::check_agent_access` (zero call sites; only a read-only summary
function is used, in a founder-only admin view) — both read, by a reviewer or DPA questionnaire,
as active controls. **Remediation:** delete both, or wire them in. **Complexity:** Low (delete) /
Medium (wire).

---

## 3. Data Protection

| Feature | Status | Evidence |
|---|---|---|
| AES-256-GCM field encryption primitive | ✓ IMPLEMENTED, sound | `security/crypto.py:151-167,170-207`; fail-fast key validation at startup |
| JMBG/passport/PIB encrypted (manual + CSV) | ✓ IMPLEMENTED | `klijenti/router.py:241-245,459-463`; `routers/import_klijenti.py:205-211` |
| Client-vault documents encrypted at rest | ✓ IMPLEMENTED, well-built | Randomized key, encrypted filename, watermarked reveal-audit |
| Smart Intake uploads encrypted at rest | ✓ IMPLEMENTED | `routers/smart_intake.py:67-77,110-118` |
| Client-portal uploads encrypted at rest | ✗ MISSING | See SEC-056 |
| Case-document full text encrypted at rest | ✗ MISSING | See SEC-057 |
| Data-classification enforcement | ✗ Dead code | See SEC-055 |
| Key rotation | ✗ Designed, not implemented | SEC-024 (confirmed open) |
| HTTPS enforcement (headers) | ✓ IMPLEMENTED | `api.py:1075-1106` |
| Sentry PII scrubbing | ✓ IMPLEMENTED | `send_default_pii=False` |

### SEC-056 — Client-portal uploads stored unencrypted, path discloses IDs and filename

`routers/client_portal.py:567-576`: raw bytes uploaded (unlike the three sibling paths, all of
which encrypt). Storage path embeds `advokat_uid/predmet_id/{uuid}_{original_filename}` — directly
contradicting `SECURITY.md:88`'s public claim that storage paths are randomized UUIDs with no
filename. **These are client-submitted evidence files, the least-trusted-origin, highest-sensitivity
category in the product**, and the one path that skipped the pattern. **Remediation:** apply the
existing `smart_intake.py::_encrypt` / `crypto.generate_storage_key()` pattern here; backfill
existing objects. **Complexity:** Low (~1 day + backfill script).

### SEC-057 — Case document full text stored plaintext despite ATTORNEY_PRIVILEGED classification

`api.py:4269,4299`: up to 100,000 characters of extracted document text written plaintext to
`predmet_dokumenti.tekst_sadrzaj`. `security/data_classification.py:60-67` classifies this content
`ATTORNEY_PRIVILEGED` — a classification nothing enforces (SEC-055). This is the single largest
gap between the product's own stated security posture and its implementation: the highest-value
content in the entire system — full pleadings, evidence, case narratives — sits behind access
control alone, with no cryptographic barrier, while three-digit identifier fields two tables over
are correctly AES-256-GCM encrypted. **Remediation:** either encrypt (accepting the loss of
`ilike` search — `routers/search.py:83` already searches this exact column, so this needs a
blind-index or in-app-filtering redesign) or formally document that this content is protected by
access control only, and correct any claim implying otherwise. **Complexity:** Medium-High.

### SEC-055 — The entire data-classification enforcement layer is dead code

`security/data_classification.py`'s `sanitize_for_ai`, `can_send_to_ai`, `classify_decorator`,
`require_classification` have **zero call sites anywhere in the codebase** (verified by repo-wide
grep). `sanitize_for_ai` is the only code that would strip `jmbg`/`maticni_broj`/`pib`/`password`/
`iban` before an LLM call — it never runs. `docs/architecture/VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md:252`
lists this module as a live security control; it is not. **Remediation:** wire it into the single
`shared/ai_client.py` chokepoint (the same one the prompt-injection guard already uses), or delete
the module and correct the Architecture Bible — a half-built, unwired security module is worse
than none, because it is mistaken for coverage that doesn't exist. **Complexity:** Low to wire.

### SEC-024 (confirmed open) — Key rotation designed, not implemented

`security/crypto.py:190-196` — the key-id is parsed from ciphertext and discarded; only one active
key is ever used. A single key protects JMBG/passport/PIB, SEF API keys, Trezor blobs, and Smart
Intake blobs, with no rotation path short of a full re-encryption outage.
`KEY_ROTATION_ANALYSIS.md:59-82` documents the fix design already. **Complexity:** Low-Medium.

### SEC-058 — Full Supabase user object and PIB logged at INFO on the hot path

`shared/deps.py:229` and `api.py:216`: `logger.info("SDK get_user resp: %s", resp)` — fires on
**every authenticated request**, serializing the full GoTrue `UserResponse` (email, phone,
`app_metadata`, `user_metadata`, `identities[]`) into whatever log aggregator the hosting platform
uses. `routers/sef.py:315` separately logs a client's PIB in plaintext. Contrasts sharply with this
same codebase's own good practice elsewhere (`_q_hash`, IP hashing, boolean-only secret logging).
**Remediation:** delete both `resp`-dumping log lines; drop `pib=%s` from the SEF log line.
**Complexity:** Trivial — highest value-per-effort fix in this entire report.

### Also confirmed in this domain: SEC-005 (field encryption inconsistency, `fakture.klijent_pib` plaintext vs `klijenti.pib_encrypted`) — already tracked, not re-verified line-by-line in this pass but consistent with the SEC-057 pattern found here.

---

## 4. AI Privacy

*(Full detail in the standalone section drafted during this audit — reproduced here.)*

| Feature | Status | Evidence |
|---|---|---|
| Which providers receive data | ✓ Identified (OpenAI, Pinecone, **Cohere — undisclosed**) | See SEC-051 |
| PII anonymization before AI calls | ⚠ PARTIAL | `main.py::_skini_pii` — numeric IDs, phone, IBAN, email, court-case numbers, heuristic addresses; **no person names, anywhere** |
| Genome/LRE extraction path scrubbed | ✗ MISSING | Zero `_skini_pii` calls in `routers/case_dna.py` or `services/legal_reasoning_engine.py` — confirmed by grep |
| Prompt injection protection | ✓ Comprehensive for chat completions | `shared/ai_client.py:113-187`, all ~130 call sites, verified real |
| Prompt injection protection on other surfaces | ✗ MISSING | Embeddings, Whisper, TTS, Realtime API — none screened |
| Prompts/outputs logged | ✓ NOT logged (by design, verified) | `app/services/audit_log.py` — hash + length only, explicitly documented PII-free |

### SEC-006 (confirmed still open) — PII scrubbing covers numeric identifiers only, and misses the richest source of party PII entirely

`main.py:1008-1033` masks JMBG/PIB/matični broj/lična karta/pasoš/phone/IBAN/court-case-number/
email/heuristic-address — broader than the original 2026-07-23 finding suggested, but **still zero
coverage for person names**, and **zero call sites in the Case Genome / Legal Reasoning Engine
extraction path** (`routers/case_dna.py`, `services/legal_reasoning_engine.py`) — verified by grep
in this session, not assumed. This is the single richest per-case source of party names,
addresses, and relationship data, and it reaches OpenAI unscrubbed on every Genome refresh.
**Remediation:** proper fix needs NER, not regex, and remains its own scoped project per the
original finding; minimum viable fix is wiring the existing `_skini_pii` into the Genome path for
at least the categories it already covers. **Complexity:** Medium (existing categories) / Large (names, needs NER).

### SEC-051 — Cohere is an undisclosed subprocessor receiving privileged case text

`app/services/retrieve.py:508-517,1214-1241` (`_cohere_rerank`): sends the user's legal question
**and** retrieved passage text — for owner-namespace hits, the client's own case-document text —
to Cohere's rerank API. Neither `privacy.html` nor `static/dpa.html`'s subprocessor Annex B list
Cohere (confirmed: only Supabase/OpenAI/Pinecone/Render are listed). Five more undisclosed
recipients found in the same sweep: Twilio (SMS, phone + deadline text), Meta/WhatsApp (same),
Viber, the SMTP provider (email + reminder content), Sentry (exception context, PII flag correctly
off). The DPA explicitly promises 30 days' notice before adding a subprocessor; six live recipients
were never announced. **Remediation:** add all six to the public list and DPA Annex B with SCC
status, or disable Cohere (it already falls back cleanly to an internal GPT-based reranker,
`retrieve.py:1220,1239`). **Complexity:** Low (disclose) / Trivial (disable Cohere).

---

## 5. Personal Data (GDPR)

*(Full per-category table from the dedicated agent pass — preserved in full given its density.)*

| PII Category | Storage | Encrypted? | Deletion Complete? | Retention? | Export Available? |
|---|---|---|---|---|---|
| Client name/email/address/phone | `klijenti.*` plaintext columns | ✗ No | ✗ No — deletion never touches `klijenti` | ✗ None | ⚠ Silently empty (SEC-052) |
| Account email/name | `profiles.*` | ✗ No | ⚠ Partial (anonymized string, `auth.users` row retained) | ✗ None | ✓ Yes |
| Lawyer's own phone (SMS/WhatsApp) | `korisnik_sms_profil.telefon` | ✗ No | ✗ **No** — survives account deletion, SMS cron keeps using it | ✗ None | ✗ Neither export |
| JMBG / passport / PIB | `klijenti.*_encrypted` | ✓ AES-256-GCM | ✗ No deletion path | ✗ None | ✗ Deliberately excluded (ciphertext useless anyway) |
| Legacy plaintext JMBG column | `klijenti.jmbg_mb` | ✗ No | ✗ `DROP COLUMN` still commented out | ✗ None | ⚠ Would export plaintext if populated |
| Case/court info | `predmeti`, `predmet_hronohologija`, `rocista` | ✗ No | ✗ **No delete endpoint exists for `predmeti` at all** | ✗ By design (statutory retention) | ✓/⚠ Partial |
| Case documents — vault | Encrypted blob | ✓ Yes | ✗ No delete endpoint; blob orphaned on client soft-delete | ✗ None | ✗ Not exported |
| Case documents — matter uploads | `predmet_dokumenti.tekst_sadrzaj` | ✗ No (SEC-057) | ✗ No delete endpoint anywhere | ✗ None | ⚠ Full text ships in export |
| OCR text | Same as above | ✗ No | ✗ No | ✗ None | ⚠ Same |
| Document text in Pinecone | Chunk metadata, up to 40k chars/chunk | ✗ No | ✗ **No** — only `tmp_*` namespaces are ever cleaned; permanent owner namespaces never deleted by any code path (`api.py` comment confirms this explicitly) | ⚠ TTL for temp only | ✗ Not exported |
| IP addresses | Hashed in audit tables | N/A (hashed) | ✗ Trigger-blocked by design | ⚠ Claimed 2yr, **no enforcing code** | ✗ Not exported |

### SEC-053 — Account deletion leaves phone number and identity row untouched, undisclosed

`routers/gdpr.py:189-206` touches exactly three things: `profiles` (anonymize email/name),
`korisnik_email_notif` (deactivate), and audit entries. **Not touched:** `auth.users` (no
`admin.delete_user` call exists anywhere in the repo), `korisnik_sms_profil` (phone survives, SMS
cron keeps selecting active rows), Pinecone namespaces, Storage buckets, or any PII table. The
response message is honest about case/client retention (a defensible legal position under Zakon o
advokaturi) but does not disclose the surviving phone number or identity row.
**Note:** `docs/security/PUBLIC_SECURITY_CLAIMS.md:45-46`, which said the erasure message itself was
inaccurate, is **stale** — the message is now accurate about what it does say; it just doesn't say
everything. **Remediation:** add SMS/Viber profile deactivation + phone nulling to the deletion
path; add a Pinecone owner-namespace purge or explicitly document why it's retained.
**Complexity:** Low (DB/phone) / Medium (Pinecone).

### SEC-052 — GDPR data export silently ships empty client/comment exports

`routers/data_export.py:73,79` order two of eight exported tables by `created_at` — a column that
does not exist on either `klijenti` or `predmet_komentari` (both use `kreirano`,
`supabase_setup.sql:539,581`). The PostgREST error is caught, logged as a warning, and swallowed
(`data_export.py:44-47`) — **`klijenti.json` and `komentari.json` are empty in every export
produced by this endpoint, with no error surfaced to the user**, while the export's own README
text asserts it contains "svi klijenti." This is a data-loss bug in the Article 20 portability
path, not a design choice — the product cannot currently demonstrate a working portability
response. **Remediation:** fix the two column names; add a fail-loud path (write an `_ERRORS.txt`
into the export ZIP instead of silently dropping a table). **Complexity:** Low (2-line fix) /
Medium (fail-loud + consolidating with the second, competing export endpoint).

### SEC-072 — Soft-deleted client records, including encrypted national ID numbers, are never purged

`klijenti/router.py:505-518` sets `status='soft_deleted'`; nothing anywhere deletes the row or its
`jmbg_encrypted`/`broj_pasosa_encrypted`/`pib_encrypted` fields afterward.
`services/retention_service.py` covers exactly four telemetry tables and explicitly does not touch
`klijenti`. **Remediation:** define and implement a purge/anonymize policy for soft-deleted
clients past N days. **Complexity:** Low (module structure already exists) — the policy decision
is the real work, not the code.

---

## 6. File Security

| Feature | Status | Evidence |
|---|---|---|
| Upload size caps | ✓ IMPLEMENTED (per-endpoint) | 10 different endpoints, 2MB-50MB depending on type |
| Size cap enforced before body read | ⚠ PARTIAL — 1 of 10 endpoints only | `routers/dokument.py:179-181` is the only pre-read check |
| Extension allowlist | ⚠ PARTIAL — absent on `smart_intake` | See SEC-062 |
| MIME/magic-byte verification | ⚠ PARTIAL — 1 of 10 endpoints does real magic-byte checking | See SEC-046 |
| Malware/AV scanning | ✗ MISSING entirely | See SEC-045 |
| Zip-bomb (DOCX) / PDF page-count guards | ✓ IMPLEMENTED | `uploaded_doc/extractor.py:25-106` |
| Temp-file cleanup | ✓ IMPLEMENTED | `try/finally` + `unlink()` at every upload site checked |
| Path traversal | ✓ NOT PRESENT (good) | Only `Path(filename).suffix` used, never a raw join |
| Originals re-served publicly | ✓ NOT PRESENT (good) | Signed URLs, 1h expiry, ownership-checked, private buckets |
| At-rest encryption of originals | ⚠ PARTIAL | Intake yes; portal uploads no (SEC-056) |

### SEC-046 — Content-type trusted from client on 9 of 10 upload endpoints

Only `routers/client_portal.py:549-561` does real magic-byte verification; the other nine
(`dokument.py`, `api.py`'s predmet upload, `smart_intake.py`, `drafting.py`'s playbook,
`law_upload.py`, `auto_discovery.py`, `voice.py`, `import_klijenti.py`, `csv_import.py`) trust
`UploadFile.content_type` (fully attacker-controlled) and file extension. `api.py:4127` even
explicitly allowlists `application/octet-stream`, nullifying its own MIME check.
**Attack:** POST arbitrary binary content as `evil.pdf` with `Content-Type: application/pdf` —
passes both checks, is handed to `pypdf`/`python-docx`/`pytesseract` (all with real CVE history),
and for `smart_intake` persists durably and is later re-downloaded by the lawyer.
**Remediation:** extract the working magic-byte logic already written at
`client_portal.py:549-561` into a shared helper, call it from all 10 sites. **Complexity:** Low.

### SEC-045 — No malware/AV scanning anywhere, including on an unauthenticated upload path

No AV integration exists in application code (confirmed by grep — only a test script that
*simulates* renamed malware). **Most severe concretely:** `POST /api/client-portal/dokument`
requires **no login**, only a portal token, and its magic-byte check accepts anything starting
with `PK\x03\x04` — which includes any ZIP, JAR, or macro-enabled Office file. That file is stored
and later surfaced to the lawyer as a signed download URL. **This makes the product a potential
malware-delivery channel from an unauthenticated third party into a law firm.**
**Remediation:** ClamAV sidecar or storage-triggered scan on both upload buckets before listing
files to the lawyer, with quarantine on hit. **Complexity:** Medium.

### SEC-062 — `smart_intake` accepts any file type/extension, silently defaults to `.pdf`

`routers/smart_intake.py:82-105` validates only size (25MB cap, non-empty) — no content-type or
extension check. `routers/smart_intake.py:512` defaults an unrecognized suffix to `.pdf`, which the
extractor then dispatches on. **Remediation:** apply the same allowlist + magic-byte gate used
elsewhere; reject rather than defaulting. **Complexity:** Low.

### SEC-061 — PDF OCR path has no wall-clock cap; decompression-bomb-adjacent DoS

`_check_docx_zip_safety` covers DOCX only; the 500-page PDF cap has no accompanying time bound. A
500-page scanned PDF at 300 DPI with a 45s-per-page Tesseract timeout can consume **6+ hours of CPU
in a single request**, and with 4 gunicorn workers, a handful of such uploads (each under the
existing 25MB size cap and within the existing 20/minute rate limit) saturates the thread pool.
**Remediation:** cap total OCR wall-clock per document; lower the OCR-path page ceiling
independently of the text-extraction ceiling. **Complexity:** Low.

### SEC-047 — No global request body size cap

No ASGI-level body-size middleware exists; only `routers/dokument.py` checks `Content-Length`
before reading. `POST /api/predmeti/{id}/upload` reads the full body before its own size check;
`POST /api/procena` reads an unbounded raw JSON body with no size limit at all (see also SEC-071).
**Remediation:** ASGI middleware rejecting oversized `Content-Length` globally, before routing.
**Complexity:** Low.

---

## 7. Audit System

*(Full detail in the standalone section drafted during this audit.)*

| Feature | Status | Evidence |
|---|---|---|
| Immutability (no UPDATE/DELETE) | ✓ IMPLEMENTED | DB trigger, `migrations/043_security_bulletproof.sql:33-52` |
| Tamper resistance (hash chain) | ✓ IMPLEMENTED, precisely scoped | Chains action/user/ts/resource fields; **not** the `metadata` payload |
| Append-only guarantee | ✓ IMPLEMENTED | Trigger + chain together |
| Integrity verification tooling | ✓ IMPLEMENTED, was unreliable for 2.5 weeks | `verify_chain_integrity()` itself had 2 bugs, undetected until first live drill (`docs/security/AUDIT_CHAIN_INCIDENT_2026-07-24.md`) — both fixed, disclosed here for calibration |
| Coverage completeness | ⚠ PARTIAL | Hardcoded allow-list, `AUDITABLE_ACTIONS`, ~24 action types |
| AI-decision-level audit | ✗ MISSING | No action type for "an AI call was governed and why" — the exact gap the in-progress Program 1 architecture work targets |
| Login success audit | ✗ Architecturally absent | Auth delegated to Supabase, invisible to this backend |
| Trigger defeatable by table owner | ⚠ Disclosed limitation | `ALTER TABLE ... DISABLE TRIGGER` would defeat it — tamper-evident against app-level attacks, not against a full DB-owner compromise |

**Also confirmed in this pass:** any `log_action()` call with an action string not in
`AUDITABLE_ACTIONS` silently no-ops (`shared/audit_immutable.py:100-102`) — logs a debug line,
writes nothing, raises nothing. This exact bug class (a control that looks live but silently
isn't) has already been found three times in this project's history (SEC-034, SEC-005, the
`/api/cron/daily` collision) — worth naming as a recurring pattern requiring a structural fix
(e.g., a CI check that every `log_action(...)` call site's literal action string is present in
`AUDITABLE_ACTIONS`), not just a fourth one-off catch.

### SEC-050 (widened) — Audit logging covers ~4 path prefixes out of ~596 routes

`shared/audit.py:15,18-19` — the separate lightweight audit middleware covers only
`/api/predmeti`, `/api/klijenti`, `/api/billing`, `/api/firm`/`gdpr`, and only for
`DELETE|PUT|PATCH`. It also silently skips any request outside `/api/` (where `user_id` is never
populated). **Not covered:** every document upload, every AI invocation, all but 2 of 17 admin
config-mutation routes, all evidence/kancelarija-member changes, all API-key usage.
**Business impact:** for a legal SaaS, there is no reconstructable record of who read or exported
which client's documents. **Remediation:** either widen the audit-path allowlist and filter noise,
or add explicit `log_action` calls at the ~30 identified sensitive handlers (the immutable logger
already exists and is proven). **Complexity:** Medium.

---

## 8. Infrastructure Security

| Feature | Status | Evidence |
|---|---|---|
| CORS real allowlist | ✓ IMPLEMENTED | `api.py:903-915` |
| Security headers middleware | ✓ IMPLEMENTED | HSTS, X-Frame-Options, nosniff, Referrer-Policy, CSP |
| CSP without `unsafe-inline` | ✗ MISSING | See SEC-014 (confirmed still open) |
| HTTPS redirect in code | ✗ MISSING | No `HTTPSRedirectMiddleware`; relies on edge TLS termination, unverifiable from repo |
| `TrustedHostMiddleware` | ✗ MISSING | Zero occurrences |
| `SlowAPIMiddleware` registered app-wide | ✗ MISSING — confirmed still open | See SEC-011 below |
| Per-route rate limits | ⚠ PARTIAL | 415/516 routers routes, 29/60 `api.py` routes |
| Rate-limit key spoofable | ✗ MISSING protection | See SEC-048 |
| Redis-backed limiter, fail-open | ✓ IMPLEMENTED | Verified sound |
| Per-user rate limiting + anomaly detection | ✓ IMPLEMENTED (SEC-005 fix, confirmed live in code) | `api.py:961-1074` |
| Global request body cap | ✗ MISSING | See SEC-047 above |
| Server timeouts / worker recycling | ✓ IMPLEMENTED | `gunicorn.conf.py` |
| CI secret/SAST/dependency scanning | ✓ IMPLEMENTED, real and blocking | `.github/workflows/security.yml` |

### SEC-011 (confirmed STILL OPEN, more consequential than previously scoped) — `SlowAPIMiddleware` never registered; the configured default limit is dead code

Verified directly against the installed `slowapi` package source: `app.state.limiter` is set
(`api.py:549`) but `SlowAPIMiddleware` is never added — and per `slowapi`'s own logic, the
`default_limits=["60/hour"]` configured in `shared/rate.py` applies to **zero routes**, decorated
or not, without that middleware registered. **This means 101+31 = 132 routes have no rate limit of
any kind**, including unauthenticated ones that write to the database on every call:
`POST /prijava` (waitlist), `POST /api/security/csp-report`, `POST /viber/webhook`,
`GET /public`/`/incidents` (status page). **Remediation:**
`app.add_middleware(SlowAPIMiddleware)` plus explicit decorators on the unauthenticated routes
named above. **Complexity:** Low, but requires regression testing since it activates a previously
inert default limit globally for the first time.

### SEC-048 — Rate-limit key (`X-Forwarded-For`) is trivially spoofable

`shared/rate.py:47-56` takes the **leftmost** XFF value with no trusted-proxy validation and no
`ProxyHeadersMiddleware`/`forwarded_allow_ips` configured anywhere. **Attack:** sending a random
`X-Forwarded-For` value per request lands each request in a fresh bucket, bypassing all 415
per-route IP limits, including registration (5/minute) and portal upload (5/minute). The
per-user limiter is unaffected (it keys on verified JWT `sub`), but every unauthenticated
IP-based control is defeated. **Remediation:** take the rightmost untrusted hop, or validate
`request.client.host` against the known edge CIDR. **Complexity:** Low.

### SEC-014 (confirmed still open) — CSP allows `unsafe-inline` scripts, plus three fully-trusted CDNs

`api.py:1097`. Combined with SEC-050's audit gap and the free-text sanitization gaps in §10, a
single missed escape becomes unmitigated stored XSS with a CSP that would otherwise have blocked
it. `connect-src` additionally allowlists `api.emailjs.com` as an exfiltration destination.
**Complexity:** Medium (requires an inline-script audit of a 413KB `index.html`).

---

## 9. Database Security

| Feature | Status | Evidence |
|---|---|---|
| FKs from `auth.users`, CASCADE→RESTRICT | ✓ IMPLEMENTED, production-verified | Migration 077, 18 constraints |
| RLS enabled on 143/148 tables | ✓ IMPLEMENTED | — |
| RLS as the actual API enforcement boundary | ✗ MISSING — see SEC-004 | Service-role bypass, confirmed |
| Retention cleanup wired and executing | ⚠ PARTIAL | 4 telemetry tables only, cron schedule itself unverifiable from repo |
| Audit immutability | ✓ IMPLEMENTED | See §7 |
| Soft delete + restore (clients) | ✓ IMPLEMENTED | — |
| Purge of soft-deleted records | ✗ MISSING | SEC-072 |
| Ownership columns backed by real FKs | ⚠ PARTIAL — inconsistent | `predmeti.user_id` has an FK; `klijenti.user_id` and 6+ others do not |
| SQL injection via raw SQL | ✓ NOT PRESENT | No raw string-interpolated SQL anywhere |
| PostgREST filter injection | ⚠ PARTIAL | See SEC-069-search below |

### SEC-060 — Two RLS policies misgranted to PUBLIC instead of service_role

`migrations/007_ingest_jobs.sql:32-34` and `migrations/017_scraper_state.sql:34-36` create
policies **named** `service_role_*` with `USING (true) WITH CHECK (true)` but **no `TO
service_role` clause** — so they apply to `PUBLIC` (`anon`+`authenticated`), unlike the correct
pattern used in migrations 048/049 in the same repo. Whether `anon`/`authenticated` hold table
privileges here is Supabase project state — **unable to verify from implementation**, but the
policy text itself is wrong regardless. **Remediation:** add `TO service_role` to both.
**Complexity:** Trivial.

### SEC-033 (confirmed open, with a new concrete exploit) — Untyped, FK-less owner columns

`klijenti.user_id` (`TEXT`, no FK) and similar columns across 4+ feature areas remain untyped —
already tracked as its own future Integrity Audit initiative. This audit connects it directly to a
live exploit path: SEC-059's mass-assignment bug is only possible because this column accepts any
string with no referential check. **Recommend re-prioritizing `klijenti.user_id` and
`api_kljucevi.user_id` specifically**, ahead of the rest of the deferred census, given the now-
demonstrated exploit path. **Complexity:** Medium per table (needs a live orphan-row check first).

### SEC-069-search — PostgREST filter injection in search endpoints

`routers/search.py:39,58,79` sanitizes only `%` before building an `.or_()` filter string; commas
and parentheses survive and can add conditions inside the OR group. The correct, stricter pattern
already exists in the same codebase (`api.py:3103`) but wasn't applied here. Impact is bounded (the
sibling `.eq("user_id", uid)` prevents cross-tenant reach) but still enables filter-logic
manipulation and cheap unindexed-scan DoS. **Remediation:** reuse the existing `api.py:3103`
regex. **Complexity:** Trivial.

---

## 10. API Security

**Aggregate, whole codebase (22-file deep sample, 100 mutating endpoints):** ownership enforcement
95/100 correct. Raw (non-Pydantic) request bodies: 13 sites. Routes without any rate limit: 132
(see SEC-011).

### SEC-050 — Internal exception text returned to clients on 66+ handlers

`detail=str(e)` or `detail=f"...{exc!r}"` patterns across `routers/benchmarking.py`,
`firm_memory.py`, `memory_graph.py`, `workflow.py`, `admin_dashboard.py`, `dokument.py`,
`law_upload.py`, `export.py`, `billing.py`, and more — 66 sites total, all bypassing the otherwise-
correct global handler (`api.py:851-901`, which properly returns a static message and logs
server-side). Supabase/PostgREST exceptions routinely include table/column/constraint names.
**Attack:** send malformed input, read the returned error to enumerate schema without prior
knowledge, then target discovered tables directly. **Remediation:** mechanical replacement of all
66 sites with a static message + `logger.exception(...)`. **Complexity:** Low-Medium (volume).

### SEC-043 — Integration API keys stored and compared in plaintext

`migrations/019_api_kljucevi.sql:9` — no hash column; lookup is `.eq("kljuc", api_key)` plaintext
equality. The Argon2id primitive this exact use case was built for
(`security/crypto.py:19-20`, docstring names it explicitly) is never called. **Attack:** any read
of this table (backup, service-key leak, future SQL/RLS issue) yields directly usable credentials
for read/write access to customer case data via the integrations API. **Remediation:** store
`sha256(key)`, mirroring the already-correct pattern at `client_portal.py:504`
(`_token_hash`/`token_hash` column). **Complexity:** Low.

### SEC-070 — Viber webhook signature check fails open when unconfigured

`routers/viber.py:113-116`: when `VIBER_AUTH_TOKEN` is unset, the signature check is skipped
entirely rather than rejecting — the inverse of the correct fail-closed pattern already used at
`routers/morning_briefing.py:428-430` in the same codebase. **Remediation:** explicit
"not configured → 503" branch before the signature check. **Complexity:** Trivial.

### SEC-071 — `/api/procena` accepts unbounded free text into a GPT prompt, uncapped and unsanitized

`api.py:3978-3981,4066`: `cinjenice` has no `max_length`, no Pydantic model, no sanitization, and
reaches the prompt in full — contrast the correctly-built sibling `PitanjeReq` (2000-char cap +
sanitize). **Attack:** post several MB of text at the 5/minute limit for direct, uncapped OpenAI
cost amplification. **Remediation:** convert to a validated, length-capped, sanitized model.
**Complexity:** Trivial.

### SEC-069-comparison — Non-constant-time comparisons on admin/cron secret checks

`!=` used instead of `hmac.compare_digest` at ~8 sites (`api.py`, `dokument.py`), while the correct
primitive is already used elsewhere in the same codebase for webhook signatures. Low practical risk
given these routes are otherwise unrated for timing-sample volume — but see SEC-011, which removes
that mitigating factor once rate limiting is fixed. **Complexity:** Trivial.

### Confirmed still accurate: SEC-036 (XSS sanitization sweep) — but coverage remains partial by router count

The bleach-based sanitizer (`security/html_sanitize.py`) is correctly built and used in ~8 routers;
this audit's broader sweep found it absent from `routers/zadaci.py`, `kancelarija.py`,
`firm_memory.py`, `learning.py`, `evidence.py`, `knowledge_base.py`, and others — free-text fields
in these routers rely entirely on frontend `escHtml()` with no server-side backstop, which combined
with SEC-014's CSP gap is a materially higher-risk combination than either alone.

---

## 11. Secrets

| Item | Status | Evidence |
|---|---|---|
| Live secret in git history | ✗ FOUND | SEC-037 |
| Live secrets in working tree | ✓ NONE FOUND | `.env` gitignored, `.env.example` all placeholders |
| Hardcoded secrets in source | ✓ NONE FOUND | Full regex sweep, clean |
| Default credentials | ✓ NONE FOUND | — |
| Admin/debug/cron gates fail closed | ✓ IMPLEMENTED | Consistent pattern |
| API keys hashed before storage | ✗ MISSING | SEC-043 |
| Constant-time comparison | ⚠ PARTIAL | SEC-069-comparison |
| `if DEBUG` security bypass | ✓ NONE FOUND | — |

No additional findings beyond SEC-037 and SEC-043 above; this domain is otherwise well-managed
(env-var-only secrets, fail-closed gates, no test-secret leakage into production code).

---

## 12. Dependencies

| Item | Status | Evidence |
|---|---|---|
| Security-critical packages present | ✓ IMPLEMENTED | cryptography, argon2-cffi, python-jose, bleach, defusedxml, sentry-sdk |
| Pinned versions on core web stack | ✓ IMPLEMENTED | fastapi/starlette/uvicorn/supabase/openai all exact-pinned |
| Loose `>=` on 21 packages | ⚠ PARTIAL | See SEC-067 |
| Lockfile / reproducible builds | ✗ MISSING | No `poetry.lock`/hash-pinned file |
| Automated vuln scanning in CI | ✓ IMPLEMENTED, real | `pip-audit`, blocking |
| Unsafe serialization (pickle/yaml.load/eval) | ✓ NONE FOUND | Clean sweep |
| XXE protection | ✓ IMPLEMENTED | `defusedxml` |

### SEC-067 — Loose version pins on 21 packages, no lockfile

Includes `cryptography>=42.0.0` and `argon2-cffi>=23.1.0` — both on the encryption/auth-adjacent
hot path. `pip-audit` in CI audits the requirements file, not the resolved image, so a vulnerable
transitive dependency satisfying a loose constraint can pass CI and ship. **Remediation:**
`pip-compile`/`uv pip compile` to a hash-pinned lockfile; point Docker build and CI audit at it.
**Complexity:** Low.

### SEC-066 — `python-jose` carries an accepted, unfixed CVE (ignored in CI with rationale)

`PYSEC-2026-1325` (transitive via `ecdsa`) is explicitly ignored in
`.github/workflows/security.yml:23-28` with a documented rationale (no upstream fix exists). This
audit independently verified the actual JWT-handling code has no exploitable algorithm-confusion
issue (each branch pins a matching key type). Residual is a supply-chain posture item, not a
confirmed exploitable defect. **Remediation:** evaluate migrating to `PyJWT` (actively maintained,
no `ecdsa` dependency) to close the advisory legitimately. **Complexity:** Medium.

### SEC-068 — Outbound `httpx` clients constructed with no timeout

`routers/integrations.py:268,342`, `routers/wallet_provenance.py:129` — no `timeout=` set. A hung
third-party endpoint (Google OAuth, a blockchain API) can hold a worker indefinitely.
**Remediation:** explicit `timeout=10.0`. **Complexity:** Trivial.

---

## 13. Logging

*(See §3's SEC-058 for the most severe finding — full PII object logging. Additional items below.)*

| Concern | Status | Evidence |
|---|---|---|
| Raw stack traces to end users | ✓ IMPLEMENTED (global handler) / ✗ (66 bypasses) | See SEC-050 |
| Full user object + PII in logs | ✗ MISSING (leak) | SEC-058 |
| Emails logged at INFO | ✗ MISSING (leak, lower severity) | `api.py:345,2355`; `routers/waitlist.py:176` |
| Client content / LLM output in logs | ✗ MISSING (leak, narrow) | `routers/voice.py:260,522` — 80-120 char previews of dictated speech and AI legal answers, at INFO |
| Full documents/OCR text in logs | ✓ NOT LOGGED (good) | Only counts logged |
| LLM prompts in logs | ✓ NOT LOGGED (good) | Hash-only pattern (`_q_hash`) |
| Log level hardcoded, no env override | ⚠ PARTIAL | `level=logging.INFO` fixed in code |

### SEC-063 (new, cross-cutting) — `SECURITY.md` contains multiple claims directly contradicted by code

Distinct from the internal `docs/security/` corpus (verified accurate everywhere sampled in this
audit, including on uncomfortable items), the repo-root `SECURITY.md` — the document most likely
shown to a prospective customer — makes several claims this audit's own evidence contradicts:

| Claim | Location | Reality |
|---|---|---|
| "Svaka tabela… ima RLS… Nema izuzetaka" | `SECURITY.md:37,39` | 2 tables have none (SEC-060's siblings); RLS bypassed for all app traffic (SEC-004) |
| "Baza podataka (RLS): … baza odbija vraćanje tuđih podataka" | `SECURITY.md:64` | False — service-role bypasses RLS entirely |
| "Svi korisnički nalozi koriste Argon2id" | `SECURITY.md:29` | Zero call sites; auth is Supabase-delegated |
| "Putanje u storage-u su randomizovane UUID vrednosti" | `SECURITY.md:88` | True for 3 buckets, false for `portal-uploads` (SEC-056) |
| Live two-account cross-tenant test claimed | `SECURITY.md:66` | No such test exists; only source-level assertions |

**Remediation:** reconcile `SECURITY.md` with `docs/security/PUBLIC_SECURITY_CLAIMS.md`, which
already states the accurate version of most of these. **Complexity:** Trivial (it's a rewrite, not
a code change) but should not wait, since this is the document most exposed to external scrutiny.

---

## 14. Privacy Architecture

| Capability | Status | Evidence |
|---|---|---|
| EU-only processing / data residency | ✗ MISSING | No region config/assertion anywhere; Azure-EU fallback is env-gated and silently degrades to global OpenAI on any error |
| Tenant isolation | ⚠ PARTIAL | App-layer only (SEC-004); Pinecone firm-namespace has **no per-matter filter** — see SEC-054 |
| Data minimization toward third parties | ⚠ PARTIAL | See §4 |
| Purpose limitation | ⚠ PARTIAL | Legal-basis field recorded (`klijenti.pravni_osnov_obrade`) but **nothing reads it** — no gate anywhere checks it before processing |
| Subprocessor transparency | ⚠ PARTIAL | 6 live recipients undisclosed — SEC-051 |
| AI provider transparency | ⚠ PARTIAL | Provider/model set is enumerable from code; no per-request payload/egress inventory exists |

### SEC-054 — No ethical-wall / cross-matter isolation in AI retrieval within a firm

`app/services/retrieve.py:1685-1690` queries the firm's shared Pinecone namespace filtered only by
document `type` — **no `predmet_id`, no per-matter access list.** A firm member analyzing Matter A
can receive document chunks from Matter B in the same firm, including a matter involving an
adverse party the firm also represents. `check-conflict` (`klijenti/router.py:567`) screens client
*intake*, not AI *retrieval* — there is no code path connecting the two. For any firm above solo
size, this is a professional-conduct problem, not merely a privacy one, and is one of the two
disqualifying findings for medium+ firm and court/government deployment (§15).
**Remediation:** add `predmet_id`/allowed-matter-list to the Pinecone metadata filter; gate
cross-matter retrieval behind an explicit firm policy setting. **Complexity:** Low.

### SEC-064 — No data-residency guarantee is expressible in code

Supabase/Pinecone are addressed by opaque URL/host with no region validation anywhere. The one
EU-processing mechanism (Azure OpenAI monkeypatch, `shared/ai_client.py:36-84`) is env-gated,
empty in `.env.example`, and **silently falls back to standard global OpenAI if the patch throws**
— so "EU processing" is a deployment-time coin flip today, not an architectural guarantee.
`privacy.html` itself states Pinecone is US `us-east-1`. **Remediation:** startup assertion of
region config for both Supabase and Pinecone, logged and exposed on an internal status page; treat
Azure-OpenAI as a verified first-class mode, not a silent fallback. **Complexity:** Low-Medium.

### SEC-065 — Recorded legal basis for processing is never enforced

`klijenti.pravni_osnov_obrade` is a real, well-designed field (CHECK-constrained, default-set,
consent-date-tracked) — more than most products record. **Nothing in the codebase reads it.** The
AI-processing pipeline (upload → embed → LLM) executes regardless of the recorded basis, even
though `privacy.html` assigns AI processing specifically to the *consent* basis.
**Remediation:** enforce the field at the AI-processing gate (a natural fit for the same chokepoint
proposed for SEC-055/SEC-006). **Complexity:** Medium.

---

## 15. Enterprise Readiness

| Customer Segment | Suitable? | Why |
|---|---|---|
| **Solo lawyer** | ✓ Yes, with disclosure | Namespace-per-user isolation applies cleanly (SEC-054 requires firm membership); identifier encryption and vault-document encryption are real and correctly built; residual risks (plaintext case-body text, no per-document delete, undisclosed subprocessors) are ones a solo practitioner can rationally accept *if told* — condition on disclosure, not on a code fix |
| **Small law office (2-5)** | ⚠ Conditional | Same protections hold; the shared firm namespace has no per-matter filter, acceptable only if the office already treats all matters as internally shared — breaks the moment the office takes both sides of related disputes, with no product mechanism to prevent it |
| **Medium law firm (10-50)** | ✗ No | Three blockers: no ethical wall (SEC-054), no matter/document deletion path anywhere in the repo, and a DPA that omits 6 live subprocessors (SEC-051) |
| **Large law firm (50+)** | ✗ No | All of the above, plus: isolation has no database-level backstop (SEC-004) — at this scale, a single missed `.eq()` in any of ~100 router files is a full cross-tenant breach; no matter-level ACLs, no SSO/SCIM, retention covers only telemetry with no committed production scheduler |
| **Government institution** | ✗ No | Decisive: no data-residency guarantee is expressible in code (SEC-064); Pinecone is documented US-hosted; the erasure endpoint leaves the phone number and identity row intact (SEC-053) |
| **Court** | ✗ No | Everything above, plus SEC-054 is disqualifying on its own — a court information system cannot allow one proceeding's text into another's AI context with only a document-type filter standing between them |
| **Highly regulated enterprise** | ✗ No | Diligence stops at: privileged document text stored plaintext while marketing states otherwise (SEC-057), the classification framework that would govern this is dead code (SEC-055), and the GDPR portability export silently ships empty for two of eight tables (SEC-052) — a controls-testing failure |

**Minimum set to unlock medium firms:** SEC-054 (matter-scoped retrieval filter, Low), a real
matter/document delete path (Medium), completed subprocessor annex (Low), SEC-052 fixed with
fail-loud behavior (Low).
**Additional minimum to unlock government/court/regulated:** SEC-064 (asserted EU residency,
Medium), SEC-057 (document-text encryption, High), RLS made load-bearing (High, long-term).

---

## Security Score

Scored 0-100 per dimension, reflecting **implementation only** — not stated intent, not documents,
not what a future revision would achieve. A dimension with strong primitives but narrow/inconsistent
application scores in the 50s-60s, not the 80s, because inconsistent application is exactly the
theme a real incident would exploit.

| Dimension | Score | Rationale |
|---|---|---|
| Authentication | 62 / 100 | Solid JWT verification and machine-auth patterns; but MFA is a false public claim, logout/revocation is dead code, and core login security is entirely unverifiable from this repo |
| Authorization | 58 / 100 | 95% ownership-check discipline on sampled endpoints is genuinely strong; pulled down hard by SEC-038 (pending confirmation) and SEC-041/059/039/040 — the failures are narrow but severe |
| Privacy (AI + GDPR + architecture combined) | 45 / 100 | Real, thoughtful primitives (legal-basis field, `_q_hash`, PII-free query log) undermined by an undisclosed subprocessor receiving privileged text, an ethical-wall gap, and a silently-broken portability export |
| Encryption | 55 / 100 | The primitive itself (AES-256-GCM, fail-fast key validation) is excellent; coverage is narrow — the highest-value content (case-document full text) is exactly what's uncovered |
| GDPR | 40 / 100 | Deletion, retention, and export are each partially real but none is complete; the export bug is a controls-testing failure a regulator would specifically look for |
| Infrastructure | 60 / 100 | CORS/headers/CI scanning are genuinely good; the rate-limiter middleware gap (SEC-011) and spoofable IP key (SEC-048) mean the abuse-control story is largely theoretical for unauthenticated traffic |
| Application Security | 55 / 100 | Ownership discipline is strong; exception-leak volume (66+ sites) and the two live IDOR/mass-assignment findings pull this down |
| AI Privacy | 48 / 100 | Structural, comprehensive injection defense is a real strength; PII scrubbing is regex-only, misses names entirely, and misses the single richest AI-input path (Genome) completely |
| Auditability | 65 / 100 | The immutability mechanism itself is well-engineered and independently strong; coverage is narrow (4 path prefixes of ~596 routes) and there is no AI-decision-level audit yet |
| Enterprise Readiness | 35 / 100 | Suitable for solo/small practice with disclosure; not suitable for medium+ firms today on ethical-wall and deletion grounds alone, before residency/encryption gaps for regulated/government buyers |
| **Overall** | **52 / 100** | A codebase with real security engineering capability, inconsistently and incompletely applied — most severe individual findings are narrow and fixable at Low-Medium complexity, not evidence of fundamental architectural failure |

---

## Gap Register

*Severity: Critical / High / Medium / Low. Likelihood reflects exploitability as verified from
code alone (not live-tested), per each finding's own stated verification limits.*

| ID | Severity | Summary | Impact | Likelihood | Fix | Complexity |
|---|---|---|---|---|---|---|
| SEC-037 | Critical | Live OpenAI key in git history | Billing fraud | High (any clone) | Rotate + purge history | Trivial / Medium |
| SEC-038 | Critical* | `profiles` self-update, no column restriction | Free entitlement escalation | Unconfirmed live, policy unambiguous | Column-restrict + RPC pattern | Low |
| SEC-039 | High | Document-session IDOR | Privileged doc read cross-tenant | Medium (needs ID disclosure) | Bind session to owner | Medium |
| SEC-040 | High | Intake entity cross-tenant write | Falsified legal deadlines | Medium | Scope query to `uploaded_by` | Low |
| SEC-041 | High | Global role assignment, no tenant bound | Cross-firm privilege manipulation | Medium (requires PARTNER role) | Add firm-boundary check | Medium |
| SEC-054 | High | No ethical wall in AI retrieval | Cross-matter privileged leak within firm | High (any firm member) | Matter-scoped filter | Low |
| SEC-056 | High | Portal uploads unencrypted, path discloses IDs | Evidence exposure on infra compromise | Low (needs infra access) | Encrypt, matching sibling paths | Low |
| SEC-057 | High | Case document text plaintext | Privileged content exposure at rest | Low (needs DB/replica access) | Encrypt or reclassify claim | Medium-High |
| SEC-059 | High | Mass assignment, `klijenti.user_id` | Cross-tenant CRM write | Medium | Enforce whitelist + FK | Trivial / Medium |
| SEC-011 | High | `SlowAPIMiddleware` never registered | 132 routes fully unrated incl. unauth DB writers | High | Register middleware + decorate | Low |
| SEC-004 | High (architectural) | RLS bypassed for all app traffic | No DB backstop for any tenant boundary | Standing fact | Ownership-check consolidation; longer-term client split | Large |
| SEC-042 | Medium-High | Logout/revocation dead code | Sessions can't be terminated via product | Medium | Wire logout; reject on empty user | Low |
| SEC-043 | Medium | Integration API keys plaintext | Full API access on any DB read | Low (needs DB access) | Hash, mirror existing pattern | Low |
| SEC-045 | Medium-High | No malware scanning, one path unauthenticated | Malware delivery via product | Medium | AV scan + quarantine | Medium |
| SEC-046 | Medium | Content-type trusted on 9/10 uploads | Parser-exploitation surface | Medium | Shared magic-byte helper | Low |
| SEC-048 | Medium-High | Rate-limit key spoofable | All IP-based unauth controls bypassable | High | Fix XFF trust | Low |
| SEC-050 | Medium | 66+ handlers leak exception text | Schema/internal disclosure | High | Static messages + server log | Low-Medium |
| SEC-051 | Medium-High | Cohere undisclosed subprocessor | Compliance/DPA breach, privileged text to 3rd party | Standing fact | Disclose or disable | Low / Trivial |
| SEC-052 | Medium | GDPR export silently empty (2 tables) | Broken Art. 20 response | Standing fact | Fix column names + fail loud | Low |
| SEC-053 | Medium | Deletion leaves phone/identity row | Incomplete Art. 17 response | Standing fact | Extend deletion scope | Low |
| SEC-055 | Medium | Data classification is dead code | False sense of AI-input protection | Standing fact | Wire in or delete + correct docs | Low |
| SEC-058 | Medium-High | Full user object + PIB logged at INFO | PII in low-trust log store | High (every request) | Delete 2 log lines | Trivial |
| SEC-060 | Medium | 2 RLS policies misgranted to PUBLIC | Depends on live grants | Unable to verify live | Add `TO service_role` | Trivial |
| SEC-061 | Medium | Unbounded PDF OCR wall-clock | Worker-pool DoS | Medium | Cap OCR time/pages | Low |
| SEC-062 | Medium | `smart_intake` no type/ext validation | Same class as SEC-046 | Medium | Apply existing gate | Low |
| SEC-063 | Medium-High | `SECURITY.md` contradicts code on 5+ claims | External trust/diligence risk | Standing fact | Reconcile with internal docs | Trivial |
| SEC-064 | Medium | No expressible EU residency guarantee | Blocks regulated/gov't deployment | Standing fact | Region assertion + fix silent fallback | Low-Medium |
| SEC-065 | Medium | Legal-basis field never enforced | Purpose-limitation gap | Standing fact | Gate AI processing on it | Medium |
| SEC-066 | Low-Medium | `python-jose` accepted CVE (supply chain) | Theoretical, code path itself verified safe | Low | Evaluate PyJWT migration | Medium |
| SEC-067 | Medium | Loose pins, no lockfile | CI audits requirements, not resolved image | Standing fact | Hash-pinned lockfile | Low |
| SEC-068 | Low | Outbound httpx no timeout | Worker hang on 3rd-party outage | Low | Add timeout | Trivial |
| SEC-069-search | Low-Medium | PostgREST filter injection (bounded) | Filter manipulation, own-tenant only | Low | Reuse existing regex fix | Trivial |
| SEC-069-comparison | Low | Non-constant-time secret comparisons | Timing side-channel, needs SEC-011 fixed first to matter | Low | `hmac.compare_digest` | Trivial |
| SEC-070 | Medium | Viber webhook fails open if unconfigured | Unauthed data injection if env misconfigured | Low (config-dependent) | Fail closed | Trivial |
| SEC-071 | Medium | `/api/procena` unbounded/unsanitized input | Cost amplification | Medium | Validate + cap + sanitize | Trivial |
| SEC-072 | Medium | Soft-deleted clients never purged | Retention/erasure gap, incl. encrypted national IDs | Standing fact | Define + implement purge policy | Low |
| SEC-073 | Low-Medium | Dead RBAC/agent-isolation modules | False impression of enforcement | Standing fact | Delete or wire in | Low |
| SEC-006 | Medium-High (confirmed open) | PII scrub misses names + entire Genome path | Party PII reaches OpenAI unscrubbed | High (every Genome refresh) | NER-based fix (Large); wire existing categories into Genome path (Medium, interim) | Medium/Large |
| SEC-024 | Medium (confirmed open) | No key rotation | Single-key blast radius on any disclosure | Standing fact | Implement per existing design doc | Low-Medium |
| SEC-026 | Low-Medium (confirmed open) | Hardcoded JWKS fallback, duplicated | Stale-key trust on rotation | Low | `kid`-match, single source | Low-Medium |
| SEC-014 | Medium (confirmed open) | CSP `unsafe-inline` | Weakens XSS mitigation | Standing fact | Nonce/hash-based CSP | Medium |
| SEC-033 | Medium (confirmed open, new exploit linked) | Untyped FK-less owner columns | Enables SEC-059 | Standing fact | Prioritize `klijenti`/`api_kljucevi` | Medium |
| SEC-045-admin | Medium | Admin authority = mutable email claim | Escalation if email-change unconfirmed | Unable to verify live | DB-backed role | Medium |

*SEC-038's severity is provisional pending the recommended 30-second live confirmation; the
underlying policy defect is unambiguous regardless of that test's outcome.*

---

## Prioritization

### Phase 1 — Critical issues preventing any further enterprise conversation

Do these regardless of roadmap; several are same-day fixes.
1. SEC-037 — rotate the exposed OpenAI key now; audit usage since the commit date.
2. SEC-038 — live-confirm, then fix the `profiles` UPDATE grant.
3. SEC-011 — register `SlowAPIMiddleware`; this single line closes the widest live abuse surface in the report.
4. SEC-048 — fix the spoofable rate-limit key (pairs with #3; fixing one without the other leaves the abuse surface open).
5. SEC-059 / SEC-040 / SEC-039 — the three concrete cross-tenant IDOR/mass-assignment paths; all Low-Medium complexity.
6. SEC-058 — delete the two PII-dumping log lines (trivial, highest value-per-effort item in the whole report).
7. SEC-054 — matter-scoped Pinecone retrieval filter; this alone unblocks the ethical-wall objection for every firm-size segment above solo.

### Phase 2 — Privacy and GDPR improvements

8. SEC-052 — fix the two broken export column names, add fail-loud behavior.
9. SEC-053 — extend account deletion to phone/SMS profile.
10. SEC-051 — disclose (or disable) Cohere and the five other undisclosed subprocessors.
11. SEC-006 — wire existing PII-scrub categories into the Case Genome path (interim fix; full NER-based name masking is a separate, larger project).
12. SEC-065 — enforce the recorded legal-basis field before AI processing.
13. SEC-064 — assert data residency in code; stop the silent Azure-OpenAI fallback.
14. SEC-072 — define and implement a soft-delete purge policy.
15. SEC-055 — wire `data_classification.py` into the AI chokepoint, or delete it and correct the Architecture Bible.

### Phase 3 — Enterprise hardening

16. SEC-057 — encrypt case-document text (largest single engineering lift in this report; needs a search-architecture decision first).
17. SEC-004 / AUTHORIZATION_PATTERN_RECOMMENDATION — build the consolidated ownership-check dependency and migrate the ~15 call sites.
18. SEC-024 — implement key rotation per the existing design document.
19. SEC-014 — migrate off CSP `unsafe-inline`.
20. SEC-067 — hash-pinned dependency lockfile.
21. SEC-043 / SEC-056 — hash integration API keys; encrypt portal uploads (both mirror already-correct patterns elsewhere in the codebase — mechanical once scheduled).
22. SEC-050 — clean up the 66+ exception-leak sites.
23. SEC-063 — reconcile `SECURITY.md` with the accurate internal claims corpus.
24. SEC-041 / SEC-045-admin — tenant-bound role assignment; DB-backed admin role.
25. Remaining Low/Trivial items (SEC-042, SEC-046, SEC-060-062, SEC-068-071, SEC-073, SEC-026) — batch as a hardening sprint; each is independently cheap and none blocks the items above.

---

## Cross-cutting notes

- **This project's internal `docs/security/` corpus (Gap Register, Maturity Dashboard, STRIDE
  model, Public Claims Policy) was independently verified accurate against code everywhere sampled
  in this audit, including on its own uncomfortable findings.** The repo-root `SECURITY.md`
  (SEC-063) is the one document that has drifted from that standard — worth fixing first among the
  documentation items precisely because it's the one most likely to be shown externally.
- **Two duplicated implementations produce divergent security behavior**, flagged by one of the
  audit passes as worth architectural attention beyond any single fix: `api.py` and
  `shared/deps.py` each carry an independent copy of `_verify_token` (with different JWKS-fallback
  and logging behavior), and two separate `Limiter` instances exist with no shared counters —
  already acknowledged as known duplication in `shared/rate.py`'s own docstring.
- **This audit's own limits, stated per this report's own rubric:** live Supabase/Render
  configuration (password policy, login rate limiting, RLS grants beyond what migrations show, MFA
  settings, PITR/backup status, actual cron scheduling) is **unable to verify from
  implementation** throughout this report, and is flagged inline wherever it bears on a finding's
  severity. Frontend `static/vindex.js`'s ~500+ render sites were not exhaustively audited for
  escaping discipline — only the backend sanitization gate was assessed.
