# -*- coding: utf-8 -*-
"""B4-M2 — ŽIVI E2E DOKAZ ZA SCENARIJE A i J.

RELEASE EVIDENCE, ne development. Ne menja produkcioni kod.

Meri se JEDNO pitanje:

    Da li činjenica iz advokatovog dokumenta preživi kada pravni deo sistema
    ne proizvede normalan odgovor — i da li se NE pojavljuje kada validnog
    dokumentarnog izvora nema?

Puni put: dokument → stvarni ingest → Pinecone → retrieval → pravni failure →
blokiran/odbijen odgovor → API → (posebno) UI.

Fixture-i i verifikator se UZIMAJU iz zamrznutog NS003 paketa i NE menjaju se:
    tests/fixtures/ns003/dokument_a.txt   sha256 2294912a...
    scripts/ns003_benchmark.py            proveri_odgovor / nadji_vrednost

Pokretanje:
    python scripts/b4m2_live_e2e.py --live --out rezultat.json
"""
import argparse
import hashlib
import io
import json
import os
import sys
import time

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)
sys.path.insert(0, os.path.join(_KOREN, "scripts"))

import ns003_benchmark as NS  # noqa: E402  — zamrznuti verifikator i fixture-i

BASE_URL = os.environ.get("B4M2_BASE_URL", "https://vindex-ai.onrender.com")

POKUSAJA_A = 10
POKUSAJA_J = 10
POKUSAJA_NEG = 5

# DOCUMENT FACT — eksplicitan, jedinstven, nije izvodiv iz opsteg pravnog znanja.
DOKUMENT = "dokument_a.txt"
DOK_KLJUC = "A"
CINJENICA_IME = "iznos"
CINJENICA_VREDNOST = "847.250,00"

PITANJE_A = "Koliko iznosi ugovorna kazna prema mom ugovoru?"
# Clan 99987 ne postoji u korpusu -> pravni deo ne moze da proizvede normalan
# odgovor. Dokumentarni deo pitanja ostaje isti.
PITANJE_J = ("Sta tacno propisuje clan 99987 Zakona o obligacionim odnosima "
             "i koliko iznosi ugovorna kazna prema mom ugovoru?")
# Negativna verifikacija: isto pitanje, predmet BEZ dokumenta.
PITANJE_NEG = PITANJE_A


def napravi_docx(tekst):
    """DOCX kontejner sa DOSLOVNIM tekstom zamrznutog fixture-a.

    Fixture na disku se ne dira. Menja se samo omot, jer produkcioni upload
    prima iskljucivo PDF/DOCX. Svaki red fixture-a postaje jedan pasus.
    """
    import tempfile
    from docx import Document
    d = Document()
    for red in tekst.split("\n"):
        d.add_paragraph(red)
    put = os.path.join(tempfile.gettempdir(), "b4m2_dokument_a.docx")
    d.save(put)
    return put


def _z(metod, putanja, token=None, **kw):
    import requests
    h = kw.pop("headers", {})
    if token:
        h["Authorization"] = "Bearer " + token
    return requests.request(metod, BASE_URL + putanja, headers=h, timeout=200, **kw)


def klasifikuj_pravni_status(r):
    """Koji se od cetiri J pod-slucaja stvarno desio. Cita se STANJE odgovora,
    ne pretpostavka."""
    if r.get("retrieval_unavailable"):
        return "C_pravna_greska"
    if r.get("blocked") is True:
        return "D_guard_block"
    conf = (r.get("confidence") or "").upper()
    if conf == "LOW":
        return "A_pravni_LOW"
    return "normalan"


def izvrsi(token, pid, pitanje, n, oznaka, dok_tekst, ocekuj_cinjenicu, rezultati):
    for i in range(1, n + 1):
        zapis = {"scenario": oznaka, "attempt": i, "question": pitanje}
        try:
            r = _z("POST", "/api/pitanje", token=token,
                   json={"pitanje": pitanje, "predmet_id": pid})
            zapis["api_status"] = r.status_code
            resp = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            zapis["raw"] = resp
            cinj = resp.get("cinjenice_iz_dokumenta")
            zapis["kanal_prisutan"] = "cinjenice_iz_dokumenta" in resp
            zapis["n_cinjenica"] = len(cinj) if isinstance(cinj, list) else None
            zapis["blocked"] = resp.get("blocked")
            zapis["confidence"] = resp.get("confidence")
            zapis["izvori_neuspeh"] = resp.get("izvori_neuspeh")
            zapis["legal_status"] = klasifikuj_pravni_status(resp)
            zapis["odgovor_prefiks"] = (resp.get("odgovor") or "")[:200]

            if ocekuj_cinjenicu:
                ok, razlozi, det = NS.proveri_odgovor(
                    resp, dok_tekst, [CINJENICA_IME], DOK_KLJUC, None)
                zapis["document_fact"] = NS.nadji_vrednost(
                    NS.CINJENICE[DOK_KLJUC][CINJENICA_IME],
                    " ".join(x.get("navod", "") for x in (cinj or [])))
                zapis["provenance_ok"] = ok
                zapis["razlozi"] = razlozi
                zapis["result"] = "PASS" if ok else "FAIL"
            else:
                # NEGATIVNA: kanal sme da postoji, ali MORA biti prazan i NE SME
                # nositi vrednost iz dokumenta koji ovaj predmet nema.
                spojeno = " ".join(x.get("navod", "") for x in (cinj or []))
                izmislio = NS.nadji_vrednost(
                    NS.CINJENICE[DOK_KLJUC][CINJENICA_IME], spojeno)
                prazan = (cinj == [] or cinj is None)
                zapis["document_fact"] = izmislio
                zapis["provenance_ok"] = (not izmislio) and prazan
                zapis["razlozi"] = ([] if zapis["provenance_ok"] else
                                    ["kanal nije prazan (%r) ili nosi izmisljenu cinjenicu (%s)"
                                     % (cinj, izmislio)])
                zapis["result"] = "PASS" if zapis["provenance_ok"] else "FAIL"
        except Exception as e:                                  # noqa: BLE001
            zapis.update({"result": "FAIL", "razlozi": ["izuzetak: %s" % e]})
        rezultati.append(zapis)
        print("  %-10s %2d/%d  %-16s blocked=%-5s kanal=%-5s fact=%-5s %s"
              % (oznaka, i, n, zapis.get("legal_status", "-"), zapis.get("blocked"),
                 zapis.get("kanal_prisutan"), zapis.get("document_fact"),
                 zapis.get("result")))


def pociscuj(supa, uid, token, predmeti):
    izv = {}
    for pid in predmeti:
        try:
            izv["predmet_%s" % pid[:8]] = _z("DELETE", "/api/predmeti/%s" % pid, token=token).status_code
        except Exception as e:                                  # noqa: BLE001
            izv["predmet_%s" % pid[:8]] = "greska: %s" % type(e).__name__
    for t, k in (("predmet_beleske", "user_id"), ("predmet_istorija", "user_id"),
                 ("predmeti", "user_id"), ("profiles", "id")):
        try:
            supa.table(t).delete().eq(k, uid).execute()
            izv[t] = "obrisano"
        except Exception as e:                                  # noqa: BLE001
            izv[t] = "greska: %s" % type(e).__name__
    try:
        supa.auth.admin.delete_user(uid)
        izv["nalog"] = "obrisan"
    except Exception as e:                                      # noqa: BLE001
        izv["nalog"] = "greska: %s" % str(e)[:80]
    for t, k in (("predmeti", "user_id"), ("profiles", "id")):
        try:
            izv["provera_" + t] = len(supa.table(t).select("id").eq(k, uid).execute().data or [])
        except Exception:                                       # noqa: BLE001
            izv["provera_" + t] = "n/a"
    return izv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out", default="b4m2_live.json")
    a = ap.parse_args()
    if not a.live:
        print("Bez --live ne radi nista.")
        return 0

    verzija = _z("GET", "/api/version").json()
    print("PRODUKCIJA: commit=%s identity_proven=%s env=%s"
          % (verzija["commit_short"], verzija["identity_proven"], verzija["environment"]))

    put_dok = os.path.join(_KOREN, "tests", "fixtures", "ns003", DOKUMENT)
    dok_tekst = io.open(put_dok, encoding="utf-8").read()
    dok_sha = NS.sha256_fajla(put_dok)
    print("DOKUMENT: %s sha256=%s" % (DOKUMENT, dok_sha[:16]))
    print("DOCUMENT FACT: %s" % CINJENICA_VREDNOST)

    import main as _app  # noqa: F401 — ucitava .env
    from supabase import create_client
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    supa = create_client(url, key)
    import uuid as _u
    email = "b4m2.live.%s@vindex-benchmark.invalid" % _u.uuid4().hex[:10]
    lozinka = "B4m2!" + _u.uuid4().hex[:16]
    kor = supa.auth.admin.create_user({"email": email, "password": lozinka, "email_confirm": True})
    uid = kor.user.id
    token = create_client(url, key).auth.sign_in_with_password(
        {"email": email, "password": lozinka}).session.access_token
    print("TENANT: %s" % email)

    rezultati, predmeti = [], []
    try:
        # Provizioniranje TENANTA, ne izmena proizvoda:
        #   `predmet_upload_ai` u `feature_registry` ima minimum_plan
        #   'professional' (izmereno), a svez nalog je 'basic' -> upload je
        #   vracao HTTP 403. Podize se plan SAMO ovom benchmark nalogu.
        _istice = "2027-12-31T00:00:00+00:00"
        supa.table("profiles").update({
            "credits_remaining": 999,
            "subscription_type": "professional",
            "subscription_expires_at": _istice,
        }).eq("id", uid).execute()

        def novi_predmet(naziv):
            r = _z("POST", "/api/predmeti", token=token, json={
                "naziv": naziv, "klijent": "B4M2LIVE", "sud": "B4M2LIVE",
                "oblast": "Ugovorno pravo"})
            pid = ((r.json() or {}).get("predmet") or {}).get("id")
            if not pid:
                raise SystemExit("STOP — predmet nije kreiran: %s %s" % (r.status_code, r.text[:200]))
            predmeti.append(pid)
            # Beleska -> marker `KONTEKST PREDMETA:` -> kes bypass (NIGHT-007).
            _z("POST", "/api/predmeti/%s/beleske" % pid, token=token,
               json={"sadrzaj": "B4M2 live marker."})
            return pid

        pid_sa = novi_predmet("B4M2 live SA dokumentom")
        # Produkcija prima SAMO PDF/DOCX (HTTP 415 za .txt — izmereno). Zamrznuti
        # fixture se NE menja; pravi se DOCX kontejner ciji je tekst doslovno
        # preuzet iz njega, pa DOCUMENT FACT ostaje nepromenjen.
        put_docx = napravi_docx(dok_tekst)
        docx_sha = NS.sha256_fajla(put_docx)
        print("KONTEJNER: docx sha256=%s (tekst iz %s)" % (docx_sha[:16], DOKUMENT))
        with io.open(put_docx, "rb") as fh:
            up = _z("POST", "/api/predmeti/%s/upload" % pid_sa, token=token,
                    files={"file": ("dokument_a.docx", fh,
                                    "application/vnd.openxmlformats-officedocument."
                                    "wordprocessingml.document")})
        print("INGEST: http=%s" % up.status_code)
        if up.status_code >= 400:
            raise SystemExit("STOP — produkcioni ingest nije uspeo: %s" % up.text[:300])
        pid_bez = novi_predmet("B4M2 live BEZ dokumenta")

        print("cekam ingest (Pinecone je eventualno konzistentan)...")
        time.sleep(30)

        print("\nSCENARIO A — dokument dostupan")
        izvrsi(token, pid_sa, PITANJE_A, POKUSAJA_A, "A", dok_tekst, True, rezultati)
        print("\nSCENARIO J — pravni deo ne moze da odgovori")
        izvrsi(token, pid_sa, PITANJE_J, POKUSAJA_J, "J", dok_tekst, True, rezultati)
        print("\nNEGATIVNA — predmet BEZ dokumenta")
        izvrsi(token, pid_bez, PITANJE_NEG, POKUSAJA_NEG, "NEG", dok_tekst, False, rezultati)
    finally:
        ciscenje = pociscuj(supa, uid, token, predmeti)
        io.open(a.out, "w", encoding="utf-8").write(json.dumps({
            "commit": verzija.get("commit_short"),
            "identity_proven": verzija.get("identity_proven"),
            "environment": verzija.get("environment"),
            "dokument": DOKUMENT, "dokument_sha256": dok_sha,
            "document_fact": CINJENICA_VREDNOST,
            "pitanja": {"A": PITANJE_A, "J": PITANJE_J, "NEG": PITANJE_NEG},
            "rezultati": rezultati, "ciscenje": ciscenje,
        }, ensure_ascii=False, indent=1))
        print("\nciscenje: %s" % json.dumps(ciscenje, ensure_ascii=False))
        print("upisano: %s" % a.out)

    for oz, n in (("A", POKUSAJA_A), ("J", POKUSAJA_J), ("NEG", POKUSAJA_NEG)):
        red = [x for x in rezultati if x["scenario"] == oz]
        print("  %-4s %d/%d PASS" % (oz, sum(1 for x in red if x.get("result") == "PASS"), n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
