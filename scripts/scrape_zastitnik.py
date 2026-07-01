#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Scraper za godišnje izveštaje Zaštitnika gradjana (ombudsman.rs)
Preuzima srpske PDF izveštaje 2011-2025 i ekstrahuje tekst.
"""
import io, json, re, sys, time
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx, pdfplumber
except ImportError as e:
    print(f"pip install httpx pdfplumber: {e}"); sys.exit(1)

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "data" / "zastitnik" / "odluke"
PDF_DIR = ROOT / "data" / "zastitnik" / "pdfs"

HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"}

# Samo srpski PDF-ovi (filtrirani rucno — iskljucujemo en/alb/hu/ru)
SRPSKI_PDFS = [
    ("2025", "https://ombudsman.rs/attachments/article/8413/Редован Годишњи извештај Заштитника грађана за 2025. годину.pdf"),
    ("2024", "https://ombudsman.rs/attachments/article/8177/Редован Годишњи извештај Заштитника грађана за 2024. годину љ.pdf"),
    ("2023", "https://ombudsman.rs/attachments/article/7979/Redovan Godisnji izvestaj Zastitnika gradjana za 2023. godinu.pdf"),
    ("2022", "https://ombudsman.rs/attachments/article/7685/Redovan GI za 2022. god.pdf"),
    ("2021", "https://ombudsman.rs/attachments/article/7369/Redovan Godisnji izvestaj Zastitnika gradjana za 2021. godinu.pdf"),
    ("2020", "https://ombudsman.rs/attachments/article/7007/Redovan godišnji izveštaj Zaštitnika građana za 2020. godinu.pdf"),
    ("2019", "https://ombudsman.rs/attachments/article/6542/Redovan godišnji izveštaj Zaštitnika građana za 2019. godinu.pdf"),
    ("2018", "https://ombudsman.rs/attachments/article/6062/Zastitnik gradjana_Godisnji izvestaj za 2018. godinu.pdf"),
    ("2017", "https://ombudsman.rs/attachments/article/5671/Godisnji izvestaj za 2017. godinu.pdf"),
    ("2016", "https://ombudsman.rs/attachments/article/5191/Godisnji izvestaj Zastitnika gradjana za 2016. godinu.pdf"),
    ("2015", "https://ombudsman.rs/attachments/article/5555/Godisnji izvestaj Zastitnika gradjana za 2015.pdf"),
    ("2014", "https://ombudsman.rs/attachments/article/5556/Godisnji izvestaj Zastitnika gradjana za 2014.pdf"),
    ("2013", "https://ombudsman.rs/attachments/article/5557/Godisnji izvestaj Zasttnika gradjana za 2013 godinu.pdf"),
    ("2012", "https://ombudsman.rs/attachments/article/5558/Godisnji izvestaj Zastitnika gradjana za 2012 godinu.pdf"),
    ("2011", "https://ombudsman.rs/attachments/article/5559/Redovan godisnji izvestaj Zastitnika gradjana za 2011 godinu.pdf"),
]


def _iso():
    return datetime.now(timezone.utc).isoformat()


def process_pdf(year: str, url: str, client: httpx.Client) -> int:
    safe_name = f"zastitnik_{year}"
    pdf_path  = PDF_DIR / f"{safe_name}.pdf"

    if not pdf_path.exists():
        print(f"  Preuzimam {year}...")
        try:
            r = client.get(url, timeout=120, follow_redirects=True)
            if r.status_code != 200:
                print(f"  GRESKA HTTP {r.status_code}")
                return 0
            pdf_path.write_bytes(r.content)
            print(f"  Preuzeto: {len(r.content):,} bytes")
        except Exception as e:
            print(f"  GRESKA preuzimanja: {e}")
            return 0
    else:
        print(f"  Vec preuzet: {pdf_path.name}")

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_text = []
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages_text.append(t)
            full_text = "\n\n".join(pages_text)
        print(f"  Tekst: {len(full_text):,} chars, {len(pages_text)} strana")
    except Exception as e:
        print(f"  GRESKA ekstrakcije: {e}")
        return 0

    if len(full_text) < 500:
        print(f"  Premalo teksta, preskacam")
        return 0

    rec = {
        "id":       f"zastitnik_{year}",
        "izvor":    "zastitnik_gradjana",
        "sud":      "Zaštitnik gradjana Srbije",
        "naslov":   f"Godišnji izveštaj Zaštitnika gradjana za {year}. godinu",
        "datum":    f"{year}-12-31",
        "tekst":    full_text,
        "url":      url,
        "pdf_name": safe_name,
        "scraped_at": _iso(),
    }
    out_path = OUT_DIR / f"{safe_name}.json"
    out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    print("=== ZASTITNIK GRADJANA SCRAPER ===")
    print(f"PDFova: {len(SRPSKI_PDFS)} (2011-2025)")

    total = 0
    with httpx.Client(headers=HEADERS, follow_redirects=True, verify=False) as client:
        for year, url in SRPSKI_PDFS:
            print(f"\n--- {year} ---")
            n = process_pdf(year, url, client)
            total += n
            time.sleep(1)

    print(f"\n=== ZAVRSENO: {total}/{len(SRPSKI_PDFS)} sacuvano ===")
    print(f"Lokacija: {OUT_DIR}")


if __name__ == "__main__":
    main()
