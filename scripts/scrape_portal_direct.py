#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Direktan scraper za sudskapraksa.sud.rs
Kombinuje listing paginiranje + fetch detalja bez zasebnog IDs koraka.
Producer/Consumer pattern: listing fetcher -> details fetcher

Pokretanje:
    python scripts/scrape_portal_direct.py
    python scripts/scrape_portal_direct.py --workers 15 --start-page 1
"""
import asyncio, json, re, sys, time, argparse
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    print("pip install httpx"); sys.exit(1)

ROOT     = Path(__file__).parent.parent
OUT_DIR  = ROOT / "data" / "sudskapraksa_portal" / "odluke"
DONE_FILE = ROOT / "data" / "sudskapraksa_portal" / "done_direct.json"

BASE     = "https://sudskapraksa.sud.rs"
LIST_URL = f"{BASE}/sudska-praksa/index"
DET_URL  = f"{BASE}/sudska-praksa/{{id}}"

HDRS = {
    "User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36",
    "Accept": "application/json",
}

MIN_TXT  = 200
PER_PAGE = 25

SUD = {1:"VKS",2:"AS Beograd",3:"AS Novi Sad",4:"AS Kragujevac",5:"AS Nis",
       6:"Prekrsajni apelacioni sud",7:"Upravni sud",8:"Visoki savet sudstva",9:"Vrhovni sud"}


def _iso(): return datetime.now(timezone.utc).isoformat()


def save_doc(doc: dict, out_dir: Path) -> bool:
    tekst = (doc.get("tekst_odluke_preview") or "").strip()
    if len(tekst) < MIN_TXT:
        return False
    doc_id = str(doc.get("id",""))
    safe   = re.sub(r"[^A-Za-z0-9_\-]","_", doc_id)[:80]
    vid    = f"sp_portal_{safe}"
    out    = out_dir / f"{vid}.json"
    if out.exists():
        return False
    rec = {
        "id": vid, "izvor": "sudskapraksa_portal",
        "sud": SUD.get(doc.get("sud_id"), f"Sud {doc.get('sud_id')}"),
        "upisnik": doc.get("upisnik",""),
        "broj": doc.get("jedinstveni_broj_predmeta",""),
        "datum": (doc.get("datum_odluke") or "")[:10],
        "tekst": tekst,
        "url": f"{BASE}/sudska-praksa/{doc_id}",
        "scraped_at": _iso(),
    }
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


async def fetch_detail(client, doc_id: str, out_dir: Path, sem: asyncio.Semaphore) -> str:
    async with sem:
        try:
            r = await client.get(DET_URL.format(id=doc_id), params={"_format":"json"}, headers=HDRS, timeout=20)
            if r.status_code == 200:
                docs = r.json().get("result",{}).get("response",{}).get("docs",[])
                if docs and save_doc(docs[0], out_dir):
                    return "ok"
                return "skip"
            return f"http{r.status_code}"
        except Exception as e:
            return f"err"
        finally:
            await asyncio.sleep(0.3)


async def run(workers: int, start_page: int):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load done IDs
    done = set()
    if DONE_FILE.exists():
        done = set(json.loads(DONE_FILE.read_text(encoding="utf-8")))
        print(f"[RESUME] {len(done)} vec gotovo")

    existing = len(list(OUT_DIR.glob("*.json")))
    print(f"[START] Fajlova u out_dir: {existing} | Workers: {workers}")

    sem = asyncio.Semaphore(workers)
    stats = {"ok":0,"skip":0,"err":0}
    t0 = time.time()
    done_new = set()

    limits = httpx.Limits(max_keepalive_connections=workers+2, max_connections=workers+5)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:

        # Fetch first page to get total
        r = await client.get(LIST_URL, params={"_format":"json","page":1}, headers=HDRS, timeout=20)
        data = r.json()
        total_count = data.get("count", 0)
        per_page    = data.get("perPage", PER_PAGE)
        total_pages = (total_count + per_page - 1) // per_page
        print(f"[INFO] Ukupno: {total_count} odluka, {total_pages} strana")

        for page in range(start_page, total_pages + 1):
            try:
                if page > start_page:
                    r = await client.get(LIST_URL, params={"_format":"json","page":page}, headers=HDRS, timeout=20)
                    data = r.json()

                ids = [str(item["id"]) for item in data.get("items",[]) if item.get("id")]
                new_ids = [i for i in ids if i not in done and i not in done_new]

                if not new_ids:
                    await asyncio.sleep(0.2)
                    continue

                # Fetch details za sve nove na ovoj stranici
                tasks = [fetch_detail(client, i, OUT_DIR, sem) for i in new_ids]
                results = await asyncio.gather(*tasks)

                for i, res in zip(new_ids, results):
                    if res == "ok": stats["ok"] += 1; done_new.add(i)
                    elif res == "skip": stats["skip"] += 1; done_new.add(i)
                    else: stats["err"] += 1

                if page % 50 == 0 or page == total_pages:
                    elapsed = time.time() - t0
                    total_done = stats["ok"] + stats["skip"] + stats["err"]
                    rate = total_done / elapsed if elapsed > 0 else 0
                    eta  = (total_count - len(done) - total_done) / rate if rate > 0 else 0
                    print(f"[P{page}/{total_pages}] ok:{stats['ok']} skip:{stats['skip']} err:{stats['err']} "
                          f"| {rate:.1f}/s | ETA {eta/60:.0f}min")
                    DONE_FILE.write_text(json.dumps(sorted(done|done_new), ensure_ascii=False), encoding="utf-8")

                await asyncio.sleep(0.15)

            except Exception as e:
                print(f"[ERR] Strana {page}: {e}")
                await asyncio.sleep(2)

    # Final save
    DONE_FILE.write_text(json.dumps(sorted(done|done_new), ensure_ascii=False), encoding="utf-8")
    total_files = len(list(OUT_DIR.glob("*.json")))
    print(f"\n=== ZAVRSENO ===")
    print(f"OK: {stats['ok']} | Skip: {stats['skip']} | Err: {stats['err']}")
    print(f"Ukupno u out_dir: {total_files}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--start-page", type=int, default=1)
    args = p.parse_args()
    asyncio.run(run(args.workers, args.start_page))


if __name__ == "__main__":
    main()
