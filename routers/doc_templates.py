# -*- coding: utf-8 -*-
"""
Vindex AI — routers/doc_templates.py

Generisanje pravnih dokumenata iz šablona pomoću GPT-4o.
Podržani tipovi: ugovor o zastupanju, tužba, žalba, punomoćje, opomena.

Endpoints:
  GET  /api/doc-templates/lista       — lista dostupnih šablona
  POST /api/doc-templates/generiši    — generiše dokument iz šablona (GPT-4o)
  POST /api/doc-templates/sačuvaj     — čuva generisani dokument u predmet_dokumenti
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.doc_templates")
router = APIRouter(prefix="/api/doc-templates", tags=["doc_templates"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ─── Šabloni ──────────────────────────────────────────────────────────────────

_SABLONI = [
    {
        "id":      "tuzba-opstinska",
        "naziv":   "Tužba — Opštinski sud",
        "tip":     "tuzba",
        "opis":    "Tužba opštinskom sudu za naknadu štete ili ispunjenje ugovora.",
        "polja":   ["ime_tuzitelja", "adresa_tuzitelja", "ime_tuzenog", "adresa_tuzenog", "cinjenice", "vrednost_spora_rsd", "datum"],
        "prompt":  "Napiši formalnu tužbu opštinskom sudu na srpskom jeziku (ekavica). Tužilac: {ime_tuzitelja}, {adresa_tuzitelja}. Tuženi: {ime_tuzenog}, {adresa_tuzenog}. Vrednost spora: {vrednost_spora_rsd} RSD. Datum: {datum}. Činjenični opis: {cinjenice}. Format: standardni srpski sudski podnesak sa zaglavljem, predmetom, činjeničnim opisom i predlogom za presudu. Bez preteranog pravnog žargona — jasno i precizno."
    },
    {
        "id":      "zalba-presuda",
        "naziv":   "Žalba na presudu",
        "tip":     "zalba",
        "opis":    "Žalba višem sudu na prvostepenu presudu.",
        "polja":   ["ime_stranke", "broj_predmeta", "naziv_suda", "datum_presude", "razlozi_zalbe", "datum"],
        "prompt":  "Napiši formalnu žalbu na presudu na srpskom jeziku (ekavica). Stranka: {ime_stranke}. Predmet br.: {broj_predmeta}, Sud: {naziv_suda}. Datum prvostepene presude: {datum_presude}. Datum žalbe: {datum}. Razlozi žalbe: {razlozi_zalbe}. Format: standardni srpski sudski podnesak sa zaglavljem, navodom razloga žalbe i predlogom drugostepenom sudu."
    },
    {
        "id":      "punomocje-opste",
        "naziv":   "Punomoćje — Opšte",
        "tip":     "punomocje",
        "opis":    "Opšte punomoćje za zastupanje pred svim organima.",
        "polja":   ["ime_vlastodavca", "jmbg_vlastodavca", "adresa_vlastodavca", "ime_punomoćnika", "datum"],
        "prompt":  "Napiši opšte punomoćje na srpskom jeziku (ekavica). Vlastodavac: {ime_vlastodavca}, JMBG: {jmbg_vlastodavca}, adresa: {adresa_vlastodavca}. Punomoćnik (advokat): {ime_punomoćnika}. Datum: {datum}. Format: kratko, formalno, sa svim potrebnim elementima za punomoćje pred sudovima i državnim organima u Republici Srbiji."
    },
    {
        "id":      "opomena-pred-utuzenje",
        "naziv":   "Opomena pred utuženje",
        "tip":     "opomena",
        "opis":    "Formalna opomena dužniku pre pokretanja sudskog postupka.",
        "polja":   ["ime_poverioca", "ime_duznika", "adresa_duznika", "iznos_rsd", "osnov_duga", "rok_dana", "datum"],
        "prompt":  "Napiši formalnu opomenu pred utuženje na srpskom jeziku (ekavica). Poverilac: {ime_poverioca}. Dužnik: {ime_duznika}, adresa: {adresa_duznika}. Iznos duga: {iznos_rsd} RSD. Osnov: {osnov_duga}. Rok za plaćanje: {rok_dana} dana. Datum: {datum}. Format: kratko, jasno, sa upozorenjem na sudski postupak i troškove ako dug ne bude izmiren u roku."
    },
    {
        "id":      "ugovor-o-delu",
        "naziv":   "Ugovor o delu",
        "tip":     "ugovor",
        "opis":    "Ugovor o izvršenju određenog posla između naručioca i izvođača.",
        "polja":   ["ime_narucioca", "adresa_narucioca", "ime_izvodjaca", "adresa_izvodjaca", "opis_posla", "rok_izvrsenja", "naknada_rsd", "datum"],
        "prompt":  "Napiši ugovor o delu na srpskom jeziku (ekavica). Naručilac: {ime_narucioca}, adresa: {adresa_narucioca}. Izvođač: {ime_izvodjaca}, adresa: {adresa_izvodjaca}. Predmet ugovora (opis posla): {opis_posla}. Rok izvršenja: {rok_izvrsenja}. Naknada: {naknada_rsd} RSD. Datum: {datum}. Format: standardni srpski ugovor sa svim potrebnim odredbama (predmet, rokovi, naknada, odgovornost, raskid, potpisi)."
    },
    {
        "id":      "ugovor-o-zajmu",
        "naziv":   "Ugovor o zajmu (pozajmici)",
        "tip":     "ugovor",
        "opis":    "Ugovor o novčanoj pozajmici između fizičkih ili pravnih lica.",
        "polja":   ["ime_zajmodavca", "ime_zajmoprimca", "iznos_rsd", "rok_vracanja", "kamata_posto", "datum"],
        "prompt":  "Napiši ugovor o zajmu na srpskom jeziku (ekavica). Zajmodavac: {ime_zajmodavca}. Zajmoprimac: {ime_zajmoprimca}. Iznos pozajmice: {iznos_rsd} RSD. Rok vraćanja: {rok_vracanja}. Kamata: {kamata_posto}% godišnje (0 za beskamatni zajam). Datum: {datum}. Format: standardni srpski ugovor o zajmu sa svim elementima (iznos, rok, kamata, posledice neplaćanja, potpisi)."
    },
    {
        "id":      "predlog-za-izvrsenje",
        "naziv":   "Predlog za izvršenje",
        "tip":     "tuzba",
        "opis":    "Predlog za prinudno izvršenje na osnovu izvršne isprave.",
        "polja":   ["ime_trazioca", "adresa_trazioca", "ime_duznika", "adresa_duznika", "izvrsna_isprava", "iznos_rsd", "nacin_izvrsenja", "datum"],
        "prompt":  "Napiši predlog za izvršenje na srpskom jeziku (ekavica). Tražilac izvršenja: {ime_trazioca}, adresa: {adresa_trazioca}. Izvršni dužnik: {ime_duznika}, adresa: {adresa_duznika}. Izvršna isprava: {izvrsna_isprava}. Iznos: {iznos_rsd} RSD. Način izvršenja: {nacin_izvrsenja}. Datum: {datum}. Format: standardni srpski predlog za izvršenje sa svim zakonskim elementima."
    },
]


# ─── Models ───────────────────────────────────────────────────────────────────

class GenerisuReq(BaseModel):
    sablon_id: str = Field(..., min_length=1, max_length=64)
    polja:     dict = Field(default_factory=dict)
    predmet_id: Optional[str] = Field(default=None)


class SacuvajReq(BaseModel):
    predmet_id: str  = Field(..., min_length=1)
    naziv:      str  = Field(..., min_length=1, max_length=200)
    sadrzaj:    str  = Field(..., min_length=10)
    sablon_id:  str  = Field(default="", max_length=64)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/lista")
@limiter.limit("60/minute")
async def lista_sablona(request: Request, user: dict = Depends(get_current_user)):
    return {
        "sabloni": [
            {"id": s["id"], "naziv": s["naziv"], "tip": s["tip"],
             "opis": s["opis"], "polja": s["polja"]}
            for s in _SABLONI
        ],
        "ukupno": len(_SABLONI),
    }


@router.post("/generiši")
@limiter.limit("10/minute")
async def generiši_dokument(
    request: Request,
    req: GenerisuReq,
    user: dict = Depends(get_current_user),
):
    """Generiše pravni dokument iz šablona koristeći GPT-4o."""
    sablon = next((s for s in _SABLONI if s["id"] == req.sablon_id), None)
    if not sablon:
        raise HTTPException(status_code=404, detail=f"Šablon '{req.sablon_id}' nije pronađen.")

    prompt = sablon["prompt"]
    for kljuc, vrednost in (req.polja or {}).items():
        prompt = prompt.replace("{" + kljuc + "}", str(vrednost or ""))

    for polje in sablon["polja"]:
        prompt = prompt.replace("{" + polje + "}", f"[{polje.upper()} — NIJE UNETO]")

    system = (
        "Ti si srpski pravni asistent specijalizovan za izradu pravnih dokumenata. "
        "Pišeš formalne pravne akte na srpskom jeziku, ekavica. "
        "Dokumenti moraju biti u skladu sa zakonodavstvom Republike Srbije. "
        "Vraćaj samo tekst dokumenta, bez objašnjenja i bez markdown formatiranja."
    )

    try:
        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        resp = await oai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        tekst = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("[DOC-TPL] OpenAI greška: %s", e)
        raise HTTPException(status_code=502, detail="Generisanje dokumenta trenutno nije dostupno.")

    logger.info("[DOC-TPL] sablon=%s uid=%.8s", req.sablon_id, user["user_id"])
    return {
        "ok":       True,
        "sablon_id": req.sablon_id,
        "naziv":    sablon["naziv"],
        "sadrzaj":  tekst,
    }


@router.post("/sačuvaj")
@limiter.limit("20/minute")
async def sacuvaj_dokument(
    request: Request,
    req: SacuvajReq,
    user: dict = Depends(get_current_user),
):
    """Čuva generisani dokument kao beleška uz predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_beleske").insert({
                "predmet_id": req.predmet_id,
                "user_id":    uid,
                "tekst":      f"📄 {req.naziv}\n\n{req.sadrzaj}",
                "tip":        "dokument",
            }).execute()
        )
        if not r.data:
            raise HTTPException(status_code=500, detail="Čuvanje nije uspelo.")
        return {"ok": True, "beleska_id": r.data[0]["id"], "naziv": req.naziv}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[DOC-TPL] čuvanje greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri čuvanju dokumenta.")
