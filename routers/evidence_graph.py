# -*- coding: utf-8 -*-
"""
Vindex AI — routers/evidence_graph.py

Evidence Graph — vizuelni graf entiteta i veza predmeta.

GPT-4o ekstrahuje lica, dokumente, dogadjaje, tvrdnje i datume iz predmeta
i vraca node/edge JSON pogodan za D3.js / Cytoscape prikaz.

Endpoints:
  POST /api/evidence-graph/generisi   — AI ekstrakcija grafa (2 kredita)
  GET  /api/evidence-graph/{predmet_id} — poslednji sacuvani graf
  POST /api/evidence-graph/dodaj-cvor — rucno dodavanje cvora u graf
"""
import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user
from shared.rate import limiter
from shared.permissions import PermissionService
from shared.usage import UsageService

logger = logging.getLogger("vindex.evidence_graph")
router = APIRouter(prefix="/api/evidence-graph", tags=["evidence_graph"])

# ── Prazan graf — fallback vrednost ──────────────────────────────────────────
_PRAZAN_GRAF: dict = {"nodes": [], "edges": []}

# ── GPT-4o promptovi (strogo ekavica) ────────────────────────────────────────
_SYSTEM_PROMPT = (
    "Ti si AI sistem za ekstrakciju pravnih entiteta. "
    "Na osnovu pravnih dokumenata i beleski ekstrahuj sve entitete i veze medu njima. "
    "Odgovori SAMO validnim JSON-om bez ikakvih dodatnih objasnjenja, komentara ili markdown fenci.\n\n"
    "Ocekivani format:\n"
    "{\n"
    '  "nodes": [\n'
    '    {"id": "<jedinstven_id>", "label": "<kratko_ime>", "tip": "<tip>", "opis": "<opis>"}\n'
    "  ],\n"
    '  "edges": [\n'
    '    {"izvor": "<id_cvora>", "cilj": "<id_cvora>", "tip_veze": "<tip>", "opis": "<opis>"}\n'
    "  ]\n"
    "}\n\n"
    "Dozvoljeni tipovi cvora (tip): lice | dokument | dogadjaj | tvrdnja | datum\n"
    "Dozvoljene veze (tip_veze): POMINJE | POTVRDJUJE | OSPORAVA | VEZUJE | PRETHODI\n\n"
    "Pravila:\n"
    "- id mora biti jedinstven string bez razmaka (npr. 'lice_01', 'dok_ugovor')\n"
    "- label je kratko prepoznatljivo ime (maks 30 karaktera)\n"
    "- opis je jedna recenica koja opisuje entitet ili vezu\n"
    "- izvor i cilj u edges moraju odgovarati id poljima iz nodes\n"
    "- Maksimalno 30 cvora i 50 grana\n"
    "- Ako nema dovoljno podataka, vrati prazne liste"
)


def _izgradj_kontekst(predmet: dict, dokumenti: list, komentari: list, rokovi: list) -> str:
    """Gradi tekstualni kontekst iz podataka predmeta za GPT prompt."""
    delovi = []

    # Predmet
    delovi.append(
        f"PREDMET: {predmet.get('naziv', 'Nepoznat predmet')}\n"
        f"Tip: {predmet.get('tip', '')}, Oblast: {predmet.get('oblast', '')}\n"
        f"Tuzilac: {predmet.get('tuzilac', '')}, Tuzeni: {predmet.get('tuzeni', '')}\n"
        f"Opis: {(predmet.get('opis', '') or '')[:500]}"
    )

    # Dokumenti
    if dokumenti:
        delovi.append("\n\nDOKUMENTI:")
        for d in dokumenti[:15]:
            naziv = d.get("naziv_fajla") or "Bez naziva"
            tip = d.get("tip_dokaza") or "nepoznat"
            tekst = (d.get("tekst") or d.get("izvod") or "")[:300]
            linija = f"- [{tip}] {naziv}"
            if tekst:
                linija += f": {tekst}"
            delovi.append(linija)

    # Komentari / beleske
    if komentari:
        delovi.append("\n\nBELESKE I KOMENTARI:")
        for k in komentari[:10]:
            tekst = (k.get("tekst") or "").strip()
            if tekst:
                delovi.append(f"- {tekst[:300]}")

    # Rokovi
    if rokovi:
        delovi.append("\n\nROKOVI I DOGADJAJI:")
        for r in rokovi[:10]:
            naziv = r.get("sud") or "Rociste"
            datum = (r.get("datum") or "")[:10]
            status = r.get("status") or ""
            delovi.append(f"- {naziv} (datum: {datum}, status: {status})")

    return "\n".join(delovi)


def _pozovi_gpt(kontekst: str) -> dict:
    """Sinhroni GPT-4o poziv — pokrece se u asyncio.to_thread."""
    from openai import OpenAI

    client = OpenAI()
    user_msg = (
        f"Ekstrahuj sve pravne entitete i veze iz sledecih podataka predmeta:\n\n"
        f"{kontekst}\n\n"
        "Vrati SAMO JSON objekat sa kljucevima 'nodes' i 'edges'."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Ukloni eventualne markdown fence
        if raw.startswith("```"):
            raw = "\n".join(
                line for line in raw.splitlines()
                if not line.strip().startswith("```")
            )
        rezultat = json.loads(raw)
        # Provera osnovne strukture
        if "nodes" not in rezultat or "edges" not in rezultat:
            logger.warning("[EG] GPT odgovor nema ocekivanu strukturu, koristim prazan graf")
            return _PRAZAN_GRAF.copy()
        return rezultat
    except json.JSONDecodeError as e:
        logger.error("[EG] JSONDecodeError pri parsiranju GPT odgovora: %s", e)
        return _PRAZAN_GRAF.copy()
    except Exception as e:
        logger.error("[EG] Greska pri GPT-4o pozivu: %s", e)
        return _PRAZAN_GRAF.copy()


# ── Pydantic modeli ───────────────────────────────────────────────────────────

class GenerisiRequest(BaseModel):
    predmet_id: str = Field(..., description="UUID predmeta za koji se generise graf")


class DodajCvorRequest(BaseModel):
    predmet_id: str = Field(..., description="UUID predmeta")
    label:      str = Field(..., max_length=60,   description="Kratko ime cvora")
    tip:        str = Field(..., description="lice | dokument | dogadjaj | tvrdnja | datum")
    opis:       str = Field("",  max_length=300,  description="Opis cvora")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generisi")
@limiter.limit("10/minute")
async def generisi_graf(
    req: GenerisiRequest,
    request: Request,
    user: dict = Depends(PermissionService.require("evidence_graph")),
):
    """
    AI ekstrakcija Evidence Grafa za predmet (2 kredita).

    GPT-4o analizira sve dokumente, komentare i rokove predmeta i
    vraca graf entiteta (lica, dokumenti, dogadjaji, tvrdnje, datumi)
    i veza medu njima (POMINJE, POTVRDJUJE, OSPORAVA, VEZUJE, PRETHODI).
    """
    supa = _get_supa()
    uid   = user["user_id"]
    email = user.get("email", "")

    # ── Provera vlasnistva ────────────────────────────────────────────────────
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select(
            "id,naziv,tip,oblast,opis,tuzilac,tuzeni"
        ).eq("id", req.predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")
    predmet = pr.data[0]

    # ── Paralelno dohvatanje podataka ─────────────────────────────────────────
    dok_r, kom_r, rok_r = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmet_dokumenti").select(
                "id,naziv_fajla,tip_dokaza,tekst_sadrzaj"
            ).eq("predmet_id", req.predmet_id).limit(15).execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("predmet_komentari").select(
                "tekst"
            ).eq("predmet_id", req.predmet_id).order("created_at", desc=True).limit(10).execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("rocista").select(
                "sud,datum,status"
            ).eq("predmet_id", req.predmet_id).order("datum").limit(10).execute()
        ),
        return_exceptions=True,
    )

    dokumenti = (dok_r.data if not isinstance(dok_r, Exception) else []) or []
    komentari = (kom_r.data if not isinstance(kom_r, Exception) else []) or []
    rokovi    = (rok_r.data if not isinstance(rok_r, Exception) else []) or []

    # Loguj greske pri dohvatanju, ali nastavi
    if isinstance(dok_r, Exception):
        logger.warning("[EG] Greska pri dohvatanju dokumenata: %s", dok_r)
    if isinstance(kom_r, Exception):
        logger.warning("[EG] Greska pri dohvatanju komentara: %s", kom_r)
    if isinstance(rok_r, Exception):
        logger.warning("[EG] Greska pri dohvatanju rokova: %s", rok_r)

    # ── Izgradnja konteksta i GPT-4o poziv ───────────────────────────────────
    kontekst = _izgradj_kontekst(predmet, dokumenti, komentari, rokovi)
    graf = await asyncio.to_thread(_pozovi_gpt, kontekst)

    # ── Cuvanje grafa u evidence_grafovi ────────────────────────────────────
    try:
        await asyncio.to_thread(
            lambda: supa.table("evidence_grafovi").insert({
                "predmet_id": req.predmet_id,
                "user_id":    uid,
                "podaci":     graf,
            }).execute()
        )
    except Exception as e:
        logger.error("[EG] Greska pri cuvanju grafa: %s", e)
        # Nastavljamo — vracamo graf cak i ako cuvanje nije uspelo

    # ── Trošenje kredita (iznos čita registar za "evidence_graph") ────────────
    preostalo = await UsageService.consume(uid, email, "evidence_graph")

    return {
        "nodes":            graf.get("nodes", []),
        "edges":            graf.get("edges", []),
        "predmet_naziv":    predmet.get("naziv", ""),
        "credits_remaining": max(preostalo, 0),
    }


@router.get("/{predmet_id}")
@limiter.limit("30/minute")
async def get_graf(
    predmet_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Vraca poslednji sacuvani Evidence Graf za predmet."""
    supa = _get_supa()
    uid  = user["user_id"]

    # ── Provera vlasnistva ────────────────────────────────────────────────────
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id,naziv").eq("id", predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    # ── Dohvatanje poslednjeg grafa ───────────────────────────────────────────
    graf_r = await asyncio.to_thread(
        lambda: supa.table("evidence_grafovi").select(
            "id,podaci,created_at"
        ).eq("predmet_id", predmet_id).eq("user_id", uid).order(
            "created_at", desc=True
        ).limit(1).execute()
    )

    if not graf_r.data:
        return {
            "postoji":       False,
            "nodes":         [],
            "edges":         [],
            "predmet_naziv": pr.data[0].get("naziv", ""),
        }

    zapis  = graf_r.data[0]
    podaci = zapis.get("podaci") or _PRAZAN_GRAF

    return {
        "postoji":       True,
        "graf_id":       zapis.get("id"),
        "created_at":    zapis.get("created_at"),
        "nodes":         podaci.get("nodes", []),
        "edges":         podaci.get("edges", []),
        "predmet_naziv": pr.data[0].get("naziv", ""),
    }


@router.post("/dodaj-cvor")
@limiter.limit("10/minute")
async def dodaj_cvor(
    req: DodajCvorRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Rucno dodaje cvor u postojeci Evidence Graf predmeta.

    Ako graf jos ne postoji, kreira novi sa samo ovim cvorom.
    """
    _DOZVOLJENI_TIPOVI = {"lice", "dokument", "dogadjaj", "tvrdnja", "datum"}
    if req.tip not in _DOZVOLJENI_TIPOVI:
        raise HTTPException(
            status_code=422,
            detail=f"Nedozvoljeni tip cvora '{req.tip}'. Dozvoljeno: {', '.join(sorted(_DOZVOLJENI_TIPOVI))}",
        )

    supa = _get_supa()
    uid  = user["user_id"]

    # ── Provera vlasnistva ────────────────────────────────────────────────────
    pr = await asyncio.to_thread(
        lambda: supa.table("predmeti").select("id").eq("id", req.predmet_id).eq("user_id", uid).execute()
    )
    if not pr.data:
        raise HTTPException(status_code=404, detail="Predmet nije pronadjen.")

    # ── Dohvatanje poslednjeg grafa ───────────────────────────────────────────
    graf_r = await asyncio.to_thread(
        lambda: supa.table("evidence_grafovi").select(
            "id,podaci"
        ).eq("predmet_id", req.predmet_id).eq("user_id", uid).order(
            "created_at", desc=True
        ).limit(1).execute()
    )

    novi_cvor = {
        "id":    f"manual_{req.tip}_{uuid.uuid4().hex[:8]}",
        "label": req.label.strip(),
        "tip":   req.tip,
        "opis":  req.opis.strip(),
    }

    if graf_r.data:
        # Azuriraj postojeci graf
        zapis  = graf_r.data[0]
        podaci = zapis.get("podaci") or _PRAZAN_GRAF.copy()
        nodes  = list(podaci.get("nodes", []))
        edges  = list(podaci.get("edges", []))
        nodes.append(novi_cvor)
        azurirani = {"nodes": nodes, "edges": edges}

        await asyncio.to_thread(
            lambda: supa.table("evidence_grafovi").update({
                "podaci": azurirani,
            }).eq("id", zapis["id"]).execute()
        )
        graf_id = zapis["id"]
    else:
        # Nema grafa — kreiraj novi sa samo ovim cvorom
        podaci = {"nodes": [novi_cvor], "edges": []}
        res = await asyncio.to_thread(
            lambda: supa.table("evidence_grafovi").insert({
                "predmet_id": req.predmet_id,
                "user_id":    uid,
                "podaci":     podaci,
            }).execute()
        )
        graf_id = (res.data or [{}])[0].get("id")

    logger.info(
        "[EG] Dodat cvor manual tip=%s label=%r predmet=%s",
        req.tip, req.label[:30], req.predmet_id,
    )

    return {
        "ok":       True,
        "cvor":     novi_cvor,
        "graf_id":  graf_id,
    }
