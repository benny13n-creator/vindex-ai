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
from routers.plans import enforce_and_increment

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
DODAJ_ROK — korisnik želi da doda, upiše ili zabeleži rok, ročište, termin, rok za dostavu
KREIRAJ_BELEŠKU — korisnik želi da napiše, zabeleži ili sačuva beleška, napomenu, podsetniku
POVEZI_KLIJENTA — korisnik želi da poveže, doda ili veže klijenta, stranku, protivnu stranu
ROKOVI — korisnik pita o rokovima, zastarelosti, kalendarskim terminima (pitanje, ne akcija)
PRETRAGA — korisnik traži određenu osobu, predmet ili dokument u sistemu
PREDLOZI — korisnik pita šta treba da uradi sledeće, koji su prioriteti, šta mu nedostaje, pregled zadataka
NAPLATI_RADNJU — korisnik želi da naplati, obračuna, upiše radnju, sate, honorar, tarifa stavku
PRIKAŽI_TARIFU — korisnik pita koliko košta neka pravna radnja, tarifa, bodovi, cena, honorar AKS
OSTALO — ništa od navedenog

Vrati SAMO jednu reč, ništa više."""

_INTENT_CHOICES = {
    "PRAVNO_PITANJE", "SUDSKA_PRAKSA", "NACRT",
    "ANALIZA_PREDMETA", "PLAN",
    "DODAJ_ROK", "KREIRAJ_BELEŠKU", "POVEZI_KLIJENTA",
    "ROKOVI", "PRETRAGA", "PREDLOZI",
    "NAPLATI_RADNJU", "PRIKAŽI_TARIFU",
    "OSTALO",
}

async def _oai_parse_json(system_prompt: str, user_content: str) -> str:
    """Patchable wrapper za GPT-4o-mini JSON parse pozive."""
    from openai import AsyncOpenAI
    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    r = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content[:500]},
        ],
        temperature=0,
        max_tokens=150,
        response_format={"type": "json_object"},
    )
    return r.choices[0].message.content or "{}"


_NAPLATA_PARSE_SYSTEM = """Iz korisničke poruke izvuci podatke za fakturisanje i vrati SAMO validan JSON.
Polja:
{
  "sati": <broj ili null — broj sati rada ako je naveden>,
  "tarifa_sifra": <"T01"–"T30" ili null — AKS šifra ako se prepoznaje>,
  "opis": <string — kratak opis radnje>,
  "iznos_rsd": <integer ili null — ako je korisnik naveo eksplicitan iznos u RSD/din>
}
Primeri mapiranja:
"naplati 2h konsultacija" → {"sati":2,"tarifa_sifra":"T17","opis":"Konsultacije","iznos_rsd":null}
"upiši tužbu" → {"sati":null,"tarifa_sifra":"T01","opis":"Tužba za novčano potraživanje","iznos_rsd":null}
"naplati 15000 din za ročište" → {"sati":null,"tarifa_sifra":"T10","opis":"Zastupanje na ročištu","iznos_rsd":15000}
"1.5 sat savetovanje" → {"sati":1.5,"tarifa_sifra":"T17","opis":"Usmena konsultacija","iznos_rsd":null}
Ako opis nije jasan stavi "Pravna radnja". Vrati SAMO JSON, bez objašnjenja."""


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


async def _handle_akcija_rok(poruka: str, predmet_id: str, user_id: str) -> dict:
    """Extrahuje rok iz prirodnog jezika i upisuje u predmet_hronologija."""
    import json as _json
    from openai import AsyncOpenAI
    from datetime import date

    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    _EX_SYS = (
        "Iz srpskog teksta izvuci podatke o roku. Vrati ISKLJUČIVO JSON:\n"
        '{"dogadjaj": str (naziv/opis roka), "datum_iso": str|null (YYYY-MM-DD), '
        '"vaznost": "kritičan|bitan|normalan"}\n'
        f"Danas je {date.today().isoformat()}. Relativne datume pretvori u apsolutne."
    )
    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=150,
            response_format={"type": "json_object"},
            messages=[{"role":"system","content":_EX_SYS},{"role":"user","content":poruka}],
        )
        ext = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.error("[COPILOT-ROK] ekstrakcija greška: %s", e)
        return {"tip":"DODAJ_ROK","uspeh":False,"odgovor":"Nisam uspeo da prepoznam rok. Pokušajte: 'Dodaj rok — ročište 20. jula 2026.'"}

    if not (ext.get("dogadjaj") or "").strip():
        return {"tip":"DODAJ_ROK","uspeh":False,"odgovor":"Naziv roka nije prepoznat. Pokušajte eksplicitno: 'Dodaj rok za pripremu do 15. jula.'"}

    supa = _get_supa()
    try:
        await asyncio.to_thread(lambda: supa.table("predmet_hronologija").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "dogadjaj":   ext["dogadjaj"][:200],
            "datum":      ext.get("datum_iso",""),
            "datum_iso":  ext.get("datum_iso",""),
            "vaznost":    ext.get("vaznost","bitan"),
            "akter":      "Copilot (AI)",
        }).execute())
    except Exception as e:
        logger.error("[COPILOT-ROK] insert greška: %s", e)
        return {"tip":"DODAJ_ROK","uspeh":False,"odgovor":"Greška pri čuvanju roka. Pokušajte ponovo."}

    return {
        "tip":     "DODAJ_ROK",
        "uspeh":   True,
        "dogadjaj": ext["dogadjaj"],
        "datum":   ext.get("datum_iso",""),
        "vaznost": ext.get("vaznost","bitan"),
        "odgovor": f"Rok dodat: {ext['dogadjaj']}" + (f" ({ext['datum_iso']})" if ext.get("datum_iso") else ""),
    }


async def _handle_akcija_beleska(poruka: str, predmet_id: str, user_id: str) -> dict:
    """Izvlači sadržaj beleške iz prirodnog jezika i upisuje u predmet_beleske."""
    import json as _json
    from openai import AsyncOpenAI

    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    _EX_SYS = (
        "Korisnik šalje komandu za kreiranje beleške u srpskim pravnom sistemu. "
        "Izvuci SAMO sadržaj beleške — bez prefixa 'zabeleži', 'napiši', 'sačuvaj' itd.\n"
        'Vrati ISKLJUČIVO JSON: {"sadrzaj": str}'
    )
    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=400,
            response_format={"type": "json_object"},
            messages=[{"role":"system","content":_EX_SYS},{"role":"user","content":poruka}],
        )
        ext     = _json.loads(resp.choices[0].message.content or "{}")
        sadrzaj = (ext.get("sadrzaj") or "").strip()
    except Exception:
        sadrzaj = poruka.strip()

    if len(sadrzaj) < 3:
        return {"tip":"KREIRAJ_BELEŠKU","uspeh":False,"odgovor":"Sadržaj beleške je prazan. Navedite šta želite da zabeležite."}

    supa = _get_supa()
    try:
        await asyncio.to_thread(lambda: supa.table("predmet_beleske").insert({
            "predmet_id": predmet_id,
            "user_id":    user_id,
            "sadrzaj":    sadrzaj[:2000],
        }).execute())
    except Exception as e:
        logger.error("[COPILOT-BELESKA] insert greška: %s", e)
        return {"tip":"KREIRAJ_BELEŠKU","uspeh":False,"odgovor":"Greška pri čuvanju beleške."}

    preview = sadrzaj[:80] + ("…" if len(sadrzaj)>80 else "")
    return {
        "tip":     "KREIRAJ_BELEŠKU",
        "uspeh":   True,
        "sadrzaj": sadrzaj[:120],
        "odgovor": f"Beleška sačuvana: {preview}",
    }


async def _handle_akcija_povezi_klijenta(poruka: str, predmet_id: str, user_id: str) -> dict:
    """Traži klijenta po imenu i linkuje ga na predmet."""
    import json as _json
    from openai import AsyncOpenAI

    oai = AsyncOpenAI(api_key=OPENAI_API_KEY)
    _EX_SYS = (
        "Iz srpskog teksta izvuci ime klijenta koji treba da se poveže sa predmetom.\n"
        'Vrati ISKLJUČIVO JSON: {"ime_klijenta": str, "uloga": "stranka|protivna_stranka|svedok|ostalo"}'
    )
    try:
        resp = await oai.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=100,
            response_format={"type": "json_object"},
            messages=[{"role":"system","content":_EX_SYS},{"role":"user","content":poruka}],
        )
        ext = _json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Nisam uspeo da prepoznam ime klijenta."}

    ime = (ext.get("ime_klijenta") or "").strip()
    if not ime:
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Navedite ime klijenta kojeg treba da povežem sa predmetom."}

    supa = _get_supa()
    try:
        found_r = await asyncio.to_thread(
            lambda: supa.table("klijenti")
                .select("id,ime,prezime,firma")
                .eq("user_id", user_id)
                .is_("deleted_at","null")
                .or_(f"ime.ilike.%{ime}%,prezime.ilike.%{ime}%,firma.ilike.%{ime}%")
                .limit(3)
                .execute()
        )
    except Exception:
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Greška pri pretražvanju klijenta."}

    if not (found_r.data):
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":f"Klijent \"{ime}\" nije pronađen u CRM-u. Proverite ime ili kreirajte novog klijenta."}

    kl    = found_r.data[0]
    naziv = ((kl.get("ime","")+" "+kl.get("prezime","")).strip()) or kl.get("firma","")
    uloga = ext.get("uloga","stranka")

    existing = await asyncio.to_thread(
        lambda: supa.table("predmet_klijenti").select("id").eq("predmet_id",predmet_id).eq("klijent_id",kl["id"]).execute()
    )
    if existing.data:
        return {"tip":"POVEZI_KLIJENTA","uspeh":True,"odgovor":f"{naziv} je već vezan za ovaj predmet."}

    try:
        await asyncio.to_thread(lambda: supa.table("predmet_klijenti").insert({
            "predmet_id":     predmet_id,
            "klijent_id":     kl["id"],
            "uloga_klijenta": uloga,
            "user_id":        user_id,
        }).execute())
    except Exception as e:
        return {"tip":"POVEZI_KLIJENTA","uspeh":False,"odgovor":"Greška pri povezivanju klijenta."}

    return {
        "tip":        "POVEZI_KLIJENTA",
        "uspeh":      True,
        "klijent":    naziv,
        "klijent_id": kl["id"],
        "uloga":      uloga,
        "odgovor":    f"Klijent {naziv} vezan za predmet (uloga: {uloga}).",
    }


async def _handle_predlozi(predmet_id: str | None, user_id: str) -> dict:
    """
    Proaktivni agent — analizira stanje predmeta (ili celog portfolia)
    i vraca strukturirane predloge sledecih akcija.
    """
    from datetime import date, timedelta
    supa = _get_supa()
    today     = date.today()
    today_iso = today.isoformat()
    in_7_iso  = (today + timedelta(days=7)).isoformat()
    ago_30    = (today - timedelta(days=30)).isoformat()

    predlozi: list[dict] = []

    if predmet_id:
        # ── Predlozi za konkretan predmet ─────────────────────────────────────
        pred_r, hron_r, dok_r, bel_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("naziv, opis, tip, status")
                .eq("id", predmet_id).eq("user_id", user_id)
                .single().execute()),
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("dogadjaj, datum_iso, vaznost")
                .eq("predmet_id", predmet_id)
                .gte("datum_iso", today_iso)
                .lte("datum_iso", in_7_iso)
                .order("datum_iso").limit(10).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_dokumenti")
                .select("naziv_fajla, status")
                .eq("predmet_id", predmet_id).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_beleske")
                .select("created_at")
                .eq("predmet_id", predmet_id)
                .gte("created_at", ago_30).execute()),
            return_exceptions=True,
        )

        pred   = pred_r.data if not isinstance(pred_r, Exception) and pred_r.data else {}
        rokovi = hron_r.data if not isinstance(hron_r, Exception) else []
        dok    = dok_r.data if not isinstance(dok_r, Exception) else []
        bel    = bel_r.data if not isinstance(bel_r, Exception) else []

        for r in rokovi:
            hitan = (r.get("datum_iso") or "") <= (today + timedelta(days=2)).isoformat()
            predlozi.append({
                "tip":       "rok",
                "prioritet": "hitan" if hitan else "normalan",
                "akcija":    f"{'⚠ HITAN — ' if hitan else ''}Rok: {r.get('dogadjaj', '')} ({r.get('datum_iso', '')})",
                "predmet_id": predmet_id,
            })

        cekaju = [d for d in dok if d.get("status") in ("na_cekanju", "greska")]
        if cekaju:
            predlozi.append({
                "tip":       "dokument",
                "prioritet": "normalan",
                "akcija":    f"{len(cekaju)} dokument{'a' if len(cekaju) != 1 else ''} čeka obradu: {', '.join(d.get('naziv_fajla','') for d in cekaju[:3])}",
                "predmet_id": predmet_id,
            })

        if not bel:
            predlozi.append({
                "tip":       "neaktivnost",
                "prioritet": "info",
                "akcija":    "Nema beleški u poslednje 30 dana — dodajte napomenu o statusu.",
                "predmet_id": predmet_id,
            })

        naziv = pred.get("naziv", "predmet")
        if not predlozi:
            predlozi.append({
                "tip":       "status",
                "prioritet": "info",
                "akcija":    f"Predmet '{naziv}' je ažuran — nema hitnih akcija.",
                "predmet_id": predmet_id,
            })

        return {
            "tip":       "PREDLOZI",
            "kontekst":  "predmet",
            "predmet":   naziv,
            "predlozi":  predlozi,
            "odgovor":   f"Pronašao sam {len(predlozi)} predlog{'a' if len(predlozi) != 1 else ''} za predmet '{naziv}'.",
        }

    else:
        # ── Firma-level predlozi (bez predmet_id) ─────────────────────────────
        rokovi_r, pred_r, hron_r, bel_r = await asyncio.gather(
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("predmet_id, dogadjaj, datum_iso, vaznost")
                .eq("user_id", user_id)
                .gte("datum_iso", today_iso)
                .lte("datum_iso", in_7_iso)
                .order("datum_iso").limit(20).execute()),
            asyncio.to_thread(lambda: supa.table("predmeti")
                .select("id, naziv, status")
                .eq("user_id", user_id).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_hronologija")
                .select("predmet_id")
                .eq("user_id", user_id)
                .gte("created_at", ago_30).execute()),
            asyncio.to_thread(lambda: supa.table("predmet_beleske")
                .select("predmet_id")
                .eq("user_id", user_id)
                .gte("created_at", ago_30).execute()),
            return_exceptions=True,
        )

        predmeti_map = {}
        if not isinstance(pred_r, Exception) and pred_r.data:
            predmeti_map = {p["id"]: p for p in pred_r.data}

        if not isinstance(rokovi_r, Exception):
            for r in (rokovi_r.data or []):
                pid = r.get("predmet_id", "")
                naziv = predmeti_map.get(pid, {}).get("naziv", "Predmet")
                hitan = (r.get("datum_iso") or "") <= (today + timedelta(days=2)).isoformat()
                predlozi.append({
                    "tip":       "rok",
                    "prioritet": "hitan" if hitan else "normalan",
                    "akcija":    f"{'⚠ ' if hitan else ''}{naziv}: {r.get('dogadjaj','')} ({r.get('datum_iso','')})",
                    "predmet_id": pid,
                })

        active = set()
        if not isinstance(hron_r, Exception):
            active |= {r["predmet_id"] for r in (hron_r.data or [])}
        if not isinstance(bel_r, Exception):
            active |= {r["predmet_id"] for r in (bel_r.data or [])}

        for pid, p in predmeti_map.items():
            if p.get("status") in ("zatvoren", "arhiviran"):
                continue
            if pid not in active:
                predlozi.append({
                    "tip":       "neaktivnost",
                    "prioritet": "info",
                    "akcija":    f"Predmet '{p.get('naziv','')}' nema aktivnosti 30+ dana.",
                    "predmet_id": pid,
                })

        hitni   = [p for p in predlozi if p["prioritet"] == "hitan"]
        predlozi = sorted(predlozi, key=lambda x: 0 if x["prioritet"] == "hitan" else 1 if x["prioritet"] == "normalan" else 2)

        return {
            "tip":      "PREDLOZI",
            "kontekst": "portfolio",
            "predlozi": predlozi[:15],
            "hitnih":   len(hitni),
            "odgovor":  f"Portfolio: {len(predlozi)} prioritet{'a' if len(predlozi) != 1 else ''}. {len(hitni)} hitno.",
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


async def _handle_naplati_radnju(poruka: str, predmet_id: str | None, uid: str) -> dict:
    """Billing Faza 2 — parsira poruku i kreira billing_entry u Supabase."""
    import json as _json

    try:
        raw    = await _oai_parse_json(_NAPLATA_PARSE_SYSTEM, poruka)
        parsed = _json.loads(raw)
    except Exception as e:
        logger.warning("[COPILOT-NAPLATA] parse greška: %s", e)
        parsed = {}

    sati        = parsed.get("sati")
    tarifa_sifra= parsed.get("tarifa_sifra")
    opis        = parsed.get("opis") or "Pravna radnja"
    iznos_rsd   = parsed.get("iznos_rsd")

    # Izračunaj iznos
    from routers.billing import AKS_TARIFA
    _BOD_RSD = 50

    if iznos_rsd:
        iznos_final = int(iznos_rsd)
        tip = "manual"
    elif tarifa_sifra and tarifa_sifra in AKS_TARIFA:
        stavka = AKS_TARIFA[tarifa_sifra]
        if stavka.get("fiksno_rsd"):
            iznos_final = stavka["fiksno_rsd"]
            if sati:
                iznos_final = int(stavka["fiksno_rsd"] * sati)
        else:
            iznos_final = int((stavka.get("bodovi") or 6) * _BOD_RSD)
        tip = "tarifa"
        opis = stavka["naziv"] if not parsed.get("opis") else opis
    elif sati:
        iznos_final = int(sati * 7500)
        tip = "satnica"
        tarifa_sifra = "T30"
    else:
        return {
            "tip":     "NAPLATI_RADNJU",
            "odgovor": "Nisam razumeo šta treba naplatiti. Recite npr: 'naplati 2h konsultacija' ili 'upiši tužbu'.",
            "status":  "nije_kreirana",
        }

    supa = _get_supa()
    entry = {
        "user_id":      uid,
        "opis":         opis[:500],
        "tip":          tip,
        "iznos_rsd":    iznos_final,
        "obracunato":   False,
    }
    if predmet_id:
        entry["predmet_id"] = predmet_id
    if tarifa_sifra:
        entry["tarifa_sifra"] = tarifa_sifra
    if sati:
        entry["sati"] = float(sati)

    try:
        res = await asyncio.to_thread(
            lambda: supa.table("billing_entries").insert(entry).execute()
        )
        kreirana_id = (res.data[0].get("id") if res.data else None)
    except Exception as e:
        logger.error("[COPILOT-NAPLATA] DB greška: %s", e)
        raise HTTPException(status_code=500, detail="Greška pri čuvanju radnje.")

    sati_prikaz = f" ({sati}h)" if sati else ""
    return {
        "tip":        "NAPLATI_RADNJU",
        "odgovor":    f"✅ Upisana radnja: **{opis}**{sati_prikaz} — **{iznos_final:,} RSD**.",
        "status":     "kreirana",
        "entry_id":   kreirana_id,
        "iznos_rsd":  iznos_final,
        "opis":       opis,
        "tarifa_sifra": tarifa_sifra,
    }


async def _handle_prikazi_tarifu(poruka: str) -> dict:
    """Billing Faza 2 — prikazuje relevantne AKS tarifa stavke za datu radnju."""
    from routers.billing import AKS_TARIFA
    _BOD_RSD = 50

    # Keyword match na AKS_TARIFA
    poruka_lower = poruka.lower()
    matches = []
    for sifra, stavka in AKS_TARIFA.items():
        naziv_lower = stavka["naziv"].lower()
        # Check key words overlap
        words = [w for w in poruka_lower.split() if len(w) > 3]
        if any(w in naziv_lower for w in words):
            if stavka.get("fiksno_rsd"):
                rsd = stavka["fiksno_rsd"]
                prikaz = f"{rsd:,} RSD/sat"
            else:
                bodovi = stavka.get("bodovi") or 0
                rsd = bodovi * _BOD_RSD
                prikaz = f"{bodovi} bodova = {rsd:,} RSD"
            matches.append({
                "sifra":  sifra,
                "naziv":  stavka["naziv"],
                "iznos":  prikaz,
                "rsd":    rsd,
            })

    if not matches:
        # Vrati sve ako nema match-a
        matches = [
            {
                "sifra": s,
                "naziv": v["naziv"],
                "iznos": (f"{v['fiksno_rsd']:,} RSD/sat"
                          if v.get("fiksno_rsd")
                          else f"{v.get('bodovi', 0) * _BOD_RSD:,} RSD"),
                "rsd": v.get("fiksno_rsd") or (v.get("bodovi", 0) * _BOD_RSD),
            }
            for s, v in AKS_TARIFA.items()
        ]
        odgovor = f"AKS tarifa — {len(matches)} stavki (1 bod = {_BOD_RSD} RSD):"
    else:
        odgovor = f"Pronašao sam {len(matches)} relevantnih AKS stavki:"

    return {
        "tip":      "PRIKAŽI_TARIFU",
        "odgovor":  odgovor,
        "stavke":   matches[:10],
        "napomena": "Tarifa po AKS (Sl. gl. RS 56/2025) — 1 bod = 50 RSD.",
    }


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

    await enforce_and_increment(uid, "ai_queries")

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
        "DODAJ_ROK":        lambda: _handle_akcija_rok(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_ostalo(req.poruka, predmet_ctx),
        "KREIRAJ_BELEŠKU":  lambda: _handle_akcija_beleska(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_ostalo(req.poruka, predmet_ctx),
        "POVEZI_KLIJENTA":  lambda: _handle_akcija_povezi_klijenta(req.poruka, req.predmet_id, uid) if req.predmet_id else _handle_ostalo(req.poruka, predmet_ctx),
        "ROKOVI":           lambda: _handle_pravno_pitanje(req.poruka, predmet_ctx, user),
        "PRETRAGA":         lambda: _handle_pretraga(req.poruka, uid),
        "PREDLOZI":         lambda: _handle_predlozi(req.predmet_id, uid),
        "NAPLATI_RADNJU":   lambda: _handle_naplati_radnju(req.poruka, req.predmet_id, uid),
        "PRIKAŽI_TARIFU":   lambda: _handle_prikazi_tarifu(req.poruka),
        "OSTALO":           lambda: _handle_ostalo(req.poruka, predmet_ctx),
    }

    handler = handlers.get(intent, handlers["OSTALO"])
    result  = await handler()

    # Oduzmi kredit (require_credits već pre-deductovao atomično)
    if not user.get("credit_pre_deducted"):
        await asyncio.to_thread(_deduct_credit, uid, email)

    return {
        "intent":     intent,
        "predmet_id": req.predmet_id,
        **result,
    }
