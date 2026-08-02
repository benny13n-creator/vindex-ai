# RED TEAM — Epic B, Revision 5, terminal pass (3 named tests)

**Date:** 2026-08-02
**Scope:** exactly the 3 tests commissioned. No other findings reported.
**Artifact under review:** `.vindex_ai_team/decisions/2026-08-02_forensic-remediation_ARCHITECTURE_DECISION.md`,
Epic B (`:189-217`) and Epic H's route-shadowing row (`:295`), as they stand in Revision 5.
**Environment:** live app imported in-process (599 `Route` objects, 444 decorated / 155 undecorated);
`slowapi` read from the installed package at `C:\Users\Benny\miniconda3\Lib\site-packages\slowapi`.
Every behavioural claim below was executed, not reasoned about.

---

## VERDICT

| Test | Verdict |
|---|---|
| **Test 1 — route shadowing as a mechanism property** | **BLOCKING** — the *invariant* Revision 5 chose is provably correct and complete; the *enumeration method* that produces the pair set is not, and Epic H does not specify it. Demonstrated by finding a **6th live shadowed pair** that the plan's own stated measurement ("**5** such pairs exist", `:193`) does not contain. |
| **Test 2 — limit model: principle, not number** | **BLOCKING**, per tier: **(i) PARTIAL** — security objective stated, workload model absent, no number derivable. **(ii) PARTIAL** — workload model sketched, security objective absent, no number derivable. **(iii) FAIL** — states neither, and is additionally *falsified* by Test 3's `/api/sesija/ping` case. 0 of 3 tiers satisfy `limit = workload model + security objective`. |
| **Test 3 — enterprise scale (50 lawyers, 1 NAT IP, 5 000 predmeti)** | **BLOCKING** — two reproduced structural defects: (3a) `/api/sesija/ping` is a 60-second heartbeat that lands in tier (iii) *by the plan's own tier criterion* and would be throttled ~10-30× under load; (3b) `key_style="url"` buckets by **concrete** path, so decorating a parameterized route provides **zero** protection against bulk scraping — which falsifies SEC-011(d)'s stated remedy. |

### **OVERALL: BLOCKING.** Epic B does not close on this pass.

None of the three findings invalidates Revision 5's core design decisions. The collapse is sound, the
parity invariant is the right invariant, and the 3-tier idea is the right shape. What fails is
(1) the *specification of the check* that is supposed to make the parity invariant durable,
(2) the *derivation* behind all three tier numbers, and (3) two route-level consequences at scale
that the tier taxonomy structurally cannot see. All three are correctable within the current design.

---

## TEST 1 — Route shadowing as a MECHANISM property

### 1.1 What I confirmed first (the invariant is right)

Before attacking, I established what the correct invariant actually is, from source rather than from
the plan's description.

`slowapi/middleware.py:18-25` — `_find_route_handler` iterates `app.routes` and keeps the **last**
`Match.FULL` that has an `.endpoint`:

```python
for route in routes:
    match, _ = route.matches(scope)
    if match == Match.FULL and hasattr(route, "endpoint"):
        handler = route.endpoint
```

`slowapi/middleware.py:98-112` — `_should_exempt` has **exactly three** branches that return `True`:
`handler is None`; `name in limiter._exempt_routes` (`:106`); `name in limiter._route_limits` (`:110`).

From that, a bypass (a route served with **no** limit at all) requires all of:
the served route is undecorated, **and** the last-full-match route is either explicitly exempt or
statically decorated. `handler is None` cannot occur when the served route matched, because the
served route is itself a full match with an endpoint. Therefore **decoration-or-exemption parity
between the first-full-match and last-full-match route is a complete invariant for the bypass
class** — there is no fourth way in. Revision 5 picked correctly, and Epic H's phrasing ("any two
routes that both fully match a request") is the correct generalisation, not an approximation.

I verified the two directions behaviourally against real `slowapi` + real `SlowAPIMiddleware`
(harness: `scratchpad/rev5_repro.py`, default `5/minute`):

- **T-A** (A undecorated, B statically decorated — the state Revision 5 fixes):
  `_should_exempt -> True`; 20 requests → **20×200, 0×429**. Bypass reproduced.
- **T-B** (both decorated — Revision 5's fix): 20 requests → **3×200, 17×429**, i.e. A's own
  `3/minute` applies correctly. Fix confirmed effective.

### 1.2 The failed attacks (recorded, per the discipline of the prior passes)

Four attempts to defeat the invariant itself, all of which failed:

1. **`WebSocketRoute` pollution.** Hypothesis: a `@app.websocket("/ws/{cid}")` route could be
   selected as the last full match for an HTTP request to `/ws/health`, since `WebSocketRoute` does
   have an `.endpoint`. **Failed** — `APIWebSocketRoute.matches()` returns `Match.NONE` for an
   `http` scope (probe E2, `scratchpad/t1_edge.py`). No cross-protocol contamination.
2. **`Mount` pollution.** Hypothesis: `app.mount("/static", ...)` (`api.py:791`) and
   `app.mount("/word_addin", ...)` (`api.py:801`) are registered *after* all 100+
   `include_router` calls (`api.py:563-777`), so a mount could win last-match. **Failed** — `Mount`
   has no `.endpoint`, so `middleware.py:24`'s `hasattr` guard skips it without clearing `handler`;
   and no top-level route shares either prefix.
3. **Regressing the collapse.** Hypothesis: a future engineer copying `shared/rate.py:60`'s own
   documented `build_limiter` pattern into a new router re-creates a second `Limiter`, defeating
   parity. **Failed as a *bypass*** — decorations registered on a second instance are invisible to
   `app.state.limiter`, so `_should_exempt` returns `False` and the app-wide default is applied *on
   top*. That fails toward over-throttling, not toward an unlimited route. (It is a real
   availability regression and no check in the plan catches it, but it is not a hole.)
4. **Three-way full matches.** Probe E3: `/x/literal` (served) / `/x/{p}` / `/{q}/{r}` (decorated).
   slowapi picks the **last** (`d`), not the direct sibling; 20 requests → **20×200, 0×429**. This
   *would* be caught by a check that compares first-full-match against last-full-match, so it does
   not defeat the invariant — but it does show that a check written as "compare a literal route with
   its direct parameterized sibling" is the wrong shape. Noted as a precision requirement, not a
   finding on its own.

### 1.3 The finding: the enumeration, not the invariant

Epic H (`:295`) specifies **what** to assert ("asserting decoration parity (or exemption parity)")
but not **how the pair set is produced** ("a mechanical check enumerating shadowed pairs"). That gap
is not theoretical, because the plan already contains one instance of the enumeration being run, and
that instance is wrong.

The natural mechanical implementation — and the one that produces the plan's own figures — is:
substitute a token into each route template, use it as a probe path, and record any probe where the
first and last full match differ. I implemented exactly that against the live app
(`scratchpad/shadow.py`) and reproduced the plan's number precisely: **5 pairs**, matching
`:193`'s list item-for-item (`client_twin` dashboard/profil, `predmeti` bulk, `predmeti` dashboard,
`search` global, `klijenti/retention-check`).

I then implemented an **exhaustive pairwise overlap** enumeration instead — for every ordered route
pair sharing a method and segment count, construct a witness path segment-by-segment (literal where
either side is literal, token where both are parameters) and test it (`scratchpad/shadow2.py`):

```
exhaustive pairwise witnesses : 6
probe-per-template method     : 5

[MISSED BY PROBE METHOD]  GET /api/simulator/partija/partije
    starlette serves : /api/simulator/{predmet_id}/partije   routers.strategy_simulator.lista_partija     decorated=False
    slowapi resolves : /api/simulator/partija/{partija_id}   routers.strategy_simulator.detalji_partije   decorated=False
```

`routers/strategy_simulator.py:471` (`@router.get("/{predmet_id}/partije")`) and `:502`
(`@router.get("/partija/{partija_id}")`), both under the `/api/simulator` prefix. A request to
`GET /api/simulator/partija/partije` fully matches both. The probe method cannot see it: the probe
generated from `:471` is `/api/simulator/TOKEN/partije`, which does not match `:502` (segment 2 must
be the literal `partija`); the probe generated from `:502` is `/api/simulator/partija/TOKEN`, which
does not match `:471` (segment 3 must be the literal `partije`). **Neither route's own probe reaches
the other, so the pair is invisible — while a real request reaches both.**

So `:193`'s "Measured across the live route table: **5** such pairs exist" and "audit the other **4**
confirmed pairs" are, as measured facts, **6** and **5**. The 6th is benign today (both sides
undecorated) and would remain benign if SEC-010 decorates all 36 parameterized routes — both are in
that set. The problem is not this pair's current state; it is that **the measurement method the plan
used, and that Epic H's row would most naturally be implemented as, has a systematic false negative,
and the plan's text gives an implementer nothing that would steer them away from it.**

### 1.4 The concrete future scenario Test 1 asked for

Both requested conditions are met, and it is reproduced end-to-end (`scratchpad/t1_edge2.py`):

A future change adds a tenant-slug landing route to one router — `GET /{kancelarija_slug}/dashboard`,
undecorated — while an existing, later-registered router already serves `GET /portal/{token}`,
decorated. Neither is a "literal vs. parameterized sibling"; they are two parameterized routes whose
parameters sit in *different* positions.

```
probes generated  : ['/TOKEN/dashboard', '/portal/TOKEN', ...]
shadowed pairs FOUND by this check: NONE

GET /portal/dashboard full-matches: ['/{kancelarija_slug}/dashboard->tenant_dashboard',
                                     '/portal/{token}->portal']
starlette serves: tenant_dashboard  | slowapi resolves: portal
_should_exempt -> True
20 req, app default 5/min -> 20 x200, 0 x429
```

(a) It is not caught by decorating-at-review-time discipline: nothing about adding a tenant-slug
route reads as a rate-limiting change, and the two routes live in different files. (b) It is not
caught by a literal implementation of Epic H's check, because the check reports **NONE**. Result: a
route serving every request to `/portal/*` with a matching shape is completely unlimited, and CI is
green. This is the same class of "two things that should agree have silently diverged" that Epic H
exists to close — reopened by the check itself.

A second, independent blind spot: a `{param:path}` catch-all. Probe E1
(`scratchpad/t1_edge.py`) registers `GET /api/reports/summary` (undecorated) before
`GET /api/{rest:path}` (decorated). `_should_exempt -> True`; 20 requests → **20×200, 0×429**. Any
enumeration that compares routes at equal segment depth — including my own exhaustive method above —
misses this entirely, because the two paths have different segment counts. The repo has zero
`:path`/`:int`/`:uuid` converters today (verified by grep), so this is purely forward-looking; but
"enumerating shadowed pairs" as written does not tell an implementer that catch-alls need separate
treatment.

### 1.5 Secondary precision gap in the same row (recorded, not the basis of the verdict)

Epic H does not say *which registry* the check's "decorated" oracle reads.
`middleware.py:110` consults `limiter._route_limits` **only** — `_dynamic_route_limits` is not
consulted. A decorator with a *callable* limit value (e.g. a future plan-tiered limit) lands in
`_dynamic_route_limits` (`extension.py:702`) and not `_route_limits` (`:704`). Reproduced (T-C):

```
_route_limits keys        : ['__main__.retention_check']
_dynamic_route_limits keys: ['__main__.get_klijent']
_should_exempt(B) -> False
20 requests to B's own path, B's dynamic limit 100/min -> 5x200, 15x429
```

A check that treats `_route_limits | _dynamic_route_limits` as "decorated" reports parity while the
middleware disagrees; the route is silently held at the app default instead of its own limit. The
direction is over-throttle, not a bypass, so this is a correctness note on the check's oracle, not a
security finding. The check must read `app.state.limiter._route_limits` and `._exempt_routes`
exclusively.

### 1.6 Required to close Test 1

Epic H's row needs to specify the enumeration, not just the assertion: enumerate over **witness
paths derived from route *pairs*, not from individual route templates**, handle catch-all converters
as a separate case, compare **first**-full-match against **last**-full-match (not "sibling"), and
read the decorated/exempt oracle from `app.state.limiter._route_limits` / `._exempt_routes` only.
And `:193`'s "5 pairs / other 4" should be restated as 6 / 5.

---

## TEST 2 — Limit model: principle, not number

Graded per tier against `limit = workload model + security objective`, using Epic B (c)'s text at
`:194` and the Revision 5 summary at `:137-149`.

### Tier (i) — unauthenticated, state-mutating, no backstop (`/api/security/csp-report`) — **PARTIAL**

| Required | Present? |
|---|---|
| Specific attack/abuse prevented | **Yes.** Stated concretely: the route "inserts into the `security_events` table on every call with no auth check" (`:194`); `:145` names it as "writing into the security audit table itself". Verified live — `api.py:1930-1931`, `@app.post("/api/security/csp-report")`, undecorated, no auth dependency. The abuse (unauthenticated flooding of the security audit table, which also poisons the evidence trail Program 4 depends on) is unambiguous. |
| Specific legitimate workload admitted | **No.** The plan never states how many CSP reports a legitimate browser session emits, over what window, or how many concurrent users are assumed. Without that there is no floor. |
| Evidence connecting the two to a number/range | **No.** The text says "their own low, individually-justified limit" — that is a *commitment to justify*, deferred to implementation, not a justification. No number and no range appears. |

**Grade: objective yes, workload no, number not derivable.** An implementer following this text
would have to invent the workload model themselves, which is precisely the failure mode Revision 5
was written to eliminate.

### Tier (ii) — authenticated high-frequency UI-backend, no backstop (`/klijenti` search) — **PARTIAL**

| Required | Present? |
|---|---|
| Specific attack/abuse prevented | **No.** The tier is defined entirely by a *false-positive* concern (NAT sharing), not by an abuse it stops. `/klijenti` (`klijenti/router.py:263-296`) is a filtered client-list read returning up to 500 rows with an `ilike` search — the obvious abuse (a compromised session enumerating the whole client book, or driving unindexed `ilike` scans) is never named, so the *ceiling* has no rationale even in principle. |
| Specific legitimate workload admitted | **Yes, sketched.** "hit once per keystroke pause per lawyer" (`:194`) is a real workload model, and it is grounded — `static/vindex.js:20334` and `:20716` both call `/klijenti?pretraga=` from debounced type-ahead handlers. |
| Evidence connecting the two to a number/range | **No.** "derived from a real estimated office workload (not copied from an unrelated mechanism)" is again a commitment, not a derivation. No firm size, no keystroke rate, no number, no range. |

**Grade: workload yes, objective no, number not derivable.** The tier's most valuable content is
structural rather than numeric — and that part I was able to *confirm*: the plan's open question
("whether slowapi's per-decorator `key_func` override supports it — needs confirming during
implementation") resolves **affirmatively**. `extension.py:650`/`:663` accept a per-decorator
`key_func`, and T-F demonstrates it working under the middleware:

```
same office IP, user u1 x8: 8x200, 0x429
same office IP, user u2 x8: 8x200, 0x429
```

Two implementation constraints the plan should carry, both confirmed in source:
`extension.py:496` selects `key_func(request)` vs `key_func()` by **parameter name** — the override's
parameter must literally be named `request`, or it raises `TypeError`; and in production
`shared/rate.py:78` sets `swallow_errors=True`, so that `TypeError` would be **swallowed and the
route served unlimited**, while the no-Redis dev path (`shared/rate.py:86`) has no `swallow_errors`
and raises loudly. A tier (ii) `key_func` bug therefore fails loud in dev and **fails open in prod**.

### Tier (iii) — the unassessed remainder — **FAIL**

| Required | Present? |
|---|---|
| Specific attack/abuse prevented | **No** — beyond the generic "default-deny friction for routes nobody has individually reviewed yet" (`:194`). That is a *policy stance*, and a defensible one, but it is not an abuse model. |
| Specific legitimate workload admitted | **No, explicitly.** The plan states outright that it is "not a number claimed to be calibrated to a specific workload, since no such calibration has been done". |
| Evidence connecting the two to a number/range | **A range only** ("materially below 600, e.g. in the low hundreds/hour"), with the derivation explicitly disclaimed. |

**Grade: `limit = feeling` — but honestly labelled as such.** The honesty is a genuine improvement
over Revision 4 and should be credited; it is not the same defect as citing an inverted source. But
the grading criterion is met by neither half, and tier (iii) has two further problems:

1. **It is falsifiable, and it is falsified.** See Test 3 (3a): tier (iii) covers
   `/api/sesija/ping`, where the realistic load is ~3 000/hour per office IP. A limit does not get
   the benefit of "conservative, uncalibrated" when a known, in-repo, always-on client behaviour
   exceeds it by an order of magnitude. The plan's own Revision 4 narrative already flagged this
   route (`:103`: "a 60-second heartbeat, i.e. already at the limit boundary for one single user")
   and Revision 5's tier model dropped it.
2. **The denominator problem the 4th pass found is unresolved, only shrunk.** The critique at
   `:141` was `109 plain paths × 600 = 65 400/h per IP`. Revision 5 lowers the multiplicand but
   leaves the multiplication intact — `default_limits` is scoped per `_endpoint_key`, which under
   `key_style="url"` is `request["path"]` (`extension.py:559`, `:565`, consumed at `:488`). Measured
   (T-G): 10 undecorated routes, default `5/minute`, 6 requests each → **50 total 200s**, i.e. exact
   `N × D`. Live count is **119** undecorated plain paths, so `D = 200/h` still yields 23 800/h per
   IP in aggregate. The plan never mentions `application_limits`, which slowapi supports and which
   pins scope to the literal string `"global"` (`extension.py:281-296`) — a single shared bucket per
   key across the whole app, i.e. exactly the aggregate cap the 4th pass's critique calls for. That
   mechanism exists, is one constructor argument away in `shared/rate.py:68-82`, and is unmentioned.

### Test 2 summary

**0 of 3 tiers satisfy `limit = workload model + security objective`.** Tiers (i) and (ii) each
state one of the two required halves and defer the number; tier (iii) states neither and is
additionally falsified by a live route. The tier *structure* is right and is a real advance over a
flat number; what has not yet happened is the derivation the structure was created to make possible.

---

## TEST 3 — Enterprise-scale scenario (50 lawyers, one NAT IP, 5 000 predmeti)

Modelled against the live route table (599 routes, 155 undecorated: 119 plain + 36 parameterized),
the collapsed `Limiter` from `shared/rate.py:86`, and `extension.py`'s actual bucketing.

### 3.0 Which routes this firm actually hits, and under what

Traced from `static/vindex.js`:

| Route | Cadence (grounded) | Decorated? | Lands in |
|---|---|---|---|
| `POST /api/sesija/ping` | `setInterval(_sesijaPing, 60000)` — `static/vindex.js:189`, started at `:639` and `:710`, per tab, unconditional while logged in | **No** | tier (iii) |
| `GET /klijenti?pretraga=` | debounced type-ahead, `static/vindex.js:20334`, `:20716` | **No** | tier (ii) |
| `GET /api/jobs/{job_id}` | 4-second poll for up to 180 s per AI job — `static/vindex.js:3696-3715` | **No** | SEC-010 |
| `GET /api/me`, `/api/tos/status`, `/api/plan/status`, `/api/auth/trial/status`, `/api/firm/health-index` | once per app boot — `vindex.js:309`, `:719`, `:2634`, `:15388`, `:1207` | **No** | tier (iii) |
| `GET /api/predmeti` (`60/minute`), `/api/predmeti/dashboard` (`30/minute`), `/api/predmeti/{predmet_id}` (`60/minute`) | per navigation | **Yes** (`api.py:3290-3291`, `:3326-3327`, `:3440-3441`) | own decorator |
| `GET /notifications` | `setInterval(..., 15 * 60 * 1000)` — `vindex.js:11382` → ~4/h/user, 200/h/firm | Yes | own decorator |

### 3.1 Finding 3a — `/api/sesija/ping`: the `/klijenti` defect, structurally reproduced

`routers/sesije.py:151` — `@router.post("/api/sesija/ping")`, undecorated, docstring:
*"Heartbeat — poziva se svakih 60 sekundi dok je korisnik aktivan."* Confirmed against the client:
`static/vindex.js:187-189`.

Arithmetic for the scenario: 50 lawyers × 60 pings/hour = **3 000 requests/hour**, from **one** IP,
to **one** exact path. Two browser tabs per lawyer — routine — doubles it to 6 000/h. Tier (iii)'s
recommended "low hundreds/hour", keyed per IP per exact path, is exceeded by roughly **10-30×**.
Every ping past the cap returns 429; `_sesijaPing`'s `catch(e){}` (`vindex.js:170`) swallows it, so
the single-device/PRO-two-device enforcement built on `aktivne_sesije` degrades **silently** rather
than visibly — the failure is invisible to both the lawyer and the operator.

The important part is *why the tier model cannot see this*. Tier (ii) is scoped at `:194` to
"authenticated, high-frequency UI-backend routes **outside `/api/`** with **no existing per-user
backstop**". `/api/sesija/ping` fails both clauses: it is inside `/api/`, and it *does* have the
per-user backstop. So the plan's own criterion routes it to tier (iii). **But the exclusion criterion
is dimensionally wrong.** The backstop (`api.py:934`, `_USER_API_LIMIT = 600/hour`, applied by
`user_rate_limit_middleware` at `api.py:1000-1023` only when `path.startswith("/api/")`) is keyed by
**`user_id`**. The new tier (iii) default is keyed by **IP** (`shared/rate.py:44-54`,
`_get_real_ip`). NAT aggregation is an IP-keying problem; a per-user backstop provides exactly zero
mitigation for it. Using "has a per-user backstop" as the test for "is safe from the NAT problem"
therefore guarantees that the tier model will keep mis-sorting the highest-frequency routes in the
app — which is the same class of defect the 4th pass found on `/klijenti`, now reproduced by the
replacement model rather than fixed by it.

At least four more tier (iii) routes are on the same gradient, all fired once per app boot:
`/api/me`, `/api/tos/status`, `/api/plan/status`, `/api/auth/trial/status`, `/api/firm/health-index`.
At 50 lawyers × ~5 loads/day these sit in the tens-to-low-hundreds per hour — under "low hundreds"
but with no margin, and with the same silent-failure characteristic.

### 3.2 Finding 3b — 5 000 matters are unprotected against scraping, and SEC-011(d)'s remedy is a no-op

`extension.py:559` sets `endpoint_url = request["path"]`; `:565` sets
`_endpoint_key = endpoint_url` under `key_style="url"`; `:488` uses it as the bucket scope
(`limit_scope = lim.scope or endpoint`). The bucket is therefore the **concrete request path**, for
decorated and undecorated routes alike. Measured (T-E), decorated `/k/{kid}` at `3/minute`:

```
same id x8              : 3x200, 5x429
30 distinct ids x1 each : 30x200, 0x429
```

And (T-D) undecorated `/plain/{n}` under a `5/minute` default: `30 distinct paths → 30x200, 0x429`.

Applied to this firm: `GET /api/predmeti/{predmet_id}` is decorated `60/minute` (`api.py:3440-3441`)
— that is **60/minute per matter**, so across 5 000 matters the decorator imposes no aggregate
ceiling whatsoever. There is no second ceiling to fall back on: `shared/rate.py:68-86` never passes
`application_limits`, so `_application_limits` is empty and slowapi contributes no cross-path cap.
The only aggregate limit in the system is `_USER_API_LIMIT = 600/hour` per `user_id` for `/api/*`
(`api.py:934`) — which caps a full 5 000-matter scrape at ~8.3 hours, i.e. **one working day, with
zero 429s from slowapi**. `_USER_RATE` is an in-process dict (`api.py:930`), so with N gunicorn
workers the effective per-user ceiling is `600 × N`, shortening that further. And the entire
`/klijenti/*` CRM tree is outside `/api/`, so it has **no aggregate cap at all** — a compromised
session can walk `GET /klijenti/{klijent_id}` (`klijenti/router.py:333`) across the whole client
book at full speed regardless of what SEC-010 decorates it with.

This directly falsifies SEC-011(d) (`:195`): *"The resulting enumeration gap (36 undecorated routes
carry path parameters) is closed by folding those into SEC-010 below instead."* Decoration does not
change the bucket key. Under `key_style="url"`, a decorated parameterized route is bucketed
per-value exactly like an undecorated one — the remedy does not address the gap it is stated to
close. (The decision to leave `key_style="url"` untouched is itself sound, for the reason `:195`
gives — flipping it globally would silently re-bucket all 444 tuned limits. The error is the claim
that SEC-010 compensates. Closing this needs a different mechanism: `application_limits` for an
aggregate ceiling, or per-decorator `key_func` overrides on the scrape-prone routes, both of which
are confirmed available.)

### 3.3 What held up (attempts that failed to break the design at this scale)

- **Job polling.** `GET /api/jobs/{job_id}` at 4-second intervals for up to 180 s is up to ~45
  requests per job. Because the bucket is the concrete path, each job gets its own bucket, so 50
  lawyers running concurrent AI jobs do **not** contend. This is the one place where
  `key_style="url"` actively helps, and it holds. (Note the inverse: it would break if an implementer
  "fixed" 3b by flipping `key_style` to `"endpoint"` — the two findings pull in opposite directions
  and must be resolved per-route, not globally.)
- **Decorated navigation routes.** `/api/predmeti` at `60/minute` per IP for 50 lawyers is ~1
  list-load per lawyer per minute — tight but survivable, and it is a deliberately tuned number, not
  a default. `/notifications` at ~200/h firm-wide is comfortable. No false positive found.
- **The exemption list.** Revision 4's exemption list (`/health` and the platform healthcheck path,
  `:102`, `:112`) is not restated in Revision 5's rewritten (c), surviving only by reference in the
  Downgraded-claim paragraph (`:200-201`). I could not turn this into a finding — the list is not
  contradicted, only un-restated — but an implementer reading (c) alone would not know it exists.
- **Redis-outage window.** Confirmed as the plan describes (`:201-203`) and correctly excluded: with
  `in_memory_fallback` set to the same `["60/hour"]` (`shared/rate.py:76-77`), every route collapses
  to one shared bucket during an outage. Pre-existing, correctly disclaimed, not counted here.

---

## Closing note on scope

These are the three commissioned tests and nothing else. The verdict is BLOCKING on all three, but
the character of the findings is different from the prior four passes: Revision 5's *design choices*
— the collapse, the parity invariant, the tier structure, keeping `key_style="url"` — all survived
direct attack. What failed is the specification around them: an enumeration method with a proven
false negative (Test 1), three tiers whose numbers are still deferred rather than derived (Test 2),
and a tier-sorting criterion that is keyed on the wrong dimension, plus a bucket-key assumption that
makes one stated remedy a no-op (Test 3). All are correctable inside the current design; none
requires rethinking it.
