# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_accuracy.py

Smart Intake Engine — Validation Sprint (founder, 2026-07-15). Live
operational KPIs computed from existing data (intake_documents,
extracted_entities, intake_review_queue, intake_processing_outcomes) — NOT
ground-truth accuracy (that's scripts/intake_accuracy_benchmark.py against
golden_dataset/, a genuinely different claim: "the system found something
confidently" vs "the system found the RIGHT thing").

Computed in Python over raw rows, not a SQL view (unlike Faza 0's
intake_queue_metrics/events_outbox_metrics) — deliberately, to avoid a
new migration/live-testing round-trip right after migrations 073/074's
long back-and-forth. Row counts at this stage don't justify a view; revisit
if this ever becomes a hot path (same "don't pre-optimize" principle
already applied earlier this session).

Honest-empty-state discipline (same as Revenue Intelligence, built earlier
this project): every KPI here returns None with an explicit "nedovoljno
podataka" flag when there isn't enough data yet, never a fabricated number.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
from typing import Optional

from shared.deps import _get_supa

_MIN_SAMPLE_SIZE = 5  # ispod ovoga, prikazuje se "nedovoljno podataka", ne broj koji izgleda precizan a nije


def _avg(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


async def get_office_accuracy_kpis(kancelarija_id: Optional[str] = None) -> dict:
    """Vraća founder-ove Validation Sprint KPI-jeve. kancelarija_id filter
    je pripremljen za Office Accuracy Dashboard (po kancelariji, ne
    globalno) — danas None znači globalno, jer intake_jobs.kancelarija_id
    još nije popunjavan nigde (dizajn review §26.9, isto ograničenje
    zabeleženo u routers/smart_intake.py upload endpoint-u)."""
    supa = _get_supa()

    documents_res = await asyncio.to_thread(
        lambda: supa.table("intake_documents").select("id, ocr_used, classification_method").execute()
    )
    documents = documents_res.data or []
    total_documents = len(documents)

    if total_documents < _MIN_SAMPLE_SIZE:
        return {
            "nedovoljno_podataka": True,
            "obradjeno_dokumenata": total_documents,
            "napomena": f"Manje od {_MIN_SAMPLE_SIZE} obrađenih dokumenata — brojevi bi izgledali precizni a ne bi bili. Sačekati realan volumen.",
        }

    review_res = await asyncio.to_thread(
        lambda: supa.table("intake_review_queue").select("intake_job_id, document_id, reason, low_confidence_fields").execute()
    )
    review_rows = review_res.data or []

    entities_res = await asyncio.to_thread(
        lambda: supa.table("extracted_entities").select("entity_type, extraction_method, reviewed, document_id").execute()
    )
    entities = entities_res.data or []

    outcomes_res = await asyncio.to_thread(
        lambda: supa.table("intake_processing_outcomes").select("*").order("created_at").execute()
    )
    outcomes = outcomes_res.data or []

    # ── OCR uspešnost — % dokumenata koji NISU završili sa reason=ocr_failed ──
    ocr_failed_count = sum(1 for r in review_rows if r["reason"] == "ocr_failed")
    ocr_success_rate = round(1 - (ocr_failed_count / total_documents), 4)

    # ── Prosečan broj review polja po dokumentu — SVI dokumenti u imeniocu,
    # ne samo oni koji su završili u review-u (0 za "prošao bez problema") ──
    low_conf_rows = [r for r in review_rows if r["reason"] == "low_confidence_extraction"]
    fields_by_document = {r["document_id"]: len(r.get("low_confidence_fields") or []) for r in low_conf_rows}
    review_field_counts = [fields_by_document.get(d["id"], 0) for d in documents]
    avg_review_fields = _avg(review_field_counts)

    # ── Correction rate — % dokumenata sa bar jednim reviewed=true entitetom ──
    documents_with_correction = {e["document_id"] for e in entities if e.get("reviewed")}
    correction_rate = round(len(documents_with_correction) / total_documents, 4)

    # ── Najčešće ispravljano polje ──
    corrected_entity_types = Counter(e["entity_type"] for e in entities if e.get("reviewed"))
    most_corrected = corrected_entity_types.most_common(1)[0][0] if corrected_entity_types else None

    # ── LLM fallback % — na nivou klasifikacije i na nivou ekstrakcije polja ──
    llm_classifications = sum(1 for d in documents if d.get("classification_method") == "llm")
    classification_llm_rate = round(llm_classifications / total_documents, 4)

    llm_entities = sum(1 for e in entities if e.get("extraction_method") == "llm")
    entity_llm_rate = round(llm_entities / len(entities), 4) if entities else None

    # ── Prosečno vreme obrade (worker pipeline, ne upload HTTP round-trip) ──
    original_outcomes = [o for o in outcomes if not o.get("user_corrected") and o.get("processing_time_ms")]
    avg_processing_ms = _avg([o["processing_time_ms"] for o in original_outcomes])

    # ── Prosečno vreme do ispravke — APROKSIMACIJA, ne precizno UX merenje ──
    # (razlika između kad je dokument prvi put obrađen i kad je ispravka
    # upisana; ne meri koliko je advokat stvarno gledao u ekran — frontend
    # bi trebalo eksplicitno da javi "review otvoren" da bi ovo bilo tačno).
    correction_deltas = []
    original_by_job: dict[str, datetime] = {}
    for o in outcomes:
        if not o.get("user_corrected"):
            ts = _parse_ts(o.get("created_at"))
            if ts and o.get("intake_job_id") not in original_by_job:
                original_by_job[o["intake_job_id"]] = ts
    for o in outcomes:
        if o.get("user_corrected"):
            correction_ts = _parse_ts(o.get("created_at"))
            original_ts = original_by_job.get(o.get("intake_job_id"))
            if correction_ts and original_ts:
                correction_deltas.append((correction_ts - original_ts).total_seconds())
    avg_correction_s = _avg(correction_deltas)

    return {
        "nedovoljno_podataka": False,
        "obradjeno_dokumenata": total_documents,
        "ocr_uspesnost": ocr_success_rate,
        "prosecan_broj_review_polja": avg_review_fields,
        "stopa_ispravki": correction_rate,
        "najcesce_ispravljano_polje": most_corrected,
        "llm_fallback_klasifikacija": classification_llm_rate,
        "llm_fallback_ekstrakcija": entity_llm_rate,
        "prosecno_vreme_obrade_ms": avg_processing_ms,
        "prosecno_vreme_do_ispravke_s": avg_correction_s,
        "napomena_vreme_ispravke": "Aproksimacija (razlika obrada→ispravka u bazi), ne precizno merenje vremena korisnika pred ekranom." if avg_correction_s is not None else None,
    }
