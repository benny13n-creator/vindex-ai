# NIGHT SPRINT — CHECKPOINT

START_HEAD: `14a71439`
CURRENT_HEAD: `14a71439`
WORKTREE: clean

## Mission status

| ID | Mission | Result | Commit |
|----|---------|--------|--------|
| V2-M01 | Authorization gate sweep | **NO-FINDING** | — |
| V2-M02..M15 | not started | — | — |
| V1-M01 | Class C billing remediation | **POLICY_REQUIRED** | — |
| V1-M02 | HTTPException swallowing sweep #2 | **NO-FINDING** (18 FP) | — |
| V1-M06 | Double-charge forensics | **NO-FINDING** (10 FP) | — |

## V2-M01 evidence

21 candidates from a route/subject/ownership/provider ordering inventory.

**3 x OWNER-AFTER-PROVIDER — all FALSE_POSITIVE, each disproven by reading source:**

- `multi_agent.run_agent` `/run` — the provider at L406 is `_pozovi_router_api`, an
  agent auto-selector operating on `req.task` (the caller's own free text). No
  subject-bound data is read before it. Same for `/run-parallel`.
- `client_twin` `/{klijent_id}/analiziraj` — the fetch at L156 is
  `_get_klijent_materijali(supa, klijent_id, user["user_id"])`, owner-scoped and
  ahead of the provider. The `.eq("klijent_id").eq("user_id")` the detector
  matched at L204 is the profile upsert lookup, not the read authorization.

**18 x NO-OWNER-CHECK — NOT usable as evidence.** The detector flagged
`/api/dokument/pitanje`, which Sprint 6B proved (and tests assert) is
owner-gated. It does not recognise ownership performed inside a helper, so its
negative column over-reports. Re-running it as-is would produce the same 18
names without any of them being findings.

## Instrument limits discovered tonight

- Transitive name matching over bare function names produces false positives:
  `_check`, `nacrt` (a parameter), `analiza` (a local dict). Confirmed in 6J and
  again in V1-M02.
- Provider dispatch in this codebase is mostly `asyncio.to_thread(_pozovi_x, ...)`
  and `_pokreni(fn, ...)` — the callee is an ARGUMENT. Any analyzer that reads
  only the call target under-reports by roughly 40 endpoints (found in 6N).
- Ownership performed inside a helper is invisible to line-level detectors.

## POLICY_REQUIRED — locked, do not touch

`F-6O-001` GET /api/profitabilnost/analiza
`F-6O-002` POST /command
`F-6O-003` POST /web3/analiziraj-ugovor

All three: consume before provider, no compensation path, credit stays spent on
provider failure. Proven in Sprint 6O by source + runtime (4/4 controlled tests).
No canonical billing wrapper exists in the codebase (0 hits) and refund is used
by 4 of 116 consuming functions, so the code does not establish a policy that
could be applied without the owner's decision.

## Closed, do not reopen

F-6H-001, F-6J-001..005 — closed in sprints 6I, 6K, 6L, 6M. The upgraded V1-M02
analyzer no longer sees any of them, which is the regression check for all five.

## Next mission

V2-M02 — subject propagation / IDOR sweep.
