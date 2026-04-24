# -*- coding: utf-8 -*-
"""
Token bucket rate limiter za Web3 adapter.
Default: MAX_RPS = 20 (podesivo pri inicijalizaciji).
"""
from __future__ import annotations

import asyncio
import time


DEFAULT_MAX_RPS: int = 20


class TokenBucketRateLimiter:
    """
    Klasični token bucket algoritam.

    - Bucket se puni brzinom max_rps tokena/sekundi.
    - Svaki zahtev troši 1 token.
    - Ako nema tokena: wait() blokira dok ne stigne sledeći token.
    - acquire() vraća True/False bez blokiranja (za non-blocking probe).
    """

    def __init__(self, max_rps: int = DEFAULT_MAX_RPS):
        if max_rps <= 0:
            raise ValueError(f"max_rps mora biti > 0, dobijeno: {max_rps}")
        self._max      = float(max_rps)
        self._tokens   = float(max_rps)   # počinjemo s punim bucketom
        self._last_ts  = time.monotonic()
        self._lock     = asyncio.Lock()

    # ── Interni refill (uvek pozivati unutar lock-a) ─────────────────────────

    def _refill(self) -> None:
        now           = time.monotonic()
        elapsed       = now - self._last_ts
        self._tokens  = min(self._max, self._tokens + elapsed * self._max)
        self._last_ts = now

    # ── Javni API ─────────────────────────────────────────────────────────────

    async def acquire(self) -> bool:
        """Non-blocking probe. Vraća True ako je token dostupan."""
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    async def wait(self) -> None:
        """Blokira dok token ne postane dostupan, zatim ga troši."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            # Sačekaj proporcionalno koliko fali do sledećeg tokena
            async with self._lock:
                deficit = max(0.0, 1.0 - self._tokens)
            wait_s = deficit / self._max
            await asyncio.sleep(max(0.001, wait_s))

    @property
    def current_tokens(self) -> float:
        """Trenutni nivo bucketa (0.0 – max_rps)."""
        now     = time.monotonic()
        elapsed = now - self._last_ts
        return min(self._max, self._tokens + elapsed * self._max)

    @property
    def max_rps(self) -> int:
        return int(self._max)

    def __repr__(self) -> str:  # pragma: no cover
        return f"TokenBucketRateLimiter(max_rps={self._max:.0f}, tokens={self.current_tokens:.2f})"
