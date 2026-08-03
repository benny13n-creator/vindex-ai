# Mission Keystone — Phase 6: Security Final Check (Investigation)

**Scope**: read-only, adversarial re-verification for closed-beta readiness. Not a repeat of the full
2026-08-02 forensic audit or the 2026-07-26 Enterprise Security Governance suite — this targets what
would actually block real lawyers/real client data going into the system.

---

## 1. Authentication — **Solid**

`shared/deps.py::get_current_user` (line 271):
- `Depends(security)` where `security = HTTPBearer(auto_error=False)` — missing credentials → explicit
  401 (`shared/deps.py:276-281`), not a silent pass-through.
- `_verify_token` (line 216): tries Supabase SDK `auth.get_user()` first (live revocation check), falls
  back to `verify_token_local` (line 158) — cryptographic HS256 (with `SUPABASE_JWT_SECRET`) or RS256/ES256
  (via JWKS, 1h cache, hardcoded **public**-key fallback if JWKS fetch fails — not a secret, so this
  fallback is safe, just a staleness risk if Supabase ever rotates keys).
- No algorithm-confusion hole: the code branches on the token's own declared `alg` and only accepts it
  via the matching verification path with an explicit `algorithms=[...]` allowlist (`deps.py:183-211`) —
  a forged token can't force acceptance via `alg: none` or mismatched key type.
- Invalid/expired token → explicit 401 with a distinct reason logged to `login_failed` audit
  (`deps.py:282-290`).
- Spot-checked a sample of `@router.` definitions across `routers/*.py` for missing
  `Depends(get_current_user)` — cron/webhook endpoints correctly use the separate `X-Cron-Secret`/
  `X-Cron-Key` mechanism instead (see §7), not an oversight.

**Verdict: Solid.**

---

## 2. Authorization / Tenant Isolation — **Solid, with one architecture note**

The FastAPI backend's Supabase client is constructed with `SUPABASE_SERVICE_KEY` (`shared/deps.py:80`)
— the **service role key, which bypasses RLS entirely** at the Postgres level. This means, for every
table the backend itself queries, **RLS is not the active enforcement mechanism** — the application's
own `.eq("user_id", uid)` (or equivalent) filter at each call site is. This is architecturally
consistent across the whole app (hundreds of call sites), not a new observation, but worth stating
explicitly: a single missed `.eq("user_id", ...)` in any backend query is a full cross-tenant leak with
**no DB-level backstop** for that call site, because the service-role connection ignores RLS.

Checked whether the **frontend** ever talks to Supabase directly (which would make RLS the *actual*
enforcement layer for those tables): `static/vindex.js:242` does
`window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)` using the anon/publishable key (correct
key type for client-side exposure). Direct frontend `.from(...)` calls found: `profiles`, `conversations`,
`reported_errors` only (`static/vindex.js` grep) — **not** `predmeti`, `predmet_dokumenti`, `klijenti`,
`zadaci`, `proactive_alerts`, or `billing_entries`. Those 6 core tables are only ever touched via the
backend's service-role connection.

RLS is nonetheless enabled and correctly scoped on the core tables — traced to `supabase_setup.sql`
(the original base schema, predating the `migrations/` directory, which is why a `migrations/*.sql` grep
alone misses it): `predmeti` (line 292, `auth.uid() = user_id` on SELECT/INSERT/UPDATE/DELETE, lines
298-322) and `predmet_dokumenti` (line 348, same pattern, lines 354-378). `klijenti` (migration 078),
`zadaci` (045), `proactive_alerts` (036), `billing_entries` (003), `predmet_klijenti` (014) all confirmed
RLS-enabled with matching `CREATE POLICY` statements.

**Verdict: Solid** — defense-in-depth (RLS) is correctly in place on every core table, and the
frontend's own direct-access surface (profiles/conversations/reported_errors) is correctly scoped to the
tables where RLS is actually the enforcing layer. The single-point-of-failure risk (one missed
`.eq("user_id", ...)` = cross-tenant leak, no RLS backstop for backend-originated queries) is not a bug,
it's the existing, unavoidable shape of a service-role-key architecture — flagged for awareness, not as
a defect to fix before beta.

---

## 3. Sensitive Data Handling — **Needs Attention (Low-Medium)**

- No hardcoded secrets or obvious plaintext-PII logging found in a targeted grep of `logger.info/debug`
  calls near document/case content in `routers/evidence.py`, `routers/case_dna.py`, `api.py`'s upload
  path — log lines reference IDs/counts/status, not raw `tekst_sadrzaj` or client PII fields.
- `routers/gdpr.py::gdpr_delete_account` hashes the original email before audit-logging it
  (`hashlib.sha256(email.encode()).hexdigest()[:16]`, line 203) — good practice, doesn't audit-log PII
  in cleartext.
- Not independently re-verified this pass: whether error-tracking/Sentry integration
  (`tests/test_faza2_resilience_sentry_2026_07_24.py` references `capture_exception`) ever receives
  exception context containing raw document text or client PII in `extra=`/`context=` fields — worth a
  dedicated check, not done here (time-boxed scope).

**Verdict: Needs Attention** — nothing found that's actively leaking PII, but the Sentry-payload
question above is a real gap in this pass's coverage, not a cleared item.

---

## 4. Audit Immutability — **Solid**

DB-level protection confirmed, not just app-level: `migrations/043_security_bulletproof.sql:49-51`
creates `trg_protect_audit_immutable`, a `BEFORE UPDATE OR DELETE` trigger on `audit_immutable` that
`RAISE EXCEPTION`s on any modification attempt (lines 40-43) — this holds even against a client using the
service-role key directly (e.g. via the Supabase dashboard SQL editor), since Postgres triggers fire
regardless of the calling role's privilege level (unless the role is literally `BYPASSRLS`+superuser,
which the app's service key is not). `migrations/044_anomaly_detection.sql:51` confirms the same
protection pattern extended to a second table. `migrations/081_audit_immutable_prev_hash_unique.sql`
adds a uniqueness constraint on the hash-chain's `prev_hash`, closing a chain-forking gap.

**Verdict: Solid.**

---

## 5. GDPR Lifecycle — **Critical Gap — the single most important finding of this phase**

Prior mission summaries (carried in memory as `project_night_shift_2026_08_02.md`'s Mission Ledger
section) describe `services/retention_service.py` as "the legitimate GDPR-driven deletion" mechanism.
**This characterization is not accurate for user-initiated erasure**, and this phase corrects it:

- `services/retention_service.py` (read in full) implements **scheduled TTL cleanup of operational logs
  only** — `security_events`, `user_daily_activity`, `ai_forensics`, and Pinecone **tmp buffers** (lines
  62-140). It has no code path tied to a specific user's erasure request; it runs on a schedule against
  everyone's old operational telemetry.
- The actual user-facing erasure endpoint is `routers/gdpr.py::gdpr_delete_account`
  (`DELETE /api/gdpr/account`, line 171). Read in full (lines 171-215): it **only**:
  1. Overwrites `profiles.email`/`profiles.full_name` with an anonymized placeholder.
  2. Deactivates `korisnik_email_notif`.
  3. Writes an audit log entry.
- It does **not** touch, delete, or anonymize: `predmeti` (case records), `klijenti` (client PII — JMBG,
  PIB, financial data), `predmet_dokumenti` (full document text via `tekst_sadrzaj`), Pinecone vector
  embeddings derived from the user's documents, Supabase Storage files (uploaded PDFs), `billing_entries`,
  `zadaci`, or `proactive_alerts`.
- Repo-wide grep for any cascading-deletion implementation (`delete_all_user_data`, `cascade.*user_id`,
  Pinecone-delete-by-user, etc.) found **nothing** beyond this one endpoint and the word "erasure" in an
  audit-log action name.
- Consequence: the `user_id` foreign key linking all of the above tables is **never changed or removed**
  by "erasure" — every one of the user's cases, client records, and uploaded documents remains fully
  intact and fully attributable to that same `user_id` after "deletion." A user (or their firm's client)
  exercising GDPR Article 17 (Right to Erasure) would receive a false assurance: the account *login*
  identity is anonymized, but the underlying legal case data — the actually sensitive content for a
  legal-tech product — is not erased at all.

**This is a genuine, previously mis-characterized gap**, not a new bug introduced by any recent mission —
it appears to have been the erasure implementation's actual scope all along, just described inaccurately
in a prior mission's summary. Flagging per Keystone's explicit mandate to correct inaccurate prior
findings.

**Verdict: Critical Gap** (compliance/legal-liability risk for a product whose entire premise is handling
confidential legal case data under an explicit GDPR promise — not an active security breach, but a false
compliance claim, which for a legal-tech product is itself a serious liability).

---

## 6. Secret Exposure — **Solid, previously-known findings confirmed resolved**

- Grepped the live source tree (excluding `data/`, `.git`, `migrations/`) for `sk-...`/`sk-ant-...`/
  `sb_secret_...` patterns: **zero matches** in actual app code.
- `.gitignore` correctly excludes `.env`, `.env.local`, `.env.production`, explicitly exempting only
  `.env.example` (a template). Confirmed `.env` itself is not tracked (`git ls-files` shows only
  `.env.example`).
- `.env.example` contains only placeholder values (`sk-proj-...`, `pcsk_...`, `change-me-to-a-long-
  random-value`, etc.) — no real secret material.
- The 2026-08-02 forensic audit's "exposed OpenAI key" urgent finding: **confirmed resolved** — no
  hardcoded key found anywhere in the current tree, and `.env` hygiene is correct. (Could not verify
  against the actual key material whether the originally-exposed key was rotated on OpenAI's side —
  that's outside what a code-only check can confirm; flagged as a founder-verification item, not a code
  gap.)
- The 2026-08-02 "profiles RLS gap" urgent finding: `migrations/078_sec034_klijenti_komentari_policies.sql`
  and related SEC-034 migrations show RLS policy work on `klijenti`; profiles-table RLS itself was not
  separately re-traced this pass (out of this investigation's specific file list) — **not independently
  re-confirmed**, flagged rather than asserted.

**Verdict: Solid** for the specific "hardcoded secret in code" and ".env hygiene" checks; the profiles
RLS sub-item is explicitly unconfirmed, not cleared.

---

## 7. API Protection — **Solid**

- All `BRIEFING_CRON_SECRET`-protected endpoints checked (`api.py:1502` `/api/cron/daily`,
  `routers/morning_briefing.py:424` `/api/briefing/cron`, `routers/morning_briefing.py:690`
  `/api/briefing/nightly-intelligence`, `routers/workflow.py:562`, `routers/zakon_monitoring.py:290`) use
  the identical fail-closed pattern: `if not cron_secret or x_secret != cron_secret: raise
  HTTPException(...)`. An unset env var locks the endpoint rather than opening it — the exact class of
  bug Project Sentinel's "Fail CLOSED" fix (2026-07-25) addressed, and it has not regressed anywhere.
- `routers/email_notif.py`/`routers/whatsapp_notif.py` use a parallel `CRON_SECRET`/`X-Cron-Key`
  mechanism (`_CRON_SECRET = os.getenv("CRON_SECRET", "")`) — also fails closed (`if _CRON_SECRET and
  cron_key == _CRON_SECRET`; an empty `_CRON_SECRET` makes the condition False, correctly rejecting).
- **SEC-002's original "/api/cron/daily routing collision"**: re-verified — grepped the entire codebase
  for any other registration of the literal route `/api/cron/daily`. Found exactly **one**
  (`api.py:1502`). `routers/proof.py:284` has a live self-test hitting this exact URL. **Confirmed
  fixed, no collision remains.**
- Minor, Low-severity note: the secret comparisons (`x_secret != cron_secret`, `cron_key ==
  _CRON_SECRET`) use plain Python string comparison, not a constant-time compare
  (`hmac.compare_digest`). Theoretically a timing side-channel; practically very low risk given network
  jitter dominates any timing signal for a remotely-invoked cron endpoint, and the secrets are
  high-entropy random strings, not guessable in a realistic number of attempts. Worth a trivial hardening
  pass, not a beta blocker.
- Rate limiting (`shared/rate.py`/slowapi `@limiter.limit(...)`) present and previously verified fail-open
  correctly (`tests/test_sec005_failopen_limiter.py`) — not re-traced in full this pass, but no
  contradicting evidence found.

**Verdict: Solid.**

---

## Summary for parent

**One Critical-severity finding**: GDPR "account deletion" (`routers/gdpr.py::gdpr_delete_account`)
anonymizes only the login profile — it does not delete or anonymize `predmeti`, `klijenti`,
`predmet_dokumenti`, Pinecone vectors, or Storage files. This corrects a prior mission's inaccurate
characterization of `services/retention_service.py` as the GDPR-erasure mechanism (that service only
does scheduled operational-log TTL cleanup, unrelated to user-initiated erasure). This is a compliance/
legal-liability risk, not an active cross-tenant breach.

**Everything else checked this pass is Solid**: authentication (JWT verification, algorithm-confusion-
safe, fails closed), tenant isolation (RLS correctly present on all 6 core tables, traced to
`supabase_setup.sql` for `predmeti`/`predmet_dokumenti` which predates `migrations/`), audit immutability
(DB-level trigger, not just app-level), secret hygiene (no hardcoded keys, correct `.gitignore`), and API
protection (all cron endpoints fail-closed, SEC-002's routing collision confirmed fixed — only one
`/api/cron/daily` registration exists).

**2026-08-02 urgent findings status**: exposed OpenAI key — confirmed resolved in code (key rotation
itself not independently verifiable from code alone, flagged as a founder-side check). Profiles RLS gap —
not independently re-confirmed this pass (out of this investigation's specific scope), flagged as
unconfirmed rather than cleared.

**Needs Attention (not Critical)**: whether Sentry/error-tracking payloads could carry raw document
text/PII in exception context — not checked this pass.
