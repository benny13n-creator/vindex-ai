# -*- coding: utf-8 -*-
"""
Vindex AI — routers/kancelarija.py
Phase 5.4: Multi-user firm account + role management.

Endpointi:
  GET  /api/kancelarija/moja           — info o firmi + lista članova
  POST /api/kancelarija/kreiraj        — kreiraj novu firmu
  PUT  /api/kancelarija/naziv          — preimenuj firmu (samo admin)
  POST /api/kancelarija/pozovi         — pozovi člana po emailu (samo admin)
  POST /api/kancelarija/prihvati       — prihvati pozivnicu (po email matchu)
  POST /api/kancelarija/odbij          — odbij pozivnicu
  DELETE /api/kancelarija/ukloni/{id}  — ukloni člana (samo admin)
  PUT  /api/kancelarija/uloga/{id}     — promeni ulogu (samo admin)
  DELETE /api/kancelarija/napusti      — napusti firmu (ne-admin)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.kancelarija")
router = APIRouter(tags=["kancelarija"])

ULOGE = ("admin", "partner", "saradnik", "citanje")
ULOGA_LABELS = {
    "admin":    "Administrator",
    "partner":  "Partner",
    "saradnik": "Saradnik",
    "citanje":  "Samo čitanje",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_firma_for_admin(supa, uid: str) -> Optional[dict]:
    res = supa.table("kancelarije").select("*").eq("admin_uid", uid).maybe_single().execute()
    return res.data if res.data else None


def _get_firma_for_member(supa, uid: str, email: str) -> Optional[dict]:
    """Returns kancelarija_clanovi row where user_id matches (aktivan member)."""
    res = (
        supa.table("kancelarija_clanovi")
        .select("*, kancelarije(*)")
        .eq("user_id", uid)
        .eq("status", "aktivan")
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None


def _require_firma_admin(supa, uid: str) -> dict:
    firma = _get_firma_for_admin(supa, uid)
    if not firma:
        raise HTTPException(status_code=403, detail="Niste administrator nijedne firme.")
    return firma


def _get_clanovi(supa, kancelarija_id: str) -> list[dict]:
    res = (
        supa.table("kancelarija_clanovi")
        .select("*")
        .eq("kancelarija_id", kancelarija_id)
        .order("invited_at")
        .execute()
    )
    return res.data or []


# ─── Models ───────────────────────────────────────────────────────────────────

class KreirajReq(BaseModel):
    naziv: str = Field(..., min_length=2, max_length=120)


class NazivReq(BaseModel):
    naziv: str = Field(..., min_length=2, max_length=120)


class PozovReq(BaseModel):
    email: str = Field(..., max_length=255)
    uloga: str = Field(default="saradnik")

    @field_validator("email")
    @classmethod
    def _norm_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("uloga")
    @classmethod
    def _valid_uloga(cls, v: str) -> str:
        if v not in ULOGE:
            raise ValueError(f"Uloga mora biti jedna od: {ULOGE}")
        if v == "admin":
            raise ValueError("Ne možete pozvati drugog administratora — samo jedan admin po firmi.")
        return v


class UlogaReq(BaseModel):
    uloga: str = Field(...)

    @field_validator("uloga")
    @classmethod
    def _valid_uloga(cls, v: str) -> str:
        if v not in ULOGE:
            raise ValueError(f"Uloga mora biti jedna od: {ULOGE}")
        if v == "admin":
            raise ValueError("Uloga 'admin' se ne može dodeliti članovima — koristite prenos vlasništva.")
        return v


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/kancelarija/moja")
@limiter.limit("60/minute")
async def moja_kancelarija(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraća firmu korisnika + listu članova. Radi i za admin i za member."""
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()

    def _fetch():
        firma = _get_firma_for_admin(supa, uid)
        role  = "admin"
        if not firma:
            member_row = _get_firma_for_member(supa, uid, email)
            if not member_row:
                # Check pending invitation by email
                pending = (
                    supa.table("kancelarija_clanovi")
                    .select("*, kancelarije(*)")
                    .eq("email", email)
                    .eq("status", "pending")
                    .maybe_single()
                    .execute()
                )
                if pending.data:
                    k = pending.data.get("kancelarije") or {}
                    return {
                        "status":      "pending_invite",
                        "invite_id":   pending.data["id"],
                        "firma_naziv": k.get("naziv", ""),
                        "uloga":       pending.data.get("uloga"),
                    }
                return {"status": "no_firma"}
            firma = member_row.get("kancelarije") or {}
            role  = member_row.get("uloga", "saradnik")

        clanovi = _get_clanovi(supa, firma["id"])
        return {
            "status":    "aktivan",
            "moja_uloga": role,
            "firma": {
                "id":         firma["id"],
                "naziv":      firma["naziv"],
                "admin_uid":  firma.get("admin_uid"),
                "created_at": firma.get("created_at"),
            },
            "clanovi": [
                {
                    "id":         c["id"],
                    "email":      c["email"],
                    "uloga":      c["uloga"],
                    "uloga_label": ULOGA_LABELS.get(c["uloga"], c["uloga"]),
                    "status":     c["status"],
                    "joined_at":  c.get("joined_at"),
                }
                for c in clanovi
            ],
        }

    return await asyncio.to_thread(_fetch)


@router.post("/api/kancelarija/kreiraj", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def kreiraj_kancelariju(
    request: Request,
    req: KreirajReq,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    def _create():
        existing = _get_firma_for_admin(supa, uid)
        if existing:
            raise HTTPException(status_code=409, detail="Već ste administrator firme. Jedna firma po adminu.")
        member_row = _get_firma_for_member(supa, uid, (user.get("email") or "").lower())
        if member_row:
            raise HTTPException(status_code=409, detail="Već ste član druge firme. Napustite je pre kreiranja nove.")

        res = supa.table("kancelarije").insert({
            "naziv":      req.naziv.strip(),
            "admin_uid":  uid,
            "created_at": _now(),
        }).execute()
        firma = res.data[0] if res.data else {}
        logger.info("[KANCELARIJA] Kreirana: '%s' admin=%.8s", req.naziv, uid)
        return {"ok": True, "firma_id": firma.get("id"), "naziv": req.naziv.strip()}

    return await asyncio.to_thread(_create)


@router.put("/api/kancelarija/naziv")
@limiter.limit("10/minute")
async def promeni_naziv(
    request: Request,
    req: NazivReq,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    def _rename():
        firma = _require_firma_admin(supa, uid)
        supa.table("kancelarije").update({"naziv": req.naziv.strip()}).eq("id", firma["id"]).execute()
        return {"ok": True, "naziv": req.naziv.strip()}

    return await asyncio.to_thread(_rename)


@router.post("/api/kancelarija/pozovi", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def pozovi_clana(
    request: Request,
    req: PozovReq,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    def _invite():
        firma = _require_firma_admin(supa, uid)
        existing = (
            supa.table("kancelarija_clanovi")
            .select("id, status")
            .eq("kancelarija_id", firma["id"])
            .eq("email", req.email)
            .maybe_single()
            .execute()
        )
        if existing.data:
            st = existing.data.get("status")
            if st in ("pending", "aktivan"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Korisnik '{req.email}' je već {st} član firme."
                )
            # Resend invite if previously declined
            supa.table("kancelarija_clanovi").update({
                "uloga":      req.uloga,
                "status":     "pending",
                "invited_by": uid,
                "invited_at": _now(),
                "joined_at":  None,
            }).eq("id", existing.data["id"]).execute()
            return {"ok": True, "action": "reinvited", "email": req.email}

        supa.table("kancelarija_clanovi").insert({
            "kancelarija_id": firma["id"],
            "email":          req.email,
            "uloga":          req.uloga,
            "status":         "pending",
            "invited_by":     uid,
            "invited_at":     _now(),
        }).execute()
        logger.info("[KANCELARIJA] Poziv poslan: %s -> %s uloga=%s", uid[:8], req.email, req.uloga)
        return {"ok": True, "action": "invited", "email": req.email, "uloga": req.uloga}

    return await asyncio.to_thread(_invite)


@router.post("/api/kancelarija/prihvati")
@limiter.limit("10/minute")
async def prihvati_pozivnicu(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()

    def _accept():
        pending = (
            supa.table("kancelarija_clanovi")
            .select("*")
            .eq("email", email)
            .eq("status", "pending")
            .maybe_single()
            .execute()
        )
        if not pending.data:
            raise HTTPException(status_code=404, detail="Nema čekajuće pozivnice za vaš email.")
        supa.table("kancelarija_clanovi").update({
            "status":    "aktivan",
            "user_id":   uid,
            "joined_at": _now(),
        }).eq("id", pending.data["id"]).execute()
        logger.info("[KANCELARIJA] Pozivnica prihvaćena: %s firma=%s", email, pending.data["kancelarija_id"])
        return {"ok": True, "kancelarija_id": pending.data["kancelarija_id"]}

    return await asyncio.to_thread(_accept)


@router.post("/api/kancelarija/odbij")
@limiter.limit("10/minute")
async def odbij_pozivnicu(
    request: Request,
    user: dict = Depends(get_current_user),
):
    email = (user.get("email") or "").lower()
    supa  = _get_supa()

    def _decline():
        pending = (
            supa.table("kancelarija_clanovi")
            .select("id")
            .eq("email", email)
            .eq("status", "pending")
            .maybe_single()
            .execute()
        )
        if not pending.data:
            raise HTTPException(status_code=404, detail="Nema čekajuće pozivnice.")
        supa.table("kancelarija_clanovi").update({"status": "odbijen"}).eq("id", pending.data["id"]).execute()
        return {"ok": True}

    return await asyncio.to_thread(_decline)


@router.delete("/api/kancelarija/ukloni/{clan_id}")
@limiter.limit("20/minute")
async def ukloni_clana(
    request: Request,
    clan_id: str,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    def _remove():
        firma = _require_firma_admin(supa, uid)
        row = (
            supa.table("kancelarija_clanovi")
            .select("id, email, user_id")
            .eq("id", clan_id)
            .eq("kancelarija_id", firma["id"])
            .maybe_single()
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Član nije pronađen u vašoj firmi.")
        if row.data.get("user_id") == uid:
            raise HTTPException(status_code=400, detail="Ne možete ukloniti sebe. Koristite 'Napusti firmu'.")
        supa.table("kancelarija_clanovi").delete().eq("id", clan_id).execute()
        logger.info("[KANCELARIJA] Uklonjen: %s iz firme %s", row.data.get("email"), firma["id"])
        return {"ok": True}

    return await asyncio.to_thread(_remove)


@router.put("/api/kancelarija/uloga/{clan_id}")
@limiter.limit("20/minute")
async def promeni_ulogu(
    request: Request,
    clan_id: str,
    req: UlogaReq,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    supa = _get_supa()

    def _change_role():
        firma = _require_firma_admin(supa, uid)
        row = (
            supa.table("kancelarija_clanovi")
            .select("id, email")
            .eq("id", clan_id)
            .eq("kancelarija_id", firma["id"])
            .maybe_single()
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Član nije pronađen u vašoj firmi.")
        supa.table("kancelarija_clanovi").update({"uloga": req.uloga}).eq("id", clan_id).execute()
        return {"ok": True, "uloga": req.uloga}

    return await asyncio.to_thread(_change_role)


@router.delete("/api/kancelarija/napusti")
@limiter.limit("5/minute")
async def napusti_kancelariju(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()

    def _leave():
        firma_admin = _get_firma_for_admin(supa, uid)
        if firma_admin:
            raise HTTPException(
                status_code=400,
                detail="Administrator ne može napustiti firmu. Prenesite vlasništvo ili obrišite firmu."
            )
        row = (
            supa.table("kancelarija_clanovi")
            .select("id")
            .eq("user_id", uid)
            .eq("status", "aktivan")
            .maybe_single()
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Niste član nijedne firme.")
        supa.table("kancelarija_clanovi").delete().eq("id", row.data["id"]).execute()
        logger.info("[KANCELARIJA] %s napustio kancelariju.", email)
        return {"ok": True}

    return await asyncio.to_thread(_leave)
