# -*- coding: utf-8 -*-
"""
V46 — zašto singleton odjave NISU zero-row defekt (odjavi_pretplatu, obrisi_telefon).

Obe rute su prošle kroz F-V41-002 trijažu kao "owner-scoped UPDATE sa odbačenim
rezultatom" i obe su klasifikovane NOT A DEFECT. Ovaj fajl ne popravlja ništa --
zaključava tri činjenice iz kojih ta klasifikacija sledi, da sledeći sweep ne bi
ponovo prijavio iste rute, i da promena oblika ne bi tiho nasledila neobezbeđen
obrazac.

ŠTA ČINI ZERO-ROW LEGITIMNIM OVDE
1. Zahtev ne nosi NIJEDAN resource id -- meta je "moja pretplata", ne red koji
   korisnik imenuje. Nema id-a koji bi pozivalac mogao da pogreši ili podmetne.
2. Predikat JESTE pozivaočev sopstveni user_id, pa strani resurs ne postoji kao
   slučaj -- za razliku od delete_dokaz / delete_api_kljuc / ukloni_praceni,
   gde je 404 bio jedini istinit odgovor.
3. Registracija radi upsert(on_conflict="user_id"), dakle najviše jedan red po
   korisniku. Nula redova znači "korisnik nikad nije uključio ovaj kanal", pa je
   {"aktivan": False} istinita tvrdnja o krajnjem stanju.

Ako se ijedna od te tri činjenice promeni -- naročito ako ruta dobije id
parametar -- klasifikacija više ne važi i ruta traži zero-row guard. Testovi
ispod padaju upravo tada.
"""
import asyncio
import inspect
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A = "advokat-A"


class _Store:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.updates = []

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, s, t):
        self.s, self.t, self.f, self.op = s, t, {}, "select"

    def update(self, patch):
        self.op, self.patch = "update", patch
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def execute(self):
        hit = [r for r in self.s.rows if all(r.get(k) == v for k, v in self.f.items())]
        if self.op == "update":
            self.s.updates.append(dict(self.f))
            for r in hit:
                r.update(self.patch)
        res = MagicMock()
        res.data = hit
        return res


def _http():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def test_1_whatsapp_unsubscribe_has_no_resource_id_parameter():
    """Nema id-a u potpisu -> nema resursa koji bi pozivalac mogao promašiti."""
    import routers.whatsapp_notif as m
    params = set(inspect.signature(m.odjavi_pretplatu).parameters)
    assert not (params - {"request", "user"}), (
        f"ruta je dobila nove parametre {params} -- ako je među njima resource id, "
        "zero-row više nije legitiman i traži guard"
    )


def test_2_sms_deactivate_has_no_resource_id_parameter():
    import routers.sms as m
    params = set(inspect.signature(m.obrisi_telefon).parameters)
    assert not (params - {"request", "user"}), (
        f"ruta je dobila nove parametre {params} -- vidi test 1"
    )


def test_3_whatsapp_predicate_is_only_the_caller_own_uid():
    import routers.whatsapp_notif as m
    st = _Store([{"user_id": A, "aktivan": True}])
    with patch.object(m, "_get_supa", return_value=st):
        out = asyncio.run(m.odjavi_pretplatu.__wrapped__(_http(), {"user_id": A}))
    assert out == {"ok": True, "aktivan": False}
    assert st.updates == [{"user_id": A}], (
        "predikat mora biti isključivo pozivaočev user_id -- to je razlog zašto "
        "strani resurs ovde ne postoji kao slučaj"
    )
    assert st.rows[0]["aktivan"] is False


def test_4_zero_row_is_a_true_statement_not_a_false_success():
    """Korisnik bez pretplate: nula redova, a {"aktivan": False} je istina."""
    import routers.whatsapp_notif as m
    st = _Store([])
    with patch.object(m, "_get_supa", return_value=st):
        out = asyncio.run(m.odjavi_pretplatu.__wrapped__(_http(), {"user_id": A}))
    assert out == {"ok": True, "aktivan": False}, (
        "kanal NIJE aktivan -- odgovor opisuje krajnje stanje, ne izvršenu mutaciju"
    )


def test_5_registration_upserts_on_user_id_proving_at_most_one_row():
    """Treća činjenica: singleton po korisniku."""
    import routers.whatsapp_notif as m
    src = inspect.getsource(m)
    assert 'on_conflict="user_id"' in src, (
        "bez upsert-a po user_id-u ruta bi mogla imati više redova i "
        "klasifikacija bi tražila ponovnu proveru"
    )
