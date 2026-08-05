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

Sprint 001 wired ONE event (DOCUMENT_ACCEPTED). Sprint 002 ("Canonical
Event Migration I", 2026-08-05) migrates 4 more onto this SAME dispatcher:
REVIEW_ACCEPTED, REVIEW_REJECTED, NEW_CLIENT_LINKED, NEW_EVIDENCE_
REGISTERED — each replacing a direct, in-process, fire-and-forget call
(genome/timeline/audit/conflict-check/evidence-classify) that used to be a
scattered "what happens next" decision made independently by
routers/smart_intake.py. 3 event types remain deliberately left with an
empty consequence list (DOCUMENT_MODIFIED, CONFIDENCE_DROPPED, MANUAL_
CORRECTION_APPLIED — no proven consequence gap yet); see
CASE_EVOLUTION_REGISTRY.md for each one's own reasoning. Never invented
speculative consequences for an event with no proven need yet.
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
    result_ref) or raises/returns nothing (failure, propagated).

    Program Delta, Sprint 002 (2026-08-05): reused UNCHANGED for
    REVIEW_ACCEPTED too (a confirmed correction to an already-assimilated
    document is, conceptually, the same "new confirmed information entered
    the case" shape as a document being accepted) — an explicit
    `event.payload["timeline_opis"]` overrides the default document-
    acceptance wording so the Timeline entry reads correctly for whichever
    event triggered it, without a second insert function."""
    predmet_id = event.predmet_id
    uid = event.user_id
    if not predmet_id:
        return "skipped_no_predmet_id"

    payload = event.payload or {}
    opis_override = payload.get("timeline_opis")
    if opis_override:
        opis = opis_override
    else:
        dokumenti = payload.get("dokumenti") or []
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


# ─── Consequence executors — REVIEW_ACCEPTED / REVIEW_REJECTED (Sprint 002) ──

async def _consequence_review_confirmation_audit(event: Event) -> str:
    """Domain-specific audit row for a confirmed human review — MIGRATES
    what used to be a direct, in-process `asyncio.create_task(log_action(
    "dokument_review_resolved", ...))` fire-and-forget call inside
    routers/smart_intake.py::resolve_job_review into this canonical flow.
    Distinct from the generic 'case_evolution_consequence_completed' row
    handle_case_changed already writes after every consequence — this one
    carries the intake-domain-specific metadata (prior_status,
    job_status_advanced, review_resolved_now) that a review-audit consumer
    actually needs, not just 'a consequence ran'. Verification: log_action
    itself either succeeds or raises (shared/audit_immutable.py's own
    established contract) — no separate before/after check needed, unlike
    genome_refresh's self-swallowing target function."""
    payload = event.payload or {}
    from shared.audit_immutable import log_action
    await log_action(
        "dokument_review_resolved",
        user_id=event.user_id,
        resource_type="intake_job",
        resource_id=payload.get("intake_job_id"),
        correlation_id=event.correlation_id,
        metadata={
            "prior_status": payload.get("prior_status"),
            "job_status_advanced": payload.get("job_status_advanced"),
            "review_resolved_now": payload.get("review_resolved_now"),
        },
    )
    return f"audit_logged:{payload.get('intake_job_id', '')}"


async def _consequence_review_rejection_audit(event: Event) -> str:
    """REVIEW_REJECTED's own canonical audit consequence — mirrors
    _consequence_review_confirmation_audit's shape for the mutually-
    exclusive alternate outcome. Deliberately the ONLY consequence
    registered for REVIEW_REJECTED (see CASE_EVOLUTION_REGISTRY.md for the
    full "šta se poništava / šta ostaje / šta se replanira" definition) —
    no genome_refresh, no timeline_entry, because a rejection means nothing
    was ever applied to the case in the first place (intake_jobs.status
    never reaches 'completed', migration 097), so there is nothing for
    Genome or Timeline to reflect."""
    payload = event.payload or {}
    from shared.audit_immutable import log_action
    await log_action(
        "dokument_review_rejected",
        user_id=event.user_id,
        resource_type="intake_job",
        resource_id=payload.get("intake_job_id"),
        correlation_id=event.correlation_id,
        metadata={
            "review_resolved_now": payload.get("review_resolved_now"),
            "job_status_rejected": payload.get("job_status_rejected"),
        },
    )
    return f"audit_logged:{payload.get('intake_job_id', '')}"


# ─── Consequence executor — NEW_CLIENT_LINKED (Sprint 002) ───────────────────

async def _consequence_conflict_check(event: Event) -> str:
    """MIGRATES what used to be a direct, in-process
    `asyncio.create_task(_conflict_check_bg())` call inside
    routers/smart_intake.py::finalize_intake_job — reuses
    routers/intake.py::_run_conflict_check and shared/proactive_alerts.py::
    create_proactive_alert UNCHANGED (this sprint is explicitly forbidden
    from modifying Genome/Alert *capability* — this is the same conflict
    check, just no longer a fire-and-forget call with no retry on failure).
    A genuine reliability improvement over the code it replaces: the old
    in-process task silently dropped a failure forever (logged, never
    retried); this executor's exception propagates to the canonical
    dispatcher, which marks the consequence 'failed' and lets the Event
    Bus's own proven retry/dead-letter mechanism take over — bounded
    (MAX_DISPATCH_ATTEMPTS=5), not silent."""
    payload = event.payload or {}
    klijent_ime = payload.get("klijent_ime") or ""
    protivna_strana = payload.get("protivna_strana") or ""
    if not klijent_ime:
        return "skipped_no_klijent_ime"

    from routers.intake import _run_conflict_check
    result = await _run_conflict_check(event.user_id, klijent_ime, "", protivna_strana, "")
    if not result.get("conflict_detected"):
        return "no_conflict"

    opisi = "; ".join(c.get("opis", "") for c in result.get("conflicts", [])[:5])
    supa = _get_supa()
    from shared.proactive_alerts import create_proactive_alert
    ok = await create_proactive_alert(
        supa,
        user_id=event.user_id,
        predmet_id=event.predmet_id,
        tip="sukob_interesa",
        naslov="BLOKIRAJUĆI sukob interesa" if result.get("has_blocker") else "Mogući sukob interesa",
        opis=f"{result.get('preporuka', '')} {opisi}".strip()[:2000],
        urgentnost="hitna" if result.get("has_blocker") else "normalna",
        retry_internally=False,
    )
    if not ok:
        raise RuntimeError(f"conflict_check: proactive_alert insert nije uspeo za predmet={event.predmet_id}")
    return "conflict_alert_created"


# ─── Consequence executor — NEW_EVIDENCE_REGISTERED (Sprint 002) ─────────────

async def _consequence_evidence_classify(event: Event) -> str:
    """MIGRATES what used to be a direct, in-process
    `asyncio.create_task(asyncio.to_thread(klasifikuj_i_sacuvaj, ...))` call
    inside routers/smart_intake.py::finalize_intake_job — reuses
    routers/evidence.py::klasifikuj_i_sacuvaj UNCHANGED. Deliberately does
    NOT carry the document's extracted text in the event payload (would
    duplicate a potentially ~100KB blob into the durable outbox for every
    document) — re-reads `tekst_sadrzaj` from the SAME predmet_dokumenti
    row this event's own dokument_id already points to, the row finalize
    just inserted moments before emitting this event. Verifies via
    `klasifikovan_at`, not "no exception" — klasifikuj_i_sacuvaj's own
    outer try/except (routers/evidence.py) logs internal failures but does
    not always re-raise, the same self-report gap genome_refresh's own
    verification exists to close."""
    payload = event.payload or {}
    dokument_id = payload.get("dokument_id")
    if not dokument_id:
        return "skipped_no_dokument_id"

    supa = _get_supa()
    before_res = await asyncio.to_thread(
        lambda: supa.table("predmet_dokumenti")
            .select("naziv_fajla,tekst_sadrzaj,klasifikovan_at")
            .eq("id", dokument_id).maybe_single().execute()
    )
    before_data = before_res.data if before_res else None
    if not before_data:
        return "skipped_document_not_found"
    tekst = before_data.get("tekst_sadrzaj")
    if not tekst:
        return "skipped_no_tekst_sadrzaj"

    naziv = payload.get("naziv") or before_data.get("naziv_fajla") or "dokument"
    from routers.evidence import klasifikuj_i_sacuvaj
    await asyncio.to_thread(klasifikuj_i_sacuvaj, event.predmet_id, dokument_id, naziv, tekst, event.user_id)

    after_res = await asyncio.to_thread(
        lambda: supa.table("predmet_dokumenti").select("klasifikovan_at").eq("id", dokument_id).maybe_single().execute()
    )
    after_data = after_res.data if after_res else None
    if not after_data or not after_data.get("klasifikovan_at"):
        raise RuntimeError(f"evidence_classification verifikacija neuspešna za dokument={dokument_id}: klasifikovan_at i dalje prazan")
    return str(dokument_id)


# ─── Canonical consequence registry ──────────────────────────────────────────
# Program Delta, Sprint 001, Task 1's own explicit instruction: prove ONE
# entry point exists for every event that changes a predmet's state, do not
# implement all of them. Sprint 002 ("Canonical Event Migration I") migrates
# 4 more: REVIEW_ACCEPTED, REVIEW_REJECTED, NEW_CLIENT_LINKED,
# NEW_EVIDENCE_REGISTERED — see CASE_EVOLUTION_REGISTRY.md for the full
# per-event reasoning (owner/input/consequences/idempotency/audit/retry/
# rollback/success-criterion) required by Task 4, including the 3 event
# types still deliberately left empty (DOCUMENT_MODIFIED, CONFIDENCE_
# DROPPED, MANUAL_CORRECTION_APPLIED — no proven consequence gap yet).

CONSEQUENCE_REGISTRY: dict[EventType, list[ConsequenceDef]] = {
    EventType.DOCUMENT_ACCEPTED: [
        ConsequenceDef(name="genome_refresh", executor=_consequence_genome_refresh),
        ConsequenceDef(name="timeline_entry", executor=_consequence_timeline_entry),
    ],
    EventType.REVIEW_ACCEPTED: [
        # Reuses DOCUMENT_ACCEPTED's own genome_refresh/timeline_entry
        # executors UNCHANGED — both already no-op gracefully
        # ("skipped_no_predmet_id") when this review was resolved BEFORE
        # the job's first finalize (the common case, no case exists yet to
        # refresh/record against). Only a POST-finalize correction (the
        # job's predmet_id already set) makes these do real work — exactly
        # the founder's own worked example ("Review Accepted → Genome →
        # Timeline → Audit").
        ConsequenceDef(name="genome_refresh", executor=_consequence_genome_refresh),
        ConsequenceDef(name="timeline_entry", executor=_consequence_timeline_entry),
        ConsequenceDef(name="review_confirmation_audit", executor=_consequence_review_confirmation_audit),
    ],
    EventType.REVIEW_REJECTED: [
        # Deliberately ONLY an audit consequence — see
        # _consequence_review_rejection_audit's own docstring for why no
        # genome_refresh/timeline_entry is registered here.
        ConsequenceDef(name="review_rejection_audit", executor=_consequence_review_rejection_audit),
    ],
    EventType.NEW_CLIENT_LINKED: [
        ConsequenceDef(name="conflict_check", executor=_consequence_conflict_check),
    ],
    EventType.NEW_EVIDENCE_REGISTERED: [
        ConsequenceDef(name="evidence_classification", executor=_consequence_evidence_classify),
    ],
    EventType.ROCISTE_ZAKAZANO: [
        # Reuses DOCUMENT_ACCEPTED's own genome_refresh executor UNCHANGED —
        # a new hearing changes tactical context the same way a new
        # document does, from Genome's own perspective (it just recomputes).
        # No timeline_entry here: routers/rocista.py never produced one for
        # hearing creation before this sprint, so none is invented now.
        ConsequenceDef(name="genome_refresh", executor=_consequence_genome_refresh),
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
