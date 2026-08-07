# PERFORMANCE_CERTIFICATION — Program Lambda, Certification 008

Covers Team 9 (Performance & Scalability). **No live staging/load-test environment is available in this
engagement** — a standing, previously-disclosed constraint across every prior Lambda certification. This
report is static/structural code analysis, not measured load-test numbers; explicitly not claiming to be
the latter. Per the mission's own North Star (`.vindex_ai_team/MISSION_BOARD.md`), only findings with real
structural evidence are reported — no vague "this could be slow" claims.

## HIGH — fixed this sprint

**`workers/background_agents.py`** (the nightly cron that runs AI agents for every active user):
`_get_active_user_ids` fetches every active user with no `.limit()`, then processed (user × agent_type)
pairs **fully sequentially** — up to 20 cases per user × up to 5 sequential GPT-4o-mini calls per case, no
`asyncio.gather`, no per-user checkpoint. Correction from Red Team review: this is **hard-capped at 600s**
by `api.py`'s own `asyncio.wait_for` wrapper — it cannot hang for hours as first described. The real,
Red-Team-confirmed consequence: as active-user count grows, later users in iteration order silently get
fewer or zero agent runs within that 600s window, with no rotation across days. Fixed via bounded
concurrency (`asyncio.Semaphore`, default 5 concurrent) so substantially more users fit inside the same
window, with budget reservation moved before the `await` to avoid a new TOCTOU under concurrency.

## MEDIUM — fixed this sprint

**`routers/morning_briefing.py::briefing_cron`**: sequential, up to 500 users, explicit 0.5s sleep per
iteration + 1 GPT call + SMTP send each — and, unlike `background_agents.py`, **no internal timeout wrapper
at all**, invoked directly by an external cron caller. Genuine unbounded-duration risk (500 × several
seconds could exceed 20+ minutes with no guardrail). Fixed via the same bounded-concurrency pattern plus a
new 540s `asyncio.wait_for` cap, mirroring `background_agents.py`'s own established precedent.

## LOW — fixed this sprint

**`routers/multi_agent.py`**'s document sampler used `.order("redni_broj")` ascending (oldest-first),
`.limit(10)` — bounded in count, but permanently stuck on a case's original oldest 10 documents as it grows,
unlike the 3 already-migrated `case_context.py` consumers. Fixed via descending order.

## Verified sound, no new issue found

`shared/case_context.py`'s 2-phase bounded fetch pattern, `case_dna.py`'s Genome refresh caps
(`_GENOME_MAX_DOCS=25` + dual char-budget caps), `routers/copilot.py` (Certification 006's own fix, still
holding), `case_commander.py`/`cio.py`'s bounded `asyncio.gather` over ≤20 cases.

## Already tracked, re-confirmed, not new

`LAMBDA-005` (`health_index.py`/`dashboard.py::command_center` unbounded `predmeti` fetch, no `.limit()`) —
present, unchanged, not addressed this sprint (outside this sprint's fix budget).

**Verdict**: 2 new structurally-evidenced scalability risks (both cron/background-agent fan-out shape) plus
1 low-severity sampler-staleness issue, all fixed this sprint. No load-test numbers exist for this
platform in any prior or current certification — that gap itself is not new, and remains a standing,
disclosed limitation, not something this sprint could close without a live environment.
