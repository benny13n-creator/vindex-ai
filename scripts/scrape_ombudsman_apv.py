#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Pokrajinski zastitnik gradjana (ombudsmanapv.org) scraper
Mišljenja i preporuke — opstа nadleznost.

URL: https://www.ombudsmanapv.org/riv/index.php/postupci/misljenja-i-preporuke-sve/opsta-nadleznost.html?start={n}
Korak: 5 stavki po stranici

Pokretanje:
    python scripts/scrape_ombudsman_apv.py
    python scripts/scrape_ombudsman_apv.py --reset
"""

import argparse
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
from bs4 import BeautifulSoup

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ombudsman_apv")

BASE        = "https://www.ombudsmanapv.org"
LIST_PATH   = "/riv/index.php/postupci/misljenja-i-preporuke-sve/opsta-nadleznost.html"
CRAWL_DELAY = 2.5
PAGE_STEP   = 5
MAX_PAGES   = 500  # max 2500 stavki

OUT_DIR     = _ROOT / "data" / "ombudsman_apv" / "misljenja"
CKPT_FILE   = _ROOT / "data" / "ombudsman_apv" / "checkpoint.json"
LOG_FILE    = _ROOT / "data" / "ombudsman_apv" / "scraper.log"

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
    return {"preuzeto": 0, "greske": 0, "preuzeti_urls": [], "poslednji_start": 0, "timestamp": _iso()}


def _save_ckpt(ck):
    CKPT_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


_last_req = [0.0]


def _rate_limit():
    elapsed = time.time() - _last_req[0]
    if elapsed < CRAWL_DELAY:
        time.sleep(CRAWL_DELAY - elapsed)
    _last_req[0] = time.time()


def _get(client: httpx.Client, url: str) -> BeautifulSoup | None:
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


def _fetch_list(client: httpx.Client, start: int) -> list[dict]:
    url = f"{BASE}{LIST_PATH}?start={start}"
    soup = _get(client, url)
    if not soup:
        return []

    items = []
    for a in soup.select("ul.latestnews-items li a, div.items-row a[href*='opsta-nadleznost'], li a[href*='opsta-nadleznost']"):
        href = a.get("href", "")
        if not href or "opsta-nadleznost" not in href:
            continue
        title = a.get_text(strip=True) or a.get("title", "")
        if not title:
            continue
        full_url = href if href.startswith("http") else BASE + href
        items.append({"naslov": title, "url": full_url})

    if not items:
        # Fallback: svi linkovi koji sadrze opsta-nadleznost i imaju datum u URL-u
        for a in soup.find_all("a", href=re.compile(r"opsta-nadleznost/.+\.html")):
            href = a.get("href", "")
            title = a.get_text(strip=True) or a.get("title", "")
            if title and len(title) > 5:
                full_url = href if href.startswith("http") else BASE + href
                items.append({"naslov": title, "url": full_url})

    return items


def _fetch_decision(client: httpx.Client, url: str) -> str:
    soup = _get(client, url)
    if not soup:
        return ""

    # Ukloni navigaciju
    for tag in soup.select("nav, header, footer, .navigation, .breadcrumb, script, style"):
        tag.decompose()

    # Trazi glavni sadrzaj
    for sel in ["article", "div.item-page", "div.content", "div#content", "main", "div.article-content"]:
        el = soup.select_one(sel)
        if el:
            return el.get_text(separator="\n", strip=True)

    return soup.body.get_text(separator="\n", strip=True) if soup.body else ""


def _safe_fname(url: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_\-]", "_", url.split("/")[-1].replace(".html", ""))
    return name[:80] or "doc"


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
        log.info("Checkpoint obrisan")

    ck = _load_ckpt()
    vec_preuzeti = set(ck.get("preuzeti_urls", []))
    start_offset = 0 if args.reset else ck.get("poslednji_start", 0)

    log.info("=== ombudsmanapv.org scraper | Vec preuzeto: %d ===", len(vec_preuzeti))

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        for offset in range(start_offset, MAX_PAGES * PAGE_STEP, PAGE_STEP):
            items = _fetch_list(client, offset)

            if not items:
                log.info("  start=%d: nema stavki — kraj liste", offset)
                break

            log.info("  start=%d: %d stavki", offset, len(items))
            new_in_page = 0

            for item in items:
                url = item["url"]
                if url in vec_preuzeti:
                    continue

                fname = _safe_fname(url)
                out_file = OUT_DIR / f"{fname}.json"
                if out_file.exists():
                    vec_preuzeti.add(url)
                    continue

                tekst = _fetch_decision(client, url)
                if not tekst or len(tekst) < 50:
                    log.warning("  Prazan tekst: %s", url)
                    continue

                doc = {
                    "naslov": item["naslov"],
                    "url": url,
                    "tekst": tekst,
                    "izvor": "ombudsmanapv.org",
                    "tip": "misljenje_preporuka",
                    "preuzeto_at": _iso(),
                }
                out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
                vec_preuzeti.add(url)
                new_in_page += 1
                log.info("    ✔ %s | %d znakova", item["naslov"][:60], len(tekst))

            ck["preuzeto"] = len(vec_preuzeti)
            ck["preuzeti_urls"] = list(vec_preuzeti)
            ck["poslednji_start"] = offset
            ck["timestamp"] = _iso()
            _save_ckpt(ck)

            if new_in_page == 0 and len(items) < PAGE_STEP:
                log.info("  Kraj — manje od PAGE_STEP stavki i sve vec preuzete")
                break

    log.info("=== ZAVRSENO: %d misljenja preuzetih | OUT: %s ===", len(vec_preuzeti), OUT_DIR)
    print(f"\n=== ZAVRSENO: {len(vec_preuzeti)} | OUT: {OUT_DIR} ===")


if __name__ == "__main__":
    main()
