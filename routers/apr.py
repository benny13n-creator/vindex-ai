# -*- coding: utf-8 -*-
"""
Vindex AI — routers/apr.py

APR (Agencija za privredne registre) autofill za CRM.
Korisnik unese matični broj -> automatski se popunjavaju: naziv firme, adresa, PIB, status.

Endpoint:
  GET /api/apr/lookup/{maticni_broj}
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user, _is_founder
from shared.rate import limiter

logger = logging.getLogger("vindex.apr")
router = APIRouter(prefix="/api/apr", tags=["apr"])

_LOOKUP_METHOD = "html_search"  # jedini metod trenutno implementiran (nema APR JSON API-ja)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_APR_SEARCH = "https://www.apr.gov.rs/registers/business-entities/search.aspx"

# ─── Circuit breaker (in-memory, per-process — dovoljno za single-instance beta) ──
_CIRCUIT_THRESHOLD    = 5      # uzastopnih SERVIS grešaka (timeout/HTTP/exception) pre otvaranja
_CIRCUIT_OPEN_SECONDS = 300    # 5 min pauza pre ponovnog pokusaja

_circuit: dict = {"consecutive_failures": 0, "open_until": None, "last_success_at": None}


def _circuit_open_remaining() -> Optional[float]:
    """Vraca broj preostalih sekundi dok je circuit otvoren, ili None ako je zatvoren."""
    open_until = _circuit.get("open_until")
    if not open_until:
        return None
    remaining = (open_until - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        _circuit["open_until"] = None
        return None
    return remaining


def _circuit_record(service_ok: bool) -> None:
    """service_ok=False znaci mrezna/HTTP greska (servis nedostupan), ne 'nije pronadjeno'."""
    if service_ok:
        _circuit["consecutive_failures"] = 0
        _circuit["open_until"]           = None
        _circuit["last_success_at"]      = datetime.now(timezone.utc).isoformat()
    else:
        _circuit["consecutive_failures"] += 1
        if _circuit["consecutive_failures"] >= _CIRCUIT_THRESHOLD:
            _circuit["open_until"] = datetime.now(timezone.utc) + timedelta(seconds=_CIRCUIT_OPEN_SECONDS)


async def _apr_lookup(maticni_broj: str) -> dict:
    """
    Pretrazuje APR registar po maticnom broju (8 cifara).
    Vraca: {naziv, adresa, pib, status, maticni_broj, greska, source, fetched_at, lookup_method, response_ms}
    """
    t0 = time.perf_counter()
    result: dict = {
        "naziv":        "",
        "adresa":       "",
        "pib":          "",
        "status":       "",
        "maticni_broj": maticni_broj,
        "greska":       None,
        "source":       "APR",
        "lookup_method": _LOOKUP_METHOD,
    }

    def _finish(r: dict) -> dict:
        r["fetched_at"]  = datetime.now(timezone.utc).isoformat()
        r["response_ms"] = round((time.perf_counter() - t0) * 1000)
        return r

    remaining = _circuit_open_remaining()
    if remaining is not None:
        logger.info("[APR] Circuit breaker OTVOREN, preskacem poziv (%.0fs preostalo)", remaining)
        result["greska"]        = "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
        result["lookup_method"] = "circuit_open"
        return _finish(result)

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                _APR_SEARCH,
                params={"q": maticni_broj, "tip": "mb"},
                headers={
                    "User-Agent":      _UA,
                    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.5",
                    "Referer":         "https://www.apr.gov.rs/",
                },
            )

        if resp.status_code != 200:
            _circuit_record(service_ok=False)
            result["greska"] = "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
            return _finish(result)

        _parse_apr(resp.text, result)
        _circuit_record(service_ok=True)  # dobili smo HTTP 200 — servis radi, bez obzira na sadrzaj

    except httpx.TimeoutException:
        _circuit_record(service_ok=False)
        result["greska"] = "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
        return _finish(result)
    except Exception as e:
        logger.warning("[APR] Lookup greska: %s", e)
        _circuit_record(service_ok=False)
        result["greska"] = "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
        return _finish(result)

    if not result["naziv"] and not result["pib"]:
        result["greska"] = (
            f"Firma sa maticnim brojem {maticni_broj} nije pronadjena u APR registru. "
            "Mozete uneti podatke rucno."
        )

    return _finish(result)


def _parse_apr(html: str, result: dict) -> None:
    """Ekstrahuje podatke iz APR HTML stranice."""
    # Naziv firme
    for pat in [
        r'Naziv\s*(?:subjekta)?[:\s]*</td>\s*<td[^>]*>\s*([^<]{2,300})',
        r'class="[^"]*naziv[^"]*"[^>]*>\s*([^<]{2,300})',
        r'subjectName["\s:]+([^"<]{2,200})',
    ]:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            v = re.sub(r"\s+", " ", m.group(1).strip())
            if 2 < len(v) < 300:
                result["naziv"] = v
                break

    # PIB (9 cifara)
    pib_m = re.search(r'\bPIB\b[:\s]*(?:</td>\s*<td[^>]*>)?\s*(\d{9})', html, re.IGNORECASE)
    if pib_m:
        result["pib"] = pib_m.group(1)

    # Adresa sedista
    for pat in [
        r'Adresa\s*(?:sedi[sš]ta)?[:\s]*</td>\s*<td[^>]*>\s*([^<]{5,300})',
        r'Adresa[:\s]+([^\n<]{5,300})',
    ]:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            v = re.sub(r"\s+", " ", m.group(1).strip())
            if 5 < len(v) < 300:
                result["adresa"] = v
                break

    # Status registracije
    for pat in [
        r'Status[:\s]*</td>\s*<td[^>]*>\s*([^<]{3,60})',
        r'(Aktiv[a-z]+|Pasiv[a-z]+|Brisan[a-z]+|Likvid[a-z]+)',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            result["status"] = m.group(1).strip()[:60]
            break


async def _log_apr_lookup(user_id: str, maticni_broj: str, result: dict) -> None:
    """Fire-and-forget log svakog APR pokusaja (uspeh/neuspeh) — za proof.py success rate."""
    try:
        supa = _get_supa()
        success = bool(result.get("naziv") or result.get("pib")) and not result.get("greska")
        await asyncio.to_thread(
            lambda: supa.table("apr_lookup_log").insert({
                "user_id":       user_id,
                "maticni_broj":  maticni_broj,
                "success":       success,
                "lookup_method": result.get("lookup_method", _LOOKUP_METHOD),
                "response_ms":   result.get("response_ms"),
                "greska":        result.get("greska"),
            }).execute()
        )
    except Exception as e:
        logger.debug("[APR] Log greska: %s", e)


@router.get("/lookup/{maticni_broj}")
@limiter.limit("20/minute")
async def apr_lookup(
    maticni_broj: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Pretrazuje APR registar po maticnom broju.
    Vraca naziv firme, adresu, PIB i status registracije.
    """
    mb = re.sub(r"[\s\-]", "", maticni_broj.strip())
    if not re.match(r"^\d{8}$", mb):
        raise HTTPException(
            status_code=422,
            detail="Maticni broj mora imati tacno 8 cifara (za privredna drustva)."
        )

    result = await _apr_lookup(mb)
    asyncio.create_task(_log_apr_lookup(user["user_id"], mb, result))
    return result


@router.get("/metrics")
@limiter.limit("10/minute")
async def apr_metrics(
    request: Request,
    dana: int = 7,
    user: dict = Depends(get_current_user),
):
    """Founder-only: APR success rate za poslednjih N dana. Koristi ga proof.py."""
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")

    supa = _get_supa()
    od = (datetime.now(timezone.utc) - timedelta(days=dana)).isoformat()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("apr_lookup_log")
                .select("success")
                .gte("created_at", od)
                .execute()
        )
        rows = r.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Greska pri citanju metrika: {e}")

    total = len(rows)
    uspesno = sum(1 for x in rows if x.get("success"))
    stopa = round(uspesno / total * 100, 1) if total else None

    return {
        "dana": dana,
        "ukupno_pokusaja": total,
        "uspesno": uspesno,
        "stopa_uspeha_pct": stopa,
    }


@router.get("/health")
@limiter.limit("30/minute")
async def apr_health(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Founder-only: circuit breaker status + 24h metrike za admin dashboard."""
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")

    supa = _get_supa()
    od = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("apr_lookup_log")
                .select("success,response_ms")
                .gte("created_at", od)
                .execute()
        )
        rows = r.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Greska pri citanju metrika: {e}")

    total = len(rows)
    uspesno = sum(1 for x in rows if x.get("success"))
    stopa = round(uspesno / total * 100, 1) if total else None
    response_times = [x["response_ms"] for x in rows if x.get("response_ms") is not None]
    avg_response = round(sum(response_times) / len(response_times)) if response_times else None

    circuit_open = _circuit_open_remaining() is not None
    status = "DEGRADED" if circuit_open else "HEALTHY"

    return {
        "status":               status,
        "success_rate_24h":     stopa,
        "avg_response_ms":      avg_response,
        "last_success_at":      _circuit.get("last_success_at"),
        "consecutive_failures": _circuit.get("consecutive_failures", 0),
        "circuit_open":         circuit_open,
    }
