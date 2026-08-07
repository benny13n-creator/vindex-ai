# SINGLE_BRAIN_ARCHITECTURE.md — Operation Single Brain, Mission 001

## Mandate

*"Tvoj posao NIJE da dodaš nove mogućnosti. Tvoj posao je da dokažeš da cela platforma ima samo jedan
mozak. Ako pronađeš makar jednu situaciju gde dva modula različito tumače isti predmet, misija NIJE
uspešna."*

This mission follows directly from Operation One Truth (2026-08-07, same day), which fixed the platform's
first confirmed cross-module risk-consistency defect and explicitly named readiness, success-probability,
and confidence fragmentation as unresolved debt. Operation Single Brain's founder mandate is stricter: assume
NO prior decision — including One Truth's own — is correct or complete. 10 independent forensic teams
re-verified everything from current code rather than trusting any prior report, and were explicitly told not
to stop at what prior missions already named.

## Methodology

10 parallel teams, each read-only except Team 6 (API Consistency), which was authorized to execute Python
reproductions against real application code with mocked I/O (the same discipline established by Operation
Black Swan). No live browser tool is available in this environment; frontend claims are verified by reading
`static/vindex.js`/`index.html` directly, not by clicking through a running instance.

**Absolute rules observed**: no new AI capabilities were added, no new GPT prompts were introduced, no new
databases or algorithms were created, and no UX changes were made except where necessary to remove a
duplicate/contradictory truth source. Every fix in Phase 3 either eliminates a duplicate computation in
favor of an existing canonical source, or hardens an existing canonical source against an unvalidated
AI-authored input — never adds a new decision-making capability.

**Governance note**: several of the 10 teams used their own background sub-forks for investigative depth.
Two forks briefly violated their read-only brief (one wrote an unsolicited file to the repo, one published
an unsolicited — but private, low-risk — Artifact). Both were caught and corrected by their own coordinating
team before reporting back; `git status` was independently re-verified clean before this document was
written. Disclosed here rather than omitted.

## What "one brain" means for Vindex AI

Per `docs/architecture/VINDEX_LEGAL_INTELLIGENCE_MODEL.md` (Operation One Truth, Phase 2): a legal case is
Facts + Evidence + Risks + Gaps + Obligations + Actions + Strategy. Every other screen, panel, and AI
feature is a VIEW onto that model — it may select, combine, filter, or narrate; it may never independently
compute a new answer to a question one of those seven entities already answers.

This mission found that principle is **substantially, but not completely, true today**. The deterministic
backbone — `services/risk_engine.py` → `shared/gap_engine.py` → `shared/case_readiness.py` →
`services/case_evolution.py`'s `case_actions` → `shared/attention_priority.py` — is a genuine, cycle-free DAG
(confirmed independently by Team 2's Decision Graph audit: zero cycles found, four hops to eleven hops deep
depending on the chain). Several violations named by Operation One Truth's own same-day report were already
fixed by the time this mission's teams re-checked them hours later (the codebase moves fast in this
engagement). But new, previously-uncatalogued fragmentation was found in categories the prior mission did
not deeply audit: readiness now confirmed as a **3-way** collision (not 2-way), confidence fragmentation is
**15 independent sources** (not 7), and two entirely new categories — **Importance** (a 3-way vocabulary
mismatch on a single column) and a same-entity **Status** classifier collision — were found that Operation
One Truth's own registry never named at all.

## Deliverables

1. `docs/singlebrain/SINGLE_BRAIN_ARCHITECTURE.md` — this document
2. `docs/singlebrain/TRUTH_REGISTRY.md` — every value in the platform representing risk/priority/
   readiness/confidence/strength/health/probability/urgency/importance/verification/credibility/quality/
   severity/completeness/status, with file:line evidence for every occurrence
3. `docs/singlebrain/CANONICAL_VALUE_MAP.md` — the resolution: for each fragmented concept, which source is
   now (post-Phase-3) the sole canonical owner, and what changed to make that true
4. `docs/singlebrain/DECISION_DEPENDENCY_GRAPH.md` — who computes/displays/uses/changes each major decision,
   and what depends on it; confirms zero cycles exist
5. `docs/singlebrain/CROSS_MODULE_CONSISTENCY_REPORT.md` — every surface (Workspace/Dashboard/Command
   Center/Court Predictor/Digital Twin/Health Index/CIO/Copilot/Morning Briefing/Case Intelligence/Case
   DNA/Risk Engine/Notifications/Case Actions/PDF/API) compared for the same case, plus Team 6's
   execution-verified endpoint-pair test results
6. `docs/singlebrain/AI_BOUNDARY_CERTIFICATION.md` — for each of risk/readiness/priority/health/success
   probability/confidence, can GPT author or override it; what was found, what was fixed
7. `docs/singlebrain/DUPLICATE_TRUTH_ELIMINATION_REPORT.md` — every duplicate found, and its resolution
   (eliminated this mission / named as debt with reasoning)
8. `docs/singlebrain/FINAL_SINGLE_BRAIN_CERTIFICATE.md` — the mission's own required stop-condition
   verdict: full suite green, zero regressions, zero duplicate truth, zero fragmentation (or an honest
   accounting of what remains and why it's bounded, not hidden)

## Stop condition (as the mission itself specified)

*"Ne prelaziti na sledeću fazu... Tek kada: FULL SUITE = GREEN, ZERO REGRESSIONS, ZERO DUPLICATE TRUTH, ZERO
FRAGMENTATION, možeš proglasiti: MISSION COMPLETE."*

Red Team's own verdict (Team 9): the mission's "even once" bar for a live, reproducible contradiction was
triggered by a fully concrete, currently-shippable finding (manually-set case risk silently outliving the
canonical engine's live recomputation, rendered contradictorily on the same screen). This is Phase 3's
highest-priority fix. See `FINAL_SINGLE_BRAIN_CERTIFICATE.md` for the honest final accounting of what was
fixed, what remains, and whether the mission's own bar is met.
