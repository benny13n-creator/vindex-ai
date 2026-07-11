# -*- coding: utf-8 -*-
"""
Vindex AI — routers/support.py

POST /api/support/poruka — korisnik šalje poruku timu podrške.
Poruka stiže emailom na FOUNDER_EMAILS i upisuje se u Supabase
tabelu support_tickets (ako postoji).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.support")
router = APIRouter(tags=["support"])

_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
_SMTP_PASS = os.getenv("EMAIL_SMTP_PASS", "")
_FROM_ADDR = os.getenv("EMAIL_FROM", "") or _SMTP_USER

_MAX_SCREENSHOT_B64_CHARS = 4_000_000  # ~3MB slika posle base64 overhead-a

_KATEGORIJE = {
    "tehnicko":  "Tehnički problem",
    "nalog":     "Nalog i pretplata",
    "ai":        "AI / tačnost odgovora",
    "podatak":   "Podatak ili odluka",
    "predlog":   "Predlog / ideja",
    "feedback":  "Iskustvo / ocena",
    "ostalo":    "Ostalo",
}


class SupportPoruka(BaseModel):
    kategorija: str = "ostalo"
    poruka: str
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    kontekst: Optional[str] = Field(default=None, max_length=100)
    screenshot_base64: Optional[str] = None

    @field_validator("poruka")
    @classmethod
    def _poruka_val(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Poruka mora imati najmanje 10 karaktera.")
        if len(v) > 3000:
            raise ValueError("Poruka ne sme biti duža od 3000 karaktera.")
        return v

    @field_validator("kategorija")
    @classmethod
    def _kat_val(cls, v: str) -> str:
        if v not in _KATEGORIJE:
            return "ostalo"
        return v

    @field_validator("screenshot_base64")
    @classmethod
    def _screenshot_val(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > _MAX_SCREENSHOT_B64_CHARS:
            raise ValueError("Screenshot je prevelik.")
        return v


def _send_support_email(user_email: str, kategorija: str, poruka: str,
                         rating: Optional[int] = None, kontekst: Optional[str] = None,
                         screenshot_base64: Optional[str] = None) -> None:
    if not _SMTP_HOST:
        logger.warning("SMTP nije konfigurisan — support email nije poslat")
        return

    kat_label = _KATEGORIJE.get(kategorija, "Ostalo")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rating_row = ""
    if rating:
        rating_row = f"""<tr>
        <td style="padding:8px 0;color:#64748b;font-size:12px;vertical-align:top;">OCENA</td>
        <td style="padding:8px 0;font-size:13px;">{'⭐' * rating}{'☆' * (5 - rating)} ({rating}/5)</td>
      </tr>"""
    kontekst_row = ""
    if kontekst:
        kontekst_row = f"""<tr>
        <td style="padding:8px 0;color:#64748b;font-size:12px;vertical-align:top;">STRANICA</td>
        <td style="padding:8px 0;color:#e2e8f0;font-size:13px;">{kontekst}</td>
      </tr>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:600px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:#1e3a5f;padding:20px 28px;border-bottom:1px solid #2a4a7f;">
    <div style="font-size:18px;font-weight:700;color:#fff;">🎫 Nova poruka podrške — Vindex AI</div>
    <div style="font-size:12px;color:rgba(255,255,255,0.55);margin-top:4px;">{ts}</div>
  </div>
  <div style="padding:24px 28px;">
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="padding:8px 0;color:#64748b;font-size:12px;width:110px;vertical-align:top;">OD</td>
        <td style="padding:8px 0;color:#e2e8f0;font-size:13px;">{user_email}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#64748b;font-size:12px;vertical-align:top;">KATEGORIJA</td>
        <td style="padding:8px 0;font-size:13px;">
          <span style="background:rgba(0,212,255,0.12);color:#00d4ff;border:1px solid rgba(0,212,255,0.25);border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600;">{kat_label}</span>
        </td>
      </tr>
      {rating_row}
      {kontekst_row}
      <tr>
        <td style="padding:8px 0;color:#64748b;font-size:12px;vertical-align:top;">PORUKA</td>
        <td style="padding:8px 0;color:#e2e8f0;font-size:13px;line-height:1.6;white-space:pre-wrap;">{poruka}</td>
      </tr>
    </table>
  </div>
  <div style="padding:16px 28px;border-top:1px solid #1e293b;font-size:11px;color:#475569;">
    Vindex AI — Sistem za podršku &middot; Odgovori direktno na ovaj email ili kontaktiraj korisnika na {user_email}
  </div>
</div>
</body></html>"""

    for to_addr in FOUNDER_EMAILS:
        try:
            msg = MIMEMultipart("mixed")
            msg["Subject"] = f"[Vindex podrška] {kat_label} — od {user_email}"
            msg["From"]    = _FROM_ADDR
            msg["To"]      = to_addr
            msg["Reply-To"] = user_email
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(html, "html", "utf-8"))
            msg.attach(alt)
            if screenshot_base64:
                try:
                    img_data = base64.b64decode(screenshot_base64.split(",")[-1])
                    img = MIMEImage(img_data)
                    img.add_header("Content-Disposition", "attachment", filename="screenshot.png")
                    msg.attach(img)
                except Exception as e:
                    logger.warning("Screenshot dekodiranje greška: %s", e)
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(_SMTP_USER, _SMTP_PASS)
                smtp.sendmail(_FROM_ADDR, [to_addr], msg.as_bytes())
        except Exception as e:
            logger.error("Support email greška ka %s: %s", to_addr, e)


async def _save_ticket(supa, user_id: str, user_email: str, kategorija: str, poruka: str,
                        rating: Optional[int] = None, kontekst: Optional[str] = None) -> None:
    try:
        await asyncio.to_thread(
            lambda: supa.table("support_tickets").insert({
                "user_id":    user_id,
                "email":      user_email,
                "kategorija": kategorija,
                "poruka":     poruka,
                "rating":     rating,
                "kontekst":   kontekst,
            }).execute()
        )
    except Exception as e:
        logger.debug("support_tickets tabela možda ne postoji: %s", e)


@router.post("/api/support/poruka")
@limiter.limit("5/hour")
async def support_poruka(
    request: Request,
    payload: SupportPoruka,
    user: dict = Depends(get_current_user),
):
    user_id    = user["user_id"]
    user_email = user.get("email", "")

    supa = _get_supa()

    await asyncio.to_thread(
        _send_support_email, user_email, payload.kategorija, payload.poruka,
        payload.rating, payload.kontekst, payload.screenshot_base64,
    )
    await _save_ticket(supa, user_id, user_email, payload.kategorija, payload.poruka,
                        payload.rating, payload.kontekst)

    logger.info("Support poruka primljena od %s [%s]", user_email, payload.kategorija)
    return {"ok": True, "message": "Poruka je poslata. Odgovorićemo u roku od 24h."}
