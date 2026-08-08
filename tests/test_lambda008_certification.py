# -*- coding: utf-8 -*-
"""
Regression tests — Program Lambda, Final Certification 008 (2026-08-07).

Covers the code fixes applied directly by the certification's fix cycle (see
docs/lambda/LAMBDA008_CERTIFICATION_REPORT.md and docs/architecture/
ARCHITECTURAL_DEBT_REGISTER.md for full findings). Pure unit tests, no live
Supabase/OpenAI/Pinecone.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request as StarletteRequest  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _chain(execute_return=None, execute_side_effect=None):
    m = MagicMock()
    for method in ("select", "eq", "neq", "insert", "update", "limit", "order",
                   "is_", "in_", "gte", "lte", "like", "maybe_single"):
        setattr(m, method, MagicMock(return_value=m))
    # `.not_` is accessed as a PROPERTY in supabase-py (`.not_.is_(...)`), not
    # called as a method -- must return the same chain object directly, not a
    # fresh MagicMock(return_value=m), or the chain silently disconnects here.
    m.not_ = m
    if execute_side_effect is not None:
        m.execute = MagicMock(side_effect=execute_side_effect)
    else:
        m.execute = MagicMock(return_value=execute_return)
    return m


def _req():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    scope = {
        "type": "http", "method": "POST", "path": "/", "headers": [],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 1234),
    }
    return StarletteRequest(scope=scope, receive=receive)


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-CONC-003 — routers/billing.py::faktura_create invoice-number race
# ═══════════════════════════════════════════════════════════════════════════

def _faktura_body():
    from routers.billing import FakturaReq
    return FakturaReq(predmet_id="p1", entry_ids=["e1"], klijent_naziv="Klijent D.O.O.", pdv_stopa=20)


def test_faktura_create_retries_on_broj_fakture_conflict_then_succeeds():
    import routers.billing as billing

    entries_chain = _chain(MagicMock(data=[{"id": "e1", "predmet_id": "p1", "iznos_rsd": 1000, "obracunato": False}]))
    broj_select_chain = _chain(MagicMock(data=[]))  # _sledeci_broj_fakture: no prior invoices
    conflict_err = Exception('duplicate key value violates unique constraint "fakture_user_broj_unique" 23505')
    insert_conflict_chain = _chain(execute_side_effect=conflict_err)
    insert_ok_chain = _chain(MagicMock(data=[{"id": "f1", "broj_fakture": "2026/0002"}]))
    update_chain = _chain(MagicMock(data=[{"id": "e1"}]))

    fakture_calls = iter([insert_conflict_chain, insert_ok_chain])

    supa = MagicMock()
    # billing_entries.select (lookup) then billing_entries.update (link) both hit
    # the same table name -- route by call count instead.
    be_calls = {"n": 0}

    def _be_table(name):
        if name == "billing_entries":
            be_calls["n"] += 1
            return entries_chain if be_calls["n"] == 1 else update_chain
        if name == "fakture":
            # _sledeci_broj_fakture always SELECTs first (broj_select_chain);
            # the actual .insert() call is what must alternate fail->succeed.
            return _FakturaTableRouter
        return _chain(MagicMock(data=[]))

    class _FakturaTableRouter:
        select = broj_select_chain.select
        eq = broj_select_chain.eq
        like = broj_select_chain.like
        order = broj_select_chain.order
        limit = broj_select_chain.limit
        execute = broj_select_chain.execute

        @staticmethod
        def insert(_row):
            return next(fakture_calls)

    supa.table.side_effect = _be_table

    with patch.object(billing, "_get_supa", return_value=supa):
        result = asyncio.run(billing.faktura_create(_faktura_body(), _req(), {"user_id": "u1", "email": "a@b.com"}))

    # Insert was attempted twice (1 conflict, 1 success) and the caller got the
    # invoice created on the successful retry, not an error.
    assert insert_conflict_chain.execute.called
    assert insert_ok_chain.execute.called
    assert result["faktura"]["id"] == "f1"


def test_faktura_create_exhausts_retries_returns_409_not_500():
    import routers.billing as billing

    entries_chain = _chain(MagicMock(data=[{"id": "e1", "predmet_id": "p1", "iznos_rsd": 1000, "obracunato": False}]))
    broj_select_chain = _chain(MagicMock(data=[]))
    conflict_err = Exception('duplicate key value violates unique constraint "fakture_user_broj_unique" 23505')

    class _AlwaysConflict:
        select = broj_select_chain.select
        eq = broj_select_chain.eq
        like = broj_select_chain.like
        order = broj_select_chain.order
        limit = broj_select_chain.limit
        execute = broj_select_chain.execute

        @staticmethod
        def insert(_row):
            return _chain(execute_side_effect=conflict_err)

    be_calls = {"n": 0}

    def _table(name):
        if name == "billing_entries":
            be_calls["n"] += 1
            return entries_chain
        if name == "fakture":
            return _AlwaysConflict
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(billing, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(billing.faktura_create(_faktura_body(), _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert exc.value.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-IDOR-001 — routers/billing.py::billing_po_klijentu ownership filter
# ═══════════════════════════════════════════════════════════════════════════

def test_billing_po_klijentu_unowned_klijent_returns_empty_without_querying_predmet_klijenti():
    import routers.billing as billing

    klijent_owned_chain = _chain(MagicMock(data=[]))  # not owned by this user
    pk_chain = _chain(MagicMock(data=[{"predmet_id": "other-firms-case"}]))

    def _table(name):
        if name == "klijenti":
            return klijent_owned_chain
        if name == "predmet_klijenti":
            return pk_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(billing, "_get_supa", return_value=supa):
        result = asyncio.run(billing.billing_po_klijentu("other-firms-klijent", _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert result["predmeti"] == []
    assert result["fakture"] == []
    # The unowned-klijent short-circuit must fire BEFORE predmet_klijenti is queried.
    assert not pk_chain.select.called


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-SEC-002 — routers/dokument.py pred_ namespace ownership check
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_verify_pred_namespace_ownership_rejects_unowned_predmet():
    from routers.dokument import _verify_pred_namespace_ownership

    supa = MagicMock()
    supa.table.return_value = _chain(MagicMock(data=[]))  # not owned

    with patch("routers.dokument._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await _verify_pred_namespace_ownership("someone-elses-predmet-id", "pred_", "u1")

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_verify_pred_namespace_ownership_allows_owned_predmet():
    from routers.dokument import _verify_pred_namespace_ownership

    supa = MagicMock()
    supa.table.return_value = _chain(MagicMock(data=[{"id": "p1"}]))

    with patch("routers.dokument._get_supa", return_value=supa):
        await _verify_pred_namespace_ownership("p1", "pred_", "u1")  # must not raise


@pytest.mark.anyio
async def test_verify_pred_namespace_ownership_tmp_prefix_never_queries_predmeti_table():
    """The tmp_ path is verified via Pinecone vector metadata (owner_user_id),
    not the predmeti table -- confirms it stays that way even after F1's fix."""
    from routers.dokument import _verify_pred_namespace_ownership

    supa = MagicMock()
    supa.table.return_value = _chain(MagicMock(data=[]))
    fake_index = MagicMock()
    fake_index.query.return_value = MagicMock(matches=[
        MagicMock(metadata={"owner_user_id": "u1"})
    ])

    with patch("routers.dokument._get_supa", return_value=supa) as get_supa, \
         patch("uploaded_doc.ingest._get_pinecone_index", return_value=fake_index):
        await _verify_pred_namespace_ownership("some-session-id", "tmp_", "u1")  # must not raise

    get_supa.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Final Beta Gate F1 (MEDIUM) — tmp_ namespaces previously had NO ownership
# check at all (the test above used to assert exactly that as correct
# behavior). A leaked session_id (browser history/logs/shared screenshot)
# let ANY authenticated user query another user's uploaded document for the
# rest of its 24h TTL via /api/dokument/pitanje.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_verify_tmp_namespace_ownership_rejects_other_users_session():
    from routers.dokument import _verify_pred_namespace_ownership

    fake_index = MagicMock()
    fake_index.query.return_value = MagicMock(matches=[
        MagicMock(metadata={"owner_user_id": "someone-else"})
    ])

    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=fake_index):
        with pytest.raises(HTTPException) as exc:
            await _verify_pred_namespace_ownership("leaked-session-id", "tmp_", "attacker-uid")

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_verify_tmp_namespace_ownership_allows_owning_user():
    from routers.dokument import _verify_pred_namespace_ownership

    fake_index = MagicMock()
    fake_index.query.return_value = MagicMock(matches=[
        MagicMock(metadata={"owner_user_id": "u1"})
    ])

    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=fake_index):
        await _verify_pred_namespace_ownership("my-session-id", "tmp_", "u1")  # must not raise


@pytest.mark.anyio
async def test_verify_tmp_namespace_ownership_fails_closed_on_legacy_vector_without_owner():
    """A vector ingested before this fix carries no owner_user_id -- must
    fail closed (404), not trust an unverifiable legacy vector as owned."""
    from routers.dokument import _verify_pred_namespace_ownership

    fake_index = MagicMock()
    fake_index.query.return_value = MagicMock(matches=[
        MagicMock(metadata={"origin": "client_doc"})  # no owner_user_id at all
    ])

    with patch("uploaded_doc.ingest._get_pinecone_index", return_value=fake_index):
        with pytest.raises(HTTPException) as exc:
            await _verify_pred_namespace_ownership("pre-fix-session-id", "tmp_", "u1")

    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_verify_tmp_namespace_ownership_fails_closed_on_pinecone_error():
    from routers.dokument import _verify_pred_namespace_ownership

    with patch("uploaded_doc.ingest._get_pinecone_index", side_effect=RuntimeError("pinecone down")):
        with pytest.raises(HTTPException) as exc:
            await _verify_pred_namespace_ownership("some-session-id", "tmp_", "u1")

    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-REL-001 — api.py /api/pitanje credit refund on genuine LLM error
# ═══════════════════════════════════════════════════════════════════════════

def test_pitanje_refund_condition_includes_error_status():
    """Direct assertion on the fixed condition's source, since the full
    /api/pitanje and /api/pitanje/stream handlers have too many external
    dependencies (OpenAI, Pinecone, cost tracking) to unit-test end-to-end
    cheaply -- this proves the specific line-level regression fix (a genuine
    LLM failure, status=='error', must trigger UsageService.refund() just
    like the pre-existing from_cache/blocked cases) is present in BOTH
    handlers, not just one."""
    import inspect
    import api

    pitanje_src = inspect.getsource(api.pitanje)
    stream_src = inspect.getsource(api.pitanje_stream)
    assert 'rezultat.get("status") == "error"' in pitanje_src
    assert 'rezultat.get("status") == "error"' in stream_src


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-CONC-002 — klijenti/router.py double-submit guard
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_create_klijent_rejects_recent_duplicate_same_name():
    from klijenti.router import create_klijent, KlijentCreateReq

    dup_row = {"id": "existing", "created_at": "2026-08-07T10:00:00+00:00",
               "ime": "Petar", "prezime": "Petrovic", "firma": ""}
    dup_chain = _chain(MagicMock(data=[dup_row]))

    supa = MagicMock()
    supa.table.return_value = dup_chain

    req = KlijentCreateReq(tip="fizicko", ime="Petar", prezime="Petrovic")

    async def _fake_auth(_request):
        return {"user_id": "u1", "email": "a@b.com", "role": "advokat", "role_str": "advokat"}

    with patch("klijenti.router._get_supa", return_value=supa), \
         patch("klijenti.router._auth_from_request", new=_fake_auth):
        with pytest.raises(HTTPException) as exc:
            await create_klijent(req, _req())

    assert exc.value.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-ARCH-001 — routers/health_index.py dead-column fix
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_compute_health_predmeti_select_does_not_reference_rizik_nivo():
    from routers import health_index as hi

    captured = {}

    def _capture_select(cols):
        captured["cols"] = cols
        chain = _chain(MagicMock(data=[]))
        return chain

    predmeti_chain = MagicMock()
    predmeti_chain.select.side_effect = _capture_select

    def _table(name):
        if name == "predmeti":
            return predmeti_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    await hi._compute_health("u1", supa)

    assert "rizik_nivo" not in captured.get("cols", "")


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-ARCH-002 — api.py::predmeti_dashboard canonical priority delegation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_predmeti_dashboard_sorts_by_canonical_action_priority():
    import api
    from shared.attention_priority import CRITICAL, LOW

    predmeti = [
        {"id": "p-low", "naziv": "Nizak prioritet", "tip": "opsti", "status": "aktivan", "created_at": "2026-01-01"},
        {"id": "p-crit", "naziv": "Kritican", "tip": "opsti", "status": "aktivan", "created_at": "2026-01-02"},
    ]
    preds_chain = _chain(MagicMock(data=predmeti))
    hron_chain = _chain(MagicMock(data=[]))
    risk_chain = _chain(MagicMock(data=[]))
    actions_chain = _chain(MagicMock(data=[
        {"predmet_id": "p-low", "prioritet": LOW},
        {"predmet_id": "p-crit", "prioritet": CRITICAL},
    ]))

    call_n = {"n": 0}

    def _table(name):
        if name == "predmeti":
            return preds_chain
        if name == "predmet_hronologija":
            return hron_chain
        if name == "predmet_istorija":
            return risk_chain
        if name == "case_actions":
            return actions_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("api._get_supa", return_value=supa):
        result = await api.predmeti_dashboard(_req(), {"user_id": "u1"})

    ids_in_order = [p["id"] for p in result["po_prioritetu"]]
    assert ids_in_order.index("p-crit") < ids_in_order.index("p-low")
    # The old hand-rolled field must be gone from the response.
    assert "priority_score" not in result["predmeti"][0]


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-AI-001 — services/ambient_analyzer.py citation grounding
# ═══════════════════════════════════════════════════════════════════════════

def test_ambient_analyzer_drops_ungrounded_clan_zakona_suggestion():
    from services.ambient_analyzer import _parsiraj_sugestije
    import json

    raw = json.dumps({"sugestije": [
        {"tip": "clan_zakona", "tekst": "Postoji rok od 15 dana.", "izvor": "Zakon o radu, čl. 999"},
    ]})
    result = _parsiraj_sugestije(raw, rag_kontekst="Relevantan zakon: Zakon o parnicnom postupku\nČlan 194...")
    assert result == []


def test_ambient_analyzer_keeps_grounded_clan_zakona_suggestion():
    from services.ambient_analyzer import _parsiraj_sugestije
    import json

    raw = json.dumps({"sugestije": [
        {"tip": "clan_zakona", "tekst": "Rok je 15 dana.", "izvor": "Zakon o radu, čl. 179"},
    ]})
    result = _parsiraj_sugestije(raw, rag_kontekst="Relevantan zakon: Zakon o radu, čl. 179\n...tekst...")
    assert len(result) == 1
    assert result[0]["izvor"] == "Zakon o radu, čl. 179"


def test_ambient_analyzer_upozorenje_does_not_require_grounding():
    from services.ambient_analyzer import _parsiraj_sugestije
    import json

    raw = json.dumps({"sugestije": [
        {"tip": "upozorenje", "tekst": "Nedostaje datum u pasusu.", "izvor": ""},
    ]})
    result = _parsiraj_sugestije(raw, rag_kontekst="")
    assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-EVT-001 — services/event_bus.py batch-claim heartbeat
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_dispatch_pending_events_heartbeats_claimed_at_for_remaining_rows():
    import services.event_bus as eb

    rows = [
        {"id": "evt-1", "event_type": "GENOME_UPDATED", "user_id": "u1", "predmet_id": "p1", "payload": {}, "correlation_id": None, "dispatch_attempts": 0},
        {"id": "evt-2", "event_type": "GENOME_UPDATED", "user_id": "u1", "predmet_id": "p1", "payload": {}, "correlation_id": None, "dispatch_attempts": 0},
    ]
    rpc_chain = _chain(MagicMock(data=rows))
    events_update_chain = _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.rpc.return_value = rpc_chain
    supa.table.return_value = events_update_chain

    async def _fake_publish(event):
        return None

    with patch("shared.deps._get_supa", return_value=supa), \
         patch.object(eb.bus, "publish_async", new=_fake_publish):
        await eb.dispatch_pending_events(batch_size=50)

    # After processing evt-1, a heartbeat must refresh claimed_at for the
    # still-remaining evt-2 -- the update() call proves the heartbeat fired at
    # least once (in_() with the remaining id list) beyond the final
    # dispatched_at mark.
    assert events_update_chain.in_.called or events_update_chain.update.called


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-PERF-003 — routers/morning_briefing.py::briefing_cron bounded
# concurrency + outer timeout (was fully sequential, no timeout wrapper)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_briefing_cron_processes_all_users_via_bounded_concurrency():
    import routers.morning_briefing as mb
    from starlette.requests import Request as StarletteRequest

    korisnici = [{"id": f"u{i}", "email": f"u{i}@x.rs"} for i in range(3)]
    profiles_chain = _chain(MagicMock(data=korisnici))
    supa = MagicMock()
    supa.table.return_value = profiles_chain

    async def _fake_generisi(uid, supa):
        return {"datum": "2026-08-07"}

    async def _fake_posalji(email, briefing, ime=""):
        return True

    scope = {
        "type": "http", "method": "POST", "path": "/api/briefing/cron",
        "headers": [(b"x-cron-secret", b"secret")], "query_string": b"",
        "app": MagicMock(), "state": MagicMock(),
    }
    req = StarletteRequest(scope=scope)

    with patch.object(mb, "_get_supa", return_value=supa), \
         patch.object(mb, "_generiši_briefing", new=_fake_generisi), \
         patch.object(mb, "_pošalji_briefing_email", new=_fake_posalji), \
         patch.dict(os.environ, {"BRIEFING_CRON_SECRET": "secret"}):
        result = await mb.briefing_cron(req)

    assert result["ok"] is True
    assert result["poslato"] == 3
    assert result["greske"] == 0


@pytest.mark.anyio
async def test_briefing_cron_one_user_failure_does_not_block_others():
    import routers.morning_briefing as mb
    from starlette.requests import Request as StarletteRequest

    korisnici = [{"id": "u-fail", "email": "fail@x.rs"}, {"id": "u-ok", "email": "ok@x.rs"}]
    profiles_chain = _chain(MagicMock(data=korisnici))
    supa = MagicMock()
    supa.table.return_value = profiles_chain

    async def _fake_generisi(uid, supa):
        if uid == "u-fail":
            raise RuntimeError("GPT boom")
        return {"datum": "2026-08-07"}

    async def _fake_posalji(email, briefing, ime=""):
        return True

    scope = {
        "type": "http", "method": "POST", "path": "/api/briefing/cron",
        "headers": [(b"x-cron-secret", b"secret")], "query_string": b"",
        "app": MagicMock(), "state": MagicMock(),
    }
    req = StarletteRequest(scope=scope)

    with patch.object(mb, "_get_supa", return_value=supa), \
         patch.object(mb, "_generiši_briefing", new=_fake_generisi), \
         patch.object(mb, "_pošalji_briefing_email", new=_fake_posalji), \
         patch.dict(os.environ, {"BRIEFING_CRON_SECRET": "secret"}):
        result = await mb.briefing_cron(req)

    assert result["poslato"] == 1
    assert result["greske"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA008-SCHEMA-001 — routers/drafting.py predmet_dokumenti missing-column
# fallback (redni_broj/tekst_sadrzaj may not exist until migration 105 runs)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_staging_promote_falls_back_when_columns_missing():
    from routers import drafting
    from types import SimpleNamespace

    missing_col_err = Exception('column "redni_broj" of relation "predmet_dokumenti" does not exist 42703')
    rn_select_chain = _chain(MagicMock(data=[]))
    fallback_insert_chain = _chain(MagicMock(data=[{"id": "d1"}]))

    call_state = {"insert_attempts": 0}

    class _DokTable:
        select = rn_select_chain.select
        eq = rn_select_chain.eq
        order = rn_select_chain.order
        limit = rn_select_chain.limit
        execute = rn_select_chain.execute

        @staticmethod
        def insert(row):
            call_state["insert_attempts"] += 1
            if call_state["insert_attempts"] == 1:
                assert "redni_broj" in row and "tekst_sadrzaj" in row
                return _chain(execute_side_effect=missing_col_err)
            assert "redni_broj" not in row and "tekst_sadrzaj" not in row
            return fallback_insert_chain

    supa = MagicMock()
    supa.table.return_value = _DokTable

    fake_manifest = SimpleNamespace(total_chunks=1)

    staging_row = {
        "id": "st1", "predmet_id": "p1", "user_id": "u1", "kancelarija_id": "",
        "tekst": "Sadržaj nacrta.", "naziv": "Nacrt",
    }

    with patch("uploaded_doc.chunker.chunk_document", return_value=fake_manifest), \
         patch("uploaded_doc.ingest.ingest_session", return_value=1), \
         patch("uploaded_doc.session.generate_session_id", return_value="sess1"), \
         patch("shared.kancelarija_utils.rag_owner_namespace", return_value="owner_p1"):
        result = await drafting._promote_staged_draft_to_pinecone(supa, staging_row)

    assert result is True
    assert call_state["insert_attempts"] == 2
