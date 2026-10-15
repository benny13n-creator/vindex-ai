# -*- coding: utf-8 -*-
"""QA-06 (dug iz PR #40) — odgovor savetnika koji NAZIVOM FAJLA pominje dokument čiji tekst nije dobio.

Pre ispravke (`649583c7`): `_pominje_nedostavljene` je prepoznavao samo oznake DOK-NN. Kada model napiše
„u zapisnik_rociste.pdf piše…“ za dokument koji nije dostavljen, upozorenje je izostajalo.

Ovde se proverava samo deterministička veza „tačan naziv fajla iz OVOG predmeta → oznaka dokumenta“: nema
semantičkog pogađanja, nema delimičnog poklapanja, nema naziva iz tuđeg predmeta. Model je mock, pa se ponašanje
stvarnog modela ne tvrdi.
"""
import json

import pytest

from tests.ns005_harness import zaglavlje
from tests.test_qa08_izvori_savetnika import PA, PB, _dok, ag, _run  # noqa: F401  (ag je fixture)

TUDJI = "tajni_izvestaj_klijenta_b.pdf"


def _baza7():
    """Sedam dokumenata; bez traženog dokumenta model dobija DOK-07…DOK-03, a DOK-02 i DOK-01 su izostavljeni."""
    nazivi = {1: "ugovor.pdf", 2: "zapisnik_rociste.pdf", 3: "aneks ugovor.pdf", 4: "ugovor_2.pdf",
              5: "05_dopis.pdf", 6: "06_racun.pdf", 7: "07_opomena.pdf"}
    dok = [_dok(rb, f"Dokument {rb}. Neutralan sadržaj.", naziv) for rb, naziv in nazivi.items()]
    dok.append(_dok(1, "TAJNA-B", TUDJI, predmet=PB, uid="uid-B"))
    dok.append(_dok(2, "TAJNA-B2", "zapisnik_rociste.pdf", predmet=PB, uid="uid-B"))
    return {"predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Sintetički QA-06", "tip": "parnicno",
                          "status": "aktivan", "tuzilac": "A", "tuzeni": "B", "opis": "", "case_dna": None},
                         {"id": PB, "user_id": "uid-B", "naziv": "Tajni B", "status": "aktivan"}],
            "predmet_dokumenti": dok, "rocista": []}


def _pominje(ag, odgovor, baza=None):
    pr, st = ag
    k, _ = pr(baza or _baza7())
    st["odgovor"] = odgovor
    d = _run(k, "Daj opštu procenu predmeta.")
    return d, d["izvori_predmeta"]["odgovor_pominje_nedostavljene"]


def test_postavka_dva_izostavljena(ag):
    d, _ = _pominje(ag, "OK")
    iz = d["izvori_predmeta"]
    assert [u["oznaka"] for u in iz["ukljuceni"]] == ["DOK-07", "DOK-06", "DOK-05", "DOK-04", "DOK-03"]
    assert [x["oznaka"] for x in iz["izostavljeni"]] == ["DOK-02", "DOK-01"]


# A1 / A9 — oznaka i dalje radi kao pre
def test_A_oznaka_nedostavljenog(ag):
    assert _pominje(ag, "Prema DOK-02 ročište je odloženo.")[1] == ["DOK-02"]


# A2 — tačan naziv fajla (pre ispravke: [])
def test_B_tacan_naziv_nedostavljenog(ag):
    assert _pominje(ag, "U zapisnik_rociste.pdf stoji da je ročište odloženo.")[1] == ["DOK-02 (zapisnik_rociste.pdf)"]


def test_B_naziv_bez_obzira_na_velika_slova_i_interpunkciju(ag):
    assert _pominje(ag, "Vidi „Ugovor.PDF“.")[1] == ["DOK-01 (ugovor.pdf)"]


def test_B_oznaka_i_naziv_istog_dokumenta_jedno_upozorenje(ag):
    assert _pominje(ag, "DOK-02 (zapisnik_rociste.pdf) kaže…")[1] == ["DOK-02"]


# A4 — sličan naziv nije dokaz
@pytest.mark.parametrize("odgovor", [
    "U aneks ugovor.pdf piše…",           # dostavljen dokument čiji naziv SADRŽI naziv nedostavljenog
    "Vidi ugovor_2.pdf.",                  # dostavljen, sličan prefiks
    "Vidi stari_ugovor.pdf.",              # ne postoji, sadrži naziv nedostavljenog
    "Vidi ugovor.pdf.bak.",                # duži naziv
    "Vidi ugovor-pdf i ugovor.",           # deo naziva
    "Vidi zapisnik_rociste.pdfx.",
])
def test_C_slican_naziv_ne_pravi_lazno_upozorenje(ag, odgovor):
    assert _pominje(ag, odgovor)[1] == []


# A3 — dostavljen dokument
def test_D_naziv_dostavljenog(ag):
    assert _pominje(ag, "U 07_opomena.pdf i 06_racun.pdf piše…")[1] == []


# A5 — tuđ predmet
def test_E_naziv_iz_tudjeg_predmeta_nije_ni_upozorenje_ni_curenje(ag):
    d, poz = _pominje(ag, f"Vidi {TUDJI}.")
    assert poz == []
    telo = json.dumps(d, ensure_ascii=False)
    assert TUDJI not in telo.replace(f"Vidi {TUDJI}.", "") and "TAJNA-B" not in telo


def test_E_isti_naziv_kod_drugog_korisnika_vazi_samo_sopstveni_dokument(ag):
    pr, st = ag
    k, _ = pr(_baza7())
    st["odgovor"] = "U zapisnik_rociste.pdf piše…"
    r = k.post("/api/agents/run", json={"agent": "intake", "task": "Procena.", "predmet_id": PA}, headers=zaglavlje("B"))
    assert r.status_code == 200 and r.json()["izvori_predmeta"] is None        # B ne vidi A-ov predmet
    assert _run(k, "Procena.")["izvori_predmeta"]["odgovor_pominje_nedostavljene"] == ["DOK-02 (zapisnik_rociste.pdf)"]


def test_dvosmislen_naziv_ne_tvrdi_nedostavljen(ag):
    """Isti naziv za dostavljen i nedostavljen dokument istog predmeta — nije dokazivo koji je pomenut."""
    b = _baza7()
    b["predmet_dokumenti"] = [d if d["redni_broj"] != 7 or d["predmet_id"] != PA else {**d, "naziv_fajla": "ugovor.pdf"}
                              for d in b["predmet_dokumenti"]]
    assert _pominje(ag, "Vidi ugovor.pdf.", b)[1] == []


def test_kratak_naziv_se_ne_poredi(ag):
    b = _baza7()
    b["predmet_dokumenti"] = [d if d["redni_broj"] != 1 or d["predmet_id"] != PA else {**d, "naziv_fajla": "a.pd"}
                              for d in b["predmet_dokumenti"]]
    assert _pominje(ag, "Ovo je a.pd i rad.", b)[1] == []


# A8 — odgovor se ne menja; A7 — bez skrivenih polja i bez rasta odgovora
def test_odgovor_nepromenjen_i_bez_internih_polja(ag):
    odg = "U zapisnik_rociste.pdf i DOK-01 piše…"
    d, poz = _pominje(ag, odg)
    assert d["odgovor"] == odg and poz == ["DOK-01", "DOK-02 (zapisnik_rociste.pdf)"]
    assert not [kl for kl in d["izvori_predmeta"] if kl.startswith("_")]


def test_mnogo_dokumenata_spisak_upozorenja_ostaje_ogranicen(ag):
    pr, st = ag
    dok = [_dok(rb, f"Dokument {rb}.", f"prilog_{rb:03d}.pdf") for rb in range(1, 121)]
    k, _ = pr({"predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Veliki", "status": "aktivan", "opis": ""}],
               "predmet_dokumenti": dok, "rocista": []})
    st["odgovor"] = " ".join(f"prilog_{rb:03d}.pdf" for rb in range(1, 121))
    d = _run(k, "Procena.")
    iz = d["izvori_predmeta"]
    assert len(iz["odgovor_pominje_nedostavljene"]) == 30 and len(iz["izostavljeni"]) == 50
    # i dokument izvan javnog spiska `izostavljeni` (prvih 50) se prepoznaje
    st["odgovor"] = "Vidi prilog_001.pdf."
    assert _run(k, "Procena.")["izvori_predmeta"]["odgovor_pominje_nedostavljene"] == ["DOK-01 (prilog_001.pdf)"]


def test_greska_citanja_teksta_naziv_se_i_dalje_oznacava(ag, monkeypatch):
    pr, st = ag
    k, _ = pr(_baza7())
    import tests.ns005_harness as H
    _execute = H._Upit.execute

    def _pad(self):
        if self.t == "predmet_dokumenti" and any(o == "in" for o, _k, _v in self.filt):
            raise RuntimeError("tekst nedostupan")
        return _execute(self)
    monkeypatch.setattr(H._Upit, "execute", _pad)
    st["odgovor"] = "U 07_opomena.pdf piše…"
    assert _run(k, "Procena.")["izvori_predmeta"]["odgovor_pominje_nedostavljene"] == ["DOK-07 (07_opomena.pdf)"]


def test_paralelni_savetnici_koriste_isti_helper(ag):
    pr, st = ag
    k, _ = pr(_baza7())
    st["odgovor"] = "U zapisnik_rociste.pdf piše…"
    r = k.post("/api/agents/run-parallel", json={"task": "Procena.", "predmet_id": PA}, headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert all(x["pominje_nedostavljene"] == ["DOK-02 (zapisnik_rociste.pdf)"] for x in d["rezultati"])
    assert not [kl for kl in d["izvori_predmeta"] if kl.startswith("_")]


def test_niz_savetnika(ag):
    pr, st = ag
    k, _ = pr(_baza7())
    st["odgovor"] = "U zapisnik_rociste.pdf piše…"
    r = k.post("/api/agents/pipeline", json={"opis": "Procena.", "predmet_id": PA, "pipeline": ["research", "drafting"]},
               headers=zaglavlje("A"))
    assert r.status_code == 200, r.text
    assert all(x["pominje_nedostavljene"] == ["DOK-02 (zapisnik_rociste.pdf)"] for x in r.json()["rezultati"])


def test_nesaglasnost_server_dostavio_model_tvrdi_da_nije_procitao(ag):
    """Produkcioni QA oblik: evidencija kaže da je DOK-01 dostavljen, a odgovor modela kaže da ga nije pročitao.
    Evidencija ostaje serverova i tačna; nema lažnog upozorenja „pominje nedostavljen“. Sistem NE tumači rečenicu
    modela (poznato ograničenje — nesaglasnost se ne označava automatski, oba podatka su vidljiva u V2)."""
    pr, st = ag
    k, _ = pr(_baza7())
    st["odgovor"] = "Nisam pročitao DOK-01 (ugovor.pdf), pa ne mogu da potvrdim rok."
    d = _run(k, "Šta piše u DOK-01?")
    iz = d["izvori_predmeta"]
    assert iz["ukljuceni"][0]["oznaka"] == "DOK-01" and iz["ukljuceni"][0]["trazen"] is True
    assert iz["odgovor_pominje_nedostavljene"] == [] and d["odgovor"] == st["odgovor"]


# Nezavisni pregled F1: naziv bez ekstenzije je obična reč — ne sme da pogodi običnu rečenicu.
@pytest.mark.parametrize("nazivi,odgovor", [
    ({1: "dokument"}, "Priloženi dokument ne pominje rok."),            # rezervni naziv pri prijemu (api.py, smart_intake)
    ({1: "Punomoćje", 2: "Tužba"}, "Punomoćje advokata mora biti overeno. Tužba je blagovremena."),
])
def test_F1_naziv_bez_ekstenzije_ne_pravi_lazno_upozorenje(ag, nazivi, odgovor):
    b = _baza7()
    b["predmet_dokumenti"] = [{**d, "naziv_fajla": nazivi[d["redni_broj"]]} if d["predmet_id"] == PA and d["redni_broj"] in nazivi
                              else d for d in b["predmet_dokumenti"]]
    assert _pominje(ag, odgovor, b)[1] == []
