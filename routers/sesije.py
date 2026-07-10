# -*- coding: utf-8 -*-
"""
Vindex AI — routers/sesije.py

Zaštita od deljenja naloga:
- Svaki uređaj dobija trajni device_id (localStorage)
- Registracija sesije na login, ping svake minute, brisanje na logout
- Limit: 1 sesija (Basic/Free), 2 sesije (PRO), neograničeno (Founder)
- Sesija se smatra neaktivnom ako nema pinga 5+ minuta
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from shared.deps import get_current_user, _get_supa, _is_founder, _ensure_profile

router = APIRouter()
logger = logging.getLogger("vindex.sesije")

# ─── Konstante ────────────────────────────────────────────────────────────────
SESSION_EXPIRY_MIN = 5   # sesija neaktivna nakon 5 min bez pinga
LIMIT_FREE         = 1   # 1 istovremena sesija za Free/Basic
LIMIT_PRO          = 2   # 2 istovremene sesije za PRO (kancelarija + kuća)


# ─── Modeli ───────────────────────────────────────────────────────────────────
class SesijaBody(BaseModel):
    device_id: str


# ─── Interne funkcije ─────────────────────────────────────────────────────────
def _ocisti_stare(user_id: str) -> None:
    """Briše sesije bez pinga duže od SESSION_EXPIRY_MIN minuta."""
    try:
        granica = (
            datetime.now(timezone.utc) - timedelta(minutes=SESSION_EXPIRY_MIN)
        ).isoformat()
        _get_supa().table("aktivne_sesije") \
            .delete() \
            .eq("user_id", user_id) \
            .lt("poslednja_aktivnost", granica) \
            .execute()
    except Exception as e:
        logger.warning("[SESIJE] ocisti_stare neuspešno: %s", e)


def _broj_aktivnih(user_id: str) -> int:
    """Vraća broj trenutno aktivnih sesija (posle čišćenja)."""
    try:
        res = _get_supa().table("aktivne_sesije") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .execute()
        return res.count or 0
    except Exception as e:
        logger.warning("[SESIJE] broj_aktivnih greška: %s", e)
        return 0


def _limit(user_id: str, email: str) -> int:
    if _is_founder(email):
        return 9999
    profil = _ensure_profile(user_id, email)
    return LIMIT_PRO if profil.get("is_pro") else LIMIT_FREE


def _upsert_sesija(user_id: str, device_id: str) -> None:
    _get_supa().table("aktivne_sesije").upsert(
        {
            "user_id": user_id,
            "device_id": device_id[:64],
            "poslednja_aktivnost": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="user_id,device_id",
    ).execute()


# ─── Endpointi ────────────────────────────────────────────────────────────────
@router.post("/api/sesija/registruj")
async def registruj_sesiju(
    body: SesijaBody,
    user: dict = Depends(get_current_user),
):
    """
    Poziva se odmah nakon uspešne prijave.
    Proverava limit sesija i registruje novi uređaj.
    Vraća 409 ako je limit dostignut.
    """
    user_id  = user["user_id"]
    email    = user.get("email", "")
    dev_id   = body.device_id[:64]

    # 1. Obriši stare sesije
    await asyncio.to_thread(_ocisti_stare, user_id)

    # 2. Proveri da li ovaj uređaj već ima sesiju → samo obnovi timestamp
    try:
        existing = (
            _get_supa().table("aktivne_sesije")
            .select("id")
            .eq("user_id", user_id)
            .eq("device_id", dev_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        existing = None

    if existing and existing.data:
        await asyncio.to_thread(_upsert_sesija, user_id, dev_id)
        return {"status": "ok", "poruka": "Sesija obnovljena"}

    # 3. Novi uređaj — proveri limit
    lim   = await asyncio.to_thread(_limit, user_id, email)
    broj  = await asyncio.to_thread(_broj_aktivnih, user_id)

    if broj >= lim:
        paket_naziv = "PRO" if lim == LIMIT_PRO else "Basic"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SESSION_LIMIT",
                "message": (
                    f"Vaš nalog je već aktivan na {broj} uređaj/a "
                    f"(limit za {paket_naziv} paket: {lim}). "
                    "Odjavite se sa drugog uređaja ili nadogradite nalog."
                ),
                "aktivnih": broj,
                "limit": lim,
            },
        )

    # 4. Upiši novu sesiju
    try:
        await asyncio.to_thread(_upsert_sesija, user_id, dev_id)
    except Exception as e:
        logger.error("[SESIJE] insert neuspešan: %s", e)

    logger.info(
        "[SESIJE] Nova sesija: uid=%.8s dev=%.8s (%d/%d)",
        user_id, dev_id, broj + 1, lim,
    )
    return {"status": "ok", "poruka": "Sesija registrovana", "aktivnih": broj + 1}


@router.post("/api/sesija/ping")
async def ping_sesija(
    body: SesijaBody,
    user: dict = Depends(get_current_user),
):
    """Heartbeat — poziva se svakih 60 sekundi dok je korisnik aktivan."""
    user_id = user["user_id"]
    dev_id  = body.device_id[:64]
    try:
        await asyncio.to_thread(_upsert_sesija, user_id, dev_id)
    except Exception as e:
        logger.warning("[SESIJE] ping neuspešan: %s", e)
    return {"status": "ok"}


@router.delete("/api/sesija/odjavi")
async def odjavi_sesiju(
    body: SesijaBody,
    user: dict = Depends(get_current_user),
):
    """Briše sesiju pri odjavljivanju. Oslobađa slot za sledeći login."""
    user_id = user["user_id"]
    dev_id  = body.device_id[:64]
    try:
        _get_supa().table("aktivne_sesije") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("device_id", dev_id) \
            .execute()
    except Exception as e:
        logger.warning("[SESIJE] odjava neuspešna: %s", e)
    return {"status": "ok", "poruka": "Sesija odjavljena"}


@router.get("/api/sesija/status")
async def status_sesija(user: dict = Depends(get_current_user)):
    """Vraća broj aktivnih sesija za trenutnog korisnika (debug/info endpoint)."""
    user_id = user["user_id"]
    email   = user.get("email", "")
    await asyncio.to_thread(_ocisti_stare, user_id)
    broj = await asyncio.to_thread(_broj_aktivnih, user_id)
    lim  = await asyncio.to_thread(_limit, user_id, email)
    return {
        "aktivnih_sesija": broj,
        "limit":           lim,
        "slobodnih":       max(0, lim - broj),
    }
