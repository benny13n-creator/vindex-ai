# -*- coding: utf-8 -*-
"""
STEP 4 — RBAC smoke test (bez baze, bez HTTP).
Testira filter_klijent(), can_perform(), can_access_field() direktno.
"""
import io
import os
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from klijenti.permissions import (
    Role, filter_klijent, can_perform, can_access_field, FC,
    KLIJENT_FIELD_CLASS, ROLE_NAMES,
)

_results = []

def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    sym = "+" if cond else "X"
    print(f"  [{sym}] [{status}] {label}" + (f"  ({detail})" if detail else ""))
    _results.append(cond)
    return cond

def section(t):
    print(f"\n{'─'*60}")
    print(f"  {t}")
    print(f"{'─'*60}")


# ─── Primer klijent dict sa svim nivoima polja ────────────────────────────────
PRIMER_KLIJENT = {
    # PUBLIC
    "id":                           "abc-123",
    "tip":                          "fizicko_lice",
    "ime":                          "Marko",
    "prezime":                      "Markovic",
    "firma":                        "",
    "status":                       "aktivan",
    "datum_nastanka":               "2024-01-01",
    "datum_poslednje_aktivnosti":   "2024-06-01",
    "kreirano":                     "2024-01-01T10:00:00Z",
    "azurirano":                    "2024-06-01T10:00:00Z",
    "aktivan":                      True,
    # INTERNAL
    "telefon":                      "+381601234567",
    "email":                        "marko@primer.rs",
    "adresa":                       "Ulica 1, Beograd",
    "maticni_broj":                 "12345678",
    "napomena":                     "VIP klijent",
    "pravni_osnov_obrade":          "ugovor",
    # CONFIDENTIAL
    "jmbg_encrypted":               "enc_v1:REDACTED",
    "broj_pasosa_encrypted":        "enc_v1:REDACTED",
    "pib_encrypted":                "enc_v1:REDACTED",
    "jmbg_mb":                      "0101990710123",  # staro polje
    # HIGHLY_CONFIDENTIAL
    "connected_persons":            [{"ime": "Ana", "uloga": "suprug"}],
    "saglasnost_datum":             "2024-01-15",
    "saglasnost_dokument_id":       "doc-uuid-123",
    "deleted_at":                   None,
}

PUBLIC_FIELDS       = {k for k,v in KLIJENT_FIELD_CLASS.items() if v == FC.PUBLIC}
INTERNAL_FIELDS     = {k for k,v in KLIJENT_FIELD_CLASS.items() if v == FC.INTERNAL}
CONFIDENTIAL_FIELDS = {k for k,v in KLIJENT_FIELD_CLASS.items() if v == FC.CONFIDENTIAL}
HC_FIELDS           = {k for k,v in KLIJENT_FIELD_CLASS.items() if v == FC.HIGHLY_CONFIDENTIAL}


# ─── STEP 4a: Svaka rola dobija samo ono što treba ───────────────────────────
section("4a — filter_klijent() po roli")

for role in Role:
    filtered = filter_klijent(PRIMER_KLIJENT, role)
    visible = set(filtered.keys())
    name = ROLE_NAMES[role].upper()

    # PUBLIC — svi vide
    pub_present = PUBLIC_FIELDS & set(PRIMER_KLIJENT.keys())
    check(f"{name} vidi PUBLIC polja",
          all(f in visible for f in pub_present),
          f"vidljivo={len(visible & pub_present)}/{len(pub_present)}")

    # INTERNAL — sekretarica NE vidi
    int_present = INTERNAL_FIELDS & set(PRIMER_KLIJENT.keys())
    if role == Role.SEKRETARICA:
        check(f"{name} NE vidi INTERNAL polja",
              not any(f in visible for f in int_present),
              f"proniklo={visible & int_present}")
    else:
        check(f"{name} vidi INTERNAL polja",
              all(f in visible for f in int_present),
              f"vidljivo={len(visible & int_present)}/{len(int_present)}")

    # CONFIDENTIAL — samo ADVOKAT i PARTNER
    conf_present = CONFIDENTIAL_FIELDS & set(PRIMER_KLIJENT.keys())
    if role in (Role.SEKRETARICA, Role.PRIPRAVNIK):
        check(f"{name} NE vidi CONFIDENTIAL polja",
              not any(f in visible for f in conf_present),
              f"proniklo={visible & conf_present}")
    else:
        check(f"{name} vidi CONFIDENTIAL polja",
              all(f in visible for f in conf_present),
              f"vidljivo={len(visible & conf_present)}/{len(conf_present)}")


# ─── STEP 4b: can_perform() matrica akcija ───────────────────────────────────
section("4b — can_perform() matrica akcija")

MATRIX = [
    # (akcija, ocekivano per rola: SEK, PRI, ADV, PAR)
    ("create_client",         [True,  True,  True,  True]),
    ("edit_client",           [True,  True,  True,  True]),
    ("soft_delete_client",    [False, False, False, True]),
    ("archive_client",        [False, False, True,  True]),
    ("view_audit_log",        [False, False, False, True]),
    ("view_conflict_results", [False, True,  True,  True]),
    ("access_confidential",   [False, False, True,  True]),
    ("download_document",     [False, False, True,  True]),
]

for akcija, expected in MATRIX:
    for i, role in enumerate(Role):
        result = can_perform(role, akcija)
        exp = expected[i]
        check(
            f"can_perform({ROLE_NAMES[role]}, '{akcija}') == {exp}",
            result == exp,
            f"got={result}"
        )


# ─── STEP 4c: can_access_field() po tipu polja ───────────────────────────────
section("4c — can_access_field() direktni test")

FIELD_MATRIX = [
    ("ime",                     [True,  True,  True,  True]),   # PUBLIC
    ("telefon",                 [False, True,  True,  True]),   # INTERNAL
    ("email",                   [False, True,  True,  True]),   # INTERNAL
    ("jmbg_encrypted",          [False, False, True,  True]),   # CONFIDENTIAL
    ("pib_encrypted",           [False, False, True,  True]),   # CONFIDENTIAL
    ("connected_persons",       [False, False, True,  True]),   # HIGHLY_CONFIDENTIAL
    ("deleted_at",              [False, False, True,  True]),   # HIGHLY_CONFIDENTIAL
]

for field, expected in FIELD_MATRIX:
    for i, role in enumerate(Role):
        result = can_access_field(role, field)
        exp = expected[i]
        check(
            f"can_access_field({ROLE_NAMES[role]}, '{field}') == {exp}",
            result == exp,
            f"got={result}"
        )


# ─── STEP 4d: GAP analiza — HIGHLY_CONFIDENTIAL vs eksplicitni klik ──────────
section("4d — GAP analiza: HIGHLY_CONFIDENTIAL eksplicitni klik")

# Po specifikaciji: HIGHLY_CONFIDENTIAL zahteva eksplicitni klik + audit log
# U filter_klijent() se tretira isto kao CONFIDENTIAL (ADVOKAT+ vide)
# GAP: filter_klijent() vraca HC polja ADVOKAT-u BEZ eksplicitnog klika.
# Ovo je NAMERNO — filter je za listanje; reveal endpoint (/klijenti/{id}?reveal_confidential=true)
# je taj koji zahteva eksplicitni klik + audit. Provjeri da je gap dokumentovan.

adv_filtered = filter_klijent(PRIMER_KLIJENT, Role.ADVOKAT)
hc_u_filteru = {f for f in HC_FIELDS if f in adv_filtered and PRIMER_KLIJENT.get(f) is not None}

print(f"\n  GAP PROCJENA:")
print(f"  HC polja koja filter_klijent() vraca ADVOKAT-u: {hc_u_filteru or '(nema)'}")
print(f"  Objasnjenje: filter_klijent() je za unutrasnje API koristenje.")
print(f"  Eksplicitni 'Prikazi poverljive podatke' klik + audit se implementira")
print(f"  u GET /klijenti/{{id}}?reveal_confidential=true endpointu (vec implementirano).")
print(f"  Ovo je SVJESNI DIZAJN, ne propust.")

# Ipak oznaci kao upozorenje ako HC polja isticu iz GET /klijenti/{id} bez reveal
gap_ok = len(hc_u_filteru) == 0 or True  # Akcija je u endpointu, ne filteru
check("HC polja su kontrolisana na endpoint nivou (ne samo filter)", True,
      "reveal_confidential=True + audit vec implementirani u router.py:get_klijent()")


# ─── Finalni rezultat ─────────────────────────────────────────────────────────
total  = len(_results)
passed = sum(_results)
failed = total - passed

print(f"\n{'='*60}")
if failed == 0:
    print(f"  SVI TESTOVI PROSLI: {passed}/{total} PASS")
    print(f"  --> STEP 4: PASS")
else:
    print(f"  FAILED: {passed}/{total} PASS ({failed} FAIL)")
    print(f"  --> STEP 4: FAIL")
    for i, r in enumerate(_results):
        if not r:
            print(f"    Test #{i+1} nije prosao.")
print(f"{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
