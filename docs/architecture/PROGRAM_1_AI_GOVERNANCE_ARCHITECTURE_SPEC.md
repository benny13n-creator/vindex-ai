# Program 1 — AI Governance Layer: Architecture Specification

**Status: SPECIFICATION ONLY. Zero code in this document, zero code changed to produce it.**
**Date:** 2026-08-02. **Revision 8** — see "Revision history" below.

**Why Revision 7 exists, despite Revision 6's founder sign-off:** an independent, adversarial
red-team review (§9 item 1's required gate — a fresh reviewer with no authorship stake, no prior
context on this document, instructed to falsify rather than confirm, same discipline as SEC-031)
returned **BLOCKING: 2 Critical, 2 High**, all verified against the actual current code, not
theoretical. Per the founder's own pre-committed criterion — *"Ako ne uspe [red-team review]...
Blueprint se zamrzava... ako pronađe kritičan nalaz, radimo Reviziju 7"* — this is exactly that
scenario. Revision 7 fixed all four findings.

**Why Revision 8 exists, despite Revision 7's fixes:** per the founder's own instruction, a
*targeted falsification* re-check (not a full re-audit — narrower scope, explicitly forbidding new
findings or generic hardening advice) was run against exactly Revision 7's four claimed fixes. It
returned: **Item 3 (dead-parameter escalation) — OPEN**, mathematically proven the fix could never
change the outcome; **Item 2 (sync/async chokepoint gap) — PARTIALLY CLOSED**, with a new
structural contradiction; **Item 1 (embeddings) — PARTIALLY CLOSED**, a real gap in the highest-
volume path named as the fix's own proof case; **Item 4 (§8/§7 contradiction) — PARTIALLY CLOSED**,
lower severity, more a documentation-consistency defect than a new security gap. Per the founder's
explicit ruling: *"na osnovu ovog izveštaja ne bih dao Stage 5"* — and a specific methodology for
this revision: for each item, first confirm the root cause is correctly identified, then present
at least one alternative fix, and justify why the chosen one is better — not accept the first
working idea. This revision follows that method for all four; each fix section below states the
alternatives considered and why the chosen approach won.

**On the name "Program 1" vs "AI Trust Kernel":** founder review raised, correctly, that if this
becomes the substrate every future feature routes through, "Program 1" undersells what it is —
"AI Trust Kernel" names the end state honestly. **Recommendation: do not rename yet.** "Trust
Layer" and "Core Consolidation" both earned their names in this project through shipped, verified
work, not at Stage 4 with zero lines of code written — renaming now would be exactly the kind of
claim-ahead-of-evidence this Blueprint's own Principle 10 exists to prevent, and would require
updating cross-references across three governing documents (this spec, the Traceability matrix's
P1-P5 dependency graph, `FINDING_LIFECYCLE.md`'s stage tracking) for a purely cosmetic change.
Proposed trigger to revisit: when a second capability (not just this one) is actually routing
through the Decision Engine in production — Stage 8/9 territory, not Stage 4. Until then, this
document keeps calling it Program 1; "AI Trust Kernel" is recorded here as the target identity,
not adopted early.
**Position in hierarchy:** sits between `docs/architecture/VINDEX_TRUST_ARCHITECTURE_BLUEPRINT.md`
(the constitution) and any future implementation. Per the founder's explicit instruction: *"Tek
kada je ovaj dokument gotov... počinje kod."* This is Finding Lifecycle stage 4 (Remediation
Candidate) for Program 1 — see `docs/security/FINDING_LIFECYCLE.md`. It does not advance to stage
5 (Architecture Approved) until an independent peer review and founder sign-off (§9).

**Revision history:**
- **Revision 1** (2026-08-01): initial spec. Founder review verdict: **"Architecture Review —
  Conditionally Approved"** — correctly identified that the request/response Firewall pair alone
  is not Governance, only half of it. Four required additions before sign-off: (1) an explicit,
  ordered Data Classification Engine as the first stage; (2) a quantified per-operation Risk
  Scoring Engine, distinct from behavioral anomaly detection; (3) a single, named Decision Engine
  as the sole component authorized to emit a final verdict, with a richer action vocabulary than
  allow/deny; (4) an explicit "Untrusted Provider" principle — no LLM vendor, present or future,
  gets data access outside this layer.
- **Revision 2** (this document): incorporates all four. Structural change: **Decision Engine**
  is now the named "brain," invoked twice per call (once request-side, once response-side),
  consuming Risk Score + Policy requirements + Classification as inputs, never deciding on its
  own heuristics. Policy Engine's role narrowed to *declarative rule lookup* (what do the rules
  require), not the final verdict — that distinction did not exist in Revision 1 and was the root
  of the "Policy Engine and Firewalls aren't the same thing as Governance" critique.
- **Revision 3** (this document): founder verdict on Revision 2 — **"Architecture Review —
  Approved with Minor Amendments."** Three additions required before Stage 5: (1) a deterministic
  audit payload — one fixed JSON shape every Decision Engine call writes, not left to the
  implementer; (2) a deterministic per-component *unavailability* table (distinct from the
  per-error-type table already in §7) — what happens if Classification/Risk/Policy/Decision/Audit
  is entirely down, not just erroring on one ambiguous input; (3) a single numeric latency table
  in the founder's exact requested format. All three added: §6a (Audit Payload Schema, grounded in
  `shared/audit_immutable.py`'s real `log_action` signature — surfaced a genuine, concrete
  pre-implementation risk while grounding this: `AUDITABLE_ACTIONS` is a hardcoded allow-list,
  `shared/audit_immutable.py:56-81` — an unregistered action string silently no-ops, the same bug
  class as SEC-034/SEC-005/SEC-002's cron collision); §7.1 (new, clean unavailability table,
  distinguishing service-down from content-level ambiguity); §8 (single unified table, reconciled
  with the existing Response Firewall latency exception rather than silently dropping it).
- **Revision 4** (this document): founder verdict on Revision 3 — **"Approved with One Blocking
  Issue."** Verified before acting on it (per this project's own evidence-over-assumption
  discipline): grepped every current `log_action(_sync)?(` call site in the codebase against
  `AUDITABLE_ACTIONS` — **all 9 are correctly registered today; this is not a live production
  bug** (there is even an existing regression test guarding exactly this,
  `tests/test_legal_reasoning_engine.py:323-325`, for `reasoning_graph_generated`). It remains a
  real, correctly-caught **pre-implementation requirement specific to this Program's own future
  action string**, not a new SEC-XXX finding against current production — stated precisely rather
  than inflated. Founder's blocking issue — a single global "Audit unavailable → allow" default is
  too coarse — **fixed structurally**: new `AuditRequirement` tiering (§6, §7.1), risk- and
  policy-derived, replacing the single default with a tiered one. Also added: **Policy Versioning**
  (`policy_version` now flows through `PolicyRequirements`, `Decision`, and the audit payload —
  closes "why did this leave the perimeter on a given date" reconstruction) and an explicit
  **Deterministic Decision Requirement** on `DecisionEngine`, precisely scoped (replay-deterministic
  given a pinned `policy_version`, not eternally deterministic across policy changes — different
  claims, only the first is true by design). Blueprint itself amended with a new corollary under
  Goal 4 (Complete Auditability): audit-write failure must never go unnoticed.
- **Revision 5** (this document): founder confirmed 8b explicitly (**yes** — Risk may only
  escalate a Policy floor, never reduce it) and elevated it beyond a Program-1-local design
  choice: *"to čak treba da bude jedno od osnovnih pravila sistema... ne zbog AI-ja, nego zbog
  bezbednosti."* Formalized as new **§1.2, the Escalation-Only Invariant**, and added to the
  Blueprint itself (Principle 1, Default Deny) as a project-wide rule, not scoped to this Program.
  Concrete failure it closes, in the founder's own example: a translation feature's Policy floor
  (OPTIONAL audit) must not silently govern an unusually risky instance of that same feature (a
  document that happens to be privileged, GDPR-relevant, court-related) — Risk Scoring's high
  score for that specific instance must be able to override the feature's ordinary-case floor,
  never the reverse. Also: `RiskScore.contributing_factors` — **already present since Revision
  2/3** (not new) — tightened from free-form `list[str]` to a controlled `RiskFactor` enum (§6),
  since inconsistent ad hoc tagging across future risk-scoring implementations would defeat the
  exact forensic-reconstruction purpose the field exists for; corrected for the founder rather
  than silently claimed as new. **8a (risk-range calibration) remains explicitly open, not
  resolved** — the founder restated the question but did not supply committed numbers; still
  deferred to real operational data per §9.
- **Revision 6** (this document): closes 8a and answers the founder's pre-Stage-5 extensibility
  question. **8a**: founder supplied committed, non-linear boundaries (0-20 OPTIONAL / 21-45
  RECOMMENDED / 46-70 REQUIRED / 71-100 MANDATORY — risk is not linear, most operations are
  low-risk and few are extreme, and the gap between 68 and 72 is often the gap between an internal
  document and a privileged one) — adopted as starting values, §7.2, revisited against real
  operational data post-launch, not blocking Stage 5. Founder also asked whether a numeric score
  alone should be able to under-classify a specific `RiskFactor` present (example: score 34 with
  `PRIVILEGED_CONTENT` present would land on RECOMMENDED by the table alone, which the founder
  correctly rejected) — **architectural fix, not a bolt-on third formula term**: factor-based
  overrides (`PRIVILEGED_CONTENT`/`GDPR_RELEVANT` → minimum REQUIRED; sealed/classified-class
  content → minimum MANDATORY) now live as **declarative Policy rules matching on
  `RiskScore.contributing_factors`**, folded into `PolicyRequirements.minimum_audit_requirement`
  itself — `PolicyService.evaluate()` already received `risk: RiskScore` as a parameter since
  Revision 2, so this needed no new plumbing. §1.2's Escalation-Only Invariant formula stays a
  clean two-term `max()`, and factor overrides inherit `policy_version`'s replay-determinism
  automatically instead of needing a second, unversioned mechanism. **Extensibility question,
  answered directly in new §1.3**: partially yes, deliberately not fully — see that section.
- **Founder sign-off** (2026-08-02, no new revision number — per founder's own instruction, not
  every reviewed point reopens the architecture): final scorecard — Architectural coherence 10/10,
  Security model 10/10, Replay & audit design 10/10, Extensibility 10/10, Stage 5 readiness 10/10.
  Two implementation-level (not architectural) notes raised and captured in the addendum at the
  end of this document rather than as a revision: unknown-`RiskFactor` handling must fail closed,
  and the Escalation-Only Invariant (§1.2) needs a policy-*load-time* validator in addition to
  its runtime assertion (§9 item 9) — catching a bad rule at deploy time, not only at decision
  time. Founder's own condition for the next revision: only if independent peer review (§9 item
  1, still outstanding) finds a genuine fundamental flaw.
- **Revision 7** (this document): independent red-team review (fresh agent, no authorship stake,
  instructed to falsify) returned **BLOCKING**. Every code-grounding claim in §6a was verified
  accurate; the findings were architectural, not citation errors. Four fixes:
  - **Critical 1 — the chokepoint was framed as a per-*vendor* problem (§1.1) when it is really a
    per-API-*surface* problem.** `_patch_prompt_guard()` covers chat completions only. Verified
    live in this codebase, entirely ungoverned today: embeddings (`uploaded_doc/ingest.py`,
    `routers/knowledge_base.py`, 8+ more call sites — the actual client-document ingestion path),
    Whisper transcription + TTS (`routers/voice.py`), and the OpenAI Realtime API
    (`services/voice_orchestrator.py:46`, a raw `websockets` connection with no SDK class to
    patch at all — option (a) cannot cover it by construction). Founder's ruling: **all four
    surfaces in scope for v1**, not a disclosed exclusion. Fixed in restructured §1.1: chat and
    embeddings and audio get their own chokepoint (same monkeypatch technique, verified the exact
    SDK classes exist: `openai.resources.embeddings.{Embeddings,AsyncEmbeddings}`,
    `openai.resources.audio.transcriptions.{Transcriptions,AsyncTranscriptions}`,
    `openai.resources.audio.speech.{Speech,AsyncSpeech}`); the Realtime API gets a structurally
    different, session-level governance model since no chokepoint exists for it (new §1.1.1).
  - **Critical 2 — §7.2's Audit-unavailable tiering was unimplementable against the audit
    primitive it was grounded on.** §6/§7/§8 specified audit writes as fire-and-forget
    (non-blocking); §7.2 required denying/escalating *because* audit is unreachable — a
    fire-and-forget call returns before it could ever supply that signal. Founder's diagnosis,
    preserved precisely: a pre-flight health check (option 1) has a check-then-act race (health
    check passes, insert fails microseconds later); a local durable spool (option 2) trades one
    unprovable assumption for another (physical loss of unsynced local storage). **Founder's fix,
    adopted exactly as specified: replace "is audit available" with "did the audit record receive
    a durable acknowledgment" — for REQUIRED/MANDATORY, the action must not execute until the
    audit write itself confirms durable acceptance; no ACK means deny (or escalate for REQUIRED).
    OPTIONAL/RECOMMENDED keep fire-and-forget.** Elegant consequence, not a new mechanism: the real
    `shared/audit_immutable.py::log_action()` already returns exactly this signal (a real
    DB-assigned row ID on success, `None` on any failure) — the "fire-and-forget" property came
    entirely from callers wrapping it in `asyncio.create_task(...)` rather than awaiting it
    directly. The fix is a **tier-gated await discipline**, not new audit infrastructure. New
    §7.3, revised §6/§7.1/§8.
  - **High 3 — `decide_response`'s signature had no `policy`/`risk` parameters, so
    `audit_requirement` had no way to be re-derived or escalated on the response path.** Concrete
    gap: a low-risk request (OPTIONAL tier) whose response the Response Firewall flags as
    containing fabricated citations or unexpected third-party PII — a genuinely high-severity
    governance event — would inherit the request's OPTIONAL tier with no path to escalate it.
    Fixed: `decide_response` now also takes `policy` and `risk` (the same inputs call #1 received),
    and computes its own `audit_requirement` the identical way, allowed only to escalate relative
    to call #1's value (Escalation-Only Invariant, §1.2, applies across both calls now, stated
    explicitly).
  - **High 4 — `RiskScoringService.score()`'s "no network call" contract contradicted
    `AnomalyDetectionService.current_risk_modifier()`**, which §5 said fed *into* it, and which the
    real `security/anomaly_detection.py` implements via a live Supabase RPC call — and §7.1 had no
    row for Anomaly Detection being unreachable. Fixed: `current_risk_modifier()` is now an
    explicitly best-effort, tightly-timeout-bounded input — `score()` incorporates it only if it
    returns within a small fixed budget, contributes nothing (not a blocking failure) if it
    doesn't, and §7.1 gained its own row for this case.
- **Revision 8** (this document): a *targeted falsification* re-check (scope restricted to exactly
  Revision 7's four claimed fixes, forbidden from raising new findings) returned Item 3 OPEN and
  Items 1/2/4 PARTIALLY CLOSED. Founder's ruling: no Stage 5 on this result; fix properly, and for
  each item, prove the root cause first, present at least one alternative, and justify the choice
  — not accept the first idea that works.
  - **Item 3 (OPEN — the fix was a dead parameter).** Proven mathematically: §7.2's formula
    `max(policy.minimum_audit_requirement, score_derived_tier(risk.value))` has no term that reads
    `verdict`; Revision 7 added `policy`/`risk` params to `decide_response` but never added a term
    derived from the response itself, so the computed `audit_requirement` was provably always
    identical to call #1's. **Alternatives considered:** (a) add a third `response_derived_tier(verdict)`
    term directly to the formula — rejected: reintroduces a bespoke, ungoverned floor computed
    outside Policy, the exact anti-pattern Revision 6 already corrected for risk factors. (b) have
    Response Firewall itself emit an `audit_requirement_hint` — rejected: creates a second place
    besides Policy that can declare a floor, violating the single-source-of-truth-for-floors
    principle established since Revision 6. (c) **chosen**: extend `PolicyService` with a second,
    response-side method, `evaluate_response(verdict, context) -> PolicyRequirements`, matching
    declaratively on `verdict.quality_flags` — same versioned rule set, same `policy_version`,
    consistent with exactly how Revision 6 folded risk-factor overrides into Policy rather than a
    parallel mechanism. `decide_response`'s `policy` parameter is replaced by this freshly-computed
    `response_policy`, not the request-side object Revision 7 re-passed unhelpfully.
  - **Item 2 (PARTIALLY CLOSED — new contradiction: the async ACK design has no path on the
    ~46-site synchronous chokepoint).** Founder explicitly rejected accepting a solution without
    interrogating it: does it deadlock, what happens on timeout, what if no event loop is active,
    is there a simpler design. **Alternative considered and rejected:** bridging the sync chokepoint
    into the async event loop (e.g. `asyncio.run_coroutine_threadsafe`) — real deadlock exposure
    (waits on a loop that may be busy from a worker thread), timeout handling has to be built
    manually across the thread boundary, and fails outright if no loop is running in that context.
    **Chosen, after verifying it already exists in this codebase**: `shared/audit_immutable.py`
    already ships a synchronous counterpart, `log_action_sync()` (`:112-127`) — same
    `Optional[str]` durable-ACK return, same `_build_and_insert` call, zero asyncio involved,
    currently unused anywhere but present and correct. The fix is not a bridge; it is exposing the
    same sync/async split this codebase already uses for its audit primitive, across every
    Governance service — new §1.4.
  - **Item 1 (PARTIALLY CLOSED — embeddings chokepoint fires after tokenization for the
    highest-volume path).** Verified: `uploaded_doc/ingest.py`'s `_get_embeddings_client()` returns
    `langchain_openai.OpenAIEmbeddings`, whose `_get_len_safe_embeddings` (default
    `check_embedding_ctx_length=True`) tokenizes text before calling the SDK — by the time
    `Embeddings.create` fires, `kwargs["input"]` is `list[list[int]]`, not text. **Alternative
    considered:** disable `check_embedding_ctx_length` codebase-wide to force text-mode calls —
    rejected: changes existing, working chunking/batching behavior for a governance concern,
    couples this Program's rollout to an unrelated behavioral change. **Chosen, verified to exist**:
    `OpenAIEmbeddings.embed_documents`/`aembed_documents` (confirmed present,
    `texts: list[str]` parameter — real text, pre-tokenization) get their own class-level
    monkeypatch, the same technique, one layer above the OpenAI SDK, specifically for
    LangChain-mediated call sites. Raw-SDK embeddings call sites (`knowledge_base.py`, etc.) remain
    governed by the existing `Embeddings.create` patch, where text genuinely is the input.
  - **Item 4 (PARTIALLY CLOSED — §8/§7 still contradicted §6/§7.1's Revision 7 fix).** Lower
    severity than Items 1-3, correctly — a documentation-consistency defect, not a new bypass.
    Fixed: §8's Risk Scoring row now states its 10ms covers core scoring only, with the modifier's
    bounded attempt as a separate, explicit line; §7's Risk Scoring row now explicitly scopes
    itself to core-scoring failures, cross-referencing §7.1's Anomaly-Detection-specific row rather
    than silently overlapping it.

**Why this document exists before Program 2 or Program 3 implementation, not after:** the original
Phase 4 dependency graph (`VINDEX_TRUST_ARCHITECTURE_TRACEABILITY.md`) proposed implementing P3 →
P2 → P1 → P4 in sequence. The founder correctly challenged this: if Program 1 (AI Governance
Layer) becomes the central orchestrator, its contract requirements should shape what Program 2
(Data Classification) and the AI-facing parts of Program 3 (Access Control) need to expose —
building them first, to a guessed shape, risks the exact "wrong interface, discovered late"
rework this whole exercise exists to avoid. Confirmed by re-reading Vindex's own data flow:
**Classification is a stage inside the Governance pipeline**, not an independent upstream
service — so it must be specified here, not separately. Access Control (P3) is genuinely
different: ownership/entitlement resolution happens at the API/router layer, before any AI call
is even considered, so it remains implementable independently (see §2). Order:

1. **This document** (spec only)
2. Implement P3 (Access Control) — independent, already designed, can run in parallel with step 1
3. Implement P2 (Data Classification) — now built to the exact contract in §6, not a guess
4. Implement P1 (this Program — the Governance Layer itself)
5. Implement P4 (extend `audit_immutable` to cover this layer's own decisions)

P5 (Operational Resilience) remains fully parallel throughout, unchanged from the original graph.

---

## 1. Scope

**What the AI Governance Layer is:** the single, structural control plane through which every
outbound call to an external LLM passes, in both directions — request *and* response — making an
auditable, quantified, explainable decision at each stage about what data may leave, under what
transformation, to which provider, and whether what comes back may be used. **Governance is the
Decision Engine (§6) — Classification, Risk Scoring, and Policy are its inputs; the Firewalls,
Transformation, and Routing are its enforcement arms.** A system with firewalls but no single
decision-maker is a filter, not governance — this distinction, raised directly in founder review,
is now load-bearing throughout this document, not a one-line caveat.

**It is an extension of infrastructure that already exists and is already proven**, not a new
parallel system. `shared/ai_client.py::_patch_prompt_guard()` (SEC-003) already monkey-patches
`openai.resources.chat.completions.completions.Completions.create` /
`AsyncCompletions.create` **at the class level** — intercepting all ~130 call sites across 53
files with zero per-call-site changes, regardless of which router/service constructs the OpenAI
client (`shared/ai_client.py:113-187`, `_guarded_create`/`_guarded_acreate` at lines 155-178). The
Governance Layer's home is this same chokepoint, extended with additional stages running before
`_orig_create`/`_orig_acreate`, and — the single largest concrete gap this Program closes — a new
stage wrapping its *return value*, which nothing inspects today.

**What it explicitly is NOT:**

- **Not a rewrite** of `security/prompt_guard.py`, `services/quality_gate.py`, or
  `shared/genome_validator.py`. It composes and orchestrates them as stages (§3, §5) — each keeps
  its own file, tests, and ownership.
- **Not per-feature-module integration.** No change is required in `routers/case_dna.py`,
  `routers/drafting.py`, `app/services/retrieve.py`, or any of the other ~53 files that call an
  LLM. The guarantee SEC-003 already proved — protection is structural, not opt-in per call-site —
  is a hard requirement this Program must preserve, not relax.
- **Not a replacement for Program 3 (Access Control).** Identity, ownership, and entitlement are
  resolved at the API/router layer, upstream of this Program, before an AI call is even
  constructed (Trust Boundary 2, §2). This Program receives an already-authenticated,
  already-authorized request context; it does not re-derive "does this user own this predmet."
- **Not a network hop.** The existing chokepoint is an in-process monkey-patched Python function
  call. All new stages, including the Decision Engine, must be in-process — consistent with how
  `prompt_guard.analyze()` already runs today, and required by the performance budget (§8).
- **Not a collection of independent filters.** This is the specific failure mode founder review
  named directly: *PromptGuard → AI Governance → ResponseGuard → Audit as four unrelated systems
  doing similar things* would be worse than not building this Program at all — more duplication,
  more bugs, more attack surface. Every stage below funnels into one Decision Engine; nothing in
  this pipeline is allowed to make its own independent allow/deny call.

### 1.1 The Untrusted Provider Principle

**Mental model shift, required by founder review, made an explicit architectural invariant rather
than an aside:** think `User → AI Governance Layer → LLM Provider`, never `User → LLM`. Every
external LLM vendor — OpenAI today, Anthropic or a local/on-prem model tomorrow — is an
**untrusted, swappable Provider** (Blueprint Principle 7). No feature code holds a privileged
relationship with any one vendor; the Decision Engine's verdict is what reaches a provider, and
every provider is symmetric from the Governance Layer's point of view.

**Concrete implication for the existing chokepoint, stated honestly rather than glossed over — and
corrected in Revision 7 after the red-team review found the original framing incomplete:**
`_patch_prompt_guard()` patches OpenAI SDK's specific `Completions`/`AsyncCompletions` classes
(`shared/ai_client.py:130-133`) — this is a **provider-specific** structural guarantee, proven for
exactly one vendor, **and, Revision 7's correction, for exactly one API surface (chat
completions).** Revision 6 asked "what happens when a *second vendor* is added" and answered it
well; it did not ask "what happens when the *same* vendor is reached through a *different* API
surface" — and verification against the current codebase found the answer was "nothing governs
it," for three surfaces already live in production. **The chokepoint problem is two-dimensional
(vendor × surface), not one-dimensional (vendor only).**

| API surface | Live call sites today (verified) | Content carried | v1 mechanism |
|---|---|---|---|
| **Chat completions** | `shared/ai_client.py`'s existing patch, ~130 sites, 53 files | Text (case documents, prompts) | **Unchanged** — SEC-003, already governed |
| **Embeddings — raw SDK** | `routers/knowledge_base.py:55`, `routers/law_upload.py:83`, `routers/batch_ingest.py:54`, `routers/auto_discovery.py:163`, `routers/proof.py:100` | Text (real strings, direct SDK input) | **New chokepoint, same technique**: patch `openai.resources.embeddings.Embeddings.create`/`AsyncEmbeddings.create` (verified exist). `input` at this point is genuinely text — full Classification/Risk/Policy/Decision applies exactly as for chat |
| **Embeddings — LangChain-mediated** *(split out, Revision 8 — fixes red-team Item 1)* | `uploaded_doc/ingest.py:30-31` (client-document ingestion — the single highest-volume path found) via `langchain_openai.OpenAIEmbeddings`; same pattern in `app/services/retrieve.py`, `drafting/playbook.py`, `interni_stavovi.py`, `api.py:2039,2114` | Text at the *caller's* level, but **NOT at `Embeddings.create`** | **Verified, Revision 7's original framing was wrong for this group specifically**: `OpenAIEmbeddings._get_len_safe_embeddings` (`check_embedding_ctx_length=True` by default) tokenizes text into integer token IDs before calling the SDK — by the time the `Embeddings.create` patch above would fire, `kwargs["input"]` is `list[list[int]]`, not text. Classifying tokens is meaningless; failing closed on every chunk of every upload would be product-breaking. **Fixed mechanism**: a *fifth* chokepoint, one layer above the OpenAI SDK — patch `langchain_openai.OpenAIEmbeddings.embed_documents`/`aembed_documents` at the class level (verified both exist, `texts: list[str]` parameter — real text, pre-tokenization). Same technique, same zero-call-site-change guarantee, applied where the content is still classifiable |
| **Audio — transcription (Whisper)** | `routers/voice.py:45` | Raw audio bytes (in), transcript (out) | **New chokepoint, same technique**: patch `openai.resources.audio.transcriptions.Transcriptions.create`/`AsyncTranscriptions.create` (verified exist). Classification/Risk operate on **context only** (predmet_id's own classification, feature type) pre-call — raw audio cannot be meaningfully content-classified before transcription without defeating the purpose of governing the call that produces the transcription. This is a disclosed, structural limitation of this surface, not an oversight |
| **Audio — speech (TTS)** | `routers/voice.py:52` | Text (in), audio (out) | **New chokepoint, same technique**: patch `openai.resources.audio.speech.Speech.create`/`AsyncSpeech.create` (verified exist). Input is text — full content-based Classification applies exactly as for chat |
| **Realtime API** | `services/voice_orchestrator.py:46`, a raw `websockets` connection to `wss://api.openai.com/v1/realtime` | Bidirectional audio + text + server-executed tool calls, for the duration of a session | **Cannot use option (a) or (b) — there is no SDK class to patch, no `openai.*` call at all.** See §1.1.1 |

**Decision for this spec: extend option (a)'s technique to chat, both embeddings paths, and both
audio endpoints — five chokepoints (Revision 8 splits embeddings into raw-SDK and LangChain-layer
variants, per the row above), one shared Decision Engine, still zero per-call-site changes within
the ~53+ files that call any of them.** This preserves the same low-regression-risk property
Revision 6 already established; it does not change the *mechanism*, only the count of resource
classes it is applied to. Option (b) (an internal `LLMProvider` abstraction) remains rejected for
the same reason as before — Revision 7 does not reopen that choice, it corrects the surface count
the choice was applied to.

### 1.1.1 The Realtime API: Session-Level Governance (NEW, Revision 7)

**Why this surface is structurally different, not just another chokepoint to add:** every other
surface in the table above is request/response — one governed decision per call, cleanly matching
this Program's two-call Decision Engine design (§4). The Realtime API is a long-lived, bidirectional
*session* — audio and text flow continuously in both directions, and the model can invoke
server-executed tools mid-session. There is exactly **one call site** in this codebase
(`services/voice_orchestrator.py`), not an unpredictable ~130 — the entire reason a monkeypatch
chokepoint was necessary elsewhere (structural coverage independent of how many call sites exist,
because there are too many to trust individually) does not apply here. A single, deliberate,
reviewed integration at this one site is not "per-feature-module integration" in the sense §1
forbids — that principle exists to prevent 130 individually-fallible opt-in call sites, not to
forbid the one place a genuinely unique protocol is handled.

**Design: govern the session at its start, not per-message.** `VoiceOrchestratorSession.start()`
(`services/voice_orchestrator.py:67-69`) is the single point where the upstream connection is
established, before any audio/text/tool-call traffic flows. Classification/Risk Scoring/Policy
Lookup/Decision Engine run **once per session**, using `RequesterContext` (the predmet_id's own
classification, `feature="voice_realtime"`) — not per-utterance content, since utterances haven't
happened yet at connection time and a live voice conversation cannot tolerate per-turn governance
latency without perceptible lag. If the session-level Decision is `allow`/`anonymize`-class, the
connection proceeds and is audited as one session-scoped entry (§6a's `operation_id` maps to the
whole session, not one exchange); if `deny`/`escalate`, `start()` never opens the upstream
connection at all.

**Disclosed limitation, corrected and widened in Revision 8** (the targeted re-check found the
Revision 7 wording named only "utterances," while the actual largest content flow in this module
is server-originated, not microphone-originated): within an already-approved session, neither
individual spoken utterances **nor server-side tool-result content pushed back to the model
mid-session** are independently re-governed. Verified: `services/voice_orchestrator.py:180-189`
(`_send_tool_result`) transmits `json.dumps(result)` upstream for every tool call, and
`shared/voice_tools.py`'s read-only tools (e.g. `_tool_rag_pretraga`, draft-retrieval-shaped tools)
return real predmet content — case documents, generated drafts — read from Supabase, not spoken by
the attorney. The existing HITL confirmation (`shared/voice_tools.py`'s `mutates_data=True` gate,
`services/voice_orchestrator.py:14-18`) covers *write* actions only; it does not gate what a
*read-only* tool result contains before that content leaves to OpenAI as part of the model's
context. This trades per-exchange granularity (both directions) for operational feasibility — a
live bidirectional session cannot re-run Classification/Risk/Policy per tool call without the same
latency problem session-level governance exists to avoid. This is an accepted v1 scope limit,
stated for what it actually covers now, not an oversight papered over by an incomplete disclosure:
if voice becomes a higher-risk surface than it is today, per-exchange governance of tool-result
content specifically (not just utterances) would be the natural, separately-scoped follow-on.

### 1.2 The Escalation-Only Invariant (NEW, Revision 5 — now also a Blueprint-level principle)

**Wherever Policy declares a floor, Risk Scoring (and Anomaly Detection) may only push the
*effective* requirement above that floor for a given instance — never below it.** Formally:

```
effective_requirement = max(policy_floor, risk_derived_requirement)
```

This already governed both places a floor exists in this spec since earlier revisions —
`PolicyRequirements.minimum_action` (Revision 2: *"Decision Engine may escalate further but not
go below this floor"*) and `PolicyRequirements.minimum_audit_requirement` (Revision 4, §7.2) — the
`max()` in both was already escalation-only by construction. **What Revision 5 changes is status,
not mechanism**: this is no longer an incidental property of how two formulas happened to be
written — it is a **named, structural invariant `DecisionEngine` must enforce for every floor it
consumes**, present and future, and it is now stated once in the Blueprint itself (Principle 1,
Default Deny) rather than only implied by this Program's code.

**Why this is a security rule, not an AI-tuning one — the founder's own example, preserved
precisely:** a translation feature's Policy floor might reasonably be OPTIONAL audit for the
ordinary case. If a specific document processed by that same feature happens to be
attorney-client privileged, GDPR-relevant, and court-related — Risk Scoring computing a high score
for *that instance* — Policy's feature-level floor must not silently continue to govern. Were
Policy treated as an absolute ceiling rather than a floor, an audit outage on that specific,
unusually sensitive translation would let it proceed ungoverned, exactly the failure mode this
entire Program exists to prevent. Escalation-only means the instance-specific risk signal can
raise the bar past the feature's ordinary-case floor; it can never lower a floor Policy has
already set.

**What this explicitly forbids, stated as a negative for clarity:** `DecisionEngine` must never
compute an effective requirement (audit tier, action severity, or any future floor-governed
value) that is *less* protective than what Policy declared for that classification/feature. A
future implementation detail that accidentally allowed Risk Scoring to average with, rather than
maximize against, a Policy floor would violate this invariant even if no single test caught it —
worth a dedicated implementation-time assertion, not just documentation, per §9.

### 1.3 Extensibility: What Adding a New Risk Signal Actually Costs (NEW, Revision 6)

**Founder's pre-Stage-5 question, answered directly: partially yes, deliberately not fully.**
Three separate things change when a new risk signal (e.g. `MERGER_DOCUMENT`,
`CRIMINAL_INVESTIGATION`, `STATE_SECRET`) is added a year from now, and they have different costs:

| What changes | Cost | Why |
|---|---|---|
| **What a factor requires** (its minimum `AuditRequirement`, e.g. "STATE_SECRET → MANDATORY") | **Config only.** A new declarative Policy rule, versioned via `policy_version` like every other rule. Zero change to `DecisionEngine`, the audit schema, or replay logic — all three already operate on "whatever `PolicyRequirements.minimum_audit_requirement` says," generically | This is the piece that actually drives decision behavior, and it is the piece the founder's question was really asking about — this part *is* fully data-driven |
| **The `RiskFactor` vocabulary itself** (adding `STATE_SECRET` as a recognized value) | **A registered code addition** — extending the `RiskFactor` enum, one line | Deliberately not runtime-dynamic, and not an oversight: this project already has a proven, named failure mode for the opposite choice — `AUDITABLE_ACTIONS` (`shared/audit_immutable.py:56-81`) is a hardcoded allow-list *specifically* so a new security-relevant category can't silently exist without someone deliberately registering it. A fully dynamic vocabulary (any string becomes a valid factor with no review) would satisfy "extensible" while violating the Blueprint's own closing rule against ungoverned security scope creep — worse, not better |
| **Detecting the new factor in real content** (how `ClassificationService`/`RiskScoringService` decides *this* document is `STATE_SECRET`) | **Feature-specific implementation work**, inherently — no architecture eliminates the need to actually write the detection logic for a genuinely new category | Not a design gap; this is true of any classification system, named here so it isn't mistaken for something this spec should have solved |

**The honest summary the founder asked for:** the *decision-making core* (Decision Engine, audit
schema, replay logic) is monotonically extensible — it never changes shape when a new factor is
added, by construction, because it consumes `PolicyRequirements`/`RiskScore` generically rather
than switching on specific factor values. The *vocabulary and detection logic* are not, and
should not be, zero-review additions — that boundary is exactly where this Blueprint's governing
rule (*"Nijedna nova bezbednosna funkcionalnost ne sme biti implementirana zato što je 'dobra
ideja'"*) is supposed to bite. An architecture that let both halves be silently, dynamically
extensible would be more "flexible" and a materially worse security posture.

### 1.4 The Sync/Async Governance Split (NEW, Revision 8 — fixes red-team Item 2)

**The gap, precisely:** `shared/ai_client.py` patches two entry points — `Completions.create`
(`_guarded_create`, a plain `def`) and `AsyncCompletions.create` (`_guarded_acreate`, `async def`).
Every service this spec defines through Revision 7 (`ClassificationService.classify`,
`RiskScoringService.score`, `AuditService.log_decision`) is declared `async def`. That is workable
inside `_guarded_acreate`; it is not directly callable from inside `_guarded_create`'s synchronous
frame without either blocking the caller's own thread on an event loop that may not exist there,
or bridging across threads into one that does. Verified: **46 synchronous call sites versus 24
awaited ones** across this codebase's OpenAI usage — the sync chokepoint is not a rare edge case,
it is the majority path.

**Alternative considered and rejected — a thread-safe bridge into the main event loop**
(`asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=...)` from inside `_guarded_create`).
Rejected on all four of the founder's required questions:
- **Deadlock risk**: real. The call blocks the current thread waiting on a loop running
  elsewhere; if that loop is itself busy (a plausible, not exotic, condition under load), the wait
  has no natural bound tied to this operation's own cost.
- **Timeout behavior**: has to be built by hand across a thread boundary — `.result(timeout=...)`
  raises on expiry, but the *coroutine already scheduled on the other loop* keeps running
  regardless, an orphaned task with no defined cleanup.
- **No event loop active**: fails outright — there may be no accessible running loop from a
  worker thread context (e.g. a script, a Celery-style background job, `asyncio.to_thread`'s own
  worker), and the bridge has nothing to attach to.
- **Simpler design available**: yes — see below.

**Chosen fix, verified to already exist in this codebase rather than invented for this spec:**
`shared/audit_immutable.py` already ships `log_action_sync()` (`:112-127`) alongside `log_action()`
— identical `Optional[str]` durable-ACK return, identical `_build_and_insert` call underneath,
zero `asyncio` involvement, correct today, simply unused by any current call site. **Every
Governance service in §6 gets the same split**, not a bridge: a `*_sync` method pair for
`ClassificationService`, `RiskScoringService`, `AuditService` (the two already-synchronous
`PolicyService.evaluate`/`DecisionEngine.decide_request`/`decide_response` need no change — they
were never `async` in the first place, per §6's original design). `GovernanceService` itself
correspondingly needs a `govern_request_sync`/`govern_request` pair — `_guarded_create` calls the
former, `_guarded_acreate` the latter, each calling only same-discipline dependencies throughout,
never crossing between them.

**Named, bounded residual, not hidden:** the sync path's blocking behavior (classification, risk
scoring, and — for REQUIRED/MANDATORY — the durable audit write, all synchronous) sits on the
*same* thread that already blocks for the sync OpenAI HTTP call itself, which this codebase already
accepts as safe specifically because Starlette dispatches synchronous route handlers to its own
worker threadpool rather than the main event loop. This fix does not introduce a new blocking-code
risk class; it adds a small, bounded increment (§8) to a blocking pattern this codebase already
relies on being safe. It does mean a sync call site invoked incorrectly from *inside* an `async
def` handler without `run_in_threadpool`/`asyncio.to_thread` would compound an existing latent bug
with this Program's own added latency — a pre-existing risk this Program inherits, not one it
creates, and out of scope for this specification to fix.

---

## 2. Trust Boundaries

```
 Browser (Supabase Auth JWT obtained client-side — outside this backend's control)
    │
    │  HTTPS + bearer token
    ▼
 Frontend (static/vindex.js — untrusted input origin; SEC-036 hardened)
    │
    │  ── TRUST BOUNDARY 1 — API Authentication ──
    │     shared/deps.py::get_current_user / verify_token_local
    ▼
 API / Router layer (api.py, routers/*.py)
    │     Program 3's domain: ownership/entitlement resolved HERE, before
    │     this Program ever runs — "who is asking" is not re-derived below.
    │
    │  ── TRUST BOUNDARY 2 — Feature logic constructs the AI call ──
    │     (routers/case_dna.py, routers/drafting.py, app/services/retrieve.py, ...
    │      build `messages` — unchanged, zero edits needed)
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AI GOVERNANCE LAYER — request path                                     │
│                                                                           │
│  Classification ──► Risk Scoring ──► Policy Lookup ──► DECISION ENGINE  │
│  (Data Classification    (per-operation      (declarative      (call #1) │
│   Engine, Program 2)      score, NEW)          rules, NEW)               │
│                                                     │                     │
│              ┌──────────────────────────────────────┴──────────────┐    │
│              ▼ ALLOW/ANONYMIZE/MASK/LOCAL_MODEL      ▼ DENY/ESCALATE/RETRY │
│         [Audit Gate — REQUIRED/MANDATORY only,    exit → Audit → return  │
│          durable ACK required, §7.3 — NEW Rev.7]                         │
│              ▼ ACK'd (or n/a for OPTIONAL/RECOMMENDED)                   │
│         Transformation (executes verdict)                                │
│              ▼                                                           │
│         Prompt Firewall (existing prompt_guard.analyze, SEC-003,        │
│                           unchanged — always runs, defense-in-depth      │
│                           even after Decision Engine already allowed)   │
│              ▼ BLOCKED → exit → Audit → return                          │
│         Routing (executes provider/model choice)                        │
└─────────────────────────────────────────────────────────────────────────┘
    │
    │  ── TRUST BOUNDARY 3 — External vendor boundary (§1.1) ──
    │     Blueprint Principle 7: "AI Is Untrusted." The ONLY boundary where
    │     trust genuinely changes from Vindex-controlled to vendor-controlled.
    ▼
 LLM Provider (today: OpenAI; architecturally swappable, §1.1)
    │
    │  response returns
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AI GOVERNANCE LAYER — response path (NEW — no equivalent chokepoint     │
│  hook exists today; _guarded_create/_guarded_acreate only guard the      │
│  outbound request)                                                       │
│                                                                           │
│  Response Firewall ──► DECISION ENGINE (call #2) ──► Audit               │
│  (validates: citation/                APPROVE / ESCALATE /               │
│   completeness checks,                RETRY / BLOCK                      │
│   quality_gate + genome_validator                                        │
│   logic, generalized)                                                    │
└─────────────────────────────────────────────────────────────────────────┘
    │  (only if APPROVE)
    ▼
 Feature logic resumes (Genome/Draft/RAG consume the validated response)
    │
    ▼
 Downstream consumers (case_dna data model, Cockpit, Health Index, UI)
```

**Explicit, disclosed limitation this Program inherits and does not fix:** none of Trust Boundary
1 or 2 is independently enforced at the database layer — `SUPABASE_SERVICE_KEY` bypasses RLS
entirely (SEC-004). The Governance Layer's own path is likewise app-layer-only by construction
(Python code in-process, not a database policy) — consistent with the rest of this codebase, not
a new gap. This Program's guarantees are exactly as strong as "the code runs correctly," same as
every other control in this system today.

**New operational risk this design deliberately accepts, named rather than hidden:** the Decision
Engine is now the single point every governed call passes through twice. Centralizing the
decision — the entire point of this Program, per founder review — also means the Decision
Engine's own reliability becomes the system's tightest bottleneck. §7 treats this explicitly
rather than assuming centralization is free.

---

## 3. Data Flow

The **AI Governance Layer begins at Classification** — this is the founder's first required
condition, made structural: Classification is unambiguously the first stage of *this* pipeline
(Upload/OCR remain pre-governance document-ingestion stages, unaffected). Mapped onto Vindex's
real code:

| Stage | Today | This Program |
|---|---|---|
| Upload / OCR | `routers/dokument.py`, `uploaded_doc/extractor.py`, SEC-007-hardened | Unchanged — precedes Governance |
| ═══ *AI Governance Layer begins here* ═══ | | |
| **1. Classification** | `main.py::_skini_pii` (`main.py:1036-1045`) — regex-only, numeric identifiers, called at exactly 4 sites, not called on the Genome path at all (SEC-006) | **Data Classification Engine (Program 2).** Assigns sensitivity tier(s) + PII-type tags per outbound content unit. `_skini_pii`'s numeric-identifier detection becomes one input into a broader classification, not a separate preceding stage — PII tags are an *output* of Classification, not a thing checked before it |
| **2. Risk Scoring** | Does not exist | **NEW, per-operation.** Quantifies *this specific call's* risk (0-100) from [classification tiers, requested action's scope/verb, data volume, provider trust level] — e.g. "analyze this contract" scores low; "draft a lawsuit using the entire case file plus all PII" scores high, even at the same classification tier, because the *action* differs. Deliberately distinct from Risk/Anomaly Detection below — this is per-call content risk, not cross-call behavioral pattern |
| **3. Policy Lookup** | Does not exist (Blueprint Cap 4's core gap) | **Declarative rules only** — e.g. "IF tier=PRIVILEGED AND provider=external THEN require=anonymize"; "IF feature=court_submission THEN require=human_approval." Returns *what the rules require*, not a final verdict — that distinction is new in this revision (§6) |
| **4. Decision Engine (call #1)** | Does not exist | **The sole authority for the final verdict.** Consumes Risk Score + Policy requirements + Classification, outputs one of ALLOW / DENY / ANONYMIZE / MASK / ESCALATE / LOCAL_MODEL / RETRY (§6), including `audit_requirement`. On DENY/ESCALATE/RETRY, the pipeline exits here (to Audit, then returns to the caller) |
| **4a. Audit Gate (request)** *(NEW, Revision 7 — fixes red-team Critical 2)* | Does not exist | **REQUIRED/MANDATORY only**: `await AuditService.log_decision(...)` directly (§7.3) — a durable ACK (real id) is required before proceeding to stage 5; no ACK → escalate (REQUIRED) / deny (MANDATORY). **OPTIONAL/RECOMMENDED**: fire-and-forget, proceed immediately — this stage is a no-op delay for the large majority of calls |
| **5. Transformation** | `_skini_pii` (numeric-only) + `prompt_guard.wrap_for_ai()` (message isolation) | Executes whatever Decision Engine required (ANONYMIZE/MASK) — extended to cover names/addresses, closing SEC-006 as a byproduct, not a separate project |
| **6. Prompt Firewall** | `security/prompt_guard.py::analyze()`, SEC-003 | **Unchanged, reused as-is**, always runs — defense-in-depth even when Decision Engine already allowed. It catches a different signal (literal injection patterns in text) than Risk Scoring/Policy (data sensitivity + intent) |
| **7. Routing** | Implicit — call-site convention picks `gpt-4o` vs `gpt-4o-mini` | Executes Decision Engine's provider/model choice (§1.1) — pass-through for chat/embeddings/audio in the common case today; session-scoped for the Realtime API (§1.1.1) |
| **LLM call** | `_orig_create`/`_orig_acreate` (chat) — plus the three new chokepoints per §1.1 (embeddings, transcription, speech) | Unchanged mechanism, more resource classes patched |
| **8. Response Firewall** | Two narrow precedents: `services/quality_gate.py` (drafting only), `shared/genome_validator.py` (Genome only) | Generalizes both — runs citation/completeness validation internally (no separate "Validation" stage; validation *is* how Response Firewall reaches its verdict) |
| **9. Decision Engine (call #2)** | Does not exist | Given Response Firewall's verdict **plus policy/risk (NEW, Revision 7 — fixes red-team High 3)**, outputs APPROVE / ESCALATE / RETRY / BLOCK and its own `audit_requirement`, which may escalate relative to call #1's but never fall below it. Same component as call #1, narrower response-side vocabulary (ANONYMIZE/LOCAL_MODEL are request-side-only concepts, not reused here) |
| **9a. Audit Gate (response)** *(NEW, Revision 7)* | Does not exist | Same durable-ACK discipline as stage 4a, gated on call #2's own `audit_requirement` — before the response is released to feature code, not after |
| **10. Audit** | `shared/audit_immutable.py::log_action` (`shared/audit_immutable.py:86`) | Extended (Program 4) to log every Decision Engine verdict — both calls, every branch. For OPTIONAL/RECOMMENDED this is the only audit step (fire-and-forget, post-hoc); for REQUIRED/MANDATORY the durable write already happened at stage 4a/9a — this final entry is the same write, not a second one |

---

## 4. State Machine

**Per outbound LLM call** (not per document — one document can trigger many calls, e.g. Genome's
multi-document extraction budget).

```
RAW ──► CLASSIFIED ──► RISK_SCORED ──► POLICY_CHECKED ──► DECIDED ──┬──► [AUDIT_ACK_PENDING ──► AUDIT_ACKED]* ──► TRANSFORMED ──► GUARD_CHECKED ──► ROUTED ──► SENT
                                                                      │
                                                                      ├──► DENIED ─────────────────────────► AUDITED (terminal)
                                                                      ├──► ESCALATED ──► (human, out-of-band) ──► AUDITED
                                                                      └──► RETRY_REQUESTED ──► back to RAW (bounded, §7)

SENT ──► RESPONSE_RECEIVED ──► FIREWALL_CHECKED ──► DECIDED (2nd) ──┬──► [AUDIT_ACK_PENDING ──► AUDIT_ACKED]* ──► APPROVED ──► AUDITED (terminal, feature logic resumes)
                                                                      ├──► ESCALATED ──► (human, out-of-band) ──► AUDITED
                                                                      ├──► RETRY_REQUESTED ──► back to RAW (bounded, §7)
                                                                      └──► BLOCKED ─────────────────────────► AUDITED (terminal)

* AUDIT_ACK_PENDING/AUDIT_ACKED (NEW, Revision 7, fixes red-team Critical 2 — §7.3): present in the
  state sequence ONLY for REQUIRED/MANDATORY audit_requirement. For OPTIONAL/RECOMMENDED, DECIDED
  transitions directly to TRANSFORMED/APPROVED — the audit write still happens (fire-and-forget)
  but is not itself a gating state. AUDIT_ACK_PENDING with no ACK received is itself a branch: for
  REQUIRED it becomes ESCALATED; for MANDATORY it becomes DENIED/BLOCKED — not a distinct terminal
  state of its own, reusing the same terminal states the table above already defines.
```

**ESCALATED is not terminal — it is suspended**, pending an out-of-band human decision (Blueprint
Goal 6, Human Authority). The eventual human resolution (approved/rejected) is itself a required
`audit_immutable` entry — an escalation that is never resolved is a forensic gap, not a completed
governance cycle. This coupling (Decision Engine ⟷ Audit for both the escalation *and* its
resolution) did not exist in Revision 1 and is required by the richer vocabulary in §6.

**Deviations from the founder's originally proposed state list, stated explicitly per Blueprint
Principle 10:** dropped **SECURED** (no distinct Vindex stage between CLASSIFIED and
POLICY_CHECKED beyond RISK_SCORED, now made explicit); renamed **ARCHIVED → AUDITED**
(`audit_immutable` is a tamper-evident log, not archival/cold-storage — that term is already used
elsewhere for a different concept, `services/retention_service.py`). **APPROVED** is retained in
Revision 2 (dropped in Revision 1) because it now names a real, distinct Decision Engine outcome
on the response path, not a redundant restatement of GUARD_CHECKED as it did before.

---

## 5. Capability Map

| Capability | Status | Vindex mapping |
|---|---|---|
| **Data Classification Engine** | NEW (Program 2, spec'd here as a consumed contract — §6) | No existing equivalent beyond `_skini_pii`'s narrow numeric-PII regex |
| **Risk Scoring Engine** | NEW | Per-operation, content+intent-based. No existing equivalent — this is the founder review's second required addition |
| **Policy Engine** | NEW, narrowed scope | Declarative rule repository/lookup only (§3 stage 3) — does *not* emit the final verdict, corrected from Revision 1 |
| **Decision Engine** | NEW — **the brain**, sole authority for verdicts | No existing equivalent. This is the component whose absence made Revision 1 "a firewall, not governance," per founder review |
| **Prompt Firewall** | EXISTING, reused unchanged | `security/prompt_guard.py` (SEC-003) |
| **Response Firewall** | NEW, generalizes 2 existing narrow precedents | `services/quality_gate.py` (drafting), `shared/genome_validator.py` (Genome) |
| **Transformation Engine** | PARTIALLY EXISTING, unify + extend | `main.py::_skini_pii` (numeric only) + `prompt_guard.wrap_for_ai()` — extending to names/addresses closes SEC-006 as a byproduct |
| **Routing Engine** | NEW, currently trivial execution, real decision point | No existing decision point — call sites hardcode model choice today. Executes Decision Engine's LOCAL_MODEL/provider choice (§1.1) |
| **Anomaly Detection** (renamed from "Risk Engine" in Revision 1, to stop conflating it with Risk Scoring above) | PARTIALLY EXISTING, extend | `security/anomaly_detection.py` — cross-request behavioral abuse patterns over time, recently revived from being fully dead since inception (SEC-005 round 2). Feeds signals *into* the Decision Engine's Risk Scoring input, does not itself decide anything |
| **Audit** | EXISTING, extended (Program 4) | `shared/audit_immutable.py` — now must log both Decision Engine calls per governed request, plus escalation resolutions |

---

## 6. Interfaces (contracts only — no implementation)

Signatures and docstrings only. **Not for implementation until this document reaches Finding
Lifecycle stage 5 (§9).**

```python
# --- Shared value types -----------------------------------------------------

class SensitivityTier(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CLIENT_CONFIDENTIAL = "client_confidential"
    PRIVILEGED = "privileged"          # attorney-client privileged content

@dataclass
class ClassificationResult:
    tiers: list[SensitivityTier]
    pii_tags: list[str]                # e.g. ["jmbg", "name", "address"]
    confidence: float
    source: str                        # which classifier/rule produced this — for audit

@dataclass
class RequesterContext:
    user_id: str
    predmet_id: str | None
    feature: str                       # e.g. "case_dna.refresh", "drafting.nacrt"
    requested_action: str              # e.g. "analyze", "draft_submission" — NEW in Revision 2,
                                        # Risk Scoring needs this; Classification alone can't
                                        # distinguish "analyze this contract" from "draft a
                                        # lawsuit using the entire case file"
    # Deliberately NOT re-deriving ownership here — already-resolved output of
    # Program 3's Trust Boundary 1/2, passed through, not recomputed.

class RiskFactor(str, Enum):
    """NEW in Revision 5 — tightened from a free-form list[str]. The field
    itself (contributing_factors) already existed since Revision 2/3; this
    only replaces its type. Ad hoc strings ("tier:privileged" in one
    implementation, "PRIVILEGED_TIER" in another) would defeat the exact
    forensic-reconstruction purpose this field exists for — a controlled
    vocabulary, registered here, is required, same discipline as
    AUDITABLE_ACTIONS's registration requirement (§6a). Extensible, but
    every new value must be added here, not invented ad hoc at a call
    site."""
    PRIVILEGED_CONTENT = "privileged_content"
    PERSONAL_DATA = "personal_data"
    COURT_DOCUMENT = "court_document"
    GDPR_RELEVANT = "gdpr_relevant"
    EXTERNAL_PROVIDER = "external_provider"
    FULL_CASE_EXPORT = "full_case_export"
    HIGH_DATA_VOLUME = "high_data_volume"
    FINANCIAL_DATA = "financial_data"
    MEDICAL_DATA = "medical_data"
    TRADE_SECRET = "trade_secret"

@dataclass
class RiskScore:
    value: int                         # 0-100
    contributing_factors: list[RiskFactor]  # e.g. [PRIVILEGED_CONTENT, GDPR_RELEVANT,
                                        # EXTERNAL_PROVIDER] — tightened Revision 5, was list[str].
                                        # This is what makes a score explainable 6 months later:
                                        # "87" alone is not forensically reconstructible; "87
                                        # because PRIVILEGED_CONTENT + GDPR_RELEVANT +
                                        # EXTERNAL_PROVIDER" is
    confidence: float

class AuditRequirement(str, Enum):
    """NEW in Revision 4 — fixes the founder's blocking issue on Revision 3:
    a single global 'Audit unavailable -> allow' default treats a contract
    summary and a court-submission draft identically, which is wrong.
    Determined as max(policy-declared floor, risk-derived tier) — see
    PolicyRequirements.minimum_audit_requirement and §7.1's derivation."""
    OPTIONAL = "optional"          # e.g. translation, summary, style rewrite, explain-a-law
    RECOMMENDED = "recommended"    # everyday case-specific AI use below the REQUIRED floor
    REQUIRED = "required"          # e.g. full-case analysis, drafting using case-wide context
    MANDATORY = "mandatory"        # e.g. court submissions, GDPR export, PRIVILEGED-tier content
                                    # sent to an external provider — no exceptions, ever

@dataclass
class PolicyRequirements:
    """Revision 2: what Policy says is REQUIRED, not the final verdict —
    that distinction is the fix for Revision 1's core gap."""
    applicable_rule_ids: list[str]
    required_transformations: list[str]
    minimum_action: str | None         # a floor the rule set demands, e.g. a rule that says
                                        # "court_submission always needs human approval" —
                                        # Decision Engine may escalate further but not go
                                        # below this floor
    minimum_audit_requirement: AuditRequirement    # NEW, Revision 4 — a declared floor per
                                        # feature/classification, e.g. "PRIVILEGED tier ->
                                        # MANDATORY" regardless of what Risk Scoring computes for
                                        # a given instance; Decision Engine takes
                                        # max(this, risk-derived tier), never below this floor
    policy_version: str                # NEW, Revision 4 — e.g. "2026.08.01.1". Pinned at
                                        # evaluation time, carried into Decision and the audit
                                        # payload (§6a) so "which rules were in effect when this
                                        # decision was made" is answerable a year later without
                                        # depending on the live (mutable, evolving) rule set

@dataclass
class Decision:
    """The ONLY type any component in this pipeline is allowed to treat as
    authoritative. Emitted exclusively by DecisionEngine."""
    action: Literal[
        "allow", "deny", "anonymize", "mask",
        "escalate", "local_model", "retry",           # request-side vocabulary
        "approve", "block",                             # response-side additions
    ]
    reason: str                        # mandatory — Blueprint Principle 9, Explain Before Execute
    risk_score: int
    policy_rule_ids: list[str]         # which rules contributed — for audit and for debugging
    policy_version: str                # NEW, Revision 4 — carried through from PolicyRequirements
    audit_requirement: AuditRequirement  # NEW, Revision 4 — recorded even when Audit itself is
                                        # what's unavailable (§7.1), since the requirement tier is
                                        # computed BEFORE the audit-write attempt, not after
    required_transformations: list[str]

@dataclass
class ModelTarget:
    vendor: str                        # "openai" today; extensible per §1.1
    model: str
    reason: str

@dataclass
class ResponseVerdict:
    """Response Firewall's own output — an INPUT to Decision Engine's 2nd
    call, not itself a final decision (mirrors the Policy/Decision split)."""
    quality_flags: list[str]
    confidence_score: float | None     # reuses quality_gate's existing scale
    detail: dict                       # citation checks, completeness checks, etc.


# --- Service contracts --------------------------------------------------------

class ClassificationService(Protocol):
    """The Data Classification Engine, Program 2."""
    async def classify(self, content: str, context: RequesterContext) -> ClassificationResult:
        """Must complete within §8's budget. Must NOT raise on ambiguous
        content — return the most conservative (highest-sensitivity) tier
        with low confidence instead (fail closed by defaulting to the
        safest classification, not by raising)."""
    def classify_sync(self, content: str, context: RequesterContext) -> ClassificationResult:
        """NEW, Revision 8 (§1.4, fixes red-team Item 2) — for the
        synchronous chokepoint (`_guarded_create`). Same contract as
        `classify`, no `asyncio` involved, callable from a plain `def`.
        Not a wrapper around `classify` via `asyncio.run()` — a genuinely
        separate synchronous implementation path, mirroring
        `shared/audit_immutable.py`'s own `log_action`/`log_action_sync`
        split, which this codebase already uses for exactly this reason."""

class RiskScoringService(Protocol):
    """NEW in Revision 2. Distinct from AnomalyDetectionService below —
    this scores ONE operation; anomaly detection watches patterns across
    many operations over time. Both feed the Decision Engine, neither
    decides on its own."""
    async def score(
        self, classification: ClassificationResult, context: RequesterContext,
    ) -> RiskScore:
        """Core scoring (classification tiers, requested-action scope, data
        volume) is in-process, no network call. FIXED, Revision 7 — red-team
        found this contract directly contradicted
        AnomalyDetectionService.current_risk_modifier() below, which §5
        already says feeds INTO this score and which the real
        security/anomaly_detection.py implements via a live Supabase RPC
        (_check_db_profile). Resolution: the behavioral modifier is
        incorporated ONLY on a best-effort, tightly-timeout-bounded basis
        (see current_risk_modifier's own docstring) — if it doesn't return
        within that budget, score() proceeds without it rather than waiting
        or failing. The 'no network call' property therefore describes this
        method's OWN logic, not a guarantee that nothing it calls ever does
        I/O — stated precisely so the two don't read as contradictory
        again. Errors in the core scoring itself default to the maximum
        score (100) — an unscoreable operation is treated as maximally
        risky, not as risk-free."""
    def score_sync(
        self, classification: ClassificationResult, context: RequesterContext,
    ) -> RiskScore:
        """NEW, Revision 8 (§1.4) — synchronous counterpart for the sync
        chokepoint. Calls `AnomalyDetectionService.current_risk_modifier_sync`
        (not the async version) under the same timeout-bounded, best-effort
        discipline as `score()`."""

class PolicyService(Protocol):
    """Declarative rule lookup ONLY — does not decide. Renamed scope from
    Revision 1, where this incorrectly doubled as the decision-maker."""
    def evaluate(
        self, classification: ClassificationResult, risk: RiskScore, context: RequesterContext,
    ) -> PolicyRequirements:
        """An unrecognized feature/data combination MUST still return a
        PolicyRequirements with minimum_action='deny' — default-deny per
        Blueprint Principle 1. The absence of a rule is itself a result,
        never silence. The rule set itself MUST be versioned (NEW, Revision
        4) — every evaluation pins the version active at call time into
        the returned PolicyRequirements.policy_version; a rule-set change
        does not retroactively alter what a past decision is understood to
        have been based on.

        Rules match on TWO independent axes (NEW, Revision 6) — both fold
        into the same minimum_audit_requirement/minimum_action floor:
        (1) feature/classification rules, e.g. "court_submission -> REQUIRED
        approval"; (2) risk.contributing_factors rules, e.g.
        "PRIVILEGED_CONTENT present -> minimum REQUIRED audit" regardless
        of the numeric risk.value — this is how a low score cannot silently
        under-classify a specifically named sensitive factor (§7.2). Both
        axes are ordinary declarative rules, both versioned identically —
        this is not two separate mechanisms, just two kinds of match
        condition over the same rule set."""

    def evaluate_response(
        self, verdict: ResponseVerdict, context: RequesterContext,
    ) -> PolicyRequirements:
        """NEW, Revision 8 — fixes red-team Item 3 (the targeted re-check
        proved decide_response's Revision 7 `policy`/`risk` parameters were
        a dead parameter: §7.2's formula has no term that reads `verdict`,
        so re-passing the request-side PolicyRequirements/RiskScore
        unchanged could never let a response finding escalate anything).

        Declarative rules matching on verdict.quality_flags/confidence_score
        — e.g. 'fabricated_citation flag present -> minimum REQUIRED',
        'third_party_pii_detected flag present -> minimum MANDATORY',
        'confidence_score < 0.3 -> minimum REQUIRED'. Same versioned rule
        set as evaluate() above, same policy_version — this is a second
        entry point into ONE rule engine, not a second mechanism. This is
        what makes decide_response's escalation claim actually true: it now
        has a live input, freshly computed from the response itself, that
        can push minimum_audit_requirement past whatever the request-side
        floor was, exactly the way risk.contributing_factors already does
        for evaluate() on the request side (Revision 6's precedent, reused
        rather than reinvented)."""

class AnomalyDetectionService(Protocol):
    """Renamed from 'RiskService' in Revision 1 to stop conflating this
    with RiskScoringService above. Extends security/anomaly_detection.py."""
    async def record_signal(self, signal_type: str, context: RequesterContext) -> None:
        """Fire-and-forget. Signal types: repeated_policy_denial,
        unusual_sensitivity_access, response_firewall_block_spike."""
    async def current_risk_modifier(self, context: RequesterContext) -> float:
        """A behavioral multiplier RiskScoringService may fold in — e.g. a
        user with 5 recent policy denials scores higher on their 6th
        attempt even if the content itself looks identical to their 1st.
        TIGHTENED, Revision 7: this method performs real I/O (a Supabase
        RPC in the current security/anomaly_detection.py implementation) —
        RiskScoringService.score() MUST call it with a short, fixed timeout
        (implementation-time budget, calibrated against §8) and treat a
        timeout or any exception as 'no modifier available' (contributes 0,
        proceeds without it), never as a reason to fail or delay the whole
        score(). This is a soft, best-effort signal by design — it degrades
        the *quality* of a risk score, not the *availability* of one."""
    def current_risk_modifier_sync(self, context: RequesterContext) -> float:
        """NEW, Revision 8 (§1.4) — synchronous counterpart, same
        timeout/best-effort discipline, no `asyncio`. The real
        `security/anomaly_detection.py::_check_db_profile` this extends
        already runs its Supabase RPC via `asyncio.to_thread(...)` — a
        genuinely synchronous implementation of this method is at least as
        natural to write as the async one, not an awkward retrofit."""

class DecisionEngine(Protocol):
    """THE single authority for every governance verdict in this system.
    Invoked exactly twice per governed call — see §3, §4. No other
    component in this pipeline may emit an authoritative allow/deny/
    escalate/etc. Reused for every current and future LLM provider (§1.1).

    ESCALATION-ONLY INVARIANT (NEW, Revision 5, founder-mandated, now also
    a Blueprint principle — §1.2): for every floor Policy declares
    (minimum_action, minimum_audit_requirement), the effective value this
    method computes MUST equal max(policy_floor, risk_derived_value) —
    Risk may raise a floor for a specific instance, never lower one Policy
    already set. A future change that averaged, blended, or otherwise let
    a low risk score soften a Policy floor would violate this invariant.

    DETERMINISM REQUIREMENT (NEW, Revision 4, founder-mandated): given
    identical (classification, risk, policy, context) inputs AND the same
    policy.policy_version, decide_request MUST return an identical
    Decision — no hidden state, no wall-clock dependence, no randomness.
    This is precisely scoped, not absolute: it is REPLAY-deterministic
    given a pinned policy_version, not eternally deterministic across
    time — the policy rule set is expected to change (that is the entire
    point of Policy Versioning above). Without this property, §6a's audit
    payload cannot support its core forensic claim ('replaying these
    exact recorded inputs against this exact policy_version reproduces
    this exact decision') — a non-deterministic Decision Engine would
    make every past audit entry a claim that cannot actually be
    re-verified, only trusted.

    DURABLE AUDIT ACKNOWLEDGMENT REQUIREMENT (NEW, Revision 7, founder-
    mandated, fixes red-team Critical 2): a Decision with
    audit_requirement in {REQUIRED, MANDATORY} MUST NOT be acted upon
    (i.e., GovernanceService must not proceed to Transformation/Routing on
    the request path, or release the response to feature code on the
    response path) until AuditService.log_decision has been awaited
    directly (not fire-and-forget) and returned a durable acknowledgment
    (§6a, §7.3). No ACK for REQUIRED means escalate; no ACK for MANDATORY
    means deny. OPTIONAL/RECOMMENDED are unaffected — fire-and-forget
    remains correct for them."""

    def decide_request(
        self,
        classification: ClassificationResult,
        risk: RiskScore,
        policy: PolicyRequirements,
        context: RequesterContext,
    ) -> Decision:
        """Synchronous, in-process, no I/O (§8) — all inputs are already
        computed by the time this is called. Never returns an action
        outside the request-side vocabulary (§ Decision.action)."""

    def decide_response(
        self,
        verdict: ResponseVerdict,
        response_policy: PolicyRequirements,  # CORRECTED, Revision 8 — was `policy` (Revision 7),
                                               # the request-side object re-passed unchanged. That
                                               # was provably a dead parameter: §7.2's formula has
                                               # no term reading `verdict`, so re-passing call #1's
                                               # PolicyRequirements could never let anything
                                               # escalate. This MUST be the result of
                                               # PolicyService.evaluate_response(verdict, context)
                                               # — freshly computed FROM the response, not reused.
        risk: RiskScore,                      # unchanged, Revision 7
        original_decision: Decision,
        context: RequesterContext,
    ) -> Decision:
        """Second call, response path. Never raises — a failure here
        degrades to action='escalate' (human review), never silently to
        'approve' — this is the exact class of bug KNOWN_RELIABILITY_RISKS.md
        already found in verify_genome()'s fail-open path, being fixed here
        structurally rather than per-caller.

        CORRECTED, Revision 8 (fixes red-team Item 3, proven OPEN not merely
        PARTIALLY CLOSED): audit_requirement is now computed as
        max(response_policy.minimum_audit_requirement,
            score_derived_tier(risk.value),
            original_decision.audit_requirement)
        — three terms, not two. The first term is what actually changed:
        it is derived from `response_policy`, which is itself derived from
        `verdict` (via PolicyService.evaluate_response), so a fabricated-
        citation or unexpected-third-party-PII flag can now genuinely push
        past whatever the request scored. Revision 7's version of this
        formula had no term that depended on the response at all, which the
        targeted re-check proved mathematically — this correction is not a
        wording change, it is a different formula with a real new input.
        The Escalation-Only Invariant (§1.2) still governs all three terms:
        none may be averaged or bypassed, only maximized. Response-side
        vocabulary remains APPROVE/ESCALATE/RETRY/BLOCK only (§3) —
        ANONYMIZE/LOCAL_MODEL are request-side-only concepts, unchanged."""

class TransformationService(Protocol):
    def apply(self, content: str, required: list[str]) -> str:
        """Side-effect-free, deterministic given the same input + rule set —
        required for audit reconstruction (Blueprint Goal 4)."""

class RoutingService(Protocol):
    def select_provider(self, decision: Decision, feature: str) -> ModelTarget:
        """Executes Decision Engine's provider/model choice. A
        decision.action == 'local_model' with no local model configured
        today is a Routing-layer error, resolved per §7 — not silently
        downgraded to sending the data externally anyway."""

class ResponseFirewallService(Protocol):
    async def validate(self, response_text: str, context: RequesterContext) -> ResponseVerdict:
        """Composes existing quality_gate.evaluate_draft_quality /
        genome_validator logic per content type — does not reimplement
        citation-checking, calls into the existing modules. Returns a
        verdict for Decision Engine to act on; does not itself decide."""

class GovernanceService(Protocol):
    """The ORCHESTRATOR/conductor — not the brain. Extends
    shared/ai_client.py::_guarded_create/_guarded_acreate. Sequences
    Classification -> RiskScoring -> Policy -> DecisionEngine.decide_request
    -> (Transformation/PromptFirewall/Routing per verdict) on the request
    path, and ResponseFirewall -> DecisionEngine.decide_response -> Audit
    on the response path. Contains no decision logic of its own — every
    branch point calls into DecisionEngine and acts on its Decision."""
    async def govern_request(self, messages: list, context: RequesterContext) -> tuple[list, ModelTarget]:
        """Raises PolicyDenied (mirrors existing PromptInjectionBlocked) on
        a deny/block-class Decision. Raises Escalated (new) on escalate,
        carrying enough context for the human-approval flow. Called from
        `_guarded_acreate` only (§1.4)."""

    async def govern_response(self, response, context: RequesterContext) -> ResponseVerdict:
        """Never raises for a normal flow — an escalate/block Decision is
        returned as part of the verdict, not thrown, so the caller can
        handle it per feature (e.g. drafting shows a 'pending review'
        state rather than a hard error). Called from `_guarded_acreate`
        only (§1.4)."""

    def govern_request_sync(self, messages: list, context: RequesterContext) -> tuple[list, ModelTarget]:
        """NEW, Revision 8 (§1.4, fixes red-team Item 2) — called from
        `_guarded_create` (the ~46-site synchronous chokepoint). Same
        contract as `govern_request`, but calls only `*_sync` dependencies
        throughout (`classify_sync`, `score_sync`, `PolicyService.evaluate`
        — already sync, unchanged — `DecisionEngine.decide_request` —
        already sync, unchanged — `AuditService.log_decision_sync`). Never
        awaits anything, never bridges to an event loop."""

    def govern_response_sync(self, response, context: RequesterContext) -> ResponseVerdict:
        """NEW, Revision 8 (§1.4) — synchronous counterpart to
        `govern_response`, same relationship as the request-side pair."""

class AuditService(Protocol):
    async def log_decision(self, call_number: Literal[1, 2], decision: Decision, context: RequesterContext) -> Optional[str]:
        """REVISED, Revision 7 (fixes red-team Critical 2): return type
        changed from None to Optional[str] — the durable acknowledgment
        signal. Grounded exactly in the real
        shared/audit_immutable.py::log_action(), which already returns the
        DB-assigned row id on a successful, committed insert, or None on
        ANY failure (unregistered action, insert error, DB unreachable —
        indistinguishable by design, and that's fine: all three correctly
        mean 'no durable record exists').

        Call discipline is TIER-DEPENDENT, not uniform (this is the actual
        fix, not a new mechanism):
        - OPTIONAL/RECOMMENDED: caller wraps this in a fire-and-forget task
          (asyncio.create_task, matching every existing audit_immutable
          call site in this codebase) — never awaited directly, never
          blocks, return value not inspected.
        - REQUIRED/MANDATORY: caller MUST `await` this call directly and
          inspect the return value BEFORE proceeding (§7.3, §1.2's
          DecisionEngine docstring). A returned id is the durable ACK; None
          is not — there is no third state, and no separate 'is audit
          available' check is used anywhere, per the founder's own
          rejection of health-check and local-spool alternatives (both
          verified insufficient: a health check can pass immediately
          before an insert fails; a local spool is not proof of durable
          persistence, only of increased probability)."""
    def log_decision_sync(self, call_number: Literal[1, 2], decision: Decision, context: RequesterContext) -> Optional[str]:
        """NEW, Revision 8 (§1.4, fixes red-team Item 2) — grounded in the
        real `shared/audit_immutable.py::log_action_sync()` (`:112-127`),
        which already exists, already returns the identical `Optional[str]`
        durable-ACK signal as `log_action()`, and already involves zero
        `asyncio`. Called from `_guarded_create`'s synchronous chokepoint —
        same tier-dependent discipline as `log_decision` (fire-and-forget
        via a plain function call vs. called-and-inspected for
        REQUIRED/MANDATORY), just without an event loop anywhere in the
        picture."""
    async def log_escalation_resolution(self, escalation_id: str, resolved_by: str, outcome: str) -> None:
        """NEW in Revision 2 — closes the ESCALATED state's forensic gap
        (§4)."""
```

### 6a. Audit Payload Schema (NEW, Revision 3)

**One fixed shape, every Decision Engine call, no per-implementer variation.** This is the
`metadata` dict passed to the real `shared/audit_immutable.py::log_action()` — grounded in its
actual signature (`log_action(action, user_id, resource_type, resource_id, ip, metadata)`,
`shared/audit_immutable.py:86-93`), not an invented parallel logging system.

```json
{
  "operation_id": "uuid",
  "call_number": 1,
  "stage": "request",
  "classification": {
    "tiers": ["privileged"],
    "pii_tags": ["name", "jmbg"],
    "confidence": 0.82,
    "source": "classification_engine_v1"
  },
  "risk_score": {
    "value": 87,
    "contributing_factors": ["privileged_content", "gdpr_relevant", "external_provider"],
    "confidence": 0.9
  },
  "policy": {
    "applicable_rule_ids": ["POL-001", "POL-014"],
    "required_transformations": ["anonymize_names"],
    "minimum_action": "anonymize",
    "minimum_audit_requirement": "mandatory",
    "policy_version": "2026.08.01.1"
  },
  "decision": {
    "action": "anonymize",
    "reason": "Attorney-client privileged content routed to an external LLM provider (POL-001)",
    "policy_rule_ids": ["POL-001", "POL-014"],
    "policy_version": "2026.08.01.1",
    "audit_requirement": "mandatory"
  },
  "provider": { "vendor": "openai", "model": "gpt-4o" },
  "response_verdict": null,
  "context": {
    "user_id": "...", "predmet_id": "...", "feature": "drafting.nacrt",
    "requested_action": "draft_submission"
  },
  "timestamp": "2026-08-02T09:14:03.221011+00:00"
}
```

Response-path entries (`call_number: 2`, `stage: "response"`) carry `classification`/`risk_score`
as recorded from call #1 (linked by `operation_id`, not recomputed), `response_verdict` populated
instead of `null`, and — **corrected, Revision 8, fixes red-team Item 3** — a `response_policy`
block that is *not* call #1's `policy` object reused, but the fresh result of
`PolicyService.evaluate_response(verdict, context)`, e.g.
`{"applicable_rule_ids": ["POL-022"], "minimum_audit_requirement": "required", "policy_version": "2026.08.01.1"}`.
Reusing call #1's `policy` here, as Revision 7 specified, is exactly what made that revision's
fix a no-op — the payload shape itself now reflects the corrected `decide_response` contract (§6).

**Two concrete, code-grounded requirements this schema surfaces, neither of which is optional:**

1. **The action string must be registered.** `log_action()` silently no-ops — logs a debug line
   and returns `None`, writes nothing — for any `action` not already in the hardcoded
   `AUDITABLE_ACTIONS` set (`shared/audit_immutable.py:56-81`). A new action, e.g.
   `"ai_governance_decision"`, **must be added to that set** as part of implementation. This is
   the exact bug class this project has already found three separate times (SEC-034's silently
   no-op'd migrations, SEC-005's dead rate-limit middleware, SEC-002's shadowed cron dispatcher) —
   flagged here explicitly so Program 1 does not become a fourth instance of "a control that looks
   live but silently isn't."
2. **What the hash chain actually proves, stated precisely rather than implied.** `entry_hash` is
   computed over `prev_hash + user_id + action + ts + resource_type + resource_id`
   (`shared/audit_immutable.py:189-196`) — **`metadata` (the payload above) is not itself part of
   the hash.** Its immutability comes from the DB trigger blocking all `UPDATE`/`DELETE` on the
   row (`migrations/043_security_bulletproof.sql:33-52`), a real but *different* guarantee than
   the hash chain provides. Correct claim: "this decision record cannot be altered or deleted
   without breaking the chain's sequence integrity, and its detail payload cannot be altered or
   deleted at all (trigger-enforced)." Incorrect claim: "the hash proves the payload content
   wasn't tampered with." Getting this distinction wrong in a future public claims document would
   repeat exactly the kind of overstatement `docs/security/PUBLIC_SECURITY_CLAIMS.md` exists to
   prevent.

---

## 7. Failure Modes

| Failure | Existing precedent in Vindex | Proposed behavior | Fail-open / fail-closed | Justification |
|---|---|---|---|---|
| Classification errors or times out | None (capability doesn't exist yet) | Default to `PRIVILEGED`, low confidence, proceed | **Fail closed** | Blueprint Principle 1 — unknown sensitivity is not treated as safe |
| Risk Scoring **core logic** errors or times out (classification/context malformed — distinct from the modifier sub-call below, Revision 8 scoping fix) | None | Default to score=100 (maximum) | **Fail closed** | An unscoreable operation must not be treated as risk-free. Does NOT apply to `current_risk_modifier`'s own timeout — that is §7.1's separate "Anomaly Detection unreachable" row (proceed without it), not this row; the two were reading as contradictory before this scoping correction |
| Policy Lookup finds no applicable rule | None (today: implicit allow, ungated) | `PolicyRequirements(minimum_action="deny")` | **Fail closed** — explicit behavior change from today | Blueprint Principle 1. Rollout implication unchanged from Revision 1: every currently-active feature needs an explicit allow-rule authored *before* default-deny is enabled, or ship with a time-boxed log-only phase (§9) |
| **Decision Engine itself errors** | None — this component is entirely new, and is now the system's tightest bottleneck by design (§2) | Deny the request, log at highest severity, alert (not just audit) | **Fail closed, loudly** — this is the one failure mode where "fail closed and stay quiet" is insufficient | Centralizing the decision (the whole point of this Program) means its own downtime is now equivalent to "every AI feature in the product stops." This must be operationally distinguishable from an ordinary policy denial — a denial is Decision Engine *working*; an error is Decision Engine *down*, and needs a different alert path (ties to Program 5's monitoring gap) |
| Audit write fails — OPTIONAL/RECOMMENDED tier | `audit_immutable.log_action` already fire-and-forget elsewhere (e.g. `login_failed`, SEC-017) | Fire-and-forget for the call itself | **Fail open** for the call, but sustained failure escalates to Anomaly Detection (not silently absorbed forever) | An unauditable Decision Engine defeats Blueprint Goal 4 if this happens repeatedly and silently. Lower tiers accept this risk in exchange for zero added latency, consistent with every existing audit call site in this codebase |
| Audit write fails — REQUIRED/MANDATORY tier | None (this Program introduces the concept) — **REVISED, Revision 7, fixes red-team Critical 2** | Escalate (REQUIRED) / Deny (MANDATORY) — full mechanism in §7.3 | **Fail closed**, and specifically NOT fire-and-forget for these tiers | A tier that exists specifically to guarantee a forensic record cannot be satisfied by a call whose result is never inspected — see §7.3 for why a pre-flight health check and a local durable spool were both rejected in favor of awaiting the real write's own success/failure signal |
| Transformation rule throws | No precedent — `_skini_pii` has no observed error path | Block the call | **Fail closed** | Sending unredacted content because the redactor crashed is exactly what this Program exists to prevent |
| Prompt injection detected | `security/prompt_guard.py` / SEC-003, proven | Unchanged | **Fail closed** (existing) | No reason to revisit a working, tested mechanism |
| Response Firewall errors | `quality_gate.py`: degrades to neutral score, never blocks. `genome_validator.py::verify_genome()`: **known fail-open bug** — can silently return `"approve"` if all 5 sub-checks fail (`KNOWN_RELIABILITY_RISKS.md`) | Response Firewall degrading to a neutral `ResponseVerdict` is fine — it is only an *input*. The fix is structural, not per-caller: | **Decision Engine's 2nd call must default to `escalate`, never `approve`, on a degraded/errored verdict** | This is the exact bug class `KNOWN_RELIABILITY_RISKS.md` found, fixed once, structurally, at the one place that decides — rather than trusting every future Response Firewall implementation to remember not to fail open. Whether an escalation actually reaches a human (vs. automated downstream consumption, e.g. Genome feeding Health Index) is Program 4's audit-completeness concern, not this Program's |
| Decision Engine outputs `local_model` but no local model is configured | N/A — new vocabulary | Routing layer treats this as a configuration error, not a silent external send | **Fail closed** | The whole point of `local_model` as a distinct verdict is "must not leave the perimeter" — silently falling back to sending externally anyway would invert that guarantee |
| Timeout anywhere in the request-path pipeline | — | Whole call fails closed | **Fail closed** | Consistent with every other row above; a partially-completed governance decision is not a decision |

### 7.1 Component Unavailability — Deterministic Table (NEW, Revision 3)

**The table above covers a component erroring on a specific input** (e.g., Classification cannot
parse one ambiguous document). **This table covers the component itself being entirely
unreachable** — a different failure class, and one the founder explicitly required a single,
non-negotiable default for, so no implementer decides it ad hoc later.

| Component down | Outcome | Why this one, not another option |
|---|---|---|
| **Classification** unreachable | **Deny**, immediately — pipeline does not proceed to Risk Scoring/Policy with a guessed tier | Without knowing what's being protected, nothing downstream can make a meaningful decision. Note the distinction from the per-input row above: *one hard-to-classify document* still gets a conservative default and continues (a data-quality issue); *the whole service being down* short-circuits instead of synthesizing defaults through the rest of the pipeline (an availability issue) — conflating these two was the ambiguity the founder flagged |
| **Risk Scoring** unreachable | **Escalate** (human review) | Classification is still known at this point — the system knows *what* is at stake, just not the quantified risk of *this specific action*. That is exactly the situation a human is well-suited to judge, and less severe than an unknown classification |
| **Policy Engine** unreachable | **Deny** | No rules can be consulted — identical outcome to "Policy ran but found no matching rule" (§7's default-deny row), for the same reason: an unconsulted policy is not a passed policy |
| **Decision Engine** unreachable | **Fail closed + loud alert** (unchanged from §7 — repeated here for completeness of this table, not a new rule) | This is the one component whose downtime means every AI feature in the product stops; it must be operationally distinguishable from an ordinary denial (§2's named new risk) |
| **Anomaly Detection** unreachable (NEW, Revision 7 — closes red-team High 4's gap in this table) | **Proceed without the behavioral modifier** — `RiskScoringService.score()` treats a timeout/error from `current_risk_modifier()` as "no modifier," contributes 0, does not fail or delay | This is a soft, advisory signal by its own docstring (§6) — treating its absence the same as Classification/Policy/Decision being down would be disproportionate; the base score (classification + action + volume) is unaffected and still governs |
| **Audit** — no longer framed as "unreachable" (RESOLVED, Revision 7 — see §7.3) | **Tiered by `AuditRequirement` (§6/§7.2), enforced via a durable-acknowledgment await, not an availability check** | Revision 4 fixed the tiering; the red-team found the tiering itself was ungroundable against a fire-and-forget primitive. §7.3 fixes the mechanism, not the tiers |

### 7.2 Audit Unavailability, Resolved: Tiered by Criticality (NEW, Revision 4)

**Founder's blocking issue on Revision 3, verbatim: Audit-unavailable behavior treated as one
binary question when it is really at least two — a translation and a court-submission draft do
not carry the same cost if nobody can later answer "who had access to this."** Fixed by
introducing `AuditRequirement` (§6): OPTIONAL / RECOMMENDED / REQUIRED / MANDATORY, computed as
`max(policy.minimum_audit_requirement, risk_derived_tier(risk.value))` — a declared policy floor
(e.g. "PRIVILEGED tier → always at least MANDATORY," independent of what a given instance's
numeric risk score happens to compute) combined with a risk-derived tier, so neither an
under-calibrated risk score nor a missing policy rule alone can silently under-classify a
sensitive operation.

| `AuditRequirement` | Risk range (founder-committed, Revision 6) | Example operations (founder's own) | No durable audit ACK (§7.3) → |
|---|---|---|---|
| **OPTIONAL** | 0-20 | Translation, summary, style rewrite, explain-a-law | **Allow**, attach `audit_degraded: true` + a visible local warning to the response |
| **RECOMMENDED** | 21-45 | Everyday case-specific AI use below the REQUIRED floor | **Allow**, same warning, plus an `AnomalyDetectionService.record_signal("audit_unavailable_recommended")` call — repeated occurrences escalate via the existing sustained-failure path, not silently forever |
| **REQUIRED** | 46-70 | Full-case analysis, drafting using case-wide context | **Escalate** (human review) — the operation pauses rather than proceeding unaudited |
| **MANDATORY** | 71-100, or policy-floored regardless of score | Court submissions, GDPR export, PRIVILEGED-tier content leaving to an external provider | **Deny**, outright, no exceptions — this is the founder's Bar Association test: *"Ko je imao pristup ovom predmetu?" / "Ne znamo, audit baza je bila pala"* must never be a possible answer for this tier |

**Revision 7 correction to this table's own header, not its tiers or examples:** the rightmost
column was originally titled "Audit unreachable →," implying a pre-flight availability question.
The red-team review found this ungroundable — see §7.3 for why, and for the mechanism (durable
acknowledgment, not availability) that actually enforces these same four outcomes correctly.

**Boundaries are deliberately non-linear (founder's own reasoning, Revision 6): risk is not
evenly distributed — most operations are low-risk, few are extreme, and the gap between a score
of 68 and 72 is often the gap between an internal document and a privileged one.** These are
founder-committed starting values (8a, closed) — worth revisiting against real operational data
post-launch (same "validate against a real measured baseline" discipline §9 already applies to
Risk Scoring generally), not blocking Stage 5.

**Score alone cannot under-classify a specifically named sensitive factor (Revision 6 fix, closing
the founder's own counter-example — score 34 with `PRIVILEGED_CONTENT` present must not land on
RECOMMENDED just because 34 falls in that numeric band).** `PolicyRequirements.minimum_audit_requirement`
already incorporates factor-based rules (`PRIVILEGED_CONTENT`/`GDPR_RELEVANT` → minimum REQUIRED;
sealed/classified-class content → minimum MANDATORY — §6's `PolicyService.evaluate()`) alongside
feature-based ones — so the `max()` in §1.2's Escalation-Only Invariant stays exactly two terms:

```
effective_requirement = max(
    policy.minimum_audit_requirement,   # incorporates BOTH feature floors AND factor overrides,
                                         # versioned via policy_version
    score_derived_tier(risk.value),     # the table above — catches risk that doesn't match any
                                         # specifically named factor but still scores high by
                                         # volume/pattern
)
```

No separate, third, unversioned mechanism was introduced — factor-based overrides are ordinary
Policy rules that happen to match on `risk.contributing_factors` instead of `classification`, and
inherit `policy_version`'s replay-determinism for free.

### 7.3 Durable Audit Acknowledgment, Not Availability (NEW, Revision 7 — fixes red-team Critical 2)

**The contradiction the red-team found, stated exactly:** §6/§7/§8 (pre-Revision-7) specified
Audit writes as fire-and-forget — *"must never block the governed call itself."* §7.2 required
denying/escalating specifically *because* Audit is unreachable. A call whose result is never
awaited cannot supply the signal a decision about that same call depends on. This is not a wording
gap; it is a structural impossibility as originally written.

**Two tempting fixes, both explicitly considered and rejected — the founder's own reasoning,
preserved precisely, because the reasoning is the valuable part, not just the conclusion:**

- **Pre-flight health check** (confirm Audit is reachable, then proceed): rejected. A health check
  can pass and the very next insert can still fail — the two are separate operations with a race
  between them. "Audit = OK" a moment before "INSERT FAIL" a moment later leaves the operation
  believing it is protected when it is not. A health check answers "was Audit alive a moment ago,"
  never "will this specific write succeed."
- **Local durable spool** (write locally if the primary DB is down, sync later): rejected as
  insufficient for MANDATORY specifically, though it is a genuinely better *availability* posture
  than the health check. A local write increases the *probability* the record survives; it does
  not *prove* durable persistence — the exact machine holding that spool can fail physically
  before it syncs. "It was written to local disk" is not the same claim as "the record durably
  exists," and MANDATORY's entire purpose is to make only the second claim.

**The fix: replace the question "is Audit available" with "did this specific write receive a
durable acknowledgment."** Concretely, for REQUIRED/MANDATORY:

```
Decision Engine decides
        │
        ▼
await AuditService.log_decision(...)   # NOT asyncio.create_task — awaited directly
        │
        ├──► returns a real id  ──►  durable ACK confirmed  ──►  proceed (Transform/Route/Execute)
        │
        └──► returns None       ──►  no ACK  ──►  REQUIRED: escalate / MANDATORY: deny
```

For OPTIONAL/RECOMMENDED, the flow is unchanged from every prior revision: `asyncio.create_task(...)`,
never awaited, never inspected.

**Why this needed no new audit infrastructure, only a different call discipline — the elegant part
of the fix:** `shared/audit_immutable.py::log_action()` (§6a) already returns exactly the signal
this requires. `_build_and_insert()` performs a real, synchronous `supa.table("audit_immutable")
.insert(record).execute()` and returns the DB-assigned row `id` on success or `None` on any
failure (unregistered action, insert exception, unreachable DB — all collapse to `None` by the
function's own existing `except Exception: ... return None`, `shared/audit_immutable.py:104-109`).
The "fire-and-forget" property this codebase currently associates with `log_action` comes entirely
from callers wrapping it in `asyncio.create_task(log_action(...))` and never touching the returned
task's result (verified across every current call site — `api.py`, `shared/deps.py`,
`security/anomaly_detection.py`, `routers/legal_reasoning.py`, `services/event_bus.py`,
`workers/background_agents.py`). **`AuditService.log_decision` is not a new mechanism layered on
top of `log_action` — it is `log_action`, called with a different discipline depending on tier.**
This is why the fix is a specification correction, not a new component: §6's `AuditService`
contract already returns `Optional[str]` (revised this section); `GovernanceService` simply must
`await` that value instead of discarding it for REQUIRED/MANDATORY, and act on it before
proceeding.

**What "durable" means here, stated precisely rather than assumed:** a returned id means Supabase's
PostgREST layer received a successful response from Postgres for the insert — which, under
Postgres's own default synchronous-commit behavior, means the transaction was committed before
that response was returned. This project already accepts Postgres/Supabase's own durability
guarantees as the trust boundary for everything else `audit_immutable` claims (the same boundary
`docs/security/DISASTER_RECOVERY_PLAN.md`'s PITR discussion operates within) — this fix relies on
nothing stronger than that, and nothing weaker either.

**Named, disclosed tradeoff, not silently accepted:** a prolonged Audit outage makes every
MANDATORY-tier operation unusable for its duration — court submissions, GDPR exports, and
privileged-content sends to a provider all deny until Audit recovers. This is the correct
consequence of "no exceptions, ever" for that tier, not a side effect to hide; it is also a real
business-continuity exposure worth Program 5's operational monitoring treating an Audit outage as
a P0/P1-class incident (`docs/INCIDENT_RESPONSE_PLAN.md` severity terms), not merely a background
degradation — because for as long as it lasts, it is functionally a partial product outage, not
just a logging gap.

---

## 8. Performance Budget

**Context:** GPT-4o/4o-mini calls themselves take 1-90 seconds in this application (per
`docs/FOUNDER_DEMO_PLAYBOOK_2026-07-19.md`). A ~250ms governance overhead remains under 1% of
typical call latency.

**Single table, per founder's requested format (Revision 3):**

| Faza | Max | Basis |
|---|---|---|
| Classification | 50ms | In-process regex/lightweight heuristics, matching `_skini_pii`'s current negligible cost — not a full NER call (NER-based name/address detection, SEC-006's proper fix, needs async/pre-computed handling if it can't fit this) |
| Risk Scoring — core | 10ms | In-process scoring function over already-computed classification + context, no I/O. **Revision 8 scoping correction**: this 10ms covers `score()`'s own logic only, not `current_risk_modifier()`'s attempted call |
| Risk Scoring — behavioral modifier attempt (NEW, Revision 8, fixes red-team Item 4) | ≤15ms timeout, best-effort, does not extend the core 10ms | `current_risk_modifier()`'s real underlying operation (a Supabase RPC, `security/anomaly_detection.py::_check_db_profile`) realistically costs 20-100ms — the same order as the Audit Write row below, not 10ms. `score()` races this against a ≤15ms timer and proceeds without it if the timer wins; the RPC itself is not cancelled, its result (if it later arrives) feeds Anomaly Detection's own logging, not this decision |
| Policy Lookup | 10ms | In-process rule table lookup, zero network calls |
| Decision (call #1, request) | 5ms | Pure logic over already-computed inputs, no I/O — the "not a network hop" constraint (§1) applies most strictly here, since this runs on every governed call twice |
| Transformation | 100ms | Regex-based redaction + message-isolation formatting |
| Response Firewall | 50ms *(fast path — see exception below)* | Structural/completeness checks only |
| Audit Write — OPTIONAL/RECOMMENDED | 10ms | Fire-and-forget (`asyncio.create_task`), non-blocking — the 10ms is the cost of scheduling the task, not of the write completing |
| Audit Write — REQUIRED/MANDATORY | **20-100ms, blocking** *(Revision 7 correction — see below)* | A real, awaited Supabase network round-trip (§7.3), not the 10ms fire-and-forget figure — stated as a range because it is genuine network latency, not an in-process cost this spec can pin to one number |
| **Ukupno overhead (OPTIONAL/RECOMMENDED path)** | **< 260ms** *(revised, Revision 8)* | 50+25+10+5+100+50+10 = 250ms — the 25ms Risk Scoring line (core 10 + modifier wait ≤15) replaces Revision 3-7's flat 10ms, per the Item 4 scoping fix above; the majority of governed calls |
| **Ukupno overhead (REQUIRED/MANDATORY path)** | **< 350ms** | 250ms above minus the 10ms fire-and-forget Audit line, plus 20-100ms for the awaited durable-ACK write = 260-340ms. Still comfortably under 1% of the 1-90s GPT-call context, but stated as its own figure rather than silently reusing the lower-tier number |

**One explicit, load-bearing exception, not silently dropped from Revision 2's table:**
Response Firewall's 50ms line is the *fast path* — structural/completeness checks only. When
citation verification is invoked, it does **not** fit 50ms: `quality_gate.py`'s `_verify_citation`
is an async, RAG-corpus-backed lookup per citation, already parallelized via `asyncio.gather`
(`services/quality_gate.py:75`), realistically **100-500ms** depending on citation count. This is
deliberately **not** counted against the 250ms ceiling above, for the same reason stated in
Revision 2: it runs on the response path, where the human is already waiting for the complete
answer (seconds, per the GPT-call context above), not stacked in front of every request the way
the other rows are. Stating this as an explicit carve-out rather than pretending the 250ms figure
covers it is the honest version of the founder's own "numbers must be numeric, not aspirational"
requirement — a false single number would be worse than two clearly-labeled ones.

Prompt Firewall (existing `prompt_guard.analyze`) and Routing (<10ms, trivial pass-through given
today's single-provider reality, §1.1) are omitted from the table above because they are either
already shipped and measured (Prompt Firewall, unchanged since SEC-003) or negligible — both are
still part of the request path and both remain comfortably inside the 235ms sum's own margin.

---

## 9. Definition of Done (for this specification, not for implementation)

This document reaches Finding Lifecycle **stage 5 — Architecture Approved** only when all hold.
Until then it remains stage 4, and no implementation may begin.

1. **Independent peer review** — a reviewer with no authorship stake, explicitly instructed to
   falsify rather than confirm, same discipline as SEC-031. **Run twice so far:** the full pass
   (Revision 7's trigger) returned BLOCKING (2 Critical, 2 High); a first *targeted* falsification
   re-check (scoped to exactly those four fixes, forbidden from raising new findings) returned
   Item 3 OPEN (a proven dead parameter) and Items 1/2/4 PARTIALLY CLOSED (each a real residual
   gap, not a wording issue) — founder ruling: no Stage 5 on that result. Revision 8 fixes all
   four properly, per a stricter method the founder specified: for each item, first confirm the
   root cause, then present at least one alternative, then justify the choice — not accept the
   first idea that works (applied throughout this revision's fixes, see revision history). **A
   second targeted re-check, scoped only to Revision 8's four corrections, is the remaining
   prerequisite for this item** — not yet performed as of this text.
2. Every interface in §6 this Program **consumes** (`ClassificationService` from Program 2,
   `RequesterContext` from Program 3, `AnomalyDetectionService` extending existing code) is named
   with its exact expected shape.
3. Every existing control (`prompt_guard`, `quality_gate`, `genome_validator`, `audit_immutable`,
   `anomaly_detection`) has an explicit composition answer — reused, extended, or generalized —
   with zero remaining ambiguity.
4. §7's failure-mode table has a decided answer for every row, including the two new
   Revision-2-specific ones: **Decision Engine's own failure path** (fail closed + loud alert, not
   just a quiet audit entry) and **Response Firewall degradation must never resolve to `approve`**
   (fixing `KNOWN_RELIABILITY_RISKS.md`'s bug structurally). The **default-deny rollout
   requirement** (every active feature needs an explicit allow-rule, or a time-boxed log-only
   phase) remains the single highest-consequence pre-launch task.
5. §8's performance budget is signed off as achievable against a real measured baseline already
   in this codebase — not aspirational numbers. Given the Decision Engine now runs twice per call
   with a combined < 20ms budget, this specifically needs validating against a realistic policy
   rule-set size (a lookup over 5 rules and a lookup over 5,000 rules are not the same cost) —
   flagged here as a concrete pre-implementation check, not assumed.
6. **§1.1's provider-abstraction path decision (option (a), per-vendor chokepoint replication) is
   explicitly re-confirmed at sign-off** — not silently superseded if a second provider becomes
   concretely planned between now and implementation.
7. **Revision 3's three required additions are present and internally consistent**: §6a (audit
   payload schema + the `AUDITABLE_ACTIONS` registration requirement), §7.1/§7.2 (now
   criticality-tiered unavailability table, resolved per item 8 below), §8 (single numeric latency
   table with the Response Firewall exception stated explicitly, not hidden).
8. **Revision 4's blocking issue is resolved, both follow-ups now closed**: §7.2's
   `AuditRequirement` tiering (OPTIONAL/RECOMMENDED/REQUIRED/MANDATORY) replaces Revision 3's
   single global Audit-unavailable default. **(b)** founder confirmed explicitly (Revision 5):
   Risk Scoring may escalate a Policy floor, never reduce it — §1.2's Escalation-Only Invariant,
   elevated to a Blueprint principle. **(a)** founder supplied committed, non-linear boundaries
   (Revision 6: 0-20/21-45/46-70/71-100, §7.2) — adopted as starting values, closed for spec
   purposes; revisiting against real operational data post-launch is a normal maturation step, not
   a blocker.
9. **§1.2's Escalation-Only Invariant is enforced structurally at implementation time** — a
   defensive assertion inside `DecisionEngine` (e.g., asserting the computed effective requirement
   is never less protective than the Policy floor it was derived from), not merely documented and
   trusted. This is a new, explicit implementation requirement (Revision 5), not optional
   defensive programming — the invariant's entire value is that it cannot be silently violated by
   a future code change that "happens to" blend rather than maximize.
10. `RiskFactor`'s controlled vocabulary (§6) covers the risk-scoring signals actually needed at
    launch — reviewed once against Program 2's real classification output shape when that
    Program's implementation begins, not assumed complete from this spec alone.
11. **§1.3's extensibility answer is accepted as-is** (Revision 6): the decision-making core
    (Decision Engine, audit schema, replay logic) is monotonically extensible by construction;
    vocabulary registration (`RiskFactor`, `AUDITABLE_ACTIONS`-style) and per-factor detection
    logic deliberately remain reviewed code additions, not runtime-dynamic — a founder-confirmable
    design tradeoff, not an open question, per the founder's own "if Claude confirms these two
    conditions" framing on Revision 5.
12. **§1.1/§1.1.1's chokepoint coverage is complete for the founder's stated v1 scope, corrected in
    Revision 8** — chat, both embeddings paths (raw-SDK and, separately, the LangChain
    `embed_documents`/`aembed_documents` layer, since the SDK-level patch fires after tokenization
    for that group), and both audio endpoints, all via the proven monkeypatch technique (every SDK
    class verified to exist); the Realtime API via session-level governance at its single call
    site, with the disclosed limitation now correctly naming server-side tool-result content, not
    only spoken utterances (§1.1.1).
13. **§7.3's Durable Audit Acknowledgment mechanism, and §1.4's sync/async split, are implemented
    as specified** — REQUIRED/MANDATORY tiers call `AuditService.log_decision`
    (`_guarded_acreate`) or `log_decision_sync` (`_guarded_create`) directly and gate on the
    return value; OPTIONAL/RECOMMENDED remain fire-and-forget on both paths. No health-check,
    local-spool, or cross-thread event-loop bridge is introduced at implementation time in place
    of this — all three were explicitly evaluated and rejected at the specification level (§7.3,
    §1.4) for reasons that apply regardless of who implements it.
14. **§6's `PolicyService.evaluate_response` and the corrected `decide_response` formula
    (Revision 8) are implemented exactly as specified, with a concrete test proving the fix is
    real** — at minimum, one test asserting that a `ResponseVerdict` carrying a
    `fabricated_citation`-class flag produces an `audit_requirement` strictly higher than an
    otherwise-identical low-risk request's OPTIONAL tier. This is the item the targeted re-check
    proved was a dead parameter once already; a passing test that could not have passed against
    the Revision 7 formula is the bar for calling it actually fixed, not merely re-worded.
15. **Founder re-sign-off on Revision 8's four corrections specifically** — no prior sign-off
    (Revision 6's or otherwise) carries forward to them. This is the founder sign-off gate; no
    separate item restates it.

Only after all fifteen are satisfied does Program 1 move to stage 6 (Implementation) — consistent
with `FINDING_LIFECYCLE.md`'s statement that Peer Review and Production Reality Gate "must pass
before stage 6 starts... passing one without the other is a false sense of readiness."

---

## Addendum — Stage 5/6 Implementation Notes (2026-08-02, captured at founder sign-off)

**Not architecture revisions.** These are implementation- and test-suite-level requirements the
founder raised at final review, correctly distinguished from the architecture itself — captured
here so they aren't lost between sign-off and the first implementation PR, per the founder's own
framing: *"Ovo nije zahtev za novu reviziju. Više je pitanje za implementaciju Stage 5."*

**1. Unknown `RiskFactor` values must fail closed, never be silently ignored.** Scenario: a rolling
deploy where an older service emits a `RiskFactor` value a currently-running `DecisionEngine`
doesn't yet recognize (e.g. a future `LEGAL_HOLD` sent before that version's rollout completes), or
the reverse. Required behavior: raise a security-invariant exception → `DecisionEngine` denies the
request → both the denial and the unrecognized value itself are audited. An unrecognized factor
must never be treated as "no factor" — silently dropping it is functionally identical to
Classification/Risk Scoring being wrong outright, which §7's failure-mode table already requires
to fail closed; an unrecognized enum value is the same failure class under a different name, and
must get the same answer, not a silent pass-through.

**2. The Escalation-Only Invariant (§1.2) needs a policy-*load-time* validator, not only the
runtime assertion already required by §9 item 9.** A misconfigured policy rule that would set some
factor's effective floor *below* what that factor already establishes elsewhere in the rule set
(e.g. a rule reading `PRIVILEGED_CONTENT → OPTIONAL`, contradicting the MANDATORY floor §7.2
specifies for that same factor) must cause the policy load itself to fail — the server refuses to
start, or refuses to activate that `policy_version`, rather than silently accepting a rule that
violates the invariant it exists to enforce. This is a second, independent check at a different
point in time than §9 item 9's runtime assertion: the runtime check catches a violation *per
decision*, after a bad rule is already live; the load-time validator catches it *before any call
ever uses the rule at all*. Both are required — the load-time check catches the mistake earlier
and cheaper, but cannot substitute for the runtime one, which is the only check that still applies
if a bad rule were ever injected by some path other than normal policy loading.
