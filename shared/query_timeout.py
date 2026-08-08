# -*- coding: utf-8 -*-
"""
Vindex AI — shared/query_timeout.py

Program Phoenix, Mission 013 (LIVINGSYS-DEBT-040): Dashboard/Workspace's
highest-traffic endpoints each fan out 6-13 parallel Supabase queries via
asyncio.gather with no overall bound — relying on the client library's own
~120s implicit ceiling per query, no fast-fail. This module is the single
canonical helper both endpoints use instead of each hand-rolling its own
wait_for/except boilerplate.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable

logger = logging.getLogger("vindex.query_timeout")

DEFAULT_TIMEOUT_SECONDS = 15.0


class _EmptyResult:
    """Placeholder matching a Supabase response's own `.data` shape."""
    data: list = []


async def gather_with_timeout(*coros: Awaitable, timeout: float = DEFAULT_TIMEOUT_SECONDS, label: str = ""):
    """`asyncio.gather(*coros, return_exceptions=True)` bounded by an overall
    timeout. On timeout, returns a `TimeoutError` placeholder for EVERY
    coroutine instead of hanging the whole request -- callers already handle
    `return_exceptions=True`'s per-item `isinstance(r, Exception)` fallback
    (a pre-existing requirement of that flag), so a timeout transparently
    flows through that same, already-tested degrade-gracefully path with no
    additional call-site logic."""
    try:
        return await asyncio.wait_for(
            asyncio.gather(*coros, return_exceptions=True), timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[QUERY_TIMEOUT] %s: %d upita premašilo %.0fs -- vraćam prazne rezultate",
            label or "gather", len(coros), timeout,
        )
        return (asyncio.TimeoutError(f"query timeout after {timeout}s"),) * len(coros)


async def single_with_timeout(coro: Awaitable, *, timeout: float = DEFAULT_TIMEOUT_SECONDS, label: str = ""):
    """Bounds a single (non-gathered) query. Returns an empty-data
    placeholder on timeout rather than raising, matching `gather_with_
    timeout`'s own fail-open philosophy."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "[QUERY_TIMEOUT] %s premašio %.0fs -- vraćam prazan rezultat",
            label or "upit", timeout,
        )
        return _EmptyResult()
