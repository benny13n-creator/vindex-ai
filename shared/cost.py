# -*- coding: utf-8 -*-
"""
shared/cost.py — GPT API cost tracking per request.

Usage:
  1. Call begin_cost_tracking() at the start of a request handler.
  2. _pozovi_openai and strategija._gpt_json/_gpt_text automatically call record_cost().
  3. Call asyncio.create_task(log_cost_to_db(uid, endpoint)) after the GPT call returns.

ContextVar propagates to threads started with asyncio.to_thread (Python 3.7+ copies context),
so record_cost() inside worker threads correctly mutates the same list.
"""
from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger("vindex.cost")

# GPT-4o pricing (USD per 1 000 tokens, June 2025)
_PRICES: dict[str, dict[str, float]] = {
    "gpt-4o":        {"input": 0.0025,  "output": 0.0100},
    "gpt-4o-mini":   {"input": 0.00015, "output": 0.0006},
    "gpt-4":         {"input": 0.030,   "output": 0.060},
    "gpt-3.5-turbo": {"input": 0.001,   "output": 0.002},
}

_request_costs: ContextVar[Optional[list]] = ContextVar("_request_costs", default=None)


def begin_cost_tracking() -> None:
    """Initialize an empty accumulator for the current async task / thread context."""
    _request_costs.set([])


def record_cost(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Append one GPT call's token counts. No-op if begin_cost_tracking() was not called."""
    costs = _request_costs.get(None)
    if costs is None:
        return
    costs.append({
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    })


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    prices = _PRICES.get(model) or _PRICES["gpt-4o"]
    return round(
        prompt_tokens / 1000 * prices["input"] + completion_tokens / 1000 * prices["output"],
        6,
    )


def get_request_total() -> tuple[int, int, float]:
    """Return (prompt_tokens, completion_tokens, cost_usd) summed over all recorded calls."""
    costs = _request_costs.get(None) or []
    p = sum(c["prompt_tokens"] for c in costs)
    c = sum(c["completion_tokens"] for c in costs)
    usd = sum(estimate_cost(e["model"], e["prompt_tokens"], e["completion_tokens"]) for e in costs)
    return p, c, round(usd, 6)


async def log_cost_to_db(user_id: str, endpoint: str) -> None:
    """Fire-and-forget: write accumulated cost for this request to api_costs table."""
    from shared.deps import _get_supa
    costs = _request_costs.get(None) or []
    if not costs:
        return
    prompt_tokens, completion_tokens, cost_usd = get_request_total()
    if cost_usd == 0.0:
        return
    dominant_model = max(
        set(c["model"] for c in costs),
        key=lambda m: sum(
            c["prompt_tokens"] + c["completion_tokens"] for c in costs if c["model"] == m
        ),
    )
    try:
        await asyncio.to_thread(
            lambda: _get_supa().table("api_costs").insert({
                "user_id":          user_id,
                "endpoint":         endpoint,
                "prompt_tokens":    prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens":     prompt_tokens + completion_tokens,
                "cost_usd":         cost_usd,
                "model":            dominant_model,
                "calls":            len(costs),
            }).execute()
        )
    except Exception:
        logger.warning("[COST] DB log neuspešan — ne blokira odgovor")
