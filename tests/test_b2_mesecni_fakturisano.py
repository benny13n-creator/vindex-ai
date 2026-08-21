# -*- coding: utf-8 -*-
"""B2-MESECNI-001 — `fakturisano_rsd` sme da dolazi ISKLJUČIVO iz faktura.

DOKAZANI KVAR (produkcija `15302e0`, mereno uživo):

    tenant sa 3 stavke rada: 1.000 + 2.500 + 500 = 4.000 RSD
    tenant sa 0 faktura

    GET /billing/report/mesecni  ->  fakturisano_rsd = 4000
                                     neplaceno_rsd   = 4000

Advokatu je prikazano da mu klijent duguje 4.000 RSD za nešto što mu **nikad
nije fakturisano**. Uzrok, `routers/billing_reports.py:649`:

    fakturisano = sum(float(e.get("iznos_rsd") or 0) for e in entries)

`entries` je `billing_entries` — NEOBRAČUNAT rad. Isti fajl, linija 181, radi to
ispravno za godišnji izveštaj: `sum(... for f in fakture)`.

TRI POJMA KOJI SE NE SMEJU MEŠATI:

    rad        `billing_entries.iznos_rsd`     — uneseno, još nefakturisano
    fakturisan `fakture.iznos_sa_pdv`          — izdato klijentu
    naplaćen   `fakture` sa `status='placena'` — stvarno naplaćeno

Dvojnik ispod NAMERNO primenjuje `gte`/`lte` nad pravom kolonom datuma i beleži
`eq("user_id", …)`, jer se bez toga period i tenant izolacija ne mogu meriti.
"""
import os
import sys
from datetime import date

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402
import api  # noqa: E402
import routers.billing_reports as br  # noqa: E402
from shared.deps import get_current_user  # noqa: E402

UID = "11111111-1111-4111-8111-111111111111"
KORISNIK = {"user_id": UID, "email": "b2@example.invalid", "is_pro": True}

DANAS = date.today()
OVAJ = DANAS.replace(day=15).isoformat()
PROSLI = (DANAS.replace(day=1) - __import__("datetime").timedelta(days=10)).isoformat()

# Kolona datuma po tabeli — dvojnik po njoj stvarno filtrira period.
DATUM_KOLONA = {
    "rocista": "datum",
    "billing_entries": "datum",
    "fakture": "datum_fakture",
    "predmet_hronologija": "datum_iso",
}


class _Supa:
    def __init__(self, redovi, pada=None):
        self.redovi = redovi
        self.pada = pada or set()
        self.scoping = []          # (tabela, kolona, vrednost) za `eq`

    def table(self, ime):
        spolja = self

        class _Q:
            def __init__(self):
                self.t = ime
                self.gte = None
                self.lte = None

            def select(self, *a, **k):
                if ime in spolja.pada:
                    raise RuntimeError("simuliran ispad izvora '%s'" % ime)
                return self

            def eq(self, k, v):
                spolja.scoping.append((ime, k, v))
                return self

            def gte(self, k, v):                      # noqa: F811
                self.gte = (k, v); return self

            def lte(self, k, v):                      # noqa: F811
                self.lte = (k, v); return self

            def lt(self, k, v):
                self.lte = (k, v); return self

            def order(self, *a, **k):
                return self

            def execute(self):
                red = list(spolja.redovi.get(ime, []))
                kol = DATUM_KOLONA.get(ime)
                if kol:
                    if self.gte:
                        red = [r for r in red if str(r.get(kol, "")) >= self.gte[1]]
                    if self.lte:
                        red = [r for r in red if str(r.get(kol, "")) <= self.lte[1]]
                return MagicMock(data=red)

        q = _Q()
        # `gte`/`lte` su i atributi i metode — razrešava se preko instance
        q.gte = _Q.gte.__get__(q)
        q.lte = _Q.lte.__get__(q)
        return q


def _pozovi(redovi, pada=None):
    supa = _Supa(redovi, pada)
    api.app.dependency_overrides[get_current_user] = lambda: KORISNIK
    try:
        with patch.object(br, "_get_supa", return_value=supa):
            k = TestClient(api.app, raise_server_exceptions=False)
            r = k.get("/billing/report/mesecni")
        return r, supa
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)


def _rad(*iznosi, datum=None):
    return [{"id": "e%d" % i, "iznos_rsd": v, "obracunato": False,
             "datum": datum or OVAJ}
            for i, v in enumerate(iznosi, 1)]


def _faktura(iznos, status="izdata", datum=None):
    return {"id": "f-%s-%s" % (iznos, status), "iznos_sa_pdv": iznos,
            "status": status, "datum_fakture": datum or OVAJ}


def _osnova(**kw):
    baza = {"predmeti": [], "rocista": [], "billing_entries": [],
            "fakture": [], "predmet_hronologija": []}
    baza.update(kw)
    return baza


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1 — NEFAKTURISAN RAD NIJE PRIHOD  (jezgro B2-MESECNI-001)
# ═══════════════════════════════════════════════════════════════════════════

def test_1_rad_bez_fakture_ne_sme_biti_fakturisan():
    r, _ = _pozovi(_osnova(billing_entries=_rad(1000.0, 2500.0, 500.0), fakture=[]))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["fakturisano_rsd"] == 0, (
        "4.000 RSD nefakturisanog rada prikazano kao FAKTURISANO — advokat vidi "
        "dug koji klijentu nikad nije ispostavljen")
    assert d["neplaceno_rsd"] == 0
    assert d["naplaceno_rsd"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2-5 — FAKTURISANO PRATI FAKTURE, NE RAD
# ═══════════════════════════════════════════════════════════════════════════

def test_2_faktura_postoji():
    r, _ = _pozovi(_osnova(billing_entries=_rad(1000.0, 2500.0, 500.0),
                           fakture=[_faktura(4000.0)]))
    assert r.json()["fakturisano_rsd"] == 4000.0


def test_3_delimicno_fakturisano():
    """Rad 4.000, faktura 2.500 — fakturisano NE SME postati 4.000."""
    r, _ = _pozovi(_osnova(billing_entries=_rad(1000.0, 2500.0, 500.0),
                           fakture=[_faktura(2500.0)]))
    d = r.json()
    assert d["fakturisano_rsd"] == 2500.0, "fakturisano prati rad umesto fakture"
    assert d["neplaceno_rsd"] == 2500.0


def test_4_fakturisano_ali_nista_naplaceno():
    r, _ = _pozovi(_osnova(fakture=[_faktura(2500.0, status="izdata")]))
    d = r.json()
    assert d["fakturisano_rsd"] == 2500.0
    assert d["naplaceno_rsd"] == 0
    assert d["neplaceno_rsd"] == 2500.0


def test_5_fakturisano_i_naplaceno():
    r, _ = _pozovi(_osnova(fakture=[_faktura(2500.0, status="placena")]))
    d = r.json()
    assert d["fakturisano_rsd"] == 2500.0
    assert d["naplaceno_rsd"] == 2500.0
    assert d["neplaceno_rsd"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6 — TENANT SCOPING OSTAJE U DB UPITU
# ═══════════════════════════════════════════════════════════════════════════

def test_6_svaki_izvor_je_skopiran_po_user_id():
    _r, supa = _pozovi(_osnova(billing_entries=_rad(1000.0),
                               fakture=[_faktura(1000.0)]))
    po_tabeli = {t for (t, k, v) in supa.scoping if k == "user_id" and v == UID}
    for t in ("predmeti", "rocista", "billing_entries", "fakture", "predmet_hronologija"):
        assert t in po_tabeli, "izvor `%s` nije skopiran po user_id" % t


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7 — PERIOD
# ═══════════════════════════════════════════════════════════════════════════

def test_7_faktura_van_meseca_ne_ulazi():
    r, _ = _pozovi(_osnova(fakture=[_faktura(9999.0, datum=PROSLI)]))
    assert r.json()["fakturisano_rsd"] == 0, "faktura iz drugog meseca je ušla u mesec"


def test_7b_faktura_u_mesecu_ulazi():
    r, _ = _pozovi(_osnova(fakture=[_faktura(1234.0, datum=OVAJ)]))
    assert r.json()["fakturisano_rsd"] == 1234.0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8 — FAIL-CLOSED: PAD IZVORA NIJE NULA
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("izvor", ["fakture", "billing_entries"])
def test_8_pad_izvora_daje_503_a_ne_laznu_nulu(izvor):
    r, _ = _pozovi(_osnova(billing_entries=_rad(1000.0), fakture=[_faktura(1000.0)]),
                   pada={izvor})
    assert r.status_code == 503, (
        "pad izvora `%s` je prikazan kao broj umesto kao greška" % izvor)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9 — RAD OSTAJE VIDLJIV, SAMO POD TAČNIM IMENOM
# ═══════════════════════════════════════════════════════════════════════════

def test_9_uneseni_rad_se_i_dalje_prikazuje():
    """Popravka ne sme da sakrije mesečni rad — samo da ga prestane zvati
    „fakturisano"."""
    r, _ = _pozovi(_osnova(billing_entries=_rad(1000.0, 2500.0, 500.0), fakture=[]))
    d = r.json()
    assert d.get("uneseno_rsd") == 4000.0, (
        "mesečni rad je nestao iz izveštaja umesto da bude ispravno imenovan")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10 — GODISNJI IZVESTAJ SE NE MENJA
# ═══════════════════════════════════════════════════════════════════════════

def test_10_godisnji_i_dalje_izvodi_fakturisano_iz_faktura():
    import io as _io
    src = _io.open(os.path.join(os.path.dirname(__file__), "..",
                                "routers", "billing_reports.py"), encoding="utf-8").read()
    assert 'ukupno_fakturisano = sum(float(f.get("iznos_sa_pdv") or 0) for f in fakture)' in src, (
        "godišnji izveštaj je promenio izvor fakturisanja")
