# -*- coding: utf-8 -*-
"""
Vindex AI — services/case_evolution.py

Program Delta, Sprint 001 (2026-08-05) — Canonical Case Evolution Engine.

Program Intake (Sprints 001-007) made "a document enters the system"
bulletproof. This module answers the next question, which nothing in the
platform answered canonically before: once a case-changing event happens,
what must AUTOMATICALLY follow — and who decides that, once, instead of
every call site independently deciding "what next" (a direct `_run_genome_
background()` call here, a direct task-insert there, a direct alert-create
somewhere else, each with its own ad-hoc idempotency story or none at all).

The one canonical flow, for every event type registered below:

    Case Changed → Determine Consequences → Execute → Verify → Audit → Complete

Built entirely ON TOP of the ALREADY-EXISTING, already-durable, already-
atomic-claim, already-retry/dead-letter Event Bus (services/event_bus.py,
migrations 073/090/091) — this module does not reimplement durability,
retry, or correlation_id propagation; it adds exactly ONE new concept those
primitives don't provide: per-(event, consequence) completion tracking
(migration 096), which is what makes "crash after Genome, retry, no
duplicate" and "crash after Timeline, retry, resumes where it left off"
true by construction, not by convention.

Scope, per this sprint's own hard token budget and explicit charter: only
ONE event (DOCUMENT_ACCEPTED) has real, wired consequences. The other 7
event types Task 1 required be mapped (services/event_bus.py::EventType)
are declared — proving one canonical entry point exists — but deliberately
left with an empty consequence list; see CASE_EVOLUTION_REGISTRY.md for
each one's own reasoning. Never invented speculative consequences for an
event with no proven need yet.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from services.event_bus import Event, EventType
from shared.deps import _get_supa

logger = logging.getLogger("vindex.case_evolution")


@dataclass(frozen=True)
class ConsequenceDef:
    """One named, independently-idempotent, independently-auditable
    consequence of a case-changing event. `executor` does the work and
    returns an opaque `result_ref` string (verified, not self-reported —
    see each executor's own docstring) used both for the audit trail and
    for future debugging ("what did this consequence actually produce")."""
    name: str
    executor: Callable[[Event], Awaitable[Optional[str]]]


# ─── Per-(event, consequence) completion tracking (migration 096) ────────────

async def _get_consequence_status(event_id: str, name: str) -> Optional[dict]:
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("case_evolution_consequences")
            .select("*").eq("event_id", event_id).eq("consequence_name", name)
            .maybe_single().execute()
    )
    return res.data if res else None


async def _mark_pending(event_id: str, name: str) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("case_evolution_consequences")
            .upsert(
                {"event_id": event_id, "consequence_name": name, "status": "pending", "error": None},
                on_conflict="event_id,consequence_name",
            )
            .execute()
    )


async def _mark_completed(event_id: str, name: str, result_ref: Optional[str]) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("case_evolution_consequences")
            .update({"status": "completed", "result_ref": result_ref, "error": None})
            .eq("event_id", event_id).eq("consequence_name", name)
            .execute()
    )


async def _mark_failed(event_id: str, name: str, error: object) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("case_evolution_consequences")
            .update({"status": "failed", "error": str(error)[:500]})
            .eq("event_id", event_id).eq("consequence_name", name)
            .execute()
    )


# ─── Consequence executors — DOCUMENT_ACCEPTED (the one event wired this sprint) ──

async def _consequence_genome_refresh(event: Event) -> str:
    """Refreshes Case Genome — reuses routers/case_dna.py::
    _run_genome_background() UNCHANGED (this sprint is explicitly forbidden
    from modifying Genome). That function's own outer try/except swallows
    internal failures (logs a warning, never re-raises) — a self-reported
    "no exception" is therefore not proof the refresh actually happened.
    This executor VERIFIES independently instead: re-reads
    `predmeti.case_dna.verzija` before and after the call. `_do_genome_
    refresh` unconditionally increments verzija by exactly 1 on every
    genuinely successful run (confirmed by reading its own source, not
    assumed) — so an unchanged verzija after the call is treated as a
    failure and raised, letting the canonical engine mark this consequence
    'failed' and the outer Event Bus retry/dead-letter mechanism take over,
    instead of silently believing a swallowed internal error succeeded."""
    predmet_id = event.predmet_id
    uid = event.user_id
    if not predmet_id:
        return "skipped_no_predmet_id"

    supa = _get_supa()
    before_res = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("case_dna").eq("id", predmet_id).maybe_single().execute()
    )
    before_data = before_res.data if before_res else None
    before_verzija = (before_data or {}).get("case_dna", {}).get("verzija") if before_data else None

    from routers.case_dna import _run_genome_background
    await _run_genome_background(predmet_id, uid, before_verzija, trigger="case_evolution_document_accepted")

    after_res = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("case_dna").eq("id", predmet_id).maybe_single().execute()
    )
    after_data = after_res.data if after_res else None
    after_verzija = (after_data or {}).get("case_dna", {}).get("verzija") if after_data else None

    if after_verzija is None or after_verzija == before_verzija:
        raise RuntimeError(
            f"genome_refresh verification failed for predmet={predmet_id}: "
            f"verzija unchanged ({before_verzija!r} -> {after_verzija!r})"
        )
    return str(after_verzija)


async def _consequence_timeline_entry(event: Event) -> str:
    """Records a Timeline entry ("document(s) accepted into this case") —
    reuses the exact existing predmet_hronologija insert shape already used
    elsewhere (routers/smart_intake.py's own deadline insert), not a new
    table or a new AI-derived analysis. One event = one entry, even when
    the event's own payload names multiple documents (a finalize call that
    accepted N documents in one pass, per Sprint 005/006's own segmentation
    — see the emission side in routers/smart_intake.py) — deliberately
    matching Genome's own existing per-finalize-call coalescing (not
    per-document), so this sprint doesn't introduce N-times-more Genome
    recomputes than before for a multi-document upload. Self-verifying: the
    insert's own response either returns a row (success, id is the
    result_ref) or raises/returns nothing (failure, propagated)."""
    predmet_id = event.predmet_id
    uid = event.user_id
    if not predmet_id:
        return "skipped_no_predmet_id"

    dokumenti = (event.payload or {}).get("dokumenti") or []
    if len(dokumenti) == 1:
        opis = f"Dokument prihvaćen — {dokumenti[0]}"
    elif dokumenti:
        opis = f"{len(dokumenti)} dokumenata prihvaćeno — {', '.join(dokumenti[:5])}" + (" ..." if len(dokumenti) > 5 else "")
    else:
        opis = "Dokument prihvaćen"

    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("predmet_hronologija").insert({
            "predmet_id": predmet_id,
            "user_id":    uid,
            "dogadjaj":   opis,
            "vaznost":    "informativan",
            "akter":      "Case Evolution Engine",
        }).execute()
    )
    if not res.data:
        raise RuntimeError(f"timeline_entry insert nije uspeo za predmet={predmet_id}")
    return str(res.data[0]["id"])


# ─── Canonical consequence registry ──────────────────────────────────────────
# Program Delta, Sprint 001, Task 1's own explicit instruction: prove ONE
# entry point exists for every event that changes a predmet's state, do not
# implement all of them. Only DOCUMENT_ACCEPTED has a real, tested
# consequence list this sprint — see CASE_EVOLUTION_REGISTRY.md for the
# full per-event reasoning (owner/input/consequences/idempotency/audit/
# retry/rollback/success-criterion) required by Task 4, including the 7
# event types deliberately left empty here.

CONSEQUENCE_REGISTRY: dict[EventType, list[ConsequenceDef]] = {
    EventType.DOCUMENT_ACCEPTED: [
        ConsequenceDef(name="genome_refresh", executor=_consequence_genome_refresh),
        ConsequenceDef(name="timeline_entry", executor=_consequence_timeline_entry),
    ],
}


# ─── The canonical dispatcher ─────────────────────────────────────────────────

async def handle_case_changed(event: Event) -> None:
    """THE one entry point. Registered as the Event Bus handler for every
    event type with a populated CONSEQUENCE_REGISTRY entry (services/
    event_bus.py::EventBus._register_defaults). Callers never call Genome/
    Timeline/Tasks/Alerts directly for a registered event type again — they
    emit the event through the durable outbox; this function alone decides
    and executes the consequences, exactly once each, regardless of how
    many times the underlying Event Bus dispatch retries the event itself.

    Requires a durable `event.event_id` (the outbox row's own id) — refuses
    to run without one rather than silently proceeding with no crash-
    survivable idempotency key (see Event.event_id's own docstring in
    services/event_bus.py)."""
    if not event.event_id:
        logger.error(
            "[CASE_EVOLUTION] event tip=%s bez event_id -- odbijam da izvršim posledice (nema trajnog identiteta za idempotenciju).",
            event.type,
        )
        raise RuntimeError(f"case_evolution: event {event.type} has no durable event_id, cannot guarantee idempotency")

    consequences = CONSEQUENCE_REGISTRY.get(event.type, [])
    if not consequences:
        return

    for c in consequences:
        existing = await _get_consequence_status(event.event_id, c.name)
        if existing and existing.get("status") == "completed":
            # Retry-safe by construction: an already-completed consequence
            # is never re-executed, never re-audited, never re-verified —
            # this is the mechanism Scenario 2/3/5 (crash-after-Genome,
            # crash-after-Timeline, replay) all rely on.
            logger.info(
                "[CASE_EVOLUTION] event=%s posledica=%s već završena, preskačem (retry-safe).",
                event.event_id[:8], c.name,
            )
            continue

        await _mark_pending(event.event_id, c.name)
        try:
            result_ref = await c.executor(event)
        except Exception as exc:
            logger.error("[CASE_EVOLUTION] event=%s posledica=%s neuspešna: %s", event.event_id[:8], c.name, exc)
            await _mark_failed(event.event_id, c.name, exc)
            # Propagate -- the Event Bus's own proven retry/dead-letter
            # mechanism (dispatch_pending_events, MAX_DISPATCH_ATTEMPTS)
            # takes over from here, exactly as it already does for every
            # other handler. A LATER retry re-enters this same loop and
            # skips every consequence already marked 'completed' above.
            raise

        await _mark_completed(event.event_id, c.name, result_ref)

        # Audit -- reuses the existing, proven, tamper-evident primitive
        # (shared/audit_immutable.py), never a parallel log. Best-effort:
        # an audit-write failure must not undo an already-completed,
        # already-verified consequence.
        try:
            from shared.audit_immutable import log_action
            await log_action(
                "case_evolution_consequence_completed",
                user_id=event.user_id,
                resource_type="predmet",
                resource_id=event.predmet_id,
                correlation_id=event.correlation_id,
                metadata={
                    "event_type": event.type.value,
                    "consequence": c.name,
                    "result_ref": result_ref,
                    "event_id": event.event_id,
                },
            )
        except Exception as audit_exc:
            logger.warning(
                "[CASE_EVOLUTION] audit upis neuspešan (non-fatal) event=%s posledica=%s: %s",
                event.event_id[:8], c.name, audit_exc,
            )
    # Complete: every consequence in the registry for this event type ended
    # 'completed' (any exception above already propagated before this
    # point) — the case is left in a fully consistent, verified state.
