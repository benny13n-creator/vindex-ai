# -*- coding: utf-8 -*-
"""
Program Intake Sprint 001 (2026-08-04) — regression tests for 3 of the
predmet_dokumenti writer sites that previously never set `status` (silently
falling to the misleading `na_cekanju` DB default forever) or, in
drafting.py's case, never set `tip_dokaza` (permanently NULL — no
classification path touches lawyer-approved AI drafts). Fork 1/Fork 3
findings — directly addresses the mission's "dokument može ostati bez
statusa" closure-blocking condition.

Covers:
1. routers/intake.py::intake_kreiraj — wizard reference-linking of an
   already-uploaded (session-based) document now explicitly writes
   status='sacuvano' (existing vocabulary, not a new value).
2. routers/onboarding.py::kreiraj_demo_predmet — the synthetic demo
   document (no real file behind it) now explicitly writes status='demo'
   (deliberately distinct from 'sacuvano'/'indeksirano' — it never went
   through the real pipeline).
3. routers/drafting.py::_promote_staged_draft_to_pinecone — an approved AI
   draft promoted into the permanent case record now explicitly writes
   tip_dokaza='podnesak' (existing evidence.py vocabulary — deterministic,
   not a new AI classification call, since the document type is already
   100% known from the call context).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request(path="/api/intake/kreiraj"):
    scope = {
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": path, "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "test@vindex.rs", "role": "advokat"}


# ═══════════════════════════════════════════════════════════════════════════
# 1. routers/intake.py — wizard document-linking sets status='sacuvano'
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_intake_kreiraj_links_document_with_explicit_status():
    from routers.intake import IntakeKreirajReq, DokumentIntakeRef, intake_kreiraj

    new_predmet = {
        "id": "pred-doc-link-001", "user_id": _fake_user()["user_id"],
        "naziv": "Ugovorni spor", "opis": "", "tip": "opsti", "status": "aktivan",
    }
    captured_doc_inserts = []

    def _table(name):
        c = MagicMock()
        for m in ["select", "eq", "insert", "execute", "order", "limit", "single", "gte"]:
            setattr(c, m, MagicMock(return_value=c))
        if name == "predmeti":
            # Program Lambda, Certification 004: intake_kreiraj now does a
            # SELECT (recent-duplicate check, must find nothing) before the
            # INSERT (must return the new predmet) -- .insert() routes to
            # its own chain so .execute() can distinguish the two.
            empty = MagicMock(); empty.data = []
            c.execute = MagicMock(return_value=empty)

            def _insert(payload):
                ic = MagicMock()
                for m in ["eq", "select", "order", "limit", "single"]:
                    setattr(ic, m, MagicMock(return_value=ic))
                r = MagicMock(); r.data = [new_predmet]
                ic.execute = MagicMock(return_value=r)
                return ic
            c.insert = MagicMock(side_effect=_insert)
        elif name == "predmet_dokumenti":
            def _capture(payload):
                captured_doc_inserts.append(payload)
                r = MagicMock(); r.data = [dict(payload, id="dok-linked-1")]
                ic = MagicMock(); ic.execute = MagicMock(return_value=r)
                return ic
            c.insert = MagicMock(side_effect=_capture)
        else:
            r = MagicMock(); r.data = []
            c.execute = MagicMock(return_value=r)
        return c

    mock_supa = MagicMock()
    mock_supa.table = MagicMock(side_effect=_table)

    req = IntakeKreirajReq(
        klijent_id="kl-doc-link-001", naziv="Ugovorni spor",
        dokumenti=[DokumentIntakeRef(naziv_fajla="ugovor.pdf", session_id="sess-abc-123")],
    )

    with patch("routers.intake._get_supa", return_value=mock_supa), \
         patch("asyncio.create_task", side_effect=lambda coro, *a, **kw: MagicMock()):
        result = await intake_kreiraj(req, _fake_request(), _fake_user())

    assert result["success"] is True
    assert len(captured_doc_inserts) == 1
    assert captured_doc_inserts[0]["status"] == "sacuvano"
    assert captured_doc_inserts[0]["status"] != "na_cekanju"


# ═══════════════════════════════════════════════════════════════════════════
# 2. routers/onboarding.py — demo document sets status='demo'
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kreiraj_demo_predmet_document_has_explicit_demo_status():
    from routers.onboarding import kreiraj_demo_predmet

    captured_doc_inserts = []

    def _table(name):
        c = MagicMock()
        for m in ["select", "eq", "insert", "execute", "order", "limit"]:
            setattr(c, m, MagicMock(return_value=c))
        if name == "predmeti":
            r = MagicMock()
            if getattr(c, "_select_called", False):
                r.data = []
            c.select = MagicMock(return_value=c)
            r.data = []  # "already exists" check: none found
            c.execute = MagicMock(return_value=r)

            def _insert(payload):
                ir = MagicMock(); ir.data = [{"id": "pred-demo-1", **payload}]
                ic = MagicMock(); ic.execute = MagicMock(return_value=ir)
                return ic
            c.insert = MagicMock(side_effect=_insert)
        elif name == "klijenti":
            def _insert(payload):
                ir = MagicMock(); ir.data = [{"id": "kl-demo-1"}]
                ic = MagicMock(); ic.execute = MagicMock(return_value=ir)
                return ic
            c.insert = MagicMock(side_effect=_insert)
        elif name == "predmet_dokumenti":
            def _capture(payload):
                captured_doc_inserts.append(payload)
                ir = MagicMock(); ir.data = [payload]
                ic = MagicMock(); ic.execute = MagicMock(return_value=ir)
                return ic
            c.insert = MagicMock(side_effect=_capture)
        else:
            r = MagicMock(); r.data = []
            c.execute = MagicMock(return_value=r)
        return c

    mock_supa = MagicMock()
    mock_supa.table = MagicMock(side_effect=_table)

    with patch("routers.onboarding._get_supa", return_value=mock_supa):
        result = await kreiraj_demo_predmet(_fake_request("/api/onboarding/demo-predmet"), _fake_user())

    assert result["ok"] is True
    assert len(captured_doc_inserts) == 1
    assert captured_doc_inserts[0]["status"] == "demo"
    # deliberately NOT claiming the document was actually saved/indexed
    assert captured_doc_inserts[0]["status"] not in ("sacuvano", "indeksirano", "na_cekanju")


# ═══════════════════════════════════════════════════════════════════════════
# 3. routers/drafting.py — approved AI draft sets tip_dokaza='podnesak'
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_promote_staged_draft_sets_tip_dokaza_deterministically():
    from routers.drafting import _promote_staged_draft_to_pinecone

    captured_doc_inserts = []

    def _table(name):
        c = MagicMock()
        for m in ["select", "eq", "insert", "execute", "order", "limit"]:
            setattr(c, m, MagicMock(return_value=c))
        if name == "predmet_dokumenti":
            r = MagicMock(); r.data = []  # redni_broj lookup: none yet
            c.execute = MagicMock(return_value=r)

            def _capture(payload):
                captured_doc_inserts.append(payload)
                ir = MagicMock(); ir.data = [payload]
                ic = MagicMock(); ic.execute = MagicMock(return_value=ir)
                return ic
            c.insert = MagicMock(side_effect=_capture)
        else:
            r = MagicMock(); r.data = []
            c.execute = MagicMock(return_value=r)
        return c

    mock_supa = MagicMock()
    mock_supa.table = MagicMock(side_effect=_table)

    staging_row = {
        "predmet_id": "pred-draft-1", "user_id": "user-1", "kancelarija_id": None,
        "tekst": "Ovim putem podnosim tužbu protiv ..." * 20,
        "naziv": "Tužba za naknadu štete", "id": "staging-1",
    }

    with patch("uploaded_doc.chunker.chunk_document",
               return_value=types.SimpleNamespace(total_chunks=1)), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1):
        ok = await _promote_staged_draft_to_pinecone(mock_supa, staging_row)

    assert ok is True
    assert len(captured_doc_inserts) == 1
    assert captured_doc_inserts[0]["tip_dokaza"] == "podnesak"
