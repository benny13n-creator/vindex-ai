# -*- coding: utf-8 -*-
"""
Vindex AI — routers/law_brain.py

NS008 — uska V2 ulazna tačka Law Brain-a. Sva logika je u `services/law_brain.py`; ovde su samo
autentifikacija, validacija i HTTP ugovor.

  GET  /api/law-brain/znanje                         — pregled znanja kancelarije (Znanje): bez modela, bez kredita.
  GET  /api/law-brain/predmeti/{predmet_id}          — kanonski kontekst predmeta: bez modela, bez kredita, bez upisa.
  GET  /api/law-brain/pretraga?q=…[&predmet_id=…]    — IZRIČITA pretraga overenog znanja kancelarije (postojeći
       Pinecone namespace vlasnika + ACL): 1 embedding upita, 0 kompletacija, bez kredita; samo na zahtev korisnika.
  POST /api/law-brain/rad/{work_id}/predlozi-znanje  — izričit predlog PRIHVAĆENOG autonomnog rada kao znanja
       kancelarije: SAMO red u `staging_memory` (na advokatsku overu), nikad direktno Pinecone (Task 15).
  POST /api/law-brain/predmeti/{predmet_id}/sinteza  — JEDINI poziv modela; samo na izričit klik. Pravo i cena:
       postojeći feature `precedenti` („Law Firm Brain", migracija 064) — bez novog reda u registru. Trajna
       idempotentnost (NS005, `ZASTICENE_RUTE`): dva fizička POST-a sa istim ključem = jedno izvršenje modela,
       jedna naplata, isti odgovor.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.law_brain")
router = APIRouter(tags=["law-brain"])

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_NEMA = "Predmet nije pronađen."


def _danas() -> date:
    return date.today()


@router.get("/api/law-brain/predmeti/{predmet_id}")
@limiter.limit("60/minute")
async def kontekst_predmeta(predmet_id: str, request: Request, user: dict = Depends(get_current_user)):
    if not _UUID.match(predmet_id or ""):
        raise HTTPException(status_code=404, detail=_NEMA)
    from services import law_brain as lb
    uid = user["user_id"]
    try:
        k = await asyncio.to_thread(lb.kontekst_predmeta, _get_supa(), uid, predmet_id, today=_danas())
    except Exception as e:
        _sentry_capture(e)
        logger.error("[LAW_BRAIN] kontekst nije pročitan uid=%.8s: %s", uid, type(e).__name__)
        raise HTTPException(status_code=503, detail="Iskustvo kancelarije trenutno nije dostupno.")
    if k is None:
        raise HTTPException(status_code=404, detail=_NEMA)
    return k


@router.get("/api/law-brain/znanje")
@limiter.limit("60/minute")
async def pregled_znanja(request: Request, user: dict = Depends(get_current_user)):
    """Znanje → Iskustvo kancelarije: bez modela, bez kredita, bez upisa."""
    from services import law_brain as lb
    uid = user["user_id"]
    try:
        return await asyncio.to_thread(lb.pregled_znanja, _get_supa(), uid, today=_danas())
    except Exception as e:
        _sentry_capture(e)
        logger.error("[LAW_BRAIN] pregled znanja nije pročitan uid=%.8s: %s", uid, type(e).__name__)
        raise HTTPException(status_code=503, detail="Iskustvo kancelarije trenutno nije dostupno.")


@router.post("/api/law-brain/predmeti/{predmet_id}/sinteza")
@limiter.limit("10/minute")
async def sinteza(predmet_id: str, request: Request, user: dict = Depends(PermissionService.require("precedenti"))):
    if not _UUID.match(predmet_id or ""):
        raise HTTPException(status_code=404, detail=_NEMA)
    from services import law_brain_sinteza as lb
    uid = user["user_id"]
    try:
        r = await lb.sinteza(_get_supa(), uid, predmet_id, today=_danas(), email=user.get("email", ""))
    except lb.ModelNedostupan as e:
        logger.warning("[LAW_BRAIN] sinteza: model nedostupan uid=%.8s: %s", uid, e)
        raise HTTPException(status_code=503, detail="Analiza iskustva trenutno nije dostupna. Kredit nije potrošen.")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[LAW_BRAIN] sinteza nije izvršena uid=%.8s: %s", uid, type(e).__name__)
        raise HTTPException(status_code=503, detail="Analiza iskustva trenutno nije dostupna. Kredit nije potrošen.")
    if r is None:
        raise HTTPException(status_code=404, detail=_NEMA)
    r.pop("model_pozvan", None)          # kredit je naplaćen u servisu, uz sam poziv modela
    return r


@router.post("/api/law-brain/rad/{work_id}/predlozi-znanje")
@limiter.limit("20/minute")
async def predlozi_znanje(work_id: str, request: Request, user: dict = Depends(get_current_user)):
    if not _UUID.match(work_id or ""):
        raise HTTPException(status_code=404, detail="Radni proizvod nije pronađen.")
    from services import law_brain_promocija as lp
    uid = user["user_id"]
    try:
        r = await lp.predlozi_kao_znanje(_get_supa(), uid, work_id)
    except lp.NijePrihvacen as e:
        raise HTTPException(status_code=409, detail="Kao znanje kancelarije može se predložiti samo prihvaćen rad sa sadržajem.")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[LAW_BRAIN] predlog znanja nije upisan uid=%.8s: %s", uid, type(e).__name__)
        raise HTTPException(status_code=503, detail="Predlog nije sačuvan.")
    if r is None:
        raise HTTPException(status_code=404, detail="Radni proizvod nije pronađen.")
    return {**r, "poruka": "Rad čeka advokatsku overu. Znanje kancelarije postaje tek posle odobrenja."}


@router.get("/api/law-brain/pretraga")
@limiter.limit("20/minute")
async def pretraga_znanja(request: Request, q: str = "", predmet_id: str = "", user: dict = Depends(get_current_user)):
    if predmet_id and not _UUID.match(predmet_id):
        raise HTTPException(status_code=404, detail=_NEMA)
    from services import law_brain as lb
    uid = user["user_id"]
    try:
        r = await asyncio.to_thread(lb.pretrazi_znanje_kancelarije, _get_supa(), uid, q, today=_danas(),
                                    predmet_id=predmet_id or None)
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[LAW_BRAIN] pretraga znanja nije izvršena uid=%.8s: %s", uid, type(e).__name__)
        return {"stanje": lb.DEGRADED, "stavke": [], "napomena": lb.KNOWLEDGE_NOTICE}
    if r["stanje"] == lb.NOT_AUTHORIZED:
        raise HTTPException(status_code=404, detail=_NEMA)
    return {**r, "stavke": [it.to_dict() for it in r["stavke"]]}
