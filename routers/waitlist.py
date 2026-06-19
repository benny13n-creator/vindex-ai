from __future__ import annotations
"""
Vindex AI — Waitlist / Early Access router

Javni endpoint: POST /waitlist/prijava
  - bez autentifikacije
  - čuva prijavu u Supabase `waitlist` tabeli
  - šalje email notifikaciju osnivaču

Admin endpoint: GET /waitlist/admin/lista
  - samo osnivač (FOUNDER_EMAILS)
  - vraća sve prijave sortirane po datumu

Supabase SQL (pokreni jednom u Supabase SQL editoru):
-------------------------------------------------------
CREATE TABLE IF NOT EXISTS waitlist (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ime         text NOT NULL,
  email       text NOT NULL,
  firma       text DEFAULT '',
  telefon     text DEFAULT '',
  poruka      text DEFAULT '',
  status      text DEFAULT 'pending',   -- pending | contacted | active
  created_at  timestamptz DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS waitlist_email_idx ON waitlist (lower(email));
ALTER TABLE waitlist ENABLE ROW LEVEL SECURITY;
-- Samo service role može čitati/pisati (API koristi service key)
CREATE POLICY "service_only" ON waitlist USING (false);
-------------------------------------------------------
"""
import asyncio
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user

logger = logging.getLogger("vindex.waitlist")
router = APIRouter(prefix="/waitlist", tags=["waitlist"])

# ── SMTP konfiguracija (iste env varijable kao billing) ──────────────────────
_SMTP_HOST  = os.getenv("EMAIL_SMTP_HOST", "")
_SMTP_PORT  = int(os.getenv("EMAIL_SMTP_PORT", "587"))
_SMTP_USER  = os.getenv("EMAIL_SMTP_USER", "")
_SMTP_PASS  = os.getenv("EMAIL_SMTP_PASS", "")
_EMAIL_FROM = os.getenv("EMAIL_FROM", "")
_NOTIFY_TO  = os.getenv("WAITLIST_NOTIFY_EMAIL",
              os.getenv("EMAIL_FROM", next(iter(FOUNDER_EMAILS), "")))


# ── Modeli ───────────────────────────────────────────────────────────────────

class WaitlistPrijava(BaseModel):
    ime:     str
    email:   EmailStr
    firma:   str = ""
    telefon: str = ""
    poruka:  str = ""

    @field_validator("ime")
    @classmethod
    def ime_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Ime je obavezno.")
        if len(v) > 120:
            raise ValueError("Ime je predugačko.")
        return v

    @field_validator("firma", "telefon", "poruka", mode="before")
    @classmethod
    def trim_optional(cls, v: str) -> str:
        return (v or "").strip()[:500]


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _db(fn):
    return await asyncio.to_thread(fn)


def _send_notification(prijava: WaitlistPrijava) -> None:
    """Šalje email notifikaciju osnivaču. Greška ne blokira odgovor korisniku."""
    if not all([_SMTP_HOST, _SMTP_USER, _SMTP_PASS, _NOTIFY_TO]):
        logger.warning("SMTP nije konfigurisan — waitlist email preskočen")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎉 Vindex AI: nova prijava od {prijava.ime}"
        msg["From"]    = _EMAIL_FROM or _SMTP_USER
        msg["To"]      = _NOTIFY_TO

        plain = (
            f"Nova prijava za Vindex AI čekajuću listu:\n\n"
            f"Ime:     {prijava.ime}\n"
            f"Email:   {prijava.email}\n"
            f"Firma:   {prijava.firma or '—'}\n"
            f"Telefon: {prijava.telefon or '—'}\n"
            f"Poruka:  {prijava.poruka or '—'}\n\n"
            f"Vreme: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        )
        html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;background:#f0f4f8;margin:0;padding:24px;">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;border:1px solid #e0e7ef;">
  <h2 style="margin:0 0 20px;color:#0099bb;font-size:20px;">🎉 Nova prijava — Vindex AI</h2>
  <table style="width:100%;border-collapse:collapse;font-size:14px;">
    <tr><td style="padding:7px 0;color:#666;width:80px;vertical-align:top;">Ime</td>
        <td style="padding:7px 0;font-weight:700;">{prijava.ime}</td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Email</td>
        <td style="padding:7px 0;"><a href="mailto:{prijava.email}" style="color:#0099bb;">{prijava.email}</a></td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Firma</td>
        <td style="padding:7px 0;">{prijava.firma or '—'}</td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Telefon</td>
        <td style="padding:7px 0;">{prijava.telefon or '—'}</td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Poruka</td>
        <td style="padding:7px 0;color:#444;font-style:{'italic' if prijava.poruka else 'normal'};">{prijava.poruka or '—'}</td></tr>
  </table>
  <p style="margin:20px 0 0;font-size:12px;color:#aaa;">{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
</div></body></html>"""

        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html,  "html",  "utf-8"))

        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=12) as s:
            s.ehlo()
            s.starttls()
            s.login(_SMTP_USER, _SMTP_PASS)
            s.sendmail(msg["From"], [_NOTIFY_TO], msg.as_string())

        logger.info("Waitlist notifikacija poslata za %s", prijava.email)
    except Exception as exc:
        logger.warning("Waitlist email nije uspeo: %s", exc)


# ── Endpointovi ──────────────────────────────────────────────────────────────

@router.post("/prijava")
async def waitlist_prijava(body: WaitlistPrijava):
    """
    Javni endpoint — bez autentifikacije.
    Hvata prijave sa landing stranice i šalje notifikaciju osnivaču.
    """
    email_clean = str(body.email).strip().lower()
    supa = _get_supa()

    # Duplikat check
    existing = await _db(lambda: supa.table("waitlist")
                         .select("id, status")
                         .ilike("email", email_clean)
                         .execute())
    if existing.data:
        st = existing.data[0].get("status", "pending")
        if st == "active":
            return {"ok": True, "poruka": "Vaš nalog je već aktivan. Prijavite se!"}
        return {"ok": True, "poruka": "Već ste na listi! Javićemo vam se uskoro."}

    await _db(lambda: supa.table("waitlist").insert({
        "ime":        body.ime,
        "email":      email_clean,
        "firma":      body.firma,
        "telefon":    body.telefon,
        "poruka":     body.poruka,
        "status":     "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute())

    # Ne blokira odgovor — email ide u pozadini
    asyncio.create_task(asyncio.to_thread(_send_notification, body))

    logger.info("Nova waitlist prijava: %s <%s>", body.ime, email_clean)
    return {
        "ok": True,
        "poruka": "Prijava primljena! Javićemo vam se čim otvorimo pristup.",
    }


@router.get("/admin/lista")
async def waitlist_admin_lista(user: dict = Depends(get_current_user)):
    """Samo osnivač — pregled svih prijava."""
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Samo osnivač.")
    supa = _get_supa()
    res = await _db(lambda: supa.table("waitlist")
                    .select("*")
                    .order("created_at", desc=True)
                    .execute())
    pending  = [r for r in res.data if r.get("status") == "pending"]
    active   = [r for r in res.data if r.get("status") == "active"]
    return {
        "total":    len(res.data),
        "pending":  len(pending),
        "active":   len(active),
        "prijave":  res.data,
    }


@router.patch("/admin/{waitlist_id}/status")
async def waitlist_update_status(
    waitlist_id: str,
    status: str,
    user: dict = Depends(get_current_user),
):
    """Osnivač može promeniti status prijave: pending → contacted → active."""
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Samo osnivač.")
    if status not in ("pending", "contacted", "active"):
        raise HTTPException(status_code=400, detail="Status mora biti: pending, contacted, active.")
    supa = _get_supa()
    await _db(lambda: supa.table("waitlist")
              .update({"status": status})
              .eq("id", waitlist_id)
              .execute())
    return {"ok": True}
