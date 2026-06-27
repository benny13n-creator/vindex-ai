# -*- coding: utf-8 -*-
"""
Vindex AI — routers/integrations.py

Integration Hub: webhooks, Google Calendar, Zapier-ready outgoing eventi.

Endpoints:
  POST   /api/integrations/webhook/register   — registruj webhook URL
  GET    /api/integrations/webhooks           — lista webhookova
  DELETE /api/integrations/webhook/{id}       — ukloni webhook
  POST   /api/integrations/webhook/test/{id}  — test ping webhook-a
  GET    /api/integrations/gcal/auth-url      — generiši Google OAuth URL
  POST   /api/integrations/gcal/callback      — razmeni code za token
  POST   /api/integrations/gcal/sync-rokovi   — exportuj rokove u GCal
  GET    /api/integrations/events             — lista outgoing event tipova
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import urllib.parse
from datetime import datetime, date, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.integrations")
router = APIRouter(tags=["integrations"])

GCAL_CLIENT_ID     = os.getenv("GCAL_CLIENT_ID", "")
GCAL_CLIENT_SECRET = os.getenv("GCAL_CLIENT_SECRET", "")
GCAL_REDIRECT_URI  = os.getenv(
    "GCAL_REDIRECT_URI",
    "https://vindex-ai.onrender.com/api/integrations/gcal/callback",
)


# ─── Modeli ──────────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    url: str
    eventi: list[str] = ["sve"]  # "novi_predmet", "novi_rok", "nova_faktura", "sve"
    naziv: Optional[str] = None


# ─── Webhook CRUD ─────────────────────────────────────────────────────────────

@router.post("/api/integrations/webhook/register")
@limiter.limit("10/minute")
async def register_webhook(
    request: Request,
    payload: WebhookCreate,
    user: dict = Depends(get_current_user),
):
    """Registruj webhook URL za Vindex AI evenimente."""
    uid = user["user_id"]
    supa = _get_supa()

    if not payload.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook URL mora koristiti HTTPS.")

    existing = await asyncio.to_thread(
        lambda: supa.table("webhooks").select("id").eq("user_id", uid).execute()
    )
    if len(existing.data or []) >= 5:
        raise HTTPException(status_code=400, detail="Maksimum 5 webhookova je dozvoljeno.")

    wh_secret = secrets.token_hex(32)

    result = await asyncio.to_thread(
        lambda: supa.table("webhooks").insert({
            "user_id": uid,
            "url":     payload.url,
            "eventi":  payload.eventi,
            "naziv":   payload.naziv or payload.url[:50],
            "secret":  wh_secret,
            "aktivan": True,
        }).execute()
    )

    webhook_id = result.data[0]["id"] if result.data else None

    return {
        "ok":         True,
        "webhook_id": webhook_id,
        "secret":     wh_secret,
        "napomena":   "Sacuvajte secret — bice koriscen za verifikaciju X-Vindex-Signature zaglavlja.",
    }


@router.get("/api/integrations/webhooks")
async def list_webhooks(user: dict = Depends(get_current_user)):
    """Lista svih webhook-ova korisnika."""
    uid = user["user_id"]
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("webhooks")
            .select("id, url, naziv, eventi, aktivan, created_at")
            .eq("user_id", uid)
            .execute()
    )
    return {"webhooks": r.data or []}


@router.delete("/api/integrations/webhook/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    user: dict = Depends(get_current_user),
):
    """Ukloni webhook."""
    uid = user["user_id"]
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("webhooks").delete().eq("id", webhook_id).eq("user_id", uid).execute()
    )
    return {"ok": True}


@router.post("/api/integrations/webhook/test/{webhook_id}")
@limiter.limit("5/minute")
async def test_webhook(
    request: Request,
    webhook_id: str,
    user: dict = Depends(get_current_user),
):
    """Posalje test ping na webhook URL."""
    uid = user["user_id"]
    supa = _get_supa()

    r = await asyncio.to_thread(
        lambda: supa.table("webhooks")
            .select("url, secret")
            .eq("id", webhook_id)
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Webhook nije pronađen.")

    test_payload = {
        "event":     "test",
        "message":   "Vindex AI webhook test ping",
        "timestamp": datetime.utcnow().isoformat(),
    }
    body = json.dumps(test_payload)
    sig  = hmac.new(r.data["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                r.data["url"],
                content=body,
                headers={
                    "Content-Type":       "application/json",
                    "X-Vindex-Signature": f"sha256={sig}",
                    "X-Vindex-Event":     "test",
                },
            )
        return {"ok": True, "status_code": resp.status_code, "response": resp.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Outgoing webhook helper ──────────────────────────────────────────────────

async def trigger_webhook(user_id: str, event: str, data: dict) -> None:
    """Fire-and-forget: salje event na sve aktivne webhookove korisnika."""
    try:
        supa = _get_supa()
        webhooks_r = await asyncio.to_thread(
            lambda: supa.table("webhooks")
                .select("url, secret, eventi")
                .eq("user_id", user_id)
                .eq("aktivan", True)
                .execute()
        )
        if not webhooks_r.data:
            return

        payload_obj = {
            "event":     event,
            "data":      data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        body = json.dumps(payload_obj)

        async with httpx.AsyncClient(timeout=8) as client:
            for wh in webhooks_r.data:
                if "sve" not in wh.get("eventi", []) and event not in wh.get("eventi", []):
                    continue
                try:
                    sig = hmac.new(
                        wh["secret"].encode(), body.encode(), hashlib.sha256
                    ).hexdigest()
                    await client.post(
                        wh["url"],
                        content=body,
                        headers={
                            "Content-Type":       "application/json",
                            "X-Vindex-Signature": f"sha256={sig}",
                            "X-Vindex-Event":     event,
                        },
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Webhook trigger greška: %s", e)


# ─── Google Calendar ──────────────────────────────────────────────────────────

@router.get("/api/integrations/gcal/auth-url")
async def gcal_auth_url(user: dict = Depends(get_current_user)):
    """Generisi Google OAuth2 URL za Google Calendar."""
    if not GCAL_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google Calendar integracija nije konfigurisana. Podesite GCAL_CLIENT_ID env var.",
        )

    params = {
        "client_id":     GCAL_CLIENT_ID,
        "redirect_uri":  GCAL_REDIRECT_URI,
        "response_type": "code",
        "scope":         "https://www.googleapis.com/auth/calendar.events",
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         user["user_id"],
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return {"auth_url": url}


@router.post("/api/integrations/gcal/callback")
async def gcal_callback(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """Razmeni authorization code za access+refresh token."""
    code = payload.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Code je obavezan.")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code":          code,
                    "client_id":     GCAL_CLIENT_ID,
                    "client_secret": GCAL_CLIENT_SECRET,
                    "redirect_uri":  GCAL_REDIRECT_URI,
                    "grant_type":    "authorization_code",
                },
            )
            token_data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth greška: {e}")

    if "error" in token_data:
        raise HTTPException(
            status_code=400,
            detail=token_data.get("error_description", "OAuth greška"),
        )

    uid  = user["user_id"]
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("integracije").upsert({
            "user_id":       uid,
            "tip":           "google_calendar",
            "access_token":  token_data.get("access_token", ""),
            "refresh_token": token_data.get("refresh_token", ""),
            "aktivan":       True,
        }, on_conflict="user_id,tip").execute()
    )

    return {"ok": True, "message": "Google Calendar je uspesno povezan."}


@router.post("/api/integrations/gcal/sync-rokovi")
@limiter.limit("10/minute")
async def gcal_sync_rokovi(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Exportuj sve aktivne rokove u Google Calendar."""
    uid  = user["user_id"]
    supa = _get_supa()

    tok_r = await asyncio.to_thread(
        lambda: supa.table("integracije")
            .select("access_token, refresh_token")
            .eq("user_id", uid)
            .eq("tip", "google_calendar")
            .maybe_single()
            .execute()
    )
    if not tok_r.data or not tok_r.data.get("access_token"):
        raise HTTPException(
            status_code=400,
            detail="Google Calendar nije povezan. Prvo autorizujte pristup putem /api/integrations/gcal/auth-url.",
        )

    access_token = tok_r.data["access_token"]

    rokovi_r = await asyncio.to_thread(
        lambda: supa.table("rokovi")
            .select("naziv, datum, opis, predmet_id")
            .eq("user_id", uid)
            .gte("datum", date.today().isoformat())
            .limit(50)
            .execute()
    )

    synced = 0
    errors = 0

    async with httpx.AsyncClient() as client:
        for rok in (rokovi_r.data or []):
            try:
                event_body = {
                    "summary":     f"[Vindex] {rok.get('naziv', 'Rok')}",
                    "description": rok.get("opis", ""),
                    "start":       {"date": str(rok["datum"])[:10]},
                    "end":         {"date": str(rok["datum"])[:10]},
                    "reminders": {
                        "useDefault": False,
                        "overrides": [{"method": "popup", "minutes": 1440}],
                    },
                }
                resp = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    json=event_body,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if resp.status_code in [200, 201]:
                    synced += 1
                else:
                    errors += 1
                    logger.debug("GCal event greška %s: %s", resp.status_code, resp.text[:200])
            except Exception as e:
                errors += 1
                logger.debug("GCal sync greška: %s", e)

    return {"synced": synced, "errors": errors, "total": len(rokovi_r.data or [])}


# ─── Event tipovi ─────────────────────────────────────────────────────────────

@router.get("/api/integrations/events")
async def get_event_types(user: dict = Depends(get_current_user)):
    """Lista svih event tipova koje Vindex salje na webhookove."""
    return {
        "eventi": [
            {"kod": "novi_predmet",    "naziv": "Novi predmet kreiran"},
            {"kod": "novi_klijent",    "naziv": "Novi klijent dodat"},
            {"kod": "novi_rok",        "naziv": "Novi rok ili rociste"},
            {"kod": "nova_faktura",    "naziv": "Faktura kreirana"},
            {"kod": "ai_analiza",      "naziv": "AI analiza zavrsena"},
            {"kod": "dokument_upload", "naziv": "Dokument uploadovan"},
            {"kod": "sve",             "naziv": "Svi eventi"},
        ]
    }
