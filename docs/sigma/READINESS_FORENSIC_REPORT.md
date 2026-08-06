# Readiness Forensic Report — Program Sigma, Master Sprint 004 (2026-08-06)

Phase 7 deliverable: assume the system cannot find the right next action. Try to prove: duplicate actions,
evidence-less actions, stale/irrelevant actions, wrong priority, contradictory actions, AI-invented
recommendations.

### Attempt 1: duplicate actions?

`case_actions` itself: no — DB-enforced partial UNIQUE index (migration 099) on `(predmet_id, dedupe_key)
WHERE status='open'`, proven repeatedly across this program (Sprints 002-004). **Across surfaces**: yes,
confirmed and largely fixed this sprint — `case_intelligence.py`'s AI Briefing and `copilot.py`'s own
`_handle_analiza_predmeta` both independently invented a "next action" that could disagree with
`case_actions`' own answer; both now read `case_actions` directly. `case_commander.py`'s own 8 surfaces
remain a confirmed, large, unfixed source of possible action duplication/disagreement (see
`ACTION_OWNERSHIP_REGISTRY.md`).

### Attempt 2: actions without evidence?

Confirmed impossible for `case_actions` itself, by construction — see `ACTION_EVIDENCE_CHAIN.md`'s own
proof (exactly 1 insert call site, all 3 rules populate real `dokaz`). Confirmed PRESENT for
`case_commander.py`'s own 8 surfaces — zero `dokaz`-equivalent field, zero stable identity, direct raw-data-
to-GPT with no structured evidence chain (`SIGMA-018`).

### Attempt 3: actions that are no longer relevant (stale)?

`_consequence_refresh_case_actions`'s own reconcile loop (`services/case_evolution.py`) closes any open
action whose `dedupe_key` is no longer in the freshly-recomputed target set, on every Case Evolution
refresh — a stale action cannot persist past the next document/event that triggers a refresh. This is
pre-existing, unchanged, re-confirmed this sprint by re-reading the reconcile logic directly (not assumed
from memory).

### Attempt 4: wrong priority?

`case_actions.prioritet` is fully deterministic (`_priority_by_days`, `_TEZINA_PRIORITET`, `ozbiljnost`-
based mapping — all pure functions over already-computed data, re-confirmed this sprint). The 2 fixes this
sprint close the 2 places where a DIFFERENT, GPT-generated priority-adjacent value (`hitnost`/
`sledeci_korak.prioritet`) could show a lawyer a next-action that DISAGREED with `case_actions`' own
priority ordering for the same case — the actual "wrong priority" risk this sprint found and closed.

### Attempt 5: contradictory actions (2 actions telling a lawyer to do opposite things)?

Not found for `case_actions` itself — each of its 5 rules addresses a genuinely distinct concern (deadline/
missing-evidence/predstojeci-rokovi/weak-evidence/contradiction), and the dedupe_key scheme prevents 2 rows
for the SAME fact. Genuinely possible ACROSS surfaces (a `case_commander.py` recommendation could tell a
lawyer something Workspace's own `case_actions`-sourced view doesn't support) — not proven with a concrete
example this sprint (would require live-browser reproduction, out of this sprint's own scope), named as a
real risk inherent to `SIGMA-018`/Case Commander's own unfixed state rather than independently verified.

### Attempt 6: AI-invented recommendations presented as fact?

**This is exactly what this sprint's own 2 fixes closed** — `case_intelligence.py`'s AI Briefing and
`copilot.py::_handle_analiza_predmeta` both presented a GPT-invented "the one most urgent action" as if it
were an authoritative answer, with no grounding in `case_actions`. Both now defer to `case_actions` when a
canonical answer exists, falling back to the GPT's own guess (clearly a lesser-authority path, not
mislabeled) only when no canonical action exists yet for that case. `case_commander.py`'s own 8 surfaces
remain a confirmed, large, unfixed instance of this exact failure mode.

## Certification verdict

Per the mission's own rule ("Nijedna preporuka ne sme postojati bez porekla... svaki problem koji može
bezbedno da se popravi... mora biti odmah popravljen"): this sprint fixed the 2 genuinely safely-fixable
instances found (small, well-scoped, mirroring an already-proven pattern from Sprint 003, tested, zero
regressions). It did NOT rush a fix into `routers/case_commander.py`'s own 8-surface violation — the single
largest finding of this sprint — because doing so safely would require individually verifying 8 separate
GPT prompts against live data, a scope this sprint's own remaining time did not support without risking
exactly the kind of rushed, unreliable change this whole engagement's own established discipline avoids.
Named precisely, not hidden, as `SIGMA-018` (and its own dedicated future-sprint recommendation) in the
Debt Register.
