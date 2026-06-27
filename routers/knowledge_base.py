# -*- coding: utf-8 -*-
"""
Vindex AI — routers/knowledge_base.py

Lična baza znanja — advokat čuva lične beleške, stavove i reference.
Čuva se u Supabase tabeli user_knowledge; embedduje se u Pinecone namespace kb_{user_id}.

SQL migracija (pokrenuti jednom):
  CREATE TABLE IF NOT EXISTS user_knowledge (
      id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id    TEXT        NOT NULL,
      naslov     TEXT        NOT NULL,
      sadrzaj    TEXT        NOT NULL,
      tagovi     TEXT[]      DEFAULT '{}',
      predmet_id TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  CREATE INDEX IF NOT EXISTS idx_uk_user    ON user_knowledge(user_id);
  CREATE INDEX IF NOT EXISTS idx_uk_predmet ON user_knowledge(predmet_id);

Endpoints:
  POST   /api/knowledge/save        — sačuvaj belešku (+ auto-tag + Pinecone upsert)
  GET    /api/knowledge/list        — lista beleški (filter po tagovima / predmetu)
  GET    /api/knowledge/search      — semantička pretraga beleški
  DELETE /api/knowledge/{id}        — obriši belešku (+ Pinecone delete)
  PUT    /api/knowledge/{id}        — ažuriraj belešku
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.knowledge_base")
router = APIRouter(tags=["knowledge_base"])


# ── Pinecone / OpenAI helpers ─────────────────────────────────────────────────

def _get_pinecone_index():
    from pinecone import Pinecone
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    return pc.Index(os.environ.get("PINECONE_INDEX", "vindex-ai"))


def _get_oai():
    from openai import OpenAI
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


async def _kb_embed(text: str) -> list[float]:
    oai = _get_oai()
    resp = await asyncio.to_thread(
        lambda: oai.embeddings.create(
            model="text-embedding-3-large",
            input=text[:8000],
        )
    )
    return resp.data[0].embedding


async def _kb_embed_and_upsert(
    uid: str, beleska_id: str, naslov: str, sadrzaj: str,
    tagovi: list, predmet_id: str | None
) -> None:
    """Embedduj belešku i upsertuj u Pinecone kb_{uid} namespace."""
    try:
        index = _get_pinecone_index()
        emb = await _kb_embed(f"{naslov}\n\n{sadrzaj}")
        index.upsert(
            vectors=[{
                "id": f"kb_{uid}_{beleska_id}",
                "values": emb,
                "metadata": {
                    "beleska_id": beleska_id,
                    "naslov": naslov[:200],
                    "sadrzaj": sadrzaj[:1000],
                    "tagovi": tagovi if isinstance(tagovi, list) else [],
                    "predmet_id": predmet_id or "",
                    "user_id": uid,
                },
            }],
            namespace=f"kb_{uid}",
        )
        logger.info("[KNOWLEDGE] Pinecone upsert ok: kb_%s_%s", uid[:8], beleska_id)
    except Exception as e:
        logger.warning("[KNOWLEDGE] Pinecone upsert greška: %s", e)


async def _kb_auto_tag(sadrzaj: str, naslov: str) -> list[str]:
    """GPT-4o-mini predlaže 3 taga za belešku."""
    try:
        oai = _get_oai()
        resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": (
                        "Predloži tačno 3 kratka taga (1-2 reči svaki) za ovu pravnu belešku. "
                        "Odgovori SAMO kao JSON lista stringova, bez objašnjenja.\n\n"
                        f"Naslov: {naslov}\nSadržaj: {sadrzaj[:400]}"
                    ),
                }],
                max_tokens=60,
                temperature=0.3,
            )
        )
        raw = resp.choices[0].message.content.strip()
        # Ukloni eventualne markdown ```json blokove
        raw = raw.replace("```json", "").replace("```", "").strip()
        tags = json.loads(raw)
        return [str(t).strip()[:30] for t in tags[:3]] if isinstance(tags, list) else []
    except Exception:
        return []


# ── Models ────────────────────────────────────────────────────────────────────

class KnowledgeSaveReq(BaseModel):
    naslov:     str           = Field(..., min_length=2, max_length=200)
    sadrzaj:    str           = Field(..., min_length=5, max_length=20000)
    tagovi:     List[str]     = Field(default_factory=list)
    predmet_id: Optional[str] = Field(default=None)


class KnowledgeUpdateReq(BaseModel):
    naslov:     Optional[str]       = None
    sadrzaj:    Optional[str]       = None
    tagovi:     Optional[List[str]] = None
    predmet_id: Optional[str]       = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/knowledge/save")
@limiter.limit("30/minute")
async def knowledge_save(
    body: KnowledgeSaveReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Sačuvaj belešku u ličnu bazu znanja (+ auto-tagovanje + Pinecone embedding)."""
    uid  = user["user_id"]
    supa = _get_supa()

    tagovi = [t.strip()[:50] for t in body.tagovi[:10] if t.strip()]

    # Auto-tagovanje ako tagovi nisu poslati
    if not tagovi:
        tagovi = await _kb_auto_tag(body.sadrzaj, body.naslov)

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("user_knowledge").insert({
                "user_id":    uid,
                "naslov":     body.naslov.strip(),
                "sadrzaj":    body.sadrzaj.strip(),
                "tagovi":     tagovi,
                "predmet_id": body.predmet_id,
            }).execute()
        )
        entry_id = r.data[0]["id"] if r.data else None
    except Exception as exc:
        logger.error("[KNOWLEDGE] Greška čuvanja beleške: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Greška pri čuvanju beleške. Pokrenite SQL migraciju za tabelu user_knowledge."
        )

    # Fire-and-forget Pinecone embedding
    if entry_id:
        asyncio.create_task(
            _kb_embed_and_upsert(uid, str(entry_id), body.naslov, body.sadrzaj, tagovi, body.predmet_id)
        )

    logger.info("[KNOWLEDGE] Beleška sačuvana: user=%.8s id=%s tagovi=%s", uid, entry_id, tagovi)
    return {"ok": True, "id": entry_id, "naslov": body.naslov, "tagovi": tagovi}


@router.get("/api/knowledge/search")
@limiter.limit("30/minute")
async def knowledge_search(
    request: Request,
    q: str,
    limit: int = 10,
    user: dict = Depends(get_current_user),
):
    """Semantička pretraga korisnikovih beleški u Pinecone kb_{user_id} namespace-u."""
    uid = user["user_id"]

    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Upit je prekratak.")

    limit = max(1, min(limit, 20))

    try:
        index = _get_pinecone_index()
        emb = await _kb_embed(q.strip())

        results = await asyncio.to_thread(
            lambda: index.query(
                vector=emb,
                top_k=limit,
                namespace=f"kb_{uid}",
                include_metadata=True,
            )
        )

        items = []
        for m in results.matches:
            if m.score >= 0.3:
                items.append({
                    "id":         m.metadata.get("beleska_id", m.id),
                    "naslov":     m.metadata.get("naslov", ""),
                    "sadrzaj":    m.metadata.get("sadrzaj", ""),
                    "tagovi":     m.metadata.get("tagovi", []),
                    "predmet_id": m.metadata.get("predmet_id") or None,
                    "score":      round(m.score, 3),
                })

        return {"results": items, "query": q, "total": len(items)}

    except Exception as e:
        logger.error("[KNOWLEDGE] Search greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri pretraživanju.")


@router.get("/api/knowledge/list")
@limiter.limit("60/minute")
async def knowledge_list(
    request: Request,
    user: dict = Depends(get_current_user),
    predmet_id: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
):
    """Lista beleški iz lične baze znanja. Opcioni filter po predmetu ili tagu."""
    uid  = user["user_id"]
    supa = _get_supa()

    limit = max(1, min(limit, 100))

    try:
        q = (supa.table("user_knowledge")
             .select("id, naslov, sadrzaj, tagovi, predmet_id, created_at")
             .eq("user_id", uid)
             .order("created_at", desc=True)
             .limit(limit))
        if predmet_id:
            q = q.eq("predmet_id", predmet_id)
        if tag:
            q = q.contains("tagovi", [tag.strip()])
        r = await asyncio.to_thread(lambda: q.execute())
        beleske = r.data or []
    except Exception as exc:
        logger.warning("[KNOWLEDGE] Greška listanja beleški: %s", exc)
        return {
            "beleske": [],
            "napomena": "Tabela user_knowledge ne postoji — pokrenite SQL migraciju.",
        }

    return {"beleske": beleske, "ukupno": len(beleske)}


@router.put("/api/knowledge/{entry_id}")
@limiter.limit("30/minute")
async def knowledge_update(
    entry_id: str,
    body: KnowledgeUpdateReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ažuriraj belešku (+ re-embedding u Pinecone)."""
    uid  = user["user_id"]
    supa = _get_supa()

    updates: dict = {}
    if body.naslov  is not None: updates["naslov"]     = body.naslov.strip()
    if body.sadrzaj is not None: updates["sadrzaj"]    = body.sadrzaj.strip()
    if body.tagovi  is not None: updates["tagovi"]     = [t.strip()[:50] for t in body.tagovi[:10] if t.strip()]
    if body.predmet_id is not None: updates["predmet_id"] = body.predmet_id

    if not updates:
        raise HTTPException(status_code=400, detail="Nema polja za ažuriranje.")

    updates["updated_at"] = "now()"

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("user_knowledge")
                .update(updates)
                .eq("id", entry_id)
                .eq("user_id", uid)
                .execute()
        )
        if not r.data:
            raise HTTPException(status_code=404, detail="Beleška nije pronađena.")
        row = r.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[KNOWLEDGE] Greška ažuriranja: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri ažuriranju beleške.")

    # Re-embed ako je sadrzaj ili naslov promenjen
    if "sadrzaj" in updates or "naslov" in updates:
        asyncio.create_task(
            _kb_embed_and_upsert(
                uid, entry_id,
                row.get("naslov", ""),
                row.get("sadrzaj", ""),
                row.get("tagovi", []),
                row.get("predmet_id"),
            )
        )

    return {"ok": True, "id": entry_id}


@router.delete("/api/knowledge/{entry_id}")
@limiter.limit("30/minute")
async def knowledge_delete(
    entry_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Briše belešku iz lične baze znanja (+ briše iz Pinecone)."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("user_knowledge")
                .delete()
                .eq("id", entry_id)
                .eq("user_id", uid)
                .execute()
        )
        if not r.data:
            raise HTTPException(status_code=404, detail="Beleška nije pronađena.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[KNOWLEDGE] Greška brisanja beleške: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri brisanju beleške.")

    # Obriši iz Pinecone (fire-and-forget)
    async def _delete_from_pinecone():
        try:
            index = _get_pinecone_index()
            await asyncio.to_thread(
                lambda: index.delete(
                    ids=[f"kb_{uid}_{entry_id}"],
                    namespace=f"kb_{uid}",
                )
            )
        except Exception as e:
            logger.warning("[KNOWLEDGE] Pinecone delete greška: %s", e)

    asyncio.create_task(_delete_from_pinecone())

    return {"ok": True, "id": entry_id}
