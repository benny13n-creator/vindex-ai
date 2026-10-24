# -*- coding: utf-8 -*-
"""Slepi paket za nezavisnog označivača: po spisu (bez oznake scenarija) samo današnji datum, tekst dokumenata, zahtev
i nacrti pod nasumičnim šiframa, izmešani. Bez sistemske poruke, bez bloka PROCESNO STANJE i pravila, bez provere.
Ključ (šifra -> scenario, indeks) ide u zaseban fajl koji označivač NE dobija.
Upotreba: python -I -X utf8 slepi_paket.py <izlazni_dir> <seme> <scenario>=<snimak>:<izlaz> ..."""
import json
import os
import random
import sys

out_dir, seme = sys.argv[1], int(sys.argv[2])
rng = random.Random(seme)
os.makedirs(out_dir, exist_ok=True)
spisi, nacrti, kljuc = {}, [], {}
imena_spisa = {}
for arg in sys.argv[3:]:
    sc, puta = arg.split("=", 1)
    snimak, izlaz = puta.split(":", 1)
    u = json.load(open(snimak, encoding="utf-8"))["N"]["poruka"]["user"]
    datum = u.splitlines()[0]
    dok = u[u.index("[DOK-"):u.index("</VINDEX_NEPOVERLJIVO_DOKUMENT_ILI_OCR", u.index("[DOK-"))].strip()
    zahtev = u.rsplit("Zahtev: ", 1)[1].strip()
    tekst = f"{datum}\n\nZAHTEV KOJI JE DAT PISCU NACRTA: {zahtev}\n\nDOKUMENTI SPISA:\n{dok}\n"
    sid = imena_spisa.setdefault(tekst, f"SPIS-{len(imena_spisa) + 1}")
    spisi[sid] = tekst
    for i, x in enumerate(json.load(open(izlaz, encoding="utf-8"))["N"]):
        nacrti.append((sid, sc, i, x["odgovor"]))
rng.shuffle(nacrti)
for n, (sid, sc, i, o) in enumerate(nacrti):
    sifra = f"N{rng.randrange(100, 999)}{n:02d}"
    kljuc[sifra] = {"scenario": sc, "indeks": i, "spis": sid}
    nacrti[n] = {"sifra": sifra, "spis": sid, "nacrt": o}
with open(os.path.join(out_dir, "SPISI.md"), "w", encoding="utf-8") as f:
    for sid, t in spisi.items():
        f.write(f"# {sid}\n\n{t}\n\n")
with open(os.path.join(out_dir, "NACRTI.md"), "w", encoding="utf-8") as f:
    for x in nacrti:
        f.write(f"# {x['sifra']} (uz {x['spis']})\n\n{x['nacrt']}\n\n")
json.dump(kljuc, open(os.path.join(os.path.dirname(out_dir.rstrip('/\\')), os.path.basename(out_dir.rstrip('/\\')) + "_KLJUC.json"),
                      "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(spisi), "spisa,", len(nacrti), "nacrta")
