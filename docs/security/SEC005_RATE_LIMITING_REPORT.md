# SEC-005 — Rate Limiting Verification & Fix (2026-07-24)

**Status:** Implemented and tested in this repository. Not yet independently
confirmed against production traffic (that requires live Render/Redis
access this environment doesn't have — same standing limitation as every
other SEC-0xx item in this register).

## Context

The 2026-07-23 SEC-005 sprint fixed Redis fail-open behavior (see
`shared/rate.py`'s module docstring and `tests/test_sec005_failopen_limiter.py`).
This round is a follow-up, read-only-analysis-first investigation into
whether the rate-limiting *layer itself* — separate from the Redis storage
question — actually protects what it appears to protect.

## Findings

**Nalaz A (HIGH) — IP-based limiter likely counted the wrong IP.** The app
runs via `gunicorn -c gunicorn.conf.py` (UvicornWorker) behind Render's edge
proxy, with no `forwarded_allow_ips` / `ProxyHeadersMiddleware` configured
anywhere. `api.py`'s slowapi `Limiter` used `slowapi.util.get_remote_address`,
which reads only `request.client.host` — behind an unconfigured reverse
proxy this is the proxy's address, not the real client's. `shared/rate.py`
already had a correct `_get_real_ip` (reads `X-Forwarded-For`, leftmost
value), used so far only by `routers/case_dna.py` and
`routers/legal_reasoning.py`.

**Nalaz B (CRITICAL) — the per-user rate limiter + anomaly detection layer
was dead code.** `api.py`'s `user_rate_limit_middleware` read
`request.state.user_id`, which was **never set anywhere in the codebase**
(confirmed via full-repo grep). Identity is normally resolved via
`Depends(get_current_user)` at the route-handler level, which returns the
user dict directly to the route — it never touches `request.state`, and
even if it did, that would happen *inside* `call_next()`, after this
middleware's pre-`call_next` check already ran. Result: `uid` was always
`None`; the entire `_check_user_rate_limit` (per-user hourly budget) and
`security/anomaly_detection.py` (anomaly scoring) code paths had never
executed against a real request since they were written.

Additionally, the `_AI_ENDPOINTS` allowlist used to apply a tighter
60/hour budget to AI-calling routes was stale: 3 of its original 6 entries
(`/api/kompletna`, `/api/copilot`, `/api/drafting`) matched no currently
mounted route (copilot's real path is `/copilot/chat`, mounted with no
`/api` prefix). Dozens of newer AI-calling routers built since this list
was written (`style_checker.py`, `matter_intel.py`, `knowledge_transfer.py`,
`evidence.py`, `case_intelligence.py`, `decision_replay.py`,
`client_twin.py`, `cio.py`, `outcome_intel.py`, `precedenti.py`) had **zero**
`@limiter.limit` decorators of their own either.

## Fixes implemented

**Faza 1** — `api.py`'s limiter now uses `shared.rate._get_real_ip` instead
of `get_remote_address` (`slowapi.util` import removed entirely). Stale
comment in `shared/rate.py` corrected.

**Faza 2** — `shared/deps.py` gained `verify_token_local(token)`, extracted
from `_verify_token`'s existing HS256/JWKS local-decode logic (signature-
verified, no Supabase SDK network round-trip — avoids doubling an
already-paid network cost on every `/api/*` request, and avoids the Sybil-
style bypass an unverified decode would allow). `user_rate_limit_middleware`
now extracts the `Authorization: Bearer` header itself, calls
`verify_token_local`, and sets `request.state.user_id` **before**
`call_next` — this is the part that actually makes the per-user limit and
anomaly detection fire for the first time. `_AI_ENDPOINTS` rebuilt to match
real mounted paths, including `/copilot/chat` and every router above;
`enterprise.py` intentionally excluded (makes no AI calls at all — its
protection is the per-route IP limiter from Faza 3, not this per-user AI
budget).

**Faza 3** — `@limiter.limit(...)` added to all 40 previously-unprotected
routes across `style_checker.py` (7), `knowledge_transfer.py` (8),
`matter_intel.py` (3), `evidence.py` (4), `case_intelligence.py` (2),
`decision_replay.py` (2), `client_twin.py` (5), `cio.py` (3),
`outcome_intel.py` (1), `precedenti.py` (1), `enterprise.py` (4). Limits:
10/minute for routes that call OpenAI directly, 20/minute for mutating
non-AI routes, 30/minute for read-only routes — consistent with the
existing convention in `api.py`.

**Faza 4** — `tests/test_sec005_rate_limiting.py` (18 tests): `_get_real_ip`
extraction correctness, structural confirmation `api.py` no longer
references `get_remote_address`, `verify_token_local` signature
verification (including a forged-signature rejection test — the concrete
proof the fix isn't a naive/bypassable decode), a full `TestClient`
integration test proving the middleware now actually blocks the 4th
request in a configured 3/hour window for a real signed token (previously
impossible — `uid` was always `None`), an anonymous-request-not-blocked
control, an invalid-token-fails-safe control, and a structural sweep
confirming every route in the 11 files above has an adjacent
`@limiter.limit`.

## What this does not (and cannot) prove from this environment

No live Redis, no live Render deployment, no way to confirm from here that
`X-Forwarded-For` actually contains the real client IP once request traffic
is live in production (it should — this is standard Render behavior — but
"should" is not "confirmed," consistent with this project's standing rule
against claiming production behavior without a production check).

## Regression note

Two pre-existing unit test files (`tests/test_matter_intel.py`,
`tests/test_outcome_intel.py`) called their route functions directly with
positional arguments matching the *old* signature (no `request` parameter).
Adding `request: Request` broke those call sites (slowapi's `isinstance`
check on the `request` kwarg/positional arg). Fixed by adding a
`_make_request()` helper (same pattern already established in
`tests/test_sec009_pii_encryption.py`) and updating all 11 affected call
sites. Full suite: 1831 passed, 0 failed.
