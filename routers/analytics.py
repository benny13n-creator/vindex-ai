# -*- coding: utf-8 -*-
"""
Vindex AI — Usage Analytics

POST /analytics/track  — log usage event (fire-and-forget, bez credit deduction)
GET  /analytics/usage  — aggregirani pregled za poslednje N dana
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.analytics")
router = APIRouter(tags=["analytics"])


class TrackReq(BaseModel):
    feature: str = Field(..., max_length=50)
    action: str = Field(..., max_length=50)
    predmet_id: Optional[str] = None
    metadata: Optional[dict] = None


async def _track_event(
    user_id: str,
    feature: str,
    action: str,
    predmet_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Fire-and-forget — pozivati via asyncio.create_task()."""
    try:
        supa = _get_supa()
        row: dict = {
            "user_id": user_id,
            "feature": feature[:50],
            "action":  action[:50],
        }
        if predmet_id:
            row["predmet_id"] = predmet_id
        if metadata:
            import json
            row["metadata"] = json.dumps(metadata, ensure_ascii=False)[:500]
        await asyncio.to_thread(
            lambda: supa.table("usage_events").insert(row).execute()
        )
    except Exception as e:
        logger.debug("[ANALYTICS] track greška: %s", e)


@router.post("/analytics/track")
@limiter.limit("120/minute")
async def track_usage(
    req: TrackReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Log usage event — bez credit deduction."""
    asyncio.create_task(
        _track_event(
            user["user_id"],
            req.feature,
            req.action,
            req.predmet_id,
            req.metadata,
        )
    )
    return {"ok": True}


@router.get("/analytics/usage")
@limiter.limit("30/minute")
async def get_usage(
    request: Request,
    user: dict = Depends(get_current_user),
    dana: int = 30,
):
    """Aggregirani usage stats za poslednje N dana (1–90)."""
    uid  = user["user_id"]
    dana = min(max(dana, 1), 90)
    since = (datetime.now(timezone.utc) - timedelta(days=dana)).isoformat()
    supa  = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("usage_events")
                .select("feature, action, predmet_id, created_at")
                .eq("user_id", uid)
                .gte("created_at", since)
                .order("created_at", desc=True)
                .limit(2000)
                .execute()
        )
        events = r.data or []
    except Exception as e:
        logger.error("[ANALYTICS] query greška: %s", e)
        events = []

    feature_counts: dict[str, int] = {}
    action_counts:  dict[str, int] = {}
    predmet_counts: dict[str, int] = {}
    day_counts:     dict[str, int] = {}

    for ev in events:
        f  = ev.get("feature") or ""
        a  = ev.get("action")  or ""
        p  = ev.get("predmet_id") or ""
        ts = (ev.get("created_at") or "")[:10]

        feature_counts[f] = feature_counts.get(f, 0) + 1
        action_counts[a]  = action_counts.get(a, 0) + 1
        if p:
            predmet_counts[p] = predmet_counts.get(p, 0) + 1
        if ts:
            day_counts[ts] = day_counts.get(ts, 0) + 1

    top_features  = sorted(feature_counts.items(), key=lambda x: -x[1])[:10]
    top_actions   = sorted(action_counts.items(),  key=lambda x: -x[1])[:10]
    top_pred_raw  = sorted(predmet_counts.items(), key=lambda x: -x[1])[:5]
    aktivnost     = sorted(day_counts.items())[-30:]

    # Enrich top predmeti with names
    top_predmeti = []
    for pid, cnt in top_pred_raw:
        try:
            pr = await asyncio.to_thread(
                lambda _p=pid: supa.table("predmeti")
                    .select("naziv")
                    .eq("id", _p)
                    .eq("user_id", uid)
                    .single()
                    .execute()
            )
            naziv = pr.data.get("naziv", pid) if pr.data else pid
        except Exception:
            naziv = pid
        top_predmeti.append({"predmet_id": pid, "naziv": naziv, "pristupa": cnt})

    return {
        "period_dana":       dana,
        "ukupno_dogadjaja":  len(events),
        "top_funkcije":      [{"feature": f, "count": c} for f, c in top_features],
        "top_akcije":        [{"action": a, "count": c} for a, c in top_actions],
        "top_predmeti":      top_predmeti,
        "aktivnost_po_danu": [{"datum": d, "count": c} for d, c in aktivnost],
    }
