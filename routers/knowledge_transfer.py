# -*- coding: utf-8 -*-
"""
Vindex AI — Knowledge Transfer System (Faza 5)

Kada senior partner odlazi, potvrdjeni obrasci rada ostaju u sistemu.
Na osnovu materijala unetih u profil, mladi advokati dobijaju preporuke
izvedene iz prethodnih predmeta — bez imitacije osobe.

Endpoints:
  POST /api/knowledge/profili                  — kreiraj profil partnera
  GET  /api/knowledge/profili                  — lista svih profila
  GET  /api/knowledge/profili/{id}             — detalji profila
  POST /api/knowledge/profili/{id}/dodaj-izvor — dodaj dokument/znanje partneru
  POST /api/knowledge/profili/{id}/upitaj      — postavi pitanje bazi znanja partnera
  GET  /api/knowledge/profili/{id}/upiti       — istorija upita prema profilu
  POST /api/knowledge/profili/{id}/ekstrakcija — auto-ekstrakcija znanja iz izvora
  PATCH /api/knowledge/profili/{id}            — azuriraj profil (deaktivacija, napomene)
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
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.knowledge_transfer")
router = APIRouter(prefix="/api/knowledge", tags=["knowledge_transfer"])

# ─── Prompts ──────────────────────────────────────────────────────────────────

_EKSTRAKCIJA_SYSTEM = """Ti si pravni analitičar koji ekstraktuje znanje iz dokumenata.

Na osnovu datih pravnih dokumenata i istorije predmeta jednog advokata, izvuci:

Vrati JSON sa tacno ovim kljucevima:
{
  "oblasti_prava": ["<oblast1>", "<oblast2>"],
  "top_argumenti": [
    {
      "argument": "<opis argumenta>",
      "uspesnost_procenat": <0-100>,
      "kontekst": "<kada i zasto radi>",
      "br_primena": <procena broja primena>
    }
  ],
  "taktike": [
    {
      "naziv": "<naziv taktike>",
      "opis": "<detaljan opis>",
      "kada_primeniti": "<situacija>",
      "primer_predmeta": "<tip predmeta>"
    }
  ],
  "stil_komunikacije": "<opis komunikacionog stila sa klijentima i sudom>",
  "kljucne_snage": ["<snaga1>", "<snaga2>"],
  "ukupno_predmeta": <broj>,
  "win_rate": <0.0-100.0>
}

Samo JSON. Srpski jezik. Budi konkretan i upotrebljiv za mlade advokate."""

_UPIT_SYSTEM = """Ti si pravni analitičar koji primenjuje potvrdjene obrasce rada iz evidencije predmeta.

Dat ti je profil potvrdjenih obrazaca rada advokata (oblasti, argumenti iz predmeta, taktike, beleske).
Postavljena ti je konkretna pravna situacija.

VAZNO: Ne simuliras osobu. Ne pricas u ime advokata.
Pruzas preporuku IZVEDENU iz potvrdjenih obrazaca koji su dokumentovani u profilu.

Format odgovora:
PREPORUKA NA OSNOVU OBRAZACA: [sta potvrdjeni obrasci iz profila ukazuju za ovu situaciju]
TIPICNI ARGUMENT IZ PROFILA: [koji argument je u slicnim predmetima bio primenjen i sa kojim uspehom]
PRIMENLJIVA TAKTIKA: [koja taktika iz profila je relevantna]
NA STA PAZITI: [sta obrasci ukazuju kao rizik]
SAVET ZA PRIMENU: [konkretan sledeci korak]

NAPOMENA ZA KORISNIKA: Ova preporuka je izvedena iz materijala unetih u profil i potvrdjenih obrazaca rada iz prethodnih predmeta. Nije zamena za profesionalnu procenu.

Srpski jezik. 2-3 recenice po sekciji."""

# ─── Modeli ───────────────────────────────────────────────────────────────────

class KreirajProfilRequest(BaseModel):
    advokat_ime: str = Field(..., min_length=2)
    advokat_email: Optional[str] = None
    oblasti_prava: Optional[List[str]] = []
    stil_komunikacije: Optional[str] = None
    napomene: Optional[str] = None
    ukupno_predmeta: Optional[int] = 0
    win_rate: Optional[float] = 0.0

class DodajIzvorRequest(BaseModel):
    sadrzaj: str = Field(..., min_length=50)
    tip: str = Field(..., description="predmet_opis | podnesak | strategija | beleska | manuelni_unos")
    oblast_prava: Optional[str] = None
    ishod: Optional[str] = None

class UpitRequest(BaseModel):
    upit: str = Field(..., min_length=10)
    kontekst: Optional[str] = None

class UpdateProfilRequest(BaseModel):
    aktivan: Optional[bool] = None
    napomene: Optional[str] = None
    stil_komunikacije: Optional[str] = None

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/profili", status_code=201)
@limiter.limit("20/minute")
async def kreiraj_profil(request: Request, body: KreirajProfilRequest, user=Depends(get_current_user)):
    """Kreira profil znanja za partnera/seniora."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("knowledge_profiles").insert({
                "user_id": user["user_id"],
                "advokat_ime": body.advokat_ime,
                "advokat_email": body.advokat_email,
                "oblasti_prava": body.oblasti_prava or [],
                "stil_komunikacije": body.stil_komunikacije,
                "napomene": body.napomene,
                "ukupno_predmeta": body.ukupno_predmeta or 0,
                "win_rate": body.win_rate or 0.0,
                "top_argumenti": [],
                "taktike": [],
                "aktivan": True,
            }).execute()
        )
        profil = row.data[0] if row.data else {}
        return {
            "profil_id": profil.get("id"),
            "advokat_ime": body.advokat_ime,
            "poruka": f"Profil za {body.advokat_ime} kreiran. Dodajte izvore znanja sa POST /api/knowledge/profili/{{id}}/dodaj-izvor, zatim pokrenite ekstrakciju."
        }
    except Exception as e:
        logger.error("kreiraj_profil: %s", e)
        raise HTTPException(500, str(e))


@router.get("/profili")
@limiter.limit("30/minute")
async def lista_profila(request: Request, user=Depends(get_current_user)):
    """Lista svih profila znanja u firmi."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("knowledge_profiles")
            .select("id, advokat_ime, advokat_email, oblasti_prava, ukupno_predmeta, win_rate, aktivan, created_at")
            .eq("user_id", user["user_id"])
            .order("advokat_ime")
            .execute()
        )
        profili = row.data or []
        return {
            "profili": profili,
            "ukupno": len(profili),
            "aktivnih": sum(1 for p in profili if p.get("aktivan")),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/profili/{profil_id}")
@limiter.limit("30/minute")
async def get_profil(request: Request, profil_id: str, user=Depends(get_current_user)):
    """Detalji profila sa brojem izvora i upita."""
    supa = _get_supa()
    try:
        profil_row, izvori_count, upiti_count = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("knowledge_profiles")
                .select("*")
                .eq("id", profil_id)
                .eq("user_id", user["user_id"])
                .maybe_single()
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("knowledge_izvori")
                .select("id", count="exact")
                .eq("profile_id", profil_id)
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("knowledge_upiti")
                .select("id", count="exact")
                .eq("profile_id", profil_id)
                .execute()
            ),
        )
        if not profil_row.data:
            raise HTTPException(404, "Profil nije pronadjen")

        profil = profil_row.data
        profil["br_izvora"] = izvori_count.count or 0
        profil["br_upita"] = upiti_count.count or 0
        return profil
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/profili/{profil_id}/dodaj-izvor", status_code=201)
@limiter.limit("20/minute")
async def dodaj_izvor(request: Request, profil_id: str, body: DodajIzvorRequest, user=Depends(get_current_user)):
    """Dodaje dokument/tekst kao izvor znanja partnera."""
    validni_tipovi = {"predmet_opis", "podnesak", "strategija", "beleska", "manuelni_unos"}
    if body.tip not in validni_tipovi:
        raise HTTPException(400, f"tip mora biti jedan od: {', '.join(validni_tipovi)}")

    supa = _get_supa()
    try:
        profil_row = await asyncio.to_thread(
            lambda: supa.table("knowledge_profiles")
            .select("id, advokat_ime")
            .eq("id", profil_id)
            .eq("user_id", user["user_id"])
            .maybe_single()
            .execute()
        )
        if not profil_row.data:
            raise HTTPException(404, "Profil nije pronadjen")

        row = await asyncio.to_thread(
            lambda: supa.table("knowledge_izvori").insert({
                "profile_id": profil_id,
                "user_id": user["user_id"],
                "tip": body.tip,
                "sadrzaj": body.sadrzaj,
                "oblast_prava": body.oblast_prava,
                "ishod": body.ishod,
            }).execute()
        )
        izvor = row.data[0] if row.data else {}
        return {
            "izvor_id": izvor.get("id"),
            "poruka": f"Izvor dodat za profil {profil_row.data['advokat_ime']}. Pokrenite ekstrakciju da azurirate profil."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/profili/{profil_id}/ekstrakcija")
@limiter.limit("10/minute")
async def pokreni_ekstrakciju(request: Request, profil_id: str, user=Depends(PermissionService.require("knowledge_transfer"))):
    """Auto-ekstrakcija znanja iz svih izvora — azurira top_argumenti i taktike profila."""
    supa = _get_supa()
    try:
        profil_row, izvori_row = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("knowledge_profiles")
                .select("*")
                .eq("id", profil_id)
                .eq("user_id", user["user_id"])
                .maybe_single()
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("knowledge_izvori")
                .select("sadrzaj, tip, oblast_prava, ishod")
                .eq("profile_id", profil_id)
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            ),
        )
        if not profil_row.data:
            raise HTTPException(404, "Profil nije pronadjen")
        if not izvori_row.data:
            raise HTTPException(400, "Nema izvora. Dodajte izvore znanja pre ekstrakcije.")

        profil = profil_row.data
        izvori = izvori_row.data

        kombinovani = "\n\n---IZVOR---\n\n".join(
            f"Tip: {i['tip']} | Oblast: {i.get('oblast_prava', 'N/A')} | Ishod: {i.get('ishod', 'N/A')}\n{i['sadrzaj']}"
            for i in izvori
        )

        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _EKSTRAKCIJA_SYSTEM},
                {"role": "user", "content": f"Advokat: {profil['advokat_ime']}\n\nIzvori:\n{kombinovani[:10000]}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        ekstrahovano = json.loads(resp.choices[0].message.content)

        await asyncio.to_thread(
            lambda: supa.table("knowledge_profiles").update({
                "oblasti_prava": ekstrahovano.get("oblasti_prava", profil.get("oblasti_prava", [])),
                "top_argumenti": ekstrahovano.get("top_argumenti", []),
                "taktike": ekstrahovano.get("taktike", []),
                "stil_komunikacije": ekstrahovano.get("stil_komunikacije", profil.get("stil_komunikacije")),
                "ukupno_predmeta": ekstrahovano.get("ukupno_predmeta", profil.get("ukupno_predmeta", 0)),
                "win_rate": ekstrahovano.get("win_rate", profil.get("win_rate", 0)),
                "updated_at": "now()",
            }).eq("id", profil_id).execute()
        )

        await UsageService.consume(user["user_id"], user.get("email", ""), "knowledge_transfer")

        return {
            "profil_id": profil_id,
            "advokat_ime": profil["advokat_ime"],
            "ekstrahovano": {
                "oblasti_prava": ekstrahovano.get("oblasti_prava", []),
                "br_argumenata": len(ekstrahovano.get("top_argumenti", [])),
                "br_taktika": len(ekstrahovano.get("taktike", [])),
                "win_rate": ekstrahovano.get("win_rate", 0),
                "kljucne_snage": ekstrahovano.get("kljucne_snage", []),
            },
            "poruka": f"Znanje {profil['advokat_ime']} uspesno ekstrahovano iz {len(izvori)} izvora."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pokreni_ekstrakciju: %s", e)
        raise HTTPException(500, str(e))


@router.post("/profili/{profil_id}/upitaj")
@limiter.limit("10/minute")
async def upitaj_znanje(request: Request, profil_id: str, body: UpitRequest, user=Depends(PermissionService.require("knowledge_transfer"))):
    """Upituje bazu znanja partnera. 'Kako bi [partner] pristupio ovom slucaju?'"""
    supa = _get_supa()
    try:
        profil_row = await asyncio.to_thread(
            lambda: supa.table("knowledge_profiles")
            .select("*")
            .eq("id", profil_id)
            .eq("user_id", user["user_id"])
            .maybe_single()
            .execute()
        )
        if not profil_row.data:
            raise HTTPException(404, "Profil nije pronadjen")

        profil = profil_row.data

        if not profil.get("top_argumenti") and not profil.get("taktike"):
            raise HTTPException(400, "Profil nema ekstrahovano znanje. Pokrenite POST /ekstrakcija prvo.")

        profil_tekst = (
            f"Advokat: {profil['advokat_ime']}\n"
            f"Oblast: {', '.join(profil.get('oblasti_prava', []))}\n"
            f"Win rate: {profil.get('win_rate', 0)}%\n"
            f"Stil komunikacije: {profil.get('stil_komunikacije', 'N/A')}\n\n"
            f"Top argumenti:\n{json.dumps(profil.get('top_argumenti', []), ensure_ascii=False)}\n\n"
            f"Taktike:\n{json.dumps(profil.get('taktike', []), ensure_ascii=False)}"
        )

        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        user_msg = f"PROFIL POTVRDJENIH OBRAZACA:\n{profil_tekst}\n\nPRAVNA SITUACIJA:\n{body.upit}"
        if body.kontekst:
            user_msg += f"\n\nKONTEKST PREDMETA:\n{body.kontekst}"

        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _UPIT_SYSTEM},
                {"role": "user", "content": user_msg[:8000]}
            ],
            temperature=0.3,
        )

        odgovor = resp.choices[0].message.content

        await asyncio.to_thread(
            lambda: supa.table("knowledge_upiti").insert({
                "user_id": user["user_id"],
                "profile_id": profil_id,
                "upit": body.upit,
                "odgovor": odgovor,
                "kontekst": {"predmet_kontekst": body.kontekst} if body.kontekst else {},
            }).execute()
        )

        await UsageService.consume(user["user_id"], user.get("email", ""), "knowledge_transfer")

        return {
            "profil_ime": profil["advokat_ime"],
            "situacija": body.upit,
            "preporuka_na_osnovu_obrazaca": odgovor,
            "osnova": (
                f"Preporuka izvedena iz {len(profil.get('top_argumenti', []))} potvrdjenih argumenata "
                f"i {len(profil.get('taktike', []))} dokumentovanih taktika iz profila."
            ),
            "disclaimer": "Ova preporuka je zasnovana isklјucivo na materijalima unetim u profil. Nije zamena za profesionalnu pravnu procenu.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("upitaj_znanje: %s", e)
        raise HTTPException(500, str(e))


@router.get("/profili/{profil_id}/upiti")
@limiter.limit("30/minute")
async def get_istorija_upita(request: Request, profil_id: str, limit: int = 20, user=Depends(get_current_user)):
    """Istorija upita prema bazi znanja partnera."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("knowledge_upiti")
            .select("id, upit, odgovor, created_at")
            .eq("profile_id", profil_id)
            .eq("user_id", user["user_id"])
            .order("created_at", desc=True)
            .limit(min(limit, 50))
            .execute()
        )
        return {"upiti": row.data or [], "ukupno": len(row.data or [])}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.patch("/profili/{profil_id}")
@limiter.limit("20/minute")
async def update_profil(request: Request, profil_id: str, body: UpdateProfilRequest, user=Depends(get_current_user)):
    """Azurira profil — deaktivacija, napomene, stil."""
    supa = _get_supa()
    try:
        update_data = {k: v for k, v in body.dict().items() if v is not None}
        if not update_data:
            raise HTTPException(400, "Nema podataka za azuriranje")
        update_data["updated_at"] = "now()"

        row = await asyncio.to_thread(
            lambda: supa.table("knowledge_profiles")
            .update(update_data)
            .eq("id", profil_id)
            .eq("user_id", user["user_id"])
            .execute()
        )
        if not row.data:
            raise HTTPException(404, "Profil nije pronadjen")
        return {"poruka": "Profil azuriran", "profil": row.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
