# -*- coding: utf-8 -*-
"""
Vindex AI — routers/agent_notifications.py

KORAK B: Autonomni "Background" Action Agenti (2026-07-24)

Feed proaktivnih preporuka koje su generisali pozadinski agenti
(services/agent_tasks/court_portal_watcher.py, precedents_radar.py) preko
workers/background_agents.py. Advokat pregleda, prihvata ili odbacuje --
agenti NIKAD ne izvršavaju akcije direktno (Human-in-the-Loop, isti princip
kao services/voice_orchestrator.py's mutates_data gate).

Endpoints:
  GET  /api/agent-notifications              — lista preporuka (default: pending)
  POST /api/agent-notifications/{id}/accept   — prihvati preporuku
  POST /api/agent-notifications/{id}/reject   — odbaci preporuku
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.agent_notifications")
router = APIRouter(prefix="/api/agent-notifications", tags=["agent-notifications"])

_VALID_STATUSES = {"pending", "accepted", "rejected"}


@router.get("")
@limiter.limit("30/minute")
async def lista_preporuka(
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
            lambda: supa.table("agent_recommendations")
                .select("*")
                .eq("user_id", user["user_id"])
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
        )
        return {"preporuke": r.data or [], "ukupno": len(r.data or [])}
    except Exception as e:
        logger.error("[AGENT_NOTIF] lista greška uid=%.8s: %s", user["user_id"][:8], e)
        raise HTTPException(status_code=500, detail="Greška pri učitavanju preporuka.")


async def _resolve(preporuka_id: str, user: dict, novi_status: str) -> dict:
    supa = _get_supa()

    # Ownership check + trenutni status u istom upitu -- samo sopstvene,
    # samo PENDING preporuke mogu biti rešene (sprečava dupli
    # accept/reject na već rešenoj preporuci).
    try:
        existing = await asyncio.to_thread(
            lambda: supa.table("agent_recommendations")
                .select("id,status")
                .eq("id", preporuka_id)
                .eq("user_id", user["user_id"])
                .maybe_single()
                .execute()
        )
    except Exception as e:
        logger.error("[AGENT_NOTIF] provera vlasništva greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška na serveru.")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Preporuka nije pronađena.")
    if existing.data.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Preporuka je već rešena.")

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("agent_recommendations")
                .update({
                    "status": novi_status,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", preporuka_id)
                .eq("user_id", user["user_id"])
                .execute()
        )
    except Exception as e:
        logger.error("[AGENT_NOTIF] update greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju preporuke.")

    updated = (r.data or [{}])[0]
    return {"ok": True, "preporuka": updated}


@router.post("/{preporuka_id}/accept")
@limiter.limit("30/minute")
async def prihvati_preporuku(preporuka_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _resolve(preporuka_id, user, "accepted")


@router.post("/{preporuka_id}/reject")
@limiter.limit("30/minute")
async def odbaci_preporuku(preporuka_id: str, request: Request, user: dict = Depends(get_current_user)):
    return await _resolve(preporuka_id, user, "rejected")
