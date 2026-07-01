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
                .select("id, sud, datum, vreme, predmet_id, status")
                .eq("user_id", uid)
                .gte("datum", danas.isoformat())
                .lte("datum", za_7.isoformat())
                .order("datum")
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
    rocista_danas   = [r for r in rocista if str(r.get("datum", ""))[:10] == danas.isoformat()]
    rocista_sedmica = [r for r in rocista if str(r.get("datum", ""))[:10] != danas.isoformat()]

    # ── AI kontekst ────────────────────────────────────────────────────────────
    parts = []
    if rocista_danas:
        parts.append(
            f"ROČIŠTA DANAS ({len(rocista_danas)}):\n" +
            "\n".join(
                f"- Ročište u {r.get('sud','N/A')} — {r.get('datum','')} {(r.get('vreme') or '')[:5]}"
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
                f"- Ročište ({r.get('sud','N/A')}) — {r.get('datum','')}"
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
            {"naziv": f"Ročište - {r.get('sud','')}", "vreme": f"{r.get('datum','')} {(r.get('vreme') or '')[:5]}", "sud": r.get("sud")}
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
            lambda: supa.table("profiles")
                .select("id, email")
                .not_.is_("email", "null")
                .limit(500)
                .execute()
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
        ime   = k.get("ime") or k.get("email", "").split("@")[0] or "Advokate"

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


# ─── Nightly Intelligence Run ──────────────────────────────────────────────────

async def _generiši_alerts_za_korisnika(uid: str, supa) -> list[dict]:
    """
    Skenira predmete, rokove i ročišta za korisnika i generiše listu proactive alertova.
    """
    danas   = date.today()
    za_3    = (danas + timedelta(days=3)).isoformat()
    za_7    = (danas + timedelta(days=7)).isoformat()
    za_48h  = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    pre_30  = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    alerts: list[dict] = []

    try:
        predmeti_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id, naziv, updated_at")
                .eq("user_id", uid)
                .in_("status", ["aktivan", "u_toku", "pending"])
                .execute()
        )
        predmeti = predmeti_r.data or []
    except Exception:
        return []

    predmeti_map = {p["id"]: p for p in predmeti}
    pred_ids = list(predmeti_map.keys())
    if not pred_ids:
        return []

    # Rokovi koji ističu za <= 3 dana (hitni)
    try:
        rok_r = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, sud, datum, predmet_id")
                .in_("predmet_id", pred_ids[:30])
                .gte("datum", danas.isoformat())
                .lte("datum", za_3)
                .execute()
        )
        for r in (rok_r.data or []):
            p = predmeti_map.get(r.get("predmet_id", ""), {})
            alerts.append({
                "tip":        "rok_kritican",
                "naslov":     f"Hitno rociste — {r.get('sud', 'Rociste')}",
                "opis":       f"Rociste {r.get('datum', '')[:10]} · Predmet: {p.get('naziv', '')}",
                "urgentnost": "hitna",
                "predmet_id": r.get("predmet_id"),
            })
    except Exception as e:
        logger.debug("[NIGHTLY] rokovi_hitni greška: %s", e)

    # Rokovi 4-7 dana (visoka urgentnost)
    try:
        rok_r2 = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, sud, datum, predmet_id")
                .in_("predmet_id", pred_ids[:30])
                .gt("datum", za_3)
                .lte("datum", za_7)
                .execute()
        )
        for r in (rok_r2.data or []):
            p = predmeti_map.get(r.get("predmet_id", ""), {})
            alerts.append({
                "tip":        "rok_uskoro",
                "naslov":     f"Rociste uskoro — {r.get('sud', 'Rociste')}",
                "opis":       f"Rociste {r.get('datum', '')[:10]} · Predmet: {p.get('naziv', '')}",
                "urgentnost": "visoka",
                "predmet_id": r.get("predmet_id"),
            })
    except Exception as e:
        logger.debug("[NIGHTLY] rokovi_uskoro greška: %s", e)

    # Ročišta u narednih 48h
    try:
        roc_r = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("id, datum, sud, predmet_id")
                .eq("user_id", uid)
                .gte("datum", danas.isoformat())
                .lte("datum", za_48h[:10])
                .execute()
        )
        for r in (roc_r.data or []):
            p = predmeti_map.get(r.get("predmet_id", ""), {})
            alerts.append({
                "tip":        "rociste_sutra",
                "naslov":     f"Ročište — {r.get('sud', 'Sud')}",
                "opis":       f"Zakazano {r.get('datum', '')[:10]} · Predmet: {p.get('naziv', '')}",
                "urgentnost": "hitna",
                "predmet_id": r.get("predmet_id"),
            })
    except Exception as e:
        logger.debug("[NIGHTLY] rocista greška: %s", e)

    # Predmeti neaktivni 30+ dana
    try:
        for p in predmeti:
            upd = p.get("updated_at") or ""
            if upd and upd < pre_30:
                alerts.append({
                    "tip":        "predmet_neaktivan",
                    "naslov":     f"Neaktivan predmet — {p.get('naziv', '')}",
                    "opis":       "Predmet nije ažuriran više od 30 dana.",
                    "urgentnost": "normalna",
                    "predmet_id": p.get("id"),
                })
    except Exception as e:
        logger.debug("[NIGHTLY] neaktivni greška: %s", e)

    return alerts


async def _ai_prioritizacija_alertova(alerts: list[dict], ime: str) -> str:
    """GPT-4o-mini: kratka prioritizovana lista najvažnijih alertova."""
    if not alerts:
        return ""
    hitni   = [a for a in alerts if a["urgentnost"] == "hitna"]
    visoki  = [a for a in alerts if a["urgentnost"] == "visoka"]
    linije  = []
    for a in (hitni + visoki)[:8]:
        linije.append(f"- [{a['urgentnost'].upper()}] {a['naslov']}: {a['opis']}")
    if not linije:
        return ""

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    try:
        resp = await asyncio.to_thread(
            lambda: oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": (
                    f"Ti si AI asistent advokata {ime}. Na osnovu sledecih upozorenja "
                    f"napiši kratku prioritizovanu preporuku (max 150 reči, ekavica):\n\n"
                    + "\n".join(linije)
                )}],
                max_tokens=250,
                temperature=0.3,
            )
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("[NIGHTLY] AI prioritizacija greška: %s", e)
        return "\n".join(linije[:3])


def _nightly_email_html(alerts: list[dict], ai_tekst: str, ime: str) -> str:
    hitni_count = sum(1 for a in alerts if a["urgentnost"] == "hitna")
    alert_html = "".join(
        f'<div style="padding:8px 0;border-bottom:1px solid #1e293b;">'
        f'<span style="color:{"#ef4444" if a["urgentnost"]=="hitna" else "#f59e0b" if a["urgentnost"]=="visoka" else "#64748b"};font-weight:700;">'
        f'[{a["urgentnost"].upper()}]</span> '
        f'<strong style="color:#e2e8f0;">{a["naslov"]}</strong>'
        f'<div style="color:#94a3b8;font-size:12px;">{a["opis"]}</div>'
        f'</div>'
        for a in alerts[:10]
    )
    ai_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", ai_tekst or "").replace("\n", "<br>")
    return f"""<!DOCTYPE html><html><body style="background:#060e1a;font-family:sans-serif;">
<div style="max-width:600px;margin:24px auto;background:#0a1628;border:1px solid #1e3a5f;border-radius:16px;overflow:hidden;">
  <div style="padding:24px 32px;border-bottom:1px solid #1e3a5f;">
    <div style="font-size:18px;font-weight:800;color:#fff;">⚡ Vindex — Noćni izveštaj</div>
    <div style="color:#64748b;font-size:13px;">Automatska analiza · {date.today().isoformat()}</div>
  </div>
  <div style="padding:20px 32px;">
    <div style="background:rgba(239,68,68,0.1);border-radius:8px;padding:12px 16px;margin-bottom:16px;">
      <strong style="color:#ef4444;">Hitnih upozorenja: {hitni_count}</strong> · Ukupno: {len(alerts)}
    </div>
    {alert_html}
    {"<div style='margin-top:16px;padding:16px;background:#0d1e2e;border-radius:8px;color:#e2e8f0;font-size:14px;line-height:1.6;'>" + ai_html + "</div>" if ai_html else ""}
  </div>
  <div style="padding:16px 32px;border-top:1px solid #1e293b;text-align:center;">
    <a href="https://vindex-ai.onrender.com/app" style="background:#00d4ff;color:#000;font-weight:700;padding:10px 24px;border-radius:8px;text-decoration:none;">Otvori Vindex →</a>
  </div>
</div></body></html>"""


@router.post("/api/briefing/nightly-intelligence")
async def nightly_intelligence_run(request: Request):
    """
    Nightly Intelligence Run — 02:00 Beograd (00:00 UTC).
    Skenira sve predmete, kreira proactive alerts, šalje email svakom korisniku koji ima hitna upozorenja.

    Podešavanje cron-job.org:
      URL:      POST https://vindex-ai.onrender.com/api/briefing/nightly-intelligence
      Header:   X-Cron-Secret: {BRIEFING_CRON_SECRET}
      Schedule: 0 0 * * *   (svake noći u ponoć UTC = 02:00 Beograd)
    """
    cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
    x_secret    = request.headers.get("X-Cron-Secret", "")
    if cron_secret and x_secret != cron_secret:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=403, detail="Neovlašćen pristup.")

    supa = _get_supa()

    try:
        korisnici_r = await asyncio.to_thread(
            lambda: supa.table("profiles")
                .select("id, email")
                .not_.is_("email", "null")
                .limit(500)
                .execute()
        )
        korisnici = korisnici_r.data or []
    except Exception as e:
        logger.error("[NIGHTLY] Greška pri dohvatanju korisnika: %s", e)
        return {"ok": False, "error": str(e)}

    ukupno_alertova = 0
    emailova        = 0

    for k in korisnici:
        uid   = k.get("id")
        email = k.get("email", "")
        ime   = k.get("ime") or k.get("email", "").split("@")[0] or "Advokate"
        if not uid:
            continue

        try:
            alerts = await _generiši_alerts_za_korisnika(uid, supa)
            if not alerts:
                continue

            ai_tekst = await _ai_prioritizacija_alertova(alerts, ime)

            # Upiši alerts u bazu
            try:
                for a in alerts:
                    await asyncio.to_thread(
                        lambda al=a: supa.table("proactive_alerts").insert({
                            "user_id":    uid,
                            "tip":        al["tip"],
                            "naslov":     al["naslov"],
                            "opis":       al["opis"],
                            "urgentnost": al["urgentnost"],
                            "predmet_id": al.get("predmet_id"),
                            "procitana":  False,
                        }).execute()
                    )
                ukupno_alertova += len(alerts)
            except Exception as e:
                logger.debug("[NIGHTLY] Insert alert greška uid=%.8s: %s", uid, e)

            # Pošalji email ako ima SMTP
            hitni_alerts = [a for a in alerts if a["urgentnost"] == "hitna"]
            if hitni_alerts and _SMTP_HOST and email:
                try:
                    html = _nightly_email_html(alerts, ai_tekst, ime)
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = f"Vindex — Noćni izveštaj ({len(hitni_alerts)} hitnih)"
                    msg["From"]    = f"Vindex AI <{_FROM_ADDR}>"
                    msg["To"]      = email
                    msg.attach(MIMEText(html, "html", "utf-8"))
                    await asyncio.to_thread(_smtp_send, msg, email)
                    emailova += 1
                except Exception as e:
                    logger.error("[NIGHTLY] Email greška za %s: %s", email, e)

        except Exception as e:
            logger.error("[NIGHTLY] Greška za korisnika %s: %s", uid, e)

        await asyncio.sleep(0.3)

    logger.info("[NIGHTLY] Završen: %d korisnika, %d alertova, %d emailova",
                len(korisnici), ukupno_alertova, emailova)
    return {"ok": True, "korisnika": len(korisnici), "alertova": ukupno_alertova, "emailova": emailova}


# ─── Proactive Alerts endpoints ───────────────────────────────────────────────

@router.get("/api/briefing/alerts")
@limiter.limit("30/minute")
async def get_proactive_alerts(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Dohvata nepročitane proactive alerts za trenutnog korisnika."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .select("id, tip, naslov, opis, urgentnost, predmet_id, created_at")
                .eq("user_id", uid)
                .eq("procitana", False)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
        )
        alerts = r.data or []
    except Exception:
        alerts = []

    hitnih = sum(1 for a in alerts if a.get("urgentnost") == "hitna")
    return {"alerts": alerts, "ukupno": len(alerts), "hitnih": hitnih}


@router.patch("/api/briefing/alerts/{alert_id}/procitana")
async def mark_alert_read(
    alert_id: str,
    user: dict = Depends(get_current_user),
):
    """Označi alert kao pročitan."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .update({"procitana": True})
                .eq("id", alert_id)
                .eq("user_id", uid)
                .execute()
        )
    except Exception as e:
        logger.debug("[ALERTS] Mark read greška: %s", e)

    return {"ok": True}


@router.get("/api/briefing/urgency-stats")
@limiter.limit("30/minute")
async def get_urgency_stats(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Statistika nepročitanih alertova za UI badge."""
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .select("urgentnost")
                .eq("user_id", uid)
                .eq("procitana", False)
                .execute()
        )
        rows = r.data or []
    except Exception:
        rows = []

    hitnih   = sum(1 for a in rows if a.get("urgentnost") == "hitna")
    visokih  = sum(1 for a in rows if a.get("urgentnost") == "visoka")
    normalnih = sum(1 for a in rows if a.get("urgentnost") == "normalna")

    return {
        "hitnih":             hitnih,
        "visokih":            visokih,
        "normalnih":          normalnih,
        "ukupno_neprocitanih": len(rows),
    }


# ─── Today Focus — Single Pane of Glass ──────────────────────────────────────
# "Šta danas treba da uradim i zašto?"
# Jedan endpoint koji sakriva svu složenost i daje JEDNU akciju.

@router.get("/today-focus")
@limiter.limit("20/minute")
async def today_focus(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Centralni dnevni fokus — agregira sve u jedan odgovor.
    Advokat otvori app i vidi tačno šta je najvažnije danas.
    GPT poziv se kešira 5 minuta da se ne troši na svaki UI refresh.
    """
    uid  = user["user_id"]
    supa = _get_supa()
    now  = datetime.now(timezone.utc)
    today_iso  = now.date().isoformat()
    in_3d_iso  = (now.date() + timedelta(days=3)).isoformat()
    in_7d_iso  = (now.date() + timedelta(days=7)).isoformat()
    week_ago   = (now - timedelta(days=7)).isoformat()

    # ── Cache: ako je briefing_istorija svežija od 5 min, vrati keširano ──────
    try:
        cached_r = await asyncio.to_thread(
            lambda: supa.table("briefing_istorija")
                .select("ai_briefing,statistike,created_at")
                .eq("user_id", uid)
                .eq("datum", today_iso)
                .limit(1)
                .execute()
        )
        rows = cached_r.data or []
        if rows:
            row = rows[0]
            ts_str = row.get("created_at") or ""
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if (now - ts).total_seconds() < 300:  # 5 minuta
                    cached = row.get("statistike") or {}
                    return {
                        **cached,
                        "ai_poruka":      row.get("ai_briefing", ""),
                        "iz_kesa":        True,
                        "poslednji_refresh": ts_str,
                    }
    except Exception:
        pass

    # ── Korak 1: Aktivni predmeti (za cross-ref) ─────────────────────────────
    pred_map: dict[str, str] = {}
    try:
        pr = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv")
                .eq("user_id", uid)
                .neq("status", "zatvoren")
                .limit(100)
                .execute()
        )
        for p in (pr.data or []):
            pred_map[p["id"]] = p.get("naziv", "")
        aktivnih_predmeta = len(pred_map)
    except Exception:
        aktivnih_predmeta = 0

    # ── Korak 2: Hitni rokovi ≤3 dana ────────────────────────────────────────
    hitni_rokovi: list[dict] = []
    try:
        rr = await asyncio.to_thread(
            lambda: supa.table("rokovi")
                .select("predmet_id,naziv,datum,tip")
                .eq("user_id", uid)
                .gte("datum", today_iso)
                .lte("datum", in_3d_iso)
                .order("datum")
                .limit(10)
                .execute()
        )
        for r in (rr.data or []):
            datum = r.get("datum", "")
            try:
                dana_do = (date.fromisoformat(datum) - now.date()).days
            except Exception:
                dana_do = 0
            hitni_rokovi.append({
                "predmet_naziv": pred_map.get(r.get("predmet_id", ""), ""),
                "rok_naziv":     r.get("naziv", ""),
                "datum":         datum,
                "dana_do":       dana_do,
                "urgentnost":    "hitno" if dana_do <= 1 else "uskoro",
            })
    except Exception:
        pass

    # ── Korak 3: Ročišta ove nedelje ─────────────────────────────────────────
    rocista_nedelja: list[dict] = []
    try:
        rocr = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("predmet_id,datum,vreme,sud")
                .eq("user_id", uid)
                .gte("datum", today_iso)
                .lte("datum", in_7d_iso)
                .order("datum")
                .limit(5)
                .execute()
        )
        for r in (rocr.data or []):
            rocista_nedelja.append({
                "predmet_naziv": pred_map.get(r.get("predmet_id", ""), ""),
                "naziv":         r.get("sud", ""),
                "datum":         r.get("datum", ""),
                "sud":           r.get("sud", ""),
            })
    except Exception:
        pass

    # ── Korak 4: Predmeti bez aktivnosti 7+ dana ─────────────────────────────
    zapostavljeni: list[dict] = []
    try:
        zr = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv,tip,updated_at")
                .eq("user_id", uid)
                .neq("status", "zatvoren")
                .lt("updated_at", week_ago)
                .order("updated_at")
                .limit(3)
                .execute()
        )
        for p in (zr.data or []):
            zapostavljeni.append({
                "predmet_id":  p.get("id", ""),
                "naziv":       p.get("naziv", ""),
                "tip":         p.get("tip", ""),
                "poslednja_aktivnost": (p.get("updated_at") or "")[:10],
            })
    except Exception:
        pass

    # ── Korak 5: Lekcije na čekanju (predlog_ai → partner potvrđuje) ─────────
    lekcije_na_cekanju: list[dict] = []
    try:
        lr = await asyncio.to_thread(
            lambda: supa.table("lessons_learned")
                .select("id,lecija,kategorija,vaznost,broj_predmeta")
                .eq("user_id", uid)
                .eq("status_lekcije", "predlog_ai")
                .eq("zastarela", False)
                .order("vaznost", desc=True)
                .limit(3)
                .execute()
        )
        lekcije_na_cekanju = lr.data or []
    except Exception:
        pass

    # ── Korak 6: Neprocitani hitni alertovi ──────────────────────────────────
    hitni_alertovi: list[dict] = []
    try:
        ar = await asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
                .select("id,naslov,opis,urgentnost,created_at")
                .eq("user_id", uid)
                .eq("procitana", False)
                .eq("urgentnost", "hitna")
                .order("created_at", desc=True)
                .limit(5)
                .execute()
        )
        hitni_alertovi = ar.data or []
    except Exception:
        pass

    # ── Korak 7: AI sinteza — JEDNA najvažnija akcija ────────────────────────
    ai_poruka = ""
    try:
        rokovi_txt = "; ".join(
            f"{r['predmet_naziv']} ({r['rok_naziv']}, {r['dana_do']}d)"
            for r in hitni_rokovi[:3]
        ) or "nema"
        rocista_txt = "; ".join(
            f"{r['predmet_naziv']} {r['datum']} {r['sud']}"
            for r in rocista_nedelja[:3]
        ) or "nema"

        context = (
            f"Advokat ima:\n"
            f"- {len(hitni_rokovi)} hitnih rokova u sledeca 3 dana\n"
            f"- {len(rocista_nedelja)} rocista ove nedelje\n"
            f"- {len(zapostavljeni)} predmeta bez aktivnosti 7+ dana\n"
            f"- {len(lekcije_na_cekanju)} lekcija koje cekaju potvrdu\n"
            f"- {len(hitni_alertovi)} neprocitanih hitnih upozorenja\n\n"
            f"Hitni rokovi: {rokovi_txt}\n"
            f"Rocista: {rocista_txt}"
        )

        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=120,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si licni AI asistent advokata. Daj mu personalizovanu jutarnju poruku. "
                        "Budi konkretan i direktan. Maksimalno 3 recenice. "
                        "Fokus na NAJKRITIČNIJU stvar danas — izaberi JEDNU najvazniju akciju. "
                        "Ekavica strogo — nikada ijekavica."
                    ),
                },
                {"role": "user", "content": context},
            ],
        )
        ai_poruka = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("[TODAY_FOCUS] GPT greška: %s", e)
        if hitni_rokovi:
            r0 = hitni_rokovi[0]
            ai_poruka = (
                f"Prioritet danas: rok '{r0['rok_naziv']}' u predmetu "
                f"'{r0['predmet_naziv']}' istice za {r0['dana_do']} dan(a)."
            )
        elif rocista_nedelja:
            r0 = rocista_nedelja[0]
            ai_poruka = f"Imate rociste u sudu '{r0.get('sud', '')}' dana {r0.get('datum', '')}. Pripremite se."
        else:
            ai_poruka = "Nema hitnih rokova ni rocista. Dobar dan za stratesko planiranje."

    # ── Statistika ────────────────────────────────────────────────────────────
    statistika = {
        "aktivnih_predmeta":   aktivnih_predmeta,
        "rokova_ove_nedelje":  len(hitni_rokovi),
        "rocista_ove_nedelje": len(rocista_nedelja),
        "lekcija_na_cekanju":  len(lekcije_na_cekanju),
        "hitnih_alertova":     len(hitni_alertovi),
    }

    payload = {
        "datum":                today_iso,
        "ai_poruka":            ai_poruka,
        "hitni_rokovi":         hitni_rokovi,
        "rocista_nedelja":      rocista_nedelja,
        "zapostavljeni_predmeti": zapostavljeni,
        "lekcije_na_cekanju":   lekcije_na_cekanju,
        "hitni_alertovi":       hitni_alertovi,
        "statistika":           statistika,
        "iz_kesa":              False,
        "poslednji_refresh":    now.isoformat(),
    }

    # ── Keširanje u briefing_istorija ─────────────────────────────────────────
    try:
        await asyncio.to_thread(
            lambda: supa.table("briefing_istorija").upsert({
                "user_id":    uid,
                "datum":      today_iso,
                "ai_briefing": ai_poruka,
                "statistike": payload,
            }, on_conflict="user_id,datum").execute()
        )
    except Exception as e:
        logger.debug("[TODAY_FOCUS] cache upsert greška: %s", e)

    return payload
