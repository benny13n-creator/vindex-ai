# -*- coding: utf-8 -*-
"""
Vindex AI — routers/email_notif.py

Email podsetnici za kritične rokove (7, 3, 1 dan pre).
Koristi isti SMTP kao billing (EMAIL_SMTP_* env vars).

Endpoints:
  GET  /email-notif/profil            — dohvata podešavanja (opt-in, 7/3/1 dan)
  POST /email-notif/profil            — čuva/ažurira podešavanja
  DELETE /email-notif/profil          — deaktivira email notifikacije
  POST /email-notif/test              — šalje test email na login email
  POST /email-notif/send-reminders    — interni cron trigger (founder only)
  POST /email-notif/onboarding-welcome — šalje welcome email jednom korisniku
  POST /email-notif/onboarding-cron   — cron: šalje day1 i day3 onboarding emailove

SEC-002 (2026-07-24): ovaj fajl više NE definiše /api/cron/daily -- taj
jedinstveni master dispečer živi isključivo u api.py, koji poziva
posalji_podsetnike/onboarding_cron/posalji_nedeljni_sazetak direktno kao
svoje module (vidi napomenu iznad Master cron sekcije, na kraju fajla).
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import smtplib
import types
import uuid
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, field_validator

from shared.deps import FOUNDER_EMAILS, _get_supa, get_current_user, _verify_token
from shared.rate import limiter
from routers.gdpr import make_unsub_url

logger = logging.getLogger("vindex.email_notif")
router = APIRouter(tags=["email_notif"])

_SMTP_HOST   = os.getenv("EMAIL_SMTP_HOST", "")
_SMTP_PORT   = int(os.getenv("EMAIL_SMTP_PORT", "587"))
_SMTP_USER   = os.getenv("EMAIL_SMTP_USER", "")
_SMTP_PASS   = os.getenv("EMAIL_SMTP_PASS", "")
_FROM_ADDR   = os.getenv("EMAIL_FROM", "") or _SMTP_USER

# Operation Lawyer Zero, LZ-001 (2026-08-03) je ovde drzao listu
# ["kritičan","važan","bitan","kljucan","normalan"], uz obrazlozenje da
# `bitan` "verovatno stvarno postoji u produkciji" iako ne odgovara CHECK-u.
# B-U-006 je to IZMERIO i pretpostavka je opovrgnuta: CHECK postoji i radi
# (5/5 pokusaja upisa van skupa palo na 23514), a svih 52 reda u produkciji
# nose iskljucivo kanonske vrednosti. `bitan`/`kljucan`/`normalan` su bili
# mrtvi unosi -- filter je izgledao siri nego sto jeste.
#
# B-U-006: izvedeno iz KANONSKOG domena, ne prepisano rucno.
#
# Ranije je lista glasila ["kritičan","važan","bitan","kljucan","normalan"].
# Poslednje tri vrednosti CHECK u produkciji ODBIJA
# (`vaznost IN ('kritičan','važan','informativan')`, potvrdjeno sondom: svih
# 5 pokusaja upisa van skupa palo je na 23514), pa su bile mrtvi unosi --
# filter je izgledao siri nego sto jeste. Sonda nad svih 52 reda u produkciji:
# informativan 22, kritičan 17, važan 13, nijedna nekanonska vrednost.
#
# INVARIJANTA: alerting ne sme da zavisi od vrednosti koju baza ne moze da
# sadrzi. Izvodjenjem iz `VAZNOST_DOZVOLJENE` lista vise ne moze da se razidje
# sa semom -- ako se domen ikad promeni, menja se na JEDNOM mestu.
from shared.rokovi import VAZNOST_DOZVOLJENE as _VAZNOST_DOZVOLJENE
# FAZA 6.2 (INV-2): `vaznost` je AI procena tezine, NE ovlascenje. AI opazen
# rok sme da posalje email tek kad ga covek potvrdi. Gejt je fail-closed i
# ne dira nijednu postojecu `vaznost` vrednost.
from shared.rokovi import filtriraj_izvrsive as _filtriraj_izvrsive
from shared.rok_potvrda import STANJE_POTVRDJEN as _POTVRDJEN, odluke as _odluke


def _potvrdjeni_ids(rok_ids) -> set:
    """Isti skup kao `shared.rok_potvrda.potvrdjeni_ids`, ali pad čitanja lanca DIŽE izuzetak.

    S2 (Sektor 2): prazan skup pri padu je ovde izgledao kao „nijedan rok nije potvrđen“ — podsetnik je odlazio
    samo sa ročištem, predmet se rezervisao za taj prag i posao je bio zelen, a potvrđen rok je tiho izostao.
    Pozivalac sad zna da potvrde NISU pročitane i to broji kao grešku."""
    return {rid for rid, s in _odluke(rok_ids, strogo=True).items() if s == _POTVRDJEN}


_ACTIONABLE_VAZNOST = [v for v in _VAZNOST_DOZVOLJENE if v != "informativan"]
_CRON_SECRET = os.getenv("CRON_SECRET", "")

_security_opt = HTTPBearer(auto_error=False)


async def _require_cron_or_founder(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security_opt),
) -> dict:
    """FastAPI dep: accepts X-Cron-Key header OR valid founder Bearer JWT."""
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
    raise HTTPException(status_code=403, detail="Restricted to founder or valid cron key.")


# ─── SMTP helper ──────────────────────────────────────────────────────────────

class _NijePredato(Exception):
    """Poruka sigurno NIJE predata provajderu: veza, TLS ili prijava nisu uspeli, pošiljalac/primalac su odbijeni pre
    sadržaja, ili je provajder privremeno (4xx) odbio poruku. Sme da se ponovi (S2, odluka D4)."""


class _Odbijeno(Exception):
    """Provajder je izričito i trajno (5xx) odbio poruku. Ne ponavlja se."""


def _smtp_send(to_addr: str, subject: str, html: str) -> None:
    """Šalje jednu poruku. Uspeh = SMTP 250 posle sadržaja (provajder PRIHVATIO, ne prijem u sanduče).
    `_NijePredato` / `_Odbijeno` su sigurni ishodi; svaki drugi izuzetak (npr. veza pukla posle predaje sadržaja) je
    NEPOZNAT ishod — poruka je možda isporučena i ne sme se slepo ponoviti."""
    if not _SMTP_HOST:
        raise _NijePredato("EMAIL_SMTP_HOST nije konfigurisan.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = _FROM_ADDR
    msg["To"]      = to_addr
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        smtp = smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15)
    except (OSError, smtplib.SMTPException) as exc:
        raise _NijePredato(f"veza: {type(exc).__name__}") from exc
    try:
        try:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(_SMTP_USER, _SMTP_PASS)
        except (OSError, smtplib.SMTPException) as exc:
            raise _NijePredato(f"prijava: {type(exc).__name__}") from exc
        try:
            smtp.sendmail(_FROM_ADDR, [to_addr], msg.as_bytes())
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
            raise _NijePredato(f"odbijen pre sadržaja: {type(exc).__name__}") from exc
        except smtplib.SMTPDataError as exc:
            # Odgovor ≠ 250 na DATA ili posle sadržaja: server je IZRIČITO rekao da poruku nije prihvatio.
            if 400 <= int(exc.smtp_code or 0) < 500:
                raise _NijePredato(f"privremeno odbijeno {exc.smtp_code}") from exc
            raise _Odbijeno(f"odbijeno {exc.smtp_code}") from exc
    finally:
        try:
            smtp.quit()          # pad QUIT-a posle 250 ne menja ishod (poruka je već prihvaćena)
        except Exception:
            try:
                smtp.close()
            except Exception:
                pass


def _email_html(rokovi: list[dict], dana_pre: int, user_id: str = "", email: str = "", test: bool = False,
                rocista: Optional[list] = None, nepotpun: bool = False) -> str:
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
    if rocista:
        # N4: podsetnik sa ročištem ne sme da kaže samo „ističe rok“.
        kada = "<strong>SUTRA</strong>" if dana_pre == 1 else f"za <strong>{dana_pre} dana</strong>"
        naslov = _naslov_podsetnika(dana_pre, bool(rokovi), True).replace("Vindex AI — ", "📅 ")
        opis = (f"Potvrđeni rokovi i zakazana ročišta {kada}:" if rokovi else f"Zakazana ročišta {kada}:")

    rows_html = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#e2e8f0;">'
        f'{html.escape(str(r.get("dogadjaj","Rok")))}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#94a3b8;white-space:nowrap;">'
        f'{html.escape(str(r.get("datum_iso","")))}</td></tr>'
        for r in rokovi
    ) + "".join(
        # N4: ročište u istom podsetniku — sud, sudnica i vreme (sve iz zapisa koji je advokat uneo).
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#e2e8f0;">'
        f'Ročište — {html.escape(str(r.get("sud") or "Sud"))}'
        f'{(", sudnica " + html.escape(str(r.get("sudnica")))) if r.get("sudnica") else ""}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#94a3b8;white-space:nowrap;">'
        f'{html.escape(str(r.get("datum") or ""))}{(" u " + html.escape(str(r.get("vreme"))[:5])) if r.get("vreme") else ""}</td></tr>'
        for r in (rocista or [])
    )

    # S2: jedan izvor (rokovi ili ročišta) nije pročitan — podsetnik ne sme da izgleda potpun.
    upozorenje = (
        '<p style="color:#facc15;font-size:13px;margin:0 0 16px;">Upozorenje: deo podataka za ovaj datum trenutno nije '
        'mogao da se pročita, pa ovaj podsetnik možda nije potpun. Proverite rokove i ročišta u Vindex AI.</p>'
    ) if nepotpun else ""
    unsub = f' <a href="{make_unsub_url(user_id, email)}" style="color:#64748b;">Odjavi se</a>' if user_id and email else ""
    # P0 (B10): primer intervala nosi oznaku TEST i izjavu da rok nije stvaran; zakazani podsetnik je nema.
    oznaka_test = (
        '<div style="background:#facc15;color:#111827;padding:10px 28px;font-size:13px;font-weight:700;">'
        'TEST — primer obaveštenja. Rok i datum su izmišljeni i nemaju pravno dejstvo.</div>'
    ) if test else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  {oznaka_test}
  <div style="background:{boja};padding:20px 28px;">
    <div style="font-size:20px;font-weight:700;color:#fff;">{naslov}</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:4px;">Vindex AI — Pravni Operativni Sistem</div>
  </div>
  <div style="padding:24px 28px;">
    <p style="color:#cbd5e1;font-size:14px;margin:0 0 16px;">{opis}</p>{upozorenje}
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
    <p style="color:#475569;font-size:12px;margin:0;">Prijavili ste se na email podsetnik za rokove u Vindex AI.{unsub}</p>
  </div>
</div>
</body></html>"""


def _naslov_podsetnika(dana_pre: int, ima_rokova: bool = True, ima_rocista: bool = False) -> str:
    """Jedan izvor naslova za zakazani podsetnik i za njegov TEST primer (N4: i za ročišta)."""
    if ima_rocista:
        sta = "rok i ročište" if ima_rokova else "ročište"
        return f"Vindex AI — {'Sutra' if dana_pre == 1 else f'Za {dana_pre} dana'}: {sta}"
    return f"Vindex AI — {'Sutra ističe rok!' if dana_pre == 1 else f'Za {dana_pre} dana — kritični rokovi'}"


def _danas_beograd(sada: Optional[datetime] = None) -> date:
    """Kalendarski dan u Srbiji (CET/CEST po pravilu EU) — bez zavisnosti od tz baze u slim slici."""
    return _beograd(sada or datetime.now(timezone.utc)).date()


def _beograd(sada: datetime) -> datetime:
    """Lokalno vreme u Srbiji (naivno). Letnje vreme: od poslednje nedelje marta 01:00 UTC do poslednje nedelje
    oktobra 01:00 UTC."""
    sada = sada.astimezone(timezone.utc)

    def _poslednja_nedelja(mesec: int) -> datetime:
        d = date(sada.year, mesec, 31)
        d -= timedelta(days=(d.weekday() + 1) % 7)
        return datetime(d.year, d.month, d.day, 1, tzinfo=timezone.utc)

    letnje = _poslednja_nedelja(3) <= sada < _poslednja_nedelja(10)
    return (sada + timedelta(hours=2 if letnje else 1)).replace(tzinfo=None)


# ─── Models ───────────────────────────────────────────────────────────────────

class EmailTestReq(BaseModel):
    """P0 (B10): `interval` bira koji podsetnik se prikazuje kao TEST primer. Bez njega se proverava samo
    dostava (SMTP), bez tvrdnje o bilo kom intervalu. Dozvoljeno isključivo 1, 3 ili 7 (ne bool, ne 3.0)."""
    model_config = ConfigDict(extra="forbid")
    interval: Optional[int] = None

    @field_validator("interval", mode="before")
    @classmethod
    def _samo_1_3_7(cls, v):
        if v is None:
            return v
        if type(v) is not int or v not in (1, 3, 7):
            raise ValueError("interval mora biti 1, 3 ili 7")
        return v


class EmailNotifReq(BaseModel):
    aktivan:  bool = True
    dan_7:    bool = True
    dan_3:    bool = True
    dan_1:    bool = True
    nedeljni: bool = True


def _adresa_primaoca(supa, user_id: str) -> str:
    """TENFRONTS-M10: JEDINI izvor adrese primaoca — `profiles.email` vlasnika (VCR002: „Primalac: isključivo
    vlasnik profila“), isti koji koristi zakazani podsetnik. Adresa iz prijave (JWT) se NE koristi kao
    zamena: oznaka „Šalje se na“ i probni email moraju pokazati/proveriti ono kuda podsetnici stvarno idu."""
    r = supa.table("profiles").select("email").eq("id", user_id).maybe_single().execute()
    return ((r.data or {}).get("email") or "").strip() if r is not None else ""


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
    # TENFRONTS-M02: supabase 2.28.3 `maybe_single().execute()` vraća None kada reda nema → ranije 500,
    # a stari UI je tada tiho ostajao bez stanja. `smtp_ok` je i bez profila istinit (UI njegovo odsustvo
    # čita kao „nije konfigurisan“). Profil se ne kreira; obaveštenja ostaju isključena do uključivanja.
    adresa = await asyncio.to_thread(_adresa_primaoca, supa, user["user_id"]) or None
    if res is None or not res.data:
        return {"aktivan": False, "dan_7": True, "dan_3": True, "dan_1": True, "email": adresa,
                "smtp_ok": bool(_SMTP_HOST)}
    d = res.data
    return {**d, "email": adresa, "smtp_ok": bool(_SMTP_HOST)}


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
async def test_email(request: Request, req: Optional[EmailTestReq] = Body(default=None),
                     user: dict = Depends(get_current_user)):
    """Šalje TEST email na adresu na koju idu podsetnici (`profiles.email`, TENFRONTS-M10).

    P0 (B10): ranije je uvek slat primer „Za 3 dana“ (hardkodovano), bez obzira na izabrani interval.
    - bez `interval`: samo provera dostave — poruka ne prikazuje nijedan rok ni interval;
    - `interval` 1/3/7: primer tačno tog podsetnika (isti naslov i šablon kao zakazani), sa izmišljenim
      rokom na dan Srbija-danas + interval. Interval mora biti uključen u profilu vlasnika.
    Nijedno od ovoga ne dokazuje rad zakazivanja (cron)."""
    interval = req.interval if req else None
    supa = _get_supa()
    to_addr = await asyncio.to_thread(_adresa_primaoca, supa, user["user_id"])
    if not to_addr:
        raise HTTPException(status_code=400, detail="Email adresa nije dostupna.")
    if not _SMTP_HOST:
        raise HTTPException(status_code=503, detail="Email server nije konfigurisan.")

    if interval is None:
        subject = "Vindex AI — TEST: provera dostave email-a"
        html = (
            '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
            '<body style="margin:0;padding:24px;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">'
            '<div style="max-width:560px;margin:0 auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;padding:24px 28px;">'
            '<div style="font-size:18px;font-weight:700;color:#fff;">TEST — provera dostave</div>'
            '<p style="color:#cbd5e1;font-size:14px;">Ova poruka proverava samo da email iz Vindex AI stiže na vašu adresu. '
            'Ne prikazuje nijedan rok ni interval podsetnika.</p></div></body></html>'
        )
    else:
        res = await asyncio.to_thread(
            lambda: supa.table("korisnik_email_notif").select("*")
                         .eq("user_id", user["user_id"]).maybe_single().execute()
        )
        p = (res.data if res is not None else None) or {}
        if not (p.get("aktivan") is True and p.get(f"dan_{interval}") is True):
            raise HTTPException(status_code=409, detail="Izabrani interval nije uključen i sačuvan u podešavanjima.")
        rok = _danas_beograd() + timedelta(days=interval)
        subject = "TEST — " + _naslov_podsetnika(interval)
        html = _email_html(
            [{"dogadjaj": "PRIMER — izmišljen rok bez pravnog dejstva", "datum_iso": rok.isoformat()}],
            dana_pre=interval, test=True,
        )
    try:
        await asyncio.to_thread(_smtp_send, to_addr, subject, html)
    except Exception as exc:
        logger.error("[EMAIL-NOTIF] test greška: %s", exc)
        raise HTTPException(status_code=502, detail=f"Greška pri slanju: {exc}")
    return {"ok": True, "poslato_na": to_addr, "interval": interval}



# ─── Dnevni podsetnici: rezervacija po DOGAĐAJU (Sektor 2, odluke osnivača D1–D6) ─────────────────────────────
#
# Tabela `email_podsetnik_dogadjaj` (migracija 142), ključ (user_id, tip, dogadjaj_id, datum_dogadjaja, svrha):
#   - redovni podsetnik `prag_N` tačno N dana pre (uključeni pragovi profila, D1 — grupisan po korisniku i pragu);
#   - `kasni` (D2): kad nijedan uključen prag više ne može da stigne pre događaja, a najkasniji uključen prag za taj
#     događaj nije poslat (potvrđen/zakazan kasno, ili dnevno slanje izostalo) — jednom po pojavi događaja;
#   - identitet je događaj, ne predmet (D3): rok B istog predmeta i datuma više ne gasi rok A;
#   - sigurno nepredata poruka sme ponovo (najviše _MAX_POKUSAJA), nepoznat ishod NE (D4);
#   - nepotvrđen/odbijen AI rok nikad ne ulazi (D5 — `_filtriraj_izvrsive` + strog lanac potvrda);
#   - `poslato` znači da je SMTP prihvatio poruku, ne da je stigla u sanduče (D6).
# Stari `email_notif_log` (021) se samo ČITA: red koji je stari kod upisao pokriva događaj predmeta koji je bio izvršiv
# pre tog slanja; kasnije izvršiv događaj nije mogao biti u tom emailu i ne smatra se pokrivenim.

_TABELA_DOGADJAJA = "email_podsetnik_dogadjaj"
_TABELA_POKRETANJA = "email_podsetnik_pokretanje"
_PRAGOVI = (1, 3, 7)
_MAX_POKUSAJA = 3
_ZAUZETO = ("rezervisano", "poslato", "nepoznato", "odbijeno")   # predato, možda predato ili trajno odbijeno
_REDOSLED_SVRHA = ("prag_7", "prag_3", "prag_1", "kasni")


def _sada() -> datetime:
    return datetime.now(timezone.utc)


def _je_dup(exc: Exception) -> bool:
    t = str(exc)
    return "23505" in t or "duplicate key" in t.lower()


def _nema_tabele(exc: Exception) -> bool:
    t = str(exc)
    return "42P01" in t or "PGRST205" in t or ("does not exist" in t and _TABELA_POKRETANJA in t)


def _kao_datum(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _kao_trenutak(v) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _vreme_rocista(v):
    try:
        hh, mm = str(v).split(":")[:2]
        return int(hh), int(mm)
    except (TypeError, ValueError):
        return None


def _predstoji_danas(ev: dict, sada_bg: datetime) -> bool:
    """Događaj DANAS: rok (samo datum) ističe na kraju dana → još predstoji. Ročište sa vremenom predstoji samo pre
    tog vremena; ročište BEZ vremena se ne šalje — ne može se utvrditi da nije već održano (vreme se ne izmišlja)."""
    if ev["tip"] == "rok":
        return True
    hm = _vreme_rocista(ev["red"].get("vreme")) if ev["red"].get("vreme") else None
    return hm is not None and (sada_bg.hour, sada_bg.minute) < hm


def _aktivni_predmeti(supa, uid: str) -> set:
    # Operation Living System: arhiviran/zatvoren/odbijen predmet se ne podseća. VCR002 T04: predmet u brisanju
    # (tombstone, migracija 114) se ponaša kao da ne postoji. T07: rezervni upit (bez kolone) SAMO pre migracije 114.
    try:
        r = supa.table("predmeti").select("id,brisanje_zapoceto").eq("user_id", uid) \
            .not_.in_("status", ["zatvoren", "arhiviran", "odbijen"]).execute()
    except Exception as exc:
        _t = str(exc)
        if not ("42703" in _t or ("brisanje_zapoceto" in _t and "does not exist" in _t)):
            raise
        r = supa.table("predmeti").select("id").eq("user_id", uid) \
            .not_.in_("status", ["zatvoren", "arhiviran", "odbijen"]).execute()
    return {p["id"] for p in (r.data or []) if not p.get("brisanje_zapoceto")}


def _dogadjaji(supa, uid: str, aktivni: set, od: date, do: date):
    """(događaji, nesigurni_predmeti). Izuzetak ako rokovi ili ročišta NISU pročitani (pozivalac ne rezerviše ništa).
    Pad lanca potvrda: predmeti sa kandidat-rokom su NESIGURNI i ne šalju se (nijedan njihov događaj)."""
    rokovi_r = (supa.table("predmet_hronologija")
                # Migracija 127: gejt traži `id` (ključ odluke) i `izvor`; `akter` nije poreklo.
                .select("id, izvor, dogadjaj, datum_iso, predmet_id, created_at")
                .eq("user_id", uid).in_("vaznost", _ACTIONABLE_VAZNOST)
                .gte("datum_iso", od.isoformat()).lte("datum_iso", do.isoformat()).execute())
    rocista_r = (supa.table("rocista").select("id, predmet_id, sud, sudnica, datum, vreme, status, created_at, updated_at")
                 .eq("user_id", uid).gte("datum", od.isoformat()).lte("datum", do.isoformat()).execute())
    rokovi = [r for r in (rokovi_r.data or []) if r.get("predmet_id") in aktivni]
    nesigurni: set = set()
    try:
        # INV-2 / FAZA 6.4.2: NIJEDAN nepotvrđen rok ne šalje email — ni AI ni ručno unet (poreklo ne ovlašćuje).
        rokovi = _filtriraj_izvrsive(rokovi, _potvrdjeni_ids([r.get("id") for r in rokovi]))
    except Exception as exc:
        logger.error("[EMAIL-CRON] potvrde rokova nisu pročitane uid=%.8s: %s", uid, type(exc).__name__)
        nesigurni = {r.get("predmet_id") for r in rokovi}
        rokovi = []
    out = []
    for r in rokovi:
        d = _kao_datum(r.get("datum_iso"))
        if d:
            out.append({"tip": "rok", "id": str(r.get("id")), "predmet_id": r.get("predmet_id"), "datum": d, "red": r})
    for r in (rocista_r.data or []):
        # N4: samo ZAKAZANO ročište; otkazano/odloženo/održano ne šalje.
        if r.get("predmet_id") not in aktivni or r.get("predmet_id") in nesigurni \
                or (r.get("status") or "zakazano") != "zakazano":
            continue
        d = _kao_datum(r.get("datum"))
        if d:
            out.append({"tip": "rociste", "id": str(r.get("id")), "predmet_id": r.get("predmet_id"), "datum": d, "red": r})
    return out, nesigurni


def _postojece_rezervacije(supa, uid: str, od: date) -> dict:
    r = (supa.table(_TABELA_DOGADJAJA).select("id, tip, dogadjaj_id, datum_dogadjaja, svrha, stanje, pokusaja, "
                                              "rezervisano_at, azurirano_at")
         .eq("user_id", uid).gte("datum_dogadjaja", od.isoformat()).execute())
    return {(x.get("tip"), str(x.get("dogadjaj_id")), str(x.get("datum_dogadjaja"))[:10], x.get("svrha")): x
            for x in (r.data or [])}


def _stari_dnevnik(supa, uid: str, od: date) -> dict:
    r = (supa.table("email_notif_log").select("predmet_id, datum_roka, dana_pre, poslato_at")
         .eq("user_id", uid).gte("datum_roka", od.isoformat()).in_("dana_pre", list(_PRAGOVI)).execute())
    return {(str(x.get("predmet_id")), str(x.get("datum_roka"))[:10], int(x.get("dana_pre") or 0)): x.get("poslato_at")
            for x in (r.data or [])}


def _vremena_potvrda(rok_ids: list) -> dict:
    """Poslednja potvrda po roku (vreme iz lanca). Pad DIŽE izuzetak — ranije je prazan rezultat značio „pokriveno“
    i rok potvrđen posle starog slanja je tiho izostajao (revizija S2-F, F3)."""
    if not rok_ids:
        return {}
    from shared.rok_potvrda import AKCIJA_POTVRDA, procitaj_lanac
    out = {}
    for red in procitaj_lanac(rok_ids, "action, resource_id, seq, created_at"):
        if red.get("action") == AKCIJA_POTVRDA:
            out[str(red.get("resource_id"))] = red.get("created_at")
    return out


def _pokriva_stari_red(ev: dict, prag: int, stari: dict, potvrde: dict) -> bool:
    """Stari red (predmet, datum, prag) pokriva događaj koji je bio izvršiv PRE tog slanja. Nepoznato vreme bilo koje
    strane → pokriveno (bez duplikata; kao do sada). Kasnije izvršiv događaj NIJE mogao biti u tom emailu."""
    kljuc = (str(ev["predmet_id"]), ev["datum"].isoformat(), prag)
    if kljuc not in stari:
        return False
    poslato_at = _kao_trenutak(stari[kljuc])
    od = _kao_trenutak(ev["red"].get("created_at"))
    if ev["tip"] == "rociste":
        # Pomeranje i vraćanje (otkazano → zakazano) menjaju red na mestu: `created_at` ostaje star, a ročište na ovom
        # datumu/u ovom stanju postoji tek od `updated_at` (revizija S2-F, F1). Kozmetička izmena posle starog slanja
        # daje najviše jedan suvišan podsetnik — bolje nego tiho izgubljen.
        izm = _kao_trenutak(ev["red"].get("updated_at"))
        if od and izm:
            od = max(od, izm)
    if ev["tip"] == "rok":
        p = _kao_trenutak(potvrde.get(ev["id"]))
        od = max(od, p) if (od and p) else None
    if poslato_at is None or od is None:
        return True
    return od <= poslato_at


def _svrha(ev: dict, danas: date, sada_bg: datetime, pragovi: list, vec_poslato, samo_hitno: bool,
           dnevno_proslo: bool) -> Optional[str]:
    """Koja poruka (ako ijedna) sada pripada događaju. `vec_poslato(ev, svrha)`."""
    d = (ev["datum"] - danas).days
    if d < 0 or (d == 0 and not _predstoji_danas(ev, sada_bg)):
        return None
    if d in pragovi:
        # Hitna provera ne preteče dnevno slanje: današnji prag šalje odmah samo ako je dnevno slanje već prošlo.
        return f"prag_{d}" if (dnevno_proslo or not samo_hitno) else None
    najkasniji = min(pragovi)
    # Već poslat prag bliži od (ili jednak) najkasnijem uključenom pokriva događaj i posle promene pragova (F4).
    if d < najkasniji and not vec_poslato(ev, "kasni") \
            and not any(vec_poslato(ev, f"prag_{m}") for m in _PRAGOVI if m <= najkasniji):
        return "kasni"
    return None


def _koliko(ev: dict, danas: date) -> str:
    d = (ev["datum"] - danas).days
    if d == 0:
        return "DANAS"
    return "SUTRA" if d == 1 else f"za {d} dana"


def _email_html_kasni(stavke: list, danas: date, user_id: str = "", email: str = "", nepotpun: bool = False) -> str:
    """Dodatni podsetnik (D2): događaj potvrđen ili zakazan kasno — svaka stavka sa STVARNIM brojem dana."""
    redovi = []
    for ev in sorted(stavke, key=lambda e: (e["datum"], e["tip"])):
        r = ev["red"]
        if ev["tip"] == "rok":
            opis = html.escape(str(r.get("dogadjaj") or "Rok"))
            kada = f"{html.escape(ev['datum'].isoformat())} — ističe {_koliko(ev, danas)}"
        else:
            opis = f'Ročište — {html.escape(str(r.get("sud") or "Sud"))}' + (
                f', sudnica {html.escape(str(r.get("sudnica")))}' if r.get("sudnica") else "")
            kada = f"{html.escape(ev['datum'].isoformat())}" + (
                f' u {html.escape(str(r.get("vreme"))[:5])}' if r.get("vreme") else "") + f" — {_koliko(ev, danas)}"
        redovi.append(f'<tr><td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#e2e8f0;">{opis}</td>'
                      f'<td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:#94a3b8;">{kada}</td></tr>')
    upozorenje = ('<p style="color:#facc15;font-size:13px;margin:0 0 16px;">Upozorenje: deo podataka za ovaj datum '
                  'trenutno nije mogao da se pročita, pa ovaj podsetnik možda nije potpun. Proverite rokove i ročišta '
                  'u Vindex AI.</p>') if nepotpun else ""
    unsub = f' <a href="{make_unsub_url(user_id, email)}" style="color:#64748b;">Odjavi se</a>' if user_id and email else ""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:#ef4444;padding:20px 28px;">
    <div style="font-size:20px;font-weight:700;color:#fff;">Podsetnik: potvrđeno ili zakazano posle redovnog podsetnika</div>
    <div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:4px;">Vindex AI — Pravni Operativni Sistem</div>
  </div>
  <div style="padding:24px 28px;">
    <p style="color:#cbd5e1;font-size:14px;margin:0 0 16px;">Redovni podsetnik za ove događaje više ne može da stigne pre njih:</p>{upozorenje}
    <table style="width:100%;border-collapse:collapse;background:#0d1b2a;border-radius:8px;overflow:hidden;"><tbody>{"".join(redovi)}</tbody></table>
    <div style="margin-top:20px;text-align:center;">
      <a href="https://vindex.rs" style="display:inline-block;padding:10px 24px;background:#ef4444;color:#fff;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;">Otvori Vindex AI →</a>
    </div>
  </div>
  <div style="padding:14px 28px;border-top:1px solid #1e293b;">
    <p style="color:#475569;font-size:12px;margin:0;">Prijavili ste se na email podsetnik za rokove u Vindex AI.{unsub}</p>
  </div>
</div>
</body></html>"""


def _naslov_kasnog(stavke: list) -> str:
    ima_rok = any(e["tip"] == "rok" for e in stavke)
    ima_roc = any(e["tip"] == "rociste" for e in stavke)
    sta = "rok i ročište" if (ima_rok and ima_roc) else ("ročište" if ima_roc else "rok")
    return f"Vindex AI — Podsetnik: {sta} uskoro"


def _rezervisi(supa, uid: str, ev: dict, svrha: str, postojeci: dict) -> tuple:
    """('da', id) | ('vec', None) | ('iscrpljeno', None) | ('trka', None) | ('greska', None)."""
    kljuc = (ev["tip"], ev["id"], ev["datum"].isoformat(), svrha)
    red = postojeci.get(kljuc)
    sada = _sada().isoformat()
    if red is not None:
        if red.get("stanje") != "neuspeh":
            return ("vec", None)
        pokusaja = int(red.get("pokusaja") or 1)
        if pokusaja >= _MAX_POKUSAJA:
            return ("iscrpljeno", None)
        try:
            # Uslovno: samo ako je red i dalje `neuspeh` sa istim brojem pokušaja — drugi proces ne može isto.
            r = (supa.table(_TABELA_DOGADJAJA)
                 .update({"stanje": "rezervisano", "pokusaja": pokusaja + 1, "greska": None, "azurirano_at": sada})
                 .eq("id", red["id"]).eq("stanje", "neuspeh").eq("pokusaja", pokusaja).execute())
        except Exception as exc:
            logger.error("[EMAIL-CRON] ponovna rezervacija neuspešna uid=%.8s: %s", uid, type(exc).__name__)
            return ("greska", None)
        return ("da", red["id"]) if (r.data or []) else ("trka", None)
    nov_id = str(uuid.uuid4())
    try:
        supa.table(_TABELA_DOGADJAJA).insert({
            "id": nov_id, "user_id": uid, "predmet_id": str(ev["predmet_id"]), "tip": ev["tip"],
            "dogadjaj_id": ev["id"], "datum_dogadjaja": ev["datum"].isoformat(), "svrha": svrha,
            "stanje": "rezervisano", "pokusaja": 1, "rezervisano_at": sada, "azurirano_at": sada,
        }).execute()
    except Exception as exc:
        if _je_dup(exc):
            return ("trka", None)
        logger.error("[EMAIL-CRON] rezervacija neuspešna uid=%.8s: %s", uid, type(exc).__name__)
        return ("greska", None)
    return ("da", nov_id)


def _zabelezi_ishod(supa, ids: list, stanje: str, greska: Optional[str] = None) -> bool:
    try:
        (supa.table(_TABELA_DOGADJAJA)
         .update({"stanje": stanje, "greska": (greska or None) and str(greska)[:200], "azurirano_at": _sada().isoformat()})
         .in_("id", ids).eq("stanje", "rezervisano").execute())
        return True
    except Exception as exc:
        # Red ostaje `rezervisano` = nepoznat ishod: ne ponavlja se (nema duplikata), ali se ne tvrdi ni uspeh.
        logger.error("[EMAIL-CRON] ishod slanja NIJE zabeležen (%s): %s", stanje, type(exc).__name__)
        return False


def _novi_brojaci() -> dict:
    return {"poslato": 0, "greske": 0, "preskoceno": 0, "neisporuceno": 0, "kasni": 0, "zaostalo_nepoznato": 0}


def _zaostali_ishodi(postojeci: dict, od: Optional[datetime], do: datetime) -> int:
    """Ishodi koje NIJE prijavilo dnevno slanje (hitna provera ili prekinut proces) od prethodnog dnevnog slanja:
    `nepoznato`, i `rezervisano` starije od 15 min (proces prekinut posred slanja). Ne ponavljaju se (D4), ali posao
    ne sme da bude zelen dok ih niko nije video (revizija S2-F, F2)."""
    if od is None:
        return 0
    n = 0
    for red in postojeci.values():
        if red.get("stanje") == "nepoznato":
            t = _kao_trenutak(red.get("azurirano_at"))
            n += bool(t and od < t <= do)
        elif red.get("stanje") == "rezervisano":
            t = _kao_trenutak(red.get("rezervisano_at"))
            n += bool(t and od < t <= do - timedelta(minutes=15))
    return n


def _obradi_korisnika(supa, profil: dict, to_addr: str, danas: date, sada_bg: datetime, n: dict,
                      samo_hitno: bool = False, dnevno_proslo: bool = True,
                      prethodno_slanje: Optional[datetime] = None, sada: Optional[datetime] = None) -> None:
    uid = profil["user_id"]
    pragovi = [p for p in _PRAGOVI if profil.get(f"dan_{p}")]
    if not pragovi:
        return
    try:
        aktivni = _aktivni_predmeti(supa, uid)
    except Exception as exc:
        logger.error("[EMAIL-CRON] aktivni predmeti nisu pročitani uid=%.8s: %s", uid, type(exc).__name__)
        n["greske"] += 1
        return
    if not aktivni:
        return
    do = danas + timedelta(days=max(pragovi))
    try:
        dogadjaji, nesigurni = _dogadjaji(supa, uid, aktivni, danas, do)
        # 7 dana unazad: nepoznat ishod za događaj koji je u međuvremenu prošao mora i dalje da se prijavi (F2).
        postojeci = _postojece_rezervacije(supa, uid, danas - timedelta(days=7))
        stari = _stari_dnevnik(supa, uid, danas)
        potvrde = _vremena_potvrda([e["id"] for e in dogadjaji if e["tip"] == "rok"
                                    and any((str(e["predmet_id"]), e["datum"].isoformat(), p) in stari for p in _PRAGOVI)])
    except Exception as exc:
        # Nijedan događaj ovog korisnika se ne rezerviše dok svi izvori nisu pročitani (S2-E F1) → ponovno slanje šalje sve.
        logger.error("[EMAIL-CRON] izvori nisu pročitani, korisnik preskočen bez rezervacije uid=%.8s: %s",
                     uid, type(exc).__name__)
        n["greske"] += 1
        return
    if nesigurni:
        n["greske"] += 1
    if not samo_hitno and sada is not None:
        z = _zaostali_ishodi(postojeci, prethodno_slanje, sada)
        n["neisporuceno"] += z
        n["zaostalo_nepoznato"] += z

    def vec_poslato(ev, svrha):
        red = postojeci.get((ev["tip"], ev["id"], ev["datum"].isoformat(), svrha))
        if red is not None and red.get("stanje") in _ZAUZETO:
            return True
        return svrha.startswith("prag_") and _pokriva_stari_red(ev, int(svrha[5:]), stari, potvrde)

    grupe: dict = {}
    for ev in dogadjaji:
        s = _svrha(ev, danas, sada_bg, pragovi, vec_poslato, samo_hitno, dnevno_proslo)
        if s is None or (s.startswith("prag_") and _pokriva_stari_red(ev, int(s[5:]), stari, potvrde)):
            continue
        red = postojeci.get((ev["tip"], ev["id"], ev["datum"].isoformat(), s))
        if red is not None and red.get("stanje") in _ZAUZETO:
            continue                                        # već predato / možda predato / trajno odbijeno
        grupe.setdefault(s, []).append(ev)
    if not grupe:
        return
    # T06: poznat ne-pokušaj (nema adrese / SMTP nije konfigurisan) je GREŠKA bez rezervacije.
    if not to_addr or not _SMTP_HOST:
        logger.error("[EMAIL-CRON] slanje nemoguće (%s), rezervacija NIJE upisana uid=%.8s",
                     "nema adrese" if not to_addr else "SMTP nije konfigurisan", uid)
        n["greske"] += 1
        return

    for svrha in _REDOSLED_SVRHA:
        if svrha not in grupe:
            continue
        rezervisani, ids, pad = [], [], False
        for ev in grupe[svrha]:
            ishod, rid = _rezervisi(supa, uid, ev, svrha, postojeci)
            if ishod == "da":
                rezervisani.append(ev)
                ids.append(rid)
            elif ishod == "trka":
                n["preskoceno"] += 1
            elif ishod in ("greska", "iscrpljeno"):
                pad = True
        if pad:
            n["greske"] += 1
        if not rezervisani:
            continue
        if svrha == "kasni":
            subject = _naslov_kasnog(rezervisani)
            telo = _email_html_kasni(rezervisani, danas, user_id=uid, email=to_addr, nepotpun=bool(nesigurni))
        else:
            dana_pre = int(svrha[5:])
            rokovi = [e["red"] for e in rezervisani if e["tip"] == "rok"]
            rocista = [e["red"] for e in rezervisani if e["tip"] == "rociste"]
            subject = _naslov_podsetnika(dana_pre, bool(rokovi), bool(rocista))
            telo = _email_html(rokovi, dana_pre, user_id=uid, email=to_addr, rocista=rocista, nepotpun=bool(nesigurni))
        try:
            _smtp_send(to_addr, subject, telo)
        except _NijePredato as exc:
            logger.error("[EMAIL-CRON] poruka NIJE predata (biće ponovljena) uid=%.8s svrha=%s: %s", uid, svrha, exc)
            _zabelezi_ishod(supa, ids, "neuspeh", str(exc))
            n["greske"] += 1
            continue
        except _Odbijeno as exc:
            logger.error("[EMAIL-CRON] provajder ODBIO poruku uid=%.8s svrha=%s: %s", uid, svrha, exc)
            _zabelezi_ishod(supa, ids, "odbijeno", str(exc))
            n["greske"] += 1
            continue
        except Exception as exc:
            # Ishod NEPOZNAT (npr. veza pukla posle predaje sadržaja): ne ponavlja se, ne tvrdi se uspeh.
            logger.error("[EMAIL-CRON] NEISPORUČENO (ishod nepoznat, bez ponavljanja) uid=%.8s svrha=%s: %s",
                         uid, svrha, type(exc).__name__)
            _zabelezi_ishod(supa, ids, "nepoznato", type(exc).__name__)
            n["neisporuceno"] += 1
            continue
        n["poslato"] += 1
        if svrha == "kasni":
            n["kasni"] += 1
        if not _zabelezi_ishod(supa, ids, "poslato"):
            n["greske"] += 1
        logger.info("[EMAIL-CRON] poslato uid=%.8s svrha=%s stavki=%d", uid, svrha, len(rezervisani))


@router.post("/email-notif/send-reminders")
@limiter.limit("10/minute")
async def posalji_podsetnike(request: Request, user: dict = Depends(_require_cron_or_founder)):
    """
    Cron trigger — dnevni email podsetnici za potvrđene rokove i zakazana ročišta (pragovi 7/3/1) i dodatni
    podsetnik za događaje kojima redovni više ne stiže. Dostupno: founder račun ILI X-Cron-Key header.
    Brojači (ugovor email-cron.yml): poslato = emailova koje je SMTP prihvatio; greske = nije poslato (ponavlja se gde
    je bezbedno); preskoceno = drugi proces je već rezervisao; neisporuceno = ishod nepoznat (ručna provera).
    """
    supa = _get_supa()

    def _run():
        sada = _sada()
        sada_bg = _beograd(sada)
        danas = sada_bg.date()
        n = _novi_brojaci()
        try:
            supa.table(_TABELA_POKRETANJA).insert({"dan": danas.isoformat(), "pokrenuto_at": sada.isoformat()}).execute()
        except Exception as exc:
            if _nema_tabele(exc):
                logger.error("[EMAIL-CRON] migracija 142 nije primenjena — podsetnici NISU poslati")
                return {**n, "greske": 1, "napomena": "Migracija 142 nije primenjena — podsetnici nisu poslati"}
            if not _je_dup(exc):
                logger.warning("[EMAIL-CRON] oznaka dnevnog slanja nije upisana: %s", type(exc).__name__)
        # Kraj prethodnog dnevnog slanja (ranijeg dana): ishodi posle njega koje dnevno slanje nije videlo se prijavljuju.
        prethodno = None
        try:
            for m in (supa.table(_TABELA_POKRETANJA).select("dan, pokrenuto_at, zavrseno_at").execute().data or []):
                # Završeno slanje (i ranije današnje, ručno ponovljeno); nezavršeno samo ranijeg dana — nikad ovo, u toku.
                if m.get("zavrseno_at"):
                    t = _kao_trenutak(m.get("zavrseno_at"))
                elif str(m.get("dan"))[:10] < danas.isoformat():
                    t = _kao_trenutak(m.get("pokrenuto_at"))
                else:
                    t = None
                if t and t <= sada and (prethodno is None or t > prethodno):
                    prethodno = t
        except Exception as exc:
            logger.warning("[EMAIL-CRON] prethodno dnevno slanje nije pročitano: %s", type(exc).__name__)
        if prethodno is None:
            prethodno = sada - timedelta(days=1)

        profili_r = supa.table("korisnik_email_notif").select("*").eq("aktivan", True).execute()
        profili = profili_r.data or []
        if not profili:
            # Isti brojači kao uobičajen odgovor — cron (email-cron.yml) odbija odgovor bez njih.
            return {**n, "napomena": "Nema aktivnih profila"}
        emails_r = supa.table("profiles").select("id, email").execute()
        email_map = {str(p["id"]): p.get("email", "") for p in (emails_r.data or [])}
        for profil in profili:
            _obradi_korisnika(supa, profil, email_map.get(profil["user_id"], ""), danas, sada_bg, n,
                              prethodno_slanje=prethodno, sada=sada)
        try:
            supa.table(_TABELA_POKRETANJA).update({"zavrseno_at": _sada().isoformat()}).eq("dan", danas.isoformat()).execute()
        except Exception as exc:
            logger.warning("[EMAIL-CRON] kraj dnevnog slanja nije upisan: %s", type(exc).__name__)
        return n

    return await asyncio.to_thread(_run)


def proveri_hitne_podsetnike(uid: str) -> dict:
    """Hitna provera posle advokatove radnje (potvrda/ispravka roka, zakazano/izmenjeno ročište) — D2.

    Pokreće se KAO POZADINSKI ZADATAK posle odgovora: radnja je već sačuvana i ne čeka SMTP. Šalje samo ono što ne sme
    da čeka sledeće dnevno slanje: `kasni`, i današnji prag ako je današnje dnevno slanje već prošlo. Isti ključevi kao
    dnevno slanje → nema duplikata ni u trci. Samo za `uid` pozivaoca (ruta je već proverila vlasništvo)."""
    n = _novi_brojaci()
    try:
        supa = _get_supa()
        sada = _sada()
        sada_bg = _beograd(sada)
        danas = sada_bg.date()
        r = supa.table("korisnik_email_notif").select("*").eq("user_id", uid).eq("aktivan", True).execute()
        profil = (r.data or [None])[0]
        if not profil:
            return n
        try:
            m = supa.table(_TABELA_POKRETANJA).select("dan").eq("dan", danas.isoformat()).execute()
            dnevno_proslo = bool(m.data)
        except Exception:
            dnevno_proslo = True     # bez oznake: pošalji odmah — isti ključ sprečava duplikat sa dnevnim slanjem
        _obradi_korisnika(supa, profil, _adresa_primaoca(supa, uid), danas, sada_bg, n,
                          samo_hitno=True, dnevno_proslo=dnevno_proslo)
    except Exception as exc:
        logger.error("[EMAIL-HITNO] provera nije izvršena uid=%.8s: %s", uid, type(exc).__name__)
        n["greske"] += 1
    if any(n[k] for k in ("poslato", "greske", "neisporuceno")):
        logger.info("[EMAIL-HITNO] uid=%.8s %s", uid, n)
    return n


# ─── Weekly Digest ────────────────────────────────────────────────────────────

def _weekly_digest_html(
    user_name: str,
    rokovi: list[dict],
    rocista: list[dict],
    aktivnih: int,
    neplaceno_rsd: float,
    hitnih: int,
    user_id: str = "",
    email: str = "",
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
            f'{tip} — {html.escape(str(r.get("dogadjaj", r.get("sud", "Dogadjaj"))))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #1e293b;color:{boja};white-space:nowrap;font-weight:600;">'
            f'{html.escape(str(r.get("datum_iso", r.get("datum", ""))))}</td></tr>'
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
    user_name_safe = html.escape(str(user_name or ""))

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#1e3a5f,#0d2744);padding:24px 28px;">
    <div style="font-size:13px;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Vindex AI — Nedeljni sažetak</div>
    <div style="font-size:22px;font-weight:700;color:#fff;">Dobro jutro, {user_name_safe}! 👋</div>
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
    <p style="color:#475569;font-size:12px;margin:0;">Nedeljni sažetak stiže svakog ponedeljka.{"  <a href='" + make_unsub_url(user_id, email) + "' style='color:#64748b;'>Odjavi se</a>" if user_id and email else ""}</p>
  </div>
</div>
</body></html>"""


@router.post("/email-notif/nedeljni-sazetak")
@limiter.limit("10/minute")
async def posalji_nedeljni_sazetak(request: Request, user: dict = Depends(_require_cron_or_founder)):
    """
    Cron trigger (ponedeljak 07:00) — šalje nedeljni sažetak svim korisnicima.
    Dostupno: founder ILI X-Cron-Key header.
    """

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

            # Final Beta Gate F27 (MEDIUM): neither query below filtered by
            # predmeti.status -- a case closed today still showed up in next
            # Monday's digest email listing its hearing/deadline next week,
            # the same trust-damaging bug class posalji_podsetnike (the
            # DAILY reminder, ~200 lines up in this same file) was already
            # fixed for. Same aktivni_ids idiom, applied here for the first
            # time. Skips both queries entirely (no `.in_("predmet_id", [])`
            # edge case) when the user has zero active cases -- billing/
            # other digest content is unaffected either way.
            _aktivni_r = supa.table("predmeti").select("id").eq("user_id", uid) \
                .not_.in_("status", ["zatvoren", "arhiviran", "odbijen"]).execute()
            _aktivni_ids = [p["id"] for p in (_aktivni_r.data or [])]

            # Fetch this user's deadlines for the next 7 days
            if _aktivni_ids:
                rokovi_r  = (supa.table("predmet_hronologija")
                                 .select("id,izvor,dogadjaj,datum_iso,vaznost,predmet_id")
                                 .eq("user_id", uid)
                                 .in_("predmet_id", _aktivni_ids)
                                 .gte("datum_iso", today_iso)
                                 .lte("datum_iso", in_7)
                                 .order("datum_iso")
                                 .limit(20)
                                 .execute())
                rocista_r = (supa.table("rocista")
                                 .select("sud,datum,vreme,status")
                                 .eq("user_id", uid)
                                 .in_("predmet_id", _aktivni_ids)
                                 .gte("datum", today_iso)
                                 .lte("datum", in_7)
                                 .order("datum")
                                 .limit(10)
                                 .execute())
            else:
                rokovi_r = types.SimpleNamespace(data=[])
                rocista_r = types.SimpleNamespace(data=[])
            billing_r = (supa.table("billing_entries")
                             .select("iznos_rsd")
                             .eq("user_id", uid)
                             .eq("obracunato", False)
                             .execute())
            if _aktivni_ids:
                hitnih_r  = (supa.table("predmet_hronologija")
                                 .select("id,izvor,predmet_id")
                                 .eq("user_id", uid)
                                 .in_("predmet_id", _aktivni_ids)
                                 .eq("vaznost", "kritičan")
                                 .gte("datum_iso", today_iso)
                                 .lte("datum_iso", in_7)
                                 .execute())
            else:
                hitnih_r = types.SimpleNamespace(data=[])

            # INV-2: isti gejt kao na send-reminders putu -- nedeljni pregled je
            # takodje email koji odlazi advokatu, pa nepotvrdjen AI rok ne sme
            # ni u njega, ni u brojac "hitnih". Jedan upit pokriva oba skupa.
            _kandidati = list(rokovi_r.data or []) + list(hitnih_r.data or [])
            try:
                _potvrdjeni = _potvrdjeni_ids([r.get("id") for r in _kandidati])
            except Exception:
                _potvrdjeni = set()      # nepromenjeno ponašanje pregleda: nepročitana potvrda = nijedan rok
            rokovi     = _filtriraj_izvrsive(rokovi_r.data or [], _potvrdjeni)
            # N4: otkazano / odloženo / održano ročište ne ide u nedeljni pregled kao predstojeće.
            rocista    = [{"datum_iso": r.get("datum", ""), "dogadjaj": r.get("sud", "Sud"), "tip": "rociste"} for r in (rocista_r.data or [])
                          if (r.get("status") or "zakazano") == "zakazano"]
            neplaceno  = sum(float(r.get("iznos_rsd", 0) or 0) for r in (billing_r.data or []))
            hitnih     = len(set(r.get("predmet_id")
                                 for r in _filtriraj_izvrsive(hitnih_r.data or [], _potvrdjeni)))
            aktivnih   = aktivan_by_uid.get(uid, 0)
            user_name  = (profil_data.get("full_name") or to_addr.split("@")[0] or "").title()

            html    = _weekly_digest_html(user_name, rokovi, rocista, aktivnih, neplaceno, hitnih, user_id=uid, email=to_addr)
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


# ─── Onboarding email sekvenca ────────────────────────────────────────────────

_APP_URL = "https://vindex.rs"

def _onboarding_welcome_html(email: str, user_id: str = "") -> str:
    ime = html.escape(email.split("@")[0].replace(".", " ").title())
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#1e3a5f,#0d2744);padding:28px;">
    <div style="font-size:11px;color:rgba(255,255,255,0.45);text-transform:uppercase;letter-spacing:.12em;margin-bottom:10px;">Vindex AI</div>
    <div style="font-size:24px;font-weight:700;color:#fff;font-family:Georgia,serif;">Dobrodošli, {ime}!</div>
    <div style="font-size:14px;color:rgba(255,255,255,0.65);margin-top:6px;">Vaš pravni AI asistent je spreman.</div>
  </div>
  <div style="padding:28px;">
    <p style="color:#cbd5e1;font-size:14px;margin:0 0 20px;line-height:1.6;">
      Upravo ste aktivirali <strong style="color:#4aa8ff;">15 besplatnih AI upita</strong> — bez kreditne kartice, bez obaveza.
      Vindex AI čita zakon, analizira dokumente i predlaže strategiju — sve u jednom mestu.
    </p>
    <div style="background:#0d1b2a;border:1px solid #1e3a5f;border-radius:10px;padding:18px;margin-bottom:20px;">
      <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.08em;font-weight:600;margin-bottom:12px;">Počnite ovde — 3 koraka</div>
      <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;">
        <div style="min-width:28px;height:28px;background:#1e3a5f;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#4aa8ff;">1</div>
        <div><div style="color:#e2e8f0;font-size:13px;font-weight:600;">Otvorite predmet</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">Unesite naziv i tip vaše parnice ili savetodavnog predmeta.</div></div>
      </div>
      <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;">
        <div style="min-width:28px;height:28px;background:#1e3a5f;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#4aa8ff;">2</div>
        <div><div style="color:#e2e8f0;font-size:13px;font-weight:600;">Postavite pravno pitanje</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">AI przoruje važeće zakone i vraća konkretan odgovor sa izvorom.</div></div>
      </div>
      <div style="display:flex;align-items:flex-start;gap:12px;">
        <div style="min-width:28px;height:28px;background:#1e3a5f;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#4aa8ff;">3</div>
        <div><div style="color:#e2e8f0;font-size:13px;font-weight:600;">Analizirajte dokument</div><div style="color:#94a3b8;font-size:12px;margin-top:2px;">Uploadujte ugovor ili tužbu — dobijate pravni revizorski izveštaj.</div></div>
      </div>
    </div>
    <div style="text-align:center;margin-bottom:20px;">
      <a href="{_APP_URL}" style="display:inline-block;padding:13px 32px;background:linear-gradient(135deg,#4aa8ff,#2563eb);color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;letter-spacing:.02em;">Otvorite Vindex AI →</a>
    </div>
    <div style="background:rgba(74,168,255,0.08);border:1px solid rgba(74,168,255,0.2);border-radius:8px;padding:12px 16px;">
      <span style="color:#4aa8ff;font-size:13px;font-weight:600;">15 besplatnih AI upita aktivirano</span>
      <span style="color:#64748b;font-size:12px;"> — bez kreditne kartice.</span>
    </div>
  </div>
  <div style="padding:14px 28px;border-top:1px solid #1e293b;">
    <p style="color:#475569;font-size:12px;margin:0;">Registrovali ste se na Vindex AI. Imate pitanje? Odgovorite na ovaj email.{"  <a href='" + make_unsub_url(user_id, email) + "' style='color:#64748b;'>Odjavi se</a>" if user_id else ""}</p>
  </div>
</div>
</body></html>"""


def _onboarding_day1_html(email: str, user_id: str = "") -> str:
    ime = html.escape(email.split("@")[0].replace(".", " ").title())
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#0f4c2a,#0d2744);padding:24px 28px;">
    <div style="font-size:11px;color:rgba(255,255,255,0.45);text-transform:uppercase;letter-spacing:.12em;margin-bottom:8px;">Vindex AI — Podsetnik</div>
    <div style="font-size:21px;font-weight:700;color:#fff;">{ime}, niste još probali AI analizu 📄</div>
  </div>
  <div style="padding:28px;">
    <p style="color:#cbd5e1;font-size:14px;margin:0 0 18px;line-height:1.6;">
      Juče ste se registrovali. Još uvek imate <strong style="color:#4aa8ff;">15 besplatnih upita</strong> koji čekaju.
    </p>
    <div style="background:#0d1b2a;border:1px solid #1e3a5f;border-radius:10px;padding:18px;margin-bottom:20px;">
      <div style="font-size:12px;color:#64748b;font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:.06em;">Isprobajte za 60 sekundi:</div>
      <div style="color:#e2e8f0;font-size:14px;margin-bottom:8px;">📋 <strong>Uploadujte ugovor ili tužbu</strong> — dobijate forenzički izveštaj: rizici, pravne praznine, preporuke izmena.</div>
      <div style="color:#e2e8f0;font-size:14px;">⚖️ <strong>Postavite pravno pitanje</strong> — AI pretražuje ZPP, KZ, ZOO i 50+ zakona i vraća odgovor sa članom.</div>
    </div>
    <div style="text-align:center;margin-bottom:16px;">
      <a href="{_APP_URL}" style="display:inline-block;padding:13px 32px;background:linear-gradient(135deg,#10b981,#059669);color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">Isprobaj sada →</a>
    </div>
    <p style="color:#64748b;font-size:12px;text-align:center;margin:0;">Pristup bez kreditne kartice. Bez obaveza.</p>
  </div>
  <div style="padding:14px 28px;border-top:1px solid #1e293b;">
    <p style="color:#475569;font-size:12px;margin:0;">Dobijate ovu poruku jer ste se registrovali na Vindex AI juče.{"  <a href='" + make_unsub_url(user_id, email) + "' style='color:#64748b;'>Odjavi se</a>" if user_id else ""}</p>
  </div>
</div>
</body></html>"""


def _onboarding_day3_html(email: str, user_id: str = "") -> str:
    ime = html.escape(email.split("@")[0].replace(".", " ").title())
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1b2a;font-family:system-ui,-apple-system,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#0f2035;border:1px solid #1e3a5f;border-radius:12px;overflow:hidden;">
  <div style="background:linear-gradient(135deg,#4c1d95,#1e1b4b);padding:24px 28px;">
    <div style="font-size:11px;color:rgba(255,255,255,0.45);text-transform:uppercase;letter-spacing:.12em;margin-bottom:8px;">Vindex AI</div>
    <div style="font-size:21px;font-weight:700;color:#fff;">{ime}, imate li aktivnih predmeta? 🗂</div>
  </div>
  <div style="padding:28px;">
    <p style="color:#cbd5e1;font-size:14px;margin:0 0 18px;line-height:1.6;">
      Advokati koji koriste Vindex AI kažu da im štedi <strong style="color:#a78bfa;">2-3 sata nedeljno</strong>
      na istraživanju prava i pripremi dokumenata.
    </p>
    <div style="background:#0d1b2a;border:1px solid #1e3a5f;border-radius:10px;padding:18px;margin-bottom:20px;">
      <div style="font-size:12px;color:#64748b;font-weight:600;margin-bottom:10px;text-transform:uppercase;letter-spacing:.06em;">Kreirajte predmet za 30 sekundi:</div>
      <div style="color:#94a3b8;font-size:13px;line-height:1.7;">
        ✓ Pratite rokove i ročišta<br>
        ✓ Čuvajte dokumente i beleške<br>
        ✓ AI analizira predmet i predlaže strategiju<br>
        ✓ Copilot odgovara na pitanja u kontekstu vašeg predmeta
      </div>
    </div>
    <div style="text-align:center;margin-bottom:16px;">
      <a href="{_APP_URL}" style="display:inline-block;padding:13px 32px;background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;">Otvorite predmet →</a>
    </div>
    <p style="color:#64748b;font-size:12px;text-align:center;margin:0;">Ili odgovorite na ovaj email ako imate pitanje — lično odgovaramo.</p>
  </div>
  <div style="padding:14px 28px;border-top:1px solid #1e293b;">
    <p style="color:#475569;font-size:12px;margin:0;">Ovo je poslednji podsetnik — nećemo vam slati više.{"  <a href='" + make_unsub_url(user_id, email) + "' style='color:#64748b;'>Odjavi se</a>" if user_id else ""}</p>
  </div>
</div>
</body></html>"""


def _log_onboarding(supa, user_id: str, tip: str, email: str) -> None:
    try:
        supa.table("onboarding_email_log").insert({
            "user_id": user_id,
            "tip":     tip,
            "email":   email,
        }).execute()
    except Exception:
        pass


def send_welcome_email(user_id: str, to_addr: str) -> None:
    """Sinhronski poziv — koristi se iz api.py registracija (background task)."""
    if not _SMTP_HOST or not to_addr:
        return
    supa = _get_supa()
    # Dedup
    dup = supa.table("onboarding_email_log").select("id").eq("user_id", user_id).eq("tip", "welcome").limit(1).execute()
    if dup.data:
        return
    try:
        html = _onboarding_welcome_html(to_addr, user_id=user_id)
        _smtp_send(to_addr, "Dobrodošli u Vindex AI — vaš pravni asistent je spreman", html)
        _log_onboarding(supa, user_id, "welcome", to_addr)
        logger.info("[ONBOARDING] welcome poslat uid=%.8s", user_id)
    except Exception as exc:
        logger.error("[ONBOARDING] welcome greška uid=%.8s: %s", user_id, exc)


@router.post("/email-notif/onboarding-welcome")
@limiter.limit("5/minute")
async def onboarding_welcome(request: Request, user: dict = Depends(get_current_user)):
    """Šalje welcome email trenutno ulogovanom korisniku (za testiranje)."""
    if (user.get("email") or "").lower() not in FOUNDER_EMAILS:
        raise HTTPException(status_code=403, detail="Restricted.")
    to_addr = user.get("email", "")
    if not to_addr:
        raise HTTPException(status_code=400, detail="Email nije dostupan.")
    await asyncio.to_thread(send_welcome_email, user["user_id"], to_addr)
    return {"ok": True, "poslato_na": to_addr}


@router.post("/email-notif/onboarding-cron")
@limiter.limit("5/minute")
async def onboarding_cron(request: Request, user: dict = Depends(_require_cron_or_founder)):
    """
    Cron trigger — pokreće se svaki dan (08:00).
    Šalje day1 email korisnicima registrovanim pre 24-48h koji nisu koristili AI.
    Šalje day3 email korisnicima registrovanim pre 72-96h koji nemaju predmete.
    Founder only OR cron key.
    """

    from datetime import datetime, timezone, timedelta as _td

    import asyncio as _asyncio

    supa = _get_supa()
    now  = datetime.now(timezone.utc)

    profiles_r = await asyncio.to_thread(
        lambda: supa.table("profiles").select("id, email, registered_at, created_at").execute()
    )
    profiles = profiles_r.data or []

    poslato_total = 0
    greske_total  = 0

    async def send_for_user(p: dict) -> tuple[int, int]:
        uid   = p.get("id", "")
        email = p.get("email", "")
        if not email or not uid:
            return 0, 0

        reg_str = p.get("registered_at") or p.get("created_at") or ""
        if not reg_str:
            return 0, 0
        try:
            reg_at = datetime.fromisoformat(reg_str.replace("Z", "+00:00"))
            if reg_at.tzinfo is None:
                reg_at = reg_at.replace(tzinfo=timezone.utc)
        except Exception:
            return 0, 0

        hours_since = (now - reg_at).total_seconds() / 3600
        p_sent = 0
        p_err  = 0

        # ── DAY 1: 24-48h, nije koristio AI ──────────────────────────────
        if 24 <= hours_since < 48:
            dup = await asyncio.to_thread(
                lambda: supa.table("onboarding_email_log").select("id").eq("user_id", uid).eq("tip", "day1").limit(1).execute()
            )
            if not dup.data:
                # Proveri korišćenje AI od registracije (ne od tekućeg meseca — fix day1 bug).
                # Faza 72.5: feature_usage (migracija 064, potvrđeno živa na produkciji),
                # NE korisnik_usage (obrisan izvor — ta tabela nema čak ni created_at
                # kolonu koju je ovaj upit ranije tražio, pa je provera uvek vraćala
                # prazno/lažno "nije koristio AI" za svakog korisnika). feature_usage_log
                # (migracija 065) bi bio precizniji izvor ali migracija još nije
                # primenjena na produkciju (potvrđeno scripts/audit_deployment_consistency.py)
                # — feature_usage.dan >= datum registracije je ekvivalentna provera na
                # tabeli koja stvarno postoji i piše se od svakog UsageService.consume() poziva.
                reg_dan = reg_at.date().isoformat()
                usage_r = await asyncio.to_thread(
                    lambda: supa.table("feature_usage")
                    .select("broj_koriscenja")
                    .eq("user_id", uid)
                    .gte("dan", reg_dan)
                    .limit(1)
                    .execute()
                )
                total_ai = sum((r.get("broj_koriscenja") or 0) for r in (usage_r.data or []))
                if total_ai == 0:
                    try:
                        html = _onboarding_day1_html(email, user_id=uid)
                        await asyncio.to_thread(lambda: _smtp_send(email, "Niste još probali Vindex AI — 15 upita čeka vas", html))
                        await asyncio.to_thread(lambda: _log_onboarding(supa, uid, "day1", email))
                        p_sent += 1
                        logger.info("[ONBOARDING-CRON] day1 uid=%.8s", uid)
                    except Exception as exc:
                        logger.error("[ONBOARDING-CRON] day1 greška uid=%.8s: %s", uid, exc)
                        p_err += 1

        # ── DAY 3: 72-96h, nema predmeta ─────────────────────────────────
        elif 72 <= hours_since < 96:
            dup = await asyncio.to_thread(
                lambda: supa.table("onboarding_email_log").select("id").eq("user_id", uid).eq("tip", "day3").limit(1).execute()
            )
            if not dup.data:
                predmeti_r = await asyncio.to_thread(
                    lambda: supa.table("predmeti").select("id").eq("user_id", uid).limit(1).execute()
                )
                if not predmeti_r.data:
                    try:
                        html = _onboarding_day3_html(email, user_id=uid)
                        await asyncio.to_thread(lambda: _smtp_send(email, "Vindex AI — otvorite prvi predmet za 30 sekundi", html))
                        await asyncio.to_thread(lambda: _log_onboarding(supa, uid, "day3", email))
                        p_sent += 1
                        logger.info("[ONBOARDING-CRON] day3 uid=%.8s", uid)
                    except Exception as exc:
                        logger.error("[ONBOARDING-CRON] day3 greška uid=%.8s: %s", uid, exc)
                        p_err += 1

        return p_sent, p_err

    # Batch paralelizacija — grupe od 10 korisnika
    BATCH_SIZE = 10
    for i in range(0, len(profiles), BATCH_SIZE):
        batch   = profiles[i:i + BATCH_SIZE]
        results = await _asyncio.gather(*[send_for_user(u) for u in batch], return_exceptions=True)
        for res in results:
            if isinstance(res, Exception):
                logger.error("[ONBOARDING-CRON] batch greška: %s", res)
                greske_total += 1
            else:
                poslato_total += res[0]
                greske_total  += res[1]

    return {"poslato": poslato_total, "greske": greske_total}


# ─── NAPOMENA (SEC-002, 2026-07-24): "Master cron endpoint" uklonjen ──────────
#
# Ovaj fajl je ranije definisao SVOJ /api/cron/daily (identičan path kao
# api.py's cron_daily, linija ~1464). FastAPI/Starlette dispečer bira PRVI
# registrovani match; ovaj router se montira (app.include_router) PRE nego
# što je api.py's cron_daily dekorator izvršen, pa je OVAJ handler tiho
# "pobeđivao" -- što je značilo da api.py's bogatiji dispečer (idempotency
# guard, heartbeat, workflow eskalacije, nedeljni zakon_monitoring, memory
# cleanup) NIKAD nije stvarno izvršen otkad je napisan.
#
# Ispravka: ovaj duplirani endpoint je uklonjen. posalji_podsetnike(),
# onboarding_cron() i posalji_nedeljni_sazetak() (funkcije iznad, i dalje
# dostupne kao svoje pojedinačne rute za ručno/eksterno okidanje) sada se
# pozivaju DIREKTNO iz api.py's cron_daily kao Modul 6/7/8 -- api.py je
# jedini, kanonski POST /api/cron/daily otkad je ova izmena napravljena.
