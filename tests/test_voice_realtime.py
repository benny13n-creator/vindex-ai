# -*- coding: utf-8 -*-
"""
Regression tests — KORAK A: Vindex Live & Voice-to-Action (2026-07-24).

Pokriva tri nova fajla:
  1. shared/voice_tools.py         — tool schema + handleri (RAG pretraga,
     dodaj_belesku, kreiraj_nacrt), svaki fail-soft (nikad ne baca).
  2. services/voice_orchestrator.py — relay logika + Human-in-the-Loop gate
     za alate koji menjaju podatke (mutates_data=True), testirano preko
     duck-typed fake client_ws/upstream objekata (nema stvarne mreže).
  3. routers/voice_realtime.py      — WebSocket auth (token iz query parama,
     jer browser WebSocket API ne može nositi Authorization header) preko
     Starlette TestClient-a (in-process, bez stvarnog socket-a).

Pure unit/integration tests -- no live Supabase, no OpenAI, no real
network I/O (websockets.connect je mock-ovan svuda).
"""
import asyncio
import json
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault("FOUNDER_EMAILS", "test@test.com")
os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-svc-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "fake-jwt-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-fake")
os.environ.setdefault("PINECONE_API_KEY", "fake-pinecone")
os.environ.setdefault("FOUNDER_TOKEN", "test-admin-token-12345")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════════════
# 1. shared/voice_tools.py
# ═══════════════════════════════════════════════════════════════════════════

def test_voice_tools_schema_has_three_tools_with_required_fields():
    import shared.voice_tools as vt

    names = {t["name"] for t in vt.VOICE_TOOLS}
    assert names == {"pretraga_prakse_i_zakona", "dodaj_belesku", "kreiraj_nacrt"}
    for tool in vt.VOICE_TOOLS:
        assert tool["type"] == "function"
        assert "description" in tool and tool["description"]
        assert tool["parameters"]["type"] == "object"
        assert tool["parameters"]["required"]


def test_requires_confirmation_true_only_for_mutating_tools():
    import shared.voice_tools as vt

    assert vt.requires_confirmation("dodaj_belesku") is True
    assert vt.requires_confirmation("pretraga_prakse_i_zakona") is False
    assert vt.requires_confirmation("kreiraj_nacrt") is False
    assert vt.requires_confirmation("nepostojeci_alat") is False


@pytest.mark.parametrize("name", ["pretraga_prakse_i_zakona", "dodaj_belesku", "kreiraj_nacrt"])
def test_tool_metadata_covers_every_schema_entry(name):
    import shared.voice_tools as vt
    assert name in vt.TOOL_METADATA
    assert callable(vt.TOOL_METADATA[name]["handler"])


def test_execute_tool_unknown_name_returns_error_without_raising():
    import shared.voice_tools as vt
    result = asyncio.run(vt.execute_tool("nepostojeci_alat", {}, {"user_id": "u1"}))
    assert result["ok"] is False
    assert "Nepoznat alat" in result["error"]


# ─── pretraga_prakse_i_zakona ───────────────────────────────────────────────

def test_rag_pretraga_returns_top_results():
    import shared.voice_tools as vt

    fake_docs = ["odlomak 1", "odlomak 2"]
    fake_meta = {"top_law": "Zakon o radu", "top_article": "Član 179", "confidence": "HIGH"}
    with patch("app.services.retrieve.retrieve_documents", return_value=(fake_docs, fake_meta)) as m:
        result = asyncio.run(vt.execute_tool("pretraga_prakse_i_zakona", {"upit": "otkaz ugovora o radu"}, {"user_id": "u1"}))

    assert result["ok"] is True
    assert result["top_zakon"] == "Zakon o radu"
    assert result["pouzdanost"] == "HIGH"
    assert result["odlomci"] == fake_docs
    m.assert_called_once()


def test_rag_pretraga_missing_upit_returns_error():
    import shared.voice_tools as vt
    result = asyncio.run(vt.execute_tool("pretraga_prakse_i_zakona", {}, {"user_id": "u1"}))
    assert result["ok"] is False


def test_rag_pretraga_never_raises_on_internal_error():
    import shared.voice_tools as vt
    with patch("app.services.retrieve.retrieve_documents", side_effect=RuntimeError("pinecone down")):
        result = asyncio.run(vt.execute_tool("pretraga_prakse_i_zakona", {"upit": "x"}, {"user_id": "u1"}))
    assert result["ok"] is False


# ─── dodaj_belesku ───────────────────────────────────────────────────────────

def _chain_mock(execute_return):
    m = MagicMock()
    for method in ("select", "eq", "insert", "single"):
        setattr(m, method, MagicMock(return_value=m))
    m.execute = MagicMock(return_value=execute_return)
    return m


def test_dodaj_belesku_rejects_predmet_not_owned():
    import shared.voice_tools as vt

    mock_supa = MagicMock()
    mock_supa.table.return_value = _chain_mock(MagicMock(data=None))

    with patch("shared.deps._get_supa", return_value=mock_supa):
        result = asyncio.run(vt.execute_tool(
            "dodaj_belesku", {"predmet_id": "p1", "sadrzaj": "test beleška"}, {"user_id": "u1"}
        ))

    assert result["ok"] is False
    assert "nije pronađen" in result["error"] or "ne pripada" in result["error"]


def test_dodaj_belesku_success_inserts_and_returns_id():
    import shared.voice_tools as vt

    mock_supa = MagicMock()
    select_chain = _chain_mock(MagicMock(data={"id": "p1"}))
    insert_chain = _chain_mock(MagicMock(data=[{"id": "beleska-123"}]))

    def _table(name):
        return select_chain if name == "predmeti" else insert_chain
    mock_supa.table.side_effect = _table

    with patch("shared.deps._get_supa", return_value=mock_supa):
        result = asyncio.run(vt.execute_tool(
            "dodaj_belesku", {"predmet_id": "p1", "sadrzaj": "test beleška"}, {"user_id": "u1"}
        ))

    assert result["ok"] is True
    assert result["beleska_id"] == "beleska-123"


def test_dodaj_belesku_missing_args_returns_error_without_db_call():
    import shared.voice_tools as vt
    result = asyncio.run(vt.execute_tool("dodaj_belesku", {"predmet_id": "p1"}, {"user_id": "u1"}))
    assert result["ok"] is False


def test_dodaj_belesku_never_raises_on_db_error():
    import shared.voice_tools as vt
    with patch("shared.deps._get_supa", side_effect=RuntimeError("no db")):
        result = asyncio.run(vt.execute_tool(
            "dodaj_belesku", {"predmet_id": "p1", "sadrzaj": "x"}, {"user_id": "u1"}
        ))
    assert result["ok"] is False


# ─── kreiraj_nacrt ───────────────────────────────────────────────────────────

def test_kreiraj_nacrt_success_returns_text():
    import shared.voice_tools as vt
    with patch("drafting.router.generate_draft", return_value={"status": "success", "data": "Tuzba tekst..."}) as m:
        result = asyncio.run(vt.execute_tool(
            "kreiraj_nacrt", {"vrsta": "tuzba_naknada_stete", "opis": "saobraćajna nezgoda"}, {"user_id": "u1"}
        ))
    assert result["ok"] is True
    assert result["nacrt"] == "Tuzba tekst..."
    m.assert_called_once_with("tuzba_naknada_stete", "saobraćajna nezgoda", "u1")


def test_kreiraj_nacrt_propagates_generation_error_message():
    import shared.voice_tools as vt
    with patch("drafting.router.generate_draft", return_value={"status": "error", "message": "Nepoznat tip"}):
        result = asyncio.run(vt.execute_tool(
            "kreiraj_nacrt", {"vrsta": "nepoznat_tip", "opis": "x"}, {"user_id": "u1"}
        ))
    assert result["ok"] is False
    assert result["error"] == "Nepoznat tip"


def test_kreiraj_nacrt_never_raises_on_internal_error():
    import shared.voice_tools as vt
    with patch("drafting.router.generate_draft", side_effect=RuntimeError("openai down")):
        result = asyncio.run(vt.execute_tool(
            "kreiraj_nacrt", {"vrsta": "zalba", "opis": "x"}, {"user_id": "u1"}
        ))
    assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. services/voice_orchestrator.py
# ═══════════════════════════════════════════════════════════════════════════

class _FakeClientWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, data):
        self.sent.append(data)


class _FakeUpstream:
    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    async def send(self, raw: str):
        self.sent.append(raw)

    async def close(self):
        self.closed = True


def _session():
    from services.voice_orchestrator import VoiceOrchestratorSession
    client_ws = _FakeClientWS()
    upstream = _FakeUpstream()
    sess = VoiceOrchestratorSession(client_ws, {"user_id": "u1", "email": "a@b.com"})
    sess.upstream = upstream  # bypass start(); nema stvarne konekcije
    return sess, client_ws, upstream


def test_send_session_config_includes_tools():
    from shared.voice_tools import VOICE_TOOLS
    sess, _, upstream = _session()
    asyncio.run(sess._send_session_config())

    assert len(upstream.sent) == 1
    payload = json.loads(upstream.sent[0])
    assert payload["type"] == "session.update"
    assert payload["session"]["tools"] == VOICE_TOOLS


def test_handle_client_message_input_audio_forwards_to_upstream():
    sess, _, upstream = _session()
    asyncio.run(sess.handle_client_message({"type": "input_audio", "audio": "BASE64=="}))

    assert len(upstream.sent) == 1
    payload = json.loads(upstream.sent[0])
    assert payload["type"] == "input_audio_buffer.append"
    assert payload["audio"] == "BASE64=="


def test_handle_upstream_event_audio_delta_forwards_to_client():
    sess, client_ws, _ = _session()
    asyncio.run(sess.handle_upstream_event({"type": "response.audio.delta", "delta": "AUDIO=="}))

    assert client_ws.sent == [{"type": "output_audio", "audio": "AUDIO=="}]


def test_non_mutating_tool_call_executes_immediately_without_confirmation():
    sess, client_ws, upstream = _session()
    event = {
        "type": "response.function_call_arguments.done",
        "name": "pretraga_prakse_i_zakona",
        "call_id": "call_1",
        "arguments": json.dumps({"upit": "otkaz"}),
    }
    fake_result = {"ok": True, "odlomci": ["x"]}
    with patch("services.voice_orchestrator.execute_tool", new=AsyncMock(return_value=fake_result)) as m:
        asyncio.run(sess.handle_upstream_event(event))

    m.assert_awaited_once_with("pretraga_prakse_i_zakona", {"upit": "otkaz"}, sess.user)
    # Nema confirmation_required poruke ka klijentu za ne-mutirajući alat
    assert all(s.get("type") != "vindex.confirmation_required" for s in client_ws.sent)
    # Rezultat je poslat nazad OpenAI-ju kao function_call_output + response.create
    assert len(upstream.sent) == 2
    item_payload = json.loads(upstream.sent[0])
    assert item_payload["item"]["call_id"] == "call_1"
    assert json.loads(item_payload["item"]["output"]) == fake_result
    assert json.loads(upstream.sent[1]) == {"type": "response.create"}


def test_mutating_tool_call_requires_confirmation_before_executing():
    sess, client_ws, upstream = _session()
    event = {
        "type": "response.function_call_arguments.done",
        "name": "dodaj_belesku",
        "call_id": "call_2",
        "arguments": json.dumps({"predmet_id": "p1", "sadrzaj": "beleška"}),
    }
    with patch("services.voice_orchestrator.execute_tool", new=AsyncMock()) as m:
        asyncio.run(sess.handle_upstream_event(event))

    m.assert_not_awaited()
    assert upstream.sent == []  # ništa nije poslato OpenAI-ju dok korisnik ne potvrdi
    assert len(client_ws.sent) == 1
    assert client_ws.sent[0] == {
        "type": "vindex.confirmation_required",
        "call_id": "call_2",
        "tool": "dodaj_belesku",
        "args": {"predmet_id": "p1", "sadrzaj": "beleška"},
    }
    assert "call_2" in sess._pending_confirmations


def test_confirm_tool_call_approved_executes_and_sends_result():
    sess, client_ws, upstream = _session()
    sess._pending_confirmations["call_3"] = {"name": "dodaj_belesku", "args": {"predmet_id": "p1", "sadrzaj": "x"}}
    fake_result = {"ok": True, "beleska_id": "b1"}

    with patch("services.voice_orchestrator.execute_tool", new=AsyncMock(return_value=fake_result)) as m:
        asyncio.run(sess._confirm_tool_call("call_3", approved=True))

    m.assert_awaited_once_with("dodaj_belesku", {"predmet_id": "p1", "sadrzaj": "x"}, sess.user)
    assert "call_3" not in sess._pending_confirmations
    item_payload = json.loads(upstream.sent[0])
    assert json.loads(item_payload["item"]["output"]) == fake_result


def test_confirm_tool_call_rejected_does_not_execute():
    sess, client_ws, upstream = _session()
    sess._pending_confirmations["call_4"] = {"name": "dodaj_belesku", "args": {"predmet_id": "p1", "sadrzaj": "x"}}

    with patch("services.voice_orchestrator.execute_tool", new=AsyncMock()) as m:
        asyncio.run(sess._confirm_tool_call("call_4", approved=False))

    m.assert_not_awaited()
    item_payload = json.loads(upstream.sent[0])
    result = json.loads(item_payload["item"]["output"])
    assert result["ok"] is False
    assert "call_4" not in sess._pending_confirmations


def test_confirm_tool_call_unknown_call_id_is_noop():
    sess, client_ws, upstream = _session()
    asyncio.run(sess._confirm_tool_call("nepostojeci", approved=True))
    assert upstream.sent == []
    assert client_ws.sent == []


def test_handle_client_message_confirm_dispatches_to_confirm_tool_call():
    sess, client_ws, upstream = _session()
    sess._pending_confirmations["call_5"] = {"name": "dodaj_belesku", "args": {}}
    with patch("services.voice_orchestrator.execute_tool", new=AsyncMock(return_value={"ok": True})):
        asyncio.run(sess.handle_client_message({
            "type": "vindex.confirm_tool_call", "call_id": "call_5", "approved": True,
        }))
    assert "call_5" not in sess._pending_confirmations


def test_connect_openai_realtime_uses_bearer_auth_header():
    from services.voice_orchestrator import _connect_openai_realtime

    import services.voice_orchestrator as vo

    fake_ws = AsyncMock()

    async def _sa_odlukom():
        # BETA-HARDENING-002 / BYPASS-7: veza bez governance odluke je od sada
        # odbijena. U produkciji odluku postavlja `proveri_voice_dozvolu()`;
        # ovde se radi isto, i to UNUTAR istog taska, jer je contextvar
        # task-lokalan. Tvrdnja testa (Bearer zaglavlje) je nepromenjena.
        vo._oznaci_odluku({"user_id": "test"}, "cid-test")
        return await _connect_openai_realtime()

    with patch("websockets.connect", new=AsyncMock(return_value=fake_ws)) as m, \
         patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
        result = asyncio.run(_sa_odlukom())

    assert result is fake_ws
    args, kwargs = m.call_args
    assert "wss://api.openai.com/v1/realtime" in args[0]
    assert kwargs["additional_headers"]["Authorization"] == "Bearer sk-test-key"
    assert kwargs["additional_headers"]["OpenAI-Beta"] == "realtime=v1"


# ═══════════════════════════════════════════════════════════════════════════
# 3. routers/voice_realtime.py — WebSocket auth (Starlette TestClient, in-process)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def client():
    from api import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


def test_ws_rejects_missing_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/voice/realtime/ws") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4401


def test_ws_rejects_invalid_token(client):
    from starlette.websockets import WebSocketDisconnect
    with patch("routers.voice_realtime._verify_token", return_value=None):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/voice/realtime/ws?token=bad.token") as ws:
                ws.receive_text()
    assert exc_info.value.code == 4401


def test_ws_rejects_when_feature_inactive(client):
    from starlette.websockets import WebSocketDisconnect
    with patch("routers.voice_realtime._verify_token", return_value={"sub": "u1", "email": "a@b.com"}), \
         patch("routers.voice_realtime.get_policy", new=AsyncMock(return_value={"aktivno": False})):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/voice/realtime/ws?token=good") as ws:
                ws.receive_text()
    assert exc_info.value.code == 4401


def test_ws_accepts_valid_token_and_starts_session(client):
    from services.voice_orchestrator import VoiceOrchestratorSession

    async def _fake_start(self):
        self.upstream = _FakeUpstream()

    async def _fake_relay_client(self):
        return  # odmah "završi" da test ne visi

    async def _fake_relay_upstream(self):
        return

    with patch("routers.voice_realtime._verify_token", return_value={"sub": "u1", "email": "a@b.com"}), \
         patch("routers.voice_realtime.get_policy", new=AsyncMock(return_value={"aktivno": True, "status": "ACTIVE"})), \
         patch.object(VoiceOrchestratorSession, "start", new=_fake_start), \
         patch.object(VoiceOrchestratorSession, "relay_client_to_upstream", new=_fake_relay_client), \
         patch.object(VoiceOrchestratorSession, "relay_upstream_to_client", new=_fake_relay_upstream):
        with client.websocket_connect("/api/voice/realtime/ws?token=good") as ws:
            ws.close()

    import routers.voice_realtime as vr
    assert vr._active_sessions.get("u1", 0) == 0  # dekrementovano nakon zatvaranja
