# -*- coding: utf-8 -*-
"""
Vindex AI — Style Consistency Checker (Faza 5)

Poredi stil pisanja advokata sa firmskim standardom.
Sprečava stilske devijacije, osigurava konzistentnost brenda firme.

Endpoints:
  POST /api/style/profil/gradi        — analizira uzorke i gradi stil profil
  GET  /api/style/profil              — preuzima aktuelni profil firme
  POST /api/style/analiziraj          — analizira dokument prema profilu
  GET  /api/style/analize             — istorija analiza
  GET  /api/style/analize/{id}        — detalji jedne analize
  DELETE /api/style/profil            — brise profil (reset)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.style_checker")
router = APIRouter(prefix="/api/style", tags=["style_checker"])

# ─── Prompts ──────────────────────────────────────────────────────────────────

_PROFIL_SYSTEM = """Ti si ekspert za pravni stil pisanja.

Analiziraj date uzorke pravnih dokumenata i izvuci karakteristike firmskog stila.

Vrati JSON sa tacno ovim kljucevima:
{
  "prosecna_duzina_recenice": <broj reci>,
  "gustina_pravnih_termina": <0.0-1.0, koliko pravnih termina na 100 reci>,
  "formalni_stil_procenat": <0-100, koliko je formalan jezik>,
  "pasiv_aktiv_odnos": "<npr. 70% pasiv / 30% aktiv>",
  "struktura_ocena": "<ocena strukture: numericke sekcije / slobodni tekst / mixed>",
  "citiranje_ocena": "<kako se citiraju zakoni i presude>",
  "karakteristicni_fraze": ["<fraza1>", "<fraza2>", "<fraza3>"],
  "snage_stila": ["<snaga1>", "<snaga2>"],
  "opis_stila": "<2-3 recenice opis prepoznatljivog stila firme>"
}

Samo JSON, bez komentara. Srpski jezik."""

_ANALIZA_SYSTEM = """Ti si ekspert za konzistentnost pravnog stila.

Dat ti je FIRMSKI STIL PROFIL i DOKUMENT koji treba proveriti.

Analiziraj dokument i vrati JSON sa tacno ovim kljucevima:
{
  "skor": <0-100, koliko dokument odgovara firmskom stilu>,
  "devijacije": [
    {"tip": "<tip devijacije>", "primer": "<konkretni primer iz dokumenta>", "preporuka": "<sta promeniti>"}
  ],
  "snage": ["<sta je dobro uradjeno>"],
  "predlozi": ["<konkretan predlog za poboljsanje>"],
  "rezime": "<2-3 recenice sumarni komentar>",
  "oblast_prava": "<oblast prava dokumenta>"
}

Skor 90+ = odlicno uskladjen. 70-89 = dobro, manje greske. 50-69 = potrebne korekcije. <50 = znacajne devijacije.

Samo JSON, bez komentara. Srpski jezik."""

# ─── Modeli ───────────────────────────────────────────────────────────────────

class GradiProfilRequest(BaseModel):
    uzorci: List[str] = Field(..., min_items=1, description="Lista tekstova dokumenata za analizu")
    naziv: Optional[str] = "Firminski profil"

class AnalizujRequest(BaseModel):
    tekst: str = Field(..., min_length=100, description="Tekst dokumenta za analizu")
    predmet_id: Optional[str] = None
    dokument_naziv: Optional[str] = None

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/profil/gradi")
async def gradi_stil_profil(body: GradiProfilRequest, user=Depends(get_current_user)):
    """Gradi firminski stil profil iz uzoraka dokumenata (min 1, preporučeno 5+)."""
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        uzorci_tekst = "\n\n---UZORAK---\n\n".join(body.uzorci[:10])

        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _PROFIL_SYSTEM},
                {"role": "user", "content": f"Analiziraj ove uzorke:\n\n{uzorci_tekst[:12000]}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        karakteristike = json.loads(resp.choices[0].message.content)
        supa = _get_supa()

        await asyncio.to_thread(
            lambda: supa.table("style_profili")
            .update({"aktivan": False})
            .eq("user_id", user["user_id"])
            .execute()
        )

        row = await asyncio.to_thread(
            lambda: supa.table("style_profili").insert({
                "user_id": user["user_id"],
                "naziv": body.naziv,
                "karakteristike": karakteristike,
                "uzoraka": len(body.uzorci),
                "aktivan": True,
            }).execute()
        )

        profil = row.data[0] if row.data else {}
        return {
            "profil_id": profil.get("id"),
            "naziv": body.naziv,
            "uzoraka": len(body.uzorci),
            "karakteristike": karakteristike,
            "poruka": f"Profil izgradjen iz {len(body.uzorci)} uzoraka. Sada mozete analizirati dokumente."
        }

    except Exception as e:
        logger.error("gradi_stil_profil: %s", e)
        raise HTTPException(500, str(e))


@router.get("/profil")
async def get_stil_profil(user=Depends(get_current_user)):
    """Preuzima aktuelni firminski stil profil."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("style_profili")
            .select("*")
            .eq("user_id", user["user_id"])
            .eq("aktivan", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not row.data:
            return {"profil": None, "poruka": "Nema aktivnog profila. Pokrenite POST /api/style/profil/gradi sa uzorcima."}
        return {"profil": row.data[0]}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/analiziraj")
async def analiziraj_stil(body: AnalizujRequest, user=Depends(get_current_user)):
    """Analizira dokument prema firmskom stilu. Vraca skor (0-100) i konkretne predloge."""
    supa = _get_supa()
    try:
        profil_row = await asyncio.to_thread(
            lambda: supa.table("style_profili")
            .select("id, karakteristike, naziv")
            .eq("user_id", user["user_id"])
            .eq("aktivan", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not profil_row.data:
            raise HTTPException(400, "Nema aktivnog firmskog profila. Prvo izgradite profil sa POST /api/style/profil/gradi")

        profil = profil_row.data[0]
        profile_id = profil["id"]
        karakteristike = profil["karakteristike"]

        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        user_msg = (
            f"FIRMSKI STIL PROFIL:\n{json.dumps(karakteristike, ensure_ascii=False, indent=2)}\n\n"
            f"DOKUMENT ZA ANALIZU:\n{body.tekst[:8000]}"
        )

        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _ANALIZA_SYSTEM},
                {"role": "user", "content": user_msg}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        rezultat = json.loads(resp.choices[0].message.content)
        skor = int(rezultat.get("skor", 50))
        skor = max(0, min(100, skor))

        row = await asyncio.to_thread(
            lambda: supa.table("style_analize").insert({
                "user_id": user["user_id"],
                "predmet_id": body.predmet_id,
                "dokument_naziv": body.dokument_naziv,
                "skor": skor,
                "rezultat": rezultat,
                "profile_id": profile_id,
            }).execute()
        )

        analiza_id = row.data[0]["id"] if row.data else None

        ocena = "Odlicno" if skor >= 90 else ("Dobro" if skor >= 70 else ("Potrebne korekcije" if skor >= 50 else "Znacajne devijacije"))

        return {
            "analiza_id": analiza_id,
            "skor": skor,
            "ocena": ocena,
            "devijacije": rezultat.get("devijacije", []),
            "snage": rezultat.get("snage", []),
            "predlozi": rezultat.get("predlozi", []),
            "rezime": rezultat.get("rezime", ""),
            "oblast_prava": rezultat.get("oblast_prava", ""),
            "firmski_profil": profil.get("naziv"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("analiziraj_stil: %s", e)
        raise HTTPException(500, str(e))


@router.get("/analize")
async def get_style_analize(limit: int = 20, predmet_id: Optional[str] = None, user=Depends(get_current_user)):
    """Istorija style analiza za korisnika."""
    supa = _get_supa()
    try:
        q = (
            supa.table("style_analize")
            .select("id, skor, dokument_naziv, predmet_id, created_at, rezultat->>'rezime' as rezime, rezultat->>'oblast_prava' as oblast_prava")
            .eq("user_id", user["user_id"])
            .order("created_at", desc=True)
            .limit(min(limit, 50))
        )
        if predmet_id:
            q = q.eq("predmet_id", predmet_id)
        row = await asyncio.to_thread(lambda: q.execute())
        return {"analize": row.data or [], "ukupno": len(row.data or [])}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/analize/{analiza_id}")
async def get_style_analiza(analiza_id: str, user=Depends(get_current_user)):
    """Detalji jedne style analize."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("style_analize")
            .select("*")
            .eq("id", analiza_id)
            .eq("user_id", user["user_id"])
            .maybe_single()
            .execute()
        )
        if not row.data:
            raise HTTPException(404, "Analiza nije pronadjena")
        return row.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.delete("/profil")
async def obrisi_stil_profil(user=Depends(get_current_user)):
    """Brise aktivni firminski profil (reset za izgradnju novog)."""
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("style_profili")
            .update({"aktivan": False})
            .eq("user_id", user["user_id"])
            .execute()
        )
        return {"poruka": "Profil deaktiviran. Mozete izgraditi novi sa POST /api/style/profil/gradi"}
    except Exception as e:
        raise HTTPException(500, str(e))


# ─── STYLE EVOLUTION ─────────────────────────────────────────────────────────

_EVOLUCIJA_SYSTEM = """Ti si ekspert za analizu evolucije pravnog stila pisanja.

Data ti je istorija stilskih profila firme od najstarijeg do najnovijeg.
Svaki profil je izgradjen u drugom vremenskom trenutku iz uzoraka dokumenata.

Na osnovu ovih profila:
1. Identifikuj konkretne promene u stilu (sta se promenilo, u kom smeru)
2. Identifikuj trendove (sta se konzistentno menja)
3. Proceni da li su promene pozitivne ili negativne za pravne dokumente

Vrati JSON:
{
  "trendovi": [
    {
      "karakteristika": "<sta se menjalo>",
      "smer": "<kratki opis smera promene>",
      "ocena": "<pozitivno | negativno | neutralno>",
      "detalj": "<konkretno objasnjenje>"
    }
  ],
  "kljucne_promene": ["<konkretna promena 1 sa datumom ako je poznato>"],
  "opsti_smer": "<opis opsteg pravca evolucije stila firme>",
  "preporuka": "<sta bi trebalo sacuvati, a sta mozda promeniti>"
}

Samo JSON. Srpski jezik. Budi konkretan, ne apstraktan."""


@router.get("/evolucija")
async def get_style_evolucija(user=Depends(get_current_user)):
    """Style Evolution: kako se stil firme menjao kroz vreme.

    Poredi sve istorijske profile i identifikuje trendove:
    kraci pasusi, manje citata, agilniji uvod, vise sudske prakse itd.
    """
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("style_profili")
            .select("id, naziv, karakteristike, uzoraka, created_at")
            .eq("user_id", user["user_id"])
            .order("created_at")
            .execute()
        )
        profili = row.data or []

        if len(profili) < 2:
            return {
                "evolucija": None,
                "profila_ukupno": len(profili),
                "poruka": (
                    "Potrebna su najmanje 2 profila za prikaz evolucije. "
                    "Izgradite novi profil posle nekoliko meseci da pratite trendove."
                ),
            }

        # Pripremi snapshot po profilu za prikaz
        snapshots = []
        for p in profili:
            k = p.get("karakteristike") or {}
            snapshots.append({
                "datum": p["created_at"][:10],
                "naziv": p.get("naziv"),
                "uzoraka": p.get("uzoraka", 0),
                "profil_id": p["id"],
                "metrike": {
                    "prosecna_duzina_recenice": k.get("prosecna_duzina_recenice"),
                    "gustina_pravnih_termina": k.get("gustina_pravnih_termina"),
                    "formalni_stil_procenat": k.get("formalni_stil_procenat"),
                    "pasiv_aktiv_odnos": k.get("pasiv_aktiv_odnos"),
                    "struktura_ocena": k.get("struktura_ocena"),
                },
            })

        # Numerička poređenja između prvog i poslednjeg profila
        prvi = profili[0].get("karakteristike") or {}
        poslednji = profili[-1].get("karakteristike") or {}

        numericke_promene = []
        for kljuc, label in [
            ("prosecna_duzina_recenice", "Prosecna duzina recenice (reci)"),
            ("gustina_pravnih_termina", "Gustina pravnih termina"),
            ("formalni_stil_procenat", "Formalni stil (%)"),
        ]:
            v_staro = prvi.get(kljuc)
            v_novo = poslednji.get(kljuc)
            if v_staro is not None and v_novo is not None:
                try:
                    delta = float(v_novo) - float(v_staro)
                    smer = "vise" if delta > 0 else "manje"
                    numericke_promene.append({
                        "karakteristika": label,
                        "od": v_staro,
                        "na": v_novo,
                        "delta": round(delta, 2),
                        "smer": smer,
                    })
                except (TypeError, ValueError):
                    pass

        # GPT-4o-mini za narativnu analizu
        profili_tekst = "\n\n".join(
            f"Profil {i+1} ({p['created_at'][:10]}, {p.get('uzoraka',0)} uzoraka):\n"
            + json.dumps(p.get("karakteristike") or {}, ensure_ascii=False, indent=2)
            for i, p in enumerate(profili)
        )

        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _EVOLUCIJA_SYSTEM},
                {"role": "user", "content": profili_tekst[:6000]}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        analiza = json.loads(resp.choices[0].message.content)

        return {
            "profila_ukupno": len(profili),
            "period": {
                "od": profili[0]["created_at"][:10],
                "do": profili[-1]["created_at"][:10],
            },
            "snapshots": snapshots,
            "numericke_promene": numericke_promene,
            "trendovi": analiza.get("trendovi", []),
            "kljucne_promene": analiza.get("kljucne_promene", []),
            "opsti_smer": analiza.get("opsti_smer"),
            "preporuka": analiza.get("preporuka"),
        }

    except Exception as e:
        logger.error("get_style_evolucija: %s", e)
        raise HTTPException(500, str(e))
