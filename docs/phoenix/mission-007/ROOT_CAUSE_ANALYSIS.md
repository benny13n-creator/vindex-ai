# Mission 007 — Root Cause Analysis

## Common root cause

`services/case_evolution.py`'s outer claim mechanism (`case_evolution_consequences`,
`(event_id, consequence_name)` uniqueness) was built to guarantee "attempted once, not
silently forgotten" — a genuinely different guarantee from "side effect happened at most
once," which requires each executor to ALSO be idempotent underneath. This distinction was
correctly reasoned about for 2 of 9 executors (the 2 reconcile-based ones,
`refresh_case_actions`/`project_notifications`, which are naturally idempotent by
construction, plus `evidence_classification`, explicitly guarded in Mission 006) but not
systematically audited across the remaining 6 until this and prior missions' Chaos/Red Team
passes found the gap.

`-016`'s root cause: `NEW_EVIDENCE_REGISTERED`'s registry entry was built early (Sprint 002)
before `refresh_case_actions` existed as a registerable consequence (added later, Sprint 003) —
every event type's registry entry that predates `refresh_case_actions`'s own introduction
needed a follow-up pass to add it where relevant, and `NEW_EVIDENCE_REGISTERED` was missed
(unlike `DOCUMENT_ACCEPTED`/`REVIEW_ACCEPTED`/`ROCISTE_ZAKAZANO`, which all got it).

## Why this mission only fully closes 1 of the 5 `-011` executors

Per Program Phoenix's own explicit rule ("Never invent new algorithms unless absolutely
unavoidable" + STOP GATE conditions including "architecture conflict"), a genuinely different
guard mechanism was required for each of the other 4 — `timeline_entry`'s "identical content,
recent window" idiom (reusing `-043`'s own proven pattern) is NOT directly portable to
`genome_refresh` (verzija-based, not content-based), the 2 audit executors (append-only
hash-chain semantics), or `case_intelligence_summary` (a documented but unenforced uniqueness
invariant that's really a missing-migration problem, not an application-code gap). Attempting
all 5 with the SAME mechanical pattern would have either not worked correctly or silently
introduced a new, unverified guard shape for each — the debt register's own prior instruction
("named as the concrete next-step template rather than attempted blind across all 5 in one
pass") anticipated exactly this.
