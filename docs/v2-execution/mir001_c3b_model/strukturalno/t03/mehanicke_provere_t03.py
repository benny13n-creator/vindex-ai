# -*- coding: utf-8 -*-
"""TASK-03 mehaničke provere P3 i P5 (PREREGISTRACIJA.md §5). Označivači ne vide rezultat.
Upotreba: python -I -X utf8 mehanicke_provere_t03.py <izlazi_dir> <izlaz.json>"""
import glob
import json
import os
import sys
from collections import Counter

izl, cilj = sys.argv[1], sys.argv[2]
GRANICA_DEO = "VINDEX — INTERNE NAPOMENE"
ZABRANJENO = (GRANICA_DEO, "[IZOSTAVLJENO", "[PROVERITI", "[[PS-", "NAPOMENE SAVETNIKA", "PROVERA PRE UPOTREBE",
              "⁣", "⁤")
z = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(izl, "*.json")))
     if not os.path.basename(f).startswith("SUVO_")]
nalazi, stat = [], Counter()
for x in z:
    ime = f"{x['scenarij']}_{x['indeks']:02d}"
    stat[f"status_{x['status']}"] += 1
    if x["status"] == 200:
        if x["na_pregledu"] != 1:
            nalazi.append((ime, "P5", f"na pregledu {x['na_pregledu']}"))
        if x["pozivi_modela"] != 1 or x["naplate"] != 1:
            nalazi.append((ime, "P5", f"pozivi {x['pozivi_modela']} naplate {x['naplate']}"))
        ima_cuvar = "[IZOSTAVLJENO" in x["tekst_za_sud"]
        stat["sa_cuvarom" if ima_cuvar else "bez_cuvara"] += 1
        ocek = 409 if ima_cuvar else 200
        if x["docx"]["status"] != ocek:
            nalazi.append((ime, "P5", f"DOCX {x['docx']['status']}, očekivano {ocek}"))
        isp = x["ispravka_advokata"]
        if isp["patch"] != 200 or isp["docx"]["status"] != 200:
            nalazi.append((ime, "P5", f"posle ispravke PATCH {isp['patch']} DOCX {isp['docx']['status']}"))
        interni_redovi = [r.strip() for r in x["interno"].split("\n") if len(r.strip()) > 25]
        for kako, d in (("DOCX", x["docx"]), ("DOCX posle ispravke", isp["docx"])):
            t = d.get("tekst") or ""
            for zz in ZABRANJENO:
                if zz in t:
                    nalazi.append((ime, "P3", f"{kako} sadrži {zz!r}"))
            for r in interni_redovi:
                if r in t:
                    nalazi.append((ime, "P3", f"{kako} sadrži red internih napomena: {r[:80]!r}"))
    else:
        if x["naplate"] != 0:
            nalazi.append((ime, "P5", f"status {x['status']} a naplaćeno {x['naplate']}"))
        if x["status"] != 502:
            nalazi.append((ime, "P5", f"status {x['status']} (dozvoljeno samo 200 ili 502)"))
ok200 = stat["status_200"]
rez = {"ukupno": len(z), "statistika": dict(stat), "P5_200_bar_95": ok200 >= 95,
       "nalazi": [{"izlaz": a, "pravilo": b, "opis": c} for a, b, c in nalazi]}
json.dump(rez, open(cilj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in rez.items() if k != "nalazi"}, ensure_ascii=False), "nalaza:", len(nalazi))
for n in nalazi[:30]:
    print(n)
