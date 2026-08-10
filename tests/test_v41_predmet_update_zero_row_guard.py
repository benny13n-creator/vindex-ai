# -*- coding: utf-8 -*-
"""
V41 / F-V41-001 — zero-row guard za PATCH /api/predmeti/{predmet_id}.

GUARD JE BIO USLOVLJEN OPCIONIM POLJEM
Handler je imao ispravan 404/409 guard, ali iza uslova:

    if if_updated_at and not result.data:

`if_updated_at` je opcioni optimistic-concurrency token koji stariji klijenti
ne šalju. Bez njega je zero-row UPDATE padao pravo u
`return {"ok": True, "updated_at": None}` -- HTTP 200 za mutaciju koja se nije
desila. Test 2 vozi tuđi predmet, test 3 nepostojeći; oba su pre ovog fixa
vraćala uspeh.

ZAŠTO 404 NIJE MOJ IZBOR NEGO DOKAZ IZ IZVORA
Isti handler je već definisao "Predmet nije pronađen" za granu sa tokenom --
ugovor je postojao, samo je bio nedostižan. Fix veže uslov za stvarni ishod
mutacije umesto za prisustvo opcionog polja.

VLASNIŠTVO OSTAJE NEDIRNUTO
`.eq("user_id", user.id)` je oduvek bio u samoj UPDATE naredbi, pa tuđi red
nikad nije bio izmenjen -- curio je samo lažan success ODGOVOR. Test 2 tvrdi
oboje: 404 i da red korisnika B nije promenjen.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

A, B = "advokat-A", "advokat-B"
P = "predmet-1"


class _Store:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [
            {"_t": "predmeti", "id": P, "user_id": A, "naziv": "Stari", "updated_at": "T1"},
            {"_t": "predmeti", "id": "predmet-B", "user_id": B, "naziv": "Tudji", "updated_at": "T1"},
        ]
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

    def maybe_single(self):
        return self

    def execute(self):
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        res = MagicMock()
        if self.op == "update":
            self.s.updates.append(dict(self.f))
            for r in hit:
                r.update(self.patch)
                r["updated_at"] = "T2"
            res.data = hit
        else:
            res.data = hit[0] if hit else None
        return res


def _patch(store, predmet_id, uid, body):
    import api as m

    async def _auth(_a):
        return MagicMock(id=uid)

    req = MagicMock()
    req.url.path = f"/api/predmeti/{predmet_id}"

    async def _json():
        return body
    req.json = _json

    with patch.object(m, "_require_auth_async", _auth), \
         patch.object(m, "_get_supa", return_value=store), \
         patch.object(m, "sanitize_user_input", lambda x: x):
        import asyncio
        try:
            return asyncio.run(m.update_predmet.__wrapped__(predmet_id, req, "Bearer t")), 200
        except HTTPException as e:
            return None, e.status_code


def test_1_owner_update_succeeds():
    st = _Store()
    out, code = _patch(st, P, A, {"naziv": "Novi"})
    assert code == 200 and out["ok"] is True
    assert [r for r in st.rows if r["id"] == P][0]["naziv"] == "Novi"


def test_2_foreign_predmet_is_404_not_fake_success():
    """F-V41-001: pre fixa je vraćalo {"ok": True} bez ijedne izmene."""
    st = _Store()
    out, code = _patch(st, "predmet-B", A, {"naziv": "Otet"})
    assert code == 404, f"tuđi predmet mora dati 404, dobijeno {code}"
    assert [r for r in st.rows if r["id"] == "predmet-B"][0]["naziv"] == "Tudji", (
        "tuđi red je oduvek bio zaštićen -- curio je samo lažan success odgovor"
    )


def test_3_nonexistent_predmet_is_404():
    st = _Store()
    out, code = _patch(st, "ne-postoji", A, {"naziv": "X"})
    assert code == 404


def test_4_stale_precondition_still_409():
    """Postojeća optimistic-concurrency semantika mora ostati netaknuta."""
    st = _Store()
    out, code = _patch(st, P, A, {"naziv": "Novi", "if_updated_at": "ZASTARELO"})
    assert code == 409, f"zastareo token mora dati 409, dobijeno {code}"


def test_5_matching_precondition_succeeds():
    st = _Store()
    out, code = _patch(st, P, A, {"naziv": "Novi", "if_updated_at": "T1"})
    assert code == 200
    assert out["updated_at"] == "T2", "novi updated_at se vraća pozivaocu"


def test_6_no_valid_fields_is_400():
    st = _Store()
    out, code = _patch(st, P, A, {"nepostojece_polje": 1})
    assert code == 400
    assert st.updates == [], "bez validnih polja se ne sme ni pokušati UPDATE"


def test_7_owner_predicate_inside_the_update():
    import inspect
    import api as m
    src = inspect.getsource(m.update_predmet)
    after = src.split(".update(allowed)", 1)[1]
    assert 'eq("user_id", user.id)' in after, (
        "owner predikat mora ostati unutar UPDATE naredbe"
    )


def test_8_guard_is_not_conditioned_on_the_optional_token():
    """Trajni invarijant: guard zavisi od ishoda mutacije, ne od opcionog polja."""
    import inspect
    import api as m
    src = inspect.getsource(m.update_predmet)
    assert "if if_updated_at and not result.data:" not in src, (
        "guard ne sme biti uslovljen prisustvom if_updated_at"
    )
    assert "if not result.data:" in src
