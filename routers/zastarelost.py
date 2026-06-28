# -*- coding: utf-8 -*-
"""
Vindex AI — routers/zastarelost.py

Phase 3.6: Kalkulacija zastarelosti + ICS export rokova.
Phase 5+: Procesni rokovi (ZPP/ZKP/ZR/ZIO/ZUP) sa srpskim praznicima i radnim danima.
Nema autentifikacije za zastarelost — javno dostupni endpointi.
"""
import asyncio
from datetime import date as _date, timedelta as _td
from typing import List, Optional

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response as _Resp
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

router = APIRouter()

# ── Srpski praznici i sudski neradni dani ─────────────────────────────────────

def _srpski_praznici(godina: int) -> set:
    """Vraća set datuma državnih praznika za datu godinu."""
    praznici = {
        _date(godina, 1, 1),
        _date(godina, 1, 2),
        _date(godina, 1, 7),
        _date(godina, 2, 15),
        _date(godina, 2, 16),
        _date(godina, 5, 1),
        _date(godina, 5, 2),
        _date(godina, 11, 11),
    }
    # Pravoslavni Uskrs (statički za 2025-2027)
    uskrs = {
        _date(2025, 4, 20), _date(2025, 4, 21),
        _date(2026, 4, 12), _date(2026, 4, 13),
        _date(2027, 5, 2),  _date(2027, 5, 3),
    }
    praznici.update(uskrs)
    return praznici


def _sudski_neradni_dani(godina: int) -> set:
    """Sudski odmori (jul/avg/dec-jan) + praznici."""
    neradni = _srpski_praznici(godina)
    for dan in range(1, 32):
        try:
            neradni.add(_date(godina, 7, dan))
        except ValueError:
            pass
    for dan in range(1, 16):
        neradni.add(_date(godina, 8, dan))
    for dan in range(27, 32):
        try:
            neradni.add(_date(godina, 12, dan))
        except ValueError:
            pass
    neradni.add(_date(godina, 12, 31))
    return neradni


def _radni_dani_add(start: _date, n: int, sudski: bool = False) -> _date:
    """Dodaj N radnih dana na startni datum (preskačući vikende i praznike)."""
    neradni: set = set()
    for g in [start.year, start.year + 1]:
        neradni.update(_sudski_neradni_dani(g) if sudski else _srpski_praznici(g))
    tekuci = start
    preostalo = n
    while preostalo > 0:
        tekuci += _td(days=1)
        if tekuci.weekday() < 5 and tekuci not in neradni:
            preostalo -= 1
    return tekuci


# ── Procesni rokovi katalog ───────────────────────────────────────────────────

PROCESNI_ROKOVI = {
    "zalba_zpp": {
        "naziv": "Žalba na prvostepenu presudu (ZPP čl. 368)",
        "dani": 15, "tip": "radni",
        "napomena": "15 radnih dana od dostavljanja presude",
    },
    "prigovor_zpp": {
        "naziv": "Prigovor na platni nalog (ZPP čl. 460)",
        "dani": 8, "tip": "radni",
        "napomena": "8 radnih dana od dostavljanja platnog naloga",
    },
    "revizija_zpp": {
        "naziv": "Revizija (ZPP čl. 407)",
        "dani": 30, "tip": "kalendarski",
        "napomena": "30 dana od dostavljanja drugostepene presude",
    },
    "odgovor_na_tuzbu_zpp": {
        "naziv": "Odgovor na tužbu (ZPP čl. 295)",
        "dani": 30, "tip": "radni",
        "napomena": "30 dana od dostavljanja tužbe",
    },
    "predlog_ponavljanja_zpp": {
        "naziv": "Predlog za ponavljanje postupka (ZPP čl. 430)",
        "dani": 30, "tip": "radni",
        "napomena": "30 dana od saznanja za razlog ponavljanja",
    },
    "zalba_kz": {
        "naziv": "Žalba na krivičnu presudu (ZKP čl. 443)",
        "dani": 15, "tip": "radni",
        "napomena": "15 dana od dostavljanja presude",
    },
    "zahtev_zasticeni_svedok": {
        "naziv": "Zahtev za zaštićenog svedoka (ZKP)",
        "dani": 30, "tip": "kalendarski",
        "napomena": "Najkasnije 30 dana pre glavnog pretresa",
    },
    "otkaz_zr_otkazni_rok": {
        "naziv": "Otkazni rok (ZR čl. 189)",
        "dani": 30, "tip": "radni",
        "napomena": "30 dana (može biti i 8 ili 15 dana zavisno od razloga)",
    },
    "tuzba_radni_spor": {
        "naziv": "Tužba u radnom sporu (ZR čl. 195)",
        "dani": 90, "tip": "radni",
        "napomena": "90 dana od saznanja za povredu prava",
    },
    "prigovor_na_resenje_izvrsenje": {
        "naziv": "Prigovor na rešenje o izvršenju (ZIO čl. 74)",
        "dani": 8, "tip": "radni",
        "napomena": "8 radnih dana od dostavljanja rešenja",
    },
    "zalba_izvrsenje": {
        "naziv": "Žalba u izvršnom postupku (ZIO čl. 25)",
        "dani": 8, "tip": "radni",
        "napomena": "8 radnih dana",
    },
    "zalba_upravni": {
        "naziv": "Žalba u upravnom postupku (ZUP čl. 228)",
        "dani": 15, "tip": "radni",
        "napomena": "15 dana od dostavljanja rešenja",
    },
    "tuzba_upravni_spor": {
        "naziv": "Tužba u upravnom sporu (ZUS čl. 18)",
        "dani": 30, "tip": "radni",
        "napomena": "30 dana od dostavljanja konačnog akta",
    },
    "zalba_prekrsaj": {
        "naziv": "Žalba na prekršajnu odluku (ZPP prekršaj)",
        "dani": 8, "tip": "radni",
        "napomena": "8 dana od dostavljanja odluke",
    },
    "ustavna_zalba": {
        "naziv": "Ustavna žalba (Zakon o US čl. 82)",
        "dani": 30, "tip": "kalendarski",
        "napomena": "30 dana od iscrpljenja pravnih sredstava",
    },
}


class ProcesniRokRequest(BaseModel):
    datum_pocetka: str
    tip_roka: str
    predmet_id: Optional[str] = None


class ZastarelostRequest(BaseModel):
    tip:           str
    datum_pocetka: str


class IcsExportRequest(BaseModel):
    rokovi: List[dict]  # [{"naslov": str, "datum_iso": str, "opis": str}]


class RelativniDatumRequest(BaseModel):
    izraz: str = Field(..., min_length=3, max_length=100)


@router.post("/zastarelost/relativni-datum")
async def post_relativni_datum(req: RelativniDatumRequest):
    """Phase 3.6 — Konvertuje relativni srpski izraz u apsolutni datum."""
    from zastarelost import parsiraj_relativni_datum
    try:
        d = await asyncio.to_thread(parsiraj_relativni_datum, req.izraz)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "izraz":        req.izraz,
        "datum":        d.isoformat(),
        "datum_prikaz": d.strftime("%d.%m.%Y"),
    }


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


@router.post("/api/rokovi/procesni")
async def izracunaj_procesni_rok(
    payload: ProcesniRokRequest,
    user: dict = Depends(get_current_user),
):
    """Izračunaj procesni rok (ZPP/ZKP/ZR/ZIO/ZUP) uz srpske praznike i radne dane."""
    try:
        datum = _date.fromisoformat(payload.datum_pocetka)
    except ValueError:
        raise HTTPException(status_code=400, detail="Neispravan datum. Koristite YYYY-MM-DD.")

    rok_info = PROCESNI_ROKOVI.get(payload.tip_roka)
    if not rok_info:
        raise HTTPException(
            status_code=400,
            detail=f"Nepoznat tip roka. Dostupni: {', '.join(PROCESNI_ROKOVI.keys())}",
        )

    if rok_info["tip"] == "radni":
        datum_isteka = await asyncio.to_thread(
            _radni_dani_add, datum, rok_info["dani"], False
        )
    else:
        datum_isteka = datum + _td(days=rok_info["dani"])

    # Pomeri na sledeći radni dan ako rok pada u neradni
    praznici = _srpski_praznici(datum_isteka.year)
    while datum_isteka.weekday() >= 5 or datum_isteka in praznici:
        datum_isteka += _td(days=1)

    dani_do = (datum_isteka - _date.today()).days

    return {
        "tip_roka":       payload.tip_roka,
        "naziv":          rok_info["naziv"],
        "datum_pocetka":  str(datum),
        "datum_isteka":   str(datum_isteka),
        "dani_do_isteka": dani_do,
        "hitno":          dani_do <= 7,
        "isteklo":        dani_do < 0,
        "napomena":       rok_info["napomena"],
        "predmet_id":     payload.predmet_id,
    }


@router.get("/api/rokovi/procesni/tipovi")
async def get_procesni_rokovi_tipovi():
    """Lista svih dostupnih tipova procesnih rokova za frontend dropdown."""
    return {
        "tipovi": [
            {
                "kod":      k,
                "naziv":    v["naziv"],
                "dani":     v["dani"],
                "tip":      v["tip"],
                "napomena": v["napomena"],
            }
            for k, v in PROCESNI_ROKOVI.items()
        ]
    }


@router.get("/api/rokovi/praznici")
async def get_praznici(godina: int = None):
    """Lista srpskih državnih praznika za datu godinu."""
    g = godina or _date.today().year
    praznici = sorted(_srpski_praznici(g))
    return {"godina": g, "praznici": [str(p) for p in praznici]}


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


# ── AI Deadline Guardian ──────────────────────────────────────────────────────

class GuardianRequest(BaseModel):
    rok_naziv:       str
    rok_datum:       str                    # ISO: "2026-07-15"
    tip_postupka:    str                    # gradjansko|krivicno|radno|upravno|privredno
    opis_predmeta:   Optional[str]  = None
    dostupni_dokazi: list[str]      = []
    predmet_id:      Optional[str]  = None


@router.post("/api/rokovi/guardian")
@limiter.limit("20/minute")
async def deadline_guardian(
    request: Request,
    payload: GuardianRequest,
    user: dict = Depends(get_current_user),
):
    """
    AI Deadline Guardian: analizira rok i generiše konkretan lanac akcija
    sa međurokovima, kritičnom putanjom i preporukom za danas.
    """
    from openai import OpenAI

    try:
        rok_datum = _date.fromisoformat(payload.rok_datum)
    except ValueError:
        raise HTTPException(status_code=400, detail="Neispravan format datuma. Koristite YYYY-MM-DD.")

    danas = _date.today()
    dani_do_roka = (rok_datum - danas).days

    if dani_do_roka < 0:
        raise HTTPException(status_code=400, detail="Rok je već prošao.")

    praznici = _srpski_praznici(danas.year) | _srpski_praznici(rok_datum.year)
    radnih_dana = sum(
        1 for i in range(dani_do_roka)
        if (danas + _td(days=i + 1)).weekday() < 5
        and (danas + _td(days=i + 1)) not in praznici
    )

    dokazi_txt = "\n".join(f"- {d}" for d in payload.dostupni_dokazi) if payload.dostupni_dokazi else "Nisu navedeni"

    system_prompt = (
        "Ti si ekspertni pravni strateg sa 30 godina iskustva u srpskim sudovima.\n\n"
        "Tvoj zadatak: Na osnovu roka i opisa predmeta, napravi KONKRETAN vremenski plan svih akcija "
        "koje advokat mora da preduzme PRE nego što rok istekne.\n\n"
        "Razmišljaj unatrag od roka: šta mora biti gotovo dan pre roka? Šta nedelju dana pre? Itd.\n\n"
        "Pravila:\n"
        "- Budi apsolutno konkretan (ne 'pribavi dokumenta' nego 'pozovi sud i zatraži overenu kopiju presude')\n"
        "- Svaka akcija ima rok do kada mora biti završena\n"
        "- Identifikuj KRITIČNU PUTANJU — koja akcija, ako kasni, ruši ceo plan\n"
        "- Upozori na skrivene zamke (praznike, sudske odmore, notarske rokove)\n"
        "- Ekavica, direktan ton"
    )

    user_prompt = (
        f"ROK: {payload.rok_naziv}\n"
        f"Datum isteka: {payload.rok_datum} (za {dani_do_roka} kalendarskih dana / {radnih_dana} radnih dana)\n"
        f"Tip postupka: {payload.tip_postupka}\n\n"
        f"Opis predmeta: {payload.opis_predmeta or 'Nije naveden'}\n\n"
        f"Dostupni dokumenti:\n{dokazi_txt}\n\n"
        "Napravi:\n"
        "1. LANAC AKCIJA (sa konkretnim međurokovima za svaku akciju)\n"
        "2. KRITIČNA PUTANJA (koja akcija je najhitnija DANAS)\n"
        "3. SKRIVENE ZAMKE (šta može da pokvari plan)\n"
        "4. PREPORUČENA AKCIJA ZA DANAS (jedna konkretna stvar)\n\n"
        "Format: strukturiran, čitljiv, sa datumima i brojevima dana."
    )

    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=1200,
            temperature=0.3,
        )
    )

    analiza = resp.choices[0].message.content.strip()
    hitnost = (
        "kritično" if dani_do_roka <= 3 else
        "hitno"    if dani_do_roka <= 7 else
        "prati"    if dani_do_roka <= 14 else
        "planiraj"
    )

    return {
        "rok_naziv":    payload.rok_naziv,
        "rok_datum":    payload.rok_datum,
        "dani_do_roka": dani_do_roka,
        "radnih_dana":  radnih_dana,
        "hitnost":      hitnost,
        "analiza":      analiza,
        "tip_postupka": payload.tip_postupka,
        "predmet_id":   payload.predmet_id,
    }


@router.post("/api/rokovi/guardian/scan")
async def guardian_scan(
    user: dict = Depends(get_current_user),
):
    """
    Skenira sve aktivne rokove korisnika u narednih 30 dana i vraća
    prioritizovanu listu sa procenom hitnosti za svaki.
    """
    uid  = user["user_id"]
    supa = _get_supa()
    danas     = _date.today()
    za_30d    = danas + _td(days=30)

    rokovi_r = await asyncio.to_thread(
        lambda: supa.table("rokovi")
            .select("id, naziv, datum, tip, predmet_id, opis")
            .eq("user_id", uid)
            .gte("datum", danas.isoformat())
            .lte("datum", za_30d.isoformat())
            .order("datum")
            .execute()
    )

    rokovi = rokovi_r.data or []
    if not rokovi:
        return {"scan": [], "ukupno": 0, "kriticno": 0, "hitno": 0,
                "period_dana": 30, "generirano": danas.isoformat(),
                "poruka": "Nema rokova u narednih 30 dana."}

    praznici = _srpski_praznici(danas.year)

    scan = []
    for rok in rokovi:
        try:
            rok_datum = _date.fromisoformat(str(rok["datum"])[:10])
            dani      = (rok_datum - danas).days
            radnih    = sum(
                1 for i in range(dani)
                if (danas + _td(days=i + 1)).weekday() < 5
                and (danas + _td(days=i + 1)) not in praznici
            )
            hitnost = (
                "kritično" if dani <= 2 else
                "hitno"    if dani <= 5 else
                "prati"    if dani <= 14 else
                "ok"
            )
            scan.append({
                "id":          rok.get("id"),
                "naziv":       rok.get("naziv", "Rok"),
                "datum":       str(rok["datum"])[:10],
                "dani_ostalo": dani,
                "radnih_dana": radnih,
                "hitnost":     hitnost,
                "predmet_id":  rok.get("predmet_id"),
                "tip":         rok.get("tip"),
            })
        except Exception:
            continue

    hitnost_order = {"kritično": 0, "hitno": 1, "prati": 2, "ok": 3}
    scan.sort(key=lambda x: (hitnost_order.get(x["hitnost"], 4), x["dani_ostalo"]))

    return {
        "scan":        scan,
        "ukupno":      len(scan),
        "kriticno":    sum(1 for r in scan if r["hitnost"] == "kritično"),
        "hitno":       sum(1 for r in scan if r["hitnost"] == "hitno"),
        "period_dana": 30,
        "generirano":  danas.isoformat(),
    }
