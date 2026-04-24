# -*- coding: utf-8 -*-
"""
Vindex AI — Semantic Chunker (Sprint 1)

Deli tekst zakona strukturalno: po članovima, zatim po stavovima unutar člana.
Mali chunk (200-300 karaktera) = jedan stav → koristi se za embedding/search.
Parent text (ceo član, ≤3000 karaktera) → čuva se u metapodacima, šalje LLM-u.
"""

import re
import hashlib
from pathlib import Path

# Mapiranje punih naziva zakona → kratke oznake za parent_id
ZAKON_SHORTCODES: dict[str, str] = {
    "zakon o obligacionim odnosima":                          "ZOO",
    "zakon o radu":                                           "ZR",
    "porodicni zakon":                                        "PZ",
    "zakon o parnicnom postupku":                             "ZPP",
    "zakonik o krivicnom postupku":                           "ZKP",
    "zakon o izvrsenju i obezbedjenju":                       "ZIO",
    "zakon o nasledjivanju":                                  "ZN",
    "zakon o opstem upravnom postupku":                       "ZOUP",
    "zakon o upravnim sporovima":                             "ZUS",
    "zakon o vanparnicnom postupku":                          "ZVP",
    "zakon o privrednim drustvima":                           "ZPD",
    "ustav republike srbije":                                 "USTAV",
    "zakon o zastiti podataka o licnosti":                    "ZZPL",
    "zakon o zastiti potrosaca":                              "ZZP",
    "zakon o digitalnoj imovini":                             "ZDI",
    "zakon o sprecavanju pranja novca i finansiranja terorizma": "ZSPNFT",
    "krivicni zakonik":                                       "KZ",
    "zakon o porezu na dohodak gradjana":                     "ZPDG",
    # Already-short codes remain as-is
    "KZ":   "KZ",
    "ZPDG": "ZPDG",
    "ZDI":  "ZDI",
}

MIN_STAV_DUZINA  = 60    # minimalna dužina stava da bi ušao kao chunk
MAX_STAV_DUZINA  = 300   # hard limit za mali (search) chunk
MAX_PARENT_DUZINA = 3000  # hard limit za parent text koji ide LLM-u


def shortcode(zakon_naziv: str) -> str:
    """Vraća kratku oznaku zakona."""
    return ZAKON_SHORTCODES.get(zakon_naziv, zakon_naziv.upper()[:6])


def _chunk_id(zakon: str, clan_num: str, stav: int) -> str:
    """Deterministički MD5 ID za v2 chunk — nikad ne kolizuje sa v1 vektorima."""
    key = f"v2|{zakon}|{clan_num}|{stav}"
    return hashlib.md5(key.encode()).hexdigest()


def _podeli_na_stavove(clan_tekst: str) -> list[str]:
    """
    Deli tekst člana na stavove.

    Prioritet prepoznavanja:
    1. Eksplicitni broj stava: (1), (2)... ili 1. 2. na početku reda
    2. Prazan red kao granica stava
    3. Ako ništa → seckanje po veličini (~250 karaktera)
    """
    # Pattern: (1) tekst, (2) tekst ili 1. tekst na početku reda
    numerirani = re.compile(
        r'(?m)(?=^\s*[\(\[]?\d{1,2}[\)\]]?[\.\s])',
        re.UNICODE,
    )
    delovi = numerirani.split(clan_tekst)
    stavovi = [s.strip() for s in delovi if len(s.strip()) >= MIN_STAV_DUZINA]

    if len(stavovi) >= 2:
        return [s[:MAX_STAV_DUZINA] for s in stavovi]

    # Fallback: razdvoj po praznim redovima
    po_redovima = [s.strip() for s in re.split(r'\n\s*\n', clan_tekst) if len(s.strip()) >= MIN_STAV_DUZINA]
    if len(po_redovima) >= 2:
        return [s[:MAX_STAV_DUZINA] for s in po_redovima]

    # Fallback: seckanje po dužini
    rec = clan_tekst.split()
    chunkovi, trenutni, duzina = [], [], 0
    for r in rec:
        trenutni.append(r)
        duzina += len(r) + 1
        if duzina >= 250:
            chunkovi.append(' '.join(trenutni))
            trenutni, duzina = [], 0
    if trenutni:
        chunkovi.append(' '.join(trenutni))

    return [s[:MAX_STAV_DUZINA] for s in chunkovi if len(s) >= MIN_STAV_DUZINA] or [clan_tekst[:MAX_STAV_DUZINA]]


def podeli_zakon_na_chunkove(tekst: str, zakon_naziv: str) -> list[dict]:
    """
    Glavna funkcija: parsira tekst zakona i vraća listu chunk rečnika.

    Svaki rečnik:
    {
      "id":   str (MD5, v2 prefix),
      "text": str (tekst za embedding, ≤300 karaktera),
      "metadata": {
          "zakon":        str  (kratka oznaka, npr. "ZOO"),
          "clan":         int  (broj člana),
          "stav":         int  (redni broj stava unutar člana),
          "parent_id":    str  (npr. "ZOO_200"),
          "parent_text":  str  (ceo clan, ≤3000 kar — šalje se LLM-u),
          "tekst_preview": str (prvih 100 karaktera stava),
          # Backward-compat polja (koriste LAW_HINTS filter u retrieve.py):
          "law":     str,
          "article": str,
          "text":    str,
      }
    }
    """
    sc = shortcode(zakon_naziv)

    # Prepoznaj granice članova
    clan_pattern = re.compile(
        r'(?m)^[ \t]*(?:Član|ČLAN|Čl\.|ČL\.)\s+(\d+[a-zA-Zа-яА-Я]?)\b',
        re.UNICODE,
    )
    matches = list(clan_pattern.finditer(tekst))

    if not matches:
        stav = tekst[:MAX_STAV_DUZINA]
        return [{
            "id":   _chunk_id(zakon_naziv, "0", 0),
            "text": f"ZAKON: {zakon_naziv}\n\n{stav}",
            "metadata": {
                "zakon": sc, "clan": 0, "stav": 0,
                "parent_id":    f"{sc}_0",
                "parent_text":  tekst[:MAX_PARENT_DUZINA],
                "tekst_preview": stav[:100],
                "law": zakon_naziv, "article": "Opšte odredbe", "text": stav,
            },
        }]

    vidjeni_clanovi: set[str] = set()
    chunkovi: list[dict] = []

    for i, m in enumerate(matches):
        broj_str = m.group(1)
        label    = f"Član {broj_str}"

        # Deduplikacija — zadržavamo prvu pojavu
        if label in vidjeni_clanovi:
            continue
        # Preskoči appendix verzije ("[sX]" anotacije)
        pos_pre = m.start() - 1
        if pos_pre >= 0 and tekst[pos_pre] in '[]':
            continue
        vidjeni_clanovi.add(label)

        try:
            clan_int = int(re.sub(r'[^0-9]', '', broj_str))
        except ValueError:
            clan_int = 0

        pocetak = m.start()
        kraj    = matches[i + 1].start() if i + 1 < len(matches) else len(tekst)
        clan_tekst = tekst[pocetak:kraj].strip()

        if len(clan_tekst) < MIN_STAV_DUZINA:
            continue

        parent_id   = f"{sc}_{broj_str}"
        parent_text = clan_tekst[:MAX_PARENT_DUZINA]

        stavovi = _podeli_na_stavove(clan_tekst)

        for stav_idx, stav_tekst in enumerate(stavovi, start=1):
            embed_text = f"ZAKON: {zakon_naziv}\n{label}\n\n{stav_tekst}"
            chunkovi.append({
                "id":   _chunk_id(zakon_naziv, broj_str, stav_idx),
                "text": embed_text,
                "metadata": {
                    "zakon":        sc,
                    "clan":         clan_int,
                    "stav":         stav_idx,
                    "parent_id":    parent_id,
                    "parent_text":  parent_text,
                    "tekst_preview": stav_tekst[:100],
                    # Backward-compat
                    "law":     zakon_naziv,
                    "article": label,
                    "text":    stav_tekst,
                },
            })

    return chunkovi
