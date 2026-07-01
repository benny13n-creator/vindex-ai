# -*- coding: utf-8 -*-
"""
Vindex AI 2.0 — services/event_bus.py

In-memory pub/sub Event Bus za reaktivnu arhitekturu.
Svaki događaj u sistemu triggeruje handlere bez blokiranja głównog toka.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger("vindex.event_bus")


# ─── Event tipovi ─────────────────────────────────────────────────────────────

class EventType(str, Enum):
    PREDMET_KREIRAN        = "predmet_kreiran"
    DOKUMENT_UPLOADOVAN    = "dokument_uploadovan"
    ROK_DODAN              = "rok_dodan"
    ROK_KRITICAN           = "rok_kritican"
    ROCISTE_ZAKAZANO       = "rociste_zakazano"
    STRATEGIJA_GENERISANA  = "strategija_generisana"
    ANALIZA_ZAHTEVANA      = "analiza_zahtevana"
    HEALTH_SCORE_PROMENJEN = "health_score_promenjen"


# ─── Event dataclass ──────────────────────────────────────────────────────────

@dataclass
class Event:
    type:       EventType
    user_id:    str
    predmet_id: str | None          = None
    payload:    dict[str, Any]      = field(default_factory=dict)
    timestamp:  datetime            = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Predefinisani handleri ───────────────────────────────────────────────────

async def on_rok_kritican(event: Event) -> None:
    """Beleži kritičan rok u decision_log i kreira proactive alert."""
    try:
        from services.decision_log import log_decision, DecisionType
        await log_decision(
            user_id    = event.user_id,
            predmet_id = event.predmet_id,
            akcija     = DecisionType.ROK_DODAT,
            kontekst   = event.payload,
            alternative= [],
            urgentnost = "hitna",
        )

        from shared.deps import _get_supa
        supa = _get_supa()
        rok_naziv = event.payload.get("naziv", "Rok")
        rok_datum = event.payload.get("datum", "")
        await asyncio.to_thread(
            lambda: supa.table("proactive_alerts").insert({
                "user_id":    event.user_id,
                "predmet_id": event.predmet_id,
                "tip":        "rok_kritican",
                "naslov":     f"Kritičan rok: {rok_naziv}",
                "opis":       f"Rok ističe: {rok_datum}. Odmah proverite predmet.",
                "urgentnost": "hitna",
            }).execute()
        )
        logger.info("[EventBus] on_rok_kritican: predmet=%s rok=%s", event.predmet_id, rok_naziv)
    except Exception as exc:
        logger.warning("[EventBus] on_rok_kritican greška: %s", exc)


async def on_predmet_kreiran(event: Event) -> None:
    """Triggeruje case pipeline kad je predmet kreiran."""
    try:
        if not event.predmet_id:
            return
        from services.case_pipeline import run_case_pipeline
        await run_case_pipeline(event.predmet_id, event.user_id)
        logger.info("[EventBus] on_predmet_kreiran: pipeline pokrenut za %s", event.predmet_id)
    except Exception as exc:
        logger.warning("[EventBus] on_predmet_kreiran greška: %s", exc)


async def on_dokument_uploadovan(event: Event) -> None:
    """Beleži upload dokumenta u decision_log."""
    try:
        from services.decision_log import log_decision, DecisionType
        await log_decision(
            user_id    = event.user_id,
            predmet_id = event.predmet_id,
            akcija     = DecisionType.DOKUMENT_PRILOZEN,
            kontekst   = event.payload,
            alternative= [],
        )
        logger.info("[EventBus] on_dokument_uploadovan: %s", event.payload.get("naziv", ""))
    except Exception as exc:
        logger.warning("[EventBus] on_dokument_uploadovan greška: %s", exc)


async def on_health_score_promenjen(event: Event) -> None:
    """Kreira alert ako health score padne ispod 30."""
    try:
        score = event.payload.get("health_score", 100)
        if score >= 30:
            return
        from shared.deps import _get_supa
        supa = _get_supa()
        await asyncio.to_thread(
            lambda: supa.table("proactive_alerts").insert({
                "user_id":    event.user_id,
                "predmet_id": event.predmet_id,
                "tip":        "nizak_health_score",
                "naslov":     f"Predmet u riziku — Health Score: {score}/100",
                "opis":       "Predmet ima nizak health score. Proverite nedostajuće dokaze i rokove.",
                "urgentnost": "visoka",
            }).execute()
        )
        logger.info("[EventBus] on_health_score: alert za score=%d predmet=%s", score, event.predmet_id)
    except Exception as exc:
        logger.warning("[EventBus] on_health_score_promenjen greška: %s", exc)


# ─── EventBus klasa ───────────────────────────────────────────────────────────

HandlerType = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    In-memory pub/sub Event Bus.
    Thread-safe za asyncio event loop — handleri se pokreću kao fire-and-forget taskovi.
    """

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[HandlerType]] = {et: [] for et in EventType}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.subscribe(EventType.ROK_KRITICAN,           on_rok_kritican)
        self.subscribe(EventType.PREDMET_KREIRAN,        on_predmet_kreiran)
        self.subscribe(EventType.DOKUMENT_UPLOADOVAN,    on_dokument_uploadovan)
        self.subscribe(EventType.HEALTH_SCORE_PROMENJEN, on_health_score_promenjen)

    def subscribe(self, event_type: EventType, handler: HandlerType) -> None:
        """Registruje async handler za dati tip događaja."""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug("[EventBus] subscribe: %s → %s", event_type, handler.__name__)

    def publish(self, event: Event) -> None:
        """
        Objavljuje događaj — svi handleri se pokreću kao fire-and-forget asyncio taskovi.
        Nikad ne blokira pozivaoce. Greška u handleru se loguje, ne propagira.
        """
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            return

        for handler in handlers:
            async def _run(h: HandlerType = handler, e: Event = event) -> None:
                try:
                    await h(e)
                except Exception as exc:
                    logger.error("[EventBus] handler %s greška: %s", h.__name__, exc)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_run())
            except RuntimeError:
                asyncio.run(_run())

        logger.debug("[EventBus] publish: %s predmet=%s", event.type, event.predmet_id)

    async def publish_async(self, event: Event) -> None:
        """Async verzija publish — awaitable, čeka završetak SVIH handlera."""
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            return
        await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)


# ─── Singleton ────────────────────────────────────────────────────────────────

bus = EventBus()


# ─── Helper funkcije ──────────────────────────────────────────────────────────

def emit(
    event_type: EventType,
    user_id:    str,
    predmet_id: str | None       = None,
    payload:    dict[str, Any]   = None,
) -> None:
    """Shortcut za bus.publish — kreira Event i objavljuje."""
    bus.publish(Event(
        type       = event_type,
        user_id    = user_id,
        predmet_id = predmet_id,
        payload    = payload or {},
    ))
