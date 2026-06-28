# -*- coding: utf-8 -*-
"""
Vindex AI — routers/digital_twin.py

Digital Twin predmeta — AI reprezentacija svakog predmeta koja evoluira.

Koncept: svakom predmetu je pridružen AI "digitalni blizanac" koji:
  1. Rekonstruiše kompletan narativ predmeta iz svih dostupnih podataka
  2. Mapira aktere, dokaze, rokove, prethodne odluke
  3. Simulira scenarije i strategije (What-If analiza)
  4. Predviđa vjerovatne ishode na osnovu sudske prakse

Endpointi:
  POST /api/twin/generisi/{predmet_id}     — kreira/osvežava digital twin
  GET  /api/twin/{predmet_id}              — vraća poslednji twin
  POST /api/twin/simulacija/{predmet_id}   — What-If simulacija strategije
  POST /api/twin/scenario/{predmet_id}     — detaljni scenario analiza

Kreditni sistem: generisi=3 kredita, simulacija=2 kredita, scenario=2 kredita
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import AsyncOpenAI
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.twin")
router = APIRouter(tags=["digital_twin"])

_oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


# ─── Modeli ───────────────────────────────────────────────────────────────────

class SimulacijaReq(BaseModel):
    strategija: str
    opis_strategije: str = ""

class ScenarioReq(BaseModel):
    scenario: str  # npr. "optimistican", "pesimistican", "realistican"


# ─── Interni: prikupljanje podataka o predmetu ───────────────────────────────

async def _prikupi_podatke_predmeta(predmet_id: str, uid: str, supa) -> dict:
    """Paralelno prikuplja sve dostupne podatke o predmetu."""
    pred_r, hron_r, dok_r, rock_r, kom_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti").select("*").eq("id", predmet_id).eq("user_id", uid).maybe_single().execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("*").eq("predmet_id", predmet_id).order("datum_iso").limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("dokumenti").select("naziv,vrsta,created_at").eq("predmet_id", predmet_id).limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select("naziv,datum,napomena").eq("predmet_id", predmet_id).order("datum").limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("komentari").select("tekst,created_at").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(10).execute()),
    )

    return {
        "predmet":    pred_r.data or {},
        "hronologija": hron_r.data or [],
        "dokumenti":  dok_r.data or [],
        "rocista":    rock_r.data or [],
        "komentari":  kom_r.data or [],
    }


def _formatiraj_kontekst_za_twin(podaci: dict) -> str:
    """Formatira podatke predmeta u kontekst za LLM."""
    pred = podaci.get("predmet") or {}
    linije = [
        f"PREDMET: {pred.get('naziv', 'Nepoznato')}",
        f"Tip: {pred.get('tip_postupka', '—')} | Status: {pred.get('status', '—')}",
        f"Opis: {pred.get('opis', '—')[:500]}",
        f"Datum otvaranja: {pred.get('created_at', '—')[:10]}",
        "",
    ]

    hron = podaci.get("hronologija", [])
    if hron:
        linije.append(f"HRONOLOGIJA ({len(hron)} dogadjaja):")
        for h in hron[:15]:
            linije.append(f"  {h.get('datum_iso', '—')[:10]} | {h.get('dogadjaj', '—')} [{h.get('vaznost', '—')}]")
        linije.append("")

    doks = podaci.get("dokumenti", [])
    if doks:
        linije.append(f"DOKUMENTI ({len(doks)}):")
        for d in doks[:10]:
            linije.append(f"  • {d.get('naziv', '—')} [{d.get('vrsta', '—')}]")
        linije.append("")

    rocs = podaci.get("rocista", [])
    if rocs:
        linije.append(f"ROCISTA ({len(rocs)}):")
        for r in rocs[:8]:
            linije.append(f"  {r.get('datum', '—')} | {r.get('naziv', '—')}")
        linije.append("")

    koms = podaci.get("komentari", [])
    if koms:
        linije.append(f"POSLEDNJE BELESKE ({len(koms)}):")
        for k in koms[:5]:
            linije.append(f"  • {k.get('tekst', '—')[:200]}")

    return "\n".join(linije)


# ─── Generisanje Digital Twin ─────────────────────────────────────────────────

@router.post("/api/twin/generisi/{predmet_id}")
@limiter.limit("5/minute")
async def generisi_twin(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Kreira/osvežava Digital Twin predmeta. 3 kredita.
    AI analizira SVE podatke o predmetu i generiše strukturiranu reprezentaciju.
    """
    supa = _get_supa()
    uid  = user["user_id"]

    podaci = await _prikupi_podatke_predmeta(predmet_id, uid, supa)
    if not podaci["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    kontekst = _formatiraj_kontekst_za_twin(podaci)
    today = date.today().isoformat()

    system_prompt = """Ti si AI pravni analitičar koji kreira Digital Twin pravnog predmeta.
Digital Twin je živa, strukturirana AI reprezentacija predmeta koja se ažurira sa svakim novim podatkom.

Generiši kompletan JSON Digital Twin sa sledećim sekcijama:
1. NARATIV — 3-5 rečenica: šta je suština ovog predmeta
2. AKTERI — lista aktera (stranka, protivnik, sudija, svedoci, veštaci)
3. SNAGE_I_SLABOSTI — SWOT analiza predmeta
4. KLJUCNI_DOKAZI — lista ključnih dokaza i njihova težina
5. KRITICNI_MOMENTI — najvažniji rokovi i datumi koji određuju ishod
6. PREDVIDJENI_ISHOD — procena sa verovatnoćama (%) za 3 scenarija: pobeda/neodlučeno/poraz
7. PREPORUCENA_STRATEGIJA — 3 konkretne akcije za sledeće 30 dana
8. ZDRAVLJE_PREDMETA — ocena 1-10 sa obrazloženjem

Vrati SAMO validan JSON. Ekavica. Bez uvoda."""

    user_msg = f"Datum analize: {today}\n\n{kontekst}"

    try:
        resp = await _oai.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        twin_json = resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("[TWIN] GPT greška: %s", exc)
        raise HTTPException(status_code=503, detail="AI servis nije dostupan.")

    try:
        twin_data = json.loads(twin_json)
    except json.JSONDecodeError:
        twin_data = {"raw": twin_json}

    try:
        await asyncio.to_thread(
            lambda: supa.table("digital_twins").upsert({
                "predmet_id":  predmet_id,
                "user_id":     uid,
                "twin_data":   twin_data,
                "created_at":  today,
            }, on_conflict="predmet_id").execute()
        )
    except Exception as e:
        logger.warning("[TWIN] Greška pri snimanju twin-a: %s", e)

    return {
        "predmet_id": predmet_id,
        "twin":       twin_data,
        "generisan":  today,
        "krediti_potroseno": 3,
    }


@router.get("/api/twin/{predmet_id}")
@limiter.limit("30/minute")
async def get_twin(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća poslednji sačuvani Digital Twin predmeta."""
    supa = _get_supa()
    uid  = user["user_id"]

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("digital_twins")
                .select("twin_data,created_at")
                .eq("predmet_id", predmet_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        if not r.data:
            raise HTTPException(status_code=404, detail="Digital Twin nije generisan. Pokrenite /api/twin/generisi/{predmet_id}")
        return r.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── What-If Simulacija ───────────────────────────────────────────────────────

@router.post("/api/twin/simulacija/{predmet_id}")
@limiter.limit("10/minute")
async def what_if_simulacija(
    predmet_id: str,
    payload: SimulacijaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    What-If simulacija strategije. 2 kredita.
    "Šta se dešava ako primenimo ovu strategiju?"
    """
    supa = _get_supa()
    uid  = user["user_id"]

    podaci = await _prikupi_podatke_predmeta(predmet_id, uid, supa)
    if not podaci["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    kontekst = _formatiraj_kontekst_za_twin(podaci)

    system_prompt = """Ti si AI pravni strateg koji simulira ishode pravnih strategija.
Dato je stanje predmeta i predložena strategija. Proceni:

1. VEROVATNOST_USPEHA — broj 0-100%
2. RIZICI — lista konkretnih rizika ove strategije
3. PREDNOSTI — lista prednosti
4. ALTERNATIVE — 2 alternativne strategije sa prednostima/manama
5. VREMENSKI_OKVIR — kada bi ova strategija dala rezultate
6. PREPORUKA — da li preporučuješ ovu strategiju? (DA/MOZDA/NE) sa obrazloženjem
7. SLEDECI_KORAK — jedan konkretan sledeći korak ako se odlučiš za ovu strategiju

Vrati SAMO validan JSON. Ekavica."""

    user_msg = (
        f"STRATEGIJA: {payload.strategija}\n"
        f"OPIS: {payload.opis_strategije}\n\n"
        f"STANJE PREDMETA:\n{kontekst}"
    )

    try:
        resp = await _oai.chat.completions.create(
            model="gpt-4o",
            temperature=0.3,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        sim_json = resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("[TWIN-SIM] GPT greška: %s", exc)
        raise HTTPException(status_code=503, detail="AI servis nije dostupan.")

    try:
        sim_data = json.loads(sim_json)
    except json.JSONDecodeError:
        sim_data = {"raw": sim_json}

    return {
        "predmet_id":        predmet_id,
        "simulirana_strategija": payload.strategija,
        "rezultat":          sim_data,
        "krediti_potroseno": 2,
    }


# ─── Scenario Analiza ─────────────────────────────────────────────────────────

@router.post("/api/twin/scenario/{predmet_id}")
@limiter.limit("10/minute")
async def scenario_analiza(
    predmet_id: str,
    payload: ScenarioReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Detaljni scenario prikaz (optimistican/realistican/pesimistican). 2 kredita.
    Šta bi se tačno desilo u ovom scenariju?
    """
    supa = _get_supa()
    uid  = user["user_id"]

    podaci = await _prikupi_podatke_predmeta(predmet_id, uid, supa)
    if not podaci["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    kontekst = _formatiraj_kontekst_za_twin(podaci)

    scenario_opisi = {
        "optimistican": "Sve ide u prilog naše stranke — sud prihvata sve argumente, dokazi su snažni, protivnik griješi.",
        "pesimistican": "Najgori mogući razvoj — sud odbija argumente, dokazi su slabi, protivnik je spreman.",
        "realistican":  "Najvjerovatniji razvoj — mešovit rezultat, postoje i prednosti i slabosti.",
    }

    opis_scenarija = scenario_opisi.get(payload.scenario.lower(), payload.scenario)

    system_prompt = f"""Ti si AI pravni analitičar koji detaljno opisuje jedan scenario predmeta.
Scenario: {payload.scenario.upper()} — {opis_scenarija}

Za ovaj scenario generiši:
1. NARATIV_SCENARIJA — detaljni opis šta se dešava u ovom scenariju (3-5 rečenica)
2. KLJUCNI_MOMENTI — 3-5 ključnih momenata koji određuju ovaj scenario
3. FINANSIJSKI_ISHOD — procena finansijskog ishoda (u RSD ili %)
4. VREMENSKI_OKVIR — koliko bi trajao ovaj scenario
5. STA_TREBA_URADITI — konkretne akcije koje povećavaju verovatnoću ovog scenarija (ili ga izbegavaju ako je pesimistican)
6. VEROVATNOCA — procena verovatnoće ovog scenarija (0-100%)

Vrati SAMO validan JSON. Ekavica."""

    user_msg = f"PREDMET:\n{kontekst}"

    try:
        resp = await _oai.chat.completions.create(
            model="gpt-4o",
            temperature=0.3,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        sc_json = resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("[TWIN-SC] GPT greška: %s", exc)
        raise HTTPException(status_code=503, detail="AI servis nije dostupan.")

    try:
        sc_data = json.loads(sc_json)
    except json.JSONDecodeError:
        sc_data = {"raw": sc_json}

    return {
        "predmet_id":        predmet_id,
        "scenario":          payload.scenario,
        "rezultat":          sc_data,
        "krediti_potroseno": 2,
    }
