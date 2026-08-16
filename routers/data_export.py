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

from fastapi import APIRouter, Depends, HTTPException
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


class ExportIncomplete(Exception):
    """One or more tables could not be read for a portability export.

    S4-4 (2026-08-09). _fetch swallowed every read error into [], and the
    endpoint shipped the ZIP regardless. So a transient database error meant the
    data subject received an export that was MISSING ENTIRE TABLES, labelled by
    its own README as a complete ZZPL čl. 36 / GDPR čl. 20 portability export.

    An incomplete export presented as complete is worse than no export: the
    recipient has no way to know what is absent, and completeness is the entire
    point of the right being exercised. Fail instead, and name the tables.
    """


async def _fetch(supa, table: str, uid: str, order: str = "created_at",
                 errors: list | None = None) -> list:
    try:
        r = supa.table(table).select("*").eq("user_id", uid).order(order).execute()
        return r.data or []
    except Exception as e:
        logger.error("[EXPORT] %s greška — export je NEPOTPUN: %s", table, e)
        if errors is not None:
            errors.append(table)
        return []


@router.get("/complete")
async def export_complete(user=Depends(get_current_user)):
    """
    Exportuje SVE podatke korisnika kao ZIP sa JSON fajlovima.
    GDPR čl. 20 — pravo na prenosivost podataka.
    """
    from shared.audit_immutable import log_action as _imm_log
    import asyncio as _aio

    supa = _get_supa()
    uid  = user["user_id"]
    email = user.get("email", uid)
    now  = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")

    # Zabeleži export u nepromenjivi audit log — GDPR čl. 20 praćenje
    _aio.create_task(_imm_log(
        "data_export",
        user_id=uid,
        resource_type="all_user_data",
        metadata={"email": email, "format": "zip"},
    ))

    # NS001 — kolona za sortiranje mora postojati na TOJ tabeli, inače
    # PostgREST odbija ceo upit (42703), `_fetch` je upiše u `_failed`, i ZIP se
    # odbacuje. `klijenti` i `predmet_komentari` nemaju `created_at` nego
    # `kreirano` -- mereno sondom `select(<kolona>)&limit=0` nad produkcijskom
    # bazom i potvrdjeno stvarnim pozivom: `GET /api/export/complete` je vraćao
    # HTTP 503 "podaci iz sledećih tabela nisu mogli da se pročitaju: klijenti,
    # predmet_komentari". Dakle prenosivost podataka (ZZPL čl. 36 / GDPR čl. 20)
    # nije radila ni za jednog korisnika.
    tables = [
        ("predmeti",          "predmeti.json",     "created_at"),
        ("klijenti",          "klijenti.json",     "kreirano"),
        ("billing_entries",   "billing.json",      "created_at"),
        ("predmet_dokumenti", "dokumenti.json",    "created_at"),
        ("predmet_beleske",   "beleske.json",      "created_at"),
        ("rocista",           "rocista.json",      "datum"),
        ("predmet_hronologija","hronologija.json", "datum_iso"),
        ("predmet_komentari", "komentari.json",    "kreirano"),
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        readme = _README.format(datum=now.replace("T", " "), email=email)
        zf.writestr("README.txt", readme)

        _failed: list[str] = []
        for table, fname, order in tables:
            data = await _fetch(supa, table, uid, order, errors=_failed)
            zf.writestr(fname, json.dumps(data, ensure_ascii=False, indent=2, default=str))

    # S4-4: never hand the data subject a partial archive that calls itself
    # complete. The ZIP is discarded rather than shipped.
    if _failed:
        raise HTTPException(
            status_code=503,
            detail=(
                "Export nije kompletan — podaci iz sledećih tabela nisu mogli da se "
                f"pročitaju: {', '.join(_failed)}. Nepotpun export vam nije poslat "
                "jer bi izgledao kao potpun. Pokušajte ponovo za koji minut."
            ),
        )

    buf.seek(0)
    filename = f"vindex-export-{now}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
