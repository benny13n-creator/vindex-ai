#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — KJN (Komisija za javne nabavke) scraper
Preuzima PDF odluke sa arhivne stranice kjn.rs.

Arhiva:  https://kjn.rs/javno-dostavljanje/javno-dostavljanje-arhiva/
PDF URL: https://kjn.rs/wp-content/uploads/{filename}.pdf

Pokretanje:
    python scripts/scrape_kjn.py
    python scripts/scrape_kjn.py --reset
    python scripts/scrape_kjn.py --max-pages 20
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
log = logging.getLogger("kjn_scraper")

BASE         = "https://kjn.rs"
ARCHIVE_URL  = f"{BASE}/javno-dostavljanje/javno-dostavljanje-arhiva/"
CRAWL_DELAY  = 2.0
MAX_PAGES    = 50  # arhivnih stranica

OUT_DIR      = _ROOT / "data" / "kjn" / "odluke"
CKPT_FILE    = _ROOT / "data" / "kjn" / "checkpoint.json"
LOG_FILE     = _ROOT / "data" / "kjn" / "scraper.log"

HEADERS = {
    "User-Agent": "Vindex AI Legal Research (vindex-ai.onrender.com; contact: info@vindexai.rs)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _load_ckpt():
    if CKPT_FILE.exists():
        return json.loads(CKPT_FILE.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzete_urls": [], "arhivne_stranice": [], "timestamp": _iso()}


def _save_ckpt(ck):
    CKPT_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


_last_req = [0.0]


def _rate_limit():
    elapsed = time.time() - _last_req[0]
    if elapsed < CRAWL_DELAY:
        time.sleep(CRAWL_DELAY - elapsed)
    _last_req[0] = time.time()


def _get_html(client: httpx.Client, url: str) -> BeautifulSoup | None:
    _rate_limit()
    for attempt in range(3):
        try:
            r = client.get(url, timeout=30, headers=HEADERS)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            if r.status_code in (404, 410):
                return None
            if r.status_code == 429:
                time.sleep(60)
        except Exception as e:
            log.warning("Greska (pokusaj %d): %s", attempt + 1, e)
            time.sleep(8 * (attempt + 1))
    return None


def _collect_pdf_urls(client: httpx.Client) -> list[dict]:
    """Prikuplja sve PDF URL-ove sa arhivnih stranica."""
    all_pdfs = []
    seen_urls = set()

    # Proba paginacije: page/1, page/2, ... ili ?paged=1
    pages_to_try = [ARCHIVE_URL]
    for page_num in range(2, MAX_PAGES + 1):
        pages_to_try.append(f"{ARCHIVE_URL}page/{page_num}/")

    for page_url in pages_to_try:
        soup = _get_html(client, page_url)
        if not soup:
            log.info("  Kraj arhivnih stranica na: %s", page_url)
            break

        # Trazi linkove na PDF fajlove
        pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.IGNORECASE))
        if not pdf_links:
            # Pokusaj siri pattern
            pdf_links = soup.find_all("a", href=re.compile(r"/wp-content/uploads/.*\.pdf", re.IGNORECASE))

        new_on_page = 0
        for a in pdf_links:
            href = a.get("href", "")
            if not href:
                continue
            full_url = href if href.startswith("http") else BASE + href
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            title = a.get_text(strip=True) or a.get("title", "") or Path(href).stem
            all_pdfs.append({"naslov": title, "url": full_url})
            new_on_page += 1

        log.info("  Str %s: %d PDF-ova (ukupno %d)", page_url.split("/")[-2] or "1",
                 new_on_page, len(all_pdfs))

        if new_on_page == 0 and "/page/" in page_url:
            log.info("  Nema novih PDF-ova — kraj paginacije")
            break

    return all_pdfs


def _extract_pdf_text(content: bytes, url: str) -> str:
    # Pokusaj 1: pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
            tekst = "\n\n".join(pages).strip()
            if tekst and len(tekst) > 50:
                return tekst
    except Exception as e:
        log.warning("pdfplumber greska (%s): %s", url, e)

    # Pokusaj 2: PyPDF reader
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = [p.extract_text() or "" for p in reader.pages]
        tekst = "\n\n".join(pages).strip()
        if tekst and len(tekst) > 50:
            return tekst
    except Exception as e:
        log.warning("pypdf greska (%s): %s", url, e)

    # PDF je verovatno skeniran — vrati placeholder za kasniji OCR
    log.info("  [OCR-NEEDED] %s", url)
    return "[SKENIRAN_PDF_OCR_POTREBAN]"


def _extract_meta_from_url(url: str) -> dict:
    fname = Path(url).stem
    # Pattern: 1065-2023odlukark → broj=1065, godina=2023, tip=odluka
    m = re.match(r"(\d+)-(\d{4})(.*)", fname)
    if m:
        return {
            "broj_predmeta": m.group(1),
            "godina": m.group(2),
            "tip_akta": "odluka" if "odluka" in fname.lower() else "resenje",
        }
    # Pattern: 4-00-823-2023 → bez broja
    return {"broj_predmeta": fname, "godina": "", "tip_akta": "odluka"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
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

    log.info("=== KJN scraper | Vec preuzeto: %d ===", len(vec_preuzete))

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        log.info("Prikupljam PDF URL-ove...")
        all_pdfs = _collect_pdf_urls(client)
        log.info("Pronadjeno ukupno %d PDF-ova", len(all_pdfs))

        for pdf_info in all_pdfs:
            url = pdf_info["url"]
            if url in vec_preuzete:
                continue

            fname = re.sub(r"[^A-Za-z0-9_\-]", "_", Path(url).stem)[:80]
            out_file = OUT_DIR / f"kjn_{fname}.json"
            if out_file.exists():
                vec_preuzete.add(url)
                continue

            _rate_limit()
            try:
                r = client.get(url, timeout=60, headers=HEADERS)
                if r.status_code != 200 or len(r.content) < 100:
                    log.warning("  SKIP %s (HTTP %d)", url, r.status_code)
                    continue

                tekst = _extract_pdf_text(r.content, url)
                if not tekst:
                    log.warning("  Prazan tekst: %s", url)
                    continue

                meta = _extract_meta_from_url(url)
                doc = {
                    "naslov": pdf_info["naslov"] or meta.get("broj_predmeta", ""),
                    "url": url,
                    "tekst": tekst,
                    "izvor": "kjn.rs",
                    "sud": "Komisija za javne nabavke",
                    "tip": "odluka_kjn",
                    **meta,
                    "preuzeto_at": _iso(),
                }
                out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
                vec_preuzete.add(url)
                ck["preuzeto"] = len(vec_preuzete)
                ck["preuzete_urls"] = list(vec_preuzete)
                ck["timestamp"] = _iso()
                _save_ckpt(ck)

                log.info("  ✔ %s | %d znakova", fname, len(tekst))

            except Exception as e:
                log.error("  GRESKA za %s: %s", url, e)
                ck["greske"] = ck.get("greske", 0) + 1

    log.info("=== ZAVRSENO: %d KJN odluka | OUT: %s ===", len(vec_preuzete), OUT_DIR)
    print(f"\n=== ZAVRSENO: {len(vec_preuzete)} | OUT: {OUT_DIR} ===")


if __name__ == "__main__":
    main()
