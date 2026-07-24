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
    before_sleep_log,
)

logger = logging.getLogger("vindex.llm_retry")

llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(
        (RateLimitError, InternalServerError, APITimeoutError, APIConnectionError)
    ),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
