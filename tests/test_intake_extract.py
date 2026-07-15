# -*- coding: utf-8 -*-
"""Tests for shared/intake_extract.py (Smart Intake Phase 1A — Confidence Graph)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_extract_case_number_matches_cyrillic():
    from shared.intake_extract import extract_case_number
    value, confidence = extract_case_number("Предмет П 341/26 пред Основним судом.")
    assert value == "П 341/26"
    assert confidence == 0.95


def test_extract_case_number_matches_latin():
    from shared.intake_extract import extract_case_number
    value, confidence = extract_case_number("Predmet Pž 1234/2025 pred Privrednim sudom.")
    assert value == "Pž 1234/2025"
    assert confidence == 0.95


def test_extract_case_number_none_when_absent():
    from shared.intake_extract import extract_case_number
    value, confidence = extract_case_number("Ovaj tekst ne sadrži broj predmeta.")
    assert value is None
    assert confidence == 0.0


def test_extract_amount_requires_currency():
    from shared.intake_extract import extract_amount
    value, confidence = extract_amount("Tužilac potražuje iznos od 48.200,00 РСД na ime naknade štete.")
    assert value == "48.200,00 РСД"
    assert confidence == 0.92


def test_extract_amount_bare_number_without_currency_is_not_matched():
    from shared.intake_extract import extract_amount
    # A bare number (page number, paragraph number...) must NOT be
    # misread as a monetary amount just because it has thousands formatting.
    value, confidence = extract_amount("Vidi tačku 48.200 pravilnika.")
    assert value is None
    assert confidence == 0.0


def test_extract_deadline_absolute_date_higher_confidence_than_relative():
    from shared.intake_extract import extract_deadline
    # "žalbu" is a legally-significant category (zalba) — gets the small
    # confidence bonus on top of the base absolute-date score (0.90+0.05).
    value, confidence = extract_deadline("Rok za žalbu je 15.11.2026.")
    assert value == "15.11.2026"
    assert confidence == pytest.approx(0.95)


def test_extract_deadline_prefers_legally_significant_date_over_first_mentioned():
    from shared.intake_extract import extract_deadline
    # Document date (03.06.2026) appears FIRST but has no legal-deadline
    # keyword nearby — the actual appeal deadline (15.11.2026) appears
    # later, near "žalba". Must pick the second one, not the first.
    text = "Presuda doneta dana 03.06.2026. godine. Rok za žalbu je 15.11.2026."
    value, confidence = extract_deadline(text)
    assert value == "15.11.2026"


def test_extract_deadline_cyrillic_zalba_category_recognized():
    from shared.intake_extract import extract_deadline
    # Regression test for the live-discovered bug: _kategorija() only
    # matched Latin keywords, so Cyrillic "жалба" never got categorized,
    # silently falling back to "ostalo" and picking the wrong date.
    text = "Пресуда донета дана 03.06.2026. Рок за жалбу је 15.11.2026."
    value, confidence = extract_deadline(text)
    assert value == "15.11.2026"


def test_extract_deadline_none_when_absent():
    from shared.intake_extract import extract_deadline
    value, confidence = extract_deadline("Ovaj dokument ne pominje nijedan rok.")
    assert value is None
    assert confidence == 0.0


@pytest.mark.anyio
async def test_extract_free_text_entities_parses_llm_response():
    from shared import intake_extract as ie

    fake_json = (
        '{"judge": {"value": "Marija Kovačević", "confidence": 0.9}, '
        '"plaintiff": {"value": "Petrović d.o.o.", "confidence": 0.85}, '
        '"defendant": {"value": null, "confidence": 0.0}, '
        '"court": {"value": "Osnovni sud u Beogradu", "confidence": 0.95}, '
        '"law_cited": {"value": null, "confidence": 0.0}}'
    )
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content=fake_json))]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await ie.extract_free_text_entities("neki pravni tekst")

    assert result["judge"] == ("Marija Kovačević", 0.9)
    assert result["defendant"] == (None, 0.0)
    assert result["court"] == ("Osnovni sud u Beogradu", 0.95)


@pytest.mark.anyio
async def test_extract_free_text_entities_handles_api_failure():
    from shared import intake_extract as ie

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=Exception("API down"))

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await ie.extract_free_text_entities("neki tekst")

    assert all(v == (None, 0.0) for v in result.values())
    assert set(result.keys()) == {"judge", "plaintiff", "defendant", "court", "law_cited"}


@pytest.mark.anyio
async def test_extract_all_entities_returns_all_eight_types():
    from shared import intake_extract as ie

    fake_free_text = {t: (None, 0.0) for t in ("judge", "plaintiff", "defendant", "court", "law_cited")}
    with patch("shared.intake_extract.extract_free_text_entities", new=AsyncMock(return_value=fake_free_text)):
        entities = await ie.extract_all_entities("П 341/26, iznos 1.000,00 РСД, rok 15.11.2026.")

    entity_types = {e["entity_type"] for e in entities}
    assert entity_types == set(ie.ENTITY_TYPES)
    case_number_entity = next(e for e in entities if e["entity_type"] == "case_number")
    assert case_number_entity["extraction_method"] == "regex"
    assert case_number_entity["value"] == "П 341/26"
