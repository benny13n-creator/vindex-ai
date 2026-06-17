# -*- coding: utf-8 -*-
"""
Vindex AI — routers/saradnja.py

Multi-lawyer collaboration — deljenje predmeta između advokata.

SQL migracija (pokrenuti JEDNOM u Supabase SQL editor):
──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predmet_saradnici (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    predmet_id       TEXT        NOT NULL,
    owner_user_id    TEXT        NOT NULL,
    saradnik_user_id TEXT        NOT NULL,
    uloga            TEXT        NOT NULL DEFAULT 'citanje'
                     CHECK (uloga IN ('citanje', 'saradnja', 'vodenje')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(predmet_id, saradnik_user_id)
);
CREATE INDEX IF NOT EXISTS idx_ps_predmet  ON predmet_saradnici(predmet_id);
CREATE INDEX IF NOT EXISTS idx_ps_saradnik ON predmet_saradnici(saradnik_user_id);
CREATE INDEX IF NOT EXISTS idx_ps_owner    ON predmet_saradnici(owner_user_id);
──────────────────────────────────────────────────────

Uloge:
  citanje   — saradnik vidi predmet/hronologiju/ročišta (read-only)
  saradnja  — može i da dodaje hronologiju/ročišta
  vodenje   — puna kontrola (kao vlasnik, osim brisanja i opoziva)

Endpoints:
  POST   /api/saradnja/dodaj/{predmet_id}            — vlasnik dodaje saradnika
  DELETE /api/saradnja/ukloni/{predmet_id}/{s_uid}   — vlasnik uklanja saradnika
  GET    /api/saradnja/saradnici/{predmet_id}         — lista saradnika (vlasnik vidi)
  GET    /api/saradnja/moji-predmeti                  — saradnik vidi deljene predmete
  GET    /api/saradnja/uloga/{predmet_id}             — moja uloga na predmetu (za UI)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.saradnja")
router = APIRouter(tags=["saradnja"])

_VALID_ULOGE = {"citanje", "saradnja", "vodenje"}


# ─── Modeli ───────────────────────────────────────────────────────────────────

class DodajSaradnikaReq(BaseModel):
    saradnik_email: str  = Field(..., min_length=5, max_length=200)
    uloga:          str  = Field(default="citanje")

    def validate_uloga(self) -> "DodajSaradnikaReq":
        if self.uloga not in _VALID_ULOGE:
            raise ValueError(f"uloga mora biti: {sorted(_VALID_ULOGE)}")
        return self


class IzmeniUloguReq(BaseModel):
    uloga: str = Field(...)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _proveri_vlasnistvo(supa, predmet_id: str, uid: str) -> dict:
    """Vraća predmet row ili baca 404. Mora biti vlasnik."""
    r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id, naziv, status")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if not r.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronađen ili nemate pravo pristupa.")
    return r.data[0]


async def _lookup_user_by_email(supa, email: str) -> Optional[dict]:
    """Pronalazi korisnika po email adresi u profiles tabeli."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("profiles")
                .select("id, email")
                .eq("email", email.strip().lower())
                .limit(1)
                .execute()
        )
        return r.data[0] if r.data else None
    except Exception as exc:
        logger.warning("[SARADNJA] profiles lookup greška: %s", exc)
        return None


# ─── POST /api/saradnja/dodaj/{predmet_id} ────────────────────────────────────

@router.post("/api/saradnja/dodaj/{predmet_id}")
@limiter.limit("20/minute")
async def dodaj_saradnika(
    predmet_id: str,
    body: DodajSaradnikaReq,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vlasnik predmeta dodaje kolegu kao saradnika."""
    if body.uloga not in _VALID_ULOGE:
        raise HTTPException(status_code=400, detail=f"uloga mora biti: {sorted(_VALID_ULOGE)}")

    uid  = user["user_id"]
    supa = _get_supa()

    # Vlasništvo
    predmet = await _proveri_vlasnistvo(supa, predmet_id, uid)

    # Ne može dodati samog sebe
    if body.saradnik_email.strip().lower() == (user.get("email") or "").strip().lower():
        raise HTTPException(status_code=400, detail="Ne možete dodati sebe kao saradnika.")

    # Lookup saradnika po email
    saradnik = await _lookup_user_by_email(supa, body.saradnik_email)
    if not saradnik:
        raise HTTPException(
            status_code=404,
            detail=f"Korisnik sa email adresom '{body.saradnik_email}' nije pronađen u sistemu.",
        )

    saradnik_uid = saradnik["id"]

    # Dodaj (UNIQUE constraint sprečava duplikate)
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_saradnici").upsert(
                {
                    "predmet_id":       predmet_id,
                    "owner_user_id":    uid,
                    "saradnik_user_id": saradnik_uid,
                    "uloga":            body.uloga,
                },
                on_conflict="predmet_id,saradnik_user_id",
            ).execute()
        )
    except Exception as exc:
        logger.error("[SARADNJA] Greška dodavanja saradnika: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri dodavanju saradnika.")

    logger.info("[SARADNJA] Saradnik dodat: predmet=%s owner=%.8s saradnik=%.8s uloga=%s",
                predmet_id, uid, saradnik_uid, body.uloga)
    return {
        "ok":              True,
        "predmet_naziv":   predmet["naziv"],
        "saradnik_email":  body.saradnik_email,
        "saradnik_uid":    saradnik_uid,
        "uloga":           body.uloga,
    }


# ─── DELETE /api/saradnja/ukloni/{predmet_id}/{saradnik_user_id} ─────────────

@router.delete("/api/saradnja/ukloni/{predmet_id}/{saradnik_user_id}")
@limiter.limit("20/minute")
async def ukloni_saradnika(
    predmet_id: str,
    saradnik_user_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vlasnik predmeta uklanja saradnika."""
    uid  = user["user_id"]
    supa = _get_supa()

    await _proveri_vlasnistvo(supa, predmet_id, uid)

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_saradnici")
                .delete()
                .eq("predmet_id", predmet_id)
                .eq("owner_user_id", uid)
                .eq("saradnik_user_id", saradnik_user_id)
                .execute()
        )
        if not r.data:
            raise HTTPException(status_code=404, detail="Saradnik nije pronađen na ovom predmetu.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SARADNJA] Greška uklanjanja saradnika: %s", exc)
        raise HTTPException(status_code=500, detail="Greška pri uklanjanju saradnika.")

    logger.info("[SARADNJA] Saradnik uklonjen: predmet=%s saradnik=%.8s", predmet_id, saradnik_user_id)
    return {"ok": True, "predmet_id": predmet_id, "saradnik_user_id": saradnik_user_id}


# ─── GET /api/saradnja/saradnici/{predmet_id} ─────────────────────────────────

@router.get("/api/saradnja/saradnici/{predmet_id}")
@limiter.limit("30/minute")
async def lista_saradnika(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vlasnik vidi listu saradnika na predmetu."""
    uid  = user["user_id"]
    supa = _get_supa()

    await _proveri_vlasnistvo(supa, predmet_id, uid)

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_saradnici")
                .select("id, saradnik_user_id, uloga, created_at")
                .eq("predmet_id", predmet_id)
                .eq("owner_user_id", uid)
                .order("created_at", desc=False)
                .execute()
        )
        saradnici_raw = r.data or []
    except Exception as exc:
        logger.warning("[SARADNJA] Greška liste saradnika: %s", exc)
        return {"saradnici": [], "napomena": "Tabela predmet_saradnici ne postoji — pokrenite SQL migraciju."}

    # Obogati sa email adresama saradnika
    saradnici = []
    for s in saradnici_raw:
        s_uid = s["saradnik_user_id"]
        email = ""
        try:
            pr = await asyncio.to_thread(
                lambda uid=s_uid: supa.table("profiles")
                    .select("email")
                    .eq("id", uid)
                    .limit(1)
                    .execute()
            )
            email = pr.data[0]["email"] if pr.data else ""
        except Exception:
            pass
        saradnici.append({
            "id":                s["id"],
            "saradnik_user_id":  s_uid,
            "email":             email,
            "uloga":             s["uloga"],
            "dodat":             s["created_at"],
        })

    return {"saradnici": saradnici}


# ─── GET /api/saradnja/moji-predmeti ─────────────────────────────────────────

@router.get("/api/saradnja/moji-predmeti")
@limiter.limit("30/minute")
async def moji_deljeni_predmeti(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Saradnik vidi predmete na kojima sarađuje (nije vlasnik)."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_saradnici")
                .select("predmet_id, uloga, owner_user_id, created_at")
                .eq("saradnik_user_id", uid)
                .order("created_at", desc=True)
                .execute()
        )
        dodele = r.data or []
    except Exception as exc:
        logger.warning("[SARADNJA] Greška moji-predmeti: %s", exc)
        return {"predmeti": [], "napomena": "Tabela predmet_saradnici ne postoji — pokrenite SQL migraciju."}

    if not dodele:
        return {"predmeti": []}

    predmet_ids = [d["predmet_id"] for d in dodele]
    uloga_map   = {d["predmet_id"]: d["uloga"] for d in dodele}

    # Dohvati predmete (bez filtera user_id jer su tuđi predmeti)
    try:
        pr = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id, naziv, opis, tip, status")
                .in_("id", predmet_ids)
                .execute()
        )
        predmeti_raw = pr.data or []
    except Exception as exc:
        logger.error("[SARADNJA] Greška dohvata predmeta: %s", exc)
        return {"predmeti": []}

    predmeti = [
        {
            "predmet_id": p["id"],
            "naziv":      p["naziv"],
            "opis":       p.get("opis"),
            "tip":        p.get("tip"),
            "status":     p.get("status"),
            "uloga":      uloga_map.get(p["id"], "citanje"),
        }
        for p in predmeti_raw
    ]

    return {"predmeti": predmeti}


# ─── GET /api/saradnja/uloga/{predmet_id} ────────────────────────────────────

@router.get("/api/saradnja/uloga/{predmet_id}")
@limiter.limit("60/minute")
async def moja_uloga_na_predmetu(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Vraća ulogu trenutnog korisnika na predmetu.
    Koristi se za UI da zna šta sme da prikazuje/menja.
    Odgovor: {uloga: 'vlasnik'|'citanje'|'saradnja'|'vodenje'|null}
    """
    uid  = user["user_id"]
    supa = _get_supa()

    # Provjeri je li vlasnik
    own_r = await asyncio.to_thread(
        lambda: supa.table("predmeti")
            .select("id")
            .eq("id", predmet_id)
            .eq("user_id", uid)
            .execute()
    )
    if own_r.data:
        return {"predmet_id": predmet_id, "uloga": "vlasnik"}

    # Provjeri saradnju
    try:
        sar_r = await asyncio.to_thread(
            lambda: supa.table("predmet_saradnici")
                .select("uloga")
                .eq("predmet_id", predmet_id)
                .eq("saradnik_user_id", uid)
                .limit(1)
                .execute()
        )
        if sar_r.data:
            return {"predmet_id": predmet_id, "uloga": sar_r.data[0]["uloga"]}
    except Exception:
        pass

    return {"predmet_id": predmet_id, "uloga": None}
