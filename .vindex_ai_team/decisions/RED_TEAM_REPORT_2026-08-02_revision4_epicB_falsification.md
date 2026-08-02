# Red Team Report — Revision 4, Epic B, two-question falsification

**Date:** 2026-08-02
**Reviewer role:** Red Team / Devil's Advocate (fourth pass, fresh agent, no authorship stake)
**Scope (strict, founder-specified):** exactly two questions — (1) exemption bypass, (2) is `600/hour`
a real number. The collapse mechanism, the `key_style` decision, SEC-048, SEC-010's general scope, and
every other epic were **not** reviewed and are not covered by this verdict. No incidental-observations
section, by instruction.
**Target under review:** `.vindex_ai_team/decisions/2026-08-02_forensic-remediation_ARCHITECTURE_DECISION.md`
lines 155–180 (Epic B, Revision 4).
**Environment ground truth:** slowapi **0.1.9** at `C:\Users\Benny\miniconda3\Lib\site-packages\slowapi\`,
read directly. The FastAPI app was **loaded in-process** (`import api`) and its live route table
enumerated — 602 route objects, 444 decorated, 156 undecorated route objects / 154 distinct endpoint
names. Every count in this report is measured, not inherited from a prior pass.

---

## VERDICT

| Question | Verdict |
|---|---|
| **Q1 — Exemption bypass** | **BLOCKING** |
| **Q2 — Is `600/hour` a real number** | **BLOCKING** |
| **Overall** | **BLOCKING** |

**Q1** — the exemption *list* is correct and complete; I could not find a route that needs exemption and
is missing. The exemption *mechanism* fails concretely: Revision 4's own item (d) — decorating
`/klijenti/{klijent_id}` under SEC-010 — causes `GET /klijenti/retention-check` to be silently treated
as exempt and to lose **all** rate limiting, because slowapi's `_find_route_handler` resolves
**last-match-wins** while Starlette dispatches **first-match-wins**. Reproduced in-process against the
real route table.

**Q2** — the plan's stated rationale is not merely thin, it is **inverted**. `api.py:924`, the line the
document cites as its authority, says this mechanism is *"Dopuna IP-based slowapi limitera: prati pozive
po user_id"* — a **supplement to** the IP limiter, keyed **per user_id**. `api.py:925` says the limits
are *"namerno blaži od IP limita"* — deliberately **laxer than the IP limits**. Revision 4 cites this to
justify adopting `600` **as** the IP limit. The two limits have different denominators (per-user /
all-paths vs. per-IP / per-path), so the number is simultaneously ~109× too permissive in aggregate and
stricter per-path for the exact NAT'd-office scenario the plan invokes. The document names no attack it
prevents and performs no workload calculation.

---

# Q1 — Exemption bypass

## 1.1 What Revision 4 specifies

Lines 158(c): exempt *"at minimum"* — `/health`, `/api/sesija/ping`, the app-shell routes (`/`, `/app`,
`/portal`, `/sw.js`, `/manifest.json`, `/offline`), and `/viber/webhook`.

## 1.2 Coverage half — I could NOT break it

I re-derived the undecorated set from the live app rather than trusting the document, then swept it with
the same reasoning pass 3 used (platform-level / high-frequency / webhook-style). Measured:

- 602 route objects; 444 decorated (29 on `api.py`'s instance, 415 on `shared.rate.limiter`'s —
  matching the document's numbers exactly); **156 undecorated route objects**.
- Revision 4's exemption list matches **11 route objects / 9 endpoint names** (`/health` is registered
  twice, GET+HEAD, `api.py:1491-1493`; `/` is registered GET+HEAD).
- Remainder: **145**, of which **36 are parameterized** (exactly the document's figure — independently
  reproduced) and **109 are plain paths** landing on the app-wide default.

**Attempts that failed to find a missing exemption:**

| Attempt | Result |
|---|---|
| Is `/health` even the right path? | **Yes.** `railway.toml:5` → `healthcheckPath = "/health"`. `healthcheckTimeout = 30`, `restartPolicyType = "ON_FAILURE"`. The list names the correct path. No second platform healthcheck exists. |
| Other health-ish endpoints left unscoped | `/v1/health` (`routers/integracije.py:202`, unauthenticated, for external integrations) and `/api/status/public` are undecorated and unexempted. Neither is a *platform* healthcheck; a third-party monitor at a 30s interval draws 120/h against a 600/h bucket. No restart-loop equivalent. **Not a concrete break.** |
| Other inbound provider webhooks | Enumerated every `webhook`/`callback` route. `/v1/webhook/clio`, `/v1/webhook/imanage`, `/api/webhooks/*`, `/api/integrations/webhook/register`, `/api/integrations/webhook/test/{id}` are **already decorated** → `_should_exempt` returns True on the `_route_limits` branch, the app-wide default never touches them. `/viber/webhook` is the only undecorated inbound provider webhook, and it **is** exempted. `/api/integrations/gcal/callback` (`routers/integrations.py:257`) is an authenticated OAuth code-exchange behind `Depends(get_current_user)`, once per integration setup — not a provider push webhook. No inbound Twilio/WhatsApp webhook exists (`routers/sms.py`, `routers/whatsapp_notif.py` are all outbound-send / subscription-management). **Category fully covered.** |
| Other timer-driven / high-frequency clients | Enumerated every `setInterval` in `static/vindex.js`. Only three make network calls: `_sesijaPing` at 60s (`:189` → `/api/sesija/ping`, **exempted**); `strat_job_poll` at 4s (`:3707-3715` → `/api/jobs/{job_id}`, parameterized → SEC-010); `_genomeBackgroundWatch` at 15s × 6 (`:19348` → `/api/predmeti/{id}/case-dna`, parameterized → SEC-010); `notif_load` at 15min (`:11382` → `/notifications`, already decorated). Service worker: `static/sw.js:186-189` `periodicsync` → `/api/notifications/rokovi-check`, already decorated. **No additional high-frequency client hits any of the 109.** |
| Cron/scheduler endpoints | 7 of them (`/api/cron/daily`, `/api/briefing/cron`, `/api/briefing/nightly-intelligence`, `/api/portal/cron-proveri`, `/api/workflow/eskalacije/cron`, `/api/zakon-monitoring/cron`, `/api/rokovi/guardian/scan`). Daily/nightly cadence from one scheduler IP. 600/h is three orders of magnitude of headroom. **Not a break.** |
| WebSocket route | `/api/voice/realtime/ws` is undecorated and unexempted, but `SlowAPIMiddleware` extends `BaseHTTPMiddleware`, which short-circuits any `scope["type"] != "http"`. Never reached. **Not a break.** |

**Coverage conclusion: I found nothing to add to the exemption list.** The four named categories are the
right four, and on an independent sweep of all 156 undecorated routes they are complete.

## 1.3 Mechanism half — the exemption primitive itself holds

I exercised `limiter.exempt` for real (not by mutating `_exempt_routes` by hand) against the live app:

- `extension.py:864-885` — `exempt(obj)` registers `f"{obj.__module__}.{obj.__name__}"` and returns a
  `@wraps`-preserving wrapper. **No signature inspection**, unlike `limit()` (`extension.py:706-714`,
  which raises on a missing `request`/`websocket` param). This matters concretely: `api.health`
  (`api.py:1493`) is `def health():` — sync, zero parameters. Verified `limiter.exempt(api.health)`
  succeeds, preserves `__module__`/`__name__`, and preserves the signature through `__wrapped__`.
- Both `/health` registrations resolve to `api.health`: `GET → exempt=True`, `HEAD → exempt=True`.
- Ordering is a non-issue: `_should_exempt` (`middleware.py:98-114`) reads `limiter._exempt_routes` and
  `SlowAPIMiddleware.dispatch` reads `app.state.limiter` **at request time**, not at registration time.
  Adding the middleware before or after decoration/exemption cannot change the outcome.
- All 9 exempted paths resolve to exactly the handler whose name is exempted, with **no** competing full
  match — I checked each one against the whole route table. **No exempted route is shadowed.**

## 1.4 Mechanism half — BLOCKING: newly-decorated `/klijenti/{klijent_id}` un-scopes a sibling route

This is the concrete instance of the `_find_route_handler` trap pass 3 flagged as latent.

**The primitive.** slowapi `middleware.py:18-25`:

```python
def _find_route_handler(routes, scope):
    handler = None
    for route in routes:
        match, _ = route.matches(scope)
        if match == Match.FULL and hasattr(route, "endpoint"):
            handler = route.endpoint       # <-- keeps overwriting: LAST match wins
    return handler
```

Starlette `routing.py:672-684` does the opposite — it `return`s on the **first** `Match.FULL`. The
router and the rate limiter therefore disagree about which endpoint a request belongs to whenever two
routes both fully match.

**The concrete pair.** `klijenti/router.py`:

```
:299  @router.get("/klijenti/retention-check")
:300  async def retention_check(request: Request, threshold_years: int = 10):
:306      """MORA biti registrovana PRE /klijenti/{klijent_id} da ne bude zasencena."""
...
:333  @router.get("/klijenti/{klijent_id}")
:334  async def get_klijent(...):
```

The comment at `:306` is correct *for Starlette* — registering the literal first is what makes the
router serve `retention_check`. But that same ordering makes slowapi's last-match-wins loop return
`get_klijent`. **The mitigation that fixes the router is what creates the rate-limiter defect.**

**Reproduction** (in-process, against the real route table, simulating Revision 4 exactly — single
collapsed `shared.rate.limiter`, `_application_limits = ["600/hour"]`, the 9-name exemption list, then
item (d)'s decoration of `/klijenti/{klijent_id}`):

```
=== BEFORE SEC-010 decorates /klijenti/{klijent_id} ===
  GET /klijenti/retention-check  handler=klijenti.router.get_klijent  _should_exempt=False   <- 600/h applies

=== AFTER SEC-010 decorates /klijenti/{klijent_id} (Revision 4 item d) ===
  GET /klijenti/retention-check  handler=klijenti.router.get_klijent  _should_exempt=True    <- middleware SKIPS
  GET /klijenti/<uuid>           handler=klijenti.router.get_klijent  _should_exempt=True    <- intended, correctly limited

=== what actually SERVES /klijenti/retention-check (starlette first-match) ===
  served: klijenti.router.retention_check | has own @limiter.limit? -> False

RESULT: retention_check is neither middleware-limited nor decorator-limited: True
```

**Why it happens:** `_should_exempt` (`middleware.py:110`) returns True on `name in limiter._route_limits`
— "there is a decorator for this route, let the decorator handle it." But the decorator is on
`get_klijent`, and `get_klijent` is never invoked for this request. `retention_check` runs with no
decorator and no middleware check.

**Net effect of Revision 4:** `/klijenti/retention-check` goes from *covered by the app-wide default* to
**completely unlimited**. Revision 4's own action item (d) is what removes the coverage that (b) was
written to provide.

**Exposure.** `retention_check` (`klijenti/router.py:299-330`) is authenticated but does a filtered
scan of `klijenti` with `ORDER BY datum_poslednje_aktivnosti` on every call, and `threshold_years: int = 10`
carries **no bound** — `threshold_years=0` sets the cutoff to `now` and returns every active client of
the caller. Unlimited invocation from one trial account is unbounded DB read amplification against the
one table the plan is elsewhere trying to protect from enumeration.

**Scope of the class, measured.** I synthesized a concrete URL for every one of the 602 routes and
re-ran the first-match/last-match comparison across the entire table. Exactly **5** divergent pairs
exist app-wide:

| Concrete path | served (Starlette, first) | slowapi sees (last) | Status |
|---|---|---|---|
| `GET /klijenti/retention-check` | `klijenti.router.retention_check` **[undecorated]** | `klijenti.router.get_klijent` | **HOLE after item (d)** |
| `GET /api/client-twin/dashboard` | `client_twin.twin_dashboard` [30/min] | `client_twin.get_komunikacioni_profil` [30/min] | benign today |
| `PATCH /api/predmeti/bulk` | `predmeti_close.bulk_promena_statusa` [10/min] | `api.update_predmet` [30/min] | benign today |
| `GET /api/predmeti/dashboard` | `api.predmeti_dashboard` [30/min] | `api.get_predmet` [60/min] | benign today |
| `GET /api/search` | `routers.search.global_search` [60/min] | `api.global_search` [30/min] | benign today |

The other four are benign **only because both endpoints happen to be decorated**, so the served route's
own decorator fires. They become the same hole the moment either decorator is removed. Revision 4 has no
guard against this and no statement that the class exists.

**Secondary mechanism property the plan does not account for.** `_should_exempt` (`middleware.py:100-102`)
returns True whenever `handler is None`. Verified live: `GET /does-not-exist-xyz → handler=None → exempt=True`,
and `GET /static/vindex.js → handler=None → exempt=True` (the `StaticFiles` `Mount` at `api.py:791` has
no `.endpoint` attribute, so the loop never assigns). The app-wide default therefore never applies to
any unmatched path. Path-probing and endpoint-discovery scanning remain completely unrated after
Revision 4 ships. This is not the exemption *list* failing — it is the exemption *control* applying far
more broadly than (b) assumes, and it bounds what "explicit app-wide default" can mean.

## Q1 verdict: **BLOCKING**

Not for the exemption list — that survived every attempt. For the exemption **mechanism**: Revision 4
item (d) creates a reproducible, zero-limit route via a name/path resolution divergence the plan does
not mention. Minimum fix: exempt-list and decoration work must be keyed against *what
`_find_route_handler` resolves*, not against what the router serves — i.e. any literal route registered
under a decorated parameterized sibling needs its own explicit decoration, and `/klijenti/retention-check`
needs it by name.

---

# Q2 — Is `600/hour` a real number

## 2.1 What the plan actually says

Line 158(b), verbatim: *"Size the new app-wide default consistently with the already-deliberate
`_USER_API_LIMIT = 600/hour` ceiling (`api.py:924`'s own comment: 'Limiti su namerno blaži od IP limita
— korisnik može biti iza NAT-a'), not 10× below it."*

That is the **entire** rationale. There is no attack scenario named, and no workload arithmetic. The
justification is structurally "match this other number, and don't be 60."

## 2.2 The cited line says the opposite of what it is cited for

`api.py:923-925`, read directly:

```
923  # ─── User-level rate limiting (in-memory sliding window) ──────────────────
924  # Dopuna IP-based slowapi limitera: prati pozive po user_id
925  # Limiti su namerno blaži od IP limita — korisnik može biti iza NAT-a
```

- **`:924`** — the line the document cites by number — states this mechanism is a *supplement to the
  IP-based slowapi limiter*, keyed *per `user_id`*. It is explicitly **not** the IP limiter.
- **`:925`** — the line the document actually quotes — states these limits are *deliberately laxer than
  the IP limits*. It is an assertion that `600` sits **above** whatever the IP limits are.

Revision 4 uses both lines as authority for setting the **IP** limit to `600`. Under `:925`'s own logic,
the IP default must sit **below** `600`, not at it. The citation does not support the conclusion drawn
from it.

## 2.3 The denominators do not match — provable from source, no behavioural assumptions

**`_USER_API_LIMIT` (`api.py:934`):**
- Key: `api.py:973` → `key = f"{user_id}:{'ai' if is_ai else 'api'}"`. **Per user_id, and the path is not
  in the key** — `path` only selects *which* of the two limits applies (`api.py:972`). It is one 600/hour
  budget spanning **every** non-AI API route that user touches.
- Gated to `/api/*` only: `api.py:1021-1022` → `if not path.startswith("/api/"): return await call_next(request)`.
- Gated to authenticated requests: `api.py:1042` → the whole check sits inside `if uid:`.

**The proposed app-wide slowapi default:**
- Key: `extension.py:501` → `args = [limit_key, limit_scope]`, where `limit_key = lim.key_func(request)`
  = `shared/rate.py::_get_real_ip` (**per IP**) and `limit_scope = lim.scope or endpoint`
  (`extension.py:488`) with `endpoint = _endpoint_key = endpoint_url = request["path"]`
  (`extension.py:559, 565`, `key_style="url"` retained per Revision 4). **Per exact URL path.**

So: **per-user / all-paths / `/api/*` / authenticated** vs. **per-IP / per-path / everything /
authenticated or not.** These are not the same quantity, and `600` cannot be simultaneously correct for
both.

## 2.4 Consequence A — far too permissive in aggregate

Measured residual after Revision 4 is fully applied (exemptions removed, the 36 parameterized routes
decorated under item (d)): **109 plain paths** remain under the app-wide default.

Because the bucket is per `(IP, path)`, a single IP's aggregate budget against the undecorated surface
is **109 × 600 = 65,400 requests/hour** — not 600. The plan's worry is that `60/hour` would be "10×
below" the 600 ceiling; the number it chose lands roughly **109× above** it in aggregate.

There is also no user-level backstop for a large part of that surface. `api.py:1021-1022` skips
everything not under `/api/`, and **38 of the 109** are outside `/api/`, including `/klijenti` (GET and
POST), `/klijenti/check-conflict`, `/klijenti/import-csv`, `/klijenti/intake-wizard`,
`/klijenti/retention-check`, `/csv-import/analiziraj`, `/export/docx`, `/v1/query`, `/api-kljucevi/novi`,
`/push/subscribe`, `/push/test`, `/waitlist/prijava`, `/rokovi/ics-export`. For these the new app-wide
default is the **only** control that exists.

**A concrete abuse case the 600 number does not stop.** `/api/security/csp-report`
(`api.py:1930-1971`) is, in its own docstring, *"Ne zahteva autentifikaciju — browser šalje automatski."*
Each request performs a `logger.warning(...)` and an **INSERT into `security_events`**. It has no `uid`,
so `api.py:1042`'s per-user check never engages. Revision 4 leaves it on the app-wide default: **600
unauthenticated DB writes per hour, per IP, into the security audit table**, plus 600 log lines. That is
write-amplification into the very table incident response depends on, and 600/h/IP is not a rate that
prevents it — it is a rate that permits it at scale from a handful of source addresses. The document
does not mention this route, and its `600` was not chosen with any such route in mind, because no attack
was analysed at all.

## 2.5 Consequence B — simultaneously too strict for the plan's own NAT scenario

The plan's only workload consideration is the NAT'd office. Under a per-`(IP, path)` bucket, `600/hour`
on a shared-path endpoint is **divided across every user in the office**, which is strictly harsher than
the per-user 600/hour it was copied from.

The sharpest instance, all facts measured:

- `GET /klijenti` is the client list **and** the type-ahead search backend. `static/vindex.js:20334`
  (`intakeKlijentSearch`) and `:20716` (`qiKlijentSearch`) both call
  `BASE_URL + '/klijenti?pretraga=' + encodeURIComponent(q)`.
- Debounce is **300 ms** (`static/vindex.js:20351`) and **280 ms** (`:20732`), firing after a 2-character
  minimum. Any inter-keystroke pause above ~300 ms — normal for a lawyer typing a client's surname —
  emits one request per keystroke.
- The query string is **not** in the bucket key: `extension.py:559` uses `request["path"]`, which excludes
  `query_string`. Every distinct search collapses into the single `/klijenti` bucket.
- `/klijenti` does not start with `/api/`, so `api.py:1021-1022` skips it — **no per-user backstop**.

Arithmetic: a 10-character surname typed with natural pauses ≈ 8 requests per lookup. At ~10 client
lookups per lawyer per hour that is ~80 requests/hour/lawyer against a bucket shared by the whole office.
A **7-lawyer office behind one NAT'd IP exhausts 600/hour**, and every subsequent client search returns
429 — on a core daily-use path, in exactly the deployment shape the plan cites NAT to protect. I want to
be precise about what is measured and what is calculated here: the 300 ms debounce, the shared bucket,
the missing backstop and the per-IP key are all verified in source; the per-lawyer request rate is a
calculation from stated assumptions about typing and lookup frequency, not an observation of production
traffic.

## 2.6 What I could NOT do

I could not construct any reading under which `600/hour` is a *derived* number. I looked for a sizing
note, a threat model, or a traffic measurement behind it in the decision document, in
`shared/rate.py`, in `api.py`'s rate-limiting block, and in the two archived Red Team reports. There is
none. `600` appears exactly once as a considered value — `api.py:934`,
`int(os.getenv("USER_API_LIMIT_PER_HOUR", "600"))` — under a different denominator, for a different
mechanism, with a comment saying it was chosen to be *laxer* than IP limits.

I also could not falsify the plan's negative claim: it is genuinely correct that `60/hour` would be
wrong, and correct that `_DEFAULT_LIMITS` must stay reserved for the `in_memory_fallback` value
(`shared/rate.py:_DEFAULT_LIMITS`, consumed at both `default_limits=` and `in_memory_fallback=`). Those
parts of (b) hold. The defect is only in what replaced `60`.

## Q2 verdict: **BLOCKING**

`600/hour` is an arbitrary number in the precise sense the founder asked about: it is transplanted from a
limiter with a different key, a different scope, a different gate and an opposite stated intent, and it
is defended on the grounds of being "not 10× below" the number it was transplanted from. It has no
attack it is sized to stop and no workload it is sized to admit — and under its actual denominator it is
~109× too loose in aggregate while being too tight on at least one core shared path.

Minimum fix: state the denominator explicitly (per-IP **per-path**), then size from a named workload and
a named attack, separately for the authenticated-and-backstopped `/api/*` subset and the 38 routes with
no backstop at all. Unauthenticated write endpoints such as `/api/security/csp-report` need their own
number, not the app-wide one.

---

## Overall: **BLOCKING**

Both questions produced concrete, reproducible scenarios. Neither can be closed.

Nothing outside these two questions was examined, and nothing outside them is implied by this verdict —
in particular the collapse mechanism, `key_style`, SEC-048 and the epic table remain as previously
assessed.
