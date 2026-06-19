# -*- coding: utf-8 -*-
"""
Katalog srpskih sudova sa adresama — za automatsko popunjavanje zaglavlja podnesaka.
Struktura: {kategorija: [{naziv, adresa, grad, nadleznost}]}
"""

SUDOVI: dict[str, list[dict]] = {
    "Osnovni sudovi": [
        {"naziv": "Osnovi sud u Beogradu",      "adresa": "Ustanička 29, 11000 Beograd",       "grad": "Beograd"},
        {"naziv": "Osnovni sud u Novom Sadu",   "adresa": "Sutješka 3, 21000 Novi Sad",         "grad": "Novi Sad"},
        {"naziv": "Osnovni sud u Nišu",          "adresa": "Vojvode Putnika 1, 18000 Niš",       "grad": "Niš"},
        {"naziv": "Osnovni sud u Kragujevcu",   "adresa": "Jovana Cvijića 1, 34000 Kragujevac", "grad": "Kragujevac"},
        {"naziv": "Osnovni sud u Subotici",     "adresa": "Trg cara Jovana Nenada 15, 24000 Subotica", "grad": "Subotica"},
        {"naziv": "Osnovni sud u Čačku",        "adresa": "Gradski trg 1, 32000 Čačak",         "grad": "Čačak"},
        {"naziv": "Osnovni sud u Pančevu",      "adresa": "Zmaj Jovina 2, 26000 Pančevo",       "grad": "Pančevo"},
        {"naziv": "Osnovni sud u Šapcu",        "adresa": "Vojvode Putnika 10, 15000 Šabac",    "grad": "Šabac"},
        {"naziv": "Osnovni sud u Vranju",       "adresa": "Pana Đukića 1, 17500 Vranje",        "grad": "Vranje"},
        {"naziv": "Osnovni sud u Kraljevu",     "adresa": "Trg Jovana Sarića 2, 36000 Kraljevo","grad": "Kraljevo"},
        {"naziv": "Osnovni sud u Užicu",        "adresa": "Dimitrija Tucovića 52, 31000 Užice", "grad": "Užice"},
        {"naziv": "Osnovni sud u Valjevu",      "adresa": "Karađorđeva 48, 14000 Valjevo",      "grad": "Valjevo"},
        {"naziv": "Osnovni sud u Zrenjaninu",   "adresa": "Trg slobode 10, 23000 Zrenjanin",    "grad": "Zrenjanin"},
        {"naziv": "Osnovni sud u Leskovcu",     "adresa": "Pane Đukića 14, 16000 Leskovac",     "grad": "Leskovac"},
        {"naziv": "Osnovni sud u Zaječaru",     "adresa": "Nikole Pašića 4, 19000 Zaječar",     "grad": "Zaječar"},
    ],
    "Viši sudovi": [
        {"naziv": "Viši sud u Beogradu",        "adresa": "Savska 17a, 11000 Beograd",          "grad": "Beograd"},
        {"naziv": "Viši sud u Novom Sadu",      "adresa": "Sutješka 3, 21000 Novi Sad",         "grad": "Novi Sad"},
        {"naziv": "Viši sud u Nišu",             "adresa": "Nikole Pašića 24, 18000 Niš",        "grad": "Niš"},
        {"naziv": "Viši sud u Kragujevcu",      "adresa": "Jovana Cvijića 1, 34000 Kragujevac", "grad": "Kragujevac"},
        {"naziv": "Viši sud u Novom Pazaru",    "adresa": "Stevana Nemanje 2, 36300 Novi Pazar","grad": "Novi Pazar"},
        {"naziv": "Viši sud u Subotici",        "adresa": "Trg cara Jovana Nenada 15, 24000 Subotica","grad": "Subotica"},
    ],
    "Apelacioni sudovi": [
        {"naziv": "Apelacioni sud u Beogradu",      "adresa": "Nemanjina 9, 11000 Beograd",         "grad": "Beograd"},
        {"naziv": "Apelacioni sud u Novom Sadu",    "adresa": "Sutješka 1, 21000 Novi Sad",          "grad": "Novi Sad"},
        {"naziv": "Apelacioni sud u Nišu",           "adresa": "Nikole Pašića 24, 18000 Niš",         "grad": "Niš"},
        {"naziv": "Apelacioni sud u Kragujevcu",    "adresa": "Jovana Cvijića 1, 34000 Kragujevac",  "grad": "Kragujevac"},
    ],
    "Privredni sudovi": [
        {"naziv": "Privredni sud u Beogradu",   "adresa": "Masarikova 2, 11000 Beograd",        "grad": "Beograd"},
        {"naziv": "Privredni sud u Novom Sadu", "adresa": "Sutješka 1, 21000 Novi Sad",          "grad": "Novi Sad"},
        {"naziv": "Privredni sud u Nišu",        "adresa": "Nikole Pašića 24, 18000 Niš",         "grad": "Niš"},
        {"naziv": "Privredni sud u Kragujevcu", "adresa": "Jovana Cvijića 1, 34000 Kragujevac",  "grad": "Kragujevac"},
        {"naziv": "Privredni sud u Subotici",   "adresa": "Markovićeva 7, 24000 Subotica",        "grad": "Subotica"},
        {"naziv": "Privredni sud u Zrenjaninu", "adresa": "Trg slobode 10, 23000 Zrenjanin",      "grad": "Zrenjanin"},
        {"naziv": "Privredni sud u Čačku",      "adresa": "Gradski trg 1, 32000 Čačak",           "grad": "Čačak"},
        {"naziv": "Privredni sud u Valjevu",    "adresa": "Karađorđeva 48, 14000 Valjevo",        "grad": "Valjevo"},
        {"naziv": "Privredni apelacioni sud",   "adresa": "Masarikova 2, 11000 Beograd",          "grad": "Beograd"},
    ],
    "Upravni i Vrhovni": [
        {"naziv": "Vrhovni kasacioni sud",      "adresa": "Nemanjina 9, 11000 Beograd",         "grad": "Beograd"},
        {"naziv": "Upravni sud",                "adresa": "Nemanjina 9, 11000 Beograd",         "grad": "Beograd"},
        {"naziv": "Ustavni sud",                "adresa": "Bulevar kralja Aleksandra 15, 11000 Beograd", "grad": "Beograd"},
    ],
}


def get_all_courts() -> list[dict]:
    """Vraća flat listu svih sudova sa kategorijom."""
    result = []
    for kategorija, lista in SUDOVI.items():
        for s in lista:
            result.append({**s, "kategorija": kategorija})
    return result


def find_court(naziv: str) -> dict | None:
    """Pronalazi sud po tačnom ili delimičnom nazivu."""
    naziv_low = naziv.lower()
    for s in get_all_courts():
        if naziv_low in s["naziv"].lower():
            return s
    return None
