# -*- coding: utf-8 -*-
"""
Vindex AI — routers/drafting.py

Nacrti, analiza, sazmi, feedback, podnesci, AI paralegal pipeline
"""
import asyncio
import json
import logging
import os
import time as _time
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from shared.deps import (
    _audit, _deduct_credit, _get_credits, _get_supa, _q_hash,
    get_current_user, require_credits, require_pro,
)
from shared.rate import limiter

from main import ask_analiza, _skini_pii
from drafting.router import generate_draft as _drafting_generate
from drafting.templates import get_types_list as _drafting_get_types
from app.services import audit_log as _al
from templates.podnesci import (
    TIPOVI as PODNESAK_TIPOVI,
    EKSTRAKCIONI_PROMPTOVI,
    OBOGACIVANJE_PROMPTOVI,
    popuni_sablon,
)
from knowledge.vks_standards import preporuci_iznose as vks_preporuci

logger = logging.getLogger("vindex.api")
router = APIRouter()

_MAX_PLAYBOOK_BYTES = 2 * 1024 * 1024  # 2 MB


# ── Models ────────────────────────────────────────────────────────────────────

class NacrtReq(BaseModel):
    vrsta: str = Field(..., min_length=2, max_length=200)
    opis:  str = Field(..., min_length=10, max_length=5000)

    @field_validator("vrsta", "opis")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return v.strip()


class AnalizaReq(BaseModel):
    tekst:   str = Field(..., min_length=10, max_length=50000)
    pitanje: str = Field("", max_length=1000)

    @field_validator("tekst", "pitanje")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return v.strip()


class FeedbackReq(BaseModel):
    pitanje: str = Field("", max_length=2000)
    odgovor: str = Field("", max_length=5000)
    tip:     str = Field("greska", max_length=50)


class PodnesakReq(BaseModel):
    tip:  str = Field(..., max_length=50)
    opis: str = Field(..., min_length=20, max_length=5000)

    @field_validator("tip")
    @classmethod
    def validiraj_tip(cls, v: str) -> str:
        dozvoljeni = {"tuzba_naknada_stete", "zalba_parnicna", "predlog_izvrsenje"}
        if v not in dozvoljeni:
            raise ValueError(f"Tip podneska mora biti jedan od: {dozvoljeni}")
        return v

    @field_validator("opis")
    @classmethod
    def ocisti_opis(cls, v: str) -> str:
        return v.strip()


class NacrtChecklistReq(BaseModel):
    tip:       str = Field(..., max_length=60)
    cinjenice: str = Field(..., min_length=10, max_length=8000)

    @field_validator("tip")
    @classmethod
    def validiraj_tip(cls, v: str) -> str:
        from nacrti.checklist_config import SVI_TIPOVI
        if v not in SVI_TIPOVI:
            raise ValueError(f"Nepoznat tip podneska: {v!r}. Dozvoljeni: {SVI_TIPOVI}")
        return v

    @field_validator("cinjenice")
    @classmethod
    def ocisti_cinjenice(cls, v: str) -> str:
        return v.strip()


class SazmiReq(BaseModel):
    odgovor: str = Field(..., max_length=6000)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _pokreni(fn, *args):
    return await asyncio.to_thread(fn, *args)


def _normalizuj_rezultat(rezultat: dict, credits_remaining: Optional[int] = None) -> dict:
    resp: dict = {}
    if not isinstance(rezultat, dict):
        resp["odgovor"] = str(rezultat)
    elif rezultat.get("status") == "success":
        resp["odgovor"] = rezultat.get("data", "")
    else:
        resp["odgovor"] = rezultat.get(
            "message",
            "Došlo je do greške prilikom obrade zahteva. Pokušajte ponovo.",
        )
    if credits_remaining is not None:
        resp["credits_remaining"] = credits_remaining
    return resp


def _greska_odgovor(status_code: int, poruka: str) -> JSONResponse:
    logger.warning("API greška %d: %s", status_code, poruka)
    return JSONResponse(status_code=status_code, content={"greska": poruka})


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/nacrt/types")
async def nacrt_types():
    """Vraća listu dostupnih tipova nacrta (bez autentifikacije)."""
    return {"tipovi": _drafting_get_types()}


@router.post("/api/playbook/upload")
@limiter.limit("10/minute")
async def playbook_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_pro),
):
    """P4.4 — Upload firm playbook (TXT or DOCX). Ne troši kredit."""
    from pathlib import Path as _Path
    import tempfile
    from uploaded_doc.extractor import extract_docx, extract_txt

    suffix = _Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".docx"}:
        raise HTTPException(status_code=415, detail="Podržani formati: TXT, DOCX")

    raw = await file.read()
    if len(raw) > _MAX_PLAYBOOK_BYTES:
        raise HTTPException(status_code=413, detail="Fajl je preko 2MB")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            tmp_path = _Path(tmp.name)

        if suffix == ".docx":
            tekst, _ = await asyncio.to_thread(extract_docx, tmp_path)
        else:
            tekst, _ = await asyncio.to_thread(extract_txt, tmp_path)

        if not tekst or not tekst.strip():
            raise HTTPException(status_code=422, detail="Fajl je prazan ili nečitljiv")

        from drafting.playbook import ingest_playbook
        count = await asyncio.to_thread(ingest_playbook, user["user_id"], file.filename or "", tekst)
        return {"filename": file.filename, "chunks_ingested": count}
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


@router.delete("/api/playbook")
@limiter.limit("10/minute")
async def playbook_delete(request: Request, user: dict = Depends(require_pro)):
    """P4.4 — Briše ceo playbook korisnika iz Pinecone."""
    from drafting.playbook import delete_playbook
    deleted = await asyncio.to_thread(delete_playbook, user["user_id"])
    return {"deleted_chunks": deleted}


@router.get("/api/playbook/status")
@limiter.limit("30/minute")
async def playbook_status(request: Request, user: dict = Depends(require_pro)):
    """P4.4 — Vraća status playbook-a: da li postoji i koliko chunks ima."""
    def _check():
        try:
            from uploaded_doc.ingest import _get_pinecone_index
            index = _get_pinecone_index()
            ns = f"playbook_{user['user_id']}"
            stats = index.describe_index_stats()
            ns_data = stats.namespaces.get(ns) if hasattr(stats, "namespaces") else None
            count = (ns_data.vector_count if hasattr(ns_data, "vector_count") else 0) if ns_data else 0
            return {"has_playbook": count > 0, "chunk_count": count}
        except Exception:
            return {"has_playbook": False, "chunk_count": 0}
    return await asyncio.to_thread(_check)


@router.post("/api/nacrt")
@limiter.limit("10/minute")
async def nacrt(req: NacrtReq, request: Request, user: dict = Depends(require_pro)):
    """Generisanje nacrta pravnog dokumenta (strukturirani šablon)."""
    logger.info("Nacrt [uid=%.8s] vrsta=%s", user["user_id"], req.vrsta)
    asyncio.create_task(_audit(user["user_id"], f"nacrt:{req.vrsta}", ""))
    try:
        qh_nacrt = _q_hash(_skini_pii(req.opis))
        t0 = _time.monotonic()
        rezultat = await _pokreni(_drafting_generate, req.vrsta, _skini_pii(req.opis), user["user_id"])
        latency_ms = int((_time.monotonic() - t0) * 1000)
        _al.log_response(
            endpoint="/api/nacrt",
            query_hash=qh_nacrt,
            tip=req.vrsta[:20],
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
        if not user.get("credit_pre_deducted"):
            preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        else:
            preostalo = user.get("credits_remaining", 0)
        return _normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Greška u /api/nacrt")
        return _greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@router.post("/api/analiza")
@limiter.limit("10/minute")
async def analiza(req: AnalizaReq, request: Request, user: dict = Depends(require_credits)):
    """Analiza pravnog dokumenta."""
    qh = _q_hash(req.pitanje)
    logger.info("Analiza [uid=%.8s] [q=%s]", user["user_id"], qh)
    asyncio.create_task(_audit(user["user_id"], "analiza", qh))
    try:
        qh_analiza = _q_hash(_skini_pii(req.pitanje or req.tekst[:200]))
        t0 = _time.monotonic()
        rezultat = await _pokreni(ask_analiza, req.tekst, req.pitanje)
        latency_ms = int((_time.monotonic() - t0) * 1000)
        _al.log_response(
            endpoint="/api/analiza",
            query_hash=qh_analiza,
            response_text=rezultat.get("data", ""),
            latency_ms=latency_ms,
        )
        is_blocked = (rezultat.get("data") or "").startswith("[!] ANALIZA BLOKIRANA")
        should_deduct = (not user.get("credit_pre_deducted") and rezultat.get("status") == "success" and not is_blocked)
        if should_deduct:
            preostalo = await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        elif user.get("credit_pre_deducted"):
            preostalo = user.get("credits_remaining", 0)
        else:
            preostalo = await asyncio.to_thread(_get_credits, user["user_id"])
        return _normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Neočekivana greška u /api/analiza")
        return _greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@router.post("/api/sazmi")
@limiter.limit("10/minute")
async def sazmi(req: SazmiReq, request: Request, user: dict = Depends(require_credits)):
    """Generiše verziju odgovora na 'ljudskom' jeziku za klijenta (Viber/Mejl)."""
    from openai import OpenAI as _OAI
    try:
        klijent_prompt = (
            "Advokat ti šalje pravni odgovor koji treba da prepišeš za klijenta — laika koji ne zna pravo.\n"
            "PRAVILA TONA: Profesionalan, smiren, poverljiv. BEZ: latinštine, paragrafa, citata, 'čl.', 'Sl. glasnik', 'lex specialis'.\n"
            "STRUKTURA (4–6 rečenica):\n"
            "  1. Šta znači situacija za klijenta u jednoj jasnoj rečenici.\n"
            "  2. Šta je klijentov ključni dokaz ili korak — konkretan, bez teorije.\n"
            "  3. Koji je rizik ako ne preduzme ništa (rok, zastarelost, gubitak prava).\n"
            "  4. Šta je sledeći korak koji klijent treba da uradi — imperativ, ne upit.\n"
            "  5. Kratka napomena: 'Pre preduzimanja koraka, konsultujte svog advokata za konačno mišljenje.'\n"
            "Počni direktno prvom rečenicom. Bez uvoda, bez 'Evo sažetka', bez zaglavlja."
        )
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=300,
            messages=[
                {"role": "system", "content": klijent_prompt},
                {"role": "user",   "content": _skini_pii(req.odgovor[:4000])},
            ],
        )
        tekst = resp.choices[0].message.content.strip()
        if not user.get("credit_pre_deducted"):
            await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))
        return {"status": "ok", "sazetak": tekst}
    except Exception:
        logger.exception("Greška u /api/sazmi")
        return _greska_odgovor(500, "Greška pri generisanju sažetka.")


@router.post("/api/feedback")
async def feedback(req: FeedbackReq, user: dict = Depends(get_current_user)):
    """
    Korisnik prijavljuje netačan ili nepotpun odgovor.
    NO-STORAGE POLICY (Basic API tier): čuvamo samo hash pitanja i tip — bez sadržaja.
    ZZPL čl. 5(1)(c) — minimizacija podataka.
    """
    try:
        qh = _q_hash(req.pitanje)
        await asyncio.to_thread(
            lambda: _get_supa().table("feedback").insert({
                "user_id": user["user_id"],
                "q_hash":  qh,
                "tip":     req.tip,
            }).execute()
        )
        logger.info("Feedback [uid=%.8s] tip=%s [q=%s]", user["user_id"], req.tip, qh)
        return {"status": "ok"}
    except Exception:
        logger.exception("Greška u /api/feedback")
        return {"status": "ok"}


@router.post("/api/podnesak")
@limiter.limit("5/minute")
async def podnesak(req: PodnesakReq, request: Request, user: dict = Depends(require_pro)):
    """
    Generiše nacrt sudskog podneska u dva koraka:
    1. Ekstrakcija entiteta iz slobodnog opisa (GPT-4o-mini, brzo)
    2. RAG + popunjavanje šablona (GPT-4o, precizno)
    """
    from openai import OpenAI as _OAI

    log_id = _q_hash(req.opis)
    logger.info("Podnesak [uid=%.8s] tip=%s [q=%s]", user["user_id"], req.tip, log_id)

    oai = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
    opis_api = _skini_pii(req.opis)

    ekstr_prompt = EKSTRAKCIONI_PROMPTOVI[req.tip]

    def _parse_json_safe(raw: str) -> dict:
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r'\{[\s\S]+\}', raw)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        return {}

    try:
        ekstr_resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=900,
                messages=[
                    {"role": "system", "content": ekstr_prompt},
                    {"role": "user",   "content": f"OPIS SLUČAJA:\n{opis_api}"},
                ],
            )
        )
        raw_json = (ekstr_resp.choices[0].message.content or "").strip()
        entiteti: dict = _parse_json_safe(raw_json)
        if not entiteti:
            logger.warning("Ekstrakcija vratila prazan JSON [q=%s] — retry sa gpt-4o", log_id)
            ekstr_resp2 = await asyncio.to_thread(
                lambda: oai.chat.completions.create(
                    model="gpt-4o",
                    temperature=0,
                    max_tokens=900,
                    messages=[
                        {"role": "system", "content": ekstr_prompt},
                        {"role": "user",   "content": f"OPIS SLUČAJA:\n{opis_api}\n\nVrati ISKLJUČIVO validan JSON objekat, bez ikakvog drugog teksta."},
                    ],
                )
            )
            entiteti = _parse_json_safe(ekstr_resp2.choices[0].message.content or "")
    except Exception as exc:
        logger.warning("Ekstrakcija entiteta neuspešna [q=%s]: %s", log_id, exc)
        entiteti = {}

    rag_upit = f"{PODNESAK_TIPOVI[req.tip]}: {opis_api[:400]}"
    try:
        from app.services.retrieve import retrieve_documents
        docs = await asyncio.to_thread(retrieve_documents, rag_upit, 5)
        kontekst = "\n\n".join(docs[:4]) if docs else ""
    except Exception as exc:
        logger.warning("RAG neuspešan za podnesak [q=%s]: %s", log_id, exc)
        kontekst = ""

    vks_analiza = ""
    vks_kontekst_blok = ""
    if req.tip == "tuzba_naknada_stete":
        try:
            vks = vks_preporuci(entiteti)
            vks_kontekst_blok = f"\n\nVKS ORIJENTACIONI KRITERIJUMI:\n{vks['kontekst_tekst']}"
            vks_analiza = vks["analiza_tekst"]
        except Exception as exc:
            logger.warning("VKS preporuka neuspešna [q=%s]: %s", log_id, exc)

    obog_prompt = OBOGACIVANJE_PROMPTOVI[req.tip]
    obog_user = (
        f"EKSTRAKTOVANI PODACI (JSON):\n{json.dumps(entiteti, ensure_ascii=False)}"
        f"{vks_kontekst_blok}\n\n"
        f"ZAKONSKI KONTEKST (RAG):\n{kontekst or 'Nije pronađen relevantan kontekst.'}"
    )
    try:
        obog_resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o",
                temperature=0,
                max_tokens=2500,
                messages=[
                    {"role": "system", "content": obog_prompt},
                    {"role": "user",   "content": obog_user},
                ],
            )
        )
        raw_obog = (obog_resp.choices[0].message.content or "").strip()
        raw_obog = raw_obog.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        obogacivanje: dict = json.loads(raw_obog)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Obogaćivanje neuspešno [q=%s]: %s", log_id, exc)
        obogacivanje = {}

    nacrt = popuni_sablon(req.tip, entiteti, obogacivanje, vks_analiza=vks_analiza)

    await asyncio.to_thread(_deduct_credit, user["user_id"], user.get("email", ""))

    return {
        "status":  "success",
        "odgovor": nacrt,
        "tip":     req.tip,
        "naziv":   PODNESAK_TIPOVI[req.tip],
    }


@router.post("/api/nacrti/checklist")
@limiter.limit("20/minute")
async def nacrti_checklist(req: NacrtChecklistReq, request: Request, user: dict = Depends(require_pro)):
    """
    Faza 1 — Checklist analiza.

    Prima tip podneska i slobodan tekst činjenica.
    Vraća koji obavezni elementi nedostaju, sa objašnjenjem zašto su važni.
    blokira_nastavak=True ako nedostaje element kriticnosti "visoka".
    """
    from nacrti.checklist_engine import analiziraj_checklist

    log_id = _q_hash(req.cinjenice)
    logger.info("NacrtChecklist [uid=%.8s] tip=%s [q=%s]", user["user_id"], req.tip, log_id)

    try:
        rezultat = await asyncio.to_thread(analiziraj_checklist, req.tip, req.cinjenice)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("NacrtChecklist GPT error [q=%s]: %s", log_id, e)
        raise HTTPException(status_code=502, detail="AI servis trenutno nedostupan. Pokušajte ponovo.")

    return rezultat
