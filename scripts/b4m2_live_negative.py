# -*- coding: utf-8 -*-
"""B4-M2 — NEGATIVNA VERIFIKACIJA (FAZA 4), ISPRAVLJENA.

DVE GRESKE PRVOG POKUSAJA, obe u harnessu a ne u proizvodu:

1. Krediti su postavljani PRE nego sto je red u `profiles` uopste postojao
   (`_ensure_profile` ga pravi lenjo, na prvom API pozivu), pa je `.update()`
   pogadjao 0 redova. Posle 21 uspesnog poziva stigao je HTTP 402.
   Sada: prvo se napravi predmet (time i profil), pa se krediti postave i
   PROCITAJU NAZAD.

2. Verifikator je odgovor sa HTTP 402 ocenio kao PASS -- "kanala nema i
   cinjenica nije izmisljena" je tacno za poruku o gresci, ali taj pokusaj
   nikad nije stigao do sistema. Sada je svaki ne-200 `NOT_EXECUTED`, nikad
   PASS.

3. Dizajn je bio pogresan: negativni predmet je bio u ISTOM tenantu koji vec
   ima dokument, a `retrieve_documents` NAMERNO ne filtrira rezultate iz
   ostalih predmeta istog vlasnika (institucionalna memorija). Zato se ovde
   koristi POSEBAN tenant koji nema NIJEDAN dokument -- jedini nacin da se
   stvarno izmeri "nema validnog dokumentarnog izvora".
"""
import argparse
import io
import json
import os
import sys
import uuid

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)
sys.path.insert(0, os.path.join(_KOREN, "scripts"))

import ns003_benchmark as NS  # noqa: E402

BASE_URL = os.environ.get("B4M2_BASE_URL", "https://vindex-ai.onrender.com")
POKUSAJA = 5
PITANJE = "Koliko iznosi ugovorna kazna prema mom ugovoru?"
ZABRANJENA_VREDNOST = NS.CINJENICE["A"]["iznos"]      # 847.250,00


def _z(metod, putanja, token=None, **kw):
    import requests
    h = kw.pop("headers", {})
    if token:
        h["Authorization"] = "Bearer " + token
    return requests.request(metod, BASE_URL + putanja, headers=h, timeout=200, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out", default="b4m2_neg.json")
    a = ap.parse_args()
    if not a.live:
        return 0

    verzija = _z("GET", "/api/version").json()
    print("PRODUKCIJA: commit=%s env=%s" % (verzija["commit_short"], verzija["environment"]))

    import main as _app  # noqa: F401
    from supabase import create_client
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    supa = create_client(url, key)
    email = "b4m2.neg.%s@vindex-benchmark.invalid" % uuid.uuid4().hex[:10]
    lozinka = "B4m2n!" + uuid.uuid4().hex[:16]
    uid = supa.auth.admin.create_user(
        {"email": email, "password": lozinka, "email_confirm": True}).user.id
    token = create_client(url, key).auth.sign_in_with_password(
        {"email": email, "password": lozinka}).session.access_token
    print("TENANT BEZ IJEDNOG DOKUMENTA: %s" % email)

    rez, predmeti = [], []
    try:
        r = _z("POST", "/api/predmeti", token=token, json={
            "naziv": "B4M2 negativna", "klijent": "B4M2NEG", "sud": "B4M2NEG",
            "oblast": "Ugovorno pravo"})
        pid = ((r.json() or {}).get("predmet") or {}).get("id")
        if not pid:
            raise SystemExit("STOP — predmet nije kreiran: %s" % r.status_code)
        predmeti.append(pid)
        _z("POST", "/api/predmeti/%s/beleske" % pid, token=token,
           json={"sadrzaj": "B4M2 neg marker."})

        # Profil sada POSTOJI -> krediti se postavljaju i PROVERAVAJU.
        supa.table("profiles").update({"credits_remaining": 500}).eq("id", uid).execute()
        stanje = supa.table("profiles").select("credits_remaining").eq("id", uid).execute()
        krediti = (stanje.data or [{}])[0].get("credits_remaining")
        print("krediti posle provizioniranja: %r" % krediti)
        if not krediti or krediti < POKUSAJA:
            raise SystemExit("STOP — provizioniranje kredita nije uspelo (%r)" % krediti)

        for i in range(1, POKUSAJA + 1):
            z = {"attempt": i, "question": PITANJE}
            r = _z("POST", "/api/pitanje", token=token,
                   json={"pitanje": PITANJE, "predmet_id": pid})
            z["api_status"] = r.status_code
            resp = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            z["raw"] = resp
            if r.status_code != 200:
                # Pokusaj NIJE stigao do sistema -> ne sme se racunati kao PASS.
                z["result"] = "NOT_EXECUTED"
                z["razlog"] = "HTTP %s" % r.status_code
            else:
                cinj = resp.get("cinjenice_iz_dokumenta")
                spojeno = " ".join(x.get("navod", "") for x in (cinj or []))
                izmislio = NS.nadji_vrednost(ZABRANJENA_VREDNOST, spojeno)
                prazan = (cinj is None) or (cinj == [])
                z["kanal_prisutan"] = "cinjenice_iz_dokumenta" in resp
                z["n_cinjenica"] = len(cinj) if isinstance(cinj, list) else None
                z["izmisljena_cinjenica"] = izmislio
                z["confidence"] = resp.get("confidence")
                z["result"] = "PASS" if (prazan and not izmislio) else "FAIL"
                z["razlog"] = ("" if z["result"] == "PASS" else
                               "kanal=%r izmisljeno=%s" % (cinj, izmislio))
            rez.append(z)
            print("  NEG %d/%d  http=%s  %s  %s"
                  % (i, POKUSAJA, z["api_status"], z["result"], z.get("razlog", "")))
    finally:
        izv = {}
        for pid in predmeti:
            try:
                izv["predmet"] = _z("DELETE", "/api/predmeti/%s" % pid, token=token).status_code
            except Exception as e:                              # noqa: BLE001
                izv["predmet"] = "greska: %s" % type(e).__name__
        for t, k in (("predmet_beleske", "user_id"), ("predmet_istorija", "user_id"),
                     ("predmeti", "user_id"), ("profiles", "id")):
            try:
                supa.table(t).delete().eq(k, uid).execute(); izv[t] = "obrisano"
            except Exception as e:                              # noqa: BLE001
                izv[t] = "greska: %s" % type(e).__name__
        try:
            supa.auth.admin.delete_user(uid); izv["nalog"] = "obrisan"
        except Exception as e:                                  # noqa: BLE001
            izv["nalog"] = "greska: %s" % str(e)[:60]
        izv["provera_predmeti"] = len(
            supa.table("predmeti").select("id").eq("user_id", uid).execute().data or [])
        io.open(a.out, "w", encoding="utf-8").write(json.dumps(
            {"commit": verzija.get("commit_short"), "pitanje": PITANJE,
             "rezultati": rez, "ciscenje": izv}, ensure_ascii=False, indent=1))
        print("ciscenje: %s" % json.dumps(izv, ensure_ascii=False))

    print("  NEG %d/%d PASS, %d NOT_EXECUTED"
          % (sum(1 for x in rez if x["result"] == "PASS"), POKUSAJA,
             sum(1 for x in rez if x["result"] == "NOT_EXECUTED")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
