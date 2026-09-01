# -*- coding: utf-8 -*-
"""D-1 — DOKUMENT BEZ TEKSTA NE SME TIHO NESTATI IZ GENOME OBRADE.

ŠTA JE BIO PROBLEM
==================
Na DVA mesta je stajalo isto filtriranje:

    docs = [d for d in (dok_res.data or []) if (d.get("tekst_sadrzaj") or "").strip()]

Dokument bez teksta — tačno ono što ostane posle neuspelog OCR-a — tiho je
ispadao iz analize. Izmereno uživo 4/4: predmet sa 2 dokumenta → Genome
analizirao 1, `_genome_docs_preskoceno = 0`, `upozorenja = None`.

Advokat uploaduje skeniranu presudu, ona se pojavi u predmetu, AI je nikad ne
pročita — i **ništa to ne kaže**.

ŠTA JE SADA
===========
Jedan vlasnik podele (`_razdvoji_dokumente_po_tekstu`) i sistemsko polje
`case_dna._dokumenti_bez_teksta` sa `id`/`naziv_fajla`/`redni_broj`.

Živi dokaz (9/9) je u `SPRINT — OCR + D-1 REPORT.md`. Ovde je regresiona brava.

GRANICA
=======
Dokument bez teksta se i dalje NE šalje modelu — to bi bio prazan kontekst.
Beleži se **činjenica** da nije analiziran, nikad **uzrok** (neuspeo OCR i
prazan fajl se odavde ne razlikuju i ne izmišljaju).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

IZVOR = os.path.join(os.path.dirname(__file__), "..", "routers", "case_dna.py")


def _izvor() -> str:
    with open(IZVOR, encoding="utf-8") as fh:
        return fh.read()


def _telo(ime: str) -> str:
    s = _izvor()
    poc = s.index(f"def {ime}(")
    ost = s[poc + 6:]
    kraj = len(s)
    for m in ("\nasync def ", "\ndef ", "\n@router"):
        k = ost.find(m)
        if k != -1:
            kraj = min(kraj, poc + 6 + k)
    return s[poc:kraj]


# ═══════════════════════════════════════════════════════════════════════════
# 1. PODELA — jedan vlasnik, bez tihog gubitka
# ═══════════════════════════════════════════════════════════════════════════

def test_podela_vraca_obe_liste():
    from routers.case_dna import _razdvoji_dokumente_po_tekstu
    redovi = [
        {"id": "a", "naziv_fajla": "tuzba.docx", "tekst_sadrzaj": "Tužilac traži..."},
        {"id": "b", "naziv_fajla": "sken.pdf", "tekst_sadrzaj": ""},
        {"id": "c", "naziv_fajla": "prazan.pdf", "tekst_sadrzaj": None},
        {"id": "d", "naziv_fajla": "razmaci.pdf", "tekst_sadrzaj": "   \n\t "},
    ]
    za, bez = _razdvoji_dokumente_po_tekstu(redovi)
    assert [d["id"] for d in za] == ["a"]
    assert [d["id"] for d in bez] == ["b", "c", "d"], \
        "dokument bez teksta se gubi umesto da bude vraćen pozivaocu"


def test_nijedan_dokument_se_ne_gubi():
    """Zbir obe liste mora biti ulaz — to je cela poenta D-1."""
    from routers.case_dna import _razdvoji_dokumente_po_tekstu
    redovi = [{"id": str(i), "tekst_sadrzaj": ("x" if i % 2 else "")} for i in range(10)]
    za, bez = _razdvoji_dokumente_po_tekstu(redovi)
    assert len(za) + len(bez) == len(redovi)
    assert {d["id"] for d in za} | {d["id"] for d in bez} == {d["id"] for d in redovi}


def test_prazan_ulaz_ne_puca():
    from routers.case_dna import _razdvoji_dokumente_po_tekstu
    assert _razdvoji_dokumente_po_tekstu(None) == ([], [])
    assert _razdvoji_dokumente_po_tekstu([]) == ([], [])


def test_zapis_nosi_identitet_a_ne_samo_ime():
    """Ime fajla nije identitet (A001). Zapis mora nositi `id`."""
    from routers.case_dna import _zapis_o_neanaliziranim
    z = _zapis_o_neanaliziranim([{"id": "u-1", "naziv_fajla": "s.pdf", "redni_broj": 3}])
    assert z == [{"id": "u-1", "naziv_fajla": "s.pdf", "redni_broj": 3}]


def test_zapis_praznog_skupa_je_prazna_lista():
    """`[]` i `None` se moraju razlikovati: `[]` znači „provereno, nema ih",
    `None` bi značilo „polje ne postoji / stariji zapis"."""
    from routers.case_dna import _zapis_o_neanaliziranim
    assert _zapis_o_neanaliziranim([]) == []
    assert _zapis_o_neanaliziranim(None) == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. OBA PROIZVOĐAČA — jedan ugovor
# ═══════════════════════════════════════════════════════════════════════════

def test_staro_tiho_filtriranje_vise_ne_postoji():
    s = _izvor()
    assert 'docs = [d for d in (dok_res.data or []) if (d.get("tekst_sadrzaj") or "").strip()]' not in s, \
        "vratilo se tiho filtriranje — dokument bez teksta opet nestaje"


@pytest.mark.parametrize("funkcija", ["_do_genome_refresh", "_refresh_case_dna_body"])
def test_oba_puta_koriste_jednog_vlasnika(funkcija):
    telo = _telo(funkcija)
    assert "_razdvoji_dokumente_po_tekstu(dok_res.data)" in telo, \
        f"{funkcija} ne koristi zajedničku podelu"


@pytest.mark.parametrize("funkcija", ["_do_genome_refresh", "_refresh_case_dna_body"])
def test_oba_puta_upisuju_neanalizirane_u_case_dna(funkcija):
    """Mora se meriti UPIS U `genome`, ne samo prisustvo poziva.

    Ručni put poziva `_zapis_o_neanaliziranim` i u ranom `return`-u kada
    nijedan dokument nema tekst — pa je slabija provera („poziv postoji")
    preživela mutaciju koja briše upis u `genome`."""
    telo = _telo(funkcija)
    assert 'genome["_dokumenti_bez_teksta"] = _zapis_o_neanaliziranim(_bez_teksta)' in telo, \
        f"{funkcija} ne upisuje neanalizirane dokumente u case_dna"


def test_polje_je_sistemsko_a_ne_llm():
    """`upozorenja[]` puni model i čita ga `case_intelligence`. Sistemska
    činjenica u tom polju bi dala dva vlasnika istog podatka."""
    s = _izvor()
    assert '"_dokumenti_bez_teksta"' in s
    assert 'upozorenja"] = _zapis' not in s and "upozorenja'] = _zapis" not in s, \
        "sistemska činjenica se upisuje u LLM polje"


def test_svi_prazni_ne_zovu_model_i_ne_pisu_case_dna():
    telo = _telo("_do_genome_refresh")
    i = telo.index("if not docs:")
    odsecak = telo[i:i + 500]
    assert "NIJEDAN" in odsecak, "izlazak bez ijednog dokumenta sa tekstom je i dalje tih"
    assert "return" in odsecak


def test_rucni_put_kaze_korisniku_koliko_dokumenata_nije_procitano():
    """Prozor se racuna DO KRAJA `return {...}` bloka, ne fiksnih N znakova.

    Raniji fiksni prozor od 900 znakova merio je duzinu odsecka, a ne ugovor:
    kada je RG-1 dodao `case_dna_persisted` u isti dict, ceo blok je narastao
    na 992 znaka i `dokumenti_bez_teksta` je ispao iz prozora -- test je pao
    iako oba polja i dalje POSTOJE u odgovoru. Isti kvar fiksnog prozora, i
    isti popravak, kao u `test_b8_rok_izvor_identitet.py`."""
    telo = _telo("_refresh_case_dna_body")
    i = telo.index("if not docs:")
    odsecak = telo[i:telo.index(chr(125) + chr(10), i) + 1]
    assert "dokumenti_bez_teksta" in odsecak, \
        "odgovor ne nosi listu nepročitanih dokumenata"
    assert "len(_bez_teksta)" in odsecak, \
        "poruka ne kaže KOLIKO dokumenata nije pročitano"
