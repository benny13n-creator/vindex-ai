# -*- coding: utf-8 -*-
"""
Vindex AI — routers/voice_realtime.py

KORAK A: Vindex Live & Voice-to-Action (2026-07-24)

WebSocket endpoint za realtime glasovnu sesiju: WS /api/voice/realtime/ws

Browser se povezuje OVDE, ne direktno na OpenAI Realtime API — svaki poziv
alata (RAG pretraga, beleške, nacrti) mora proći kroz naš auth/permission/
HITL sloj (services/voice_orchestrator.py) pre izvršenja; direktna WebRTC
konekcija browser→OpenAI bi to zaobišla.

Auth: WebSocket handshake iz browsera ne može nositi Authorization header
(ograničenje browser WebSocket API-ja) — token se šalje kao query param
(?token=...), verifikovan istim _verify_token mehanizmom kao HTTP rute
(shared/deps.py) PRE nego što se sesija otvori ka OpenAI-ju.

Concurrent-session cap: laka in-memory zaštita (po procesu) od trivijalnog
resource-exhaustion-a — jedan korisnik ne može otvoriti neograničen broj
paralelnih realtime sesija (svaka drži otvorenu upstream WS konekciju ka
OpenAI-ju, što je stanje, ne samo request).
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from shared.deps import _verify_token
from shared.feature_registry import get_policy
from shared.deps import _is_founder
from shared.sentry import capture_exception as _sentry_capture
from services.voice_orchestrator import VoiceOrchestratorSession

logger = logging.getLogger("vindex.voice_realtime")
router = APIRouter(prefix="/api/voice/realtime", tags=["voice-realtime"])

_POLICY_VIOLATION_CODE = 4401  # aplikacioni WS close kod za auth/policy odbijanje
_UPSTREAM_UNAVAILABLE_CODE = 1011

_MAX_CONCURRENT_SESSIONS_PER_USER = 2
_active_sessions: dict[str, int] = {}


async def _authenticate(websocket: WebSocket) -> Optional[dict]:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=_POLICY_VIOLATION_CODE, reason="Nedostaje token.")
        return None

    payload = await asyncio.to_thread(_verify_token, token)
    if not payload:
        await websocket.close(code=_POLICY_VIOLATION_CODE, reason="Nevažeći ili istekao token.")
        return None

    email = (
        payload.get("email")
        or payload.get("user_metadata", {}).get("email")
        or ""
    )
    user = {"user_id": payload.get("sub"), "email": email}

    try:
        policy = await get_policy("voice")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[VOICE_RT] get_policy('voice') greška: %s", e)
        await websocket.close(code=_UPSTREAM_UNAVAILABLE_CODE, reason="Servis trenutno nije dostupan.")
        return None
    is_founder = _is_founder(email)
    if not policy.get("aktivno", True):
        await websocket.close(code=_POLICY_VIOLATION_CODE, reason="Glasovni asistent je privremeno onemogućen.")
        return None
    if policy.get("status") in ("DEPRECATED", "COMING_SOON") and not is_founder:
        await websocket.close(code=_POLICY_VIOLATION_CODE, reason="Funkcija nije dostupna.")
        return None
    if policy.get("status") == "INTERNAL" and not is_founder:
        await websocket.close(code=_POLICY_VIOLATION_CODE, reason="Restricted.")
        return None

    # Governance Wave 2: TARIFNA PROVERA. Ovo je nedostajalo.
    #
    # WebSocket ne prolazi kroz FastAPI `Depends`, pa `PermissionService.require`
    # ovde nikad nije opalio. Provera je do sada obuhvatala kill-switch i
    # `status`, ali NE `minimum_plan` — a `voice` je `professional`
    # (`migrations/064_feature_registry.sql:136`).
    #
    # Posledica koja je merena: korisnik na `basic` tarifi (podrazumevana za
    # svaku novu registraciju — `migrations/063_entitlement_system.sql:30`,
    # `api.py:2498` ne postavlja `subscription_type`) dobijao je 403 na sve tri
    # HTTP glasovne rute, a WebSocket kanal mu je bio potpuno otvoren. Isti
    # feature, dva kanala, dva različita odgovora — pri čemu je otvoren onaj
    # koji nosi ceo privilegovani razgovor i nema nijedan `ai_forensics` red.
    #
    # Ponovo se koriste POSTOJEĆI helperi iz `shared/permissions.py`, ne nova
    # logika: `_ensure_profile` čita profil, `effective_tier` spušta isteklu
    # pretplatu na `basic`, `_tier_satisfies` poredi po `_TIER_ORDER`. Founder
    # zadržava izuzetak koji ima i na HTTP putanji (`permissions.py:159-163`).
    minimum_plan = policy.get("minimum_plan")
    if minimum_plan and not is_founder:
        try:
            from shared.permissions import (
                _ensure_profile, _tier_satisfies, effective_tier,
            )
            profil = await _ensure_profile(user["user_id"])
            if not _tier_satisfies(effective_tier(profil), minimum_plan):
                logger.info(
                    "[VOICE_RT] odbijen uid=%.8s tarifa=%s < %s",
                    user["user_id"], effective_tier(profil), minimum_plan,
                )
                await websocket.close(
                    code=_POLICY_VIOLATION_CODE,
                    reason="Glasovni asistent zahteva Professional tarifu.",
                )
                return None
        except Exception as e:
            # FAIL-CLOSED. Na HTTP putanji greška u čitanju profila ide kroz
            # `Depends` i vraća 500; ovde bi `except: pass` značio da pad baze
            # otvara kanal svima. Za privilegovani glasovni sadržaj to nije
            # prihvatljiv kompromis.
            _sentry_capture(e)
            logger.error("[VOICE_RT] provera tarife nije uspela: %s", e)
            await websocket.close(
                code=_UPSTREAM_UNAVAILABLE_CODE, reason="Servis trenutno nije dostupan.",
            )
            return None

    return user


@router.websocket("/ws")
async def voice_realtime_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    user = await _authenticate(websocket)
    if not user:
        return

    uid = user.get("user_id") or ""
    if _active_sessions.get(uid, 0) >= _MAX_CONCURRENT_SESSIONS_PER_USER:
        await websocket.close(code=_POLICY_VIOLATION_CODE, reason="Previše aktivnih glasovnih sesija.")
        return
    _active_sessions[uid] = _active_sessions.get(uid, 0) + 1

    logger.info("[VOICE_RT] sesija otvorena uid=%.8s", uid[:8] if uid else "?")
    session = VoiceOrchestratorSession(websocket, user)

    try:
        await session.start()
    except Exception as e:
        _sentry_capture(e)
        logger.error("[VOICE_RT] upstream konekcija neuspešna uid=%.8s: %s", uid[:8] if uid else "?", e)
        await websocket.close(code=_UPSTREAM_UNAVAILABLE_CODE, reason="Glasovni servis trenutno nije dostupan.")
        _active_sessions[uid] = max(0, _active_sessions.get(uid, 1) - 1)
        return

    try:
        await asyncio.gather(
            session.relay_client_to_upstream(),
            session.relay_upstream_to_client(),
        )
    except WebSocketDisconnect:
        logger.info("[VOICE_RT] klijent prekinuo vezu uid=%.8s", uid[:8] if uid else "?")
    except Exception as e:
        _sentry_capture(e)
        logger.error("[VOICE_RT] sesija greška uid=%.8s: %s", uid[:8] if uid else "?", e)
    finally:
        await session.close()
        _active_sessions[uid] = max(0, _active_sessions.get(uid, 1) - 1)
        logger.info("[VOICE_RT] sesija zatvorena uid=%.8s", uid[:8] if uid else "?")
