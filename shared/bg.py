# -*- coding: utf-8 -*-
"""
Background task registry.

WHY THIS EXISTS
───────────────
The codebase has 137 `asyncio.create_task(...)` calls in application code and,
before this module, zero `add_done_callback` and no task registry anywhere
(verified 2026-08-09 by grep across the whole tree). That is two distinct
defects in one line of code, repeated 137 times:

1. NO STRONG REFERENCE. The event loop keeps only a weak reference to a task.
   CPython's own documentation for `asyncio.create_task` says so explicitly and
   tells you to keep a reference: a task with no strong reference can be
   garbage-collected mid-execution, so the work simply stops, part-done, with
   no error anywhere.

2. NO EXCEPTION IS EVER OBSERVED. If the coroutine raises, nobody calls
   `task.exception()`, so the failure surfaces only as an "exception was never
   retrieved" line at interpreter GC time -- if at all. Every one of these
   failures is currently silent.

And a third at the process level: the shutdown handler in api.py drains exactly
two long-lived loops (the intake worker and the event-bus dispatch loop). The
other 135 tasks are killed with no grace on every SIGTERM -- which on Render
means every single redeploy. Nothing reconciles them afterwards; the three
existing reapers detect a missing DURABLE EVENT ROW, not a task that died.

What is lost on a redeploy today includes trial provisioning for a user who
signed up seconds earlier, knowledge-base embeddings (leaving a row in Postgres
that is permanently unsearchable), and immutable hash-chained audit writes --
including the one for GDPR erasure.

WHAT THIS MODULE DOES NOT DO
────────────────────────────
It does not make the work durable. A task registered here still dies if the
process dies; it just dies loudly instead of silently, and gets a bounded
chance to finish during graceful shutdown. Work that MUST survive a crash
belongs on the durable outbox (services/event_bus.py), not here. This module is
the floor, not the ceiling.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional, Set

logger = logging.getLogger("vindex.bg")

# Strong references to in-flight background tasks. A task removes itself in its
# own done-callback, so this set stays bounded by concurrency, not by lifetime.
_BG: Set[asyncio.Task] = set()


def _on_done(task: asyncio.Task) -> None:
    _BG.discard(task)

    # A cancelled task is not a failure -- it is what shutdown does on purpose.
    if task.cancelled():
        logger.info("[BG] task otkazan: %s", task.get_name())
        return

    exc = task.exception()
    if exc is not None:
        # logger.exception() would be wrong here: we are not inside the
        # exception's handler, so there is no active traceback to attach.
        logger.error(
            "[BG] pozadinski task '%s' pao: %s: %s",
            task.get_name(), type(exc).__name__, exc,
            exc_info=exc,
        )


def spawn(coro: Coroutine[Any, Any, Any], *, name: Optional[str] = None) -> asyncio.Task:
    """Drop-in replacement for `asyncio.create_task` that keeps a reference and
    observes the result.

    Use this instead of `asyncio.create_task` for any fire-and-forget work.
    `name` shows up in the log line when the task fails, so pass something that
    identifies the call site -- "gdpr_erasure_audit" beats "task-17".
    """
    task = asyncio.create_task(coro, name=name)
    _BG.add(task)
    task.add_done_callback(_on_done)
    return task


def pending_count() -> int:
    """Number of registered tasks still in flight. Used by tests and by the
    readiness surface; do not use it for control flow."""
    return len(_BG)


async def drain(timeout: float = 10.0) -> int:
    """Give registered tasks a bounded chance to finish during shutdown.

    Returns the number that were still pending when the timeout expired. Those
    are then left to the interpreter -- draining is best-effort by design, and a
    shutdown that hangs is worse than one that loses a log line.

    Bounded on purpose: gunicorn.conf.py sets graceful_timeout=30 (dead config
    today, since production runs the Dockerfile's bare uvicorn, but it is the
    number that applies the moment anyone activates the Procfile), and the two
    loops already drained ahead of this can consume ~45s between them. 10s here
    keeps the total inside a typical platform grace window.
    """
    if not _BG:
        return 0

    tasks = set(_BG)
    logger.info("[BG] drenaža %d pozadinskih taskova (timeout %.1fs)…", len(tasks), timeout)

    done, pending = await asyncio.wait(tasks, timeout=timeout)

    if pending:
        logger.warning(
            "[BG] %d task(ova) nije završilo u %.1fs — nastavljam gašenje: %s",
            len(pending), timeout,
            ", ".join(sorted(t.get_name() for t in pending))[:400],
        )
    else:
        logger.info("[BG] svi pozadinski taskovi završeni pre gašenja.")

    return len(pending)
