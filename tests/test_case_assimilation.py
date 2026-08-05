# -*- coding: utf-8 -*-
"""
Program Intake Sprint 006 (2026-08-05) — "Canonical Case Assimilation".
Tests for shared/case_assimilation.py's Ownership Resolution logic.

Mission's own governing rule, checked throughout: "Ako sistem ne može
dokazati da dokument pripada određenom predmetu ili klijentu, mora ga
zadržati u kontrolisanom stanju (Review Required)." Every ambiguous-match
test below exists because a document assigned to the wrong case/client is a
more serious problem than ten documents waiting for a human to confirm.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared.case_assimilation import (
    normalize_case_number, looks_like_company, split_person_name,
    find_conflicting_case_numbers,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ═══════════════════════════════════════════════════════════════════════════
# Pure helpers
# ═══════════════════════════════════════════════════════════════════════════

def test_normalize_case_number_collapses_whitespace():
    assert normalize_case_number("  П.  бр.   100/24  ") == "П. бр. 100/24"


def test_normalize_case_number_none_for_empty_or_none():
    assert normalize_case_number("") is None
    assert normalize_case_number("   ") is None
    assert normalize_case_number(None) is None


def test_looks_like_company_detects_doo_suffix():
    assert looks_like_company("Petrović Trans d.o.o.") is True
    assert looks_like_company("PETROVIĆ TRANS DOO") is True


def test_looks_like_company_does_not_false_positive_on_surname_containing_ad():
    """'Adamović' must not match the 'ad' company-suffix token via substring
    containment -- looks_like_company uses whole-token matching."""
    assert looks_like_company("Marko Adamović") is False


def test_split_person_name_first_token_is_ime():
    assert split_person_name("Marko Marković") == ("Marko", "Marković")


def test_split_person_name_single_word_gets_empty_prezime():
    assert split_person_name("Preduzetnik") == ("Preduzetnik", "")


def test_find_conflicting_case_numbers_empty_when_all_agree():
    assert find_conflicting_case_numbers(["П. 100/24", "П. 100/24", None]) == set()


def test_find_conflicting_case_numbers_empty_when_only_one_has_a_number():
    assert find_conflicting_case_numbers(["П. 100/24", None, None]) == set()


def test_find_conflicting_case_numbers_detects_genuine_multi_case_bundle():
    conflicting = find_conflicting_case_numbers(["П. 100/24", "П. 200/24", None])
    # Program Intake Sprint 007 -- canonicalized form (normalize_case_number
    # is what find_conflicting_case_numbers applies internally).
    assert conflicting == {"П100/24", "П200/24"}


# ═══════════════════════════════════════════════════════════════════════════
# resolve_case_ownership — never guesses between 2+ matching cases
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_resolve_case_ownership_no_case_number_creates_new():
    from shared.case_assimilation import resolve_case_ownership
    result = await resolve_case_ownership("user-1", None)
    assert result == {"outcome": "create_new", "case_number": None}


@pytest.mark.anyio
async def test_resolve_case_ownership_zero_matches_creates_new():
    from shared.case_assimilation import resolve_case_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_case_ownership("user-1", "П. 999/24")
    assert result["outcome"] == "create_new"
    # Program Intake Sprint 007 -- normalize_case_number now canonicalizes
    # (no separator before the number, slash before the year), not just
    # whitespace-collapses.
    assert result["case_number"] == "П999/24"


@pytest.mark.anyio
async def test_resolve_case_ownership_exactly_one_match_attaches():
    from shared.case_assimilation import resolve_case_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "pred-EXISTING", "naziv": "Petrović protiv Markovića"},
    ]
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_case_ownership("user-1", "П. 100/24")
    assert result == {"outcome": "attach", "predmet_id": "pred-EXISTING", "naziv": "Petrović protiv Markovića"}


@pytest.mark.anyio
async def test_resolve_case_ownership_two_matches_never_guesses():
    """Never picks one -- mission's own absolute rule, applied even to a
    rare/unexpected data state (case numbers have no uniqueness constraint
    today)."""
    from shared.case_assimilation import resolve_case_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": "pred-A", "naziv": "A"}, {"id": "pred-B", "naziv": "B"},
    ]
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_case_ownership("user-1", "П. 100/24")
    assert result["outcome"] == "review_required"
    assert len(result["candidates"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# resolve_client_ownership — the mission's own named "two clients, same
# surname" edge case, and the correctly-fixed full-name matching bug.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_resolve_client_ownership_empty_name_creates_new():
    from shared.case_assimilation import resolve_client_ownership
    result = await resolve_client_ownership("user-1", "")
    assert result["outcome"] == "create_new"


@pytest.mark.anyio
async def test_resolve_client_ownership_full_name_exact_match():
    """The core bug fix: klijenti.ime is first-name-only, but the extracted
    party name is a full 'First Last' string -- must compare against the
    correctly concatenated ime+prezime, not ime alone."""
    from shared.case_assimilation import resolve_client_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.ilike.return_value.neq.return_value.execute.return_value.data = [
        {"id": "kl-001", "ime": "Ana", "prezime": "Jović"},
    ]
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_client_ownership("user-1", "Ana Jović")
    assert result == {"outcome": "match", "klijent_id": "kl-001"}


@pytest.mark.anyio
async def test_resolve_client_ownership_same_first_name_different_surname_does_not_match():
    """A candidate sharing only the first name (from the cheap ILIKE
    prefilter) must be excluded once the full-name comparison runs -- this
    is what the pre-Sprint-006 ime-only query could never distinguish."""
    from shared.case_assimilation import resolve_client_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.ilike.return_value.neq.return_value.execute.return_value.data = [
        {"id": "kl-999", "ime": "Ana", "prezime": "Petrović"},  # same "Ana", different surname
    ]
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_client_ownership("user-1", "Ana Jović")
    assert result["outcome"] == "create_new"


@pytest.mark.anyio
async def test_resolve_client_ownership_two_same_name_clients_is_ambiguous():
    """The mission's own named edge case: two clients with the same
    surname (here, identical full name) -- must never guess between them."""
    from shared.case_assimilation import resolve_client_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.ilike.return_value.neq.return_value.execute.return_value.data = [
        {"id": "kl-001", "ime": "Marko", "prezime": "Marković"},
        {"id": "kl-002", "ime": "Marko", "prezime": "Marković"},
    ]
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_client_ownership("user-1", "Marko Marković")
    assert result["outcome"] == "ambiguous"
    assert len(result["candidates"]) == 2


@pytest.mark.anyio
async def test_resolve_client_ownership_company_matches_against_firma_column():
    from shared.case_assimilation import resolve_client_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.ilike.return_value.neq.return_value.execute.return_value.data = [
        {"id": "kl-firma-1"},
    ]
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_client_ownership("user-1", "Petrović Trans d.o.o.")
    assert result == {"outcome": "match", "klijent_id": "kl-firma-1"}


@pytest.mark.anyio
async def test_resolve_client_ownership_new_company_gets_pravno_lice_type():
    from shared.case_assimilation import resolve_client_ownership
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.ilike.return_value.neq.return_value.execute.return_value.data = []
    with patch("shared.case_assimilation._get_supa", return_value=mock_supa):
        result = await resolve_client_ownership("user-1", "Petrović Trans d.o.o.")
    assert result["outcome"] == "create_new"
    assert result["tip"] == "pravno_lice"
    assert result["firma"] == "Petrović Trans d.o.o."
