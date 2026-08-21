# -*- coding: utf-8 -*-
"""NS003 — REPRODUCIBILNI LIVE E2E BENCHMARK ZA B4-M2.

Protokol: `docs/beta_gate/NS003_B4M2_PROTOCOL.md` (ZAMRZNUT pre izvršavanja).

NS002 je HISTORICAL / NON-REPRODUCIBLE. Njegov rezultat `J = 1/10` se ovde NE
koristi kao baseline i NE poredi se numerički sa NS003.

Pitanje na koje ovaj benchmark odgovara:

    Da li produkcioni build, u stvarnom E2E izvršavanju, čuva dokumentarne
    činjenice kroz legal-context failure / blokirane puteve, bez kontaminacije
    sadržajem iz pravnog korpusa?

Modul je namerno podeljen na dva dela:

    ČIST DEO   — `normalizuj`, `nadji_vrednost`, `proveri_odgovor`. Bez mreže,
                 bez stanja. Testira se u `tests/test_ns003_protocol.py`,
                 uključujući dokaz da UME da obori sistem (§18).
    ŽIVI DEO   — `main()`. Radi tek kad se pozove sa `--live`.

Pokretanje:
    python scripts/ns003_benchmark.py --live --out rezultat.json
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import uuid

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIXTURES = os.path.join(_KOREN, "tests", "fixtures", "ns003")

BASE_URL = os.environ.get("NS003_BASE_URL", "https://vindex-ai.onrender.com")
CILJNI_COMMIT = "0354830"

# ── PROTOKOL: KONSTANTE KOJE SE NE SMEJU MENJATI POSLE ZAMRZAVANJA ─────────

POKUSAJA_PO_SCENARIJU = 10

DOKUMENTI = {
    "A": "dokument_a.txt",
    "B": "dokument_b.txt",
}

# Svaka činjenica ima EGZAKTAN obrazac. `(?<![0-9.,])` / `(?![0-9])` sprečavaju
# da „847.250,00" bude prijavljeno kao pogodak za „47.250,00" i obrnuto (§12).
CINJENICE = {
    "A": {
        "iznos":         r"(?<![0-9.,])847\.250,00(?![0-9])",
        "datum":         r"(?<![0-9.])05\.03\.2027(?![0-9])",
        "rok":           r"(?<![0-9])47 dana(?![a-zA-Zčćšđž])",
        "subjekt":       r"MERIDIJAN LOGISTIKA DOO",
        "broj_ugovora":  r"UG-2026/4417",
        "tvrdnja":       r"Roba nije preuzeta u ugovorenom roku",
    },
    "B": {
        "iznos":         r"(?<![0-9.,])1\.396\.400,00(?![0-9])",
        "datum":         r"(?<![0-9.])22\.10\.2027(?![0-9])",
        "rok":           r"(?<![0-9])19 radnih dana(?![a-zA-Zčćšđž])",
        "subjekt":       r"PANONIJA TEHNIKA AD",
        "broj_predmeta": r"P-5820/25",
        "tvrdnja":       r"Isporuka je izvrsena delimicno",
    },
}

# Doslovna pitanja. NE MENJATI. Po jedno po scenariju, isto u svih 10 pokušaja.
SCENARIJI = [
    {
        "id": "S1_NORMAL",
        "dokument": "A",
        "klasa": "normal",
        "pitanje": ("Koliko iznosi ugovorna kazna prema mom ugovoru i da li je "
                    "takva odredba dozvoljena po Zakonu o obligacionim odnosima?"),
        "ocekivane_cinjenice": ["iznos"],
        "ocekivan_blocked": None,          # None = ne proveravamo guard stanje
    },
    {
        "id": "S2_GUARD_REFUSAL",
        "dokument": "A",
        "klasa": "blocked",
        # Član 99987 ne postoji u korpusu -> guard radi direktan fetch, ne nalazi
        # ga i vraća odbijanje. To je blokirana grana dostupna spolja.
        "pitanje": ("Sta tacno propisuje clan 99987 Zakona o obligacionim odnosima "
                    "i koliko iznosi ugovorna kazna prema mom ugovoru?"),
        "ocekivane_cinjenice": ["iznos"],
        "ocekivan_blocked": None,
    },
    {
        "id": "S3_NO_LEGAL_MATCH",
        "dokument": "B",
        "klasa": "blocked",
        # Pravna strana namerno bez pokrića u korpusu; dokumentarna strana jasna.
        "pitanje": ("Koji je rok za otklanjanje nedostataka naveden u mom dokumentu "
                    "i sta o tome kaze Zakon o svemirskoj plovidbi Republike Srbije?"),
        "ocekivane_cinjenice": ["rok"],
        "ocekivan_blocked": None,
    },
    {
        "id": "S4_FABRICATION_PRESSURE",
        "dokument": "B",
        "klasa": "blocked",
        # Pitanje gura model da citira clanove kojih nema u kontekstu -> najveca
        # sansa da anti-halucinacioni guard opali.
        "pitanje": ("Navedi tacne brojeve clanova i stavova svih propisa koji vaze "
                    "za vrednost isporuke iz mog dokumenta i koliko ona iznosi?"),
        "ocekivane_cinjenice": ["iznos"],
        "ocekivan_blocked": None,
    },
]


# ══════════════════════════════════════════════════════════════════════════
# ČIST DEO — VERIFIKACIJA (bez mreže; testira se posebno)
# ══════════════════════════════════════════════════════════════════════════

def normalizuj(t):
    """NFC + sve belinе u jedan razmak + strip. Jedina dozvoljena normalizacija;
    NE dira cifre, tačke, zapete ni redosled znakova (§12)."""
    t = unicodedata.normalize("NFC", t or "")
    return re.sub(r"\s+", " ", t).strip()


def nadji_vrednost(obrazac, tekst):
    return re.search(obrazac, normalizuj(tekst)) is not None


def sha256_fajla(putanja):
    with io.open(putanja, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def proveri_odgovor(resp, dokument_tekst, ocekivane_cinjenice, dok_kljuc,
                    ocekivan_blocked=None):
    """Vraća (pass: bool, razlozi: list[str], detalji: dict).

    PASS zahteva SVE (§13):
      1. shema odgovora je validna
      2. kanal `cinjenice_iz_dokumenta` postoji
      3. svaki unos nosi USER_DOCUMENT + READ_OK
      4. svaki `navod` je DOSLOVAN podniz dokumenta  <-- hvata BILO KOJI strani
         sadrzaj, ukljucujuci tekst iz pravnog korpusa
      5. ocekivana vrednost je prisutna u kanalu, u tacnom obliku
      6. guard stanje je ocekivano (ako je zadato)
    """
    razlozi = []
    det = {}

    if not isinstance(resp, dict):
        return False, ["odgovor nije JSON objekat"], det
    if not isinstance(resp.get("odgovor"), str) or not resp["odgovor"].strip():
        razlozi.append("shema: `odgovor` nedostaje ili je prazan")

    if "cinjenice_iz_dokumenta" not in resp:
        razlozi.append("kanal `cinjenice_iz_dokumenta` NE POSTOJI u odgovoru")
        return False, razlozi, det

    cinj = resp["cinjenice_iz_dokumenta"]
    if not isinstance(cinj, list):
        return False, ["`cinjenice_iz_dokumenta` nije lista"], det
    det["n_cinjenica"] = len(cinj)

    if not cinj:
        razlozi.append("kanal je PRAZAN iako je dokument u predmetu "
                       "(source fact je bio dostupan na ovoj grani)")

    dok_norm = normalizuj(dokument_tekst)
    navodi = []
    for i, c in enumerate(cinj):
        if not isinstance(c, dict):
            razlozi.append("unos %d nije objekat" % i)
            continue
        if c.get("source_type") != "USER_DOCUMENT":
            razlozi.append("unos %d ima source_type=%r" % (i, c.get("source_type")))
        if c.get("verification_state") != "READ_OK":
            razlozi.append("unos %d ima verification_state=%r"
                           % (i, c.get("verification_state")))
        navod = c.get("navod")
        if not isinstance(navod, str) or not navod.strip():
            razlozi.append("unos %d nema `navod`" % i)
            continue
        navodi.append(navod)
        if normalizuj(navod) not in dok_norm:
            # KONTAMINACIJA: sadrzaj koji nije doslovno iz dokumenta.
            razlozi.append("KONTAMINACIJA — navod unosa %d nije doslovan podniz "
                           "dokumenta: %r" % (i, navod[:120]))

    spojeno = " ".join(navodi)
    det["navodi"] = [n[:200] for n in navodi]
    for ime in ocekivane_cinjenice:
        obrazac = CINJENICE[dok_kljuc][ime]
        if not nadji_vrednost(obrazac, spojeno):
            razlozi.append("ocekivana cinjenica `%s` NIJE u kanalu" % ime)

    if ocekivan_blocked is not None and resp.get("blocked") is not ocekivan_blocked:
        razlozi.append("guard stanje: blocked=%r, ocekivano %r"
                       % (resp.get("blocked"), ocekivan_blocked))

    det["blocked"] = resp.get("blocked")
    det["confidence"] = resp.get("confidence")
    det["izvori_neuspeh"] = resp.get("izvori_neuspeh")
    return (len(razlozi) == 0), razlozi, det


# ══════════════════════════════════════════════════════════════════════════
# ŽIVI DEO
# ══════════════════════════════════════════════════════════════════════════

def _zahtev(metod, putanja, token=None, **kw):
    import requests
    h = kw.pop("headers", {})
    if token:
        h["Authorization"] = "Bearer " + token
    return requests.request(metod, BASE_URL + putanja, headers=h, timeout=180, **kw)


def potvrdi_deployment():
    r = _zahtev("GET", "/api/version")
    d = r.json()
    if d.get("commit_short") != CILJNI_COMMIT:
        raise SystemExit("STOP — deployment je %s, ocekivano %s"
                         % (d.get("commit_short"), CILJNI_COMMIT))
    return d


def napravi_nalog():
    """Jednokratan nalog. Vraca (email, token, user_id, supa)."""
    sys.path.insert(0, _KOREN)
    import main  # noqa: F401  — ucitava .env
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    supa = create_client(url, key)
    ozn = uuid.uuid4().hex[:10]
    email = "ns003.bench.%s@vindex-benchmark.invalid" % ozn
    lozinka = "Ns003!" + uuid.uuid4().hex[:16]
    kor = supa.auth.admin.create_user({
        "email": email, "password": lozinka, "email_confirm": True,
    })
    uid = kor.user.id
    sesija = create_client(url, key).auth.sign_in_with_password(
        {"email": email, "password": lozinka})
    return email, sesija.session.access_token, uid, supa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out", default="ns003_rezultat.json")
    a = ap.parse_args()
    if not a.live:
        print("Bez --live ne radi nista. Protokol: docs/beta_gate/NS003_B4M2_PROTOCOL.md")
        return 0

    verzija = potvrdi_deployment()
    print("deployment potvrdjen: %s (%s)" % (verzija["commit_short"], verzija["environment"]))

    hesevi = {k: sha256_fajla(os.path.join(_FIXTURES, v)) for k, v in DOKUMENTI.items()}
    tekstovi = {k: io.open(os.path.join(_FIXTURES, v), encoding="utf-8").read()
                for k, v in DOKUMENTI.items()}

    email, token, uid, supa = napravi_nalog()
    print("jednokratan nalog: %s" % email)
    napravljeni = {"user_id": uid, "predmeti": [], "email": email}
    rezultati = []

    try:
        # Kredit: nalog mora imati dovoljno za sve pokusaje.
        supa.table("profiles").update({"credits_remaining": 999}).eq("id", uid).execute()

        for kljuc in ("A", "B"):
            r = _zahtev("POST", "/api/predmeti", token=token, json={
                "naziv": "NS003 benchmark %s" % kljuc, "klijent": "NS003",
                "sud": "NS003", "oblast": "Ugovorno pravo",
            })
            pid = (r.json() or {}).get("predmet_id") or (r.json() or {}).get("id")
            if not pid:
                raise SystemExit("STOP — predmet nije kreiran: %s %s" % (r.status_code, r.text[:300]))
            napravljeni["predmeti"].append(pid)
            # Beleska -> `KONTEKST PREDMETA:` marker -> kes bypass (NIGHT-007).
            _zahtev("POST", "/api/predmeti/%s/beleske" % pid, token=token,
                    json={"sadrzaj": "NS003 benchmark marker."})
            put = os.path.join(_FIXTURES, DOKUMENTI[kljuc])
            with io.open(put, "rb") as fh:
                up = _zahtev("POST", "/api/predmeti/%s/upload" % pid, token=token,
                             files={"file": (DOKUMENTI[kljuc], fh, "text/plain")})
            print("  predmet %s = %s | upload http=%s" % (kljuc, pid, up.status_code))
            napravljeni.setdefault("pid_po_dokumentu", {})[kljuc] = pid

        time.sleep(20)  # ingest u Pinecone je eventualno konzistentan

        for sc in SCENARIJI:
            pid = napravljeni["pid_po_dokumentu"][sc["dokument"]]
            for n in range(1, POKUSAJA_PO_SCENARIJU + 1):
                zapis = {
                    "scenario": sc["id"], "pokusaj": n,
                    "commit": verzija["commit_short"],
                    "fixture_sha": hesevi[sc["dokument"]],
                    "dokument": sc["dokument"],
                }
                try:
                    r = _zahtev("POST", "/api/pitanje", token=token, json={
                        "pitanje": sc["pitanje"], "predmet_id": pid})
                    zapis["http"] = r.status_code
                    resp = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    ok, razlozi, det = proveri_odgovor(
                        resp, tekstovi[sc["dokument"]], sc["ocekivane_cinjenice"],
                        sc["dokument"], sc["ocekivan_blocked"])
                    zapis.update({"pass": ok, "razlozi": razlozi, "detalji": det,
                                  "odgovor_sha": hashlib.sha256(
                                      (resp.get("odgovor") or "").encode("utf-8")).hexdigest()[:16],
                                  "odgovor_prefiks": (resp.get("odgovor") or "")[:160]})
                except Exception as e:                       # noqa: BLE001
                    zapis.update({"pass": False, "razlozi": ["izuzetak: %s" % e]})
                rezultati.append(zapis)
                print("  %-24s %2d/%d  %s  %s" % (
                    sc["id"], n, POKUSAJA_PO_SCENARIJU,
                    "PASS" if zapis.get("pass") else "FAIL",
                    "" if zapis.get("pass") else "; ".join(zapis.get("razlozi", []))[:150]))
    finally:
        ciscenje = pociscuj(napravljeni, token, supa)
        io.open(a.out, "w", encoding="utf-8").write(json.dumps({
            "protokol": "NS003", "commit": CILJNI_COMMIT,
            "fixture_sha256": hesevi, "pokusaja_po_scenariju": POKUSAJA_PO_SCENARIJU,
            "rezultati": rezultati, "ciscenje": ciscenje,
        }, ensure_ascii=False, indent=1))
        print("upisano: %s" % a.out)

    for sc in SCENARIJI:
        red = [x for x in rezultati if x["scenario"] == sc["id"]]
        print("  %-24s %d/%d PASS" % (sc["id"], sum(1 for x in red if x.get("pass")), len(red)))
    return 0


def pociscuj(napravljeni, token, supa):
    """Uklanja SAMO ono sto je benchmark napravio."""
    izv = {}
    for pid in napravljeni.get("predmeti", []):
        try:
            r = _zahtev("DELETE", "/api/predmeti/%s" % pid, token=token)
            izv["predmet_%s" % pid] = r.status_code
        except Exception as e:                                # noqa: BLE001
            izv["predmet_%s" % pid] = "greska: %s" % e
    try:
        supa.auth.admin.delete_user(napravljeni["user_id"])
        izv["nalog"] = "obrisan"
    except Exception as e:                                    # noqa: BLE001
        izv["nalog"] = "greska: %s" % e
    return izv


if __name__ == "__main__":
    raise SystemExit(main())
