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


def _build_lanac(tip: str, datum_pocetka: date) -> list[dict]:
    items = []
    for rok in _TIPOVI[tip]["rokovi"]:
        target = datum_pocetka + timedelta(days=rok["dana"])
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
                        .single()
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
