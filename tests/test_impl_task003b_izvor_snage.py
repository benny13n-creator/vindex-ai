"""IMPL TASK 003B — EVIDENCE ASSESSMENT COVERAGE / PROVENANCE PERSISTENCE.

Perzistira se JEDNA prethodno implicitna činjenica: da li je snaga dokaza
uopšte procenjena. Do sada se `izvor_odluke` računao u `odredi_snagu` i bacao
pre upisa, pa se iz baze nije moglo dokazati da li je iko odlučio.

Testovi prolaze kroz STVARNI HTTP seam (`TestClient` → Pydantic → ruta →
primitiv), jer se ljudska provenijencija utvrđuje tačno na toj granici
(TASK 003A). Negativni testovi drže granicu: nijedan pojedinačni signal
(`snaga`, `nacin_pronalaska`, `start_offset`) ne sme značiti „procenjeno".
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api  # noqa: E402
import routers.evidence as ev  # noqa: E402
from shared.deps import get_current_user  # noqa: E402
from shared.evidence_write import (  # noqa: E402
    IZVOR_COVEK, IZVOR_DC005, IZVOR_PODRAZUMEVANO, IZVORI, IZVORI_PROCENJENO,
    KOLONA_IZVOR_SNAGE, POKRIVENOST_DELIMICNO, POKRIVENOST_NEMA_TVRDNJI,
    POKRIVENOST_NEPROCENJENO, POKRIVENOST_PROCENJENO,
    izvor_snage_iz_odluke, pokrivenost_procene,
)

PREDMET = "11111111-1111-1111-1111-111111111111"
DOKUMENT = "22222222-2222-2222-2222-222222222222"
KORISNIK = {"user_id": "33333333-3333-3333-3333-333333333333", "email": "a@b.c"}

TVRDNJA = "Tuženi je dana 15.03.2026. godine primio opomenu pred utuženje"
TEKST = "Zapisnik. " + TVRDNJA + " i nije postupio po njoj u roku."
NEMA_U_TEKSTU = "Tužilac je isporučio robu 01.01.2020. po ugovoru broj 5555"


class _Supa:
    def __init__(self, tekst=None, kolona_postoji=True):
        self.tekst, self.kolona_postoji = tekst, kolona_postoji
        self.upisano, self.pokusaji = [], []

    def table(self, ime):
        return _Q(self, ime)


class _Q:
    def __init__(self, supa, ime):
        self.supa, self.ime, self._red = supa, ime, None

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self

    def insert(self, redovi):
        self._red = redovi
        return self

    def execute(self):
        if self._red is not None:
            self.supa.pokusaji.append(self._red)
            if not self.supa.kolona_postoji and any(KOLONA_IZVOR_SNAGE in r for r in self._red):
                raise Exception('column predmet_dokazi.izvor_snage does not exist')
            self.supa.upisano.extend(self._red)
            return MagicMock(data=[dict(r, id="dokaz-1") for r in self._red])
        if self.ime == "predmeti":
            return MagicMock(data=[{"id": PREDMET}])
        if self.ime == "predmet_dokumenti":
            return MagicMock(data=[{"id": DOKUMENT, "tekst_sadrzaj": self.supa.tekst}])
        return MagicMock(data=[])


def _post(telo, tekst=None, kolona_postoji=True):
    supa = _Supa(tekst, kolona_postoji)
    api.app.dependency_overrides[get_current_user] = lambda: KORISNIK
    try:
        with patch.object(ev, "get_supa", return_value=supa):
            k = TestClient(api.app, raise_server_exceptions=False)
            r = k.post("/api/evidence/predmeti/%s/dokaz" % PREDMET, json=telo)
        return r, supa
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)


def _red(supa):
    assert supa.upisano, "ništa nije upisano"
    return supa.upisano[0]


# ═══════════════════════════════════════════════════════════════════════════
# §12.1-5 — PERZISTIRANA PROVENIJENCIJA, kroz stvarni HTTP put
# ═══════════════════════════════════════════════════════════════════════════

def test_t1_absent_snaga_daje_podrazumevano():
    r, supa = _post({"tvrdnja": TVRDNJA})
    assert r.status_code == 200, r.text
    assert _red(supa)["snaga"] == "srednja"
    assert _red(supa)[KOLONA_IZVOR_SNAGE] == IZVOR_PODRAZUMEVANO


def test_t2_explicit_srednja_daje_covek():
    """Ista `snaga` kao t1, RAZLIČITA provenijencija — to je cela poenta."""
    r, supa = _post({"tvrdnja": TVRDNJA, "snaga": "srednja"})
    assert _red(supa)["snaga"] == "srednja"
    assert _red(supa)[KOLONA_IZVOR_SNAGE] == IZVOR_COVEK


def test_t3_explicit_jaka_daje_covek():
    _, supa = _post({"tvrdnja": TVRDNJA, "snaga": "jaka"})
    assert _red(supa)[KOLONA_IZVOR_SNAGE] == IZVOR_COVEK


def test_t4_dc005_nadjeno_daje_dc005():
    _, supa = _post({"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}, tekst=TEKST)
    red = _red(supa)
    assert red["snaga"] == "jaka"
    assert red["nacin_pronalaska"] == "egzaktan"
    assert red[KOLONA_IZVOR_SNAGE] == IZVOR_DC005


def test_t5_dc005_NIJE_naslo_daje_podrazumevano_a_ne_dc005():
    """Najvažniji red ovog taska: „pretražio sam i nisam našao" NIJE procena."""
    _, supa = _post({"tvrdnja": NEMA_U_TEKSTU, "dokument_id": DOKUMENT}, tekst=TEKST)
    red = _red(supa)
    assert red["snaga"] == "srednja"
    assert red["nacin_pronalaska"] == "nije_pronadjen"
    assert red[KOLONA_IZVOR_SNAGE] == IZVOR_PODRAZUMEVANO
    assert red[KOLONA_IZVOR_SNAGE] != IZVOR_DC005


def test_t5b_dc005_nadjeno_ali_prekratka_tvrdnja_je_podrazumevano():
    """Nađeno egzaktno, ali `snaga_iz_lokacije` odbija da opravda `jaka`
    (dužina < 20). Nalaz postoji, procena ne postoji."""
    kratka = "Tuženi je"
    _, supa = _post({"tvrdnja": kratka, "dokument_id": DOKUMENT}, tekst=TEKST)
    red = _red(supa)
    assert red["nacin_pronalaska"] == "egzaktan"
    assert red["snaga"] == "srednja"
    assert red[KOLONA_IZVOR_SNAGE] == IZVOR_PODRAZUMEVANO


def test_t5c_dc005_pregazi_coveka_i_provenijencija_prati_dc005():
    _, supa = _post({"tvrdnja": TVRDNJA, "snaga": "slaba", "dokument_id": DOKUMENT}, tekst=TEKST)
    assert _red(supa)[KOLONA_IZVOR_SNAGE] == IZVOR_DC005


# ═══════════════════════════════════════════════════════════════════════════
# §12 NEGATIVNI SLUČAJEVI — nijedan pojedinačni signal ne znači „procenjeno"
# ═══════════════════════════════════════════════════════════════════════════

def test_neg1_snaga_srednja_sama_ne_znaci_procenjeno():
    redovi = [{"snaga": "srednja", KOLONA_IZVOR_SNAGE: IZVOR_PODRAZUMEVANO}]
    assert pokrivenost_procene(redovi)["broj_procenjenih"] == 0


def test_neg2_snaga_jaka_sama_ne_znaci_procenjeno():
    """Legacy red sa `jaka` i BEZ provenijencije ostaje NEPROCENJEN."""
    redovi = [{"snaga": "jaka", KOLONA_IZVOR_SNAGE: None}]
    p = pokrivenost_procene(redovi)
    assert p["broj_procenjenih"] == 0
    assert p["status"] == POKRIVENOST_NEPROCENJENO


def test_neg3_nacin_egzaktan_sam_ne_znaci_procenjeno():
    redovi = [{"snaga": "srednja", "nacin_pronalaska": "egzaktan",
               KOLONA_IZVOR_SNAGE: IZVOR_PODRAZUMEVANO}]
    assert pokrivenost_procene(redovi)["broj_procenjenih"] == 0


def test_neg4_start_offset_sam_ne_znaci_procenjeno():
    redovi = [{"snaga": "srednja", "start_offset": 42, "end_offset": 99,
               KOLONA_IZVOR_SNAGE: IZVOR_PODRAZUMEVANO}]
    assert pokrivenost_procene(redovi)["broj_procenjenih"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# §12.6-10 + §8 — DERIVACIJA POKRIVENOSTI
# ═══════════════════════════════════════════════════════════════════════════

P = {KOLONA_IZVOR_SNAGE: IZVOR_PODRAZUMEVANO}
C = {KOLONA_IZVOR_SNAGE: IZVOR_COVEK}
D = {KOLONA_IZVOR_SNAGE: IZVOR_DC005}
L = {KOLONA_IZVOR_SNAGE: None}          # legacy
X = {}                                   # kolona uopšte ne postoji u redu


@pytest.mark.parametrize("redovi,status,proc,ukupno", [
    ([],                 POKRIVENOST_NEMA_TVRDNJI,  0, 0),
    ([P],                POKRIVENOST_NEPROCENJENO,  0, 1),
    ([P, P, P],          POKRIVENOST_NEPROCENJENO,  0, 3),
    ([L],                POKRIVENOST_NEPROCENJENO,  0, 1),
    ([L, L, L],          POKRIVENOST_NEPROCENJENO,  0, 3),
    ([X],                POKRIVENOST_NEPROCENJENO,  0, 1),
    ([C],                POKRIVENOST_PROCENJENO,    1, 1),
    ([D],                POKRIVENOST_PROCENJENO,    1, 1),
    ([C, D],             POKRIVENOST_PROCENJENO,    2, 2),
    ([C, P],             POKRIVENOST_DELIMICNO,     1, 2),
    ([D, L],             POKRIVENOST_DELIMICNO,     1, 2),
    ([C] + [P] * 99,     POKRIVENOST_DELIMICNO,     1, 100),
    ([C, D, P, L],       POKRIVENOST_DELIMICNO,     2, 4),
])
def test_pokrivenost_matrica(redovi, status, proc, ukupno):
    p = pokrivenost_procene(redovi)
    assert p["status"] == status
    assert p["broj_procenjenih"] == proc
    assert p["broj_tvrdnji"] == ukupno
    assert p["broj_neprocenjenih"] == ukupno - proc


def test_pokrivenost_ne_gleda_snagu_uopste():
    """Isti `izvor_snage`, sve tri vrednosti `snaga` — identičan rezultat."""
    a = pokrivenost_procene([dict(P, snaga="jaka"), dict(P, snaga="slaba")])
    b = pokrivenost_procene([dict(P, snaga="srednja"), dict(P, snaga="srednja")])
    assert a == b == {"status": POKRIVENOST_NEPROCENJENO, "broj_tvrdnji": 2,
                      "broj_procenjenih": 0, "broj_neprocenjenih": 2}


# ═══════════════════════════════════════════════════════════════════════════
# MAPIRANJE — čista funkcija, iscrpno
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("izvor_odluke,snaga,ocekivano", [
    ("covek",         "jaka",    IZVOR_COVEK),
    ("covek",         "srednja", IZVOR_COVEK),
    ("covek",         "slaba",   IZVOR_COVEK),
    ("dc005",         "jaka",    IZVOR_DC005),
    ("dc005",         "srednja", IZVOR_PODRAZUMEVANO),
    ("podrazumevano", "srednja", IZVOR_PODRAZUMEVANO),
])
def test_mapiranje_izvora(izvor_odluke, snaga, ocekivano):
    assert izvor_snage_iz_odluke(izvor_odluke, snaga) == ocekivano


def test_vokabular_je_zatvoren():
    assert IZVORI == {IZVOR_COVEK, IZVOR_DC005, IZVOR_PODRAZUMEVANO}
    assert IZVORI_PROCENJENO == {IZVOR_COVEK, IZVOR_DC005}
    assert IZVOR_PODRAZUMEVANO not in IZVORI_PROCENJENO
    assert None not in IZVORI_PROCENJENO


# ═══════════════════════════════════════════════════════════════════════════
# §7 — FALLBACK: kolona ne postoji (migracija 118 nije pokrenuta)
# ═══════════════════════════════════════════════════════════════════════════

def test_fallback_bez_kolone_upis_prezivljava_i_ostala_polja_ostaju(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        r, supa = _post({"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT},
                        tekst=TEKST, kolona_postoji=False)
    assert r.status_code == 200, r.text
    red = _red(supa)
    # `izvor_snage` je izostavljen...
    assert KOLONA_IZVOR_SNAGE not in red
    # ...ali NIJEDNO drugo polje nije izgubljeno ni izmišljeno
    assert red["identitet"] and red["nacin_pronalaska"] == "egzaktan"
    assert red["start_offset"] is not None and red["snaga"] == "jaka"
    assert red["tvrdnja"] == TVRDNJA
    # i degradacija je prijavljena glasno
    assert any("118" in m for m in caplog.messages), caplog.messages


def test_fallback_degradira_tacno_jedan_stepen():
    """Kad fali SAMO `izvor_snage`, ne sme se odbaciti ništa drugo."""
    _, supa = _post({"tvrdnja": TVRDNJA}, kolona_postoji=False)
    assert len(supa.pokusaji) == 2, supa.pokusaji
    assert KOLONA_IZVOR_SNAGE in supa.pokusaji[0][0]
    assert KOLONA_IZVOR_SNAGE not in supa.pokusaji[1][0]
    assert "identitet" in supa.pokusaji[1][0]
    assert "nacin_pronalaska" in supa.pokusaji[1][0]


def test_fallback_redovi_bez_kolone_broje_se_kao_neprocenjeni():
    """Fail-closed spoj: degradirani upis + derivacija = NEPROCENJENO."""
    _, supa = _post({"tvrdnja": TVRDNJA, "snaga": "jaka"}, kolona_postoji=False)
    assert pokrivenost_procene(supa.upisano)["status"] == POKRIVENOST_NEPROCENJENO


# ═══════════════════════════════════════════════════════════════════════════
# §4/§10 — GRANICE: ništa izvan provenijencije nije dirnuto
# ═══════════════════════════════════════════════════════════════════════════

def test_snaga_vokabular_i_health_netaknuti():
    from shared.evidence_write import SNAGE, SNAGA_PODRAZUMEVANA, snaga_iz_lokacije
    assert SNAGE == {"jaka", "srednja", "slaba"}
    assert "nepoznato" not in SNAGE
    assert SNAGA_PODRAZUMEVANA == "srednja"
    # `snaga_iz_lokacije` i dalje daje isključivo {jaka, srednja}
    izlazi = {snaga_iz_lokacije("x" * 30, {"start_offset": None}),
              snaga_iz_lokacije("x" * 30, {"start_offset": 0}),
              snaga_iz_lokacije("x" * 5, {"start_offset": 0}),
              snaga_iz_lokacije("x" * 200, {"start_offset": 0})}
    assert izlazi == {"jaka", "srednja"}


def test_health_aritmetika_ne_cita_brojace_pokrivenosti():
    """TASK 004A — usklađeno sa TASK 004, ne oslabljeno.

    STARO (TASK 003B): `assert "izvor_snage" not in inspect.getsource(risk_engine)`.
    To je bio zapis GRANICE OPSEGA taska 003B („coverage se uvodi, ali se
    potrošači još ne diraju"), a ne trajni invarijant. TASK 004 je tu granicu
    po mandatu prešao: `risk_engine` sada MORA koristiti provenance da bi
    strength računao samo nad procenjenim tvrdnjama.

    NOVO: preživeli deo tvrdnje — `health` aritmetika i dalje ne čita brojače
    pokrivenosti. `health` zavisi od labela, praznog imenioca, nedostajućih
    dokumenata i rokova; `broj_tvrdnji`/`broj_procenjenih` su izlazni podaci,
    ne ulazi u formulu."""
    import inspect
    from services.risk_engine import calculate_procesni_rizik
    from shared.constants import EXPECTED_DOCS

    telo = inspect.getsource(calculate_procesni_rizik)
    aritmetika = telo[telo.index("rizik_score = 50"):telo.index("health = 100 - rizik_score")]
    for zabranjeno in ("broj_tvrdnji", "broj_procenjenih", "pokrivenost["):
        assert zabranjeno not in aritmetika, zabranjeno

    # Isti procenjeni skup + proizvoljno mnogo NEPROCENJENIH tvrdnji -> isti health.
    A = {"snaga": "jaka", KOLONA_IZVOR_SNAGE: IZVOR_COVEK}
    N = {"snaga": "srednja", KOLONA_IZVOR_SNAGE: IZVOR_PODRAZUMEVANO}
    def h(d):
        return calculate_procesni_rizik(dokazi=d, dokumenti=[], rocista=[],
                                        tip_predmeta="ostalo", expected_docs=EXPECTED_DOCS)["health_score"]
    assert h([A]) == h([A] + [N] * 50) == h([A] + [N] * 500)
