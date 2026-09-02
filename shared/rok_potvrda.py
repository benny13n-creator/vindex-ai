# -*- coding: utf-8 -*-
"""
Vindex AI — shared/rok_potvrda.py

FAZA 6.2 — LJUDSKA POTVRDA ROKA, BEZ NOVE TABELE I BEZ MIGRACIJE.

## Zašto ovde, a ne nova tabela

`predmet_hronologija` nema nijedno polje stanja (izmereno na živoj šemi:
`akter, created_at, datum, datum_iso, dogadjaj, dokument_id, dokument_naziv,
id, predmet_id, user_id, vaznost`). Dodavanje kolone traži migraciju koju
pokreće vlasnik — do tada bi gejt bio mrtav kod, a INV-2 bi ostao otvoren.

`audit_immutable` VEĆ POSTOJI, živ je (20.817 redova), INSERT-only je,
hash-lančan (`seq`/`prev_hash`/`entry_hash`) i već nosi ljudske odluke istog
oblika — `dokument_review_resolved` i `entity_corrected`. Odluka o roku je
tačno ta vrsta zapisa, pa se koristi postojeći kanon umesto paralelnog.

## Šta ovo NIJE

Nije identitet roka. Nije rezolucija identiteta. Nije spajanje opažanja.
`resource_id` je `predmet_hronologija.id` — identitet REDA, ne činjenice.
FAZA 6.1 je dokazala da identitet činjenice danas nije rešiv; ovaj modul to
NE pokušava i ne sme se tako čitati.

## Semantika

Poslednja odluka pobeđuje, po `seq` (monotono raste, INSERT-only lanac).
Odbijanje posle potvrde gasi izvršivost. Ponovljena potvrda ne menja ishod —
idempotencija dolazi iz „poslednja pobeđuje", ne iz sprečavanja upisa: audit
lanac po svojoj prirodi beleži SVAKI pokušaj, i to je poželjno.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable, Optional

logger = logging.getLogger("vindex.rok_potvrda")

#: Akcije u `audit_immutable.action`. Moraju biti i u `AUDITABLE_ACTIONS`
#: (`shared/audit_immutable.py`) — inače `log_action` tiho ne upiše ništa.
AKCIJA_POTVRDA = "rok_potvrdjen"
AKCIJA_ODBIJANJE = "rok_odbijen"

#: `audit_immutable.resource_type` za rok iz hronologije.
RESURS = "rok"


async def potvrdi_rok(rok_id: str, user_id: str, *, napomena: Optional[str] = None) -> bool:
    """Advokat preuzima odgovornost za AI opažen rok. Tek posle ovoga rok sme
    da pokrene podsetnik/notifikaciju."""
    return await _zapisi(AKCIJA_POTVRDA, rok_id, user_id, napomena)


async def odbij_rok(rok_id: str, user_id: str, *, napomena: Optional[str] = None) -> bool:
    """Advokat odbacuje AI opažen rok. Odbijen rok NIKAD ne postaje izvršiv."""
    return await _zapisi(AKCIJA_ODBIJANJE, rok_id, user_id, napomena)


async def _zapisi(akcija: str, rok_id: str, user_id: str, napomena: Optional[str]) -> bool:
    from shared.audit_immutable import log_action
    zapis = await log_action(
        akcija, user_id=user_id, resource_type=RESURS, resource_id=str(rok_id),
        metadata={"napomena": napomena} if napomena else None,
    )
    if zapis is None:
        # `log_action` vraća None i kada akcija nije u `AUDITABLE_ACTIONS`.
        # Tiho „uspelo" bi značilo da rok izgleda potvrđen a nije — najgori
        # mogući ishod za bezbednosni gejt, pa se prijavljuje neuspeh.
        logger.warning("[ROK_POTVRDA] %s nije upisan za rok=%s", akcija, rok_id)
        return False
    return True


def potvrdjeni_ids(rok_ids: Iterable[str]) -> set:
    """Skup `predmet_hronologija.id` koji SMEJU da pokrenu obavezu.

    FAIL-CLOSED na svakom nivou: pad upita, prazan odgovor ili nedostupna
    tabela daju PRAZAN skup — dakle nijedan AI rok ne prolazi. Nikad se ne
    vraća „sve dozvoljeno" kao rezervni ishod."""
    ids = [str(x) for x in (rok_ids or []) if x]
    if not ids:
        return set()
    try:
        from shared.deps import _get_supa
        r = (_get_supa().table("audit_immutable")
             .select("action, resource_id, seq")
             .eq("resource_type", RESURS)
             .in_("resource_id", ids)
             .in_("action", [AKCIJA_POTVRDA, AKCIJA_ODBIJANJE])
             .order("seq")
             .execute())
    except Exception as exc:
        logger.warning("[ROK_POTVRDA] citanje odluka palo — nijedan AI rok nije izvrsiv: %s", exc)
        return set()

    poslednja: dict = {}
    for red in (r.data or []):
        poslednja[str(red.get("resource_id"))] = red.get("action")
    return {rid for rid, akcija in poslednja.items() if akcija == AKCIJA_POTVRDA}


async def potvrdjeni_ids_async(rok_ids: Iterable[str]) -> set:
    return await asyncio.to_thread(potvrdjeni_ids, rok_ids)
