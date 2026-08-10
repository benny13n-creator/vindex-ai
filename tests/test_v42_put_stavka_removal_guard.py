# -*- coding: utf-8 -*-
"""
V42 / F-V40-001 lokacija 2 — zero-row guard za PUT /api/tarife/stavke/{kod}.

DRUGA POLOVINA ISTOG NALAZA
`put_klijent_tarifa` je popravljen u V40-A/V40-B2; `put_stavka` je nosio isti
defekt netaknut: DELETE rezultat se odbacivao i ruta je bezuslovno vraćala
`removed: true` -- i korisniku koji nikada nije imao sopstveni override za taj
tarifni kod, i za tuđi red.

VLASNIŠTVO NIJE BILO PROBIJENO
`.eq("user_id", uid)` je oduvek bio u samoj DELETE naredbi, pa tuđi red nije
mogao biti obrisan. Curio je lažan success ODGOVOR: klijent nije mogao da
razlikuje "poništio sam svoju izmenu" od "nisam imao šta da poništim". Test 3
tvrdi oboje -- 404 i da tuđi red preživi.

BEZ AUDITA
Ova ruta nema `log_action` i V42 ga NE uvodi: popravka mutacije i uvođenje
audita su odvojeni poslovi, a za `tarifne_stavke_custom` ne postoji dokazana
akcija u registru. Test 6 to zaključava da neko kasnije ne bi dodao
`tarifa_delete` (koji označava red u DRUGOJ tabeli).
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as _SReq

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "advokat-A", "advokat-B"
KOD = "T01"


class _Store:
    """DELETE uklanja red samo ako SVI .eq() predikati poklope."""

    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [
            {"_t": "tarifne_stavke_custom", "id": "st-A", "user_id": A, "kod": KOD, "iznos": 9.0},
            {"_t": "tarifne_stavke_custom", "id": "st-B", "user_id": B, "kod": KOD, "iznos": 7.0},
        ]
        self.deletes = []

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, s, t):
        self.s, self.t, self.f, self.op = s, t, {}, "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def update(self, p):
        self.op, self.patch = "update", p
        return self

    def insert(self, r):
        self.op, self.row = "insert", r
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, c, v):
        self.f[c] = v
        return self

    def limit(self, n):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        res = MagicMock()
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        if self.op == "delete":
            self.s.deletes.append(dict(self.f))
            for r in hit:
                self.s.rows.remove(r)
            res.data = hit
        elif self.op == "select":
            res.data = hit
        else:
            # UPDATE/INSERT vracaju pun red (returning=representation), pa mora
            # nositi i `iznos` -- produkcija ga cita iz rezultata mutacije.
            val = getattr(self, "patch", getattr(self, "row", {}))
            res.data = [{"id": "st-A", "kod": KOD, "iznos": val.get("iznos", 9.0),
                         "naziv": val.get("naziv")}]
        return res


def _http():
    return _SReq(scope={"type": "http", "method": "PUT", "headers": [], "query_string": b"",
                        "path": f"/api/tarife/stavke/{KOD}", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _reset(store, uid=A, kod=KOD):
    """PUT sa iznos=None i naziv=None -> grana uklanjanja."""
    import asyncio
    import routers.tarife as m
    body = m.StavkaReq(iznos=None, naziv=None)
    with patch.object(m, "_get_supa", return_value=store):
        try:
            return asyncio.run(m.put_stavka(kod, body, _http(), {"user_id": uid})), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_own_override_reset_succeeds():
    st = _Store()
    out, code = _reset(st)
    assert code == 200
    assert out == {"ok": True, "removed": True, "kod": KOD}
    assert not [r for r in st.rows if r["id"] == "st-A"], "red mora biti obrisan"


def test_2_no_override_at_all_is_404():
    """F-V40-001: bezuslovni removed:true je tvrdio brisanje koga nije bilo."""
    st = _Store(rows=[])
    out, code = _reset(st)
    assert code == 404, f"nepostojeći override mora dati 404, dobijeno {code}"
    assert out is None


def test_3_foreign_override_is_404_and_survives():
    st = _Store(rows=[{"_t": "tarifne_stavke_custom", "id": "st-B",
                       "user_id": B, "kod": KOD, "iznos": 7.0}])
    out, code = _reset(st, uid=A)
    assert code == 404, "tuđi override nije moj -> 404"
    assert any(r["id"] == "st-B" for r in st.rows), "tuđi red mora ostati"


def test_4_owner_predicate_is_inside_the_delete():
    st = _Store()
    _reset(st)
    assert st.deletes, "DELETE se mora izvršiti"
    assert st.deletes[0].get("user_id") == A, "owner predikat mora biti u DELETE naredbi"
    assert st.deletes[0].get("kod") == KOD


def test_5_second_reset_cannot_report_a_second_success():
    st = _Store()
    _, code1 = _reset(st)
    assert code1 == 200
    _, code2 = _reset(st)
    assert code2 == 404, "drugi poziv ne sme prijaviti drugo uspešno brisanje"


def test_6_removal_branch_emits_no_audit():
    """Ova ruta nema audit i V42 ga ne uvodi -- ni slučajno tuđom akcijom."""
    import routers.tarife as m

    calls = []

    async def _spy(action, **kw):
        calls.append(action)
        return "id"

    st = _Store()
    with patch("shared.audit_immutable.log_action", _spy):
        _reset(st)
    assert calls == [], (
        "tarifne_stavke_custom nema dokazanu akciju; tarifa_delete označava red "
        "u tabeli `tarife`, ne ovde"
    )


def test_7_unknown_kod_is_404_before_any_delete():
    st = _Store()
    out, code = _reset(st, kod="NEPOSTOJECI")
    assert code == 404
    assert st.deletes == [], "nepoznat kod ne sme ni doći do DELETE-a"


def test_8_edit_branch_unaffected():
    """Regresioni pojas: postavljanje iznosa ne sme ući u granu brisanja."""
    import asyncio
    import routers.tarife as m
    st = _Store()
    body = m.StavkaReq(iznos=12.5, naziv=None)
    with patch.object(m, "_get_supa", return_value=st):
        out = asyncio.run(m.put_stavka(KOD, body, _http(), {"user_id": A}))
    assert out["ok"] is True
    assert st.deletes == [], "grana izmene ne sme brisati"
