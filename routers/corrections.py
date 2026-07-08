# -*- coding: utf-8 -*-
"""
Vindex AI — routers/corrections.py

Correction Capture Pipeline — nevidljivo hvatanje korekcija AI outputa.

Princip: Kada advokat izmeni AI-generisani tekst i sačuva ga,
frontend pošalje (original_ai_output, edited_output) ovde.
Sistem:
  1. Meri stepen izmene (edit distance)
  2. Čuva u ai_corrections tabeli
  3. Periodično agregira u firm_style_profile

Frontend integracija (JavaScript):
  // Nakon što korisnik sačuva izmenjeni AI tekst:
  await fetch('/api/corrections/capture', {
    method: 'POST',
    headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    body: JSON.stringify({
      original_output: aiGeneratedText,
      edited_output:   savedText,
      context_type:    'drafting',  // 'drafting'|'analiza'|'copilot'|'nacrt'
      predmet_id:      predmetId,   // opciono
      tip_dokumenta:   'tuzba',     // opciono
    })
  });

Endpoints:
  POST /api/corrections/capture          — sačuvaj korekciju
  POST /api/corrections/analyze          — agregiraj u stil profil (cron/admin)
  GET  /api/corrections/style-profile    — trenutni stil profil kancelarije
  GET  /api/corrections/stats            — statistika korekcija
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user, _is_founder
from shared.rate import limiter

logger = logging.getLogger("vindex.corrections")
router = APIRouter(prefix="/api/corrections", tags=["corrections"])


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class CorrectionRequest(BaseModel):
    original_output: str = Field(..., min_length=10)
    edited_output:   str = Field(..., min_length=1)
    context_type:    str = Field("ostalo")
    predmet_id:      Optional[str] = None
    tip_dokumenta:   Optional[str] = None
    prompt_summary:  Optional[str] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _edit_distance_approx(a: str, b: str) -> int:
    """Aproksimativna Levenshtein distanca (reč-nivo za brzinu)."""
    a_words = a.lower().split()
    b_words = b.lower().split()
    a_set = set(a_words)
    b_set = set(b_words)
    added   = len(b_set - a_set)
    removed = len(a_set - b_set)
    return added + removed


def _izmena_procenat(original: str, edited: str) -> float:
    """Procenat izmenjenih reči (0.0 = identično, 1.0 = potpuno drugačije)."""
    if not original:
        return 1.0
    o_words = set(original.lower().split())
    e_words = set(edited.lower().split())
    if not o_words:
        return 1.0
    zajednicki = len(o_words & e_words)
    return round(1.0 - zajednicki / max(len(o_words), len(e_words)), 3)


def _detektuj_stil(original: str, edited: str) -> dict:
    """Detektuje karakteristike izmene za izgradnju stil profila."""
    signals = {}

    # Dužina: skratio ili produžio?
    o_len = len(original.split())
    e_len = len(edited.split())
    if e_len < o_len * 0.7:
        signals["preferira_krace"] = True
    elif e_len > o_len * 1.3:
        signals["preferira_duze"] = True

    # Bullet liste
    if "\n-" in edited or "\n•" in edited:
        signals["koristi_bullet_liste"] = True

    # Numerisane tačke
    import re
    if re.search(r"\n\s*\d+\.", edited):
        signals["koristi_numerisane_tacke"] = True

    # Formalni/neformalni ton (gruba heuristika za srpski)
    formalni_markeri = ["poštovani", "sa uvažavanjem", "u skladu sa", "u smislu odredbe"]
    neformalni_markeri = ["možete", "molim vas", "hvala"]
    edited_lower = edited.lower()
    if any(m in edited_lower for m in formalni_markeri):
        signals["ton"] = "veoma_formalan"
    elif any(m in edited_lower for m in neformalni_markeri):
        signals["ton"] = "umereno_formalan"

    return signals


async def _get_kancelarija_id(supa, uid: str) -> Optional[str]:
    """Pronalazi kancelarija_id za datog korisnika."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("kancelarija_id")
                .eq("user_id", uid)
                .eq("status", "aktivan")
                .maybe_single()
                .execute()
        )
        if r.data:
            return r.data.get("kancelarija_id")
        # Može biti admin
        r2 = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("id")
                .eq("admin_uid", uid)
                .maybe_single()
                .execute()
        )
        return r2.data.get("id") if r2.data else None
    except Exception:
        return None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/capture")
@limiter.limit("120/minute")
async def capture_correction(
    request: Request,
    payload: CorrectionRequest,
    user: dict = Depends(get_current_user),
):
    """
    Nevidljivo hvatanje korekcije AI outputa.
    Poziva se iz frontenda kada korisnik sačuva izmenjeni AI tekst.
    Ne troši kredite. Nulta frikcija.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Ako je identično — ne čuvaj (nema korekcije)
    izmena = _izmena_procenat(payload.original_output, payload.edited_output)
    if izmena < 0.02:
        return {"ok": True, "captured": False, "reason": "no_change"}

    kancelarija_id = await _get_kancelarija_id(supa, uid)
    edit_dist = _edit_distance_approx(payload.original_output, payload.edited_output)

    try:
        await asyncio.to_thread(
            lambda: supa.table("ai_corrections").insert({
                "user_id":        uid,
                "kancelarija_id": kancelarija_id,
                "predmet_id":     payload.predmet_id,
                "context_type":   payload.context_type[:50],
                "original_output": payload.original_output[:8000],
                "edited_output":   payload.edited_output[:8000],
                "edit_distance":   edit_dist,
                "prompt_summary":  (payload.prompt_summary or "")[:200],
                "tip_dokumenta":   (payload.tip_dokumenta or "ostalo")[:50],
                "processed":       False,
            }).execute()
        )
    except Exception as e:
        logger.debug("[CORRECTIONS] Insert greška: %s", e)
        return {"ok": False, "error": "db_error"}

    # Ako firma ima 10+ novih korekcija — pokreni async ažuriranje stil profila
    if kancelarija_id:
        asyncio.create_task(_maybe_update_style_profile(kancelarija_id, supa))

    return {"ok": True, "captured": True, "izmena_procenat": izmena}


@router.post("/analyze")
async def analyze_corrections(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Agregiraj neprocesirane korekcije u firm_style_profile.
    Pozivati periodično (cron) ili ručno.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Kancelarija nije pronađena.")

    result = await _update_style_profile(kancelarija_id, supa)
    return result


@router.get("/style-profile")
@limiter.limit("30/minute")
async def get_style_profile(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća trenutni stil profil kancelarije."""
    uid  = user["user_id"]
    supa = _get_supa()

    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        return {"stil_data": {}, "korekcija_count": 0, "poruka": "Niste član kancelarije."}

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("firm_style_profile")
                .select("*")
                .eq("kancelarija_id", kancelarija_id)
                .maybe_single()
                .execute()
        )
        if not r.data:
            return {
                "stil_data": {},
                "korekcija_count": 0,
                "poruka": "Stil profil još nije izgrađen. Nastavite da koristite Vindex i sistem će naučiti vaš stil.",
            }
        return r.data
    except Exception as e:
        return {"error": str(e)}


@router.get("/stats")
@limiter.limit("30/minute")
async def get_correction_stats(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Statistika korekcija za dashboarda."""
    uid  = user["user_id"]
    supa = _get_supa()

    kancelarija_id = await _get_kancelarija_id(supa, uid)

    try:
        query_filter = {"kancelarija_id": kancelarija_id} if kancelarija_id else {"user_id": uid}
        field = "kancelarija_id" if kancelarija_id else "user_id"
        val   = kancelarija_id   if kancelarija_id else uid

        r = await asyncio.to_thread(
            lambda: supa.table("ai_corrections")
                .select("context_type, edit_distance, tip_dokumenta, created_at")
                .eq(field, val)
                .order("created_at", desc=True)
                .limit(200)
                .execute()
        )
        rows = r.data or []

        po_tipu: dict[str, int] = {}
        for row in rows:
            ct = row.get("context_type", "ostalo")
            po_tipu[ct] = po_tipu.get(ct, 0) + 1

        avg_dist = sum(r.get("edit_distance", 0) or 0 for r in rows) / max(1, len(rows))

        return {
            "ukupno_korekcija": len(rows),
            "po_tipu": po_tipu,
            "prosecna_izmena_reci": round(avg_dist, 1),
            "poruka": (
                f"Na osnovu {len(rows)} korekcija, sistem uči vaš stil pisanja."
                if len(rows) >= 5 else
                "Nastavite sa radom — sistem počinje da uči vaš stil nakon 5+ korekcija."
            ),
        }
    except Exception as e:
        return {"error": str(e), "ukupno_korekcija": 0}


# ─── Interni async helpers ────────────────────────────────────────────────────

async def _maybe_update_style_profile(kancelarija_id: str, supa) -> None:
    """Ažurira stil profil samo ako ima 10+ neprocesiranih korekcija."""
    try:
        cnt = await asyncio.to_thread(
            lambda: supa.table("ai_corrections")
                .select("id", count="exact")
                .eq("kancelarija_id", kancelarija_id)
                .eq("processed", False)
                .execute()
        )
        if (cnt.count or 0) >= 10:
            await _update_style_profile(kancelarija_id, supa)
    except Exception as e:
        logger.debug("[CORRECTIONS] maybe_update greška: %s", e)


async def _update_style_profile(kancelarija_id: str, supa) -> dict:
    """
    Čita neprocesirane korekcije, agregira stilske signale,
    ažurira firm_style_profile, markira korekcije kao processed.
    """
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("ai_corrections")
                .select("original_output, edited_output, context_type, tip_dokumenta")
                .eq("kancelarija_id", kancelarija_id)
                .eq("processed", False)
                .limit(50)
                .execute()
        )
        rows = r.data or []

        if not rows:
            return {"ok": True, "processed": 0}

        # Agregiraj signale
        signali_lista = []
        ukupna_izmena = 0.0
        tip_stat: dict[str, int] = {}

        for row in rows:
            orig = row.get("original_output", "")
            edit = row.get("edited_output", "")
            tip  = row.get("tip_dokumenta", "ostalo")

            signali = _detektuj_stil(orig, edit)
            signali_lista.append(signali)
            ukupna_izmena += _izmena_procenat(orig, edit)
            tip_stat[tip] = tip_stat.get(tip, 0) + 1

        n = len(rows)
        prosek_izmena = round(ukupna_izmena / n * 100, 1)

        # Glasanje za signale
        bullet = sum(1 for s in signali_lista if s.get("koristi_bullet_liste"))
        numeri = sum(1 for s in signali_lista if s.get("koristi_numerisane_tacke"))
        krace  = sum(1 for s in signali_lista if s.get("preferira_krace"))
        duze   = sum(1 for s in signali_lista if s.get("preferira_duze"))
        formalni = sum(1 for s in signali_lista if s.get("ton") == "veoma_formalan")

        stil_update = {
            "preferira_bullet_liste":       bullet > n * 0.4,
            "preferira_numerisane_tacke":   numeri > n * 0.4,
            "preferira_krace":              krace  > n * 0.5,
            "preferira_duze":               duze   > n * 0.5,
            "ton": "veoma_formalan" if formalni > n * 0.5 else "formalan",
            "prosecna_izmena_procenat":     prosek_izmena,
            "tip_dokumenta_stat":           tip_stat,
        }

        # GPT-4o-mini za dublje zaključke (samo ako ima 20+ korekcija)
        if n >= 20:
            try:
                sample_pairs = rows[:5]
                pairs_txt = "\n---\n".join(
                    f"ORIGINAL:\n{r['original_output'][:300]}\n\nIZMENJENO:\n{r['edited_output'][:300]}"
                    for r in sample_pairs
                )
                from openai import AsyncOpenAI
                oai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
                gpt_r = await oai.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.2,
                    max_tokens=300,
                    messages=[{
                        "role": "user",
                        "content": (
                            "Analiziraj 5 parova originalni AI tekst → izmenjeni tekst od advokata u Srbiji. "
                            "Identifikuj obrazac kako advokat piše (stil, ton, duzinam fraze koje koristi). "
                            "Odgovori SAMO JSON-om: {\"stil_opis\": \"...\", \"preferirane_fraze\": [\"...\"], "
                            "\"izbegavane_fraze\": [\"...\"], \"ton\": \"...\"}. Ekavica.\n\n"
                            + pairs_txt
                        )
                    }],
                    response_format={"type": "json_object"},
                )
                gpt_data = json.loads(gpt_r.choices[0].message.content or "{}")
                stil_update.update({
                    "stil_opis":          gpt_data.get("stil_opis", ""),
                    "preferirane_fraze":  gpt_data.get("preferirane_fraze", [])[:10],
                    "izbegavane_fraze":   gpt_data.get("izbegavane_fraze", [])[:10],
                })
            except Exception as e:
                logger.debug("[CORRECTIONS] GPT stil greška: %s", e)

        # Upsert u firm_style_profile
        try:
            existing = await asyncio.to_thread(
                lambda: supa.table("firm_style_profile")
                    .select("id, korekcija_count, stil_data")
                    .eq("kancelarija_id", kancelarija_id)
                    .maybe_single()
                    .execute()
            )

            if existing.data:
                prev_count = existing.data.get("korekcija_count", 0)
                prev_stil  = existing.data.get("stil_data") or {}
                merged = {**prev_stil, **stil_update}
                await asyncio.to_thread(
                    lambda: supa.table("firm_style_profile")
                        .update({
                            "korekcija_count": prev_count + n,
                            "stil_data":       merged,
                            "last_updated":    datetime.now(timezone.utc).isoformat(),
                        })
                        .eq("kancelarija_id", kancelarija_id)
                        .execute()
                )
            else:
                await asyncio.to_thread(
                    lambda: supa.table("firm_style_profile").insert({
                        "kancelarija_id": kancelarija_id,
                        "korekcija_count": n,
                        "stil_data": stil_update,
                    }).execute()
                )
        except Exception as e:
            logger.error("[CORRECTIONS] profile upsert greška: %s", e)

        # Markir korekcije kao processed
        try:
            await asyncio.to_thread(
                lambda: supa.table("ai_corrections")
                    .update({"processed": True})
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("processed", False)
                    .execute()
            )
        except Exception as e:
            logger.debug("[CORRECTIONS] mark processed greška: %s", e)

        logger.info("[CORRECTIONS] firma=%s processed=%d stil=%s", kancelarija_id[:8], n, stil_update.get("ton"))
        return {"ok": True, "processed": n, "stil_update": stil_update}

    except Exception as e:
        logger.error("[CORRECTIONS] update_style_profile greška: %s", e)
        return {"ok": False, "error": str(e)}
