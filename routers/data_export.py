# -*- coding: utf-8 -*-
"""
GDPR Data Export — kancelarija preuzima sve svoje podatke.
GET /api/export/complete → ZIP sa JSON fajlovima.
"""
import io
import json
import logging
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.data_export")
router = APIRouter(prefix="/api/export", tags=["export"])

_README = """VINDEX AI — Export podataka
Datum: {datum}
Korisnik: {email}

Sadržaj:
  predmeti.json       — svi predmeti
  klijenti.json       — svi klijenti
  billing.json        — sve stavke naplate
  dokumenti.json      — metadata dokumenata (bez fajlova)
  beleske.json        — beleške uz predmete
  rocista.json        — ročišta
  hronologija.json    — automatski generisana hronologija
  komentari.json      — komentari uz predmete

Napomena: Fajlovi dokumenata (PDF, DOCX...) nisu uključeni u ovaj export.
Za preuzimanje fajlova kontaktirajte: support@vindex.ai

Prava: Imate pravo na prenosivost podataka prema ZZPL čl. 36 i GDPR čl. 20.
"""


async def _fetch(supa, table: str, uid: str, order: str = "created_at") -> list:
    try:
        r = supa.table(table).select("*").eq("user_id", uid).order(order).execute()
        return r.data or []
    except Exception as e:
        logger.warning("[EXPORT] %s greška: %s", table, e)
        return []


@router.get("/complete")
async def export_complete(user=Depends(get_current_user)):
    """
    Exportuje SVE podatke korisnika kao ZIP sa JSON fajlovima.
    GDPR čl. 20 — pravo na prenosivost podataka.
    """
    supa = _get_supa()
    uid  = user["user_id"]
    email = user.get("email", uid)
    now  = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")

    tables = [
        ("predmeti",          "predmeti.json",     "created_at"),
        ("klijenti",          "klijenti.json",     "created_at"),
        ("billing_entries",   "billing.json",      "created_at"),
        ("predmet_dokumenti", "dokumenti.json",    "created_at"),
        ("predmet_beleske",   "beleske.json",      "created_at"),
        ("rocista",           "rocista.json",      "datum"),
        ("predmet_hronologija","hronologija.json", "datum_iso"),
        ("predmet_komentari", "komentari.json",    "created_at"),
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        readme = _README.format(datum=now.replace("T", " "), email=email)
        zf.writestr("README.txt", readme)

        for table, fname, order in tables:
            data = await _fetch(supa, table, uid, order)
            zf.writestr(fname, json.dumps(data, ensure_ascii=False, indent=2, default=str))

    buf.seek(0)
    filename = f"vindex-export-{now}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
