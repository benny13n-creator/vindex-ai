# -*- coding: utf-8 -*-
"""
Vindex AI — routers/komentari.py

F8.1: Komentari na predmetima (CRUD)
"""
import asyncio
import logging
from datetime import datetime as _dt, timezone as _tz

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from security.html_sanitize import sanitize_user_input
from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.api")
router = APIRouter()


class KomentarRequest(BaseModel):
    tekst: str = Field(..., min_length=1, max_length=2000)

    @field_validator("tekst")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        return sanitize_user_input(v) or ""


class KomentarUpdateRequest(BaseModel):
    tekst: str = Field(..., min_length=1, max_length=2000)

    @field_validator("tekst")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        return sanitize_user_input(v) or ""


@router.post("/predmeti/{predmet_id}/komentari")  # F8.1
@limiter.limit("30/minute")
async def post_komentar(
    predmet_id: str,
    req: KomentarRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """F8.1 — Dodaj komentar na predmet (samo vlasnik predmeta)."""
    uid = user["user_id"]
    supa = _get_supa()

    # Verify predmet ownership before allowing comment
    own = await asyncio.to_thread(
        lambda: supa.table("predmeti")
                    .select("id")
                    .eq("id", predmet_id)
                    .eq("user_id", uid)
                    .maybe_single()
                    .execute()
    )
    if not own.data:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Pristup predmetu nije dozvoljen.")

    res = await asyncio.to_thread(
        lambda: supa.table("predmet_komentari").insert({
            "predmet_id": predmet_id,
            "user_id":    uid,
            "tekst":      req.tekst.strip(),
        }).execute()
    )
    return {"status": "dodat", "komentar": res.data[0] if res.data else {}}


@router.get("/predmeti/{predmet_id}/komentari")  # F8.1
@limiter.limit("60/minute")
async def get_komentari(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """F8.1 — Lista komentara za predmet (samo vlasnik predmeta)."""
    uid = user["user_id"]
    supa = _get_supa()

    # Verify predmet ownership — service_role bypasses RLS so we enforce manually
    own = await asyncio.to_thread(
        lambda: supa.table("predmeti")
                    .select("id")
                    .eq("id", predmet_id)
                    .eq("user_id", uid)
                    .maybe_single()
                    .execute()
    )
    if not own.data:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Pristup predmetu nije dozvoljen.")

    res = await asyncio.to_thread(
        lambda: supa.table("predmet_komentari")
                    .select("*")
                    .eq("predmet_id", predmet_id)
                    .order("created_at", desc=False)
                    .execute()
    )
    return {"komentari": res.data or []}


@router.put("/komentari/{komentar_id}")  # F8.1
@limiter.limit("20/minute")
async def put_komentar(
    komentar_id: str,
    req: KomentarUpdateRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """F8.1 — Izmeni komentar (samo vlasnik)."""
    supa = _get_supa()
    now = _dt.now(_tz.utc).isoformat()
    await asyncio.to_thread(
        lambda: supa.table("predmet_komentari")
                    .update({"tekst": req.tekst.strip(), "izmenjeno": now})
                    .eq("id", komentar_id)
                    .eq("user_id", user["user_id"])
                    .execute()
    )
    return {"status": "izmenjeno"}


@router.delete("/komentari/{komentar_id}")  # F8.1
@limiter.limit("20/minute")
async def delete_komentar(
    komentar_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """F8.1 — Obriši komentar (samo vlasnik)."""
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("predmet_komentari")
                    .delete()
                    .eq("id", komentar_id)
                    .eq("user_id", user["user_id"])
                    .execute()
    )
    return {"status": "obrisan"}
