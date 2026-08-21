# -*- coding: utf-8 -*-
"""Kanonska autorizacija za RAG nad predmetima.

BETA-DATA-CONFIDENTIALITY-003 / F-01.

ŠTA JE BILO

`app/services/retrieve.py` pretražuje `kancelarija_{id}` namespace sa filterom
samo po `type` — dakle SVE trajne dokumente cele kancelarije, za svakog aktivnog
člana. A kanonska kapija za čitanje predmeta (`api.py::get_predmet`) propušta
po tačno dva osnova:

    1. `predmeti.user_id == pozivalac`            (vlasnik)
    2. aktivan red u `predmet_delegiranja`         (izričito delegiran uvid)

Članstvo u istoj kancelariji NIJE osnov za pristup predmetu. Član koji nije
vlasnik i nije delegiran ne može da otvori predmet kroz API — ali mu je RAG
mogao vratiti doslovan tekst iz njegovih dokumenata.

ZAŠTO SE OVO DESILO

Nije zaboravljeno nego nedovršeno. `shared/kancelarija_utils.py:44` u docstringu
sam kaže da `predmet_id` stoji u metapodacima vektora „za scoping unutar tog
namespace-a" — mehanizam je ugrađen po dizajnu, a filter koji bi ga koristio
nikad nije napisan.

ŠTA OVO NAMERNO NE MENJA

Pretraga preko više predmeta je stvarna funkcija proizvoda („Institutional
Learning", 2026-07-26) i ostaje. Menja se samo SKUP predmeta: umesto svih u
kancelariji, oni koje pozivalac stvarno sme da vidi. Za solo advokata je to i
dalje ceo njegov korpus, pa se za njega ne menja ništa.

ZAŠTO SE `predmet_saradnici` NE RAČUNA

Tabela postoji (`migrations/011_saradnja.sql`) i popunjava se, ali je
`get_predmet` nikad ne konsultuje. Uključiti je ovde značilo bi DATI pristup
koji kanonska kapija ne daje — a mandat izričito zabranjuje izvođenje dozvole
iz bilo čega osim stvarnog ugovora. Ako proizvod želi da saradnici vide
predmet, to je odluka koja se donosi u `get_predmet`, pa se odrazi ovde.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("vindex.rag_acl")

# Sentinel: „autorizacija nije izračunata". Razlikuje se od prazne liste, koja
# znači „izračunata je i korisnik nema nijedan predmet".
NEPOZNATO: Optional[list] = None


def dozvoljeni_predmeti(supa, user_id: str) -> list:
    """Predmeti koje `user_id` sme da vidi — ogledalo `api.py::get_predmet`.

    Vraća listu ID-eva. Prazna lista je validan odgovor (korisnik bez predmeta)
    i MORA se razlikovati od `None`, koje znači da provera nije uspela.

    Diže izuzetak ako baza ne odgovori: pozivalac tada NE SME da pretražuje
    namespace vlasnika. Tiho vraćanje prazne liste bi izgledalo isto kao
    „nema predmeta" i pretvorilo ispad baze u pogrešno prazan odgovor umesto u
    vidljivu grešku; tiho vraćanje `None` bi u pozivaocu moglo da se pročita
    kao „bez ograničenja". Zato izuzetak.
    """
    if not user_id:
        return []

    # BETA-DEL-001: predmet u stanju brisanja NE SME biti izvor za RAG.
    #
    # Ovo je JEDINO usko grlo kroz koje vlasnikov namespace ulazi u pretragu,
    # pa je jedan filter ovde dovoljan da tombstonovan predmet nestane iz
    # konteksta — uključujući `cinjenice_iz_dokumenta` (B4-M2), koje se time
    # prirodno prazni. Nijedna linija B4-M2 logike se NE dira.
    #
    # Zašto `try` a ne samo filter: kolona stiže migracijom 114. Ako migracija
    # jos nije primenjena, upit sa filterom pada i korisnik bi ostao BEZ
    # retrieval-a. Pad na neutralnu granu je ovde bezbedan jer se tombstone bez
    # te kolone ne moze ni upisati (`obrisi_predmet` tada vraca
    # PERMANENT_FAILURE i ne dira nista), pa nijedan predmet ne moze biti
    # DELETING.
    try:
        svoji = (supa.table("predmeti").select("id")
                 .eq("user_id", user_id).is_("brisanje_zapoceto", "null").execute())
    except Exception as e:
        logger.warning("[RAG_ACL] filter `brisanje_zapoceto` nije primenjen "
                       "(migracija 114?): %s", e)
        svoji = (supa.table("predmeti").select("id")
                 .eq("user_id", user_id).execute())
    ids = [r["id"] for r in (svoji.data or []) if r.get("id")]

    # Delegirani uvid — isti uslov koji `get_predmet` koristi na svojoj
    # rezervnoj grani (`api.py:4178`): status mora biti 'aktivno'.
    try:
        deleg = (supa.table("predmet_delegiranja").select("predmet_id")
                 .eq("na_user_id", user_id).eq("status", "aktivno").execute())
        ids += [r["predmet_id"] for r in (deleg.data or []) if r.get("predmet_id")]
    except Exception as e:
        # Delegiranje je dodatak, ne osnov. Ako ta tabela zakaže, korisnik
        # dobija uži skup — nikad širi. Fail-closed u pravom smeru.
        logger.warning("[RAG_ACL] predmet_delegiranja nedostupno, nastavljam bez njih: %s", e)

    return sorted(set(ids))


# Gornja granica za `$in` listu u Pinecone filteru. Metadata filter nije
# namenjen listama proizvoljne dužine, a `_pretraga_ns` (`retrieve.py:966`)
# guta izuzetke — pa bi odbijen filter izgledao kao „nema rezultata", tiho.
# Iznad granice se sužava na trenutni predmet: uže, nikad šire.
_MAX_IN = 400


def filter_za_namespace_vlasnika(
    dozvoljeni: Optional[list],
    tipovi: list,
    current_predmet_id: Optional[str] = None,
) -> Optional[dict]:
    """Pinecone filter za namespace vlasnika, ili `None` ako pretragu ne smemo.

    `None` na izlazu je naredba pozivaocu da namespace NE pretražuje. To je
    namerno jače od praznog filtera: `retrieve.py:963` radi `if filter:`, pa
    `{}` tiho UKLANJA filter i pretražuje ceo namespace — tačno mehanizam kojim
    bi se F-01 ponovo otvorio.
    """
    if dozvoljeni is None:
        logger.error(
            "[RAG_ACL] namespace vlasnika je tražen bez izračunate autorizacije — "
            "pretraga se odbija (fail-closed)"
        )
        return None
    if not dozvoljeni:
        # Korisnik nema nijedan predmet: nema šta da se nađe, a `$in: []` je u
        # Pinecone-u nedefinisan — pa se pretraga preskače.
        return None

    if len(dozvoljeni) > _MAX_IN:
        # Advokat sa velikim portfoliom je realan slučaj. Sužavamo na trenutni
        # predmet ako ga imamo — korisnik tada gubi pretragu preko ranijih
        # predmeta, ali ne dobija ništa što ne sme da vidi.
        if current_predmet_id and current_predmet_id in dozvoljeni:
            logger.warning(
                "[RAG_ACL] %d autorizovanih predmeta prelazi granicu %d — "
                "sužavam na trenutni predmet",
                len(dozvoljeni), _MAX_IN,
            )
            dozvoljeni = [current_predmet_id]
        else:
            logger.warning(
                "[RAG_ACL] %d autorizovanih predmeta prelazi granicu %d i nema "
                "trenutnog predmeta — preskačem namespace vlasnika",
                len(dozvoljeni), _MAX_IN,
            )
            return None

    return {"type": {"$in": tipovi}, "predmet_id": {"$in": dozvoljeni}}
