# -*- coding: utf-8 -*-
"""
RH001 Faza B — Hearing Prep ne sme da predstavi neproverenu pravnu tvrdnju kao utvrđeno pravo.

Rupa (reprodukovana na deac5d99): `proveri_ai_stavke` je odbacivala samo FORMALNE citate (član, zakon o…, Rev 12/23)
i predviđanja ishoda. Implicitni autoritet bez broja propisa — „Prema ustaljenoj praksi Vrhovnog suda…",
„Sudska praksa nalaže…", „Vrhovni sud smatra…", „Teret dokazivanja je uvek na tuženom" — prolazio je uz važeću
referencu na činjenicu iz spisa. Važeća referenca dokazuje da stavka govori o predmetu, NE da je pravna tvrdnja tačna.

Ugovor (hearing_prep.py, NS007 Task 8): Hearing Prep nema proverene pravne izvore → sme pitanja, proceduralne
korake vezane za predmet, sažetke stvarnih činjenica i JASNO označena pitanja za pravnu proveru; ne sme pravne
tvrdnje kao utvrđeno pravo, obavezujuću praksu ni izvesne procesne ishode.
"""
import asyncio
import json

import pytest

from services.agent_tasks import hearing_prep as hp
from shared.pravni_autoritet import tvrdi_pravni_autoritet

POZNATI = {"c1", "k1", "a1"}

# Tvrdnje autoriteta bez formalnog citata — svaka MORA biti odbijena.
ADVERSARIJALNE = [
    "Prema ustaljenoj praksi Vrhovnog suda, ovakav otkaz je nezakonit.",
    "Sudska praksa nalaže da se svedok sasluša pre veštaka.",
    "Vrhovni sud smatra da je potvrda o prijemu dovoljan dokaz.",
    "Teret dokazivanja je uvek na tuženom.",
    "Po praksi sudova, zakašnjela uplata se ne priznaje.",
    "Apelacioni sud je zauzeo stav da je rok prekluzivan.",
    "Pravno shvatanje je da poslodavac mora da dokaže razlog otkaza.",
    "Sudovi dosledno odbijaju ovakve prigovore.",
    "Zakon propisuje da se otkaz uručuje lično.",
    "Po zakonu, zaposleni ima pravo na otpremninu.",
    "Sud mora da odbije dokaz koji nije dostavljen na vreme.",
    "Vrhovni sud stoji na stanovištu da usmeni dogovor ne važi.",
    "Prema praksi Apelacionog suda u Beogradu tužba je osnovana.",
    "Teret dokazivanja leži na poslodavcu.",
    "Ovo je u skladu sa ustaljenom judikaturom.",
    "Sudska praksa nalaze da je dostava uredna.",          # bez dijakritika
    "Kako je poznato iz prakse, sud ne prihvata fotokopije.",
    "Zakonom je propisano da poslodavac mora isplatiti otpremninu.",
    "Propisano je da se dostava vrši preporučeno.",
    "Dosadašnja praksa ide u korist tužioca.",
    "Praksa je da se veštak sasluša prvi.",
    "Ima više presedana u korist poslodavca.",
    "Stav Vrhovnog suda je jasan po ovom pitanju.",
    "Ustaljeno je da se ovakvi zahtevi odbijaju.",
    "Proverite: sudska praksa nalaže pismeno upozorenje.",   # okvir provere ne pere prvi nivo
    # nivo 2 — pravno pravilo kao činjenica
    "Prekluzivni rok je 15 dana.",
    "Zastarelost nastupa posle tri godine.",
    "Poslodavac je dužan da dokaže razlog otkaza.",
    "Otkaz je nezakonit jer nije bilo upozorenja.",
    "Rok za žalbu je osam dana.",
    "Vrhovni sud je više puta potvrdio da je ovakav ugovor ništav.",
    "Opšte je pravilo da se dokazi podnose do pripremnog ročišta.",
    "Poslodavac mora dokazati da je otkaz opravdan.",
    "Tužba je očigledno neosnovana.",
    "Ugovor bez overe nema pravno dejstvo.",
    "Prema shvatanju sudova, svedok mora biti nepristrasan.",
    "U praksi se ovakvi zahtevi odbijaju.",
    # po jedan primer koji hvata SAMO jedan obrazac (mutacija svakog obrasca mora da obori test)
    "Novija sudska praksa drugačije gleda na ovo.",
    "Kako je opšte poznato, ovakvi dokazi se teško osporavaju.",
    "Takvo je pravno shvatanje odeljenja.",
    "Rok za dopunu je prekluzivan.",
]

# Legitimna priprema (pitanje ili zadatak) — svaka MORA proći (ista referenca, isti tok).
LEGITIMNE = [
    "Proverite da li je potpis na ugovoru o radu originalan.",
    "Pripremite pitanja za svedoka Marka o datumu isplate zarade.",
    "Proverite da li postoji praksa Vrhovnog suda o otkazu zbog povrede radne discipline.",
    "Proverite ko snosi teret dokazivanja za isplatu zarade.",
    "Pravno pitanje za proveru: da li je rok za tužbu poštovan?",
    "Razjasnite sa klijentom zašto se datumi u dva dokumenta ne poklapaju.",
    "Pribaviti potvrdu o prijemu otkaza pre ročišta.",
    "Poneti original dostavnice na ročište.",
    "Uporediti datum iz ugovora sa izjavom svedoka.",
    "Ko je potpisao dostavnicu?",
    # nivo 2 dozvoljen samo kao jasno označeno pitanje za proveru
    "Proveriti: da li je potraživanje zastarelo?",
    "Da li je otkaz nezakonit — proveriti pre ročišta?",
    "Proverite da li je rok za žalbu 15 dana.",
    "Pitanje za proveru: da li je poslodavac dužan da dokaže razlog otkaza.",
]

# Deklarativne činjenice koje LIČE na pravne reči. Deljeno pravilo autoriteta ih NE sme označiti (NS008 sinteza
# legitimno piše deklarativno), a Hearing Prep ih odbija po OBLIKU: činjenice već dolaze iz baze sa poreklom.
DEKLARATIVNE_CINJENICE = [
    "Ugovor o radu i izjava svedoka razlikuju se u datumu početka rada.",
    "Ročište je pred Apelacionim sudom u Beogradu u 10:00, sudnica 12.",
    "Rok za odgovor na tužbu ističe 15.10.2026. prema rešenju u spisu.",
    "Društvo tuženog je osnovano 2015. godine.",
    "Osnovni sud je potvrdio prijem podneska 3.9.2026.",
    "Svedok mora da donese originalni ugovor na ročište.",
    "Sudija je na prošlom ročištu odložio raspravu.",
]

# NEZAVISAN skup (napisan posle podešavanja obrazaca, nikad korišćen za njih): lista obrazaca sama hvata 3/15 —
# zato Hearing Prep ne oslanja ugovor na nju, nego na oblik stavke.
NOVE_FORMULACIJE = [
    "Viši sudovi ovakve zahteve tradicionalno ne uvažavaju.",
    "Pravilo je da tužilac dokazuje postojanje potraživanja.",
    "Zaposleni po sili zakona ima pravo na naknadu.",
    "Sudija u ovakvim predmetima obično traži veštačenje.",
    "Ugovor je ništav jer nije overen.",
    "Otkaz bez prethodnog upozorenja ne može opstati.",
    "Ova klauzula je suprotna imperativnim propisima.",
    "Kamata teče od dana dospeća.",
    "Vrhovni kasacioni sud je u sličnom predmetu odbio reviziju.",
    "Najčešće se ovakav spor rešava poravnanjem.",
    "Postoji jasan stav sudova o ovom pitanju.",
    "Ustavni sud je proglasio odredbu neustavnom.",
    "Nadležan je Privredni sud.",
    "Dokaz pribavljen na ovaj način je nezakonit.",
    "Tužilac ima pravo na naknadu nematerijalne štete.",
]

# Autoritet umotan u DOZVOLJEN oblik (zadatak/pitanje) — hvata ga samo deljeno pravilo, nezavisno od oblika.
UMOTAN_AUTORITET = [
    "Pripremite argument da Vrhovni sud smatra potvrdu dovoljnom.",
    "Proverite: sudska praksa nalaže pismeno upozorenje.",
    "Da li će sud prihvatiti dokaz, kad je po zakonu dostava obavezna?",
    "Pripremiti odgovor jer je ugovor ništav.",
]


@pytest.mark.parametrize("tekst", ADVERSARIJALNE)
def test_implicitni_pravni_autoritet_se_odbacuje(tekst):
    out, odbaceno = hp.proveri_ai_stavke({"pitanja": [{"tekst": tekst, "refs": ["c1"]}],
                                          "beleske": [{"tekst": tekst, "refs": ["k1"]}]}, POZNATI)
    assert out == {"pitanja": [], "beleske": []} and odbaceno == 2, tekst


@pytest.mark.parametrize("tekst", LEGITIMNE)
def test_legitimna_priprema_prolazi(tekst):
    out, odbaceno = hp.proveri_ai_stavke({"beleske": [{"tekst": tekst, "refs": ["a1"]}]}, POZNATI)
    assert odbaceno == 0 and [s["tekst"] for s in out["beleske"]] == [tekst], tekst


def test_deljeno_pravilo_samo_hvata_poznate_tvrdnje_bez_lazne_uzbune():
    """Sloj 1 nezavisno od oblika: svaka poznata tvrdnja autoriteta je označena; činjenice i priprema nisu."""
    for t in ADVERSARIJALNE + UMOTAN_AUTORITET:
        assert tvrdi_pravni_autoritet(t), t
    for t in LEGITIMNE + DEKLARATIVNE_CINJENICE:
        assert not tvrdi_pravni_autoritet(t), t


@pytest.mark.parametrize("tekst", DEKLARATIVNE_CINJENICE + NOVE_FORMULACIJE)
def test_deklarativna_stavka_se_odbija_po_obliku(tekst):
    """Sloj 2 nezavisno od liste obrazaca: deklarativna AI stavka ne ulazi u pripremu, ma kako bila formulisana."""
    assert not hp.oblik_pripreme(tekst)
    out, odbaceno = hp.proveri_ai_stavke({"beleske": [{"tekst": tekst, "refs": ["c1"]}]}, POZNATI)
    assert out["beleske"] == [] and odbaceno == 1


@pytest.mark.parametrize("tekst", UMOTAN_AUTORITET)
def test_autoritet_u_dozvoljenom_obliku_se_odbija(tekst):
    """Oblik pitanja/zadatka ne pere tvrdnju autoriteta (oba sloja su potrebna, nijedan nije dovoljan sam)."""
    assert hp.oblik_pripreme(tekst)
    out, odbaceno = hp.proveri_ai_stavke({"pitanja": [{"tekst": tekst, "refs": ["c1"]}]}, POZNATI)
    assert out["pitanja"] == [] and odbaceno == 1


def _det():
    return {
        "rociste": {"id": "r1", "datum": "2026-10-11", "vreme": "10:00", "sud": "Osnovni sud", "sudnica": "3"},
        "predmet": {"id": "p1", "naziv": "X", "genome_verzija": 2, "kompletnost": 0.5},
        "spremnost": {}, "kljucne_cinjenice": [{"id": "c1", "tekst": "Otkaz uručen 2026-03-01.", "poreklo": "SOURCE_FACT"}],
        "protivrecnosti": [], "otvorene_radnje": [], "nedostaje": [],
    }


def test_ai_deo_cuva_legitimno_odbacuje_autoritet(monkeypatch):
    """Ceo AI tok: model vrati mešavinu — u proizvod ulazi samo legitimna stavka, odbijene se broje."""
    odgovor = {"pitanja": [{"tekst": LEGITIMNE[0], "refs": ["c1"]}, {"tekst": ADVERSARIJALNE[0], "refs": ["c1"]}],
               "beleske": [{"tekst": ADVERSARIJALNE[2], "refs": ["c1"]}, {"tekst": ADVERSARIJALNE[3], "refs": ["c1"]}]}

    async def model(prompt, predmet_id, work_id=None):
        return json.dumps(odgovor, ensure_ascii=False)
    monkeypatch.setattr(hp, "_pozovi_model", model)
    r = asyncio.run(hp.ai_deo(_det(), "p1", "w1"))
    assert r["stanje"] == "PRIPREMLJENO" and r["odbaceno"] == 3
    assert [s["tekst"] for s in r["pitanja"]] == [LEGITIMNE[0]] and r["beleske"] == []


def test_ai_deo_samo_autoritet_nije_pripremljeno(monkeypatch):
    """Ako je SVE odbijeno, proizvod nema AI deo (deterministički deo iz baze ostaje) — ne prazna „priprema"."""
    async def model(prompt, predmet_id, work_id=None):
        return json.dumps({"pitanja": [{"tekst": t, "refs": ["c1"]} for t in ADVERSARIJALNE[:4]]}, ensure_ascii=False)
    monkeypatch.setattr(hp, "_pozovi_model", model)
    r = asyncio.run(hp.ai_deo(_det(), "p1", "w1"))
    assert r["stanje"] == "NIJE_PRIPREMLJENO" and r["razlog"] == "NIJEDNA_STAVKA_NIJE_PROSLA_PROVERU" and r["odbaceno"] == 4


def test_uputstvo_modelu_zabranjuje_implicitni_autoritet():
    """Prva linija odbrane (uputstvo) i druga (validator) su nezavisne; uputstvo mora da imenuje klasu."""
    s = hp._SISTEM.lower()
    assert "sudska praksa" in s and "proveriti:" in s
