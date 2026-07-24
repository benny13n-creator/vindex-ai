# -*- coding: utf-8 -*-
"""
Vindex AI — services/voice_orchestrator.py

KORAK A: Vindex Live & Voice-to-Action (2026-07-24)

Orkestruje JEDNU realtime glasovnu sesiju: relay audio/event saobraćaja
između browsera (routers/voice_realtime.py's WebSocket) i OpenAI Realtime
API-ja (wss://api.openai.com/v1/realtime), i presreće function-call evente
da bi ih izvršio SERVER-SIDE (kroz shared/voice_tools.py) umesto da
dozvoli browseru direktnu WebRTC vezu ka OpenAI-ju — to je jedini način da
naš auth/permission/HITL sloj ostane u putanji svakog poziva alata.

Human-in-the-Loop: alati sa mutates_data=True (v. shared/voice_tools.py)
se NE izvršavaju odmah po pozivu modela — sesija šalje
"vindex.confirmation_required" browseru i čeka eksplicitnu
"vindex.confirm_tool_call" poruku (korisnik potvrđuje glasom ili u UI)
pre nego što se akcija stvarno izvrši i rezultat vrati modelu.

Namerno odvojeno testabilno: VoiceOrchestratorSession prima BILO KOJI
objekat sa async send/receive-json metodama za client_ws (duck-typing —
FastAPI WebSocket u produkciji, fake u testovima) i bilo koji async
iterable+send za upstream (websockets.ClientConnection u produkciji, fake
u testovima) — nijedna metoda ovde ne zavisi direktno od stvarne mrežne
konekcije.
"""
import asyncio
import json
import logging
import os
from typing import Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from shared.sentry import capture_exception as _sentry_capture
from shared.voice_tools import VOICE_TOOLS, execute_tool, requires_confirmation

logger = logging.getLogger("vindex.voice_orchestrator")

_REALTIME_URL = "wss://api.openai.com/v1/realtime"
_REALTIME_MODEL = os.getenv("VINDEX_REALTIME_MODEL", "gpt-4o-realtime-preview")

_SYSTEM_INSTRUCTIONS = (
    "Ti si Vindex Live, glasovni pravni saradnik za srpske advokate. Govoriš "
    "srpski, kratko i konkretno. Za pravna pitanja koristi alat "
    "pretraga_prakse_i_zakona pre nego što odgovoriš — nikad ne izmišljaj "
    "članove zakona. Za dodavanje beleške ili generisanje nacrta pozovi "
    "odgovarajući alat; ako alat zahteva potvrdu, jasno pitaj korisnika da "
    "potvrdi glasom pre nastavka. Nikad ne pominji da si AI model."
)


class VoiceOrchestratorSession:
    def __init__(self, client_ws: Any, user: dict, openai_ws_factory=None):
        self.client_ws = client_ws
        self.user = user
        self._connect = openai_ws_factory or _connect_openai_realtime
        self.upstream: Any = None
        self._pending_confirmations: dict[str, dict] = {}

    async def start(self) -> None:
        self.upstream = await self._connect()
        await self._send_session_config()

    async def close(self) -> None:
        if self.upstream is not None:
            try:
                await self.upstream.close()
            except Exception:
                pass

    async def _send_session_config(self) -> None:
        await self.upstream.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": _SYSTEM_INSTRUCTIONS,
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "tools": VOICE_TOOLS,
                "tool_choice": "auto",
            },
        }))

    # ─── Client (browser) → OpenAI ─────────────────────────────────────────

    async def relay_client_to_upstream(self) -> None:
        while True:
            msg = await self.client_ws.receive_json()
            await self.handle_client_message(msg)
            if msg.get("type") == "vindex.stop":
                break

    async def handle_client_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == "input_audio":
            await self.upstream.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": msg.get("audio", ""),
            }))
        elif mtype == "vindex.confirm_tool_call":
            await self._confirm_tool_call(msg.get("call_id"), approved=bool(msg.get("approved")))
        elif mtype == "vindex.stop":
            logger.info("[VOICE_RT] stop primljen uid=%.8s", (self.user.get("user_id") or "")[:8])
        # nepoznat tip poruke se tiho ignoriše — ne prekida sesiju

    # ─── OpenAI → Client (browser) ─────────────────────────────────────────

    async def relay_upstream_to_client(self) -> None:
        async for raw in self.upstream:
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                continue
            await self.handle_upstream_event(event)

    async def handle_upstream_event(self, event: dict) -> None:
        etype = event.get("type")
        if etype == "response.audio.delta":
            await self.client_ws.send_json({"type": "output_audio", "audio": event.get("delta", "")})
        elif etype == "response.function_call_arguments.done":
            await self._handle_function_call(event)
        elif etype == "error":
            logger.warning("[VOICE_RT] OpenAI Realtime error event: %s", event.get("error"))
            await self.client_ws.send_json({"type": "vindex.error", "detail": event.get("error")})
        else:
            # transcript delte, response.done, itd. — prosledi browseru
            # neizmenjeno za UI prikaz, ne blokira relay ako browser ignoriše.
            await self.client_ws.send_json(event)

    # ─── Function calling + Human-in-the-Loop ──────────────────────────────

    async def _handle_function_call(self, event: dict) -> None:
        name = event.get("name", "")
        call_id = event.get("call_id", "")
        try:
            args = json.loads(event.get("arguments") or "{}")
        except (TypeError, ValueError):
            args = {}

        if requires_confirmation(name):
            self._pending_confirmations[call_id] = {"name": name, "args": args}
            await self.client_ws.send_json({
                "type": "vindex.confirmation_required",
                "call_id": call_id,
                "tool": name,
                "args": args,
            })
            return

        result = await execute_tool(name, args, self.user)
        await self._send_tool_result(call_id, result)

    async def _confirm_tool_call(self, call_id: Optional[str], approved: bool) -> None:
        pending = self._pending_confirmations.pop(call_id, None) if call_id else None
        if not pending:
            logger.warning("[VOICE_RT] potvrda za nepoznat/istekao call_id=%s", call_id)
            return

        if not approved:
            await self._send_tool_result(call_id, {"ok": False, "error": "Korisnik nije potvrdio akciju."})
            return

        result = await execute_tool(pending["name"], pending["args"], self.user)
        await self._send_tool_result(call_id, result)

    async def _send_tool_result(self, call_id: str, result: dict) -> None:
        await self.upstream.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result, ensure_ascii=False),
            },
        }))
        await self.upstream.send(json.dumps({"type": "response.create"}))


# ─── Upstream konekcija ka OpenAI Realtime API-ju ──────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((OSError, ConnectionError, asyncio.TimeoutError)),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def _connect_openai_realtime():
    """Otvara WebSocket ka OpenAI Realtime API-ju. Retry-uje SAMO prolazne
    mrežne greške (isti obrazac kao shared/llm_retry.py, prilagođen
    websockets bibliotekom umesto openai SDK-om jer Realtime API nije
    request/response chat.completions poziv nego trajna sesija)."""
    import websockets

    api_key = os.environ["OPENAI_API_KEY"]
    url = f"{_REALTIME_URL}?model={_REALTIME_MODEL}"
    try:
        return await websockets.connect(
            url,
            additional_headers={
                "Authorization": f"Bearer {api_key}",
                "OpenAI-Beta": "realtime=v1",
            },
            max_size=10 * 1024 * 1024,
        )
    except Exception as e:
        _sentry_capture(e)
        raise
