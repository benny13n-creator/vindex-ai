# -*- coding: utf-8 -*-
"""
P3.1/P3.2 / Phase 4.1 — Deadline/rok ekstrakcija iz pravnih dokumenata.

Funkcija `ekstrahuj_rokove` parsira srpske datume i relativne rokove
iz pravnog teksta i vraća strukturirane dict-ove sa kontekstom i kategorijom.

Phase 4.1 dodaci:
  - `_extract_datum_dokumenta` — auto-detekcija datuma dokumenta
  - `_parse_trajanje_dana`     — konverzija relativnog roka u broj dana
  - `_kalkulisi_rok`           — kalkulacija konkretnog datuma + countdown
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

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


# ─── Phase 4.1: Auto-detekcija datuma dokumenta ──────────────────────────────

def _extract_datum_dokumenta(tekst: str) -> Optional[str]:
    """
    Detektuje datum dokumenta iz prvih 500 karaktera teksta.
    Vraća "DD.MM.YYYY" string ili None.

    Traži tipične pravne fraze: "Dana ...", "Beograd, ...", "doneta ...",
    "zaključen dana ..." i sl. Fallback: prvi DD.MM.YYYY u prvih 500 chars.
    """
    probe = tekst[:500]

    # Fraze koje prethode datumu dokumenta (redosled je bitan — specifičnije pre generičnih)
    phrase_patterns = [
        # "Dana DD.MM.YYYY" / "dana DD.MM.YYYY"
        r"\bdana\s+(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "datum presude/zaključenja/ugovora/dokumenta: DD.MM.YYYY"
        r"\bdatum\s+(?:presude|zaklju[čc][ie]?nja|ugovora|dokumenta)\s*[:\s]+(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "zaključen/zaključena dana DD.MM.YYYY"
        r"\bzaklju[čc]en[ao]?\s+(?:dana\s+)?(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "doneta/doneto/donet dana DD.MM.YYYY"
        r"\bdonet[ao]?\s+(?:dana\s+)?(\d{1,2}\.\d{1,2}\.\d{4})\b",
        # "Grad/Mesto, DD.MM.YYYY" — npr. "Beograd, 01.03.2025"
        r"\b[A-ZŠĐŽČĆ][a-zšđžčćA-ZŠĐŽČĆ]{2,20},\s*(\d{1,2}\.\d{1,2}\.\d{4})\b",
    ]

    for pat in phrase_patterns:
        m = re.search(pat, probe, re.IGNORECASE)
        if m:
            raw = m.group(1)
            parts = raw.split(".")
            if len(parts) == 3 and _valid_date_parts(parts):
                return f"{parts[0].zfill(2)}.{parts[1].zfill(2)}.{parts[2]}"

    # Fallback: prvi DD.MM.YYYY u prvih 500 chars
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", probe)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if _valid_date_parts([d, mo, y]):
            return f"{d.zfill(2)}.{mo.zfill(2)}.{y}"

    return None


def _valid_date_parts(parts: list) -> bool:
    """Osnovna validacija datumskih delova (nije puna validacija)."""
    try:
        d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
        return 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100
    except (ValueError, IndexError):
        return False


# ─── Phase 4.1: Konverzija relativnog roka u dane ────────────────────────────

def _parse_trajanje_dana(vrednost: str) -> Optional[int]:
    """
    Konvertuje relativni rok string u ekvivalentan broj dana.

    Primeri:
      "8 dana"           → 8
      "15 radnih dana"   → 15
      "3 meseca"         → 90
      "1 godina"         → 365
      "2 nedelje"        → 14
      "narednog radnog dana" → 1
    """
    v = vrednost.lower().strip()

    if "narednog radnog dana" in v:
        return 1

    m = re.search(r"(\d+)", v)
    if not m:
        return None
    n = int(m.group(1))

    if re.search(r"godin", v):
        return n * 365
    if re.search(r"mesec", v):
        return n * 30
    if re.search(r"nedelj", v):
        return n * 7
    # "dana", "dan", "radnih dana" — sve tretiramo kao kalendarske dane
    return n


# ─── Phase 4.1: Kalkulacija konkretnog datuma i countdowna ───────────────────

def _kalkulisi_rok(vrednost: str, tip: str, datum_dokumenta: Optional[str]) -> dict:
    """
    Vraća dict sa:
      konkretan_datum: "DD.MM.YYYY" | None
      istekao:         bool
      dana_do_roka:    int | None  (negativno = isteklo pre N dana)
    """
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    if tip == "apsolutni":
        try:
            rok_dt = datetime.strptime(vrednost, "%d.%m.%Y")
            delta  = (rok_dt - today).days
            return {
                "konkretan_datum":     vrednost,
                "konkretan_datum_iso": rok_dt.strftime("%Y-%m-%d"),
                "istekao":             delta < 0,
                "dana_do_roka":        delta,
            }
        except ValueError:
            return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None}

    elif tip == "relativni":
        if not datum_dokumenta:
            return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None}
        try:
            doc_dt = datetime.strptime(datum_dokumenta, "%d.%m.%Y")
            n_dana  = _parse_trajanje_dana(vrednost)
            if n_dana is None:
                return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None}
            rok_dt = doc_dt + timedelta(days=n_dana)
            delta  = (rok_dt - today).days
            return {
                "konkretan_datum":     rok_dt.strftime("%d.%m.%Y"),
                "konkretan_datum_iso": rok_dt.strftime("%Y-%m-%d"),
                "istekao":             delta < 0,
                "dana_do_roka":        delta,
            }
        except ValueError:
            return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None}

    return {"konkretan_datum": None, "konkretan_datum_iso": None, "istekao": False, "dana_do_roka": None}


# ─── Glavna funkcija ──────────────────────────────────────────────────────────

def ekstrahuj_rokove(tekst: str, datum_dokumenta: Optional[str] = None) -> list[dict]:
    """
    Parsira srpske datume i relativne rokove iz pravnog teksta.

    Returns list of dicts:
      {
        "tip":            "apsolutni" | "relativni",
        "vrednost":       "15.11.2025" | "8 dana",
        "kontekst":       "...tekst oko roka...",
        "kategorija":     "zastarelost" | "otkaz" | "zalba" | "podnesak" | "isplata" | "ostalo",
        "konkretan_datum": "DD.MM.YYYY" | None,
        "istekao":        True | False,
        "dana_do_roka":   int | None
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

    # ─── Deduplikacija: isti vrednost + prvih 50 chars konteksta ─────────────
    seen_keys: set[str] = set()
    deduped: list[dict] = []
    for r in results:
        key = r["vrednost"] + "|" + r["kontekst"][:50]
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(r)

    # ─── Sortiranje: apsolutni hronološki → relativni leksikografski ─────────
    def _sort_key(r: dict) -> tuple:
        if r["tip"] == "apsolutni":
            parts = r["vrednost"].split(".")
            if len(parts) == 3:
                return (0, f"{parts[2]}-{parts[1]}-{parts[0]}")
            return (0, r["vrednost"])
        return (1, r["vrednost"])

    deduped.sort(key=_sort_key)

    # ─── Phase 4.1: Dodaj kalkulisana polja na svaki rok ─────────────────────
    for r in deduped:
        kalk = _kalkulisi_rok(r["vrednost"], r["tip"], datum_dokumenta)
        r["konkretan_datum"] = kalk["konkretan_datum"]
        r["istekao"]         = kalk["istekao"]
        r["dana_do_roka"]    = kalk["dana_do_roka"]

    return deduped
