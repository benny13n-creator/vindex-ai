# -*- coding: utf-8 -*-
"""
V45 / F-V41-002 — DELETE /api/portal/prati/{praceni_id}.

DVA NEZAVISNA PUTA DO LAŽNOG USPEHA
Ovo je jedina do sada nađena ruta u klasi koja je imala oba:

  1. rezultat mutacije se odbacivao -> nepostojeći ili tuđi praceni_id je
     vraćao {"ok": True} bez ijednog dirnutog reda (test 2, 3)
  2. `except Exception` je gutao stvarni otkaz baze i takođe vraćao
     {"ok": True} -- baza eksplicitno padne, korisnik dobije potvrdu (test 6)

Druga je teža: prva je propust u dokazu, druga je aktivno prikrivanje otkaza.

ISHODI SU IZVEDENI IZ KONVENCIJE SAMOG FAJLA
404 i 500 nisu preneti iz ranijih sprintova po sličnosti. `dodaj_praceni` --
direktni parnjak ove rute -- na otkaz diže HTTPException(500), kao i endpoint za
metrike; graciozno degradiranje na prazan odgovor rezervisano je za ČITANJA
(lista pracenih, log). Ovo je bila jedina mutacija u fajlu koja guta izuzetak.
Test 8 to zaključava.

VEĆ DEAKTIVIRANO NIJE ZERO-ROW
Red sa aktivan=False i dalje poklapa `id` + `user_id`, pa UPDATE vraća red i
ruta ostaje 200 (test 5). Idempotencija je očuvana bez ijedne posebne grane;
pretvaranje u 404 bilo bi izmišljanje semantike koju kod nema.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "advokat-A", "advokat-B"


class _Store:
    def __init__(self, rows=None, raises=False, vanish_before_update=False):
        self.rows = rows if rows is not None else [
            {"_t": "praceni_predmeti", "id": "pr-A", "user_id": A, "aktivan": True},
            {"_t": "praceni_predmeti", "id": "pr-B", "user_id": B, "aktivan": True},
        ]
        self.raises = raises
        self.vanish = vanish_before_update
        self.updates = []

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, s, t):
        self.s, self.t, self.f, self.op = s, t, {}, "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def update(self, patch):
        self.op, self.patch = "update", patch
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def execute(self):
        if self.s.raises:
            raise RuntimeError("DB down")
        if self.op == "update" and self.s.vanish:
            self.s.rows = [r for r in self.s.rows if r.get("_t") != "praceni_predmeti"]
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        res = MagicMock()
        if self.op == "update":
            self.s.updates.append(dict(self.f))
            for r in hit:
                r.update(self.patch)
        res.data = hit
        return res


def _remove(store, praceni_id, uid=A):
    import routers.portal_monitoring as m
    with patch.object(m, "_get_supa", return_value=store):
        try:
            return asyncio.run(m.ukloni_praceni(praceni_id, {"user_id": uid})), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_own_tracked_case_deactivated():
    st = _Store()
    out, code = _remove(st, "pr-A")
    assert code == 200 and out == {"ok": True}
    assert [r for r in st.rows if r["id"] == "pr-A"][0]["aktivan"] is False


def test_2_nonexistent_is_404_not_fake_success():
    st = _Store()
    out, code = _remove(st, "ne-postoji")
    assert code == 404, f"nepostojeći zapis mora dati 404, dobijeno {code}"
    assert out is None


def test_3_foreign_record_is_404_and_stays_active():
    st = _Store()
    out, code = _remove(st, "pr-B", uid=A)
    assert code == 404, "tuđi zapis mora dati 404"
    assert [r for r in st.rows if r["id"] == "pr-B"][0]["aktivan"] is True, (
        "tuđi zapis je oduvek bio zaštićen -- curio je samo lažan odgovor"
    )


def test_4_owner_predicate_is_inside_the_update():
    st = _Store()
    _remove(st, "pr-A")
    assert st.updates, "UPDATE se mora izvršiti"
    assert st.updates[0].get("user_id") == A, "owner predikat mora biti u samoj naredbi"
    assert st.updates[0].get("id") == "pr-A"


def test_5_already_deactivated_stays_200():
    """Red i dalje poklapa -> nije zero-row; idempotencija bez posebne grane."""
    st = _Store(rows=[{"_t": "praceni_predmeti", "id": "pr-A", "user_id": A, "aktivan": False}])
    out, code = _remove(st, "pr-A")
    assert code == 200, "ponovljeno uklanjanje je istinita tvrdnja o krajnjem stanju"


def test_6_db_exception_is_500_not_swallowed_success():
    """Najteži od dva defekta: baza padne, a korisnik je dobijao {"ok": True}."""
    st = _Store(raises=True)
    out, code = _remove(st, "pr-A")
    assert code == 500, f"otkaz baze mora biti prijavljen, dobijeno {code}"
    assert out is None


def test_7_toctou_zero_row_is_404():
    """Red nestane između poziva i izvršenja mutacije."""
    st = _Store(vanish_before_update=True)
    out, code = _remove(st, "pr-A")
    assert code == 404
    assert out is None


def test_8_sibling_mutation_convention_still_holds():
    """404/500 su izvedeni iz ovog fajla, ne iz opšteg obrasca drugih ruta."""
    import inspect
    import routers.portal_monitoring as m
    add_src = inspect.getsource(m.dodaj_praceni)
    assert "status_code=500" in add_src, (
        "parnjak dodaj_praceni mora i dalje dizati 500 na otkaz -- to je "
        "izvor iz kog je izveden ugovor ove rute"
    )
    del_src = inspect.getsource(m.ukloni_praceni)
    assert "except HTTPException:" in del_src, (
        "404 ne sme biti progutan sopstvenim except Exception blokom"
    )


def test_9_no_audit_is_emitted():
    calls = []

    async def _spy(action, **kw):
        calls.append(action)
        return "id"

    st = _Store()
    with patch("shared.audit_immutable.log_action", _spy):
        _remove(st, "pr-A")
    assert calls == [], "V45 popravlja mutaciju i ne uvodi audit"
