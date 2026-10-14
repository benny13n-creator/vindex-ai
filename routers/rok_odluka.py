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
from shared import rokovi as _rokovi_domen
from shared.rok_izvor import izvor_uklonjen_posle_potvrde
from shared.rok_potvrda import (
    STANJE_NEPOTVRDJEN, STANJE_NEPOZNATO, STANJE_POTVRDJEN,
    odbij_rok, odluke, potvrdi_rok, stanje_roka,
)

logger = logging.getLogger("vindex.rok_odluka")
router = APIRouter(tags=["rokovi"])

_MAX_KANDIDATA = 200


class OdlukaReq(BaseModel):
    napomena: Optional[str] = Field(default=None, max_length=500)


async def _rok_u_vlasnistvu(supa, rok_id: str, uid: str, sa_vrstom: bool = False) -> dict:
    """Vraca red ili dize 404. Nikad ne otkriva postojanje tudjeg roka.

    NS2-A2: posle migracije 129 cita se i `vrsta` — potvrda trazi da je red
    IZJAVLJEN kao rok (vidi `potvrdi`). Pre 129 kolona ne postoji i projekcija
    ostaje bajt u bajt ista kao ranije (isti obrazac kao `kandidati`).
    Pozivalac jednom pita semu i istu vrednost koristi i za upit i za kapiju.
    Pad citanja → 503 (ranije neuhvacen 500): stanje reda nije provereno, nista
    se ne upisuje."""
    _kolone = "id, predmet_id, dogadjaj, datum_iso, vaznost, akter"
    if sa_vrstom:
        _kolone += ", vrsta"
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select(_kolone)
                .eq("id", rok_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
    except Exception as exc:
        logger.error("[ROK_ODLUKA] citanje roka palo rok=%s: %s", rok_id, exc)
        raise HTTPException(status_code=503, detail="Stanje roka trenutno nije moguće proveriti. Ništa nije zabeleženo.")
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

    # `vrsta`/`stanje` postoje tek od migracije 129. Projekcija se bira prema
    # STVARNOJ semi: da su kolone bezuslovno u `select`-u, PostgREST bi pre
    # migracije vratio 42703 i ceo endpoint bi pao sa 503. Zateceno ponasanje
    # mora ostati netaknuto dok migracija ne bude pokrenuta.
    _osnovne = ("id, predmet_id, dogadjaj, datum, datum_iso, vaznost, akter, "
                # `izvor` (Z016.1, migracija 127): provenijencija. Bez nje
                # potrosac ne moze da DOKAZE poreklo reda, a pogadjanje po
                # tekstu ili po `akter` je tacno ono sto se ovde ne sme raditi.
                "dokument_naziv, izvor")
    _kolone = (_osnovne + ", vrsta, stanje") if _rokovi_domen._sema_ima_129(supa) else _osnovne

    def _upit():
        q = (supa.table("predmet_hronologija")
             .select(_kolone)
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
    # N03: lanac odluka se cita STROGO. Neprocitan lanac nije "niko nije
    # odlucio" -- inace se odbijen rok vraca u Danas kao nov predlog, a
    # potvrdjen spusta u predlog. Isto pravilo kao za pad hronologije iznad.
    try:
        _odl = await asyncio.to_thread(odluke, [x.get("id") for x in redovi], True)
    except Exception as exc:
        logger.error("[ROK_ODLUKA] citanje odluka palo: %s", exc)
        raise HTTPException(status_code=503, detail="Stanje odluka o rokovima trenutno nije dostupno.")
    # N03-FD6: potvrda se NE ponistava kad se izvor promeni (veza rok -> dokument
    # nije dokaziva), ali advokat dobija upozorenje za pregled. Pad ove provere ne
    # obara pregled rokova — kaze se da provera nije uradjena.
    _potvrdjeni = [x for x in redovi if stanje_roka(x.get("id"), _odl) == STANJE_POTVRDJEN]
    provera_izvora_dostupna = True
    _promenjen: set = set()
    if _potvrdjeni:
        try:
            _promenjen = await asyncio.to_thread(izvor_uklonjen_posle_potvrde, _potvrdjeni)
        except Exception as exc:
            logger.error("[ROK_ODLUKA] provera izmena izvora pala: %s", exc)
            provera_izvora_dostupna = False
    return {
        "rokovi": [
            {**x, "stanje_odluke": stanje_roka(x.get("id"), _odl),
             "izvor_uklonjen_posle_potvrde": str(x.get("id")) in _promenjen}
            for x in redovi
        ],
        "provera_izvora_dostupna": provera_izvora_dostupna,
        "ukupno": len(redovi),
        # Ako je lista puna, poslednji rokovi su odsecani -- to se KAZE, ne cuti.
        "odseceno": len(redovi) >= _MAX_KANDIDATA,
    }


async def _javi_odluku(uid: str, red: dict, rok_id: str, odluka: str) -> None:
    """VCR001 T03 — odluka o roku menja ciljni skup Case Actions (Rule 6). Trajni događaj pokreće usklađivanje akcija
    za TAJ predmet. Odluka je već zabeležena u lancu; pad upisa događaja samo odlaže osvežavanje akcija do sledećeg
    događaja predmeta (zabeleženo u logu), ne gubi odluku."""
    try:
        from services.event_bus import EventType, emit_durable
        await emit_durable(EventType.MANUAL_CORRECTION_APPLIED, uid, red.get("predmet_id"),
                           {"rok_id": str(rok_id), "odluka": odluka, "trigger": "rok_odluka"})
    except Exception as exc:
        logger.warning("[ROK_ODLUKA] događaj posle odluke nije upisan rok=%s: %s", rok_id, exc)


async def _odgovor_posle_odluke(rok_id: str, red: dict) -> dict:
    """N03-FD8: stanje odluke posle upisa se cita STROGO. Ranije je neprocitan
    lanac davao `{}` pa je odgovor glasio UNCONFIRMED odmah posle uspesne
    potvrde — izmisljeno stanje. Odluka JESTE zabelezena (`odluka_zabelezena`),
    ali njeno trenutno stanje se ne zna, i to se kaze: `UNKNOWN`."""
    try:
        _odl = await asyncio.to_thread(odluke, [rok_id], True)
        stanje = stanje_roka(rok_id, _odl)
    except Exception as exc:
        logger.error("[ROK_ODLUKA] stanje posle odluke nije procitano rok=%s: %s", rok_id, exc)
        stanje = STANJE_NEPOZNATO
    return {"ok": True, "rok_id": rok_id, "odluka_zabelezena": True,
            "stanje_odluke": stanje,
            "dogadjaj": red.get("dogadjaj"), "datum_iso": red.get("datum_iso")}


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
    ima_129 = _rokovi_domen._sema_ima_129(supa)
    red = await _rok_u_vlasnistvu(supa, rok_id, uid, sa_vrstom=ima_129)

    # NS2-A2: potvrda daje IZVRSIVOST (podsetnici, .ics, klijent), a izlazni
    # slojevi pitaju samo `sme_pristupiti` — koja ne zna za `vrsta`. Potvrdjen
    # neizjavljen red (npr. „Predmet zatvoren") bio bi izvrsiva obaveza koju
    # V2 Danas/Dosije ne prikazuju (filtriraju po `vrsta`). Zato se potvrda
    # prima SAMO za red izjavljen kao rok. Pre migracije 129 `vrsta` ne postoji
    # ni za jedan red, pa se zateceno ponasanje zadrzava (inace bi jedina
    # ljudska kapija bila ugasena i za stvarne rokove).
    if ima_129 and not _rokovi_domen.je_rok(red):
        raise HTTPException(
            status_code=409,
            detail="Ovaj zapis nije označen kao rok, pa se ne može potvrditi. Ništa nije zabeleženo.")

    if not await potvrdi_rok(rok_id, uid, napomena=body.napomena):
        raise HTTPException(
            status_code=503,
            detail="Odluka nije zabeležena. Pokušajte ponovo — rok ostaje nepotvrđen.")
    await _javi_odluku(uid, red, rok_id, "potvrda")

    return await _odgovor_posle_odluke(rok_id, red)


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

    NS2-A2: za razliku od potvrde, odbijanje NE trazi `vrsta='rok'`. Odbijanje
    samo oduzima izvrsivost (`sme_pristupiti` pusta jedino CONFIRMED), i jedini
    je nacin da se opozove ranija potvrda reda koji nije izjavljen kao rok.
    """
    supa = _get_supa()
    uid = user["user_id"]
    red = await _rok_u_vlasnistvu(supa, rok_id, uid)

    if not await odbij_rok(rok_id, uid, napomena=body.napomena):
        raise HTTPException(
            status_code=503,
            detail="Odluka nije zabeležena. Pokušajte ponovo.")
    await _javi_odluku(uid, red, rok_id, "odbijanje")

    return await _odgovor_posle_odluke(rok_id, red)
