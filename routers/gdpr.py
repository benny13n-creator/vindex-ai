# -*- coding: utf-8 -*-
"""
Vindex AI — routers/gdpr.py

GDPR / ZZPL usklađenost:
  GET  /gdpr/unsubscribe          — javni link iz emailova (bez auth), odjava
  GET  /api/gdpr/export           — export svih korisnikovih podataka (auth)
  DELETE /api/gdpr/account        — brisanje/anonimizacija naloga (auth)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac as _hmac
import logging
import os
import urllib.parse
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.permissions import effective_tier
from shared.rate import limiter

logger = logging.getLogger("vindex.gdpr")
router = APIRouter(tags=["gdpr"])

_APP_URL  = "https://vindex.rs"
_SECRET   = (os.getenv("UNSUBSCRIBE_SECRET") or os.getenv("SUPABASE_JWT_SECRET", "vindex-unsub-key")).encode()


# ─── Token helpers ────────────────────────────────────────────────────────────

def make_unsub_token(user_id: str, email: str) -> str:
    """HMAC-SHA256 token za one-click unsubscribe link."""
    msg = f"{user_id}:{email}".encode()
    sig = _hmac.new(_SECRET, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def make_unsub_url(user_id: str, email: str) -> str:
    em_enc = urllib.parse.quote(email, safe="")
    token  = make_unsub_token(user_id, email)
    return f"{_APP_URL}/gdpr/unsubscribe?uid={user_id}&em={em_enc}&t={token}"


def _verify_unsub_token(token: str, user_id: str, email: str) -> bool:
    expected = make_unsub_token(user_id, email)
    try:
        return _hmac.compare_digest(
            token.encode(),
            expected.encode(),
        )
    except Exception:
        return False


# ─── HTML helper ──────────────────────────────────────────────────────────────

def _page(title: str, body: str, color: str = "#4aa8ff") -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{title} — Vindex AI</title></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;">
<div style="max-width:480px;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;padding:36px;text-align:center;">
  <div style="font-size:40px;margin-bottom:16px;">{"✓" if color=="#4aa8ff" else "⚠"}</div>
  <h2 style="color:{color};margin:0 0 12px;font-size:20px;">{title}</h2>
  <p style="color:#94a3b8;font-size:14px;line-height:1.6;margin:0 0 24px;">{body}</p>
  <a href="{_APP_URL}" style="display:inline-block;padding:10px 24px;background:{color};color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">Vindex AI →</a>
</div>
</body></html>"""


# ─── 1. One-click unsubscribe ─────────────────────────────────────────────────

@router.get("/gdpr/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
async def unsubscribe(
    uid: str = Query(...),
    em:  str = Query(...),
    t:   str = Query(...),
):
    """
    Javni endpoint — ne zahteva auth.
    Link format: /gdpr/unsubscribe?uid=...&em=URL-encoded-email&t=HMAC
    """
    email = urllib.parse.unquote(em)

    if not _verify_unsub_token(t, uid, email):
        return HTMLResponse(
            _page("Neispravan link", "Link za odjavu nije validan ili je istekao.", color="#ef4444"),
            status_code=400,
        )

    try:
        supa = _get_supa()
        await asyncio.to_thread(
            lambda: supa.table("korisnik_email_notif").upsert(
                {"user_id": uid, "aktivan": False},
                on_conflict="user_id",
            ).execute()
        )
        logger.info("[GDPR] unsubscribe uid=%.8s email=%s", uid, email[:4] + "***")
    except Exception as exc:
        logger.error("[GDPR] unsubscribe greška uid=%.8s: %s", uid, exc)
        return HTMLResponse(
            _page("Greška", "Odjava nije uspela. Pokušajte ponovo ili nas kontaktirajte.", color="#ef4444"),
            status_code=500,
        )

    return HTMLResponse(
        _page(
            "Uspešno ste odjavljeni",
            "Više nećete dobijati email podsetnike od Vindex AI. "
            "Email notifikacije možete ponovo aktivirati u Podešavanjima.",
        )
    )


# ─── 2. Data export (GDPR čl. 20 / ZZPL čl. 24) ──────────────────────────────

@router.get("/api/gdpr/export")
@limiter.limit("5/minute")
async def gdpr_export(request: Request, user: dict = Depends(get_current_user)):
    """Vraća sve podatke korisnika u JSON formatu (pravo na prenosivost)."""
    uid  = user["user_id"]
    supa = _get_supa()

    def _fetch():
        profile_r = (
            supa.table("profiles")
            .select("id,email,full_name,created_at,subscription_type,addons,subscription_expires_at,subscription_seats_extra")
            .eq("id", uid).maybe_single().execute()
        )
        profil = profile_r.data or {}
        # Stvarna pretplata — ISKLJUČIVO iz profiles.subscription_type (Faza 72.5:
        # korisnik_plan je obrisan izvor, nikad ažuriran otkad je UsageService
        # preuzeo kredit-tracking, GDPR izvoz ne sme prikazati zastarelu tarifu).
        plan = {
            "tarifa":                    effective_tier(profil),
            "addons":                    profil.get("addons") or [],
            "subscription_expires_at":   profil.get("subscription_expires_at"),
            "subscription_seats_extra":  profil.get("subscription_seats_extra", 0),
        }
        predm_r   = supa.table("predmeti").select("id,naziv,status,tip_spora,created_at").eq("user_id", uid).execute()
        billing_r = supa.table("billing_entries").select("datum,opis,iznos_rsd,obracunato").eq("user_id", uid).order("datum").execute()
        email_r   = supa.table("korisnik_email_notif").select("aktivan,dan_7,dan_3,dan_1,nedeljni").eq("user_id", uid).maybe_single().execute()
        usage_r   = supa.table("usage_events").select("feature,created_at").eq("user_id", uid).order("created_at", desc=True).limit(200).execute()

        return {
            "export_datum":   datetime.now(timezone.utc).isoformat(),
            "napomena":       "Određena polja (JMBG, pasoš, PIB) čuvaju se enkriptovana i nisu uključena u ovaj izvoz zbog bezbednosti.",
            "profil":         {k: v for k, v in profil.items() if k in ("id", "email", "full_name", "created_at")},
            "plan":           plan,
            "predmeti":       predm_r.data or [],
            "billing_stavke": billing_r.data or [],
            "email_podesavanja": email_r.data or {},
            "poslednje_aktivnosti": usage_r.data or [],
        }

    data = await asyncio.to_thread(_fetch)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": "attachment; filename=vindex-gdpr-export.json"},
    )


# ─── 3. Account deletion (GDPR čl. 17 / ZZPL čl. 26 — pravo na zaborav) ─────

@router.delete("/api/gdpr/account")
@limiter.limit("3/minute")
async def gdpr_delete_account(request: Request, user: dict = Depends(get_current_user)):
    """
    Anonimizuje nalog korisnika (soft delete):
    - Zamenjuje email i ime u profiles tabeli
    - Deaktivira sve email notifikacije
    - Upisuje u audit_log
    """
    uid   = user["user_id"]
    email = user.get("email", "")
    supa  = _get_supa()

    if email.lower() in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Founder nalog se ne može obrisati putem API-ja.")

    anon_email = f"deleted_{uid[:8]}@deleted.vindex.rs"

    def _delete():
        supa.table("profiles").update({
            "email":     anon_email,
            "full_name": "Obrisani korisnik",
        }).eq("id", uid).execute()

        supa.table("korisnik_email_notif").upsert(
            {"user_id": uid, "aktivan": False},
            on_conflict="user_id",
        ).execute()

        try:
            from app.services import audit_log as _al
            _al.log(uid, "gdpr_account_deleted", {
                "original_email_hash": hashlib.sha256(email.encode()).hexdigest()[:16],
            })
        except Exception:
            pass

    await asyncio.to_thread(_delete)
    logger.info("[GDPR] account deleted uid=%.8s", uid)

    # Zabeleži brisanje u nepromenjivi audit log — ne može biti obrisano
    from shared.audit_immutable import log_action as _imm_log
    ip = request.client.host if request.client else None
    asyncio.create_task(_imm_log(
        "gdpr_erasure",
        user_id=uid,
        resource_type="account",
        ip=ip,
        metadata={"email_hash": hashlib.sha256(email.encode()).hexdigest()[:16]},
    ))

    return {
        "ok": True,
        "poruka": "Vaš nalog je anonimizovan. Lični podaci su obrisani iz profila.",
        "napomena": "Predmeti i dokumenti ostaju u sistemu u anonimizovanom obliku zbog zakonskih obaveza čuvanja."
    }
