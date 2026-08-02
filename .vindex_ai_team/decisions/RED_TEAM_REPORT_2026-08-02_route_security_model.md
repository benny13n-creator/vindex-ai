# Red Team Report — Route Security Model

**Target:** `docs/architecture/ROUTE_SECURITY_MODEL.md` (the model, not Epic B's patches)
**Date:** 2026-08-02
**Mandate:** the five tests named in the document's own §7. No findings outside those five.
**Environment:** slowapi 0.1.9 (`C:\Users\Benny\miniconda3\Lib\site-packages\slowapi`), repo at
`C:\Users\Benny\moj_prvi_agent\src\moj_prvi_agent\legal-agent`, branch `main`.

---

## VERDICT

| Test | Verdict | One-line reasoning |
|---|---|---|
| **A — composite key mechanics** | **BLOCKING** | The natural implementation of §3's `composite` (one concatenated key_func) is a **proven no-op** against the exact threat §3 says it exists to stop — measured 30 requests from one IP across 10 user_ids, **0×429**. A correct mechanism exists (stacked decorators, measured 25×429) but the document never names it. |
| **B — classification gaming / gaps** | **BLOCKING** | A live route (`WS /api/voice/realtime/ws`, api.py:710) fits **none** of the 5 classifications, cannot be expressed in the §6.1 registry key (`APIWebSocketRoute` has no `.methods`), and **cannot carry a slowapi limiter at all** (runtime `Exception`). Its real control is a concurrency cap the schema cannot represent. §6.3's auto-classifier also silently misclassifies in-body-gated admin routes. |
| **C — CI check gameability** | **BLOCKING** | A fully content-free entry passes every field requirement — and the boilerplate does not have to be invented, it is **copied verbatim from the document's own §6.2 pilot entries**, which directly contradict §5's stated requirement. |
| **D — registry/runtime divergence** | **BLOCKING** | **§6.4 does not exist.** It is referenced 4× (lines 259, 292, 296, 298) but the document ends at §6.3. No shadow-pair discovery algorithm is specified anywhere. A fresh cross-position pair defeats per-template probing and is served **unlimited (6/6 × 200)**. |
| **E — would it have prevented Epic B's 5 findings?** | **BLOCKING** | **2 of 5 prevented** (unscoped default on `/health`; the `/api/sesija/ping` dimension error — this is the model's genuinely strong part). **3 of 5 not prevented**, including finding #5, the `key_style="url"` no-op: `scope=` is **not a schema field** and appears nowhere in §1–§6.1. |

### Overall: **BLOCKING**

Not because the model is wrong in direction — §1–§4 are a real improvement and Test E confirms two
of Epic B's five findings become structurally hard to repeat. It is BLOCKING because the document's
**central promise** — *"catch it mechanically if that posture is missing or wrong"* (line 19) — rests
on a section (§6.4) that **was never written**, and because the two mechanisms the model adds beyond
prose (`composite`, and the registry schema) each contain a defect of exactly the class the five
prior passes were convened to eliminate: a control that is *stated* but, as specified, *does nothing*.

The headline: **§3's `composite` is this document's own `key_style="url"`.** Epic B's 5th pass found a
bucketing choice that made a claimed protection a complete no-op. §3 specifies a bucketing choice
that, implemented as written, is a complete no-op — and it is the newest, least-reviewed mechanism in
the document. The methodology reproduced the defect class it was written to prevent, one level up.

---

## Test A — composite key mechanics

### What I checked

Read the installed slowapi source directly: `extension.py` (886 lines) and `wrappers.py` (114 lines),
then verified behaviourally with a FastAPI + TestClient harness rather than reasoning from source
alone.

**The `key_func` contract is single-valued.** `slowapi/extension.py:496-501`:

```python
if "request" in inspect.signature(lim.key_func).parameters.keys():
    limit_key = lim.key_func(request)
else:
    limit_key = lim.key_func()
args = [limit_key, limit_scope]
```

`limit_key` is one string. `Limit.key_func` (`wrappers.py:25`) is one callable. There is no
multi-key path anywhere in the library. So §3's `composite` **cannot** be a single key_func in the
sense §3 describes it ("an outer coarse `ip` ceiling plus an inner `user_id` ceiling, evaluated
together").

### The break

The only thing a single key_func *can* do is return a concatenated string like `f"{ip}|{user_id}"`.
§3's wording invites exactly this. I measured what it produces:

```
S1 concatenated-composite: 1 IP x 10 uids x 3 req = 30 requests, 429s=0, 200s=30
```

A concatenated key is a **conjunction namespace**: it creates one bucket *per (ip, user_id) pair*.
It therefore provides **neither** ceiling — it is strictly *more permissive* than either dimension
alone. And the attack it fails to stop is the one §3 names verbatim as composite's reason to exist:

> *"pure `user_id` gives zero protection against many-throwaway-accounts IP floods"* (line 77)

An implementer who reads §3, writes the obvious key_func, and ticks `identity_dimension: composite`
in the registry has built a control that is **worse than useless** — it is worse than the pure
`user_id` it was supposed to improve on, and the registry entry will read as the most carefully
reasoned one in the file. This is structurally identical to Epic B's 5th finding.

### What I could NOT break (stated explicitly, per the discipline of the prior passes)

**Two stacked decorators genuinely work.** I expected to find a gap here and did not find one.

```python
@app2.get("/s")
@lim2.limit("5/minute", key_func=ip_of)      # outer IP ceiling
@lim2.limit("3/minute", key_func=uid_of)     # inner user ceiling
async def s(request: Request): ...
```

Measured:
```
S2 stacked ip5/uid3: 1 IP x 10 uids x 3 req = 30 requests, 429s=25, 200s=5
S2 fresh uid on exhausted IP -> 429  body={"error":"Rate limit exceeded: 5 per 1 minute"}
S2 single uid on fresh IP, 6 req: [200, 200, 200, 429, 429, 429]
S2 registered route-limit names: ['__main__.s']
    __main__.s -> ['3 per 1 minute', '5 per 1 minute']
```

The mechanism: `__limit_decorator` keys registration on `f"{func.__module__}.{func.__name__}"`
(`extension.py:664`) and `functools.wraps` preserves `__name__` through the inner wrapper, so **both
decorators register into the same `_route_limits[name]` list** (`extension.py:704`). One
`_check_request_limit` call then evaluates both (`__evaluate_limits`, `extension.py:487`). The
`request.state._rate_limiting_complete` guard (`extension.py:729-733`) prevents double-counting.

Both bounds are enforced. Both attack shapes are caught. I tried to find an ordering where one limit
silently won and could not: `__evaluate_limits` iterates all limits and `break`s only on the *first
failure* (line 518), so ordering affects **which 429 message is reported**, never **whether a limit is
enforced**. That is an observability nuance, not a security gap.

**So the fix is cheap.** The model does not need a new mechanism; it needs §3 to say *"`composite` is
implemented as two stacked `@limiter.limit(...)` decorators with different `key_func`s, never as a
single concatenated key_func"* — and the §6.1 schema needs `limiter` to be a **list** so a composite
route can express both bounds. As written, `limiter:` holds exactly one `{strategy, burst, sustained}`
block and **cannot represent a composite route at all**, even correctly implemented.

### Two secondary mechanics the model does not account for

1. **Empty key ⇒ limit silently skipped (fail-open).** `extension.py:502` guards `if all(args):`, and
   the `else` branch (line 519-523) logs and `continue`s. Measured:
   ```
   S3 empty key_func, 8 req:   [200, 200, 200, 200, 200, 200, 200, 200]
   S3 present key_func, 5 req: [200, 200, 429, 429, 429]
   ```
   Any route with `identity_dimension: user_id` whose key_func returns `""`/`None` when identity is
   unresolvable is **completely unlimited**, silently. The §6.1 schema has **no field** for
   identity-unavailable fallback, and §3 never requires the key_func to be total. Note also that the
   only signal is `logger.error` on a logger that has a `BlackHoleHandler` attached at
   `extension.py:228-232`.

2. **Stacked bounds share one failure mode.** `swallow_errors` and `in_memory_fallback` are
   **`Limiter`-level**, not per-limit (`extension.py:631-645`; repo config at `shared/rate.py:83`
   sets `swallow_errors=True`). So an "outer + inner" composite is *not* defence in depth against
   storage failure — both bounds fail open **together**. The model presents composite as layered
   protection without stating this correlation.

---

## Test B — classification gaming / gaps

### The break: a live route that fits none of the 5 classifications

`routers/voice_realtime.py:85` → `WS /api/voice/realtime/ws`, registered at `api.py:710`.

**1. The registry key format cannot express it.** §6.1 keys entries as `"<METHOD> <path template>"`.
Measured:
```
type=APIWebSocketRoute path=/ws has_methods=False methods=None
```
There is no METHOD. Worse for §6.3, whose script is specified to "walk `app.routes`": a
`WebSocketRoute` has no `.methods` attribute at all, so a method-keyed enumerator will either raise
or — more likely, using `getattr(r, "methods", [])` — **silently emit zero entries** for every
WebSocket route. §6.3's step 3 promises to "flag every route the script cannot confidently classify";
a route that never enters the iteration is never flagged.

**2. slowapi cannot rate-limit it, and fails at runtime rather than import.** `__limit_decorator`
accepts a `websocket` parameter at decoration time (`extension.py:709`), but `async_wrapper` then
does `if not isinstance(request, Request): raise Exception(...)` (`extension.py:724-727`). Measured:
```
B1 decoration: OK (no exception at import time)
B2 connect FAILED: Exception parameter `request` must be an instance of starlette.requests.Request
```
So a registry entry specifying a limiter on a WS route **passes review, passes import, and breaks the
route in production on first connection**.

**3. The threat is real and the schema cannot size it.** This route proxies to the OpenAI Realtime
API (`services/voice_orchestrator.py`), i.e. textbook `cost-amplification` — but the abuse is *one*
request held open for hours streaming metered audio. §5's entire vocabulary is
`burst: "<rate>/<window>"` and `sustained: "<rate>/<window>"` — **requests per window**. The actual
control in the code is `_MAX_CONCURRENT_SESSIONS_PER_USER = 2` (`voice_realtime.py:42`), a
**concurrency cap**, which is a legitimate security control the registry has no field for: it is not
`burst`, not `sustained`, not `exempt`.

**4. §4 offers no honest exemption reason.** §4 reserves exemption for "routes where a limit would
itself be the availability risk." That is *not* the reason here; the reason is "rate-per-window is
the wrong *shape* of control." An implementer following §4 literally must either write a false
`exempt_reason` or force the route into a classification that hides its cost profile.

Incidentally — and invisible to the registry as specified — `_active_sessions` (`voice_realtime.py:43`)
is a **per-process** in-memory dict, so under gunicorn the effective cap is `N_workers × 2`, not 2.

**5. It is also the "public but token-gated" case.** Auth is a **query-param** token
(`voice_realtime.py:47`, with the constraint documented at lines 14-17), verified in-body by
`_authenticate`, not by a `Depends`. Under §6.3's rule 2 — *"any route with no auth dependency →
`public`"* — this authenticated route classifies as **`public`**, which pushes toward `ip` keying:
precisely the dimensional error of Epic B finding #4.

### The compound-tag escape hatch is permissive, and there is a real route that exploits it

`routers/batch_ingest.py:251` → `GET /api/admin/ingest/job/{job_id}`, gated by
`Depends(_require_admin)` (line 256). This is genuinely **both** `privileged-admin` (elevated role)
**and** `authenticated-heavy-workload` (a job-status poll — §1 lists `/api/jobs/{job_id}` (poll) as
the canonical heavy-workload example).

§1 line 43 says a route *"may need a compound tag in rare cases."* That is **permissive, not
conditional-mandatory**. There is no rule of the form *"if the UI polls this route, `authenticated-
heavy-workload` MUST be present."* An implementer writes `classification: [privileged-admin]`, passes
CI (§6.1 says "list, usually length 1"), and the polling dimension — **the one that actually sizes
the limit** — is simply gone. The document asked whether the escape hatch "actually resolves this."
It does not: it permits the resolution without requiring it.

### §6.3's auto-classifier misclassifies confidently, so its own review-flag never fires

`routers/apr.py:332` → `GET /api/apr/metrics` (prefix at line 54). It is **founder-only**, but the
gate is an **in-body** `if not _is_founder(...)` at line 341, while the signature carries
`Depends(get_current_user)`.

Walk §6.3's rules: rule 2 sees `Depends(get_current_user)` → `authenticated-user`. Rule 3 looks for
"path/module name matches an admin-role pattern" — path is `/api/apr/metrics`, module is `apr.py`;
**no match**. Result: confidently classified `authenticated-user`, `privileged-admin` **missed**, and
step 3's "flag what the script cannot confidently classify" never fires because the script *is*
confident. Same pattern at `routers/analytics.py:349` and `routers/corrections.py`.

---

## Test C — CI check gameability

### The break

Here is an entry that satisfies **every** field requirement in §6.1 and §5 and contains **zero**
security reasoning:

```yaml
"GET /api/dokumenti/{dokument_id}/preuzmi":
  classification: [authenticated-user]
  threat: [dos]
  identity_dimension: user_id
  limiter:
    strategy: user_id
    burst: "30/minute"
    sustained: "300/hour"
  rationale:
    formula: "policy floor, unassessed -- generic tier (iii) treatment"
    reason: "default-deny friction; not individually reviewed"
    expected_workload: "not calibrated to a specific workload"
  source: route-security-registry-v1
```

Every field present and non-empty. `classification` and `identity_dimension` are enum-valid. `threat`
has length ≥ 1. The `limiter` and `rationale` blocks are complete. **Any mechanical check the
document specifies passes this.**

Yet: the route is a document *download* by enumerable ID — genuinely `scraping` + `cost-amplification`
— tagged `dos`. Nothing mechanical catches that, because `threat` only needs *some* valid enum member.
It has a path parameter and no `scope=`, so under `key_style="url"` it is the Epic B finding #5 no-op
verbatim. And `expected_workload` names no number, no actor, and no frequency.

### Why this is worse than a hypothetical gaming vector

**The implementer does not have to invent that boilerplate. The document supplies it.** The three
`rationale` strings above are copied, near-verbatim, from the document's **own pilot entries** at
lines 236-238 and 251-253:

```yaml
    formula: "policy floor, unassessed -- generic tier (iii) treatment"
    reason: "default-deny friction; not individually reviewed beyond the shadow-pair fix below"
    expected_workload: "not calibrated to a specific workload -- this is what makes it tier (iii) rather than a reviewed entry"
```

And this **directly contradicts §5**, which requires `expected_workload` to be:

> *"The concrete legitimate-usage assumption the number must not break — who, how often, at what
> scale. Must be stated even when derived from an estimate rather than measured traffic"* (line 94)

`"not calibrated to a specific workload"` is the **negation** of that requirement, presented in the
document's own worked examples as an acceptable entry. §5 then claims this is what makes
*"limit = feeling" mechanically unrepresentable* (line 96-97). It does not: the document ships a
blessed, copy-pasteable template for representing exactly that, and a reviewer who rejects it can be
answered with "I used the format from §6.2."

### Does the spec give CI enough to reject content-free entries?

**No — only enough to reject *missing* fields.** Every requirement in §5 and §6.1 is a
presence/enum-membership requirement. There is not one *content* predicate anywhere: no requirement
that `expected_workload` contain a numeral, no requirement that `formula` reference a quantity, no
requirement that `burst`/`sustained` be arithmetically consistent with `expected_workload`. The
minimum viable content predicates the document would need and does not have:

- `expected_workload` must match a numeric pattern (a count **and** a time unit **and** an actor).
- `formula` must be derivable — must reference a number that appears in `expected_workload`.
- `sustained` must be ≥ the rate implied by `expected_workload`, and `burst` ≥ `sustained`/window
  (an arithmetic check, mechanically enforceable, currently absent).
- A denylist for the document's own tier-(iii) boilerplate, or the boilerplate removed from §6.2.

---

## Test D — registry/runtime divergence

### First, the finding that subsumes the rest: §6.4 does not exist

The brief I was given describes §6.4 as "the CI enforcement spec." I verified against the document
itself rather than taking that on faith. Every heading in the file:

```
1  # Route Security Model & Registry
30 ## 1. Route Classification
47 ## 2. Threat Model
66 ## 3. Identity Dimension
79 ## 4. Exemption
88 ## 5. Limit Derivation
99 ## 6. The Route Security Registry
106 ### 6.1 Schema
125 ### 6.2 Worked entries
262 ### 6.3 Full population is an implementation-phase task
276 ## 7. What the final Red Team pass on this model must test
```

**There is no §6.4.** It is referenced four times — line 259 ("CI's parity check, §6.4"), line 292
("§6.4/CI"), line 296 ("registry-runtime consistency (§6.4)"), line 298 ("the same way §6.4
requires") — and never written. §5's "fails CI (§6)" (line 96) likewise points at a section
containing no CI specification.

So Test D's question — *"does the new check correctly use exhaustive pairwise witnesses, not
per-template probing?"* — has an unambiguous answer: **the check does not specify anything, because
the check does not exist.** Line 298's "the same way §6.4 requires" asserts a requirement that is
nowhere stated. Every "mechanically enforced" claim in the document (lines 19, 96-97) currently
resolves to a dangling cross-reference.

### Second: the shadow-pair knowledge lives in an unschema'd field

What *is* written about shadow pairs sits in `note:` fields at lines 197 and 240. **`note` is not in
the §6.1 schema.** A CI parser written against §6.1 would not read it. And line 259 describes the
"parity check" as needing existing entries "so CI's parity check has something to compare" — i.e. it
**compares pairs already known to be pairs**. It contains no *discovery* step. A pair nobody has
noticed is never compared.

### The fresh scenario (constructed, not one of the 6 already-found pairs)

Two plausible future routes with parameters in **different segment positions**:

```
A:  GET /api/spisi/{spis_id}/verzije/latest        # param seg 3, literal seg 5
B:  GET /api/spisi/nacrti/verzije/{verzija_id}     # literal seg 3, param seg 5
```

Witness: `/api/spisi/nacrti/verzije/latest`. Measured against Starlette's own `compile_path`:

```
witness path: /api/spisi/nacrti/verzije/latest
  matches /api/spisi/{spis_id}/verzije/latest      -> True
  matches /api/spisi/nacrti/verzije/{verzija_id}   -> True

-- naive per-template DUMMY probe --
  probe for /api/spisi/{spis_id}/verzije/latest    = /api/spisi/DUMMY/verzije/latest    matches: ['/api/spisi/{spis_id}/verzije/latest']
  probe for /api/spisi/nacrti/verzije/{verzija_id} = /api/spisi/nacrti/verzije/DUMMY    matches: ['/api/spisi/nacrti/verzije/{verzija_id}']
```

**Neither** per-template probe finds the collision — each template's own dummy substitution fails the
*other* template's literal. Only a witness that simultaneously satisfies A's literal (`latest`) and
B's literal (`nacrti`) exposes it, which requires exhaustive pairwise enumeration over literal
alphabets, not per-template probing.

Runtime consequence, with B registered first and A carrying the decoration (the realistic case: a new
route added above an older decorated one):

```
witness /api/spisi/nacrti/verzije/latest, 6 requests:
   200 {"who":"B"}
   200 {"who":"B"}
   200 {"who":"B"}
   200 {"who":"B"}
   200 {"who":"B"}
   200 {"who":"B"}
```

**Six for six, unlimited.** Starlette serves first-full-match (B, undecorated); the registry says A is
decorated and covered; the parity check has no entry pairing them because nothing discovered they
were a pair. Epic B's 5th-pass finding class, fully reproduced against the model as written.

For completeness I confirmed `docs/security/route_security_registry.yaml` does not exist and no
registry/shadow-pair CI script exists (`scripts/` contains only `validate_feature_registry.py`;
`.github/workflows/` has `email-cron.yml`, `security.yml`, `sms-cron.yml`, `tests.yml`). The document
is honest that it is unimplemented — the finding is that the *specification* of the check, which is
what a model document owes, is absent, not merely its code.

---

## Test E — would the model have prevented Epic B's own 5 findings?

I walked each finding as if filling out a registry entry with only this document in hand.

### #1 — Root-cause misattribution, two `Limiter` instances → **NOT prevented**

The registry records a route's *intended* posture. It has **no field** for *which `Limiter` instance
enforces it*, whether that instance is wired to `app.state.limiter`, or whether the middleware is
installed. `limiter.strategy` (§6.1) describes the key_func, not the instance.

A route can have a flawless entry — classification, threat, dimension, limits, rationale all correct —
and be enforced by a `Limiter` that is not wired up. The registry reads 100% green. This is not
hypothetical in this repo: `shared/rate.py:59-66` documents in its own docstring that *"dve odvojene
Limiter instance i dalje postoje u ovom kodu ... arhitektonska duplikacija, poznata"*, and `api.py:546`
builds a **second** instance via `build_limiter(_get_real_ip)`.

One could argue instance wiring is out of a per-route model's scope. But the document claims to be
*"the single source of truth for a route's security posture"* (line 102), and "is my decorator
actually enforced by the limiter the app uses?" is squarely posture, not plumbing.

### #2 — Unscoped default landing on `/health` → **PREVENTED** (with a caveat)

This one works. §4 makes exemption an explicit, reasoned decision, §2 line 62-64 removes waiver-by-
omission, and the pilot entry (lines 132-138) cites `railway.toml:5` as evidence. An engineer filling
this out is forced to look at `/health` and justify it. **Genuine improvement.**

Caveat: `exempt: true` in the registry does **not** make slowapi exempt the route. The app-level
default (`_DEFAULT_LIMITS = ["60/hour"]`, `shared/rate.py:42`) still applies unless `@limiter.exempt`
or an `exempt_when` is present, and the registry has no representation of the default-limit set or
which routes it silently lands on. So the model makes you *notice* — the main thing — but a registry
saying `exempt` and a runtime applying 60/hour is another registry/runtime divergence.

### #3 — Route-shadowing bypass → **NOT prevented for new pairs**

Fully covered in Test D. The 6 known pairs are recorded (in an unschema'd `note:` field); no
discovery algorithm is specified; a fresh cross-position pair is served unlimited.

### #4 — Dimensionally-wrong tier criterion for `/api/sesija/ping` → **PREVENTED**

**This is the model's strongest field and I could not break it.** §3 forces an explicit
`identity_dimension` and states outright that `user_id` *"must be used wherever NAT-sharing would
otherwise produce false positives."* Combined with §5's mandatory `expected_workload`, an engineer
filling out `ping` must write down something like the pilot entry's own arithmetic (lines 148-154):
*"50 lawyers × 2 tabs = 3,000-6,000/h from one office IP."* Having written that sentence, the per-IP
choice is visibly indefensible. The dimension field plus the workload field, together, make this
error hard to commit silently. **Real, structural prevention.**

### #5 — `key_style="url"` scrape-protection no-op → **NOT prevented**

The sharpest failure. I grepped for `scope` across the whole document:

```
line   6: (header prose, summarising Epic B)
line 137: (inside an exempt_reason, unrelated sense: "an unscoped limit here")
line 204: strategy: "...with an explicit scope= override..."      <- pilot entry free text
line 209: reason:   "...hence the scope= requirement"             <- pilot entry free text
line 218: strategy: "...with an explicit scope= override..."      <- pilot entry free text
line 222: formula:  "...scope= added without changing the limit"  <- pilot entry free text
```

**`scope=` appears nowhere in §1–§6.1** — not in the classification rules, not in the threat table,
not in the identity-dimension table, not in §5's derivation requirements, and **not as a field in the
§6.1 schema.** It exists only as English prose inside three pilot entries' free-text
`strategy`/`reason`/`formula` strings.

§6.1 types `strategy` as `<slowapi key_func description>`. So a new path-parameter route can be
entered as:

```yaml
"GET /api/dokumenti/{dokument_id}":
  classification: [authenticated-user]
  threat: [scraping]
  identity_dimension: user_id
  limiter: {strategy: user_id, burst: "60/minute", sustained: "600/hour"}
  rationale:
    formula: "per-document views during normal casework x headroom"
    reason: "prevents scraping the document store by enumerating IDs"
    expected_workload: "a lawyer opening ~40 documents per hour"
```

This entry is **better-reasoned than most of the document's own pilot entries** — concrete workload,
named threat, correct dimension — and it is a **complete no-op against scraping**, because under
`key_style="url"` each `{dokument_id}` gets its own bucket. Epic B's fifth finding, reproduced
verbatim, by an engineer following this document correctly and diligently.

The lesson the terminal pass paid the most to learn is the one the model encoded least: as narrative
in two worked examples rather than as a schema field or a normative rule. §6.2's own framing invites
this — it presents those `strategy` strings as descriptions of past decisions, not as a pattern any
path-parameter route must follow.

### Test E tally

| Epic B finding | Prevented? |
|---|---|
| #1 Two-`Limiter`-instance root cause | No — no field represents enforcement wiring |
| #2 Unscoped default on `/health` | **Yes** — §4 exemption discipline works |
| #3 Route-shadowing bypass | No — no discovery algorithm specified (§6.4 missing) |
| #4 `/api/sesija/ping` dimension error | **Yes** — §3 + `expected_workload` force the NAT math |
| #5 `key_style="url"` no-op | No — `scope=` is not a schema field or a rule |

**2 of 5.** The model's own §7 states this is *"the model's actual test of usefulness — not whether it
looks complete on paper."* By that standard it is not yet passing.

---

## Minimum changes to reach MODEL SOUND

Scoped strictly to defects found by Tests A-E. No new scope.

1. **§3 `composite`** — state that it is implemented as **stacked decorators with different
   `key_func`s**, never as a concatenated key_func; add the concatenation anti-pattern explicitly
   with the measured 0×429 result. Change §6.1's `limiter:` to a **list of bounds** so composite is
   representable. Note that stacked bounds share one `swallow_errors`/fallback fate.
2. **§3 / §6.1** — require a declared fallback for when the identity dimension is unresolvable
   (empty key ⇒ limit silently skipped, `extension.py:502`).
3. **§1 / §6.1** — add a **6th classification or an explicit non-HTTP carve-out** for WebSocket/
   long-lived-stream routes; add a `concurrency:` bound to the schema; state that slowapi cannot
   limit a WS route. Fix the registry key format so non-HTTP routes are expressible.
4. **§1** — make compound tags **conditional-mandatory** ("if UI-polled, heavy-workload MUST be
   present"), not merely permitted.
5. **§6.1** — add `scope:` as a **first-class required field for every route with a path parameter**.
   This is the single highest-value change in the list.
6. **§5 / §6.2** — add content predicates (numeral required in `expected_workload`; `formula` must
   reference a quantity appearing in it; `burst`/`sustained` arithmetic consistency), and **remove or
   quarantine the tier-(iii) boilerplate** from §6.2 that currently contradicts §5.
7. **Write §6.4.** Specify the shadow-pair check as **exhaustive pairwise witness enumeration over
   literal alphabets**, explicitly rejecting per-template probing, with the Test D scenario as the
   regression fixture. Add `note:` to the schema, or replace it with a structured `shadow_pair_with:`
   field the check can actually read.
8. **§6.3** — the auto-classifier must treat **in-body** auth/role gates (`_is_founder`,
   `_require_firma_admin`, in-body token verification) as classification signals, not just `Depends`,
   or explicitly emit low-confidence for any route whose module contains such a call.

---

*Scope note: this report addresses only §7's Tests A-E against `ROUTE_SECURITY_MODEL.md`. Epic B's
already-settled findings — the 6 shadow pairs, the exemption list, the tier numbers — were treated as
out of scope and were not re-litigated; they appear here only where Test E required checking whether
the model would have re-derived them.*
