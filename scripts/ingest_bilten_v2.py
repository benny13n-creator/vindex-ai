# -*- coding: utf-8 -*-
"""
VINDEX Faza 2B — Flexible bilten parser (v2)

Handles attribution formats for:
  --court-type bg   : Apelacioni sud u Beogradu
                      (пресуда/решење Апелационог суда у Београду CASE од D. Month YYYY.)
  --court-type nis  : Apelacioni sud u Nišu  (same as ingest_bilten.py)
  --court-type vks  : Vrhovni sud (Рев/Уж CASE од DD.MM.YYYY.)

Use the existing ingest_bilten.py for AS Niš (it already works).
This script is for AS Beograd and VKS.

Usage:
  python scripts/ingest_bilten_v2.py \
      --pdf   data/... \
      --out   data/.../decisions_XXX/ \
      --court-type bg \
      --court  "Apelacioni sud u Beogradu" \
      --source "AS Beograd Bilten 14 (2024)" \
      --source_url_base "https://bg.ap.sud.rs/files/..."
"""
import argparse, json, re, sys, hashlib
from pathlib import Path
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("bilten_v2")


# ─── Month name mapping (Serbian genitive) ──────────────────────────────────

MONTHS_SR = {
    'јануара': '01', 'фебруара': '02', 'марта': '03',
    'априла': '04', 'маја': '05', 'јуна': '06',
    'јула': '07', 'августа': '08', 'септембра': '09',
    'октобра': '10', 'новембра': '11', 'децембра': '12',
    # Latin equivalents (OCR may swap scripts)
    'januara': '01', 'februara': '02', 'marta': '03',
    'aprila': '04', 'maja': '05', 'juna': '06',
    'jula': '07', 'avgusta': '08', 'septembra': '09',
    'oktobra': '10', 'novembra': '11', 'decembra': '12',
}


# ─── Helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_id(text: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9а-яА-ЯђљњћџЂЉЊЋЏ]', '_', text)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned[:80] if cleaned else "id_" + hashlib.md5(text.encode()).hexdigest()[:12]

def _parse_date_ddmmyyyy(s: str) -> str:
    # Handles DD.MM.YYYY and D.M.YYYY (single-digit day/month)
    m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return s

def _parse_date_serbian(s: str) -> str:
    """Parse 'D. Month YYYY' or 'D Month YYYY' → YYYY-MM-DD.
    Handles OCR word breaks within month names (e.g. 'апри ла', 'авугу ста',
    'сеп-\nтембра') by joining fragments and looking up in MONTHS_SR."""
    s = s.strip()
    # Remove hyphen+newline line breaks within words (OCR artifact)
    s = re.sub(r'-\s*\n\s*', '', s)
    s = re.sub(r'\s+', ' ', s)
    # Try "D. MonthName YYYY" — month name may have OCR spaces/hyphens
    # Capture everything between day and 4-digit year (3–25 chars)
    m = re.match(r'(\d{1,2})\.?\s+(.{3,25}?)\s+(\d{4})\b', s)
    if m:
        day, month_raw, year = m.groups()
        # Collapse spaces/hyphens to reconstruct full month word
        month_word = re.sub(r'[\s\-]+', '', month_raw.lower())
        month = MONTHS_SR.get(month_word)
        if month:
            return f"{year}-{month}-{int(day):02d}"
    # Try D.M.YYYY or DD.MM.YYYY fallback
    return _parse_date_ddmmyyyy(s)

def _detect_matter(text: str, case_num: str) -> str:
    t = text.upper()
    cn = case_num.upper()
    if any(x in t for x in ['РАДНО', 'ZAPOSLENI', 'ЗАПОСЛЕН', 'ПОСЛОДАВАЦ', 'ЗАРАДА',
                              'RADNI', 'УГОВОР О РАДУ', 'UGOVOR O RADU']):
        return "radni_sporovi"
    if any(x in t for x in ['КРИВИЧНО', 'ОСУЂЕН', 'КАЗН', 'ОКРИВЉЕН']):
        return "krivicna"
    if re.search(r'[КK][жЖ]', cn): return "krivicna"
    if re.search(r'[ГG][жЖ]1', cn): return "radni_sporovi"
    if re.search(r'[ГG][жЖ]', cn): return "gradjanska"
    if re.search(r'Рев2|Rev2', cn, re.I): return "radni_sporovi"
    if re.search(r'Рев|Rev', cn, re.I): return "gradjanska"
    if re.search(r'Уж|Uz', cn, re.I): return "gradjanska"
    return "gradjanska"

def _normalize(text: str) -> str:
    # Fix spaced-letter OCR: "Р А Д Н О" → "РАДНО"
    text = re.sub(r'(?<=[А-ЯЂЉЊЋЏA-Z])\s{1,2}(?=[А-ЯЂЉЊЋЏA-Z])', '', text)
    # Join hyphenated line-breaks: "при-\nме ра" → "примера" (common in AS BG)
    text = re.sub(r'([а-яА-Яа-яЂЉЊЋЏa-zA-Z])-\s+([а-яа-яЂЉЊЋЏa-z])', r'\1\2', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()

def _extract_text_from_pdf(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    log.info("PDF loaded: %d pages, %d chars", len(pages), sum(len(p) for p in pages))
    return pages


# ─── AS Beograd parser ────────────────────────────────────────────────────────
#
# AS BG attribution ends each sentence:
#   (пресуда/решење Апелационог суда у Београду CASE_NUM од D. Month YYYY. ...)
#   аутор сентенце: NAME
#
# Strategy: split on "аутор сентенце:" — each segment is one decision.
# Then extract case number and date from the LAST `(...)` attribution before the split.

# "аутор сентенце:" boundary — split at the author + title block
# Matches: \n аутор сентенце: NAME,\n TITLE LINE\n
_AUTEUR_SPLIT = re.compile(
    r'\n[Аа]утор.{0,15}сентенц[еа][^\n]*\n[^\n]{3,120}\n',
    re.UNICODE,
)

# Step 1: capture the full attribution block (everything inside parens containing court name).
# Handles all observed AS BG formats:
#   A) (решење Апелационог суда у Бео граду CASE од DATE - ...)   — court type word first
#   B) (Пресуда first-instance ... и пресуда Апелационог суда у Бео граду CASE)  — AS BG second
#   C) ( Апелациони суд у Београду CASE od DATE)  — nominative, no type word prefix (older bilteni)
#   D) ( Из пресуде Апелационог суда у Београду CASE od DATE)  — "Из пресуде" prefix
# [^()]{0,250} allows skipping any prefix text before reaching the AS BG court name.
_BG_ATTR_BLOCK = re.compile(
    r'\(\s*[^()]{0,250}'         # any content up to 250 chars after '(' (skips prefix / first-inst.)
    r'Апе\s*л\s*[аa]\s*ционо(?:г\s+суда|и\s+суда|и\s+суд)\s+у\s+Бео\s*граду'
    r'([^)]{1,500})\)',           # capture everything inside parens after AS BG court name
    re.UNICODE | re.DOTALL | re.I,
)

# Step 2a: extract date from attribution body: D. Month YYYY or DD.MM.YYYY
# [оo][дd] handles Cyrillic 'од' and Latin 'od' and mixed OCR variants
_BG_DATE_IN_ATTR = re.compile(
    r'(?:[оo][дd]\s+)(\d{1,2}\.?\s+.{3,25}?\s+\d{4}\b|\d{1,2}\.\d{1,2}\.\d{4})',
    re.UNICODE | re.I | re.DOTALL,
)

# Step 2b: extract case number — handles Xж formats with optional dots/spaces/dashes
# e.g.: Кж1 348/24, Гж 857/23, Кж-1 103/14, Кж.1 621/14, Кж- По1-Кре 21/24
_BG_CASE_IN_ATTR = re.compile(
    r'\b([КкГгУуРрПпKkGgUuRrPp][жЖzZ][\w\s\-\.]{0,30}?\d+/\d{2,4})',
    re.UNICODE,
)


def parse_bilten_bg(pdf_path: Path, court: str, source: str, source_url_base: str) -> list[dict]:
    """Parse AS Beograd bilten — split on 'аутор сентенце:' boundaries."""
    pages = _extract_text_from_pdf(pdf_path)
    total_pages = len(pages)

    # Normalize each page and join
    normalized = []
    for i, t in enumerate(pages):
        n = _normalize(t)
        if n:
            normalized.append((i + 1, n))

    full_text = "\n\n".join(t for _, t in normalized)

    # Split at "аутор сентенце:" boundaries
    parts = _AUTEUR_SPLIT.split(full_text)
    # parts = [before_first_sentenca, after1, after2, ...]
    # Each pair: parts[i] = decision body, parts[i+1] = next body or author line
    # Actually: split() gives us the text BETWEEN each "аутор сентенце:" occurrence
    # So parts[0] = text before first attribution, parts[1] = text ending with 2nd attribution, etc.

    # Each segment (except possibly the last) ends with an attribution + decision body
    decisions = []
    for seg_idx, segment in enumerate(parts[:-1]):  # last part is trailing author text
        if not segment.strip():
            continue

        # Trim oversized first segment (front matter bleeds in before first decision)
        # Decision body is at the END of the segment, before the "аутор сентенце:" split.
        # Strategy: find the last double-newline paragraph boundary within last 5000 chars
        # and use that as the start of the decision body.
        if len(segment) > 6_000:
            # Look at last 5000 chars; find first paragraph start there
            tail_window = segment[-5_000:]
            first_para = tail_window.find('\n\n')
            if first_para >= 0:
                segment = tail_window[first_para:].strip()
            else:
                segment = tail_window.strip()

        # Find the attribution line in this segment (look in last 900 chars)
        tail = segment[-900:]

        # Step 1: find the attribution block (paren block with court name)
        attr_block_m = _BG_ATTR_BLOCK.search(tail)
        if attr_block_m:
            attr_body = attr_block_m.group(1)
            # Split on " - пресуда/решење" to isolate AS BG portion (drop first-instance part)
            appellate_part = re.split(r'\s+-\s+(?:пресуда|решење|одлука)', attr_body, maxsplit=1)[0]

            # Step 2a: date
            dm = _BG_DATE_IN_ATTR.search(appellate_part)
            date_raw = dm.group(1).strip() if dm else ""

            # Step 2b: case number — prefer Xж pattern, fall back to general case number
            case_hits = _BG_CASE_IN_ATTR.findall(appellate_part)
            if case_hits:
                case_num_raw = case_hits[-1].strip()
            else:
                # Fallback A: any letter prefix + number/year (e.g. "Р 29/24", "Рев 12/23")
                fb = re.search(
                    r'([А-ЯЂЉЊЋЏА-яđljnjćčđžšА-яa-zA-Z]{1,8}[\s\-\.]{0,3}\w{0,8}\s+\d+/\d{2,4})',
                    appellate_part,
                )
                if fb:
                    case_num_raw = fb.group(1).strip()
                else:
                    # Fallback B: bare number/year
                    fb2 = re.search(r'(\d+/\d{2,4})', appellate_part)
                    case_num_raw = fb2.group(1) if fb2 else f"BG_UNK_{seg_idx}"
        else:
            case_num_raw = f"BG_UNK_{seg_idx}"
            date_raw = ""

        # Clean case number (collapse whitespace/newlines)
        case_num = re.sub(r'\s+', ' ', case_num_raw).strip()

        # Parse date
        decision_date = _parse_date_serbian(date_raw) if date_raw else ""

        # Heading: first all-caps line
        heading_match = re.search(
            r'^([А-ЯЂЉЊЋЏA-Z][А-ЯЂЉЊЋЏA-Z\s–\-\(\)\.]{8,})\s*\n',
            segment, re.MULTILINE,
        )
        heading = heading_match.group(1).strip() if heading_match else ""
        # Strip section header noise
        heading = re.sub(r'^(?:КРИВИЧНО|ГРАЂАНСКО|РАДНО)\s+(?:ПРОЦЕСНО|МАТЕРИЈАЛНО|ПРАВО)\s*\n?\s*', '', heading, flags=re.I).strip()

        matter = _detect_matter(heading + "\n" + segment[:400], case_num)

        decision_id = _safe_id(case_num)
        page_approx = min(seg_idx * max(1, total_pages // max(len(parts), 1)), total_pages)

        d = {
            "decision_id": decision_id,
            "decision_number": case_num,
            "court": court,
            "decision_date": decision_date,
            "matter": matter,
            "heading": heading,
            "raw_text": segment.strip(),
            "source": source,
            "source_url": f"{source_url_base}#page={page_approx}",
            "scraped_at": _now_iso(),
            "bilten_source": True,
        }
        decisions.append(d)

    log.info("Parsed %d decisions (BG format)", len(decisions))
    return decisions


# ─── AS Niš (older bilteni 2010-2018) parser ─────────────────────────────────
#
# Format: "(Сентенца из пресуде Апелационог суда у Нишу Гж1.1234/2018 од DD.MM.YYYY.
#           године, утврђена на седници Одељења за ..."
# Key differences from 2023-24 format:
#   1. Optional "Сентенца " prefix before "из"
#   2. Case numbers use dot separator: "Гж1.3715/2016" not "Гж1 3715/2016"

_NIS_OLD_ATTR = re.compile(
    # Optional prefix: "Сентенца из", "Из", or just court-type word (Пресуда/Решење)
    # Also handles combined paren where AS Niš is second (after first-instance court)
    r'\(?[^()\n]{0,200}'                        # allow up to 200 chars before court name
    r'(?:пресуда|решење|одлука|пресуди|Пресуда|Решење)\s+'
    r'Апелационог\s+суда\s+у\s+Нишу[,\s]+'
    r'([\w][\w\s\.\-]*?\d+/\d{2,4})'          # case number — allows dots
    r'\s+(?:[оo][дd])\s+'
    r'(\d{1,2}\.\d{1,2}\.\d{4})',              # date: DD.MM.YYYY
    re.UNICODE | re.DOTALL,
)


def parse_bilten_nis_old(pdf_path: Path, court: str, source: str, source_url_base: str) -> list[dict]:
    """Parse older AS Niš bilteni (2010-2018) — uses 'Сентенца из пресуде' attribution."""
    from scripts.ingest_bilten import _extract_text_from_pdf, _normalize_whitespace
    pages = _extract_text_from_pdf(pdf_path)
    total_pages = len(pages)

    # Reuse the same СУДСКА ПРАКСА page detection logic
    sudska_praksa_pages: list[int] = []
    in_sudska_praksa = False
    for i, t in enumerate(pages):
        stripped = t.strip()
        is_start = bool(re.search(r'СУДСКА\s+ПР\s*АКСА', stripped, re.I) and len(stripped) < 200)
        is_theory = bool(re.search(r'ТЕОРИЈСКО.?ПР\s*АКТИЧНА|ТЕОРЕТСКИ', stripped, re.I))
        is_blank = len(stripped) < 30
        if is_start:
            in_sudska_praksa = True; continue
        if in_sudska_praksa and not is_blank:
            if is_theory:
                in_sudska_praksa = False
            else:
                sudska_praksa_pages.append(i)

    log.info("Pages in SUDSKA PRAKSA sections: %d (of %d)", len(sudska_praksa_pages), total_pages)

    combined = []
    for idx in sudska_praksa_pages:
        t = _normalize_whitespace(pages[idx])
        if t:
            combined.append((idx + 1, t))

    full_text = "\n\n".join(text for _, text in combined)

    decisions = []
    last_end = 0
    segments = []

    for m in _NIS_OLD_ATTR.finditer(full_text):
        body = full_text[last_end:m.end()]
        case_num_raw = m.group(1).strip()
        date_raw = m.group(2)
        # Clean case number: collapse spaces/newlines
        case_num = re.sub(r'\s+', ' ', case_num_raw).strip()
        decision_date = _parse_date_ddmmyyyy(date_raw)
        segments.append((body, case_num, decision_date))
        last_end = m.end()

    log.info("Attribution lines found: %d", len(segments))

    for seg_idx, (body, case_num, decision_date) in enumerate(segments):
        heading_match = re.search(
            r'^([А-ЯЂЉЊЋЏA-Z][А-ЯЂЉЊЋЏA-Z\s–\-\(\)\.]{8,})\s*\n',
            body, re.MULTILINE,
        )
        heading = heading_match.group(1).strip() if heading_match else ""
        matter = _detect_matter(heading + "\n" + case_num, case_num)
        page_approx = sudska_praksa_pages[
            min(seg_idx * max(1, len(sudska_praksa_pages) // max(len(segments), 1)),
                len(sudska_praksa_pages) - 1)
        ] + 1 if sudska_praksa_pages else 0

        decisions.append({
            "decision_id": _safe_id(case_num),
            "decision_number": case_num,
            "court": court,
            "decision_date": decision_date,
            "matter": matter,
            "heading": heading,
            "raw_text": body.strip(),
            "source": source,
            "source_url": f"{source_url_base}#page={page_approx}",
            "scraped_at": _now_iso(),
            "bilten_source": True,
        })

    log.info("Parsed %d decisions (NIS-OLD format)", len(decisions))
    return decisions


# ─── VKS / Vrhovni sud parser ─────────────────────────────────────────────────
#
# VKS bilteni (2024-2025) attribution format (to be confirmed after download):
# Likely: "(Из пресуде Врховног суда Рев CASE_NUM од DD.MM.YYYY. године)"
# OR like AS Beograd but with "Врховног суда" instead of "Апелационог суда у Београду"

# VKS attribution pattern (validated against bilten 2023-3):
# "(Сентенца из пре суде Врхов ног каса ционог суда Кзз 1169/2022 од 1.11.2022.)"
# OCR may split words: "пресуде"→"пре суде", "Врховног"→"Врхов ног", etc.
# Allow optional spaces at key word-break positions and use flexible court name match.
_VKS_ATTR = re.compile(
    r'\((?:Сентенца\s+)?[Ии]з\s+(?:пре\s*суде|реше\s*ња|одлу\s*ке|решења|пресуде)\s+'
    r'Врхов\s*ног\s+(?:каса\s*ционог\s+)?суда'
    r'[^()\n]{0,100}?'                   # non-greedy: preserve case type prefix in capture
    r'(\w[\w\s\-\.]*?\d+/\d{2,4})'      # case number (allows OCR spaces/dots)
    r'\s+[оo][дd]\s+'
    r'(\d{1,2}\.\d{1,2}\.\d{4})',        # date: D.MM.YYYY or DD.MM.YYYY
    re.UNICODE | re.DOTALL | re.I,
)

# VKS may also use "аутор сентенце" boundary like AS BG
_VKS_AUTEUR = re.compile(
    r'[Аа]утор(?:и|е)?\s+сентенц[еа][,:]?\s*\n',
    re.UNICODE | re.IGNORECASE,
)


def parse_bilten_vks(pdf_path: Path, court: str, source: str, source_url_base: str) -> list[dict]:
    """Parse VKS bilten — try NIS-style attribution first, fall back to BG-style."""
    pages = _extract_text_from_pdf(pdf_path)
    total_pages = len(pages)

    normalized = []
    for i, t in enumerate(pages):
        n = _normalize(t)
        if n:
            normalized.append((i + 1, n))
    full_text = "\n\n".join(t for _, t in normalized)

    # Try AS Niš-style attribution pattern first
    decisions = []
    last_end = 0

    for m in _VKS_ATTR.finditer(full_text):
        body = full_text[last_end:m.end()]
        case_num_raw = m.group(1).strip()
        date_raw = m.group(2)
        case_num = re.sub(r'\s+', ' ', case_num_raw).strip()
        decision_date = _parse_date_ddmmyyyy(date_raw)

        heading_match = re.search(r'^([А-ЯЂЉЊЋЏA-Z][А-ЯЂЉЊЋЏA-Z\s–\-\(\)\.]{8,})\s*\n', body, re.MULTILINE)
        heading = heading_match.group(1).strip() if heading_match else ""
        matter = _detect_matter(heading + "\n" + case_num, case_num)

        d = {
            "decision_id": _safe_id(case_num),
            "decision_number": case_num,
            "court": court,
            "decision_date": decision_date,
            "matter": matter,
            "heading": heading,
            "raw_text": body.strip(),
            "source": source,
            "source_url": f"{source_url_base}",
            "scraped_at": _now_iso(),
            "bilten_source": True,
        }
        decisions.append(d)
        last_end = m.end()

    if decisions:
        log.info("Parsed %d decisions (VKS NIS-style format)", len(decisions))
        return decisions

    # Fallback: try BG-style "аутор сентенце:" split
    log.info("VKS: no NIS-style attributions found, trying BG-style split...")
    parts = _AUTEUR_SPLIT.split(full_text)
    for seg_idx, segment in enumerate(parts[:-1]):
        if not segment.strip():
            continue
        tail = segment[-600:]

        # Try the VKS attr pattern in tail
        m = _VKS_ATTR.search(tail)
        if m:
            case_num = re.sub(r'\s+', ' ', m.group(1)).strip()
            decision_date = _parse_date_ddmmyyyy(m.group(2))
        else:
            case_num = f"VKS_UNK_{seg_idx}"
            decision_date = ""

        heading_match = re.search(r'^([А-ЯЂЉЊЋЏA-Z][А-ЯЂЉЊЋЏA-Z\s–\-\(\)\.]{8,})\s*\n', segment, re.MULTILINE)
        heading = heading_match.group(1).strip() if heading_match else ""
        matter = _detect_matter(heading + "\n" + case_num, case_num)

        decisions.append({
            "decision_id": _safe_id(case_num),
            "decision_number": case_num,
            "court": court,
            "decision_date": decision_date,
            "matter": matter,
            "heading": heading,
            "raw_text": segment.strip(),
            "source": source,
            "source_url": source_url_base,
            "scraped_at": _now_iso(),
            "bilten_source": True,
        })

    log.info("Parsed %d decisions (VKS BG-fallback format)", len(decisions))
    return decisions


# ─── Dispatch ─────────────────────────────────────────────────────────────────

def parse_bilten(
    pdf_path: Path,
    court_type: str,
    court: str,
    source: str,
    source_url_base: str,
) -> list[dict]:
    if court_type == "bg":
        return parse_bilten_bg(pdf_path, court, source, source_url_base)
    elif court_type == "vks":
        return parse_bilten_vks(pdf_path, court, source, source_url_base)
    elif court_type == "nis_old":
        return parse_bilten_nis_old(pdf_path, court, source, source_url_base)
    else:
        raise ValueError(f"Unknown court_type: {court_type!r}. Use bg, vks, or nis_old.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse bilten PDF to decision JSONs (v2)")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--court-type", required=True, choices=["bg", "vks", "nis_old"], help="bg|vks|nis_old")
    parser.add_argument("--court", default="Apelacioni sud u Beogradu")
    parser.add_argument("--source", default="AS Beograd Bilten")
    parser.add_argument("--source_url_base", default="")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        log.error("PDF not found: %s", pdf_path); import sys; sys.exit(1)

    decisions = parse_bilten(
        pdf_path=pdf_path,
        court_type=args.court_type,
        court=args.court,
        source=args.source,
        source_url_base=args.source_url_base,
    )

    if not decisions:
        log.error("No decisions parsed — check PDF structure")
        import sys; sys.exit(1)

    saved = 0
    seen_ids: dict[str, int] = {}
    for d in decisions:
        base_id = d['decision_id']
        if base_id in seen_ids:
            seen_ids[base_id] += 1
            fname = out_dir / f"{base_id}_{seen_ids[base_id]}.json"
        else:
            seen_ids[base_id] = 0
            fname = out_dir / f"{base_id}.json"
        fname.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        saved += 1

    log.info("Saved %d JSONs to %s", saved, out_dir)

    from collections import Counter
    matters = Counter(d["matter"] for d in decisions)
    print(f"\n{'='*50}")
    print(f"PARSER V2 SUMMARY")
    print(f"{'='*50}")
    print(f"  Court type       : {args.court_type}")
    print(f"  Decisions parsed : {len(decisions)}")
    print(f"  JSONs saved      : {saved}")
    print(f"  By matter        : {dict(matters)}")
    print(f"  Sample (first 5):")
    for d in decisions[:5]:
        print(f"    [{d['matter']:<20}] {d['decision_number']} | {d['decision_date']} | {len(d['raw_text'])} chars")


if __name__ == "__main__":
    main()
