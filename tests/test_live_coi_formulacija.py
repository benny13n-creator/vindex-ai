# -*- coding: utf-8 -*-
"""OPERATION LIVE — odobrena COI politika bete na STARIM putevima (stvarna HTTP ruta, fake baza, stvarna provera):
POST /api/intake/conflict-check (čarobnjak „ime prvo“, static/vindex.js prikazuje `preporuka` doslovno).

Podudaranje imena je MOGUĆI sukob — nikad kategorično „Ne možete zastupati“. Ozbiljnost (`has_blocker`) ostaje.
"""
from tests.test_fri001_coi_lanac import _postojeci_klijent
from tests.test_osb002_solo_tok import A, B, solo  # noqa: F401 — `solo` je pytest fixture

PAD = Exception('{"code": "57014", "message": "statement timeout"}')


def _provera(k, h=A, **telo):
    return k.post("/api/intake/conflict-check", json={"novi_klijent_ime": "Marko Petrovic", **telo}, headers=h)


def test_podudaranje_imena_je_moguc_sukob_a_ne_kategorican_zakljucak(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO", uloga="tuzilac")          # protivna strana je vaš klijent
    r = _provera(k, protivna_strana="Gradnja Invest DOO")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["has_blocker"] is True and d["status_provere"] == "CONFLICT_FOUND"   # ozbiljnost ostaje
    p = d["preporuka"]
    assert p.startswith("Mogući sukob interesa — potrebna provera")
    assert "nije pravna ocena" in p
    assert "ne možete zastupati" not in p.lower() and "postoji blokirajuci" not in p.lower()
    assert "čl. 42" not in p                                                      # neprovereni navod člana uklonjen


def test_bez_podudaranja_nema_izmisljenog_sukoba(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO")
    d = _provera(k, novi_klijent_ime="Jelena Nikolic", protivna_strana="Delta Promet DOO").json()
    assert d["conflict_detected"] is False and d["status_provere"] == "NO_CONFLICT" and d["conflicts"] == []


def test_neuspela_provera_je_nepoznato_nikad_cisto(solo):
    k, b = solo
    b.greske["klijenti"] = PAD
    r = _provera(k, protivna_strana="Gradnja Invest DOO")
    del b.greske["klijenti"]
    assert r.status_code == 503                    # greška, ne „nema sukoba“ (detalj 5xx menja globalni handler)
    assert "conflict_detected" not in r.text and "NO_CONFLICT" not in r.text


def test_tudji_podaci_ne_cure_kroz_proveru(solo):
    k, b = solo
    _postojeci_klijent(k, b, "Gradnja", "Invest DOO", h=B, naziv="Tajni predmet korisnika B")
    d = _provera(k, h=A, protivna_strana="Gradnja Invest DOO").json()
    assert d["conflict_detected"] is False and "Tajni predmet" not in str(d)
