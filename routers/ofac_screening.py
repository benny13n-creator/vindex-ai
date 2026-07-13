# -*- coding: utf-8 -*-
"""
Vindex AI — routers/ofac_screening.py

F14: OFAC sankcije screening (Faza 3) — provera da li je adresa digitalne
imovine na zvaničnoj OFAC SDN (Specially Designated Nationals) listi.

Podaci: statički JSON lookup (data/ofac_crypto_addresses.json), generisan
skriptom scripts/ingest_ofac_sdn.py iz zvaničnog OFAC izvora. Čista
deterministička provera — NEMA AI poziva, NEMA troška kredita, besplatno za
sve ulogovane korisnike (isti princip kao F11.10a jurisdikcije lista).

Osvežavanje podataka: v1 je ručno pokretanje ingest skripte. Endpoint vraća
i datum poslednjeg osvežavanja da korisnik zna koliko su podaci sveži.
"""
import json
import logging
import os
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import get_current_user
from shared.rate import limiter

router = APIRouter()
logger = logging.getLogger("vindex.ofac")

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ofac_crypto_addresses.json"
)

_lock = threading.Lock()
_cache: Optional[dict] = None
_cache_mtime: Optional[float] = None


def _load() -> Optional[dict]:
    """Lazy-load + auto-reload ako je fajl osvežen (npr. novi ingest run) bez restarta servera."""
    global _cache, _cache_mtime
    if not os.path.exists(_DATA_PATH):
        return None
    mtime = os.path.getmtime(_DATA_PATH)
    with _lock:
        if _cache is None or mtime != _cache_mtime:
            with open(_DATA_PATH, "r", encoding="utf-8") as f:
                _cache = json.load(f)
            _cache_mtime = mtime
        return _cache


class OfacScreeningRequest(BaseModel):
    adrese: list[str] = Field(..., min_length=1, max_length=25)

    @field_validator("adrese")
    @classmethod
    def ocisti(cls, v: list[str]) -> list[str]:
        cisce = [a.strip() for a in v if a and a.strip()]
        if not cisce:
            raise ValueError("Bar jedna adresa je obavezna.")
        return cisce


@router.post("/web3/ofac-screening")  # F14.1
@limiter.limit("20/minute")
async def post_ofac_screening(
    req: OfacScreeningRequest, request: Request, user: dict = Depends(get_current_user)
):
    """F14.1 — Provera adresa digitalne imovine protiv OFAC SDN liste (besplatno)."""
    podaci = _load()
    if podaci is None:
        raise HTTPException(
            status_code=503,
            detail="OFAC baza trenutno nije dostupna na serveru. Pokušajte kasnije.",
        )

    lookup = podaci["adrese"]
    rezultati = []
    broj_pogodaka = 0
    for adresa in req.adrese:
        pogodak = lookup.get(adresa.strip().lower())
        if pogodak:
            broj_pogodaka += 1
            rezultati.append({
                "adresa": adresa,
                "sankcionisano": True,
                "entitet": pogodak["entitet"],
                "asset": pogodak["asset_naziv"],
                "programi": pogodak["programi"],
                "ofac_uid": pogodak["ofac_uid"],
            })
        else:
            rezultati.append({"adresa": adresa, "sankcionisano": False})

    return {
        "modul": "ofac_screening",
        "rezultati": rezultati,
        "broj_pogodaka": broj_pogodaka,
        "izvor": podaci.get("izvor"),
        "napomena": (
            "Provera je izvršena protiv zvanične OFAC SDN liste digitalne imovine. "
            "Odsustvo pogotka NE znači da adresa nema drugi pravni ili reputacioni rizik — "
            "OFAC lista se ažurira u realnom vremenu i ovaj snapshot može biti neaktuelan. "
            "Ovo nije pravni savet niti zamena za profesionalni sankcijski compliance program."
        ),
    }


@router.get("/web3/ofac-info")  # F14.2
async def get_ofac_info(user: dict = Depends(get_current_user)):
    """F14.2 — Metapodaci o učitanoj OFAC bazi (broj adresa, izvor) — besplatno."""
    podaci = _load()
    if podaci is None:
        return {
            "dostupno": False,
            "napomena": "OFAC baza još nije generisana na serveru.",
        }
    return {
        "dostupno": True,
        "broj_adresa": podaci.get("broj_adresa", 0),
        "izvor": podaci.get("izvor"),
        "napomena": podaci.get("napomena"),
    }
