# -*- coding: utf-8 -*-
"""
Vindex AI — routers/strategy_simulator.py

Strategy Simulator: "Igraonica" za strategiju.
Advokat unese predmet + planiranu strategiju, a AI simulira protivnikovu
reakciju, identifikuje rupe i predlaže kontra-poteze.
Svaka runda je jedan "potez" u strategijskoj igri.

Endpoints:
  POST /api/simulator/nova-partija          — nova simulacija za predmet (2 kredita)
  POST /api/simulator/sledeci-potez         — novi potez u partiji (1 kredit)
  GET  /api/simulator/{predmet_id}/partije  — lista simulacija za predmet
  GET  /api/simulator/partija/{partija_id}  — kompletna istorija partije

SQL migracija (primeniti u Supabase):
  CREATE TABLE IF NOT EXISTS simulator_partije (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id UUID NOT NULL,
    user_id UUID NOT NULL,
    istorija JSONB DEFAULT '[]',
    status TEXT DEFAULT 'aktivna',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
  );
  CREATE INDEX IF NOT EXISTS idx_sim_predmet
    ON simulator_partije(predmet_id, created_at DESC);
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import (
    _audit,
    _get_supa,
    get_current_user,
)
from shared.permissions import PermissionService
from shared.usage import UsageService
from shared.rate import limiter

logger = logging.getLogger("vindex.strategy_simulator")

router = APIRouter(prefix="/api/simulator", tags=["strategy-simulator"])

# ─── Sistem prompt ────────────────────────────────────────────────────────────

_SIMULATOR_SYSTEM = """Ti si AI koji igra dvostruku ulogu: PROTIVNICKI ADVOKAT i SAVETNIK.

Kao PROTIVNICKI ADVOKAT: identifikuj rupe i napadaj argumentima.
Kao SAVETNIK: pruzi konkretne kontra-poteze i upozorenja.

Format odgovora (SAMO JSON):
{
  "slabosti": ["..."],
  "protivnikovi_odgovori": [
    {"potez": "...", "verovatnoca": "visoka/srednja/niska", "kako_kontrirati": "..."}
  ],
  "kontra_strategija": "...",
  "zabrane": ["Nikada ne radite X jer..."],
  "rizik_score": 7
}

Ekavica. Budi ostar i konkretan — ovo je trening, ne uteba."""

# ─── Pydantic modeli ──────────────────────────────────────────────────────────


class NovaPartijaRequest(BaseModel):
    predmet_id: str = Field(..., description="UUID predmeta iz tabele predmeti")
    moja_strategija: str = Field(..., min_length=20, max_length=10000)


class SledeciPotezRequest(BaseModel):
    partija_id: str = Field(..., description="UUID partije iz tabele simulator_partije")
    novi_potez: str = Field(..., min_length=10, max_length=5000)


# ─── Interni helperi ──────────────────────────────────────────────────────────

def _pozovi_gpt(messages: list[dict]) -> dict:
    """Sinhroni GPT-4o poziv — koristiti u asyncio.to_thread."""
    from openai import OpenAI

    oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    resp = oai.chat.completions.create(
        model="gpt-4o",
        temperature=0.4,
        max_tokens=2000,
        response_format={"type": "json_object"},
        messages=messages,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[Simulator] JSON parse greška — vraćam sirovi tekst")
        return {"raw": raw, "greska_parsiranja": True}


def _dohvati_predmet(supa, predmet_id: str, user_id: str) -> dict:
    """Dohvata predmet iz Supabase i proverava vlasništvo."""
    res = (
        supa.table("predmeti")
        .select("id,naziv,tip,opis,status,stranke")
        .eq("id", predmet_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronaden ili nemate pristup.")
    return res.data[0]


def _kreiraj_partiju(supa, predmet_id: str, user_id: str, prvi_potez: dict) -> str:
    """Kreira novi red u simulator_partije i vraca UUID."""
    partija_id = str(uuid.uuid4())
    supa.table("simulator_partije").insert(
        {
            "id": partija_id,
            "predmet_id": predmet_id,
            "user_id": user_id,
            "istorija": json.dumps([prvi_potez]),
            "status": "aktivna",
        }
    ).execute()
    return partija_id


def _dodaj_potez(supa, partija_id: str, user_id: str, potez: dict) -> None:
    """Dohvata istoriju, dodaje novi potez i upisuje nazad."""
    res = (
        supa.table("simulator_partije")
        .select("istorija")
        .eq("id", partija_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Partija nije pronadena ili nemate pristup.")

    istorija_raw = res.data[0].get("istorija") or "[]"
    if isinstance(istorija_raw, str):
        try:
            istorija: list = json.loads(istorija_raw)
        except json.JSONDecodeError:
            istorija = []
    else:
        istorija = list(istorija_raw)

    istorija.append(potez)

    supa.table("simulator_partije").update(
        {
            "istorija": json.dumps(istorija, ensure_ascii=False),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", partija_id).eq("user_id", user_id).execute()


def _dohvati_partiju(supa, partija_id: str, user_id: str) -> dict:
    res = (
        supa.table("simulator_partije")
        .select("*")
        .eq("id", partija_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Partija nije pronadena ili nemate pristup.")
    row = res.data[0]
    if isinstance(row.get("istorija"), str):
        try:
            row["istorija"] = json.loads(row["istorija"])
        except json.JSONDecodeError:
            row["istorija"] = []
    return row


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/nova-partija")
@limiter.limit("10/minute")
async def nova_partija(
    req: NovaPartijaRequest,
    request: Request,
    user: dict = Depends(PermissionService.require("strategy_simulator")),
) -> dict[str, Any]:
    """
    Kreira novu simulaciju za predmet.
    GPT-4o igra ulogu protivnickog advokata i analizira strategiju.
    Kosta 2 kredita.
    """
    uid = user["user_id"]
    email = user.get("email", "")
    supa = _get_supa()

    # Dohvati predmet
    predmet = await asyncio.to_thread(_dohvati_predmet, supa, req.predmet_id, uid)
    asyncio.create_task(_audit(uid, "simulator_nova_partija", req.predmet_id[:16]))

    # Dohvati Case Genome — centralni model predmeta
    genome_ctx = ""
    try:
        _gr = await asyncio.to_thread(
            lambda: supa.table("predmeti")
            .select("case_dna")
            .eq("id", req.predmet_id)
            .eq("user_id", uid)
            .single()
            .execute()
        )
        _g = (_gr.data or {}).get("case_dna") or {}
        if _g and not _g.get("greska"):
            _gi = _g.get("pravna_teorija") or {}
            genome_ctx = (
                f"\nCASE GENOME — Zivi model predmeta (v{_g.get('verzija',1)}):\n"
                f"  Identitet: {_gi.get('pravni_identitet', 'N/A')}\n"
                f"  Osnov odgovornosti: {_gi.get('osnov_odgovornosti', 'N/A')}\n"
                f"  Snaga predmeta: {_g.get('snaga_predmeta_procent', '?')}%\n"
            )
            _nt = _g.get("najslabija_tacka") or {}
            if _nt.get("rizik"):
                genome_ctx += f"  NAJSLABIJA TACKA: {_nt['rizik']} [kriticnost {_nt.get('kriticnost', '')}%]\n"
            _sp = _g.get("strategija") or {}
            if _sp.get("primarni_cilj"):
                genome_ctx += f"  Primarni cilj: {_sp['primarni_cilj']}\n"
            if _sp.get("rezervni_plan"):
                genome_ctx += f"  Rezervni plan: {_sp['rezervni_plan']}\n"
            _kontr = _g.get("kontradikcije") or []
            if _kontr:
                genome_ctx += f"  Kontradikcije: {len(_kontr)} pronađeno\n"
            _ned = _g.get("nedostaje") or []
            if _ned:
                genome_ctx += "  Nedostajuci dokazi: " + ", ".join(
                    n.get("dokument", "") for n in _ned[:3]
                ) + "\n"
            _sf = _g.get("snaga_faktori") or []
            if _sf:
                genome_ctx += "  Faktori snage:\n"
                for f in _sf[:4]:
                    genome_ctx += f"    {f.get('uticaj','')} {f.get('faktor','')} — {f.get('opis','')[:80]}\n"
    except Exception:
        pass

    # Pripremi poruku za GPT
    user_msg = (
        f"PREDMET: {predmet.get('naziv', 'Nepoznato')}\n"
        f"Tip: {predmet.get('tip', 'ostalo')}\n"
        f"Opis: {(predmet.get('opis') or '')[:1000]}\n"
        f"Status: {predmet.get('status', '')}\n"
        + genome_ctx
        + f"\nMOJA STRATEGIJA:\n{req.moja_strategija}"
    )

    messages = [
        {"role": "system", "content": _SIMULATOR_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    try:
        analiza = await asyncio.to_thread(_pozovi_gpt, messages)
    except Exception:
        logger.exception("[Simulator] GPT poziv greška (nova-partija)")
        raise HTTPException(status_code=500, detail="Greška pri AI analizi. Pokusajte ponovo.")

    # Normalizacija — fallback ako JSON nije u ocekivanom formatu
    if analiza.get("greska_parsiranja"):
        analiza = {
            "slabosti": ["AI odgovor nije bio u ocekivanom formatu — pokusajte ponovo."],
            "protivnikovi_odgovori": [],
            "kontra_strategija": analiza.get("raw", ""),
            "zabrane": [],
            "rizik_score": 5,
        }

    prvi_potez = {
        "redni_broj": 1,
        "tip": "nova_partija",
        "moja_strategija": req.moja_strategija,
        "analiza": analiza,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        partija_id = await asyncio.to_thread(
            _kreiraj_partiju, supa, req.predmet_id, uid, prvi_potez
        )
    except Exception:
        logger.exception("[Simulator] Greška pri kreiranju partije")
        raise HTTPException(status_code=500, detail="Greška pri snimanju partije.")

    # multiplier čita se iz feature_registry.credit_multiplier (migracija 069,
    # Admin Console editabilno) — ne hardkoduje se ovde.
    preostalo = await UsageService.consume(uid, email, "strategy_simulator")

    return {
        "partija_id": partija_id,
        "analiza": {
            "slabosti": analiza.get("slabosti", []),
            "protivnikovi_odgovori": analiza.get("protivnikovi_odgovori", []),
            "kontra_strategija": analiza.get("kontra_strategija", ""),
            "zabrane": analiza.get("zabrane", []),
            "rizik_score": analiza.get("rizik_score", 5),
        },
        "credits_remaining": max(preostalo, 0),
    }


@router.post("/sledeci-potez")
@limiter.limit("10/minute")
async def sledeci_potez(
    req: SledeciPotezRequest,
    request: Request,
    user: dict = Depends(PermissionService.require("strategy_simulator")),
) -> dict[str, Any]:
    """
    Novi potez u postojecoj partiji.
    GPT-4o nastavlja simulaciju u kontekstu prethodnih poteza.
    Kosta 1 kredit.
    """
    uid = user["user_id"]
    email = user.get("email", "")
    supa = _get_supa()

    # Dohvati partiju i istoriju
    partija = await asyncio.to_thread(_dohvati_partiju, supa, req.partija_id, uid)
    istorija: list = partija.get("istorija") or []
    asyncio.create_task(_audit(uid, "simulator_sledeci_potez", req.partija_id[:16]))

    # Pripremi kontekst iz istorije (maks poslednjih 5 poteza)
    kontekst_potezi = istorija[-5:] if len(istorija) > 5 else istorija
    kontekst_txt = "\n\n".join(
        f"[POTEZ {p.get('redni_broj', i+1)}]\n"
        f"Moj potez: {p.get('moja_strategija', p.get('novi_potez', ''))}\n"
        f"Analiza: rizik_score={p.get('analiza', {}).get('rizik_score', '?')}, "
        f"kontra_strategija={p.get('analiza', {}).get('kontra_strategija', '')[:200]}"
        for i, p in enumerate(kontekst_potezi)
    )

    user_msg = (
        f"ISTORIJA PARTIJE (poslednjih {len(kontekst_potezi)} poteza):\n"
        f"{kontekst_txt}\n\n"
        f"MOJ NOVI POTEZ:\n{req.novi_potez}\n\n"
        "Analiziraj novi potez u kontekstu prethodnih, simuliraj protivnikovu reakciju "
        "i proceni rizik (rizik_score 1-10)."
    )

    messages = [
        {"role": "system", "content": _SIMULATOR_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    try:
        analiza = await asyncio.to_thread(_pozovi_gpt, messages)
    except Exception:
        logger.exception("[Simulator] GPT poziv greška (sledeci-potez)")
        raise HTTPException(status_code=500, detail="Greška pri AI analizi. Pokusajte ponovo.")

    if analiza.get("greska_parsiranja"):
        analiza = {
            "slabosti": [],
            "protivnikovi_odgovori": [],
            "kontra_strategija": analiza.get("raw", ""),
            "zabrane": [],
            "rizik_score": 5,
        }

    redni_broj = len(istorija) + 1
    novi_zapis = {
        "redni_broj": redni_broj,
        "tip": "potez",
        "novi_potez": req.novi_potez,
        "analiza": analiza,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await asyncio.to_thread(_dodaj_potez, supa, req.partija_id, uid, novi_zapis)
    except HTTPException:
        raise
    except Exception:
        logger.exception("[Simulator] Greška pri snimanju poteza")
        raise HTTPException(status_code=500, detail="Greška pri snimanju poteza.")

    # Oduzmi 1 kredit — eksplicitan multiplier=1 override, nova_partija je
    # jedina varijanta koja koristi feature_registry.credit_multiplier (2x).
    preostalo = await UsageService.consume(uid, email, "strategy_simulator", multiplier=1)

    # Izvuci relevantna polja za odgovor
    protivnikovi = analiza.get("protivnikovi_odgovori", [])
    protivnikova_reakcija = protivnikovi[0] if protivnikovi else {}

    return {
        "redni_broj": redni_broj,
        "analiza_poteza": {
            "slabosti": analiza.get("slabosti", []),
            "zabrane": analiza.get("zabrane", []),
        },
        "protivnikova_reakcija": protivnikova_reakcija,
        "preporuka": analiza.get("kontra_strategija", ""),
        "rizik_score": analiza.get("rizik_score", 5),
        "credits_remaining": max(preostalo, 0),
    }


@router.get("/{predmet_id}/partije")
async def lista_partija(
    predmet_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Lista svih simulacija za dati predmet."""
    uid = user["user_id"]
    supa = _get_supa()

    try:
        res = await asyncio.to_thread(
            lambda: supa.table("simulator_partije")
            .select("id,predmet_id,status,created_at,updated_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", uid)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
    except Exception:
        logger.exception("[Simulator] Greška pri dohvatanju partija")
        raise HTTPException(status_code=500, detail="Greška pri ucitavanju partija.")

    partije = res.data or []
    return {
        "predmet_id": predmet_id,
        "ukupno": len(partije),
        "partije": partije,
    }


@router.get("/partija/{partija_id}")
async def detalji_partije(
    partija_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Kompletna istorija jedne partije — svi potezi i analize."""
    uid = user["user_id"]
    supa = _get_supa()

    try:
        partija = await asyncio.to_thread(_dohvati_partiju, supa, partija_id, uid)
    except HTTPException:
        raise
    except Exception:
        logger.exception("[Simulator] Greška pri dohvatanju partije")
        raise HTTPException(status_code=500, detail="Greška pri ucitavanju partije.")

    istorija = partija.get("istorija") or []
    return {
        "partija_id": partija_id,
        "predmet_id": partija.get("predmet_id"),
        "status": partija.get("status", "aktivna"),
        "broj_poteza": len(istorija),
        "istorija": istorija,
        "created_at": partija.get("created_at"),
        "updated_at": partija.get("updated_at"),
    }
