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
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService
from shared.case_context import build_case_context
from shared.case_readiness import CRITICAL_GAP, BLOCKED

logger = logging.getLogger("vindex.digital_twin")
router = APIRouter(prefix="/api/twin", tags=["digital_twin"])


@llm_retry
def _pozovi_twin_api(client, **kwargs):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return client.chat.completions.create(**kwargs)


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

Ako je ispod dat blok "STVARNO STANJE PREDMETA U SISTEMU": to je kanonski izvor, koristi ga kao osnovu.
Nijedan scenario ne sme tvrditi visoku verovatnocu uspeha (nad 50%) ako taj blok pokazuje kriticni
nedostatak (readiness: CRITICAL_GAP ili BLOCKED) -- takav predmet strukturno ne moze imati optimisticki
scenario sa visokom verovatnocom dok se nedostatak ne otkloni.

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

Ako je ispod dat blok "STVARNO STANJE PREDMETA U SISTEMU": to je kanonski izvor, koristi ga kao osnovu.
"nova_verovatnoca_uspeha" ne sme biti visoka (nad 50%) ako taj blok pokazuje kriticni nedostatak
(readiness: CRITICAL_GAP ili BLOCKED).

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
    Dohvata predmet + rokove + dokumente + komentare iz Supabase.
    Baca 404 ako predmet ne postoji ili ne pripada korisniku.

    Lambda Certification 003 (2026-08-06) -- Horizontal Privilege Escalation
    fork found (NEEDS-DEEPER-LOOK, not exploitable today, upheld by the
    Adversarial Certification fork's own independent re-trace) that the
    ownership-scoped `predmeti` query used to run INSIDE the same
    asyncio.gather() as the 3 sibling queries below -- meaning another
    tenant's full document names/hearing dates/comment text transited this
    process's memory for every guessed predmet_id BEFORE the 404 check ran,
    even though every caller already correctly discarded that data on a
    404. The ownership check now runs first, alone; the sibling queries
    only fire once ownership is confirmed -- same shape strategy_simulator.py
    already used correctly."""
    predmet_r = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,status,rizik,opis,created_at"
        ).eq("id", predmet_id).eq("user_id", uid).execute()
    )
    predmet_data = predmet_r.data or []
    if not predmet_data:
        raise HTTPException(
            status_code=404,
            detail="Predmet nije pronadjen ili nije u vasem vlasnistvu.",
        )

    rokovi_r, dokumenti_r, komentari_r = await asyncio.gather(
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

    return {
        "predmet":    predmet_data[0],
        "rokovi":     (rokovi_r.data    if not isinstance(rokovi_r,    Exception) else []) or [],
        "dokumenti":  (dokumenti_r.data if not isinstance(dokumenti_r, Exception) else []) or [],
        "komentari":  (komentari_r.data if not isinstance(komentari_r, Exception) else []) or [],
    }


# Program Lambda, Master Sprint 001 (AI Reasoning Auditor finding): GPT je do
# sada nezavisno izmišljao "verovatnoca"/"nova_verovatnoca_uspeha" isključivo
# iz sirovog konteksta iznad (predmeti/rokovi/dokumenti/komentari) -- nula
# poziva build_case_context()-u, ista forma već zatvorena za court_predictor.py
# (Tau 005) i hearing_cc.py (Tau 006), i eksplicitno predviđena za
# digital_twin.py u docs/tau/TAU_007_HANDOVER.md ali nikad primenjena. Ovaj
# sprint zatvara SAMO GPT granicu (deterministički cap), ne migrira ceo fajl
# na kanonski kontekst kao Tau 006 (to bi bio poseban, veći Factory sprint) --
# vidi docs/lambda/LAMBDA_ARCHITECTURE_AI_AUDIT.md za granicu obima. Isti
# pragovi kao court_predictor.py/hearing_cc.py -- platformska doslednost, ne
# novi izmišljeni brojevi.
_CAP_BY_READINESS = {CRITICAL_GAP: 50, BLOCKED: 65}


async def _dohvati_case_context_ako_postoji(predmet_id: str, uid: str, supa) -> Optional[dict]:
    """Fail-soft kanonski dohvat -- isti obrazac kao court_predictor.py/
    hearing_cc.py. Nikad ne baca, nikad ne blokira postojeće ponašanje."""
    if not predmet_id:
        return None
    try:
        return await build_case_context(predmet_id, uid, supa, include_documents=False)
    except Exception as exc:
        logger.warning("[TWIN] build_case_context greška (nastavlja bez kanonskog konteksta): %s", exc)
        return None


def _case_context_blok(cc: Optional[dict]) -> str:
    """Minimalan formatter -- samo readiness, dovoljno da grounduje GPT
    granicu ispod. Ne novi context builder: čita isključivo već izračunato
    build_case_context()-ovo polje."""
    if not cc or cc.get("error"):
        return ""
    readiness = (cc.get("readiness") or {}).get("value") or {}
    status = readiness.get("status")
    if not status:
        return ""
    return f"STVARNO STANJE PREDMETA U SISTEMU (kanonski izvor): readiness={status} — {readiness.get('razlog', '')}"


def _build_kontekst_tekst(ctx: dict, strategija_promena: Optional[str] = None, case_context_blok: str = "") -> str:
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

    if case_context_blok:
        tekst += f"\n{case_context_blok}\n"

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

    ctx, case_context = await asyncio.gather(
        _dohvati_kontekst_predmeta(supa, req.predmet_id, uid),
        _dohvati_case_context_ako_postoji(req.predmet_id, uid, supa),
    )
    case_context_blok = _case_context_blok(case_context)
    kontekst_tekst = _build_kontekst_tekst(ctx, req.strategija_promena, case_context_blok)

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        resp = await asyncio.to_thread(
            _pozovi_twin_api,
            oai,
            model="gpt-4o",
            temperature=0.3,
            max_tokens=3000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _TWIN_SYSTEM},
                {"role": "user",   "content": kontekst_tekst},
            ],
        )
        rezultat = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError as je:
        _sentry_capture(je)
        logger.error("[TWIN] JSON parse greska pri simulaciji: %s", je)
        raise HTTPException(status_code=500, detail="Greska pri parsiranju AI odgovora.")
    except Exception as _exc:
        _sentry_capture(_exc)
        logger.exception("[TWIN] Greska pri kreiranju simulacije")
        raise HTTPException(status_code=500, detail="Greska pri generisanju simulacije. Pokusajte ponovo.")

    scenariji            = rezultat.get("scenariji", [])
    kljucne_tacke        = rezultat.get("kljucne_tacke", [])
    optimalna_strategija = rezultat.get("optimalna_strategija", "")

    # Program Lambda, Master Sprint 001: deterministički cap -- GPT ne sme
    # tvrditi visoku verovatnocu ni za jedan scenario ako je kanonski status
    # CRITICAL_GAP/BLOCKED. Isti mehanizam kao court_predictor.py/hearing_cc.py,
    # primenjen na SVAKI scenario (ne samo jedno polje).
    if case_context and not case_context.get("error"):
        _status = ((case_context.get("readiness") or {}).get("value") or {}).get("status")
        _cap = _CAP_BY_READINESS.get(_status)
        if _cap is not None and isinstance(scenariji, list):
            for _sc in scenariji:
                if isinstance(_sc, dict):
                    _v = _sc.get("verovatnoca")
                    if isinstance(_v, (int, float)) and _v > _cap:
                        _sc["verovatnoca"] = _cap

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

    # multiplier čita se iz feature_registry.credit_multiplier (migracija 069,
    # Admin Console editabilno) — ne hardkoduje se ovde.
    preostalo = await UsageService.consume(uid, email, "digital_twin")

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

    ctx, case_context = await asyncio.gather(
        _dohvati_kontekst_predmeta(supa, req.predmet_id, uid),
        _dohvati_case_context_ako_postoji(req.predmet_id, uid, supa),
    )
    case_context_blok = _case_context_blok(case_context)
    kontekst_tekst = _build_kontekst_tekst(ctx, case_context_blok=case_context_blok)
    user_msg = f"{kontekst_tekst}\n\nHIPOTEZA ZA ANALIZU: {req.hipoteza[:1000]}"

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    try:
        resp = await asyncio.to_thread(
            _pozovi_twin_api,
            oai,
            model="gpt-4o",
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _STA_AKO_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
        )
        rezultat = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError as je:
        _sentry_capture(je)
        logger.error("[TWIN] JSON parse greska pri sta-ako: %s", je)
        raise HTTPException(status_code=500, detail="Greska pri parsiranju AI odgovora.")
    except Exception as _exc:
        _sentry_capture(_exc)
        logger.exception("[TWIN] Greska pri sta-ako analizi")
        raise HTTPException(status_code=500, detail="Greska pri analizi hipoteze. Pokusajte ponovo.")

    uticaj             = rezultat.get("uticaj", "")
    nova_verovatnoca   = rezultat.get("nova_verovatnoca_uspeha", 50)
    preporucene_akcije = rezultat.get("preporucene_akcije", [])

    # Program Lambda, Master Sprint 001: isti deterministički cap kao gore.
    if case_context and not case_context.get("error"):
        _status = ((case_context.get("readiness") or {}).get("value") or {}).get("status")
        _cap = _CAP_BY_READINESS.get(_status)
        if _cap is not None and isinstance(nova_verovatnoca, (int, float)) and nova_verovatnoca > _cap:
            nova_verovatnoca = _cap

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

    # sta_ako analiza je jeftinija varijanta iste feature_key (1x, ne 3x kao
    # kreiraj_simulaciju) — explicitan multiplier=1 override je namerno
    # HARDKODOVAN ovde: "1" znači "tačno bazna cena, bez množenja", to je
    # definiciono tačno (ne poslovna odluka koju bi trebalo Admin Console da
    # menja), za razliku od kreiraj_simulaciju's 3x koji sad dolazi iz Registry-ja.
    preostalo = await UsageService.consume(uid, email, "digital_twin", multiplier=1)

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
