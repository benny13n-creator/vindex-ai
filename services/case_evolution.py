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
    nove_kontradikcije = max(0, len(kontradikcije_posle) - before_kontradikcije)
    novi_dogadjaji = max(0, len(dogadjaji_posle) - before_dogadjaji)

    # Core Consolidation's own jedini algoritam za "šta nedostaje / koji su
    # rizici" -- isti kod koji routers/matter_intel.py već koristi, nikad
    # duplirano ovde (namerno NE Genome-ov sopstveni odvojen "nedostaje"/
    # "upozorenja" -- to bi vratilo tačno onu duplikaciju koju je Core
    # Consolidation uklonio 2026-07-22).
    from services.risk_engine import calculate_procesni_rizik, identify_case_problems
    from shared.constants import EXPECTED_DOCS as _EXPECTED_DOCS
    tip_predmeta = after_data.get("tip") or "ostalo"
    dokazi_r, dok_r, rok_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select("snaga,kategorija,pravni_element").eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("naziv_fajla,status").eq("predmet_id", predmet_id).execute()),
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
            "kontradikcije": kontradikcije_posle[-nove_kontradikcije:] if nove_kontradikcije else [],
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
        asyncio.to_thread(lambda: supa.table("predmet_dokazi").select("snaga,kategorija,pravni_element").eq("predmet_id", predmet_id).is_("deleted_at", "null").execute()),
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
        if dani < 0 or dani > 30:
            continue
        actions.append({
            "tip": "PRIPREMITI_PODNESAK",
            "razlog": f"Ročište ({r.get('sud') or 'sud'}) za {dani} dan(a) — {rok_datum.isoformat()}",
            "dokaz": {"rociste_id": r.get("id"), "sud": r.get("sud"), "datum": rok_datum.isoformat(), "dani_preostalo": dani},
            "prioritet": _priority_by_days(dani),
            "rok": rok_datum.isoformat(),
            "dedupe_key": _stable_key("rociste", str(r.get("id"))),
        })

    # Rule 2/4/5 -- Core Consolidation's own canonical problem list, mapped
    # to stable per-category keys (not per-count) so a changing count
    # UPDATES the existing action instead of closing+reopening it.
    for p in problemi:
        text = p.get("problem") or ""
        ozbiljnost = p.get("ozbiljnost")
        if "kritičan rok" in text:
            continue  # already covered, per-rociste, by Rule 1 above -- avoid a duplicate, less precise signal
        if text.startswith("Nema uploadovanih dokaza"):
            actions.append({
                "tip": "PRIBAVITI_DOKAZ", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text},
                "prioritet": "critical", "rok": None,
                "dedupe_key": _stable_key("problem", "nema_dokaza"),
            })
        elif text.startswith("Nedostaje "):
            actions.append({
                "tip": "PRIBAVITI_DOKAZ", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text},
                "prioritet": "high", "rok": None,
                "dedupe_key": _stable_key("problem", "nedostaje", text),
            })
        elif "predstojećih rokova" in text:
            actions.append({
                "tip": "PLANIRATI_ROKOVE", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text, "predstojeći_rokovi": rizik.get("predstojeći_rokovi")},
                "prioritet": "high", "rok": None,
                "dedupe_key": _stable_key("problem", "predstojeci_rokovi"),
            })
        elif text.startswith("Dokazi slabe snage"):
            actions.append({
                "tip": "OJACATI_DOKAZE", "razlog": text,
                "dokaz": {"izvor": "identify_case_problems", "problem": text},
                "prioritet": "informational", "rok": None,
                "dedupe_key": _stable_key("problem", "dokazi_slabi"),
            })

    # Rule 3 -- contradictions, sourced directly from Genome's own current
    # case_dna.kontradikcije (already required to carry a "DOK-XX str.Y"
    # source location by Genome's own extraction prompt).
    _TEZINA_PRIORITET = {"kriticna": "critical", "vazna": "high", "manja": "medium"}
    for k in (case_dna.get("kontradikcije") or []):
        opis = k.get("opis") or ""
        loc1 = k.get("lokacija_1") or ""
        loc2 = k.get("lokacija_2") or ""
        if not opis:
            continue
        actions.append({
            "tip": "RAZRESITI_KONTRADIKCIJU", "razlog": opis,
            "dokaz": {"opis": opis, "lokacija_1": loc1, "lokacija_2": loc2, "tezina": k.get("tezina")},
            "prioritet": _TEZINA_PRIORITET.get(k.get("tezina"), "medium"), "rok": None,
            "dedupe_key": _stable_key("kontradikcija", opis, loc1, loc2),
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
    REAL safety net -- two concurrent refreshes racing to CREATE the same
    action both attempt the same upsert; the DB constraint, not application
    logic, guarantees exactly one open row per fact survives, matching
    every other idempotency mechanism this whole engagement has used
    (content_sha256, idempotency_key, case_evolution_consequences)."""
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

    existing_res = await asyncio.to_thread(
        lambda: supa.table("case_actions").select("id,dedupe_key").eq("predmet_id", predmet_id).eq("status", "open").execute()
    )
    existing_rows = (existing_res.data if existing_res else None) or []
    existing_by_key = {r["dedupe_key"]: r["id"] for r in existing_rows}

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
            await asyncio.to_thread(
                lambda r=row, aid=existing_by_key[key]: supa.table("case_actions")
                    .update({**r, "updated_at": _now_iso}).eq("id", aid).execute()
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

    for key, action_id in existing_by_key.items():
        if key not in target_by_key:
            await asyncio.to_thread(
                lambda aid=action_id: supa.table("case_actions")
                    .update({"status": "closed", "closed_at": _now_iso}).eq("id", aid).execute()
            )
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
        ConsequenceDef(name="refresh_case_actions", executor=_consequence_refresh_case_actions),
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
