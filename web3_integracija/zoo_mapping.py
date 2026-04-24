# -*- coding: utf-8 -*-
"""
ZOO mapiranje blockchain kršenja na pravne odredbe Srbije.
Čisti podaci — nula zavisnosti prema ostatku sistema.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ZOOClan:
    broj:    str
    naziv:   str
    opis:    str
    # Primenjuje se na tip podneska koji generiše Legal Engine
    tip_podneska: str = "tuzba_naknada_stete"


# ─── Katalog pravnih odredbi ──────────────────────────────────────────────────

ZOO_KATALOG: dict[str, ZOOClan] = {
    "nepotpuna_uplata": ZOOClan(
        broj         = "262",
        naziv        = "Pravo na ispunjenje obaveze",
        opis         = (
            "Poverilac čije potraživanje nije ispunjeno ima pravo zahtevati "
            "ispunjenje obaveze ili, ako to više nije moguće, naknadu štete. "
            "Primenjuje se kada vrednost blockchain transakcije nije u celosti "
            "namirena prema ugovorenim uslovima pametnog ugovora."
        ),
        tip_podneska = "tuzba_naknada_stete",
    ),
    "nedostatak_dobra": ZOOClan(
        broj         = "154",
        naziv        = "Odgovornost za štetu",
        opis         = (
            "Ko drugome prouzrokuje štetu dužan je naknaditi je, ako ne dokaže "
            "da je šteta nastala bez njegove krivice. Digitalno dobro isporučeno "
            "sa nedostatkom (defektni NFT, greška u kodu pametnog ugovora, "
            "neispravna tokenizovana imovina) potpada pod ovu odredbu."
        ),
        tip_podneska = "tuzba_naknada_stete",
    ),
    "istekao_rok": ZOOClan(
        broj         = "124",
        naziv        = "Raskid ugovora zbog neispunjenja",
        opis         = (
            "Ako dužnik ne ispuni obavezu u ostavljenom naknadnom roku, ugovor "
            "se raskida po sili zakona. Kada blockchain vremenski pečat (timestamp) "
            "evidentira prekoračenje roka isporuke digitalnog dobra ili usluge, "
            "nastupaju pretpostavke za primenu ovog člana."
        ),
        tip_podneska = "predlog_izvrsenje",
    ),
}


# ─── Logika detekcije kršenja ─────────────────────────────────────────────────

@dataclass
class DetekcijaKrsenja:
    kljuc:    str           # ključ u ZOO_KATALOG
    clan:     ZOOClan
    vrednost: str | None    # vrednost polja koje je okidač


def detektuj_krsenje(dogadjaj: dict) -> list[DetekcijaKrsenja]:
    """
    Analizira normalizovani blockchain događaj i vraća listu kršenja.
    Jedan događaj može pokriti više članova ZOO.
    """
    krsenja: list[DetekcijaKrsenja] = []

    status_uplate  = str(dogadjaj.get("status_uplate",  "")).strip().lower()
    status_dobra   = str(dogadjaj.get("status_dobra",   "")).strip().lower()
    rok_isporuke   = str(dogadjaj.get("rok_isporuke",   "")).strip().lower()

    if status_uplate in ("nepotpun", "partial", "incomplete", "neplacen"):
        krsenja.append(DetekcijaKrsenja(
            kljuc    = "nepotpuna_uplata",
            clan     = ZOO_KATALOG["nepotpuna_uplata"],
            vrednost = dogadjaj.get("status_uplate"),
        ))

    if status_dobra in ("sa nedostatkom", "nedostatak", "defective", "faulty", "invalid"):
        krsenja.append(DetekcijaKrsenja(
            kljuc    = "nedostatak_dobra",
            clan     = ZOO_KATALOG["nedostatak_dobra"],
            vrednost = dogadjaj.get("status_dobra"),
        ))

    if rok_isporuke in ("istekao", "expired", "overdue", "kasni", "prekoracen"):
        krsenja.append(DetekcijaKrsenja(
            kljuc    = "istekao_rok",
            clan     = ZOO_KATALOG["istekao_rok"],
            vrednost = dogadjaj.get("rok_isporuke"),
        ))

    return krsenja
