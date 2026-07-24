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

# AKCIJA 1 (2026-07-24): naziv suda — strukturisan, predvidiv format u
# srpskim pravnim dokumentima, isti razlog za regex-prvo kao case_number/
# amount. Dva oblika: sudovi vezani za grad ("Osnovni sud u Beogradu") i
# nacionalni sudovi bez grada ("Vrhovni kasacioni sud", "Ustavni sud").
# Namerno NE zamenjuje LLM ekstrakciju za "court" -- samo joj prethodi kao
# visoko-pouzdan deterministički kandidat (vidi extract_all_entities).
_COURT_TIP_SA_GRADOM = (
    r"(?:Prvi\s+osnovni|Drugi\s+osnovni|Treći\s+osnovni|Osnovni|Viši|Apelacioni|"
    r"Privredni|Prekršajni)"
)
# Privredni apelacioni sud i Prekršajni apelacioni sud su pojedinačni,
# republički sudovi (sedište Beograd) — u praksi se ne navode sa "u Gradu"
# (za razliku od "Privredni sud u X" / "Prekršajni sud u X", koji jesu
# vezani za grad i ostaju u _COURT_TIP_SA_GRADOM).
_COURT_TIP_BEZ_GRADA = r"(?:Vrhovni\s+kasacioni|Privredni\s+apelacioni|Prekršajni\s+apelacioni|Ustavni|Upravni)"

# NAPOMENA: samo tip suda + "sud u" je case-insensitive (?i:...) -- svrha je
# da pokrije SVA-CAPS zaglavlja ("OSNOVNI SUD U BEOGRADU"). Naziv grada MORA
# početi velikim slovom (van dometa (?i:...)) da bi regex ostao selektivan —
# globalni re.IGNORECASE bi ovaj zahtev poništio i dozvolio da bilo koja
# sledeća reč (npr. običan glagol) bude pogrešno pročitana kao deo naziva.
_COURT_RE = re.compile(
    rf"\b(?i:{_COURT_TIP_SA_GRADOM}\s+sud\s+u)\s+[A-ZČĆĐŠŽ][a-zčćđšžA-ZČĆĐŠŽ]*(?:\s+[A-ZČĆĐŠŽ][a-zčćđšžA-ZČĆĐŠŽ]*)?"
    rf"|\b(?i:{_COURT_TIP_BEZ_GRADA}\s+sud)\b"
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


def extract_court(text: str) -> tuple[Optional[str], float]:
    """Regex, deterministički — visok confidence kad se poklopi (0.9).
    Namerno NE zamenjuje LLM ekstrakciju za "court" u extract_all_entities,
    samo joj prethodi kao pouzdaniji kandidat kad se poklopi; sudovi koje
    ovaj (namerno ne-iscrpan) regex ne pokrije i dalje idu preko LLM-a."""
    m = _COURT_RE.search(text or "")
    if not m:
        return None, 0.0
    naziv = re.sub(r"\s+", " ", m.group(0)).strip()
    return naziv, 0.9


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


_LLM_HEAD_CHARS = 4000
_LLM_TAIL_CHARS = 3000


def _kljucne_sekcije(text: str) -> str:
    """AKCIJA 1 (2026-07-24): bira ključne delove dugačkog dokumenta za LLM
    ekstrakciju umesto slepog uzimanja prvih 4000 znakova. Sudija je u
    srpskim sudskim odlukama gotovo uvek u potpisnom bloku na KRAJU
    dokumenta ("Sudija: ...", "Predsednik veća: ..."), koji je čisto
    head-only rezanje potpuno propuštalo kod dokumenata dužih od par
    strana -- polje "judge" je vraćalo null iako je podatak fizički
    postojao u dokumentu. Šalje početak (zaglavlje, stranke, sud) i kraj
    (potpis, pravna pouka); kraći dokumenti idu u celosti bez izmena."""
    text = text or ""
    if len(text) <= _LLM_HEAD_CHARS + _LLM_TAIL_CHARS:
        return text
    head = text[:_LLM_HEAD_CHARS]
    tail = text[-_LLM_TAIL_CHARS:]
    izostavljeno = len(text) - _LLM_HEAD_CHARS - _LLM_TAIL_CHARS
    return f"{head}\n\n[... isečeno {izostavljeno} znakova iz sredine dokumenta ...]\n\n{tail}"


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
    excerpt = _kljucne_sekcije(text)

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

    # AKCIJA 1 (2026-07-24): regex kandidat za sud se traži PRE LLM poziva;
    # kad se poklopi, deterministički je pouzdaniji od slobodnog LLM teksta
    # (isti princip kao case_number/amount/deadline), pa se koristi umesto
    # LLM-ovog "court" polja. Kad regex ne pronađe ništa, LLM ostaje jedini
    # izvor za taj entitet — regex ovde namerno nije iscrpan.
    court_regex, court_conf = extract_court(text)

    free_text = await extract_free_text_entities(text)
    for entity_type, (value, confidence) in free_text.items():
        if entity_type == "court" and court_regex:
            entities.append({"entity_type": "court", "value": court_regex, "confidence": court_conf, "extraction_method": "regex"})
        else:
            entities.append({"entity_type": entity_type, "value": value, "confidence": confidence, "extraction_method": "llm"})

    return entities
