# -*- coding: utf-8 -*-
"""
Vindex AI — services/v2_observation.py

A017 (2026-08-31) — KANONSKI I JEDINI PUT OD GENOME OPAŽANJA DO V2 PERSISTENCE-a.

## Zašto postoji

Genome opažanje se u produkciji proizvodi na DVA mesta, i to je zatečeno stanje
koje A017 nije uveo (mapirano u §1, dokazano po `_extract_genome` call-site-ovima):

    routers/case_dna.py::_do_genome_refresh      pozadinski put (event bus)
    routers/case_dna.py::_refresh_case_dna_body  ručni refresh (HTTP)

Oba čitaju iste dokumente, zovu isti `_extract_genome`, upisuju isti
`predmeti.case_dna` i emituju isti događaj. Kad bi V2 bio uvezan u samo jedan od
njih, drugi bi proizvodio Genome rezultat BEZ V2 slike — pa bi `case_dna` i V2
tvrdili različite stvari o istom predmetu.

Zato ovaj modul: **jedan kanonski ulaz, dva pozivaoca.** Nije spajanje dva pisca
nagađanjem — dva proizvođača opažanja ostaju netaknuta; samo im je oduzeta
mogućnost da svaki na svoj način razgovara sa V2 slojem.

## Šta ovaj modul NIKAD ne radi

  - ne odlučuje identitet (to je `shared/issue_v2.py`);
  - ne zove `v2_persist_contradiction` niti bilo koji pojedinačni RPC —
    isključivo paketni `persist_observation_package`;
  - ne guta izuzetke: pozivalac mora saznati da opažanje NIJE upisano;
  - ne piše `predmeti.case_dna` niti emituje događaje — to ostaje na pozivaocu,
    i to TEK POSLE uspešnog povratka odavde.

## Redosled koji ovaj modul čini obaveznim (A017 §2)

    Genome opažanje
      -> materijalizacija kandidata (claim_refs, ne par dokumenata)
      -> KOMPLETAN paket
      -> persist_observation_package  (jedna transakcija, A016 dokazano)
      -> COMMIT
      -> tek tada pozivalac sme upisati case_dna i emitovati posledice

Ako ovaj poziv podigne izuzetak, pozivalac NE SME nastaviti. Zato se ovde ništa
ne hvata — `V2PackageRejected`, `V2StaleObservation` i `V2PersistenceError`
putuju do pozivaoca neizmenjeni, sa svojom semantikom iz A016.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from services.v2_contradiction_persistence import persist_observation_package
from shared.claim_catalog import napravi_katalog
from shared.contradiction_materializer import materializuj

logger = logging.getLogger("vindex.v2_observation")


def _poznati_dokazi(dokazi: Any) -> dict[str, dict]:
    """`predmet_dokazi.id -> red`, iz ISTE liste koju je video prompt.

    `shared/claim_catalog.py` izričito traži da se katalog gradi nad istom
    listom nad kojom je model birao reference. Zato se ovde ništa ne dohvata
    iznova — lista stiže od pozivaoca, onakva kakva je otišla u prompt."""
    return {d["id"]: d for d in (dokazi or []) if isinstance(d, dict) and d.get("id")}


async def upisi_v2_opazanje(
    *, predmet_id: str, user_id: str, genome: dict, dokazi: Any,
    event_id: Optional[str] = None,
) -> dict:
    """Materijalizuje Genome kontradikcije i upisuje CEO paket atomarno.

    Vraća `{"kandidata", "odbijeno", "kompletno", "observation_version",
    "ishodi", "odbijeni"}`.

    Podiže izuzetak ako paket nije upisan. Pozivalac tada NE SME upisati
    `case_dna` ni emitovati posledice.
    """
    if not predmet_id or not user_id:
        raise ValueError("upisi_v2_opazanje: predmet_id i user_id su obavezni")

    poznati = _poznati_dokazi(dokazi)
    katalog = napravi_katalog(dokazi or [], predmet_id)
    mat = materializuj(genome.get("kontradikcije"), katalog, predmet_id, poznati)
    kandidati, odbijeni = mat["kandidati"], mat["odbijeni"]

    # Odbijen kandidat znači: Genome JESTE video kontradikciju, a mi je nismo
    # mogli izraziti. Tvrditi kompletnost tada bi značilo zatvoriti spornu tačku
    # na koju se odbijeni odnosio — tihi gubitak, ne čišćenje.
    kompletno = not odbijeni

    tezine = {i: k["_tezina"] for i, k in enumerate(kandidati) if k.get("_tezina")}

    rez = await persist_observation_package(
        predmet_id=predmet_id, user_id=user_id, event_id=event_id,
        predlozi=kandidati, tezina_po_indeksu=tezine,
        kompletno_opazanje=kompletno,
    )

    if odbijeni:
        logger.info(
            "[A017] predmet=%s V2 opažanje NIJE kompletno — %d kandidata upisano, "
            "%d odbijeno (%s); neopažene kontradikcije se NE zatvaraju",
            predmet_id, len(kandidati), len(odbijeni),
            ", ".join(sorted({o["razlog"] for o in odbijeni})))

    return {
        "kandidata": len(kandidati),
        "odbijeno": len(odbijeni),
        "kompletno": rez["observation_complete"],
        "observation_version": rez["observation_version"],
        "ishodi": rez["ishodi"],
        "odbijeni": odbijeni,
    }
