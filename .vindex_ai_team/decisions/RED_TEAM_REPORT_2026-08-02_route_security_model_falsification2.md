# Red Team Report — Route Security Model, Falsification Pass 2

**Date:** 2026-08-02
**Target:** `docs/architecture/ROUTE_SECURITY_MODEL.md` (post-correction state, "Revision 6" of the underlying decision)
**Mandate:** narrow, falsification-only. Assume the corrected model is WRONG. Find a minimal, realistic
scenario where implementing it exactly as specified still produces a **false sense of protection**.
Exactly 5 tests, no findings outside them.
**Environment:** `slowapi 0.1.9`, `limits 5.8.0`, `fastapi 0.135.3`, `starlette 1.3.1` — all measured, not assumed.

---

## VERDICT

| Test | Subject | Verdict |
|---|---|---|
| **Test 1** | Composite key correctness | **BLOCKING** |
| **Test 2** | Route completeness (hypothetical future routes) | **BLOCKING** |
| **Test 3** | CI bypass | **BLOCKING** |
| **Test 4** | Epic B self-test (5 original findings) | **BLOCKING** |
| **Test 5** | Scope boundary clarity | **BLOCKING** |

### **OVERALL: BLOCKING**

The document's corrections are real and, where I could measure them, they work: stacked-decorator
`composite` is genuinely enforced on both bounds (measured), and §6.4's pairwise-witness shadow
algorithm genuinely finds all four known pairs including the `spisi` fixture, non-circularly (measured).
Those two fixes are sound and I could not falsify them.

But every one of the five tests produced at least one **CI-green, registry-conforming entry whose
runtime behaviour I measured at 0×429** — i.e. a route the registry declares protected and that is, in
fact, completely unlimited. The failures share one generator, stated in §"Framing judgment" at the end.

---

## Test 1 — Composite key correctness — **BLOCKING**

### What I verified first (and could NOT falsify)

Harness: `scratchpad/t1_composite.py` — FastAPI app, real `SlowAPIMiddleware`, real `Limiter`, two
stacked `@limiter.limit(...)` decorators with distinct `key_func`s, exactly as §3 now prescribes.

Both bounds register under one route name and both are independently enforced. Registration dump:

```
__main__.comp_ip_user -> [('3 per 1 minute', 'user_key'), ('10 per 1 minute', 'ip_key')]
```

Measured:

| Scenario | Result |
|---|---|
| A1 — 10 users behind 1 IP, 3 reqs each (30) | **20×429** — coarse `ip` bound holds |
| A2 — 1 user on own IP, 6 reqs | **3×429** — inner `user_id` bound holds |
| A3 — same user rotating across 6 IPs (one attacker → one victim) | **3×429** — user bound survives IP rotation |
| C1 — banned single concatenated key `f"{ip}\|{user}"`, 30 reqs | **0×429** — anti-pattern reproduced exactly as documented |

Mechanism confirmed in source: `extension.py:704` `self._route_limits.setdefault(name, []).extend(...)`
accumulates both bounds under one name (`functools.wraps` preserves `__name__`); `extension.py:487-528`
`__evaluate_limits` iterates all of them in a single pass. §3's corrected `composite` mechanism is
**correct for the `ip`+`user_id` pairing it works through.** I could not break it. That part is closed.

### The falsification — `user_id` + `tenant_id` composite

§3's Identity Dimension table lists `tenant_id` as a first-class dimension. §6.1's schema says `limiter`
is "a LIST when identity_dimension is `composite` (two bound objects, **e.g.** one ip-keyed, one
user_id-keyed)" — `e.g.`, an example, not a constraint. §6.4 check 2 requires only "2 entries if
`identity_dimension: composite`". Nothing in the document constrains *which* two dimensions.

So I built the `user_id`+`tenant_id` composite the document permits (`/comp_user_tenant`, tenant bound
10/min coarse, user bound 3/min inner). Mechanically it works fine — B1 (1 tenant / 10 users / 3 each)
gave 20×429, B3 (1 user, 6 reqs) gave 3×429. The bounds are real.

**But measure it against the threat §3 says `composite` exists to stop.** §3's own justification text:

> *"pure `user_id` gives zero protection against many-throwaway-accounts IP floods"*

That is the defining threat. Measured against it:

```
B2  5 tenants / distinct users / 3 reqs each : 15 reqs, 0 x429, 15 x200
C1  banned concatenated key, 1 IP / 10 users : 30 reqs, 0 x429, 30 x200
```

**Zero protection — the same result as the anti-pattern the correction was written to ban.**

This is not hypothetical for this codebase. Both dimensions are attacker-mintable:
- `api.py:2298-2300` — `POST /api/register`, `@limiter.limit("5/minute")` → ~300 accounts/hour per IP.
- `routers/kancelarija.py:216-241` — `POST /api/kancelarija/kreiraj`, `Depends(get_current_user)` only,
  one firm per admin. **Every new account can mint its own new tenant.**

So an attacker with N accounts has N tenants, and *both* bounds of a `user_id`+`tenant_id` composite
are per-attacker-controlled. The composite is a strict no-op against many-throwaway-accounts.

**Why this is a false sense of protection, not a mis-configuration:** the entry is fully conforming.
`identity_dimension: composite`, `limiter` is a 2-entry list, all enums valid, all §5 predicates
satisfiable. It passes every one of §6.4's seven checks. A reviewer reading `composite` inherits §3's
stated security property. Nothing — prose or CI — states the invariant that actually makes composite
work: **at least one bound must be keyed on an identity the attacker cannot cheaply mint.**

The document specified the *mechanism* (two decorators) and did not specify the *property* the
mechanism must achieve. That is structurally the same error as the original `composite` defect, one
level further in.

### Secondary (same test, supporting)

§6.4 check 4: *"`sustained` (from **each** `limiter` entry) must be numerically ≥ the number extracted
from `expected_workload`"* — one number, applied to every bound. But composite's two bounds are
dimensionally different: the coarse `ip` bound must sit above *aggregate* office traffic (50 lawyers ×
80/h ≈ 4,000/h), the inner `user_id` bound above *per-seat* traffic (80/h). Satisfying check 4 with one
extracted number forces both bounds to the same order of magnitude. Set both to 4,000/hour and CI is
green while the per-user ceiling is 50× too loose — the registry says "composite, per-user ceiling
enforced," the runtime has no meaningful per-user ceiling. This is Epic B finding #4's dimensional
error recurring inside the CI spec that was written to prevent it.

---

## Test 2 — Route completeness (hypothetical future routes) — **BLOCKING**

Harness: `scratchpad/t2_shapes.py` — one app containing all five shapes plus two `Mount`s mirroring
`api.py:791` / `api.py:801`, then walking `app.routes` exactly as §6.3 step 1 prescribes.

### (a) plain GET / (b) state-mutating POST / (c) WebSocket / (e) internal-service — CLOSED

All four appear in `app.routes` with the attributes §6.1/§6.3 rely on. The enumerator produces
`GET /plain`, `POST /mutate`, `WS /ws`, `POST /cron/daily`; §6.4 check 1 (coverage) then forces an entry
for each. I tried to construct a variant of (b) or (e) that evades enumeration and could not — FastAPI
flattens `include_router` into `app.routes`, so router-mounted routes are all visible. **Closed.**

(I note (b) and (e) can be *mis*-classified — a mutating POST tagged `threat: [dos]` passes — but the
model is honest about this: §6.3 step 3 explicitly disclaims automatic-classification accuracy. Not a
false-sense-of-protection scenario on its own; the CI-green version of it is Test 3.)

### (d) SSE / streaming HTTP — the falsification

§1 defines `non-http-stream` as: *"A WebSocket or other long-lived-connection route… **cannot be
rate-limited by slowapi at all** — verified: `SlowAPIMiddleware`'s decorator raises at connection time
if the handler isn't a plain HTTP `Request`."*

**I measured this against a real SSE route and the claim is false for streaming HTTP.** An SSE endpoint
takes a plain `Request` and returns a `StreamingResponse`; the decorator applies normally:

```
6 sequential SSE requests -> [200, 200, 200, 429, 429, 429]     (3/minute, enforced)
```

So an implementer reading §1 correctly concludes SSE is **not** `non-http-stream` — slowapi *can* limit
it. They classify it `authenticated-user` + `cost-amplification`, give it `burst`/`sustained`, CI goes
green. Then:

```
12 concurrent streams from 12 distinct IPs -> [200 x12]
peak simultaneously-open generators: 12
```

The rate limit governs **connection initiation**, not **open duration or concurrency**. Long-lived
streams accumulate without bound. Even from a single IP, a 3/minute limit permits 3 new held-open
streams every minute, forever.

The model already *knows* rate ≠ concurrency — that is exactly why it added the `concurrency` field.
But §6.1 makes that field structurally unreachable for this shape:

> `concurrency: … # REQUIRED **instead of** limiter for non-http-stream routes`

`concurrency` is gated behind `classification: non-http-stream`, and §1 defines that classification by a
property (slowapi can't limit it) that SSE does not have. **For a streaming-HTTP route the model
mandates the wrong control and forbids the right one.**

Compounding it: §6.1 offers `"SSE <path template>"` as a registry key form, but §6.4 check 1 derives
keys from the live route table, where an SSE route is an ordinary `APIRoute` with `methods={'GET'}` /
`{'POST'}`. My enumerator dump:

```
APIRoute   methods={'GET'}   path=/sse   has_endpoint=True
```

An entry keyed `"SSE /api/pitanje/stream"` therefore **fails** coverage (the live key is `POST …`), and
the conforming `"POST …"` key carries no stream semantics. **The `"SSE"` key form is unreachable by the
model's own enumeration algorithm, and nothing in the model can distinguish an SSE route from a plain
one.**

This is live, not hypothetical: **`api.py:2973-2974` `POST /api/pitanje/stream`,
`@limiter.limit("10/minute")`, returning `StreamingResponse(media_type="text/event-stream")`
(`api.py:3068-3070`)** — an LLM-backed, credit-metered route, i.e. genuinely `cost-amplification`. Each
held-open stream pins a worker and an in-flight model call. Its registry entry will read
`burst/sustained`, pass CI, and declare a protection the route does not have.

### Mount — a second miss in the same test

`Mount` objects have no `.methods` and no `.endpoint`. §6.3 step 1's corrected rule says *"any route
object lacking a `.methods` attribute must be enumerated into the `"WS <path>"` key form"* — so a
`StaticFiles` mount becomes `WS /static`, `classification: non-http-stream`, requiring a `concurrency`
bound. That is nonsense, and it passes CI.

Worse, the routes *inside* a mounted ASGI sub-app are not in `app.routes` at all, so coverage check 1
can never see them — and slowapi skips them entirely:

```
_find_route_handler('/sub/inner') -> None
_should_exempt                    -> True
80 reqs to mounted /sub/inner  (default 60/hour) -> 0 x429
80 reqs to top-level /plain    (same default)    -> 20 x429
```

Source: `middleware.py:24` requires `hasattr(route, "endpoint")`, so a `Mount` never yields a handler;
`middleware.py:100-101` — `if handler is None: return True` → the middleware returns before any limit is
evaluated. Every route under a mounted sub-app is **unlimited and invisible**, while the registry shows
100% coverage. The repo has two live `Mount`s today (`api.py:791`, `api.py:801`, both `StaticFiles` —
currently benign); a future `app.mount("/api/v2", sub_app)` is an entirely ordinary move for a 600-route
codebase and would silently produce a fully unprotected, fully "covered" surface.

---

## Test 3 — CI bypass — **BLOCKING**

I wrote candidate entries against §6.4's seven checks as literally specified. Three got through.

### Bypass 3-A — check 4 is a lower bound only ("raise the number until it stops mattering")

```yaml
"GET /api/klijenti/{klijent_id}/dokumenta":
  classification: [authenticated-user]
  threat: [dos]
  identity_dimension: user_id
  scope: per_value
  limiter:
    - strategy: user_id
      burst: "600/minute"
      sustained: "10000/hour"
  rationale:
    formula: "1 lawyer/hour baseline x 10000 headroom"
    reason: "default-deny friction"
    expected_workload: "1 lawyer per hour"
  reviewed: true
```

Walk the checks: (2) all enums valid, `limiter` present. (3) `scope` present; `threat` is `[dos]` not
`[scraping]`, so `per_value` is permitted. (4) `expected_workload` has a number (`1`), a time unit
(`per hour`) and an actor noun (`lawyer`) → passes; `formula` contains `1`, which appears in
`expected_workload` → passes; `sustained` 10000 ≥ 1 → passes. (5) `"default-deny friction"` is not one
of the two denylisted literals — and it is copied verbatim from §6.2's own `simulator` pilot entries.

**A 10,000/hour ceiling justified by a 1/hour workload is CI-green.** §5's stated intent was *"the
ceiling must sit above the stated legitimate workload, with the headroom multiplier named in `formula`
— not simply asserted"*, but §6.4 check 4 implements only `sustained ≥ workload`. There is no upper
bound and no check that the named multiplier is the one actually used. The check is monotone in the
wrong direction: **the cheapest way to pass CI is to make the limit meaningless** — precisely the
anti-pattern §4 names ("raise the number until it stops mattering").

### Bypass 3-B — check 3 fires only on `scraping`, never on `enumeration`

§6.4 check 3: *"An entry with `threat` including `scraping` and `scope: per_value` fails."* Only
`scraping`. But §2 defines `enumeration` as *"Discovering **which** IDs/users/resources exist"* — which
is exactly what per-value bucketing fails to stop, since each probed ID gets its own fresh bucket.
`threat: [enumeration]` + `scope: per_value` passes CI while providing literally zero enumeration
protection. (§6.2's own `GET /klijenti` entry carries `threat: [scraping, enumeration]`, so an
implementer dropping `scraping` to keep `per_value` is a one-token edit.) The brief asked whether the
check "only catches it in the one direction described" — confirmed, it does.

### Bypass 3-C — no cross-field check between `classification` and `identity_dimension` (measured no-op)

§6.4 check 2 validates each field against its own enum, independently. Nothing rejects
`classification: [public]` (unauthenticated) with `identity_dimension: user_id`. §3 requires the
identity-unavailable fallback be stated *in `rationale.reason` prose* and says omitting it "is treated
the same as a missing required field (§5)" — **but §6.4's seven checks contain no check for it.** The
mandate is prose-only.

Measured (`scratchpad/t34.py`), a route declaring 5/minute whose `user_id` key_func returns `""`:

```
40 reqs, no X-User (key_func -> "")  -> 0 x429     <-- completely unlimited
10 reqs with X-User                  -> 5 x429
```

Source: `extension.py:501-502` `args = [limit_key, limit_scope]` / `if all(args):` — a falsy key skips
the limit; `extension.py:519-523` logs `logger.error("Skipping limit… Empty value found")` and
`continue`s. A swallowed log line is the only signal.

**A registry entry that passes all seven §6.4 checks, declares a 5/minute ceiling, and is a total
runtime no-op.**

### What I tried that FAILED to bypass

- **Empty-ish descriptions.** `expected_workload: "1"` fails check 4 (no time unit, no actor). Good.
- **The two denylisted literals** are genuinely caught by check 5 without `reviewed: false`. Good.
- **`reviewed: false` as a blanket escape.** Correctly still subject to checks 1-3. Good.
- **Omitting `scope` on a parameterised route.** Correctly fails check 3. Good.
- **Copying §6.2's `GET /api/predmeti/{predmet_id}` verbatim with the route name changed.** This *does*
  pass (workload "…~60 detail views/hour per lawyer" → number 60, unit `/hour`, actor `lawyer`; formula
  cites 60; sustained 600 ≥ 60). But I judged this **not** a finding on its own: unlike 3-A it asserts a
  plausible, real derivation, so it is copied *reasoning*, not content-free boilerplate. Logged for
  completeness, not counted.

---

## Test 4 — Epic B self-test — **BLOCKING**

### Finding #2 — unscoped default landing on `/health` — **CAUGHT (closed)**

Coverage (check 1) forces an entry; §2 forbids waiver-by-omission; §4 explicitly names healthchecks;
and check 7 cross-checks the `exempt: true` claim against an actual `@limiter.exempt` registration
rather than mere absence of a decorator. I tried to construct a `/health` entry that hides the problem
and could not — any entry must either claim exemption (verified by check 7) or state a limit (which
surfaces the restart-loop question). **Genuinely closed.** Check 7 is the one place in the document
where a registry claim is bound to a runtime witness, and it works.

### Finding #4 — dimensionally-wrong tier-sorting of `/api/sesija/ping` — **CAUGHT (closed, with a caveat already logged)**

§5's `expected_workload` predicate forces a numeral+unit+actor, so the author must write something like
"3,000/hour from 50 lawyers behind one office IP." Check 4 then requires `sustained ≥ 3000` on an
**`ip`-keyed** bound — which makes the dimensional error visibly absurd on the page and pushes toward
§4's exemption. I could not construct a version where the mis-sort stays hidden. **Closed.** The
residual — that the escape from check 4 is always "raise the number" — is Test 3-A, and the composite
variant is Test 1's secondary; both already counted, not double-counted here.

### Finding #3 — route shadowing (slowapi last-match vs Starlette first-match) — **PARTIAL**

I implemented §6.4 step 6's pairwise-witness algorithm literally (`scratchpad/t4_shadow.py`), using
Starlette's own `compile_path`, over the known route set. It found **4/4** pairs:

```
/api/spisi/{spis_id}/verzije/latest  vs  /api/spisi/nacrti/verzije/{verzija_id}  -> /api/spisi/nacrti/verzije/latest
/api/simulator/{predmet_id}/partije  vs  /api/simulator/partija/{partija_id}     -> /api/simulator/partija/partije
/klijenti/retention-check            vs  /klijenti/{klijent_id}                  -> /klijenti/retention-check
/api/predmeti/{predmet_id}           vs  /api/predmeti/bulk                      -> /api/predmeti/bulk
```

§7's Test D asks whether finding the `spisi` fixture is circular. **It is not** — the same unmodified
algorithm found the three independently-known real pairs. The core algorithm is sound for HTTP-vs-HTTP
and I could not construct a same-method, same-segment-count pair it misses. That much is closed.

**But it misses `Mount`-vs-route shadowing entirely**, and this is a real bypass. Measured:

```
GET /static/config.json served by  -> {"served_by":"StaticFiles"}   <-- the Mount won
30 reqs (decorator declares 2/minute) -> 0 x429
slowapi _find_route_handler -> static_cfg
_should_exempt              -> True
route in _route_limits?     -> True
```

Starlette serves the first full match (the `Mount`, registered at `api.py:791`); the decorated
`/static/config.json` endpoint body never executes, so its decorator never runs. Meanwhile
`_should_exempt` returns `True` because the name *is* in `_route_limits` (`middleware.py:110-111`), so
the middleware also stands down. **Both paths decline; the route is completely unlimited.** §6.4 step 6
cannot see this pair: its loop is over "every **pair of routes** sharing the same HTTP method and the
same segment count," and a `Mount` has neither attribute. Its third bullet handles `{x:path}`-style
converters, not `Mount`s.

Note also what this proves about the **oracle**: §6.4 step 6 designates `_route_limits` membership as
the decorated/exempt oracle *"since the actual runtime behavior is what must be checked."*
`static_cfg` **is** in `_route_limits` and is measured at **0×429**. Membership in `_route_limits` is
not runtime behaviour. (Carried into Test 5.)

### Finding #5 — the `key_style="url"` scrape no-op — **NOT CLOSED. This is the sharpest finding.**

§6.1 defines the fix as: *"`fixed` = an explicit `scope=` override collapsing all values into one shared
bucket (the correct choice whenever `threat` includes `scraping`)."*

**`Limiter.limit()` has no `scope` parameter.** Measured directly:

```
limit()        params: ['self','limit_value','key_func','per_method','methods',
                        'error_message','exempt_when','cost','override_defaults']
shared_limit() params: ['self','limit_value','scope','key_func','error_message',
                        'exempt_when','cost','override_defaults']
```

`scope` is accepted only by `shared_limit` (`extension.py:823-832`), and `extension.py:660`
(`_scope = scope if shared else None`) confirms it is honoured only when `shared=True`. **The document
never names `shared_limit` anywhere.**

Measured consequence — a registry entry declaring `scope: fixed` on a route decorated with a plain
`@limiter.limit`:

```
C. registry `scope: fixed`, plain @limiter.limit, key_style='url'
   30 DISTINCT klijent ids -> 0 x429      <-- Epic B finding #5, verbatim
   30 reqs to ONE id       -> 20 x429

D. shared_limit(scope=...)  (the mechanism that actually works, unnamed in the doc)
   30 DISTINCT predmet ids -> 20 x429
```

And it passes CI. §6.4 check 3 verifies only that a `scope` **field is present** and that
`scraping`+`per_value` isn't claimed. **There is no check that `scope: fixed` corresponds to any runtime
scope override** — even though the document demonstrably knew to write exactly that kind of check for
`exempt` (check 7, quoted above: *"must correspond to an actual `@limiter.exempt(...)` registration —
not merely to the absence of a decorator"*). The identical reasoning was not applied to `scope`.

The result is finding #5 reproduced *inside* the corrected model, and made worse: the registry now
**affirmatively asserts** scrape protection (`scope: fixed`, `threat: [scraping]`) for a route measured
at 0×429 across 30 distinct IDs. Before the model, the route was silently unprotected; after it, it is
documented as protected.

Repo state: `shared_limit` appears **zero** times and `scope=` appears **zero** times across the
codebase — so today `scope: fixed` has no implementation anywhere, and the first engineer to implement
it will hit `TypeError` on `limiter.limit(..., scope=…)` with no guidance in the document toward the
API that actually works.

### Finding #1 — two-`Limiter`-instance wiring — **the scoping is legitimate in principle, but its placement is not, and it is currently producing false green**

§6's scope-boundary paragraph is honest and I agree with its *premise*: which `Limiter` instance
enforces a route is an application-wiring property, not a per-route property, and a per-route registry
structurally cannot carry it. As a scoping decision that is defensible, not an excuse.

**The placement is the defect.** §6 says instance wiring *"should be a standing CI check **alongside,
not inside**, §6.4."* But §6.4's own checks read that very object:

- check 6: *"The decorated/exempt oracle this check reads is **`app.state.limiter._route_limits`** and
  **`app.state.limiter._exempt_routes`** only"*
- check 7: `exempt: true` must correspond to an actual exemption registration — resolvable only via the
  same instance.

So §6.4 **consumes as a silent precondition** the exact property §6 declares out of scope. If the
one-instance property does not hold, checks 6 and 7 do not degrade — they read the wrong object and
return green.

**It does not hold in this repo today.** Measured:

| Evidence | Location |
|---|---|
| Instance #1 created, assigned to `app.state.limiter` | `api.py:547`, `api.py:549` |
| Instance #2, a separate module-level singleton | `shared/rate.py:89` |
| Modules importing instance #2 (`from shared.rate import limiter`) | **93** |
| `@limiter.limit` / `@limiter.exempt` decorations in `routers/` + `klijenti/` (all on instance #2) | **415** |

`shared/rate.py:59-68` documents this state explicitly and in the present tense: *"dve odvojene Limiter
instance i dalje postoje u ovom kodu … arhitektonska duplikacija, poznata, van obima SEC-005."*

Consequence for §6.4 as written: its oracle is `app.state.limiter` = instance #1, whose `_route_limits`
contains **only `api.py`'s own decorated routes**. All 415 router decorations are invisible to it.
Therefore:

- **Check 6** sees every router-module route as *undecorated*. A shadow pair between two router routes
  reads as "neither decorated → no divergence → **PASS**," even where a genuine decoration mismatch
  exists. A pair spanning `api.py` and a router reads as a bypass that may not be one. Both directions
  wrong.
- **Check 7** cannot resolve any router-module exemption at all.

So the answer to the brief's question is: **the scoping is legitimate, the "alongside, not inside"
placement is not.** The wiring check must be a **hard gate that runs before checks 6 and 7 and aborts
them if violated** — because those checks' correctness is *derived from* it, not merely adjacent to it.
A model whose CI returns green while reading an oracle blind to 415 of the app's decorations is
delivering exactly the false sense of protection this pass was asked to look for.

---

## Test 5 — Scope boundary clarity — **BLOCKING**

The distinction between (a) registry/declared intent, (b) runtime limiter wiring, (c) `SlowAPIMiddleware`
behaviour, and (d) framework/library behaviour is **stated well in exactly one place** — §6's
scope-boundary paragraph, which is clear, correct, and honestly written. Outside that paragraph it is
blurred in four places, three of them inside sections added by the corrections.

**5-1 — §6.4 check 6 presents (a′) as (b).** *"…and not the registry's own `limiter`/`exempt` fields in
isolation, since **the actual runtime behavior is what must be checked**, not just what the registry
claims."* The oracle it designates is `_route_limits` membership — which is **decorator-registration
state, not enforcement state**. Test 4's Mount measurement disproves the equation directly:
`static_cfg` is in `_route_limits` and measured 0×429. The sentence claims (b)-grade truth for an
(a′)-grade signal, in the section written to fix the declared-vs-enforced defect class.

**5-2 — §6.4 checks 6 and 7 depend on (b) without declaring it.** Covered in Test 4 finding #1. §6 says
instance wiring is out of scope; §6.4 then reads `app.state.limiter` as authoritative. The dependency
is never stated, so a reader has no way to know that §6.4's green is conditional.

**5-3 — §1's `non-http-stream` row misattributes (c) vs (a).** *"`SlowAPIMiddleware`'s decorator raises
at connection time if the handler isn't a plain HTTP `Request`."* `SlowAPIMiddleware` has no decorator.
The raise is in the `@limiter.limit` **decorator's** wrapper — `extension.py:724-727`
(`if not isinstance(request, Request): raise Exception(…)`). The middleware never sees a WebSocket at
all: `SlowAPIASGIMiddleware.__call__` returns early on `scope["type"] != "http"` (`middleware.py:147-148`),
and `SlowAPIMiddleware` is a `BaseHTTPMiddleware`. Decorator (a) and middleware (c) are conflated in the
row added to fix a (c)/(d) problem — and the same sentence's over-broad generalisation ("cannot be
rate-limited by slowapi at all") is what produces the SSE gap in Test 2.

**5-4 — §6.1's `scope` field presents (a) as if it named a working (b) mechanism.** *"`fixed` = an
explicit `scope=` override"* — `scope=` is not a parameter of `limiter.limit` (measured, Test 4 #5). A
registry-field value is described in terms of a runtime API call that does not exist, with no statement
that the binding between the two is unverified. This is the single most direct instance of the defect
class, in the field added to close Epic B finding #5.

---

## Framing judgment (explicitly requested)

**This should become a separate "Security Governance Framework" epic, not another Epic B patch.**

The individual findings are rate-limiting-specific in their *details* (composite dimension choice,
`shared_limit` vs `scope=`, SSE concurrency, `Mount` enumeration). Patching them one at a time is
exactly the loop the model document was written to end, and this pass is the seventh consecutive one to
find a genuine defect. Two reasons the theme is broader:

**1. Every finding in all five tests has the same shape.** The document declares a control and asserts a
security property, without a check that **binds the declaration to an executable runtime witness.**
§6.4 gets this right in exactly one place — check 7, for `exempt` — and I could not falsify that check.
It has no equivalent for `scope` (Test 4 #5), none for `identity_dimension`'s unavailable-identity
fallback (Test 3-C), none for `composite`'s dimension choice (Test 1), none for `concurrency` (Test 2).
The missing primitive is not "a better rate-limit taxonomy," it is: **every declared control must have a
runtime witness, and CI must fail when the witness is absent.** That principle is not specific to rate
limiting — it applies identically to RLS policies, auth dependencies, and PII redaction, all of which
this codebase declares in prose today. Generalising check 7 is the actual deliverable.

**2. There is a live prerequisite that no amount of registry work can fix.** The two-`Limiter`-instance
state (93 modules, 415 decorations on the instance `SlowAPIMiddleware` never reads —
`api.py:547/549` vs `shared/rate.py:89`) means §6.4's own oracle is currently reading the wrong object.
**Until that is collapsed, checks 6 and 7 return green for reasons unrelated to whether routes are
protected.** This must be sequenced *before* registry population, not "alongside" it. It is
application-wiring remediation, not a per-route task — which is exactly why it does not belong to
Epic B, and exactly why leaving it as a footnote in §6 is the wrong call.

**Recommended sequencing:** (i) collapse to one `Limiter` instance and make "exactly one instance, bound
to `app.state.limiter`" a hard CI gate that *precedes* §6.4; (ii) generalise check 7 into a
declaration→runtime-witness rule and apply it to `scope`, `identity_dimension`, and `concurrency`;
(iii) only then populate the registry across the remaining ~590 routes. Steps (i) and (ii) are the
Security Governance Framework epic; step (iii) is what remains of Epic B.

---

## Reproduction artifacts

| File | Covers |
|---|---|
| `scratchpad/t1_composite.py` | Test 1 — stacked composite (ip+user, user+tenant), concatenated-key anti-pattern |
| `scratchpad/t2_shapes.py` | Test 2 — five route shapes, `app.routes` enumeration, SSE rate-vs-concurrency, Mount |
| `scratchpad/t34.py` | Tests 3/4 — falsy key_func no-op, `scope: fixed` divergence, `shared_limit` control, Mount shadow |
| `scratchpad/t4_shadow.py` | Test 4 — §6.4 step 6 pairwise-witness algorithm, literal implementation |

All measurements are from `slowapi 0.1.9` / `limits 5.8.0` / `starlette 1.3.1` as installed at
`C:\Users\Benny\miniconda3\Lib\site-packages\slowapi`.
