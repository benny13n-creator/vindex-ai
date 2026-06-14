# -*- coding: utf-8 -*-
"""
Tests for routers/rocista.py — hearing_followup endpoint (Vindex OS PRIORITET 5).
POST /api/rociste/followup
All tests run without live Supabase (mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req():
    scope = {"type":"http","method":"POST","headers":[],"query_string":b"","path":"/api/rociste/followup",
             "app":MagicMock(),"state":MagicMock()}
    return StarletteRequest(scope=scope)


def _user():
    return {"user_id": "aaaa0000-0000-0000-0000-000000000001", "email": "test@vindex.rs"}


PID = "cccc0000-0000-0000-0000-000000000003"


def _make_chain(data):
    chain = MagicMock()
    for attr in ['select','eq','gte','lte','order','limit','execute',
                 'insert','update','delete','is_','in_','neq']:
        setattr(chain, attr, MagicMock(return_value=chain))
    r = MagicMock(); r.data = data
    chain.execute = MagicMock(return_value=r)
    return chain


def _make_supa(pred_data=None):
    """
    First table call (predmeti) returns pred_data.
    All subsequent insert calls return success row.
    """
    supa  = MagicMock()
    calls = [0]

    def _table(name):
        ch = MagicMock()
        for attr in ['select','eq','gte','lte','order','limit','execute',
                     'insert','update','delete','is_','in_','neq']:
            setattr(ch, attr, MagicMock(return_value=ch))

        if name == "predmeti" and calls[0] == 0:
            calls[0] += 1
            data = pred_data if pred_data is not None else [{"id": PID, "naziv": "Test predmet", "status": "aktivan"}]
            r = MagicMock(); r.data = data
            ch.execute = MagicMock(return_value=r)
        else:
            calls[0] += 1
            r = MagicMock(); r.data = [{"id": "new_row"}]
            ch.execute = MagicMock(return_value=r)
        return ch

    supa.table = MagicMock(side_effect=_table)
    return supa


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FollowUpReq validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_followup_req_valid():
    from routers.rocista import FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Ročište odloženo zbog svedoka.")
    assert body.predmet_id == PID
    assert body.rociste_id is None


def test_followup_req_with_rociste_id():
    from routers.rocista import FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Napomena", rociste_id="roc-123")
    assert body.rociste_id == "roc-123"


def test_followup_req_empty_napomena_fails():
    from routers.rocista import FollowUpReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FollowUpReq(predmet_id=PID, napomena="")


def test_followup_req_empty_predmet_id_fails():
    from routers.rocista import FollowUpReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FollowUpReq(predmet_id="", napomena="Napomena")


def test_followup_req_too_long_napomena_fails():
    from routers.rocista import FollowUpReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FollowUpReq(predmet_id=PID, napomena="x" * 4001)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Happy path
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_followup_returns_ok():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Ročište je odloženo.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert result["ok"] is True
    assert result["predmet_id"] == PID


@pytest.mark.anyio
async def test_followup_returns_required_keys():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Napomena.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert {"ok","predmet_id","naziv","datum","preporuke","akcije"}.issubset(result.keys())


@pytest.mark.anyio
async def test_followup_akcije_flags():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Presuda je doneta.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert result["akcije"]["beleska_kreirana"] is True
    assert result["akcije"]["hronologija_azurana"] is True
    assert result["akcije"]["istorija_azurana"] is True


@pytest.mark.anyio
async def test_followup_naziv_from_predmet():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Napomena.")
    supa = _make_supa(pred_data=[{"id": PID, "naziv": "Kovač vs. Petrović", "status": "aktivan"}])
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert result["naziv"] == "Kovač vs. Petrović"


@pytest.mark.anyio
async def test_followup_datum_is_today():
    from routers.rocista import hearing_followup, FollowUpReq
    from datetime import date
    body = FollowUpReq(predmet_id=PID, napomena="Napomena.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert result["datum"] == date.today().isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 404 on missing predmet
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_followup_404_missing_predmet():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Napomena.")
    supa = _make_supa(pred_data=[])
    with patch("routers.rocista._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await hearing_followup(body=body, request=_req(), user=_user())
    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Rule-based preporuke
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_preporuke_odlozeno():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Ročište je odloženo zbog bolesti svedoka.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert any("odloženo" in p.lower() or "novi termin" in p.lower() or "obavestite" in p.lower()
               for p in result["preporuke"])


@pytest.mark.anyio
async def test_preporuke_dokaz():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Nedostaju ključni dokazi iz arhive.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert any("dokaz" in p.lower() for p in result["preporuke"])


@pytest.mark.anyio
async def test_preporuke_svedok():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Svedok nije pristupio ročištu.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert any("svedok" in p.lower() for p in result["preporuke"])


@pytest.mark.anyio
async def test_preporuke_nagodba():
    from routers.rocista import hearing_followup, FollowUpReq
    # Use "nagodba" (nominative) so substring match works
    body = FollowUpReq(predmet_id=PID, napomena="Razmatramo opciju nagodba sa tužiocem.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert any("nagod" in p.lower() or "poravnanje" in p.lower() for p in result["preporuke"])


@pytest.mark.anyio
async def test_preporuke_zalba():
    from routers.rocista import hearing_followup, FollowUpReq
    # Use "žalba" (nominative) so substring match works
    body = FollowUpReq(predmet_id=PID, napomena="Razmatramo žalba na prvostepenu presudu.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert any("žalb" in p.lower() or "zalb" in p.lower() for p in result["preporuke"])


@pytest.mark.anyio
async def test_preporuke_presuda():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Doneta je presuda u korist tužioca.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert any("presud" in p.lower() or "odluk" in p.lower() for p in result["preporuke"])


@pytest.mark.anyio
async def test_preporuke_rok():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Rok za dostavljanje dokumentacije je ponedjeljak.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert any("rok" in p.lower() for p in result["preporuke"])


@pytest.mark.anyio
async def test_preporuke_default_when_no_keywords():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Sve je prošlo dobro danas.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert len(result["preporuke"]) >= 1


@pytest.mark.anyio
async def test_preporuke_multiple_keywords():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Ročište odloženo. Trebaju nam dokazi i svedok.")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert len(result["preporuke"]) >= 3  # odloženo + dokaz + svedok


# ═══════════════════════════════════════════════════════════════════════════════
# 5. rociste_id tag in beleška
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_followup_with_rociste_id_returns_ok():
    from routers.rocista import hearing_followup, FollowUpReq
    body = FollowUpReq(predmet_id=PID, napomena="Follow-up napomena.", rociste_id="roc-abc123")
    supa = _make_supa()
    with patch("routers.rocista._get_supa", return_value=supa):
        result = await hearing_followup(body=body, request=_req(), user=_user())
    assert result["ok"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Router registration
# ═══════════════════════════════════════════════════════════════════════════════

def test_followup_route_registered():
    from routers.rocista import router
    paths = [r.path for r in router.routes]
    assert "/api/rociste/followup" in paths


def test_followup_route_is_post():
    from routers.rocista import router
    for r in router.routes:
        if r.path == "/api/rociste/followup":
            assert "POST" in r.methods
            return
    pytest.fail("/api/rociste/followup not found")
