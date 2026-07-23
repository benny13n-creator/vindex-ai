# -*- coding: utf-8 -*-
"""
Vindex AI — routers/import_klijenti.py

CSV/XLSX bulk import klijenata.

Endpoints:
  GET  /api/klijenti/import/template  — preuzmi CSV template fajl
  POST /api/klijenti/import/preview   — preview prvih 5 redova + predloženo mapiranje kolona
  POST /api/klijenti/import/execute   — izvrši import posle korisnikove potvrde
"""
from __future__ import annotations

import asyncio
import base64
import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from security.crypto import encrypt_field
from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.import_klijenti")
router = APIRouter(tags=["import"])

VINDEX_POLJA = [
    "ime", "prezime", "naziv_kompanije", "email",
    "telefon", "pib", "adresa", "grad", "tip_klijenta",
]

_KOL_HINTS: dict[str, str] = {
    "ime": "ime", "first": "ime", "name": "ime",
    "prezime": "prezime", "lastname": "prezime", "surname": "prezime",
    "naziv": "naziv_kompanije", "kompanija": "naziv_kompanije",
    "firma": "naziv_kompanije", "company": "naziv_kompanije",
    "email": "email", "mail": "email", "e-mail": "email",
    "telefon": "telefon", "tel": "telefon", "mobil": "telefon",
    "gsm": "telefon", "phone": "telefon",
    "pib": "pib", "poreski": "pib", "tax": "pib",
    "adresa": "adresa", "ulica": "adresa", "address": "adresa",
    "grad": "grad", "mesto": "grad", "city": "grad",
    "tip": "tip_klijenta", "type": "tip_klijenta",
}


def _predlozi_mapiranje(kolone: list[str]) -> dict[str, Optional[str]]:
    mapping: dict[str, Optional[str]] = {}
    for k in kolone:
        kl = k.lower().strip().replace(" ", "_").replace("-", "_")
        # Exact match first
        if kl in VINDEX_POLJA:
            mapping[k] = kl
            continue
        # Hint lookup — check if any hint key is contained in column name
        matched = None
        for hint, polje in _KOL_HINTS.items():
            if hint in kl:
                matched = polje
                break
        mapping[k] = matched
    return mapping


def _parse_csv(content: bytes) -> tuple[list[str], list[dict]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1250", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    kolone: list[str] = list(reader.fieldnames or [])
    redovi = [dict(row) for _, row in zip(range(5), reader)]
    return kolone, redovi


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict]]:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=400, detail="XLSX nije podržan na serveru — koristite CSV.")
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], []
    kolone = [str(c or "").strip() for c in rows[0]]
    redovi = [
        {kolone[i]: str(v or "").strip() for i, v in enumerate(row) if i < len(kolone)}
        for row in rows[1:6]
    ]
    return kolone, redovi


# ── Template ──────────────────────────────────────────────────────────────────

@router.get("/api/klijenti/import/template")
async def import_template(user: dict = Depends(get_current_user)):
    """Preuzmi prazan CSV template za import klijenata."""
    lines = [
        "ime,prezime,naziv_kompanije,email,telefon,pib,adresa,grad,tip_klijenta",
        "Petar,Petrović,,petar@email.com,+381601234567,,,Beograd,fizicko",
        ",,DOO Primer d.o.o.,info@primer.rs,0112345678,123456789,Knez Mihailova 10,Beograd,pravno",
    ]
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=vindex_import_template.csv"},
    )


# ── Preview ───────────────────────────────────────────────────────────────────

@router.post("/api/klijenti/import/preview")
@limiter.limit("10/minute")
async def import_preview(
    request: Request,
    fajl: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Prima CSV ili XLSX; vraća prvih 5 redova i predloženo mapiranje kolona."""
    content = await fajl.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fajl je prevelik (max 10 MB).")

    filename = (fajl.filename or "").lower()
    if filename.endswith((".xlsx", ".xls")):
        kolone, redovi = _parse_xlsx(content)
    else:
        kolone, redovi = _parse_csv(content)

    if not kolone:
        raise HTTPException(status_code=400, detail="Fajl je prazan ili nema zaglavlja.")

    return {
        "kolone": kolone,
        "predlozeno_mapiranje": _predlozi_mapiranje(kolone),
        "preview_redovi": redovi,
        "ukupno_kolona": len(kolone),
        "vindex_polja": VINDEX_POLJA,
    }


# ── Execute ───────────────────────────────────────────────────────────────────

class ImportExecuteRequest(BaseModel):
    mapiranje: dict[str, Optional[str]]
    csv_base64: str


@router.post("/api/klijenti/import/execute")
@limiter.limit("5/minute")
async def import_execute(
    request: Request,
    payload: ImportExecuteRequest,
    user: dict = Depends(get_current_user),
):
    """Izvrši import klijenata iz base64-enkodovanog CSV-a."""
    uid = user["user_id"]
    supa = _get_supa()

    try:
        raw = base64.b64decode(payload.csv_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Neispravan base64 sadržaj.")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    rezultati: dict = {"uvezeno": 0, "duplikati": 0, "greske": 0, "detalji": []}

    # Dohvati postojeće emailove za duplikat check
    existing_emails: set[str] = set()
    try:
        ex_r = await asyncio.to_thread(
            lambda: supa.table("klijenti").select("email").eq("user_id", uid).execute()
        )
        existing_emails = {r["email"].lower() for r in (ex_r.data or []) if r.get("email")}
    except Exception:
        pass

    BATCH_SIZE = 25
    batch: list[dict] = []

    async def _flush(b: list[dict]) -> None:
        await asyncio.to_thread(
            lambda: supa.table("klijenti").insert(b).execute()
        )

    for row in reader:
        klijent: dict = {"user_id": uid}
        for csv_col, vindex_polje in payload.mapiranje.items():
            if vindex_polje and csv_col in row:
                val = str(row[csv_col] or "").strip()
                if not val:
                    continue
                if vindex_polje == "pib":
                    # SEC-009 — isti put kao ručni unos (klijenti/router.py:225):
                    # PIB je CONFIDENTIAL polje, NIKAD plaintext u bazi. Ranije je
                    # ovde pisano direktno u "pib" — kolona koja ne postoji u šemi
                    # (samo pib_encrypted postoji), pa je svaki red sa PIB-om
                    # tiho padao kao deo neuspešnog batch-a.
                    klijent["pib_encrypted"] = await asyncio.to_thread(encrypt_field, val)
                else:
                    klijent[vindex_polje] = val

        # Mora imati bar neko ime
        if not (klijent.get("ime") or klijent.get("naziv_kompanije")):
            rezultati["greske"] += 1
            rezultati["detalji"].append({"status": "greska", "razlog": "Nema imena ni naziva kompanije", "red": dict(row)})
            continue

        # Duplikat check po emailu
        email = (klijent.get("email") or "").strip().lower()
        if email and email in existing_emails:
            rezultati["duplikati"] += 1
            rezultati["detalji"].append({"status": "duplikat", "email": email})
            continue
        if email:
            existing_emails.add(email)

        # Default tip_klijenta
        if "tip_klijenta" not in klijent:
            klijent["tip_klijenta"] = "pravno" if klijent.get("naziv_kompanije") else "fizicko"

        batch.append(klijent)

        if len(batch) >= BATCH_SIZE:
            try:
                await _flush(batch)
                rezultati["uvezeno"] += len(batch)
            except Exception as e:
                logger.error("Import batch greška: %s", e)
                rezultati["greske"] += len(batch)
            batch.clear()

    if batch:
        try:
            await _flush(batch)
            rezultati["uvezeno"] += len(batch)
        except Exception as e:
            logger.error("Import final batch greška: %s", e)
            rezultati["greske"] += len(batch)

    logger.info(
        "Import završen za %s: uvezeno=%d duplikati=%d greske=%d",
        uid[:8], rezultati["uvezeno"], rezultati["duplikati"], rezultati["greske"],
    )
    return rezultati
