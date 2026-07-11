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
import time
from datetime import datetime, timedelta, timezone
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

_MIN_RECHECK_MINUTES = 30  # normalan interval kad predmet nema uzastopnih grešaka
_BACKOFF_MAX_MINUTES = 360  # 6h — gornja granica exponential backoff-a

_DISCLAIMER = (
    "Vindex periodično proverava javno dostupne podatke sa Portala sudova. "
    "Dostupnost i učestalost promena zavise od izvora podataka."
)


def _minutes_since(iso_ts: Optional[str]) -> Optional[float]:
    if not iso_ts:
        return None
    try:
        last = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - last).total_seconds() / 60
    except Exception:
        return None


def _backoff_minutes(consecutive_failures: int) -> int:
    """Per-predmet exponential backoff: 15m, 30m, 60m, ..., max 6h. Bez grešaka -> normalan interval."""
    if not consecutive_failures or consecutive_failures <= 0:
        return _MIN_RECHECK_MINUTES
    return min(15 * (2 ** (consecutive_failures - 1)), _BACKOFF_MAX_MINUTES)

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
    Vraća: {status, datum, greska, kind, response_ms} — kind: ok | unavailable | error
    """
    t0 = time.perf_counter()

    def _ms() -> int:
        return round((time.perf_counter() - t0) * 1000)

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
                "kind": "unavailable",
                "response_ms": _ms(),
            }

        if resp.status_code != 200:
            return {
                "status": "",
                "datum": "",
                "greska": f"Portal nedostupan (HTTP {resp.status_code})",
                "kind": "unavailable",
                "response_ms": _ms(),
            }

        status = _extrahuj_status(resp.text)
        return {
            "status": status,
            "datum": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "greska": None if status else "Status nije pronađen — format portala se promenio.",
            "kind": "ok" if status else "error",
            "response_ms": _ms(),
        }

    except httpx.TimeoutException:
        return {"status": "", "datum": "", "greska": "Portal nije odgovorio (timeout 20s).", "kind": "unavailable", "response_ms": _ms()}
    except Exception as e:
        logger.warning("[PORTAL] Scraping greška: %s", e)
        return {"status": "", "datum": "", "greska": "Greška pri pristupu portalu.", "kind": "error", "response_ms": _ms()}


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

def _poruka_promena(naziv: str, stari: str, novi: str) -> str:
    return (
        f"Vindex AI — Promena statusa\n\n"
        f"Predmet: {naziv}\n"
        f"Novi status: {novi}\n"
        f"Prethodni: {stari or '—'}\n\n"
        f"Prijavite se na vindex.rs za detalje."
    )


def _poruka_digest(promene: list) -> str:
    """Grupiše više promena istog korisnika u jednu poruku."""
    linije = [f"Vindex AI — {len(promene)} promena statusa", ""]
    for p in promene[:10]:
        linije.append(f"• {p['naziv']}: {p['stari'] or '—'} → {p['novi']}")
    if len(promene) > 10:
        linije.append(f"... i još {len(promene) - 10} promena")
    linije.append("")
    linije.append("Prijavite se na vindex.rs za detalje.")
    return "\n".join(linije)


async def _posalji_poruku(user_id: str, poruka: str, tip: str, critical: bool = False) -> None:
    """Šalje Viber i/ili SMS poruku, poštujući tihi period, i loguje ishod."""
    from shared.notify_quiet import is_quiet_now, log_notification

    supa = _get_supa()

    # Viber
    try:
        vr = await asyncio.to_thread(
            lambda: supa.table("korisnik_viber_profil")
                .select("viber_user_id,quiet_start,quiet_end,allow_critical_override")
                .eq("user_id", user_id)
                .eq("aktivan", True)
                .maybe_single()
                .execute()
        )
        if vr.data and vr.data.get("viber_user_id"):
            if is_quiet_now(vr.data, critical=critical):
                await log_notification(user_id, "viber", tip, "deferred_quiet_hours")
            else:
                from routers.viber import _viber_send
                ok = await _viber_send(vr.data["viber_user_id"], poruka)
                await log_notification(user_id, "viber", tip, "sent" if ok else "failed",
                                        error_message=None if ok else "Viber slanje nije uspelo")
                if ok:
                    logger.info("[PORTAL] Viber poslat: uid=%.8s", user_id)
    except Exception as e:
        logger.warning("[PORTAL] Viber greška: %s", e)

    # SMS / WhatsApp
    try:
        sr = await asyncio.to_thread(
            lambda: supa.table("korisnik_sms_profil")
                .select("telefon,whatsapp,quiet_start,quiet_end,allow_critical_override")
                .eq("user_id", user_id)
                .eq("aktivan", True)
                .maybe_single()
                .execute()
        )
        if sr.data and sr.data.get("telefon"):
            if is_quiet_now(sr.data, critical=critical):
                await log_notification(user_id, "sms", tip, "deferred_quiet_hours")
            else:
                from routers.sms import _send_sms
                tel = sr.data["telefon"]
                to  = f"whatsapp:{tel}" if sr.data.get("whatsapp") else tel
                ok  = await asyncio.to_thread(_send_sms, to, poruka[:160])
                await log_notification(user_id, "sms" if not sr.data.get("whatsapp") else "whatsapp",
                                        tip, "sent" if ok else "failed",
                                        error_message=None if ok else "SMS/WhatsApp slanje nije uspelo")
                if ok:
                    logger.info("[PORTAL] SMS poslat: uid=%.8s", user_id)
    except Exception as e:
        logger.warning("[PORTAL] SMS greška: %s", e)


async def _posalji_notifikaciju(user_id: str, naziv: str, stari: str, novi: str) -> None:
    """Šalje Viber i/ili SMS notifikaciju o promeni statusa jednog predmeta (koristi manual-update)."""
    await _posalji_poruku(user_id, _poruka_promena(naziv, stari, novi), tip="portal_status_change")


async def _posalji_digest_notifikaciju(user_id: str, promene: list) -> None:
    """Šalje JEDNU poruku za više promena istog korisnika (koristi cron-proveri)."""
    await _posalji_poruku(user_id, _poruka_digest(promene), tip="portal_status_digest")


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
                .select("id,predmet_id,naziv,broj_predmeta,sud_naziv,poslednji_status,poslednji_status_datum,"
                        "poslednja_provera,current_status,last_successful_check_at,last_error")
                .eq("user_id", user["user_id"])
                .eq("aktivan", True)
                .order("created_at", desc=True)
                .execute()
        )
        return {"predmeti": r.data or [], "napomena": _DISCLAIMER}
    except Exception as e:
        logger.error("[PORTAL] Lista greška: %s", e)
        return {"predmeti": [], "napomena": _DISCLAIMER}


@router.get("/health")
@limiter.limit("30/minute")
async def portal_health(request: Request, user: dict = Depends(get_current_user)):
    """Founder-only: agregatno zdravlje portal.sud.rs monitoringa za admin dashboard."""
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")

    supa = _get_supa()
    now = datetime.now(timezone.utc)
    od_24h = (now - timedelta(hours=24)).isoformat()
    od_7d  = (now - timedelta(days=7)).isoformat()

    def _stats(rows: list) -> dict:
        total = len(rows)
        ok = sum(1 for r in rows if r.get("result_kind") == "ok")
        return round(ok / total * 100, 1) if total else None

    try:
        r24 = await asyncio.to_thread(
            lambda: supa.table("portal_status_log")
                .select("result_kind,response_ms,created_at")
                .gte("created_at", od_24h)
                .execute()
        )
        rows_24h = r24.data or []
        r7 = await asyncio.to_thread(
            lambda: supa.table("portal_status_log")
                .select("result_kind")
                .gte("created_at", od_7d)
                .execute()
        )
        rows_7d = r7.data or []
        last_ok = await asyncio.to_thread(
            lambda: supa.table("portal_status_log")
                .select("created_at")
                .eq("result_kind", "ok")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Greska pri citanju metrika: {e}")

    stopa_24h = _stats(rows_24h)
    stopa_7d  = _stats(rows_7d)
    failed_24h = sum(1 for r in rows_24h if r.get("result_kind") in ("unavailable", "error"))
    response_times = [r["response_ms"] for r in rows_24h if r.get("response_ms") is not None]
    avg_response = round(sum(response_times) / len(response_times)) if response_times else None
    last_success_at = (last_ok.data or [{}])[0].get("created_at") if last_ok.data else None

    if stopa_24h is None:
        status = "UNKNOWN"
    elif stopa_24h >= 90:
        status = "HEALTHY"
    elif stopa_24h >= 50:
        status = "DEGRADED"
    else:
        status = "DOWN"

    return {
        "status":                   status,
        "success_rate_24h":        stopa_24h,
        "success_rate_7d":         stopa_7d,
        "avg_response_ms":         avg_response,
        "failed_checks_count":     failed_24h,
        "last_successful_check_at": last_success_at,
    }


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


async def _audit_check(supa, pp_id: str, uid: str, stari: str, novi: str, source: str, run_id: str,
                        is_change: bool, result_kind: Optional[str] = None, response_ms: Optional[int] = None) -> None:
    """Upisuje red u portal_status_log za SVAKU proveru (audit trail), ne samo promene."""
    try:
        row = {
            "praceni_predmet_id": pp_id,
            "user_id":            uid,
            "old_status":         stari,
            "new_status":         novi,
            "source":             source,
            "run_id":             run_id,
            "result_kind":        result_kind,
            "response_ms":        response_ms,
        }
        if is_change:
            row["status_tekst"] = novi
            row["status_datum"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await asyncio.to_thread(lambda: supa.table("portal_status_log").insert(row).execute())
    except Exception as e:
        logger.debug("[PORTAL] Audit log greška: %s", e)


def _current_status_update(result: dict, promena: bool, prev_consecutive_failures: int = 0) -> dict:
    """Gradi update dict za praceni_predmeti na osnovu ishoda provere, uklj. backoff brojac."""
    now_iso = datetime.now(timezone.utc).isoformat()
    kind = result.get("kind", "error")
    update = {"poslednja_provera": now_iso, "last_error": result.get("greska")}
    if kind in ("unavailable", "error"):
        update["current_status"]        = kind
        update["consecutive_failures"]  = (prev_consecutive_failures or 0) + 1
    else:
        update["current_status"]              = "changed" if promena else "unchanged"
        update["last_successful_check_at"]    = now_iso
        update["last_error"]                  = None
        update["consecutive_failures"]        = 0
    return update


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

    # Duplicate protection — per-predmet exponential backoff (15m/30m/60m.../max 6h posle grešaka)
    prev_failures = pp.get("consecutive_failures", 0) or 0
    cekaj_min = _backoff_minutes(prev_failures)
    minuta_od = _minutes_since(pp.get("poslednja_provera"))
    if minuta_od is not None and minuta_od < cekaj_min:
        return {
            "ok": True, "preskoceno": True,
            "poruka": f"Nedavno proveravano (pre {round(minuta_od)} min). Sačekajte {round(cekaj_min - minuta_od)} min.",
            "status": pp.get("poslednji_status", ""),
        }

    result     = await _scrape_portal_status(pp["broj_predmeta"], pp["sud_naziv"])
    stari      = pp.get("poslednji_status", "")
    novi       = result.get("status", "")
    promena    = bool(novi and novi != stari)

    update = _current_status_update(result, promena, prev_consecutive_failures=prev_failures)
    if promena:
        update["poslednji_status"]        = novi
        update["poslednji_status_datum"]  = result.get("datum", "")

    await _audit_check(supa, praceni_id, uid, stari, novi, source="manual", run_id="manual", is_change=promena,
                        result_kind=result.get("kind"), response_ms=result.get("response_ms"))
    if promena:
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
    run_id: Optional[str] = None,
):
    """
    Cron trigger — proveri status svih aktivnih praćenih predmeta.
    Samo za founder korisnika ili sa validnim X-Cron-Secret header-om.
    `run_id` — prosledjen iz api.py::cron_daily radi audit trail-a; standalone poziv dobija sopstveni.
    """
    is_cron   = bool(_CRON_SECRET and x_cron_secret == _CRON_SECRET)
    is_admin  = _is_founder(user.get("email", ""))
    if not is_cron and not is_admin:
        raise HTTPException(status_code=403, detail="Restricted.")

    if not run_id:
        import uuid as _uuid
        run_id = _uuid.uuid4().hex[:8]

    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("praceni_predmeti")
                .select("id,user_id,naziv,broj_predmeta,sud_naziv,poslednji_status,poslednja_provera,consecutive_failures")
                .eq("aktivan", True)
                .execute()
        )
        predmeti = r.data or []
    except Exception as e:
        logger.error("[PORTAL-CRON] Učitavanje greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri učitavanju liste.")

    if not predmeti:
        return {"provereno": 0, "promena": 0, "napomena": "Nema aktivnih praćenih predmeta."}

    provereno = promena_ct = greska_ct = preskoceno_ct = 0
    promene_po_korisniku: dict[str, list] = {}

    for p in predmeti:
        pp_id      = p["id"]
        uid        = p["user_id"]
        naziv      = p.get("naziv") or p["broj_predmeta"]
        stari      = p.get("poslednji_status", "")
        prev_failures = p.get("consecutive_failures", 0) or 0

        # Duplicate protection — per-predmet exponential backoff
        minuta_od = _minutes_since(p.get("poslednja_provera"))
        if minuta_od is not None and minuta_od < _backoff_minutes(prev_failures):
            preskoceno_ct += 1
            continue

        result = await _scrape_portal_status(p["broj_predmeta"], p["sud_naziv"])
        provereno += 1

        if result.get("greska"):
            greska_ct += 1
            logger.warning("[PORTAL-CRON] %s: %s", p["broj_predmeta"], result["greska"])

        novi    = result.get("status", "")
        promena = bool(novi and novi != stari)
        update  = _current_status_update(result, promena, prev_consecutive_failures=prev_failures)

        if promena:
            promena_ct += 1
            update["poslednji_status"]       = novi
            update["poslednji_status_datum"] = result.get("datum", "")
            promene_po_korisniku.setdefault(uid, []).append({"naziv": naziv, "stari": stari, "novi": novi})
            try:
                from routers.analytics import _track_event
                asyncio.create_task(_track_event(uid, "portal", "status_changed", metadata={"stari": stari, "novi": novi}))
            except Exception:
                pass

        await _audit_check(supa, pp_id, uid, stari, novi, source="cron", run_id=run_id, is_change=promena,
                            result_kind=result.get("kind"), response_ms=result.get("response_ms"))

        try:
            await asyncio.to_thread(
                lambda: supa.table("praceni_predmeti").update(update).eq("id", pp_id).execute()
            )
        except Exception:
            pass

    # Digest — jedna poruka po korisniku, ne po predmetu
    for uid, promene in promene_po_korisniku.items():
        try:
            await _posalji_digest_notifikaciju(uid, promene)
        except Exception as e:
            logger.warning("[PORTAL-CRON] Digest notifikacija greška: %s", e)

    logger.info(
        "[PORTAL-CRON] run_id=%s Završeno: provereno=%d promena=%d greška=%d preskočeno=%d",
        run_id, provereno, promena_ct, greska_ct, preskoceno_ct,
    )
    return {
        "run_id": run_id, "provereno": provereno, "promena": promena_ct,
        "greske": greska_ct, "preskoceno": preskoceno_ct,
    }
