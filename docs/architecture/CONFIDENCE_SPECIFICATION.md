# Document Classification Confidence Specification — Program Intake Sprint 003 (2026-08-05)

**Status: DESIGNED, NOT YET ADOPTED IN CODE** (except the narrow bounded fix in §5). Phase 4 requirement:
every classification must carry confidence, reason, evidence, and the signals used — never "GPT said so."
Full design: `.vindex_ai_team/decisions/2026-08-05_intake_sprint003_fork_taxonomy_confidence.md` (Fork B, §5).

## 1. Governing constraint (platform-wide, not invented here)

`docs/architecture/CONFIDENCE_MODEL_SPECIFICATION.md`'s existing rule applies verbatim: no confidence value
in the platform may be the LLM's own self-reported opinion whenever an already-extracted signal exists to
compute it from instead. Document classification clearly has such signals — this design is proposed as a
**4th independently-confirmed instance** of that spec's already-proven pattern (`compute_snaga_score` →
`_procenat_iz_score` → `sistemsko_upozorenje` → this), and is the concrete design `EVIDENCE_CHAIN_REGISTRY.md`
row #5 (currently **Broken** — "no grounding check exists") was waiting for.

## 2. Signal categories, ranked by reliability

1. **Keyword/phrase match** (strongest, already proven) — the same mechanism `intake_classify.py`'s
   `classify_heuristic()` already uses. **Gap found**: current heuristics cover only 10 of 13 English types
   and have zero entries for `medicinska_dokumentacija`/`finansijska_dokumentacija`/`javna_isprava` — extending
   coverage to the full canonical taxonomy is a concrete, bounded future task (word lists directly derivable
   from `evidence.py`'s own prompt docstring).
2. **Structural markers** — regex/pattern checks independent of vocabulary: court-letterhead + case-number
   format for `sudska_odluka`/`javna_isprava`; signature + notarization block for `punomocje`; tabular/
   itemized layout with currency amounts for `finansijska_dokumentacija`; dated-header + salutation shape for
   `dopis`. Genuinely programmatically detectable, satisfying the mission's "distinguishable by actual
   signals" requirement independent of keyword luck.
3. **Filename hint — weak only, capped, never sufficient alone.** Adversarial-prone (any file can be named
   anything); must never push a classification over auto-accept by itself; must be visibly tagged as weak in
   `signals_used`, never silently blended into one number.
4. **Case-type prior — conditionally available, weak adjustment only.** When `predmet.tip` is already known
   (`EXPECTED_DOCS[tip]` gives a Bayesian-style nudge), a legitimate weak signal — but Pipeline B/C is
   document-first, so the case may not exist yet at classification time; must degrade gracefully to "absent."

## 3. How confidence is computed — combination, never raw self-report

Extends the platform's already-proven `baseline + Σ(factor adjustments) → clamp[0,1]` shape, applied to a
categorical classification:

- **Path 1 — deterministic keyword hit.** `0.85 base + 0.05 per additional independent corroborating signal
  (structural marker, case-type-prior agreement), capped at 0.97` — never 1.00 (even a keyword+structural
  double-hit could be a misfiled quote — a cover letter that quotes "TUŽBA" while attaching one).
- **Path 2 — no keyword hit, LLM fallback, NOT via self-reported confidence.** The model is asked to (1)
  propose a type/subtype AND (2) quote the literal text span it based that decision on. A deterministic
  post-hoc check verifies the quote is found VERBATIM in the source — the exact mechanism already proven for
  evidentiary claims (`routers/evidence.py::_lociraj_tvrdnju`/`_snaga_iz_lokacije`, Program Beta), applied to
  classification justification instead. Formula: `0.5 baseline (neutral) + 0.30 if quote is grounded (found
  verbatim) + 0.10 if an independent structural marker also fires + 0.05 if filename hint agrees (capped,
  weak) + 0.05 if case-type prior agrees (when available) − 0.20 if the model's reasoning contains hedge
  language ("možda", "nije jasno") — negative-only signal, never counted upward`. Clamp to [0,1].
- **Explicit rejection of trusting raw LLM self-report anywhere in this design.** Mirrors `_snaga_iz_
  lokacije`'s own asymmetry: a verified-grounded claim is trusted more than an unverifiable positive
  self-report; an honest negative signal (hedge language) is still informative even though a positive
  self-report is not. "Not found" (grounding failed) does NOT mean "wrong" — paraphrase is possible — so the
  baseline stays neutral (0.5) rather than punitive, mirroring `_snaga_iz_lokacije`'s own choice to default
  unverified claims to "srednja" (neutral), not "slaba" (weak).

## 4. Thresholds — reuse the existing platform default, differ by granularity level

- **Reuse `AUTO_ACCEPT_THRESHOLD = 0.90`** (`shared/intake_documents.py`) for parent-level classification — no
  new number invented without cause.
- **Parent and subtype get independent confidence, never blended** — mirrors the Confidence Graph's own
  already-proven per-entity design one level up. A document can be accepted at 0.93 as `sudska_odluka` while
  its `presuda`-vs-`resenje` subtype sits at 0.55 (genuinely harder — the two document types' title blocks are
  structurally near-identical and each necessarily quotes the other's name in boilerplate). If parent clears
  0.90 but subtype doesn't clear its own threshold: accept the parent, surface only the subtype ambiguity as
  a review-queue item (`reason=classification_uncertain`, already a valid value in migration 074's CHECK
  constraint) — don't block the whole document on subtype ambiguity a lawyer may not even care about.
- **`dopis` is structurally harder, by design, not a future bug report.** Ordinary correspondence has no
  reliable fixed opening phrase the way "ТУЖБА"/"ПРЕСУДА" does — expect it to have a structurally higher
  review-queue rate than `sudska_odluka`/`podnesak`/`punomocje`, and track it separately once volume
  accumulates rather than reading a high `dopis` review rate as a broken classifier.
- **`izvestaj`-shaped documents must never clear auto-accept on a single keyword hit** — a hard classifier-
  design rule (§3.8 of the Taxonomy), not a threshold number, since that one word is genuinely compatible
  with 3 different canonical parents.

## 5. What `evidence`, `reason`, and `signals_used` must concretely contain

- **`evidence`**: the literal quoted text span (verbatim substring, with page/paragraph/offset via the same
  `_lociraj_tvrdnju`-style mechanism already built for `kljucne_cinjenice`) — never a paraphrase, never
  generic prose.
- **`signals_used`**: a structured object reusing the exact JSONB shape already established by
  `intake_processing_outcomes.entity_confidence`: `{"keyword_match": {"phrase": "TUŽBA", "offset": 42} | null,
  "structural_marker": {"type": "court_letterhead", "found": true} | null, "filename_hint": {"value": "...",
  "weight": "weak"} | null, "case_type_prior": {"tip_predmeta": "parnicno", "agrees": true} | "unavailable"}`.
- **`reason`**: one short, concrete, actionable sentence a lawyer can verify in under 10 seconds by looking
  at the document — never "AI determined this is a lawsuit with 87% confidence." Example: *"Naslov na vrhu
  prve strane sadrži 'TUŽBA'; tekst ne sadrži 'ODGOVOR NA TUŽBU', pa je ta alternativa isključena."* Mirrors
  migration 074's own `correction_reason` design principle ("zašto", not just "šta"), applied forward.
- **`classification_method`** tag always present (`heuristic | llm | llm_grounded`) — a heuristic hit and a
  grounded-LLM guess must never be blended into one undifferentiated number without the method staying
  visible downstream, matching the Confidence Graph's existing per-entity discipline.

## 6. Self-skepticism check (required by the mission charter)

This design recommends trusting raw LLM self-reported confidence for document classification **in zero
places**. The two places an LLM's output is used at all (Path 2's type/subtype guess, and its quoted
grounding span) are both treated as *proposals* — accepted only after deterministic scoring combines them
with grounding/structural verification. The one place a raw model signal (hedge language) enters the formula
at all, it is used exclusively as a downward adjustment, never upward.

## 7. Bounded fix already implemented this sprint, ahead of full adoption

Full adoption of this confidence model requires rewriting classifiers and is future work (§6 of
`CANONICAL_DOCUMENT_TAXONOMY.md`). One narrow, bounded piece was implemented THIS sprint without waiting for
that larger rewrite: `routers/smart_intake.py::finalize_intake_job` now reads the ALREADY-COMPUTED confidence
signal Pipeline B produces (`intake_review_queue`'s `low_confidence_fields`, previously fetched and silently
discarded) and uses it to (a) prevent a confidence-blind second classifier from silently overwriting an
already-flagged-uncertain value, and (b) surface `klasifikacija_nesigurna`/`nesigurna_polja` explicitly in
the finalize response. This is not the full confidence model above — it's the smallest change that stops the
platform's worst violation of this spec's own core principle ("never let an uncertain classification look
confident") using signals that already exist today. See `REVIEW_QUEUE_SPECIFICATION.md` for full detail.
