#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Poverenik za informacije od javnog značaja scraper
Preuzima odluke i mišljenja Poverenika sa poverenik.rs.

Pokretanje:
    python scripts/scrape_poverenik.py --dry-run
    python scripts/scrape_poverenik.py

Output: data/poverenik/odluke/{id}.json
"""

import argparse, json, logging, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
from bs4 import BeautifulSoup

_ROOT = Path(__file__).parent.parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("poverenik_scraper")

BASE   = "https://www.poverenik.rs"
RATE_S = 1.3

# Kategorije — sve sekcije sa odlukama i mišljenjima
KATEGORIJE = [
    # Pristup informacijama
    {"url": "/sr-yu/pristup-informacijama2/praksa/odluke-i-mi%C5%A1ljenja-poverenika/odluke-poverenika.html",
     "tip": "odluka_pristup_informacijama"},
    {"url": "/sr-yu/pristup-informacijama2/praksa/odluke-i-mi%C5%A1ljenja-poverenika/mi%C5%A1ljenja-poverenika.html",
     "tip": "misljenje_pristup_informacijama"},
    {"url": "/sr-yu/36-pristup-informacijama/66-stavovi-misljenja-di.html",
     "tip": "stav_misljenje"},
    # Zaštita podataka
    {"url": "/sr-yu/za%C5%A1tita-podataka/praksa/odluke-i-mi%C5%A1ljenja-poverenika/odluke.html",
     "tip": "odluka_zastita_podataka"},
    {"url": "/sr-yu/za%C5%A1tita-podataka/praksa/odluke-i-mi%C5%A1ljenja-poverenika/mi%C5%A1ljenja.html",
     "tip": "misljenje_zastita_podataka"},
]

OUT_DIR  = _ROOT / "data" / "poverenik" / "odluke"
CKPT     = _ROOT / "data" / "poverenik" / "checkpoint.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VindexBot/1.0; legal research; contact: info@vindexai.rs)",
    "Accept": "text/html,*/*",
    "Accept-Language": "sr-RS,sr;q=0.9",
}

def _iso(): return datetime.now(timezone.utc).isoformat()
def _load_ckpt():
    if CKPT.exists(): return json.loads(CKPT.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzeti_urls": [], "timestamp": _iso()}
def _save_ckpt(ck): CKPT.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")

def _slug(url: str) -> str:
    path = url.rstrip("/").split("/")[-1].replace(".html", "")
    path = re.sub(r"%[0-9A-Fa-f]{2}", "_", path)
    return re.sub(r"[^\w]", "_", path)[:80] or "doc"

def _get(client, url):
    for attempt in range(3):
        try:
            r = client.get(url, timeout=30)
            if r.status_code == 200: return r
            if r.status_code in (404, 410): return None
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            log.warning("Greška (pokušaj %d): %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return None

def _extract_doc_links(soup, base_url: str) -> list[dict]:
    """Izvlači linkove na individualne odluke/mišljenja iz liste."""
    items = []
    seen  = set()

    # Joomla CMS — linkovi u content oblasti
    content = soup.find(["div", "section", "main"], class_=re.compile(r"content|item|article", re.I))
    search_area = content if content else soup

    skip = ["/sr-yu/", "/en/", "/upload/", "mailto:", "javascript:", "#",
            ".pdf", "facebook", "twitter", "youtube", "/tag/", "/category/"]

    for a in search_area.find_all("a", href=True):
        href = a["href"]
        txt  = a.get_text(strip=True)

        if len(txt) < 8: continue
        if any(s in href for s in skip): continue

        # Pun URL
        if href.startswith("http"):
            if "poverenik.rs" not in href: continue
            full = href
        else:
            full = BASE + href

        if full in seen: continue
        seen.add(full)

        # Datum
        datum = ""
        parent = a.find_parent(["td", "li", "div", "tr"])
        if parent:
            dm = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", parent.get_text())
            if dm: datum = f"{dm.group(3)}-{dm.group(2).zfill(2)}-{dm.group(1).zfill(2)}"

        items.append({"url": full, "naslov": txt[:400], "datum": datum})

    return items

def _extract_content(soup) -> str:
    """Izvlači tekst iz stranice sa odlukom."""
    for sel in [".item-page", ".content", "article", "#content", "main"]:
        el = soup.select_one(sel)
        if el:
            for tag in el.select("script, style, nav, header, footer, .breadcrumb"):
                tag.decompose()
            tekst = el.get_text(separator="\n", strip=True)
            if len(tekst) > 200: return tekst
    body = soup.find("body")
    return body.get_text(separator="\n", strip=True)[:60000] if body else ""

def _scrape_category(client, kat: dict, preuzeti: set) -> list[dict]:
    """Scrape-uje jednu kategoriju sa svim pod-stranicama."""
    url = BASE + kat["url"]
    tip = kat["tip"]
    log.info("═ Kategorija: %s ═", tip)

    nova = []
    page = 0
    empty = 0

    while True:
        page_url = url if page == 0 else f"{url}?start={page * 20}"
        log.info("  Stranica offset=%d", page * 20)

        r = _get(client, page_url)
        if not r:
            empty += 1
            if empty >= 2: break
            page += 1
            time.sleep(RATE_S)
            continue

        soup = BeautifulSoup(r.text, "lxml")
        links = _extract_doc_links(soup, page_url)

        if not links:
            break

        log.info("  Pronađeno %d linkova", len(links))
        new_on_page = 0

        for item in links:
            if item["url"] in preuzeti: continue

            out_id   = _slug(item["url"])
            out_path = OUT_DIR / f"poverenik_{out_id}.json"
            if out_path.exists():
                preuzeti.add(item["url"])
                continue

            tekst_r = _get(client, item["url"])
            time.sleep(RATE_S * 0.7)

            if not tekst_r:
                continue

            tekst_soup = BeautifulSoup(tekst_r.text, "lxml")
            tekst = _extract_content(tekst_soup)

            if len(tekst) < 80:
                continue

            rec = {
                "id": f"poverenik_{out_id}",
                "izvor": "poverenik",
                "institucija": "Poverenik za informacije od javnog značaja i zaštitu podataka o ličnosti",
                "tip": tip,
                "naslov": item["naslov"],
                "datum": item["datum"],
                "url": item["url"],
                "tekst": tekst[:80000],
                "scraped_at": _iso(),
            }
            out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            preuzeti.add(item["url"])
            nova.append(rec)
            new_on_page += 1

        if new_on_page == 0 and page > 0:
            break

        page += 1
        time.sleep(RATE_S)

    log.info("  Kategorija završena: %d novih", len(nova))
    return nova

def run(dry_run=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (_ROOT / "data" / "poverenik").mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(_ROOT / "data" / "poverenik" / "scraper.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    ck = _load_ckpt()
    preuzeti = set(ck.get("preuzeti_urls", []))
    preuzeto = ck.get("preuzeto", 0)
    greske   = ck.get("greske", 0)

    log.info("═══ POVERENIK SCRAPER — %d kategorija ═══", len(KATEGORIJE))

    if dry_run:
        print(f"Kategorije: {len(KATEGORIJE)}")
        for k in KATEGORIJE: print(f"  {k['tip']}: {BASE + k['url'][:60]}")
        return

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for kat in KATEGORIJE:
            nova = _scrape_category(client, kat, preuzeti)
            preuzeto += len(nova)
            ck.update({
                "preuzeto": preuzeto, "greske": greske,
                "preuzeti_urls": list(preuzeti), "timestamp": _iso(),
            })
            _save_ckpt(ck)
            log.info("Ukupno preuzeto: %d", preuzeto)
            time.sleep(RATE_S * 2)

    ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_urls": list(preuzeti), "timestamp": _iso()})
    _save_ckpt(ck)
    log.info("═══ POVERENIK ZAVRŠEN: %d dokumenata ═══", preuzeto)
    print(f"\nPOVERENIK: {preuzeto} dokumenata u {OUT_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
