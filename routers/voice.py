# -*- coding: utf-8 -*-
"""
Voice Command Engine — glasovne komande za Vindex AI.

Dva moda:
  QUERY   — korisnik pita pitanje → backend fetch-uje podatke iz DB → GPT odgovara → TTS
  COMMAND — korisnik daje komandu → GPT parsira akcije → frontend izvršava sekvencijalno

POST /api/voice/command   — glavna ruta
POST /api/voice/feedback  — beleži feedback o tačnosti
"""
import asyncio
import io
import logging
import json
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field

from shared.deps import _get_supa, get_current_user as require_user
from shared.rate import limiter

logger = logging.getLogger("vindex.voice")
router = APIRouter(prefix="/api/voice", tags=["voice"])

# ── Detekcija tipa: pitanje vs komanda ───────────────────────────────────────

_QUERY_RE = re.compile(
    r'\b(da li|koliko|koji|koja|koje|šta|sta|kada|gde|kde|'
    r'ima\b|imate\b|imam\b|imaš\b|imas\b|postoji\b|postoje\b|'
    r'recite mi|reci mi|kaži mi|kazi mi|možeš mi|mozes mi|'
    r'koji je status|šta je sa|sta je sa|kako stoji)',
    re.IGNORECASE
)

_STOP_WORDS = {'zatvori', 'hvala', 'kraj', 'stop', 'izlaz', 'ok hvala', 'to je sve'}


def _is_query(text: str) -> bool:
    return bool(_QUERY_RE.search(text))


def _is_stop(text: str) -> bool:
    return text.lower().strip().rstrip('.!') in _STOP_WORDS


# ── DB fetch za query kontekst ────────────────────────────────────────────────

async def _fetch_rocista(uid: str, supa, days_ahead: int = 7) -> list:
    """Ročišta u narednih N dana."""
    today = date.today()
    until = (today + timedelta(days=days_ahead)).isoformat()
    today_str = today.isoformat()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("rocista")
                .select("datum,vreme,sud,sudnica,predmet_id,status")
                .eq("user_id", uid)
                .eq("status", "zakazano")
                .gte("datum", today_str)
                .lte("datum", until)
                .order("datum")
                .limit(20)
                .execute()
        )
        rows = r.data or []

        # Fetch predmet names
        if rows:
            pred_ids = list({row["predmet_id"] for row in rows if row.get("predmet_id")})
            pr = await asyncio.to_thread(
                lambda: supa.table("predmeti")
                    .select("id,naziv,tuzilac,tuzeni")
                    .in_("id", pred_ids)
                    .execute()
            )
            pred_map = {p["id"]: p for p in (pr.data or [])}
            for row in rows:
                p = pred_map.get(row.get("predmet_id"), {})
                row["predmet_naziv"] = p.get("naziv", "")
                row["tuzilac"]       = p.get("tuzilac", "")
                row["tuzeni"]        = p.get("tuzeni", "")
        return rows
    except Exception as exc:
        logger.warning("[VOICE] rocista fetch error: %s", exc)
        return []


async def _fetch_predmeti_summary(uid: str, supa) -> dict:
    """Ukupan broj aktivnih predmeta i lista naziva."""
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv,tuzilac,tuzeni,oblast,status,created_at")
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(100)
                .execute()
        )
        rows = r.data or []
        active = [p for p in rows if p.get("status") not in ("zatvoren", "arhiviran")]
        return {"ukupno": len(rows), "aktivnih": len(active), "predmeti": rows[:20]}
    except Exception as exc:
        logger.warning("[VOICE] predmeti fetch error: %s", exc)
        return {"ukupno": 0, "aktivnih": 0, "predmeti": []}


async def _fetch_rokovi(uid: str, supa, days_ahead: int = 14) -> list:
    """Rokovi koji ističu u narednih N dana."""
    today = date.today().isoformat()
    until = (date.today() + timedelta(days=days_ahead)).isoformat()
    try:
        r = await asyncio.to_thread(
            lambda: supa.table("predmet_hronologija")
                .select("datum,naziv,vaznost,predmet_id")
                .eq("user_id", uid)
                .gte("datum", today)
                .lte("datum", until)
                .order("datum")
                .limit(20)
                .execute()
        )
        return r.data or []
    except Exception as exc:
        logger.warning("[VOICE] rokovi fetch error: %s", exc)
        return []


# ── Query handler — verbalni odgovor sa DB podacima ──────────────────────────

_QUERY_SYSTEM = """Ti si glasovni pravni asistent za Vindex AI. Advokat te pita pitanje.
Dobijaš trenutne podatke iz sistema. Odgovori direktno, na srpskom.

PRAVILA:
- Maksimum 2-3 kratke rečenice. Odgovor se čita glasom (TTS).
- Budi konkretan: navedi sat, sud, naziv predmeta ako ih imaš.
- Datume prevedi u prirodan govor: "ponedeljak 23. juna" ili "danas", "sutra", "prekosutra".
- Ako nema traženih podataka, reci to direktno.
- Ne pominjaš da si AI ili model.
- Nikad ne koristi emoji ili markdown."""


async def _handle_query(text: str, uid: str, supa) -> dict:
    """Fetch-uje relevantne podatke, GPT formira verbalni odgovor."""
    today = date.today()
    today_str = today.isoformat()
    day_names = ["ponedeljak", "utorak", "sredu", "četvrtak", "petak", "subotu", "nedelju"]
    month_names = ["januara", "februara", "marta", "aprila", "maja", "juna", "jula",
                   "avgusta", "septembra", "oktobra", "novembra", "decembra"]

    def fmt_datum(d_str: str) -> str:
        try:
            d = date.fromisoformat(d_str)
            if d == today: return "danas"
            if d == today + timedelta(days=1): return "sutra"
            if d == today + timedelta(days=2): return "prekosutra"
            return f"{day_names[d.weekday()]} {d.day}. {month_names[d.month-1]}"
        except Exception:
            return d_str

    context_parts = [f"Danas je {fmt_datum(today_str)} ({today_str})."]
    text_lower = text.lower()

    tasks = []
    need_rocista   = any(w in text_lower for w in ['rociste', 'ročište', 'rocišta', 'ročišta', 'sud', 'sudu', 'danas', 'sutra', 'nedelje', 'sledece', 'sledeće'])
    need_predmeti  = any(w in text_lower for w in ['predmet', 'aktiv', 'koliko', 'predmeta', 'slucaj', 'slučaj'])
    need_rokovi    = any(w in text_lower for w in ['rok', 'rokovi', 'istice', 'ističe', 'deadline'])

    if need_rocista:
        rocista = await _fetch_rocista(uid, supa, days_ahead=14)
        if rocista:
            lines = []
            for r in rocista:
                vreme = r.get("vreme", "") or ""
                if vreme: vreme = f" u {vreme[:5]}h"
                pred = r.get("predmet_naziv", "") or ""
                tuzilac = r.get("tuzilac", "") or ""
                tuzeni  = r.get("tuzeni", "") or ""
                stranke = f" ({tuzilac} vs {tuzeni})" if tuzilac or tuzeni else ""
                sud = r.get("sud", "")
                lines.append(f"- {fmt_datum(r['datum'])}{vreme} | {sud}{' | ' + pred if pred else ''}{stranke}")
            context_parts.append("Zakazana ročišta:\n" + "\n".join(lines))
        else:
            context_parts.append("Nema zakazanih ročišta u narednih 14 dana.")

    if need_predmeti:
        summary = await _fetch_predmeti_summary(uid, supa)
        context_parts.append(
            f"Predmeti: ukupno {summary['ukupno']}, aktivnih {summary['aktivnih']}."
        )
        if summary["predmeti"]:
            names = [p.get("naziv", "") for p in summary["predmeti"][:5] if p.get("naziv")]
            if names:
                context_parts.append("Poslednji predmeti: " + ", ".join(names))

    if need_rokovi:
        rokovi = await _fetch_rokovi(uid, supa)
        if rokovi:
            lines = [f"- {fmt_datum(r['datum'])} | {r.get('naziv','')} (važnost: {r.get('vaznost','')})"
                     for r in rokovi[:5]]
            context_parts.append("Rokovi koji ističu:\n" + "\n".join(lines))
        else:
            context_parts.append("Nema kritičnih rokova u narednih 14 dana.")

    if not (need_rocista or need_predmeti or need_rokovi):
        # Generic query — no specific data needed
        context_parts.append("Korisnik pita opšto pravno pitanje.")

    context = "\n".join(context_parts)

    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=150,
            messages=[
                {"role": "system",  "content": _QUERY_SYSTEM},
                {"role": "user",    "content": f"Podaci:\n{context}\n\nPitanje: {text}"},
            ],
        )
        odgovor = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("[VOICE] query GPT error: %s", exc)
        odgovor = "Nisam mogao da obradim vaš upit. Pokušajte ponovo."

    logger.info("[VOICE] QUERY uid=%.8s → '%s'", uid, odgovor[:80])
    return {
        "type":    "query",
        "actions": [],
        "odgovor": odgovor,
        # backward compat
        "action": "unknown", "params": {}, "followup": None,
    }


# ── Command handler — parsiranje akcija ──────────────────────────────────────

_INTENT_SYSTEM = """Ti si glasovni asistent za Vindex AI — pravni sistem za srpske advokate.

Korisnik govori srpski. Pretvori komandu u niz akcija.

Vrati JSON: {"actions": [...], "odgovor": "1 kratka rečenica potvrde na srpskom (bez emojija)"}

Svaka akcija: {"action": "...", "params": {...}, "wait_ms": 0}

VAŽNO O wait_ms:
- Za sve akcije POSLE navigate_predmet: wait_ms = 0 (sistem automatski čeka da se predmet učita)
- Za export_pdf POSLE analyze_predmet: wait_ms = 12000 (analiza traje ~10s)
- Inače: wait_ms = 0 uvek

DOSTUPNE AKCIJE:
navigate_predmet    — otvori predmet (params: {query: string})
show_tab            — pređi na subtab (params: {tab: "rokovi"|"dokumenti"|"strategija"|"ai-analiza"|"naplata"|"pregled"|"timeline"|"dokazi"})
analyze_predmet     — pokreni AI analizu predmeta, procenu rizika (params: {})
load_doc_by_number  — učitaj specifičan dokument po rednom broju za analizu (params: {numbers: [1, 2, 3]})
compare_docs        — uporedi dva dokumenta po rednom broju (params: {numbers: [2, 5]})
refresh_case_dna    — regeneriši Case Genome iz svih dokumenata predmeta (params: {})
ask_question        — pošalji pitanje AI agentu (params: {text: string})
generate_document   — otvori generator dokumenta (params: {tip: "tuzba"|"zalba"|"ugovor"|"podnesak"|"urgencija"})
export_pdf          — exportuj predmet kao PDF (params: {})
start_timer         — pokreni tajmer naplate (params: {})
stop_timer          — zaustavi tajmer (params: {})
show_dashboard      — idi na početnu/dashboard (params: {})
show_klijenti       — idi na klijente (params: {})
open_digitalna_imovina — otvori modul Digitalna imovina & Usklađenost (params: {})
red_team            — red team strategija (params: {})
hearing_prep        — priprema za ročište (params: {})
search              — pretraži (params: {query: string})
stop_voice          — zatvori glasovni asistent (params: {})
unknown             — komanda nije prepoznana (params: {text: string})

PRAVILA MAPIRANJA (precizno!):
- "otvori/nađi/prikaži predmet X" → navigate_predmet({query:X})
- "analiziraj" / "uradi analizu" / "proceni" / "izvrši analizu" (bez broja dokumenta) → analyze_predmet
- "analiziraj [N]. dokument" / "učitaj [N]. dokument" / "otvori [N]. i [M]. dokument" → load_doc_by_number({numbers:[N,M]})
  Primeri: "analiziraj treći dokument" → {numbers:[3]}, "učitaj 1. i 2. dokument" → {numbers:[1,2]}, "otvori četvrti i peti" → {numbers:[4,5]}
  Redni brojevi rečima: prvi=1, drugi=2, treći=3, četvrti=4, peti=5, šesti=6, sedmi=7, osmi=8, deveti=9, deseti=10
- "uporedi DOK-X i DOK-Y" / "pronađi razlike između X. i Y. dokumenta" / "pronađi kontradikcije između X. i Y." → compare_docs({numbers:[X,Y]})
  Primer: "uporedi drugi i peti dokument" → compare_docs({numbers:[2,5]})
- "koji dokument ide u prilog" / "koji je najjači dokaz" → ask_question({text: "Koji dokument iz predmeta najviše ide u prilog našem zahtevu i zašto?"})
- "osveži Case Genome" / "analiziraj sve dokumente" / "regeneriši profil predmeta" → refresh_case_dna
- "pogledaj dokumente" / "idi na dokumenta" / "prikaži dokumenta" → show_tab({tab:"dokumenti"})
- "uradi red team" / "napravi strategiju" → red_team
- "pripremi ročište" / "šta treba za ročište" / "brifing za sud" → hearing_prep
- "idi na rokove" → show_tab({tab:"rokovi"})
- "idi na naplatu" → show_tab({tab:"naplata"})
- "idi na strategiju" → show_tab({tab:"strategija"})
- "pokreni tajmer" / "počni naplatu" / "start tajmer" → start_timer
- "zaustavi tajmer" / "stop tajmer" → stop_timer
- "idi na dashboard" / "početna" / "komandni centar" → show_dashboard
- "otvori digitalnu imovinu" / "idi na kripto usklađenost" / "otvori CARF DAC8" → open_digitalna_imovina
- "postavi pitanje" / konkretno pravno pitanje → ask_question({text: celo pitanje})
- "napravi tužbu/žalbu/ugovor/podnesak" → generate_document({tip: odgovarajući tip})
- "sačuvaj PDF" / "exportuj PDF" / "izbaci PDF" / "generiši PDF" → export_pdf
- "zatvori" / "hvala" / "kraj" → stop_voice
- Nešto što nije jasno → unknown

SLOŽENE KOMANDE — primeri sa tačnim wait_ms:
- "otvori predmet X i analiziraj" → [navigate_predmet(X,wms:0), analyze_predmet(wms:0)]
- "otvori predmet X i analiziraj 3. dokument" → [navigate_predmet(X,wms:0), load_doc_by_number({numbers:[3]},wms:0)]
- "otvori predmet X, učitaj 2. i 3. dokument i analiziraj" → [navigate_predmet(X,wms:0), load_doc_by_number({numbers:[2,3]},wms:0), analyze_predmet(wms:0)]
- "otvori predmet X i idi na rokove" → [navigate_predmet(X,wms:0), show_tab(rokovi,wms:0)]
- "otvori predmet X, analiziraj i sačuvaj PDF" → [navigate_predmet(X,wms:0), analyze_predmet(wms:0), export_pdf(wms:12000)]
- "otvori predmet X i postavi pitanje o Y" → [navigate_predmet(X,wms:0), ask_question(Y,wms:0)]
- "otvori predmet X i pokreni tajmer" → [navigate_predmet(X,wms:0), start_timer(wms:0)]

odgovor mora biti max 10 reči, bez emojija, samo potvrda šta se radi.

Vrati SAMO JSON bez markdown blokova."""


async def _handle_command(text: str) -> dict:
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=400,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user",   "content": f"Komanda: {text}"},
            ],
        )
        raw    = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("[VOICE] command parse error: %s", exc)
        parsed = {
            "actions": [{"action": "ask_question", "params": {"text": text}, "wait_ms": 0}],
            "odgovor": "",
        }

    # Normalizuj stari format {action, params} → novi {actions: [...]}
    if "action" in parsed and "actions" not in parsed:
        actions = [{"action": parsed["action"], "params": parsed.get("params", {}), "wait_ms": 0}]
        if parsed.get("followup"):
            actions.append({"action": parsed["followup"], "params": {}, "wait_ms": 0})
        parsed = {"actions": actions, "odgovor": parsed.get("odgovor", "")}

    actions = parsed.get("actions") or []
    if not actions:
        actions = [{"action": "unknown", "params": {"text": text}, "wait_ms": 0}]

    odgovor = parsed.get("odgovor", "")
    logger.info("[VOICE] COMMAND %d akcija: %s", len(actions), [a.get("action") for a in actions])

    return {
        "type":    "command",
        "actions":  actions,
        "odgovor":  odgovor,
        "original": text,
        # Backward compat
        "action":  actions[0].get("action") if actions else "unknown",
        "params":  actions[0].get("params", {}) if actions else {},
        "followup": actions[1].get("action") if len(actions) > 1 else None,
    }


# ── Whisper STT — transkribovanje audio snimka ───────────────────────────────

@router.post("/transcribe")
@limiter.limit("20/minute")
async def voice_transcribe(
    request: Request,
    audio: UploadFile = File(...),
    language: str = "sr",
    user=Depends(require_user),
):
    """
    Prima audio blob (webm/mp4/wav/ogg) od MediaRecorder-a i vraća transkript
    putem OpenAI Whisper-1. Koristiti umesto browser Web Speech API.
    """
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="Audio fajl je prazan.")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio fajl ne sme biti veći od 10MB.")

    content_type = audio.content_type or "audio/webm"
    filename = audio.filename or "audio.webm"
    if "webm" in content_type or "webm" in filename:
        filename = "audio.webm"
    elif "mp4" in content_type:
        filename = "audio.mp4"
    elif "wav" in content_type:
        filename = "audio.wav"
    elif "ogg" in content_type:
        filename = "audio.ogg"
    else:
        filename = "audio.webm"

    lang = language if language in ("sr", "en", "de", "fr", "bs", "hr") else "sr"

    try:
        from openai import OpenAI
        import os
        oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        buf = io.BytesIO(data)
        buf.name = filename

        response = await asyncio.to_thread(
            lambda: oai.audio.transcriptions.create(
                model="whisper-1",
                file=(filename, buf, content_type),
                language=lang,
                prompt="Pravni tekst na srpskom jeziku. Advokat, sud, predmet, tužba, žalba, ročište.",
            )
        )
        transkript = (response.text or "").strip()
        logger.info("[VOICE/STT] uid=%.8s %d chars", user["user_id"], len(transkript))
        return {"transkript": transkript, "language": lang, "chars": len(transkript)}

    except Exception as exc:
        logger.error("[VOICE/STT] Whisper greška: %s", exc)
        raise HTTPException(status_code=500, detail=f"Transkribovanje nije uspelo: {exc}")


# ── TTS endpoint — OpenAI višejezični sintetizator ───────────────────────────

class VoiceTtsReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)


@router.post("/tts")
@limiter.limit("40/minute")
async def voice_tts(req: VoiceTtsReq, request: Request, user=Depends(require_user)):
    """Generiše MP3 audio iz teksta pomoću OpenAI TTS (višejezičan — srpski radi ispravno)."""
    from fastapi.responses import Response as _Resp
    from openai import OpenAI

    text = req.text.strip()[:600]
    if not text:
        return _Resp(content=b"", media_type="audio/mpeg")

    try:
        client = OpenAI()
        resp = await asyncio.to_thread(
            lambda: client.audio.speech.create(
                model="tts-1",
                voice="onyx",   # Dubok, profesionalan glas
                input=text,
                speed=0.94,
                response_format="mp3",
            )
        )
        return _Resp(content=resp.content, media_type="audio/mpeg",
                     headers={"Cache-Control": "no-store"})
    except Exception as exc:
        logger.warning("[VOICE/TTS] OpenAI TTS greška: %s", exc)
        # Vraćamo 204 — frontend će koristiti browser fallback
        return _Resp(status_code=204, content=b"")


# ── Endpoint ──────────────────────────────────────────────────────────────────

class VoiceCommandReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.post("/command")
@limiter.limit("40/minute")
async def voice_command(
    req: VoiceCommandReq,
    request: Request,
    user=Depends(require_user),
):
    """
    Glasovna komanda ili upit.

    QUERY  → backend fetch-uje podatke iz DB → GPT odgovara → {type:"query", odgovor:"..."}
    COMMAND → GPT parsira akcije → {type:"command", actions:[...], odgovor:"..."}
    """
    text = req.text.strip()
    uid  = user["user_id"]
    supa = _get_supa()

    logger.info("[VOICE] uid=%.8s text='%s'", uid, text[:120])

    # Stop reč → odmah zatvori bez API poziva
    if _is_stop(text):
        return {
            "type": "command", "actions": [{"action": "stop_voice", "params": {}, "wait_ms": 0}],
            "odgovor": "Doviđenja.", "action": "stop_voice", "params": {}, "followup": None,
        }

    # Pitanje sa upitnim rečima → Query mod
    if _is_query(text):
        return await _handle_query(text, uid, supa)

    # Komanda → Command mod
    return await _handle_command(text)


# ── Feedback endpoint ─────────────────────────────────────────────────────────

class VoiceFeedbackReq(BaseModel):
    action:   str
    uspeh:    bool
    text:     Optional[str] = None
    response: Optional[str] = None
    komentar: Optional[str] = None


@router.post("/feedback")
async def voice_feedback(req: VoiceFeedbackReq, user=Depends(require_user)):
    """Beleži tačnost interpretacije glasovne komande."""
    uid = user["user_id"]
    logger.info("[VOICE_FB] user=%.8s action=%s uspeh=%s", uid, req.action, req.uspeh)
    try:
        supa = _get_supa()
        await asyncio.to_thread(
            lambda: supa.table("usage_events").insert({
                "user_id": uid,
                "feature": "voice",
                "action":  "voice_feedback",
                "meta": {
                    "voice_action": req.action,
                    "uspeh":        req.uspeh,
                    "text":         req.text,
                    "response":     req.response,
                    "komentar":     req.komentar,
                },
            }).execute()
        )
    except Exception as exc:
        logger.warning("[VOICE_FB] greška: %s", exc)
    return {"ok": True}
