# Security Governance Framework — Epic Charter

**Status:** ACTIVE BLOCKER. Revision 2 — the architecture validation pass returned **NOT YET A SOUND
FOUNDATION** against Revision 1; all findings fixed below. Pending one further, narrower validation
check before any build-out (see "Status after validation," end of document).
**Trigger:** the Route Security Model's narrow falsification-only re-check (7th consecutive real
Red Team finding across this mission) returned BLOCKING on all 5 named tests. Per the founder's own
pre-committed branching rule, a finding at this stage means the theme is broader than rate limiting
and gets its own epic — not another Epic B patch.
**Sources:** `.vindex_ai_team/decisions/RED_TEAM_REPORT_2026-08-02_route_security_model_falsification2.md`;
`.vindex_ai_team/decisions/ARCHITECTURE_VALIDATION_2026-08-02_security-governance-framework.md`
(Revision 2's basis).
**Founder's own framing, preserved verbatim because it is the standard this document is held to:**
*"Deklarisana kontrola ≠ izvršna kontrola... kod enterprise proizvoda najveća opasnost nije samo
rupa. Veća opasnost je false confidence... 'imamo zaštitu' a nemaš je, je mnogo gore [nego da znaš da
je nemaš]."*

---

## Revision history

- **Revision 1**: the 3-layer principle (Intent → Policy → Runtime Witness), the Limiter-collapse
  prerequisite, the 3-item rate-limiting deliverable, and the new Agent 15 role.
- **Revision 2** (this document): an architecture validation pass (not a classic falsification pass
  — this document was reviewed as a foundation, the way a constitution is reviewed rather than a
  specific law) returned **NOT YET A SOUND FOUNDATION**, with a decisive, self-referential finding:
  **the charter's own exemplar row — cited as proof the principle is buildable — was itself false.**
  It described check 7 as *"present and working... the one control in the whole model with a real
  Runtime Witness"*; verified directly, `docs/security/route_security_registry.yaml` does not exist
  and zero implementation of check 7 exists anywhere in the repo. Check 7 survived falsification as
  a **specification**, not as running code. The charter committed the exact defect — declaring a
  control "present and working" with no runtime evidence — in the paragraph written to demonstrate
  the defect was fixable. All findings below are fixed in this revision; none required discarding
  the 3-layer model, which the validation pass confirmed is directionally sound.

---

## Why this is its own epic, not Epic B Revision 8

The falsification pass's own "Framing judgment" section, quoted because it names the generalizable
defect precisely:

> *"Every finding in all five tests has the same shape. The document declares a control and asserts a
> security property, without a check that binds the declaration to an executable runtime witness...
> That principle is not specific to rate limiting — it applies identically to RLS policies, auth
> dependencies, and PII redaction, all of which this codebase declares in prose today."*

This is the same escalation shape already climbed twice in this mission: Epic B's 5 patches were
symptoms → the Route Security Model was the generalization → the model's own 6 findings were
symptoms → this document is the next generalization up.

## The principle (design now; do not build 5 separate frameworks)

Per the founder's explicit instruction: this document designs **one central principle**, not a
rate-limiting framework, an RLS framework, an auth framework, and a PII framework separately —
building five parallel systems would repeat the exact "narrow, inconsistent application of an
already-correct pattern" diagnosis this whole mission traces back to.

### Three layers, every security control

```
Intent Layer
    |  "what should be true" -- a human-readable security requirement
    v
Policy Layer
    |  "what is declared" -- a structured, machine-readable assertion of the control
    v
Runtime Witness Layer
    |  "what is actually verified to be enforced" -- an executable check binding the
    v  declaration to real, running code/config, not merely to its own existence
```

**Corrected status of the worked example (Revision 2 — was the false exemplar row):** check 7, as
specified in `docs/architecture/ROUTE_SECURITY_MODEL.md` §6.4, is a sound **design** for a Runtime
Witness — it survived every falsification attempt made against it *as a specification*. It has
**never been implemented**: `docs/security/route_security_registry.yaml` does not exist, and no
code implementing check 7 exists anywhere in this repository (verified 2026-08-02, repo-wide grep,
zero matches). It is cited below as a template for what a Runtime Witness's *shape* should look
like, never again as evidence that one currently exists and works.

| Example | Intent | Policy (declared) | Runtime Witness (actual status) |
|---|---|---|---|
| Scrape protection | "IDs shouldn't be enumerable" | `scope: fixed` in the registry | None — `scope` isn't even a real slowapi parameter; nothing checks the decorator actually calls `shared_limit(scope=...)` |
| Exemption | "`/health` shouldn't be rate-limited" | `exempt: true` | **Specified, never implemented.** Check 7 (`ROUTE_SECURITY_MODEL.md` §6.4) describes binding `exempt: true` to an actual `@limiter.exempt(...)` registration — a sound design, confirmed unbroken by every falsification attempt made against it on paper. No registry, and no code implementing this check, exists in the repo. |
| Identity fallback | "unauthenticated requests get a defined fallback" | prose in `rationale.reason` | None — nothing checks the route's `key_func` actually has non-empty-key behavior |

### Bad model (what this codebase does today, restated per the founder's own example)

```python
# route requires tenant isolation      <- Intent, as a comment
@router.get(...)
def get_client():
    ...                                 # <- no Policy layer, no Runtime Witness anywhere
```

### Good model, corrected (Revision 2 — the original RLS example was itself wrong for this codebase)

The validation pass proved the Revision 1 example (`enforcement="RLS_POLICY_X"` for a `/clients`
surface) is not a hypothetical illustration — it is a **factually false claim about this specific
codebase**: `shared/deps.py:80` builds the one app-wide Supabase client using the service-role key,
which bypasses RLS on every backend request (SEC-004, CRITICAL, still open). A witness implementing
that example literally would query `pg_policies`, find `klijenti_select` genuinely present and
active (migration 078), and return **green — certifying a control that is not in the request path**.
That is strictly worse than the `scope: fixed` failure this whole framework exists to prevent,
because `scope` was at least unverifiable by construction; `RLS_POLICY_X` is verifiable and wrong.
**The Revision 1 example is deleted.** Corrected shape, generalized rather than tied to a specific
(and specifically false) mechanism name:

```yaml
# Policy layer — a structured declaration, per control, per protected surface
control:
  tenant_isolation: required
```

```python
# Runtime Witness layer — an executable check binding the declaration to a REACHABLE
# enforcement mechanism, not merely a mechanism that exists somewhere in the system
verify_runtime_binding(
    surface="/clients",
    policy="tenant_isolation",
    enforcement="<the mechanism actually on this surface's request path>",
    # For THIS codebase, tenant isolation on backend routes is enforced by
    # per-handler .eq("user_id", ...) filtering (SEC-004's documented architecture),
    # NOT by RLS, since the backend's DB client uses the service-role key.
    # A witness naming "RLS" here would be reachability-invalid -- see the
    # Reachability Predicate (R1) below, which is precisely the check that
    # would have caught the deleted example.
)
```

CI fails if the binding cannot be verified. This is the generalization of check 7's *shape* —
corrected, per the validation pass, to require the 4 additional properties below (R1-R4), none of
which change the 3 layers, all of which close the gap between "the mechanism is named" and "the
mechanism is the one actually protecting this surface."

## What a Runtime Witness must actually establish (Revision 2 — new; this section did not exist in Revision 1 and its absence was the validation pass's central finding)

The validation pass proved that "a Runtime Witness exists" is not itself a single binary property —
it found real controls in this codebase sitting at meaningfully different levels of proof, and found
that a checker satisfied by the weakest level produces exactly the false-confidence failure this
whole framework exists to prevent. Per the founder's own refinement: a Runtime Witness has 4 quality
levels, not one, and an enterprise-grade control requires a stated minimum.

### Runtime Witness Quality Levels (W0-W3)

| Level | Name | Establishes | Example (real, from the validation pass) |
|---|---|---|---|
| **W0** | Declaration only | The control is described in prose or a Policy-layer field. Nothing checks it. | `security/data_classification.py`'s full API (`can_send_to_ai`, `sanitize_for_ai`, ...) — fully implemented, documented in the Architecture Bible as part of the security stack, **zero callers anywhere in the codebase** (SEC-055). Complete Intent, complete Policy, zero runtime anything. |
| **W1** | Binding verified | The named mechanism is confirmed to be **on the actual request/write path** of the protected surface — not merely present and callable somewhere in the system. Operational test: *"if this mechanism were disabled, would this surface's behavior change?"* | The deleted `RLS_POLICY_X` example fails W1: disabling that RLS policy changes nothing for backend traffic, since the backend never runs as a role RLS applies to. |
| **W2** | Execution verified | Exercising the real system produces the declared behavior — a request is actually made, and the actual response/effect is observed (a 429 returns; a provider call is actually blocked; a write is actually rejected). | `tests/test_sec003_llm_wrapper.py::test_sync_call_blocked_before_reaching_openai` — exercises the guarded call path and asserts the provider is never reached for an attack input. This is **not** the same file's `test_completions_create_is_patched`, which only asserts a patch was installed (W1-level at best — confirms binding, not behavior). |
| **W3** | Security property verified | The specific attack the control exists to stop is demonstrated to fail, under a realistic adversarial shape, not just one probing request. | Founder's own worked example: 10 users behind one shared IP; the legitimate user's request is allowed; a scripted attacker attempting to enumerate all clients through the same surface is demonstrated to fail. This is deeper than W2 — W2 shows *a* request gets the right response; W3 shows the *class of attack* the control is named for actually doesn't work. |

**Minimum required level, stated explicitly (this is the founder's own instruction and the
validation pass's R2 finding, merged):** a control classified CRITICAL or HIGH under
`docs/security/SECURITY_GAP_REGISTER.md`'s existing severity scale requires **at minimum W2**;
W3 is required wherever the control's entire purpose is resisting a specific enumerated attack
shape (scraping, enumeration, cross-tenant access) rather than a generic availability/cost concern.
A control may be shipped at W0 or W1 **only** if explicitly labeled as such — the failure mode this
whole framework exists to close is a W0/W1 control being *presented* as W2/W3, never a W0/W1 control
honestly labeled as what it is.

### The regress question, and why it terminates at W2/W3, not W1

The validation pass asked directly whether a Runtime Witness can itself become just another
unverified Policy-layer claim — i.e., whether "the mechanism is registered" quietly becomes the new
thing nobody checks. **Answer: yes, and this repository already contains a live instance of exactly
that, discovered by the same pass that is fixing this document.** Check 7 itself, as specified, only
verifies that `@limiter.exempt(...)` was *called* — it does not verify that `limiter.exempt` *does*
anything. That is W1 dressed as W2. The regress does not go on forever, though: **a witness that
observes the actual security outcome on the protected surface (W2) — or the actual attack failing
(W3) — does not care what mechanism produced that outcome, what library version is installed, or
whether a name was spelled correctly.** W2/W3 is where the regress bottoms out, because it stops
asking "was the right function called" and starts asking "did the right thing happen." This is
exactly the distinction already present, unlabeled, in this repo's own test suite (see the W2 example
above) — the framework's job is to make that distinction mandatory and named, not to invent it.

**Mandatory negative control, for every witness at W1 or above:** a witness is not accepted until it
has been demonstrated to fail — break the control deliberately (disable the mechanism, revert the
patch, remove the policy) and confirm the witness goes red, with the demonstration recorded alongside
the witness itself. This is cheap, and it is the *only* mechanism that reliably catches a witness
pointed at the wrong runtime object (the exact defect that made check 7's real ancestor — the
two-`Limiter`-instance problem — invisible to its own oracle). The Limiter-collapse prerequisite
below is one specific instance of this general rule; the rule itself, not just its rate-limiting
instance, is now part of this framework.

## One framework core, many domain adapters (not one universal checker)

Per the founder's explicit instruction, and independently confirmed necessary by the validation
pass's finding that RLS/auth/encryption/PII controls all fail differently and need different
verification mechanics (a live DB query, an execution trace, a call-site sweep, a call count): this
framework is **not** a single "AI security validator" that inspects everything. It is a small,
fixed **Core** — the definition of what counts as proof (the Intent/Policy/Witness layering; the
W0-W3 scale; the mandatory negative control; the venue-declaration requirement below) — plus one
**Adapter per security domain**, each of which knows what "binding," "execution," and "security
property" concretely mean in its own domain and which venue can execute its checks.

```
        Security Governance Core
   (Intent/Policy/Witness layers, W0-W3
    scale, negative-control rule, venue
    declaration requirement)
                |
      +---------+---------+---------+----------+
      |         |         |         |          |
 Rate Limiting  RLS   Encryption  AI Provider  PII
  Adapter     Adapter   Adapter    Adapter    Adapter
```

The Core does not know what a `Limiter` is, what `pg_policies` is, or what `Completions.create` is.
Each Adapter does, and each Adapter is responsible for stating, per the venue rule below, where its
checks can actually run. This is why the rate-limiting deliverable below is scoped as **one
adapter**, not as proof the whole framework works — proving one adapter's mechanics is not the same
as proving the Core generalizes, which is exactly the validation pass's sequencing warning, addressed
directly in "Status after validation" below.

## Enforcement venue must be declared per domain, honestly (Revision 2 — new, R4)

The validation pass found this repository's actual CI (`.github/workflows/tests.yml`) runs against
`fake.supabase.co` / `sk-fake` with all three external services mocked, stated in the workflow file
itself. **An OUTCOME-class (W2+) witness for RLS, encryption-at-rest coverage, or real provider
behavior cannot execute in that job — only in-process, REGISTRATION-class (W1-at-best) checks can.**
This framework does not get to claim "CI enforces this" for a domain whose real enforcement venue CI
cannot reach. Every Adapter must state, per control, which of these actually runs its witness:
- the existing mocked CI job (valid for W1 binding checks only, and only where the mocked object
  still faithfully represents the real binding — e.g. slowapi's in-process `Limiter`);
- a separate live-environment job with real credentials (the shape `scripts/export_rls_policies.py`
  is already reaching for, requiring `SUPABASE_DB_URL` rather than the app's service-role key);
  or
- a periodic production probe, for anything that can only be meaningfully checked against live data
  or live traffic.

`.github/workflows/security.yml`'s existing per-job BLOCKING/HIGH-only/INFORMATIONAL declarations are
the correct model for this kind of honesty and should be followed, not reinvented.

## Immediate prerequisite (blocks everything else, sequence first)

**Collapse the two `Limiter` instances.** The falsification pass proved this is *actively producing
false-green results right now*, in the very checks meant to prevent false-green results: §6.4's
checks 6 (shadow-pair oracle) and 7 (exemption oracle) both read `app.state.limiter`, which is
`api.py:547/549`'s instance — invisible to 415 decorations across 93 modules registered against
`shared/rate.py:89`'s separate instance. This must be a **hard CI gate that runs and passes before
any other check in this framework runs** — not "alongside." (This is also the framework's own
worked instance of the mandatory negative control above: the collapse is only confirmed correct once
someone deliberately un-collapses it and watches the gate go red.)

## Rate-Limiting Adapter deliverable (one adapter, not proof of the whole framework)

Generalize check 7's *shape*, corrected per W1-W3 above, and apply it to the 3 places the
falsification pass found it missing in the Route Security Model:
- `scope: fixed` needs a W2 witness verifying the decorator actually calls
  `shared_limit(scope=...)` **and** that enumerating distinct IDs against the route produces 429s
  in aggregate (not just that the parameter is present) — `Limiter.limit()` has no `scope` parameter
  at all, so today's declaration is unverifiable by construction, let alone true.
- `identity_dimension`'s stated identity-unavailable fallback needs a W2 witness — a falsy
  `key_func` result silently disables a limit entirely (`extension.py:502`); the witness must exhibit
  the fallback actually engaging, not just assert it in prose.
- `concurrency` (for `non-http-stream` routes) needs a W2 witness that an enforced concurrency cap
  actually rejects the (N+1)th concurrent connection — and the classification rule gating it needs
  correcting first, since it currently misclassifies real streaming-HTTP (SSE) routes.

**This adapter is necessary but not sufficient to validate the framework — stated explicitly per the
validation pass's sequencing warning:** rate limiting is the one domain where the Policy registry and
the enforcement engine run in the same in-process object, reachable from the existing mocked CI job.
Passing here is closer to proof the mechanics are buildable than proof the Core generalizes to a
domain where declaration and enforcement live in different systems (Postgres, OpenAI, disk).

## Generalization gate (Revision 2 — new; required before this framework is considered validated)

Per the validation pass's explicit recommendation: this framework is not considered validated by the
rate-limiting adapter alone. **At least one W2-or-higher witness, with a demonstrated negative
control, must exist in a domain whose enforcement lives outside the Python process**, before Epic B
resumes or any further domain adapter is treated as "just apply the same pattern." Two candidates are
already tracked in this codebase and cost little to attempt, per the validation pass:
- **SEC-055** — wire `security/data_classification.py` (currently W0: fully built, zero callers) into
  the AI chokepoint, and build a W2 witness that a classified-sensitive input is actually blocked or
  redacted before reaching a provider.
- **The SEC-003 embeddings gap** — `shared/ai_client.py::_patch_prompt_guard` covers chat completions
  only; `embeddings.create` is unpatched at 5+ live call sites. A W2 witness here (exercise an
  embeddings call with a malicious input, assert the guard engages) exercises R1-R4 in a domain that
  actually involves an external provider, unlike rate limiting.

Whichever is chosen, this is the framework's own proof of generalization, not a fourth parallel
framework — it is the RLS/AI-provider/PII Adapter question deferred by design in Revision 1, now
narrowed to "build exactly one, for real, before claiming the pattern generalizes."

## What happens to Epic B

**Epic B: HOLD.** Not because it failed — because it surfaced a system-wide pattern more important
than its own original scope. Its substantive fixes already made (the 6-pair shadow-pair decorations,
the exemption list, the `Limiter` collapse design, the tier-derivation methodology) are not reopened
or discarded; they were independently confirmed sound wherever tested. What remains of Epic B —
populating the Route Security Registry across the remaining ~590 live routes — is gated on: the
Limiter-collapse prerequisite, the Rate-Limiting Adapter's 3 W2 witnesses, **and** the Generalization
Gate above landing first, since populating a registry whose witnesses don't exist yet (or exist only
at W0/W1) reproduces the exact false-confidence failure this chain of Red Team passes exists to
prevent.

## Organizational change triggered by this finding

A 15th agent role, **Security Verification Engineer**, has been added
(`agents/15_security_verification_engineer.md`) — see that file for its corrected boundary
(Revision 2: static-code-reading vs. execution-observed, not "should-be vs. is," per the validation
pass's finding that the original boundary was collapsible against the existing Security & Privacy
Architect role).

## Explicitly out of scope for this charter, still

A full 9-section architecture spec (this project's own template) for how the Core/Adapter split gets
enforced mechanically in this specific codebase is the next step, not yet done here. The
RLS/auth/PII/encryption Adapters beyond whichever one is built for the Generalization Gate are named
as future work, deliberately not designed in this pass, per the founder's own instruction to
generalize one domain at a time rather than five at once.

## Status after validation

The architecture validation pass returned **NOT YET A SOUND FOUNDATION** against Revision 1, with 4
additive fixes (R1-R4, folded in above) and 2 corrections to the document's own claims (C1: the
false exemplar row, corrected above; C2: tense — "closes" corrected to accurately reflect nothing is
yet built). The validation pass explicitly stated this was **not** "start over" — the 3-layer model
and the escalation that produced it were both confirmed sound; the defects were in what the document
claimed was already proven, not in the model itself. Per this mission's own discipline (narrowing,
falsification-only re-checks rather than full re-reviews once a document has been substantially
corrected): the next check on this document should be scoped to whether Revision 2's fixes actually
close the validation pass's findings — particularly whether the corrected exemplar section and the
new W0-W3/negative-control text would, this time, survive being checked against the actual repo
state rather than accepted on the document's own say-so.
