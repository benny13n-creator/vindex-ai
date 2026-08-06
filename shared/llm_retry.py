# -*- coding: utf-8 -*-
"""
LLM retry/backoff — centralni tenacity decorator za sve direktne OpenAI pozive.

Retry-uje SAMO prolazne greške (rate-limit 429, server errors 500/502/503/504,
connection/timeout greške) sa exponential backoff-om, max 3 pokušaja ukupno.
NE retry-uje 400 (Bad Request) ili 401 (Unauthorized) -- ti su deterministički
i ponavljanje ne menja ishod.

Radi transparentno na sync i async funkcijama (tenacity sam detektuje
coroutine funkcije i koristi AsyncRetrying).
"""
import logging

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_random,
    before_sleep_log,
)

logger = logging.getLogger("vindex.llm_retry")

llm_retry = retry(
    stop=stop_after_attempt(3),
    # Program Lambda, Certification 006 (2026-08-07) -- Chaos Engineer fork
    # found the plain wait_exponential produced an IDENTICAL, deterministic
    # backoff schedule (1s->2s->4s->8s) for every concurrent caller -- during
    # a sustained OpenAI outage, every request that started retrying around
    # the same wall-clock time would re-hit the API in near-lockstep the
    # moment it recovers, a real thundering-herd risk. + wait_random(0, 2)
    # adds 0-2s of jitter on top of the SAME exponential envelope (keeps the
    # existing min=1/max=8 floor/ceiling, just spreads concurrent retries
    # instead of synchronizing them) -- tenacity's own supported composition,
    # not a new mechanism.
    wait=wait_exponential(multiplier=1, min=1, max=8) + wait_random(0, 2),
    retry=retry_if_exception_type(
        (RateLimitError, InternalServerError, APITimeoutError, APIConnectionError)
    ),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
