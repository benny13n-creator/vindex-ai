# -*- coding: utf-8 -*-
"""
Vindex AI — routers/drafting.py

Nacrti, analiza, sazmi, feedback, podnesci, AI paralegal pipeline

Core Consolidation Sec 1.4 (2026-07-22) — interim ownership (NOT merged,
pilot-gated by explicit founder decision): this file hosts TWO of the
three drafting surfaces. POST /api/nacrt (line ~236) wraps
drafting.router.generate_draft (drafting/router.py) unchanged — the quick
single-shot path. POST /api/podnesak (line ~372) is this file's OWN
generation logic against templates/podnesci.py's TIPOVI/SABLONI, RAG-
augmented (sudska praksa retrieval, see rag_upit below) and tied to an
open predmet — richer context than /api/nacrt. 6 of podnesci.py's 12
types duplicate drafting/templates.py's TEMPLATES under the same type
keys with different template text (tuzba_naknada_stete, tuzba_radni_spor,
tuzba_razvod, prigovor_platni_nalog, krivicna_prijava,
predlog_privremena_mera) — known, tracked duplication, not an oversight.
Do not resolve by intuition; see VINDEX_CORE_CONSOLIDATION.md Sec 1.4.
"""
import asyncio
import json
import logging
import os
import time as _time
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from shared.deps import _audit, _get_supa, _q_hash, get_current_user
from shared.rate import limiter
from shared.permissions import PermissionService
from shared.usage import UsageService

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
    tip:        str           = Field(..., max_length=50)
    opis:       str           = Field(..., min_length=20, max_length=5000)
    sud_naziv:  Optional[str] = Field(None, max_length=200)
    sud_adresa: Optional[str] = Field(None, max_length=300)

    @field_validator("tip")
    @classmethod
    def validiraj_tip(cls, v: str) -> str:
        dozvoljeni = {
            "tuzba_naknada_stete", "zalba_parnicna", "predlog_izvrsenje",
            "tuzba_radni_spor", "tuzba_razvod", "prigovor_platni_nalog",
            "krivicna_prijava", "predlog_privremena_mera",
            "odgovor_na_tuzbu", "zalba_krivicna", "urgencija_sudu", "prigovor_izvrsenje",
        }
        if v not in dozvoljeni:
            raise ValueError(f"Tip podneska mora biti jedan od: {dozvoljeni}")
        return v

    @field_validator("opis")
    @classmethod
    def ocisti_opis(cls, v: str) -> str:
        return v.strip()

    @field_validator("sud_naziv", "sud_adresa")
    @classmethod
    def ocisti_sud(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


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
    format:  str = Field(default="email", pattern="^(email|viber|pisano)$")


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


@router.get("/api/courts")
async def get_courts():
    """Katalog srpskih sudova sa adresama — za popunjavanje zaglavlja podnesaka."""
    from knowledge.sudovi import SUDOVI
    return {"sudovi": SUDOVI}


@router.post("/api/playbook/upload")
@limiter.limit("10/minute")
async def playbook_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(PermissionService.require("drafting")),
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
async def playbook_delete(request: Request, user: dict = Depends(PermissionService.require("drafting"))):
    """P4.4 — Briše ceo playbook korisnika iz Pinecone."""
    from drafting.playbook import delete_playbook
    deleted = await asyncio.to_thread(delete_playbook, user["user_id"])
    return {"deleted_chunks": deleted}


@router.get("/api/playbook/status")
@limiter.limit("30/minute")
async def playbook_status(request: Request, user: dict = Depends(PermissionService.require("drafting"))):
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
async def nacrt(req: NacrtReq, request: Request, user: dict = Depends(PermissionService.require("drafting"))):
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
        preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")
        return _normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Greška u /api/nacrt")
        return _greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


@router.post("/api/analiza")
@limiter.limit("10/minute")
async def analiza(req: AnalizaReq, request: Request, user: dict = Depends(PermissionService.require("drafting"))):
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
        if rezultat.get("status") == "success" and not is_blocked:
            preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")
        else:
            preostalo = await UsageService.balance(user["user_id"], user.get("email", ""))
        return _normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except Exception:
        logger.exception("Neočekivana greška u /api/analiza")
        return _greska_odgovor(
            500,
            "Došlo je do greške na serveru. Pokušajte ponovo za nekoliko sekundi.",
        )


_FORMAT_INSTRUKCIJA = {
    "email": (
        "Format: EMAIL klijentu. Ton: profesionalan, formalan. "
        "Početak: 'Poštovani/a,' — zatim 4-5 rečenica — kraj: 'S poštovanjem, Vaš advokat'."
    ),
    "viber": (
        "Format: KRATKA VIBER PORUKA klijentu. Ton: neformalan, prijatan, bez 'Poštovani'. "
        "Maksimalno 3-4 kratke rečenice. Bez formalnog pozdrava na kraju."
    ),
    "pisano": (
        "Format: PISANO OBAVEŠTENJE klijentu. Ton: formalan, kao zvanično pismo. "
        "Koristiti 'Obaveštavamo Vas...' — 5-6 rečenica — zaključna napomena o konsultaciji."
    ),
}


@router.post("/api/sazmi")
@limiter.limit("10/minute")
async def sazmi(req: SazmiReq, request: Request, user: dict = Depends(PermissionService.require("drafting"))):
    """Generiše verziju odgovora na 'ljudskom' jeziku za klijenta (email/viber/pisano)."""
    from openai import OpenAI as _OAI
    try:
        fmt_instr = _FORMAT_INSTRUKCIJA.get(req.format, _FORMAT_INSTRUKCIJA["email"])
        klijent_prompt = (
            "Advokat ti šalje pravni odgovor koji treba da prepišeš za klijenta — laika koji ne zna pravo.\n"
            "PRAVILA TONA: Profesionalan, smiren, poverljiv. BEZ: latinštine, paragrafa, citata, 'čl.', 'Sl. glasnik', 'lex specialis'.\n\n"
            f"{fmt_instr}\n\n"
            "SADRŽAJ (obavezni elementi):\n"
            "  1. Šta znači situacija za klijenta — jasno i konkretno.\n"
            "  2. Šta je klijentov ključni dokaz ili sledeći korak — bez teorije.\n"
            "  3. Koji je rizik ako ne preduzme ništa (rok, zastarelost, gubitak prava).\n"
            "  4. Šta konkretno da uradi — imperativ.\n"
            "  5. Napomena: konsultacija sa advokatom pre svakog koraka.\n"
            "Počni direktno. Bez uvoda, bez 'Evo sažetka', bez zaglavlja."
        )
        client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=600,
            messages=[
                {"role": "system", "content": klijent_prompt},
                {"role": "user",   "content": _skini_pii(req.odgovor[:4000])},
            ],
        )
        tekst = resp.choices[0].message.content.strip()
        await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")
        return {"status": "ok", "sazetak": tekst, "format": req.format}
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
async def podnesak(req: PodnesakReq, request: Request, user: dict = Depends(PermissionService.require("drafting"))):
    """
    Generiše nacrt sudskog podneska u dva koraka:
    1. Ekstrakcija entiteta iz slobodnog opisa (GPT-4o-mini, brzo)
    2. RAG + popunjavanje šablona (GPT-4o, precizno)
    """
    from openai import OpenAI as _OAI

    log_id = _q_hash(req.opis)
    logger.info("Podnesak [uid=%.8s] tip=%s sud=%s [q=%s]",
                user["user_id"], req.tip, req.sud_naziv or "-", log_id)

    oai = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
    opis_api = _skini_pii(req.opis)

    # Pripremi kontekst sa sudom ako je korisnik izabrao
    sud_ctx = ""
    if req.sud_naziv:
        sud_ctx = (
            f"\n\nSUD (unapred određen — OBAVEZNO koristiti):\n"
            f"  Naziv: {req.sud_naziv}\n"
            f"  Adresa: {req.sud_adresa or 'N/A'}\n"
            f"Polja SUD_NAZIV i SUD_ADRESA popuniti ovim vrednostima."
        )

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
                    {"role": "user",   "content": f"OPIS SLUČAJA:\n{opis_api}{sud_ctx}"},
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

    await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")

    return {
        "status":  "success",
        "odgovor": nacrt,
        "tip":     req.tip,
        "naziv":   PODNESAK_TIPOVI[req.tip],
    }


@router.post("/api/nacrti/checklist")
@limiter.limit("20/minute")
async def nacrti_checklist(req: NacrtChecklistReq, request: Request, user: dict = Depends(PermissionService.require("drafting"))):
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

    await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")
    return rezultat


# ── DOCX Export ───────────────────────────────────────────────────────────────

class DocxExportReq(BaseModel):
    tekst:  str = Field(..., min_length=1, max_length=100_000)
    naslov: str = Field("Nacrt", max_length=200)
    tip:    str = Field("", max_length=100)


def _nacrt_to_docx(tekst: str, naslov: str, firma_info: dict | None = None) -> bytes:
    """Konvertuje nacrt tekst u .docx sa kancelarijskim headerom. Vraća bytes."""
    import io
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    for section in doc.sections:
        section.top_margin    = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin   = Cm(3.0)
        section.right_margin  = Cm(2.5)

    if firma_info:
        naziv   = (firma_info.get("seller_naziv") or firma_info.get("naziv") or "").strip()
        adresa  = (firma_info.get("seller_adresa") or firma_info.get("adresa") or "").strip()
        mesto   = (firma_info.get("seller_mesto") or firma_info.get("mesto") or "").strip()
        pib     = (firma_info.get("seller_pib") or firma_info.get("pib") or "").strip()
        email   = (firma_info.get("email") or "").strip()

        if naziv:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(naziv)
            run.bold = True
            run.font.size = Pt(14)

        kontakt_delovi = [adresa, mesto, email]
        kontakt = " | ".join(d for d in kontakt_delovi if d)
        if kontakt:
            p = doc.add_paragraph(kontakt)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.runs[0].font.size = Pt(10)
            p.runs[0].font.color.rgb = RGBColor(0x44, 0x44, 0x44)

        if pib:
            p = doc.add_paragraph(f"PIB: {pib}")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.runs[0].font.size = Pt(9)
            p.runs[0].font.color.rgb = RGBColor(0x77, 0x77, 0x77)

        # Separator
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "999999")
        pBdr.append(bottom)
        pPr.append(pBdr)

    # Naslov
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(naslov.upper())
    run.bold = True
    run.font.size = Pt(13)
    doc.add_paragraph()

    # Sadržaj — markdown-aware parsing
    for linija in tekst.split("\n"):
        if linija.startswith("# "):
            doc.add_heading(linija[2:], level=1)
        elif linija.startswith("## "):
            doc.add_heading(linija[3:], level=2)
        elif linija.startswith("### "):
            doc.add_heading(linija[4:], level=3)
        elif linija.strip() == "":
            doc.add_paragraph()
        else:
            p = doc.add_paragraph()
            parts = linija.split("**")
            for idx, part in enumerate(parts):
                if part:
                    run = p.add_run(part)
                    run.bold = (idx % 2 == 1)
                    run.font.size = Pt(11)

    # Footer
    from datetime import date as _date
    footer = doc.sections[0].footer
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = fp.add_run(f"Generisano: {_date.today().strftime('%d.%m.%Y.')} | Vindex AI")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


@router.post("/api/nacrti/export/docx")
@limiter.limit("30/minute")
async def export_nacrt_docx(
    req: DocxExportReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Preuzmi nacrt kao .docx fajl sa kancelarijskim headerom."""
    uid = user["user_id"]
    supa = _get_supa()

    # Dohvati firma/SEF info za header
    firma_info = None
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("sef_podesavanja")
                .select("seller_pib,seller_naziv,seller_adresa,seller_mesto")
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        if r and r.data:
            firma_info = r.data
    except Exception:
        pass

    naslov = req.naslov or req.tip or "Nacrt"

    try:
        docx_bytes = await asyncio.to_thread(_nacrt_to_docx, req.tekst, naslov, firma_info)
    except Exception as e:
        logger.error("DOCX export greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri generisanju DOCX fajla.")

    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in naslov)[:40]
    filename = f"{safe_name}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
