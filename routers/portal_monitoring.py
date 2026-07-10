# -*- coding: utf-8 -*-
"""
Vindex AI — routers/portal_monitoring.py

Automatsko praćenje statusa predmeta na portal.sud.rs
Kada se status predmeta promeni → Viber/SMS notifikacija advokatu.

Endpoints:
  POST   /api/portal/prati               — dodaj predmet za praćenje
  GET    /api/portal/praceni             — lista praćenih predmeta
  DELETE /api/portal/prati/{id}          — prestani pratiti
  GET    /api/portal/log/{praceni_id}    — istorija statusa
  POST   /api/portal/manual-update/{id} — ručna provera jednog predmeta
  POST   /api/portal/cron-proveri        — cron trigger (founder / X-Cron-Secret)

Cron podešavanje (cron-job.org, svaki dan u 07:00):
  URL:      POST https://vindex-ai.onrender.com/api/portal/cron-proveri
  Header:   X-Cron-Secret: {BRIEFING_CRON_SECRET}
  Schedule: 0 5 * * *  (05:00 UTC = 07:00 Beograd)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user, _is_founder
from shared.rate import limiter

logger = logging.getLogger("vindex.portal_monitoring")
router = APIRouter(prefix="/api/portal", tags=["portal-monitoring"])

_CRON_SECRET = os.getenv("BRIEFING_CRON_SECRET", "")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ─── Modeli ───────────────────────────────────────────────────────────────────

class PratiReq(BaseModel):
    predmet_id: str  = Field(..., min_length=1, max_length=64)
    naziv:      str  = Field(default="", max_length=200)
    broj_predmeta: str = Field(..., min_length=1, max_length=100)
    sud_naziv:  str  = Field(..., min_length=1, max_length=200)
    sud_kod:    str  = Field(default="", max_length=20)


# ─── Scraper ──────────────────────────────────────────────────────────────────

_PORTAL_SEARCH = "https://portal.sud.rs/webportal/faces/javni/pretraga.xhtml"

async def _scrape_portal_status(broj_predmeta: str, sud_naziv: str) -> dict:
    """
    Dohvata status predmeta sa portal.sud.rs javnog modula.
    Vraća: {status, datum, greska}
    """
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                _PORTAL_SEARCH,
                params={"brPredmeta": broj_predmeta, "sud": sud_naziv},
                headers={
                    "User-Agent": _UA,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.5",
                    "Referer": "https://portal.sud.rs/",
                },
            )

        if resp.status_code == 403:
            return {
                "status": "",
                "datum": "",
                "greska": "Portal zahteva verifikaciju. Proverite ručno na portal.sud.rs.",
            }

        if resp.status_code != 200:
            return {
                "status": "",
                "datum": "",
                "greska": f"Portal nedostupan (HTTP {resp.status_code})",
            }

        status = _extrahuj_status(resp.text)
        return {
            "status": status,
            "datum": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "greska": None if status else "Status nije pronađen — format portala se promenio.",
        }

    except httpx.TimeoutException:
        return {"status": "", "datum": "", "greska": "Portal nije odgovorio (timeout 20s)."}
    except Exception as e:
        logger.warning("[PORTAL] Scraping greška: %s", e)
        return {"status": "", "datum": "", "greska": "Greška pri pristupu portalu."}


def _extrahuj_status(html: str) -> str:
    """Parsira HTML portal.sud.rs i extrahuje status predmeta."""
    patterns = [
        r'class="[^"]*status[^"]*"[^>]*>\s*([^<]{3,80})\s*<',
        r'Stanje\s*predmeta[:\s]+([^<\n]{3,80})',
        r'Status[:\s]*<[^>]+>([^<]{3,80})',
        r'<td[^>]*>\s*Status\s*</td>\s*<td[^>]*>\s*([^<]{3,80})\s*</td>',
        r'statusPredmeta[^>]*>([^<]{3,80})<',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            val = re.sub(r"\s+", " ", m.group(1).strip())
            if 3 <= len(val) <= 200:
                return val
    return ""


# ─── Notifikacije ─────────────────────────────────────────────────────────────

async def _posalji_notifikaciju(user_id: str, naziv: str, stari: str, novi: str) -> None:
    """Šalje Viber i/ili SMS notifikaciju o promeni statusa predmeta."""
    supa = _get_supa()
    poruka = (
        f"Vindex AI — Promena statusa\n\n"
        f"Predmet: {naziv}\n"
        f"Novi status: {novi}\n"
        f"Prethodni: {stari or '—'}\n\n"
        f"Prijavite se na vindex.rs za detalje."
    )

    # Viber
    try:
        vr = await asyncio.to_thread(
            lambda: supa.table("korisnik_viber_profil")
                .select("viber_user_id")
                .eq("user_id", user_id)
                .eq("aktivan", True)
                .maybe_single()
                .execute()
        )
        if vr.data and vr.data.get("viber_user_id"):
            from routers.viber import _viber_send
            await _viber_send(vr.data["viber_user_id"], poruka)
            logger.info("[PORTAL] Viber poslat: uid=%.8s", user_id)
    except Exception as e:
        logger.warning("[PORTAL] Viber greška: %s", e)

    # SMS / WhatsApp
    try:
        sr = await asyncio.to_thread(
            lambda: supa.table("korisnik_sms_profil")
                .select("telefon,whatsapp")
                .eq("user_id", user_id)
                .eq("aktivan", True)
                .maybe_single()
                .execute()
        )
        if sr.data and sr.data.get("telefon"):
            from routers.sms import _send_sms
            tel = sr.data["telefon"]
            to  = f"whatsapp:{tel}" if sr.data.get("whatsapp") else tel
            await asyncio.to_thread(_send_sms, to, poruka[:160])
            logger.info("[PORTAL] SMS poslat: uid=%.8s", user_id)
    except Exception as e:
        logger.warning("[PORTAL] SMS greška: %s", e)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/prati")
@limiter.limit("20/minute")
async def dodaj_praceni(
    req: PratiReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dodaje predmet na listu automatskog praćenja statusa."""
    supa = _get_supa()
    uid  = user["user_id"]
    try:
        await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti").upsert({
                "user_id":       uid,
                "predmet_id":    req.predmet_id[:64],
                "naziv":         req.naziv[:200],
                "broj_predmeta": req.broj_predmeta[:100],
                "sud_naziv":     req.sud_naziv[:200],
                "sud_kod":       req.sud_kod[:20],
                "aktivan":       True,
            }, on_conflict="user_id,predmet_id").execute()
        )
    except Exception as e:
        logger.error("[PORTAL] Upsert greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri dodavanju na listu praćenja.")
    return {"ok": True, "poruka": "Predmet dodat na listu praćenja"}


@router.get("/praceni")
@limiter.limit("30/minute")
async def lista_pracenih(request: Request, user: dict = Depends(get_current_user)):
    """Lista predmeta koji se aktivno prate za ovog korisnika."""
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti")
                .select("id,predmet_id,naziv,broj_predmeta,sud_naziv,poslednji_status,poslednji_status_datum,poslednja_provera")
                .eq("user_id", user["user_id"])
                .eq("aktivan", True)
                .order("created_at", desc=True)
                .execute()
        )
        return {"predmeti": r.data or []}
    except Exception as e:
        logger.error("[PORTAL] Lista greška: %s", e)
        return {"predmeti": []}


@router.delete("/prati/{praceni_id}")
async def ukloni_praceni(praceni_id: str, user: dict = Depends(get_current_user)):
    """Deaktivira praćenje predmeta."""
    supa = _get_supa()
    try:
        await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti")
                .update({"aktivan": False})
                .eq("id", praceni_id)
                .eq("user_id", user["user_id"])
                .execute()
        )
    except Exception as e:
        logger.warning("[PORTAL] Brisanje greška: %s", e)
    return {"ok": True}


@router.get("/log/{praceni_id}")
async def status_log(praceni_id: str, user: dict = Depends(get_current_user)):
    """Istorija promena statusa za praćeni predmet."""
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("portal_status_log")
                .select("status_tekst,status_datum,created_at")
                .eq("praceni_predmet_id", praceni_id)
                .eq("user_id", user["user_id"])
                .order("created_at", desc=True)
                .limit(20)
                .execute()
        )
        return {"log": r.data or []}
    except Exception:
        return {"log": []}


@router.post("/manual-update/{praceni_id}")
@limiter.limit("10/minute")
async def manual_update(
    praceni_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ručna provera statusa jednog predmeta na portalu (odmah, ne cron)."""
    supa = _get_supa()
    uid  = user["user_id"]

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti")
                .select("*")
                .eq("id", praceni_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        pp = r.data
    except Exception:
        pp = None

    if not pp:
        raise HTTPException(status_code=404, detail="Praćeni predmet nije pronađen.")

    result     = await _scrape_portal_status(pp["broj_predmeta"], pp["sud_naziv"])
    stari      = pp.get("poslednji_status", "")
    novi       = result.get("status", "")
    promena    = bool(novi and novi != stari)

    update = {"poslednja_provera": datetime.now(timezone.utc).isoformat()}
    if promena:
        update["poslednji_status"]        = novi
        update["poslednji_status_datum"]  = result.get("datum", "")
        try:
            await asyncio.to_thread(
                lambda: supa.table("portal_status_log").insert({
                    "praceni_predmet_id": praceni_id,
                    "user_id":            uid,
                    "status_tekst":       novi,
                    "status_datum":       result.get("datum", ""),
                }).execute()
            )
        except Exception:
            pass
        await _posalji_notifikaciju(uid, pp.get("naziv") or pp["broj_predmeta"], stari, novi)

    try:
        await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti").update(update).eq("id", praceni_id).execute()
        )
    except Exception:
        pass

    return {
        "ok":      True,
        "status":  novi,
        "datum":   result.get("datum", ""),
        "promena": promena,
        "greska":  result.get("greska"),
    }


@router.post("/cron-proveri")
async def cron_proveri(
    request: Request,
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
    user: dict = Depends(get_current_user),
):
    """
    Cron trigger — proveri status svih aktivnih praćenih predmeta.
    Samo za founder korisnika ili sa validnim X-Cron-Secret header-om.
    """
    is_cron   = bool(_CRON_SECRET and x_cron_secret == _CRON_SECRET)
    is_admin  = _is_founder(user.get("email", ""))
    if not is_cron and not is_admin:
        raise HTTPException(status_code=403, detail="Restricted.")

    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti")
                .select("id,user_id,naziv,broj_predmeta,sud_naziv,poslednji_status")
                .eq("aktivan", True)
                .execute()
        )
        predmeti = r.data or []
    except Exception as e:
        logger.error("[PORTAL-CRON] Učitavanje greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri učitavanju liste.")

    if not predmeti:
        return {"provereno": 0, "promena": 0, "napomena": "Nema aktivnih praćenih predmeta."}

    provereno = promena_ct = greska_ct = 0

    for p in predmeti:
        pp_id      = p["id"]
        uid        = p["user_id"]
        naziv      = p.get("naziv") or p["broj_predmeta"]
        stari      = p.get("poslednji_status", "")

        result = await _scrape_portal_status(p["broj_predmeta"], p["sud_naziv"])
        provereno += 1

        if result.get("greska"):
            greska_ct += 1
            logger.warning("[PORTAL-CRON] %s: %s", p["broj_predmeta"], result["greska"])

        novi   = result.get("status", "")
        update = {"poslednja_provera": datetime.now(timezone.utc).isoformat()}

        if novi and novi != stari:
            promena_ct += 1
            update["poslednji_status"]       = novi
            update["poslednji_status_datum"] = result.get("datum", "")
            try:
                await asyncio.to_thread(
                    lambda: supa.table("portal_status_log").insert({
                        "praceni_predmet_id": pp_id,
                        "user_id":            uid,
                        "status_tekst":       novi,
                        "status_datum":       result.get("datum", ""),
                    }).execute()
                )
            except Exception:
                pass
            try:
                await _posalji_notifikaciju(uid, naziv, stari, novi)
            except Exception as e:
                logger.warning("[PORTAL-CRON] Notifikacija greška: %s", e)

        try:
            await asyncio.to_thread(
                lambda: supa.table("praceni_predmeti").update(update).eq("id", pp_id).execute()
            )
        except Exception:
            pass

    logger.info("[PORTAL-CRON] Završeno: provereno=%d promena=%d greška=%d", provereno, promena_ct, greska_ct)
    return {"provereno": provereno, "promena": promena_ct, "greske": greska_ct}
