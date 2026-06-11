# -*- coding: utf-8 -*-
"""
PRIORITY 3 — Large scale CRM testovi.

Testira čiste Python slojeve bez baze:
- Enkripcija/dekripcija N klijenata (batch throughput)
- filter_klijent() za N klijenata × 4 role (RBAC filtering performance)
- Fuzzy name matching za N klijenata (conflict check simulation)
- Paginacija simulacija
- Pretraga simulacija
- Memory footprint estimate
"""
import io, os, sys, time, random, string, secrets, base64
import unicodedata, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ["FIELD_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

from security.crypto import encrypt_field, decrypt_field
from klijenti.permissions import Role, filter_klijent, ROLE_NAMES

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

def elapsed_ms(start):
    return (time.perf_counter() - start) * 1000


# ─── Fake data generator ──────────────────────────────────────────────────────
SRPSKA_IMENA = [
    "Marko", "Milan", "Stefan", "Nikola", "Aleksa", "Petar", "Luka", "Ivan",
    "Ana", "Jelena", "Milica", "Jovana", "Maja", "Ivana", "Katarina", "Bojana",
    "Dragan", "Slobodan", "Zoran", "Nenad", "Miroslav", "Branko", "Dejan",
    "Snezana", "Dragana", "Vesna", "Gordana", "Biljana",
]
SRPSKA_PREZIMENA = [
    "Markovic", "Petrovic", "Jovanovic", "Nikolic", "Djordjevic", "Stojanovic",
    "Ilic", "Stankovic", "Popovic", "Vukovic", "Milovanovic", "Todorovic",
    "Milosevic", "Stanisic", "Kovacevic", "Rakic", "Mitrovic", "Pejovic",
    "Lazarevic", "Dordevic", "Simic", "Lukic", "Stefanovic",
]
SRPSKE_FIRME = [
    "DOO Pravni Centar", "AD Poslovni Sistem", "SZR Usluge", "OD Konsalting",
    "JP Komunalni Servis", "DD Izgradnja", "DOO Financije", "LLC Pravna Podrska",
]


def generate_jmbg():
    # Realan format: DDMMGG7RRRK (13 cifara)
    d = random.randint(1, 28)
    m = random.randint(1, 12)
    y = random.randint(70, 99)
    r = random.randint(100, 799)
    k = random.randint(0, 9)
    return f"{d:02d}{m:02d}{y:02d}7{r:03d}{k}"


def generate_pib():
    return "".join([str(random.randint(0, 9)) for _ in range(9)])


def generate_pasos():
    letter = random.choice(string.ascii_uppercase)
    digits = "".join([str(random.randint(0, 9)) for _ in range(7)])
    return f"{letter}{digits}"


def generate_klijent(i: int) -> dict:
    """Generiše jedan fake klijent dict sa svim poljima."""
    ime = random.choice(SRPSKA_IMENA)
    prezime = random.choice(SRPSKA_PREZIMENA)
    tip = random.choice(["fizicko_lice", "pravno_lice"])
    return {
        "id":                           f"fake-{i:06d}",
        "tip":                          tip,
        "ime":                          ime,
        "prezime":                      prezime if tip == "fizicko_lice" else "",
        "firma":                        random.choice(SRPSKE_FIRME) if tip == "pravno_lice" else "",
        "status":                       "aktivan",
        "datum_nastanka":               "2024-01-01",
        "datum_poslednje_aktivnosti":   "2024-06-01",
        "kreirano":                     "2024-01-01T10:00:00Z",
        "azurirano":                    "2024-06-01T10:00:00Z",
        "aktivan":                      True,
        "telefon":                      f"+38160{random.randint(1000000,9999999)}",
        "email":                        f"{ime.lower()}.{prezime.lower()}{i}@test.rs",
        "adresa":                       f"Ulica {i}, Beograd",
        "maticni_broj":                 f"{random.randint(10000000, 99999999)}",
        "napomena":                     f"Test klijent #{i}",
        "pravni_osnov_obrade":          "legitimni_interes",
        # CONFIDENTIAL (plaintext za test, u produkciji su enc_v1:...)
        "jmbg_encrypted":               "",  # popunjavamo odvojeno
        "broj_pasosa_encrypted":        "",
        "pib_encrypted":                "",
        # HIGHLY_CONFIDENTIAL
        "connected_persons":            None,
        "saglasnost_datum":             None,
        "saglasnost_dokument_id":       None,
        "deleted_at":                   None,
        # Plaintext za matchovanje (JMBG pre enkripcije)
        "_jmbg_plain":                  generate_jmbg(),
        "_pib_plain":                   generate_pib(),
        "_pasos_plain":                 generate_pasos(),
    }


# ─── Benchmark helper ─────────────────────────────────────────────────────────
def benchmark(label, fn, *args, **kwargs):
    t = time.perf_counter()
    result = fn(*args, **kwargs)
    ms = elapsed_ms(t)
    return result, ms


# ─── DATASET VELIČINE ─────────────────────────────────────────────────────────
DATASET_SIZES = [100, 500, 1000, 5000]

for N in DATASET_SIZES:
    section(f"Dataset: {N} klijenata")

    # ── Generisanje ───────────────────────────────────────────────────────────
    t = time.perf_counter()
    klijenti = [generate_klijent(i) for i in range(N)]
    gen_ms = elapsed_ms(t)
    print(f"    Generate:    {gen_ms:.1f}ms  ({gen_ms/N:.3f}ms/klijent)")
    check(f"N={N}: Generisanje {N} klijenata u < {max(N*0.5, 500)}ms",
          gen_ms < max(N * 0.5, 500), f"{gen_ms:.1f}ms")

    # ── Enkripcija JMBG za sve ────────────────────────────────────────────────
    t = time.perf_counter()
    for k in klijenti:
        k["jmbg_encrypted"] = encrypt_field(k["_jmbg_plain"])
    enc_ms = elapsed_ms(t)
    avg_enc = enc_ms / N
    print(f"    Encrypt:     {enc_ms:.1f}ms  ({avg_enc:.3f}ms/klijent)")
    # Threshold: AES-GCM treba biti < 5ms/operacija
    check(f"N={N}: Enkriptovanje {N} JMBG-ova  (<5ms/op)",
          avg_enc < 5.0, f"{avg_enc:.3f}ms/op")

    # ── Dekripcija JMBG za sve ────────────────────────────────────────────────
    t = time.perf_counter()
    decrypted = [decrypt_field(k["jmbg_encrypted"]) for k in klijenti]
    dec_ms = elapsed_ms(t)
    avg_dec = dec_ms / N
    print(f"    Decrypt:     {dec_ms:.1f}ms  ({avg_dec:.3f}ms/klijent)")
    check(f"N={N}: Dekriptovanje {N} JMBG-ova (<5ms/op)",
          avg_dec < 5.0, f"{avg_dec:.3f}ms/op")

    # Verifikuj round-trip za prvih 10
    rt_ok = all(decrypted[i] == klijenti[i]["_jmbg_plain"] for i in range(min(10, N)))
    check(f"N={N}: Round-trip integritet (10 sample)", rt_ok)

    # ── RBAC filter za sve 4 role ──────────────────────────────────────────────
    t = time.perf_counter()
    for role in Role:
        filtered = [filter_klijent(k, role) for k in klijenti]
    rbac_ms = elapsed_ms(t)
    avg_rbac = rbac_ms / (N * 4)
    print(f"    RBAC filter: {rbac_ms:.1f}ms za {N}×4 role ({avg_rbac:.3f}ms/op)")
    check(f"N={N}: RBAC filter {N}×4 role (<0.5ms/op)",
          avg_rbac < 0.5, f"{avg_rbac:.3f}ms/op")

    # Verifikuj: SEKRETARICA ne vidi telefon (INTERNAL)
    sek_sample = filter_klijent(klijenti[0], Role.SEKRETARICA)
    check(f"N={N}: SEKRETARICA ne vidi 'telefon' u filter output",
          "telefon" not in sek_sample)

    # ── Pretraga simulacija ───────────────────────────────────────────────────
    search_term = klijenti[N // 2]["ime"].lower()[:4]  # prvih 4 slova
    t = time.perf_counter()
    results = [k for k in klijenti if search_term in k["ime"].lower()]
    search_ms = elapsed_ms(t)
    print(f"    Search:      {search_ms:.2f}ms  ('{search_term}' -> {len(results)} rezultata)")
    check(f"N={N}: Pretraga po imenu (<{max(5.0, N*0.005):.0f}ms)",
          search_ms < max(5.0, N * 0.005), f"{search_ms:.2f}ms")
    check(f"N={N}: Pretraga vraca >0 rezultata", len(results) > 0)

    # ── Paginacija simulacija ─────────────────────────────────────────────────
    PAGE_SIZE = 20
    t = time.perf_counter()
    pages = []
    for page_idx in range(min(5, N // PAGE_SIZE)):
        offset = page_idx * PAGE_SIZE
        page = klijenti[offset:offset + PAGE_SIZE]
        pages.append(page)
    pag_ms = elapsed_ms(t)
    print(f"    Pagination:  {pag_ms:.2f}ms za {len(pages)} strana × {PAGE_SIZE}")
    check(f"N={N}: Paginacija {len(pages)} strana (<2ms)", pag_ms < 2.0, f"{pag_ms:.2f}ms")
    if pages:
        check(f"N={N}: Svaka strana ima tacno {PAGE_SIZE} klijenata",
              all(len(p) == PAGE_SIZE for p in pages))

    # ── Conflict check simulacija (fuzzy match) ────────────────────────────────
    def normalize(s):
        s = unicodedata.normalize("NFD", s.lower())
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', s)).strip()

    target_name = normalize(klijenti[random.randint(0, N-1)]["ime"] + " " + klijenti[0]["prezime"])
    t = time.perf_counter()
    matches = [
        k for k in klijenti
        if target_name and (target_name in normalize(k["ime"] + " " + k["prezime"]) or
                            normalize(k["ime"] + " " + k["prezime"]) in target_name)
    ]
    conflict_ms = elapsed_ms(t)
    print(f"    ConflictChk: {conflict_ms:.2f}ms  ({len(matches)} matches za '{target_name[:20]}')")
    check(f"N={N}: Conflict check full scan (<{max(20.0, N*0.01):.0f}ms)",
          conflict_ms < max(20.0, N * 0.01), f"{conflict_ms:.2f}ms")

    # ── Memory estimate ───────────────────────────────────────────────────────
    import sys as _sys
    sample_size = _sys.getsizeof(klijenti[0])
    total_est_kb = (sample_size * N) / 1024
    print(f"    Memory est:  ~{total_est_kb:.0f}KB za {N} klijenata (~{sample_size}B/obj)")
    # Threshold: 1000 klijenata < 5MB u memoriji (samo objekti, bez strings)
    check(f"N={N}: Memory estimate <{max(5000, N*5):.0f}KB",
          total_est_kb < max(5000, N * 5), f"{total_est_kb:.0f}KB")


# ─── Pregled po veličinama ────────────────────────────────────────────────────
section("Sumarni izvestaj performansi")

# Samo verifikacija da smo prošli sve veličine
check("Svi dataset sizes završeni (100, 500, 1000, 5000)", True, "all completed")

print()
print("  NAPOMENA: Ovo su in-memory benchmarki bez baze.")
print("  Pravi bottleneck je Supabase I/O (network latency ~20-100ms/query).")
print("  Za insert 5000 klijenata u Supabase (batch insert) procijeniti:")
print("  - Batch od 100 po pozivu: ~50 requests × 50ms = ~2.5s")
print("  - Single row inserts: 5000 × 50ms = ~250s (ne koristiti!)")
print("  PREPORUKA: Koristiti batch insert (upsert sa nizom) za bulk operacije.")


# ─── Finalni rezultat ─────────────────────────────────────────────────────────
total  = len(_results)
passed = sum(1 for _, r in _results if r)
failed = total - passed

print(f"\n{'='*60}")
if failed == 0:
    print(f"  SVI TESTOVI PROSLI: {passed}/{total} PASS")
    print(f"  --> PRIORITY 3 (Scale testovi): PASS")
else:
    print(f"  FAILED: {passed}/{total} PASS ({failed} FAIL)")
    for label, r in _results:
        if not r:
            print(f"    FAIL: {label}")
    print(f"  --> PRIORITY 3 (Scale testovi): PARCIJALNI FAIL")
print(f"{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
