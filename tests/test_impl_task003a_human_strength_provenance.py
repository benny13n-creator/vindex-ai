"""IMPLEMENTATION TASK 003A — HUMAN STRENGTH PROVENANCE REPAIR.

Gate 005 je dokazao da `DokazReq.snaga: str = "srednja"` pretvara ODSUSTVO
korisnikove odluke u `izvor_odluke='covek'` -- lažnu tvrdnju da je advokat
procenio dokaznu snagu.

Ovi testovi mere STVARNI ulazni put (HTTP → Pydantic → ruta → primitiv), a ne
samo primitiv. To je bio `SEMANTIC COVERAGE GAP` iz Gate 005 §14: postojećih
36 poziva primitiva u `tests/` preskaču tačno onu liniju na kojoj se semantika
gubila, pa nijedan od njih ovaj kvar nije mogao da vidi.

Centralna tvrdnja (§10 mandata):
    POST {"tvrdnja": "X"}  NE SME dati  izvor_odluke = "covek".
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
from shared.evidence_write import odredi_snagu  # noqa: E402

PREDMET = "11111111-1111-1111-1111-111111111111"
DOKUMENT = "22222222-2222-2222-2222-222222222222"
KORISNIK = {"user_id": "33333333-3333-3333-3333-333333333333", "email": "a@b.c"}

# Dovoljno duga (>= 20, <= 100) da `snaga_iz_lokacije` sme da vrati "jaka".
TVRDNJA = "Tuženi je dana 15.03.2026. godine primio opomenu pred utuženje"
TEKST = "Zapisnik. " + TVRDNJA + " i nije postupio po njoj u roku."


class _Supa:
    """Minimalan dvojnik: predmet postoji, dokument nosi tekst, insert prolazi."""

    def __init__(self, tekst_dokumenta=None):
        self.tekst = tekst_dokumenta
        self.upisano = []

    def table(self, ime):
        return _Q(self, ime)


class _Q:
    def __init__(self, supa, ime):
        self.supa, self.ime, self._red = supa, ime, None

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def insert(self, redovi):
        self._red = redovi
        return self

    def execute(self):
        if self._red is not None:
            self.supa.upisano.extend(self._red)
            return MagicMock(data=[dict(r, id="dokaz-1") for r in self._red])
        if self.ime == "predmeti":
            return MagicMock(data=[{"id": PREDMET}])
        if self.ime == "predmet_dokumenti":
            return MagicMock(data=[{"id": DOKUMENT, "tekst_sadrzaj": self.supa.tekst}])
        return MagicMock(data=[])


def _post(telo, tekst_dokumenta=None):
    """Pravi HTTP POST kroz Pydantic validaciju i celu rutu."""
    supa = _Supa(tekst_dokumenta)
    api.app.dependency_overrides[get_current_user] = lambda: KORISNIK
    try:
        with patch.object(ev, "get_supa", return_value=supa):
            k = TestClient(api.app, raise_server_exceptions=False)
            r = k.post("/api/evidence/predmeti/%s/dokaz" % PREDMET, json=telo)
        return r, supa
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)


# ═══════════════════════════════════════════════════════════════════════════
# M8 — STVARNI HTTP PUT (obavezno; zatvara SEMANTIC COVERAGE GAP)
# ═══════════════════════════════════════════════════════════════════════════

def test_m8_http_bez_snage_ne_sme_dati_covek():
    """CENTRALNA TVRDNJA TASK-a 003A.

    Pre popravke ovaj isti zahtev je vraćao `snaga_izvor='covek'` jer je
    Pydantic default popunjavao polje na serveru."""
    r, supa = _post({"tvrdnja": TVRDNJA})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["snaga_izvor"] != "covek"
    assert d["snaga_izvor"] == "podrazumevano"
    assert d["snaga"] == "srednja"          # vrednost ostaje ista...
    assert supa.upisano[0]["snaga"] == "srednja"   # ...i u bazi


def test_m8_http_sa_eksplicitnom_snagom_daje_covek():
    r, _ = _post({"tvrdnja": TVRDNJA, "snaga": "jaka"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["snaga_izvor"] == "covek"
    assert d["snaga"] == "jaka"


def test_m8_http_absent_i_explicit_daju_RAZLICIT_provenance():
    """Jedan test koji drži celu razliku: ista ruta, dva tela, dva ishoda."""
    r_bez, _ = _post({"tvrdnja": TVRDNJA})
    r_sa, _ = _post({"tvrdnja": TVRDNJA, "snaga": "srednja"})
    assert r_bez.json()["snaga"] == r_sa.json()["snaga"] == "srednja"
    assert r_bez.json()["snaga_izvor"] != r_sa.json()["snaga_izvor"]
    assert (r_bez.json()["snaga_izvor"], r_sa.json()["snaga_izvor"]) == ("podrazumevano", "covek")


# ═══════════════════════════════════════════════════════════════════════════
# M1–M5 — ulazni ugovor
# ═══════════════════════════════════════════════════════════════════════════

def test_m1_absent_polje_nije_u_fields_set_i_vrednost_je_none():
    req = ev.DokazReq(tvrdnja=TVRDNJA)
    assert req.model_fields_set == {"tvrdnja"}
    assert req.snaga is None
    # human provenance == FALSE
    assert odredi_snagu(TVRDNJA, {"start_offset": None},
                        izvor_dostupan=False, snaga_tvrdi_covek=None)[1] == "podrazumevano"


def test_m2_explicit_slaba():
    req = ev.DokazReq(tvrdnja=TVRDNJA, snaga="slaba")
    assert "snaga" in req.model_fields_set
    assert req.snaga == "slaba"
    r, _ = _post({"tvrdnja": TVRDNJA, "snaga": "slaba"})
    assert r.json()["snaga_izvor"] == "covek"
    assert r.json()["snaga"] == "slaba"


def test_m3_explicit_srednja_ostaje_razlicito_od_absent():
    """ABSENT != EXPLICIT "srednja" -- iako je vrednost identična."""
    req_a = ev.DokazReq(tvrdnja=TVRDNJA)
    req_b = ev.DokazReq(tvrdnja=TVRDNJA, snaga="srednja")
    assert req_a.snaga is None and req_b.snaga == "srednja"
    assert ("snaga" in req_a.model_fields_set) is False
    assert ("snaga" in req_b.model_fields_set) is True


def test_m4_explicit_jaka():
    r, _ = _post({"tvrdnja": TVRDNJA, "snaga": "jaka"})
    assert r.json()["snaga_izvor"] == "covek"


def test_m5_nevazeca_vrednost_se_i_dalje_odbija():
    """Dozvoljene vrednosti se NE šire ovim taskom."""
    r, supa = _post({"tvrdnja": TVRDNJA, "snaga": "ZZZ"})
    assert r.status_code == 400
    assert supa.upisano == []


# ═══════════════════════════════════════════════════════════════════════════
# M6 — DC-005 precedence mora ostati netaknut
# ═══════════════════════════════════════════════════════════════════════════

def test_m6_dc005_precedence_nepromenjen_bez_poslate_snage():
    r, _ = _post({"tvrdnja": TVRDNJA, "dokument_id": DOKUMENT}, tekst_dokumenta=TEKST)
    assert r.status_code == 200, r.text
    assert r.json()["snaga_izvor"] == "dc005"
    assert r.json()["snaga"] == "jaka"


def test_m6b_dc005_pregazi_eksplicitnu_ljudsku_vrednost():
    """Postojeće pravilo: kad izvor postoji, DC-005 je merodavan i to se
    prijavljuje kroz `snaga_prepisana`, nikad tiho."""
    r, _ = _post({"tvrdnja": TVRDNJA, "snaga": "slaba", "dokument_id": DOKUMENT},
                 tekst_dokumenta=TEKST)
    assert r.json()["snaga_izvor"] == "dc005"
    assert r.json()["snaga"] == "jaka"
    assert r.json()["snaga_prepisana"] is True


# ═══════════════════════════════════════════════════════════════════════════
# M7 — primitiv ostaje kompatibilan (ugovor se NE menja)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("covek,ocekivano", [
    (None,      "podrazumevano"),
    ("jaka",    "covek"),
    ("srednja", "covek"),
    ("slaba",   "covek"),
])
def test_m7_primitiv_ugovor_nepromenjen(covek, ocekivano):
    assert odredi_snagu(TVRDNJA, {"start_offset": None},
                        izvor_dostupan=False, snaga_tvrdi_covek=covek)[1] == ocekivano


def test_m7b_primitiv_default_ostaje_none():
    """`Optional[str] = None` u primitivu je ono što čuva `ABSENT`; ne dira se."""
    import inspect
    for fn in ("odredi_snagu", "upisi_dokaz"):
        import shared.evidence_write as ew
        p = inspect.signature(getattr(ew, fn)).parameters
        ime = "snaga_tvrdi_covek" if fn == "odredi_snagu" else "snaga"
        assert p[ime].default is None


# ═══════════════════════════════════════════════════════════════════════════
# TRIPWIRE — schema regresija puca glasno umesto da fabrikuje `covek`
# ═══════════════════════════════════════════════════════════════════════════

def test_tripwire_vrednost_bez_eksplicitnog_unosa_puca_a_ne_laze():
    """Ako se `snaga: str = "srednja"` ikada vrati, ruta mora pući, a ne tiho
    zabeležiti ljudsku procenu. Simulira se objektom čiji `model_fields_set`
    ne sadrži `snaga` iako vrednost postoji."""
    supa = _Supa()
    api.app.dependency_overrides[get_current_user] = lambda: KORISNIK
    try:
        with patch.object(ev, "get_supa", return_value=supa):
            lazni = ev.DokazReq(tvrdnja=TVRDNJA)
            object.__setattr__(lazni, "snaga", "srednja")   # vrednost bez unosa
            assert "snaga" not in lazni.model_fields_set
            import asyncio
            from shared.http_errors import NamerniHTTPException
            with pytest.raises(NamerniHTTPException):
                asyncio.run(ev.add_dokaz.__wrapped__(
                    MagicMock(), PREDMET, lazni, user=KORISNIK))
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)
    assert supa.upisano == []
