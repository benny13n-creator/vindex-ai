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


# -----------------------------------------------------------------------------
# NS001/FAZA 3 (BR-005) -- PROMENJENA OCEKIVANJA, NE OSLABLJENA
#
# STARO: `pred_` je bio prihvatljiva sema, a `session_id` je za nju BIO
# `predmeti.id`, pa su c1/c2/c9/c7 merili da se taj predmet_id verno veze kao
# subjekat AI poziva.
#
# NOVO: `pred_` sema je uklonjena iz svih produkcijskih putanja. Dokaz da je
# bila mrtva: nijedan pisac je ne proizvodi; 6 `pred_*` namespace-ova u
# Pinecone-u nema `predmeti.id` kao sufiks; 43 `pred_*` namespace-a iz
# `predmet_dokumenti` ne postoje u Pinecone-u. Grana je mogla da vrati
# iskljucivo 404.
#
# ZASTO OVO NIJE OSLABLJENJE: tvrdnja koju su ovi testovi stitili -- "subjekat
# AI poziva mora biti istinit, nikad izmisljen" -- ne samo da ostaje, nego je
# sada jaca: za `tmp_` subjekat je i dalje NULL (c3), a `pred_` vise uopste ne
# moze da udje. Dodata je i tvrdnja koje ranije nije bilo: vlasnicki namespace
# (`kancelarija_*`/`user_*`) ne sme da prodje ovim putem, jer `extra_namespaces`
# pretraga ide BEZ `rag_acl` filtera.
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_c1_pred_sema_se_vise_ne_prihvata():
    """Bilo `test_c1_pred_success_binds_the_real_predmet_id`."""
    from fastapi import HTTPException
    import routers.dokument as dok

    called = {"n": 0}

    def _must_not_run(*a, **k):
        called["n"] += 1
        return {}

    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", _must_not_run), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        with pytest.raises(HTTPException) as exc:
            await _call(dok, session_id="pred_predmet-A", prefix="pred_")

    assert exc.value.status_code == 422
    assert called["n"] == 0, "provajder je dohvacen za uklonjenu semu"


@pytest.mark.anyio
async def test_c2_prosledjen_prefiks_ne_moze_da_vrati_pred_semu():
    """Bilo `test_c2_pred_failure_carries_the_same_predmet_id`.

    Polje `namespace_prefix` je ranije BIRALO semu. Sada je bez uticaja: cist
    `session_id` uz `namespace_prefix='pred_'` ide kroz `tmp_` put, i subjekat
    ostaje istinit NULL."""
    import routers.dokument as dok

    seen = {}

    def _record(pitanje, history, extra_ns, *a, **k):
        seen["ns"] = extra_ns[0]
        seen["subject"] = _subject()
        return {"status": "success", "data": "x"}

    idx = _index_with({"tmp_sess-9": "x"})
    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", _record), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await _call(dok, session_id="sess-9", prefix="pred_")

    assert seen["ns"] == "tmp_sess-9", seen
    assert seen["subject"][1] is None


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
async def test_c8_tudja_tmp_sesija_nikad_ne_stize_do_provajdera():
    """Bilo `test_c8_unauthorized_predmet_never_reaches_the_provider`.

    Ista tvrdnja, samo nad semom koja je ostala: vektori tudje `tmp_` sesije
    nose `owner_user_id` koji se ne poklapa, pa se pada zatvoreno (404) PRE
    ijednog poziva provajderu."""
    from fastapi import HTTPException
    import routers.dokument as dok

    called = {"n": 0}

    def _must_not_run(*a, **k):
        called["n"] += 1
        return {}

    idx = MagicMock()
    idx.query.return_value = MagicMock(matches=[
        MagicMock(metadata={"owner_user_id": "user-NEKO-DRUGI"})
    ])

    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx), \
         patch("main.ask_agent", _must_not_run), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        with pytest.raises(HTTPException) as exc:
            await _call(dok, session_id="tudja-sesija", prefix="tmp_")

    assert exc.value.status_code == 404
    assert called["n"] == 0, "the provider must never be reached for a foreign session"


@pytest.mark.anyio
async def test_c8b_vlasnicki_namespace_ne_sme_da_udje_ovim_putem():
    """TVRDNJA KOJE RANIJE NIJE BILO.

    `extra_namespaces` pretraga u `app/services/retrieve.py` ide BEZ metadata
    filtera. Da vlasnicki namespace stigne ovim putem, `shared/rag_acl.py`
    kapija bi bila zaobidjena i pozivalac bi dobio doslovan tekst iz predmeta
    koje ne sme ni da otvori."""
    from fastapi import HTTPException
    import routers.dokument as dok

    called = {"n": 0}

    def _must_not_run(*a, **k):
        called["n"] += 1
        return {}

    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("main.ask_agent", _must_not_run), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        for sid in ("kancelarija_k1", "user_u1", "tmp_x", "pred_x"):
            with pytest.raises(HTTPException) as exc:
                await _call(dok, session_id=sid, prefix="tmp_")
            assert exc.value.status_code == 422, sid
    assert called["n"] == 0


@pytest.mark.anyio
async def test_c9_the_subject_does_not_survive_the_endpoint():
    import routers.dokument as dok

    idx = _index_with({"tmp_sess-1": "x"})
    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", lambda *a, **k: {"status": "success", "data": "x"}), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await _call(dok, session_id="sess-1", prefix="tmp_")

    assert _subject()[1] is None, "predmet_id must not outlive the endpoint"


@pytest.mark.anyio
async def test_c7_parallel_requests_cross_neither_namespace_nor_subject():
    """Dva paralelna `tmp_` zahteva. Nijedan ne sme da vidi tudji namespace ni
    tudji subjekat, i oba subjekta ostaju NULL."""
    import routers.dokument as dok

    seen = {}

    def _record(pitanje, history, extra_ns, *a, **k):
        seen[extra_ns[0]] = _subject()
        return {"status": "success", "data": "x"}

    idx = _index_with({"tmp_sess-1": "x", "tmp_sess-2": "y"})
    with patch.object(dok, "_get_supa", return_value=_owned_supa()), \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=idx), \
         patch("uploaded_doc.session.validate_session", return_value=True), \
         patch("main.ask_agent", _record), \
         patch("shared.usage.UsageService.consume", new=AsyncMock(return_value=9)):
        await asyncio.gather(
            _call(dok, session_id="sess-1", prefix="tmp_"),
            _call(dok, session_id="sess-2", prefix="tmp_"),
        )

    assert set(seen) == {"tmp_sess-1", "tmp_sess-2"}, seen
    assert seen["tmp_sess-1"][1] is None
    assert seen["tmp_sess-2"][1] is None
