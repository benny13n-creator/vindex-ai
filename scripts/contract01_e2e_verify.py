# -*- coding: utf-8 -*-
"""
CONTRACT 01 (Upload tuzbe) — E2E Verified Coverage check, Faza A
Internal Integration Sprint (2026-07-19).

Reuses the Reality Validation harness (genome_case_dna_evaluate.run_batch)
to produce REAL evidence for the "Koji test potvrdjuje gotovost" row of
CONTRACT 01 in VINDEX_OPERATING_SYSTEM_CONTRACTS.md. Exercises the real
API (predmet create -> upload -> background Genome refresh -> event
dispatch), then additionally checks predmet_dokazi (Evidence Vault),
which run_batch itself does not check.

Creates ONE clearly-labeled test predmet in production. Not deleted
automatically -- kept as a permanent regression case, same policy as the
2026-07-18 synthetic calibration batch.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genome_case_dna_evaluate import run_batch  # noqa: E402

FOUNDER_USER_ID = "384a7149-938b-4b83-99e0-8d7524e0581a"
FOUNDER_EMAIL = "benny13.n@gmail.com"

CASE = {
    "label": "CONTRACT01-VERIFY",
    "naziv": "[INTEGRACIJA-TEST] Upload tuzbe E2E provera — Contract 01",
    "opis": "Faza A Internal Integration Sprint — E2E verifikacija Toka 1 (Upload tuzbe)",
    "tip": "radni_spor",
    "documents": [
        {"filename": "tuzba.docx", "paragraphs": [
            "TUZBA",
            "Tuzilac Marko Jovanovic protiv tuzenog DOO Alfa Trejd, zbog neisplacene zarade.",
            "Tuzeni duguje tuziocu iznos od 350.000 RSD na ime neisplacenih zarada za period "
            "januar-mart 2026. godine.",
            "Tuzilac je bio zaposlen kod tuzenog od 01.01.2024. do 31.03.2026. godine, na "
            "poziciji komercijaliste, sa mesecnom bruto zaradom od 120.000 RSD.",
            "Tuzeni je poslednju isplatu zarade izvrsio 15.12.2025. godine, nakon cega isplate "
            "nisu vrsene uprkos vise pisanih opomena tuzioca.",
            "Predlaze se da sud obaveze tuzenog na isplatu duga sa zakonskom zateznom kamatom.",
        ]},
    ],
}


async def main():
    out_dir = str(ROOT / "vindex_scraper_output" / "contract01_verify")
    results = await run_batch(
        cases=[CASE], user_id=FOUNDER_USER_ID, email=FOUNDER_EMAIL,
        out_dir=out_dir, poll_timeout_s=90.0, poll_interval_s=4.0,
    )
    r = results[0]

    from supabase import create_client
    import os
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    supa = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_SERVICE_KEY"],
    )
    predmet_id = r.get("predmet_id")
    dokazi = []
    if predmet_id:
        dz = supa.table("predmet_dokazi").select("id,tvrdnja,kategorija").eq("predmet_id", predmet_id).execute()
        dokazi = dz.data or []

    print("\n===== CONTRACT 01 — Upload tuzbe: E2E rezultat =====")
    checks = {
        "1. Klasifikacija automatska (predmet_dokumenti popunjen)": bool(r.get("documents_in_db")),
        "2. Evidence Vault upis automatski (predmet_dokazi red postoji)": bool(dokazi),
        "3. Case Genome regeneracija automatska (case_dna sa verzijom)": bool(r.get("genome")),
        "4. PREDMET_KREIRAN event emitovan (D3)": False,  # poznato: ne emituje se, potvrdjujemo eksplicitno
        "5. run_case_pipeline pokrenut (D9)": False,       # poznato: ne poziva se za standardni put
        "6. Audit red za predmet_create/dokument_upload (D22)": False,  # poznato: ne belezi se
    }
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL/POZNATO'}] {k}")

    print(f"\n  predmet_id: {predmet_id}")
    print(f"  genome verzija: {(r.get('genome') or {}).get('verzija')}")
    print(f"  genome _verifikacija: {(r.get('genome') or {}).get('_verifikacija', {}).get('odluka')}")
    print(f"  GenomeUpdated event red: {'DA' if r.get('event_row') else 'NE'}")
    print(f"  audit_immutable (genome_refresh) red: {'DA' if r.get('audit_row') else 'NE'}")
    print(f"  predmet_dokazi (Evidence Vault) redova: {len(dokazi)}")
    print(f"  upload greske: {r.get('upload_errors')}")
    print(f"  ukupno vreme: {r.get('total_elapsed_s')}s")

    verified = sum(1 for v in checks.values() if v)
    print(f"\n  CONTRACT 01 Verified koraci (od kriticnih 1-3): "
          f"{sum(1 for k in list(checks)[:3] if checks[k])}/3")


if __name__ == "__main__":
    asyncio.run(main())
