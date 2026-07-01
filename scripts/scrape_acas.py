#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — ACAS (Agencija za sprečavanje korupcije) scraper
Preuzima sve odluke sa acas.rs (~910 dokumenata, PDF format).

Pokretanje:
    python scripts/scrape_acas.py --dry-run
    python scripts/scrape_acas.py

Output: data/acas/odluke/{id}.json
"""

import argparse, hashlib, json, logging, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
import pypdf
from bs4 import BeautifulSoup

_ROOT = Path(__file__).parent.parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("acas_scraper")

BASE     = "https://www.acas.rs"
LIST_URL = "https://www.acas.rs/lat/decisions/all?page={page}"
RATE_S   = 1.2

OUT_DIR  = _ROOT / "data" / "acas" / "odluke"
PDF_DIR  = _ROOT / "data" / "acas" / "pdf"
CKPT     = _ROOT / "data" / "acas" / "checkpoint.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; VindexBot/1.0; legal research; contact: info@vindexai.rs)",
    "Accept": "text/html,*/*",
    "Accept-Language": "sr-RS,sr;q=0.9",
    "Referer": "https://www.acas.rs/lat/",
}

def _iso(): return datetime.now(timezone.utc).isoformat()
def _load_ckpt():
    if CKPT.exists(): return json.loads(CKPT.read_text(encoding="utf-8"))
    return {"preuzeto": 0, "greske": 0, "preuzeti_ids": [], "timestamp": _iso()}
def _save_ckpt(ck): CKPT.write_text(json.dumps(ck, ensure_ascii=False, indent=2), encoding="utf-8")

def _safe_id(url: str) -> str:
    name = Path(url.split("?")[0]).stem
    name = re.sub(r"[^\w]", "_", name).strip("_")[:60]
    return name or hashlib.md5(url.encode()).hexdigest()[:12]

def _get(client, url):
    for attempt in range(3):
        try:
            r = client.get(url, timeout=30)
            if r.status_code == 200: return r
            if r.status_code == 404: return None
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            log.warning("Greška (pokušaj %d): %s", attempt + 1, e)
            time.sleep(5 * (attempt + 1))
    return None

def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip(): parts.append(t)
        return "\n\n".join(parts)
    except Exception as e:
        log.error("PDF greška (%s): %s", pdf_path.name, e)
        return ""

def _scrape_listing(client, page: int) -> list[dict]:
    r = _get(client, LIST_URL.format(page=page))
    if not r: return []

    soup = BeautifulSoup(r.text, "lxml")
    items = []

    # ACAS koristi linkove sa /storage/decision_files/
    for a in soup.find_all("a", href=lambda h: h and "decision_files" in h):
        href = a["href"]
        if not href.startswith("http"): href = BASE + href

        naslov = a.get_text(strip=True)
        if not naslov: naslov = Path(href).stem.replace("-", " ").replace("_", " ")

        # Datum iz roditeljskog elementa
        parent = a.find_parent(["tr", "li", "div", "p"])
        datum = ""
        if parent:
            dm = re.search(r"(\d{1,2})[.\s]+(\d{1,2})[.\s]+(\d{4})", parent.get_text())
            if dm: datum = f"{dm.group(3)}-{dm.group(2).zfill(2)}-{dm.group(1).zfill(2)}"

        items.append({"url": href, "naslov": naslov[:400], "datum": datum})

    return items

def run(dry_run=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    (_ROOT / "data" / "acas").mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(str(_ROOT / "data" / "acas" / "scraper.log"), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s"))
    log.addHandler(fh)

    ck = _load_ckpt()
    preuzeti = set(ck.get("preuzeti_ids", []))
    preuzeto = ck.get("preuzeto", 0)
    greske   = ck.get("greske", 0)

    log.info("═══ ACAS SCRAPER — pokretanje ═══")

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        empty_pages = 0
        page = 1

        while True:
            log.info("Stranica %d...", page)
            items = _scrape_listing(client, page)

            if not items:
                empty_pages += 1
                if empty_pages >= 3:
                    log.info("Kraj listinga.")
                    break
                page += 1
                time.sleep(RATE_S)
                continue

            empty_pages = 0
            log.info("  Pronađeno %d odluka", len(items))

            if dry_run:
                for it in items[:3]: print(f"  {it['naslov'][:70]}")
                if page >= 2:
                    print(f"\nDRY RUN: ~{len(items)*65} odluka procenjeno (65 stranica)")
                    return
                page += 1
                time.sleep(RATE_S)
                continue

            for item in items:
                doc_id = _safe_id(item["url"])
                if doc_id in preuzeti: continue

                out_path = OUT_DIR / f"acas_{doc_id}.json"
                if out_path.exists():
                    preuzeti.add(doc_id)
                    continue

                # Preuzmi PDF
                pdf_path = PDF_DIR / f"{doc_id}.pdf"
                if not pdf_path.exists():
                    r_pdf = _get(client, item["url"])
                    if r_pdf and (b"%PDF" in r_pdf.content[:10] or len(r_pdf.content) > 1000):
                        pdf_path.write_bytes(r_pdf.content)
                        log.info("  PDF: %s (%d KB)", doc_id[:40], len(r_pdf.content)//1024)
                    else:
                        log.warning("  Nije PDF: %s", item["url"][:60])
                        greske += 1
                        preuzeti.add(doc_id)
                        continue
                    time.sleep(RATE_S * 0.5)

                tekst = _extract_pdf_text(pdf_path)

                rec = {
                    "id": f"acas_{doc_id}",
                    "izvor": "acas",
                    "institucija": "Agencija za sprečavanje korupcije",
                    "naslov": item["naslov"],
                    "datum": item["datum"],
                    "url": item["url"],
                    "tekst": tekst[:80000],
                    "scraped_at": _iso(),
                }
                out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                preuzeti.add(doc_id)
                preuzeto += 1
                log.info("  Sačuvano: %s", doc_id[:40])

            ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_ids": list(preuzeti), "timestamp": _iso()})
            _save_ckpt(ck)
            log.info("  Ukupno: %d", preuzeto)
            page += 1
            time.sleep(RATE_S)

    ck.update({"preuzeto": preuzeto, "greske": greske, "preuzeti_ids": list(preuzeti), "timestamp": _iso()})
    _save_ckpt(ck)
    log.info("═══ ACAS ZAVRŠEN: %d odluka ═══", preuzeto)
    print(f"\nACAS: {preuzeto} odluka u {OUT_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
