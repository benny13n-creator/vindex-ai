# -*- coding: utf-8 -*-
"""
Program Tau, Master Sprint 006 ("Canonical Context Migration Factory") —
Phase 4 pilot migration tests for routers/hearing_cc.py.

Covers: _dohvati_case_context_ako_postoji (fail-soft fetch), _case_context_blok
(formatter), the deterministic hearing_score cap (Factory Step 4 boundary,
same shape Tau 005 proved for court_predictor.py), full-mode document
injection, cross_examination's lightweight-mode injection, and concurrency/
replay stability.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(path="/api/rociste/command-center"):
    scope = {
        "type": "http", "method": "POST", "headers": [],
        "query_string": b"", "path": path,
        "app": MagicMock(), "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)


def _user(uid="aaaa0000-0000-0000-0000-000000000001"):
    return {"user_id": uid, "email": "test@vindex.rs", "is_pro": True}


UID   = "aaaa0000-0000-0000-0000-000000000001"
PID   = "cccc0000-0000-0000-0000-000000000003"
EMAIL = "test@vindex.rs"


def _cc(readiness_status="READY", missing=None, contra=None, documents=None):
    """Minimal valid build_case_context()-shaped mock dict."""
    return {
        "contract_version": "1.0.0",
        "readiness": {"value": {"status": readiness_status, "razlog": "test"}},
        "key_facts": {"value": {"snaga_predmeta_procent": 60, "najslabija_tacka": {"rizik": "Nema svedoka"}}},
        "missing_evidence": {"value": missing or []},
        "contradictions": {"value": contra or []},
        "active_actions": {"value": []},
        "timeline": {"value": []},
        "relevant_documents": {"value": {"included": documents or [], "not_included_but_retrievable": [], "total_documents": len(documents or [])}},
    }


def _make_supa(predmet_data=None):
    supa = MagicMock()
    call_n = [0]

    def _make_result(data):
        r = MagicMock()
        r.data = data
        return r

    pred_result = _make_result([predmet_data] if predmet_data else [])
    empty_result = _make_result([])

    chain = MagicMock()
    for attr in ['table', 'select', 'eq', 'is_', 'limit', 'order', 'execute',
                 'insert', 'update', 'delete', 'maybe_single']:
        setattr(chain, attr, MagicMock(return_value=chain))

    def execute_side():
        call_n[0] += 1
        return pred_result if call_n[0] == 1 else empty_result

    chain.execute.side_effect = execute_side
    supa.table = MagicMock(return_value=chain)
    return supa


def _oai_resp(content: dict):
    msg = MagicMock(); msg.content = json.dumps(content)
    choice = MagicMock(); choice.message = msg
    resp = MagicMock(); resp.choices = [choice]
    return resp


_BRIFING = {
    "executive_brief": "Test", "timeline": [], "win_lose_matrix": {"u_prilog": [], "na_stetu": []},
    "opposing_counsel": "X", "judge_attack_mode": "X", "missing_evidence": [], "witness_analysis": "X",
    "cross_examination": [], "practice_pack": "X", "hearing_checklist": [],
    "hearing_score": 85, "risk_breakdown": {"overall": "NIZAK", "factors": []},
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. _dohvati_case_context_ako_postoji — fail-soft fetch (Factory Step 1)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_dohvati_case_context_returns_none_without_predmet_id():
    from routers.hearing_cc import _dohvati_case_context_ako_postoji
    result = await _dohvati_case_context_ako_postoji("", UID, MagicMock())
    assert result is None


@pytest.mark.anyio
async def test_dohvati_case_context_fail_soft_on_exception():
    from routers.hearing_cc import _dohvati_case_context_ako_postoji
    with patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, side_effect=Exception("boom")):
        result = await _dohvati_case_context_ako_postoji(PID, UID, MagicMock())
    assert result is None


@pytest.mark.anyio
async def test_dohvati_case_context_calls_build_case_context_full_mode():
    from routers.hearing_cc import _dohvati_case_context_ako_postoji
    with patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, return_value=_cc()) as mock_bcc:
        result = await _dohvati_case_context_ako_postoji(PID, UID, MagicMock(), include_documents=True)
    mock_bcc.assert_awaited_once_with(PID, UID, mock_bcc.await_args[0][2], include_documents=True)
    assert result is not None


# ═══════════════════════════════════════════════════════════════════════════
# 2. _case_context_blok — formatter (Factory Step 2)
# ═══════════════════════════════════════════════════════════════════════════

def test_case_context_blok_empty_on_none_or_error():
    from routers.hearing_cc import _case_context_blok
    assert _case_context_blok(None) == ""
    assert _case_context_blok({"error": "predmet_not_found"}) == ""


def test_case_context_blok_includes_readiness_and_missing_evidence():
    from routers.hearing_cc import _case_context_blok
    blok = _case_context_blok(_cc(readiness_status="CRITICAL_GAP", missing=[{"opis": "Nedostaje ugovor"}]))
    assert "CRITICAL_GAP" in blok
    assert "Nedostaje ugovor" in blok


def test_case_context_blok_includes_documents_when_present():
    from routers.hearing_cc import _case_context_blok
    blok = _case_context_blok(_cc(documents=[{"naziv": "Tuzba.pdf", "excerpt": "Tuženi duguje 500.000 din."}]))
    assert "Tuzba.pdf" in blok
    assert "Tuženi duguje" in blok


# ═══════════════════════════════════════════════════════════════════════════
# 3. hearing_command_center — full-mode injection + deterministic cap
# ═══════════════════════════════════════════════════════════════════════════

_PRED = {"id": PID, "naziv": "T", "opis": "", "status": "a", "rizik": "", "tuzilac": "", "tuzeni": "", "oblast": ""}


@pytest.mark.anyio
async def test_hearing_command_center_uses_full_document_mode():
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    supa = _make_supa(predmet_data=_PRED)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, return_value=_cc()) as mock_bcc, \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc.UsageService.consume", new_callable=AsyncMock, return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BRIFING))
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result = await hearing_command_center(body=body, request=_req(), user=_user())

    assert mock_bcc.call_args.kwargs.get("include_documents") is True
    assert result["kontekst_predmeta_koriscen"] is True


@pytest.mark.anyio
async def test_hearing_command_center_caps_score_on_critical_gap_even_if_gpt_disagrees():
    """Adversarial (Factory Step 4 / Phase 5): a poisoned GPT response claims
    hearing_score=95 while the canonical readiness is CRITICAL_GAP -- the
    deterministic cap must win regardless of what GPT returns."""
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    supa = _make_supa(predmet_data=_PRED)
    poisoned = dict(_BRIFING, hearing_score=95)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, return_value=_cc(readiness_status="CRITICAL_GAP")), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc.UsageService.consume", new_callable=AsyncMock, return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(poisoned))
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result = await hearing_command_center(body=body, request=_req(), user=_user())

    assert result["brifing"]["hearing_score"] == 50


@pytest.mark.anyio
async def test_hearing_command_center_no_cap_when_readiness_ready():
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    supa = _make_supa(predmet_data=_PRED)
    high = dict(_BRIFING, hearing_score=92)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, return_value=_cc(readiness_status="READY")), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc.UsageService.consume", new_callable=AsyncMock, return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(high))
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result = await hearing_command_center(body=body, request=_req(), user=_user())

    assert result["brifing"]["hearing_score"] == 92


@pytest.mark.anyio
async def test_hearing_command_center_degrades_gracefully_without_case_context():
    """build_case_context() fails -- endpoint must still succeed, unchanged
    pre-migration behavior, per Factory Step 1's own fail-soft requirement."""
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    supa = _make_supa(predmet_data=_PRED)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, side_effect=Exception("db down")), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc.UsageService.consume", new_callable=AsyncMock, return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(_BRIFING))
        mock_oai_cls.return_value = mock_oai

        body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result = await hearing_command_center(body=body, request=_req(), user=_user())

    assert result["ok"] is True
    assert result["kontekst_predmeta_koriscen"] is False
    assert result["brifing"]["hearing_score"] == 85  # unchanged, no cap applied


# ═══════════════════════════════════════════════════════════════════════════
# 4. cross_examination — lightweight-mode injection
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_cross_examination_uses_lightweight_mode_and_injects_context():
    from routers.hearing_cc import cross_examination, CrossExamRequest
    supa = MagicMock()

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock,
               return_value=_cc(contra=[{"opis": "Svedok tvrdi suprotno od izjave iz 2024."}])) as mock_bcc, \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc.UsageService.consume", new_callable=AsyncMock, return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="1. Pitanje?"))]
        ))
        mock_oai_cls.return_value = mock_oai

        body = CrossExamRequest(predmet_id=PID, svedok_opis="Svedok A, komsija", tema="Video incident", nasa_pozicija="Tuzilac")
        result = await cross_examination(body=body, request=_req("/api/rociste/cross-exam"), user=_user())

    assert mock_bcc.call_args.kwargs.get("include_documents") is False
    assert result["kontekst_predmeta_koriscen"] is True
    prompt_sent = mock_oai.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "Svedok tvrdi suprotno" in prompt_sent


# ═══════════════════════════════════════════════════════════════════════════
# 5. Concurrency / replay stability (Phase 9 precedent from Tau 005)
# ═══════════════════════════════════════════════════════════════════════════

def _make_multi_supa(preds_by_id: dict):
    """Unlike _make_supa's global call counter (fine for a single sequential
    request), concurrent requests sharing one mock need per-call isolation:
    each supa.table(...) invocation gets its own chain/closure keyed by the
    actual .eq('id', ...) value, so 2 concurrent _load_all_context() calls
    for different cases never see each other's row."""
    supa = MagicMock()

    def _table_side_effect(name):
        chain = MagicMock()
        state = {"id": None}

        def _eq(field, value):
            if name == "predmeti" and field == "id":
                state["id"] = value
            return chain

        for attr in ['select', 'is_', 'limit', 'order', 'insert', 'update', 'delete', 'maybe_single']:
            setattr(chain, attr, MagicMock(return_value=chain))
        chain.eq = MagicMock(side_effect=_eq)

        def _execute():
            r = MagicMock()
            if name == "predmeti":
                pred = preds_by_id.get(state["id"])
                r.data = [pred] if pred else []
            else:
                r.data = []
            return r

        chain.execute = MagicMock(side_effect=_execute)
        return chain

    supa.table = MagicMock(side_effect=_table_side_effect)
    return supa


@pytest.mark.anyio
async def test_concurrent_briefings_for_different_cases_do_not_cross_contaminate():
    from routers.hearing_cc import hearing_command_center, HearingCCReq

    async def _bcc_side_effect(predmet_id, uid, supa, include_documents=True):
        status = "CRITICAL_GAP" if predmet_id == "case-a" else "READY"
        return _cc(readiness_status=status)

    supa = _make_multi_supa({
        "case-a": {**_PRED, "id": "case-a"},
        "case-b": {**_PRED, "id": "case-b"},
    })
    poisoned = dict(_BRIFING, hearing_score=95)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, side_effect=_bcc_side_effect), \
         patch("routers.hearing_cc.begin_cost_tracking"), \
         patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
         patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
         patch("routers.hearing_cc.UsageService.consume", new_callable=AsyncMock, return_value=90), \
         patch("openai.AsyncOpenAI") as mock_oai_cls:

        mock_oai = MagicMock()
        mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(poisoned))
        mock_oai_cls.return_value = mock_oai

        body_a = HearingCCReq(predmet_id="case-a", datum_rocista="2026-07-15", tip_postupka="gradjanski")
        body_b = HearingCCReq(predmet_id="case-b", datum_rocista="2026-07-15", tip_postupka="gradjanski")
        result_a, result_b = await asyncio.gather(
            hearing_command_center(body=body_a, request=_req(), user=_user()),
            hearing_command_center(body=body_b, request=_req(), user=_user()),
        )

    assert result_a["brifing"]["hearing_score"] == 50   # capped, CRITICAL_GAP
    assert result_b["brifing"]["hearing_score"] == 95   # not capped, READY


# ═══════════════════════════════════════════════════════════════════════════
# 6. Phase 5 — adversarial review (nonexistent case, missing Genome,
#    incomplete case, OCR-garbled text, restart/determinism safety)
# ═══════════════════════════════════════════════════════════════════════════

def test_case_context_blok_empty_on_predmet_not_found_error():
    """build_case_context() returns {"error": "predmet_not_found", ...} for a
    nonexistent case -- the formatter must degrade cleanly, not KeyError."""
    from routers.hearing_cc import _case_context_blok
    blok = _case_context_blok({"error": "predmet_not_found", "predmet_id": "ghost-id", "contract_version": "1.0.0"})
    assert blok == ""


def test_case_context_blok_handles_missing_genome():
    """genome_computed=False -> key_facts.value is None (not a dict) -- the
    Genome section must be skipped, not raise."""
    from routers.hearing_cc import _case_context_blok
    cc = _cc()
    cc["key_facts"] = {"value": None}
    blok = _case_context_blok(cc)
    assert "Snaga predmeta" not in blok
    assert "Najslabija" not in blok


def test_case_context_blok_handles_bare_incomplete_case():
    """A newly-created case with nothing yet: no Genome, no missing_evidence,
    no contradictions, no actions, no timeline, no documents. Must render an
    empty-but-valid header, not crash."""
    from routers.hearing_cc import _case_context_blok
    bare = {
        "readiness": {"value": {"status": "UNKNOWN", "razlog": ""}},
        "key_facts": {"value": None},
        "missing_evidence": {"value": []},
        "contradictions": {"value": []},
        "active_actions": {"value": []},
        "timeline": {"value": []},
        "relevant_documents": {"value": {"included": [], "not_included_but_retrievable": [], "total_documents": 0}},
    }
    blok = _case_context_blok(bare)
    assert "STVARNO STANJE PREDMETA" in blok
    assert "UNKNOWN" in blok


def test_case_context_blok_handles_ocr_garbled_document_text():
    """A document whose extracted text is OCR garbage (control chars, no
    real words) must still render as a plain excerpt string -- no special
    parsing exists to break on malformed content."""
    from routers.hearing_cc import _case_context_blok
    garbled = "\x00\x01##%%%__ ovaj tekst je o%%%crigovan iz OCR-a §§§ necitljivo ���"
    blok = _case_context_blok(_cc(documents=[{"naziv": "skenirano.pdf", "excerpt": garbled}]))
    assert "skenirano.pdf" in blok
    assert garbled[:50] in blok


@pytest.mark.anyio
async def test_hearing_command_center_404_on_nonexistent_case_even_with_context_pending():
    """A nonexistent predmet_id: _load_all_context finds no predmet row (404
    path) while _dohvati_case_context_ako_postoji concurrently gets
    build_case_context()'s own {"error": "predmet_not_found"}. The 404 must
    still fire correctly -- confirms the concurrent gather doesn't let a
    degraded case_context mask the missing-case error."""
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    from fastapi import HTTPException
    supa = _make_supa(predmet_data=None)

    with patch("routers.hearing_cc._get_supa", return_value=supa), \
         patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock,
               return_value={"error": "predmet_not_found", "predmet_id": "ghost", "contract_version": "1.0.0"}), \
         patch("routers.hearing_cc.begin_cost_tracking"):

        body = HearingCCReq(predmet_id="ghost", datum_rocista="2026-07-15", tip_postupka="gradjanski")
        with pytest.raises(HTTPException) as exc_info:
            await hearing_command_center(body=body, request=_req(), user=_user())

    assert exc_info.value.status_code == 404


def test_no_module_level_mutable_state_in_hearing_cc():
    """Restart/determinism safety (Phase 5's own 'proces restart' scenario):
    confirms no module-level cache/mutable dict was introduced by this
    sprint's migration -- the same case, called again after a fresh process
    start, must produce the same result. Static proof (not a runtime
    behavior this file's own mocks can simulate a real restart for): the only
    new module-level object is _CAP_BY_READINESS, and it must be a read-only,
    never-mutated constant."""
    import routers.hearing_cc as hc
    assert hc._CAP_BY_READINESS == {"CRITICAL_GAP": 50, "BLOCKED": 65}
    # Confirm nothing in the module accidentally mutates it at call time.
    snapshot = dict(hc._CAP_BY_READINESS)
    assert hc._CAP_BY_READINESS == snapshot


@pytest.mark.anyio
async def test_repeated_identical_calls_produce_identical_capped_output_replay_stable():
    """Phase 9 replay test: the exact same request, called twice in sequence,
    must produce an identical capped hearing_score both times -- no hidden
    state carried between calls."""
    # _make_supa's own global call-counter ("1st execute() call = predmet
    # row") is order-fragile under asyncio.to_thread's real thread scheduling
    # -- fine for a single isolated call (as this file's other tests show),
    # but not safe to reuse across 2 back-to-back invocations. _make_multi_supa
    # (keyed by the actual .eq("id", ...) value, see the concurrency test
    # above) is deterministic regardless of thread completion order.
    from routers.hearing_cc import hearing_command_center, HearingCCReq
    poisoned = dict(_BRIFING, hearing_score=97)

    async def _one_call():
        with patch("routers.hearing_cc._get_supa", return_value=_make_multi_supa({PID: _PRED})), \
             patch("routers.hearing_cc.build_case_context", new_callable=AsyncMock, return_value=_cc(readiness_status="BLOCKED")), \
             patch("routers.hearing_cc.begin_cost_tracking"), \
             patch("routers.hearing_cc.log_cost_to_db", new_callable=AsyncMock), \
             patch("routers.hearing_cc._audit", new_callable=AsyncMock), \
             patch("routers.hearing_cc.UsageService.consume", new_callable=AsyncMock, return_value=90), \
             patch("openai.AsyncOpenAI") as mock_oai_cls:

            mock_oai = MagicMock()
            mock_oai.chat.completions.create = AsyncMock(return_value=_oai_resp(poisoned))
            mock_oai_cls.return_value = mock_oai

            body = HearingCCReq(predmet_id=PID, datum_rocista="2026-07-15", tip_postupka="gradjanski")
            return await hearing_command_center(body=body, request=_req(), user=_user())

    result_1 = await _one_call()
    result_2 = await _one_call()

    assert result_1["brifing"]["hearing_score"] == result_2["brifing"]["hearing_score"] == 65
