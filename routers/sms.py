# -*- coding: utf-8 -*-
"""
Vindex AI — routers/sms.py

SMS/WhatsApp notifikacije via Twilio.
Korisnik upisuje broj telefona → dobija SMS podsetnike 24h i 48h pre kritičnih rokova.

Env vars (Railway):
  TWILIO_ACCOUNT_SID   — Twilio Account SID
  TWILIO_AUTH_TOKEN    — Twilio Auth Token
  TWILIO_FROM_NUMBER   — broj/WhatsApp sender (npr. +381XXXXXXXX ili whatsapp:+14155238886)

Endpoints:
  GET  /sms/status                    — da li je Twilio konfigurisan
  POST /sms/telefon                   — korisnik čuva/menja broj telefona
  GET  /sms/telefon                   — korisnik čita svoj broj
  DELETE /sms/telefon                 — korisnik briše broj i onemogućava SMS
  POST /sms/test                      — pošalje test SMS na broj korisnika
  POST /sms/send-reminders            — interní cron trigger (founder only)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.sms")
router = APIRouter(tags=["sms"])

_FOUNDER_EMAILS = set(
    e.strip().lower()
    for e in os.getenv("FOUNDER_EMAILS", "").split(",")
    if e.strip()
)


def _twilio_client():
    """Vraća Twilio client ili None ako Twilio nije konfigurisan."""
    sid   = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        return None
    try:
        from twilio.rest import Client
        return Client(sid, token)
    except ImportError:
        logger.warning("[SMS] twilio paket nije instaliran — SMS nije dostupan")
        return None


def _from_number() -> str:
    return os.getenv("TWILIO_FROM_NUMBER", "").strip()


def _normalize_phone(broj: str) -> str:
    """Normalizuje broj u E.164 format (srpski 06X → +3816X)."""
    cleaned = re.sub(r"[\s\-\(\)\.]+", "", broj.strip())
    if cleaned.startswith("06"):
        cleaned = "+381" + cleaned[1:]
    elif cleaned.startswith("381") and not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    if not re.match(r"^\+\d{7,15}$", cleaned):
        raise ValueError(f"Neispravan format broja telefona: {broj!r}")
    return cleaned


def _send_sms(to: str, body: str) -> bool:
    """Šalje SMS. Vraća True ako uspešno."""
    client = _twilio_client()
    if not client:
        logger.warning("[SMS] Twilio nije konfigurisan — SMS nije poslat na %s", to)
        return False
    from_num = _from_number()
    if not from_num:
        logger.warning("[SMS] TWILIO_FROM_NUMBER nije postavljen")
        return False
    try:
        msg = client.messages.create(body=body, from_=from_num, to=to)
        logger.info("[SMS] Poslat: %s → %s (sid=%s)", from_num, to, msg.sid)
        return True
    except Exception as exc:
        logger.error("[SMS] Greška pri slanju na %s: %s", to, exc)
        return False


# ─── Modeli ───────────────────────────────────────────────────────────────────

class TelefonReq(BaseModel):
    broj: str = Field(..., min_length=9, max_length=20)
    whatsapp: bool = Field(default=False, description="Pošalji WhatsApp umesto SMS")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/sms/status")
async def sms_status():
    """Vraća da li je Twilio konfigurisan (bez auth)."""
    konfigurisan = bool(
        os.getenv("TWILIO_ACCOUNT_SID") and
        os.getenv("TWILIO_AUTH_TOKEN") and
        os.getenv("TWILIO_FROM_NUMBER")
    )
    return {"konfigurisan": konfigurisan}


@router.post("/sms/telefon")
@limiter.limit("10/minute")
async def sacuvaj_telefon(
    req: TelefonReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Korisnik čuva/menja broj telefona za SMS notifikacije."""
    try:
        normalized = _normalize_phone(req.broj)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    supa  = _get_supa()
    uid   = user["user_id"]
    email = user.get("email", "")

    await asyncio.to_thread(
        lambda: supa.table("korisnik_sms_profil").upsert({
            "user_id":  uid,
            "email":    email,
            "telefon":  normalized,
            "whatsapp": req.whatsapp,
            "aktivan":  True,
        }, on_conflict="user_id").execute()
    )
    logger.info("[SMS] Broj sačuvan za korisnika %s → %s", uid[:8], normalized)
    return {"ok": True, "telefon": normalized, "whatsapp": req.whatsapp}


@router.get("/sms/telefon")
@limiter.limit("30/minute")
async def citaj_telefon(request: Request, user: dict = Depends(get_current_user)):
    """Čita SMS profil korisnika."""
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("korisnik_sms_profil")
                .select("telefon,whatsapp,aktivan")
                .eq("user_id", user["user_id"])
                .maybe_single()
                .execute()
        )
        return r.data or {"telefon": None, "whatsapp": False, "aktivan": False}
    except Exception:
        return {"telefon": None, "whatsapp": False, "aktivan": False}


@router.delete("/sms/telefon")
@limiter.limit("10/minute")
async def obrisi_telefon(request: Request, user: dict = Depends(get_current_user)):
    """Deaktivira SMS notifikacije (ne briše broj — samo aktivan=False)."""
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("korisnik_sms_profil")
            .update({"aktivan": False})
            .eq("user_id", user["user_id"])
            .execute()
    )
    return {"ok": True, "aktivan": False}


@router.post("/sms/test")
@limiter.limit("3/minute")
async def posalji_test_sms(request: Request, user: dict = Depends(get_current_user)):
    """Pošalje test SMS na broj korisnika."""
    supa = _get_supa()
    uid  = user["user_id"]

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("korisnik_sms_profil")
                .select("telefon,whatsapp,aktivan")
                .eq("user_id", uid)
                .eq("aktivan", True)
                .maybe_single()
                .execute()
        )
        profil = r.data
    except Exception:
        profil = None

    if not profil or not profil.get("telefon"):
        raise HTTPException(status_code=422, detail="Niste uneli broj telefona. Dodajte ga u Podešavanjima.")

    telefon  = profil["telefon"]
    whatsapp = profil.get("whatsapp", False)
    to_num   = (f"whatsapp:{telefon}" if whatsapp else telefon)

    poruka = (
        "Vindex AI — test poruka ✓\n"
        "SMS notifikacije su uspešno aktivirane.\n"
        "Dobićete podsetnike 48h i 24h pre kritičnih rokova."
    )

    ok = await asyncio.to_thread(_send_sms, to_num, poruka)
    if not ok:
        raise HTTPException(status_code=503, detail="SMS nije mogao biti poslat. Proverite konfiguraciju Twilio-a.")

    return {"ok": True, "poslat_na": telefon}


@router.post("/sms/send-reminders")
@limiter.limit("5/minute")
async def posalji_podsetnike(request: Request, user: dict = Depends(get_current_user)):
    """
    Interni cron trigger — šalje SMS podsetnike za rokove u narednih 48h.
    Samo za founder korisnike (poziva se Railway cron-om ili ručno).
    """
    email = user.get("email", "").lower()
    if email not in _FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Restricted.")

    supa    = _get_supa()
    today   = date.today()
    in_48h  = (today + timedelta(days=2)).isoformat()
    in_24h  = (today + timedelta(days=1)).isoformat()
    today_s = today.isoformat()

    poslato = 0
    greske  = 0

    try:
        # Svi aktivni SMS profili
        profili_r = await asyncio.to_thread(
            lambda: supa.table("korisnik_sms_profil")
                .select("user_id,telefon,whatsapp")
                .eq("aktivan", True)
                .execute()
        )
        profili = {p["user_id"]: p for p in (profili_r.data or [])}

        if not profili:
            return {"poslato": 0, "greske": 0, "napomena": "Nema aktivnih SMS profila"}

        # Rokovi u narednih 48h za sve korisnike koji imaju SMS
        for uid, profil in profili.items():
            try:
                rokovi_r = await asyncio.to_thread(
                    lambda uid=uid: supa.table("predmet_hronologija")
                        .select("dogadjaj,datum_iso,predmet_id")
                        .eq("user_id", uid)
                        .eq("vaznost", "kritičan")
                        .gte("datum_iso", today_s)
                        .lte("datum_iso", in_48h)
                        .execute()
                )
                rokovi = rokovi_r.data or []
                if not rokovi:
                    continue

                telefon  = profil["telefon"]
                whatsapp = profil.get("whatsapp", False)
                to_num   = (f"whatsapp:{telefon}" if whatsapp else telefon)

                for rok in rokovi:
                    datum   = rok.get("datum_iso", "")
                    dogadjaj = rok.get("dogadjaj", "Rok")
                    hitnost  = "🔴 SUTRA" if datum == in_24h else "⚠ Za 2 dana"
                    poruka = (
                        f"Vindex AI — {hitnost}\n"
                        f"ROK: {dogadjaj}\n"
                        f"Datum: {datum}\n"
                        "Prijavite se na Vindex AI za detalje."
                    )
                    ok = await asyncio.to_thread(_send_sms, to_num, poruka)
                    if ok:
                        poslato += 1
                    else:
                        greske += 1
            except Exception as e:
                logger.error("[SMS-CRON] Greška za korisnika %s: %s", uid[:8], e)
                greske += 1

    except Exception as exc:
        logger.error("[SMS-CRON] Fatalna greška: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri slanju podsetnika.")

    logger.info("[SMS-CRON] Završeno: poslato=%d greške=%d", poslato, greske)
    return {"poslato": poslato, "greske": greske}
