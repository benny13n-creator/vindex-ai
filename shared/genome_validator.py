# -*- coding: utf-8 -*-
"""
Vindex AI — Genome Verification Layer (Faza 1.3, 90-dnevni plan 2026-07-18)

Advisory, non-blocking, deterministicka provera Case Genome-a PRE snimanja.
Nula GPT/LLM poziva — cisto proverava strukturu i reference genoma naspram
podataka koji su vec ucitani (dokumenti predmeta), ne AI kritičar. Design
note: docs/architecture/PHASE_1_EXECUTION_CHECKLIST_2026-07-18.md, stavka 1.3.

Obrazac (arhitektonski, ne kod) preuzet iz analiza/validator.py: nikad ne
baca izuzetak, uvek vraca validan dict, sumnjive stavke se premestaju u
flag liste umesto da se tiho odbace. validate_law_refs se REUSE-uje
direktno (import), ne kopira.

Namerno iskljuceno iz v1 (nije zaboravljeno, procenjeno i odlozeno):
- argumenti_za/argumenti_protiv provenance — Genome nema clause_excerpt
  polje kao analiza/validator.py, provera bi trazila izmenu Genome sheme.
- stranke/svedoci/vestaci cross-referencing protiv teksta dokumenta —
  visok rizik laznih pozitiva (OCR varijante, srpska deklinacija imena).
- datumi_kljucni/rokovi_kriticni tekstualno poklapanje — visok rizik
  laznih pozitiva (datumi se cesto preformatiraju u ekstrakciji).
"""
from __future__ import annotations

import re
import time
from typing import Any

from analiza.validator import validate_law_refs

_DOK_PATTERN = re.compile(r"DOK-0*(\d+)", re.IGNORECASE)


def _validate_dokazi_rang(genome: dict, docs: list[dict]) -> list[dict]:
    """Hard-flag: dokazi_rang.naziv mora odgovarati stvarnom dokumentu predmeta."""
    poznati_nazivi = {(d.get("naziv_fajla") or "").strip().lower() for d in docs}
    flags = []
    for stavka in genome.get("dokazi_rang") or []:
        naziv = (stavka.get("naziv") or "").strip().lower()
        if naziv and naziv not in poznati_nazivi:
            flags.append({
                "polje": "dokazi_rang",
                "razlog": f"dokument '{stavka.get('naziv')}' ne postoji medju dokumentima predmeta",
                "stavka": stavka.get("naziv"),
            })
    return flags


def _validate_kontradikcije_lokacije(genome: dict, docs: list[dict]) -> list[dict]:
    """Hard-flag: DOK-XX reference u kontradikcijama moraju odgovarati stvarnim
    redni_broj vrednostima medju dokumentima predmeta."""
    poznati_brojevi = {
        int(d["redni_broj"]) for d in docs
        if str(d.get("redni_broj") or "").isdigit()
    }
    flags = []
    for k in genome.get("kontradikcije") or []:
        for polje in ("lokacija_1", "lokacija_2"):
            vrednost = k.get(polje) or ""
            m = _DOK_PATTERN.search(vrednost)
            if not m:
                continue
            broj = int(m.group(1))
            if broj not in poznati_brojevi:
                flags.append({
                    "polje": f"kontradikcije.{polje}",
                    "razlog": f"'{vrednost}' referencira DOK-{broj:02d} koji ne postoji medju dokumentima predmeta",
                    "stavka": vrednost,
                })
    return flags


def _validate_relevantni_zakoni(genome: dict) -> list[dict]:
    """Soft-flag: reuse analiza/validator.py validate_law_refs preko adaptera —
    Genome ima list[str], validate_law_refs ocekuje findings sa law_ref kljucem."""
    zakoni = ((genome.get("pravna_teorija") or {}).get("relevantni_zakoni")) or []
    if not zakoni:
        return []
    adapted = {"findings": [{"law_ref": z} for z in zakoni if z]}
    checked = validate_law_refs(adapted)
    flags = []
    for f in checked.get("findings", []):
        if f.get("unverified_law_ref"):
            flags.append({
                "polje": "pravna_teorija.relevantni_zakoni",
                "razlog": f"'{f.get('law_ref')}' nije prepoznat u poznatoj listi zakona (soft check — moze biti tacan, samo nepotvrdjen)",
                "stavka": f.get("law_ref"),
            })
    return flags


def _validate_snaga_konzistentnost(genome: dict) -> tuple[list[dict], list[dict]]:
    """Interna konzistentnost (ne provenance protiv dokumenata):
    - snaga_predmeta_procent ne sme da protivreci neto smeru snaga_faktori.
    - dokazi_rang.zvezdice ne sme daleko odstupati od round(snaga_score/20),
      formula koju sam ekstrakcioni prompt definise ali nikad ne proverava."""
    hard: list[dict] = []
    soft: list[dict] = []

    procent = genome.get("snaga_predmeta_procent")
    faktori = genome.get("snaga_faktori") or []
    if isinstance(procent, (int, float)) and faktori:
        neto = 0
        for f in faktori:
            try:
                neto += int(str(f.get("uticaj", "0")).replace("+", ""))
            except (ValueError, TypeError):
                continue
        if procent >= 65 and neto < 0:
            hard.append({
                "polje": "snaga_predmeta_procent",
                "razlog": f"procenat je visok ({procent}%) ali je neto uticaj snaga_faktori negativan ({neto})",
                "stavka": procent,
            })
        elif procent <= 35 and neto > 0:
            hard.append({
                "polje": "snaga_predmeta_procent",
                "razlog": f"procenat je nizak ({procent}%) ali je neto uticaj snaga_faktori pozitivan ({neto})",
                "stavka": procent,
            })

    for stavka in genome.get("dokazi_rang") or []:
        score = stavka.get("snaga_score")
        zvezdice = stavka.get("zvezdice")
        if isinstance(score, (int, float)) and isinstance(zvezdice, (int, float)):
            ocekivano = round(score / 20)
            if abs(ocekivano - zvezdice) >= 2:
                soft.append({
                    "polje": "dokazi_rang.zvezdice",
                    "razlog": f"'{stavka.get('naziv')}' ima {zvezdice} zvezdica ali score={score} implicira ~{ocekivano}",
                    "stavka": stavka.get("naziv"),
                })

    return hard, soft


def verify_genome(genome: dict, docs: list[dict]) -> dict[str, Any]:
    """Glavna ulazna tacka — Faza 1.3. Nula GPT poziva, nula I/O (docs je vec
    ucitan od strane pozivaoca). Nikad ne baca izuzetak — greska u jednoj
    proveri se preskace (logovana implicitno kroz prazan rezultat te
    provere), ne obara ostatak niti glavni zahtev.

    Vraca advisory rezultat — poziv ga upisuje u genome["_verifikacija"] i
    NASTAVLJA da snima genom bez obzira na odluku. 'require_review' je
    status, ne blokada."""
    start = time.monotonic()
    hard: list[dict] = []
    soft: list[dict] = []

    for fn, bucket in (
        (lambda: _validate_dokazi_rang(genome, docs), hard),
        (lambda: _validate_kontradikcije_lokacije(genome, docs), hard),
        (lambda: _validate_relevantni_zakoni(genome), soft),
    ):
        try:
            bucket.extend(fn())
        except Exception:
            pass

    try:
        k_hard, k_soft = _validate_snaga_konzistentnost(genome)
        hard.extend(k_hard)
        soft.extend(k_soft)
    except Exception:
        pass

    if hard:
        odluka = "require_review"
    elif soft:
        odluka = "approve_with_warning"
    else:
        odluka = "approve"

    return {
        "odluka": odluka,
        "hard_flags": hard,
        "soft_flags": soft,
        "provereno_u_ms": round((time.monotonic() - start) * 1000, 2),
    }
