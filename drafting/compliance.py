# -*- coding: utf-8 -*-
"""
Compliance checks for employment contracts (ugovor_o_radu).
All checks are deterministic — no LLM calls.

Each rule returns a dict with:
  pravilo  — short rule identifier
  zakon    — law reference
  status   — "ok" | "krsi" | "upozorenje"
  poruka   — human-readable explanation in Serbian
"""
from __future__ import annotations


# ── Konstante (ZR vrednosti) ──────────────────────────────────────────────────
ZR_PROBNI_RAD_MAX_MESECI = 6         # ZR čl. 36
ZR_OTKAZNI_ROK_MIN_DANA = 8          # ZR čl. 189
ZR_KONKURENTSKA_MAX_GODINA = 2       # ZR čl. 162
ZR_GODISNJI_ODMOR_MIN_DANA = 20      # ZR čl. 69
ZR_PREKOVREMENI_MAX_NEDELJNO_H = 8   # ZR čl. 53 st. 1
ZR_PREKOVREMENI_MAX_GODISNJE_H = 250 # ZR čl. 53 st. 3
MIN_ZARADA_BRUTO_RSD = 74_000        # okvirna minimalna bruto zarada 2025
ZR_ODREDJENO_MAX_MESECI = 24         # ZR čl. 37


def _parse_mesece(vrednost: str) -> float | None:
    """Pokušava da parsira trajanje u mesecima iz stringa poput '3 meseca', '6 months', '1 godina'."""
    if not vrednost:
        return None
    v = vrednost.lower().strip()
    try:
        # Ako je samo broj
        return float(v)
    except ValueError:
        pass
    import re
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mesec|month|god|year|nedel|week)", v)
    if not m:
        return None
    broj = float(m.group(1).replace(",", "."))
    jedinica = m.group(2)
    if "god" in jedinica or "year" in jedinica:
        return broj * 12
    if "nedel" in jedinica or "week" in jedinica:
        return broj / 4.33
    return broj  # meseci


def _parse_dane(vrednost: str) -> float | None:
    """Pokušava da parsira broj dana iz stringa poput '15 radnih dana', '8 dana'."""
    if not vrednost:
        return None
    import re
    m = re.search(r"(\d+(?:[.,]\d+)?)", vrednost)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def _parse_broj(vrednost) -> float | None:
    """Parsira čist broj (int ili str)."""
    if vrednost is None or vrednost == "":
        return None
    try:
        return float(str(vrednost).replace(",", ".").replace(".", "", str(vrednost).count(".") - 1))
    except (ValueError, AttributeError):
        return None


def _ok(pravilo: str, zakon: str, poruka: str) -> dict:
    return {"pravilo": pravilo, "zakon": zakon, "status": "ok", "poruka": poruka}


def _krsi(pravilo: str, zakon: str, poruka: str) -> dict:
    return {"pravilo": pravilo, "zakon": zakon, "status": "krsi", "poruka": poruka}


def _upozorenje(pravilo: str, zakon: str, poruka: str) -> dict:
    return {"pravilo": pravilo, "zakon": zakon, "status": "upozorenje", "poruka": poruka}


# ── Pravila ───────────────────────────────────────────────────────────────────

def _proveri_probni_rad(fields: dict) -> dict | None:
    vrednost = fields.get("probni_rad", "")
    if not vrednost:
        return None
    meseci = _parse_mesece(str(vrednost))
    if meseci is None:
        return _upozorenje(
            "probni_rad", "ZR čl. 36",
            f"Nije moguće proveriti trajanje probnog rada ('{vrednost}'). "
            f"Maksimum je {ZR_PROBNI_RAD_MAX_MESECI} meseci."
        )
    if meseci > ZR_PROBNI_RAD_MAX_MESECI:
        return _krsi(
            "probni_rad", "ZR čl. 36",
            f"Probni rad od {vrednost} prelazi zakonski maksimum od {ZR_PROBNI_RAD_MAX_MESECI} meseci (ZR čl. 36)."
        )
    return _ok(
        "probni_rad", "ZR čl. 36",
        f"Probni rad od {vrednost} je u skladu sa ZR čl. 36 (max {ZR_PROBNI_RAD_MAX_MESECI} meseci)."
    )


def _proveri_otkazni_rok(fields: dict, kljuc: str, strana: str) -> dict | None:
    vrednost = fields.get(kljuc, "")
    if not vrednost:
        return None
    dana = _parse_dane(str(vrednost))
    if dana is None:
        return _upozorenje(
            f"otkazni_rok_{kljuc}", "ZR čl. 189",
            f"Nije moguće proveriti otkazni rok {strana} ('{vrednost}'). "
            f"Minimum je {ZR_OTKAZNI_ROK_MIN_DANA} dana."
        )
    if dana < ZR_OTKAZNI_ROK_MIN_DANA:
        return _krsi(
            f"otkazni_rok_{kljuc}", "ZR čl. 189",
            f"Otkazni rok {strana} od {vrednost} kraći je od zakonskog minimuma "
            f"od {ZR_OTKAZNI_ROK_MIN_DANA} dana (ZR čl. 189)."
        )
    return _ok(
        f"otkazni_rok_{kljuc}", "ZR čl. 189",
        f"Otkazni rok {strana} od {vrednost} ispunjava minimum ZR čl. 189 ({ZR_OTKAZNI_ROK_MIN_DANA} dana)."
    )


def _proveri_konkurentsku_klauzulu(fields: dict) -> dict | None:
    if not fields.get("ima_konkurentsku") in (True, "true", "True", "1", 1):
        return None
    vrednost = fields.get("konkurentska_trajanje", "")
    if not vrednost:
        return _upozorenje(
            "konkurentska_klauzula", "ZR čl. 162",
            "Konkurentska klauzula postoji ali trajanje nije navedeno. "
            f"Zakonski maksimum je {ZR_KONKURENTSKA_MAX_GODINA} godine."
        )
    meseci = _parse_mesece(str(vrednost))
    if meseci is None:
        return _upozorenje(
            "konkurentska_klauzula", "ZR čl. 162",
            f"Nije moguće proveriti trajanje konkurentske klauzule ('{vrednost}'). "
            f"Maksimum je {ZR_KONKURENTSKA_MAX_GODINA} godine."
        )
    if meseci > ZR_KONKURENTSKA_MAX_GODINA * 12:
        return _krsi(
            "konkurentska_klauzula", "ZR čl. 162",
            f"Konkurentska klauzula od {vrednost} prelazi zakonski maksimum od "
            f"{ZR_KONKURENTSKA_MAX_GODINA} godine (ZR čl. 162 st. 1)."
        )
    return _ok(
        "konkurentska_klauzula", "ZR čl. 162",
        f"Konkurentska klauzula od {vrednost} u skladu je sa ZR čl. 162 "
        f"(max {ZR_KONKURENTSKA_MAX_GODINA} godine)."
    )


def _proveri_godisnji_odmor(fields: dict) -> dict | None:
    vrednost = fields.get("godisnji_odmor_dani", "")
    if not vrednost:
        return None
    dana = _parse_broj(vrednost)
    if dana is None:
        return _upozorenje(
            "godisnji_odmor", "ZR čl. 69",
            f"Nije moguće proveriti godišnji odmor ('{vrednost}'). "
            f"Minimum je {ZR_GODISNJI_ODMOR_MIN_DANA} radnih dana."
        )
    if dana < ZR_GODISNJI_ODMOR_MIN_DANA:
        return _krsi(
            "godisnji_odmor", "ZR čl. 69",
            f"Godišnji odmor od {int(dana)} radnih dana manji je od zakonskog minimuma "
            f"od {ZR_GODISNJI_ODMOR_MIN_DANA} radnih dana (ZR čl. 69)."
        )
    return _ok(
        "godisnji_odmor", "ZR čl. 69",
        f"Godišnji odmor od {int(dana)} radnih dana ispunjava minimum ZR čl. 69 "
        f"({ZR_GODISNJI_ODMOR_MIN_DANA} radnih dana)."
    )


def _proveri_minimalnu_zaradu(fields: dict) -> dict | None:
    vrednost = fields.get("osnovna_zarada", "")
    if not vrednost:
        return None
    iznos = _parse_broj(str(vrednost).replace(".", "").replace(",", ""))
    if iznos is None:
        return _upozorenje(
            "minimalna_zarada", "ZR čl. 111",
            f"Nije moguće proveriti iznos zarade ('{vrednost}'). "
            f"Minimalna bruto zarada je ~{MIN_ZARADA_BRUTO_RSD:,} RSD."
        )
    if iznos < MIN_ZARADA_BRUTO_RSD:
        return _krsi(
            "minimalna_zarada", "ZR čl. 111",
            f"Osnovna zarada od {int(iznos):,} RSD bruto niža je od okvirne minimalne zarade "
            f"od {MIN_ZARADA_BRUTO_RSD:,} RSD bruto (ZR čl. 111 i Uredba o minimalnoj ceni rada)."
        )
    return _ok(
        "minimalna_zarada", "ZR čl. 111",
        f"Osnovna zarada od {int(iznos):,} RSD bruto iznad je minimalne zarade."
    )


def _proveri_odredjeno_trajanje(fields: dict) -> dict | None:
    vrednost = fields.get("trajanje_odredjeno", "")
    if not vrednost:
        return None
    meseci = _parse_mesece(str(vrednost))
    if meseci is None:
        return _upozorenje(
            "odredjeno_trajanje", "ZR čl. 37",
            f"Nije moguće proveriti trajanje ugovora na određeno ('{vrednost}'). "
            f"Maksimum je {ZR_ODREDJENO_MAX_MESECI} meseci."
        )
    if meseci > ZR_ODREDJENO_MAX_MESECI:
        return _krsi(
            "odredjeno_trajanje", "ZR čl. 37",
            f"Ugovor na određeno vreme od {vrednost} prelazi zakonski maksimum od "
            f"{ZR_ODREDJENO_MAX_MESECI} meseci (ZR čl. 37 st. 4)."
        )
    return _ok(
        "odredjeno_trajanje", "ZR čl. 37",
        f"Trajanje ugovora od {vrednost} u skladu je sa ZR čl. 37 "
        f"(max {ZR_ODREDJENO_MAX_MESECI} meseci)."
    )


# ── Javna funkcija ────────────────────────────────────────────────────────────

def proveri_uskladjenost(fields: dict, vrsta: str) -> list[dict]:
    """
    Proverava usklađenost ugovornih odredbi sa ZR.
    Vraća listu rezultata (može biti prazna ako nema proverljivih podataka).
    """
    rezultati: list[dict] = []

    if vrsta in ("ugovor_neodredjeno", "ugovor_odredjeno"):
        for r in [
            _proveri_probni_rad(fields),
            _proveri_otkazni_rok(fields, "otkazni_rok_zaposleni", "zaposlenog"),
            _proveri_otkazni_rok(fields, "otkazni_rok_poslodavac", "poslodavca"),
            _proveri_konkurentsku_klauzulu(fields),
            _proveri_godisnji_odmor(fields),
            _proveri_minimalnu_zaradu(fields),
        ]:
            if r is not None:
                rezultati.append(r)

    if vrsta == "ugovor_odredjeno":
        r = _proveri_odredjeno_trajanje(fields)
        if r is not None:
            rezultati.append(r)

    return rezultati


def formatiraj_violations(violations: list[dict]) -> str:
    """Formatuje listu violations u tekst za dodavanje na kraj nacrta."""
    if not violations:
        return ""
    krsenja = [v for v in violations if v["status"] == "krsi"]
    upozorenja = [v for v in violations if v["status"] == "upozorenje"]
    oks = [v for v in violations if v["status"] == "ok"]

    linije = ["\n\n---\n\n### VINDEX COMPLIANCE ANALIZA (ZR)\n"]
    if krsenja:
        linije.append("**⚠ KRŠENJA ZAKONSKOG MINIMUMA:**")
        for v in krsenja:
            linije.append(f"• [{v['zakon']}] {v['poruka']}")
    if upozorenja:
        linije.append("\n**! UPOZORENJA — proveriti ručno:**")
        for v in upozorenja:
            linije.append(f"• [{v['zakon']}] {v['poruka']}")
    if oks:
        linije.append("\n**✓ PROVERENE ODREDBE:**")
        for v in oks:
            linije.append(f"• [{v['zakon']}] {v['poruka']}")

    linije.append(
        "\n> Ova compliance analiza je isključivo informativna. "
        "Konačnu pravnu ocenu daje ovlašćeni advokat."
    )
    return "\n".join(linije)
