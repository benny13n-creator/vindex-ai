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
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from security.html_sanitize import sanitize_user_input
from shared.deps import _audit, _get_supa, _q_hash, get_current_user
from shared.rate import limiter
from shared.permissions import PermissionService
from shared.usage import UsageService
from shared.sentry import capture_exception as _sentry_capture
from shared.llm_retry import llm_retry

from main import ask_analiza, _skini_pii
from drafting.router import generate_draft as _drafting_generate
from drafting.templates import get_types_list as _drafting_get_types
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

# Program Phoenix, Mission 015 (LIVINGSYS-DEBT-031) / Phoenix Closure
# (LIVINGSYS-DEBT-028): shared window for "treat a 2nd identical-shape request
# within this many seconds as the same retry, not a new one" -- was
# _stage_draft_for_review's own function-local constant, hoisted here so the
# NEW pre-GPT-call check below (LIVINGSYS-DEBT-028) reuses the exact same
# value instead of guessing a 2nd one.
_STAGING_RETRY_WINDOW_SECONDS = 30


async def _recent_generation_exists(user_id: str, predmet_id: str, tip: str) -> bool:
    """Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-028): distinct from
    _stage_draft_for_review's own duplicate check below (-031, Mission 015),
    which only guards the STAGING insert AFTER the GPT call already ran. This
    checks the SAME staging_memory table for the SAME (user_id, predmet_id,
    tip) recent-window match, but BEFORE the expensive GPT generation call
    even starts -- a user-triggered retry (double-click, "Generiši" again
    after a network hiccup) no longer pays for a 2nd full generation just to
    have -031's own guard discard it a moment later. Fail-open on any DB
    error (never block a legitimate generation over a transient read glitch)."""
    if not predmet_id:
        return False
    try:
        supa = _get_supa()
        from datetime import datetime as _dt_stg, timedelta as _td_stg, timezone as _tz_stg
        _recent_cutoff = (_dt_stg.now(_tz_stg.utc) - _td_stg(seconds=_STAGING_RETRY_WINDOW_SECONDS)).isoformat()
        _dup_r = await asyncio.to_thread(
            lambda: supa.table("staging_memory").select("id")
                .eq("user_id", user_id).eq("predmet_id", predmet_id).eq("tip", tip)
                .gte("created_at", _recent_cutoff)
                .limit(1).execute()
        )
        return bool(_dup_r.data)
    except Exception as _exc:
        logger.warning("[DRAFTING] _recent_generation_exists provera neuspešna (nastavljam): %s", _exc)
        return False


@llm_retry
def _pozovi_drafting_api(client, **kwargs):
    """Zajednički retry-zaštićen poziv za sync OpenAI pozive u ovom fajlu
    (sazmi, podnesak ekstrakcija/obogaćivanje).

    CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške.
    """
    return client.chat.completions.create(**kwargs)


# ── Models ────────────────────────────────────────────────────────────────────

class NacrtReq(BaseModel):
    vrsta: str = Field(..., min_length=2, max_length=200)
    opis:  str = Field(..., min_length=10, max_length=5000)
    # Institutional Memory V2 (2026-07-26): opciono -- ako je prosleđen,
    # generisani nacrt ide u staging_memory na advokatsku overu (v.
    # _stage_draft_for_review niže) umesto da se odmah zaboravi. Bez ovoga
    # ponašanje je nepromenjeno (samo generiši i vrati tekst).
    predmet_id: Optional[str] = Field(None, max_length=100)

    @field_validator("vrsta", "opis")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return sanitize_user_input(v.strip()) or ""


class AnalizaReq(BaseModel):
    tekst:   str = Field(..., min_length=10, max_length=50000)
    pitanje: str = Field("", max_length=1000)

    @field_validator("tekst", "pitanje")
    @classmethod
    def ocisti(cls, v: str) -> str:
        return sanitize_user_input(v.strip()) or ""


class FeedbackReq(BaseModel):
    pitanje: str = Field("", max_length=2000)
    odgovor: str = Field("", max_length=5000)
    tip:     str = Field("greska", max_length=50)

    @field_validator("pitanje", "odgovor")
    @classmethod
    def _sanitize(cls, v: str) -> str:
        return sanitize_user_input(v) or ""


class PodnesakReq(BaseModel):
    tip:        str           = Field(..., max_length=50)
    opis:       str           = Field(..., min_length=20, max_length=5000)
    sud_naziv:  Optional[str] = Field(None, max_length=200)
    sud_adresa: Optional[str] = Field(None, max_length=300)
    # Institutional Learning & RAG Audit (2026-07-26) #3 — v. NacrtReq.predmet_id.
    predmet_id: Optional[str] = Field(None, max_length=100)

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
        return sanitize_user_input(v.strip()) or ""

    @field_validator("sud_naziv", "sud_adresa")
    @classmethod
    def ocisti_sud(cls, v: Optional[str]) -> Optional[str]:
        return sanitize_user_input(v.strip()) if v else None


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
        return sanitize_user_input(v.strip()) or ""


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
    # Program Phoenix, Mission 010 (LIVINGSYS-DEBT-013): generate_draft() now
    # runs its own critique pass and reports whether it verified the draft --
    # forward it through so /api/nacrt's frontend can show the same
    # not-verified warning /api/podnesak already gained in Mission 009.
    if isinstance(rezultat, dict) and "critique_applied" in rezultat:
        resp["critique_applied"] = rezultat["critique_applied"]
    # Final Beta Gate F4 (MEDIUM): drafting had no ai_generated marker in its
    # JSON response (only an in-DOCX footer, not visible pre-export) -- other
    # AI surfaces (digital_twin, court_predictor, hearing_cc) already carry
    # this disclosure since Phoenix Closure's LIVINGSYS-DEBT-025.
    if isinstance(rezultat, dict) and rezultat.get("status") == "success":
        resp["ai_generated"] = True
    return resp


def _greska_odgovor(status_code: int, poruka: str) -> JSONResponse:
    logger.warning("API greška %d: %s", status_code, poruka)
    return JSONResponse(status_code=status_code, content={"greska": poruka})


# Institutional Memory Architecture V2 (2026-07-26), STUB 1 — Quality Gate &
# Staging Memory. ZAMENJUJE raniju _index_finalized_draft (Institutional
# Learning & RAG Audit, 2026-07-25), koja je AI-generisan nacrt indeksirala
# DIREKTNO u kancelarija_{id}/user_{id} Pinecone namespace čim je predmet_id
# prosleđen -- to je tačno "toksično učenje" rizik koji V2 sprečava: nikad
# više se sirov, neproveren AI tekst ne upisuje u glavnu bazu znanja.
# Sada: finalizovan nacrt ide u staging_memory (migracija 088) sa
# automatskim Quality Gate skorom (services/quality_gate.py) i čeka
# eksplicitnu advokatsku potvrdu (v. POST /api/staging/{id}/approve) PRE
# nego što ijedan vektor uđe u Pinecone.
async def _stage_draft_for_review(user: dict, predmet_id: str, tip: str, naziv: str, tekst: str,
                                  dodatni_detalj: dict | None = None) -> None:
    """Fire-and-forget (asyncio.create_task) -- ne sme da uspori odgovor
    korisniku niti da greška ovde ikad utiče na već generisan i vraćen nacrt."""
    try:
        supa = _get_supa()
        pred_row = await asyncio.to_thread(
            lambda: supa.table("predmeti").select("id").eq("id", predmet_id).eq("user_id", user["user_id"]).maybe_single().execute()
        )
        if not pred_row.data:
            logger.warning("[STAGING] predmet_id=%s ne pripada korisniku — preskočeno", predmet_id)
            return

        # Program Phoenix, Mission 015 (LIVINGSYS-DEBT-031): a user-triggered retry
        # (double-click, or a genuine "Generiši" retry after a network hiccup) fires
        # this fire-and-forget staging insert again with no idempotency check --
        # 2 near-duplicate drafts of the SAME type for the SAME case land in the
        # lawyer's review queue for what was conceptually one action. GPT output
        # isn't deterministic, so the "identical text" dedup idiom used elsewhere
        # in this codebase (rocista.py, case_evolution.py) doesn't directly apply;
        # instead, treat a 2nd (predmet_id, tip) staging entry within a short
        # window as the same retry, not a new draft. (_STAGING_RETRY_WINDOW_SECONDS
        # is now a module-level constant, shared with _recent_generation_exists.)
        from datetime import datetime as _dt_stg, timedelta as _td_stg, timezone as _tz_stg
        _recent_cutoff = (_dt_stg.now(_tz_stg.utc) - _td_stg(seconds=_STAGING_RETRY_WINDOW_SECONDS)).isoformat()
        _dup_r = await asyncio.to_thread(
            lambda: supa.table("staging_memory").select("id")
                .eq("user_id", user["user_id"]).eq("predmet_id", predmet_id).eq("tip", tip)
                .gte("created_at", _recent_cutoff)
                .limit(1).execute()
        )
        # MIR001 R4: AI radni predlog iz spisa je NAPLAĆEN pre ovog upisa — tiho odbacivanje bi značilo naplatu bez
        # predloga na pregledu. Mrežno ponavljanje istog zahteva već zaustavlja `Idempotency-Key`, a drugi klik u prozoru
        # `run_agent` odbija PRE modela i naplate; ako ipak stigne (trka pre ovog upisa), svaka naplata ima svoj predlog.
        if _dup_r.data and tip != "nacrt_iz_spisa":
            logger.info(
                "[STAGING] predmet=%s tip=%s -- duplikat unutar %ds prozora, preskočeno (id=%s)",
                predmet_id, tip, _STAGING_RETRY_WINDOW_SECONDS, _dup_r.data[0]["id"],
            )
            return

        from services.quality_gate import evaluate_draft_quality
        from shared.kancelarija_utils import get_kancelarija_id

        quality = await evaluate_draft_quality(tekst, tip)
        kancelarija_id = await get_kancelarija_id(supa, user["user_id"])

        await asyncio.to_thread(
            lambda: supa.table("staging_memory").insert({
                "user_id": user["user_id"],
                "kancelarija_id": kancelarija_id,
                "predmet_id": predmet_id,
                "tip": tip,
                "naziv": naziv,
                "tekst": tekst,
                "confidence_score": quality["confidence_score"],
                # C3b FINAL CLOSURE: AI radni predlog nosi i svoj snimak (`predlog`) — v. shared/usvajanje_nacrta
                "quality_detail": {**(quality["detail"] or {}), **(dodatni_detalj or {})},
            }).execute()
        )
        logger.info(
            "[STAGING] predmet=%s tip=%s confidence=%.2f -- čeka advokatsku potvrdu",
            predmet_id, tip, quality["confidence_score"],
        )
        # Mission Migration (2026-08-03) -- Canonical AI Infrastructure
        # Adoption: durable audit entry for the drafting decision, carrying
        # quality_gate's already-computed confidence_score in metadata (the
        # one AI feature in this codebase with a real confidence signal
        # already available, per Mission Atlas's ATLAS-002 finding).
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(
            action="drafting_generisan", user_id=user["user_id"],
            resource_type="predmet", resource_id=predmet_id,
            metadata={"tip": tip, "confidence_score": quality["confidence_score"]},
        ))
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[STAGING] neuspešno (non-fatal) predmet=%s: %s", predmet_id, exc)


_APPROVAL_CONFIDENCE_THRESHOLD = 0.85
_TIP_IZ_SPISA = "nacrt_iz_spisa"      # = routers.multi_agent._TIP_NACRTA_IZ_SPISA
_TIP_DOKUMENT_ZA_SUD = "dokument_za_sud"   # = shared.usvajanje_nacrta.TIP_DOKUMENTA_ZA_SUD


def _putanja_nacrta(staging_id) -> str:
    return f"draft/staging/{staging_id}"


def _red_nacrta(supa, predmet_id, putanja: str):
    r = (supa.table("predmet_dokumenti").select("id").eq("predmet_id", predmet_id)
         .eq("storage_path", putanja).limit(1).execute())
    d = getattr(r, "data", None)
    return d[0] if isinstance(d, list) and d and isinstance(d[0], dict) else None


def _azuriraj_red_nacrta(supa, postojeci: dict, red: dict) -> None:
    polja = {k: v for k, v in red.items() if k in ("status", "naziv_fajla", "pinecone_namespace", "velicina_kb",
                                                   "tekst_sadrzaj", "tip_dokaza")}
    supa.table("predmet_dokumenti").update(polja).eq("id", postojeci["id"]).execute()


# NS4 O3: oporavljiva promocija. Jedan aktivan pokušaj po nacrtu (`staging_memory.promocija_token`, migracija 140):
# prvo odobrenje ga uzima zajedno sa prelaskom pending → approved, ponovni upis atomski preko
# `preuzmi_ponovni_upis_nacrta` (samo podoban nacrt), a zatvara ga SAMO isti token (`zavrsi_promociju_nacrta`) —
# zastareo radnik ne prepisuje noviji ishod. Napušten pokušaj (pad procesa) može se preuzeti posle roka.
# Identitet vektora je stabilan (predmet + heš teksta + redni broj dela) → ponovni upis prepisuje, ne duplira.
# Ovo je „bar jednom + idempotentno", NE „tačno jednom" preko PostgreSQL-a i Pinecone-a.
_PROMOCIJA_ISTEK_S = 600


async def _zavrsi_promociju(supa, staging_id: str, token: str, indeksiran: bool) -> bool:
    r = await asyncio.to_thread(lambda: supa.rpc("zavrsi_promociju_nacrta", {
        "p_staging_id": staging_id, "p_token": token, "p_indeksiran": bool(indeksiran)}).execute())
    d = getattr(r, "data", None)
    return (d[0] if isinstance(d, list) and d else d) is True


def _ponovni_upis_moguc(red: dict) -> bool:
    """Podobnost za ponovni upis iz POSTOJEĆIH kolona (za prikaz dugmeta); konačnu odluku donosi atomsko
    preuzimanje u bazi (uključuje i „pokušaj u toku")."""
    try:
        ocena = float(red.get("confidence_score") or 0)
    except (TypeError, ValueError):
        return False
    return (red.get("status") == "approved" and red.get("is_lawyer_approved") is True
            and red.get("pinecone_indexed") is not True and ocena >= _APPROVAL_CONFIDENCE_THRESHOLD
            and red.get("tip") not in (_TIP_IZ_SPISA, _TIP_DOKUMENT_ZA_SUD))   # MIR001 T06/C3b: nikad u znanje


async def _promote_staged_draft_to_pinecone(supa, staging_row: dict) -> bool:
    """Poziva se SAMO iz POST /api/staging/{id}/approve, i SAMO ako
    is_lawyer_approved=True I confidence_score >= 0.85 (oba uslova, v.
    migracija 088). Indeksira pod origin=LAWYER_VERIFIED (ne AI_GENERATED --
    upravo je prošao ljudsku overu), sa parent_id/origin_chain koji čuvaju
    da je tekst NASTAO kao AI_GENERATED pre nego što je postao
    LAWYER_VERIFIED (STUB 2 -- lineage protiv AI-to-AI degeneracije: budući
    retrieval uvek zna da je ovo poreklo bilo AI, ne izvorni advokatski rad
    od nule). Vraća True ako je Pinecone upis uspeo."""
    from uploaded_doc.chunker import chunk_document
    from uploaded_doc.ingest import ingest_session
    from uploaded_doc.session import generate_session_id
    from shared.kancelarija_utils import rag_owner_namespace
    from shared.vector_origin import ORIGIN_LAWYER_VERIFIED, ORIGIN_AI_GENERATED, now_iso

    predmet_id = staging_row["predmet_id"]
    user_id = staging_row["user_id"]
    kancelarija_id = staging_row.get("kancelarija_id")
    tekst = staging_row["tekst"]
    naziv = staging_row.get("naziv") or staging_row.get("tip") or "Nacrt"

    # BETA-DATA-ID-01: `source_sha256` je ranije bio prazan string, jer nacrt ne
    # dolazi iz fajla. Otkad identitet vektora zavisi od verzije sadrzaja
    # (`shared/vector_identity.py`), prazna verzija znaci "nema identiteta" i
    # ingest se fail-closed odbija -- pa bi promocija odobrenog nacrta tiho
    # prestala da radi (izuzetak se nize guta i vraca False).
    #
    # Nacrt SVOJ sadrzaj i jeste njegova verzija: hes teksta daje istu
    # semantiku kao hes fajla kod uploada -- ponovna promocija istog teksta
    # prepisuje umesto da duplira, izmenjen tekst pravi novu verziju.
    from shared.vector_identity import verzija_dokumenta as _verzija
    source_meta = {
        "source_filename": f"Nacrt — {naziv}", "source_format": "txt",
        "source_sha256": _verzija(tekst), "is_scanned": False,
        "session_id": "__local__",
    }
    manifest = await asyncio.to_thread(chunk_document, tekst, source_meta)
    if manifest.total_chunks == 0:
        return False

    owner_ns = rag_owner_namespace(user_id, kancelarija_id)
    session_id = generate_session_id()

    try:
        _upisano = await asyncio.to_thread(
            ingest_session, manifest, session_id,
            namespace_override=owner_ns,
            verzija_dokumenta_id=_verzija(tekst),
            extra_metadata={
                "predmet_id": predmet_id,
                "kancelarija_id": kancelarija_id or "",
                "type": "draft_final",
                "origin": ORIGIN_LAWYER_VERIFIED,
                "parent_id": staging_row["id"],
                "origin_chain": [ORIGIN_AI_GENERATED, ORIGIN_LAWYER_VERIFIED],
                "created_at": now_iso(),
                "golden_template": False,
            },
        )
    except Exception as pe:
        logger.warning("[STAGING_PROMOTE] Pinecone ingest neuspešan predmet=%s: %s", predmet_id, str(pe)[:150])
        return False

    # BETA-DATA-CONFIDENTIALITY-004 / SE-01: povratna vrednost `ingest_session`
    # se ovde uopste nije uzimala, a `status` je nize bio hard-kodovan literal
    # "indeksirano" -- dakle tvrdnja o pretrazivosti bez ijednog dokaza.
    from uploaded_doc.ingest import ingest_je_potpun as _potpun
    _indeksiran = _potpun(_upisano, manifest.total_chunks)
    if not _indeksiran:
        logger.error(
            "[STAGING_PROMOTE] nepotpun ingest predmet=%s: upisano %s od %s",
            predmet_id, _upisano, manifest.total_chunks,
        )

    try:
        _rn_res = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti").select("redni_broj").eq("predmet_id", predmet_id).order("redni_broj", desc=True).limit(1).execute()
        )
        next_rn = int((_rn_res.data or [{}])[0].get("redni_broj") or 0) + 1
    except Exception:
        next_rn = 1

    _dok_row = {
        "predmet_id": predmet_id, "user_id": user_id,
        "naziv_fajla": f"AI Nacrt (odobren) — {naziv}",
        # NS4 O3: stabilan identitet knjigovodstvenog reda nacrta (ranije `draft/<nasumičan session_id>` → svaki
        # ponovni pokušaj bi dodao nov red). Jedinstvenost sprovodi baza (migracija 140, delimični UNIQUE indeks).
        "storage_path": _putanja_nacrta(staging_row["id"]),
        "pinecone_namespace": owner_ns,
        "status": "indeksirano" if _indeksiran else "sacuvano",
        "velicina_kb": max(1, len(tekst.encode("utf-8")) // 1024),
        "redni_broj": next_rn, "tekst_sadrzaj": tekst[:100_000],
        # Program Intake Sprint 001 (2026-08-04) -- ovaj red je ranije
        # ostajao SA tip_dokaza=NULL trajno (Fork 1 finding: nijedan
        # background task ovde ne pokreće klasifikaciju, za razliku od
        # ostalih pisaca predmet_dokumenti). Ne pokrećemo novi AI poziv
        # da to popunimo (misija zabranjuje novu AI funkcionalnost) --
        # umesto toga, deterministički postavljamo vrednost koju već
        # 100% sa sigurnošću znamo iz konteksta ovog poziva: ovo je
        # advokatov odobren nacrt podneska, tačno 'podnesak' iz
        # POSTOJEĆEG dozvoljenog vokabulara (routers/evidence.py,
        # isti taj koji stvarni klasifikator koristi) -- ne nova reč.
        "tip_dokaza": "podnesak",
    }
    # NS4 O3: ponovni pokušaj (ili istovremeni pokušaj posle isteka roka) ažurira ISTI red umesto da doda nov.
    _postojeci_dok = await asyncio.to_thread(_red_nacrta, supa, predmet_id, _dok_row["storage_path"])
    if _postojeci_dok:
        await asyncio.to_thread(_azuriraj_red_nacrta, supa, _postojeci_dok, _dok_row)
        return _indeksiran
    try:
        await asyncio.to_thread(lambda: supa.table("predmet_dokumenti").insert(_dok_row).execute())
    except Exception as _ie:
        if "23505" in str(_ie):
            _postojeci_dok = await asyncio.to_thread(_red_nacrta, supa, predmet_id, _dok_row["storage_path"])
            if _postojeci_dok:      # drugi pokušaj je upisao isti red između čitanja i upisa
                await asyncio.to_thread(_azuriraj_red_nacrta, supa, _postojeci_dok, _dok_row)
                return _indeksiran
            raise                   # druga jedinstvenost (npr. redni_broj) — ne gutati
        # LAMBDA008-SCHEMA-001 defense-in-depth: mirrors api.py/smart_intake.py's own
        # column-may-not-exist fallback (migration 105 adds redni_broj/tekst_sadrzaj,
        # applied by the founder per this repo's standing convention, not automatically)
        # -- if it hasn't landed yet, don't lose the draft's Pinecone ingest (already
        # done above) over a missing-column error on the DB bookkeeping row alone.
        if "42703" in str(_ie) or "does not exist" in str(_ie).lower():
            logger.warning("[STAGING_PROMOTE] predmet_dokumenti insert bez redni_broj/tekst_sadrzaj (kolona ne postoji): predmet=%s", predmet_id)
            _dok_row.pop("redni_broj", None)
            _dok_row.pop("tekst_sadrzaj", None)
            await asyncio.to_thread(lambda: supa.table("predmet_dokumenti").insert(_dok_row).execute())
        else:
            raise
    # NS4-T5: uspeh promocije = dokument je CEO u indeksu. Ranije `return True` i kad je upisano manje delova od
    # očekivanog — ruta je tada tvrdila „dodat u bazu znanja“ i postavljala `pinecone_indexed=True`.
    return _indeksiran


# Program Phoenix, Mission 010 (LIVINGSYS-DEBT-013): _izvori_kontekst and
# _CRITIQUE_SYSTEM moved to shared/drafting_grounding.py as the single
# canonical owner -- drafting/router.py's /api/nacrt path now reuses the
# identical [IZVOR-n] format and critique prompt instead of a hand-copied
# divergent version.
from shared.drafting_grounding import izvori_kontekst as _izvori_kontekst, CRITIQUE_SYSTEM as _CRITIQUE_SYSTEM

# ── FAZA 3 (2026-07-24): Critique & Self-Correction pass za podneske ──────────


@llm_retry
async def _pozovi_kriticara(oai_client, nacrt: str, kontekst: str, tip_naziv: str) -> dict:
    """Retry-ovani deo critique pass-a -- izdvojen kao poseban helper (isti
    razlog kao services/legal_reasoning_engine.py::_pozovi_reasoning_api):
    _critique_and_refine_draft ima sopstveni try/except sa fallback-om na
    originalni nacrt, koji bi inače sakrio grešku od tenacity-ja."""
    resp = await asyncio.wait_for(
        asyncio.to_thread(
            lambda: oai_client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=4000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _CRITIQUE_SYSTEM},
                    {"role": "user", "content": (
                        f"VRSTA PODNESKA: {tip_naziv}\n\n"
                        f"IZVORI (RAG kontekst sa oznakama):\n"
                        f"{kontekst or '(nema dostavljenih izvora -- oslanjaj se samo na opšte pravno znanje)'}\n\n"
                        f"NACRT ZA PROVERU:\n{nacrt}"
                    )},
                ],
            )
        ),
        timeout=30.0,
    )
    raw = (resp.choices[0].message.content or "{}").strip()
    return json.loads(raw)


async def _critique_and_refine_draft(nacrt: str, kontekst: str, tip: str, log_id: str) -> tuple[str, bool]:
    """Drugi, brz LLM prolaz nad već generisanim nacrtom: proverava izmišljene
    članove zakona van [IZVOR-n] konteksta i obavezne formalne elemente
    podneska, i ispravlja ih ako postoje. Ako je nacrt besprekoran, vraća ga
    NEIZMENJEN (ignoriše model's "ispravljen_tekst" kad model sam prijavi da
    nema problema -- izbegava suvišno prepisivanje/drift). Nikad ne baca:
    svaka greška pada nazad na originalni nacrt umesto da blokira odgovor.

    Vraća (nacrt, critique_applied). Program Phoenix, Mission 009 (LIVINGSYS-DEBT-015):
    critique_applied=False znači da critique pass NIJE pouzdano potvrdio ovaj nacrt (exception,
    ili je model prijavio problem ali nije vratio ispravku) -- pre ove izmene oba slučaja su
    tiho vraćala neizmenjen nacrt sa nula signala da anti-halucinacija provera nije uspela."""
    try:
        from openai import OpenAI as _OAI
        oai_client = _OAI(api_key=os.getenv("OPENAI_API_KEY"))
        tip_naziv = PODNESAK_TIPOVI.get(tip, tip)
        kritika = await _pozovi_kriticara(oai_client, nacrt, kontekst, tip_naziv)

        izmisljeni = kritika.get("izmisljeni_navodi") or []
        nedostaje = kritika.get("nedostaju_elementi") or []
        ima_problema = bool(kritika.get("ima_izmisljenih_navoda")) or bool(izmisljeni) or bool(nedostaje)

        if not ima_problema:
            return nacrt, True

        ispravljen = (kritika.get("ispravljen_tekst") or "").strip()
        if not ispravljen:
            logger.warning(
                "Critique pass prijavio probleme ali nije vratio ispravljen tekst [q=%s]", log_id
            )
            return nacrt, False

        logger.info(
            "Critique pass ispravio nacrt [q=%s]: izmisljeni_navodi=%s nedostaju_elementi=%s",
            log_id, izmisljeni, nedostaje,
        )
        return ispravljen, True
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("Critique pass neuspešan [q=%s]: %s — vraćam originalni nacrt", log_id, exc)
        return nacrt, False


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/nacrt/types")
async def nacrt_types():
    """Vraća listu dostupnih tipova nacrta (bez autentifikacije)."""
    return {"tipovi": _drafting_get_types()}


@router.get("/api/podnesak/types")
async def podnesak_types():
    """Katalog tipova podnesaka -- isti ugovor kao `/api/nacrt/types`.

    Postoji zato sto je spisak dozvoljenih tipova do sada zivelo SAMO u
    validatoru `PodnesakReq.tip`. Frontend koji bi ga prepisao nudio bi tip
    koji server vise ne zna, i to bi se videlo tek posle klika -- kontrola
    koja pada na kraju umesto da se ne ponudi. Bez autentifikacije, kao i
    `/api/nacrt/types` i `/api/courts`.
    """
    return {"tipovi": [{"tip": k, "naziv": v} for k, v in PODNESAK_TIPOVI.items()]}


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
    from uploaded_doc.extractor import DocumentSafetyLimitExceeded, extract_docx, extract_txt

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

        try:
            if suffix == ".docx":
                tekst, _ = await asyncio.to_thread(extract_docx, tmp_path)
            else:
                tekst, _ = await asyncio.to_thread(extract_txt, tmp_path)
        except DocumentSafetyLimitExceeded:
            raise HTTPException(
                status_code=413,
                detail="Fajl je odbijen — sadržaj posle raspakivanja prelazi bezbednosni limit.",
            )

        if not tekst or not tekst.strip():
            raise HTTPException(status_code=422, detail="Fajl je prazan ili nečitljiv")

        from drafting.playbook import ingest_playbook
        count = await asyncio.to_thread(ingest_playbook, user["user_id"], file.filename or "", tekst)
        return {"filename": file.filename, "chunks_ingested": count}
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception as _exc:
                _sentry_capture(_exc)
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
        except Exception as _exc:
            _sentry_capture(_exc)
            return {"has_playbook": False, "chunk_count": 0}
    return await asyncio.to_thread(_check)


@router.post("/api/nacrt")
@limiter.limit("10/minute")
async def nacrt(req: NacrtReq, request: Request, user: dict = Depends(PermissionService.require("drafting"))):
    """Generisanje nacrta pravnog dokumenta (strukturirani šablon)."""
    logger.info("Nacrt [uid=%.8s] vrsta=%s", user["user_id"], req.vrsta)
    asyncio.create_task(_audit(user["user_id"], f"nacrt:{req.vrsta}", ""))
    try:
        # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-028): a user-triggered
        # retry (double-click, "Generiši" again after a slow response) used to
        # pay for a full 2nd GPT generation only to have -031's own staging
        # guard silently discard the result a moment later. Checked BEFORE the
        # generation call, scoped identically to -031 (only when predmet_id is
        # set -- the case-less/ad-hoc path is intentionally left alone).
        # S6C-1 (2026-08-09): AUTHORIZATION BEFORE ANYTHING ELSE TOUCHES predmet_id.
        #
        # req.predmet_id is Optional[str] = Field(None, max_length=100) -- a free
        # string from the request body. Until now nothing verified it belonged to
        # the caller before the GPT call, and the only ownership check in this
        # file lives inside _stage_draft_for_review, which runs AFTER generation
        # and as a fire-and-forget task.
        #
        # The order was SUBJECT (unverified) -> AI -> OWNERSHIP. So the
        # case_context binding below recorded provenance against a predmet the
        # caller had not been shown to own: user B could send user A's predmet
        # UUID and write audit rows attributed to A's case. No data leaked --
        # the AI only ever sees req.opis, text the caller supplied -- but the
        # audit trail is exactly the thing that must not be forgeable.
        #
        # Reuses the existing canonical check rather than adding another one:
        # routers/copilot_ambient.py::_proveri_vlasnistvo_predmeta, whose own
        # docstring names the pattern ("predmet_id iz zahteva se NIKAD ne
        # prihvata bez provere da pripada pozivaocu"). Imported lazily, as this
        # codebase does elsewhere, to avoid an import cycle between routers.
        #
        # predmet_id=None keeps its existing behaviour untouched: the case-less
        # ad-hoc drafting path is legitimate and stays unverified AND unbound.
        if req.predmet_id:
            from routers.copilot_ambient import _proveri_vlasnistvo_predmeta
            await _proveri_vlasnistvo_predmeta(req.predmet_id, user["user_id"])

        if req.predmet_id and await _recent_generation_exists(user["user_id"], req.predmet_id, req.vrsta):
            _staged = await asyncio.to_thread(
                lambda: _get_supa().table("staging_memory").select("tekst")
                    .eq("user_id", user["user_id"]).eq("predmet_id", req.predmet_id).eq("tip", req.vrsta)
                    .order("created_at", desc=True).limit(1).execute()
            )
            _tekst = (_staged.data or [{}])[0].get("tekst") if _staged.data else None
            if _tekst:
                _preostalo = await UsageService.balance(user["user_id"], user.get("email", ""))
                return _normalizuj_rezultat({"status": "success", "data": _tekst}, credits_remaining=max(_preostalo, 0))
        # Project Phoenix (2026-08-03) — Phase 8: migrates the deep
        # generation call itself (previously only the router-level staging
        # step, _stage_draft_for_review, had audit/case-context wiring --
        # this closes the gap for the raw generate call, including the
        # case-less/ad-hoc draft path staging never covers).
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(predmet_id=req.predmet_id, module_name="drafting", operation_name="nacrt"):
            rezultat = await _pokreni(_drafting_generate, req.vrsta, _skini_pii(req.opis), user["user_id"])
        # Program Phoenix, Mission 004 (LIVINGSYS-DEBT-002): this used to charge a credit
        # unconditionally regardless of rezultat.get("status") -- generate_draft() never raises
        # on failure (OpenAI timeout/error/unknown vrsta all become {"status":"error",...}), so
        # every one of those failure paths still charged the lawyer for zero output. The
        # sibling analiza() 35 lines below already gates correctly -- same pattern applied here.
        _ok = isinstance(rezultat, dict) and rezultat.get("status") == "success" and rezultat.get("data")
        if _ok:
            preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(
                action="drafting_nacrt", user_id=user["user_id"],
                resource_type="predmet" if req.predmet_id else "nacrt",
                resource_id=req.predmet_id, metadata={"vrsta": req.vrsta},
            ))
            if req.predmet_id:
                asyncio.create_task(_stage_draft_for_review(user, req.predmet_id, req.vrsta, req.vrsta, rezultat["data"]))
        else:
            preostalo = await UsageService.balance(user["user_id"], user.get("email", ""))
        return _normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except HTTPException:
        # F-6H-001 (Sprint 6H forensics): HTTPException nasleđuje Exception, pa
        # je 404 iz _proveri_vlasnistvo_predmeta (iznad, u istom try bloku) padao
        # u generičku granu ispod i vraćao se kao 500 "greška na serveru".
        # Odbijanje autorizacije je i dalje bilo fail-closed -- ni provider ni
        # consume nisu dosezani jer oba leže iza tačke podizanja -- ali je napad
        # izgledao kao sopstveni kvar i punio Sentry preko logger.exception.
        # Namerne HTTP greške propagiraju netaknute; sve ostalo ide kao i pre.
        raise
    except Exception as _exc:
        _sentry_capture(_exc)
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
        # Project Phoenix (2026-08-03) — Phase 8, same reasoning as nacrt()
        # above: no predmet_id by design (AnalizaReq has no case-scope
        # field), matching Strategy Engine's own precedent.
        from shared.ai_provenance import case_context as _ai_case_ctx
        with _ai_case_ctx(module_name="drafting", operation_name="analiza"):
            rezultat = await _pokreni(ask_analiza, req.tekst, req.pitanje)
        is_blocked = (rezultat.get("data") or "").startswith("[!] ANALIZA BLOKIRANA")
        if rezultat.get("status") == "success" and not is_blocked:
            preostalo = await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")
            from shared.audit_immutable import log_action
            asyncio.create_task(log_action(action="drafting_analiza", user_id=user["user_id"], resource_type="analiza"))
        else:
            preostalo = await UsageService.balance(user["user_id"], user.get("email", ""))
        return _normalizuj_rezultat(rezultat, credits_remaining=max(preostalo, 0))
    except HTTPException:
        # F-6J-004 (Sprint 6J forensics): HTTPException nasleđuje Exception, pa
        # su naplatne greške iz UsageService.consume (iznad) padale u granu
        # ispod i vraćale se kao generički 500. consume diže 402 (nema kredita)
        # i 429 (cooldown/dnevni/mesečni limit) i jedini je izvor HTTPException
        # u ovom bloku -- balance ne diže nijednu, a AnalizaReq nema predmet_id
        # pa nema ni vlasničke provere koju bi ovo moglo da promeni.
        raise
    except Exception as _exc:
        _sentry_capture(_exc)
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
        # BUG FIX (2026-07-24): sinhroni SDK poziv unutar async def blokirao je
        # ceo event loop (i sve druge konkurentne zahteve na istom workeru) za
        # trajanje OpenAI poziva -- ostala 3 poziva u ovom fajlu (linije ~443,
        # 458, 507) su već ispravno await asyncio.to_thread(...)-ovana.
        resp = await asyncio.to_thread(
            _pozovi_drafting_api,
            client,
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
    except HTTPException:
        # F-6J-005, isto kao /api/analiza gore. SazmiReq nosi samo odgovor+format
        # -- nema subjekta ni vlasničke provere, pa je consume jedini izvor
        # HTTPException u ovom bloku.
        raise
    except Exception as _exc:
        _sentry_capture(_exc)
        logger.exception("Greška u /api/sazmi")
        return _greska_odgovor(500, "Greška pri generisanju sažetka.")


@router.post("/api/feedback")
async def feedback(req: FeedbackReq, user: dict = Depends(get_current_user)):
    """
    Korisnik prijavljuje netačan ili nepotpun odgovor.
    NO-STORAGE POLICY (Basic API tier): čuvamo samo hash pitanja i tip — bez sadržaja.
    ZZPL čl. 5(1)(c) — minimizacija podataka.
    """
    qh = _q_hash(req.pitanje)
    try:
        _ins = await asyncio.to_thread(
            lambda: _get_supa().table("feedback").insert({
                "user_id": user["user_id"],
                "q_hash":  qh,
                "tip":     req.tip,
            }).execute()
        )
        # BETA-P1-FEEDBACK-TRUTH: prazan `data` znaci da nijedan red nije upisan.
        if not getattr(_ins, "data", None):
            raise RuntimeError("upis nije vratio nijedan red")
    except Exception as _exc:
        # BETA-P1-FEEDBACK-TRUTH.
        #
        # Ovde je ranije stajalo `return {"status": "ok"}` -- doslovno ista
        # vrednost kao kod uspeha. Kolona `q_hash` NE POSTOJI u produkciji
        # (mereno: `feedback` ima samo id, user_id, tip, created_at), pa je
        # SVAKI poziv padao na 42703 i svaki je javljao „ok".
        #
        # Ovo je jedini kanal kojim advokat prijavljuje POGRESAN PRAVNI SADRZAJ.
        # Tisina na tom kanalu znaci da mi ne saznajemo za netacne odgovore, a
        # korisnik veruje da jesmo. Zato neuspeh sada IZLAZI iz funkcije.
        _sentry_capture(_exc)
        logger.error("[FEEDBACK] prijava NIJE zabelezena [uid=%.8s] [q=%s]: %s",
                     user["user_id"], qh, _exc)
        return _greska_odgovor(
            503, "Prijava NIJE zabeležena. Pokušajte ponovo ili nam pišite na "
                 "benny13.n@gmail.com.")

    logger.info("Feedback [uid=%.8s] tip=%s [q=%s]", user["user_id"], req.tip, qh)
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

    # Phoenix Closure (2026-08-08, LIVINGSYS-DEBT-028): same reasoning as
    # nacrt()'s own pre-check above -- /api/podnesak is the MORE expensive of
    # the 2 (2 sequential GPT calls: extraction + RAG-grounded enrichment),
    # making a wasted retry here more costly, not less.
    # S6C-1: same authorization precondition as nacrt() above. /api/podnesak
    # produces a court filing, so an audit row attributed to the wrong case is
    # worse here, not better. Same canonical check, same lazy import, same
    # untouched behaviour when predmet_id is absent.
    if req.predmet_id:
        from routers.copilot_ambient import _proveri_vlasnistvo_predmeta
        await _proveri_vlasnistvo_predmeta(req.predmet_id, user["user_id"])

    if req.predmet_id and await _recent_generation_exists(user["user_id"], req.predmet_id, req.tip):
        _staged = await asyncio.to_thread(
            lambda: _get_supa().table("staging_memory").select("tekst")
                .eq("user_id", user["user_id"]).eq("predmet_id", req.predmet_id).eq("tip", req.tip)
                .order("created_at", desc=True).limit(1).execute()
        )
        _tekst = (_staged.data or [{}])[0].get("tekst") if _staged.data else None
        if _tekst:
            return {
                "status":  "success",
                "odgovor": _tekst,
                "tip":     req.tip,
                "naziv":   PODNESAK_TIPOVI[req.tip],
                "critique_applied": None,
                "ai_generated": True,
            }

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

    # S6C-2 (2026-08-09): ONE case_context scope over the WHOLE AI sequence.
    #
    # Pre-flight found this endpoint makes FIVE provider-touching calls, not
    # one: two _pozovi_drafting_api extractions, retrieve_documents (which runs
    # its own embedding + query-decomposition LLM calls), the enrichment call,
    # and _critique_and_refine_draft. All five belong to the SAME predmet, so a
    # single scope is correct and per-call wrapping would be both noisier and
    # easier to leave incomplete.
    #
    # That is why this diff re-indents a block instead of adding one line: the
    # scope has to span the sequence. No logic inside it changed -- the diff is
    # indentation plus this comment.
    #
    # req.predmet_id is VERIFIED, not merely present: _proveri_vlasnistvo_predmeta
    # ran at the top of this handler (S6C-1) and raises 404 unless the predmet
    # belongs to the caller. predmet_id=None keeps its existing behaviour and
    # stays unbound -- no fake subject is invented for the ad-hoc path.
    from shared.ai_provenance import case_context as _ai_case_ctx
    with _ai_case_ctx(
        predmet_id=req.predmet_id,
        module_name="drafting",
        operation_name="podnesak",
    ):
        try:
            ekstr_resp = await asyncio.to_thread(
                _pozovi_drafting_api,
                oai,
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=900,
                messages=[
                    {"role": "system", "content": ekstr_prompt},
                    {"role": "user",   "content": f"OPIS SLUČAJA:\n{opis_api}{sud_ctx}"},
                ],
            )
            raw_json = (ekstr_resp.choices[0].message.content or "").strip()
            entiteti: dict = _parse_json_safe(raw_json)
            if not entiteti:
                logger.warning("Ekstrakcija vratila prazan JSON [q=%s] — retry sa gpt-4o", log_id)
                ekstr_resp2 = await asyncio.to_thread(
                    _pozovi_drafting_api,
                    oai,
                    model="gpt-4o",
                    temperature=0,
                    max_tokens=900,
                    messages=[
                        {"role": "system", "content": ekstr_prompt},
                        {"role": "user",   "content": f"OPIS SLUČAJA:\n{opis_api}\n\nVrati ISKLJUČIVO validan JSON objekat, bez ikakvog drugog teksta."},
                    ],
                )
                entiteti = _parse_json_safe(ekstr_resp2.choices[0].message.content or "")
        except Exception as exc:
            _sentry_capture(exc)
            logger.warning("Ekstrakcija entiteta neuspešna [q=%s]: %s", log_id, exc)
            entiteti = {}

        rag_upit = f"{PODNESAK_TIPOVI[req.tip]}: {opis_api[:400]}"
        try:
            from app.services.retrieve import retrieve_documents
            # BUG FIX (2026-07-24): retrieve_documents vraća tuple[list[str], dict]
            # (docs, retrieval_meta), ne samu listu -- pre ove izmene je "docs"
            # bio ceo tuple, "\n\n".join(docs[:4]) je pucao sa TypeError na dict
            # elementu, spoljašnji except je to tiho gutao i kontekst je UVEK bio
            # prazan string. Svaki podnesak generisan pre ove izmene je pisan bez
            # ijednog stvarnog RAG zakonskog citata, uprkos promptu koji to
            # eksplicitno traži.
            docs, _retrieval_meta = await asyncio.to_thread(retrieve_documents, rag_upit, 5)
            kontekst = _izvori_kontekst(docs)
        except Exception as exc:
            _sentry_capture(exc)
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
                _sentry_capture(exc)
                logger.warning("VKS preporuka neuspešna [q=%s]: %s", log_id, exc)

        obog_prompt = OBOGACIVANJE_PROMPTOVI[req.tip]
        obog_user = (
            f"EKSTRAKTOVANI PODACI (JSON):\n{json.dumps(entiteti, ensure_ascii=False)}"
            f"{vks_kontekst_blok}\n\n"
            f"ZAKONSKI KONTEKST (RAG):\n{kontekst or 'Nije pronađen relevantan kontekst.'}"
        )
        try:
            obog_resp = await asyncio.to_thread(
                _pozovi_drafting_api,
                oai,
                model="gpt-4o",
                temperature=0,
                max_tokens=2500,
                messages=[
                    {"role": "system", "content": obog_prompt},
                    {"role": "user",   "content": obog_user},
                ],
            )
            raw_obog = (obog_resp.choices[0].message.content or "").strip()
            raw_obog = raw_obog.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            obogacivanje: dict = json.loads(raw_obog)
        except (json.JSONDecodeError, Exception) as exc:
            _sentry_capture(exc)
            logger.warning("Obogaćivanje neuspešno [q=%s]: %s", log_id, exc)
            obogacivanje = {}

        nacrt = popuni_sablon(req.tip, entiteti, obogacivanje, vks_analiza=vks_analiza)
        nacrt, critique_applied = await _critique_and_refine_draft(nacrt, kontekst, req.tip, log_id)

    # Program Phoenix, Mission 004 (LIVINGSYS-DEBT-027): this charged unconditionally even
    # when entity extraction (the step whose failure makes the draft closest to worthless --
    # a template with no real case facts filled in, just placeholders) silently degraded to
    # an empty dict. Output here is never literally zero (unlike /api/nacrt's own failure
    # mode, LIVINGSYS-DEBT-002), so this only skips the charge for the specific worst case,
    # not for RAG/VKS/enrichment individually degrading -- those still produce a
    # substantially useful draft and are still charged, matching this debt item's own
    # "Medium, not High" severity distinction from -002.
    if entiteti:
        await UsageService.consume(user["user_id"], user.get("email", ""), "drafting")
    else:
        logger.warning("Podnesak: naplata preskočena, ekstrakcija entiteta potpuno neuspešna [q=%s]", log_id)

    if req.predmet_id and nacrt:
        asyncio.create_task(_stage_draft_for_review(user, req.predmet_id, req.tip, PODNESAK_TIPOVI[req.tip], nacrt))

    return {
        "status":  "success",
        "odgovor": nacrt,
        "tip":     req.tip,
        "naziv":   PODNESAK_TIPOVI[req.tip],
        "critique_applied": critique_applied,
        "ai_generated": True,
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


def _nacrt_to_docx(tekst: str, naslov: str, firma_info: dict | None = None, za_sud: bool = False) -> bytes:
    """Konvertuje nacrt tekst u .docx sa kancelarijskim headerom. Vraća bytes.
    `za_sud=True` (C3b FINAL CLOSURE, samo odobren dokument za sud): bez automatskog naslova i bez sistemskog podnožja
    („Generisano … Vindex AI“) — telo je tačno odobren tekst; zaglavlje kancelarije (podaci korisnika) ostaje."""
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
    if not za_sud:
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
    if not za_sud:
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


async def _firma_za_zaglavlje(supa, uid: str):
    """Firma/SEF podaci za zaglavlje DOCX-a (ili None) — isti za izvoz teksta i za izvoz nacrta sa pregleda."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("sef_podesavanja")
                .select("seller_pib,seller_naziv,seller_adresa,seller_mesto")
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        if r and r.data:
            return r.data
    except Exception as _exc:
        _sentry_capture(_exc)
    return None


@router.post("/api/nacrti/export/docx")
@limiter.limit("30/minute")
async def export_nacrt_docx(
    req: DocxExportReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Preuzmi nacrt kao .docx fajl sa kancelarijskim headerom."""
    supa = _get_supa()
    firma_info = await _firma_za_zaglavlje(supa, user["user_id"])
    naslov = req.naslov or req.tip or "Nacrt"
    from shared.nacrt_za_sud import GRANICA
    from shared.usvajanje_nacrta import TIP_DOKUMENTA_ZA_SUD, TIP_PREDLOGA
    if req.tip in (TIP_PREDLOGA, TIP_DOKUMENTA_ZA_SUD):
        # C3b FINAL CLOSURE (GATE-00 N1): AI radni predlog i dokument za sud se izvoze SAMO sa pregleda, iz sačuvanog
        # i odobrenog teksta (`POST /api/staging/{id}/docx`) — nikad iz teksta koji šalje pregledač.
        raise HTTPException(status_code=409, detail="Nacrt iz spisa se izvozi samo kao odobren dokument za sud, iz "
                                                    "pregleda nacrta.")
    if GRANICA in (req.tekst or ""):
        # MIR001 C3b STRUCTURAL: tekst sa internim napomenama se ne izvozi ovim putem (ovde server ne zna šta je
        # tekst za sud) — nacrt sa pregleda se izvozi preko `POST /api/staging/{id}/docx`.
        raise HTTPException(status_code=409, detail="Tekst sadrži interne napomene za advokata. Nacrt sa pregleda "
                                                    "izvezite iz pregleda nacrta — u DOCX ide samo tekst za sud.")

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


@router.post("/api/staging/{staging_id}/docx")
@limiter.limit("30/minute")
async def staging_docx(staging_id: str, request: Request, user: dict = Depends(get_current_user)):
    """MIR001 C3b STRUCTURAL — DOCX nacrta sa pregleda: SAČUVAN tekst iz baze (ne tekst iz pregledača), samo vlasnik
    (tuđ ili nepostojeći → 404). Nacrt iz spisa (AI radni predlog) se ne izvozi → 409. Dokument za sud (C3b FINAL
    CLOSURE): samo ODOBREN, i samo tekst čiji sha256 je tačno odobren; bez automatskog naslova i sistemskog podnožja.
    Nacrt druge vrste: isti tekst kao do sada, ali tekst sa granicom se ne izvozi ceo (deo pre jedine granice, inače 409)."""
    from shared.nacrt_za_sud import GRANICA, za_izvoz
    from shared import usvajanje_nacrta as UN
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("staging_memory").select("id,tip,naziv,tekst,status,quality_detail")
            .eq("id", staging_id).eq("user_id", user["user_id"]).maybe_single().execute()
    )
    red = getattr(r, "data", None)
    if not red:
        raise HTTPException(status_code=404, detail="Nacrt nije pronađen.")
    tekst = red.get("tekst") or ""
    if red.get("tip") == _TIP_NACRTA_IZ_SPISA_STAGING:
        # C3b FINAL CLOSURE TASK-00: nacrt iz spisa je AI RADNI PREDLOG — ne izvozi se kao dokument za sud (ni stari,
        # ni odobren ranijim „odobri“). Leksička kapija koja je ranije „čistila“ tekst za izvoz je povučena (GATE-03).
        raise HTTPException(status_code=409, detail="AI radni predlog se ne izvozi kao dokument za sud. Usvojite tekst "
                                                    "u dokument za sud i odobrite ga.")
    if red.get("tip") == UN.TIP_DOKUMENTA_ZA_SUD:
        odobreno = ((red.get("quality_detail") or {}).get("usvajanje") or {}).get("odobreno") or {}
        if red.get("status") != "approved" or not odobreno.get("sha256"):
            raise HTTPException(status_code=409, detail="Dokument za sud nije odobren. Izvozi se samo odobren tekst.")
        if UN.sha(tekst) != odobreno["sha256"]:
            raise HTTPException(status_code=409, detail="Sačuvan tekst se razlikuje od odobrenog — izvoz nije dozvoljen.")
        razlozi = UN.nedozvoljen_sadrzaj(tekst)
        if razlozi:                                            # odbrana u dubini: serverski natpis ne ide u sudski DOCX
            raise HTTPException(status_code=409, detail=" ".join(razlozi) + " Odobren tekst se pri izvozu ne menja: "
                                "napravite novu verziju, ispravite tekst i odobrite je (ako je AI predlog izrađen pre "
                                "ovog pravila, potreban je novi predlog).")
        try:
            docx_bytes = await asyncio.to_thread(_nacrt_to_docx, tekst, "", await _firma_za_zaglavlje(supa, user["user_id"]),
                                                 True)
        except Exception as e:
            logger.error("DOCX export (dokument za sud) greška: %s", type(e).__name__)
            raise HTTPException(status_code=500, detail="Greška pri generisanju DOCX fajla.")
        _audit_usvajanja("dokument_za_sud_izvezen", user, staging_id, {"sha256": odobreno["sha256"]})
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="Dokument_za_sud.docx"'},
        )
    if GRANICA in tekst:
        tekst, razlog = za_izvoz(tekst)
        if razlog:
            raise HTTPException(status_code=409, detail=razlog)
    naslov = red.get("naziv") or red.get("tip") or "Nacrt"
    try:
        docx_bytes = await asyncio.to_thread(_nacrt_to_docx, tekst, naslov, await _firma_za_zaglavlje(supa, user["user_id"]))
    except Exception as e:
        logger.error("DOCX export (staging) greška: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Greška pri generisanju DOCX fajla.")
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in naslov)[:40]
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
    )


_TIP_NACRTA_IZ_SPISA_STAGING = "nacrt_iz_spisa"      # = routers/multi_agent.py::_TIP_NACRTA_IZ_SPISA


# ─── Institutional Memory V2 (2026-07-26) — Staging Memory review endpoints ──

@router.get("/api/staging/predmet/{predmet_id}")
@limiter.limit("30/minute")
async def staging_list_za_predmet(predmet_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Lista nacrta koji čekaju (ili su prošli) advokatsku overu za dati predmet."""
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("staging_memory")
            .select("id,tip,naziv,confidence_score,is_lawyer_approved,status,pinecone_indexed,created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user["user_id"])
            .order("created_at", desc=True)
            .execute()
    )
    return {"stavke": [{**x, "ponovni_upis_moguc": _ponovni_upis_moguc(x)} for x in (r.data or [])]}


# ── VCR001 T05: nacrt kao TRAJAN radni proizvod ─────────────────────────────────────────────────────────────────
# Zatečeno (mereno): V2 lista overe je prikazivala samo naziv/datum/status uz „Odobri“, a tekst nacrta posle
# reload-a nije mogao da se otvori — overa naslepo. Izmene advokata postojale su samo u polju za tekst, pa je
# odobrenje u bazu znanja kancelarije unosilo NEIZMENJEN AI tekst: „odobreno“ nije bilo „pregledano“.
_STAGING_TEKST_MAX = 100_000


class StagingTekstReq(BaseModel):
    tekst: str = Field(..., min_length=1, max_length=_STAGING_TEKST_MAX)

    @field_validator("tekst")
    @classmethod
    def _neprazan(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Tekst nacrta ne može biti prazan.")
        return v


@router.get("/api/staging/{staging_id}")
@limiter.limit("60/minute")
async def staging_jedan(staging_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Ceo nacrt (sa tekstom) — samo vlasnik; tuđ ili nepostojeći → 404 (bez razlike)."""
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("staging_memory")
            .select("id,predmet_id,tip,naziv,tekst,confidence_score,quality_detail,status,pinecone_indexed,created_at")
            .eq("id", staging_id).eq("user_id", user["user_id"]).maybe_single().execute()
    )
    red = getattr(r, "data", None)
    if not red:
        raise HTTPException(status_code=404, detail="Nacrt nije pronađen.")
    qd = red.pop("quality_detail", None) or {}
    red["izmenio_advokat"] = bool(qd.get("izmenio_advokat"))
    red["izmenjeno_at"] = qd.get("izmenjeno_at")
    # C3b FINAL CLOSURE: AI radni predlog nosi snimak za usvajanje i spisak dokumenata za sud nastalih iz njega;
    # dokument za sud nosi zapis usvajanja (šta je advokat usvojio, odbacio, odlučio i odobrio).
    from shared import usvajanje_nacrta as UN
    if red.get("tip") == UN.TIP_PREDLOGA:
        red["status_teksta"] = UN.STATUS_PREDLOGA
        red["predlog"] = qd.get("predlog")
        dz = await asyncio.to_thread(
            lambda: supa.table("staging_memory").select("id,status,quality_detail,created_at")
                .eq("user_id", user["user_id"]).eq("predmet_id", red.get("predmet_id"))
                .eq("tip", UN.TIP_DOKUMENTA_ZA_SUD).execute())
        red["dokumenti_za_sud"] = [
            {"id": x["id"], "status": x.get("status"), "verzija": _usvajanje(x).get("verzija"), "created_at": x.get("created_at")}
            for x in (dz.data or []) if _usvajanje(x).get("predlog_id") == str(red["id"])]
    elif red.get("tip") == UN.TIP_DOKUMENTA_ZA_SUD:
        dok = {**red, "quality_detail": qd}
        pr = await _red_staging(supa, _usvajanje(dok).get("predlog_id"), user["user_id"])
        red["usvajanje"] = _prikaz_dokumenta(dok, _snimak_predloga(pr))
    return red


@router.patch("/api/staging/{staging_id}/tekst")
@limiter.limit("30/minute")
async def staging_sacuvaj_tekst(staging_id: str, req: StagingTekstReq, request: Request,
                                user: dict = Depends(get_current_user)):
    """Advokatova izmena nacrta pre odluke. Dozvoljena SAMO dok je nacrt na čekanju (uslovni UPDATE na
    `status='pending'` — ista brava kao odobrenje, F16): odobren ili odbijen nacrt je zapis odluke i ne menja se.
    Quality Gate se ponovo računa nad IZMENJENIM tekstom (deterministički, bez modela), pa prag za bazu znanja
    važi za ono što advokat zaista odobrava — uključujući član koji je sam dopisao."""
    supa = _get_supa()
    r = await asyncio.to_thread(
        lambda: supa.table("staging_memory").select("id,tip,status,predmet_id,tekst,quality_detail")
            .eq("id", staging_id).eq("user_id", user["user_id"]).maybe_single().execute()
    )
    red = getattr(r, "data", None)
    if not red:
        raise HTTPException(status_code=404, detail="Nacrt nije pronađen.")
    if red.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Nacrt je već odobren ili odbijen — izmena više nije moguća.")
    from shared import usvajanje_nacrta as UN
    if red.get("tip") == UN.TIP_PREDLOGA:
        # C3b FINAL CLOSURE: AI radni predlog je zapis onoga što je AI predložio — ne menja se; advokat piše i
        # menja tekst u dokumentu za sud.
        raise HTTPException(status_code=409, detail="AI radni predlog se ne menja. Tekst menjate u dokumentu za sud.")

    from services.quality_gate import evaluate_draft_quality
    from shared.vector_origin import now_iso
    kvalitet = await evaluate_draft_quality(req.tekst, red.get("tip") or "")
    detalj = {**(kvalitet.get("detail") or {}), "izmenio_advokat": True, "izmenjeno_at": now_iso()}
    za_sud = red.get("tip") == UN.TIP_DOKUMENTA_ZA_SUD
    if za_sud:
        # zapis usvajanja ostaje; izmena važi samo nad pročitanim tekstom i revizijom (bez izgubljenog usvajanja u trci)
        detalj["usvajanje"] = _usvajanje(red)
        detalj["usvajanje_rev"] = _rev(red) + 1

    def _azuriraj():
        q = (supa.table("staging_memory")
             .update({"tekst": req.tekst, "confidence_score": kvalitet["confidence_score"], "quality_detail": detalj})
             .eq("id", staging_id).eq("user_id", user["user_id"]).eq("status", "pending"))
        if za_sud:
            q = q.eq("tekst", red.get("tekst") or "").eq("quality_detail->>usvajanje_rev", str(_rev(red)))
        return q.execute()
    upd = await asyncio.to_thread(_azuriraj)
    if not upd.data:
        raise HTTPException(status_code=409, detail="Nacrt je u međuvremenu odobren ili odbijen — izmena nije sačuvana.")
    try:
        from shared.audit_immutable import log_action
        import hashlib as _hl
        asyncio.create_task(log_action(
            action="nacrt_izmenjen", user_id=user["user_id"], resource_type="staging", resource_id=staging_id,
            metadata={"predmet_id": red.get("predmet_id"), "duzina": len(req.tekst),
                      "sha256": _hl.sha256(req.tekst.encode("utf-8")).hexdigest()[:16],
                      "confidence_score": kvalitet["confidence_score"]},
        ))
    except Exception as exc:
        logger.warning("[STAGING] audit izmene nije upisan staging=%s: %s", staging_id, exc)
    return {"status": "pending", "sacuvano": True, "confidence_score": kvalitet["confidence_score"],
            "izmenio_advokat": True, "izmenjeno_at": detalj["izmenjeno_at"]}


# ─── MIR001 C3b FINAL CLOSURE TASK-01: AI radni predlog → izričito usvajanje → dokument za sud ──────────────────────
# Ugovor: `shared/usvajanje_nacrta`. AI radni predlog (`nacrt_iz_spisa`) je nepromenljiv i ne izvozi se; dokument za
# sud (`dokument_za_sud`) je poseban red čiji tekst nastaje samo od stavki koje je advokat usvojio i teksta koji je sam
# napisao, uz advokatovu odluku o svakoj od osam procesnih tačaka. Bez nove šeme: `tip` je tekst, zapis je u
# `quality_detail` (jsonb, migracija 088). Svaka izmena je uslovna (`status='pending'` i nepromenjen tekst).
class StavkaReq(BaseModel):
    stavka: str = Field(..., pattern=r"^S-\d{2,3}$")
    odluka: str = Field(..., pattern=r"^(USVOJENO|ODBACENO)$")


class ProcesneTackeReq(BaseModel):
    tacke: dict = Field(..., min_length=1, max_length=8)


def _audit_usvajanja(akcija: str, user: dict, staging_id: str, metadata: dict) -> None:
    try:
        from shared.audit_immutable import log_action
        asyncio.create_task(log_action(action=akcija, user_id=user["user_id"], resource_type="staging",
                                       resource_id=staging_id, metadata=metadata))
    except Exception as exc:
        logger.warning("[USVAJANJE] audit %s nije upisan staging=%s: %s", akcija, staging_id, type(exc).__name__)


async def _red_staging(supa, staging_id, uid: str) -> Optional[dict]:
    if not staging_id:
        return None
    r = await asyncio.to_thread(
        lambda: supa.table("staging_memory").select("*").eq("id", staging_id).eq("user_id", uid).maybe_single().execute())
    return getattr(r, "data", None)


def _usvajanje(red: Optional[dict]) -> dict:
    return dict(((red or {}).get("quality_detail") or {}).get("usvajanje") or {})


def _snimak_predloga(red: Optional[dict]) -> Optional[dict]:
    return ((red or {}).get("quality_detail") or {}).get("predlog") or None


async def _predlog_dokumenta(supa, dok: dict, uid: str) -> tuple:
    """(red predloga, snimak) iz kog je dokument za sud nastao — isti vlasnik, isti predmet, tekst predloga nepromenjen
    od izrade (sha256 snimka). Inače 409: usvajanje bez proverljivog porekla se ne radi."""
    from shared import usvajanje_nacrta as UN
    from shared.nacrt_za_sud import GRANICA
    usv = _usvajanje(dok)
    pr = await _red_staging(supa, usv.get("predlog_id"), uid)
    snimak = _snimak_predloga(pr)
    if (not pr or pr.get("tip") != UN.TIP_PREDLOGA or str(pr.get("predmet_id")) != str(dok.get("predmet_id"))
            or pr.get("status") == "rejected"
            or not snimak or int(snimak.get("verzija_ugovora") or 0) < UN.VERZIJA_UGOVORA
            or snimak.get("sha256") != usv.get("predlog_sha256")
            or UN.sha((pr.get("tekst") or "").split(GRANICA, 1)[0].strip()) != snimak.get("sha256")):
        raise HTTPException(status_code=409, detail="AI predlog ovog dokumenta nije dostupan ili je promenjen — "
                                                    "usvajanje nije moguće.")
    return pr, snimak


def _prikaz_dokumenta(dok: dict, snimak: Optional[dict]) -> dict:
    from shared import usvajanje_nacrta as UN
    usv, tekst = _usvajanje(dok), dok.get("tekst") or ""
    out = {"id": dok["id"], "tip": UN.TIP_DOKUMENTA_ZA_SUD, "status": dok.get("status"), "tekst": tekst,
           "sha256": UN.sha(tekst), "verzija": usv.get("verzija"), "predlog_id": usv.get("predlog_id"),
           "prethodna_verzija_id": usv.get("prethodna_verzija_id"), "procesne_tacke": usv.get("procesne_tacke") or {},
           "odobreno": usv.get("odobreno"), "stavke": UN.stanje_stavki(tekst, usv, snimak or {}),
           # Usvajanje je odluka advokata, ne provera izvora: ništa ovde nije SOURCE_VERIFIED.
           "provera_izvora": "NIJE_IZVRSENA_SERVEROM", "rev": _rev(dok)}
    if dok.get("status") == "pending":
        out["razlozi_protiv_odobrenja"] = UN.razlozi_protiv_odobrenja(tekst, usv, snimak or {})
    return out


def _rev(red: Optional[dict]) -> int:
    try:
        return int(((red or {}).get("quality_detail") or {}).get("usvajanje_rev") or 0)
    except (TypeError, ValueError):
        return -1


async def _uslovno_azuriraj_dokument(supa, dok: dict, uid: str, polja: dict) -> dict:
    """Upis u dokument za sud samo ako je red i dalje onakav kakav je pročitan: na čekanju, isti tekst i ista revizija
    zapisa usvajanja (`quality_detail.usvajanje_rev`, raste sa svakim upisom). Paralelan upis (npr. odluka o tački
    dok traje odobrenje) → 409, nikad tiho prepisan zapis (GATE-01 B1)."""
    rev = _rev(dok)
    polja = {**polja, "quality_detail": {**(polja.get("quality_detail") or dok.get("quality_detail") or {}),
                                         "usvajanje_rev": rev + 1}}
    upd = await asyncio.to_thread(
        lambda: supa.table("staging_memory").update(polja).eq("id", dok["id"]).eq("user_id", uid)
            .eq("status", "pending").eq("tekst", dok.get("tekst") or "")
            .eq("quality_detail->>usvajanje_rev", str(rev)).execute())
    if not upd.data:
        raise HTTPException(status_code=409, detail="Dokument za sud je u međuvremenu promenjen, odobren ili odbijen — "
                                                    "osvežite i pokušajte ponovo. Ništa nije promenjeno.")
    return {**dok, **(upd.data[0] if isinstance(upd.data, list) and isinstance(upd.data[0], dict) else polja)}


async def _dokument_na_cekanju(supa, staging_id: str, uid: str) -> dict:
    from shared import usvajanje_nacrta as UN
    dok = await _red_staging(supa, staging_id, uid)
    if not dok:
        raise HTTPException(status_code=404, detail="Dokument nije pronađen.")
    if dok.get("tip") != UN.TIP_DOKUMENTA_ZA_SUD:
        raise HTTPException(status_code=409, detail="Ovo nije dokument za sud.")
    if dok.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Dokument za sud je odobren ili odbijen i više se ne menja — "
                                                    "napravite novu verziju.")
    return dok


@router.post("/api/staging/{staging_id}/dokument-za-sud")
@limiter.limit("20/minute")
async def staging_dokument_za_sud(staging_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Dokument za sud iz AI radnog predloga `staging_id`. Postoji li verzija na čekanju — vraća nju (ponovljen zahtev
    ne pravi novu). Ako je poslednja odobrena — nova verzija kreće od njenog teksta, BEZ odobrenja i bez odluka o
    procesnim tačkama (izmena posle odobrenja ne nasleđuje odobrenje). Tekst se ne prepisuje iz predloga."""
    from shared import usvajanje_nacrta as UN
    from shared.vector_origin import now_iso
    supa, uid = _get_supa(), user["user_id"]
    pr = await _red_staging(supa, staging_id, uid)
    if not pr:
        raise HTTPException(status_code=404, detail="Nacrt nije pronađen.")
    if pr.get("tip") != UN.TIP_PREDLOGA:
        raise HTTPException(status_code=409, detail="Dokument za sud nastaje samo iz AI radnog predloga nacrta iz spisa.")
    snimak = _snimak_predloga(pr)
    if not snimak:
        raise HTTPException(status_code=409, detail="Ovaj nacrt je izrađen pre kontrolisanog usvajanja i nema zapis za "
                                                    "usvajanje. Izradite novi predlog.")
    if int(snimak.get("verzija_ugovora") or 0) < UN.VERZIJA_UGOVORA:
        # R1: stariji zapis nema odvojen tekst za dokument (izvod bez interne oznake spisa) — ne usvaja se
        raise HTTPException(status_code=409, detail="Ovaj AI predlog je izrađen pre pravila o izvorima u dokumentu za "
                                                    "sud. Izradite novi predlog.")
    if pr.get("status") == "rejected":
        raise HTTPException(status_code=409, detail="AI predlog je odbačen.")
    r = await asyncio.to_thread(
        lambda: supa.table("staging_memory").select("*").eq("user_id", uid).eq("predmet_id", pr["predmet_id"])
            .eq("tip", UN.TIP_DOKUMENTA_ZA_SUD).execute())
    moji = [x for x in (r.data or []) if _usvajanje(x).get("predlog_id") == str(pr["id"])]
    na_cekanju = [x for x in moji if x.get("status") == "pending"]
    if na_cekanju:
        return _prikaz_dokumenta(na_cekanju[0], snimak)
    odobreni = sorted((x for x in moji if x.get("status") == "approved"), key=lambda x: _usvajanje(x).get("verzija") or 0)
    prethodni = odobreni[-1] if odobreni else None
    usv = {"predlog_id": str(pr["id"]), "predlog_sha256": snimak["sha256"],
           "verzija": max([_usvajanje(x).get("verzija") or 0 for x in moji] or [0]) + 1,
           "prethodna_verzija_id": prethodni["id"] if prethodni else None,
           "stavke": list(_usvajanje(prethodni).get("stavke") or []) if prethodni else [],
           "procesne_tacke": {}, "odobreno": None, "kreirano_at": now_iso()}
    ins = await asyncio.to_thread(lambda: supa.table("staging_memory").insert({
        "user_id": uid, "kancelarija_id": pr.get("kancelarija_id"), "predmet_id": pr["predmet_id"],
        "tip": UN.TIP_DOKUMENTA_ZA_SUD, "naziv": f"Dokument za sud — verzija {usv['verzija']}",
        "tekst": (prethodni or {}).get("tekst") or "", "confidence_score": 0,
        "quality_detail": {"usvajanje": usv, "usvajanje_rev": 0},
    }).execute())
    dok = ins.data[0] if isinstance(ins.data, list) and ins.data else None
    if not dok:
        raise HTTPException(status_code=503, detail="Dokument za sud nije napravljen. Ništa nije promenjeno.")
    # Paralelan ponovljen zahtev (dupli klik): bez jedinstvenog ograničenja u šemi oba upisa mogu da prođu. Posle upisa
    # se zato bira JEDNA verzija na čekanju (najranija po created_at, pa id); suvišna, upravo napravljena i još
    # netaknuta (revizija 0) se briše, a vraća se izabrana.
    r2 = await asyncio.to_thread(
        lambda: supa.table("staging_memory").select("*").eq("user_id", uid).eq("predmet_id", pr["predmet_id"])
            .eq("tip", UN.TIP_DOKUMENTA_ZA_SUD).eq("status", "pending").execute())
    cekaju = sorted((x for x in (r2.data or []) if _usvajanje(x).get("predlog_id") == str(pr["id"])),
                    key=lambda x: (str(x.get("created_at") or ""), str(x.get("id"))))
    if cekaju and str(cekaju[0]["id"]) != str(dok["id"]):
        await asyncio.to_thread(
            lambda: supa.table("staging_memory").delete().eq("id", dok["id"]).eq("user_id", uid)
                .eq("status", "pending").eq("quality_detail->>usvajanje_rev", "0").execute())
        return _prikaz_dokumenta(cekaju[0], snimak)
    _audit_usvajanja("dokument_za_sud_kreiran", user, dok["id"], {"predmet_id": pr["predmet_id"], "predlog_id": pr["id"],
                                                                  "verzija": usv["verzija"]})
    return _prikaz_dokumenta(dok, snimak)


@router.post("/api/staging/{staging_id}/stavka")
@limiter.limit("60/minute")
async def staging_stavka(staging_id: str, req: StavkaReq, request: Request, user: dict = Depends(get_current_user)):
    """Advokatova odluka o JEDNOJ stavci AI predloga. USVOJENO: server dodaje tekst stavke iz snimka predloga (po id-u,
    ne iz pregledača) na kraj dokumenta za sud. ODBACENO: stavka ne ulazi u dokument (zapis odluke). Ponovljena ista
    odluka ne menja ništa. Usvojena stavka se ne odbacuje naknadno — uklanja se izmenom teksta."""
    from shared.vector_origin import now_iso
    supa, uid = _get_supa(), user["user_id"]
    dok = await _dokument_na_cekanju(supa, staging_id, uid)
    pr, snimak = await _predlog_dokumenta(supa, dok, uid)
    s = next((x for x in snimak.get("stavke") or [] if x["id"] == req.stavka), None)
    if not s:
        raise HTTPException(status_code=404, detail="Stavka ne postoji u AI predlogu.")
    usv = _usvajanje(dok)
    ranije = next((x for x in usv.get("stavke") or [] if x["id"] == req.stavka), None)
    if ranije and ranije.get("odluka") == req.odluka:
        return _prikaz_dokumenta(dok, snimak)
    if ranije and ranije.get("odluka") == "USVOJENO":
        raise HTTPException(status_code=409, detail="Stavka je već usvojena u tekst. Uklonite je izmenom teksta.")
    tekst = dok.get("tekst") or ""
    za_dok = s["tekst_za_dokument"]                     # R1: izvod bez interne oznake spisa (snimak verzije 2)
    if req.odluka == "USVOJENO":
        tekst = f"{tekst.rstrip()}\n\n{za_dok}" if tekst.strip() else za_dok
    zapis = [x for x in usv.get("stavke") or [] if x["id"] != req.stavka] + [
        {"id": s["id"], "odluka": req.odluka, "sha256": s["sha256"], "sha256_za_dokument": s["sha256_za_dokument"],
         "by": uid, "at": now_iso()}]
    qd = {**(dok.get("quality_detail") or {}), "usvajanje": {**usv, "stavke": zapis}}
    dok = await _uslovno_azuriraj_dokument(supa, dok, uid, {"tekst": tekst, "quality_detail": qd})
    _audit_usvajanja("dokument_za_sud_stavka", user, staging_id, {"stavka": s["id"], "odluka": req.odluka,
                                                                  "stavka_sha256": s["sha256"][:16]})
    return _prikaz_dokumenta(dok, snimak)


@router.post("/api/staging/{staging_id}/procesne-tacke")
@limiter.limit("60/minute")
async def staging_procesne_tacke(staging_id: str, req: ProcesneTackeReq, request: Request,
                                 user: dict = Depends(get_current_user)):
    """Advokatove odluke o procesnim tačkama (potvrđeno / ispravljeno / nepoznato / nije primenljivo, uz njegov opis
    stanja). Upisuje ih samo ovaj zahtev korisnika — sistem ih nikad ne popunjava. Odluka nije provera izvora."""
    from shared import usvajanje_nacrta as UN
    from shared.vector_origin import now_iso
    supa, uid = _get_supa(), user["user_id"]
    dok = await _dokument_na_cekanju(supa, staging_id, uid)
    pr, snimak = await _predlog_dokumenta(supa, dok, uid)
    poznati = {d["oznaka"] for d in snimak.get("dokumenti") or [] if d.get("oznaka")}
    for k, o in req.tacke.items():
        razlog = UN.proveri_odluku_tacke(k, o, poznati)
        if razlog:
            raise HTTPException(status_code=422, detail=razlog)
    usv = _usvajanje(dok)
    tacke = {**(usv.get("procesne_tacke") or {}), **{
        k: {"odluka": o["odluka"], "tekst": (o.get("tekst") or "").strip(), "izvori": list(o.get("izvori") or []),
            "by": uid, "at": now_iso()} for k, o in req.tacke.items()}}
    qd = {**(dok.get("quality_detail") or {}), "usvajanje": {**usv, "procesne_tacke": tacke}}
    dok = await _uslovno_azuriraj_dokument(supa, dok, uid, {"quality_detail": qd})
    _audit_usvajanja("dokument_za_sud_procesne_tacke", user, staging_id, {k: tacke[k]["odluka"] for k in req.tacke})
    return _prikaz_dokumenta(dok, snimak)


async def _odobri_dokument_za_sud(supa, dok: dict, request: Request, user: dict) -> dict:
    """Odobrenje TAČNO određenog teksta: telo `{"sha256": …}` mora odgovarati sačuvanom tekstu (advokat odobrava ono
    što je video). Uslovi: osam procesnih tačaka odlučeno, nema serverskih natpisa ni nerazrešenih mesta, nema
    doslovne AI stavke koja nije usvojena. Bez upisa u bazu znanja i bez promocije."""
    from shared import usvajanje_nacrta as UN
    from shared.vector_origin import now_iso
    uid = user["user_id"]
    if dok.get("status") != "pending":
        return {"status": dok.get("status"), "indexed": False, "poruka": "Ovaj dokument je već obrađen (odobren ili odbijen)."}
    try:
        telo = await request.json()
    except Exception:
        telo = None
    trazeni = telo.get("sha256") if isinstance(telo, dict) else None
    vidjena_rev = telo.get("rev") if isinstance(telo, dict) else None
    tekst = dok.get("tekst") or ""
    if not isinstance(trazeni, str) or trazeni != UN.sha(tekst) or vidjena_rev != _rev(dok):
        raise HTTPException(status_code=409, detail={"razlog": "TEKST_NIJE_ISTI", "poruka": (
            "Odobrava se tačno tekst i odluke koje ste videli (u međuvremenu je nešto promenjeno ili zahtev nije iz "
            "pregleda nacrta). Osvežite dokument za sud i odobrite ga ponovo.")})
    pr, snimak = await _predlog_dokumenta(supa, dok, uid)
    usv = _usvajanje(dok)
    razlozi = UN.razlozi_protiv_odobrenja(tekst, usv, snimak)
    if razlozi:
        raise HTTPException(status_code=409, detail={"razlog": "NIJE_SPREMNO", "razlozi": razlozi})
    sad = now_iso()
    qd = {**(dok.get("quality_detail") or {}), "usvajanje": {**usv, "odobreno": {"sha256": trazeni, "by": uid, "at": sad}}}
    await _uslovno_azuriraj_dokument(supa, dok, uid, {"status": "approved", "is_lawyer_approved": True, "approved_by": uid,
                                                      "approved_at": sad, "quality_detail": qd})
    _audit_usvajanja("dokument_za_sud_odobren", user, dok["id"], {"predmet_id": dok.get("predmet_id"), "sha256": trazeni,
                                                                  "verzija": usv.get("verzija")})
    return {"status": "approved", "indexed": False, "razlog": "DOKUMENT_ZA_SUD", "sha256": trazeni,
            "poruka": "Dokument za sud je odobren. Ne dodaje se u bazu znanja kancelarije ni u dokumente predmeta."}


_PORUKA_NEPOTPUN_UPIS = (
    "Nacrt je odobren, ali upis u bazu znanja kancelarije nije potvrđen kao potpun — sistem ga zato ne koristi "
    "kao overen izvor u znanju kancelarije. Upis možete ponoviti.")


@router.post("/api/staging/{staging_id}/ponovi-upis")
@limiter.limit("10/minute")
async def staging_ponovi_upis(staging_id: str, request: Request, user: dict = Depends(get_current_user)):
    """NS4 O3: ponovni upis ODOBRENOG nacrta čiji upis nije potvrđen kao potpun. Samo vlasnik; samo nacrt koji je
    i dalje odobren, iznad praga kvaliteta, nije potvrđeno indeksiran i nema aktivnog pokušaja (atomsko
    preuzimanje u bazi). Ne zaobilazi advokatsku overu ni prag; isti tekst → isti ID-evi vektora."""
    supa = _get_supa()
    try:
        sid = str(uuid.UUID(str(staging_id)))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Nacrt nije pronađen.")
    # MIR001 TASK-06: nacrt iz spisa (savetnik) se ne upisuje u bazu znanja ni ponovnim upisom — provera PRE preuzimanja.
    try:
        vrsta = await asyncio.to_thread(lambda: supa.table("staging_memory").select("tip")
                                        .eq("id", sid).eq("user_id", user["user_id"]).maybe_single().execute())
    except Exception as exc:
        logger.warning("[STAGING_RETRY] čitanje vrste nije uspelo staging_id=%s: %s", sid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Stanje nacrta trenutno nije moguće proveriti. Ništa nije promenjeno.")
    if ((getattr(vrsta, "data", None) or {}).get("tip")) in (_TIP_IZ_SPISA, _TIP_DOKUMENT_ZA_SUD):
        raise HTTPException(status_code=409, detail={"razlog": "NACRT_IZ_SPISA",
                            "poruka": "Nacrt iz spisa se ne dodaje u bazu znanja kancelarije. Ništa nije promenjeno."})
    try:
        r = await asyncio.to_thread(lambda: supa.rpc("preuzmi_ponovni_upis_nacrta", {
            "p_staging_id": sid, "p_user_id": user["user_id"],
            "p_prag": _APPROVAL_CONFIDENCE_THRESHOLD, "p_istek_sekundi": _PROMOCIJA_ISTEK_S}).execute())
    except Exception as exc:
        logger.warning("[STAGING_RETRY] preuzimanje nije uspelo staging_id=%s: %s", sid, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Stanje nacrta trenutno nije moguće proveriti. Ništa nije promenjeno.")
    redovi = r.data if isinstance(getattr(r, "data", None), list) else []
    if not redovi:
        cur = await asyncio.to_thread(
            lambda: supa.table("staging_memory").select("status,is_lawyer_approved,pinecone_indexed,confidence_score")
                .eq("id", sid).eq("user_id", user["user_id"]).maybe_single().execute())
        red = getattr(cur, "data", None)
        if not red:
            raise HTTPException(status_code=404, detail="Nacrt nije pronađen.")
        if red.get("status") == "approved" and red.get("pinecone_indexed") is True:
            return {"status": "approved", "indexed": True, "poruka": "Nacrt je već u bazi znanja kancelarije."}
        raise HTTPException(status_code=409, detail=(
            "Ponovni upis nije moguć: nacrt nije odobren, ocena kvaliteta je ispod praga ili je upis već u toku."))
    staging_row = redovi[0]
    token = staging_row.get("promocija_token")
    promoted = False
    try:
        promoted = await _promote_staged_draft_to_pinecone(supa, staging_row)
    except Exception as exc:
        _sentry_capture(exc)
        logger.warning("[STAGING_RETRY] promocija neuspešna staging_id=%s: %s", sid, type(exc).__name__)
        promoted = False
    promoted = await _zavrsi_promociju(supa, sid, token, promoted) and promoted
    if promoted:
        return {"status": "approved", "indexed": True, "poruka": "Nacrt je dodat u bazu znanja kancelarije."}
    return {"status": "approved", "indexed": False, "razlog": "INDEKSIRANJE_NIJE_USPELO",
            "poruka": _PORUKA_NEPOTPUN_UPIS, "ponovni_upis_moguc": True}


@router.post("/api/staging/{staging_id}/approve")
@limiter.limit("20/minute")
async def staging_approve(staging_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Eksplicitna advokatska potvrda (STUB 1.3). NUŽAN ali NE DOVOLJAN uslov
    za ulazak u Pinecone -- promocija se dešava SAMO ako je i
    confidence_score >= 0.85 (v. _promote_staged_draft_to_pinecone)."""
    supa = _get_supa()
    row_res = await asyncio.to_thread(
        lambda: supa.table("staging_memory").select("*").eq("id", staging_id).eq("user_id", user["user_id"]).maybe_single().execute()
    )
    if not row_res.data:
        raise HTTPException(status_code=404, detail="Nacrt na čekanju nije pronađen.")
    staging_row = row_res.data
    # C3b FINAL CLOSURE TASK-01: AI radni predlog se ne odobrava (nije dokument ni znanje); dokument za sud se odobra-
    # va po svom ugovoru (tačan tekst, procesne tačke, bez promocije) — `_odobri_dokument_za_sud`.
    if staging_row.get("tip") == _TIP_IZ_SPISA:
        raise HTTPException(status_code=409, detail={"razlog": "AI_RADNI_PREDLOG", "poruka": (
            "AI radni predlog se ne odobrava. Usvojite tekst u dokument za sud i odobrite dokument.")})
    if staging_row.get("tip") == _TIP_DOKUMENT_ZA_SUD:
        return await _odobri_dokument_za_sud(supa, staging_row, request, user)

    from shared.vector_origin import now_iso
    token = str(uuid.uuid4())
    update_fields = {
        "is_lawyer_approved": True,
        "approved_by": user["user_id"],
        "approved_at": now_iso(),
        "status": "approved",
        # NS4 O3: prelaz pending → approved je i preuzimanje promocije — ponovni upis ne može da teče uporedo.
        "promocija_token": token,
        "promocija_preuzeta_at": now_iso(),
    }

    # Final Beta Gate F16 (HIGH): claim the row FIRST, atomically, BEFORE any
    # Pinecone promotion -- a double-click or slow-UI retry used to let 2
    # concurrent requests both read status='pending', both pass the
    # confidence check below, and both independently call
    # _promote_staged_draft_to_pinecone (which has no dedup of its own),
    # permanently ingesting 2 duplicate vectors into the firm's real
    # Pinecone knowledge base plus 2 duplicate predmet_dokumenti rows -- a
    # silent, permanent corruption of an institutional-memory asset other
    # cases' retrieval depends on. The UPDATE below is conditioned on status
    # still being 'pending' (the table's own DEFAULT/CHECK, migration 088)
    # -- only the request that actually flips pending -> approved may
    # promote; a losing concurrent request gets a clear "already processed"
    # response instead of silently promoting a second time.
    claim_res = await asyncio.to_thread(
        lambda: supa.table("staging_memory")
            .update(update_fields)
            .eq("id", staging_id)
            .eq("user_id", user["user_id"])
            .eq("status", "pending")
            .execute()
    )
    if not claim_res.data:
        current = await asyncio.to_thread(
            lambda: supa.table("staging_memory")
                .select("status,pinecone_indexed")
                .eq("id", staging_id).eq("user_id", user["user_id"])
                .maybe_single().execute()
        )
        cur = current.data or {}
        return {
            "status": cur.get("status", "approved"),
            "indexed": bool(cur.get("pinecone_indexed")),
            "poruka": "Ovaj nacrt je već obrađen (odobren ili odbijen).",
        }
    # VCR001 T05: promoviše se tekst IZ PREUZETOG reda (stanje u trenutku prelaska pending → approved), ne iz
    # čitanja pre brave — izmena sačuvana između ta dva koraka inače ne bi bila ono što ulazi u bazu znanja.
    if isinstance(claim_res.data, list) and claim_res.data and isinstance(claim_res.data[0], dict):
        staging_row = {**staging_row, **claim_res.data[0]}

    promoted = False
    ispod_praga = float(staging_row.get("confidence_score") or 0) < _APPROVAL_CONFIDENCE_THRESHOLD
    # MIR001 TASK-06: nacrt iz spisa (savetnik) je radni nacrt — odobren AI tekst ne postaje dokument predmeta ni deo baze
    # znanja kancelarije, pa ne može da se vrati kao „izvor“ u dalju analizu istog predmeta.
    iz_spisa = staging_row.get("tip") == _TIP_IZ_SPISA
    if not ispod_praga and not iz_spisa:
        try:
            promoted = await _promote_staged_draft_to_pinecone(supa, {**staging_row, **update_fields})
        except Exception as exc:
            _sentry_capture(exc)
            logger.warning("[STAGING_APPROVE] promocija neuspešna staging_id=%s: %s", staging_id, exc)
            promoted = False

    promoted = await _zavrsi_promociju(supa, staging_id, token, promoted) and promoted

    if iz_spisa:
        return {"status": "approved", "indexed": False, "razlog": "NACRT_IZ_SPISA",
                "poruka": "Nacrt je odobren kao radni nacrt. Nacrt iz spisa se ne dodaje u bazu znanja kancelarije ni u dokumente predmeta."}
    if promoted:
        return {"status": "approved", "indexed": True, "poruka": "Nacrt odobren i dodat u bazu znanja kancelarije."}
    if not ispod_praga:
        # NS4-T5: ranije je i ovaj slučaj (ocena IZNAD praga, upis u indeks pao ili nepotpun) vraćao poruku
        # „confidence_score je ispod praga“ — pogrešan razlog, a advokat nije znao da upis nije uspeo.
        return {
            "status": "approved", "indexed": False, "razlog": "INDEKSIRANJE_NIJE_USPELO",
            # NS4-R2: deo delova je možda fizički upisan — ne tvrdi se „nije pretraživ", nego ono što sistem zna:
            # upis nije potvrđen kao potpun, pa se nacrt ne koristi kao overen izvor (`vazece_overe`).
            "poruka": _PORUKA_NEPOTPUN_UPIS,
            "ponovni_upis_moguc": True,
        }
    return {
        "status": "approved", "indexed": False, "razlog": "ISPOD_PRAGA",
        "poruka": (
            "Nacrt je označen kao odobren, ali confidence_score "
            f"({staging_row.get('confidence_score')}) je ispod praga {_APPROVAL_CONFIDENCE_THRESHOLD} "
            "za automatski ulazak u bazu znanja kancelarije."
        ),
    }


@router.post("/api/staging/{staging_id}/reject")
@limiter.limit("20/minute")
async def staging_reject(staging_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Advokat odbija nacrt -- nikad ne ulazi u Pinecone, ostaje samo istorijski
    zapis u staging_memory (audit trail — zašto je nešto odbijeno)."""
    supa = _get_supa()
    row_res = await asyncio.to_thread(
        lambda: supa.table("staging_memory").select("id,tip,status").eq("id", staging_id).eq("user_id", user["user_id"]).maybe_single().execute()
    )
    if not row_res.data:
        raise HTTPException(status_code=404, detail="Nacrt na čekanju nije pronađen.")
    if row_res.data.get("tip") == _TIP_DOKUMENT_ZA_SUD and row_res.data.get("status") != "pending":
        # C3b FINAL CLOSURE (GATE-01 N4): odobren dokument za sud je zapis odluke — ne odbija se naknadno
        raise HTTPException(status_code=409, detail="Dokument za sud je već odobren ili odbijen. Izmene idu u novu verziju.")
    if row_res.data.get("tip") == _TIP_DOKUMENT_ZA_SUD:
        # GATE-01 N-a: uslovno, da odobrenje završeno u međuvremenu ne bude prepisano odbijanjem
        upd = await asyncio.to_thread(
            lambda: supa.table("staging_memory").update({"status": "rejected", "is_lawyer_approved": False})
                .eq("id", staging_id).eq("user_id", user["user_id"]).eq("status", "pending").execute())
        if not upd.data:
            raise HTTPException(status_code=409, detail="Dokument za sud je u međuvremenu odobren ili odbijen.")
        return {"status": "rejected", "indexed": False}

    await asyncio.to_thread(
        lambda: supa.table("staging_memory").update({"status": "rejected", "is_lawyer_approved": False}).eq("id", staging_id).execute()
    )
    return {"status": "rejected", "indexed": False}
