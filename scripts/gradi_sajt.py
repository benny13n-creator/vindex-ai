"""Vindex — gradi javni sajt (Website V2) iz izvora i registra funkcija.

    python scripts/gradi_sajt.py            # upisuje site/*.html i docs/website-v2/02_…md
    python scripts/gradi_sajt.py --provera  # ne upisuje; izlaz 1 ako generisano ≠ sačuvano

Izvori:
  site/_izvor/<strana>.html  — sadržaj <main> svake stranice
  site/funkcije.json         — jedini izvor istine za katalog (/funkcionalnosti) i matricu dokaza
                               (docs/website-v2/02_PRODUCT_CAPABILITY_TRUTH_MATRIX.md)
Website V3 (founder): planovi razvoja se NE objavljuju. Stranica /razvoj je povučena
(301 na /funkcionalnosti); PLANNED_APPROVED stavke ostaju samo u internoj matrici.
Zaglavlje, podnožje i <head> su ovde, jednom, za sve stranice. Generisani fajlovi se čuvaju u git-u
(server ih servira kao statične fajlove, bez koraka gradnje u produkciji); tests/test_website_public.py
proverava da su usklađeni sa izvorom.
"""
from __future__ import annotations

import hashlib
import html
import json
import sys
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent
SAJT = KOREN / "site"
DOMEN = "https://vindex.rs"

STRANICE = [
    # (izvor, izlaz, ruta, naslov, opis, stavka menija)
    ("index", "index.html", "/", "Vindex — od dokumenata do jasnih odluka",
     "Vindex povezuje predmete, dokumente, dokaze, rokove i pravna pitanja u jedan radni prostor. Svaki podatak ostaje vezan za svoj izvor, a odluka ostaje advokatu.", None),
    ("kako-radi", "kako-radi.html", "/kako-radi", "Kako radi — Vindex",
     "Tok rada u Vindexu od otvaranja predmeta do odluke advokata: šta radite vi, šta radi Vindex i gde je potrebna vaša potvrda.", "Kako radi"),
    ("funkcionalnosti", "funkcionalnosti.html", "/funkcionalnosti", "Funkcionalnosti — Vindex",
     "Funkcije koje Vindex danas nudi, grupisane po poslu: organizacija predmeta, čitanje dokumenata, dokazi, istraživanje, nacrti, rokovi i zaštita.", "Funkcionalnosti"),
    ("za-advokate", "za-advokate.html", "/za-advokate", "Za advokate — Vindex",
     "Primeri toka rada u advokatskoj kancelariji sa funkcijama koje danas postoje u Vindexu, uz granice svake funkcije.", "Za advokate"),
    ("bezbednost", "bezbednost.html", "/bezbednost", "Bezbednost i zaštita podataka — Vindex",
     "Ko pristupa podacima, gde se čuvaju, šta se šalje AI modelu, kako se izvoze i brišu — opisano onako kako Vindex stvarno radi.", "Bezbednost"),
    ("beta", "beta.html", "/beta", "Rani pristup — Vindex",
     "Prijava za rani pristup Vindexu: kontrolisano uključivanje advokata i kancelarija u rad sa aplikacijom, uz podršku.", None),
]
JAVNI_STATUSI = ["V2_AVAILABLE", "AVAILABLE_WITH_LIMITATIONS", "LEGACY_ONLY"]
CTA = "Prijavi se za rani pristup"

# Katalog je grupisan po poslu koji korisnik obavlja (ne po tehničkim oblastima):
# ORGANIZUJ → RAZUMI → POVEŽI → ANALIZIRAJ → PRIPREMI → DELUJ, pa kontrola i zaštita.
# (sidro, naslov, uvod, oblasti iz registra)
GRUPE = [
    ("predmeti", "Organizujte predmete i klijente",
     "Registar, podaci predmeta, beleške, hronologija i klijenti, sa proverom sukoba interesa.", ["A", "H"]),
    ("dokumenti", "Razumite dokumente",
     "Dokumenti i skenovi ulaze u predmet; Vindex čita tekst i predlaže vrstu i podatke za vaš pregled.", ["B"]),
    ("dokazi", "Povežite podatke i dokaze",
     "Tvrdnje ostaju vezane za dokument iz kog potiču; razlike između dokumenata su vidljive.", ["C"]),
    ("istrazivanje", "Istražite i iskoristite znanje kancelarije",
     "Pravno pitanje uz izvore, savetnici, sudska praksa i iskustvo iz vaših predmeta.", ["E", "G"]),
    ("nacrti", "Pripremite podneske i naplatu",
     "Nacrt kao polazna tačka koju overava advokat, i evidencija rada za naplatu.", ["F", "I"]),
    ("rokovi", "Delujte na vreme",
     "Rokovi, ročišta i zadaci preko svih predmeta, sa vašom potvrdom svakog predloženog roka.", ["D"]),
    ("zastita", "Kontrola i zaštita",
     "Pristup po nalogu, poreklo svakog podatka i istinit prikaz grešaka.", ["J", "K"]),
]
e = html.escape


def registar() -> dict:
    return json.loads((SAJT / "funkcije.json").read_text(encoding="utf-8"))


def verzija() -> str:
    h = hashlib.sha256()
    for f in ("sajt.css", "sajt.js"):
        h.update((SAJT / f).read_bytes().replace(b"\r\n", b"\n"))  # isti heš na Windows (CRLF) i Linux checkout-u
    return h.hexdigest()[:10]


def zaglavlje(ruta: str) -> str:
    stavke = [(r, m) for _, _, r, _, _, m in STRANICE if m]
    def li(r, m):
        tren = ' aria-current="page"' if r == ruta else ""
        return f'<li><a href="{r}"{tren}>{m}</a></li>'
    meni = "".join(li(r, m) for r, m in stavke)
    return f"""<header class="zaglavlje">
  <div class="okvir">
    <a class="logo" href="/" aria-label="Vindex — početna"><img src="/v2/site/brand/vindex-logo-final-tamna.png" alt="" width="398" height="287"></a>
    <nav aria-label="Glavna navigacija"><ul class="meni">{meni}</ul></nav>
    <div class="zaglavlje__akcije">
      <a class="dugme dugme--sporedno dugme--malo" href="/app">Prijava</a>
      <a class="dugme dugme--malo" href="/beta">{CTA}</a>
    </div>
    <details class="meni-mob">
      <summary>Meni</summary>
      <div class="meni-mob__panel">
        <nav aria-label="Glavna navigacija (mobilni prikaz)"><ul>{meni}</ul></nav>
        <div class="meni-mob__akcije">
          <a class="dugme dugme--malo" href="/beta">{CTA}</a>
          <a class="dugme dugme--sporedno dugme--malo" href="/app">Prijava</a>
        </div>
      </div>
    </details>
  </div>
</header>"""


PODNOZJE = """<footer class="podnozje">
  <div class="okvir">
    <div class="podnozje__redovi">
      <div>
        <h2>Vindex</h2>
        <p>Pravni radni prostor: predmeti, dokumenti, dokazi, rokovi i pravna pitanja, povezani sa svojim izvorom.</p>
      </div>
      <nav aria-label="Sajt">
        <h2>Sajt</h2>
        <ul>
          <li><a href="/kako-radi">Kako radi</a></li>
          <li><a href="/funkcionalnosti">Funkcionalnosti</a></li>
          <li><a href="/za-advokate">Za advokate</a></li>
          <li><a href="/bezbednost">Bezbednost</a></li>
          <li><a href="/beta">Rani pristup</a></li>
          <li><a href="/app">Prijava u aplikaciju</a></li>
        </ul>
      </nav>
      <nav aria-label="Dokumenti">
        <h2>Dokumenti</h2>
        <ul>
          <li><a href="/privacy">Politika privatnosti</a></li>
          <li><a href="/terms">Uslovi korišćenja</a></li>
          <li><a href="/dpa">Ugovor o obradi podataka</a></li>
          <li><a href="/ai-disclosure">Upotreba AI</a></li>
          <li><a href="/status">Status servisa</a></li>
        </ul>
      </nav>
    </div>
    <div class="podnozje__dno">
      <span>© 2026 Vindex</span>
      <span>Vindex ne zamenjuje profesionalno rasuđivanje advokata.</span>
    </div>
  </div>
</footer>"""


def katalog(reg: dict) -> str:
    """Katalog po poslu. Javno: samo dostupne funkcije (JAVNI_STATUSI); interni status
    ostaje u `data-status` (testovi), a posetiocu se kaže samo gde funkcija radi.
    Granica funkcije je deo njene javne formulacije i prikazuje se u celosti."""
    javne = [f for f in reg["funkcije"] if f["javno"] and f["status"] in JAVNI_STATUSI]
    poznate = {o for g in GRUPE for o in g[3]}
    assert {f["oblast"] for f in javne} <= poznate, "javna funkcija van GRUPE"
    nav, delovi = [], []
    for sidro, naslov, uvod, oblasti in GRUPE:
        stavke = [f for o in oblasti for f in javne if f["oblast"] == o]
        if not stavke:
            continue
        nav.append(f'<li><a href="#{sidro}">{e(naslov)}</a></li>')
        redovi = []
        for f in stavke:
            gde = ("Dostupno u klasičnom interfejsu aplikacije" if f["status"] == "LEGACY_ONLY"
                   else "U aplikaciji: " + f["v2_ulaz"].replace("/app → ", ""))
            redovi.append(
                f'<li class="stavka" id="f-{f["id"]}" data-id="{f["id"]}" data-status="{f["status"]}">'
                f'<div><h3>{e(f["naziv"])}</h3><p>{e(f["javni_opis"])}</p><p class="stavka__gde">{e(gde)}</p></div></li>')
        delovi.append(f'<section class="oblast otkrij" id="{sidro}" aria-labelledby="o-{sidro}">'
                      f'<h2 id="o-{sidro}">{e(naslov)}</h2><p class="oblast__uvod">{e(uvod)}</p>'
                      f'<ul class="stavke">{"".join(redovi)}</ul></section>')
    return f"""<div class="katalog">
      <nav class="katalog__nav" aria-label="Grupe funkcija"><ul>{"".join(nav)}</ul></nav>
      <div id="katalog-stavke">
        <div class="filter" id="filter" hidden>
          <div class="filter__polje"><label for="filter-tekst">Pretraga funkcija</label><input id="filter-tekst" type="search" autocomplete="off"></div>
          <p class="filter__rezultat" id="filter-rezultat" role="status" aria-live="polite"></p>
        </div>
        {"".join(delovi)}
      </div>
    </div>"""


def stranica(reg: dict, izvor: str, ruta: str, naslov: str, opis: str) -> str:
    telo = (SAJT / "_izvor" / f"{izvor}.html").read_text(encoding="utf-8")
    if "<!--KATALOG-->" in telo:
        telo = telo.replace("<!--KATALOG-->", katalog(reg))
    telo = telo.replace("<!--CTA-->", CTA)
    v = verzija()
    url = DOMEN + ruta
    return f"""<!doctype html>
<html lang="sr-Latn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(naslov)}</title>
<meta name="description" content="{e(opis)}">
<link rel="canonical" href="{url}">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0d0e10">
<meta property="og:type" content="website">
<meta property="og:locale" content="sr_RS">
<meta property="og:site_name" content="Vindex">
<meta property="og:title" content="{e(naslov)}">
<meta property="og:description" content="{e(opis)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{DOMEN}/v2/site/snimci/registar.webp">
<meta property="og:image:alt" content="Demonstracioni prikaz ekrana Aktivni predmeti u aplikaciji Vindex, sa izmišljenim predmetima.">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/png" href="/static/favicon-vindex-v5-32.png">
<link rel="stylesheet" href="/v2/site/fonts/ibm-plex-sans/400.css">
<link rel="stylesheet" href="/v2/site/fonts/ibm-plex-sans/500.css">
<link rel="stylesheet" href="/v2/site/fonts/source-serif-4/500.css">
<link rel="stylesheet" href="/v2/site/sajt.css?v={v}">
<!-- Generisano: scripts/gradi_sajt.py iz site/_izvor/{izvor}.html i site/funkcije.json. Ne menjati ručno. -->
</head>
<body class="sajt">
<a class="skip" href="#sadrzaj">Preskoči na sadržaj</a>
<canvas id="pozadina" aria-hidden="true"></canvas>
<div class="strana">
{zaglavlje(ruta)}
<main id="sadrzaj" tabindex="-1">
{telo.rstrip()}
</main>
{PODNOZJE}
</div>
<script src="/v2/site/potpis.js"></script>
<script src="/v2/site/sajt.js?v={v}"></script>
</body>
</html>
"""


def matrica(reg: dict) -> str:
    from collections import Counter
    br = Counter(f["status"] for f in reg["funkcije"])
    redovi = ["# 02 — Matrica istine o sposobnostima proizvoda (Website V2)", "",
              "> Generisano iz `site/funkcije.json` skriptom `scripts/gradi_sajt.py`. Ne menjati ručno.",
              f"> Produkcija u trenutku provere: `{reg['produkcija']}`; datum provere: {reg['verifikovano']}.", "",
              "Status određuje šta sajt sme da kaže. Javno se prikazuju samo stavke sa `javno: true` i statusom",
              "V2_AVAILABLE, AVAILABLE_WITH_LIMITATIONS i LEGACY_ONLY (katalog). PLANNED_APPROVED se od Website V3",
              "ne objavljuje (planovi razvoja nisu javni; /razvoj je povučen).", "",
              "## Statusi", "", "| Status | Javna oznaka | Značenje | Broj stavki |", "|---|---|---|---|"]
    for s, d in reg["statusi"].items():
        redovi.append(f"| `{s}` | {d['javno'] or '— (ne prikazuje se)'} | {d['opis']} | {br.get(s, 0)} |")
    redovi += ["", f"Ukupno stavki: {len(reg['funkcije'])}. Broj nije marketinški podatak; meri obuhvat inventara.", ""]
    kol = ["ID", "Naziv", "Šta korisnik radi", "Status", "Javno", "V2 ulaz", "Backend", "Pravo pristupa", "Test", "Ograničenje",
           "Podaci provere", "Javna formulacija", "Izvor odluke", "Provereno"]
    for o in reg["oblasti"]:
        st = [f for f in reg["funkcije"] if f["oblast"] == o["id"]]
        if not st:
            continue
        redovi += [f"## {o['id']}. {o['naziv']}", "", "| " + " | ".join(kol) + " |", "|" + "---|" * len(kol)]
        for f in st:
            cel = [f["id"], f["naziv"], f["radnja"], f"`{f['status']}`", "da" if f["javno"] else "ne", f["v2_ulaz"], f["backend"],
                   f["pravo"], f["test"], f["ogranicenje"] or "—", f["podaci"], f["javni_opis"] or "—", f["izvor"], f["verifikovano"]]
            redovi.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in cel) + " |")
        redovi.append("")
    return "\n".join(redovi)


def izgradi() -> dict[Path, str]:
    reg = registar()
    out = {SAJT / izlaz: stranica(reg, izvor, ruta, naslov, opis) for izvor, izlaz, ruta, naslov, opis, _ in STRANICE}
    out[KOREN / "docs" / "website-v2" / "02_PRODUCT_CAPABILITY_TRUTH_MATRIX.md"] = matrica(reg)
    return out


def main() -> int:
    provera = "--provera" in sys.argv
    razlike = []
    for put, sadrzaj in izgradi().items():
        if provera:
            if not put.exists() or put.read_bytes().decode("utf-8").replace("\r\n", "\n") != sadrzaj:
                razlike.append(put.relative_to(KOREN).as_posix())
        else:
            put.parent.mkdir(parents=True, exist_ok=True)
            put.write_bytes(sadrzaj.encode("utf-8"))
            print("upisano", put.relative_to(KOREN).as_posix())
    if razlike:
        print("NIJE USKLAĐENO (pokrenite python scripts/gradi_sajt.py):", ", ".join(razlike))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
