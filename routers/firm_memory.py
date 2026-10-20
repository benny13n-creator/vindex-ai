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
  GET  /api/firma-memorija/klijent/{klijent_id} — profil SOPSTVENOG klijenta (NS4 O2: identitet, ne ime)
  POST /api/firma-memorija/klijent/sacuvaj    — ažuriraj profil sopstvenog klijenta (obavezan klijent_id)
  GET  /api/firma-memorija/partner/{uid}      — profil partnera
  DELETE /api/firma-memorija/{id}             — ukloni memoriju
  GET  /api/firma-memorija/sve               — sve aktivne memorije firme
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.kancelarija_utils import get_kancelarija_id as _get_kancelarija_id
from shared.rate import limiter

logger = logging.getLogger("vindex.firm_memory")
router = APIRouter(prefix="/api/firma-memorija", tags=["firma-memorija"])

_ENTITY_TYPES = {"partner", "klijent", "sudija", "firma", "predmet"}
_MEMORY_TIPS  = {"preferencija", "odbijanje", "obrazac", "napomena"}
_VAZNOSTI     = {"visoka", "normalna", "niska"}
# Program Phoenix, Mission 003 (LIVINGSYS-DEBT-008): every .order("vaznost") call site below
# used Supabase's default ascending sort -- alphabetically "niska" < "normalna" < "visoka", so
# LOW-importance memories sorted BEFORE high-importance ones. Combined with each query's own
# .limit(), a firm with more memories than the limit could have its most important entries
# (a judge/client "NIKAD prihvata nagodbu"-type fact) silently pushed out while low-importance
# ones survived -- backwards from intent, worst at /kontekst-za-ai (fed directly into the AI
# system prompt). Fixed to .order("vaznost", desc=True) at all 5 call sites.


# ─── Helpers ─────────────────────────────────────────────────────────────────
# _get_kancelarija_id je konsolidovano u shared/kancelarija_utils.py
# (2026-07-26) -- v. import iznad. Alias zadržan da se ne menja svaki
# poziv u ovom fajlu.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# RH001: članstvo u kancelariji NIJE pristup predmetu. Beleška vezana za predmet/klijenta vidi se samo uz kanonsku
# autorizaciju (`shared/memorija_vidljivost` — isti vlasnik pravila kao NS008 Law Brain). Filtrira se PRE limita
# rute (iz ograničenog većeg skupa), da ni broj vidljivih stavki ne zavisi od tuđih skrivenih beleški.
_SKUP_ZA_FILTER = 1000


def _vidljive(supa, uid: str, redovi: list) -> list:
    from shared.memorija_vidljivost import vidljive_beleske
    return vidljive_beleske(supa, uid, redovi)


async def _vidljiv_red_ili_404(supa, uid: str, kancelarija_id, memorija_id: str, kolone: str) -> dict:
    """Red memorije koji korisnik SME da vidi; tuđ predmetni/klijentski red = isti 404 kao nepostojeći."""
    r = await asyncio.to_thread(
        lambda: supa.table("memory_entries").select(kolone + ", entity_type, entity_id")
            .eq("id", memorija_id).eq("kancelarija_id", kancelarija_id).eq("aktivan", True)
            .maybe_single().execute())
    red = getattr(r, "data", None)
    if not red or not await asyncio.to_thread(_vidljive, supa, uid, [red]):
        raise HTTPException(status_code=404, detail="Memorija nije pronađena.")
    return red


# NS4 O2: profil klijenta (`client_memory`) je bio vezan za IME klijenta u kancelariji — kolega je čitao i menjao
# profil tuđeg klijenta (`ilike` po imenu), a dva klijenta istog imena delila su profil. Članstvo u kancelariji
# NIJE pristup klijentu: profil je vezan za IDENTITET klijenta (`klijenti.id`) i vidi ga/menja samo VLASNIK tog
# klijenta (`klijenti.user_id`) — isto pravilo kao za klijentske beleške (`shared/memorija_vidljivost`). Ime nije
# akreditiv i ne učestvuje u autorizaciji.
#
# Ključ reda: `client_memory.klijent_ime` = "klijent:<uuid>". Postojeće ograničenje UNIQUE(kancelarija_id,
# klijent_ime) (046) time postaje jedinstvenost po IDENTITETU klijenta — bez migracije, bez sudara istoimenih
# klijenata (ranije: tuđi istoimeni profil → greška upisa koja odaje njegovo postojanje). Redovi bez tog ključa
# (stari, vezani za ime; produkcija 2026-10-19: 0 redova) se NE služe i NE spajaju — nema dokazanog identiteta.
_CM_PREFIKS = "klijent:"


def _cm_kljuc(klijent_id: str) -> str:
    return _CM_PREFIKS + klijent_id


def _kanonski_uuid(v) -> Optional[str]:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError, AttributeError):
        return None


async def _moj_klijent(supa, uid: str, ref) -> Optional[str]:
    """Kanonski id klijenta SAMO ako je `ref` UUID klijenta čiji je vlasnik `uid` i nije obrisan; inače None.
    Nepostojeći, tuđ, obrisan i neispravan identitet daju ISTI ishod (bez proročišta). Greška baze se PROPUŠTA —
    pozivalac vraća grešku, nikad „prikaži"."""
    kid = _kanonski_uuid(ref)
    if not kid:
        return None
    r = await asyncio.to_thread(
        lambda: supa.table("klijenti").select("id,user_id,deleted_at")
            .eq("id", kid).eq("user_id", uid).limit(1).execute())
    red = (getattr(r, "data", None) or [None])[0]
    if not red or str(red.get("id")) != kid or str(red.get("user_id") or "") != str(uid) or red.get("deleted_at"):
        return None
    return kid


async def _profil_klijenta(supa, kancelarija_id, klijent_id: str, kolone: str) -> Optional[dict]:
    r = await asyncio.to_thread(
        lambda: supa.table("client_memory").select(kolone)
            .eq("kancelarija_id", kancelarija_id).eq("klijent_id", klijent_id)
            .eq("klijent_ime", _cm_kljuc(klijent_id)).limit(1).execute())
    return (getattr(r, "data", None) or [None])[0]


def _apply_trust(memorije: list[dict], supa, kancelarija_id: str) -> list[dict]:
    """
    Annotates memory entries with trust metadata and auto-marks expired ones.
    Runs synchronously after fetch; DB update for zastarela is fire-and-forget.
    """
    today = date.today()
    expired_ids: list[str] = []
    result: list[dict] = []

    for m in memorije:
        confidence = float(m.get("confidence") or 1.0)
        zastarela  = bool(m.get("zastarela") or False)
        expires_at = m.get("expires_at")

        if expires_at and not zastarela:
            try:
                exp = date.fromisoformat(str(expires_at)[:10])
                if exp < today:
                    zastarela = True
                    expired_ids.append(m["id"])
            except Exception:
                pass

        m["_trust"] = {
            "confidence":    confidence,
            "izvor":         m.get("izvor", "manual"),
            "potvrde_count": m.get("potvrde_count", 1),
            "zastarela":     zastarela,
            "expires_at":    expires_at,
            "upozorenje":    (
                "Memorija je istekla — proverite da li je još uvek tačna."
                if zastarela else
                "Nizak nivo pouzdanosti — preporučuje se ručna potvrda."
                if confidence < 0.5 else None
            ),
        }
        result.append(m)

    if expired_ids:
        try:
            supa.table("memory_entries").update(
                {"zastarela": True, "updated_at": _now()}
            ).in_("id", expired_ids).execute()
        except Exception:
            pass

    return result


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
    # NS4 O2: identitet je `klijent_id` (klijent čiji je vlasnik pozivalac); ime se ne koristi za autorizaciju
    # ni za izbor reda (zadržano u ugovoru radi kompatibilnosti starih klijenata).
    klijent_ime:       Optional[str] = None
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

    # CONF-011 (BETA-DATA-CONFIDENTIALITY-002): `entity_id` je stizao iz tela
    # neproveren, pa je zapis o TUDJEM predmetu/klijentu ulazio u memoriju koju
    # cela kancelarija cita -- i odatle u AI kontekst kolega. Provera se odnosi
    # samo na tipove koji su stvarni resursi u bazi; `sudija`/`firma`/`partner`
    # su slobodan tekst i nemaju vlasnika.
    _TABELA_ZA_TIP = {"predmet": "predmeti", "klijent": "klijenti"}
    _tabela = _TABELA_ZA_TIP.get(payload.entity_type)
    if _tabela:
        from shared.ownership import zahtevaj as _zahtevaj_vlasnistvo
        await asyncio.to_thread(
            _zahtevaj_vlasnistvo, supa, _tabela, payload.entity_id, uid
        )

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
            lambda: qb.order("vaznost", desc=True).order("created_at", desc=True).limit(_SKUP_ZA_FILTER).execute()
        )
        memorije = (await asyncio.to_thread(_vidljive, supa, uid, r.data or []))[:min(limit, 100)]

        # Lokalno filtriranje po q (case-insensitive, srpski)
        if q:
            q_l = q.lower()
            memorije = [
                m for m in memorije
                if q_l in (m.get("sadrzaj", "") + m.get("entity_name", "")).lower()
            ]

        memorije = _apply_trust(memorije, _get_supa(), kancelarija_id)

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
    klijent_id: Optional[str] = None,
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
                    .select("tip, sadrzaj, vaznost, entity_type, entity_id")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("entity_id", entity_id)
                    .eq("entity_type", entity_type)
                    .eq("aktivan", True)
                    .order("vaznost", desc=True)
                    .limit(_SKUP_ZA_FILTER)
                    .execute()
            )
            # select bez entity_id/entity_type ne bi mogao da se proveri → čitaju se uz sadržaj
            return (await asyncio.to_thread(_vidljive, supa, uid, r.data or []))[:10]
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

    # NS4 O2: klijentski deo samo za SOPSTVENOG klijenta po identitetu (`klijent_id`); samo ime ne daje ništa.
    # Greška provere vlasništva → klijentski deo se izostavlja (zatvoreno), nikad tuđi profil u promptu.
    kid = None
    if klijent_id:
        try:
            kid = await _moj_klijent(supa, uid, klijent_id)
        except Exception:
            kid = None
    if kid:
        oznaka = (klijent_ime or "").strip()[:120]
        mem = await _fetch_memorije(kid, "klijent")
        if mem:
            memorije_count += len(mem)
            delovi.append(f"MEMORIJA O KLIJENTU {oznaka.upper()}:" if oznaka else "MEMORIJA O KLIJENTU:")
            for m in mem:
                delovi.append(f"  [{m['tip'].upper()}] {m['sadrzaj']}")

        try:
            cm = await _profil_klijenta(supa, kancelarija_id, kid,
                                        "prihvata_nagodbu, preferira_brze, rizik_profil, napomene")
            if cm:
                memorije_count += 1
                ko = f"Klijent {oznaka}" if oznaka else "Klijent"
                if cm.get("prihvata_nagodbu") is False:
                    delovi.append(f"  VAZNO: {ko} NIKAD ne prihvata nagodbu.")
                elif cm.get("prihvata_nagodbu") is True:
                    delovi.append(f"  {ko} otvoren za nagodbu.")
                if cm.get("rizik_profil") == "visok":
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
                .order("vaznost", desc=True)
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


@router.get("/klijent/{klijent_ref}")
@limiter.limit("30/minute")
async def get_klijent_profil(
    klijent_ref: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Profil SOPSTVENOG klijenta po identitetu (`klijenti.id`). Tuđ, nepostojeći, obrisan klijent ili ime umesto
    identiteta → isti prazan odgovor kao klijent bez profila (NS4 O2 — bez proročišta postojanja)."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član kancelarije.")

    try:
        kid = await _moj_klijent(supa, uid, klijent_ref)
        if not kid:
            return {"profil": None, "memorije": []}
        profil, mem_r = await asyncio.gather(
            _profil_klijenta(supa, kancelarija_id, kid, "*"),
            asyncio.to_thread(
                lambda: supa.table("memory_entries")
                    .select("tip, sadrzaj, vaznost, created_at, entity_type, entity_id")
                    .eq("kancelarija_id", kancelarija_id)
                    .eq("entity_type", "klijent")
                    .eq("entity_id", kid)
                    .eq("aktivan", True)
                    .order("vaznost", desc=True)
                    .limit(_SKUP_ZA_FILTER)
                    .execute()
            ),
        )
        return {
            "profil":   profil,
            "memorije": (await asyncio.to_thread(_vidljive, supa, uid, mem_r.data or []))[:20],
        }
    except Exception as e:
        logger.warning("[FIRM_MEMORY] profil klijenta nije dostupan: %s", type(e).__name__)
        raise HTTPException(status_code=503, detail="Profil klijenta trenutno nije dostupan.")


@router.post("/klijent/sacuvaj")
@limiter.limit("20/minute")
async def sacuvaj_klijenta(
    request: Request,
    payload: KlijentSacuvajReq,
    user: dict = Depends(get_current_user),
):
    """Kreira ili ažurira profil SOPSTVENOG klijenta (NS4 O2: obavezan `klijent_id` klijenta čiji je pozivalac
    vlasnik; tuđ ili nepostojeći identitet → isti 404, bez upisa)."""
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=400, detail="Niste član kancelarije.")
    if not payload.klijent_id:
        raise HTTPException(status_code=422, detail="Profil klijenta zahteva identitet klijenta (klijent_id).")

    update: dict = {"updated_at": _now()}
    if payload.prihvata_nagodbu  is not None: update["prihvata_nagodbu"]  = payload.prihvata_nagodbu
    if payload.preferira_brze    is not None: update["preferira_brze"]    = payload.preferira_brze
    if payload.komunikacija_tip  is not None: update["komunikacija_tip"]  = payload.komunikacija_tip
    if payload.rizik_profil      is not None: update["rizik_profil"]      = payload.rizik_profil
    if payload.napomene          is not None: update["napomene"]          = payload.napomene[:1000]

    try:
        kid = await _moj_klijent(supa, uid, payload.klijent_id)
    except Exception as e:
        logger.warning("[FIRM_MEMORY] provera vlasništva klijenta nije uspela: %s", type(e).__name__)
        raise HTTPException(status_code=503, detail="Profil klijenta trenutno nije moguće sačuvati.")
    if not kid:
        raise HTTPException(status_code=404, detail="Klijent nije pronađen.")

    async def _azuriraj(postojeci: dict):
        polja = dict(update)
        if payload.kljucna_odluka:
            prev = list(postojeci.get("kljucne_odluke") or [])
            prev.append({"odluka": payload.kljucna_odluka, "datum": _now()[:10]})
            polja["kljucne_odluke"] = prev[-20:]
        await asyncio.to_thread(
            lambda: supa.table("client_memory").update(polja)
                .eq("id", postojeci["id"]).eq("kancelarija_id", kancelarija_id).eq("klijent_id", kid).execute())

    postojeci = await _profil_klijenta(supa, kancelarija_id, kid, "id, kljucne_odluke")
    if postojeci:
        await _azuriraj(postojeci)
        return {"ok": True}
    novi = {**update, "kancelarija_id": kancelarija_id, "klijent_id": kid, "klijent_ime": _cm_kljuc(kid),
            "kljucne_odluke": ([{"odluka": payload.kljucna_odluka, "datum": _now()[:10]}]
                               if payload.kljucna_odluka else [])}
    try:
        await asyncio.to_thread(lambda: supa.table("client_memory").insert(novi).execute())
    except Exception as e:
        # Istovremeni prvi upis istog klijenta: UNIQUE(kancelarija_id, klijent_ime) = jedinstvenost po identitetu.
        # Pobednikov red se ažurira; svaka druga greška se prijavljuje (bez detalja baze).
        if "23505" not in str(e):
            raise
        postojeci = await _profil_klijenta(supa, kancelarija_id, kid, "id, kljucne_odluke")
        if not postojeci:
            raise
        await _azuriraj(postojeci)
    return {"ok": True}


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
        await _vidljiv_red_ili_404(supa, uid, kancelarija_id, memorija_id, "id")
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
            lambda: qb.order("vaznost", desc=True).order("created_at", desc=True).limit(_SKUP_ZA_FILTER).execute()
        )
        vidljive = (await asyncio.to_thread(_vidljive, supa, uid, r.data or []))[:min(limit, 200)]
        memorije = _apply_trust(vidljive, _get_supa(), kancelarija_id)

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


@router.post("/potvrdi/{memorija_id}")
@limiter.limit("30/minute")
async def potvrdi_memoriju(
    memorija_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Partner potvrđuje da je memorija tačna i aktuelna.
    Svaka potvrda povećava potvrde_count; 3+ potvrde boostuju confidence za 0.2.
    """
    uid  = user["user_id"]
    supa = _get_supa()
    kancelarija_id = await _get_kancelarija_id(supa, uid)
    if not kancelarija_id:
        raise HTTPException(status_code=403, detail="Niste član nijedne kancelarije.")

    try:
        entry = await _vidljiv_red_ili_404(supa, uid, kancelarija_id, memorija_id,
                                           "id, confidence, potvrde_count, potvrdjeno_od, zastarela")
        potvrdjeno_od: list = list(entry.get("potvrdjeno_od") or [])
        potvrde_count: int  = int(entry.get("potvrde_count") or 0)
        confidence:   float = float(entry.get("confidence") or 1.0)

        if uid not in potvrdjeno_od:
            potvrdjeno_od.append(uid)
            potvrde_count += 1

        # 3+ unique confirmations boost confidence
        if potvrde_count >= 3:
            confidence = min(1.0, confidence + 0.2)

        await asyncio.to_thread(
            lambda: supa.table("memory_entries").update({
                "potvrde_count": potvrde_count,
                "potvrdjeno_od": potvrdjeno_od,
                "confidence":    round(confidence, 2),
                "zastarela":     False,
                "updated_at":    _now(),
            }).eq("id", memorija_id).execute()
        )

        return {
            "ok":            True,
            "potvrde_count": potvrde_count,
            "confidence":    round(confidence, 2),
            "poruka":        f"Potvrđeno. Pouzdanost memorije: {round(confidence * 100)}%.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
