# -*- coding: utf-8 -*-
"""
PRIORITY 4 — Audit log integritet testovi.

Testira bez prave baze — mockuje supa i log_event.
Proverava da se audit kreira sa ispravnim poljima za svaku akciju i svaku rolu.
"""
import io, os, sys, asyncio, base64, secrets, unittest
from unittest.mock import AsyncMock, MagicMock, patch, call
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Postavi encryption key za testove
os.environ["FIELD_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

from klijenti.permissions import Role, ROLE_NAMES

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


# ─── Helper: kreira mock user za svaku rolu ───────────────────────────────────
def make_user(role: Role) -> dict:
    return {
        "user_id":   f"uid-{ROLE_NAMES[role]}",
        "email":     f"{ROLE_NAMES[role]}@vindex.test",
        "role":      role,
        "role_str":  ROLE_NAMES[role],
    }


# ─── 4a: VIEW_CONFIDENTIAL audit MORA biti pre return-a ─────────────────────
section("4a — reveal_confidential: audit MORA biti await (ne create_task)")

# Proveravamo statički da li je u kodu `await log_event` za VIEW_CONFIDENTIAL
import inspect
import klijenti.router as _router_mod
src = inspect.getsource(_router_mod.get_klijent)

# Tražimo pattern: await log_event(...VIEW_CONFIDENTIAL...)
# Mora biti BEFORE decrypt, i mora biti AWAIT (ne create_task)
lines = src.split('\n')
# VIEW_CONFIDENTIAL može biti na zasebnoj liniji multi-line call-a
vc_line_idx = None
log_event_before_vc_idx = None
decrypt_line_idx = None
for i, line in enumerate(lines):
    if 'VIEW_CONFIDENTIAL' in line:
        vc_line_idx = i
    if 'await log_event' in line and vc_line_idx is None:
        # log_event koji prethodi VIEW_CONFIDENTIAL liniji
        log_event_before_vc_idx = i
    if 'decrypt_field' in line and 'klijent[' in line:
        if decrypt_line_idx is None:
            decrypt_line_idx = i

# audit_line_idx = linija 'await log_event' koja je najbliza vc_line_idx (pre ili na vc liniji)
audit_line_idx = log_event_before_vc_idx

check(
    "VIEW_CONFIDENTIAL audit log postoji u get_klijent()",
    vc_line_idx is not None,
    f"vc_linija={vc_line_idx}"
)
check(
    "VIEW_CONFIDENTIAL audit je AWAIT (ne create_task)",
    vc_line_idx is not None and any(
        'await log_event' in lines[j] for j in range(max(0, vc_line_idx - 5), vc_line_idx + 3)
    ),
    "trazi 'await log_event' u okolini VIEW_CONFIDENTIAL (+/-5 linija)"
)
if vc_line_idx is not None and decrypt_line_idx is not None:
    check(
        "Audit BEFORE decrypt (linija audit < linija decrypt)",
        vc_line_idx < decrypt_line_idx,
        f"vc_line={vc_line_idx}, decrypt_line={decrypt_line_idx}"
    )


# ─── 4b: Sva polja audit zapisa ──────────────────────────────────────────────
section("4b — Audit log polja: user_id, role, timestamp, resource_id, action, IP")

import klijenti.audit as _audit_mod

# Proveravamo potpis log_event funkcije
import inspect
sig = inspect.signature(_audit_mod.log_event)
params = set(sig.parameters.keys())

for field in ['user_id', 'user_email', 'user_role', 'akcija', 'entitet_id', 'ip_adresa']:
    check(f"log_event ima parametar '{field}'", field in params)

# Proveravamo da se timestamp dodaje automatski (DEFAULT now() u SQL)
# Provera: insert u log_event ne prosleđuje timestamp ručno (baza ga generise)
src_audit = inspect.getsource(_audit_mod.log_event)
check(
    "log_event ne prosleđuje 'timestamp' ručno (baza generiše DEFAULT now())",
    '"timestamp"' not in src_audit and "'timestamp'" not in src_audit,
    "timestamp mora biti DB DEFAULT, ne klijentski"
)


# ─── 4c: Role-based access za VIEW_CONFIDENTIAL ──────────────────────────────
section("4c — Koje role SMEJU pozvati reveal_confidential=True")

from klijenti.permissions import can_perform, Role

EXPECTED = {
    Role.SEKRETARICA: False,  # ne sme
    Role.PRIPRAVNIK:  False,  # ne sme
    Role.ADVOKAT:     True,   # sme
    Role.PARTNER:     True,   # sme
}

for role, expected in EXPECTED.items():
    result = can_perform(role, "access_confidential")
    check(
        f"can_perform({ROLE_NAMES[role]}, 'access_confidential') == {expected}",
        result == expected,
        f"got={result}"
    )


# ─── 4d: Provjera da encrypt fields nisu u reveal_confidential response ───────
section("4d — reveal_confidential response ne sadrži i enc i plain")

# Statička analiza: nakon .pop(enc_field), klijent[plain_key] se dodaje
src_get = inspect.getsource(_router_mod.get_klijent)

# Tražimo .pop() za encrypted polja
check(
    "jmbg_encrypted se .pop()-uje pre dodavanja plain verzije",
    'klijent.pop(enc_field' in src_get or "klijent.pop(" in src_get,
    "encrypted polje mora biti uklonjeno iz response"
)

# Proveravamo da return NE vraća oba (enc i plain)
# Tražimo pattern gde se filter_klijent primenjuje na reveal response
check(
    "Kod vraća klijent dict direktno na reveal_confidential=True",
    "if not reveal_confidential else klijent" in src_get,
    "reveal path vraca nefiltriran klijent (posle pop encrypted)"
)


# ─── 4e: Svi endpointi koji pristupaju klijent podacima imaju auth check ──────
section("4e — Svaki klijent endpoint ima _auth_from_request() poziv")

import ast
router_src = open(os.path.join(ROOT, "klijenti", "router.py"), encoding="utf-8").read()
tree = ast.parse(router_src)

endpoint_functions = []
for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef):
        # Funkcije koje su endpointi (imaju router dekorator u okolini)
        # Gruba heuristika: traži funkcije sa "request" parametrom
        params = [a.arg for a in node.args.args]
        if 'request' in params and node.name.startswith(('create_', 'list_', 'get_', 'update_', 'delete_',
                                                           'check_', 'upload_', 'download_', 'add_',
                                                           'arhiviraj_', 'set_', 'retention_')):
            endpoint_functions.append(node.name)

            # Provjeri da u tijelu postoji _auth_from_request poziv
            has_auth = False
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Name) and func.id == '_auth_from_request':
                        has_auth = True
                    elif isinstance(func, ast.Attribute) and func.attr == '_auth_from_request':
                        has_auth = True
            check(f"Endpoint '{node.name}' ima _auth_from_request()", has_auth)


# ─── 4f: Horizontal access guard u svim sub-resource endpointima ─────────────
section("4f — _verify_owns_klijent() u svim sub-resource endpointima")

SUB_RESOURCE_ENDPOINTS = [
    'get_klijent_audit', 'upload_klijent_dokument', 'list_klijent_dokumenti',
    'download_klijent_dokument', 'add_komunikacija', 'get_timeline',
]

for node in ast.walk(tree):
    if isinstance(node, ast.AsyncFunctionDef) and node.name in SUB_RESOURCE_ENDPOINTS:
        has_guard = False
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Name) and func.id == '_verify_owns_klijent':
                    has_guard = True
                elif isinstance(func, ast.Attribute) and func.attr == '_verify_owns_klijent':
                    has_guard = True
        check(
            f"'{node.name}' ima _verify_owns_klijent() horizontal access guard",
            has_guard
        )


# ─── Finalni rezultat ─────────────────────────────────────────────────────────
total  = len(_results)
passed = sum(1 for _, r in _results if r)
failed = total - passed

print(f"\n{'='*60}")
if failed == 0:
    print(f"  SVI TESTOVI PROSLI: {passed}/{total} PASS")
    print(f"  --> PRIORITY 4 (Audit integritet): PASS")
else:
    print(f"  FAILED: {passed}/{total} PASS ({failed} FAIL)")
    print(f"  --> PRIORITY 4 (Audit integritet): FAIL")
    for label, r in _results:
        if not r:
            print(f"    FAIL: {label}")
print(f"{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
