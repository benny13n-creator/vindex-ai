# -*- coding: utf-8 -*-
"""
Vindex AI — routers/email_notif.py

Email podsetnici za kritične rokove (7, 3, 1 dan pre).
Koristi isti SMTP kao billing (EMAIL_SMTP_* env vars).

Endpoints:
  GET  /email-notif/profil         — dohvata podešavanja (opt-in, 7/3/1 dan)
  POST /email-notif/profil         — čuva/ažurira podešavanja
  DELETE /email-notif/profil       — deaktivira email notifikacije
  POST /email-notif/test           — šalje test email na login email
  POST /email-notif/send-reminders — interni cron trigger (founder only)
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.email_notif")
router = APIRouter(tags=["email_notif"])

_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
_SMTP_PASS = os.getenv("EMAIL_SMTP_PASS", "")
_FROM_ADDR = os.getenv("EMAIL_FROM", "") or _SMTP_USER


# ─── SMTP helper ──────────────────────────────────────────────────────────────

def _smtp_send(to_addr: str, subject: str, html: str) -> None:
    if not _SMTP_HOST:
        raise RuntimeError("EMAIL_SMTP_HOST nije konfigurisan.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _FROM_ADDR
    msg["To"]      = to_addr
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(_SMTP_USER, _SMTP_PASS)
        smtp.sendmail(_FROM_ADDR, [to_addr], msg.as_bytes())


def _email_html(rokovi: list[dict], dana_pre: int) -> str:
    if dana_pre == 1:
        naslov = "⚠️ Sutra ističe rok!"
        boja   = "#ef4444"
        opis   = "Sledeći kritični rokovi ističu <strong>SUTRA</strong>:"
    elif dana_pre == 3:
        naslov = "📅 Za 3 dana — kritični rokovi"
        boja   = "#f97316"
        opis   = "Sledeći kritični rokovi ističu za <strong>3 dana</strong>:"
    else:
        naslov = "📅 Za 7 dana — kritični rokovi"
        boja   = "#3b82f6"
        opis   = "Sledeći kritični rokovi ističu za <strong>7 dana</strong>:"

    rows_html = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#e2e8f0;">'
        f'{r.get("dogadjaj","Rok")}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#94a3b8;white-space:nowrap;">'
        f'{r.get("datum_iso","")}</td></tr>'
        for r in rokovi
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:{boja};padding:20px 28px;">
    <div style="font-size:20px;font-weight:700;color:#fff;">{naslov}</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:4px;">Vindex AI — Pravni Operativni Sistem</div>
  </div>
  <div style="padding:24px 28px;">
    <p style="color:#cbd5e1;font-size:14px;margin:0 0 16px;">{opis}</p>
    <table style="width:100%;border-collapse:collapse;background:#0d1b2a;border-radius:8px;overflow:hidden;">
      <thead>
        <tr style="background:#1e3a5f;">
          <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Rok / Dogadjaj</th>
          <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Datum</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div style="margin-top:20px;text-align:center;">
      <a href="https://vindex.rs" style="display:inline-block;padding:10px 24px;background:{boja};color:#fff;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;">Otvori Vindex AI →</a>
    </div>
  </div>
  <div style="padding:14px 28px;border-top:1px solid #1e293b;">
    <p style="color:#475569;font-size:12px;margin:0;">Prijavili ste se na email podsetnik za rokove u Vindex AI. Da odjavljujete, idite na Podešavanja → Email notifikacije.</p>
  </div>
</div>
</body></html>"""


# ─── Models ───────────────────────────────────────────────────────────────────

class EmailNotifReq(BaseModel):
    aktivan: bool = True
    dan_7:   bool = True
    dan_3:   bool = True
    dan_1:   bool = True


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/email-notif/profil")
@limiter.limit("60/minute")
async def get_profil(request: Request, user: dict = Depends(get_current_user)):
    """Dohvata email notif podešavanja korisnika."""
    supa = _get_supa()
    res = await asyncio.to_thread(
        lambda: supa.table("korisnik_email_notif")
                     .select("*")
                     .eq("user_id", user["user_id"])
                     .maybe_single()
                     .execute()
    )
    if not res.data:
        return {"aktivan": False, "dan_7": True, "dan_3": True, "dan_1": True, "email": user.get("email")}
    d = res.data
    return {**d, "email": user.get("email"), "smtp_ok": bool(_SMTP_HOST)}


@router.post("/email-notif/profil")
@limiter.limit("10/minute")
async def sacuvaj_profil(request: Request, req: EmailNotifReq, user: dict = Depends(get_current_user)):
    """Čuva email notif podešavanja (upsert)."""
    if not _SMTP_HOST:
        raise HTTPException(status_code=503, detail="Email server nije konfigurisan (EMAIL_SMTP_HOST).")
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("korisnik_email_notif").upsert({
            "user_id":    user["user_id"],
            "aktivan":    req.aktivan,
            "dan_7":      req.dan_7,
            "dan_3":      req.dan_3,
            "dan_1":      req.dan_1,
            "updated_at": date.today().isoformat(),
        }, on_conflict="user_id").execute()
    )
    return {"ok": True, "aktivan": req.aktivan}


@router.delete("/email-notif/profil")
@limiter.limit("10/minute")
async def obrisi_profil(request: Request, user: dict = Depends(get_current_user)):
    """Deaktivira email notif (brise red)."""
    supa = _get_supa()
    await asyncio.to_thread(
        lambda: supa.table("korisnik_email_notif").delete().eq("user_id", user["user_id"]).execute()
    )
    return {"ok": True}


@router.post("/email-notif/test")
@limiter.limit("3/minute")
async def test_email(request: Request, user: dict = Depends(get_current_user)):
    """Šalje test email na login adresu korisnika."""
    to_addr = user.get("email", "")
    if not to_addr:
        raise HTTPException(status_code=400, detail="Email adresa nije dostupna.")
    if not _SMTP_HOST:
        raise HTTPException(status_code=503, detail="Email server nije konfigurisan.")

    html = _email_html(
        [{"dogadjaj": "Test rok — Vindex AI", "datum_iso": date.today().isoformat()}],
        dana_pre=3,
    )
    try:
        await asyncio.to_thread(_smtp_send, to_addr, "Vindex AI — Test email notifikacija", html)
    except Exception as exc:
        logger.error("[EMAIL-NOTIF] test greška: %s", exc)
        raise HTTPException(status_code=502, detail=f"Greška pri slanju: {exc}")
    return {"ok": True, "poslato_na": to_addr}


@router.post("/email-notif/send-reminders")
@limiter.limit("5/minute")
async def posalji_podsetnike(request: Request, user: dict = Depends(get_current_user)):
    """
    Interni cron trigger — šalje email podsetnik za kritične rokove.
    Poziva se automatski (Railway cron) ili ručno (founder only).
    Šalje za 7, 3 i 1 dan (samo ako se već nije slao za taj rok+dana).
    """
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Restricted.")

    supa    = _get_supa()
    today   = date.today()
    targets = {1: today + timedelta(days=1),
               3: today + timedelta(days=3),
               7: today + timedelta(days=7)}

    def _run():
        profili_r = supa.table("korisnik_email_notif").select("*").eq("aktivan", True).execute()
        profili   = profili_r.data or []
        if not profili:
            return {"poslato": 0, "greske": 0, "napomena": "Nema aktivnih profila"}

        # Get user emails from Supabase auth via profiles (or use billing pattern)
        # We fetch user emails from profiles table which has email
        emails_r = supa.table("profiles").select("id, email").execute()
        email_map = {str(p["id"]): p.get("email", "") for p in (emails_r.data or [])}

        poslato = 0
        greske  = 0

        for profil in profili:
            uid        = profil["user_id"]
            to_addr    = email_map.get(uid, "")
            if not to_addr:
                continue

            for dana_pre, target_date in targets.items():
                col = f"dan_{dana_pre}"
                if not profil.get(col, False):
                    continue

                target_iso = target_date.isoformat()

                # Check if already sent
                dup = supa.table("email_notif_log").select("id").eq("user_id", uid).eq("datum_roka", target_iso).eq("dana_pre", dana_pre).limit(1).execute()
                if dup.data:
                    continue

                rokovi_r = (
                    supa.table("predmet_hronologija")
                    .select("dogadjaj, datum_iso, predmet_id")
                    .eq("user_id", uid)
                    .eq("vaznost", "kritičan")
                    .eq("datum_iso", target_iso)
                    .execute()
                )
                rokovi = rokovi_r.data or []
                if not rokovi:
                    continue

                subject = f"Vindex AI — {'Sutra ističe rok!' if dana_pre == 1 else f'Za {dana_pre} dana — kritični rokovi'}"
                html    = _email_html(rokovi, dana_pre)

                try:
                    _smtp_send(to_addr, subject, html)
                    # Log sent
                    for rok in rokovi:
                        try:
                            supa.table("email_notif_log").insert({
                                "user_id":   uid,
                                "predmet_id": rok.get("predmet_id", ""),
                                "datum_roka": target_iso,
                                "dana_pre":   dana_pre,
                            }).execute()
                        except Exception:
                            pass
                    poslato += 1
                    logger.info("[EMAIL-CRON] poslato uid=%.8s dana_pre=%d datum=%s", uid, dana_pre, target_iso)
                except Exception as exc:
                    logger.error("[EMAIL-CRON] greška uid=%.8s: %s", uid, exc)
                    greske += 1

        return {"poslato": poslato, "greske": greske}

    result = await asyncio.to_thread(_run)
    return result
