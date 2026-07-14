# -*- coding: utf-8 -*-
"""
Vindex AI — Confidence Audit + Explainable Learning

GET  /api/audit/kalibracija                         — kalibracija po bandu
POST /api/audit/sync                                — sinhronizuje outcome→audit
GET  /api/audit/preporuke                           — sve preporuke sa statistikom
GET  /api/audit/explainable/{recommendation_id}    — tezine izvora za preporuku
PATCH /api/audit/preporuke/{id}/bila-tacna         — rucno markuj tacnost
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.usage import UsageService
from services.confidence_auditor import (
    calculate_calibration,
    get_explainable_recommendation,
    sync_outcomes_to_audit,
)

logger = logging.getLogger("vindex.confidence_audit")
router = APIRouter(prefix="/api/audit", tags=["confidence_audit"])


class BilaTacnaRequest(BaseModel):
    bila_tacna: bool


@router.get("/kalibracija")
async def get_kalibracija(user=Depends(PermissionService.require("confidence_audit"))):
    """Kalibracija AI pouzdanosti po confidence bandu.

    Odgovara na: 'Kada sam rekao VISOKO, koliko puta sam bio u pravu?'
    Ukljucuje: Brier score, status po bandu, top oblasti, preporuka.
    """
    supa = _get_supa()
    try:
        rezultat = await calculate_calibration(supa, user["user_id"])
        await UsageService.consume(user["user_id"], user.get("email", ""), "confidence_audit")
        return rezultat
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/sync")
async def sync_audit(user=Depends(get_current_user)):
    """Sinhronizuje ishode predmeta sa recommendation_log → puni confidence_audit_log.

    Pokretati: posle svakog zatvaranja predmeta, ili periodicno kao cron.
    """
    supa = _get_supa()
    try:
        result = await sync_outcomes_to_audit(supa, user["user_id"])
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/preporuke")
async def get_preporuke_statistika(
    confidence_band: Optional[str] = None,
    oblast_prava: Optional[str] = None,
    limit: int = 50,
    user=Depends(PermissionService.require("confidence_audit")),
):
    """Lista preporuka sa confidence bandom i isohodom. Podrzava filtriranje."""
    supa = _get_supa()
    try:
        q = (
            supa.table("recommendation_log")
            .select("id, preporuka, tip_slucaja, confidence_band, oblast_prava, prihvacena, bila_tacna, izbori_tezina:izvori_tezina, created_at")
            .eq("user_id", user["user_id"])
            .order("created_at", desc=True)
            .limit(min(limit, 100))
        )
        if confidence_band:
            q = q.eq("confidence_band", confidence_band)
        if oblast_prava:
            q = q.eq("oblast_prava", oblast_prava)

        row = await asyncio.to_thread(lambda: q.execute())
        preporuke = row.data or []

        total = len(preporuke)
        prihvacenih = sum(1 for p in preporuke if p.get("prihvacena"))
        tacnih = sum(1 for p in preporuke if p.get("bila_tacna"))
        sa_explainability = sum(1 for p in preporuke if p.get("izbori_tezina") and p["izbori_tezina"].get("ukupno_izvora", 0) > 0)

        await UsageService.consume(user["user_id"], user.get("email", ""), "confidence_audit")

        return {
            "preporuke": preporuke,
            "statistika": {
                "ukupno": total,
                "prihvacenih": prihvacenih,
                "tacnih": tacnih,
                "sa_explainability": sa_explainability,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/explainable/{recommendation_id}")
async def get_explainable(recommendation_id: str, user=Depends(PermissionService.require("confidence_audit"))):
    """Objasnjava odakle dolazi preporuka: 40% interna / 30% RAG / 20% zakon / 10% AI.

    Vraca komponente sa procentima i dominantni izvor.
    """
    supa = _get_supa()
    try:
        rezultat = await get_explainable_recommendation(supa, recommendation_id, user["user_id"])
        await UsageService.consume(user["user_id"], user.get("email", ""), "confidence_audit")
        return rezultat
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.patch("/preporuke/{recommendation_id}/bila-tacna")
async def set_bila_tacna(
    recommendation_id: str,
    body: BilaTacnaRequest,
    user=Depends(get_current_user),
):
    """Rucno markuje da li je preporuka bila tacna (za slucajeve bez automatskog ishoda)."""
    supa = _get_supa()
    try:
        rec_row = await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
            .select("id, confidence_band, oblast_prava, predmet_id")
            .eq("id", recommendation_id)
            .eq("user_id", user["user_id"])
            .maybe_single()
            .execute()
        )
        if not rec_row.data:
            raise HTTPException(404, "Preporuka nije pronadjena")

        rec = rec_row.data

        await asyncio.to_thread(
            lambda: supa.table("recommendation_log")
            .update({"bila_tacna": body.bila_tacna})
            .eq("id", recommendation_id)
            .execute()
        )

        if rec.get("confidence_band"):
            await asyncio.to_thread(
                lambda: supa.table("confidence_audit_log")
                .upsert({
                    "user_id": user["user_id"],
                    "recommendation_id": recommendation_id,
                    "confidence_band": rec["confidence_band"],
                    "prihvacena": True,
                    "bila_tacna": body.bila_tacna,
                    "oblast_prava": rec.get("oblast_prava"),
                    "predmet_id": rec.get("predmet_id"),
                }, on_conflict="recommendation_id")
                .execute()
            )

        return {
            "recommendation_id": recommendation_id,
            "bila_tacna": body.bila_tacna,
            "poruka": "Azurirano. Pokrenite GET /api/audit/kalibracija za azurirani izvestaj.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
