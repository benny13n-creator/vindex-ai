#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Privredni apelacioni sud (pa.sud.rs) — bilteni sudske prakse
SSL bypass (verify=False) jer sertifikat istekao.

Bilteni: https://pa.sud.rs/tekst/394/bilteni-sudske-prakse.php
Preuzima PDF biltene, ekstrahuje presude sa pdfplumber.

Pokretanje:
    python scripts/scrape_pa_sud.py
    python scripts/scrape_pa_sud.py --reset
"""

import argparse
import io
import json
import logging
import re
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import pdfplumber
from bs4 import BeautifulSoup

# Supress SSL warnings
warnings.filterwarnings("ignore", message=".*SSL.*")
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pa_sud_scraper")

BASE        = "https://pa.sud.rs"
# Pokusavamo vise URL-ova jer ssl expired sajt moze da ima razlicite putanje
BILTENI_URLS = [
    f"{BASE}/tekst/394/bilteni-sudske-prakse.php",
    f"{BASE}/sekcija/7/sudska-praksa.php",
    f"{BASE}/sudska-praksa",
    f"{BASE}/sekcija/sudska-praksa",
]
CRAWL_DELAY = 2.5

OUT_DIR     = _ROOT / "data" / "pa_sud" / "bilteni"
CKPT_FILE   = _ROOT / "data" / "pa_sud" / "checkpoint.json"
LOG_FILE    = _ROOT / "data" / "pa_sud" / "scraper.log"

HEADERS = {
    "User-Agent": "Vindex AI Legal Research (vindex-ai.onrender.com; contact: info@vindexai.rs)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sr,en;q=0.9",
}


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
            r = client.get(url, timeout=60, headers=HEADERS)
            if r.status_code == 200:
                return r
            log.warning("HTTP %d: %s", r.status_code, url)
            return None
        except Exception as e:
            log.warning("Greska (pokusaj %d): %s — %s", attempt + 1, url, e)
            time.sleep(8 * (attempt + 1))
    return None


def _collect_pdf_urls(client: httpx.Client) -> list[dict]:
    pdfs = []
    seen = set()

    for url in BILTENI_URLS:
        r = _get(client, url)
        if not r:
            log.warning("Ne mogu da pristupim %s", url)
            continue

        soup = BeautifulSoup(r.text, "lxml")
        found_on_page = 0

        # Trazi PDF linkove
        for a in soup.find_all("a", href=re.compile(r"\.pdf", re.IGNORECASE)):
            href = a.get("href", "")
            full_url = href if href.startswith("http") else BASE + "/" + href.lstrip("/")
            if full_url in seen:
                continue
            seen.add(full_url)
            title = a.get_text(strip=True) or a.get("title", "") or Path(href).stem
            pdfs.append({"naslov": title, "url": full_url})
            found_on_page += 1
            log.info("  PDF: %s", title[:60])

        log.info("Stranica %s: %d PDF-ova pronadjeno", url, found_on_page)

        # Pokazi sve linkove ako nema PDF-ova (debugging)
        if found_on_page == 0:
            all_links = [(a.get_text(strip=True)[:50], a.get("href","")[:80]) for a in soup.find_all("a") if a.get("href")]
            log.info("  Svi linkovi na stranici: %s", all_links[:15])

    log.info("Ukupno pronadjeno %d PDF biltena", len(pdfs))
    return pdfs


def _extract_pdf_text(content: bytes, url: str) -> str:
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n\n".join(pages).strip()
    except Exception as e:
        log.warning("PDF parse greska (%s): %s", url, e)
        return ""


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

    log.info("=== PA Sud (pa.sud.rs) bilteni scraper | SSL bypass ===")

    # SSL verify=False zbog isteklog sertifikata
    transport = httpx.HTTPTransport(verify=False)
    with httpx.Client(transport=transport, follow_redirects=True, timeout=60) as client:
        pdfs = _collect_pdf_urls(client)

        if not pdfs:
            log.error("Nema PDF-ova — proveri URL: %s", BILTENI_URL)
            return

        for pdf_info in pdfs:
            url = pdf_info["url"]
            if url in vec_preuzete:
                continue

            fname = re.sub(r"[^A-Za-z0-9_\-]", "_", Path(url).stem)[:80]
            out_file = OUT_DIR / f"pa_sud_{fname}.json"
            if out_file.exists():
                vec_preuzete.add(url)
                continue

            r = _get(client, url)
            if not r or len(r.content) < 100:
                log.warning("SKIP (prazan) %s", url)
                continue

            tekst = _extract_pdf_text(r.content, url)
            if not tekst or len(tekst) < 100:
                log.warning("Prazan tekst: %s", url)
                continue

            doc = {
                "naslov": pdf_info["naslov"],
                "url": url,
                "tekst": tekst,
                "izvor": "pa.sud.rs",
                "sud": "Privredni apelacioni sud",
                "tip": "bilten_sudske_prakse",
                "preuzeto_at": _iso(),
            }
            out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            vec_preuzete.add(url)
            ck["preuzeto"] = len(vec_preuzete)
            ck["preuzete_urls"] = list(vec_preuzete)
            ck["timestamp"] = _iso()
            _save_ckpt(ck)

            log.info("  ✔ %s | %d znakova", fname, len(tekst))

    log.info("=== ZAVRSENO: %d biltena | OUT: %s ===", len(vec_preuzete), OUT_DIR)
    print(f"\n=== ZAVRSENO: {len(vec_preuzete)} | OUT: {OUT_DIR} ===")


if __name__ == "__main__":
    main()
