# -*- coding: utf-8 -*-
"""
Law Firm Brain — cross-case learning.

Za dati predmet, pronalazi slične zatvorene predmete iz kancelarije
i vraća: uspešne argumente, korišćene presude, ishode, strategije.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

def get_supa(): return _get_supa()
require_user = get_current_user

logger = logging.getLogger("vindex.precedenti")
router = APIRouter(prefix="/api/precedenti", tags=["precedenti"])

_BRAIN_SYSTEM = """Ti si pravni analitičar koji analizira iskustvo advokatske kancelarije.

Dobijaš informacije o tekućem predmetu i sličnim zatvorenim predmetima iz iste kancelarije.
Na osnovu toga daj konkretne preporuke:

1. ISKUSTVO KANCELARIJE — šta je radilo, šta nije
2. PREPORUČENA STRATEGIJA — na osnovu prethodnih sličnih predmeta
3. KLJUČNE PRESUDE — koje su bile najvažnije u sličnim predmetima
4. UPOZORENJA — greške koje treba izbegavati (naučene lekcije)
5. PROCENA — na osnovu istorije kancelarije, koliko sličnih predmeta je dobijeno

Format: Jasan, konkretan tekst. Ne pričaj o tome šta radiš — odmah daj analizu.
Maksimum 500 reči. Srpski jezik."""


@router.get("/predmeti/{predmet_id}")
@limiter.limit("10/minute")
async def get_precedenti(request: Request, predmet_id: str, user=Depends(PermissionService.require("precedenti"))):
    """
    Law Firm Brain: pronalazi slične predmete iz kancelarije i vraća naučene lekcije.
    """
    supa = get_supa()
    uid = user["user_id"]

    # Provera vlasništva + dohvati predmet
    pr = supa.table("predmeti").select(
        "id,naziv,tip,status,oblast,opis"
    ).eq("id", predmet_id).eq("user_id", uid).execute()
    if not pr.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen.")

    predmet = pr.data[0]
    tip = predmet.get("tip") or ""
    oblast = predmet.get("oblast") or ""

    # Pronađi slične ZATVORENE predmete istog tipa/oblasti
    q = supa.table("predmeti").select(
        "id,naziv,tip,status,oblast,opis,created_at"
    ).eq("user_id", uid).neq("id", predmet_id).eq("status", "zatvoren")

    # Filter po tipu (isti tip spora)
    slicni = []
    if tip:
        r1 = supa.table("predmeti").select(
            "id,naziv,tip,status,oblast,opis"
        ).eq("user_id", uid).eq("tip", tip).neq("id", predmet_id).limit(10).execute()
        slicni.extend(r1.data or [])

    # Filter po oblasti ako nema dovoljno po tipu
    if len(slicni) < 3 and oblast:
        r2 = supa.table("predmeti").select(
            "id,naziv,tip,status,oblast,opis"
        ).eq("user_id", uid).eq("oblast", oblast).neq("id", predmet_id).limit(5).execute()
        seen_ids = {p["id"] for p in slicni}
        for p in (r2.data or []):
            if p["id"] not in seen_ids:
                slicni.append(p)

    # Dohvati istoriju pitanja/odgovora za slične predmete (uspešne argumente)
    slicni_ids = [p["id"] for p in slicni[:8]]
    istorija_data = []
    if slicni_ids:
        for sid in slicni_ids[:5]:
            ih = supa.table("predmet_istorija").select(
                "pitanje,odgovor"
            ).eq("predmet_id", sid).eq("user_id", uid).limit(3).execute()
            istorija_data.extend(ih.data or [])

    # Dohvati hronologiju za slične predmete
    hron_data = []
    if slicni_ids:
        for sid in slicni_ids[:3]:
            hh = supa.table("predmet_hronologija").select(
                "dogadjaj,akter,datum,vaznost"
            ).eq("predmet_id", sid).order("datum_iso").limit(5).execute()
            hron_data.extend(hh.data or [])

    if not slicni:
        return {
            "analiza": "Nema sličnih predmeta u kancelariji za analizu. Ovo je prvi predmet ovog tipa.",
            "slicni_predmeti": [],
            "ukupno_slicnih": 0,
            "tip": tip,
        }

    # Pripremi kontekst za GPT
    ctx_predmet = f"Naziv: {predmet.get('naziv', '')}\nTip: {tip}\nOpis: {(predmet.get('opis') or '')[:300]}"

    ctx_slicni = ""
    for i, p in enumerate(slicni[:6], 1):
        ctx_slicni += f"\n{i}. Predmet: {p.get('naziv','')} | Tip: {p.get('tip','')} | Status: {p.get('status','')}"
        opis = (p.get("opis") or "")[:150]
        if opis:
            ctx_slicni += f"\n   Opis: {opis}"

    ctx_istorija = ""
    if istorija_data:
        ctx_istorija = "\n\nArgumentacija iz sličnih predmeta:\n"
        for ih in istorija_data[:5]:
            ctx_istorija += f"- {(ih.get('pitanje') or '')[:100]}\n"

    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=700,
            messages=[
                {"role": "system", "content": _BRAIN_SYSTEM},
                {"role": "user", "content": (
                    f"TEKUĆI PREDMET:\n{ctx_predmet}\n\n"
                    f"SLIČNI PREDMETI IZ KANCELARIJE:{ctx_slicni}"
                    f"{ctx_istorija}"
                )},
            ],
        )
        analiza = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("[BRAIN] GPT greška: %s", exc)
        analiza = f"Pronađeno {len(slicni)} sličnih predmeta. AI analiza trenutno nedostupna."
    else:
        await UsageService.consume(user["user_id"], user.get("email", ""), "precedenti")

    return {
        "analiza":          analiza,
        "slicni_predmeti":  slicni[:8],
        "ukupno_slicnih":   len(slicni),
        "tip":              tip,
    }
