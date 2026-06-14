# -*- coding: utf-8 -*-
"""
Vindex AI — routers/tarife.py
Personalizovane tarife

GET  /api/tarife/moja-satnica          — globalna satnica korisnika
PUT  /api/tarife/moja-satnica          — postavi globalnu satnicu
GET  /api/tarife/klijent/{klijent_id} — per-klijent tarifa
PUT  /api/tarife/klijent/{klijent_id} — postavi / ukloni per-klijent tarifu
GET  /api/tarife/stavke                — AKS stavke T01-T30 + custom overlay
PUT  /api/tarife/stavke/{kod}          — postavi / vrati na default za stavku
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
from routers.billing import AKS_TARIFA, BOD_RSD

logger = logging.getLogger("vindex.tarife")
router = APIRouter(prefix="/api/tarife", tags=["tarife"])


async def _db(fn):
    return await asyncio.to_thread(fn)


def _first(r) -> Optional[dict]:
    """Uzima prvi red iz APIResponse (limit(1) uvek vraca listu)."""
    return r.data[0] if r.data else None


# ─── resolve helpers (used by billing.py) ─────────────────────────────────────

async def resolve_tarifa(supa, uid: str, klijent_id: Optional[str] = None) -> float:
    """Hijerarhija: per-klijent → globalna → AKS default 7500."""
    if klijent_id:
        r = await _db(lambda: supa.table("tarife")
                      .select("tarifa_po_satu")
                      .eq("user_id", uid)
                      .eq("klijent_id", klijent_id)
                      .limit(1)
                      .execute())
        row = _first(r)
        if row and row.get("tarifa_po_satu"):
            return float(row["tarifa_po_satu"])
    r = await _db(lambda: supa.table("tarife")
                  .select("tarifa_po_satu")
                  .eq("user_id", uid)
                  .is_("klijent_id", "null")
                  .limit(1)
                  .execute())
    row = _first(r)
    if row and row.get("tarifa_po_satu"):
        return float(row["tarifa_po_satu"])
    return 7500.0


async def resolve_tarifne_stavke(supa, uid: str) -> dict[str, dict]:
    """
    Vraća dict kod → {naziv, iznos_rsd, bodovi, is_custom}
    Hijerarhija: user custom → AKS default
    """
    r = await _db(lambda: supa.table("tarifne_stavke_custom")
                  .select("kod,naziv,iznos")
                  .eq("user_id", uid)
                  .execute())
    custom: dict[str, dict] = {row["kod"]: row for row in (r.data or [])}

    result: dict[str, dict] = {}
    for kod, t in AKS_TARIFA.items():
        aks_iznos = t.get("fiksno_rsd") or (t["bodovi"] * BOD_RSD if t.get("bodovi") else 0)
        c = custom.get(kod)
        result[kod] = {
            "naziv":     c["naziv"] if c and c.get("naziv") else t["naziv"],
            "iznos_rsd": float(c["iznos"]) if c else float(aks_iznos),
            "bodovi":    t.get("bodovi"),
            "is_custom": bool(c),
            "aks_iznos": float(aks_iznos),
        }
    return result


# ─── Pydantic models ──────────────────────────────────────────────────────────

class SatnicaReq(BaseModel):
    tarifa_po_satu: float = Field(..., gt=0, le=1_000_000)


class KlijentTarifaReq(BaseModel):
    tarifa_po_satu: Optional[float] = Field(default=None, gt=0, le=1_000_000)


class StavkaReq(BaseModel):
    iznos:  Optional[float] = Field(default=None, ge=0, le=1_000_000)
    naziv:  Optional[str]   = Field(default=None, max_length=300)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/moja-satnica")
@limiter.limit("60/minute")
async def get_moja_satnica(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()
    r   = await _db(lambda: supa.table("tarife")
                    .select("tarifa_po_satu,updated_at")
                    .eq("user_id", uid)
                    .is_("klijent_id", "null")
                    .limit(1)
                    .execute())
    row = _first(r)
    if row:
        return {"tarifa_po_satu": float(row["tarifa_po_satu"]), "source": "custom", "updated_at": row.get("updated_at")}
    return {"tarifa_po_satu": 7500.0, "source": "default"}


@router.put("/moja-satnica")
@limiter.limit("30/minute")
async def put_moja_satnica(
    body: SatnicaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    ex_r = await _db(lambda: supa.table("tarife")
                     .select("id")
                     .eq("user_id", uid)
                     .is_("klijent_id", "null")
                     .limit(1)
                     .execute())
    existing = _first(ex_r)

    if existing:
        r = await _db(lambda: supa.table("tarife")
                      .update({"tarifa_po_satu": body.tarifa_po_satu})
                      .eq("id", existing["id"])
                      .execute())
    else:
        r = await _db(lambda: supa.table("tarife")
                      .insert({"user_id": uid, "klijent_id": None, "tarifa_po_satu": body.tarifa_po_satu})
                      .execute())

    if not r.data:
        raise HTTPException(status_code=500, detail="Greška pri čuvanju satnice.")

    logger.info("[TARIFA] satnica uid=%.8s iznos=%.2f", uid, body.tarifa_po_satu)
    return {"ok": True, "tarifa_po_satu": float(r.data[0]["tarifa_po_satu"])}


@router.get("/klijent/{klijent_id}")
@limiter.limit("60/minute")
async def get_klijent_tarifa(
    klijent_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()
    r   = await _db(lambda: supa.table("tarife")
                    .select("tarifa_po_satu,updated_at")
                    .eq("user_id", uid)
                    .eq("klijent_id", klijent_id)
                    .limit(1)
                    .execute())
    row = _first(r)
    if row:
        return {"klijent_id": klijent_id, "tarifa_po_satu": float(row["tarifa_po_satu"]), "source": "custom", "updated_at": row.get("updated_at")}
    global_satnica = await resolve_tarifa(supa, uid)
    return {"klijent_id": klijent_id, "tarifa_po_satu": global_satnica, "source": "default"}


@router.put("/klijent/{klijent_id}")
@limiter.limit("30/minute")
async def put_klijent_tarifa(
    klijent_id: str,
    body: KlijentTarifaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    ex_r = await _db(lambda: supa.table("tarife")
                     .select("id")
                     .eq("user_id", uid)
                     .eq("klijent_id", klijent_id)
                     .limit(1)
                     .execute())
    existing = _first(ex_r)

    if body.tarifa_po_satu is None:
        if existing:
            await _db(lambda: supa.table("tarife").delete().eq("id", existing["id"]).execute())
        return {"ok": True, "removed": True}

    if existing:
        r = await _db(lambda: supa.table("tarife")
                      .update({"tarifa_po_satu": body.tarifa_po_satu})
                      .eq("id", existing["id"])
                      .execute())
    else:
        r = await _db(lambda: supa.table("tarife")
                      .insert({"user_id": uid, "klijent_id": klijent_id, "tarifa_po_satu": body.tarifa_po_satu})
                      .execute())

    if not r.data:
        raise HTTPException(status_code=500, detail="Greška pri čuvanju tarife klijenta.")

    logger.info("[TARIFA] klijent uid=%.8s klijent=%.8s iznos=%.2f", uid, klijent_id, body.tarifa_po_satu)
    return {"ok": True, "klijent_id": klijent_id, "tarifa_po_satu": float(r.data[0]["tarifa_po_satu"])}


@router.get("/stavke")
@limiter.limit("60/minute")
async def get_stavke(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()
    resolved = await resolve_tarifne_stavke(supa, uid)
    stavke = [
        {
            "sifra":     kod,
            "naziv":     v["naziv"],
            "bodovi":    v["bodovi"],
            "aks_iznos": v["aks_iznos"],
            "iznos_rsd": v["iznos_rsd"],
            "is_custom": v["is_custom"],
        }
        for kod, v in resolved.items()
    ]
    return {"stavke": stavke, "bod_rsd": BOD_RSD}


@router.put("/stavke/{kod}")
@limiter.limit("30/minute")
async def put_stavka(
    kod: str,
    body: StavkaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()
    kod  = kod.upper()

    if kod not in AKS_TARIFA:
        raise HTTPException(status_code=404, detail=f"Tarifa '{kod}' ne postoji.")

    if body.iznos is None and body.naziv is None:
        await _db(lambda: supa.table("tarifne_stavke_custom")
                  .delete()
                  .eq("user_id", uid)
                  .eq("kod", kod)
                  .execute())
        return {"ok": True, "removed": True, "kod": kod}

    ex_r = await _db(lambda: supa.table("tarifne_stavke_custom")
                     .select("id")
                     .eq("user_id", uid)
                     .eq("kod", kod)
                     .limit(1)
                     .execute())
    existing = _first(ex_r)

    update_data: dict = {}
    if body.iznos is not None:
        update_data["iznos"] = body.iznos
    if body.naziv is not None:
        update_data["naziv"] = body.naziv.strip() or None

    if existing:
        r = await _db(lambda: supa.table("tarifne_stavke_custom")
                      .update(update_data)
                      .eq("id", existing["id"])
                      .execute())
    else:
        if body.iznos is None:
            raise HTTPException(status_code=422, detail="iznos je obavezan pri prvom setovanju stavke.")
        r = await _db(lambda: supa.table("tarifne_stavke_custom")
                      .insert({"user_id": uid, "kod": kod, **update_data})
                      .execute())

    if not r.data:
        raise HTTPException(status_code=500, detail="Greška pri čuvanju stavke.")

    logger.info("[TARIFA] stavka uid=%.8s kod=%s iznos=%s", uid, kod, body.iznos)
    return {"ok": True, "kod": kod, "iznos": r.data[0]["iznos"]}
