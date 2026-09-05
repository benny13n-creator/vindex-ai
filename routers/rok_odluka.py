# -*- coding: utf-8 -*-
"""
Vindex AI — routers/rok_odluka.py

FAZA 6.5 — POVRSINA ZA LJUDSKU ODLUKU O ROKU.

  GET  /api/rokovi/kandidati              — advokat vidi rokove i njihovo stanje
  POST /api/rokovi/{rok_id}/potvrdi       — potvrda TACNO tog roka
  POST /api/rokovi/{rok_id}/odbij         — odbijanje TACNO tog roka

## Zasto ovaj fajl postoji

FAZA 6.4.2 je zatvorila izlaznu granicu: nijedan rok ne moze pokrenuti email,
SMS, Viber, WhatsApp ni kalendar bez ljudske potvrde. FAZA 6.4.3 je izmerila da
`potvrdi_rok`/`odbij_rok` **nemaju nijednog pozivaoca** — dakle advokat nije imao
nacina da potvrdi bilo sta, pa je ceo izlazni sloj bio mrtav.

Ovo je ta povrsina, i nista vise od nje.

## Sta ovaj modul NIKAD ne radi

  * ne menja `predmet_hronologija` — ni `izvor`, ni `akter`, ni `vaznost`, ni
    datum, ni naziv. Odluka je zapis O roku, ne prepravka roka;
  * ne potvrdjuje grupno — nema "potvrdi sve", jer potvrda mora biti odluka o
    konkretnoj cinjenici, a ne o listi;
  * ne izvodi identitet ni iz cega osim iz `predmet_hronologija.id`;
  * ne tumaci `izvor` — AI i ljudski rok prolaze isti put.

## Vlasnistvo

Backend radi sa `service_role` kljucem, pa je RLS zaobidjen. Zato je
`.eq("user_id", uid)` u svakom upitu **jedina** brana izmedju kancelarija —
isti razlog i isti obrazac kao u `shared/rokovi.py` i `shared/ownership.py`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
from shared.rok_potvrda import (
    STANJE_NEPOTVRDJEN, odbij_rok, odluke, potvrdi_rok, stanje_roka,
)

logger = logging.getLogger("vindex.rok_odluka")
router = APIRouter(tags=["rokovi"])

_MAX_KANDIDATA = 200


class OdlukaReq(BaseModel):
    napomena: Optional[str] = Field(default=None, max_length=500)


async def _rok_u_vlasnistvu(supa, rok_id: str, uid: str) -> dict:
    """Vraca red ili dize 404. Nikad ne otkriva postojanje tudjeg roka."""
    r = await asyncio.to_thread(
        lambda: supa.table("predmet_hronologija")
            .select("id, predmet_id, dogadjaj, datum_iso, vaznost, akter")
            .eq("id", rok_id)
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    if not r or not r.data:
        raise HTTPException(status_code=404, detail="Rok nije pronađen.")
    return r.data


@router.get("/api/rokovi/kandidati")
@limiter.limit("60/minute")
async def kandidati(
    request: Request,
    predmet_id: Optional[str] = None,
    dana: int = 30,
    od: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """INTERNAL pogled: advokat vidi SVE svoje rokove sa stanjem odluke.

    Namerno se ne filtrira po stanju — advokat mora videti kandidata da bi ga
    uopste mogao potvrditi, a odbijen rok mora ostati vidljiv u istoriji.
    ODBIJEN NIJE OBRISAN.

    Sam pregled NE menja nista: nema upisa, nema potvrde, nema promene stanja.

    `od` (Z016 / Gate A): pocetak opsega, podrazumevano DANAS — bez njega
    ponasanje je bajt u bajt isto kao pre. Postoji zato sto je istekao rok
    najvaznija stavka na ekranu Danas, a jedini drugi izvor datiranih obaveza
    (`/api/kalendar/pregled`) ne vraca `id` reda ni `stanje_odluke`. Bez ovog
    parametra istekao rok bi se mogao prikazati samo kao gola tvrdnja, bez
    podatka da li ga je covek ikad potvrdio ili ga je predlozio AI.
    """
    supa = _get_supa()
    uid = user["user_id"]
    _dana = max(1, min(int(dana or 30), 365))
    danas = date.today()
    try:
        od_date = date.fromisoformat(od) if od else danas
    except ValueError:
        raise HTTPException(status_code=422, detail="Datum mora biti u obliku YYYY-MM-DD.")
    # Gornja granica se racuna od DANAS, ne od `od` — `dana` znaci „koliko
    # unapred gledam", a ne „koliko dana ukupno". Pomeranje pocetka unazad ne
    # sme tiho da produzi pogled u buducnost.
    do_date = danas + timedelta(days=_dana)
    if od_date > do_date:
        od_date = do_date
    if (do_date - od_date).days > 365:
        raise HTTPException(status_code=422, detail="Raspon ne može biti veći od 365 dana.")

    def _upit():
        q = (supa.table("predmet_hronologija")
             # `izvor` (Z016.1): kolona provenijencije. Bez nje potrosac ne moze
             # da DOKAZE da je red predlog roka, a ne istorijska cinjenica
             # predmeta -- a pogadjanje po tekstu ili po `akter` je tacno ono
             # sto na ovom podatku ne sme da se radi.
             .select("id, predmet_id, dogadjaj, datum, datum_iso, vaznost, akter, dokument_naziv, izvor")
             .eq("user_id", uid)
             .gte("datum_iso", od_date.isoformat())
             .lte("datum_iso", do_date.isoformat())
             .order("datum_iso")
             .limit(_MAX_KANDIDATA))
        if predmet_id:
            q = q.eq("predmet_id", predmet_id)
        return q.execute()

    try:
        r = await asyncio.to_thread(_upit)
    except Exception as exc:
        logger.error("[ROK_ODLUKA] citanje kandidata palo: %s", exc)
        raise HTTPException(status_code=503, detail="Rokovi trenutno nisu dostupni.")

    redovi = r.data or []
    _odl = await asyncio.to_thread(odluke, [x.get("id") for x in redovi])
    return {
        "rokovi": [
            {**x, "stanje_odluke": stanje_roka(x.get("id"), _odl)}
            for x in redovi
        ],
        "ukupno": len(redovi),
        # Ako je lista puna, poslednji rokovi su odsecani -- to se KAZE, ne cuti.
        "odseceno": len(redovi) >= _MAX_KANDIDATA,
    }


@router.post("/api/rokovi/{rok_id}/potvrdi")
@limiter.limit("60/minute")
async def potvrdi(
    rok_id: str,
    request: Request,
    body: OdlukaReq = OdlukaReq(),
    user: dict = Depends(get_current_user),
):
    """Advokat preuzima odgovornost za TACNO ovaj rok.

    Tek posle ovoga rok sme da pokrene podsetnik, SMS, Viber, WhatsApp ili upis
    u kalendar, i tek tada sme da bude prikazan klijentu.

    Ne tvrdi se da je rok cinjenicno tacan — tvrdi se da ga je covek video i
    prihvatio za upotrebu.
    """
    supa = _get_supa()
    uid = user["user_id"]
    red = await _rok_u_vlasnistvu(supa, rok_id, uid)

    if not await potvrdi_rok(rok_id, uid, napomena=body.napomena):
        raise HTTPException(
            status_code=503,
            detail="Odluka nije zabeležena. Pokušajte ponovo — rok ostaje nepotvrđen.")

    _odl = await asyncio.to_thread(odluke, [rok_id])
    return {"ok": True, "rok_id": rok_id,
            "stanje_odluke": stanje_roka(rok_id, _odl),
            "dogadjaj": red.get("dogadjaj"), "datum_iso": red.get("datum_iso")}


@router.post("/api/rokovi/{rok_id}/odbij")
@limiter.limit("60/minute")
async def odbij(
    rok_id: str,
    request: Request,
    body: OdlukaReq = OdlukaReq(),
    user: dict = Depends(get_current_user),
):
    """Advokat odbacuje TACNO ovaj rok.

    Odbijen rok se NE BRISE: ostaje u hronologiji i u internom pregledu, sa
    stanjem `REJECTED`. Ne moze pokrenuti akciju i ne prikazuje se klijentu.

    GRANICA: odbijanje vazi za OVAJ `predmet_hronologija.id`. Ako sledeca AI
    ekstrakcija napravi NOV red (a hronologija je insert-only, pa hoce), taj red
    je nov kandidat i trazi novu odluku. To je poznata praznina zivotnog ciklusa,
    dokumentovana u FAZI 6.5 — a ne tiho nasledjivanje odluke.
    """
    supa = _get_supa()
    uid = user["user_id"]
    red = await _rok_u_vlasnistvu(supa, rok_id, uid)

    if not await odbij_rok(rok_id, uid, napomena=body.napomena):
        raise HTTPException(
            status_code=503,
            detail="Odluka nije zabeležena. Pokušajte ponovo.")

    _odl = await asyncio.to_thread(odluke, [rok_id])
    return {"ok": True, "rok_id": rok_id,
            "stanje_odluke": stanje_roka(rok_id, _odl),
            "dogadjaj": red.get("dogadjaj"), "datum_iso": red.get("datum_iso")}
