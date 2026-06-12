# -*- coding: utf-8 -*-
"""
Vindex AI — Copilot (Faza 4)

Orkestrator koji advokatu daje jedinstven chat interfejs nad svim postojećim
modulima. Ne dodaje nove AI modele — poziva postojeće servise interno.

POST /copilot/chat
  - Prihvata poruku + opcioni predmet_id
  - Detektuje nameru (intent detection)
  - Rutira na odgovarajući servis
  - Vraća strukturiran odgovor

Podržane namere:
  PRAVNO_PITANJE    → /api/pitanje (RAG zakon)
  SUDSKA_PRAKSA     → /api/praksa/search
  NACRT             → /api/nacrt (generisanje dokumenta)
  ANALIZA_PREDMETA  → /api/analiza
  ROKOVI            → /zastarelost/kalkulisi
  PRETRAGA          → /api/search
  STRATEGIJA        → /strategija/litigation (PRO)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user, require_credits, _deduct_credit
from shared.rate import limiter

logger = logging.getLogger("vindex.copilot")
router = APIRouter(tags=["copilot"])

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_INTENT_SYSTEM = """Ti si detektor namere za srpski pravni AI asistent.
Na osnovu korisničke poruke, vrati SAMO jednu od sledećih reči (bez ikakvog drugog teksta):
PRAVNO_PITANJE — korisnik pita šta zakon kaže, koji član, kakvo je pravo
SUDSKA_PRAKSA — korisnik traži sudske odluke, presude, praksu VKS
NACRT — korisnik traži da se napiše, generiše ili napravi dokument (tužba, ugovor, žalba...)
ANALIZA_PREDMETA — korisnik traži analizu, procenu predmeta, strategiju
PLAN — korisnik traži plan, korake, šta dalje, akcioni plan, naredne korake, šta treba uraditi
ROKOVI — korisnik pita o rokovima, zastarelosti, kalendarskim terminima
PRETRAGA — korisnik traži određenu osobu, predmet ili dokument u sistemu
OSTALO — ništa od navedenog

Vrati SAMO jednu reč, ništa više."""

_INTENT_CHOICES = {
    "PRAVNO_PITANJE", "SUDSKA_PRAKSA", "NACRT",
    "ANALIZA_PREDMETA", "PLAN", "ROKOVI", "PRETRAGA", "OSTALO",
}


class CopilotReq(BaseModel):
    poruka: str = Field(..., min_length=3, max_length=4000)
    predmet_id: Optional[str] = None
    session_id: Optional[str] = None


async def _detect_intent(poruka: str) -> str:
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        r = await oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user",   "content": poruka[:500]},
            ],
            temperature=0,
            max_tokens=20,
        )
        intent = (r.choices[0].message.content or "").strip().upper()
        return intent if intent in _INTENT_CHOICES else "OSTALO"
    except Exception:
        return "PRAVNO_PITANJE"


async def _load_predmet_context(predmet_id: str, user_id: str) -> str:
    """Učitava naziv+opis predmeta za kontekst copilota."""
    try:
        supa = _get_supa()
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("naziv, opis, tip, status")
                .eq("id", predmet_id)
                .eq("user_id", user_id)
                .single()
                .execute()
        )
        if r.data:
            d = r.data
            return f"[Predmet: {d.get('naziv','')} | {d.get('tip','')} | {d.get('status','')}]\n{d.get('opis','')}"
    except Exception:
        pass
    return ""


async def _handle_pravno_pitanje(poruka: str, predmet_ctx: str, user: dict) -> dict:
    """Poziva RAG zakon pipeline direktno."""
    from app.services.retrieve import retrieve_documents
    from main import ask_agent as _ask
    try:
        q = f"{predmet_ctx}\n\n{poruka}".strip() if predmet_ctx else poruka
        chunks = await asyncio.to_thread(retrieve_documents, q, 5)
        odgovor = await asyncio.to_thread(_ask, q, chunks)
        return {"tip": "PRAVNO_PITANJE", "odgovor": odgovor, "chunks": len(chunks)}
    except Exception as e:
        logger.error("[COPILOT] pravno_pitanje greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri pravnom istraživanju.")


async def _handle_sudska_praksa(poruka: str) -> dict:
    """Poziva Pinecone praksa namespace."""
    from app.services.retrieve import retrieve_sudska_praksa as _rp
    try:
        results = await asyncio.to_thread(_rp, poruka, top_k=5)
        return {"tip": "SUDSKA_PRAKSA", "presude": results}
    except Exception as e:
        logger.warning("[COPILOT] sudska_praksa greška: %s — fallback", e)
        return {
            "tip": "SUDSKA_PRAKSA",
            "odgovor": "Upotrebite modul Sudska praksa za detaljnu pretragu.",
            "presude": [],
        }


async def _handle_nacrt(poruka: str, predmet_ctx: str, user: dict) -> dict:
    """Vraća uputstvo za nacrt — korisnik mora otvoriti modul za draft."""
    return {
        "tip": "NACRT",
        "odgovor": (
            "Prepoznao sam zahtev za generisanje dokumenta. "
            "Otvorite tab **Nacrte** i odaberite tip dokumenta — sistem će "
            "iskoristiti kontekst ovog predmeta automatski."
        ),
        "akcija": "otvori_nacrt",
    }


async def _handle_pretraga(poruka: str, user_id: str) -> dict:
    """Cross-entity search."""
    supa = _get_supa()
    q = poruka[:100]
    results = []
    for table, fields, tip, url_prefix in [
        ("klijenti",          "id, ime, prezime, firma", "klijent",  "/klijenti/"),
        ("predmeti",          "id, naziv",                "predmet",  "/predmeti/"),
        ("predmet_beleske",   "id, sadrzaj, predmet_id",  "beleska",  "/predmeti/"),
    ]:
        try:
            filter_col = "sadrzaj" if table == "predmet_beleske" else ("naziv" if table == "predmeti" else "ime")
            r = await asyncio.to_thread(
                lambda t=table, f=fields, c=filter_col: supa.table(t).select(f).eq("user_id", user_id).ilike(c, f"%{q}%").limit(3).execute()
            )
            for row in (r.data or []):
                naziv = row.get("naziv") or row.get("sadrzaj","")[:80] or f"{row.get('ime','')} {row.get('prezime','')}".strip()
                url = url_prefix + row.get("predmet_id", row.get("id", ""))
                results.append({"tip": tip, "naziv": naziv, "url": url})
        except Exception:
            pass
    return {"tip": "PRETRAGA", "rezultati": results}


async def _handle_analiza_predmeta(poruka: str, predmet_id: str, user_id: str) -> dict:
    """
    Orkestrator za analizu predmeta — automatski učitava workspace podatke i
    sintetiše procenu snage pozicije bez da korisnik zna koji endpoint se zove.
    """
    supa = _get_supa()

    # Parallel fetch of all case data
    pred_r, beleske_r, dok_r, hron_r, istorija_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti").select("naziv,opis,tip,status").eq("id", predmet_id).eq("user_id", user_id).single().execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(5).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("naziv_fajla,status").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("dogadjaj,datum_iso,vaznost").eq("predmet_id", predmet_id).order("datum_iso").limit(8).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_istorija").select("pitanje,odgovor").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(2).execute()),
        return_exceptions=True,
    )

    pred = pred_r.data if not isinstance(pred_r, Exception) and pred_r.data else {}
    beleske = beleske_r.data if not isinstance(beleske_r, Exception) else []
    dok = dok_r.data if not isinstance(dok_r, Exception) else []
    hron = hron_r.data if not isinstance(hron_r, Exception) else []
    istorija = istorija_r.data if not isinstance(istorija_r, Exception) else []

    if not pred:
        return {
            "tip": "ANALIZA_PREDMETA",
            "odgovor": "Predmet nije pronađen ili nemate pristup. Proverite da li ste otvorili predmet pre analize.",
        }

    _SYNTH_SYSTEM = (
        "Ti si iskusni srpski pravni strateg. Sintetiši sve dostupne podatke i vrati ISKLJUČIVO JSON bez teksta van JSON-a:\n"
        '{"procena": str (1 konkretna rečenica — ocena snage pozicije),\n'
        ' "prednosti": [str] (max 4, konkretni faktori),\n'
        ' "slabosti": [str] (max 4, konkretni rizici),\n'
        ' "nedostaju": [str] (max 4, dokumenti/dokazi kojih nema),\n'
        ' "sledeci_korak": {"opis": str, "rok": str, "prioritet": "hitan|normalan"},\n'
        ' "verovatnoca_uspeha": int (0-100)}\n'
        "Ne halucinuj zakone ni činjenice koje nisu u podacima."
    )

    ctx = "\n".join([
        f"Predmet: {pred.get('naziv','')} | Tip: {pred.get('tip','')} | Status: {pred.get('status','')}",
        f"Opis: {(pred.get('opis') or '')[:500]}",
        f"Dokumenti u dosijeu: {', '.join(d.get('naziv_fajla','') for d in dok[:6]) or 'nema'}",
        f"Beleške: {' | '.join((b.get('sadrzaj','') or '')[:80] for b in beleske[:3]) or 'nema'}",
        f"Hronologija: {' | '.join((h.get('dogadjaj','') or '')[:80]+((' ('+h.get('datum_iso','')+')') if h.get('datum_iso') else '') for h in hron[:5]) or 'nema'}",
        f"Pitanje: {poruka}",
    ] + ([f"Prethodna analiza: {istorija[0].get('odgovor','')[:300]}"] if istorija else []))

    from openai import AsyncOpenAI
    import json as _json
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini", temperature=0.1, max_tokens=1200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYNTH_SYSTEM},
                {"role": "user",   "content": ctx},
            ],
        )
        result = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.error("[COPILOT-ANALIZA] OpenAI greška: %s", e)
        return {"tip": "ANALIZA_PREDMETA", "odgovor": "Greška pri generisanju analize."}

    return {
        "tip":               "ANALIZA_PREDMETA",
        "predmet":           pred.get("naziv", ""),
        "procena":           result.get("procena", ""),
        "prednosti":         result.get("prednosti", []),
        "slabosti":          result.get("slabosti", []),
        "nedostaju":         result.get("nedostaju", []),
        "sledeci_korak":     result.get("sledeci_korak", {}),
        "verovatnoca_uspeha": result.get("verovatnoca_uspeha", 0),
    }


async def _handle_plan_predmeta(poruka: str, predmet_id: str, user_id: str) -> dict:
    """
    Agentic PLAN — interno poziva rokove, praksu i strategiju,
    a zatim sintetiše strukturiran akcioni plan sa fazama i koracima.
    """
    supa = _get_supa()

    pred_r, beleske_r, dok_r, hron_r = await asyncio.gather(
        asyncio.to_thread(lambda: supa.table("predmeti").select("naziv,opis,tip,status").eq("id", predmet_id).eq("user_id", user_id).single().execute()),
        asyncio.to_thread(lambda: supa.table("predmet_beleske").select("sadrzaj").eq("predmet_id", predmet_id).order("created_at", desc=True).limit(4).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_dokumenti").select("naziv_fajla,status").eq("predmet_id", predmet_id).execute()),
        asyncio.to_thread(lambda: supa.table("predmet_hronologija").select("dogadjaj,datum_iso,vaznost").eq("predmet_id", predmet_id).order("datum_iso").execute()),
        return_exceptions=True,
    )

    pred = pred_r.data if not isinstance(pred_r, Exception) and pred_r.data else {}
    if not pred:
        return {"tip": "PLAN", "odgovor": "Predmet nije pronađen. Otvorite predmet pre kreiranja plana."}

    dok = dok_r.data if not isinstance(dok_r, Exception) else []
    hron = hron_r.data if not isinstance(hron_r, Exception) else []
    beleske = beleske_r.data if not isinstance(beleske_r, Exception) else []

    from datetime import date
    today_iso = date.today().isoformat()
    urgentni = [h for h in hron if h.get("vaznost") == "kritičan" and (h.get("datum_iso") or "") >= today_iso]
    nadolazeci = sorted([h for h in hron if (h.get("datum_iso") or "") >= today_iso], key=lambda x: x.get("datum_iso", ""))[:6]

    # Alat 1: Sudska praksa (Pinecone)
    praksa_kontekst = ""
    try:
        from app.services.retrieve import retrieve_sudska_praksa as _rp
        _q = f"{pred.get('naziv','')} {pred.get('tip','')} {(pred.get('opis') or '')[:200]}"
        _matches = await asyncio.wait_for(asyncio.to_thread(_rp, _q, 5), timeout=6.0)
        if _matches:
            praksa_kontekst = "\n".join(
                f"- {m.get('metadata',{}).get('decision_number','?')}: {(m.get('metadata',{}).get('izreka_preview') or '')[:100]}"
                for m in _matches[:3]
            )
    except Exception as _pe:
        logger.warning("[COPILOT-PLAN] praksa greška: %s", _pe)

    _PLAN_SYSTEM = (
        "Ti si srpski pravni strateg. Na osnovu stanja predmeta kreiraj konkretan akcioni plan. "
        "Vrati ISKLJUČIVO JSON bez teksta van JSON-a:\n"
        '{"cilj": str,\n'
        ' "faze": [{"naziv": str, "trajanje": str, "koraci": [\n'
        '   {"korak": str, "prioritet": "hitan|normalan|odlozen", "rok": str, "alat": "dokument|sud|klijent|praksa|interno"}]}],\n'
        ' "kriticni_rokovi": [{"naziv": str, "datum": str, "posledica_propustanja": str}],\n'
        ' "nedostaje": [{"stavka": str, "hitnost": "visoka|srednja|niska"}],\n'
        ' "upozorenja": [str]}\n'
        "Maks 3 faze, maks 4 koraka po fazi. Ne koristi generičke fraze — budi konkretan za ovaj predmet."
    )

    ctx = "\n".join([
        f"Predmet: {pred.get('naziv','')} | Tip: {pred.get('tip','')} | Status: {pred.get('status','')}",
        f"Opis: {(pred.get('opis') or '')[:400]}",
        f"Dokumenti: {', '.join(d.get('naziv_fajla','') for d in dok[:6]) or 'nema'}",
        f"Beleške: {' | '.join((b.get('sadrzaj','') or '')[:60] for b in beleske[:3]) or 'nema'}",
        f"Hitni rokovi: {' | '.join((h.get('dogadjaj','') or '')+'('+h.get('datum_iso','')+')' for h in urgentni[:3]) or 'nema'}",
        f"Nadolazeći: {' | '.join((h.get('dogadjaj','') or '')+'('+h.get('datum_iso','')+')' for h in nadolazeci[:5]) or 'nema'}",
        f"Relevantna praksa VKS: {praksa_kontekst or 'nije pronađena'}",
        f"Zahtev advokata: {poruka}",
    ])

    from openai import AsyncOpenAI
    import json as _json
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini", temperature=0.1, max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user",   "content": ctx},
            ],
        )
        result = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.error("[COPILOT-PLAN] OpenAI greška: %s", e)
        return {"tip": "PLAN", "odgovor": "Greška pri generisanju plana."}

    return {
        "tip":              "PLAN",
        "predmet":          pred.get("naziv", ""),
        "alati_koristeni":  ["rokovi", "sudska_praksa_vks", "strategija"],
        "cilj":             result.get("cilj", ""),
        "faze":             result.get("faze", []),
        "kriticni_rokovi":  result.get("kriticni_rokovi", []),
        "nedostaje":        result.get("nedostaje", []),
        "upozorenja":       result.get("upozorenja", []),
    }


async def _handle_ostalo(poruka: str, predmet_ctx: str) -> dict:
    """Generalni odgovor bez RAG — kratki savet."""
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    ctx_line = f"\nKontekst predmeta: {predmet_ctx}" if predmet_ctx else ""
    try:
        r = await oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "Ti si pravni asistent za srpsko pravo. Daj kratak, konkretan odgovor. "
                    "Ako ne znaš tačan zakon, kaži to otvoreno." + ctx_line
                )},
                {"role": "user", "content": poruka},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        return {"tip": "OSTALO", "odgovor": r.choices[0].message.content or ""}
    except Exception as e:
        logger.error("[COPILOT] ostalo greška: %s", e)
        return {"tip": "OSTALO", "odgovor": "Molim precizite pitanje."}


@router.post("/copilot/chat")
@limiter.limit("30/minute")
async def copilot_chat(
    req: CopilotReq,
    request: Request,
    user: dict = Depends(require_credits),
):
    """
    Vindex Copilot — orkestrator svih modula.
    Detektuje nameru i automatski rutira na odgovarajući servis.
    """
    uid      = user["user_id"]
    email    = user.get("email", "")
    predmet_ctx = ""

    if req.predmet_id:
        predmet_ctx = await _load_predmet_context(req.predmet_id, uid)

    intent = await _detect_intent(req.poruka)
    logger.info("[COPILOT] uid=%.8s intent=%s predmet=%s", uid, intent, req.predmet_id or "-")

    handlers = {
        "PRAVNO_PITANJE":   lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "SUDSKA_PRAKSA":    lambda: _handle_sudska_praksa(req.poruka),
        "NACRT":            lambda: _handle_nacrt(req.poruka, predmet_ctx, user),
        "ANALIZA_PREDMETA": lambda: _handle_analiza_predmeta(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "PLAN":             lambda: _handle_plan_predmeta(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "ROKOVI":           lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "PRETRAGA":         lambda: _handle_pretraga(req.poruka, uid),
        "OSTALO":           lambda: _handle_ostalo(req.poruka, predmet_ctx),
    }

    handler = handlers.get(intent, handlers["OSTALO"])
    result  = await handler()

    # Oduzmi kredit
    await asyncio.to_thread(_deduct_credit, uid, email)

    return {
        "intent":     intent,
        "predmet_id": req.predmet_id,
        **result,
    }
