# -*- coding: utf-8 -*-
"""
Vindex AI — routers/morning_briefing.py

Daily Morning Briefing: personalizovani AI jutarnji izveštaj za svakog advokata.
Šalje se automatski u 8:00 ili na zahtev.

Endpoints:
  GET  /api/briefing/daily          — generiši briefing za trenutnog korisnika (on-demand)
  POST /api/briefing/cron           — admin endpoint, šalje svim korisnicima (poziva cron)
  POST /api/briefing/send-email     — pošalji briefing emailom
  GET  /api/briefing/history        — prethodnih 7 dana briefinga
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.morning_briefing")
router = APIRouter(tags=["morning-briefing"])

_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
_SMTP_PASS = os.getenv("EMAIL_SMTP_PASS", "")
_FROM_ADDR = os.getenv("EMAIL_FROM", "") or _SMTP_USER

_MESECI_SR = {
    "January": "januara", "February": "februara", "March": "marta",
    "April": "aprila", "May": "maja", "June": "juna",
    "July": "jula", "August": "avgusta", "September": "septembra",
    "October": "oktobra", "November": "novembra", "December": "decembra",
}
_DANI_SR = {
    "Monday": "Ponedeljak", "Tuesday": "Utorak", "Wednesday": "Sreda",
    "Thursday": "Četvrtak", "Friday": "Petak", "Saturday": "Subota", "Sunday": "Nedelja",
}


def _danas_sr(d: date) -> str:
    s = d.strftime("%A, %d. %B %Y.")
    for en, sr in {**_DANI_SR, **_MESECI_SR}.items():
        s = s.replace(en, sr)
    return s


# ─── Generisanje briefinga ─────────────────────────────────────────────────────

async def _generiši_briefing(uid: str, supa) -> dict:
    """
    Generiše kompletan personalizovani jutarnji briefing za advokata.
    Paralelno dohvata sve podatke, zatim AI sintetiše.
    """
    danas   = date.today()
    za_7    = danas + timedelta(days=7)

    predmeti_r, rokovi_r, rocista_r, klijenti_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id, naziv, status, stranka, protivnik, updated_at")
                .eq("user_id", uid)
                .in_("status", ["aktivan", "u_toku", "pending"])
                .order("updated_at", desc=True)
                .limit(20)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rokovi")
                .select("id, naziv, datum, tip, predmet_id, opis")
                .eq("user_id", uid)
                .gte("datum", danas.isoformat())
                .lte("datum", za_7.isoformat())
                .order("datum")
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, naziv, datum_vreme, sud, predmet_id, tip")
                .eq("user_id", uid)
                .gte("datum_vreme", danas.isoformat())
                .lte("datum_vreme", za_7.isoformat())
                .order("datum_vreme")
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("klijenti")
                .select("id, ime, prezime, naziv_kompanije")
                .eq("user_id", uid)
                .limit(100)
                .execute()
        ),
    )

    predmeti = predmeti_r.data or []
    rokovi   = rokovi_r.data   or []
    rocista  = rocista_r.data  or []

    def _dani_do(datum_str: str) -> int:
        try:
            return (date.fromisoformat(str(datum_str)[:10]) - danas).days
        except Exception:
            return 999

    rokovi_hitni    = [r for r in rokovi if _dani_do(r["datum"]) <= 2]
    rokovi_uskoro   = [r for r in rokovi if 2 < _dani_do(r["datum"]) <= 7]
    rocista_danas   = [r for r in rocista if str(r.get("datum_vreme", ""))[:10] == danas.isoformat()]
    rocista_sedmica = [r for r in rocista if str(r.get("datum_vreme", ""))[:10] != danas.isoformat()]

    # ── AI kontekst ────────────────────────────────────────────────────────────
    parts = []
    if rocista_danas:
        parts.append(
            f"ROČIŠTA DANAS ({len(rocista_danas)}):\n" +
            "\n".join(
                f"- {r.get('naziv','Ročište')} u {str(r.get('datum_vreme',''))[:16]}, sud: {r.get('sud','N/A')}"
                for r in rocista_danas
            )
        )
    if rokovi_hitni:
        parts.append(
            f"HITNI ROKOVI (ističu za 0-2 dana) ({len(rokovi_hitni)}):\n" +
            "\n".join(f"- {r.get('naziv','Rok')} — {r['datum']}" for r in rokovi_hitni)
        )
    if rokovi_uskoro:
        parts.append(
            f"ROKOVI OVE NEDELJE ({len(rokovi_uskoro)}):\n" +
            "\n".join(f"- {r.get('naziv','Rok')} — {r['datum']}" for r in rokovi_uskoro)
        )
    if predmeti:
        parts.append(
            f"AKTIVNI PREDMETI ({len(predmeti)}):\n" +
            "\n".join(
                f"- {p.get('naziv','Predmet')} | stranka: {p.get('stranka','N/A')}"
                for p in predmeti[:10]
            )
        )
    if rocista_sedmica:
        parts.append(
            f"ROČIŠTA OVE NEDELJE ({len(rocista_sedmica)}):\n" +
            "\n".join(
                f"- {r.get('naziv','Ročište')} — {str(r.get('datum_vreme',''))[:10]}"
                for r in rocista_sedmica[:5]
            )
        )

    context = "\n\n".join(parts) if parts else "Nema hitnih stavki za danas."

    ai_prompt = f"""Ti si lični AI asistent advokata. Danas je {_danas_sr(danas)}.

Na osnovu sledećih podataka iz sistema, napiši koncizan, profesionalan jutarnji briefing.

{context}

Napiši briefing u sledećem formatu:

**Dobro jutro.** [Jedna rečenica o tome kakav dan predstoji — mirno/zauzeto/kritično]

**Danas zahteva pažnju:**
[Lista 2-4 konkretne akcije, sa jasnim prioritetima. Budi specifičan — ne generički.]

**Ključni rok:**
[Najbitniji rok ili ročište sa konkretnom preporukom šta uraditi]

**Preporuka za danas:**
[Jedna konkretna akcija koja bi imala najveći uticaj na predmete]

Budi direktan, koncizan, kao iskusan kolega koji te brifuje. Bez praznih reči. Ekavica."""

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    ai_resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": ai_prompt}],
            max_tokens=600,
            temperature=0.4,
        )
    )

    ai_tekst = ai_resp.choices[0].message.content.strip()

    return {
        "datum": danas.isoformat(),
        "ai_briefing": ai_tekst,
        "statistike": {
            "aktivnih_predmeta":  len(predmeti),
            "rokova_ove_nedelje": len(rokovi),
            "rokova_hitnih":      len(rokovi_hitni),
            "rocista_danas":      len(rocista_danas),
            "rocista_sedmica":    len(rocista_sedmica),
        },
        "rokovi_hitni":  [{"naziv": r.get("naziv"), "datum": r["datum"]} for r in rokovi_hitni],
        "rocista_danas": [
            {"naziv": r.get("naziv"), "vreme": str(r.get("datum_vreme", ""))[:16], "sud": r.get("sud")}
            for r in rocista_danas
        ],
        "generisano_u": datetime.now(timezone.utc).isoformat(),
    }


# ─── Email ─────────────────────────────────────────────────────────────────────

def _briefing_email_html(briefing: dict, ime: str = "Advokate") -> str:
    datum_prikaz = briefing.get("datum", "")
    ai_tekst     = briefing.get("ai_briefing", "")
    stat         = briefing.get("statistike", {})

    ai_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", ai_tekst)
    ai_html = ai_html.replace("\n", "<br>")

    rokovi_hitni = briefing.get("rokovi_hitni", [])
    rocista_d    = briefing.get("rocista_danas", [])

    rokovi_html = ""
    if rokovi_hitni:
        items = "".join(
            f'<li style="color:#ef4444;margin:4px 0;"><strong>{r["naziv"]}</strong> — {r["datum"]}</li>'
            for r in rokovi_hitni
        )
        rokovi_html = (
            '<div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);'
            'border-radius:8px;padding:12px 16px;margin:16px 0;">'
            '<strong style="color:#ef4444;">⚠️ Hitni rokovi</strong>'
            f'<ul style="margin:8px 0 0;padding-left:20px;">{items}</ul></div>'
        )

    rocista_html = ""
    if rocista_d:
        items = "".join(
            f'<li style="color:#00d4ff;margin:4px 0;"><strong>{r["naziv"]}</strong>'
            f' u {r["vreme"][-5:] if len(r.get("vreme",""))>=5 else r.get("vreme","")}</li>'
            for r in rocista_d
        )
        rocista_html = (
            '<div style="background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.2);'
            'border-radius:8px;padding:12px 16px;margin:16px 0;">'
            '<strong style="color:#00d4ff;">⚖️ Ročišta danas</strong>'
            f'<ul style="margin:8px 0 0;padding-left:20px;">{items}</ul></div>'
        )

    hitni_color = "#ef4444" if stat.get("rokova_hitnih", 0) > 0 else "#22c55e"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#060e1a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<div style="max-width:600px;margin:24px auto;background:#0a1628;border:1px solid #1e3a5f;border-radius:16px;overflow:hidden;">

  <div style="background:linear-gradient(135deg,#0f2035,#0a1628);padding:28px 32px;border-bottom:1px solid #1e3a5f;">
    <div style="display:flex;align-items:center;gap:12px;">
      <div style="font-size:28px;">⚖️</div>
      <div>
        <div style="font-size:20px;font-weight:800;color:#fff;">Vindex AI</div>
        <div style="font-size:13px;color:#64748b;">Jutarnji izveštaj · {datum_prikaz}</div>
      </div>
    </div>
  </div>

  <div style="display:flex;background:#0d1e2e;padding:16px 32px;gap:24px;border-bottom:1px solid #1e293b;">
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:#00d4ff;">{stat.get('aktivnih_predmeta',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Aktivnih predmeta</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:{hitni_color};">{stat.get('rokova_hitnih',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Hitnih rokova</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:#f59e0b;">{stat.get('rocista_danas',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Ročišta danas</div>
    </div>
    <div style="text-align:center;flex:1;">
      <div style="font-size:24px;font-weight:800;color:#a78bfa;">{stat.get('rokova_ove_nedelje',0)}</div>
      <div style="font-size:11px;color:#64748b;margin-top:2px;">Rokova ove nedelje</div>
    </div>
  </div>

  <div style="padding:28px 32px;">
    {rokovi_html}
    {rocista_html}
    <div style="background:#0d1e2e;border:1px solid #1e293b;border-radius:10px;padding:20px 24px;margin:16px 0;">
      <div style="font-size:12px;color:#00d4ff;font-weight:700;letter-spacing:0.08em;margin-bottom:12px;">✦ AI ANALIZA</div>
      <div style="font-size:14px;color:#e2e8f0;line-height:1.7;">{ai_html}</div>
    </div>
  </div>

  <div style="padding:20px 32px;border-top:1px solid #1e293b;text-align:center;">
    <a href="https://vindex-ai.onrender.com/app"
       style="display:inline-block;background:#00d4ff;color:#000;font-weight:700;font-size:14px;
              padding:12px 28px;border-radius:10px;text-decoration:none;">
      Otvori Vindex →
    </a>
    <div style="margin-top:12px;font-size:11px;color:#374151;">
      Vindex AI · Automatski jutarnji izveštaj
    </div>
  </div>

</div>
</body></html>"""


def _smtp_send(msg: MIMEMultipart, to_email: str) -> None:
    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(_SMTP_USER, _SMTP_PASS)
        smtp.sendmail(_FROM_ADDR, [to_email], msg.as_bytes())


async def _pošalji_briefing_email(to_email: str, briefing: dict, ime: str = "") -> bool:
    if not _SMTP_HOST or not to_email:
        return False

    html  = _briefing_email_html(briefing, ime)
    datum = briefing.get("datum", "")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Vindex jutarnji izveštaj — {datum}"
        msg["From"]    = f"Vindex AI <{_FROM_ADDR}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html, "html", "utf-8"))
        await asyncio.to_thread(_smtp_send, msg, to_email)
        return True
    except Exception as e:
        logger.error("Briefing email greška za %s: %s", to_email, e)
        return False


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/briefing/daily")
@limiter.limit("10/minute")
async def get_daily_briefing(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Generiši i vrati personalizovani jutarnji briefing (on-demand)."""
    uid  = user["user_id"]
    supa = _get_supa()

    briefing = await _generiši_briefing(uid, supa)

    try:
        await asyncio.to_thread(
            lambda: supa.table("briefing_istorija").insert({
                "user_id":     uid,
                "datum":       briefing["datum"],
                "ai_briefing": briefing["ai_briefing"],
                "statistike":  briefing["statistike"],
            }).execute()
        )
    except Exception:
        pass

    return briefing


@router.post("/api/briefing/send-email")
@limiter.limit("3/hour")
async def send_briefing_email(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Pošalji briefing emailom na adresu korisnika."""
    uid        = user["user_id"]
    user_email = user.get("email", "")

    if not user_email:
        raise HTTPException(status_code=400, detail="Email adresa nije podešena na nalogu.")

    supa     = _get_supa()
    briefing = await _generiši_briefing(uid, supa)
    sent     = await _pošalji_briefing_email(user_email, briefing)

    return {"ok": sent, "email": user_email, "datum": briefing["datum"]}


@router.post("/api/briefing/cron")
async def briefing_cron(request: Request):
    """
    Poziva se iz eksternog cron servisa svako jutro u 8:00 (Beograd = 06:00 UTC).
    Zaštićen BRIEFING_CRON_SECRET header-om.

    Podešavanje (cron-job.org ili Render Cron):
      URL:      POST https://vindex-ai.onrender.com/api/briefing/cron
      Header:   X-Cron-Secret: {BRIEFING_CRON_SECRET}
      Schedule: 0 6 * * 1-5   (radni dani)
    """
    cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
    x_secret    = request.headers.get("X-Cron-Secret", "")

    if cron_secret and x_secret != cron_secret:
        raise HTTPException(status_code=403, detail="Neovlašćen pristup.")

    supa = _get_supa()

    try:
        korisnici_r = await asyncio.to_thread(
            lambda: supa.table("korisnici")
                .select("id, email, ime")
                .eq("briefing_aktivan", True)
                .not_.is_("email", "null")
                .execute()
        )
        korisnici = korisnici_r.data or []
    except Exception:
        try:
            korisnici_r = await asyncio.to_thread(
                lambda: supa.table("korisnici").select("id, email, ime").limit(500).execute()
            )
            korisnici = korisnici_r.data or []
        except Exception as e:
            logger.error("Cron: greška pri dohvatanju korisnika: %s", e)
            return {"ok": False, "error": str(e)}

    poslato = 0
    greske  = 0

    for k in korisnici:
        uid   = k.get("id")
        email = k.get("email", "")
        ime   = k.get("ime") or "Advokate"

        if not uid or not email:
            continue

        try:
            briefing = await _generiši_briefing(uid, supa)
            sent     = await _pošalji_briefing_email(email, briefing, ime)
            if sent:
                poslato += 1
            else:
                greske += 1
        except Exception as e:
            logger.error("Cron briefing greška za %s: %s", email, e)
            greske += 1

        await asyncio.sleep(0.5)

    logger.info("Briefing cron završen: %d poslato, %d grešaka", poslato, greske)
    return {"ok": True, "poslato": poslato, "greske": greske, "ukupno": len(korisnici)}


@router.get("/api/briefing/history")
async def get_briefing_history(
    user: dict = Depends(get_current_user),
    limit: int = 7,
):
    """Prethodnih N dana briefinga (max 30)."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("briefing_istorija")
                .select("datum, ai_briefing, statistike, created_at")
                .eq("user_id", uid)
                .order("datum", desc=True)
                .limit(min(limit, 30))
                .execute()
        )
        return {"history": r.data or []}
    except Exception:
        return {"history": []}
