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
import html as _html
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user
from shared.rate import limiter

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
        # Unos sa javne forme ide u HTML poruku samo escapovan, a u zaglavlje
        # bez prelaza reda (ime može da sadrži `<script>` ili prelaz reda).
        e = {k: _html.escape(getattr(prijava, k) or "", quote=True)
             for k in ("ime", "email", "firma", "telefon", "poruka")}
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎉 Vindex AI: nova prijava od {' '.join(prijava.ime.split())}"
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
        <td style="padding:7px 0;font-weight:700;">{e['ime']}</td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Email</td>
        <td style="padding:7px 0;"><a href="mailto:{e['email']}" style="color:#0099bb;">{e['email']}</a></td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Firma</td>
        <td style="padding:7px 0;">{e['firma'] or '—'}</td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Telefon</td>
        <td style="padding:7px 0;">{e['telefon'] or '—'}</td></tr>
    <tr><td style="padding:7px 0;color:#666;vertical-align:top;">Poruka</td>
        <td style="padding:7px 0;color:#444;font-style:{'italic' if prijava.poruka else 'normal'};">{e['poruka'] or '—'}</td></tr>
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

        logger.info("Waitlist notifikacija predata SMTP serveru")
    except Exception as exc:
        logger.warning("Waitlist email nije uspeo: %s", exc)


# ── Endpointovi ──────────────────────────────────────────────────────────────

# Website V2 (P0-B): isti odgovor za novu i već evidentiranu adresu. Ranije su
# tri različite poruke otkrivale da li je proizvoljna adresa na listi i da li
# ima aktivan nalog. Sada odgovor ne zavisi od stanja adrese.
_NEUTRALAN_ODGOVOR = {"ok": True, "poruka": "Prijava je evidentirana."}


def _je_duplikat(exc: Exception) -> bool:
    """Jedinstveni indeks `lower(email)` (migracija 055) odbio je drugi upis."""
    return getattr(exc, "code", None) == "23505"


# Night Sprint V (G11): ključ po klijentu (`_get_real_ip`) čita krajnje levi
# X-Forwarded-For, koji klijent sam postavlja, pa ga promenljivo zaglavlje
# zaobilazi. Zato forma ima i UKUPNU granicu koja ne zavisi od zaglavlja:
# najviše 20 prijava na sat i 100 na dan za sve klijente zajedno (Redis kada
# postoji, inače po procesu). Prekoračenje = 429; sajt tada kaže da prijava nije
# potvrđena. Lažni upisi su ograničeni brojem, a ne samo poštenjem klijenta.
_GLOBALNI_KLJUC = "waitlist-prijava-svi-klijenti"


@router.post("/prijava")
@limiter.limit("10/hour")
@limiter.limit("20/hour;100/day", key_func=lambda request: _GLOBALNI_KLJUC)
async def waitlist_prijava(request: Request, body: WaitlistPrijava):
    """
    Javni endpoint — bez autentifikacije.
    Hvata prijave sa landing stranice i šalje notifikaciju osnivaču.
    Ograničenje učestalosti: 10/h po klijentu + 20/h i 100/dan ukupno (vidi iznad).
    """
    email_clean = str(body.email).strip().lower()
    supa = _get_supa()

    # Duplikat check — `eq`, ne `ilike`: u `ilike` su `_` i `%` džokeri, pa je
    # `a_b@` pogađao tuđi `axb@`. Upis uvek čuva `email_clean`, pa je `eq` tačan.
    existing = await _db(lambda: supa.table("waitlist")
                         .select("id")
                         .eq("email", email_clean)
                         .execute())
    if existing.data:
        return dict(_NEUTRALAN_ODGOVOR)

    try:
        await _db(lambda: supa.table("waitlist").insert({
            "ime":        body.ime,
            "email":      email_clean,
            "firma":      body.firma,
            "telefon":    body.telefon,
            "poruka":     body.poruka,
            "status":     "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute())
    except Exception as exc:
        # Istovremena prijava iste adrese: drugi upis odbija jedinstveni indeks.
        # Zapis postoji, pa je odgovor isti; obaveštenje je već poslao prvi.
        if _je_duplikat(exc):
            return dict(_NEUTRALAN_ODGOVOR)
        raise

    # Ne blokira odgovor — email ide u pozadini
    asyncio.create_task(asyncio.to_thread(_send_notification, body))

    logger.info("Nova waitlist prijava")
    return dict(_NEUTRALAN_ODGOVOR)


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
