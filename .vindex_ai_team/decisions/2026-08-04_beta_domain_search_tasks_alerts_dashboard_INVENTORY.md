# Program Beta — Domain Inventory: Search / Task Engine / Alert Engine / Dashboard

**Scope**: every AI operation in this domain, plus the Facts/Inference/Recommendation boundary, Evidence
Chain, confidence, and hallucination-vector analysis Program Beta requires. Read-only, no code/git
touched. All claims verified against current code today.

---

## 1. AI operation inventory

| Operation | Input | Output | Prompt/Model | Data sources | Audit/Provenance/Correlation | Fallback | Confidence |
|---|---|---|---|---|---|---|---|
| Global keyword search (`routers/search.py::global_search`) | query string | ranked results per entity type | **No AI — pure `ilike` SQL** | 7 tables directly | N/A (not an AI call) | Per-type `nepotpuno` degraded marker (Project Phoenix) | N/A |
| RAG retrieval (`app/services/retrieve.py`) | query text | ranked doc chunks + `retrieval_meta` | canonical, ~20+ callers | Pinecone | `case_context()` wired, but **`retrieval_query`/`retrieved_context_ids` never populated by any of its ~15+ callers** (re-confirmed today, unchanged from Program Alpha's own domain audit hours earlier) | N/A | Real vector match scores returned in `retrieval_meta`, discarded by every caller |
| Task detection (`services/risk_engine.py::identify_case_problems`) | already-computed `rizik` dict | list of `{problem, ozbiljnost}` | **No AI at all — pure Python if/else over real DB-derived counts** | `calculate_procesni_rizik`'s own output | N/A | N/A (deterministic, cannot fail except on bad input) | N/A — not a probabilistic value, a rule match |
| AI task generation (`routers/zadaci.py::ai_analiziraj_predmet`) | Deterministic `_otkriveni_problemi` findings injected into the prompt verbatim, plus raw context (doc names, billing, deadlines) | list of `{naziv, opis, prioritet}` task suggestions | `gpt-4o-mini`, temp `0.2`, `max_tokens=600`, JSON-only | `predmeti`/`predmet_dokumenti`/`billing_entries`/`zadaci`/`rokovi`/`predmet_dokazi`/`rocista` (6 tables) + the deterministic findings above | `case_context(knowledge_sources=[...])` **is populated** with the exact deterministic findings the AI was given — a genuine, working explainability example; `log_action("zadaci_ai_analiza_complete")` fires on success | On GPT failure: falls back to the SAME deterministic `_otkriveni_problemi` list, not a cruder heuristic | No confidence field stored on created tasks at all |
| Genome-delta alert text (`routers/case_dna.py::_delta_alert_text`, `_verifikacija_alert_text`) | `_compute_delta()`'s already-computed delta dict, or `verify_genome()`'s `hard_flags` | formatted alert `opis` string | **No AI — pure string templating over already-computed numbers** | Genome delta / verification result (produced elsewhere, not this domain's concern) | Inherits whatever the canonical `create_proactive_alert()` (Program Alpha) provides | N/A | N/A |
| Dashboard health score (`routers/dashboard.py::matter_health_score`) | predmet_id | health score + problems | **No AI — delegates entirely to `calculate_procesni_rizik`/`identify_case_problems`** | Same canonical risk engine | N/A | N/A | N/A |

---

## 2. Facts / Inference / Recommendation assessment

**`ai_analiziraj_predmet` is the one genuinely mixed-layer operation in this domain, and it already
implements the Facts→Inference boundary correctly, in code, not just in a comment:**

- **Facts**: `_otkriveni_problemi` (deterministic, computed before any LLM call).
- **The prompt explicitly forbids the model from re-deriving facts**: *"za nedostajuće dokumente/dokaze i
  kritične rokove: koristi ISKLJUČIVO nalaze iz POZNATI PROBLEMI iznad... ne nagađaj iz naziva fajlova da
  li dokument postoji"* (for missing documents/evidence and critical deadlines: use EXCLUSIVELY the
  findings above — don't guess from filenames whether a document exists). This is a real, working "Facts
  Before AI" implementation, not aspirational language.
- **Recommendation**: the model's own task suggestions for the 2 genuinely judgment-shaped categories
  (inactivity, unbilled amount) — and even these are threshold-based enough that the exception-path
  fallback reproduces them deterministically without any LLM at all (`if dana_neaktivnosti > 14`, `if
  nefakturisano_rsd > 50000` — see the fallback code, which is NOT a cruder approximation, it's the exact
  same logic the prompt asks the model to apply).
- **Residual soft spot**: the model still generates each task's free-text `opis` itself, with no code-level
  check that the description doesn't add invented specifics beyond the injected facts — a prompt-only
  guardrail, not a code-enforced one. Lower severity than a fabricated fact/number, since `naziv` and
  `prioritet` (the fields actually driving downstream action) are constrained; `opis` is advisory prose.

**Everything else in this domain has no Inference/Recommendation layer at all** — Search, task detection,
alert text, and dashboard scoring are 100% Facts, mechanically derived, zero LLM involvement.

## 3. Evidence Chain

- **Task detection → Task Engine → Alerts → Dashboard**: fully traceable. Every number a lawyer sees
  (health score, problem count, alert text) resolves, in one or two hops, to a real, named DB query or a
  pure function of one — no broken link found in this domain.
- **AI-generated task `opis` text**: **not** independently evidence-chained beyond the prompt-level
  instruction above — this is the one place in the domain where "why does this task exist" is answered by
  "the model said so, informed by real facts" rather than "this is a direct readout of a real fact."

## 4. Confidence audit

**No probabilistic confidence value exists anywhere in this domain.** Search has no confidence (pure SQL
match). Task detection has no confidence (rule match, binary). Alert text has no confidence. Dashboard
health score's confidence-shaped concerns are `calculate_procesni_rizik`'s own concern (a different
domain's fork). **This domain is confidence-clean by construction** — nothing here needs Phase 4 redesign.

## 5. Hallucination vectors, systemic vs. local

1. **`retrieval_query`/`retrieved_context_ids` unpopulated (Medium, systemic fix available, not new)**:
   confirmed unchanged from Program Alpha's finding hours earlier. Systemic fix: the pipe already exists
   end-to-end (`shared/ai_provenance.py` → `shared/ai_client.py` → `security/ai_forensics.py`) — this is
   purely a matter of `retrieve_documents()`'s ~15+ callers threading its own already-returned
   `retrieval_meta` into `case_context()`'s existing parameters, not inventing new infrastructure. Highest-
   leverage systemic fix in this domain for Program Beta's Phase 5 (Explainability By Design) specifically,
   because it's the SAME fix for every RAG-based AI feature in the app at once, not a per-feature patch.
2. **`ai_analiziraj_predmet`'s free-text `opis` field (Low)**: soft, prompt-only guardrail. A systemic fix
   would mean validating that generated prose doesn't introduce named entities/dates/amounts absent from
   the injected context — a real but nontrivial NLP-verification problem, not a quick win; flagged for
   Program Beta's Phase 6 (Reasoning Pipeline) to consider as a general "Explanation" stage check
   applicable to any free-text AI output, not just this one call site.

## 6. Positive patterns worth citing as the model for Program Beta's Phase 6 canonical pipeline

- `ai_analiziraj_predmet`'s "deterministic facts computed first, injected into the prompt with an explicit
  don't-contradict-them instruction, LLM only reasons over the residual" shape is close to exactly what
  Program Beta's own Phase 6 pipeline (Facts → Evidence Validation → Legal Rules → Reasoning → ...)
  describes — it should be named as a working reference implementation, not redesigned from scratch.
- `_verifikacija_alert_text`'s own docstring states the anti-hallucination principle explicitly in-code:
  *"ne izmislja 'confidence %' ili drugu vrednost koja se stvarno ne racuna nigde"* (doesn't invent a
  confidence % or another value that isn't actually computed anywhere) — this exact sentence could be the
  literal governing rule for Program Beta's `CONFIDENCE_MODEL_SPECIFICATION.md`.

---

## Summary for the parent

**Operations inventoried**: 6 (1 pure-SQL search, 1 pure-deterministic task detector, 1 mixed
facts+LLM task generator, 2 pure-template alert-text formatters, 1 pure-delegation dashboard score).
**Non-deterministic confidence values found**: 0 — this domain is confidence-clean.
**Evidence chain gaps**: 1 real (RAG provenance fields unpopulated, domain-wide, not new — same root
cause Program Alpha already named), 1 soft (AI task descriptions' free text not independently verified).
**Single highest-priority systemic fix opportunity**: wire `retrieve_documents()`'s already-returned
`retrieval_meta` into `case_context()`'s existing `retrieval_query`/`retrieved_context_ids` parameters —
one fix, ~15+ call sites benefit simultaneously, infrastructure already built and connected, nothing new
to invent. **Best positive pattern to replicate elsewhere**: `ai_analiziraj_predmet`'s
facts-first-then-constrained-reasoning prompt design, and its fallback path proving the deterministic
core works standalone without the LLM at all.