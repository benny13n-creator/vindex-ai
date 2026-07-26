# -*- coding: utf-8 -*-
"""
Vindex AI — services/quality_gate.py

Institutional Memory Architecture V2 (2026-07-26), STUB 1.2 — Quality Score
Evaluacija. Pre nego što bilo koji AI-generisan nacrt uđe u staging_memory
(v. routers/drafting.py's _stage_draft_for_review), izračunava
confidence_score (0.00-1.00) na osnovu:

  1. Validnost citiranih propisa -- NIJE puna LRE (services/
     legal_reasoning_engine.py) integracija: LRE je case/genome-specifičan
     reasoning-graph generator (zahteva predmet_id + facts + genome), ne
     generički "proveri citate u proizvoljnom tekstu" alat. Umesto
     forsiranog nefit-a, ovde se ponovo koriste već postojeći, dokazani
     RAG helperi (app.services.retrieve._izvuci_broj_clana +
     _direktan_fetch_clana) da se svaki "Član N" citat u nacrtu proveri
     protiv stvarno indeksiranog zakonskog korpusa -- lakša ali POŠTENA
     provera (stvarno postoji u bazi, ne halucinacija), transparentno
     nazvana "citation_score", ne predstavljena kao nešto šire.
  2. Kompletnost formalnih elemenata (sud, stranke, pravni osnov) --
     heuristika ključnih reči, dokumentovano kao takva.

confidence_score = 0.6 * citation_score + 0.4 * completeness_score
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger("vindex.quality_gate")

_CLAN_PATTERN = re.compile(r"(?:[Čč]lan|čl\.|cl\.)\s*(\d+[a-zA-Z]?)", re.IGNORECASE)

_COMPLETENESS_CHECKS: dict[str, re.Pattern] = {
    "sud":          re.compile(r"\bsud\w*\b", re.IGNORECASE),
    "stranke":      re.compile(r"\b(tuzil\w+|tužil\w+|tuzen\w+|tužen\w+|stranka|stranke|izvrsni\w+|izvršni\w+|duznik\w*|dužnik\w*)\b", re.IGNORECASE),
    "pravni_osnov": re.compile(r"\b(clan|član|čl\.|cl\.|zakon\w*)\b", re.IGNORECASE),
}


def _extract_article_citations(tekst: str) -> list[str]:
    """Vraća SVE 'Član N' citate (za razliku od
    app.services.retrieve._izvuci_broj_clana, koji vraća samo prvi pogodak
    -- ovde treba proveriti svaki citat u nacrtu, ne samo jedan)."""
    return sorted(set(_CLAN_PATTERN.findall(tekst)))


async def _verify_citation(broj_clana: str) -> bool:
    from app.services.retrieve import _direktan_fetch_clana
    try:
        matches = await asyncio.to_thread(_direktan_fetch_clana, f"Član {broj_clana}")
        return bool(matches)
    except Exception as exc:
        logger.warning("[QUALITY_GATE] Provera citata 'Član %s' neuspešna: %s", broj_clana, exc)
        return False


def _completeness_score(tekst: str) -> dict:
    checks = {name: bool(pattern.search(tekst)) for name, pattern in _COMPLETENESS_CHECKS.items()}
    score = sum(checks.values()) / len(checks) if checks else 0.0
    return {"checks": checks, "score": round(score, 2)}


async def evaluate_draft_quality(tekst: str, tip: str = "") -> dict:
    """Vraća {"confidence_score": float, "detail": {...}}.

    Nikad ne baca -- greška u proveri citata degradira na citation_score=0.5
    (neutralno, ne kažnjava niti nagrađuje) umesto da obori ceo quality gate."""
    citations = _extract_article_citations(tekst)
    citations_verified = 0
    if citations:
        try:
            results = await asyncio.gather(*[_verify_citation(c) for c in citations])
            citations_verified = sum(1 for r in results if r)
            citation_score = citations_verified / len(citations)
        except Exception as exc:
            logger.warning("[QUALITY_GATE] Citation verification batch neuspešna: %s", exc)
            citation_score = 0.5
    else:
        # Nema citata u tekstu -- nije crvena zastavica sama po sebi (neki
        # tipovi podnesaka, npr. urgencija, legitimno ne citiraju članove),
        # ali ne zaslužuje ni punu ocenu za ovu komponentu.
        citation_score = 0.7

    completeness = _completeness_score(tekst)

    confidence = round(0.6 * citation_score + 0.4 * completeness["score"], 2)
    confidence = max(0.0, min(1.0, confidence))

    return {
        "confidence_score": confidence,
        "detail": {
            "tip": tip,
            "citations_found": len(citations),
            "citations_verified": citations_verified,
            "citation_score": round(citation_score, 2),
            "completeness_checks": completeness["checks"],
            "completeness_score": completeness["score"],
        },
    }
