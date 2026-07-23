# Phase 0.5 — Reality Calibration

Evaluation framework (not a one-off script — founder, 2026-07-23: *"Nemoj
praviti skriptu. Pravi infrastrukturu za evaluaciju."*), reusable for
future evaluations (LRE v2, Precedent Engine, Draft Engine, Adversarial
Review).

Governing document: `docs/architecture/LEGAL_REASONING_ARCHITECTURE.md`,
Phase 0.5.

## The question this answers

Not "does LRE run" — **"is LRE's Reasoning Graph a materially better model
of the case than Genome's existing `argumenti_za`/`argumenti_protiv`/
`kontradikcije` fields, judged by an experienced lawyer against real
cases."** If it isn't, Phase 1 (migrating those fields to LRE) does not
happen — a prettier architecture is not sufficient justification for
replacing a working system.

## Process

1. **Curate the dataset** (founder, manual, never automatic). Copy
   `datasets/dataset_manifest.template.json` to `datasets/dataset_manifest.json`
   and fill in 20–30 real predmet_ids, one or more per profile category
   (simple/complex civil, labor, enforcement, family, contradictory
   evidence, weak documentation, heavy documentation). Synthetic or
   calibration-batch cases are excluded — same lesson G-027's validation
   already taught this project (synthetic samples distort results toward
   test-data artifacts).
2. **Run** (`python evaluation/phase_0_5/run.py datasets/dataset_manifest.json`).
   For each case: reads Genome's existing fields unchanged, runs LRE
   (`generate_reasoning_graph`), reconstructs both into comparable
   structures, and **blind-labels** them as "Analysis A" / "Analysis B"
   (random per case) — writes `outputs/blinded/{id}.json` (what the lawyer
   sees) and `outputs/keys/{id}.json` (the real mapping, kept separate).
3. **Score, blind.** The lawyer reviews `outputs/blinded/{id}.json` for
   each case — without knowing which is Genome and which is LRE — and
   fills in `score_sheet` per the metrics in `metrics.py`, including which
   analysis they'd trust more for drafting, and whether it changed their
   reasoning about the case (the single most direct value signal: *"Nisam
   primetio kontradikciju... LRE: označio kontradikciju... Advokat: tačno,
   ovo sam propustio."*).
4. **Reveal and aggregate** (`python evaluation/phase_0_5/compare.py`) —
   only now does the A/B → genome/lre mapping get read. Produces per-metric
   averages, win counts, and a mechanical (not automatic) gate verdict.
5. **Report** (`python evaluation/phase_0_5/report.py`) — human-readable
   summary of the same data.

## Hard prerequisite (binding, not optional)

`services/legal_reasoning_engine.py::_retrieval_agreement` must be
identity-based (fixed 2026-07-23) before these numbers mean anything —
methodology cannot change mid-experiment. If retrieval scoring changes
again, restart Phase 0.5 from case #1, don't patch results in place.

## Dataset selection rule (binding, founder 2026-07-23)

**Do not hand-pick "interesting" or "best" cases.** When the pilot
starts: take the **first 30 new cases** that fall into the profile
categories in `datasets/dataset_manifest.template.json`, in the order
they arrive — not the ones you expect the AI to shine on. Picking
favorable cases is selection bias, and it invalidates the whole
comparison. The manifest's `selection_method` field exists so this rule
is recorded, not left to memory — `run.py` prints a warning if it isn't
set to `"prvih_30_novih_po_kategoriji"`.

## Reading the result — don't stop at the overall average

`report.py` prints a per-profile breakdown matrix, not just one number.
Founder: *"Možda ćeš otkriti da je LRE fantastičan u jednoj oblasti, a
loš u drugoj. To je mnogo vrednije nego jedna ukupna ocena."* A tie in
the overall average can hide a real, actionable pattern in the matrix.

## When LRE loses a case

Log it in `FAILURE_LOG.md` — not as a bug report, but as *why* it lost
(reasoning category, not stack trace). This is the input future
engineering work actually needs; an averaged score alone doesn't tell
you what to fix.

## After scoring is complete

Fill in `PHASE_0_5_DECISION.md` — three possible outcomes (GO / GO WITH
FIXES / NO GO), criteria fixed *before* looking at results, so the
decision isn't made on enthusiasm. Same discipline as this project's
other decision-model documents (e.g. `docs/architecture/
G030_NEXT_ACTION_DECISION_MODEL.md`).

## Files

- `metrics.py` — the 7 scored dimensions + blind-label assignment (true randomness, not derived from predmet_id).
- `run.py` — generates blinded comparisons from a curated manifest.
- `compare.py` — reveals labels after scoring, aggregates overall AND per-profile.
- `report.py` — renders `compare.py`'s output as a readable table + matrix.
- `FAILURE_LOG.md` — why LRE (or Genome) lost specific cases, not a bug list.
- `PHASE_0_5_DECISION.md` — GO / GO WITH FIXES / NO GO, criteria fixed in advance.
- `datasets/` — manifests (curated, not committed with real predmet_ids — see `.gitignore`).
- `outputs/` — blinded comparisons + keys + scores (real case data — never committed, see `.gitignore`).
