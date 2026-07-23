# Vindex AI — Public Security Claims

**Date:** 2026-07-23
**This is the most important document of the audit.** Every claim in List A has direct code evidence and is safe to say publicly today, with the exact scope stated — do not broaden the wording beyond what's written here. Every claim in List B must not be published until the underlying Gap Register item is closed and re-verified. Source: `SECURITY_DUE_DILIGENCE_REPORT.md`, `SECURITY_GAP_REGISTER.md`.

---

## LIST A — Claims Vindex AI may publish today

✔ **"Sensitive personal identifiers (JMBG, passport number, PIB) are encrypted at rest using AES-256-GCM authenticated encryption."**
Evidence: `security/crypto.py:139-155` (correct AES-256-GCM, random nonce per encryption), applied at `klijenti/router.py:220-225,429-434` for manually-created/updated client records.
**Caveat — do not publish until SEC-009 is fixed:** the bulk CSV/XLSX client-import path (`routers/import_klijenti.py`) currently does not apply this encryption. Publishing this claim before SEC-009 closes would overstate its scope. Once fixed, the claim applies without qualification.

✔ **"All audit log entries are immutable — protected by a database-level trigger that blocks modification or deletion, even for the application's own service account, not just by application-layer convention."**
Evidence: `migrations/043_security_bulletproof.sql:33-52` (`protect_audit_immutable()` trigger, `SECURITY DEFINER`, raises on any `UPDATE`/`DELETE`), `:59-61` (RLS additionally blocks direct `SELECT`). This is genuinely strong and safe to say exactly as scoped — do not broaden to "all data is immutable" or "full audit coverage," which would not be supported (see List B).

✔ **"Vindex AI uses parameterized database queries throughout — there is no raw SQL string-concatenation in the codebase, which structurally prevents SQL injection."**
Evidence: repo-wide search found zero raw SQL execution in reachable application code; all 14 `.rpc()` calls use dict-based parameters, never string interpolation.

✔ **"Cross-origin requests are restricted to a specific, configured list of allowed origins — not open to any website."**
Evidence: `api.py:832-843` — CORS origin list from env var, not wildcard, correctly paired with `allow_credentials`.

✔ **"Each client record tracks the legal basis under which their personal data is being processed, including a consent date where applicable."**
Evidence: `klijenti/router.py:122,138-143` — `pravni_osnov_obrade` field, enum-validated to `{ugovor, zakonska_obaveza, legitimni_interes, saglasnost}`, plus `saglasnost_datum`.

---

## LIST B — Claims Vindex AI must NOT publish

✘ **"Enterprise-grade security"**
No evidence supports this at the level the phrase implies. Two confirmed CRITICAL findings are live today (SEC-001, SEC-002). See Final Assessment in `SECURITY_DUE_DILIGENCE_REPORT.md`.

✘ **"Zero-trust architecture"**
The opposite of zero-trust is closer to the current reality in one specific, important dimension: a single service-role Supabase key bypasses Row-Level Security for the entire backend (SEC-004) — every table's real protection is "the code remembered to filter by user_id," not an independently-enforced trust boundary.

✘ **"SOC2-ready" / "SOC2-compliant"**
No evidence of any compliance-framework preparation work (control documentation, access reviews, formal risk register beyond this audit) was found in the repository.

✘ **"Military-grade encryption"**
Not a meaningful technical term. The actual, accurate, defensible claim is the specific one in List A (AES-256-GCM) — use that instead.

✘ **"Passwords are hashed using Argon2id"** — as it would be understood by a reader (i.e., "your login password is protected this way")
**This is the one that will surprise you:** the Argon2id implementation (`security/crypto.py:215-251`) is real, correctly parameterized, and fully functional — but it has **zero call sites** anywhere in the codebase (SEC-023). Actual user authentication is delegated entirely to Supabase Auth, which has its own (unverified-from-this-repo) password handling. Publishing this claim would describe infrastructure that exists but is not actually in the login path.

✘ **"GDPR compliant" / "Full right to erasure" / "Your data can be permanently deleted"**
SEC-002 — the erasure endpoint's own user-facing message currently claims case data is anonymized when the code does not do this. This is the single most important claim NOT to overstate further in public marketing while it's open.

✘ **"Protected against AI prompt injection" / "Jailbreak-resistant AI"**
SEC-003 — real defenses exist but are applied to roughly 1 of an estimated 50+ AI call sites. True today only for the single `/api/pitanje` endpoint, not the product as a whole.

✘ **"Client data is anonymized/stripped of PII before AI processing"**
SEC-006 — only numeric identifiers (JMBG/PIB/etc.) are masked; names and addresses are not, and the masking function isn't even called on the Case Genome extraction path specifically.

✘ **"Your data is fully isolated from other customers" / "Strict multi-tenant isolation"**
SEC-001 — a confirmed, reproducible cross-tenant data-injection bug exists today. This claim cannot be made until it's fixed and a full endpoint sweep confirms no sibling instances remain.

✘ **"Rate-limited and protected against abuse" / "DDoS protected"**
SEC-011/SEC-010 — `SlowAPIMiddleware` is not registered (configured default limits may not be enforcing app-wide) and ~30% of routes, including newly-added AI-cost-bearing ones, have no explicit rate limit.

✘ **"All data encrypted at rest"**
Field-level encryption is confirmed only for specific identifier fields (List A). Whether the underlying Postgres/Supabase infrastructure itself encrypts the disk is a hosting-provider fact, `REQUIRES PRODUCTION VERIFICATION` / vendor documentation — not something this codebase can prove either way.

✘ **"Fully audited and secure" / "No known vulnerabilities"**
This audit itself is direct counter-evidence — 30 findings, 2 confirmed live CRITICAL issues. Do not cite the existence of a security audit as proof of security; cite it as proof of a serious, ongoing process, once the CRITICAL items are closed.

---

## How to use this document

List A items are safe verbatim, with their stated caveats respected. Do not combine or generalize them into a broader claim than what's written (e.g., do not turn "audit logs are immutable" into "all data is immutable"). Re-run this classification after each `SECURITY_ROADMAP.md` P0/P1 item closes — several List B items (multi-tenant isolation, AI injection protection, GDPR erasure) are one confirmed fix away from moving to List A, and that is the fastest, most honest way to expand what Vindex AI can publicly claim.
