# -*- coding: utf-8 -*-
"""
ToS (Uslovi korišćenja) + saglasnost za AI obradu podataka.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.tos")
router = APIRouter(prefix="/api/tos", tags=["tos"])

CURRENT_VERSION = "2026-07-02"


@router.get("/status")
async def tos_status(user=Depends(get_current_user)):
    """Vraća da li je korisnik prihvatio aktuelnu verziju uslova."""
    supa = _get_supa()
    uid  = user["user_id"]
    try:
        r = supa.table("tos_acceptances").select("version,accepted_at").eq(
            "user_id", uid
        ).eq("version", CURRENT_VERSION).execute()
        accepted = bool(r.data)
    except Exception:
        accepted = True  # ne blokiraj na DB grešku
    return {"accepted": accepted, "current_version": CURRENT_VERSION}


@router.post("/accept")
async def tos_accept(user=Depends(get_current_user)):
    """Beleži prihvatanje uslova i saglasnosti za AI obradu."""
    supa = _get_supa()
    uid  = user["user_id"]
    try:
        existing = supa.table("tos_acceptances").select("id").eq(
            "user_id", uid
        ).eq("version", CURRENT_VERSION).execute()
        if not existing.data:
            supa.table("tos_acceptances").insert({
                "user_id":     uid,
                "version":     CURRENT_VERSION,
                "accepted_at": datetime.utcnow().isoformat(),
                "ai_consent":  True,
            }).execute()
    except Exception as e:
        logger.warning("[TOS] Insert greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri beleženju saglasnosti.")
    return {"ok": True}
