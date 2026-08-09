# NIGHT SPRINT — CHECKPOINT

START_HEAD: `14a71439`
CURRENT_HEAD: `77cdcf9f`
WORKTREE: clean

## Mission status

| ID | Mission | Result | Commit |
|----|---------|--------|--------|
| V2-M01 | Authorization gate sweep | **NO-FINDING** | — |
| V3-M01 | Policy-lock verification | **POLICY-REQUIRED** (re-confirmed) | — |
| V3-M02 | Streaming/retry billing | **UNPROVEN** — see below | — |
| V4-M01 | Streaming billing integrity | **BLOCKED** — M01-A done, harness not built | — |
| V5-M01 | ask_agent execution semantics | **GREEN — SOURCE-PROVEN** | — |
| V6-M01..M04 | Streaming harness + matrix | **BLOCKED** — no budget for a valid harness | — |
| V6-M07 | Refund integrity | **GREEN — SOURCE-PROVEN** | — |
| V6-M05,06,08..15 | not started | — | — |
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

## V3-M01 evidence

`git diff 14a71439 HEAD -- routers/profitabilnost.py routers/voice.py routers/web3.py`
is EMPTY. All three files are byte-identical to the Sprint 6O baseline, so the
6O source+runtime proof stands unchanged. No new wrapper alters the conclusion.

## V3-M02 — UNPROVEN, not NO-FINDING

`/api/pitanje/stream` (api.py L3167+) already carries explicit, commented
hardening for exactly the scenarios M02 asks about:

- `UsageService.consume` runs ABOVE the generator (pre-deduction).
- `_refunded` makes the refund idempotent across three exit paths.
- SOA-012 (2026-08-08) fixed the case where client disconnect raises
  `asyncio.CancelledError` / `GeneratorExit` -- both BaseException, not
  Exception -- so no refund ran at all.
- `_delivered` guards the refund exploit (NIGHT-005).

That is source evidence of PRIOR closure. It is NOT proof that the 10-scenario
matrix (reconnect, partial stream, retry+failure, consume failure, refund
failure) holds today. Producing that matrix needs a controlled async-generator
harness that drives disconnect and reconnect against a mocked provider, which
was not built. Do not record this endpoint as clean until that harness exists.

## Next mission

V3-M02 — build the streaming billing harness, then V3-M03 ownership/IDOR
sweep with a detector that follows ownership THROUGH helpers.

## V4-M01-A — execution map (PROVEN by source, api.py)

```
L3167  consume                      OUTSIDE the generator, before StreamingResponse
L3169  async def _event_generator()
L3182  _refunded = False
L3185  _delivered = False
L3190  ask_agent                    provider — produces the WHOLE answer here
L3203  yield chunk ...              chunking happens AFTER the answer exists
L3207  _delivered = True
L3214  refund  -> _refunded = True  cache-hit / blocked path
L3224  except Exception   -> if not _refunded: refund (its own try/except)
L3241  except BaseException -> if not _refunded and not _delivered: refund
L3264  elif _delivered: no refund, logged only
```

Two consequences that change the remaining work — both derived from the map,
neither runtime-verified:

1. **This is not a token stream.** `ask_agent` at L3190 returns the complete
   answer and the generator chunks it afterwards. Scenarios S3/S5/S9 ("provider
   failure after partial output", "disconnect after partial output",
   "reconnect after partial stream") may be structurally unreachable: either the
   whole answer exists or none of it does. Verify this before spending a harness
   on them — it removes 3 of the 10 scenarios.

2. **Refund failure is silently swallowed** (L3230, L3247: `except Exception:
   logger.warning`). A failed refund leaves the credit spent with only a log
   line. That is the documented best-effort semantics of `UsageService.refund`,
   NOT a new finding — but it is the point where the streaming invariant can
   break without any signal, and it is what a harness should measure first.

**Open question, likely POLICY not defect:** each HTTP request runs its own
`consume` at L3167. Whether a client reconnect is a second billable operation
depends on frontend retry behaviour, which was not inspected.

## V4-M01 status: BLOCKED — INSUFFICIENT CONTEXT BUDGET

M01-A (source mapping) is complete and recorded above. M01-B (harness), M01-C
(10-scenario matrix) and M01-D (adversarial) were NOT performed. No runtime
evidence exists for this endpoint. Do not record it as verified.

## V5-M01 — RESOLVED. /api/pitanje/stream is not a stream.

PROVEN by AST over main.py: `ask_agent` is a plain `def` (not async, not a
generator), 0 yield/yield-from, 17 value returns. It returns a dict.

api.py L3190-3203:

```
rezultat  = await pokreni(ask_agent, ...)      # provider completes ENTIRELY
data_text = rezultat.get("data", "")           # the whole answer
for i in range(0, len(data_text), 80):         # slicing a FINISHED string
    yield f"data: {chunk}..."
```

The V4-M01-A hypothesis is CONFIRMED: **S3, S5 and S9 are structurally
unreachable.** There is no partial provider output and no server-side partial
state for a reconnect to resume. The mission matrix drops from 10 scenarios to 7,
and the survivors are simpler, because by the first yield the billable work is
already 100% done.

### CANDIDATE V5-C1 — over-refund on mid-slice disconnect (POLICY-ADJACENT)

Derived from the above, SOURCE-PROVEN / RUNTIME-UNPROVEN:

`_delivered = True` is set at L3207, i.e. AFTER the slicing loop finishes. A
client disconnect during the loop raises CancelledError/GeneratorExit, which the
BaseException handler at L3241 catches with `if not _refunded and not
_delivered:` -> it REFUNDS.

But the provider already ran to completion at L3190 and was fully paid for, and
the user has already received part of the answer. So this path refunds work that
was performed and partially delivered.

This is the INVERSE of credit loss -- it favours the user, not the vendor -- so
it is not a security or user-harm defect. Whether it is a defect at all depends
on the same billing policy that F-6O-001..003 are waiting on. NOT fixed, NOT
decided. Runtime proof requires the M02 harness.

## Next mission

V5-M02 — build the streaming harness (7 scenarios, not 10) and runtime-verify
V5-C1 first, since it is the only candidate the source map produced.

## V6-M07 — refund integrity (SOURCE-PROVEN / RUNTIME-UNPROVEN)

`UsageService.refund`, shared/usage.py L489-541:

- **Contains no try/except.** It does NOT swallow its own errors; an exception
  from `_refund_n_credits` propagates to the caller.
- **One atomic write:** `await asyncio.to_thread(_refund_n_credits, user_id, credits)`.
- **NOT idempotent by itself.** Calling it twice refunds twice. Every guard that
  makes refunding idempotent lives in the CALLER (`_refunded` in the stream
  generator, `_credit_consumed` in /api/pitanje).

Two consequences worth carrying forward:

1. The swallowing observed in the streaming endpoint (`except Exception:
   logger.warning`) is at the CALL SITE, not inside refund. A failed refund
   leaving the credit spent with only a log line is the caller's choice, not the
   primitive's.
2. Because the primitive is not idempotent, **each of the 4 refund call sites
   carries double-refund risk independently**, and a 5th caller added without a
   guard would mint credits. That is an architectural fact, not a current bug --
   all 4 existing sites are guarded. Worth knowing before anyone adds a fifth.

Prior real defect already closed here and visible in the source: CREDIT-REFUND-002
(2026-08-08) -- recomputing the refund from the registry minted 5 credits per
failure for the three routers that override the multiplier. Fixed; `credits=` is
now the preferred call form.

## V6-M01..M04 — BLOCKED

Building the streaming harness needs several iterations. Two harnesses tonight
were contaminated by environment (missing .env in a fresh worktree, missing
FOUNDER_EMAILS) and produced results that looked like findings but were not. An
improvised harness here yields false proof, not weak proof. Not attempted.
