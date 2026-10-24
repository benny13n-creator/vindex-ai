# -*- coding: utf-8 -*-
"""TASK-03 (FINAL CLOSURE) — paketi za nezavisnog „advokata“ (B1) i slepe ocenjivače (B2: AI predlog, B3: dokument za
sud). PREREGISTRACIJA.md §3. Šifre su nasumične; ključ (šifra → scenarij) ide u `kljuc_<faza>.json` VAN foldera paketa.

Upotreba (iz ovog foldera):
  python -I -X utf8 paketi_fc.py b1 <seme>        → paket_b1/ (iz gen/*.json)
  python -I -X utf8 paketi_fc.py b2|b3 <seme>     → paket_b2/ (iz gen/), paket_b3/ (iz primeni/); isto seme za oba
  python -I -X utf8 paketi_fc.py odluke           → b1/odluke.json (iz paket_b1/odluke_sifre.json + kljuc_b1.json)"""
import json
import os
import random
import sys

OVDE = os.path.dirname(os.path.abspath(__file__))
SC = ["A", "C1", "C2", "H2", "B", "H1", "N1", "N2", "N3", "N4"]
ZAHTEV = ("Sastavi podnesak tuzioca za rociste zakazano za 18.11.2026. kojim se izjasnjava na nalaz i misljenje vestaka "
          "(DOK-05), na izjasnjenje tuzenog (DOK-06) i o stanju postupka.")
DATUM = "Današnji datum: 2026-10-24"


def _gen(sc):
    return json.load(open(os.path.join(OVDE, "gen", sc + ".json"), encoding="utf-8"))


def _spis(z):
    out = [DATUM, "", f"ZAHTEV KOJI JE DAT SISTEMU: {ZAHTEV}", "", "DOKUMENTI SPISA:"]
    for d in z["dokumenti_spisa"]:
        t = d["tekst"].strip()
        oz = f"[{d['oznaka']}] {d['ime']}"
        if len(t.splitlines()) <= 1:
            oz += " — skeniran dokument; ispod je sav čitljiv tekst"
        out += ["", oz, t]
    return "\n".join(out)


def _sifre(seme, n, pref):
    rng = random.Random(seme)
    red = list(SC)
    rng.shuffle(red)
    return {f"{pref}{rng.randrange(100, 999)}{i}": sc for i, sc in enumerate(red)}


def b1(seme):
    kljuc = _sifre(seme, 10, "P")
    d = os.path.join(OVDE, "paket_b1")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "PREDMETI.md"), "w", encoding="utf-8") as f:
        for sif, sc in kljuc.items():
            z = _gen(sc)
            p = z["predlog"]
            f.write(f"# PREDMET {sif}\n\n## SPIS\n\n{_spis(z)}\n\n## AI RADNI PREDLOG (stavke; samo za pregled)\n\n")
            for s in p["stavke"]:
                f.write(f"### {s['id']}\n{s['tekst']}\n" + (f"Izvori koje navodi AI (nisu provereni): {', '.join(s['izvori'])}\n" if s["izvori"] else "") + "\n")
            f.write("## PROCESNE INFORMACIJE (doslovni izvodi iz spisa koje je izdvojio sistem; značenje i važenje NISU utvrđeni)\n\n")
            for t in p["procesne_tacke"]:
                f.write(f"### {t['kljuc']} — {t['naziv']}\n" + (f"{t['pomoc']}\n" if t.get("pomoc") else ""))
                for c in t["kandidati"]:
                    f.write(f"- {c['oznaka']}: „{c['izvod']}“" + (f" · Nije utvrđeno: {'; '.join(c['nije_utvrdjeno'])}" if c["nije_utvrdjeno"] else "")
                            + (f" · Kasnije u spisu: {'; '.join(c['kasnije'])}" if c["kasnije"] else "") + "\n")
                f.write("\n")
            f.write(f"## INTERNE NAPOMENE (savetnik i sistem; ne idu u dokument za sud)\n\n{z.get('interno', '')}\n\n---\n\n")
    json.dump(kljuc, open(os.path.join(OVDE, "kljuc_b1.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("paket_b1:", len(kljuc), "predmeta")


def odluke():
    kljuc = json.load(open(os.path.join(OVDE, "kljuc_b1.json"), encoding="utf-8"))
    o = json.load(open(os.path.join(OVDE, "paket_b1", "odluke_sifre.json"), encoding="utf-8"))
    out = {kljuc[s]: v for s, v in o.items()}
    assert sorted(out) == sorted(SC), sorted(out)
    os.makedirs(os.path.join(OVDE, "b1"), exist_ok=True)
    json.dump(out, open(os.path.join(OVDE, "b1", "odluke.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("b1/odluke.json:", len(out))


def b23(seme, samo=None):
    for faza, pref, seme_f in (("b2", "Q", seme), ("b3", "D", seme + 1)):
        if samo and faza != samo:
            continue
        kljuc = _sifre(seme_f, 10, pref)
        d = os.path.join(OVDE, "paket_" + faza)
        os.makedirs(d, exist_ok=True)
        spisi, tekstovi = {}, []
        for sif, sc in kljuc.items():
            z = _gen(sc)
            spisi.setdefault(sc, _spis(z))
            if faza == "b2":
                tekst = "\n\n".join(s["tekst"] for s in z["predlog"]["stavke"])
            else:
                pr = json.load(open(os.path.join(OVDE, "primeni", sc + ".json"), encoding="utf-8"))
                tekst = "\n".join(pr.get("docx_pasusi") or []) if pr.get("docx_status") == 200 else "(Dokument nije odobren ni izvezen.)"
            tekstovi.append((sif, sc, tekst))
        imena = {sc: f"SPIS-{i + 1}" for i, sc in enumerate(random.Random(seme_f + 7).sample(SC, len(SC)))}
        with open(os.path.join(d, "SPISI.md"), "w", encoding="utf-8") as f:
            for sc in sorted(imena, key=lambda s: int(imena[s].split("-")[1])):
                f.write(f"# {imena[sc]}\n\n{spisi[sc]}\n\n")
        with open(os.path.join(d, "TEKSTOVI.md"), "w", encoding="utf-8") as f:
            for sif, sc, t in tekstovi:
                f.write(f"# TEKST {sif} (uz {imena[sc]})\n\n{t}\n\n---\n\n")
        json.dump({s: {"scenarij": sc, "spis": imena[sc]} for s, sc, _ in tekstovi},
                  open(os.path.join(OVDE, f"kljuc_{faza}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"paket_{faza}:", len(tekstovi))


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "b1":
        b1(int(sys.argv[2]))
    elif m == "odluke":
        odluke()
    elif m in ("b2", "b3"):
        b23(int(sys.argv[2]), samo=m)
