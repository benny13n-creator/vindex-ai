# -*- coding: utf-8 -*-
"""
Vindex AI — routers/region.py

Regionalna ekspanzija: podrška za advokate iz Bosne i Hercegovine,
Hrvatske, Slovenije, Crne Gore i Severne Makedonije.

Endpoints:
  GET  /api/region/podrska          — lista podržanih zemalja i njihove specifičnosti
  POST /api/region/ai-savet         — AI pravni savet prilagođen zakonu određene zemlje
  GET  /api/region/sudovi/{zemlja}  — lista sudova po zemlji
  POST /api/region/rokovi           — procesni rokovi po pravu određene zemlje
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.region")
router = APIRouter(tags=["region"])

# ── Podaci o zemljama ─────────────────────────────────────────────────────────

REGION_PODRSKA = {
    "RS": {
        "naziv":    "Republika Srbija",
        "jezik":    "srpski (ekavica)",
        "valuta":   "RSD",
        "sud_vrh":  "Vrhovni kasacioni sud",
        "kljucni_zakoni": [
            "ZPP (Zakon o parničnom postupku)",
            "ZKP (Zakonik o krivičnom postupku)",
            "ZOO (Zakon o obligacionim odnosima)",
            "ZR (Zakon o radu)",
            "ZIO (Zakon o izvršenju i obezbeđenju)",
        ],
        "sef_integracija":   True,
        "advokatska_komora": "Advokatska komora Srbije",
        "akreditovan":       True,
    },
    "BA": {
        "naziv":   "Bosna i Hercegovina",
        "jezik":   "bosanski/srpski/hrvatski",
        "valuta":  "BAM",
        "sud_vrh": "Sud Bosne i Hercegovine",
        "entiteti": ["Federacija BiH", "Republika Srpska", "Brčko Distrikt"],
        "kljucni_zakoni": [
            "ZPP FBiH (Zakon o parničnom postupku FBiH)",
            "ZPP RS (Zakon o parničnom postupku RS)",
            "ZKP BiH",
            "ZOO (Zakon o obligacionim odnosima)",
            "Zakon o radu FBiH / RS",
        ],
        "napomena":        "Dvojni pravni sistem: FBiH i RS imaju odvojena zakonodavstva",
        "sef_integracija": False,
        "akreditovan":     False,
    },
    "HR": {
        "naziv":   "Republika Hrvatska",
        "jezik":   "hrvatski",
        "valuta":  "EUR",
        "sud_vrh": "Vrhovni sud Republike Hrvatske",
        "kljucni_zakoni": [
            "ZPP (Zakon o parničnom postupku)",
            "ZKP (Zakon o kaznenom postupku)",
            "ZOO (Zakon o obveznim odnosima)",
            "ZR (Zakon o radu)",
            "OZ (Ovršni zakon)",
        ],
        "eu_clanica":      True,
        "sef_integracija": False,
        "napomena":        "EU pravo ima prednost — CJEU presude su obavezujuće",
        "akreditovan":     False,
    },
    "SI": {
        "naziv":   "Republika Slovenija",
        "jezik":   "slovenački",
        "valuta":  "EUR",
        "sud_vrh": "Vrhovno sodišče Republike Slovenije",
        "kljucni_zakoni": [
            "ZPP (Zakon o pravdnem postopku)",
            "ZKP (Zakon o kazenskem postopku)",
            "OZ (Obligacijski zakonik)",
            "ZDR-1 (Zakon o delovnih razmerjih)",
            "ZIZ (Zakon o izvršbi in zavarovanju)",
        ],
        "eu_clanica":      True,
        "sef_integracija": False,
        "napomena":        "Slovenački pravni tekstovi — AI daje odgovore na srpskom",
        "akreditovan":     False,
    },
    "ME": {
        "naziv":   "Crna Gora",
        "jezik":   "crnogorski/srpski",
        "valuta":  "EUR",
        "sud_vrh": "Vrhovni sud Crne Gore",
        "kljucni_zakoni": [
            "ZPP (Zakon o parničnom postupku)",
            "ZKP (Zakon o krivičnom postupku)",
            "ZOO (Zakon o obligacionim odnosima)",
            "Zakon o radu",
        ],
        "sef_integracija": False,
        "akreditovan":     False,
    },
    "MK": {
        "naziv":   "Republika Severna Makedonija",
        "jezik":   "makedonski",
        "valuta":  "MKD",
        "sud_vrh": "Vrhovni sud na Republika Severna Makedonija",
        "kljucni_zakoni": [
            "ZPP (Zakon za parnična postapka)",
            "KZ (Krivičen zakonik)",
            "ZOO (Zakon za obligacioni odnosi)",
            "ZRO (Zakon za rabotni odnosi)",
        ],
        "sef_integracija": False,
        "akreditovan":     False,
    },
}

SUDOVI_PO_ZEMLJI: dict = {
    "BA": {
        "FBiH": [
            "Vrhovni sud FBiH (Sarajevo)",
            "Kantonalni sudovi (Sarajevo, Mostar, Tuzla, Zenica, Bihać, Travnik, Orašje, Goražde, Livno)",
            "Općinski/Opštinski sudovi",
        ],
        "RS": [
            "Vrhovni sud RS (Banja Luka)",
            "Okružni sudovi (Banja Luka, Bijeljina, Doboj, Foča, Trebinje, Sarajevo-Istok)",
            "Osnovni sudovi",
        ],
        "BD":  ["Sud Brčko Distrikta"],
        "BiH": ["Sud Bosne i Hercegovine (Sarajevo)", "Ustavni sud BiH"],
    },
    "HR": [
        "Vrhovni sud RH (Zagreb)",
        "Visoki sudovi (Zagreb, Split, Rijeka, Osijek, Varaždin)",
        "Županski sudovi (21 županija)",
        "Prekršajni sudovi",
        "Trgovački sudovi",
        "Upravni sudovi",
        "Visoki prekršajni sud",
        "Visoki upravni sud",
    ],
    "SI": [
        "Vrhovno sodišče (Ljubljana)",
        "Višja sodišča (Ljubljana, Maribor, Koper, Celje)",
        "Okrožna sodišča",
        "Okrajna sodišča",
        "Delovno sodišče",
        "Upravno sodišče",
    ],
    "ME": [
        "Vrhovni sud (Podgorica)",
        "Apelacioni sud (Podgorica)",
        "Viši sudovi (Podgorica, Bijelo Polje)",
        "Osnovni sudovi",
    ],
    "MK": [
        "Vrhovni sud (Skopje)",
        "Apelacioni sudovi (Skopje, Gostivar, Štip, Bitola)",
        "Osnovni sudovi",
    ],
}

# ── Sistem promptovi ──────────────────────────────────────────────────────────

_REGION_SYSTEM_PROMPTS: dict[str, str] = {
    "BA": """Ti si ekspert za pravo Bosne i Hercegovine.
Bosna ima složen pravni sistem: Federacija BiH i Republika Srpska imaju ODVOJENA zakonodavstva.
Brčko Distrikt ima sopstvene zakone.
Na nivou države postoji Sud BiH za ratne zločine i organizovani kriminal.

Kada odgovaraš, uvek specificuj:
- Na koji entitet se primenjuje (FBiH, RS, BiH, Brčko)
- Koji zakon je relevantan za taj entitet
- Procesne razlike između entiteta ako postoje

Ekavica. Direktan ton.""",

    "HR": """Ti si ekspert za hrvatsko pravo.
Hrvatska je članica EU — EU pravo (direktive, uredbe, CJEU presude) ima prednost nad nacionalnim zakonodavstvom.
ZPP (parnični), OZ (ovršni), ZKP (kazneni), ZOO (obvezno pravo), ZR (radno).
Sudovi: Vrhovni sud → Visoki sudovi → Županski/Prekršajni/Trgovački.

Kada se radi o EU aspektu, navedi relevantnu EU direktivu ili presudu CJEU ako je poznaješ.
Ekavica (adaptirana za srpskog advokata). Direktan ton.""",

    "SI": """Ti si ekspert za slovenačko pravo.
Slovenija je članica EU — EU pravo ima prednost.
OZ (obligacijski zakonik), ZPP (pravdni postopek), ZDR-1 (delovna razmerja), ZKP (kazenski postopek), ZIZ (izvršba).
Odgovori su na srpskom jeziku, ali navodi nazive zakona na slovenačkom.

Ekavica. Direktan ton.""",

    "ME": """Ti si ekspert za pravo Crne Gore.
Crna Gora ima pravni sistem blizak srpskom — mnogi zakoni su slični ZPP, ZKP, ZOO RS.
Sudovi: Vrhovni → Apelacioni → Viši → Osnovni.
Crna Gora je kandidat za EU — neke direktive se primenjuju.

Ekavica. Direktan ton.""",

    "MK": """Ti si ekspert za pravo Republike Severne Makedonije.
Makedonija ima ZPP, KZ, ZOO, ZRO slične srpskom modelu.
Sudovi: Vrhovni → Apelacioni → Osnovni.
Makedonija je kandidat za EU.

Odgovori su na srpskom jeziku. Ekavica. Direktan ton.""",

    "RS": """Ti si ekspert za srpsko pravo.
ZPP, ZKP, ZOO, ZR, ZIO. Sudovi: VKS → Apelacioni → Viši/Privredni → Osnovni.
Ekavica. Direktan ton.""",
}

# ── Modeli ────────────────────────────────────────────────────────────────────

class RegionSavetRequest(BaseModel):
    pitanje: str
    zemlja:  str                      # "RS" | "BA" | "HR" | "SI" | "ME" | "MK"
    entitet: Optional[str] = None     # Za BiH: "FBiH" | "RS" | "BD" | "BiH"

# ── Endpointi ─────────────────────────────────────────────────────────────────

@router.get("/api/region/podrska")
async def get_region_podrska(user: dict = Depends(get_current_user)):
    """Lista podržanih zemalja sa pravnim sistemima."""
    return {
        "podrzane_zemlje": list(REGION_PODRSKA.keys()),
        "detalji":         REGION_PODRSKA,
    }


@router.post("/api/region/ai-savet")
@limiter.limit("20/minute")
async def region_ai_savet(
    request: Request,
    payload: RegionSavetRequest,
    user: dict = Depends(PermissionService.require("region_ai")),
):
    """AI pravni savet prilagođen pravu određene zemlje u regionu. 1 kredit."""
    zemlja = payload.zemlja.upper()

    if zemlja not in _REGION_SYSTEM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Zemlja '{zemlja}' nije podržana. Podržane: {', '.join(_REGION_SYSTEM_PROMPTS.keys())}",
        )

    if not payload.pitanje or len(payload.pitanje.strip()) < 10:
        raise HTTPException(status_code=400, detail="Pitanje je prekratko.")

    system_prompt = _REGION_SYSTEM_PROMPTS[zemlja]

    entitet_txt = ""
    if zemlja == "BA" and payload.entitet:
        entitet_txt = f"\n\nKorisnik pita za entitet: **{payload.entitet}**. Fokusiraj se na zakonodavstvo tog entiteta."

    zemlja_info = REGION_PODRSKA.get(zemlja, {})

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt + entitet_txt},
                {"role": "user",   "content": payload.pitanje},
            ],
            max_tokens=1500,
            temperature=0.3,
        )
    )

    odgovor = resp.choices[0].message.content.strip()

    await UsageService.consume(user["user_id"], user.get("email", ""), "region_ai")

    return {
        "odgovor":      odgovor,
        "zemlja":       zemlja,
        "zemlja_naziv": zemlja_info.get("naziv", zemlja),
        "entitet":      payload.entitet,
        "napomena":     zemlja_info.get("napomena"),
        "eu_clanica":   zemlja_info.get("eu_clanica", False),
        "akreditovan":  zemlja_info.get("akreditovan", False),
    }


@router.get("/api/region/sudovi/{zemlja}")
async def get_sudovi_zemlja(
    zemlja: str,
    user: dict = Depends(get_current_user),
):
    """Lista sudova za određenu zemlju u regionu."""
    z = zemlja.upper()
    if z not in SUDOVI_PO_ZEMLJI and z != "RS":
        raise HTTPException(status_code=404, detail=f"Sudovi za '{z}' nisu dostupni.")

    sudovi = SUDOVI_PO_ZEMLJI.get(z, ["Pogledati nacionalnu listu sudova"])

    return {
        "zemlja": z,
        "naziv":  REGION_PODRSKA.get(z, {}).get("naziv", z),
        "sudovi": sudovi,
    }


@router.post("/api/region/rokovi")
@limiter.limit("30/minute")
async def region_rokovi(
    request: Request,
    tip_roka: str,
    zemlja:   str,
    user: dict = Depends(PermissionService.require("region_ai")),
):
    """AI generisani procesni rokovi za određenu zemlju (prilagođeni lokalni zakoni)."""
    z = zemlja.upper()
    if z not in _REGION_SYSTEM_PROMPTS:
        raise HTTPException(status_code=400, detail=f"Zemlja nije podržana: {z}")

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    system = _REGION_SYSTEM_PROMPTS[z]

    resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"Koliki je rok za '{tip_roka}' po važećem pravu? "
                        "Navedi: broj dana, kalendarski ili radni dani, zakonski osnov (zakon + član), "
                        "posebne napomene. Kratko i konkretno."
                    ),
                },
            ],
            max_tokens=300,
            temperature=0.2,
        )
    )

    await UsageService.consume(user["user_id"], user.get("email", ""), "region_ai")

    return {
        "tip_roka": tip_roka,
        "zemlja":   z,
        "odgovor":  resp.choices[0].message.content.strip(),
        "napomena": "AI procena — obavezno proverite aktuelne propise.",
    }
