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


# ─── Wave 9 / D2: tvrda entitlement kapija na sirovom WSS chokepoint-u ──────
#
# Voice je VLASNIČKOM ODLUKOM van bete. Mandat zabranjuje stanje "voice ugašen
# u UI-ju, a sirov WSS endpoint i dalje upotrebljiv". Kapija u
# `routers/voice_realtime.py::_authenticate` je merena i JESTE fail-closed, ali
# je to kapija JEDNOG pozivnog mesta. Sirova WSS konekcija ka OpenAI Realtime
# API-ju otvara se OVDE, u `start()`, i do sada nije imala nijednu sopstvenu
# proveru -- verovala je pozivaocu. Svaki budući pozivalac (novi ruter, pozadinski
# posao, alat) otvorio bi privilegovani kanal bez ijedne provere.
#
# Zato je provera spuštena na mesto gde se konekcija stvarno otvara. Ne uvodi se
# nova politika: čitaju se ISTI `feature_registry` red i ISTI helperi iz
# `shared/permissions.py` koje koristi i HTTP putanja.
_VOICE_KILL_ENV = "VINDEX_VOICE_KILL"
_KILL_TRUE = {"1", "true", "yes", "on", "da"}


class VoiceEntitlementError(RuntimeError):
    """Sesija je odbijena. Namerno je RuntimeError, ne HTTPException — ovaj
    modul nema HTTP kontekst, a pozivalac (WS ruter) ionako zatvara kanal."""


async def proveri_voice_dozvolu(user: dict) -> None:
    """FAIL-CLOSED provera prava na glasovnu sesiju. Diže izuzetak ili ćuti.

    Redosled je namerno isti kao na HTTP putanji:
      1. env kill switch  (`VINDEX_VOICE_KILL`) — radi i kad je baza nedostupna
      2. kill switch u bazi (`feature_registry.voice.aktivno`)
      3. `status` (DEPRECATED/COMING_SOON/INTERNAL) — founder izuzetak
      4. `minimum_plan` (`professional`) — founder izuzetak

    DEFAULT DISABLED: `aktivno` se čita sa podrazumevanom vrednošću **False**,
    ne True. Ako red u `feature_registry`-ju nedostaje, `get_policy` diže
    RuntimeError i završava u `except` ispod — takođe odbijanje. Nijedan put
    kroz ovu funkciju ne vodi u "propusti jer ne znam".

    BILO KOJI neočekivani izuzetak (pad baze, nedostupan registry, greška u
    profilu) znači ODBIJANJE. Za kanal koji nosi izgovoreni privilegovani
    razgovor advokata sa klijentom, i koji je jedini AI put bez telemetrije
    sadržaja, "ne mogu da proverim" ne sme da znači "puštam".
    """
    email = (user or {}).get("email") or ""
    uid = (user or {}).get("user_id") or ""

    if (os.getenv(_VOICE_KILL_ENV) or "").strip().lower() in _KILL_TRUE:
        logger.warning("[VOICE_RT] odbijeno: %s je aktivan (kill switch)", _VOICE_KILL_ENV)
        raise VoiceEntitlementError(
            "Glasovni asistent je isključen prekidačem VINDEX_VOICE_KILL."
        )

    try:
        from shared.deps import _is_founder
        from shared.feature_registry import get_policy
        from shared.permissions import _ensure_profile, _tier_satisfies, effective_tier

        policy = await get_policy("voice")
        is_founder = _is_founder(email)

        if not policy.get("aktivno", False):
            raise VoiceEntitlementError("Glasovni asistent je privremeno onemogućen.")

        if policy.get("status") in ("DEPRECATED", "COMING_SOON", "INTERNAL") and not is_founder:
            raise VoiceEntitlementError("Funkcija nije dostupna.")

        minimum_plan = policy.get("minimum_plan")
        if minimum_plan and not is_founder:
            profil = await _ensure_profile(uid)
            if not _tier_satisfies(effective_tier(profil), minimum_plan):
                raise VoiceEntitlementError(
                    "Glasovni asistent zahteva Professional tarifu."
                )
    except VoiceEntitlementError:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error(
            "[VOICE_RT] provera prava nije mogla da se izvrši (%s) — kanal se ZATVARA",
            type(e).__name__,
        )
        raise VoiceEntitlementError(
            "Provera prava za glasovni asistent nije uspela — sesija je odbijena."
        ) from e


def _uknjizi_voice_sesiju_provenance(user: dict, status: str = "success",
                                     error: Optional[Exception] = None) -> None:
    """Provenance trag da je sirova WSS sesija ka OpenAI-ju OTVORENA.

    Ne rešava BP-01 u celini — sadržaj razgovora i dalje ne prolazi kroz
    `ai_forensics` jer sirov WSS ne vidi monkey-patch iz `shared/ai_client.py`.
    Ali uklanja gore stanje: do sada nije postojao NIJEDAN red koji svedoči da
    je sesija uopšte postojala, pa je i founder/admin izuzetak bio potpuno
    nevidljiv. Sada postoji red po sesiji (ko, kada, koji model, koji
    `correlation_id`), bez ijednog karaktera sadržaja.

    Fail-soft: greška u knjiženju nikad ne obara sesiju.
    """
    try:
        from shared import ai_provenance as _prov
        from security.ai_forensics import log_provenance_from_wrapper

        ctx = _prov.current_context()
        cid = ctx.get("correlation_id") or _prov.new_correlation_id()
        uid = (user or {}).get("user_id") or ctx.get("user_id")

        logger.warning(
            "[VOICE_RT/PROVENANCE] sirova WSS sesija provider=openai-realtime "
            "model=%s correlation_id=%s user_id=%.8s status=%s",
            _REALTIME_MODEL, cid, str(uid or "?"), status,
        )

        coro = log_provenance_from_wrapper(
            module_name="services.voice_orchestrator",
            operation_name="voice_realtime_session",
            model_provider="openai-realtime-raw-wss",
            model_name=_REALTIME_MODEL,
            correlation_id=cid,
            user_id=uid,
            tenant_id=ctx.get("tenant_id"),
            status=status,
            error_message=str(error)[:500] if error else None,
        )
        # Isti obrazac kao `shared/ai_client.py:238-250` — ne nov mehanizam.
        try:
            asyncio.get_running_loop()
            from shared.bg import spawn as _spawn_bg
            _spawn_bg(coro, name="voice_session_provenance:write")
        except RuntimeError:
            asyncio.run(coro)
    except Exception as exc:  # pragma: no cover — fail-soft po ugovoru
        logger.debug("[VOICE_RT/PROVENANCE] knjiženje nije uspelo: %s", exc)


class VoiceOrchestratorSession:
    def __init__(self, client_ws: Any, user: dict, openai_ws_factory=None):
        self.client_ws = client_ws
        self.user = user
        self._connect = openai_ws_factory or _connect_openai_realtime
        self.upstream: Any = None
        self._pending_confirmations: dict[str, dict] = {}
        # BETA-HARDENING-001 / FS-002: koliko je audio delti STVARNO otislo
        # browseru. Bez ovoga se ishod sesije ne moze razlikovati od namere.
        self._isporucenih_delti: int = 0
        self._provenance_zatvoren: bool = False

    async def start(self) -> None:
        # Wave 9 / D2: kapija PRE konekcije. Ako provera padne, `self.upstream`
        # ostaje None i nijedan bajt ne odlazi ka OpenAI Realtime API-ju.
        await proveri_voice_dozvolu(self.user)
        self.upstream = await self._connect()
        await self._send_session_config()
        # FS-002: ovde se sesija tek OTVARA. Ranije je ovo upisivalo
        # `status="success"` (podrazumevana vrednost potpisa) jos pre nego sto
        # je ijedan bajt zvuka isporucen -- pa je sesija u kojoj advokat nije
        # cuo NISTA ostajala zabelezena kao uspesna. Za privilegovan razgovor
        # to je jedini forenzicki trag koji postoji, i bio je netacan.
        _uknjizi_voice_sesiju_provenance(self.user, status="started")

    async def close(self) -> None:
        if self.upstream is not None:
            try:
                await self.upstream.close()
            except Exception:
                pass
        # FS-002: terminalni status po STVARNOM ishodu, ne po nameri.
        # Sesija bez ijedne isporucene audio delte NIJE uspesna sesija.
        # `_provenance_zatvoren` cuva od dvostrukog upisa ako se `close()`
        # pozove vise puta (npr. i iz rukovaoca greske i iz `finally`).
        if not self._provenance_zatvoren:
            self._provenance_zatvoren = True
            _uknjizi_voice_sesiju_provenance(
                self.user,
                status="success" if self._isporucenih_delti > 0 else "error",
            )

    async def _send_session_config(self) -> None:
        await self.upstream.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": _SYSTEM_INSTRUCTIONS,
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                # Bez ovoga OpenAI ne transkribuje ŠTA JE ADVOKAT IZGOVORIO --
                # samo sopstveni (asistentov) audio.transcript event postoji po
                # defaultu. Frontend (vindex.js, VindexLive) prikazuje oba
                # transkripta u modalu, pa je ovo neophodno, ne kozmetika.
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {"type": "server_vad"},
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
        # SE-004 (protivnicki pregled): brojac je merio SAMO
        # `response.audio.delta`. Sesija koja je isporucila transkript i
        # rezultat alata, ali bez ijedne audio delte, zavrsavala bi kao
        # `error` -- lazan uspeh zamenjen laznom greskom, sto je jednako
        # netacan forenzicki trag.
        #
        # Meri se ISHOD, ne jedan kanal: svaki dogadjaj koji je stvarno otisao
        # browseru broji se kao isporuka.
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
        # Posle uspesnog `send_json` -- greska u slanju baca pre ovog reda,
        # pa se neisporucen dogadjaj ne broji kao isporucen.
        if etype != "error":
            self._isporucenih_delti += 1

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

    # S2-2 (2026-08-09): FAIL CLOSED when the deployment is configured for
    # Azure / EU data residency.
    #
    # shared/ai_client.py redirects every OpenAI SDK call to the Azure endpoint
    # when AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT are set. This module does
    # not use the SDK -- it opens a raw WebSocket to a hardcoded
    # wss://api.openai.com/v1/realtime -- so it silently ignored that redirect.
    #
    # A firm on the EU-residency configuration believes all AI traffic stays in
    # the EU. Vindex Live carries the lawyer's spoken, privileged client
    # conversation plus its whisper transcription. Sending that to OpenAI US
    # while the rest of the product honours the redirect is not a degraded
    # experience; it is a false statement about where the data went.
    #
    # Refusing the session is the honest outcome. Adding Azure realtime support
    # is new transport work (different URL shape, different auth) and is not a
    # hardening fix.
    _azure_key = os.getenv("AZURE_OPENAI_KEY", "").strip()
    _azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    if _azure_key and _azure_endpoint:
        logger.error(
            "[VOICE_RT] Azure/EU konfiguracija je aktivna, a Realtime API ide "
            "iskljucivo na OpenAI US — odbijam sesiju umesto da tiho posaljem "
            "poverljiv razgovor van EU."
        )
        raise RuntimeError(
            "Vindex Live nije dostupan na EU konfiguraciji: Realtime sesija bi "
            "isla van EU. Koristite tekstualne module dok se ne uvede Azure "
            "Realtime transport."
        )

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
