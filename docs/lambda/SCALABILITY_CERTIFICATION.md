# SCALABILITY_CERTIFICATION — Program Lambda, Certification 008

The masterprompt's Phase 6 asks for measured behavior at 10/100/500/1000/5000/10000 documents and
10/100/1000+ users. **This cannot be honestly delivered**: no live staging environment, seed-data generator
at that scale, or load-testing tooling exists anywhere in this repository or in any prior Lambda
certification (004-007 all disclosed the identical constraint). Fabricating numbers would violate this
program's own evidence-honesty discipline (`Security Governance Framework`'s Evidence-Based Claims Policy).
This report is the structural-scaling analysis that IS available — what the code's own algorithmic shape
implies about growth — clearly labeled as such, not measured throughput.

## Per-document-count scaling (within one case)

- **Fixed this sprint**: `case_commander.py`, `zakon_monitoring.py`, `multi_agent.py` all previously used
  unordered or oldest-first document slices with a fixed cap (10-20 rows) — meaning a case with more
  documents than the cap didn't get slower, it got *silently wrong* (permanently missing newer documents).
  This is a correctness-at-scale bug, not a latency one; fixed via recency ordering (see
  `ARCHITECTURE_CERTIFICATION.md`/`PERFORMANCE_CERTIFICATION.md`).
- **Sound, re-verified**: `shared/case_context.py`'s 2-phase pattern (metadata for all documents, full text
  for a bounded recency-sampled subset) and `case_dna.py`'s Genome refresh (`_GENOME_MAX_DOCS=25` + char
  budget caps) both correctly bound their own cost independent of case size — the mechanism that should
  prevent an unbounded-cost blowup as one case accumulates hundreds of documents is in place and was not
  found broken by any team this sprint.

## Per-user-count scaling (across the whole platform)

- **Fixed this sprint**: `workers/background_agents.py` and `routers/morning_briefing.py`'s nightly cron
  jobs were the two structurally-evidenced findings with real per-user multiplication risk — both now use
  bounded concurrency instead of strict sequential processing, meaning the platform-wide nightly automation
  degrades gracefully (processes more users per unit time) rather than silently dropping coverage as the
  user base grows. See `PERFORMANCE_CERTIFICATION.md` for detail.
- **Already tracked, unresolved**: `LAMBDA-005` — `health_index.py`/`dashboard.py::command_center` fetch
  all of a user's `predmeti` rows with no `.limit()`. Per-user cost grows with that single user's own case
  count, not with total platform user count — a real but narrower risk than the cron findings above, not
  independently re-verified as fixed or broken this sprint.

## What would be needed to close this gap for real

A seed script generating N synthetic cases × M documents × K users against a disposable Supabase project,
plus a load-testing harness (k6, locust, or similar) hitting the highest-traffic endpoints
(`/api/pitanje`, Smart Intake finalize, Case Genome refresh, the two cron endpoints above). None of this
exists today. Recommended as a distinct, scoped future mission — not attempted here, and not guessed at.

**Verdict**: no measured scalability numbers exist for this platform, a standing and disclosed limitation
unchanged since Certification 004. The structural risks that WERE identifiable from code alone (2 cron
fan-out patterns, 3 document-sampling staleness bugs) were found and fixed this sprint.
