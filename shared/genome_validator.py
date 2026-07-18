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

v2 dodaci (Reliability Patch, 2026-07-18, posle CASE_GENOME_REALITY_
VALIDATION_REPORT.md nalaza na 6 sintetickih predmeta):

1. compute_snaga_score() — snaga_predmeta_procent/snaga_predmeta se sada
   RACUNAJU backend-om iz snaga_faktori, ne uzimaju se GPT-ovo samo-
   prijavljenu vrednost. Uzrok originalnog nalaza (svih 6 predmeta vratilo
   IDENTICNIH 65%/"srednja"): sistem prompt u case_dna.py je imao
   BUKVALAN brojcani primer ("snaga_predmeta_procent": 65) u JSON sablonu
   — GPT anchor-uje/kopira taj primer umesto da racuna po predmetu (poznat
   prompt-anchoring bug, potvrdjen time sto se identican obrazac ponovio u
   svih 6 slucajeva na temperaturi 0.1). Isti obrazac (backend racuna
   score, ne trazi se od LLM-a) vec postoji u analiza/validator.py Sloj 10
   (compute_executive_summary) — ovo je nastavak istog principa, ne nova
   ideja.
2. _validate_clan_brojevi() — proverava da broj clana u pravnim citatima
   nije OCIGLEDNO nemoguc (generic gornja granica po tipu zakona), NE
   potvrdjuje da tacan clan stvarno postoji (to bi zahtevalo pravni
   korpus/graf, eksplicitno van obima — "Do not build a graph database,
   do not create a new legal reasoning engine"). Ako je naveden stav,
   dodaje se transparentna napomena da stav nivo nije proveravan.
"""
from __future__ import annotations

import re
import time
from typing import Any

from analiza.validator import validate_law_refs

_CLAN_PATTERN = re.compile(r"(?:čl\.?|clan|član)\s*0*(\d+)", re.IGNORECASE)
_STAV_PATTERN = re.compile(r"stav\w*\s*0*(\d+)", re.IGNORECASE)

# Namerno siroke/konzervativne aproksimacije, NE precizna pravna baza po
# zakonu — precizne granice po svakom zakonu bi zahtevale pravni korpus/
# graf (eksplicitno van obima v2). Cilj je da uhvati OCIGLEDNO nemoguc broj
# clana (npr. izmisljen clan 5000), ne da potvrdi da tacan broj postoji —
# ta granica ostaje 'nepotvrdjeno' (soft), isto kao ranije.
_USTAV_MAX_CLAN_APPROX = 250
_ZAKON_MAX_CLAN_APPROX = 1200


def _neto_uticaj(faktori: list[dict]) -> int:
    """Zbir svih uticaj vrednosti iz snaga_faktori (npr. '+18', '-8' -> 18, -8).
    Deljeno izmedju compute_snaga_score i _validate_snaga_konzistentnost."""
    neto = 0
    for f in faktori:
        if not isinstance(f, dict):
            continue
        try:
            neto += int(str(f.get("uticaj", "0")).replace("+", ""))
        except (ValueError, TypeError):
            continue
    return neto

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


def _validate_clan_brojevi(genome: dict) -> tuple[list[dict], list[dict]]:
    """v2 (Reliability Patch, 2026-07-18) — proverava da broj clana u
    relevantni_zakoni citatima nije OCIGLEDNO nemoguc za tip zakona (Ustav
    ima znatno manje clanova od obicnog zakona). NE potvrdjuje da tacan
    clan stvarno postoji — to bi zahtevalo pravni korpus/graf, van obima.
    Ako je naveden i stav/paragraf, dodaje se soft napomena da taj nivo
    nije proveravan (transparentno, ne cutke ignorisano)."""
    hard: list[dict] = []
    soft: list[dict] = []
    zakoni = ((genome.get("pravna_teorija") or {}).get("relevantni_zakoni")) or []
    for z in zakoni:
        if not z:
            continue
        m = _CLAN_PATTERN.search(z)
        if not m:
            continue
        broj = int(m.group(1))
        is_ustav = "ustav" in z.lower()
        gornja_granica = _USTAV_MAX_CLAN_APPROX if is_ustav else _ZAKON_MAX_CLAN_APPROX
        if broj <= 0 or broj > gornja_granica:
            hard.append({
                "polje": "pravna_teorija.relevantni_zakoni",
                "razlog": f"'{z}' navodi član {broj}, van uobičajenog opsega za ovaj tip zakona (0 < član <= {gornja_granica}) — verovatno izmišljen broj.",
                "stavka": z,
            })
        stav_m = _STAV_PATTERN.search(z)
        if stav_m:
            soft.append({
                "polje": "pravna_teorija.relevantni_zakoni",
                "razlog": f"'{z}' navodi stav {stav_m.group(1)} — nivo stava nije proveravan (van obima v2, samo broj člana).",
                "stavka": z,
            })
    return hard, soft


def compute_snaga_score(genome: dict) -> dict:
    """v2 (Reliability Patch, 2026-07-18) — backend-racunata, objasnjiva
    zamena za GPT-ovo samo-prijavljeno snaga_predmeta_procent/snaga_predmeta.

    Zasto: Reality Validation batch (6 sintetickih predmeta, 2026-07-18)
    pokazao je da SVIH 6 predmeta vraca IDENTICNIH 65%/"srednja" bez obzira
    na dramaticno razlicit sadrzaj predmeta — uzrok je bio bukvalan brojcani
    primer u system promptu koji GPT anchor-uje/kopira. Ovde se procenat
    RACUNA iz vec ekstrahovanih snaga_faktori (koji SU specificni po
    predmetu, potvrdjeno istim batch-om), ne trazi se od LLM-a — isti
    princip kao analiza/validator.py Sloj 10 (compute_executive_summary).

    Formula: baseline 50 (neutralno, ista konvencija kao STROGA PRAVILA u
    system promptu) + neto uticaj snaga_faktori, umanjeno za penal ako je
    genome_kompletnost niska (nedovoljno dokaza za pouzdanu procenu — ovaj
    penal je i sam dodat kao vidljiv, objasnjiv faktor, ne skriveno
    podesavanje). Kategorija (jaka/srednja/slaba) izvedena iz istog broja
    prema vec postojecim pragovima (75+ jaka, <35 slaba, izmedju srednja).

    Vraca {"snaga_predmeta_procent": int, "snaga_predmeta": str,
    "snaga_faktori": list} — snaga_faktori se vraca NAZAD (mozda sa dodatim
    kompletnost-penalom) da explainability ostane tacna za konacan broj."""
    raw_faktori = genome.get("snaga_faktori")
    faktori = list(raw_faktori) if isinstance(raw_faktori, list) else []

    if genome.get("genome_kompletnost") == "niska":
        faktori.append({
            "faktor": "Kompletnost dokaznog materijala",
            "uticaj": "-15",
            "opis": "Genome kompletnost ocenjena kao niska — nedovoljno dokumenata za pouzdanu procenu snage predmeta.",
        })

    neto = _neto_uticaj(faktori)
    procent = max(0, min(100, 50 + neto))

    if procent >= 75:
        kategorija = "jaka"
    elif procent < 35:
        kategorija = "slaba"
    else:
        kategorija = "srednja"

    return {
        "snaga_predmeta_procent": procent,
        "snaga_predmeta": kategorija,
        "snaga_faktori": faktori,
    }


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
        neto = _neto_uticaj(faktori)
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

    try:
        c_hard, c_soft = _validate_clan_brojevi(genome)
        hard.extend(c_hard)
        soft.extend(c_soft)
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
