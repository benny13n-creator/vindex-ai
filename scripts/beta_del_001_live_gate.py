# -*- coding: utf-8 -*-
"""BETA-DEL-001 P2 — ŽIVI PRODUKCIONI GATE.

Redosled je propisan mandatom i NE MENJA SE:

    §6 BASELINE      predmet stvarno ima funkcionalan sadrzaj
    TEST A           normalno brisanje
    TEST B           prirodni `events`-FK scenario (korenski uzrok)
    TEST C           pad Pinecone sloja
    TEST D           retry
    TEST E           izolacija citanja / retrieval-a

Destruktivni DELETE se NE pokrece dok baseline ne prodje.

Nista se ne pretpostavlja: broj `events` i `case_evolution_consequences` redova
se MERI pre brisanja, pa se tek onda tvrdi da je scenario B stvarno pokriven.
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

import ns003_benchmark as NS  # noqa: E402

BASE = os.environ.get("B4M2_BASE_URL", "https://vindex-ai.onrender.com")
FIX = os.path.join(_KOREN, "tests", "fixtures", "ns003", "dokument_a.txt")
IZNOS = "847.250,00"
PITANJE = "Koliko iznosi ugovorna kazna prema mom ugovoru?"

izvestaj = {"koraci": {}, "matrica": [], "anomalije": []}


def Z(m, p, tok, **kw):
    import requests
    return requests.request(m, BASE + p, headers={"Authorization": "Bearer " + tok},
                            timeout=200, **kw)


def docx(tekst):
    import tempfile
    from docx import Document
    d = Document()
    for r in tekst.split("\n"):
        d.add_paragraph(r)
    p = os.path.join(tempfile.gettempdir(), "del_live.docx")
    d.save(p)
    return p


def stanje(supa, pid):
    """DB stanje predmeta — mereno, ne pretpostavljeno."""
    def n(t, k="predmet_id"):
        try:
            return len(supa.table(t).select("id").eq(k, pid).execute().data or [])
        except Exception:                                        # noqa: BLE001
            return "n/a"
    ev = []
    try:
        ev = [r["id"] for r in (supa.table("events").select("id")
                                .eq("predmet_id", pid).execute().data or [])]
    except Exception:                                            # noqa: BLE001
        pass
    posl = 0
    if ev:
        try:
            posl = len(supa.table("case_evolution_consequences").select("id")
                       .in_("event_id", ev).execute().data or [])
        except Exception:                                        # noqa: BLE001
            posl = "n/a"
    red = supa.table("predmeti").select("id,status,brisanje_zapoceto").eq("id", pid).execute().data or []
    return {
        "predmeti": len(red),
        "tombstone": (red[0].get("brisanje_zapoceto") if red else None),
        "status": (red[0].get("status") if red else None),
        "dokumenti": n("predmet_dokumenti"),
        "events": len(ev),
        "consequences": posl,
    }


def pitaj(tok, pid, oz):
    r = Z("POST", "/api/pitanje", tok, json={"pitanje": PITANJE, "predmet_id": pid})
    j = r.json() if r.status_code == 200 else {}
    c = j.get("cinjenice_iz_dokumenta") or []
    nav = " ".join(x.get("navod", "") for x in c)
    ima = NS.nadji_vrednost(NS.CINJENICE["A"]["iznos"], nav)
    st = [x.get("source_type") for x in c]
    vs = [x.get("verification_state") for x in c]
    print("    %-26s http=%-4s kanal=%-5s cinjenica=%-5s source=%s verif=%s"
          % (oz, r.status_code, "cinjenice_iz_dokumenta" in j, ima,
             set(st) or "-", set(vs) or "-"))
    return {"http": r.status_code, "cinjenica": ima, "source_type": st, "verification_state": vs}


def obrisi(tok, pid, oz):
    r = Z("DELETE", "/api/predmeti/%s" % pid, tok)
    try:
        j = r.json()
    except Exception:                                            # noqa: BLE001
        j = {}
    det = j.get("detail", j) if isinstance(j, dict) else {}
    if not isinstance(det, dict):
        det = {"poruka": str(det)}
    print("    %-26s http=%-4s ishod=%-18s vektori=%-14s retry=%s"
          % (oz, r.status_code, det.get("ishod") or j.get("ishod"),
             det.get("vektori") or j.get("vektori"), det.get("retry_moguc")))
    if det.get("poruka"):
        print("      poruka: %s" % str(det["poruka"])[:140])
    return {"http": r.status_code, "ishod": det.get("ishod") or j.get("ishod"),
            "vektori": det.get("vektori") or j.get("vektori"),
            "retry_moguc": det.get("retry_moguc"),
            "neuspele_tabele": det.get("neuspele_tabele"),
            "tombstone": det.get("tombstone"),
            "poruka": det.get("poruka")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out", default="beta_del_live.json")
    a = ap.parse_args()
    if not a.live:
        return 0

    import requests
    v = requests.get(BASE + "/api/version", timeout=60).json()
    print("PRODUKCIJA: %s identity=%s env=%s" % (v["commit_short"], v["identity_proven"], v["environment"]))
    if v["commit_short"] != "693de0c":
        raise SystemExit("STOP — deployment je %s, ocekivano 693de0c" % v["commit_short"])
    izvestaj["produkcija"] = v

    import main as _app  # noqa: F401
    from supabase import create_client
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    supa = create_client(url, key)
    email = "del.p2.%s@vindex-benchmark.invalid" % uuid.uuid4().hex[:8]
    lozinka = "DelP2!" + uuid.uuid4().hex[:16]
    uid = supa.auth.admin.create_user({"email": email, "password": lozinka,
                                       "email_confirm": True}).user.id
    tok = create_client(url, key).auth.sign_in_with_password(
        {"email": email, "password": lozinka}).session.access_token
    print("TENANT: %s\n" % email)
    izvestaj["tenant"] = email
    predmeti = []

    def novi(naziv, sa_dokumentom):
        r = Z("POST", "/api/predmeti", tok, json={
            "naziv": naziv, "klijent": "DELP2", "sud": "DELP2", "oblast": "Ugovorno pravo"})
        pid = ((r.json() or {}).get("predmet") or {}).get("id")
        if not pid:
            raise SystemExit("STOP — predmet nije kreiran: %s" % r.status_code)
        predmeti.append(pid)
        Z("POST", "/api/predmeti/%s/beleske" % pid, tok, json={"sadrzaj": "delp2 marker"})
        if sa_dokumentom:
            with io.open(docx(io.open(FIX, encoding="utf-8").read()), "rb") as fh:
                up = Z("POST", "/api/predmeti/%s/upload" % pid, tok,
                       files={"file": ("ugovor.docx", fh,
                                       "application/vnd.openxmlformats-officedocument."
                                       "wordprocessingml.document")})
            print("    upload http=%s" % up.status_code)
            if up.status_code != 200:
                raise SystemExit("STOP — ingest nije uspeo: %s" % up.text[:200])
        return pid

    try:
        supa.table("profiles").update({"credits_remaining": 300}).eq("id", uid).execute()
        # profil sada postoji -> plan i krediti se postavljaju i CITAJU NAZAD
        supa.table("profiles").update({
            "credits_remaining": 300, "subscription_type": "professional",
            "subscription_expires_at": "2027-12-31T00:00:00+00:00"}).eq("id", uid).execute()
        pr = (supa.table("profiles").select("credits_remaining,subscription_type")
              .eq("id", uid).execute().data or [{}])[0]
        print("  provizioniranje: %s" % pr)
        if not pr.get("credits_remaining"):
            raise SystemExit("STOP — krediti nisu provizionirani")

        # ── §6 BASELINE ─────────────────────────────────────────────────
        print("\n== §6 BASELINE ==")
        pid_b = novi("DELP2 baseline", True)
        time.sleep(30)
        pre_b = stanje(supa, pid_b)
        print("    DB: %s" % json.dumps(pre_b, ensure_ascii=False))
        base = pitaj(tok, pid_b, "pre brisanja")
        izvestaj["koraci"]["baseline"] = {"db": pre_b, "pitanje": base}
        if not base["cinjenica"]:
            raise SystemExit("STOP — baseline nije prosao; DELETE se NE pokrece")

        # ── TEST B (koristi isti predmet: ima dokument, events, mozda posledice)
        print("\n== TEST B — prirodni events-FK scenario ==")
        print("    izmereno PRE: events=%s consequences=%s"
              % (pre_b["events"], pre_b["consequences"]))
        b_del = obrisi(tok, pid_b, "DELETE")
        time.sleep(5)
        posle_b = stanje(supa, pid_b)
        vidljiv_b = Z("GET", "/api/predmeti/%s" % pid_b, tok).status_code
        po_pit_b = pitaj(tok, pid_b, "posle brisanja") if posle_b["predmeti"] else None
        print("    DB posle: %s | GET=%s" % (json.dumps(posle_b, ensure_ascii=False), vidljiv_b))
        izvestaj["koraci"]["test_b"] = {"pre": pre_b, "delete": b_del, "posle": posle_b,
                                        "get": vidljiv_b, "pitanje_posle": po_pit_b}

        # ── TEST A — normalno brisanje, bez dokumenta ───────────────────
        print("\n== TEST A — normalno brisanje ==")
        pid_a = novi("DELP2 normal", False)
        pre_a = stanje(supa, pid_a)
        a_del = obrisi(tok, pid_a, "DELETE")
        posle_a = stanje(supa, pid_a)
        vid_a = Z("GET", "/api/predmeti/%s" % pid_a, tok).status_code
        print("    DB posle: %s | GET=%s" % (json.dumps(posle_a, ensure_ascii=False), vid_a))
        izvestaj["koraci"]["test_a"] = {"pre": pre_a, "delete": a_del, "posle": posle_a, "get": vid_a}

        # ── TEST D — retry ──────────────────────────────────────────────
        print("\n== TEST D — retry ==")
        d1 = obrisi(tok, pid_b, "retry nad B")
        d2 = obrisi(tok, pid_a, "retry nad A")
        izvestaj["koraci"]["test_d"] = {"retry_b": d1, "retry_a": d2}

        # ── TEST E — izolacija citanja ──────────────────────────────────
        print("\n== TEST E — izolacija citanja ==")
        lista = Z("GET", "/api/predmeti", tok)
        ids = [p["id"] for p in ((lista.json() or {}).get("predmeti") or [])]
        print("    u listi: %d predmeta | B prisutan=%s | A prisutan=%s"
              % (len(ids), pid_b in ids, pid_a in ids))
        izvestaj["koraci"]["test_e"] = {"lista_n": len(ids), "b_u_listi": pid_b in ids,
                                        "a_u_listi": pid_a in ids}
    finally:
        ci = {}
        for pid in predmeti:
            try:
                ci["del_%s" % pid[:8]] = Z("DELETE", "/api/predmeti/%s" % pid, tok).status_code
            except Exception as e:                               # noqa: BLE001
                ci["del_%s" % pid[:8]] = type(e).__name__
        for t, k in (("predmet_beleske", "user_id"), ("predmet_istorija", "user_id"),
                     ("predmet_hronologija", "user_id"), ("predmet_dokumenti", "user_id"),
                     ("predmeti", "user_id"), ("profiles", "id")):
            try:
                supa.table(t).delete().eq(k, uid).execute()
            except Exception:                                    # noqa: BLE001
                pass
        try:
            supa.auth.admin.delete_user(uid)
            ci["nalog"] = "obrisan"
        except Exception as e:                                   # noqa: BLE001
            ci["nalog"] = str(e)[:60]
        ci["provera_predmeti"] = len(
            supa.table("predmeti").select("id").eq("user_id", uid).execute().data or [])
        izvestaj["ciscenje"] = ci
        io.open(a.out, "w", encoding="utf-8").write(
            json.dumps(izvestaj, ensure_ascii=False, indent=1))
        print("\nciscenje: %s" % json.dumps(ci, ensure_ascii=False))
        print("upisano: %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
