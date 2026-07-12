# -*- coding: utf-8 -*-
"""
Vindex AI — routers/export.py

F6.1: DOCX export
F6.3: API ključevi + v1/query eksterni API
Phase 5.3: PDF export predmeta
"""
import asyncio
import re as _re
import secrets as _secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response as _Resp
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user, require_pro
from docx_export import tekst_u_docx as _tekst_u_docx

router = APIRouter()


class DocxExportRequest(BaseModel):
    naslov: str = Field(default="Vindex analiza", max_length=200)
    tekst:  str = Field(..., max_length=50000)
    tip:    str = Field(default="analiza", max_length=20)


class ApiKljucRequest(BaseModel):
    naziv: str = Field(default="Default", max_length=50)


def _generiši_api_kljuc() -> str:
    return "vndx_" + _secrets.token_urlsafe(32)


@router.post("/export/docx")  # F6.1
async def post_export_docx(req: DocxExportRequest, user: dict = Depends(get_current_user)):
    """F6.1 — Export teksta kao formatiran .docx fajl."""
    import re as _re
    if len(req.tekst.strip()) < 20:
        raise HTTPException(status_code=422, detail="Tekst je prekratak za export.")
    docx_bytes = await asyncio.to_thread(_tekst_u_docx, req.naslov, req.tekst, req.tip)
    safe = _re.sub(r"[^\w\-]", "_", req.naslov)[:50]
    filename = f"vindex_{safe}.docx"
    return _Resp(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api-kljucevi/novi")  # F6.3
async def post_novi_api_kljuc(req: ApiKljucRequest, user: dict = Depends(require_pro)):
    """F6.3 — Generiši novi API ključ (PRO only, max 3)."""
    supa = _get_supa()
    existing = await asyncio.to_thread(
        lambda: supa.table("api_kljucevi")
                    .select("id")
                    .eq("user_id", user["user_id"])
                    .eq("aktivan", True)
                    .execute()
    )
    if existing.data and len(existing.data) >= 3:
        raise HTTPException(status_code=400, detail="Maksimalan broj API ključeva (3) je dostignut.")
    kljuc = _generiši_api_kljuc()
    await asyncio.to_thread(
        lambda: supa.table("api_kljucevi").insert({
            "user_id": user["user_id"],
            "kljuc":   kljuc,
            "naziv":   req.naziv,
        }).execute()
    )
    return {"kljuc": kljuc, "naziv": req.naziv, "napomena": "Sačuvajte ključ — neće biti ponovo prikazan."}


@router.get("/api-kljucevi/lista")  # F6.3
async def get_api_kljucevi(user: dict = Depends(require_pro)):
    """F6.3 — Lista API ključeva korisnika (bez samih ključeva)."""
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("api_kljucevi")
                    .select("id, naziv, aktivan, kreirano, poslednje_koriscenje, broj_poziva")
                    .eq("user_id", user["user_id"])
                    .order("kreirano", desc=True)
                    .execute()
    )
    return {"kljucevi": res.data or []}


@router.delete("/api-kljucevi/{kljuc_id}")  # F6.3
async def delete_api_kljuc(kljuc_id: str, user: dict = Depends(get_current_user)):
    """F6.3 — Opozovi API ključ (označava kao neaktivan)."""
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("api_kljucevi")
                    .update({"aktivan": False})
                    .eq("id", kljuc_id)
                    .eq("user_id", user["user_id"])
                    .execute()
    )
    return {"status": "opozvan"}


@router.post("/v1/query")  # F6.3 — eksterni API
async def post_v1_query(request: Request):
    """F6.3 — Eksterni API endpoint — autentifikacija via X-Vindex-Key header."""
    api_key = (
        request.headers.get("X-Vindex-Key")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
    )
    if not api_key or not api_key.startswith("vndx_"):
        raise HTTPException(status_code=401, detail="API ključ je obavezan. Header: X-Vindex-Key: vndx_...")
    supa = _get_supa()
    try:
        res = await asyncio.to_thread(
            lambda: supa.table("api_kljucevi")
                        .select("user_id, aktivan, naziv, broj_poziva")
                        .eq("kljuc", api_key)
                        .eq("aktivan", True)
                        .execute()
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Servis privremeno nedostupan.")
    if not res.data:
        raise HTTPException(status_code=401, detail="Nevažeći ili neaktivni API ključ.")
    key_row = res.data[0]
    try:
        await asyncio.to_thread(
            lambda: supa.table("api_kljucevi")
                        .update({"broj_poziva": key_row.get("broj_poziva", 0) + 1})
                        .eq("kljuc", api_key)
                        .execute()
        )
    except Exception:
        pass
    body = await request.json()
    upit = (body.get("upit") or "").strip()
    if len(upit) < 3:
        raise HTTPException(status_code=422, detail="Polje 'upit' je obavezno (min 3 karaktera).")
    return {
        "upit":    upit,
        "napomena": "v1 API beta — odgovor dostupan u sledećoj verziji.",
    }


# ─── Phase 5.3 — PDF export predmeta ─────────────────────────────────────────

def _generiši_pdf(predmet, dokumenti, beleske, hronologija) -> bytes:
    from predmet_pdf import generiši_predmet_pdf
    return generiši_predmet_pdf(predmet, dokumenti, beleske, hronologija)


@router.get("/api/predmeti/{predmet_id}/pdf-export")  # Phase 5.3
async def get_predmet_pdf_export(predmet_id: str, user: dict = Depends(get_current_user)):
    """Phase 5.3 — Generisanje PDF izveštaja za predmet (sve sekcije)."""
    supa = _get_supa()
    uid  = user["user_id"]

    predmet_res = await asyncio.to_thread(
        lambda: supa.table("predmeti")
                     .select("*")
                     .eq("id", predmet_id)
                     .eq("user_id", uid)
                     .maybe_single()
                     .execute()
    )
    if not predmet_res.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    predmet = predmet_res.data

    docs_res, beleske_res, hron_res = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                         .select("naziv_fajla, status, velicina_kb, created_at")
                         .eq("predmet_id", predmet_id)
                         .eq("user_id", uid)
                         .order("created_at")
                         .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_beleske")
                         .select("sadrzaj, created_at")
                         .eq("predmet_id", predmet_id)
                         .eq("user_id", uid)
                         .order("created_at")
                         .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                         .select("dogadjaj, akter, datum, datum_iso, vaznost")
                         .eq("predmet_id", predmet_id)
                         .eq("user_id", uid)
                         .order("datum_iso", desc=False)
                         .execute()
        ),
    )

    try:
        pdf_bytes = await asyncio.to_thread(
            _generiši_pdf,
            predmet,
            docs_res.data or [],
            beleske_res.data or [],
            hron_res.data or [],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Greška pri generisanju PDF-a: {exc}")

    _SRLATMAP  = str.maketrans("žšćčđŽŠĆČĐ", "zsccdZSCCD")
    raw_naziv  = (predmet.get("naziv") or "predmet").translate(_SRLATMAP)
    safe_naziv = _re.sub(r"[^a-zA-Z0-9\-_]", "_", raw_naziv)[:50]
    filename   = f"vindex_predmet_{safe_naziv}.pdf"

    return _Resp(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
