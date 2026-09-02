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

Program Omega, Sprint 002 (2026-08-06) — "Case Intelligence Aggregation
Engine". Adds ONE more event (DOCUMENT_BATCH_COMPLETED) and its own
canonical entry point, `refresh_case_intelligence()`, which is what
resolves Program Omega Sprint 001's own named, deferred `OMEGA-001`: a
batch of N documents finalized into the SAME case now produces ONE
case-level Genome refresh + intelligence summary, not N redundant ones.
`refresh_case_intelligence` is still just another consequence executor,
dispatched through the SAME `handle_case_changed` loop as every other one
— no second orchestrator, no bypass.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from services.event_bus import Event, EventType
from shared.attention_priority import CANONICAL_TO_NOTIFICATIONS
from shared.contradiction_identity import contradiction_dedupe_key, normalize_tezina
from shared.contradiction_identity import nove_kontradikcije_za_briefing
from shared.deps import _get_supa
from shared import rokovi as _IZVOR  # migracija 127 — kanonske vrednosti `izvor`

logger = logging.getLogger("vindex.case_evolution")


class ConsequenceClaimPending(RuntimeError):
    """Program Lambda, Certification 005 (2026-08-07): raised by
    handle_case_changed when a consequence is claimed by someone else but
    not YET stale enough to reclaim (_CONSEQUENCE_STALE_PENDING_SECONDS,
    300s) -- a "come back later" signal, categorically different from a
    genuine executor failure (which uses a bare exception + _mark_failed).

    Why this needs its own type, not a bare RuntimeError: services/
    event_bus.py's own dispatch_pending_events() clears the OUTER event's
    claimed_at immediately on ANY handler exception, specifically so a
    genuinely-broken handler retries fast (~3s, the DispatchLoop's own poll
    cadence) instead of waiting out the outer claim's own staleness window
    -- correct for that case, but fatal here: with MAX_DISPATCH_ATTEMPTS=5
    at a 3s cadence, that is only ~15-18s of total retry budget, nowhere
    near enough to ever reach this 300s inner threshold -- every retry
    would immediately re-fail the same way, and the event would be
    DEAD-LETTERED long before the legitimately-in-flight (or crashed)
    consequence could ever become reclaimable. event_bus.py checks for
    this exact type and leaves claimed_at untouched instead, so the retry
    cadence is governed by the OUTER claim's own staleness window (120s)
    -- comfortably reaching 300s within MAX_DISPATCH_ATTEMPTS."""


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


_CONSEQUENCE_STALE_PENDING_SECONDS = 300  # same threshold as shared/intake_queue.py::reap_stale_jobs's own default -- reused, not re-guessed, for the identical "claimed but never completed" problem shape


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_seconds_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


async def _try_claim_consequence(event_id: str, name: str) -> bool:
    """Atomically claims (event_id, name) for execution. Returns True if
    THIS call won the claim (caller should proceed to execute), False if it
    should skip (already completed, or another caller currently holds a
    live claim).

    Program Lambda, Certification 003's own LAMBDA003-EVT-001 (re-confirmed
    and given a broader real-world blast radius by Certification 004's own
    Distributed Systems Engineer fork -- 5 of 9 consequence executors would
    produce a visible duplicate row under this exact race): the previous
    `_get_consequence_status` (read) then `_mark_pending` (upsert, which
    does NOT fail or block on an existing row -- it just overwrites) was a
    genuine TOCTOU race. Two calls could both pass the read-check before
    either wrote 'pending', and both then execute the consequence.

    Fix, in 2 steps, each itself atomic at the single-row level (Postgres's
    own row-level locking is the real mutual-exclusion mechanism, not
    application logic):
      1. A fresh INSERT with `ignore_duplicates=True` (PostgREST's
         `INSERT ... ON CONFLICT (event_id, consequence_name) DO NOTHING`,
         backed by the table's own existing `UNIQUE(event_id,
         consequence_name)` constraint, migration 096 -- no new migration
         needed). Returns the inserted row ONLY if there was no conflict;
         wins the claim outright for the common "never attempted before"
         case.
      2. On conflict, read the existing row. 'completed' -> already done,
         don't reclaim. 'failed' -> a conditional `UPDATE ... WHERE
         status='failed'` reclaims it unconditionally (a genuinely
         terminal state; Postgres guarantees at most one concurrent
         UPDATE with that WHERE clause matches, since the first to commit
         changes status away from 'failed'). 'pending' -> reclaimed ONLY
         if `updated_at` is older than `_CONSEQUENCE_STALE_PENDING_SECONDS`
         -- see below for why this can't be unconditional.

    An earlier version of this fix reclaimed 'pending' unconditionally too
    (reasoning: `handle_case_changed` is only re-entered when the OUTER
    Event Bus dispatch already decided a retry is needed, so treating
    'pending' as reclaimable seemed to just extend that same trust). A
    regression test written immediately after
    (test_try_claim_consequence_second_attempt_on_still_pending_row_loses)
    proved this WRONG: reclaiming 'pending' by writing status='pending'
    again is a self-referential transition -- the WHERE clause
    `status='pending'` remains satisfied by the row's own post-reclaim
    state, so a SECOND concurrent caller's identical reclaim attempt would
    ALSO match and ALSO win, reproducing the exact race this function
    exists to close. The staleness gate (reusing `reap_stale_jobs`'s own
    already-shipped 300s threshold for the identical "claimed but never
    finished" problem shape, not a newly-guessed number) fixes this: a
    reclaim's own `WHERE updated_at < cutoff` becomes false the instant one
    caller's reclaim commits (it stamps a fresh `updated_at`), so a second,
    near-simultaneous caller's identical query no longer matches.
    """
    supa = _get_supa()

    ins = await asyncio.to_thread(
        lambda: supa.table("case_evolution_consequences")
            .upsert(
                {"event_id": event_id, "consequence_name": name, "status": "pending", "error": None},
                on_conflict="event_id,consequence_name",
                ignore_duplicates=True,
            )
            .execute()
    )
    if ins.data:
        return True

    existing = await _get_consequence_status(event_id, name)
    if not existing or existing.get("status") == "completed":
        return False

    prior_status = existing.get("status")  # "failed" or "pending"
    now_iso = _now_iso()

    if prior_status == "failed":
        upd = await asyncio.to_thread(
            lambda: supa.table("case_evolution_consequences")
                .update({"status": "pending", "error": None, "updated_at": now_iso})
                .eq("event_id", event_id).eq("consequence_name", name).eq("status", "failed")
                .execute()
        )
        return bool(upd.data)

    # prior_status == "pending" -- only reclaim if stale.
    cutoff_iso = _iso_seconds_ago(_CONSEQUENCE_STALE_PENDING_SECONDS)
    upd = await asyncio.to_thread(
        lambda: supa.table("case_evolution_consequences")
            .update({"status": "pending", "error": None, "updated_at": now_iso})
            .eq("event_id", event_id).eq("consequence_name", name).eq("status", "pending")
            .lt("updated_at", cutoff_iso)
            .execute()
    )
    return bool(upd.data)


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

async def _prethodne_kontradikcije(supa, predmet_id: str, after_verzija) -> Optional[list]:
    """Kontradikcije iz PRETHODNE verzije Genome-a, ili `None`.

    `None` znači „nema sa čim porediti" (prvi Genome predmeta, ili verzija nije
    poznata) — a ne „nema kontradikcija". Ta razlika je bitna: prazna lista bi
    značila da je sve nestalo."""
    if after_verzija is None:
        return None
    try:
        res = await asyncio.to_thread(
            lambda: supa.table("predmet_genome_history").select("genome_data,verzija")
                .eq("predmet_id", predmet_id).lt("verzija", after_verzija)
                .order("verzija", desc=True).limit(1).execute()
        )
    except Exception as exc:                                # noqa: BLE001
        # Pad čitanja istorije NE sme da se predstavi kao „ništa se nije promenilo".
        # Vraća se `None`, pa pozivalac ide starim putem i to je vidljivo u logu.
        logger.warning("[CASE_EVOLUTION] istorija Genome-a nečitljiva predmet=%s: %s", predmet_id, exc)
        return None
    red = (res.data or [None])[0]
    if not isinstance(red, dict):
        return None
    return (red.get("genome_data") or {}).get("kontradikcije") or []


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

    # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-011 remainder): a crash-then-reclaim
    # within _CONSEQUENCE_STALE_PENDING_SECONDS (the executor ran and _do_genome_refresh
    # already wrote a new predmet_genome_history row + bumped verzija, but the process
    # died before _mark_completed) used to re-trigger a full 2nd GPT recompute on
    # reclaim -- wasted cost, and since GPT output isn't deterministic, a real risk of 2
    # DIFFERENT genome results for what was conceptually one trigger. _do_genome_refresh
    # (routers/case_dna.py::_save_genome_history) already writes trigger_event on every
    # successful refresh -- reused as the dedup key, but scoped to THIS event's own
    # event_id (not the old hardcoded, shared-across-all-callers literal) so 2 genuinely
    # DIFFERENT events for the same predmet within the same window (e.g. a document
    # accepted, then separately a hearing scheduled) are never conflated -- only a
    # reclaim of the SAME event_id is treated as a duplicate. static/vindex.js's genome
    # history renderer maps the "case_evolution:" prefix to a friendly label, same
    # pattern already used there for 'upload_trigger'/'manual_refresh'.
    _trigger = f"case_evolution:{event.event_id}"
    _dup_g = await asyncio.to_thread(
        lambda: supa.table("predmet_genome_history").select("verzija")
            .eq("predmet_id", predmet_id).eq("trigger_event", _trigger)
            .gte("created_at", _iso_seconds_ago(_CONSEQUENCE_STALE_PENDING_SECONDS))
            .order("created_at", desc=True).limit(1).execute()
    )
    if _dup_g.data:
        return f"skipped_duplicate_refresh_v{_dup_g.data[0].get('verzija')}"

    before_res = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("case_dna").eq("id", predmet_id).maybe_single().execute()
    )
    before_data = before_res.data if before_res else None
    before_verzija = (before_data or {}).get("case_dna", {}).get("verzija") if before_data else None

    from routers.case_dna import _run_genome_background
    # A016.7 §6: `event_id` se prosledjuje EKSPLICITNO. Do sada je putovao samo
    # ukalupljen u `_trigger` string (`case_evolution:<event_id>`), sto je bilo
    # nusproizvod dedup logike -- citati ga natrag iz stringa bilo bi parsiranje
    # tudjeg formata, ne ugovor.
    await _run_genome_background(predmet_id, uid, before_verzija, trigger=_trigger,
                                 event_id=event.event_id)

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

    # Program Phoenix, Mission 007 (LIVINGSYS-DEBT-011): this executor had no inner
    # idempotency guard beneath the outer claim -- a crash-then-reclaim within the SAME
    # _CONSEQUENCE_STALE_PENDING_SECONDS window this module already reclaims on (the
    # executor ran and inserted successfully, but the process died before _mark_completed)
    # caused a genuine duplicate, user-visible Timeline row on reclaim. predmet_hronologija
    # has no event_id/correlation_id column (would need a migration) -- reusing the same
    # "identical content, recent window" idempotency shape already proven for
    # LIVINGSYS-DEBT-043 (routers/rocista.py) instead: an identical (predmet_id, dogadjaj)
    # row inserted within the same reclaim window is treated as the already-applied result
    # of an earlier attempt, not a new event.
    _dup_r = await asyncio.to_thread(
        lambda: supa.table("predmet_hronologija").select("id")
            .eq("predmet_id", predmet_id).eq("dogadjaj", opis)
            .gte("created_at", _iso_seconds_ago(_CONSEQUENCE_STALE_PENDING_SECONDS))
            .limit(1).execute()
    )
    if _dup_r.data:
        return str(_dup_r.data[0]["id"])

    res = await asyncio.to_thread(
        lambda: supa.table("predmet_hronologija").insert({
            "predmet_id": predmet_id,
            "user_id":    uid,
            "dogadjaj":   opis,
            "vaznost":    "informativan",
            "akter":      "Case Evolution Engine",
            # migracija 127 — W-EVOLUTION: posledica dogadjaja na sabirnici,
            # nije opazanje.
            "izvor":      _IZVOR.IZVOR_SYSTEM,
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
    genome_refresh's self-swallowing target function.

    Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-011 remainder): a crash-then-
    reclaim within _CONSEQUENCE_STALE_PENDING_SECONDS (log_action succeeded but
    the process died before _mark_completed) used to append a 2nd, misleading
    "review resolved" audit row for the same job. Appending is always safe for
    an immutable hash-chained log (skipping never touches a prior entry), so a
    plain recent-match check before the insert is enough -- no chain-integrity
    concern, unlike deleting/editing would be."""
    payload = event.payload or {}
    job_id = payload.get("intake_job_id")
    from shared.audit_immutable import log_action
    supa = _get_supa()
    _dup_a = await asyncio.to_thread(
        lambda: supa.table("audit_immutable").select("id")
            .eq("action", "dokument_review_resolved").eq("resource_id", job_id)
            .gte("created_at", _iso_seconds_ago(_CONSEQUENCE_STALE_PENDING_SECONDS))
            .limit(1).execute()
    )
    if _dup_a.data:
        return f"skipped_duplicate_audit:{job_id or ''}"
    await log_action(
        "dokument_review_resolved",
        user_id=event.user_id,
        resource_type="intake_job",
        resource_id=job_id,
        correlation_id=event.correlation_id,
        metadata={
            "prior_status": payload.get("prior_status"),
            "job_status_advanced": payload.get("job_status_advanced"),
            "review_resolved_now": payload.get("review_resolved_now"),
        },
    )
    return f"audit_logged:{job_id or ''}"


async def _consequence_review_rejection_audit(event: Event) -> str:
    """REVIEW_REJECTED's own canonical audit consequence — mirrors
    _consequence_review_confirmation_audit's shape for the mutually-
    exclusive alternate outcome. Deliberately the ONLY consequence
    registered for REVIEW_REJECTED (see CASE_EVOLUTION_REGISTRY.md for the
    full "šta se poništava / šta ostaje / šta se replanira" definition) —
    no genome_refresh, no timeline_entry, because a rejection means nothing
    was ever applied to the case in the first place (intake_jobs.status
    never reaches 'completed', migration 097), so there is nothing for
    Genome or Timeline to reflect.

    Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-011 remainder): same
    crash-then-reclaim duplicate-audit-row guard as
    _consequence_review_confirmation_audit above."""
    payload = event.payload or {}
    job_id = payload.get("intake_job_id")
    from shared.audit_immutable import log_action
    supa = _get_supa()
    _dup_a = await asyncio.to_thread(
        lambda: supa.table("audit_immutable").select("id")
            .eq("action", "dokument_review_rejected").eq("resource_id", job_id)
            .gte("created_at", _iso_seconds_ago(_CONSEQUENCE_STALE_PENDING_SECONDS))
            .limit(1).execute()
    )
    if _dup_a.data:
        return f"skipped_duplicate_audit:{job_id or ''}"
    await log_action(
        "dokument_review_rejected",
        user_id=event.user_id,
        resource_type="intake_job",
        resource_id=job_id,
        correlation_id=event.correlation_id,
        metadata={
            "review_resolved_now": payload.get("review_resolved_now"),
            "job_status_rejected": payload.get("job_status_rejected"),
        },
    )
    return f"audit_logged:{job_id or ''}"


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

    from routers.intake import COI_CHECK_FAILED, COI_NO_CONFLICT, _run_conflict_check
    result = await _run_conflict_check(event.user_id, klijent_ime, "", protivna_strana, "")

    # N4-COI-001: neuspela provera NIJE "nema sukoba". Ranije je pao upit
    # zavrsavao ovde kao `no_conflict` i proaktivni alarm se nikad ne bi
    # kreirao -- tiho i trajno. Izuzetak ide kanonskom dispatcher-u, koji
    # posledicu oznaci 'failed' i prepusti je proverenom retry/dead-letter
    # mehanizmu Event Bus-a (MAX_DISPATCH_ATTEMPTS=5).
    if result.get("status_provere") == COI_CHECK_FAILED:
        raise RuntimeError(
            "Provera sukoba interesa nije izvršena (izvori: %s) — "
            "rezultat se ne sme tumačiti kao odsustvo sukoba."
            % ", ".join(result.get("izvori_neuspeh", []) or ["nepoznato"])
        )

    if result.get("status_provere") != COI_NO_CONFLICT and not result.get("conflict_detected"):
        raise RuntimeError(
            "Provera sukoba interesa vratila nepoznat status: %r"
            % result.get("status_provere")
        )

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

    # Operation Singular Intelligence, Mission 002 (Team 8, reproduced same bug class as
    # _consequence_refresh_case_actions's own concurrency gap): a redelivered/retried event
    # for the SAME dokument_id used to call klasifikuj_i_sacuvaj again unconditionally --
    # its own predmet_dokazi insert has no dedup key, so every retry appended a fresh set of
    # duplicate "kljucne_cinjenice" rows. klasifikovan_at is already this function's own
    # completion marker (read into before_data above, checked below instead of ignored) --
    # reusing it as the idempotency guard, no new column/table/algorithm.
    if before_data.get("klasifikovan_at"):
        return "skipped_already_classified"

    naziv = payload.get("naziv") or before_data.get("naziv_fajla") or "dokument"
    from routers.evidence import klasifikuj_i_sacuvaj
    _klas_rezultat = await asyncio.to_thread(klasifikuj_i_sacuvaj, event.predmet_id, dokument_id, naziv, tekst, event.user_id)

    after_res = await asyncio.to_thread(
        lambda: supa.table("predmet_dokumenti").select("klasifikovan_at").eq("id", dokument_id).maybe_single().execute()
    )
    after_data = after_res.data if after_res else None
    if not after_data or not after_data.get("klasifikovan_at"):
        raise RuntimeError(f"evidence_classification verifikacija neuspešna za dokument={dokument_id}: klasifikovan_at i dalje prazan")

    # Program Phoenix, Mission 006 (LIVINGSYS-DEBT-009): klasifikovan_at above only proves a
    # ROW was written, not that the classification itself succeeded -- klasifikuj_i_sacuvaj's
    # own GPT-failure fallback ALSO stamps klasifikovan_at (a real, valid "ostalo" fallback
    # value gets persisted either way). Its own ai_tags now carries an explicit failure flag
    # (Mission 006's own fix to routers/evidence.py) -- logged here so a genuine AI failure on
    # this, the most frequent event-driven classification path, is never silently
    # indistinguishable from a real "ostalo" classification, matching this function's own
    # "verify, don't just no-exception" standard for the completion marker above.
    if isinstance(_klas_rezultat, dict) and _klas_rezultat.get("ai_tags", {}).get("_klasifikacija_greska"):
        logger.warning(
            "[CASE_EVOLUTION] evidence_classification: AI klasifikacija neuspešna za dokument=%s (fallback 'ostalo' upisan)",
            dokument_id,
        )
    return str(dokument_id)


# ─── Case Intelligence Aggregation Engine (Program Omega, Sprint 002) ────────
#
# Split into TWO independently-resumable consequences (genome_refresh reused
# UNCHANGED from DOCUMENT_ACCEPTED, plus a NEW case_intelligence_summary
# step) rather than one monolithic function, for the exact same reason
# DOCUMENT_ACCEPTED itself is split: if a crash happens after Genome
# completes but before the summary is written, a retry must NOT re-run the
# (expensive, GPT-based) Genome recompute — it should resume with only the
# summary step, matching the mission's own Scenario 4 requirement
# ("nastavlja gde je stalo", not "restarts everything"). The "before" Genome
# snapshot (kontradikcije/datumi_kljucni counts, needed for the summary's
# own diff) is captured by the EMITTER (routers/smart_intake.py::
# finalize_intake_jobs_batch) before genome_refresh ever runs, and travels
# in the event's own durable payload — so it survives a crash/retry
# perfectly, unlike a value read mid-consequence.

async def _consequence_case_intelligence_summary(event: Event) -> str:
    """THE canonical entry point Program Omega Sprint 002's own charter
    names as `refresh_case_intelligence(case_id, reason)` — the SECOND half
    of the pair (genome_refresh, reused unchanged from DOCUMENT_ACCEPTED,
    is the first; the Event Bus's own sequential per-consequence loop in
    `handle_case_changed` guarantees it already completed before this one
    starts, within this same event dispatch). Answers the mission's own 4
    questions:

    - "Ko je vlasnik trenutnog stanja predmeta?" -- Case Genome
      (predmeti.case_dna) remains the single source of truth; this function
      only READS it (already refreshed by the prior consequence) and
      records what changed.
    - "Kada se Genome osvežava?" -- by the sibling `genome_refresh`
      consequence, triggered by a durable DOCUMENT_BATCH_COMPLETED event
      itself only emitted AFTER an entire finalize-batch operation's
      document-linking work is done (never mid-batch).
    - "Ko odlučuje da li je refresh potreban?" -- the EMITTER
      (`finalize_intake_jobs_batch`) decides at emission time (only emits
      for predmet_ids that actually got 1+ documents linked); this function
      itself additionally refuses to summarize with zero new documents, as
      a second, independent guard.
    - "Kako znamo da je rezultat zasnovan na kompletnim podacima?" -- every
      number here is either read fresh from the DB (Genome's own
      `case_dna`, `predmet_dokazi`/`predmet_dokumenti`/`rocista` via the
      SAME canonical `calculate_procesni_rizik`/`identify_case_problems`
      Core Consolidation already established as the platform's one
      algorithm for this question) or carried verbatim from the emitter's
      own already-verified finalize results (`dokumenti_za_proveru`,
      `rokovi_dodati`) — never invented, and persisted durably (migration
      098, `case_intelligence_summaries`) so it stays inspectable after the
      fact (Agent 3's own "no conclusion without source" rule)."""
    payload = event.payload or {}
    predmet_id = event.predmet_id
    uid = event.user_id
    if not predmet_id:
        return "skipped_no_predmet_id"

    dokumenata_dodato = int(payload.get("dokumenata_dodato") or 0)
    if dokumenata_dodato <= 0:
        return "skipped_no_new_documents"

    supa = _get_supa()

    # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-011 remainder): a crash-then-
    # reclaim within _CONSEQUENCE_STALE_PENDING_SECONDS used to insert a 2nd
    # summary row for the same batch. The row already carries this exact
    # event's own event_id (below) -- an exact match is a more precise dedup
    # key than a recent-window heuristic and needs no migration (no new
    # UNIQUE constraint), just an application-level check-before-insert.
    _dup_s = await asyncio.to_thread(
        lambda: supa.table("case_intelligence_summaries").select("id")
            .eq("event_id", event.event_id).limit(1).execute()
    )
    if _dup_s.data:
        return str(_dup_s.data[0]["id"])

    after_res = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("case_dna,tip").eq("id", predmet_id).maybe_single().execute()
    )
    after_data = (after_res.data if after_res else None) or {}
    after_dna = after_data.get("case_dna") or {}
    after_verzija = after_dna.get("verzija")

    before_kontradikcije = int(payload.get("pre_kontradikcije") or 0)
    before_dogadjaji = int(payload.get("pre_dogadjaji") or 0)
    kontradikcije_posle = after_dna.get("kontradikcije") or []
    dogadjaji_posle = after_dna.get("datumi_kljucni") or []
    novi_dogadjaji = max(0, len(dogadjaji_posle) - before_dogadjaji)

    # ── A016.7 §9 (A016.1 C-2) ────────────────────────────────────────────────
    # Ranije: broj = `len(posle) - pre_broj`, a prikazane stavke = `posle[-broj:]`.
    # Dve nezavisne pretpostavke, obe netačne. Izmereno na 2 nestale + 3 nove:
    # razlika dužina daje 1, pa je briefing prikazivao JEDNU stavku (poslednju po
    # redosledu koji GPT ne garantuje), dok su dve nove ostajale nevidljive a
    # nestanak dve stare se nigde nije pominjao.
    #
    # `pre_kontradikcije` je samo BROJ, pa razlika ni ne može biti tačna. Prethodni
    # snimak se zato čita iz `predmet_genome_history.genome_data`, gde ceo Genome
    # već stoji — bez nove tabele i bez nove kolone.
    _prethodne = await _prethodne_kontradikcije(supa, predmet_id, after_verzija)
    nove_kontradikcije, _nove_stavke = nove_kontradikcije_za_briefing(
        _prethodne, kontradikcije_posle, before_kontradikcije)

    # Core Consolidation's own jedini algoritam za "šta nedostaje / koji su
    # rizici" -- isti kod koji routers/matter_intel.py već koristi, nikad
    # duplirano ovde (namerno NE Genome-ov sopstveni odvojen "nedostaje"/
    # "upozorenja" -- to bi vratilo tačno onu duplikaciju koju je Core
    # Consolidation uklonio 2026-07-22).
    from services.risk_engine import calculate_procesni_rizik, identify_case_problems
    from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS
    tip_predmeta = after_data.get("tip") or "ostalo"
    dokazi_r, dok_r, rok_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select("snaga,kategorija,pravni_element,izvor_snage").eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()),
        # Operation Singular Intelligence, Mission 002: tip_dokaza added -- Red Team's Attack 1
        # reproduced this exact caller (of calculate_procesni_rizik, missing the column every
        # sibling caller selects since the G-028 fix) computing "Srednji"/health=55/4 fabricated
        # missing-doc findings for the identical case data ccc.py/case_pipeline.py compute as
        # "Nizak"/health=70/[] for -- persisted into case_intelligence_summaries.
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("naziv_fajla,status,tip_dokaza").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select("sud,datum,status").eq("predmet_id", predmet_id).order("datum").execute()),
        return_exceptions=True,
    )
    dokazi = ((dokazi_r.data if not isinstance(dokazi_r, Exception) else []) or [])
    dok_data = ((dok_r.data if not isinstance(dok_r, Exception) else []) or [])
    rok_data = ((rok_r.data if not isinstance(rok_r, Exception) else []) or [])
    rizik = calculate_procesni_rizik(dokazi=dokazi, dokumenti=dok_data, rocista=rok_data, tip_predmeta=tip_predmeta, expected_docs=_EXPECTED_DOCS)
    problemi = identify_case_problems(rizik, tip_predmeta)
    rizici_ozbiljni = [p for p in problemi if p.get("ozbiljnost") in ("kritican", "vazan")]

    summary_row = {
        "predmet_id": predmet_id,
        "event_id": event.event_id,
        "reason": payload.get("reason") or "DOCUMENT_BATCH_COMPLETED",
        "correlation_id": event.correlation_id,
        "dokumenata_dodato": dokumenata_dodato,
        "novi_dokazi": dokumenata_dodato,  # svaki uspešno povezan dokument je i sam kandidat-dokaz (Evidence Vault klasifikacija radi po dokumentu, već sprovedena pre ovog koraka)
        "novi_dogadjaji": novi_dogadjaji,
        "kontradikcije_pronadjene": nove_kontradikcije,
        "rizici_koji_zahtevaju_paznju": len(rizici_ozbiljni),
        "novi_rokovi": int(payload.get("rokovi_dodati") or 0),
        "dokumenti_niska_sigurnost": int(payload.get("dokumenti_za_proveru") or 0),
        "genome_verzija_pre": payload.get("pre_verzija"),
        "genome_verzija_posle": after_verzija,
        "detalji": {
            "kontradikcije": _nove_stavke,
            "nedostajuci_dokazi": rizik.get("nedostajuci_dokazi") or [],
            "rizici": rizici_ozbiljni,
            "job_ids": payload.get("job_ids") or [],
        },
    }
    ins = await asyncio.to_thread(lambda: supa.table("case_intelligence_summaries").insert(summary_row).execute())
    summary_id = (ins.data or [{}])[0].get("id") if ins and ins.data else None

    try:
        from shared.audit_immutable import log_action
        await log_action(
            "case_intelligence_refreshed",
            user_id=uid, resource_type="predmet", resource_id=predmet_id,
            correlation_id=event.correlation_id,
            metadata={"summary_id": summary_id, **{k: v for k, v in summary_row.items() if k != "detalji"}},
        )
    except Exception as audit_exc:
        logger.warning("[CASE_EVOLUTION] case_intelligence_refreshed audit upis neuspešan (non-fatal) predmet=%s: %s", predmet_id, audit_exc)

    return str(summary_id) if summary_id else "completed_no_summary_id"


# ─── Canonical Action Engine (Program Omega, Sprint 003) ─────────────────────
#
# refresh_case_actions(case_id) -- the mission's own named canonical entry
# point. Implemented as ONE more consequence, appended to every event that
# already refreshes Genome (DOCUMENT_ACCEPTED, REVIEW_ACCEPTED, ROCISTE_
# ZAKAZANO, DOCUMENT_BATCH_COMPLETED) -- runs LAST, so it always reads
# freshly-refreshed facts. No new orchestrator, no direct calls: same
# Event → Canonical Handler → Consequence → Audit path as everything else.
#
# Deterministic, NEVER GPT: every rule below reads either
# services/risk_engine.py's own canonical `calculate_procesni_rizik`/
# `identify_case_problems` (Core Consolidation, 2026-07-22 — the ONE
# established algorithm for "what's wrong with this case", never
# duplicated) or a real DB row (rocista, case_dna.kontradikcije — the
# latter already required to carry a "DOK-XX str.Y" source location by
# Genome's own extraction prompt, unchanged). "Client not contacted in 45
# days" (the mission's own third worked example) is deliberately NOT
# implemented — no deterministic last-contact data source exists anywhere
# in the platform (checked, not assumed) — named honestly as `OMEGA-005`
# rather than approximated from an unrelated timestamp.

_ACTION_TYPES = (
    "PRIPREMITI_PODNESAK", "PRIBAVITI_DOKAZ", "RAZRESITI_KONTRADIKCIJU",
    "OJACATI_DOKAZE", "PLANIRATI_ROKOVE",
)


def _priority_by_days(days_until: int) -> str:
    if days_until <= 3:
        return "critical"
    if days_until <= 7:
        return "high"
    return "medium"


def _stable_key(*parts: str) -> str:
    import hashlib as _hashlib
    return _hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


async def _compute_target_actions(predmet_id: str) -> list[dict]:
    """Pure computation, no DB writes -- returns the FULL target set of
    actions that SHOULD be open right now, each already carrying its own
    dedupe_key/dokaz/prioritet. Separated from the reconciliation step
    below so it can be unit-tested on its own."""
    from datetime import date, datetime, timezone

    supa = _get_supa()
    pred_res = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("case_dna,tip").eq("id", predmet_id).maybe_single().execute()
    )
    pred_data = (pred_res.data if pred_res else None) or {}
    case_dna = pred_data.get("case_dna") or {}
    tip_predmeta = pred_data.get("tip") or "ostalo"

    dokazi_r, dok_r, rok_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select("snaga,kategorija,pravni_element,izvor_snage").eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()),
        # tip_dokaza included (unlike matter_intel.py's own read-only display
        # caller, G-028) -- this query feeds a STATEFUL, persisted action
        # ("Nedostaje X u spisu" -> PRIBAVITI_DOKAZ), so a permanently-empty
        # tip_dokaza would make that action a permanent false positive on
        # every case, violating Agent 4's "no conclusion without source" rule.
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("naziv_fajla,status,tip_dokaza").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("rocista").select("id,sud,datum,status").eq("predmet_id", predmet_id).order("datum").execute()),
        return_exceptions=True,
    )
    dokazi = ((dokazi_r.data if not isinstance(dokazi_r, Exception) else []) or [])
    dok_data = ((dok_r.data if not isinstance(dok_r, Exception) else []) or [])
    rok_data = ((rok_r.data if not isinstance(rok_r, Exception) else []) or [])

    from services.risk_engine import calculate_procesni_rizik, identify_case_problems
    from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS
    rizik = calculate_procesni_rizik(dokazi=dokazi, dokumenti=dok_data, rocista=rok_data, tip_predmeta=tip_predmeta, expected_docs=_EXPECTED_DOCS)
    problemi = identify_case_problems(rizik, tip_predmeta)

    actions: list[dict] = []
    today = date.today()

    # Rule 1 -- deadline (per rociste, sourced directly from `rocista`,
    # never a GPT guess). Mission's own worked example:
    # "Rok ističe za 5 dana -> Pripremiti podnesak".
    for r in rok_data:
        if r.get("status") != "zakazano":
            continue
        rok_datum_raw = r.get("datum")
        if not rok_datum_raw:
            continue
        try:
            rok_datum = datetime.fromisoformat(str(rok_datum_raw)[:10]).date()
        except ValueError:
            continue
        dani = (rok_datum - today).days
        # BLACKSWAN-CRIT-002 fix (Operation Black Swan, Mission 001, Scenario 15): was
        # `dani < 0 or dani > 30` -- an OVERDUE hearing (negative dani) got silently
        # dropped from the target set entirely, identical to "no deadline at all."
        # Reproduced: an open action for a hearing that passed while the lawyer was away
        # sits frozen showing stale "za N dana" text, then on the NEXT reconciliation
        # event (which treats "no longer in target set" as "resolved") gets silently
        # CLOSED -- a missed court date becoming indistinguishable from "handled." An
        # overdue rociste is only dropped from the target set once its own `status`
        # actually changes (rescheduled/held), never merely by the clock passing 0.
        if dani > 30:
            continue
        razlog = (
            f"Ročište ({r.get('sud') or 'sud'}) PROPUŠTENO pre {abs(dani)} dan(a) — {rok_datum.isoformat()}"
            if dani < 0 else
            f"Ročište ({r.get('sud') or 'sud'}) za {dani} dan(a) — {rok_datum.isoformat()}"
        )
        actions.append({
            "tip": "PRIPREMITI_PODNESAK",
            "razlog": razlog,
            "dokaz": {"rociste_id": r.get("id"), "sud": r.get("sud"), "datum": rok_datum.isoformat(), "dani_preostalo": dani},
            "prioritet": _priority_by_days(dani),
            "rok": rok_datum.isoformat(),
            "dedupe_key": _stable_key("rociste", str(r.get("id"))),
        })

    # Rule 2/4/5 -- Core Consolidation's own canonical problem list, mapped
    # to stable per-category keys (not per-count) so a changing count
    # UPDATES the existing action instead of closing+reopening it.
    #
    # Program Sigma, Master Sprint 003 (2026-08-06): the text->category
    # classification below now calls shared/gap_engine.py::classify_case_problem
    # -- the SAME classifier shared/gap_engine.py::gaps_from_case_problems
    # uses. Previously this cascade was duplicated, independently, in both
    # places (this function's own if/elif chain, and a near-identical one
    # this sprint's own new gap_engine.py first introduced) -- a real,
    # self-found violation of this program's own "no parallel algorithms"
    # principle, fixed the same sprint it was introduced rather than left as
    # a new debt item.
    from shared.gap_engine import classify_case_problem, GAP_TIP_KRITICAN_ROK
    for p in problemi:
        text = p.get("problem") or ""
        if not text:
            continue
        gap_tip = classify_case_problem(text)
        if gap_tip is None or gap_tip == GAP_TIP_KRITICAN_ROK:
            continue  # unrecognized text, or already covered per-rociste by Rule 1 above -- same silent-skip as before this refactor
        if gap_tip == "NEMA_DOKAZA":
            actions.append({
                "tip": "PRIBAVITI_DOKAZ", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text},
                "prioritet": "critical", "rok": None,
                "dedupe_key": _stable_key("problem", "nema_dokaza"),
            })
        elif gap_tip == "NEDOSTAJE_DOKUMENT":
            actions.append({
                "tip": "PRIBAVITI_DOKAZ", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text},
                "prioritet": "high", "rok": None,
                "dedupe_key": _stable_key("problem", "nedostaje", text),
            })
        elif gap_tip == "PREDSTOJECI_ROKOVI":
            actions.append({
                "tip": "PLANIRATI_ROKOVE", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text, "predstojeći_rokovi": rizik.get("predstojeći_rokovi")},
                "prioritet": "high", "rok": None,
                "dedupe_key": _stable_key("problem", "predstojeci_rokovi"),
            })
        elif gap_tip == "DOKAZI_SLABI":
            actions.append({
                "tip": "OJACATI_DOKAZE", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text},
                "prioritet": "informational", "rok": None,
                "dedupe_key": _stable_key("problem", "dokazi_slabi"),
            })

    # Rule 3 -- contradictions, sourced directly from Genome's own current
    # case_dna.kontradikcije (already required to carry a "DOK-XX str.Y"
    # source location by Genome's own extraction prompt).
    #
    # Program Sigma, Master Sprint 002 (2026-08-06) -- dedupe_key is now the
    # ONE shared contradiction identity (shared/contradiction_identity.py),
    # anchored on lokacija_1/lokacija_2 rather than the free-text `opis`.
    # FOUND AND FIXED this sprint: the previous `_stable_key("kontradikcija",
    # opis, loc1, loc2)` included GPT's own re-worded-every-refresh `opis` in
    # the hash -- any rephrasing of the IDENTICAL underlying contradiction
    # between 2 Genome refreshes changed the dedupe_key, so the reconcile
    # loop below (target-vs-existing diff) would close the old action and
    # create a new one: a live RAZRESITI_KONTRADIKCIJU action flickering
    # closed+reopened on every refresh even when nothing real changed. Same
    # root cause, same fix, as routers/case_dna.py::_compute_delta's own
    # SIGMA-002 (Sprint 001 Debt Register) -- one shared identity function,
    # not two independent patches.
    # A015 (2026-08-30) — V2 PROJEKCIJA IMA PREDNOST, BEZ MESANJA IDENTITETA.
    #
    # Ako predmet ima perzistirane V2 kontradikcije, Rule 3 projektuje ISKLJUCIVO
    # iz njih, sa kljucem izvedenim iz `predmet_contradictions.id`. Legacy grana
    # ispod se u tom slucaju uopste ne izvrsava.
    #
    # Zasto "ili-ili", a ne oboje: kada bi obe grane radile, ista sporna tacka bi
    # dobila DVE akcije sa dva razlicita kljuca (V2 i legacy), pa bi reconcile
    # video duplikat i advokat bi dobio isti nalaz dvaput. Pravilo iz mandata je
    # izricito -- legacy kontradikcija -> legacy projekcija, V2 -> V2 projekcija.
    #
    # Predmet bez tvrdnji (`predmet_dokazi = 0`) ne moze imati V2 kontradikciju
    # (A014 tamo pada zatvoreno), pa za njega ovo vraca praznu listu i legacy
    # putanja ostaje netaknuta -- sto je i uslov iz A015 §14.
    from services.v2_projection import v2_akcije_za_predmet
    _v2_akcije = await v2_akcije_za_predmet(supa, predmet_id)
    if _v2_akcije:
        actions.extend(_v2_akcije)
        return actions

    _TEZINA_PRIORITET = {"kriticna": "critical", "vazna": "high", "manja": "medium"}
    for k in (case_dna.get("kontradikcije") or []):
        opis = k.get("opis") or ""
        loc1 = k.get("lokacija_1") or ""
        loc2 = k.get("lokacija_2") or ""
        if not opis:
            continue
        # Operation Single Brain (2026-08-07): raw k.get("tezina") is a free-form GPT
        # classification -- normalize_tezina() validates it against the 3 values Genome's
        # own extraction prompt actually asks for, fail-safe toward "kriticna" for anything
        # unrecognized (see shared/contradiction_identity.py's docstring). Previously this
        # dict's own .get(..., "medium") default silently downgraded an out-of-enum tezina
        # to medium priority -- invisible under-flagging of a possibly-critical contradiction.
        _tez = normalize_tezina(k.get("tezina"))
        # A003 (2026-08-29) — ADITIVNA PROVENIJENCIJA DOKUMENTA.
        # A002 (routers/case_dna.py) je JEDINI vlasnik rezolucije `DOK-NN` ->
        # `predmet_dokumenti.id` i upisuje `dokument_id_1`/`dokument_id_2` u istu
        # kontradikciju, uparene sa `lokacija_1`/`lokacija_2` iz kojih su izvedene.
        # Ovde se ta vec-razresena vrednost SAMO PRENOSI dalje -- nikad ponovo ne
        # racuna: nema regexa, nema poklapanja po nazivu fajla, nema pozicije u
        # listi, nema `docs[0]`. Drugi resolver istog pojma je tacno ono sto ovaj
        # repo zabranjuje (jedan koncept = jedan vlasnik).
        #
        # `.get()` je namerno: Genome ekstrahovan PRE A002 nema ove kljuceve
        # (izmereno: 0/19 postojecih kontradikcija u produkciji ih ima), pa je
        # `None` ispravan ishod, a ne greska.
        #
        # FAIL-CLOSED, tri pravila koja NE SMEJU biti "popravljena":
        #   1. oba kljuca UVEK postoje -- `None` znaci "nije razreseno", dok bi
        #      izostavljen kljuc znacio "ova verzija ne podrzava provenijenciju";
        #   2. `dokument_id_1 == dokument_id_2` je VALIDNO, ne duplikat --
        #      intra-dokumentna kontradikcija (dva iskaza u istom dokumentu) je
        #      26% stvarnih slucajeva; deduplikacija bi obrisala drugu stranu;
        #   3. `lokacija_N` i `dokument_id_N` ostaju upareni -- zamena strana je
        #      korupcija provenijencije, iako je identitet kontradikcije
        #      (shared/contradiction_identity.py) namerno order-independent.
        #
        # `izvor_dokumenti`, `dedupe_key`, `lokacija_1/2` i identitet kontradikcije
        # ostaju NEPROMENJENI -- ovo je iskljucivo dodavanje dva polja u `dokaz`.
        actions.append({
            "tip": "RAZRESITI_KONTRADIKCIJU", "razlog": opis,
            "dokaz": {"opis": opis, "lokacija_1": loc1, "lokacija_2": loc2, "tezina": _tez,
                      "dokument_id_1": k.get("dokument_id_1"),
                      "dokument_id_2": k.get("dokument_id_2")},
            "prioritet": _TEZINA_PRIORITET[_tez], "rok": None,
            "dedupe_key": contradiction_dedupe_key(k),
            "izvor_dokumenti": [x for x in (loc1, loc2) if x],
        })

    return actions


async def _consequence_refresh_case_actions(event: Event) -> str:
    """THE canonical entry point Program Omega Sprint 003's own charter
    names `refresh_case_actions(case_id)`. Reconciles the CURRENT target
    action set (`_compute_target_actions`, pure/deterministic) against
    whatever is already open in `case_actions`:

    - A target action not yet open -> CREATED (`status='open'`).
    - An already-open action whose `dedupe_key` is still in the target set
      -> UPDATED in place (razlog/dokaz/prioritet/rok refreshed) --
      Scenario 3 ("rok produžen -> akcija se ažurira", not closed+reopened).
    - An already-open action whose `dedupe_key` is NO LONGER in the target
      set -> CLOSED (`status='closed', closed_at=now()`) -- Scenario 2
      ("nov dokaz uklanja rizik -> akcija se zatvara") and Scenario 4
      ("dokument obrisan -> zastarela akcija nestaje").

    Concurrency (Scenario 5): the partial UNIQUE index on
    `(predmet_id, dedupe_key) WHERE status='open'` (migration 099) is the
    real safety net for the CREATE path ONLY -- two concurrent refreshes
    racing to CREATE the same action both attempt the same upsert; the DB
    constraint, not application logic, guarantees exactly one open row per
    fact survives. This was previously mis-stated as covering all 3 paths;
    Operation Singular Intelligence Mission 002 (Team 8) reproduced, via an
    isolated simulation, that the UPDATE and CLOSE paths had NO equivalent
    protection -- two concurrent refreshes for the SAME predmet_id could
    interleave so a stale CLOSE overwrote a fresher UPDATE's decision to
    keep a row open. Both paths now carry optimistic-concurrency guards
    (`.eq("status","open")` on both; `.eq("updated_at", snapshot)` on CLOSE
    specifically) using only existing columns -- no migration, no new
    infrastructure. This narrows the race to "whichever caller's write
    reaches the DB last still wins" (a live, up-to-date write correctly
    surviving), rather than fully eliminating a stale write's ability to
    silently overwrite a fresher one under the old code. Full cross-worker
    serialization would need a session/transaction-scoped Postgres lock,
    which does not fit this client's per-call (not held-open-transaction)
    execution model without moving the reconcile into a stored procedure --
    named as debt, not attempted without live-DB verification."""
    predmet_id = event.predmet_id
    uid = event.user_id
    if not predmet_id:
        return "skipped_no_predmet_id"

    # Program Omega, Sprint 004 (2026-08-06): a real, computed ISO-8601
    # timestamp, not the string literal "now()" this function originally
    # used (a pattern copied from elsewhere in the codebase, e.g.
    # routers/evidence.py). Found during Sprint 004 because Workspace's own
    # "recently completed" bucket filters case_actions by `closed_at` with
    # `.gte()` -- Postgres's timestamptz input parser does not recognize the
    # literal string "now()" (with parentheses) as its documented "now"
    # special value, so a value written this way would have made every
    # closed action's own closed_at either reject the update outright or
    # store an unusable value, silently breaking that bucket. Fixed for
    # THIS function only -- the 9 other pre-existing "now()" call sites
    # elsewhere in the repo are unrelated, pre-existing code, unverified
    # and untouched here (out of this sprint's scope).
    from datetime import datetime as _dt, timezone as _tz
    _now_iso = _dt.now(_tz.utc).isoformat()

    supa = _get_supa()
    target = await _compute_target_actions(predmet_id)
    target_by_key = {a["dedupe_key"]: a for a in target}

    # Operation Singular Intelligence, Mission 002 (Team 8, Cross-Module Concurrency, reproduced
    # via isolated simulation): this snapshot-then-write sequence is NOT serialized per predmet_id
    # across concurrent event handlers (only the CREATE path below has a real DB-level safety net,
    # the partial UNIQUE index -- the docstring above only ever claimed that path was covered).
    # Two events for the SAME case racing (e.g. DOCUMENT_ACCEPTED + ROCISTE_ZAKAZANO dispatched to
    # different gunicorn workers within the same ~3s poll window) could previously interleave so a
    # stale CLOSE overwrote a fresher concurrent UPDATE's decision to keep the row open -- a real
    # lost update on the platform's own single source of truth for "what needs attention."
    #
    # A traditional Postgres advisory lock doesn't cleanly fit here: this client issues each
    # .execute() as its own PostgREST call, not one held-open transaction, so a lock acquired in
    # one call would already be released before the next call in this same function runs. Closing
    # this properly with a session/transaction-scoped lock would mean moving the whole reconcile
    # into a Postgres function (a real migration, needing the founder to run it and live-DB
    # verification neither of which is available here) -- named as SINGULAR2-DEBT (see
    # docs/singular2/ for the full spec), not attempted blind.
    #
    # What IS fixed here, with existing columns only, no migration: optimistic concurrency control.
    # `updated_at` is captured in the same snapshot read and threaded into both the UPDATE and
    # CLOSE calls' WHERE clause. If a concurrent, fresher call already touched the row since this
    # snapshot was taken, this call's write now matches ZERO rows (a safe no-op) instead of
    # silently overwriting the fresher decision -- whichever call actually reads the row's current
    # state last still wins, but neither can silently clobber the other's already-applied result.
    existing_res = await asyncio.to_thread(
        lambda: supa.table("case_actions").select("id,dedupe_key,updated_at").eq("predmet_id", predmet_id).eq("status", "open").execute()
    )
    existing_rows = (existing_res.data if existing_res else None) or []
    existing_by_key = {r["dedupe_key"]: {"id": r["id"], "updated_at": r.get("updated_at")} for r in existing_rows}

    created, updated, closed = 0, 0, 0

    for key, action in target_by_key.items():
        row = {
            "predmet_id": predmet_id,
            "tip": action["tip"],
            "razlog": action["razlog"][:2000],
            "dokaz": action["dokaz"],
            "prioritet": action["prioritet"],
            "rok": action.get("rok"),
            "dedupe_key": key,
            "izvor_dokumenti": action.get("izvor_dokumenti") or [],
            "event_id": event.event_id,
            "correlation_id": event.correlation_id,
        }
        if key in existing_by_key:
            _existing = existing_by_key[key]
            await asyncio.to_thread(
                lambda r=row, aid=_existing["id"]: supa.table("case_actions")
                    .update({**r, "updated_at": _now_iso}).eq("id", aid).eq("status", "open").execute()
            )
            updated += 1
        else:
            try:
                await asyncio.to_thread(lambda r=row: supa.table("case_actions").insert(r).execute())
                created += 1
            except Exception as _ins_exc:
                # Partial UNIQUE index violation -- another concurrent
                # refresh already created this exact action (Scenario 5).
                # Not an error: the fact now has exactly one open row,
                # which is the actual goal.
                if "duplicate key" not in str(_ins_exc).lower() and "unique" not in str(_ins_exc).lower():
                    raise
                logger.info("[CASE_EVOLUTION] case_action already created concurrently, skipping: predmet=%s key=%s", predmet_id, key)

    for key, existing in existing_by_key.items():
        if key not in target_by_key:
            _snapshot_updated_at = existing["updated_at"]
            _close_query = (
                supa.table("case_actions")
                    .update({"status": "closed", "closed_at": _now_iso, "updated_at": _now_iso})
                    .eq("id", existing["id"]).eq("status", "open")
            )
            if _snapshot_updated_at is not None:
                _close_query = _close_query.eq("updated_at", _snapshot_updated_at)
            await asyncio.to_thread(_close_query.execute)
            closed += 1

    try:
        from shared.audit_immutable import log_action
        await log_action(
            "case_action_refreshed",
            user_id=uid, resource_type="predmet", resource_id=predmet_id,
            correlation_id=event.correlation_id,
            metadata={"created": created, "updated": updated, "closed": closed, "open_total": len(target_by_key)},
        )
    except Exception as audit_exc:
        logger.warning("[CASE_EVOLUTION] case_action_refreshed audit upis neuspešan (non-fatal) predmet=%s: %s", predmet_id, audit_exc)

    return f"created={created} updated={updated} closed={closed}"


async def _consequence_project_case_actions_to_notifications(event: Event) -> str:
    """Program Omega, Final Sprint 007 (2026-08-06) — Canonical Notification
    & Trigger Engine, Phase 3 (Trigger Consolidation). Closes `OMEGA-020`
    (Sprint 006's own debt register): before this sprint, `case_actions`
    (this file's own canonical deadline detector, Rule 1) and
    `routers/notifications.py::_generate_notifications` (its own
    independent `rok`/`hitan_rok` query over the SAME `rocista` data)
    could each decide, separately, that a hearing/deadline is urgent —
    "dva mesta koja odlučuju o istom događaju," exactly what Phase 3
    forbids. This consequence makes `case_actions` the SOLE decision-maker:
    it runs LAST (after `refresh_case_actions`, same sequential-ordering
    guarantee every other consequence in this registry relies on) and
    PROJECTS the just-refreshed `PRIPREMITI_PODNESAK` case_actions rows —
    unchanged, not re-decided — into `notifications` rows a lawyer already
    knows how to read (the bell icon).

    CORRECTION (Operation One Truth, 2026-08-07): this docstring previously
    claimed "routers/notifications.py's own rok/hitan_rok generation is
    retired in the same commit" — verified FALSE by direct code trace, not
    accepted on the strength of this comment (this mission's own Principle 0).
    That generator (`_generate_notifications`'s rokovi/propušteni-rokovi
    blocks) is still live, still reads `predmet_hronologija` (a broader
    deadline calendar than `rocista`, including document-extracted deadlines
    this projection doesn't cover), and was NOT retired. What WAS fixed this
    mission: its own delete-then-regenerate cycle used to delete every unread
    rok/hitan_rok row for the user regardless of source, including this
    projection's own dedupe_key-tracked rows — now scoped to exclude any row
    carrying a dedupe_key, so the two systems no longer destructively collide.
    They still independently generate notifications for overlapping (not
    identical) deadline sources — named as `IRONLAWYER`-style debt, not a
    silent architecture claim.

    Reconciliation is dedupe-key-based, reusing case_actions' OWN stable
    per-fact key directly (`_stable_key("rociste", rociste_id)`) — the
    SAME idempotency identity, not a second one invented for notifications.
    Concurrency safety is migration 101's own partial UNIQUE index on
    `notifications(user_id, dedupe_key) WHERE procitano=FALSE`, the exact
    same pattern as case_actions' own `idx_case_actions_open_dedupe`
    (migration 099) — proven, not new."""
    predmet_id = event.predmet_id
    if not predmet_id:
        return "skipped_no_predmet_id"

    supa = _get_supa()

    pred_res = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("user_id,naziv").eq("id", predmet_id).maybe_single().execute()
    )
    pred_data = (pred_res.data if pred_res else None) or {}
    owner_uid = pred_data.get("user_id")
    naziv = pred_data.get("naziv") or "Predmet"
    if not owner_uid:
        return "skipped_no_owner"

    # Target: this predmet's own currently-OPEN deadline actions —
    # case_actions' own Rule 1 (PRIPREMITI_PODNESAK), refreshed by the
    # consequence that ran immediately before this one in the same
    # dispatch. Deliberately scoped to this ONE action type — extending
    # notifications to also fire for PRIBAVITI_DOKAZ/RAZRESITI_KONTRADIKCIJU/
    # etc. would be a genuine NEW notification category a lawyer never
    # received before, a product decision, not a consolidation of an
    # existing one (notifications.py's own pre-existing scope was always
    # just deadlines + inactivity).
    actions_res = await asyncio.to_thread(
        lambda: supa.table("case_actions")
            .select("dedupe_key,razlog,prioritet,rok")
            .eq("predmet_id", predmet_id)
            .eq("status", "open")
            .eq("tip", "PRIPREMITI_PODNESAK")
            .execute()
    )
    target_actions = (actions_res.data if actions_res else None) or []
    target_by_key = {a["dedupe_key"]: a for a in target_actions}

    existing_res = await asyncio.to_thread(
        lambda: supa.table("notifications")
            .select("id,dedupe_key")
            .eq("user_id", owner_uid)
            .eq("predmet_id", predmet_id)
            .eq("procitano", False)
            .not_.is_("dedupe_key", "null")
            .execute()
    )
    existing_rows = (existing_res.data if existing_res else None) or []
    existing_by_key = {r["dedupe_key"]: r["id"] for r in existing_rows}

    created, updated, closed = 0, 0, 0

    for key, action in target_by_key.items():
        canon_prio = action.get("prioritet") or "medium"
        notif_prio = CANONICAL_TO_NOTIFICATIONS.get(canon_prio, "normal")
        row = {
            "user_id": owner_uid,
            "tip": "hitan_rok" if canon_prio == "critical" else "rok",
            "naslov": f"{'⚠ Hitan rok' if canon_prio == 'critical' else 'Nadolazeći rok'} — {naziv}",
            "poruka": (action.get("razlog") or "Rok")[:500],
            "predmet_id": predmet_id,
            "prioritet": notif_prio,
            "dedupe_key": key,
        }
        if key in existing_by_key:
            await asyncio.to_thread(
                lambda r=row, nid=existing_by_key[key]: supa.table("notifications")
                    .update(r).eq("id", nid).execute()
            )
            updated += 1
        else:
            try:
                await asyncio.to_thread(lambda r=row: supa.table("notifications").insert(r).execute())
                created += 1
            except Exception as _ins_exc:
                # Partial UNIQUE index violation (migration 101) -- another
                # concurrent projection already created this exact
                # notification. Same benign-race handling as
                # _consequence_refresh_case_actions's own insert path.
                if "duplicate key" not in str(_ins_exc).lower() and "unique" not in str(_ins_exc).lower():
                    raise
                logger.info("[CASE_EVOLUTION] notification already projected concurrently, skipping: predmet=%s key=%s", predmet_id, key)

    for key, notif_id in existing_by_key.items():
        if key not in target_by_key:
            # The underlying deadline fact no longer holds (resolved,
            # rescheduled out of window, or the hearing was deleted) --
            # mark read rather than delete, so it still appears in the
            # notifications history exactly like a lawyer manually
            # dismissing it would.
            await asyncio.to_thread(
                lambda nid=notif_id: supa.table("notifications")
                    .update({"procitano": True}).eq("id", nid).execute()
            )
            closed += 1

    return f"created={created} updated={updated} closed={closed}"


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
        # Program Omega, Sprint 003 — runs LAST, always reading freshly-
        # refreshed Genome/risk-engine facts (handle_case_changed's own
        # sequential per-consequence loop guarantees genome_refresh already
        # completed for this same event).
        ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions),
        # Program Omega, Final Sprint 007 — runs LAST of all, always
        # projecting the JUST-refreshed case_actions rows (never a stale
        # read) into notifications. Closes OMEGA-020.
        ConsequenceDef(name="project_notifications", executor=_consequence_project_case_actions_to_notifications),
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
        ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions),
        ConsequenceDef(name="project_notifications", executor=_consequence_project_case_actions_to_notifications),
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
        # Program Phoenix, Mission 007 (LIVINGSYS-DEBT-016): this event never triggered
        # refresh_case_actions before -- case_actions/readiness (which _compute_target_actions
        # derives partly from predmet_dokazi, the table evidence_classification just wrote to)
        # could lag a live risk computation within the same build_case_context() response, a
        # self-documented ordering gap (see _consequence_refresh_case_actions's own docstring).
        # Reuses the SAME executor DOCUMENT_ACCEPTED/REVIEW_ACCEPTED/ROCISTE_ZAKAZANO already
        # register unchanged -- no new consequence logic invented.
        ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions),
    ],
    EventType.ROCISTE_ZAKAZANO: [
        # Reuses DOCUMENT_ACCEPTED's own genome_refresh executor UNCHANGED —
        # a new hearing changes tactical context the same way a new
        # document does, from Genome's own perspective (it just recomputes).
        # No timeline_entry here: routers/rocista.py never produced one for
        # hearing creation before this sprint, so none is invented now.
        ConsequenceDef(name="genome_refresh", executor=_consequence_genome_refresh),
        ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions),
        ConsequenceDef(name="project_notifications", executor=_consequence_project_case_actions_to_notifications),
    ],
    EventType.DOCUMENT_BATCH_COMPLETED: [
        # Program Omega, Sprint 002 — genome_refresh + case_intelligence_
        # summary, in this exact order. genome_refresh REUSED unchanged from
        # DOCUMENT_ACCEPTED (own idempotency, own verification) —
        # handle_case_changed's own sequential per-consequence loop
        # guarantees it completes before case_intelligence_summary starts,
        # so a crash-then-retry never redoes the expensive Genome recompute
        # once it has already succeeded (see
        # _consequence_case_intelligence_summary's own docstring for the
        # full reasoning).
        #
        # Program Omega, Sprint 003 — timeline_entry ADDED (REUSED unchanged
        # from DOCUMENT_ACCEPTED, parameterized via payload["timeline_opis"]).
        # Forensic Discovery finding: `finalize_intake_jobs_batch` now
        # suppresses its own per-job DOCUMENT_ACCEPTED emission (see
        # routers/smart_intake.py::_finalize_intake_job_core's own
        # `emit_document_accepted` parameter) so Genome only recomputes ONCE
        # per case per batch, not once per document — but DOCUMENT_ACCEPTED
        # was ALSO where the per-document Timeline entry came from. Without
        # this addition, batch-processed documents would get NO timeline
        # entry at all (neither per-job, now suppressed, nor batch-level,
        # previously missing here) — a real regression this sprint closes
        # before it ships.
        ConsequenceDef(name="genome_refresh", executor=_consequence_genome_refresh),
        ConsequenceDef(name="timeline_entry", executor=_consequence_timeline_entry),
        ConsequenceDef(name="case_intelligence_summary", executor=_consequence_case_intelligence_summary),
        ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions),
        ConsequenceDef(name="project_notifications", executor=_consequence_project_case_actions_to_notifications),
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
        # Program Lambda, Certification 004 (2026-08-06): the previous
        # read-then-write (_get_consequence_status then _mark_pending) was
        # a genuine TOCTOU race (LAMBDA003-EVT-001) -- see
        # _try_claim_consequence's own docstring for the full fix
        # rationale. A False return covers 2 DIFFERENT cases that must NOT
        # be treated the same:
        #   (a) genuinely 'completed' -- retry-safe, silently skip, the
        #       guarantee Scenario 2/3/5 rely on.
        #   (b) claimed by someone else but not yet stale enough to
        #       reclaim -- could mean a live worker is still processing it
        #       RIGHT NOW (fine to skip), OR it could mean that worker
        #       crashed and this consequence is now silently stuck.
        #
        # Program Lambda, Certification 005 (2026-08-07) -- Chaos Engineer
        # fork found (cross-layer, not visible to Certification 004's own
        # unit tests, which never exercised the actual dispatch_pending_
        # events() interaction): the OUTER event-claim staleness
        # (claim_pending_events, 30s) is SHORTER than the INNER
        # consequence-claim staleness (_CONSEQUENCE_STALE_PENDING_SECONDS,
        # 300s). A worker crash landing in that 30-300s gap -- an entirely
        # ordinary window for an OOM kill or a rolling deploy, not a rare
        # edge case -- used to be treated as case (a): the loop silently
        # `continue`d, the event was then marked dispatched by the OUTER
        # caller (dispatch_pending_events), and since nothing ever
        # re-invokes this specific (event_id, consequence_name) claim
        # again, the consequence stayed stuck at 'pending' FOREVER, with
        # zero error, zero retry, zero trace anywhere. For DOCUMENT_
        # ACCEPTED (this platform's own single most frequent event type,
        # 4 consequences including genome_refresh) this meant a case's
        # Genome could silently, permanently miss a refresh.
        #
        # Fix: only case (a) -- confirmed via a fresh read -- is treated as
        # a safe skip. Anything else raises ConsequenceClaimPending (see
        # its own docstring above for exactly why this can't be a bare
        # RuntimeError), so the outer dispatch layer does NOT mark this
        # event fully handled -- it stays eligible for retry (governed by
        # the OUTER claim's own 120s staleness window, not the fast ~3s
        # DispatchLoop cadence) until the consequence either completes
        # normally or becomes genuinely stale enough to reclaim (300s), or,
        # if genuinely stuck well past that, is dead-lettered -- a VISIBLE,
        # LOGGED, ALREADY-ESTABLISHED recovery state (services/event_bus.py's
        # own MAX_DISPATCH_ATTEMPTS), never a silent one.
        won = await _try_claim_consequence(event.event_id, c.name)
        if not won:
            existing = await _get_consequence_status(event.event_id, c.name)
            if existing and existing.get("status") == "completed":
                logger.info(
                    "[CASE_EVOLUTION] event=%s posledica=%s već završena, preskačem (retry-safe).",
                    event.event_id[:8], c.name,
                )
                continue
            logger.warning(
                "[CASE_EVOLUTION] event=%s posledica=%s nije završena a claim nije osvojen "
                "(status=%s) -- tražim spoljni retry umesto tihog trajnog gubitka.",
                event.event_id[:8], c.name, existing.get("status") if existing else None,
            )
            raise ConsequenceClaimPending(
                f"case_evolution: consequence '{c.name}' for event {event.event_id[:8]} "
                f"is claimed but not completed (status={existing.get('status') if existing else 'unknown'}) "
                f"-- requesting outer retry instead of silently skipping"
            )

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
