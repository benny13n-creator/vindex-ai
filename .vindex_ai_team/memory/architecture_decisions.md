# Architecture Decisions — Institutional Record

Chronological. Each entry is a compressed pointer to the full decision record, not a restatement —
follow the link for the actual reasoning, alternatives, and evidence.

## 2026-07-22 — Core Consolidation
**Decision:** "1 concept = 1 owner = 1 algorithm = 1 truth." Ended a 3-way overlap in
risk/next-action/drafting logic that a code-only 15-part forensic audit had found the same day.
**Full record:** `docs/architecture/VINDEX_CORE_CONSOLIDATION.md`
**Verification:** brutal-audit-verified same day; 9.5/10 founder review.
**Standing implication for all future work:** before designing anything, check whether Case Genome,
the Legal Reasoning Engine, or another existing owner already computes this.

## 2026-08-01 — Trust Architecture Blueprint adopted
**Decision:** the Blueprint becomes the governing security constitution, sitting above the existing
implementation-evidence documents (Gap Register, Maturity Dashboard, STRIDE model), not replacing
them. **Full record:** `docs/architecture/VINDEX_TRUST_ARCHITECTURE_BLUEPRINT.md`,
`docs/architecture/VINDEX_TRUST_ARCHITECTURE_TRACEABILITY.md`.
**Key finding:** Capability 4 (AI Governance Layer) was a genuine architectural absence — confirmed
by grep, the phrase didn't exist anywhere in this project's docs before the Blueprint itself.
**5 Programs defined**, dependency order revised same day after founder challenge: originally
P3→P2→P1→P4, revised to **spec Program 1 first** (since Classification is a stage *inside* the
Governance pipeline, not an independent upstream program), then P3 parallel, then P2→P1→P4, P5
always parallel.

## 2026-08-01/02 — Program 1 (AI Governance Layer), 8 revisions
**Decision, evolving:** the full record is `docs/architecture/PROGRAM_1_AI_GOVERNANCE_ARCHITECTURE_SPEC.md`'s
own revision history — do not summarize it here, it is the single best worked example in this
project of adversarial architecture review actually working. Compressed lessons that generalize
beyond Program 1 specifically:
- **A firewall pair (input guard + output check) is not governance without a single decision-maker
  that both feed into.** (Revision 1→2's core fix.)
- **Folding a new signal into an existing versioned rule engine beats inventing a parallel,
  differently-versioned mechanism** — proven twice: risk-factor overrides folded into Policy rather
  than a third formula term (Revision 6), and the eventual fix for the "dead parameter" bug folded
  response-side escalation into Policy the same way (Revision 8).
- **When red-teaming a fix, verify the fix against the exact original problem statement, not a
  fresh re-derivation of what might be wrong** — this is what makes a *targeted* re-check different
  from, and cheaper than, a full re-audit, and is why Program 1 didn't spiral into infinite revisions.
- **A "simpler alternative" claim must be checked against what already exists in the codebase**
  before being adopted — the sync/async chokepoint fix (Revision 8) was only correct because
  `shared/audit_immutable.py::log_action_sync` was found to already exist, unused, rather than a new
  event-loop bridge being invented.

## Template for new entries
```
## [Date] — [Decision Title]
**Decision:** [one sentence]
**Full record:** [link to decisions/ARCHITECTURE_DECISION.md instance]
**Key finding / lesson that generalizes:** [if any]
```
