# -*- coding: utf-8 -*-
"""
Vindex AI — routers/enterprise.py

Enterprise funkcionalnosti: upravljanje timom, firma-nivo statistike,
delegiranje predmeta, role-based access control.

Endpoints:
  POST   /api/enterprise/tim/pozovi        — pozovi advokata u tim
  GET    /api/enterprise/tim/clanovi       — lista clanova tima
  DELETE /api/enterprise/tim/{user_id}     — ukloni clana
  POST   /api/enterprise/tim/uloge         — dodeli ulogu (admin/advokat/asistent)
  GET    /api/enterprise/statistike        — firma-nivo dashboard
  POST   /api/enterprise/predmet/delegiraj — delegiraj predmet advokatu
  GET    /api/enterprise/kapacitet         — pregled zauzetosti advokata
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.enterprise")
router = APIRouter(tags=["enterprise"])

# ── Role definicije ───────────────────────────────────────────────────────────

ULOGE = {
    "firma_admin": "Firma administrator — puni pristup",
    "advokat":     "Advokat — sopstveni predmeti + zajednicki",
    "asistent":    "Pravni asistent — ogranicen pristup",
    "saradnik":    "Spoljni saradnik — read-only",
}


async def _check_firma_admin(supa, user_id: str) -> dict:
    """Verifikuj da je korisnik firma admin i vrati info o firmi."""
    r = await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .select("firma_id, uloga")
            .eq("user_id", user_id)
            .eq("uloga", "firma_admin")
            .maybe_single()
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=403, detail="Samo firma administrator moze ovu akciju.")
    return r.data


async def _get_firma_id(supa, user_id: str) -> str:
    """Vrati firma_id za korisnika ili podigne 404."""
    r = await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .select("firma_id")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Niste clan nijedne firme.")
    return r.data["firma_id"]


# ── Request modeli ─────────────────────────────────────────────────────────────

class PozivanjeRequest(BaseModel):
    email: str
    uloga: str = "advokat"
    poruka: Optional[str] = None


class UlogaRequest(BaseModel):
    clan_user_id: str
    nova_uloga: str


class DelegiranjeRequest(BaseModel):
    predmet_id: str
    advokat_user_id: str
    napomena: Optional[str] = None


# ── Tim management ─────────────────────────────────────────────────────────────

@router.post("/api/enterprise/tim/pozovi")
@limiter.limit("20/hour")
async def pozovi_clana(
    request: Request,
    payload: PozivanjeRequest,
    user: dict = Depends(get_current_user),
):
    """Posalji pozivnicu advokatu da se pridruzи firmi."""
    uid = user["user_id"]
    supa = _get_supa()

    firma = await _check_firma_admin(supa, uid)
    firma_id = firma["firma_id"]

    if payload.uloga not in ULOGE:
        raise HTTPException(
            status_code=400,
            detail=f"Nepoznata uloga. Dostupne: {', '.join(ULOGE.keys())}",
        )

    token = secrets.token_urlsafe(24)

    await asyncio.to_thread(
        lambda: supa.table("firma_pozivnice").insert({
            "firma_id":    firma_id,
            "email":       payload.email,
            "uloga":       payload.uloga,
            "token":       token,
            "pozvao":      uid,
            "iskoriscena": False,
        }).execute()
    )

    base_url = os.getenv("APP_URL", "https://vindex-ai.onrender.com")
    pozivnica_url = f"{base_url}/app?firma_pozivnica={token}"

    logger.info("Firma %s: pozivnica poslata na %s (%s)", firma_id, payload.email, payload.uloga)
    return {
        "ok": True,
        "pozivnica_url": pozivnica_url,
        "email": payload.email,
        "uloga": ULOGE[payload.uloga],
    }


@router.get("/api/enterprise/tim/clanovi")
async def get_tim_clanovi(user: dict = Depends(get_current_user)):
    """Lista svih clanova firme."""
    uid = user["user_id"]
    supa = _get_supa()

    clan_r = await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .select("firma_id, uloga")
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    if not clan_r.data:
        return {"clanovi": [], "firma_id": None, "moja_uloga": None}

    firma_id = clan_r.data["firma_id"]

    r = await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .select("user_id, uloga, created_at")
            .eq("firma_id", firma_id)
            .order("created_at", desc=False)
            .execute()
    )

    return {
        "clanovi":    r.data or [],
        "firma_id":   firma_id,
        "moja_uloga": clan_r.data["uloga"],
        "uloge_opis": ULOGE,
    }


@router.delete("/api/enterprise/tim/{clan_user_id}")
async def ukloni_clana(clan_user_id: str, user: dict = Depends(get_current_user)):
    """Ukloni clana iz tima (samo firma admin)."""
    uid = user["user_id"]
    supa = _get_supa()

    firma = await _check_firma_admin(supa, uid)

    if clan_user_id == uid:
        raise HTTPException(status_code=400, detail="Ne mozete ukloniti sebe iz tima.")

    await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .delete()
            .eq("user_id", clan_user_id)
            .eq("firma_id", firma["firma_id"])
            .execute()
    )

    logger.info("Firma %s: uklonjen clan %s", firma["firma_id"], clan_user_id)
    return {"ok": True}


@router.post("/api/enterprise/tim/uloge")
async def dodeli_ulogu(payload: UlogaRequest, user: dict = Depends(get_current_user)):
    """Promeni ulogu clana tima (samo firma admin)."""
    uid = user["user_id"]
    supa = _get_supa()

    firma = await _check_firma_admin(supa, uid)

    if payload.nova_uloga not in ULOGE:
        raise HTTPException(status_code=400, detail=f"Nepoznata uloga: {payload.nova_uloga}")

    await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .update({"uloga": payload.nova_uloga})
            .eq("user_id", payload.clan_user_id)
            .eq("firma_id", firma["firma_id"])
            .execute()
    )

    return {"ok": True, "nova_uloga": payload.nova_uloga, "opis": ULOGE[payload.nova_uloga]}


# ── Statistike i kapacitet ─────────────────────────────────────────────────────

@router.get("/api/enterprise/statistike")
async def firma_statistike(user: dict = Depends(get_current_user)):
    """Firma-nivo dashboard statistike."""
    uid = user["user_id"]
    supa = _get_supa()

    firma_id = await _get_firma_id(supa, uid)

    clanovi_r = await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .select("user_id, uloga")
            .eq("firma_id", firma_id)
            .execute()
    )
    clan_ids = [c["user_id"] for c in (clanovi_r.data or [])]

    if not clan_ids:
        return {"firma_id": firma_id, "clanovi_count": 0}

    predmeti_r, klijenti_r, fakture_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("user_id, status", count="exact")
                .in_("user_id", clan_ids)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("klijenti")
                .select("user_id", count="exact")
                .in_("user_id", clan_ids)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("fakture")
                .select("user_id, iznos, status")
                .in_("user_id", clan_ids)
                .execute()
        ),
    )

    fakture = fakture_r.data or []
    ukupan_prihod  = sum(float(f.get("iznos") or 0) for f in fakture)
    placene_fakture = sum(1 for f in fakture if f.get("status") == "placena")

    # Broj predmeta po statusu
    predmeti = predmeti_r.data or []
    predmeti_po_statusu: dict[str, int] = {}
    for p in predmeti:
        s = p.get("status") or "nepoznat"
        predmeti_po_statusu[s] = predmeti_po_statusu.get(s, 0) + 1

    return {
        "firma_id":            firma_id,
        "clanovi_count":       len(clan_ids),
        "predmeti_ukupno":     predmeti_r.count or len(predmeti),
        "predmeti_po_statusu": predmeti_po_statusu,
        "klijenti_ukupno":     klijenti_r.count or 0,
        "fakture_prihod":      round(ukupan_prihod, 2),
        "fakture_placene":     placene_fakture,
        "fakture_ukupno":      len(fakture),
    }


@router.get("/api/enterprise/kapacitet")
async def firma_kapacitet(user: dict = Depends(get_current_user)):
    """Pregled zauzetosti advokata u firmi — broj aktivnih predmeta po advokatu."""
    uid = user["user_id"]
    supa = _get_supa()

    firma_id = await _get_firma_id(supa, uid)

    clanovi_r = await asyncio.to_thread(
        lambda: supa.table("firma_clanovi")
            .select("user_id, uloga")
            .eq("firma_id", firma_id)
            .execute()
    )
    clanovi = clanovi_r.data or []

    if not clanovi:
        return {"kapacitet": []}

    # Dohvati aktivne predmete za sve clanove odjednom
    clan_ids = [c["user_id"] for c in clanovi]
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("user_id, status")
            .in_("user_id", clan_ids)
            .eq("status", "aktivan")
            .execute()
    )

    # Grupisanje po user_id
    pred_count: dict[str, int] = {}
    for p in (pred_r.data or []):
        uid_p = p["user_id"]
        pred_count[uid_p] = pred_count.get(uid_p, 0) + 1

    kapacitet = [
        {
            "user_id":          c["user_id"],
            "uloga":            c["uloga"],
            "aktivnih_predmeta": pred_count.get(c["user_id"], 0),
        }
        for c in clanovi
    ]
    kapacitet.sort(key=lambda x: x["aktivnih_predmeta"], reverse=True)

    return {"kapacitet": kapacitet, "firma_id": firma_id}


# ── Delegiranje predmeta ───────────────────────────────────────────────────────

@router.post("/api/enterprise/predmet/delegiraj")
async def delegiraj_predmet(
    payload: DelegiranjeRequest,
    user: dict = Depends(get_current_user),
):
    """Delegiraj predmet drugom advokatu u firmi."""
    uid = user["user_id"]
    supa = _get_supa()

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("naziv, user_id")
            .eq("id", payload.predmet_id)
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(
            status_code=404,
            detail="Predmet nije pronadjen ili nemate pravo delegiranja.",
        )

    await asyncio.to_thread(
        lambda: supa.table("predmet_delegiranja").insert({
            "predmet_id":      payload.predmet_id,
            "od_user_id":      uid,
            "na_user_id":      payload.advokat_user_id,
            "napomena":        payload.napomena,
            "status":          "aktivno",
        }).execute()
    )

    logger.info("Predmet %s delegiran sa %s na %s", payload.predmet_id, uid, payload.advokat_user_id)
    return {"ok": True, "predmet_id": payload.predmet_id}


@router.get("/api/enterprise/predmet/delegiranja")
async def get_delegiranja(user: dict = Depends(get_current_user)):
    """Lista predmeta delegiranih od/ka korisniku."""
    uid = user["user_id"]
    supa = _get_supa()

    od_r, ka_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_delegiranja")
                .select("*")
                .eq("od_user_id", uid)
                .order("created_at", desc=True)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_delegiranja")
                .select("*")
                .eq("na_user_id", uid)
                .order("created_at", desc=True)
                .execute()
        ),
    )

    return {
        "delegirano_od_mene": od_r.data or [],
        "delegirano_ka_meni": ka_r.data or [],
    }
