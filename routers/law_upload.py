# -*- coding: utf-8 -*-
"""
Vindex AI — routers/law_upload.py
Law database expansion: admin upload Serbian law PDFs → Pinecone zakoni_rs namespace.

POST /api/admin/law/upload   — upload PDF zakona, kreira ingest job u pozadini
GET  /api/admin/law/lista    — lista ingested zakona iz law_docs tabele
DELETE /api/admin/law/{id}   — označi zakon kao obrisan (soft delete)
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.law_upload")
router = APIRouter(tags=["law_upload"])

_CHUNK_SIZE    = 900
_CHUNK_OVERLAP = 180
_EMBED_BATCH   = 40
_UPSERT_BATCH  = 100
_MAX_PDF_MB    = 30
_SRLATMAP      = str.maketrans("žšćčđŽŠĆČĐ", "zsccdZSCCD")


# ─── Admin guard ──────────────────────────────────────────────────────────────

async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Samo za administratore.")
    return user


# ─── PDF extraction ───────────────────────────────────────────────────────────

def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            pass
    return "\n".join(parts)


# ─── Chunking ─────────────────────────────────────────────────────────────────

def _chunk(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(text) <= _CHUNK_SIZE:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - _CHUNK_OVERLAP
    return chunks


# ─── Embed + upsert (sync, runs in thread) ───────────────────────────────────

def _embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    resp = OpenAI().embeddings.create(model="text-embedding-3-large", input=texts)
    return [e.embedding for e in resp.data]


def _upsert(vectors: list[dict]) -> None:
    from pinecone import Pinecone
    pc  = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    idx = pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))
    idx.upsert(vectors=vectors, namespace="zakoni_rs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_ingest_sync(
    doc_id: str,
    naziv: str,
    broj_sl_glasnika: str,
    tekst: str,
    supa,
) -> dict:
    """Full pipeline: chunk → embed → upsert → update law_docs. Runs in thread."""
    safe_id = re.sub(r"[^A-Za-z0-9_]", "_", doc_id.translate(_SRLATMAP))[:60]
    chunks  = _chunk(tekst)
    if not chunks:
        _db_update(supa, doc_id, "failed", 0, 0, "Nema teksta u PDF-u.")
        return {"status": "failed", "razlog": "Nema teksta."}

    _db_update(supa, doc_id, "running", 0, len(chunks))

    vectors: list[dict] = []
    for i in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[i: i + _EMBED_BATCH]
        try:
            embs = _embed(batch)
        except Exception as exc:
            logger.error("[LAW_UPLOAD] embed greška batch %d: %s", i, exc)
            continue
        for j, emb in enumerate(embs):
            ci = i + j
            vectors.append({
                "id":       f"{safe_id}_c{ci}",
                "values":   emb,
                "metadata": {
                    "text":             chunks[ci],
                    "naziv_zakona":     naziv,
                    "broj_sl_glasnika": broj_sl_glasnika,
                    "chunk_index":      ci,
                    "doc_id":           doc_id,
                    "source":           "admin_law_upload",
                },
            })

    upserted = 0
    for i in range(0, len(vectors), _UPSERT_BATCH):
        try:
            _upsert(vectors[i: i + _UPSERT_BATCH])
            upserted += len(vectors[i: i + _UPSERT_BATCH])
        except Exception as exc:
            logger.error("[LAW_UPLOAD] upsert greška batch %d: %s", i, exc)

    if upserted > 0:
        _db_update(supa, doc_id, "done", upserted, len(chunks))
        logger.info("[LAW_UPLOAD] '%s' done: %d vektora upserted", naziv, upserted)
        return {"status": "done", "vektori": upserted}
    else:
        _db_update(supa, doc_id, "failed", 0, len(chunks), "Svi upsert pozivi neuspešni.")
        return {"status": "failed"}


def _db_update(supa, doc_id: str, status: str, vektori: int, ukupno_chunkova: int, greska: str = None):
    fields = {
        "status":          status,
        "vektori_upserted": vektori,
        "ukupno_chunkova": ukupno_chunkova,
    }
    if status == "done":
        fields["ingested_at"] = _now()
    if greska:
        fields["greska"] = greska
    try:
        supa.table("law_docs").update(fields).eq("id", doc_id).execute()
    except Exception as exc:
        logger.warning("[LAW_UPLOAD] db update greška: %s", exc)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/api/admin/law/upload", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def upload_zakon(
    request: Request,
    naziv:            str        = Form(..., max_length=300),
    broj_sl_glasnika: str        = Form(default="", max_length=100),
    pdf:              UploadFile = File(...),
    user: dict = Depends(_require_admin),
):
    """
    Law database expansion — upload PDF zakona.
    Parsira tekst, chunka, embeduje i upsertuje u Pinecone `default` namespace.
    Maksimalan fajl: 30 MB. Samo za administratore.
    """
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Samo PDF fajlovi su podržani.")

    pdf_bytes = await pdf.read()
    if len(pdf_bytes) > _MAX_PDF_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"PDF je prevelik (max {_MAX_PDF_MB} MB).")
    if len(pdf_bytes) < 500:
        raise HTTPException(status_code=422, detail="PDF je prazan ili oštećen.")

    doc_id = str(uuid.uuid4())
    supa   = _get_supa()

    # Persist record
    try:
        supa.table("law_docs").insert({
            "id":               doc_id,
            "naziv":            naziv.strip(),
            "broj_sl_glasnika": broj_sl_glasnika.strip(),
            "filename":         pdf.filename,
            "size_bytes":       len(pdf_bytes),
            "status":           "pending",
            "uploaded_by":      user.get("user_id", ""),
            "created_at":       _now(),
        }).execute()
    except Exception as exc:
        logger.error("[LAW_UPLOAD] insert greška: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri čuvanju zapisa.")

    # Extract text synchronously (fast, in-process)
    try:
        tekst = await asyncio.to_thread(_extract_pdf_text, pdf_bytes)
    except Exception as exc:
        _db_update(supa, doc_id, "failed", 0, 0, str(exc))
        raise HTTPException(status_code=422, detail=f"Ne mogu da pročitam PDF: {exc}")

    if len(tekst.strip()) < 100:
        _db_update(supa, doc_id, "failed", 0, 0, "PDF nema dovoljno teksta (skeniran?).")
        raise HTTPException(
            status_code=422,
            detail="PDF nema dovoljno teksta. Moguće da je skeniran — koristite PDF sa selektabilnim tekstom."
        )

    # Background ingest
    asyncio.create_task(
        asyncio.to_thread(_run_ingest_sync, doc_id, naziv.strip(), broj_sl_glasnika.strip(), tekst, supa)
    )

    logger.info("[LAW_UPLOAD] started: '%s' doc_id=%s size=%dKB", naziv, doc_id[:8], len(pdf_bytes) // 1024)
    return {
        "ok":     True,
        "doc_id": doc_id,
        "naziv":  naziv.strip(),
        "status": "pending",
        "napomena": "Ingest pokrenut u pozadini. Pratite status na /api/admin/law/lista.",
    }


@router.get("/api/admin/law/lista")
@limiter.limit("30/minute")
async def lista_zakona(
    request: Request,
    user: dict = Depends(_require_admin),
):
    """Lista svih uploadovanih zakona sa statusom ingesta."""
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("law_docs")
                     .select("id, naziv, broj_sl_glasnika, filename, size_bytes, status, vektori_upserted, ukupno_chunkova, created_at, ingested_at, greska")
                     .order("created_at", desc=True)
                     .limit(100)
                     .execute()
    )
    return {"zakoni": res.data or [], "total": len(res.data or [])}


@router.delete("/api/admin/law/{doc_id}", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def obrisi_zakon(
    request: Request,
    doc_id: str,
    user: dict = Depends(_require_admin),
):
    """Soft delete zakona (označava kao obrisan, NE briše iz Pinecone)."""
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("law_docs").select("id, naziv").eq("id", doc_id).maybe_single().execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Zakon nije pronađen.")
    await asyncio.to_thread(
        lambda: supa.table("law_docs").update({"status": "obrisan"}).eq("id", doc_id).execute()
    )
    logger.info("[LAW_UPLOAD] soft-deleted: '%s' id=%s", res.data.get("naziv"), doc_id[:8])
    return {"ok": True, "naziv": res.data.get("naziv")}
