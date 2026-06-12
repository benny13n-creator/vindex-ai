#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script za POST /api/nacrti/checklist (Faza 1).
Direktno poziva nacrti/checklist_engine.py bez HTTP/auth.
"""

import sys
import os
import json

# Force UTF-8 output na Windows konzoli
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nacrti.checklist_config import SVI_TIPOVI, get_config
from nacrti.checklist_engine import analiziraj_checklist

TIP_PODNESKA = "tuzba"
CINJENICE = (
    "Klijent je zaposlen kod poslodavca DOO Primer od 2020. godine na poziciji magacioner. "
    "Poslodavac mu nije isplatio zaradu za poslednja tri meseca. "
    "Klijent je vise puta usmeno trazio isplatu, bez rezultata. "
    "Radni odnos je i dalje aktivan."
)

print("=" * 62)
print("TEST: POST /api/nacrti/checklist -- Faza 1")
print("=" * 62)
print(f"Ulazni tip : {TIP_PODNESKA!r}")
print(f"Cinjenice  : {CINJENICE[:75]}...")
print()

# Pokusaj sa originalnim tipom -- "tuzba" nije validan kljuc
efektivni_tip = TIP_PODNESKA
try:
    get_config(TIP_PODNESKA)
except KeyError:
    print(f"[!] Tip {TIP_PODNESKA!r} ne postoji u konfiguraciji.")
    print(f"    Dozvoljeni tipovi: {SVI_TIPOVI}")
    efektivni_tip = "tuzba_radni_spor"
    print(f"    -> Auto-select: {efektivni_tip!r} (najbliži match za opisani scenario)\n")

print(f"Pozivam analiziraj_checklist({efektivni_tip!r}, cinjenice)...")
print()

rezultat = analiziraj_checklist(efektivni_tip, CINJENICE)

# -- Pun JSON -----------------------------------------------------------------
print("-" * 62)
print("PUNI JSON ODGOVOR:")
print("-" * 62)
print(json.dumps(rezultat, ensure_ascii=False, indent=2))
print()

# -- Provere ------------------------------------------------------------------
print("-" * 62)
print("PROVERE:")
print("-" * 62)

nedostajuci_svi   = rezultat.get("nedostajuci_svi", [])
svi_elementi      = rezultat.get("elementi", [])
nedostajuci_elems = [e for e in svi_elementi if not e["pokriven"]]
pokriveni_elems   = [e for e in svi_elementi if  e["pokriven"]]

# Provera 1: nedostaje element za "iznos/vrednost"?
iznos_kw = ["iznos", "vrednost", "potrazi", "potraži", "naknada"]
iznos_nedostaju = [
    e for e in nedostajuci_elems
    if any(kw in e["naziv"].lower() for kw in iznos_kw)
]

print("1. Nedostaje element vezan za 'vrednost spora' / 'iznos potrazivanja'?")
if iznos_nedostaju:
    for e in iznos_nedostaju:
        print(f"   [OK] DA -- '{e['naziv']}' (kriticnost: {e['kriticnost']})")
else:
    print("   [X]  NE -- element nije pronaden u nedostajucima")

# Provera 2: kriticnost "visoka" za taj element?
iznos_visoka = any(e["kriticnost"] == "visoka" for e in iznos_nedostaju)
print("2. Taj element ima kriticnost 'visoka'?")
if iznos_nedostaju:
    if iznos_visoka:
        print("   [OK] DA")
    else:
        krit = iznos_nedostaju[0]["kriticnost"]
        print(f"   [!]  NE -- kriticnost je {krit!r} (nije 'visoka')")
else:
    print("   [--] N/A (element nije pronaden)")

# Provera 3: blokira_nastavak == True?
blokira = rezultat.get("blokira_nastavak", False)
print("3. blokira_nastavak == True?")
if blokira:
    print("   [OK] DA")
    visoki_koji_nedostaju = [e for e in nedostajuci_elems if e["kriticnost"] == "visoka"]
    for e in visoki_koji_nedostaju:
        print(f"        -> blokirajuci: '{e['naziv']}'")
else:
    print("   [X]  NE -- nema blokirajucih nedostajucih elemenata")

# Provera 4: prepoznaje radni odnos / poslodavca?
radni_kw = ["stranke", "identitet", "radni", "datum", "poslodavac", "zasniv"]
pokriveni_radni = [
    e for e in pokriveni_elems
    if any(kw in e["naziv"].lower() for kw in radni_kw)
]
print("4. Prepoznaje radni odnos / poslodavca (pokriveni elementi)?")
if pokriveni_radni:
    print("   [OK] DA:")
    for e in pokriveni_radni:
        print(f"        -> '{e['naziv']}'")
else:
    all_pokriveni = [e["naziv"] for e in pokriveni_elems]
    if all_pokriveni:
        print(f"   [!]  NE direktno, ali ostali pokriveni: {all_pokriveni}")
    else:
        print("   [X]  NE -- nijedan element nije prepoznat kao pokriven")

# -- Sazetak ------------------------------------------------------------------
print()
print("-" * 62)
nedostajuci_kriticni = rezultat.get("nedostajuci_kriticni", [])
print("SAZETAK:")
print(f"  Tip                : {rezultat['naziv_tipa']}")
print(f"  Pokrivenost        : {rezultat['procenat_pokrivenosti']}%")
print(f"  Nedostajuci ukupno : {len(nedostajuci_svi)}")
print(f"  Nedostajuci krit.  : {len(nedostajuci_kriticni)}")
if nedostajuci_kriticni:
    for n in nedostajuci_kriticni:
        print(f"    [!] {n}")
print("-" * 62)
