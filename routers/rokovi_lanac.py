# -*- coding: utf-8 -*-
"""
Vindex AI — routers/rokovi_lanac.py

GET  /api/rokovi/tipovi-dogadjaja  — Katalog tipova procesnih dogadjaja
POST /api/rokovi/lanac             — Automatski lanac ZPP procesnih rokova

Generiše sve relevantne procesne rokove na osnovu datuma ključnog akta.
Opciono upisuje rokove direktno u predmet_hronologija.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.rokovi_lanac")
router = APIRouter(tags=["rokovi"])

# ─── Katalog ZPP procesnih rokova ────────────────────────────────────────────

_TIPOVI: dict[str, dict] = {
    "dostava_presude_prvostepene": {
        "naziv": "Dostava presude prvostepenog suda",
        "opis":  "Datum prijema presude prvostepenog suda od strane stranke",
        "rokovi": [
            {
                "naziv":          "Rok za žalbu",
                "opis":           "Rok za izjavljivanje žalbe na presudu prvostepenog suda",
                "zakonski_osnov": "ZPP čl. 374 st. 1",
                "dana":           15,
                "vaznost":        "kritican",
                "tip_roka":       "zalba",
            },
            {
                "naziv":          "Okvirni rok za odgovor na žalbu",
                "opis":           "Protivna strana ima 8 dana od dostave žalbe (okvirno ~23. dan od dostave presude)",
                "zakonski_osnov": "ZPP čl. 379 st. 1",
                "dana":           23,
                "vaznost":        "vazno",
                "tip_roka":       "odgovor_na_zalbu",
            },
            {
                "naziv":          "Pravosnažnost presude (bez žalbe)",
                "opis":           "Presuda postaje pravosnažna po proteku roka za žalbu ako žalba nije izjavljena",
                "zakonski_osnov": "ZPP čl. 374 st. 1",
                "dana":           15,
                "vaznost":        "info",
                "tip_roka":       "pravosnaznost",
            },
        ],
    },
    "dostava_presude_drugostepene": {
        "naziv": "Dostava presude drugostepenog suda",
        "opis":  "Datum prijema presude Apelacionog suda",
        "rokovi": [
            {
                "naziv":          "Rok za reviziju",
                "opis":           "Rok za izjavljivanje revizije Vrhovnom kasacionom sudu",
                "zakonski_osnov": "ZPP čl. 393 st. 1",
                "dana":           30,
                "vaznost":        "kritican",
                "tip_roka":       "revizija",
            },
            {
                "naziv":          "Okvirni rok za odgovor na reviziju",
                "opis":           "Protivna strana ima 15 dana od dostave revizije (~45. dan od dostave presude)",
                "zakonski_osnov": "ZPP čl. 396 st. 1",
                "dana":           45,
                "vaznost":        "vazno",
                "tip_roka":       "odgovor_na_reviziju",
            },
        ],
    },
    "dostava_zalbe": {
        "naziv": "Dostava žalbe protivnoj strani",
        "opis":  "Datum kada je sud dostavio žalbu protivnoj strani",
        "rokovi": [
            {
                "naziv":          "Rok za odgovor na žalbu",
                "opis":           "Rok za podnošenje odgovora na žalbu drugoj strani",
                "zakonski_osnov": "ZPP čl. 379 st. 1",
                "dana":           8,
                "vaznost":        "kritican",
                "tip_roka":       "odgovor_na_zalbu",
            },
        ],
    },
    "dostava_tuzbe": {
        "naziv": "Dostava tužbe tuženom",
        "opis":  "Datum kada je tuženom dostavljena tužba sa pozivom za odgovor",
        "rokovi": [
            {
                "naziv":          "Rok za odgovor na tužbu",
                "opis":           "Rok tuženog za podnošenje odgovora na tužbu",
                "zakonski_osnov": "ZPP čl. 296 st. 1",
                "dana":           15,
                "vaznost":        "kritican",
                "tip_roka":       "odgovor_na_tuzbu",
            },
            {
                "naziv":          "Okvirni rok za pripremno ročište",
                "opis":           "Sud zakazuje pripremno ročište po isteku roka za odgovor (okvirni termin)",
                "zakonski_osnov": "ZPP čl. 303",
                "dana":           45,
                "vaznost":        "info",
                "tip_roka":       "pripremno_rociste",
            },
        ],
    },
    "dostava_resenja": {
        "naziv": "Dostava rešenja suda",
        "opis":  "Datum kada je stranka primila rešenje suda",
        "rokovi": [
            {
                "naziv":          "Rok za žalbu na rešenje",
                "opis":           "Rok za izjavljivanje žalbe na rešenje prvostepenog suda",
                "zakonski_osnov": "ZPP čl. 354 st. 1",
                "dana":           15,
                "vaznost":        "kritican",
                "tip_roka":       "zalba_na_resenje",
            },
        ],
    },
    "dostava_revizije": {
        "naziv": "Dostava revizije protivnoj strani",
        "opis":  "Datum kada je Vrhovni kasacioni sud dostavio reviziju protivnoj strani",
        "rokovi": [
            {
                "naziv":          "Rok za odgovor na reviziju",
                "opis":           "Rok protivne strane za podnošenje odgovora na reviziju VKS-u",
                "zakonski_osnov": "ZPP čl. 396 st. 1",
                "dana":           15,
                "vaznost":        "kritican",
                "tip_roka":       "odgovor_na_reviziju",
            },
        ],
    },
    # ── ZKP — Zakonik o krivičnom postupku ───────────────────────────────────
    "zkp_dostava_presude": {
        "naziv": "Dostava krivične presude (ZKP)",
        "opis":  "Datum prijema presude krivičnog suda od strane stranke ili branioca",
        "rokovi": [
            {
                "naziv":          "Rok za žalbu na presudu",
                "opis":           "Rok za izjavljivanje žalbe na presudu prvostepenog krivičnog suda",
                "zakonski_osnov": "ZKP čl. 443",
                "dana":           15,
                "vaznost":        "kritican",
                "tip_roka":       "zkp_zalba_presuda",
            },
        ],
    },
    "zkp_dostava_resenja": {
        "naziv": "Dostava rešenja u krivičnom postupku (ZKP)",
        "opis":  "Datum prijema rešenja donetog u toku krivičnog postupka",
        "rokovi": [
            {
                "naziv":          "Rok za žalbu na rešenje",
                "opis":           "Rok za izjavljivanje žalbe na rešenje u krivičnom postupku",
                "zakonski_osnov": "ZKP čl. 448",
                "dana":           8,
                "vaznost":        "kritican",
                "tip_roka":       "zkp_zalba_resenje",
            },
        ],
    },
    "zkp_pravosnaznost_presude": {
        "naziv": "Pravosnažnost krivične presude (ZKP)",
        "opis":  "Datum pravosnažnosti krivične presude — polazni datum za zahtev za zaštitu zakonitosti",
        "rokovi": [
            {
                "naziv":          "Rok za zahtev za zaštitu zakonitosti",
                "opis":           "Rok za podnošenje zahteva za zaštitu zakonitosti Vrhovnom kasacionom sudu",
                "zakonski_osnov": "ZKP čl. 484",
                "dana":           30,
                "vaznost":        "kritican",
                "tip_roka":       "zkp_zahtev_zastita_zakonitosti",
            },
        ],
    },
    # ── Zakon o radu ─────────────────────────────────────────────────────────
    "zr_dostava_resenja_otkaz": {
        "naziv": "Dostava rešenja o otkazu ugovora o radu (ZR)",
        "opis":  "Datum kada je zaposleni primio rešenje o otkazu ugovora o radu",
        "rokovi": [
            {
                "naziv":          "Rok za žalbu na rešenje o otkazu",
                "opis":           "Rok zaposlenog za izjavljivanje žalbe poslodavcu na rešenje o otkazu",
                "zakonski_osnov": "ZR čl. 185",
                "dana":           8,
                "vaznost":        "kritican",
                "tip_roka":       "zr_zalba_resenje_otkaz",
            },
            {
                "naziv":          "Rok za tužbu zbog nezakonitog otkaza",
                "opis":           "Rok zaposlenog za podnošenje tužbe sudu zbog nezakonitog otkaza (od dana saznanja)",
                "zakonski_osnov": "ZR čl. 195",
                "dana":           90,
                "vaznost":        "kritican",
                "tip_roka":       "zr_tuzba_otkaz",
            },
        ],
    },
    # ── Zakon o opštem upravnom postupku / Zakon o upravnim sporovima ────────
    "zup_dostava_prvostepenog_resenja": {
        "naziv": "Dostava prvostepenog upravnog rešenja (ZUP)",
        "opis":  "Datum kada je stranka primila prvostepeno rešenje organa uprave",
        "rokovi": [
            {
                "naziv":          "Rok za žalbu na prvostepeno rešenje",
                "opis":           "Rok za izjavljivanje žalbe drugostepenom organu na prvostepeno rešenje",
                "zakonski_osnov": "ZUP čl. 224",
                "dana":           15,
                "vaznost":        "kritican",
                "tip_roka":       "zup_zalba_prvostepeno",
            },
        ],
    },
    "zup_dostava_konacnog_resenja": {
        "naziv": "Dostava konačnog upravnog rešenja (ZUS)",
        "opis":  "Datum kada je stranka primila konačno rešenje organa uprave (prvostepeno bez žalbe ili drugostepeno)",
        "rokovi": [
            {
                "naziv":          "Rok za tužbu Upravnom sudu",
                "opis":           "Rok za podnošenje tužbe Upravnom sudu radi pokretanja upravnog spora",
                "zakonski_osnov": "ZUS čl. 18",
                "dana":           30,
                "vaznost":        "kritican",
                "tip_roka":       "zup_tuzba_upravni_sud",
            },
        ],
    },
    "zup_cutanje_uprave": {
        "naziv": "Ćutanje uprave — protok roka za donošenje rešenja (ZUP)",
        "opis":  "Datum podnošenja zahteva od koga se računa rok za ćutanje uprave",
        "rokovi": [
            {
                "naziv":          "Rok za prigovor zbog ćutanja uprave",
                "opis":           "Ako prvostepeni organ nije doneo rešenje u roku od 60 dana, stranka može izjaviti žalbu",
                "zakonski_osnov": "ZUP čl. 226",
                "dana":           60,
                "vaznost":        "vazno",
                "tip_roka":       "zup_prigovor_cutanje",
            },
        ],
    },
    # ── Zakon o izvršenju i obezbeđenju ──────────────────────────────────────
    "zio_dostava_resenja_o_izvrsenju": {
        "naziv": "Dostava rešenja o izvršenju (ZIO)",
        "opis":  "Datum kada je izvršni dužnik primio rešenje o izvršenju",
        "rokovi": [
            {
                "naziv":          "Rok za prigovor na rešenje o izvršenju",
                "opis":           "Rok izvršnog dužnika za podnošenje prigovora na rešenje o izvršenju",
                "zakonski_osnov": "ZIO čl. 74",
                "dana":           8,
                "vaznost":        "kritican",
                "tip_roka":       "zio_prigovor_resenje",
            },
            {
                "naziv":          "Rok za žalbu na rešenje o izvršenju",
                "opis":           "Rok za izjavljivanje žalbe na rešenje o izvršenju (ako prigovor nije dozvoljen)",
                "zakonski_osnov": "ZIO čl. 25",
                "dana":           15,
                "vaznost":        "kritican",
                "tip_roka":       "zio_zalba_resenje",
            },
        ],
    },
}

_VALID_TIPOVI = frozenset(_TIPOVI)

_VAZNOST_HRON: dict[str, str] = {
    "kritican": "kljucan",
    "vazno":    "normalan",
    "info":     "info",
}


def lista_tipova_dogadjaja() -> list[dict]:
    return [
        {"kljuc": k, "naziv": v["naziv"], "opis": v["opis"]}
        for k, v in _TIPOVI.items()
    ]


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    if re.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", raw):
        d, m, y = raw.split(".")
        return date(int(y), int(m), int(d))
    return date.fromisoformat(raw)


# Državni praznici Srbije (fiksni) — mesec/dan
_PRAZNICI_FIKSNI: set[tuple[int, int]] = {
    (1, 1), (1, 2),   # Nova godina
    (1, 7),            # Božić
    (2, 15), (2, 16),  # Dan državnosti
    (5, 1), (5, 2),    # Praznik rada
    (11, 11),          # Dan primirja
}

# Pokretni praznici 2025–2027 (pravoslavni Uskrs)
_PRAZNICI_POKRETNI: set[date] = {
    date(2025, 4, 18), date(2025, 4, 19), date(2025, 4, 20), date(2025, 4, 21),
    date(2026, 4, 10), date(2026, 4, 11), date(2026, 4, 12), date(2026, 4, 13),
    date(2027, 4, 30), date(2027, 5, 1),  date(2027, 5, 2),  date(2027, 5, 3),
}


def _je_neradan(d: date) -> bool:
    if d.weekday() >= 5:
        return True
    if (d.month, d.day) in _PRAZNICI_FIKSNI:
        return True
    return d in _PRAZNICI_POKRETNI


def _adjust_for_weekend_holiday(datum: date) -> date:
    """Pomera procesni rok na sledeći radni dan ako pada na vikend ili praznik."""
    while _je_neradan(datum):
        datum += timedelta(days=1)
    return datum


def _build_lanac(tip: str, datum_pocetka: date) -> list[dict]:
    items = []
    for rok in _TIPOVI[tip]["rokovi"]:
        raw_target = datum_pocetka + timedelta(days=rok["dana"])
        target = _adjust_for_weekend_holiday(raw_target)
        items.append({
            "naziv":          rok["naziv"],
            "opis":           rok["opis"],
            "zakonski_osnov": rok["zakonski_osnov"],
            "dana":           rok["dana"],
            "datum_iso":      target.isoformat(),
            "datum_display":  target.strftime("%d.%m.%Y"),
            "vaznost":        rok["vaznost"],
            "tip_roka":       rok["tip_roka"],
        })
    return items


# ─── Request model ────────────────────────────────────────────────────────────

class LanacReq(BaseModel):
    tip_dogadjaja: str           = Field(..., min_length=3, max_length=60)
    datum_pocetka: str           = Field(..., min_length=8, max_length=10)
    predmet_id:    Optional[str] = Field(default=None, max_length=50)

    @field_validator("tip_dogadjaja")
    @classmethod
    def _val_tip(cls, v: str) -> str:
        v = v.strip()
        if v not in _VALID_TIPOVI:
            raise ValueError(f"Nepoznat tip_dogadjaja. Dozvoljeno: {sorted(_VALID_TIPOVI)}")
        return v

    @field_validator("datum_pocetka")
    @classmethod
    def _val_datum(cls, v: str) -> str:
        v = v.strip()
        try:
            _parse_date(v)
        except (ValueError, AttributeError):
            raise ValueError("datum_pocetka mora biti YYYY-MM-DD ili DD.MM.YYYY")
        return v


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/rokovi/tipovi-dogadjaja")
async def get_tipovi_dogadjaja():
    """Katalog tipova procesnih dogadjaja za ZPP lanac rokova."""
    return {"tipovi": lista_tipova_dogadjaja()}


@router.post("/api/rokovi/lanac")
@limiter.limit("30/minute")
async def post_rokovi_lanac(
    body: LanacReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Generiše automatski lanac ZPP procesnih rokova od datuma ključnog akta.

    Ako je prosleđen predmet_id, svaki rok se upisuje u predmet_hronologija.
    """
    uid   = user["user_id"]
    datum = _parse_date(body.datum_pocetka)
    lanac = _build_lanac(body.tip_dogadjaja, datum)

    sacuvano = False

    if body.predmet_id:
        supa = _get_supa()

        pred_res = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                        .select("id, naziv")
                        .eq("id", body.predmet_id)
                        .eq("user_id", uid)
                        .maybe_single()
                        .execute()
        )
        if not pred_res.data:
            raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

        records = [
            {
                "predmet_id": body.predmet_id,
                "user_id":    uid,
                "dogadjaj":   f"Rok: {r['naziv']} ({r['zakonski_osnov']})",
                "datum":      r["datum_iso"],
                "datum_iso":  r["datum_iso"],
                "vaznost":    _VAZNOST_HRON.get(r["vaznost"], "normalan"),
                "akter":      f"Automatski — ZPP lanac | {r['opis'][:200]}",
            }
            for r in lanac
        ]

        try:
            await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").insert(records).execute()
            )
            sacuvano = True
        except Exception as e:
            logger.warning("[ROKOVI_LANAC] hronologija insert greška: %s", e)

    tip_meta = _TIPOVI[body.tip_dogadjaja]
    logger.info(
        "[ROKOVI_LANAC] uid=%.8s tip=%s datum=%s predmet=%s sacuvano=%s",
        uid, body.tip_dogadjaja, datum.isoformat(), body.predmet_id, sacuvano,
    )

    return {
        "ok":                    True,
        "tip_dogadjaja":         body.tip_dogadjaja,
        "tip_naziv":             tip_meta["naziv"],
        "datum_pocetka_iso":     datum.isoformat(),
        "datum_pocetka_display": datum.strftime("%d.%m.%Y"),
        "lanac":                 lanac,
        "sacuvano_u_predmet":    sacuvano,
        "predmet_id":            body.predmet_id,
    }
