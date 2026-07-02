# -*- coding: utf-8 -*-
"""
Role-Based Access Control za Vindex AI.

Uloge (od najviše do najniže):
  admin         — pun pristup, upravlja firmom
  partner       — pun pristup predmetima i klijentima, vidi billing
  advokat       — RW na sopstvenim predmetima, nema billing admin
  pripravnik    — read-only na predmetima kojima je dodeljen
  administracija— billing + rokovi, bez pristupa sadržaju predmeta
  citanje       — legacy read-only (kompatibilnost)
"""
from fastapi import HTTPException

ULOGE = ("admin", "partner", "advokat", "pripravnik", "administracija", "citanje")

ULOGA_LABELS = {
    "admin":          "Administrator",
    "partner":        "Partner",
    "advokat":        "Advokat",
    "pripravnik":     "Pripravnik",
    "administracija": "Administracija",
    "citanje":        "Samo čitanje",
}

# Šta svaka uloga sme — set stringova "resurs:akcija"
_DOZVOLE: dict[str, set[str]] = {
    "admin": {"*"},  # sve
    "partner": {
        "predmeti:r", "predmeti:w",
        "klijenti:r", "klijenti:w",
        "billing:r",  "billing:w",
        "dokumenti:r","dokumenti:w",
        "analiza:r",  "analiza:w",
        "rokovi:r",   "rokovi:w",
        "ai:r",       "ai:w",
        "firma:r",
        "export:r",
    },
    "advokat": {
        "predmeti:r", "predmeti:w",
        "klijenti:r", "klijenti:w",
        "billing:r",
        "dokumenti:r","dokumenti:w",
        "analiza:r",  "analiza:w",
        "rokovi:r",   "rokovi:w",
        "ai:r",       "ai:w",
    },
    "pripravnik": {
        "predmeti:r",
        "klijenti:r",
        "dokumenti:r",
        "analiza:r",
        "rokovi:r",
    },
    "administracija": {
        "billing:r",  "billing:w",
        "rokovi:r",   "rokovi:w",
        "predmeti:r",
        "klijenti:r",
        "export:r",
    },
    "citanje": {
        "predmeti:r",
        "klijenti:r",
        "dokumenti:r",
    },
}


def ima_dozvolu(uloga: str, dozvola: str) -> bool:
    """Proverava da li uloga ima traženu dozvolu."""
    if not uloga:
        return False
    prava = _DOZVOLE.get(uloga, set())
    return "*" in prava or dozvola in prava


def zahtevaj_dozvolu(uloga: str, dozvola: str, poruka: str = "") -> None:
    """Baca 403 ako uloga nema dozvolu."""
    if not ima_dozvolu(uloga, dozvola):
        raise HTTPException(
            status_code=403,
            detail=poruka or f"Uloga '{ULOGA_LABELS.get(uloga, uloga)}' nema pristup ovoj funkciji."
        )
