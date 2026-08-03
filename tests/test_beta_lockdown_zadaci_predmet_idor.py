# -*- coding: utf-8 -*-
"""
Operation Beta Lockdown (2026-08-03): GET /api/zadaci/predmet/{predmet_id}
(routers/zadaci.py::zadaci_za_predmet) had ZERO ownership verification --
it took predmet_id directly from the URL and returned every row in
`zadaci` filtered only by predmet_id, with no check that the calling user
even has access to that case. Any authenticated user who obtained another
firm's predmet_id (a leaked URL, a screenshot, a support ticket -- UUIDs
aren't brute-forceable, but they do leak through normal channels) could
read that firm's complete task list: names, descriptions, deadlines,
assignees. A real, live, exploitable cross-tenant leak (IDOR), not
theoretical -- found by an isolation spot-check, not a bug report.

This is an isolated omission, not a systemic issue: every comparable
{predmet_id}-scoped endpoint in the SAME file (e.g. ai_analiziraj_predmet,
~90 lines below) already does exactly this ownership check. Fix mirrors
that established in-file pattern: verify predmeti.eq("id",...).eq("user_id",...)
before touching zadaci; a non-owned or non-existent predmet_id gets 404,
identical to how every other endpoint in this file already behaves --
no existence-vs-ownership oracle for an attacker to exploit.

User Scenario Test: a lawyer opens a case they don't own (by URL, by
mistake, or via an attacker probing IDs) -- must get "not found", never
another firm's real task data.
"""
import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

import routers.zadaci as zadaci  # noqa: E402


def _make_supa(predmet_owned: bool, zadaci_rows=None):
    """predmeti table returns a row only if `predmet_owned` -- mirrors what
    a real .eq("id",...).eq("user_id",...) filter would do: a case that
    exists but belongs to someone else looks identical to one that doesn't
    exist at all (no existence-vs-ownership oracle)."""
    supa = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = (
                {"id": "pred-1"} if predmet_owned else None
            )
        elif name == "zadaci":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = (
                zadaci_rows or []
            )
        return t

    supa.table.side_effect = _table
    return supa


def test_owner_can_read_their_own_case_tasks():
    other_firms_tasks = [
        {"id": "z1", "naziv": "Pripremiti odgovor na tuzbu", "predmet_id": "pred-1"},
    ]
    supa = _make_supa(predmet_owned=True, zadaci_rows=other_firms_tasks)

    with patch.object(zadaci, "_get_supa", return_value=supa):
        result = asyncio.run(zadaci.zadaci_za_predmet.__wrapped__(
            "pred-1", request=MagicMock(), user={"user_id": "owner-uid"},
        ))

    assert result["zadaci"] == other_firms_tasks


def test_non_owner_cannot_read_another_firms_case_tasks():
    """The core regression guard: a predmet_id the caller does NOT own must
    never return another firm's task data."""
    another_firms_tasks = [
        {"id": "z1", "naziv": "SECRET -- confidential deadline for firm A", "predmet_id": "pred-A"},
    ]
    supa = _make_supa(predmet_owned=False, zadaci_rows=another_firms_tasks)

    with patch.object(zadaci, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(zadaci.zadaci_za_predmet.__wrapped__(
                "pred-A", request=MagicMock(), user={"user_id": "attacker-uid"},
            ))

    assert exc_info.value.status_code == 404


def test_nonexistent_predmet_id_rejected_identically_to_someone_elses():
    """No existence-vs-ownership oracle: a predmet_id that doesn't exist at
    all must produce the exact same 404 as one that exists but isn't
    owned by the caller -- never a different error an attacker could use
    to enumerate real case IDs."""
    supa = _make_supa(predmet_owned=False)

    with patch.object(zadaci, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(zadaci.zadaci_za_predmet.__wrapped__(
                "does-not-exist", request=MagicMock(), user={"user_id": "someone"},
            ))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Predmet nije pronađen."


def test_zadaci_query_never_runs_when_ownership_check_fails():
    """Direct proof the fix actually prevents the data read, not just
    wraps it in a try/except that happens to succeed."""
    supa = _make_supa(predmet_owned=False, zadaci_rows=[{"id": "leaked"}])

    with patch.object(zadaci, "_get_supa", return_value=supa):
        with pytest.raises(HTTPException):
            asyncio.run(zadaci.zadaci_za_predmet.__wrapped__(
                "pred-X", request=MagicMock(), user={"user_id": "attacker"},
            ))

    zadaci_table_calls = [c for c in supa.table.call_args_list if c.args == ("zadaci",)]
    assert not zadaci_table_calls, "the zadaci table must never be queried when ownership fails"
