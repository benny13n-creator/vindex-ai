# -*- coding: utf-8 -*-
"""
Vindex AI — routers/zadaci.py

Team Task Assignment — dodela zadataka u okviru kancelarije.

Šta radi:
  - Partner kreira zadatak i dodeljuje ga članu tima
  - Svaki zadatak je vezan za predmet (opciono)
  - Notifikacija dodelje_nom članu (proactive_alerts)
  - Status tracking: otvoreno → u_toku → zavrseno
  - Dashboard: moji zadaci, zadaci tima, prekoračeni rokovi

Endpoints:
  POST   /api/zadaci/kreiraj            — kreiraj i dodeli zadatak
  GET    /api/zadaci/moji               — zadaci dodeljeni meni
  GET    /api/zadaci/tim                — svi zadaci kancelarije (partner/admin)
  PATCH  /api/zadaci/{id}/status        — ažuriraj status
  PATCH  /api/zadaci/{id}/dodeli        — redodeli zadatak
  DELETE /api/zadaci/{id}               — obriši (samo kreator ili admin)
  GET    /api/zadaci/predmet/{id}       — zadaci vezani za predmet
  GET    /api/zadaci/statistika         — dashboard statistika
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.zadaci")
router = APIRouter(prefix="/api/zadaci", tags=["zadaci"])

_VALIDNI_STATUSI  = {"otvoreno", "u_toku", "ceka", "zavrseno", "otkazano"}
_VALIDNI_PRIORITETI = {"hitno", "visoko", "normalan", "nisko"}


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class ZadatakRequest(BaseModel):
    naziv:          str = Field(..., min_length=2, max_length=200)
    opis:           Optional[str] = None
    prioritet:      str = Field("normalan")
    rok_datum:      Optional[str] = None
    predmet_id:     Optional[str] = None
    dodeljen_uid:   Optional[str] = None  # user_id kome se dodeljuje


class StatusUpdate(BaseModel):
    status:   str
    komentar: Optional[str] = None


class DodeljivanjeUpdate(BaseModel):
    dodeljen_uid: str


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_firma_info(supa, uid: str) -> dict:
    """Vraća {kancelarija_id, uloga, is_admin} za korisnika."""
    try:
        # Provjeri da li je admin firme
        admin_r = await asyncio.to_thread(
            lambda: supa.table("kancelarije")
                .select("id")
                .eq("admin_uid", uid)
                .maybe_single()
                .execute()
        )
        if admin_r.data:
            return {"kancelarija_id": admin_r.data["id"], "uloga": "admin", "is_admin": True}

        # Inače — član
        clan_r = await asyncio.to_thread(
            lambda: supa.table("kancelarija_clanovi")
                .select("kancelarija_id, uloga")
                .eq("user_id", uid)
                .eq("status", "aktivan")
                .maybe_single()
                .execute()
        )
        if clan_r.data:
            uloga = clan_r.data.get("uloga", "saradnik")
            return {
                "kancelarija_id": clan_r.data["kancelarija_id"],
                "uloga": uloga,
                "is_admin": uloga in ("admin", "partner"),
            }
    except Exception as e:
        logger.debug("[ZADACI] get_firma_info greška: %s", e)

    return {"kancelarija_id": None, "uloga": None, "is_admin": False}


async def _posalji_notifikaciju(supa, dodeljen_uid: str, naziv: str, kreirao: str, prioritet: str) -> None:
    """Kreira proactive_alert za dodelje_nog člana."""
    try:
        urgentnost = "hitna" if prioritet == "hitno" else ("visoka" if prioritet == "visoko" else "normalna")
        await asyncio.to_thread(
            lambda: supa.table("proactive_alerts").insert({
                "user_id":    dodeljen_uid,
                "tip":        "novi_zadatak",
                "naslov":     f"Novi zadatak: {naziv[:60]}",
                "opis":       f"Zadatak [{prioritet.upper()}] dodelio/la vam je kolega/ica.",
                "urgentnost": urgentnost,
                "procitana":  False,
            }).execute()
        )
    except Exception as e:
        logger.debug("[ZADACI] notifikacija greška: %s", e)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/kreiraj")
@limiter.limit("30/minute")
async def kreiraj_zadatak(
    request: Request,
    payload: ZadatakRequest,
    user: dict = Depends(get_current_user),
):
    """Kreira zadatak i dodeljuje ga članu tima."""
    uid  = user["user_id"]
    supa = _get_supa()

    if payload.prioritet not in _VALIDNI_PRIORITETI:
        raise HTTPException(status_code=400, detail=f"Prioritet mora biti: {', '.join(_VALIDNI_PRIORITETI)}")

    firma = await _get_firma_info(supa, uid)
    kancelarija_id = firma.get("kancelarija_id")

    # Validacija datuma
    rok_datum = None
    if payload.rok_datum:
        try:
            rok_datum = date.fromisoformat(payload.rok_datum).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="Neispravan format datuma (YYYY-MM-DD).")

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci").insert({
                "kancelarija_id": kancelarija_id,
                "predmet_id":     payload.predmet_id,
                "kreirao_uid":    uid,
                "dodeljen_uid":   payload.dodeljen_uid,
                "naziv":          payload.naziv,
                "opis":           payload.opis or "",
                "prioritet":      payload.prioritet,
                "status":         "otvoreno",
                "rok_datum":      rok_datum,
            }).execute()
        )
        zadatak = r.data[0] if r.data else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Greška pri kreiranju: {e}")

    # Notifikacija
    if payload.dodeljen_uid and payload.dodeljen_uid != uid:
        asyncio.create_task(
            _posalji_notifikaciju(supa, payload.dodeljen_uid, payload.naziv, uid, payload.prioritet)
        )

    return {"ok": True, "zadatak": zadatak}


@router.get("/moji")
@limiter.limit("30/minute")
async def moji_zadaci(
    request: Request,
    user: dict = Depends(get_current_user),
    status_filter: Optional[str] = None,
):
    """Zadaci dodeljeni trenutnom korisniku."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        q = (
            supa.table("zadaci")
            .select("*, predmeti(naziv)")
            .eq("dodeljen_uid", uid)
        )
        if status_filter and status_filter in _VALIDNI_STATUSI:
            q = q.eq("status", status_filter)
        else:
            q = q.not_.in_("status", ["zavrseno", "otkazano"])

        r = await asyncio.to_thread(
            lambda: q.order("prioritet").order("rok_datum").limit(100).execute()
        )
        zadaci = r.data or []

        hitni   = sum(1 for z in zadaci if z.get("prioritet") == "hitno")
        prekoraceni = sum(
            1 for z in zadaci
            if z.get("rok_datum") and z["rok_datum"] < date.today().isoformat()
            and z.get("status") not in ("zavrseno", "otkazano")
        )

        return {
            "zadaci":       zadaci,
            "ukupno":       len(zadaci),
            "hitnih":       hitni,
            "prekoracenih": prekoraceni,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tim")
@limiter.limit("20/minute")
async def zadaci_tima(
    request: Request,
    user: dict = Depends(get_current_user),
    samo_otvoreni: bool = True,
):
    """Svi zadaci kancelarije (vidljivo svim članovima, ne samo adminu)."""
    uid  = user["user_id"]
    supa = _get_supa()

    firma = await _get_firma_info(supa, uid)
    kancelarija_id = firma.get("kancelarija_id")
    if not kancelarija_id:
        return {"zadaci": [], "ukupno": 0, "poruka": "Niste član nijedne kancelarije."}

    try:
        q = supa.table("zadaci").select("*").eq("kancelarija_id", kancelarija_id)
        if samo_otvoreni:
            q = q.not_.in_("status", ["zavrseno", "otkazano"])

        r = await asyncio.to_thread(
            lambda: q.order("prioritet").order("rok_datum", desc=False).limit(200).execute()
        )
        zadaci = r.data or []

        by_status: dict[str, int] = {}
        for z in zadaci:
            s = z.get("status", "otvoreno")
            by_status[s] = by_status.get(s, 0) + 1

        return {
            "zadaci":    zadaci,
            "ukupno":    len(zadaci),
            "by_status": by_status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{zadatak_id}/status")
@limiter.limit("60/minute")
async def azuriraj_status(
    zadatak_id: str,
    request: Request,
    payload: StatusUpdate,
    user: dict = Depends(get_current_user),
):
    """Ažurira status zadatka."""
    uid  = user["user_id"]
    supa = _get_supa()

    if payload.status not in _VALIDNI_STATUSI:
        raise HTTPException(status_code=400, detail=f"Status mora biti: {', '.join(_VALIDNI_STATUSI)}")

    update_data: dict = {
        "status":     payload.status,
        "updated_at": _now_iso(),
    }
    if payload.komentar:
        update_data["komentar"] = payload.komentar[:500]
    if payload.status == "zavrseno":
        update_data["zavrseno_u"] = _now_iso()

    try:
        # Provera vlasništva (dodeljen ili kreirao)
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci")
                .update(update_data)
                .eq("id", zadatak_id)
                .or_(f"dodeljen_uid.eq.{uid},kreirao_uid.eq.{uid}")
                .execute()
        )
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Zadatak nije pronađen ili nemate pristup.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "novi_status": payload.status}


@router.patch("/{zadatak_id}/dodeli")
@limiter.limit("30/minute")
async def redodeli_zadatak(
    zadatak_id: str,
    request: Request,
    payload: DodeljivanjeUpdate,
    user: dict = Depends(get_current_user),
):
    """Redodeli zadatak drugom članu tima (partner/admin ili kreator)."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci")
                .update({
                    "dodeljen_uid": payload.dodeljen_uid,
                    "updated_at":   _now_iso(),
                })
                .eq("id", zadatak_id)
                .eq("kreirao_uid", uid)
                .execute()
        )
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Zadatak nije pronađen ili nemate pravo redodele.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True, "dodeljen_uid": payload.dodeljen_uid}


@router.delete("/{zadatak_id}")
@limiter.limit("20/minute")
async def obrisi_zadatak(
    zadatak_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Briše zadatak (samo kreator ili admin kancelarije)."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await _get_firma_info(supa, uid)

    try:
        if firma.get("is_admin"):
            q = supa.table("zadaci").delete().eq("id", zadatak_id)
        else:
            q = supa.table("zadaci").delete().eq("id", zadatak_id).eq("kreirao_uid", uid)

        r = await asyncio.to_thread(lambda: q.execute())
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Zadatak nije pronađen ili nemate pravo brisanja.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True}


@router.get("/predmet/{predmet_id}")
@limiter.limit("30/minute")
async def zadaci_za_predmet(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Svi zadaci vezani za dati predmet."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("zadaci")
                .select("*")
                .eq("predmet_id", predmet_id)
                .order("prioritet")
                .limit(50)
                .execute()
        )
        return {"zadaci": r.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistika")
@limiter.limit("20/minute")
async def zadaci_statistika(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dashboard statistika zadataka za korisnika i tim."""
    uid  = user["user_id"]
    supa = _get_supa()
    danas = date.today().isoformat()
    firma = await _get_firma_info(supa, uid)
    kancelarija_id = firma.get("kancelarija_id")

    moji_r, tim_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("zadaci")
                .select("status, prioritet, rok_datum")
                .eq("dodeljen_uid", uid)
                .not_.in_("status", ["zavrseno", "otkazano"])
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("zadaci")
                .select("status, prioritet, rok_datum, dodeljen_uid")
                .eq("kancelarija_id", kancelarija_id)
                .not_.in_("status", ["zavrseno", "otkazano"])
                .execute()
        ) if kancelarija_id else asyncio.coroutine(lambda: type('obj', (object,), {'data': []})())(),
    )

    moji   = moji_r.data or []
    timski = tim_r.data  if not isinstance(tim_r, Exception) else []
    if hasattr(timski, 'data'):
        timski = timski.data or []

    return {
        "moji_zadaci": {
            "ukupno":       len(moji),
            "hitnih":       sum(1 for z in moji if z.get("prioritet") == "hitno"),
            "prekoracenih": sum(1 for z in moji if z.get("rok_datum", "9999") < danas),
        },
        "tim_zadaci": {
            "ukupno":       len(timski),
            "hitnih":       sum(1 for z in timski if z.get("prioritet") == "hitno"),
            "prekoracenih": sum(1 for z in timski if z.get("rok_datum", "9999") < danas),
        } if kancelarija_id else None,
    }


@router.post("/ai-analiziraj/{predmet_id}")
@limiter.limit("10/hour")
async def ai_analiziraj_predmet(
    predmet_id: str,
    request: Request,
    user: dict = Depends(PermissionService.require("zadaci_ai")),
):
    """
    AI analizira predmet i automatski kreira zadatke za nedostajuće stavke.

    Šta proverava:
      - Nedostaje li punomoć
      - Da li su rokovi prekoračeni ili bliže ističu
      - Da li nedostaju ključni dokumenti (tužba, odgovor, žalba)
      - Da li postoje neplaćene billing stavke starije od 30 dana
      - Da li predmet nema aktivnost duže od 14 dana

    Svaki problem → automatski kreiran zadatak sa odgovarajućim prioritetom.
    """
    uid  = user["user_id"]
    supa = _get_supa()
    danas = date.today().isoformat()

    # Dohvati predmet
    try:
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("*")
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        if not pred_r.data:
            raise HTTPException(status_code=404, detail="Predmet nije pronađen.")
        predmet = pred_r.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Dohvati relevantne podatke paralelno
    docs_r, billing_r, zadaci_r, rokovi_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("naziv_fajla, status, created_at")
                .eq("predmet_id", predmet_id)
                .limit(30)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("billing_entries")
                .select("iznos_rsd, obracunato, datum")
                .eq("predmet_id", predmet_id)
                .eq("obracunato", False)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("zadaci")
                .select("naziv, status")
                .eq("predmet_id", predmet_id)
                .not_.in_("status", ["zavrseno", "otkazano"])
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rokovi")
                .select("naziv, datum, status")
                .eq("predmet_id", predmet_id)
                .gte("datum", danas)
                .order("datum")
                .limit(5)
                .execute()
        ),
        return_exceptions=True,
    )

    docs     = (docs_r.data    if not isinstance(docs_r, Exception)    else []) or []
    billing  = (billing_r.data if not isinstance(billing_r, Exception) else []) or []
    zadaci   = (zadaci_r.data  if not isinstance(zadaci_r, Exception)  else []) or []
    rokovi   = (rokovi_r.data  if not isinstance(rokovi_r, Exception)  else []) or []

    # Pripremi kontekst za AI
    naziv_predmeta = predmet.get("naziv", "predmet")
    tip_predmeta   = predmet.get("tip", "")
    status_pred    = predmet.get("status", "")
    poslednja_akt  = predmet.get("updated_at", predmet.get("created_at", ""))[:10]

    dana_neaktivnosti = 0
    if poslednja_akt:
        try:
            d0 = date.fromisoformat(poslednja_akt)
            dana_neaktivnosti = (date.today() - d0).days
        except Exception:
            pass

    nefakturisano_rsd = sum(float(b.get("iznos_rsd", 0) or 0) for b in billing)
    doc_nazivi = [d.get("naziv_fajla", "") for d in docs]
    zadaci_aktivni = [z.get("naziv", "") for z in zadaci]

    kontekst = (
        f"Predmet: {naziv_predmeta}\n"
        f"Tip: {tip_predmeta}\n"
        f"Status: {status_pred}\n"
        f"Neaktivan: {dana_neaktivnosti} dana\n"
        f"Dokumenti: {', '.join(doc_nazivi[:10]) or 'nema'}\n"
        f"Nefakturisano: {nefakturisano_rsd:,.0f} RSD\n"
        f"Aktivni zadaci: {', '.join(zadaci_aktivni[:5]) or 'nema'}\n"
        f"Nadolazeći rokovi: {', '.join(r.get('naziv','') + ' ' + r.get('datum','') for r in rokovi[:3]) or 'nema'}\n"
    )

    # AI analiza
    try:
        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": (
                    "Ti si asistent advokatske kancelarije. Analiziraj sledeći predmet i identifikuj "
                    "konkretne zadatke koji nedostaju ili su hitni.\n\n"
                    + kontekst
                    + "\n\nVrati SAMO JSON listu zadataka koji treba kreirati:\n"
                    '[{"naziv": "...", "opis": "...", "prioritet": "hitno|visoko|normalan|nisko"}]\n\n'
                    "Pravila:\n"
                    "- Ako nema punomoćja → zadatak 'Pribaviti punomoćje' (prioritet: visoko)\n"
                    "- Ako je predmet neaktivan >14 dana → zadatak 'Proveriti status predmeta' (normalan)\n"
                    "- Ako ima nefakturisanog >50000 RSD → zadatak 'Fakturisati nenaplaćene stavke' (visoko)\n"
                    "- Ako nema dokumenata → zadatak 'Uneti dokumenta u predmet' (normalan)\n"
                    "- Max 5 zadataka. Ekavica. Samo konkretni, akcioni zadaci."
                )
            }],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "[]"
        parsed = json.loads(raw)
        ai_zadaci = parsed if isinstance(parsed, list) else parsed.get("zadaci", [])
    except Exception as e:
        logger.warning("[ZADACI_AI] AI analiza nije uspela: %s", e)
        # Fallback: heuristički zadaci
        ai_zadaci = []
        if dana_neaktivnosti > 14:
            ai_zadaci.append({"naziv": "Proveriti status predmeta", "opis": f"Predmet je neaktivan {dana_neaktivnosti} dana.", "prioritet": "normalan"})
        if nefakturisano_rsd > 50000:
            ai_zadaci.append({"naziv": "Fakturisati nenaplaćene stavke", "opis": f"Nefakturisano: {nefakturisano_rsd:,.0f} RSD", "prioritet": "visoko"})
        if not docs:
            ai_zadaci.append({"naziv": "Uneti dokumenta u predmet", "opis": "Predmet nema priloženih dokumenata.", "prioritet": "normalan"})

    await UsageService.consume(uid, user.get("email", ""), "zadaci_ai")

    if not ai_zadaci:
        return {"ok": True, "kreirano": 0, "poruka": "Predmet je uredan — nema kritičnih zadataka.", "zadaci": []}

    # Kreiraj zadatke u bazi
    firma = await _get_firma_info(supa, uid)
    kancelarija_id = firma.get("kancelarija_id")
    kreirani = []

    for z in ai_zadaci[:5]:
        naziv = str(z.get("naziv", ""))[:200]
        if not naziv:
            continue
        prioritet = z.get("prioritet", "normalan")
        if prioritet not in _VALIDNI_PRIORITETI:
            prioritet = "normalan"
        try:
            r = await asyncio.to_thread(
                lambda n=naziv, p=prioritet, o=z.get("opis", ""): supa.table("zadaci").insert({
                    "kancelarija_id": kancelarija_id,
                    "predmet_id":     predmet_id,
                    "kreirao_uid":    "ai_system",
                    "dodeljen_uid":   uid,
                    "naziv":          n,
                    "opis":           o[:500],
                    "prioritet":      p,
                    "status":         "otvoreno",
                }).execute()
            )
            if r.data:
                kreirani.append(r.data[0])
        except Exception as e:
            logger.debug("[ZADACI_AI] insert greška: %s", e)

    return {
        "ok":       True,
        "kreirano": len(kreirani),
        "zadaci":   kreirani,
        "poruka":   f"AI je kreirao {len(kreirani)} zadatak(a) za predmet '{naziv_predmeta}'.",
    }
