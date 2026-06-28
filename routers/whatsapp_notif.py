# -*- coding: utf-8 -*-
"""
Vindex AI — routers/whatsapp_notif.py

WhatsApp (i Viber) notifikacije za pravne rokove via Twilio.

NAPOMENA — PRODUKCIJA:
  Twilio WhatsApp sandbox radi odmah, ali zahteva da korisnik
  prvi posalje poruku na sandbox broj. Za produkciju je potrebno
  Twilio WhatsApp Business odobrenje (Meta Business Verification).

SQL migracija — pokrenuti u Supabase SQL Editoru:
----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS whatsapp_pretplate (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE,
  telefon TEXT NOT NULL,
  kanal TEXT DEFAULT 'whatsapp',
  tip_notifikacija JSONB DEFAULT '["rokovi_hitni","rocista"]',
  aktivan BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS whatsapp_send_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  poslato_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wa_send_log_user
  ON whatsapp_send_log(user_id, poslato_at DESC);
----------------------------------------------------------------------

Env vars (Railway / .env):
  TWILIO_ACCOUNT_SID      — Twilio Account SID
  TWILIO_AUTH_TOKEN       — Twilio Auth Token
  TWILIO_WHATSAPP_FROM    — sender (format: whatsapp:+14155238886)

Endpointi:
  POST   /api/whatsapp/registruj          — korisnik registruje WhatsApp/Viber broj
  POST   /api/whatsapp/posalji-rok        — rucno pošalji notifikaciju o roku
  POST   /api/whatsapp/dnevni-brifing-wa  — jutarnji brifing za sve pretplatnike (cron)
  GET    /api/whatsapp/pretplata          — status pretplate korisnika
  DELETE /api/whatsapp/pretplata          — odjavljivanje
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user, _verify_token
from shared.rate import limiter

logger = logging.getLogger("vindex.whatsapp_notif")
router = APIRouter(tags=["whatsapp_notif"])

_CRON_SECRET = os.getenv("CRON_SECRET", "")
_security_opt = HTTPBearer(auto_error=False)

# ─── Rate limit: max 1 poruka po korisniku na sat ─────────────────────────────
_RATE_LIMIT_SATI = 1


# ─── Twilio helper ────────────────────────────────────────────────────────────

def _twilio_konfigurisan() -> bool:
    return bool(
        os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        and os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    )


def _posalji_whatsapp(telefon: str, poruka: str) -> bool:
    """
    Salje WhatsApp poruku via Twilio.
    Telefon mora biti u formatu +381XXXXXXXX (E.164).
    Vraca True ako je poruka uspesno poslata.

    NAPOMENA: Sandbox zahteva da korisnik prethodno posalje
    join poruku na Twilio sandbox broj.
    """
    sid   = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        logger.error("[WA] Twilio kredencijali nisu postavljeni.")
        return False
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        msg = client.messages.create(
            from_=os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
            body=poruka,
            to=f"whatsapp:{telefon}",
        )
        logger.info("[WA] Poslato na %s (sid=%s)", telefon, msg.sid)
        return True
    except Exception as exc:
        logger.error("[WA] Greška pri slanju na %s: %s", telefon, exc)
        return False


# ─── Cron / founder autentifikacija ───────────────────────────────────────────

async def _require_cron_or_founder(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_opt),
) -> dict:
    """FastAPI dep: prihvata X-Cron-Key header ILI validan founder Bearer JWT."""
    cron_key = request.headers.get("X-Cron-Key", "")
    if _CRON_SECRET and cron_key == _CRON_SECRET:
        founder_email = next(iter(FOUNDER_EMAILS), "")
        return {"user_id": "cron-scheduler", "email": founder_email}
    if credentials:
        payload = await asyncio.to_thread(_verify_token, credentials.credentials)
        if payload:
            email = (payload.get("email") or "").lower()
            if email in FOUNDER_EMAILS:
                return {"user_id": payload.get("sub"), "email": email}
    raise HTTPException(status_code=403, detail="Restricted — founder ili cron key.")


# ─── Phone normalizacija ──────────────────────────────────────────────────────

def _normalizuj_telefon(broj: str) -> str:
    """Normalizuje srpski broj u E.164 format (+381XXXXXXXX)."""
    ociscen = re.sub(r"[\s\-\(\)\.]+", "", broj.strip())
    if ociscen.startswith("06"):
        ociscen = "+381" + ociscen[1:]
    elif ociscen.startswith("381") and not ociscen.startswith("+"):
        ociscen = "+" + ociscen
    if not re.match(r"^\+\d{7,15}$", ociscen):
        raise ValueError(f"Neispravan format broja telefona: {broj!r}. Koristite +381XXXXXXXXX.")
    return ociscen


# ─── Rate limit check (Supabase) ─────────────────────────────────────────────

def _proveri_rate_limit(supa, user_id: str) -> bool:
    """
    Vraca True ako korisnik MOZE da primi poruku (nije probio limit).
    Limit: max 1 poruka po korisniku na sat (whatsapp_send_log tabela).
    """
    pre_sat = (datetime.now(timezone.utc) - timedelta(hours=_RATE_LIMIT_SATI)).isoformat()
    try:
        res = (
            supa.table("whatsapp_send_log")
            .select("id")
            .eq("user_id", user_id)
            .gte("poslato_at", pre_sat)
            .limit(1)
            .execute()
        )
        return not bool(res.data)
    except Exception as exc:
        logger.warning("[WA] Rate limit provera neuspesna: %s — dozvoljavamo slanje", exc)
        return True


def _zabeleži_slanje(supa, user_id: str) -> None:
    """Belezi slanje u whatsapp_send_log za rate limiting."""
    try:
        supa.table("whatsapp_send_log").insert({"user_id": user_id}).execute()
    except Exception as exc:
        logger.warning("[WA] Beleška slanja neuspesna: %s", exc)


# ─── Pydantic modeli ──────────────────────────────────────────────────────────

TipNotifikacije = Literal["rokovi_hitni", "rocista", "dnevni_brifing", "sve"]


class RegistracijaReq(BaseModel):
    telefon: str = Field(..., min_length=9, max_length=20, description="Broj u formatu +381XXXXXXXXX")
    kanal: Literal["whatsapp", "viber"] = "whatsapp"
    tip_notifikacija: List[TipNotifikacije] = Field(
        default=["rokovi_hitni", "rocista"],
        description="Tipovi notifikacija: rokovi_hitni, rocista, dnevni_brifing, sve",
    )


class PošaljiRokReq(BaseModel):
    rok_id: str = Field(..., description="UUID roka iz tabele rokovi")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/api/whatsapp/registruj")
@limiter.limit("5/minute")
async def registruj_pretplatu(
    request: Request,
    req: RegistracijaReq,
    user: dict = Depends(get_current_user),
):
    """
    Korisnik registruje WhatsApp (ili Viber) broj za notifikacije.
    Odmah salje welcome poruku kao potvrdu.
    """
    if not _twilio_konfigurisan():
        raise HTTPException(
            status_code=503,
            detail="WhatsApp servis nije konfigurisan. Kontaktirajte administratora (TWILIO env vars).",
        )

    try:
        telefon = _normalizuj_telefon(req.telefon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    supa   = _get_supa()
    uid    = user["user_id"]
    tipovi = req.tip_notifikacija

    await asyncio.to_thread(
        lambda: supa.table("whatsapp_pretplate").upsert(
            {
                "user_id":          uid,
                "telefon":          telefon,
                "kanal":            req.kanal,
                "tip_notifikacija": tipovi,
                "aktivan":          True,
            },
            on_conflict="user_id",
        ).execute()
    )
    logger.info("[WA] Registracija uid=%.8s telefon=%s kanal=%s", uid, telefon, req.kanal)

    # Welcome poruka
    welcome = (
        "⚖ *Vindex AI*\n"
        "Uspesno ste se prijavili na WhatsApp notifikacije.\n\n"
        "Dobicete obavestenja o:\n"
        + ("• Hitnim rokovima\n" if "rokovi_hitni" in tipovi or "sve" in tipovi else "")
        + ("• Rocistima\n" if "rocista" in tipovi or "sve" in tipovi else "")
        + ("• Dnevnom brifingu\n" if "dnevni_brifing" in tipovi or "sve" in tipovi else "")
        + "\nPrijavite se: app.vindex.rs"
    )

    ok = await asyncio.to_thread(_posalji_whatsapp, telefon, welcome)
    if not ok:
        logger.warning("[WA] Welcome poruka nije poslata uid=%.8s", uid)

    return {
        "ok": True,
        "telefon": telefon,
        "kanal": req.kanal,
        "tip_notifikacija": tipovi,
        "welcome_poslat": ok,
    }


@router.post("/api/whatsapp/posalji-rok")
@limiter.limit("10/minute")
async def posalji_rok(
    request: Request,
    req: PošaljiRokReq,
    user: dict = Depends(get_current_user),
):
    """
    Rucno posalje WhatsApp notifikaciju o odredjenom roku.
    Dohvata rok + predmet iz Supabase i salje formatiranu poruku.
    """
    if not _twilio_konfigurisan():
        raise HTTPException(
            status_code=503,
            detail="WhatsApp servis nije konfigurisan (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN).",
        )

    supa = _get_supa()
    uid  = user["user_id"]

    # Dohvati pretplatu
    pretplata_r = await asyncio.to_thread(
        lambda: supa.table("whatsapp_pretplate")
            .select("telefon, aktivan")
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    pretplata = pretplata_r.data
    if not pretplata or not pretplata.get("aktivan"):
        raise HTTPException(
            status_code=422,
            detail="Niste registrovani za WhatsApp notifikacije. Koristite /api/whatsapp/registruj.",
        )

    # Rate limit provera
    dozvoljen = await asyncio.to_thread(_proveri_rate_limit, supa, uid)
    if not dozvoljen:
        raise HTTPException(
            status_code=429,
            detail=f"Prekoracen limit: max 1 WhatsApp poruka po korisniku na sat.",
        )

    # Dohvati rok iz tabele rokovi
    rok_r = await asyncio.to_thread(
        lambda: supa.table("rokovi")
            .select("id, naziv, datum, opis, predmet_id")
            .eq("id", req.rok_id)
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )
    rok = rok_r.data
    if not rok:
        raise HTTPException(status_code=404, detail="Rok nije pronadjen.")

    # Dohvati naziv predmeta
    naziv_predmeta = "Predmet"
    if rok.get("predmet_id"):
        predmet_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv")
                .eq("id", rok["predmet_id"])
                .maybe_single()
                .execute()
        )
        if predmet_r.data:
            naziv_predmeta = predmet_r.data.get("naziv", "Predmet")

    datum_str  = (rok.get("datum") or "")[:10]
    dogadjaj   = rok.get("naziv") or rok.get("opis") or "Rok"
    telefon    = pretplata["telefon"]

    poruka = (
        f"⚖ Vindex AI\n"
        f"*{naziv_predmeta}*\n"
        f"📅 Rok: {datum_str}\n"
        f"📌 {dogadjaj}\n\n"
        f"Prijavite se na app.vindex.rs"
    )

    ok = await asyncio.to_thread(_posalji_whatsapp, telefon, poruka)
    if ok:
        await asyncio.to_thread(_zabeleži_slanje, supa, uid)
    else:
        raise HTTPException(status_code=502, detail="WhatsApp poruka nije mogla biti poslata.")

    return {"ok": True, "poslato_na": telefon, "rok_id": req.rok_id}


@router.post("/api/whatsapp/dnevni-brifing-wa")
@limiter.limit("10/minute")
async def dnevni_brifing_wa(
    request: Request,
    user: dict = Depends(_require_cron_or_founder),
):
    """
    Jutarnji WhatsApp brifing — salje se svim aktivnim pretplatnicima.
    Poziva se cron sistemom svakog dana u 07:30.

    Autentifikacija: X-Cron-Key header (CRON_SECRET) ILI founder Bearer JWT.

    Railway/Render cron podesavanje:
      URL: POST https://vindex.rs/api/whatsapp/dnevni-brifing-wa
      Header: X-Cron-Key: <CRON_SECRET>
      Raspored: 30 7 * * 1-6 (pon-sub u 07:30)
    """
    if not _twilio_konfigurisan():
        raise HTTPException(
            status_code=503,
            detail="WhatsApp servis nije konfigurisan (TWILIO env vars).",
        )

    supa      = _get_supa()
    danas     = date.today()
    danas_iso = danas.isoformat()
    za_7_iso  = (danas + timedelta(days=7)).isoformat()

    def _dohvati_pretplatnike():
        return (
            supa.table("whatsapp_pretplate")
            .select("user_id, telefon, tip_notifikacija")
            .eq("aktivan", True)
            .execute()
        )

    pretpl_r    = await asyncio.to_thread(_dohvati_pretplatnike)
    pretplatnici = pretpl_r.data or []

    if not pretplatnici:
        return {"poslato": 0, "preskoceno": 0, "greske": 0, "napomena": "Nema aktivnih pretplatnika"}

    # Filtriraj samo one koji imaju dnevni_brifing ili sve
    pretplatnici = [
        p for p in pretplatnici
        if "dnevni_brifing" in (p.get("tip_notifikacija") or [])
        or "sve" in (p.get("tip_notifikacija") or [])
    ]

    poslato  = 0
    preskoceno = 0
    greske   = 0

    for pretpl in pretplatnici:
        uid     = pretpl["user_id"]
        telefon = pretpl["telefon"]

        # Rate limit provera
        dozvoljen = await asyncio.to_thread(_proveri_rate_limit, supa, uid)
        if not dozvoljen:
            logger.debug("[WA-CRON] Rate limit uid=%.8s — preskacam", uid)
            preskoceno += 1
            continue

        # Dohvati podatke za brifing
        rokovi_r, rocista_r = await asyncio.gather(
            asyncio.to_thread(
                lambda u=uid: supa.table("rokovi")
                    .select("naziv, datum, opis")
                    .eq("user_id", u)
                    .gte("datum", danas_iso)
                    .lte("datum", za_7_iso)
                    .order("datum")
                    .limit(5)
                    .execute()
            ),
            asyncio.to_thread(
                lambda u=uid: supa.table("rocista")
                    .select("naziv, datum, vreme, sud")
                    .eq("user_id", u)
                    .eq("datum", danas_iso)
                    .limit(5)
                    .execute()
            ),
        )

        rokovi        = rokovi_r.data or []
        rocista_danas = rocista_r.data or []

        # Gradimo poruku (max 4000 znakova — WhatsApp limit)
        linije = [
            f"⚖ *Vindex AI — Jutarnji brifing*",
            f"📆 {danas.strftime('%d.%m.%Y')}",
            "",
        ]

        if rocista_danas:
            linije.append("🏛 *Danas u sudu:*")
            for r in rocista_danas[:3]:
                naziv = r.get("naziv") or r.get("sud") or "Rociste"
                vreme = r.get("vreme", "")
                linije.append(f"  • {naziv}" + (f" u {vreme}" if vreme else ""))

        if rokovi:
            linije.append("")
            linije.append("📅 *Nadolazeci rokovi (7 dana):*")
            for rok in rokovi[:5]:
                naziv  = rok.get("naziv") or rok.get("opis") or "Rok"
                datum  = (rok.get("datum") or "")[:10]
                linije.append(f"  • {datum} — {naziv}")

        if not rocista_danas and not rokovi:
            linije.append("✅ Nema hitnih rokova ni rocista.")

        linije.append("")
        linije.append("Detalji: app.vindex.rs")

        poruka = "\n".join(linije)
        if len(poruka) > 4000:
            poruka = poruka[:3997] + "..."

        ok = await asyncio.to_thread(_posalji_whatsapp, telefon, poruka)
        if ok:
            await asyncio.to_thread(_zabeleži_slanje, supa, uid)
            poslato += 1
            logger.info("[WA-CRON] Brifing poslat uid=%.8s", uid)
        else:
            greske += 1
            logger.warning("[WA-CRON] Brifing nije poslat uid=%.8s", uid)

    return {"poslato": poslato, "preskoceno": preskoceno, "greske": greske, "datum": danas_iso}


@router.get("/api/whatsapp/pretplata")
@limiter.limit("30/minute")
async def get_pretplata(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraca status WhatsApp pretplate korisnika."""
    supa = _get_supa()
    uid  = user["user_id"]

    res = await asyncio.to_thread(
        lambda: supa.table("whatsapp_pretplate")
            .select("telefon, kanal, tip_notifikacija, aktivan, created_at")
            .eq("user_id", uid)
            .maybe_single()
            .execute()
    )

    twilio_ok = _twilio_konfigurisan()

    if not res.data:
        return {
            "registrovan": False,
            "aktivan": False,
            "twilio_konfigurisan": twilio_ok,
        }

    d = res.data
    return {
        "registrovan": True,
        "aktivan": d.get("aktivan", False),
        "telefon": d.get("telefon"),
        "kanal": d.get("kanal", "whatsapp"),
        "tip_notifikacija": d.get("tip_notifikacija", []),
        "created_at": d.get("created_at"),
        "twilio_konfigurisan": twilio_ok,
    }


@router.delete("/api/whatsapp/pretplata")
@limiter.limit("10/minute")
async def odjavi_pretplatu(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Deaktivira WhatsApp pretplatu korisnika (ne brise — samo aktivan=False)."""
    supa = _get_supa()
    uid  = user["user_id"]

    await asyncio.to_thread(
        lambda: supa.table("whatsapp_pretplate")
            .update({"aktivan": False})
            .eq("user_id", uid)
            .execute()
    )
    logger.info("[WA] Odjava pretplate uid=%.8s", uid)
    return {"ok": True, "aktivan": False}
