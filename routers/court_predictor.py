# -*- coding: utf-8 -*-
"""
Vindex AI — routers/court_predictor.py

AI Court Predictor: predviđa ishod sudskog postupka na osnovu
opisa predmeta, sudske prakse i pravnih argumenata.

Endpoints:
  POST /api/predictor/analiza  — predviđanje ishoda + šansa za uspeh
  GET  /api/predictor/faktori  — lista faktora koji utiču na predviđanje
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.court_predictor")
router = APIRouter(tags=["court-predictor"])


class PredictorRequest(BaseModel):
    opis_predmeta: str
    tip_postupka: str                          # gradjansko|krivicno|radno|upravno|privredno
    cinjenicni_opis: str
    dokazi: Optional[list[str]] = []
    suprotna_strana_argumenti: Optional[str] = None
    sud: Optional[str] = None
    predmet_id: Optional[str] = None


_PREDICTOR_SYSTEM = """Ti si ekspertni pravni analiticar sa 30 godina iskustva u srpskom pravosudju.
Analiziras pravne predmete i daješ procenu ishoda na osnovu:
- Vazeceg zakonodavstva Republike Srbije
- Sudske prakse srpskih sudova
- Jacine i relevantnosti dokaza
- Procesnih prednosti/nedostataka

STROGO pravilo:
1. Nikad ne garantuj ishod — uvek navedi procenat i objasni nesigurnost
2. Procenat iskazuj kao opseg (npr. "55%-70%") sa obrazlozenjem
3. Navedi kontra-argumente koje suprotna strana moze koristiti
4. Preporuci konkretne korake za jacanje pozicije

Format odgovora mora biti strukturiran i sadrzati:
- PROCENA ISHODA (%)
- KLJUCNI FAKTORI ZA i PROTIV
- PREPORUCENA STRATEGIJA
- RIZICI"""


@router.post("/api/predictor/analiza")
@limiter.limit("10/minute")
async def prediktuj_ishod(
    request: Request,
    payload: PredictorRequest,
    user: dict = Depends(get_current_user),
):
    """AI predviđanje ishoda sudskog postupka. Kosta 2 kredita."""
    uid = user["user_id"]
    supa = _get_supa()

    # Kredit provera (2 kredita)
    try:
        kredit_r = await asyncio.to_thread(
            lambda: supa.table("korisnici").select("krediti").eq("id", uid).single().execute()
        )
        if not kredit_r.data or kredit_r.data.get("krediti", 0) < 2:
            raise HTTPException(status_code=402, detail="Nedovoljno kredita. Potrebna su 2 kredita.")
    except HTTPException:
        raise
    except Exception:
        pass

    if not payload.opis_predmeta or len(payload.opis_predmeta) < 20:
        raise HTTPException(status_code=400, detail="Opis predmeta je prekratak (minimum 20 karaktera).")

    if payload.tip_postupka not in ["gradjansko", "krivicno", "radno", "upravno", "privredno"]:
        raise HTTPException(status_code=400, detail="Nepoznat tip postupka.")

    dokazi_txt = "\n".join([f"- {d}" for d in payload.dokazi]) if payload.dokazi else "Nisu navedeni"

    user_prompt = f"""PREDMET ZA ANALIZU:

Tip postupka: {payload.tip_postupka.upper()}
Sud: {payload.sud or "Nije navedeno"}

OPIS: {payload.opis_predmeta}

CINJENICE:
{payload.cinjenicni_opis}

DOSTUPNI DOKAZI:
{dokazi_txt}

ARGUMENTI SUPROTNE STRANE:
{payload.suprotna_strana_argumenti or "Nisu poznati"}

Analiziraj i daj strukturisano predvidjanje ishoda sa procentom sanse za uspeh."""

    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _PREDICTOR_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1500,
                temperature=0.3,
            )
        )

        analiza = resp.choices[0].message.content.strip()

        # Oduzmi 2 kredita
        try:
            await asyncio.to_thread(
                lambda: supa.rpc("oduzmi_kredite", {"p_user_id": uid, "p_kolicina": 2}).execute()
            )
        except Exception:
            pass

        # Sacuvaj analizu
        try:
            await asyncio.to_thread(
                lambda: supa.table("predictor_analize").insert({
                    "user_id":      uid,
                    "predmet_id":   payload.predmet_id,
                    "tip_postupka": payload.tip_postupka,
                    "opis":         payload.opis_predmeta[:500],
                    "analiza":      analiza[:5000],
                }).execute()
            )
        except Exception:
            pass

        return {
            "analiza":           analiza,
            "tip_postupka":      payload.tip_postupka,
            "krediti_utroseni":  2,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Court predictor greška: %s", e)
        raise HTTPException(status_code=500, detail=f"Greška pri analizi: {str(e)}")


@router.get("/api/predictor/faktori")
async def get_faktori(user: dict = Depends(get_current_user)):
    """Lista faktora koji utiču na ishod po tipu postupka."""
    return {
        "faktori": {
            "gradjansko": [
                "Jacina pisanih dokaza (ugovori, priznanice)",
                "Svedoci i njihova verodostojnost",
                "Zastarelost potrazivanja",
                "Teret dokazivanja",
                "Sudska praksa u slicnim slucajevima",
            ],
            "krivicno": [
                "Alibi optuzenog",
                "Verodostojnost svedoka",
                "Materijalni dokazi i lanac staranja",
                "Vestacenja (sudski vestaci)",
                "Prethodne osude",
            ],
            "radno": [
                "Pismeni otkazni akt i procedure",
                "Evidencija o radu i ucinku",
                "Kolektivni ugovor i pravilnik",
                "Rok za osporavanje otkaza",
                "Diskriminatorski osnov",
            ],
            "upravno": [
                "Zakonitost upravnog akta",
                "Postovanje procedure donosenja",
                "Obrazlozenost odluke",
                "Rok za zalbu",
                "Nadleznost organa",
            ],
            "privredno": [
                "Ugovorna dokumentacija",
                "Finansijski izvestaji i vestak",
                "Registracioni podaci privrednog subjekta",
                "Likvidnost tuzene strane",
                "Medjunarodna arbitraza (ako postoji klauzula)",
            ],
        }
    }
