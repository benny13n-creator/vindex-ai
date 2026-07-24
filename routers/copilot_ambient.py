# -*- coding: utf-8 -*-
"""
Vindex AI — routers/copilot_ambient.py

KORAK C: Ambient Context & Word/Browser Copilot (2026-07-24)

POST /api/copilot/ambient/analyze — prima poslednji pasus koji advokat
kuca van aplikacije (MS Word add-in / browser ekstenzija, v. integrations/
word_addin/) i vraća kratke kontekstualne sugestije preko
services/ambient_analyzer.py.

predmet_id je opcion (add-in ga šalje samo ako je dokument eksplicitno
povezan sa predmetom u Vindex-u) -- kad je prisutan, MORA proći isti
vlasništvo-check kao svaka druga {predmet_id}-scoped ruta (SEC-001,
docs/security/SECURITY_GAP_REGISTER.md) pre nego što bilo šta uradimo
sa njim, inače bi tuđi predmet_id procureo kroz RAG kontekst.
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.copilot_ambient")
router = APIRouter(prefix="/api/copilot/ambient", tags=["copilot-ambient"])

_MAX_TEKST_CHARS = 4000  # jedan pasus, ne ceo dokument


class AmbientAnalyzeReq(BaseModel):
    tekst: str = Field(..., min_length=1, max_length=_MAX_TEKST_CHARS)
    predmet_id: str | None = None
    tip_dokumenta: str | None = Field(default=None, max_length=50)


async def _proveri_vlasnistvo_predmeta(predmet_id: str, user_id: str) -> None:
    """SEC-001 obrazac: predmet_id iz zahteva se NIKAD ne prihvata bez
    provere da pripada pozivaocu -- ista provera kao dodaj_belesku (api.py)."""
    supa = _get_supa()
    pred = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", predmet_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
    )
    if not pred.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")


@router.post("/analyze")
@limiter.limit("60/minute")
async def ambient_analyze(
    req: AmbientAnalyzeReq,
    request: Request,
    user: dict = Depends(PermissionService.require("copilot_ambient")),
):
    uid = user["user_id"]

    if req.predmet_id:
        await _proveri_vlasnistvo_predmeta(req.predmet_id, uid)

    from services.ambient_analyzer import analyze_paragraph
    rezultat = await analyze_paragraph(
        tekst=req.tekst,
        predmet_id=req.predmet_id,
        tip_dokumenta=req.tip_dokumenta,
        user_id=uid,
    )

    # krediti=0 (v. migracija 083) -- ali dnevni_limit=200 JESTE stvarna
    # budžetska zaštita koju UsageService.consume primenjuje (baca
    # HTTPException 429 kad je limit dostignut). Namerno se NE guta ta
    # greška -- isti obrazac kao /api/nacrt (poziv posle same operacije,
    # greška propagira ka klijentu kao 429/402).
    await UsageService.consume(uid, user.get("email", ""), "copilot_ambient")

    return rezultat
