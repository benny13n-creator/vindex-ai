# -*- coding: utf-8 -*-
"""
Vindex AI — routers/onboarding.py

F3.3: Onboarding flow — 5-koracni wizard za postavljanje kancelarije.

SQL migracija (pokrenuti JEDNOM u Supabase SQL editor):
──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS onboarding_state (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid UNIQUE NOT NULL,
  step_completed   int DEFAULT 0,
  completed        boolean DEFAULT false,
  tip_kancelarije  text,
  oblasti_prava    text[],
  broj_predmeta    text,
  ciljevi          text[],
  completed_at     timestamptz,
  created_at       timestamptz DEFAULT now(),
  updated_at       timestamptz DEFAULT now()
);
──────────────────────────────────────────────────────

Koraci:
  1 — Tip kancelarije (samostalni/tim/firma)
  2 — Oblast prava (krivicno/gradjansko/privredno/radno/ostalo)
  3 — Broj predmeta mesecno (do10/10-50/50+)
  4 — Ciljevi (billing/praksa/dokumenti/ai/sve)
  5 — Kompletiran
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.onboarding")
router = APIRouter(tags=["onboarding"])

_PRAZAN_STATE = {
    "step_completed":  0,
    "completed":       False,
    "tip_kancelarije": None,
    "oblasti_prava":   None,
    "broj_predmeta":   None,
    "ciljevi":         None,
    "completed_at":    None,
}


class OnboardingStep(BaseModel):
    step:    int  = Field(..., ge=1, le=5)
    odgovor: dict = Field(...)


async def _dohvati_state(supa, uid: str) -> dict:
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("onboarding_state")
                .select("*")
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        return r.data or dict(_PRAZAN_STATE)
    except Exception as exc:
        logger.debug("onboarding_state tabela greška: %s", exc)
        return dict(_PRAZAN_STATE)


async def _upsert_state(supa, uid: str, update: dict) -> None:
    try:
        existing = await asyncio.to_thread(
            lambda: supa.table("onboarding_state").select("id").eq("user_id", uid).maybe_single().execute()
        )
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        if existing.data:
            await asyncio.to_thread(
                lambda: supa.table("onboarding_state").update(update).eq("user_id", uid).execute()
            )
        else:
            update["user_id"] = uid
            await asyncio.to_thread(
                lambda: supa.table("onboarding_state").insert(update).execute()
            )
    except Exception as exc:
        logger.warning("onboarding upsert greška: %s", exc)


@router.get("/api/onboarding/stanje")
@limiter.limit("30/minute")
async def onboarding_stanje(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vrati trenutni onboarding state za korisnika."""
    uid  = user["user_id"]
    supa = _get_supa()
    state = await _dohvati_state(supa, uid)
    return state


@router.post("/api/onboarding/korak")
@limiter.limit("30/minute")
async def onboarding_korak(
    body: OnboardingStep,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Upiši odgovor za jedan onboarding korak."""
    uid  = user["user_id"]
    supa = _get_supa()

    update: dict[str, Any] = {"step_completed": body.step}

    if body.step == 1:
        update["tip_kancelarije"] = body.odgovor.get("tip")
    elif body.step == 2:
        oblasti = body.odgovor.get("oblasti")
        update["oblasti_prava"] = oblasti if isinstance(oblasti, list) else [oblasti] if oblasti else []
    elif body.step == 3:
        update["broj_predmeta"] = body.odgovor.get("broj")
    elif body.step == 4:
        ciljevi = body.odgovor.get("ciljevi")
        update["ciljevi"] = ciljevi if isinstance(ciljevi, list) else [ciljevi] if ciljevi else []
    elif body.step == 5:
        update["completed"]    = True
        update["completed_at"] = datetime.now(timezone.utc).isoformat()

    await _upsert_state(supa, uid, update)
    logger.info("[ONBOARDING] uid=%.8s korak=%d", uid, body.step)
    return {"success": True, "step": body.step, "completed": body.step == 5}


@router.get("/api/onboarding/kompletiran")
@limiter.limit("60/minute")
async def onboarding_kompletiran(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Brza provera da li je onboarding završen."""
    uid   = user["user_id"]
    supa  = _get_supa()
    state = await _dohvati_state(supa, uid)
    return {
        "completed":      state.get("completed", False),
        "step_completed": state.get("step_completed", 0),
    }


# ─── Demo predmet (Beta onboarding kit) ────────────────────────────────────────

_DEMO_NAZIV = "🎓 Demo predmet — Vindex AI vodič"
_DEMO_OPIS = (
    "Ovo je demo predmet koji vam pomaže da isprobate Vindex AI. "
    "Tužilac Marko Marković potražuje naknadu štete od 350.000 RSD od tuženog "
    "\"Demo Klijent d.o.o.\" zbog neispunjenja ugovorne obaveze isporuke robe iz "
    "ugovora od 15.03.2026. Slobodno pokrenite AI analizu, dodajte rok ili "
    "uključite praćenje portala — ovo je siguran prostor za vežbu, možete ga "
    "obrisati kad god želite."
)


@router.post("/api/onboarding/demo-predmet")
@limiter.limit("5/minute")
async def kreiraj_demo_predmet(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Kreira jedan demo predmet (klijent + rok + zadatak + dokument) da bi novi
    korisnik odmah imao nešto da istraži. Idempotentno — ne duplira ako demo
    predmet za ovog korisnika već postoji (prepoznaje se po fiksnom nazivu).
    """
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        existing = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id")
                .eq("user_id", uid)
                .eq("naziv", _DEMO_NAZIV)
                .limit(1)
                .execute()
        )
        if existing.data:
            return {"ok": True, "vec_postoji": True, "predmet_id": existing.data[0]["id"]}
    except Exception as e:
        logger.warning("[ONBOARDING] Provera demo predmeta greška: %s", e)

    # Klijent
    klijent_id = None
    try:
        kl_r = await asyncio.to_thread(
            lambda: supa.table("klijenti").insert({
                "user_id": uid, "status": "aktivan",
                "ime": "Marko", "prezime": "Marković", "firma": "Demo Klijent d.o.o.",
                "email": "demo.klijent@vindex.rs",
            }).execute()
        )
        if kl_r.data:
            klijent_id = kl_r.data[0]["id"]
    except Exception as e:
        logger.warning("[ONBOARDING] Demo klijent greška: %s", e)

    # Predmet
    try:
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti").insert({
                "user_id": uid, "naziv": _DEMO_NAZIV, "opis": _DEMO_OPIS,
                "tip": "parnicno", "status": "aktivan",
                "tuzilac": "Marko Marković", "tuzeni": "Demo Klijent d.o.o.",
            }).execute()
        )
    except Exception as e:
        logger.error("[ONBOARDING] Demo predmet insert greška: %s", e)
        raise HTTPException(status_code=500, detail="Kreiranje demo predmeta nije uspelo.")

    if not pred_r.data:
        raise HTTPException(status_code=500, detail="Kreiranje demo predmeta nije uspelo.")
    predmet_id = pred_r.data[0]["id"]

    if klijent_id:
        try:
            await asyncio.to_thread(
                lambda: supa.table("predmet_klijenti").insert({
                    "predmet_id": predmet_id, "klijent_id": klijent_id,
                    "uloga_klijenta": "stranka", "user_id": uid,
                }).execute()
            )
        except Exception as e:
            logger.debug("[ONBOARDING] predmet_klijenti greška: %s", e)

    # Rok (10 dana od danas)
    try:
        rok_datum = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()
        await asyncio.to_thread(
            lambda: supa.table("predmet_hronologija").insert({
                "predmet_id": predmet_id, "user_id": uid,
                "dogadjaj": "Rok za odgovor na tužbu", "datum": rok_datum, "datum_iso": rok_datum,
                "vaznost": "kritičan", "akter": "Demo predmet",
            }).execute()
        )
    except Exception as e:
        logger.debug("[ONBOARDING] Demo rok greška: %s", e)

    # Zadatak
    try:
        from routers.zadaci import _get_firma_info
        firma = await _get_firma_info(supa, uid)
        await asyncio.to_thread(
            lambda: supa.table("zadaci").insert({
                "kancelarija_id": firma.get("kancelarija_id"),
                "predmet_id": predmet_id, "kreirao_uid": uid, "dodeljen_uid": uid,
                "naziv": "Pregledati dokumentaciju demo predmeta",
                "opis": "Prvi koraci — otvorite AI Analizu i pokrenite kompletnu analizu.",
                "prioritet": "normalan", "status": "otvoreno",
            }).execute()
        )
    except Exception as e:
        logger.debug("[ONBOARDING] Demo zadatak greška: %s", e)

    # Dokument (metapodaci — bez stvarnog fajla, dovoljno za checklist/demo)
    try:
        await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti").insert({
                "predmet_id": predmet_id, "user_id": uid,
                "naziv_fajla": "Ugovor_o_isporuci_demo.pdf", "velicina_kb": 128,
            }).execute()
        )
    except Exception as e:
        logger.debug("[ONBOARDING] Demo dokument greška: %s", e)

    logger.info("[ONBOARDING] Demo predmet kreiran za uid=%.8s: %s", uid, predmet_id)
    return {"ok": True, "vec_postoji": False, "predmet_id": predmet_id}


# ─── Welcome checklist (Beta onboarding kit) ───────────────────────────────────

@router.get("/api/onboarding/checklist")
@limiter.limit("30/minute")
async def onboarding_checklist(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Izvedena (ne uskladištena) kontrolna lista — proverava stvarno stanje
    korisnika umesto posebnog trackovanog fleg-a, pa ne moze da zastari.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    async def _has(table: str, col: str = "id", user_col: str = "user_id") -> bool:
        try:
            r = await asyncio.to_thread(
                lambda: supa.table(table).select(col).eq(user_col, uid).limit(1).execute()
            )
            return bool(r.data)
        except Exception:
            return False

    async def _has_event(feature: str) -> bool:
        try:
            r = await asyncio.to_thread(
                lambda: supa.table("usage_events").select("id").eq("user_id", uid)
                    .eq("feature", feature).limit(1).execute()
            )
            return bool(r.data)
        except Exception:
            return False

    kreirao_predmet, uploadovao_dok, pokrenuo_analizu, dodao_rok, portal_ukljucen, kreirao_zadatak = \
        await asyncio.gather(
            _has("predmeti"),
            _has("predmet_dokumenti"),
            _has_event("ai_analysis"),
            _has("predmet_hronologija"),
            _has("praceni_predmeti"),
            _has("zadaci", user_col="kreirao_uid"),
        )

    stavke = [
        {"kod": "kreiraj_predmet",     "naziv": "Kreirajte predmet",              "gotovo": kreirao_predmet},
        {"kod": "uploaduj_dokument",   "naziv": "Uploadujte dokument",            "gotovo": uploadovao_dok},
        {"kod": "pokreni_ai_analizu",  "naziv": "Pokrenite AI analizu",           "gotovo": pokrenuo_analizu},
        {"kod": "dodaj_rok",           "naziv": "Dodajte rok",                    "gotovo": dodao_rok},
        {"kod": "aktiviraj_portal",    "naziv": "Aktivirajte praćenje portala",   "gotovo": portal_ukljucen},
        {"kod": "kreiraj_zadatak",     "naziv": "Kreirajte zadatak",              "gotovo": kreirao_zadatak},
    ]
    zavrseno = sum(1 for s in stavke if s["gotovo"])

    return {"stavke": stavke, "zavrseno": zavrseno, "ukupno": len(stavke), "kompletno": zavrseno == len(stavke)}
