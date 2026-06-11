# -*- coding: utf-8 -*-
"""
PRIORITY 5 — Soft delete i recovery testovi.

Testira soft-delete logiku statički (bez baze) + simulira state machine.
Dokazuje da soft-delete ne briše podatke, da se status ispravno setuje,
i da recovery vraća sve podatke.
"""
import io, os, sys, base64, secrets, ast, inspect
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["FIELD_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

from security.crypto import encrypt_field, decrypt_field
from klijenti.permissions import Role, can_perform

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


# ─── 5a: Soft delete state machine simulacija ─────────────────────────────────
section("5a — Soft delete state machine (bez baze)")

class FakeKlijent:
    """Simulira klijent objekat u memoriji."""
    def __init__(self, ime, jmbg):
        self.id = "fake-uuid-001"
        self.ime = ime
        self.jmbg_encrypted = encrypt_field(jmbg)
        self.status = "aktivan"
        self.aktivan = True
        self.deleted_at = None
        self.dokumenti = [{"id": "doc-1", "naziv": "ugovor.pdf"}]
        self.audit_log = []
        self.komunikacija = []

    def soft_delete(self, by_role: Role, now: str):
        if not can_perform(by_role, "soft_delete_client"):
            raise PermissionError(f"Rola {by_role} nema dozvolu za soft_delete")
        self.status = "soft_deleted"
        self.aktivan = False
        self.deleted_at = now
        self.audit_log.append({"akcija": "DELETE_SOFT", "ts": now})

    def restore(self, by_role: Role, now: str):
        if by_role < Role.PARTNER:
            raise PermissionError("Restore zahteva PARTNER")
        self.status = "aktivan"
        self.aktivan = True
        self.deleted_at = None
        self.audit_log.append({"akcija": "RESTORE", "ts": now})

    def decrypt_jmbg(self):
        return decrypt_field(self.jmbg_encrypted)


# Korak 1: Kreiraj klijenta
k = FakeKlijent("Marko Markovic", "0101990710123")
check("Klijent kreiran — status=aktivan", k.status == "aktivan")
check("Klijent kreiran — aktivan=True", k.aktivan is True)
check("Klijent kreiran — deleted_at=None", k.deleted_at is None)
check("JMBG enkriptovan (ne plaintext u 'bazi')", k.jmbg_encrypted.startswith("enc_v1:"))

# Korak 2: Dodaj dokument i komunikaciju
k.dokumenti.append({"id": "doc-2", "naziv": "punomocje.pdf"})
k.komunikacija.append({"tip": "poziv", "opis": "inicijalni kontakt"})
check("Dokumenti postoje pre delete", len(k.dokumenti) == 2)
check("Komunikacija postoji pre delete", len(k.komunikacija) == 1)

# Korak 3: Pokusaj soft-delete sa non-PARTNER rolom (mora fail)
for bad_role in [Role.SEKRETARICA, Role.PRIPRAVNIK, Role.ADVOKAT]:
    try:
        k.soft_delete(bad_role, "2026-06-11T10:00:00Z")
        check(f"Soft-delete rola {bad_role} treba FAIL", False, "nije bacilo PermissionError")
    except PermissionError:
        check(f"Soft-delete rola {bad_role} → PermissionError", True)

# Korak 4: Soft-delete sa PARTNER rolom (mora uspeti)
check("Status pre delete = aktivan", k.status == "aktivan")
k.soft_delete(Role.PARTNER, "2026-06-11T10:00:00Z")
check("Status posle delete = soft_deleted", k.status == "soft_deleted")
check("aktivan = False posle delete", k.aktivan is False)
check("deleted_at postavljeno", k.deleted_at is not None)
check("Audit log ima DELETE_SOFT zapis", any(a["akcija"] == "DELETE_SOFT" for a in k.audit_log))

# Korak 5: Verifikacija da su podaci OSTALI
check("Dokumenti postoje posle delete", len(k.dokumenti) == 2)
check("Komunikacija postoji posle delete", len(k.komunikacija) == 1)
check("JMBG ostao enkriptovan posle delete", k.jmbg_encrypted.startswith("enc_v1:"))
jmbg_dec = k.decrypt_jmbg()
check("JMBG se dekriptuje posle delete", jmbg_dec == "0101990710123", f"got={jmbg_dec}")

# Korak 6: Restore (simulacija — ne implementovano u router-u, ali testiramo logiku)
k.restore(Role.PARTNER, "2026-06-11T11:00:00Z")
check("Status posle restore = aktivan", k.status == "aktivan")
check("aktivan = True posle restore", k.aktivan is True)
check("deleted_at = None posle restore", k.deleted_at is None)
check("Audit log ima RESTORE zapis", any(a["akcija"] == "RESTORE" for a in k.audit_log))
check("Dokumenti postoje posle restore", len(k.dokumenti) == 2)
check("Komunikacija postoji posle restore", len(k.komunikacija) == 1)


# ─── 5b: Statička analiza router.py — soft delete ne briše hard ──────────────
section("5b — Statička analiza: soft delete ne poziva hard DELETE")

router_src = open(os.path.join(ROOT, "klijenti", "router.py"), encoding="utf-8").read()
tree = ast.parse(router_src)

# Trazimo delete_klijent funkciju
delete_fn_src = None
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == "delete_klijent":
        delete_fn_src = ast.get_source_segment(router_src, node)
        break

if delete_fn_src:
    check("delete_klijent postoji u router-u", True)
    # Mora imati UPDATE (soft-delete), ne DELETE
    check("delete_klijent koristi UPDATE (ne DELETE)", ".update(" in delete_fn_src)
    check("delete_klijent ne koristi .delete()", ".delete(" not in delete_fn_src)
    check("Setuje status='soft_deleted'", "soft_deleted" in delete_fn_src)
    check("Setuje deleted_at", "deleted_at" in delete_fn_src)
    check("Setuje aktivan=False", "aktivan" in delete_fn_src)
    check("Ima audit log (SOFT_DELETE akcija)", "SOFT_DELETE" in delete_fn_src or "Akcija.SOFT_DELETE" in delete_fn_src)
    # Role check — mora biti PARTNER
    check("Ima can_perform check za soft_delete_client", "soft_delete_client" in delete_fn_src)
else:
    check("delete_klijent postoji u router-u", False, "KRITICNO: funkcija nije pronadjena")


# ─── 5c: list_klijenti isklucuje soft_deleted ────────────────────────────────
section("5c — list_klijenti filtrira soft_deleted (nikad ne vracaju se obrisani)")

list_fn_src = None
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_klijenti":
        list_fn_src = ast.get_source_segment(router_src, node)
        break

if list_fn_src:
    check("list_klijenti isklucuje 'soft_deleted' status", "soft_deleted" in list_fn_src)
else:
    check("list_klijenti postoji", False)

get_fn_src = None
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_klijent":
        get_fn_src = ast.get_source_segment(router_src, node)
        break

if get_fn_src:
    check("get_klijent isklucuje 'soft_deleted' status", "soft_deleted" in get_fn_src)


# ─── 5d: RESTORE endpoint (GAP analiza) ──────────────────────────────────────
section("5d — GAP: Restore endpoint")

restore_endpoints = [n for n in router_src.split('\n') if 'restore' in n.lower() and '@router' in n.lower()]
has_restore = len(restore_endpoints) > 0

if has_restore:
    check("Restore endpoint postoji", True)
else:
    print("  [!] [GAP] Restore endpoint nije implementovan.")
    print("  [!]       Soft-delete je implementiran ali recovery zahteva direktan DB pristup.")
    print("  [!]       Preporuka: implementovati POST /klijenti/{id}/restore (samo PARTNER).")
    check("Restore endpoint postoji", False, "GAP — nije blocker, ali treba za produkciju")


# ─── Finalni rezultat ─────────────────────────────────────────────────────────
total  = len(_results)
passed = sum(1 for _, r in _results if r)
failed = total - passed
critical_fails = [l for l, r in _results if not r and "KRITICNO" in l]

print(f"\n{'='*60}")
if failed == 0:
    print(f"  SVI TESTOVI PROSLI: {passed}/{total} PASS")
    print(f"  --> PRIORITY 5 (Soft delete/recovery): PASS")
elif critical_fails:
    print(f"  KRITICNI FAIL: {critical_fails}")
    print(f"  --> PRIORITY 5: CRITICAL FAIL")
else:
    print(f"  FAILED: {passed}/{total} PASS ({failed} FAIL)")
    for label, r in _results:
        if not r:
            print(f"    FAIL: {label}")
    print(f"  --> PRIORITY 5: PARTIAL PASS (provjeri gore)")
print(f"{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
