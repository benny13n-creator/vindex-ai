# Forensic Audit Remediation & Enterprise Security Readiness

**Started:** 2026-08-02
**Current phase:** 2 (Architecture Review), Revision 2 — returning to 3 (Mandatory Opposition, targeted re-check)
**Status:** ACTIVE

## Mission (Phase 0 — Founder Request, verbatim)
"Remedijacija FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md i priprema Vindex-a za enterprise
security nivo." Explicit constraint: **do not modify production code yet.** Run the full
governance workflow; produce the remediation execution plan.

## Phase log
- Phase 0 (Founder Request): received 2026-08-02, first real activation of this organization.
- Phase 1 (Product Discovery): done — folded into the Architecture Decision artifact below (for a
  remediation mission, product-discovery and architecture-review questions overlap enough to
  combine into one document rather than force an artificial split).
- Phase 2 (Architecture Review), Revision 1: done — see `decisions/2026-08-02_forensic-remediation_ARCHITECTURE_DECISION.md`.
- Phase 3 (Mandatory Opposition), pass 1: fresh Red Team agent spawned against Revision 1.
  **VERDICT: BLOCKING** (4 Critical, 5 High, 3 Medium, 1 Low). Per this organization's own
  branching rule (`ORG_CHART.md` rule 2; founder's explicit instruction), this returns the mission
  to Phase 2 — implementation does not start on a plan that "looks good."
- Phase 2 (Architecture Review), **Revision 2: done** — same document, rewritten. All 4 Critical +
  5 High + 3 Medium findings addressed; Epic C decoupled from Program 3 and SEC-004 honestly
  restated as not closed; SEC-051 moved to Epic E and rescoped as a documentation deliverable;
  SEC-006 given an immediate interim fix instead of a deferral; matter/document delete path and
  SEC-045 restored (were silently missing from every epic in Revision 1); SEC-050 split; Epic F
  re-sequenced (SEC-056 ungated, SEC-057 rescoped from a false "search redesign" premise to a
  13+-site decrypt-on-read migration); Epic G dependencies made explicit; new Epic H added for
  structural/process fixes (audit-coverage gap, `AUDITABLE_ACTIONS` CI check, duplicated
  `_verify_token`, Supabase Auth config export); full SEC-ID reconciliation table added; explicit
  single-epic-under-bandwidth-constraint answer added (Epic D's SEC-054).
- Phase 3 (Mandatory Opposition), pass 2: done. Fresh Red Team agent, targeted re-check of
  Revision 2. **VERDICT: BLOCKING — 1 High remaining, 3 Medium/Low residue.** Confirmed FULLY
  CLOSED: all 4 Criticals, 3 of 5 Highs, 2 of 3 Mediums from pass 1. Still open (HIGH): Epic B's
  own root-cause claim was itself factually wrong (Revision 2 said the two `Limiter` instances have
  "no shared counters" — `shared/rate.py`'s docstring says they do share a Redis keyspace; the
  real defect is `SlowAPIMiddleware`'s exemption check only seeing `api.py`'s 29 routes, not the
  other 415 registered against a different `Limiter` object) — Revision 2's prescribed fix
  ("verify/reconcile which instance") would have shipped a regression, hard-capping 415 routes to
  60/hour. Report: `decisions/RED_TEAM_REPORT_2026-08-02_revision2.md`.
- Phase 2 (Architecture Review), **Revision 3: done** — Epic B rewritten with the corrected root
  cause and fix (collapse to a single `Limiter` instance, not a verification step); SEC-057's
  reader/writer site list corrected (2 mislabeled writes, 1 missing write, 1 missing reader);
  SEC-014's dependency corrected to Epic H's SEC-050 item, not Epic G's; SEC-072's dependency
  corrected from a misquoted "purge policy" requirement to the audit's actual "live orphan-row
  check." Reconciliation table re-verified complete, no changes needed.
- Phase 3 (Mandatory Opposition), pass 3: done. Fresh Red Team agent, falsification-only, scoped
  strictly to Epic B. **VERDICT: BLOCKING — 1 High, 1 Medium, 3 Low/Info.** The collapse mechanism
  itself was attacked 7 independent ways (circular import, hidden separation rationale, ordering,
  hidden `app.state.limiter` dependents, route-shadowing quirk, `BaseHTTPMiddleware`/SSE risk, the
  brief's own "simpler alternative") and held on all 7 — confirmed sound, not assumed. What still
  blocked: registering the middleware post-collapse inherits an unscoped `60/hour` default that
  lands on the 153 undecorated routes, including `/health` (Railway's healthcheck path — restart-
  loop risk), `/api/sesija/ping` (a 60-second heartbeat, already at the limit boundary for one
  user), and all 20 `klijenti/` CRM routes (confirmed undecorated, correcting Revision 3's
  wording). Medium: `key_style="url"` leaves 36 parameterized undecorated routes enumerable even
  after the fix. Report: `decisions/RED_TEAM_REPORT_2026-08-02_revision3_epicB.md`.
- Phase 2 (Architecture Review), **Revision 4: done** — Epic B rewritten again: explicit,
  separately-sized app-wide default (decoupled from the Redis-outage fallback constant); explicit
  exemption list (`/health`, `/api/sesija/ping`, app-shell routes, `/viber/webhook`); `key_style`
  left at `"url"` deliberately (switching to `"endpoint"` would silently re-bucket all 444
  already-tuned per-route limits) with the resulting enumeration gap on 36 parameterized routes
  folded into SEC-010's scope instead; SEC-010's own cost corrected (120 of 153 undecorated routes
  need a signature change, not just a decorator line, since slowapi requires a `request`/
  `websocket` parameter).
- **Escalation checkpoint:** status reported to founder after 3 consecutive BLOCKING verdicts.
  **Founder direction received:** run exactly one more pass — strictly a falsification-only pass,
  not a fourth general review — scoped to exactly 2 named questions (exemption-list bypass path;
  whether 600/hour has a stated threat/workload rationale). Explicit closing condition given: if
  no concrete bypass/harm scenario is found, mark CLOSED, no further passes. Founder also
  instituted a new standing organizational rule (added to `ESCALATION_RULES.md`): CLOSED findings
  are locked and only reopen on a code/architecture change, never re-litigated by a later pass
  "just to check again" — this is now the canonical rule for all future Red Team cycles, not just
  this mission.
- Phase 3 (Mandatory Opposition), pass 4: done. Fresh Red Team agent, strict 2-question
  falsification (loaded the live FastAPI app in-process rather than trusting prior counts).
  **VERDICT: BLOCKING — both questions.** Q1 (exemption bypass): the exemption *list* was
  confirmed complete (swept all 156 undecorated routes, nothing missing), but the exemption
  *mechanism* has a reproducible gap — slowapi resolves route-shadowing pairs last-match while
  Starlette serves first-match, and decorating `/klijenti/{klijent_id}` (Epic B's own SEC-010 item)
  would silently un-limit `/klijenti/retention-check` entirely. 5 shadowed pairs exist app-wide; 4
  are benign only because both sides are currently decorated. Q2 (`600/hour` rationale): the cited
  line (`api.py:924-925`) says the opposite of what it was cited for — describes a per-`user_id`
  backstop deliberately laxer than the IP limit, not a template for the IP limit's value; applied
  flat and per-path, `600/hour` is ~109× too loose in aggregate and too tight for the plan's own
  NAT scenario on `/klijenti` search specifically (no per-user backstop, shared bucket, ~7-lawyer
  office exhausts it on ordinary typing). Report:
  `decisions/RED_TEAM_REPORT_2026-08-02_revision4_epicB_falsification.md`.
- Phase 2 (Architecture Review), **Revision 5: done** — Epic B rewritten a third time: (b) decorate
  the losing side of all 5 shadowed route pairs, plus a structural shadow-pair/decoration-parity
  check added to Epic H; (c) replaced the flat `600/hour` default with a 3-tier shape —
  unauthenticated state-mutating routes (e.g. `/api/security/csp-report`) get their own low
  individually-justified limit, high-frequency authenticated UI routes with no backstop (e.g.
  `/klijenti` search) get their own workload-derived limit, and the genuinely-unassessed remainder
  gets a conservative low default framed honestly as default-deny friction, not a calibrated
  number.
- **Escalation checkpoint (per the founder's own explicit framing that pass 4 was meant to be the
  last targeted check on this item):** Revision 5 is **not** being sent to a 5th automatic Red Team
  pass. It is presented directly to the founder: either proceed to Phase 4 (Security Gate) for the
  whole plan with Epic B included as now written, or the founder requests one further, even
  narrower check specifically given this item's unusual history (4 consecutive real BLOCKING
  findings, each one substantive, not manufactured). Per the CLOSED-findings-lock rule, the 4th
  pass's confirmations (exemption list completeness, collapse mechanism soundness) do not need
  re-verification regardless of which path is chosen.
- **Founder direction received:** run exactly one more pass — a terminal, 3-test falsification pass
  against Revision 5, since Revision 5 changed two fundamental things (the bypass-prevention model,
  not just its instances; the limit-sizing model, not just its numbers), so this is genuinely a new
  design being checked, not the same artifact re-litigated. Founder's explicit 3 tests: (1) Route
  Shadowing — not just the 5 known pairs, but whether the *mechanism* (route additions, registration
  order changes, `include_router` changes) can silently defeat rate limiting in the future, i.e. is
  Epic H's proposed structural check actually specified precisely enough to be enforceable; (2)
  Limit Model — for each of the 3 tiers, does the plan state a real principle (`limit = workload
  model + security objective`, with a named attack prevented and a named legitimate workload
  supported), or does any tier still reduce to "a felt number"; (3) Enterprise scenario — simulate a
  50-lawyer firm, one NAT egress, 5000 matters, concurrent searches: does the limiting protect the
  system without breaking normal work at that scale. **Explicit terminal closing rule, given by the
  founder**: if Revision 5 survives this pass, **Epic B is CLOSED** for this mission — proceeds to
  Phase 4 (Security Gate) with the rest of the plan, and does not return to Red Team again unless a
  future *implementation* deviates from this approved specification (a Phase 6/7 QA-track concern
  from that point on, not an architecture-track one).
- Phase 3 (Mandatory Opposition), pass 5 (terminal): done. **VERDICT: BLOCKING on all 3 named
  tests.** Test 1 (route-shadowing mechanism): the parity invariant itself is complete (4 more
  falsification attempts failed), but the *enumeration method* Revision 5 used has a proven false
  negative — found a **6th** shadowed pair (`strategy_simulator.py:471`/`:502`) invisible to
  per-route-template probing, plus a concrete future-scenario reproduction that defeats a literal
  implementation of Epic H's prior wording with CI staying green. Test 2 (limit model): graded all
  3 tiers against `limit = workload + objective` — **0 of 3 complete** (each stated at most one of
  the two halves, no tier had a derived number). Test 3 (enterprise scale): 2 findings — (a)
  `/api/sesija/ping` (60s heartbeat, 3,000-6,000/h from one office IP at 50 lawyers) was
  mis-sorted into tier (iii) by a dimensionally-wrong criterion (checked for a per-user backstop
  against a per-IP aggregation threat); (b) `key_style="url"` bucketing means decorating a
  parameterized route gives **zero** aggregate scrape protection (30 distinct IDs → 0×429),
  falsifying Revision 5's claim that SEC-010 closed the enumeration gap. The pass also caught,
  unprompted, that Revision 5's table relettering had silently dropped the explicit exemption list
  down to an indirect reference — a real documentation regression, not yet an exploited one.
  Report: `decisions/RED_TEAM_REPORT_2026-08-02_revision5_epicB_terminal.md`.
- Phase 2 (Architecture Review), **Revision 6: done** — all 3 terminal-test findings plus the
  exemption-list regression fixed: exemption list restored explicitly (now also including
  `/api/sesija/ping` and 5 once-per-boot routes, moved out of tier (iii) since a per-user backstop
  doesn't mitigate per-IP NAT aggregation); shadow-pair count corrected to 6, Epic H's check
  rewritten to specify the enumeration method itself (pairwise witnesses, not per-template probes;
  catch-all handling; correct oracle registries); each of the 3 default tiers now states a named
  attack, a named workload, and a derived number (tier ii additionally uses a confirmed-working
  per-`user_id` `key_func` override instead of IP-keying); `application_limits` added as tier
  (iii)'s aggregate backstop; a `scope=` override requirement added for scrape-target parameterized
  routes, since decoration alone under `key_style="url"` doesn't provide aggregate protection.
- **Escalation checkpoint:** this is the 5th consecutive Red Team pass to find something real on
  this one epic, and the pass explicitly designed to be terminal did not close it. Status reported
  to the founder for direction.
- **Founder direction received: a tactical pivot, not another patch pass.** The founder's diagnosis:
  the 5 findings weren't independent bugs, they were symptoms of the same missing thing — no formal
  methodology for defining a route's security posture, meaning a 6th, never-examined route could
  reproduce the same class of defect regardless of how well Epic B's specific fixes hold up.
  Direction: (1) lock a formal Route Security Model first (classification / threat model / identity
  dimension / limit-derivation taxonomy) — not another implementation review; (2) materialize it as
  a Route Security Registry artifact, not just decorator arguments, with a CI check that every live
  route has a real entry; (3) only then, one final Red Team pass — testing whether the *model* can
  be broken, not whether this patch is good.
- **Done:** `docs/architecture/ROUTE_SECURITY_MODEL.md` written — the full taxonomy (§1-5), the
  registry schema plus worked entries for every route this mission has actually analyzed with
  evidence (§6.2 — all 6 shadow-pair routes, the full exemption list, the 3 worked tier examples),
  explicit scoping of full ~600-route population as a scripted implementation-phase task rather
  than hand-invented here (§6.3), and the 5 named tests (A-E) the final Red Team pass must run
  against the model itself (§7). Epic B's table in the decision document is retained as the
  historical record; the model document is now the operative specification (Revision 7 note added).
- Phase 3 (Mandatory Opposition), final pass (model-level): done. Fresh Red Team agent, all 5 named
  tests. **VERDICT: BLOCKING on all 5** — a genuine 6th consecutive real finding, this time on the
  model itself: (A) the natural implementation of `composite` (a single concatenated key) was a
  proven no-op — 0×429 across 30 requests from 1 IP spanning 10 user_ids; stacked decorators
  confirmed as the correct mechanism, but the document never named it; (B) a live WebSocket route
  (`/api/voice/realtime/ws`) fit none of the 5 classifications and cannot be rate-limited by slowapi
  at all; (C) a fully content-free registry entry passed every stated field requirement using
  boilerplate copied verbatim from the document's own pilot entries; (D) §6.4 (the CI enforcement
  section) was referenced 4 times but never actually written; (E) applying the model to Epic B's own
  5 real findings would have caught only 2 of 5 (`/health` exemption, `/sesija/ping` dimension
  error) — not the `key_style="url"` scrape no-op the model was written in direct response to.
  Report: `decisions/RED_TEAM_REPORT_2026-08-02_route_security_model.md`.
- **Done:** `docs/architecture/ROUTE_SECURITY_MODEL.md` corrected against all 5 findings —
  `composite` now specified as stacked decorators (never concatenation), `limiter` changed to a list
  to represent it; added a 6th classification (`non-http-stream`) plus a `concurrency` field and a
  `"WS <path>"` registry key form; compound tags made conditional-mandatory, not merely permitted;
  §5 given content predicates (numeral-in-workload, formula-references-workload, arithmetic
  consistency, a placeholder denylist) so presence-only checks can't be gamed; §6.4 written in full
  (previously missing) with a precisely-specified shadow-pair enumeration algorithm (pairwise
  witnesses, not per-template probing) plus a `shadow_pair_with` schema field replacing the
  unschema'd `note:`; §6.3's auto-classifier now treats in-body role/founder gates as classification
  signals, not just `Depends`; an explicit scope boundary added stating the registry cannot and does
  not verify which `Limiter` instance enforces a route (Epic B finding #1) — a separate, one-time
  whole-application wiring check, not a per-route registry concern. §7 rewritten as a narrower,
  falsification-only re-check per finding, consistent with the CLOSED-findings-lock discipline.
- **Founder direction received:** run the narrow falsification-only pass, with a specific reframing:
  not "is the model good" but "assume it's wrong; find a minimal realistic scenario where following
  this spec exactly still produces a false sense of protection." 5 tests specified, matching but
  sharpening §7's own re-check list: (1) composite key correctness — multiple users/one IP, same/
  different tenants, one attacker vs. one victim, and specifically whether the `user_id`+`tenant_id`
  composite case (which §3 allows but the document only worked out `ip`+`user_id` for) generalizes
  correctly; (2) route completeness against 5 hypothetical NEW route shapes (GET, mutating POST,
  WebSocket, SSE/streaming — distinct from WebSocket — and internal-service/cron), asking whether
  the model's own machinery forces real classification of each; (3) CI bypass with 5 concrete gaming
  attempts; (4) Epic B self-test — do the corrected model's own rules force detection of all 5
  original historical findings, with explicit judgment on whether finding #1's out-of-scope framing
  is legitimate or a convenient excuse; (5) scope-boundary clarity between registry/wiring/
  middleware/framework. Founder's explicit closing rule: if this passes, Epic B closes — not because
  the model is perfect, but because it now has a threat model, enforcement model, CI control,
  runtime limitations, and known boundaries. If it finds something new, founder's own framing: this
  stops being an Epic B problem and becomes a separate "Security Governance Framework" epic, since
  the pattern would then be broader than rate limiting specifically.
- Phase 3 (Mandatory Opposition), narrow falsification pass: done. **VERDICT: BLOCKING on all 5
  tests — 7th consecutive real Red Team finding this mission.** What survived (genuinely closed,
  not just asserted): stacked-decorator `composite` for `ip`+`user_id` (measured correctly enforced
  on both bounds); the §6.4 pairwise-witness shadow-pair algorithm (found all 4 known pairs
  non-circularly); Epic B findings #2 (`/health`) and #4 (`ping` dimension) are genuinely forced
  into the open by the corrected model. What did not survive: (1) `user_id`+`tenant_id` composite —
  permitted by the schema, a proven no-op against the exact threat composite exists to stop, since
  both dimensions are attacker-mintable in this codebase (self-registration + self-service tenant
  creation); (2) SSE/streaming-HTTP routes have no correct classification — the model's own
  `non-http-stream` definition is factually wrong for this shape (slowapi *can* rate-limit SSE; the
  real gap is concurrency, which the schema then forbids for anything not `non-http-stream`) — live
  route affected: `POST /api/pitanje/stream`; (3) three CI bypasses, most seriously that the content
  predicate is a lower bound only ("raise the number until it stops mattering" passes); (4) Epic B
  finding #5 (the `key_style="url"` scrape no-op) is **not closed** — `scope: fixed` isn't even a
  real slowapi parameter (`Limiter.limit()` has no `scope` arg; only `shared_limit()` does, which
  the model never names), so the registry now *affirmatively documents* protection for a route
  measured at 0×429 across 30 distinct IDs; (5) the two-`Limiter`-instance state (93 modules / 415
  decorations invisible to `app.state.limiter`) is currently making the model's own CI oracle
  (checks 6/7) read the wrong object and return false-green, and the "alongside, not inside §6.4"
  sequencing for fixing this was proven insufficient — it must be a hard gate that precedes every
  other check. Report:
  `decisions/RED_TEAM_REPORT_2026-08-02_route_security_model_falsification2.md`.
- **Founder's own pre-committed branching rule applies:** a finding at this stage means the theme is
  broader than rate limiting — open a separate Security Governance Framework epic rather than
  another Epic B patch. The falsification pass's own explicit framing judgment agreed independently:
  every one of its 5 findings shares one generator ("a declared control with no executable runtime
  witness"), which is not rate-limiting-specific and — per the pass's own text — "applies identically
  to RLS policies, auth dependencies, and PII redaction."
- **Done:** opened `.vindex_ai_team/decisions/2026-08-02_security-governance-framework_SCOPE.md` — a
  charter (not yet a full design) recording why this is its own epic, the one non-optional
  prerequisite (collapse the two `Limiter` instances into a hard CI gate that precedes all other
  checks — currently sequenced as merely "alongside," proven insufficient), the core deliverable
  (generalize check 7's declaration→runtime-witness pattern to `scope`, `identity_dimension`'s
  fallback, and `concurrency`), and Epic B's revised disposition: steps (i) collapse + gate and (ii)
  generalize the witness pattern belong to the new epic; step (iii), populating the registry across
  the remaining ~590 routes, remains Epic B's scope but is now gated on (i)/(ii).
- **Founder direction received, final for this checkpoint:** stop tuning Epic B — accept that Red
  Team did its job; the finding is now recognized as a systemic Vindex pattern ("deklarisana kontrola
  ≠ izvršna kontrola"), more important than the rate-limit specifics that surfaced it. Explicit
  reclassification: **Epic B → 🟡 HOLD** (not failed — superseded by a more important finding).
  **Security Governance Framework → 🔴 ACTIVE BLOCKER.**
  - **Design depth answered:** design the unifying **principle** now (a 3-layer Intent → Policy →
    Runtime Witness model, generalizing §6.4 check 7 — the one control in the whole Route Security
    Model that actually binds a declaration to real enforcement), but do **not** build 5 separate
    frameworks (RLS/auth/PII/encryption/AI-provider) now — each is a future, separately-scoped
    application of this one principle, one domain at a time.
  - **Organizational change:** added a 15th role, **Security Verification Engineer**
    (`agents/15_security_verification_engineer.md`), distinct from Security & Privacy Architect —
    the Architect states what a control should be; this role asks "show me the code that proves it
    exists," which is exactly the question this mission's chain of Red Team passes had to
    reconstruct from scratch 7 times because no standing role owned asking it systematically.
    `ORG_CHART.md` updated to fifteen roles.
  - **Charter rewritten**: `decisions/2026-08-02_security-governance-framework_SCOPE.md` now contains
    the 3-layer principle (with the founder's own worked bad-model/good-model example), the
    immediate prerequisite (Limiter collapse as a hard precedence gate), the concrete
    rate-limiting-scoped deliverable (3 Runtime Witnesses: `scope`, identity fallback,
    `concurrency`), and an explicit statement that RLS/auth/PII extensions are named as motivation,
    not designed in this pass.
- Phase 3 (Mandatory Opposition), **architecture validation pass on the new charter**: **in
  progress** — not a classic Red Team pass; scoped exactly to the founder's own prompt: attack the
  Security Governance Framework as a foundation for enterprise security enforcement (not individual
  rate-limit details); test whether this model can prevent false security claims in future features
  (authorization, RLS, encryption, AI provider controls, PII handling); central question: can a
  document still claim a control exists without a runtime witness, under this charter's own rules?
- **Done — architecture validation pass complete.** **VERDICT: NOT YET A SOUND FOUNDATION** (not
  "start over" — the 3-layer model itself confirmed directionally sound). The decisive finding: the
  charter's own worked exemplar row — describing check 7 as "present and working, the one control
  with a real Runtime Witness" — was itself false. Verified: `docs/security/route_security_registry.yaml`
  does not exist and zero implementation of check 7 exists anywhere in the repo; it survived
  falsification as a specification, never as running code. The charter committed the exact defect
  (declaring a control present with no runtime evidence) in the paragraph meant to prove the defect
  was fixable. All 5 hypothetical domain claims (authorization, RLS, encryption, AI provider, PII)
  would have passed the Revision 1 charter's rules while remaining unverified or actively false —
  most seriously, the charter's own RLS worked example (`enforcement="RLS_POLICY_X"`) is factually
  wrong for this codebase specifically: `shared/deps.py:80` uses the service-role key, bypassing RLS
  on every backend request (SEC-004), so a witness implementing that example verbatim would return
  green on a control not in the request path — strictly worse than the original `scope: fixed` defect
  it was written to prevent. The recursion question (can a Runtime Witness itself become just another
  unverified claim) was confirmed real and unaddressed in Revision 1, with its own termination
  condition already present, unlabeled, in this repo's test suite (`tests/test_sec003_llm_wrapper.py`
  holds both a registration-only check and a real outcome-verifying check side by side). Report:
  `decisions/ARCHITECTURE_VALIDATION_2026-08-02_security-governance-framework.md`.
- **Founder direction received:** confirmed the 3-layer model is the right direction and specifically
  praised catching the recursion question. Added two concrete refinements before any further pass:
  (1) **Runtime Witness Quality Levels W0-W3** (declaration-only / binding-verified / execution-
  verified / security-property-verified — a strict refinement of the validation pass's own
  REGISTRATION-vs-OUTCOME binary, adding a "binding" level between them and a "security property"
  level above, per the founder's own worked example: 10 users behind one IP, legitimate access
  allowed, enumeration attack demonstrated to fail); (2) **Core/Adapter structure** — one small,
  fixed Security Governance Core (the layering, the W0-W3 scale, the negative-control rule, the
  venue-declaration requirement) plus a separate Adapter per security domain, explicitly rejecting a
  single "universal security checker" as an anti-pattern.
- **Done — charter rewritten to Revision 2:** the false exemplar row corrected to state its actual
  status (specified, never implemented); the RLS worked example deleted and replaced with a
  reachability-safe generalized form; the W0-W3 Runtime Witness Quality Levels section added in full,
  with minimum-level requirements tied to existing CRITICAL/HIGH severity classifications; the
  mandatory negative-control rule generalized from its one rate-limiting instance (the Limiter
  collapse) into a standing rule; the Core/Adapter structure added explicitly; an enforcement-venue
  declaration requirement added (this repo's CI mocks all external services — `fake.supabase.co`,
  `sk-fake` — so OUTCOME-class witnesses for RLS/encryption/provider-behavior cannot run there, and
  the charter no longer claims otherwise); a **Generalization Gate** added — the framework is not
  considered validated by the rate-limiting adapter alone (rate limiting is the one domain where
  Policy and enforcement share one in-process object, which the validation pass called "domain luck,
  not evidence of generalization") — at least one W2+ witness with a demonstrated negative control
  must land in an out-of-process domain first, with SEC-055 (`data_classification.py`, W0 today,
  zero callers) and the SEC-003 embeddings gap named as the two cheapest real candidates.
- **Done — Agent 15's charter corrected:** the boundary with Agent 05 redrawn from "should-be vs. is"
  (found collapsible, since Agent 05 already forbids doc-rubber-stamping) to **static-code-reading
  (05) vs. execution-observed (this role)** — the distinction that actually explains why static
  review missed `scope: fixed` for 7 passes while execution caught it in one. Its Output section
  tightened to require citing a re-runnable artifact (test path or CI job) and an observed negative-
  control result — a prose "witness exists and works" claim is no longer an acceptable finding from
  this role, closing the validation pass's finding that Agent 15's own output was otherwise as
  unverifiable as everything else in scope.
- Phase 3 (Mandatory Opposition): per this mission's own narrowing discipline, the next check on this
  document (not yet launched) should be scoped specifically to whether Revision 2's fixes survive
  being checked against actual repo state — particularly the corrected exemplar section and the new
  W0-W3/negative-control text — rather than a full re-review.
- Phase 4 (Security Gate): pending that narrower check.
- Phase 5 (Implementation): **deliberately deferred** — founder explicit instruction, not started.
- Phase 6 (QA): N/A until Phase 5 authorized.
- Phase 7 (Release Governance): N/A until Phase 5 authorized.

## Current blocker
None yet — Revision 2 is written; awaiting the targeted Red Team re-check's verdict before Phase 4.

## Next action
1. **In progress** — fresh, non-fork Red Team agent launched for a **targeted re-check** of
   Revision 2 (scope: the 8 Critical/High items + 4 Medium/Low items from pass 1's report — not a
   full fresh audit). Report will land at
   `decisions/RED_TEAM_REPORT_2026-08-02_revision2.md`.
2. **Done** — root-cause-clustering analysis added to the Architecture Decision doc (new section,
   before "Answer to 'if only one epic can start right now'"): 6 clusters identified; clusters
   1/3/5/6 structurally closed by this plan's epics (mostly Epic H, F, D/E); cluster 2
   (session-based resources with no first-class owner column) closed for its 2 known instances but
   flagged as needing a design-review-template fix, not just a code patch; cluster 4 (rate/cost
   controls as opt-in decorator, not default-deny) is the one genuine open gap this analysis found
   — Epic B closes known instances, not the mechanism.
3. **Done** — 14th agent role added: `agents/14_compliance_enterprise_readiness.md`
   (Compliance / Enterprise Readiness), `ORG_CHART.md` updated to fourteen roles. Advisory-only,
   no veto — distinct from Agent 05 (technical control correctness) by design. First recommended
   use: reviewing this remediation plan's Epic E/Epic A against the medium-firm and
   government/regulated segments, once Phase 4 clears.
4. If Red Team pass 2 returns PASS → Phase 4 Security Gate → deliver finished plan to founder for a
   Phase 5 go/no-go. If CONDITIONAL → targeted architecture fix, no third full revision cycle
   unless genuinely warranted. If BLOCKING again → escalate to founder directly rather than attempt
   a Revision 3 unilaterally — two full BLOCKING verdicts on the same artifact is itself a signal
   worth surfacing, not absorbing silently.
5. Separately open, not part of this mission's critical path: Program 1's Revision 8 fixes still
   await their own second targeted red-team re-check (requested earlier, deferred when this
   mission started, not yet resumed).
