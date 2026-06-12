# -*- coding: utf-8 -*-
"""
Vindex AI — routers/push.py

F6.4: Web Push notifikacije (VAPID).
"""
import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user

router = APIRouter()

_VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY", "")
_VAPID_PUBLIC  = os.getenv("VAPID_PUBLIC_KEY", "")
_VAPID_EMAIL   = os.getenv("VAPID_CLAIMS_EMAIL", "info@vindex.rs")


def _vapid_pem_from_der_b64(der_b64: str) -> str:
    """Konvertuje DER base64 private key u PEM string za pywebpush."""
    import base64
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, NoEncryption, load_der_private_key
    )
    der = base64.urlsafe_b64decode(der_b64 + "==")
    return load_der_private_key(der, None).private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    ).decode("utf-8")


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh:   str
    auth:     str


@router.get("/push/vapid-public")  # F6.4 — bez auth (browser treba ovo)
async def get_vapid_public():
    """F6.4 — Vraća VAPID public key za browser pushManager.subscribe."""
    if not _VAPID_PUBLIC:
        raise HTTPException(status_code=503, detail="Push notifikacije nisu konfigurisane.")
    return {"public_key": _VAPID_PUBLIC}


@router.post("/push/subscribe")  # F6.4
async def post_push_subscribe(req: PushSubscribeRequest, user: dict = Depends(get_current_user)):
    """F6.4 — Registruje push subscription za korisnika."""
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("push_subscriptions").upsert({
                "user_id":  user["user_id"],
                "endpoint": req.endpoint,
                "p256dh":   req.p256dh,
                "auth":     req.auth,
            }, on_conflict="endpoint").execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "pretplaćen"}


@router.post("/push/test")  # F6.4
async def post_push_test(user: dict = Depends(get_current_user)):
    """F6.4 — Test push notifikacija za prijavljenog korisnika."""
    import json
    if not _VAPID_PRIVATE:
        return {"status": "VAPID ključevi nisu podešeni na serveru"}
    supa = _get_supa()
    subs = await asyncio.to_thread(
        lambda: supa.table("push_subscriptions")
                    .select("endpoint, p256dh, auth")
                    .eq("user_id", user["user_id"])
                    .execute()
    )
    if not subs.data:
        return {"status": "nema aktivnih push pretplata"}
    from pywebpush import webpush, WebPushException
    pem = _vapid_pem_from_der_b64(_VAPID_PRIVATE)
    uspešno = 0
    for sub in subs.data:
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=json.dumps({
                    "title": "Vindex AI — Test",
                    "body":  "Push notifikacije rade ispravno ✓",
                    "url":   "/app",
                }),
                vapid_private_key=pem,
                vapid_claims={"sub": f"mailto:{_VAPID_EMAIL}"},
            )
            uspešno += 1
        except WebPushException as e:
            if e.response and e.response.status_code == 410:
                await asyncio.to_thread(
                    lambda: supa.table("push_subscriptions")
                                .delete()
                                .eq("endpoint", sub["endpoint"])
                                .execute()
                )
    return {"status": f"{uspešno}/{len(subs.data)} notifikacija poslato"}
