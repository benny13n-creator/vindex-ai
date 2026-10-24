# -*- coding: utf-8 -*-
"""TASK-03 spajanje oznaka dva označivača sa ključem (posle završene slepe ocene).
Za recenzenta GATE-03 piše listu svih prijavljenih nalaza (bilo koji označivač). Prema prethodnoj registraciji, nalaz je
potvrđen dok ga recenzent ne opovrgne. Ovaj skript ne odlučuje o spornim nalazima.
Upotreba: python -I -X utf8 spoji_t03.py <slepo_dir> <kljuc.json> <izlazi_dir> <izlaz.json>"""
import json
import os
import sys
from collections import Counter, defaultdict

slepo, kljuc_f, izl, cilj = sys.argv[1:5]
kljuc = json.load(open(kljuc_f, encoding="utf-8"))
oznake = {}
for o in ("A", "B"):
    oznake[o] = {}
    for d in range(1, 5):
        f = os.path.join(slepo, f"oznacivac_{o}", f"deo{d}", "oznake.json")
        oznake[o].update(json.load(open(f, encoding="utf-8"))["nacrti"])
    nedostaje = set(kljuc) - set(oznake[o])
    assert not nedostaje, (o, sorted(nedostaje))

MAT = ("M1", "M2", "M3", "M4", "M5", "M7", "M8")
nalazi, po_sc = [], defaultdict(Counter)
for sifra, k in sorted(kljuc.items(), key=lambda x: (x[1]["scenarij"], x[1]["indeks"])):
    sc = k["scenarij"]
    z = json.load(open(os.path.join(izl, f"{sc}_{k['indeks']:02d}.json"), encoding="utf-8"))
    po_sc[sc]["n"] += 1
    for o in ("A", "B"):
        x = oznake[o][sifra]
        for m in MAT:
            if str(x.get(m, "")).upper().startswith("DA"):
                po_sc[sc][f"{m}_{o}"] += 1
                citat = x.get(f"{m}_citat", "")
                nalazi.append({"sifra": sifra, "izlaz": f"{sc}_{k['indeks']:02d}", "scenarij": sc, "oznacivac": o,
                               "merilo": m, "citat": citat, "obrazlozenje": x.get(f"{m}_obrazlozenje", ""),
                               "citat_u_tekstu_za_sud": bool(citat) and all(c.strip().strip("„“\"") in z["tekst_za_sud"]
                                                                            for c in citat.split(" || ") if c.strip())})
        if str(x.get("M6", "")).upper().startswith("DA"):
            po_sc[sc][f"M6_{o}"] += 1
            nalazi.append({"sifra": sifra, "izlaz": f"{sc}_{k['indeks']:02d}", "scenarij": sc, "oznacivac": o,
                           "merilo": "M6", "citat": x.get("M6_citati", []), "obrazlozenje": x.get("M6_obrazlozenje", "")})
        if str(x.get("O2", "")).upper().startswith("DA"):
            po_sc[sc][f"O2_{o}"] += 1
        try:
            po_sc[sc][f"Q_{o}"] += float(x.get("Q") or 0)
        except (TypeError, ValueError):
            pass
pregled = {sc: dict(c) for sc, c in sorted(po_sc.items())}
json.dump({"po_scenariju": pregled, "nalazi": nalazi}, open(cilj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for sc, c in pregled.items():
    print(sc, {kk: v for kk, v in c.items() if not kk.startswith("Q_")},
          "Q_A=%.2f Q_B=%.2f" % (c.get("Q_A", 0) / c["n"], c.get("Q_B", 0) / c["n"]))
print("nalaza ukupno:", len(nalazi), Counter(n["merilo"] for n in nalazi))
