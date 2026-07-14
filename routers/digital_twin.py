# -*- coding: utf-8 -*-
"""
Vindex AI — routers/digital_twin.py

Digital Twin predmeta — AI simulira 3 scenarija razvoja predmeta,
predvida ishode sa procentima, identifikuje kljucne tacke odlucivanja
i analizira "sta ako" hipoteze.

Endpoints:
  POST /api/twin/simulacija    — kreira Digital Twin simulaciju (3 scenarija, 3 kredita)
  POST /api/twin/sta-ako       — "Sta ako" hipoteza analiza (1 kredit)
  GET  /api/twin/{predmet_id}  — dohvata poslednju simulaciju

SQL migracija (primeni rucno u Supabase Dashboard):
  CREATE TABLE IF NOT EXISTS twin_simulacije (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id UUID NOT NULL,
    user_id UUID NOT NULL,
    scenariji JSONB DEFAULT '[]',
    kljucne_tacke JSONB DEFAULT '[]',
    optimalna_strategija TEXT,
    hipoteza TEXT,
    tip TEXT DEFAULT 'simulacija',
    created_at TIMESTAMPTZ DEFAULT now()
  );
  CREATE INDEX idx_twin_predmet ON twin_simulacije(predmet_id, created_at DESC);
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.digital_twin")
router = APIRouter(prefix="/api/twin", tags=["digital_twin"])


# ── GPT-4o sistem prompt za simulaciju ───────────────────────────────────────

_TWIN_SYSTEM = """Ti si pravni strateg koji simulira razvoj sudskog predmeta.
Na osnovu dostavljenih informacija, kreiraj 3 detaljne simulacije razvoja.

Odgovori SAMO validnim JSON-om u sledecem formatu:
{
  "scenariji": [
    {
      "naziv": "Optimisticki",
      "verovatnoca": 30,
      "opis": "...",
      "kljucni_rizici": ["..."],
      "preporucene_akcije": ["..."],
      "procenjeno_trajanje_meseci": 6
    },
    {
      "naziv": "Realni",
      "verovatnoca": 50,
      "opis": "...",
      "kljucni_rizici": ["..."],
      "preporucene_akcije": ["..."],
      "procenjeno_trajanje_meseci": 12
    },
    {
      "naziv": "Pesimisticki",
      "verovatnoca": 20,
      "opis": "...",
      "kljucni_rizici": ["..."],
      "preporucene_akcije": ["..."],
      "procenjeno_trajanje_meseci": 24
    }
  ],
  "kljucne_tacke": ["Rok za odgovor na tuzbu je kritican..."],
  "optimalna_strategija": "..."
}

Ekavica. Budi konkretan i direktan."""

# ── GPT-4o sistem prompt za sta-ako analizu ──────────────────────────────────

_STA_AKO_SYSTEM = """Ti si pravni strateg koji analizira uticaj hipoteze na sudski predmet.
Na osnovu dostavljenih informacija, analiziraj sta bi se desilo u datom scenariju.

Odgovori SAMO validnim JSON-om u sledecem formatu:
{
  "uticaj": "Detaljan opis kako hipoteza menja tok predmeta...",
  "nova_verovatnoca_uspeha": 65,
  "preporucene_akcije": ["Prva konkretna akcija", "Druga konkretna akcija"]
}

Ekavica. Budi konkretan i direktan."""


# ── Pydantic modeli ───────────────────────────────────────────────────────────

class SimulacijaRequest(BaseModel):
    predmet_id: str
    strategija_promena: Optional[str] = None


class StaAkoRequest(BaseModel):
    predmet_id: str
    hipoteza: str


# ── Interni helperi ───────────────────────────────────────────────────────────

async def _dohvati_kontekst_predmeta(supa, predmet_id: str, uid: str) -> dict:
    """
    Paralelno dohvata predmet + rokove + dokumente + komentare iz Supabase.
    Baca 404 ako predmet ne postoji ili ne pripada korisniku.
    """
    predmet_r, rokovi_r, dokumenti_r, komentari_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti").select(
                "id,naziv,tip,status,rizik,opis,created_at"
            ).eq("id", predmet_id).eq("user_id", uid).execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rocista").select(
                "sud,datum,status"
            ).eq("predmet_id", predmet_id).order("datum").execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti").select(
                "naziv_fajla,created_at"
            ).eq("predmet_id", predmet_id).execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_komentari").select(
                "tekst,created_at"
            ).eq("predmet_id", predmet_id).order("created_at", desc=True).limit(10).execute()
        ),
        return_exceptions=True,
    )

    predmet_data = (predmet_r.data if not isinstance(predmet_r, Exception) else []) or []
    if not predmet_data:
        raise HTTPException(
            status_code=404,
            detail="Predmet nije pronadjen ili nije u vasem vlasnistvu.",
        )

    return {
        "predmet":    predmet_data[0],
        "rokovi":     (rokovi_r.data    if not isinstance(rokovi_r,    Exception) else []) or [],
        "dokumenti":  (dokumenti_r.data if not isinstance(dokumenti_r, Exception) else []) or [],
        "komentari":  (komentari_r.data if not isinstance(komentari_r, Exception) else []) or [],
    }


def _build_kontekst_tekst(ctx: dict, strategija_promena: Optional[str] = None) -> str:
    """Formatira kontekst predmeta u tekst za GPT."""
    predmet   = ctx["predmet"]
    rokovi    = ctx["rokovi"]
    dokumenti = ctx["dokumenti"]
    komentari = ctx["komentari"]

    tekst = (
        f"PREDMET: {predmet.get('naziv', 'Nepoznato')}\n"
        f"Tip: {predmet.get('tip', 'ostalo')}\n"
        f"Status: {predmet.get('status', 'aktivan')}\n"
        f"Rizik: {predmet.get('rizik', 'srednji')}\n"
        f"Opis: {(predmet.get('opis') or 'Nije unet opis.')[:1000]}\n"
    )

    tekst += f"\nROCISTA ({len(rokovi)}):\n"
    for r in rokovi[:15]:
        tekst += f"- {r.get('sud', '?')} — {r.get('datum', '?')} [{r.get('status', '?')}]\n"

    tekst += f"\nDOKUMENTI ({len(dokumenti)}):\n"
    for d in dokumenti[:15]:
        tekst += f"- {d.get('naziv_fajla', '?')}\n"

    if komentari:
        tekst += f"\nPOSLEDNJE BELESKE ({len(komentari)}):\n"
        for k in komentari[:5]:
            tekst += f"- {(k.get('tekst') or '')[:300]}\n"

    if strategija_promena:
        tekst += f"\nPREDLOZENA PROMENA STRATEGIJE:\n{strategija_promena[:500]}\n"

    return tekst


# ── Endpoint 1: Digital Twin simulacija ──────────────────────────────────────

@router.post("/simulacija")
@limiter.limit("5/minute")
async def kreiraj_simulaciju(
    req: SimulacijaRequest,
    request: Request,
    user: dict = Depends(PermissionService.require("digital_twin")),
):
    """
    Digital Twin — simulira 3 scenarija razvoja predmeta sa procentima verovatnoce,
    kljucnim tackama odlucivanja i optimalnom strategijom.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    ctx = await _dohvati_kontekst_predmeta(supa, req.predmet_id, uid)
    kontekst_tekst = _build_kontekst_tekst(ctx, req.strategija_promena)

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o",
                temperature=0.3,
                max_tokens=3000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _TWIN_SYSTEM},
                    {"role": "user",   "content": kontekst_tekst},
                ],
            )
        )
        rezultat = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError as je:
        logger.error("[TWIN] JSON parse greska pri simulaciji: %s", je)
        raise HTTPException(status_code=500, detail="Greska pri parsiranju AI odgovora.")
    except Exception:
        logger.exception("[TWIN] Greska pri kreiranju simulacije")
        raise HTTPException(status_code=500, detail="Greska pri generisanju simulacije. Pokusajte ponovo.")

    scenariji            = rezultat.get("scenariji", [])
    kljucne_tacke        = rezultat.get("kljucne_tacke", [])
    optimalna_strategija = rezultat.get("optimalna_strategija", "")

    # Sacuvaj u twin_simulacije
    try:
        await asyncio.to_thread(
            lambda: supa.table("twin_simulacije").insert({
                "predmet_id":           req.predmet_id,
                "user_id":              uid,
                "scenariji":            scenariji,
                "kljucne_tacke":        kljucne_tacke,
                "optimalna_strategija": optimalna_strategija,
                "tip":                  "simulacija",
            }).execute()
        )
    except Exception:
        logger.warning("[TWIN] Cuvanje simulacije u bazu nije uspelo — nastavlja se.")

    preostalo = await UsageService.consume(uid, email, "digital_twin", multiplier=3)

    return {
        "scenariji":            scenariji,
        "kljucne_tacke":        kljucne_tacke,
        "optimalna_strategija": optimalna_strategija,
        "credits_remaining":    preostalo,
    }


# ── Endpoint 2: Sta ako analiza ───────────────────────────────────────────────

@router.post("/sta-ako")
@limiter.limit("5/minute")
async def sta_ako_analiza(
    req: StaAkoRequest,
    request: Request,
    user: dict = Depends(PermissionService.require("digital_twin")),
):
    """
    'Sta ako' analiza — GPT-4o analizira uticaj hipoteze na predmet
    i racuna novu verovatnocu uspeha.
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if not req.hipoteza or len(req.hipoteza.strip()) < 5:
        raise HTTPException(status_code=422, detail="Hipoteza mora imati najmanje 5 karaktera.")

    ctx = await _dohvati_kontekst_predmeta(supa, req.predmet_id, uid)
    kontekst_tekst = _build_kontekst_tekst(ctx)
    user_msg = f"{kontekst_tekst}\n\nHIPOTEZA ZA ANALIZU: {req.hipoteza[:1000]}"

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o",
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _STA_AKO_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
            )
        )
        rezultat = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError as je:
        logger.error("[TWIN] JSON parse greska pri sta-ako: %s", je)
        raise HTTPException(status_code=500, detail="Greska pri parsiranju AI odgovora.")
    except Exception:
        logger.exception("[TWIN] Greska pri sta-ako analizi")
        raise HTTPException(status_code=500, detail="Greska pri analizi hipoteze. Pokusajte ponovo.")

    uticaj             = rezultat.get("uticaj", "")
    nova_verovatnoca   = rezultat.get("nova_verovatnoca_uspeha", 50)
    preporucene_akcije = rezultat.get("preporucene_akcije", [])

    # Sacuvaj u twin_simulacije
    try:
        await asyncio.to_thread(
            lambda: supa.table("twin_simulacije").insert({
                "predmet_id":           req.predmet_id,
                "user_id":              uid,
                "scenariji":            [],
                "kljucne_tacke":        [],
                "optimalna_strategija": uticaj,
                "hipoteza":             req.hipoteza,
                "tip":                  "sta_ako",
            }).execute()
        )
    except Exception:
        logger.warning("[TWIN] Cuvanje sta-ako analize u bazu nije uspelo — nastavlja se.")

    preostalo = await UsageService.consume(uid, email, "digital_twin")

    return {
        "uticaj":                  uticaj,
        "nova_verovatnoca_uspeha": nova_verovatnoca,
        "preporucene_akcije":      preporucene_akcije,
        "credits_remaining":       preostalo,
    }


# ── Endpoint 3: Dohvata poslednju simulaciju ──────────────────────────────────

@router.get("/{predmet_id}")
async def dohvati_simulaciju(
    predmet_id: str,
    user: dict = Depends(get_current_user),
):
    """Dohvata poslednju sacuvanu Digital Twin simulaciju za predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    # Validacija vlasnistva predmeta
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    r = await asyncio.to_thread(
        lambda: supa.table("twin_simulacije").select("*")
            .eq("predmet_id", predmet_id)
            .eq("user_id", uid)
            .eq("tip", "simulacija")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
    )

    if not r.data:
        raise HTTPException(
            status_code=404,
            detail="Nema sacuvane simulacije za ovaj predmet. Pokrenite POST /api/twin/simulacija.",
        )

    return r.data[0]
