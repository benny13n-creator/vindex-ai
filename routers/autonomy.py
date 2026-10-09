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


# ══════════════════════════════════════════════════════════════════════════════
# Pregled radnih proizvoda (NS007 Task 12) — SAMO vlasnik, SAMO odluka o pregledu.
# ══════════════════════════════════════════════════════════════════════════════
#   GET  /api/autonomy/work-items                 ?status=&matter_id=&work_type=&limit=
#   GET  /api/autonomy/work-items/{id}
#   POST /api/autonomy/work-items/{id}/accept
#   POST /api/autonomy/work-items/{id}/reject     telo (opciono): {"razlog": "..."}
# Tuđ, nepostojeći i neispravan id → ISTI 404 (bez orakla postojanja). PRIHVATI/ODBACI menja SAMO stanje pregleda:
# ne šalje, ne podnosi, ne piše mejl, ne promoviše u memoriju znanja, ne izvršava i ne zatvara Case Action.
# Mutacije su pod NS005 trajnom idempotentnošću (shared/idempotency.py); prelaz je i u bazi uslovljen stanjem
# READY_FOR_REVIEW, pa i bez ključa dva fizička zahteva daju jedan prelaz (drugi → 409).

import re as _re  # noqa: E402
from typing import Optional as _Opt  # noqa: E402

from fastapi import Depends  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from shared.deps import get_current_user  # noqa: E402
from shared.rate import limiter  # noqa: E402

_UUID = _re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_STATUSI = {"QUEUED", "RUNNING", "READY_FOR_REVIEW", "ACCEPTED", "REJECTED", "FAILED", "DEAD_LETTER", "SUPERSEDED"}
_TIPOVI = {"HEARING_PREP", "PRECEDENT_IMPACT", "CASE_CHANGE_BRIEF"}
_LISTA_KOLONE = ("id,predmet_id,work_type,status,title,summary,reason,trigger_type,quality_state,source_version,"
                 "case_action_id,queued_at,ready_at,resolved_at,updated_at")
_DETALJ_KOLONE = _LISTA_KOLONE + ",trigger_ref,content_json,source_refs,review_note,safe_error_code"
_NIJE_PRONADJEN = "Radni proizvod nije pronađen."


class OdbijanjeTelo(BaseModel):
    razlog: _Opt[str] = Field(default=None, max_length=1000)


def _nije_pronadjen():
    return HTTPException(status_code=404, detail=_NIJE_PRONADJEN)


async def _nazivi(supa, uid: str, ids: list) -> dict:
    if not ids:
        return {}
    import asyncio as _a
    r = await _a.to_thread(lambda: supa.table("predmeti").select("id,naziv").eq("user_id", uid).in_("id", ids).execute())
    return {str(p["id"]): p.get("naziv") for p in (r.data or [])}


@router.get("/api/autonomy/work-items")
@limiter.limit("60/minute")
async def lista_radnih_proizvoda(request: Request, status: str = "READY_FOR_REVIEW", matter_id: _Opt[str] = None,
                                 work_type: _Opt[str] = None, limit: int = 50, user: dict = Depends(get_current_user)):
    import asyncio as _a
    if status not in _STATUSI:
        raise HTTPException(status_code=400, detail="Nepoznat status.")
    if work_type is not None and work_type not in _TIPOVI:
        raise HTTPException(status_code=400, detail="Nepoznata vrsta rada.")
    if matter_id is not None and not _UUID.match(matter_id):
        raise HTTPException(status_code=400, detail="Neispravan predmet.")
    limit = max(1, min(int(limit), 100))
    uid = user["user_id"]
    supa = _get_supa()

    def _upit():
        q = supa.table("autonomy_work_items").select(_LISTA_KOLONE).eq("user_id", uid).eq("status", status)
        if matter_id:
            q = q.eq("predmet_id", matter_id)
        if work_type:
            q = q.eq("work_type", work_type)
        return q.order("ready_at" if status == "READY_FOR_REVIEW" else "updated_at", desc=True).limit(limit).execute()
    try:
        r = await _a.to_thread(_upit)
    except Exception as e:
        from routers.workspace import _nema_tabele
        if _nema_tabele(e):   # kod pre migracije 136: mogućnost nije uključena — nije greška
            return {"stavke": [], "ukupno": 0, "status": status, "stanje": "NIJE_UKLJUCENO"}
        _sentry_capture(e)
        logger.error("[AUTONOMY] lista nije pročitana uid=%.8s: %s", uid, type(e).__name__)
        raise HTTPException(status_code=503, detail="Pripremljeni rad trenutno nije dostupan.")
    stavke = list(r.data or [])
    nazivi = await _nazivi(supa, uid, sorted({str(s["predmet_id"]) for s in stavke}))
    for s in stavke:
        s["predmet_naziv"] = nazivi.get(str(s["predmet_id"]))
    return {"stavke": stavke, "ukupno": len(stavke), "status": status, "stanje": "OK"}


async def _ucitaj_svoj(supa, uid: str, wid: str, kolone: str) -> dict:
    import asyncio as _a
    if not _UUID.match(wid or ""):
        raise _nije_pronadjen()
    r = await _a.to_thread(lambda: supa.table("autonomy_work_items").select(kolone)
                           .eq("id", wid).eq("user_id", uid).limit(1).execute())
    red = (r.data or [None])[0]
    if not red:
        raise _nije_pronadjen()
    return red


@router.get("/api/autonomy/work-items/{work_id}")
@limiter.limit("60/minute")
async def detalj_radnog_proizvoda(work_id: str, request: Request, user: dict = Depends(get_current_user)):
    supa = _get_supa()
    red = await _ucitaj_svoj(supa, user["user_id"], work_id, _DETALJ_KOLONE)
    red["predmet_naziv"] = (await _nazivi(supa, user["user_id"], [str(red["predmet_id"])])).get(str(red["predmet_id"]))
    return red


async def _odluka(work_id: str, user: dict, novi: str, razlog: _Opt[str]) -> dict:
    import asyncio as _a
    from datetime import datetime as _dt, timezone as _tz
    uid = user["user_id"]
    supa = _get_supa()
    await _ucitaj_svoj(supa, uid, work_id, "id,status")
    sada = _dt.now(_tz.utc).isoformat()
    r = await _a.to_thread(lambda: supa.table("autonomy_work_items").update({
        "status": novi, "resolved_at": sada, "reviewed_by": uid, "updated_at": sada,
        "review_note": (razlog or "").strip()[:1000] or None,
    }).eq("id", work_id).eq("user_id", uid).eq("status", "READY_FOR_REVIEW").execute())
    if not r.data:
        raise HTTPException(status_code=409, detail="Ovaj rad više nije na pregledu.")
    red = r.data[0]
    from services.autonomy import revizija
    upisano = await revizija("AUTONOMY_WORK_ACCEPTED" if novi == "ACCEPTED" else "AUTONOMY_WORK_REJECTED", uid, red["id"],
                             red.get("predmet_id"), {"status": novi, "work_type": red.get("work_type")})
    if not upisano:
        logger.warning("[AUTONOMY] revizija odluke nije upisana work=%s", red["id"])
    return {"ok": True, "id": red["id"], "status": red["status"], "resolved_at": red.get("resolved_at")}


@router.post("/api/autonomy/work-items/{work_id}/accept")
@limiter.limit("30/minute")
async def prihvati_radni_proizvod(work_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _odluka(work_id, user, "ACCEPTED", None)


@router.post("/api/autonomy/work-items/{work_id}/reject")
@limiter.limit("30/minute")
async def odbaci_radni_proizvod(work_id: str, request: Request, telo: _Opt[OdbijanjeTelo] = None,
                                user: dict = Depends(get_current_user)):
    return await _odluka(work_id, user, "REJECTED", telo.razlog if telo else None)
