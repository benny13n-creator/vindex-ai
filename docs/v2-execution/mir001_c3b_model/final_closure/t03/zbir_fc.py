# -*- coding: utf-8 -*-
"""TASK-03 (FINAL CLOSURE) — zbir provera K po režimu. Upotreba: python -I -X utf8 zbir_fc.py replay|primeni"""
import glob
import json
import os
import sys
from collections import Counter

OVDE = os.path.dirname(os.path.abspath(__file__))
mod = sys.argv[1]
z = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(OVDE, mod, "*.json")))]
povrede, stat = [], Counter()
for x in z:
    ime = x.get("izlaz") or x.get("scenarij")
    stat["ukupno"] += 1
    stat[f"ruta_{x.get('ruta', 200)}"] += 1
    if x.get("odobrenje") == 200:
        stat["odobreno"] += 1
    else:
        stat["nije_odobreno"] += 1
        povrede.append((ime, "nije odobreno", x.get("razlozi_protiv_odobrenja")))
    if x.get("K4_fali_iz_sirovog"):
        povrede.append((ime, "K4 deo sirovog izlaza nedostaje u predlogu", x["K4_fali_iz_sirovog"][:3]))
    for k, v in (x.get("provere") or {}).items():
        if v is not True:
            povrede.append((ime, k, v))
    for k in ("A2_ubacena_je_ai_predlog", "A2_ubacena_nije_u_dokumentu"):
        if k in x:
            stat[k + ("_DA" if x[k] else "_NE")] += 1
            if x[k] is not True:
                povrede.append((ime, k, x[k]))
    if "pozivi_modela_posle" in x and (x["pozivi_modela_posle"] != x["pozivi_modela"] or x["naplate_posle"] != x["naplate"]):
        povrede.append((ime, "K7 usvajanje zvalo model ili naplatilo", [x["pozivi_modela"], x["pozivi_modela_posle"]]))
    stat["usvojeno_stavki"] += x.get("usvojeno", 0) or sum(1 for v in (x.get("odluke") or {}).values() if v == "USVOJENO")
    stat["odbaceno_stavki"] += x.get("odbaceno", 0) or sum(1 for v in (x.get("odluke") or {}).values() if v == "ODBACENO")
rez = {"rezim": mod, "statistika": dict(stat), "povrede": [{"izlaz": a, "provera": b, "detalj": c} for a, b, c in povrede]}
json.dump(rez, open(os.path.join(OVDE, f"zbir_{mod}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(rez["statistika"], ensure_ascii=False))
print("povreda:", len(povrede))
for p in povrede[:20]:
    print(p)
