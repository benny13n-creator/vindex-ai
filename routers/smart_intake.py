# -*- coding: utf-8 -*-
"""
Vindex AI — routers/smart_intake.py

Smart Intake Engine — POST /api/smart-intake/documents (upload), GET
.../jobs/{id} (proizvodni Definition of Done: tip + Confidence Graph +
tačna polja za proveru u JEDNOM pozivu), POST .../entities/{id}/correct
(10-sekundna ispravka), GET .../admin/health.

NAPOMENA O NAZIVU PUTANJE: ADR-0001 je originalno specificirao
`/api/intake/documents`. Pri implementaciji je otkriveno da `/api/intake/*`
već u potpunosti pripada POSTOJEĆEM routers/intake.py — CRM Intake Wizard
(ekstrakcija/kreiraj/conflict-check/templates/bulk-import/history, 7 ruta,
već u produkciji). Isti naziv "intake", potpuno različita funkcija (otvaranje
predmeta/klijenta, ne organizacija dokumenata). Da bi se izbegao sudar sa
živim sistemom, ova ruta koristi `/api/smart-intake/*` — formalno zabeleženo
kao amandman na ADR-0001 (vidi belešku na dnu tog fajla), ne tiha izmena.

Ovo je NOVA putanja, NE preprava postojećeg /api/dokument/upload (taj
endpoint je efemerni session-based Q&A upload — sinhron po dizajnu, jer
korisnik odmah postavlja pitanja o dokumentu u istom toku; prebacivanje NA
queue bi mu pokvarilo tačno tu funkciju). Smart Intake je nezavisna nova
putanja od prvog dana — bez feature-flag grananja između dva paralelna
sistema (founder eksplicitno zabranio: "ako uvodiš novu putanju, uvedi je
potpuno").

Upload kontrakt (nepromenjen od Faze 0): perzistuje fajl (enkriptovano,
isti obrazac kao klijenti/router.py Trezor) i vraća 202 + job_id ODMAH —
prava obrada (Faza 1A: OCR → klasifikacija → ekstrakcija, shared/
intake_worker.py) dešava se u pozadini. Ako upload i dalje čeka obradu pre
odgovora, cela poenta queue arhitekture je izgubljena.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter
from shared import intake_documents, intake_queue

logger = logging.getLogger("vindex.smart_intake")
router = APIRouter(prefix="/api/smart-intake", tags=["smart_intake"])

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB, isti limit kao /api/dokument/upload
_STORAGE_BUCKET = "intake-dokumenti"


async def _require_founder(user: dict = Depends(get_current_user)) -> dict:
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Samo za administratore.")
    return user


def _encrypt(raw: bytes) -> bytes:
    """Isti obrazac kao klijenti/router.py Trezor — enkriptovano pre upload-a
    na Supabase Storage, nikad plaintext u bucket-u."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from security.crypto import _get_field_key

    key = _get_field_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(nonce, raw, None)
    return base64.urlsafe_b64encode(nonce + encrypted)


@router.post("/documents", status_code=202)
@limiter.limit("20/minute")
async def upload_intake_documents(
    request: Request,
    files: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """Batch upload — 202 + job_id po fajlu ODMAH, obrada (OCR/klasifikacija/
    ekstrakcija) u pozadini preko IntakeWorker-a (shared/intake_worker.py).
    Nikad sinhrono čeka tu obradu — to je cela poenta Postgres-backed
    queue-a (ADR-0002)."""
    if not files:
        raise HTTPException(status_code=422, detail="Nijedan fajl nije poslat.")

    supa = _get_supa()
    results = []

    for f in files:
        raw = await f.read()
        if len(raw) > _MAX_UPLOAD_BYTES:
            results.append({"filename": f.filename, "ok": False, "greska": "Fajl je prevelik (max 25MB)."})
            continue
        if len(raw) < 1:
            results.append({"filename": f.filename, "ok": False, "greska": "Fajl je prazan."})
            continue

        content_sha256 = hashlib.sha256(raw).hexdigest()
        storage_key = f"{user['user_id']}/{uuid.uuid4().hex}"

        try:
            encrypted = await asyncio.to_thread(_encrypt, raw)
            bucket = supa.storage.from_(_STORAGE_BUCKET)
            await asyncio.to_thread(
                lambda: bucket.upload(
                    path=storage_key,
                    file=encrypted,
                    file_options={"content-type": "application/octet-stream", "upsert": "false"},
                )
            )
        except Exception as exc:
            logger.error("[SMART_INTAKE] storage upload greška za %s: %s", f.filename, exc)
            results.append({"filename": f.filename, "ok": False, "greska": "Greška pri čuvanju fajla."})
            continue

        try:
            job_id = await intake_queue.enqueue_job(
                source="dropzone",
                content_sha256=content_sha256,
                storage_path=storage_key,
                uploaded_by=user["user_id"],
                kancelarija_id=None,  # Faza 1: office-scoped review queue (dizajn review §26.9) — nije reseno ovde
                idempotency_key=f"{user['user_id']}:{content_sha256}",
            )
        except Exception as exc:
            logger.error("[SMART_INTAKE] enqueue greška za %s: %s", f.filename, exc)
            results.append({"filename": f.filename, "ok": False, "greska": "Greška pri prijemu dokumenta."})
            continue

        # Best-effort follow-up upis (original_filename/mime_type) — NIJE deo
        # atomske enqueue_intake_job RPC transakcije (ADR-0001), namerno: to
        # bi značilo menjanje potpisa RPC-a koji je već pokrenut u produkciji
        # (migracija 073). Ova dva polja su pomoćna metapodatka za Fazu 1A
        # (extract() treba ekstenziju fajla), ne kritičan put za queue
        # pouzdanost — ako ovaj upis padne, posao i dalje postoji i biće
        # obrađen (extractor pada na .pdf kao razuman podrazumevani izbor).
        try:
            await asyncio.to_thread(
                lambda: supa.table("intake_jobs")
                    .update({"original_filename": f.filename, "mime_type": f.content_type})
                    .eq("id", job_id)
                    .execute()
            )
        except Exception as exc:
            logger.warning("[SMART_INTAKE] filename/mime upis neuspešan (non-fatal) za job=%s: %s", job_id[:8], exc)

        results.append({"filename": f.filename, "ok": True, "job_id": job_id})

    logger.info("[SMART_INTAKE] batch upload: %d fajlova, %d uspešno prijavljeno", len(files), sum(1 for r in results if r["ok"]))
    return {"rezultati": results, "ukupno": len(files)}


@router.get("/jobs/{job_id}")
@limiter.limit("60/minute")
async def intake_job_status(job_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Proizvodni Definition of Done (Faza 1A) — advokat u JEDNOM pozivu
    vidi: status posla, tip dokumenta, SVAKI izvučen podatak sa sopstvenom
    pouzdanošću (Confidence Graph), i — ako postoji nesigurnost — TAČNO
    koja polja treba da pogleda, ne ceo dokument. RLS (migracija 073) već
    ograničava na sopstvene poslove za ne-service_role upite; eksplicitna
    provera ovde daje jasnu 404 poruku umesto praznog reda."""
    res = await asyncio.to_thread(
        lambda: _get_supa().table("intake_jobs")
            .select("id, status, source, attempts, last_error, created_at, completed_at, original_filename")
            .eq("id", job_id)
            .eq("uploaded_by", user["user_id"])
            .maybe_single()
            .execute()
    )
    if not res or not res.data:
        raise HTTPException(status_code=404, detail="Posao nije pronađen.")
    job = res.data

    result = await intake_documents.get_job_result(job_id)
    document = result["document"]
    entities = result["entities"]
    review = result["review"]

    entiteti_view = [{
        "entity_id": e["id"],
        "entity_type": e["entity_type"],
        "value": e.get("corrected_value") or e["value"],
        "confidence": e["confidence"],
        "needs_review": (not e["reviewed"]) and e["confidence"] < intake_documents.AUTO_ACCEPT_THRESHOLD,
        "corrected": e["reviewed"],
    } for e in entities]

    return {
        "job": job,
        "dokument": {
            "tip": document["document_type"] if document else None,
            "tip_pouzdanost": document["classification_confidence"] if document else None,
            "ocr_koriscen": document["ocr_used"] if document else None,
        } if document else None,
        "entiteti": entiteti_view,
        "potrebna_provera": {
            "razlog": review["reason"],
            "polja": review["low_confidence_fields"],
        } if review else None,
    }


@router.post("/entities/{entity_id}/correct")
@limiter.limit("60/minute")
async def correct_entity(
    entity_id: str,
    request: Request,
    corrected_value: str = Body(..., embed=True),
    reason: str = Body(default=None, embed=True),
    error_source: str = Body(default=None, embed=True),
    user: dict = Depends(get_current_user),
):
    """Proizvodni Definition of Done: "ispravka za deset sekundi." Original
    vrednost se NIKAD ne briše (corrected_value je dodatak, ne prepisivanje)
    — i piše se u intake_processing_outcomes sa user_corrected=true, jer je
    ovo tačno podatak koji founder eksplicitno traži za buduće podešavanje
    pragova/heuristika. `reason` je OPCIONO (Validation Sprint, drugi krug
    feedbacka) — "Datum presude nije rok za žalbu" je mnogo korisniji
    materijal od gole činjenice da je polje ispravljeno, ali obavezno polje
    bi pretvorilo 10-sekundnu ispravku u formular — namerno ostaje
    opciono. `error_source` je takođe OPCIONO (LEC feedback, treći krug,
    2026-07-15) — kategorička klasifikacija KOG SLOJA je kriv (ocr/parser/
    regex/heuristics/llm/ground_truth/human_annotation/unknown), isti
    vokabular kao evaluation/lec/ i evaluation/hall_of_shame/ anotacije,
    tako da se posle šest meseci realne upotrebe može agregirati "gde
    stvarno gubimo vreme" umesto da svaki correction_reason ostane
    slobodan tekst koji se ne može grupisati."""
    try:
        result = await intake_documents.correct_entity(
            entity_id, corrected_value, user.get("email", user["user_id"]),
            reason=reason, error_source=error_source,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Stavka nije pronađena.")
    return result


@router.get("/admin/health")
@limiter.limit("30/minute")
async def intake_health(request: Request, user: dict = Depends(_require_founder)):
    """Operativna vidljivost (Faza 0 Definition of Done) — queue depth,
    najstariji pending, failed/retrying, outbox backlog, worker heartbeat-ovi.
    Sve IZVEDENO u letu (SQL view-ovi), nikad zaseban stored red."""
    queue_metrics, outbox_metrics, heartbeats = await asyncio.gather(
        intake_queue.get_queue_metrics(),
        intake_queue.get_outbox_metrics(),
        intake_queue.get_worker_heartbeats(),
    )
    return {
        "queue": queue_metrics,
        "outbox": outbox_metrics,
        "workeri": heartbeats,
    }


@router.get("/admin/accuracy")
@limiter.limit("30/minute")
async def intake_accuracy(request: Request, user: dict = Depends(_require_founder)):
    """Validation Sprint (founder, 2026-07-15) — Office Accuracy Dashboard.
    Ovo su OPERATIVNI KPI-jevi iz stvarne upotrebe (OCR uspešnost, review
    polja po dokumentu, stopa ispravki, LLM fallback %, vreme obrade) —
    NIJE isto što i tačnost naspram ground truth-a, za to postoji
    scripts/intake_accuracy_benchmark.py protiv evaluation/lec/. Iskreno
    prazno stanje ispod praga uzorka, nikad izmišljen broj koji izgleda
    precizan a nije (isti princip kao Revenue Intelligence)."""
    from shared.intake_accuracy import get_office_accuracy_kpis
    return await get_office_accuracy_kpis()


# ─── Finalize: Smart Intake job → stvaran predmet ──────────────────────────────
# Founder direktiva (2026-07-16): "Iz dokumenta" mora da zavrsi kreiranjem
# STVARNOG predmeta, ne samo prikazom klasifikacije. Faza 1A migracija
# (074) je namerno ostavila dokument nepovezan sa predmet_id — ovaj
# endpoint je tacka gde se ta veza konacno pravi, tek kad advokat potvrdi.

_DOC_TYPE_LABELS = {
    "lawsuit": "tužba", "response": "odgovor na tužbu", "appeal": "žalba",
    "judgment": "presuda", "contract": "ugovor", "invoice": "faktura",
    "power_of_attorney": "punomoćje", "evidence": "dokaz", "email": "email",
    "court_decision": "sudska odluka", "enforcement": "izvršenje",
    "legal_opinion": "pravno mišljenje", "other": "dokument",
}

_DEADLINE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEADLINE_DATE_SR_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


def _deadline_to_iso(value: str) -> Optional[str]:
    """shared/intake_extract.py::extract_deadline reuse-uje uploaded_doc/
    deadline_parser.py, koji vraća 'konkretan_datum' u DD.MM.YYYY formatu
    (srpska konvencija za prikaz) — NE ISO. Otkriveno 2026-07-16 pravim
    end-to-end testom: prvobitna verzija ovog fajla je prihvatala samo
    YYYY-MM-DD i cutke odbacivala svaki stvaran rok."""
    if not value:
        return None
    if _DEADLINE_DATE_RE.match(value):
        return value
    m = _DEADLINE_DATE_SR_RE.match(value)
    if m:
        dd, mm, yyyy = m.groups()
        return f"{yyyy}-{mm}-{dd}"
    return None


class FinalizeReq(BaseModel):
    naziv: Optional[str] = Field(default=None, max_length=200)
    klijent_strana: Optional[str] = Field(default=None, max_length=20)  # "plaintiff" | "defendant" | None
    klijent_ime_override: Optional[str] = Field(default=None, max_length=200)


def _compute_finalize_wait_s(job: dict) -> Optional[float]:
    """Faza 2.1 (90-dnevni plan, 2026-07-18) — sekunde izmedju job.completed_at
    i trenutka finalize poziva. None ako completed_at nedostaje (ne
    pretpostavlja 0 — odsustvo podatka nije isto sto i trenutna finalizacija)."""
    completed_at_raw = job.get("completed_at")
    if not completed_at_raw:
        return None
    try:
        from datetime import datetime, timezone
        completed_dt = datetime.fromisoformat(completed_at_raw.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - completed_dt).total_seconds()
    except Exception:
        return None


def _count_corrected_entities(entities: list[dict]) -> int:
    """Faza 2.1 — broj entiteta gde je advokat stvarno promenio vrednost pre
    finalize-a (corrected_value postavljen I razlicit od originalnog value),
    ne samo pregledan (reviewed)."""
    return sum(
        1 for e in entities
        if e.get("corrected_value") and e.get("corrected_value") != e.get("value")
    )


@router.post("/jobs/{job_id}/finalize")
@limiter.limit("20/minute")
async def finalize_intake_job(
    job_id: str,
    request: Request,
    body: FinalizeReq,
    user: dict = Depends(get_current_user),
):
    """Pretvara zavrsen Smart Intake posao u stvaran predmet — ovo je tacno
    obecanje iz UI-ja ("Otpremi tuzbu... i Vindex automatski kreira
    predmet"). Idempotentno: ako je posao vec finalizovan (intake_jobs.
    predmet_id popunjen), vraca postojeci predmet umesto da pravi duplikat."""
    uid = user["user_id"]
    supa = _get_supa()

    job_res = await asyncio.to_thread(
        lambda: supa.table("intake_jobs")
            .select("id, status, storage_path, original_filename, mime_type, predmet_id, completed_at")
            .eq("id", job_id)
            .eq("uploaded_by", uid)
            .maybe_single()
            .execute()
    )
    if not job_res or not job_res.data:
        raise HTTPException(status_code=404, detail="Posao nije pronađen.")
    job = job_res.data

    if job.get("predmet_id"):
        return {"ok": True, "predmet_id": job["predmet_id"], "already_finalized": True}

    if job["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Posao još nije obrađen (status: {job['status']}).")

    result = await intake_documents.get_job_result(job_id)
    document = result["document"]
    entities = result["entities"]
    if not document:
        raise HTTPException(status_code=409, detail="Klasifikacija nije dostupna za ovaj posao.")

    # Faza 2.1 instrumentacija (90-dnevni plan, 2026-07-18) — MERI, ne
    # pretpostavlja, da li advokat menja izvucene podatke pre finalize-a ili
    # samo potvrdjuje kako jeste. Rule B (ne menja UX/API), proizvodi Rule A
    # dokaz za buducu odluku o auto-finalize. Ne blokira finalize ako
    # bilo koji deo ovoga padne.
    finalize_wait_s = _compute_finalize_wait_s(job)
    entities_corrected = _count_corrected_entities(entities)

    value_map = {
        e["entity_type"]: (e.get("corrected_value") or e.get("value"))
        for e in entities
        if (e.get("corrected_value") or e.get("value"))
    }

    doc_type = document.get("document_type") or "other"
    tip_labela = _DOC_TYPE_LABELS.get(doc_type, "dokument")

    # ── Naziv predmeta ───────────────────────────────────────────────────────
    if body.naziv and body.naziv.strip():
        naziv = body.naziv.strip()[:200]
    elif value_map.get("plaintiff") and value_map.get("defendant"):
        naziv = f"{value_map['plaintiff']} protiv {value_map['defendant']}"[:200]
    elif value_map.get("case_number"):
        naziv = f"Predmet {value_map['case_number']}"[:200]
    elif job.get("original_filename"):
        naziv = Path(job["original_filename"]).stem[:200]
    else:
        naziv = f"Predmet iz dokumenta ({tip_labela})"

    opis_delovi = [f"Kreirano iz dokumenta ({tip_labela}) putem Smart Intake."]
    if value_map.get("case_number"):
        opis_delovi.append(f"Broj predmeta: {value_map['case_number']}")
    if value_map.get("court"):
        opis_delovi.append(f"Sud/organ: {value_map['court']}")
    if value_map.get("judge"):
        opis_delovi.append(f"Sudija: {value_map['judge']}")
    if value_map.get("law_cited"):
        opis_delovi.append(f"Zakon: {value_map['law_cited']}")
    if value_map.get("amount"):
        opis_delovi.append(f"Iznos: {value_map['amount']}")

    pred_r = await asyncio.to_thread(
        lambda: supa.table("predmeti").insert({
            "user_id": uid,
            "naziv":   naziv,
            "opis":    "\n".join(opis_delovi),
            "tip":     "opsti",
            "status":  "aktivan",
        }).execute()
    )
    if not pred_r.data:
        raise HTTPException(status_code=500, detail="Kreiranje predmeta nije uspelo.")
    predmet_id = pred_r.data[0]["id"]

    # ── Klijent (best-effort, ne obara finalize ako padne) ──────────────────
    klijent_ime = (body.klijent_ime_override or "").strip()
    if not klijent_ime and body.klijent_strana in ("plaintiff", "defendant"):
        klijent_ime = (value_map.get(body.klijent_strana) or "").strip()
    if klijent_ime:
        try:
            existing = await asyncio.to_thread(
                lambda: supa.table("klijenti")
                    .select("id")
                    .eq("user_id", uid)
                    .ilike("ime", klijent_ime[:100])
                    .neq("status", "soft_deleted")
                    .limit(1)
                    .execute()
            )
            if existing.data:
                klijent_id = existing.data[0]["id"]
            else:
                kl_res = await asyncio.to_thread(
                    lambda: supa.table("klijenti").insert({
                        "user_id": uid,
                        "ime":     klijent_ime[:100],
                        "tip":     "fizicko_lice",
                        "status":  "aktivan",
                    }).execute()
                )
                klijent_id = kl_res.data[0]["id"] if kl_res.data else None
            if klijent_id:
                # NAPOMENA (otkriveno 2026-07-16 pravim testom): predmet_klijenti
                # NEMA kolonu user_id, iako je routers/intake.py (stari wizard,
                # intake_kreiraj I intake_bulk_import) tu kolonu slao ovoj tabeli
                # ovaj citav niz vremena — PGRST204 na svakom pozivu, cutke
                # progutano. predmet_klijenti ima 0 redova u produkciji zbog
                # ovoga. Ne diram routers/intake.py (eksplicitna instrukcija),
                # ali OVAJ insert namerno ne salje user_id.
                await asyncio.to_thread(
                    lambda: supa.table("predmet_klijenti").insert({
                        "predmet_id":     predmet_id,
                        "klijent_id":     klijent_id,
                        "uloga_klijenta": "stranka",
                    }).execute()
                )
        except Exception as exc:
            logger.warning("[SMART_INTAKE] klijent link greška (non-fatal) predmet=%s: %s", predmet_id, exc)

    # ── Rok (ako je deadline izvučen sa dovoljnom pouzdanošću) ──────────────
    rok_dodat = False
    deadline_iso = _deadline_to_iso(value_map.get("deadline") or "")
    if deadline_iso:
        try:
            await asyncio.to_thread(
                lambda: supa.table("predmet_hronologija").insert({
                    "predmet_id": predmet_id,
                    "user_id":    uid,
                    "dogadjaj":   f"Rok — {tip_labela}",
                    "datum":      deadline_iso,
                    "datum_iso":  deadline_iso,
                    "vaznost":    "važan",
                    "akter":      "Smart Intake",
                }).execute()
            )
            rok_dodat = True
        except Exception as exc:
            logger.warning("[SMART_INTAKE] rok insert greška (non-fatal) predmet=%s: %s", predmet_id, exc)

    # ── Dokument: decrypt → tekst → chunk → Pinecone → predmet_dokumenti ────
    doc_linked = False
    try:
        from uploaded_doc.chunker import chunk_document
        from uploaded_doc.extractor import extract
        from uploaded_doc.ingest import ingest_session
        from uploaded_doc.session import generate_session_id
        from shared.intake_worker import worker as _intake_worker

        raw_bytes = await _intake_worker._download_and_decrypt(job["storage_path"])
        suffix = Path(job.get("original_filename") or "").suffix.lower() or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)
        try:
            text, is_scanned, ocr_used = await asyncio.to_thread(extract, tmp_path)
        finally:
            try:
                tmp_path.unlink()
            except Exception:
                pass

        if text and text.strip():
            source_meta = {
                "source_filename": job.get("original_filename") or "dokument",
                "source_format":   suffix.lstrip("."),
                "source_sha256":   hashlib.sha256(raw_bytes).hexdigest(),
                "is_scanned":      is_scanned,
                "session_id":      "__local__",
            }
            manifest = await asyncio.to_thread(chunk_document, text, source_meta)
            session_id = generate_session_id()
            pinecone_ok = True
            try:
                await asyncio.to_thread(ingest_session, manifest, session_id, namespace_prefix="pred_")
            except Exception as pe:
                logger.warning("[SMART_INTAKE] Pinecone ingest neuspešan (non-fatal) predmet=%s: %s", predmet_id, str(pe)[:150])
                pinecone_ok = False

            _dok_row_base = {
                "predmet_id":         predmet_id,
                "user_id":            uid,
                "naziv_fajla":        job.get("original_filename") or "dokument",
                "storage_path":       f"session/{session_id}",
                "pinecone_namespace": f"pred_{session_id}",
                "status":             "indeksirano" if pinecone_ok else "sacuvano",
                "velicina_kb":        max(1, len(raw_bytes) // 1024),
                "redni_broj":         1,
            }
            # tip_dokaza/klasifikovan_at (migracija 016) i tekst_sadrzaj su
            # opcioni po istom obrascu kao api.py predmet upload — probaj
            # najbogatiju varijantu prvo, padaj na osnovnu ako kolone/migracija
            # nedostaju, nikad ne izgubi ceo dokument zbog jedne kolone.
            dok_ins = None
            for extra in (
                {**_dok_row_base, "tip_dokaza": doc_type, "klasifikovan_at": "now()", "tekst_sadrzaj": text[:100_000]},
                {**_dok_row_base, "tekst_sadrzaj": text[:100_000]},
                _dok_row_base,
            ):
                try:
                    dok_ins = await asyncio.to_thread(
                        lambda r=extra: supa.table("predmet_dokumenti").insert(r).execute()
                    )
                    break
                except Exception as dok_exc:
                    logger.debug("[SMART_INTAKE] predmet_dokumenti insert varijanta neuspešna, probam sledeću: %s", dok_exc)
            doc_linked = bool(dok_ins and dok_ins.data)
    except Exception as exc:
        logger.warning("[SMART_INTAKE] dokument link/ingest greška (non-fatal) predmet=%s: %s", predmet_id, exc)

    # ── Case Genome auto-refresh (isti obrazac kao api.py predmet upload) ───
    if doc_linked:
        async def _genome_bg():
            await asyncio.sleep(3)
            try:
                from routers.case_dna import _run_genome_background
                await _run_genome_background(predmet_id, uid, None, trigger="smart_intake_finalize")
            except Exception as ge:
                logger.warning("[SMART_INTAKE] Genome auto-refresh greška: %s", ge)
        asyncio.create_task(_genome_bg())

    await asyncio.to_thread(
        lambda: supa.table("intake_jobs").update({"predmet_id": predmet_id}).eq("id", job_id).execute()
    )

    try:
        from routers.analytics import _track_event
        asyncio.create_task(_track_event(
            uid, "novi_predmet_flow", "smart_intake_completed",
            predmet_id=predmet_id,
            metadata={
                "job_id": job_id,
                "document_type": doc_type,
                # Faza 2.1 instrumentacija — vidi komentar iznad. finalize_wait_s
                # None ako completed_at nedostaje (ne pretpostavlja 0).
                "finalize_wait_s": round(finalize_wait_s, 1) if finalize_wait_s is not None else None,
                "entities_total": len(entities),
                "entities_corrected": entities_corrected,
            },
        ))
    except Exception:
        pass

    logger.info("[SMART_INTAKE] finalize job=%s -> predmet=%s klijent=%s rok=%s dok=%s",
                job_id[:8], predmet_id, bool(klijent_ime), rok_dodat, doc_linked)

    return {
        "ok":          True,
        "predmet_id":  predmet_id,
        "naziv":       naziv,
        "klijent_dodat": bool(klijent_ime),
        "rok_dodat":     rok_dodat,
        "dokument_povezan": doc_linked,
    }
