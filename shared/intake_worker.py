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

from shared import intake_documents, intake_queue, intake_segments
from shared.intake_segment import PageText, segment_document, uncertain_boundaries

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
            needs_review = await self._process(job)
            # Program Intake Sprint 004 (2026-08-05) -- ranije se OVDE
            # bezuslovno zvao mark_job_completed(), bez obzira da li je
            # _process() upravo napravio intake_review_queue red. Rezultat:
            # intake_jobs.status='completed' I intake_review_queue.
            # resolved_at=NULL istovremeno tvrde suprotne stvari o istom
            # poslu -- dva izvora istine koji se ne slazu (Sprint 004 Fork
            # A §6, potvrdjeno). Sada: nizak-confidence/OCR-neuspeh posao
            # ide na 'awaiting_review' (vec deklarisan u CHECK constraint-u
            # od migracije 073, ranije nikad pisan -- isti "dormant status"
            # nalaz kao Sprint 002 Fork B), sto finalize_intake_job-ov VEC
            # POSTOJECI status gate ('Posao jos nije obradjen') prirodno
            # iskoristi da blokira finalizaciju dok covek ne potvrdi --
            # bez ijedne nove linije koda u finalize-u samom.
            if needs_review:
                await intake_queue.mark_job_awaiting_review(job_id)
            else:
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

    async def _process(self, job: dict) -> bool:
        """Faza 1A: decrypt+OCR → klasifikacija → ekstrakcija → review
        routing → processing_outcomes. Idempotentnost: ako je reap+retry
        pozvao ovo dvaput za isti posao (prethodni pokušaj je pao POSLE
        upisa dokumenta ali PRE mark_job_completed), rani izlaz — ne piše
        drugi intake_documents/extracted_entities red za isti posao.

        Vraća True ako je posao poslat u Review Required (nizak confidence
        ili OCR neuspeh), False ako je pouzdano klasifikovan. Program
        Intake Sprint 004 (2026-08-05) -- ovaj povratni signal je _tick()-u
        potreban da bira izmedju mark_job_completed() i
        mark_job_awaiting_review() -- ranije je SVAKI uspesno obradjen
        posao (cak i nizak-confidence) zavrsavao na status='completed',
        dok je SEPARATAN intake_review_queue red istovremeno tvrdio da
        posao jos ceka covekovu potvrdu -- dva izvora istine koja se ne
        slazu, tacno "trece skriveno stanje" koje ovaj sprint zabranjuje."""
        job_id = job["id"]
        t_start = time.monotonic()

        # Program Intake Sprint 005 (2026-08-05) -- checked FIRST, and via a
        # plain list query (never .maybe_single()): a segmented job can have
        # 2+ intake_documents rows sharing this job_id, and
        # intake_documents.get_job_result()'s own .maybe_single() call would
        # raise on 2+ rows (postgrest's own ambiguity guard) if it ran first
        # on a resumed segmented job. If this job already has segment rows,
        # the OLD single-document idempotency check below never runs at all
        # -- resuming a segmented job is _process_segments()'s own job (it
        # reconciles against each segment's already-persisted status),
        # exactly the way delete_partial_document()/has_processing_outcome()
        # below reconcile a single-document job's own partial state.
        existing_segment_rows = await intake_segments.get_segments_for_job(job_id)

        if not existing_segment_rows:
            existing = await intake_documents.get_job_result(job_id)
            if existing["document"] is not None:
                if await intake_documents.has_processing_outcome(job_id):
                    logger.info("[INTAKE_WORKER] job=%s već potpuno obrađen (idempotentan retry) — preskačem.", job_id[:8])
                    # Program Intake Sprint 004: redak edge-case put (claim_next_job
                    # trazi status='received', pa se ovo obicno ne dostize dok je
                    # posao vec 'awaiting_review' -- ali ako je reaper vratio
                    # posao na 'received' pre nego sto je prethodni status upis
                    # stigao da se izvrsi, moramo ponovo proveriti da li
                    # nerazresen review i dalje postoji, ne slepo vratiti False.
                    return existing["review"] is not None
                # Program Intake Sprint 001 (2026-08-04) -- dokument POSTOJI ali
                # processing_outcome NE POSTOJI: prethodni pokušaj je pao negde
                # IZMEĐU create_document() i write_processing_outcome() (ta
                # linija je UVEK poslednja stvar koju _process() radi, u obe
                # grane ispod). Stari kod je ovo tretirao kao "već gotovo" i
                # tiho vraćao (bez exception-a) -- _tick() bi onda pozvao
                # mark_job_completed() na poslu bez ijednog entiteta, bez
                # review queue unosa, neraspoznatljivo od stvarnog uspeha,
                # bez loga, bez dead-letter traga. Tačno "upload prijavljuje
                # uspeh iako obrada nije bezbedno završena" -- Sprint 001
                # eksplicitno zabranjeno stanje za zatvaranje misije. Ispravka:
                # obriši nepotpuno stanje i obradi ponovo od nule -- tekst
                # dokumenta se ionako nigde ne perzistira između koraka, pa
                # "nastavak odakle je stao" bi ionako morao da ponovi OCR;
                # čisto ponavljanje je jednostavnije i podjednako jeftino.
                logger.warning(
                    "[INTAKE_WORKER] job=%s ima NEPOTPUN dokument (prethodni pokušaj pao usred obrade, processing_outcome nedostaje) — brišem i obrađujem ponovo od nule.",
                    job_id[:8],
                )
                await intake_documents.delete_partial_document(existing["document"]["id"], job_id)

        raw_bytes = await self._download_and_decrypt(job["storage_path"])

        suffix = self._guess_suffix(job.get("original_filename"), job.get("mime_type"))
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)
        try:
            text, is_scanned, ocr_used, pages = await asyncio.to_thread(self._extract_text, tmp_path)
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
            # Program Intake Sprint 002: raise_on_error=True -- ovo je
            # POSLEDNJI upis u obe grane ove funkcije, i has_processing_outcome()
            # ga koristi kao jedini pouzdan signal da je _process() stvarno
            # zavrsio (v. napomena na idempotentnost-proveri iznad). Ako OVAJ
            # upis padne (tranzijentna DB greska, ne sam OCR neuspeh koji je
            # vec fail-soft obradjen iznad), mora ici kroz isti retry put kao
            # svaka druga greska u ovoj funkciji, ne biti tiho progutan.
            await intake_documents.write_processing_outcome(
                job_id, "other", 0.0, {}, int((time.monotonic() - t_start) * 1000),
                raise_on_error=True,
            )
            return True

        # Program Intake Sprint 005 (2026-08-05) -- Canonical Document
        # Segmentation runs here, BEFORE classification, for every job that
        # has a real per-page breakdown (pages is None for DOCX/TXT/image —
        # a structural absence, see uploaded_doc/extractor.py). Governing
        # principle (Fork C, adopted): a job that segments into exactly 1
        # (implicit) segment must be byte-for-byte behaviorally identical
        # to pre-Sprint-005 processing -- so segmentation always RUNS, but
        # the intake_job_segments table (migration 093) is only ever
        # written to when it actually found 2+ documents. The single-
        # document branch below is the EXACT code this function ran before
        # this sprint, untouched.
        page_objs: list[PageText] = []
        segments = []
        uncertain_signals = []
        if pages and len(pages) > 1:
            page_objs = [PageText(page_number=i + 1, text=p, ocr_used=ocr_used) for i, p in enumerate(pages)]
            segments = segment_document(page_objs)
            uncertain_signals = uncertain_boundaries(page_objs)

        if existing_segment_rows:
            # Resuming a job that already segmented on a prior (crashed)
            # attempt. Segmentation is a pure, deterministic function of the
            # same bytes, so re-running it here reproduces the identical
            # segments in the identical order -- we reconcile against the
            # ALREADY-PERSISTED rows (by position) rather than inserting new
            # ones, so already-completed segments are never reprocessed.
            return await self._process_segments(job_id, t_start, pages, ocr_used, segments, uncertain_signals, segment_rows=existing_segment_rows)

        if len(segments) <= 1:
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
                # Program Intake Sprint 004 -- 'classification_uncertain' je bio
                # deklarisan u CHECK constraint-u (migracija 074) ali NIKAD
                # stvarno upisivan -- svaka nesigurnost je padala pod generican
                # 'low_confidence_extraction', bez razlike izmedju "par polja
                # nejasno" i "sam TIP dokumenta nejasan" (ozbiljnije -- pogresan
                # tip moze pokrenuti pogresan dalji tok). Sada: ako je
                # document_type medju niskim poljima, razlog je precizniji.
                reason = "classification_uncertain" if "document_type" in low_confidence_fields else "low_confidence_extraction"
                await intake_documents.create_review_queue_entry(job_id, document_id, reason, low_confidence_fields)
            if uncertain_signals:
                # Program Intake Sprint 005 -- real evidence of a possible
                # extra document was found (e.g. one lone strong signal, or
                # 2+ corroborating with no strong signal) but it did not
                # clear the auto-split bar. Mission mandate: never guess in
                # either direction on thin evidence -- the document stays
                # whole AND a human is asked to confirm that was right,
                # rather than the engine silently doing nothing.
                await intake_documents.create_review_queue_entry(
                    job_id, document_id, "segmentation_uncertain",
                    [f"strana {s.page_number}: {s.detail}" for s in uncertain_signals],
                )

            entity_confidence_map = {e["entity_type"]: e["confidence"] for e in entities}
            processing_time_ms = int((time.monotonic() - t_start) * 1000)
            # Program Intake Sprint 002: raise_on_error=True, same reasoning as
            # the OCR-failed branch above -- this is the true completion signal
            # has_processing_outcome() checks; a failure here must retry, not
            # silently leave the job marked completed with no outcome row.
            await intake_documents.write_processing_outcome(
                job_id, classification["document_type"],
                (0.6 if ocr_used else None), entity_confidence_map, processing_time_ms,
                raise_on_error=True,
            )
            logger.info(
                "[INTAKE_WORKER] job=%s obrađen: tip=%s (%.2f) low_confidence=%s (%dms)",
                job_id[:8], classification["document_type"], classification["confidence"], low_confidence_fields, processing_time_ms,
            )
            return bool(low_confidence_fields) or bool(uncertain_signals)

        return await self._process_segments(job_id, t_start, pages, ocr_used, segments, uncertain_signals)

    async def _process_segments(
        self, job_id: str, t_start: float, pages: list[str], ocr_used: bool,
        segments: list, uncertain_signals: list, segment_rows: list[dict] | None = None,
    ) -> bool:
        """Program Intake Sprint 005 -- canonical multi-document hand-off
        (Phase 5 + Phase 6). Every segment enters the SAME classification/
        extraction pipeline used above (Phase 5: no second classifier), each
        wrapped in its OWN try/except so one segment's failure cannot abort
        or lose its siblings (Phase 6: partial failure recovery, Fork C's
        load-bearing fix -- the old code had ONE try/except around this
        entire stretch; here each segment gets its own). A segment that
        fails gets one immediate in-process retry (shared/intake_segments.py
        ::DEFAULT_MAX_ATTEMPTS) before being dead-lettered -- a full cross-
        run backoff/claim system is out of this sprint's bounded scope.

        segment_rows: pre-existing rows when RESUMING a job that already
        segmented on a prior attempt (caller: _process()'s idempotency
        check) -- already-completed/awaiting_review/failed segments are
        skipped, never reprocessed or duplicated. None (fresh job): rows
        are created here, all starting 'pending'."""
        resuming = segment_rows is not None
        if segment_rows is None:
            segment_rows = await intake_segments.create_segments(job_id, segments)

        uncertain_by_segment_idx: dict[int, list] = {}
        for sig in uncertain_signals:
            for idx, seg in enumerate(segments):
                if seg.start_page <= sig.page_number <= seg.end_page:
                    uncertain_by_segment_idx.setdefault(idx, []).append(sig)
                    break

        job_needs_review = False
        for idx, (seg, row) in enumerate(zip(segments, segment_rows)):
            if resuming and row["status"] in ("completed", "awaiting_review", "failed"):
                # Already resolved by a prior attempt (or permanently
                # dead-lettered) -- never reprocessed. A dead-lettered or
                # awaiting_review segment still means the JOB as a whole
                # needs a human look, even though nothing more happens here.
                if row["status"] in ("awaiting_review", "failed"):
                    job_needs_review = True
                logger.info(
                    "[INTAKE_WORKER] job=%s segment=%d/%d već razrešen (status=%s) — preskačem (resume).",
                    job_id[:8], idx + 1, len(segments), row["status"],
                )
                continue

            segment_id = row["id"]
            segment_text = "\n\n".join(pages[seg.start_page - 1:seg.end_page])
            await intake_segments.mark_segment_processing(segment_id)

            attempts = row.get("attempts", 0)
            max_attempts = row.get("max_attempts", intake_segments.DEFAULT_MAX_ATTEMPTS)
            while True:
                document_id = None
                try:
                    classification = await self._classify(segment_text)
                    entities = await self._extract_entities(segment_text)

                    document_id = await intake_documents.create_document(
                        job_id, classification["document_type"], classification["confidence"],
                        classification["method"], ocr_confidence=(0.6 if ocr_used else None), ocr_used=ocr_used,
                    )
                    await intake_documents.insert_entities(document_id, entities)

                    low_confidence_fields = [
                        e["entity_type"] for e in entities
                        if e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD
                    ]
                    if classification["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD:
                        low_confidence_fields = ["document_type"] + low_confidence_fields
                    needs_review_this_segment = bool(low_confidence_fields)
                    if low_confidence_fields:
                        reason = "classification_uncertain" if "document_type" in low_confidence_fields else "low_confidence_extraction"
                        await intake_documents.create_review_queue_entry(job_id, document_id, reason, low_confidence_fields)
                    if idx in uncertain_by_segment_idx:
                        await intake_documents.create_review_queue_entry(
                            job_id, document_id, "segmentation_uncertain",
                            [f"strana {s.page_number}: {s.detail}" for s in uncertain_by_segment_idx[idx]],
                        )
                        needs_review_this_segment = True

                    entity_confidence_map = {e["entity_type"]: e["confidence"] for e in entities}
                    await intake_documents.write_processing_outcome(
                        job_id, classification["document_type"], (0.6 if ocr_used else None),
                        entity_confidence_map, int((time.monotonic() - t_start) * 1000),
                        raise_on_error=True, segment_id=segment_id,
                    )

                    if needs_review_this_segment:
                        await intake_segments.mark_segment_awaiting_review(segment_id, document_id)
                        job_needs_review = True
                    else:
                        await intake_segments.mark_segment_completed(segment_id, document_id)
                    logger.info(
                        "[INTAKE_WORKER] job=%s segment=%d/%d obrađen: tip=%s (%dp-%dp) low_confidence=%s",
                        job_id[:8], idx + 1, len(segments), classification["document_type"], seg.start_page, seg.end_page, low_confidence_fields,
                    )
                    break
                except Exception as exc:
                    if document_id is not None:
                        # Program Intake Sprint 005 -- same orphan-document
                        # shape Sprint 001 already fixed for the single-
                        # document path (delete_partial_document): if
                        # create_document()/insert_entities() succeeded but
                        # a LATER step in this same attempt (review queue
                        # write, write_processing_outcome) threw, an
                        # immediate in-process retry must not leave that
                        # partial document behind AND create a second one.
                        try:
                            await intake_documents.delete_partial_document(document_id, job_id)
                        except Exception:
                            logger.warning("[INTAKE_WORKER] job=%s segment=%d/%d: čišćenje delimičnog dokumenta neuspešno (nastavljam retry svejedno).", job_id[:8], idx + 1, len(segments))
                    dead_lettered = await intake_segments.mark_segment_failed(segment_id, str(exc), attempts, max_attempts)
                    attempts += 1
                    if dead_lettered:
                        job_needs_review = True
                        logger.error(
                            "[INTAKE_WORKER] job=%s segment=%d/%d trajno neuspešan (strane %d-%d): %s -- ostali segmenti nastavljaju obradu.",
                            job_id[:8], idx + 1, len(segments), seg.start_page, seg.end_page, exc,
                        )
                        break
                    # else: immediate in-process retry, same segment, next loop iteration

        return job_needs_review

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
        # Mission 001 / Night Shift M-001 (2026-08-02): image suffixes added
        # here too, not just in uploaded_doc/extractor.py -- extract() dispatches
        # on this guessed suffix, so a .jpg/.png job that fell through to the
        # ".pdf" default below would have pypdf try to parse a JPEG as a PDF
        # and fail every retry attempt identically (not a transient failure).
        if original_filename:
            suffix = Path(original_filename).suffix.lower()
            if suffix in (".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png"):
                return suffix
        if mime_type == "application/pdf":
            return ".pdf"
        if mime_type == "text/plain":
            return ".txt"
        if mime_type in ("image/jpeg", "image/jpg"):
            return ".jpg"
        if mime_type == "image/png":
            return ".png"
        return ".pdf"  # najčešći slučaj u praksi (skenirane presude) — razuman podrazumevani izbor

    @staticmethod
    def _extract_text(path: Path) -> tuple[str, bool, bool, list[str] | None]:
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
