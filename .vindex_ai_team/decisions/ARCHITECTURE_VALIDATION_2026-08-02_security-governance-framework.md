# Architecture Validation — Security Governance Framework Charter

**Pass type:** Architecture validation of a principle (not falsification of an implementation).
**Subject:** `.vindex_ai_team/decisions/2026-08-02_security-governance-framework_SCOPE.md`
**Supporting read:** `docs/architecture/ROUTE_SECURITY_MODEL.md` §6.4 (check 7), `.vindex_ai_team/agents/15_security_verification_engineer.md`, `.vindex_ai_team/agents/05_security_privacy_architect.md`
**Date:** 2026-08-02
**Brief tested:** *"Can this model prevent false security claims in future features — authorization, RLS, encryption, AI provider controls, PII? Can a document still claim a control exists without a runtime witness, under this charter's own rules?"*

---

## VERDICT: NOT YET A SOUND FOUNDATION

Answer to the founder's question, stated plainly: **yes — a document can still claim a control exists without a runtime witness under this charter's own rules, and the charter itself does it, in the one table row it uses as proof that the primitive works.**

I constructed a hypothetical claim in all 5 named domains, grounded in this repository. The charter's text as written would let **5 of 5** through as "compliant" while the control remained unverified or absent. In the RLS case the charter does not merely fail to catch it — the charter's own worked "Good model" example, copied verbatim, *produces* the false claim, because it names RLS as the enforcement mechanism for a `/clients`-style surface in a codebase where RLS is bypassed on every backend request (`shared/deps.py:80`, SEC-004).

This verdict is **not** "start over." The 3-layer model is directionally right and the escalation that produced it was correct. Every defect below is closable with 4 additive, specific edits (§6), none of which require redesigning the layers. But the charter is already operating as governing text — Agent 15's job description cites it as "the governing charter for this role's mandate" — and in its current form, a future author who conforms to it *exactly* ships a false security claim. That is a foundation defect, not a drafting nit, and it must be fixed before the 3 rate-limiting Runtime Witnesses are built on top of it.

**The one-sentence structural diagnosis:** the charter generalizes from the single domain where the policy registry *is* the enforcement engine (slowapi, in-process) to four domains where the declaration and the enforcement live in different systems (Postgres, OpenAI, disk, network) — and it carries over check 7's shape without carrying over the property that made check 7 work.

---

## 1. Domain tests — 5 hypothetical claims, grounded

### 1.1 Authorization — **LETS IT THROUGH**

**Hypothetical claim:** *"Every `{predmet_id}`-scoped mutation route verifies that the caller owns the predmet."*

**Grounded state.** SEC-001 (Gap Register line 14) found `POST /api/predmeti/{id}/beleske` and `.../istorija` inserting with no ownership check — a confirmed cross-tenant write — and closed it with a 24-endpoint sweep plus 6 regression tests. `docs/security/AUTHORIZATION_PATTERN_RECOMMENDATION.md` §1 documents that the surviving 22 endpoints use **three different mechanisms**: (A) inline `.eq("id", predmet_id).eq("user_id", uid)`, (B) named per-file helpers (`_dohvati_predmet`, `_proveri_vlasnistvo`), (C) owner-OR-collaborator logic. My repo-wide grep for a canonical primitive (`def assert_owner|require_ownership|verify_predmet|_owns`) returned **zero results** — there is no single enforcement function to bind a declaration to.

**Under the charter.** Policy: `control: tenant_isolation: required`. The witness must fill in `enforcement=`. With three mechanisms and no primitive, the only mechanically resolvable witness is *"the handler's source contains one of patterns A/B/C."* That is a static source-pattern check. It cannot distinguish "`.eq("user_id", uid)` is applied to the query that returns the protected data" from "`.eq("user_id", uid)` appears somewhere in a 60-line handler on an unrelated second query," and mechanism C is not expressible as a pattern at all.

**Does the charter catch it?** No. The charter contains no requirement that a witness observe enforcement rather than the presence of a construct correlated with enforcement. Note this is precisely the `_route_limits`-membership mistake — and **Agent 15's `Forbidden` section names that mistake explicitly, while the charter does not.** The governing document is weaker than the role definition it spawned.

The honest witness exists and is cheap: execute each route as user B against user A's `predmet_id` and assert denial. SEC-001's own tests are exactly this shape (including a well-designed control: non-existent ID rejected *identically* to someone-else's, so there is no existence-vs-ownership oracle). Nothing in the charter forces that version over the source-pattern version.

### 1.2 RLS — **LETS IT THROUGH; this is the charter's own example**

**Hypothetical claim:** *"The `klijenti` table is protected by row-level security; a user cannot read another firm's clients."*

**Grounded state.** Three independently verified facts:
1. `supabase_setup.sql` declares 49 RLS constructs, including `klijenti_select/insert/update/delete` (lines 586-604).
2. `shared/deps.py:80` builds the **one app-wide Supabase client** with `SUPABASE_SERVICE_KEY`. Service role bypasses RLS entirely. Gap Register SEC-004 (**CRITICAL**, still `P0 mitigate, ongoing`) states it exactly: *"tenant isolation for ~150+ endpoints rests 100% on each handler manually filtering by `user_id`; RLS is not a backstop for a missed filter."*
3. `scripts/export_rls_policies.py`'s own docstring records that RLS policies *"se danas menjaju isključivo ručno u Supabase Dashboard-u i nigde nisu zapisane u repo-u"* — changed by hand in the Dashboard, recorded nowhere in the repo. SEC-034 proved the consequence empirically: `klijenti` and `predmet_komentari` ran in production with RLS **enabled and zero active policies**, for an unknown period, while `supabase_setup.sql` declared four CRUD policies for each. Reading the SQL file would have returned GREEN the entire time; only a live `pg_policies` query found it.

**Under the charter.** The charter's Good-model block (lines 86-93) is:

```python
verify_runtime_binding(surface="/clients", policy="tenant_isolation",
                       enforcement="RLS_POLICY_X")   # "names the ACTUAL mechanism, checkable against the live system"
```

Implemented literally: query `pg_policies`, find `klijenti_select` present (it is — migration 078, 8/8 confirmed active per SEC-034), return **GREEN**. The control is certified. It is not in the request path.

**This is strictly worse than the `scope: fixed` failure it was written to prevent.** `scope` was unverifiable *by construction* — a parameter that does not exist on `Limiter.limit()` — so signature inspection can detect it. `RLS_POLICY_X` is verifiable by construction and **wrong**: the mechanism is real, live, queryable, and irrelevant, so the witness passes cleanly. A green check on a bypassed control is the highest-grade false confidence this codebase can produce.

Second-order problem the charter does not name: for RLS the Policy layer **does not exist in the repo at all**. If it is derived from the live DB (the only accurate source), Policy and Witness become the same read, and the model degenerates — you cannot detect divergence between a declaration and reality when the declaration is a copy of reality. `export_rls_policies.py` is groping toward the right answer (committed snapshot + git diff = drift detection), but the charter's 3-layer diagram cannot express it.

### 1.3 Encryption — **PARTIALLY CATCHES, for the wrong reason; real witness is venue-blocked**

**Hypothetical claim** (taken verbatim from `security/crypto.py`'s HARD RULES header): *"JMBG, pasoš, PIB → `encrypt_field()` before the DB write, never plaintext."*

**Grounded state.** Enforced purely by call-site convention: `klijenti/router.py:241,243,245` (create), `:459,461,463` (update), `routers/import_klijenti.py:211` (PIB only). Nothing structural prevents a new write path from skipping it. `import_klijenti.py:205-211`'s own inline comment records a real historical divergence — PIB was previously written to a `pib` column *"koja ne postoji u šemi"*.

**Under the charter.** Policy: `field_encryption: [jmbg, broj_pasosa, pib]`; witness: `enforcement="security.crypto.encrypt_field"`. This is the one domain where the charter's tripwire fires correctly — `encrypt_field` is a real function with a real signature, so a misnamed mechanism would be caught the way `scope` should have been. But the charter's tripwire only asks *"is the named mechanism resolvable,"* never *"does it cover every path."* A call-site check passes trivially and misses the actual risk: a new router writing `jmbg` to a differently-named column, or writing plaintext alongside ciphertext.

The decisive witness is data-side — query the live DB for any row whose PII column fails `is_encrypted()`. That requires a live database. See §4: CI cannot provide one.

### 1.4 AI provider controls — **LETS IT THROUGH; the closest structural analogue to check 7**

**Hypothetical claim**, quoted verbatim from the code's own success log at `shared/ai_client.py:183-186`: *"svi GPT pozivi u aplikaciji sada strukturno zaštićeni (SEC-003)"* — all GPT calls in the application are now structurally protected.

**Grounded state.** `_patch_prompt_guard()` patches exactly two methods: `Completions.create` and `AsyncCompletions.create` (`:180-181`). It does **not** patch `embeddings.create`, through which user and document text reaches OpenAI from `routers/proof.py:100`, `routers/knowledge_base.py:55`, `routers/auto_discovery.py:163`, `routers/batch_ingest.py:54`, `routers/law_upload.py:83`. Separately, `:134-137`: if the OpenAI class import fails, the function logs an error, sets `_guard_patched = True`, and returns — **fail-open and latched**, so no later invocation can re-patch.

**Under the charter.** Witness: `enforcement="shared.ai_client._patch_prompt_guard"`, modeled on check 7 — verify the registration happened. `tests/test_sec003_llm_wrapper.py:64-68` **already implements exactly this**: `assert Completions.create.__name__ == "_guarded_create"`. GREEN. The claim "all GPT calls" is still false, and the fail-open latch is invisible to it.

This is the most important domain result in this pass, because it is check 7's shape transplanted into another domain, already existing in the repo, and demonstrably insufficient. It is direct evidence that check-7-shaped witnesses do not generalize safely.

The good news is in the same file: `test_sync_call_blocked_before_reaching_openai` and `test_benign_question_not_blocked_by_real_guard` assert the **outcome** (the provider call never happens; a benign call passes) rather than the registration. Those would not be fooled by a latched fail-open. **The repository already contains both witness classes side by side.** The charter has no rule preferring the second.

### 1.5 PII handling — **LETS IT THROUGH; the purest instance in the codebase**

**Hypothetical claim:** *"Data classified above a sensitivity threshold is not sent to AI providers, and PII is stripped before any provider call."*

**Grounded state.** `security/data_classification.py` implements the full API for this: `get_classification()`, `can_send_to_ai()`, `sanitize_for_ai()`, `require_classification()`, `classify_decorator()`. My repo-wide grep for any of those names outside the module itself returned **zero Python callers** — only documentation: the forensic audit (`docs/security/FORENSIC_IMPLEMENTATION_AUDIT_2026-08-02.md:331-333`, which reached the same conclusion by the same method), the Architecture Bible (`docs/architecture/VINDEX_AI_ARCHITECTURE_BIBLE_v1.0.md:252`, which **lists it as part of the security stack**), and SEC-055 (*"wire `data_classification.py` into the AI chokepoint, or delete it + correct the Architecture Bible"*).

**Under the charter.** Witness: `enforcement="security.data_classification.sanitize_for_ai"`. The function exists, imports cleanly, and is fully implemented. A resolvability witness returns GREEN on a module that has never executed in production once.

This case shows the charter's operative test — *"names the ACTUAL mechanism, checkable against the live system"* — is satisfied by **importability**, and importability is not enforcement. There is a complete Intent layer (Architecture Bible), a complete Policy layer (a correct, working module), and literally zero runtime anything.

### Summary

| Domain | Charter's verdict on an under-verified claim | Why |
|---|---|---|
| Authorization | Compliant (wrongly) | No canonical primitive; only a source-pattern proxy is resolvable |
| RLS | Compliant (wrongly) | Named mechanism is real, live, queryable — and bypassed by service_role |
| Encryption | Half-caught | Catches a misnamed mechanism; misses path coverage; real witness needs a live DB |
| AI provider | Compliant (wrongly) | Registration check passes; scope gap + fail-open latch invisible |
| PII | Compliant (wrongly) | Importability accepted as enforcement on a zero-caller module |

---

## 2. The recursion problem — can "Runtime Witness" itself be a Policy claim in disguise?

**Yes. The regress is real, the charter has no stated defense, and the charter documents one instance of the regress without recognizing it as the general case.**

Check 7 verifies that `@limiter.exempt(...)` was registered. It does not verify that `limiter.exempt` *does* anything — it trusts slowapi. So the witness is, structurally, "a function was called": a Policy-layer claim about the library, pushed one level down.

The charter proves this is not hypothetical, in its own "Immediate prerequisite" section: checks 6 and 7 read `app.state.limiter`, while 415 decorations across 93 modules registered against a *different* `Limiter` instance. The charter's own words: *"a witness derived from the wrong runtime object is not a witness at all."* That is exactly the regress — check 7 would be green and meaningless. The charter names it as a **rate-limiting prerequisite** rather than as **the general failure mode of every witness**, and so does not generalize the lesson it just learned.

A second, smaller instance sits inside the exemplar itself. `ROUTE_SECURITY_MODEL.md:489`: an entry marked `exempt: true` must correspond to an actual `@limiter.exempt(...)` registration **"or equivalent."** "Or equivalent" is undefined and unbounded, in the one check the charter holds up as the gold standard. Under a generalized framework, "or equivalent" is precisely where a future author inserts a proxy.

**The regress is not infinite, and this repository already contains its termination condition — it is just never abstracted.** `tests/test_sec003_llm_wrapper.py` holds both shapes:

- `test_completions_create_is_patched` — asserts `Completions.create.__name__ == "_guarded_create"`. **REGISTRATION-class.** One level of regress: it proves a patch is installed, not that it protects anything. Same class as check 7.
- `test_sync_call_blocked_before_reaching_openai` / `test_benign_question_not_blocked_by_real_guard` — exercise the call, assert the provider is never reached for an attack input and *is* reached for a benign one. **OUTCOME-class.** Zero levels of regress: it does not care what was patched, which library version is installed, or whether the mechanism is named correctly. If the protection stops working, the test fails.

**The principle that terminates the regress:** a witness bottoms out when it observes the *security outcome on the protected surface* — attack input denied, legitimate input allowed — rather than the presence of the mechanism intended to produce that outcome. Every registration check is one level of regress. Every outcome check is zero.

**The empirical backstop, which is cheaper and independently sufficient:** a witness that has never been demonstrated to fail is not a witness. `scope: fixed` was caught by measurement (0×429 across 30 distinct IDs). The two-`Limiter` problem was caught by discovering the check read the wrong object. Both are instances of one rule: *break the control deliberately and confirm the witness goes red.* This bounds the regress without needing to verify the library, the DB engine, or the provider — and it is the only mechanism that catches a witness pointed at the wrong runtime object, which no amount of code review reliably does.

The charter provides neither rule. Without them, "Runtime Witness" is a label, and a sufficiently motivated author can satisfy the charter with a registration check in every one of the 5 domains above — as §1.4 shows someone already has, in good faith, in production code.

---

## 3. Agent 15 — is the role distinction durable?

**Partly. The charter for the role is unusually well-defended for a role definition, but the boundary is drawn on the wrong axis, and the role has no mechanism preventing it from becoming the thing it was created to prevent.**

**What is genuinely strong** (worth crediting, because it is better than the governing charter): Agent 15's `Forbidden` list explicitly bans *"building a witness mechanism that checks a proxy for enforcement... instead of enforcement itself,"* names the `_route_limits`-membership mistake with its falsifying evidence, and its `Required inputs` demands *"the actual running system or an executable reproduction of it — never by trusting a description of what the system does."* Its invocation rule requires a fresh agent, not a fork, for framing-bias reasons. **This role definition already contains the anti-proxy rule that §1 found missing from the charter.** Recommendation R2 below is therefore a transcription upward, not an invention.

**Risk 1 — the boundary is drawn on a collapsible axis.** The stated distinction is *should-be (05) vs. is (15)*. But Agent 05's own `Forbidden` section already says: *"Rubber-stamping a claim from documentation without checking the actual code — the forensic audit's single most repeated finding type was 'the doc says X, the code does not.' This role exists specifically to prevent that gap from reopening."* Both roles claim the verification mandate. Under time pressure, two roles asking overlapping questions collapse into one.

The durable axis is available and is *not* the one used: **05 verifies against code (static reading); 15 must verify against execution (observed behavior).** This matters concretely — 05's invocation instruction is *"verify every claim against actual code."* Reading the code is exactly the method that missed `scope: fixed` for seven passes, **because the code did contain `scope="..."`**. Static reading confirms declarations; only execution falsifies them. Stating the boundary as static-vs-behavioral makes it decidable and non-collapsible. Stating it as should-be-vs-is does not.

**Risk 2 — no gate, so the function is absorbable.** Agent 15 has *"No independent veto"* and routes findings through 05/Red Team, who hold absolute veto. Nothing makes "a HIGH-severity control has no Runtime Witness" a blocking condition in its own right — escalation depends on severity, which is assigned by the layer under review. A role with a distinct mandate, no gate, and an overlapping peer holding absolute veto is a role that becomes an optional step.

**Risk 3 — yes, it can become another declaration layer, and the role's own text opens the door.** Its `Output` section permits the finding *"Runtime Witness exists and correctly proves the claim — in which case, say so explicitly and move on."* Nothing checks that assertion. A report stating "witness verified" is a Policy-layer claim *about a witness*, with no witness — the same defect, relocated into the verification function itself. The fix is cheap and already implied by the role's own `Required inputs`: **Agent 15's output must cite the executable artifact (test path, CI job name) and the observed failing case, never prose.** Then the report's claim is itself re-runnable, and the role's output is checkable by the same standard it applies to everyone else. Without that, the role's only defense against becoming a checklist is the diligence of whoever plays it — which is exactly the defense that failed seven times.

Note also that the role's stated *"First recommended use: verifying the Security Governance Framework charter's own claimed Runtime Witness examples"* is a good instinct but self-referential — Agent 15 validating the framework that defines Agent 15. §1.4 and §5 below were both findable by an outside pass; neither depends on the role existing.

---

## 4. Enforcement venue — "CI fails" is itself a declared control with no witness

The charter states: *"CI fails if the binding cannot be verified"* and that the enforcement mechanism must be *"checkable against the live system."* Verified against this repository's actual CI:

`.github/workflows/tests.yml` runs `pytest tests/ -q` with:
```yaml
SUPABASE_URL: https://fake.supabase.co
SUPABASE_SERVICE_KEY: fake-service-key
OPENAI_API_KEY: sk-fake
PINECONE_API_KEY: fake-pinecone
```
with the workflow's own comment: *"the test suite mocks Supabase/OpenAI/Pinecone throughout and does not hit live services."*

**There is no live system in CI.** Therefore, in the charter's own stated enforcement venue, an OUTCOME-class witness is impossible for RLS (needs Postgres with a real role), for encryption-at-rest coverage (needs real rows), and for actual provider behavior. What remains buildable in CI is in-process introspection — i.e. REGISTRATION-class proxies — which Agent 15's `Forbidden` list prohibits. **The charter mandates something its own venue cannot execute for 4 of 5 domains, and does not acknowledge the constraint.**

Corroboration that this is already a known, unsolved constraint rather than my inference: `scripts/export_rls_policies.py` (untracked, in progress) requires `SUPABASE_DB_URL` — a direct Postgres connection string its docstring explicitly notes is *"RAZLIČITA od SUPABASE_SERVICE_KEY koji koristi ostatak aplikacije"* — plus `psycopg2-binary`, deliberately excluded from `requirements.txt` as *"jednokratni/periodični ops alat, ne runtime zavisnost."* The one proto-witness in the repo that would work for RLS is, by construction, not runnable in the existing CI job.

`.github/workflows/security.yml` is a good counter-model and shows the team can do this well: it declares per-job enforcement policy explicitly (`secret-scan`: BLOCKING; `sast-core`: BLOCKING but scoped and HIGH-only, with the reason stated; `sast-full`: INFORMATIONAL). The charter needs the same per-domain honesty about which venue actually runs each witness.

Secondary note, lower confidence: both workflows trigger on `push: [main]` as well as `pull_request`. For work pushed directly to `main` (this project's standing practice per its auto-push rule), CI failure is a notification after the fact, not a gate — Railway deploys from the repository independently. This does not change the recommendations but does mean "CI fails" and "the change is prevented" are not the same statement here, and the charter should not conflate them.

---

## 5. Epistemic honesty of the charter's own text

**Mixed — genuinely disciplined in structure, with one falsifiable overclaim in the most load-bearing sentence in the document.**

**Where it is honest, and this is real:**
- Status line: *"Principle designed below; not yet implemented; pending an architecture validation pass on the principle itself before any build-out."* Accurate and appropriately scoped.
- *"What this principle is NOT"* explicitly declines to design the RLS/auth/PII witnesses, and *"Explicitly out of scope, still"* concedes the 9-section spec is unwritten.
- The **Epic B HOLD** reasoning is the charter correctly applying its own principle against its own predecessor: *"populating a registry whose witnesses don't exist yet reproduces the exact false-confidence failure this chain of Red Team passes exists to prevent."* That is the document doing the right thing at its own cost.
- The **Immediate prerequisite** (collapse the `Limiter` instances *before* any witness runs, not "alongside") is correct and is the single sharpest piece of reasoning in the charter. It is R3 below in specific form and deserves promotion to a general rule.

**Overclaim 1 — the exemplar row is false. This is the decisive finding.**

The charter's table marks the exemption control:

> **Present and working** — check 7 verifies an actual `@limiter.exempt(...)` registration exists. This is the one control in the whole model with a real Runtime Witness, and it's the only one the falsification pass could not break.

Verified in this environment:
- `docs/security/route_security_registry.yaml` — **does not exist** (`ls`: No such file or directory).
- Repo-wide grep for `route_security_registry|verify_runtime_binding|_exempt_routes` across all `.py` and `.yml` — **zero matches**.

There is no implementation of check 7. There is no registry for it to read. It has never executed once. Check 7 survived the falsification passes **as a specification**, not as running code.

The table's column header is *"Runtime Witness (what was missing)"*; the other two rows say "None." The contrast the table draws is present-vs-absent witness, and the reader's takeaway — stated in the row itself as *"the one control in the whole model with a real Runtime Witness"* — is that one runtime witness exists. It does not.

**This is the `scope: fixed` shape, committed by the charter, in the row it uses as its proof that the primitive is buildable.** A document affirmatively describing a control as "present and working" when measurement shows it does not exist is the precise defect the charter was written to eliminate. It is also the reason this pass cannot return SOUND: before the charter existed, "we have no runtime witnesses" was honestly known; after it, the governing document asserts there is one.

**Overclaim 2 — an unproven universal.** *"Every one of the 7 real findings across this mission's Red Team passes was, underneath its specific technical detail, exactly this."* Seven asserted, three shown in the table. The remaining four are verifiable — the reports exist — but are not verified here, in a document whose entire thesis is that assertion without demonstration is the defect.

**Overclaim 3 — tense.** The heading *"The failure mode this closes, stated exactly"* is present-tense and definite. Nothing is closed; nothing is built; the charter's own status line says so. "Intends to close" costs one word.

---

## 6. What must change before the 3 rate-limiting Runtime Witnesses are built

All four are additive. None requires redesigning the 3 layers.

**R1 — Add a reachability predicate to the definition of a witness.**
A witness must establish that the named mechanism is *on the request/write path of the protected surface*, not merely that the mechanism exists and is queryable. Operational form of the test: *"if this mechanism were disabled, would this surface behave differently?"* For RLS on any backend route today the answer is **no** (`shared/deps.py:80`, SEC-004). **The charter's `enforcement="RLS_POLICY_X"` example must be deleted or rewritten** — it is factually wrong for this codebase and, copied verbatim, generates exactly the false green it warns against. Replace it with an example whose mechanism is demonstrably on-path.

**R2 — Classify every witness, and require OUTCOME-class for CRITICAL/HIGH.**
- *REGISTRATION-class*: observes that a mechanism is installed (check 7; `test_completions_create_is_patched`). Permitted **only** where the registry consulted *is* the enforcement path — true for slowapi, false for Postgres, OpenAI, and disk — and must be labeled as such.
- *OUTCOME-class*: observes the protected surface denying an attack input and permitting a legitimate one (`test_sync_call_blocked_before_reaching_openai` + `test_benign_question_not_blocked_by_real_guard`).

Every CRITICAL/HIGH control requires at least one OUTCOME-class witness. This is the stated answer to §2's regress and is a transcription of a rule Agent 15's `Forbidden` list already contains — the charter is currently weaker than the role it created.

**R3 — Mandatory negative control: no witness is accepted until it has been demonstrated to fail.**
Break the control deliberately, confirm the witness goes red, record the demonstration alongside the witness. This is the empirical regress-terminator, costs almost nothing, and is the *only* mechanism that reliably catches a witness pointed at the wrong runtime object — the charter's own `Limiter`-instance prerequisite is one instance of this general rule and should be restated as the rule.

**R4 — Declare the enforcement venue per domain, honestly.**
CI runs on `fake.supabase.co` / `sk-fake` and mocks all three external services; it cannot host an OUTCOME-class witness for RLS, encryption coverage, or provider behavior. State per domain which venue executes the witness — CI job / live-environment job with `SUPABASE_DB_URL` (à la `scripts/export_rls_policies.py`) / periodic production probe — and do not claim CI enforcement for controls CI cannot reach. Model it on `security.yml`'s existing per-job BLOCKING/INFORMATIONAL declarations, which already do this well.

**C1 — Correct the exemplar row** to: *"specified in §6.4, never executed; no implementation exists in the repo and `docs/security/route_security_registry.yaml` does not exist (verified 2026-08-02). Survived falsification as a specification, not as running code."* Also bound or delete *"or equivalent"* in `ROUTE_SECURITY_MODEL.md:489`.

**C2 — Fix the tense** (*"closes"* → *"intends to close"*) and either cite all 7 findings or soften the universal.

### One sequencing warning

After R1-R4 land, the 3 rate-limiting witnesses are safe to build — but the charter must stop describing them as *"the concrete, immediately-buildable proof that the 3-layer principle works."* Rate limiting is the one domain where enforcement is in-process and CI-reachable, so success there is **domain luck, not evidence of generalization**. The planned first proof cannot fail in the way the other four domains fail, so passing it proves less than the charter claims it will.

Recommend the charter add an explicit **generalization gate**: the principle is not considered validated until one OUTCOME-class witness exists, with a demonstrated negative control, in a domain whose enforcement lives *outside* the Python process. The two cheapest grounded candidates are already tracked — SEC-055 (`data_classification.py`, zero callers, §1.5) and the `embeddings.create` gap in SEC-003 (§1.4). Either would exercise R1-R4 for real, at small cost, in a domain where the failure mode actually bites.

---

## Appendix — what this pass verified directly

| Claim | Method | Result |
|---|---|---|
| `route_security_registry.yaml` exists | `ls` | Does not exist |
| check 7 / `verify_runtime_binding` implemented | repo-wide grep, `.py` + `.yml` | Zero matches |
| Backend bypasses RLS | read `shared/deps.py:70-80`; Gap Register SEC-004 | Confirmed — one app-wide client, `SUPABASE_SERVICE_KEY` |
| RLS not version-controlled | `scripts/export_rls_policies.py` docstring; SEC-034 | Confirmed — Dashboard-only; 2 tables ran with 0 policies |
| No canonical ownership primitive | grep `def assert_owner\|require_ownership\|verify_predmet\|_owns` | Zero matches; 3 mechanisms per `AUTHORIZATION_PATTERN_RECOMMENDATION.md` §1 |
| Prompt guard scope | read `shared/ai_client.py:113-186`; grep `embeddings.create` | Patches chat completions only; 5+ live embeddings call sites unguarded; fail-open latch at `:134-137` |
| `data_classification.py` unused | repo-wide grep, `.py` + `.md` | Zero Python callers; doc references only |
| CI cannot reach live services | read `.github/workflows/tests.yml` | Fake credentials, all externals mocked, stated in-file |
| Both witness classes already in repo | read `tests/test_sec003_llm_wrapper.py` | Confirmed — registration-class and outcome-class side by side |
