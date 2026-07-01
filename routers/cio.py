# -*- coding: utf-8 -*-
"""
Vindex AI — Chief Intelligence Officer (CIO)

Ne čeka pitanje. Svaki dan skenira kompletni portfelj kancelarije i
pronalazi šta je najvažnije — i šta advokat JOŠ NIJE PRIMETIO.

GET  /api/cio/daily    — dnevni CIO izveštaj (keširan 6h)
POST /api/cio/run      — forsiraj regenerisanje
GET  /api/cio/history  — poslednjih 7 dana
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.cio")
router = APIRouter(prefix="/api/cio", tags=["cio"])

# ── CIO sistem prompt ─────────────────────────────────────────────────────────

_CIO_SYSTEM = """Ti si Chief Intelligence Officer (CIO) pravne kancelarije.

TVOJ POSAO NIJE DA ODGOVARAS NA PITANJA. TVOJ POSAO JE DA DOLAZIS SA ODGOVORIMA.

Svaki dan skenujes kompletan portfelj i pronalazis ono sto advokat JOS NIJE PRIMETIO.
Koristis: Case Genome modele predmeta + Firm DNA + Lekcije + Obrasce uspeha.

Vrati SAMO validan JSON (bez markdown):
{
  "cio_preporuka": "JEDNA konkretna akcija sa najvecim uticajem — danas, imenuj predmet",
  "najveci_rizik": {
    "predmet_id": "uuid tacno iz portfolija",
    "predmet_naziv": "...",
    "rizik": "Konkretan opis — sta moze da propadne i zasto",
    "kriticnost": 94,
    "akcija": "Sta tacno uraditi u sledecih 24h"
  },
  "najveca_prilika": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "prilika": "Opis prilike koja se ne koristi — konkretno",
    "akcija": "Sta uraditi da se iskoristi"
  },
  "zapostavljen_predmet": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "dana_bez_aktivnosti": 18,
    "rizik_zapustanja": "Sta se moze dogoditi ako se ne reaguje"
  },
  "neprimecena_kontradikcija": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "kontradikcija": "Tacno sta se kosi u dokazima ili cinjenicama",
    "tezina": "kriticna|vazna",
    "preporuka": "Konkretna akcija"
  },
  "kriticni_rok": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "rok_naziv": "Naziv roka",
    "datum": "YYYY-MM-DD",
    "dana_do": 13,
    "akcija": "Sta tacno uraditi"
  },
  "suboptimalna_strategija": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "problem": "Zasto strategija vise nije optimalna u svetlu novih podataka",
    "preporuka": "Predlozena izmena strategije"
  },
  "slicni_predmet": {
    "predmet_id": "uuid",
    "predmet_naziv": "...",
    "slicnost": "Cemu lici iz prethodne prakse — konkretna paralela",
    "lekcija": "Sta se moze direktno primeniti"
  },
  "cio_zakljucak": "2-3 recenice o opstem zdravlju portfolija — iskreno, bez optimizma",
  "pouzdanost": "visoka|srednja|niska"
}

STROGA PRAVILA:
- Popuni SVE kljuceve. Ako nemas podataka za neki, stavi null za ceo objekat.
- predmet_id mora biti UUID tacno preuzet iz ulaznih podataka.
- Budi konkretan — imenuj predmete, opisi rizike precizno. Nikad genericki.
- kriticnost 0-100 (100 = odmah reagovati, predmet u opasnosti).
- zapostavljen_predmet = predmet sa najvecim dana_bez_aktivnosti koji ima aktivni rizik.
- kriticni_rok = rok koji istice najranije u sledecih 60 dana (status=aktivan).
- neprimecena_kontradikcija = kontradikcija tezina=kriticna koja jos nije adresovana.
- suboptimalna_strategija = predmet cija strategija nije pracena novim dokazima ili gecosima.
- slicni_predmet = predmet koji se podudara sa dobijenim sporom iz lekcija ili obrazaca.
- cio_preporuka = JEDNA akcija, ne lista. Imenuj predmet. Reci tacno sta uraditi.
- Ekavica strogo — nikada ijekavica.
- Budi iskren o slabostima portfelja. CIO koji utesava nije CIO."""


# ── Portfolio builder ─────────────────────────────────────────────────────────

def _kompaktan_predmet(p: dict, danas: date) -> Optional[dict]:
    """Izvlaci kljucne signale iz jednog predmeta za CIO analizu."""
    genome = p.get("case_dna") or {}
    if not genome or genome.get("greska"):
        return None

    now = datetime.now(timezone.utc)
    upd = p.get("updated_at") or ""
    dana_neakt = 0
    if upd:
        try:
            upd_dt = datetime.fromisoformat(upd.replace("Z", "+00:00"))
            dana_neakt = (now - upd_dt).days
        except Exception:
            pass

    rokovi_aktivni = []
    for r in (genome.get("rokovi_kriticni") or []):
        if r.get("status") == "aktivan" and r.get("datum"):
            try:
                rok_dt = date.fromisoformat(str(r["datum"])[:10])
                dana_do = (rok_dt - danas).days
                if 0 <= dana_do <= 60:
                    rokovi_aktivni.append({
                        "naziv": r.get("naziv", "")[:60],
                        "datum": str(r["datum"])[:10],
                        "dana_do": dana_do,
                        "opis": (r.get("opis") or "")[:50],
                    })
            except Exception:
                pass

    nt = genome.get("najslabija_tacka") or {}
    strat = genome.get("strategija") or {}
    kontr_list = genome.get("kontradikcije") or []
    kontr_kriticne = [k for k in kontr_list if k.get("tezina") == "kriticna"]
    ned_kriticno = sum(1 for n in (genome.get("nedostaje") or []) if n.get("hitnost") == "kriticno")

    return {
        "id":                   p.get("id"),
        "naziv":                p.get("naziv", ""),
        "oblast":               p.get("oblast_prava", ""),
        "snaga":                genome.get("snaga_predmeta_procent"),
        "dana_bez_aktivnosti":  dana_neakt,
        "genome_verzija":       genome.get("verzija", 1),
        "najslabija_tacka":     {
            "rizik":      (nt.get("rizik") or "")[:80],
            "kriticnost": nt.get("kriticnost"),
        } if nt.get("rizik") else None,
        "rokovi_aktivni":       sorted(rokovi_aktivni, key=lambda x: x["dana_do"])[:3],
        "kontradikcije_kriticne": [
            {"opis": (k.get("opis") or "")[:70]} for k in kontr_kriticne[:2]
        ],
        "nedostaje_kriticno":   ned_kriticno,
        "strategija_cilj":      (strat.get("primarni_cilj") or genome.get("strategija_osnova") or "")[:70],
        "zakljucak":            (genome.get("zakljucak") or "")[:100],
    }


async def _generiši_cio_izvestaj(uid: str, supa) -> dict:
    """Skenira kompletni portfelj i generise dnevni CIO izvestaj."""
    danas = date.today()

    # Paralelno prikupljanje
    pred_r, fdna_r, lek_r, patt_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
            .select("id,naziv,oblast_prava,updated_at,case_dna")
            .eq("user_id", uid)
            .in_("status", ["aktivan", "u_toku", "pending"])
            .order("updated_at", desc=False)
            .limit(40)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("firm_dna")
            .select("pattern,frekvencija,uzoraka")
            .eq("user_id", uid)
            .eq("aktuelna", True)
            .order("frekvencija", desc=True)
            .limit(6)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("lessons_learned")
            .select("sadrzaj,kategorija,pouzdanost,broj_predmeta")
            .eq("user_id", uid)
            .in_("status_lekcije", ["usvojena_praksa"])
            .order("pouzdanost", desc=True)
            .limit(8)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("case_patterns")
            .select("tip_spora,faktor,pobede,porazi,ukupno")
            .eq("user_id", uid)
            .order("pobede", desc=True)
            .limit(8)
            .execute()
        ),
    )

    predmeti_raw = pred_r.data or []

    # Kompaktni portfolio za GPT
    portfolio = []
    for p in predmeti_raw:
        komp = _kompaktan_predmet(p, danas)
        if komp:
            portfolio.append(komp)

    if not portfolio:
        return {
            "datum":              danas.isoformat(),
            "cio_preporuka":      "Nema aktivnih predmeta sa Case Genome modelom. Generišite Genome za aktivne predmete.",
            "portfolio_zdravlje": {"ukupno_aktivnih": len(predmeti_raw), "sa_genomom": 0},
            "predmeta_analizirano": 0,
            "pouzdanost":         "niska",
        }

    # Firm context tekst
    firm_ctx_parts = []
    fdna = fdna_r.data or []
    if fdna:
        firm_ctx_parts.append("FIRM DNA — kako kancelarija razmislja:\n" + "\n".join(
            f"- {d.get('pattern','')[:80]} (frekvencija: {d.get('frekvencija',0)})"
            for d in fdna
        ))
    lekcije = lek_r.data or []
    if lekcije:
        firm_ctx_parts.append("USVOJENE LEKCIJE iz prethodnih predmeta:\n" + "\n".join(
            f"- [{l.get('pouzdanost','?')}] {l.get('sadrzaj','')[:100]}"
            for l in lekcije
        ))
    patt = patt_r.data or []
    if patt:
        firm_ctx_parts.append("OBRASCI USPEHA (tip spora → win rate):\n" + "\n".join(
            f"- {cp.get('tip_spora','')}: {cp.get('faktor','')[:50]} "
            f"({cp.get('pobede',0)}/{cp.get('ukupno',1)} predmeta)"
            for cp in patt
        ))

    firm_ctx = "\n\n".join(firm_ctx_parts)

    # Portfolio statistike
    snage = [p["snaga"] for p in portfolio if p["snaga"] is not None]
    prosecna_snaga = round(sum(snage) / len(snage)) if snage else 0

    user_msg = (
        f"PORTFOLIO KANCELARIJE: {len(portfolio)} aktivnih predmeta sa Genome modelom\n"
        f"Prosecna snaga predmeta: {prosecna_snaga}%\n\n"
        f"PREDMETI (kompaktni prikaz):\n{json.dumps(portfolio, ensure_ascii=False, separators=(',',':'))}\n\n"
        + (f"{firm_ctx}" if firm_ctx else "Napomena: Firma jos nema akumuliranu DNA/lekcije.")
    )

    import openai
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _CIO_SYSTEM},
            {"role": "user",   "content": user_msg[:14000]},
        ],
        response_format={"type": "json_object"},
        temperature=0.15,
        max_tokens=2500,
    )

    try:
        izvestaj = json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        izvestaj = {}

    # Deterministicke statistike (ne GPT)
    jakih  = sum(1 for p in portfolio if (p["snaga"] or 0) >= 65)
    slabih = sum(1 for p in portfolio if (p["snaga"] or 0) < 40)
    kriticnih_rizika = sum(1 for p in portfolio
                           if (p.get("najslabija_tacka") or {}).get("kriticnost", 0) >= 85)
    sa_kriticnim_rokovima = sum(1 for p in portfolio
                                if any(r["dana_do"] <= 7 for r in (p.get("rokovi_aktivni") or [])))

    izvestaj["portfolio_zdravlje"] = {
        "ukupno_aktivnih":      len(portfolio),
        "jakih":                jakih,
        "srednje":              len(portfolio) - jakih - slabih,
        "slabih":               slabih,
        "prosecna_snaga":       prosecna_snaga,
        "kriticnih_rizika":     kriticnih_rizika,
        "kriticnih_rokova_7d":  sa_kriticnim_rokovima,
    }
    izvestaj["datum"]               = danas.isoformat()
    izvestaj["predmeta_analizirano"] = len(portfolio)

    logger.info("[CIO] izvestaj generisan uid=%.8s predmeta=%d prosecna_snaga=%d%%",
                uid, len(portfolio), prosecna_snaga)
    return izvestaj


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/daily")
async def cio_daily(user=Depends(get_current_user)):
    """Vraca dnevni CIO izvestaj. Generise se jednom i kesira 6 sati."""
    uid  = user["user_id"]
    supa = _get_supa()
    now  = datetime.now(timezone.utc)
    danes_iso = date.today().isoformat()

    # Kes — 6 sati
    try:
        cached = await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj")
            .select("izvestaj,predmeta_analizirano,created_at")
            .eq("user_id", uid)
            .eq("datum", danes_iso)
            .single()
            .execute()
        )
        if cached.data:
            ts_str = cached.data.get("created_at", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if (now - ts).total_seconds() < 21600:
                    return {
                        "izvestaj":             cached.data["izvestaj"],
                        "predmeta_analizirano": cached.data.get("predmeta_analizirano", 0),
                        "iz_kesa":              True,
                        "generisano_u":         ts_str,
                    }
    except Exception:
        pass

    # Generisi
    try:
        izvestaj = await _generiši_cio_izvestaj(uid, supa)
    except Exception as e:
        logger.error("[CIO] daily greška: %s", e)
        raise HTTPException(500, f"CIO greška: {e}")

    # Snimi
    try:
        await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj").upsert({
                "user_id":             uid,
                "datum":               danes_iso,
                "izvestaj":            izvestaj,
                "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
            }, on_conflict="user_id,datum").execute()
        )
    except Exception as ue:
        logger.warning("[CIO] upsert greška: %s", ue)

    return {
        "izvestaj":             izvestaj,
        "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
        "iz_kesa":              False,
        "generisano_u":         now.isoformat(),
    }


@router.post("/run")
async def cio_run(user=Depends(get_current_user)):
    """Forsira regenerisanje CIO izvestaja — ignoriše kes."""
    uid  = user["user_id"]
    supa = _get_supa()
    now  = datetime.now(timezone.utc)

    try:
        izvestaj = await _generiši_cio_izvestaj(uid, supa)
    except Exception as e:
        logger.error("[CIO] run greška: %s", e)
        raise HTTPException(500, f"CIO greška: {e}")

    danes_iso = date.today().isoformat()
    try:
        await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj").upsert({
                "user_id":             uid,
                "datum":               danes_iso,
                "izvestaj":            izvestaj,
                "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
            }, on_conflict="user_id,datum").execute()
        )
    except Exception:
        pass

    return {
        "izvestaj":             izvestaj,
        "predmeta_analizirano": izvestaj.get("predmeta_analizirano", 0),
        "iz_kesa":              False,
        "generisano_u":         now.isoformat(),
    }


@router.get("/history")
async def cio_history(user=Depends(get_current_user), limit: int = 7):
    """Poslednjih N dana CIO izvestaja."""
    uid  = user["user_id"]
    supa = _get_supa()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("cio_dnevni_izvestaj")
            .select("datum,predmeta_analizirano,created_at,izvestaj")
            .eq("user_id", uid)
            .order("datum", desc=True)
            .limit(min(limit, 30))
            .execute()
        )
        rows = r.data or []
        # Vrati sazeti prikaz (ne ceo izvestaj)
        return {
            "history": [
                {
                    "datum":               row["datum"],
                    "predmeta_analizirano": row.get("predmeta_analizirano"),
                    "created_at":          row.get("created_at"),
                    "cio_preporuka":       (row.get("izvestaj") or {}).get("cio_preporuka", ""),
                    "pouzdanost":          (row.get("izvestaj") or {}).get("pouzdanost", ""),
                    "portfolio_zdravlje":  (row.get("izvestaj") or {}).get("portfolio_zdravlje"),
                }
                for row in rows
            ]
        }
    except Exception as e:
        raise HTTPException(500, str(e))
