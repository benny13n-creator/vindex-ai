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

    # Auto-doprinos anonimnom benchmarku (fire-and-forget, nikad ne blokira zatvaranje)
    async def _benchmark_doprinos():
        try:
            opt_r = await asyncio.to_thread(
                lambda: supa.table("profiles")
                    .select("benchmark_opt_in")
                    .eq("id", uid)
                    .maybe_single()
                    .execute()
            )
            if not (opt_r.data or {}).get("benchmark_opt_in"):
                return
            bill_r = await asyncio.to_thread(
                lambda: supa.table("billing_entries")
                    .select("iznos_rsd, sati")
                    .eq("predmet_id", predmet_id)
                    .execute()
            )
            ukupno_rsd = sum(float(b.get("iznos_rsd") or 0) for b in (bill_r.data or []))
            tip_pred = pred.get("opis", "")  # type extracted below
            pred_tip_r = await asyncio.to_thread(
                lambda: supa.table("predmeti")
                    .select("tip")
                    .eq("id", predmet_id)
                    .maybe_single()
                    .execute()
            )
            tip_pred = (pred_tip_r.data or {}).get("tip") or "ostalo"
            if tip_pred and ukupno_rsd > 0:
                # 5% band anonymization
                band = max(round(ukupno_rsd / 5000) * 5000, 5000)
                await asyncio.to_thread(
                    lambda: supa.table("case_benchmarks").insert({
                        "tip_predmeta": tip_pred,
                        "naplaceno_rsd": band,
                        "ishod": body.ishod,
                        "opt_in": True,
                    }).execute()
                )
        except Exception as _be:
            logger.debug("[BENCHMARK] Doprinos greška: %s", _be)

    asyncio.create_task(_benchmark_doprinos())

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


# ─── Bulk operacije ────────────────────────────────────────────────────────────

_BULK_AKCIJE = {
    "arhiviranje": "arhiviran",
    "aktiviranje": "aktivan",
    "zatvaranje":  "zatvoren",
}


class BulkAkcijaReq(BaseModel):
    predmet_ids: list[str] = Field(..., min_length=1, max_length=50)
    akcija: str = Field(..., pattern="^(arhiviranje|aktiviranje|zatvaranje)$")


@router.patch("/api/predmeti/bulk")
@limiter.limit("10/minute")
async def bulk_promena_statusa(
    body: BulkAkcijaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Bulk promena statusa predmeta.
    akcija: 'arhiviranje' | 'aktiviranje' | 'zatvaranje'
    Maks 50 predmeta odjednom. Svaki predmet mora biti korisnikov.
    """
    uid    = user["user_id"]
    supa   = _get_supa()
    novi_status = _BULK_AKCIJE[body.akcija]

    # Fetch predmeti da verifikujemo vlasništvo
    ids = list(set(body.predmet_ids))[:50]
    existing_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id,status")
            .eq("user_id", uid)
            .in_("id", ids)
            .execute()
    )
    existing = {p["id"]: p for p in (existing_r.data or [])}

    if not existing:
        raise HTTPException(status_code=404, detail="Nijedan od navedenih predmeta nije pronađen.")

    # Samo oni koji postoje i nisu već u tom statusu
    za_update = [pid for pid in ids if pid in existing and existing[pid].get("status") != novi_status]

    if not za_update:
        return {"ok": True, "azurirano": 0, "poruka": "Svi predmeti su već u traženom statusu."}

    await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .update({"status": novi_status})
            .eq("user_id", uid)
            .in_("id", za_update)
            .execute()
    )

    logger.info("[BULK] uid=%.8s akcija=%s azurirano=%d", uid, body.akcija, len(za_update))
    return {
        "ok":        True,
        "azurirano": len(za_update),
        "poruka":    f"{len(za_update)} predmet(a) — status promenjen na '{novi_status}'.",
        "novi_status": novi_status,
    }
