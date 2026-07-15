# -*- coding: utf-8 -*-
"""Tests for shared/intake_classify.py (Smart Intake Phase 1A)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_classify_heuristic_recognizes_cyrillic_lawsuit():
    from shared.intake_classify import classify_heuristic
    result = classify_heuristic("ТУЖБА\n\nОсновном суду у Београду\n\nТужилац: Петровић д.о.о...")
    assert result == ("lawsuit", 0.85)


def test_classify_heuristic_recognizes_latin_judgment():
    from shared.intake_classify import classify_heuristic
    result = classify_heuristic("PRESUDA U IME NARODA\n\nOsnovni sud u Novom Sadu...")
    assert result == ("judgment", 0.85)


def test_classify_heuristic_recognizes_appeal():
    from shared.intake_classify import classify_heuristic
    result = classify_heuristic("ŽALBA na presudu Osnovnog suda...")
    assert result == ("appeal", 0.85)


def test_classify_heuristic_only_checks_document_head():
    from shared.intake_classify import classify_heuristic
    # "TUŽBA" appears far past _HEAD_CHARS (400) — must NOT match, otherwise
    # a document that merely quotes/references a lawsuit somewhere in its
    # body would be misclassified.
    padding = "x" * 500
    result = classify_heuristic(padding + " TUŽBA ")
    assert result is None


def test_classify_heuristic_returns_none_when_nothing_matches():
    from shared.intake_classify import classify_heuristic
    assert classify_heuristic("Poštovani, u prilogu vam šaljem dokument.") is None


@pytest.mark.anyio
async def test_classify_llm_fallback_called_when_heuristic_fails():
    from shared import intake_classify as ic

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"document_type": "contract", "confidence": 0.72}'))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await ic.classify("Ovaj tekst ne sadrži nijednu očiglednu ključnu reč.")

    assert result == {"document_type": "contract", "confidence": 0.72, "method": "llm"}


@pytest.mark.anyio
async def test_classify_heuristic_skips_llm_entirely():
    from shared import intake_classify as ic

    with patch("shared.intake_classify.classify_llm", new=AsyncMock()) as mock_llm:
        result = await ic.classify("ТУЖБА против Јовановић д.о.о.")

    mock_llm.assert_not_awaited()
    assert result["method"] == "heuristic"
    assert result["document_type"] == "lawsuit"


@pytest.mark.anyio
async def test_classify_llm_rejects_unknown_type():
    from shared import intake_classify as ic

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content='{"document_type": "made_up_type", "confidence": 0.9}'))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        doc_type, confidence = await ic.classify_llm("neki tekst")

    assert doc_type == "other"
    assert confidence == 0.3


@pytest.mark.anyio
async def test_classify_llm_handles_api_failure_gracefully():
    from shared import intake_classify as ic

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=Exception("API down"))

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        doc_type, confidence = await ic.classify_llm("neki tekst")

    assert doc_type == "other"
    assert confidence == 0.0
