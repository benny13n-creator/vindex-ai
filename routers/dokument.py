# -*- coding: utf-8 -*-
"""
Vindex AI — routers/dokument.py

F2.2 /api/dokument/upload
F2.3 /api/dokument/pitanje
F4.0 /api/dokument/analiza
F4.1 /api/dokument/rokovi
     /api/dokument/cleanup  (admin)
"""
import asyncio
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field, field_validator

from shared.deps import _deduct_credit, _get_supa, get_current_user, require_credits
from shared.rate import limiter

logger = logging.getLogger("vindex.api")
router = APIRouter()

_ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_ALLOWED_SUFFIXES  = {".pdf", ".docx"}
_MAX_UPLOAD_BYTES  = 10 * 1024 * 1024  # 10 MB
_MAX_DOC_PITANJE_LEN = 2000


# ── Models ────────────────────────────────────────────────────────────────────

class PitanjeDocRequest(BaseModel):
    session_id: str
    pitanje:    str
    history:    Optional[List[dict]] = None


class DokumentAnalizaReq(BaseModel):
    session_id: str = Field("", max_length=128)
    tekst:      str = Field("", max_length=80000)
    pitanje:    str = Field("", max_length=1000)

    @field_validator("session_id", "tekst", "pitanje")
    @classmethod
    def _trim(cls, v: str) -> str:
        return (v or "").strip()


class RokoviRequest(BaseModel):
    session_id:      str = ""
    tekst:           str = Field("", max_length=50000)
    datum_dokumenta: str = Field("", max_length=12)


# ── Helper ────────────────────────────────────────────────────────────────────

def _fetch_session_tekst(session_id: str) -> str:
    """Reconstruct document text from Pinecone tmp_<session_id> chunk metadata."""
    try:
        from uploaded_doc.ingest import _get_pinecone_index
        index = _get_pinecone_index()
        namespace = f"tmp_{session_id}"
        result = index.query(
            vector=[0.0] * 3072,
            top_k=1000,
            namespace=namespace,
            include_metadata=True,
        )
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
        if not matches:
            return ""
        matches_sorted = sorted(
            matches,
            key=lambda m: int((m.metadata or {}).get("chunk_index", 0))
        )
        texts = [(m.metadata or {}).get("text", "") for m in matches_sorted]
        return "\n\n".join(t for t in texts if t.strip())
    except Exception:
        logger.exception("[ROKOVI] Greška pri čitanju chunks iz Pinecone za session=%s", session_id)
        return ""


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/api/dokument/upload")
@limiter.limit("20/minute")
async def dokument_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_credits),
):
    """Upload a legal document (PDF or DOCX), chunk it, and ingest into a
    temporary Pinecone namespace. Returns session_id for Phase 2.3 retrieval."""
    import hashlib
    import tempfile
    from pathlib import Path as _Path

    from uploaded_doc.api_models import UploadResponse
    from uploaded_doc.chunker import chunk_document
    from uploaded_doc.cleanup import cleanup_expired
    from uploaded_doc.extractor import extract
    from uploaded_doc.ingest import ingest_session
    from uploaded_doc.session import generate_session_id, expires_at_iso, ttl_seconds_remaining

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    suffix = _Path(file.filename or "").suffix.lower()
    if file.content_type not in _ALLOWED_MIMES or suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Unsupported format")

    raw = await file.read()

    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = _Path(tmp.name)

        text, is_scanned, ocr_used = await asyncio.to_thread(extract, tmp_path)

        if is_scanned:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Skenirani ili nečitljivi PDF — OCR nije uspeo da prepozna tekst. "
                    "Pokušajte sa višom rezolucijom skeniranja (300 DPI ili više), "
                    "ili pošaljite digitalni PDF nastao direktno iz Word-a ili procesora teksta."
                ),
            )

        source_meta = {
            "source_filename": file.filename,
            "source_format":   suffix.lstrip("."),
            "source_sha256":   hashlib.sha256(raw).hexdigest(),
            "is_scanned":      is_scanned,
            "session_id":      "__local__",
        }
        manifest = await asyncio.to_thread(chunk_document, text, source_meta)

        if manifest.total_chunks == 0:
            raise HTTPException(status_code=422, detail="Empty document")

        session_id = generate_session_id()
        ttl_hours = 24
        try:
            count = await asyncio.to_thread(ingest_session, manifest, session_id, ttl_hours)
        except Exception as e:
            logger.error("[UPLOAD] ingest_session greška: %s", str(e), exc_info=True)
            raise HTTPException(status_code=500, detail=f"Greška pri obradi dokumenta: {str(e)}")

        exp_iso = expires_at_iso(ttl_hours)

        async def _background_cleanup():
            try:
                result = await asyncio.to_thread(cleanup_expired)
                logger.info("[UPLOAD] Background cleanup: %s", result)
            except Exception as _ce:
                logger.warning("[UPLOAD] Background cleanup failed: %s", _ce)

        asyncio.create_task(_background_cleanup())

        if not user.get("credit_pre_deducted"):
            await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return UploadResponse(
            session_id=session_id,
            chunk_count=count,
            chunk_mode_used=manifest.chunk_mode_used,
            article_labels_detected=manifest.article_labels_detected,
            expires_at=exp_iso,
            ttl_seconds=ttl_seconds_remaining(exp_iso),
            ocr_used=ocr_used,
            ocr_warning=(
                "Dokument je skeniran — tekst je prepoznat putem OCR-a. "
                "Kvalitet analize može biti niži nego kod digitalnog PDF-a."
            ) if ocr_used else "",
        )

    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


@router.post("/api/dokument/cleanup")
async def dokument_cleanup(
    x_admin_token: str = Header(default=""),
):
    """Admin endpoint: delete expired tmp_* Pinecone namespaces.
    Requires X-Admin-Token matching FOUNDER_TOKEN env var."""
    import os as _os
    from uploaded_doc.api_models import CleanupResponse
    from uploaded_doc.cleanup import cleanup_expired

    founder_token = _os.getenv("FOUNDER_TOKEN", "").strip()
    if not founder_token:
        raise HTTPException(status_code=503, detail="Cleanup endpoint not configured")
    if x_admin_token != founder_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await asyncio.to_thread(cleanup_expired, False)
    return CleanupResponse(
        namespaces_deleted=result["namespaces_deleted"],
        chunks_deleted=result["chunks_deleted"],
        namespaces_inspected=result["namespaces_inspected"],
    )


@router.post("/api/dokument/pitanje")
async def dokument_pitanje(body: PitanjeDocRequest, user: dict = Depends(require_credits)):
    """Ask a question about an uploaded document session."""
    from main import ask_agent
    from uploaded_doc.session import validate_session

    if not body.pitanje or not body.pitanje.strip():
        raise HTTPException(status_code=422, detail="Pitanje ne može biti prazno")
    if len(body.pitanje) > _MAX_DOC_PITANJE_LEN:
        raise HTTPException(status_code=422, detail="Pitanje je predugačko")
    if not body.session_id or not body.session_id.strip():
        raise HTTPException(status_code=422, detail="session_id je obavezan")

    session_valid = await asyncio.to_thread(validate_session, body.session_id)
    if not session_valid:
        raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")

    rezultat = await asyncio.to_thread(
        ask_agent,
        body.pitanje,
        body.history,
        [f"tmp_{body.session_id}"],
    )
    if not user.get("credit_pre_deducted"):
        await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
    return rezultat


@router.post("/api/dokument/analiza")
@limiter.limit("5/minute")
async def dokument_analiza(
    body: DokumentAnalizaReq,
    request: Request,
    user: dict = Depends(require_credits),
):
    """
    Forenzički Legal Audit — 10-slojni sistem.

    Prima session_id (uploadovani dokument) ILI direktni tekst.
    Segmentuje dokument, pokreće strukturiranu analizu, vraća JSON Executive Report.
    """
    from analiza.segmenter import segment_document
    from main import ask_analiza_v2
    from uploaded_doc.session import validate_session

    log_id = body.session_id or body.tekst[:200]
    logger.info("DokumentAnaliza [uid=%.8s]", user["user_id"])

    tekst = body.tekst
    if not tekst and body.session_id:
        session_ok = await asyncio.to_thread(validate_session, body.session_id)
        if not session_ok:
            raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")
        tekst = await asyncio.to_thread(_fetch_session_tekst, body.session_id)

    if not tekst or len(tekst.strip()) < 50:
        raise HTTPException(status_code=422, detail="Dokument je prazan ili previše kratak za analizu")

    try:
        segmented = await asyncio.to_thread(segment_document, tekst)
        logger.info("[ANALIZA] segment_document: type=%s segments=%d chars=%d",
                    segmented.doc_type, segmented.segment_count, segmented.char_count)
    except Exception as e:
        logger.error("[ANALIZA] segmentacija neuspešna: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri segmentaciji dokumenta")

    if segmented.char_count > 12000:
        logger.info("[ANALIZA] Dugačak dokument (%d ch) — primena multi-pass pristupa", segmented.char_count)

    rezultat = await asyncio.to_thread(ask_analiza_v2, segmented, body.pitanje)

    if rezultat.get("status") != "success":
        raise HTTPException(status_code=502, detail="AI analiza trenutno nedostupna. Pokušajte ponovo.")

    if not user.get("credit_pre_deducted"):
        preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
    else:
        preostalo = user.get("credits_remaining", 0)

    return {
        "status":           "success",
        "doc_type":         segmented.doc_type,
        "segment_count":    segmented.segment_count,
        "char_count":       segmented.char_count,
        "report":           rezultat["data"],
        "credits_remaining": max(preostalo, 0),
    }


@router.post("/api/dokument/rokovi")
@limiter.limit("20/minute")
async def dokument_rokovi(body: RokoviRequest, request: Request, user: dict = Depends(require_credits)):
    """Phase 4.1 — Ekstrakcija rokova + kalkulacija datuma. Ne troši kredit."""
    from uploaded_doc.deadline_parser import ekstrahuj_rokove, _extract_datum_dokumenta

    tekst = (body.tekst or "").strip()

    if not tekst and body.session_id:
        from uploaded_doc.session import validate_session
        session_ok = await asyncio.to_thread(validate_session, body.session_id)
        if not session_ok:
            raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")
        tekst = await asyncio.to_thread(_fetch_session_tekst, body.session_id)

    if not tekst:
        return {"rokovi": [], "ukupno": 0, "datum_dokumenta": None, "datum_dokumenta_izvor": None}

    datum_doc: Optional[str] = (body.datum_dokumenta or "").strip() or None
    datum_izvor: Optional[str] = None
    if datum_doc:
        datum_izvor = "korisnik"
    else:
        datum_doc = await asyncio.to_thread(_extract_datum_dokumenta, tekst)
        if datum_doc:
            datum_izvor = "auto"

    rokovi = await asyncio.to_thread(ekstrahuj_rokove, tekst, datum_doc)
    return {
        "rokovi":                rokovi,
        "ukupno":                len(rokovi),
        "datum_dokumenta":       datum_doc,
        "datum_dokumenta_izvor": datum_izvor,
    }
