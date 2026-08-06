# -*- coding: utf-8 -*-
"""
Program Lambda, Certification 003 (2026-08-06) -- Authorization Architect
fork found, and the Adversarial Certification fork independently
re-confirmed, that klijenti/router.py::_get_role() treated a DB read
EXCEPTION (network blip, RLS misconfiguration, connection pool exhaustion)
identically to "user has no user_roles row yet" -- both silently returned
DEFAULT_ROLE (Role.ADVOKAT), which passes can_perform() for
access_confidential/archive_client/view_conflict_results. Contrast:
_get_firma_info (routers/zadaci.py) and _verify_owns_klijent (this same
file) both correctly fail CLOSED on the identical exception shape.

Fix: on exception, _get_role now returns the LOWEST role (Role.SEKRETARICA)
instead of DEFAULT_ROLE. The genuinely-no-row-yet case (a real, intentional
product default for newly onboarded users) is unchanged -- it still returns
DEFAULT_ROLE (Role.ADVOKAT). Only the "we don't actually know" case changed.
"""
import sys
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from klijenti.router import _get_role  # noqa: E402
from klijenti.permissions import Role, DEFAULT_ROLE, can_perform  # noqa: E402


def test_db_exception_fails_closed_to_lowest_role():
    """A transient DB error reading user_roles must never grant DEFAULT_ROLE
    (ADVOKAT) -- it must grant the lowest role, SEKRETARICA."""
    mock_supa = MagicMock()
    mock_supa.table.side_effect = RuntimeError("connection reset")

    with patch("klijenti.router._is_founder", return_value=False), \
         patch("klijenti.router._get_supa", return_value=mock_supa):
        role = _get_role("uid-1", "advokat@vindex.rs")

    assert role == Role.SEKRETARICA
    assert role != DEFAULT_ROLE


def test_db_exception_role_cannot_access_confidential_fields():
    """The whole point of the fix: a role granted during a DB failure must
    not pass the access_confidential permission check that DEFAULT_ROLE
    (ADVOKAT) would have passed."""
    mock_supa = MagicMock()
    mock_supa.table.side_effect = RuntimeError("connection reset")

    with patch("klijenti.router._is_founder", return_value=False), \
         patch("klijenti.router._get_supa", return_value=mock_supa):
        role = _get_role("uid-1", "advokat@vindex.rs")

    assert can_perform(role, "access_confidential") is False
    # Prove this is a real behavior change: DEFAULT_ROLE itself DOES pass.
    assert can_perform(DEFAULT_ROLE, "access_confidential") is True


def test_no_role_row_yet_still_gets_intentional_default_not_lowest():
    """No regression: a genuinely new user with zero user_roles rows (not an
    error -- res.data is an empty list) must still get the intentional
    product default, DEFAULT_ROLE (ADVOKAT), not the fail-closed lowest role."""
    mock_query = MagicMock()
    mock_query.data = []
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_query

    with patch("klijenti.router._is_founder", return_value=False), \
         patch("klijenti.router._get_supa", return_value=mock_supa):
        role = _get_role("uid-new", "novi@vindex.rs")

    assert role == DEFAULT_ROLE


def test_real_role_row_still_returned_correctly():
    """No regression: a real, successfully-read role row must still be
    honored exactly as before."""
    mock_query = MagicMock()
    mock_query.data = [{"rola": "partner"}]
    mock_supa = MagicMock()
    mock_supa.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_query

    with patch("klijenti.router._is_founder", return_value=False), \
         patch("klijenti.router._get_supa", return_value=mock_supa):
        role = _get_role("uid-partner", "partner@vindex.rs")

    assert role == Role.PARTNER


def test_founder_unaffected_by_exception_path():
    """No regression: founder short-circuit must still work even if the
    (never-reached) DB path would have thrown."""
    mock_supa = MagicMock()
    mock_supa.table.side_effect = RuntimeError("should never be called for founder")

    with patch("klijenti.router._is_founder", return_value=True), \
         patch("klijenti.router._get_supa", return_value=mock_supa):
        role = _get_role("uid-founder", "founder@vindex.rs")

    assert role == Role.PARTNER
