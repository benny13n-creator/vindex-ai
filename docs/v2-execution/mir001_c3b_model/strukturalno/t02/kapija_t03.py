"""Kapija (shared/nacrt_za_sud.zastiti) nad 110 nacrta slepog merenja t03 — UNUTAR UZORKA, nije dokaz.
Za svaku slepo označenu materijalnu tvrdnju (O1/P/R/I = DA ili granično, sa citatom) proverava da li njen citat
posle kapije više nije u tekstu za sud; broji i koliko je rečenica izostavljeno po nacrtu (rizik potiskivanja)."""
import json
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
from shared import procesno_stanje as PS, nacrt_za_sud as NZ  # noqa: E402

T = "docs/v2-execution/mir001_c3b_model/t03/"
kljuc = json.load(open(T + "slepo_KLJUC.json", encoding="utf-8"))
oznake = {}
for i in (1, 2, 3):
    oznake.update(json.load(open(T + f"oznake_deo{i}.json", encoding="utf-8"))["nacrti"])


def docs(f):
    u = json.load(open(T + f, encoding="utf-8"))["N"]["poruka"]["user"]
    body = u.split("SADRZAJ DOKUMENATA PREDMETA")[1].split("[KRAJ DOKUMENATA]")[0]
    return [{"id": k, "oznaka": k, "tekst": v, "predmet_id": "P", "user_id": "U"}
            for k, v in re.findall(r"\n\[(DOK-\d+): [^\]]*\]\n(.*?)(?=\n\[DOK-|\n</VINDEX)", body, re.S)]


stanja, izlazi = {}, {}
norm = lambda t: " ".join(PS._n(t).split())
stat = defaultdict(Counter)
primeri = defaultdict(list)
for sifra, kk in kljuc.items():
    g, sc, ix = kk["grupa"], kk["scenario"], kk["indeks"]
    if (g, sc) not in stanja:
        stanja[(g, sc)] = PS.utvrdi(docs(f"snimak_{g}_{sc}.json"), predmet_id="P", user_id="U")
        izlazi[(g, sc)] = json.load(open(T + f"r/{g}_{sc}.json", encoding="utf-8"))["N"]
    nacrt = izlazi[(g, sc)][ix]["odgovor"]
    k = NZ.zastiti(nacrt, stanja[(g, sc)])
    ostalo = norm(k["tekst"])
    grp = f"{g}_{sc}"
    stat[grp]["nacrta"] += 1
    stat[grp]["izostavljeno_recenica"] += len(k["izostavljeno"])
    o = oznake.get(sifra) or {}
    for pol in ("O1", "P", "R", "I"):
        if str(o.get(pol, "")).upper().startswith(("DA", "GRAN")) and o.get(pol + "_citat"):
            cit = norm(o[pol + "_citat"])[:60]
            uklonjeno = cit not in ostalo
            stat[grp][f"{pol}_ukupno"] += 1
            stat[grp][f"{pol}_uklonjeno"] += uklonjeno
            if not uklonjeno:
                primeri[grp].append(f"{pol} OSTALO #{ix}: {o[pol + '_citat'][:150]}")
    for i in k["izostavljeno"]:
        primeri[grp + "_izost"].append(f"#{ix} {i['razlog'][:40]}: {i['recenica'][:140]}")
for grp in sorted(stat):
    print(grp, dict(stat[grp]))
for grp in sorted(primeri):
    if grp.endswith("_izost"):
        continue
    for p in primeri[grp][:8]:
        print("  ", grp, p)
for grp in ("posle_B_izost", "posle_H1_izost"):
    print("== izostavljeno u", grp, len(primeri[grp]))
    for p in primeri[grp][:25]:
        print("   ", p)
