# -*- coding: utf-8 -*-
"""
Vindex AI 2.0 — services/event_bus.py

In-memory pub/sub Event Bus za reaktivnu arhitekturu.
Svaki događaj u sistemu triggeruje handlere bez blokiranja głównog toka.

Faza 0 Smart Intake Engine-a (ADR-0001, dizajn review §6/§26.4) dodaje
durable outbox sloj ispod ovog in-memory bus-a: publish()/publish_async()
ostaju iste (in-process, fire-and-forget dispatch handlerima), ali
dispatch_pending_events() dole čita 'events' tabelu (outbox — pisanu u
istoj Postgres transakciji kao promenu koja je izazvala, npr. preko
enqueue_intake_job RPC) i pokreće handlere preko istog registry-ja. Restart/
redeploy pre nego što je handler pozvan više NE gubi događaj — nedispečovan
red ostaje u bazi dok ga poller ne obradi.
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
    # Faza 0 Smart Intake — job lifecycle, NE AI ponašanje (klasifikacija/
    # ekstrakcija dolaze u Fazi 1). Vrednosti moraju biti IDENTIČNE stringu
    # koji enqueue_intake_job RPC upisuje u events.event_type.
    DOCUMENT_JOB_ENQUEUED  = "DocumentJobEnqueued"
    DOCUMENT_JOB_COMPLETED = "DocumentJobCompleted"
    DOCUMENT_JOB_FAILED    = "DocumentJobFailed"


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


# ─── Durable outbox dispatch (Faza 0, ADR-0001) ────────────────────────────────
# Poller — čita nedispečovane redove iz 'events' tabele (migracija 073) i
# pokreće ih kroz isti in-memory handler registry. Redovi se pišu u istoj
# Postgres transakciji kao promena koja ih je izazvala (npr. enqueue_intake_job
# RPC) — "publish" u smislu ovog fajla znači "handler pozvan", ne "događaj
# zabeležen"; beleženje je već trajno urađeno pre nego što ovaj poller ikad
# pokrene.

DISPATCH_BATCH_SIZE = 50


async def dispatch_pending_events(batch_size: int = DISPATCH_BATCH_SIZE) -> dict[str, int]:
    """Čita do batch_size nedispečovanih redova iz 'events', pokreće handlere
    preko bus.publish_async(), i markira dispatched_at. Best-effort po redu —
    greška na jednom redu ne sme da blokira ostale u batch-u. Namerno se ne
    poziva iz FastAPI request handlera — pokreće ga periodičan worker/cron
    (Faza 0 infrastruktura, van ovog fajla)."""
    from shared.deps import _get_supa

    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("events")
            .select("*")
            .is_("dispatched_at", "null")
            .order("created_at")
            .limit(batch_size)
            .execute()
    )
    rows = res.data or []
    dispatched, errored, unknown_type = 0, 0, 0

    for row in rows:
        row_id = row["id"]
        raw_type = row.get("event_type")
        try:
            event_type = EventType(raw_type)
        except ValueError:
            logger.warning("[EVENT_BUS] dispatch: nepoznat event_type '%s' (red=%s) — markiram dispečovanim, nema handlera koji bi ga obradio.", raw_type, str(row_id)[:8])
            unknown_type += 1
            await _mark_dispatched(supa, row_id)
            continue

        event = Event(
            type       = event_type,
            user_id    = row.get("user_id") or "",
            predmet_id = row.get("predmet_id"),
            payload    = row.get("payload") or {},
        )
        try:
            await bus.publish_async(event)
            await _mark_dispatched(supa, row_id)
            dispatched += 1
        except Exception as exc:
            errored += 1
            logger.error("[EVENT_BUS] dispatch greška za red=%s tip=%s: %s", str(row_id)[:8], raw_type, exc)
            await asyncio.to_thread(
                lambda: supa.table("events")
                    .update({
                        "dispatch_attempts": (row.get("dispatch_attempts") or 0) + 1,
                        "last_error": str(exc)[:500],
                    })
                    .eq("id", row_id)
                    .execute()
            )

    if rows:
        logger.info("[EVENT_BUS] dispatch batch: %d obrađeno, %d dispečovano, %d nepoznat tip, %d grešaka", len(rows), dispatched, unknown_type, errored)
    return {"obradjeno": len(rows), "dispecovano": dispatched, "nepoznat_tip": unknown_type, "greske": errored}


async def _mark_dispatched(supa, row_id: str) -> None:
    await asyncio.to_thread(
        lambda: supa.table("events")
            .update({"dispatched_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", row_id)
            .execute()
    )


# ─── Periodic dispatch loop (Faza 0) ────────────────────────────────────────────
# dispatch_pending_events() postojalo je bez ičega da ga periodično poziva —
# founder je eksplicitno primetio da je to "infrastruktura koja postoji ali
# se ne koristi". Ista graceful start/stop disciplina kao shared/
# intake_worker.py::IntakeWorker, namerno zaseban od njega — dispatch loop
# nema veze sa intake_jobs specifično, servira SVE evente kroz event bus.

_DISPATCH_POLL_INTERVAL_S = 3.0


class DispatchLoop:
    def __init__(self, poll_interval_s: float = _DISPATCH_POLL_INTERVAL_S) -> None:
        self.poll_interval_s = poll_interval_s
        self._shutdown = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._shutdown.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("[EVENT_BUS] dispatch loop pokrenut (poll=%.1fs)", self.poll_interval_s)

    async def stop(self, timeout_s: float = 15.0) -> None:
        self._shutdown.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=timeout_s)
            except asyncio.TimeoutError:
                logger.warning("[EVENT_BUS] dispatch loop nije stao u %.0fs — otkazujem task.", timeout_s)
                self._task.cancel()
            self._task = None
        logger.info("[EVENT_BUS] dispatch loop zaustavljen.")

    async def _run(self) -> None:
        while not self._shutdown.is_set():
            try:
                result = await dispatch_pending_events()
                did_work = result["obradjeno"] > 0
            except Exception:
                logger.exception("[EVENT_BUS] dispatch loop neočekivana greška — nastavlja, ne obara worker.")
                did_work = False

            if not did_work:
                try:
                    await asyncio.wait_for(self._shutdown.wait(), timeout=self.poll_interval_s)
                except asyncio.TimeoutError:
                    pass


dispatch_loop = DispatchLoop()


def start_dispatch_loop() -> None:
    dispatch_loop.start()


async def stop_dispatch_loop() -> None:
    await dispatch_loop.stop()
