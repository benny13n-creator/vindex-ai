#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — sudskapraksa.sud.rs scraper
Centralni repozitorijum VKS + Apelacioni + Upravni sudovi (od 2019).

Strategy: iterira ID-ove 83000-88000, preskace 404, preuzima PDF,
          ekstrahuje tekst sa pdfplumber.

URL pattern:
  Lista: https://sudskapraksa.sud.rs/sudska-praksa/{ID}
  PDF:   https://sudskapraksa.sud.rs/sudska-praksa/download/id/{ID}/file/odluka

Pokretanje:
    python scripts/scrape_sudskapraksa_sud.py
    python scripts/scrape_sudskapraksa_sud.py --reset
    python scripts/scrape_sudskapraksa_sud.py --start 84000 --end 87500
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
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("sudskapraksa_sud")

BASE       = "https://sudskapraksa.sud.rs"
CRAWL_DELAY = 2.0
ID_START   = 83000
ID_END     = 88000

OUT_DIR    = _ROOT / "data" / "sudskapraksa_sud" / "odluke"
CKPT_FILE  = _ROOT / "data" / "sudskapraksa_sud" / "checkpoint.json"
LOG_FILE   = _ROOT / "data" / "sudskapraksa_sud" / "scraper.log"

HEADERS = {
    "User-Agent": "Vindex AI Legal Research (vindex-ai.onrender.com; contact: info@vindexai.rs)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sr,en;q=0.9",
    "Referer": "https://sudskapraksa.sud.rs/sudska-praksa",
}


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _load_ckpt():
    if CKPT_FILE.exists():
        return json.loads(CKPT_FILE.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzeti_ids": [], "preskoceni_ids": [], "timestamp": _iso()}


def _save_ckpt(ck):
    CKPT_FILE.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")


_last_req = [0.0]


def _rate_limit():
    elapsed = time.time() - _last_req[0]
    if elapsed < CRAWL_DELAY:
        time.sleep(CRAWL_DELAY - elapsed)
    _last_req[0] = time.time()


def _fetch_html(client: httpx.Client, node_id: int) -> BeautifulSoup | None:
    url = f"{BASE}/sudska-praksa/{node_id}"
    _rate_limit()
    for attempt in range(3):
        try:
            r = client.get(url, timeout=30, headers=HEADERS)
            if r.status_code == 200:
                return BeautifulSoup(r.text, "lxml")
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                log.warning("429 — cekam 60s")
                time.sleep(60)
            else:
                log.warning("HTTP %d za ID %d", r.status_code, node_id)
                return None
        except Exception as e:
            log.warning("Greska (pokusaj %d, ID %d): %s", attempt + 1, node_id, e)
            time.sleep(6 * (attempt + 1))
    return None


def _fetch_pdf_text(client: httpx.Client, node_id: int) -> str:
    url = f"{BASE}/sudska-praksa/download/id/{node_id}/file/odluka"
    _rate_limit()
    for attempt in range(3):
        try:
            r = client.get(url, timeout=60, headers=HEADERS)
            if r.status_code == 200 and len(r.content) > 100:
                try:
                    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                        pages = [p.extract_text() or "" for p in pdf.pages]
                        return "\n\n".join(pages).strip()
                except Exception as pdf_e:
                    log.warning("PDF greska za ID %d: %s", node_id, pdf_e)
                    return r.text[:5000] if r.headers.get("content-type", "").startswith("text") else ""
            if r.status_code == 404:
                return ""
        except Exception as e:
            log.warning("PDF fetch greska (pokusaj %d, ID %d): %s", attempt + 1, node_id, e)
            time.sleep(6 * (attempt + 1))
    return ""


def _parse_metadata(soup: BeautifulSoup, node_id: int) -> dict:
    meta = {"node_id": node_id, "url": f"{BASE}/sudska-praksa/{node_id}"}

    # Naslov
    h1 = soup.find("h1")
    meta["naslov"] = h1.get_text(strip=True) if h1 else ""

    # Pokusaj da izvuces broj predmeta i datum iz naslova
    naslov = meta["naslov"]
    # Pattern: "Решење Рев2 2192/2019 од 27. 09. 2019."
    m = re.search(r"(\d{4}\.)", naslov)
    meta["datum"] = m.group(1).strip() if m else ""

    # Sud — trazi u linkovima
    sud_link = soup.find("a", href=re.compile(r"tip_suda"))
    meta["sud"] = sud_link.get_text(strip=True) if sud_link else ""

    # Oblast prava
    oblast_link = soup.find("a", href=re.compile(r"oblast_prava"))
    meta["oblast_prava"] = oblast_link.get_text(strip=True) if oblast_link else ""

    # Broj predmeta — iz naslova ili meta detalja
    m2 = re.search(r"([A-ZА-Яa-zа-я]+\d+\s+[\d/]+)", naslov)
    meta["broj_predmeta"] = m2.group(0).strip() if m2 else ""

    # Vrsta — Resenje/Presuda/Zakljucak
    for vrsta in ["Решење", "Пресуда", "Закључак", "Reшenje", "Presuda"]:
        if vrsta in naslov:
            meta["vrsta"] = vrsta
            break
    else:
        meta["vrsta"] = ""

    return meta


def _is_no_result(soup: BeautifulSoup) -> bool:
    text = soup.get_text()
    return "Није пронађен ниједан документ" in text or "Nije pronadjen nijedan dokument" in text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--start", type=int, default=ID_START)
    parser.add_argument("--end", type=int, default=ID_END)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    if args.reset and CKPT_FILE.exists():
        CKPT_FILE.unlink()
        log.info("Checkpoint obrisan — krecem ispocetka")

    ck = _load_ckpt()
    vec_preuzeti = set(ck.get("preuzeti_ids", []))
    preskoceni   = set(ck.get("preskoceni_ids", []))
    id_range     = range(args.start, args.end + 1)

    log.info("=== sudskapraksa.sud.rs scraper | Opseg: %d–%d ===", args.start, args.end)
    log.info("  Vec preuzeto: %d | Preskoceno (404): %d", len(vec_preuzeti), len(preskoceni))

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        for node_id in id_range:
            if node_id in vec_preuzeti:
                continue
            if node_id in preskoceni:
                continue

            out_file = OUT_DIR / f"sp_{node_id}.json"
            if out_file.exists():
                vec_preuzeti.add(node_id)
                continue

            soup = _fetch_html(client, node_id)
            if soup is None or _is_no_result(soup):
                preskoceni.add(node_id)
                if node_id % 100 == 0:
                    log.info("  [%d] 404/nema — preskacemo", node_id)
                continue

            meta = _parse_metadata(soup, node_id)

            if args.dry_run:
                log.info("DRY-RUN [%d] %s | %s", node_id, meta.get("sud", "?"), meta.get("naslov", "?")[:60])
                continue

            # Preuzmi PDF tekst
            tekst = _fetch_pdf_text(client, node_id)

            doc = {
                **meta,
                "tekst": tekst,
                "izvor": "sudskapraksa.sud.rs",
                "preuzeto_at": _iso(),
            }

            out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            vec_preuzeti.add(node_id)
            ck["preuzeto"] = len(vec_preuzeti)
            ck["preuzeti_ids"] = list(vec_preuzeti)
            ck["preskoceni_ids"] = list(preskoceni)
            ck["timestamp"] = _iso()
            _save_ckpt(ck)

            log.info("  [%d] ✔ %s | %s | %d znakova",
                     node_id, meta.get("sud", "?")[:30], meta.get("naslov", "?")[:50], len(tekst))

    log.info("=== ZAVRSENO: %d odluka preuzetih, %d preskocenih (404) ===",
             len(vec_preuzeti), len(preskoceni))
    print(f"\n=== ZAVRSENO: {len(vec_preuzeti)} odluka | OUT: {OUT_DIR} ===")


if __name__ == "__main__":
    main()
