# -*- coding: utf-8 -*-
"""
Program Sigma, Master Sprint 002 (2026-08-06) — "Autonomous Evidence & Timeline
Reconstruction Engine". Tests for 2 real, previously-unknown bugs found and fixed
this sprint while auditing the Evidence Graph's own canonical writers: the literal
string "now()" (with parentheses) is NOT a value Postgres's timestamptz input
parser recognizes -- only the bare word "now" is a documented special value. This
is the SAME bug class Program Omega Sprint 004 already found and fixed for
case_actions.closed_at (services/case_evolution.py).

1. routers/evidence.py::delete_dokaz -- predmet_dokazi.deleted_at (soft-delete).
2. routers/evidence.py::klasifikuj_i_sacuvaj -- predmet_dokumenti.klasifikovan_at
   (the canonical evidence-classification timestamp, written on every document
   classification).
3. routers/smart_intake.py's own document-insert variant-fallback loop -- the
   SAME klasifikovan_at bug, but with a more severe consequence: because the
   fallback loop catches ANY insert exception and silently tries a narrower
   variant, this one invalid value in 3 of 6 variants risked masking a
   different-looking "migration not applied" degradation, actually falling all
   the way to a variant with neither tip_dokaza nor tekst_sadrzaj at all.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type": "http", "method": "DELETE", "headers": [], "query_string": b"",
              "path": "/predmeti/pred-1/dokaz/dok-1", "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


@pytest.mark.anyio
async def test_delete_dokaz_writes_a_real_timestamp_not_the_literal_string():
    """Wave 2 Task 2D corrective closure (2026-09-20): delete_dokaz's own
    soft-delete moved from a client-side .update({"deleted_at": <python
    computed iso string>}) into migration 130's atomic invalidate_dokaz_
    and_emit_event RPC, which sets `deleted_at = now()` directly in SQL --
    a real, unquoted call to Postgres's own now() FUNCTION, not the
    quoted string literal "now()" this test file's bug class is about
    (a quoted string embedded in a value is what the timestamptz parser
    rejects; an actual function call in a SET clause is exactly the
    correct fix, arguably more robust than a client-computed timestamp --
    no risk of app/DB clock skew)."""
    import os
    migracija_put = os.path.join(os.path.dirname(__file__), "..", "migrations", "131_atomic_source_invalidation.sql")
    with open(migracija_put, "r", encoding="utf-8") as f:
        migracija = f.read()
    assert "SET deleted_at = now()" in migracija
    assert 'SET deleted_at = \'now()\'' not in migracija  # the quoted-string bug shape, must never reappear

    from routers import evidence as ev
    supa = MagicMock()
    supa.rpc.return_value.execute.return_value = MagicMock(data=[{"predmet_id": "pred-1", "invalidated": True}])
    with patch("routers.evidence.get_supa", return_value=supa):
        await ev.delete_dokaz(_req(), "pred-1", "dok-1", user={"user_id": "u1"})
    # No client-side timestamp is even computed anymore -- the RPC call
    # itself carries no deleted_at value at all (the SQL owns it).
    _, rpc_params = supa.rpc.call_args[0]
    assert "deleted_at" not in rpc_params


def test_klasifikuj_i_sacuvaj_writes_a_real_timestamp_for_klasifikovan_at():
    from routers import evidence as ev

    dokumenti_table = MagicMock()
    dokazi_table = MagicMock()

    def _table(name):
        return dokumenti_table if name == "predmet_dokumenti" else dokazi_table
    supa = MagicMock()
    supa.table = MagicMock(side_effect=_table)

    def _fake_rezultat(naziv, tekst):
        return {"tip_dokaza": "podnesak", "pravni_elementi": [], "ai_tags": {}, "kljucne_cinjenice": []}

    with patch("routers.evidence.get_supa", return_value=supa), \
         patch("routers.evidence._klasifikuj_dokument", side_effect=_fake_rezultat):
        ev.klasifikuj_i_sacuvaj("predmet-1", "dok-1", "tuzba.pdf", "neki tekst dokumenta " * 5, "user-1")

    dokumenti_table.update.assert_called_once()
    payload = dokumenti_table.update.call_args[0][0]
    assert payload["klasifikovan_at"] != "now()"
    from datetime import datetime
    datetime.fromisoformat(payload["klasifikovan_at"])


@pytest.mark.anyio
async def test_smart_intake_document_variant_never_contains_the_literal_now_string():
    """The more severe of the 2 klasifikovan_at bugs: routers/smart_intake.py's
    own 6-variant insert-fallback loop had "now()" baked into the FIRST 3
    variants (all richer than the base) -- if that value genuinely breaks the
    insert, every Smart-Intake document would silently fall through to the
    variant with neither tip_dokaza nor tekst_sadrzaj. This test proves the
    variant construction itself no longer contains the bad literal, at the
    exact source line rather than mocking the whole finalize flow."""
    import inspect
    import routers.smart_intake as si

    source = inspect.getsource(si)
    # The specific line this sprint fixed -- must no longer construct
    # klasifikovan_at from the literal string "now()".
    assert '"klasifikovan_at": "now()"' not in source
