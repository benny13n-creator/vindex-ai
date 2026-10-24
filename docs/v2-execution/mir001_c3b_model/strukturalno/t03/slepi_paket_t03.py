# -*- coding: utf-8 -*-
"""TASK-03 slepi paketi (PREREGISTRACIJA.md §3).

Svih 100 izlaza se meša i deli u 4 dela po 25. Oba označivača dobijaju iste delove, a svaki označivač ocenjuje svih 100.
Spisi su pod nasumičnim imenima (SPIS-n) i bez oznake scenarija. Ključ (šifra → scenarij, indeks, spis) ide u
zaseban fajl van foldera označivača.

Za svaki izlaz označivač vidi:
- tekst za sud;
- izostavljene rečenice (bez razloga kapije);
- napomene savetnika (AI);
- izvezen DOCX i DOCX posle uklanjanja obeležja.
Ne vidi razloge kapije, procesno stanje koje je utvrdio sistem, rezultate automatskih provera ni verziju koda.

Upotreba: python -I -X utf8 slepi_paket_t03.py <izlazi_dir> <izlazni_dir> <seme>"""
import glob
import json
import os
import random
import re
import sys

izl, out, seme = sys.argv[1], sys.argv[2], int(sys.argv[3])
rng = random.Random(seme)
DATUM = "Današnji datum: 2026-10-24"
ZAHTEV_RE = None


def _odeljak(interno, naslov):
    """Redovi odeljka internih napomena do sledećeg naslova (red bez „- “ na početku) ili do kraja."""
    redovi = interno.split("\n")
    try:
        i = next(n for n, r in enumerate(redovi) if r.startswith(naslov))
    except StopIteration:
        return []
    van = []
    for r in redovi[i + 1:]:
        if not r.strip() or r.startswith("———") or not r.startswith("- "):
            break
        van.append(r[2:])
    return van


def izostavljene(interno):
    recenice = []
    for r in _odeljak(interno, "IZOSTAVLJENO IZ TEKSTA ZA SUD"):
        m = re.match(r"^I-\d+ \(.*?\): „(.*)“\s*$", r, flags=re.S)
        recenice.append(m.group(1) if m else r)   # bez razloga kapije
    return recenice


def spis_tekst(z):
    delovi = [DATUM, "", f"ZAHTEV KOJI JE DAT SISTEMU: {ZAHTEV}", "", "DOKUMENTI SPISA:"]
    for d in z["dokumenti_spisa"]:
        t = d["tekst"].strip()
        oznaka = f"[{d['oznaka']}] {d['ime']}"
        if len(t.splitlines()) <= 1:
            oznaka += " — skeniran dokument; ispod je sav čitljiv tekst"
        delovi += ["", oznaka, t]
    return "\n".join(delovi)


fajlovi = sorted(glob.glob(os.path.join(izl, "*.json")))
fajlovi = [f for f in fajlovi if not os.path.basename(f).startswith("SUVO_")]
zapisi = [json.load(open(f, encoding="utf-8")) for f in fajlovi]
assert len(zapisi) == 100, len(zapisi)
ZAHTEV = re.search(r"Zahtev: (.*)$", zapisi[0]["poruka_modelu"], flags=re.S).group(1).strip()

spisi_po_sc, imena = {}, list(range(1, 11))
rng.shuffle(imena)
for z in zapisi:
    if z["scenarij"] not in spisi_po_sc:
        spisi_po_sc[z["scenarij"]] = None
for n, sc in enumerate(sorted(spisi_po_sc)):
    spisi_po_sc[sc] = f"SPIS-{imena[n]}"
spisi = {}
for z in zapisi:
    t = spis_tekst(z)
    sid = spisi_po_sc[z["scenarij"]]
    assert spisi.setdefault(sid, t) == t, sid   # isti scenarij = isti spis

stavke = []
for z in zapisi:
    if z["status"] != 200 or not z.get("na_pregledu"):
        nacrt = f"(Sistem nije izradio nacrt: odgovor {z['status']}.)"
    else:
        dx, isp = z["docx"], z["ispravka_advokata"]["docx"]
        docx1 = dx["tekst"] if dx["status"] == 200 else f"(Izvoz nije dozvoljen: {dx['razlog']})"
        docx2 = isp["tekst"] if isp["status"] == 200 else f"(Izvoz nije dozvoljen: {isp['razlog']})"
        izo = izostavljene(z["interno"])
        nap = _odeljak(z["interno"], "NAPOMENE SAVETNIKA (AI)")
        nacrt = "\n".join([
            "## 1. TEKST ZA SUD", "", z["tekst_za_sud"], "",
            "## 2. IZOSTAVLJENO IZ TEKSTA ZA SUD", "",
            *([f"- „{r}“" for r in izo] or ["(ništa)"]), "",
            "## 3. INTERNE NAPOMENE", "",
            *([f"- {r}" for r in nap] or ["(nema)"]), "",
            "## 4a. IZVEZEN DOCX (tekst kako je sačuvan)", "", docx1, "",
            "## 4b. IZVEZEN DOCX posle uklanjanja redova sa obeležjima „[IZOSTAVLJENO …]“", "", docx2])
    stavke.append({"sc": z["scenarij"], "i": z["indeks"], "spis": spisi_po_sc[z["scenarij"]], "nacrt": nacrt})

rng.shuffle(stavke)
kljuc = {}
for n, s in enumerate(stavke):
    s["sifra"] = f"X{rng.randrange(100, 999)}{n:02d}"
    kljuc[s["sifra"]] = {"scenarij": s["sc"], "indeks": s["i"], "spis": s["spis"], "deo": n % 4 + 1}
os.makedirs(out, exist_ok=True)
for d in range(4):
    dd = os.path.join(out, f"deo{d + 1}")
    os.makedirs(dd, exist_ok=True)
    with open(os.path.join(dd, "SPISI.md"), "w", encoding="utf-8") as f:
        for sid in sorted(spisi, key=lambda s: int(s.split("-")[1])):
            f.write(f"# {sid}\n\n{spisi[sid]}\n\n")
    deo = [s for n, s in enumerate(stavke) if n % 4 == d]
    with open(os.path.join(dd, "NACRTI.md"), "w", encoding="utf-8") as f:
        for s in deo:
            f.write(f"# NACRT {s['sifra']} (uz {s['spis']})\n\n{s['nacrt']}\n\n---\n\n")
    print(f"deo{d + 1}: {len(deo)} nacrta")
json.dump(kljuc, open(os.path.join(os.path.dirname(out.rstrip("/\\")), "t03_KLJUC.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(len(spisi), "spisa")
