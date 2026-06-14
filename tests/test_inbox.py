# -*- coding: utf-8 -*-
"""
Tests for routers/inbox.py — Unified Inbox (Vindex OS PRIORITET 3).
All tests run without live Supabase (mocked with table-name routing).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type":"http","method":"GET","headers":[],"query_string":b"","path":"/api/inbox",
             "app":MagicMock(),"state":MagicMock()}
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


PID  = "cccc0000-0000-0000-0000-000000000003"
PID2 = "dddd0000-0000-0000-0000-000000000004"


def _make_chain(data):
    chain = MagicMock()
    for attr in ['select','eq','neq','gte','lte','order','limit','execute',
                 'insert','update','delete','is_','in_','desc']:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock(); r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


def _make_supa(predmeti=None, rocista=None, rokovi=None,
               dokumenti=None, billing=None, beleske=None, ist=None):
    """Route by table name — safe for concurrent asyncio.gather calls."""
    supa = MagicMock()
    table_map = {
        "predmeti":            predmeti  or [],
        "rocista":             rocista   or [],
        "predmet_hronologija": rokovi    or [],
        "predmet_dokumenti":   dokumenti or [],
        "billing_entries":     billing   or [],
        "predmet_beleske":     beleske   or [],
        "predmet_istorija":    ist       or [],
    }
    supa.table = MagicMock(side_effect=lambda name: _make_chain(table_map.get(name, [])))
    return supa


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Basic structure
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_returns_required_keys():
    from routers.inbox import unified_inbox
    supa = _make_supa()
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    assert {"stavke","ukupno","kriticno","visok","srednji","nizak"}.issubset(result.keys())


@pytest.mark.anyio
async def test_inbox_empty_returns_zeros():
    from routers.inbox import unified_inbox
    supa = _make_supa()
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    assert result["ukupno"]   == 0
    assert result["kriticno"] == 0
    assert result["stavke"]   == []


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Ročišta items
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_rociste_today_is_kriticno():
    from routers.inbox import unified_inbox
    from datetime import date
    today = date.today().isoformat()
    preds = [{"id": PID, "naziv": "Test", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocs  = [{"id": "r1", "predmet_id": PID, "sud": "Viši sud", "datum": today, "vreme": "10:00:00", "status": "zakazano"}]
    supa  = _make_supa(predmeti=preds, rocista=rocs)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    roc_items = [i for i in result["stavke"] if i["tip"] == "rociste"]
    assert len(roc_items) == 1
    assert roc_items[0]["prioritet"] == "kriticno"
    assert roc_items[0]["naslov"] == "Ročište — Viši sud"
    assert result["kriticno"] == 1


@pytest.mark.anyio
async def test_inbox_rociste_future_is_visok():
    from routers.inbox import unified_inbox
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=6)).isoformat()
    preds  = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocs   = [{"id": "r1", "predmet_id": PID, "sud": "Sud", "datum": future, "vreme": "09:00:00", "status": "zakazano"}]
    supa   = _make_supa(predmeti=preds, rocista=rocs)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    roc_items = [i for i in result["stavke"] if i["tip"] == "rociste"]
    assert roc_items[0]["prioritet"] == "visok"


@pytest.mark.anyio
async def test_inbox_rociste_naziv_predmeta_resolved():
    from routers.inbox import unified_inbox
    from datetime import date
    today = date.today().isoformat()
    preds = [{"id": PID, "naziv": "Moj predmet", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocs  = [{"id": "r1", "predmet_id": PID, "sud": "S", "datum": today, "vreme": "09:00", "status": "zakazano"}]
    supa  = _make_supa(predmeti=preds, rocista=rocs)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    item = result["stavke"][0]
    assert item["predmet_naziv"] == "Moj predmet"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Rok items
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_rok_kritican_prioritet():
    from routers.inbox import unified_inbox
    from datetime import date
    today = date.today().isoformat()
    rokovi = [{"predmet_id": PID, "dogadjaj": "Rok za žalbu", "datum_iso": today, "vaznost": "kritičan"}]
    supa   = _make_supa(rokovi=rokovi)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    rok_items = [i for i in result["stavke"] if i["tip"] == "rok"]
    assert len(rok_items) == 1
    assert rok_items[0]["prioritet"] == "kriticno"


@pytest.mark.anyio
async def test_inbox_rok_bitan_is_visok():
    from routers.inbox import unified_inbox
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=5)).isoformat()
    rokovi = [{"predmet_id": PID, "dogadjaj": "Rok", "datum_iso": future, "vaznost": "bitan"}]
    supa   = _make_supa(rokovi=rokovi)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    rok_items = [i for i in result["stavke"] if i["tip"] == "rok"]
    assert rok_items[0]["prioritet"] == "visok"


@pytest.mark.anyio
async def test_inbox_rok_ordinary_is_srednji():
    from routers.inbox import unified_inbox
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=6)).isoformat()
    rokovi = [{"predmet_id": PID, "dogadjaj": "Rok", "datum_iso": future, "vaznost": "normalan"}]
    supa   = _make_supa(rokovi=rokovi)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    rok_items = [i for i in result["stavke"] if i["tip"] == "rok"]
    assert rok_items[0]["prioritet"] == "srednji"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Dokument items
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_dokument_is_srednji():
    from routers.inbox import unified_inbox
    docs = [{"id": "d1", "predmet_id": PID, "naziv_fajla": "ugovor.pdf", "created_at": "2026-06-14T10:00:00"}]
    supa = _make_supa(dokumenti=docs)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    doc_items = [i for i in result["stavke"] if i["tip"] == "dokument"]
    assert len(doc_items) == 1
    assert doc_items[0]["prioritet"] == "srednji"
    assert doc_items[0]["naslov"] == "ugovor.pdf"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Billing / naplata items
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_naplata_is_nizak():
    from routers.inbox import unified_inbox
    billing = [{"id": "b1", "predmet_id": PID, "opis": "Konsultacija", "iznos_rsd": 5000, "datum": "2026-05-01"}]
    supa    = _make_supa(billing=billing)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    nap_items = [i for i in result["stavke"] if i["tip"] == "naplata"]
    assert len(nap_items) == 1
    assert nap_items[0]["prioritet"] == "nizak"
    assert "5" in nap_items[0]["opis"]  # contains the amount


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Neaktivni predmeti
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_neaktivan_predmet_detected():
    from routers.inbox import unified_inbox
    preds = [{"id": PID, "naziv": "Star predmet", "status": "aktivan", "updated_at": "2026-01-01"}]
    supa  = _make_supa(predmeti=preds)  # beleske=[], ist=[] by default
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    nei_items = [i for i in result["stavke"] if i["tip"] == "neaktivan"]
    assert len(nei_items) == 1
    assert nei_items[0]["predmet_id"] == PID
    assert nei_items[0]["prioritet"] == "nizak"


@pytest.mark.anyio
async def test_inbox_active_predmet_not_neaktivan():
    from routers.inbox import unified_inbox
    preds   = [{"id": PID, "naziv": "Aktivan predmet", "status": "aktivan", "updated_at": "2026-06-01"}]
    beleske = [{"predmet_id": PID}]
    supa    = _make_supa(predmeti=preds, beleske=beleske)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    nei_items = [i for i in result["stavke"] if i["tip"] == "neaktivan"]
    assert len(nei_items) == 0


@pytest.mark.anyio
async def test_inbox_zatvoren_predmet_not_neaktivan():
    from routers.inbox import unified_inbox
    preds = [{"id": PID, "naziv": "Zatvoren", "status": "zatvoren", "updated_at": "2025-01-01"}]
    supa  = _make_supa(predmeti=preds)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    nei_items = [i for i in result["stavke"] if i["tip"] == "neaktivan"]
    assert len(nei_items) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Sorting
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_sorted_kriticno_first():
    from routers.inbox import unified_inbox
    from datetime import date
    today = date.today().isoformat()
    preds   = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    billing = [{"id": "b1", "predmet_id": PID, "opis": "Usluga", "iznos_rsd": 1000, "datum": "2026-01-01"}]
    rokovi  = [{"predmet_id": PID, "dogadjaj": "Kritičan rok", "datum_iso": today, "vaznost": "kritičan"}]
    supa    = _make_supa(predmeti=preds, rokovi=rokovi, billing=billing)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    items = result["stavke"]
    assert len(items) >= 2
    assert items[0]["prioritet"] == "kriticno"


@pytest.mark.anyio
async def test_inbox_counts_match_stavke():
    from routers.inbox import unified_inbox
    from datetime import date
    today = date.today().isoformat()
    preds   = [{"id": PID, "naziv": "P", "status": "aktivan", "updated_at": "2026-01-01"}]
    rocs    = [{"id": "r1", "predmet_id": PID, "sud": "S", "datum": today, "vreme": "10:00", "status": "zakazano"}]
    billing = [{"id": "b1", "predmet_id": PID, "opis": "Usluga", "iznos_rsd": 1000, "datum": "2026-01-01"}]
    supa    = _make_supa(predmeti=preds, rocista=rocs, billing=billing)
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    total = result["kriticno"] + result["visok"] + result["srednji"] + result["nizak"]
    assert total == result["ukupno"]
    assert result["ukupno"] == len(result["stavke"])


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Exception safety
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_inbox_handles_exceptions():
    from routers.inbox import unified_inbox
    supa = MagicMock()
    supa.table.side_effect = Exception("DB error")
    with patch("routers.inbox._get_supa", return_value=supa):
        result = await unified_inbox(request=_req(), user=_user())
    assert result["ukupno"] == 0
    assert result["stavke"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Router registration
# ═══════════════════════════════════════════════════════════════════════════════

def test_inbox_router_path():
    from routers.inbox import router
    paths = [r.path for r in router.routes]
    assert "/api/inbox" in paths


def test_inbox_router_tags():
    from routers.inbox import router
    assert "inbox" in router.tags
