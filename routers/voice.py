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

_INTENT_SYSTEM = """Ti si glasovni asistent za Vindex AI — pravni operativni sistem.

Korisnik je advokat koji govori srpski. Pretvori njegovu komandu u strukturiranu akciju.

Vrati JSON objekat sa poljem "action" i "params". Primer:
{"action": "navigate_predmet", "params": {"query": "Petrović"}}

Dostupne akcije:
- navigate_predmet — otvori predmet (params: {query: naziv klijenta ili predmeta})
- analyze_predmet — pokreni AI analizu otvorenog predmeta (params: {})
- ask_question — postavi pravno pitanje agentu (params: {text: pitanje})
- generate_document — generiši dokument (params: {tip: "tuzba"|"zalba"|"ugovor"|"podnesak"})
- show_tab — pređi na tab (params: {tab: "rokovi"|"naplata"|"dokumenti"|"strategija"|"ai-analiza"|"pregled"|"timeline"|"dokazi"})
- start_timer — pokreni tajmer (params: {})
- stop_timer — zaustavi tajmer (params: {})
- show_dashboard — idi na dashboard (params: {})
- show_klijenti — idi na klijente (params: {})
- search — pretraži (params: {query: tekst pretrage})
- procena_rizika — pokreni procenu rizika (params: {})
- red_team — pokreni red team analizu (params: {})
- hearing_prep — priprema za ročište (params: {})
- unknown — nismo razumeli komandu (params: {text: originalni tekst})

Pravila:
- Ako korisnik kaže "otvori mi predmet X" ili "prikaži predmet X" → navigate_predmet
- Ako kaže "analiziraj" ili "uradi analizu" → analyze_predmet
- Ako kaže "postavi pitanje" ili "pitaj agenta" ili konkretno pravno pitanje → ask_question
- Ako kaže "napravi tužbu" / "generiši žalbu" itd. → generate_document
- Ako kaže "prikaži rokove" / "idi na naplatu" itd. → show_tab
- Ako kaže "pokreni tajmer" → start_timer
- Ako kaže "zaustavi tajmer" / "stopi tajmer" → stop_timer
- Ako kaže "idi na dashboard" / "početna" → show_dashboard
- Ako kaže "proceni rizik" ili "kakav je rizik" → procena_rizika

Vrati SAMO JSON bez markdown fenci."""


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
            max_tokens=200,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM},
                {"role": "user", "content": f"Komanda: {text}"},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("[VOICE] Parse greška: %s", exc)
        parsed = {"action": "ask_question", "params": {"text": text}}

    action = parsed.get("action", "unknown")
    params = parsed.get("params", {})

    # Složene komande — "otvori predmet X i analiziraj ga"
    followup = None
    text_lower = text.lower()
    if action == "navigate_predmet" and ("analiz" in text_lower):
        followup = "analyze_predmet"
    if action == "navigate_predmet" and ("izveštaj" in text_lower or "izvestaj" in text_lower):
        followup = "analyze_predmet"

    logger.info("[VOICE] Action=%s params=%s followup=%s", action, params, followup)

    return {
        "action":   action,
        "params":   params,
        "followup": followup,
        "original": text,
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
