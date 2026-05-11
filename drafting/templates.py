# -*- coding: utf-8 -*-
"""
Drafting template registry for /api/nacrt.
Each entry: label, opis_hint, ekstrakcioni_prompt, sablon.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# ŠABLONI
# ─────────────────────────────────────────────────────────────────────────────

SABLON_UGOVOR_NEODREDJENO = """\
UGOVOR O RADU
(na neodređeno vreme)

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}, sa sedištem u {POSLODAVAC_ADRESA}{POSLODAVAC_PIB_CLAN}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}, JMBG: {ZAPOSLENI_JMBG}, {ZAPOSLENI_ADRESA}
(u daljem tekstu: Zaposleni)


Član 1 — Predmet ugovora
Ovim ugovorom, u skladu sa Zakonom o radu (Sl. glasnik RS, br. 24/2005, 61/2005, 54/2009,\
 32/2013, 75/2014, 13/2017, 113/2017, 95/2018), zasniva se radni odnos na neodređeno\
 vreme, počev od {DATUM_POCETKA}.

Član 2 — Probni rad
{PROBNI_RAD_CLAN}

Član 3 — Radno mesto i opis posla
Zaposleni se zapošljava na radnom mestu: {RADNO_MESTO}.
Opis posla: {OPIS_POSLA}

Član 4 — Mesto rada
Osnovno mesto rada Zaposlenog je: {MESTO_RADA}.

Član 5 — Radno vreme
Puno radno vreme iznosi {RADNO_VREME} sati nedeljno.
{PREKOVREMENI_CLAN}

Član 6 — Osnovna zarada
Osnovna mesečna zarada Zaposlenog iznosi {OSNOVNA_ZARADA} dinara (bruto iznos).
Zarada se isplaćuje najkasnije do {ROK_ISPLATE}. u mesecu za prethodni mesec,\
 na tekući račun Zaposlenog.
{BONUS_CLAN}

Član 7 — Godišnji odmor
{GODISNJI_ODMOR_CLAN}

Član 8 — Tajnost poslovnih informacija
{TAJNOST_CLAN}

Član 9 — Konkurentska klauzula
{KONKURENTSKA_CLAN}

Član 10 — Otkaz ugovora
Otkazni rok kod otkaza od strane Zaposlenog iznosi {OTKAZNI_ROK_ZAPOSLENI}.
Otkazni rok kod otkaza od strane Poslodavca iznosi {OTKAZNI_ROK_POSLODAVAC}.

Član 11 — Završne odredbe
Za sve što nije regulisano ovim ugovorom primenjuju se odredbe Zakona o radu i\
 drugih važećih propisa Republike Srbije.
Ugovor je sastavljen u 2 istovetna primerka, od kojih svaka strana zadržava po jedan.

                                Poslodavac:                    Zaposleni:
                            ____________________           ____________________
                            {POSLODAVAC_IME}               {ZAPOSLENI_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre potpisivanja.\
"""

SABLON_UGOVOR_ODREDJENO = """\
UGOVOR O RADU
(na određeno vreme)

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}, sa sedištem u {POSLODAVAC_ADRESA}{POSLODAVAC_PIB_CLAN}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}, JMBG: {ZAPOSLENI_JMBG}, {ZAPOSLENI_ADRESA}
(u daljem tekstu: Zaposleni)


Član 1 — Predmet ugovora
Ovim ugovorom, u skladu sa Zakonom o radu (Sl. glasnik RS, br. 24/2005 i izmene),\
 naročito čl. 37, zasniva se radni odnos na određeno vreme u trajanju od {TRAJANJE_ODREDJENO},\
 počev od {DATUM_POCETKA}.
Razlog zasnivanja radnog odnosa na određeno vreme: {RAZLOG_ODREDJENOG}

Član 2 — Probni rad
{PROBNI_RAD_CLAN}

Član 3 — Radno mesto i opis posla
Zaposleni se zapošljava na radnom mestu: {RADNO_MESTO}.
Opis posla: {OPIS_POSLA}

Član 4 — Mesto rada
Osnovno mesto rada Zaposlenog je: {MESTO_RADA}.

Član 5 — Radno vreme
Puno radno vreme iznosi {RADNO_VREME} sati nedeljno.
{PREKOVREMENI_CLAN}

Član 6 — Osnovna zarada
Osnovna mesečna zarada Zaposlenog iznosi {OSNOVNA_ZARADA} dinara (bruto iznos).
Zarada se isplaćuje najkasnije do {ROK_ISPLATE}. u mesecu za prethodni mesec.
{BONUS_CLAN}

Član 7 — Godišnji odmor
{GODISNJI_ODMOR_CLAN}

Član 8 — Tajnost poslovnih informacija
{TAJNOST_CLAN}

Član 9 — Konkurentska klauzula
{KONKURENTSKA_CLAN}

Član 10 — Otkaz i istек ugovora
Ovaj ugovor prestaje istekom ugovorenog roka, osim ako se ne sporazumno produži\
 ili ne pretvori u ugovor na neodređeno vreme.
Otkazni rok kod prevremenog otkaza od strane Zaposlenog iznosi {OTKAZNI_ROK_ZAPOSLENI}.
Otkazni rok kod prevremenog otkaza od strane Poslodavca iznosi {OTKAZNI_ROK_POSLODAVAC}.

Član 11 — Završne odredbe
Za sve što nije regulisano ovim ugovorom primenjuju se odredbe Zakona o radu.
Ugovor je sastavljen u 2 istovetna primerka.

                                Poslodavac:                    Zaposleni:
                            ____________________           ____________________
                            {POSLODAVAC_IME}               {ZAPOSLENI_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre potpisivanja.\
"""

SABLON_ANEKS = """\
ANEKS UGOVORA O RADU
broj {ANEKS_BROJ}

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}
(u daljem tekstu: Zaposleni)


Ugovorne strane su dana {DATUM} zaključile sledeći aneks na Ugovor o radu\
 {REFERENCA_UGOVORA}.

Član 1 — Izmene i dopune
{IZMENE_OPIS}

Član 2 — Početak primene
Izmene iz člana 1 ovog aneksa primenjuju se od {DATUM_PRIMENE}.

Član 3 — Ostale odredbe
Sve ostale odredbe Ugovora o radu {REFERENCA_UGOVORA} ostaju na snazi i\
 neizmenjene.

                                Poslodavac:                    Zaposleni:
                            ____________________           ____________________
                            {POSLODAVAC_IME}               {ZAPOSLENI_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre potpisivanja.\
"""

SABLON_SPORAZUMNI_RASKID = """\
SPORAZUM O PRESTANKU RADNOG ODNOSA
(Sporazumni raskid ugovora o radu)

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}
(u daljem tekstu: Zaposleni)


Član 1 — Prestanak radnog odnosa
Ugovorne strane se sporazumevaju da radni odnos Zaposlenog kod Poslodavca prestaje\
 dana {DATUM_PRESTANKA}, u skladu sa čl. 177 Zakona o radu.

Član 2 — Prava pri prestanku
{OTPREMNINA_CLAN}
Do dana prestanka radnog odnosa, Zaposleni će iskoristiti neiskorišćeni godišnji\
 odmor ili primiti novčanu naknadu u skladu sa zakonom.

Član 3 — Povraćaj imovine
Zaposleni se obavezuje da do dana {DATUM_PRESTANKA} vrati Poslodavcu sva sredstva\
 rada, dokumente i drugu imovinu poslodavca koja mu je bila poverena.

Član 4 — Obaveze Poslodavca
Poslodavac se obavezuje da Zaposlenom izda potrebne dokumente (radnu knjižicu,\
 potvrdu o radnom stažu i sl.) i izmiri sve dospele obaveze prema Zaposlenom do\
 dana prestanka radnog odnosa.

Član 5 — Završne odredbe
{NAPOMENA_CLAN}
Ovaj sporazum je sastavljen u 2 istovetna primerka i stupa na snagu danom potpisivanja.

                                Poslodavac:                    Zaposleni:
                            ____________________           ____________________
                            {POSLODAVAC_IME}               {ZAPOSLENI_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre potpisivanja.\
"""

SABLON_PUNOMOCJE = """\
PUNOMOĆJE

Ja, {VLASTODAVAC_IME}, JMBG: {VLASTODAVAC_JMBG}, {VLASTODAVAC_ADRESA}
(u daljem tekstu: Vlastodavac)

OVLAŠĆUJEM

{PUNOMOCNIK_IME}, {PUNOMOCNIK_ADRESA}
(u daljem tekstu: Punomoćnik)

da u moje ime i za moj račun {PREDMET_PUNOMOCJA}.

Ovo punomoćje važi {ROK_VAZENJA}.
{SUPSTITUCIJA_CLAN}

                                        Vlastodavac:
                                    ____________________
                                    {VLASTODAVAC_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre upotrebe.\
"""


# ─────────────────────────────────────────────────────────────────────────────
# Ekstrakcioni promptovi po tipu
# ─────────────────────────────────────────────────────────────────────────────

_EKSTRAKCIONI_BAZA = """\
Ti si pravni asistent koji ekstraktuje podatke iz slobodnog opisa.
Vrati ČIST JSON — bez komentara, bez markdown blokova, bez ikakvog teksta van JSON-a.
Ako polje nije pomenuto, ostavi prazan string "".
ZABRANJENO: izmišljati ili pretpostavljati podatke koji nisu u tekstu.
"""

EKSTRAKCIONI_PROMPTOVI: dict[str, str] = {

"ugovor_neodredjeno": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "poslodavac_adresa": "Sedište/adresa poslodavca",
  "poslodavac_pib": "PIB poslodavca ako je naveden, inače prazno",
  "zaposleni_ime": "Puno ime zaposlenog",
  "zaposleni_jmbg": "JMBG zaposlenog ako je naveden, inače [JMBG — POPUNITI]",
  "zaposleni_adresa": "Adresa zaposlenog",
  "radno_mesto": "Naziv radnog mesta",
  "opis_posla": "Kratak opis posla",
  "mesto_rada": "Mesto/grad rada",
  "osnovna_zarada": "Iznos osnovne zarade u RSD (samo broj, bez 'dinara')",
  "rok_isplate": "Dan u mesecu za isplatu zarade (npr. 10)",
  "datum_pocetka": "Datum početka rada u formatu DD.MM.YYYY",
  "radno_vreme": "Broj radnih sati nedeljno (npr. 40)",
  "otkazni_rok_zaposleni": "Otkazni rok zaposlenog (npr. '8 radnih dana')",
  "otkazni_rok_poslodavac": "Otkazni rok poslodavca (npr. '8 radnih dana')",
  "probni_rad": "Trajanje probnog rada (npr. '3 meseca') ili prazno ako nema",
  "godisnji_odmor_dani": "Broj dana godišnjeg odmora (npr. 20) ili prazno",
  "ima_tajnost": "true ako postoji klauzula o tajnosti, inače false",
  "tajnost_rok": "Trajanje obaveze tajnosti nakon prestanka (npr. '2 godine') ili prazno",
  "ima_konkurentsku": "true ako postoji konkurentska klauzula, inače false",
  "konkurentska_trajanje": "Trajanje zabrane (npr. '1 godina') ili prazno",
  "konkurentska_naknada_procenat": "Procenat zarade kao naknada (npr. 30) ili prazno",
  "bonus_procenat": "Maks. bonus kao % zarade (npr. 30) ili prazno",
  "datum": "Datum zaključenja u formatu DD.MM.YYYY ili danas",
  "mesto": "Mesto zaključenja"
}
""",

"ugovor_odredjeno": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "poslodavac_adresa": "Sedište/adresa poslodavca",
  "poslodavac_pib": "PIB poslodavca ako je naveden, inače prazno",
  "zaposleni_ime": "Puno ime zaposlenog",
  "zaposleni_jmbg": "JMBG zaposlenog ako je naveden, inače [JMBG — POPUNITI]",
  "zaposleni_adresa": "Adresa zaposlenog",
  "radno_mesto": "Naziv radnog mesta",
  "opis_posla": "Kratak opis posla",
  "mesto_rada": "Mesto/grad rada",
  "osnovna_zarada": "Iznos osnovne zarade u RSD",
  "rok_isplate": "Dan u mesecu za isplatu zarade",
  "datum_pocetka": "Datum početka rada u formatu DD.MM.YYYY",
  "trajanje_odredjeno": "Trajanje ugovora (npr. '12 meseci', '1 godina')",
  "razlog_odredjenog": "Razlog za određeno vreme — npr. zamena odsutnog radnika, sezonski posao, privremeni porast obima posla (ZR čl. 37)",
  "radno_vreme": "Broj radnih sati nedeljno",
  "otkazni_rok_zaposleni": "Otkazni rok zaposlenog",
  "otkazni_rok_poslodavac": "Otkazni rok poslodavca",
  "probni_rad": "Trajanje probnog rada ili prazno",
  "godisnji_odmor_dani": "Broj dana godišnjeg odmora ili prazno",
  "ima_tajnost": "true ako postoji klauzula o tajnosti, inače false",
  "tajnost_rok": "Trajanje tajnosti nakon prestanka ili prazno",
  "ima_konkurentsku": "true ako postoji konkurentska klauzula, inače false",
  "konkurentska_trajanje": "Trajanje zabrane ili prazno",
  "konkurentska_naknada_procenat": "Procenat zarade kao naknada ili prazno",
  "bonus_procenat": "Maks. bonus kao % zarade ili prazno",
  "datum": "Datum zaključenja u formatu DD.MM.YYYY ili danas",
  "mesto": "Mesto zaključenja"
}
""",

"aneks": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "zaposleni_ime": "Puno ime zaposlenog",
  "aneks_broj": "Broj aneksa (npr. I, II, 1/2026) ili [BROJ — POPUNITI]",
  "referenca_ugovora": "Referenca na osnovni ugovor (npr. 'br. 15/2024 od 01.03.2024.')",
  "izmene_opis": "Opis izmena — šta se menja, novi uslovi",
  "datum_primene": "Datum od kojeg stupaju izmene na snagu",
  "datum": "Datum zaključenja aneksa",
  "mesto": "Mesto zaključenja"
}
""",

"sporazumni_raskid": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "zaposleni_ime": "Puno ime zaposlenog",
  "datum_prestanka": "Datum prestanka radnog odnosa u formatu DD.MM.YYYY",
  "ima_otpremninu": "true ako je otpremnina navedena, inače false",
  "otpremnina_iznos": "Iznos otpremnine u RSD ili prazno",
  "napomena": "Eventualna posebna napomena ili prazno",
  "datum": "Datum zaključenja sporazuma",
  "mesto": "Mesto zaključenja"
}
""",

"punomocje": _EKSTRAKCIONI_BAZA + """
{
  "vlastodavac_ime": "Puno ime vlastodavca",
  "vlastodavac_jmbg": "JMBG vlastodavca ili [JMBG — POPUNITI]",
  "vlastodavac_adresa": "Adresa vlastodavca",
  "punomocnik_ime": "Puno ime punomoćnika",
  "punomocnik_adresa": "Adresa punomoćnika",
  "predmet_punomocja": "Šta punomoćnik sme da radi u ime vlastodavca",
  "rok_vazenja": "Rok važenja punomoćja (npr. 'do opoziva', '6 meseci', 'do 31.12.2026.')",
  "ima_supstituciju": "true ako punomoćnik sme dalje ovlašćivati, inače false",
  "datum": "Datum izdavanja punomoćja",
  "mesto": "Mesto izdavanja"
}
""",
}


# ─────────────────────────────────────────────────────────────────────────────
# Registar tipova
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: dict[str, dict] = {
    "ugovor_neodredjeno": {
        "label":      "Ugovor o radu na neodređeno vreme",
        "opis_hint":  (
            "Npr. Poslodavac: 'TechCorp' d.o.o., Beograd. Zaposleni: Ana Nikolić, "
            "radno mesto: junior developer, zarada 120.000 RSD bruto, probni rad 3 meseca, "
            "početak rada 01.06.2026."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["ugovor_neodredjeno"],
        "sablon":     SABLON_UGOVOR_NEODREDJENO,
        "compliance_tip": "ugovor_o_radu",
    },
    "ugovor_odredjeno": {
        "label":      "Ugovor o radu na određeno vreme",
        "opis_hint":  (
            "Npr. Poslodavac: 'MediaGroup' d.o.o., Novi Sad. Zaposleni: Marko Đorđević, "
            "radno mesto: grafički dizajner, trajanje 12 meseci, razlog: privremeni porast obima posla, "
            "zarada 90.000 RSD bruto."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["ugovor_odredjeno"],
        "sablon":     SABLON_UGOVOR_ODREDJENO,
        "compliance_tip": "ugovor_o_radu",
    },
    "aneks": {
        "label":      "Aneks ugovora o radu",
        "opis_hint":  (
            "Npr. Aneks I na Ugovor br. 5/2024. Zarada se menja sa 100.000 na 120.000 RSD bruto "
            "od 01.06.2026. Ostale odredbe ostaju nepromenjene."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["aneks"],
        "sablon":     SABLON_ANEKS,
        "compliance_tip": None,
    },
    "sporazumni_raskid": {
        "label":      "Sporazumni raskid radnog odnosa",
        "opis_hint":  (
            "Npr. Poslodavac 'LogiTech' d.o.o. i zaposleni Petar Petrović sporazumno raskidaju "
            "radni odnos. Datum prestanka: 31.05.2026. Otpremnina: 150.000 RSD."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["sporazumni_raskid"],
        "sablon":     SABLON_SPORAZUMNI_RASKID,
        "compliance_tip": None,
    },
    "punomocje": {
        "label":      "Punomoćje",
        "opis_hint":  (
            "Npr. Vlastodavac: Jovana Marković, Beograd, ovlašćuje advokata Milana Petrovića "
            "da je zastupa pred svim sudovima i organima u Srbiji, do opoziva."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["punomocje"],
        "sablon":     SABLON_PUNOMOCJE,
        "compliance_tip": None,
    },
}


def get_types_list() -> list[dict]:
    """Vraća listu tipova za GET /api/nacrt/types."""
    return [
        {"vrsta": k, "label": v["label"], "opis_hint": v["opis_hint"]}
        for k, v in TEMPLATES.items()
    ]
