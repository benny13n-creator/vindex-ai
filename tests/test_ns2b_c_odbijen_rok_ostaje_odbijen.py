# -*- coding: utf-8 -*-
"""NS2B-C (P0) — odbijen rok NIKAD ne postaje potvrdjen obicnom odlukom.

Odluka osnivaca 2026-10-14: zastareo prozor (ili bilo koji obican zahtev za potvrdu) ne sme
odbijen rok uciniti potvrdjenim. Upis u lanac odluka je „procitaj pa upisi" bez uslovnog upisa
u bazi, pa provera pre upisa nije dokaz pod konkurencijom. Zastitu daje izvodjenje stanja koje NE
zavisi od redosleda (`shared.rok_potvrda.odluke`): ijedno odbijanje = REJECTED. Ruta `potvrdi`
dodatno vraca 409 bez upisa kad je rok vec odbijen, i 503 bez upisa kad lanac nije procitan.

Stvarne rute, stvaran `log_action` nad bazom u memoriji (tests/ns005_harness.py). Sinteticki podaci.
"""
import itertools
from datetime import date, timedelta

import pytest

from shared import rokovi as rokovi_domen
from shared.rok_potvrda import (STANJE_NEPOZNATO, STANJE_ODBIJEN, STANJE_POTVRDJEN,
                                odluke, potvrdjeni_ids)
from tests.ns005_harness import ocisti, pripremi, zaglavlje

PA, PB = "pred-A-1", "pred-B-1"
D = lambda n: (date.today() + timedelta(days=n)).isoformat()
P, O = "rok_potvrdjen", "rok_odbijen"
PORUKA_409 = "Rok je već odbijen. Potvrda posle odbijanja nije moguća iz ovog prozora — osvežite stranicu."


def _baza():
    return {
        "predmeti": [{"id": PA, "user_id": "uid-A", "naziv": "Predmet A", "status": "aktivan"},
                     {"id": PB, "user_id": "uid-B", "naziv": "Predmet B", "status": "aktivan"}],
        "predmet_hronologija": [
            {"id": "r-1", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za odgovor na tuzbu",
             "datum_iso": D(4), "vaznost": "visok", "izvor": "AI_EXTRACTED", "vrsta": "rok"},
            {"id": "r-2", "user_id": "uid-A", "predmet_id": PA, "dogadjaj": "Rok za zalbu",
             "datum_iso": D(6), "vaznost": "visok", "izvor": "AI_EXTRACTED", "vrsta": "rok"},
            {"id": "r-B", "user_id": "uid-B", "predmet_id": PB, "dogadjaj": "TAJNI rok B",
             "datum_iso": D(2), "vaznost": "visok", "izvor": "AI_EXTRACTED", "vrsta": "rok"},
        ],
        "audit_immutable": [],
        "events": [],
    }


@pytest.fixture
def ok(monkeypatch):
    rokovi_domen._resetuj_sondu()
    import shared.audit_immutable as audit
    pravi = audit.log_action
    k, b = pripremi(monkeypatch, _baza())
    monkeypatch.setattr(audit, "log_action", pravi)
    yield k, b
    rokovi_domen._resetuj_sondu()
    ocisti()


def _stanja(k, ko="A"):
    r = k.get("/api/rokovi/kandidati", params={"od": D(-5), "dana": 30}, headers=zaglavlje(ko))
    assert r.status_code == 200, r.text
    return {x["id"]: x["stanje_odluke"] for x in r.json()["rokovi"]}


def _odluke_reda(b, rid):
    return [z["action"] for z in b.tabele["audit_immutable"] if z.get("resource_id") == rid]


def _post(k, rid, akcija, ko="A", **telo):
    return k.post(f"/api/rokovi/{rid}/{akcija}", json=telo, headers=zaglavlje(ko))


def _upisi(b, rid, akcija, uid="uid-A"):
    """Upis u lanac MIMO rute (simulira konkurentni zahtev ciji je upis vec prosao proveru)."""
    b.table("audit_immutable").insert({"action": akcija, "resource_type": "rok", "resource_id": rid,
                                       "user_id": uid}).execute()


# (1) A otvori prozor, B (druga sesija istog advokata) odbije, A potvrdi iz zastarelog prozora
def test_1_zastareo_prozor_potvrda_posle_odbijanja_409_bez_upisa(ok):
    k, b = ok
    assert _stanja(k)["r-1"] == "UNCONFIRMED"                 # prozor A je ovo video
    assert _post(k, "r-1", "odbij").status_code == 200        # prozor B
    r = _post(k, "r-1", "potvrdi")                            # prozor A, zastareo
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == PORUKA_409
    assert "stanje_odluke" not in r.json()
    assert _odluke_reda(b, "r-1") == [O]                      # nema upisa potvrde
    assert _stanja(k)["r-1"] == STANJE_ODBIJEN
    assert potvrdjeni_ids(["r-1"]) == set()


# (2) trka: obe odluke stignu u lanac, u bilo kom redosledu → nikad CONFIRMED posle ijednog odbijanja
@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_2_svaki_redosled_sa_odbijanjem_je_REJECTED(ok, n):
    k, b = ok
    for niz in itertools.product((P, O), repeat=n):
        b.tabele["audit_immutable"].clear()
        for a in niz:
            _upisi(b, "r-1", a)
        ocekivano = STANJE_ODBIJEN if O in niz else STANJE_POTVRDJEN
        assert odluke(["r-1"], True) == {"r-1": ocekivano}, niz
        assert _stanja(k)["r-1"] == ocekivano, niz
        assert (potvrdjeni_ids(["r-1"]) == {"r-1"}) is (O not in niz), niz
        assert rokovi_domen.sme_pristupiti({"id": "r-1"}, odluke(["r-1"]),
                                           potrosac=rokovi_domen.POTROSAC_AKCIJA) is (O not in niz), niz


def test_2b_odbijanje_upadne_IZMEDJU_provere_i_upisa_potvrde(ok, monkeypatch):
    """Najgora preplitanja: potvrda je prosla proveru (rok jos nije bio odbijen), pa je odbijanje
    druge sesije upisano, pa je upisana potvrda. Odgovor ne sme tvrditi CONFIRMED; stanje je REJECTED."""
    import routers.rok_odluka as ro
    k, b = ok
    prava = ro.potvrdi_rok

    async def _sa_trkom(rok_id, uid, **kw):
        _upisi(b, rok_id, O)                     # konkurentno odbijanje sleti pre nase potvrde
        return await prava(rok_id, uid, **kw)
    monkeypatch.setattr(ro, "potvrdi_rok", _sa_trkom)
    r = _post(k, "r-1", "potvrdi")
    assert r.status_code == 200, r.text
    assert r.json()["stanje_odluke"] == STANJE_ODBIJEN       # V2 tada ne javlja uspeh i ponovo ucitava
    assert _odluke_reda(b, "r-1") == [O, P]
    assert _stanja(k)["r-1"] == STANJE_ODBIJEN
    assert potvrdjeni_ids(["r-1"]) == set()


def test_2c_izvor_upozorenje_ne_vaskrsava_odbijen_rok(ok):
    """`rok_izvor` cita isti lanac radi vremena potvrde: potvrda posle odbijanja ne sme ga
    tretirati kao potvrdjen (isto pravilo kao `odluke`)."""
    from shared.rok_izvor import izvor_uklonjen_posle_potvrde
    k, b = ok
    _upisi(b, "r-1", O)
    _upisi(b, "r-1", P)
    b.tabele["events"].append({"event_type": "SourceInvalidated", "predmet_id": PA,
                               "created_at": "2999-01-01T00:00:00+00:00", "payload": {"source_type": "dokument"}})
    assert izvor_uklonjen_posle_potvrde([{"id": "r-1", "predmet_id": PA}]) == set()
    b.tabele["audit_immutable"].clear()
    _upisi(b, "r-1", P)                                       # kontrola: potvrdjen rok JESTE upozoren
    assert izvor_uklonjen_posle_potvrde([{"id": "r-1", "predmet_id": PA}]) == {"r-1"}


# (3) ponovljen zahtev posle nepoznatog ishoda
def test_3_dvostruka_potvrda_i_dvostruko_odbijanje(ok):
    k, b = ok
    # NS2B-C F1: ponovljena ista odluka je 200 sa stanjem iz lanca, ali BEZ novog reda
    # (`odluka_zabelezena: False`) — lanac ne raste bez promene stanja.
    for i in range(2):
        r = _post(k, "r-1", "potvrdi")
        assert r.status_code == 200 and r.json()["stanje_odluke"] == STANJE_POTVRDJEN
        assert r.json()["odluka_zabelezena"] is (i == 0)
    for i in range(2):
        r = _post(k, "r-2", "odbij")
        assert r.status_code == 200 and r.json()["stanje_odluke"] == STANJE_ODBIJEN
        assert r.json()["odluka_zabelezena"] is (i == 0)
    assert _odluke_reda(b, "r-1") == [P] and _odluke_reda(b, "r-2") == [O]
    assert potvrdjeni_ids(["r-1", "r-2"]) == {"r-1"}
    # Odbijanje POTVRDJENOG roka i dalje upisuje i gasi; ponovljena potvrda posle toga je 409.
    assert _post(k, "r-1", "odbij").json()["odluka_zabelezena"] is True
    assert _post(k, "r-1", "potvrdi").status_code == 409
    assert _odluke_reda(b, "r-1") == [P, O]


# (4) i (10) drugi korisnik / izolacija kancelarija
def test_4_10_tudj_rok_404_i_kad_je_odbijen_bez_curenja_stanja(ok):
    k, b = ok
    assert _post(k, "r-B", "odbij", ko="B").status_code == 200
    for akcija in ("potvrdi", "odbij"):
        r = _post(k, "r-B", akcija, ko="A")
        assert r.status_code == 404 and "TAJNI" not in r.text and "odbijen" not in r.text
    assert _odluke_reda(b, "r-B") == [O]
    # B ne moze da odbije A-ov rok; A-ov rok ostaje potvrdiv
    assert _post(k, "r-1", "odbij", ko="B").status_code == 404
    assert _odluke_reda(b, "r-1") == []
    assert _post(k, "r-1", "potvrdi").status_code == 200
    assert _stanja(k)["r-1"] == STANJE_POTVRDJEN
    assert "r-1" not in _stanja(k, "B") and _stanja(k, "B")["r-B"] == STANJE_ODBIJEN


# (5) lanac se ne moze procitati pre potvrde → nema uspeha, nema upisa
def test_5_pad_citanja_pre_potvrde_503_bez_upisa(ok, monkeypatch):
    import routers.rok_odluka as ro
    k, b = ok

    def _pada(ids, strogo=False):
        # Kao prava `odluke`: nestrogo citanje pad GUTA i vraca {} („niko nije odlucio") —
        # zato potvrda MORA citati strogo, inace bi neprocitan lanac propustio upis.
        if not strogo:
            return {}
        raise RuntimeError("lanac nedostupan")
    monkeypatch.setattr(ro, "odluke", _pada)
    _upisi(b, "r-1", O)                                       # rok JESTE odbijen, ali se to ne vidi
    r = _post(k, "r-1", "potvrdi")
    assert r.status_code == 503
    assert "stanje_odluke" not in r.json() and "odluka_zabelezena" not in r.json()
    assert _odluke_reda(b, "r-1") == [O]


def test_5b_ceo_lanac_nedostupan_nema_uspeha(ok):
    k, b = ok
    b.greske["audit_immutable"] = Exception('{"code": "57014", "message": "statement timeout"}')
    assert _post(k, "r-1", "potvrdi").status_code == 503
    assert k.get("/api/rokovi/kandidati", params={"od": D(-5)}, headers=zaglavlje("A")).status_code == 503
    del b.greske["audit_immutable"]
    assert b.tabele["audit_immutable"] == []


# (6) upis u lanac pada → nema uspeha, nema lazne poruke o stanju
def test_6_pad_upisa_503_bez_tvrdnje(ok, monkeypatch):
    import shared.audit_immutable as audit
    k, b = ok

    def _upis_pada(*a, **kw):
        raise RuntimeError("insert pao")
    monkeypatch.setattr(audit, "_build_and_insert", _upis_pada)
    for rid, akcija in (("r-1", "potvrdi"), ("r-2", "odbij")):
        r = _post(k, rid, akcija)
        assert r.status_code == 503, r.text
        assert "stanje_odluke" not in r.json() and "odluka_zabelezena" not in r.json()
    assert b.tabele["audit_immutable"] == []
    assert _stanja(k) == {"r-1": "UNCONFIRMED", "r-2": "UNCONFIRMED"}


# (7) potvrdjen pa odbijen → REJECTED (opoziv i dalje radi)
def test_7_potvrda_pa_odbijanje_je_REJECTED(ok):
    k, b = ok
    assert _post(k, "r-1", "potvrdi").json()["stanje_odluke"] == STANJE_POTVRDJEN
    assert potvrdjeni_ids(["r-1"]) == {"r-1"}
    r = _post(k, "r-1", "odbij")
    assert r.status_code == 200 and r.json()["stanje_odluke"] == STANJE_ODBIJEN
    assert potvrdjeni_ids(["r-1"]) == set()
    assert _stanja(k)["r-1"] == STANJE_ODBIJEN


# (8) namerna nova potvrda posle odbijanja (svez prozor, sa napomenom) → i dalje 409
def test_8_namerna_ponovna_potvrda_nije_obicna_odluka(ok):
    k, b = ok
    assert _post(k, "r-1", "odbij").status_code == 200
    assert _stanja(k)["r-1"] == STANJE_ODBIJEN                # svez prikaz: advokat VIDI da je odbijen
    r = _post(k, "r-1", "potvrdi", napomena="Ipak vazi — proverio sam spis")
    assert r.status_code == 409 and r.json()["detail"] == PORUKA_409
    assert _odluke_reda(b, "r-1") == [O]


# (9) UNKNOWN nikad nije CONFIRMED
def test_9_nepoznato_nikad_nije_potvrdjeno(ok, monkeypatch):
    k, b = ok
    _upisi(b, "r-1", P)
    b.greske["audit_immutable"] = Exception("lanac nedostupan")
    assert odluke(["r-1"]) == {}                              # ne-strogo: prazno = niko nije potvrdio
    assert potvrdjeni_ids(["r-1"]) == set()
    with pytest.raises(Exception):
        odluke(["r-1"], True)
    for potrosac in (rokovi_domen.POTROSAC_AKCIJA, rokovi_domen.POTROSAC_KLIJENT,
                     rokovi_domen.POTROSAC_IZVOZ_SPOLJA):
        assert rokovi_domen.sme_pristupiti({"id": "r-1"}, {"r-1": STANJE_NEPOZNATO}, potrosac=potrosac) is False
    del b.greske["audit_immutable"]
    # Posle upisa lanac nije procitan → odgovor kaze UNKNOWN, ne CONFIRMED.
    import routers.rok_odluka as ro
    prava = ro.odluke
    poziv = []

    def _drugi_pada(ids, strogo=False):
        poziv.append(1)
        if strogo and len(poziv) > 1:
            raise RuntimeError("lanac nedostupan")
        return prava(ids, strogo)
    monkeypatch.setattr(ro, "odluke", _drugi_pada)
    r = _post(k, "r-2", "potvrdi")
    assert r.status_code == 200 and r.json()["stanje_odluke"] == STANJE_NEPOZNATO
