# AI Reasoning Boundary Audit — Program Lambda, Master Sprint 001

Adversarial sweep: does GPT change priority, readiness, risk, next-action, contradictions, deadlines, or
facts anywhere beyond what Program Tau (005-008) already closed? Read-only investigation, findings triaged
after.

## Findings

| # | Finding | Status | Severity |
|---|---|---|---|
| 1 | `routers/digital_twin.py` — both endpoints (`/simulacija`, `/sta-ako`) are live (confirmed via `static/vindex.js` `fetch()` calls, not a docstring claim) and let GPT invent `verovatnoca`/`nova_verovatnoca_uspeha` (0-100 success probabilities) with zero grounding or cap anywhere. Explicitly predicted as a "3rd confirmed candidate" for the deterministic-cap mechanism in `docs/tau/TAU_007_HANDOVER.md`, never implemented until now. | **FIXED this sprint** — lightweight canonical-context fetch + the exact same `_CAP_BY_READINESS` mechanism already proven for Court Predictor/Hearing CC, applied per-scenario for `/simulacija` and to the single probability for `/sta-ako`. Adversarially tested. | High → Closed |
| 2 | `routers/evidence_graph.py` — GPT decides `OSPORAVA` (contradicts) edges between evidence nodes. `validate_graph_edge_references` correctly checks referenced nodes exist, but nothing checks whether an asserted contradiction is actually TRUE — no existing deterministic ground truth to check against. | Named as `LAMBDA-002`, not fixed (no safe existing-architecture fix available) | Medium |
| 3 | `routers/matter_intel.py`'s Pre-Flight Check / Uncertainty Dashboard | Matches `GAMMA-003`'s own existing description exactly — not a new finding | — |
| 4 | `routers/outcome_intel.py`, `precedenti.py`, `zastarelost.py`, `zakon_monitoring.py`, `decision_replay.py`, `multi_agent.py`, `copilot.py` (all handlers), `drafting.py`, `services/agent_tasks/precedents_radar.py`, `profitabilnost.py`, `strategy_simulator.py` | Checked, clean — no ungrounded numeric/categorical GPT decision found | — |

## Verdict

One real, live, previously-named-but-never-fixed GPT Boundary violation was found and closed this sprint
(#1) — `digital_twin.py` had sat exactly where Tau 007's own handover said it would need attention, for an
entire program cycle, until this adversarial pass actually implemented the fix rather than re-naming it.
One softer, genuinely harder-to-close gap (#2) is named, not rushed. No new violation was found in the
remaining ~12 GPT-calling files checked.
