# -*- coding: utf-8 -*-
"""
P3.1/P3.2 — Deadline/rok ekstrakcija iz pravnih dokumenata.

Funkcija `ekstrahuj_rokove` parsira srpske datume i relativne rokove
iz pravnog teksta i vraća strukturirane dict-ove sa kontekstom i kategorijom.
"""
from __future__ import annotations

import re
from typing import Literal

# ─── Meseci na srpskom ────────────────────────────────────────────────────────
_MESECI_GEN = {
    "januara": "01", "februara": "02", "marta": "03", "aprila": "04",
    "maja": "05", "juna": "06", "jula": "07", "avgusta": "08",
    "septembra": "09", "oktobra": "10", "novembra": "11", "decembra": "12",
}

_MESECI_NOM = {
    "januar": "01", "februar": "02", "mart": "03", "april": "04",
    "maj": "05", "jun": "06", "jul": "07", "avgust": "08",
    "septembar": "09", "oktobar": "10", "novembar": "11", "decembar": "12",
}

# ─── Redni brojevi na srpskom (za "petnaestog maja") ─────────────────────────
_REDNI = {
    "prvog": "01", "drugog": "02", "trećeg": "03", "treća": "03",
    "četvrtog": "04", "petog": "05", "šestog": "06", "sedmog": "07",
    "osmog": "08", "devetog": "09", "desetog": "10", "jedanaestog": "11",
    "dvanaestog": "12", "trinaestog": "13", "četrnaestog": "14",
    "petnaestog": "15", "šesnaestog": "16", "sedamnaestog": "17",
    "osamnaestog": "18", "devetnaestog": "19", "dvadesetog": "20",
    "dvadeset prvog": "21", "dvadeset drugog": "22", "dvadeset trećeg": "23",
    "dvadeset četvrtog": "24", "dvadeset petog": "25", "dvadeset šestog": "26",
    "dvadeset sedmog": "27", "dvadeset osmog": "28", "dvadeset devetog": "29",
    "tridesetog": "30", "trideset prvog": "31",
}

# ─── Kategorije ───────────────────────────────────────────────────────────────
_KATEGORIJE: list[tuple[str, str]] = [
    (r"zastar",                         "zastarelost"),
    (r"otkaz|otkazn",                   "otkaz"),
    (r"žalb|zalb|žalba",                "zalba"),
    (r"podnes|tužb|tuzb|tužilac|tuzilac", "podnesak"),
    (r"uplat|isplat|plat",              "isplata"),
]

_CONTEXT_RADIUS = 100  # chars on each side


def _kategorija(kontekst: str) -> str:
    k = kontekst.lower()
    for pattern, cat in _KATEGORIJE:
        if re.search(pattern, k):
            return cat
    return "ostalo"


def _snippet(tekst: str, pos: int, end: int) -> str:
    start = max(0, pos - _CONTEXT_RADIUS)
    stop  = min(len(tekst), end + _CONTEXT_RADIUS)
    return tekst[start:stop].strip()


def ekstrahuj_rokove(tekst: str) -> list[dict]:
    """
    Parsira srpske datume i relativne rokove iz pravnog teksta.

    Returns list of dicts:
      {
        "tip":       "apsolutni" | "relativni",
        "vrednost":  "15.11.2025" | "8 dana",
        "kontekst":  "...tekst oko roka...",
        "kategorija":"zastarelost" | "otkaz" | "zalba" | "podnesak" | "isplata" | "ostalo"
      }
    """
    if not tekst or not tekst.strip():
        return []

    results: list[dict] = []
    seen_positions: set[int] = set()

    def _add(tip: str, vrednost: str, pos: int, end: int) -> None:
        if pos in seen_positions:
            return
        seen_positions.add(pos)
        ctx = _snippet(tekst, pos, end)
        results.append({
            "tip":       tip,
            "vrednost":  vrednost,
            "kontekst":  ctx,
            "kategorija": _kategorija(ctx),
        })

    # ─── 1. Apsolutni datum DD.MM.YYYY ──────────────────────────────────────
    for m in re.finditer(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", tekst):
        day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        _add("apsolutni", f"{day}.{month}.{year}", m.start(), m.end())

    # ─── 2. Tekstualni datum: "15. maja 2026" / "15 maja 2026" ──────────────
    meseci_pattern = "|".join(list(_MESECI_GEN) + list(_MESECI_NOM))
    pat_tekstualni = re.compile(
        rf"\b(\d{{1,2}})\.?\s+({meseci_pattern})\s+(\d{{4}})\b",
        re.IGNORECASE,
    )
    for m in pat_tekstualni.finditer(tekst):
        day  = m.group(1).zfill(2)
        mon  = (_MESECI_GEN.get(m.group(2).lower()) or _MESECI_NOM.get(m.group(2).lower(), "??"))
        year = m.group(3)
        _add("apsolutni", f"{day}.{mon}.{year}", m.start(), m.end())

    # ─── 3. Redni broj + mesec: "petnaestog maja 2026" ───────────────────────
    for redni_str, day_str in _REDNI.items():
        pat = re.compile(
            rf"\b{re.escape(redni_str)}\s+({meseci_pattern})\s+(\d{{4}})\b",
            re.IGNORECASE,
        )
        for m in pat.finditer(tekst):
            mon  = (_MESECI_GEN.get(m.group(1).lower()) or _MESECI_NOM.get(m.group(1).lower(), "??"))
            year = m.group(2)
            _add("apsolutni", f"{day_str}.{mon}.{year}", m.start(), m.end())

    # ─── 4. Relativni rok: "u roku od N dana/meseci/godina" ─────────────────
    pat_relativni = re.compile(
        r"u\s+roku\s+od\s+(\d+)\s+(dan[a]?|dana|radnih?\s+dana|mesec[a]?|meseci|godin[ae]?|nedeljno|nedelj[ae]?)",
        re.IGNORECASE,
    )
    for m in pat_relativni.finditer(tekst):
        vrednost = f"{m.group(1)} {m.group(2).strip()}"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 5. "narednog radnog dana" ───────────────────────────────────────────
    for m in re.finditer(r"\bnarednog\s+radnog\s+dana\b", tekst, re.IGNORECASE):
        _add("relativni", "narednog radnog dana", m.start(), m.end())

    # ─── 6. "u roku od N radnih dana" (fallback ako nije uhvaćen gore) ───────
    for m in re.finditer(r"\bu\s+roku\s+od\s+(\d+)\s+radnih?\s+dana\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} radnih dana"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 7. "rok od N dana" (skraćena forma) ─────────────────────────────────
    for m in re.finditer(r"\brok\s+od\s+(\d+)\s+(dan[a]?|dana|mesec[a]?|meseci)\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} {m.group(2)}"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 8. "u roku od N meseca" ─────────────────────────────────────────────
    for m in re.finditer(r"\bu\s+roku\s+od\s+(\d+)\s+mesec[ia]?\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} meseci"
        _add("relativni", vrednost, m.start(), m.end())

    # ─── 9. "N dana od" / "je N dana" (skraćena forma bez "u roku od") ───────
    for m in re.finditer(r"\b(?:je|iznosi|traje)\s+(\d+)\s+dan(?:a)?\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} dana"
        _add("relativni", vrednost, m.start(), m.end())

    for m in re.finditer(r"\b(\d+)\s+dan(?:a)?\s+od\b", tekst, re.IGNORECASE):
        vrednost = f"{m.group(1)} dana"
        _add("relativni", vrednost, m.start(), m.end())

    # Sort by position in text (preserving document order)
    results.sort(key=lambda r: tekst.find(r["vrednost"]))
    return results
