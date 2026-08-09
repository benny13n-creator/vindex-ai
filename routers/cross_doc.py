# -*- coding: utf-8 -*-
"""
Vindex AI — routers/cross_doc.py

POST /api/analiza/cross-doc
  Višedokumentna pravna analiza: konflikti, sličnosti, preporuke.
  GPT-4o poredi 2-5 dokumenata/odlomaka u kontekstu datog pravnog pitanja.

POST /api/analiza/cross-doc/predmet
  Cross-doc v1: uzima ID-jeve dokumenata vezanih za predmet, rekonstruiše
  tekst iz Pinecone i pokreće analizu konflikata.
"""
import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa
from shared.llm_retry import llm_retry
from shared.rate import limiter
from shared.permissions import PermissionService
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService

logger = logging.getLogger("vindex.api")
router = APIRouter()


@llm_retry
def _pozovi_cross_doc_api(client, system: str, user_msg: str):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        max_tokens=2000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
    )


# ─── Modeli ───────────────────────────────────────────────────────────────────

class DokumentUnos(BaseModel):
    naziv:  str = Field(..., min_length=1, max_length=200, description="Naziv dokumenta")
    # AKCIJA 2 (2026-07-24): podignuto sa 5000 -- pri starom limitu, klijent
    # nije mogao ni da POŠALJE tekst duži od par strana. Sama analiza i dalje
    # radi nad pametno uzorkovanim tekstom (_uzorkuj_dokument), ne nad celim
    # tekstom bez ograničenja -- ovo samo dozvoljava da duži tekst UOPŠTE
    # stigne do te logike umesto da bude odbijen na validaciji.
    tekst:  str = Field(..., min_length=10, max_length=100_000, description="Sadržaj dokumenta")


class CrossDocReq(BaseModel):
    dokumenti:      list[DokumentUnos] = Field(..., min_length=2, max_length=5)
    pravno_pitanje: str                = Field(..., min_length=10, max_length=500)
    kontekst:       Optional[str]      = Field(default=None, max_length=500,
                                                description="Dodatni kontekst (opciono)")

    @field_validator("dokumenti")
    @classmethod
    def _check_unique_nazivi(cls, v: list) -> list:
        nazivi = [d.naziv for d in v]
        if len(set(nazivi)) != len(nazivi):
            raise ValueError("Svi dokumenti moraju imati različite nazive.")
        return v


# ─── GPT prompt ───────────────────────────────────────────────────────────────

_SYSTEM = (
    "Ti si pravni analitičar specijalizovan za srpsko pravo. "
    "Analiziraš više pravnih dokumenata i pronalaziš konflikte, sličnosti i daješ preporuke. "
    "Odgovori ISKLJUČIVO u JSON formatu:\n"
    "{\n"
    '  "rezime": "1-2 rečenice o ukupnom nalazu",\n'
    '  "konflikti": [\n'
    '    {"dokument_a": str, "dokument_b": str, "opis": str, "ozbiljnost": "visoka"|"srednja"|"niska",\n'
    '     "citat_a": "DOSLOVAN citat iz dokument_a koji potkrepljuje konflikt, ILI null", '
    '"citat_b": "DOSLOVAN citat iz dokument_b, ILI null"}\n'
    '  ],\n'
    '  "slicnosti": [\n'
    '    {"dokumenti": [str, ...], "opis": str}\n'
    '  ],\n'
    '  "preporuke": [\n'
    '    {"prioritet": int (1=najvažnija), "akcija": str, "obrazloženje": str}\n'
    '  ],\n'
    '  "pravni_zakljucak": "Zaključni pravni stav na osnovu analize svih dokumenata"\n'
    "}\n"
    "citat_a/citat_b moraju biti DOSLOVNO kopirani iz teksta dokumenta (ne parafraza) -- "
    "ako ne možeš da citiraš doslovno, postavi null umesto da izmišljaš. "
    "Budi koncizan, precizan, srpski jezik (ekavica). Ne halucinuj."
)


_DOC_CHAR_BUDGET = 8000  # po dokumentu, unutar cross-doc prompta


def _uzorkuj_dokument(tekst: str, budget: int = _DOC_CHAR_BUDGET) -> tuple[str, bool]:
    """AKCIJA 2 (2026-07-24): ako tekst prelazi budget, segmentuje ga
    (analiza/segmenter.py, isti obrazac kao Forenzički Legal Audit) i
    RAVNOMERNO uzorkuje segmente preko CELOG dokumenta -- umesto starog
    pristupa koji je prosto sekao na prvih 4000-5000 znakova i time
    garantovano gubio sve posle par prvih strana. Vraća (uzorkovan_tekst,
    da_li_je_uzorkovano) -- pozivalac koristi drugi element da doda
    eksplicitno upozorenje korisniku kad se to desi."""
    if len(tekst) <= budget:
        return tekst, False

    from analiza.segmenter import segment_document
    try:
        segmented = segment_document(tekst)
        segments = [s for s in segmented.segments if s.start_offset >= 0 and s.tekst]
    except Exception:
        segments = []

    if len(segments) < 3:
        # Nema smislene segmentacije (kratak/nestrukturiran ali ipak
        # predugačak tekst) -- uzmi početak I kraj, ne samo početak.
        head = tekst[: budget * 2 // 3]
        tail = tekst[-(budget // 3):]
        return f"{head}\n\n[... deo dokumenta izostavljen radi dužine ...]\n\n{tail}", True

    # Ravnomeran korak preko svih segmenata (ne samo prvih N) -- garantuje
    # da i segmenti sa KRAJA dugačkog dokumenta (npr. rizična klauzula na
    # 80. strani) imaju šansu da uđu u uzorak.
    max_segmenata = 20
    korak = max(1, len(segments) // max_segmenata)
    izabrani = segments[::korak]
    per_segment_budget = max(300, budget // max(len(izabrani), 1))

    # NAPOMENA: namerno NEMA "break kad ukupno >= budget" ovde -- per_segment_budget
    # je već izračunat da ukupan zbir bude blizu budget-a, i rani prekid bi
    # ponovo odsekao KRAJ uzorka (tačno problem koji ovo rešava). budget je
    # meki cilj, ne tvrd hard cap; blagi višak je prihvatljiva cena za
    # garanciju da uzorak pokriva ceo dokument, ne samo početak.
    delovi = []
    for s in izabrani:
        deo_teksta = s.tekst[:per_segment_budget]
        if len(s.tekst) > per_segment_budget:
            deo_teksta += f"... [skraćeno, ukupno {len(s.tekst)} znakova]"
        naslov_str = f" | {s.naslov}" if s.naslov else ""
        delovi.append(f"[{s.id}]{naslov_str}\n{deo_teksta}")

    return "\n\n".join(delovi), True


def _format_dokumenti(dokumenti: list[DokumentUnos]) -> tuple[str, list[str]]:
    """Vraća (formatiran_blok, upozorenja) -- upozorenja je lista naziva
    dokumenata čiji sadržaj nije poslat u celosti (uzorkovan zbog dužine)."""
    delovi = []
    upozorenja = []
    for i, d in enumerate(dokumenti, 1):
        uzorak, uzorkovano = _uzorkuj_dokument(d.tekst.strip())
        if uzorkovano:
            upozorenja.append(d.naziv)
        delovi.append(f"[DOKUMENT {i}: {d.naziv}]\n{uzorak}")
    return "\n\n---\n\n".join(delovi), upozorenja


def _validate_konflikti_citati(konflikti: list, dokumenti: list[DokumentUnos]) -> list:
    """AKCIJA 2 (2026-07-24): isti substring-verifikacioni princip kao
    analiza/validator.py::validate_clause_excerpts (reuse-uje njegov
    _normalize_ws), primenjen na cross-doc konflikte. citat_a/citat_b
    moraju biti doslovni citati iz odgovarajućeg dokumenta -- konflikt se
    NE odbacuje ako citat nije pronađen (uvid može biti tačan uprkos
    nepreciznom citiranju, isto kao missing_clauses u Forenzičkom Auditu
    koje ne zahtevaju izvorni citat), ali se eksplicitno obeležava
    citat_a_potvrdjen/citat_b_potvrdjen da advokat zna da mora ručno da
    proveri kad je False."""
    from analiza.validator import _normalize_ws

    tekst_po_nazivu = {d.naziv: d.tekst for d in dokumenti}

    def _proveri(citat: Optional[str], naziv_dok: Optional[str]) -> Optional[bool]:
        if not citat or not naziv_dok:
            return None
        izvor = tekst_po_nazivu.get(naziv_dok, "")
        if not izvor:
            return None
        probe = _normalize_ws(citat)[:100]
        if not probe:
            return None
        return probe in _normalize_ws(izvor)

    for k in konflikti:
        k["citat_a_potvrdjen"] = _proveri(k.get("citat_a"), k.get("dokument_a"))
        k["citat_b_potvrdjen"] = _proveri(k.get("citat_b"), k.get("dokument_b"))
    return konflikti


# ─── Sync helper (za asyncio.to_thread) ──────────────────────────────────────

def _cross_doc_sync(
    dokumenti: list[DokumentUnos],
    pravno_pitanje: str,
    kontekst: Optional[str],
) -> dict:
    from openai import OpenAI as _OAI
    client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))

    doc_blok, skraceni_dokumenti = _format_dokumenti(dokumenti)
    user_msg = (
        f"PRAVNO PITANJE / TEMA ANALIZE:\n{pravno_pitanje}\n"
        + (f"\nDODATNI KONTEKST:\n{kontekst}\n" if kontekst else "")
        + f"\n\nDOKUMENTI:\n\n{doc_blok}"
    )

    try:
        resp = _pozovi_cross_doc_api(client, _SYSTEM, user_msg)
        raw = resp.choices[0].message.content or "{}"
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        _sentry_capture(exc)
        logger.warning("[CROSS_DOC] JSON parse greška: %s", exc)
        result = {}
    except Exception as exc:
        _sentry_capture(exc)
        logger.error("[CROSS_DOC] GPT greška: %s", exc)
        raise

    konflikti = _validate_konflikti_citati(result.get("konflikti", []), dokumenti)

    return {
        "pravno_pitanje":  pravno_pitanje,
        "broj_dokumenata": len(dokumenti),
        "nazivi":          [d.naziv for d in dokumenti],
        "rezime":          result.get("rezime", ""),
        "konflikti":       konflikti,
        "slicnosti":       result.get("slicnosti", []),
        "preporuke":       sorted(result.get("preporuke", []), key=lambda x: x.get("prioritet", 99)),
        "pravni_zakljucak": result.get("pravni_zakljucak", ""),
        # AKCIJA 2 (2026-07-24): eksplicitno upozorenje kad je bar jedan
        # dokument predugačak da bi bio poslat u celosti -- korisnik mora
        # znati da analiza pokriva UZORAK, ne ceo tekst tog dokumenta.
        "upozorenje_skracenja": (
            f"Sledeći dokumenti su predugački pa je analiziran reprezentativan uzorak "
            f"njihovog sadržaja, ne ceo tekst: {', '.join(skraceni_dokumenti)}."
        ) if skraceni_dokumenti else None,
    }


# ─── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/api/analiza/cross-doc")
@limiter.limit("10/minute")
async def cross_doc_analiza(
    req: CrossDocReq,
    request: Request,
    user: dict = Depends(PermissionService.require("cross_doc")),
):
    """
    Višedokumentna pravna analiza.
    Poredi 2-5 dokumenata i identifikuje konflikte, sličnosti i daje prioritetne preporuke.
    """
    try:
        result = await asyncio.to_thread(
            _cross_doc_sync,
            req.dokumenti,
            req.pravno_pitanje,
            req.kontekst,
        )
        await UsageService.consume(user["user_id"], user.get("email", ""), "cross_doc")
        return result
    except Exception:
        logger.exception("Greška u /api/analiza/cross-doc")
        return JSONResponse(
            status_code=500,
            content={"error": "Greška pri analizi dokumenata. Pokušajte ponovo."},
        )


# ─── Cross-doc v1 — predmetni endpoint ───────────────────────────────────────

class CrossDocPredmetReq(BaseModel):
    predmet_id:     str            = Field(..., min_length=1)
    dokument_ids:   list[str]      = Field(..., min_length=2, max_length=5)
    pravno_pitanje: str            = Field(..., min_length=10, max_length=500)


@router.post("/api/analiza/cross-doc/predmet")
@limiter.limit("5/minute")
async def cross_doc_predmet(
    req: CrossDocPredmetReq,
    request: Request,
    user: dict = Depends(PermissionService.require("cross_doc")),
):
    """
    Cross-doc v1: uzima IDs dokumenata predmeta, rekonstruiše tekst iz Pinecone
    i pronalazi konflikte između dokumenata.
    """
    supa = _get_supa()
    user_id = user["user_id"]

    # Fetch storage_path for requested doc ids, scoped to this predmet + user
    def _fetch_docs():
        return (
            supa.table("predmet_dokumenti")
            .select("id,naziv_fajla,storage_path")
            .eq("predmet_id", req.predmet_id)
            .eq("user_id", user_id)
            .in_("id", req.dokument_ids)
            .execute()
        )

    try:
        docs_r = await asyncio.to_thread(_fetch_docs)
    except Exception:
        logger.exception("[CROSS_DOC] DB greška pri dohvatanju dokumenata")
        raise HTTPException(status_code=500, detail="Greška pri čitanju dokumenata.")

    rows = docs_r.data or []
    if len(rows) < 2:
        raise HTTPException(
            status_code=422,
            detail="Potrebna su najmanje 2 dokumenta koja postoje u ovom predmetu.",
        )

    # Reconstruct text for each doc via Pinecone
    from routers.dokument import _fetch_session_tekst

    async def _get_tekst(row: dict) -> tuple[str, str]:
        storage_path = row.get("storage_path", "")
        session_id = storage_path.replace("session/", "", 1) if storage_path else ""
        if not session_id:
            return row.get("naziv_fajla", "Dokument"), ""
        tekst = await asyncio.to_thread(_fetch_session_tekst, session_id)
        # AKCIJA 2 (2026-07-24): ranije [:4000] je bilo tvrdo sečenje BEZ
        # ikakvog uzorkovanja -- za dokument od 100 strana to je bilo ~2
        # strane, ostatak tiho odbačen. Sada se pun tekst (do Pydantic
        # max_length=100_000 na DokumentUnos.tekst) prosleđuje dalje, a
        # PAMETNO uzorkovanje (_uzorkuj_dokument, segment-bazirano preko
        # celog dokumenta) se dešava jednom, u _format_dokumenti -- ne ovde.
        return row.get("naziv_fajla", "Dokument"), tekst[:100_000]

    tekst_results = await asyncio.gather(*[_get_tekst(r) for r in rows])

    # Drop docs with no text
    dokumenti = [
        DokumentUnos(naziv=naziv, tekst=tekst)
        for naziv, tekst in tekst_results
        if tekst and len(tekst.strip()) >= 10
    ]

    if len(dokumenti) < 2:
        raise HTTPException(
            status_code=422,
            detail="Nije moguće rekonstruisati tekst za dovoljno dokumenata. Proverite da li su dokumenti pravilno indeksirani.",
        )

    # S6-P3 (2026-08-09): bind the AI operation to the case it belongs to.
    #
    # This file had ZERO case_context declarations, so every cross-document
    # analysis produced a provenance row with predmet_id NULL — the audit trail
    # could not answer which case an AI comparison of two client documents was
    # performed for.
    #
    # req.predmet_id is authoritative here, not asserted: the document fetch
    # above filters .eq("predmet_id", req.predmet_id).eq("user_id", user_id) and
    # raises 422 unless at least two rows come back, so a predmet belonging to
    # another user yields no rows and the request fails BEFORE this point. The
    # ownership check is the existing one; nothing about authorization changed.
    from shared.ai_provenance import case_context as _ai_case_ctx

    try:
        with _ai_case_ctx(
            predmet_id=req.predmet_id,
            module_name="cross_doc",
            operation_name="cross_doc_predmet",
        ):
            result = await asyncio.to_thread(
                _cross_doc_sync,
                dokumenti,
                req.pravno_pitanje,
                None,
            )
        await UsageService.consume(user["user_id"], user.get("email", ""), "cross_doc")
        return result
    except Exception:
        logger.exception("Greška u /api/analiza/cross-doc/predmet")
        return JSONResponse(
            status_code=500,
            content={"error": "Greška pri analizi dokumenata. Pokušajte ponovo."},
        )
