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
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.apr")
router = APIRouter(prefix="/api/apr", tags=["apr"])

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_APR_SEARCH = "https://www.apr.gov.rs/registers/business-entities/search.aspx"


async def _apr_lookup(maticni_broj: str) -> dict:
    """
    Pretrazuje APR registar po maticnom broju (8 cifara).
    Vraca: {naziv, adresa, pib, status, maticni_broj, greska}
    """
    result: dict = {
        "naziv":        "",
        "adresa":       "",
        "pib":          "",
        "status":       "",
        "maticni_broj": maticni_broj,
        "greska":       None,
    }

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
            result["greska"] = f"APR nedostupan (HTTP {resp.status_code}). Unesite podatke rucno."
            return result

        _parse_apr(resp.text, result)

    except httpx.TimeoutException:
        result["greska"] = "APR nije odgovorio. Pokusajte ponovo."
        return result
    except Exception as e:
        logger.warning("[APR] Lookup greska: %s", e)
        result["greska"] = "APR pretraga nije dostupna. Unesite podatke rucno."
        return result

    if not result["naziv"] and not result["pib"]:
        result["greska"] = (
            f"Firma sa maticnim brojem {maticni_broj} nije pronadjena u APR registru."
        )

    return result


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

    return await _apr_lookup(mb)
