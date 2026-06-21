# -*- coding: utf-8 -*-
"""
Vindex AI — routers/knowledge_base.py

Lična baza znanja — advokat čuva lične beleške, stavove i reference.
Čuva se u Supabase tabeli user_knowledge.

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
  POST   /api/knowledge/save    — sačuvaj belešku
  GET    /api/knowledge/list    — lista beleški (filter po tagovima / predmetu)
  DELETE /api/knowledge/{id}    — obriši belešku
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.knowledge_base")
router = APIRouter(tags=["knowledge_base"])


class KnowledgeSaveReq(BaseModel):
    naslov:     str           = Field(..., min_length=2, max_length=200)
    sadrzaj:    str           = Field(..., min_length=5, max_length=20000)
    tagovi:     List[str]     = Field(default_factory=list)
    predmet_id: Optional[str] = Field(default=None)


@router.post("/api/knowledge/save")
@limiter.limit("30/minute")
async def knowledge_save(
    body: KnowledgeSaveReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Advokat čuva belešku u ličnu bazu znanja."""
    uid  = user["user_id"]
    supa = _get_supa()

    tagovi = [t.strip()[:50] for t in body.tagovi[:10] if t.strip()]

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

    logger.info("[KNOWLEDGE] Beleška sačuvana: user=%.8s id=%s", uid, entry_id)
    return {"ok": True, "id": entry_id, "naslov": body.naslov}


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


@router.delete("/api/knowledge/{entry_id}")
@limiter.limit("30/minute")
async def knowledge_delete(
    entry_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Briše belešku iz lične baze znanja."""
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

    return {"ok": True, "id": entry_id}
