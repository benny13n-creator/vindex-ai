# -*- coding: utf-8 -*-
"""
Vindex AI — routers/smart_intake.py

Smart Intake Engine — POST /api/smart-intake/documents (upload), GET
.../jobs/{id} (proizvodni Definition of Done: tip + Confidence Graph +
tačna polja za proveru u JEDNOM pozivu), POST .../entities/{id}/correct
(10-sekundna ispravka), GET .../admin/health.

NAPOMENA O NAZIVU PUTANJE: ADR-0001 je originalno specificirao
`/api/intake/documents`. Pri implementaciji je otkriveno da `/api/intake/*`
već u potpunosti pripada POSTOJEĆEM routers/intake.py — CRM Intake Wizard
(ekstrakcija/kreiraj/conflict-check/templates/bulk-import/history, 7 ruta,
već u produkciji). Isti naziv "intake", potpuno različita funkcija (otvaranje
predmeta/klijenta, ne organizacija dokumenata). Da bi se izbegao sudar sa
živim sistemom, ova ruta koristi `/api/smart-intake/*` — formalno zabeleženo
kao amandman na ADR-0001 (vidi belešku na dnu tog fajla), ne tiha izmena.

Ovo je NOVA putanja, NE preprava postojećeg /api/dokument/upload (taj
endpoint je efemerni session-based Q&A upload — sinhron po dizajnu, jer
korisnik odmah postavlja pitanja o dokumentu u istom toku; prebacivanje NA
queue bi mu pokvarilo tačno tu funkciju). Smart Intake je nezavisna nova
putanja od prvog dana — bez feature-flag grananja između dva paralelna
sistema (founder eksplicitno zabranio: "ako uvodiš novu putanju, uvedi je
potpuno").

Upload kontrakt (nepromenjen od Faze 0): perzistuje fajl (enkriptovano,
isti obrazac kao klijenti/router.py Trezor) i vraća 202 + job_id ODMAH —
prava obrada (Faza 1A: OCR → klasifikacija → ekstrakcija, shared/
intake_worker.py) dešava se u pozadini. Ako upload i dalje čeka obradu pre
odgovora, cela poenta queue arhitekture je izgubljena.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import uuid
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Request, UploadFile, File

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter
from shared import intake_documents, intake_queue

logger = logging.getLogger("vindex.smart_intake")
router = APIRouter(prefix="/api/smart-intake", tags=["smart_intake"])

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB, isti limit kao /api/dokument/upload
_STORAGE_BUCKET = "intake-dokumenti"


async def _require_founder(user: dict = Depends(get_current_user)) -> dict:
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Samo za administratore.")
    return user


def _encrypt(raw: bytes) -> bytes:
    """Isti obrazac kao klijenti/router.py Trezor — enkriptovano pre upload-a
    na Supabase Storage, nikad plaintext u bucket-u."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from security.crypto import _get_field_key

    key = _get_field_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(nonce, raw, None)
    return base64.urlsafe_b64encode(nonce + encrypted)


@router.post("/documents", status_code=202)
@limiter.limit("20/minute")
async def intake_documents(
    request: Request,
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """Batch upload — 202 + job_id po fajlu ODMAH, obrada (OCR/klasifikacija/
    ekstrakcija) u pozadini preko IntakeWorker-a (shared/intake_worker.py).
    Nikad sinhrono čeka tu obradu — to je cela poenta Postgres-backed
    queue-a (ADR-0002)."""
    if not files:
        raise HTTPException(status_code=422, detail="Nijedan fajl nije poslat.")

    supa = _get_supa()
    results = []

    for f in files:
        raw = await f.read()
        if len(raw) > _MAX_UPLOAD_BYTES:
            results.append({"filename": f.filename, "ok": False, "greska": "Fajl je prevelik (max 25MB)."})
            continue
        if len(raw) < 1:
            results.append({"filename": f.filename, "ok": False, "greska": "Fajl je prazan."})
            continue

        content_sha256 = hashlib.sha256(raw).hexdigest()
        storage_key = f"{user['user_id']}/{uuid.uuid4().hex}"

        try:
            encrypted = await asyncio.to_thread(_encrypt, raw)
            bucket = supa.storage.from_(_STORAGE_BUCKET)
            await asyncio.to_thread(
                lambda: bucket.upload(
                    path=storage_key,
                    file=encrypted,
                    file_options={"content-type": "application/octet-stream", "upsert": "false"},
                )
            )
        except Exception as exc:
            logger.error("[SMART_INTAKE] storage upload greška za %s: %s", f.filename, exc)
            results.append({"filename": f.filename, "ok": False, "greska": "Greška pri čuvanju fajla."})
            continue

        try:
            job_id = await intake_queue.enqueue_job(
                source="dropzone",
                content_sha256=content_sha256,
                storage_path=storage_key,
                uploaded_by=user["user_id"],
                kancelarija_id=None,  # Faza 1: office-scoped review queue (dizajn review §26.9) — nije reseno ovde
                idempotency_key=f"{user['user_id']}:{content_sha256}",
            )
        except Exception as exc:
            logger.error("[SMART_INTAKE] enqueue greška za %s: %s", f.filename, exc)
            results.append({"filename": f.filename, "ok": False, "greska": "Greška pri prijemu dokumenta."})
            continue

        # Best-effort follow-up upis (original_filename/mime_type) — NIJE deo
        # atomske enqueue_intake_job RPC transakcije (ADR-0001), namerno: to
        # bi značilo menjanje potpisa RPC-a koji je već pokrenut u produkciji
        # (migracija 073). Ova dva polja su pomoćna metapodatka za Fazu 1A
        # (extract() treba ekstenziju fajla), ne kritičan put za queue
        # pouzdanost — ako ovaj upis padne, posao i dalje postoji i biće
        # obrađen (extractor pada na .pdf kao razuman podrazumevani izbor).
        try:
            await asyncio.to_thread(
                lambda: supa.table("intake_jobs")
                    .update({"original_filename": f.filename, "mime_type": f.content_type})
                    .eq("id", job_id)
                    .execute()
            )
        except Exception as exc:
            logger.warning("[SMART_INTAKE] filename/mime upis neuspešan (non-fatal) za job=%s: %s", job_id[:8], exc)

        results.append({"filename": f.filename, "ok": True, "job_id": job_id})

    logger.info("[SMART_INTAKE] batch upload: %d fajlova, %d uspešno prijavljeno", len(files), sum(1 for r in results if r["ok"]))
    return {"rezultati": results, "ukupno": len(files)}


@router.get("/jobs/{job_id}")
@limiter.limit("60/minute")
async def intake_job_status(job_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Proizvodni Definition of Done (Faza 1A) — advokat u JEDNOM pozivu
    vidi: status posla, tip dokumenta, SVAKI izvučen podatak sa sopstvenom
    pouzdanošću (Confidence Graph), i — ako postoji nesigurnost — TAČNO
    koja polja treba da pogleda, ne ceo dokument. RLS (migracija 073) već
    ograničava na sopstvene poslove za ne-service_role upite; eksplicitna
    provera ovde daje jasnu 404 poruku umesto praznog reda."""
    res = await asyncio.to_thread(
        lambda: _get_supa().table("intake_jobs")
            .select("id, status, source, attempts, last_error, created_at, completed_at, original_filename")
            .eq("id", job_id)
            .eq("uploaded_by", user["user_id"])
            .maybe_single()
            .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Posao nije pronađen.")
    job = res.data

    result = await intake_documents.get_job_result(job_id)
    document = result["document"]
    entities = result["entities"]
    review = result["review"]

    entiteti_view = [{
        "entity_type": e["entity_type"],
        "value": e.get("corrected_value") or e["value"],
        "confidence": e["confidence"],
        "needs_review": (not e["reviewed"]) and e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD,
        "corrected": e["reviewed"],
    } for e in entities]

    return {
        "job": job,
        "dokument": {
            "tip": document["document_type"] if document else None,
            "tip_pouzdanost": document["classification_confidence"] if document else None,
            "ocr_koriscen": document["ocr_used"] if document else None,
        } if document else None,
        "entiteti": entiteti_view,
        "potrebna_provera": {
            "razlog": review["reason"],
            "polja": review["low_confidence_fields"],
        } if review else None,
    }


@router.post("/entities/{entity_id}/correct")
@limiter.limit("60/minute")
async def correct_entity(
    entity_id: str,
    request: Request,
    corrected_value: str = Body(..., embed=True),
    user: dict = Depends(get_current_user),
):
    """Proizvodni Definition of Done: "ispravka za deset sekundi." Original
    vrednost se NIKAD ne briše (corrected_value je dodatak, ne prepisivanje)
    — i piše se u intake_processing_outcomes sa user_corrected=true, jer je
    ovo tačno podatak koji founder eksplicitno traži za buduće podešavanje
    pragova/heuristika."""
    try:
        result = await intake_documents.correct_entity(entity_id, corrected_value, user.get("email", user["user_id"]))
    except ValueError:
        raise HTTPException(status_code=404, detail="Stavka nije pronađena.")
    return result


@router.get("/admin/health")
@limiter.limit("30/minute")
async def intake_health(request: Request, user: dict = Depends(_require_founder)):
    """Operativna vidljivost (Faza 0 Definition of Done) — queue depth,
    najstariji pending, failed/retrying, outbox backlog, worker heartbeat-ovi.
    Sve IZVEDENO u letu (SQL view-ovi), nikad zaseban stored red."""
    queue_metrics, outbox_metrics, heartbeats = await asyncio.gather(
        intake_queue.get_queue_metrics(),
        intake_queue.get_outbox_metrics(),
        intake_queue.get_worker_heartbeats(),
    )
    return {
        "queue": queue_metrics,
        "outbox": outbox_metrics,
        "workeri": heartbeats,
    }


@router.get("/admin/accuracy")
@limiter.limit("30/minute")
async def intake_accuracy(request: Request, user: dict = Depends(_require_founder)):
    """Validation Sprint (founder, 2026-07-15) — Office Accuracy Dashboard.
    Ovo su OPERATIVNI KPI-jevi iz stvarne upotrebe (OCR uspešnost, review
    polja po dokumentu, stopa ispravki, LLM fallback %, vreme obrade) —
    NIJE isto što i tačnost naspram ground truth-a, za to postoji
    scripts/intake_accuracy_benchmark.py protiv golden_dataset/. Iskreno
    prazno stanje ispod praga uzorka, nikad izmišljen broj koji izgleda
    precizan a nije (isti princip kao Revenue Intelligence)."""
    from shared.intake_accuracy import get_office_accuracy_kpis
    return await get_office_accuracy_kpis()
