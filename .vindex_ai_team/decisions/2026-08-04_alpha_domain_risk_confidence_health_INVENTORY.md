# Program Alpha — Domain Inventory: Risk / Confidence / Health Scoring

**Scope**: every risk score, confidence score/level/percentage, and health/strength score computed
platform-wide. Read-only. All findings independently re-verified against current code today, not cited
from prior mission reports on faith.

## Decision table

| Decision | Canonical location | Consumers | # implementations | Duplicate? | Evidence |
|---|---|---|---|---|---|
| Case procedural risk / health score | `services/risk_engine.py::calculate_procesni_rizik` | `api.py`, `routers/ccc.py`, `routers/dashboard.py`, `routers/matter_intel.py`, `routers/zadaci.py`, `services/case_pipeline.py` | **1** (canonical, Nexus's `ccc.py` duplicate confirmed eliminated) | No — confirmed | `risk_engine.py:1-20` docstring cites the original 2-implementation bug (G-027) and its fix |
| Next-action / detected-problems list | `services/risk_engine.py::identify_case_problems` | Same consumer set as above | **1** (canonical; replaced 3 prior independent "next action" generators per its own docstring, and a 5th independent GPT detector in `zadaci.py`, confirmed still eliminated) | No — confirmed | `risk_engine.py:157-174`; `routers/zadaci.py:610` calls the canonical function |
| Case Genome case-strength % | `routers/case_dna.py` | Genome UI, Copilot, Firm Brain (via `_fetch_firm_memory_context`) | 1, deterministic from evidence factors | No | Positive precedent — grounded, not raw LLM self-report |
| Court Predictor confidence — qualitative level (`nivo`) | `routers/court_predictor.py::_calc_confidence_nivo` (line 1028) | Court Predictor response | 1, deterministic from `rag_hits`/`vks_hits`/`kancelarija_data`/`len(dokazi)` counts | No | `court_predictor.py:1028-1082` |
| Court Predictor confidence — numeric percentage (`procenat`) | Same function, line 1165-1190 | Same response, same UI, right next to `nivo` | **2 independent signals for one concept, never reconciled** | **Yes — real, live, confirmed today** | `court_predictor.py:1170` defaults `procenat=50`, then lines 1177-1190 overwrite it via a **separate GPT-4o-mini call** with zero cross-check against `nivo`. Nothing in the code prevents `nivo="NISKO"` + `procenat=78` in the same response. |
| Strategy Engine litigation win-probability | `strategija.py::litigation_simulator_sync` (line 224) | `routers/strategija.py` PRO endpoint | Effectively **0 backend implementations** — raw GPT text | N/A — worse than duplication, zero grounding | `strategija.py:224-239`: returns `resp.choices[0].message.content` verbatim. The prompt (`_LITIGATION_SYSTEM`, lines 124-149) *instructs* percentage calibration but nothing in code parses, validates, or independently computes it. Confirmed unchanged from Keystone's K-3. |
| Evidence "strength" (`snaga`) — auto-classification path | `routers/evidence.py:221` (inside `klasifikuj_i_sacuvaj`) | Feeds directly into `calculate_procesni_rizik`'s `snaga_count` tally | **Structurally constant**, not duplicated but silently defeats the canonical formula | **New finding, not previously named this way** | Hardcoded `"snaga": "srednja"` for every AI-extracted fact, regardless of the AI's own assessment — see "Hidden logic" below |
| Evidence "strength" — manual entry path | `routers/evidence.py:298,323` | Same table, different endpoint | 1, user-supplied, legitimate | No | Default `"srednja"` is a form default, user can override — not the same defect as the auto-path |

## Hidden logic found

1. **`routers/evidence.py:221`** — the AI classification pipeline extracts `kljucne_cinjenice` (key facts)
   and `pravni_elementi` (legal elements) from real model output, but discards any strength signal the
   model might have and hardcodes `"srednja"` unconditionally. This is not a duplicate implementation —
   it is a **silent default masquerading as AI-derived data**, feeding directly into the one canonical
   risk formula and structurally flattening its most evidence-sensitive input for every
   auto-classified document. `calculate_procesni_rizik`'s own docstring (line 3) calls itself "jedini
   deterministicki izvor istine" — but one of its primary inputs is, for the AI-classification path,
   not really a measurement at all.
2. **`routers/court_predictor.py:1170-1190`** — a second, independent, unvalidated LLM call producing a
   number presented as if it were the AI's calibrated confidence, sitting next to a genuinely deterministic
   signal (`nivo`) computed two lines above it, with no code path connecting the two. This is exactly
   Program Alpha's "No Duplicate Decisions" principle violated: two modules (the deterministic tallying
   logic and the raw GPT call) both answer "how confident should the lawyer be," and neither defers to
   the other.

## Source-of-truth violations

- **Risk/health score**: single author (`risk_engine.py`), multiple legitimate readers. **No violation.**
- **Court Predictor confidence**: two authors of what a lawyer perceives as one number (`nivo` computed
  deterministically; `procenat` computed by an independent, unchecked GPT call, displayed together in the
  same response). **Rank: Critical**, per Program Alpha's own rule ("Ako postoje dva autora istog podatka:
  to je Critical") — the two values are presented adjacently as if describing the same assessment, and
  nothing prevents them from contradicting each other.
- **Strategy Engine litigation percentage**: zero deterministic author at all — the "author" is an
  unconstrained LLM completion. Arguably a more severe violation of Principle 5 ("Evidence Before
  Opinion") than a two-author case, since there is no canonical author to defer to at all yet.
- **Evidence strength (auto-path)**: one nominal author (`evidence.py`'s classification handler) but the
  value it writes is not actually derived from evidence — a "false single source of truth" masking what
  should be a per-fact, AI-derived signal.

## Prioritized recommendations (for Phase 5 synthesis, not decided here)

1. **Court Predictor's `procenat`** — highest priority. Concrete elimination path: either (a) derive
   `procenat` deterministically as a bounded range keyed off `nivo` (e.g., `nivo` maps to a canonical
   percentage band, no second GPT call needed at all — reduces 2 implementations to 1, removes an entire
   GPT call), or (b) keep the GPT call but clamp/reconcile it against `nivo` server-side before returning,
   with a hard rule that a contradiction is never returned to the user. Option (a) is the more thorough
   "eliminate the class of defect" fix per Program Alpha's own directive — no reconciliation logic needed
   if there's only one author.
2. **Strategy Engine's litigation percentage** — same shape as Keystone's K-3/`KEYSTONE-004`, still open.
   Real fix requires the same category of work as (1): a deterministic confidence layer, or explicitly
   demoting the percentage to advisory prose with no numeric claim (removing the number is itself a valid
   "eliminate the defect class" option Program Alpha's principles support — Evidence Before Opinion doesn't
   require a fabricated number to exist at all).
3. **Evidence auto-classification `snaga` hardcode** — lower complexity to fix than 1/2 (a single field,
   one call site), but currently silently caps a canonical, already-correct formula's sensitivity. Fixing
   this doesn't reduce implementation *count*, but it is exactly the kind of "hidden logic that defeats a
   canonical service" Phase 3 is chartered to find.

## Summary for parent

**Total decisions mapped: 8** (procedural risk/health, next-action detection, Genome strength, Court
Predictor nivo, Court Predictor procenat, Strategy Engine litigation %, Evidence auto-strength, Evidence
manual-strength). **New duplicates/violations found this pass: 2 real, live ones** — Court Predictor's
nivo/procenat split (Critical, two authors of one perceived value) and Strategy Engine's litigation
percentage (zero grounding, worse than a duplicate). Nexus's prior fixes (ccc.py health_score, zadaci.py's
5th detector) are both confirmed still intact — no regression. The evidence auto-strength hardcode is a
new framing (not previously described as a source-of-truth violation, just as a data-quality gap) but the
underlying fact was already known from Nexus/Keystone.

**Single highest-priority canonicalization target**: Court Predictor's `nivo`/`procenat` split. It is the
clearest "two authors, one concept, Critical by the mission's own rule" case in this domain, has a
concrete, low-risk elimination path (derive `procenat` from `nivo` deterministically, deleting the second
GPT call entirely — this REDUCES complexity: one call site instead of two, one source of truth instead of
two, per Program Alpha's Phase 7 regression-analysis requirement), and is more tractable than Strategy
Engine's litigation percentage (which needs a larger grounding-layer design decision, not just a
reconciliation).