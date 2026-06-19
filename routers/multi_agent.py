# -*- coding: utf-8 -*-
"""
Multi-Agent Orchestration — 6 specijalizovanih AI agenata.

POST /api/agents/run
Agenti: intake | research | drafting | litigation | billing | deadline
"""
import logging
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from shared.deps import _get_supa, get_current_user

logger = logging.getLogger("vindex.multi_agent")
router = APIRouter(prefix="/api/agents", tags=["agents"])

# ── Sistemski promptovi po agentu ───────────────────────────────────────────

_AGENTS: dict = {
    "intake": {
        "naziv": "Intake Agent",
        "ikona": "📥",
        "opis":  "Prima i analizira inicijalne informacije od klijenta",
        "system": """Ti si Intake Agent — specijalizovan za prijem novih klijenata.
Analiziraš opisanu situaciju i izvlačiš:
1. Tip spora (parnicno/krivicno/radno/upravno/porodicno/privredno/nepokretnosti/ostalo)
2. Ko je klijent, ko je suprotna strana
3. Ključna pravna pitanja
4. Hitnost (da li postoje rokovi koji ističu uskoro)
5. Potrebni dokumenti za sledeći korak
6. Preporuka: prihvatiti predmet ili ne (i zašto)

Format: strukturiran odgovor sa jasnim sekcijama. Srpski jezik.""",
    },
    "research": {
        "naziv": "Research Agent",
        "ikona": "🔍",
        "opis":  "Pretražuje relevantnu sudsku praksu i zakone",
        "system": """Ti si Research Agent — specijalizovan za pravna istraživanja.
Za dato pravno pitanje pronalazi:
1. Relevantne zakonske odredbe (tačne članove)
2. Sudsku praksu (sa referentnim brojevima ako su poznate)
3. Doktrinarne stavove
4. Analogna tumačenja

Budi konkretan, citaj tačne članove i uvek navedi izvor.
Format: strukturiran izveštaj sa sekcijama. Srpski jezik.""",
    },
    "drafting": {
        "naziv": "Drafting Agent",
        "ikona": "✍️",
        "opis":  "Generiše pravne dokumente i podneske",
        "system": """Ti si Drafting Agent — specijalizovan za pisanje pravnih dokumenata.
Generiši dokument koji je:
1. Formalno ispravan (pravna terminologija)
2. Konkretno prilagođen opisanom predmetu
3. Sa svim potrebnim zakonskim referencama
4. Strukturiran prema sudskim standardima

UVEK navedi da dokument treba pregledati advokat pre podnošenja.
Srpski jezik.""",
    },
    "litigation": {
        "naziv": "Litigation Agent",
        "ikona": "⚔️",
        "opis":  "Napada argumentaciju i pronalazi slabosti",
        "system": """Ti si Litigation Agent — preuzimas ulogu protivničkog advokata.
Analiziraš argumentaciju klijenta i:
1. Identificuješ 3-5 ključnih slabosti
2. Za svaku slabost predlaješ kako će je protivnik iskoristiti
3. Predlaješ kontra-argumente i načine jačanja pozicije
4. Daješ realnu procenu šansi (0-100%)

Budi nemilosrdan u analizi — tvoj cilj je da pronađeš sve što može poći po zlu.
Srpski jezik.""",
    },
    "billing": {
        "naziv": "Billing Agent",
        "ikona": "💰",
        "opis":  "Saveti o naplati i AKS tarifi",
        "system": """Ti si Billing Agent — specijalizovan za naplatu advokatskih usluga.
Pomažeš advokatu da:
1. Pravilno primeni AKS tarifu (Sl. gl. RS 56/2025)
2. Identifikuje sve naplatne radnje u predmetu
3. Odredi optimalnu strategiju naplate
4. Prepozna propuštenu naplatu

Budi konkretan sa tarifnim stavkama i iznosima. Srpski jezik.""",
    },
    "deadline": {
        "naziv": "Deadline Agent",
        "ikona": "⏰",
        "opis":  "Prati i upravlja procesnim rokovima",
        "system": """Ti si Deadline Agent — specijalizovan za procesne rokove.
Za dati predmet:
1. Identifikuješ sve tekuće procesne rokove
2. Upozoravaš na kritične rokove (7 i 3 dana)
3. Objašnjavaš posledice propuštanja svakog roka
4. Predlaješ plan upravljanja rokovima

Budi precizan sa datumima i zakonskim osnovama rokova.
Srpski jezik.""",
    },
}

_ROUTER_SYSTEM = """Ti si orchestrator multi-agent sistema.
Na osnovu korisnikovog zahteva, odredi koji agent treba da odgovori.
Vrati JSON: {"agent": "<naziv>", "razlog": "<kratko objašnjenje>"}
Dostupni agenti: intake, research, drafting, litigation, billing, deadline"""


class AgentReq(BaseModel):
    agent:      Optional[str] = None  # ako None, auto-select
    task:       str
    predmet_id: Optional[str] = None
    kontekst:   Optional[str] = None


@router.get("/lista")
async def lista_agenata():
    """Vraća listu dostupnih agenata."""
    return {"agenti": [
        {"id": k, "naziv": v["naziv"], "ikona": v["ikona"], "opis": v["opis"]}
        for k, v in _AGENTS.items()
    ]}


@router.post("/run")
async def run_agent(req: AgentReq, user=Depends(get_current_user)):
    """Pokreće izabrani agent ili automatski bira najprikladniji."""
    supa = _get_supa()
    uid  = user["user_id"]

    # ── Auto-selekcija agenta ────────────────────────────────────────────────
    agent_id = req.agent
    if not agent_id:
        try:
            from openai import OpenAI
            client = OpenAI()
            sel = client.chat.completions.create(
                model="gpt-4o-mini", temperature=0, max_tokens=60,
                messages=[
                    {"role": "system", "content": _ROUTER_SYSTEM},
                    {"role": "user",   "content": req.task},
                ],
            )
            raw = (sel.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("```"))
            parsed = json.loads(raw)
            agent_id = parsed.get("agent", "research")
        except Exception as exc:
            logger.warning("[AGENT] auto-select greška: %s", exc)
            agent_id = "research"

    if agent_id not in _AGENTS:
        raise HTTPException(status_code=400, detail=f"Nepoznat agent: {agent_id}")

    agent_cfg = _AGENTS[agent_id]

    # ── Dohvati kontekst predmeta ────────────────────────────────────────────
    predmet_ctx = ""
    if req.predmet_id:
        try:
            pr = supa.table("predmeti").select(
                "naziv,tip,status,tuzilac,tuzeni,opis"
            ).eq("id", req.predmet_id).eq("user_id", uid).execute()
            if pr.data:
                p = pr.data[0]
                predmet_ctx = (
                    f"\nKontekst predmeta: {p.get('naziv','?')} | Tip: {p.get('tip','?')} | "
                    f"Status: {p.get('status','?')}\n"
                    f"Tužilac: {p.get('tuzilac','?')} | Tuženi: {p.get('tuzeni','?')}\n"
                )
                if p.get("opis"):
                    predmet_ctx += f"Opis: {p['opis'][:400]}\n"
        except Exception as exc:
            logger.debug("[AGENT] predmet ctx greška: %s", exc)

    # ── Pozovi agent ─────────────────────────────────────────────────────────
    user_msg = f"{predmet_ctx}\n{req.kontekst or ''}\n\nZahtev: {req.task}".strip()

    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0.35,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": agent_cfg["system"]},
                {"role": "user",   "content": user_msg},
            ],
        )
        odgovor = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.error("[AGENT] GPT greška: %s", exc)
        raise HTTPException(status_code=503, detail="AI servis trenutno nedostupan.")

    logger.info("[AGENT] user=%s agent=%s predmet=%s", uid[:8], agent_id, req.predmet_id or "-")

    return {
        "agent":     agent_id,
        "naziv":     agent_cfg["naziv"],
        "ikona":     agent_cfg["ikona"],
        "odgovor":   odgovor,
        "task":      req.task,
    }
