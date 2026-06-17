# -*- coding: utf-8 -*-
"""
Vindex AI — routers/predmeti_close.py

PATCH /api/predmeti/{predmet_id}/zatvori  — Zatvaranje predmeta sa ishodom
GET   /api/predmeti/{predmet_id}/ishod    — Dohvata ishod zatvorenog predmeta
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.predmeti_close")
router = APIRouter(tags=["predmeti"])

_VALID_ISHOD = {
    "pobeda",
    "poraz",
    "nagodba",
    "odustajanje",
    "odbacena",
    "ostalo",
}

_ISHOD_LABEL: dict[str, str] = {
    "pobeda":      "Pobeda",
    "poraz":       "Poraz",
    "nagodba":     "Nagodba / Poravnanje",
    "odustajanje": "Odustajanje od tužbe",
    "odbacena":    "Tužba odbačena",
    "ostalo":      "Ostalo",
}


class ZatvoriReq(BaseModel):
    ishod:     str           = Field(..., min_length=3, max_length=30)
    zakljucak: str           = Field(default="", max_length=3000)
    datum_zatvaranja: Optional[str] = Field(default=None, max_length=10)

    @field_validator("ishod")
    @classmethod
    def _val_ishod(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in _VALID_ISHOD:
            raise ValueError(f"ishod mora biti jedan od: {sorted(_VALID_ISHOD)}")
        return v

    @field_validator("datum_zatvaranja")
    @classmethod
    def _val_datum(cls, v: Optional[str]) -> Optional[str]:
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError("datum_zatvaranja mora biti YYYY-MM-DD")
        return v


@router.patch("/api/predmeti/{predmet_id}/zatvori")
@limiter.limit("20/minute")
async def zatvori_predmet(
    predmet_id: str,
    body: ZatvoriReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Zatvara predmet i beleži ishod slučaja.

    Ishod: pobeda | poraz | nagodba | odustajanje | odbacena | ostalo
    Closure event se upisuje u predmet_hronologija za trajan zapis.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Fetch predmet
    pred_res = await asyncio.to_thread(
        lambda: supa.table("predmeti")
                    .select("id, naziv, status, opis")
                    .eq("id", predmet_id)
                    .eq("user_id", uid)
                    .single()
                    .execute()
    )
    if not pred_res.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    pred = pred_res.data
    if pred.get("status") == "zatvoren":
        raise HTTPException(
            status_code=409,
            detail="Predmet je već zatvoren.",
        )

    datum_zatv = body.datum_zatvaranja or date.today().isoformat()
    ishod_label = _ISHOD_LABEL.get(body.ishod, body.ishod)

    # Build closure note to append to opis
    closure_note_parts = [f"\n\n--- Zatvoreno {datum_zatv} ---", f"Ishod: {ishod_label}"]
    if body.zakljucak:
        closure_note_parts.append(f"Zaključak: {body.zakljucak[:2000]}")
    closure_note = "\n".join(closure_note_parts)

    existing_opis = (pred.get("opis") or "").rstrip()
    new_opis = existing_opis + closure_note

    # Update predmet status and opis
    update_data: dict = {"status": "zatvoren", "opis": new_opis}

    updated_res = await asyncio.to_thread(
        lambda: supa.table("predmeti")
                    .update(update_data)
                    .eq("id", predmet_id)
                    .eq("user_id", uid)
                    .execute()
    )

    if not updated_res.data:
        raise HTTPException(status_code=500, detail="Ažuriranje predmeta nije uspelo.")

    # Record closure in hronologija
    hron_dogadjaj = f"Predmet zatvoren — Ishod: {ishod_label}"
    hron_akter    = "Advokat (ručno zatvaranje)"
    if body.zakljucak:
        hron_akter += f" | {body.zakljucak[:100]}"

    try:
        await asyncio.to_thread(
            lambda: supa.table("predmet_hronologija").insert({
                "predmet_id": predmet_id,
                "user_id":    uid,
                "dogadjaj":   hron_dogadjaj[:200],
                "datum":      datum_zatv,
                "datum_iso":  datum_zatv,
                "vaznost":    "kljucan",
                "akter":      hron_akter[:300],
            }).execute()
        )
    except Exception as e:
        logger.warning("[ZATVORI] hronologija insert greška: %s", e)

    logger.info("[ZATVORI] predmet=%s uid=%.8s ishod=%s", predmet_id, uid, body.ishod)

    return {
        "ok":             True,
        "predmet_id":     predmet_id,
        "naziv":          pred.get("naziv", ""),
        "ishod":          body.ishod,
        "ishod_label":    ishod_label,
        "datum_zatvaranja": datum_zatv,
        "zakljucak":      body.zakljucak or "",
        "poruka":         f"Predmet '{pred.get('naziv', '')}' je uspešno zatvoren. Ishod: {ishod_label}.",
    }


@router.get("/api/predmeti/{predmet_id}/ishod")
@limiter.limit("30/minute")
async def get_predmet_ishod(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Dohvata ishod zatvorenog predmeta iz hronologije.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Verify predmet belongs to user
    pred_res = await asyncio.to_thread(
        lambda: supa.table("predmeti")
                    .select("id, naziv, status")
                    .eq("id", predmet_id)
                    .eq("user_id", uid)
                    .single()
                    .execute()
    )
    if not pred_res.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    pred = pred_res.data
    if pred.get("status") != "zatvoren":
        return {
            "zatvoren": False,
            "ishod": None,
            "datum_zatvaranja": None,
            "zakljucak": None,
        }

    # Find closure event in hronologija
    hron_res = await asyncio.to_thread(
        lambda: supa.table("predmet_hronologija")
                    .select("dogadjaj, datum, akter")
                    .eq("predmet_id", predmet_id)
                    .eq("user_id", uid)
                    .ilike("dogadjaj", "Predmet zatvoren%")
                    .order("datum", desc=True)
                    .limit(1)
                    .execute()
    )

    hron = (hron_res.data or [None])[0]
    ishod_raw = None
    datum_zatv = None
    zakljucak  = None

    if hron:
        # Parse "Predmet zatvoren — Ishod: Pobeda" → "pobeda"
        dogadjaj = hron.get("dogadjaj", "")
        if "Ishod:" in dogadjaj:
            ishod_label = dogadjaj.split("Ishod:", 1)[1].strip()
            # Reverse lookup
            ishod_raw = next(
                (k for k, v in _ISHOD_LABEL.items() if v == ishod_label),
                ishod_label.lower()
            )
        datum_zatv = hron.get("datum")
        akter = hron.get("akter", "")
        if " | " in akter:
            zakljucak = akter.split(" | ", 1)[1]

    return {
        "zatvoren":         True,
        "ishod":            ishod_raw,
        "ishod_label":      _ISHOD_LABEL.get(ishod_raw or "", ishod_raw or ""),
        "datum_zatvaranja": datum_zatv,
        "zakljucak":        zakljucak,
        "predmet_naziv":    pred.get("naziv", ""),
    }
