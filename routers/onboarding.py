# -*- coding: utf-8 -*-
"""
Vindex AI — routers/onboarding.py

F3.3: Onboarding flow — 5-koracni wizard za postavljanje kancelarije.

SQL migracija (pokrenuti JEDNOM u Supabase SQL editor):
──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS onboarding_state (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid UNIQUE NOT NULL,
  step_completed   int DEFAULT 0,
  completed        boolean DEFAULT false,
  tip_kancelarije  text,
  oblasti_prava    text[],
  broj_predmeta    text,
  ciljevi          text[],
  completed_at     timestamptz,
  created_at       timestamptz DEFAULT now(),
  updated_at       timestamptz DEFAULT now()
);
──────────────────────────────────────────────────────

Koraci:
  1 — Tip kancelarije (samostalni/tim/firma)
  2 — Oblast prava (krivicno/gradjansko/privredno/radno/ostalo)
  3 — Broj predmeta mesecno (do10/10-50/50+)
  4 — Ciljevi (billing/praksa/dokumenti/ai/sve)
  5 — Kompletiran
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.onboarding")
router = APIRouter(tags=["onboarding"])

_PRAZAN_STATE = {
    "step_completed":  0,
    "completed":       False,
    "tip_kancelarije": None,
    "oblasti_prava":   None,
    "broj_predmeta":   None,
    "ciljevi":         None,
    "completed_at":    None,
}


class OnboardingStep(BaseModel):
    step:    int  = Field(..., ge=1, le=5)
    odgovor: dict = Field(...)


async def _dohvati_state(supa, uid: str) -> dict:
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("onboarding_state")
                .select("*")
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        return r.data or dict(_PRAZAN_STATE)
    except Exception as exc:
        logger.debug("onboarding_state tabela greška: %s", exc)
        return dict(_PRAZAN_STATE)


async def _upsert_state(supa, uid: str, update: dict) -> None:
    try:
        existing = await asyncio.to_thread(
            lambda: supa.table("onboarding_state").select("id").eq("user_id", uid).maybe_single().execute()
        )
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        if existing.data:
            await asyncio.to_thread(
                lambda: supa.table("onboarding_state").update(update).eq("user_id", uid).execute()
            )
        else:
            update["user_id"] = uid
            await asyncio.to_thread(
                lambda: supa.table("onboarding_state").insert(update).execute()
            )
    except Exception as exc:
        logger.warning("onboarding upsert greška: %s", exc)


@router.get("/api/onboarding/stanje")
@limiter.limit("30/minute")
async def onboarding_stanje(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vrati trenutni onboarding state za korisnika."""
    uid  = user["user_id"]
    supa = _get_supa()
    state = await _dohvati_state(supa, uid)
    return state


@router.post("/api/onboarding/korak")
@limiter.limit("30/minute")
async def onboarding_korak(
    body: OnboardingStep,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Upiši odgovor za jedan onboarding korak."""
    uid  = user["user_id"]
    supa = _get_supa()

    update: dict[str, Any] = {"step_completed": body.step}

    if body.step == 1:
        update["tip_kancelarije"] = body.odgovor.get("tip")
    elif body.step == 2:
        oblasti = body.odgovor.get("oblasti")
        update["oblasti_prava"] = oblasti if isinstance(oblasti, list) else [oblasti] if oblasti else []
    elif body.step == 3:
        update["broj_predmeta"] = body.odgovor.get("broj")
    elif body.step == 4:
        ciljevi = body.odgovor.get("ciljevi")
        update["ciljevi"] = ciljevi if isinstance(ciljevi, list) else [ciljevi] if ciljevi else []
    elif body.step == 5:
        update["completed"]    = True
        update["completed_at"] = datetime.now(timezone.utc).isoformat()

    await _upsert_state(supa, uid, update)
    logger.info("[ONBOARDING] uid=%.8s korak=%d", uid, body.step)
    return {"success": True, "step": body.step, "completed": body.step == 5}


@router.get("/api/onboarding/kompletiran")
@limiter.limit("60/minute")
async def onboarding_kompletiran(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Brza provera da li je onboarding završen."""
    uid   = user["user_id"]
    supa  = _get_supa()
    state = await _dohvati_state(supa, uid)
    return {
        "completed":      state.get("completed", False),
        "step_completed": state.get("step_completed", 0),
    }
