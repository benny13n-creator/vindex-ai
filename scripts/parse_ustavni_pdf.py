#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Ustavni sud PDF parser (v2)
Parsuje već preuzete PDF biltene i deli ih na individualne odluke.

Pokretanje:
    python scripts/parse_ustavni_pdf.py

PDF-ovi su u: data/ustavni/pdf/
Output: data/ustavni/odluke/
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pypdf

_ROOT = Path(__file__).parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s")
log = logging.getLogger("ustavni_parser")

PDF_DIR = _ROOT / "data" / "ustavni" / "pdf"
OUT_DIR = _ROOT / "data" / "ustavni" / "odluke"

# Regex za broj predmeta Ustavnog suda
# Pokriva mešoviti ćirilično/latinični format koji pypdf generiše
# Primeri iz realnih PDF-ova: "IУ о-183/2016", "Уж-1234/2022", "ИУ з-5/2021"
CASE_PATTERN = re.compile(
    r"(?:"
    # Mešoviti format: latinično I + ćirilično У + slovo + broj
    r"IУ\s*[зоапл]\s*[-–]\s*\d+/\d{4}"
    r"|IУо\s*[-–]\s*\d+/\d{4}"
    r"|IУз\s*[-–]\s*\d+/\d{4}"
    # Puno ćirilično
    r"|ИУ\s*[зоапл]\s*[-–]\s*\d+/\d{4}"
    # Уж (ustavna žalba)
    r"|Уж\s*[-–]\s*\d+/\d{4}"
    r"|Уж\s+\d+/\d{4}"
    # Latinični (rezerva)
    r"|IU[zoаpл]\s*[-–]\s*\d+/\d{4}"
    r"|IUo[-–]\d+/\d{4}"
    r"|IUz[-–]\d+/\d{4}"
    r"|Uz[-–]\d+/\d{4}"
    r")",
    re.IGNORECASE
)

# Alternativni splitter — "Одлука" ili "Решење" + datum
ODLUKA_PATTERN = re.compile(
    r"\n\s*(Одлука|Решење|Закључак|Odluka|Re[sš]enje)\s*\n",
    re.IGNORECASE
)


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _extract_full_text(pdf_path: Path) -> str:
    """Ekstrahuje SVE stranice iz PDF-a bez trunkacije."""
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        pages = []
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            if t.strip():
                pages.append(f"[STR {i+1}]\n{t}")
        full = "\n\n".join(pages)
        log.info("  PDF: %d stranica, %d karaktera", len(reader.pages), len(full))
        return full
    except Exception as e:
        log.error("PDF greška (%s): %s", pdf_path.name, e)
        return ""


def _clean_text(t: str) -> str:
    """Ukloni OCR artefakte — višestruke razmake, slova razdvojena razmakom."""
    # "Г рад" → "Град", "У ставни" → "Уставни"
    t = re.sub(r"([А-ШЂЉЊЋЏ])\s+([а-шђљњћџ])", r"\1\2", t)
    # Višestruki whitespace
    t = re.sub(r" {3,}", " ", t)
    t = re.sub(r"\n{4,}", "\n\n\n", t)
    return t.strip()


def _split_decisions(text: str, period: str, pdf_name: str) -> list[dict]:
    """Deli tekst biltena na individualne odluke."""
    decisions = []
    text = _clean_text(text)

    # Pronađi sve pozicije slučajeva
    matches = list(CASE_PATTERN.finditer(text))
    log.info("  Pronađeno %d šablona slučajeva", len(matches))

    if len(matches) < 3:
        # Malo šablona — pokušaj split po "Одлука\n" graničniku
        alt_matches = list(ODLUKA_PATTERN.finditer(text))
        log.info("  Alternativni splitter (Одлука/Решење): %d", len(alt_matches))
        if len(alt_matches) > len(matches):
            matches = alt_matches

    if not matches:
        # Poslednji resort: sačuvaj ceo tekst kao jedan chunk od 100k
        log.warning("  Nema šablona — čuvam kao celinu")
        decisions.append(_make_record(
            id_str=f"ustavni_{period.replace(' ','_').replace('/','_')}_full",
            period=period,
            broj="",
            datum="",
            tip="",
            tekst=text[:100000],
        ))
        return decisions

    # Grupiši tekst između svake pojave broja predmeta
    # Dodaj sentinel na kraj
    positions = [m.start() for m in matches] + [len(text)]

    for i, match in enumerate(matches):
        start = match.start()
        end = positions[i + 1]
        chunk = text[start:end].strip()

        if len(chunk) < 80:
            continue

        broj = match.group(0).strip()
        broj = re.sub(r"\s+", " ", broj)

        datum = ""
        dm = re.search(r"(\d{1,2})[.\s]+(\d{1,2})[.\s]+(\d{4})", chunk)
        if dm:
            datum = f"{dm.group(3)}-{dm.group(2).zfill(2)}-{dm.group(1).zfill(2)}"

        tip = ""
        tm = re.search(r"(Одлука|Решење|Закључак|Odluka|Rešenje)", chunk[:300])
        if tm:
            tip = tm.group(1)

        safe_id = re.sub(r"[^\w]", "_", broj)[:60]
        decisions.append(_make_record(
            id_str=f"ustavni_{safe_id}_{i}",
            period=period,
            broj=broj,
            datum=datum,
            tip=tip,
            tekst=chunk[:50000],
        ))

    return decisions


def _make_record(id_str, period, broj, datum, tip, tekst) -> dict:
    return {
        "id": id_str,
        "izvor": "ustavni_sud_bilten",
        "sud": "Ustavni sud Srbije",
        "period": period,
        "broj_predmeta": broj,
        "tip_odluke": tip,
        "datum": datum,
        "tekst": tekst,
        "scraped_at": _iso(),
    }


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Obriši stare _full fajlove
    stari = list(OUT_DIR.glob("*_full.json"))
    for f in stari:
        f.unlink()
        log.info("Obrisan stari: %s", f.name)

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        log.error("Nema PDF fajlova u %s", PDF_DIR)
        return

    log.info("=== USTAVNI SUD PARSER v2 — %d PDF-ova ===", len(pdfs))

    ukupno = 0
    for pdf_path in pdfs:
        # Period iz naziva fajla
        name = pdf_path.stem
        period = (name
            .replace("bilten_ustavnog_suda_", "")
            .replace("bilten_us_", "")
            .replace("bilten_", "")
            .replace("_", " ")
        )
        log.info("═ Parsujem: %s (period: %s) ═", pdf_path.name, period)

        text = _extract_full_text(pdf_path)
        if not text or len(text) < 500:
            log.warning("  Prazan PDF, preskačem")
            continue

        odluke = _split_decisions(text, period, pdf_path.name)
        log.info("  → %d odluka ekstraktovano", len(odluke))

        for odluka in odluke:
            path = OUT_DIR / f"{odluka['id']}.json"
            path.write_text(
                json.dumps(odluka, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            ukupno += 1

    log.info("=== ZAVRŠENO: %d odluka iz %d PDF-ova ===", ukupno, len(pdfs))
    print(f"\nUstavni sud: {ukupno} odluka sačuvano u {OUT_DIR}")


if __name__ == "__main__":
    run()
