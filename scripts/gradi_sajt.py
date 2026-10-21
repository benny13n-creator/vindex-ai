"""Vindex — gradi javni sajt (Website V2) iz izvora i registra funkcija.

    python scripts/gradi_sajt.py            # upisuje site/*.html i docs/website-v2/02_…md
    python scripts/gradi_sajt.py --provera  # ne upisuje; izlaz 1 ako generisano ≠ sačuvano

Izvori:
  site/_izvor/<strana>.html  — sadržaj <main> svake stranice
  site/funkcije.json         — jedini izvor istine za katalog (/funkcionalnosti), razvoj (/razvoj)
                               i matricu dokaza (docs/website-v2/02_PRODUCT_CAPABILITY_TRUTH_MATRIX.md)
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
    ("index", "index.html", "/", "Vindex — manje traženja, više vremena za važne odluke",
     "Vindex povezuje dokumente, činjenice i izvore sa radnim koracima kako biste manje vremena trošili na traženje.", None),
    ("kako-radi", "kako-radi.html", "/kako-radi", "Kako radi — Vindex",
     "Tok rada u Vindexu od otvaranja predmeta do odluke advokata: šta radite vi, šta radi Vindex i gde je potrebna vaša potvrda.", "Kako radi"),
    ("funkcionalnosti", "funkcionalnosti.html", "/funkcionalnosti", "Funkcionalnosti — Vindex",
     "Pregled funkcionalnosti Vindexa: predmeti, dokumenti, dokazi, rokovi, pravno istraživanje i nacrti.", "Funkcionalnosti"),
    ("za-advokate", "za-advokate.html", "/za-advokate", "Za advokate — Vindex",
     "Primeri toka rada u advokatskoj kancelariji sa funkcijama koje danas postoje u Vindexu, uz granice svake funkcije.", "Za advokate"),
    ("bezbednost", "bezbednost.html", "/bezbednost", "Bezbednost i zaštita podataka — Vindex",
     "Kako Vindex kontroliše pristup, ko obrađuje dokumente i kako funkcioniše izvoz podataka.", "Bezbednost"),
    ("beta", "beta.html", "/beta", "Rani pristup — Vindex",
     "Prijavite interesovanje za kontrolisani rani pristup Vindex radnom prostoru.", None),
]
JAVNI_STATUSI = ["V2_AVAILABLE", "AVAILABLE_WITH_LIMITATIONS", "LEGACY_ONLY"]
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
    <a class="logo" href="/" aria-label="Vindex — početna"><img src="/v2/site/brand/Vindex_Transparent_EXACT_LOOK.svg" alt="" width="1183" height="309"></a>
    <nav aria-label="Glavna navigacija"><ul class="meni">{meni}</ul></nav>
    <div class="zaglavlje__akcije">
      <a class="dugme dugme--sporedno dugme--malo" href="/app">Prijava</a>
      <a class="dugme dugme--malo" href="/beta">Rani pristup</a>
    </div>
    <details class="meni-mob">
      <summary>Meni</summary>
      <div class="meni-mob__panel">
        <nav aria-label="Glavna navigacija (mobilni prikaz)"><ul>{meni}</ul></nav>
        <div class="meni-mob__akcije">
          <a class="dugme dugme--malo" href="/beta">Rani pristup</a>
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
        <p>Radni prostor za predmete, dokumente, rokove i pravni rad advokatske kancelarije. U kontrolisanom beta testiranju.</p>
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


def status_oznaka(reg: dict, st: str) -> str:
    return f'<span class="status status--{st}">{e(reg["statusi"][st]["javno"])}</span>'


def katalog(reg: dict) -> tuple[str, str]:
    javne = [f for f in reg["funkcije"] if f["javno"] and f["status"] in JAVNI_STATUSI]
    nav, delovi = [], []
    for o in reg["oblasti"]:
        stavke = [f for f in javne if f["oblast"] == o["id"]]
        if not stavke:
            continue
        nav.append(f'<li><a href="#{o["sidro"]}">{e(o["naziv"])}</a></li>')
        redovi = []
        for f in stavke:
            gde = ("U klasičnom interfejsu aplikacije" if f["status"] == "LEGACY_ONLY"
                   else "U aplikaciji: " + f["v2_ulaz"].replace("/app → ", ""))
            redovi.append(
                f'<li class="stavka" id="f-{f["id"]}" data-id="{f["id"]}" data-status="{f["status"]}">'
                f'<div><h3>{e(f["naziv"])}</h3><p>{e(f["javni_opis"])}</p><p class="stavka__gde">{e(gde)}</p></div>'
                f'<div class="stavka__status">{status_oznaka(reg, f["status"])}</div></li>')
        delovi.append(f'<section class="oblast" id="{o["sidro"]}" aria-labelledby="o-{o["sidro"]}">'
                      f'<h2 id="o-{o["sidro"]}">{e(o["naziv"])}</h2><ul class="stavke">{"".join(redovi)}</ul></section>')
    opcije = "".join(f'<option value="{s}">{e(reg["statusi"][s]["javno"])}</option>' for s in JAVNI_STATUSI)
    sadrzaj = f"""<div class="katalog">
      <nav class="katalog__nav" aria-label="Oblasti"><ul>{"".join(nav)}</ul></nav>
      <div id="katalog-stavke">
        <div class="filter" id="filter" hidden>
          <div class="filter__polje"><label for="filter-tekst">Pretraga funkcija</label><input id="filter-tekst" type="search" autocomplete="off"></div>
          <div><label for="filter-status">Status</label><select id="filter-status"><option value="">Svi statusi</option>{opcije}</select></div>
          <p class="filter__rezultat" id="filter-rezultat" role="status" aria-live="polite"></p>
        </div>
        {"".join(delovi)}
      </div>
    </div>"""
    legenda = "".join(f'<li>{status_oznaka(reg, s)} <span class="tiho">{e(t)}</span></li>' for s, t in [
        ("V2_AVAILABLE", "radi u aplikaciji V2"),
        ("AVAILABLE_WITH_LIMITATIONS", "radi u aplikaciji, uz navedenu granicu"),
        ("LEGACY_ONLY", "radi samo u klasičnom interfejsu aplikacije")])
    return sadrzaj, f'<ul class="legenda" aria-label="Značenje statusa">{legenda}</ul>'


def razvoj(reg: dict) -> str:
    out = []
    for f in reg["funkcije"]:
        if not (f["javno"] and f["status"] == "PLANNED_APPROVED"):
            continue
        out.append(f"""<article class="plan" id="f-{f["id"]}" data-id="{f["id"]}" data-status="{f["status"]}" aria-labelledby="p-{f["id"]}">
      <div><h2 id="p-{f["id"]}">{e(f["naziv"])}</h2>{status_oznaka(reg, f["status"])}</div>
      <dl>
        <div><dt>Šta je planirano</dt><dd>{e(f["javni_opis"])}</dd></div>
        <div><dt>Problem koji rešava</dt><dd>{e(f["problem"])}</dd></div>
        <div><dt>Šta postoji danas</dt><dd>{e(f["umesto"])}</dd></div>
        <div><dt>Dostupnost</dt><dd>Nije dostupno. Datum isporuke nije određen.</dd></div>
      </dl>
    </article>""")
    return "\n    ".join(out)


def stranica(reg: dict, izvor: str, ruta: str, naslov: str, opis: str) -> str:
    telo = (SAJT / "_izvor" / f"{izvor}.html").read_text(encoding="utf-8")
    if "<!--KATALOG-->" in telo:
        k, legenda = katalog(reg)
        telo = telo.replace("<!--KATALOG-->", k).replace("<!--STATUSI-->", legenda)
    if "<!--RAZVOJ-->" in telo:
        telo = telo.replace("<!--RAZVOJ-->", razvoj(reg))
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
<link rel="icon" type="image/png" href="/static/favicon-vindex-32.png">
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
              "V2_AVAILABLE, AVAILABLE_WITH_LIMITATIONS i LEGACY_ONLY (katalog) ili PLANNED_APPROVED (razvoj).", "",
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
