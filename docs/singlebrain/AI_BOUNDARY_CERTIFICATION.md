# AI_BOUNDARY_CERTIFICATION.md — Operation Single Brain, Team 4

For each of 6 named values, can GPT author or override it anywhere in the platform? Independently
re-verified from current code, not cited from Operation One Truth's own same-day audit.

## Where the boundary genuinely holds (re-confirmed)

- **Risk**: `services/risk_engine.py` — zero GPT calls, confirmed by full-file read.
- **Readiness**: `shared/case_readiness.py` — zero GPT calls, confirmed structurally (only import is
  `shared.attention_priority`). `compute_case_readiness()`'s signature has no parameter through which a GPT
  value could be injected.
- **Health**: `routers/health_index.py::_compute_health` — fully deterministic weighted sum, clamped. GPT
  (`_compute_chief_partner`) only produces a separate narrative string, never fed back into the numeric
  score. `risk_engine.py`'s per-case `health_score` is likewise deterministic and clamped.
- Matter Intel's `preflight_check` `status`/`score` — clamped and enum-validated (BLACKSWAN-AI-001 fix,
  confirmed present); dead endpoint, zero frontend callers, not a live threat regardless.
- Hearing CC's `hearing_score` — has both an unconditional 0-100 clamp AND the readiness-tier cap, the most
  rigorously bounded of the 4 success-probability generators.
- CIO's `kriticnost` — unconditionally clamped and reference-validated against real portfolio case IDs.
- Court Predictor's Confidence Check — the cleanest example in the codebase: the number is derived purely
  from RAG-hit counts/VKS-hit counts/firm win-rate/readiness, and GPT is explicitly instructed not to state
  a percentage at all.

## Confirmed gaps — 8 concrete, independently reproducible

1. **`kontradikcije[].tezina` (Genome's raw GPT field) flows unvalidated into `case_actions.prioritet`,
   which then drives `CRITICAL_GAP` readiness — a novel finding, not caught by Operation One Truth.**
   `_compute_target_actions`'s Rule 3 maps `tezina` via `_TEZINA_PRIORITET.get(k.get("tezina"), "medium")`
   with no code-side validation of `tezina` itself (unlike `kontradikcije`'s *location* references, which
   ARE validated). Reproduction: a Genome extraction labels any contradiction `"tezina": "kriticna"` —
   nothing constrains this beyond the model's own judgment — and the case's canonical readiness becomes
   `CRITICAL_GAP` off one unchecked AI self-classification.
2. **Same root cause reaches Priority** — `case_actions.prioritet`, the canonical priority field, is set
   directly from the same unvalidated `tezina` field.
3. **`digital_twin.py::kreiraj_simulaciju`** — only the readiness-tier cap exists, **no unconditional 0-100
   clamp**, unlike Hearing CC's sibling fix.
4. **`digital_twin.py::sta_ako_analiza`** — same gap.
5. **`court_predictor.py::prediktuj_ishod`** — same gap; `procenat_min`/`procenat_max` returned raw
   whenever readiness isn't at an extreme, with no `min<=max` ordering check either.
6. **Compounding gap across #3-5**: the readiness-tier cap itself is silently disabled whenever
   `build_case_context()` throws — a transient DB/context-fetch error fully removes the only guard these 3
   sites have, even for a genuinely `CRITICAL_GAP` case.
7. **Opponent Intel's `pouzdanost`** — mostly GPT self-declared; only forced to `"niska"` when literally
   zero data exists. One weak RAG hit lets GPT's own "visoka"/"srednja" choice pass through unchecked.
8. **Genome's `genome_kompletnost`** — fully GPT self-declared, zero code-side check, yet feeds a real -15
   penalty into `compute_snaga_score()` — the field marketed elsewhere as "backend-recomputed, not GPT's
   raw number" has one un-audited GPT-controlled input.

**Reproduction for #7**: call Opponent Intel with any query producing even one generic RAG hit — GPT can
freely return `"pouzdanost": "visoka"` regardless of how thin that hit actually is.

**Reproduction for #8**: GPT extraction returns `"genome_kompletnost": "visoka"` for a case with 0 real
documents — nothing cross-checks this against actual document count, silently inflating the canonical
strength score by skipping a penalty it should apply.

## Final count

**4 of 6 named values (Readiness, Priority, Success Probability, Confidence) currently have a real,
unguarded or under-guarded GPT-authorship path.** Risk and Health are clean — verified zero GPT influence
on either's numeric output. This is narrower than a naive read of "GPT overwrites a deterministic engine's
output" (no such direct overwrite was found anywhere) — the actual pattern is that specific GPT-authored
sub-fields inside otherwise well-guarded features slip through because the clamping discipline visible
elsewhere in the same codebase was applied per-field, not systematically.

## Certification verdict (Mission 001)

All 8 gaps above were closed in Mission 001's own Phase 3 (see `docs/singlebrain/
FINAL_SINGLE_BRAIN_CERTIFICATE.md`'s ledger, gaps #1-2 via `normalize_tezina()`, #3-5 via
unconditional clamps, #7 via evidence-tiering, #8 via enum-normalization). Gap #6 (the
compounding readiness-tier-cap-fails-open issue) was explicitly deferred as `SINGLEBRAIN-DEBT-010`
rather than fixed, for the reason stated in that mission's own debt register entry.

---

## Mission 002 update (2026-08-07) — Team 3 re-verification + new findings

Team 3 independently re-verified all 8 Mission 001 gaps against current code (not cited from the
prior report) and confirms all 8 still hold closed. Re-confirmed `SINGLEBRAIN-DEBT-002` and
`SINGLEBRAIN-DEBT-010` were both still genuinely open at the start of Mission 002.

**Closed this mission:**

- **`SINGLEBRAIN-DEBT-002` — `court_predictor.py::argument_reputation`** now applies the same
  `CAP_BY_READINESS` tier cap its sibling `prediktuj_ishod` already had — both the per-argument
  `uspesnost_procena` and the overall `ukupna_snaga` are readiness-capped, not just range-clamped.

**New gap found and closed — the single most direct violation of Acceptance Criterion 2 found in
either mission**: `strategija.py`'s F10 orchestrator "AI Sudija" verdict step
(`orkestrator_kompletna_analiza_sync`, korak 5) had **zero server-side clamp or validation** on
`procena_uspeha_tuzilac` (documented 0-100, returned raw), `izreka` (documented 3-value enum,
returned raw), or `confidence` (documented 3-value enum, returned raw). The frontend only clamped
the progress-bar *width*, never the displayed number text. Reproduced with an actual poisoned
response (`procena_uspeha_tuzilac: 9999`, `izreka: "TUZBA SIGURNO USVOJENA STOPOSTOTNO"`) proven to
reach the live, UI-wired `POST /api/strategija/kompletna-analiza` response unmodified. Now
clamped/enum-guarded, fail-safe toward the non-extreme values on the same "don't overstate
certainty" philosophy used throughout this engagement.

**New gap found and closed — the sibling-field pattern recurring a 3rd time**: Genome's `heatmap`
and `dokazi_rang[].snaga_score` sub-fields had never been clamped, even though the headline
`snaga_predmeta_procent`/`kriticnost`/`genome_kompletnost` fields on the SAME extraction call were
already guarded (Mission 001). `dokazi_rang[].snaga_score` specifically also drives a `<70` "weak
evidence" filter downstream — an unclamped raw value could silently misclassify evidence strength.
Now clamped identically to the headline fields.

**Remaining open, unchanged**: `SINGLEBRAIN-DEBT-010` (readiness-tier cap fails open on
`build_case_context()` error) — still not fixed, for the same reason Mission 001 named: no safe
default cap value could be picked without guessing at product intent, and applying an unconditional
cap on ANY context-fetch error risks a different failure mode (understating a healthy case's
probability due to an unrelated transient error).

## Certification verdict (Mission 002)

**Every concretely-reproduced AI-boundary gap found across both missions is now closed**, except
`SINGLEBRAIN-DEBT-010`, which remains open and named rather than silently dropped. See
`docs/singlebrain/SINGLE_BRAIN_MISSION_002_FINAL_CERTIFICATE.md` for the full honest verdict against
this mission's own stricter acceptance criteria.
