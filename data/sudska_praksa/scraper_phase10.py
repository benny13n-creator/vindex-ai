#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex Phase 1.0 — VKS Decision Scraper
Collects ~200 court decisions from https://www.vrh.sud.rs
Stratified: 50 each × (Krivična=33, Građanska=19, Upravna=9, Zaštita=8)
Rate-limited to ≥10s between requests (robots.txt Crawl-delay).
"""

import json
import logging
import os
import re
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import httpx
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("vks_scraper")

BASE_URL = "https://www.vrh.sud.rs"
SEARCH_URL = f"{BASE_URL}/sr-lat/solr-search-page/results"
UA = "Vindex AI Legal Research (vindex-ai.onrender.com; contact: vindex.rs)"
CRAWL_DELAY = 10.5  # seconds — respects robots.txt Crawl-delay: 10
SCRAPER_VERSION = "1.0"

MATTERS = [
    {"slug": "krivicna",   "label": "Krivična",   "matter_id": "33"},
    {"slug": "gradjanska", "label": "Građanska",   "matter_id": "19"},
    {"slug": "upravna",    "label": "Upravna",     "matter_id": "9"},
    {"slug": "zastitaprava", "label": "Zaštita prava", "matter_id": "8"},
]

TARGET_PER_MATTER = 50
MAX_PAGES = 10
RESULTS_PER_PAGE = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(decision_number: str, url: str) -> str:
    """Create a filesystem-safe ID from decision number or URL."""
    if decision_number:
        safe = re.sub(r"[^A-Za-z0-9žćčšđŽĆČŠĐ]", "_", decision_number)
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe[:80]
    # Fallback: hash of URL
    return "id_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _extract_decision_number(soup: BeautifulSoup) -> str:
    """Extract decision number from h1.
    Handles single-word registrants ('Kzz 754/2025') and
    multi-word registrants ('Rž1 u 31/2026').
    """
    for h1 in soup.find_all("h1"):
        text = h1.get_text(strip=True)
        # Greedily match everything before the number/year pattern
        m = re.search(r"^(.+?)\s+(\d+/\d{4})", text)
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return ""


def _extract_date(text: str) -> str:
    """Find first date pattern DD.MM.YYYY in text. Returns YYYY-MM-DD."""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\.", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


def _extract_court(text: str) -> str:
    """Extract court name from decision body text."""
    if "VRHOVNI SUD" in text.upper() and "KASACIONI" not in text.upper():
        return "Vrhovni sud"
    if "VRHOVNI KASACIONI SUD" in text.upper() or "Vrhovni kasacioni sud" in text:
        return "Vrhovni kasacioni sud"
    if "Vrhovni sud" in text:
        return "Vrhovni sud"
    if "Vrhovni kasacioni sud" in text:
        return "Vrhovni kasacioni sud"
    return "Vrhovni sud Srbije"


def _extract_registrant(decision_number: str) -> str:
    """Extract registrant code from decision number like 'Kzz 754/2025' → 'Kzz'."""
    if not decision_number:
        return ""
    return decision_number.split()[0] if decision_number.split() else ""


def fetch_search_page(
    client: httpx.Client,
    matter_id: str,
    page: int = 0,
    last_request_time: list = None,
) -> BeautifulSoup | None:
    """Fetch one search results page. Returns BS4 or None on error."""
    params = (
        f"court_type=sc&matter={matter_id}&sorting=by_date_down"
        f"&results={RESULTS_PER_PAGE}&page={page}"
    )
    url = f"{SEARCH_URL}?{params}"
    _rate_limit(last_request_time)
    try:
        r = client.post(url, data={"op": "Pretraga", "level": "1"}, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            log.error("HTTP 403 BLOCKED — HARD STOP")
            raise
        if e.response.status_code == 429:
            log.warning("HTTP 429 — backing off 30s")
            time.sleep(30)
            return None
        log.warning("HTTP %d on search page: %s", e.response.status_code, url)
        return None
    except Exception as e:
        log.warning("Connection error on search page %s: %s", url, e)
        return None


def extract_results(soup: BeautifulSoup, matter_label: str) -> list[dict]:
    """Extract decision stubs from search results page."""
    items = []
    for li in soup.select("li.search-result"):
        a = li.find("h3").find("a") if li.find("h3") else None
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            href = BASE_URL + href
        decision_text = a.get_text(strip=True)
        summary_div = li.find("div", class_="result-summary")
        summary = summary_div.get_text(strip=True) if summary_div else ""
        # Parse summary: "Krivična materija / Upisnici: Kzz / Br. predmeta: 754/2025 / Datum: 15.04.2026."
        registrant = re.search(r"Upisnici:\s*([^/]+)", summary)
        reg_val = registrant.group(1).strip() if registrant else ""
        date_m = re.search(r"Datum:\s*(\d{2}\.\d{2}\.\d{4})", summary)
        date_val = date_m.group(1) if date_m else ""
        # Convert date
        date_iso = ""
        if date_val:
            parts = date_val.split(".")
            if len(parts) >= 3:
                date_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
        items.append({
            "url": href,
            "decision_title": decision_text,
            "matter": matter_label,
            "registrant_from_search": reg_val,
            "date_from_search": date_iso,
        })
    return items


def fetch_decision(
    client: httpx.Client,
    url: str,
    matter_slug: str,
    matter_label: str,
    base_dir: Path,
    last_request_time: list,
    registrant_hint: str = "",
    date_hint: str = "",
) -> dict | None:
    """Fetch one decision page, parse, save HTML + JSON. Returns JSON dict or None."""
    _rate_limit(last_request_time)
    retries = 0
    while retries < 3:
        try:
            r = client.get(url, timeout=30)
            if r.status_code == 403:
                log.error("HTTP 403 BLOCKED at %s — HARD STOP", url)
                raise httpx.HTTPStatusError("403", request=r.request, response=r)
            if r.status_code == 429:
                wait = 30 * (2 ** retries)
                if retries >= 2:
                    log.error("HTTP 429 max retries exceeded at %s", url)
                    return None
                log.warning("HTTP 429 at %s — backing off %ds", url, wait)
                time.sleep(wait)
                retries += 1
                _rate_limit(last_request_time)
                continue
            if r.status_code >= 500:
                if retries == 0:
                    log.warning("HTTP %d at %s — retry after 10s", r.status_code, url)
                    time.sleep(10)
                    retries += 1
                    _rate_limit(last_request_time)
                    continue
                else:
                    log.warning("HTTP %d after retry at %s — skipping", r.status_code, url)
                    return None
            r.raise_for_status()
            html = r.text
            break
        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            if retries == 0:
                log.warning("Connection error at %s: %s — retry", url, e)
                time.sleep(10)
                retries += 1
                _rate_limit(last_request_time)
                continue
            log.warning("Connection error at %s after retry: %s — skip", url, e)
            return None

    soup = BeautifulSoup(html, "lxml")
    warnings = []

    # Extract decision number
    decision_number = _extract_decision_number(soup)
    if not decision_number:
        # Fallback: extract from URL path
        url_path = url.split("/sr-lat/")[-1]
        # Try to reconstruct e.g. kzz-7542025 → Kzz 754/2025
        m = re.match(r"([a-z0-9-]+?)-(\d+)(\d{4})-", url_path)
        if m:
            reg_raw = m.group(1).replace("-", " ")
            decision_number = f"{reg_raw.title()} {m.group(2)}/{m.group(3)}"
        warnings.append("decision_number extracted from URL (h1 parse failed)")

    decision_id = _safe_id(decision_number, url)

    # Extract body text
    body_div = soup.find("div", class_="field-name-body")
    raw_text = body_div.get_text(separator="\n", strip=True) if body_div else ""
    if not raw_text:
        # Try field-item even
        body_div = soup.find("div", class_="field-item")
        raw_text = body_div.get_text(separator="\n", strip=True) if body_div else ""
        if raw_text:
            warnings.append("body from field-item fallback")

    # Trim navigation noise from start (page nav is often prepended)
    # Find the start of the actual decision text
    nav_end_markers = ["BeogradVrhovni", "godinaBeograd", "Beograd\n"]
    for marker in ["Republika Srbija\n", "REPUBLIKA SRBIJA\n"]:
        if marker in raw_text:
            raw_text = raw_text[raw_text.find(marker):]
            break

    # Extract court
    court = _extract_court(raw_text)

    # Extract date (prefer search hint, then body text)
    decision_date = date_hint
    if not decision_date:
        decision_date = _extract_date(raw_text[:500])

    # Registrant
    registrant = registrant_hint or _extract_registrant(decision_number)

    # Validation checks
    if not decision_number:
        warnings.append("MISSING: decision_number")
    if not court:
        warnings.append("MISSING: court")
    if len(raw_text) < 500:
        warnings.append(f"SHORT: raw_text only {len(raw_text)} chars")

    # Build relative path
    html_path = f"raw/{matter_slug}/{decision_id}.html"
    json_path = f"raw/{matter_slug}/{decision_id}.json"

    # Save HTML
    html_file = base_dir / "raw" / matter_slug / f"{decision_id}.html"
    html_file.parent.mkdir(parents=True, exist_ok=True)
    html_file.write_text(html, encoding="utf-8")

    # Build JSON
    record = {
        "decision_id": decision_id,
        "source_url": url,
        "court": court,
        "decision_number": decision_number,
        "decision_date": decision_date,
        "matter": matter_label,
        "registrant": registrant,
        "raw_text_length": len(raw_text),
        "raw_text": raw_text,
        "raw_html_path": html_path,
        "scraped_at": _now_iso(),
        "scraper_version": SCRAPER_VERSION,
        "parse_warnings": warnings,
    }

    # Save JSON
    json_file = base_dir / "raw" / matter_slug / f"{decision_id}.json"
    json_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    return record


def _rate_limit(last_request_time: list):
    """Ensure minimum CRAWL_DELAY between requests."""
    if last_request_time:
        elapsed = time.monotonic() - last_request_time[0]
        if elapsed < CRAWL_DELAY:
            time.sleep(CRAWL_DELAY - elapsed)
    last_request_time.clear()
    last_request_time.append(time.monotonic())


def run_scrape(
    base_dir: Path,
    dryrun: bool = False,
    dryrun_targets: list[dict] | None = None,
) -> dict:
    """
    Main scrape loop.
    dryrun=True: fetch only the specified dryrun_targets (5 decisions).
    dryrun=False: full stratified scrape.
    Returns stats dict.
    """
    stats = {
        "totals": {"requested": 0, "collected": 0, "partial": 0, "failed": 0},
        "by_matter": {},
        "decisions": [],
    }

    last_request_time = []

    with httpx.Client(
        headers={"User-Agent": UA},
        follow_redirects=True,
        timeout=30,
    ) as client:

        if dryrun and dryrun_targets:
            log.info("=== DRY-RUN MODE: %d decisions ===", len(dryrun_targets))
            dryrun_dir = base_dir / "raw" / "_dryrun"
            dryrun_dir.mkdir(parents=True, exist_ok=True)
            for target in dryrun_targets:
                log.info("Dry-run: %s — %s", target["matter"], target["url"])
                record = fetch_decision(
                    client,
                    target["url"],
                    "_dryrun",
                    target["matter"],
                    base_dir,
                    last_request_time,
                    registrant_hint=target.get("registrant", ""),
                    date_hint=target.get("date", ""),
                )
                if record:
                    # Also save to dryrun dir explicitly
                    did = record["decision_id"]
                    dr_html = (base_dir / "raw" / "_dryrun" / f"{did}.html")
                    dr_json = (base_dir / "raw" / "_dryrun" / f"{did}.json")
                    # Already saved to _dryrun by fetch_decision (matter_slug="_dryrun")
                    stats["totals"]["collected"] += 1
                    stats["decisions"].append({
                        "decision_id": did,
                        "matter": target["matter"],
                        "court": record["court"],
                        "decision_number": record["decision_number"],
                        "path": f"raw/_dryrun/{did}.json",
                        "warnings": record["parse_warnings"],
                    })
                    log.info(
                        "  OK: %s | court=%s | date=%s | len=%d | warnings=%s",
                        record["decision_number"],
                        record["court"],
                        record["decision_date"],
                        record["raw_text_length"],
                        record["parse_warnings"],
                    )
                else:
                    stats["totals"]["failed"] += 1
                    log.error("  FAILED: %s", target["url"])
            return stats

        # Full stratified scrape
        for matter in MATTERS:
            slug = matter["slug"]
            label = matter["label"]
            mid = matter["matter_id"]
            log.info("=== Matter: %s (id=%s) ===", label, mid)

            collected_ids = set()
            collected = 0
            partial = 0
            failed = 0
            t_start = time.monotonic()

            page = 0
            while collected < TARGET_PER_MATTER and page < MAX_PAGES:
                log.info("  Fetching search page %d for %s ...", page, label)
                search_soup = fetch_search_page(client, mid, page, last_request_time)
                if not search_soup:
                    log.warning("  Search page %d failed — skipping", page)
                    page += 1
                    continue

                result_stubs = extract_results(search_soup, label)
                if not result_stubs:
                    log.info("  No more results on page %d — stopping", page)
                    break

                log.info("  Got %d results on page %d", len(result_stubs), page)

                for stub in result_stubs:
                    if collected >= TARGET_PER_MATTER:
                        break

                    url = stub["url"]
                    # Dedup by URL
                    if url in collected_ids:
                        log.debug("  Skip duplicate: %s", url)
                        continue

                    stats["totals"]["requested"] += 1
                    log.info(
                        "  [%s %d/%d] %s — %s",
                        slug,
                        collected + 1,
                        TARGET_PER_MATTER,
                        stub.get("decision_title", ""),
                        url,
                    )

                    try:
                        record = fetch_decision(
                            client,
                            url,
                            slug,
                            label,
                            base_dir,
                            last_request_time,
                            registrant_hint=stub.get("registrant_from_search", ""),
                            date_hint=stub.get("date_from_search", ""),
                        )
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 403:
                            log.error("HARD STOP: HTTP 403 at %s", url)
                            # Save partial manifest and raise
                            _write_partial_manifest(base_dir, stats)
                            raise
                        record = None

                    if record is None:
                        failed += 1
                        log.warning("  FAILED: %s", url)
                        continue

                    collected_ids.add(url)

                    is_partial = bool(record.get("parse_warnings"))
                    if is_partial:
                        partial += 1
                    else:
                        pass

                    collected += 1
                    stats["totals"]["collected"] += 1
                    if is_partial:
                        stats["totals"]["partial"] += 1

                    stats["decisions"].append({
                        "decision_id": record["decision_id"],
                        "matter": label,
                        "court": record["court"],
                        "decision_number": record["decision_number"],
                        "decision_date": record.get("decision_date", ""),
                        "path": f"raw/{slug}/{record['decision_id']}.json",
                        "warnings": record["parse_warnings"],
                    })

                    # Progress checkpoint every 25
                    if collected % 25 == 0:
                        log.info(
                            "  CHECKPOINT: %s — %d collected, %d partial, %d failed",
                            label, collected, partial, failed,
                        )

                page += 1

            wall = time.monotonic() - t_start
            stats["by_matter"][slug] = {
                "label": label,
                "collected": collected,
                "partial": partial,
                "failed": failed,
                "wall_s": round(wall),
            }
            stats["totals"]["failed"] += failed
            log.info(
                "Matter %s done: %d collected, %d partial, %d failed in %ds",
                label, collected, partial, failed, round(wall),
            )

    return stats


def _write_partial_manifest(base_dir: Path, stats: dict):
    manifest = {
        "phase": "1.0",
        "status": "PARTIAL",
        "scraped_at": _now_iso(),
        "scraper_version": SCRAPER_VERSION,
        "branch": "phase1-sudska-praksa",
        "totals": stats["totals"],
        "by_matter": stats.get("by_matter", {}),
        "decisions": stats.get("decisions", []),
    }
    (base_dir / "manifest_partial.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Partial manifest saved.")


def write_manifest(base_dir: Path, stats: dict):
    manifest = {
        "phase": "1.0",
        "scraped_at": _now_iso(),
        "scraper_version": SCRAPER_VERSION,
        "branch": "phase1-sudska-praksa",
        "totals": stats["totals"],
        "by_matter": stats.get("by_matter", {}),
        "decisions": stats.get("decisions", []),
    }
    (base_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Manifest written: %d decisions", len(stats["decisions"]))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dryrun", "full"], default="full")
    parser.add_argument(
        "--base-dir",
        default=str(Path(__file__).parent),
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)

    if args.mode == "dryrun":
        # 5 decisions: 1 Krivična, 2 Građanska, 1 Upravna, 1 Zaštita prava
        # URLs collected from Phase B discovery
        DRYRUN_TARGETS = [
            {
                "url": "https://www.vrh.sud.rs/sr-lat/kzz-7542025-24121233",
                "matter": "Krivična",
                "registrant": "Kzz",
                "date": "2026-04-15",
            },
            {
                "url": "https://www.vrh.sud.rs/sr-lat/kzz-6952025-24121234",
                "matter": "Krivična",
                "registrant": "Kzz",
                "date": "2026-03-26",
            },
            {
                "url": "https://www.vrh.sud.rs/sr-lat/prev-1022025-24121235",
                "matter": "Građanska",
                "registrant": "Prev",
                "date": "",
            },
            {
                "url": "https://www.vrh.sud.rs/sr-lat/us-102025-24111236",
                "matter": "Upravna",
                "registrant": "Us",
                "date": "",
            },
            {
                "url": "https://www.vrh.sud.rs/sr-lat/rz1k-312026-24121237",
                "matter": "Zaštita prava",
                "registrant": "Rž1k",
                "date": "",
            },
        ]
        stats = run_scrape(base_dir, dryrun=True, dryrun_targets=DRYRUN_TARGETS)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        stats = run_scrape(base_dir, dryrun=False)
        write_manifest(base_dir, stats)
        total = stats["totals"]["collected"]
        print(f"\nSCRAPE COMPLETE: {total} decisions collected")
        sys.exit(0 if total >= 150 else 1)
