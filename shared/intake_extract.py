# -*- coding: utf-8 -*-
"""
Vindex AI — shared/intake_extract.py

Smart Intake Engine, Faza 1A — Confidence Graph entity extraction (ADR-0005).
Hibridno po polju (ADR-0003): case_number/amount/deadline su strukturisana
polja sa fiksnim formatom u srpskim pravnim dokumentima — regex prvo, uvek
auditabilno. deadline reuse-uje POSTOJEĆI uploaded_doc/deadline_parser.py
(ne piše se nov parser od nule — isti mehanizam koji /api/dokument/rokovi
već koristi). judge/plaintiff/defendant/court/law_cited su slobodan tekst
— ide LLM, sa sopstvenim confidence po polju.

Svaki entitet ima svoju nezavisnu vrednost, čak i kad nije pronađen —
fail-soft (docs/ENGINEERING_PRINCIPLES.md): "rok nije pronađen" je entitet
sa niskim confidence-om koji ide u review queue, nikad tiho izostavljen red.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("vindex.intake_extract")

ENTITY_TYPES = (
    "case_number", "judge", "plaintiff", "defendant",
    "court", "deadline", "amount", "law_cited",
)

# Srpski broj predmeta: slovni prefiks (ćirilica ili latinica, 1-3 znaka,
# npr. "П", "Пж", "К", "P", "Pž", "Iv") + opciona tačka/razmak + broj + "/" +
# 2-4 cifre godine. Latinični skup MORA uključiti č/ć/đ/š/ž (Latin Extended-A)
# — srpska latinica ih koristi u prefiksima (npr. "Pž"), obična A-Za-z ih ne
# pokriva. Namerno permisivan raspon dužine broja (sudovi variraju).
_CASE_NUMBER_RE = re.compile(
    r"\b([А-ШЂЖЉЊЋЏA-Za-zČĆĐŠŽčćđšž]{1,3})\.?\s?(\d{1,6}/\d{2,4})\b"
)

# Novčani iznos sa hiljadama-separatorom i valutom (RSD/din/EUR/€/$/USD) —
# valuta je OBAVEZNA u match-u, bez nje je prevelik rizik lažnog pozitiva
# (bilo koji broj bi inače "izgledao" kao iznos).
_AMOUNT_RE = re.compile(
    r"\b(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s?(РСД|RSD|дин\.?|din\.?|€|EUR|евра|eura|\$|USD)\b",
    re.IGNORECASE,
)


def extract_case_number(text: str) -> tuple[Optional[str], float]:
    """Regex, deterministički — visok confidence kad se poklopi (0.95),
    nikad izmišljeno kad se ne poklopi (None, 0.0 — ide u review)."""
    m = _CASE_NUMBER_RE.search(text or "")
    if not m:
        return None, 0.0
    return f"{m.group(1)} {m.group(2)}", 0.95


def extract_amount(text: str) -> tuple[Optional[str], float]:
    m = _AMOUNT_RE.search(text or "")
    if not m:
        return None, 0.0
    return f"{m.group(1)} {m.group(2)}", 0.92


def extract_deadline(text: str) -> tuple[Optional[str], float]:
    """Reuse-uje uploaded_doc/deadline_parser.py::ekstrahuj_rokove — isti
    mehanizam koji /api/dokument/rokovi već koristi, ne nov parser.

    Otkriveno uživo (Faza 1A): "uzmi prvi pronađeni rok" je pogrešno kad
    dokument pominje VIŠE datuma — datum same presude je skoro uvek prvi u
    tekstu, a stvarni rok (za žalbu/otkaz/isplatu) dolazi kasnije, tipično u
    odeljku pravne pouke. Zato se prvo traži rok sa PRAVNO ZNAČAJNOM
    kategorijom (zastarelost/otkaz/zalba/podnesak/isplata — vidi
    deadline_parser._kategorija).

    Drugi sloj istog nalaza: deadline_parser.py-ov kontekst-prozor (100
    karaktera) je dovoljno širok da OBA datuma u kratkom pasusu dobiju istu
    kategoriju (npr. i datum presude i stvarni rok za žalbu, ako su blizu u
    tekstu) — kategorija sama nije uvek dovoljna da razdvoji. Dodatni signal:
    istekao=False (rok još nije prošao) je jači pokazatelj "ovo je stvarni,
    aktivni rok" nego prosto koji je prvi u tekstu — presuda je skoro uvek
    ranije datirana od roka koji iz nje proizilazi."""
    from uploaded_doc.deadline_parser import ekstrahuj_rokove

    rokovi = ekstrahuj_rokove(text or "")
    if not rokovi:
        return None, 0.0

    znacajan = (
        next((r for r in rokovi if r.get("kategorija") != "ostalo" and r.get("istekao") is False), None)
        or next((r for r in rokovi if r.get("kategorija") != "ostalo"), None)
    )
    izabran = znacajan or rokovi[0]

    vrednost = izabran.get("konkretan_datum") or izabran.get("vrednost")
    # Apsolutni datum (regex sa eksplicitnim danom/mesecom/godinom) je
    # pouzdaniji signal nego relativni ("15 dana") koji zavisi od tačnog
    # datuma dokumenta da bi se izračunao unapred. Kategorisan rok (znacajan
    # je not None) dobija blagi bonus — manja šansa da je ovo slučajan datum.
    base = 0.9 if izabran.get("tip") == "apsolutni" else 0.72
    confidence = min(0.97, base + 0.05) if znacajan else base
    return vrednost, confidence


_LLM_SYSTEM = """Ti si ekstraktor podataka iz srpskih pravnih dokumenata. Izvuci sledeće entitete iz teksta, ako postoje.

Vrati ISKLJUČIVO validan JSON bez markdown fence-ova:
{
  "judge": {"value": "<ime sudije ili null>", "confidence": <0-1>},
  "plaintiff": {"value": "<ime/naziv tužioca ili null>", "confidence": <0-1>},
  "defendant": {"value": "<ime/naziv tuženog ili null>", "confidence": <0-1>},
  "court": {"value": "<naziv suda ili null>", "confidence": <0-1>},
  "law_cited": {"value": "<naziv zakona/članova ili null>", "confidence": <0-1>}
}

PRAVILA:
1. confidence je TVOJA iskrena procena koliko si siguran — ne izmišljaj visoku sigurnost.
2. value = null AKO entitet nije eksplicitno pomenut u tekstu. NE pretpostavljaj.
3. Jezik: srpska ekavica u eventualnim objašnjenjima (entiteti se prepisuju iz teksta kakvi jesu)."""


async def extract_free_text_entities(text: str) -> dict:
    """LLM ekstrakcija za slobodan tekst — judge/plaintiff/defendant/court/
    law_cited. Vraća {entity_type: (value, confidence)} za svih 5 —
    uključujući null vrednosti sa niskim confidence-om ako LLM samo ne
    zna, nikad izostavljeno."""
    import json
    import os
    from openai import AsyncOpenAI

    free_text_types = ("judge", "plaintiff", "defendant", "court", "law_cited")
    fallback = {t: (None, 0.0) for t in free_text_types}

    oai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    excerpt = (text or "")[:4000]

    for attempt in range(3):
        try:
            r = await oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM},
                    {"role": "user", "content": excerpt},
                ],
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            raw = (r.choices[0].message.content or "{}").strip()
            parsed = json.loads(raw)
            result = {}
            for t in free_text_types:
                field = parsed.get(t) or {}
                value = field.get("value")
                confidence = float(field.get("confidence", 0.0)) if value else 0.0
                result[t] = (value, max(0.0, min(1.0, confidence)))
            return result
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("[INTAKE_EXTRACT] parse greška (pokušaj %d/3): %s", attempt + 1, e)
        except Exception as e:
            logger.error("[INTAKE_EXTRACT] OpenAI greška: %s", e)
            return fallback
    logger.error("[INTAKE_EXTRACT] LLM ekstrakcija neuspešna posle 3 pokušaja.")
    return fallback


async def extract_all_entities(text: str) -> list[dict]:
    """Glavna ulazna tačka — vraća listu {entity_type, value, confidence,
    extraction_method} za svih 8 tipova iz ENTITY_TYPES. Regex polja se
    izvlače sinhrono/lokalno, slobodan tekst preko jednog LLM poziva
    (ne 5 zasebnih — jeftinije i konzistentnije)."""
    entities: list[dict] = []

    case_number, cn_conf = extract_case_number(text)
    entities.append({"entity_type": "case_number", "value": case_number, "confidence": cn_conf, "extraction_method": "regex"})

    amount, amt_conf = extract_amount(text)
    entities.append({"entity_type": "amount", "value": amount, "confidence": amt_conf, "extraction_method": "regex"})

    deadline, dl_conf = extract_deadline(text)
    entities.append({"entity_type": "deadline", "value": deadline, "confidence": dl_conf, "extraction_method": "regex"})

    free_text = await extract_free_text_entities(text)
    for entity_type, (value, confidence) in free_text.items():
        entities.append({"entity_type": entity_type, "value": value, "confidence": confidence, "extraction_method": "llm"})

    return entities
