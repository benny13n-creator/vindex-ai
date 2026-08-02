# Architecture Decision — Forensic Audit Remediation & Enterprise Security Readiness

**Author (role):** AI CTO / Chief Architect + Solution Architect (Phase 1 Product Discovery folded in)
**Date:** 2026-08-02. **Revision 7** — see "Revision history" below.
**Status:** Draft — per founder direction, Epic B's rate-limiting fixes are now formalized under `docs/architecture/ROUTE_SECURITY_MODEL.md` (a Route Classification / Threat Model / Identity Dimension / Limit Derivation methodology + Route Security Registry + CI enforcement spec), superseding ad hoc patch-by-patch fixes. One final Red Team pass, scoped to the model itself, is pending — see that document's §7.
**Source:** `docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md`

## Revision history

- **Revision 1** (this document): initial epic grouping of the forensic audit's findings.
- **Revision 2** (this document): independent Red Team review (fresh agent, no authorship stake)
  returned **BLOCKING: 4 Critical, 5 High, 3 Medium, 1 Low**. Three of the four Critical findings
  were spot-verified directly against code/source documents before accepting them (grep confirmed
  zero "cohere" mentions in the Program 1 spec; `uploaded_doc/session.py::validate_session`
  confirmed to take no `user_id` parameter; `AUTHORIZATION_PATTERN_RECOMMENDATION.md` §5 confirmed
  to state verbatim what the Red Team quoted). All four Criticals, all five Highs, and all three
  Mediums are addressed below — this is a substantive rewrite of Phase 2, not a wording pass.
  Summary of what changed:
  - **Epic C decoupled from Program 3.** Revision 1 claimed the `verify_predmet_ownership`
    consolidation (Program 3) would prevent SEC-039/040/059. Verified false: SEC-039 is scoped by
    Pinecone `session_id` with no owning table; SEC-040 needs a 3-table join; SEC-059 is mass
    assignment on an INSERT, not an ownership check. All three are now independent, targeted fixes.
    SEC-004 is restated as **not closed** by this epic or by Program 3 — `AUTHORIZATION_PATTERN_RECOMMENDATION.md`
    §5's own text says the two "are not substitutes for each other." SEC-041 added here (was
    mis-binned in Epic G as Low/Trivial; it is HIGH severity, Medium complexity).
  - **SEC-051 moved out of the Program 1/AI epic, into GDPR/Lifecycle, and reduced to what it
    actually is.** Verified: the Program 1 spec never mentions Cohere, and the chokepoint mechanism
    it describes only covers `openai.*`/`langchain_openai.*` classes — Cohere is a separate client
    (`app/services/retrieve.py:1229-1234`) it does not and cannot govern. 5 of SEC-051's 6
    recipients (Twilio/Meta/Viber/SMTP/Sentry) aren't AI surfaces at all. The actual fix is a
    documentation deliverable (`privacy.html`/`dpa.html` Annex B) plus, separately, an engineering
    option to disable Cohere (Trivial — clean existing fallback).
  - **SEC-006 gets an immediate interim fix**, not a deferral. Verified the Program 1 spec's own
    text (§5, describing `_skini_pii`): *"becomes one input into a broader classification... PII
    tags are an output of Classification, not a thing checked before it"* — Program 1 **absorbs**
    the existing function, it does not replace it. Wiring `_skini_pii` into the Genome path today
    is forward-compatible, not throwaway work.
  - **Two silently-dropped items restored**: a real matter/document delete path (§15's own "minimum
    set to unlock medium firms" named this explicitly; it was missing from every epic in Revision
    1), and SEC-045 (no malware scanning — confused in Revision 1 with the unrelated SEC-045-admin).
  - **SEC-050 split.** It was overloaded across two different findings in the source audit (an
    audit-*coverage* gap and an exception-*leak* gap); Revision 1 inherited the collision and
    scheduled only one of them. Both are now separately tracked.
  - **Epic F re-sequenced and re-scoped.** SEC-056 is ungated (encrypting a 4th path into an
    already-encrypted corpus adds no new key-rotation blast radius, so gating it behind SEC-024 was
    unjustified). SEC-057 is rescoped from a "search redesign" (verified false — `routers/search.py`
    reads a different table, `uploaded_documents.extracted_text`) to what it actually is: a
    decrypt-on-read migration across 13+ reader sites in Case Genome, Evidence, Drafting, and
    Case Commander. Its design phase now runs in parallel with SEC-024, only its bulk backfill
    is gated on rotation landing first.
  - **Epic G's dependencies made explicit** (SEC-069-comparison depends on Epic B shipping first;
    SEC-014 depends on SEC-050's exception-leak item and the SEC-036 sanitizer gaps shipping first)
    and its complexity claims corrected against the Gap Register.
  - **New Epic H** for structural/process fixes the Red Team's completeness check surfaced as
    missing entirely: the audit-coverage half of SEC-050, a CI check that closes the recurring
    "control that looks live but silently isn't" bug class structurally instead of catching a
    fourth instance one at a time, the duplicated `_verify_token` cross-cutting cleanup, and the
    Supabase Auth config export recommendation from the audit's own §1.
  - **Full reconciliation table added** (every finding named anywhere in the source audit mapped to
    exactly one epic or explicitly marked deliberately deferred) — its absence in Revision 1 is what
    let two items disappear silently.
  - **Explicit answer added for "only one epic can start right now."**

- **Revision 3** (this document): a second, narrower targeted Red Team re-check of Revision 2's
  fixes returned **BLOCKING: 1 High remaining, 3 Medium/Low residue** — a real improvement (all 4
  Criticals, 3 of 5 Highs, and 2 of 3 Mediums from pass 1 confirmed FULLY CLOSED on independent
  re-derivation), but not yet clear. Fixed below:
  - **Epic B's own root-cause claim was itself wrong, and its fix was a no-op.** Revision 2 claimed
    the two `Limiter` instances have "no shared counters," citing `shared/rate.py`'s docstring —
    that docstring says the opposite: with `REDIS_URL` set, both instances share one Redis keyspace,
    so counters genuinely are shared. The real, unstated mechanism: `SlowAPIMiddleware`'s
    `_should_exempt` check reads `app.state.limiter._route_limits` — `app.state.limiter` is only
    `api.py`'s instance (`api.py:547-549`), holding just its own 29 decorated routes. The other 415
    `@limiter.limit(...)` decorations across `routers/`+`klijenti/` register against
    `shared.rate.limiter`, a *different object* — invisible to `_should_exempt`. Registering the
    middleware as Revision 2 instructed ("verify or reconcile which instance it binds to") would
    have shipped a regression: the `60/hour` default applied on top of every one of those 415
    routes' own, much higher, intended limits. Corrected below to the actual fix: collapse to a
    single `Limiter` instance used everywhere (both for route decoration and as `app.state.limiter`),
    not a verification step.
  - **SEC-057's reader-site list corrected.** Two entries were writes mislabeled as reads
    (`drafting.py:307`, `smart_intake.py:578`); a third write site was missing (`api.py:4299`); one
    real reader was missing (`scripts/genome_bootstrap_sample.py:77`).
  - **SEC-014's dependency corrected.** It was bound to Epic G's SEC-050 (exception-leak) item;
    the audit's own citation (`:602`) is about the *audit-coverage* half, which Revision 2 itself
    moved to Epic H. Corrected to depend on Epic H's item.
  - **SEC-072→FK-retype dependency corrected.** Revision 2 claimed the source audit calls for a
    "purge policy" before the FK migration; the audit's actual text (`:641`) says a live
    **orphan-row check**, not a purge. Corrected to: run the check first; the FK migration does not
    need to wait for a full purge-policy *implementation*, only for that check's result.
  - Reconciliation table re-verified independently (all 44 Gap Register IDs mapped, none dropped) —
    no changes needed there.

- **Revision 4** (this document): a third, narrow, falsification-only Red Team pass scoped strictly
  to Epic B's collapse fix (no other epic reviewed). Verdict: **BLOCKING — 1 High, 1 Medium, 3
  Low/Info** — but the collapse itself was independently attacked seven different ways (circular
  import, hidden separation rationale, registration ordering, hidden `app.state.limiter`
  dependents, a route-shadowing quirk, `BaseHTTPMiddleware`-vs-SSE risk, and the brief's own
  suggested "simpler alternative") and **held on all seven** — confirmed sound, not assumed.
  What still blocked: registering the middleware after the collapse inherits `_DEFAULT_LIMITS`
  (`60/hour`) as an **unscoped, unexempted** app-wide default, which lands on the 153
  *undecorated* routes — including `/health` (Railway's own healthcheck path — restart-loop risk),
  `/api/sesija/ping` (a 60-second heartbeat, i.e. already at the limit boundary for one single
  user), the app-shell routes, the Viber webhook, and all 20 `klijenti/` CRM routes (confirmed to
  have zero decorations, correcting Revision 3's "`routers/*.py`+`klijenti/`" wording — only
  `routers/` actually has decorations). The codebase's own existing per-user middleware
  (`api.py:924`'s comment, `_USER_API_LIMIT = 600/hour`) is direct evidence this team already
  chose a NAT-aware ceiling 10× looser than what an unscoped default would silently impose
  underneath it. A second, Medium finding: `Limiter`'s default `key_style="url"` keys buckets by
  concrete path, so 36 of the undecorated routes carry path parameters and would still be
  enumerable per-value even after the fix — the exact abuse class SEC-011 exists to close. Fixed
  below: an explicit, separately-sized default; an explicit exemption list; and — rather than
  globally flipping `key_style` (which would silently re-bucket all 444 already-tuned per-route
  limits, a collateral change out of proportion to this fix) — extending SEC-010's own decoration
  work to cover the 36 enumerable parameterized routes individually, leaving `key_style="url"`
  untouched for everything else.

- **Revision 5** (this document): the founder's 4th-pass instruction was strictly scoped to two
  named questions with an explicit closing condition ("if you can't find a concrete scenario, mark
  CLOSED — this is meant to be the last pass"). The pass **did** find concrete, reproducible
  problems on both questions — not a failure of the discipline, exactly the outcome that
  discipline exists to catch. Both are fixed below. Per the founder's own new standing rule
  ([[feedback_red_team_closed_findings_lock]] / `ESCALATION_RULES.md`) and the explicit "last pass"
  framing, **a 5th Red Team pass is not auto-launched** — this revision goes to the founder
  directly for a decision on whether one further, even-narrower check is warranted or whether to
  proceed.
  - **Q1 fix — route-shadowing exemption bypass.** The pass reproduced, in-process against the live
    route table, that decorating `/klijenti/{klijent_id}` (Revision 4's own item (d)) causes
    `GET /klijenti/retention-check` — an undecorated sibling registered earlier so Starlette's
    first-match routing serves it correctly — to be treated as fully exempt by slowapi's
    `_find_route_handler`, which resolves **last**-match instead. Net effect: that route goes from
    *covered by the app-wide default* to **completely unlimited**, and it is a filtered,
    unbounded-by-input DB scan (`threshold_years: int = 10` has no lower bound — `=0` returns every
    active client). Fixed by explicitly decorating every route on the losing side of the 5
    confirmed shadowed pairs app-wide (not just this one), and adding a structural check (folded
    into Epic H) so a future decoration change can't silently reopen this class.
  - **Q2 fix — `600/hour` had an inverted citation and wrong denominator.** The line Revision 4 cited
    (`api.py:924-925`) says the opposite of what it was cited for: it describes a **per-user_id**,
    `/api/*`-only, authenticated backstop that is *deliberately laxer than* the IP limit — not a
    template for the IP limit's value. Applied as a flat per-IP-per-exact-path default, `600/hour`
    is simultaneously ~109× too loose in aggregate (109 remaining plain paths × 600 = 65,400/h per
    IP) and too tight for the plan's own cited NAT scenario on at least one core route (`/klijenti`
    type-ahead search, no per-user backstop, shared bucket across the whole office). Fixed by
    rejecting a single flat number for a population this heterogeneous: unauthenticated
    state-mutating routes (e.g. `/api/security/csp-report`, writing into the security audit table
    itself) and high-frequency authenticated UI-backend routes with no existing backstop (e.g.
    `/klijenti` search) get their own individually-derived limits instead of inheriting the
    app-wide default; the app-wide default itself is lowered and reframed as intentional
    default-deny friction for the genuinely-unassessed remainder, not a number claimed to be
    calibrated to any specific workload.

- **Revision 6** (this document): the founder's terminal 3-test pass returned **BLOCKING on all 3**
  — Revision 5's core design choices (the collapse, the parity invariant, the 3-tier shape, keeping
  `key_style="url"`) all survived direct attack, but the specification around them did not. The pass
  also surfaced, unprompted but honestly, a self-inflicted regression: Revision 5's table relettering
  dropped the explicit exemption-list text (it was only referenced obliquely afterward, in the
  "Downgraded claim" paragraph) — never revoked, but an implementer reading the Epic B table alone
  would not know it existed. Fixed below, all four:
  - **Test 1 fix — the enumeration method, not the invariant.** The pass proved the parity invariant
    itself (decoration/exemption parity between the first-full-match and last-full-match route) is
    complete — 4 separate attacks on it failed. What failed: the natural implementation of "enumerate
    shadowed pairs" (probe each route's own template) has a proven false negative — an exhaustive
    pairwise check found a **6th** live pair (`routers/strategy_simulator.py:471`/`:502`, both
    undecorated, currently benign) that the per-template method cannot see by construction. The pass
    also built a concrete future scenario (a new parameterized route added in a different file, whose
    parameter sits in a different segment position) that defeats *both* the per-template method and a
    literal implementation of Epic H's prior wording, with CI staying green. Epic H's row is rewritten
    below to specify the enumeration method itself, not just what it should assert.
  - **Test 2 fix — each tier now states an attack, a workload, and a number.** The pass graded all
    three tiers against `limit = workload model + security objective` and found 0 of 3 complete —
    tier (i) had the attack but not the workload or number; tier (ii) had the workload but not the
    attack or number (though it confirmed the per-decorator `key_func` override actually works under
    the middleware); tier (iii) had neither, and was additionally falsified by its own criterion
    mis-sorting `/api/sesija/ping` (see Test 3). All three now get concrete figures below, derived
    from stated assumptions (not measured production traffic — flagged honestly as CTO-level starting
    estimates for Backend Engineering/QA to sanity-check against real logs, the same measured-vs-
    calculated discipline this project already applies elsewhere). `application_limits` — a genuine
    aggregate ceiling slowapi already supports and the plan never mentioned — is added as tier (iii)'s
    structural backstop against the N×D aggregate problem, rather than hoping N stays small.
  - **Test 3 fix (a) — `/api/sesija/ping` restored to the exemption list.** Tier (iii)'s sorting
    criterion ("outside `/api/`, no per-user backstop") was dimensionally wrong: the existing backstop
    it checked for is keyed by `user_id`, while the new default is keyed by IP — a per-user backstop
    provides zero protection against NAT aggregation. Reproduced arithmetic: 50 lawyers × 60 pings/hour
    = 3,000/hour from one office IP against a "low hundreds/hour" tier-iii ceiling. Corrected: the
    sorting criterion itself is replaced (below) with one based on known aggregate traffic risk, not
    prefix/backstop existence, and `/api/sesija/ping` — plus 5 low-value, once-per-boot routes on the
    same gradient — move to the exemption list.
  - **Test 3 fix (b) — SEC-011(d)'s claimed remedy for scraping was a no-op, now actually fixed.**
    `key_style="url"` buckets by the *concrete* path, so a decorated parameterized route (`3/minute`)
    gave a scraper enumerating 30 distinct IDs **zero** 429s — each ID gets its own independent
    bucket. Revision 5 claimed SEC-010's decoration closed this; it does not, and the pass proved it
    live. Fixed below: scrape-target routes (`/api/predmeti/{predmet_id}`, `/klijenti/{klijent_id}`,
    and the rest of SEC-010's parameterized set) require an explicit fixed `scope=` override (slowapi
    supports this — `lim.scope or endpoint` — confirmed in source) so all enumerated ID values
    collapse into one shared bucket instead of each getting its own.
  - **Founder note:** this is the 5th consecutive Red Team pass to find something real on this one
    epic, and the pass that was meant to be terminal did not close it. Per the founder's own
    escalation discipline, this revision is presented directly for founder direction — run one more
    strictly-scoped pass (and if so, on what exact scope, given the terminal test's own 3 questions
    are now individually addressed rather than open), or handle differently — rather than an
    automatic 6th pass being launched unilaterally.

---

## Phase 1 — Product Discovery (unchanged from Revision 1 — not challenged by Red Team)

**Problem:** the forensic audit scored Vindex AI 52/100, found 2 live-severity items (SEC-037,
SEC-038), and diagnosed a repeating root cause: narrow, inconsistent application of an
already-correct pattern. §15 named specific blockers to medium+ firm, government, and
regulated-enterprise deployment.

**Who benefits:** every future customer above solo/small-practice scale, and current customers
directly (SEC-037/038 are live exposure regardless of segment).

**How this is handled today:** ad hoc — a flat audit document, no epic structure, no dependency
graph, no reconciliation against already-planned architecture work.

**Value:** closes live risk; unlocks medium+ firm and, eventually, government/regulated deployment;
validates whether this organization's governance workflow actually catches what a single pass
misses — which, per Revision 1→2, it demonstrably did.

**MVP framing:** this document defines the roadmap. It implements nothing, per explicit founder
instruction.

---

## Phase 2 — Architecture Review: Epics, Corrected

### Epic A — Immediate Risk Closure
| Finding | Action | Owner (founder-time vs. engineering-time) |
|---|---|---|
| SEC-037 | Rotate OpenAI key; audit usage since exposure date; decide on git-history rewrite | **Founder** — not engineering capacity |
| SEC-038 | 30-second live test; then fix RLS policy + grant | **Founder** (test) → **Engineering** (fix, small diff) |
| SEC-058 | Delete PII-dumping log lines in **both** `shared/deps.py:229` **and** `api.py:216`(the audit's own cross-cutting note records these as two independent copies of `_verify_token` — fixing one and not the other leaves a live leak) | Engineering, trivial |

**Why first, and why this doesn't compete for the "one epic" answer below:** SEC-037/038's first
steps are founder actions, not engineering capacity; SEC-058 is a 2-line diff. This epic should
proceed regardless of any bandwidth-constrained prioritization decision made for the epics below.

### Epic B — Rate Limiting & Abuse Surface (Revision 7 — superseded by a formal model, see below)

**Revision 7 note:** after Revision 6's fixes, the founder's assessment of the pattern across 5
consecutive real findings was that the actual defect was never any single patch — it was the absence
of a formal methodology for defining a route's security posture, meaning a 6th, unexamined route
could reproduce the same class of defect regardless of how well Epic B's specific fixes held up.
Per that direction, Epic B's tiered-default system below is now **specified by, and subordinate to**,
`docs/architecture/ROUTE_SECURITY_MODEL.md` — a formal Route Classification / Threat Model /
Identity Dimension / Limit Derivation taxonomy, materialized as a versioned Route Security Registry
(`docs/security/route_security_registry.yaml`), with a CI check requiring every live route to have a
registry entry with a real classification, threat, identity dimension, and (unless explicitly
exempted with a stated reason) a derived limit. Epic B's substantive fixes below are preserved
exactly — the collapse, the 6 shadow-pair decorations, the exemption list, the `scope=` override for
scrape targets — expressed as registry entries instead of free-form epic prose. The table below is
retained as the historical record of what was found and fixed; `ROUTE_SECURITY_MODEL.md` is now the
operative specification. One final Red Team pass tests the **model itself** (can it be gamed, does
it have taxonomy gaps, does its own CI check have the blind spot the prior enumeration method had) —
not another patch-correctness pass — per the model document's §7.

(5 real Red Team passes deep on the underlying findings; see history above for what each corrected)
| Finding | Action |
|---|---|
| SEC-011 (a) — collapse | **Collapse to a single `Limiter` instance** — `api.py` imports and reuses `shared.rate.limiter` instead of constructing its own via `build_limiter`, so `app.state.limiter` and the object every `routers/*.py` file imports for `@limiter.limit(...)` decoration are the same object. Confirmed sound (11 independent falsification attempts across passes 3-5, none succeeded) |
| SEC-011 (b) — **exemption list, restored explicitly (Revision 6)** | Exempt, by name, at minimum: `/health` (Railway's healthcheck path), the app-shell routes (`/`, `/app`, `/portal`, `/sw.js`, `/manifest.json`, `/offline`), `/viber/webhook`, **and — moved here from tier (iii) in Revision 6 —** `/api/sesija/ping` plus the once-per-boot routes `/api/me`, `/api/tos/status`, `/api/plan/status`, `/api/auth/trial/status`, `/api/firm/health-index`. Independently swept and confirmed complete against the full live route table (pass 4); this list must appear explicitly in whatever document or code an implementer actually reads — Revision 5's table relettering silently dropped this list down to an indirect reference, which the terminal pass caught as a real (if not yet exploited) documentation regression |
| SEC-011 (c) — **route-shadowing fix, enumeration method corrected (Revision 6)** | Decorate the losing side of every shadowed route pair — **6** confirmed, not 5: the terminal pass found `GET /api/simulator/partija/partije` (`routers/strategy_simulator.py:471` vs. `:502`) is a 6th pair invisible to the per-route-template probing method Revision 5 used, because the two routes' parameters sit at different segment positions. slowapi's `_find_route_handler` resolves the **last** full-path match while Starlette serves the **first** — decorating `/klijenti/{klijent_id}` without also decorating `GET /klijenti/retention-check` (registered earlier specifically so Starlette serves it correctly — `klijenti/router.py:306`) would have silently stripped **all** rate limiting from `retention_check`, an authenticated but inadequately-bounded client scan (`threshold_years: int = 10` has no lower bound). Required: decorate all 6 losing-side routes explicitly |
| SEC-010 (scrape-protection fix, **new in Revision 6**) | For routes where the actual threat is bulk enumeration across many resource IDs — at minimum `/api/predmeti/{predmet_id}` and `/klijenti/{klijent_id}`, and the rest of SEC-010's 36 parameterized routes where the resource is client/matter-scoped — a plain per-route decorator gives **zero** aggregate protection under `key_style="url"`, since each ID value gets its own independent bucket (measured: 30 distinct IDs → 30×200, 0×429, even at `3/minute`). Revision 5 claimed SEC-010's decoration alone closed this; it does not. Required: these routes use an explicit fixed `scope=` argument on `@limiter.limit(...)` (slowapi supports this — `lim.scope or endpoint` in `extension.py:488` lets an explicit scope override the per-URL default), collapsing all enumerated ID values into one shared bucket per IP/user instead of one bucket per ID |
| SEC-011 (d) — key-style, unchanged since Revision 4 | Leave `key_style="url"` as-is for the collapsed instance rather than switching to `"endpoint"` globally — switching would silently re-bucket all 444 already-tuned per-route limits. The enumeration gap this leaves is closed per-route via the explicit `scope=` override above, not by a global key-style change |
| SEC-011 (e) — **default tiers, now with a stated attack, workload, and number per tier (Revision 6)** | Register `SlowAPIMiddleware` with a 3-tier default, each tier now complete against `limit = workload model + security objective` (graded 0/3 complete in the terminal pass; fixed here): **Tier (i)** — unauthenticated, state-mutating, no backstop (`/api/security/csp-report`, which inserts into `security_events` on every call, unauthenticated). *Objective:* stop unauthenticated flooding of the security-incident audit trail itself. *Workload:* a legitimate browser reports a CSP violation only when one actually occurs client-side — rare, typically single digits per session even for a misconfigured page. *Number:* **20/hour per IP** — several times the heavy-legitimate-session estimate, while making sustained flooding ineffective. **Tier (ii)** — authenticated, high-frequency, no backstop (`/klijenti` search/list). *Objective:* stop one compromised or scripted session from enumerating the full client book. *Mechanism:* key this route by `user_id`, not IP, via slowapi's per-decorator `key_func` override — **confirmed working under the middleware in the terminal pass** — which removes the NAT-sharing false-positive at its root instead of just raising a shared number. *Workload:* grounded in the debounced type-ahead handler (`vindex.js:20351`, 300ms debounce) — roughly 8 requests per client lookup under natural typing, ~10 lookups/hour for a heavy user ≈ 80/hour/lawyer. *Number:* **400/hour per user** — ~5× the heavy-use estimate, still catching a scripted enumeration attempt within the hour. **Tier (iii)** — the genuinely-unassessed remainder, **sorting criterion corrected**: Revision 5's criterion ("outside `/api/`, no per-user backstop") was dimensionally wrong — a per-`user_id` backstop provides zero protection against a per-IP default's NAT-aggregation exposure, which is exactly why it mis-sorted `/api/sesija/ping` (now moved to the exemption list, (b) above). Corrected criterion: a route stays in tier (iii) only if its known, in-repo client behavior could not plausibly approach the tier's ceiling under concurrent legitimate use at NAT-shared-IP scale — not based on URL prefix or backstop existence. *Objective:* default-deny friction for routes nobody has individually reviewed. *Workload:* explicitly not calibrated to any specific route (that is what makes something belong in this tier rather than (i)/(ii)/its own reviewed limit). *Number:* **100/hour per IP per path**, plus — **new in Revision 6** — an explicit `application_limits` **aggregate** ceiling (slowapi supports this directly, `extension.py:281-296`; unused in Revision 5, one constructor argument away in `shared/rate.py`) of **2,000/hour per IP across the whole tier-iii remainder**, closing the N×D aggregate problem structurally instead of depending on N staying small |
| SEC-048 | Fix `X-Forwarded-For` trust |
| SEC-010 (scope, carried forward) | Decorate remaining undecorated AI-cost routes, the 36 enumerable parameterized routes (with the `scope=` override above where scraping is the threat), and the tier (i)/(ii) individually-tiered routes. Most currently-undecorated routes lack a `request`/`websocket` parameter in their signature, which slowapi's decorator requires — decorating them is a signature change touching every caller/test, not a one-line addition |

**Downgraded claim (carried forward, still accurate):** after the above, SEC-011 is closed for the
444 already-decorated routes and for the undecorated routes covered by the exemption list, the
shadow-pair fix, and SEC-010's extended scope. It is **not** closed during a Redis-outage window —
`extension.py`'s documented, test-pinned fallback behavior collapses every route to one shared
`60/hour` bucket regardless of this fix, a pre-existing, separate, already-known limitation. Also not
closed: unmatched/404 paths and the `/static` mount are never subject to the app-wide default at all
(`_should_exempt` returns `True` whenever no handler resolves) — an accepted boundary of what an
application-level rate limiter can cover, not a defect this epic introduces or claims to fix. **Every
number above is a CTO-level starting estimate derived from stated assumptions, not measured
production traffic — flagged explicitly for Backend Engineering/QA to sanity-check against real
logs before finalizing, the same measured-vs-calculated discipline this project applies elsewhere.**

**Root cause, corrected across three revisions:** Revision 2 claimed the two `Limiter` instances have
"no shared counters" — false, they share a Redis keyspace when configured. Revision 3 found the real
defect (the middleware's exemption check only inspects `app.state.limiter`'s own registry, which was
`api.py`'s separate, mostly-empty instance) and the collapse fix, independently confirmed structurally
sound (no circular import, no lost configuration, no hidden dependent, no ordering issue, no new
streaming-response risk). Revision 4 scoped the post-collapse default with an explicit exemption list
and a cited sizing rationale. Revision 5, per the founder's own strict two-question falsification
pass, found the exemption *mechanism* (not the list) has a reproducible gap via route-shadowing, and
the sizing citation was inverted and denominator-mismatched — both fixed above.

### Epic C — Targeted Authorization Fixes (rewritten — decoupled from Program 3, SEC-004 honestly scoped)
| Finding | Action | Independent? |
|---|---|---|
| SEC-039 | Bind Pinecone document sessions to `user_id` at upload time; enforce it in `validate_session` | Yes |
| SEC-040 | Join `extracted_entities → intake_documents → intake_jobs.uploaded_by`; scope the correction endpoint | Yes |
| SEC-059 | Enforce the CSV-import column whitelist (`if vindex_polje not in VINDEX_POLJA: continue`); retype `klijenti.user_id` to `uuid` + FK | Yes for the whitelist (Trivial); the FK retype depends on Epic E's SEC-072 **check** (not a full purge-policy implementation, corrected in Revision 3 — see Epic E) running first |
| SEC-041 | Add `kancelarija_id` to `user_roles`; require the target to be an active member of the caller's firm before a role-assignment succeeds | Yes — **moved here from Epic G's "whenever convenient" batch; this is the audit's only HIGH-severity finding that had no priority treatment in Revision 1** |
| SEC-033 | Prioritize `klijenti.user_id`/`api_kljucevi.user_id` ahead of the rest of the deferred Integrity Audit census | Same dependency as SEC-059's FK part |

**SEC-004, honestly restated (Revision 1's Critical error):** this epic does **not** close SEC-004.
`AUTHORIZATION_PATTERN_RECOMMENDATION.md` §5, quoted directly: *"it does not remove the underlying
architectural fact named in SEC-004... it does not make the boundary self-enforcing the way real
RLS would if the backend used a non-service-role connection. Both are worth doing; they are not
substitutes for each other."* SEC-004 remains open, tracked as its own long-term item (moving off
the single service-role client), not marked remediated by anything in this plan.

**Program 3 (Access Control), correctly scoped:** Program 3's `verify_predmet_ownership`
consolidation is a **separate, parallel track** — its actual scope is the `predmet_id`-ownership
pattern (~18 call sites per `AUTHORIZATION_PATTERN_RECOMMENDATION.md`'s own survey), which is a
different resource shape than SEC-039 (`session_id`), SEC-040 (`entity_id`, 3-table join), or
SEC-059 (an INSERT, not an ownership check). Program 3 can and should start on its own timeline,
per the Traceability doc's existing P3→P2→P1→P4 sequence — it is not gated by this epic, and this
epic is not satisfied by it.

### Epic D — AI Retrieval Isolation + Interim PII Fix (rewritten — SEC-051 removed, SEC-006 no longer deferred)
| Finding | Action |
|---|---|
| SEC-054 | Matter-scoped Pinecone retrieval filter (add `predmet_id`/allowed-matter-list to the metadata filter) |
| SEC-006 (interim) | Wire the existing `main.py::_skini_pii` into `routers/case_dna.py` and `services/legal_reasoning_engine.py` **now** — covers the categories `_skini_pii` already handles (numeric IDs, email, heuristic addresses); does not require NER and does not need to be redone once Program 1 ships, since Program 1's own spec (§5) describes `_skini_pii` becoming an *input into* Classification, not something it replaces |

**Both items ship independently and immediately.** Neither depends on Program 1. The full,
name-covering fix (NER-based) remains a separate, larger, future project, unchanged from the
original audit's own framing.

### Epic E — GDPR, Data Lifecycle & Subprocessor Disclosure (rewritten — SEC-051 added, delete path added)
| Finding | Action |
|---|---|
| SEC-052 | Fix 2 wrong sort-column names in data export; add fail-loud behavior |
| SEC-053 | Extend account deletion to phone/SMS/Viber profile |
| SEC-072 (corrected) | Run the **live orphan-row check** the audit actually calls for (`:641` — a check, not a purge-policy implementation, corrected in Revision 3 from Revision 2's misquote); its result gates Epic C's FK retype, not a full purge-policy build |
| SEC-065 | Enforce recorded legal-basis field before AI processing |
| SEC-064 | Assert data residency in code; stop silent Azure-OpenAI fallback |
| SEC-055 | Wire `data_classification.py` into the AI chokepoint, or delete it + correct the Architecture Bible — genuine judgment call, left open, best made once Epic D's interim PII fix is live |
| **SEC-051** *(moved from Epic D)* | Documentation deliverable: update `privacy.html` + `static/dpa.html` Annex B for all 6 recipients (Cohere, Twilio, Meta/WhatsApp, Viber, SMTP provider, Sentry). Separate, optional engineering item: disable Cohere reranking (Trivial — clean fallback to the internal GPT reranker already exists) |
| **Matter/document delete path** *(new — was silently missing from every epic in Revision 1)* | A real delete path for `predmeti`/`predmet_dokumenti` and their Pinecone vectors — named explicitly in §15's "minimum set to unlock medium firms," which this plan cannot honestly claim to deliver without it |
| **SEC-045** *(new — was confused with SEC-045-admin and dropped)* | Malware/AV scanning on upload buckets, prioritizing the unauthenticated `client-portal` path |

### Epic F — Data-at-Rest Encryption (re-sequenced and SEC-057 correctly scoped)
| Finding | Action | Sequencing |
|---|---|---|
| SEC-056 | Encrypt client-portal uploads | **Ungated — ships immediately.** Adds a 4th path to an already-encrypted corpus under the *same* key; no new key-rotation blast radius, so gating it behind SEC-024 was unjustified |
| SEC-057 (design) | Decide the read-path strategy for encrypting `predmet_dokumenti.tekst_sadrzaj`. **Corrected reader/writer list (Revision 3)** — Revision 2's list mislabeled 2 write sites as reads and missed a write site and a reader: **readers** — `case_dna.py` (×5), `evidence.py`, `evidence_graph.py` (×2), `multi_agent.py`, `case_commander.py`, `zakon_monitoring.py`, `api.py:4828-4843`, `scripts/genome_bootstrap_sample.py:77`; **writers** (need encrypt-on-write, not decrypt-on-read) — `drafting.py:307`, `smart_intake.py:578`, `api.py:4299`. **Not** a search-index redesign — `routers/search.py` reads a different table/column (`uploaded_documents.extracted_text`) entirely | Runs in **parallel** with SEC-024, no dependency |
| SEC-024 | Implement key rotation (design already exists, `KEY_ROTATION_ANALYSIS.md`) | Runs in parallel with SEC-057's design phase |
| SEC-057 (backfill) | Execute the bulk re-encryption of existing document text | **Gated on SEC-024 landing** — this is where the original blast-radius argument genuinely applies |
| SEC-032 | `fakture.klijent_pib` plaintext vs. `klijenti.pib_encrypted` — bundle into this epic's design pass rather than a separate future PII-field-registry project, since the same encrypt-on-write/decrypt-on-read pattern is being built here anyway | After SEC-057's design decision |

### Epic G — Application Hardening (dependencies made explicit, complexity corrected, 4 items added)
| Finding | Note |
|---|---|
| SEC-042, SEC-043, SEC-046, SEC-060, SEC-061, SEC-062, SEC-067, SEC-068, SEC-070, SEC-071, SEC-073, SEC-026, SEC-045-admin | Independently schedulable, Low/Trivial, no correction needed |
| SEC-050 (exception-leak half only — see Epic H for the audit-coverage half) | Independently schedulable |
| **SEC-069-comparison** | **Depends on Epic B shipping first** — per the Gap Register's own text, this finding's practical risk is contingent on rate limiting actually being enforced |
| **SEC-014** | **Depends on Epic H's SEC-050 (audit-coverage half) and the SEC-036 residual (below) shipping first** — corrected in Revision 3: the audit's own citation (`:602`) is the audit-coverage finding, not Epic G's exception-leak item as Revision 2 stated; the audit states the combination is materially higher-risk than any one alone; fixing CSP in isolation doesn't address that |
| **SEC-069-search** | Independently schedulable, unchanged |
| **SEC-036 residual** *(new)* | Sanitizer (`security/html_sanitize.py`) still absent from `routers/zadaci.py`, `kancelarija.py`, `firm_memory.py`, `learning.py`, `evidence.py`, `knowledge_base.py` — must ship alongside SEC-014, not independently |
| **SEC-044** *(new)* | 2FA publicly claimed, not implemented — same class as SEC-063, batch together |
| **SEC-047** *(new)* | No global request body size cap — interacts with SEC-071 and SEC-011; schedule alongside Epic B for a single combined verification pass, even though it doesn't strictly block either |
| **SEC-066** *(new)* | `python-jose` accepted CVE — evaluate PyJWT migration, independently schedulable |

### Epic H — Structural / Process Fixes (new — root-cause items that close a recurring pattern, not one instance of it)
| Item | Why this is structural, not a one-off |
|---|---|
| **SEC-050 (audit-coverage half)** | `_AUDIT_PATHS` covers ~4 prefixes of ~596 routes. Connects directly to **Program 4 (Complete Forensic Traceability)** in the Traceability doc — this should be scoped as accelerating Program 4, the same reasoning Epic C/D apply to Programs 3/1, corrected from Revision 1's failure to make this same connection here |
| **`AUDITABLE_ACTIONS` CI check** | A mechanical check that every `log_action(...)` call site's literal action string exists in the hardcoded allow-list. This is the audit's own explicit ask: *"worth naming as a recurring pattern requiring a structural fix... not just a fourth one-off catch"* — three prior instances (SEC-034, SEC-005, the `/api/cron/daily` collision) already occurred |
| **Duplicated `_verify_token`** | `api.py` and `shared/deps.py` each carry an independent copy, with different JWKS-fallback and logging behavior — flagged by the audit as worth architectural attention beyond any single fix (this is also what made Epic A's SEC-058 fix need to touch two files, per H-4) |
| **Supabase Auth config export** | The audit's own recommendation for AUTH-1 (an entire domain — login, password policy, MFA settings — this repo cannot verify): export the live config into a version-controlled snapshot and assert it in CI, mirroring the existing `scripts/export_rls_policies.py` pattern |
| **Route-shadowing / decoration-parity check** *(Revision 5, enumeration method corrected Revision 6 per the terminal Red Team pass)* | slowapi's `_find_route_handler` resolves last-full-match while Starlette's router serves first-full-match, so any two routes that both fully match a request can silently disagree about which one's rate-limit decoration applies. **6** such pairs exist today (corrected from 5 — a per-route-template probe misses pairs whose parameters sit at different segment positions, e.g. `strategy_simulator.py:471`/`:502`; only found by an exhaustive pairwise check). The check this row commits to building must, specifically: (1) enumerate over **witness paths derived from route pairs**, not from probing each route's own template in isolation — the pairwise method is what finds cross-position matches the per-template method structurally cannot; (2) handle path-converter catch-alls (`{x:path}`) as a separate case, since they match at a different segment count than the pairwise method's equal-depth comparison covers (none exist in the repo today, but the check must not silently assume none ever will); (3) compare **first**-full-match against **last**-full-match specifically, not "a literal route vs. its parameterized sibling" — the correct invariant, confirmed complete against slowapi's actual `_should_exempt` logic (exactly 3 True-branches: `handler is None`, `_exempt_routes`, `_route_limits` — no fourth path in); (4) read the decorated/exempt oracle from `app.state.limiter._route_limits` and `._exempt_routes` **only** — not `_dynamic_route_limits`, which holds callable (non-static) limit values and uses a separate code path the middleware's exemption check never consults |

---

## Full Reconciliation Table

Every finding named anywhere in `docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md` (its
Gap Register table plus its narrative sections), mapped to exactly one epic or explicitly marked
deferred. This table's absence in Revision 1 is what let two findings vanish silently — it is not
optional structure for Revision 2.

| Finding | Epic | Finding | Epic |
|---|---|---|---|
| SEC-004 | C (tracked, not closed) | SEC-044 | G |
| SEC-006 | D | SEC-045 | E |
| SEC-010 | B | SEC-045-admin | G |
| SEC-011 | B | SEC-046 | G |
| SEC-014 | G | SEC-047 | G |
| SEC-024 | F | SEC-048 | B |
| SEC-026 | G | SEC-050 (exceptions) | G |
| SEC-032 | F | SEC-050 (audit-coverage) | H |
| SEC-033 | C | SEC-051 | E |
| SEC-036 (residual) | G | SEC-052 | E |
| SEC-037 | A | SEC-053 | E |
| SEC-038 | A | SEC-054 | D |
| SEC-039 | C | SEC-055 | E |
| SEC-040 | C | SEC-056 | F |
| SEC-041 | C | SEC-057 | F |
| SEC-042 | G | SEC-058 | A |
| SEC-043 | G | SEC-059 | C |
| SEC-060 | G | SEC-067 | G |
| SEC-061 | G | SEC-068 | G |
| SEC-062 | G | SEC-069-comparison | G |
| SEC-063 | G | SEC-069-search | G |
| SEC-064 | E | SEC-070 | G |
| SEC-065 | E | SEC-071 | G |
| SEC-066 | G | SEC-072 | E |
| — | | SEC-073 | G |
| Matter/document delete path | E (new) | `AUDITABLE_ACTIONS` CI check | H (new) |
| Duplicated `_verify_token` | H (new) | Supabase Auth config export | H (new) |

**Deliberately deferred, not in any epic, with reasons stated (not silently dropped):** none as of
this revision — every item found in the source audit's Gap Register and narrative sections is
above. If a future item is deliberately excluded, it must be listed here with its reason, per this
table's own purpose.

---

## Root-Cause Clustering Analysis (founder-requested: "koji root cause problemi rešavaju više SEC nalaza odjednom")

This section groups findings by the underlying mechanism that produced them, not by which epic
schedules them. The point of doing this separately from the epic table above: an epic can ship a
patch to every symptom in a cluster without anyone noticing the cluster shares one cause — which is
exactly how a fifth instance of the same bug class would get "fixed" as if it were novel, again.
Where a cluster's structural fix is already captured by an epic above, that's noted; where it isn't,
that's a gap in this plan, not a gap this section merely observes and drops.

1. **"Two places that should be one source of truth have silently diverged."** This is the audit's
   own executive-summary diagnosis, restated at the mechanism level. Concrete instances: the
   `AUDITABLE_ACTIONS` hardcoded allow-list vs. actual `log_action()` call sites (the recurring
   pattern behind SEC-034/SEC-005/the `/api/cron/daily` collision); `_AUDIT_PATHS`' ~4-prefix
   coverage vs. ~596 actual routes (SEC-050's audit-coverage half); two independent `Limiter`
   instances with no shared counters (M-2); two independently-maintained copies of `_verify_token`
   (M-3, and why Epic A's SEC-058 fix had to touch two files instead of one). **Already captured**:
   this is precisely why Epic H exists as a named cluster rather than four unrelated line items —
   Epic H's four items are one root cause, not four.
2. **"Session- or event-based resources were never given a first-class owner column."** SEC-039
   (Pinecone document session scoped by `session_id`, no owning table), SEC-040 (`extracted_entities`
   needs a 3-table join to find its owner because it was never given one directly). Both are
   Smart Intake / document-session features built around an ephemeral flow, where "who owns this"
   was answered implicitly by "whoever holds the session token" rather than a column. **Already
   captured** in Epic C, but worth naming: if a *third* new ephemeral-session feature ships before
   this pattern is corrected at the design-review level (not just patched twice), it will very
   likely repeat this exact gap a third time. This is an argument for the Solution Architect role
   treating "does this new resource have a first-class `user_id`/`predmet_id` owner column, set at
   creation, not derived" as a standing design-review question — recommended addition to
   `templates/TECHNICAL_DESIGN.md`, not something this remediation plan itself can fix in code.
3. **"Encryption was added to the newest module and never retrofitted to older or adjacent paths."**
   SEC-056 (client-portal uploads, the older upload path, unencrypted while Smart Intake's newer
   path is), SEC-057 (`predmet_dokumenti.tekst_sadrzaj` itself unencrypted at rest, read in 13+
   places), SEC-032 (`fakture.klijent_pib` plaintext vs. `klijenti.pib_encrypted`'s correct pattern
   right next to it). **Already captured** — this is why Epic F now explicitly bundles SEC-032 into
   the same design pass instead of leaving it as a separate future project: the pattern (a correct
   encrypt-on-write/decrypt-on-read mechanism exists, applied to one field/path but not its
   siblings) is the same across all three, so one design decision should close all three, not three
   separate ones.
4. **"Rate/cost controls are an opt-in decorator, not a default-deny gate."** SEC-010 (undecorated
   AI-cost routes), SEC-011/SEC-048 (the middleware side of the same gap), SEC-047 (no global body
   size cap — the same "must remember to add this per-route" shape), SEC-069-comparison (only
   risky once rate limiting is confirmed absent). **Partially captured** — Epic B and Epic G note
   the dependency between these, but the plan does not currently propose flipping the *mechanism*
   from opt-in-per-route to default-deny-with-opt-out, which is the actual structural fix implied
   by naming this a cluster. Recording this explicitly as a gap: Epic B's scope as written closes
   the specific instances found, not the mechanism that will produce the next one.
5. **"A correct redaction/classification mechanism exists but is wired into some content-processing
   paths and not others."** SEC-006 (`_skini_pii` covers 4 call sites, not the Genome path),
   SEC-055 (`data_classification.py` built, never wired into the AI chokepoint). **Already captured**
   in Epic D (interim fix now) and Epic E (SEC-055's wire-in-or-delete decision) — and this cluster
   is precisely what Program 1's chokepoint pattern (`shared/ai_client.py::_patch_prompt_guard`)
   is the long-term structural answer to: once Program 1 ships, this class of "forgot one call site"
   finding should stop recurring for anything routed through the chokepoint, the same way SEC-003's
   prompt-injection coverage already benefits from it today.
6. **"External vendors receive data with no central registry of what/why/legal-basis."** SEC-051
   (6 undisclosed recipients), SEC-064 (residency/fallback), SEC-065 (legal basis not enforced
   before AI processing). **Already captured** in Epic E, but distinct in kind from clusters 1-5:
   this one is a governance/documentation gap, not a code-pattern gap — no single code fix closes
   it, only a maintained registry (the DPA Annex B update) plus enforcement checks at the few
   points data actually leaves the system.

**Bottom line for the founder:** clusters 1, 3, 5, and 6 are structurally addressed by this plan's
epics (mostly Epic H, F, D/E respectively). Cluster 2 is addressed for its two known instances but
not at the design-review-process level — a template change, not a code change, is the durable fix,
and is recommended above rather than assumed. Cluster 4 is the one genuine gap this analysis
surfaces that the epic table does not yet close at the mechanism level — Epic B closes the known
instances, not the opt-in-decorator pattern that will produce the next one. This is noted as an
open item for the Solution Architect to weigh, not silently resolved by this document.

## Answer to "if only one epic can start right now" (was missing in Revision 1)

**Approve Epic D's SEC-054 fix specifically** (not the whole epic, not Epic D's SEC-006 item) if
engineering bandwidth allows exactly one thing: it is Low complexity, has no dependencies, and per
the audit's own §15, is the single item that changes the enterprise-readiness verdict for every
customer segment above solo/small-practice — the "ethical wall" gap is independently disqualifying
for medium, large, court, and regulated-enterprise deployment. Epic A's items are separately
recommended regardless of this decision, since two of its three items consume founder time, not
engineering bandwidth, and the third is a 2-line diff.

## Alternatives Considered (Revision 2 additions)

- **Keep Epic C tied to Program 3, softening only the SEC-004 claim.** Rejected — the Red Team's
  evidence (session_id has no owner table, entity_id needs a different join shape, SEC-059 is an
  insert not an authz check) means the *mechanism* itself doesn't transfer, not just the framing;
  decoupling is the only defensible fix.
- **Leave SEC-057 gated behind SEC-024 in full (design + backfill).** Rejected for the design phase
  specifically — the blast-radius argument only applies to bulk re-encryption of existing data, not
  to deciding the read-path architecture, which has zero dependency on which key protects the
  eventual ciphertext.

## Open Questions — status after the second Red Team pass

1. Epic H's grouping: **not challenged** by the second pass — left as-is.
2. SEC-072→FK dependency direction: **resolved** — the second pass caught that Revision 2 had
   misquoted the audit (claimed a purge-policy requirement where the audit only calls for a check);
   corrected in Revision 3 above to gate on the check, not a full purge implementation.
3. Reconciliation table completeness: **confirmed** — the second pass independently re-verified all
   44 Gap Register IDs are mapped and found none dropped.

## Status after the fourth Red Team pass (strict 2-question falsification, Epic B only)

The founder's 4th-pass instruction named an explicit closing condition and framed it as the last
targeted check on this item. It returned BLOCKING on both named questions, with fully reproduced,
concrete evidence (not speculative) — the exemption *list* was confirmed complete, but the
exemption *mechanism* had a route-shadowing gap; the `600/hour` default's citation was inverted and
its denominator didn't match. Both are fixed in Revision 5 above.

**Per the founder's own standing rule** (CLOSED findings lock; a 5th pass is not launched
automatically just because a document changed again) **and** the explicit "this was meant to be the
last pass" framing, this revision is being presented to the founder directly rather than triggering
another automatic Red Team cycle. Open question for the founder, not for another agent: is Revision
5's fix sufficient to proceed to Phase 4 (Security Gate) for the rest of the plan with Epic B
included, or is one further, even-narrower check warranted given this specific item's history (4
consecutive real BLOCKING findings)? Either way, per the locked-findings rule, anything the 4th
pass's report explicitly confirmed CLOSED (the exemption list's completeness; the collapse
mechanism itself) does not need re-verification — only the two corrected fixes above are actually
new since that pass ran.
