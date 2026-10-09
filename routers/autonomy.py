# -*- coding: utf-8 -*-
"""
Vindex AI — routers/autonomy.py

NS007 — uska ulazna tačka autonomnog rada.

  POST /api/cron/autonomy   — SAMO mašina-mašini. Zaglavlje `X-Autonomy-Secret` mora biti jednako
                              `AUTONOMY_CRON_SECRET` (poređenje u konstantnom vremenu). Tajna nije podešena ILI je
                              pogrešna → ISTI 401 (ne otkriva se da li je raspoređivač konfigurisan).
                              Telo se ne čita: nema `user_id`, `predmet_id` ni prozora od pozivaoca.

TOK: autentifikacija → atomsko zauzimanje prozora (`autonomy_cycles`, INSERT) → kanonski radnik
(`workers.background_agents.run_autonomy_cycle`) → završetak ciklusa → sažetak. Nema poslovne logike ovde.

Prozor = UTC sat (`auto:YYYY-MM-DDTHH`): najviše jedan ciklus po satu bez obzira na broj okidanja. Dnevni cron
(`/api/cron/daily`) NE poziva ovu rutu i ona ne zavisi od njegovog heartbeat-a.
"""
from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from shared.deps import _get_supa
from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.autonomy")
router = APIRouter(tags=["autonomy"])

ZAGLAVLJE_TAJNE = "X-Autonomy-Secret"


def _sada() -> datetime:
    return datetime.now(timezone.utc)


def prozor(t: datetime) -> str:
    return "auto:" + t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def _ovlascen(request: Request) -> bool:
    tajna = os.getenv("AUTONOMY_CRON_SECRET", "")
    dato = request.headers.get(ZAGLAVLJE_TAJNE, "")
    if not tajna or len(tajna) < 32:
        # nepodešena ili preslaba tajna = zatvoreno; isti odgovor kao pogrešna tajna
        hmac.compare_digest(dato.encode(), b"x" * 32)
        return False
    return hmac.compare_digest(dato.encode(), tajna.encode())


@router.post("/api/cron/autonomy")
async def cron_autonomy(request: Request):
    if not _ovlascen(request):
        raise HTTPException(status_code=401, detail="Neovlašćen pristup.")
    from services import autonomy as au
    from workers.background_agents import run_autonomy_cycle

    run_id = uuid.uuid4().hex[:12]
    kljuc = prozor(_sada())
    supa = _get_supa()
    try:
        z = await au.zauzmi_ciklus(supa, kljuc, run_id)
    except Exception as e:
        _sentry_capture(e)
        logger.error("[AUTONOMY] zauzimanje prozora %s nije uspelo: %s", kljuc, type(e).__name__)
        return JSONResponse({"ok": False, "status": "CLAIM_UNAVAILABLE", "prozor": kljuc}, status_code=503)
    if z["ishod"] == "ALREADY_CLAIMED":
        logger.info("[AUTONOMY] prozor %s je već zauzet — preskačem", kljuc)
        return {"ok": True, "status": "SKIPPED", "razlog": "ALREADY_CLAIMED", "prozor": kljuc}

    try:
        sazetak = await run_autonomy_cycle(run_id)
    except Exception as e:
        _sentry_capture(e)
        logger.error("[AUTONOMY] ciklus %s run=%s pao: %s", kljuc, run_id, type(e).__name__)
        try:
            await au.zavrsi_ciklus(supa, kljuc, run_id, False, {}, "CYCLE_EXCEPTION")
        except Exception as e2:
            _sentry_capture(e2)
        return JSONResponse({"ok": False, "status": "FAILED", "prozor": kljuc, "run_id": run_id}, status_code=500)

    zavrsen = False
    try:
        zavrsen = await au.zavrsi_ciklus(supa, kljuc, run_id, True, sazetak)
    except Exception as e:
        _sentry_capture(e)
    # Ako upis završetka ne uspe, rad je već trajno upisan po stavkama; ciklus ostaje vidljivo RUNNING (nije ukraden).
    return {"ok": True, "status": "COMPLETED" if zavrsen else "COMPLETED_UNRECORDED", "prozor": kljuc,
            "run_id": run_id, "sazetak": sazetak}
