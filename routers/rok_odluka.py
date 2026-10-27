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
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
from shared import rokovi as _rokovi_domen
from shared.rok_ispravka import napomena_ispravke, postojeca_ispravka, upisi_ispravljen_rok
from shared.rok_izvor import izvor_uklonjen_posle_potvrde
from shared.rok_potvrda import (
    STANJE_NEPOTVRDJEN, STANJE_NEPOZNATO, STANJE_ODBIJEN, STANJE_POTVRDJEN,
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
    _kolone = (_osnovne + ", vrsta, stanje, dokument_id") if _rokovi_domen._sema_ima_129(supa) else _osnovne

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
    # MIR001 TASK-07: predlog roka čiji je izvorni dokument obrisan označava se ISTIM pravilom kao Case Actions Rule 6
    # (`izvor_povucen`) — Danas ga ne nudi na potvrdu kao da izvor postoji. Pad čitanja dokumenata = provera nije urađena.
    _povucen: set = set()
    _sumnjivi = [x for x in redovi if x.get("akter") == _rokovi_domen.AKTER_GENOME and x.get("dokument_naziv")
                 and "dokument_id" in x and not x.get("dokument_id")]
    if _sumnjivi:
        try:
            _pids = sorted({x["predmet_id"] for x in _sumnjivi if x.get("predmet_id")})
            _dr = await asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("predmet_id,naziv_fajla")
                                          .eq("user_id", uid).in_("predmet_id", _pids).execute())
            _nazivi: dict = {}
            for d in (_dr.data or []):
                _nazivi.setdefault(d.get("predmet_id"), set()).add(d.get("naziv_fajla"))
            _povucen = {str(x["id"]) for x in _sumnjivi if _rokovi_domen.izvor_povucen(x, _nazivi.get(x.get("predmet_id"), set()))}
        except Exception as exc:
            logger.error("[ROK_ODLUKA] provera povučenog izvora pala: %s", exc)
            provera_izvora_dostupna = False
    return {
        "rokovi": [
            {**x, "stanje_odluke": stanje_roka(x.get("id"), _odl),
             "izvor_uklonjen_posle_potvrde": str(x.get("id")) in _promenjen,
             "izvor_povucen": str(x.get("id")) in _povucen}
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


def _bez_upisa(rok_id: str, red: dict, stanje: str) -> dict:
    """NS2B-C F1: ista odluka je VEC u lancu (stanje upravo procitano strogo). Nista se ne
    upisuje i ne tvrdi se nov upis (`odluka_zabelezena: False`); stanje je ono koje lanac kaze."""
    return {"ok": True, "rok_id": rok_id, "odluka_zabelezena": False, "vec_odluceno": True,
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

    # NS2B-C: odbijen rok se ne potvrdjuje obicnom odlukom (zastareo prozor, ponovljen
    # zahtev). Ova provera je SAMO za jasan odgovor i da se ne upise suvisan zapis — NIJE
    # zastita od trke: upis nije uslovan. Zastitu daje `odluke()`, koja odbijanje cini
    # zavrsnim bez obzira na redosled upisa. Neprocitan lanac → 503, nista se ne upisuje.
    try:
        _pre = await asyncio.to_thread(odluke, [rok_id], True)
    except Exception as exc:
        logger.error("[ROK_ODLUKA] stanje pre potvrde nije procitano rok=%s: %s", rok_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Stanje roka trenutno nije moguće proveriti. Ništa nije zabeleženo.")
    if stanje_roka(rok_id, _pre) == STANJE_ODBIJEN:
        raise HTTPException(
            status_code=409,
            detail="Rok je već odbijen. Potvrda posle odbijanja nije moguća iz ovog prozora — osvežite stranicu.")
    # G3: predlog koji je advokat već ispravio (a odbijanje predloga nije uspelo) ne sme da postane DRUGA obaveza.
    try:
        _ispravka = await asyncio.to_thread(postojeca_ispravka, supa, uid=uid, predlog=red, rok_id=rok_id)
    except Exception as exc:
        logger.error("[ROK_ODLUKA] provera ispravke pre potvrde nije uspela rok=%s: %s", rok_id, exc)
        raise HTTPException(status_code=503, detail="Stanje roka trenutno nije moguće proveriti. Ništa nije zabeleženo.")
    if _ispravka:
        raise HTTPException(
            status_code=409,
            detail=f"Ovaj predlog je već ispravljen — važi ispravljen rok {_ispravka}. Potvrda predloga bi napravila "
                   "drugu obavezu; odbijte predlog. Ništa nije zabeleženo.")
    # NS2B-C F1: ponovljena potvrda VEC potvrdjenog roka ne upisuje nov red (lanac ne raste
    # bez promene stanja). Jedini izuzetak je N03-FD6: posle uklanjanja dokumenta iz predmeta
    # nova potvrda JESTE nova cinjenica (advokat je ponovo pregledao) i gasi upozorenje — tada
    # se upisuje. Ako to ne moze da se proveri → 503, nista se ne upisuje.
    if stanje_roka(rok_id, _pre) == STANJE_POTVRDJEN:
        try:
            _ponovni_pregled = str(rok_id) in await asyncio.to_thread(izvor_uklonjen_posle_potvrde, [red])
        except Exception as exc:
            logger.error("[ROK_ODLUKA] provera izvora pre ponovne potvrde pala rok=%s: %s", rok_id, exc)
            raise HTTPException(
                status_code=503,
                detail="Stanje roka trenutno nije moguće proveriti. Ništa nije zabeleženo.")
        if not _ponovni_pregled:
            return _bez_upisa(rok_id, red, STANJE_POTVRDJEN)

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

    # NS2B-C F1: odbijanje VEC odbijenog roka ne upisuje nov red — REJECTED je apsorbujuce,
    # pa drugi zapis ne menja nista. Potvrdjen ili nepotvrdjen rok se i dalje odbija (upis).
    # Pad citanja NE blokira odbijanje: oduzimanje izvrsivosti je bezbedan smer, pa se tada
    # upisuje kao i ranije (najvise jedan suvisan red).
    try:
        _pre = await asyncio.to_thread(odluke, [rok_id], True)
    except Exception as exc:
        logger.warning("[ROK_ODLUKA] stanje pre odbijanja nije procitano rok=%s, odbijanje se upisuje: %s", rok_id, exc)
        _pre = {}
    if stanje_roka(rok_id, _pre) == STANJE_ODBIJEN:
        return _bez_upisa(rok_id, red, STANJE_ODBIJEN)

    if not await odbij_rok(rok_id, uid, napomena=body.napomena):
        raise HTTPException(
            status_code=503,
            detail="Odluka nije zabeležena. Pokušajte ponovo.")
    await _javi_odluku(uid, red, rok_id, "odbijanje")

    return await _odgovor_posle_odluke(rok_id, red)


# ── N4: ispravka PREDLOGA roka (pogrešno pročitan datum) ─────────────────────
#
# Potvrda prihvata TAČNO taj red, a red se ne menja (nema puta izmene hronologije). Kad je OCR/model pročitao
# pogrešan datum, advokat je mogao samo da odbije i — u V2 — nije imao gde da upiše tačan. Ispravka zato:
#   1) upisuje NOV red `vrsta='rok'`, `izvor=HUMAN_DIRECT` (advokat je uneo datum), uz isti predmet, dokument
#      i opis kao predlog;
#   2) potvrđuje NOV red (advokat je izričito dao vrednost — to je njegova odluka, ne AI predlog);
#   3) odbija STARI predlog (napomena pokazuje na nov red).
# Redosled je izabran tako da delimičan neuspeh nikad ne izgubi rok: pad posle (1) ostavlja nov red kao predlog
# uz stari; pad posle (2) ostavlja stari predlog vidljiv uz potvrđen nov — oba stanja se kažu u odgovoru.
# Samo NEPOTVRĐEN predlog se ispravlja ovde; dva istovremena zahteva za isti rok → drugi dobija 409.

_ISPRAVKA_U_TOKU: set = set()


class IspravkaReq(BaseModel):
    datum_iso: str = Field(..., min_length=10, max_length=10)
    dogadjaj:  Optional[str] = Field(default=None, max_length=500)


@router.post("/api/rokovi/{rok_id}/ispravi")
@limiter.limit("30/minute")
async def ispravi(
    rok_id: str,
    body: IspravkaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.datum_iso):
            raise ValueError
        novi_datum = date.fromisoformat(body.datum_iso)
    except ValueError:
        raise HTTPException(status_code=422, detail="Datum mora biti GGGG-MM-DD. Ništa nije zabeleženo.")
    supa = _get_supa()
    uid = user["user_id"]
    ima_129 = _rokovi_domen._sema_ima_129(supa)
    red = await _rok_u_vlasnistvu(supa, rok_id, uid, sa_vrstom=ima_129)
    if ima_129 and not _rokovi_domen.je_rok(red):
        raise HTTPException(status_code=409, detail="Ovaj zapis nije označen kao rok. Ništa nije zabeleženo.")
    # Nalaz pregleda N4: isti datum nije ispravka — to je potvrda AI datuma i ide kroz „Potvrdi“ (poreklo ostaje AI).
    if str(red.get("datum_iso") or "")[:10] == novi_datum.isoformat():
        raise HTTPException(status_code=409, detail="Datum je isti kao u predlogu — to nije ispravka. Ako je predlog tačan, koristite „Potvrdi“. Ništa nije zabeleženo.")
    kljuc = (uid, str(rok_id))
    if kljuc in _ISPRAVKA_U_TOKU:
        raise HTTPException(status_code=409, detail="Ispravka ovog roka je već u toku. Osvežite spisak.")
    _ISPRAVKA_U_TOKU.add(kljuc)
    try:
        try:
            _pre = await asyncio.to_thread(odluke, [rok_id], True)
        except Exception as exc:
            logger.error("[ROK_ODLUKA] stanje pre ispravke nije procitano rok=%s: %s", rok_id, exc)
            raise HTTPException(status_code=503, detail="Stanje roka trenutno nije moguće proveriti. Ništa nije zabeleženo.")
        if stanje_roka(rok_id, _pre) != STANJE_NEPOTVRDJEN:
            raise HTTPException(status_code=409, detail="Ispravlja se samo nepotvrđen predlog; ovaj rok je već potvrđen ili odbijen. Ništa nije zabeleženo.")
        # G3: već postoji potvrđena ispravka ovog predloga (odbijanje predloga ranije nije uspelo) — nov rok se ne
        # pravi; dovršava se odbijanje predloga.
        try:
            _ispravka = await asyncio.to_thread(postojeca_ispravka, supa, uid=uid, predlog=red, rok_id=rok_id)
        except Exception as exc:
            logger.error("[ROK_ODLUKA] provera ranije ispravke nije uspela rok=%s: %s", rok_id, exc)
            raise HTTPException(status_code=503, detail="Stanje roka trenutno nije moguće proveriti. Ništa nije zabeleženo.")
        if _ispravka:
            odbijen = await odbij_rok(rok_id, uid, napomena=f"Ispravljen — tačan rok je {_ispravka}")
            raise HTTPException(
                status_code=409,
                detail=f"Ovaj predlog je već ispravljen — važi ispravljen rok {_ispravka}; nov rok nije napravljen. "
                       + ("Predlog je sada odbijen." if odbijen else "Predlog i dalje NIJE odbijen — odbijte ga."))
        try:
            izvor_r = await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").select("dokument_id, dokument_naziv")
                    .eq("id", rok_id).eq("user_id", uid).maybe_single().execute())
            izvor = (izvor_r.data if izvor_r else None) or {}
        except Exception:
            izvor = {}
        opis = (body.dogadjaj or "").strip() or red.get("dogadjaj") or "Rok"
        # Upis je u shared/rok_ispravka.py (ova ruta samo čita hronologiju — FAZA 6.5); ponovni pokušaj posle
        # delimičnog neuspeha koristi postojeću ispravku umesto da napravi drugi nov rok.
        try:
            nov_id = await asyncio.to_thread(upisi_ispravljen_rok, supa, uid=uid, predlog=red, izvor=izvor,
                                             opis=opis, datum=novi_datum)
        except Exception as exc:
            logger.error("[ROK_ODLUKA] ispravka: nov rok nije upisan rok=%s: %s", rok_id, exc)
            nov_id = None
        if not nov_id:
            raise HTTPException(status_code=503, detail="Ispravljen rok nije upisan. Predlog je ostao nepromenjen.")
        if not await potvrdi_rok(nov_id, uid, napomena=napomena_ispravke(rok_id)):
            raise HTTPException(status_code=503, detail="Ispravljen rok je upisan, ali NIJE potvrđen — vidi se kao nov predlog uz stari. Potvrdite ga ručno.")
        odbijen = await odbij_rok(rok_id, uid, napomena=f"Ispravljen — tačan rok je {nov_id}")
        await _javi_odluku(uid, red, nov_id, "potvrda")
    finally:
        _ISPRAVKA_U_TOKU.discard(kljuc)
    return {"ok": True, "rok_id": nov_id, "ispravljen_rok_id": rok_id, "datum_iso": novi_datum.isoformat(),
            "stanje_odluke": STANJE_POTVRDJEN, "stari_odbijen": bool(odbijen)}
