# G-030 — Next Action Ownership Analysis

**Date:** 2026-07-22
**Type:** Discovery only. **No code changed, no architecture decided.** This document answers "what exists today and how does it work" — the merge/no-merge/canonical-source decision is explicitly the founder's, matching the same discipline used for G-027 and G-034.

---

## The four systems, precisely

| System | Where it lives | Algorithm | Inputs | Where it's displayed |
|---|---|---|---|---|
| **Cockpit `sledeca_akcija`** | `api.py:4587-4634` (`_fetch_cockpit_ai`, called from the `/workspace` endpoint) | **GPT-4o-mini, free-form.** System prompt explicitly tells the model the risk *level* is pre-computed and not to re-decide it — but `sledeca_akcija.{opis, rok, prioritet}` is entirely the model's own judgment, generated fresh on every request. | Predmet naziv/tip/status/opis, party names, document filenames, last 3 notes, last 5 hronologija entries, the deterministic risk level (for context only) | `index.html` "Sledeća akcija" card, top of the "Pregled predmeta" tab — the **first thing shown** when a case is opened |
| **Matter Intel `sledeca_radnja`** | `routers/matter_intel.py:193-223` (`_compute_next_action`) | **Fully deterministic if/elif tree. Zero GPT calls.** Its own docstring confirms this explicitly (and corrects an earlier wrong docstring claiming otherwise, fixed 2026-07-18). | `kriticni_rokovi` count, `snaga_dokaza` label, `nedostajuci_dokazi` list, `predstojeći_rokovi` count, `tip predmeta` — the exact same underlying signals `services/risk_engine.py::calculate_procesni_rizik` uses | `mi-sledeca` element in the Matter Intel stats section — **currently hidden** (deliberately suppressed in the 2026-07-22 scorecard merge, commit `c91e0de`, specifically because it visually duplicated Cockpit's card; the data is still computed and returned by the API, just not rendered) |
| **Case Ready Score `copilot_preporuka`** | `services/case_pipeline.py::_step_copilot_preporuka` (line ~547) | **GPT-4o-mini, free-form.** Not idempotency-gated like the pipeline's other steps — regenerates fresh every manual pipeline run. | Predmet naziv/opis/tip, `rizik_nivo` (**from the pipeline's own separate GPT-generated risk snapshot, `_step_risk_snapshot` — NOT `services/risk_engine.py`**), and rok count from the pipeline's own deadline-extraction step | `pred-crs-copilot` block, only after the user manually clicks "Analiziraj" (`POST /api/predmeti/{id}/pipeline`) — hidden by default, no auto-load |
| **`workflow.py` `sledeci_korak`** | `routers/workflow.py:428` (`PATCH /api/workflow/step/{id}/zavrsi`) | **N/A — different concept entirely.** This is the next *step in a predefined, explicitly-started workflow template* (e.g., a firm-authored checklist for "debt collection process"), not an AI-generated strategic suggestion. Only exists if a workflow was started via `POST /api/workflow/pokreni` for that specific predmet. | The workflow template's own predefined step order | A transient toast ("Sledeći korak: X") after completing a step, plus the persistent step checklist in the dedicated Workflow/Zadatci panel — **not shown on "Pregled predmeta" at all** |

## Correction to the standing "4 competing systems" framing

Every prior audit (`VINDEX_INTEGRATION_MASTER_PLAN.md` finding #7, `VINDEX_AI_UX_SIMPLIFICATION_STRATEGY.md` Top 10 #2, the Gap Register's G-030 entry) describes this as "4 independent, non-communicating systems." Having now read all four implementations directly: **`workflow.py` is not actually competing for the same question.** It answers "what's the next step in a process the firm explicitly started," not "what should the lawyer do about this case right now" — it's opt-in, per-predmet, and never appears on the same screen as the other three. It doesn't contradict them; it's orthogonal.

**The real conflict is 3-way, not 4-way: Cockpit, Matter Intel, and Case Ready Score all answer the same question** ("what should I do next on this case") **for the same user on adjacent parts of the same screen**, with three independently-computed answers that can disagree.

## A second finding, adjacent but real: two different "risk" inputs feed two of the three

Cockpit's next-action generation is given `services/risk_engine.py::calculate_procesni_rizik`'s deterministic output as context (post-G-027). Case Ready Score's `copilot_preporuka` is given a **different, separately GPT-generated** risk assessment from the pipeline's own `_step_risk_snapshot` — which has no connection to `risk_engine.py` at all (this is the same disconnect already logged as **G-034**, "Resolved — Evidence insufficient" for the Genome-vs-risk_engine question specifically, but it applies here too in a different pairing: case_pipeline's risk snapshot vs. risk_engine). This means even before you get to "which next-action wins," two of the three systems aren't reasoning from the same facts about the case's risk level.

## Authority today (by actual exposure, not by design intent)

Ranked by how likely a user is to actually see each one:

1. **Cockpit** — always visible, first thing shown, auto-refreshed every time a case is opened. Highest exposure. Also the **least deterministic** of the three (free-form GPT, no caching, re-generated per request, and its `prioritet` field is a pure model judgment call with no deterministic backing — the same category of AR-01 concern already flagged as G-029, not yet actioned).
2. **Case Ready Score's copilot_preporuka** — only visible after a manual click, and only if it happens to be non-empty from the last pipeline run. Second-highest exposure, but gated behind user action.
3. **Matter Intel's sledeca_radnja** — computed on every load, but **currently not rendered at all** (hidden in the scorecard merge). Zero visual exposure today despite being the only fully-deterministic one of the three.

**The most-seen system is the least deterministic one, and the most-deterministic system is currently invisible.** That inversion is worth naming plainly — it's not a defect of this analysis, it's the actual state of the product today.

## Candidate canonical-source shapes (discovery-level observation, not a recommendation to build)

Not a decision — the founder's call, same as G-027/G-034. Naming what's already visible in the code as a *possible* direction, because `services/risk_engine.py` already proved this shape works once:

- Matter Intel's `_compute_next_action` is already structured the way G-027's fix made `calculate_procesni_rizik`: deterministic, rule-based, reusing the same underlying signals as the risk engine. It's the only one of the three that doesn't have an AR-01 exposure.
- Cockpit's GPT call already receives the deterministic risk level as input and is *instructed* not to re-derive it — the same "GPT explains, doesn't decide" pattern from G-027 exists for risk *level* in this exact code today, but is not yet applied to *next action* the same way. `sledeca_akcija.prioritet` is the one field in this whole flow still fully GPT-decided (this is G-029, previously logged, not yet actioned).

If a canonical source is eventually chosen, this existing pattern (deterministic decides what/priority, GPT phrases why/how) is already proven in this codebase once — that's a fact about precedent, not a proposal to act on it now.

## What would need empirical validation before any merge decision (same discipline as G-027/G-034)

1. Do the three systems' recommendations actually *disagree* on real cases, or do they usually converge (same pattern as G-027's Cockpit/Matter Intel risk comparison, which turned out to genuinely disagree — but that isn't yet proven here)?
2. If Matter Intel's rule-based engine were made visible again, would its (currently generic, templated) phrasing feel materially worse to a lawyer than Cockpit's GPT-tailored phrasing, independent of which one is more "correct"?
3. Does `case_pipeline.py`'s separate risk snapshot ever meaningfully diverge from `risk_engine.py`'s deterministic value on real cases — this is testable with the same script pattern as `g027_risk_validation.py`/`g034_risk_validation.py`.

No implementation follows from this document. Next step is the founder's decision on whether/how to run that empirical check.
