# -*- coding: utf-8 -*-
"""
Vindex AI — routers/case_pipeline.py
Case Wizard Automation Pipeline [FAZA:CASE-WIZARD-PIPELINE]

POST /api/predmeti/{predmet_id}/pipeline  — run full post-wizard pipeline
GET  /api/predmeti/{predmet_id}/pipeline/status — check pipeline state / score
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.case_pipeline")
router = APIRouter(tags=["case_pipeline"])


@router.post("/api/predmeti/{predmet_id}/pipeline")
@limiter.limit("10/minute")
async def run_pipeline(
    predmet_id: str,
    request:    Request,
    user:       dict = Depends(PermissionService.require("case_pipeline")),
):
    """
    Triggers the 9-step post-wizard automation pipeline for a predmet.
    Idempotent: safe to call multiple times per day.
    Returns pipeline result with Case Ready Score and checklist.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Verify ownership before running pipeline
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .limit(1)
            .execute()
    )
    if not (pred_r.data):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    try:
        from services.case_pipeline import run_case_pipeline
        result = await run_case_pipeline(predmet_id, uid)
        await UsageService.consume(uid, user.get("email", ""), "case_pipeline")
        return result.to_dict()
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        logger.exception("[PIPELINE] neočekivana greška za predmet=%s", predmet_id)
        raise HTTPException(status_code=500,
                            detail="Pipeline nije uspeo. Predmet je kreiran.")


@router.get("/api/predmeti/{predmet_id}/pipeline/status")
@limiter.limit("30/minute")
async def pipeline_status(
    predmet_id: str,
    request:    Request,
    user:       dict = Depends(get_current_user),
):
    """
    Returns the current Case Ready Score and checklist without running the pipeline.
    Reads existing DB state.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .limit(1)
            .execute()
    )
    if not (pred_r.data):
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    docs_r, pk_r, hron_r, ist_r, roc_r, ca_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_klijenti")
            .select("klijent_id").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("id").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija")
            .select("pitanje").eq("predmet_id", predmet_id)
            .eq("user_id", uid).execute()),
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("id").eq("predmet_id", predmet_id)
            .eq("user_id", uid).execute()),
        # Operation Single Brain, Mission 002: see calculate_case_ready_score's own
        # docstring / docs/singlebrain/READINESS_AUTHORITY_SPEC.md.
        asyncio.to_thread(lambda: supa.table("case_actions")
            .select("prioritet,tip,status,razlog,dedupe_key")
            .eq("predmet_id", predmet_id).eq("status", "open").execute()),
        return_exceptions=True,
    )

    def _safe(r) -> list:
        if isinstance(r, Exception):
            return []
        return r.data or []

    from services.case_pipeline import calculate_case_ready_score
    from shared.case_readiness import compute_case_readiness
    _readiness = compute_case_readiness(_safe(ca_r))
    score, checklist = calculate_case_ready_score(
        dokumenti=_safe(docs_r),
        klijenti=_safe(pk_r),
        rokovi=_safe(hron_r),
        istorija=_safe(ist_r),
        rocista=_safe(roc_r),
        readiness=_readiness,
    )
    return {
        "predmet_id":       predmet_id,
        "case_ready_score": score,
        "checklist":        checklist,
        # Operation Single Brain, Mission 002: exposes the CANONICAL_OWNER's own verdict
        # alongside the checklist score it may have capped, so a caller/UI can explain
        # a capped score rather than showing a lower number with no context.
        "readiness_status": _readiness.get("status"),
    }
