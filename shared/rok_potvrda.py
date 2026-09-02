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


#: Tri stanja odluke. Odsustvo zapisa je NEPOTVRDJEN — to NIJE isto sto i
#: ODBIJEN: „niko se jos nije izjasnio" i „covek je rekao ne" moraju ostati
#: razlicite cinjenice (odbijen rok se i dalje vidi u istoriji, nepotvrdjen ceka).
STANJE_NEPOTVRDJEN = "UNCONFIRMED"
STANJE_POTVRDJEN = "CONFIRMED"
STANJE_ODBIJEN = "REJECTED"


def odluke(rok_ids: Iterable[str]) -> dict:
    """Poslednja odluka po roku: `{rok_id: CONFIRMED|REJECTED}`.

    Rok koji se ne pojavi u rezultatu je NEPOTVRDJEN. FAIL-CLOSED na svakom
    nivou: pad upita, prazan odgovor ili nedostupna tabela daju PRAZAN recnik —
    dakle sve je nepotvrdjeno. Nikad se ne vraca „sve odobreno".

    Redosled je po `seq` (INSERT-only hash-lanac), pa poslednja odluka pobedjuje:
    odbijanje posle potvrde gasi izvrsivost, potvrda posle odbijanja je vraca.
    """
    ids = [str(x) for x in (rok_ids or []) if x]
    if not ids:
        return {}
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
        logger.warning("[ROK_POTVRDA] citanje odluka palo — sve ostaje nepotvrdjeno: %s", exc)
        return {}

    poslednja: dict = {}
    for red in (r.data or []):
        akcija = red.get("action")
        poslednja[str(red.get("resource_id"))] = (
            STANJE_POTVRDJEN if akcija == AKCIJA_POTVRDA else STANJE_ODBIJEN)
    return poslednja


def stanje_roka(rok_id: str, odluke_mapa: Optional[dict] = None) -> str:
    """Stanje jednog roka. Bez zapisa -> `UNCONFIRMED`."""
    return (odluke_mapa or {}).get(str(rok_id), STANJE_NEPOTVRDJEN)


def potvrdjeni_ids(rok_ids: Iterable[str]) -> set:
    """Skup `predmet_hronologija.id` koji SMEJU da pokrenu obavezu.

    FAIL-CLOSED na svakom nivou: pad upita, prazan odgovor ili nedostupna
    tabela daju PRAZAN skup — dakle nijedan AI rok ne prolazi. Nikad se ne
    vraća „sve dozvoljeno" kao rezervni ishod."""
    return {rid for rid, stanje in odluke(rok_ids).items()
            if stanje == STANJE_POTVRDJEN}


async def potvrdjeni_ids_async(rok_ids: Iterable[str]) -> set:
    return await asyncio.to_thread(potvrdjeni_ids, rok_ids)
