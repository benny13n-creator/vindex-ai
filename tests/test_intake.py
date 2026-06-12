# -*- coding: utf-8 -*-
"""
Tests for /api/intake/ekstrakcija and /api/intake/kreiraj

Mocks: OpenAI (ekstrakcija), Supabase (kreiraj)
All tests run without live services.
"""
import sys, os, json
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
