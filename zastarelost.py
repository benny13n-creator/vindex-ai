# -*- coding: utf-8 -*-
"""
Phase 3.6 — Kalkulator zastarelosti i procesnih rokova po srpskom pravu.
N4 (2026-10-27): katalog proveren prema lokalnim tekstovima zakona (ZOO, ZR, ZPP, ZIO, ZUP, ZUS, ZKP);
poslednji dan na neradni dan se pomera po pravilu o računanju rokova (shared/neradni_dani.py).
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
    datum_zastarelosti: date            # pravno poslednji dan (posle pomeranja sa neradnog dana)
    dana_preostalo:    int   # negativno = isteklo
    isteklo:           bool
    napomena:          str
    vrsta:             str = "zastarelost"          # "zastarelost" | "procesni"
    kalendarski_poslednji_dan: Optional[date] = None
    pomereno_razlog:   str = ""                     # "nedelju" / "subotu" / "državni praznik" kad je pomereno
    pravilo_racunanja: str = ""
    izvor_neradnih_dana: str = ""


# ─── Katalog ─────────────────────────────────────────────────────────────────
# N4 (2026-10-27): SVAKA stavka je proverena prema lokalnom tekstu zakona (data/laws/pdfs, UTF-8 tekst; verzije
# u zaglavljima: ZOO 18/2020, ZPP 10/2023, ZKP 62/2021, ZUP 2/2023-US, ZUS 111/2009, ZIO 91/2025, ZR 109/2025).
# Uklonjene su stavke koje lokalni tekst ne potvrđuje ili koje su bile pogrešne: „potrošačka“ (ZZP čl. 22 je o
# nasrtljivoj praksi), „nasledna potraživanja“ (ZN čl. 142 je podisporuka; pravo na zaostavštinu ne zastareva,
# čl. 221), „predlog za izvršenje 10 god.“ (nije pravilo ZIO — ispravno: ZOO čl. 379), „vanredno preispitivanje“
# (ne postoji u ZUP), „saobraćajna nezgoda ZOO 378“ (čl. 378 je jednogodišnji rok; opšte pravilo je čl. 376),
# „šteta od krivičnog dela“ (čl. 377 nema fiksni rok — zavisi od KZ), menica/ček/poreski (zakoni nisu lokalni).
# Ispravljeni članovi i rokovi: komunalne → ZOO 378 (1 god., domaćinstvo); žalba ZPP 367 (bilo 357); revizija 403
# (bilo 393); prigovor na platni nalog 457 (bilo 459); povraćaj 110 (bilo 113); ZUP žalba 153 (bilo 147);
# ZKP žalba 432 (bilo 362); neosnovano lišenje slobode ZKP 591, 3 god. (bilo 588, 6 meseci).
# `racunanje` = pravilo za poslednji dan na neradni dan (ZPP čl. 103 st. 5 izričito važi i za zastarelost).
_ZPP = "ZPP čl. 103 st. 4–5: ako poslednji dan pada u nedelju, na državni praznik ili drugi dan kad sud ne radi (ovde: i subota), rok ističe protekom prvog narednog radnog dana"
_ZUP = "ZUP čl. 80 st. 5: ako poslednji dan pada na dan u kome organ ne radi, rok ističe kad protekne prvi naredni radni dan"
_ZKP = "ZKP čl. 224: ako poslednji dan pada na državni praznik, subotu ili nedelju, rok ističe protekom prvog narednog radnog dana"
_ZIO = "ZIO čl. 39 → ZPP čl. 103 st. 4"
_ZUS = "ZUS čl. 74 → ZPP čl. 103 st. 4–5"

ROKOVI_ZASTARELOSTI: dict[str, dict] = {
    "opsti": {"naziv": "Opšti rok zastarelosti", "osnov": "ZOO čl. 371", "godine": 10, "racunanje": _ZPP,
              "opis": "Potraživanja za koja zakon ne određuje drugi rok — teče od dana dospelosti (ZOO čl. 361)"},
    "privreda": {"naziv": "Međusobna potraživanja pravnih lica iz ugovora o prometu robe i usluga", "osnov": "ZOO čl. 374 st. 1",
                 "godine": 3, "racunanje": _ZPP, "opis": "Između PRAVNIH LICA, iz ugovora o prometu robe i usluga",
                 "napomena": "Zastarevanje teče odvojeno za svaku isporuku robe, izvršeni rad ili uslugu (čl. 374 st. 2)."},
    "periodicna": {"naziv": "Povremena potraživanja (kamata, izdržavanje, anuiteti)", "osnov": "ZOO čl. 372 st. 1", "godine": 3,
                   "racunanje": _ZPP, "opis": "Od dospelosti SVAKOG pojedinog davanja",
                   "napomena": "Ne važi za otplate u obrocima (čl. 372 st. 2). Samo pravo zastareva za 5 godina (čl. 373); pravo na zakonsko izdržavanje ne zastareva (čl. 373 st. 3)."},
    "zakupnina": {"naziv": "Potraživanje zakupnine", "osnov": "ZOO čl. 375", "godine": 3, "racunanje": _ZPP,
                  "opis": "Zakupnina, bilo da se plaća povremeno ili u ukupnom iznosu"},
    "radni_spor": {"naziv": "Novčana potraživanja iz radnog odnosa", "osnov": "ZR čl. 196", "godine": 3, "racunanje": _ZPP,
                   "opis": "Od dana nastanka obaveze"},
    "naknada_stete": {"naziv": "Naknada štete — subjektivni rok", "osnov": "ZOO čl. 376 st. 1", "godine": 3, "racunanje": _ZPP,
                      "opis": "Od kad je oštećeni doznao za štetu i za lice koje ju je učinilo",
                      "napomena": "Proverite i objektivni rok: u svakom slučaju 5 godina od nastanka štete (čl. 376 st. 2). Za štetu od krivičnog dela rok može biti duži (čl. 377) — ne računa se ovde. Šteta od povrede ugovora: rok te obaveze (st. 3)."},
    "naknada_stete_obj": {"naziv": "Naknada štete — objektivni rok", "osnov": "ZOO čl. 376 st. 2", "godine": 5, "racunanje": _ZPP,
                          "opis": "Od kad je šteta nastala, bez obzira na saznanje"},
    "komunalne": {"naziv": "Struja, toplotna energija, gas, voda, telefon — za potrebe domaćinstva", "osnov": "ZOO čl. 378 st. 1 tač. 1 i 3",
                  "godine": 1, "racunanje": _ZPP, "opis": "Struja, toplotna energija, gas, voda — za potrebe DOMAĆINSTVA; telefon i pošta (tač. 3)",
                  "napomena": "Uslov „za potrebe domaćinstva“ važi za struju, toplotnu energiju, gas, vodu, dimničarske usluge i održavanje čistoće (tač. 1); za telefon i poštu (tač. 3) tog uslova nema. Zastarevanje teče iako su isporuke produžene (čl. 378 st. 2)."},
    "presudjeno": {"naziv": "Potraživanje utvrđeno pravnosnažnom odlukom ili poravnanjem", "osnov": "ZOO čl. 379 st. 1", "godine": 10,
                   "racunanje": _ZPP, "opis": "I kad zakon inače predviđa kraći rok",
                   "napomena": "Povremena potraživanja iz takve odluke koja dospevaju ubuduće zastarevaju u roku za povremena potraživanja (čl. 379 st. 2)."},
    "zalba_parnicna": {"naziv": "Žalba na prvostepenu presudu (parnični postupak)", "osnov": "ZPP čl. 367", "dani": 15, "vrsta": "procesni",
                       "racunanje": _ZPP, "opis": "Od dana dostavljanja prepisa presude",
                       "napomena": "U meničnim i čekovnim sporovima rok je 8 dana (čl. 367). Posebne odredbe (npr. sporovi male vrednosti) mogu propisati drugačiji rok."},
    "revizija": {"naziv": "Revizija (parnični postupak)", "osnov": "ZPP čl. 403", "dani": 30, "vrsta": "procesni", "racunanje": _ZPP,
                 "opis": "Od dana dostavljanja drugostepene pravnosnažne presude",
                 "napomena": "Revizija nije dozvoljena u svakom sporu — proverite dozvoljenost pre računanja roka."},
    "prigovor_platni_nalog": {"naziv": "Prigovor na platni nalog", "osnov": "ZPP čl. 457 st. 2", "dani": 8, "vrsta": "procesni",
                              "racunanje": _ZPP, "opis": "Od dana dostavljanja platnog naloga",
                              "napomena": "U meničnim i čekovnim sporovima rok je 3 dana (čl. 457 st. 2)."},
    "predlog_povracaj": {"naziv": "Predlog za vraćanje u pređašnje stanje", "osnov": "ZPP čl. 110", "dani": 8, "vrsta": "procesni",
                         "racunanje": _ZPP, "opis": "Od dana kad je prestao razlog propuštanja (ili kad je stranka saznala za propuštanje)",
                         "napomena": "Posle 60 dana od dana propuštanja vraćanje se ne može tražiti (čl. 110); u privrednim sporovima taj rok je 30 dana (čl. 486)."},
    "otkaz_pobijanje": {"naziv": "Spor protiv rešenja kojim je povređeno pravo zaposlenog (npr. otkaz)", "osnov": "ZR čl. 195", "dani": 60,
                        "vrsta": "procesni", "racunanje": _ZPP, "opis": "Od dana dostavljanja rešenja, odnosno saznanja za povredu prava"},
    "zalba_izvrsenje": {"naziv": "Žalba ili prigovor u izvršnom postupku", "osnov": "ZIO čl. 25 st. 1", "dani": 8, "vrsta": "procesni",
                        "racunanje": _ZIO, "opis": "Od dana dostavljanja rešenja",
                        "napomena": "Zakon za pojedina rešenja može odrediti duži ili kraći rok (čl. 25 st. 1)."},
    "zalbeni_upravni": {"naziv": "Žalba u upravnom postupku", "osnov": "ZUP čl. 153 st. 1", "dani": 15, "vrsta": "procesni",
                        "racunanje": _ZUP, "opis": "Od obaveštavanja stranke o rešenju", "napomena": "Ako zakonom nije drukčije propisano."},
    "tuzba_upravni_spor": {"naziv": "Tužba u upravnom sporu", "osnov": "ZUS čl. 18 st. 1", "dani": 30, "vrsta": "procesni",
                           "racunanje": _ZUS, "opis": "Od dana dostavljanja upravnog akta stranci",
                           "napomena": "Zakon može propisati kraći rok (čl. 18 st. 1); poseban rok važi kad akt nije dostavljen (čl. 18 st. 3)."},
    "zalbeni_krivicni": {"naziv": "Žalba na prvostepenu presudu (krivični postupak)", "osnov": "ZKP čl. 432", "dani": 15, "vrsta": "procesni",
                         "racunanje": _ZKP, "opis": "Od dana dostavljanja prepisa presude",
                         "napomena": "Posebne odredbe (npr. skraćeni postupak) mogu propisati kraći rok — proverite."},
    "naknada_stete_neosnovano_lisen": {"naziv": "Naknada štete — neosnovana osuda ili neosnovano lišenje slobode", "osnov": "ZKP čl. 591",
                                       "godine": 3, "racunanje": _ZPP,
                                       "opis": "Od pravnosnažnosti prvostepene odbijajuće ili oslobađajuće presude, odnosno rešenja o obustavi",
                                       "napomena": "Ako je o žalbi odlučivao apelacioni sud — od dana prijema njegove odluke (čl. 591). Prethodno se podnosi zahtev ministarstvu (čl. 588); dok taj postupak traje zastarelost ne teče (čl. 589 st. 3) — to se ovde ne računa."},
}


def kalkulisi_zastarelost(tip: str, datum_pocetka: date) -> ZastarelostRezultat:
    """Datum isteka za dati tip od datuma događaja (dostavljanje, dospelost, saznanje…).

    Dani: prvi dan roka je dan POSLE događaja, pa je poslednji dan = događaj + N (ZPP čl. 103 st. 2, ZUP čl. 80
    st. 2, ZKP čl. 224, ZOO čl. 77 st. 1). Meseci/godine: dan istog broja; ako ga nema — poslednji dan meseca
    (relativedelta). Poslednji dan na neradni dan → prvi naredni radni dan (`racunanje`; shared/neradni_dani.py).
    Prekid i zastoj zastarelosti se NE računaju.
    """
    from shared.neradni_dani import IZVOR_PRAZNIKA, prvi_radni_od, razlog
    if tip not in ROKOVI_ZASTARELOSTI:
        raise ValueError(f"Nepoznat tip zastarelosti: {tip!r}")

    r = ROKOVI_ZASTARELOSTI[tip]
    try:
        from routers.email_notif import _danas_beograd
        danas = _danas_beograd()
    except Exception:
        danas = date.today()

    if r.get("dani"):
        kalendarski = datum_pocetka + timedelta(days=r["dani"])
        rok_opis = f"{r['dani']} dana"
        rok_godina = 0
    elif r.get("meseci"):
        kalendarski = datum_pocetka + relativedelta(months=r["meseci"])
        rok_opis = f"{r['meseci']} meseci"
        rok_godina = 0
    else:
        g = r["godine"]
        kalendarski = datum_pocetka + relativedelta(years=g)
        rok_opis = f"{g} {'godina' if g >= 5 or g == 1 else 'godine'}" if g != 1 else "1 godina"
        rok_godina = g

    datum_isteka = prvi_radni_od(kalendarski)
    dana_preostalo = (datum_isteka - danas).days

    return ZastarelostRezultat(
        tip_potrazivanja=r["naziv"],
        zakonski_osnov=r["osnov"],
        rok_godina=rok_godina,
        rok_opis=rok_opis,
        datum_pocetka=datum_pocetka,
        datum_zastarelosti=datum_isteka,
        dana_preostalo=dana_preostalo,
        isteklo=dana_preostalo < 0,
        napomena=r.get("napomena", ""),
        vrsta=r.get("vrsta", "zastarelost"),
        kalendarski_poslednji_dan=kalendarski,
        pomereno_razlog=razlog(kalendarski) if datum_isteka != kalendarski else "",
        pravilo_racunanja=r.get("racunanje", ""),
        izvor_neradnih_dana=IZVOR_PRAZNIKA,
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
