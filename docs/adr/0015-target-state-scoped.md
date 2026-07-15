# ADR-0015: Target-state tracking, scoped to dimensions where "target" has clear meaning

- Status: Accepted
- Date: 2026-07-15

## Context

The State Diff Engine (ADR-0012) shows Old → Current. A proposed extension:
Old → Current → **Target** — turning the diff from analysis ("what
changed") into navigation ("what's still needed"). Example: Case
Completeness at 84% with a target of 100%, and the specific missing items
(proof of service) named. This is a genuinely strong idea, but "target"
does not mean the same thing for every dimension.

## Decision

Target-state tracking is adopted, but scoped per dimension rather than
applied uniformly:

- **Completeness** — target is trivially 100%; the gap is literally the
  unchecked items in `case_completeness_rules`. Build first.
- **Confidence** — target is a fixed high-water mark (e.g. 90%+); the gap
  is the specific low-confidence entities (ADR-0005) still needing review.
  Build alongside Completeness.
- **Health / Risk / Strategy posture** — target is not self-evidently a
  fixed number. A "target risk score" would need either a fixed benchmark
  (e.g. the median health of similar cases resolved favorably, which
  requires a corpus Vindex doesn't have yet) or an explicit target a lawyer
  sets manually per case. Deferred until one of those two approaches is
  actually designed — not built as a fake fixed target now.

## Alternatives Considered

- **Apply a uniform "target = 100" or "target = best observed" rule across
  every dimension.** Rejected — for Health/Risk specifically this would be
  a fabricated number dressed up as a target, which is exactly the "honest
  empty state over invented numbers" standard this session already
  committed to elsewhere (Revenue Intelligence).
- **Skip target-state entirely, ship Old → Current only.** Rejected —
  Completeness and Confidence have unambiguous, already-available targets;
  not shipping them there because two harder dimensions aren't ready yet
  would be leaving real, low-cost value on the table.

## Consequences

- Completeness and Confidence get "what's still needed" navigation in the
  same phase they ship. Health/Risk/Strategy get it later, once a real
  target-setting mechanism is designed — tracked as a follow-up decision,
  not silently dropped.
