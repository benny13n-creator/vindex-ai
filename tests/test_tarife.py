# -*- coding: utf-8 -*-
"""
Tests for routers/tarife.py — personalizovane tarife.
All tests run without live Supabase (mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from starlette.requests import Request as StarletteRequest

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/tarife/moja-satnica", method="GET"):
    scope = {
        "type": "http", "method": method, "headers": [],
        "query_string": b"", "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs", "role": "advokat"}


UID = "aaaa0000-0000-0000-0000-000000000001"
KL_ID = "bbbb0000-0000-0000-0000-000000000002"


def _chain(data):
    """Chainable Supabase mock returning data."""
    m = MagicMock()
    result = MagicMock(); result.data = data
    m.table.return_value = m
    m.select.return_value = m
    m.eq.return_value = m
    m.is_.return_value = m
    m.insert.return_value = m
    m.update.return_value = m
    m.delete.return_value = m
    m.maybe_single.return_value = m
    m.limit.return_value = m
    m.execute.return_value = result
    return m, result


# ═══════════════════════════════════════════════════════════════════════════════
# 1. resolve_tarifa
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_resolve_tarifa_aks_default():
    from routers.tarife import resolve_tarifa
    supa, res = _chain(None)
    res.data = None
    satnica = await resolve_tarifa(supa, UID, None)
    assert satnica == 7500.0


@pytest.mark.anyio
async def test_resolve_tarifa_global():
    from routers.tarife import resolve_tarifa
    supa, res = _chain([{"tarifa_po_satu": 6000}])
    satnica = await resolve_tarifa(supa, UID, None)
    assert satnica == 6000.0


@pytest.mark.anyio
async def test_resolve_tarifa_per_klijent():
    from routers.tarife import resolve_tarifa
    supa = MagicMock()
    result_klijent = MagicMock(); result_klijent.data = [{"tarifa_po_satu": 9000}]
    result_global  = MagicMock(); result_global.data  = [{"tarifa_po_satu": 6000}]

    call_count = [0]
    chain_m = MagicMock()
    chain_m.return_value = chain_m
    chain_m.table.return_value = chain_m
    chain_m.select.return_value = chain_m
    chain_m.eq.return_value = chain_m
    chain_m.is_.return_value = chain_m
    chain_m.limit.return_value = chain_m
    chain_m.maybe_single.return_value = chain_m

    def execute_side():
        call_count[0] += 1
        if call_count[0] == 1:
            return result_klijent  # per-klijent query
        return result_global       # global query (should not be reached)

    chain_m.execute.side_effect = execute_side
    supa.table = chain_m.table

    satnica = await resolve_tarifa(supa, UID, KL_ID)
    assert satnica == 9000.0


@pytest.mark.anyio
async def test_resolve_tarifa_falls_back_to_global():
    from routers.tarife import resolve_tarifa
    supa = MagicMock()
    result_none   = MagicMock(); result_none.data   = []
    result_global = MagicMock(); result_global.data = [{"tarifa_po_satu": 8000}]

    call_count = [0]
    chain_m = MagicMock()
    for attr in ['table','select','eq','is_','maybe_single','insert','update','delete','limit']:
        setattr(chain_m, attr, MagicMock(return_value=chain_m))

    def execute_side():
        call_count[0] += 1
        return result_none if call_count[0] == 1 else result_global

    chain_m.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain_m)

    satnica = await resolve_tarifa(supa, UID, KL_ID)
    assert satnica == 8000.0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. resolve_tarifne_stavke
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_resolve_tarifne_stavke_no_custom():
    from routers.tarife import resolve_tarifne_stavke
    supa, res = _chain([])
    result = await resolve_tarifne_stavke(supa, UID)
    assert "T01" in result
    assert result["T01"]["is_custom"] is False
    assert result["T01"]["iznos_rsd"] == 12 * 50  # 600


@pytest.mark.anyio
async def test_resolve_tarifne_stavke_with_custom():
    from routers.tarife import resolve_tarifne_stavke
    supa, res = _chain([{"kod": "T01", "naziv": None, "iznos": 800}])
    result = await resolve_tarifne_stavke(supa, UID)
    assert result["T01"]["is_custom"] is True
    assert result["T01"]["iznos_rsd"] == 800.0
    assert result["T01"]["aks_iznos"] == 600.0


@pytest.mark.anyio
async def test_resolve_tarifne_stavke_custom_naziv():
    from routers.tarife import resolve_tarifne_stavke
    supa, res = _chain([{"kod": "T01", "naziv": "Moja Tužba", "iznos": 750}])
    result = await resolve_tarifne_stavke(supa, UID)
    assert result["T01"]["naziv"] == "Moja Tužba"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. GET /api/tarife/moja-satnica
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_satnica_default():
    from routers.tarife import get_moja_satnica
    supa, res = _chain(None)
    res.data = None
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await get_moja_satnica(_req(), user=_user())
    assert r["tarifa_po_satu"] == 7500.0
    assert r["source"] == "default"


@pytest.mark.anyio
async def test_get_satnica_custom():
    from routers.tarife import get_moja_satnica
    supa, res = _chain([{"tarifa_po_satu": 6000, "updated_at": "2026-01-01"}])
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await get_moja_satnica(_req(), user=_user())
    assert r["tarifa_po_satu"] == 6000.0
    assert r["source"] == "custom"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PUT /api/tarife/moja-satnica
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_put_satnica_insert():
    from routers.tarife import put_moja_satnica, SatnicaReq
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','is_','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))
    none_result = MagicMock(); none_result.data = None
    ok_result   = MagicMock(); ok_result.data   = [{"tarifa_po_satu": 5500}]

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        return none_result if call_count[0] == 1 else ok_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    body = SatnicaReq(tarifa_po_satu=5500)
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await put_moja_satnica(body, _req(method="PUT"), user=_user())
    assert r["ok"] is True
    assert r["tarifa_po_satu"] == 5500.0


@pytest.mark.anyio
async def test_put_satnica_update():
    from routers.tarife import put_moja_satnica, SatnicaReq
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','is_','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))
    exist_result = MagicMock(); exist_result.data = [{"id": "row-1"}]
    ok_result    = MagicMock(); ok_result.data    = [{"tarifa_po_satu": 7000}]

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        return exist_result if call_count[0] == 1 else ok_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    body = SatnicaReq(tarifa_po_satu=7000)
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await put_moja_satnica(body, _req(method="PUT"), user=_user())
    assert r["tarifa_po_satu"] == 7000.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GET /api/tarife/klijent/{klijent_id}
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_klijent_tarifa_custom():
    from routers.tarife import get_klijent_tarifa
    supa, res = _chain([{"tarifa_po_satu": 9000, "updated_at": "2026-01-01"}])
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await get_klijent_tarifa(KL_ID, _req(), user=_user())
    assert r["tarifa_po_satu"] == 9000.0
    assert r["source"] == "custom"
    assert r["klijent_id"] == KL_ID


@pytest.mark.anyio
async def test_get_klijent_tarifa_falls_to_global():
    from routers.tarife import get_klijent_tarifa
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','is_','maybe_single','insert','update','delete','limit']:
        setattr(chain, attr, MagicMock(return_value=chain))
    none_result = MagicMock(); none_result.data = []
    global_res  = MagicMock(); global_res.data  = [{"tarifa_po_satu": 6500}]

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        return none_result if call_count[0] == 1 else global_res

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    with patch("routers.tarife._get_supa", return_value=supa):
        r = await get_klijent_tarifa(KL_ID, _req(), user=_user())
    assert r["tarifa_po_satu"] == 6500.0
    assert r["source"] == "default"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PUT /api/tarife/klijent/{klijent_id}
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_put_klijent_tarifa_set():
    from routers.tarife import put_klijent_tarifa, KlijentTarifaReq
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))
    none_result = MagicMock(); none_result.data = None
    ok_result   = MagicMock(); ok_result.data   = [{"tarifa_po_satu": 9000}]

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        return none_result if call_count[0] == 1 else ok_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    body = KlijentTarifaReq(tarifa_po_satu=9000)
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await put_klijent_tarifa(KL_ID, body, _req(method="PUT"), user=_user())
    assert r["ok"] is True
    assert r["tarifa_po_satu"] == 9000.0


@pytest.mark.anyio
async def test_put_klijent_tarifa_remove():
    from routers.tarife import put_klijent_tarifa, KlijentTarifaReq
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))
    exist_result = MagicMock(); exist_result.data = [{"id": "row-1"}]
    del_result   = MagicMock(); del_result.data   = [{"id": "row-1"}]

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        return exist_result if call_count[0] == 1 else del_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    body = KlijentTarifaReq(tarifa_po_satu=None)
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await put_klijent_tarifa(KL_ID, body, _req(method="PUT"), user=_user())
    assert r["removed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 7. GET /api/tarife/stavke
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_get_stavke_no_custom():
    from routers.tarife import get_stavke
    supa, res = _chain([])
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await get_stavke(_req(), user=_user())
    assert len(r["stavke"]) == len(__import__("routers.billing", fromlist=["AKS_TARIFA"]).AKS_TARIFA)
    t01 = next(s for s in r["stavke"] if s["sifra"] == "T01")
    assert t01["is_custom"] is False
    assert t01["iznos_rsd"] == 600.0


@pytest.mark.anyio
async def test_get_stavke_with_custom_t01():
    from routers.tarife import get_stavke
    supa, res = _chain([{"kod": "T01", "naziv": None, "iznos": 800}])
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await get_stavke(_req(), user=_user())
    t01 = next(s for s in r["stavke"] if s["sifra"] == "T01")
    assert t01["is_custom"] is True
    assert t01["iznos_rsd"] == 800.0
    assert t01["aks_iznos"] == 600.0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. PUT /api/tarife/stavke/{kod}
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_put_stavka_set():
    from routers.tarife import put_stavka, StavkaReq
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))
    none_result = MagicMock(); none_result.data = None
    ok_result   = MagicMock(); ok_result.data   = [{"iznos": 800}]

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        return none_result if call_count[0] == 1 else ok_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    body = StavkaReq(iznos=800)
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await put_stavka("T01", body, _req(method="PUT"), user=_user())
    assert r["ok"] is True
    assert float(r["iznos"]) == 800.0


@pytest.mark.anyio
async def test_put_stavka_reset():
    from routers.tarife import put_stavka, StavkaReq
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))
    del_result = MagicMock(); del_result.data = []
    chain.execute.return_value = del_result
    supa.table = MagicMock(return_value=chain)

    body = StavkaReq(iznos=None, naziv=None)
    with patch("routers.tarife._get_supa", return_value=supa):
        r = await put_stavka("T01", body, _req(method="PUT"), user=_user())
    assert r["removed"] is True


@pytest.mark.anyio
async def test_put_stavka_unknown_kod():
    from routers.tarife import put_stavka, StavkaReq
    from fastapi import HTTPException
    supa, _ = _chain(None)
    body = StavkaReq(iznos=500)
    with patch("routers.tarife._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            await put_stavka("TXXX", body, _req(method="PUT"), user=_user())
    assert exc_info.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 9. billing.py — _resolve_tarifa_for_predmet
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_resolve_tarifa_for_predmet_with_klijent():
    from routers.billing import _resolve_tarifa_for_predmet
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','is_','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))

    kl_result     = MagicMock(); kl_result.data     = [{"klijent_id": KL_ID}]
    tarifa_result = MagicMock(); tarifa_result.data  = [{"tarifa_po_satu": 9000}]
    fallback      = MagicMock(); fallback.data       = None

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        if call_count[0] == 1: return kl_result      # predmet_klijenti lookup
        if call_count[0] == 2: return tarifa_result   # per-klijent tarifa
        return fallback

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    satnica = await _resolve_tarifa_for_predmet(supa, UID, "pred-1")
    assert satnica == 9000.0


@pytest.mark.anyio
async def test_resolve_tarifa_for_predmet_no_klijent():
    from routers.billing import _resolve_tarifa_for_predmet
    supa = MagicMock()
    chain = MagicMock()
    for attr in ['table','select','eq','is_','limit','maybe_single','insert','update','delete']:
        setattr(chain, attr, MagicMock(return_value=chain))

    no_kl   = MagicMock(); no_kl.data   = []
    global_r = MagicMock(); global_r.data = [{"tarifa_po_satu": 6000}]

    call_count = [0]
    def execute_side():
        call_count[0] += 1
        if call_count[0] == 1: return no_kl      # no klijent for predmet
        return global_r                            # global tarifa

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)

    satnica = await _resolve_tarifa_for_predmet(supa, UID, "pred-1")
    assert satnica == 6000.0


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Pydantic model validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_satnica_req_valid():
    from routers.tarife import SatnicaReq
    m = SatnicaReq(tarifa_po_satu=5000)
    assert m.tarifa_po_satu == 5000


def test_satnica_req_invalid_zero():
    from routers.tarife import SatnicaReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SatnicaReq(tarifa_po_satu=0)


def test_klijent_tarifa_req_none():
    from routers.tarife import KlijentTarifaReq
    m = KlijentTarifaReq(tarifa_po_satu=None)
    assert m.tarifa_po_satu is None


def test_stavka_req_both_none():
    from routers.tarife import StavkaReq
    m = StavkaReq(iznos=None, naziv=None)
    assert m.iznos is None


def test_stavka_req_iznos_zero_allowed():
    from routers.tarife import StavkaReq
    m = StavkaReq(iznos=0)
    assert m.iznos == 0
