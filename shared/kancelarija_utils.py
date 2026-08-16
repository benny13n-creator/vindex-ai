# -*- coding: utf-8 -*-
"""
Vindex AI — shared/kancelarija_utils.py

Kanonska funkcija za razrešavanje kancelarija_id datog korisnika + RAG
namespace šema zasnovana na tom rezultatu.

Konsolidovano 2026-07-26 (Institutional Learning & RAG Audit, sprovođenje
stavke #1/#2) -- pre ovoga su `routers/firm_memory.py` i
`routers/corrections.py` svaki imali sopstvenu, nezavisnu ali funkcionalno
identičnu kopiju iste logike (`_get_kancelarija_id`). Oba sada uvoze odavde.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional


def get_kancelarija_id_sync(supa: Any, uid: str) -> Optional[str]:
    """Sinhrono jezgro razrešavanja kancelarije. JEDINA implementacija upita.

    BR-003: `retrieve_documents` je sinhrona funkcija (poziva se kroz
    `asyncio.to_thread`), pa joj `async` varijanta nije upotrebljiva. Umesto
    druge kopije istih upita, logika je izvučena OVDE, a `get_kancelarija_id`
    ispod je sada tanak async omotač nad ovim jezgrom. Broj mesta na kojima se
    zna KAKO se kancelarija razrešava time pada sa jedan na jedan -- ne raste.

    Vraća `None` i kad korisnik nema kancelariju (solo advokat) i kad upit
    padne. Obe situacije vode u `user_{uid}` namespace, dakle u UŽI opseg --
    greška nikad ne proširuje vidljivost.
    """
    try:
        r = (supa.table("kancelarije")
             .select("id")
             .eq("admin_uid", uid)
             .maybe_single()
             .execute())
        if r.data:
            return r.data["id"]
        r2 = (supa.table("kancelarija_clanovi")
              .select("kancelarija_id")
              .eq("user_id", uid)
              .eq("status", "ACTIVE")
              .maybe_single()
              .execute())
        return r2.data.get("kancelarija_id") if r2.data else None
    except Exception:
        return None


async def get_kancelarija_id(supa: Any, uid: str) -> Optional[str]:
    """Vraća kancelarija_id kancelarije čiji je `uid` admin ili aktivan član,
    ili None ako korisnik ne pripada nijednoj kancelariji (solo advokat)."""
    return await asyncio.to_thread(get_kancelarija_id_sync, supa, uid)


def rag_owner_namespace(user_id: str, kancelarija_id: Optional[str]) -> str:
    """Pinecone namespace za TRAJNE (case_doc/draft_final) vektore jednog
    "vlasnika" znanja -- kancelarije ako korisnik pripada jednoj, inače
    pojedinačnog korisnika (solo advokat, nema deljenja).

    Institutional Learning & RAG Audit (2026-07-26) #1: zamenjuje raniju
    `pred_{session_id}` šemu (nasumičan ID po uploadu, bez ikakve
    mogućnosti agregacije) jednim stabilnim namespace-om po vlasniku, uz
    `predmet_id`/`kancelarija_id`/`type` u metadati svakog vektora (v.
    uploaded_doc/ingest.py's `extra_metadata` parametar) za scoping unutar
    tog namespace-a."""
    if kancelarija_id:
        return f"kancelarija_{kancelarija_id}"
    return f"user_{user_id}"
