# -*- coding: utf-8 -*-
"""
PRIORITY 1 — Testovi za fail-fast startup validaciju FIELD_ENCRYPTION_KEY.

Testira sve scenarije bez prave baze — samo env var manipulacija.
"""
import io, os, sys, base64, secrets, subprocess, textwrap
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_results = []

def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    sym = "+" if cond else "X"
    print(f"  [{sym}] [{status}] {label}" + (f"  -- {detail}" if detail else ""))
    _results.append((label, cond))
    return cond

def section(t):
    print(f"\n{'─'*60}")
    print(f"  {t}")
    print(f"{'─'*60}")


# ─── 1a: validate_field_encryption_key() direktni testovi ────────────────────
section("1a — validate_field_encryption_key() direktno")

# Pokrećemo u subprocesima jer funkcija poziva sys.exit() — ne možemo je testirati
# u istom procesu bez mockanja.

def run_validate(env_value: str | None) -> tuple[int, str]:
    """Pokretanje validate_field_encryption_key() u subprocesu."""
    script = textwrap.dedent(f"""
        import sys, os, io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        sys.path.insert(0, {repr(ROOT)})
        {'os.environ["FIELD_ENCRYPTION_KEY"] = ' + repr(env_value) if env_value is not None else 'os.environ.pop("FIELD_ENCRYPTION_KEY", None)'}
        from security.crypto import validate_field_encryption_key
        validate_field_encryption_key()
        print("VALIDATION_PASSED")
    """)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script],
        capture_output=True, text=True, timeout=10, encoding="utf-8"
    )
    output = result.stdout + result.stderr
    return result.returncode, output


# Test 1: Validan kljuc → exit 0, nema abort poruke
valid_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
rc, out = run_validate(valid_key)
check("Validan kljuc (32B) → exit 0", rc == 0, f"rc={rc}")
check("Validan kljuc → 'VALIDATION_PASSED' u output", "VALIDATION_PASSED" in out, out[:80])

# Test 2: Prazan string → exit 1 + abort poruka
rc, out = run_validate("")
check("Prazan kljuc → exit 1", rc == 1, f"rc={rc}")
check("Prazan kljuc → abort poruka u output", "STARTUP ABORTED" in out or "missing" in out.lower(), out[:120])

# Test 3: None / unset → exit 1
rc, out = run_validate(None)
check("Unset kljuc → exit 1", rc == 1, f"rc={rc}")
check("Unset kljuc → abort poruka", "STARTUP ABORTED" in out or "nije postavljen" in out, out[:120])

# Test 4: Nije base64url → exit 1
rc, out = run_validate("ovo_nije_base64!!!###")
check("Nevalidan base64url → exit 1", rc == 1, f"rc={rc}")
check("Nevalidan base64url → abort poruka", "STARTUP ABORTED" in out or "base64" in out.lower(), out[:120])

# Test 5: Prekratak kljuc (16 bajta = 128-bit, premalo) → exit 1
short_key = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode()
rc, out = run_validate(short_key)
check("Kljuc 16B (premalo) → exit 1", rc == 1, f"rc={rc}")
check("Kljuc 16B → abort poruka o duzini", "STARTUP ABORTED" in out or "bajta" in out, out[:120])

# Test 6: Tacno 32 bajta → exit 0
exact_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
rc, out = run_validate(exact_key)
check("Kljuc tacno 32B → exit 0", rc == 0, f"rc={rc}")

# Test 7: 64 bajta (veci od potrebnog) → exit 0 (koristi prvih 32)
big_key = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode()
rc, out = run_validate(big_key)
check("Kljuc 64B → exit 0 (koristi prvih 32B)", rc == 0, f"rc={rc}")

# ─── 1b: _get_field_key() greske (exception, ne sys.exit) ────────────────────
section("1b — _get_field_key() exception behavior")

from security.crypto import _get_field_key

# Unset
os.environ.pop("FIELD_ENCRYPTION_KEY", None)
try:
    _get_field_key()
    check("Unset kljuc → RuntimeError", False, "nije bacilo exception")
except RuntimeError as e:
    check("Unset kljuc → RuntimeError", True, str(e)[:60])

# Nevalidan base64
os.environ["FIELD_ENCRYPTION_KEY"] = "!@#$%^"
try:
    _get_field_key()
    check("Nevalidan base64 → RuntimeError", False, "nije bacilo exception")
except RuntimeError as e:
    check("Nevalidan base64 → RuntimeError", True, str(e)[:60])

# Prekratak (1 bajt = "AA==")
os.environ["FIELD_ENCRYPTION_KEY"] = "AA"
try:
    _get_field_key()
    check("1-bajt kljuc → RuntimeError", False, "nije bacilo exception")
except RuntimeError as e:
    check("1-bajt kljuc → RuntimeError", True, str(e)[:60])

# Obnovi validan kljuc
os.environ["FIELD_ENCRYPTION_KEY"] = valid_key
key = _get_field_key()
check("Validan kljuc → bytes[32]", len(key) == 32, f"len={len(key)}")

# ─── Finalni rezultat ─────────────────────────────────────────────────────────
total  = len(_results)
passed = sum(1 for _, r in _results if r)
failed = total - passed

print(f"\n{'='*60}")
if failed == 0:
    print(f"  SVI TESTOVI PROSLI: {passed}/{total} PASS")
    print(f"  --> PRIORITY 1 (Startup validation): PASS")
else:
    print(f"  FAILED: {passed}/{total} PASS ({failed} FAIL)")
    print(f"  --> PRIORITY 1 (Startup validation): FAIL")
    for label, r in _results:
        if not r:
            print(f"    FAIL: {label}")
print(f"{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
