# -*- coding: utf-8 -*-
"""
Vindex AI — services/agent_tasks/precedents_radar.py

KORAK B: Autonomni "Background" Action Agenti (2026-07-24)

Za svaki aktivan predmet korisnika sa popunjenim Case Genome-om
(predmeti.case_dna), pretražuje sudsku praksu preko VEĆ POSTOJEĆEG RAG
pipeline-a (app.services.retrieve.retrieve_sudska_praksa +
process_praksa_chunks — ista logika koja stoji iza /api/praksa i shared/
voice_tools.py) i za svaku novu, dovoljno-relevantnu odluku pita LLM
(@llm_retry) da li ona PODUPIRE ili OSPORAVA pravnu poziciju iz Case
Genome-a. Preporuka se kreira SAMO ako je klasifikacija jasna
(podupire/osporava) -- neutralne/nejasne odluke se tiho odbacuju da agent
ne zatrpa korisnika šumom.

Agent NIKAD ne piše u predmete/case_dna — samo čita odatle i piše
ISKLJUČIVO u agent_recommendations (predlog, ne akcija).
"""
import asyncio
import json
import logging
from typing import Optional

from shared.llm_retry import llm_retry
from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.agent_tasks.precedents_radar")

AGENT_TYPE = "precedents_radar"

_MAX_PREDMETI_PER_RUN = 20   # budžetska zaštita nezavisna od org-level budžeta u workers/
_TOP_K_PRAKSA = 5

_KLASIFIKACIJA_SYSTEM = """Ti si pravni analitičar. Dobijaš pravnu poziciju iz predmeta i
tekst nove sudske odluke. Oceni odnos odluke prema poziciji.

Vrati SAMO JSON: {"odnos": "podupire"|"osporava"|"neutralno", "obrazlozenje": "1 rečenica na srpskom"}

"podupire" — odluka ide u prilog pravnoj poziciji predmeta.
"osporava" — odluka ide protiv pravne pozicije predmeta, rizik za predmet.
"neutralno" — odluka nije dovoljno direktno povezana da bi menjala procenu.

Budi konzervativan: koristi "neutralno" osim ako je veza jasna i konkretna."""


@llm_retry
def _pozovi_klasifikaciju(pozicija: str, odluka_tekst: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=200,
        timeout=20.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _KLASIFIKACIJA_SYSTEM},
            {"role": "user", "content": f"PRAVNA POZICIJA PREDMETA:\n{pozicija}\n\nNOVA ODLUKA:\n{odluka_tekst[:2000]}"},
        ],
    )
    return (r.choices[0].message.content or "{}").strip()


async def _klasifikuj(pozicija: str, odluka_tekst: str) -> dict:
    try:
        raw = await asyncio.to_thread(_pozovi_klasifikaciju, pozicija, odluka_tekst)
        return json.loads(raw)
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[PRECEDENTS_RADAR] klasifikacija neuspešna: %s", e)
        return {"odnos": "neutralno", "obrazlozenje": ""}


def _pravna_pozicija_iz_genoma(genome: dict, oblast_prava: str) -> Optional[str]:
    if not genome or genome.get("greska"):
        return None
    gi = genome.get("pravna_teorija") or {}
    delovi = []
    if oblast_prava:
        delovi.append(f"Oblast: {oblast_prava}.")
    if gi.get("sustina_spora"):
        delovi.append(f"Suština spora: {gi['sustina_spora']}.")
    if gi.get("osnov_odgovornosti"):
        delovi.append(f"Pravni osnov: {gi['osnov_odgovornosti']}.")
    if not delovi:
        return None
    return " ".join(delovi)


def _upit_za_pretragu(genome: dict, oblast_prava: str) -> Optional[str]:
    gi = genome.get("pravna_teorija") or {}
    upit = gi.get("sustina_spora") or gi.get("pravni_identitet") or ""
    if not upit:
        return None
    return f"{oblast_prava} {upit}".strip()


async def run(user_id: str, supa) -> dict:
    """Pokreće agenta za JEDNOG korisnika. Vraća {"predmeta_skenirano": int,
    "preporuke_kreirane": int, "greske": int}. Nikad ne baca."""
    skenirano = 0
    preporuke = 0
    greske = 0

    try:
        pred_r = await asyncio.to_thread(
            lambda: supa.table("predmeti")
                .select("id,naziv,oblast_prava,status,case_dna")
                .eq("user_id", user_id)
                .not_.in_("status", ["zatvoren", "arhiviran"])
                .limit(_MAX_PREDMETI_PER_RUN)
                .execute()
        )
        predmeti = pred_r.data or []
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[PRECEDENTS_RADAR] predmeti upit neuspešan uid=%.8s: %s", user_id[:8], e)
        return {"predmeta_skenirano": 0, "preporuke_kreirane": 0, "greske": 1}

    from app.services.retrieve import retrieve_sudska_praksa, process_praksa_chunks

    for predmet in predmeti:
        genome = predmet.get("case_dna") or {}
        oblast_prava = predmet.get("oblast_prava", "") or ""
        pozicija = _pravna_pozicija_iz_genoma(genome, oblast_prava)
        upit = _upit_za_pretragu(genome, oblast_prava)
        if not pozicija or not upit:
            continue  # nema dovoljno Case Genome sadržaja da bi poređenje imalo smisla

        skenirano += 1
        try:
            raw_matches = await asyncio.to_thread(retrieve_sudska_praksa, upit, max(_TOP_K_PRAKSA, 20))
            odluke = process_praksa_chunks(raw_matches, k=_TOP_K_PRAKSA)
        except Exception as e:
            _sentry_capture(e)
            logger.warning("[PRECEDENTS_RADAR] RAG pretraga neuspešna predmet=%s: %s", predmet["id"], e)
            greske += 1
            continue

        for odluka in odluke:
            decision_number = odluka.get("decision_number", "")
            if not decision_number or not odluka.get("text"):
                continue
            dedup_key = f"precedent:{predmet['id']}:{decision_number}"

            klasifikacija = await _klasifikuj(pozicija, odluka["text"])
            odnos = klasifikacija.get("odnos", "neutralno")
            if odnos not in ("podupire", "osporava"):
                continue  # neutralno/nejasno -- ne zatrpavaj korisnika

            naslov = (
                f"Nova praksa {'u prilog' if odnos == 'podupire' else 'protiv'} predmetu: "
                f"{predmet.get('naziv', '')}"
            )
            opis = f"{odluka.get('court', '')} {odluka.get('date', '')} — {decision_number}"
            payload = {
                "odnos": odnos,
                "obrazlozenje": klasifikacija.get("obrazlozenje", ""),
                "odluka": {
                    "decision_number": decision_number,
                    "court": odluka.get("court", ""),
                    "date": odluka.get("date", ""),
                    "matter": odluka.get("matter", ""),
                    "score": odluka.get("score", 0.0),
                },
            }

            try:
                await asyncio.to_thread(
                    lambda: supa.table("agent_recommendations").insert({
                        "user_id":    user_id,
                        "predmet_id": predmet["id"],
                        "agent_type": AGENT_TYPE,
                        "naslov":     naslov,
                        "opis":       opis,
                        "payload":    payload,
                        "dedup_key":  dedup_key,
                    }).execute()
                )
                preporuke += 1
            except Exception as e:
                if "duplicate key" not in str(e).lower() and "23505" not in str(e):
                    _sentry_capture(e)
                    logger.warning("[PRECEDENTS_RADAR] insert preporuke neuspešan: %s", e)
                    greske += 1

    return {"predmeta_skenirano": skenirano, "preporuke_kreirane": preporuke, "greske": greske}
