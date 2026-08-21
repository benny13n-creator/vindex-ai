# -*- coding: utf-8 -*-
"""BETA REALITY RECON — zivi journey stvarnog advokata.

RECONNAISSANCE, ne remediation. Ne menja produkcioni kod.

Redosled po prioritetu iz mandata:
  DATA LEAK   -> cross-tenant read/write
  WRONG DEADLINE -> B1 (rok iz dokumenta: EXTRACTED/PERSISTED/RETRIEVED)
  DATA LOSS   -> brisanje predmeta
  ostalo      -> B2 finansije, B3 glas, B4 smoke, AI failure modes

Dva jednokratna tenanta, oba se ciste i provera se upisuje u izlaz.
"""
import argparse
import io
import json
import os
import sys
import time
import uuid

_KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _KOREN)
sys.path.insert(0, os.path.join(_KOREN, "scripts"))

import ns003_benchmark as NS  # noqa: E402  (fixture + verifikator, nepromenjeni)

BASE = os.environ.get("B4M2_BASE_URL", "https://vindex-ai.onrender.com")
FIX = os.path.join(_KOREN, "tests", "fixtures", "ns003", "dokument_a.txt")
IZNOS = "847.250,00"
ROK_DATUM = "2027-03-05"          # 05.03.2027 iz dokumenta
ROK_NAZIV = "NS-RECON rok iz ugovora"

nalazi = []


def N(ident, sev, naslov, dokaz, repro=True):
    nalazi.append({"id": ident, "severity": sev, "finding": naslov,
                   "evidence": dokaz, "reproducible": repro})
    print("  [%s] %-8s %s" % (ident, sev, naslov))


def Z(metod, putanja, token=None, **kw):
    import requests
    h = kw.pop("headers", {})
    if token:
        h["Authorization"] = "Bearer " + token
    return requests.request(metod, BASE + putanja, headers=h, timeout=200, **kw)


def docx_od(tekst):
    import tempfile
    from docx import Document
    d = Document()
    for r in tekst.split("\n"):
        d.add_paragraph(r)
    p = os.path.join(tempfile.gettempdir(), "recon_a.docx")
    d.save(p)
    return p


def napravi_tenant(supa, url, key, oznaka):
    from supabase import create_client
    email = "recon.%s.%s@vindex-benchmark.invalid" % (oznaka, uuid.uuid4().hex[:8])
    lozinka = "Rec0n!" + uuid.uuid4().hex[:16]
    uid = supa.auth.admin.create_user(
        {"email": email, "password": lozinka, "email_confirm": True}).user.id
    tok = create_client(url, key).auth.sign_in_with_password(
        {"email": email, "password": lozinka}).session.access_token
    return email, uid, tok


def provizionisi(supa, uid):
    supa.table("profiles").update({
        "credits_remaining": 400, "subscription_type": "professional",
        "subscription_expires_at": "2027-12-31T00:00:00+00:00"}).eq("id", uid).execute()
    r = supa.table("profiles").select("credits_remaining,subscription_type").eq("id", uid).execute()
    return (r.data or [{}])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out", default="beta_recon.json")
    a = ap.parse_args()
    if not a.live:
        return 0

    v = Z("GET", "/api/version").json()
    print("PRODUKCIJA: %s identity=%s env=%s\n" % (v["commit_short"], v["identity_proven"], v["environment"]))

    import main as _app  # noqa: F401
    from supabase import create_client
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    supa = create_client(url, key)

    eA, uidA, tokA = napravi_tenant(supa, url, key, "a")
    eB, uidB, tokB = napravi_tenant(supa, url, key, "b")
    print("TENANT A: %s\nTENANT B: %s\n" % (eA, eB))
    stanje = {"predmeti": [], "uidA": uidA, "uidB": uidB}
    izlaz = {"commit": v["commit_short"], "nalazi": nalazi, "koraci": {}}

    try:
        print("== provizioniranje ==")
        print("  A:", provizionisi(supa, uidA))
        print("  B:", provizionisi(supa, uidB))

        # ── predmet + dokument (tenant A) ──────────────────────────────────
        print("\n== FAZA 2: journey tenanta A ==")
        r = Z("POST", "/api/predmeti", token=tokA, json={
            "naziv": "RECON predmet A", "klijent": "RECON", "sud": "RECON",
            "oblast": "Ugovorno pravo"})
        pidA = ((r.json() or {}).get("predmet") or {}).get("id")
        if not pidA:
            raise SystemExit("STOP — predmet A nije kreiran: %s" % r.status_code)
        stanje["predmeti"].append((pidA, tokA))
        Z("POST", "/api/predmeti/%s/beleske" % pidA, token=tokA, json={"sadrzaj": "recon marker"})
        with io.open(docx_od(io.open(FIX, encoding="utf-8").read()), "rb") as fh:
            up = Z("POST", "/api/predmeti/%s/upload" % pidA, token=tokA,
                   files={"file": ("ugovor.docx", fh,
                                   "application/vnd.openxmlformats-officedocument."
                                   "wordprocessingml.document")})
        izlaz["koraci"]["upload"] = up.status_code
        print("  upload http=%s" % up.status_code)
        if up.status_code != 200:
            N("RECON-UPLOAD", "RED", "Upload dokumenta ne radi", "HTTP %s" % up.status_code)

        # ── FAZA 4: B1 — rok EXTRACTED/PERSISTED/RETRIEVED ────────────────
        print("\n== FAZA 4: B1 rok ==")
        rr = Z("POST", "/api/predmeti/%s/confirm-links" % pidA, token=tokA, json={
            "klijent_ids": [],
            "dodaj_rok": {"naziv": ROK_NAZIV, "datum_iso": ROK_DATUM, "vaznost": "kritičan"}})
        jr = rr.json() if rr.status_code == 200 else {}
        izlaz["koraci"]["confirm_links"] = {"http": rr.status_code, "body": jr}
        print("  confirm-links http=%s success=%s rok_dodat=%s"
              % (rr.status_code, jr.get("success"), jr.get("rok_dodat")))
        hr = Z("GET", "/api/predmeti/%s/hronologija" % pidA, token=tokA)
        hj = hr.json() if hr.status_code == 200 else {}
        stavke = hj if isinstance(hj, list) else (hj.get("hronologija") or hj.get("stavke") or [])
        nasao = [x for x in stavke if ROK_NAZIV in json.dumps(x, ensure_ascii=False)]
        izlaz["koraci"]["hronologija"] = {"http": hr.status_code, "n": len(stavke),
                                          "rok_pronadjen": len(nasao)}
        print("  hronologija http=%s stavki=%d rok_pronadjen=%d" % (hr.status_code, len(stavke), len(nasao)))
        if jr.get("rok_dodat") is True and not nasao:
            N("B1-RECON", "RED", "rok_dodat=true ali rok NIJE u hronologiji",
              "confirm-links=%s, hronologija n=%d" % (jr, len(stavke)))
        elif jr.get("rok_dodat") is not True:
            N("B1-RECON", "YELLOW", "rok nije upisan; API to PRIZNAJE (rok_dodat != true)",
              json.dumps(jr, ensure_ascii=False)[:200])
        elif nasao:
            d = nasao[0]
            tacan = ROK_DATUM in json.dumps(d, ensure_ascii=False)
            print("  datum tacan: %s | %s" % (tacan, json.dumps(d, ensure_ascii=False)[:150]))
            if not tacan:
                N("B1-DATUM", "RED", "rok sacuvan sa POGRESNIM datumom",
                  json.dumps(d, ensure_ascii=False)[:200])

        # ── FAZA 9: cross-tenant ─────────────────────────────────────────
        print("\n== FAZA 9: tenant izolacija ==")
        probe = [
            ("READ predmet", "GET", "/api/predmeti/%s" % pidA, None),
            ("READ hronologija", "GET", "/api/predmeti/%s/hronologija" % pidA, None),
            ("WRITE beleska", "POST", "/api/predmeti/%s/beleske" % pidA, {"sadrzaj": "PROBOJ"}),
            ("WRITE confirm-links", "POST", "/api/predmeti/%s/confirm-links" % pidA,
             {"klijent_ids": [], "dodaj_rok": {"naziv": "PROBOJ", "datum_iso": "2027-01-01",
                                               "vaznost": "kritičan"}}),
            ("DELETE predmet", "DELETE", "/api/predmeti/%s" % pidA, None),
        ]
        izo = []
        for ime, m, put, body in probe:
            rp = Z(m, put, token=tokB, json=body) if body else Z(m, put, token=tokB)
            ok = rp.status_code in (401, 403, 404)
            izo.append({"probe": ime, "http": rp.status_code, "odbijeno": ok})
            print("  %-22s http=%-4s %s" % (ime, rp.status_code, "ODBIJENO" if ok else ">>> PROPUSTENO <<<"))
            if not ok:
                N("ISO-%s" % ime.split()[0], "RED", "Cross-tenant %s NIJE odbijen" % ime,
                  "HTTP %s telo=%s" % (rp.status_code, rp.text[:160]))
        izlaz["koraci"]["izolacija"] = izo

        # ── FAZA 5: B2 finansije ─────────────────────────────────────────
        print("\n== FAZA 5: B2 finansijski izvestaji ==")
        fin = []
        for put in ("/billing/report/godisnji", "/billing/report/po-klijentu",
                    "/billing/report/mesecni", "/billing/report/po-tipu"):
            rf = Z("GET", put, token=tokA)
            telo = rf.text[:200]
            fin.append({"put": put, "http": rf.status_code, "telo": telo})
            print("  %-32s http=%-4s %s" % (put, rf.status_code, telo[:90].replace("\n", " ")))
            if rf.status_code >= 500:
                N("B2-%s" % put.split("/")[-1], "YELLOW", "Finansijski izvestaj vraca 5xx",
                  "%s -> HTTP %s" % (put, rf.status_code))
        izlaz["koraci"]["billing"] = fin

        # ── FAZA 6: B3 glas ──────────────────────────────────────────────
        print("\n== FAZA 6: B3 glasovni put ==")
        rv = Z("POST", "/api/voice/command", token=tokA,
               json={"tekst": "Koji rokovi postoje u ovom predmetu?", "predmet_id": pidA})
        izlaz["koraci"]["voice"] = {"http": rv.status_code, "telo": rv.text[:300]}
        print("  voice/command http=%s" % rv.status_code)
        print("  telo: %s" % rv.text[:180].replace("\n", " "))
        if rv.status_code == 200:
            tv = rv.text.lower()
            tvrdi_nema = ("nema" in tv and "rok" in tv)
            if nasao and tvrdi_nema:
                N("B3-RECON", "RED", "Glas tvrdi da nema rokova, a rok POSTOJI u hronologiji",
                  rv.text[:200])

        # ── FAZA 7: B4 smoke ─────────────────────────────────────────────
        print("\n== FAZA 7: B4 smoke ==")
        smoke = []
        for ime, q in (("doc fact", "Koliko iznosi ugovorna kazna prema mom ugovoru?"),
                       ("blocked", "Sta propisuje clan 99987 Zakona o obligacionim odnosima "
                                   "i koliko iznosi ugovorna kazna prema mom ugovoru?")):
            rs = Z("POST", "/api/pitanje", token=tokA, json={"pitanje": q, "predmet_id": pidA})
            js = rs.json() if rs.status_code == 200 else {}
            c = js.get("cinjenice_iz_dokumenta") or []
            nav = " ".join(x.get("navod", "") for x in c)
            ok = NS.nadji_vrednost(NS.CINJENICE["A"]["iznos"], nav)
            smoke.append({"scenario": ime, "http": rs.status_code, "kanal": "cinjenice_iz_dokumenta" in js,
                          "fact": ok})
            print("  %-10s http=%-4s kanal=%-5s fact=%s" % (ime, rs.status_code, "cinjenice_iz_dokumenta" in js, ok))
            if rs.status_code == 200 and not ok:
                N("B4-REG-%s" % ime.split()[0], "RED", "B4-M2 REGRESIJA: cinjenica nestala (%s)" % ime,
                  json.dumps(js, ensure_ascii=False)[:200])
        izlaz["koraci"]["b4_smoke"] = smoke

        # ── FAZA 10: brisanje ────────────────────────────────────────────
        print("\n== FAZA 10: brisanje predmeta ==")
        rd = Z("DELETE", "/api/predmeti/%s" % pidA, token=tokA)
        posle = Z("GET", "/api/predmeti/%s" % pidA, token=tokA)
        red_db = supa.table("predmeti").select("id").eq("id", pidA).execute().data or []
        dok_db = supa.table("predmet_dokumenti").select("id").eq("predmet_id", pidA).execute().data or []
        hro_db = supa.table("predmet_hronologija").select("id").eq("predmet_id", pidA).execute().data or []
        izlaz["koraci"]["brisanje"] = {"delete_http": rd.status_code, "get_posle": posle.status_code,
                                       "predmeti": len(red_db), "dokumenti": len(dok_db),
                                       "hronologija": len(hro_db)}
        print("  DELETE http=%s | GET posle=%s | DB predmeti=%d dokumenti=%d hronologija=%d"
              % (rd.status_code, posle.status_code, len(red_db), len(dok_db), len(hro_db)))
        if rd.status_code == 200 and (red_db or dok_db or hro_db):
            N("DEL-RECON", "RED", "DELETE vratio 200 a redovi su ostali u bazi",
              "predmeti=%d dokumenti=%d hronologija=%d" % (len(red_db), len(dok_db), len(hro_db)))
        if rd.status_code == 200 and posle.status_code == 200:
            N("DEL-GET", "RED", "Predmet i dalje citljiv posle uspesnog DELETE",
              "GET http=200")
    finally:
        ciscenje = {}
        for pid, tok in stanje["predmeti"]:
            try:
                ciscenje["del_%s" % pid[:8]] = Z("DELETE", "/api/predmeti/%s" % pid, token=tok).status_code
            except Exception as e:                                  # noqa: BLE001
                ciscenje["del_%s" % pid[:8]] = str(type(e).__name__)
        for uid in (stanje["uidA"], stanje["uidB"]):
            for t, k in (("predmet_beleske", "user_id"), ("predmet_istorija", "user_id"),
                         ("predmet_hronologija", "user_id"), ("predmet_dokumenti", "user_id"),
                         ("predmeti", "user_id"), ("profiles", "id")):
                try:
                    supa.table(t).delete().eq(k, uid).execute()
                except Exception:                                   # noqa: BLE001
                    pass
            try:
                supa.auth.admin.delete_user(uid)
            except Exception as e:                                  # noqa: BLE001
                ciscenje["nalog_%s" % uid[:8]] = str(e)[:60]
        ciscenje["provera_predmeti_A"] = len(
            supa.table("predmeti").select("id").eq("user_id", stanje["uidA"]).execute().data or [])
        ciscenje["provera_predmeti_B"] = len(
            supa.table("predmeti").select("id").eq("user_id", stanje["uidB"]).execute().data or [])
        izlaz["ciscenje"] = ciscenje
        io.open(a.out, "w", encoding="utf-8").write(json.dumps(izlaz, ensure_ascii=False, indent=1))
        print("\nciscenje: %s" % json.dumps(ciscenje, ensure_ascii=False))
        print("upisano: %s" % a.out)

    print("\n== NALAZI: %d ==" % len(nalazi))
    for n in nalazi:
        print("  %-14s %-8s %s" % (n["id"], n["severity"], n["finding"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
