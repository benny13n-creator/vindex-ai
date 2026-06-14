# -*- coding: utf-8 -*-
"""
Vindex AI — routers/rocista.py
Faza 1: Ročišta entity

POST   /api/rocista              — kreiraj ročište
GET    /api/rocista              — lista ročišta za predmet ili sva
PATCH  /api/rocista/{id}         — izmeni ročište
DELETE /api/rocista/{id}         — obriši ročište
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.rocista")
router = APIRouter(tags=["rocista"])

_VALID_STATUS = {"zakazano", "odrzano", "odlozeno", "otkazano"}


def _norm_vreme(v: Optional[str]) -> Optional[str]:
    """Supabase vraća TIME kao 'HH:MM:SS' — normalizujemo na 'HH:MM'."""
    if not v:
        return None
    return v[:5] if len(v) >= 5 else v


class RocisteReq(BaseModel):
    predmet_id:         str           = Field(..., min_length=1, max_length=64)
    sud:                str           = Field(..., min_length=1, max_length=300)
    datum:              str           = Field(..., min_length=10, max_length=10)
    vreme:              Optional[str] = Field(None, max_length=8)
    sudnica:            Optional[str] = Field(None, max_length=100)
    broj_predmeta_suda: Optional[str] = Field(None, max_length=100)
    napomena:           Optional[str] = Field(None, max_length=2000)

    @field_validator("datum")
    @classmethod
    def _val_datum(cls, v: str) -> str:
        from datetime import date as _date
        try:
            _date.fromisoformat(v)
        except ValueError:
            raise ValueError("datum mora biti YYYY-MM-DD")
        return v

    @field_validator("vreme")
    @classmethod
    def _val_vreme(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("vreme mora biti HH:MM")
        return v


class RocistePatchReq(BaseModel):
    sud:                Optional[str] = Field(None, max_length=300)
    datum:              Optional[str] = Field(None, max_length=10)
    vreme:              Optional[str] = Field(None, max_length=8)
    sudnica:            Optional[str] = Field(None, max_length=100)
    broj_predmeta_suda: Optional[str] = Field(None, max_length=100)
    status:             Optional[str] = Field(None, max_length=20)
    napomena:           Optional[str] = Field(None, max_length=2000)

    @field_validator("datum")
    @classmethod
    def _val_datum(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        from datetime import date as _date
        try:
            _date.fromisoformat(v)
        except ValueError:
            raise ValueError("datum mora biti YYYY-MM-DD")
        return v

    @field_validator("status")
    @classmethod
    def _val_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_STATUS:
            raise ValueError(f"status mora biti jedan od: {sorted(_VALID_STATUS)}")
        return v

    @field_validator("vreme")
    @classmethod
    def _val_vreme(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("vreme mora biti HH:MM")
        return v


@router.post("/api/rocista")
@limiter.limit("30/minute")
async def kreiraj_rociste(
    body: RocisteReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", body.predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen")

    payload = {
        "predmet_id":          body.predmet_id,
        "user_id":             uid,
        "sud":                 body.sud.strip(),
        "datum":               body.datum,
        "vreme":               body.vreme or None,
        "sudnica":             (body.sudnica or "").strip() or None,
        "broj_predmeta_suda":  (body.broj_predmeta_suda or "").strip() or None,
        "napomena":            (body.napomena or "").strip() or None,
        "status":              "zakazano",
    }

    r = await asyncio.to_thread(
        lambda: supa.table("rocista").insert(payload).execute()
    )
    if not r.data:
        raise HTTPException(status_code=500, detail="Greška pri kreiranju ročišta")

    row = r.data[0]
    row["vreme"] = _norm_vreme(row.get("vreme"))
    logger.info("[ROCISTE] kreirano uid=%.8s predmet=%s datum=%s", uid, body.predmet_id, body.datum)
    return {"rociste": row, "ok": True}


@router.get("/api/rocista")
@limiter.limit("60/minute")
async def lista_rocista(
    request: Request,
    predmet_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    q = supa.table("rocista").select("*").eq("user_id", uid)
    if predmet_id:
        q = q.eq("predmet_id", predmet_id)

    r = await asyncio.to_thread(lambda: q.order("datum").execute())
    rows = r.data or []
    for row in rows:
        row["vreme"] = _norm_vreme(row.get("vreme"))
    return {"rocista": rows, "ukupno": len(rows)}


@router.patch("/api/rocista/{rociste_id}")
@limiter.limit("30/minute")
async def izmeni_rociste(
    rociste_id: str,
    body: RocistePatchReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(status_code=422, detail="Nema polja za izmenu")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    r = await asyncio.to_thread(
        lambda: supa.table("rocista")
            .update(updates)
            .eq("id", rociste_id)
            .eq("user_id", uid)
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Ročište nije pronađeno")

    row = r.data[0]
    row["vreme"] = _norm_vreme(row.get("vreme"))
    return {"rociste": row, "ok": True}


@router.delete("/api/rocista/{rociste_id}")
@limiter.limit("30/minute")
async def obrisi_rociste(
    rociste_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    r = await asyncio.to_thread(
        lambda: supa.table("rocista")
            .delete()
            .eq("id", rociste_id)
            .eq("user_id", uid)
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Ročište nije pronađeno")

    return {"ok": True}
