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

## Semantika (NS2B-C, odluka osnivača 2026-10-14)

Odbijanje je ZAVRŠNO za običnu odluku. Stanje se izvodi iz SKUPA odluka, ne
iz njihovog redosleda:

  * ijedno odbijanje            -> REJECTED (bez obzira na kasnije potvrde)
  * bar jedna potvrda, nijedno odbijanje -> CONFIRMED
  * nijedna odluka              -> UNCONFIRMED (odsustvo iz recnika)
  * lanac nije procitan         -> UNKNOWN kod pozivaoca (nikad CONFIRMED)

Zasto skup, a ne „poslednja pobeđuje": upis u lanac je „procitaj pa upisi"
bez uslovnog upisa u bazi (nema RPC-a ni zakljucavanja po roku), pa provera
pre upisa NIJE dokaz pod konkurencijom — zastareo prozor ili trka dva
zahteva moze upisati potvrdu posle odbijanja. Izvodjenje koje ne zavisi od
redosleda cini taj upis bezopasnim: skup odluka samo raste, a REJECTED je
apsorbujuce stanje, pa nijedan redosled, ponavljanje ni trka ne mogu odbijen
rok uciniti potvrdjenim. Potvrda -> odbijanje i dalje radi. Ponovljena
potvrda ili odbijanje ne menja ishod; od NS2B-C F1 ruta je i NE upisuje (lanac ne raste
bez promene stanja), osim ponovne potvrde posle uklanjanja izvora (N03-FD6 ponovni pregled).

Namerno ponovno otvaranje odbijenog roka NE POSTOJI kao obicna odluka. Ako
zatreba, to je zasebna, posebno revizibilna operacija (buduci rad).
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
#: N03-FD8 — lanac odluka NIJE PROCITAN. Ovo nije cetvrto stanje odluke nego
#: odsustvo znanja o njoj: ne sme se prikazati kao UNCONFIRMED (to bi odbijen rok
#: vratilo u predlog, a potvrdjen spustilo u predlog) niti kao „nema odluke".
#: Kanonska politika ga tretira kao svako stanje koje nije CONFIRMED: interno
#: vidljivo, spolja i za akciju ZABRANJENO.
STANJE_NEPOZNATO = "UNKNOWN"

#: PostgREST/Supabase `max-rows` (podrazumevano 1000) TIHO sece odgovor bez opsega.
#: Strana nikad nije veca od te granice (isti obrazac kao `routers/data_export._fetch`).
_STRANA = 1000
#: Broj `resource_id` vrednosti po upitu: `in.(...)` ide u URL, a cron (SMS/email/ICS)
#: salje rokove SVIH korisnika odjednom. ~40 znakova po uuid-u → ~4 KB po upitu.
_IDS_PO_UPITU = 100
#: Gornja granica strana po grupi id-jeva (i uz `max-rows`=1 to je 10.000 odluka po grupi;
#: uz 1000 po strani, 10 miliona). Prekoracenje je greska, ne „dovoljno" — petlja bez
#: kraja nad neispravnim odgovorom nije citanje.
_MAX_STRANA = 10_000


def procitaj_lanac(rok_ids: Iterable[str], kolone: str) -> list:
    """SVE odluke o datim rokovima, rastuce po `seq` — ili izuzetak. Nikad deo.

    NS2B-C F1: jedan upit bez opsega PostgREST sece na `max-rows` (1000) bez greske, a
    redovi su rastuci po `seq` — dakle padaju upravo NAJNOVIJE odluke. Kasnije odbijanje
    je tako nestajalo, pa je odbijen rok citan kao CONFIRMED (ICS, SMS cron, portal...).

    Zato: stranicenje po kljucu (`seq > poslednji`, `order(seq)`, `limit(_STRANA)`), kraj
    TEK na PRAZNOJ strani (ne na kratkoj — i `max-rows` nizi od `_STRANA` je bezbedan),
    `seq` strogo raste unutar i preko strana (inace duplikati/rupe → izuzetak), petlja je
    ogranicena. Id-jevi se salju u grupama (`_IDS_PO_UPITU`). Pad bilo koje strane dize
    izuzetak; pozivalac bira: strogo → UNKNOWN/503, inace prazno (nista potvrdjeno).
    `rok_izvor` cita lanac ovom istom funkcijom — jedan citac, jedno pravilo.
    """
    ids = list(dict.fromkeys(str(x) for x in (rok_ids or []) if x))
    from shared.deps import _get_supa
    supa = _get_supa()
    out: list = []
    for i in range(0, len(ids), _IDS_PO_UPITU):
        grupa = ids[i:i + _IDS_PO_UPITU]
        poslednji = None
        for _ in range(_MAX_STRANA):
            q = (supa.table("audit_immutable")
                 .select(kolone)
                 .eq("resource_type", RESURS)
                 .in_("resource_id", grupa)
                 .in_("action", [AKCIJA_POTVRDA, AKCIJA_ODBIJANJE]))
            if poslednji is not None:
                q = q.gt("seq", poslednji)
            strana = q.order("seq").limit(_STRANA).execute().data or []
            if not strana:
                break
            for red in strana:
                seq = red.get("seq")
                if isinstance(seq, bool) or not isinstance(seq, int):
                    raise RuntimeError("lanac odluka: seq nije ceo broj")
                if poslednji is not None and seq <= poslednji:
                    raise RuntimeError("lanac odluka: stranicenje nije strogo rastuce po seq")
                poslednji = seq
            out.extend(strana)
        else:
            raise RuntimeError("lanac odluka: prekoracen broj strana")
    out.sort(key=lambda r: r["seq"])
    return out


def odluke(rok_ids: Iterable[str], strogo: bool = False) -> dict:
    """Stanje odluke po roku: `{rok_id: CONFIRMED|REJECTED}`.

    Rok koji se ne pojavi u rezultatu je NEPOTVRDJEN. FAIL-CLOSED na svakom
    nivou: pad upita, prazan odgovor ili nedostupna tabela daju PRAZAN recnik —
    dakle sve je nepotvrdjeno. Nikad se ne vraca „sve odobreno".

    NS2B-C: izvodjenje NE zavisi od redosleda. Ijedno odbijanje daje REJECTED
    (zavrsno — potvrda posle odbijanja, iz zastarelog prozora ili trke, ga ne
    vraca); CONFIRMED samo ako postoji potvrda i nijedno odbijanje.
    """
    ids = [str(x) for x in (rok_ids or []) if x]
    if not ids:
        return {}
    try:
        redovi = procitaj_lanac(ids, "action, resource_id, seq")
    except Exception as exc:
        # VCR001 T03: `strogo=True` (Case Actions) — iz ODSUSTVA odluke pozivalac izvodi obavezu, pa
        # neprocitan lanac ne sme da izgleda kao „nema odluka“. Podrazumevano ponasanje je nepromenjeno.
        if strogo:
            raise
        logger.warning("[ROK_POTVRDA] citanje odluka palo — sve ostaje nepotvrdjeno: %s", exc)
        return {}

    stanje: dict = {}
    for red in redovi:
        rid, akcija = str(red.get("resource_id")), red.get("action")
        if akcija != AKCIJA_POTVRDA:
            # Odbijanje (i, fail-closed, svaka nepoznata akcija) je apsorbujuce.
            stanje[rid] = STANJE_ODBIJEN
        elif stanje.get(rid) != STANJE_ODBIJEN:
            stanje[rid] = STANJE_POTVRDJEN
    return stanje


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
