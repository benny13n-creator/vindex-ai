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
    aktivan:  bool = True
    dan_7:    bool = True
    dan_3:    bool = True
    dan_1:    bool = True
    nedeljni: bool = True


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
            "nedeljni":   req.nedeljni,
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


# ─── Weekly Digest ────────────────────────────────────────────────────────────

def _weekly_digest_html(
    user_name: str,
    rokovi: list[dict],
    rocista: list[dict],
    aktivnih: int,
    neplaceno_rsd: float,
    hitnih: int,
) -> str:
    """Generiše HTML za nedeljni sažetak email (ponedjeljak ujutru)."""
    from datetime import date as _date
    today = _date.today()
    nedelja_kraj = today + timedelta(days=6)
    period_lbl = f"{today.day}. — {nedelja_kraj.day}. {['jan','feb','mar','apr','maj','jun','jul','avg','sep','okt','nov','dec'][nedelja_kraj.month-1]}."

    def _rok_row(r: dict) -> str:
        tip = "🏛 Ročište" if r.get("tip") == "rociste" else "📅 Rok"
        boja = "#ef4444" if r.get("vaznost") == "kritičan" else "#f97316"
        return (
            f'<tr><td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#e2e8f0;">'
            f'{tip} — {r.get("dogadjaj", r.get("sud", "Dogadjaj"))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:{boja};white-space:nowrap;font-weight:600;">'
            f'{r.get("datum_iso", r.get("datum", ""))}</td></tr>'
        )

    all_items = [{"tip": "rokovi", **r} for r in (rokovi or [])] + [{"tip": "rociste", **r} for r in (rocista or [])]
    all_items.sort(key=lambda x: x.get("datum_iso", x.get("datum", "")))

    rows_html = "".join(_rok_row(r) for r in all_items[:10])
    if not rows_html:
        rows_html = '<tr><td colspan="2" style="padding:12px;text-align:center;color:#475569;">Nema zakazanih rokova ili ročišta za ovu nedelju.</td></tr>'

    hitni_html = ""
    if hitnih > 0:
        hitni_html = (
            f'<div style="margin:16px 0;padding:12px 16px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;">'
            f'<span style="color:#f87171;font-weight:700;">⚠ {hitnih} hitan{"a" if hitnih > 1 else ""} predmet{"a" if hitnih > 1 else ""}!</span>'
            f'<span style="color:#94a3b8;font-size:13px;"> Proverite Komandni Centar.</span>'
            f'</div>'
        )

    neplaceno_str = f"{int(neplaceno_rsd):,}".replace(",", ".") if neplaceno_rsd else "0"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#1e3a5f,#0d2744);padding:24px 28px;">
    <div style="font-size:13px;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Vindex AI — Nedeljni sažetak</div>
    <div style="font-size:22px;font-weight:700;color:#fff;">Dobro jutro, {user_name}! 👋</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.6);margin-top:4px;">Ovo je vaš plan za {period_lbl}</div>
  </div>
  <div style="padding:24px 28px;">
    <!-- KPI row -->
    <div style="display:flex;gap:12px;margin-bottom:20px;">
      <div style="flex:1;background:#0d1b2a;border:1px solid #1e3a5f;border-radius:8px;padding:12px;text-align:center;">
        <div style="font-size:22px;font-weight:700;color:#4aa8ff;">{aktivnih}</div>
        <div style="font-size:11px;color:#64748b;margin-top:2px;">aktivnih predmeta</div>
      </div>
      <div style="flex:1;background:#0d1b2a;border:1px solid #1e3a5f;border-radius:8px;padding:12px;text-align:center;">
        <div style="font-size:22px;font-weight:700;color:#fbbf24;">{len(all_items)}</div>
        <div style="font-size:11px;color:#64748b;margin-top:2px;">obaveza ove nedelje</div>
      </div>
      <div style="flex:1;background:#0d1b2a;border:1px solid #1e3a5f;border-radius:8px;padding:12px;text-align:center;">
        <div style="font-size:22px;font-weight:700;color:{"#f87171" if neplaceno_rsd > 0 else "#4ade80"};">{neplaceno_str}</div>
        <div style="font-size:11px;color:#64748b;margin-top:2px;">nenaplaćeno RSD</div>
      </div>
    </div>
    {hitni_html}
    <!-- Schedule -->
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;font-weight:600;">Plan za ovu nedelju</div>
    <table style="width:100%;border-collapse:collapse;background:#0d1b2a;border-radius:8px;overflow:hidden;margin-bottom:20px;">
      <thead>
        <tr style="background:#1e3a5f;">
          <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Obaveza</th>
          <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;">Datum</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div style="text-align:center;">
      <a href="https://vindex.rs" style="display:inline-block;padding:11px 28px;background:#4aa8ff;color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">Otvori Vindex AI →</a>
    </div>
  </div>
  <div style="padding:14px 28px;border-top:1px solid #1e293b;">
    <p style="color:#475569;font-size:12px;margin:0;">Nedeljni sažetak stižena svaki ponedeljak. Isključite u Podešavanja → Email notifikacije.</p>
  </div>
</div>
</body></html>"""


@router.post("/email-notif/nedeljni-sazetak")
@limiter.limit("5/minute")
async def posalji_nedeljni_sazetak(request: Request, user: dict = Depends(get_current_user)):
    """
    Cron trigger (ponedjeljak 07:00) — šalje nedeljni sažetak svim korisnicima
    koji imaju aktivan email notif profil sa nedeljni=True.
    Dostupno samo founderu.
    """
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Restricted.")

    supa  = _get_supa()
    today = date.today()
    in_7  = (today + timedelta(days=7)).isoformat()

    def _run():
        profili_r = (supa.table("korisnik_email_notif")
                        .select("*")
                        .eq("aktivan", True)
                        .eq("nedeljni", True)
                        .execute())
        profili = profili_r.data or []
        if not profili:
            return {"poslato": 0, "greske": 0, "napomena": "Nema korisnika sa aktivnim nedeljnim sažetkom"}

        emails_r  = supa.table("profiles").select("id,email,full_name").execute()
        predm_r   = supa.table("predmeti").select("id,user_id,naziv,status").eq("status", "aktivan").execute()
        email_map = {str(p["id"]): p for p in (emails_r.data or [])}

        aktivan_by_uid: dict[str, int] = {}
        for p in (predm_r.data or []):
            aktivan_by_uid[p["user_id"]] = aktivan_by_uid.get(p["user_id"], 0) + 1

        poslato = greske = 0
        today_iso = today.isoformat()

        for profil in profili:
            uid     = profil["user_id"]
            profil_data = email_map.get(uid, {})
            to_addr = profil_data.get("email", "")
            if not to_addr:
                continue

            # Prevent duplicate (already sent this week)
            dup = (supa.table("email_notif_log")
                       .select("id")
                       .eq("user_id", uid)
                       .eq("datum_roka", today_iso)
                       .eq("dana_pre", 0)
                       .limit(1)
                       .execute())
            if dup.data:
                continue

            # Fetch this user's deadlines for the next 7 days
            rokovi_r  = (supa.table("predmet_hronologija")
                             .select("dogadjaj,datum_iso,vaznost")
                             .eq("user_id", uid)
                             .gte("datum_iso", today_iso)
                             .lte("datum_iso", in_7)
                             .order("datum_iso")
                             .limit(20)
                             .execute())
            rocista_r = (supa.table("rocista")
                             .select("sud,datum,vreme,status")
                             .eq("user_id", uid)
                             .gte("datum", today_iso)
                             .lte("datum", in_7)
                             .order("datum")
                             .limit(10)
                             .execute())
            billing_r = (supa.table("billing_entries")
                             .select("iznos_rsd")
                             .eq("user_id", uid)
                             .eq("obracunato", False)
                             .execute())
            hitnih_r  = (supa.table("predmet_hronologija")
                             .select("predmet_id")
                             .eq("user_id", uid)
                             .eq("vaznost", "kritičan")
                             .gte("datum_iso", today_iso)
                             .lte("datum_iso", in_7)
                             .execute())

            rokovi     = rokovi_r.data or []
            rocista    = [{"datum_iso": r.get("datum", ""), "dogadjaj": r.get("sud", "Sud"), "tip": "rociste"} for r in (rocista_r.data or [])]
            neplaceno  = sum(float(r.get("iznos_rsd", 0) or 0) for r in (billing_r.data or []))
            hitnih     = len(set(r.get("predmet_id") for r in (hitnih_r.data or [])))
            aktivnih   = aktivan_by_uid.get(uid, 0)
            user_name  = (profil_data.get("full_name") or to_addr.split("@")[0] or "").title()

            html    = _weekly_digest_html(user_name, rokovi, rocista, aktivnih, neplaceno, hitnih)
            subject = f"📅 Vindex AI — Vaš plan za nedelju ({today.strftime('%d.%m.')})"

            try:
                _smtp_send(to_addr, subject, html)
                supa.table("email_notif_log").insert({
                    "user_id":    uid,
                    "predmet_id": None,
                    "datum_roka": today_iso,
                    "dana_pre":   0,
                }).execute()
                poslato += 1
                logger.info("[WEEKLY-DIGEST] poslato uid=%.8s", uid)
            except Exception as exc:
                logger.error("[WEEKLY-DIGEST] greška uid=%.8s: %s", uid, exc)
                greske += 1

        return {"poslato": poslato, "greske": greske}

    return await asyncio.to_thread(_run)
