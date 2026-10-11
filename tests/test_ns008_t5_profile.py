# -*- coding: utf-8 -*-
"""NS008 Task 5 — izveden profil zatvorenog predmeta (bez nove tabele, bez kopiranja sadržaja)."""
import json

import pytest

import tests.ns008_fake as f8
from services import law_brain as lb

PA = "aaaaaaaa-5555-4000-8000-00000000000a"
PB = "bbbbbbbb-5555-4000-8000-00000000000b"
I1, I2, IB = (f"9{i}aaaaaa-5555-4000-8000-00000000000{i}" for i in range(1, 4))
TAJNA = "Svedok Marko je video isplatu u kešu 3. marta"


def _tabele(n_dodatnih=0):
    predmeti = [
        {"id": PA, "user_id": "uid-A", "naziv": "Petrović protiv ABC", "tip": "radni", "oblast": "radno",
         "status": "zatvoren", "case_dna": {"verzija": 4, "snaga_predmeta_procent": 70}},
        {"id": PB, "user_id": "uid-B", "naziv": "Tajni B", "tip": "radni", "status": "zatvoren", "case_dna": {}},
    ]
    for i in range(n_dodatnih):
        predmeti.append({"id": f"cccccccc-5555-4000-8000-{i:012d}", "user_id": "uid-A", "naziv": f"X{i}",
                         "tip": "radni", "status": "zatvoren", "case_dna": {}})
    return {
        "predmeti": predmeti,
        "outcome_log": [{"id": "o-a", "predmet_id": PA, "user_id": "uid-A", "ishod": "nagodba",
                         "presudni_faktori": ["svedoci"], "updated_at": "2026-09-01T00:00:00+00:00"}],
        "predmet_dokazi": [
            {"predmet_id": PA, "user_id": "uid-A", "kategorija": "svedok", "tvrdnja": TAJNA},
            {"predmet_id": PA, "user_id": "uid-A", "kategorija": "dokaz", "tvrdnja": "Ugovor o radu"},
            {"predmet_id": PA, "user_id": "uid-A", "kategorija": "dokaz", "tvrdnja": "obrisan",
             "deleted_at": "2026-09-01"},
            {"predmet_id": PA, "user_id": "uid-B", "kategorija": "vestacenje", "tvrdnja": "podmetnut"},
        ],
        "rocista": [{"predmet_id": PA, "user_id": "uid-A", "sud": "Osnovni sud u Beogradu", "status": "odrzano"},
                    {"predmet_id": PA, "user_id": "uid-A", "sud": "Osnovni sud u Beogradu", "status": "odrzano"}],
        "predmet_issues": [
            {"id": I1, "predmet_id": PA, "user_id": "uid-A", "status": "CONFIRMED", "label": TAJNA},
            {"id": I2, "predmet_id": PA, "user_id": "uid-A", "status": "MERGED"},
            {"id": IB, "predmet_id": PB, "user_id": "uid-B", "status": "CONFIRMED"},
        ],
        "predmet_contradictions": [
            {"issue_id": I1, "relation_type": "cinjenica_cinjenica", "tezina": "kriticna", "state": "OPEN"},
            {"issue_id": I1, "relation_type": "cinjenica_norma", "tezina": "manja", "state": "RESOLVED"},
            {"issue_id": IB, "relation_type": "cinjenica_norma", "tezina": "kriticna", "state": "OPEN"},
        ],
        "staging_memory": [
            {"id": "s-ok", "user_id": "uid-A", "predmet_id": PA, "tip": "tuzba", "naziv": "Tužba", "tekst": "t",
             "confidence_score": 0.9, "is_lawyer_approved": True, "approved_at": "2026-08-01T00:00:00+00:00",
             "status": "approved", "pinecone_indexed": True},
            {"id": "s-ai", "user_id": "uid-A", "predmet_id": PA, "tip": "zalba", "naziv": "Žalba", "tekst": "t",
             "confidence_score": 0.99, "is_lawyer_approved": False, "status": "pending", "pinecone_indexed": False},
        ],
    }


@pytest.fixture
def baza(monkeypatch):
    _, b = f8.pripremi(monkeypatch, _tabele())
    yield b
    f8.ocisti()


def _pa(baza):
    return next(p for p in baza.tabele["predmeti"] if p["id"] == PA)


def test_profil_razdvaja_izvore(baza):
    p = lb.ucitaj_profile(baza, [_pa(baza)])[PA]
    assert p["terminalan"] is True
    c = p["cinjenice"]
    assert c["trust_class"] == lb.SOURCE_CASE_FACT
    assert (c["tip"], c["oblast"], c["sudovi"]) == ("radni", "radno", ["Osnovni sud u Beogradu"])
    assert c["dokazi_po_kategoriji"] == {"dokaz": 1, "svedok": 1}, "obrisan i tuđ dokaz se ne broje"
    assert p["ljudski_ishod"]["status"] == lb.OUTCOME_RECORDED and p["ljudski_ishod"]["ishod"] == "nagodba"
    assert p["ljudski_ishod"]["item"]["trust_class"] == lb.HUMAN_CONFIRMED_OUTCOME
    ai = p["ai_analiza"]
    assert ai["trust_class"] == lb.AI_WORK_PRODUCT and ai["genome_verzija"] == 4
    assert ai["pravna_pitanja_po_statusu"] == {"CONFIRMED": 1}, "spojena tema nije živa"
    assert ai["kontradikcije_po_vrsti"] == {"cinjenica_cinjenica": 1}, "razrešena i tuđa se ne broje"
    assert [a["source_ref"]["id"] for a in p["overeni_artefakti"]] == ["s-ok"], "AI nacrt na čekanju nije overen"
    assert p["nepoznato"] == []
    assert p["poreklo"] == {"derivation_version": lb.PROFILE_DERIVATION, "genome_verzija": 4,
                            "outcome_ref": "o-a", "outcome_updated_at": "2026-09-01T00:00:00+00:00"}


def test_profil_ne_kopira_sadrzaj(baza):
    tekst = json.dumps(lb.ucitaj_profile(baza, [_pa(baza)]), ensure_ascii=False)
    assert TAJNA not in tekst and "Ugovor o radu" not in tekst
    assert "snaga_predmeta_procent" not in tekst and "70" not in tekst.replace("2026", "")


def test_bez_ishoda_i_genoma_je_nepoznato():
    p = lb.matter_profile({"id": PA, "user_id": "uid-A", "status": "zatvoren"}, ishod_red=None, dokazi=[],
                          rocista=[], issues=[], kontradikcije=[], artefakti=[])
    assert p["ljudski_ishod"]["status"] == lb.OUTCOME_UNKNOWN
    assert p["nepoznato"] == ["genome", "ishod", "oblast", "sud", "tip"]
    assert p["poreklo"]["outcome_ref"] is None


def test_deterministicki(baza):
    a = lb.ucitaj_profile(baza, [_pa(baza)])
    b = lb.ucitaj_profile(baza, [_pa(baza)])
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_broj_upita_ne_raste_sa_brojem_predmeta(monkeypatch):
    _, b = f8.pripremi(monkeypatch, _tabele(n_dodatnih=60))
    try:
        svoji = [p for p in b.tabele["predmeti"] if p["user_id"] == "uid-A"]
        b.dnevnik.clear()
        lb.ucitaj_profile(b, svoji[:1])
        jedan = len(b.dnevnik)
        b.dnevnik.clear()
        profili = lb.ucitaj_profile(b, svoji)
        assert len(profili) == 61
        assert len(b.dnevnik) == jedan == 6
    finally:
        f8.ocisti()


def test_greska_izvora_se_propusta(baza):
    baza.greske["predmet_dokazi"] = Exception("down")
    with pytest.raises(Exception):
        lb.ucitaj_profile(baza, [_pa(baza)])
