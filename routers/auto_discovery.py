# -*- coding: utf-8 -*-
"""
Vindex AI — routers/auto_discovery.py

Auto Discovery: bulk PDF ingestion pipeline za Pinecone.
Administrator pokrece masovni uvoz pravnih tekstova (zakoni, sudska praksa i sl.)
u Pinecone vektorsku bazu.

SQL migracija (samo ispiši, pokrenuti rucno u Supabase Dashboard):

  CREATE TABLE IF NOT EXISTS discovery_queue (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    url          TEXT,
    tip          TEXT        NOT NULL,
    zemlja       TEXT        DEFAULT 'RS',
    namespace    TEXT,
    metapodaci   JSONB       DEFAULT '{}',
    status       TEXT        DEFAULT 'pending',
    greska       TEXT,
    processed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT now()
  );
  CREATE INDEX IF NOT EXISTS idx_dq_status ON discovery_queue(status);
  CREATE INDEX IF NOT EXISTS idx_dq_created ON discovery_queue(created_at DESC);

Endpoints:
  POST /api/discovery/pokreni      — pokrece background bulk ingestion (admin)
  POST /api/discovery/dodaj-url    — dodaje URL/zapis u discovery_queue (admin)
  POST /api/discovery/upload       — direktan upload jednog PDF-a (admin, sinhrono)
  GET  /api/discovery/status       — statistika queue tabele (admin)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from pypdf import PdfReader

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.auto_discovery")
router = APIRouter(tags=["auto_discovery"])

# ── Konstante ─────────────────────────────────────────────────────────────────

_MAX_PDF_MB    = 50
_EMBED_BATCH   = 100   # max vektora po OpenAI batch pozivu
_UPSERT_BATCH  = 100   # max vektora po Pinecone upsert pozivu

# ── Admin guard ───────────────────────────────────────────────────────────────

_DISCOVERY_ADMIN_EMAIL = os.getenv("DISCOVERY_ADMIN_EMAIL", "").strip().lower()


def _is_discovery_admin(email: str) -> bool:
    """Provera admin statusa: founder ili DISCOVERY_ADMIN_EMAIL env var."""
    e = (email or "").lower()
    if e in FOUNDER_EMAILS:
        return True
    if _DISCOVERY_ADMIN_EMAIL and e == _DISCOVERY_ADMIN_EMAIL:
        return True
    # Fallback: @vindex.rs domen
    if e.endswith("@vindex.rs"):
        return True
    return False


async def _require_discovery_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    if not _is_discovery_admin(user.get("email", "")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pristup odbijen. Samo administratori mogu pokretati Auto Discovery.",
        )
    return user


# ── Pinecone / OpenAI helpers ─────────────────────────────────────────────────

def _get_pinecone_index():
    from pinecone import Pinecone as PineconeClient
    pc = PineconeClient(api_key=os.environ["PINECONE_API_KEY"])
    return pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))


def _get_oai():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ── Core pipeline funkcije ────────────────────────────────────────────────────

def _parsuj_pdf(pdf_bytes: bytes) -> str:
    """Parsuje tekst iz PDF bajta pomocu pypdf."""
    reader = PdfReader(BytesIO(pdf_bytes))
    delovi: list[str] = []
    for page in reader.pages:
        try:
            tekst_stranice = page.extract_text() or ""
            if tekst_stranice.strip():
                delovi.append(tekst_stranice)
        except Exception as exc:
            logger.warning("[DISCOVERY] Stranica nije mogla biti procitana: %s", exc)
    return "\n".join(delovi)


def _chunk_text(
    tekst: str,
    max_tokens: int = 800,
    overlap: int = 100,
) -> list[str]:
    """
    Deli tekst na chunks od max_tokens reci sa overlap-om.
    Koristimo reci kao aproksimaciju tokena (MVP pristup).
    """
    reci = tekst.split()
    if not reci:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(reci):
        kraj = min(start + max_tokens, len(reci))
        chunk = " ".join(reci[start:kraj]).strip()
        if chunk:
            chunks.append(chunk)
        if kraj >= len(reci):
            break
        start = kraj - overlap  # nazad za overlap reci
    return chunks


def _embed_chunks(chunks: list[str]) -> list[list[float]]:
    """
    Embed-uje listu chunk-ova pomocu OpenAI text-embedding-3-large.
    Obradjuje u batchevima od max _EMBED_BATCH chunk-ova.
    """
    oai = _get_oai()
    svi_embeddings: list[list[float]] = []
    for i in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[i : i + _EMBED_BATCH]
        try:
            resp = oai.embeddings.create(
                model="text-embedding-3-large",
                input=batch,
            )
            svi_embeddings.extend([e.embedding for e in resp.data])
            logger.debug(
                "[DISCOVERY] Embed batch %d/%d — %d vektora",
                i // _EMBED_BATCH + 1,
                (len(chunks) - 1) // _EMBED_BATCH + 1,
                len(batch),
            )
        except Exception as exc:
            logger.error("[DISCOVERY] Embed greska za batch %d: %s", i, exc)
            # Popunjavamo praznim vektorima da indeksi ostanu uskladjeni
            svi_embeddings.extend([[0.0] * 3072] * len(batch))
    return svi_embeddings


def _upiši_pinecone(
    chunks: list[str],
    embeddings: list[list[float]],
    namespace: str,
    metapodaci: dict[str, Any],
) -> int:
    """
    Upisuje chunk-ove u Pinecone.
    ID = 'discovery_{sha256_prvih_64_znakova_chanka}'.
    Vraca broj uspesno upsertovanih vektora.
    """
    index = _get_pinecone_index()
    vektori: list[dict] = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        # Preskoci prazne embeddings (greska u embed fazi)
        if all(v == 0.0 for v in emb[:5]):
            continue
        chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()[:32]
        vec_id = f"discovery_{chunk_hash}"
        meta = {
            **metapodaci,
            "text": chunk[:1500],
            "chunk_index": i,
        }
        vektori.append({"id": vec_id, "values": emb, "metadata": meta})

    upsertovano = 0
    for i in range(0, len(vektori), _UPSERT_BATCH):
        batch = vektori[i : i + _UPSERT_BATCH]
        try:
            index.upsert(vectors=batch, namespace=namespace)
            upsertovano += len(batch)
            logger.debug(
                "[DISCOVERY] Pinecone upsert: namespace=%s batch=%d vektora",
                namespace,
                len(batch),
            )
        except Exception as exc:
            logger.error(
                "[DISCOVERY] Pinecone upsert greska (batch %d, namespace=%s): %s",
                i,
                namespace,
                exc,
            )
    return upsertovano


# ── Background task: bulk ingestion iz discovery_queue ───────────────────────

def _obradi_jedan_red(red: dict, supa) -> None:
    """
    Obraduje jedan red iz discovery_queue:
    1. Preuzima PDF sa URL-a (ako postoji)
    2. Parsuje tekst
    3. Chunking
    4. Embed
    5. Upsert u Pinecone
    6. Azurira status u tabeli
    """
    red_id = red["id"]
    url = red.get("url") or ""
    namespace = red.get("namespace") or f"zakon_{red.get('zemlja', 'RS').lower()}"
    metapodaci: dict = red.get("metapodaci") or {}
    metapodaci.setdefault("tip", red.get("tip", "zakon"))
    metapodaci.setdefault("zemlja", red.get("zemlja", "RS"))
    metapodaci.setdefault("izvor_url", url)

    try:
        # Preuzimanje PDF-a sa URL-a
        if not url:
            raise ValueError("URL nije naveden za ovaj zapis u redu.")

        import urllib.request as _ur
        with _ur.urlopen(url, timeout=30) as resp:
            pdf_bytes = resp.read()

        if len(pdf_bytes) < 200:
            raise ValueError("Preuzeti fajl je premali ili prazan.")

        # Parsiranje
        tekst = _parsuj_pdf(pdf_bytes)
        if len(tekst.strip()) < 100:
            raise ValueError("PDF nema dovoljno teksta (mozda je skeniran).")

        # Chunking
        chunks = _chunk_text(tekst)
        if not chunks:
            raise ValueError("Chunking nije proizveo nijedno parce teksta.")

        # Embed + upsert
        embeddings = _embed_chunks(chunks)
        upsertovano = _upiši_pinecone(chunks, embeddings, namespace, metapodaci)

        # Azuriraj status u bazi
        supa.table("discovery_queue").update({
            "status": "processed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "metapodaci": {**metapodaci, "chunks_upserted": upsertovano},
        }).eq("id", red_id).execute()

        logger.info(
            "[DISCOVERY] OK: id=%s namespace=%s chunks=%d upsertovano=%d",
            str(red_id)[:8],
            namespace,
            len(chunks),
            upsertovano,
        )

    except Exception as exc:
        greska_poruka = f"{type(exc).__name__}: {exc}"
        logger.error("[DISCOVERY] GRESKA za red %s: %s", str(red_id)[:8], greska_poruka)
        try:
            supa.table("discovery_queue").update({
                "status": "error",
                "greska": greska_poruka[:500],
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", red_id).execute()
        except Exception as db_exc:
            logger.error(
                "[DISCOVERY] Ne mogu da azuriram status greske za red %s: %s",
                str(red_id)[:8],
                db_exc,
            )


def _bulk_ingestion_sync(task_id: str) -> None:
    """
    Sinhrona funkcija koja se izvrsava u threadpool-u.
    Ucitava sve pending redove i obradjuje ih sekvencijalno.
    """
    supa = _get_supa()
    logger.info("[DISCOVERY] Bulk ingestion pokrenut. task_id=%s", task_id)

    try:
        res = (
            supa.table("discovery_queue")
            .select("id, url, tip, zemlja, namespace, metapodaci")
            .eq("status", "pending")
            .order("created_at")
            .limit(1000)
            .execute()
        )
        redovi = res.data or []
    except Exception as exc:
        logger.error("[DISCOVERY] Ne mogu da ucitam discovery_queue: %s", exc)
        return

    ukupno = len(redovi)
    logger.info("[DISCOVERY] Pronadjeno %d pending redova.", ukupno)

    if not ukupno:
        logger.info("[DISCOVERY] Nema pending redova. Zavrsetak.")
        return

    for i, red in enumerate(redovi, 1):
        logger.info(
            "[DISCOVERY] Obrada %d/%d: id=%s url=%s",
            i,
            ukupno,
            str(red.get("id", "?"))[:8],
            (red.get("url") or "")[:60],
        )
        _obradi_jedan_red(red, supa)

    logger.info("[DISCOVERY] Bulk ingestion zavrsen. Obradjeno: %d/%d", ukupno, ukupno)


# ── Pydantic modeli ───────────────────────────────────────────────────────────

class DodajUrlReq(BaseModel):
    url: str = Field(..., min_length=10, max_length=2000)
    tip: str = Field(..., pattern=r"^(zakon|praksa|kb)$")
    zemlja: str = Field(default="RS", max_length=10)
    namespace: Optional[str] = Field(default=None, max_length=100)
    metapodaci: dict[str, Any] = Field(default_factory=dict)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/discovery/pokreni", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
async def pokreni_discovery(
    request: Request,
    background_tasks: BackgroundTasks,
    user: dict = Depends(_require_discovery_admin),
):
    """
    Pokrecr async background task koji obradi sve PDF-ove u discovery_queue
    sa statusom 'pending'. Odmah vraca task_id i potvrdnu poruku.
    Samo za administratore.
    """
    task_id = str(uuid.uuid4())
    background_tasks.add_task(
        asyncio.to_thread,
        _bulk_ingestion_sync,
        task_id,
    )
    logger.info(
        "[DISCOVERY] Bulk ingestion zakazan. task_id=%s admin=%s",
        task_id,
        user.get("email", "?"),
    )
    return {
        "task_id": task_id,
        "poruka": "Bulk ingestion je pokrenut u pozadini. Pratite napredak u tabeli discovery_queue.",
        "napomena": "Koristite GET /api/discovery/status za pracenje statistike.",
    }


@router.post("/api/discovery/dodaj-url", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def dodaj_url(
    body: DodajUrlReq,
    request: Request,
    user: dict = Depends(_require_discovery_admin),
):
    """
    Dodaje jedan URL u discovery_queue radi kasnijeg bulk procesiranja.
    Samo za administratore.
    """
    supa = _get_supa()

    # Podrazumevani namespace na osnovu tipa i zemlje
    namespace = body.namespace or (
        f"zakon_{body.zemlja.lower()}"
        if body.tip == "zakon"
        else f"{body.tip}_{body.zemlja.lower()}"
    )

    try:
        res = await asyncio.to_thread(
            lambda: supa.table("discovery_queue").insert({
                "url":        body.url.strip(),
                "tip":        body.tip,
                "zemlja":     body.zemlja.upper(),
                "namespace":  namespace,
                "metapodaci": body.metapodaci,
                "status":     "pending",
            }).execute()
        )
        zapis_id = res.data[0]["id"] if res.data else None
    except Exception as exc:
        logger.error("[DISCOVERY] Greska pri dodavanju URL-a: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                "Greska pri dodavanju URL-a u redu. "
                "Pokrenite SQL migraciju za tabelu discovery_queue."
            ),
        )

    logger.info(
        "[DISCOVERY] URL dodat: id=%s tip=%s zemlja=%s url=%s",
        str(zapis_id)[:8] if zapis_id else "?",
        body.tip,
        body.zemlja,
        body.url[:60],
    )
    return {
        "ok": True,
        "id": zapis_id,
        "url": body.url,
        "tip": body.tip,
        "namespace": namespace,
        "status": "pending",
        "poruka": "URL je dodat u red. Pokrenite /api/discovery/pokreni za obradu.",
    }


@router.post("/api/discovery/upload", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def upload_pdf(
    request: Request,
    fajl: UploadFile = File(...),
    tip: str = Form(...),
    zemlja: str = Form(default="RS"),
    namespace: str = Form(...),
    user: dict = Depends(_require_discovery_admin),
):
    """
    Direktan upload jednog PDF-a. Obraduje se SINHRONO (pogodno za manje fajlove).
    Vraca broj chunk-ova i prvih 3 chunk-a kao preview.
    Samo za administratore.
    """
    # Validacija fajla
    if not (fajl.filename or "").lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Podrzani su samo PDF fajlovi.",
        )

    pdf_bytes = await fajl.read()
    if len(pdf_bytes) > _MAX_PDF_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF je prevelik (maksimum {_MAX_PDF_MB} MB).",
        )
    if len(pdf_bytes) < 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF je prazan ili ostecen.",
        )

    # Validacija tipa
    if tip not in ("zakon", "praksa", "kb"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tip mora biti: 'zakon', 'praksa' ili 'kb'.",
        )

    # Parsiranje teksta
    try:
        tekst = await asyncio.to_thread(_parsuj_pdf, pdf_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ne mogu da procitam PDF: {exc}",
        )

    if len(tekst.strip()) < 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "PDF nema dovoljno teksta. "
                "Moguce da je skeniran — koristite PDF sa selektabilnim tekstom."
            ),
        )

    # Chunking
    chunks = await asyncio.to_thread(_chunk_text, tekst)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chunking nije proizveo nijedno parce teksta.",
        )

    # Metapodaci za Pinecone
    metapodaci: dict[str, Any] = {
        "tip": tip,
        "zemlja": zemlja.upper(),
        "namespace": namespace,
        "fajl": fajl.filename or "",
        "source": "discovery_upload",
    }

    # Embed + upsert (sinhrono, u threadpool-u)
    try:
        embeddings = await asyncio.to_thread(_embed_chunks, chunks)
        upsertovano = await asyncio.to_thread(
            _upiši_pinecone, chunks, embeddings, namespace, metapodaci
        )
    except Exception as exc:
        logger.error("[DISCOVERY] Upload embed/upsert greska: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Greska pri upisivanju u Pinecone: {exc}",
        )

    logger.info(
        "[DISCOVERY] Upload ok: fajl=%s namespace=%s chunks=%d upsertovano=%d admin=%s",
        fajl.filename,
        namespace,
        len(chunks),
        upsertovano,
        user.get("email", "?"),
    )

    return {
        "ok": True,
        "fajl": fajl.filename,
        "namespace": namespace,
        "ukupno_chunks": len(chunks),
        "upsertovano": upsertovano,
        "preview_chunks": chunks[:3],
        "poruka": f"PDF je uspesno obradjen i upisano {upsertovano} vektora u Pinecone.",
    }


@router.get("/api/discovery/status")
@limiter.limit("30/minute")
async def discovery_status(
    request: Request,
    user: dict = Depends(_require_discovery_admin),
):
    """
    Vraca statistiku discovery_queue tabele:
    - ukupan broj redova
    - broj po statusu (pending / processed / error)
    - poslednjih 10 gresaka
    Samo za administratore.
    """
    supa = _get_supa()

    try:
        # Grupisanje po statusu
        svi = await asyncio.to_thread(
            lambda: supa.table("discovery_queue")
            .select("status")
            .execute()
        )
        redovi = svi.data or []
    except Exception as exc:
        logger.error("[DISCOVERY] Status greska: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                "Ne mogu da ucitam tabelu discovery_queue. "
                "Pokrenite SQL migraciju."
            ),
        )

    brojaci: dict[str, int] = {}
    for red in redovi:
        s = red.get("status", "nepoznat")
        brojaci[s] = brojaci.get(s, 0) + 1

    # Poslednjih 10 gresaka
    try:
        greske_res = await asyncio.to_thread(
            lambda: supa.table("discovery_queue")
            .select("id, url, greska, processed_at")
            .eq("status", "error")
            .order("processed_at", desc=True)
            .limit(10)
            .execute()
        )
        poslednje_greske = greske_res.data or []
    except Exception:
        poslednje_greske = []

    return {
        "ukupno": len(redovi),
        "po_statusu": {
            "pending":   brojaci.get("pending", 0),
            "processed": brojaci.get("processed", 0),
            "error":     brojaci.get("error", 0),
        },
        "ostali_statusi": {
            k: v for k, v in brojaci.items()
            if k not in ("pending", "processed", "error")
        },
        "poslednje_greske": poslednje_greske,
    }
