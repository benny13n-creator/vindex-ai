# -*- coding: utf-8 -*-
"""
STEP 1 — Round-trip test za field-level enkripciju.
Pokreće se lokalno, ne potrebna baza ni API ključ.
Generiše privremeni test ključ — NE dotiče .env niti produkcijske podatke.
"""
import io
import os
import sys
import base64
import secrets

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Postavi privremeni test ključ (samo za ovu sesiju, nikad u .env) ────────
_TEST_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
os.environ["FIELD_ENCRYPTION_KEY"] = _TEST_KEY

# Dodaj root u sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.crypto import encrypt_field, decrypt_field, is_encrypted

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_results = []


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    marker = "✓" if condition else "✗"
    print(f"  {marker} [{status}] {label}" + (f"  ({detail})" if detail else ""))
    _results.append(condition)
    return condition


def section(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ─── STEP 1a: Realni srpski formati ──────────────────────────────────────────
section("1a — Realni formati (JMBG, pasoš, PIB)")

TEST_CASES = [
    ("JMBG",     "0101990710123"),
    ("Pasos",    "P1234567"),
    ("PIB",      "123456789"),
    ("JMBG+razmak", "010199 0710123"),  # typo sa razmakom
    ("Spec.chars",  "AB-12/34 (test)"),
    ("Unicode",     "Марко Марковић"),  # UTF-8 edge case
]

for name, plaintext in TEST_CASES:
    enc = encrypt_field(plaintext)
    dec = decrypt_field(enc)
    check(
        f"Round-trip {name}: '{plaintext[:20]}'",
        dec == plaintext,
        f"enc prefix={enc[:12]}… dec='{dec[:20]}'"
    )

# ─── STEP 1b: Edge case — prazan string ──────────────────────────────────────
section("1b — Edge cases")

enc_empty = encrypt_field("")
check("Prazan string → vraća ''", enc_empty == "", f"got: {repr(enc_empty)}")

dec_empty = decrypt_field("")
check("decrypt('') → vraća ''", dec_empty == "", f"got: {repr(dec_empty)}")

# Plaintext koji nije enkriptovan (stari unos bez prefix-a) → vraća as-is
old_plaintext = "stari_plaintext_bez_prefixa"
dec_old = decrypt_field(old_plaintext)
check("Stari plaintext (bez enc_v1: prefix) → as-is", dec_old == old_plaintext, f"got: {repr(dec_old)}")

# ─── STEP 1c: Nonce randomizacija — isti input → RAZLIČIT ciphertext ─────────
section("1c — Nonce randomizacija (sigurnosni zahtev)")

REPEAT_INPUT = "0101990710123"
ROUNDS = 10
enc_set = set()
for _ in range(ROUNDS):
    enc_set.add(encrypt_field(REPEAT_INPUT))

check(
    f"Isti JMBG × {ROUNDS} → svi različiti ciphertexti",
    len(enc_set) == ROUNDS,
    f"Unique: {len(enc_set)}/{ROUNDS}"
)

# Svi se dekriptuju na isti original
dec_all_ok = all(decrypt_field(ct) == REPEAT_INPUT for ct in enc_set)
check("Svi ciphertexti se dekriptuju na original", dec_all_ok)

# ─── STEP 1d: is_encrypted detekcija ─────────────────────────────────────────
section("1d — is_encrypted() detekcija")

enc_sample = encrypt_field("test")
check("is_encrypted(encrypt_field('test')) → True", is_encrypted(enc_sample))
check("is_encrypted('plaintext') → False", not is_encrypted("plaintext"))
check("is_encrypted('') → False", not is_encrypted(""))

# ─── STEP 1e: Pogrešan ključ → vraća sentinel, ne crasha ─────────────────────
section("1e — Pogrešan ključ → graceful degradacija")

enc_with_key1 = encrypt_field("tajni_jmbg")

# Zameni ključ drugim
os.environ["FIELD_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

dec_wrong_key = decrypt_field(enc_with_key1)
check(
    "Decrypt sa pogrešnim ključem → sentinel '[GREŠKA DEKRIPTOVANJA]'",
    dec_wrong_key == "[GREŠKA DEKRIPTOVANJA]",
    f"got: {repr(dec_wrong_key)}"
)
# Vrati originalni ključ za dalje testove
os.environ["FIELD_ENCRYPTION_KEY"] = _TEST_KEY

# ─── Finalni rezultat ─────────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
failed = total - passed

print(f"\n{'═'*55}")
if failed == 0:
    print(f"  \033[92mSVI TESTOVI PROŠLI: {passed}/{total} PASS\033[0m")
    print(f"  → STEP 1: PASS — Enkripcija radi ispravno.")
else:
    print(f"  \033[91mFAILED: {passed}/{total} PASS ({failed} FAIL)\033[0m")
    print(f"  → STEP 1: FAIL — Provjeri gornje greške pre deploy-a.")
print(f"{'═'*55}\n")

sys.exit(0 if failed == 0 else 1)
