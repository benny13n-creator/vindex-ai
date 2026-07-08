# -*- coding: utf-8 -*-
"""
Vindex AI — routers/firm_memory.py

AI Memory Engine — institucionalna inteligencija kancelarije.

Šta radi:
  - Pamti ponašanje, ne samo tekst
  - Partner A odbio strategiju X → AI nikad više ne predlaže X tom partneru
  - Sudija Y uvek insistira na određenoj procesnoj formi → AI to zna pre ročišta
  - Klijent Z nikad ne prihvata nagodbu → AI to uzima u obzir pri savetu
  - Svaka firma gradi sopstvenu institucionalnu memoriju koja se ne može kopirati

Tri tipa memorije:
  1. Generalna (memory_entries)     — slobodni unos bilo čega bitnog
  2. Sudijska (judge_patterns)      — procesni obrasci sudija
  3. Klijentska (client_memory)     — preferencije i stavovi klijenata

Endpoints:
  POST /api/firma-memorija/dodaj              — dodaj memoriju
  GET  /api/firma-memorija/pretrazi           — AI pretraga relevantnih memorija
  GET  /api/firma-memorija/sudija/{ime}       — profil sudije
  POST /api/firma-memorija/sudija/sacuvaj     — ažuriraj profil sudije
  GET  /api/firma-memorija/klijent/{ime}      — profil klijenta
  POST /api/firma-memorija/klijent/sacuvaj    — ažuriraj profil klijenta
  GET  /api/firma-memorija/partner/{uid}      — profil partnera
  DELETE /api/firma-memorija/{id}             — ukloni memoriju
  GET  /api/firma-memorija/sve               — sve aktivne memorije firme
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.firm_memory")
router = APIRouter(prefix="/api/firma-memorija", tags=["firma-memorija"])

_ENTITY_TYPES = {"partner", "klijent", "sudija", "firma", "predmet"}
_MEMORY_TIPS  = {"preferencija", "odbijanje", "obrazac", "napomena"}
_VAZNOSTI     = {"visoka", "normalna", "niska"}


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_kancelarija_id(supa, uid: str) -> Optional[str]:
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
        return r2.data.get("kancelarija_id") if r2.data else None
    except Exception:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class MemorijaDodajReq(BaseModel):
    entity_type:  str  = Field(..., description="partner|klijent|sudija|firma|predmet")
    entity_id:    str  = Field(..., min_length=1, max_length=200)
    entity_name:  Optional[str] = None
    tip:          str  = Field(..., description="preferencija|odbijanje|obrazac|napomena")
    sadrzaj:      str  = Field(..., min_length=5, max_length=2000)
    kontekst:     Optional[str] = None
    vaznost:      str  = Field("normalna")


class SudijaSacuvajReq(BaseModel):
    sudija_ime:        str
    sud:               Optional[str] = None
    oblast_prava:      Optional[str] = None
    insistira_na:      Optional[list] = None
    odbija:            Optional[list] = None
    opis_ponasanja:    Optional[str] = None
    napomene:          Optional[str] = None
    pobeda:            bool = False
    poraz:             bool = False
    nagodba:           bool = False


class KlijentSacuvajReq(BaseModel):
    klijent_ime:       str
    klijent_id:        Optional[str] = None
    prihvata_nagodbu:  Optional[bool] = None
    preferira_brze:    Optional[bool] = None
    komunikacija_tip:  Optional[str] = None
    rizik_profil:      Optional[str] = None
    napomene:          Optional[str] = None
    kljucna_odluka:    Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/dodaj")
@limiter.limit("60/minute")
async def dodaj_memoriju(
    request: Request,
    payload: MemorijaDodajReq,
    user: dict = Depends(get_current_user),
):
    """
    Dodaje novu memoriju za entitet (partner/klijent/sudija/firma/predmet).
    Primer: "Sudija Petrović uvek odbija podneske bez tabelarnog prikaza rokova."
    """
    uid  = user["user_id"]
    supa = _get_supa()

    if payload.entity_type not in _ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type mora biti: {', '.join(_ENTITY_TYPES)}")
    if payload.tip not in _MEMORY_TIPS:
        raise HTTPException(status_code=400, detail=f"tip mora biti: {', '.join(_MEMORY_TIPS)}")
    if payload.vaznost not in _VAZNOSTI:
        raise HTTPException(status_code=400, detail=f"vaznost mora biti: {', '.join(_VAZNOSTI)}")

    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član nijedne kancelarije.")

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("memory_entries").insert({
                "kancelarija_id": kancelarija_id,
                "user_id":        uid,
                "entity_type":    payload.entity_type,
                "entity_id":      payload.entity_id[:200],
                "entity_name":    (payload.entity_name or payload.entity_id)[:200],
                "tip":            payload.tip,
                "sadrzaj":        payload.sadrzaj[:2000],
                "kontekst":       (payload.kontekst or "")[:500],
                "vaznost":        payload.vaznost,
                "aktivan":        True,
            }).execute()
        )
        return {"ok": True, "id": (r.data or [{}])[0].get("id")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pretrazi")
@limiter.limit("30/minute")
async def pretrazi_memoriju(
    request: Request,
    user: dict = Depends(get_current_user),
    q: str = "",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 20,
):
    """
    Pretraga relevantnih memorija.
    Koristi se u AI pipeline-u da pronađe šta sistem pamti o učesniku u predmetu.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        return {"memorije": [], "poruka": "Niste član nijedne kancelarije."}

    try:
        qb = (supa.table("memory_entries")
              .select("*")
              .eq("kancelarija_id", kancelarija_id)
              .eq("aktivan", True))

        if entity_type:
            qb = qb.eq("entity_type", entity_type)
        if entity_id:
            qb = qb.eq("entity_id", entity_id)

        r = await asyncio.to_thread(
            lambda: qb.order("vaznost").order("created_at", desc=True).limit(min(limit, 100)).execute()
        )
        memorije = r.data or []

        # Lokalno filtriranje po q (case-insensitive, srpski)
        if q:
            q_l = q.lower()
            memorije = [
                m for m in memorije
                if q_l in (m.get("sadrzaj", "") + m.get("entity_name", "")).lower()
            ]

        return {
            "memorije": memorije,
            "ukupno":   len(memorije),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kontekst-za-ai")
@limiter.limit("60/minute")
async def kontekst_za_ai(
    request: Request,
    user: dict = Depends(get_current_user),
    sudija_ime: Optional[str] = None,
    klijent_ime: Optional[str] = None,
    partner_uid: Optional[str] = None,
):
    """
    Vraća sve memorije relevantne za konkretni predmet/situaciju.
    Poziva se iz AI pipeline-a pre generisanja odgovora.
    Output se injectuje u system prompt.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        return {"kontekst": "", "memorije_count": 0}

    delovi: list[str] = []
    memorije_count = 0

    async def _fetch_memorije(entity_id: str, entity_type: str) -> list[dict]:
        try:
            r = await asyncio.to_thread(
                lambda: supa.table("memory_entries")
                    .select("tip, sadrzaj, vaznost")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("entity_id", entity_id)
                    .eq("entity_type", entity_type)
                    .eq("aktivan", True)
                    .order("vaznost")
                    .limit(10)
                    .execute()
            )
            return r.data or []
        except Exception:
            return []

    if sudija_ime:
        mem = await _fetch_memorije(sudija_ime, "sudija")
        if mem:
            memorije_count += len(mem)
            delovi.append(f"MEMORIJA O SUDIJI {sudija_ime.upper()}:")
            for m in mem:
                delovi.append(f"  [{m['tip'].upper()}] {m['sadrzaj']}")

        # Sudijski profil
        try:
            jp = await asyncio.to_thread(
                lambda: supa.table("judge_patterns")
                    .select("insistira_na, odbija, opis_ponasanja, pobede, porazi")
                    .eq("kancelarija_id", kancelarija_id)
                    .ilike("sudija_ime", f"%{sudija_ime}%")
                    .maybe_single()
                    .execute()
            )
            if jp.data:
                memorije_count += 1
                if jp.data.get("insistira_na"):
                    delovi.append(f"  Sudija insistira na: {', '.join(jp.data['insistira_na'][:5])}")
                if jp.data.get("odbija"):
                    delovi.append(f"  Sudija odbija: {', '.join(jp.data['odbija'][:5])}")
                uk = (jp.data.get("pobede", 0) or 0) + (jp.data.get("porazi", 0) or 0)
                if uk > 0:
                    wr = round((jp.data.get("pobede", 0) or 0) / uk * 100)
                    delovi.append(f"  Istorija: {wr}% win rate ({uk} predmeta)")
        except Exception:
            pass

    if klijent_ime:
        mem = await _fetch_memorije(klijent_ime, "klijent")
        if mem:
            memorije_count += len(mem)
            delovi.append(f"MEMORIJA O KLIJENTU {klijent_ime.upper()}:")
            for m in mem:
                delovi.append(f"  [{m['tip'].upper()}] {m['sadrzaj']}")

        try:
            cm = await asyncio.to_thread(
                lambda: supa.table("client_memory")
                    .select("prihvata_nagodbu, preferira_brze, rizik_profil, napomene")
                    .eq("kancelarija_id", kancelarija_id)
                    .ilike("klijent_ime", f"%{klijent_ime}%")
                    .maybe_single()
                    .execute()
            )
            if cm.data:
                memorije_count += 1
                if cm.data.get("prihvata_nagodbu") is False:
                    delovi.append(f"  VAZNO: Klijent {klijent_ime} NIKAD ne prihvata nagodbu.")
                elif cm.data.get("prihvata_nagodbu") is True:
                    delovi.append(f"  Klijent {klijent_ime} otvoren za nagodbu.")
                if cm.data.get("rizik_profil") == "visok":
                    delovi.append(f"  Visokorizican klijent — biti oprezan sa savetima.")
        except Exception:
            pass

    if partner_uid:
        mem = await _fetch_memorije(partner_uid, "partner")
        if mem:
            memorije_count += len(mem)
            delovi.append(f"MEMORIJA O PARTNERU:")
            for m in mem:
                delovi.append(f"  [{m['tip'].upper()}] {m['sadrzaj']}")

        try:
            pp = await asyncio.to_thread(
                lambda: supa.table("partner_profiles")
                    .select("preferira_krace, preferira_bullet, odbijene_strategije, preferirane_fraze")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("partner_uid", partner_uid)
                    .maybe_single()
                    .execute()
            )
            if pp.data:
                memorije_count += 1
                if pp.data.get("preferira_krace"):
                    delovi.append("  Partner preferira kraće odgovore.")
                if pp.data.get("preferira_bullet"):
                    delovi.append("  Partner preferira bullet liste.")
                odbijene = pp.data.get("odbijene_strategije") or []
                if odbijene:
                    delovi.append(f"  Partner je ranije odbio: {'; '.join(str(s) for s in odbijene[:3])}")
        except Exception:
            pass

    kontekst = "\n".join(delovi)
    return {
        "kontekst":        kontekst,
        "memorije_count":  memorije_count,
        "has_memory":      memorije_count > 0,
    }


@router.get("/sudija/{sudija_ime}")
@limiter.limit("30/minute")
async def get_sudija_profil(
    sudija_ime: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća profil sudije — procesni obrasci, istorija, napomene."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član kancelarije.")

    try:
        jp_r = await asyncio.to_thread(
            lambda: supa.table("judge_patterns")
                .select("*")
                .eq("kancelarija_id", kancelarija_id)
                .ilike("sudija_ime", f"%{sudija_ime}%")
                .limit(3)
                .execute()
        )
        mem_r = await asyncio.to_thread(
            lambda: supa.table("memory_entries")
                .select("tip, sadrzaj, vaznost, created_at")
                .eq("kancelarija_id", kancelarija_id)
                .ilike("entity_id", f"%{sudija_ime}%")
                .eq("entity_type", "sudija")
                .eq("aktivan", True)
                .order("vaznost")
                .limit(20)
                .execute()
        )
        return {
            "profil":   jp_r.data or [],
            "memorije": mem_r.data or [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sudija/sacuvaj")
@limiter.limit("20/minute")
async def sacuvaj_sudiju(
    request: Request,
    payload: SudijaSacuvajReq,
    user: dict = Depends(get_current_user),
):
    """Kreira ili ažurira profil sudije."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član kancelarije.")

    update: dict = {"updated_at": _now()}
    if payload.insistira_na  is not None: update["insistira_na"]    = payload.insistira_na
    if payload.odbija         is not None: update["odbija"]          = payload.odbija
    if payload.opis_ponasanja is not None: update["opis_ponasanja"]  = payload.opis_ponasanja[:1000]
    if payload.napomene       is not None: update["napomene"]        = payload.napomene[:500]
    if payload.oblast_prava   is not None: update["oblast_prava"]    = payload.oblast_prava
    if payload.sud            is not None: update["sud"]             = payload.sud

    try:
        existing = await asyncio.to_thread(
            lambda: supa.table("judge_patterns")
                .select("id, pobede, porazi, nagodbe")
                .eq("kancelarija_id", kancelarija_id)
                .eq("sudija_ime", payload.sudija_ime)
                .maybe_single()
                .execute()
        )
        if existing.data:
            eid = existing.data["id"]
            if payload.pobeda:  update["pobede"]  = (existing.data.get("pobede", 0) or 0) + 1
            if payload.poraz:   update["porazi"]  = (existing.data.get("porazi", 0) or 0) + 1
            if payload.nagodba: update["nagodbe"] = (existing.data.get("nagodbe", 0) or 0) + 1
            await asyncio.to_thread(
                lambda: supa.table("judge_patterns").update(update).eq("id", eid).execute()
            )
        else:
            update.update({
                "kancelarija_id": kancelarija_id,
                "sudija_ime":     payload.sudija_ime,
                "pobede":         1 if payload.pobeda  else 0,
                "porazi":         1 if payload.poraz   else 0,
                "nagodbe":        1 if payload.nagodba else 0,
            })
            await asyncio.to_thread(
                lambda: supa.table("judge_patterns").insert(update).execute()
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/klijent/{klijent_ime}")
@limiter.limit("30/minute")
async def get_klijent_profil(
    klijent_ime: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća profil klijenta — preferencije, stavovi, istorija odluka."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član kancelarije.")

    try:
        cm_r, mem_r = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("client_memory")
                    .select("*")
                    .eq("kancelarija_id", kancelarija_id)
                    .ilike("klijent_ime", f"%{klijent_ime}%")
                    .limit(1)
                    .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("memory_entries")
                    .select("tip, sadrzaj, vaznost, created_at")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("entity_type", "klijent")
                    .ilike("entity_id", f"%{klijent_ime}%")
                    .eq("aktivan", True)
                    .order("vaznost")
                    .limit(20)
                    .execute()
            ),
        )
        return {
            "profil":   (cm_r.data or [None])[0],
            "memorije": mem_r.data or [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/klijent/sacuvaj")
@limiter.limit("20/minute")
async def sacuvaj_klijenta(
    request: Request,
    payload: KlijentSacuvajReq,
    user: dict = Depends(get_current_user),
):
    """Kreira ili ažurira memoriju o klijentu."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član kancelarije.")

    update: dict = {"updated_at": _now()}
    if payload.prihvata_nagodbu  is not None: update["prihvata_nagodbu"]  = payload.prihvata_nagodbu
    if payload.preferira_brze    is not None: update["preferira_brze"]    = payload.preferira_brze
    if payload.komunikacija_tip  is not None: update["komunikacija_tip"]  = payload.komunikacija_tip
    if payload.rizik_profil      is not None: update["rizik_profil"]      = payload.rizik_profil
    if payload.napomene          is not None: update["napomene"]          = payload.napomene[:1000]
    if payload.klijent_id        is not None: update["klijent_id"]        = payload.klijent_id

    try:
        existing = await asyncio.to_thread(
            lambda: supa.table("client_memory")
                .select("id, kljucne_odluke")
                .eq("kancelarija_id", kancelarija_id)
                .eq("klijent_ime", payload.klijent_ime)
                .maybe_single()
                .execute()
        )
        if existing.data:
            eid = existing.data["id"]
            if payload.kljucna_odluka:
                prev = existing.data.get("kljucne_odluke") or []
                prev.append({"odluka": payload.kljucna_odluka, "datum": _now()[:10]})
                update["kljucne_odluke"] = prev[-20:]
            await asyncio.to_thread(
                lambda: supa.table("client_memory").update(update).eq("id", eid).execute()
            )
        else:
            update.update({
                "kancelarija_id": kancelarija_id,
                "klijent_ime":    payload.klijent_ime,
                "kljucne_odluke": [{"odluka": payload.kljucna_odluka, "datum": _now()[:10]}] if payload.kljucna_odluka else [],
            })
            await asyncio.to_thread(
                lambda: supa.table("client_memory").insert(update).execute()
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/partner/{partner_uid}")
@limiter.limit("30/minute")
async def get_partner_profil(
    partner_uid: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća profil partnera — stil pisanja, odbijene strategije, preferencije."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član kancelarije.")

    try:
        pp_r, mem_r = await asyncio.gather(
            asyncio.to_thread(
                lambda: supa.table("partner_profiles")
                    .select("*")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("partner_uid", partner_uid)
                    .maybe_single()
                    .execute()
            ),
            asyncio.to_thread(
                lambda: supa.table("memory_entries")
                    .select("tip, sadrzaj, vaznost, created_at")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("entity_type", "partner")
                    .eq("entity_id", partner_uid)
                    .eq("aktivan", True)
                    .limit(20)
                    .execute()
            ),
        )
        return {
            "profil":   pp_r.data,
            "memorije": mem_r.data or [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{memorija_id}")
@limiter.limit("30/minute")
async def obrisi_memoriju(
    memorija_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Deaktivira memoriju (soft delete — ostaje u bazi, aktivan=FALSE)."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("memory_entries")
                .update({"aktivan": False, "updated_at": _now()})
                .eq("id", memorija_id)
                .eq("kancelarija_id", kancelarija_id)
                .execute()
        )
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Memorija nije pronađena.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sve")
@limiter.limit("20/minute")
async def sve_memorije(
    request: Request,
    user: dict = Depends(get_current_user),
    entity_type: Optional[str] = None,
    limit: int = 50,
):
    """Sve aktivne memorije firme — za pregled i upravljanje."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        return {"memorije": [], "ukupno": 0}

    try:
        qb = (supa.table("memory_entries")
              .select("*")
              .eq("kancelarija_id", kancelarija_id)
              .eq("aktivan", True))
        if entity_type:
            qb = qb.eq("entity_type", entity_type)

        r = await asyncio.to_thread(
            lambda: qb.order("vaznost").order("created_at", desc=True).limit(min(limit, 200)).execute()
        )
        memorije = r.data or []

        by_type: dict[str, int] = {}
        for m in memorije:
            t = m.get("entity_type", "ostalo")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "memorije":  memorije,
            "ukupno":    len(memorije),
            "by_type":   by_type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
