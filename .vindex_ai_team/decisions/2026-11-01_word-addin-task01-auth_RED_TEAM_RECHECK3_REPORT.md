# Red Team Re-review 3 — Word Add-in Task 01 Authentication

**Author (role):** Red Team / Devil's Advocate (fresh, non-fork review)
**Date:** 2026-11-01
**Verdict:** BLOCKING — one HIGH finding

## RT-08 — Word analysis misses AI user-rate and anomaly controls

**Evidence (PROVEN):** api.py:1067-1107 defines 60/hour AI and 600/hour general user limits; _check_user_rate_limit selects by matching _AI_ENDPOINTS. The existing middleware records/checks AI anomalies only within its locally verified uid branch (api.py:1184-1207). The proposed /api/word/* carveout skips that parser, and Word paths are not currently in _AI_ENDPOINTS. Calling the limiter with a future Word analysis path would therefore select the general API bucket; calling the limiter alone also omits anomaly checks. Current source has no Word API routes yet.

**Impact:** Word analysis could receive ten times the default account-level user quota and avoid existing AI anomaly screening, weakening protection against IP rotation.

**Smallest correction:** Add an explicit post-auth Word rate guard after provider/session verification and before side effects. Exchange applies the general API bucket after provider identity is established and before session issuance. Session management and future non-AI Word operations use the general API bucket; analysis/rewrite use the existing AI bucket plus _anomaly_record and _anomaly_check before analyzer/provider work. Key account-wide policy by server-derived user ID, shared across sessions and IPs. Use an exact /api/word/ path-segment carveout that skips only bearer parsing and continues through SlowAPI; keep all routes in that namespace Word-only and protected routes session-authenticated.

**Acceptance:** Instrument legacy verifier helpers and prove zero calls for Word exchanges. Prove SlowAPI IP/route limits still return 429. With server-verified Word sessions, show general versus AI bucket selection, AI anomaly checks before analyzer/provider calls, account buckets shared across sessions/IPs, client identity ignored, and /api/wordsmith retains ordinary bearer handling. Confirm unrelated authenticated APIs keep existing behavior.

## Other design checks

- Word-specific effective CSP replacement and Word-only X-Frame-Options removal remain specified; real host/header support is unverified.
- Per-provider-attempt claims, controlled retries, disabled hidden SDK retries, and result suppression after logout remain specified.
- Dialog Origin 1.1 capability gate, full-origin comparison, nonce, and fail-closed behavior remain specified; host compatibility is unverified.
- Word exchange avoids shared verifier logging, whose legacy helper records token prefixes; tests must cover app/access/audit logs.
- shared/permissions.py remains unchanged and the route must pass server-verified identity explicitly. PR #66 current state was not rechecked in this review.
- No files were edited by the reviewer; no tests, live authentication, AI calls, or network access were used.