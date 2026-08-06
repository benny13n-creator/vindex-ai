# -*- coding: utf-8 -*-
"""
Tests for /api/intake/ekstrakcija and /api/intake/kreiraj

Mocks: OpenAI (ekstrakcija), Supabase (kreiraj)
All tests run without live services.
"""
import sys, os, json, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.requests import Request as StarletteRequest


def _fake_request():
    scope = {
        "type": "http",
        "method": "POST",
        "headers": [],
        "query_string": b"",
        "path": "/api/intake/kreiraj",
        "app": MagicMock(),
        "state": MagicMock(),
    }
    return StarletteRequest(scope=scope)

# Restrict anyio to asyncio backend (trio not installed)
@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── helpers ──────────────────────────────────────────────────────────────────

def _fake_user():
    return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "test@vindex.rs", "role": "advokat"}


def _mock_openai_response(content: str):
    """Build a minimal AsyncOpenAI response mock."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── ekstrakcija: entity extraction ───────────────────────────────────────────

@pytest.mark.anyio
async def test_call_ekstrakcija_radni_spor():
    """GPT call returns sensible fields for a radni spor description."""
    from routers.intake import _call_ekstrakcija

    expected = {
        "predlog_naziva_predmeta": "Radni spor — otkaz bez otkaznog roka",
        "protivna_strana": None,
        "vrsta_spora": "radni spor",
        "vrednost_spora": None,
        "prvi_rok": None,
        "rok_opis": None,
        "potrebni_dokumenti": ["Rešenje o otkazu", "Ugovor o radu"],
    }

    with patch("openai.AsyncOpenAI") as MockOAI:
        instance = AsyncMock()
        MockOAI.return_value = instance
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response(json.dumps(expected))
        )
        result = await _call_ekstrakcija(
            "Klijent je dobio otkaz bez otkaznog roka, traži naknadu štete.",
            []
        )

    assert result["vrsta_spora"] == "radni spor"
    assert result["prvi_rok"] is None
    assert isinstance(result["potrebni_dokumenti"], list)
    assert len(result["potrebni_dokumenti"]) >= 1


@pytest.mark.anyio
async def test_call_ekstrakcija_no_date_hallucination():
    """prvi_rok must be null when no date is mentioned in the description."""
    from routers.intake import _call_ekstrakcija

    ai_resp = {
        "predlog_naziva_predmeta": "Naknada štete",
        "protivna_strana": None,
        "vrsta_spora": "naknada štete",
        "vrednost_spora": None,
        "prvi_rok": None,          # must stay null — no date in description
        "rok_opis": None,
        "potrebni_dokumenti": ["Medicinsku dokumentaciju"],
    }

    with patch("openai.AsyncOpenAI") as MockOAI:
        instance = AsyncMock()
        MockOAI.return_value = instance
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response(json.dumps(ai_resp))
        )
        result = await _call_ekstrakcija(
            "Klijent je povređen na radu i traži naknadu štete.",
            []
        )

    assert result["prvi_rok"] is None, "prvi_rok mora biti null jer datum nije pomenut"


@pytest.mark.anyio
async def test_call_ekstrakcija_with_findings():
    """Findings from analiza are included in the prompt context."""
    from routers.intake import _call_ekstrakcija

    ai_resp = {
        "predlog_naziva_predmeta": "Ugovorni spor",
        "protivna_strana": "XYZ d.o.o.",
        "vrsta_spora": "ugovorni spor",
        "vrednost_spora": "1000000 RSD",
        "prvi_rok": None,
        "rok_opis": None,
        "potrebni_dokumenti": ["Ugovor", "Fakture"],
    }

    with patch("openai.AsyncOpenAI") as MockOAI:
        instance = AsyncMock()
        MockOAI.return_value = instance
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response(json.dumps(ai_resp))
        )
        result = await _call_ekstrakcija(
            "Klijent tvrdi da ugovor nije ispunjen od strane XYZ d.o.o.",
            [{"severity": "visok", "finding": "Klauzula o penalima je nejasna"}],
        )

    assert result["protivna_strana"] == "XYZ d.o.o."
    assert result["vrednost_spora"] == "1000000 RSD"
    # Verify the OpenAI call actually happened
    MockOAI.return_value.chat.completions.create.assert_awaited_once()


# ── kreiraj: predmet creation ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_intake_kreiraj_without_rok():
    """Creates predmet + links klijent; no rok inserted when prvi_rok is None."""
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    new_predmet = {
        "id": "pred-abc-123",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "naziv": "Radni spor Petrović",
        "opis": "Klijent dobio otkaz",
        "tip": "radni",
        "status": "aktivan",
    }

    mock_supa = MagicMock()
    mock_supa.table.return_value.insert.return_value.execute.return_value.data = [new_predmet]
    # Program Lambda, Certification 004: intake_kreiraj now checks for a
    # recent duplicate before inserting -- empty result means "no duplicate found".
    mock_supa.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []

    req = IntakeKreirajReq(
        klijent_id="kl-id-0001",
        naziv="Radni spor Petrović",
        opis="Klijent dobio otkaz",
        tip="radni",
        vrsta_spora="radni spor",
        prvi_rok=None,
    )
    mock_request = _fake_request()

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_kreiraj(req, mock_request, _fake_user())

    assert result["success"] is True
    assert result["predmet_id"] == "pred-abc-123"
    assert result["rok_dodat"] is False


@pytest.mark.anyio
async def test_intake_kreiraj_with_rok():
    """When prvi_rok is set, inserts into predmet_hronologija."""
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    new_predmet = {
        "id": "pred-xyz-456",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "naziv": "Tužba za naknadu",
        "opis": "",
        "tip": "opsti",
        "status": "aktivan",
    }

    insert_calls = []

    def _table_side_effect(table_name):
        mock_t = MagicMock()
        mock_t.insert.return_value.execute.return_value.data = [new_predmet] if table_name == "predmeti" else []
        # Program Lambda, Certification 004: recent-duplicate check before insert.
        mock_t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
        insert_calls.append(table_name)
        return mock_t

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table_side_effect

    req = IntakeKreirajReq(
        klijent_id="kl-id-0002",
        naziv="Tužba za naknadu",
        prvi_rok="2026-09-15",
        rok_opis="Rok zastarelosti",
    )
    mock_request = _fake_request()

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_kreiraj(req, mock_request, _fake_user())

    assert result["rok_dodat"] is True
    assert "predmet_hronologija" in insert_calls


# ── Night Shift M-013 (2026-08-02): intake_kreiraj must trigger the Case Pipeline ──

@pytest.mark.anyio
async def test_intake_kreiraj_triggers_case_pipeline():
    """User scenario: a lawyer creates a case via the primary AI-assisted flow
    (POST /api/intake/kreiraj) -- the 9-step Case Pipeline must run in the
    background afterward, the same way it already does for
    POST /api/intake/from-template and POST /api/predmeti (M-002 finding:
    this was the one major case-creation path missing the trigger)."""
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    new_predmet = {
        "id": "pred-pipeline-001",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "naziv": "Radni spor Jovanović",
        "opis": "",
        "tip": "radni",
        "status": "aktivan",
    }
    mock_supa = MagicMock()
    mock_supa.table.return_value.insert.return_value.execute.return_value.data = [new_predmet]
    mock_supa.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []

    req = IntakeKreirajReq(klijent_id="kl-pipeline-001", naziv="Radni spor Jovanović")
    mock_request = _fake_request()

    captured_coro = {}

    def _capture_create_task(coro, *a, **kw):
        captured_coro["coro"] = coro
        return MagicMock()  # stand-in Task object, never actually scheduled by the event loop here

    with patch("routers.intake._get_supa", return_value=mock_supa), \
         patch("asyncio.create_task", side_effect=_capture_create_task), \
         patch("services.case_pipeline.run_case_pipeline", new=AsyncMock()) as mock_pipeline:
        result = await intake_kreiraj(req, mock_request, _fake_user())
        assert "coro" in captured_coro, "intake_kreiraj must schedule a background pipeline task"
        await captured_coro["coro"]  # run what create_task would have scheduled

    assert result["predmet_id"] == "pred-pipeline-001"
    mock_pipeline.assert_awaited_once_with("pred-pipeline-001", "00000000-0000-0000-0000-000000000001")


@pytest.mark.anyio
async def test_intake_kreiraj_pipeline_failure_does_not_break_response():
    """The pipeline trigger is fire-and-forget -- if it raises, the case
    creation response must already have been returned successfully (this
    mirrors post_from_template's existing, established error-handling
    pattern for the same call)."""
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    new_predmet = {
        "id": "pred-pipeline-002",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "naziv": "Ugovorni spor",
        "opis": "",
        "tip": "opsti",
        "status": "aktivan",
    }
    mock_supa = MagicMock()
    mock_supa.table.return_value.insert.return_value.execute.return_value.data = [new_predmet]
    mock_supa.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []

    req = IntakeKreirajReq(klijent_id="kl-pipeline-002", naziv="Ugovorni spor")
    mock_request = _fake_request()

    captured_coro = {}

    def _capture_create_task(coro, *a, **kw):
        captured_coro["coro"] = coro
        return MagicMock()

    with patch("routers.intake._get_supa", return_value=mock_supa), \
         patch("asyncio.create_task", side_effect=_capture_create_task), \
         patch("services.case_pipeline.run_case_pipeline", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await intake_kreiraj(req, mock_request, _fake_user())
        await captured_coro["coro"]  # must not raise -- caught and logged inside _run_pipeline

    assert result["success"] is True


def test_ekstrakcija_req_min_length():
    """EkstrakcijReq rejects descriptions shorter than 20 characters."""
    from pydantic import ValidationError
    from routers.intake import EkstrakcijReq

    with pytest.raises(ValidationError):
        EkstrakcijReq(opis_problema="Kratak")


def test_intake_kreiraj_req_naziv_required():
    """IntakeKreirajReq requires at least 2-char naziv."""
    from pydantic import ValidationError
    from routers.intake import IntakeKreirajReq

    with pytest.raises(ValidationError):
        IntakeKreirajReq(klijent_id="kl-0001", naziv="X")  # 1 char — fails min_length=2


# ═══════════════════════════════════════════════════════════════════════════
# Program Lambda, Certification 004 (2026-08-06) -- Chaos Engineer +
# Database Reliability forks both independently found (Adversarial
# Certification-confirmed) that intake_kreiraj had zero protection against
# a double-click/duplicate submit: a bare INSERT, no idempotency key, no
# recent-duplicate check. A near-simultaneous resubmit created 2 real
# predmeti rows, each triggering its own Case Pipeline.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_intake_kreiraj_rejects_near_duplicate_submission():
    """A second, near-simultaneous request with the same naziv (the
    double-click scenario) must be rejected with a clean 409, not create a
    second case."""
    from fastapi import HTTPException
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    mock_supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            # A case with the same naziv, created 1 second ago -- inside
            # the dedup window.
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = [
                {"id": "pred-original", "created_at": "2026-08-06T12:00:00+00:00"}
            ]
        return t
    mock_supa.table.side_effect = _table

    req = IntakeKreirajReq(klijent_id="kl-0001", naziv="Radni spor Petrović")

    with patch("routers.intake._get_supa", return_value=mock_supa):
        with pytest.raises(HTTPException) as exc:
            await intake_kreiraj(req, _fake_request(), _fake_user())

    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_intake_kreiraj_allows_same_name_outside_dedup_window():
    """No regression: a genuinely separate case creation (no recent
    duplicate found -- the normal case) must still succeed."""
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    new_predmet = {
        "id": "pred-new-1", "user_id": _fake_user()["user_id"],
        "naziv": "Radni spor Petrović", "opis": "", "tip": "opsti", "status": "aktivan",
    }
    mock_supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [new_predmet]
        return t
    mock_supa.table.side_effect = _table

    req = IntakeKreirajReq(klijent_id="kl-0001", naziv="Radni spor Petrović")

    with patch("routers.intake._get_supa", return_value=mock_supa):
        result = await intake_kreiraj(req, _fake_request(), _fake_user())

    assert result["success"] is True
    assert result["predmet_id"] == "pred-new-1"


@pytest.mark.anyio
async def test_intake_kreiraj_writes_predmet_create_audit_entry():
    """Program Lambda, Certification 005 (2026-08-07): an Audit Continuity
    fork found this endpoint -- the Intake Wizard's own case-creation path --
    left zero audit trail, unlike api.py::kreiraj_predmet (the OTHER
    case-creation path), which already logs 'predmet_create'. A case created
    through the wizard must be equally auditable."""
    from routers.intake import IntakeKreirajReq, intake_kreiraj

    new_predmet = {
        "id": "pred-audit-1", "user_id": _fake_user()["user_id"],
        "naziv": "Radni spor Petrović", "opis": "", "tip": "opsti", "status": "aktivan",
    }
    mock_supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value.data = []
            t.insert.return_value.execute.return_value.data = [new_predmet]
        return t
    mock_supa.table.side_effect = _table

    req = IntakeKreirajReq(klijent_id="kl-0001", naziv="Radni spor Petrović")

    with patch("routers.intake._get_supa", return_value=mock_supa), \
         patch("shared.audit_immutable.log_action", new=AsyncMock()) as mock_log:
        result = await intake_kreiraj(req, _fake_request(), _fake_user())
        # log_action is scheduled via asyncio.create_task -- give the loop a
        # tick so the fire-and-forget task actually runs before asserting.
        await asyncio.sleep(0)

    assert result["success"] is True
    mock_log.assert_awaited_once()
    call_args = mock_log.await_args
    assert call_args.args[0] == "predmet_create"
    assert call_args.kwargs["resource_id"] == "pred-audit-1"
    assert call_args.kwargs["user_id"] == _fake_user()["user_id"]
