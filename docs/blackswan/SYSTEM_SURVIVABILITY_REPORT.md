# SYSTEM_SURVIVABILITY_REPORT — Operation Black Swan, Mission 001

What survives vs. what breaks, by subsystem, plus the dedicated cross-subsystem (Scenario 17 / Team 14)
findings — the ones no single-scenario team could have found.

## Subsystems that held up under active adversarial testing

- **Multi-tenant isolation** (Scenario 13, Team 8): 0 new leaks across context/cache/ownership/AI/
  notification categories, tested via real multi-threaded/multi-tenant reproduction. Both previously-known
  leaks re-verified still fixed.
- **Event Bus core mechanics** (Scenario 16, Team 10): starvation, deadlock, and livelock all actively
  simulated at 5,000-row scale and ruled out. The claim-based concurrency design genuinely works.
- **Genome data integrity under crash** (Scenario 6, Team 5): the destructive-replace guard (from a prior
  certification) holds — a crash never corrupts the live Genome column, only (in one case) its audit trail.
- **Zero-byte/blank-PDF/OCR-failure handling** (Scenario 14, Team 2): all confirmed genuinely fail-soft.
- **Smart Intake's upload and finalize paths** (Scenarios 5, 6, 11, Human Attack): consistently the most
  hardened code in the platform across every team that touched it — idempotency-key hashing, atomic claim
  RPCs, resume-on-restart logic all held under direct adversarial pressure.
- **AI-output range clamping, where it already existed**: `case_actions.prioritet` and Genome's own
  `snaga_predmeta_procent` both correctly clamp/validate a GPT-influenced value — proving the pattern works
  when applied; the gaps found (`matter_intel`, CIO, Hearing CC) were places the pattern hadn't been
  applied yet, not a flaw in the pattern itself. All 3 gaps fixed this mission.

## Subsystems that broke under active adversarial testing

- **Billing invariants**: the single most-independently-confirmed failure in this mission — 2 different
  teams, 2 different trigger mechanisms (connection exception, process crash), same root cause (no
  compensating rollback on the second write of a 2-step sequence). CRITICAL, now fixed both ways.
- **Deadline tracking under absence**: the platform's second CRITICAL finding, and arguably its most
  consequential for a legal product — 4 independent code paths (risk score, canonical priority engine, case
  actions, notification regeneration) all independently forgot that a deadline could pass while nobody was
  looking. Now fixed in all 4 places.
- **Optimistic concurrency, inconsistently applied**: some endpoints have it (billing, predmeti close,
  now kanban and bulk-status), most don't. The pattern that works isn't systematically applied — this
  mission fixed the highest-impact gaps found but named several more as debt (`DEBT-012`, `-013`, `-014`).
- **Resource pooling under tenant load**: the single-shared-threadpool noisy-neighbor finding (Team 14) is
  the mission's clearest evidence that "no cross-tenant DATA leak" (true, verified) is not the same claim
  as "no cross-tenant PERFORMANCE impact" (false, reproduced) — a distinction worth remembering going
  forward.

## Cross-subsystem findings (Scenario 17, Team 14) — the mission's own standout work

Team 14 was deliberately structured differently from every other team: instead of attacking one subsystem,
it combined 2+ stressors from the other 16 scenarios and looked specifically for interactions neither
stressor alone would produce.

1. **A residual gap in the prior certification's own Event Bus heartbeat fix**: the row currently being
   processed is removed from the "remaining" tracking set before its own handler runs, so it never gets
   heartbeated WHILE it's the one taking a long time — only the other, still-queued rows do. Reproduced:
   `run_case_pipeline` ran twice with overlapping wall-clock windows for the same event. **FIXED** this
   mission via a pre-process heartbeat on the row about to be handled, not just the remainder.
2. **The noisy-neighbor threadpool contention** described above — invisible to Team 8's data-leak-focused
   testing and to Team 1's single-tenant concurrency testing, only visible when both a bulk-upload load and
   an unrelated tenant's request were combined. **DEBT-016**.
3. **A refuted hypothesis that surfaced a real adjacent finding**: a DB blip during the intake dedup check
   does NOT fail open as hypothesized (it fails closed — a hard error, not a silent duplicate) — but
   ordinary concurrency alone, no DB trouble needed, already defeats the same dedup check. **DEBT-017**.
4. **The mission's single most striking number**: combining "500 concurrent lawyers" with "OpenAI degraded"
   produced 415/500 (83%) requests failing purely from AI-semaphore queue-timeout, even though OpenAI itself
   never permanently failed a single call. Neither stressor alone produces this. **DEBT-018** (the
   underlying capacity-collapse architecture; the credit-loss consequence of it is already fixed).

**This is the concrete argument for why a dedicated cross-subsystem team belongs in every future chaos
mission**: 3 of its 4 findings were genuinely invisible to all 13 other teams working in isolation.
