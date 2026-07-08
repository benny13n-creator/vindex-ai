# -*- coding: utf-8 -*-
"""
Vindex AI — routers/zadaci.py

Team Task Assignment — dodela zadataka u okviru kancelarije.

Šta radi:
  - Partner kreira zadatak i dodeljuje ga članu tima
  - Svaki zadatak je vezan za predmet (opciono)
  - Notifikacija dodelje_nom članu (proactive_alerts)
  - Status tracking: otvoreno → u_toku → zavrseno
  - Dashboard: moji zadaci, zadaci tima, prekoračeni rokovi

Endpoints:
  POST   /api/zadaci/kreiraj            — kreiraj i dodeli zadatak
  GET    /api/zadaci/moji               — zadaci dodeljeni meni
  GET    /api/zadaci/tim                — svi zadaci kancelarije (partner/admin)
  PATCH  /api/zadaci/{id}/status        — ažuriraj status
  PATCH  /api/zadaci/{id}/dodeli        — redodeli zadatak
  DELETE /api/zadaci/{id}               — obriši (samo kreator ili admin)
  GET    /api/zadaci/predmet/{id}       — zadaci vezani za predmet
  GET    /api/zadaci/statistika         — dashboard statistika
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.zadaci")
router = APIRouter(prefix="/api/zadaci", tags=["zadaci"])

_VALIDNI_STATUSI  = {"otvoreno", "u_toku", "ceka", "zavrseno", "otkazano"}
_VALIDNI_PRIORITETI = {"hitno", "visoko", "normalan", "nisko"}


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class ZadatakRequest(BaseModel):
    naziv:          str = Field(..., min_length=2, max_length=200)
    opis:           Optional[str] = None
    prioritet:      str = Field("normalan")
    rok_datum:      Optional[str] = None
    predmet_id:     Optional[str] = None
    dodeljen_uid:   Optional[str] = None  # user_id kome se dodeljuje


class StatusUpdate(BaseModel):
    status:   str
    komentar: Optional[str] = None


class DodeljivanjeUpdate(BaseModel):
    dodeljen_uid: str


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_firma_info(supa, uid: str) -> dict:
    """Vraća {kancelarija_id, uloga, is_admin} za korisnika."""
    try:
        # Provjeri da li je admin firme
        admin_r = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("id")
                .eq("admin_uid", uid)
                .maybe_single()
                .execute()
        )
        if admin_r.data:
            return {"kancelarija_id": admin_r.data["id"], "uloga": "admin", "is_admin": True}

        # Inače — član
        clan_r = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("kancelarija_id, uloga")
                .eq("user_id", uid)
                .eq("status", "aktivan")
                .maybe_single()
                .execute()
        )
        if clan_r.data:
            uloga = clan_r.data.get("uloga", "saradnik")
            return {
                "kancelarija_id": clan_r.data["kancelarija_id"],
                "uloga": uloga,
                "is_admin": uloga in ("admin", "partner"),
            }
    except Exception as e:
        logger.debug("[ZADACI] get_firma_info greška: %s", e)

    return {"kancelarija_id": None, "uloga": None, "is_admin": False}


async def _posalji_notifikaciju(supa, dodeljen_uid: str, naziv: str, kreirao: str, prioritet: str) -> None:
    """Kreira proactive_alert za dodelje_nog člana."""
    try:
        urgentnost = "hitna" if prioritet == "hitno" else ("visoka" if prioritet == "visoko" else "normalna")
        await asyncio.to_thread(
            lambda: supa.table("proactive_alerts").insert({
                "user_id":    dodeljen_uid,
                "tip":        "novi_zadatak",
                "naslov":     f"Novi zadatak: {naziv[:60]}",
                "opis":       f"Zadatak [{prioritet.upper()}] dodelio/la vam je kolega/ica.",
                "urgentnost": urgentnost,
                "procitana":  False,
            }).execute()
        )
    except Exception as e:
        logger.debug("[ZADACI] notifikacija greška: %s", e)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/kreiraj")
@limiter.limit("30/minute")
async def kreiraj_zadatak(
    request: Request,
    payload: ZadatakRequest,
    user: dict = Depends(get_current_user),
):
    """Kreira zadatak i dodeljuje ga članu tima."""
    uid  = user["user_id"]
    supa = _get_supa()

    if payload.prioritet not in _VALIDNI_PRIORITETI:
        raise HTTPException(status_code=400, detail=f"Prioritet mora biti: {', '.join(_VALIDNI_PRIORITETI)}")

    firma = await _get_firma_info(supa, uid)
    kancelarija_id = firma.get("kancelarija_id")

    # Validacija datuma
    rok_datum = None
    if payload.rok_datum:
        try:
            rok_datum = date.fromisoformat(payload.rok_datum).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="Neispravan format datuma (YYYY-MM-DD).")

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci").insert({
                "kancelarija_id": kancelarija_id,
                "predmet_id":     payload.predmet_id,
                "kreirao_uid":    uid,
                "dodeljen_uid":   payload.dodeljen_uid,
                "naziv":          payload.naziv,
                "opis":           payload.opis or "",
                "prioritet":      payload.prioritet,
                "status":         "otvoreno",
                "rok_datum":      rok_datum,
            }).execute()
        )
        zadatak = r.data[0] if r.data else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Greška pri kreiranju: {e}")

    # Notifikacija
    if payload.dodeljen_uid and payload.dodeljen_uid != uid:
        asyncio.create_task(
            _posalji_notifikaciju(supa, payload.dodeljen_uid, payload.naziv, uid, payload.prioritet)
        )

    return {"ok": True, "zadatak": zadatak}


@router.get("/moji")
@limiter.limit("30/minute")
async def moji_zadaci(
    request: Request,
    user: dict = Depends(get_current_user),
    status_filter: Optional[str] = None,
):
    """Zadaci dodeljeni trenutnom korisniku."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        q = (
            supa.table("zadaci")
            .select("*, predmeti(naziv)")
            .eq("dodeljen_uid", uid)
        )
        if status_filter and status_filter in _VALIDNI_STATUSI:
            q = q.eq("status", status_filter)
        else:
            q = q.not_.in_("status", ["zavrseno", "otkazano"])

        r = await asyncio.to_thread(
            lambda: q.order("prioritet").order("rok_datum").limit(100).execute()
        )
        zadaci = r.data or []

        hitni   = sum(1 for z in zadaci if z.get("prioritet") == "hitno")
        prekoraceni = sum(
            1 for z in zadaci
            if z.get("rok_datum") and z["rok_datum"] < date.today().isoformat()
            and z.get("status") not in ("zavrseno", "otkazano")
        )

        return {
            "zadaci":       zadaci,
            "ukupno":       len(zadaci),
            "hitnih":       hitni,
            "prekoracenih": prekoraceni,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tim")
@limiter.limit("20/minute")
async def zadaci_tima(
    request: Request,
    user: dict = Depends(get_current_user),
    samo_otvoreni: bool = True,
):
    """Svi zadaci kancelarije (vidljivo svim članovima, ne samo adminu)."""
    uid  = user["user_id"]
    supa = _get_supa()

    firma = await _get_firma_info(supa, uid)
    kancelarija_id = firma.get("kancelarija_id")
    if not kancelarija_id:
        return {"zadaci": [], "ukupno": 0, "poruka": "Niste član nijedne kancelarije."}

    try:
        q = supa.table("zadaci").select("*").eq("kancelarija_id", kancelarija_id)
        if samo_otvoreni:
            q = q.not_.in_("status", ["zavrseno", "otkazano"])

        r = await asyncio.to_thread(
            lambda: q.order("prioritet").order("rok_datum", desc=False).limit(200).execute()
        )
        zadaci = r.data or []

        by_status: dict[str, int] = {}
        for z in zadaci:
            s = z.get("status", "otvoreno")
            by_status[s] = by_status.get(s, 0) + 1

        return {
            "zadaci":    zadaci,
            "ukupno":    len(zadaci),
            "by_status": by_status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{zadatak_id}/status")
@limiter.limit("60/minute")
async def azuriraj_status(
    zadatak_id: str,
    request: Request,
    payload: StatusUpdate,
    user: dict = Depends(get_current_user),
):
    """Ažurira status zadatka."""
    uid  = user["user_id"]
    supa = _get_supa()

    if payload.status not in _VALIDNI_STATUSI:
        raise HTTPException(status_code=400, detail=f"Status mora biti: {', '.join(_VALIDNI_STATUSI)}")

    update_data: dict = {
        "status":     payload.status,
        "updated_at": _now_iso(),
    }
    if payload.komentar:
        update_data["komentar"] = payload.komentar[:500]
    if payload.status == "zavrseno":
        update_data["zavrseno_u"] = _now_iso()

    try:
        # Provera vlasništva (dodeljen ili kreirao)
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci")
                .update(update_data)
                .eq("id", zadatak_id)
                .or_(f"dodeljen_uid.eq.{uid},kreirao_uid.eq.{uid}")
                .execute()
        )
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Zadatak nije pronađen ili nemate pristup.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "novi_status": payload.status}


@router.patch("/{zadatak_id}/dodeli")
@limiter.limit("30/minute")
async def redodeli_zadatak(
    zadatak_id: str,
    request: Request,
    payload: DodeljivanjeUpdate,
    user: dict = Depends(get_current_user),
):
    """Redodeli zadatak drugom članu tima (partner/admin ili kreator)."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci")
                .update({
                    "dodeljen_uid": payload.dodeljen_uid,
                    "updated_at":   _now_iso(),
                })
                .eq("id", zadatak_id)
                .eq("kreirao_uid", uid)
                .execute()
        )
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Zadatak nije pronađen ili nemate pravo redodele.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "dodeljen_uid": payload.dodeljen_uid}


@router.delete("/{zadatak_id}")
@limiter.limit("20/minute")
async def obrisi_zadatak(
    zadatak_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Briše zadatak (samo kreator ili admin kancelarije)."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma_info(supa, uid)

    try:
        if firma.get("is_admin"):
            q = supa.table("zadaci").delete().eq("id", zadatak_id)
        else:
            q = supa.table("zadaci").delete().eq("id", zadatak_id).eq("kreirao_uid", uid)

        r = await asyncio.to_thread(lambda: q.execute())
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Zadatak nije pronađen ili nemate pravo brisanja.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True}


@router.get("/predmet/{predmet_id}")
@limiter.limit("30/minute")
async def zadaci_za_predmet(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Svi zadaci vezani za dati predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci")
                .select("*")
                .eq("predmet_id", predmet_id)
                .order("prioritet")
                .limit(50)
                .execute()
        )
        return {"zadaci": r.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistika")
@limiter.limit("20/minute")
async def zadaci_statistika(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dashboard statistika zadataka za korisnika i tim."""
    uid  = user["user_id"]
    supa = _get_supa()
    danas = date.today().isoformat()
    firma = await _get_firma_info(supa, uid)
    kancelarija_id = firma.get("kancelarija_id")

    moji_r, tim_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("zadaci")
                .select("status, prioritet, rok_datum")
                .eq("dodeljen_uid", uid)
                .not_.in_("status", ["zavrseno", "otkazano"])
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("zadaci")
                .select("status, prioritet, rok_datum, dodeljen_uid")
                .eq("kancelarija_id", kancelarija_id)
                .not_.in_("status", ["zavrseno", "otkazano"])
                .execute()
        ) if kancelarija_id else asyncio.coroutine(lambda: type('obj', (object,), {'data': []})())(),
    )

    moji   = moji_r.data or []
    timski = tim_r.data  if not isinstance(tim_r, Exception) else []
    if hasattr(timski, 'data'):
        timski = timski.data or []

    return {
        "moji_zadaci": {
            "ukupno":       len(moji),
            "hitnih":       sum(1 for z in moji if z.get("prioritet") == "hitno"),
            "prekoracenih": sum(1 for z in moji if z.get("rok_datum", "9999") < danas),
        },
        "tim_zadaci": {
            "ukupno":       len(timski),
            "hitnih":       sum(1 for z in timski if z.get("prioritet") == "hitno"),
            "prekoracenih": sum(1 for z in timski if z.get("rok_datum", "9999") < danas),
        } if kancelarija_id else None,
    }
