# -*- coding: utf-8 -*-
"""
Vindex AI — routers/interni.py

F7.2: Interni pravni stavovi firme (PRO only).
"""
import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from shared.deps import require_pro
from shared.rate import limiter
from interni_stavovi import (
    ingest_stav as _ingest_stav,
    search_stavovi as _search_stavovi,
    obrisi_stavove as _obrisi_stavove,
)

router = APIRouter()


class InterniStavRequest(BaseModel):
    naslov: str = Field(..., min_length=3, max_length=200)
    tekst:  str = Field(..., min_length=30, max_length=20000)


class InterniPretraga(BaseModel):
    upit: str = Field(..., min_length=3, max_length=500)


@router.post("/interni-stavovi/dodaj")  # F7.2
@limiter.limit("20/minute")
async def post_dodaj_stav(req: InterniStavRequest, request: Request, user: dict = Depends(require_pro)):
    """F7.2 — Dodaj interni pravni stav firme (PRO)."""
    count = await asyncio.to_thread(_ingest_stav, user["user_id"], req.naslov, req.tekst)
    return {"vektori": count, "naslov": req.naslov}


@router.post("/interni-stavovi/pretraga")  # F7.2
@limiter.limit("30/minute")
async def post_pretraga_stavova(req: InterniPretraga, request: Request, user: dict = Depends(require_pro)):
    """F7.2 — Pretraži interne stavove firme (PRO)."""
    rezultati = await asyncio.to_thread(_search_stavovi, user["user_id"], req.upit)
    return {"rezultati": rezultati, "ukupno": len(rezultati)}


@router.delete("/interni-stavovi/obrisi-sve")  # F7.2
@limiter.limit("5/minute")
async def delete_svi_stavovi(request: Request, user: dict = Depends(require_pro)):
    """F7.2 — Obriši sve interne stavove korisnika (PRO)."""
    count = await asyncio.to_thread(_obrisi_stavove, user["user_id"])
    return {"obrisano_vektora": count}
