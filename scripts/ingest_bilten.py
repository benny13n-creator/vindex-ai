# -*- coding: utf-8 -*-
"""
VINDEX Phase 2A — AS Bilten PDF ingest pipeline
Parses Apelacioni sud bilten PDFs (sentence extracts) into decision JSON dicts
compatible with the existing VKS chunker/ingest pipeline.

Usage:
  python scripts/ingest_bilten.py \
      --pdf   data/sudska_praksa/raw_bilteni/as_nis/bilten_2023-24.pdf \
      --out   data/sudska_praksa/raw_bilteni/as_nis/decisions/ \
      --court "Apelacioni sud u Nišu" \
      --source "AS Niš Bilten 2023-24" \
      --source_url_base "https://ni.ap.sud.rs/resources/files/Bilten%202023-24%20Nis.pdf"

Produces one JSON per decision in --out dir, same schema as VKS scraper output.
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
log = logging.getLogger("bilten_ingest")


# ─── Helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_id(text: str) -> str:
    """Filesystem-safe ID from case number or text hash."""
    cleaned = re.sub(r'[^A-Za-z0-9а-яА-ЯђљњћџЂЉЊЋЏ]', '_', text)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned[:80] if cleaned else "id_" + hashlib.md5(text.encode()).hexdigest()[:12]

def _detect_matter(text: str, case_num: str) -> str:
    """Detect legal matter from heading/case number text."""
    t = text.upper()
    cn = case_num.upper()
    if any(x in t for x in ['РАДНО', 'ZAPOSLENI', 'ЗАПОСЛЕН', 'ПОСЛОДАВАЦ', 'ЗАРАДА',
                              'RADNI', 'PLATA', 'UGOVOR O RADU', 'УГОВОР О РАДУ']):
        return "radni_sporovi"
    if any(x in t for x in ['КРИВИЧНО', 'ОСУЂЕН', 'КАЗН', 'ОКРИВЉЕН', 'КЖ']):
        return "krivicna"
    if 'КЖ' in cn or 'KЖ' in cn:
        return "krivicna"
    if 'ГЖ1' in cn or 'GЖ1' in cn:
        return "radni_sporovi"   # Гж1 = labour in appellate courts
    if 'ГЖ' in cn or 'GЖ' in cn:
        return "gradjanska"
    return "gradjanska"

def _parse_date(date_str: str) -> str:
    """Convert DD.MM.YYYY → YYYY-MM-DD."""
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return date_str

def _extract_text_from_pdf(pdf_path: Path) -> list[str]:
    """Extract page text list using pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages):
        t = page.extract_text() or ""
        pages.append(t)
    log.info("PDF loaded: %d pages, %d total chars",
             len(pages), sum(len(p) for p in pages))
    return pages


# ─── Core parsing logic ──────────────────────────────────────────────────────

# Attribution line: ends each sentence extract
# Captures: case_number (group 1), date DD.MM.YYYY (group 2)
ATTR_PATTERN = re.compile(
    r'\(?(?:Из|из)\s+(?:пресуде|решења|одлуке|пресуди|Пресуде|Решења)\s+'
    r'Апелационог\s+суда\s+у\s+Нишу[,\s]+'
    r'(\w[\w\s]*?\d+/\d{2,4})'            # case number: handles "Гж1 664/2022", "1 Гж1 664/2022"
    r'\s+од\s+(\d{2}\.\d{2}\.\d{4})',      # date
    re.UNICODE | re.DOTALL,
)

# Section marker patterns — pages that start "СУДСКА ПРАКСА" sections
SECTION_HEADER = re.compile(
    r'^\s*(?:КРИВИЧНО|ГРАЂАНСКО|РАДНО|УПРАВНО|ПРИВРЕДНО)\s+ПР\s*(?:АВО|AVO)\s*$',
    re.I | re.MULTILINE,
)

# Heading extractor — first substantial uppercase run after section separator
HEADING_RE = re.compile(
    r'^([А-ЯЂЉЊЋЏA-Z][А-ЯЂЉЊЋЏA-Z\s–\-\(\)\.]{10,})\s*\n',
    re.MULTILINE,
)


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces/newlines but preserve paragraph breaks."""
    # Fix spaced-letter OCR artifact: "Р А Д Н О" → "РАДНО"
    # (only in all-caps words, max 2-char gaps)
    text = re.sub(r'(?<=[А-ЯЂЉЊЋЏA-Z])\s{1,2}(?=[А-ЯЂЉЊЋЏA-Z])', '', text)
    # Collapse triple+ newlines to double
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Collapse multiple spaces to single
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def parse_bilten_pdf(
    pdf_path: Path,
    court: str,
    source: str,
    source_url_base: str,
) -> list[dict]:
    """
    Parse a bilten PDF into a list of decision dicts.
    Each dict matches the VKS raw decision schema.
    """
    pages = _extract_text_from_pdf(pdf_path)
    total_pages = len(pages)

    # Find which pages are in СУДСКА ПРАКСА sections (skip theory articles)
    # Strategy: find all section header pages, then include pages from
    # the first СУДСКА ПРАКСА divider until next non-СУДСКА section or end.
    #
    # From inspection of AS Niš 2023-24:
    # - Pages 83-89: КРИВИЧНО ПРАВО СУДСКА ПРАКСА  (pages 82-88 in 0-indexed)
    # - Pages 111-209: ГРАЂАНСКО ПРАВО СУДСКА ПРАКСА  (pages 110-208 in 0-indexed)
    #
    # General detection: a page whose stripped content is just a section title
    # like "КРИВИЧНО ПРАВО\nСУДСКА ПРАКСА" marks the start.

    sudska_praksa_pages: list[int] = []  # 0-indexed
    in_sudska_praksa = False
    for i, t in enumerate(pages):
        stripped = t.strip()
        # Detect separator pages that mark START of СУДСКА ПРАКСА section
        is_start = bool(re.search(
            r'СУДСКА\s+ПР\s*АКСА',
            stripped, re.I,
        ) and len(stripped) < 200)   # separator page is short
        # Detect pages that are clearly theoretical articles:
        is_theory = bool(re.search(
            r'ТЕОРИЈСКО.?ПР\s*АКТИЧНА|ТЕОРЕТСКИ|УВОДНА\s+РЕЧ',
            stripped, re.I,
        ))
        # Detect cover/blank pages
        is_blank = len(stripped) < 30

        if is_start:
            in_sudska_praksa = True
            continue
        if in_sudska_praksa and not is_blank:
            if is_theory:
                in_sudska_praksa = False
            else:
                sudska_praksa_pages.append(i)

    log.info("Pages in SUDSKA PRAKSA sections: %d (out of %d)",
             len(sudska_praksa_pages), total_pages)

    # Concatenate the relevant pages into one big text, tracking page numbers
    combined_chunks: list[tuple[int, str]] = []  # (1-indexed page, text)
    for idx in sudska_praksa_pages:
        t = _normalize_whitespace(pages[idx])
        if t:
            combined_chunks.append((idx + 1, t))

    full_text = "\n\n".join(text for _, text in combined_chunks)

    # ── Split on attribution pattern ──────────────────────────────────────
    # We split by finding all attribution matches and then slicing
    decisions = []
    last_end = 0
    segments: list[tuple[str, str, str]] = []  # (body_text, case_num, date)

    for m in ATTR_PATTERN.finditer(full_text):
        body = full_text[last_end:m.end()]
        case_num = m.group(1).strip()
        date_raw = m.group(2)
        segments.append((body, case_num, date_raw))
        last_end = m.end()

    log.info("Attribution lines found: %d", len(segments))

    for seg_idx, (body, raw_case_num, date_raw) in enumerate(segments):
        # Clean case number — remove leading digits/spaces that bleed from page numbers
        case_num = re.sub(r'^\d{1,3}\s+', '', raw_case_num).strip()
        case_num = re.sub(r'\s+', ' ', case_num).strip()

        # Extract heading: largest uppercase block at start of segment
        heading = ""
        heading_match = HEADING_RE.search(body)
        if heading_match:
            heading = heading_match.group(1).strip()
            # Trim repeated section header noise
            heading = re.sub(
                r'^(?:ГР\s*АЂАНСКО\s+ПР\s*АВО|КРИВИЧНО\s+ПР\s*АВО)\s*[\|\n]?\s*(?:Судска\s+пракса)?\s*',
                '', heading, flags=re.I,
            ).strip()

        # Detect matter
        matter = _detect_matter(heading + "\n" + case_num, case_num)

        # Date
        decision_date = _parse_date(date_raw)

        # Source URL with page number (approximate — page where attribution appears)
        # We'll use segment index as a proxy
        page_approx = sudska_praksa_pages[
            min(seg_idx * max(1, len(sudska_praksa_pages) // max(len(segments), 1)),
                len(sudska_praksa_pages) - 1)
        ] + 1 if sudska_praksa_pages else 0

        decision_id = _safe_id(case_num)

        d = {
            "decision_id": decision_id,
            "decision_number": case_num,
            "court": court,
            "decision_date": decision_date,
            "matter": matter,
            "heading": heading,
            "raw_text": body,
            "source": source,
            "source_url": f"{source_url_base}#page={page_approx}",
            "scraped_at": _now_iso(),
            "bilten_source": True,
        }
        decisions.append(d)
        log.debug("Decision %d: %s | %s | %s | %d chars",
                  seg_idx + 1, case_num, decision_date, matter, len(body))

    log.info("Total decisions parsed: %d", len(decisions))
    return decisions


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse bilten PDF to decision JSONs")
    parser.add_argument("--pdf", required=True, help="Path to bilten PDF")
    parser.add_argument("--out", required=True, help="Output directory for JSON files")
    parser.add_argument("--court", default="Apelacioni sud u Nišu")
    parser.add_argument("--source", default="AS Niš Bilten 2023-24")
    parser.add_argument("--source_url_base",
                        default="https://ni.ap.sud.rs/resources/files/Bilten%202023-24%20Nis.pdf")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    out_dir  = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        log.error("PDF not found: %s", pdf_path); sys.exit(1)

    decisions = parse_bilten_pdf(
        pdf_path=pdf_path,
        court=args.court,
        source=args.source,
        source_url_base=args.source_url_base,
    )

    if not decisions:
        log.error("No decisions parsed — check PDF structure"); sys.exit(1)

    # Save one JSON per decision
    saved = 0
    for d in decisions:
        fname = out_dir / f"{d['decision_id']}.json"
        # Handle duplicates with counter suffix
        if fname.exists():
            fname = out_dir / f"{d['decision_id']}_{saved}.json"
        fname.write_text(
            json.dumps(d, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        saved += 1

    log.info("Saved %d decision JSONs to %s", saved, out_dir)

    # Print summary
    from collections import Counter
    matters = Counter(d["matter"] for d in decisions)
    print(f"\n{'='*50}")
    print(f"PARSER SUMMARY")
    print(f"{'='*50}")
    print(f"  Decisions parsed : {len(decisions)}")
    print(f"  JSONs saved      : {saved}")
    print(f"  By matter        : {dict(matters)}")
    print(f"  Output dir       : {out_dir}")
    if decisions:
        print(f"\n  Sample decisions (first 5):")
        for d in decisions[:5]:
            print(f"    [{d['matter']:<20}] {d['decision_number']} | {d['decision_date']} | {len(d['raw_text'])} chars")
            print(f"       heading: {d['heading'][:70]}")


if __name__ == "__main__":
    main()
