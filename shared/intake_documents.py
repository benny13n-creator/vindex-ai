# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_documents.py

Smart Intake Engine, Faza 1A — perzistencija klasifikacije, Confidence
Graph-a (ADR-0005), review queue-a i processing outcomes (migracija 074).

Routing prag: ADR-0005 opšti prag je 90% auto-accept / 60% "nedovoljno
dokaza da se pogodi". Za Fazu 1A pojednostavljeno na jedan prag (< 90% =
review) — svaki entitet ispod praga ide u low_confidence_fields, čak i kad
value=None (rok/podatak nije pronađen — fail-soft, ne tiha praznina).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from shared.deps import _get_supa

logger = logging.getLogger("vindex.intake_documents")

AUTO_ACCEPT_THRESHOLD = 0.90

# Deljen vokabular sa evaluation/lec/ i evaluation/hall_of_shame/ anotacijama
# (founder, LEC feedback 2026-07-15) — KOJI SLOJ je stvarno uzrok greške, ne
# samo "šta" je ispravljeno (to je correction_reason, slobodan tekst).
ERROR_SOURCES = (
    "ocr", "parser", "regex", "heuristics", "llm",
    "ground_truth", "human_annotation", "unknown",
)


async def create_document(
    intake_job_id: str,
    document_type: str,
    classification_confidence: float,
    classification_method: str,
    ocr_confidence: Optional[float] = None,
    ocr_used: bool = False,
    suggested_filename: Optional[str] = None,
) -> str:
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("intake_documents").insert({
            "intake_job_id": intake_job_id,
            "document_type": document_type,
            "classification_confidence": classification_confidence,
            "classification_method": classification_method,
            "ocr_confidence": ocr_confidence,
            "ocr_used": ocr_used,
            "suggested_filename": suggested_filename,
        }).execute()
    )
    document_id = res.data[0]["id"]
    logger.info("[INTAKE_DOCUMENTS] document created: %s type=%s conf=%.2f (%s)", document_id[:8], document_type, classification_confidence, classification_method)
    return document_id


async def insert_entities(document_id: str, entities: list[dict]) -> list[dict]:
    """Bulk insert Confidence Graph redova. Vraća redove sa dodeljenim id-
    jevima (potrebno da review queue zna tačno koji entity_id treba da se
    ispravi)."""
    if not entities:
        return []
    supa = _get_supa()
    rows = [{
        "document_id": document_id,
        "entity_type": e["entity_type"],
        "value": e["value"],
        "confidence": e["confidence"],
        "extraction_method": e["extraction_method"],
    } for e in entities]
    res = await asyncio.to_thread(lambda: supa.table("extracted_entities").insert(rows).execute())
    return res.data or []


async def create_review_queue_entry(
    intake_job_id: str,
    document_id: Optional[str],
    reason: str,
    low_confidence_fields: list[str],
) -> None:
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_review_queue").insert({
            "intake_job_id": intake_job_id,
            "document_id": document_id,
            "reason": reason,
            "low_confidence_fields": low_confidence_fields,
        }).execute()
    )
    logger.info("[INTAKE_DOCUMENTS] review queue: job=%s reason=%s fields=%s", intake_job_id[:8], reason, low_confidence_fields)


async def write_processing_outcome(
    intake_job_id: str,
    document_type: Optional[str],
    ocr_confidence: Optional[float],
    entity_confidence: dict,
    processing_time_ms: int,
    user_corrected: bool = False,
    fields_corrected: Optional[list[str]] = None,
    correction_reason: Optional[str] = None,
    error_source: Optional[str] = None,
    raise_on_error: bool = False,
    segment_id: Optional[str] = None,
) -> None:
    """Founder-ov eksplicitan zahtev — upisuje se posle SVAKOG obrađenog
    dokumenta. Best-effort po default-u: greška ovde ne sme da obori
    `correct_entity`-jev 10-sekundni ispravni tok (ispravka sama je vec
    uspesno committed pre ovog poziva — ovaj upis je dodatna analitika, ne
    sme dodati trenje na vec zavrsenu korisnicku akciju).

    raise_on_error (Program Intake Sprint 002, 2026-08-05) — shared/
    intake_worker.py::_process() prosledjuje True ovde, jer je JEDINO za taj
    pozivaoca ovaj upis STVARNI signal zavrsetka (has_processing_outcome()
    ga koristi da razlikuje "posao je gotov" od "posao je pao usred obrade").
    Sprint 002 Fork A §B1 / Fork B §3.3 su nezavisno dokazali da tiho
    gutanje ove greske ovde tiho ponovo otvara TACNO onaj bug oblik koji je
    Sprint 001 zatvorio (has_processing_outcome/delete_partial_document) --
    kroz druga vrata (upis sam padne, umesto pad PRE upisa). Kad
    raise_on_error=True i upis padne, izuzetak sada ide gore do _tick()-ovog
    vec dokazanog retry/dead-letter puta (mark_job_failed), koji na sledecem
    pokusaju ispravno detektuje nepotpuno stanje i cisto obradjuje ponovo --
    isti mehanizam koji Sprint 001 vec izgradio, samo sada primenjen i na
    ovaj poslednji korak, ne samo na sve pre njega.

    correction_reason (Validation Sprint, drugi krug feedbacka) — OPCIONO
    slobodno objašnjenje "zašto", ne samo "šta" je ispravljeno ("Datum
    presude nije rok za žalbu"). Namerno opciono — ne sme da doda trenje na
    10-sekundnu ispravku tako što bi postalo obavezno polje.

    error_source (LEC feedback, treći krug) — OPCIONO, kategorička
    klasifikacija KOG SLOJA je stvarno kriv (ERROR_SOURCES) — fail-soft:
    nevalidna vrednost se loguje i tiho odbacuje (postaje None), ne obara
    upis, jer je constraint na DB nivou samo dodatna zaštita, ne treba da
    obori proizvodni tok zbog jednog lošeg parametra.

    segment_id (Program Intake Sprint 005, 2026-08-05) — OPCIONO, nenulto
    samo kad je posao segmentiran u 2+ dokumenta (shared/intake_segment.py).
    Bez njega bi više segmenata jednog posla pisalo nerazlučive
    processing_outcomes redove pod istim intake_job_id (isti job_id, nema
    document_id kolone ovde) — segment_id je jedina stvar koja ih razdvaja."""
    if error_source is not None and error_source not in ERROR_SOURCES:
        logger.warning("[INTAKE_DOCUMENTS] nepoznat error_source '%s' za job=%s — odbačen", error_source, intake_job_id[:8])
        error_source = None
    try:
        supa = _get_supa()
        await asyncio.to_thread(
            lambda: supa.table("intake_processing_outcomes").insert({
                "intake_job_id": intake_job_id,
                "document_type": document_type,
                "ocr_confidence": ocr_confidence,
                "entity_confidence": entity_confidence,
                "user_corrected": user_corrected,
                "fields_corrected": fields_corrected or [],
                "correction_reason": correction_reason,
                "error_source": error_source,
                "processing_time_ms": processing_time_ms,
                "segment_id": segment_id,
            }).execute()
        )
    except Exception as exc:
        logger.warning("[INTAKE_DOCUMENTS] processing_outcome upis neuspešan za job=%s: %s", intake_job_id[:8], exc)
        if raise_on_error:
            raise


async def has_processing_outcome(intake_job_id: str) -> bool:
    """Da li je write_processing_outcome već upisan za ovaj posao — jedini
    pouzdan signal da je _process() (shared/intake_worker.py) STVARNO
    završio do kraja, jer je to poslednja linija u obe grane (OCR-failed i
    normalni put). Program Intake Sprint 001 (2026-08-04) — korišćeno da
    razlikuje "posao je gotov" od "posao je pao usred obrade", jer sama
    provera "da li dokument postoji" (get_job_result) to ne razlikuje."""
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("intake_processing_outcomes").select("intake_job_id").eq("intake_job_id", intake_job_id).maybe_single().execute()
    )
    return bool(res.data if res else None)


async def delete_partial_document(document_id: str, intake_job_id: str) -> None:
    """Program Intake Sprint 001 (2026-08-04) — čisti tragove nepotpunog
    pokušaja obrade (dokument postoji, ali processing_outcome ne, što znači
    da je prethodni pokušaj pao negde između create_document() i
    write_processing_outcome()) pre ponovne obrade od nule. Redosled
    brisanja poštuje FK (extracted_entities i intake_review_queue
    referenciraju intake_documents bez ON DELETE CASCADE — migracija
    074_intake_phase1a.sql) — deca pre roditelja."""
    supa = _get_supa()
    await asyncio.to_thread(lambda: supa.table("extracted_entities").delete().eq("document_id", document_id).execute())
    await asyncio.to_thread(lambda: supa.table("intake_review_queue").delete().eq("document_id", document_id).execute())
    await asyncio.to_thread(lambda: supa.table("intake_documents").delete().eq("id", document_id).execute())
    logger.warning("[INTAKE_DOCUMENTS] nepotpun dokument obrisan: document_id=%s job=%s (ponovna obrada od nule)", document_id[:8], intake_job_id[:8])


async def get_job_result(intake_job_id: str) -> dict:
    """Vraća sve što UI treba da prikaže za jedan posao — dokument,
    entiteti (Confidence Graph), i da li čeka review. Jedan pogled, ne
    3 zasebna poziva sa frontenda."""
    supa = _get_supa()

    # NAPOMENA: instalirana verzija postgrest-py (2.28.3) vraća goli None iz
    # maybe_single().execute() kad nema redova (ne response objekat sa
    # .data=None) — otkriveno 2026-07-16 pravim end-to-end testom (worker je
    # cutke padao na SVAKOM poslu na ovoj tacnoj liniji, idempotency check na
    # pocetku _process()). `res.data if res else None` je obavezno svuda
    # gde se maybe_single() koristi u ovom fajlu, ne kozmeticka izmena.
    doc_res = await asyncio.to_thread(
        lambda: supa.table("intake_documents").select("*").eq("intake_job_id", intake_job_id).maybe_single().execute()
    )
    document = doc_res.data if doc_res else None
    if not document:
        return {"document": None, "entities": [], "review": None}

    ent_res = await asyncio.to_thread(
        lambda: supa.table("extracted_entities").select("*").eq("document_id", document["id"]).execute()
    )
    entities = ent_res.data or []

    review_res = await asyncio.to_thread(
        lambda: supa.table("intake_review_queue").select("*").eq("intake_job_id", intake_job_id).is_("resolved_at", "null").maybe_single().execute()
    )
    review = review_res.data if review_res else None

    return {"document": document, "entities": entities, "review": review}


async def get_job_documents(intake_job_id: str) -> list[dict]:
    """Program Intake Sprint 006 (2026-08-05) — the list-returning sibling of
    get_job_result(), needed because Sprint 005 (Canonical Document
    Segmentation) can legitimately produce 2+ intake_documents rows under one
    intake_job_id. get_job_result()'s own `.maybe_single()` call would RAISE
    (postgrest's own ambiguity guard) the moment it ran against a segmented
    job — confirmed as a live, structural incompatibility during this
    sprint's own investigation (finalize_intake_job and GET /jobs/{job_id}
    both still called get_job_result() unconditionally). This function never
    uses `.maybe_single()` — a plain list query handles 0, 1, or N rows
    uniformly, with no special-casing needed by either caller.

    Ordered by `created_at` (each document's own insert order — for a
    segmented job this matches segment_index/reading order, since
    shared/intake_worker.py's _process_segments() creates them in that
    sequence) so callers that need a single "anchor" document (e.g.
    finalize_intake_job's case-naming logic) can deterministically use
    documents[0] rather than an arbitrary row."""
    supa = _get_supa()
    doc_res = await asyncio.to_thread(
        lambda: supa.table("intake_documents").select("*").eq("intake_job_id", intake_job_id).order("created_at").execute()
    )
    docs = doc_res.data or []
    if not docs:
        return []

    results = []
    for document in docs:
        ent_res = await asyncio.to_thread(
            lambda doc_id=document["id"]: supa.table("extracted_entities").select("*").eq("document_id", doc_id).execute()
        )
        entities = ent_res.data or []

        # Scoped by document_id, not just intake_job_id -- a review entry for
        # ONE document under a multi-document job must never be attached to
        # a DIFFERENT document's result (the same ambiguity class get_job_result's
        # own intake_job_id-only review query would have hit for a segmented job).
        # Deliberately a plain list query, never `.maybe_single()`: a single
        # document can carry 2+ simultaneous unresolved review reasons today
        # (e.g. both 'segmentation_uncertain' and 'low_confidence_extraction'
        # -- shared/intake_worker.py's _process_segments() can write both for
        # the same segment), which would trip the identical ambiguity guard
        # this function exists to avoid for the intake_job_id-level query.
        review_res = await asyncio.to_thread(
            lambda doc_id=document["id"]: supa.table("intake_review_queue").select("*").eq("intake_job_id", intake_job_id).eq("document_id", doc_id).is_("resolved_at", "null").execute()
        )
        reviews = review_res.data or []
        review = reviews[0] if reviews else None

        results.append({"document": document, "entities": entities, "review": review})

    return results


async def correct_entity(entity_id: str, corrected_value: str, resolved_by: str, reason: Optional[str] = None, error_source: Optional[str] = None) -> dict:
    """Ovo je '10-sekundna ispravka' iz proizvodnog Definition of Done —
    original value se NIKAD ne briše (corrected_value je dodatak), reviewed
    postaje true, i piše se NOV processing_outcomes red sa user_corrected=
    true (founder-ov zahtev: ovo je zlato za buduće podešavanje pragova).

    reason (Validation Sprint) — OPCIONO, "zašto" ne samo "šta". Ostaje
    opciono namerno: obavezno polje bi pretvorilo "ispravku za 10 sekundi"
    u formular, što bi poništilo tačno ono što Faza 1A Definition of Done
    traži.

    error_source (LEC feedback, treći krug) — OPCIONO, KOJI SLOJ je kriv
    (ERROR_SOURCES) — isto opciono iz istog razloga."""
    supa = _get_supa()

    old_res = await asyncio.to_thread(
        lambda: supa.table("extracted_entities").select("*").eq("id", entity_id).maybe_single().execute()
    )
    if not old_res or not old_res.data:
        raise ValueError(f"extracted_entities red '{entity_id}' nije pronađen.")
    entity = old_res.data

    await asyncio.to_thread(
        lambda: supa.table("extracted_entities")
            .update({"corrected_value": corrected_value, "reviewed": True})
            .eq("id", entity_id)
            .execute()
    )

    doc_res = await asyncio.to_thread(
        lambda: supa.table("intake_documents").select("intake_job_id,document_type").eq("id", entity["document_id"]).maybe_single().execute()
    )
    doc = (doc_res.data if doc_res else None) or {}

    await write_processing_outcome(
        intake_job_id=doc.get("intake_job_id", ""),
        document_type=doc.get("document_type"),
        ocr_confidence=None,
        entity_confidence={entity["entity_type"]: entity["confidence"]},
        processing_time_ms=0,
        user_corrected=True,
        fields_corrected=[entity["entity_type"]],
        correction_reason=reason,
        error_source=error_source,
    )

    logger.info("[INTAKE_DOCUMENTS] entity corrected: %s (%s) od %s", entity_id[:8], entity["entity_type"], resolved_by)
    return {"entity_id": entity_id, "entity_type": entity["entity_type"], "corrected_value": corrected_value}


async def resolve_review_queue_for_job(intake_job_id: str, resolved_by: str) -> bool:
    """Poziva se kad su sve niske-confidence stavke za jedan posao
    ispravljene — markira review queue red kao rešen. Idempotentno:
    `.is_("resolved_at", "null")` znači da drugi/treći poziv nad istim
    poslom ne radi ništa (Postgres single-row UPDATE atomicity — isti
    obrazac kao tip_dokaza race-safety iz Sprint 002/003, konkurentni
    pozivi se sami prirodno serijalizuju na DB nivou).

    Vraća True ako je OVAJ poziv stvarno razrešio nerazrešen red (koristi
    se u resolve_review() ispod da razlikuje "ja sam upravo potvrdio" od
    "neko je već potvrdio pre mene" — Program Intake Sprint 004)."""
    from datetime import datetime, timezone
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("intake_review_queue")
            .update({"resolved_at": datetime.now(timezone.utc).isoformat(), "resolved_by": resolved_by})
            .eq("intake_job_id", intake_job_id)
            .is_("resolved_at", "null")
            .execute()
    )
    return bool(res.data)


async def resolve_review(intake_job_id: str, resolved_by: str) -> dict:
    """Program Intake Sprint 004 (2026-08-05) -- kanonski i JEDINI nacin da
    covek potvrdi nisko-pouzdanu klasifikaciju/ekstrakciju i da obrada
    automatski nastavi. resolve_review_queue_for_job je postojala od
    migracije 074 ali nikad nije bila pozvana nigde u kodu (Sprint 004
    Fork A, potvrdjeno repo-wide grep-om) -- ovo je prva stvarna zicna
    veza.

    Dva upisa, namerno NE u jednoj RPC transakciji (Fork B Sprint 002 §3.2
    -- supabase-py nema multi-statement atomicnost van RPC-a, a ovde nije
    ni potrebna): ako PRVI upis (review resolved_at) uspe a DRUGI (job
    status) padne, sledeci pokusaj ovog istog poziva je bezbedan -- prvi
    upis je vec idempotentan no-op (resolved_at vise nije null), drugi
    upis se prosto ponovo pokusa. Posao ostaje ispravno blokiran
    (status i dalje 'awaiting_review') dok OBA upisa stvarno ne prodju --
    fail-closed, ne fail-open (isti princip kao Sprint 002 Fork B §3.3-ovo
    "self-healing bez transakcije" zapazanje)."""
    review_resolved_now = await resolve_review_queue_for_job(intake_job_id, resolved_by)

    supa = _get_supa()
    status_res = await asyncio.to_thread(
        lambda: supa.table("intake_jobs")
            .update({"status": "completed"})
            .eq("id", intake_job_id)
            .eq("status", "awaiting_review")
            .execute()
    )
    job_status_advanced = bool(status_res.data)

    logger.info(
        "[INTAKE_DOCUMENTS] review resolved: job=%s od=%s (review_resolved_now=%s, job_status_advanced=%s)",
        intake_job_id[:8], resolved_by, review_resolved_now, job_status_advanced,
    )
    return {
        "review_resolved_now": review_resolved_now,
        "job_status_advanced": job_status_advanced,
    }
