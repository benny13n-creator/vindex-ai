# -*- coding: utf-8 -*-
"""
Vindex AI — Client Communication Profile (Faza 4/5)

Konkretne, proverljive komunikacione preferencije klijenta.
Ne profilisanje osobe — samo sta klijent konkretno trazi u komunikaciji.

Primeri:
  - preferira kratke izveštaje
  - uvek traži procenu troškova
  - želi da bude uključen u svaku odluku
  - preferira email, ne telefon

Endpoints:
  POST /api/client-twin/{klijent_id}/analiziraj   — gradi profil iz istorije komunikacije
  GET  /api/client-twin/{klijent_id}              — preuzima komunikacioni profil
  PATCH /api/client-twin/{klijent_id}             — rucno azurira preferencije
  GET  /api/client-twin/dashboard                 — svi klijenti, sortirani po datumu azuriranja
  GET  /api/client-twin/{klijent_id}/savet        — preporuke za sledeci kontakt
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

logger = logging.getLogger("vindex.client_twin")
router = APIRouter(prefix="/api/client-twin", tags=["client_twin"])

# ─── Prompt ───────────────────────────────────────────────────────────────────

_KOMUNIKACIJA_SYSTEM = """Ti si asistent koji analizira konkretne komunikacione preferencije klijenta.

Na osnovu date istorije predmeta i beleska, izvuci ISKLJUCIVO konkretne, proverljive
komunikacione preferencije — onako kako su se manifestovale u stvarnoj komunikaciji.

NE procenjuj psihologiju, licnost, rizike ili verovatnoce odluka.
NE koristis subjektivne ocene poput "tezeran klijent" ili "nije zadovoljan".
SAMO: sta klijent konkretno trazi, preferira i ocekuje u komunikaciji.

Vrati JSON sa tacno ovim kljucevima:
{
  "tip_izvestaja": "<kratak | detaljan | vizualni | nije_poznato>",
  "ucestalost_kontakta": "<dnevno | nedeljno | po_dogadjaju | mesecno | nije_poznato>",
  "ukljucenost_u_odluke": "<uvek | samo_kljucne | delegira | nije_poznato>",
  "prioriteti_pri_izvestavanju": ["<troskovi | rokovi | ishod | sledeci_koraci | transparentnost | ...>"],
  "preferirani_kanal": "<email | telefon | aplikacija | licem_u_lice | nije_poznato>",
  "uvek_trazi_procenu_troskova": <true | false | null>,
  "uvek_trazi_rokove": <true | false | null>,
  "pita_za_alternative": <true | false | null>,
  "ocekuje_brze_odgovore": <true | false | null>,
  "konkretne_napomene": ["<konkretna primetba iz komunikacije, ne procena>"],
  "izvor": "<N komunikacija / predmeta analiziranih>",
  "pouzdanost": "<visoka | srednja | niska>",
  "disclaimer": "Ove preferencije su izvedene iz analiziranih materijala. Uvek proverite direktno sa klijentom."
}

Pouzdanost = visoka ako postoji 5+ predmeta/beleska, srednja ako 2-4, niska ako 0-1.
Samo JSON. Srpski jezik. Budi konkretan i proverljiv."""

# ─── Modeli ───────────────────────────────────────────────────────────────────

class RucnoAzuriranjeRequest(BaseModel):
    tip_izvestaja: Optional[str] = None
    ucestalost_kontakta: Optional[str] = None
    ukljucenost_u_odluke: Optional[str] = None
    prioriteti_pri_izvestavanju: Optional[List[str]] = None
    preferirani_kanal: Optional[str] = None
    uvek_trazi_procenu_troskova: Optional[bool] = None
    uvek_trazi_rokove: Optional[bool] = None
    pita_za_alternative: Optional[bool] = None
    ocekuje_brze_odgovore: Optional[bool] = None
    konkretne_napomene: Optional[List[str]] = None

# ─── Helper ───────────────────────────────────────────────────────────────────

async def _get_klijent_materijali(supa, klijent_id: str, user_id: str) -> dict:
    try:
        klijent_row, predmeti_row, komentari_row = await asyncio.gather(  # noqa: E501
            asyncio.to_thread(
                lambda: supa.table("klijenti")
                .select("ime, prezime, tip_lica, napomene")
                .eq("id", klijent_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("predmeti")
                .select("naziv, tip, status, vrednost_spora, ishod")
                .eq("klijent_id", klijent_id)
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("predmet_komentari")
                .select("tekst, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(20)
                .execute()
            ),
            return_exceptions=True,
        )
        def _d(r):
            if isinstance(r, Exception):
                return []
            return getattr(r, "data", None) or []
        def _d1(r):
            if isinstance(r, Exception):
                return {}
            return getattr(r, "data", None) or {}
        return {
            "klijent": _d1(klijent_row),
            "predmeti": _d(predmeti_row),
            "beleske": _d(komentari_row),
        }
    except Exception as e:
        logger.warning("_get_klijent_materijali: %s", e)
        return {"klijent": {}, "predmeti": [], "beleske": []}

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{klijent_id}/analiziraj")
async def analiziraj_komunikacioni_profil(klijent_id: str, user=Depends(get_current_user)):
    """Gradi komunikacioni profil klijenta iz istorije predmeta i beleska."""
    supa = _get_supa()
    try:
        materijali = await _get_klijent_materijali(supa, klijent_id, user["user_id"])

        if not materijali["klijent"]:
            raise HTTPException(404, "Klijent nije pronadjen")

        klijent = materijali["klijent"]
        predmeti = materijali["predmeti"]
        beleske = materijali["beleske"]

        if not predmeti and not beleske:
            raise HTTPException(400, "Nema materijala za analizu. Potreban je bar 1 predmet ili beleska.")

        materijal_tekst = (
            f"Klijent: {klijent.get('ime', '')} {klijent.get('prezime', '')} | "
            f"Tip: {klijent.get('tip_lica', 'N/A')}\n"
            f"Interne napomene: {klijent.get('napomene', 'nema')}\n\n"
            f"PREDMETI ({len(predmeti)}):\n"
        )
        for p in predmeti:
            materijal_tekst += f"- {p.get('naziv', 'N/A')} | {p.get('tip', '')} | Status: {p.get('status', 'N/A')}\n"

        if beleske:
            materijal_tekst += f"\nBELESKE ({len(beleske)}):\n"
            for b in beleske[:15]:
                materijal_tekst += f"- [{b.get('tip', 'N/A')}] {b.get('sadrzaj', '')[:250]}\n"

        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": _KOMUNIKACIJA_SYSTEM},
                {"role": "user", "content": materijal_tekst[:8000]}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        profil = json.loads(resp.choices[0].message.content)

        existing = await asyncio.to_thread(
            lambda: supa.table("client_twin_profili")
            .select("id")
            .eq("klijent_id", klijent_id)
            .eq("user_id", user["user_id"])
            .execute()
        )

        if existing.data:
            await asyncio.to_thread(
                lambda: supa.table("client_twin_profili").update({
                    "twin_profil": profil,
                    "br_predmeta": len(predmeti),
                    "updated_at": "now()",
                }).eq("klijent_id", klijent_id).eq("user_id", user["user_id"]).execute()
            )
            akcija = "azuriran"
        else:
            await asyncio.to_thread(
                lambda: supa.table("client_twin_profili").insert({
                    "user_id": user["user_id"],
                    "klijent_id": klijent_id,
                    "twin_profil": profil,
                    "br_predmeta": len(predmeti),
                }).execute()
            )
            akcija = "kreiran"

        return {
            "klijent_id": klijent_id,
            "klijent_ime": f"{klijent.get('ime', '')} {klijent.get('prezime', '')}".strip(),
            "komunikacioni_profil": profil,
            "analizirano_predmeta": len(predmeti),
            "analizirano_beleska": len(beleske),
            "poruka": f"Komunikacioni profil {akcija}.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("analiziraj_komunikacioni_profil: %s", e)
        raise HTTPException(500, str(e))


@router.get("/dashboard")
async def twin_dashboard(user=Depends(get_current_user)):
    """Svi komunikacioni profili, sortirani po datumu azuriranja."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("client_twin_profili")
            .select("klijent_id, twin_profil, br_predmeta, updated_at")
            .eq("user_id", user["user_id"])
            .order("updated_at", desc=True)
            .execute()
        )
        profili = row.data or []

        return {
            "profili": [
                {
                    "klijent_id": p["klijent_id"],
                    "tip_izvestaja": p.get("twin_profil", {}).get("tip_izvestaja", "N/A"),
                    "preferirani_kanal": p.get("twin_profil", {}).get("preferirani_kanal", "N/A"),
                    "ukljucenost_u_odluke": p.get("twin_profil", {}).get("ukljucenost_u_odluke", "N/A"),
                    "pouzdanost": p.get("twin_profil", {}).get("pouzdanost", "N/A"),
                    "br_predmeta": p["br_predmeta"],
                    "updated_at": p["updated_at"],
                }
                for p in profili
            ],
            "ukupno": len(profili),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{klijent_id}")
async def get_komunikacioni_profil(klijent_id: str, user=Depends(get_current_user)):
    """Preuzima komunikacioni profil klijenta."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("client_twin_profili")
            .select("*")
            .eq("klijent_id", klijent_id)
            .eq("user_id", user["user_id"])
            .single()
            .execute()
        )
        if not row.data:
            return {
                "komunikacioni_profil": None,
                "poruka": "Profil jos nije izgradjen. Pokrenite POST /api/client-twin/{id}/analiziraj"
            }
        return {
            "klijent_id": klijent_id,
            "komunikacioni_profil": row.data.get("twin_profil"),
            "br_predmeta": row.data.get("br_predmeta"),
            "updated_at": row.data.get("updated_at"),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.patch("/{klijent_id}")
async def rucno_azuriraj_profil(klijent_id: str, body: RucnoAzuriranjeRequest, user=Depends(get_current_user)):
    """Rucno azurira specificne preferencije (override AI analize)."""
    supa = _get_supa()
    try:
        existing_row = await asyncio.to_thread(
            lambda: supa.table("client_twin_profili")
            .select("twin_profil")
            .eq("klijent_id", klijent_id)
            .eq("user_id", user["user_id"])
            .single()
            .execute()
        )
        if not existing_row.data:
            raise HTTPException(404, "Profil nije pronadjen. Pokrenite /analiziraj prvo.")

        stari_profil = existing_row.data.get("twin_profil") or {}
        update_fields = {k: v for k, v in body.dict().items() if v is not None}
        novi_profil = {**stari_profil, **update_fields, "rucno_azurirano": True}

        await asyncio.to_thread(
            lambda: supa.table("client_twin_profili").update({
                "twin_profil": novi_profil,
                "updated_at": "now()",
            }).eq("klijent_id", klijent_id).eq("user_id", user["user_id"]).execute()
        )

        return {
            "klijent_id": klijent_id,
            "azurirano": list(update_fields.keys()),
            "komunikacioni_profil": novi_profil,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{klijent_id}/savet")
async def get_savet_za_kontakt(klijent_id: str, user=Depends(get_current_user)):
    """Konkretne preporuke za sledeci kontakt sa klijentom na osnovu komunikacionog profila."""
    supa = _get_supa()
    try:
        row = await asyncio.to_thread(
            lambda: supa.table("client_twin_profili")
            .select("twin_profil, updated_at")
            .eq("klijent_id", klijent_id)
            .eq("user_id", user["user_id"])
            .single()
            .execute()
        )
        if not row.data or not row.data.get("twin_profil"):
            raise HTTPException(400, "Nema profila. Pokrenite POST /analiziraj prvo.")

        p = row.data["twin_profil"]
        saveti = []

        if p.get("tip_izvestaja") == "kratak":
            saveti.append("Pripremi kratak izvestaj — maks 1 stranica, bullet points.")
        elif p.get("tip_izvestaja") == "detaljan":
            saveti.append("Pripremi detaljan izvestaj sa objasnjenjima svakog koraka.")

        if p.get("uvek_trazi_procenu_troskova"):
            saveti.append("Uvek ukljuci procenu troskova u komunikaciju.")
        if p.get("uvek_trazi_rokove"):
            saveti.append("Jasno istakni sve rokove i sledece korake sa datumima.")
        if p.get("pita_za_alternative"):
            saveti.append("Ponudi 2-3 alternative, ne samo jednu preporuku.")
        if p.get("ocekuje_brze_odgovore"):
            saveti.append("Odgovori u roku od 24h — klijent ocekuje brze reakcije.")

        kanal = p.get("preferirani_kanal")
        if kanal and kanal != "nije_poznato":
            saveti.append(f"Preferirani kanal: {kanal}.")

        ukljucenost = p.get("ukljucenost_u_odluke")
        if ukljucenost == "uvek":
            saveti.append("Ukljuci klijenta u svaku odluku — ne donosi odluke bez konsultacije.")
        elif ukljucenost == "delegira":
            saveti.append("Klijent delegira — donesi preporuku sa jasnim obrazlozenjiem, ne trazi odobrenje za svaki korak.")

        konkretne = p.get("konkretne_napomene", [])

        return {
            "klijent_id": klijent_id,
            "saveti_za_kontakt": saveti,
            "konkretne_napomene_iz_profila": konkretne,
            "prioriteti_pri_izvestavanju": p.get("prioriteti_pri_izvestavanju", []),
            "pouzdanost_profila": p.get("pouzdanost", "N/A"),
            "disclaimer": p.get("disclaimer", ""),
            "poslednje_azurirano": row.data.get("updated_at"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
