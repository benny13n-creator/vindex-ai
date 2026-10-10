# -*- coding: utf-8 -*-
"""
Vindex AI — routers/law_brain.py

NS008 — uska V2 ulazna tačka Law Brain-a. Sva logika je u `services/law_brain.py`; ovde su samo
autentifikacija, validacija i HTTP ugovor.

  GET  /api/law-brain/predmeti/{predmet_id}          — kanonski kontekst predmeta: bez modela, bez kredita, bez upisa.
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


@router.post("/api/law-brain/predmeti/{predmet_id}/sinteza")
@limiter.limit("10/minute")
async def sinteza(predmet_id: str, request: Request, user: dict = Depends(PermissionService.require("precedenti"))):
    if not _UUID.match(predmet_id or ""):
        raise HTTPException(status_code=404, detail=_NEMA)
    from services import law_brain_sinteza as lb
    from shared.usage import UsageService
    uid = user["user_id"]
    try:
        r = await lb.sinteza(_get_supa(), uid, predmet_id, today=_danas())
    except lb.ModelNedostupan as e:
        logger.warning("[LAW_BRAIN] sinteza: model nedostupan uid=%.8s: %s", uid, e)
        raise HTTPException(status_code=503, detail="Analiza iskustva trenutno nije dostupna. Kredit nije potrošen.")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[LAW_BRAIN] sinteza nije izvršena uid=%.8s: %s", uid, type(e).__name__)
        raise HTTPException(status_code=503, detail="Analiza iskustva trenutno nije dostupna. Kredit nije potrošen.")
    if r is None:
        raise HTTPException(status_code=404, detail=_NEMA)
    if r.pop("model_pozvan"):
        await UsageService.consume(uid, user.get("email", ""), "precedenti", predmet_id=predmet_id)
    return r
