# -*- coding: utf-8 -*-
"""
Regression tests for SEC-001 (docs/security/SECURITY_GAP_REGISTER.md).

Vulnerability: POST /api/predmeti/{predmet_id}/beleske and
POST /api/predmeti/{predmet_id}/istorija (api.py) inserted using a
predmet_id taken directly from the URL, with no check that the predmet
belonged to the calling user. Any authenticated user could inject a
note/history entry into another user's case file, and because the
sibling GET (get_predmet, api.py:3161-3171) correctly gates the parent
predmeti row but fetches beleske/istorija filtered only by predmet_id,
the injected content became visible to the victim on their next read.

Full sweep performed before this fix (per founder's explicit request):
every other {predmet_id}-scoped mutation across api.py and all router
files already applies the same ownership check via one of three
existing patterns (inline .eq("id",...).eq("user_id",...), a named
helper like _dohvati_predmet/_proveri_vlasnistvo, or PermissionService-
gated + inline check). dodaj_belesku and sacuvaj_istoriju were the only
two exceptions. This file tests exactly those two, plus confirms the
fix does not special-case founder/admin status (ownership is a strict
data-boundary check, unrelated to feature-gating or credit exemptions).

Pure unit tests -- no live Supabase, no OpenAI. Mocks _get_supa and
_require_auth directly (api.py's auth style differs from the router
files' Depends(get_current_user) pattern -- it decodes the Authorization
header manually via _require_auth()).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json as _json
import types
import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request as StarletteRequest

import api


@pytest.fixture
def anyio_backend():
    return "asyncio"


USER_A = "user-aaaa-0000-0000-000000000001"
USER_B = "user-bbbb-0000-0000-000000000002"
PREDMET_OF_A = "pred-aaaa-0000-0000-000000000001"


def _fake_user(uid: str, email: str = "test@vindex.rs"):
    return types.SimpleNamespace(id=uid, email=email)


def _req(body: dict, path: str = "/api/predmeti/x/beleske") -> StarletteRequest:
    """Real starlette Request (not a bare MagicMock) -- @limiter.limit does a
    strict isinstance(request, Request) check, and reads request.client for
    the rate-limit key. Wires a real `receive` callable so `await
    request.json()` works, since these two endpoints read the body."""
    body_bytes = _json.dumps(body).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": path,
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


def _chain(data):
    c = MagicMock()
    for m in ["select", "eq", "insert", "execute", "single"]:
        setattr(c, m, MagicMock(return_value=c))
    r = MagicMock()
    r.data = data
    c.execute = MagicMock(return_value=r)
    return c


def _supa_owns_only(owned_predmet_id: str, owner_user_id: str = USER_A, beleska_insert_result=None):
    """Supabase double: `predmeti` ownership check only returns a row when
    BOTH .eq("id", predmet_id) AND .eq("user_id", uid) match the real
    (predmet_id, owner) pair -- this is the actual boundary the fix is
    supposed to enforce, so the mock must model both filters, not just the
    id, or a broken fix and a correct fix would look identical to these
    tests."""
    supa = MagicMock()

    def _table(name):
        if name == "predmeti":
            calls = {"id": None, "user_id": None}
            c = MagicMock()

            def _eq(field, value):
                if field in calls:
                    calls[field] = value
                return c
            c.select = MagicMock(return_value=c)
            c.eq = MagicMock(side_effect=_eq)

            def _execute():
                r = MagicMock()
                matches = calls["id"] == owned_predmet_id and calls["user_id"] == owner_user_id
                r.data = {"id": owned_predmet_id} if matches else None
                return r
            c.single = MagicMock(return_value=c)
            c.execute = MagicMock(side_effect=_execute)
            return c
        if name == "predmet_beleske":
            return _chain(beleska_insert_result if beleska_insert_result is not None else [{"id": "beleska-1", "sadrzaj": "x"}])
        if name == "predmet_istorija":
            return _chain([{"id": "istorija-1"}])
        return _chain([])

    supa.table.side_effect = _table
    return supa


# ═══════════════════════════════════════════════════════════════════════════
# dodaj_belesku — POST /api/predmeti/{predmet_id}/beleske
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_user_a_cannot_inject_note_into_user_b_predmet():
    """The exact SEC-001 exploit: User B (attacker) POSTs a note to a
    predmet_id that belongs to User A. Must be rejected, not inserted."""
    supa = _supa_owns_only(owned_predmet_id=PREDMET_OF_A)
    req = _req({"sadrzaj": "injected malicious note"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user(USER_B)):
        with pytest.raises(api.HTTPException) as exc:
            await api.dodaj_belesku(PREDMET_OF_A, req, "Bearer fake-token-for-user-b")
    assert exc.value.status_code == 404
    # The critical assertion: no insert into predmet_beleske was attempted.
    beleske_table = supa.table("predmet_beleske")
    beleske_table.insert.assert_not_called()


@pytest.mark.anyio
async def test_owner_can_still_add_note_to_own_predmet():
    """The fix must not break the legitimate path -- User A adding a note
    to their own predmet must still succeed exactly as before."""
    supa = _supa_owns_only(owned_predmet_id=PREDMET_OF_A)
    req = _req({"sadrzaj": "legitimate note"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user(USER_A)):
        result = await api.dodaj_belesku(PREDMET_OF_A, req, "Bearer fake-token-for-user-a")
    assert "beleska" in result


@pytest.mark.anyio
async def test_founder_status_does_not_bypass_ownership_check():
    """Founder/admin exemptions in this codebase apply to billing and
    feature-gating (UsageService, PermissionService) -- NOT to data
    ownership. A founder account must be rejected exactly like any other
    non-owner; this fix intentionally does not special-case founder email."""
    supa = _supa_owns_only(owned_predmet_id=PREDMET_OF_A)
    req = _req({"sadrzaj": "founder trying to write into someone else's case"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user(USER_B, email="benny13.n@gmail.com")):
        with pytest.raises(api.HTTPException) as exc:
            await api.dodaj_belesku(PREDMET_OF_A, req, "Bearer fake-token-founder")
    assert exc.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# sacuvaj_istoriju — POST /api/predmeti/{predmet_id}/istorija
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_user_a_cannot_inject_history_into_user_b_predmet():
    """Same exploit shape, second endpoint."""
    supa = _supa_owns_only(owned_predmet_id=PREDMET_OF_A)
    req = _req({"pitanje": "x", "odgovor": "injected", "confidence": "HIGH"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user(USER_B)):
        with pytest.raises(api.HTTPException) as exc:
            await api.sacuvaj_istoriju(PREDMET_OF_A, req, "Bearer fake-token-for-user-b")
    assert exc.value.status_code == 404
    istorija_table = supa.table("predmet_istorija")
    istorija_table.insert.assert_not_called()


@pytest.mark.anyio
async def test_owner_can_still_save_history_to_own_predmet():
    supa = _supa_owns_only(owned_predmet_id=PREDMET_OF_A)
    req = _req({"pitanje": "x", "odgovor": "y", "confidence": "HIGH"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user(USER_A)):
        result = await api.sacuvaj_istoriju(PREDMET_OF_A, req, "Bearer fake-token-for-user-a")
    assert result == {"ok": True}


@pytest.mark.anyio
async def test_nonexistent_predmet_id_rejected_same_as_someone_elses():
    """A guessed/random predmet_id that doesn't exist at all must fail the
    same way as one that exists but belongs to someone else -- no
    existence-vs-ownership distinction that could leak which UUIDs are real."""
    supa = _supa_owns_only(owned_predmet_id=PREDMET_OF_A)
    req = _req({"pitanje": "x", "odgovor": "y", "confidence": "HIGH"})
    with patch("api._get_supa", return_value=supa), \
         patch("api._require_auth", return_value=_fake_user(USER_A)):
        with pytest.raises(api.HTTPException) as exc:
            await api.sacuvaj_istoriju("pred-does-not-exist-at-all", req, "Bearer fake-token-for-user-a")
    assert exc.value.status_code == 404
