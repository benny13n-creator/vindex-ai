# Authorization Forensics — Program Lambda, Certification 003

**Agent**: Authorization Architect. **Scope**: every authorization/ownership ENFORCEMENT MECHANISM itself —
`@require_auth`-style dependencies, ownership-check helper functions, fail-open/fail-closed behavior on
exception — not another endpoint-by-endpoint sweep (Certification 002 already did that near-exhaustively,
see `IDOR_MATRIX.md`).

## Finding — FIXED: `klijenti/router.py::_get_role` failed open on DB exception

`klijenti/router.py:48-58`. Before this sprint, a DB read exception (network blip, RLS misconfiguration,
connection-pool exhaustion) while reading `user_roles` was treated **identically** to "user genuinely has no
role row yet" — both silently returned `DEFAULT_ROLE` (`Role.ADVOKAT`), which passes `can_perform(role,
"access_confidential")` and grants `archive_client`/`view_conflict_results`. Contrast: `routers/zadaci.py::
_get_firma_info` and this same file's own `_verify_owns_klijent` both correctly fail **closed** on the
identical exception shape — this was an isolated deviation, not "how the system always works."

Independently re-verified by the Adversarial Certification fork line-by-line: `DEFAULT_ROLE = Role.ADVOKAT`
confirmed correct (not misread), `ACTION_MIN_ROLE["access_confidential"] = Role.ADVOKAT` confirmed to pass
`can_perform`, no outer guard exists between `_auth_from_request` and `_get_role`, exception path confirmed
reachable by any authenticated-but-unassigned-role account. **CONFIRMED, not refuted.**

**Fix**: on exception, `_get_role` now returns `Role.SEKRETARICA` (the lowest role), not `DEFAULT_ROLE`. The
genuinely-no-row-yet case (an intentional product default for new users) is unchanged — still `DEFAULT_ROLE`.
**Status: FIXED.** Proof: `tests/test_lambda003_klijenti_role_fail_closed.py` (5 tests) — exception fails
closed and cannot pass `access_confidential`; no-row-yet still gets the intentional default; a real role row
is still honored; founder short-circuit unaffected.

## Finding — dormant: `shared/case_context.py::get_document_full_text()` ignored `uid`

Covered in full in `AI_CONTEXT_ISOLATION.md` (the AI Isolation Auditor's own scope) since this function is
the Document Visibility Engine's documented scale safety-net, not a general authorization helper — cross-
referenced here because it's the same bug CLASS (a function accepting an ownership parameter and silently
not using it). **Status: FIXED**, see that report.

## Finding — ACCEPTED RISK: auth fallback silently skips live revocation check on Supabase transient failure

`shared/deps.py::_verify_token` (~line 216-244) tries a live `supa.auth.get_user(token)` call first (would
catch a server-revoked session immediately), but on **any** exception (line ~235, bare `except Exception`, no
type filtering, no re-raise) falls through to `verify_token_local(token)` — a function whose own docstring
states explicitly it has no live revocation check and is "NOT sufficient for authorization" on its own. Yet
`get_current_user()` — the dependency gating every protected route — uses exactly this fallback chain as its
sole verification path. The Adversarial Certification fork independently re-verified this and found it
**stronger than originally stated**: the documented safety invariant ("authorization is done exclusively by
`get_current_user` further down the chain") is factually false in this codebase, since `get_current_user` IS
that fallback chain.

**Reproduction trace**: revoke a user's Supabase session (sign-out-everywhere, suspend, password reset) while
their JWT is still unexpired → the next `auth.get_user()` call from this backend throws for any transient
reason (network blip, Supabase-side hiccup) → the code silently accepts the token via signature+expiry-only
local verification, granting the revoked user continued access for the remainder of the token's lifetime.
**Not attacker-triggerable on demand** — requires an external fault condition on Supabase's own side, not
client-controlled input.

**Why not fixed this sprint**: closing this requires a genuine security-vs-availability policy decision, not
a bug patch. Failing closed on ANY Supabase outage (reject every request while Supabase's own `auth.get_user`
is degraded) protects against this narrow revocation-lag window but takes the whole platform down during any
Supabase-side blip, for every user, not just revoked ones. Keeping the current fallback preserves availability
at the cost of this narrow, external-fault-gated exposure window. This is the founder's call to make, the same
class of decision `LAMBDA-001` (Supabase timeout tuning) was already correctly deferred for lack of production
fault-rate data. **Status: ACCEPTED RISK**, tracked as `LAMBDA003-AUTH-001` in the debt register — revisit if
Supabase outage frequency/duration data ever makes the tradeoff concrete.

## Finding — ARCHITECTURAL DEBT: "firm admin" defined inconsistently across 2 files

`routers/kancelarija.py:66-68` (`_get_firma_for_admin`) treats only literal `kancelarije.admin_uid == uid` as
admin. `routers/zadaci.py:83-112`/`routers/workflow.py:45-72` instead treat `uloga in ("admin", "partner")`
as admin — a broader principal set. No evidence a "partner"-role member can currently reach a
`kancelarija.py`-gated owner-only action (that file never consults `kancelarija_clanovi.uloga`), so this is
**not a confirmed bypass today** — but it is real definitional drift that could become exploitable the next
time a new admin-gated action reuses the wrong helper's notion of "admin." **Status: ARCHITECTURAL DEBT**
(`LAMBDA003-AUTH-002`) — unifying "admin" needs a single source-of-truth decision (which is correct: strict
owner-only, or role-inclusive?), not a guessed patch.

## Finding — noted, not fixed: dead `is_admin` field in `routers/workflow.py::_get_firma`

Computed at 2 of 3 return branches but never read at any of its 7 call sites (verified: every authorization
decision in that file correctly uses `kancelarija_id` matching instead). Not itself exploitable — an unused
field grants nothing — but authorization-shaped dead code that could mislead a future maintainer into
believing a check exists here when it doesn't. Left untouched this sprint (zero operational risk, not worth
a code-change/test cycle) — noted for a future cleanup pass, not tracked as debt.

## Certified clean, with fresh evidence

- `shared/deps.py::get_current_user`/primary `_verify_token` path/`verify_token_local`'s signature check: no
  test/debug/env-var bypass found anywhere (grepped `SKIP_AUTH`, `DEV_MODE`, `DEBUG`-gated patterns — zero
  matches beyond harmless `logger.debug` calls). Both cryptographic verification paths (Supabase SDK, local
  JWT/JWKS) perform real signature checks.
- `require_case_owner()`/`require_firm_owner()` as literal named functions **do not exist** — case ownership
  is enforced via ~300+ independent inline `.eq(user_id, uid)` filters (already exhaustively mapped in
  Certification 002's `IDOR_MATRIX.md`), meaning the "one broken shared helper" risk class doesn't apply
  there — the risk is per-callsite omission, a different, already-swept category.
- `validate_predmet_reference()` (`shared/genome_validator.py`) is **not** an authorization gate despite the
  name — it's a GPT-hallucination detector checking a model claim against an already-ownership-scoped dict.
  Miscategorizing it as an ownership helper would have produced a false negative; corrected here.
- `shared/permissions.py::PermissionService.require()`: founder bypass re-evaluated fresh per request from a
  static env-var set, no caching; kill-switch/dependency checks apply even to founder by design.
- No permission/role caching of any kind exists anywhere in the repo (exhaustive `lru_cache`/`TTLCache` grep
  — zero hits outside the JWKS public-key cache, which caches Supabase's own signing key, not user state).
- Firm-membership removal (`kancelarija_clanovi.status`) is queried live on every request — no delay window.
- No user-reachable route executes with service-role trust bypassing a check a normal request would hit.

## NEEDS LIVE VERIFICATION (source-only audit cannot resolve)

`verify_token_local` decodes with `options={"verify_aud": False}`. Whether Supabase ever issues a differently
-scoped JWT (e.g. password-recovery) sharing the same signing key/`sub` shape that could be replayed as a
full session token here is a Supabase-platform behavior question this repo's source cannot answer.
