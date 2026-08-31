# -*- coding: utf-8 -*-
"""
Vindex AI — shared/contradiction_materializer.py

A014 (2026-08-30) — MATERIJALIZACIJA: sirov Genome izlaz -> razrešen domen objekat.

## Zašto je ovo zaseban sloj

A014 §8 traži da persistence sloj NIKAD sam ne pogađa tvrdnje. Adapter
(`services/v2_contradiction_persistence.py`) prima **već razrešen** objekat i ne
zna ni za `lokacija_1`, ni za `DOK-NN`, ni za `opis`. Ovaj modul je jedino mesto
na kojem sirovi LLM izlaz postaje domen objekat, i jedino mesto koje sme da
kaže „ovaj predlog ne prolazi".

    sirov kontradikcije[]  ->  oblik  ->  claim_refs  ->  vlasnistvo  ->  kandidat
                                 |            |              |
                              odbijen      odbijen        odbijen

## Šta NIJE identitet — i zato se ovde ne koristi za razrešavanje

`opis`, `issue_label`, `lokacija_1/2`, `dokument_id_1/2` prolaze kroz ovaj modul
**samo kao provenijencija i prikaz**. Nijedno od njih ne učestvuje u odluci koja
je tvrdnja član kontradikcije. Ta odluka dolazi isključivo iz `claim_refs`, koje
model bira iz kataloga (`shared/claim_catalog.py`).

## Vokabular relacija se NE duplira

`RELACIJE` je već kanonski definisan u `shared/issue_v2.py`. Ovde se uvozi, ne
prepisuje — dva izraza za isti pojam značila bi dva vlasnika istog pravila.

## Odnos prema `REVIEW_REQUIRED`

Ovaj modul ga NE proizvodi. A014 §10 razdvaja:

    nepoznata/neispravna referenca   -> ODBIJEN ovde (producer validation error)
    tvrdnja iz drugog predmeta       -> ODBIJEN ovde (hard fail)
    manje od 2 razlicite tvrdnje     -> ODBIJEN ovde (hard fail)
    nema dokaza o kontinuitetu       -> REVIEW_REQUIRED, ali TEK u domenu
                                        (`shared/issue_v2.razresi_kontinuitet`)

`REVIEW_REQUIRED` je ishod o KONTINUITETU, nikad izgovor za nerazrešen identitet.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from shared.claim_catalog import GreskaKataloga, razresi_reference
from shared.issue_v2 import MIN_TVRDNJI, RELACIJE

logger = logging.getLogger("vindex.contradiction_materializer")

# Razlozi odbijanja — stabilni, da bi testovi i log mogli da ih razlikuju.
ODBIJEN_OBLIK = "MALFORMED"
ODBIJEN_RELACIJA = "UNKNOWN_RELATION"
ODBIJEN_REFERENCA = "UNRESOLVED_CLAIM_REF"
ODBIJEN_MALO_TVRDNJI = "TOO_FEW_CLAIMS"


def _tekst(v: Any) -> Optional[str]:
    return v.strip() if isinstance(v, str) and v.strip() else None


def materializuj(
    kontradikcije: Any, katalog: dict[str, str], predmet_id: str,
    poznati_dokazi: Optional[dict[str, dict]] = None,
) -> dict:
    """Vraća `{"kandidati": [...], "odbijeni": [...]}`.

    `kandidati` su tačno onog oblika koji `persist_paket` očekuje
    (`claim_refs` = razrešeni `predmet_dokazi.id`, `relation_type`,
    `issue_label`), plus provenijencija koja se prenosi netaknuta.

    Prazna lista kontradikcija je VALIDNA (A014 §12 CASE I) — nula kandidata,
    nula odbijenih, bez greške."""
    if kontradikcije is None:
        kontradikcije = []
    if not isinstance(kontradikcije, list):
        return {"kandidati": [], "odbijeni": [
            {"indeks": 0, "razlog": ODBIJEN_OBLIK,
             "detalj": f"kontradikcije nije lista nego {type(kontradikcije).__name__}"}]}

    kandidati: list[dict] = []
    odbijeni: list[dict] = []

    for i, k in enumerate(kontradikcije):
        if not isinstance(k, dict):
            odbijeni.append({"indeks": i, "razlog": ODBIJEN_OBLIK,
                             "detalj": f"stavka nije objekat nego {type(k).__name__}"})
            continue

        # `isinstance` PRE provere članstva — neheširana vrednost (dict/list) bi na
        # `in RELACIJE` podigla TypeError umesto da padne zatvoreno. Isti obrazac
        # koji `issue_v2.validiraj_predlog_teme` već primenjuje.
        rel = k.get("relation_type")
        if not isinstance(rel, str) or rel not in RELACIJE:
            odbijeni.append({"indeks": i, "razlog": ODBIJEN_RELACIJA,
                             "detalj": f"relation_type={rel!r}",
                             "opis": _tekst(k.get("opis"))})
            continue

        try:
            razresene = razresi_reference(k.get("claim_refs"), katalog,
                                          predmet_id, poznati_dokazi)
        except GreskaKataloga as exc:
            # Nema pokusaja oporavka iz `lokacija_1/2` ni iz `opis`. To bi bio
            # tacno onaj document-pair model koji A005-A013 uklanjaju.
            odbijeni.append({"indeks": i, "razlog": ODBIJEN_REFERENCA,
                             "detalj": str(exc), "opis": _tekst(k.get("opis"))})
            continue

        if len(set(razresene)) < MIN_TVRDNJI:
            odbijeni.append({"indeks": i, "razlog": ODBIJEN_MALO_TVRDNJI,
                             "detalj": f"{len(set(razresene))} razlicitih tvrdnji",
                             "opis": _tekst(k.get("opis"))})
            continue

        kandidati.append({
            # --- ono sto domen i adapter zaista koriste ---
            "claim_refs": razresene,
            "relation_type": rel,
            "issue_label": _tekst(k.get("issue_label")) or _tekst(k.get("opis")),
            # --- provenijencija i prikaz: prenosi se, NIKAD ne odlucuje ---
            "_opis": _tekst(k.get("opis")),
            "_tezina": _tekst(k.get("tezina")),
            "_lokacije": [x for x in (_tekst(k.get("lokacija_1")),
                                      _tekst(k.get("lokacija_2"))) if x],
            "_izvorni_indeks": i,
        })

    if odbijeni:
        logger.info("[A014] predmet=%s materijalizacija: %d kandidata, %d odbijeno (%s)",
                    predmet_id, len(kandidati), len(odbijeni),
                    ", ".join(sorted({o["razlog"] for o in odbijeni})))
    return {"kandidati": kandidati, "odbijeni": odbijeni}
