# Duplicate Decision Report — Program Alpha, Phase 2/3

**The mission's central demand, restated**: *"Ako pronađeš lokalni bug: NE popravljaj ga odmah. Prvo
pronađi razlog zbog kojeg je taj bug uopšte mogao da postoji."* (If you find a local bug, don't fix it
immediately — first find the reason that bug was able to exist at all.) This report is organized around
that question for every duplicate found: not just "what's duplicated" but "what pattern in how this
codebase gets built allowed a second implementation to appear instead of a call to the first one."

11 duplicates found. **They cluster into exactly 3 root-cause patterns**, not 11 unrelated accidents —
this is the report's main finding.

---

## Root cause pattern A: "a new feature's author didn't know a canonical function already existed, or built one to avoid a cross-module import"

This is the dominant pattern — **7 of 11 duplicates** fit it:

1. Court Predictor's `procenat` — a second GPT call added next to the real deterministic `nivo` computation, instead of deriving a value from it.
2. Document classification — `shared/intake_classify.py` built its own taxonomy/AI call instead of importing `routers/evidence.py`'s classifier (or vice versa; whichever came second didn't reuse the first).
3. Entity extraction — same pattern, `intake_extract.py` vs. Evidence's `ai_tags`.
4. Proactive alert creation — 11 call sites across 9 files, each independently wrote a `supa.table("proactive_alerts").insert(...)` block instead of a shared helper existing to call.
5. Embedding model — 5 ingestion routers each hardcode the model string instead of importing `retrieve.py`'s `EMBEDDING_MODEL` constant.
6. Outbound email — 5 routers each wrote their own `smtplib` block instead of importing `email_notif.py::_smtp_send` (which `client_portal.py` correctly does — proving the reuse was always possible, just not consistently done).
7. Correlation ID minting — 2 inline `uuid.uuid4()` calls instead of `new_correlation_id()`.

**Why this pattern keeps recurring**: this codebase has no *enforced* convention (a lint rule, an
import-boundary check, a documented "always check `shared/`/`services/` before writing new business
logic" step) that would catch this at write-time. It relies entirely on the author's own awareness of
what already exists — which degrades naturally as the codebase grows and more routers exist than any one
session can hold in context. **This is the actual defect class**, not any one of the 7 instances above.

## Root cause pattern B: "a bug was patched by adding a second, corrective implementation instead of fixing the first"

**3 of 11 duplicates** fit this, and it is the most dangerous pattern because each instance looks, at the
moment it was written, like a reasonable local fix:

1. **Document classification's "second write wins" pattern** — LZ-002 (2026-08-03) found intake's
   classifier wrote the wrong vocabulary to `tip_dokaza`; the fix applied was to add Evidence's classifier
   as a *second* write that overwrites the first, held together by call-order. The actual cause (two
   independent classifiers) was never removed.
2. **Phoenix's `morning_briefing.py` alert-retry fix** — a real, correct fix for one of 11
   `proactive_alerts` call sites, but scoped to that one call site because no canonical function existed
   to fix once, for all 11.
3. **Court Predictor's confidence split** (by inference from its shape, not an explicitly documented
   patch history, but structurally identical) — a plausible-looking "give the user a percentage too" was
   added next to an already-working deterministic signal, rather than deriving the percentage from it.

**Why this pattern is worse than Pattern A**: it doesn't just leave a duplicate lying around passively —
it actively signals "fixed" (a test may even pass, the immediate symptom is gone) while leaving the
generating cause intact and available to produce the *next* instance of the same defect class at the next
call site. Program Alpha's own Phase 7 regression-analysis requirement ("did the number of local decisions
decrease?") exists specifically to catch this pattern, which a symptom-only fix's own tests would never
flag as incomplete.

## Root cause pattern C: "global/cross-cutting infrastructure was introduced independently of the module that already owns that concern"

**1 of 11 duplicates**, but it is the single most severe finding across all 6 domains:

1. **The correlation-ID middleware** (`api.py`) — introduced as global FastAPI middleware, entirely
   independently of `shared/ai_provenance.py`, which 4 prior missions (Ledger, Migration, Phoenix,
   Keystone) had already built out as the canonical request-correlation mechanism. The middleware's author
   (at whatever point it was added) evidently needed "a correlation id for the response header" and, rather
   than importing the existing module, wrote a self-contained `ContextVar` + middleware pair — which then
   sat, unnoticed, disconnected from everything else, because **nothing in this codebase's structure
   declares "this is the one correlation mechanism, nothing else may mint one."**

**Why this is the worst instance of any pattern found**: Patterns A and B produce internal inconsistency —
annoying, real, but contained to code few people directly observe. Pattern C's specific instance broke the
one piece of correlation infrastructure a human actually sees (the `X-Correlation-ID` response header),
silently, while 4 missions' worth of internal wiring effort proceeded in parallel, unaware. This is exactly
what Program Alpha's Principle 6 (Event/Data Consistency: "Bez skrivenih ažuriranja. Bez paralelnih
puteva.") is written to prevent, and it's the clearest evidence in this whole report that a principle
stated in a mission charter needs an enforcement mechanism, not just documentation, to actually hold.

---

## What "eliminating the cause, not the symptom" means for each pattern, concretely

- **Pattern A's structural fix** is not "delete 7 duplicate functions" (that's still symptom-level,
  applied 7 times) — it is: every canonicalization in `CANONICAL_MIGRATION_PLAN.md` below should leave
  behind a *more discoverable* canonical function than existed before (a docstring naming it as "the only
  place this decision should be made," placed in `shared/` or `services/` where a `Ctrl+F`/grep for the
  concept surfaces it before a new implementation would be written). This mission does not build a lint
  rule or CI check to enforce this mechanically (that would be new infrastructure, arguably outside this
  mission's "eliminate patterns, don't build features" charter) — but Mission Olympus's Architecture Review
  Agent (17), now a standing governance role, is exactly positioned to catch a *future* instance of this
  pattern at review time, if its findings are actually acted on. This mission's implementation work
  (Phase 6) deliberately exercises that governance layer for real (Phase 9) rather than treating it as a
  separate concern.
- **Pattern B's structural fix**: when migrating a Pattern-B duplicate onto its canonical form, the *local
  patch* that pattern B represents (the second write, the one-call-site retry fix) is retired entirely,
  not left in place "just in case" — Program Alpha's own prohibition list explicitly forbids "privremena
  rešenja koja ostaju u kodu."
- **Pattern C's structural fix**: the correlation-ID middleware must stop minting its own value — it must
  read from and/or set `shared/ai_provenance.py`'s own request context, so there is exactly one place a
  correlation id is ever created for a given request, and the value a client sees is provably the same
  value every internal table records.

---

## Severity ranking (feeds `CANONICAL_MIGRATION_PLAN.md`)

| Rank | Finding | Pattern | Why this rank |
|---|---|---|---|
| 1 | Correlation-ID middleware disconnect | C | Only Pattern-C instance found; breaks the one externally-visible piece of correlation infrastructure; 4 prior missions' work is silently unreachable through it |
| 2 | Court Predictor `nivo`/`procenat` split | B | Critical two-author violation on a number a lawyer directly reads; fix reduces complexity (deletes a GPT call) |
| 3 | Firm memory for AI — dead vs. live implementation | A | The MORE CAPABLE implementation is the dead one — Copilot is silently worse than the codebase already supports |
| 4 | Document classification — two taxonomies | B | Held together by implicit call-order today; breaks under Program Alpha's own stress-test framing (concurrent workers) |
| 5 | Proactive alert creation — 11 call sites | A | Highest blast radius; historical proof of real risk (a silent, months-long schema-mismatch bug); Phoenix's fix only covers 1 of 11 |
| 6 | Business audit trail — `response_audit` legacy table | A/dead-weight | Confirmed write-only, zero readers; pure removal, no migration risk |
| 7 | Outbound email — 5 SMTP implementations | A | Well-precedented consolidation target already exists (`client_portal.py` shows the pattern works) |
| 8 | Embedding model — 5 hardcoded strings | A | Cheapest fix in this report; zero behavior change; closes a real latent-defect class |
| 9 | Correlation ID minting — 2 inline `uuid.uuid4()` | A | Trivial, 2 lines |
| 10 | GDPR's dead `audit_log.log()` call | Dead code | Trivial, never executes |
| 11 | Pinecone namespace registry | A | Real, but needs a design decision before implementation — not a mechanical fix |
| 12 | "Critical deadline" threshold — 6 files, 2 values | A | Needs the `ccc.py` 30-day discrepancy resolved first — a design question, not purely mechanical |
| 13 | Entity extraction — 2 pipelines | A | Lower priority — no active correctness bug today, only future-drift risk |
| 14 | Strategy Engine litigation % | Zero grounding | Needs a real deterministic-scoring design (Keystone `KEYSTONE-004`) — larger than a canonicalization, a founder decision |
| 15 | Evidence auto-strength hardcode | Compromised source | Same category as #14 — needs real per-fact confidence design, not a mechanical fix |
