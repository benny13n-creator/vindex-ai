# -*- coding: utf-8 -*-
"""
Vindex AI — services/law_brain_promocija.py

NS008 Task 15 — izričit put od PRIHVAĆENOG autonomnog rada (NS007) do znanja kancelarije, KROZ POSTOJEĆI
staging tok. Ništa se ne uči automatski: prihvatanje rada (ACCEPTED) nije promocija.

  ACCEPTED radni proizvod → korisnik izričito traži „sačuvaj kao znanje kancelarije" → red u `staging_memory`
  (status `pending`, Quality Gate skor) → advokat ga odobri postojećom rutom `POST /api/staging/{id}/approve`
  → tek tada (i samo ako je skor ≥ prag) Pinecone → Law Brain ga vidi kao LAWYER_VERIFIED_ARTIFACT.

Ovaj modul NIKAD ne piše u Pinecone i ne postavlja `is_lawyer_approved`.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

TIP_STAGING = "pripremljen_rad"
_MAKS_TEKSTA = 20000


def tekst_rada(item: dict) -> str:
    """Čitljiv tekst radnog proizvoda: naslov, sažetak i svako polje `tekst` iz sadržaja (determinističko)."""
    delovi = [str(item.get("title") or "").strip(), str(item.get("summary") or "").strip()]

    def _pokupi(v):
        if isinstance(v, dict):
            for k in sorted(v):
                if k == "tekst" and isinstance(v[k], str) and v[k].strip():
                    delovi.append(v[k].strip())
                else:
                    _pokupi(v[k])
        elif isinstance(v, list):
            for x in v:
                _pokupi(x)
    sadrzaj = item.get("content_json")
    if isinstance(sadrzaj, str):
        try:
            sadrzaj = json.loads(sadrzaj)
        except ValueError:
            sadrzaj = None
    _pokupi(sadrzaj or {})
    return "\n\n".join(d for d in delovi if d)[:_MAKS_TEKSTA]


class NijePrihvacen(Exception):
    pass


async def predlozi_kao_znanje(supa, user_id: str, work_id: str) -> Optional[dict]:
    """None = rad ne postoji ili nije korisnikov (isti 404). NijePrihvacen = rad nije ACCEPTED. Ponovljen
    zahtev za isti rad vraća POSTOJEĆI staging red (jedan rad = jedan predlog)."""
    from services.quality_gate import evaluate_draft_quality
    from shared.kancelarija_utils import get_kancelarija_id
    try:
        r = await asyncio.to_thread(lambda: supa.table("autonomy_work_items")
                                    .select("id,user_id,predmet_id,work_type,status,title,summary,content_json")
                                    .eq("id", work_id).eq("user_id", user_id).limit(1).execute())
    except Exception as e:
        from routers.workspace import _nema_tabele
        if _nema_tabele(e):   # pre migracije 136 radni proizvod ne postoji → isti 404 kao nepostojeći
            return None
        raise
    item = (r.data or [None])[0]
    if not item or not item.get("predmet_id"):
        return None
    if item.get("status") != "ACCEPTED":
        raise NijePrihvacen(item.get("status"))
    # vlasništvo predmeta se proverava ponovo (rad je mogao nadživeti promenu vlasništva)
    pr = await asyncio.to_thread(lambda: supa.table("predmeti").select("id").eq("id", item["predmet_id"])
                                 .eq("user_id", user_id).limit(1).execute())
    if not (pr.data or []):
        return None
    post = await asyncio.to_thread(lambda: supa.table("staging_memory").select("id,status,quality_detail")
                                   .eq("user_id", user_id).eq("predmet_id", item["predmet_id"]).eq("tip", TIP_STAGING)
                                   .execute())
    for red in (post.data or []):
        if str((red.get("quality_detail") or {}).get("izvor_rad_id") or "") == str(work_id):
            return {"staging_id": red["id"], "status": red.get("status"), "novo": False}
    tekst = tekst_rada(item)
    if not tekst:
        raise NijePrihvacen("PRAZAN_RAD")
    kvalitet = await evaluate_draft_quality(tekst, TIP_STAGING)
    kanc = await get_kancelarija_id(supa, user_id)
    detalj = {**(kvalitet.get("detail") or {}), "izvor_rad_id": str(work_id), "izvor_vrsta_rada": item.get("work_type")}
    ins = await asyncio.to_thread(lambda: supa.table("staging_memory").insert({
        "user_id": user_id, "kancelarija_id": kanc, "predmet_id": item["predmet_id"], "tip": TIP_STAGING,
        "naziv": (str(item.get("title") or "Pripremljen rad"))[:200], "tekst": tekst,
        "confidence_score": kvalitet["confidence_score"], "quality_detail": detalj,
    }).execute())
    novi = (ins.data or [{}])[0]
    return {"staging_id": novi.get("id"), "status": novi.get("status", "pending"), "novo": True}
