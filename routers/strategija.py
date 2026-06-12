# -*- coding: utf-8 -*-
"""
Vindex AI — routers/strategija.py

F5, F7.1, F9: AI Strategija moduli (PRO only).
  F5.1  — Red Team analiza
  F5.2  — Litigation Simulator
  F5.3  — AI Sudija
  F5.4  — Due Diligence
  F7.1  — AI Pravni Revizor
  F9.1  — Witness Analyzer
  F9.2  — AI Judge v2
"""
import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _audit, _deduct_credit, require_pro
from shared.rate import limiter
from strategija import (
    red_team_analiza_sync,
    litigation_simulator_sync,
    ai_judge_mode_sync,
    due_diligence_analiza_sync,
    pravni_revizor_sync,
    witness_analyzer_sync,
    ai_judge_v2_sync,
)

router = APIRouter()

logger = __import__("logging").getLogger("vindex.api")


class StrategijaRequest(BaseModel):
    tekst: str = Field(..., max_length=20000)


@router.post("/strategija/red-team")  # F5.1
@limiter.limit("5/minute")
async def post_red_team(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.1 — Red Team analiza predmeta iz perspektive protivne strane (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "red_team", ""))
    try:
        rezultat = await asyncio.to_thread(
            red_team_analiza_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "red_team", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] red_team greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/litigation")  # F5.2
@limiter.limit("5/minute")
async def post_litigation(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.2 — Litigation Simulator — procena ishoda sa % verovatnoće (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "litigation", ""))
    _praksa_context = ""
    try:
        from app.services.retrieve import _pretraga_praksa, _ugradi_query, _formatiraj_praksa_match
        _vec = await asyncio.wait_for(
            asyncio.to_thread(_ugradi_query, req.tekst[:500]), timeout=8.0
        )
        _matches = await asyncio.wait_for(
            asyncio.to_thread(_pretraga_praksa, _vec, 3), timeout=5.0
        )
        if _matches:
            _parts = [_formatiraj_praksa_match(m) for m in _matches]
            _parts = [p for p in _parts if p and len(p.strip()) > 30]
            if _parts:
                _praksa_context = "\n\n---\n\n".join(_parts[:3])
    except (asyncio.TimeoutError, Exception) as _pe:
        logger.warning("[F5] litigation praksa greška: %s", _pe)
    try:
        rezultat = await asyncio.to_thread(
            litigation_simulator_sync, req.tekst, os.getenv("OPENAI_API_KEY", ""), _praksa_context
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "litigation", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] litigation greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju simulacije. Pokušajte ponovo.")


@router.post("/strategija/sudija")  # F5.3
@limiter.limit("5/minute")
async def post_sudija(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.3 — AI Sudija — neutralna sudska perspektiva (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "ai_sudija", ""))
    try:
        rezultat = await asyncio.to_thread(
            ai_judge_mode_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "sudija", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] sudija greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/due-diligence")  # F5.4
@limiter.limit("5/minute")
async def post_due_diligence(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F5.4 — Due Diligence analiza dokumenta (PRO)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Tekst dokumenta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "due_diligence", ""))
    try:
        rezultat = await asyncio.to_thread(
            due_diligence_analiza_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "due_diligence", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F5] due_diligence greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju analize. Pokušajte ponovo.")


@router.post("/strategija/revizor")  # F7.1
@limiter.limit("5/minute")
async def post_revizor(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F7.1 — AI Pravni Revizor — pregled dokumenta sa predlozima izmena (PRO)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Tekst dokumenta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "pravni_revizor", ""))
    try:
        rezultat = await asyncio.to_thread(
            pravni_revizor_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "revizor", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F7] pravni_revizor greška")
        raise HTTPException(status_code=500, detail="Greška pri generisanju revizije. Pokušajte ponovo.")


@router.post("/strategija/witness")  # F9.1
@limiter.limit("5/minute")
async def post_witness(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F9.1 — AI Witness Analyzer — analiza iskaza/svedočenja (PRO)."""
    if len(req.tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Iskaz mora imati najmanje 50 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "witness_analyzer", ""))
    try:
        rezultat = await asyncio.to_thread(
            witness_analyzer_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"rezultat": rezultat, "modul": "witness", "credits_remaining": max(preostalo, 0)}
    except Exception:
        logger.exception("[F9] witness_analyzer greška")
        raise HTTPException(status_code=500, detail="Greška pri analizi iskaza. Pokušajte ponovo.")


@router.post("/strategija/sudija-v2")  # F9.2
@limiter.limit("3/minute")
async def post_sudija_v2(req: StrategijaRequest, request: Request, user: dict = Depends(require_pro)):
    """F9.2 — AI Judge v2 — tužilac vs branilac → sudija (PRO, 3-round chain)."""
    if len(req.tekst.strip()) < 100:
        raise HTTPException(status_code=422, detail="Opis predmeta mora imati najmanje 100 karaktera.")
    asyncio.create_task(_audit(user["user_id"], "sudija_v2", ""))
    try:
        rezultat = await asyncio.to_thread(
            ai_judge_v2_sync, req.tekst, os.getenv("OPENAI_API_KEY", "")
        )
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {
            "tuzilac":  rezultat["tuzilac"],
            "branilac": rezultat["branilac"],
            "presuda":  rezultat["presuda"],
            "modul":    "sudija_v2",
            "credits_remaining": max(preostalo, 0),
        }
    except Exception:
        logger.exception("[F9] sudija_v2 greška")
        raise HTTPException(status_code=500, detail="Greška pri simulaciji debate. Pokušajte ponovo.")
