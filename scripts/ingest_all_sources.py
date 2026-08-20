#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vindex AI — Unified multi-source ingest
Sekvencijalno ingestuje sve lokalne JSON izvore u Pinecone sudska_praksa namespace.
Pokretanje: python scripts/ingest_all_sources.py
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent

SOURCES = [
    ("echr",                    ROOT / "data/echr/odluke",                    "ECHR odluke"),
    ("kzk",                     ROOT / "data/kzk/odluke",                     "KZK — Komisija za zaštitu konkurencije"),
    ("ustavni",                 ROOT / "data/ustavni/odluke",                 "Ustavni sud"),
    ("ravnopravnost",           ROOT / "data/ravnopravnost/odluke",           "Poverenik za zaštitu ravnopravnosti"),
    ("parlament",               ROOT / "data/parlament/odluke",               "Parlament — zakoni"),
    ("acas",                    ROOT / "data/acas/odluke",                    "ACAS"),
    ("mfin",                    ROOT / "data/mfin/odluke",                    "Ministarstvo finansija"),
    ("poverenik",               ROOT / "data/poverenik/odluke",               "Poverenik za informacije"),
    ("vks_prosirenje",          ROOT / "data/vks_prosirenje/odluke",          "VKS/AP/PAP/US proširenje — 34 kombinacija"),
    ("sudska_praksa_converted", ROOT / "data/sudska_praksa_converted/odluke", "Stara kolekcija — VKS/AS bilteni i raw odluke"),
    ("misljenja_converted",     ROOT / "data/misljenja_converted/odluke",     "Ministarstva — pravna mišljenja"),
    ("sudskapraksa_portal",     ROOT / "data/sudskapraksa_portal/odluke",     "sudskapraksa.sud.rs — 75,157 sudskih odluka"),
    ("as_ns_bilteni",           ROOT / "data/as_ns_bilteni/odluke",           "AS Novi Sad — 10 PDF biltena sudske prakse"),
    ("zastitnik",               ROOT / "data/zastitnik/odluke",               "Zaštitnik gradjana — godišnji izveštaji 2011-2025"),
    ("sudskapraksa_sud_converted", ROOT / "data/sudskapraksa_sud_converted/odluke", "sudskapraksa.sud.rs API odluke"),
    ("ombudsman_apv_converted",    ROOT / "data/ombudsman_apv_converted/odluke",    "Ombudsman APV — mišljenja i preporuke"),
    ("apelacioni_bilteni_converted", ROOT / "data/apelacioni_bilteni_converted/odluke", "Apelacioni sudovi — PDF bilteni"),
    # PRESKOCENI (duplikati bez id polja ili prazni tekst):
    # sudskapraksa_sud — duplikat sa sudskapraksa_sud_converted, nema id polje
    # ombudsman_apv — duplikat sa ombudsman_apv_converted, nema id polje
    # apelacioni_bilteni — duplikat sa apelacioni_bilteni_converted, nema id polje
    # kjn — 184/185 su [SKENIRAN_PDF_OCR_POTREBAN], bez teksta
]

INGEST_SCRIPT = ROOT / "scripts/ingest_sudskapraksa.py"

def run_source(key, odluke_dir, label):
    if not odluke_dir.exists():
        print(f"[SKIP] {label} — direktorijum ne postoji: {odluke_dir}")
        return
    files = list(odluke_dir.glob("*.json"))
    if not files:
        print(f"[SKIP] {label} — nema JSON fajlova")
        return

    print(f"\n{'='*60}")
    print(f"[START] {label} ({len(files)} fajlova)")
    print(f"{'='*60}")
    t0 = time.time()

    cmd = [sys.executable, str(INGEST_SCRIPT),
           "--odluke-dir", str(odluke_dir),
           "--resume"]

    result = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = round(time.time() - t0)
    status = "OK" if result.returncode == 0 else f"GREŠKA (exit {result.returncode})"
    print(f"[{status}] {label} — {elapsed}s")
    return result.returncode == 0

if __name__ == "__main__":
    print("=== VINDEX UNIFIED INGEST ===")
    print(f"Izvora: {len(SOURCES)}")

    results = {}
    for key, odluke_dir, label in SOURCES:
        ok = run_source(key, odluke_dir, label)
        results[key] = ok

    print("\n=== FINALNI IZVESTAJ ===")
    for key, ok in results.items():
        status = "OK" if ok else ("SKIP" if ok is None else "GRESKA")
        print(f"  [{status}] {key}")
    print("=== INGEST ZAVRSEN ===")
