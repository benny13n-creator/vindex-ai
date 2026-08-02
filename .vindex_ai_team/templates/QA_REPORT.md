# QA Report — [Feature Name]

**Author (role):** QA Engineering
**Date:**
**Implementation Plan:** [link]

## User Scenario Test (required — this is not the same thing as the happy-path row below)

State the actual end-user goal this ticket was opened for, as a numbered sequence of steps a real
user performs, and confirm every step actually completes — not just that each individual code path
has a passing unit/integration test. A feature can pass every row in "Test Coverage" below while
this still fails, if two individually-tested pieces don't actually work together end to end
(the concrete case this rule was added for: Mission 001, 2026-08-02 — `user_id` removal and a
duplicate-check bug were two separately-testable changes at the same call site; a test suite
verifying each in isolation would have missed that the duplicate-check's failure prevented the
insert from ever being reached, so "user_id is gone" would report green while the actual user
scenario — link a client to a case — still failed).

```
Scenario: [the actual user-facing goal, e.g. "Link a client to an existing case"]
1. [step] -> [expected observable result]
2. [step] -> [expected observable result]
...
N. [step] -> [expected observable result, including the DB/state ending up consistent]

PASS / FAIL — if FAIL, the ticket is not done regardless of unit test results below.
```

## Test Coverage

| Scenario | Type | Result |
|---|---|---|
| Happy path | | |
| Cross-tenant / ownership boundary (if applicable) | | |
| Malformed / adversarial input | | |
| Concurrent access (if applicable — check for the `FOR UPDATE SKIP LOCKED` pattern where relevant) | | |
| Provider/dependency failure (if AI or external-service-calling) | | |
| Boundary conditions (size caps, empty results, expired tokens) | | |
| Full existing suite | | pass count / total |

## Acceptance Criteria Verification
Cross-checked against `PRODUCT_SPECIFICATION.md`'s acceptance criteria, item by item — not just
"tests pass."

## Finding Lifecycle Position
This feature/fix is at **Stage 7 — Verified Fix** (tests pass in CI/local) once this report is
complete. It is explicitly NOT yet Stage 8 (Production Verified) — that requires live-environment
confirmation this role does not perform.

## Untested / Deferred
Anything explicitly not covered, and why — do not let a report imply completeness it doesn't have.

## Verdict
PASS / BLOCKED (name the specific failing scenario).
