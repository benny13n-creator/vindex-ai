# Genome Verification Layer — Bootstrap Evaluation Report

Status: **blocked — no data to evaluate.** Requested per
`PHASE_1_EXECUTION_CHECKLIST_2026-07-18.md` §1.3 Rule C and the 2026-07-18
follow-up instruction to complete Phase 1 validation closure before Phase 2.
This report documents why the evaluation could not run as specified, rather
than fabricating results against synthetic data.

## Dataset description

**Intended:** 20-30 representative Genome outputs pulled from live production
(`predmeti.case_dna`), spanning a range of `snaga_predmeta_procent` and
document counts, each with its source `predmet_dokumenti` for provenance
cross-checking.

**Actual, verified live against the production database** (same
`SUPABASE_URL`/service-role credentials already confirmed correct via
`scripts/audit_state.py` earlier in this project):

| Table | Row count |
|---|---|
| `predmeti` | 1 |
| `predmet_dokumenti` | 0 |
| `predmet_genome_history` | 0 |
| `events` (context check — confirms this is genuinely the live DB, not an empty project) | 80 |

The single `predmeti` row (`created_at: 2026-07-01`, the date Case Genome was
first built per project history) has `case_dna: null` — never populated, or
reset since. **There are zero real Genome outputs in production to sample.**
This was checked directly, not inferred: `scripts/genome_bootstrap_sample.py`
(committed alongside this report — reusable once real data exists) queried
the last 500 `predmeti` rows and found none with a non-empty, non-error
`case_dna`.

This is consistent with, and sharper than, the earlier
`CASE_GENOME_GAP_ANALYSIS_2026-07-18.md` finding that `evaluation/lec/` and
`evaluation/hall_of_shame/` are both empty placeholders, and the
`project_strategic_direction` pilot (3-5 firms) hasn't launched. That
finding was "no *annotated* evaluation data yet." This finding is stronger:
**no real *usage* data yet for Case Genome specifically** — the feature has
had months of architecture and reliability work built on top of it (this
entire Phase 1) without a single real case having gone through it end to end
in production.

## Validation methodology (as designed, not executed)

Per the checklist: run `shared/genome_validator.verify_genome()` **unmodified**
against each sample, then manually review each Genome against its source
documents for (1) factual correctness, (2) provenance/source availability,
(3) evidence ranking quality, (4) risk assessment quality, (5) strategy
usefulness — counting where the validator's flags agreed or disagreed with
manual judgment. This methodology is sound and unchanged; it has nothing to
run against.

## False positive rate — not measurable

## False negative findings — not measurable

## Unsupported claim rate — not measurable

All three require real Genome outputs checked against real source documents.
Reporting a number here would be inventing evidence in a document whose
entire purpose is to prevent that.

## Recommended adjustments

**None to `shared/genome_validator.py`.** There is no evidence to base an
adjustment on — changing the validator now would be exactly the "missing and
speculative" category the Architecture Bible's Rule A exists to block.

**The actual recommendation is upstream of validator tuning:** Case Genome
needs at least one real predmet with real documents run through it before
this evaluation — or any Rule A evidence-gated Genome work — can proceed on
anything but guesswork. Two paths, not mutually exclusive:

1. **Fastest, smallest:** the founder runs 3-5 real (or realistic, real-content)
   predmeti through the existing UI — upload real documents, let Genome
   refresh normally. This alone would produce enough for a first honest
   bootstrap round, well short of the full pilot.
2. **The already-planned path:** `project_strategic_direction`'s pilot (3-5
   law firms) and LEC population (150-200 annotated documents) — founder's
   task, not scheduled here — would produce this data plus far more, as a
   side effect of starting.

Neither is a Phase 2 blocker on its own merits, but per the explicit
instruction ("do not proceed to Phase 2 until Phase 1 validation closure is
complete"), this needs your call, not mine, since the missing piece is real
data collection, not further engineering.
