# -*- coding: utf-8 -*-
"""
Phase 3.6 — Kalkulator zastarelosti po srpskom pravu.
ZOO, ZR, ZPP, ZIO, ZOM, ZZP, ZUP, ZUS, ZKP rokovi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta


@dataclass
class ZastarelostRezultat:
    tip_potrazivanja:  str
    zakonski_osnov:    str
    rok_godina:        int
    rok_opis:          str
    datum_pocetka:     date
    datum_zastarelosti: date
    dana_preostalo:    int   # negativno = isteklo
    isteklo:           bool
    napomena:          str


# ─── Katalog rokova zastarelosti ─────────────────────────────────────────────
# Svaki unos: "naziv", "osnov", "opis", i JEDAN od: "godine" | "meseci" | "dani"
ROKOVI_ZASTARELOSTI: dict[str, dict] = {
    "opsti": {
        "naziv": "Opšti rok zastarelosti",
        "osnov": "ZOO čl. 371",
        "godine": 10,
        "opis":   "Ugovorna i vanugovorna potraživanja — opšti rok",
    },
    "privreda": {
        "naziv": "Međusobna potraživanja privrednih subjekata",
        "osnov": "ZOO čl. 374",
        "godine": 3,
        "opis":   "Potraživanja iz privrednih ugovora između privrednih subjekata",
    },
    "periodicna": {
        "naziv": "Periodična potraživanja (kirija, kamata, alimentacija)",
        "osnov": "ZOO čl. 372",
        "godine": 3,
        "opis":   "Godišnje i kraće periodične obaveze, uključujući kamate",
    },
    "radni_spor": {
        "naziv": "Potraživanja iz radnog odnosa",
        "osnov": "ZR čl. 196",
        "godine": 3,
        "opis":   "Potraživanja zaposlenog prema poslodavcu iz radnog odnosa",
    },
    "naknada_stete": {
        "naziv": "Naknada štete — subjektivni rok",
        "osnov": "ZOO čl. 376 st. 1",
        "godine": 3,
        "opis":   "Od saznanja za štetu i učinioca (subjektivni rok)",
        "napomena": "Subjektivni rok — teče od saznanja. Proverite i objektivni rok (5 god. od nastanka štete, ZOO čl. 376 st. 2).",
    },
    "naknada_stete_obj": {
        "naziv": "Naknada štete — objektivni rok",
        "osnov": "ZOO čl. 376 st. 2",
        "godine": 5,
        "opis":   "Od nastanka štete bez obzira na saznanje",
    },
    "saobracan_udes": {
        "naziv": "Naknada štete — saobraćajna nezgoda",
        "osnov": "ZOO čl. 378",
        "godine": 3,
        "opis":   "Od dana saznanja za štetu i odgovorno lice",
    },
    "potroskac": {
        "naziv": "Potrošačka potraživanja",
        "osnov": "ZZP čl. 22",
        "godine": 3,
        "opis":   "Potraživanja potrošača prema trgovcu",
    },
    "komunalne": {
        "naziv": "Komunalne usluge (struja, voda, gas, telefon)",
        "osnov": "ZOO čl. 372",
        "godine": 3,
        "opis":   "Mesečna i kvartalna potraživanja komunalnih preduzeća",
    },
    "menjacki": {
        "naziv": "Mjenični zahtev (imac prema akceptantu)",
        "osnov": "ZOM čl. 93",
        "godine": 3,
        "opis":   "Zahtev imaoca prema akceptantu od dospelosti menice",
        "napomena": "Zahtev imaoca prema indosantima zastareva za 1 godinu od dana protesta.",
    },
    "cek": {
        "naziv": "Čekovni zahtev imaoca prema trasantu",
        "osnov": "ZOM čl. 186",
        "meseci": 6,
        "opis":   "Zahtev imaoca čeka prema trasantu",
        "napomena": "Rok za prezentaciju čeka je 8 dana (lokalni) ili 20 dana (isti država). Zastarelost teče od isteka roka prezentacije.",
    },
    "zalbeni_upravni": {
        "naziv": "Žalba u upravnom postupku",
        "osnov": "ZUP čl. 147",
        "dani":  15,
        "opis":  "Rok za žalbu na prvostepeno rešenje — 15 dana od dostavljanja",
    },
    "tuzba_upravni_spor": {
        "naziv": "Tužba u upravnom sporu",
        "osnov": "ZUS čl. 18",
        "dani":  30,
        "opis":  "Rok za pokretanje upravnog spora — 30 dana od dostavljanja",
    },
    "zalbeni_krivicni": {
        "naziv": "Žalba na presudu (krivični postupak)",
        "osnov": "ZKP čl. 362",
        "dani":  15,
        "opis":  "Rok za žalbu na prvostepenu presudu — 15 dana od dostavljanja",
    },
    "revizija": {
        "naziv": "Revizija (ZPP)",
        "osnov": "ZPP čl. 393",
        "dani":  30,
        "opis":  "Rok za izjavljivanje revizije — 30 dana od dostavljanja presude",
    },
    "izvrsenje": {
        "naziv": "Predlog za izvršenje",
        "osnov": "ZIO čl. 52",
        "godine": 10,
        "opis":  "Rok za podnošenje predloga za izvršenje na osnovu izvršne isprave",
    },
}


def kalkulisi_zastarelost(tip: str, datum_pocetka: date) -> ZastarelostRezultat:
    """Kalkuliše datum zastarelosti za dati tip potraživanja od datuma početka."""
    if tip not in ROKOVI_ZASTARELOSTI:
        raise ValueError(f"Nepoznat tip zastarelosti: {tip!r}")

    r = ROKOVI_ZASTARELOSTI[tip]
    danas = date.today()

    if r.get("dani"):
        datum_zastarelosti = datum_pocetka + timedelta(days=r["dani"])
        rok_opis = f"{r['dani']} dana"
        rok_godina = 0
    elif r.get("meseci"):
        datum_zastarelosti = datum_pocetka + relativedelta(months=r["meseci"])
        rok_opis = f"{r['meseci']} meseci"
        rok_godina = 0
    else:
        g = r["godine"]
        datum_zastarelosti = datum_pocetka + relativedelta(years=g)
        rok_opis = f"{g} {'godina' if g >= 5 else 'godine'}"
        rok_godina = g

    dana_preostalo = (datum_zastarelosti - danas).days
    isteklo = dana_preostalo < 0

    return ZastarelostRezultat(
        tip_potrazivanja=r["naziv"],
        zakonski_osnov=r["osnov"],
        rok_godina=rok_godina,
        rok_opis=rok_opis,
        datum_pocetka=datum_pocetka,
        datum_zastarelosti=datum_zastarelosti,
        dana_preostalo=dana_preostalo,
        isteklo=isteklo,
        napomena=r.get("napomena", ""),
    )


_RE_RELATIVNI = re.compile(
    r"^(za|pre)\s+(\d+)\s+"
    r"(dan|dana|nedelju|nedelja|nedelje|mesec|meseca|meseci|godinu|godini|godina|godine)"
    r"\s*$",
    re.IGNORECASE,
)


def parsiraj_relativni_datum(izraz: str) -> date:
    """
    Parsira relativni srpski vremenski izraz u apsolutni datum.
    Primeri: 'za 30 dana', 'pre 2 meseca', 'za 1 godinu', 'za 3 nedelje'
    """
    m = _RE_RELATIVNI.match(izraz.strip())
    if not m:
        raise ValueError(
            f"Nepoznat relativni izraz: {izraz!r}. "
            "Koristite: 'za N dana/nedelja/meseci/godina' ili "
            "'pre N dana/nedelja/meseci/godina'"
        )

    smer, broj_str, jedinica = m.groups()
    n = int(broj_str)
    jedinica = jedinica.lower()

    if jedinica in ("dan", "dana"):
        delta = timedelta(days=n)
    elif jedinica in ("nedelju", "nedelja", "nedelje"):
        delta = timedelta(weeks=n)
    elif jedinica in ("mesec", "meseca", "meseci"):
        delta = relativedelta(months=n)
    else:  # godinu, godini, godina, godine
        delta = relativedelta(years=n)

    danas = date.today()
    return danas + delta if smer.lower() == "za" else danas - delta


def lista_tipova_zastarelosti() -> list[dict]:
    """Vraća listu svih tipova za frontend dropdown."""
    return [
        {
            "kljuc": k,
            "naziv": v["naziv"],
            "osnov": v["osnov"],
            "opis":  v["opis"],
        }
        for k, v in ROKOVI_ZASTARELOSTI.items()
    ]
