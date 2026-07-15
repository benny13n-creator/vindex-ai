# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_classify.py

Smart Intake Engine, Faza 1A — dokument klasifikacija. Hibridna: keyword
heuristika prvo (jeftino, brzo, visoko pouzdano za očigledne slučajeve —
"ТУЖБА" u prvih 200 karaktera je tužba sa skoro sigurnošću), LLM samo za
ono što heuristika ne prepozna (design review §8, §23.6 — pure-LLM
klasifikacija je skuplja i manje objašnjiva bez ikakve stvarne dobiti kad
heuristika već pokriva očigledan slučaj).

12 tipova + 'other' — isti skup definisan u migraciji 074 (CHECK constraint).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("vindex.intake_classify")

DOCUMENT_TYPES = (
    "lawsuit", "response", "appeal", "judgment", "contract", "invoice",
    "power_of_attorney", "evidence", "email", "court_decision",
    "enforcement", "legal_opinion", "other",
)

# Ključne reči tražene u prvih _HEAD_CHARS karaktera teksta — dovoljno da
# uhvati naslov/zaglavlje dokumenta bez skeniranja celog teksta. Ćirilica i
# latinica namerno paralelno, srpski pravni dokumenti mešaju oba pisma.
_HEAD_CHARS = 400
_HEURISTICS: list[tuple[str, list[str]]] = [
    ("lawsuit",           ["ТУЖБА", "TUŽBA", "TUZBA"]),
    ("appeal",             ["ЖАЛБА", "ŽALBA", "ZALBA", "PRIGOVOR", "ПРИГОВОР"]),
    ("response",           ["ОДГОВОР НА ТУЖБУ", "ODGOVOR NA TUŽBU", "ODGOVOR NA TUZBU"]),
    ("judgment",           ["ПРЕСУДА", "PRESUDA"]),
    ("court_decision",     ["РЕШЕЊЕ", "REŠENJE", "RESENJE"]),
    ("enforcement",        ["РЕШЕЊЕ О ИЗВРШЕЊУ", "IZVRŠNI PREDLOG", "IZVRSNI PREDLOG", "ПРЕДЛОГ ЗА ИЗВРШЕЊЕ"]),
    ("power_of_attorney",  ["ПУНОМОЋЈЕ", "PUNOMOĆJE", "PUNOMOCJE"]),
    ("contract",           ["УГОВОР", "UGOVOR"]),
    ("invoice",            ["ФАКТУРА", "FAKTURA", "РАЧУН", "RAČUN", "RACUN"]),
    ("legal_opinion",      ["ПРАВНО МИШЉЕЊЕ", "PRAVNO MIŠLJENJE", "PRAVNO MISLJENJE"]),
]


def classify_heuristic(text: str) -> tuple[str, float] | None:
    """Vraća (document_type, confidence) ako je neka ključna reč prepoznata
    u zaglavlju teksta, inače None (poziva se LLM fallback). Confidence je
    namerno konzervativan (0.85) — dovoljno visok za auto-accept prag (§14
    dizajn review, ≥90% opšte, ali klasifikacija ovde nosi manji rizik od
    case-matcha pa je 85% prihvatljivo kao heuristički signal, ne slepo
    veruj — LLM fallback postoji baš za slučajeve gde ovo nije dovoljno)."""
    head = (text or "")[:_HEAD_CHARS].upper()
    for doc_type, keywords in _HEURISTICS:
        for kw in keywords:
            if kw.upper() in head:
                return doc_type, 0.85
    return None


_LLM_SYSTEM = """Ti si klasifikator pravnih dokumenata za srpske advokate. Na osnovu teksta dokumenta, odredi tip dokumenta.

Vrati ISKLJUČIVO validan JSON bez markdown fence-ova:
{
  "document_type": "<jedan od: lawsuit, response, appeal, judgment, contract, invoice, power_of_attorney, evidence, email, court_decision, enforcement, legal_opinion, other>",
  "confidence": <broj između 0 i 1, tvoja iskrena procena sigurnosti>
}

Ako nisi siguran, koristi "other" sa niskom pouzdanošću — NIKAD ne izmišljaj tip samo da bi dao odgovor."""


async def classify_llm(text: str) -> tuple[str, float]:
    """LLM fallback — poziva se SAMO kad heuristika ne prepozna ništa.
    Vraća (document_type, confidence); confidence dolazi direktno iz
    modelovog samoprocenjivanja (objašnjeno korisniku kao takvo, ne
    predstavljeno kao egzaktna mera)."""
    import json
    import os
    from openai import AsyncOpenAI

    oai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    excerpt = (text or "")[:3000]

    for attempt in range(3):
        try:
            r = await oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM},
                    {"role": "user", "content": excerpt},
                ],
                temperature=0.1,
                max_tokens=100,
                response_format={"type": "json_object"},
            )
            raw = (r.choices[0].message.content or "{}").strip()
            parsed = json.loads(raw)
            doc_type = parsed.get("document_type", "other")
            confidence = float(parsed.get("confidence", 0.5))
            if doc_type not in DOCUMENT_TYPES:
                logger.warning("[INTAKE_CLASSIFY] LLM vratio nepoznat tip '%s' — koristim 'other'.", doc_type)
                doc_type, confidence = "other", 0.3
            return doc_type, max(0.0, min(1.0, confidence))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[INTAKE_CLASSIFY] parse greška (pokušaj %d/3): %s", attempt + 1, e)
        except Exception as e:
            logger.error("[INTAKE_CLASSIFY] OpenAI greška: %s", e)
            return "other", 0.0
    logger.error("[INTAKE_CLASSIFY] LLM klasifikacija neuspešna posle 3 pokušaja — 'other' sa confidence=0.")
    return "other", 0.0


async def classify(text: str) -> dict:
    """Glavna ulazna tačka — vraća {document_type, confidence, method}."""
    heuristic = classify_heuristic(text)
    if heuristic:
        doc_type, confidence = heuristic
        return {"document_type": doc_type, "confidence": confidence, "method": "heuristic"}

    doc_type, confidence = await classify_llm(text)
    return {"document_type": doc_type, "confidence": confidence, "method": "llm"}
