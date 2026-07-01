#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Scraper za AS Novi Sad biltene sudske prakse (PDF)
10 potvrdjenih PDFova na ns.ap.sud.rs/images/bilten/

Pokretanje:
    python scripts/scrape_as_ns_bilteni.py
"""

import io
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
    import pdfplumber
except ImportError as e:
    print(f"Nedostaje biblioteka: {e}. pip install httpx pdfplumber")
    sys.exit(1)

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "data" / "as_ns_bilteni" / "odluke"
PDF_DIR = ROOT / "data" / "as_ns_bilteni" / "pdfs"

PDF_URLS = [
    "https://www.ns.ap.sud.rs/images/bilten/bilten_10_01.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_11_02.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_11_03.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_12_04.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_13_05.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_14_06.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_16_07.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_18_08.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_18_09.pdf",
    "https://www.ns.ap.sud.rs/images/bilten/bilten_20_10.pdf",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
}

MIN_TEKST = 300


def _iso():
    return datetime.now(timezone.utc).isoformat()


def split_decisions(full_text: str, pdf_name: str) -> list[dict]:
    """
    Razdvaja tekst PDF biltena na individualne odluke.
    Bilteni AS NS obicno imaju odluke odvojene sa 'Iz obrazlozenja:', 'PRESUDA', 'RESENJE' header.
    """
    # Pokuaj razdvajanja po pattern-ima karakteristicnim za bilten
    # Odluke pocinje sa brojem predmeta ili sa 'PRESUDA' / 'RESENJE'
    patterns = [
        r'\n\s*(?:PRESUDA|REŠENJE|РЕШЕЊЕ|ПРЕСУДА)\s*\n',
        r'\n\s*(?:Gž|Gž\d|Gz|KŽ|Kž|IKž|Rev|Pvž|Mal)\s*\d+',
        r'\n\s*\d+\s*\n\s*(?:U\s+IME\s+NARODA|У\s+ИМЕ\s+НАРОДА)',
    ]

    # Najpre pokusaj razdvajanje po praznoj liniji + velikim slovima (header sekcija)
    chunks = re.split(r'\n{3,}', full_text)

    decisions = []
    current_parts = []
    current_header = ""

    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            continue

        # Detekcija pocetka nove odluke
        is_header = (
            re.match(r'^[A-ZČŠŽĆĐА-Ш]{3,}', stripped) or
            re.match(r'^(?:Gž|Kž|Rev|Pvž|IKž|Gz|Kzz|Ž)\s*\d', stripped) or
            re.match(r'^(?:Iz\s+(?:obrazloženja|образложења)|PRESUDA|REŠENJE|РЕШЕЊЕ|ПРЕСУДА)', stripped, re.I)
        )

        if is_header and current_parts and len(' '.join(current_parts)) > MIN_TEKST:
            decisions.append({
                "header": current_header,
                "tekst": '\n\n'.join(current_parts),
            })
            current_parts = [stripped]
            current_header = stripped[:100]
        else:
            if not current_parts:
                current_header = stripped[:100]
            current_parts.append(stripped)

    # Poslednji blok
    if current_parts and len(' '.join(current_parts)) > MIN_TEKST:
        decisions.append({
            "header": current_header,
            "tekst": '\n\n'.join(current_parts),
        })

    return decisions


def process_pdf(pdf_url: str, client: httpx.Client) -> int:
    """Preuzmi PDF, ekstrahuj tekst, podeli na odluke, snimi. Vraca broj sacuvanih."""
    pdf_name = pdf_url.split("/")[-1].replace(".pdf", "")
    pdf_path = PDF_DIR / f"{pdf_name}.pdf"

    # Preuzimanje PDFa
    if not pdf_path.exists():
        print(f"  Preuzimam {pdf_url}...")
        r = client.get(pdf_url, timeout=60)
        if r.status_code != 200:
            print(f"  GRESKA HTTP {r.status_code}")
            return 0
        pdf_path.write_bytes(r.content)
        print(f"  Preuzeto: {len(r.content):,} bytes")
    else:
        print(f"  Vec preuzet: {pdf_path.name}")

    # Ekstrakcija teksta
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append(text)
            full_text = "\n\n".join(pages)
        print(f"  Ekstrahovan tekst: {len(full_text):,} chars, {len(pages)} strana")
    except Exception as e:
        print(f"  GRESKA pri ekstrakciji: {e}")
        return 0

    if len(full_text) < MIN_TEKST:
        print(f"  Preskocen — premalo teksta")
        return 0

    # Podela na odluke (ili sacuvaj ceo bilten kao jednu odluku)
    decisions = split_decisions(full_text, pdf_name)
    print(f"  Pronadjeno segmenata: {len(decisions)}")

    if not decisions or (len(decisions) == 1 and len(decisions[0]["tekst"]) > 50000):
        # Ceo bilten kao jedan zapis (za pre-procesiranje)
        decisions = [{"header": pdf_name, "tekst": full_text}]

    saved = 0
    for i, dec in enumerate(decisions):
        tekst = dec["tekst"].strip()
        if len(tekst) < MIN_TEKST:
            continue

        safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", f"{pdf_name}_{i:04d}")[:80]
        vindex_id = f"as_ns_{safe_id}"

        rec = {
            "id":       vindex_id,
            "izvor":    "as_ns_bilten",
            "sud":      "Apelacioni sud Novi Sad",
            "naslov":   dec["header"][:200],
            "datum":    "",
            "tekst":    tekst,
            "url":      pdf_url,
            "pdf_name": pdf_name,
            "scraped_at": _iso(),
        }

        out_path = OUT_DIR / f"{vindex_id}.json"
        out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        saved += 1

    return saved


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    print("=== AS NOVI SAD BILTENI SCRAPER ===")
    print(f"PDFova za preuzimanje: {len(PDF_URLS)}")
    print(f"Output: {OUT_DIR}")

    total_saved = 0
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for url in PDF_URLS:
            name = url.split("/")[-1]
            print(f"\n--- {name} ---")
            saved = process_pdf(url, client)
            print(f"  Sacuvano odluka/segmenata: {saved}")
            total_saved += saved
            time.sleep(1)

    final_count = len(list(OUT_DIR.glob("*.json")))
    print(f"\n=== ZAVRSENO ===")
    print(f"Ukupno sacuvano:  {total_saved}")
    print(f"Ukupno u out_dir: {final_count}")
    print(f"Lokacija: {OUT_DIR}")


if __name__ == "__main__":
    main()
