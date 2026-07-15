# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_worker.py

Smart Intake Engine — worker koji claim-uje/obrađuje/završava poslove iz
intake_jobs (shared/intake_queue.py, ADR-0002). Ovo NIJE "privremeni
worker" — founder je eksplicitno tražio da bude idempotentan, restart-safe,
graceful-shutdown, health-check friendly i metrics friendly od prvog dana.

Faza 1A _process(): decrypt+OCR → klasifikacija (shared/intake_classify.py)
→ ekstrakcija Confidence Graph-a (shared/intake_extract.py) → review queue
routing (< 90% confidence, ADR-0005) → processing_outcomes (founder-ov
eksplicitan zahtev za buduće podešavanje). Menjati samo _process(), nikad
petlju/shutdown/heartbeat/reap logiku oko njega — to bi bilo tačno ono
"malo odstupanje od ADR-a" koje je founder izričito zabranio.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import socket
import tempfile
import time
import uuid
from pathlib import Path

from shared import intake_documents, intake_queue

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
        """Faza 1A: decrypt+OCR → klasifikacija → ekstrakcija → review
        routing → processing_outcomes. Idempotentnost: ako je reap+retry
        pozvao ovo dvaput za isti posao (prethodni pokušaj je pao POSLE
        upisa dokumenta ali PRE mark_job_completed), rani izlaz — ne piše
        drugi intake_documents/extracted_entities red za isti posao."""
        job_id = job["id"]
        t_start = time.monotonic()

        existing = await intake_documents.get_job_result(job_id)
        if existing["document"] is not None:
            logger.info("[INTAKE_WORKER] job=%s već ima dokument (verovatno reap posle delimične obrade) — preskačem ponovnu obradu.", job_id[:8])
            return

        raw_bytes = await self._download_and_decrypt(job["storage_path"])

        suffix = self._guess_suffix(job.get("original_filename"), job.get("mime_type"))
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)
        try:
            text, is_scanned, ocr_used = await asyncio.to_thread(self._extract_text, tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

        if is_scanned:
            # Fail-soft (docs/ENGINEERING_PRINCIPLES.md) — OCR neuspeh NIJE
            # tranzijentna greška koju retry rešava (ista slika, isti
            # rezultat), pa se NE baca exception (što bi pokrenulo retry
            # petlju). Umesto toga: dokument se čuva sa document_type='other'
            # i confidence=0, review queue dobija jasan razlog, posao se
            # ipak završava normalno — advokat vidi "OCR nije uspeo" odmah,
            # ne posle 5 pokušaja i nekoliko minuta eksponencijalnog backoff-a.
            document_id = await intake_documents.create_document(
                job_id, "other", 0.0, "heuristic", ocr_confidence=0.0, ocr_used=True,
            )
            await intake_documents.create_review_queue_entry(job_id, document_id, "ocr_failed", [])
            await intake_documents.write_processing_outcome(
                job_id, "other", 0.0, {}, int((time.monotonic() - t_start) * 1000),
            )
            return

        classification = await self._classify(text)
        entities = await self._extract_entities(text)

        document_id = await intake_documents.create_document(
            job_id,
            classification["document_type"],
            classification["confidence"],
            classification["method"],
            ocr_confidence=(0.6 if ocr_used else None),  # OCR bez eksplicitnog skora danas — konzervativna fiksna vrednost dok extractor ne vraća pravi confidence (poznato ograničenje, ne skriveno)
            ocr_used=ocr_used,
        )
        entity_rows = await intake_documents.insert_entities(document_id, entities)

        low_confidence_fields = [
            e["entity_type"] for e in entities
            if e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD
        ]
        if classification["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD:
            low_confidence_fields = ["document_type"] + low_confidence_fields
        if low_confidence_fields:
            await intake_documents.create_review_queue_entry(job_id, document_id, "low_confidence_extraction", low_confidence_fields)

        entity_confidence_map = {e["entity_type"]: e["confidence"] for e in entities}
        processing_time_ms = int((time.monotonic() - t_start) * 1000)
        await intake_documents.write_processing_outcome(
            job_id, classification["document_type"],
            (0.6 if ocr_used else None), entity_confidence_map, processing_time_ms,
        )
        logger.info(
            "[INTAKE_WORKER] job=%s obrađen: tip=%s (%.2f) low_confidence=%s (%dms)",
            job_id[:8], classification["document_type"], classification["confidence"], low_confidence_fields, processing_time_ms,
        )

    async def _download_and_decrypt(self, storage_path: str) -> bytes:
        """Isti Trezor obrazac kao klijenti/router.py — preuzmi enkriptovan
        blob iz Supabase Storage, dekriptuj AESGCM-om."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from security.crypto import _get_field_key
        from shared.deps import _get_supa

        supa = _get_supa()
        bucket = supa.storage.from_("intake-dokumenti")
        raw_encrypted = await asyncio.to_thread(lambda: bucket.download(storage_path))

        key = _get_field_key()
        blob_raw = base64.urlsafe_b64decode(raw_encrypted + b"==")
        nonce, ct = blob_raw[:12], blob_raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None)

    @staticmethod
    def _guess_suffix(original_filename: str | None, mime_type: str | None) -> str:
        if original_filename:
            suffix = Path(original_filename).suffix.lower()
            if suffix in (".pdf", ".docx", ".txt"):
                return suffix
        if mime_type == "application/pdf":
            return ".pdf"
        if mime_type == "text/plain":
            return ".txt"
        return ".pdf"  # najčešći slučaj u praksi (skenirane presude) — razuman podrazumevani izbor

    @staticmethod
    def _extract_text(path: Path) -> tuple[str, bool, bool]:
        from uploaded_doc.extractor import extract
        return extract(path)

    @staticmethod
    async def _classify(text: str) -> dict:
        from shared.intake_classify import classify
        return await classify(text)

    @staticmethod
    async def _extract_entities(text: str) -> list[dict]:
        from shared.intake_extract import extract_all_entities
        return await extract_all_entities(text)


# ─── Singleton — deli se sa FastAPI startup/shutdown hook-ovima ────────────────

worker = IntakeWorker()


def start_worker() -> None:
    worker.start()


async def stop_worker() -> None:
    await worker.stop()
