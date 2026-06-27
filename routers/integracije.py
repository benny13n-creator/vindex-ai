# -*- coding: utf-8 -*-
"""
Vindex AI — routers/integracije.py

Phase 5.5: API za spoljne integracije (Clio, iManage).
Svi /v1/* endpointi — autentifikacija via X-Vindex-Key header (API ključ).
Webhook endpointi za Clio i iManage — HMAC/shared-secret validacija.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.integracije")
router = APIRouter(tags=["integracije"])

_API_DAILY_LIMIT = int(os.getenv("API_KEY_DAILY_LIMIT", "500"))


# ─── API key resolver ─────────────────────────────────────────────────────────

async def _resolve_key(request: Request) -> dict:
    """Extract X-Vindex-Key, validate against api_kljucevi, return row."""
    api_key = (
        request.headers.get("X-Vindex-Key")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    if not api_key or not api_key.startswith("vndx_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API ključ je obavezan. Pošaljite: X-Vindex-Key: vndx_...",
        )

    supa = _get_supa()
    try:
        res = await asyncio.to_thread(
            lambda: supa.table("api_kljucevi")
                         .select("id, user_id, aktivan, naziv, broj_poziva")
                         .eq("kljuc", api_key)
                         .eq("aktivan", True)
                         .execute()
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Servis privremeno nedostupan.")

    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nevažeći ili neaktivni API ključ.",
        )

    row = res.data[0]
    if row.get("broj_poziva", 0) >= _API_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Dnevni limit API poziva ({_API_DAILY_LIMIT}) je dostignut.",
        )

    try:
        await asyncio.to_thread(
            lambda: supa.table("api_kljucevi")
                         .update({
                             "broj_poziva":          row.get("broj_poziva", 0) + 1,
                             "poslednje_koriscenje": datetime.now(timezone.utc).isoformat(),
                         })
                         .eq("id", row["id"])
                         .execute()
        )
    except Exception:
        pass

    return row


# ─── Patchable wrappers ───────────────────────────────────────────────────────

def _retrieve(pitanje: str, k: int = 8):
    from app.services.retrieve import retrieve_documents
    return retrieve_documents(pitanje, k=k)


def _gpt_analyze(system_prompt: str, user_content: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=1500,
        messages=[
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": user_content},
        ],
    )
    return resp.choices[0].message.content.strip()


_SYSTEM_PROMPT_V1 = """Ti si Vindex AI — srpski pravni asistent.
Odgovaraj na srpskom jeziku. Citiraš zakone i sudsku praksu.
Ako nisi siguran, jasno to naznači. Nikada ne generiši lažne zakone ili presude.
Odgovor strukturiraj: PRAVNI OSNOV | ANALIZA | ZAKLJUČAK"""


def _run_analyze_sync(pitanje: str) -> dict[str, Any]:
    docs, meta = _retrieve(pitanje)
    confidence = meta.get("confidence", "LOW")

    if confidence == "LOW" or not docs:
        return {
            "odgovor":    "Nisam pronašao dovoljno relevantnih pravnih izvora za ovo pitanje.",
            "confidence": "LOW",
            "top_score":  meta.get("top_score", 0.0),
        }

    context = "\n\n".join(docs[:5])
    hedge = "[UMERENA POUZDANOST] " if confidence == "MEDIUM" else ""
    user_content = (
        f"{hedge}PITANJE: {pitanje}\n\n"
        f"RELEVANTNI PRAVNI TEKSTOVI:\n{context}"
    )
    odgovor = _gpt_analyze(_SYSTEM_PROMPT_V1, user_content)
    return {
        "odgovor":     odgovor,
        "confidence":  confidence,
        "top_score":   meta.get("top_score", 0.0),
        "top_article": meta.get("top_article"),
        "top_law":     meta.get("top_law"),
    }


# ─── Webhook helpers ──────────────────────────────────────────────────────────

def _verify_clio_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """Validate Clio HMAC-SHA256 signature: sha256=<hex>."""
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def _verify_imanage_token(token_header: str, secret: str) -> bool:
    return hmac.compare_digest(token_header, secret)


# ─── Request models ───────────────────────────────────────────────────────────

class AnalyzeReq(BaseModel):
    pitanje: str = Field(..., min_length=5, max_length=2000)


class PredmetCreateReq(BaseModel):
    naziv:  str           = Field(..., min_length=1, max_length=200)
    opis:   Optional[str] = Field(default=None, max_length=2000)
    tip:    str           = Field(default="opsti", max_length=50)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/v1/health")
async def get_v1_health():
    """Phase 5.5 — Health check za eksterne integracije (bez autentifikacije)."""
    return {
        "status":  "ok",
        "version": "1.0",
        "service": "Vindex AI External API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/v1/analyze")
@limiter.limit("30/minute")
async def post_v1_analyze(request: Request, req: AnalyzeReq):
    """Phase 5.5 — AI pravna analiza via API ključ."""
    await _resolve_key(request)

    try:
        result = await asyncio.to_thread(_run_analyze_sync, req.pitanje)
    except Exception as exc:
        logger.error("v1/analyze error: %s", exc)
        raise HTTPException(status_code=503, detail="Greška u analizi — pokušajte ponovo.")

    return {
        "pitanje":    req.pitanje,
        "odgovor":    result["odgovor"],
        "confidence": result["confidence"],
        "top_score":  result.get("top_score"),
        "top_article":result.get("top_article"),
        "top_law":    result.get("top_law"),
        "napomena":   "⚠️ Vindex AI ne zamenjuje pravnog savetnika.",
    }


@router.get("/v1/predmeti")
@limiter.limit("60/minute")
async def get_v1_predmeti(request: Request):
    """Phase 5.5 — Lista predmeta za API ključ vlasnika (max 50)."""
    key_row = await _resolve_key(request)
    supa    = _get_supa()

    result = await asyncio.to_thread(
        lambda: supa.table("predmeti")
                     .select("id, naziv, tip, status, created_at, updated_at")
                     .eq("user_id", key_row["user_id"])
                     .order("created_at", desc=True)
                     .limit(50)
                     .execute()
    )
    return {"predmeti": result.data or [], "total": len(result.data or [])}


@router.post("/v1/predmeti", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def post_v1_predmeti(request: Request, req: PredmetCreateReq):
    """Phase 5.5 — Kreiranje predmeta via API ključ."""
    key_row = await _resolve_key(request)
    supa    = _get_supa()

    result = await asyncio.to_thread(
        lambda: supa.table("predmeti").insert({
            "user_id": key_row["user_id"],
            "naziv":   req.naziv,
            "opis":    req.opis,
            "tip":     req.tip,
            "status":  "aktivan",
        }).execute()
    )
    new_pred = result.data[0] if result.data else {}
    return {"predmet": new_pred, "status": "kreiran"}


@router.post("/v1/webhook/clio")
@limiter.limit("100/minute")
async def post_webhook_clio(request: Request):
    """
    Phase 5.5 — Clio matter webhook.
    Validira HMAC-SHA256 potpis (X-Clio-Signature), kreira predmet iz Clio mattera.
    Requires: CLIO_WEBHOOK_SECRET env var.
    """
    secret = os.getenv("CLIO_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Clio integracija nije konfigurisana.")

    body      = await request.body()
    signature = request.headers.get("X-Clio-Signature", "")
    if not _verify_clio_signature(body, signature, secret):
        raise HTTPException(status_code=401, detail="Neispravan Clio potpis.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Neispravan JSON payload.")

    matter = payload.get("matter") or payload
    naziv  = matter.get("display_number") or matter.get("description") or "Clio predmet"
    opis   = matter.get("description") or ""

    user_id = payload.get("vindex_user_id") or os.getenv("CLIO_DEFAULT_USER_ID", "")
    if not user_id:
        return {"status": "primljeno", "napomena": "vindex_user_id nije definisan — predmet nije kreiran."}

    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("predmeti").insert({
            "user_id": user_id,
            "naziv":   naziv[:200],
            "opis":    opis[:2000],
            "tip":     "clio_import",
            "status":  "aktivan",
        }).execute()
    )

    logger.info("Clio webhook: kreiran predmet '%s' za user_id=%s", naziv, user_id)
    return {"status": "ok", "kreiran_predmet": naziv}


@router.post("/v1/webhook/imanage")
@limiter.limit("100/minute")
async def post_webhook_imanage(request: Request):
    """
    Phase 5.5 — iManage document webhook.
    Validira shared-secret token (X-IManage-Token), beleži dolazni dokument.
    Requires: IMANAGE_WEBHOOK_SECRET env var.
    """
    secret = os.getenv("IMANAGE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="iManage integracija nije konfigurisana.")

    token = request.headers.get("X-IManage-Token", "")
    if not _verify_imanage_token(token, secret):
        raise HTTPException(status_code=401, detail="Neispravan iManage token.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Neispravan JSON payload.")

    event_type = payload.get("event_type") or "document.created"
    doc_name   = payload.get("document", {}).get("name") or "Bez naziva"
    doc_id     = payload.get("document", {}).get("id") or ""

    logger.info("iManage webhook: event=%s doc='%s' id=%s", event_type, doc_name, doc_id)
    return {
        "status":     "primljeno",
        "event_type": event_type,
        "dokument":   doc_name,
        "napomena":   "Dokument je evidentiran u Vindex AI.",
    }


# ─── F3.7: Korisnički webhook sistem ─────────────────────────────────────────

_DOZVOLJENI_EVENTI = {
    "predmet.kreiran", "predmet.zatvoren", "rok.istice",
    "faktura.izdata",  "faktura.placena",  "klijent.dodat", "dokument.uploadovan",
}


class WebhookReq(BaseModel):
    url:    str            = Field(..., min_length=10, max_length=500)
    events: List[str]      = Field(..., min_length=1)
    secret: Optional[str] = Field(default=None, max_length=64)
    naziv:  Optional[str] = Field(default=None, max_length=100)


def _slanje_webhook_sync(url: str, payload: str, secret: Optional[str]) -> None:
    headers = {"Content-Type": "application/json"}
    if secret:
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        headers["X-Vindex-Signature"] = f"sha256={sig}"
    req_obj = urllib.request.Request(url, data=payload.encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req_obj, timeout=10) as resp:
            logger.debug("Webhook isporucen url=%s status=%s", url, resp.status)
    except Exception as exc:
        logger.warning("Webhook greška url=%s: %s", url, exc)


async def trigger_webhook(event: str, user_id: str, data: dict) -> None:
    """Šalje webhook notifikaciju svim aktivnim registrovanim endpointima."""
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("user_webhooks")
                .select("url,secret,events")
                .eq("user_id", user_id)
                .eq("aktivan", True)
                .execute()
        )
        hookovi = [w for w in (r.data or []) if event in (w.get("events") or [])]
        if not hookovi:
            return
        ts = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"event": event, "timestamp": ts, "data": data}, ensure_ascii=False)
        for wh in hookovi:
            await asyncio.to_thread(_slanje_webhook_sync, wh["url"], payload, wh.get("secret"))
    except Exception as exc:
        logger.warning("trigger_webhook greška: %s", exc)


@router.post("/api/webhooks")
@limiter.limit("20/minute")
async def webhook_registruj(
    body: WebhookReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    eventi = [e for e in body.events if e in _DOZVOLJENI_EVENTI]
    if not eventi:
        raise HTTPException(status_code=400, detail=f"Nijedan validan event. Dozvoljeni: {sorted(_DOZVOLJENI_EVENTI)}")

    count_r = await asyncio.to_thread(
        lambda: supa.table("user_webhooks").select("id", count="exact").eq("user_id", uid).eq("aktivan", True).execute()
    )
    if (count_r.count or 0) >= 5:
        raise HTTPException(status_code=400, detail="Dostignut limit od 5 webhook-a po korisniku.")

    r = await asyncio.to_thread(
        lambda: supa.table("user_webhooks").insert({
            "user_id": uid,
            "url":     body.url,
            "events":  eventi,
            "secret":  body.secret,
            "naziv":   body.naziv,
        }).execute()
    )
    return {"success": True, "webhook": r.data[0] if r.data else {}}


@router.get("/api/webhooks")
@limiter.limit("30/minute")
async def webhook_lista(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("user_webhooks").select("id,url,events,naziv,aktivan,created_at").eq("user_id", uid).order("created_at", desc=True).execute()
    )
    return {"webhooks": r.data or []}


@router.delete("/api/webhooks/{webhook_id}")
@limiter.limit("20/minute")
async def webhook_brisi(
    webhook_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("user_webhooks").delete().eq("id", webhook_id).eq("user_id", uid).execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Webhook nije pronađen.")
    return {"success": True, "id": webhook_id}


@router.post("/api/webhooks/test/{webhook_id}")
@limiter.limit("10/minute")
async def webhook_test(
    webhook_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("user_webhooks").select("*").eq("id", webhook_id).eq("user_id", uid).maybe_single().execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Webhook nije pronađen.")
    wh = r.data
    ts      = datetime.now(timezone.utc).isoformat()
    payload = json.dumps({"event": "test", "timestamp": ts, "data": {"message": "Vindex AI webhook test"}}, ensure_ascii=False)
    await asyncio.to_thread(_slanje_webhook_sync, wh["url"], payload, wh.get("secret"))
    return {"success": True, "url": wh["url"], "timestamp": ts}
