# -*- coding: utf-8 -*-
"""
STEP 3 — Migracija plaintext jmbg_mb → jmbg_encrypted (AES-256-GCM).

UPUTSTVO ZA POKRETANJE:
  1. Postavi FIELD_ENCRYPTION_KEY u .env (32-byte base64url ključ)
  2. Pokreni: python scripts/migrate_jmbg_encrypt.py --dry-run   (samo pregled, bez upisa)
  3. Pokreni: python scripts/migrate_jmbg_encrypt.py             (pravi upis)
  4. Ručno verifikuj nekoliko redova: python scripts/migrate_jmbg_encrypt.py --verify
  5. TEK POSLE verifikacije: pokreni DROP COLUMN jmbg_mb (vidi dno fajla)

NIKAD NE POKRETAJ OVAJ SKRIPT BEZ --dry-run PRVO.
NIKAD NE RADI DROP COLUMN dok ne proveris svaki red.
"""
import io
import os
import sys
import argparse
import asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─── Setup puta ──────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(ROOT) / ".env")

# ─── Provjera da su env varijable postavljene PRIJE importa crypto ────────────
FIELD_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "").strip()
if not FIELD_KEY:
    print("BLOCKER: FIELD_ENCRYPTION_KEY nije postavljen u .env!")
    print("Generisite ga komandom:")
    print('  python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"')
    print("i dodajte u Render dashboard + .env fajl.")
    sys.exit(1)

SUPA_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPA_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
if not SUPA_URL or not SUPA_KEY:
    print("BLOCKER: SUPABASE_URL i/ili SUPABASE_SERVICE_KEY nisu postavljeni!")
    sys.exit(1)

from security.crypto import encrypt_field, decrypt_field, is_encrypted
from supabase import create_client


def migrate(dry_run: bool = True, verify_only: bool = False):
    supa = create_client(SUPA_URL, SUPA_KEY)

    # ─── Dohvati sve redove sa jmbg_mb poljem ────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Migracija jmbg_mb -> jmbg_encrypted")
    print(f"  Mod: {'DRY RUN (bez upisa)' if dry_run else 'PRODUKCIJA (pravi upis)'}")
    print(f"{'='*60}\n")

    # Provjeri postoji li kolona jmbg_mb
    try:
        res = supa.table("klijenti").select("id, jmbg_mb, jmbg_encrypted").limit(1).execute()
    except Exception as e:
        print(f"  GRESKA: Nije moguce pristupiti tabeli klijenti: {e}")
        print("  (Moguce je da jmbg_mb kolona vec ne postoji — migiracija nije potrebna)")
        sys.exit(0)

    # Dohvati sve redove
    all_res = supa.table("klijenti").select("id, jmbg_mb, jmbg_encrypted").execute()
    redovi = all_res.data or []
    print(f"  Ukupno redova u klijenti: {len(redovi)}")

    # Kategorizuj
    sa_plaintext    = [r for r in redovi if r.get("jmbg_mb")]
    vec_enkriptovani = [r for r in redovi if r.get("jmbg_encrypted") and is_encrypted(r["jmbg_encrypted"])]
    prazni          = [r for r in redovi if not r.get("jmbg_mb") and not r.get("jmbg_encrypted")]

    print(f"  - Sa plaintext jmbg_mb (treba migrirati): {len(sa_plaintext)}")
    print(f"  - Vec enkriptovani jmbg_encrypted:        {len(vec_enkriptovani)}")
    print(f"  - Bez JMBG podataka (null/prazan):         {len(prazni)}")

    if verify_only:
        print(f"\n  --- VERIFIKACIJA ({len(vec_enkriptovani)} enkriptovanih redova) ---")
        greske = 0
        for r in vec_enkriptovani:
            dec = decrypt_field(r["jmbg_encrypted"])
            if dec == "[GREŠKA DEKRIPTOVANJA]":
                print(f"  FAIL  id={r['id'][:8]}... decrypt greska!")
                greske += 1
            else:
                print(f"  PASS  id={r['id'][:8]}... decrypt OK (len={len(dec)})")
        print(f"\n  Verifikacija: {len(vec_enkriptovani)-greske}/{len(vec_enkriptovani)} OK, {greske} gresaka")
        if greske == 0 and len(vec_enkriptovani) > 0:
            print("\n  MOZETE POKRENUTI DROP COLUMN jmbg_mb SQL:")
            print("  ALTER TABLE klijenti DROP COLUMN IF EXISTS jmbg_mb;")
        return

    if not sa_plaintext:
        print("\n  Nema redova za migraciju. Sve je azurirano ili prazno.")
        return

    # ─── Migracija ───────────────────────────────────────────────────────────
    print(f"\n  Obrada {len(sa_plaintext)} redova...")
    uspesno = 0
    failovalo = 0

    for r in sa_plaintext:
        rid = r["id"]
        jmbg_plain = r["jmbg_mb"]

        # Ne enkriptuj ako vec ima enkriptovanu vrednost
        if r.get("jmbg_encrypted") and is_encrypted(r["jmbg_encrypted"]):
            print(f"  SKIP  id={rid[:8]}... (vec enkriptovan)")
            continue

        try:
            enc = encrypt_field(jmbg_plain)
            # Verifikuj round-trip pre upisa
            dec_check = decrypt_field(enc)
            if dec_check != jmbg_plain:
                raise ValueError(f"Round-trip greska: '{jmbg_plain}' != '{dec_check}'")

            if dry_run:
                print(f"  DRY   id={rid[:8]}... jmbg_mb='{jmbg_plain[:4]}...' -> enc={enc[:16]}... [OK]")
            else:
                supa.table("klijenti").update({
                    "jmbg_encrypted": enc
                    # jmbg_mb se NE brise ovde — DROP COLUMN ide tek posle verifikacije
                }).eq("id", rid).execute()
                print(f"  DONE  id={rid[:8]}... encrypted OK")
            uspesno += 1

        except Exception as e:
            print(f"  FAIL  id={rid[:8]}... GRESKA: {e}")
            failovalo += 1

    print(f"\n{'='*60}")
    print(f"  Rezultat: {uspesno} uspesno, {failovalo} failovalo, {len(sa_plaintext)} ukupno")
    if dry_run:
        print("  Ovo je bio DRY RUN — nista nije upisano u bazu.")
        print("  Pokrenite bez --dry-run za pravi upis.")
    elif failovalo == 0:
        print("\n  SLEDECI KORACI:")
        print("  1. python scripts/migrate_jmbg_encrypt.py --verify")
        print("  2. Ako sve OK: ALTER TABLE klijenti DROP COLUMN IF EXISTS jmbg_mb;")
    else:
        print(f"\n  UPOZORENJE: {failovalo} redova nije migrirano! Provjeri greske gore.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Samo prikaz, bez upisa (default: True)")
    parser.add_argument("--run",     action="store_true",
                        help="Pravi upis u bazu (bez ovoga samo dry-run)")
    parser.add_argument("--verify",  action="store_true",
                        help="Verifikuje vec enkriptovane redove")
    args = parser.parse_args()

    dry = not args.run
    migrate(dry_run=dry, verify_only=args.verify)
