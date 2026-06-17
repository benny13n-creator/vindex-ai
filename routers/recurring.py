# -*- coding: utf-8 -*-
"""
Vindex AI — routers/recurring.py

Ponavljajuće fakture (mesecne/kvartalne/godisnje)

POST   /billing/recurring                   — kreira recurring template
GET    /billing/recurring                   — lista (aktivan filter opcioni)
GET    /billing/recurring/{id}              — jedna
PATCH  /billing/recurring/{id}              — izmeni / deaktiviraj
DELETE /billing/recurring/{id}              — obriši (samo neaktivirane)
POST   /billing/recurring/{id}/generiši     — kreira fakturu + pomera sledeci_datum
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.recurring")
router = APIRouter(prefix="/billing/recurring", tags=["billing"])


# ─── Patchable wrapper ────────────────────────────────────────────────────────

def _db(fn):
    return asyncio.to_thread(fn)


# ─── Schema ───────────────────────────────────────────────────────────────────

class RecurringCreateReq(BaseModel):
    naziv:          str            = Field(..., min_length=2, max_length=200)
    ucestalost:     str            = Field(..., pattern=r"^(mesecno|kvartalno|godisnje)$")
    iznos_rsd:      float          = Field(..., gt=0)
    opis:           str            = Field(..., min_length=2, max_length=500)
    sledeci_datum:  date
    klijent_id:     Optional[str]  = None
    predmet_id:     Optional[str]  = None
    pdv_procenat:   float          = Field(default=0.0, ge=0, le=100)


class RecurringPatchReq(BaseModel):
    naziv:          Optional[str]   = Field(None, min_length=2, max_length=200)
    ucestalost:     Optional[str]   = Field(None, pattern=r"^(mesecno|kvartalno|godisnje)$")
    iznos_rsd:      Optional[float] = Field(None, gt=0)
    opis:           Optional[str]   = Field(None, min_length=2, max_length=500)
    sledeci_datum:  Optional[date]  = None
    klijent_id:     Optional[str]   = None
    predmet_id:     Optional[str]   = None
    pdv_procenat:   Optional[float] = Field(None, ge=0, le=100)
    aktivan:        Optional[bool]  = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _next_datum(od: date, ucestalost: str) -> date:
    if ucestalost == "mesecno":
        return od + relativedelta(months=1)
    if ucestalost == "kvartalno":
        return od + relativedelta(months=3)
    return od + relativedelta(years=1)


def _build_faktura_row(tpl: dict, uid: str) -> dict:
    bruto = round(tpl["iznos_rsd"] * (1 + tpl.get("pdv_procenat", 0) / 100), 2)
    return {
        "user_id":       uid,
        "klijent_id":    tpl.get("klijent_id"),
        "predmet_id":    tpl.get("predmet_id"),
        "opis":          tpl["opis"],
        "iznos_rsd":     tpl["iznos_rsd"],
        "pdv_procenat":  tpl.get("pdv_procenat", 0),
        "bruto_rsd":     bruto,
        "status":        "nacrt",
        "datum_izdavanja": date.today().isoformat(),
        "napomena":      f"Auto-generisana iz šablona: {tpl['naziv']}",
    }


# ─── POST /billing/recurring ─────────────────────────────────────────────────

@router.post("", status_code=201)
@limiter.limit("30/minute")
async def create_recurring(
    req:    RecurringCreateReq,
    request: Request,
    user:   dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    row = {
        "user_id":       uid,
        "naziv":         req.naziv.strip(),
        "ucestalost":    req.ucestalost,
        "iznos_rsd":     req.iznos_rsd,
        "opis":          req.opis.strip(),
        "sledeci_datum": req.sledeci_datum.isoformat(),
        "pdv_procenat":  req.pdv_procenat,
        "aktivan":       True,
    }
    if req.klijent_id:
        row["klijent_id"] = req.klijent_id
    if req.predmet_id:
        row["predmet_id"] = req.predmet_id

    res = await _db(lambda: supa.table("recurring_templates").insert(row).execute())
    if not res.data:
        raise HTTPException(status_code=500, detail="Greška pri kreiranju šablona.")

    return {"status": "kreiran", "template": res.data[0]}


# ─── GET /billing/recurring ──────────────────────────────────────────────────

@router.get("")
@limiter.limit("60/minute")
async def list_recurring(
    request: Request,
    aktivan: Optional[bool] = None,
    user:    dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    def _fetch():
        q = (supa.table("recurring_templates")
             .select("*")
             .eq("user_id", uid)
             .order("sledeci_datum", desc=False))
        if aktivan is not None:
            q = q.eq("aktivan", aktivan)
        return q.execute()

    res  = await _db(_fetch)
    rows = res.data or []

    return {
        "templates": rows,
        "total":     len(rows),
        "aktivnih":  sum(1 for r in rows if r.get("aktivan")),
    }


# ─── GET /billing/recurring/{id} ─────────────────────────────────────────────

@router.get("/{template_id}")
@limiter.limit("60/minute")
async def get_recurring(
    template_id: str,
    request:     Request,
    user:        dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    res = await _db(
        lambda: supa.table("recurring_templates")
        .select("*")
        .eq("id", template_id)
        .eq("user_id", uid)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Šablon nije pronađen.")
    return res.data


# ─── PATCH /billing/recurring/{id} ───────────────────────────────────────────

@router.patch("/{template_id}")
@limiter.limit("30/minute")
async def patch_recurring(
    template_id: str,
    req:         RecurringPatchReq,
    request:     Request,
    user:        dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    chk = await _db(
        lambda: supa.table("recurring_templates")
        .select("id")
        .eq("id", template_id)
        .eq("user_id", uid)
        .single()
        .execute()
    )
    if not chk.data:
        raise HTTPException(status_code=404, detail="Šablon nije pronađen.")

    updates: dict = {}
    for field in ("naziv", "ucestalost", "iznos_rsd", "opis",
                  "pdv_procenat", "klijent_id", "predmet_id", "aktivan"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val.strip() if isinstance(val, str) else val
    if req.sledeci_datum is not None:
        updates["sledeci_datum"] = req.sledeci_datum.isoformat()

    if not updates:
        raise HTTPException(status_code=422, detail="Nema polja za izmenu.")

    from datetime import datetime, timezone
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    res = await _db(
        lambda: supa.table("recurring_templates")
        .update(updates)
        .eq("id", template_id)
        .eq("user_id", uid)
        .execute()
    )
    return {"status": "izmenjeno", "template": (res.data or [{}])[0]}


# ─── DELETE /billing/recurring/{id} ──────────────────────────────────────────

@router.delete("/{template_id}", status_code=204)
@limiter.limit("20/minute")
async def delete_recurring(
    template_id: str,
    request:     Request,
    user:        dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    chk = await _db(
        lambda: supa.table("recurring_templates")
        .select("id, aktivan")
        .eq("id", template_id)
        .eq("user_id", uid)
        .single()
        .execute()
    )
    if not chk.data:
        raise HTTPException(status_code=404, detail="Šablon nije pronađen.")
    if chk.data.get("aktivan"):
        raise HTTPException(
            status_code=409,
            detail="Najpre deaktivirajte šablon (aktivan=false) pre brisanja."
        )

    await _db(
        lambda: supa.table("recurring_templates")
        .delete()
        .eq("id", template_id)
        .eq("user_id", uid)
        .execute()
    )


# ─── POST /billing/recurring/{id}/generiši ───────────────────────────────────

@router.post("/{template_id}/generiši", status_code=201)
@limiter.limit("20/minute")
async def generiši_iz_sablona(
    template_id: str,
    request:     Request,
    user:        dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    tpl_res = await _db(
        lambda: supa.table("recurring_templates")
        .select("*")
        .eq("id", template_id)
        .eq("user_id", uid)
        .single()
        .execute()
    )
    if not tpl_res.data:
        raise HTTPException(status_code=404, detail="Šablon nije pronađen.")

    tpl = tpl_res.data
    if not tpl.get("aktivan"):
        raise HTTPException(status_code=409, detail="Šablon je deaktiviran — ne može generisati fakturu.")

    faktura_row = _build_faktura_row(tpl, uid)
    fak_res = await _db(
        lambda: supa.table("fakture").insert(faktura_row).execute()
    )
    if not fak_res.data:
        raise HTTPException(status_code=500, detail="Greška pri kreiranju fakture.")

    faktura    = fak_res.data[0]
    novi_datum = _next_datum(
        date.fromisoformat(tpl["sledeci_datum"]),
        tpl["ucestalost"]
    )

    await _db(
        lambda: supa.table("recurring_templates")
        .update({"sledeci_datum": novi_datum.isoformat()})
        .eq("id", template_id)
        .execute()
    )

    logger.info("[RECURRING] Generisana faktura %s iz šablona %s", faktura["id"], template_id)
    return {
        "status":         "generisano",
        "faktura_id":     faktura["id"],
        "sledeci_datum":  novi_datum.isoformat(),
        "iznos_rsd":      faktura["iznos_rsd"],
        "bruto_rsd":      faktura["bruto_rsd"],
    }
