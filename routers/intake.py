# -*- coding: utf-8 -*-
"""
Vindex AI — routers/intake.py

POST /api/intake/ekstrakcija  — GPT-4o-mini entity extraction
POST /api/intake/kreiraj      — Create predmet + link klijent + add rok
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.intake")
router = APIRouter(tags=["intake"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_EKSTRAKCIJA_SYSTEM = """Ti si pravni asistent za srpske advokate. Na osnovu opisa problema i opcionalnih nalaza iz analize dokumenta, ekstrahuj ključne podatke za otvaranje novog predmeta.

Vrati ISKLJUČIVO validan JSON bez markdown fence-ova, bez ikakvih komentara:
{
  "predlog_naziva_predmeta": "<kratak opisni naziv, max 80 znakova>",
  "protivna_strana": "<ime/naziv protivne strane ILI null ako nije pomenuta>",
  "vrsta_spora": "<radni spor|ugovorni spor|naknada štete|nasleđe|porodično pravo|privredno pravo|krivično|nekretnine|ostalo>",
  "vrednost_spora": "<iznos u RSD kao string npr. '500000 RSD' ILI null>",
  "prvi_rok": "<datum u formatu YYYY-MM-DD ILI null — SAMO ako je eksplicitno naveden u tekstu>",
  "rok_opis": "<opis roka ILI null>",
  "potrebni_dokumenti": ["<naziv dokumenta>"]
}

APSOLUTNA PRAVILA:
1. prvi_rok = null osim ako datum nije EKSPLICITNO naveden u tekstu. NE izmišljaj datume.
2. vrednost_spora = null ako iznos nije pomenut.
3. protivna_strana = null ako nije pomenuta.
4. Jezik: srpski ekavica.
5. potrebni_dokumenti: navedi 2-5 dokumenata tipičnih za ovu vrstu spora."""


async def _call_ekstrakcija(opis: str, nalazi: list) -> dict:
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)

    context_parts = [f"Opis problema:\n{opis}"]
    if nalazi:
        top = nalazi[:5]
        nalazi_tekst = "\n".join(
            f"- [{f.get('severity', '')}] {f.get('finding', '')}"
            for f in top if isinstance(f, dict)
        )
        if nalazi_tekst:
            context_parts.append(f"\nNalazi iz analize dokumenta:\n{nalazi_tekst}")

    user_msg = "\n".join(context_parts)

    try:
        r = await oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _EKSTRAKCIJA_SYSTEM},
                {"role": "user",   "content": user_msg[:3000]},
            ],
            temperature=0.2,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        raw = (r.choices[0].message.content or "{}").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[INTAKE] JSON parse greška: %s", e)
        raise HTTPException(status_code=502, detail="AI ekstrakcija vratila neispravan odgovor.")
    except Exception as e:
        logger.error("[INTAKE] OpenAI greška: %s", e)
        raise HTTPException(status_code=502, detail="AI ekstrakcija trenutno nedostupna.")


class EkstrakcijReq(BaseModel):
    opis_problema: str = Field(..., min_length=20, max_length=4000)
    analiza_results: Optional[List[dict]] = None


class IntakeKreirajReq(BaseModel):
    klijent_id:      str           = Field(..., min_length=1, max_length=64)
    naziv:           str           = Field(..., min_length=2, max_length=200)
    opis:            str           = Field(default="", max_length=4000)
    tip:             str           = Field(default="opsti", max_length=50)
    vrsta_spora:     str           = Field(default="", max_length=100)
    vrednost_spora:  str           = Field(default="", max_length=100)
    protivna_strana: str           = Field(default="", max_length=200)
    prvi_rok:        Optional[str] = Field(default=None, max_length=12)
    rok_opis:        Optional[str] = Field(default=None, max_length=300)


@router.post("/api/intake/ekstrakcija")
@limiter.limit("20/minute")
async def intake_ekstrakcija(
    body: EkstrakcijReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ekstrahuje ključne podatke za novi predmet iz opisa problema i opcionalnih nalaza."""
    nalazi = body.analiza_results or []
    result = await _call_ekstrakcija(body.opis_problema, nalazi)

    return {
        "predlog_naziva_predmeta": result.get("predlog_naziva_predmeta") or "Novi predmet",
        "protivna_strana":        result.get("protivna_strana"),
        "vrsta_spora":            result.get("vrsta_spora") or "ostalo",
        "vrednost_spora":         result.get("vrednost_spora"),
        "prvi_rok":               result.get("prvi_rok"),
        "rok_opis":               result.get("rok_opis"),
        "potrebni_dokumenti":     result.get("potrebni_dokumenti") or [],
    }


@router.post("/api/intake/kreiraj")
@limiter.limit("30/minute")
async def intake_kreiraj(
    body: IntakeKreirajReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Kreira predmet, linkuje klijenta i opcionalno dodaje rok."""
    uid  = user["user_id"]
    supa = _get_supa()

    opis_delovi = [body.opis] if body.opis else []
    if body.protivna_strana:
        opis_delovi.append(f"Protivna strana: {body.protivna_strana}")
    if body.vrsta_spora:
        opis_delovi.append(f"Vrsta spora: {body.vrsta_spora}")
    if body.vrednost_spora:
        opis_delovi.append(f"Vrednost spora: {body.vrednost_spora}")
    full_opis = "\n".join(opis_delovi)

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti").insert({
            "user_id": uid,
            "naziv":   body.naziv,
            "opis":    full_opis,
            "tip":     body.tip,
            "status":  "aktivan",
        }).execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=500, detail="Kreiranje predmeta nije uspelo.")
    predmet    = pred_r.data[0]
    predmet_id = predmet["id"]

    try:
        await asyncio.to_thread(
            lambda: supa.table("predmet_klijenti").insert({
                "predmet_id":     predmet_id,
                "klijent_id":     body.klijent_id,
                "uloga_klijenta": "stranka",
                "user_id":        uid,
            }).execute()
        )
    except Exception as e:
        logger.warning("[INTAKE] predmet_klijenti insert greška: %s", e)

    rok_dodat = False
    if body.prvi_rok:
        try:
            naziv_roka = (body.rok_opis or "Rok").strip()[:200]
            await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    uid,
                    "dogadjaj":   naziv_roka,
                    "datum":      body.prvi_rok,
                    "datum_iso":  body.prvi_rok,
                    "vaznost":    "bitan",
                    "akter":      "Intake Wizard (AI)",
                }).execute()
            )
            rok_dodat = True
        except Exception as e:
            logger.warning("[INTAKE] rok insert greška: %s", e)

    logger.info("[INTAKE] predmet=%s uid=%.8s rok=%s", predmet_id, uid, rok_dodat)
    return {
        "success":    True,
        "predmet_id": predmet_id,
        "predmet":    predmet,
        "rok_dodat":  rok_dodat,
    }
