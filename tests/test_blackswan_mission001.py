# -*- coding: utf-8 -*-
"""
Regression tests — Operation Black Swan, Mission 001 ("The Day Everything Goes Wrong").

Covers the code fixes applied directly by the mission's fix cycle (see
docs/blackswan/BLACK_SWAN_REPORT.md and docs/architecture/ARCHITECTURAL_DEBT_REGISTER.md
for the full findings ledger). Pure unit tests, no live Supabase/OpenAI/Pinecone.
"""
import asyncio
import json
import os
import sys
import threading
from datetime import date as _date, timedelta as _td
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



# BETA-DEADLINE-DOMAIN-001 (2026-08-14): rokovi se vise ne citaju iz nepostojece
# tabele `rokovi` nego iz kanonskog vlasnika `predmet_hronologija`. Lazni lanac
# ispod STVARNO primenjuje opseg po `datum_iso` -- bez toga bi isti red ispao i
# kao propusten i kao nadolazeci, pa test ne bi merio ono sto tvrdi.
def _hronologija_chain(redovi):
    stanje = {}

    class _C:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def order(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def gte(self, k, v):
            stanje["gte"] = v
            return self

        def lte(self, k, v):
            stanje["lte"] = v
            return self

        def execute(self):
            izlaz = [
                r for r in redovi
                if (not stanje.get("gte") or str(r["datum_iso"]) >= stanje["gte"])
                and (not stanje.get("lte") or str(r["datum_iso"]) <= stanje["lte"])
            ]
            return MagicMock(data=izlaz)
    return _C()


def _chain(execute_return=None, execute_side_effect=None):
    m = MagicMock()
    for method in ("select", "eq", "neq", "insert", "update", "delete", "limit", "order",
                   "is_", "in_", "gte", "lte", "lt", "gt", "like", "maybe_single", "not_"):
        setattr(m, method, MagicMock(return_value=m))
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
# BLACKSWAN-CRIT-001 — routers/billing.py::faktura_create orphan-invoice rollback
# ═══════════════════════════════════════════════════════════════════════════

def _faktura_body():
    from routers.billing import FakturaReq
    return FakturaReq(predmet_id="p1", entry_ids=["e1"], klijent_naziv="Klijent D.O.O.", pdv_stopa=20)


def test_faktura_create_rolls_back_on_billing_entries_update_exception():
    import routers.billing as billing

    entries_chain = _chain(MagicMock(data=[{"id": "e1", "predmet_id": "p1", "iznos_rsd": 1000, "obracunato": False}]))
    broj_select_chain = _chain(MagicMock(data=[]))
    insert_ok_chain = _chain(MagicMock(data=[{"id": "f1", "broj_fakture": "2026/0001"}]))
    delete_chain = _chain(MagicMock(data=[{"id": "f1"}]))

    class _FakturaTable:
        select = broj_select_chain.select
        eq = broj_select_chain.eq
        like = broj_select_chain.like
        order = broj_select_chain.order
        limit = broj_select_chain.limit
        execute = broj_select_chain.execute

        @staticmethod
        def insert(_row):
            return insert_ok_chain

        @staticmethod
        def delete():
            return delete_chain

    be_calls = {"n": 0}

    def _table(name):
        if name == "billing_entries":
            be_calls["n"] += 1
            if be_calls["n"] == 1:
                return entries_chain
            return _chain(execute_side_effect=ConnectionError("blip"))
        if name == "fakture":
            return _FakturaTable
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(billing, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(billing.faktura_create(_faktura_body(), _req(), {"user_id": "u1", "email": "a@b.com"}))

    assert exc.value.status_code == 500
    assert delete_chain.execute.called  # compensating rollback attempted


@pytest.mark.anyio
async def test_reap_orphan_fakture_deletes_zero_linked_entry_drafts():
    import routers.billing as billing

    candidates_chain = _chain(MagicMock(data=[
        {"id": "f-orphan", "user_id": "u1", "broj_fakture": "2026/0002", "created_at": "2020-01-01T00:00:00Z"},
    ]))
    be_check_chain = _chain(MagicMock(data=[]))  # zero linked entries -> genuine orphan
    delete_chain = _chain(MagicMock(data=[{"id": "f-orphan"}]))

    call_n = {"n": 0}

    def _table(name):
        if name == "fakture":
            call_n["n"] += 1
            return candidates_chain if call_n["n"] == 1 else delete_chain
        if name == "billing_entries":
            return be_check_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(billing, "_get_supa", return_value=supa):
        result = await billing.reap_orphan_fakture()

    assert result["checked"] == 1
    assert result["reaped"] == 1
    assert delete_chain.execute.called


@pytest.mark.anyio
async def test_reap_orphan_fakture_skips_rows_with_linked_entries():
    import routers.billing as billing

    candidates_chain = _chain(MagicMock(data=[
        {"id": "f-real", "user_id": "u1", "broj_fakture": "2026/0003", "created_at": "2020-01-01T00:00:00Z"},
    ]))
    be_check_chain = _chain(MagicMock(data=[{"id": "entry1"}]))  # HAS a linked entry -> not orphan

    def _table(name):
        if name == "fakture":
            return candidates_chain
        if name == "billing_entries":
            return be_check_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(billing, "_get_supa", return_value=supa):
        result = await billing.reap_orphan_fakture()

    assert result["checked"] == 1
    assert result["reaped"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-CRIT-002 — overdue deadline handling (3 code copies)
# ═══════════════════════════════════════════════════════════════════════════

def test_risk_engine_treats_overdue_hearing_as_critical_not_absent():
    from services.risk_engine import calculate_procesni_rizik
    from datetime import date, timedelta

    overdue_datum = (date.today() - timedelta(days=5)).isoformat()
    upcoming_datum = (date.today() + timedelta(days=25)).isoformat()

    r_overdue = calculate_procesni_rizik(
        dokazi=[{"snaga": "jaka"}] * 3, dokumenti=[], rocista=[{"datum": overdue_datum}],
        tip_predmeta="parnicno", expected_docs={"parnicno": [], "ostalo": []},
    )
    r_upcoming = calculate_procesni_rizik(
        dokazi=[{"snaga": "jaka"}] * 3, dokumenti=[], rocista=[{"datum": upcoming_datum}],
        tip_predmeta="parnicno", expected_docs={"parnicno": [], "ostalo": []},
    )

    assert r_overdue["zakasneli_rokovi"] == 1
    assert r_overdue["kriticni_rokovi"] == 1
    # The whole point of the bug: overdue must NOT score identically to "safely upcoming".
    assert r_overdue["health_score"] < r_upcoming["health_score"]
    assert r_upcoming["zakasneli_rokovi"] == 0


@pytest.mark.anyio
async def test_case_evolution_keeps_overdue_hearing_in_target_actions():
    import services.event_bus  # noqa: F401 -- primes sys.modules to avoid a circular-import
    import services.case_evolution as ce
    from datetime import date, timedelta

    overdue_datum = (date.today() - timedelta(days=5)).isoformat()
    rok_data = [{"id": "r1", "sud": "Osnovni sud", "datum": overdue_datum, "status": "zakazano"}]

    dokazi_chain = _chain(MagicMock(data=[]))
    dok_chain = _chain(MagicMock(data=[]))
    rok_chain = _chain(MagicMock(data=rok_data))

    def _table(name):
        if name == "rocista":
            return rok_chain
        if name == "predmet_dokazi":
            return dokazi_chain
        return dok_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch.object(ce, "_get_supa", return_value=supa), \
         patch("services.risk_engine.identify_case_problems", return_value=[]):
        actions = await ce._compute_target_actions("p1")

    rociste_actions = [a for a in actions if a.get("dokaz", {}).get("rociste_id") == "r1"]
    assert len(rociste_actions) == 1
    assert rociste_actions[0]["prioritet"] == "critical"
    assert "PROPUŠTENO" in rociste_actions[0]["razlog"]


@pytest.mark.anyio
async def test_morning_briefing_surfaces_missed_deadlines():
    import routers.morning_briefing as mb

    korisnik = {"id": "u1", "email": "u1@x.rs"}
    _propusten_datum = (_date.today() - _td(days=30)).isoformat()
    propusteni_rok = {"id": "rok1", "dogadjaj": "Odgovor na tužbu",
                      "datum_iso": _propusten_datum, "vaznost": "kritičan",
                      "predmet_id": "p1", "akter": ""}

    def _table(name):
        if name == "predmet_hronologija":
            return _hronologija_chain([propusteni_rok])
        if name == "rocista":
            return _chain(MagicMock(data=[]))
        if name == "predmeti":
            return _chain(MagicMock(data=[]))
        if name == "klijenti":
            return _chain(MagicMock(data=[]))
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    async def _fake_log_action(*a, **k):
        return None

    # CI-RED-003 (2026-08-08): this test used to mock NOTHING here and issued a
    # real, billed gpt-4o request on every run -- passing locally only because
    # the developer's .env holds a live key, and 401'ing in CI. Worse, its final
    # assertion ("propušten" in ai_briefing) depended on the exact wording gpt-4o
    # chose at temperature 0.4, so it could fail at random with a valid key too.
    #
    # The real question is whether the missed-deadline data REACHES the narrative
    # step. Capture the prompt and assert on that -- deterministic, offline, and
    # a strictly stronger claim than pattern-matching a model's paraphrase.
    _sent = {}

    def _fake_ai(client, **kwargs):
        _sent.update(kwargs)
        resp = MagicMock()
        resp.choices[0].message.content = "Dan pred vama traži pažnju."
        return resp

    with patch.object(mb, "_get_supa", return_value=supa), \
         patch.object(mb, "_pozovi_briefing_sync_api", new=_fake_ai), \
         patch("shared.audit_immutable.log_action", new=_fake_log_action):
        briefing = await mb._generiši_briefing("u1", supa)

    assert briefing["statistike"]["rokova_propustenih"] == 1
    assert any(r["naziv"] == "Odgovor na tužbu" for r in briefing["rokovi_propusteni"])

    _prompt = _sent["messages"][0]["content"]
    assert "PROPUŠTENI" in _prompt
    assert "Odgovor na tužbu" in _prompt, "the missed deadline must reach the narrative step"


@pytest.mark.anyio
async def test_morning_briefing_survives_an_openai_outage():
    """CI-RED-003: gpt-4o writes exactly ONE decorative opening sentence here;
    every other section is computed deterministically before the call. The call
    had no except path, so an outage, an exhausted @llm_retry, or an expired key
    500'd the whole briefing -- taking the missed-deadline warning, the one
    time-critical part of the screen, down with it."""
    import routers.morning_briefing as mb

    _propusten_datum = (_date.today() - _td(days=30)).isoformat()
    propusteni_rok = {"id": "rok1", "dogadjaj": "Odgovor na tužbu",
                      "datum_iso": _propusten_datum, "vaznost": "kritičan",
                      "predmet_id": "p1", "akter": ""}

    def _table(name):
        if name == "predmet_hronologija":
            return _hronologija_chain([propusteni_rok])
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    async def _fake_log_action(*a, **k):
        return None

    def _boom(client, **kwargs):
        raise RuntimeError("openai is down")

    with patch.object(mb, "_get_supa", return_value=supa), \
         patch.object(mb, "_pozovi_briefing_sync_api", new=_boom), \
         patch("shared.audit_immutable.log_action", new=_fake_log_action):
        briefing = await mb._generiši_briefing("u1", supa)

    # Delivered, not raised — and the deterministic payload is intact.
    assert briefing["statistike"]["rokova_propustenih"] == 1
    assert any(r["naziv"] == "Odgovor na tužbu" for r in briefing["rokovi_propusteni"])
    # The fallback opening must still lead with what the lawyer has to act on.
    assert "propušten" in briefing["ai_briefing"].lower()


def test_notifications_generates_rok_propusten_type():
    from routers.notifications import NOTIF_TIPOVI
    assert "rok_propusten" in NOTIF_TIPOVI
    assert NOTIF_TIPOVI["rok_propusten"]["priority"] == "urgent"


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-EVT-001 — event_bus pre-process claim heartbeat
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_dispatch_pending_events_heartbeats_before_processing_current_row():
    import services.event_bus as eb

    rows = [{"id": "evt-1", "event_type": "GENOME_UPDATED", "user_id": "u1", "predmet_id": "p1",
             "payload": {}, "correlation_id": None, "dispatch_attempts": 0}]
    rpc_chain = _chain(MagicMock(data=rows))
    events_table_chain = _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.rpc.return_value = rpc_chain
    supa.table.return_value = events_table_chain

    async def _fake_publish(event):
        # At the moment the handler runs, a pre-process heartbeat update() must
        # already have fired for this row (not just the post-row heartbeat for
        # OTHER remaining rows).
        assert events_table_chain.update.called

    with patch("shared.deps._get_supa", return_value=supa), \
         patch.object(eb.bus, "publish_async", new=_fake_publish):
        await eb.dispatch_pending_events(batch_size=50)


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-001 — _get_supa() thread-safe singleton
# ═══════════════════════════════════════════════════════════════════════════

def test_get_supa_thread_safe_single_client_created():
    import shared.deps as deps

    deps._supa = None
    call_count = {"n": 0}

    def _slow_create_client(*a, **k):
        import time
        call_count["n"] += 1
        time.sleep(0.02)
        return MagicMock()

    with patch.object(deps, "create_client", side_effect=_slow_create_client), \
         patch.object(deps, "SUPABASE_URL", "https://x.supabase.co"), \
         patch.object(deps, "SUPABASE_SERVICE_KEY", "fake-key"):
        threads = [threading.Thread(target=deps._get_supa) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert call_count["n"] == 1
    deps._supa = None  # reset for other tests


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-002 — update_kanban_faza optimistic-concurrency guard
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kanban_faza_rejects_stale_if_faza():
    import api

    update_chain = _chain(MagicMock(data=[]))  # 0 rows updated -> conflict
    exists_chain = _chain(MagicMock(data={"id": "p1"}))

    def _table(name):
        return update_chain if not exists_chain.execute.called else exists_chain

    supa = MagicMock()
    supa.table.side_effect = lambda name: update_chain

    # api.py calls `await asyncio.to_thread(_require_auth, authorization)` -- a SYNC
    # function run on a worker thread, not a coroutine.
    def _fake_auth(_authorization):
        return MagicMock(id="u1")

    scope = {"type": "http", "method": "PATCH", "path": "/", "headers": [], "query_string": b"", "app": MagicMock(), "state": MagicMock()}

    async def receive():
        import json as _j
        body = _j.dumps({"kanban_faza": "priprema", "if_faza": "inicijalna_procena"}).encode()
        return {"type": "http.request", "body": body, "more_body": False}

    req = StarletteRequest(scope=scope, receive=receive)

    with patch.object(api, "_get_supa", return_value=supa), \
         patch.object(api, "_require_auth", new=_fake_auth):
        with pytest.raises(HTTPException) as exc:
            await api.update_kanban_faza("p1", req, "Bearer faketoken")

    assert exc.value.status_code in (404, 409)


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-003 — manual Genome refresh coalescing guard
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_refresh_case_dna_rejects_concurrent_call_for_same_predmet():
    from routers import case_dna

    case_dna._genome_refresh_inflight.discard("p-race")
    case_dna._genome_refresh_inflight.add("p-race")
    try:
        with pytest.raises(HTTPException) as exc:
            await case_dna.refresh_case_dna("p-race", _req(), {"user_id": "u1", "email": "a@b.com"})
        assert exc.value.status_code == 409
    finally:
        case_dna._genome_refresh_inflight.discard("p-race")


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-004 — /api/pitanje + stream refund on exception (queue timeout etc.)
# ═══════════════════════════════════════════════════════════════════════════

def test_pitanje_refunds_on_httpexception_from_pokreni():
    import inspect
    import api
    src = inspect.getsource(api.pitanje)
    assert "_credit_consumed" in src
    assert "UsageService.refund" in src


def test_pitanje_stream_refunds_in_except_block():
    import inspect
    import api
    src = inspect.getsource(api.pitanje_stream)
    # The except block inside _event_generator must attempt a refund.
    except_idx = src.rindex("except Exception as _stream_exc:")
    tail = src[except_idx:]
    assert "UsageService.refund" in tail


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-005 — copilot_chat credit refund
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_copilot_chat_refunds_on_handler_exception():
    import routers.copilot as copilot

    async def _boom(*_a, **_k):
        raise RuntimeError("handler crashed")

    class _Req:
        poruka = "zdravo"
        predmet_id = None
        history = []

    with patch.object(copilot, "UsageService") as mock_usage, \
         patch.object(copilot, "_detect_intent", new=_async_val("OSTALO")), \
         patch.object(copilot, "_handle_ostalo", new=_boom):
        mock_usage.consume = _async_none_fn()
        mock_usage.refund = MagicMock(side_effect=_async_none_fn())
        with pytest.raises(RuntimeError):
            await copilot.copilot_chat(_Req(), _req(), {"user_id": "u1", "email": "a@b.com"})
        assert mock_usage.refund.called


def _async_none_fn():
    async def _f(*a, **k):
        return None
    return _f


def _async_val(v):
    async def _f(*a, **k):
        return v
    return _f


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-006 — bulk_promena_statusa race guard
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_bulk_promena_statusa_skips_rows_raced_to_target_status():
    from routers.predmeti_close import bulk_promena_statusa, BulkAkcijaReq

    existing_chain = _chain(MagicMock(data=[{"id": "p1", "status": "zatvoren"}]))
    # The guarded update returns ZERO rows (a concurrent request already flipped
    # status to the target 'aktivan' -- .neq("status","aktivan") excludes it).
    update_chain = _chain(MagicMock(data=[]))

    call_n = {"n": 0}

    def _table(name):
        call_n["n"] += 1
        return existing_chain if call_n["n"] == 1 else update_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("routers.predmeti_close._get_supa", return_value=supa):
        result = await bulk_promena_statusa(
            BulkAkcijaReq(predmet_ids=["p1"], akcija="aktiviranje"), _req(), {"user_id": "u1"}
        )

    assert result["azurirano"] == 0
    assert "preskočeno" in result["poruka"]


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-007 — case_context.py bounded predmet_hronologija/rocista
# ═══════════════════════════════════════════════════════════════════════════

def test_case_context_hronologija_query_is_bounded():
    import inspect
    import shared.case_context as cc
    src = inspect.getsource(cc)
    # Both queries must now specify a limit (not unbounded fetch).
    assert src.count(".limit(50)") >= 2


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-HIGH-008 — kreiraj_predmet retry + reap_missing_pipeline_events
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_reap_missing_pipeline_events_backfills_orphan_predmet():
    import services.event_bus as eb

    preds_chain = _chain(MagicMock(data=[
        {"id": "p-orphan", "user_id": "u1", "naziv": "Test", "tip": "opsti", "created_at": "2020-01-01T00:00:00Z"},
    ]))
    evt_check_chain = _chain(MagicMock(data=[]))  # no existing PREDMET_KREIRAN event
    insert_chain = _chain(MagicMock(data=[{"id": "evt-new"}]))

    call_n = {"n": 0}

    def _table(name):
        if name == "predmeti":
            return preds_chain
        if name == "events":
            call_n["n"] += 1
            return evt_check_chain if call_n["n"] == 1 else insert_chain
        return _chain(MagicMock(data=[]))

    supa = MagicMock()
    supa.table.side_effect = _table

    with patch("shared.deps._get_supa", return_value=supa):
        result = await eb.reap_missing_pipeline_events()

    assert result["checked"] == 1
    assert result["backfilled"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-AI-001/002/003 — GPT output range/enum clamping
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_matter_intel_preflight_clamps_out_of_range_score():
    import routers.matter_intel as mi

    pred_chain = _chain(MagicMock(data=[{"id": "p1", "naziv": "X", "tip": "opsti", "status": "aktivan",
                                          "tuzeni": "", "tuzilac": "", "opis": "", "sud": ""}]))
    empty_chain = _chain(MagicMock(data=[]))

    def _table(name):
        return pred_chain if name == "predmeti" else empty_chain

    supa = MagicMock()
    supa.table.side_effect = _table

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content=json.dumps({
        "status": "spreman", "score": 250, "kategorije": [], "kriticna_upozorenja": [],
        "preporuke": [], "procena_rizika": "test",
    })))]

    class Body:
        tip_radnje = "podnesak"
        datum_radnje = "2026-08-10"
        opis_radnje = ""

    with patch.object(mi, "_get_supa", return_value=supa), \
         patch.object(mi, "_pozovi_matter_intel_api", return_value=fake_resp), \
         patch.object(mi, "UsageService") as mock_usage:
        mock_usage.consume = _async_none_fn()
        result = await mi.preflight_check("p1", Body(), _req(), {"user_id": "u1", "email": "a@b.com"})

    assert result["score"] == 100  # clamped from 250


def test_cio_kriticnost_clamped_unconditionally():
    import inspect
    import routers.cio as cio
    src = inspect.getsource(cio)
    assert "BLACKSWAN-AI-002" in src
    assert "max(0, min(100, _k0))" in src


def test_hearing_cc_score_clamped_unconditionally():
    import inspect
    import routers.hearing_cc as hcc
    src = inspect.getsource(hcc)
    assert "BLACKSWAN-AI-003" in src
    assert "max(0, min(100, _score0))" in src


# ═══════════════════════════════════════════════════════════════════════════
# BLACKSWAN-AI-004 — main.py hallucination guard field-scope + ASCII bypass
# ═══════════════════════════════════════════════════════════════════════════

_stashed_mock = sys.modules.pop("main", None)
import main as _m  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# FAZA 6.4.2 — SVI ROKOVI U OVIM FIXTURE-IMA SU POTVRDJENI
#
# Od 6.4.2 nijedan rok ne moze proizvesti izvrsivu posledicu bez eksplicitne
# ljudske potvrde -- ni ljudski, ni deterministicki, ni sistemski. Testovi u
# ovom fajlu ne mere TU granicu (nju meri `test_faza621_provenance_boundary.py`
# i `test_faza64_provenance_contract.py`); oni mere svoje sopstvene ugovore,
# koji su i dalje vazeci.
#
# Zato se ovde modeluje advokat koji je rokove VEC potvrdio. Bez toga bi svaki
# ovaj test padao iz razloga koji nema veze sa onim sto tvrdi.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _rokovi_su_potvrdjeni(monkeypatch):
    import routers.morning_briefing as _m
    if hasattr(_m, "_potvrdjeni_ids"):
        monkeypatch.setattr(_m, "_potvrdjeni_ids", lambda ids: {str(i) for i in ids if i})

del sys.modules["main"]
if _stashed_mock is not None:
    sys.modules["main"] = _stashed_mock


_LONG_CONTEXT_155 = (
    "Zakon o obligacionim odnosima, Član 155: Šteta se nadoknađuje u punom iznosu, "
    "uzimajući u obzir okolnosti nastale posle prouzrokovanja štete, kao i redovnu "
    "vrednost stvari u vreme donošenja sudske odluke. Odgovorno lice dužno je da "
    "uspostavi stanje koje je bilo pre nego što je šteta nastala, ili da isplati "
    "oštećeniku odgovarajuću sumu novca, po njegovom izboru."
)

_LONG_CONTEXT_179 = (
    "Zakon o radu, Član 179: Otkazni rok za slučaj otkaza ugovora o radu od strane "
    "zaposlenog iznosi najmanje 15 dana, a najviše 30 dana. Poslodavac i zaposleni "
    "mogu ugovorom o radu utvrditi duži otkazni rok, u skladu sa opštim aktom, ali "
    "ne duži od 30 dana. Otkazni rok počinje da teče narednog dana od dana dostavljanja."
)


def test_guard_catches_fabricated_article_outside_original_3_fields():
    """Placed in `kada_ne_vazi`, a field the OLD guard_text never scanned."""
    docs = [_LONG_CONTEXT_155]
    raw = json.dumps({
        "statusna_potvrda_status": "ok", "statusna_potvrda_tekst": "test",
        "hijerarhija_izvora": "ZOO", "pravni_zakljucak": "Tužilac ima pravo.",
        "citat_zakona": "Član 155", "pravni_osnov": "ZOO čl. 155",
        "kada_ne_vazi": "Ovo ne vazi po Član 999 koji nije u kontekstu.",
    })
    valid, text = _m._parsiraj_strukturni_odgovor(raw, "PARNICA", docs)
    assert valid is False


def test_guard_catches_ascii_clan_without_diacritic():
    docs = [_LONG_CONTEXT_179]
    valid, razlog = _m._proveri_halucinaciju("Prema Clan 999 ovo je zabranjeno.", docs)
    assert valid is False


def test_guard_still_passes_grounded_ascii_citation():
    docs = [_LONG_CONTEXT_179.replace("Član", "Clan")]
    valid, razlog = _m._proveri_halucinaciju("Prema Clan 179 otkazni rok je 30 dana.", docs)
    assert valid is True
