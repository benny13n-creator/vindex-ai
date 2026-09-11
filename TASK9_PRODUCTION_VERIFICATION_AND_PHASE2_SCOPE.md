# TASK 9 — PRODUCTION VERIFICATION RECORD & PHASE 2 SCOPE

Addendum to `TASK8_FINAL_EVIDENCE_DOSSIER.md`. Written after `fd47c809` was
pushed to `origin/main` and deployed, closing the loop the dossier's own
"Recommendation" section asked for: re-run the Task 2/Task 5 live A/B tests
against production once, before relying on the fix in front of a real user.
This document is that re-run's record, plus the founder's resulting scope
decision for what comes next. Nothing in this file changes code.

## 1. Pre-push precondition: 150 vs 136 test count

Founder required this explained, with the explicit caveat "ne tvrdim da je
problem, ali... za ovako fundamentalni subsystem taj detalj ne sme ostati
neobjašnjen" (I don't claim it's a problem, but it must not stay unexplained
for a subsystem this fundamental).

Root cause, via `pytest --collect-only`, not assertion:

| Set | Files | Count |
|---|---|---|
| Common to both runs | `test_ccc.py`, `test_p14_t2_ccc_degradacija.py`, `test_n4_coi001_intake_fail_closed.py`, `test_faza642_authorization_boundary.py` | 130 |
| Only in the earlier 150-run | `test_beta_gate_klijent_delete_audit.py`, `test_lambda003_klijenti_role_fail_closed.py`, `test_ns001_faza1_klijent_predmet.py`, `test_beta_gate_upload_refund.py` | 20 |
| Only in the later 136-run | `test_doc_pitanje_api.py` (added specifically to cover the Task 5 `/api/pitanje` fix) | 6 |

130+20 = 150. 130+6 = 136. No test disappeared; the two runs targeted two
different, deliberately-scoped file sets. A union re-run of all 9 files
(executed, not just collected) gave the single clean current total:
**156 passed, 0 failed, 6.59s.** This is now the recorded number — treat any
future count that isn't traceable to a stated file-set change the same way
this one was: as a required-explanation event, not noise.

## 2. Production gate — all 4 founder-specified checks, executed live

Method: fresh, isolated, service-role-created test accounts against
`https://vindex-ai.onrender.com` directly (never the founder's account),
cleaned up as informational leftovers per the sprint's standing convention.

1. **Manual dokaz → event → case_action (Task 2 fix).** Isolated test
   matter, one manual fact write → `NewEvidenceRegistered` event row
   inserted immediately, `case_actions` created ~2.4s later
   (`23:48:52.770` → `23:48:55.007/.134`). PROVEN live.
2. **AI answers from a newly-added fact (Task 5 fix).** Planted a
   distinctive contractual-penalty figure (91.847,36 RSD), asked a question
   answerable only from it. AI answered with the exact figure, correctly
   cited "član 7 ugovora." PROVEN live. (First automated check flagged this
   as failed only because the harness compared against an unformatted
   number string; the AI's Serbian-formatted answer was correct all along —
   a harness bug, not a product bug, corrected before reporting.)
3. **Injection quarantine on the new channel.** Planted an instruction-
   override attack inside a manually-entered fact. AI did not obey it —
   answered "nije direktno definisano u dostavljenim izvorima." PROVEN
   live, existing `_ctx_bezbedan()` quarantine holds for this new channel.
4. **Standard upload flow, unregressed.** Real PDF upload (via `reportlab`,
   OCR-readable) → 200, `procena` generated, full event chain fired
   end-to-end: `predmet_kreiran → NewEvidenceRegistered → DocumentAccepted →
   GenomeUpdated → case_actions` (2 rows). PROVEN live. First poll (15s)
   showed 0 events — a false negative from insufficient wait, not a defect;
   a second poll ~30-45s post-upload showed the full chain. **Methodology
   finding, recorded for Phase 2**: a fixed `sleep(N)` then single check is
   already falsified by production's own worker latency variance (2.4s for
   the manual-write path, 30-45s for the upload+GPT-analysis path observed
   live). Future async-evolution tests must poll with a bounded timeout
   against the expected terminal state and log actual observed latency, not
   assume one fixed sleep window covers every trigger shape.

## 3. Real anomaly found during verification, resolved with evidence (not asserted away)

A `case_actions` row's `correlation_id` matched a *later* triggering event,
not the one whose timing lined up with its `created_at` — looked like
broken lineage. Root-caused, not dismissed: `_consequence_refresh_case_actions`
(`services/case_evolution.py:1166-1172`) does an UPDATE-on-conflict for an
already-open `dedupe_key` — it refreshes `correlation_id` + `updated_at` to
the MOST RECENT triggering event on every reconciliation pass, while
`created_at` stays fixed at first appearance. Confirmed: the case_action's
`updated_at` (`23:49:31.815`) sits ~3s after the second event
(`23:49:28.539`) — the same causal latency shape as the original create.

**This is a semantics gap, not (yet) a proven bug**, and is the single
highest-priority Phase 2 item per the founder's explicit framing: the schema
currently conflates two possibly-distinct relations —

- `originating_cause` — which event first created this action, and
- `latest_refresh_cause` — which event most recently confirmed/refreshed it

— under one `correlation_id` column that currently only tracks the latter.
Whether that's *correct* depends on what legal-auditability consumers will
actually need to answer ("what caused this action to exist" vs "what most
recently confirmed it's still warranted") — a question to be answered by
reading existing/planned consumers of `case_actions.correlation_id` before
changing anything, not by assuming either interpretation is wrong.

## 4. Evidence classification (founder's, recorded verbatim as the standing baseline for Phase 2)

- PROVEN: manual dokaz now enters the durable event/evolution path.
- PROVEN: new `predmet_dokazi` content reaches AI context well enough for the model to use a newly-added fact.
- PROVEN: existing untrusted-context quarantine holds on this new channel.
- PROVEN: upload lifecycle unregressed, produces the expected event chain.
- PROVEN: live worker latency is large enough that a short polling window can produce a false negative.
- PROVEN: reconciliation can change an existing action's `correlation_id`.
- UNKNOWN: whether that is the right provenance semantics for all `case_actions` types.
- UNKNOWN: whether `case_pipeline.py` has a parallel/conflicting mechanism.
- UNKNOWN / incomplete: the remaining 8 of 12 Task 7 adversarial scenarios.
- PROVEN GAP: fact-level provenance (`izvor_dokumenti`) incomplete for 4/5 `case_actions` types.
- OPEN BY DESIGN: deadline automation (Task 6's legitimate STOP stands).

## 5. Status

**`fd47c809`: production-confirmed and closed for its own scope** (the two
Task 2 / Task 5 fixes). **Case Evolution as a subsystem: not CLOSED.**
Founder's own wording, to be used verbatim in any future status report:

> CASE EVOLUTION — CRITICAL GAPS FIXED, ADVERSARIAL CLOSURE PENDING

Do not reopen or re-test the two shipped fixes without new evidence they've
regressed — re-litigating closed, production-verified findings wastes cycles
this project's own history has repeatedly flagged as the wrong failure mode.

## 6. Phase 2 scope, in the founder's explicit priority order

Not started. Do not start without a fresh explicit go-ahead. In order:

1. **Provenance semantics for all 5 `case_actions` types.** For each type,
   must be answerable: which source first created it, which events later
   refreshed it, which evolution run produced its current state, and
   whether that state still rests on a currently-valid version of its
   source. Resolves §3 above as a designed answer, not a guess.
2. **`services/case_pipeline.py` / `routers/case_pipeline.py` forensics.**
   Prove, before any further change, whether a second mechanism creates or
   mutates the same derived artifacts as `case_evolution.py`. If one
   exists, the founder must set an ownership boundary before more code is
   written — two independent "case evolution" systems would be a standing
   risk, not a feature.
3. **Failure / idempotency / concurrency matrix** (the remaining 8 of 12
   Task 7 scenarios): duplicate event delivery, retry, concurrent workers,
   stale source, failed model run, cross-matter/cross-tenant leakage, and
   explicitly a **no-consequence test** — proving the system can legitimately
   say "event processed successfully → no material case change → no
   justified action" without fabricating a `case_actions` row just because
   a dokaz was added. A system that manufactures an action from every
   input would be a defect on the opposite side of the one this sprint
   fixed.

Deadline automation (Task 6) remains explicitly out of Phase 2's engineering
scope — SMTP absence is an infrastructure fact, but the real blocker is a
Product + Legal Reliability decision (should an AI-derived, unconfirmed
high-confidence deadline extraction be allowed to auto-create an operative
reminder), which precedes any implementation work.
