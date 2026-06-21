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

from datetime import date as _date

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
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    q = supa.table("rocista").select("*").eq("user_id", uid)
    if predmet_id:
        q = q.eq("predmet_id", predmet_id)
    if status:
        q = q.eq("status", status)

    r = await asyncio.to_thread(lambda: q.order("datum").limit(limit).offset(offset).execute())
    rows = r.data or []
    for row in rows:
        row["vreme"] = _norm_vreme(row.get("vreme"))
    return {"rocista": rows, "ukupno": len(rows), "limit": limit, "offset": offset}


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


# ── PRIORITET 5: Hearing Follow-Up ───────────────────────────────────────────

class FollowUpReq(BaseModel):
    predmet_id: str           = Field(..., min_length=1, max_length=64)
    napomena:   str           = Field(..., min_length=1, max_length=4000)
    rociste_id: Optional[str] = Field(default=None)


@router.post("/api/rociste/followup")
@limiter.limit("20/minute")
async def hearing_followup(
    body: FollowUpReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Post-ročište follow-up:
    - Kreira belešku sa napomenom
    - Kreira hronologiju entry
    - Ažurira istoriju predmeta
    - Generiše preporuke sledećih koraka (rule-based)
    """
    uid  = user["user_id"]
    supa = _get_supa()
    today_iso = _date.today().isoformat()

    # Proveri vlasništvo
    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,naziv,status")
            .eq("id", body.predmet_id)
            .eq("user_id", uid)
            .limit(1)
            .execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    predmet = pred_r.data[0]
    naziv   = predmet.get("naziv", "Predmet")

    # Taguj napomenu ročišta ako je dat rociste_id
    tag     = f"[Ročište follow-up{' #'+body.rociste_id[:8] if body.rociste_id else ''}]"
    tekst_b = f"{tag} {body.napomena}"

    # Paralelno upiši: beleška + hronologiju + istoriju
    await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_beleske").insert({
            "predmet_id": body.predmet_id,
            "user_id":    uid,
            "sadrzaj":    tekst_b[:2000],
        }).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").insert({
            "predmet_id": body.predmet_id,
            "user_id":    uid,
            "dogadjaj":   f"Follow-up ročište: {body.napomena[:120]}",
            "datum":      today_iso,
            "datum_iso":  today_iso,
            "vaznost":    "bitan",
            "akter":      "Advokat",
        }).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").insert({
            "predmet_id": body.predmet_id,
            "user_id":    uid,
            "pitanje":    f"[Follow-up ročište] {today_iso}",
            "odgovor":    body.napomena[:2000],
            "confidence": "HIGH",
        }).execute()),
        return_exceptions=True,
    )

    # Rule-based preporuke sledećih koraka
    napomena_lower = body.napomena.lower()
    preporuke: list[str] = []

    if any(w in napomena_lower for w in ("odloženo", "odlozeno", "odlaganje", "odložiti")):
        preporuke.append("Ročište je odloženo — proverite i ažurirajte datum sledećeg ročišta.")
        preporuke.append("Obavestite klijenta o novom terminu.")
    if any(w in napomena_lower for w in ("dokaz", "dokaze", "dokumenta", "dokumenti", "veštačenje", "vestacenje")):
        preporuke.append("Identifikujte nedostajuće dokaze i zatražite ih od klijenta ili suda.")
    if any(w in napomena_lower for w in ("svedok", "svedoci", "saslušanje", "ispit")):
        preporuke.append("Pripremite svedoke za naredni pretres — uskladite iskaze sa dokumentacijom.")
    if any(w in napomena_lower for w in ("nagodba", "sporazum", "poravnanje")):
        preporuke.append("Razgovarajte sa klijentom o mogućnosti nagodbe — procenite uslove.")
    if any(w in napomena_lower for w in ("žalba", "zalba", "pobijanje", "revizija")):
        preporuke.append("Proverite rokove za žalbu i pripremite osnove za pobijanje presude.")
    if any(w in napomena_lower for w in ("presuda", "odluka", "rešenje", "resenje")):
        preporuke.append("Analizirajte presudu/odluku i utvrdite dalji tok postupka.")
    if any(w in napomena_lower for w in ("rok", "termin", "zakazano")):
        preporuke.append("Dodajte novi rok u sistem i obavestite klijenta o terminima.")

    if not preporuke:
        preporuke.append("Ažurirajte status predmeta i zabeleškite ishod ročišta.")
        preporuke.append("Planirajte sledeće korake sa klijentom.")

    logger.info("[FOLLOWUP] uid=%.8s predmet=%s", uid, body.predmet_id)

    return {
        "ok":         True,
        "predmet_id": body.predmet_id,
        "naziv":      naziv,
        "datum":      today_iso,
        "preporuke":  preporuke,
        "akcije": {
            "beleska_kreirana":     True,
            "hronologija_azurana":  True,
            "istorija_azurana":     True,
        },
    }


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
