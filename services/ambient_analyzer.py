# -*- coding: utf-8 -*-
"""
Vindex AI — services/ambient_analyzer.py

KORAK C: Ambient Context & Word/Browser Copilot (2026-07-24)

Brza, ekspresna analiza JEDNOG pasusa dok advokat kuca dokument van
aplikacije (MS Word add-in / browser ekstenzija — v. integrations/
word_addin/). Poziva se na svaku "pauzu u kucanju" (debounce se radi
KLIJENTSKI, u adapter.js — ovaj servis pretpostavlja da je već pozvan sa
razumnom učestalošću, ne radi svoj rate-limit osim onoga što
PermissionService/dnevni_limit već nameću preko routers/copilot_ambient.py).

Namerno LAKŠI od punog RAG pipeline-a (app.services.retrieve.
retrieve_documents je 5-sprint agentic pipeline sa multi-query/HyDE/CRAG --
odličan za /api/pitanje, presporo za nešto što treba da se vrati u
sekundi-dve dok korisnik i dalje kuca): mali top_k, gpt-4o-mini, kratak
max_tokens, strog timeout. Fail-soft na SVAKOM koraku -- RAG koji ne
uspe ili timeout-uje ne sme da obori LLM sugestiju, i obrnuto.
"""
import asyncio
import json
import logging
import re
import time
from typing import Optional

from shared.llm_retry import llm_retry
from shared.sentry import capture_exception as _sentry_capture

logger = logging.getLogger("vindex.ambient_analyzer")

_RAG_TOP_K = 3
_RAG_TIMEOUT_SECONDS = 4.0
_LLM_TIMEOUT_SECONDS = 6.0
_MIN_PASSAGE_CHARS = 40  # prekratak pasus (par reči) ne vredi analize

_SUGESTIJA_SYSTEM = """Ti si ambijentalni pravni copilot -- advokat kuca dokument
(van Vindex aplikacije, u Word-u ili pregledaču) i ti vidiš SAMO poslednji pasus
koji je napisao. Dobijaš i kratak RAG kontekst (odlomci zakona/prakse ako postoje).

Vrati SAMO JSON: {"sugestije": [{"tip": "clan_zakona"|"sudska_praksa"|"upozorenje", "tekst": "...", "izvor": "..."}]}

Pravila:
- Maksimum 3 sugestije. Prazan niz ako pasus ne daje povod ni za šta konkretno.
- "tekst" je JEDNA kratka rečenica na srpskom (max ~20 reči) -- ovo se čita
  usput dok advokat kuca, ne sme biti esej.
- "clan_zakona" -- SAMO ako RAG kontekst sadrži konkretan član koji je
  relevantan; nikad ne izmišljaj broj člana van dobijenog konteksta.
- "sudska_praksa" -- SAMO ako RAG kontekst sadrži konkretnu odluku.
- "upozorenje" -- za očiglednu grešku/nedostatak u samom pasusu (npr.
  nedostaje rok, kontradiktorna tvrdnja) -- ovo NE zahteva RAG kontekst.
- "izvor" -- kratka referenca (npr. "Zakon o radu, čl. 179" ili "Rev 123/2026"),
  prazan string ako nije primenljivo.
- Bez markdown blokova, samo JSON."""


@llm_retry
def _pozovi_sugestije_api(pasus: str, rag_kontekst: str, tip_dokumenta: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=350,
        timeout=_LLM_TIMEOUT_SECONDS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SUGESTIJA_SYSTEM},
            {"role": "user", "content": (
                f"TIP DOKUMENTA: {tip_dokumenta or 'nepoznat'}\n\n"
                f"RAG KONTEKST:\n{rag_kontekst or '(nema pronađenog konteksta)'}\n\n"
                f"PASUS:\n{pasus}"
            )},
        ],
    )
    return (r.choices[0].message.content or "{}").strip()


async def _brzi_rag_kontekst(pasus: str) -> str:
    """Ekspresni RAG prolaz -- mali top_k, strog timeout, fail-soft prazan
    string umesto greške. Kombinuje zakon (retrieve_documents) i praksu
    (retrieve_sudska_praksa) u kratak tekstualni blok za LLM prompt."""
    try:
        from app.services.retrieve import retrieve_documents, retrieve_sudska_praksa, process_praksa_chunks

        async def _zakon():
            docs, meta = await asyncio.to_thread(retrieve_documents, pasus, _RAG_TOP_K)
            if not docs:
                return ""
            top = f"{meta.get('top_law', '')} {meta.get('top_article', '')}".strip()
            return f"Relevantan zakon: {top}\n" + "\n".join(docs[:_RAG_TOP_K])

        async def _praksa():
            raw = await asyncio.to_thread(retrieve_sudska_praksa, pasus, max(_RAG_TOP_K, 20))
            odluke = process_praksa_chunks(raw, k=_RAG_TOP_K)
            if not odluke:
                return ""
            return "\n".join(
                f"{o.get('decision_number', '')} ({o.get('court', '')}, {o.get('date', '')}): {o.get('text', '')[:300]}"
                for o in odluke
            )

        zakon_txt, praksa_txt = await asyncio.wait_for(
            asyncio.gather(_zakon(), _praksa(), return_exceptions=False),
            timeout=_RAG_TIMEOUT_SECONDS,
        )
        return "\n\n".join(p for p in (zakon_txt, praksa_txt) if p)
    except asyncio.TimeoutError:
        logger.info("[AMBIENT] RAG timeout (%.1fs) — nastavljam bez konteksta", _RAG_TIMEOUT_SECONDS)
        return ""
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[AMBIENT] RAG greška — nastavljam bez konteksta: %s", e)
        return ""


def _izvor_potkrepljen(izvor: str, rag_kontekst: str) -> bool:
    """LAMBDA008-AI-001: the system prompt tells GPT never to invent a citation
    outside the given RAG context, but nothing downstream ever checked that --
    ungrounded, guarded only by prompt instruction, exactly the gap ask_agent's
    own hard-refusal (main.py) closes for the main Q&A path.

    Not a full-string substring check -- GPT legitimately paraphrases the law's
    name (e.g. "ZR čl. 179" for context that says "Zakon o radu, čl. 179"), and
    requiring an exact substring match would reject correct, grounded citations
    just as readily as fabricated ones. The concrete, checkable, hallucination-
    prone part named in the system prompt is the NUMBER ("nikad ne izmišljaj
    broj člana") -- every number token in `izvor` must actually appear in the
    RAG text we sent. Falls back to a substring check only when `izvor` has no
    numbers at all (e.g. a case name with no cited number)."""
    izvor_norm = (izvor or "").strip().lower()
    if not izvor_norm:
        return False
    kontekst_norm = (rag_kontekst or "").lower()
    brojevi = re.findall(r"\d+[a-z]?", izvor_norm)
    if brojevi:
        return all(b in kontekst_norm for b in brojevi)
    return izvor_norm in kontekst_norm


def _parsiraj_sugestije(raw: str, rag_kontekst: str = "") -> list[dict]:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    sugestije = parsed.get("sugestije") if isinstance(parsed, dict) else None
    if not isinstance(sugestije, list):
        return []

    # Filtriraj PRE sečenja na 3 -- ako model stavi koju nevalidnu stavku
    # rano u niz, to ne sme da istisne validne sugestije koje dolaze posle.
    ocisceno = []
    for s in sugestije:
        if not isinstance(s, dict):
            continue
        tip = s.get("tip")
        tekst = (s.get("tekst") or "").strip()
        if tip not in ("clan_zakona", "sudska_praksa", "upozorenje") or not tekst:
            continue
        izvor = (s.get("izvor") or "").strip()[:120]
        # "upozorenje" is explicitly RAG-independent per the system prompt (flags a
        # problem in the paragraph itself); clan_zakona/sudska_praksa MUST cite
        # something that was actually in the context we sent, or get dropped here
        # rather than reaching a lawyer's live document ungrounded.
        if tip in ("clan_zakona", "sudska_praksa") and not _izvor_potkrepljen(izvor, rag_kontekst):
            logger.info("[AMBIENT] sugestija odbačena (nepotkrepljena) tip=%s izvor=%r", tip, izvor)
            continue
        ocisceno.append({
            "tip": tip,
            "tekst": tekst[:300],
            "izvor": izvor,
        })
        if len(ocisceno) == 3:
            break
    return ocisceno


async def analyze_paragraph(
    tekst: str,
    predmet_id: Optional[str] = None,
    tip_dokumenta: Optional[str] = None,
    user_id: str = "",
) -> dict:
    """Vraća {"sugestije": [...], "trajanje_ms": int}. Nikad ne baca --
    svaka greška degradira na prazan niz sugestija (fail-soft)."""
    t0 = time.monotonic()
    pasus = (tekst or "").strip()

    if len(pasus) < _MIN_PASSAGE_CHARS:
        return {"sugestije": [], "trajanje_ms": round((time.monotonic() - t0) * 1000)}

    rag_kontekst = await _brzi_rag_kontekst(pasus)

    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_pozovi_sugestije_api, pasus, rag_kontekst, tip_dokumenta or ""),
            timeout=_LLM_TIMEOUT_SECONDS + 2,
        )
        sugestije = _parsiraj_sugestije(raw, rag_kontekst)
    except asyncio.TimeoutError:
        logger.info("[AMBIENT] LLM timeout uid=%.8s", (user_id or "")[:8])
        sugestije = []
    except Exception as e:
        _sentry_capture(e)
        logger.warning("[AMBIENT] LLM greška uid=%.8s: %s", (user_id or "")[:8], e)
        sugestije = []

    return {
        "sugestije": sugestije,
        "trajanje_ms": round((time.monotonic() - t0) * 1000),
    }
