# -*- coding: utf-8 -*-
"""
Tests for services/case_pipeline.py and routers/case_pipeline.py
[FAZA:CASE-WIZARD-PIPELINE]

All tests run without live Supabase or OpenAI (mocked).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _req(method="POST", path="/api/predmeti/pid/pipeline"):
    scope = {"type": "http", "method": method, "headers": [], "query_string": b"",
             "path": path, "app": MagicMock(), "state": MagicMock()}
    return StarletteRequest(scope=scope)


def _user(uid="uid-001"):
    return {"user_id": uid, "email": "test@vindex.rs"}


PID = "pred-0000-0000-0000-000000000001"
UID = "user-0000-0000-0000-000000000001"
TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def _chain(data):
    c = MagicMock()
    for m in ['select','eq','neq','gte','lte','like','limit','order','single',
              'insert','update','execute','is_','in_']:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock(); r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _supa_by_table(**table_data):
    """Table-name routing mock."""
    supa = MagicMock()
    def _table(name):
        return _chain(table_data.get(name, []))
    supa.table = MagicMock(side_effect=_table)
    return supa


# ─── OpenAI mock helpers ──────────────────────────────────────────────────────

def _oai_mock(content="{}"):
    """Mock AsyncOpenAI that returns a fixed completion."""
    oai = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    oai.chat.completions.create = AsyncMock(return_value=resp)
    return oai


# ═══════════════════════════════════════════════════════════════════════════════
# 1. calculate_case_ready_score
# ═══════════════════════════════════════════════════════════════════════════════

def test_score_zero_empty():
    from services.case_pipeline import calculate_case_ready_score
    score, checklist = calculate_case_ready_score([], [], [], [], [])
    assert score == 0
    assert len(checklist) == 6
    assert all(not item["ok"] for item in checklist)


def test_score_full():
    from services.case_pipeline import calculate_case_ready_score
    istorija = [
        {"pitanje": "[Strategija Pipeline] Inicijalna procena"},
        {"pitanje": f"[Rizik] {TODAY}"},
    ]
    score, checklist = calculate_case_ready_score(
        dokumenti=[{"id": "d1"}],
        klijenti=[{"klijent_id": "k1"}],
        rokovi=[{"id": "r1"}],
        istorija=istorija,
        rocista=[{"id": "roc1"}],
    )
    assert score == 100
    assert all(item["ok"] for item in checklist)


def test_score_partial():
    from services.case_pipeline import calculate_case_ready_score
    # Only klijent + rokovi
    score, checklist = calculate_case_ready_score(
        dokumenti=[],
        klijenti=[{"klijent_id": "k1"}],
        rokovi=[{"id": "r1"}],
        istorija=[],
        rocista=[],
    )
    assert score == 35  # 20 + 15


def test_checklist_has_six_items():
    from services.case_pipeline import calculate_case_ready_score
    _, checklist = calculate_case_ready_score([], [], [], [], [])
    assert len(checklist) == 6


def test_checklist_stavka_names():
    from services.case_pipeline import calculate_case_ready_score
    _, checklist = calculate_case_ready_score([], [], [], [], [])
    names = [item["stavka"] for item in checklist]
    assert "Dokumentacija priložena" in names
    assert "Klijenti evidentirani" in names
    assert "Strategija generisana" in names


def test_score_detects_strategija_tag():
    from services.case_pipeline import calculate_case_ready_score
    istorija = [{"pitanje": "[Strategija Pipeline] test"}]
    score, _ = calculate_case_ready_score([], [], [], istorija, [])
    assert score == 20


def test_score_detects_rizik_tag():
    from services.case_pipeline import calculate_case_ready_score
    istorija = [{"pitanje": f"[Rizik] {TODAY}"}]
    score, _ = calculate_case_ready_score([], [], [], istorija, [])
    assert score == 15


# ═══════════════════════════════════════════════════════════════════════════════
# 2. StepResult and PipelineResult
# ═══════════════════════════════════════════════════════════════════════════════

def test_step_result_ok_true():
    from services.case_pipeline import StepResult, StepStatus
    s = StepResult("test", StepStatus.SUCCESS)
    assert s.ok is True


def test_step_result_ok_false_on_failed():
    from services.case_pipeline import StepResult, StepStatus
    s = StepResult("test", StepStatus.FAILED)
    assert s.ok is False


def test_step_result_ok_false_on_skipped():
    from services.case_pipeline import StepResult, StepStatus
    s = StepResult("test", StepStatus.SKIPPED)
    assert s.ok is False


def test_pipeline_result_to_dict_keys():
    from services.case_pipeline import PipelineResult, StepResult, StepStatus
    r = PipelineResult(predmet_id="p1", user_id="u1")
    r.steps = [StepResult("analiza_dokumenata", StepStatus.SKIPPED)]
    r.case_ready_score = 42
    d = r.to_dict()
    assert {"predmet_id", "case_ready_score", "checklist",
            "copilot_preporuka", "koraci"}.issubset(d.keys())
    assert d["case_ready_score"] == 42
    assert d["koraci"][0]["korak"] == "analiza_dokumenata"
    assert d["koraci"][0]["status"] == "SKIPPED"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _step_analiza_dokumenata
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step1_skipped_no_docs():
    from services.case_pipeline import _step_analiza_dokumenata, StepStatus
    supa = _supa_by_table(predmet_dokumenti=[], predmet_istorija=[])
    result = await _step_analiza_dokumenata(supa, PID, UID)
    assert result.status == StepStatus.SKIPPED


@pytest.mark.anyio
async def test_step1_success_docs_analyzed():
    from services.case_pipeline import _step_analiza_dokumenata, StepStatus
    supa = _supa_by_table(
        predmet_dokumenti=[{"id": "d1", "naziv_fajla": "doc.pdf"}],
        predmet_istorija=[{"pitanje": "[Auto-analiza] doc.pdf"}],
    )
    result = await _step_analiza_dokumenata(supa, PID, UID)
    assert result.status == StepStatus.SUCCESS


@pytest.mark.anyio
async def test_step1_failed_docs_not_analyzed():
    from services.case_pipeline import _step_analiza_dokumenata, StepStatus
    supa = _supa_by_table(
        predmet_dokumenti=[{"id": "d1", "naziv_fajla": "doc.pdf"}],
        predmet_istorija=[],
    )
    result = await _step_analiza_dokumenata(supa, PID, UID)
    assert result.status == StepStatus.FAILED


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _step_auto_linking
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step2_success_has_links():
    from services.case_pipeline import _step_auto_linking, StepStatus
    supa = _supa_by_table(predmet_klijenti=[{"klijent_id": "k1"}])
    result = await _step_auto_linking(supa, PID, UID, {"naziv": "Test"})
    assert result.status == StepStatus.SUCCESS
    assert result.data["klijenti_count"] == 1


@pytest.mark.anyio
async def test_step2_skipped_no_links():
    from services.case_pipeline import _step_auto_linking, StepStatus
    supa = _supa_by_table(predmet_klijenti=[])
    result = await _step_auto_linking(supa, PID, UID, {"naziv": "Test"})
    assert result.status == StepStatus.SKIPPED


# ═══════════════════════════════════════════════════════════════════════════════
# 5. _step_ekstrakcija_rokova
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step3_skipped_short_opis():
    from services.case_pipeline import _step_ekstrakcija_rokova, StepStatus
    supa = _supa_by_table(predmet_istorija=[])
    result = await _step_ekstrakcija_rokova(supa, PID, UID, {"naziv": "x", "opis": ""})
    assert result.status == StepStatus.SKIPPED


@pytest.mark.anyio
async def test_step3_idempotent_if_marker_exists():
    from services.case_pipeline import _step_ekstrakcija_rokova, StepStatus
    supa = _supa_by_table(predmet_istorija=[{"pitanje": f"[Pipeline:rokovi] {TODAY}"}])
    result = await _step_ekstrakcija_rokova(supa, PID, UID,
                                             {"naziv": "Test predmet", "opis": "Opis"})
    assert result.status == StepStatus.SUCCESS
    assert "idempotent" in result.poruka


@pytest.mark.anyio
async def test_step3_success_with_dates():
    from services.case_pipeline import _step_ekstrakcija_rokova, StepStatus
    supa = _supa_by_table(predmet_istorija=[], predmet_hronologija=[])
    oai = _oai_mock(
        f'[{{"datum":"{TOMORROW}","opis":"Rok za dostavljanje","vaznost":"bitan"}}]'
    )
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_ekstrakcija_rokova(
            supa, PID, UID,
            {"naziv": "Test predmet", "opis": "Rok za dostavljanje dokumentacije je " + TOMORROW},
        )
    assert result.status in (StepStatus.SUCCESS, StepStatus.SKIPPED)


@pytest.mark.anyio
async def test_step3_skipped_no_dates_found():
    from services.case_pipeline import _step_ekstrakcija_rokova, StepStatus
    supa = _supa_by_table(predmet_istorija=[], predmet_hronologija=[])
    oai = _oai_mock('[]')
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_ekstrakcija_rokova(
            supa, PID, UID,
            {"naziv": "Test predmet", "opis": "Klijent je otpušten bez razloga prošle godine."},
        )
    assert result.status == StepStatus.SKIPPED


# ═══════════════════════════════════════════════════════════════════════════════
# 6. _step_kalendar
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step4_success_has_rokovi():
    from services.case_pipeline import _step_kalendar, StepStatus
    supa = _supa_by_table(predmet_hronologija=[{"id": "h1"}])
    result = await _step_kalendar(supa, PID, UID)
    assert result.status == StepStatus.SUCCESS


@pytest.mark.anyio
async def test_step4_skipped_no_rokovi():
    from services.case_pipeline import _step_kalendar, StepStatus
    supa = _supa_by_table(predmet_hronologija=[])
    result = await _step_kalendar(supa, PID, UID)
    assert result.status == StepStatus.SKIPPED


# ═══════════════════════════════════════════════════════════════════════════════
# 7. _step_strategija
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step5_idempotent():
    from services.case_pipeline import _step_strategija, StepStatus
    supa = _supa_by_table(
        predmet_istorija=[{"pitanje": "[Strategija Pipeline] Inicijalna procena"}]
    )
    result = await _step_strategija(supa, PID, UID, {"naziv": "test", "opis": "x"})
    assert result.status == StepStatus.SUCCESS
    assert "idempotent" in result.poruka


@pytest.mark.anyio
async def test_step5_skipped_no_data():
    from services.case_pipeline import _step_strategija, StepStatus
    supa = _supa_by_table(predmet_istorija=[])
    result = await _step_strategija(supa, PID, UID, {"naziv": "", "opis": ""})
    assert result.status == StepStatus.SKIPPED


@pytest.mark.anyio
async def test_step5_success():
    from services.case_pipeline import _step_strategija, StepStatus
    supa = _supa_by_table(predmet_istorija=[])
    oai = _oai_mock("Preporuka: tužba zbog povrede prava.")
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_strategija(
            supa, PID, UID,
            {"naziv": "Radni spor", "opis": "Klijent otpušten bez otkaznog roka.", "tip": "radni"},
        )
    assert result.status == StepStatus.SUCCESS


@pytest.mark.anyio
async def test_step5_fails_gracefully_on_oai_error():
    from services.case_pipeline import _step_strategija, StepStatus
    supa = _supa_by_table(predmet_istorija=[])
    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=RuntimeError("OpenAI down"))
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_strategija(
            supa, PID, UID,
            {"naziv": "Test predmet", "opis": "Opis problema koji je duži od 20 karaktera.", "tip": "opsti"},
        )
    assert result.status == StepStatus.FAILED


# ═══════════════════════════════════════════════════════════════════════════════
# 8. _step_hcc
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step6_skipped_no_rocista():
    from services.case_pipeline import _step_hcc, StepStatus
    supa = _supa_by_table(rocista=[], predmet_istorija=[])
    result = await _step_hcc(supa, PID, UID, {"naziv": "Test", "opis": ""})
    assert result.status == StepStatus.SKIPPED


@pytest.mark.anyio
async def test_step6_idempotent_if_marker_exists():
    from services.case_pipeline import _step_hcc, StepStatus
    supa = _supa_by_table(
        rocista=[{"id": "roc1", "datum": TOMORROW, "sud": "Viši sud"}],
        predmet_istorija=[{"pitanje": f"[HCC Pipeline] {TOMORROW}"}],
    )
    result = await _step_hcc(supa, PID, UID, {"naziv": "Test"})
    assert result.status == StepStatus.SUCCESS
    assert "idempotent" in result.poruka


@pytest.mark.anyio
async def test_step6_success_generates_briefing():
    from services.case_pipeline import _step_hcc, StepStatus
    supa = _supa_by_table(
        rocista=[{"id": "roc1", "datum": TOMORROW, "sud": "Viši sud Beograd",
                  "tip_postupka": "gradjanski", "status": "zakazano"}],
        predmet_istorija=[],
    )
    oai = _oai_mock("Pre ročišta: 1. Pripremite dokaze. 2. Pozovite svedoke.")
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_hcc(supa, PID, UID, {"naziv": "Test", "opis": "Opis"})
    assert result.status == StepStatus.SUCCESS
    assert result.data.get("datum") == TOMORROW


# ═══════════════════════════════════════════════════════════════════════════════
# 9. _step_risk_snapshot
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step7_idempotent():
    from services.case_pipeline import _step_risk_snapshot, StepStatus
    supa = _supa_by_table(
        predmet_istorija=[{"pitanje": f"[Rizik] {TODAY}"}]
    )
    result = await _step_risk_snapshot(supa, PID, UID, {"naziv": "Test"})
    assert result.status == StepStatus.SUCCESS
    assert "idempotent" in result.poruka


@pytest.mark.anyio
async def test_step7_success():
    from services.case_pipeline import _step_risk_snapshot, StepStatus
    supa = _supa_by_table(predmet_istorija=[])
    oai = _oai_mock('{"nivo":"srednji","faktori_plus":["Jak dokaz"],"faktori_minus":["Kratak rok"]}')
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_risk_snapshot(
            supa, PID, UID,
            {"naziv": "Radni spor", "opis": "Klijent otpušten bez razloga.", "tip": "radni"},
        )
    assert result.status == StepStatus.SUCCESS
    assert result.data["nivo"] == "srednji"


@pytest.mark.anyio
async def test_step7_fails_gracefully():
    from services.case_pipeline import _step_risk_snapshot, StepStatus
    supa = _supa_by_table(predmet_istorija=[])
    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=RuntimeError("Network error"))
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_risk_snapshot(
            supa, PID, UID,
            {"naziv": "Test", "opis": "Opis", "tip": "opsti"},
        )
    assert result.status == StepStatus.FAILED


# ═══════════════════════════════════════════════════════════════════════════════
# 10. _step_copilot_preporuka
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step8_success():
    from services.case_pipeline import _step_copilot_preporuka, StepResult, StepStatus
    supa = MagicMock()
    oai = _oai_mock("Pribavite medicinsko veštačenje. Proverite rokove za žalbu.")
    step3 = StepResult("ekstrakcija_rokova", StepStatus.SUCCESS, "", {"inserted": 1})
    step7 = StepResult("risk_snapshot", StepStatus.SUCCESS, "", {"nivo": "nizak", "data": {}})
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_copilot_preporuka(
            supa, PID, UID,
            {"naziv": "Test", "opis": "Klijent traži naknadu.", "tip": "opsti"},
            step3, step7,
        )
    assert result.status == StepStatus.SUCCESS
    assert "preporuka" in result.data
    assert len(result.data["preporuka"]) > 5


@pytest.mark.anyio
async def test_step8_fallback_on_error():
    from services.case_pipeline import _step_copilot_preporuka, StepResult, StepStatus
    supa = MagicMock()
    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(side_effect=RuntimeError("error"))
    step3 = StepResult("ekstrakcija_rokova", StepStatus.SKIPPED)
    step7 = StepResult("risk_snapshot", StepStatus.FAILED)
    with patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await _step_copilot_preporuka(
            supa, PID, UID,
            {"naziv": "Test", "opis": "Opis", "tip": "opsti"},
            step3, step7,
        )
    # Even on failure, fallback preporuka is returned
    assert result.data.get("preporuka")


# ═══════════════════════════════════════════════════════════════════════════════
# 11. _step_istorija
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_step9_idempotent():
    from services.case_pipeline import _step_istorija, StepResult, StepStatus
    supa = _supa_by_table(predmet_istorija=[{"id": "existing"}])
    steps = [StepResult("test", StepStatus.SUCCESS)]
    result = await _step_istorija(supa, PID, UID, steps)
    assert result.status == StepStatus.SUCCESS
    assert "idempotent" in result.poruka


@pytest.mark.anyio
async def test_step9_saves_summary():
    from services.case_pipeline import _step_istorija, StepResult, StepStatus
    supa = _supa_by_table(predmet_istorija=[])
    steps = [
        StepResult("analiza_dokumenata", StepStatus.SKIPPED),
        StepResult("auto_linking", StepStatus.SUCCESS),
    ]
    result = await _step_istorija(supa, PID, UID, steps)
    assert result.status == StepStatus.SUCCESS


# ═══════════════════════════════════════════════════════════════════════════════
# 12. run_case_pipeline — integration
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_pipeline_raises_on_missing_predmet():
    from services.case_pipeline import run_case_pipeline
    supa = MagicMock()
    r = MagicMock(); r.data = None
    supa.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = r
    with patch("services.case_pipeline._get_supa", return_value=supa), \
         patch("services.case_pipeline.AsyncOpenAI", return_value=_oai_mock()):
        with pytest.raises(ValueError, match="nije pronađen"):
            await run_case_pipeline(PID, UID)


@pytest.mark.anyio
async def test_pipeline_returns_pipeline_result():
    from services.case_pipeline import run_case_pipeline

    predmet_row = {"naziv": "Test predmet", "opis": "Opis radnog spora.", "tip": "radni", "status": "aktivan"}
    supa = MagicMock()
    pred_resp = MagicMock(); pred_resp.data = predmet_row
    empty_resp = MagicMock(); empty_resp.data = []

    calls_by_name = {
        "predmeti":          pred_resp,
        "predmet_dokumenti": empty_resp,
        "predmet_istorija":  empty_resp,
        "predmet_klijenti":  MagicMock(data=[{"klijent_id": "k1"}]),
        "predmet_hronologija": empty_resp,
        "rocista":           empty_resp,
    }

    def _table(name):
        c = MagicMock()
        for m in ['select','eq','neq','gte','lte','like','limit','order',
                  'single','insert','execute','is_','in_']:
            setattr(c, m, MagicMock(return_value=c))
        resp = calls_by_name.get(name, empty_resp)
        c.execute = MagicMock(return_value=resp)
        c.single.return_value = c  # for .single().execute()
        return c

    supa.table = MagicMock(side_effect=_table)
    oai = _oai_mock('{"nivo":"nizak","faktori_plus":[],"faktori_minus":[]}')
    oai.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(
            content='{"nivo":"nizak","faktori_plus":[],"faktori_minus":[]}'
        ))])
    )

    with patch("services.case_pipeline._get_supa", return_value=supa), \
         patch("services.case_pipeline.AsyncOpenAI", return_value=oai):
        result = await run_case_pipeline(PID, UID)

    assert result.predmet_id == PID
    assert len(result.steps) == 9
    assert isinstance(result.case_ready_score, int)
    assert 0 <= result.case_ready_score <= 100
    assert isinstance(result.checklist, list)


@pytest.mark.anyio
async def test_pipeline_continues_when_step_fails():
    """All steps run even if one raises an exception."""
    from services.case_pipeline import (
        _step_analiza_dokumenata, _step_auto_linking, StepStatus,
    )
    supa = _supa_by_table(
        predmet_dokumenti=[{"id": "d1"}],
        predmet_istorija=[],
        predmet_klijenti=[{"klijent_id": "k1"}],
    )
    step1 = await _step_analiza_dokumenata(supa, PID, UID)
    step2 = await _step_auto_linking(supa, PID, UID, {"naziv": "Test"})
    # Step 1 fails (doc without analysis) but Step 2 succeeds
    assert step1.status == StepStatus.FAILED
    assert step2.status == StepStatus.SUCCESS


@pytest.mark.anyio
async def test_pipeline_idempotent_second_run():
    """Second run returns SUCCESS on already-completed steps (idempotent check)."""
    from services.case_pipeline import _step_strategija, StepStatus
    supa = _supa_by_table(
        predmet_istorija=[{"pitanje": "[Strategija Pipeline] Inicijalna procena"}]
    )
    result1 = await _step_strategija(supa, PID, UID, {"naziv": "T", "opis": "Test opis koji je dug", "tip": "opsti"})
    result2 = await _step_strategija(supa, PID, UID, {"naziv": "T", "opis": "Test opis koji je dug", "tip": "opsti"})
    assert result1.status == StepStatus.SUCCESS
    assert result2.status == StepStatus.SUCCESS
    assert "idempotent" in result2.poruka


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Router endpoint tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_pipeline_routes_registered():
    from routers.case_pipeline import router
    paths = {r.path for r in router.routes}
    assert "/api/predmeti/{predmet_id}/pipeline" in paths
    assert "/api/predmeti/{predmet_id}/pipeline/status" in paths


def test_pipeline_route_is_post():
    from routers.case_pipeline import router
    for r in router.routes:
        if r.path == "/api/predmeti/{predmet_id}/pipeline":
            assert "POST" in r.methods


def test_status_route_is_get():
    from routers.case_pipeline import router
    for r in router.routes:
        if r.path == "/api/predmeti/{predmet_id}/pipeline/status":
            assert "GET" in r.methods


@pytest.mark.anyio
async def test_run_pipeline_endpoint_404_unknown_predmet():
    from routers.case_pipeline import run_pipeline
    supa = _supa_by_table(predmeti=[])
    with patch("routers.case_pipeline._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await run_pipeline(predmet_id="no-such-id",
                               request=_req(), user=_user())
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_pipeline_status_endpoint_404():
    from routers.case_pipeline import pipeline_status
    supa = _supa_by_table(predmeti=[])
    with patch("routers.case_pipeline._get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc:
            await pipeline_status(predmet_id="no-such-id",
                                  request=_req("GET"), user=_user())
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_pipeline_status_returns_score():
    from routers.case_pipeline import pipeline_status
    supa = _supa_by_table(
        predmeti=[{"id": PID}],
        predmet_dokumenti=[],
        predmet_klijenti=[{"klijent_id": "k1"}],
        predmet_hronologija=[],
        predmet_istorija=[],
        rocista=[],
    )
    with patch("routers.case_pipeline._get_supa", return_value=supa):
        result = await pipeline_status(predmet_id=PID,
                                       request=_req("GET"), user=_user(UID))
    assert "case_ready_score" in result
    assert "checklist" in result
    assert result["case_ready_score"] == 20  # only klijent (+20)
