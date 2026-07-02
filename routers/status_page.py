# -*- coding: utf-8 -*-
"""
Status Page — javni health check endpoint + incident log.
GET /api/status/public   — bez autentifikacije
GET /api/status/incidents — lista incidenata (bez autentifikacije)
POST /api/status/incidents — kreira incident (samo founder)
"""
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.status")
router = APIRouter(prefix="/api/status", tags=["status"])

_FOUNDER_EMAILS = set(e.strip() for e in os.getenv("FOUNDER_EMAILS", "").split(",") if e.strip())


def _check_db(supa) -> dict:
    t0 = time.monotonic()
    try:
        supa.table("predmeti").select("id").limit(1).execute()
        ms = round((time.monotonic() - t0) * 1000)
        return {"status": "operational", "ms": ms}
    except Exception as e:
        return {"status": "degraded", "error": str(e)[:80]}


def _check_openai() -> dict:
    key = os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_KEY")
    return {"status": "operational" if key else "unknown"}


def _check_pinecone() -> dict:
    key = os.getenv("PINECONE_API_KEY")
    return {"status": "operational" if key else "unknown"}


@router.get("/public")
async def status_public():
    """Javni health check — bez autentifikacije."""
    supa = _get_supa()
    db = _check_db(supa)
    oai = _check_openai()
    pine = _check_pinecone()

    components = [
        {"naziv": "Baza podataka",    "status": db["status"],   "ms": db.get("ms")},
        {"naziv": "AI Engine",        "status": oai["status"]},
        {"naziv": "Pretraga dokumenata","status": pine["status"]},
        {"naziv": "API",              "status": "operational"},
    ]

    degraded = any(c["status"] not in ("operational", "unknown") for c in components)
    overall  = "degraded" if degraded else "operational"

    try:
        inc_r = supa.table("status_incidents").select(
            "id,title,severity,started_at,resolved_at,description"
        ).order("started_at", desc=True).limit(5).execute()
        incidents = inc_r.data or []
    except Exception:
        incidents = []

    return {
        "status":     overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
        "incidents":  incidents,
    }


@router.get("/incidents")
async def get_incidents():
    supa = _get_supa()
    try:
        r = supa.table("status_incidents").select("*").order("started_at", desc=True).limit(20).execute()
        return {"incidents": r.data or []}
    except Exception:
        return {"incidents": []}


class IncidentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    severity: str = "minor"  # minor | major | critical
    resolved: bool = False


@router.post("/incidents")
async def create_incident(body: IncidentCreate, user=Depends(get_current_user)):
    email = user.get("email", "")
    if email not in _FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Samo administratori mogu kreirati incidente.")
    supa = _get_supa()
    now  = datetime.now(timezone.utc).isoformat()
    row = {
        "title":       body.title,
        "description": body.description,
        "severity":    body.severity,
        "started_at":  now,
        "resolved_at": now if body.resolved else None,
    }
    supa.table("status_incidents").insert(row).execute()
    return {"ok": True}


@router.put("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, user=Depends(get_current_user)):
    email = user.get("email", "")
    if email not in _FOUNDER_EMAILS:
        raise HTTPException(status_code=403)
    supa = _get_supa()
    supa.table("status_incidents").update({
        "resolved_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", incident_id).execute()
    return {"ok": True}
