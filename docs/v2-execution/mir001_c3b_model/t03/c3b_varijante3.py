# -*- coding: utf-8 -*-
"""MIR001 C3b TASK-01 — varijante poruke nacrta iz snimka HEAD koda (scenario A).
Blok PROCESNO STANJE se za svaku varijantu računa STVARNIM kodom (`_RE_ODLUKA_SUDA` + `_procesno_stanje_za_nacrt`).
A  — sud je naložio dopunu (Golden Case, nepromenjeno)
B  — nema naloga: zapisnik DOK-07 nije u spisu
C1 — nalog postoji (DOK-07), ali kasniji podnesak tuženog (DOK-08) odustaje od predloga — da li nalog i dalje važi, nejasno
C2 — zapisnika nema; samo podnesak tuženog (DOK-08) tvrdi da je predlog „razmatran“ — da li je nalog donet, nejasno
Ab — dijagnostika: A, ali zahtev se izjašnjava SAMO na nalaz (DOK-05), ne i na DOK-06
Upotreba: python -I -X utf8 c3b_varijante.py <snimak_A.json> <izlazni_dir>"""
import json
import os
import re
import sys

KOREN = os.environ.get("VX_KOREN", r"C:/vindex-miroslav")
sys.path.insert(0, KOREN)
os.chdir(KOREN)
import routers.multi_agent as MA  # noqa: E402

A = json.load(open(sys.argv[1], encoding="utf-8"))["N"]
OUT = sys.argv[2]
u0 = A["poruka"]["user"]
DOK07 = u0[u0.index("[DOK-07:"):u0.index("[DOK-04:")]
DOK08_C1 = ("[DOK-08: 08 Podnesak tuzenog.pdf | 1KB]\nPRIVREDNI SUD U PRIMERGRADU (SINTETICKI)\nBroj predmeta: P 9901/2026\n"
            "PODNESAK TUZENOG (SINTETICKI PREDMET)\nTuzeni odustaje od predloga za dopunu vestacenja.\n"
            "Tuzeni navodi da gradjevinski dnevnik nije sacuvan.\nDatum podneska: 05.09.2026. godine.\n")
DOK08_C2 = ("[DOK-08: 08 Podnesak tuzenog.pdf | 1KB]\nPRIVREDNI SUD U PRIMERGRADU (SINTETICKI)\nBroj predmeta: P 9901/2026\n"
            "PODNESAK TUZENOG (SINTETICKI PREDMET)\nTuzeni navodi da je na rocistu odrzanom 15.07.2026. godine raspravljano "
            "o njegovom predlogu za dopunu vestacenja.\nTuzeni ponavlja predlog za dopunu vestacenja.\n"
            "Datum podneska: 20.07.2026. godine.\n")


def blok(dokumenti: dict) -> str:
    odluke = []
    for oz, tx in dokumenti.items():
        for red in tx.splitlines():
            if MA._RE_ODLUKA_SUDA.search(red):
                odluke.append({"oznaka": oz, "tekst": " ".join(red.split())[:200]})
    return MA._procesno_stanje_za_nacrt({"_odluke_suda": odluke}), odluke


def dokumenti_iz(u):
    deo = u[u.index("[DOK-"):u.index("</VINDEX_NEPOVERLJIVO_DOKUMENT_ILI_OCR", u.index("[DOK-"))]
    out = {}
    for m in re.finditer(r"\[(DOK-\d+):[^\]]*\]\n(.*?)(?=\n\[DOK-|\Z)", deo, re.S):
        out[m.group(1)] = m.group(2)
    return out


def poredaj(u, zahtev):
    """Redosled kao stvarni kod (multi_agent.py: meta `redni_broj desc`, traženi u zadatku prvi)."""
    a = u.index("[DOK-")
    b = u.index("</VINDEX_NEPOVERLJIVO_DOKUMENT_ILI_OCR", a)
    blokovi = re.findall(r"\[DOK-\d+:.*?(?=\[DOK-\d+:|\Z)", u[a:b], re.S)
    trazeni = {int(x) for x in re.findall(r"DOK-(\d+)", zahtev)}
    rb = lambda s: int(re.match(r"\[DOK-(\d+)", s).group(1))
    blokovi = [x if x.endswith("\n") else x + "\n" for x in blokovi]
    # multi_agent.py:865–867: traženi rastuće po rednom broju, zatim ostali u redosledu meta (`redni_broj desc`)
    blokovi.sort(key=lambda s: (0, rb(s)) if rb(s) in trazeni else (1, -rb(s)))
    return u[:a] + "".join(blokovi) + u[b:]


def sastavi(u, dodaj_posle_07=None, bez_07=False, zahtev=None, preimenuj=None, zameni_07=None):
    if zameni_07:                                    # held-out: izmenjeni redovi zapisnika DOK-07
        novi07 = DOK07
        for staro, novo in zameni_07:
            assert novi07.count(staro) == 1, staro
            novi07 = novi07.replace(staro, novo)
        u = u.replace(DOK07, novi07)
    if bez_07:
        u = u.replace(DOK07, "")
    if dodaj_posle_07:
        sidro = "[DOK-04:"
        u = u.replace(sidro, (dodaj_posle_07.replace(*preimenuj) if preimenuj else dodaj_posle_07) + sidro, 1)
    if zahtev:
        pre_z, _ = u.rsplit("\n\nZahtev: ", 1)
        u = pre_z + "\n\nZahtev: " + zahtev
    u = poredaj(u, u.rsplit("Zahtev: ", 1)[1])
    oznake = re.findall(r"\[(DOK-\d+):", u[:u.index("[KRAJ DOKUMENATA]")])
    u = re.sub(r"Dokumenti: \d+", f"Dokumenti: {len(oznake)}", u, 1)
    u = re.sub(r"Dokumenata u predmetu: \d+", f"Dokumenata u predmetu: {len(oznake)}", u, 1)
    u = re.sub(r"Tekst dostavljen u celini: [^\n]*", "Tekst dostavljen u celini: " + ", ".join(oznake), u, 1)
    # stari blok PROCESNO STANJE (ako postoji) zameni novim, izračunatim nad dokumentima ove varijante
    pre, zah = u.rsplit("\n\nZahtev: ", 1)
    if "\n\nPROCESNO STANJE —" in pre:
        pre = pre[:pre.index("\n\nPROCESNO STANJE —")]
    novi, odluke = blok(dokumenti_iz(u))
    pre = pre + novi
    return pre + "\n\nZahtev: " + (zahtev or zah), odluke


ZAHTEV_AB = ("Sastavi podnesak tuzioca kojim se izjasnjava na nalaz i misljenje vestaka (DOK-05), za rociste zakazano "
             "za 18.11.2026.")
var = {
    "A": sastavi(u0),
    "B": sastavi(u0, bez_07=True),
    "C1": sastavi(u0, dodaj_posle_07=DOK08_C1),
    "C2": sastavi(u0, bez_07=True, dodaj_posle_07=DOK08_C2, preimenuj=("[DOK-08: 08 ", "[DOK-07: 07 ")),
    "Ab": sastavi(u0, zahtev=ZAHTEV_AB),
    # HELD-OUT (nisu viđeni u razvoju): H1 sud je predlog ODBIO; H2 nalog tužiocu sa rokom od prijema zapisnika
    "H1": sastavi(u0, zameni_07=[("Sud prihvata predlog za dopunu vestacenja.", "Sud odbija predlog tuzenog za dopunu vestacenja."),
                                 ("Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana.\n", "")]),
    "H2": sastavi(u0, zameni_07=[("Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana.",
                                  "Sud nalaze tuziocu da u roku od 8 dana od prijema zapisnika uplati predujam za dopunu vestacenja u iznosu od 60.000 dinara.")]),
}
IME = sys.argv[3] if len(sys.argv) > 3 else ""
for ime, (u, odluke) in var.items():
    json.dump({"N": {"agent": "drafting", "pitanje": u.rsplit("Zahtev: ", 1)[1], "_odluke_suda": odluke,
                     "poruka": {"system": A["poruka"]["system"], "user": u}}},
              open(os.path.join(OUT, f"snimak{IME}_{ime}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(ime, "odluka:", len(odluke), "| blok:", "PROCESNO STANJE" in u, "| A-identican:", ime != "A" or u == u0)
