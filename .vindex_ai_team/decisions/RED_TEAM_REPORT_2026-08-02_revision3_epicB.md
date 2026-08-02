# Red Team Report — Revision 3, Epic B only (narrow falsification re-check)

**Date:** 2026-08-02
**Reviewer role:** Red Team / Devil's Advocate (third pass, fresh agent, no authorship stake)
**Scope (strict):** Epic B's SEC-011 fix only — "collapse to a single `Limiter` instance, then register
`SlowAPIMiddleware`". Epics A, C, D, E, F, G, H, the reconciliation table, and the root-cause clustering
section were **not** reviewed and are not covered by this verdict.
**Target under review:** `.vindex_ai_team/decisions/2026-08-02_forensic-remediation_ARCHITECTURE_DECISION.md`
lines 131–152.
**Environment ground truth:** slowapi **0.1.9**, installed at
`C:\Users\Benny\miniconda3\Lib\site-packages\slowapi\`. All library line numbers below refer to that
installed source, which I read directly.

---

## VERDICT: **BLOCKING**

One genuine **HIGH** remains **in the proposed fix itself**, plus one Medium that materially weakens
the fix's own success claim.

The fix's *direction* is correct and I could not break it on the axes it was challenged on — the
collapse is necessary, mechanically sound, and import-safe (§3 below documents everything I tried to
break and why it held). What blocks it is that Revision 3 removed the regression for the **444
decorated** routes and left an **identical-magnitude regression, from the same root cause, on the 153
undecorated routes** — which is precisely where the middleware's default now lands, and which includes
the platform's own healthcheck endpoint and its 60-second session heartbeat.

Revision 2 shipped "60/hour layered on top of routes that already have higher limits."
Revision 3 fixes that and ships "60/hour applied to `/health` and to a 60-second heartbeat."
Same defect class, moved one step to the right.

---

## 1. Claims from the brief that I re-verified myself

| Claim | Verdict | Evidence |
|---|---|---|
| Two independent `Limiter` instances exist | **CONFIRMED** | `shared/rate.py:89` (`limiter = build_limiter(_get_real_ip)`) and `api.py:547` (`limiter = build_limiter(_get_real_ip)`). Repo-wide grep for `Limiter(` outside site-packages returns only `shared/rate.py:71`, `shared/rate.py:86` (inside the factory) and `tests/test_sec005_failopen_limiter.py:61`. The `TokenBucketRateLimiter` hits in `web3_integracija/` are an unrelated class. |
| `app.state.limiter` is `api.py`'s instance | **CONFIRMED** | `api.py:549` is the **only** assignment to `app.state.limiter` anywhere in the repo (single grep hit). |
| `SlowAPIMiddleware._should_exempt` reads `app.state.limiter._route_limits` | **CONFIRMED against installed source** | `slowapi/middleware.py:117` `limiter: Limiter = app.state.limiter`; `:120` `if _should_exempt(limiter, handler)`; `_should_exempt` at `:96-110` checks `name in limiter._exempt_routes` then `name in limiter._route_limits`. The ASGI variant does the same at `:168-175`. |
| Registering the middleware pre-collapse layers the default on top of decorated routes | **CONFIRMED, and it is worse than "on top"** | `slowapi/extension.py:550-630`. With `in_middleware=True`, `limits` is never populated (`:579 if not in_middleware:`), so `route_limits == []`, so `combined_defaults = all(...)` over an empty list evaluates **`True`** (`:617-619`), so `all_limits += self._default_limits` fires **unconditionally** (`:628`) for any non-exempt route. |
| Counts: 29 in `api.py`, 415 elsewhere, 444 total decorated | **CONFIRMED exactly** | Full AST scan of `api.py` + `routers/**` + `klijenti/**`: **597 routes total, 444 decorated, 153 undecorated**. `api.py` = 29 decorated. |
| "…across `routers/*.py` **and `klijenti/`**" | **FALSE (Low)** | `klijenti/` contains **zero** `@limiter.limit(` and **zero** `from shared.rate import limiter`. All 415 are in `routers/`. See B-3. |
| Import-path resolution: routers' `limiter` ≠ `app.state.limiter` | **CONFIRMED** | 90 router files do `from shared.rate import limiter` (module-level singleton, `shared/rate.py:89`); `api.py:545` imports only `build_limiter`/`_get_real_ip`/`_REDIS_URL` and constructs a *second* instance at `:547`. Two distinct objects. |
| The docstring says counters are shared under Redis | **CONFIRMED** — Revision 3's correction of Revision 2 is right | `shared/rate.py:59-67`: both instances get the same `storage_uri`, same `key_func`. Counter *values* are shared; the `_route_limits` *registry* is not. Revision 3's diagnosis is correct. |

---

## 2. FINDINGS

### B-1 — **HIGH — the fix ships a production-outage-class regression on the 153 undecorated routes**

**What the plan says.** Line 134/151-152: collapse, "then register the middleware." Line 148 explicitly
names the default as `60/hour`. The plan says nothing about *changing* that default, *scoping* it, or
*exempting* anything.

**What actually happens after the collapse.** `_should_exempt` returns `True` for all 444 decorated
routes (correct — that is the fix working). It returns `False` for the other **153**, so
`extension.py:628` applies `self._default_limits`. `shared/rate.py:42` sets that to `["60/hour"]`, and
`build_limiter` is called with no `default_limits` override at either `shared/rate.py:89` or
`api.py:547`. So: **60 requests per hour, per client IP, per URL** on 153 routes that today have no
slowapi limit at all.

**The blast radius, enumerated from the AST scan** (file:line, all confirmed undecorated):

| Route | Site | Why it breaks |
|---|---|---|
| `GET /health` | `api.py:1493` | `railway.toml:5` sets `healthcheckPath = "/health"`. Platform healthchecks poll far more often than 1/min from a small set of source IPs. Sustained 429 on the healthcheck path is a **deploy/restart loop**, not a degraded feature. |
| `POST /api/sesija/ping` | `routers/sesije.py:151` | `static/vindex.js:189` — `setInterval(_sesijaPing, 60000)`. Its own docstring: *"Heartbeat — poziva se svakih 60 sekundi"*. That is **exactly 60/hour for one user**, sitting on the limit boundary with zero headroom. Two lawyers behind one office NAT = 120/hour = guaranteed 429s. The heartbeat drives the single-device-session enforcement (the 409 path at `static/vindex.js:152`). |
| `GET /`, `/app`, `/portal`, `/sw.js`, `/manifest.json`, `/offline` | `api.py:1435, 2152, 2157, 2264, 2275, 2281` | App-shell routes served through FastAPI route functions (not a `StaticFiles` mount, which would be exempt via `handler is None`). Per-IP 60/hour on `/app` for a whole NAT'd office. Note `/sw.js` is fetched by the service worker on every SW update check — see the SW cache-bump practice in this project. |
| `POST /viber/webhook` | `routers/viber.py:105` | Inbound provider webhook. All firm traffic arrives from a small set of Viber egress IPs → one shared bucket → **silently dropped inbound client messages**. |
| Entire `klijenti/` CRM — 20 routes | `klijenti/router.py:212…1436` | Includes `POST /klijenti`, `GET /klijenti`, `GET/PUT/DELETE /klijenti/{id}`, document upload/download, timeline, CSV import. These are **not** under `/api/`, so they are also not covered by the existing per-user middleware (below) — the 60/hour IP blanket would be their only limiter, and their primary one. |
| `POST /api/cron/daily` | `api.py:1503` | Low volume; listed for completeness. |

**In-repo evidence that 60/hour per-IP is against this codebase's own deliberate policy.** `api.py:922-934`
already implements a second, independent, app-wide rate limiter (`user_rate_limit_middleware`,
`api.py:998`) with `_USER_API_LIMIT = 600/hour` and `_USER_AI_LIMIT = 60/hour`, under this comment at
`api.py:924`:

> `# Limiti su namerno blaži od IP limita — korisnik može biti iza NAT-a`

The team has already reasoned about NAT and deliberately chose **600/hour** as the general-API global
ceiling. Epic B as written would layer a **10× stricter, IP-keyed** ceiling underneath it, silently
overriding that decision — and would extend it to the non-`/api/` surface (`klijenti/`, app shell)
that the existing middleware deliberately does not touch.

**Concrete failure scenario.** Deploy on a Friday. Railway/Render healthcheck hits `/health` every 10s
from its checker IP → 360 requests/hour → 429 from request ~61 onward → healthcheck fails →
platform marks the instance unhealthy and cycles it → restart loop. Meanwhile, at a 4-lawyer firm behind
one office IP, `/api/sesija/ping` returns 429 for 3 of the 4 users within the first hour, their session
rows go stale, and the single-device-session logic starts issuing spurious 409 "already active on
another device" toasts. Neither symptom points at rate limiting in the logs, because
`_json_rate_limit_handler` (`api.py:552`) returns a generic Serbian "Previše zahteva" body.

**Severity reasoning: HIGH.** It is a defect *in the proposed fix itself*, not elsewhere in the plan; it
is triggered by shipping the fix exactly as written, with no adversary required; and its worst case is
platform-level (restart loop), not feature-level. It is the same defect class the previous pass caught,
which is why it does not get a discount for being "only" the undecorated half.

**Required correction (this is what would move the verdict to CONDITIONAL/READY):** Epic B must state
the middleware's default explicitly rather than inheriting `_DEFAULT_LIMITS`, and must state an exemption
set. Concretely: pass an explicit `default_limits` to `build_limiter` for the app-wide instance, sized
consistently with the existing `_USER_API_LIMIT = 600/hour` decision rather than 10× below it; and
register `limiter.exempt` (`extension.py:870`) — or equivalent — for at minimum `/health`,
`/api/sesija/ping`, the app-shell routes, and inbound provider webhooks. Note that `_DEFAULT_LIMITS` is
also the `in_memory_fallback` value (`shared/rate.py:68, 78`), so it cannot simply be raised in place
without also changing Redis-outage behavior — the app-wide default and the fallback limit need to be
decoupled.

---

### B-2 — **MEDIUM — `key_style` defaults to `"url"`, so the "blanket default" does not actually cap enumeration abuse**

`Limiter.__init__` defaults `key_style: Literal["endpoint", "url"] = "url"` (`extension.py:147`).
`build_limiter` (`shared/rate.py:59-86`) never passes it. Therefore, at `extension.py:565`:

```python
_endpoint_key = endpoint_url if self._key_style == "url" else endpoint_func_name
```

`endpoint_url` is `request["path"]` (`extension.py:559`) — the **concrete** path, with path parameters
already substituted. That value becomes `limit_scope` in `__evaluate_limits` (`extension.py:488`,
`lim.scope or endpoint`) and is part of the storage key (`:501`).

**Consequence for the fix as stated.** The middleware's default bucket is keyed
`(client_ip, exact_URL_path)` — not `(client_ip, route)`. Of the 153 undecorated routes, **36 carry path
parameters**. For those, an attacker enumerating values gets a **fresh 60/hour bucket per value**:
`/klijenti/{klijent_id}` (`klijenti/router.py:334`), `/klijenti/{klijent_id}/dokumenti/{doc_id}/download`
(`:826`), `/{job_id}` (`routers/jobs.py:84`), and so on. Enumeration/scraping — the abuse SEC-011 is
named for — remains uncapped by the new middleware for exactly the routes where enumeration is possible.

So the plan's claim at line 152, *"then register the middleware"* → gap closed, is **overstated even
after the collapse**. It closes the gap for un-parameterized undecorated routes only.

**Second-order note that must be decided deliberately, not silently:** if Epic B fixes this by setting
`key_style="endpoint"`, that also changes the bucket key for all **444 already-decorated** routes, which
today are per-concrete-URL. A route decorated `5/minute` on `/api/predmet/{id}/analiza` currently means
5/min *per predmet*; under `"endpoint"` it becomes 5/min *across all predmeti* for that user's IP. That
is a real tightening of live limits and needs to be an intentional, announced change — not a side effect
of an SEC-011 patch.

**Severity: Medium.** It does not break production; it means the fix delivers materially less than the
plan claims, on the specific abuse vector SEC-011 exists to stop.

---

### B-3 — **LOW (factual) — `klijenti/` is named as a decoration site; it has none**

Epic B line 134 instructs making the single instance *"the object every `routers/*.py`+`klijenti/` file
imports for `@limiter.limit(...)` decoration."* Verified: `klijenti/` contains **zero** occurrences of
`@limiter.limit(` and **zero** `from shared.rate import limiter`. All 415 non-`api.py` decorations live
in `routers/`. The instruction is a no-op for `klijenti/`.

This is worth correcting not for pedantry but because it hides B-1: `klijenti/`'s 20 routes are
undecorated, non-`/api/`-prefixed, and therefore land squarely in the 60/hour blast radius while the
plan's own wording implies they are already covered.

---

### B-4 — **INFO (pre-existing, unchanged by the collapse, but caps the claim)**

During a Redis outage the collapse does not preserve per-route limits. `extension.py:599-608`: when
`_storage_dead` and a fallback limiter exists, the decorator path (`in_middleware=False`) takes the
`else` branch and sets `all_limits = self._in_memory_fallback` — a single global `60/hour`
(`shared/rate.py:68, 78`) for **every** route, discarding each route's own limit. This is already
documented and test-pinned in `tests/test_sec005_failopen_limiter.py:14-24` ("SVE rute privremeno dele
JEDAN, globalni `in_memory_fallback` limit"). Not caused by Epic B, but any claim that Epic B delivers
"correct per-route limits app-wide" is true only while Redis is healthy.

---

### B-5 — **INFO — SEC-010's cost is understated (adjacent line in the same epic table)**

Epic B line 136 says "decorate remaining undecorated AI-cost routes." `__limit_decorator` raises at
**import time** if the decorated function has no `request` or `websocket` parameter
(`extension.py:711-713`). Of the 153 undecorated routes, **120 have neither parameter**
(e.g. `routers/sesije.py:151 ping_sesija(body, user)`, `routers/push.py:41`, `routers/tos.py:18`,
`routers/status_page.py:45-114`). Each therefore needs a signature change plus every caller/test that
constructs it. This is an argument *for* the middleware direction, not against it — but "just decorate
them" is not the cheap fallback it looks like, and the epic should say so.

---

## 3. What I tried to break and why it held

I did not confirm the collapse because it looks right. These are the specific attacks I ran at it:

1. **"Collapsing will cause a circular import."** — **Held.** `shared/rate.py:30-35` imports only
   `logging`, `os`, `typing`, `slowapi.Limiter`, `starlette.requests.Request`. It imports **nothing**
   from this repo. Grep for `import api` under `shared/` returns nothing. And `api.py:545` **already**
   imports from `shared.rate` today. Changing `api.py:545-547` to `from shared.rate import limiter`
   introduces no new edge in the import graph at all.

2. **"The two instances were separated for a reason the collapse would destroy."** — **Held; there is
   no such reason, and the code says so in writing.** `shared/rate.py:59-67`, the `build_limiter`
   docstring, calls the duplication verbatim *"arhitektonska duplikacija, poznata, van obima SEC-005"*
   — a known accident explicitly declared out of scope, not a design. Both instances are constructed
   from the same factory, same `key_func` (`_get_real_ip`), same limits, same Redis config, same
   fail-open flags. `git log -- shared/rate.py` shows the factory was introduced by SEC-005 precisely to
   make the two identical. There is no configuration difference for the collapse to lose.

3. **"Ordering: routers are imported at `api.py:566+`, after `app.state.limiter` is set at `:549` —
   decorations registered later won't be visible."** — **Held.** `_route_limits` is a plain mutable
   `Dict` (`extension.py:219`) mutated in place at decoration time via `setdefault(...).extend(...)`
   (`extension.py:704`). `app.state.limiter` stores a **reference**; the middleware dereferences it per
   request (`middleware.py:117`). Late mutation is visible. Order is irrelevant once it is one object.

4. **"Something else already depends on `app.state.limiter` being `api.py`'s specific instance."** —
   **Held; nothing does.** Repo-wide, `app.state.limiter` appears exactly once (`api.py:549`, the
   assignment). No handler, no `/health`, no `/status`, no `routers/proof.py` check, and no test reads
   it. The only tests touching limiter internals are
   `tests/test_sec005_failopen_limiter.py:204-205`, which assert `_in_memory_fallback_enabled` /
   `_swallow_errors` on a **locally constructed** limiter from `build_limiter`, not on the app's. The
   `RateLimitExceeded` handler (`api.py:552-559`, registered `:561`) is bound to the app's exception
   handler table, not to any limiter instance — instance-agnostic.

5. **"`_find_route_handler` takes the *last* full match (`middleware.py:19-27`, no `break`) while
   Starlette dispatches the *first* — a shadowed duplicate route could get the wrong exemption
   decision."** — **Real quirk, but held here.** Prefix-aware full-path scan across all 597 routes finds
   exactly **one** true duplicate: `GET /api/search` at `api.py:3083` and `routers/search.py:187`.
   Starlette dispatches `routers.search.global_search` (registered first, at `api.py:702`); the
   middleware would evaluate `api.global_search` (registered last). **Both are decorated**
   (`60/minute` and `30/minute` respectively), so after the collapse both names are in the single
   `_route_limits` and `_should_exempt` returns `True` on either. No mismatch is reachable today. Flagging
   it only as a latent trap: if a future duplicate pair has one decorated and one not, this quirk
   silently applies the default to a route that has its own limit.

6. **"`SlowAPIMiddleware` is `BaseHTTPMiddleware`; adding it will break the SSE endpoint."** —
   **Held.** `api.py:3068` is a genuine `text/event-stream` `StreamingResponse`
   (`/api/pitanje/stream`). But `shared/audit.py:22` (`AuditMiddleware(BaseHTTPMiddleware)`, registered
   `api.py:921`) and two `@app.middleware("http")` decorators (`api.py:991`, `api.py:998`) are already
   `BaseHTTPMiddleware`-based and already wrap that response. Adding a third introduces no new class of
   streaming risk. WebSocket routes (`routers/voice_realtime.py:86`) are untouched — `BaseHTTPMiddleware`
   never sees non-HTTP scopes.

7. **The brief's proposed "simpler alternative": leave `api.py`'s instance alone and just set
   `app.state.limiter = shared.rate.limiter` at startup.** — **This does not work; the plan is right and
   the alternative is wrong.** `api.py`'s 29 routes would then be decorated against an instance the
   middleware never inspects, so `_should_exempt` returns `False` for all 29, so `extension.py:628`
   layers the default on top of *their* limits. That is the identical Revision-2 regression, merely
   inverted — 29 routes instead of 415, and 29 of the most sensitive ones (`api.py`'s decorated set
   includes the AI-cost routes). The only variant that works is the one the brief describes second —
   api.py re-decorating against `shared.rate.limiter` — which **is** the full collapse the plan
   specifies. Epic B's chosen shape is correct.

**Summary of §3:** the collapse is sound, cheap, import-safe, and has no hidden dependents. Every
mechanical objection I could construct against it failed. The BLOCKING verdict rests entirely on what
the plan does *after* the collapse — registering the middleware while inheriting a `60/hour` default
that was never sized to be an app-wide blanket (B-1), and inheriting `key_style="url"`, which prevents
that blanket from doing the job it is claimed to do (B-2).

---

## 4. What Epic B should say

1. Keep the collapse, verbatim — it is correct and independently verified.
2. Correct "`routers/*.py`+`klijenti/`" → "`routers/*.py`" (B-3), and note that `klijenti/`'s 20 routes
   are *undecorated*, hence in the middleware's blast radius rather than exempt from it.
3. Add, as part of the same change, an explicit app-wide default sized against the existing
   `_USER_API_LIMIT = 600/hour` decision (`api.py:933`), decoupled from `_DEFAULT_LIMITS`, which must
   stay as the Redis-outage `in_memory_fallback` value.
4. Add an explicit exemption list, minimum: `/health`, `/api/sesija/ping`, `/`, `/app`, `/portal`,
   `/sw.js`, `/manifest.json`, `/offline`, `/viber/webhook`.
5. State a `key_style` decision explicitly, and acknowledge that `"endpoint"` re-buckets all 444
   existing per-route limits (B-2).
6. Downgrade the claim: after this, SEC-011 is closed for undecorated routes; it is **not** closed for
   Redis-outage windows (B-4).

---

## 5. Incidental observations — explicitly NON-BLOCKING, outside Epic B's scope

Noted while reading; not part of the verdict, not reviewed to audit depth, and deliberately not blended
into the findings above.

- **Two independent rate-limiting systems coexist.** Beyond slowapi, `api.py:922-1030` implements a
  per-user in-memory sliding window (`_USER_RATE`, `user_rate_limit_middleware`). It is process-local
  (`api.py:929`), so under multi-worker gunicorn each worker keeps its own window and the effective
  limit is `N_workers × 600/hour`. Not an Epic B item, but any future claim about "the" rate limit
  needs to name which of the two (soon three) layers it means.
- **Undecorated debug/diagnostic routes are publicly routable.** `GET /api/debug` (`api.py:2578`),
  `/api/credits-debug` (`:2497`), `/api/diagnose` (`:2088`), `/test-pinecone` (`:2032`), `/test-zdi`
  (`:2063`), `/api/rag-test` (`:2624`), `/api/test-pitanje` (`:2603`). I did **not** check their auth
  guards — they may well be `Depends`-protected. Flagging only that they exist, are undecorated, and
  look like development leftovers.
- **`GET /status` is registered three times** on different prefixes (`api.py:1450`, `routers/plans.py:47`,
  `routers/tos.py:18`). Not a collision after prefixing, but a naming-clarity smell in a codebase that
  has already had one real routing collision (`/api/cron/daily`, SEC-002, resolved per
  `routers/email_notif.py:795-807`).
- **`597` decorator-declared routes** found by AST across `api.py` + `routers/**` + `klijenti/**` — a
  useful cross-check against the "508 endpoints" figure in the Platform Anatomy Report. The delta is
  probably methodology (that report may count mounted/HTTP-method pairs differently), but the two
  numbers should be reconciled before either is cited externally under the Evidence-Based Claims Policy.
