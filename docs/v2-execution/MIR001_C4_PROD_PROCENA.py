# -*- coding: utf-8 -*-
"""MIR001 C4 — READ-ONLY procena (samo GET, sa straničenjem) šta prvo usklađivanje posle puštanja zatvara (TASK-07
ogr. 9): (a) otvorene LEGACY radnje protivrečnosti na predmetima sa V2 spornim tačkama; (b) otvorene radnje pregleda
roka (`PLANIRATI_ROKOVE`, `dokaz.izvor = predmet_hronologija`) čiji red hronologije ispunjava pravilo `izvor_povucen`
(shared/rokovi.py: akter „Genome (AI)“, `dokument_naziv` postoji, `dokument_id` NULL, a dokumenta tog naziva u predmetu
više nema). Čita samo oznake, tip, akter i nazive fajlova — bez teksta. Ne ispisuje ključeve ni oznake predmeta.
Upotreba: python -I -X utf8 MIR001_C4_PROD_PROCENA.py"""
import os
import json
import urllib.parse
import urllib.request

env = {}
for l in open(os.environ.get("VINDEX_ENV_FILE", ".env"), encoding="utf-8"):
    if "=" in l and not l.lstrip().startswith("#"):
        k, v = l.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
URL, KEY = env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_SERVICE_KEY"]
AKTER_GENOME = "Genome (AI)"


def get(putanja):
    out, od = [], 0
    while True:
        req = urllib.request.Request(f"{URL}/rest/v1/{putanja}", method="GET",
                                     headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                                              "Range-Unit": "items", "Range": f"{od}-{od + 999}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        out += d
        if len(d) < 1000:
            return out
        od += 1000


akc = get("case_actions?select=predmet_id,tip,dedupe_key,izvor:dokaz->>izvor,hid:dokaz->>hronologija_id&status=eq.open")
v2 = {r["predmet_id"] for r in get("predmet_issues?select=predmet_id")}
kon = [a for a in akc if a["tip"] == "RAZRESITI_KONTRADIKCIJU"]
legacy_v2 = [a for a in kon if not a["dedupe_key"].startswith("v2:") and a["predmet_id"] in v2]
print("(a) otvorene protivrecnosti:", len(kon), "| legacy:", sum(not a["dedupe_key"].startswith("v2:") for a in kon),
      "| legacy na predmetu sa V2 (zatvaraju se):", len(legacy_v2), "| predmeta sa V2:", len(v2))

rok = [a for a in akc if a["tip"] == "PLANIRATI_ROKOVE" and a.get("izvor") == "predmet_hronologija" and a.get("hid")]
povucen = 0
if rok:
    hid = sorted({a["hid"] for a in rok})
    redovi = {}
    for i in range(0, len(hid), 100):
        lista = ",".join(hid[i:i + 100])
        for h in get(f"predmet_hronologija?select=id,predmet_id,akter,dokument_naziv,dokument_id&id=in.({lista})"):
            redovi[str(h["id"])] = h
    pids = sorted({a["predmet_id"] for a in rok})
    nazivi = {}
    for i in range(0, len(pids), 100):
        lista = ",".join(urllib.parse.quote(p) for p in pids[i:i + 100])
        for d in get(f"predmet_dokumenti?select=predmet_id,naziv_fajla&predmet_id=in.({lista})"):
            nazivi.setdefault(d["predmet_id"], set()).add(d.get("naziv_fajla"))
    for a in rok:
        h = redovi.get(str(a["hid"]))
        if h is None:
            continue                                                   # red hronologije ne postoji: Rule 6 ga ne cilja
        if (h.get("akter") == AKTER_GENOME and h.get("dokument_naziv") and not h.get("dokument_id")
                and h["dokument_naziv"] not in nazivi.get(a["predmet_id"], set())):
            povucen += 1
print("(b) otvorene radnje pregleda roka:", len(rok), "| izvor povucen (zatvaraju se):", povucen,
      "| ostale PLANIRATI_ROKOVE:", sum(1 for a in akc if a["tip"] == "PLANIRATI_ROKOVE") - len(rok))
