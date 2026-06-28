# -*- coding: utf-8 -*-
"""
Vindex AI — routers/viber.py

Viber Bot notifikacije (najpopularniji messaging u Srbiji i regionu).

Arhitektura:
  1. Korisnik otvara Viber bota (VIBER_BOT_URI) → Viber šalje webhook na /viber/webhook
  2. Webhook beleži Viber user ID → čuva u korisnik_viber_profil
  3. Vindex može slati jutarnji briefing i podsetnike via /api/viber/send-briefing

Env vars:
  VIBER_AUTH_TOKEN  — iz Viber Developers portala
  VIBER_BOT_NAME    — prikazano ime bota (default: "Vindex AI")
  VIBER_BOT_URI     — deep link za otvaranje bota (npr. viber://pa?chatURI=vindex_ai)

Endpointi:
  POST /viber/webhook           — Viber šalje svi eventi (subscribe, message, ...)
  GET  /api/viber/status        — da li je Viber konfigurisan
  POST /api/viber/send-briefing — pošalji jutarnji izveštaj korisniku
  POST /api/viber/test          — test poruka za auth korisnika
  POST /api/viber/cron-briefing — cron trigger: šalje svim pretplaćenim (founder only)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.viber")
router = APIRouter(tags=["viber"])

_VIBER_API = "https://chatapi.viber.com/pa"

_FOUNDER_EMAILS = set(
    e.strip().lower()
    for e in os.getenv("FOUNDER_EMAILS", "").split(",")
    if e.strip()
)


def _viber_headers() -> dict:
    token = os.getenv("VIBER_AUTH_TOKEN", "").strip()
    return {"X-Viber-Auth-Token": token, "Content-Type": "application/json"}


def _viber_configured() -> bool:
    return bool(os.getenv("VIBER_AUTH_TOKEN", "").strip())


def _verify_viber_signature(body: bytes, signature: str) -> bool:
    """Verify X-Viber-Content-Signature header."""
    token = os.getenv("VIBER_AUTH_TOKEN", "").strip()
    if not token:
        return False
    expected = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


async def _viber_send(viber_user_id: str, text: str) -> bool:
    """Send text message to a Viber user. Returns True on success."""
    if not _viber_configured():
        logger.warning("[VIBER] VIBER_AUTH_TOKEN nije konfigurisan")
        return False
    bot_name = os.getenv("VIBER_BOT_NAME", "Vindex AI")
    payload = {
        "receiver": viber_user_id,
        "min_api_version": 1,
        "sender": {"name": bot_name},
        "type": "text",
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_VIBER_API}/send_message",
                json=payload,
                headers=_viber_headers(),
            )
            data = resp.json()
            if data.get("status") == 0:
                logger.info("[VIBER] Poruka poslata: viber_id=%s", viber_user_id[:8])
                return True
            logger.warning("[VIBER] API greška: %s", data.get("status_message"))
            return False
    except Exception as exc:
        logger.error("[VIBER] Greška pri slanju: %s", exc)
        return False


# ─── Viber webhook (javni endpoint, bez auth) ─────────────────────────────────

@router.post("/viber/webhook")
async def viber_webhook(request: Request):
    """
    Viber šalje sve webhook evente ovde.
    Subscribe event → belezi viber_user_id za matching korisnika po emailu.
    """
    body = await request.body()
    signature = request.headers.get("X-Viber-Content-Signature", "")

    if _viber_configured() and not _verify_viber_signature(body, signature):
        logger.warning("[VIBER] Neispravan potpis webhook-a")
        return Response(content=json.dumps({"status": 0}), media_type="application/json")

    try:
        event = json.loads(body)
    except Exception:
        return Response(content=json.dumps({"status": 0}), media_type="application/json")

    event_type = event.get("event")
    logger.info("[VIBER] Webhook event: %s", event_type)

    if event_type in ("subscribed", "conversation_started"):
        sender = event.get("sender") or event.get("user") or {}
        viber_uid  = sender.get("id", "")
        viber_name = sender.get("name", "")

        if viber_uid:
            supa = _get_supa()
            try:
                await asyncio.to_thread(
                    lambda: supa.table("korisnik_viber_profil").upsert({
                        "viber_user_id": viber_uid,
                        "viber_name":    viber_name,
                        "aktivan":       True,
                    }, on_conflict="viber_user_id").execute()
                )
                logger.info("[VIBER] Pretplaćen: viber_id=%s name=%s", viber_uid[:8], viber_name)
            except Exception as e:
                logger.error("[VIBER] Greška pri snimanju pretplate: %s", e)

        if event_type == "conversation_started":
            welcome = (
                f"Dobrodošli u Vindex AI bot!\n\n"
                "Ovde ćete primati:\n"
                "• Jutarnji izveštaj sa vašim predmetima\n"
                "• Podsetnike za hitne rokove\n"
                "• Obaveštenja o ročištima\n\n"
                "Povežite vaš nalog na vindex.rs/app → Podešavanja → Viber."
            )
            await _viber_send(viber_uid, welcome)

    elif event_type == "message":
        sender = event.get("sender", {})
        viber_uid = sender.get("id", "")
        text = (event.get("message", {}) or {}).get("text", "").strip().lower()
        if viber_uid:
            if "help" in text or "pomoc" in text or "pomoć" in text:
                await _viber_send(viber_uid, "Possetite vindex.rs/app za puni pristup. Za tehničku podršku: support@vindex.rs")
            elif text in ("hi", "zdravo", "bok", "cao", "čao"):
                await _viber_send(viber_uid, "Zdravo! Koristite vindex.rs/app za puni pristup Vindex AI platformi.")

    return Response(content=json.dumps({"status": 0}), media_type="application/json")


# ─── Konfiguracija webhook-a na Viber (admin poziva jednom) ──────────────────

@router.post("/api/viber/setup-webhook")
async def viber_setup_webhook(request: Request, user: dict = Depends(get_current_user)):
    """Registruje webhook URL na Viber API. Poziva se jednom pri deploymentu."""
    email = user.get("email", "").lower()
    if email not in _FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Restricted.")

    if not _viber_configured():
        raise HTTPException(status_code=503, detail="VIBER_AUTH_TOKEN nije konfigurisan.")

    app_url = os.getenv("APP_BASE_URL", "https://vindex.rs")
    webhook_url = f"{app_url}/viber/webhook"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_VIBER_API}/set_webhook",
                json={"url": webhook_url, "event_types": ["subscribed", "conversation_started", "message"]},
                headers=_viber_headers(),
            )
            data = resp.json()
        if data.get("status") == 0:
            return {"ok": True, "webhook_url": webhook_url, "viber_response": data}
        raise HTTPException(status_code=502, detail=f"Viber greška: {data.get('status_message')}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Status i profil ──────────────────────────────────────────────────────────

@router.get("/api/viber/status")
async def viber_status():
    """Da li je Viber bot konfigurisan."""
    bot_uri = os.getenv("VIBER_BOT_URI", "")
    return {
        "konfigurisan": _viber_configured(),
        "bot_uri":      bot_uri,
        "bot_name":     os.getenv("VIBER_BOT_NAME", "Vindex AI"),
    }


@router.post("/api/viber/povezi-nalog")
@limiter.limit("5/minute")
async def povezi_viber_nalog(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Korisnik unosi svoj Viber ID (ili ga bot automatski beleži).
    Alternativni tok: korisnik ide na Viber bot link → automatska pretplata.
    """
    supa = _get_supa()
    uid  = user["user_id"]

    try:
        profil_r = await asyncio.to_thread(
            lambda: supa.table("korisnik_viber_profil")
                .select("viber_user_id,aktivan")
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        return profil_r.data or {"viber_user_id": None, "aktivan": False, "napomena": "Otvorite Viber bot link za pretplatu."}
    except Exception:
        return {"viber_user_id": None, "aktivan": False}


# ─── Test poruka ──────────────────────────────────────────────────────────────

@router.post("/api/viber/test")
@limiter.limit("3/minute")
async def viber_test(request: Request, user: dict = Depends(get_current_user)):
    """Šalje test Viber poruku korisniku koji je pretplaćen."""
    supa = _get_supa()
    uid  = user["user_id"]

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("korisnik_viber_profil")
                .select("viber_user_id,aktivan")
                .eq("user_id", uid)
                .eq("aktivan", True)
                .maybe_single()
                .execute()
        )
        profil = r.data
    except Exception:
        profil = None

    if not profil or not profil.get("viber_user_id"):
        raise HTTPException(status_code=422, detail="Viber nalog nije povezan. Otvorite Viber bot link.")

    ok = await _viber_send(profil["viber_user_id"], "Vindex AI ✓\nViber notifikacije su aktivne!")
    if not ok:
        raise HTTPException(status_code=503, detail="Viber poruka nije mogla biti poslata.")

    return {"ok": True}


# ─── Jutarnji briefing ────────────────────────────────────────────────────────

async def _briefing_tekst(uid: str, supa) -> str:
    """Generiše tekst jutarnjeg izveštaja za Viber."""
    today = date.today()
    today_s = today.isoformat()
    in_7d = (today + timedelta(days=7)).isoformat()

    predmeti_r, rokovi_r, rocista_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti").select("id").eq("user_id", uid).eq("status", "aktivan").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("dogadjaj,datum_iso").eq("user_id", uid).gte("datum_iso", today_s).lte("datum_iso", in_7d).eq("vaznost", "kritičan").order("datum_iso").limit(3).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select("naziv,datum").eq("user_id", uid).gte("datum", today_s).lte("datum", today_s).limit(3).execute()),
    )

    n_predmeta = len(predmeti_r.data or [])
    hitni = rokovi_r.data or []
    rocista = rocista_r.data or []

    linije = [f"Vindex AI - {today_s}", f"Aktivni predmeti: {n_predmeta}"]

    if rocista:
        linije.append("\nDanasnja rocista:")
        for r in rocista:
            linije.append(f"  • {r.get('naziv', 'Rociste')}")

    if hitni:
        linije.append("\nHitni rokovi (7 dana):")
        for rok in hitni:
            linije.append(f"  • {rok.get('dogadjaj', 'Rok')} - {rok.get('datum_iso', '')[:10]}")

    if not rocista and not hitni:
        linije.append("\nNema hitnih rokova danas.")

    linije.append("\nvindex.rs/app")
    return "\n".join(linije)


@router.post("/api/viber/send-briefing")
@limiter.limit("5/minute")
async def viber_send_briefing(request: Request, user: dict = Depends(get_current_user)):
    """Šalje jutarnji briefing korisniku via Viber."""
    supa = _get_supa()
    uid  = user["user_id"]

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("korisnik_viber_profil")
                .select("viber_user_id,aktivan")
                .eq("user_id", uid)
                .eq("aktivan", True)
                .maybe_single()
                .execute()
        )
        profil = r.data
    except Exception:
        profil = None

    if not profil or not profil.get("viber_user_id"):
        raise HTTPException(status_code=422, detail="Viber nalog nije povezan.")

    tekst = await _briefing_tekst(uid, supa)
    ok = await _viber_send(profil["viber_user_id"], tekst)

    if not ok:
        raise HTTPException(status_code=503, detail="Viber poruka nije mogla biti poslata.")

    return {"ok": True}


@router.post("/api/viber/cron-briefing")
@limiter.limit("3/minute")
async def viber_cron_briefing(request: Request, user: dict = Depends(get_current_user)):
    """
    Cron trigger — šalje jutarnji briefing svim Viber pretplatnicima.
    Samo founder. Cron: 0 6 * * 1-5 (8:00 Beograd).
    """
    email = user.get("email", "").lower()
    if email not in _FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Restricted.")

    if not _viber_configured():
        return {"poslato": 0, "napomena": "Viber nije konfigurisan."}

    supa = _get_supa()

    try:
        profili_r = await asyncio.to_thread(
            lambda: supa.table("korisnik_viber_profil")
                .select("user_id,viber_user_id")
                .eq("aktivan", True)
                .execute()
        )
        profili = profili_r.data or []
    except Exception as e:
        logger.error("[VIBER-CRON] Greška pri učitavanju profila: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri učitavanju Viber profila.")

    poslato = 0
    greske  = 0
    for p in profili:
        uid       = p.get("user_id", "")
        viber_uid = p.get("viber_user_id", "")
        if not uid or not viber_uid:
            continue
        try:
            tekst = await _briefing_tekst(uid, supa)
            ok    = await _viber_send(viber_uid, tekst)
            if ok:
                poslato += 1
            else:
                greske += 1
        except Exception as ex:
            logger.error("[VIBER-CRON] Greška za user %s: %s", uid[:8], ex)
            greske += 1

    logger.info("[VIBER-CRON] Zavrseno: poslato=%d greske=%d", poslato, greske)
    return {"poslato": poslato, "greske": greske}
