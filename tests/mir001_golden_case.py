# -*- coding: utf-8 -*-
"""MIR001 TASK-01 — Miroslavljev „Golden Case“: jedan sintetički parnični spis od sedam procesnih dokumenata,
jedan kasniji dokument (promena) i nepovezan predmet korisnika B za negativne ACL provere.

SVE JE SINTETIČKO: stranke, sud, brojevi, iznosi i datumi su izmišljeni i nose oznaku SINTETICKI. Nijedna stvarna
sudska odluka ni pravni autoritet se ne navodi; član ugovora (čl. 9 Ugovora 12/2024) je deo izmišljenog ugovora.

Tekst je bez dijakritika (ASCII), da isti tekst važi za reportlab PDF, pypdf ekstrakciju i Tesseract — tačnost
dijakritika u ekstrakciji je posebno dokazana u VCR002 T02 i ovde se ne meša sa merenjem razumevanja spisa.

Korpus je deterministički: isti bajtovi pri svakom generisanju (reportlab `invariant=1`, PyMuPDF `no_new_id`),
što meri `test_mir001_t01_golden_case.py`.
"""
import io

BROJ = "P 9901/2026"
SUD = "PRIVREDNI SUD U PRIMERGRADU (SINTETICKI)"
TUZILAC = "Alfa Fiktiv DOO"
TUZENI = "Beta Primer Gradnja DOO"

# ── Dokumenti spisa (redosled = redosled prijema = redni broj DOK-NN) ──────────────────────────────────────────────
# Svaki red je jedna rečenica; ključni navodi imaju stabilan ID (N-xx) u `NAVODI`.
DOKUMENTI = [
    {
        "oznaka": "DOK-01", "ime": "01 Tuzba.pdf", "vrsta": "tuzba", "strana": "tuzilac", "datum": "2026-02-10",
        "skeniran": False,
        "redovi": [
            SUD, f"Broj predmeta: {BROJ}", "TUZBA radi naknade stete (SINTETICKI PREDMET)",
            f"Tuzilac: {TUZILAC}, Primergrad", f"Tuzeni: {TUZENI}, Fiktivgrad",
            "Stranke su zakljucile Ugovor o gradjenju broj 12/2024 dana 15.03.2024. godine.",
            "Tuzeni je zavrsio radove na krovu hale dana 15.06.2025. godine.",
            "Prokisnjavanje krova hale primeceno je dana 02.09.2025. godine.",
            "Tuzeni je reklamaciju tuzioca primio dana 08.09.2025. godine.",
            "Clanom 9 Ugovora 12/2024 ugovoren je garantni rok od pet godina za krovne radove.",
            "Tuzilac trazi naknadu stete u iznosu od 4.200.000 dinara.",
            "Datum tuzbe: 10.02.2026. godine.",
        ],
    },
    {
        "oznaka": "DOK-02", "ime": "02 Odgovor na tuzbu.pdf", "vrsta": "odgovor_na_tuzbu", "strana": "tuzeni",
        "datum": "2026-03-12", "skeniran": False,
        "redovi": [
            SUD, f"Broj predmeta: {BROJ}", "ODGOVOR NA TUZBU (SINTETICKI PREDMET)",
            f"Tuzeni {TUZENI} osporava tuzbeni zahtev u celosti.",
            "Tuzeni je prvu reklamaciju tuzioca primio tek dana 20.11.2025. godine.",
            "Trece lice je postavilo solarne panele na krov hale dana 10.08.2025. godine.",
            "Tuzeni tvrdi da je prokisnjavanje posledica ugradnje solarnih panela od strane treceg lica.",
            "Datum odgovora: 12.03.2026. godine.",
        ],
    },
    {
        "oznaka": "DOK-03", "ime": "03 Podnesak tuzioca.pdf", "vrsta": "podnesak", "strana": "tuzilac",
        "datum": "2026-04-02", "skeniran": False,
        "redovi": [
            SUD, f"Broj predmeta: {BROJ}", "PODNESAK TUZIOCA (SINTETICKI PREDMET)",
            "Tuzilac tvrdi da su solarni paneli postavljeni tek dana 10.10.2025. godine, posle prokisnjavanja.",
            "Tuzilac prilaze povratnicu PK-4471 o urucenju reklamacije dana 08.09.2025. godine.",
            "Tuzilac dodatno trazi 600.000 dinara za ostecenu robu u hali.",
            "Datum podneska: 02.04.2026. godine.",
        ],
    },
    {
        "oznaka": "DOK-04", "ime": "04 Podnesak tuzenog.pdf", "vrsta": "podnesak", "strana": "tuzeni",
        "datum": "2026-04-20", "skeniran": False,
        "redovi": [
            SUD, f"Broj predmeta: {BROJ}", "PODNESAK TUZENOG (SINTETICKI PREDMET)",
            "Tuzeni predlaze vestacenje od strane vestaka gradjevinske struke.",
            "Tuzeni tvrdi da eventualna steta ne prelazi iznos od 1.100.000 dinara.",
            "Datum podneska: 20.04.2026. godine.",
        ],
    },
    {
        "oznaka": "DOK-05", "ime": "05 Nalaz i misljenje vestaka.pdf", "vrsta": "nalaz_vestaka", "strana": "vestak",
        "datum": "2026-06-15", "skeniran": True,
        "redovi": [
            "NALAZ I MISLJENJE VESTAKA",
            f"Broj predmeta: {BROJ}",
            "SINTETICKI PREDMET",
            "Vestak gradjevinske struke Petar Izmisljeni.",
            "Uzrok prokisnjavanja je neodgovarajuce",
            "izvedena hidroizolacija na spoju atike.",
            "Nosaci solarnih panela nisu ostetili",
            "hidroizolaciju krova.",
            "Visina stete iznosi 3.150.000 dinara.",
            "Datum nalaza: 15.06.2026. godine.",
        ],
    },
    {
        "oznaka": "DOK-06", "ime": "06 Izjasnjenje na nalaz vestaka.pdf", "vrsta": "podnesak", "strana": "tuzeni",
        "datum": "2026-07-01", "skeniran": False,
        "redovi": [
            SUD, f"Broj predmeta: {BROJ}", "IZJASNJENJE TUZENOG NA NALAZ VESTAKA (SINTETICKI PREDMET)",
            "Tuzeni osporava nalaz vestaka od 15.06.2026. godine.",
            "Tuzeni tvrdi da vestak nije izvrsio uvid u gradjevinski dnevnik.",
            "Tuzeni predlaze dopunu vestacenja.",
            "Datum izjasnjenja: 01.07.2026. godine.",
        ],
    },
    {
        "oznaka": "DOK-07", "ime": "07 Zapisnik sa rocista.pdf", "vrsta": "zapisnik", "strana": "sud",
        "datum": "2026-07-15", "skeniran": False,
        "redovi": [
            SUD, f"Broj predmeta: {BROJ}", "ZAPISNIK SA ROCISTA (SINTETICKI PREDMET)",
            "Rociste odrzano dana 15.07.2026. godine.",
            "Uvidom u gradjevinsku dozvolu utvrdjeno je da je izdata dana 01.02.2024. godine.",
            "Sud prihvata predlog za dopunu vestacenja.",
            "Sud nalaze tuzenom da dostavi gradjevinski dnevnik u roku od 15 dana.",
            "Tuzilac je precizirao tuzbeni zahtev na iznos od 3.150.000 dinara.",
            "Tuzilac povlaci zahtev za naknadu stete na robi od 600.000 dinara.",
            "Sledece rociste zakazano je za 18.11.2026. godine.",
        ],
    },
]

# Kasnija promena (TASK-07/08): dopuna nalaza sa novim rokom — materijalno značajna, menja sledeće radnje.
KASNIJI = {
    "oznaka": "DOK-08", "ime": "08 Dopuna nalaza vestaka.pdf", "vrsta": "nalaz_vestaka", "strana": "vestak",
    "datum": "2026-10-20", "skeniran": False,
    "redovi": [
        SUD, f"Broj predmeta: {BROJ}", "DOPUNA NALAZA I MISLJENJA VESTAKA (SINTETICKI PREDMET)",
        "Vestak je izvrsio uvid u gradjevinski dnevnik.",
        "Gradjevinski dnevnik ne sadrzi upis o probi vodonepropusnosti krova.",
        "Vestak ostaje pri nalazu da je uzrok prokisnjavanja izvodjacka greska.",
        "Sud ostavlja strankama rok od 8 dana od dana dopune nalaza za izjasnjenje.",
        "Datum dopune: 20.10.2026. godine.",
    ],
}

# ── Očekivani nalazi (izvor istine testova) ─────────────────────────────────────────────────────────────────────────
# status: NAVOD_TUZIOCA / NAVOD_TUZENOG / NALAZ_VESTAKA / SUD (procesna radnja suda, ne utvrđena materijalna činjenica)
NAVODI = {
    "N-01": {"dok": "DOK-01", "status": "NAVOD_TUZIOCA", "tekst": "reklamaciju tuzioca primio dana 08.09.2025"},
    "N-02": {"dok": "DOK-01", "status": "NAVOD_TUZIOCA", "tekst": "garantni rok od pet godina"},
    "N-03": {"dok": "DOK-01", "status": "NAVOD_TUZIOCA", "tekst": "4.200.000 dinara"},
    "N-04": {"dok": "DOK-02", "status": "NAVOD_TUZENOG", "tekst": "primio tek dana 20.11.2025"},
    "N-05": {"dok": "DOK-02", "status": "NAVOD_TUZENOG", "tekst": "solarne panele na krov hale dana 10.08.2025"},
    "N-06": {"dok": "DOK-03", "status": "NAVOD_TUZIOCA", "tekst": "postavljeni tek dana 10.10.2025"},
    "N-07": {"dok": "DOK-03", "status": "NAVOD_TUZIOCA", "tekst": "600.000 dinara za ostecenu robu"},
    "N-08": {"dok": "DOK-04", "status": "NAVOD_TUZENOG", "tekst": "ne prelazi iznos od 1.100.000 dinara"},
    "N-09": {"dok": "DOK-05", "status": "NALAZ_VESTAKA", "tekst": "hidroizolacija na spoju atike"},
    "N-10": {"dok": "DOK-05", "status": "NALAZ_VESTAKA", "tekst": "Visina stete iznosi 3.150.000"},
    "N-11": {"dok": "DOK-06", "status": "NAVOD_TUZENOG", "tekst": "nije izvrsio uvid u gradjevinski dnevnik"},
    "N-12": {"dok": "DOK-07", "status": "SUD", "tekst": "dostavi gradjevinski dnevnik u roku od 15 dana"},
    "N-13": {"dok": "DOK-07", "status": "SUD", "tekst": "povlaci zahtev za naknadu stete na robi"},
    "N-14": {"dok": "DOK-07", "status": "SUD", "tekst": "zakazano je za 18.11.2026"},
    "N-15": {"dok": "DOK-07", "status": "SUD", "tekst": "precizirao tuzbeni zahtev na iznos od 3.150.000"},
}

# Zastareo navod: tužbeni zahtev iz tužbe (N-03, 4.200.000) više nije aktuelan — preciziran na ročištu (N-15).
AKTUELNI_ZAHTEV = {"zamenjen": "N-03", "aktuelan": "N-15", "iznos": "3.150.000"}

# Dokaziva protivrečnost između strana (nikad „saglasnost“)
PROTIVRECNOSTI = [
    {"id": "K-01", "pitanje": "datum prijema reklamacije", "strane": ("N-01", "N-04"),
     "vrednosti": ("08.09.2025", "20.11.2025")},
    {"id": "K-02", "pitanje": "datum postavljanja solarnih panela", "strane": ("N-05", "N-06"),
     "vrednosti": ("10.08.2025", "10.10.2025")},
]

# Ispravan hronološki sled ključnih događaja (datum događaja, ne datum dokumenta)
HRONOLOGIJA = [
    ("2024-02-01", "izdata gradjevinska dozvola (utvrdjeno uvidom na rocistu)", "DOK-07"),
    ("2024-03-15", "zakljucen Ugovor 12/2024", "DOK-01"),
    ("2025-06-15", "zavrseni radovi na krovu", "DOK-01"),
    ("2025-09-02", "primeceno prokisnjavanje", "DOK-01"),
    ("2026-02-10", "tuzba", "DOK-01"),
    ("2026-03-12", "odgovor na tuzbu", "DOK-02"),
    ("2026-06-15", "nalaz vestaka", "DOK-05"),
    ("2026-07-15", "rociste", "DOK-07"),
    ("2026-11-18", "sledece rociste", "DOK-07"),
]
# Sporni datumi (K-01/K-02) nemaju jedan ispravan položaj: obe verzije se prikazuju kao sporne, uz izvor.

# Činjenice samo u dokumentima VAN pet najnovijih (DOK-03..07 su najnoviji)
STARE_CINJENICE = ["N-02", "N-05"]

# Činjenica koja menja očekivanu procenu: nalaz pripisuje uzrok izvođaču i odbacuje tezu o panelima,
# ali smanjuje visinu štete u odnosu na tužbu.
PRELOMNA = {"navod": "N-09", "menja": "uzrok stete: izvodjacka greska, ne paneli (N-05/teza tuzenog)", "iznos": "N-10"}

# Namerno NEDOSTUPNO u spisu (odgovor mora biti „nije u spisu“, ne nagađanje)
NEDOSTUPNO = [
    # Pre DOK-08: sadržaj dnevnika potpuno nepoznat. Posle DOK-08: i dalje nema sadržaja za jun 2025; poznato je SAMO
    # (iz veštakovog uvida, ne iz samog dnevnika) da nema upisa o probi vodonepropusnosti.
    {"pitanje": "Sta tacno pise u gradjevinskom dnevniku za jun 2025?", "razlog": "dnevnik nikad nije dostavljen u spis",
     "posle_DOK_08": "sadrzaj za jun 2025 i dalje nedostupan; poznato samo: nema upisa o probi vodonepropusnosti (uvid vestaka)"},
    {"pitanje": "Kako se zove odgovorni izvodjac radova tuzenog?", "razlog": "ime nije navedeno ni u jednom dokumentu",
     "posle_DOK_08": "i dalje nedostupno"},
]

# Povučen navod (sadržinski): N-07 povučen u DOK-07 (N-13). Test zastarelosti izvora: brisanje DOK-03 iz predmeta
# mora povući i njegove AI tvrdnje (N-06, N-07) — više ne smeju biti aktivne ni autoritativne.
POVUCENO = {"sadrzinski": {"navod": "N-07", "povlaci": "N-13"}, "brisanje_izvora": "DOK-03"}

# Kasnija promena: novi rok iz DOK-08 (8 dana od dopune) → očekivana nova radnja; isti događaj ponovljen = bez duplikata.
# Rok teče „od dana dopune nalaza“ (izričito u tekstu DOK-08), pa je 2026-10-28 izračunljiv bez pretpostavke o dostavi.
# Testovi koji zavise od „danas“ koriste SADA (zamrznuto) ili pomeraju datume relativno — korpus ne zastareva.
SADA = "2026-10-22"
KASNIJA_PROMENA = {"dok": "DOK-08", "rok_dana": 8, "od": "2026-10-20", "rok": "2026-10-28",
                   "navod": "ne sadrzi upis o probi vodonepropusnosti"}

# ── Korisnik B: nepovezan predmet, jedinstven marker za otkrivanje curenja ──────────────────────────────────────────
B_MARKER = "SIFRA-B-77Q"
B_PREDMET = {"naziv": "Gama Test protiv Delta Test (SINTETICKI)", "tip": "Privredni spor"}
B_DOKUMENT = {"ime": "B Ugovor.pdf", "redovi": ["UGOVOR (SINTETICKI, KORISNIK B)", f"Interna oznaka: {B_MARKER}",
                                                  "Iznos: 777.777 dinara."], "skeniran": False}


# ── Generatori (deterministički) ────────────────────────────────────────────────────────────────────────────────────
def digitalni_pdf(redovi) -> bytes:
    """Digitalni PDF sa tekstualnim slojem; `invariant=1` uklanja datum i slučajni ID → isti bajtovi."""
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b, invariant=1)
    for i, red in enumerate(redovi):
        c.drawString(50, 790 - i * 22, red)
    c.showPage()
    c.save()
    return b.getvalue()


def skeniran_pdf(redovi) -> bytes:
    """Skenirana strana BEZ tekstualnog sloja (rasterizovan tekst, 200 dpi). Tekst je unapred poznat (`redovi`)."""
    import fitz
    izvor = fitz.open()
    s = izvor.new_page(width=595, height=842)
    tw = fitz.TextWriter(s.rect)
    for i, red in enumerate(redovi):
        tw.append((50, 80 + i * 30), red, font=fitz.Font("helv"), fontsize=18)
    tw.write_text(s)
    png = s.get_pixmap(dpi=200).tobytes("png")
    izvor.close()
    sken = fitz.open()
    s2 = sken.new_page(width=595, height=842)
    s2.insert_image(s2.rect, stream=png)
    b = io.BytesIO()
    sken.save(b, no_new_id=True)
    sken.close()
    return b.getvalue()


def bajtovi(dok: dict) -> bytes:
    return skeniran_pdf(dok["redovi"]) if dok["skeniran"] else digitalni_pdf(dok["redovi"])


def tekst(dok: dict) -> str:
    return "\n".join(dok["redovi"])


def po_oznaci(oznaka: str) -> dict:
    return next(d for d in DOKUMENTI + [KASNIJI] if d["oznaka"] == oznaka)

