# -*- coding: utf-8 -*-
"""
Vindex AI — Decision Replay

Rekonstruise vremenski tok predmeta i analizira gde je doslo do kriticnih momenata.
"Zasto smo izgubili predmet?" — AI prelazi kroz sve dogadjaje hronoloski.

GET /api/predmeti/{predmet_id}/replay
GET /api/predmeti/{predmet_id}/replay/timeline   — samo timeline bez AI analize (brzo)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from datetime import date
from shared import rokovi as _rokovi_domen
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.deps import _get_supa, get_current_user
from shared.llm_retry import llm_retry
from shared.permissions import PermissionService
from shared.rate import limiter
from shared.sentry import capture_exception as _sentry_capture
from shared.usage import UsageService

logger = logging.getLogger("vindex.decision_replay")
router = APIRouter(prefix="/api/predmeti", tags=["decision_replay"])

# ─── Prompt ───────────────────────────────────────────────────────────────────

_REPLAY_SYSTEM = """Ti si pravni analitičar koji rekonstruise tok predmeta.

Data ti je hronoloski sortirana istorija dogadjaja na predmetu:
odluke, rokovi, rocista, AI preporuke, alertovi, ishod.

Analiziraj i identifikuj:
1. Kriticne momente — tacke u kojima je mogla biti donesena drugacija odluka
2. Propustene prilike — sta je moglo biti uradjeno a nije
3. Sto je presudilo ishodu

Vrati JSON:
{
  "kljucni_momenti": [
    {
      "datum": "<datum dogadjaja>",
      "dogadjaj": "<sta se desilo>",
      "alternativa": "<sta je moglo biti uradjeno umesto toga>",
      "procena_uticaja": "<kako bi alternativa promenila tok: visok | srednji | nizak>",
      "tip": "<propustena_prilika | ispravna_odluka | kljucna_greska>"
    }
  ],
  "presudni_faktor": "<JEDAN najvazniiji faktor koji je odredio ishod>",
  "lekcija": "<konkretna lekcija za buduce predmete>",
  "alternativni_scenario": "<kratki opis kako bi predmet izgledao da je kriticni momenat bio drugaciji>",
  "pouzdanost_analize": "<visoka | srednja | niska — zavisno od potpunosti podataka>"
}

Samo JSON. Srpski jezik. Budi konkretan. Koristi konkretne datume iz podataka."""

# ─── Helper: prikupljanje svih dogadjaja ─────────────────────────────────────

_TIP_LABELE = {
    "decision_log": "Odluka",
    "rok": "Rok",
    "rociste": "Rociste",
    "ai_preporuka": "AI preporuka",
    "alert": "Alert",
    "outcome": "Ishod",
    "dokument": "Dokument",
}


async def _gather_timeline_events(supa, predmet_id: str, user_id: str) -> list[dict]:
    """Prikuplja sve dogadjaje iz svih tabela i vraca listu sortiranu po datumu."""

    predmet_row, decisions_row, rokovi_row, rocista_row, recs_row, outcome_row, alerts_row = await asyncio.gather(
        asyncio.to_thread(
            lambda: supa.table("predmeti")
            .select("naziv, tip, status, oblast_prava, datum_otvaranja, datum_zatvaranja, ishod")
            .eq("id", predmet_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("decision_log")
            .select("opis, tip_odluke, alternativa, kontekst, created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        ),
        # BETA-DEADLINE-DOMAIN-001: kanonski izvor. Prozor je namerno sirok --
        # replay gleda ceo zivot predmeta, ne narednih 7 dana.
        _rokovi_domen.rokovi_za_predmet(
            supa, user_id, predmet_id,
            od=date(2000, 1, 1), do=date(2100, 1, 1), limit=200),
        asyncio.to_thread(
            lambda: supa.table("rocista")
            .select("sud, datum, vreme, status, napomena")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .order("datum")
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("recommendation_log")
            .select("preporuka, tip_slucaja, prihvacena, confidence_band, created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("outcome_log")
            .select("ishod, uzroci, kontekst_poraza, created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supa.table("proactive_alerts")
            .select("tekst_alerta, tip_alerta, hitnost, created_at")
            .eq("predmet_id", predmet_id)
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        ),
    )

    events: list[dict] = []

    # Odluke
    for d in (decisions_row.data or []):
        if d.get("tip_odluke") == "intelligence_briefing":
            continue
        events.append({
            "datum": d.get("created_at", "")[:10],
            "datum_full": d.get("created_at", ""),
            "tip": "decision_log",
            "tip_label": "Odluka",
            "opis": d.get("opis", ""),
            "detalji": {"tip_odluke": d.get("tip_odluke"), "alternativa": d.get("alternativa")},
            "kriticnost": "srednja",
        })

    # Rokovi — BETA-DEADLINE-DOMAIN-001.
    #
    # Stara `rokovi.status` kolona ("prekoracen"/"propusten") nije nedostajuca
    # sema nego IZVEDENA vrednost: rok je prekoracen ako mu je datum u
    # proslosti. Kanonski sloj to vec racuna (`Rok.prekoracen`), pa se ovde
    # nista ne izmislja niti gubi.
    if not rokovi_row.uspeh:
        raise HTTPException(
            status_code=503,
            detail="Rokovi nisu dostupni — replay bi prikazao nepotpunu istoriju.")
    for r in rokovi_row.rokovi:
        status = "prekoracen" if r.prekoracen else "aktivan"
        events.append({
            "datum": r.datum.isoformat(),
            "datum_full": r.datum.isoformat(),
            "tip": "rok",
            "tip_label": "Rok",
            "opis": f"{r.naslov} — status: {status}",
            "detalji": {"vaznost": r.vaznost, "status": status},
            "kriticnost": "visoka" if (r.prekoracen or r.vaznost == "kritičan") else "srednja",
        })

    # Rocista
    for ro in (rocista_row.data or []):
        datum = ro.get("datum", "")
        events.append({
            "datum": datum[:10] if datum else "",
            "datum_full": datum,
            "tip": "rociste",
            "tip_label": "Rociste",
            "opis": f"Ročište ({ro.get('sud', 'Sud')}) — {(ro.get('napomena') or '')[:120]}",
            "detalji": {"status": ro.get("status")},
            "kriticnost": "srednja",
        })

    # AI preporuke
    for rec in (recs_row.data or []):
        prihvacena = rec.get("prihvacena")
        kriticnost = "niska"
        status_txt = "prihvacena" if prihvacena else ("odbijena" if prihvacena is False else "nije ocenjena")
        if prihvacena is False:
            kriticnost = "visoka"  # odbijena AI preporuka = potencijalni kljucni momenat
        events.append({
            "datum": rec.get("created_at", "")[:10],
            "datum_full": rec.get("created_at", ""),
            "tip": "ai_preporuka",
            "tip_label": "AI preporuka",
            "opis": f"[{rec.get('confidence_band', '?')} pouzdanost] {rec.get('preporuka', '')[:150]} — {status_txt}",
            "detalji": {"prihvacena": prihvacena, "confidence_band": rec.get("confidence_band")},
            "kriticnost": kriticnost,
        })

    # Alertovi
    for a in (alerts_row.data or []):
        events.append({
            "datum": a.get("created_at", "")[:10],
            "datum_full": a.get("created_at", ""),
            "tip": "alert",
            "tip_label": "Alert",
            "opis": f"[{a.get('hitnost','?')}] {a.get('tekst_alerta','')[:150]}",
            "detalji": {"tip_alerta": a.get("tip_alerta"), "hitnost": a.get("hitnost")},
            "kriticnost": "visoka" if a.get("hitnost") == "hitno" else "srednja",
        })

    # Ishod
    for o in (outcome_row.data or []):
        events.append({
            "datum": o.get("created_at", "")[:10],
            "datum_full": o.get("created_at", ""),
            "tip": "outcome",
            "tip_label": "Ishod",
            "opis": f"Ishod: {o.get('ishod', 'N/A')} | Uzroci: {', '.join(o.get('uzroci') or [])}",
            "detalji": {"ishod": o.get("ishod"), "kontekst_poraza": o.get("kontekst_poraza")},
            "kriticnost": "visoka",
        })

    # Sortiraj po datumu
    events.sort(key=lambda e: e.get("datum_full") or "")
    return events, (predmet_row.data or {}), (outcome_row.data[0] if outcome_row.data else None)


@llm_retry
async def _pozovi_replay_api(client, timeline_tekst: str):
    """CELINA 4 (2026-07-24): @llm_retry -- max 3 pokušaja sa exponential
    backoff-om za rate-limit/5xx/timeout/connection greške."""
    return await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _REPLAY_SYSTEM},
            {"role": "user", "content": timeline_tekst[:9000]}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{predmet_id}/replay/timeline")
@limiter.limit("30/minute")
async def get_timeline(request: Request, predmet_id: str, user=Depends(get_current_user)):
    """Hronoloski timeline dogadjaja na predmetu — brzo, bez AI analize."""
    supa = _get_supa()
    try:
        events, predmet, ishod = await _gather_timeline_events(supa, predmet_id, user["user_id"])
        if not predmet:
            raise HTTPException(404, "Predmet nije pronadjen")

        return {
            "predmet_id": predmet_id,
            "predmet_naziv": predmet.get("naziv"),
            "status": predmet.get("status"),
            "timeline": events,
            "ukupno_dogadjaja": len(events),
            "kriticnih": sum(1 for e in events if e.get("kriticnost") == "visoka"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{predmet_id}/replay")
@limiter.limit("10/minute")
async def decision_replay(request: Request, predmet_id: str, user=Depends(PermissionService.require("decision_replay"))):
    """Decision Replay — AI rekonstruise tok predmeta i identifikuje kriticne momente.

    Odgovara na: 'Zasto smo izgubili predmet?'
    Vraca: timeline + kljucni momenti + presudni faktor + lekcija + alternativni scenario.
    """
    supa = _get_supa()
    try:
        events, predmet, ishod_data = await _gather_timeline_events(supa, predmet_id, user["user_id"])

        if not predmet:
            raise HTTPException(404, "Predmet nije pronadjen")

        if len(events) < 2:
            return {
                "predmet_id": predmet_id,
                "timeline": events,
                "ai_analiza": None,
                "poruka": "Nedovoljno dogadjaja za replay analizu. Potrebne su odluke, rokovi ili rocista.",
            }

        # Formiraj tekst za GPT
        timeline_tekst = (
            f"PREDMET: {predmet.get('naziv')} | Tip: {predmet.get('tip')} | "
            f"Oblast: {predmet.get('oblast_prava')} | Status: {predmet.get('status')}\n\n"
            f"HRONOLOSKI TOK ({len(events)} dogadjaja):\n"
        )
        for e in events:
            kriticnost_mark = "!" if e.get("kriticnost") == "visoka" else " "
            timeline_tekst += f"{kriticnost_mark} {e['datum']} | {e['tip_label']}: {e['opis']}\n"

        if ishod_data:
            timeline_tekst += f"\nKONACNI ISHOD: {ishod_data.get('ishod', 'N/A')}"
            if ishod_data.get("kontekst_poraza"):
                timeline_tekst += f"\nKONTEKST PORAZA: {ishod_data['kontekst_poraza']}"

        import openai
        client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = await _pozovi_replay_api(client, timeline_tekst)

        analiza = json.loads(resp.choices[0].message.content)

        await UsageService.consume(user["user_id"], user.get("email", ""), "decision_replay")

        return {
            "predmet_id": predmet_id,
            "predmet_naziv": predmet.get("naziv"),
            "predmet_status": predmet.get("status"),
            "ishod": ishod_data.get("ishod") if ishod_data else None,
            "timeline": events,
            "ukupno_dogadjaja": len(events),
            "kriticnih_dogadjaja": sum(1 for e in events if e.get("kriticnost") == "visoka"),
            "kljucni_momenti": analiza.get("kljucni_momenti", []),
            "presudni_faktor": analiza.get("presudni_faktor"),
            "lekcija": analiza.get("lekcija"),
            "alternativni_scenario": analiza.get("alternativni_scenario"),
            "pouzdanost_analize": analiza.get("pouzdanost_analize"),
        }

    except HTTPException:
        raise
    except Exception as e:
        _sentry_capture(e)
        logger.error("decision_replay: %s", e)
        raise HTTPException(500, str(e))
