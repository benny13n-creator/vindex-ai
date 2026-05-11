# -*- coding: utf-8 -*-
"""
Drafting router — generate_draft(vrsta, opis) → dict.
Uses GPT-4o for field extraction; then fills the template deterministically.
"""
from __future__ import annotations

import json
import logging
import os
import re
from string import Formatter

from openai import OpenAI

from .compliance import formatiraj_violations, proveri_uskladjenost
from .templates import TEMPLATES

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def _call_openai(system: str, user: str, max_tokens: int = 2000) -> str:
    r = _get_client().chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
        max_tokens=max_tokens,
        timeout=30.0,
    )
    return (r.choices[0].message.content or "").strip()


def _ekstraktuj_json(tekst: str) -> dict:
    """Parsira JSON iz LLM odgovora, toleriše markdown code fences."""
    # Ukloni ```json ... ``` ili ``` ... ```
    cleaned = re.sub(r"```(?:json)?\s*", "", tekst).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Pokuša da pronađe {} blok
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _popuni_sablon(sablon: str, fields: dict) -> str:
    """
    Popunjava {PLACEHOLDER} u šablonu.
    Nepoznata polja dobijaju vrednost '[POPUNITI]'.
    """
    class _DefaultDict(dict):
        def __missing__(self, key: str) -> str:
            return f"[{key.replace('_', ' ')} — POPUNITI]"

    # Kolektuj sva polja iz šablona
    placeholders = {
        fname
        for _, fname, _, _ in Formatter().parse(sablon)
        if fname is not None
    }
    merged = _DefaultDict()
    for p in placeholders:
        merged[p] = fields.get(p.lower(), "")
        if merged[p] == "" or merged[p] is None:
            merged[p] = f"[{p.replace('_', ' ')} — POPUNITI]"

    return sablon.format_map(merged)


def _pripremi_ugovor_fields(fields: dict, vrsta: str) -> dict:
    """Kreira vrednosti za kondicionalne sekcije ugovornih šablona."""
    out = {k: (v if v is not None else "") for k, v in fields.items()}

    # PIB
    pib = out.get("poslodavac_pib", "")
    out["poslodavac_pib_clan"] = f", PIB: {pib}" if pib else ""

    # Probni rad
    probni = out.get("probni_rad", "")
    if probni:
        out["probni_rad_clan"] = (
            f"Zaposleni se prima na rad uz probni rad u trajanju od {probni}, "
            f"u skladu sa čl. 36 Zakona o radu."
        )
    else:
        out["probni_rad_clan"] = "Probni rad nije ugovoren."

    # Prekovremeni
    out["prekovremeni_clan"] = (
        "Prekovremeni rad može biti naložen u skladu sa čl. 53 Zakona o radu "
        "(max 8h nedeljno, 32h mesečno, 250h godišnje)."
    )

    # Godišnji odmor
    dani = out.get("godisnji_odmor_dani", "")
    if dani:
        out["godisnji_odmor_clan"] = (
            f"Zaposleni ima pravo na godišnji odmor u trajanju od {dani} radnih dana, "
            f"u skladu sa čl. 68–76 Zakona o radu."
        )
    else:
        out["godisnji_odmor_clan"] = (
            "Zaposleni ima pravo na godišnji odmor u skladu sa čl. 68–76 Zakona o radu "
            "(minimum 20 radnih dana)."
        )

    # Tajnost
    ima_tajnost = out.get("ima_tajnost") in (True, "true", "True", "1", 1)
    if ima_tajnost:
        rok = out.get("tajnost_rok", "")
        rok_tekst = f" u periodu od {rok} nakon prestanka radnog odnosa" if rok else " i nakon prestanka radnog odnosa"
        out["tajnost_clan"] = (
            f"Zaposleni je obavezan da čuva poverljive informacije Poslodavca{rok_tekst}, "
            f"u skladu sa čl. 83 Zakona o radu."
        )
    else:
        out["tajnost_clan"] = (
            "Zaposleni je obavezan da čuva poverljive informacije Poslodavca u skladu "
            "sa zakonom i opštim aktima Poslodavca."
        )

    # Konkurentska klauzula
    ima_konk = out.get("ima_konkurentsku") in (True, "true", "True", "1", 1)
    if ima_konk:
        trajanje = out.get("konkurentska_trajanje", "[TRAJANJE — POPUNITI]")
        naknada = out.get("konkurentska_naknada_procenat", "")
        naknada_tekst = (
            f" Za vreme trajanja zabrane Poslodavac isplaćuje Zaposlenom naknadu "
            f"od {naknada}% poslednje zarade mesečno."
            if naknada else ""
        )
        out["konkurentska_clan"] = (
            f"Zaposleni se obavezuje da po prestanku radnog odnosa neće raditi za "
            f"konkurentske firme niti osnivati preduzeće u istoj delatnosti u periodu "
            f"od {trajanje}, u skladu sa čl. 161–162 Zakona o radu.{naknada_tekst}"
        )
    else:
        out["konkurentska_clan"] = "Konkurentska klauzula nije ugovorena."

    # Bonus
    bonus = out.get("bonus_procenat", "")
    if bonus:
        out["bonus_clan"] = (
            f"Zaposleni može ostvariti pravo na varijabilni deo zarade (bonus) "
            f"do {bonus}% osnovne zarade, na osnovu procene radnog učinka."
        )
    else:
        out["bonus_clan"] = ""

    return out


def _pripremi_sporazum_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    ima_otp = out.get("ima_otpremninu") in (True, "true", "True", "1", 1)
    if ima_otp:
        iznos = out.get("otpremnina_iznos", "[IZNOS — POPUNITI]")
        out["otpremnina_clan"] = (
            f"Poslodavac se obavezuje da Zaposlenom isplati otpremninu u iznosu "
            f"od {iznos} dinara."
        )
    else:
        out["otpremnina_clan"] = ""

    napomena = out.get("napomena", "")
    out["napomena_clan"] = napomena if napomena else ""
    return out


def _pripremi_punomocje_fields(fields: dict) -> dict:
    out = {k: (v if v is not None else "") for k, v in fields.items()}
    ima_sup = out.get("ima_supstituciju") in (True, "true", "True", "1", 1)
    out["supstitucija_clan"] = (
        "Punomoćnik je ovlašćen da izda supstituciono punomoćje."
        if ima_sup else
        "Punomoćnik nije ovlašćen da izda supstituciono punomoćje."
    )
    return out


def _pripremi_fields(fields: dict, vrsta: str) -> dict:
    if vrsta in ("ugovor_neodredjeno", "ugovor_odredjeno"):
        return _pripremi_ugovor_fields(fields, vrsta)
    if vrsta == "sporazumni_raskid":
        return _pripremi_sporazum_fields(fields)
    if vrsta == "punomocje":
        return _pripremi_punomocje_fields(fields)
    return {k: (v if v is not None else "") for k, v in fields.items()}


def generate_draft(vrsta: str, opis: str) -> dict:
    """
    Generiše strukturiran nacrt dokumenta.

    vrsta  — ključ iz TEMPLATES registra
    opis   — slobodan opis od korisnika

    Vraća {"status": "success", "data": tekst} ili {"status": "error", "message": ...}.
    """
    tpl = TEMPLATES.get(vrsta)
    if tpl is None:
        return {
            "status": "error",
            "message": f"Nepoznat tip dokumenta: '{vrsta}'. "
                       f"Dostupni tipovi: {', '.join(TEMPLATES.keys())}.",
        }

    try:
        # ── 1. Ekstrakcija polja ─────────────────────────────────────────────
        system_p = tpl["ekstrakcioni_prompt"]
        user_p = f"OPIS:\n{opis}"
        raw_json = _call_openai(system_p, user_p, max_tokens=800)
        fields = _ekstraktuj_json(raw_json)

        # ── 2. Priprema kondicionalnih sekcija ───────────────────────────────
        fields_ready = _pripremi_fields(fields, vrsta)

        # ── 3. Popuni šablon ─────────────────────────────────────────────────
        sablon = tpl["sablon"]
        nacrt_tekst = _popuni_sablon(sablon, fields_ready)

        # ── 4. Compliance check ──────────────────────────────────────────────
        compliance_tip = tpl.get("compliance_tip")
        violations: list[dict] = []
        if compliance_tip == "ugovor_o_radu":
            violations = proveri_uskladjenost(fields, vrsta)
        compliance_tekst = formatiraj_violations(violations)

        return {
            "status": "success",
            "data": nacrt_tekst + compliance_tekst,
        }

    except Exception:
        logger.exception("Greška u generate_draft (vrsta=%s)", vrsta)
        return {
            "status": "error",
            "message": "Sistem je trenutno zauzet. Pokušajte ponovo.",
        }
