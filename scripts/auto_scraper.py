# -*- coding: utf-8 -*-
"""
Vindex AI — Phase 5.2: Auto-scraper za nove biltene sudske prakse.

Strategija: prediktivno + HTML scraping
  1. Pokušava predvidljive URL-ove za buduće biltene (VKS, AS Beograd, AS Niš, AS Kragujevac)
  2. Scrapes HTML bilten liste za nove linkove
  3. Verifikuje PDF fajlove (content-type + magic bytes)
  4. Sprema stanje u data/scraper_state.json (standalone) ili Supabase (kada koristi API)

Standalone upotreba:
    python scripts/auto_scraper.py --check       # pronađi nove, ne skidaj
    python scripts/auto_scraper.py --download     # pronađi + skini u data/sudska_praksa/raw_bilteni/
    python scripts/auto_scraper.py --court vks    # samo VKS
    python scripts/auto_scraper.py --since 2025   # samo bilteni od 2025

Veze sa ostalim skriptama:
  --download → ingest_bilten.py → ingest_bilten_to_pinecone.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("auto_scraper")

_PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = _PROJECT_ROOT / "data" / "scraper_state.json"
DOWNLOAD_BASE = _PROJECT_ROOT / "data" / "sudska_praksa" / "raw_bilteni"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
POLITE_DELAY = 8   # seconds between requests
MIN_PDF_BYTES = 20_000

_CURRENT_YEAR = datetime.now().year


# ─── Katalog sudova i URL strategija ─────────────────────────────────────────

def _vks_candidates() -> list[dict]:
    """VKS: 3 biltena godišnje (1, 2, 3). Poslednji potvrđen: 2025-3."""
    base_new  = "https://www.vrh.sud.rs/sites/default/files/files/Bilteni/VrhovniSud"
    base_old  = "https://www.vrh.sud.rs/sites/default/files/attachments"
    candidates = []
    for year in range(2025, _CURRENT_YEAR + 2):
        for num in range(1, 4):
            slug = f"bilten_vks_{year}_{num}"
            url_new = f"{base_new}/Bilten-VS-{year}-{num}.pdf"
            candidates.append({
                "slug":  slug,
                "url":   url_new,
                "court": "vks",
                "label": f"VS Bilten {year}-{num}",
                "year":  year,
            })
    return candidates


def _as_bg_candidates() -> list[dict]:
    """AS Beograd: 1 bilten godišnje, numerisan. Poslednji: 14 (2024)."""
    base = "https://bg.ap.sud.rs/files"
    candidates = []
    # Try next 3 bilten numbers from 15
    for num in range(15, 19):
        year = 2023 + (num - 13)
        slug = f"bilten_as_bg_{num}"
        for tmpl in [
            f"{base}/Bilten%20Apel%20BG%20{num}-{year}.pdf",
            f"{base}/BiltenApelBG{num}-{year}.pdf",
            f"{base}/Bilten%20broj%20{num}%20u%20elektronskoj%20formi.pdf",
        ]:
            candidates.append({
                "slug":  slug + f"_v{candidates.count({'slug': slug})+1 if any(c['slug']==slug for c in candidates) else 1}",
                "url":   tmpl,
                "court": "as_bg",
                "label": f"AS Beograd Bilten {num} ({year})",
                "year":  year,
            })
    return candidates


def _as_nis_candidates() -> list[dict]:
    """AS Niš: 1 bilten godišnje, po godini. Poslednji: 2023-24."""
    base = "http://www.ni.ap.sud.rs/resources/files"
    candidates = []
    for year in range(2025, _CURRENT_YEAR + 2):
        slug = f"bilten_as_nis_{year}"
        for tmpl in [
            f"{base}/Bilten%20{year}%20Nis.pdf",
            f"{base}/Bilten-{year}-Nis.pdf",
            f"{base}/Bilten_{year}_Nis.pdf",
        ]:
            candidates.append({
                "slug":  slug,
                "url":   tmpl,
                "court": "as_nis",
                "label": f"AS Niš Bilten {year}",
                "year":  year,
            })
    return candidates


def _as_kg_candidates() -> list[dict]:
    """AS Kragujevac: bilteni na www.kg.ap.sud.rs."""
    base = "https://www.kg.ap.sud.rs/resources/files"
    candidates = []
    for year in range(2023, _CURRENT_YEAR + 2):
        slug = f"bilten_as_kg_{year}"
        for tmpl in [
            f"{base}/Bilten%20{year}.pdf",
            f"{base}/bilten_{year}.pdf",
            f"{base}/Bilten-{year}-KG.pdf",
        ]:
            candidates.append({
                "slug":  slug,
                "url":   tmpl,
                "court": "as_kg",
                "label": f"AS Kragujevac Bilten {year}",
                "year":  year,
            })
    return candidates


# ─── HTML scraping za bilten liste ───────────────────────────────────────────

_BILTEN_PAGES = {
    "vks": [
        "https://www.vrh.sud.rs/bilteni",
        "https://www.vrh.sud.rs/sudska-praksa/bilteni",
    ],
    "as_bg": [
        "https://bg.ap.sud.rs/sudska-praksa/bilteni",
        "https://bg.ap.sud.rs/publikacije",
    ],
    "as_nis": [
        "http://www.ni.ap.sud.rs/praksa/bilteni",
        "http://www.ni.ap.sud.rs/bilteni",
    ],
    "as_kg": [
        "https://www.kg.ap.sud.rs/bilteni",
        "https://www.kg.ap.sud.rs/sudska-praksa",
    ],
}

_PDF_LINK_RE = re.compile(
    r'href=["\']([^"\']*(?:bilten|Bilten|BILTEN)[^"\']*\.pdf)["\']',
    re.IGNORECASE,
)


def _scrape_html_links(court: str, client) -> list[dict]:
    """Scrapes HTML bilten listing pages for PDF links."""
    found = []
    pages = _BILTEN_PAGES.get(court, [])
    for page_url in pages:
        try:
            resp = client.get(page_url, timeout=20)
            if resp.status_code != 200:
                log.debug("[HTML] %s HTTP %d — %s", court, resp.status_code, page_url)
                continue
            for m in _PDF_LINK_RE.finditer(resp.text):
                href = m.group(1)
                full_url = urljoin(page_url, href)
                if not full_url.startswith("http"):
                    continue
                fname = Path(urlparse(full_url).path).name
                found.append({
                    "slug":  f"{court}_html_{hashlib.md5(full_url.encode()).hexdigest()[:8]}",
                    "url":   full_url,
                    "court": court,
                    "label": f"{court.upper()} {fname}",
                    "year":  _year_from_url(full_url),
                })
            log.info("[HTML] %s → %d linkova na %s", court, len(found), page_url)
            break  # first page that worked
        except Exception as exc:
            log.debug("[HTML] %s fetch greška: %s", court, exc)
    return found


def _year_from_url(url: str) -> int:
    m = re.search(r"20(2\d)", url)
    return int(m.group(0)) if m else _CURRENT_YEAR


# ─── State management ─────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── PDF validation ───────────────────────────────────────────────────────────

def _valid_pdf(data: bytes) -> bool:
    return len(data) >= MIN_PDF_BYTES and data[:4] == b"%PDF"


# ─── Core discovery ───────────────────────────────────────────────────────────

def discover(
    courts: Optional[list[str]] = None,
    since_year: int = 2024,
    use_html: bool = True,
) -> list[dict]:
    """
    Pronalazi nove biltene (HTTP HEAD/GET probe + HTML scraping).
    Vraća listu dicts sa: url, court, label, year, slug, size_bytes.
    """
    try:
        import httpx
    except ImportError:
        log.error("httpx nije instaliran — instalirajte: pip install httpx")
        sys.exit(1)

    all_courts = courts or ["vks", "as_bg", "as_nis", "as_kg"]

    candidates: list[dict] = []
    for court in all_courts:
        if court == "vks":
            candidates += _vks_candidates()
        elif court == "as_bg":
            candidates += _as_bg_candidates()
        elif court == "as_nis":
            candidates += _as_nis_candidates()
        elif court == "as_kg":
            candidates += _as_kg_candidates()

    # Filter by year
    candidates = [c for c in candidates if c.get("year", 0) >= since_year]

    state = load_state()
    already_done = set(state.keys())

    # De-duplicate by URL
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for c in candidates:
        if c["url"] not in seen_urls:
            seen_urls.add(c["url"])
            deduped.append(c)

    log.info("Probam %d kandidata za %s (od %d)...", len(deduped), all_courts, since_year)

    discovered: list[dict] = []
    headers = {"User-Agent": UA, "Accept": "application/pdf,*/*"}

    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        # HTML scraping
        if use_html:
            for court in all_courts:
                time.sleep(POLITE_DELAY)
                html_links = _scrape_html_links(court, client)
                for lnk in html_links:
                    if lnk["url"] not in seen_urls and lnk["url"] not in already_done:
                        seen_urls.add(lnk["url"])
                        deduped.append(lnk)

        for i, cand in enumerate(deduped):
            url = cand["url"]
            if url in already_done:
                log.debug("[SKIP] %s (već obrađen)", url)
                continue

            try:
                if i > 0:
                    time.sleep(POLITE_DELAY)
                head = client.head(url, timeout=15)
                if head.status_code == 200:
                    ct = head.headers.get("content-type", "")
                    size = int(head.headers.get("content-length", 0))
                    if "pdf" in ct.lower() or size >= MIN_PDF_BYTES:
                        log.info("[NOVI] %-40s | %s | %d bytes",
                                 cand["label"], cand["court"], size)
                        discovered.append({**cand, "size_bytes": size})
                    else:
                        log.debug("[HEAD OK] %s ali content-type=%s size=%d — preskačem",
                                  cand["label"], ct, size)
                elif head.status_code == 405:
                    # HEAD nije podržan — probaj GET range
                    get_r = client.get(url, headers={**headers, "Range": "bytes=0-127"}, timeout=20)
                    if get_r.status_code in (200, 206) and _valid_pdf(get_r.content[:4] if len(get_r.content) >= 4 else b""):
                        log.info("[NOVI via GET] %s", cand["label"])
                        discovered.append({**cand, "size_bytes": len(get_r.content)})
                else:
                    log.debug("[%d] %s — nije dostupan", head.status_code, cand["label"])
            except Exception as exc:
                log.debug("[ERR] %s: %s", cand["label"], exc)

    log.info("Ukupno novih biltena: %d", len(discovered))
    return discovered


# ─── Download ────────────────────────────────────────────────────────────────

def download_discovered(discovered: list[dict]) -> list[dict]:
    """Skida pronađene PDF fajlove u data/sudska_praksa/raw_bilteni/{court}/."""
    try:
        import httpx
    except ImportError:
        sys.exit(1)

    state = load_state()
    results = []
    headers = {"User-Agent": UA}

    with httpx.Client(headers=headers, timeout=120, follow_redirects=True) as client:
        for i, item in enumerate(discovered):
            if i > 0:
                time.sleep(POLITE_DELAY)
            url    = item["url"]
            court  = item["court"]
            fname  = Path(urlparse(url).path).name or f"{item['slug']}.pdf"
            out_dir = DOWNLOAD_BASE / court
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / fname

            if out_path.exists() and out_path.stat().st_size >= MIN_PDF_BYTES:
                log.info("[SKIP] %s — već postoji (%d KB)", fname, out_path.stat().st_size // 1024)
                state[url] = {"status": "downloaded", "path": str(out_path),
                              "downloaded_at": datetime.now(timezone.utc).isoformat()}
                results.append({**item, "status": "already_exists", "path": str(out_path)})
                continue

            try:
                resp = client.get(url, timeout=90)
                resp.raise_for_status()
                data = resp.content
                if not _valid_pdf(data):
                    log.warning("[INVALID PDF] %s — magic bytes: %s", fname, data[:4])
                    results.append({**item, "status": "invalid_pdf"})
                    continue
                out_path.write_bytes(data)
                log.info("[OK] %s → %s (%d KB)", item["label"], out_path, len(data) // 1024)
                state[url] = {"status": "downloaded", "path": str(out_path),
                              "downloaded_at": datetime.now(timezone.utc).isoformat()}
                results.append({**item, "status": "downloaded", "path": str(out_path)})
            except Exception as exc:
                log.error("[FAIL] %s: %s", item["label"], exc)
                results.append({**item, "status": "failed", "error": str(exc)})

    save_state(state)
    return results


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Vindex AI — auto-scraper za sudske biltene")
    ap.add_argument("--check",    action="store_true", help="Pronađi nove biltene (ne skidaj)")
    ap.add_argument("--download", action="store_true", help="Pronađi + skini PDF fajlove")
    ap.add_argument("--court",    nargs="+", choices=["vks","as_bg","as_nis","as_kg"],
                    help="Samo određeni sudovi (default: svi)")
    ap.add_argument("--since",    type=int, default=2024, metavar="YEAR",
                    help="Traži biltene od ove godine nadalje (default: 2024)")
    ap.add_argument("--no-html",  action="store_true", help="Ne scrape HTML liste")
    ap.add_argument("--json",     action="store_true", help="Izlaz u JSON formatu")
    args = ap.parse_args()

    if not args.check and not args.download:
        ap.print_help()
        sys.exit(0)

    found = discover(
        courts=args.court,
        since_year=args.since,
        use_html=not args.no_html,
    )

    if not found:
        log.info("Nema novih biltena.")
        if args.json:
            print(json.dumps({"new_count": 0, "bilteni": []}, ensure_ascii=False))
        return

    if args.json:
        if args.download:
            results = download_discovered(found)
            print(json.dumps({"new_count": len(found), "bilteni": results}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"new_count": len(found), "bilteni": found}, ensure_ascii=False, indent=2))
        return

    print(f"\n{'='*60}")
    print(f"  NOVI BILTENI: {len(found)}")
    print(f"{'='*60}")
    for b in found:
        print(f"  [{b['court'].upper():6}] {b['label']}")
        print(f"           {b['url']}")
    print(f"{'='*60}\n")

    if args.download:
        print("Skidanje...\n")
        results = download_discovered(found)
        ok  = [r for r in results if r["status"] == "downloaded"]
        err = [r for r in results if r["status"] == "failed"]
        print(f"\nSkinuto: {len(ok)} | Greška: {len(err)}")
        if ok:
            print("\nSledeći korak:")
            for r in ok:
                print(f"  python scripts/ingest_bilten.py --pdf {r['path']} --court '{r['court']}'")
            print(f"  python scripts/ingest_bilten_to_pinecone.py --decisions data/sudska_praksa/raw_bilteni/{results[0]['court']}/decisions/")


if __name__ == "__main__":
    main()
