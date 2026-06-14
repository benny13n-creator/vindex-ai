# -*- coding: utf-8 -*-
"""
Vindex AI — routers/kalendar.py
Faza 1: Centralizovani Kalendar

GET  /api/kalendar/pregled   — agregira ročišta + predmet_hronologija u date range
POST /api/kalendar/ics       — izvoz agregiranih događaja u .ics fajl
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.kalendar")
router = APIRouter(tags=["kalendar"])

_STATUS_EMOJI = {
    "zakazano":  "🏛",
    "odrzano":   "✅",
    "odlozeno":  "⏳",
    "otkazano":  "❌",
}


def _norm_vreme(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    return v[:5] if len(v) >= 5 else v


def _klasifikuj_dogadjaj(dogadjaj: str) -> str:
    d = dogadjaj.lower()
    if "zastarelost" in d or "zastarelos" in d:
        return "rok_zastarelost"
    return "rok_dokument"


async def _aggr_events(uid: str, od_iso: str, do_iso: str) -> list[dict]:
    """Agregira ročišta i predmet_hronologija u zadatom opsegu datuma."""
    supa = _get_supa()

    rocista_r, hron_r, pred_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("rocista")
            .select("*")
            .eq("user_id", uid)
            .gte("datum", od_iso)
            .lte("datum", do_iso)
            .order("datum")
            .limit(200)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija")
            .select("predmet_id, dogadjaj, datum_iso, vaznost")
            .eq("user_id", uid)
            .gte("datum_iso", od_iso)
            .lte("datum_iso", do_iso)
            .order("datum_iso")
            .limit(200)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id, naziv")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    pred_map: dict[str, str] = {}
    if not isinstance(pred_r, Exception) and pred_r.data:
        pred_map = {p["id"]: p.get("naziv", "") for p in pred_r.data}

    events: list[dict] = []

    if not isinstance(rocista_r, Exception):
        for r in (rocista_r.data or []):
            emoji = _STATUS_EMOJI.get(r.get("status", "zakazano"), "🏛")
            sud = r.get("sud", "")
            pid = r.get("predmet_id", "")
            events.append({
                "tip":           "rociste",
                "datum":         r.get("datum", ""),
                "vreme":         _norm_vreme(r.get("vreme")),
                "naslov":        f"{emoji} Ročište — {pred_map.get(pid, 'Predmet')}",
                "predmet_id":    pid,
                "predmet_naziv": pred_map.get(pid, ""),
                "detalji": {
                    "id":                  r.get("id"),
                    "sud":                 sud,
                    "sudnica":             r.get("sudnica"),
                    "broj_predmeta_suda":  r.get("broj_predmeta_suda"),
                    "status":              r.get("status", "zakazano"),
                    "napomena":            r.get("napomena"),
                },
            })

    if not isinstance(hron_r, Exception):
        for h in (hron_r.data or []):
            pid   = h.get("predmet_id", "")
            tip   = _klasifikuj_dogadjaj(h.get("dogadjaj", ""))
            emoj  = "⚠️" if h.get("vaznost") == "kritičan" else ("📋" if tip == "rok_dokument" else "⏰")
            events.append({
                "tip":           tip,
                "datum":         h.get("datum_iso", ""),
                "vreme":         None,
                "naslov":        f"{emoj} {h.get('dogadjaj', '')}",
                "predmet_id":    pid,
                "predmet_naziv": pred_map.get(pid, ""),
                "detalji": {
                    "vaznost":   h.get("vaznost"),
                    "dogadjaj":  h.get("dogadjaj"),
                },
            })

    events.sort(key=lambda e: (e["datum"], e["vreme"] or ""))
    return events


@router.get("/api/kalendar/pregled")
@limiter.limit("60/minute")
async def kalendar_pregled(
    request: Request,
    od: Optional[str] = None,
    datum_do: Optional[str] = Query(None, alias="do"),
    user: dict = Depends(get_current_user),
):
    """
    Agregira ročišta + predmet_hronologija u zadatom opsegu.
    Podrazumevano: od=danas, do=+30 dana.
    """
    today = date.today()
    try:
        od_date  = date.fromisoformat(od)       if od       else today
        do_date  = date.fromisoformat(datum_do) if datum_do else today + timedelta(days=30)
    except ValueError:
        raise HTTPException(status_code=422, detail="Datumi moraju biti YYYY-MM-DD format")

    if (do_date - od_date).days > 365:
        raise HTTPException(status_code=422, detail="Raspon ne može biti veći od 365 dana")

    events = await _aggr_events(user["user_id"], od_date.isoformat(), do_date.isoformat())
    return {
        "dogadjaji": events,
        "ukupno":    len(events),
        "od":        od_date.isoformat(),
        "do":        do_date.isoformat(),
    }


@router.post("/api/kalendar/ics")
@limiter.limit("20/minute")
async def kalendar_ics_export(
    request: Request,
    od: Optional[str] = None,
    datum_do: Optional[str] = Query(None, alias="do"),
    user: dict = Depends(get_current_user),
):
    """Generišé .ics fajl sa ročištima i rokovima za zadati opseg."""
    from ics_export import generiši_ics_multi

    today = date.today()
    try:
        od_date  = date.fromisoformat(od)       if od       else today
        do_date  = date.fromisoformat(datum_do) if datum_do else today + timedelta(days=90)
    except ValueError:
        raise HTTPException(status_code=422, detail="Datumi moraju biti YYYY-MM-DD format")

    if (do_date - od_date).days > 365:
        raise HTTPException(status_code=422, detail="Raspon ne može biti veći od 365 dana")

    events = await _aggr_events(user["user_id"], od_date.isoformat(), do_date.isoformat())

    ics_eventi = []
    for e in events:
        try:
            d = date.fromisoformat(e["datum"])
        except (ValueError, TypeError):
            continue
        opis_parts = [e.get("predmet_naziv", "")]
        if e["tip"] == "rociste":
            det = e.get("detalji", {})
            if det.get("sud"):
                opis_parts.append(f"Sud: {det['sud']}")
            if det.get("sudnica"):
                opis_parts.append(f"Sudnica: {det['sudnica']}")
            if det.get("status"):
                opis_parts.append(f"Status: {det['status']}")
            if e.get("vreme"):
                opis_parts.append(f"Vreme: {e['vreme']}")
        ics_eventi.append({
            "naslov": e["naslov"],
            "datum":  d,
            "opis":   " | ".join(p for p in opis_parts if p),
        })

    if not ics_eventi:
        raise HTTPException(status_code=404, detail="Nema događaja u zadatom periodu")

    ics_str = generiši_ics_multi(ics_eventi)
    filename = f"vindex-kalendar-{od_date.isoformat()}-{do_date.isoformat()}.ics"
    return Response(
        content=ics_str,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
