# -*- coding: utf-8 -*-
"""TASK-03: spoj slepih oznaka (3 dela) sa ključem; brojevi po grupi i scenariju; slaganje na preklopu;
pokrivenost: da li je sporna rečenica (citat O1/S) označena automatskom proverom (`provera_t03.json`)."""
import json
import re
import sys
from collections import Counter, defaultdict

T = sys.argv[1].rstrip("/\\") + "/"
kljuc = json.load(open(T + "slepo_KLJUC.json", encoding="utf-8"))
oznake = defaultdict(list)                       # sifra -> [labels...]
for d in (1, 2, 3):
    o = json.load(open(T + f"oznake_deo{d}.json", encoding="utf-8"))
    for s, x in o["nacrti"].items():
        oznake[s].append(dict(x, _deo=d))
assert set(oznake) == set(kljuc), (len(oznake), len(kljuc))
provera = json.load(open(T + "provera_t03.json", encoding="utf-8"))
izlazi = {}
for k in provera:
    izlazi[k] = json.load(open(T + f"r/{k}.json", encoding="utf-8"))["N"]

norm = lambda s: re.sub(r"\W+", " ", (s or "").lower()).strip()
DA = lambda v: str(v).upper().startswith("DA")


def kombinuj(lista, polje):
    """Preklop: konzervativno — DA ako bilo koji označivač kaže DA (GRANICNO ako bilo ko kaže GRANICNO, a niko DA)."""
    # GATE-03: tačan prvi token (ranije je prefiks "NE" hvatao i NEPRIMENLJIVO i NEMA)
    v = [(re.findall(r"[A-ZČĆŽŠĐ_]+", str(x.get(polje, "")).upper()) or [""])[0] for x in lista]
    for tok in ("DA", "GRANICNO", "NETACNA", "SABLON", "TACNA", "NE", "NEPRIMENLJIVO", "NEMA"):
        if tok in v:
            return tok
    return v[0] if v else ""


def oznaceno(grupa_sc, indeks, citat):
    """Da li se citat preklapa sa rečenicom koju je provera označila."""
    c = norm(citat)
    if not c:
        return None
    for r in provera[grupa_sc][indeks]:
        rn = norm(r)
        if not rn:
            continue
        if rn in c or c in rn or len(set(rn.split()) & set(c.split())) >= max(6, int(0.6 * len(set(c.split())))):
            return True
    return False


tab = defaultdict(lambda: defaultdict(Counter))
detalji = defaultdict(list)
for s, k in kljuc.items():
    g = f"{k['grupa']}_{k['scenario']}"
    L = oznake[s]
    t = tab[g]
    t["n"]["n"] += 1
    for polje in ("O1", "S", "G", "P", "K", "UZ", "U", "I", "R", "N", "O2"):
        t[polje][kombinuj(L, polje)] += 1
    okviri = [str(x.get("S_okvir", "")).upper() for x in L if DA(x.get("S"))]
    if okviri:                                   # GATE-03: po NACRTU (najgori okvir), ne po oznaci
        for ok in ("GOLA", "STAV_UZ_ODLUKU", "OBRAZLOZEN_PREDLOG", ""):
            if ok in okviri:
                t["S_okvir"][ok] += 1
                break
    t["Q"]["zbir"] += sum(x.get("Q", 0) for x in L) / len(L)
    o1, sv = kombinuj(L, "O1"), kombinuj(L, "S")
    if o1 in ("DA", "GRANICNO") or (sv == "DA" and any(str(x.get("S_okvir", "")).upper() == "GOLA" for x in L)):
        citati = [x.get("O1_citat") for x in L if str(x.get("O1", "")).upper() in ("DA", "GRANICNO")] + \
                 [x.get("S_citat") for x in L if DA(x.get("S"))]
        pokr = [oznaceno(g, k["indeks"], c) for c in citati if c]
        detalji[g].append({"sifra": s, "indeks": k["indeks"], "O1": o1, "S_okvir": [x.get("S_okvir") for x in L],
                           "citati": citati, "oznaceno": any(pokr) if pokr else None})
# slaganje na preklopu
sl = Counter()
for s, L in oznake.items():
    if len(L) == 2:
        for polje in ("O1", "S", "P", "U", "R", "I", "K", "UZ", "N"):
            a, b = (str(x.get(polje, "")).upper().split()[0] if x.get(polje) else "" for x in L)
            sl[polje + ("_isto" if a == b else "_razlicito")] += 1
red = ["pre_A", "posle_A", "pre_C1", "posle_C1", "posle_C2", "posle_B", "posle_H1", "posle_H2"]
print("grupa | n | O1 DA/GRAN | S DA (okviri) | G | P | K NE | UZ NE | U NE | R | I | N | Q̄")
for g in red:
    t = tab[g]
    n = t["n"]["n"]
    print(f"{g} | {n} | {t['O1']['DA']}/{t['O1']['GRANICNO']} | {t['S']['DA']} {dict(t['S_okvir'])} | {t['G']['DA']} | "
          f"{t['P']['DA']} | {t['K']['NE']} | {t['UZ']['NE']} | {t['U']['NE']} | {t['R']['DA']} | {t['I']['DA']} | "
          f"{dict(t['N'])} | {t['Q']['zbir'] / n:.2f}")
print("\nslaganje na preklopu:", dict(sl))
print("\nsporne tvrdnje (O1 DA/GRAN ili S GOLA) i da li ih provera označava:")
for g in red:
    for x in detalji[g]:
        print(g, x["indeks"], x["O1"], x["S_okvir"], "oznaceno=", x["oznaceno"], "|", (x["citati"][0] or "")[:150])
json.dump({"tab": {g: {p: dict(c) for p, c in t.items()} for g, t in tab.items()}, "detalji": detalji,
           "slaganje": dict(sl)}, open(T + "t03_rezultat.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
