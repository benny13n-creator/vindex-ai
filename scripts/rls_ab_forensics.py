# -*- coding: utf-8 -*-
"""
RLS-AB-001 — A/B IZOLACIJA nad `public.reported_errors`, STVARNIM identitetima.

METOD (isti koji aplikacija koristi, bez izmisljanja):
  1. `POST /auth/v1/admin/users`  (service_role)  -> dva throwaway naloga
  2. `POST /auth/v1/token?grant_type=password` (publishable) -> STVARNI JWT
  3. `GET  /auth/v1/user` -> potvrda da token pripada bas tom `id`
  4. PostgREST pozivi sa tim JWT-om -> `auth.uid()` je taj korisnik

NIJEDAN korak ne kuje token i ne koristi `service_role` kao A ili B.
`service_role` se koristi ISKLJUCIVO za pripremu, verifikaciju stanja i
ciscenje -- nikad kao dokaz izolacije.

CISCENJE je u `finally` i uvek se izvrsava.

UPOZORENJE — OVAJ ALAT DODIRUJE PRODUKCIJU
  * kreira i BRISE dva throwaway naloga u `auth.users`
  * upisuje i BRISE redove u `reported_errors`
Zato trazi izricitu potvrdu kroz promenljivu okruzenja:

    RLS_AB_FORENSICS=DA python scripts/rls_ab_forensics.py

Bez nje odbija da se pokrene. Nikad ne dira postojece korisnike ni podatke.
"""
import io
import json
import os
import re
import urllib.error
import urllib.request
import uuid

from dotenv import load_dotenv

load_dotenv(".env")
URL = os.environ["SUPABASE_URL"].rstrip("/")
SVC = os.environ["SUPABASE_SERVICE_KEY"]
PUB = re.search(r"var SUPABASE_ANON_KEY = '([^']+)'",
                io.open("static/vindex.js", encoding="utf-8").read()).group(1)

ZIG = uuid.uuid4().hex[:10]
MARK_A = "RLS_AB_PROBE_A_" + ZIG
MARK_B = "RLS_AB_PROBE_B_" + ZIG
EMAIL_A = "rls-probe-a-%s@vindex-test.invalid" % ZIG
EMAIL_B = "rls-probe-b-%s@vindex-test.invalid" % ZIG
LOZ = "Probna-" + uuid.uuid4().hex


def http(metod, put, apikey, token=None, telo=None, prefer=None):
    h = {"apikey": apikey, "Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if prefer:
        h["Prefer"] = prefer
    d = json.dumps(telo).encode() if telo is not None else None
    r = urllib.request.Request(URL + put, data=d, headers=h, method=metod)
    try:
        with urllib.request.urlopen(r, timeout=30) as o:
            return o.status, o.headers.get("Content-Range"), o.read(3000).decode()
    except urllib.error.HTTPError as e:
        return e.code, None, e.read(1200).decode()


def kod(t):
    try:
        return json.loads(t).get("code", "")
    except Exception:
        return ""


def nas(x):
    print("\n" + "=" * 74 + "\n" + x + "\n" + "=" * 74)


def rez(ime, uslov, detalj=""):
    print("  %-46s %s %s" % (ime, "BLOKIRAN" if uslov else ">>> PROPUSTIO <<<", detalj))
    return uslov


if os.getenv("RLS_AB_FORENSICS", "").strip().upper() not in ("DA", "YES", "1"):
    print("ODBIJENO: ovaj alat kreira i brise produkcione naloge.")
    print("Pokreni svesno:  RLS_AB_FORENSICS=DA python scripts/rls_ab_forensics.py")
    raise SystemExit(2)

A_ID = B_ID = None
ROW_A = ROW_B = None
ishodi = {}

try:
    # ── PRIPREMA ─────────────────────────────────────────────────────────────
    nas("0. PRIPREMA — dva throwaway naloga (service_role, samo priprema)")
    s, _, t = http("GET", "/rest/v1/profiles?select=id&limit=0", SVC, SVC,
                   prefer="count=exact")
    print("  profiles PRE:", _)
    prof_pre = _

    for ime, mail in (("A", EMAIL_A), ("B", EMAIL_B)):
        s, _, t = http("POST", "/auth/v1/admin/users", SVC, SVC,
                       {"email": mail, "password": LOZ, "email_confirm": True})
        if s not in (200, 201):
            print("  KREIRANJE %s NEUSPESNO: HTTP %s %s" % (ime, s, t[:300]))
            raise SystemExit(1)
        uid = json.loads(t)["id"]
        print("  USER_%s  id=%s  email=%s" % (ime, uid, mail))
        if ime == "A":
            A_ID = uid
        else:
            B_ID = uid

    print("  A != B :", A_ID != B_ID)

    # ── STVARNE SESIJE ───────────────────────────────────────────────────────
    nas("1. STVARNE AUTH SESIJE (publishable kljuc, grant_type=password)")
    tok = {}
    for ime, mail, uid in (("A", EMAIL_A, A_ID), ("B", EMAIL_B, B_ID)):
        s, _, t = http("POST", "/auth/v1/token?grant_type=password", PUB, None,
                       {"email": mail, "password": LOZ})
        if s != 200:
            print("  PRIJAVA %s NEUSPESNA: HTTP %s %s" % (ime, s, t[:300]))
            raise SystemExit(1)
        tok[ime] = json.loads(t)["access_token"]
        # TASK 13 — potvrda da token STVARNO pripada tom identitetu
        s2, _, t2 = http("GET", "/auth/v1/user", PUB, tok[ime])
        vraceni = json.loads(t2).get("id")
        print("  %s: token dobijen, /auth/v1/user id=%s  poklapa se: %s"
              % (ime, vraceni, vraceni == uid))
        ishodi["identitet_" + ime] = (vraceni == uid)
    print("  token A == token B :", tok["A"] == tok["B"], "(mora biti False)")
    ishodi["razliciti_tokeni"] = tok["A"] != tok["B"]

    A, B = tok["A"], tok["B"]

    # ── KONTROLNI REDOVI ─────────────────────────────────────────────────────
    nas("2. KONTROLNI REDOVI — svaki korisnik upisuje SVOJ (pozitivna kontrola)")
    for ime, t_, uid, mark in (("A", A, A_ID, MARK_A), ("B", B, B_ID, MARK_B)):
        s, _, t = http("POST", "/rest/v1/reported_errors", PUB, t_,
                       [{"user_id": uid, "original_prompt": mark,
                         "ai_response": "netaknuto"}],
                       prefer="return=representation")
        print("  %s upisuje SVOJ red: HTTP %-4s %s" % (ime, s, t[:220]))
        ishodi["insert_svoj_" + ime] = s in (200, 201)

    # id-jeve citamo service_role-om (verifikacioni kanal, ne dokaz)
    s, _, t = http("GET", "/rest/v1/reported_errors?select=id,user_id,original_prompt,ai_response",
                   SVC, SVC)
    redovi = json.loads(t)
    for r in redovi:
        if r["original_prompt"] == MARK_A:
            ROW_A = r["id"]
        if r["original_prompt"] == MARK_B:
            ROW_B = r["id"]
    print("  ROW_A =", ROW_A, " ROW_B =", ROW_B)
    if not (ROW_A and ROW_B):
        print("  Korisnici NE MOGU da upisu ni sopstveni red -> deklarisana")
        print("  INSERT politika `auth.uid() = user_id` NIJE na snazi.")
        print("  Eksperiment se nastavlja: redove pravi service_role kao PRIPREMU,")
        print("  sa STVARNIM vlasnistvom (user_id = A odnosno B). Pristup i dalje")
        print("  testiraju iskljucivo A i B svojim pravim tokenima.")
        for uid, mark in ((A_ID, MARK_A), (B_ID, MARK_B)):
            s2, _, t2 = http("POST", "/rest/v1/reported_errors", SVC, SVC,
                             [{"user_id": uid, "original_prompt": mark,
                               "ai_response": "netaknuto"}],
                             prefer="return=representation")
            if s2 in (200, 201):
                rid = json.loads(t2)[0]["id"]
                if mark == MARK_A:
                    ROW_A = rid
                else:
                    ROW_B = rid
        print("  ROW_A =", ROW_A, " ROW_B =", ROW_B)
    if not (ROW_A and ROW_B):
        print("  >>> Ni priprema nije uspela. PREKIDAM.")
        raise SystemExit(1)

    # ── UGOVOR CITANJA ───────────────────────────────────────────────────────
    nas("3. UGOVOR CITANJA — sme li korisnik da vidi SOPSTVENI red?")
    print("  Deklarisana SELECT politika: samo `service_role`.")
    print("  Dakle ocekivano je da NI VLASNIK ne cita -- proizvod je WRITE-ONLY.")
    for ime, t_ in (("A", A), ("B", B)):
        s, rng, t = http("GET", "/rest/v1/reported_errors?select=*", PUB, t_,
                         prefer="count=exact")
        print("  %s cita SVOJE: HTTP %-4s count=%-6s telo=%s" % (ime, s, rng, t[:60]))
        ishodi["cita_svoj_" + ime] = (t.strip() != "[]")

    # ── A -> B ───────────────────────────────────────────────────────────────
    nas("4. A -> B  (SELECT / UPDATE / DELETE / INSERT)")
    s, rng, t = http("GET", "/rest/v1/reported_errors?select=*&id=eq." + ROW_B,
                     PUB, A, prefer="count=exact")
    ishodi["A_select_B"] = rez("A SELECT po tacnom id reda B", MARK_B not in t,
                               "HTTP %s count=%s" % (s, rng))
    s, rng, t = http("GET", "/rest/v1/reported_errors?select=*&user_id=eq." + B_ID,
                     PUB, A, prefer="count=exact")
    ishodi["A_select_B_filter"] = rez("A SELECT filtriran po user_id B", MARK_B not in t,
                                      "HTTP %s count=%s" % (s, rng))
    s, rng, t = http("GET", "/rest/v1/reported_errors?select=*", PUB, A,
                     prefer="count=exact")
    ishodi["A_select_sve"] = rez("A SELECT bez filtera", MARK_B not in t,
                                 "HTTP %s count=%s" % (s, rng))

    http("PATCH", "/rest/v1/reported_errors?id=eq." + ROW_B, PUB, A,
         {"ai_response": "RLS_AB_ATTACKED_BY_A"})
    s, _, t = http("GET", "/rest/v1/reported_errors?select=ai_response&id=eq." + ROW_B,
                   SVC, SVC)
    stanje = json.loads(t)[0]["ai_response"] if json.loads(t) else "<nema>"
    ishodi["A_update_B"] = rez("A UPDATE reda B", stanje == "netaknuto",
                               "stvarno stanje=%r" % stanje)

    http("DELETE", "/rest/v1/reported_errors?id=eq." + ROW_B, PUB, A)
    s, _, t = http("GET", "/rest/v1/reported_errors?select=id&id=eq." + ROW_B, SVC, SVC)
    ishodi["A_delete_B"] = rez("A DELETE reda B", bool(json.loads(t)),
                               "red postoji=%s" % bool(json.loads(t)))

    s, _, t = http("POST", "/rest/v1/reported_errors", PUB, A,
                   [{"user_id": B_ID, "original_prompt": "KOVANO_OD_A",
                     "ai_response": "x"}], prefer="return=representation")
    s2, _, t2 = http("GET", "/rest/v1/reported_errors?select=id&original_prompt=eq.KOVANO_OD_A",
                     SVC, SVC)
    ishodi["A_insert_kao_B"] = rez("A INSERT sa user_id=B (kovanje vlasnistva)",
                                   not json.loads(t2),
                                   "HTTP %s %s" % (s, kod(t)))

    # ── B -> A ───────────────────────────────────────────────────────────────
    nas("5. B -> A  (SELECT / UPDATE / DELETE / INSERT)")
    s, rng, t = http("GET", "/rest/v1/reported_errors?select=*&id=eq." + ROW_A,
                     PUB, B, prefer="count=exact")
    ishodi["B_select_A"] = rez("B SELECT po tacnom id reda A", MARK_A not in t,
                               "HTTP %s count=%s" % (s, rng))
    s, rng, t = http("GET", "/rest/v1/reported_errors?select=*&user_id=eq." + A_ID,
                     PUB, B, prefer="count=exact")
    ishodi["B_select_A_filter"] = rez("B SELECT filtriran po user_id A", MARK_A not in t,
                                      "HTTP %s count=%s" % (s, rng))

    http("PATCH", "/rest/v1/reported_errors?id=eq." + ROW_A, PUB, B,
         {"ai_response": "RLS_AB_ATTACKED_BY_B"})
    s, _, t = http("GET", "/rest/v1/reported_errors?select=ai_response&id=eq." + ROW_A,
                   SVC, SVC)
    stanje = json.loads(t)[0]["ai_response"] if json.loads(t) else "<nema>"
    ishodi["B_update_A"] = rez("B UPDATE reda A", stanje == "netaknuto",
                               "stvarno stanje=%r" % stanje)

    http("DELETE", "/rest/v1/reported_errors?id=eq." + ROW_A, PUB, B)
    s, _, t = http("GET", "/rest/v1/reported_errors?select=id&id=eq." + ROW_A, SVC, SVC)
    ishodi["B_delete_A"] = rez("B DELETE reda A", bool(json.loads(t)),
                               "red postoji=%s" % bool(json.loads(t)))

    s, _, t = http("POST", "/rest/v1/reported_errors", PUB, B,
                   [{"user_id": A_ID, "original_prompt": "KOVANO_OD_B",
                     "ai_response": "x"}], prefer="return=representation")
    s2, _, t2 = http("GET", "/rest/v1/reported_errors?select=id&original_prompt=eq.KOVANO_OD_B",
                     SVC, SVC)
    ishodi["B_insert_kao_A"] = rez("B INSERT sa user_id=A (kovanje vlasnistva)",
                                   not json.loads(t2),
                                   "HTTP %s %s" % (s, kod(t)))

    # ── INFORMACIONO CURENJE ─────────────────────────────────────────────────
    nas("6. INFORMACIONO CURENJE — postojeci tudji id vs nepostojeci id")
    s1, r1, t1 = http("GET", "/rest/v1/reported_errors?select=*&id=eq." + ROW_B,
                      PUB, A, prefer="count=exact")
    s2, r2, t2 = http("GET", "/rest/v1/reported_errors?select=*&id=eq." + str(uuid.uuid4()),
                      PUB, A, prefer="count=exact")
    print("  A -> POSTOJECI tudji id : HTTP %s count=%s telo=%s" % (s1, r1, t1[:40]))
    print("  A -> NEPOSTOJECI id     : HTTP %s count=%s telo=%s" % (s2, r2, t2[:40]))
    ishodi["nema_curenja"] = (s1 == s2 and t1 == t2 and r1 == r2)
    print("  identicno u statusu, telu i count-u:", ishodi["nema_curenja"])

finally:
    # ── CISCENJE ─────────────────────────────────────────────────────────────
    nas("7. CISCENJE (service_role — samo ciscenje, nije dokaz)")
    for m in (MARK_A, MARK_B, "KOVANO_OD_A", "KOVANO_OD_B"):
        http("DELETE", "/rest/v1/reported_errors?original_prompt=eq." + m, SVC, SVC)
    for ime, uid in (("A", A_ID), ("B", B_ID)):
        if uid:
            s, _, t = http("DELETE", "/auth/v1/admin/users/" + uid, SVC, SVC)
            print("  brisanje USER_%s: HTTP %s" % (ime, s))

    s, rng, t = http("GET", "/rest/v1/reported_errors?select=id&limit=0", SVC, SVC,
                     prefer="count=exact")
    print("  reported_errors POSLE: count=%s" % rng)
    s, rng2, t = http("GET", "/rest/v1/profiles?select=id&limit=0", SVC, SVC,
                      prefer="count=exact")
    print("  profiles POSLE: %s" % rng2)
    for ime, uid in (("A", A_ID), ("B", B_ID)):
        if uid:
            s, _, t = http("GET", "/auth/v1/admin/users/" + uid, SVC, SVC)
            print("  USER_%s i dalje postoji: %s (HTTP %s)" % (ime, s == 200, s))

    nas("8. REZIME")
    for k, v in ishodi.items():
        print("  %-24s %s" % (k, "OK" if v else ">>> PAO <<<"))
