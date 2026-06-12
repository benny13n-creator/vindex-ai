# -*- coding: utf-8 -*-
"""
Vindex AI — routers/zastarelost.py

Phase 3.6: Kalkulacija zastarelosti + ICS export rokova.
Nema autentifikacije — javno dostupni endpointi.
"""
import asyncio
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response as _Resp
from pydantic import BaseModel

router = APIRouter()


class ZastarelostRequest(BaseModel):
    tip:           str
    datum_pocetka: str


class IcsExportRequest(BaseModel):
    rokovi: List[dict]  # [{"naslov": str, "datum_iso": str, "opis": str}]


@router.get("/zastarelost/tipovi")
async def get_tipovi_zastarelosti():
    """Phase 3.6 — Lista svih tipova zastarelosti za frontend dropdown."""
    from zastarelost import lista_tipova_zastarelosti
    return {"tipovi": lista_tipova_zastarelosti()}


@router.post("/zastarelost/kalkulisi")
async def post_kalkulisi_zastarelost(req: ZastarelostRequest):
    """Phase 3.6 — Kalkulacija datuma zastarelosti po srpskom pravu."""
    import re as _re
    from datetime import date as _date
    from zastarelost import kalkulisi_zastarelost

    raw = req.datum_pocetka.strip()
    try:
        if _re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", raw):
            d, m, y = raw.split(".")
            datum = _date(int(y), int(m), int(d))
        else:
            datum = _date.fromisoformat(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Neispravan format datuma — koristite DD.MM.YYYY ili YYYY-MM-DD")

    try:
        rez = await asyncio.to_thread(kalkulisi_zastarelost, req.tip, datum)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "tip_potrazivanja":       rez.tip_potrazivanja,
        "zakonski_osnov":         rez.zakonski_osnov,
        "rok_opis":               rez.rok_opis,
        "datum_pocetka":          rez.datum_pocetka.strftime("%d.%m.%Y"),
        "datum_zastarelosti":     rez.datum_zastarelosti.strftime("%d.%m.%Y"),
        "datum_zastarelosti_iso": rez.datum_zastarelosti.isoformat(),
        "dana_preostalo":         rez.dana_preostalo,
        "isteklo":                rez.isteklo,
        "napomena":               rez.napomena,
    }


@router.post("/rokovi/ics-export")
async def post_ics_export(req: IcsExportRequest):
    """Phase 3.6 — Generisanje .ics kalendar fajla za jedan ili više rokova."""
    from datetime import date as _date
    from ics_export import generiši_ics_event, generiši_ics_multi

    if not req.rokovi:
        raise HTTPException(status_code=422, detail="Lista rokova je prazna")

    eventi = []
    for r in req.rokovi:
        if not r.get("datum_iso") or not r.get("naslov"):
            raise HTTPException(status_code=422, detail="Svaki rok mora imati 'naslov' i 'datum_iso'")
        try:
            d = _date.fromisoformat(r["datum_iso"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Neispravan datum_iso: {r['datum_iso']!r}")
        eventi.append({"naslov": r["naslov"], "datum": d, "opis": r.get("opis", "")})

    if len(eventi) == 1:
        ics_str  = generiši_ics_event(eventi[0]["naslov"], eventi[0]["datum"], eventi[0]["opis"])
        filename = "rok_vindex.ics"
    else:
        ics_str  = generiši_ics_multi(eventi)
        filename = f"rokovi_vindex_{len(eventi)}.ics"

    return _Resp(
        content=ics_str.encode("utf-8"),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
