# -*- coding: utf-8 -*-
"""TASK-03 slepi paketi: svi nacrti (sve grupe) izmešani i raspoređeni u K delova; P nacrta je dodatno u još jednom delu
(slaganje označivača). Spisi su isti za sve delove i bez oznake scenarija/grupe. Ključ (šifra -> grupa, scenario,
indeks) ide u zaseban fajl koji označivači ne dobijaju.
Upotreba: python -I -X utf8 slepi_paket2.py <izlazni_dir> <seme> <K> <P> <grupa>:<scenario>=<snimak>:<izlaz> ..."""
import json
import os
import random
import sys

out_dir, seme, K, P = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
rng = random.Random(seme)
os.makedirs(out_dir, exist_ok=True)
spisi, imena, nacrti = {}, {}, []
for arg in sys.argv[5:]:
    gs, puta = arg.split("=", 1)
    grupa, sc = gs.split(":", 1)
    snimak, izlaz = puta.split(":", 1)
    u = json.load(open(snimak, encoding="utf-8"))["N"]["poruka"]["user"]
    datum = u.splitlines()[0]
    dok = u[u.index("[DOK-"):u.index("</VINDEX_NEPOVERLJIVO_DOKUMENT_ILI_OCR", u.index("[DOK-"))].strip()
    zahtev = u.rsplit("Zahtev: ", 1)[1].strip()
    tekst = f"{datum}\n\nZAHTEV KOJI JE DAT PISCU NACRTA: {zahtev}\n\nDOKUMENTI SPISA:\n{dok}\n"
    sid = imena.setdefault(tekst, None)
    if sid is None:
        sid = imena[tekst] = f"SPIS-{len(imena)}"
        spisi[sid] = tekst
    for i, x in enumerate(json.load(open(izlaz, encoding="utf-8"))["N"]):
        nacrti.append({"grupa": grupa, "scenario": sc, "indeks": i, "spis": sid, "nacrt": x["odgovor"]})
rng.shuffle(nacrti)
kljuc, delovi = {}, [[] for _ in range(K)]
for n, x in enumerate(nacrti):
    x["sifra"] = f"T{rng.randrange(100, 999)}{n:03d}"
    kljuc[x["sifra"]] = {k: x[k] for k in ("grupa", "scenario", "indeks", "spis")}
    delovi[n % K].append(x)
preklop = rng.sample(range(len(nacrti)), P)
for j, n in enumerate(preklop):
    drugi = (n % K + 1 + j % (K - 1)) % K
    delovi[drugi].append(nacrti[n])
    kljuc[nacrti[n]["sifra"]]["preklop_u_delu"] = drugi + 1
for d, lista in enumerate(delovi, 1):
    rng.shuffle(lista)
    dd = os.path.join(out_dir, f"deo{d}")
    os.makedirs(dd, exist_ok=True)
    with open(os.path.join(dd, "SPISI.md"), "w", encoding="utf-8") as f:
        for sid in sorted(spisi, key=lambda s: int(s.split("-")[1])):
            f.write(f"# {sid}\n\n{spisi[sid]}\n\n")
    with open(os.path.join(dd, "NACRTI.md"), "w", encoding="utf-8") as f:
        for x in lista:
            f.write(f"# {x['sifra']} (uz {x['spis']})\n\n{x['nacrt']}\n\n")
    print(f"deo{d}:", len(lista), "nacrta")
json.dump(kljuc, open(os.path.join(os.path.dirname(out_dir.rstrip('/\\')), os.path.basename(out_dir.rstrip('/\\')) + "_KLJUC.json"),
                      "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(spisi), "spisa,", len(nacrti), "nacrta, preklop", P)
