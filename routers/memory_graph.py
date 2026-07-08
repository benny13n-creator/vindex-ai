# -*- coding: utf-8 -*-
"""
Vindex AI — routers/memory_graph.py

Memory Graph Engine — eksplicitne veze između entiteta.

Odgovara na pitanja poput:
  "Prikaži sve predmete u kojima je partner A koristio argument X
   pred sudijom Z i ostvario uspeh."

Čvorovi: partner | klijent | sudija | predmet | argument | strategija
Veze:    koristio_argument | pobedio_pred | izgubio_pred |
         preferira | odbija | radio_sa

Endpoints:
  POST /api/memory-graph/dodaj-vezu           — dodaj eksplicitnu vezu
  GET  /api/memory-graph/entitet/{type}/{id}  — sve veze entiteta
  GET  /api/memory-graph/upit                 — NL upit nad grafom
  GET  /api/memory-graph/preporuka/{predmet_id} — preporuka strategije iz grafa
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

logger = logging.getLogger("vindex.memory_graph")
router = APIRouter(prefix="/api/memory-graph", tags=["memory-graph"])

_VALID_TYPES    = {"partner", "klijent", "sudija", "predmet", "argument", "strategija"}
_VALID_RELACIJE = {"koristio_argument", "pobedio_pred", "izgubio_pred",
                   "preferira", "odbija", "radio_sa", "zastupao", "resio_nagodbo"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_firma_id(supa, uid: str) -> Optional[str]:
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("id")
                .eq("admin_uid", uid)
                .maybe_single()
                .execute()
        )
        if r.data:
            return r.data["id"]
        r2 = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("kancelarija_id")
                .eq("user_id", uid)
                .eq("status", "aktivan")
                .maybe_single()
                .execute()
        )
        return (r2.data or {}).get("kancelarija_id")
    except Exception:
        return None


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class VezaRequest(BaseModel):
    from_type:   str
    from_id:     str
    from_naziv:  Optional[str] = None
    to_type:     str
    to_id:       str
    to_naziv:    Optional[str] = None
    relacija:    str
    predmet_id:  Optional[str] = None
    ishod:       Optional[str] = None
    snaga:       float = Field(1.0, ge=0.0, le=1.0)
    kontekst:    Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/dodaj-vezu")
@limiter.limit("60/minute")
async def dodaj_vezu(
    request: Request,
    payload: VezaRequest,
    user: dict = Depends(get_current_user),
):
    """Dodaje eksplicitnu vezu između dva entiteta u grafu."""
    uid  = user["user_id"]
    supa = _get_supa()

    if payload.from_type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"from_type mora biti: {', '.join(_VALID_TYPES)}")
    if payload.to_type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"to_type mora biti: {', '.join(_VALID_TYPES)}")
    if payload.relacija not in _VALID_RELACIJE:
        raise HTTPException(status_code=400, detail=f"relacija mora biti: {', '.join(_VALID_RELACIJE)}")

    kancelarija_id = await _get_firma_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=403, detail="Niste član nijedne kancelarije.")

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("memory_graph_edges").insert({
                "kancelarija_id": kancelarija_id,
                "from_type":      payload.from_type,
                "from_id":        payload.from_id,
                "from_naziv":     payload.from_naziv,
                "to_type":        payload.to_type,
                "to_id":          payload.to_id,
                "to_naziv":       payload.to_naziv,
                "relacija":       payload.relacija,
                "predmet_id":     payload.predmet_id,
                "ishod":          payload.ishod,
                "snaga":          payload.snaga,
                "kontekst":       payload.kontekst,
            }).execute()
        )
        return {"ok": True, "veza": r.data[0] if r.data else {}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entitet/{entity_type}/{entity_id}")
@limiter.limit("30/minute")
async def entitet_veze(
    entity_type: str,
    entity_id:   str,
    request:     Request,
    user:        dict = Depends(get_current_user),
    dubina:      int  = 1,
):
    """
    Sve veze entiteta (partner/sudija/klijent/predmet/argument/strategija).
    dubina=1: direktne veze. dubina=2: veze veza (2 hop).
    """
    uid  = user["user_id"]
    supa = _get_supa()

    if entity_type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Nevalidan tip: {entity_type}")

    kancelarija_id = await _get_firma_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=403, detail="Niste član nijedne kancelarije.")

    try:
        # Direktne veze (from i to)
        from_r, to_r = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("memory_graph_edges")
                    .select("*")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("from_type", entity_type)
                    .eq("from_id", entity_id)
                    .order("snaga", desc=True)
                    .limit(50)
                    .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("memory_graph_edges")
                    .select("*")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("to_type", entity_type)
                    .eq("to_id", entity_id)
                    .order("snaga", desc=True)
                    .limit(50)
                    .execute()
            ),
        )

        odlazne = from_r.data or []
        dolazne = to_r.data or []

        # Grupiraj po tipu relacije
        by_rel: dict[str, list] = {}
        for e in odlazne:
            by_rel.setdefault(e["relacija"], []).append({**e, "_smer": "odlazna"})
        for e in dolazne:
            by_rel.setdefault(e["relacija"], []).append({**e, "_smer": "dolazna"})

        return {
            "entitet":    {"tip": entity_type, "id": entity_id},
            "ukupno_veza": len(odlazne) + len(dolazne),
            "odlaznih":   len(odlazne),
            "dolaznih":   len(dolazne),
            "by_relacija": by_rel,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upit")
@limiter.limit("10/minute")
async def graph_upit(
    request: Request,
    user:    dict = Depends(get_current_user),
    q:       str  = "",
):
    """
    Pretraživanje grafa na prirodnom jeziku.
    Primer: "partner Marković pred sudijom Petrovićem"
    AI identifikuje entitete, pretražuje graf i daje sintezni odgovor.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    if not q or len(q) < 5:
        raise HTTPException(status_code=400, detail="Upit mora biti duži od 5 znakova.")

    kancelarija_id = await _get_firma_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=403, detail="Niste član nijedne kancelarije.")

    try:
        # Dohvati sve ivice firme (max 200 za kontekst)
        r = await asyncio.to_thread(
            lambda: supa.table("memory_graph_edges")
                .select("from_type, from_naziv, relacija, to_type, to_naziv, ishod, snaga, kontekst")
                .eq("kancelarija_id", kancelarija_id)
                .order("snaga", desc=True)
                .limit(200)
                .execute()
        )
        ivice = r.data or []

        if not ivice:
            return {"odgovor": "Graf je prazan. Počnite da dodajete veze između entiteta.", "ivice_pronadjene": 0}

        # Formatiraj ivice kao tekst za AI
        graf_tekst = "\n".join(
            f"[{e.get('from_type')}:{e.get('from_naziv', '?')}] --{e.get('relacija')}--> "
            f"[{e.get('to_type')}:{e.get('to_naziv', '?')}]"
            + (f" (ishod: {e['ishod']})" if e.get("ishod") else "")
            + (f" | {e['kontekst']}" if e.get("kontekst") else "")
            for e in ivice
        )

        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=600,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si asistent koji analizira graf pravnih odnosa advokatske kancelarije. "
                        "Na osnovu grafa ivica (veza) odgovori na korisnikov upit. "
                        "Navedi konkretne veze koje su relevantne za upit. "
                        "Ako nema relevantnih podataka, reci to jasno. "
                        "Odgovor na srpskom (ekavica), max 300 reči."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Graf veza:\n{graf_tekst}\n\nUpit: {q}",
                },
            ],
        )

        return {
            "odgovor":           resp.choices[0].message.content.strip(),
            "ivice_pronadjene":  len(ivice),
            "napomena":          "Odgovor baziran na eksplicitnim vezama u grafu kancelarije.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preporuka/{predmet_id}")
@limiter.limit("10/minute")
async def graf_preporuka(
    predmet_id: str,
    request:    Request,
    user:       dict = Depends(get_current_user),
):
    """
    Na osnovu predmeta i grafa preporučuje strategiju.
    Ko je pobedio u sličnim predmetima? Pred kojim sudijom? S kojim argumentom?
    """
    uid  = user["user_id"]
    supa = _get_supa()

    kancelarija_id = await _get_firma_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=403, detail="Niste član nijedne kancelarije.")

    try:
        # Dohvati predmet
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, tip, status, opis")
                .eq("id", predmet_id)
                .maybe_single()
                .execute()
        )
        if not pred_r.data:
            raise HTTPException(status_code=404, detail="Predmet nije pronađen.")
        predmet = pred_r.data

        # Veze vezane za ovaj predmet
        pred_veze_r = await asyncio.to_thread(
            lambda: supa.table("memory_graph_edges")
                .select("*")
                .eq("kancelarija_id", kancelarija_id)
                .eq("predmet_id", predmet_id)
                .execute()
        )
        direktne_veze = pred_veze_r.data or []

        # Veze pobeda/poraza za isti tip predmeta (iz celokupnog grafa)
        pobede_r = await asyncio.to_thread(
            lambda: supa.table("memory_graph_edges")
                .select("from_type, from_naziv, to_type, to_naziv, relacija, ishod, snaga, kontekst")
                .eq("kancelarija_id", kancelarija_id)
                .in_("relacija", ["pobedio_pred", "izgubio_pred", "koristio_argument"])
                .order("snaga", desc=True)
                .limit(50)
                .execute()
        )
        istorija = pobede_r.data or []

        if not istorija and not direktne_veze:
            return {
                "preporuka": "Graf kancelarije je prazan. Počnite da beležite veze (argumenti, ishodi, sudije) da bi AI mogao da daje preporuke.",
                "predmet": predmet,
            }

        # AI sinteza
        istorija_tekst = "\n".join(
            f"- [{e.get('from_naziv', '?')}] {e.get('relacija')} [{e.get('to_naziv', '?')}]"
            + (f" → {e['ishod']}" if e.get("ishod") else "")
            + (f" | {e['kontekst']}" if e.get("kontekst") else "")
            for e in istorija[:30]
        )

        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=500,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si strateški savetnik advokatske kancelarije. "
                        "Na osnovu istorije predmeta iz grafa kancelarije preporuči strategiju za novi predmet. "
                        "Budi konkretan: koji argumenti su ranije funkcionisali, pred kojim sudijama, u sličnim predmetima. "
                        "Ekavica. Max 250 reči."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Predmet: {predmet.get('naziv', '?')} (tip: {predmet.get('tip', '?')})\n"
                        f"Opis: {(predmet.get('opis') or '')[:300]}\n\n"
                        f"Istorija grafa kancelarije:\n{istorija_tekst or 'Nema podataka.'}"
                    ),
                },
            ],
        )

        return {
            "predmet":         predmet,
            "preporuka":       resp.choices[0].message.content.strip(),
            "direktnih_veza":  len(direktne_veze),
            "istorija_uzoraka": len(istorija),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
