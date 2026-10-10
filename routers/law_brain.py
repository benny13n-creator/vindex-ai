# -*- coding: utf-8 -*-
"""
Vindex AI — routers/law_brain.py

NS008 — uska V2 ulazna tačka Law Brain-a. Sva logika je u `services/law_brain.py`; ovde su samo
autentifikacija, validacija i HTTP ugovor.

  GET /api/law-brain/predmeti/{predmet_id}  — kanonski kontekst predmeta: bez modela, bez kredita, bez upisa.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
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
