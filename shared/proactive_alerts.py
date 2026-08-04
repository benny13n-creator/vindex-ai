# -*- coding: utf-8 -*-
"""
Vindex AI — shared/proactive_alerts.py

Program Alpha (2026-08-04): the canonical, single-source-of-truth function for
creating a `proactive_alerts` row. Before this file existed, 7 files independently
constructed their own `supa.table("proactive_alerts").insert({...})` call (12
independent call sites total) — zero shared helper, zero shared retry/failure
discipline.

Historical proof this was a real, not theoretical, risk: `routers/case_dna.py`'s
own comment documents that one of its 3 insert sites used wrong column names
(`tekst_alerta`/`tip_alerta`/`hitnost` instead of the real schema's
`naslov`/`opis`/`tip`/`urgentnost`) and silently failed on EVERY call for the
entire time the feature existed, undetected until a 2026-07-18 "Reality
Validation" pass caught it by accident. A canonical function with named
parameters turns that exact mistake into an immediate Python `TypeError` at the
call site — not a silent Postgres schema-mismatch swallowed by a broad `except`.

This also absorbs Project Phoenix's own proven retry + durable-failure-audit
pattern (previously only applied to `morning_briefing.py`'s nightly loop, one of
the 12 call sites) so every caller gets it once, not per call site.

Mission Olympus governance review (2026-08-04, Agent 18/Backend Engineering
Review's first live finding, F-5): the internal retry's blocking sleep
(up to `_MAX_ATTEMPTS * 0.5 * attempt`s ~= 1.5s per failing alert) compounds
badly for the 3 `services/event_bus.py` handlers invoked from
`dispatch_pending_events()`'s SERIAL batch loop (up to `DISPATCH_BATCH_SIZE`
rows per batch) -- under a sustained proactive_alerts outage, a slow batch
could exceed migration 091's `p_stale_claim_seconds` (30s) reclaim window,
letting a second gunicorn worker reclaim and duplicate-process rows worker A
is still retrying -- precisely the race Mission Keystone's atomic-claim fix
exists to close. Those 3 callers pass `retry_internally=False`: a single
attempt, immediate durable-audit-on-failure, and rely on
`dispatch_pending_events()`'s own OUTER retry (`MAX_DISPATCH_ATTEMPTS=5`,
re-driven by the 3s poll, not a blocking sleep) instead of a second,
redundant, blocking retry layer underneath it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("vindex.proactive_alerts")

_MAX_ATTEMPTS = 3


async def create_proactive_alert(
    supa,
    *,
    user_id: str,
    tip: str,
    naslov: str,
    opis: str = "",
    urgentnost: str = "normalna",
    predmet_id: Optional[str] = None,
    retry_internally: bool = True,
) -> bool:
    """Insert one `proactive_alerts` row. Up to `_MAX_ATTEMPTS` retries with a
    short backoff (mirrors Project Phoenix's own proven `morning_briefing.py`
    cadence: `0.5 * (attempt + 1)`s) by default. On exhaustion, logs at ERROR
    level (not DEBUG — a lost proactive alert is exactly the kind of critical
    information this table exists to surface) and writes a durable
    `proactive_alert_insert_failed` audit entry via `shared/audit_immutable.py`
    so the loss is provably recorded, never silently lost without a trace.

    `retry_internally=False` skips the internal retry/backoff entirely (a
    single attempt) — for callers that already sit inside an OUTER retry
    mechanism with its own backoff (currently: the 3 services/event_bus.py
    handlers invoked from dispatch_pending_events()'s batch loop), so retry
    delay isn't compounded twice, once inside this function and once outside
    it (see module docstring, Mission Olympus F-5).

    Returns True if the insert succeeded (possibly after retry), False if it
    failed on every attempt.
    """
    attempts = _MAX_ATTEMPTS if retry_internally else 1
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            await asyncio.to_thread(
                lambda: supa.table("proactive_alerts").insert({
                    "user_id":    user_id,
                    "predmet_id": predmet_id,
                    "tip":        tip,
                    "naslov":     naslov,
                    "opis":       opis,
                    "urgentnost": urgentnost,
                    "procitana":  False,
                }).execute()
            )
            return True
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                await asyncio.sleep(0.5 * (attempt + 1))

    logger.error(
        "[PROACTIVE_ALERTS] insert TRAJNO neuspešan user=%.8s tip=%s posle %d pokušaja: %s",
        user_id, tip, attempts, last_exc,
    )
    from shared.audit_immutable import log_action
    asyncio.create_task(log_action(
        action="proactive_alert_insert_failed", user_id=user_id,
        resource_type="proactive_alert", resource_id=predmet_id,
        metadata={"tip": tip, "naslov": (naslov or "")[:200], "greska": str(last_exc)[:300]},
    ))
    return False
