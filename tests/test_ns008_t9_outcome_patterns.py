# -*- coding: utf-8 -*-
"""NS008 Task 9 — opis prošlih ishoda: samo ljudski ishodi, brojevi iz koda, uvek imenilac, nikad predviđanje."""
import json
import re

import pytest

from services import law_brain as lb


def _profil(pid, ishod=None, status=None, faktori=()):
    st = status or (lb.OUTCOME_RECORDED if ishod else lb.OUTCOME_UNKNOWN)
    item = None
    if ishod and st in (lb.OUTCOME_RECORDED, lb.OUTCOME_REOPENED):
        item = {"trust_class": lb.HUMAN_CONFIRMED_OUTCOME, "attrs": {"presudni_faktori": tuple(faktori)}}
    return {"predmet_id": pid, "ljudski_ishod": {"status": st, "ishod": ishod, "item": item}}


PROFILI = [
    _profil("p1", "pobeda", faktori=("svedoci", "pisana_komunikacija")),
    _profil("p2", "pobeda", faktori=("svedoci",)),
    _profil("p3", "nagodba", faktori=("svedoci", "vestacenje")),
    _profil("p4", "poraz", faktori=("pisana_komunikacija",)),
    _profil("p5"),                                            # zatvoren, ishod nepoznat
    _profil("p6", "pobeda", status=lb.OUTCOME_REOPENED),      # ponovo otvoren
]


def test_brojevi_i_imenilac():
    r = lb.descriptive_outcomes(PROFILI)
    assert (r["relevantnih"], r["sa_ljudskim_ishodom"], r["bez_ishoda"], r["ponovo_otvoreni"]) == (6, 4, 1, 1)
    assert r["po_ishodu"] == {"pobeda": 2, "poraz": 1, "nagodba": 1}
    assert r["faktori"][0] == {"faktor": "svedoci", "naziv": "Svedoci", "broj": 3, "od": 4}
    assert {"faktor": "pisana_komunikacija", "naziv": "Pisana komunikacija", "broj": 2, "od": 4} in r["faktori"]
    assert r["uzorak"] == 4 and r["mali_uzorak"] is True


def test_recenice_bez_procenata_i_predvidjanja():
    r = lb.descriptive_outcomes(PROFILI)
    tekst = " ".join(r["recenice"]) + r["napomena"]
    assert "Zabeleženi ishodi: 2 pobeda, 1 poraz, 1 nagodba." in r["recenice"]
    assert "Faktor „Svedoci“ izričito zabeležen u 3 od 4 ishoda." in r["recenice"]
    assert "Veličina uzorka: 4." in r["recenice"]
    assert "%" not in json.dumps(r, ensure_ascii=False)
    for zabranjeno in ("šansa", "verovatno", "očekuje", "win rate", "predviđ"):
        if zabranjeno == "predviđ":
            assert "Nije predviđanje" in tekst
            continue
        assert zabranjeno not in tekst.lower()


def test_nepoznat_i_ponovo_otvoren_ishod_se_ne_broje_kao_ishod():
    r = lb.descriptive_outcomes([_profil("a"), _profil("b", "pobeda", status=lb.OUTCOME_REOPENED)])
    assert r["sa_ljudskim_ishodom"] == 0 and r["po_ishodu"] == {} and r["faktori"] == []
    assert not any(re.search(r"\d+ pobeda", s) for s in r["recenice"])


def test_ishod_bez_ljudskog_izvora_se_ne_broji():
    lazni = {"predmet_id": "x", "ljudski_ishod": {"status": lb.OUTCOME_RECORDED, "ishod": "pobeda", "item": None}}
    assert lb.descriptive_outcomes([lazni])["sa_ljudskim_ishodom"] == 0


def test_prazno():
    r = lb.descriptive_outcomes([])
    assert r["relevantnih"] == 0 and r["recenice"] == [] and r["mali_uzorak"] is True


def test_veliki_uzorak_nije_mali():
    r = lb.descriptive_outcomes([_profil(f"p{i}", "pobeda") for i in range(5)])
    assert r["mali_uzorak"] is False and r["po_ishodu"] == {"pobeda": 5}


def test_modul_ne_zove_model_za_statistiku():
    import inspect
    src = inspect.getsource(lb.descriptive_outcomes)
    assert "openai" not in src.lower() and "chat" not in src.lower()


@pytest.mark.parametrize("n,ocekivano", [(1, "1 relevantan raniji predmet"), (2, "2 relevantna ranija predmeta"),
                                         (5, "5 relevantnih ranijih predmeta"), (11, "11 relevantnih ranijih predmeta"),
                                         (21, "21 relevantan raniji predmet"), (12, "12 relevantnih ranijih predmeta")])
def test_srpska_mnozina(n, ocekivano):
    assert lb.descriptive_outcomes([_profil(f"p{i}") for i in range(n)])["recenice"][0].startswith(ocekivano + ";")
