# -*- coding: utf-8 -*-
"""
Vindex AI — Knowledge Hygiene

Sprecava digitalni haos: duplikati, zastarele lekcije, kontradikcije, niska potvrda.

POST /api/hygiene/skeniraj               — pokreni puno skeniranje
GET  /api/hygiene/report                 — pending akcije po tipu
GET  /api/hygiene/kontradikcije          — samo kontradikcije u case_patterns
POST /api/hygiene/arhiviraj-zastarele    — automatski arhiviraj sve zastarele
POST /api/hygiene/spoji/{id1}/{id2}      — spoji dve slicne lekcije
PATCH /api/hygiene/akcije/{id}           — markuj akciju kao sprovedeno / ignorisano
GET  /api/hygiene/zdravlje               — ukupni skor zdravlja knowledge baze
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from services.knowledge_hygiene import (
    archive_stale_lessons,
    merge_lessons,
    run_full_scan,
)

logger = logging.getLogger("vindex.knowledge_hygiene")
router = APIRouter(prefix="/api/hygiene", tags=["knowledge_hygiene"])

_VALIDNI_STATUSI = {"sprovedeno", "ignorisano"}


class AkcijaStatusRequest(BaseModel):
    status: str


@router.post("/skeniraj")
async def skeniraj(user=Depends(get_current_user)):
    """Pokrece kompletno skeniranje: duplikati, zastarele, kontradikcije, niska_potvrda.

    Upisuje nalaze u knowledge_hygiene_log. Preskace vec postojece pending nalaze.
    Vraca broj pronadjenih problema po kategoriji.
    """
    supa = _get_supa()
    try:
        result = await run_full_scan(supa, user["user_id"])
        return {
            **result,
            "poruka": (
                f"Skeniranje zavrseno. Pronadjeno {result['ukupno_pronadjeno']} problema "
                f"({result['novo_upisano']} novih). "
                "Pogledajte GET /api/hygiene/report za detalje."
            ),
        }
    except Exception as e:
        logger.error("skeniraj: %s", e)
        raise HTTPException(500, str(e))


@router.get("/report")
async def get_report(
    tip_akcije: Optional[str] = None,
    status: Optional[str] = "pending",
    limit: int = 50,
    user=Depends(get_current_user),
):
    """Lista hygiene nalaza. Filtriranje po tipu i statusu."""
    supa = _get_supa()
    try:
        q = (
            supa.table("knowledge_hygiene_log")
            .select("id, tip_akcije, entitet_tip, entitet_id, entitet2_id, opis, skor, status, created_at")
            .eq("user_id", user["user_id"])
            .order("created_at", desc=True)
            .limit(min(limit, 100))
        )
        if tip_akcije:
            q = q.eq("tip_akcije", tip_akcije)
        if status:
            q = q.eq("status", status)

        row = await asyncio.to_thread(lambda: q.execute())
        akcije = row.data or []

        # Grupisanje po tipu za pregled
        po_tipu: dict[str, int] = {}
        for a in akcije:
            tip = a.get("tip_akcije", "nepoznato")
            po_tipu[tip] = po_tipu.get(tip, 0) + 1

        return {
            "akcije": akcije,
            "ukupno": len(akcije),
            "po_tipu": po_tipu,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/kontradikcije")
async def get_kontradikcije(user=Depends(get_current_user)):
    """Kontradikcije u case_patterns: isti tip slucaja, razlicite preporuke."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("knowledge_hygiene_log")
            .select("id, entitet_id, entitet2_id, opis, status, created_at")
            .eq("user_id", user["user_id"])
            .eq("tip_akcije", "kontradikcija")
            .order("created_at", desc=True)
            .execute()
        )
        return {"kontradikcije": row.data or [], "ukupno": len(row.data or [])}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/arhiviraj-zastarele")
async def arhiviraj_zastarele(user=Depends(get_current_user)):
    """Automatski arhivira sve zastarele lekcije sa pending hygiene nalazima.

    Postavlja status_lekcije='zastarela' na svim flagovanim lekcijama.
    """
    supa = _get_supa()
    try:
        result = await archive_stale_lessons(supa, user["user_id"])
        return {
            **result,
            "poruka": (
                f"Arhivirano {result['arhivirano']} zastarelih lekcija."
                if result["arhivirano"] > 0
                else "Nema zastarelih lekcija za arhiviranje. Pokrenite /skeniraj prvo."
            ),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/spoji/{zadrzi_id}/{arhiviraj_id}")
async def spoji_lekcije(zadrzi_id: str, arhiviraj_id: str, user=Depends(get_current_user)):
    """Spaja dve slicne lekcije.

    zadrzi_id  — lekcija koja ostaje (akumulira br_predmeta obe)
    arhiviraj_id — lekcija koja se arhivira (status_lekcije='zastarela')
    """
    if zadrzi_id == arhiviraj_id:
        raise HTTPException(400, "zadrzi_id i arhiviraj_id moraju biti razliciti")
    supa = _get_supa()
    try:
        result = await merge_lessons(supa, user["user_id"], zadrzi_id, arhiviraj_id)
        return {
            **result,
            "poruka": f"Lekcije spojene. Zadrzana: {zadrzi_id}, arhivirana: {arhiviraj_id}.",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.patch("/akcije/{akcija_id}")
async def update_akcija_status(
    akcija_id: str,
    body: AkcijaStatusRequest,
    user=Depends(get_current_user),
):
    """Markuj hygiene akciju kao sprovedeno ili ignorisano."""
    if body.status not in _VALIDNI_STATUSI:
        raise HTTPException(400, f"status mora biti: {', '.join(_VALIDNI_STATUSI)}")

    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("knowledge_hygiene_log")
            .update({"status": body.status, "updated_at": "now()"})
            .eq("id", akcija_id)
            .eq("user_id", user["user_id"])
            .execute()
        )
        if not row.data:
            raise HTTPException(404, "Akcija nije pronadjena")
        return {"akcija_id": akcija_id, "status": body.status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/zdravlje")
async def get_zdravlje_baze(user=Depends(get_current_user)):
    """Ukupni skor zdravlja knowledge baze (0-100).

    Uzima u obzir: procenat pendingproblema vs ukupno lekcija, kontradikcije, niska_potvrda.
    """
    supa = _get_supa()
    try:
        lekcije_row, pending_row, sprovedeno_row = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("lessons_learned")
                .select("id", count="exact")
                .eq("user_id", user["user_id"])
                .in_("status_lekcije", ["predlog_ai", "usvojena_praksa"])
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("knowledge_hygiene_log")
                .select("tip_akcije")
                .eq("user_id", user["user_id"])
                .eq("status", "pending")
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("knowledge_hygiene_log")
                .select("id", count="exact")
                .eq("user_id", user["user_id"])
                .eq("status", "sprovedeno")
                .execute()
            ),
        )

        ukupno_lekcija = lekcije_row.count or 0
        pending = pending_row.data or []
        sprovedeno = sprovedeno_row.count or 0

        pending_po_tipu: dict[str, int] = {}
        for p in pending:
            t = p.get("tip_akcije", "nepoznato")
            pending_po_tipu[t] = pending_po_tipu.get(t, 0) + 1

        ukupno_pending = len(pending)
        penalizacija = 0

        if ukupno_lekcija > 0:
            penalizacija += min(ukupno_pending / ukupno_lekcija * 50, 40)

        penalizacija += pending_po_tipu.get("kontradikcija", 0) * 5
        penalizacija += pending_po_tipu.get("duplikat", 0) * 2
        penalizacija += pending_po_tipu.get("zastarela", 0) * 1
        penalizacija += pending_po_tipu.get("niska_potvrda", 0) * 1

        skor = max(0, round(100 - penalizacija))
        ocena = (
            "Odlicno" if skor >= 85
            else "Dobro" if skor >= 70
            else "Potrebna paznja" if skor >= 50
            else "Kriticno — pokrenite hygiene odmah"
        )

        return {
            "skor_zdravlja": skor,
            "ocena": ocena,
            "ukupno_aktivnih_lekcija": ukupno_lekcija,
            "pending_problemi": ukupno_pending,
            "pending_po_tipu": pending_po_tipu,
            "sprovedenih_akcija_ikad": sprovedeno,
            "preporuka": (
                "Baza je u dobrom stanju." if skor >= 70
                else f"Pokrenite POST /api/hygiene/skeniraj i resajte {ukupno_pending} pending problema."
            ),
        }
    except Exception as e:
        raise HTTPException(500, str(e))
