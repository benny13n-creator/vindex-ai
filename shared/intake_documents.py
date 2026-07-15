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
) -> None:
    """Founder-ov eksplicitan zahtev — upisuje se posle SVAKOG obrađenog
    dokumenta. Best-effort: greška ovde ne sme da obori obradu (ovo je
    podatak za buduće podešavanje, ne kritičan put).

    correction_reason (Validation Sprint, drugi krug feedbacka) — OPCIONO
    slobodno objašnjenje "zašto", ne samo "šta" je ispravljeno ("Datum
    presude nije rok za žalbu"). Namerno opciono — ne sme da doda trenje na
    10-sekundnu ispravku tako što bi postalo obavezno polje.

    error_source (LEC feedback, treći krug) — OPCIONO, kategorička
    klasifikacija KOG SLOJA je stvarno kriv (ERROR_SOURCES) — fail-soft:
    nevalidna vrednost se loguje i tiho odbacuje (postaje None), ne obara
    upis, jer je constraint na DB nivou samo dodatna zaštita, ne treba da
    obori proizvodni tok zbog jednog lošeg parametra."""
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
            }).execute()
        )
    except Exception as exc:
        logger.warning("[INTAKE_DOCUMENTS] processing_outcome upis neuspešan (non-fatal) za job=%s: %s", intake_job_id[:8], exc)


async def get_job_result(intake_job_id: str) -> dict:
    """Vraća sve što UI treba da prikaže za jedan posao — dokument,
    entiteti (Confidence Graph), i da li čeka review. Jedan pogled, ne
    3 zasebna poziva sa frontenda."""
    supa = _get_supa()

    doc_res = await asyncio.to_thread(
        lambda: supa.table("intake_documents").select("*").eq("intake_job_id", intake_job_id).maybe_single().execute()
    )
    document = doc_res.data
    if not document:
        return {"document": None, "entities": [], "review": None}

    ent_res = await asyncio.to_thread(
        lambda: supa.table("extracted_entities").select("*").eq("document_id", document["id"]).execute()
    )
    entities = ent_res.data or []

    review_res = await asyncio.to_thread(
        lambda: supa.table("intake_review_queue").select("*").eq("intake_job_id", intake_job_id).is_("resolved_at", "null").maybe_single().execute()
    )
    review = review_res.data

    return {"document": document, "entities": entities, "review": review}


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
    if not old_res.data:
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
    doc = doc_res.data or {}

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


async def resolve_review_queue_for_job(intake_job_id: str, resolved_by: str) -> None:
    """Poziva se kad su sve niske-confidence stavke za jedan posao
    ispravljene — markira review queue red kao rešen."""
    from datetime import datetime, timezone
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("intake_review_queue")
            .update({"resolved_at": datetime.now(timezone.utc).isoformat(), "resolved_by": resolved_by})
            .eq("intake_job_id", intake_job_id)
            .is_("resolved_at", "null")
            .execute()
    )
