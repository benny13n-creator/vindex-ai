# -*- coding: utf-8 -*-
"""
Program Beta (2026-08-04) — sistemsko_upozorenje u
strategija.py::orkestrator_kompletna_analiza_sync vise NIJE odluka koju
donosi Synthesis LLM poziv (prompt-instrukcija "ako su >=2 koraka NISKA,
postavi..."), vec deterministicki racunata u kodu iz istih 5 already-
prisutnih po-koraka confidence vrednosti (isti princip kao Court Predictor i
compute_snaga_score -- "LLM rezonuje, platforma racuna"). Ovi testovi
dokazuju da kod NADJACAVA LLM izlaz u oba smera (kad LLM propusti da
postavi upozorenje ISPOD praga, kad LLM pogresno postavi upozorenje).
"""
import json
import sys, os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import strategija


def _resp(content: str):
    m = MagicMock()
    m.usage = None
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


def test_orkestrator_sistemsko_upozorenje_racuna_se_deterministicki_ne_llm():
    responses = [
        _resp(json.dumps({"confidence": "NISKA", "ocena": "SPREMAN ZA UPOTREBU"})),   # korak1 revizor
        _resp(json.dumps({"confidence": "NISKA", "preporuka": "PREGOVARATI"})),        # korak2 due diligence
        _resp(json.dumps({"confidence": "SREDNJA", "ukupna_ranjivost": "NISKA"})),     # korak4 red team
        _resp("Argumenti tuzioca..."),                                                  # korak5: tuzilac (text)
        _resp("Argumenti branioca..."),                                                 # korak5: branilac (text)
        _resp(json.dumps({"confidence": "VISOKA", "procena_uspeha_tuzilac": 55})),      # korak5: presuda
        _resp(json.dumps({                                                              # korak6 synthesis
            "executive_summary": "test",
            "sistemsko_upozorenje": None,  # LLM (pogresno) ne postavlja upozorenje
            "opsta_confidence": "SREDNJA",
        })),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    # 2 od 4 relevantnih koraka (korak3/witness preskocen -- nije dostavljen)
    # imaju NISKA -- kod mora postaviti upozorenje bez obzira sto ga LLM nije.
    assert rezultat["sinteza"]["sistemsko_upozorenje"] is not None
    assert "2 od 4" in rezultat["sinteza"]["sistemsko_upozorenje"]


def test_orkestrator_sistemsko_upozorenje_ne_okida_ispod_praga():
    responses = [
        _resp(json.dumps({"confidence": "NISKA"})),
        _resp(json.dumps({"confidence": "VISOKA"})),
        _resp(json.dumps({"confidence": "SREDNJA"})),
        _resp("tuzilac"),
        _resp("branilac"),
        _resp(json.dumps({"confidence": "VISOKA", "procena_uspeha_tuzilac": 60})),
        _resp(json.dumps({
            "executive_summary": "test",
            "sistemsko_upozorenje": "LLM je (pogresno) samo postavio ovo",
            "opsta_confidence": "VISOKA",
        })),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    # Samo 1 od 4 relevantnih koraka je NISKA -- ispod praga, kod mora
    # NADJACATI LLM-ovu (pogresnu) string vrednost nazad na None.
    assert rezultat["sinteza"]["sistemsko_upozorenje"] is None


def test_orkestrator_witness_nije_primenljivo_se_ne_broji():
    """Kad su iskazi_svedoka dostavljeni ali witness modul vrati
    NIJE_PRIMENLJIVO (postoji i taj put), i dalje se ne racuna u imenilac --
    ali ovde testiramo podrazumevani slucaj (iskazi_svedoka=None), gde se
    korak3 nikad ne poziva kao GPT (fiksni skip dict sa NIJE_PRIMENLJIVO)."""
    responses = [
        _resp(json.dumps({"confidence": "NISKA"})),
        _resp(json.dumps({"confidence": "NISKA"})),
        _resp(json.dumps({"confidence": "SREDNJA"})),
        _resp("tuzilac"), _resp("branilac"),
        _resp(json.dumps({"confidence": "SREDNJA", "procena_uspeha_tuzilac": 50})),
        _resp(json.dumps({"executive_summary": "x", "sistemsko_upozorenje": None, "opsta_confidence": "SREDNJA"})),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test", iskazi_svedoka=None,
        )

    assert rezultat["koraci"]["korak_3_witness_analyzer"]["confidence"] == "NIJE_PRIMENLJIVO"
    # imenilac mora biti 4 (bez witness-a), ne 5
    assert "od 4" in rezultat["sinteza"]["sistemsko_upozorenje"]


def test_orkestrator_json_parse_greska_se_ne_broji_kao_stvarna_niska_pouzdanost():
    """Olympus Faza 10 (2026-08-04, Workflow Integrity nalaz): _gpt_json-ov
    JSON-decode-failure fallback sintetički vraca confidence=NISKA za
    TEHNICKU gresku (API/parsing), ne pravnu analizu -- kod mora razdvojiti
    ovo od stvarnog niskog pouzdanja umesto da ga tiho izjednaci."""
    responses = [
        _resp("ovo nije validan JSON"),                    # korak1 -- izaziva JSONDecodeError fallback
        _resp(json.dumps({"confidence": "VISOKA"})),       # korak2
        _resp(json.dumps({"confidence": "VISOKA"})),       # korak4
        _resp("tuzilac"), _resp("branilac"),
        _resp(json.dumps({"confidence": "VISOKA", "procena_uspeha_tuzilac": 70})),
        _resp(json.dumps({"executive_summary": "x", "sistemsko_upozorenje": None, "opsta_confidence": "VISOKA"})),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    assert rezultat["koraci"]["korak_1_pravni_revizor"]["error"] == "JSON decode failed"
    # samo 1 korak je stvarno VISOKA/SREDNJA/NISKA relevantan i taj je VISOKA -- ne sme preci prag
    # ali greska korak mora biti eksplicitno pomenuta u poruci, ne skrivena
    poruka = rezultat["sinteza"]["sistemsko_upozorenje"]
    assert poruka is not None
    assert "tehničku grešku" in poruka


def test_orkestrator_neocekivana_confidence_vrednost_se_racuna_kao_anomalija():
    """Olympus Faza 10 (2026-08-04, Workflow Integrity nalaz): confidence
    vrednost van {VISOKA,SREDNJA,NISKA} (npr. GPT pomesao polje sa susednim
    ocena_pouzdanosti enum-om) se vise NE gubi tiho iz brojanja -- racuna se
    konzervativno kao anomalija koja doprinosi upozorenju."""
    responses = [
        _resp(json.dumps({"confidence": "NEPOUZDANO"})),   # korak1 -- off-spec vrednost za ovo polje
        _resp(json.dumps({"confidence": "NISKA"})),         # korak2
        _resp(json.dumps({"confidence": "VISOKA"})),        # korak4
        _resp("tuzilac"), _resp("branilac"),
        _resp(json.dumps({"confidence": "VISOKA", "procena_uspeha_tuzilac": 65})),
        _resp(json.dumps({"executive_summary": "x", "sistemsko_upozorenje": None, "opsta_confidence": "VISOKA"})),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    # 1 stvarna NISKA (korak2) + 1 anomalija (korak1) = 2 -- prelazi prag
    poruka = rezultat["sinteza"]["sistemsko_upozorenje"]
    assert poruka is not None
    assert "neočekivanu confidence vrednost" in poruka


# ═══════════════════════════════════════════════════════════════════════════
# Program Gamma (2026-08-04) — detektovani_konflikti: isti defekt kao
# sistemsko_upozorenje (LLM-executed rule prompt sam navodi kao proverljivu),
# ostavljen neispravljen istog dana u istoj funkciji. Kod DODAJE garantovano
# uhvacene kategoricke konflikte, ne zamenjuje LLM-ovu semanticku analizu.
# ═══════════════════════════════════════════════════════════════════════════

def test_detektovani_konflikti_racuna_spreman_vs_visoka_ranjivost():
    responses = [
        _resp(json.dumps({"confidence": "VISOKA", "ocena": "SPREMAN ZA UPOTREBU"})),   # korak1
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ocena": "BEZBEDAN"})),        # korak2
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ranjivost": "VISOKA"})),      # korak4
        _resp("tuzilac"), _resp("branilac"),
        _resp(json.dumps({"confidence": "VISOKA", "izreka": "TUZBA USVOJENA", "procena_uspeha_tuzilac": 80})),
        _resp(json.dumps({"executive_summary": "x", "detektovani_konflikti": [], "opsta_confidence": "VISOKA"})),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    konflikti = rezultat["sinteza"]["detektovani_konflikti"]
    assert len(konflikti) == 1
    assert "SPREMAN ZA UPOTREBU" in konflikti[0]
    assert "VISOKA ranjivost" in konflikti[0]


def test_detektovani_konflikti_racuna_neprihvatljiv_vs_tuzba_usvojena_za_litigacioni_predmet():
    """Olympus Faza 10 (2026-08-04, Legal Domain Expert nalaz): pravilo 2 se
    okida SAMO kad je Due Diligence sam prepoznao litigacioni tip dokumenta
    (preporuka u {PODNETI, ISPRAVITI_PA_PODNETI, NE_PODNETI}) -- inace bi
    poredjenje sa Korak 5 (Sudija, koji se izvrsava BEZUSLOVNO cak i za
    transakcione predmete) bila greska kategorije, ne pravno neslaganje."""
    responses = [
        _resp(json.dumps({"confidence": "VISOKA", "ocena": "POTREBNE IZMENE"})),
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ocena": "NEPRIHVATLJIV", "preporuka": "NE_PODNETI"})),  # korak2
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ranjivost": "NISKA"})),
        _resp("tuzilac"), _resp("branilac"),
        _resp(json.dumps({"confidence": "VISOKA", "izreka": "TUZBA USVOJENA", "procena_uspeha_tuzilac": 80})),  # korak5
        _resp(json.dumps({"executive_summary": "x", "detektovani_konflikti": ["LLM-ov sopstveni nalaz"], "opsta_confidence": "VISOKA"})),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    konflikti = rezultat["sinteza"]["detektovani_konflikti"]
    # LLM-ov sopstveni nalaz je OCUVAN (dodato, ne zamenjeno), plus 1 izracunat.
    assert "LLM-ov sopstveni nalaz" in konflikti
    assert any("NEPRIHVATLJIV" in k and "TUZBA USVOJENA" in k for k in konflikti)
    assert len(konflikti) == 2


def test_detektovani_konflikti_ne_okida_za_transakcioni_predmet():
    """Isti kategoricki sudar (NEPRIHVATLJIV + TUZBA USVOJENA) ali Due
    Diligence-ova preporuka je ugovorno-oblikovana (POTPISATI) -- Korak 5
    je za ovaj predmet bezuslovno izvrsen ali nije stvarno primenljiv
    (nema tuzbe), pa pravilo 2 NE sme da se okine."""
    responses = [
        _resp(json.dumps({"confidence": "VISOKA", "ocena": "POTREBNE IZMENE"})),
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ocena": "NEPRIHVATLJIV", "preporuka": "POTPISATI"})),  # korak2 -- ugovor, ne tuzba
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ranjivost": "NISKA"})),
        _resp("tuzilac"), _resp("branilac"),
        _resp(json.dumps({"confidence": "VISOKA", "izreka": "TUZBA USVOJENA", "procena_uspeha_tuzilac": 80})),  # korak5
        _resp(json.dumps({"executive_summary": "x", "detektovani_konflikti": [], "opsta_confidence": "VISOKA"})),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    assert rezultat["sinteza"]["detektovani_konflikti"] == []


def test_detektovani_konflikti_ne_dodaje_nista_kad_nema_kategorickog_sudara():
    responses = [
        _resp(json.dumps({"confidence": "VISOKA", "ocena": "SPREMAN ZA UPOTREBU"})),
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ocena": "BEZBEDAN"})),
        _resp(json.dumps({"confidence": "VISOKA", "ukupna_ranjivost": "NISKA"})),
        _resp("tuzilac"), _resp("branilac"),
        _resp(json.dumps({"confidence": "VISOKA", "izreka": "TUZBA ODBIJENA", "procena_uspeha_tuzilac": 20})),
        _resp(json.dumps({"executive_summary": "x", "detektovani_konflikti": [], "opsta_confidence": "VISOKA"})),
    ]

    with patch("strategija._pozovi_strategija_api", side_effect=responses):
        rezultat = strategija.orkestrator_kompletna_analiza_sync(
            opis_predmeta="Test predmet.", api_key="sk-test",
        )

    assert rezultat["sinteza"]["detektovani_konflikti"] == []
