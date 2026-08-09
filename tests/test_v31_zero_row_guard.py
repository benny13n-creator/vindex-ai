# -*- coding: utf-8 -*-
"""
V31 — zero-row guard za dve DELETE rute.

DEFEKT
Obe rute su izvršavale owner-scoped DELETE i potom ODBACIVALE rezultat:

    await asyncio.to_thread(lambda: supa.table(T).delete().eq(...).execute())
    return {"status": "obrisan"}      # bezuslovno

Owner predikat je uvek držao -- tuđi red se nikada nije brisao. Ali handler
nije razlikovao "obrisan jedan red" od "nijedan red nije poklopljen", pa je
nepostojeći I tuđi ID dobijao HTTP 200 sa porukom o uspešnom brisanju.

Devet od jedanaest srodnih DELETE ruta već koristi `if not r.data: raise 404`
(rocista, knowledge_base, recurring, zadaci, billing, integracije). Ove dve su
bile odstupanje od sopstvenog obrasca sistema.

OBIM
Ovo NIJE audit sprint. Testovi ne tvrde ništa o log_action() -- samo o HTTP
ugovoru i o tome da tuđi red ostaje netaknut.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

from starlette.requests import Request as _SReq

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _Store:
    """Minimalni model DELETE semantike: briše samo red koji poklapa SVE .eq()."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.deleted = []

    def table(self, name):
        return _Q(self, name)


class _Q:
    def __init__(self, store, table):
        self.s = store
        self.t = table
        self.f = {}

    def delete(self):
        return self

    def eq(self, col, val):
        self.f[col] = val
        return self

    def execute(self):
        hit = [r for r in self.s.rows
               if r.get("_t") == self.t and all(r.get(k) == v for k, v in self.f.items())]
        for r in hit:
            self.s.rows.remove(r)
            self.s.deleted.append(r)
        res = MagicMock()
        res.data = hit          # PostgREST vraća obrisane redove
        return res


A, B = "user-A", "user-B"


def _komentari_store():
    return _Store([
        {"_t": "predmet_komentari", "id": "kom-A", "user_id": A},
        {"_t": "predmet_komentari", "id": "kom-B", "user_id": B},
    ])


def _webhooks_store():
    return _Store([
        {"_t": "webhooks", "id": "wh-A", "user_id": A},
        {"_t": "webhooks", "id": "wh-B", "user_id": B},
    ])


def _http():
    """@limiter.limit traži pravi Request, ne MagicMock."""
    return _SReq(scope={"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
                        "path": "/komentari/x", "client": ("127.0.0.1", 1),
                        "app": MagicMock(), "state": MagicMock()})


def _call_komentar(store, komentar_id, uid):
    import routers.komentari as k
    with patch.object(k, "_get_supa", return_value=store):
        return asyncio.run(k.delete_komentar(komentar_id, _http(), {"user_id": uid}))


def _call_webhook(store, webhook_id, uid):
    import routers.integrations as ig
    with patch.object(ig, "_get_supa", return_value=store):
        return asyncio.run(ig.delete_webhook(webhook_id, {"user_id": uid}))


def _status(fn, *a):
    """Vraća (status, izuzetak) bez obzira kojim kanalom ruta signalizira."""
    try:
        out = fn(*a)
        return getattr(out, "status_code", 200), None
    except HTTPException as exc:
        return exc.status_code, exc


# ── komentar_delete ───────────────────────────────────────────────────────

def test_1_komentar_success():
    st = _komentari_store()
    code, _ = _status(_call_komentar, st, "kom-A", A)
    assert code == 200
    assert not [r for r in st.rows if r["id"] == "kom-A"], "red mora biti obrisan"


def test_2_komentar_nonexistent_is_404():
    st = _komentari_store()
    code, exc = _status(_call_komentar, st, "ne-postoji", A)
    assert code == 404, f"nepostojeći ID mora biti 404, dobijeno {code}"
    assert len(st.rows) == 2, "ništa se ne sme obrisati"


def test_3_komentar_foreign_owner_is_404_and_row_survives():
    """Najvažniji: tuđi red mora OSTATI, ne samo biti odbijen."""
    st = _komentari_store()
    code, _ = _status(_call_komentar, st, "kom-B", A)
    assert code == 404, f"tuđi resurs mora biti 404, dobijeno {code}"
    assert any(r["id"] == "kom-B" for r in st.rows), "komentar korisnika B mora ostati netaknut"
    assert st.deleted == [], "nijedan red ne sme biti obrisan"


# ── integration_webhook_delete ────────────────────────────────────────────

def test_4_webhook_success():
    st = _webhooks_store()
    code, _ = _status(_call_webhook, st, "wh-A", A)
    assert code == 200
    assert not [r for r in st.rows if r["id"] == "wh-A"]


def test_5_webhook_nonexistent_is_404():
    st = _webhooks_store()
    code, _ = _status(_call_webhook, st, "ne-postoji", A)
    assert code == 404
    assert len(st.rows) == 2


def test_6_webhook_foreign_owner_is_404_and_row_survives():
    st = _webhooks_store()
    code, _ = _status(_call_webhook, st, "wh-B", A)
    assert code == 404
    assert any(r["id"] == "wh-B" for r in st.rows), "webhook korisnika B mora ostati netaknut"
    assert st.deleted == []


# ── V31 ne sme uvesti audit ───────────────────────────────────────────────

def test_7_zero_row_guard_survives():
    """Guard mora ostati prisutan i posle kasnijih izmena istih handlera.

    ISTORIJA OVE TVRDNJE: u V31 je glasila "log_action ne sme postojati u ovim
    handlerima" -- ispravno za obim V31, koji je namerno razdvojio HTTP guard od
    audita. V35 je audit dodao po planu, pa je ta formulacija istekla. Nije
    obrisana da bi test prošao: zamenjena je invarijantom koja trajno vredi --
    da guard koji V31 uvodi i dalje stoji. Originalna tvrdnja je sačuvana u git
    istoriji commita 621526bd.
    """
    import inspect
    import routers.integrations as ig
    import routers.komentari as k

    for fn in (k.delete_komentar, ig.delete_webhook):
        src = inspect.getsource(fn)
        assert "if not r.data" in src, f"{fn.__name__} je izgubio zero-row guard"
        assert "404" in src, f"{fn.__name__} više ne vraća 404 na zero-row"
