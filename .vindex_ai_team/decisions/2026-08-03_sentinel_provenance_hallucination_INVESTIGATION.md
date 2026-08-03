# Project Sentinel — Phase 5 (AI Provenance) + Phase 6 (Hallucination Hardening)

Read-only investigation. No code changed. All claims below are grounded in direct grep/read of the
current repository state, not documentation or prior audit claims.

---

## PART A — AI Provenance

### A.1 Scope correction vs. Project Nexus's inventory

Project Nexus (same night, earlier) stated model/prompt-version/output-hash are "captured nowhere"
across **6 known AI call sites** (Case Genome, AI Briefing, Smart Intake extraction, document
classification, AI Drafting, Evidence Vault classification). That conclusion is directionally correct
but the scope was understated. A repo-wide grep for `.chat.completions.create(` / `.embeddings.create(`
under `routers/`, `services/`, `shared/`, `app/` finds **53 files** with live call sites — not 6. The
true count of distinct AI *features* (many files have multiple call sites; some "6" are one feature
each, others are call sites within one router) is well over 20. Nexus's 6 were real but a subset.

### A.2 Central infrastructure that DOES exist (applies to all 53 call sites structurally)

- `shared/ai_client.py` — patches `Completions.create`/`AsyncCompletions.create` at the OpenAI SDK
  class level (SEC-003). This is a **security guard** (prompt-injection blocking on the `user`-role
  input, via `security/prompt_guard.py::analyze`), not a provenance recorder and not a hallucination
  guard. It logs `caller_hint` (file:function:line) and a risk score to the application logger on
  **block** events only — that log line is not queryable/persisted to any table, and it never fires on
  allowed calls, so it contributes nothing to the provenance question ("what happened on this call").
- `shared/llm_retry.py` (`@llm_retry` decorator) — used broadly (`routers/strategija.py`,
  `routers/case_dna.py::_pozovi_compare_api`, others) for retry-with-backoff. Reliability infrastructure,
  not provenance.

Neither of these two shared layers captures user / model / prompt-version / input-refs / output /
confidence / timestamp / duration / sources in a queryable form. They are structurally global (every
call is wrapped) but orthogonal to provenance.

### A.3 Field-by-field reality (sampled across representative high-stakes call sites)

| Field | Reality |
|---|---|
| **korisnik** | Present in most feature tables via `user_id` on the row the AI output lands in (e.g. `predmet_genome_history.user_id`, `staging_memory` presumably has an author FK). Confirmed for Case Genome. NOT present as a field on the AI call itself anywhere — it's inferred from "whose row is this," not recorded as "who triggered this specific inference." |
| **predmet** | Present the same indirect way — inferred from FK on the destination row, not recorded against the call. |
| **model** | Confirmed absent everywhere sampled. `model="gpt-4o"` is a Python literal at the call site (`case_dna.py:209`, `:964`, hardcoded), never written to any table. If a model were swapped mid-flight (e.g. `gpt-4o` → `gpt-4o-mini` fallback, which several routers do on rate-limit), no persisted record shows which model actually produced a given stored output. |
| **verzija prompta** | Confirmed absent everywhere. No prompt-versioning scheme exists in the repo at all — prompts are inline f-strings/constants with no version tag. |
| **ulazne reference** | Partial. `predmet_genome_history.genome_data` stores a full snapshot, and `trigger_event` records *why* it fired, but neither records exactly which document IDs / dokazi rows / RAG chunks were in the prompt context for that specific call. Reconstructing "what did the AI actually see" requires re-deriving it from application logic at the time, not from a stored record. |
| **izlaz** | Actually the best-covered field — most features persist the literal AI output as their domain payload (`case_dna` jsonb column, `predmet_genome_history.genome_data`, `staging_memory` draft text). This is persistence-as-side-effect, not persistence-as-provenance: it's the current state, and history exists only for Genome (via `predmet_genome_history`) and drafting (via `staging_memory`'s single row per draft) — most other features (Briefing, Strategy, Copilot answers, `zadaci.py` AI tasks) overwrite/produce a row with no version history at all. |
| **confidence** | Exists in exactly 2 places: `staging_memory.confidence_score` (drafting only, via `quality_gate.py`) and Case Genome's `snaga_procent` (a case-strength percentage, which is a domain metric computed partly deterministically — not a literal "how sure is the LLM" score). Everywhere else (Briefing, Strategy, Copilot, Smart Intake extraction, document classification, `zadaci.py`): absent. |
| **timestamp** | Present wherever a table has a `created_at` default (most do) — but that's the row's creation time, not necessarily a dedicated "AI call happened at T" timestamp when the output overwrites an existing row in place (e.g. `predmeti.case_dna` UPDATE — no timestamp column on that update path separate from the table's own `updated_at`, if one exists). |
| **trajanje** | Confirmed absent everywhere sampled. No call site times its own OpenAI call and persists the duration. |
| **korišćeni izvori** | Confirmed absent as a structured field anywhere. RAG-backed features (precedenti, praksa, Copilot) construct a context string from retrieved chunks but do not persist "these N chunk/document IDs backed this specific answer" — so a citation cannot be verified after the fact without re-running retrieval and hoping it's deterministic. |

### A.4 Severity

**HIGH** (not Critical, because the two live-fixed 2026-08-02 security items and the event-loss items
from Nexus outrank this) — **AI Provenance Coverage is effectively 0% by the mission's own strict
definition** ("moguće rekonstruisati" model/prompt-version/duration/sources for *any* AI decision — none
of the 4 hardest fields are recoverable for *any* feature, not just the original 6). Confidence and
input-snapshot exist only for Genome and Drafting (2 of 20+ features). This is a **schema/architecture
gap requiring a founder decision** (a shared `ai_provenance` table + a single wrapper all call sites
route through), not a quick patch — correctly already flagged as NEX-006 (deferred) rather than
attempted ad hoc tonight.

---

## PART B — Hallucination Hardening

### B.1 Is there a shared output-validation layer? — **No. Confirmed 3 independent, non-overlapping patterns.**

1. **`services/quality_gate.py`** — the only thing in the repo that does real semantic grounding
   verification (citation-checks "Član N" references against the actually-indexed legal corpus via
   `app.services.retrieve._direktan_fetch_clana`, plus a keyword-heuristic completeness score). **Used
   by exactly one call site: `routers/drafting.py`'s `_stage_draft_for_review`.** Confirmed via repo-wide
   grep — no other router imports `quality_gate`.
2. **`routers/zadaci.py::ai_analiziraj_predmet`** (fixed tonight, Project Nexus NEX-002) — grounds the
   GPT prompt in `identify_case_problems`'s deterministic findings and instructs the model not to guess.
   This is prompt-level grounding (steer the model toward known-true facts before it speaks), structurally
   different from `quality_gate.py`'s pattern (let the model speak freely, then verify its claims after
   the fact against the corpus). Both are legitimate hardening strategies, but they are two different
   techniques invented independently, in two different routers, with no shared abstraction connecting
   them.
3. **Ad hoc `response_format={"type": "json_object"}` + `try/except json.loads`** — the dominant pattern
   across the remaining ~50 call sites (`case_dna.py`, `strategija.py`, `court_predictor.py`, etc.).
   This validates that the output *parses as JSON*, which is a syntax check, not a truth check — it
   catches "the model returned malformed JSON," not "the model asserted something false." No confidence
   threshold, no citation check, no bound-sanity check (e.g. a risk percentage the model invents being
   clamped or cross-checked against `risk_engine`'s deterministic number) exists on this path for any
   of these ~50 sites.

**Conclusion: `routers/zadaci.py`'s new grounding is the right instinct but is not "the pattern other
call sites should now adopt" in a mechanical sense — there is no shared layer to adopt.** It is a 3rd
bespoke implementation. A genuine Phase-6 fix (per the mission's own instruction: "ako postoje različite
implementacije zaštite od halucinacija, objedini ih") would require designing ONE shared post-generation
validation layer (grounding-check + confidence-bound + optional citation-verify, configurable per feature)
and migrating `quality_gate.py`'s logic and `zadaci.py`'s pattern onto it — not implemented tonight,
correctly scoped as future work, not attempted ad hoc.

### B.2 AI output paths that skip validation entirely

Every one of the ~50 "ad hoc JSON parse only" call sites qualifies as "skips validation" under the
mission's strict definition (schema-parse ≠ grounding/sanity validation). The **highest-severity**
concrete instances, because their output reaches the user as an apparent fact with no cross-check
against a deterministic source that already exists in this codebase for the same domain:

- **`routers/court_predictor.py`** — predicts case outcomes; no cross-check against `risk_engine`'s
  deterministic `calculate_procesni_rizik`/`identify_case_problems`, no confidence floor, no
  "insufficient evidence, decline to predict" path confirmed.
- **`routers/strategija.py`** / `strategija.py` (top-level) — legal conclusions with citation claims
  parsed as JSON only; not run through `quality_gate.py`'s citation verifier even though that verifier
  already exists and is reusable (it's a generic "Član N" checker, not drafting-specific — despite the
  module's own docstring in `quality_gate.py` framing it narrowly, the underlying `_verify_citation`
  helper has no drafting-specific dependency).
- **`routers/copilot.py`** — user-facing chat answers, the single highest-exposure surface (this is what
  the lawyer directly reads/trusts turn by turn) — no grounding check beyond whatever context string was
  assembled into the prompt; no citation verification on legal claims it makes in free text.

### B.3 Severity

**HIGH.** Not a single AI call site in the repo passes through a shared, mandatory hallucination guard.
Two isolated, non-overlapping partial implementations exist (`quality_gate.py` for drafting only;
`zadaci.py`'s fresh prompt-grounding for one task-creation endpoint). The mission's Phase 9 gate question
"Može li AI doneti zaključak bez dokazivog porekla?" must currently be answered **DA** for Copilot,
Strategy, Court Predictor, Briefing, and every other feature outside Drafting and today's `zadaci.py` fix
— i.e., for the large majority of the platform's AI surface.

---

## Bottom line for the coordinator

- Part A: AI Provenance is architecturally absent platform-wide (confidence/input-snapshot exist for
  only 2 of 20+ AI features); this needs a shared schema + wrapper, a founder-scoped decision, not a
  quick patch.
- Part B: No shared hallucination-guard layer exists; 3 independent partial patterns, ~50 call sites with
  syntax-only validation and zero semantic grounding, highest-exposure gap is `routers/copilot.py`
  (direct user-facing chat, no citation/grounding check at all).
