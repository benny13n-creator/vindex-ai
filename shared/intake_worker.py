# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_worker.py

Smart Intake Engine, Faza 0 — worker koji claim-uje/obrađuje/završava
poslove iz intake_jobs (shared/intake_queue.py, ADR-0002). Ovo NIJE
"privremeni worker" — founder je eksplicitno tražio da bude idempotentan,
restart-safe, graceful-shutdown, health-check friendly i metrics friendly
od prvog dana, ne kao naknadno dotoerivanje kada Faza 1 doda pravu AI
obradu.

Faza 0 _process() je namerno no-op — dokazuje da queue → claim → process →
outbox → dispatch → ack petlja radi PRE nego što Faza 1 stavi OCR/
klasifikaciju/ekstrakciju na to mesto. Menjati samo _process(), nikad
petlju/shutdown/heartbeat/reap logiku oko njega — to bi bilo tačno ono
"malo odstupanje od ADR-a" koje je founder izričito zabranio.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid

from shared import intake_queue

logger = logging.getLogger("vindex.intake_worker")

_DEFAULT_POLL_INTERVAL_S = 2.0
_DEFAULT_STALE_AFTER_S = 300
_DEFAULT_REAP_EVERY_N_TICKS = 30


class IntakeWorker:
    """Jedan worker proces. Više instanci (na više procesa/mašina) je
    bezbedno konkurentno zahvaljujući claim_intake_job() RPC-u (SELECT ...
    FOR UPDATE SKIP LOCKED) — nema potrebe za spoljnim leader-election-om."""

    def __init__(
        self,
        worker_id: str | None = None,
        poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
        stale_after_s: int = _DEFAULT_STALE_AFTER_S,
        reap_every_n_ticks: int = _DEFAULT_REAP_EVERY_N_TICKS,
    ) -> None:
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.poll_interval_s = poll_interval_s
        self.stale_after_s = stale_after_s
        self.reap_every_n_ticks = reap_every_n_ticks

        self._shutdown = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._tick_count = 0
        self.jobs_processed = 0
        self.jobs_failed = 0

    def start(self) -> None:
        """Pokreće petlju kao pozadinski asyncio task. Poziva se iz FastAPI
        startup hook-a — worker deli event loop sa HTTP serverom, nema
        zaseban proces u Fazi 0."""
        if self._task is not None:
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("[INTAKE_WORKER] %s pokrenut (poll=%.1fs, stale_after=%ds)", self.worker_id, self.poll_interval_s, self.stale_after_s)

    async def stop(self, timeout_s: float = 30.0) -> None:
        """Graceful shutdown — signalizira petlji da stane POSLE trenutnog
        tick-a (nikad usred obrade jednog posla), čeka do timeout_s da se
        task stvarno završi. Poziva se iz FastAPI shutdown hook-a."""
        self._shutdown.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=timeout_s)
            except asyncio.TimeoutError:
                logger.warning("[INTAKE_WORKER] %s nije stao u %.0fs — otkazujem task.", self.worker_id, timeout_s)
                self._task.cancel()
            self._task = None
        logger.info("[INTAKE_WORKER] %s zaustavljen (processed=%d failed=%d)", self.worker_id, self.jobs_processed, self.jobs_failed)

    async def _run(self) -> None:
        while not self._shutdown.is_set():
            try:
                did_work = await self._tick()
            except Exception:
                logger.exception("[INTAKE_WORKER] %s neočekivana greška u tick-u — petlja nastavlja, ne obara worker.", self.worker_id)
                did_work = False

            if not did_work:
                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=self.poll_interval_s)
                except asyncio.TimeoutError:
                    pass

    async def _tick(self) -> bool:
        """Jedan ciklus: povremeni reap → claim → process → complete/fail →
        heartbeat. Vraća True ako je posao obrađen (worker odmah pokušava
        sledeći claim bez čekanja poll_interval_s — adaptivno pollovanje)."""
        self._tick_count += 1
        if self._tick_count % self.reap_every_n_ticks == 0:
            await intake_queue.reap_stale_jobs(self.stale_after_s)

        job = await intake_queue.claim_next_job("received", "preprocessing")
        if not job:
            await intake_queue.record_heartbeat(self.worker_id, self.jobs_processed, self.jobs_failed)
            return False

        job_id = job["id"]
        try:
            await self._process(job)
            await intake_queue.mark_job_completed(job_id)
            self.jobs_processed += 1
        except Exception as exc:
            self.jobs_failed += 1
            logger.error("[INTAKE_WORKER] %s obrada neuspešna za job=%s: %s", self.worker_id, str(job_id)[:8], exc)
            await intake_queue.mark_job_failed(
                job_id, str(exc)[:500],
                job.get("attempts", 0), job.get("max_attempts", 5),
            )

        await intake_queue.record_heartbeat(self.worker_id, self.jobs_processed, self.jobs_failed)
        return True

    async def _process(self, job: dict) -> None:
        """Faza 0 — namerno no-op. Dokazuje da je infrastruktura (queue/
        outbox/audit/retry/reap) ispravna PRE nego što Faza 1 ovde doda
        pravu obradu (OCR → klasifikacija → ekstrakcija → case-match).
        Kada Faza 1 stigne: svaka stage-funkcija ovde mora ostati
        idempotentna — mark_job_completed je idempotentna po konstrukciji,
        ali stage logika (npr. "kreiraj dokaz u bazi") to mora biti eksplicitno
        (npr. upsert na content_sha256, ne insert) jer reap+retry znači da se
        _process() MOŽE pozvati više puta nad istim poslom."""
        pass


# ─── Singleton — deli se sa FastAPI startup/shutdown hook-ovima ────────────────

worker = IntakeWorker()


def start_worker() -> None:
    worker.start()


async def stop_worker() -> None:
    await worker.stop()
