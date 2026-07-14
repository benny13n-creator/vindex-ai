# -*- coding: utf-8 -*-
"""
Vindex AI — routers/zakon_monitoring.py

Law Change Monitoring — automatsko praćenje promena Sl. glasnika RS.

Šta radi:
  1. Scrape RSS/sajt Sl. glasnika RS za nove zakone i izmene
  2. AI analizira relevatnost za srpska pravna područja
  3. Upoređuje sa aktivnim predmetima korisnika
  4. Generiše proactive alerts: "Zakon o radu izmenjen — 3 vaša predmeta su pogođena"

Endpoints:
  POST /api/zakon-monitoring/proveri         — ručna provera za novim zakonima (cron)
  GET  /api/zakon-monitoring/novi-zakoni     — lista zakona iz poslenjih N dana
  GET  /api/zakon-monitoring/moji-predmeti   — koje izmene pogađaju moje predmete
  POST /api/zakon-monitoring/cron            — admin cron endpoint (X-Cron-Secret)

Cron podešavanje (cron-job.org, svakog ponedeljka u 07:00):
  URL:      POST https://vindex-ai.onrender.com/api/zakon-monitoring/cron
  Header:   X-Cron-Secret: {BRIEFING_CRON_SECRET}
  Schedule: 0 5 * * 1  (ponedeljak, 05:00 UTC = 07:00 Beograd)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.request import urlopen, Request as URLRequest
from urllib.error import URLError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user, _is_founder
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.usage import UsageService

logger = logging.getLogger("vindex.zakon_monitoring")
router = APIRouter(prefix="/api/zakon-monitoring", tags=["zakon-monitoring"])

# ─── Konfiguracija ────────────────────────────────────────────────────────────

# RSS feed Sl. glasnika RS
_SL_GLASNIK_RSS = "https://www.pravno-informacioni-sistem.rs/SlGlasnikPortal/eli/rss"

# Pravna područja za matching sa predmetima
_OBLASTI_KEYWORDS = {
    "radno":      ["zakon o radu", "radni odnos", "zaposleni", "otkaz", "zarade"],
    "poresko":    ["zakon o porezu", "pdv", "poreska uprava", "fiskalna"],
    "privredno":  ["privredna društva", "stečaj", "registracija", "privredno"],
    "porodično":  ["porodični zakon", "staratelj", "alimentacija", "razvod"],
    "nasledno":   ["nasledno", "testament", "zaostavština"],
    "parnično":   ["zakonik o parničnom", "parnični postupak", "izvršenje"],
    "krivično":   ["krivični zakonik", "zakonik o krivičnom", "krivičan"],
    "upravno":    ["zakon o opštem upravnom", "upravni postupak", "inspekcija"],
    "nepokretnosti": ["zakon o planiranju", "izgradnja", "katastar", "nepokretnosti"],
    "obligaciono": ["zakon o obligacionim", "ugovor", "odgovornost"],
}


# ─── RSS Parser ───────────────────────────────────────────────────────────────

def _parse_rss(url: str, timeout: int = 15) -> list[dict]:
    """Čita RSS feed i vraća listu stavki {title, link, date}."""
    items = []
    try:
        req = URLRequest(url, headers={"User-Agent": "VindexAI/1.0 (+https://vindex.ai)"})
        with urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Parsiraj <item> elemente
        item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        for match in item_pattern.finditer(content):
            item_txt = match.group(1)
            title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item_txt)
            link  = re.search(r"<link>(.*?)</link>", item_txt)
            pub   = re.search(r"<pubDate>(.*?)</pubDate>", item_txt)

            items.append({
                "title": (title.group(1) if title else "").strip(),
                "link":  (link.group(1)  if link  else "").strip(),
                "pub_date": (pub.group(1) if pub else "").strip(),
            })

    except URLError as e:
        logger.warning("[ZAKON] RSS fetch greška: %s", e)
    except Exception as e:
        logger.warning("[ZAKON] RSS parse greška: %s", e)
    return items[:50]  # Max 50 stavki


def _identifikuj_oblasti(tekst: str) -> list[str]:
    """Identifikuje pravna područja na osnovu ključnih reči."""
    tekst_l = tekst.lower()
    oblasti = []
    for oblast, keywords in _OBLASTI_KEYWORDS.items():
        if any(kw in tekst_l for kw in keywords):
            oblasti.append(oblast)
    return oblasti or ["ostalo"]


def _datum_iz_rss(pub_date_str: str) -> Optional[str]:
    """Parsira RSS datum u ISO format."""
    if not pub_date_str:
        return date.today().isoformat()
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub_date_str)
        return dt.date().isoformat()
    except Exception:
        pass
    # Fallback: tražimo YYYY-MM-DD pattern
    m = re.search(r"\d{4}-\d{2}-\d{2}", pub_date_str)
    return m.group(0) if m else date.today().isoformat()


# ─── AI Analiza zakona ───────────────────────────────────────────────────────

async def _ai_analiziraj_zakon(naziv: str, url: str = "") -> dict:
    """GPT-4o-mini generiše sažetak i identifikuje oblasti zakona."""
    try:
        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        prompt = (
            f"Analiziraj sledeći propis iz Sl. glasnika RS: '{naziv}'\n\n"
            "Odgovori SAMO validnim JSON-om:\n"
            '{"sazetak": "...", "oblasti_prava": ["radno", "poresko"], '
            '"kljucni_termini": ["otkaz", "zarade"], "vaznost": "visoka|srednja|niska", '
            '"tip_izmene": "novi_zakon|izmena|dopuna|ukidanje"}\n\n'
            "oblasti_prava vrednosti: radno|poresko|privredno|porodično|nasledno|parnično|krivično|upravno|nepokretnosti|obligaciono|ostalo\n"
            "Ekavica. Sažetak max 150 reči."
        )

        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.debug("[ZAKON] AI analiza greška za '%s': %s", naziv[:50], e)
        return {
            "sazetak": naziv,
            "oblasti_prava": _identifikuj_oblasti(naziv),
            "kljucni_termini": [],
            "vaznost": "srednja",
            "tip_izmene": "izmena",
        }


# ─── Glavna logika skeniranja ─────────────────────────────────────────────────

async def _skeniraj_sl_glasnik(supa, dana_unazad: int = 7) -> dict:
    """
    Čita RSS Sl. glasnika, filtrira nove zakone,
    AI analizira, upisuje u zakoni_monitoring, kreira user alertove.
    """
    od_datuma = (date.today() - timedelta(days=dana_unazad)).isoformat()
    items = await asyncio.to_thread(_parse_rss, _SL_GLASNIK_RSS)

    novi = 0
    alertovi = 0

    for item in items:
        naziv    = item.get("title", "").strip()
        link     = item.get("link", "").strip()
        pub_date = _datum_iz_rss(item.get("pub_date", ""))

        if not naziv or pub_date < od_datuma:
            continue

        # Preskoci ako već postoji
        try:
            exists = await asyncio.to_thread(
                lambda n=naziv, d=pub_date: supa.table("zakoni_monitoring")
                    .select("id")
                    .eq("naziv_zakona", n[:200])
                    .eq("datum_objave", d)
                    .maybe_single()
                    .execute()
            )
            if exists.data:
                continue
        except Exception:
            pass

        # AI analiza
        ai_data = await _ai_analiziraj_zakon(naziv, link)

        oblasti    = ai_data.get("oblasti_prava", _identifikuj_oblasti(naziv))
        termini    = ai_data.get("kljucni_termini", [])
        sazetak    = ai_data.get("sazetak", naziv)[:2000]
        vaznost    = ai_data.get("vaznost", "srednja")

        # Upiši u zakoni_monitoring
        try:
            await asyncio.to_thread(
                lambda: supa.table("zakoni_monitoring").insert({
                    "naziv_zakona":   naziv[:200],
                    "izvor_url":      link[:500],
                    "datum_objave":   pub_date,
                    "sazetak":        sazetak,
                    "oblasti_prava":  oblasti,
                    "kljucni_termini": termini[:20],
                }).execute()
            )
            novi += 1
        except Exception as e:
            logger.debug("[ZAKON] insert greška: %s", e)
            continue

        # Samo visoke i srednje važnosti idu kao alert
        if vaznost == "niska":
            continue

        # Pronađi korisnike sa aktivnim predmetima u ovim oblastima
        try:
            predmeti_r = await asyncio.to_thread(
                lambda: supa.table("predmeti")
                    .select("user_id, id, naziv, tip")
                    .in_("status", ["aktivan", "u_toku", "pending"])
                    .in_("tip", oblasti)
                    .execute()
            )
            pogodeni = predmeti_r.data or []
        except Exception:
            pogodeni = []

        # Grupiši po user_id
        by_user: dict[str, list] = {}
        for p in pogodeni:
            uid = p.get("user_id", "")
            if uid:
                by_user.setdefault(uid, []).append(p)

        # Kreiraj alert za svakog pogođenog korisnika
        for uid, predmeti in by_user.items():
            predmeti_nazivi = ", ".join(p.get("naziv", "")[:40] for p in predmeti[:3])
            alert_opis = (
                f"Sazetak: {sazetak[:300]}\n\n"
                f"Pogođeni predmeti ({len(predmeti)}): {predmeti_nazivi}"
            )
            try:
                await asyncio.to_thread(
                    lambda u=uid, a=alert_opis, v=vaznost: supa.table("proactive_alerts").insert({
                        "user_id":    u,
                        "tip":        "zakon_promenjen",
                        "naslov":     f"Promena zakona: {naziv[:80]}",
                        "opis":       a[:1000],
                        "urgentnost": "visoka" if v == "visoka" else "normalna",
                        "procitana":  False,
                    }).execute()
                )
                alertovi += 1
            except Exception as e:
                logger.debug("[ZAKON] alert insert greška: %s", e)

        await asyncio.sleep(0.3)  # Rate limit prema OpenAI

    logger.info("[ZAKON] Skeniranje završeno: %d novih zakona, %d alertova", novi, alertovi)
    return {"novi_zakoni": novi, "korisnik_alertova": alertovi}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/cron")
async def zakon_monitoring_cron(request: Request):
    """
    Cron endpoint — pozivati jednom nedeljno (ponedeljak, 07:00 Beograd).
    Header: X-Cron-Secret: {BRIEFING_CRON_SECRET}
    """
    cron_secret = os.getenv("BRIEFING_CRON_SECRET", "")
    x_secret    = request.headers.get("X-Cron-Secret", "")
    # Fail CLOSED: prazan cron_secret vise ne otvara endpoint za sve.
    if not cron_secret or x_secret != cron_secret:
        raise HTTPException(status_code=403, detail="Neovlašćen pristup.")

    supa = _get_supa()
    result = await _skeniraj_sl_glasnik(supa, dana_unazad=7)
    return {"ok": True, **result}


@router.post("/proveri")
@limiter.limit("3/hour")
async def proveri_nove_zakone(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ručna provera za novim zakonima (founder-only)."""
    if not _is_founder(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Restricted.")

    supa   = _get_supa()
    result = await _skeniraj_sl_glasnik(supa, dana_unazad=14)
    return {"ok": True, **result}


@router.get("/novi-zakoni")
@limiter.limit("30/minute")
async def get_novi_zakoni(
    request: Request,
    user: dict = Depends(get_current_user),
    dana: int = 30,
):
    """Lista novih zakona iz poslenjih N dana (max 90)."""
    supa     = _get_supa()
    od       = (date.today() - timedelta(days=min(dana, 90))).isoformat()

    try:
        r = await asyncio.to_thread(
            lambda: supa.table("zakoni_monitoring")
                .select("naziv_zakona, datum_objave, sazetak, oblasti_prava, izvor_url")
                .gte("datum_objave", od)
                .order("datum_objave", desc=True)
                .limit(50)
                .execute()
        )
        return {"zakoni": r.data or [], "od_datuma": od}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moji-predmeti")
@limiter.limit("20/minute")
async def zakoni_moji_predmeti(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Koje izmene zakona pogađaju moje aktivne predmete.
    Pametan cross-reference: zakoni_monitoring.oblasti_prava ∩ predmeti.tip
    """
    uid  = user["user_id"]
    supa = _get_supa()
    od   = (date.today() - timedelta(days=30)).isoformat()

    try:
        # Aktivni predmeti korisnika
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id, naziv, tip")
                .eq("user_id", uid)
                .in_("status", ["aktivan", "u_toku", "pending"])
                .execute()
        )
        predmeti = pred_r.data or []

        if not predmeti:
            return {"matches": [], "poruka": "Nemate aktivnih predmeta."}

        oblasti_predmeta = list({p.get("tip", "ostalo") for p in predmeti})

        # Novi zakoni u ovim oblastima
        zakoni_r = await asyncio.to_thread(
            lambda: supa.table("zakoni_monitoring")
                .select("naziv_zakona, datum_objave, sazetak, oblasti_prava, izvor_url")
                .gte("datum_objave", od)
                .order("datum_objave", desc=True)
                .limit(50)
                .execute()
        )
        svi_zakoni = zakoni_r.data or []

        # Intersection matching
        matches = []
        for zakon in svi_zakoni:
            oblasti_zakona = set(zakon.get("oblasti_prava", []))
            pogodeni_pred = [
                {"id": p["id"], "naziv": p["naziv"]}
                for p in predmeti
                if p.get("tip", "ostalo") in oblasti_zakona
            ]
            if pogodeni_pred:
                matches.append({
                    "zakon":           zakon.get("naziv_zakona", ""),
                    "datum_objave":    zakon.get("datum_objave", ""),
                    "sazetak":         zakon.get("sazetak", "")[:300],
                    "izvor_url":       zakon.get("izvor_url", ""),
                    "oblasti_prava":   list(oblasti_zakona),
                    "pogodeni_predmeti": pogodeni_pred[:5],
                })

        return {
            "matches": matches[:20],
            "ukupno_predmeta":  len(predmeti),
            "pronadjenih_izmena": len(matches),
            "period_dana": 30,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/impact-analiza/{predmet_id}")
@limiter.limit("3/hour")
async def impact_analiza(
    predmet_id: str,
    request:    Request,
    user:       dict = Depends(PermissionService.require("zakon_monitoring")),
):
    """
    Dubinska analiza uticaja promena zakona na konkretni predmet.

    Tok:
      1. Učitaj dokumente predmeta (tekst sadrzaj)
      2. Učitaj relevantne izmene zakona (poslenjih 90 dana)
      3. GPT-4o-mini analizira koje pasuse dokumenata pogađaju izmene
      4. Vraća: pogođeni pasusi + predložene izmene + nivo rizika
      5. Kreira proactive_alert ako je rizik visok
    """
    uid  = user["user_id"]
    supa = _get_supa()

    try:
        # Predmet
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, tip, status")
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        )
        if not pred_r.data:
            raise HTTPException(status_code=404, detail="Predmet nije pronađen.")
        predmet = pred_r.data

        # Dokumenti predmeta (tekst sadrzaj)
        dok_r = await asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("naziv_fajla, tekst_sadrzaj")
                .eq("predmet_id", predmet_id)
                .not_.is_("tekst_sadrzaj", "null")
                .limit(5)
                .execute()
        )
        dokumenti = dok_r.data or []

        if not dokumenti:
            return {
                "predmet":  predmet,
                "analiza":  "Predmet nema uploadovanih dokumenata sa tekstualnim sadržajem. Uploadujte dokumente da biste koristili impact analizu.",
                "rizik":    "nepoznat",
                "alertova": 0,
            }

        tekst_predmeta = "\n\n".join(
            f"=== {d.get('naziv_fajla', '?')} ===\n{(d.get('tekst_sadrzaj') or '')[:1500]}"
            for d in dokumenti
        )[:5000]

        # Izmene zakona relevantne za tip predmeta
        od = (date.today() - timedelta(days=90)).isoformat()
        tip = predmet.get("tip", "ostalo")

        zakoni_r = await asyncio.to_thread(
            lambda: supa.table("zakoni_monitoring")
                .select("naziv_zakona, datum_objave, sazetak, oblasti_prava")
                .gte("datum_objave", od)
                .order("datum_objave", desc=True)
                .limit(20)
                .execute()
        )
        svi_zakoni = zakoni_r.data or []

        # Filtriraj relevantne (oblast odgovara tipu predmeta)
        relevantni = [
            z for z in svi_zakoni
            if tip in (z.get("oblasti_prava") or []) or not z.get("oblasti_prava")
        ][:10]

        if not relevantni:
            return {
                "predmet":  predmet,
                "analiza":  "Nije pronađena nijedna izmena zakona relevantna za ovaj predmet u poslenjih 90 dana.",
                "rizik":    "nizak",
                "alertova": 0,
            }

        zakoni_tekst = "\n".join(
            f"- {z.get('naziv_zakona', '?')} ({z.get('datum_objave', '?')}): {(z.get('sazetak') or '')[:300]}"
            for z in relevantni
        )

        # AI analiza
        from openai import AsyncOpenAI
        oai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=1000,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ti si pravni analitičar. Analiziraj kako nedavne izmene zakona utiču na konkretne dokumente predmeta. "
                        "Odgovori SAMO validnim JSON-om:\n"
                        '{"rizik": "visok|srednji|nizak", "pogodeni_pasusi": ["..."], '
                        '"predlozene_izmene": ["..."], "zakoni_koji_uticu": ["..."], '
                        '"obrazlozenje": "..."}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Predmet: {predmet.get('naziv', '?')} (tip: {predmet.get('tip', '?')})\n\n"
                        f"Dokumenti predmeta:\n{tekst_predmeta}\n\n"
                        f"Relevantne izmene zakona (poslenjih 90 dana):\n{zakoni_tekst}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )

        import json as _json
        ai_result = _json.loads(resp.choices[0].message.content or "{}")
        rizik = ai_result.get("rizik", "nizak")

        await UsageService.consume(uid, user.get("email", ""), "zakon_monitoring")

        # Alert ako visok rizik
        alertova = 0
        if rizik == "visok":
            try:
                await asyncio.to_thread(
                    lambda: supa.table("proactive_alerts").insert({
                        "user_id":    uid,
                        "tip":        "zakon_promenjen",
                        "naslov":     f"Visok rizik: izmene zakona utiču na predmet '{predmet.get('naziv', '')[:60]}'",
                        "opis":       ai_result.get("obrazlozenje", "")[:800],
                        "urgentnost": "visoka",
                        "procitana":  False,
                    }).execute()
                )
                alertova = 1
            except Exception:
                pass

        return {
            "predmet":           predmet,
            "rizik":             rizik,
            "pogodeni_pasusi":   ai_result.get("pogodeni_pasusi", []),
            "predlozene_izmene": ai_result.get("predlozene_izmene", []),
            "zakoni_koji_uticu": ai_result.get("zakoni_koji_uticu", []),
            "obrazlozenje":      ai_result.get("obrazlozenje", ""),
            "period_dana":       90,
            "alertova":          alertova,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
