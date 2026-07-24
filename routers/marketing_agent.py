# -*- coding: utf-8 -*-
"""
Vindex AI — routers/marketing_agent.py

KORAK D: Legal Thought Leadership & Content Agent (2026-07-24)

Endpoints:
  POST /api/marketing/generate               — generiši nov nacrt (javna sudska
                                                praksa ili zakonska izmena)
  GET  /api/marketing/drafts                  — lista sopstvenih nacrta
  POST /api/marketing/drafts/{id}/accept       — HITL odobrenje
  POST /api/marketing/drafts/{id}/reject       — HITL odbacivanje
  GET  /api/marketing/drafts/{id}/format       — prikaz formata za platformu
                                                (SAMO za već prihvaćene nacrte
                                                — v. shared/social_connectors.py,
                                                nema stvarnog slanja nigde)

Human-in-the-Loop je STROG ovde: nijedan nacrt se ne može formatirati za
eksternu platformu (ni prikaz formata, a kamoli slanje) pre eksplicitnog
accept-a. Generisanje samo kreira PENDING nacrt.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.marketing_agent")
router = APIRouter(prefix="/api/marketing", tags=["marketing-agent"])

_VALID_IZVOR_TIPOVI = {"sudska_praksa", "zakonska_izmena"}
_VALID_PLATFORME = {"linkedin", "blog"}
_VALID_STATUSES = {"pending", "accepted", "rejected"}


class GenerateReq(BaseModel):
    izvor_tip: str = Field(..., description="'sudska_praksa' ili 'zakonska_izmena'")
    platforma: str = Field(..., description="'linkedin' ili 'blog'")
    oblast_prava: str | None = Field(default=None, max_length=100)


@router.post("/generate")
@limiter.limit("10/minute")
async def generisi_nacrt(
    req: GenerateReq,
    request: Request,
    user: dict = Depends(PermissionService.require("marketing_agent")),
):
    if req.izvor_tip not in _VALID_IZVOR_TIPOVI:
        raise HTTPException(status_code=400, detail=f"Nevažeći izvor_tip. Dostupno: {', '.join(_VALID_IZVOR_TIPOVI)}")
    if req.platforma not in _VALID_PLATFORME:
        raise HTTPException(status_code=400, detail=f"Nevažeća platforma. Dostupno: {', '.join(_VALID_PLATFORME)}")

    uid = user["user_id"]
    supa = _get_supa()

    from services.content_generator import generate_post
    rezultat = await generate_post(req.izvor_tip, req.oblast_prava, req.platforma, uid, supa)

    if not rezultat["ok"]:
        raise HTTPException(status_code=422, detail=rezultat["error"] or "Generisanje nije uspelo.")

    # krediti se troše samo na USPEŠNO generisanje (isti obrazac kao
    # /api/nacrt) -- neuspeh (nema javnog materijala, LLM greška) ne troši budžet.
    await UsageService.consume(uid, user.get("email", ""), "marketing_agent")

    return {"draft": rezultat["draft"]}


@router.get("/drafts")
@limiter.limit("30/minute")
async def lista_nacrta(
    request: Request,
    user: dict = Depends(get_current_user),
    status: str = "pending",
    limit: int = 50,
):
    if status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Nevažeći status. Dostupno: {', '.join(_VALID_STATUSES)}")
    limit = min(max(limit, 1), 200)
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("marketing_content_drafts")
                .select("*")
                .eq("user_id", user["user_id"])
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
        )
        return {"nacrti": r.data or [], "ukupno": len(r.data or [])}
    except Exception as e:
        logger.error("[MARKETING] lista greška uid=%.8s: %s", user["user_id"][:8], e)
        raise HTTPException(status_code=500, detail="Greška pri učitavanju nacrta.")


async def _fetch_own_draft(draft_id: str, user_id: str) -> dict:
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("marketing_content_drafts")
            .select("*")
            .eq("id", draft_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Nacrt nije pronađen.")
    return r.data


async def _resolve(draft_id: str, user: dict, novi_status: str) -> dict:
    from datetime import datetime, timezone
    supa = _get_supa()

    existing = await _fetch_own_draft(draft_id, user["user_id"])
    if existing.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Nacrt je već rešen.")

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("marketing_content_drafts")
                .update({"status": novi_status, "resolved_at": datetime.now(timezone.utc).isoformat()})
                .eq("id", draft_id)
                .eq("user_id", user["user_id"])
                .execute()
        )
    except Exception as e:
        logger.error("[MARKETING] update greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju nacrta.")

    return {"ok": True, "nacrt": (r.data or [{}])[0]}


@router.post("/drafts/{draft_id}/accept")
@limiter.limit("30/minute")
async def prihvati_nacrt(draft_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _resolve(draft_id, user, "accepted")


@router.post("/drafts/{draft_id}/reject")
@limiter.limit("30/minute")
async def odbaci_nacrt(draft_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _resolve(draft_id, user, "rejected")


@router.get("/drafts/{draft_id}/format")
@limiter.limit("30/minute")
async def format_nacrta(draft_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Prikaz formata za ciljnu platformu -- SAMO za već PRIHVAĆENE nacrte.
    Nema slanja nigde u ovom pozivu (v. shared/social_connectors.py)."""
    draft = await _fetch_own_draft(draft_id, user["user_id"])
    if draft.get("status") != "accepted":
        raise HTTPException(status_code=409, detail="Format je dostupan samo za prihvaćene nacrte.")

    from shared.social_connectors import format_draft
    try:
        formatiran = format_draft(draft["platforma"], draft.get("naslov") or "", draft["tekst"], draft.get("izvor_opis"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return formatiran
