# -*- coding: utf-8 -*-
"""
Vindex AI — routers/case_commander.py

AI Case Commander: sveobuhvatna analiza predmeta, proaktivna upozorenja,
preporuceni sledeci potez. Chief of Staff za advokata.

Endpoints:
  POST /api/commander/analiza      — kompletna analiza predmeta (GPT-4o)
  POST /api/commander/quick-check  — brza provera, 3 upozorenja (GPT-4o-mini)
  POST /api/commander/checklist    — proceduralna checklist za predmet
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter

logger = logging.getLogger("vindex.case_commander")
router = APIRouter(tags=["case-commander"])

# ── Sistem prompt ─────────────────────────────────────────────────────────────

_COMMANDER_SYSTEM = """Ti si AI Case Commander — licni pravni Chief of Staff za advokata.

Tvoj zadatak: Analiziraj ceo predmet i daj sveobuhvatan izvestaj koji advokatu govori TACNO sta treba da uradi sledece.

Format izvestaja mora biti UVEK ovaj:

**STATUS PREDMETA:** [Jedna recenica o trenutnom stanju]

**NEDOSTAJE:**
- [Lista dokumenata/dokaza/radnji koje nedostaju]

**RIZICI:**
- [Konkretni pravni rizici sa obrazlozenjem]

**PROTIVNIKOVA STRATEGIJA:**
[Sta ce protivna strana verovatno uraditi i zasto]

**SUDSKA PRAKSA:**
[Relevantni pattern u slicnim predmetima — cituj samo ako si siguran]

**PREPORUCENI POTEZ:**
[Jedna konkretna akcija sa obrazlozenjem — zasto bas ovo, zasto bas sada]

**VREMENSKI PRITISAK:**
[Da li postoji urgentnost — ako da, koji rok i koliko dana ostaje]

Budi direktan kao iskusan kolega, ne kao AI. Ekavica. Bez uvodnih fraza tipa 'Naravno' ili 'Svakako'."""

# ── Modeli ────────────────────────────────────────────────────────────────────

class CommanderRequest(BaseModel):
    predmet_id: str
    dodatni_kontekst: Optional[str] = None
    tip_analize: str = "kompletna"   # "kompletna" | "brza" | "rizici"


class ChecklistRequest(BaseModel):
    predmet_id: str
    tip_postupka: Optional[str] = None

# ── Helperi ───────────────────────────────────────────────────────────────────

async def _dohvati_predmet_kontekst(predmet_id: str, uid: str, supa) -> dict:
    """Paralelno dohvata sve podatke o predmetu."""
    pred_r, rokovi_r, dok_r, kom_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("*")
                .eq("id", predmet_id)
                .eq("user_id", uid)
                .maybe_single()
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rokovi")
                .select("naziv, datum, tip, opis")
                .eq("predmet_id", predmet_id)
                .order("datum")
                .limit(10)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti")
                .select("naziv, tip, created_at")
                .eq("predmet_id", predmet_id)
                .limit(20)
                .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("komentari")
                .select("sadrzaj, created_at")
                .eq("predmet_id", predmet_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
        ),
        return_exceptions=True,
    )

    def _safe(r):
        if isinstance(r, Exception):
            return []
        return getattr(r, "data", None) or []

    def _safe_one(r):
        if isinstance(r, Exception):
            return {}
        return getattr(r, "data", None) or {}

    return {
        "predmet":   _safe_one(pred_r),
        "rokovi":    _safe(rokovi_r),
        "dokumenta": _safe(dok_r),
        "komentari": _safe(kom_r),
    }


def _formatiraj_kontekst(ctx: dict, dodatni: str = "") -> str:
    """Formatira podatke o predmetu u citljiv tekst za AI."""
    p = ctx["predmet"]

    lines = [
        f"NAZIV PREDMETA: {p.get('naziv', 'N/A')}",
        f"STATUS: {p.get('status', 'N/A')}",
        f"STRANKA: {p.get('stranka', 'N/A')}",
        f"PROTIVNIK: {p.get('protivnik', 'N/A')}",
        f"TIP POSTUPKA: {p.get('tip_postupka') or p.get('oblast', 'N/A')}",
        f"SUD: {p.get('sud', 'N/A')}",
        f"VREDNOST SPORA: {p.get('vrednost_spora') or p.get('vrednost', 'N/A')}",
    ]

    if p.get("opis") or p.get("napomena"):
        opis = (p.get("opis") or p.get("napomena") or "")[:500]
        lines.append(f"OPIS: {opis}")

    if ctx["rokovi"]:
        lines.append(f"\nROKOVI ({len(ctx['rokovi'])}):")
        for r in ctx["rokovi"]:
            datum = str(r.get("datum", "N/A"))[:10]
            opis  = (r.get("opis") or "")[:80]
            lines.append(f"  - {r.get('naziv', 'Rok')} | {datum}" + (f" | {opis}" if opis else ""))
    else:
        lines.append("\nROKOVI: Nema unetih rokova")

    if ctx["dokumenta"]:
        lines.append(f"\nDOKUMENTA U SISTEMU ({len(ctx['dokumenta'])}):")
        for d in ctx["dokumenta"][:10]:
            lines.append(f"  - {d.get('naziv', 'N/A')} ({d.get('tip', 'N/A')})")
    else:
        lines.append("\nDOKUMENTA: Nema uploadovanih dokumenata")

    if ctx["komentari"]:
        lines.append("\nPOSLEDNJA BELEZKA:")
        lines.append(f"  {ctx['komentari'][0].get('sadrzaj', '')[:300]}")

    if dodatni:
        lines.append(f"\nDODATNI KONTEKST OD ADVOKATA: {dodatni}")

    return "\n".join(lines)

# ── Endpointi ─────────────────────────────────────────────────────────────────

@router.post("/api/commander/analiza")
@limiter.limit("15/minute")
async def commander_analiza(
    request: Request,
    payload: CommanderRequest,
    user: dict = Depends(get_current_user),
):
    """
    Kompletna AI analiza predmeta — Chief of Staff izvestaj.
    GPT-4o, strukturiran format, proaktivna upozorenja.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    ctx = await _dohvati_predmet_kontekst(payload.predmet_id, uid, supa)

    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    predmet_tekst = _formatiraj_kontekst(ctx, payload.dodatni_kontekst or "")

    from openai import OpenAI
    oai   = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = "gpt-4o" if payload.tip_analize in ("kompletna", "rizici") else "gpt-4o-mini"

    resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _COMMANDER_SYSTEM},
                {"role": "user",   "content": f"Analiziraj sledeci predmet:\n\n{predmet_tekst}"},
            ],
            max_tokens=1500,
            temperature=0.3,
        )
    )

    analiza = resp.choices[0].message.content.strip()

    # Sacuvaj analizu u bazu (ignorisi gresku ako tabela ne postoji)
    try:
        await asyncio.to_thread(
            lambda: supa.table("commander_analize").insert({
                "user_id":    uid,
                "predmet_id": payload.predmet_id,
                "analiza":    analiza[:8000],
                "tip":        payload.tip_analize,
            }).execute()
        )
    except Exception:
        pass

    return {
        "analiza":       analiza,
        "predmet_id":    payload.predmet_id,
        "predmet_naziv": ctx["predmet"].get("naziv", ""),
        "tip_analize":   payload.tip_analize,
        "model":         model,
    }


@router.post("/api/commander/quick-check")
@limiter.limit("30/minute")
async def commander_quick_check(
    request: Request,
    payload: CommanderRequest,
    user: dict = Depends(get_current_user),
):
    """
    Brza provera predmeta — 3 najhitnija upozorenja za 15-20 sek.
    Idealno za hover/tooltip pri otvaranju predmeta.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    ctx = await _dohvati_predmet_kontekst(payload.predmet_id, uid, supa)

    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    predmet_tekst = _formatiraj_kontekst(ctx)

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    "Brza provera predmeta. Navedi TACNO 3 najhitnija upozorenja ili akcije. "
                    "Format: numericana lista, svaka stavka maks 2 recenice. Direktan ton. Ekavica.\n\n"
                    + predmet_tekst
                ),
            }],
            max_tokens=300,
            temperature=0.3,
        )
    )

    tekst = resp.choices[0].message.content.strip()
    upozorenja = [
        u.strip().lstrip("123456789.-) ")
        for u in tekst.split("\n")
        if u.strip() and len(u.strip()) > 10
    ][:3]

    return {
        "upozorenja":    upozorenja,
        "predmet_id":    payload.predmet_id,
        "predmet_naziv": ctx["predmet"].get("naziv", ""),
    }


@router.post("/api/commander/checklist")
@limiter.limit("20/minute")
async def commander_checklist(
    request: Request,
    payload: ChecklistRequest,
    user: dict = Depends(get_current_user),
):
    """
    Generise proceduranu checklist za predmet.
    Grupisana po fazama: Priprema → Tuzba/Odgovor → Postupak → Zakljucenje.
    """
    uid  = user["user_id"]
    supa = _get_supa()

    ctx = await _dohvati_predmet_kontekst(payload.predmet_id, uid, supa)

    if not ctx["predmet"]:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    p   = ctx["predmet"]
    tip = (
        payload.tip_postupka
        or p.get("tip_postupka")
        or p.get("oblast")
        or "gradjansko"
    )
    predmet_tekst = _formatiraj_kontekst(ctx)

    from openai import OpenAI
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": (
                    f"Napravi kompletnu proceduralnu checklist za {tip} predmet. "
                    "Svaka stavka je konkretna akcija (markdown checkbox format). "
                    "Grupisi u faze: ## Priprema, ## Podnesak/Tuzba, ## Tok postupka, ## Zakljucenje. "
                    "Ekavica.\n\n"
                    + predmet_tekst
                ),
            }],
            max_tokens=900,
            temperature=0.3,
        )
    )

    checklist_tekst = resp.choices[0].message.content.strip()

    stavke = []
    for linija in checklist_tekst.split("\n"):
        l = linija.strip()
        if l.startswith("- [ ]") or l.startswith("- [x]") or l.startswith("- [X]"):
            stavke.append({
                "text":      l[5:].strip(),
                "completed": "[x]" in l.lower(),
            })

    return {
        "checklist_tekst": checklist_tekst,
        "stavke":          stavke,
        "ukupno":          len(stavke),
        "predmet_id":      payload.predmet_id,
        "tip_postupka":    tip,
    }


# ── AI Command Center — Jutarnji brifing ──────────────────────────────────────

async def _dohvati_sve_predmete_za_analizu(user_id: str) -> dict:
    """Paralelno dohvata sve aktivne predmete + rokove/dokumente/komentare iz 30/7 dana."""
    from datetime import datetime, timedelta

    danas     = datetime.now().date()
    za_30     = (danas + timedelta(days=30)).isoformat()
    pre_7     = (datetime.now() - timedelta(days=7)).isoformat()
    supa      = _get_supa()

    predmeti_r, rokovi_r, dokumenti_r, komentari_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti")
            .select("id, naziv, opis, status, tip_postupka, protivnik, sud, vrednost_spora, created_at")
            .eq("user_id", user_id).eq("status", "aktivan")
            .order("created_at", desc=True).limit(20).execute()),
        asyncio.to_thread(lambda: supa.table("rokovi")
            .select("id, naziv, datum, opis, predmet_id, status")
            .eq("user_id", user_id)
            .gte("datum", danas.isoformat()).lte("datum", za_30)
            .order("datum").limit(50).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
            .select("id, naziv, tip, predmet_id, created_at")
            .eq("user_id", user_id)
            .gte("created_at", pre_7)
            .order("created_at", desc=True).limit(30).execute()),
        asyncio.to_thread(lambda: supa.table("komentari")
            .select("id, sadrzaj, predmet_id, created_at")
            .eq("user_id", user_id)
            .gte("created_at", pre_7)
            .order("created_at", desc=True).limit(20).execute()),
        return_exceptions=True,
    )

    def _d(r):
        if isinstance(r, Exception):
            return []
        return getattr(r, "data", None) or []

    predmeti  = _d(predmeti_r)
    rokovi    = _d(rokovi_r)
    dokumenti = _d(dokumenti_r)
    komentari = _d(komentari_r)

    predmeti_map = {p["id"]: {**p, "rokovi": [], "dokumenti": [], "komentari": []} for p in predmeti}
    for r in rokovi:
        if r.get("predmet_id") in predmeti_map:
            predmeti_map[r["predmet_id"]]["rokovi"].append(r)
    for d in dokumenti:
        if d.get("predmet_id") in predmeti_map:
            predmeti_map[d["predmet_id"]]["dokumenti"].append(d)
    for k in komentari:
        if k.get("predmet_id") in predmeti_map:
            predmeti_map[k["predmet_id"]]["komentari"].append(k)

    return {
        "predmeti":           list(predmeti_map.values()),
        "ukupno_rokova":      len(rokovi),
        "ukupno_dokumentata": len(dokumenti),
    }


async def _cross_case_analiza(podaci: dict, ime_korisnika: str) -> dict:
    """GPT-4o cross-case analiza — rizici, kontradikcije, nepovezani dokumenti, prioritet."""
    from datetime import datetime, timedelta
    from openai import OpenAI

    predmeti = podaci["predmeti"]
    n = len(predmeti)

    if n == 0:
        return {
            "nalazeni": False,
            "rezime": "",
            "nalazi": [],
            "prioritet": None,
            "statistike": {"aktivnih": 0, "rizika": 0, "kontradikcija": 0, "nepovezanih": 0, "rokova_hitnih": 0},
        }

    predmeti_txt = ""
    for p in predmeti:
        predmeti_txt += f"\n--- PREDMET: {p['naziv']} (ID: {p['id'][:8]}) ---\n"
        predmeti_txt += f"Tip: {p.get('tip_postupka','?')} | Protivnik: {p.get('protivnik','?')} | Sud: {p.get('sud','?')}\n"
        if p.get("opis"):
            predmeti_txt += f"Opis: {p['opis'][:300]}\n"
        if p["rokovi"]:
            predmeti_txt += "Rokovi: " + ", ".join(
                f"{r['naziv']} ({r['datum']})" for r in p["rokovi"][:5]
            ) + "\n"
        if p["dokumenti"]:
            predmeti_txt += "Novi dokumenti: " + ", ".join(d["naziv"] for d in p["dokumenti"][:5]) + "\n"
        if p["komentari"]:
            predmeti_txt += "Beleške: " + " | ".join(
                (k.get("sadrzaj") or k.get("tekst") or "")[:100] for k in p["komentari"][:3]
            ) + "\n"

    danas_str = datetime.now().strftime("%d.%m.%Y")

    prompt = f"""Analiziraj sledeće aktivne pravne predmete advokata {ime_korisnika} (datum: {danas_str}):

{predmeti_txt}

Identifikuj:
1. RIZICI — stvari koje mogu negativno uticati na ishod (max 5)
2. KONTRADIKCIJE — protivrečnosti unutar jednog predmeta ili između beleški i dokumenta (max 3)
3. NEPOVEZANI DOKUMENTI — dokumenti uploadovani u poslednjih 7 dana koji nisu pomenuti u rokovima niti belešci (max 3)
4. PRIORITET — koji JEDAN predmet treba da bude prioritet danas i zašto (konkretno)

Odgovori SAMO validnim JSON-om:

{{
  "nalazi": [
    {{
      "tip": "rizik",
      "predmet_naziv": "naziv predmeta",
      "predmet_id_prefix": "prva 8 slova ID-a",
      "naslov": "kratak naslov nalaza (max 60 karaktera)",
      "opis": "konkretan opis i šta treba uraditi (max 200 karaktera)"
    }}
  ],
  "prioritet": {{
    "predmet_naziv": "naziv",
    "predmet_id_prefix": "prva 8 slova",
    "razlog": "konkretan razlog zašto baš ovaj predmet (max 150 karaktera)"
  }},
  "rezime": "jedna rečenica koja opisuje opšte stanje svih predmeta (max 120 karaktera)"
}}

Pravila: Budi konkretan. Ako nema stvarnih nalaza, vrati praznu listu. Ekavica obavezna. tip mora biti tačno: rizik | kontradikcija | nepovezan_dokument"""

    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await asyncio.to_thread(
        lambda: oai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ti si AI pravni operativni asistent. Odgovaraš SAMO validnim JSON-om. Ekavica."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
    )

    analiza = json.loads(resp.choices[0].message.content.strip())
    nalazi  = analiza.get("nalazi", [])

    za_7  = (datetime.now().date() + timedelta(days=7)).isoformat()
    hitni = [r for p in predmeti for r in p["rokovi"] if r.get("datum", "") <= za_7]

    return {
        "nalazeni": True,
        "rezime":   analiza.get("rezime", ""),
        "nalazi":   nalazi,
        "prioritet": analiza.get("prioritet"),
        "statistike": {
            "aktivnih":      n,
            "rizika":        sum(1 for f in nalazi if f["tip"] == "rizik"),
            "kontradikcija": sum(1 for f in nalazi if f["tip"] == "kontradikcija"),
            "nepovezanih":   sum(1 for f in nalazi if f["tip"] == "nepovezan_dokument"),
            "rokova_hitnih": len(hitni),
        },
    }


@router.get("/api/commander/jutarnji")
async def commander_jutarnji(
    user: dict = Depends(get_current_user),
):
    """
    AI Command Center jutarnji brifing — srce platforme.

    Keširan po korisniku za tekući dan. Analizira SVE aktivne predmete odjednom.
    Pronalazi rizike, kontradikcije, nepovezane dokumente i preporučuje prioritet za danas.
    0 kredita — uključeno u pretplatu.
    """
    from datetime import datetime, date

    uid   = user["user_id"]
    danas = date.today().isoformat()
    supa  = _get_supa()

    cached = await asyncio.to_thread(
        lambda: supa.table("commander_jutarnji")
            .select("brifing")
            .eq("user_id", uid)
            .eq("datum", danas)
            .limit(1)
            .execute()
    )
    if cached.data:
        return cached.data[0]["brifing"]

    korisnik_r = await asyncio.to_thread(
        lambda: supa.table("korisnici")
            .select("ime, prezime")
            .eq("id", uid)
            .maybe_single()
            .execute()
    )
    k   = (korisnik_r.data if not isinstance(korisnik_r, Exception) else None) or {}
    ime = k.get("ime") or "advokate"

    sat = datetime.now().hour
    if sat < 12:
        pozdrav_prefix = "Dobro jutro"
    elif sat < 18:
        pozdrav_prefix = "Dobar dan"
    else:
        pozdrav_prefix = "Dobro veče"

    podaci  = await _dohvati_sve_predmete_za_analizu(uid)
    n       = len(podaci["predmeti"])
    analiza = await _cross_case_analiza(podaci, ime)

    if n == 0:
        poruka = "Još uvek nemaš aktivnih predmeta. Dodaj prvi predmet da bi AI Command Center počeo da radi."
    elif n == 1:
        poruka = "Analizirao sam tvoj aktivan predmet."
    else:
        poruka = f"Analizirao sam svih {n} aktivnih predmeta."

    brifing = {
        "pozdrav":      f"{pozdrav_prefix}, {ime}.",
        "poruka":       poruka,
        "datum":        danas,
        "generisan_u":  datetime.now().isoformat(),
        **analiza,
    }

    try:
        await asyncio.to_thread(
            lambda: supa.table("commander_jutarnji")
                .upsert({"user_id": uid, "datum": danas, "brifing": brifing},
                        on_conflict="user_id,datum")
                .execute()
        )
    except Exception:
        pass

    return brifing


@router.post("/api/commander/jutarnji/refresh")
async def commander_jutarnji_refresh(
    user: dict = Depends(get_current_user),
):
    """Briše keš za danas i generiše novi brifing."""
    from datetime import date
    from fastapi.responses import RedirectResponse

    uid  = user["user_id"]
    supa = _get_supa()

    try:
        await asyncio.to_thread(
            lambda: supa.table("commander_jutarnji")
                .delete()
                .eq("user_id", uid)
                .eq("datum", date.today().isoformat())
                .execute()
        )
    except Exception:
        pass

    return RedirectResponse(url="/api/commander/jutarnji", status_code=303)
