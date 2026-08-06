# Sprint 003A Mission Report — "Regression Recovery & Green Baseline Certification"

Chronological execution log.

## 0. Entry state

Certification 003 ("Forensic Authorization & Isolation Certification") had just closed with the full suite at
**2,984 passed, 1 skipped, 7 failed** — the 7 failures were found, root-caused, and partially mitigated
(`teardown_module` added to 2 files) as a byproduct of that sprint's own regression verification, tracked as
`LAMBDA003-TEST-001`, and explicitly flagged as NOT fully fixed. This sprint exists to close that gap and
nothing else.

## 1. Phase 1-3 — Two independent, parallel, read-only investigations launched

Per this mission's own explicit rule ("no implementation before at least two independent agents agree on the
root cause"), 2 forks were launched in parallel, each instructed to re-derive the root cause from scratch —
not simply accept the coordinator's own prior (demonstrably-incomplete) conclusion — and specifically explain
why the previously-applied `teardown_module` fix failed to resolve the failures.

- **Fork A** (Pytest Failure Analyst + Root Cause Auditor): ran the full failure inventory fresh, traced the
  mechanism via a minimal deterministic reproduction (file-order-independent controlled experiment: listing
  `test_doc_pitanje_api.py` LAST on the command line still reproduces the failure, proving collection order,
  not file-list order, is what matters), confirmed the timeline via `git log`/`git blame`, and recommended
  moving the mutation into a `setup_module` hook.
- **Fork B** (Architecture Verifier + Independent Code Reviewer): approached independently via pytest's own
  internal source code (confirming the collection-then-execution lifecycle model directly from
  `_pytest/main.py`), ruled out alternative hypotheses (a real `main.py` regression, a pytest-plugin
  interaction, an unrelated Certification 003 change) with git evidence, and independently reproduced the
  same causal proof via a negative-control experiment (omitting the 2 files eliminates the failure).

**Both forks converged on the same root cause** (collection-time `sys.modules["main"]` mutation with no
execution-scoped guard, in exactly the same 2 files) — satisfying this mission's own agreement requirement.
They differed only on the specific recommended fix mechanism (Fork A: `setup_module`; Fork B: patch `api.py`'s
own bound reference via `monkeypatch`) — a legitimate implementation-choice difference, not a root-cause
disagreement.

## 2. Coordinator's own additional verification before implementing

Before choosing between the two suggested fix directions, the coordinator read `tests/test_doc_pitanje_api.py`
and `routers/dokument.py::dokument_pitanje` directly, identifying the specific reason the `setup_module`
approach would be safe: the actual endpoint handler does its own function-body-local `from main import
ask_agent`, re-resolved fresh at call time — meaning the fix's own correctness didn't depend on `api.py`'s own
top-level import binding order at all. This closed the one open safety question neither fork had fully
resolved (whether `api.py`'s own top-level `from main import ...` binding would matter), before any code was
changed.

## 3. Phase 5 — Minimal repair implemented

Chose the lower-risk of the two suggested fixes (`setup_module`, an exact structural pairing with the
already-present `teardown_module`) over the alternative (a broader `monkeypatch`-based restructuring), per
Phase 5's own "minimal repair only" rule. Applied identically to both `tests/test_doc_pitanje_api.py` and
`tests/test_uploaded_doc_api.py` — moved the 5 `sys.modules.setdefault(...)` calls and their preceding capture
dict into a `setup_module(module)` function each. No other line in either file changed. No production code
touched.

## 4. Phase 6 — Regression certification, layered

1. Targeted: both modified files run standalone (6/6, 8/8 — both pass).
2. Affected module: both modified files plus the previously-failing file and its alphabetical neighbors, run
   together (67/67 pass).
3. Edge case: `-k`-filtered single-test selection on one modified file (passes, confirming the hook fires
   correctly even under test filtering).
4. Full repository suite: **2,991 passed, 1 skipped, 0 failed** — up from 2,984/1/7, exact +7/-0 delta.

## 5. Phase 7 — Forensic self-review, adversarial

A third, dedicated fork (Independent Code Reviewer) was tasked with trying to disprove the fix, not confirm
it — re-verifying the handler's local-import claim from raw bytes independently, re-running both modified
files in isolation, testing `-k` filtering itself (not trusting the coordinator's own run), grepping for
skip/xfail shortcuts, and re-grepping for any other latent instance of the same bug class. **Verdict: the fix
holds, no flaw found, no follow-up required.**

## 6. Deliverables and trackers

7 deliverables written (`REGRESSION_FAILURE_INVENTORY.md`, `ROOT_CAUSE_ANALYSIS.md`, `FIX_JUSTIFICATION.md`,
`REGRESSION_CERTIFICATION_REPORT.md`, `TEST_COVERAGE_IMPACT.md`, this file, plus the architectural debt
register update below). `LAMBDA003-TEST-001` closed in `ARCHITECTURAL_DEBT_REGISTER.md` (marked FIXED, not
left open) — no new debt was manufactured; this sprint discovered no new architectural gap, only closed a
previously-named test-infrastructure one.

## Success criteria, checked against the mission's own bar

✔ Zero failing tests (2,991 passed, 1 skipped, 0 failed)
✔ Zero unexpected regressions (exact +7/-0 delta, verified via Phase 7 forensic review)
✔ Root cause identified for every failure, with git-verified evidence, by 2 independent investigations
✔ Every repair independently reviewed (Phase 7 fork found no flaw)
✔ Full suite green
✔ Honest documentation, including one disclosed open question (`ROOT_CAUSE_ANALYSIS.md`'s closing note) and
one disclosed coverage limitation (`TEST_COVERAGE_IMPACT.md`'s closing note) — neither hidden, neither guessed
past what the evidence actually supports.

Repository is in a clean, fully green, verified state, ready for Certification 004.
