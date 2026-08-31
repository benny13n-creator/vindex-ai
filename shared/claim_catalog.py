# -*- coding: utf-8 -*-
"""
Vindex AI — shared/claim_catalog.py

A014 (2026-08-30) — DETERMINISTIČKI KATALOG REFERENCI NA TVRDNJE.

## Problem koji ovo zatvara

Genome producer je i pre A014 dobijao već klasifikovane tvrdnje iz
`predmet_dokazi` (`routers/case_dna.py::_fetch_dokazi_kontekst`), ali kao
ANONIMNE redove:

    - Radni odnos je prestao 15.03.2025. [otkaz]
    - Neisplaćena zarada iznosi 480.000,00 RSD [dug]

Model ih je video, ali nije imao **čime** da ih imenuje. Zato kontradikcija nije
mogla da nosi `claim_refs`, pa V2 `CONTRADICTION` — koji traži ≥2
`predmet_dokazi.id` — nikada nije mogao da nastane iz stvarnog producera
(izmereno u A013: 11 predmeta sa kontradikcijama, 0 sa vezanim tvrdnjama).

## Rešenje — i granica koju NE prelazi

Pre LLM poziva sistem gradi katalog:

    CLAIM-001 -> predmet_dokazi.id  a1b2…
    CLAIM-002 -> predmet_dokazi.id  c3d4…

Model bira **isključivo iz ponuđenog skupa** i vraća `["CLAIM-001","CLAIM-003"]`.
Sistem to deterministički prevodi u UUID-jeve.

Model NIKADA ne piše UUID. Identitet ne nastaje iz proze.

## Fail-closed, bez izuzetka

Nepoznat token (`CLAIM-999`, prazan string, broj, `null`) se **ne pogađa**.
Nema fuzzy poređenja, nema „najbliže tvrdnje", nema mapiranja po dokumentu ni po
lokaciji. Nepoznata referenca ruši ceo predlog.

## Zašto sortiranje po `id`

Redosled redova iz PostgREST-a nije garantovan. Katalog se zato gradi nad
**sortiranim `predmet_dokazi.id`**, pa isti ulazni skup uvek daje isti katalog,
bez obzira kojim je redom baza vratila redove.

## Oznaka NIJE identitet — i nije stabilna između poziva

`CLAIM-001` je **efemerna adresa unutar jednog poziva**, ne trajno ime. Kada se
skup tvrdnji promeni (nova tvrdnja čiji `id` sortira ispred postojećih), oznake
se pomeraju. To je bezbedno **samo** zato što se razrešavanje radi katalogom koji
je model i video.

    ⚠ UGOVOR ZA POZIVAOCA: materijalizuj referencama iz ISTE liste `dokazi` koja
    je prosleđena `_extract_genome`. Ako se lista ponovo učita iz baze između
    ekstrakcije i materijalizacije, a u međuvremenu je dodata tvrdnja, oznake se
    mogu pomeriti i `CLAIM-001` bi pokazao na drugu tvrdnju.

Trajni identitet je i ostaje `predmet_dokazi.id`. Oznaka nikada ne ulazi u
persistence.

## Jedno pravo pravilo o vidljivosti

Tvrdnja bez teksta se ne prikazuje modelu, pa **ne sme ni da postoji u katalogu**
— inače bi katalog nudio oznaku za nešto što model nikada nije video. Isto važi
za gornju granicu broja tvrdnji: ono što je odsečeno nije ponuđeno.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

# Gornja granica broja tvrdnji koje ulaze u prompt. Postojala je i pre A014, kao
# `.limit(20)` u `_fetch_dokazi_kontekst`; ovde je izdvojena da bi granica imala
# JEDNOG vlasnika — katalog i prompt ne smeju da se razilaze.
MAKS_TVRDNJI = 20

PREFIKS = "CLAIM-"


class GreskaKataloga(ValueError):
    """Referenca se ne može razrešiti. Nikad se ne pretvara u pogađanje."""


def _upotrebljiva(d: Any) -> bool:
    return (
        isinstance(d, dict)
        and isinstance(d.get("id"), str)
        and d["id"].strip()
        and isinstance(d.get("tvrdnja"), str)
        and d["tvrdnja"].strip()
        and d.get("deleted_at") is None
    )


def napravi_katalog(dokazi: Iterable[dict], predmet_id: str) -> dict[str, str]:
    """`{"CLAIM-001": predmet_dokazi.id, …}` — deterministički i predmet-scoped.

    Tvrdnja tuđeg predmeta se ne pojavljuje u katalogu. To je prva od tri
    nezavisne brave protiv cross-case člana (druga je `validiraj_claim_ref` u
    domenu, treća je GUARD 2 u SQL-u)."""
    if not predmet_id:
        raise GreskaKataloga("Katalog trazi predmet_id — oznaka bez opsega nema znacenje.")

    upotrebljive = [
        d for d in (dokazi or [])
        if _upotrebljiva(d) and (d.get("predmet_id") in (None, predmet_id))
    ]
    # Sortiranje po `id`, ne po redosledu iz baze: ista tvrdnja mora dobiti istu
    # oznaku u dva uzastopna refresh-a.
    upotrebljive.sort(key=lambda d: d["id"])

    return {
        f"{PREFIKS}{i:03d}": d["id"]
        for i, d in enumerate(upotrebljive[:MAKS_TVRDNJI], start=1)
    }


def redovi_za_prompt(katalog: dict[str, str], dokazi: Iterable[dict]) -> list[str]:
    """Redovi koje model vidi. Isti izvor kao katalog — nikad drugi upit.

    Ako bi se ovo gradilo nezavisno od `napravi_katalog`, model bi mogao da vidi
    tvrdnju koja nema oznaku, ili obrnuto."""
    po_id = {d["id"]: d for d in (dokazi or []) if isinstance(d, dict) and d.get("id")}
    redovi = []
    for oznaka, did in katalog.items():
        d = po_id.get(did) or {}
        tvrdnja = (d.get("tvrdnja") or "").strip()
        elm = f" [{d['pravni_element']}]" if d.get("pravni_element") else ""
        redovi.append(f"{oznaka}: {tvrdnja}{elm}")
    return redovi


def razresi_reference(
    refs: Any, katalog: dict[str, str], predmet_id: str,
    poznati_dokazi: Optional[dict[str, dict]] = None,
) -> list[str]:
    """`["CLAIM-001","CLAIM-003"]` -> `[uuid, uuid]`, ili `GreskaKataloga`.

    Duplirana referenca je HARD FAIL, ne tiha deduplikacija (A014 §12 CASE G):
    „CLAIM-001 dva puta" znači da producer nije razumeo sopstveni izlaz, i to je
    podatak koji se ne sme izgubiti sažimanjem u skup."""
    if not isinstance(refs, list):
        raise GreskaKataloga(f"claim_refs mora biti lista, dobijeno {type(refs).__name__}")

    vidjene: set[str] = set()
    razresene: list[str] = []
    for r in refs:
        if not isinstance(r, str) or not r.strip():
            raise GreskaKataloga(f"neispravna referenca: {r!r}")
        oznaka = r.strip()
        if oznaka not in katalog:
            # Nema pogadjanja. Nema prefiks-poklapanja. Nema „najblize".
            raise GreskaKataloga(f"nepoznata referenca: {oznaka!r}")
        if oznaka in vidjene:
            raise GreskaKataloga(f"duplirana referenca: {oznaka!r}")
        vidjene.add(oznaka)
        razresene.append(katalog[oznaka])

    if poznati_dokazi is not None:
        for did in razresene:
            red = poznati_dokazi.get(did)
            if not isinstance(red, dict):
                raise GreskaKataloga(f"tvrdnja {did} ne postoji")
            if red.get("predmet_id") != predmet_id:
                raise GreskaKataloga(f"tvrdnja {did} pripada drugom predmetu")
            if red.get("deleted_at") is not None:
                raise GreskaKataloga(f"tvrdnja {did} je obrisana")

    return razresene
