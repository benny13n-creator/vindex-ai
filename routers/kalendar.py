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


# Program Phoenix, Mission 008 (LIVINGSYS-DEBT-053): these are narrative hronologija entries,
# not deadlines -- rendering them tagged identically to a real filing deadline made a lawyer's
# "what's actually due" scan of the Calendar unreliable. Matched by known prefix rather than a
# generic heuristic, so a genuine deadline text never gets misclassified as a note.
_NAPOMENA_PREFIKSI = ("Predmet zatvoren", "Follow-up ročište", "Ugovor o zastupanju zaključen")


def _klasifikuj_dogadjaj(dogadjaj: str) -> str:
    d = dogadjaj.lower()
    if "zastarelost" in d or "zastarelos" in d:
        return "rok_zastarelost"
    if dogadjaj.startswith(_NAPOMENA_PREFIKSI):
        return "napomena"
    return "rok_dokument"


async def _aggr_events(uid: str, od_iso: str, do_iso: str) -> tuple[list[dict], dict]:
    """Agregira ročišta i predmet_hronologija u zadatom opsegu datuma.

    Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-038 remainder): the 200-row cap
    on each source and the return_exceptions=True fallback below used to be
    completely silent -- a lawyer viewing an incomplete Calendar had no way to
    tell "genuinely nothing due" from "a query failed" or "there are more than
    200 hearings this range and some are missing". Now returns a 2nd `meta`
    dict alongside the events, same disclosure pattern already proven for
    Mission 014's CIO `truncated` and Mission 015's Timeline `degraded_sources`.
    """
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
            .select("id, predmet_id, dogadjaj, datum_iso, vaznost")
            .eq("user_id", uid)
            .gte("datum_iso", od_iso)
            .lte("datum_iso", do_iso)
            .order("datum_iso")
            .limit(200)
            .execute()),
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id, naziv, status")
            .eq("user_id", uid)
            .execute()),
        return_exceptions=True,
    )

    degraded_sources: list[str] = []
    if isinstance(rocista_r, Exception):
        degraded_sources.append("rocista")
    if isinstance(hron_r, Exception):
        degraded_sources.append("hronologija")
    if isinstance(pred_r, Exception):
        degraded_sources.append("predmeti")
    truncated = (
        (not isinstance(rocista_r, Exception) and len(rocista_r.data or []) >= 200)
        or (not isinstance(hron_r, Exception) and len(hron_r.data or []) >= 200)
    )
    meta = {"degraded_sources": degraded_sources, "truncated": truncated}

    # Program Phoenix, Mission 001 (LIVINGSYS-DEBT-038): neither event source below was
    # filtered by predmeti.status -- a hearing/deadline belonging to an archived/closed case
    # rendered on the firm-wide deadline Calendar exactly like an active one, the same
    # archived-case-leak bug class Operation Living System already closed for the email cron
    # and Command Center. Calendar's entire job is "don't let a lawyer miss a hearing" --
    # this file was the last major proactive-surface leak of this class.
    pred_map: dict[str, str] = {}
    arhivirani_ids: set[str] = set()
    if not isinstance(pred_r, Exception) and pred_r.data:
        pred_map = {p["id"]: p.get("naziv", "") for p in pred_r.data}
        arhivirani_ids = {p["id"] for p in pred_r.data if p.get("status") in ("zatvoren", "arhiviran", "odbijen")}

    events: list[dict] = []

    if not isinstance(rocista_r, Exception):
        for r in (rocista_r.data or []):
            pid = r.get("predmet_id", "")
            # Only exclude a POSITIVELY-confirmed archived case -- a predmet_id absent from
            # pred_map (lookup failure, cross-user edge case, etc.) fails OPEN and still
            # renders (with its existing name-fallback behavior), consistent with this
            # endpoint's "don't miss a hearing" purpose.
            if pid in arhivirani_ids:
                continue
            emoji = _STATUS_EMOJI.get(r.get("status", "zakazano"), "🏛")
            sud = r.get("sud", "")
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
            if pid in arhivirani_ids:
                continue
            tip   = _klasifikuj_dogadjaj(h.get("dogadjaj", ""))
            if tip == "napomena":
                emoj = "🗒"
            elif h.get("vaznost") == "kritičan":
                emoj = "⚠️"
            else:
                emoj = "📋" if tip == "rok_dokument" else "⏰"
            events.append({
                "tip":           tip,
                "datum":         h.get("datum_iso", ""),
                "vreme":         None,
                "naslov":        f"{emoj} {h.get('dogadjaj', '')}",
                "predmet_id":    pid,
                "predmet_naziv": pred_map.get(pid, ""),
                "detalji": {
                    # N03: identitet reda -- bez njega se izvoz ne moze vezati za odluku o roku.
                    "id":        h.get("id"),
                    "vaznost":   h.get("vaznost"),
                    "dogadjaj":  h.get("dogadjaj"),
                },
            })

    events.sort(key=lambda e: (e["datum"], e["vreme"] or ""))
    return events, meta


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

    events, meta = await _aggr_events(user["user_id"], od_date.isoformat(), do_date.isoformat())

    # N03-FD5/FD8: ovo je INTERNI pogled — advokat vidi svaki svoj rok, i
    # nepotvrdjen i odbijen (odbijen nije obrisan). Ali svaki rok nosi stanje
    # odluke, da nijedan potrosac ovog odgovora (legacy „Google/Outlook" precica)
    # ne bi nepotvrdjen rok izneo napolje kao obavezu. Neprocitan lanac odluka ne
    # gasi kalendar (rocista i rokovi ostaju vidljivi), ali stanje je UNKNOWN —
    # nikad izmisljeno UNCONFIRMED — i to se kaze u `odluke_dostupne`.
    odluke_dostupne = True
    _rok_ids = _ids_rokova(events)
    if _rok_ids:
        from shared.rok_potvrda import STANJE_NEPOZNATO, odluke, stanje_roka
        try:
            _odl = await asyncio.to_thread(odluke, _rok_ids, True)
        except Exception as exc:
            logger.error("[KALENDAR] pregled: citanje odluka o rokovima palo: %s", exc)
            _odl, odluke_dostupne = None, False
        for e in events:
            rid = (e.get("detalji") or {}).get("id") if e["tip"] != "rociste" else None
            if rid:
                e["detalji"]["stanje_odluke"] = (stanje_roka(str(rid), _odl) if odluke_dostupne
                                                 else STANJE_NEPOZNATO)
    return {
        "dogadjaji": events,
        "ukupno":    len(events),
        "od":        od_date.isoformat(),
        "do":        do_date.isoformat(),
        # Phoenix Closure (LIVINGSYS-DEBT-038 remainder): empty list / False on full success.
        "degraded_sources": meta["degraded_sources"],
        "truncated":        meta["truncated"],
        "odluke_dostupne":  odluke_dostupne,
    }


def _ids_rokova(events: list) -> list:
    """`predmet_hronologija.id` svakog dogadjaja koji NIJE rociste."""
    return [str(e["detalji"]["id"]) for e in events
            if e["tip"] != "rociste" and (e.get("detalji") or {}).get("id")]


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

    events, _meta = await _aggr_events(user["user_id"], od_date.isoformat(), do_date.isoformat())

    # N03-FD5: `.ics` je upis u advokatov SPOLJNI kalendar (isti efekat kao
    # Google sinhronizacija). O tome odlucuje JEDINO kanonska politika
    # `sme_pristupiti(..., EXPORT_EXTERNAL)`: prolazi samo rok koji je covek
    # POTVRDIO. Nepotvrdjen i odbijen ne prolaze — bez izuzetka za izvor
    # (AI, rucni unos, ZPP lanac), vaznost ili pouzdanost. Rociste je zaseban
    # domenski objekat (tabela `rocista`) i zadrzava svoje ponasanje. Lanac
    # odluka se cita strogo: neprocitan lanac nije „nista nije odbijeno" niti
    # „sve je potvrdjeno" -> 503, nista se ne izvozi.
    _rok_ids = _ids_rokova(events)
    _odl: dict = {}
    if _rok_ids:
        from shared.rok_potvrda import odluke
        try:
            _odl = await asyncio.to_thread(odluke, _rok_ids, True)
        except Exception as exc:
            logger.error("[KALENDAR] ics: citanje odluka o rokovima palo: %s", exc)
            raise HTTPException(status_code=503, detail="Stanje odluka o rokovima trenutno nije dostupno.")
    from shared import rokovi as _rokovi_domen
    events = [e for e in events
              if e["tip"] == "rociste"
              or _rokovi_domen.sme_pristupiti({"id": (e.get("detalji") or {}).get("id")}, _odl,
                                              potrosac=_rokovi_domen.POTROSAC_IZVOZ_SPOLJA)]

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
        raise HTTPException(status_code=404, detail="Nema ročišta ni potvrđenih rokova u zadatom periodu. "
                                                    "Nepotvrđeni rokovi se ne izvoze u spoljni kalendar.")

    ics_str = generiši_ics_multi(ics_eventi)
    filename = f"vindex-kalendar-{od_date.isoformat()}-{do_date.isoformat()}.ics"
    return Response(
        content=ics_str,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
