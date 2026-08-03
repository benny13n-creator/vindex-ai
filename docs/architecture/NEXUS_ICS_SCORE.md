# Intelligence Connectivity Score (ICS)

**Mission:** Project Nexus, 2026-08-03. Formula (founder's own):
`ICS = Verified Intelligence Connections / Total Required Intelligence Connections × 100`.

**Methodology, stated explicitly so this number stays comparable over time**: a "required connection"
is an edge in the Intelligence Graph where a downstream module's answer would be measurably better if
it consumed an upstream module's already-computed output, AND no deliberate architectural decision
excludes it. Deliberately sealed modules (Web3/Digital Asset Compliance) and deliberate one-way sinks
(Usage Analytics) are excluded from the denominator entirely — they aren't gaps, they're correct
by design, confirmed via direct code read. Every connection below was verified, not assumed — see
`docs/architecture/NEXUS_INTELLIGENCE_GRAPH.md` and `NEXUS_MODULE_DEPENDENCY_MAP.md` for the evidence.

---

## Full connection ledger

| # | Connection | Status | Fixed this mission? |
|---|---|---|---|
| 1 | OCR → Classification | ✅ Verified | |
| 2 | Classification → Extraction | ✅ Verified | |
| 3 | Extraction → Chronology/Deadlines | ✅ Verified | |
| 4 | Extraction/Documents → Case Genome | ✅ Verified | |
| 5 | Evidence Vault → Case Genome | ✅ Verified | |
| 6 | Case Genome → AI Briefing | ✅ Verified | |
| 7 | Case Genome → CIO | ✅ Verified | |
| 8 | Case Genome → Copilot | ✅ Verified | Yes (Project Synapse, same engagement) |
| 9 | Case Genome → Firm Brain | ✅ Verified | Yes (Project Synapse) |
| 10 | Case Genome → Outcome Intelligence | ❌ Gap | No — documented, not attempted |
| 11 | Case Genome → Judge/Opponent Predictor | ❌ Gap | No — documented, not attempted |
| 12 | Risk Engine → Matter Intelligence | ✅ Verified | |
| 13 | Risk Engine → Case Command Center | ✅ Verified | **Yes, this mission** (was an independent, silently-diverging reimplementation) |
| 14 | Risk Engine (`identify_case_problems`) → Task Engine | ✅ Verified | **Yes, this mission** (was bypassed by a 5th independent GPT detector) |
| 15 | Risk Engine (health_score) → Event Bus alert | ✅ Verified | **Yes, this mission** (handler existed, never emitted) |
| 16 | Risk Engine (critical hearing) → Event Bus alert | ✅ Verified | **Yes, this mission** (same) |
| 17 | `PREDMET_KREIRAN` → Case Pipeline | ✅ Verified, but fragile (no durability) | No — documented as a reliability risk, not re-architected blind |
| 18 | `GENOME_UPDATED` → Audit Log | ✅ Verified | |
| 19 | `DOCUMENT_JOB_ENQUEUED` → any handler | ❌ Gap | No — needs new handler logic, outside orchestration-only scope |
| 20 | `DOCUMENT_JOB_COMPLETED` → any handler | ❌ Gap | No — same |
| 21 | `DOCUMENT_JOB_FAILED` → any handler | ❌ Gap | No — same, highest-value of the three |
| 22 | Smart Intake extraction (judge/opponent) → `predmeti.tuzilac`/`tuzeni` | ❌ Gap | No — reconfirmed from a prior mission, still not attempted |
| 23 | `predmeti.tuzilac`/`tuzeni` → Judge/Opponent auto-run | ❌ Gap | No — depends on #22 |
| 24 | Deadline detection → Calendar | ✅ Verified | |
| 25 | Deadline detection → Notifications | ✅ Verified | |
| 26 | Chronology → Timeline aggregator | ✅ Verified | |
| 27 | Timeline → case-scoped Audit view | ✅ Verified | |
| 28 | Semantic Search → RAG/AI consumers (15+) | ✅ Verified | |
| 29 | Quality Gate's citation-existence check → Case Genome/Briefing | ❌ Gap | No — a real, uneven distribution of hallucination protection |
| 30 | Legal Reasoning Engine's SOURCE-n constraint → Case Genome/Briefing | ❌ Gap | No — same category as #29 |
| 31 | `knowledge_profiles` → AI Briefing (real data, not phantom) | ❌ Gap | No — founder decision needed (build real extraction, or retire as a Briefing input) |
| 32 | Memory Graph → anything | ❌ Gap | No — unchanged, founder decision needed |

## Score

**Verified: 20 / Total required: 32 → ICS = 62.5%**

**Target before Beta: >90%.** Current state is well below target — reported plainly, not softened.
Of the 12 gaps, **4 were closed this mission** (rows 13-16 would have been gaps this morning); the
remaining 8 are correctly documented rather than guessed at:
- 2 (`10`, `11`) need the same low-risk "read Genome as context" pattern already proven twice this
  engagement (Copilot, Firm Brain) — the cheapest remaining wins.
- 3 (`19`-`21`) need new handler logic, one step past pure orchestration.
- 2 (`22`, `23`) need a small, well-scoped backend write (reconfirmed from a prior mission, `WOW-003`).
- 2 (`29`, `30`) need a design decision on how much hallucination-guardrail machinery Case Genome/
  Briefing should route through, given both already have a lighter, prompt-only safeguard.
- 2 (`31`, `32`) are explicit founder decisions (population strategy for two structurally-inert data
  sources).

## Recomputation note
This score should be recalculated the same way (same connection list, same exclusion criteria) at the
start of any future mission that touches these modules — appending new rows for new modules rather
than redefining what counts as "required," so the trend stays meaningful, matching this engagement's
own established `METRICS.md` discipline for cross-run comparability.
