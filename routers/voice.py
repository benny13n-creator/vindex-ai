# -*- coding: utf-8 -*-
"""
Voice Command Engine — glasovne komande za Vindex AI.

Advokat govori → browser Web Speech API → POST /api/voice/command →
GPT-4o-mini parsira intent → vraća action + params → frontend izvršava.
"""
import asyncio
import logging
import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional

from shared.deps import _get_supa, get_current_user as require_user
from shared.rate import limiter

logger = logging.getLogger("vindex.voice")
router = APIRouter(prefix="/api/voice", tags=["voice"])

_INTENT_SYSTEM = """Ti si glasovni asistent za Vindex AI — pravni operativni sistem za srpske advokate.

Korisnik govori srpski. Pretvori komandu u niz akcija koje treba izvršiti po redu.

Vrati JSON: {"actions": [...], "odgovor": "kratak TTS tekst za potvrdu na srpskom"}

Svaka akcija: {"action": "...", "params": {...}, "wait_ms": 0}
- wait_ms = kašnjenje u ms PRE ove akcije (npr. 2200 ako prethodna otvara predmet koji treba da se učita)

DOSTUPNE AKCIJE:
navigate_predmet  — otvori predmet (params: {query: string})
show_tab          — pređi na subtab unutar predmeta (params: {tab: "rokovi"|"dokumenti"|"strategija"|"ai-analiza"|"naplata"|"pregled"|"timeline"|"dokazi"})
ask_question      — postavi pravno pitanje AI agentu (params: {text: string})
generate_document — generiši dokument (params: {tip: "tuzba"|"zalba"|"ugovor"|"podnesak"|"urgencija"})
start_timer       — pokreni tajmer naplate (params: {})
stop_timer        — zaustavi tajmer (params: {})
show_dashboard    — idi na početnu (params: {})
show_klijenti     — idi na klijente (params: {})
procena_rizika    — pokreni procenu rizika predmeta (params: {})
red_team          — pokreni red team strategiju (params: {})
hearing_prep      — priprema za ročište (params: {})
search            — pretraži sistem (params: {query: string})
unknown           — nije prepoznata komanda (params: {text: string})

PRAVILA:
- "otvori/prikaži/nađi predmet X" → navigate_predmet({query:X})
- "analiziraj dokument" ili "pogledaj dokumente" → show_tab({tab:"dokumenti"})
- "uradi AI analizu" ili "proceni predmet" → procena_rizika
- "idi na rokove/naplatu/strategiju/dokumenti" → show_tab odgovarajući tab
- "pokreni tajmer" / "počni naplatу" → start_timer
- "zaustavi tajmer" / "stopi" → stop_timer
- "idi na dashboard" / "početna" / "komandni centar" → show_dashboard
- "postavi pitanje o X" ili konkretno pravno pitanje → ask_question({text: pitanje})
- "napravi tužbu/žalbu/ugovor" → generate_document
- "proceni rizik" / "kakav je rizik" → procena_rizika
- "uradi red team" / "napravi strategiju" → red_team
- "pripremi ročište" / "šta treba za ročište" → hearing_prep

SLOŽENE KOMANDE (vraćaj actions niz):
- "otvori predmet X i analiziraj dokument" → [navigate_predmet(X, wait_ms:0), show_tab(dokumenti, wait_ms:2200)]
- "otvori predmet X i idi na rokove" → [navigate_predmet(X, wait_ms:0), show_tab(rokovi, wait_ms:2200)]
- "otvori predmet X i postavi pitanje o Y" → [navigate_predmet(X, wait_ms:0), ask_question(Y, wait_ms:2200)]
- "otvori predmet X i pokreni tajmer" → [navigate_predmet(X, wait_ms:0), start_timer(wait_ms:2500)]

odgovor = 1 kratak rečenica šta se radi (bez emojija), max 12 reči.

Vrati SAMO JSON bez markdown."""


class VoiceCommandReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.post("/command")
@limiter.limit("30/minute")
async def voice_command(req: VoiceCommandReq, request: Request, user=Depends(require_user)):
    """
    Parsira glasovnu komandu i vraća akciju za frontend.

    Body: {"text": "otvori mi predmet Petrović i analiziraj ga"}
    Response: {"action": "navigate_predmet", "params": {"query": "Petrović"}, "followup": "analyze_predmet"}
    """
    text = req.text.strip()
    if not text:
        return {"action": "unknown", "params": {"text": ""}, "followup": None}

    logger.info("[VOICE] Korisnik=%s komanda='%s'", user["user_id"][:8], text[:100])

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
                {"role": "user", "content": f"Komanda: {text}"},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("[VOICE] Parse greška: %s", exc)
        parsed = {"actions": [{"action": "ask_question", "params": {"text": text}, "wait_ms": 0}], "odgovor": ""}

    # Normalizuj: ako GPT vrati stari format {action, params}, konvertuj
    if "action" in parsed and "actions" not in parsed:
        actions = [{"action": parsed["action"], "params": parsed.get("params", {}), "wait_ms": 0}]
        if parsed.get("followup"):
            actions.append({"action": parsed["followup"], "params": {}, "wait_ms": 2200})
        parsed = {"actions": actions, "odgovor": parsed.get("odgovor", "")}

    actions = parsed.get("actions") or []
    if not actions:
        actions = [{"action": "unknown", "params": {"text": text}, "wait_ms": 0}]

    odgovor = parsed.get("odgovor", "")

    logger.info("[VOICE] %d akcija(e): %s", len(actions), [a.get("action") for a in actions])

    return {
        "actions":  actions,
        "odgovor":  odgovor,
        "original": text,
        # Backward compat polja (stari frontend format)
        "action":   actions[0].get("action") if actions else "unknown",
        "params":   actions[0].get("params", {}) if actions else {},
        "followup": actions[1].get("action") if len(actions) > 1 else None,
    }


class VoiceFeedbackReq(BaseModel):
    action:   str
    uspeh:    bool
    text:     Optional[str] = None
    response: Optional[str] = None
    komentar: Optional[str] = None


@router.post("/feedback")
async def voice_feedback(req: VoiceFeedbackReq, user=Depends(require_user)):
    """Beleži da li je akcija bila ispravno interpretirana (za buduće poboljšanje)."""
    uid = user["user_id"]
    logger.info("[VOICE_FB] user=%s action=%s uspeh=%s", uid[:8], req.action, req.uspeh)
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
        logger.warning("[VOICE_FB] Greška pri čuvanju u usage_events: %s", exc)
    return {"ok": True}
