# -*- coding: utf-8 -*-
"""
Vindex AI — routers/search.py

GET /api/search?q=...&vrste=predmeti,klijenti,dokumenti,billing,hronologija&limit=5

Globalna pretraga: pretražuje predmete, klijente, dokumente, billing i hronologiju
korisnika. Vrši ilike pretragu po ključnim tekstualnim kolonama.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.search")
router = APIRouter(tags=["search"])

_VALID_VRSTE = {"predmeti", "klijenti", "dokumenti", "billing", "hronologija", "beleske"}
_MAX_LIMIT   = 10
_MAX_Q_LEN   = 200


# ─── Patchable DB wrapper ─────────────────────────────────────────────────────

def _db(fn):
    return asyncio.to_thread(fn)


# ─── Per-type search helpers ──────────────────────────────────────────────────

def _search_predmeti(supa, uid: str, q: str, limit: int) -> list[dict]:
    q2 = q.replace("%", "")
    r  = (supa.table("predmeti")
          .select("id, naziv, opis, tip, status")
          .eq("user_id", uid)
          .or_(f"naziv.ilike.%{q2}%,opis.ilike.%{q2}%")
          .limit(limit)
          .execute())
    return [
        {
            "tip":        "predmet",
            "id":         row["id"],
            "naziv":      row.get("naziv") or "",
            "preview":    (row.get("opis") or "")[:100],
            "meta":       {"status": row.get("status"), "tip": row.get("tip")},
        }
        for row in (r.data or [])
    ]


def _search_klijenti(supa, uid: str, q: str, limit: int) -> list[dict]:
    q2 = q.replace("%", "")
    r  = (supa.table("klijenti")
          .select("id, ime, prezime, naziv_firme, email, pib")
          .eq("user_id", uid)
          .or_(f"ime.ilike.%{q2}%,prezime.ilike.%{q2}%,naziv_firme.ilike.%{q2}%,email.ilike.%{q2}%,pib.ilike.%{q2}%")
          .limit(limit)
          .execute())
    return [
        {
            "tip":    "klijent",
            "id":     row["id"],
            "naziv":  " ".join(filter(None, [row.get("ime"), row.get("prezime"), row.get("naziv_firme")])) or row.get("email", ""),
            "preview": row.get("email") or row.get("pib") or "",
            "meta":   {},
        }
        for row in (r.data or [])
    ]


def _search_dokumenti(supa, uid: str, q: str, limit: int) -> list[dict]:
    q2 = q.replace("%", "")
    r  = (supa.table("uploaded_documents")
          .select("id, naziv_fajla, predmet_id, tip_fajla, created_at")
          .eq("user_id", uid)
          .or_(f"naziv_fajla.ilike.%{q2}%,extracted_text.ilike.%{q2}%")
          .limit(limit)
          .execute())
    return [
        {
            "tip":       "dokument",
            "id":        row["id"],
            "naziv":     row.get("naziv_fajla") or "",
            "preview":   row.get("tip_fajla") or "",
            "meta":      {"predmet_id": row.get("predmet_id")},
        }
        for row in (r.data or [])
    ]


def _search_billing(supa, uid: str, q: str, limit: int) -> list[dict]:
    q2 = q.replace("%", "")
    r  = (supa.table("billing_entries")
          .select("id, opis, iznos_rsd, predmet_id, datum")
          .eq("user_id", uid)
          .ilike("opis", f"%{q2}%")
          .limit(limit)
          .execute())
    return [
        {
            "tip":     "billing",
            "id":      row["id"],
            "naziv":   row.get("opis") or "",
            "preview": f"{float(row.get('iznos_rsd') or 0):,.0f} RSD · {row.get('datum', '')}",
            "meta":    {"predmet_id": row.get("predmet_id")},
        }
        for row in (r.data or [])
    ]


def _get_user_predmet_ids(supa, uid: str) -> list[str]:
    r = (supa.table("predmeti")
         .select("id")
         .eq("user_id", uid)
         .limit(500)
         .execute())
    return [row["id"] for row in (r.data or [])]


def _search_hronologija(supa, uid: str, q: str, limit: int) -> list[dict]:
    q2   = q.replace("%", "")
    pids = _get_user_predmet_ids(supa, uid)
    if not pids:
        return []
    r = (supa.table("predmet_hronologija")
         .select("id, predmet_id, dogadjaj, datum_iso, vaznost")
         .in_("predmet_id", pids[:200])
         .ilike("dogadjaj", f"%{q2}%")
         .limit(limit)
         .execute())
    return [
        {
            "tip":     "hronologija",
            "id":      row["id"],
            "naziv":   row.get("dogadjaj") or "",
            "preview": row.get("datum_iso") or "",
            "meta":    {"predmet_id": row.get("predmet_id"), "vaznost": row.get("vaznost")},
        }
        for row in (r.data or [])
    ]


def _search_beleske(supa, uid: str, q: str, limit: int) -> list[dict]:
    q2   = q.replace("%", "")
    pids = _get_user_predmet_ids(supa, uid)
    if not pids:
        return []
    r = (supa.table("predmet_beleske")
         .select("id, predmet_id, sadrzaj, created_at")
         .in_("predmet_id", pids[:200])
         .ilike("sadrzaj", f"%{q2}%")
         .limit(limit)
         .execute())
    return [
        {
            "tip":     "beleska",
            "id":      row["id"],
            "naziv":   (row.get("sadrzaj") or "")[:80],
            "preview": row.get("created_at", "")[:10],
            "meta":    {"predmet_id": row.get("predmet_id")},
        }
        for row in (r.data or [])
    ]


_SEARCHERS = {
    "predmeti":   _search_predmeti,
    "klijenti":   _search_klijenti,
    "dokumenti":  _search_dokumenti,
    "billing":    _search_billing,
    "hronologija": _search_hronologija,
    "beleske":    _search_beleske,
}


# ─── GET /api/search ─────────────────────────────────────────────────────────

@router.get("/api/search")
@limiter.limit("60/minute")
async def global_search(
    request: Request,
    q:       str,
    vrste:   Optional[str] = None,
    limit:   int           = 5,
    user:    dict          = Depends(get_current_user),
):
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(status_code=422, detail="Upit mora imati barem 2 karaktera.")
    if len(q) > _MAX_Q_LEN:
        q = q[:_MAX_Q_LEN]

    limit = max(1, min(limit, _MAX_LIMIT))
    uid   = user["user_id"]
    supa  = _get_supa()

    if vrste:
        tražene = {v.strip() for v in vrste.split(",") if v.strip() in _VALID_VRSTE}
    else:
        tražene = _VALID_VRSTE

    tasks = {
        tip: _db(lambda fn=fn: fn(supa, uid, q, limit))
        for tip, fn in _SEARCHERS.items()
        if tip in tražene
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    grouped: dict[str, list] = {}
    for tip, res in zip(tasks.keys(), results):
        if isinstance(res, Exception):
            logger.warning("[SEARCH] tip=%s greška: %s", tip, res)
            grouped[tip] = []
        else:
            grouped[tip] = res

    ukupno = sum(len(v) for v in grouped.values())
    return {"q": q, "ukupno": ukupno, **grouped}
