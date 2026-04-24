# -*- coding: utf-8 -*-
"""
Exponential backoff retry + centralizovano logovanje grešaka.
Loguje u web3_integracija/logs/error.log (UTF-8, JSONL format).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import random
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import Web3LegalEvent

# ─── Log putanja ─────────────────────────────────────────────────────────────

def _log_path() -> Path:
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "error.log"


def log_error(
    event:   Optional["Web3LegalEvent"],
    exc:     Exception,
    context: str = "",
) -> None:
    """
    Upisuje grešku u error.log (JSONL, UTF-8).
    Nikada ne baca izuzetak — logovanje ne sme ugroziti glavni tok.
    """
    try:
        ts     = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        tx_id  = getattr(event, "event_id", "UNKNOWN") if event else "UNKNOWN"
        entry  = {
            "timestamp":      ts,
            "transaction_id": tx_id,
            "error_type":     type(exc).__name__,
            "error_msg":      str(exc),
            "context":        context or "",
        }
        line = json.dumps(entry, ensure_ascii=False)
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # silent — logovanje ne sme ubiti radni tok


# ─── Retry logika ─────────────────────────────────────────────────────────────

# HTTP statusi koji opravdavaju retry (server greška / privremena nedostupnost)
RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class MaxRetriesExceeded(Exception):
    """Bačena kada su iscrpljeni svi pokušaji."""
    def __init__(self, last_exc: Exception, attempts: int):
        self.last_exc = last_exc
        self.attempts = attempts
        super().__init__(
            f"Svi {attempts} pokušaj(a) su neuspešni. Poslednja greška: {last_exc}"
        )


async def exponential_backoff(
    coro_fn:      Callable[[], Awaitable[Any]],
    max_attempts: int   = 3,
    base_delay:   float = 1.0,
    max_delay:    float = 30.0,
    jitter:       bool  = True,
    event:        Optional["Web3LegalEvent"] = None,
) -> Any:
    """
    Izvršava async coroutine sa exponential backoff retry logikom.

    Pokušaji:  1 → odmah
               2 → base_delay * 2^0  (+ jitter)
               3 → base_delay * 2^1  (+ jitter)
               ...do max_delay

    Baca MaxRetriesExceeded ako svi pokušaji propadnu.
    Svaki neuspeli pokušaj se loguje u error.log.

    Primer:
        await exponential_backoff(lambda: http_post(payload), event=my_event)
    """
    last_exc: Exception = RuntimeError("Nema pokušaja")

    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn()

        except Exception as exc:
            last_exc = exc
            log_error(
                event,
                exc,
                context=f"Pokušaj {attempt}/{max_attempts}",
            )
            if attempt == max_attempts:
                break

            delay = min(base_delay * (2.0 ** (attempt - 1)), max_delay)
            if jitter:
                delay *= 0.5 + random.random() * 0.5
            await asyncio.sleep(delay)

    raise MaxRetriesExceeded(last_exc, max_attempts)
