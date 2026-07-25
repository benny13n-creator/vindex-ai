# -*- coding: utf-8 -*-
"""
Vindex AI — routers/apr.py

APR (Agencija za privredne registre) autofill za CRM.
Korisnik unese matični broj -> automatski se popunjavaju: naziv firme, adresa, PIB, status, zastupnik.

Endpoint:
  GET /api/apr/lookup/{maticni_broj}

POPRAVKA (2026-07-25) — nalazi iz inspekcije 2026-07-25 i uzivo verifikovano
ovde pre izmene:
  1. Stari URL (www.apr.gov.rs/registers/business-entities/search.aspx) vraca
     HTTP 200 sa APR-ovom SOPSTVENOM brendiranom "HTTP 404" error stranicom
     kao telom -- kod je to tumacio kao uspesan, prazan rezultat ("nije
     pronadjeno"), ne kao kvar servisa. _looks_like_error_page() sada hvata
     ovo PRE parsiranja.
  2. APR je u medjuvremenu spojio pretragu u jedinstvenu React aplikaciju na
     pretraga.apr.gov.rs ("Objedinjena pretraga"). Stvarni API iza nje
     (pronadjen inspekcijom bundle-ovanog JS-a, ne dokumentacijom -- APR
     nema javnu API dokumentaciju) je
     https://pretraga.apr.gov.rs/api/search/PrivrednaDrustva/PretragaNaziva
     ali je zasticen reCAPTCHA-om na nivou servera -- SVAKI automatizovan
     poziv (potvrdjeno uzivo, bez obzira na parametre) vraca HTTP 400
     {"error": "reCAPTCHA verification failed"} PRE nego sto se upit uopste
     obradi. Ovo NIJE mrezni/SSL problem koji "tih fallback" moze da resi --
     to je namerna zastita APR-a od automatizovanog pristupa. Namerno NE
     pokusavamo da zaobidjemo reCAPTCHA (van obima i etike ovog projekta) --
     _looks_like_error_page() prepoznaje i OVAJ odgovor i tretira ga kao
     kvar servisa (otvara circuit breaker), ne kao "nije pronadjeno", sto je
     najvise sto se posteno moze uraditi bez ljudske/reCAPTCHA interakcije.
     Stvarno vracanje pravih podataka zahteva ili zvanican API pristup od
     APR-a, ili rucni unos od strane korisnika (postojeci fallback u UI-ju).
  3. pretraga2.apr.gov.rs/unifiedentitysearch (stariji sistem) sada samo
     redirect-uje na ISTI zasticeni pretraga.apr.gov.rs -- nije vise
     nezavisna, manje-zasticena putanja.
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

_LOOKUP_METHOD = "html_search"  # jedini metod trenutno implementiran (nema zvanicnog, javno-dokumentovanog APR API-ja)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Primarni cilj: stvaran API iza APR-ove "Objedinjena pretraga" React
# aplikacije (v. napomenu u docstring-u modula -- reCAPTCHA-zasticen, ali
# ovo je ISPRAVAN endpoint ako/kad APR ikad ponudi zvanican, ne-zasticen
# pristup ili ako Vindex dobije zvanicne kredencijale).
_APR_SEARCH_PRIMARY = "https://pretraga.apr.gov.rs/api/search/PrivrednaDrustva/PretragaNaziva"
# Fallback: stari HTML endpoint. Takodje trenutno ne vraca stvarne podatke
# (v. docstring), ali se pokusava ako primarni endpoint padne na
# mrezном/SSL nivou (timeout, connect/SSL greska) -- ne i kad primarni
# eksplicitno odbije zahtev (npr. reCAPTCHA 400), jer to nije prolazna
# mrezna greska koju bi drugi URL zaobisao.
_APR_SEARCH_FALLBACK = "https://www.apr.gov.rs/registers/business-entities/search.aspx"

# ─── Detekcija "lazno uspesnog" odgovora (HTTP 200 koji NIJE stvaran rezultat) ──
# APR vraca HTTP 200 i za sopstvenu brendiranu error stranicu i za
# reCAPTCHA odbijanje (JSON, ali sa 400 statusom -- ako se ikad promeni na
# 200 sa istim telom, ovo i dalje hvata sadrzaj). Bilo koji od ovih
# indikatora u telu odgovora znaci "servis nije stvarno odgovorio", ne
# "firma nije pronadjena".
_ERROR_PAGE_MARKERS = (
    "apr error page",
    "recaptcha verification failed",
    "recaptcha",
    ">http 404<",
    ">http 500<",
    "id=\"error\"",
)


def _looks_like_error_page(body: str) -> bool:
    lower = (body or "").lower()
    return any(marker in lower for marker in _ERROR_PAGE_MARKERS)


# ─── Circuit breaker (in-memory, per-process — dovoljno za single-instance beta) ──
_CIRCUIT_THRESHOLD    = 5      # uzastopnih SERVIS grešaka (timeout/HTTP/exception/error-page) pre otvaranja
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


async def _fetch_apr(url: str, maticni_broj: str, *, is_json_api: bool) -> httpx.Response:
    """Jedan HTTP pokusaj ka datom URL-u. Baca na mreznu/HTTP gresku --
    pozivalac (_apr_lookup) odlucuje da li i kako da reaguje (fallback,
    circuit breaker)."""
    headers = {
        "User-Agent":      _UA,
        "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.5",
        "Referer":         "https://www.apr.gov.rs/",
    }
    if is_json_api:
        # Stvaran API zahtev/odgovor oblik nije mogao biti potvrdjen uzivo
        # (reCAPTCHA blokira PRE nego sto bi bilo koji parametar bio
        # obradjen -- v. napomenu u docstring-u modula). Saljemo oba
        # razumna imena polja defanzivno.
        headers["Accept"] = "application/json"
        params = {"naziv": maticni_broj, "maticniBroj": maticni_broj}
    else:
        params = {"q": maticni_broj, "tip": "mb"}

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        return await client.get(url, params=params, headers=headers)


async def _apr_lookup(maticni_broj: str) -> dict:
    """
    Pretrazuje APR registar po maticnom broju (8 cifara).
    Vraca: {naziv, adresa, pib, status, zastupnik, maticni_broj, greska,
            source, fetched_at, lookup_method, response_ms}
    """
    t0 = time.perf_counter()
    result: dict = {
        "naziv":        "",
        "adresa":       "",
        "pib":          "",
        "status":       "",
        "zastupnik":    "",
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

    resp: Optional[httpx.Response] = None

    try:
        resp = await _fetch_apr(_APR_SEARCH_PRIMARY, maticni_broj, is_json_api=True)
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        # Samo PROLAZNE mrezne greske (timeout, konekcija/SSL) idu na tihi
        # fallback -- ne i eksplicitna odbijanja servisa (npr. reCAPTCHA
        # 400), koja drugi URL ne bi zaobisao jer nisu mrezni problem.
        logger.info("[APR] Primarni endpoint mrezna greska (%s) — pokusavam fallback.", type(e).__name__)
        try:
            resp = await _fetch_apr(_APR_SEARCH_FALLBACK, maticni_broj, is_json_api=False)
            result["lookup_method"] = "html_search_fallback"
        except Exception as e2:
            logger.warning("[APR] Fallback takodje neuspesan: %s", e2)
            _circuit_record(service_ok=False)
            result["greska"] = "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
            return _finish(result)
    except Exception as e:
        logger.warning("[APR] Lookup greska: %s", e)
        _circuit_record(service_ok=False)
        result["greska"] = "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
        return _finish(result)

    # FIX (2026-07-25): HTTP 200 vise NE znaci automatski "servis je
    # odgovorio stvarnim rezultatom" -- APR-ova sopstvena error stranica I
    # reCAPTCHA odbijanje se prepoznaju eksplicitno PRE parsiranja, i
    # tretiraju kao kvar servisa (otvara circuit breaker), ne kao "firma
    # nije pronadjena" (sto je bio prethodni, tihi propust).
    if resp.status_code != 200 or _looks_like_error_page(resp.text):
        _circuit_record(service_ok=False)
        result["greska"] = "Podaci trenutno nisu dostupni. Mozete ih uneti rucno."
        return _finish(result)

    _parse_apr(resp.text, result)
    _circuit_record(service_ok=True)

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

    # Zastupnik (zakonski zastupnik/direktor) — DODATO 2026-07-25.
    # NAPOMENA: uzorci ispod su izvedeni iz uobicajene srpske
    # administrativne terminologije i testirani protiv rekonstruisanog
    # fixture-a u istom (starom, table-cell) formatu koji ostatak ovog
    # parsera vec cilja -- NISU potvrdjeni protiv stvarnog trenutnog APR
    # odgovora, jer je live pristup blokiran reCAPTCHA-om (v. docstring
    # modula). Ako/kad primarni endpoint ikad vrati stvaran sadrzaj, ove
    # uzorke treba proveriti/podesiti protiv stvarnog HTML/JSON oblika.
    for pat in [
        r'Zastupnik[:\s]*</td>\s*<td[^>]*>\s*([^<]{2,200})',
        r'Lice\s+ovla[sš][cć]eno\s+za\s+zastupanje[:\s]*</td>\s*<td[^>]*>\s*([^<]{2,200})',
        r'Zastupnik[:\s]+([^\n<]{2,200})',
        r'"zastupnik"\s*:\s*"([^"]{2,200})"',
    ]:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            v = re.sub(r"\s+", " ", m.group(1).strip())
            if 2 < len(v) < 200:
                result["zastupnik"] = v
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
