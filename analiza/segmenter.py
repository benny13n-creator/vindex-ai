# -*- coding: utf-8 -*-
"""
Sloj 1 — Document Segmentation Engine

Deterministička segmentacija pravnih dokumenata pre slanja LLM-u.
Nema LLM poziva — čisto regex/heuristika, nulta latencija.

Tipovi dokumenata:
  "ugovor"  — ugovor (segmenti = klauzule)
  "presuda" — sudska presuda (segmenti = sekcije)
  "resenje" — sudsko rešenje (segmenti = sekcije)
  "ostalo"  — neprepoznat tip (segmenti = paragrafi po 1500 ch)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional


DocType = Literal["ugovor", "presuda", "resenje", "ostalo"]

# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class Segment:
    id: str                   # npr. "clause_3" ili "izreka"
    type: str                 # "klauzula" | "uvod" | "izreka" | "obrazlozenje" | ...
    naslov: Optional[str]     # naslov klauzule/sekcije ili null
    tekst: str                # čist tekst segmenta
    start_offset: int         # pozicija u full_text
    end_offset: int


@dataclass
class SegmentedDocument:
    doc_type: DocType
    segments: list[Segment]
    full_text: str
    char_count: int
    segment_count: int = field(init=False)

    def __post_init__(self):
        self.segment_count = len(self.segments)

    def segment_map(self) -> dict[str, Segment]:
        return {s.id: s for s in self.segments}

    def to_llm_context(self, max_chars_per_segment: int = 2000) -> str:
        """
        Vraća kompaktni JSON-like string za umetanje u LLM prompt.
        Svaki segment ima eksplicitan ID za referenciranje u findings.
        """
        lines = [f'DOKUMENT [{self.doc_type.upper()}] — {self.segment_count} segmenata:\n']
        for s in self.segments:
            naslov_str = f" | {s.naslov}" if s.naslov else ""
            tekst_trim = s.tekst[:max_chars_per_segment]
            if len(s.tekst) > max_chars_per_segment:
                tekst_trim += f"... [skraćeno, ukupno {len(s.tekst)} znakova]"
            lines.append(f"[{s.id}]{naslov_str}\n{tekst_trim}\n")
        return "\n".join(lines)


# ─── Keyword scoring za detect_document_type ─────────────────────────────────

_PRESUDA_KW = [
    "presuđuje", "presuda", "u ime naroda", "tužilac", "tuženi",
    "vrhovni kasacioni sud", "vrhovni sud", "privredni apelacioni",
    "apelacioni sud", "odlučujući po tužbi", "odbija tužbeni zahtev",
    "usvaja tužbeni zahtev", "rev.", "gž.", "p.", "g.z.",
    "prvostepeni sud", "izreka", "dispozitiv", "pouka o pravnom leku",
]
_RESENJE_KW = [
    "rešava", "rešenje", "zaključuje", "predlagač", "protivnik predlagača",
    "izvršni poverilac", "izvršni dužnik", "predlog za izvršenje",
    "iv.", "r.", "kž.", "kv.", "ki.", "oi.", "i.i.",
    "nalogom", "obavezuje se", "nalaže se",
]
_UGOVOR_KW = [
    "ugovorne strane", "zaključuju sledeći ugovor", "ugovor o",
    "kupac", "prodavac", "zakupac", "zakupodavac", "nalogodavac",
    "nalogoprimac", "poslodavac", "zaposleni", "član 1", "član 2",
    "potpisnici", "ugovarači", "u daljem tekstu", "ovim ugovorom",
    "ugovor je zaključen", "tačka 1", "tačka 2", "strane su saglasne",
]


def _score(tekst_lower: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in tekst_lower)


def detect_document_type(tekst: str) -> DocType:
    """
    Deterministički klasifikator tipa dokumenta (bez LLM).
    Koristi keyword scoring na prvim 3000 karaktera (dovoljno za header).
    """
    probe = tekst[:3000].lower()
    # Normalizuj dijakritike za matching
    probe_norm = probe
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        probe_norm = probe_norm.replace(src, dst)

    probe_both = probe + " " + probe_norm

    s_presuda = _score(probe_both, _PRESUDA_KW)
    s_resenje  = _score(probe_both, _RESENJE_KW)
    s_ugovor   = _score(probe_both, _UGOVOR_KW)

    # Rešenje mora da pobedi sa jasnom marginom jer deli mnogo termina sa presudom
    if s_resenje >= 3 and s_resenje > s_presuda:
        return "resenje"
    if s_presuda >= 3:
        return "presuda"
    if s_ugovor >= 3:
        return "ugovor"

    # Tiebreaker: koje ima više?
    scores = {"presuda": s_presuda, "resenje": s_resenje, "ugovor": s_ugovor}
    best = max(scores, key=lambda k: scores[k])
    if scores[best] >= 2:
        return best  # type: ignore[return-value]

    return "ostalo"


# ─── Segmentatori po tipu ─────────────────────────────────────────────────────

# Regex za "Član N", "ČLAN N.", "Čl. N", "Čl.N"
_CLAN_RE = re.compile(
    r"(?:^|\n)\s*(?:Č|Č|C)(?:l(?:an|\.)|LAN)\s*(\d+[a-zA-Z]?)\.?",
    re.IGNORECASE | re.MULTILINE,
)

# "Tačka N" ili "Tačka N.M" ili "TAČKA N"
_TACKA_RE = re.compile(
    r"(?:^|\n)\s*Ta(?:č|c)ka\s+(\d+(?:\.\d+)?)\.?",
    re.IGNORECASE | re.MULTILINE,
)

# Numerisani paragrafi: "1.", "2.", "1.1.", itd. na početku reda (min 30 znakova linije)
_NUM_PARA_RE = re.compile(
    r"(?:^|\n)(\d{1,2}(?:\.\d{1,2})?\.)\s+(?=\S.{25,})",
    re.MULTILINE,
)

# Naslovi klauzula (ALL CAPS linija ≤ 80 znakova)
_TITLE_RE = re.compile(r"^([A-ZŠĐČĆŽ][A-ZŠĐČĆŽ\s]{2,79})$", re.MULTILINE)


def _extract_naslov_after(tekst: str, offset: int, window: int = 120) -> Optional[str]:
    """Traži ALL-CAPS naslov u prvom redu posle offseta."""
    snippet = tekst[offset:offset + window]
    lines = snippet.split("\n")
    for ln in lines[:3]:
        ln = ln.strip()
        if ln and _TITLE_RE.match(ln) and len(ln) > 3:
            return ln
    return None


def _segmentuj_ugovor(tekst: str) -> list[Segment]:
    segments: list[Segment] = []

    # Pokušaj 1: Član N
    matches = list(_CLAN_RE.finditer(tekst))
    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(tekst)
            seg_tekst = tekst[start:end].strip()
            naslov = _extract_naslov_after(tekst, m.end())
            segments.append(Segment(
                id=f"clause_{m.group(1)}",
                type="klauzula",
                naslov=naslov,
                tekst=seg_tekst,
                start_offset=start,
                end_offset=end,
            ))
        return segments

    # Pokušaj 2: Tačka N
    matches = list(_TACKA_RE.finditer(tekst))
    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(tekst)
            seg_tekst = tekst[start:end].strip()
            safe_id = m.group(1).replace(".", "_")
            segments.append(Segment(
                id=f"tacka_{safe_id}",
                type="klauzula",
                naslov=None,
                tekst=seg_tekst,
                start_offset=start,
                end_offset=end,
            ))
        return segments

    # Pokušaj 3: Numerisani paragrafi
    matches = list(_NUM_PARA_RE.finditer(tekst))
    if len(matches) >= 3:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(tekst)
            seg_tekst = tekst[start:end].strip()
            safe_id = m.group(1).rstrip(".").replace(".", "_")
            segments.append(Segment(
                id=f"para_{safe_id}",
                type="klauzula",
                naslov=None,
                tekst=seg_tekst,
                start_offset=start,
                end_offset=end,
            ))
        return segments

    # Fallback: podeli na blokove po 1500 znakova
    return _fallback_segments(tekst)


# Ključne reči sekcija presude/rešenja (lowercase, bez dijakritika)
_DECISION_SECTION_PATTERNS = [
    ("uvod",            [r"u\s*v\s*o\s*d", r"osnov spora", r"u postupku", r"pred\s+sudom"]),
    ("izreka",          [r"i\s*z\s*r\s*e\s*k\s*a", r"d\s*i\s*s\s*p\s*o\s*z\s*i\s*t\s*i\s*v",
                         r"presuđuje se", r"resava se", r"odlucuje se", r"nalaže se"]),
    ("obrazlozenje",    [r"o\s*b\s*r\s*a\s*z\s*l\s*o\s*[zž]\s*e\s*nj\s*e",
                         r"iz\s+[a-z]+\s+obrazlo[zž]enja"]),
    ("pravni_osnov",    [r"pravni\s+osnov", r"na osnovu\s+(?:čl|cl|člana|clana)"]),
    ("pouka_o_pravnom_leku", [r"pouka\s+o\s+pravnom\s+leku", r"protiv\s+ove\s+presude",
                              r"žalba\s+se\s+mo[zž]e\s+izjav", r"alba\s+se\s+mo[zž]e"]),
]


def _norm(s: str) -> str:
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        s = s.replace(src, dst)
    return s.lower()


def _segmentuj_presudu(tekst: str) -> list[Segment]:
    """
    Sekcijska segmentacija presude/rešenja.
    Traži sekcije po ključnim rečima, vraća pronađene + null za nepronađene.
    """
    tekst_norm = _norm(tekst)
    found: dict[str, tuple[int, int]] = {}  # section_name → (start, end)

    # Za svaku sekciju, nađi prvu pojavu u tekstu
    positions: list[tuple[int, str]] = []
    for section_name, patterns in _DECISION_SECTION_PATTERNS:
        for pat in patterns:
            m = re.search(pat, tekst_norm)
            if m:
                positions.append((m.start(), section_name))
                break  # prva pojava, prestajemo

    # Sortiraj po poziciji
    positions.sort(key=lambda x: x[0])

    segments: list[Segment] = []
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(tekst)
        seg_tekst = tekst[start:end].strip()
        # Uzmi prvu liniju kao naslov
        first_line = seg_tekst.split("\n")[0].strip()[:80]
        segments.append(Segment(
            id=name,
            type=name,
            naslov=first_line or None,
            tekst=seg_tekst,
            start_offset=start,
            end_offset=end,
        ))
        found[name] = (start, end)

    # Dodaj null segmente za nepronađene sekcije
    found_names = {s.id for s in segments}
    for section_name, _ in _DECISION_SECTION_PATTERNS:
        if section_name not in found_names:
            segments.append(Segment(
                id=section_name,
                type=section_name,
                naslov=None,
                tekst="",   # prazan = sekcija nije pronađena
                start_offset=-1,
                end_offset=-1,
            ))

    # Sortiraj po start_offset (null segmenti na kraj)
    segments.sort(key=lambda s: s.start_offset if s.start_offset >= 0 else 999999)

    if not any(s.start_offset >= 0 for s in segments):
        return _fallback_segments(tekst)

    return segments


def _fallback_segments(tekst: str, block_size: int = 1500) -> list[Segment]:
    """Fallback: podeli tekst na blokove po `block_size` znakova."""
    segments = []
    i = 0
    block_idx = 1
    while i < len(tekst):
        end = min(i + block_size, len(tekst))
        # Pokušaj da seciš na kraju pasusa
        if end < len(tekst):
            nl = tekst.rfind("\n\n", i, end)
            if nl > i + block_size // 2:
                end = nl
        seg_tekst = tekst[i:end].strip()
        if seg_tekst:
            segments.append(Segment(
                id=f"blok_{block_idx}",
                type="blok",
                naslov=None,
                tekst=seg_tekst,
                start_offset=i,
                end_offset=end,
            ))
            block_idx += 1
        i = end
    return segments


# ─── Glavni API ───────────────────────────────────────────────────────────────

def segment_document(tekst: str) -> SegmentedDocument:
    """
    Glavna funkcija — detektuje tip i segmentuje dokument.

    Args:
        tekst: Čist tekst dokumenta (ekstrahovan PDF/DOCX).

    Returns:
        SegmentedDocument sa svim segmentima i metadatom.
    """
    tekst = tekst.strip()
    doc_type = detect_document_type(tekst)

    if doc_type == "ugovor":
        segments = _segmentuj_ugovor(tekst)
    elif doc_type in ("presuda", "resenje"):
        segments = _segmentuj_presudu(tekst)
    else:
        segments = _fallback_segments(tekst)

    # Fallback ako segmenter nije našao ništa
    if not segments:
        segments = _fallback_segments(tekst)

    return SegmentedDocument(
        doc_type=doc_type,
        segments=segments,
        full_text=tekst,
        char_count=len(tekst),
    )
