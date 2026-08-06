# -*- coding: utf-8 -*-
"""
Program Lambda, Certification 002 (2026-08-06) -- AI Context Auditor / API
Penetration sweep found routers/multi_agent.py::run_agent's billing_ctx and
rokovi_ctx blocks queried billing_entries/rocista by predmet_id ALONE,
unconditional on whether the sibling ownership check (predmet_ctx block)
actually found the case. A caller supplying a foreign predmet_id with
agent="billing" or agent="deadline" had that foreign case's real invoice
line items / hearing schedule injected into the GPT prompt.

Fix: both blocks are now gated on a `predmet_verifikovan` flag set only when
`predmeti.eq(id,..).eq(user_id,..)` actually returned a row. These tests
prove the leak is closed by inspecting the actual user_msg string passed to
the GPT call -- not just that no exception was raised.
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

from starlette.requests import Request as StarletteRequest  # noqa: E402
import routers.multi_agent as multi_agent  # noqa: E402


def _req() -> StarletteRequest:
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http", "method": "POST", "path": "/api/agents/run",
        "headers": [], "query_string": b"", "app": MagicMock(), "state": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    return StarletteRequest(scope=scope, receive=receive)


def _table_for(predmet_owned: bool, billing_rows=None, rocista_rows=None):
    def _table(name):
        t = MagicMock()
        if name == "predmeti":
            data = [{"naziv": "Test predmet", "tip": "parnicno", "status": "aktivan",
                     "tuzilac": "A", "tuzeni": "B", "opis": ""}] if predmet_owned else []
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = data
        elif name == "billing_entries":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = billing_rows or []
        elif name == "rocista":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = rocista_rows or []
        elif name == "predmet_dokumenti":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        return t
    return _table


def _run(agent_id, predmet_owned, billing_rows=None, rocista_rows=None):
    captured = {}

    def _fake_pozovi_agent_api(client, system, user_msg):
        captured["user_msg"] = user_msg
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "OK"
        return resp

    mock_supa = MagicMock()
    mock_supa.table.side_effect = _table_for(predmet_owned, billing_rows, rocista_rows)

    req = multi_agent.AgentReq(agent=agent_id, task="analiziraj", predmet_id="pred-target")

    with patch.object(multi_agent, "_get_supa", return_value=mock_supa), \
         patch.object(multi_agent, "_pozovi_agent_api", side_effect=_fake_pozovi_agent_api), \
         patch("shared.usage.UsageService.consume", return_value=None):
        asyncio.run(multi_agent.run_agent(req, _req(), user={"user_id": "u1", "email": "a@b.com"}))

    return captured.get("user_msg", "")


def test_billing_agent_does_not_leak_foreign_case_billing_data():
    """Ownership check fails (predmet not owned) -- billing_ctx must stay empty
    even though billing_entries HAS rows for that predmet_id (a foreign case's
    real invoice data)."""
    user_msg = _run(
        "billing", predmet_owned=False,
        billing_rows=[{"opis": "Tajna radnja za drugog klijenta", "kolicina": 1, "jedinica": "h",
                        "cena_po_jedinici": 50000, "ukupno": 50000, "datum": "2026-08-01", "fakturisano": True}],
    )
    assert "Tajna radnja za drugog klijenta" not in user_msg
    assert "STVARNE BILLING STAVKE" not in user_msg


def test_billing_agent_includes_own_case_billing_data():
    """No regression: a genuinely owned case's billing data must still reach the prompt."""
    user_msg = _run(
        "billing", predmet_owned=True,
        billing_rows=[{"opis": "Sopstvena radnja", "kolicina": 1, "jedinica": "h",
                        "cena_po_jedinici": 50000, "ukupno": 50000, "datum": "2026-08-01", "fakturisano": True}],
    )
    assert "Sopstvena radnja" in user_msg
    assert "STVARNE BILLING STAVKE" in user_msg


def test_deadline_agent_does_not_leak_foreign_case_hearing_schedule():
    user_msg = _run(
        "deadline", predmet_owned=False,
        rocista_rows=[{"sud": "Tajni sud protivnika", "datum": "2026-09-01", "status": "aktivan", "napomena": ""}],
    )
    assert "Tajni sud protivnika" not in user_msg
    assert "STVARNI ROKOVI IZ PREDMETA" not in user_msg


def test_deadline_agent_includes_own_case_hearing_schedule():
    user_msg = _run(
        "deadline", predmet_owned=True,
        rocista_rows=[{"sud": "Sopstveni sud", "datum": "2026-09-01", "status": "aktivan", "napomena": ""}],
    )
    assert "Sopstveni sud" in user_msg
    assert "STVARNI ROKOVI IZ PREDMETA" in user_msg
