#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Apelacioni sudovi bilteni scraper
Preuzima PDF biltene sudske prakse sa svih apelacionih sudova Srbije.

Pokriveni sudovi:
  - Apelacioni sud Beograd (bg.ap.sud.rs) — 14 biltena 2010-2024
  - Apelacioni sud Novi Sad (ns.ap.sud.rs) — 10 biltena 2010-2020
  - Apelacioni sud Kragujevac (kg.ap.sud.rs)
  - Apelacioni sud Nis (ni.ap.sud.rs)

Pokretanje:
    python scripts/scrape_apelacioni_bilteni.py
    python scripts/scrape_apelacioni_bilteni.py --reset
"""

import argparse
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import pdfplumber
from bs4 import BeautifulSoup

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("apelacioni_bilteni")

CRAWL_DELAY = 3.0

OUT_DIR    = _ROOT / "data" / "apelacioni_bilteni" / "fajlovi"
CKPT_FILE  = _ROOT / "data" / "apelacioni_bilteni" / "checkpoint.json"
LOG_FILE   = _ROOT / "data" / "apelacioni_bilteni" / "scraper.log"

HEADERS = {
    "User-Agent": "Vindex AI Legal Research (vindex-ai.onrender.com; contact: info@vindexai.rs)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Poznati PDF URL-ovi za sve apelacione sudove
KNOWN_PDFS = [
    # Apelacioni sud Beograd
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2010-1", "url": "https://bg.ap.sud.rs/files/Bilten%202010_1.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2011-2", "url": "https://bg.ap.sud.rs/files/bilten%202.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2011-3", "url": "https://bg.ap.sud.rs/files/bilten%203.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2012-4", "url": "https://bg.ap.sud.rs/files/Bilten-4%202012.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2013-5", "url": "https://bg.ap.sud.rs/files/Bilten_5_2013.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2014-6", "url": "https://bg.ap.sud.rs/files/Bilten%20broj%206%20u%20elektronskoj%20formimin.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2015-7", "url": "https://bg.ap.sud.rs/files/Bilten%20broj%207%20u%20elektronskoj%20formi.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2016-8", "url": "https://bg.ap.sud.rs/files/Bilten%20broj%208%20u%20elektronskoj%20formi.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2017-9", "url": "https://bg.ap.sud.rs/files/Bilten_Apelacije_BGD_9_2019min.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2018-10", "url": "https://bg.ap.sud.rs/files/Bilten10.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2020-11", "url": "https://bg.ap.sud.rs/files/Bilten11.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2022-12", "url": "https://bg.ap.sud.rs/files/Bilten-Apelacije-BG-br-12.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2023-13", "url": "https://bg.ap.sud.rs/files/BiltenApelBG13-2023.pdf"},
    {"sud": "Apelacioni sud Beograd", "naslov": "Bilten ASB 2024-14", "url": "https://bg.ap.sud.rs/files/Bilten%20Apel%20BG%2014-2024%20-%20provera%202-.pdf"},
    # Apelacioni sud Novi Sad
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2010-1", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_10_01.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2011-2", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_11_02.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2011-3", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_11_03.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2012-4", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_12_04.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2013-5", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_13_05.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2014-6", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_14_06.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2016-7", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_16_07.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2018-8", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_18_08.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2018-9", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_18_09.pdf"},
    {"sud": "Apelacioni sud Novi Sad", "naslov": "Bilten ASNS 2020-10", "url": "https://www.ns.ap.sud.rs/images/bilten/bilten_20_10.pdf"},
]

# Stranice za automatsko otkrivanje PDF-ova
DISCOVERY_PAGES = [
    {"sud": "Apelacioni sud Kragujevac", "url": "https://kg.ap.sud.rs/sekcija/91/sudska-praksa.php"},
    {"sud": "Apelacioni sud Kragujevac", "url": "https://www.kg.ap.sud.rs/bilten-sudske-prakse/"},
    {"sud": "Apelacioni sud Nis", "url": "https://www.ni.ap.sud.rs/bilten-sudske-prakse/"},
    {"sud": "Apelacioni sud Nis", "url": "https://ni.ap.sud.rs/sekcija/91/sudska-praksa.php"},
]


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _load_ckpt():
    if CKPT_FILE.exists():
        return json.loads(CKPT_FILE.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzete_urls": [], "timestamp": _iso()}


def _save_ckpt(ck):
    CKPT_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


_last_req = [0.0]


def _rate_limit():
    elapsed = time.time() - _last_req[0]
    if elapsed < CRAWL_DELAY:
        time.sleep(CRAWL_DELAY - elapsed)
    _last_req[0] = time.time()


def _get(client: httpx.Client, url: str) -> httpx.Response | None:
    _rate_limit()
    for attempt in range(3):
        try:
            r = client.get(url, timeout=90, headers=HEADERS)
            if r.status_code == 200:
                return r
            log.warning("HTTP %d: %s", r.status_code, url)
            return None
        except Exception as e:
            log.warning("Greska (pokusaj %d): %s — %s", attempt + 1, url, e)
            time.sleep(8 * (attempt + 1))
    return None


def _discover_pdfs(client: httpx.Client) -> list[dict]:
    """Automatski otkriva PDF URL-ove sa discovery_pages (kratki timeout)."""
    discovered = []
    for page in DISCOVERY_PAGES:
        try:
            _rate_limit()
            r = client.get(page["url"], timeout=8, headers=HEADERS)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=re.compile(r"\.pdf", re.IGNORECASE)):
                href = a.get("href", "")
                base = "/".join(page["url"].split("/")[:3])
                full_url = href if href.startswith("http") else base + href
                title = a.get_text(strip=True) or Path(href).stem
                discovered.append({"sud": page["sud"], "naslov": title, "url": full_url})
                log.info("  Otkriven: %s — %s", page["sud"], title[:50])
        except Exception as e:
            log.warning("Discovery skip (SSL/timeout): %s", page["url"])

    return discovered


def _extract_pdf_text(content: bytes, url: str) -> str:
    """Ekstrahuje tekst iz PDF-a."""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages):
                t = page.extract_text() or ""
                if t.strip():
                    pages.append(f"[Strana {i+1}]\n{t}")
            tekst = "\n\n".join(pages).strip()
            if tekst and len(tekst) > 200:
                return tekst
    except Exception as e:
        log.warning("pdfplumber greska (%s): %s", url, e)

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for i, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            if t.strip():
                pages.append(f"[Strana {i+1}]\n{t}")
        return "\n\n".join(pages).strip()
    except Exception as e:
        log.warning("pypdf greska (%s): %s", url, e)
        return "[SKENIRAN_PDF_OCR_POTREBAN]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    if args.reset and CKPT_FILE.exists():
        CKPT_FILE.unlink()

    ck = _load_ckpt()
    vec_preuzete = set(ck.get("preuzete_urls", []))

    log.info("=== Apelacioni sudovi bilteni scraper ===")
    log.info("  Poznati PDF-ovi: %d | Vec preuzeto: %d", len(KNOWN_PDFS), len(vec_preuzete))

    with httpx.Client(follow_redirects=True, timeout=90) as client:
        # Otkrij dodatne PDF-ove sa discovery stranica
        log.info("Otkrivam PDF-ove sa discovery stranica...")
        discovered = _discover_pdfs(client)
        log.info("Otkriveno %d dodatnih PDF-ova", len(discovered))

        all_pdfs = KNOWN_PDFS + discovered
        # Deduplikacija po URL-u
        seen_urls = set()
        unique_pdfs = []
        for pdf in all_pdfs:
            if pdf["url"] not in seen_urls:
                seen_urls.add(pdf["url"])
                unique_pdfs.append(pdf)

        log.info("Ukupno %d unikatnih PDF-ova za preuzimanje", len(unique_pdfs))

        for pdf_info in unique_pdfs:
            url = pdf_info["url"]
            if url in vec_preuzete:
                log.info("  SKIP (vec preuzet): %s", pdf_info["naslov"])
                continue

            fname = re.sub(r"[^A-Za-z0-9_\-]", "_", pdf_info["naslov"])[:80]
            out_file = OUT_DIR / f"bilten_{fname}.json"
            if out_file.exists():
                vec_preuzete.add(url)
                continue

            log.info("Preuzimam: %s — %s", pdf_info["sud"], pdf_info["naslov"])
            r = _get(client, url)
            if not r or len(r.content) < 1000:
                log.warning("  SKIP (prazan): %s", url)
                ck["greske"] = ck.get("greske", 0) + 1
                continue

            size_mb = len(r.content) / 1024 / 1024
            log.info("  Preuzet: %.1f MB — ekstraktujem tekst...", size_mb)

            tekst = _extract_pdf_text(r.content, url)
            if not tekst or len(tekst) < 100:
                log.warning("  Prazan tekst za %s", url)
                tekst = "[SKENIRAN_PDF_OCR_POTREBAN]"

            doc = {
                "naslov": pdf_info["naslov"],
                "sud": pdf_info["sud"],
                "url": url,
                "tekst": tekst,
                "izvor": url.split("/")[2],
                "tip": "bilten_sudske_prakse",
                "velicina_mb": round(size_mb, 2),
                "znakova": len(tekst),
                "preuzeto_at": _iso(),
            }

            out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            vec_preuzete.add(url)
            ck["preuzeto"] = len(vec_preuzete)
            ck["preuzete_urls"] = list(vec_preuzete)
            ck["timestamp"] = _iso()
            _save_ckpt(ck)

            log.info("  ✔ %s | %d znakova", fname, len(tekst))

    log.info("=== ZAVRSENO: %d biltena preuzetih | OUT: %s ===", len(vec_preuzete), OUT_DIR)
    print(f"\n=== ZAVRSENO: {len(vec_preuzete)} biltena | OUT: {OUT_DIR} ===")


if __name__ == "__main__":
    main()
