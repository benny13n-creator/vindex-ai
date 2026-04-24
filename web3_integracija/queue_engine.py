# -*- coding: utf-8 -*-
"""
Web3QueueEngine — async buffer između blockchain adaptera i Legal Engine-a.

Garantuje:
  - Backpressure: queue.full() → odbacivanje + logging (ne blokira caller)
  - Rate limiting: max 20 req/s prema Legal Engine-u (token bucket)
  - Spike defense: N worker taskova procesiraju paralelno (asyncio.create_task)
  - Retry: 3 pokušaja sa exponential backoff za svaki event
  - Izolacija: Legal Engine API nikada ne oseća direktni spike od 100 ev/s

Flow:
  blockchain event
      │
      ▼
  enqueue() ──→ asyncio.Queue(maxsize) ──→ [worker-0]──→ rate_limiter.wait()
                                        ├─→ [worker-1]──→ exponential_backoff()
                                        ├─→ [worker-2]──→ dispatch_fn(event)
                                        └─→ [worker-N]──→ health.record_*()
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

from .health       import HealthMonitor, HealthStatus
from .rate_limiter import TokenBucketRateLimiter
from .retry        import MaxRetriesExceeded, exponential_backoff, log_error
from .schemas      import Web3LegalEvent


class Web3QueueEngine:
    """
    Produkcijski async engine za procesiranje blockchain događaja.

    Primer upotrebe:
        async def posalji_legal_engine(event: Web3LegalEvent):
            async with aiohttp.ClientSession() as s:
                await s.post(url, json={"pitanje": event.to_prompt()})

        engine = Web3QueueEngine(dispatch_fn=posalji_legal_engine)
        await engine.start()

        prihvacen = await engine.enqueue(moj_event)
        # ... later ...
        await engine.stop()
    """

    DEFAULT_QUEUE_SIZE:  int = 1_000
    DEFAULT_WORKER_COUNT: int = 4
    DEFAULT_MAX_RPS:     int = 20
    DEFAULT_MAX_RETRIES: int = 3

    def __init__(
        self,
        dispatch_fn:    Callable[[Web3LegalEvent], Awaitable[None]],
        max_queue_size: int = DEFAULT_QUEUE_SIZE,
        max_rps:        int = DEFAULT_MAX_RPS,
        worker_count:   int = DEFAULT_WORKER_COUNT,
        max_retries:    int = DEFAULT_MAX_RETRIES,
    ):
        self._dispatch      = dispatch_fn
        self._queue         = asyncio.Queue(maxsize=max_queue_size)
        self._limiter       = TokenBucketRateLimiter(max_rps)
        self._health        = HealthMonitor(max_rps, worker_count)
        self._worker_n      = worker_count
        self._max_retries   = max_retries
        self._workers:      list[asyncio.Task] = []
        self._running:      bool = False
        self._total_dropped: int = 0  # eventi odbijeni zbog punog queue-a

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Pokreće worker taskove. Pozivati jednom po event loopu."""
        if self._running:
            return
        self._running = True
        self._workers = [
            asyncio.create_task(
                self._worker_loop(worker_id=i),
                name=f"web3-worker-{i}",
            )
            for i in range(self._worker_n)
        ]

    async def stop(self, grace_seconds: float = 10.0) -> None:
        """
        Zaustavlja engine.
        Čeka do grace_seconds da se queue isprazni, zatim canceluje workere.
        """
        self._running = False
        try:
            await asyncio.wait_for(self._queue.join(), timeout=grace_seconds)
        except asyncio.TimeoutError:
            pass
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    # ── Enqueue (backpressure) ────────────────────────────────────────────────

    async def enqueue(self, event: Web3LegalEvent) -> bool:
        """
        Instant enqueue sa backpressure.
        Vraća False (ne baca) ako je queue pun — caller mora da throttluje.
        """
        if self._queue.full():
            self._total_dropped += 1
            log_error(
                event,
                OverflowError(
                    f"Queue pun ({self._queue.maxsize} eventa). "
                    f"Backpressure aktivan — event odbačen. "
                    f"Ukupno odbačeno: {self._total_dropped}"
                ),
                context="enqueue/backpressure",
            )
            return False
        await self._queue.put(event)
        return True

    async def enqueue_wait(
        self,
        event:   Web3LegalEvent,
        timeout: float = 5.0,
    ) -> bool:
        """
        Čeka slobodno mesto u queue-u (throttling).
        Vraća False ako timeout istekne — nikada ne baca izuzetak.
        """
        try:
            await asyncio.wait_for(self._queue.put(event), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            self._total_dropped += 1
            log_error(
                event,
                TimeoutError(f"Timeout {timeout}s — queue zaglavljeno."),
                context="enqueue_wait/timeout",
            )
            return False

    # ── Worker loop ───────────────────────────────────────────────────────────

    async def _worker_loop(self, worker_id: int) -> None:
        """Beskonačna petlja: uzima event iz queue-a, procesira, ponovi."""
        while self._running:
            # Čekaj event, ali ne beskonačno (da bi proverjeli _running)
            try:
                event: Web3LegalEvent = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            start_ts = time.monotonic()
            try:
                # Rate limiting: čekaj token pre slanja ka Legal Engine-u
                await self._limiter.wait()

                # Dispatch sa retry
                await exponential_backoff(
                    coro_fn      = lambda e=event: self._dispatch(e),
                    max_attempts = self._max_retries,
                    base_delay   = 1.0,
                    max_delay    = 30.0,
                    jitter       = True,
                    event        = event,
                )
                self._health.record_success(time.monotonic() - start_ts)

            except MaxRetriesExceeded as exc:
                self._health.record_failure()
                log_error(event, exc.last_exc, context=f"worker-{worker_id}/max_retries")

            except asyncio.CancelledError:
                self._queue.task_done()
                raise  # mora biti re-raised za cancel propagation

            except Exception as exc:
                self._health.record_failure()
                log_error(event, exc, context=f"worker-{worker_id}/unexpected")

            finally:
                self._queue.task_done()

    # ── Monitoring ────────────────────────────────────────────────────────────

    def get_health(self) -> HealthStatus:
        """Trenutni zdravstveni status engine-a."""
        return self._health.get_status(
            queue_size     = self._queue.qsize(),
            queue_capacity = self._queue.maxsize,
        )

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def total_dropped(self) -> int:
        return self._total_dropped

    @property
    def is_running(self) -> bool:
        return self._running and any(not t.done() for t in self._workers)

    def __repr__(self) -> str:  # pragma: no cover
        h = self.get_health()
        return (
            f"Web3QueueEngine("
            f"status={h.status}, "
            f"queue={h.queue_size}/{h.queue_capacity}, "
            f"rps={h.rate_limit_rps}, "
            f"workers={h.worker_count})"
        )
