# -*- coding: utf-8 -*-
"""
Vindex AI — routers/vindex_memory.py

Vindex Memory: institucionalna inteligencija kancelarije.
Uci iz svakog dokumenta, argumenta i presude koja prodje kroz sistem.

Endpoints:
  POST /api/memory/dodaj        — dodaj znanje u memoriju
  GET  /api/memory/pretraga     — pretrazi memoriju
  POST /api/memory/sugestija    — AI sugestija na osnovu istorije kancelarije
  GET  /api/memory/statistike   — koliko je memorija narasla
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.memory")
router = APIRouter(tags=["vindex-memory"])


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

class MemoryDodajRequest(BaseModel):
    tip: str                              # "argument"|"presuda"|"tuzba"|"ugovor"|"komentar"|"ishod"
    sadrzaj: str
    predmet_tip: Optional[str] = None    # "gradjansko"|"krivicno"|"radno"|"upravno"|"privredno"
    ishod: Optional[str] = None          # "uspesno"|"neuspesno"|"poravnanje"
    tagovi: Optional[list[str]] = []
    predmet_id: Optional[str] = None


class SugestijaRequest(BaseModel):
    tekuci_tekst: str
    tip_dokumenta: str                   # "tuzba"|"zalba"|"ugovor"|"podnesak"
    tip_postupka: Optional[str] = None
    predmet_id: Optional[str] = None


# ─── Interni helperi ──────────────────────────────────────────────────────────

async def _firma_id_za_korisnika(supa, uid: str) -> str | None:
    """Vrati firma_id ako korisnik pripada nekoj firmi."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("firma_clanovi")
                .select("firma_id")
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        return r.data.get("firma_id") if r.data else None
    except Exception:
        return None


async def _embed_i_sacuvaj(
    uid: str,
    firma_id: str | None,
    tip: str,
    sadrzaj: str,
    metapodaci: dict,
    record_id: str,
) -> None:
    """Embedduj sadrzaj i upsertuj u Pinecone memory namespace-ove."""
    try:
        from pinecone import Pinecone
        from openai import OpenAI

        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        pc  = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        idx = pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))

        emb = oai.embeddings.create(
            model="text-embedding-3-large",
            input=sadrzaj[:8000],
        ).data[0].embedding

        namespaces = [f"mem_{uid}"]
        if firma_id:
            namespaces.append(f"mem_firma_{firma_id}")

        vector = {
            "id":     f"mem_{uid}_{record_id}",
            "values": emb,
            "metadata": {
                "tip":      tip,
                "sadrzaj":  sadrzaj[:1500],
                "user_id":  uid,
                "firma_id": firma_id or "",
                **metapodaci,
            },
        }

        for ns in namespaces:
            idx.upsert(vectors=[vector], namespace=ns)

    except Exception as e:
        logger.warning("Memory embed greška: %s", e)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/api/memory/dodaj")
@limiter.limit("30/minute")
async def memory_dodaj(
    request: Request,
    payload: MemoryDodajRequest,
    user: dict = Depends(get_current_user),
):
    """Dodaj znanje u Vindex Memory — manuelno ili automatski iz workflow-a."""
    uid  = user["user_id"]
    supa = _get_supa()

    if len(payload.sadrzaj.strip()) < 20:
        raise HTTPException(status_code=400, detail="Sadrzaj je prekratak (minimum 20 znakova).")

    DOZVOLJENI_TIPOVI = {"argument", "presuda", "tuzba", "ugovor", "komentar", "ishod", "podnesak", "ostalo"}
    if payload.tip not in DOZVOLJENI_TIPOVI:
        payload.tip = "ostalo"

    firma_id  = await _firma_id_za_korisnika(supa, uid)
    record_id = str(uuid.uuid4())

    try:
        await asyncio.to_thread(
            lambda: supa.table("vindex_memory").insert({
                "id":          record_id,
                "user_id":     uid,
                "firma_id":    firma_id,
                "tip":         payload.tip,
                "sadrzaj":     payload.sadrzaj[:10000],
                "predmet_tip": payload.predmet_tip,
                "ishod":       payload.ishod,
                "tagovi":      payload.tagovi or [],
                "predmet_id":  payload.predmet_id,
            }).execute()
        )
    except Exception as e:
        logger.warning("Memory DB insert greška: %s", e)

    metapodaci = {
        "predmet_tip": payload.predmet_tip or "",
        "ishod":       payload.ishod or "",
        "tagovi":      ",".join(payload.tagovi or []),
    }
    asyncio.create_task(
        _embed_i_sacuvaj(uid, firma_id, payload.tip, payload.sadrzaj, metapodaci, record_id)
    )

    return {"ok": True, "id": record_id, "tip": payload.tip}


@router.get("/api/memory/pretraga")
@limiter.limit("30/minute")
async def memory_pretraga(
    request: Request,
    q: str,
    tip: Optional[str] = None,
    limit: int = 10,
    user: dict = Depends(PermissionService.require("vindex_memory")),
):
    """Semanticka pretraga kroz celokupnu memoriju korisnika."""
    uid = user["user_id"]

    if not q or len(q.strip()) < 3:
        raise HTTPException(status_code=400, detail="Upit je prekratak.")

    limit = max(1, min(limit, 20))

    try:
        from pinecone import Pinecone
        from openai import OpenAI

        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        pc  = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        idx = pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))

        emb = await asyncio.to_thread(
            lambda: oai.embeddings.create(
                model="text-embedding-3-large",
                input=q.strip(),
            ).data[0].embedding
        )

        filter_dict: dict = {}
        if tip:
            filter_dict["tip"] = {"$eq": tip}

        rezultati = await asyncio.to_thread(
            lambda: idx.query(
                vector=emb,
                top_k=limit,
                namespace=f"mem_{uid}",
                include_metadata=True,
                filter=filter_dict if filter_dict else None,
            )
        )

        items = [
            {
                "id":          m.id,
                "tip":         m.metadata.get("tip"),
                "sadrzaj":     m.metadata.get("sadrzaj", "")[:500],
                "ishod":       m.metadata.get("ishod"),
                "predmet_tip": m.metadata.get("predmet_tip"),
                "score":       round(m.score, 3),
            }
            for m in (rezultati.matches or [])
            if m.score >= 0.35
        ]

        await UsageService.consume(user["user_id"], user.get("email", ""), "vindex_memory")

        return {"rezultati": items, "query": q, "ukupno": len(items)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Memory pretraga greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri pretraživanju memorije.")


@router.post("/api/memory/sugestija")
@limiter.limit("15/minute")
async def memory_sugestija(
    request: Request,
    payload: SugestijaRequest,
    user: dict = Depends(PermissionService.require("vindex_memory")),
):
    """
    Analizira tekuci dokument i na osnovu istorije kancelarije
    daje konkretne sugestije za poboljsanje.

    Primer outputa: "[MEMORIJA] Partner Markovic u poslednjih 12 slicnih predmeta
    uvek koristi cl. 172 kao primarni argument. Ovde nedostaje."
    """
    uid  = user["user_id"]

    if len(payload.tekuci_tekst.strip()) < 30:
        raise HTTPException(status_code=400, detail="Tekst dokumenta je prekratak.")

    try:
        from pinecone import Pinecone
        from openai import OpenAI

        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        pc  = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        idx = pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))

        emb = await asyncio.to_thread(
            lambda: oai.embeddings.create(
                model="text-embedding-3-large",
                input=payload.tekuci_tekst[:4000],
            ).data[0].embedding
        )

        mem_r = await asyncio.to_thread(
            lambda: idx.query(
                vector=emb,
                top_k=8,
                namespace=f"mem_{uid}",
                include_metadata=True,
            )
        )

        memorija_kontekst = "\n\n".join([
            f"[{m.metadata.get('tip','?').upper()} | ishod: {m.metadata.get('ishod','nepoznat')}]\n"
            f"{m.metadata.get('sadrzaj','')[:600]}"
            for m in (mem_r.matches or [])
            if m.score >= 0.38
        ])

    except Exception as e:
        logger.warning("Memory sugestija Pinecone greška: %s", e)
        memorija_kontekst = ""

    if not memorija_kontekst:
        return {
            "sugestije": [],
            "memorija_koriscena": False,
            "poruka": (
                "Memorija kancelarije je jos uvek prazna. "
                "Kako dodajete vise dokumenata, sugestije ce postajati preciznije."
            ),
        }

    ai_prompt = f"""Analiziras dokument koji advokat trenutno pise i na osnovu istorije kancelarije
dajas konkretne sugestije za poboljsanje.

TEKUCI DOKUMENT ({payload.tip_dokumenta}):
{payload.tekuci_tekst[:3000]}

MEMORIJA KANCELARIJE (prethodni dokumenti, argumenti, ishodi):
{memorija_kontekst}

Na osnovu memorije kancelarije, identifikuj:
1. Koji argumenti su se u slicnim predmetima pokazali uspesnim — a ovde nedostaju?
2. Koje greske su ranije pravljene — i da li ih vidiš ovde?
3. Koji zakonski clanovi se uvek koriste u ovakvim predmetima — a nisu pomenuti?

Format: daj 3-5 konkretnih sugestija. Svaka MORA poceti sa tacno ovom recju: [MEMORIJA]
Budi konkretan. Navedi clanove zakona, argumente, rizike. Pisi u ekavici."""

    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": ai_prompt}],
                max_tokens=900,
                temperature=0.35,
            )
        )
        sugestije_tekst = resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Memory sugestija GPT greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri generisanju sugestija.")

    sugestije = [
        s.strip().lstrip("-•").strip()
        for s in sugestije_tekst.split("\n")
        if s.strip() and "[MEMORIJA]" in s
    ]

    if not sugestije:
        sugestije = [sugestije_tekst]

    await UsageService.consume(user["user_id"], user.get("email", ""), "vindex_memory")

    return {
        "sugestije":          sugestije,
        "memorija_koriscena": True,
        "tip_dokumenta":      payload.tip_dokumenta,
    }


@router.get("/api/memory/statistike")
async def memory_statistike(user: dict = Depends(get_current_user)):
    """Koliko je memorija narasla — motivacioni prikaz za korisnika."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("vindex_memory")
                .select("tip")
                .eq("user_id", uid)
                .execute()
        )
        redovi   = r.data or []
        ukupno   = len(redovi)
        po_tipu: dict[str, int] = {}
        for row in redovi:
            t = row.get("tip", "ostalo")
            po_tipu[t] = po_tipu.get(t, 0) + 1

        if ukupno == 0:
            poruka = "Memorija je tek pocela da raste. Svaki dokument je korak napred."
        elif ukupno < 20:
            poruka = f"Memorija kancelarije sadrzi {ukupno} jedinica znanja. Nastavite da koristite Vindex."
        elif ukupno < 100:
            poruka = f"Solidna memorija: {ukupno} jedinica znanja. AI sugestije postaju sve preciznije."
        else:
            poruka = f"Impresivna memorija: {ukupno} jedinica znanja. Vas AI asistent sada dobro poznaje kancelariju."

        return {"ukupno_znanja": ukupno, "po_tipu": po_tipu, "poruka": poruka}

    except Exception:
        return {"ukupno_znanja": 0, "po_tipu": {}, "poruka": "Memorija jos nije aktivna."}
