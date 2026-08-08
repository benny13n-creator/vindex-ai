# -*- coding: utf-8 -*-
"""
Final Beta Gate — F12 (HIGH): "klijent_delete" has been declared in
shared/audit_immutable.py's AUDITABLE_ACTIONS since that allowlist was
written, implying every client deletion is hash-chain tamper-evident logged
(GDPR čl. 32 / ZZPL čl. 50). The only real delete path,
klijenti/router.py::delete_klijent, never actually called
shared.audit_immutable.log_action -- it only wrote to the separate, mutable
klijenti_audit table via klijenti/audit.py::log_event. A false compliance
claim for the single most sensitive delete action in the app.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _fake_request():
    from starlette.requests import Request as StarletteRequest
    scope = {"type": "http", "method": "DELETE", "path": "/klijenti/kl-1", "headers": [],
              "query_string": b"", "app": MagicMock(), "state": MagicMock(),
              "client": ("127.0.0.1", 1234)}
    return StarletteRequest(scope=scope)


@pytest.mark.anyio
async def test_delete_klijent_writes_to_immutable_audit_chain():
    from klijenti import router as kr

    supa = MagicMock()
    upd_res = MagicMock()
    upd_res.data = [{"id": "kl-1"}]
    supa.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = upd_res

    with patch.object(kr, "_auth_from_request", new=AsyncMock(
             return_value={"user_id": "u1", "email": "partner@vindex.rs", "role": kr.Role.PARTNER, "role_str": "partner"})), \
         patch.object(kr, "_get_supa", return_value=supa), \
         patch.object(kr, "can_perform", return_value=True), \
         patch.object(kr, "log_event", new=AsyncMock(return_value=None)), \
         patch("shared.audit_immutable.log_action", new=AsyncMock(return_value="entry-1")) as mock_immutable, \
         patch("klijenti.router.get_client_ip", return_value="127.0.0.1"):
        result = await kr.delete_klijent("kl-1", _fake_request())

    assert result == {"status": "obrisan"}
    # asyncio.create_task fire-and-forget -- let the event loop run it.
    import asyncio
    await asyncio.sleep(0)
    mock_immutable.assert_called_once()
    call_kwargs = mock_immutable.call_args.kwargs
    assert call_kwargs["action"] == "klijent_delete"
    assert call_kwargs["resource_id"] == "kl-1"
    assert call_kwargs["user_id"] == "u1"


def test_klijent_delete_is_in_auditable_actions_allowlist():
    """log_action() silently no-ops for any action not in this set (see its
    own AUDITABLE_ACTIONS membership check) -- if 'klijent_delete' were ever
    removed from the allowlist, the call this fix added would become a
    silent no-op again."""
    from shared.audit_immutable import AUDITABLE_ACTIONS
    assert "klijent_delete" in AUDITABLE_ACTIONS
