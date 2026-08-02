# Route Security Model & Registry

**Status:** Architecture specification. Not implemented. Supersedes Epic B's ad-hoc tier system in
`.vindex_ai_team/decisions/2026-08-02_forensic-remediation_ARCHITECTURE_DECISION.md` as the source
of truth for per-route rate-limiting/abuse-surface decisions — Epic B's substantive fixes (the
`Limiter` collapse, the 6 shadow-pair decorations, the exemption list, the `scope=` override for
scrape targets) are preserved, but expressed as registry entries conforming to this model instead of
free-form epic prose.

**Why this exists:** five consecutive Red Team passes on Epic B each found a genuine defect, and the
fifth — designed to be terminal — proved the problem was never really "is this one patch correct."
Every defect traced back to the same missing thing: **no formal model existed for what a route's
security posture is supposed to be**, so each fix was reasoned about ad hoc, from scratch, in prose,
and each ad hoc reasoning pass missed something the next one found. This is the audit's own
diagnosis (*"a primitive exists, but isn't systematically applied"*) recurring one level up: rate
limiting *as a primitive* now works (the collapse is proven sound); what was missing is a systematic
way to decide, for **any** route — including the 601st one added six months from now, by a different
engineer, possibly through a different agent — what its security posture must be, and to catch it
mechanically if that posture is missing or wrong.

**Founder's own framing, preserved verbatim as the standard this document is held to:** *"Problem
više nije implementacija rate limiting-a. Problem je metodologija kojom se definišu security
kontrole."* This document is the methodology. It does not re-litigate Epic B's 5 passes' findings —
see `.vindex_ai_team/decisions/RED_TEAM_REPORT_2026-08-02_revision*.md` for that evidence trail — it
generalizes what they collectively taught into something a 6th, unexamined route can be checked
against without a 6th ad hoc pass.

**Revision note (post-model Red Team pass):** the first version of this document was itself Red
Teamed against its own §7 (5 named tests) and returned **BLOCKING** —
`.vindex_ai_team/decisions/RED_TEAM_REPORT_2026-08-02_route_security_model.md`. The verdict's own
framing, worth preserving verbatim because it names exactly why this mattered: *"§3's `composite` is
this document's own `key_style='url'`... The methodology reproduced the defect class it was written
to prevent, one level up."* Concretely: the natural implementation of `composite` (a single
concatenated key) was a proven no-op (30 requests from one IP across 10 user_ids, 0×429); a live
WebSocket route (`WS /api/voice/realtime/ws`) fit none of the 5 classifications and could not be
rate-limited by slowapi at all; a fully content-free registry entry passed every stated field
requirement using boilerplate copied verbatim from this document's own pilot entries; the promised
§6.4 CI enforcement section did not actually exist, only forward references to it; and, most
pointedly, applying this model to Epic B's own 5 real findings would have caught only 2 of them (the
`/health` exemption and the `/api/sesija/ping` dimension error) — not the other 3, including the
exact `key_style="url"` scrape no-op the model was written in response to. Every section below has
been corrected against that report; §6.4 (previously missing) is now written; the fixes are
integrated inline rather than kept as a separate errata list, consistent with how Epic B's own
revisions were handled.

---

## 1. Route Classification (exactly one per route)

The population a route is exposed to and the frequency it's legitimately used at — the two things
that determine what "normal" looks like, which every limit must be sized against.

| Classification | Meaning | Example |
|---|---|---|
| `public` | No authentication. Reachable by anyone, including unauthenticated actors and bots. | `/health`, `/api/security/csp-report`, `/viber/webhook` |
| `authenticated-user` | Requires a valid session. Normal-frequency usage (navigation, CRUD, detail views). | `/api/predmeti/{id}` |
| `authenticated-heavy-workload` | Requires a valid session, but the feature's own UI drives high per-user call frequency (type-ahead, polling, heartbeats). | `/klijenti` (search), `/api/sesija/ping`, `/api/jobs/{job_id}` (poll) |
| `privileged-admin` | Requires an elevated role (firm admin, internal staff). Small population, often high-value target. | role-assignment endpoints (SEC-041) |
| `internal-service` | Not intended for direct end-user traffic — scheduler/cron, internal webhooks, service-to-service. | `/api/cron/daily` |
| `non-http-stream` *(added post-model Red Team pass)* | A WebSocket or other long-lived-connection route. Cannot be expressed by the `"<METHOD> <path>"` registry key (§6.1) and **cannot be rate-limited by slowapi at all** — verified: `SlowAPIMiddleware`'s decorator raises at connection time if the handler isn't a plain HTTP `Request` (`WS /api/voice/realtime/ws` reproduces this exactly). Its real control is a `concurrency:` bound (§6.1), not `burst`/`sustained`. | `WS /api/voice/realtime/ws` |

**Compound tags are conditional-mandatory, not merely permitted** *(corrected post-model Red Team
pass — the original wording, "may need a compound tag in rare cases," was proven to let an
implementer pick the more comfortable single tag and silently drop the dimension that actually sizes
the limit; found concretely at `GET /api/admin/ingest/job/{job_id}`, which is both `privileged-admin`
and a UI-polled status route)*: if a route is polled or searched by the frontend at a frequency the
`authenticated-heavy-workload` row describes, `authenticated-heavy-workload` **must** be included
alongside whatever other tag applies — it is not optional once that condition is true. A route with
only `privileged-admin` and a real polling pattern in the client is a non-conforming registry entry,
not a permitted judgment call.

**A route with only `Depends(get_current_user)` and no further check is not necessarily
`authenticated-user`.** An in-body role/founder gate (`if not _is_founder(...)`, `_require_admin`,
etc. — not expressed as a `Depends`) makes a route `privileged-admin` even though a naive
dependency-based classifier would miss it entirely (§6.3 addresses the auto-classifier's obligation
here explicitly, corrected for the same reason).

## 2. Threat Model (one or more per route)

What a route's rate-limit exists to stop. Stating this is what makes a number defensible instead of
felt — this is the direct generalization of the terminal pass's `limit = workload model + security
objective` test.

| Threat | Meaning |
|---|---|
| `scraping` | Bulk extraction of many records of the same resource type once valid IDs are known. |
| `brute-force` | Guessing a secret — credential, OTP, token, invite code. |
| `abuse` | Excessive legitimate-function use for cost or nuisance (spamming sends, hammering AI routes). |
| `cost-amplification` | Triggers expensive downstream work (LLM call, heavy join, PDF render) disproportionate to request cost. |
| `enumeration` | Discovering *which* IDs/users/resources exist, distinct from extracting their content once known — a route can carry both `enumeration` and `scraping`. |
| `dos` | No extraction value, but sustained volume degrades availability for others. |

A route with **zero** applicable threats does not get a waiver by omission — it must be explicitly
classified `public`+`dos` at minimum (any reachable HTTP endpoint has at least a DoS surface) or
carry an explicit, reviewed exemption (§4).

## 3. Identity Dimension (exactly one, used as the rate-limit key)

The terminal Red Team pass proved a single wrong choice here is what created 2 of Epic B's 5
findings (the `/klijenti` NAT false-positive and the `/api/sesija/ping` mis-sort) — this is not a
secondary detail, it is frequently the whole defect.

| Dimension | Appropriate when |
|---|---|
| `ip` | No reliable per-actor identity exists (unauthenticated), or the threat is genuinely IP-level (a DoS from any source, not a specific account being abused). |
| `user_id` | Authenticated, and the threat is per-account abuse — must be used wherever NAT-sharing would otherwise produce false positives (Epic B's tier (ii) fix). |
| `tenant_id` | The workload is naturally firm-wide (many seats sharing one legitimate use pattern) rather than per individual seat. |
| `composite` | A single dimension either over-shares state (pure `user_id` gives zero protection against many-throwaway-accounts IP floods) or under-shares it (pure `ip` breaks under NAT) — an outer coarse `ip` ceiling plus an inner `user_id` ceiling, both enforced. |

**`composite`, corrected mechanism (post-model Red Team pass):** `composite` **must** be implemented
as **two stacked `@limiter.limit(...)` decorators with two different `key_func`s** (one `ip`-keyed,
one `user_id`-keyed) — confirmed, by direct measurement against the installed `slowapi`, that both
bounds register under the same route name and both are independently enforced (25 of 30 test
requests correctly rejected across a 10-user/1-IP simulation). **`composite` must never be
implemented as a single concatenated key** (e.g. `f"{ip}|{user_id}"`) — measured directly: this
produces one bucket *per (ip, user_id) pair*, which is strictly *more permissive* than either
dimension alone and a complete no-op against the exact many-throwaway-accounts threat this dimension
exists to stop (30 requests from 1 IP across 10 user_ids: 0×429). A registry entry with
`identity_dimension: composite` therefore requires `limiter` to be a **list** of two bound objects
(§6.1), not one — a single-bound `limiter` block cannot represent a composite route at all, correctly
implemented or not. Note the shared failure mode: `swallow_errors`/`in_memory_fallback` are
`Limiter`-level, not per-bound, so stacked bounds fail open **together** during a storage outage —
composite is not defence-in-depth against that failure mode, only against the split-dimension attack.

**Every non-`ip` dimension must declare a fallback for when identity is unresolvable.** Verified:
slowapi silently skips a limit entirely when its `key_func` returns an empty/falsy value
(`extension.py:502`'s `if all(args):` guard) — a route keyed `user_id` whose key_func returns `""`
when the session is unauthenticated-but-reachable is **completely unlimited**, with only a
swallowed `logger.error` as a signal. Every registry entry with `identity_dimension: user_id` or
`tenant_id` must state, in `rationale.reason`, what happens when that identity is unavailable
(reject the request, fall back to `ip`, or state why it cannot occur for this route) — omitting this
is treated the same as a missing required field (§5).

## 4. Exemption (route carries no rate limit at all)

Reserved for routes where a limit would itself be the availability risk — platform healthchecks,
app-shell assets, and (per Epic B's own corrected finding) routes with a legitimate call cadence at
or above any defensible ceiling, where the right answer is "don't limit it," not "raise the number
until it stops mattering." Every exemption must be named explicitly in the registry with a stated
reason — an exemption is a decision, not an absence of one, and "not yet classified" is never a valid
reason (that is what `public`+`dos`, minimally rate-limited, is for).

## 5. Limit Derivation (required for every non-exempt route)

| Field | Required content |
|---|---|
| `formula` | How the number was produced — e.g. "heavy-use estimate × headroom multiplier," "known cadence × population + margin," "policy floor, unassessed remainder." |
| `reason` | The specific threat tag(s) from §2 this number is sized against. |
| `expected_workload` | The concrete legitimate-usage assumption the number must not break — who, how often, at what scale. Must be stated even when derived from an estimate rather than measured traffic (flagged as such, not presented as measured). |

A registry entry missing any of these three fields fails CI (§6.4) — this is what makes "limit = feeling"
mechanically unrepresentable, not just discouraged in prose.

**Content predicates, not just presence (added post-model Red Team pass).** A field that is merely
non-empty is not enough — verified that a fully field-complete entry containing zero real reasoning
passes every check stated above, using boilerplate copied from this very document's own pilot
entries (§6.2). CI (§6.4) must additionally enforce:
- `expected_workload` must contain a **number** and a **time unit** and an **actor** (e.g. "50
  lawyers", "3,000/hour") — a string with none of these, however articulate, fails.
- `formula` must reference a **quantity that also appears in** `expected_workload` — a formula that
  cites no number from the workload it claims to derive from fails.
- `sustained` and `burst` must be **arithmetically consistent** with `expected_workload`'s stated
  number (the ceiling must sit above the stated legitimate workload, with the headroom multiplier
  named in `formula` — not simply asserted).
- The literal strings `"not calibrated to a specific workload"` / `"not individually reviewed"` (or
  close paraphrases) are **not** valid `expected_workload`/`reason` content for any entry that is not
  explicitly tagged `reviewed: false` (§6.2) — a route may legitimately be an unreviewed policy-floor
  placeholder, but it must say so as a structured, CI-checkable flag, not by writing prose that reads
  like a derivation while stating none.

## 6. The Route Security Registry

A structured, versioned artifact — `docs/security/route_security_registry.yaml` — one entry per
route (by method + path template), the single source of truth for a route's **intended** security
posture. Not a comment, not a decorator argument alone: a route's `@limiter.limit(...)` call and its
`key_func` implement what the registry specifies, they do not replace the registry as documentation.

**Explicit scope boundary (added post-model Red Team pass, Test E, finding #1):** this registry
records what a route's posture *should be* — it does not, and structurally cannot, verify *which
`Limiter` instance actually enforces it, or whether that instance is wired to `app.state.limiter` and
the app's middleware at all*. That is an application-wiring property, not a per-route property, and
is out of this registry's scope by design — a route can have a flawless registry entry while being
enforced by a `Limiter` instance the middleware never inspects (exactly Epic B's own first finding,
`shared/rate.py:59-66`'s documented dual-instance history). Verifying instance wiring is a
one-time, whole-application check (confirm exactly one `Limiter` instance exists and is assigned to
`app.state.limiter`), not a per-route registry concern, and should be a standing CI check alongside,
not inside, §6.4.

### 6.1 Schema

**Registry key format, corrected (post-model Red Team pass):** `"<METHOD> <path template>"` cannot
express a non-HTTP route — verified a `WebSocketRoute` has no `.methods` attribute at all, so a
method-keyed enumerator silently emits nothing for it rather than raising, meaning it would never
even reach the "flag for manual review" step (§6.3). Non-HTTP routes use the key format
`"WS <path template>"` / `"SSE <path template>"` explicitly, both valid registry keys in their own
right, classified `non-http-stream` (§1) and carrying `concurrency` instead of `burst`/`sustained`.

```yaml
"<METHOD> <path template>":                     # or "WS <path template>" for non-http-stream routes
  classification: [public | authenticated-user | authenticated-heavy-workload | privileged-admin | internal-service | non-http-stream]  # list; length > 1 REQUIRED when the compound-tag condition in §1 applies, not merely allowed
  threat: [scraping, enumeration, ...]        # list, length >= 1
  identity_dimension: ip | user_id | tenant_id | composite
  scope: per_value | fixed                      # REQUIRED whenever the path template contains a parameter (e.g. {klijent_id}). per_value = default slowapi bucketing (one bucket per ID -- provides NO aggregate/scraping protection, must be an explicit, justified choice, not silence). fixed = an explicit `scope=` override collapsing all values into one shared bucket (the correct choice whenever `threat` includes `scraping`).
  limiter:                                      # a LIST when identity_dimension is `composite` (two bound objects, e.g. one ip-keyed, one user_id-keyed); a single object otherwise. OMITTED entirely for non-http-stream routes.
    - strategy: <slowapi key_func description, e.g. "user_id" | "ip">
      burst: "<rate>/<window>"                   # e.g. "30/minute"
      sustained: "<rate>/<window>"                # e.g. "300/hour"
  concurrency: <max concurrent connections per identity_dimension unit>   # REQUIRED instead of limiter for non-http-stream routes; e.g. "2 per user_id" -- state explicitly whether this is process-local (multiply by worker count for the real ceiling) or centrally tracked
  rationale:
    formula: "..."       # must reference a number that also appears in expected_workload (§5)
    reason: "..."        # must state the identity-unavailable fallback for non-ip dimensions (§3)
    expected_workload: "..."   # must contain a number, a time unit, and an actor (§5) UNLESS reviewed: false
  reviewed: true                                 # false marks an explicit, honestly-flagged policy-floor placeholder (not individually derived) -- exempts this entry from §5's content predicates, but NOT from having classification/threat/identity_dimension/scope correctly set
  exempt: false                                 # true only for explicit, reasoned exemptions; if true, limiter/rationale/scope are omitted and `exempt_reason` is required instead
  shadow_pair_with: ["<METHOD> <path template>", ...]   # REQUIRED whenever §6.4's enumeration identifies this route as part of a shadowed pair; CI reads this field, not free-text `note:`
  source: "epic-b-revision-6 | route-security-registry-v1 | <mission/PR reference>"   # provenance, so a future reader knows whether a number is inherited from this mission's derivation or freshly reviewed
```

### 6.2 Worked entries (pilot — the routes this mission has actually analyzed in depth)

Populated here, by hand, only for routes this mission examined with real evidence — not invented for
routes never looked at, per this project's own discipline against unfounded claims. Full population
across all ~600 live routes is explicitly **not** done in this document; see §6.3.

```yaml
"GET /health":
  classification: [public]
  threat: [dos]
  identity_dimension: ip
  exempt: true
  exempt_reason: "Railway healthcheck path (railway.toml:5); an unscoped limit here is a deploy restart-loop risk, not a degraded feature."
  source: epic-b-revision-4

"POST /viber/webhook":
  classification: [internal-service]
  threat: [dos]
  identity_dimension: ip
  exempt: true
  exempt_reason: "Inbound provider traffic from a small shared IP set; a limit risks silently dropping legitimate client messages."
  source: epic-b-revision-4

"POST /api/sesija/ping":
  classification: [authenticated-heavy-workload]
  threat: [dos]
  identity_dimension: ip
  exempt: true
  exempt_reason: "60-second heartbeat (vindex.js:189); at 50 lawyers x 2 tabs this is 3,000-6,000/h from one office IP -- any per-IP ceiling in a plausible range is either useless or breaks the single-device-session feature this heartbeat drives. Already has a per-user_id backstop (api.py:934) for the actual abuse case; the IP dimension adds nothing but NAT breakage."
  source: epic-b-revision-6

"GET /klijenti":
  classification: [authenticated-heavy-workload]
  threat: [scraping, enumeration]
  identity_dimension: user_id
  limiter:
    - strategy: "user_id, via per-decorator key_func override (confirmed working under SlowAPIMiddleware, terminal Red Team pass)"
      burst: "30/minute"
      sustained: "400/hour"
  rationale:
    formula: "heavy-use estimate (debounced type-ahead, 300ms debounce, vindex.js:20351): ~8 req/lookup x ~10 lookups/hour x ~5 headroom multiplier = 400/hour"
    reason: "prevents a single compromised/scripted session from enumerating or scraping the full client book via search; identity unresolvable case cannot occur -- route requires an authenticated session"
    expected_workload: "~80 requests/hour for one heavy-use lawyer (~8 requests per client lookup under natural typing pauses, ~10 lookups/hour); NOT measured production traffic"
  reviewed: true
  source: epic-b-revision-6

"POST /api/security/csp-report":
  classification: [public]
  threat: [abuse, dos]
  identity_dimension: ip
  limiter:
    - strategy: ip
      burst: "5/minute"
      sustained: "20/hour"
  rationale:
    formula: "legitimate-session estimate (single digits per session) x ~several-fold headroom = 20/hour"
    reason: "prevents unauthenticated flooding of the security_events audit table this route writes to unconditionally"
    expected_workload: "a real browser reports a CSP violation only when one actually occurs -- typically under 5 per session even for a misconfigured page; NOT measured production traffic"
  reviewed: true
  source: epic-b-revision-6

"GET /klijenti/retention-check":
  classification: [authenticated-user]
  threat: [dos, cost-amplification]
  identity_dimension: user_id
  limiter:
    - strategy: user_id
      burst: "5/minute"
      sustained: "30/hour"
  rationale:
    formula: "policy floor -- infrequent administrative check (a handful/session), no legitimate high-frequency use case, 30/hour ceiling"
    reason: "prevents unbounded repeated invocation of an inadequately-bounded scan (threshold_years has no lower bound; =0 returns every active client); identity unresolvable case cannot occur -- route requires an authenticated session"
    expected_workload: "an admin checking retention status a handful of times (under 10) per session"
  reviewed: true
  shadow_pair_with: ["GET /klijenti/{klijent_id}"]
  source: epic-b-revision-6

"GET /klijenti/{klijent_id}":
  classification: [authenticated-user]
  threat: [scraping, enumeration]
  identity_dimension: user_id
  scope: fixed
  limiter:
    - strategy: "user_id, with an explicit scope= override so all enumerated klijent_id values share one bucket instead of one bucket per ID"
      burst: "60/minute"
      sustained: "600/hour"
  rationale:
    formula: "per-client detail views during normal casework (tens/hour) x headroom = 600/hour"
    reason: "prevents scraping the full client book by enumerating IDs -- a plain per-route decorator under key_style=url gives zero aggregate protection here (measured: 30 distinct IDs, 0x429), hence scope: fixed is mandatory, not optional"
    expected_workload: "a lawyer opening client records during normal casework, under 60 per hour at most"
  reviewed: true
  shadow_pair_with: ["GET /klijenti/retention-check"]
  source: epic-b-revision-6

"GET /api/predmeti/{predmet_id}":
  classification: [authenticated-user]
  threat: [scraping]
  identity_dimension: user_id
  scope: fixed
  limiter:
    - strategy: "user_id, with an explicit scope= override, same reasoning as klijenti/{klijent_id}"
      burst: "60/minute"
      sustained: "600/hour"
  rationale:
    formula: "already-tuned per-route decorator (api.py:3440-3441, 60/minute), scope: fixed added without changing the numeric limit"
    reason: "prevents scraping across 5,000+ matters -- decoration alone under key_style=url does not aggregate across IDs (terminal pass Test 3b), hence scope: fixed is mandatory"
    expected_workload: "unchanged from the existing, already-live 60/minute decision (~60 detail views/hour per lawyer)"
  reviewed: true
  source: epic-b-revision-6

"GET /api/simulator/{predmet_id}/partije":
  classification: [authenticated-user]
  threat: [dos]
  identity_dimension: user_id
  limiter:
    - strategy: user_id
      burst: "30/minute"
      sustained: "300/hour"
  rationale:
    formula: "policy floor -- unreviewed, default-deny friction ceiling"
    reason: "default-deny friction; not individually reviewed beyond the shadow-pair fix required by parity with the sibling route below"
    expected_workload: "N/A -- reviewed: false; see §5's content-predicate exemption for honestly-flagged placeholders"
  reviewed: false
  shadow_pair_with: ["GET /api/simulator/partija/{partija_id}"]
  source: epic-b-revision-6

"GET /api/simulator/partija/{partija_id}":
  classification: [authenticated-user]
  threat: [dos]
  identity_dimension: user_id
  limiter:
    - strategy: user_id
      burst: "30/minute"
      sustained: "300/hour"
  rationale:
    formula: "policy floor -- unreviewed, matched to its shadow-pair sibling above"
    reason: "default-deny friction; parity with the sibling route is the actual security property here, not this specific number"
    expected_workload: "N/A -- reviewed: false"
  reviewed: false
  shadow_pair_with: ["GET /api/simulator/{predmet_id}/partije"]
  source: epic-b-revision-6

"WS /api/voice/realtime/ws":
  classification: [non-http-stream]
  threat: [cost-amplification, dos]
  identity_dimension: user_id
  concurrency: "2 per user_id, process-local -- effective ceiling is 2 x N_gunicorn_workers, not 2 (voice_realtime.py:43 is an in-process dict); centralizing this count is a separate, larger fix and out of scope for this registry entry, but the divergence must be stated, not hidden"
  rationale:
    formula: "existing _MAX_CONCURRENT_SESSIONS_PER_USER = 2 constant (voice_realtime.py:42), carried forward as-is"
    reason: "prevents one account from holding open unbounded concurrent metered OpenAI Realtime API streams; slowapi cannot enforce this at all -- confirmed the decorator raises at connection time (not import time) if applied to a WebSocket route, so this route is NOT decorated with @limiter.limit and relies entirely on the application-level concurrency cap"
    expected_workload: "a lawyer using voice features typically holds 1 session per tab"
  reviewed: true
  source: route-security-model-post-red-team

"GET /api/admin/ingest/job/{job_id}":
  classification: [privileged-admin, authenticated-heavy-workload]
  threat: [dos]
  identity_dimension: user_id
  scope: fixed
  limiter:
    - strategy: "user_id, scope=fixed so polling one job doesn't create per-job buckets an attacker could otherwise use to bypass a per-value ceiling"
      burst: "60/minute"
      sustained: "600/hour"
  rationale:
    formula: "job-status poll cadence (comparable to /api/jobs/{job_id}'s existing 4-second poll pattern) x headroom = 600/hour"
    reason: "worked example of the conditional-mandatory compound tag (§1): this route is admin-gated (Depends(_require_admin)) AND UI-polled -- both tags are required, not a choice between them, since dropping authenticated-heavy-workload would leave the polling frequency unsized"
    expected_workload: "one admin polling one ingest job's status every few seconds for the job's duration"
  reviewed: true
  source: route-security-model-post-red-team
```

The remaining 5 shadow pairs (`client_twin` dashboard/profil, `predmeti` bulk/dashboard, `search`
global, and the 6th pair found by the model's own Red Team pass — `GET /api/spisi/{spis_id}/verzije/latest`
vs. `GET /api/spisi/nacrti/verzije/{verzija_id}`, a **hypothetical future-route scenario used to test
the enumeration method, not a route that exists in the repo today** — kept here as the regression
fixture §6.4's check must be run against) need a registry entry each, with `shadow_pair_with` set on
both sides, not a new number for the already-decorated ones; carry their existing live decorator
values forward into the registry rather than re-deriving them here.

### 6.3 Full population is an implementation-phase task, not hand-authored here

Populating this registry for the remaining ~590 live routes must be done by a script that:
1. Enumerates the live route table the same way the Red Team passes did (`import api`, walk
   `app.routes`, not a static grep) — the only method proven to produce an authoritative count in
   this mission (599-602 depending on measurement pass; reconcile precisely at implementation time).
   Non-HTTP routes (`WebSocketRoute`, or any route object lacking a `.methods` attribute) must be
   enumerated explicitly into the `"WS <path>"` key form (§6.1), not silently skipped by a
   method-keyed walker — verified this is exactly what a naive `getattr(r, "methods", [])` walker
   does today, and it is precisely how a non-HTTP route could reach step 3 below without ever being
   flagged, since a route the walker never iterates can't be flagged as unclassifiable either.
2. Applies this document's classification rules as a first pass — but **treats in-body role/founder
   gates as classification signals, not just `Depends`**, corrected because the naive
   `Depends`-only rule was proven to confidently (and wrongly) classify at least one live founder-
   gated route (`GET /api/apr/metrics`, gated by an in-body `if not _is_founder(...)` check with no
   corresponding `Depends`) as plain `authenticated-user`, meaning step 3's review-flag never fired
   for it. Concretely: any route whose module contains a call to a known role/founder-gate function
   (`_is_founder`, `_require_admin`, `_require_firma_admin`, or equivalent) is classified
   `privileged-admin` regardless of its `Depends` list, or — if the script cannot confirm the gate
   actually applies to this specific route within the module — flagged low-confidence rather than
   silently defaulted to `authenticated-user`.
3. Flags every route the script cannot confidently classify for manual Security & Privacy Architect
   review — this document does not claim automatic classification will be fully accurate, only that
   it is where the ~590 remaining entries must start from, not be invented wholesale by an
   architecture document with no evidence for any specific one of them.

## 6.4 CI Enforcement Specification (previously missing — added post-model Red Team pass)

The prior version of this document referenced "§6.4" four times as the CI enforcement mechanism
without ever writing it — found by the model's own Red Team pass and the single most important gap
it identified, since every "mechanically enforced" claim elsewhere in this document rested on a
section that did not exist. This section is that specification.

CI runs against `docs/security/route_security_registry.yaml` and the live route table (obtained by
importing the app and walking `app.routes`, per §6.3 step 1 — never a static grep, which is what
produced the false negatives found in Test D of the model's own Red Team report) and fails the build
on any of the following:

1. **Coverage.** Every route in the live table has a corresponding registry entry (by the key format
   in §6.1, including the `"WS <path>"` form for non-HTTP routes). A route present in the app but
   absent from the registry fails.
2. **Field completeness and validity.** Every entry has valid `classification` (from the enum in §1,
   including `non-http-stream`), `threat` (length ≥ 1, from §2's enum), `identity_dimension` (from
   §3's enum), and either `exempt: true` + `exempt_reason`, or a complete `limiter` (list, ≥1 entry,
   2 entries if `identity_dimension: composite`) + `rationale` block, or (for `non-http-stream`
   routes) a `concurrency` field + `rationale` in place of `limiter`.
3. **`scope` requirement.** Every entry whose key contains a path parameter (`{...}`) has an explicit
   `scope` field (`per_value` or `fixed`) — a missing `scope` on a parameterized route fails, it does
   not default to either value. An entry with `threat` including `scraping` and `scope: per_value`
   fails (an explicit, self-contradictory combination — scraping protection was claimed while
   choosing the bucketing mode that provides none).
4. **Content predicates (§5), skippable only via `reviewed: false`.** For every entry with
   `reviewed: true` (the default) and not `exempt`: `expected_workload` must match a pattern
   containing a number, a time-unit token (`/hour`, `/minute`, `/day`, or equivalent), and an actor
   noun; `formula` must contain at least one numeral that also appears in `expected_workload`;
   `sustained` (from each `limiter` entry) must be numerically ≥ the number extracted from
   `expected_workload`. An entry with `reviewed: false` is exempt from these three checks but still
   must pass checks 1-3 — `reviewed: false` marks an honest placeholder, not a way to skip
   classification.
5. **Denylist for placeholder boilerplate.** Regardless of the `reviewed` flag, `expected_workload`
   and `reason` fail if they match the literal strings this document's own pre-correction pilot
   entries used as placeholders (`"not calibrated to a specific workload"`, `"not individually
   reviewed"`) unless `reviewed: false` is also set — closing the exact loophole the model's Red Team
   pass found, where this document's own worked examples were directly copy-pasteable as
   content-free entries.
6. **Shadow-pair discovery and parity — the algorithm, specified precisely because a naive version
   was proven to have a false negative.** Do **not** implement this as "probe each route's own
   template with a dummy value and see what else matches" — verified this method misses pairs whose
   parameters sit at different segment positions (found live: `strategy_simulator.py:471`/`:502`;
   reproduced hypothetically for a future-route scenario in §6.2's `spisi` example). Instead:
   - For every **pair** of routes sharing the same HTTP method and the same segment count, construct
     a witness path segment-by-segment: for each segment position, use the **literal** value if
     either route has a literal there, or a placeholder token if both routes have a parameter there.
   - Test the witness against both routes' compiled path patterns (Starlette's own `compile_path`).
     If both match, the pair is shadowed.
   - Separately handle any route using a path-converter catch-all (`{x:path}`, `{x:int}`, `{x:uuid}`
     with unbounded matching behavior) — these can shadow routes at a **different segment count**,
     which the equal-segment-count pairwise method above does not check; enumerate these against
     every route of any segment length that could plausibly fall under the catch-all's prefix.
   - For every shadowed pair found, determine which route Starlette actually serves (first full
     match, in registration order) versus which route slowapi's `_should_exempt` would resolve to
     (last full match, per `_find_route_handler`). If these differ and the two routes' decoration/
     exemption status differs, that is a live bypass — **CI fails**.
   - The **decorated/exempt oracle** this check reads is `app.state.limiter._route_limits` and
     `app.state.limiter._exempt_routes` **only** — not `_dynamic_route_limits` (which holds callable,
     non-static limit values and is consulted by a different code path the middleware's exemption
     check never reads), and not the registry's own `limiter`/`exempt` fields in isolation, since the
     actual runtime behavior is what must be checked, not just what the registry claims.
   - Every route found to be part of a shadowed pair must have `shadow_pair_with` populated
     (§6.1) on both sides — an entry missing this field despite being part of a detected pair fails.
7. **Registry/runtime cross-check for `exempt: true`.** An entry marked `exempt: true` must
   correspond to an actual `@limiter.exempt(...)` registration or equivalent — not merely to the
   absence of a `@limiter.limit(...)` decorator, since an "exempt" route with no exemption call still
   receives the app-wide default per §4/Epic B's own history. A registry claiming exemption that the
   runtime does not actually grant is exactly the registry/runtime divergence class this document
   exists to prevent, and must fail CI, not merely fail a future Red Team pass.

## 7. What the next Red Team pass on this model should test

The model's first Red Team pass (`.vindex_ai_team/decisions/RED_TEAM_REPORT_2026-08-02_route_security_model.md`)
found genuine structural gaps in all 5 of the tests below and is why this section, and most of the
document above it, now reads differently from its original version. Per this project's standing rule
that CLOSED findings lock and only reopen on a real change ([[feedback_red_team_closed_findings_lock]]
/ `ESCALATION_RULES.md`), a next pass should be a **narrower, falsification-only** check of the
specific fixes below — not a full re-derivation of all 5 tests from scratch:

- **Test A, re-check** — does the stacked-decorator mechanism for `composite`, and the required
  `limiter` list schema, actually get correctly implemented for the one live route that might need it
  (if any is found during full registry population, §6.3), or does the "single concatenated key"
  anti-pattern reappear despite being named explicitly?
- **Test B, re-check** — does `non-http-stream` plus the `concurrency` field actually cover every
  non-HTTP route found during full population (§6.3), not just the one worked example
  (`/api/voice/realtime/ws`)? Are there other in-body-gated admin routes beyond `/api/apr/metrics`,
  `/api/analytics/...`, `/api/corrections/...` that the corrected §6.3 rule still misses?
- **Test C, re-check** — falsification-only: try to construct a new content-free-but-passing entry
  against the corrected §5/§6.4 content predicates (numeral-in-workload, formula-references-workload,
  `sustained` ≥ workload number, denylist). If none can be constructed, this closes.
- **Test D, re-check** — falsification-only: run the corrected §6.4 pairwise-witness algorithm (or a
  faithful description of it) against the `spisi` hypothetical pair from §6.2 and confirm it is
  actually found (it is designed to be found by construction — verify this isn't circular).
  Separately, try to construct a *different* future-route scenario the corrected algorithm still
  misses (e.g. involving a catch-all converter, which §6.4 step 6's third bullet claims to handle
  but which was not behaviorally tested against a real catch-all route in this repo, since none
  currently exist).
- **Test E, re-check** — with all corrections applied, re-walk Epic B's 5 original findings once
  more: does the corrected model now force all 5 to surface (not just #2 and #4, as the first pass
  found), specifically finding #1 (Limiter-instance wiring — note this may remain legitimately out of
  scope for a *per-route* registry, and if so the model should say so explicitly rather than silently
  fail to mention it) and #5 (the `key_style="url"` no-op, which the new `scope` field is intended to
  close)?
