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

from security.html_sanitize import sanitize_user_input
from shared.deps import _get_supa, get_current_user
from shared.llm_retry import llm_retry
from shared.rate import limiter
from shared.permissions import PermissionService
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService

logger = logging.getLogger("vindex.api")
router = APIRouter()

_ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_ALLOWED_SUFFIXES  = {".pdf", ".docx"}
_MAX_UPLOAD_BYTES  = 25 * 1024 * 1024  # 25 MB
_MAX_DOC_PITANJE_LEN = 2000


# ── Models ────────────────────────────────────────────────────────────────────

class PitanjeDocRequest(BaseModel):
    session_id:       str
    pitanje:          str
    history:          Optional[List[dict]] = None
    namespace_prefix: Optional[str] = "tmp_"

    @field_validator("pitanje")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        return sanitize_user_input((v or "").strip()) or ""


class DokumentAnalizaReq(BaseModel):
    session_id: str = Field("", max_length=128)
    tekst:      str = Field("", max_length=80000)
    pitanje:    str = Field("", max_length=1000)

    @field_validator("session_id", "tekst", "pitanje")
    @classmethod
    def _trim(cls, v: str) -> str:
        return sanitize_user_input((v or "").strip()) or ""


class RokoviRequest(BaseModel):
    session_id:      str = ""
    tekst:           str = Field("", max_length=50000)
    datum_dokumenta: str = Field("", max_length=12)


# ── AI klasifikacija dokaza ───────────────────────────────────────────────────

@llm_retry
def _pozovi_klasifikacija_api(client, prompt: str):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.2,
        response_format={"type": "json_object"},
    )


async def _klasifikuj_dokaz(tekst: str, filename: str) -> dict:
    """GPT-4o-mini klasifikuje dokument kao pravni dokaz."""
    try:
        import json, os
        from openai import OpenAI

        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        preview = tekst[:2000] if tekst else ""

        prompt = (
            "Analiziraj ovaj pravni dokument i vrati JSON sa tacno ovim poljima:\n"
            '{"tip_dokaza":"ugovor|presuda|resenje|zapisnik|izvestaj|priznanica|dopis|punomocje|ostalo",'
            '"oblast_prava":"gradjansko|krivicno|radno|upravno|privredno|poresko|porodicno|nasledno|ostalo",'
            '"kljucne_odredbe":["clan X zakona Y"],'
            '"snaga_dokaza":"visoka|srednja|niska",'
            '"preporuka":"Kratak savet advokatu (1 recen.)",'
            '"tagovi":["tag1","tag2","tag3"]}\n\n'
            f"Naziv fajla: {filename}\n"
            f"Sadrzaj (prvih 2000 znakova):\n{preview}\n\n"
            "Odgovori SAMO JSON-om, bez objasnjenja."
        )

        resp = await asyncio.to_thread(_pozovi_klasifikacija_api, oai, prompt)
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        _sentry_capture(e)
        logger.warning("Klasifikacija dokaza greška: %s", e)
        return {
            "tip_dokaza": "ostalo",
            "oblast_prava": "ostalo",
            "kljucne_odredbe": [],
            "snaga_dokaza": "niska",
            "preporuka": "Nije moguće automatski klasifikovati dokument.",
            "tagovi": [],
        }


# ── Helper ────────────────────────────────────────────────────────────────────

def _fetch_session_tekst(session_id: str, namespace_prefix: str = "tmp_") -> str:
    """Reconstruct document text from Pinecone <prefix><session_id> chunk metadata.
    Tries given prefix first; if empty, falls back to the other prefix."""
    try:
        from uploaded_doc.ingest import _get_pinecone_index
        index = _get_pinecone_index()

        def _query_ns(ns: str) -> str:
            result = index.query(
                vector=[0.0] * 3072,
                top_k=1000,
                namespace=ns,
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

        # S6B Phase A (2026-08-09): DECLARED namespace must equal ACTUAL namespace.
        #
        # This used to fall back to the OTHER prefix when the declared one
        # returned nothing. tmp_<id> and pred_<id> are different ID spaces --
        # tmp_ is an ephemeral uuid4 upload session with a 24h TTL and no row
        # anywhere, pred_ is a real predmeti.id -- so the fallback could hand an
        # AI call text from a namespace the request never asked for.
        #
        # That is an audit-integrity defect, not a convenience: once a caller
        # binds provenance to the declared namespace, a silent cross-read means
        # the record can claim the AI worked on case X while the text came from
        # somewhere else. Better an empty result with a truthful identity than a
        # populated one with a false subject.
        #
        # Fail closed: return empty and let the caller's existing 404/422 handle
        # it, exactly as it already does when a namespace is genuinely empty.
        # The error contract is unchanged; only the silent cross-read is gone.
        return _query_ns(f"{namespace_prefix}{session_id}")
    except Exception:
        logger.exception("[ROKOVI] Greška pri čitanju chunks iz Pinecone za session=%s", session_id)
        return ""


async def _verify_pred_namespace_ownership(session_id: str, ns_prefix: str, uid: str) -> None:
    """LAMBDA008-SEC-001 fix: pred_<predmet_id> Pinecone namespaces never expire
    (see uploaded_doc/session.py::validate_session docstring), so validate_session
    alone (namespace-existence + TTL only) lets any authenticated user read any
    other firm's case documents forever by guessing/leaking a predmet_id. Raises
    404 (not 403, to avoid confirming existence of another firm's case) if the
    caller doesn't own the referenced predmet.

    Final Beta Gate F1 (MEDIUM): tmp_ namespaces got the identical class of
    check here for the first time -- previously this function explicitly
    no-op'd for anything other than "pred_" (deliberately, per the prior fix's
    own comment), leaving tmp_ gated by session_id entropy alone (a real
    uuid4, not a guessable id -- lower risk than pred_'s sequential-feeling
    ids, but not zero: a leaked session_id, e.g. via browser history/logs/a
    shared screenshot, let ANY authenticated user query another user's
    uploaded document for the rest of its 24h TTL). Vectors ingested before
    this fix carry no owner_user_id -- fails closed (404) on a missing/
    mismatched owner rather than trusting an unverifiable legacy vector; the
    24h TTL bounds this to a one-time transition window, not a standing gap."""
    if ns_prefix not in ("pred_", "tmp_"):
        return
    if ns_prefix == "pred_":
        supa = _get_supa()
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("id", session_id).eq("user_id", uid).limit(1).execute()
        )
        if not (r.data or []):
            raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")
        return

    # ns_prefix == "tmp_"
    try:
        from uploaded_doc.ingest import _get_pinecone_index
        index = await asyncio.to_thread(_get_pinecone_index)
        result = await asyncio.to_thread(
            lambda: index.query(
                vector=[0.0] * 3072, top_k=1, namespace=f"tmp_{session_id}", include_metadata=True,
            )
        )
        matches = result.matches if hasattr(result, "matches") else result.get("matches", [])
    except Exception:
        logger.exception("[SEC] tmp_ namespace ownership check greška za session=%s", session_id)
        raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")
    if not matches or (matches[0].metadata or {}).get("owner_user_id") != uid:
        raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/api/dokument/upload")
@limiter.limit("20/minute")
async def dokument_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(PermissionService.require("document_analysis")),
):
    """Upload a legal document (PDF or DOCX), chunk it, and ingest into a
    temporary Pinecone namespace. Returns session_id for Phase 2.3 retrieval."""
    import hashlib
    import tempfile
    from pathlib import Path as _Path

    from uploaded_doc.api_models import UploadResponse
    from uploaded_doc.chunker import chunk_document
    from uploaded_doc.cleanup import cleanup_expired
    from uploaded_doc.extractor import DocumentSafetyLimitExceeded, extract
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

        try:
            text, is_scanned, ocr_used, _pages, _ocr_conf = await asyncio.to_thread(extract, tmp_path)
        except DocumentSafetyLimitExceeded:
            raise HTTPException(
                status_code=413,
                detail="Fajl je odbijen — sadržaj posle raspakivanja prelazi bezbednosni limit.",
            )

        if is_scanned:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Skenirani PDF — automatski OCR nije uspeo da prepozna tekst. "
                    "Mogući razlozi: loš kvalitet skeniranja, rukopisni tekst, ili nestandardni font. "
                    "Preporuke: (1) Ponovo skenirajte u 300 DPI ili višoj rezoluciji, "
                    "(2) Koristite digitalni PDF nastao direktno iz Word-a ili suda, "
                    "(3) Ručno kopirajte i nalepite tekst u polje za analizu."
                ),
            )

        source_meta = {
            "source_filename": file.filename,
            "source_format":   suffix.lstrip("."),
            # BETA-DATA-ID-02: isti kanonski ugovor kao ostali pisci.
            "source_sha256":   __import__(
                "shared.vector_identity", fromlist=["x"]
            ).verzija_dokumenta(text),
            "is_scanned":      is_scanned,
            "session_id":      "__local__",
        }
        manifest = await asyncio.to_thread(chunk_document, text, source_meta)

        if manifest.total_chunks == 0:
            raise HTTPException(status_code=422, detail="Empty document")

        session_id = generate_session_id()
        ttl_hours = 24
        try:
            # Institutional Memory V2 (2026-07-26) STUB 2: origin metadata i
            # ovde, iako ovaj tmp_* namespace ostaje potpuno nepromenjen
            # (ad-hoc, 24h TTL, van kancelarija_{id}/user_{id} šeme -- v.
            # Institutional Learning & RAG Audit #1) -- svaki vektor u
            # Pinecone-u treba da nosi origin, ne samo trajni case_doc/
            # draft_final.
            from shared.vector_origin import ORIGIN_CLIENT_DOC
            from shared.vector_identity import verzija_dokumenta as _vd02
            count = await asyncio.to_thread(
                ingest_session, manifest, session_id, ttl_hours,
                # Final Beta Gate F1 (MEDIUM): tmp_ namespaces are session-based
                # (a real uuid4, not a guessable id) but had NO ownership check at
                # all -- unlike pred_ namespaces (_verify_pred_namespace_ownership
                # above). If a session_id ever leaks (browser history, logs, a
                # shared screenshot), ANY authenticated user could query another
                # user's uploaded document via /api/dokument/pitanje. owner_user_id
                # lets that check happen now -- see _verify_pred_namespace_ownership.
                extra_metadata={"origin": ORIGIN_CLIENT_DOC, "owner_user_id": user["user_id"]},
                verzija_dokumenta_id=_vd02(text),
            )
            # SE-02: `count` se dodeljivao a nikad nije poredjen sa brojem
            # chunk-ova -- sesija je mogla biti proglasena spremnom za pitanja
            # nad nepotpuno indeksiranim dokumentom.
            from uploaded_doc.ingest import ingest_je_potpun as _potpun
            if not _potpun(count, manifest.total_chunks):
                logger.error(
                    "[UPLOAD] nepotpun ingest session=%s: upisano %s od %s",
                    session_id, count, manifest.total_chunks,
                )
        except Exception as e:
            _es = str(e)
            # SE-02: stari klasifikator (`"storage" in _es.lower()`) je svaku
            # gresku koja pominje "storage" pretvarao u kvotu. Kanonski je sada
            # `je_kvota_greska`, isti koji koristi `api.py`.
            from uploaded_doc.ingest import je_kvota_greska as _je_kvota
            if _je_kvota(e):
                # Pinecone pun — nastavi bez RAG, tekst je ekstraktovan
                logger.warning("[UPLOAD] Pinecone storage pun, nastavljam bez indeksiranja: %s", _es[:120])
                count = 0
            else:
                logger.error("[UPLOAD] ingest_session greška: %s", _es, exc_info=True)
                raise HTTPException(status_code=500, detail=f"Greška pri obradi dokumenta: {_es}")

        exp_iso = expires_at_iso(ttl_hours)

        async def _background_cleanup():
            try:
                result = await asyncio.to_thread(cleanup_expired)
                logger.info("[UPLOAD] Background cleanup: %s", result)
            except Exception as _ce:
                logger.warning("[UPLOAD] Background cleanup failed: %s", _ce)

        asyncio.create_task(_background_cleanup())

        # FIX (nightly repair, 2026-07-24), Faza 3 item 9: klasifikacija
        # dokaza je ranije bila deo istog asyncio.gather-a koji je upload
        # odgovor čekao da završi -- korisnik je čekao GPT poziv koji mu
        # nije bio odmah potreban. Sad je fire-and-forget, isti obrazac kao
        # _background_cleanup iznad. Rezultat se NE vraća više u upload
        # odgovoru (bilo bi nepotpuno/pogrešno vraćati polupopunjen
        # rezultat) -- POST /api/dokument/klasifikuj-sesija već postoji kao
        # postojeći, nezavisan način da se klasifikacija dobije na zahtev.
        async def _background_klasifikacija():
            try:
                rezultat = await _klasifikuj_dokaz(text, file.filename or "dokument")
                logger.info("[UPLOAD] Klasifikacija dovršena session_id=%s: %s", session_id, rezultat.get("tip", "?"))
            except Exception as _ke:
                logger.warning("[UPLOAD] Background klasifikacija failed session_id=%s: %s", session_id, _ke)

        asyncio.create_task(_background_klasifikacija())

        await UsageService.consume(user["user_id"], user.get("email", ""), "document_analysis")

        base_resp = UploadResponse(
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
        resp_dict = base_resp.model_dump()
        resp_dict["klasifikacija"] = None
        resp_dict["klasifikacija_napomena"] = (
            "Klasifikacija dokumenta se izračunava u pozadini — pozovite "
            "POST /api/dokument/klasifikuj-sesija sa ovim session_id za rezultat."
        )
        return resp_dict

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
async def dokument_pitanje(body: PitanjeDocRequest, user: dict = Depends(PermissionService.require("document_analysis"))):
    """Ask a question about an uploaded document session."""
    from main import ask_agent
    from uploaded_doc.session import validate_session

    if not body.pitanje or not body.pitanje.strip():
        raise HTTPException(status_code=422, detail="Pitanje ne može biti prazno")
    if len(body.pitanje) > _MAX_DOC_PITANJE_LEN:
        raise HTTPException(status_code=422, detail="Pitanje je predugačko")
    if not body.session_id or not body.session_id.strip():
        raise HTTPException(status_code=422, detail="session_id je obavezan")

    ns_prefix = body.namespace_prefix or "tmp_"
    if ns_prefix not in ("tmp_", "pred_"):
        ns_prefix = "tmp_"

    await _verify_pred_namespace_ownership(body.session_id, ns_prefix, user["user_id"])

    session_valid = await asyncio.to_thread(validate_session, body.session_id, ns_prefix)
    if not session_valid:
        raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla")

    # Mission Keystone (2026-08-04): a second, real, unwrapped ask_agent call
    # path that Mission Migration/Project Phoenix's own inventories missed
    # (both only traced routers/copilot.py's delegation) -- same flat
    # single-wrap-point shape as copilot.py::_handle_pravno_pitanje, migrated
    # here using the identical proven pattern.
    # S6B Phase B (2026-08-09): bind the subject, but ONLY where one truthfully
    # exists.
    #
    # For ns_prefix == "pred_", body.session_id IS predmeti.id -- not a session
    # id that resembles one. _verify_pred_namespace_ownership above proved it
    # with .eq("id", session_id).eq("user_id", uid), raising 404 otherwise, so
    # by this line it is an authoritative, owned predmet_id. No mapping is
    # invented and no new semantics are introduced.
    #
    # For ns_prefix == "tmp_", the subject stays NULL. The semantic trace found
    # NO deterministic mapping from a tmp_ session id to predmet_dokumenti.id:
    # it is a uuid4 that is never written to any table, has no PK, no FK and no
    # unique constraint. Writing it into document_id would manufacture an audit
    # identity that joins to nothing. A truthful NULL is the correct record, and
    # leaving it NULL is a PASS here, not a coverage gap.
    #
    # Note also that this endpoint does NOT go through _fetch_session_tekst --
    # it passes the namespace straight to ask_agent -- so the cross-prefix
    # fallback closed in Phase A never applied to this binding in the first
    # place. Phase A stands on its own as an integrity fix for the other callers.
    from shared.ai_provenance import case_context as _ai_case_ctx
    _subject_predmet_id = body.session_id if ns_prefix == "pred_" else None
    with _ai_case_ctx(
        predmet_id=_subject_predmet_id,
        module_name="ask_agent",
        operation_name="dokument_pitanje",
    ):
        rezultat = await asyncio.to_thread(
            ask_agent,
            body.pitanje,
            body.history,
            [f"{ns_prefix}{body.session_id}"],
        )
    if isinstance(rezultat, dict) and rezultat.get("status") != "error":
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="dokument_pitanje", user_id=user.get("user_id"),
            resource_type="dokument_pitanje", resource_id=body.session_id,
        ))
    # SOA2-004 (second-order audit, 2026-08-08): ask_agent never raises — a
    # provider failure comes back as {"status":"error","message":"Sistem je
    # trenutno zauzet..."}. The predicate three lines above ALREADY computes
    # exactly that condition, and was used only to decide whether to write an
    # audit row; the charge below ran unconditionally. The lawyer paid 2
    # credits for an HTTP 200 whose entire body is "the system is busy".
    # Same gate, now also governing the money — this codebase's canonical
    # semantics are charge-for-a-delivered-result (see drafting.py:628-634,
    # api.py:5049-5060, evidence.py:479-480).
    if isinstance(rezultat, dict) and rezultat.get("status") == "error":
        logger.warning(
            "[DOC_PITANJE] AI nije vratio rezultat (status=error) — kredit NIJE naplaćen uid=%.8s",
            user["user_id"],
        )
        return rezultat

    await UsageService.consume(user["user_id"], user.get("email", ""), "document_analysis")
    return rezultat


@router.post("/api/dokument/analiza")
@limiter.limit("5/minute")
async def dokument_analiza(
    body: DokumentAnalizaReq,
    request: Request,
    user: dict = Depends(PermissionService.require("document_analysis")),
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
        # NIGHT-002 (2026-08-09): validate_session only proves the namespace
        # exists and has not expired -- it says nothing about WHO owns it. The
        # ownership check was added to /pitanje and /klasifikuj-sesija (Final
        # Beta Gate F1, LAMBDA008-SEC-001) and missed here, so any authenticated
        # user holding a leaked session_id (browser history, a support
        # screenshot, a copied URL) could read the full analysis of another
        # firm's document through this endpoint.
        await _verify_pred_namespace_ownership(body.session_id, "tmp_", user["user_id"])
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
        # AKCIJA 1 (2026-07-24): prethodna poruka je govorila "primena
        # multi-pass pristupa", ali ask_analiza_v2 (main.py) radi TAČNO
        # JEDAN GPT-4o poziv bez obzira na dužinu dokumenta -- za dokumente
        # iznad ovog praga samo skraćuje svaki segment na max_chars_per_segment
        # (main.py, trenutno 1800 znakova) pre tog jednog poziva. Poruka je
        # sada usklađena sa stvarnim ponašanjem, ne sa željenom arhitekturom.
        logger.info(
            "[ANALIZA] Dugačak dokument (%d ch, %d segmenata) — segmenti skraćeni pre jednog GPT-4o poziva (nije stvaran multi-pass)",
            segmented.char_count, segmented.segment_count,
        )

    rezultat = await asyncio.to_thread(ask_analiza_v2, segmented, body.pitanje)

    if rezultat.get("status") != "success":
        raise HTTPException(status_code=502, detail="AI analiza trenutno nedostupna. Pokušajte ponovo.")

    preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "document_analysis")

    return {
        "status":           "success",
        "doc_type":         segmented.doc_type,
        "segment_count":    segmented.segment_count,
        "char_count":       segmented.char_count,
        "report":           rezultat["data"],
        "credits_remaining": max(preostalo, 0),
    }


@router.post("/api/dokument/klasifikuj-sesija")
@limiter.limit("10/minute")
async def klasifikuj_sesiju(
    request: Request,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Ručna AI klasifikacija dokumenta iz aktivne sesije."""
    session_id = (body.get("session_id") or "").strip()
    namespace_prefix = body.get("namespace_prefix") or "tmp_"
    filename = body.get("filename") or "dokument"

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id je obavezan.")
    if namespace_prefix not in ("tmp_", "pred_"):
        namespace_prefix = "tmp_"

    await _verify_pred_namespace_ownership(session_id, namespace_prefix, user["user_id"])

    tekst = await asyncio.to_thread(_fetch_session_tekst, session_id, namespace_prefix)
    if not tekst:
        raise HTTPException(status_code=404, detail="Sesija nije pronađena ili je istekla.")

    klasifikacija = await _klasifikuj_dokaz(tekst, filename)
    return {"ok": True, "session_id": session_id, "klasifikacija": klasifikacija}


@router.post("/api/dokument/rokovi")
@limiter.limit("20/minute")
async def dokument_rokovi(body: RokoviRequest, request: Request, user: dict = Depends(PermissionService.require("document_analysis"))):
    """Phase 4.1 — Ekstrakcija rokova + kalkulacija datuma. Ne troši kredit."""
    from uploaded_doc.deadline_parser import ekstrahuj_rokove, _extract_datum_dokumenta

    tekst = (body.tekst or "").strip()

    if not tekst and body.session_id:
        from uploaded_doc.session import validate_session
        # NIGHT-002 (2026-08-09): validate_session only proves the namespace
        # exists and has not expired -- it says nothing about WHO owns it. The
        # ownership check was added to /pitanje and /klasifikuj-sesija (Final
        # Beta Gate F1, LAMBDA008-SEC-001) and missed here, so any authenticated
        # user holding a leaked session_id (browser history, a support
        # screenshot, a copied URL) could read the full analysis of another
        # firm's document through this endpoint.
        await _verify_pred_namespace_ownership(body.session_id, "tmp_", user["user_id"])
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
