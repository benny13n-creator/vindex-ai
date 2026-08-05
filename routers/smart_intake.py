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

# Mission 001 / Night Shift M-001 (2026-08-02): this endpoint previously did
# NO suffix/extension validation at all -- any file was silently accepted,
# enqueued, and only failed deep in the background worker (shared/
# intake_worker.py) with an opaque error, several seconds/minutes after the
# lawyer already closed the upload dialog. Validating here means an
# unsupported file gets a clear, immediate rejection instead. Kept in sync
# with uploaded_doc/extractor.py's IMAGE_SUFFIXES + its .pdf/.docx/.txt
# dispatch -- .doc is deliberately NOT included (SEC-028: accepted-but-
# unhandled by the extractor, a separately tracked, pre-existing bug this
# mission does not touch).
_ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png"}


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
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
            results.append({
                "filename": f.filename, "ok": False,
                "greska": "Nepodržan format fajla. Podržano: PDF, DOCX, TXT, JPG, PNG.",
            })
            continue

        raw = await f.read()
        if len(raw) > _MAX_UPLOAD_BYTES:
            results.append({"filename": f.filename, "ok": False, "greska": "Fajl je prevelik (max 25MB)."})
            continue
        if len(raw) < 1:
            results.append({"filename": f.filename, "ok": False, "greska": "Fajl je prazan."})
            continue

        content_sha256 = hashlib.sha256(raw).hexdigest()
        idempotency_key = f"{user['user_id']}:{content_sha256}"

        # Program Intake Sprint 002 (2026-08-05) -- pre-check PRE storage
        # upload-a, ne posle. Fork C ovog sprinta je dokazao da je stari kod
        # sirotio novi enkriptovan blob na SVAKI obican sekvencijalni
        # duplikatni resubmit (ne samo kad enqueue RPC pukne) -- storage upis
        # bi uspeo pod svezim uuid4 kljucem, a onda bi enqueue_intake_job
        # samo vratio VEC POSTOJECI job_id bez ikad zabelezenog novog bloba
        # nigde (sirи od originalno-scope-ovanog INTAKE-002). Ovo je goli
        # SELECT (bez pisanja), pa ne treba RPC-nivo atomicnost -- to je
        # samo prečica da se izbegne uzaludan upload, ne stvarna zastita od
        # duplikacije (idempotency_key UNIQUE indeks + enqueue_intake_job RPC
        # ostaju stvarna zastita za pravu konkurentnu trku, obradjeno u
        # except bloku ispod).
        try:
            _existing_job = await asyncio.to_thread(
                lambda: supa.table("intake_jobs").select("id").eq("idempotency_key", idempotency_key).maybe_single().execute()
            )
        except Exception:
            _existing_job = None
        _existing_job_data = _existing_job.data if _existing_job else None
        if _existing_job_data:
            results.append({"filename": f.filename, "ok": True, "job_id": _existing_job_data["id"], "already_submitted": True})
            continue

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
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            logger.error("[SMART_INTAKE] enqueue greška za %s: %s", f.filename, exc)
            # Program Intake Sprint 002: kompenzujuce brisanje -- storage
            # upis iznad je vec uspeo, ali enqueue je pao (npr. prava
            # konkurentna trka na idempotency_key UNIQUE indeks -- gubitnik
            # ove trke prolazi kroz ovu granu, Fork C Faza 5 #2). Bez ovoga
            # blob ostaje trajno sirotce (INTAKE-002). Best-effort: ako i
            # brisanje padne, samo se loguje -- klijent i dalje dobija istu
            # honest "ok: False" poruku kao pre.
            try:
                await asyncio.to_thread(lambda: bucket.remove([storage_key]))
            except Exception as _ce:
                logger.warning("[SMART_INTAKE] orphan cleanup neuspesan za %s (key=%s): %s", f.filename, storage_key, _ce)
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
            .select("id, status, source, attempts, last_error, created_at, completed_at, original_filename, predmet_id")
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

    # Program Intake Sprint 003 (2026-08-05) -- Sprint 003 Fork A confirmed
    # a live, permanent, two-different-Serbian-labels contradiction: this
    # endpoint keeps serving intake_documents.document_type (Pipeline B's
    # ENGLISH-vocab staging value) indefinitely, even after finalize has
    # already written the real, Serbian-vocab predmet_dokumenti.tip_dokaza
    # for the case file -- and the frontend's own hardcoded translation map
    # renders THIS stale value during Smart Intake review. There is no
    # reliable join back to the specific predmet_dokumenti row from here
    # (no intake_job_id FK exists on that table -- tracked, unchanged,
    # INTAKE-003) to fetch and show the current canonical value directly,
    # so rather than guess via a fragile filename/order heuristic, this
    # response now honestly flags staleness and points the caller at the
    # real source of truth (the case file) instead of presenting a
    # possibly-superseded value as if it were still current.
    already_finalized = bool(job.get("predmet_id"))

    return {
        "job": job,
        "dokument": {
            "tip": document["document_type"] if document else None,
            "tip_pouzdanost": document["classification_confidence"] if document else None,
            "ocr_koriscen": document["ocr_used"] if document else None,
            "tip_moze_biti_zastareo": already_finalized,
            "napomena": (
                "Posao je vec finalizovan -- ovo je poslednja poznata klasifikacija PRE finalizacije, "
                "koja moze biti zamenjena ili ispravljena u samom predmetu. Za trenutnu klasifikaciju "
                "pogledajte dokument u predmetu (predmet_id ispod)."
            ) if already_finalized else None,
        } if document else None,
        "entiteti": entiteti_view,
        "potrebna_provera": {
            "razlog": review["reason"],
            "polja": review["low_confidence_fields"],
        } if review else None,
    }


@router.post("/jobs/{job_id}/review/resolve")
@limiter.limit("30/minute")
async def resolve_job_review(job_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Program Intake Sprint 004 (2026-08-05) -- kanonski i JEDINI nacin da
    advokat potvrdi da je pregledao nisko-pouzdanu klasifikaciju/
    ekstrakciju i da obrada sme automatski da nastavi (Faza 4: Automatic
    Pipeline Resume). Pre ovog sprinta, shared/intake_documents.py::
    resolve_review_queue_for_job je postojala ali je NIKAD nije pozivao
    nijedan kod put (Fork A, potvrdjeno repo-wide grep-om) -- posao je
    mogao zavrsiti u intake_review_queue-u i ostati tamo trajno, bez ijedne
    kapije za izlazak. Ova ruta JE ta kapija.

    Nastavak je AUTOMATSKI i IDEMPOTENTAN bez ijedne nove linije koda u
    finalize_intake_job: resolve_review() vraca intake_jobs.status sa
    'awaiting_review' na 'completed', sto finalize-ov VEC POSTOJECI status
    gate ('Posao jos nije obradjen') prirodno propusta -- lekar ponovo
    pozove POST /jobs/{job_id}/finalize (isti poziv kao i za bilo koji
    drugi zavrsen posao) i on nastavi TACNO odakle je stao: ne ponavlja
    OCR/klasifikaciju/ekstrakciju (vec upisani u intake_documents/
    extracted_entities), ne pravi nov dokument, ne pravi nov predmet, ne
    pravi nove vektore (finalize sam po sebi je vec idempotentan preko
    claim_intake_finalize RPC-a iz Sprint 002)."""
    uid = user["user_id"]
    supa = _get_supa()

    job_res = await asyncio.to_thread(
        lambda: supa.table("intake_jobs")
            .select("id, status, predmet_id")
            .eq("id", job_id)
            .eq("uploaded_by", uid)
            .maybe_single()
            .execute()
    )
    if not job_res or not job_res.data:
        raise HTTPException(status_code=404, detail="Posao nije pronađen.")
    job = job_res.data

    if job.get("predmet_id"):
        # Vec finalizovano -- review razresenje posle finalizacije je i
        # dalje bezopasno (istorijski zapis), ali nema vise nijedan status
        # da "otkljuca" -- vrati jasnu, ne-zbunjujucu poruku umesto tihog
        # no-op-a koji izgleda kao uspeh a nista se stvarno nije desilo.
        return {"ok": True, "already_finalized": True, "predmet_id": job["predmet_id"]}

    result = await intake_documents.resolve_review(job_id, user.get("email", uid))

    try:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            "dokument_review_resolved",
            user_id=uid,
            resource_type="intake_job",
            resource_id=job_id,
            ip=request.client.host if request.client else None,
            metadata={
                "prior_status": job.get("status"),
                "job_status_advanced": result["job_status_advanced"],
                "review_resolved_now": result["review_resolved_now"],
            },
        ))
    except Exception as ae:
        logger.warning("[SMART_INTAKE] dokument_review_resolved audit log greška: %s", ae)

    return {"ok": True, "already_finalized": False, **result}


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

    # Program Intake Sprint 004 (2026-08-05) -- ranije NIJEDAN audit poziv
    # ovde (Fork A §5, potvrdjeno) -- ovo JESTE covekova odluka (menja
    # trajno stanje ekstrakcije), pa mora imati audit trag po Fazi 5.
    # correlation_id se automatski nasledjuje iz request-scoped konteksta
    # (log_action's default, isti middleware kao svuda drugde) -- nista
    # dodatno nije potrebno da bi provenance nastavak radio.
    try:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            "entity_corrected",
            user_id=user["user_id"],
            resource_type="entity",
            resource_id=entity_id,
            ip=request.client.host if request.client else None,
            metadata={"entity_type": result["entity_type"], "reason": reason},
        ))
    except Exception as ae:
        logger.warning("[SMART_INTAKE] entity_corrected audit log greška: %s", ae)

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
    # Zero-Touch Case investigation (2026-08-03, BETA-002/Scenario B): before
    # this field existed there was NO way to finalize a second document into
    # a case a prior finalize call already created -- every finalize always
    # inserted a new `predmeti` row. A lawyer uploading N documents for one
    # client (the batch-upload contract already returns one job_id per file)
    # got N separate cases, not one organized case, with no merge feature to
    # recover afterward. Passing predmet_id attaches this job's document to
    # an already-finalized case instead of creating a new one.
    predmet_id: Optional[str] = Field(default=None, max_length=64)


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
    predmet_id popunjen), vraca postojeci predmet umesto da pravi duplikat.

    Program Intake Sprint 002 (2026-08-05): pre ove izmene, ta provera je
    citala kolonu koja se pisala tek NA KRAJU funkcije, bez zastite od
    konkurentnog poziva -- dva finalize poziva blizu jedan drugom su mogla
    oba proci proveru i oba izvrsiti citavu funkciju, tiho duplirajuci ceo
    predmet. Sada je zasticeno claim_intake_finalize() RPC-om (migracija
    092), istim SELECT...FOR UPDATE SKIP LOCKED obrascem kao claim_intake_job."""
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
        # Program Intake Sprint 004 (2026-08-05) -- ovaj gate je vec
        # postojao, ali poruka je bila ista za "jos se obradjuje" I za
        # "obradjeno, ali ceka covekovu potvrdu" (status='awaiting_review')
        # -- dve potpuno razlicite situacije za advokata (jedna: sacekaj;
        # druga: idi razresi review). Sada jasno razlikuje, i navodi tacnu
        # rutu (POST .../review/resolve) koja "otkljucava" nastavak --
        # ovaj if-blok i dalje JE ceo mehanizam blokade, nijedna nova
        # logika, samo precizna poruka.
        if job["status"] == "awaiting_review":
            raise HTTPException(
                status_code=409,
                detail="Klasifikacija/ekstrakcija zahteva potvrdu pre finalizacije — pozovite POST /api/smart-intake/jobs/{job_id}/review/resolve, zatim ponovo finalize.",
            )
        raise HTTPException(status_code=409, detail=f"Posao još nije obrađen (status: {job['status']}).")

    # Program Intake Sprint 002 (2026-08-05) -- ovaj deo funkcije je ranije
    # bio jedini "idempotentnost" mehanizam za citavu ovu funkciju: docstring
    # iznad tvrdi da je finalize idempotentan, ali provera "if job.get(
    # 'predmet_id')" iznad (400-401) citala je kolonu koja se pise TEK NA
    # KRAJU ove funkcije (posle predmet/klijent/rok/dokument/Pinecone upisa),
    # bez try/except-a. Dva finalize poziva za ISTI job_id dovoljno blizu
    # (dupli klik, ili frontend timeout retry dok prvi poziv jos radi na
    # serveru -- ova funkcija traje nekoliko sekundi i radi Pinecone upis)
    # oba citaju predmet_id=NULL, oba prolaze gornju proveru, i OBA izvrse
    # celu funkciju nezavisno -- tiho duplirajuci ceo predmet (slucaj, klijent,
    # rok, dokument, Pinecone vektori). Nezavisno potvrdjeno od STRANE 3 fork-a
    # istog dana (Fork A §C-bonus, Fork B §3.4, Fork C Faza 5 #4) -- najozbiljniji
    # nalaz ovog sprinta. Ispravka ogledava vec dokazan obrazac iz enqueue_
    # intake_job/claim_intake_job (migracija 073): atomski "proveri-i-zauzmi"
    # RPC (migracija 092), ne goli SELECT koji moze da se utrkuje sam sa sobom.
    claimed = await intake_queue.claim_finalize(job_id)
    if not claimed:
        # Nula redova znaci: predmet_id je vec postavljen (vec finalizovano),
        # ILI je drugi finalize poziv trenutno u toku (svez finalizing_at),
        # ILI konkurentna transakcija trenutno drzi lock nad redom. Ova tri
        # ishoda NISU isti odgovor -- moramo ponovo procitati red da ih
        # razlikujemo, ne pretpostaviti.
        refetch = await asyncio.to_thread(
            lambda: supa.table("intake_jobs").select("predmet_id").eq("id", job_id).maybe_single().execute()
        )
        existing_predmet_id = (refetch.data or {}).get("predmet_id") if refetch else None
        if existing_predmet_id:
            return {"ok": True, "predmet_id": existing_predmet_id, "already_finalized": True}
        raise HTTPException(
            status_code=409,
            detail="Finalizacija je već u toku za ovaj posao — pokušajte ponovo za par sekundi.",
        )

    result = await intake_documents.get_job_result(job_id)
    document = result["document"]
    entities = result["entities"]
    if not document:
        raise HTTPException(status_code=409, detail="Klasifikacija nije dostupna za ovaj posao.")

    # Program Intake Sprint 003 (2026-08-05) -- result["review"] je ranije
    # bio ucitan a NIKAD procitan (Sprint 003 Fork C §1.6a) -- finalize nije
    # imao NIKAKAV nacin da zna da li je Pipeline B-ova klasifikacija bila
    # ispod AUTO_ACCEPT_THRESHOLD. Ovo je tacno "trece stanje" koje misija
    # zabranjuje: dokument tiho pogodjen umesto poslat u Review Required.
    # classification_uncertain postaje ulaz u dve odluke ispod: (1) da li
    # dozvoliti Evidence Vault-ovom confidence-slepom klasifikatoru da tiho
    # prepise ovu vec-oznacenu-kao-nesigurnu vrednost (ne dozvoljavamo — v.
    # napomenu kod _evidence_classify_bg), (2) da li ukljuciti eksplicitan
    # signal u finalize odgovoru (ukljucujemo — jedini trenutak kad advokat
    # sigurno gleda ovaj ekran).
    review = result["review"]
    low_confidence_fields = (review or {}).get("low_confidence_fields") or []
    classification_uncertain = bool(review) and "document_type" in low_confidence_fields

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

    # ── Predmet: prikaci na postojeci (Scenario B) ili napravi novi ─────────
    attach_existing = bool(body.predmet_id)
    if attach_existing:
        existing_pred = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv")
                .eq("id", body.predmet_id)
                .eq("user_id", uid)
                .maybe_single().execute()
        )
        if not existing_pred or not existing_pred.data:
            raise HTTPException(status_code=404, detail="Predmet za prikačivanje nije pronađen.")
        predmet_id = existing_pred.data["id"]
        naziv = existing_pred.data.get("naziv") or ""
    else:
        # ── Naziv predmeta ───────────────────────────────────────────────
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

        # Zero-Touch Case investigation (2026-08-03, BETA-002/Scenario 5):
        # POST /api/intake/conflict-check (routers/intake.py) exists and
        # works, but only in the older name-first CRM Intake Wizard flow --
        # this document-first flow never called it, so a case could be
        # created here with a conflict of interest never having been
        # checked, silently, every time. Extracted party names ARE already
        # available in value_map at exactly this point. Deliberately
        # non-blocking (surfaces a proactive_alerts entry, does not fail or
        # delay finalize) -- this endpoint is a promise of automatic case
        # creation, and a false-positive name match should never silently
        # block a lawyer from opening a real case. The lawyer sees the
        # alert immediately inside the case that was just created either
        # way; the actual "should I decline this client" judgment remains
        # the lawyer's, per the existing endpoint's own BLOKIRAJUCI wording.
        protivna_strana_val = ""
        if body.klijent_strana == "plaintiff":
            protivna_strana_val = (value_map.get("defendant") or "").strip()
        elif body.klijent_strana == "defendant":
            protivna_strana_val = (value_map.get("plaintiff") or "").strip()

        async def _conflict_check_bg():
            try:
                from routers.intake import _run_conflict_check
                result = await _run_conflict_check(uid, klijent_ime, "", protivna_strana_val, "")
                if result.get("conflict_detected"):
                    opisi = "; ".join(c.get("opis", "") for c in result.get("conflicts", [])[:5])
                    from shared.proactive_alerts import create_proactive_alert
                    await create_proactive_alert(
                        supa,
                        user_id=uid,
                        predmet_id=predmet_id,
                        tip="sukob_interesa",
                        naslov="BLOKIRAJUĆI sukob interesa" if result.get("has_blocker") else "Mogući sukob interesa",
                        opis=f"{result.get('preporuka', '')} {opisi}".strip()[:2000],
                        urgentnost="hitna" if result.get("has_blocker") else "normalna",
                    )
            except Exception as cce:
                logger.warning("[SMART_INTAKE] Conflict-check greška (non-fatal) predmet=%s: %s", predmet_id, cce)
        asyncio.create_task(_conflict_check_bg())

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
            # Institutional Learning & RAG Audit (2026-07-26) #1: isti
            # vlasnik-znanja namespace kao api.py's predmet upload (v. tamo
            # za punu napomenu) -- zamenjuje pred_{session_id}.
            from shared.kancelarija_utils import get_kancelarija_id as _get_kid, rag_owner_namespace as _rag_ns
            from shared.vector_origin import ORIGIN_CLIENT_DOC, now_iso as _now_iso
            _kancelarija_id = await _get_kid(supa, uid)
            _owner_ns = _rag_ns(uid, _kancelarija_id)
            try:
                await asyncio.to_thread(
                    ingest_session, manifest, session_id,
                    namespace_override=_owner_ns,
                    extra_metadata={
                        "predmet_id": predmet_id,
                        "kancelarija_id": _kancelarija_id or "",
                        "type": "case_doc",
                        # Institutional Memory V2 (2026-07-26) STUB 2/3.
                        "origin": ORIGIN_CLIENT_DOC,
                        "parent_id": "",
                        "origin_chain": [ORIGIN_CLIENT_DOC],
                        "created_at": _now_iso(),
                        "golden_template": False,
                    },
                )
            except Exception as pe:
                logger.warning("[SMART_INTAKE] Pinecone ingest neuspešan (non-fatal) predmet=%s: %s", predmet_id, str(pe)[:150])
                pinecone_ok = False

            # Zero-Touch Case investigation (2026-08-03, BETA-002/Scenario B):
            # bilo je hardkodovano na 1 -- bezopasno dok je svaki finalize
            # uvek pravio NOV predmet (tacno jedan dokument po predmetu), ali
            # cim je moguce prikaciti vise dokumenata na ISTI predmet (gore),
            # svaki naredni dokument bi kolidirao na redni_broj=1, sto bi
            # ucinilo Genome-ovo .order("redni_broj") sortiranje besmislenim.
            _postojeci_redni = await asyncio.to_thread(
                lambda: supa.table("predmet_dokumenti")
                    .select("redni_broj").eq("predmet_id", predmet_id)
                    .order("redni_broj", desc=True).limit(1).execute()
            )
            _sledeci_redni = ((_postojeci_redni.data or [{}])[0].get("redni_broj") or 0) + 1 \
                if _postojeci_redni.data else 1

            _dok_row_base = {
                "predmet_id":         predmet_id,
                "user_id":            uid,
                "naziv_fajla":        job.get("original_filename") or "dokument",
                "storage_path":       f"session/{session_id}",
                "pinecone_namespace": _owner_ns,
                "status":             "indeksirano" if pinecone_ok else "sacuvano",
                "velicina_kb":        max(1, len(raw_bytes) // 1024),
                "redni_broj":         _sledeci_redni,
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

        # Operation Lawyer Zero, LZ-002 (2026-08-03): Evidence Vault's real
        # classifier (routers/evidence.py::klasifikuj_i_sacuvaj -- richer
        # tip_dokaza vocabulary, pravni_elementi, ai_tags, kljucne_cinjenice
        # -> predmet_dokazi) was never auto-triggered on ingestion; its only
        # entry point was the manual /reklasifikuj action. This also starved
        # services/risk_engine.py's missing-document detector, the platform's
        # sole deterministic "next action" algorithm (routers/matter_intel.py),
        # which reads tip_dokaza and compares it against shared/constants.py's
        # EXPECTED_DOCS -- and matters more than it first appears: the coarse
        # tip_dokaza this finalize path already writes above (from
        # shared/intake_classify.py's own classifier) uses a DIFFERENT
        # vocabulary ("lawsuit"/"judgment"/etc.) than EXPECTED_DOCS expects
        # ("sudska_odluka"/"podnesak"/etc.) -- so that field was already being
        # populated, just with values that could never match. Same
        # vocabulary-fragmentation defect shape as LZ-001's `vaznost` finding,
        # one field over. klasifikuj_i_sacuvaj's own UPDATE (routers/evidence.py)
        # corrects tip_dokaza to the right vocabulary and adds the richer
        # fields, exactly matching the manual /reklasifikuj pattern -- no new
        # classification logic written, only the missing auto-trigger added.
        # Deliberately does NOT call UsageService.consume: this is a system-
        # initiated background enrichment step, not a lawyer-initiated action,
        # so it should not silently consume a billing credit the way the
        # manual endpoint does.
        # Program Intake Sprint 003 (2026-08-05) -- ovaj task se RANIJE
        # pokretao bezuslovno, svaki put, bez obzira da li je Pipeline B-ova
        # klasifikacija bila ispod AUTO_ACCEPT_THRESHOLD i vec cekala u
        # intake_review_queue. To je znacilo da je jedina tacka u citavom
        # sistemu koja ispravno prepoznaje "nisam siguran" (Confidence Graph)
        # bila tiho prepisana klasifikatorom koji NEMA confidence polje
        # uopste (routers/evidence.py::_klasifikuj_dokument — Sprint 003
        # Fork C §1.2/§1.6b: potvrdjeno, nema numericku vrednost nigde u
        # svom izlazu). Netacna posledica: cak i kad je sistem ispravno
        # rekao "nisam siguran," ta neizvesnost NIKAD ne bi stigla do
        # trajnog zapisa — tiho zamenjena "sigurnijim"-izgledajucim (ali
        # jednako negrundovanim) nagadjanjem, tacno "trece stanje" koje
        # ova misija zabranjuje. Sada: prepisivanje se preskace kad je
        # document_type vec oznacen kao nesiguran — vrednost koju je
        # finalize upisao iznad (Pipeline B-ov original) ostaje, i
        # klasifikacija_nesigurna=True u odgovoru ispod cini tu neizvesnost
        # vidljivom advokatu, umesto da je sakrije iza lazno-sigurnog
        # drugog nagadjanja. LZ-002-ov ispravan cilj (engleski->srpski
        # vokabular popravka za EXPECTED_DOCS) i dalje radi za VECINU
        # dokumenata — samo za one vec-oznacene-kao-nesigurne se preskace.
        if not classification_uncertain:
            async def _evidence_classify_bg():
                try:
                    from routers.evidence import klasifikuj_i_sacuvaj
                    dokument_id = dok_ins.data[0]["id"]
                    await asyncio.to_thread(
                        klasifikuj_i_sacuvaj, predmet_id, dokument_id,
                        job.get("original_filename") or "dokument", text, uid,
                    )
                except Exception as ce:
                    logger.warning("[SMART_INTAKE] Evidence Vault auto-klasifikacija greška: %s", ce)
            asyncio.create_task(_evidence_classify_bg())
        else:
            logger.info(
                "[SMART_INTAKE] dok=%s klasifikacija nesigurna (document_type u low_confidence_fields) -- preskacem Evidence Vault auto-prepisivanje, ostaje Review Required",
                (dok_ins.data[0]["id"] if dok_ins and dok_ins.data else "?"),
            )

    # Program Intake Sprint 002 -- ova linija je i dalje jedini upis koji
    # trajno "zatvara" finalizaciju (isti field kao pre), ali sada je
    # zasticena claim_intake_finalize() zauzecem iznad: ako OVAJ upis padne,
    # finalizing_at ostaje postavljen i nijedan konkurentan poziv u sledecih
    # ~120s nece moci ponovo da pokrene celu funkciju (claim ce vratiti 0
    # redova, tretirano kao "u toku"). Tek posle isteka tog prozora bi novi
    # pokusaj mogao da ponovi ceo tok -- suzeno sa "bilo kad, bilo koji
    # konkurentan retry" (pre ove izmene) na "samo ako bas ovaj upis padne I
    # sledeci pokusaj sacheka >120s", sto pokriva dominantan trigger (dupli
    # klik / brz timeout-retry) bez pretvaranja u punu transakciju koju
    # supabase-py ne izlaze (v. Fork B §3.2).
    try:
        await asyncio.to_thread(
            lambda: supa.table("intake_jobs").update({"predmet_id": predmet_id}).eq("id", job_id).execute()
        )
    except Exception as fe:
        logger.error(
            "[SMART_INTAKE] finalize marker upis neuspesan job=%s predmet=%s -- claim ostaje rezervisan ~120s, zatim ponovo obradiv: %s",
            job_id[:8], predmet_id, fe,
        )
        raise

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
        # Program Intake Sprint 003 (2026-08-05) -- eksplicitan signal da je
        # tip_dokaza klasifikacija ispod AUTO_ACCEPT_THRESHOLD (Sprint 003
        # Fork C's headline finding) -- "Review Required" mora biti vidljivo
        # stanje, ne tiho zakopano u endpoint-u koji niko posle finalize-a
        # ne posecuje (GET /jobs/{id}, jedini ranije citalac ovog signala).
        "klasifikacija_nesigurna": classification_uncertain,
        "nesigurna_polja": low_confidence_fields if classification_uncertain else [],
    }
