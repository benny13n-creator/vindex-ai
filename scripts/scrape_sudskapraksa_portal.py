#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Scraper za sudskapraksa.sud.rs JSON API
75,157 sudskih odluka dostupno bez reCAPTCHA putem JSON API.

Korak 1: Paginiranje listinga -> prikupljanje svih ID-eva (3007 strana x 25)
Korak 2: Async fetch detalja po ID-u -> ekstrakcija tekst_odluke_preview
Korak 3: Snimanje u data/sudskapraksa_portal/odluke/{id}.json

Pokretanje:
    python scripts/scrape_sudskapraksa_portal.py
    python scripts/scrape_sudskapraksa_portal.py --only-ids     # samo prikupi ID-eve
    python scripts/scrape_sudskapraksa_portal.py --only-details # samo preuzmi tekstove (IDs vec postoje)
    python scripts/scrape_sudskapraksa_portal.py --workers 15   # broj concurrent requests
"""

import asyncio
import json
import re
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    print("httpx nije instaliran. Pokreni: pip install httpx")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
OUT_DIR     = ROOT / "data" / "sudskapraksa_portal" / "odluke"
IDS_FILE    = ROOT / "data" / "sudskapraksa_portal" / "all_ids.json"
DONE_FILE   = ROOT / "data" / "sudskapraksa_portal" / "done_ids.json"

BASE_URL    = "https://sudskapraksa.sud.rs"
LIST_URL    = f"{BASE_URL}/sudska-praksa/index"
DETAIL_URL  = f"{BASE_URL}/sudska-praksa/{{id}}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://sudskapraksa.sud.rs/sudska-praksa",
}

MIN_TEKST   = 200
PER_PAGE    = 25
CRAWL_DELAY = 0.3   # sekundi izmedju zahteva po workeru

SUD_IDS = {
    1: "Vrhovni kasacioni sud",
    2: "Apelacioni sud Beograd",
    3: "Apelacioni sud Novi Sad",
    4: "Apelacioni sud Kragujevac",
    5: "Apelacioni sud Nis",
    6: "Prekrsajni apelacioni sud",
    7: "Upravni sud",
    8: "Visoki savet sudstva",
    9: "Vrhovni sud",
}


def _iso():
    return datetime.now(timezone.utc).isoformat()


def save_decision(doc: dict, out_dir: Path) -> bool:
    """Konvertuj Solr doc u standardni Vindex format i sacuvaj."""
    tekst = (doc.get("tekst_odluke_preview") or "").strip()
    if len(tekst) < MIN_TEKST:
        return False

    doc_id = str(doc.get("id", ""))
    safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", doc_id)[:80]
    vindex_id = f"sp_portal_{safe_id}"

    sud_id = doc.get("sud_id")
    sud = SUD_IDS.get(sud_id, f"Sud {sud_id}")

    datum = (doc.get("datum_odluke") or "")[:10]

    rec = {
        "id":       vindex_id,
        "izvor":    "sudskapraksa_portal",
        "sud":      sud,
        "sud_id":   sud_id,
        "materija": str(doc.get("pravna_materija_id", "")),
        "upisnik":  doc.get("upisnik", ""),
        "broj":     doc.get("jedinstveni_broj_predmeta", ""),
        "datum":    datum,
        "tekst":    tekst,
        "url":      f"{BASE_URL}/sudska-praksa/{doc_id}",
        "scraped_at": _iso(),
    }

    out_path = out_dir / f"{vindex_id}.json"
    out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


async def fetch_all_ids(client: httpx.AsyncClient) -> list[str]:
    """Preuzmi sve ID-eve sa listing API (3007 strana)."""
    all_ids = []

    print("[IDS] Preuzimam prvu stranu da dobijem ukupan broj...")
    r = await client.get(LIST_URL, params={"_format": "json", "page": 1}, headers=HEADERS, timeout=20)
    data = r.json()
    total = data.get("count", 0)
    per_page = data.get("perPage", PER_PAGE)
    total_pages = (total + per_page - 1) // per_page
    print(f"[IDS] Ukupno odluka: {total} | Strana: {total_pages} | Po strani: {per_page}")

    for item in data.get("items", []):
        if item.get("id"):
            all_ids.append(str(item["id"]))

    for page in range(2, total_pages + 1):
        try:
            r = await client.get(LIST_URL, params={"_format": "json", "page": page}, headers=HEADERS, timeout=20)
            data = r.json()
            for item in data.get("items", []):
                if item.get("id"):
                    all_ids.append(str(item["id"]))

            if page % 100 == 0 or page == total_pages:
                print(f"[IDS] Strana {page}/{total_pages} — sakupljeno {len(all_ids)} ID-eva")

            await asyncio.sleep(0.2)

        except Exception as e:
            print(f"[IDS] GRESKA strana {page}: {e}")
            await asyncio.sleep(2)

    return all_ids


async def fetch_decision(client: httpx.AsyncClient, doc_id: str, out_dir: Path, semaphore: asyncio.Semaphore) -> tuple[str, str]:
    """Preuzmi detalj jedne odluke. Vraca (id, status)."""
    async with semaphore:
        try:
            url = DETAIL_URL.format(id=doc_id)
            r = await client.get(url, params={"_format": "json"}, headers=HEADERS, timeout=20)

            if r.status_code != 200:
                return doc_id, f"HTTP {r.status_code}"

            data = r.json()
            docs = data.get("result", {}).get("response", {}).get("docs", [])
            if not docs:
                # Pokusaj item iz items
                items = data.get("items", [])
                if items and items[0].get("data"):
                    docs = [items[0]["data"]]

            if not docs:
                return doc_id, "no_docs"

            doc = docs[0]
            if save_decision(doc, out_dir):
                return doc_id, "ok"
            else:
                return doc_id, "short"

        except Exception as e:
            return doc_id, f"err:{e}"
        finally:
            await asyncio.sleep(CRAWL_DELAY)


async def fetch_all_details(all_ids: list[str], done_ids: set[str], out_dir: Path, workers: int) -> dict:
    """Async preuzimanje detalja za sve IDs."""
    pending = [doc_id for doc_id in all_ids if doc_id not in done_ids]
    total   = len(pending)
    print(f"[DETAILS] Preostalo: {total} | Preskoceno (vec gotovo): {len(done_ids)}")

    semaphore = asyncio.Semaphore(workers)
    stats = {"ok": 0, "short": 0, "err": 0, "no_docs": 0}
    done_new = set()
    t0 = time.time()

    limits = httpx.Limits(max_keepalive_connections=workers, max_connections=workers + 5)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        tasks = [fetch_decision(client, doc_id, out_dir, semaphore) for doc_id in pending]

        for i, coro in enumerate(asyncio.as_completed(tasks)):
            doc_id, status = await coro

            if status == "ok":
                stats["ok"] += 1
                done_new.add(doc_id)
            elif status == "short":
                stats["short"] += 1
                done_new.add(doc_id)
            elif status == "no_docs":
                stats["no_docs"] += 1
            else:
                stats["err"] += 1

            if (i + 1) % 500 == 0 or i + 1 == total:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total - i - 1) / rate if rate > 0 else 0
                print(f"[DETAILS] {i+1}/{total} | ok:{stats['ok']} err:{stats['err']} | "
                      f"{rate:.1f}/s | ETA: {eta/60:.0f}min")

                # Sacuvaj checkpoint
                all_done = done_ids | done_new
                DONE_FILE.write_text(json.dumps(sorted(all_done), ensure_ascii=False), encoding="utf-8")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Scraper za sudskapraksa.sud.rs")
    parser.add_argument("--only-ids",     action="store_true", help="Samo prikupi ID-eve")
    parser.add_argument("--only-details", action="store_true", help="Samo preuzmi tekstove")
    parser.add_argument("--workers",      type=int, default=10, help="Broj concurrent requests (default: 10)")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== SUDSKAPRAKSA.SUD.RS SCRAPER ===")
    print(f"Output: {OUT_DIR}")
    print(f"Workers: {args.workers}")

    # KORAK 1: Prikupljanje ID-eva
    if not args.only_details:
        if IDS_FILE.exists():
            all_ids = json.loads(IDS_FILE.read_text(encoding="utf-8"))
            print(f"[IDS] Vec postoje: {len(all_ids)} ID-eva iz {IDS_FILE}")
        else:
            print("[IDS] Prikupljanje svih ID-eva sa listing API...")
            all_ids = asyncio.run(
                _fetch_ids_only()
            )
            IDS_FILE.write_text(json.dumps(all_ids, ensure_ascii=False), encoding="utf-8")
            print(f"[IDS] Sacuvano {len(all_ids)} ID-eva -> {IDS_FILE}")

        if args.only_ids:
            return
    else:
        if not IDS_FILE.exists():
            print(f"GRESKA: {IDS_FILE} ne postoji. Pokreni bez --only-details prvo.")
            sys.exit(1)
        all_ids = json.loads(IDS_FILE.read_text(encoding="utf-8"))
        print(f"[IDS] Ucitano {len(all_ids)} ID-eva")

    # KORAK 2: Preuzimanje detalja
    done_ids = set()
    if DONE_FILE.exists():
        done_ids = set(json.loads(DONE_FILE.read_text(encoding="utf-8")))
        print(f"[RESUME] Vec preuzeto: {len(done_ids)} odluka")

    existing = len(list(OUT_DIR.glob("*.json")))
    print(f"[RESUME] Fajlova u out_dir: {existing}")

    stats = asyncio.run(
        fetch_all_details(all_ids, done_ids, OUT_DIR, args.workers)
    )

    total_files = len(list(OUT_DIR.glob("*.json")))
    print(f"\n=== ZAVRSENO ===")
    print(f"Sacuvano odluka:   {stats['ok']}")
    print(f"Prekratko tekst:   {stats['short']}")
    print(f"Nema docs:         {stats['no_docs']}")
    print(f"Greske:            {stats['err']}")
    print(f"Ukupno u out_dir:  {total_files}")
    print(f"Lokacija: {OUT_DIR}")


async def _fetch_ids_only():
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=8)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        return await fetch_all_ids(client)


if __name__ == "__main__":
    main()
