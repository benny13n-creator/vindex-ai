# -*- coding: utf-8 -*-
"""
Sprint 6B — namespace integrity, then safe subject binding.

PRE-FLIGHT CORRECTED AN EARLIER FINDING OF MY OWN.
The Sprint 6 trace warned that a request declaring pred_ might read text from
tmp_ through the cross-prefix fallback and then be bound to the wrong case.
Reading the actual execution path shows /api/dokument/pitanje never calls
_fetch_session_tekst at all -- it passes the namespace straight to ask_agent as
extra_namespaces. So the fallback never touched the branch being bound.

The fallback is still a real integrity defect for the callers that DO use it
(/analiza, /rokovi, /klasifikuj-sesija, cross_doc, api.py's workspace path):
tmp_<id> and pred_<id> are different ID spaces, and a silent cross-read hands an
AI call text from a namespace the request never asked for. Phase A closes it on
its own merits, not as a precondition for the binding.

Everything here drives real functions. Nothing is proved by grep, and nothing
relies on a UUID-collision argument -- the namespace boundary is asserted as a
code invariant.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request as StarletteRequest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _subject():
    from shared.ai_provenance import current_context
    ctx = current_context()
    return (ctx.get("user_id"), ctx.get("predmet_id"), ctx.get("document_id"))


def _index_with(namespace_texts: dict):
    """A fake Pinecone index that only answers for the namespaces it is given.

    This is what makes the proof a boundary proof rather than a probabilistic
    one: pred_X and tmp_X are BOTH populated with distinguishable text, so a
    cross-read is directly observable instead of being argued away.
    """
    def _query(**kwargs):
        ns = kwargs.get("namespace")
        text = namespace_texts.get(ns)
        if text is None:
            return {"matches": []}
        m = MagicMock()
        m.metadata = {"text": text, "chunk_index": 0, "owner_user_id": "user-A"}
        m.id = "c0"
        return {"matches": [m]}

    idx = MagicMock()
    idx.query.side_effect = _query
    return idx


# ── PHASE A: declared namespace must equal actual namespace ───────────────

def test_a1_declared_pred_reads_pred():
    import routers.dokument as dok

    idx = _index_with({"pred_X": "TEKST IZ PREDMETA", "tmp_X": "TEKST IZ SESIJE"})
    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx):
        out = dok._fetch_session_tekst("X", "pred_")
    assert "PREDMETA" in out


def test_a2_declared_pred_never_falls_back_to_tmp():
    """The defect. pred_X is empty, tmp_X is full; the old code returned the
    tmp_ text. A caller binding provenance to the declared namespace would then
    record a case the AI never actually read."""
    import routers.dokument as dok

    idx = _index_with({"tmp_X": "TEKST IZ SESIJE"})   # pred_X deliberately absent
    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx):
        out = dok._fetch_session_tekst("X", "pred_")
    assert out == "", f"declared pred_ must never consume tmp_ data, got: {out!r}"


def test_a3_declared_tmp_never_falls_back_to_pred():
    """The reverse direction, which is the one most callers hit: /analiza,
    /rokovi and cross_doc all call with the default tmp_ prefix."""
    import routers.dokument as dok

    idx = _index_with({"pred_X": "TEKST IZ PREDMETA"})  # tmp_X deliberately absent
    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx):
        out = dok._fetch_session_tekst("X", "tmp_")
    assert out == "", f"declared tmp_ must never consume pred_ data, got: {out!r}"


def test_a3b_both_present_uses_only_the_declared_one():
    import routers.dokument as dok

    idx = _index_with({"pred_X": "TEKST IZ PREDMETA", "tmp_X": "TEKST IZ SESIJE"})
    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx):
        assert "SESIJE" in dok._fetch_session_tekst("X", "tmp_")
        assert "PREDMETA" in dok._fetch_session_tekst("X", "pred_")


# ── PHASE B/C: subject binding, driven through the real handler ───────────

def _req(session_id="predmet-A", prefix="pred_"):
    from routers.dokument import PitanjeDocRequest
    return PitanjeDocRequest(
        session_id=session_id, pitanje="Koliki je rok za žalbu?",
        namespace_prefix=prefix, history=[],
    )


def _http():
    return StarletteRequest(scope={
        "type": "http", "method": "POST", "headers": [], "query_string": b"",
        "path": "/api/dokument/pitanje", "client": ("127.0.0.1", 1),
        "app": MagicMock(), "state": MagicMock(),
    })


def _owned_supa():
    res = MagicMock()
    res.data = [{"id": "predmet-A"}]
    chain = MagicMock()
    chain.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = res
    supa = MagicMock()
    supa.table.return_value = chain
    return supa


async def _call(dok, session_id="predmet-A", prefix="pred_", user_id="user-A"):
    from shared.ai_provenance import set_request_context
    set_request_context(user_id=user_id)
    return await dok.dokument_pitanje(
        _req(session_id, prefix), {"user_id": user_id, "email": "a@b.rs"},
    )


@pytest.mark.anyio
async def test_c1_pred_success_binds_the_real_predmet_id():
    import routers.dokument as dok

    captured = {}

    def _fake_agent(*a, **k):
        captured["subject"] = _subject()
        return {"status": "success", "data": "odgovor"}

    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", _fake_agent), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await _call(dok)

    assert captured["subject"][1] == "predmet-A", captured["subject"]
    assert captured["subject"][2] is None, "session_id must never be written as document_id"


@pytest.mark.anyio
async def test_c2_pred_failure_carries_the_same_predmet_id():
    import routers.dokument as dok

    captured = {}

    def _err_agent(*a, **k):
        captured["subject"] = _subject()
        return {"status": "error", "message": "Sistem je trenutno zauzet"}

    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", _err_agent), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await _call(dok)

    assert captured["subject"][1] == "predmet-A", (
        "a failed AI call must carry the same subject as a successful one"
    )


@pytest.mark.anyio
async def test_c3_tmp_success_records_no_subject():
    """The core rule: better a truthful NULL than a predmet_id with a false
    meaning. A tmp_ session id is a uuid4 that exists in no table."""
    import routers.dokument as dok

    captured = {}

    def _fake_agent(*a, **k):
        captured["subject"] = _subject()
        return {"status": "success", "data": "odgovor"}

    idx = _index_with({"tmp_sess-1": "x"})
    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", _fake_agent), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await _call(dok, session_id="sess-1", prefix="tmp_")

    assert captured["subject"][1] is None, "a tmp_ session has no canonical subject"
    assert captured["subject"][2] is None


@pytest.mark.anyio
async def test_c8_unauthorized_predmet_never_reaches_the_provider():
    from fastapi import HTTPException
    import routers.dokument as dok

    called = {"n": 0}

    def _must_not_run(*a, **k):
        called["n"] += 1
        return {}

    empty = MagicMock()
    empty.data = []
    chain = MagicMock()
    chain.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = empty
    supa = MagicMock()
    supa.table.return_value = chain

    with patch.object(dok, "_get_supa", return_value=supa), \
         patch("main.ask_agent", _must_not_run), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        with pytest.raises(HTTPException) as exc:
            await _call(dok, session_id="predmet-TUDJ")

    assert exc.value.status_code == 404
    assert called["n"] == 0, "the provider must never be reached for a foreign case"


@pytest.mark.anyio
async def test_c9_the_subject_does_not_survive_the_endpoint():
    import routers.dokument as dok

    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", lambda *a, **k: {"status": "success", "data": "x"}), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await _call(dok)

    assert _subject()[1] is None, "predmet_id must not outlive the endpoint"


@pytest.mark.anyio
async def test_c7_parallel_requests_cross_neither_namespace_nor_subject():
    """One pred_ request and one tmp_ request in flight together. Neither may
    observe the other's subject, and the tmp_ one must stay NULL."""
    import routers.dokument as dok

    seen = {}

    def _record(pitanje, history, extra_ns, *a, **k):
        subj = _subject()
        seen[extra_ns[0]] = subj
        return {"status": "success", "data": "x"}

    idx = _index_with({"tmp_sess-1": "x", "pred_predmet-A": "y"})
    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", _record), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await asyncio.gather(
            _call(dok, session_id="predmet-A", prefix="pred_"),
            _call(dok, session_id="sess-1", prefix="tmp_"),
        )

    assert seen["pred_predmet-A"][1] == "predmet-A"
    assert seen["tmp_sess-1"][1] is None, "the tmp_ request must not inherit a case"
