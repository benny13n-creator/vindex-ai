# -*- coding: utf-8 -*-
"""
Health monitoring za Web3 adapter.
Meri latency od dolaska blockchain eventa do odgovora Legal Engine-a.
Thread-safe (koristi threading.Lock za kompatibilnost sa asyncio + sync kontekstima).
"""
from __future__ import annotations

import json
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class HealthStatus:
    status:           str    # "healthy" | "degraded" | "down"
    queue_size:       int
    queue_capacity:   int
    avg_latency_ms:   float
    p95_latency_ms:   float
    success_rate:     float  # 0.0 – 1.0
    total_processed:  int
    total_errors:     int
    uptime_seconds:   float
    rate_limit_rps:   int
    worker_count:     int

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"


class HealthMonitor:
    """
    Sliding window monitor: čuva poslednjih WINDOW merenja latency-ja.

    Pragovi za status:
        healthy  — success_rate ≥ 0.90 I avg_latency < 5000 ms
        degraded — success_rate ≥ 0.50 ILI avg_latency ≥ 5000 ms
        down     — success_rate < 0.50
    """

    WINDOW: int = 200  # broj poslednjih merenja

    def __init__(self, rate_limit_rps: int = 20, worker_count: int = 4):
        self._start_time   = time.monotonic()
        self._latencies    = deque(maxlen=self.WINDOW)
        self._total_ok     = 0
        self._total_err    = 0
        self._rate_rps     = rate_limit_rps
        self._worker_count = worker_count
        self._lock         = threading.Lock()

    # ── Snimanje merenja ──────────────────────────────────────────────────────

    def record_success(self, latency_seconds: float) -> None:
        with self._lock:
            self._latencies.append(latency_seconds * 1_000)  # → ms
            self._total_ok += 1

    def record_failure(self) -> None:
        with self._lock:
            self._total_err += 1

    # ── Čitanje statusa ───────────────────────────────────────────────────────

    def get_status(
        self,
        queue_size:     int = 0,
        queue_capacity: int = 0,
    ) -> HealthStatus:
        with self._lock:
            lats  = list(self._latencies)
            total = self._total_ok + self._total_err

        avg_ms = statistics.mean(lats)       if lats else 0.0
        p95_ms = _percentile(lats, 95)       if lats else 0.0
        sr     = self._total_ok / total      if total > 0 else 1.0

        if sr < 0.50:
            status = "down"
        elif sr < 0.90 or avg_ms > 5_000:
            status = "degraded"
        else:
            status = "healthy"

        return HealthStatus(
            status          = status,
            queue_size      = queue_size,
            queue_capacity  = queue_capacity,
            avg_latency_ms  = round(avg_ms, 2),
            p95_latency_ms  = round(p95_ms, 2),
            success_rate    = round(sr, 4),
            total_processed = total,
            total_errors    = self._total_err,
            uptime_seconds  = round(time.monotonic() - self._start_time, 1),
            rate_limit_rps  = self._rate_rps,
            worker_count    = self._worker_count,
        )

    def reset(self) -> None:
        with self._lock:
            self._latencies.clear()
            self._total_ok  = 0
            self._total_err = 0


def _percentile(data: list[float], pct: int) -> float:
    """Vraća pct-ti percentil sortirane liste."""
    if not data:
        return 0.0
    s = sorted(data)
    idx = int(len(s) * pct / 100)
    return s[min(idx, len(s) - 1)]
