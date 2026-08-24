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
    # Faza 1 Case Genome reliability (90-dnevni plan, 2026-07-18, stavka 1.1)
    # — upisuje se SAMO u durable outbox ('events' tabela, direktan insert iz
    # routers/case_dna.py), nikad kroz Python emit()/bus.publish() direktno,
    # da dispatch_pending_events() ne pokrene isti handler dvaput.
    GENOME_UPDATED         = "GenomeUpdated"
    # Faza 0 Smart Intake — job lifecycle, NE AI ponašanje (klasifikacija/
    # ekstrakcija dolaze u Fazi 1). Vrednosti moraju biti IDENTIČNE stringu
    # koji enqueue_intake_job RPC upisuje u events.event_type.
    DOCUMENT_JOB_ENQUEUED  = "DocumentJobEnqueued"
    DOCUMENT_JOB_COMPLETED = "DocumentJobCompleted"
    DOCUMENT_JOB_FAILED    = "DocumentJobFailed"
    # Program Delta, Sprint 001 (2026-08-05) — "Canonical Case Evolution
    # Engine". These 8 event types are Task 1's own required mapping of
    # every event that changes a predmet's state — the mission's own
    # explicit instruction is "prove ONE entry point exists," not
    # "implement all of them." Only DOCUMENT_ACCEPTED has a registered
    # consequence handler this sprint (services/case_evolution.py); the
    # other 7 are declared here (a real, checkable "one entry point per
    # event type" claim) and tracked as not-yet-wired in
    # CASE_EVOLUTION_REGISTRY.md — never silently invented consequences for
    # events with no proven need yet.
    DOCUMENT_ACCEPTED           = "DocumentAccepted"
    DOCUMENT_MODIFIED           = "DocumentModified"
    NEW_CLIENT_LINKED           = "NewClientLinked"
    NEW_EVIDENCE_REGISTERED     = "NewEvidenceRegistered"
    CONFIDENCE_DROPPED          = "ConfidenceDropped"
    MANUAL_CORRECTION_APPLIED   = "ManualCorrectionApplied"
    REVIEW_ACCEPTED             = "ReviewAccepted"
    REVIEW_REJECTED             = "ReviewRejected"
    # Program Omega, Sprint 002 (2026-08-06) — "Case Intelligence Aggregation
    # Engine". Fired ONCE per (predmet_id) touched by a finalize-batch
    # operation (routers/smart_intake.py::finalize_intake_jobs_batch) — NOT
    # once per document/job. This is the mechanism that turns "500 documents
    # finalized" into "one case-level refresh" instead of N redundant Genome
    # recomputes (Program Omega Sprint 001's own named, deferred `OMEGA-001`).
    DOCUMENT_BATCH_COMPLETED    = "DocumentBatchCompleted"


# ─── Event dataclass ──────────────────────────────────────────────────────────

@dataclass
class Event:
    type:           EventType
    user_id:        str
    predmet_id:     str | None       = None
    payload:        dict[str, Any]   = field(default_factory=dict)
    timestamp:      datetime         = field(default_factory=lambda: datetime.now(timezone.utc))
    # Mission Ledger (2026-08-03): correlation_id je sada prvoklasno polje
    # Event-a, ne samo nešto zakopano u payload-u (kako je GENOME_UPDATED
    # ranije radio) — isti id koji shared/ai_provenance.py generiše po
    # zahtevu i koji shared/audit_immutable.py::log_action/security/
    # ai_forensics.py već koriste, tako da JEDAN id povezuje HTTP zahtev →
    # Event Bus → AI Provenance → Audit (Phase 2, Correlation ID Continuity).
    correlation_id: str | None       = None
    # Program Delta, Sprint 001 (2026-08-05) — the durable outbox row's own
    # `events.id` (migration 073), populated by dispatch_pending_events()
    # below. This is the identity services/case_evolution.py keys its own
    # per-consequence idempotency on — NOT correlation_id, which can be
    # (and often is) shared across multiple distinct operations in the same
    # logical request. None for an event published purely in-process
    # (bus.publish(), never durably logged) — the canonical consequence
    # engine requires a durable event_id and will refuse to run without one
    # (see handle_case_changed's own guard), by design: an in-process-only
    # event offers no crash-survivable idempotency key to check against.
    event_id:       str | None       = None


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
        from shared.proactive_alerts import create_proactive_alert
        supa = _get_supa()
        rok_naziv = event.payload.get("naziv", "Rok")
        rok_datum = event.payload.get("datum", "")
        _ok = await create_proactive_alert(
            supa,
            user_id=event.user_id,
            predmet_id=event.predmet_id,
            tip="rok_kritican",
            naslov=f"Kritičan rok: {rok_naziv}",
            opis=f"Rok ističe: {rok_datum}. Odmah proverite predmet.",
            urgentnost="hitna",
            # Mission Olympus governance review (2026-08-04, F-5), kept
            # forward-compatible even though not currently load-bearing for
            # THIS handler (see the corrected note below): if ROK_KRITICAN
            # is ever converted to the durable outbox (SENT-001, still
            # open), this same handler would then run inside
            # dispatch_pending_events()'s batch loop, where the internal
            # blocking retry would compound with the outer one and risk
            # exceeding migration 091's stale-claim window.
            retry_internally=False,
        )
        if not _ok:
            # CORRECTED (Mission Olympus governance review, 2026-08-04,
            # Reliability & Chaos Agent's F-1 finding): this handler is
            # currently invoked ONLY via the in-process emit()/bus.publish()
            # path (routers/matter_intel.py) -- publish()'s own _run()
            # wrapper (below in this file) catches every handler exception
            # and only logs it, it never re-raises further. This `raise`
            # does NOT currently reach dispatch_pending_events()'s outer
            # retry/dead-letter mechanism the way on_document_job_failed's
            # does (that one IS durable-outbox-connected) -- ROK_KRITICAN
            # has no durable outbox row at all yet (SENT-001, unchanged,
            # still open). This raise still has real, if smaller, value:
            # it's caught by this handler's own outer except below and
            # logged there, and keeps this handler's shape consistent with
            # every other Event Bus handler's re-raise-after-log discipline
            # (Project Phoenix) so it's automatically correct the day
            # SENT-001 is finally closed. Do not read this as "dead-lettered
            # if it fails" -- it is not, today.
            raise RuntimeError(f"proactive_alert insert permanently failed: rok_kritican predmet={event.predmet_id}")
        logger.info("[EventBus] on_rok_kritican: predmet=%s rok=%s", event.predmet_id, rok_naziv)
    except Exception as exc:
        logger.warning("[EventBus] on_rok_kritican greška: %s", exc)
        # Project Phoenix (2026-08-03): re-baci posle logovanja -- v. napomenu
        # na EventBus.publish_async() za zašto ovo mora da se propagira.
        raise


async def on_predmet_kreiran(event: Event) -> None:
    """Triggeruje case pipeline kad je predmet kreiran.

    Program Sigma, Master Sprint 001 (2026-08-06): `event.payload["skip_pipeline_steps"]`
    (optional list of step names) is forwarded to `run_case_pipeline` unchanged --
    lets a caller opt individual pipeline steps out without this handler needing
    to know WHY (e.g. routers/smart_intake.py's own new PREDMET_KREIRAN emission
    passes `["ekstrakcija_rokova"]`, see case_pipeline.py::_step_ekstrakcija_rokova's
    own docstring)."""
    try:
        if not event.predmet_id:
            return
        from services.case_pipeline import run_case_pipeline
        skip_steps = frozenset((event.payload or {}).get("skip_pipeline_steps") or ())
        await run_case_pipeline(event.predmet_id, event.user_id, skip_steps=skip_steps)
        logger.info("[EventBus] on_predmet_kreiran: pipeline pokrenut za %s", event.predmet_id)
    except Exception as exc:
        logger.warning("[EventBus] on_predmet_kreiran greška: %s", exc)
        raise


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
        raise


async def on_health_score_promenjen(event: Event) -> None:
    """Kreira alert ako health score padne ispod 30."""
    try:
        score = event.payload.get("health_score", 100)
        if score >= 30:
            return
        from shared.deps import _get_supa
        from shared.proactive_alerts import create_proactive_alert
        supa = _get_supa()
        _ok = await create_proactive_alert(
            supa,
            user_id=event.user_id,
            predmet_id=event.predmet_id,
            tip="nizak_health_score",
            naslov=f"Predmet u riziku — Health Score: {score}/100",
            opis="Predmet ima nizak health score. Proverite nedostajuće dokaze i rokove.",
            urgentnost="visoka",
            retry_internally=False,  # see on_rok_kritican's own comment above
        )
        if not _ok:
            raise RuntimeError(f"proactive_alert insert permanently failed: nizak_health_score predmet={event.predmet_id}")
        logger.info("[EventBus] on_health_score: alert za score=%d predmet=%s", score, event.predmet_id)
    except Exception as exc:
        logger.warning("[EventBus] on_health_score_promenjen greška: %s", exc)
        raise


async def on_document_job_failed(event: Event) -> None:
    """Project Sentinel (2026-08-03) — DocumentJobFailed je ranije bio
    dispečovan i tiho odbačen (nula registrovanih handlera od Faze 0 Smart
    Intake-a naovamo) — permanentno neuspeo OCR/intake posao (posle svih
    pokušaja, v. fail_intake_job RPC) nije proizvodio nikakav proactive_alert
    niti obaveštenje; advokat je jedini način da sazna bio da ručno proveri
    status dokumenta. migrations/073_intake_foundations.sql's fail_intake_job
    RPC upisuje SAMO event_type/payload na 'events' red (bez user_id/
    predmet_id) — vlasnik posla se mora razrešiti preko intake_jobs.uploaded_by."""
    try:
        job_id = (event.payload or {}).get("intake_job_id")
        if not job_id:
            return
        from shared.deps import _get_supa
        supa = _get_supa()
        job_r = await asyncio.to_thread(
            lambda: supa.table("intake_jobs")
                .select("uploaded_by,predmet_id,storage_path,last_error")
                .eq("id", job_id)
                .limit(1)
                .execute()
        )
        job = (job_r.data or [{}])[0]
        uid = job.get("uploaded_by")
        if not uid:
            logger.warning("[EventBus] on_document_job_failed: intake_job=%s nema uploaded_by, alert preskočen", job_id)
            return
        naziv = (job.get("storage_path") or "dokument").rsplit("/", 1)[-1]
        greska = (job.get("last_error") or "")[:200]
        from shared.proactive_alerts import create_proactive_alert
        _ok = await create_proactive_alert(
            supa,
            user_id=uid,
            predmet_id=job.get("predmet_id"),
            tip="dokument_obrada_neuspesna",
            naslov=f"Obrada dokumenta neuspešna: {naziv}",
            opis=f"Dokument nije uspeo da se obradi posle svih pokušaja. Greška: {greska}. Otpremite dokument ponovo.",
            urgentnost="visoka",
            # Mission Olympus governance review (2026-08-04, F-5) -- unlike
            # on_rok_kritican/on_health_score_promenjen above, THIS handler
            # genuinely IS invoked via the durable outbox: fail_intake_job
            # (migrations/073_intake_foundations.sql) inserts a real
            # DocumentJobFailed row into 'events', dispatched via
            # dispatch_pending_events() -> bus.publish_async(). The `raise`
            # below genuinely does reach that outer retry/dead-letter
            # mechanism (Project Phoenix) for this handler specifically --
            # retry_internally=False here avoids compounding this
            # function's own blocking retry with that outer one.
            retry_internally=False,
        )
        if not _ok:
            raise RuntimeError(f"proactive_alert insert permanently failed: dokument_obrada_neuspesna intake_job={job_id}")
        logger.info("[EventBus] on_document_job_failed: alert kreiran za intake_job=%s uid=%s", job_id, uid)
    except Exception as exc:
        logger.warning("[EventBus] on_document_job_failed greška: %s", exc)
        raise


async def on_genome_updated(event: Event) -> None:
    """Faza 1.2 (90-dnevni plan, 2026-07-18) — prvi stvaran potrošač GENOME_UPDATED
    eventa. Upisuje audit_immutable red (hash-chain, nepromenjiv) za svaku Genome
    promenu — ko/kada su vec kolone log_action()-a, zasto/agent/pre-posle/
    korelacija idu u metadata (log_action nema dedikovane kolone za njih).

    Mission Ledger (2026-08-03): correlation_id se sada eksplicitno prosleđuje
    iz event.correlation_id (prvoklasno polje Event-a) umesto oslanjanja na
    ai_provenance.py's kontekst — ovaj handler često radi kroz
    dispatch_pending_events() poller, van bilo kog HTTP zahteva, gde taj
    kontekst ne postoji. Metadata i dalje čuva istu vrednost radi
    kompatibilnosti sa starijim čitaocima."""
    try:
        from shared.audit_immutable import log_action
        payload = event.payload or {}
        _cid = event.correlation_id or payload.get("correlation_id")
        await log_action(
            action        = "genome_refresh",
            user_id       = event.user_id,
            resource_type = "predmet",
            resource_id   = event.predmet_id,
            correlation_id = _cid,
            metadata      = {
                "trigger":                 payload.get("trigger"),
                "agent":                   "case_dna_extractor",
                "verzija":                 payload.get("verzija"),
                "prev_verzija":            payload.get("prev_verzija"),
                "snaga_predmeta_procent":  payload.get("snaga_predmeta_procent"),
                "correlation_id":          _cid,
                # Faza 1.3 — verify_genome() odluka (approve/approve_with_warning/
                # require_review); require_review je status na sacuvanom Genome-u,
                # ne blokada snimanja.
                "verifikacija_odluka":     payload.get("verifikacija_odluka"),
            },
        )
        logger.info("[EventBus] on_genome_updated: audit upisan predmet=%s v%s",
                    event.predmet_id, payload.get("verzija"))
    except Exception as exc:
        logger.warning("[EventBus] on_genome_updated greška: %s", exc)
        raise


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
        self.subscribe(EventType.GENOME_UPDATED,          on_genome_updated)
        self.subscribe(EventType.DOCUMENT_JOB_FAILED,     on_document_job_failed)
        # Program Delta, Sprint 001 (2026-08-05) — the ONE canonical
        # consequence dispatcher (services/case_evolution.py). Registered
        # here, imported lazily inside _register_defaults' own call to
        # avoid a module-level circular import (case_evolution imports
        # Event/EventType from this module).
        from services.case_evolution import handle_case_changed
        self.subscribe(EventType.DOCUMENT_ACCEPTED, handle_case_changed)
        # Program Delta, Sprint 002 (2026-08-05) — Canonical Event Migration
        # I. 4 more event types now flow through the SAME dispatcher; each
        # one's own consequence list (or deliberate lack thereof) lives in
        # services/case_evolution.py::CONSEQUENCE_REGISTRY, never here.
        self.subscribe(EventType.REVIEW_ACCEPTED,         handle_case_changed)
        self.subscribe(EventType.REVIEW_REJECTED,         handle_case_changed)
        self.subscribe(EventType.NEW_CLIENT_LINKED,       handle_case_changed)
        self.subscribe(EventType.NEW_EVIDENCE_REGISTERED, handle_case_changed)
        # Program Delta, Sprint 003 (2026-08-05) — Canonical Event Migration
        # II. ROCISTE_ZAKAZANO existed in this enum since before Program
        # Delta but had ZERO handlers and was never emitted anywhere
        # (confirmed by repo-wide grep) — now wired for the first time,
        # replacing routers/rocista.py's own direct Genome-refresh call.
        self.subscribe(EventType.ROCISTE_ZAKAZANO,        handle_case_changed)
        # Program Omega, Sprint 002 (2026-08-06) — Case Intelligence
        # Aggregation Engine. Same canonical dispatcher, no separate
        # mechanism — see services/case_evolution.py::refresh_case_intelligence.
        self.subscribe(EventType.DOCUMENT_BATCH_COMPLETED, handle_case_changed)

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
        """Async verzija publish — awaitable, čeka završetak SVIH handlera.

        Project Phoenix (2026-08-03): ranije je `return_exceptions=True` tiho
        gutao SVAKI handler exception pre nego što bi ikad stigao do
        dispatch_pending_events()'s sopstvenog except bloka — koji postoji
        upravo da bi track-ovao dispatch_attempts/last_error i omogućio
        pravi retry (migracija 073 je dodala te kolone TAČNO za ovaj
        slučaj, ali su ostale mrtve za klasu "handler bug", ne "infra pad").
        Kombinovano sa time da svaki handler VEĆ hvata i loguje sopstvene
        greške pa ih sada i re-baca, ovde se PROVERAVA da li je neki handler
        pao POSLE što su svi (uspešni i neuspešni) završili izvršavanje —
        `return_exceptions=True` ostaje (jedan pokvaren handler ne sme da
        spreči IZVRŠAVANJE drugih), samo se REZULTAT sada ispravno
        prijavljuje pozivaocu umesto da nestane bez traga."""
        handlers = self._handlers.get(event.type, [])
        if not handlers:
            return
        results = await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result


# ─── Singleton ────────────────────────────────────────────────────────────────

bus = EventBus()


# ─── Helper funkcije ──────────────────────────────────────────────────────────

def emit(
    event_type:     EventType,
    user_id:        str,
    predmet_id:     str | None       = None,
    payload:        dict[str, Any]   = None,
    correlation_id: str | None       = None,
) -> None:
    """Shortcut za bus.publish — kreira Event i objavljuje.

    Mission Ledger (2026-08-03): correlation_id se, ako nije eksplicitno
    prosleđen, automatski čita iz shared/ai_provenance.py's request-scoped
    konteksta (isti id koji log_action/AI wrapper već koriste) — pozivna
    mesta (npr. routers/matter_intel.py's ROK_KRITICAN/HEALTH_SCORE_PROMENJEN)
    dobijaju kontinuitet BESPLATNO, bez izmene sopstvenog koda."""
    if correlation_id is None:
        try:
            from shared.ai_provenance import current_correlation_id
            correlation_id = current_correlation_id()
        except Exception:
            correlation_id = None
    bus.publish(Event(
        type           = event_type,
        user_id        = user_id,
        predmet_id     = predmet_id,
        payload        = payload or {},
        correlation_id = correlation_id,
    ))


# ═══════════════════════════════════════════════════════════════════════════
# BLK-2.1 — DOGADJAJ SE NE UPISUJE ZA PREDMET KOJI SE BRIŠE ILI JE OBRISAN
# ═══════════════════════════════════════════════════════════════════════════
#
# Dokazano determinističkom trkom (55 iteracija, barijera puštena TAČNO kad
# korak 5b brisanja obriše `events`): **54/55 je proizvelo orphan** — predmet
# obrisan, a `events` red sa njegovim `predmet_id` ostao. `events.predmet_id`
# nema FK, pa ga korak 7 (`DELETE FROM predmeti`) ne dodiruje.
#
# Zašto guard, a ne „metla posle brisanja": metla nije atomarna prema piscu i
# ne sprečava da poller DISPEČUJE takav događaj (`dispatch_pending_events` ne
# proverava postojanje predmeta) — Case Evolution bi se pokrenuo nad mrtvim
# predmetom. Presretanje na PISCU je najranija tačka na kojoj se to može
# sprečiti.
#
# Zašto NE strani ključ `events.predmet_id → predmeti.id`: izmereno na
# produkciji — kolona je `TEXT`, `predmeti.id` je `UUID`, i **871 od 1000**
# redova u uzorku nosi vrednosti koje nisu UUID (`"pred-1"`, `"pred-001"` —
# talog jediničnih testova), uz 86 redova sa `NULL`. FK bi zahtevao promenu
# tipa i brisanje/migraciju tih redova, što invarijanta 8 specifikacije
# izričito zabranjuje bez dokaza da nema orphan redova. Zato: bez izmene šeme.
#
# Koristi se POSTOJEĆI tombstone (`predmeti.brisanje_zapoceto`, migracija 114),
# isti koji `shared/rag_acl.py` već koristi da isključi predmet iz RAG-a — nije
# uveden nov mehanizam.

_NEISPRAVAN_UUID_KODOVI = ("22P02", "invalid input syntax for type uuid")


def _je_uuid(vrednost: str) -> bool:
    import uuid as _uuid
    try:
        _uuid.UUID(str(vrednost))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


async def predmet_prima_dogadjaje(supa, predmet_id: "str | None") -> bool:
    """True ako se za `predmet_id` sme upisati događaj.

    False SAMO kad je dokazano da predmet ne postoji ili je označen za brisanje.

    Namerno propušta (vraća True) u tri slučaja:
      1. `predmet_id` je prazan — događaj nije vezan za predmet (sistemski);
      2. `predmet_id` nije UUID — takav red ne može referencirati stvaran
         predmet (kolona `predmeti.id` je UUID), pa ne može ni biti orphan
         obrisanog predmeta; upit bi samo pukao sa `22P02`;
      3. sama provera je pala — `events` je outbox čiji gubitak trajno lomi
         Case Pipeline (BLACKSWAN-HIGH-008: predmet bez `PREDMET_KREIRAN`
         događaja nikad ne dobije nijedan prolaz), dok je orphan red pitanje
         higijene. Zato prolazna greška baze NE sme da guta događaje. Loguje se.
    """
    if not predmet_id or not _je_uuid(predmet_id):
        return True
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id, brisanje_zapoceto")
                .eq("id", predmet_id)
                .limit(1)
                .execute()
        )
        redovi = getattr(r, "data", None) or []
    except Exception as exc:
        if any(k.lower() in str(exc).lower() for k in _NEISPRAVAN_UUID_KODOVI):
            return True
        logger.warning(
            "[EVENT_BUS] provera stanja predmeta %s nije izvedena (%s) — dogadjaj se PROPUSTA "
            "da se outbox ne bi tiho gubio; moguc orphan ako je predmet u brisanju.",
            str(predmet_id)[:8], exc,
        )
        return True
    if not redovi:
        logger.info("[EVENT_BUS] dogadjaj odbijen: predmet %s ne postoji (obrisan).",
                    str(predmet_id)[:8])
        return False
    if redovi[0].get("brisanje_zapoceto"):
        logger.info("[EVENT_BUS] dogadjaj odbijen: predmet %s je oznacen za brisanje.",
                    str(predmet_id)[:8])
        return False
    return True


# ─── Canonical durable emission helper (Program Delta, Sprint 002) ───────────
# Sprint 001 introduced ONE emission idiom (INSERT INTO events, tolerant of
# correlation_id column missing pre-migration-090) at exactly one call site
# (DOCUMENT_ACCEPTED). Sprint 002 migrates 4 more scattered call sites onto
# the SAME idiom — factored out here so there is exactly ONE place that
# knows how to durably emit an event, not 5 copies of the same try/except
# fallback. Callers still wrap this in their own try/except (message context
# — which predmet/dokument/job — differs per call site and belongs to the
# caller, not this helper); this function re-raises anything that isn't the
# known "correlation_id column not migrated yet" case.

async def emit_durable(
    event_type:     "EventType",
    user_id:        str,
    predmet_id:     str | None,
    payload:        dict[str, Any],
    supa=None,
    event_id:       str | None = None,
) -> None:
    """Durably inserts one row into the 'events' outbox — the caller's own
    state-changing work must already be committed BEFORE calling this (same
    discipline as every existing emission site: the event represents
    something that already happened, never a promise of something about to
    happen). Fail-soft is the CALLER's responsibility (wrap in try/except),
    matching PREDMET_KREIRAN/DOCUMENT_ACCEPTED's own established pattern —
    this helper raises on any error that isn't the tolerated missing-column
    case, it does not itself swallow anything.

    `event_id` (S6, 2026-08-20) -- OPCIONO i podrazumevano None, pa je ponasanje
    svih 11 postojecih poziva nepromenjeno (baza i dalje generise `id`).
    Kad je prosledjen, koristi se kao `events.id` uz `ignore_duplicates=True`
    (PostgREST `ON CONFLICT (id) DO NOTHING`), pa POZIVALAC dobija pravo da
    definise STABILAN POSLOVNI IDENTITET dogadjaja. Time ponovljen upis istog
    poslovnog dogadjaja postaje no-op umesto drugog reda, a brana je vec
    postojeci `events.id` PRIMARY KEY (migracija 073) -- bez ijedne izmene seme.

    Zasto je to potrebno: bez stabilnog identiteta svaki retry pravi NOV
    `events.id`, dakle NOV poslovni dogadjaj, dakle drugu COI posledicu i drugi
    alarm. Izmereno: retry bez identiteta -> 2 posledice, 2 alarma; ista
    isporuka istog id-a x3 -> 1 posledica, 1 alarm."""
    if supa is None:
        from shared.deps import _get_supa
        supa = _get_supa()
    # BLK-2.1 — najranija tačka na kojoj se orphan može sprečiti.
    if not await predmet_prima_dogadjaje(supa, predmet_id):
        return
    from shared.ai_provenance import current_correlation_id
    _cid = current_correlation_id()
    _evt_row = {
        "event_type": event_type.value,
        "user_id":    user_id,
        "predmet_id": predmet_id,
        "payload":    {**payload, "correlation_id": _cid},
    }
    if event_id is not None:
        _evt_row["id"] = event_id
    # `ignore_duplicates=True` samo kad pozivalac nosi identitet -- inace bi
    # menjalo ponasanje postojecih poziva.
    _opts = {"ignore_duplicates": True} if event_id is not None else {}
    from shared.audit_immutable import _is_missing_column_error
    try:
        await asyncio.to_thread(
            lambda: supa.table("events").insert({**_evt_row, "correlation_id": _cid}, **_opts).execute()
        )
    except Exception as _wide_exc:
        if not _is_missing_column_error(_wide_exc):
            raise
        await asyncio.to_thread(lambda: supa.table("events").insert(_evt_row, **_opts).execute())


# ─── Durable outbox dispatch (Faza 0, ADR-0001) ────────────────────────────────
# Poller — čita nedispečovane redove iz 'events' tabele (migracija 073) i
# pokreće ih kroz isti in-memory handler registry. Redovi se pišu u istoj
# Postgres transakciji kao promena koja ih je izazvala (npr. enqueue_intake_job
# RPC) — "publish" u smislu ovog fajla znači "handler pozvan", ne "događaj
# zabeležen"; beleženje je već trajno urađeno pre nego što ovaj poller ikad
# pokrene.

DISPATCH_BATCH_SIZE = 50

# Project Phoenix (2026-08-03): sada kad publish_async() ispravno propagira
# handler greške (v. napomenu tamo), jedan trajno pokvaren handler bi bez
# gornje granice pokušavao ZAUVEK, na svakih 3s (DispatchLoop) — "retry
# exhaustion never triggers, infinite retry storm" klasa rizika koju je ova
# misija eksplicitno tražila da se proveri. Ista granica kao Smart Intake's
# već dokazan max_attempts=5 (migracija 073, fail_intake_job).
MAX_DISPATCH_ATTEMPTS = 5


def _is_missing_function_error(exc: Exception) -> bool:
    """Mission Keystone (2026-08-04): PostgREST's "function not found in
    schema cache" (PGRST202) or Postgres's own undefined_function SQLSTATE
    (42883) — narrow, deliberate check (mirrors shared/audit_immutable.py's
    _is_missing_column_error) so claim_pending_events() falling back to the
    pre-migration-091 plain-select behavior only happens for "RPC not
    deployed yet", never masking an unrelated real error."""
    msg = str(exc).lower()
    return "pgrst202" in msg or "42883" in msg or "could not find the function" in msg


async def dispatch_pending_events(batch_size: int = DISPATCH_BATCH_SIZE) -> dict[str, int]:
    """Čita do batch_size nedispečovanih redova iz 'events', pokreće handlere
    preko bus.publish_async(), i markira dispatched_at. Best-effort po redu —
    greška na jednom redu ne sme da blokira ostale u batch-u. Namerno se ne
    poziva iz FastAPI request handlera — pokreće ga periodičan worker/cron
    (Faza 0 infrastruktura, van ovog fajla).

    Mission Keystone (2026-08-04): produkcija podrazumevano pokreće 4
    gunicorn worker procesa (gunicorn.conf.py), svaki sa sopstvenim
    DispatchLoop-om koji poll-uje ISTU 'events' tabelu na svake 3s. Prostim
    SELECT-om bez claim-a, dva worker-a mogu izabrati isti nedispečovan red u
    istom tick-u i oba pokrenuti handler — duplirani proactive_alerts/audit
    upisi za jedan stvaran događaj (handleri nisu svi idempotentni). Sada se
    prvo pokušava atomski claim preko migracije 091's claim_pending_events()
    RPC-a (SELECT ... FOR UPDATE SKIP LOCKED, isti obrazac kao migracija
    073's claim_intake_job za intake_jobs) -- ako RPC još nije pokrenut,
    tiho se vraća na prethodno ponašanje (funkcionalno identično kao pre ove
    izmene za single-worker slučaj, i dalje izloženo istom riziku dok se
    migracija ne pokrene)."""
    from shared.deps import _get_supa

    supa = _get_supa()
    claimed = True
    try:
        res = await asyncio.to_thread(
            lambda: supa.rpc(
                "claim_pending_events",
                # Program Lambda, Certification 005 (2026-08-07): was 30s,
                # shorter than case_evolution.py's own inner
                # _CONSEQUENCE_STALE_PENDING_SECONDS (300s), creating a
                # cross-layer staleness-mismatch window that could
                # silently, permanently drop a consequence on a worker
                # crash. Raised to 120s, reusing shared/intake_queue.py's
                # own claim_finalize() stale_after_seconds=120 default as
                # precedent -- also more realistic given llm_retry's own
                # worst-case latency (3 attempts w/ backoff can approach
                # 24s+ before counting actual call time). Paired with
                # handle_case_changed's own claim-failure fix, which no
                # longer silently skips a not-yet-completed consequence.
                {"p_batch_size": batch_size, "p_stale_claim_seconds": 120},
            ).execute()
        )
    except Exception as _rpc_exc:
        if not _is_missing_function_error(_rpc_exc):
            raise
        claimed = False
        res = await asyncio.to_thread(
            lambda: supa.table("events")
                .select("*")
                .is_("dispatched_at", "null")
                .order("created_at")
                .limit(batch_size)
                .execute()
        )
    rows = res.data or []
    dispatched, errored, unknown_type, dead_lettered = 0, 0, 0, 0

    # LAMBDA008-EVT-001 fix: claim_pending_events() stamps the WHOLE batch with one
    # claimed_at, but this loop processes it serially and some handlers are GPT-bound
    # (run_case_pipeline, Genome refresh). If cumulative processing time exceeds the
    # p_stale_claim_seconds window (120s) before reaching a later row, that row becomes
    # reclaimable by another worker's next poll while this worker is still legitimately
    # working through the same batch, causing duplicate handler execution. Heartbeat:
    # after each row, push claimed_at forward for the rows still remaining in this
    # batch, so the staleness window is measured from "since this worker last made
    # progress," not "since the batch was claimed."
    remaining_ids = [r["id"] for r in rows]

    async def _heartbeat_remaining() -> None:
        if not claimed or not remaining_ids:
            return
        try:
            await asyncio.to_thread(
                lambda: supa.table("events")
                    .update({"claimed_at": datetime.now(timezone.utc).isoformat()})
                    .in_("id", remaining_ids)
                    .is_("dispatched_at", "null")
                    .execute()
            )
        except Exception:
            logger.debug("[EVENT_BUS] batch claim heartbeat failed (non-fatal)", exc_info=True)

    for row in rows:
        row_id = row["id"]
        if row_id in remaining_ids:
            remaining_ids.remove(row_id)
        # BLACKSWAN-EVT-001 fix (Operation Black Swan, Mission 001): the heartbeat above
        # only ever refreshes claimed_at for rows still QUEUED (`remaining_ids`) -- the
        # row about to be processed right here was just removed from that set, so its OWN
        # claim goes unrefreshed for the entire duration of ITS OWN handler call, however
        # long that takes. If cumulative time-already-elapsed-since-batch-claim plus this
        # row's own processing time exceeds the staleness window, a second worker can
        # reclaim and re-run this exact in-flight row. Reproduced (Black Swan Team 14):
        # run_case_pipeline ran twice with overlapping wall-clock windows for the same
        # event. Refresh THIS row's own claim immediately before starting its handler, so
        # it gets the FULL staleness window from the moment its own processing begins, not
        # whatever was left over from earlier rows in the same batch.
        if claimed:
            try:
                await asyncio.to_thread(
                    lambda row_id=row_id: supa.table("events")
                        .update({"claimed_at": datetime.now(timezone.utc).isoformat()})
                        .eq("id", row_id)
                        .is_("dispatched_at", "null")
                        .execute()
                )
            except Exception:
                logger.debug("[EVENT_BUS] pre-process claim heartbeat failed (non-fatal)", exc_info=True)
        raw_type = row.get("event_type")
        try:
            event_type = EventType(raw_type)
        except ValueError:
            logger.warning("[EVENT_BUS] dispatch: nepoznat event_type '%s' (red=%s) — markiram dispečovanim, nema handlera koji bi ga obradio.", raw_type, str(row_id)[:8])
            unknown_type += 1
            await _mark_dispatched(supa, row_id)
            await _heartbeat_remaining()
            continue

        event = Event(
            type           = event_type,
            user_id        = row.get("user_id") or "",
            predmet_id     = row.get("predmet_id"),
            payload        = row.get("payload") or {},
            correlation_id = row.get("correlation_id"),
            # Program Delta, Sprint 001 -- the durable row's own id, the
            # identity services/case_evolution.py keys per-consequence
            # idempotency on (see Event.event_id's own docstring above).
            event_id       = str(row_id),
        )
        try:
            await bus.publish_async(event)
            await _mark_dispatched(supa, row_id)
            dispatched += 1
        except Exception as exc:
            errored += 1
            attempts = (row.get("dispatch_attempts") or 0) + 1
            logger.error("[EVENT_BUS] dispatch greška za red=%s tip=%s (pokušaj %d/%d): %s", str(row_id)[:8], raw_type, attempts, MAX_DISPATCH_ATTEMPTS, exc)

            if attempts >= MAX_DISPATCH_ATTEMPTS:
                # Odustani od daljeg pokušavanja -- BEZ ovoga, trajno pokvaren
                # handler bi se pokušavao zauvek na svaka 3s. Markira se
                # dispatched (poller ga više ne dohvata) da ne uspori batch,
                # ali last_error nosi eksplicitan "DEAD_LETTER" prefiks tako
                # da ovo NIKAD ne izgleda kao tih uspeh -- ostaje dokazivo iz
                # same events tabele (correlation_id + last_error), zadovoljava
                # "nijedan kritični događaj ne sme biti izgubljen bez
                # detekcije" čak i u ovom najgorem slučaju.
                dead_lettered += 1
                logger.critical(
                    "[EVENT_BUS] DEAD_LETTER: red=%s tip=%s odustajem posle %d pokušaja — POTREBNA RUČNA INTERVENCIJA. correlation_id=%s greška=%s",
                    str(row_id)[:8], raw_type, attempts, event.correlation_id, str(exc)[:200],
                )
                await asyncio.to_thread(
                    lambda: supa.table("events")
                        .update({
                            "dispatch_attempts": attempts,
                            "last_error": f"DEAD_LETTER after {attempts} attempts: {str(exc)[:450]}",
                            "dispatched_at": datetime.now(timezone.utc).isoformat(),
                        })
                        .eq("id", row_id)
                        .execute()
                )
            else:
                # Claimed_at se čisti (samo kad je RPC put stvarno korišćen)
                # da neuspešan-ali-ne-iscrpljen red ostane odmah ponovo
                # dostupan za claim na SLEDEĆEM 3s pollu -- bez ovoga bi
                # p_stale_claim_seconds prozor (120s) neopravdano usporio
                # retry cadence koju je Project Phoenix već dokazao testovima.
                #
                # Program Lambda, Certification 005 (2026-08-07) -- EXCEPT for
                # services.case_evolution.ConsequenceClaimPending. That
                # exception is a "come back later" signal (a consequence
                # another attempt claimed is not yet stale enough to
                # reclaim, see its own docstring), not a genuinely broken
                # handler -- clearing claimed_at for it would let this same
                # fast ~3s retry loop re-fire immediately, exhausting
                # MAX_DISPATCH_ATTEMPTS (5) in ~15-18s, nowhere near
                # case_evolution.py's own 300s inner staleness window --
                # dead-lettering an event whose consequence may simply
                # still be legitimately in flight (or was, until a crash),
                # exactly the false-permanent-loss shape this sprint's own
                # fix exists to close. Leaving claimed_at untouched here
                # means the retry cadence is instead governed by the OUTER
                # claim's own 120s staleness window -- comfortably reaching
                # 300s within the 5-attempt budget (~3 outer cycles).
                from services.case_evolution import ConsequenceClaimPending
                _update = {"dispatch_attempts": attempts, "last_error": str(exc)[:500]}
                if claimed and not isinstance(exc, ConsequenceClaimPending):
                    _update["claimed_at"] = None
                await asyncio.to_thread(
                    lambda: supa.table("events")
                        .update(_update)
                        .eq("id", row_id)
                        .execute()
                )

        await _heartbeat_remaining()

    if rows:
        logger.info("[EVENT_BUS] dispatch batch: %d obrađeno, %d dispečovano, %d nepoznat tip, %d grešaka, %d dead-lettered", len(rows), dispatched, unknown_type, errored, dead_lettered)
    return {"obradjeno": len(rows), "dispecovano": dispatched, "nepoznat_tip": unknown_type, "greske": errored, "dead_letter": dead_lettered}


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


# ── Missing-pipeline-event reconciliation (BLACKSWAN-HIGH-008) ─────────────────

async def reap_missing_pipeline_events(min_age_minutes: int = 10, lookback_days: int = 7) -> dict:
    """Operation Black Swan, Mission 001: api.py::kreiraj_predmet's own PREDMET_KREIRAN
    durable-event insert now retries on transient failure (see that function's own
    comment), but a genuinely sustained outage can still exhaust the retry and leave a
    predmet with no pipeline run and no trace it was ever supposed to have one. This is
    the out-of-band repair: find predmeti created more than `min_age_minutes` ago (so a
    request still legitimately in flight is never touched) within the last
    `lookback_days` (bounded, not a full-table scan forever) that have no `events` row of
    type PREDMET_KREIRAN, and backfill one via the same durable-outbox insert the
    original endpoint uses -- dispatch_pending_events() then runs the real Case Pipeline
    on it normally, no special-casing needed downstream."""
    from datetime import datetime, timedelta, timezone
    from shared.deps import _get_supa

    supa = _get_supa()
    now = datetime.now(timezone.utc)
    cutoff_new = (now - timedelta(minutes=min_age_minutes)).isoformat()
    cutoff_old = (now - timedelta(days=lookback_days)).isoformat()

    preds_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id, user_id, naziv, tip, created_at")
            .gte("created_at", cutoff_old)
            .lt("created_at", cutoff_new)
            .execute()
    )
    predmeti = preds_r.data or []
    if not predmeti:
        return {"checked": 0, "backfilled": 0}

    pred_ids = [p["id"] for p in predmeti]
    evt_r = await asyncio.to_thread(
        lambda: supa.table("events")
            .select("predmet_id")
            .eq("event_type", EventType.PREDMET_KREIRAN.value)
            .in_("predmet_id", pred_ids)
            .execute()
    )
    already_have_event = {e["predmet_id"] for e in (evt_r.data or [])}

    backfilled = 0
    for p in predmeti:
        if p["id"] in already_have_event:
            continue
        # BLK-2.1: reaper bira po `created_at`, bez obzira na tombstone —
        # predmet u brisanju bi ovde dobio NOV dogadjaj koji korak 5b vise
        # nece stici da obrise.
        if not await predmet_prima_dogadjaje(supa, p["id"]):
            continue
        try:
            await asyncio.to_thread(
                lambda p=p: supa.table("events").insert({
                    "event_type": EventType.PREDMET_KREIRAN.value,
                    "user_id":    p["user_id"],
                    "predmet_id": p["id"],
                    "payload":    {"naziv": p.get("naziv"), "tip": p.get("tip"), "backfilled": True},
                }).execute()
            )
            backfilled += 1
            logger.warning(
                "[EVENT_BUS] reap: backfilled missing PREDMET_KREIRAN for predmet=%s (created %s, no event ever recorded)",
                p["id"], p.get("created_at"),
            )
        except Exception as e:
            logger.error("[EVENT_BUS] reap: failed to backfill predmet=%s: %s", p["id"], e)

    return {"checked": len(predmeti), "backfilled": backfilled}


async def reap_missing_rociste_events(min_age_minutes: int = 10, lookback_days: int = 7) -> dict:
    """Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-042 sub-item): the identical
    reaper shape as reap_missing_pipeline_events above, for the one other event
    type whose "should have happened" signal is the same simple 1:1 comparison
    (a `rocista` row exists vs. a ROCISTE_ZAKAZANO event exists for it) --
    `routers/rocista.py::kreiraj_rociste`'s own emit_durable call is already
    wrapped in a non-fatal try/except (a genuinely sustained outage can leave a
    hearing with no event and no trace it was ever supposed to have one, same
    failure shape PREDMET_KREIRAN's reaper already closes). The remaining 6
    Case-Evolution event types (document/review-level) are each conditional on
    a different sub-entity action and need their own per-type detection design
    -- not attempted here, correctly left as genuine infrastructure work."""
    from datetime import datetime, timedelta, timezone
    from shared.deps import _get_supa

    supa = _get_supa()
    now = datetime.now(timezone.utc)
    cutoff_new = (now - timedelta(minutes=min_age_minutes)).isoformat()
    cutoff_old = (now - timedelta(days=lookback_days)).isoformat()

    roc_r = await asyncio.to_thread(
        lambda: supa.table("rocista")
            .select("id, user_id, predmet_id, sud, datum, created_at")
            .gte("created_at", cutoff_old)
            .lt("created_at", cutoff_new)
            .execute()
    )
    rocista = roc_r.data or []
    if not rocista:
        return {"checked": 0, "backfilled": 0}

    evt_r = await asyncio.to_thread(
        lambda: supa.table("events")
            .select("predmet_id, payload")
            .eq("event_type", EventType.ROCISTE_ZAKAZANO.value)
            .in_("predmet_id", [r["predmet_id"] for r in rocista])
            .execute()
    )
    # ROCISTE_ZAKAZANO's own payload carries no rociste-row id -- it's emitted
    # per rociste creation, keyed by (predmet_id, sud, datum), the same
    # (predmet_id, sud, datum, vreme)-adjacent fields -043's own dedup already
    # keys on. predmet_id alone would be too coarse (2 hearings for the same
    # case); (sud, datum) alone would be too broad (2 unrelated cases sharing a
    # court date is a real, not-impossibly-rare coincidence) -- all 3 together.
    evt_keys = set()
    for e in (evt_r.data or []):
        p = e.get("payload") or {}
        evt_keys.add((e.get("predmet_id"), p.get("sud"), p.get("datum")))

    backfilled = 0
    for r in rocista:
        key = (r.get("predmet_id"), r.get("sud"), r.get("datum"))
        if key in evt_keys:
            continue
        # BLK-2.1 — isti razlog kao kod PREDMET_KREIRAN reapera iznad.
        if not await predmet_prima_dogadjaje(supa, r.get("predmet_id")):
            continue
        try:
            await asyncio.to_thread(
                lambda r=r: supa.table("events").insert({
                    "event_type": EventType.ROCISTE_ZAKAZANO.value,
                    "user_id":    r["user_id"],
                    "predmet_id": r["predmet_id"],
                    "payload":    {"sud": r.get("sud"), "datum": r.get("datum"), "trigger": "rociste_created", "backfilled": True},
                }).execute()
            )
            backfilled += 1
            logger.warning(
                "[EVENT_BUS] reap: backfilled missing ROCISTE_ZAKAZANO for rociste=%s predmet=%s (created %s, no event ever recorded)",
                r["id"], r["predmet_id"], r.get("created_at"),
            )
        except Exception as e:
            logger.error("[EVENT_BUS] reap: failed to backfill rociste=%s: %s", r["id"], e)

    return {"checked": len(rocista), "backfilled": backfilled}
