# -*- coding: utf-8 -*-
"""
Vindex AI — routers/kancelarija.py
Phase 5.4 + Faza 71: Multi-user firm account + seat lifecycle.

Seat model (5 stanja, migracija 067) — vidi shared/seats.py za punu formulu
i pravila prelaza:
    ACTIVE / INVITED  — troše mesto
    PENDING / SUSPENDED / REMOVED — ne troše mesto

Endpointi:
  GET  /api/kancelarija/moja           — info o firmi + lista članova (ACTIVE/INVITED/SUSPENDED)
  POST /api/kancelarija/kreiraj        — kreiraj novu firmu
  PUT  /api/kancelarija/naziv          — preimenuj firmu (samo admin)
  GET  /api/kancelarija/mesta          — pregled iskorišćenosti mesta (samo admin)
  GET  /api/kancelarija/istorija       — audit log promena članstva (samo admin)
  POST /api/kancelarija/pozovi         — pozovi člana po emailu (samo admin, proverava slobodno mesto)
  POST /api/kancelarija/prihvati       — prihvati pozivnicu (po email matchu)
  POST /api/kancelarija/odbij          — odbij pozivnicu
  POST /api/kancelarija/suspenduj/{id} — privremeno isključi člana (samo admin)
  POST /api/kancelarija/reaktiviraj/{id} — vrati suspendovanog člana (samo admin, proverava slobodno mesto)
  DELETE /api/kancelarija/ukloni/{id}  — ukloni člana — soft-delete, status=REMOVED (samo admin)
  PUT  /api/kancelarija/uloga/{id}     — promeni ulogu (samo admin)
  DELETE /api/kancelarija/napusti      — napusti firmu — soft-delete, status=REMOVED (ne-admin)
  GET  /api/kancelarija/predmeti       — predmeti svih ACTIVE članova
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
from shared.seats import SeatService

logger = logging.getLogger("vindex.kancelarija")
router = APIRouter(tags=["kancelarija"])

# Firma-membership uloge — NAMERNO odvojene od shared.rbac.ULOGE (koje su za
# širi RBAC sistem: admin/partner/advokat/pripravnik/administracija/citanje,
# nema "saradnik"). Pronađeno pri Fazi 71 testiranju: kancelarija.py je ranije
# uvozio shared.rbac.ULOGE za validaciju, ali frontend (index.html invite
# dropdown) i PozovReq default nude "partner"/"saradnik"/"citanje" — "saradnik"
# nikad nije bio validan po toj listi, pa je svaki poziv sa podrazumevanom
# ulogom tiho padao na 422. Ovo je taj tačan skup koji frontend stvarno nudi.
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
    """Returns kancelarija_clanovi row where user_id matches AND status=ACTIVE."""
    res = (
        supa.table("kancelarija_clanovi")
        .select("*, kancelarije(*)")
        .eq("user_id", uid)
        .eq("status", "ACTIVE")
        .maybe_single()
        .execute()
    )
    return res.data if res.data else None


def _require_firma_admin(supa, uid: str) -> dict:
    firma = _get_firma_for_admin(supa, uid)
    if not firma:
        raise HTTPException(status_code=403, detail="Niste administrator nijedne firme.")
    return firma


def _get_clanovi(supa, kancelarija_id: str, ukljuci_uklonjene: bool = False) -> list[dict]:
    q = (
        supa.table("kancelarija_clanovi")
        .select("*")
        .eq("kancelarija_id", kancelarija_id)
    )
    if not ukljuci_uklonjene:
        q = q.neq("status", "REMOVED")
    res = q.order("invited_at").execute()
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
                    .eq("status", "INVITED")
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
                    "id":          c["id"],
                    "email":       c["email"],
                    "uloga":       c["uloga"],
                    "uloga_label": ULOGA_LABELS.get(c["uloga"], c["uloga"]),
                    "status":      c["status"],
                    "joined_at":   c.get("joined_at"),
                    "suspended_at": c.get("suspended_at"),
                }
                for c in clanovi
            ],
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as exc:
        logger.warning("[KANCELARIJA] moja_kancelarija greška: %s", exc)
        return {"status": "no_firma"}


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


@router.get("/api/kancelarija/mesta")
@limiter.limit("60/minute")
async def pregled_mesta(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Administrativni pregled iskorišćenosti mesta — samo admin firme."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await asyncio.to_thread(_require_firma_admin, supa, uid)
    return await SeatService.get_seat_summary(firma["id"], uid)


@router.get("/api/kancelarija/istorija")
@limiter.limit("30/minute")
async def istorija_mesta(
    request: Request,
    user: dict = Depends(get_current_user),
    limit: int = 100,
):
    """Audit log svake promene članstva — samo admin firme. Trajan zapis,
    izvor istine za sporove oko broja korisnika."""
    uid  = user["user_id"]
    supa = _get_supa()
    firma = await asyncio.to_thread(_require_firma_admin, supa, uid)

    def _fetch():
        res = (
            supa.table("kancelarija_seat_audit")
            .select("*")
            .eq("kancelarija_id", firma["id"])
            .order("created_at", desc=True)
            .limit(min(limit, 500))
            .execute()
        )
        return res.data or []

    events = await asyncio.to_thread(_fetch)
    return {"firma_id": firma["id"], "events": events}


@router.post("/api/kancelarija/pozovi", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def pozovi_clana(
    request: Request,
    req: PozovReq,
    user: dict = Depends(get_current_user),
):
    uid  = user["user_id"]
    email = (user.get("email") or "").lower()
    supa = _get_supa()

    firma = await asyncio.to_thread(_require_firma_admin, supa, uid)
    await SeatService.assert_seat_available(firma["id"], uid)

    def _find_existing():
        return (
            supa.table("kancelarija_clanovi")
            .select("id, status")
            .eq("kancelarija_id", firma["id"])
            .eq("email", req.email)
            .maybe_single()
            .execute()
        )

    existing = await asyncio.to_thread(_find_existing)

    if existing.data:
        st = existing.data.get("status")
        if st in ("INVITED", "ACTIVE", "PENDING", "SUSPENDED"):
            raise HTTPException(
                status_code=409,
                detail=f"Korisnik '{req.email}' je već {st} član firme."
            )
        # st == "REMOVED" — re-invite reuses the same row (audit trail keeps
        # the full history: original REMOVED transition stays on record).
        await SeatService.transition(
            kancelarija_id=firma["id"], clan_id=existing.data["id"], clan_email=req.email,
            actor_uid=uid, actor_email=email, action="invite",
            from_status="REMOVED", to_status="INVITED",
            extra_fields={
                "uloga": req.uloga, "invited_by": uid, "invited_at": _now(),
                "joined_at": None, "removed_at": None, "removed_reason": None,
            },
        )
        return {"ok": True, "action": "reinvited", "email": req.email}

    def _insert():
        res = supa.table("kancelarija_clanovi").insert({
            "kancelarija_id": firma["id"],
            "email":          req.email,
            "uloga":          req.uloga,
            "status":         "INVITED",
            "invited_by":     uid,
            "invited_at":     _now(),
        }).execute()
        return res.data[0] if res.data else {}

    new_row = await asyncio.to_thread(_insert)
    await SeatService.transition(
        kancelarija_id=firma["id"], clan_id=new_row.get("id"), clan_email=req.email,
        actor_uid=uid, actor_email=email, action="invite",
        from_status=None, to_status="INVITED",
    )
    logger.info("[KANCELARIJA] Poziv poslan: %s -> %s uloga=%s", uid[:8], req.email, req.uloga)
    return {"ok": True, "action": "invited", "email": req.email, "uloga": req.uloga}


@router.post("/api/kancelarija/prihvati")
@limiter.limit("10/minute")
async def prihvati_pozivnicu(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()

    def _find():
        return (
            supa.table("kancelarija_clanovi")
            .select("*")
            .eq("email", email)
            .eq("status", "INVITED")
            .maybe_single()
            .execute()
        )

    pending = await asyncio.to_thread(_find)
    if not pending.data:
        raise HTTPException(status_code=404, detail="Nema čekajuće pozivnice za vaš email.")

    await SeatService.transition(
        kancelarija_id=pending.data["kancelarija_id"], clan_id=pending.data["id"], clan_email=email,
        actor_uid=uid, actor_email=email, action="accept",
        from_status="INVITED", to_status="ACTIVE",
        extra_fields={"user_id": uid, "joined_at": _now()},
    )
    logger.info("[KANCELARIJA] Pozivnica prihvaćena: %s firma=%s", email, pending.data["kancelarija_id"])
    return {"ok": True, "kancelarija_id": pending.data["kancelarija_id"]}


@router.post("/api/kancelarija/odbij")
@limiter.limit("10/minute")
async def odbij_pozivnicu(
    request: Request,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()

    def _find():
        return (
            supa.table("kancelarija_clanovi")
            .select("id, kancelarija_id")
            .eq("email", email)
            .eq("status", "INVITED")
            .maybe_single()
            .execute()
        )

    pending = await asyncio.to_thread(_find)
    if not pending.data:
        raise HTTPException(status_code=404, detail="Nema čekajuće pozivnice.")

    await SeatService.transition(
        kancelarija_id=pending.data["kancelarija_id"], clan_id=pending.data["id"], clan_email=email,
        actor_uid=uid, actor_email=email, action="decline",
        from_status="INVITED", to_status="REMOVED",
        extra_fields={"removed_reason": "declined", "removed_at": _now()},
    )
    return {"ok": True}


@router.post("/api/kancelarija/suspenduj/{clan_id}")
@limiter.limit("20/minute")
async def suspenduj_clana(
    request: Request,
    clan_id: str,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()
    firma = await asyncio.to_thread(_require_firma_admin, supa, uid)

    def _find():
        return (
            supa.table("kancelarija_clanovi")
            .select("id, email, status, user_id")
            .eq("id", clan_id)
            .eq("kancelarija_id", firma["id"])
            .maybe_single()
            .execute()
        )

    row = await asyncio.to_thread(_find)
    if not row.data:
        raise HTTPException(status_code=404, detail="Član nije pronađen u vašoj firmi.")
    if row.data.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail=f"Član nije aktivan (trenutno: {row.data.get('status')}) — ne može se suspendovati.")

    await SeatService.transition(
        kancelarija_id=firma["id"], clan_id=clan_id, clan_email=row.data["email"],
        actor_uid=uid, actor_email=email, action="suspend",
        from_status="ACTIVE", to_status="SUSPENDED",
        extra_fields={"suspended_at": _now()},
    )
    logger.info("[KANCELARIJA] Suspendovan: %s u firmi %s", row.data["email"], firma["id"])
    return {"ok": True}


@router.post("/api/kancelarija/reaktiviraj/{clan_id}")
@limiter.limit("20/minute")
async def reaktiviraj_clana(
    request: Request,
    clan_id: str,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()
    firma = await asyncio.to_thread(_require_firma_admin, supa, uid)

    def _find():
        return (
            supa.table("kancelarija_clanovi")
            .select("id, email, status")
            .eq("id", clan_id)
            .eq("kancelarija_id", firma["id"])
            .maybe_single()
            .execute()
        )

    row = await asyncio.to_thread(_find)
    if not row.data:
        raise HTTPException(status_code=404, detail="Član nije pronađen u vašoj firmi.")
    if row.data.get("status") != "SUSPENDED":
        raise HTTPException(status_code=400, detail=f"Član nije suspendovan (trenutno: {row.data.get('status')}).")

    # SUSPENDED ne troši mesto — reaktivacija ga vraća na ACTIVE koje troši,
    # pa mora ponovo da prođe proveru kapaciteta (drugi pozivi/prijave su se
    # mogli desiti dok je bio suspendovan).
    await SeatService.assert_seat_available(firma["id"], uid)

    await SeatService.transition(
        kancelarija_id=firma["id"], clan_id=clan_id, clan_email=row.data["email"],
        actor_uid=uid, actor_email=email, action="reactivate",
        from_status="SUSPENDED", to_status="ACTIVE",
        extra_fields={"suspended_at": None},
    )
    logger.info("[KANCELARIJA] Reaktiviran: %s u firmi %s", row.data["email"], firma["id"])
    return {"ok": True}


@router.delete("/api/kancelarija/ukloni/{clan_id}")
@limiter.limit("20/minute")
async def ukloni_clana(
    request: Request,
    clan_id: str,
    user: dict = Depends(get_current_user),
):
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()
    firma = await asyncio.to_thread(_require_firma_admin, supa, uid)

    def _find():
        return (
            supa.table("kancelarija_clanovi")
            .select("id, email, status, user_id")
            .eq("id", clan_id)
            .eq("kancelarija_id", firma["id"])
            .maybe_single()
            .execute()
        )

    row = await asyncio.to_thread(_find)
    if not row.data:
        raise HTTPException(status_code=404, detail="Član nije pronađen u vašoj firmi.")
    if row.data.get("user_id") == uid:
        raise HTTPException(status_code=400, detail="Ne možete ukloniti sebe. Koristite 'Napusti firmu'.")
    if row.data.get("status") == "REMOVED":
        raise HTTPException(status_code=400, detail="Član je već uklonjen.")

    await SeatService.transition(
        kancelarija_id=firma["id"], clan_id=clan_id, clan_email=row.data["email"],
        actor_uid=uid, actor_email=email, action="remove",
        from_status=row.data["status"], to_status="REMOVED",
        extra_fields={"removed_reason": "removed_by_admin", "removed_at": _now(), "suspended_at": None},
    )
    logger.info("[KANCELARIJA] Uklonjen: %s iz firme %s", row.data.get("email"), firma["id"])
    return {"ok": True}


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
            .select("id, email, status")
            .eq("id", clan_id)
            .eq("kancelarija_id", firma["id"])
            .maybe_single()
            .execute()
        )
        if not row.data:
            raise HTTPException(status_code=404, detail="Član nije pronađen u vašoj firmi.")
        if row.data.get("status") == "REMOVED":
            raise HTTPException(status_code=400, detail="Ne može se menjati uloga uklonjenog člana.")
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

    firma_admin = await asyncio.to_thread(_get_firma_for_admin, supa, uid)
    if firma_admin:
        raise HTTPException(
            status_code=400,
            detail="Administrator ne može napustiti firmu. Prenesite vlasništvo ili obrišite firmu."
        )

    def _find():
        return (
            supa.table("kancelarija_clanovi")
            .select("id, kancelarija_id")
            .eq("user_id", uid)
            .eq("status", "ACTIVE")
            .maybe_single()
            .execute()
        )

    row = await asyncio.to_thread(_find)
    if not row.data:
        raise HTTPException(status_code=404, detail="Niste član nijedne firme.")

    await SeatService.transition(
        kancelarija_id=row.data["kancelarija_id"], clan_id=row.data["id"], clan_email=email,
        actor_uid=uid, actor_email=email, action="leave",
        from_status="ACTIVE", to_status="REMOVED",
        extra_fields={"removed_reason": "left_voluntarily", "removed_at": _now()},
    )
    logger.info("[KANCELARIJA] %s napustio kancelariju.", email)
    return {"ok": True}


@router.get("/api/kancelarija/predmeti")
@limiter.limit("60/minute")
async def firma_predmeti(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Kancelarija Faza 2 — vraća predmete svih aktivnih članova firme.
    Dostupno i adminu i memberima (uloga: partner/saradnik/citanje).
    """
    uid   = user["user_id"]
    email = (user.get("email") or "").lower()
    supa  = _get_supa()

    def _fetch():
        # Pronađi firmu (kao admin ili member)
        firma = _get_firma_for_admin(supa, uid)
        kancelarija_id = firma["id"] if firma else None

        if not kancelarija_id:
            member_row = _get_firma_for_member(supa, uid, email)
            if not member_row:
                return {"predmeti": [], "firma_naziv": None, "razlog": "nije_clan"}
            nested = member_row.get("kancelarije") or {}
            kancelarija_id = nested.get("id")
            firma_naziv    = nested.get("naziv", "")
        else:
            firma_naziv = firma.get("naziv", "")

        if not kancelarija_id:
            return {"predmeti": [], "firma_naziv": None}

        # Svi aktivni članovi
        clanovi_res = (
            supa.table("kancelarija_clanovi")
            .select("user_id, email, uloga")
            .eq("kancelarija_id", kancelarija_id)
            .eq("status", "ACTIVE")
            .execute()
        )
        clanovi = clanovi_res.data or []

        # Admin je uvek u listi (nema red u kancelarija_clanovi za admina)
        if firma:
            admin_u = {"user_id": uid, "email": email, "uloga": "admin"}
            if not any(c["user_id"] == uid for c in clanovi):
                clanovi.insert(0, admin_u)

        clan_uids = [c["user_id"] for c in clanovi if c.get("user_id")]
        if not clan_uids:
            return {"predmeti": [], "firma_naziv": firma_naziv}

        # Email mapa za prikaz vlasnika
        email_by_uid = {c["user_id"]: c["email"] for c in clanovi if c.get("user_id")}

        # Predmeti svih članova (max 200)
        pred_res = (
            supa.table("predmeti")
            .select("id, naziv, tip, status, created_at, user_id")
            .in_("user_id", clan_uids)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        predmeti = pred_res.data or []

        # Dodaj vlasnik info
        for p in predmeti:
            p["vlasnik_email"] = email_by_uid.get(p.get("user_id"), "—")
            p["je_moj"]        = (p.get("user_id") == uid)

        return {
            "predmeti":    predmeti,
            "firma_naziv": firma_naziv,
            "clan_count":  len(clanovi),
        }

    return await asyncio.to_thread(_fetch)
