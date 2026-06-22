# -*- coding: utf-8 -*-
"""
Tests for routers/hearing_cc.py — Hearing Command Center.
All tests run without live Supabase or OpenAI (fully mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import MagicMock, AsyncMock, patch, call
import pytest
from starlette.requests import Request as StarletteRequest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/rociste/command-center", method="POST"):
    scope = {
        "type": "http", "method": method, "headers": [],
        "query_string": b"", "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user():
    return {
        "user_id": "aaaa0000-0000-0000-0000-000000000001",
        "email":   "test@vindex.rs",
        "is_pro":  True,
    }


UID   = "aaaa0000-0000-0000-0000-000000000001"
PID   = "cccc0000-0000-0000-0000-000000000003"
EMAIL = "test@vindex.rs"

_BRIFING = {
    "executive_brief":  "Predmet ima dobre izglede.",
    "timeline":         ["2026-01-01 — Tužba podneta"],
    "win_lose_matrix":  {"u_prilog": ["Jak dokaz"], "na_stetu": ["Kašnjenje"]},
    "opposing_counsel": "Protivnik će napadati rok.",
    "judge_attack_mode":"Pozovite se na čl. 231 ZPP.",
    "missing_evidence": ["Veštačenje"],
    "witness_analysis": "Svedok A — pouzdan.",
    "cross_examination":["Kada ste videli dokument?"],
    "practice_pack":    "VKS Rev 123/2022",
    "hearing_checklist":["Proverite dosije", "Kontaktirajte svedoka"],
    "hearing_score":    78,
    "risk_breakdown":   {"overall": "SREDNJI", "factors": ["Nedostaje veštačenje"]},
}


def _make_supa(predmet_data=None, empty_rest=True):
    """Returns a chainable Supabase mock for all 8 gather queries."""
    supa = MagicMock()
    call_n = [0]

    def _make_result(data):
        r = MagicMock()
        r.data = data
        return r

    pred_result = _make_result([predmet_data] if predmet_data else [])
    empty_result = _make_result([])

    chain = MagicMock()
    for attr in ['table','select','eq','is_','limit','order','execute',
                 'insert','update','delete','maybe_single']:
        setattr(chain, attr, MagicMock(return_value=chain))

    def execute_side():
        call_n[0] += 1
        if call_n[0] == 1:
            return pred_result
        return empty_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)
    return supa


def _make_openai_resp(content: dict):
    msg = MagicMock()
    msg.content = json.dumps(content)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Pydantic validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_req_valid_gradjanski():
    from routers.hearing_cc import HearingCCReq
    r = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
    assert r.tip_postupka == "gradjanski"
    assert r.datum_rocista == "2026-07-15"


def test_req_normalizes_tip_case():
    from routers.hearing_cc import HearingCCReq
    r = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="  KRIVICNI  ")
    assert r.tip_postupka == "krivicni"


def test_req_invalid_tip():
    from routers.hearing_cc import HearingCCReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="nepostoji")


def test_req_invalid_datum():
    from routers.hearing_cc import HearingCCReq
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        HearingCCReq(predmet_id=PID, datum_rocista="15-07-2026", tip_postupka="upravni")


def test_req_all_tip_values():
    from routers.hearing_cc import HearingCCReq, _VALID_TIP
    for tip in _VALID_TIP:
        r = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka=tip)
        assert r.tip_postupka == tip


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _first helper
# ═══════════════════════════════════════════════════════════════════════════════

def test_first_returns_none_on_empty():
    from routers.hearing_cc import _first
    r = MagicMock(); r.data = []
    assert _first(r) is None


def test_first_returns_none_on_none_data():
    from routers.hearing_cc import _first
    r = MagicMock(); r.data = None
    assert _first(r) is None


def test_first_returns_first_row():
    from routers.hearing_cc import _first
    r = MagicMock(); r.data = [{"id": "x"}, {"id": "y"}]
    assert _first(r) == {"id": "x"}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _load_all_context
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_load_context_returns_predmet():
    from routers.hearing_cc import _load_all_context
    pred = {"id": PID, "naziv": "Test predmet", "opis": "opis", "status": "aktivan"}
    supa = _make_supa(predmet_data=pred)
    ctx = await _load_all_context(supa, UID, PID)
    assert ctx["predmet"] is not None
    assert ctx["predmet"]["naziv"] == "Test predmet"


@pytest.mark.anyio
async def test_load_context_none_predmet():
    from routers.hearing_cc import _load_all_context
    supa = _make_supa(predmet_data=None)
    ctx = await _load_all_context(supa, UID, PID)
    assert ctx["predmet"] is None


@pytest.mark.anyio
async def test_load_context_handles_exception():
    from routers.hearing_cc import _load_all_context
    supa = MagicMock()
    supa.table.side_effect = Exception("DB error")
    ctx = await _load_all_context(supa, UID, PID)
    assert ctx["predmet"] is None
    assert ctx["klijenti"] == []
    assert ctx["dokumenti"] == []


@pytest.mark.anyio
async def test_load_context_keys_present():
    from routers.hearing_cc import _load_all_context
    supa = _make_supa(predmet_data={"id": PID, "naziv": "X"})
    ctx = await _load_all_context(supa, UID, PID)
    for key in ("predmet","klijenti","dokumenti","beleske","istorija","hronologija","komentari","rocista"):
        assert key in ctx


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _build_prompt
# ═══════════════════════════════════════════════════════════════════════════════

def test_build_prompt_contains_tip():
    from routers.hearing_cc import _build_prompt
    ctx = {
        "predmet":     {"naziv": "Test", "opis": "opis", "status": "aktivan", "rizik": "SREDNJI",
                        "tuzilac": "A", "tuzeni": "B", "oblast": "Parnično"},
        "klijenti":    [],
        "dokumenti":   [],
        "beleske":     [],
        "istorija":    [],
        "hronologija": [],
        "komentari":   [],
        "rocista":     [],
    }
    prompt = _build_prompt(ctx, "2026-07-15", "krivicni")
    assert "KRIVICNI" in prompt
    assert "2026-07-15" in prompt
    assert "Test" in prompt


def test_build_prompt_includes_hronologija():
    from routers.hearing_cc import _build_prompt
    ctx = {
        "predmet":     {"naziv": "P", "opis": "", "status": "a", "rizik": "", "tuzilac":"","tuzeni":"","oblast":""},
        "klijenti":    [],
        "dokumenti":   [],
        "beleske":     [],
        "istorija":    [],
        "hronologija": [{"datum_iso":"2025-01-01","dogadjaj":"Tužba","vaznost":"visoka"}],
        "komentari":   [],
        "rocista":     [],
    }
    prompt = _build_prompt(ctx, "2026-07-15", "gradjanski")
    assert "Tužba" in prompt
    assert "2025-01-01" in prompt


def test_build_prompt_includes_json_schema():
    from routers.hearing_cc import _build_prompt, _JSON_SCHEMA
    ctx = {k: [] if k != "predmet" else {"naziv":"X","opis":"","status":"","rizik":"","tuzilac":"","tuzeni":"","oblast":""}
           for k in ("predmet","klijenti","dokumenti","beleske","istorija","hronologija","komentari","rocista")}
    prompt = _build_prompt(ctx, "2026-07-15", "radni")
    assert "hearing_score" in prompt
    assert "executive_brief" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# 5. System prompts
# ═══════════════════════════════════════════════════════════════════════════════

def test_system_prompts_all_five():
    from routers.hearing_cc import _SYSTEM_PROMPTS
    for tip in ("gradjanski","krivicni","upravni","privredni","radni"):
        assert tip in _SYSTEM_PROMPTS
        assert len(_SYSTEM_PROMPTS[tip]) > 50


def test_gradjanski_mentions_zpp():
    from routers.hearing_cc import _SYSTEM_PROMPTS
    assert "ZPP" in _SYSTEM_PROMPTS["gradjanski"]


def test_krivicni_mentions_zkp():
    from routers.hearing_cc import _SYSTEM_PROMPTS
    assert "ZKP" in _SYSTEM_PROMPTS["krivicni"]


def test_radni_mentions_zor():
    from routers.hearing_cc import _SYSTEM_PROMPTS
    assert "ZOR" in _SYSTEM_PROMPTS["radni"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Endpoint — happy path
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_endpoint_success():
    from routers.hearing_cc import hearing_command_center, HearingCCReq

    pred = {"id": PID, "naziv": "Test", "opis": "opis", "status": "aktivan",
            "rizik": "SREDNJI", "tuzilac": "A", "tuzeni": "B", "oblast": "Parnično"}
    supa = _make_supa(predmet_data=pred)
    oai_resp = _make_openai_resp(_BRIFING)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc._deduct_n_credits", return_value=97) as mock_deduct, \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat = MagicMock()
        mock_oai.chat.completions = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=oai_resp)
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result = await hearing_command_center(
            body=body,
            request=_req(),
            user=_user(),
            _cred={"credits_remaining": 100},
        )

    assert result["ok"] is True
    assert result["predmet_id"] == PID
    assert result["tip_postupka"] == "gradjanski"
    assert result["datum_rocista"] == "2026-07-15"
    assert result["brifing"]["hearing_score"] == 78
    assert result["krediti_preostalo"] == 97
    mock_deduct.assert_called_once_with(UID, EMAIL, 3)


@pytest.mark.anyio
async def test_endpoint_deducts_3_credits():
    from routers.hearing_cc import hearing_command_center, HearingCCReq

    pred = {"id": PID, "naziv": "T", "opis": "", "status": "a",
            "rizik": "", "tuzilac": "", "tuzeni": "", "oblast": ""}
    supa = _make_supa(predmet_data=pred)
    oai_resp = _make_openai_resp(_BRIFING)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc._deduct_n_credits", return_value=50) as mock_deduct, \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=oai_resp)
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="krivicni")
        await hearing_command_center(body=body, request=_req(), user=_user(), _cred={})

    mock_deduct.assert_called_once()
    args = mock_deduct.call_args[0]
    assert args[2] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Endpoint — 404 on missing predmet
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_endpoint_404_missing_predmet():
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    from fastapi import HTTPException

    supa = _make_supa(predmet_data=None)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"):

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="upravni")
        with pytest.raises(HTTPException) as exc_info:
            await hearing_command_center(body=body, request=_req(), user=_user(), _cred={})

    assert exc_info.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Endpoint — OpenAI error → 503
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_endpoint_503_on_openai_error():
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    from fastapi import HTTPException

    pred = {"id": PID, "naziv": "T", "opis": "", "status": "a",
            "rizik": "", "tuzilac": "", "tuzeni": "", "oblast": ""}
    supa = _make_supa(predmet_data=pred)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(side_effect=Exception("Timeout"))
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="privredni")
        with pytest.raises(HTTPException) as exc_info:
            await hearing_command_center(body=body, request=_req(), user=_user(), _cred={})

    assert exc_info.value.status_code == 503


@pytest.mark.anyio
async def test_endpoint_503_on_invalid_json():
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    from fastapi import HTTPException

    pred = {"id": PID, "naziv": "T", "opis": "", "status": "a",
            "rizik": "", "tuzilac": "", "tuzeni": "", "oblast": ""}
    supa = _make_supa(predmet_data=pred)

    bad_msg = MagicMock(); bad_msg.content = "not json"
    bad_choice = MagicMock(); bad_choice.message = bad_msg
    bad_resp = MagicMock(); bad_resp.choices = [bad_choice]

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=bad_resp)
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="radni")
        with pytest.raises(HTTPException) as exc_info:
            await hearing_command_center(body=body, request=_req(), user=_user(), _cred={})

    assert exc_info.value.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Endpoint — all tip_postupka values work
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
@pytest.mark.parametrize("tip", ["gradjanski","krivicni","upravni","privredni","radni"])
async def test_endpoint_all_tip_postupka(tip):
    from routers.hearing_cc import hearing_command_center, HearingCCReq

    pred = {"id": PID, "naziv": "T", "opis": "", "status": "a",
            "rizik": "", "tuzilac": "", "tuzeni": "", "oblast": ""}
    supa = _make_supa(predmet_data=pred)
    oai_resp = _make_openai_resp(_BRIFING)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc._deduct_n_credits", return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=oai_resp)
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka=tip)
        result = await hearing_command_center(body=body, request=_req(), user=_user(), _cred={})

    assert result["ok"] is True
    assert result["tip_postupka"] == tip


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Router registration
# ═══════════════════════════════════════════════════════════════════════════════

def test_router_has_correct_tag():
    from routers.hearing_cc import router
    assert "hearing_cc" in router.tags


def test_router_has_command_center_route():
    from routers.hearing_cc import router
    paths = [r.path for r in router.routes]
    assert "/api/rociste/command-center" in paths


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Brifing structure
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_brifing_has_all_12_sections():
    from routers.hearing_cc import hearing_command_center, HearingCCReq

    pred = {"id": PID, "naziv": "T", "opis": "", "status": "a",
            "rizik": "", "tuzilac": "", "tuzeni": "", "oblast": ""}
    supa = _make_supa(predmet_data=pred)
    oai_resp = _make_openai_resp(_BRIFING)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc._deduct_n_credits", return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=oai_resp)
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result = await hearing_command_center(body=body, request=_req(), user=_user(), _cred={})

    brifing = result["brifing"]
    expected_keys = {
        "executive_brief", "timeline", "win_lose_matrix", "opposing_counsel",
        "judge_attack_mode", "missing_evidence", "witness_analysis",
        "cross_examination", "practice_pack", "hearing_checklist",
        "hearing_score", "risk_breakdown",
    }
    assert expected_keys.issubset(set(brifing.keys()))


@pytest.mark.anyio
async def test_hearing_score_in_response():
    from routers.hearing_cc import hearing_command_center, HearingCCReq

    pred = {"id": PID, "naziv": "T", "opis": "", "status": "a",
            "rizik": "", "tuzilac": "", "tuzeni": "", "oblast": ""}
    supa = _make_supa(predmet_data=pred)
    brifing_high = dict(_BRIFING, hearing_score=92)
    oai_resp = _make_openai_resp(brifing_high)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc._deduct_n_credits", return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=oai_resp)
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result = await hearing_command_center(body=body, request=_req(), user=_user(), _cred={})

    assert result["brifing"]["hearing_score"] == 92
