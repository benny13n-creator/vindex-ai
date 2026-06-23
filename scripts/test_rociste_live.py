#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Live test for Ročišta + Kalendar endpoints.
Run AFTER migrations/005_rocista.sql is applied in Supabase.

Usage:
    python scripts/test_rociste_live.py --email YOUR_EMAIL --password YOUR_PASSWORD
    python scripts/test_rociste_live.py --token YOUR_JWT_TOKEN
"""
import argparse
import json
import sys
from datetime import date, timedelta

import requests

BASE_URL = "https://vindex-ai.onrender.com"

DATUM_TEST = (date.today() + timedelta(days=5)).isoformat()
SUB_TEST   = "Osnovni sud u Beogradu"
VREME_TEST = "10:00"

def _login(email: str, password: str) -> str:
    import os; from dotenv import load_dotenv; load_dotenv()
    from supabase import create_client
    supa = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    r = supa.auth.sign_in_with_password({"email": email, "password": password})
    token = r.session.access_token
    print(f"[AUTH] Login OK, token: {token[:30]}...")
    return token


def _hdr(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def run(token: str):
    print(f"\n{'='*60}")
    print(f"BASE_URL: {BASE_URL}")
    print(f"Test datum: {DATUM_TEST}")
    print(f"{'='*60}\n")

    # ── 1. Nađi predmet "Naknada štete zbog otkaza..." ───────────────────────
    r = requests.get(f"{BASE_URL}/api/predmeti", headers=_hdr(token), timeout=15)
    if r.status_code != 200:
        print(f"[FAIL] GET /api/predmeti → {r.status_code}: {r.text[:200]}")
        sys.exit(1)

    predmeti = r.json().get("predmeti", [])
    print(f"[OK] GET /api/predmeti → {len(predmeti)} predmeta")

    predmet_id = None
    for p in predmeti:
        naziv = (p.get("naziv") or "").lower()
        if "naknada" in naziv or "otkaz" in naziv:
            predmet_id = p["id"]
            print(f"     ✓ Pronađen: '{p['naziv']}' (id={predmet_id[:8]}...)")
            break

    if not predmet_id:
        # Uzmi prvi dostupni predmet
        if predmeti:
            predmet_id = predmeti[0]["id"]
            print(f"     ⚠ 'Naknada štete' nije pronađen — koristim: '{predmeti[0].get('naziv','')}' (id={predmet_id[:8]}...)")
        else:
            print("[FAIL] Nema predmeta. Kreirajte bar jedan predmet pre testa.")
            sys.exit(1)

    # ── 2. Kreiraj test ročište ───────────────────────────────────────────────
    payload = {
        "predmet_id":  predmet_id,
        "sud":         SUB_TEST,
        "datum":       DATUM_TEST,
        "vreme":       VREME_TEST,
        "napomena":    "Vindex test ročište — može se obrisati",
    }
    r = requests.post(f"{BASE_URL}/api/rocista", headers=_hdr(token), json=payload, timeout=15)
    if r.status_code not in (200, 201):
        print(f"[FAIL] POST /api/rocista → {r.status_code}: {r.text[:300]}")
        sys.exit(1)

    data = r.json()
    rociste_id = data["rociste"]["id"]
    print(f"\n[OK] POST /api/rocista → 201 Created")
    print(json.dumps(data["rociste"], ensure_ascii=False, indent=2))

    # ── 3. GET /api/kalendar/pregled ──────────────────────────────────────────
    r = requests.get(f"{BASE_URL}/api/kalendar/pregled", headers=_hdr(token), timeout=15)
    if r.status_code != 200:
        print(f"\n[FAIL] GET /api/kalendar/pregled → {r.status_code}: {r.text[:300]}")
        sys.exit(1)

    kal = r.json()
    eventi = kal.get("dogadjaji", [])
    print(f"\n[OK] GET /api/kalendar/pregled → {kal['ukupno']} događaja ({kal['od']} → {kal['do']})")

    found = [e for e in eventi if e.get("detalji", {}).get("id") == rociste_id]
    if found:
        print(f"\n✅ Test ročište PRONAĐENO u kalendaru:")
        print(json.dumps(found[0], ensure_ascii=False, indent=2))
    else:
        print(f"\n[FAIL] Test ročište (id={rociste_id[:8]}...) NIJE pronađeno u kalendaru!")
        print(f"Svi eventi: {json.dumps(eventi, ensure_ascii=False, indent=2)}")
        # Cleanup
        requests.delete(f"{BASE_URL}/api/rocista/{rociste_id}", headers=_hdr(token), timeout=10)
        sys.exit(1)

    # Verify tip
    tip = found[0].get("tip")
    assert tip == "rociste", f"Očekivan tip='rociste', dobijen tip='{tip}'"
    assert found[0].get("datum") == DATUM_TEST
    assert found[0].get("vreme") == VREME_TEST

    print(f"\n✅ tip='{tip}' ✅ datum={DATUM_TEST} ✅ vreme={VREME_TEST}")

    # ── 4. Cleanup — obriši test ročište ──────────────────────────────────────
    r = requests.delete(f"{BASE_URL}/api/rocista/{rociste_id}", headers=_hdr(token), timeout=10)
    if r.status_code == 200:
        print(f"\n[CLEANUP] Test ročište obrisano (id={rociste_id[:8]}...)")
    else:
        print(f"\n[WARN] Cleanup nije uspeo: {r.status_code}")

    print(f"\n{'='*60}")
    print("✅ SVI TESTOVI PROŠLI — Ročišta + Kalendar endpoint RADI")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email",    default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--token",    default="")
    args = parser.parse_args()

    if args.token:
        run(args.token)
    elif args.email and args.password:
        t = _login(args.email, args.password)
        run(t)
    else:
        print("Koristite: --token JWT ili --email EMAIL --password PASS")
        sys.exit(1)
