# -*- coding: utf-8 -*-
"""
Drafting template registry for /api/nacrt.
Each entry: label, opis_hint, ekstrakcioni_prompt, sablon.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# ZR REFERENCE CONSTANTS  (Bug 6 + 7)
# ─────────────────────────────────────────────────────────────────────────────

ZR_AMENDMENTS = (
    "24/2005, 61/2005, 54/2009, 32/2013, 75/2014, 13/2017 - odluka US, "
    "113/2017, 95/2018 - autentično tumačenje, 86/2019, 157/2020"
)
ZR_FULL_REFERENCE = f"Zakon o radu (Sl. glasnik RS, br. {ZR_AMENDMENTS})"
ZR_SHORT_REFERENCE = "Zakonom o radu"

# ─────────────────────────────────────────────────────────────────────────────
# ŠABLONI
# Use __ZR_FULL__ / __ZR_SHORT__ sentinels replaced at module load time,
# so {PLACEHOLDER} braces for template fields are not affected.
# ─────────────────────────────────────────────────────────────────────────────

_SABLON_UGOVOR_NEODREDJENO_RAW = """\
UGOVOR O RADU
(na neodređeno vreme)

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}, sa sedištem u {POSLODAVAC_ADRESA}{POSLODAVAC_PIB_CLAN}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}, JMBG: {ZAPOSLENI_JMBG}, {ZAPOSLENI_ADRESA}
(u daljem tekstu: Zaposleni)


Član 1 — Predmet ugovora
Ovim ugovorom, u skladu sa __ZR_FULL__, zasniva se radni odnos na neodređeno\
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
Za sve što nije regulisano ovim ugovorom primenjuju se odredbe __ZR_SHORT__ i\
 drugih važećih propisa Republike Srbije.
Ugovor je sastavljen u 2 istovetna primerka, od kojih svaka strana zadržava po jedan.

                                Poslodavac:                    Zaposleni:
                            ____________________           ____________________
                            {POSLODAVAC_IME}               {ZAPOSLENI_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre potpisivanja.\
"""

_SABLON_UGOVOR_ODREDJENO_RAW = """\
UGOVOR O RADU
(na određeno vreme)

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}, sa sedištem u {POSLODAVAC_ADRESA}{POSLODAVAC_PIB_CLAN}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}, JMBG: {ZAPOSLENI_JMBG}, {ZAPOSLENI_ADRESA}
(u daljem tekstu: Zaposleni)


Član 1 — Predmet ugovora
Ovim ugovorom, u skladu sa __ZR_FULL__, naročito čl. 37, zasniva se radni odnos\
 na određeno vreme u trajanju od {TRAJANJE_ODREDJENO}, počev od {DATUM_POCETKA}.
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

Član 10 — Otkaz i istek ugovora
Ovaj ugovor prestaje istekom ugovorenog roka, osim ako se ne sporazumno produži\
 ili ne pretvori u ugovor na neodređeno vreme.
Otkazni rok kod prevremenog otkaza od strane Zaposlenog iznosi {OTKAZNI_ROK_ZAPOSLENI}.
Otkazni rok kod prevremenog otkaza od strane Poslodavca iznosi {OTKAZNI_ROK_POSLODAVAC}.

Član 11 — Završne odredbe
Za sve što nije regulisano ovim ugovorom primenjuju se odredbe __ZR_SHORT__.
Ugovor je sastavljen u 2 istovetna primerka.

                                Poslodavac:                    Zaposleni:
                            ____________________           ____________________
                            {POSLODAVAC_IME}               {ZAPOSLENI_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre potpisivanja.\
"""

_SABLON_ANEKS_RAW = """\
ANEKS UGOVORA O RADU
broj {ANEKS_BROJ}

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}
(u daljem tekstu: Zaposleni)


Ugovorne strane su zaključile sledeći aneks na Ugovor o radu\
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

_SABLON_SPORAZUMNI_RASKID_RAW = """\
SPORAZUM O PRESTANKU RADNOG ODNOSA
(Sporazumni raskid ugovora o radu)

Zaključen {DATUM} u {MESTO}, između:

POSLODAVCA: {POSLODAVAC_IME}
(u daljem tekstu: Poslodavac)

i

ZAPOSLENOG/E: {ZAPOSLENI_IME}
(u daljem tekstu: Zaposleni)


Član 1 — Prestanak radnog odnosa
Ugovorne strane se sporazumevaju da radni odnos Zaposlenog kod\
 Poslodavca{ORIGINAL_UGOVOR_CLAN} prestaje dana {DATUM_PRESTANKA},\
 u skladu sa čl. 177 __ZR_SHORT__.

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

# Bug 8: "preduzme sledeće radnje:" makes any noun/verb predmet grammatically correct
_SABLON_PUNOMOCJE_RAW = """\
PUNOMOĆJE

Ja, {VLASTODAVAC_IME}, JMBG: {VLASTODAVAC_JMBG}, {VLASTODAVAC_ADRESA}
(u daljem tekstu: Vlastodavac)

OVLAŠĆUJEM

{PUNOMOCNIK_IME}, {PUNOMOCNIK_ADRESA}
(u daljem tekstu: Punomoćnik)

da u moje ime i za moj račun preduzme sledeće radnje: {PREDMET_PUNOMOCJA}

Ovo punomoćje važi {ROK_VAZENJA}.
{SUPSTITUCIJA_CLAN}

                                        Vlastodavac:
                                    ____________________
                                    {VLASTODAVAC_IME}

{DATUM}, {MESTO}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre upotrebe.\
"""

# Resolve ZR sentinel markers
SABLON_UGOVOR_NEODREDJENO = (
    _SABLON_UGOVOR_NEODREDJENO_RAW
    .replace("__ZR_FULL__", ZR_FULL_REFERENCE)
    .replace("__ZR_SHORT__", ZR_SHORT_REFERENCE)
)
SABLON_UGOVOR_ODREDJENO = (
    _SABLON_UGOVOR_ODREDJENO_RAW
    .replace("__ZR_FULL__", ZR_FULL_REFERENCE)
    .replace("__ZR_SHORT__", ZR_SHORT_REFERENCE)
)
SABLON_ANEKS = (
    _SABLON_ANEKS_RAW
    .replace("__ZR_FULL__", ZR_FULL_REFERENCE)
    .replace("__ZR_SHORT__", ZR_SHORT_REFERENCE)
)
SABLON_SPORAZUMNI_RASKID = (
    _SABLON_SPORAZUMNI_RASKID_RAW
    .replace("__ZR_FULL__", ZR_FULL_REFERENCE)
    .replace("__ZR_SHORT__", ZR_SHORT_REFERENCE)
)
SABLON_PUNOMOCJE = (
    _SABLON_PUNOMOCJE_RAW
    .replace("__ZR_FULL__", ZR_FULL_REFERENCE)
    .replace("__ZR_SHORT__", ZR_SHORT_REFERENCE)
)

_SABLON_ZALBA_NA_PRESUDU_RAW = """\
ŽALBA NA PRESUDU

{PODNOSILAC_IME}{ADVOKAT_CLAN}

Sudu:
{SUD_NAZIV}

Putem prvostepenog suda

Predmet: {BROJ_PREDMETA}

Žalba na presudu od {DATUM_PRESUDE}

Uvaženi sude,

U zakonskom roku, u skladu sa Zakonom o parničnom postupku (ZPP, Sl. glasnik RS, br. 72/2011,\
 49/2013, 74/2013, 55/2014, 87/2018, 18/2020), a naročito čl. 373, izjavljujem ŽALBU\
 na prvostepenu presudu {BROJ_PREDMETA} od {DATUM_PRESUDE}.

I. RAZLOZI ŽALBE

{RAZLOZI_ZALBE}

II. PREDLOG

Na osnovu navedenih razloga predlažem drugostepenom sudu da:

{PREDLOG}

{DATUM}, {MESTO}

                                                   Podnosilac žalbe:
                                                ____________________
                                                {PODNOSILAC_IME}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre podnošenja.\
"""

_SABLON_ZALBA_NA_RESENJE_RAW = """\
ŽALBA NA REŠENJE

Podnosilac: {PODNOSILAC_IME}

Organu:
{ORGAN_NAZIV}

Predmet: Žalba na rešenje br. {BROJ_RESENJA} od {DATUM_RESENJA}

Poštovani,

U zakonskom roku od 15 dana, u skladu sa Zakonom o opštem upravnom postupku\
 (ZUP, Sl. glasnik RS, br. 18/2016, 95/2018, 2/2023 - autentično tumačenje),\
 čl. 158, izjavljujem ŽALBU na rešenje br. {BROJ_RESENJA} od {DATUM_RESENJA}.

I. RAZLOZI ŽALBE

{RAZLOZI_ZALBE}

II. PREDLOG

Na osnovu iznetih razloga, predlažem drugostepenom organu da:

{PREDLOG}

{DATUM}, {MESTO}

                                                   Podnosilac žalbe:
                                                ____________________
                                                {PODNOSILAC_IME}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre podnošenja.\
"""

_SABLON_TUZBA_NAKNADA_STETE_RAW = """\
TUŽBA ZA NAKNADU ŠTETE

TUŽILAC: {TUZILAC_IME}
TUŽENI: {TUZENI_IME}

{SUD_NAZIV}

TUŽBA

I. PREDMET SPORA

{OPIS_STETE}

II. PRAVNI OSNOV

Na osnovu Zakona o obligacionim odnosima (ZOO, Sl. glasnik SFRJ br. 29/78 i dr.),\
 čl. 154 (osnov odgovornosti), čl. 155 (pojam štete) i čl. {PRAVNI_OSNOV_CLAN}\
 (naknada nematerijalne/materijalne štete), tužilac ima pravo na naknadu štete od tuženog.

III. TUŽBENI ZAHTEV

Tužilac tražim da sud:

1. Obaveže tuženog {TUZENI_IME} da tužiocu {TUZILAC_IME} plati naknadu štete\
 u iznosu od {IZNOS_STETE} RSD, sa zakonskom zateznom kamatom od dana donošenja\
 presude do isplate;
2. Obaveže tuženog da snosi troškove postupka.

IV. DOKAZI

{DOKAZI}

{DATUM}, {MESTO}

                                                   Tužilac:
                                                ____________________
                                                {TUZILAC_IME}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre podnošenja.\
"""

_SABLON_TUZBA_RADNI_SPOR_RAW = """\
TUŽBA — RADNI SPOR

TUŽILAC (zaposleni): {TUZILAC_IME}
TUŽENI (poslodavac): {POSLODAVAC_IME}

{SUD_NAZIV}

TUŽBA ZA ZAŠTITU PRAVA IZ RADNOG ODNOSA

I. ČINJENIČNO STANJE

{OPIS_POVREDE}

Povreda prava nastupila je dana {DATUM_POVREDE}.

II. PRAVNI OSNOV

Na osnovu __ZR_FULL__, a naročito čl. 195 (sudska zaštita prava zaposlenog),\
 tužilac je ovlašćen da pokrene radni spor pred nadležnim sudom radi zaštite\
 povređenih prava iz radnog odnosa.

III. TUŽBENI ZAHTEV

{ZAHTEV}

IV. PREDLOG

Na osnovu navedenog, predlažem sudu da:
1. Usvoji tužbeni zahtev u celosti;
2. Obaveže tuženog da snosi troškove postupka.

{DATUM}, {MESTO}

                                                   Tužilac:
                                                ____________________
                                                {TUZILAC_IME}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre podnošenja.\
"""

SABLON_ZALBA_NA_PRESUDU = _SABLON_ZALBA_NA_PRESUDU_RAW
SABLON_ZALBA_NA_RESENJE  = _SABLON_ZALBA_NA_RESENJE_RAW
SABLON_TUZBA_NAKNADA_STETE = _SABLON_TUZBA_NAKNADA_STETE_RAW
SABLON_TUZBA_RADNI_SPOR = (
    _SABLON_TUZBA_RADNI_SPOR_RAW
    .replace("__ZR_FULL__", ZR_FULL_REFERENCE)
)

_SABLON_OPOMENA_DUZNIK_RAW = """\
OPOMENA PRE TUŽBE

{POVERILAC_IME}
{DATUM_OPOMENE}

{DUZNIK_IME}

Predmet: Opomena za plaćanje duga — poslednji poziv pre pokretanja sudskog postupka

Poštovani/a,

Obaveštavamo Vas da po osnovu {OSNOV_DUGA} imate dospelu i neizmirenu novčanu\
 obavezu prema {POVERILAC_IME} u ukupnom iznosu od {IZNOS_DUGA} RSD.

Uprkos ranijim pozivima, navedeni iznos nije plaćen u ugovorenom roku.

POSLEDNJI ROK ZA PLAĆANJE: {ROK_PLACANJA}

Ukoliko plaćanje ne bude izvršeno do navedenog roka, bićemo prinuđeni da pokrenemo\
 sudski postupak za naplatu potraživanja, uključujući i zakonsku zateznu kamatu,\
 troškove postupka i advokatske troškove.

Nadamo se da će ovaj dopis biti dovoljan podstrek za dobrovoljno izmirenje obaveze.

S poštovanjem,

                                                {POVERILAC_IME}
                                            ____________________

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre slanja.\
"""

_SABLON_ZAHTEV_POSLODAVCU_RAW = """\
ZAHTEV ZAPOSLENOG

{ZAPOSLENI_IME}
{DATUM}

{POSLODAVAC_IME}

Predmet: {PREDMET_ZAHTEVA}

Poštovani/a,

Na osnovu __ZR_SHORT__ i važećih propisa Republike Srbije, a naročito {PRAVNI_OSNOV},\
 obraćam Vam se sledećim zahtevom:

{PREDMET_ZAHTEVA}

Molim Vas da mi u roku od {ROK_ODGOVORA} od prijema ovog zahteva dostavite pismeni\
 odgovor i preduzmete odgovarajuće mere u skladu sa zakonskim obavezama poslodavca.

Ukoliko na ovaj zahtev ne dobijemo odgovor u navedenom roku, biću prinuđen/a da\
 pokrenem odgovarajući postupak pred nadležnim organima.

S poštovanjem,

                                                {ZAPOSLENI_IME}
                                            ____________________

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre slanja.\
"""

_SABLON_OBAVEST_OTKAZ_RAW = """\
OBAVEŠTENJE O OTKAZU UGOVORA

{STRANA_KOJA_OTKAZUJE}
{DATUM_OTKAZA}

{DRUGA_STRANA}

Predmet: Obaveštenje o otkazu ugovora o radu / poslovnog ugovora

Poštovani/a,

Ovim putem Vas obaveštavamo da je {STRANA_KOJA_OTKAZUJE} donela odluku\
 o otkazu ugovornog odnosa, i to iz sledećeg razloga:

{RAZLOG}

Otkazni rok iznosi {OTKAZNI_ROK}.

U skladu sa navedenim, ugovorni odnos prestaje po isteku otkaznog roka,\
 počev od {DATUM_OTKAZA}.

Molimo Vas da u otkaznom roku izmirite sve preuzete obaveze i preduzmete\
 potrebne radnje u skladu sa ugovorom i važećim propisima.

S poštovanjem,

                                                {STRANA_KOJA_OTKAZUJE}
                                            ____________________

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan\
 od strane ovlašćenog pravnika pre slanja.\
"""

SABLON_OPOMENA_DUZNIK   = _SABLON_OPOMENA_DUZNIK_RAW
SABLON_ZAHTEV_POSLODAVCU = (
    _SABLON_ZAHTEV_POSLODAVCU_RAW
    .replace("__ZR_SHORT__", ZR_SHORT_REFERENCE)
)
SABLON_OBAVEST_OTKAZ = _SABLON_OBAVEST_OTKAZ_RAW

# ─────────────────────────────────────────────────────────────────────────────
# Novi šabloni P1.2 — Legal Form Library
# ─────────────────────────────────────────────────────────────────────────────

SABLON_UGOVOR_KUPOPRODAJA = """\
UGOVOR O KUPOPRODAJI

Zaključen {DATUM} u {MESTO}, između:

PRODAVAC: {PRODAVAC_IME}, {PRODAVAC_ADRESA}
(u daljem tekstu: Prodavac)

i

KUPAC: {KUPAC_IME}, {KUPAC_ADRESA}
(u daljem tekstu: Kupac)


Član 1 — Predmet ugovora
Prodavac prodaje, a Kupac kupuje sledeći predmet:
{PREDMET_PRODAJE}

Član 2 — Kupoprodajna cena
Kupoprodajna cena iznosi {KUPOPRODAJNA_CENA} dinara.
Plaćanje se vrši: {NACIN_PLACANJA}.

Član 3 — Rok isporuke
Prodavac se obavezuje da preda predmet prodaje Kupcu u roku od {ROK_ISPORUKE}.

Član 4 — Pravo vlasništva
Pravo vlasništva na predmetu prodaje prelazi na Kupca nakon isplate celokupne kupoprodajne cene.

Član 5 — Garancija i reklamacije
Prodavac garantuje da predmet prodaje nema skrivenih mana i da nije opterećen pravima trećih lica.

Član 6 — Rešavanje sporova
Eventualne sporove ugovorne strane će rešavati sporazumno, a ako to ne bude moguće, nadležan je sud u mestu zaključenja ugovora.

Član 7 — Primerci
Ovaj ugovor je sačinjen u dva (2) istovetna primerka, po jedan za svaku ugovornu stranu.


___________________________
PRODAVAC

___________________________
KUPAC
"""

SABLON_UGOVOR_ZAKUP = """\
UGOVOR O ZAKUPU NEPOKRETNOSTI

Zaključen {DATUM} u {MESTO}, između:

ZAKUPODAVAC: {ZAKUPODAVAC_IME}, {ZAKUPODAVAC_ADRESA}
(u daljem tekstu: Zakupodavac)

i

ZAKUPAC: {ZAKUPAC_IME}, {ZAKUPAC_ADRESA}
(u daljem tekstu: Zakupac)


Član 1 — Predmet zakupa
Zakupodavac daje u zakup Zakupcu sledeću nepokretnost:
{NEKRETNINA_OPIS}

Član 2 — Period zakupa
Ugovor se zaključuje na period od {PERIOD_ZAKUPA_OD} do {PERIOD_ZAKUPA_DO}.

Član 3 — Zakupnina
Mesečna zakupnina iznosi {ZAKUPNINA} dinara i plaća se {ROK_PLACANJA} u mesecu za tekući mesec.

Član 4 — Depozit
{DEPOZIT_CLAN}

Član 5 — Obaveze Zakupca
Zakupac se obavezuje da: (1) plaća zakupninu u ugovorenom roku; (2) koristi nepokretnost isključivo u ugovorene svrhe; (3) održava nepokretnost u stanju u kakvom ju je preuzeo; (4) ne vrši izmene bez pisane saglasnosti Zakupodavca.

Član 6 — Obaveze Zakupodavca
Zakupodavac se obavezuje da: (1) preda nepokretnost u stanju pogodnom za ugovorenu upotrebu; (2) vrši redovne popravke i održavanje nosive konstrukcije.

Član 7 — Raskid ugovora
Svaka ugovorna strana može raskinuti ugovor davanjem pisane otkazne izjave sa 30 dana unapred.

Član 8 — Primerci
Ovaj ugovor je sačinjen u dva (2) istovetna primerka, po jedan za svaku ugovornu stranu.


___________________________
ZAKUPODAVAC

___________________________
ZAKUPAC
"""

SABLON_PRIGOVOR_PLATNI_NALOG = """\
{SUD_NAZIV}
{SUD_ADRESA}

                                                    Dužnik (podnosilac prigovora): {DUZNIK_IME},
                                                    {DUZNIK_ADRESA}

                                                    Poverilac: {POVERILAC_IME}

Predmet: Prigovor na platni nalog br. {BROJ_PREDMETA}


P R I G O V O R
na platni nalog


Platni nalog ovog suda br. {BROJ_PREDMETA} dostavljen je dužniku dana {DATUM_DOSTAVE}.
Dužnik u zakonskom roku od 8 dana izjavljuje prigovor na navedeni platni nalog.


RAZLOZI PRIGOVORA:

{RAZLOZI_PRIGOVORA}


Na osnovu navedenog, dužnik predlaže sudu da:
1. Prihvati ovaj prigovor kao osnovan i blagovremen;
2. Ukine platni nalog br. {BROJ_PREDMETA} u delu koji se ospori;
3. Zakazane ročište za glavnu raspravu.

Prilog: Dokazi u prilogu.

Dana {DATUM} u {MESTO}.

___________________________
Dužnik / Punomoćnik
"""

SABLON_PREDLOG_PRIVREMENA_MERA = """\
{SUD_NAZIV}
{SUD_ADRESA}

                                                    Predlagač: {PREDLAGAC_IME},
                                                    {PREDLAGAC_ADRESA}

                                                    Protivnik obezbeđenja: {PROTIVNIK_IME},
                                                    {PROTIVNIK_ADRESA}


PREDLOG ZA ODREĐIVANJE PRIVREMENE MERE
(čl. 302-319 ZIO)


I. POTRAŽIVANJE KOJE SE OBEZBEĐUJE

{POTRAZIVANJE_OPIS}
{IZNOS_POTRAZIVANJA_CLAN}


II. PREDLOŽENA PRIVREMENA MERA

Predlagač predlaže sudu da odredi sledeću privremenu meru:
{PREDLOZENA_MERA}


III. OKOLNOSTI KOJE OPRAVDAVAJU ODREĐIVANJE PRIVREMENE MERE

{OPASNOST_OPIS}

Predlagač ukazuje da bez određivanja predložene mere postoji ozbiljna opasnost da će ostvarivanje potraživanja biti onemogućeno ili znatno otežano (čl. 302 st. 1 ZIO).


IV. PREDLOG

Na osnovu iznetog, predlagač predlaže sudu da:
1. Odredi traženu privremenu meru;
2. Naloži protivniku obezbeđenja da postupi u skladu sa merom.

Prilog: Dokazi u prilogu.

Dana {DATUM}.

___________________________
Predlagač / Punomoćnik
"""

SABLON_TUZBA_RAZVOD = """\
{SUD_NAZIV}
{SUD_ADRESA}

                                                    Tužilac: {TUZILAC_IME},
                                                    {TUZILAC_ADRESA}

                                                    Tuženi: {TUZENI_IME},
                                                    {TUZENI_ADRESA}


T U Ž B A
radi razvoda braka


I. BRAK

Tužilac i tuženi zaključili su brak pred matičarom {MATICNA_OPSTINA} dana {DATUM_BRAKA}.
Brak je trajao {ZAJEDNICKI_BRAK_TRAJAO}.
{DECA_CLAN}


II. RAZLOZI ZA RAZVOD

{RAZLOZI}

Odnosi između stranaka su ozbiljno i trajno poremećeni tako da je zajednički život postao nepodnošljiv (čl. 41 Porodičnog zakona).


III. ZAHTEVI
{ZAHTEV_DECA_CLAN}
{ZAHTEV_IMOVINA_CLAN}


IV. PREDLOG

Na osnovu svega navedenog, predlaže se sudu da donese presudu kojom se:
1. RAZVODI brak zaključen između tužioca {TUZILAC_IME} i tuženog {TUZENI_IME};
{PETITUM_DECA}{PETITUM_IMOVINA}
2. Tuženi obaveže da tužiocu naknadi troškove postupka.

Dana {DATUM}.

___________________________
Tužilac / Punomoćnik
"""

SABLON_KRIVICNA_PRIJAVA = """\
REPUBLIČKO JAVNO TUŽILAŠTVO
(Osnovno javno tužilaštvo u ________________________)

                                                    Podnosilac: {PODNOSILAC_IME},
                                                    {PODNOSILAC_ADRESA}
                                                    {PODNOSILAC_JMBG_CLAN}


KRIVIČNA PRIJAVA


Podnosim krivičnu prijavu protiv:

Okrivljenog: {OKRIVLJENI_IME}, {OKRIVLJENI_ADRESA}

Zbog krivičnog dela: {KRIVICNO_DELO} iz {ZAKONSKI_CLAN} Krivičnog zakonika RS.


I. OPIS DOGADJAJA

{OPIS_DOGADJAJA}

Navedena dela su učinjena dana {DATUM_DOGADJAJA}.


II. DOKAZI

{DOKAZI}


III. ZAHTEV

Na osnovu izloženog, predlažem nadležnom tužiocu da:
1. Pokrene istragu/predistražni postupak protiv okrivljenog;
2. Preduzme sve potrebne mere radi rasvjetljavanja slučaja.

Dana {DATUM}.

___________________________
Podnosilac prijave
"""

# ─────────────────────────────────────────────────────────────────────────────
# Ekstrakcioni promptovi po tipu
# ─────────────────────────────────────────────────────────────────────────────

# Bug 3: explicit JMBG instruction added to base prompt
_EKSTRAKCIONI_BAZA = """\
Ti si pravni asistent koji ekstraktuje podatke iz slobodnog opisa.
Vrati ČIST JSON — bez komentara, bez markdown blokova, bez ikakvog teksta van JSON-a.
Ako polje nije pomenuto, ostavi prazan string "".
ZABRANJENO: izmišljati ili pretpostavljati podatke koji nisu u tekstu.
JMBG: Tačno 13 cifara. Ako se u opisu pojavi 13-cifreni broj, ekstraktuj kao JMBG\
 za odgovarajuću osobu (zaposleni_jmbg, vlastodavac_jmbg) u zavisnosti od konteksta.
"""

EKSTRAKCIONI_PROMPTOVI: dict[str, str] = {

"ugovor_neodredjeno": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "poslodavac_adresa": "Sedište/adresa poslodavca",
  "poslodavac_pib": "PIB poslodavca ako je naveden, inače prazno",
  "poslodavac_mb": "Matični broj (MB) poslodavca ako je naveden, inače prazno",
  "poslodavac_zastupnik": "Ime zastupnika/direktora poslodavca ako je navedeno (npr. 'direktor Petar Petrović'), inače prazno",
  "zaposleni_ime": "Puno ime zaposlenog",
  "zaposleni_jmbg": "JMBG zaposlenog — tačno 13 cifara ako je naveden, inače prazno",
  "zaposleni_adresa": "Adresa zaposlenog",
  "radno_mesto": "Naziv radnog mesta",
  "opis_posla": "Kratak opis posla",
  "mesto_rada": "Mesto/grad rada",
  "osnovna_zarada": "Iznos osnovne zarade u RSD (samo broj, bez 'dinara')",
  "rok_isplate": "Dan u mesecu za isplatu zarade (npr. 10)",
  "datum_pocetka": "Datum početka rada u formatu DD.MM.YYYY bez trailing tačke",
  "radno_vreme": "Broj radnih sati nedeljno (samo broj, npr. 40)",
  "otkazni_rok_zaposleni": "Otkazni rok zaposlenog (npr. '30 radnih dana')",
  "otkazni_rok_poslodavac": "Otkazni rok poslodavca (npr. '30 radnih dana')",
  "probni_rad": "Trajanje probnog rada (npr. '3 meseca') ili prazno ako nema",
  "godisnji_odmor_dani": "Broj dana godišnjeg odmora (samo broj, npr. 20) ili prazno",
  "ima_tajnost": "true ako postoji klauzula o tajnosti, inače false",
  "tajnost_rok": "Trajanje obaveze tajnosti nakon prestanka (npr. '2 godine') ili prazno",
  "ima_konkurentsku": "true ako postoji konkurentska klauzula, inače false",
  "konkurentska_trajanje": "Trajanje zabrane (npr. '1 godina') ili prazno",
  "konkurentska_naknada_procenat": "Procenat zarade kao naknada (samo broj, npr. 30) ili prazno",
  "bonus_procenat": "Maks. bonus kao % zarade (samo broj, npr. 30) ili prazno",
  "datum": "Datum zaključenja u formatu DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto zaključenja"
}
""",

"ugovor_odredjeno": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "poslodavac_adresa": "Sedište/adresa poslodavca",
  "poslodavac_pib": "PIB poslodavca ako je naveden, inače prazno",
  "poslodavac_mb": "Matični broj (MB) poslodavca ako je naveden, inače prazno",
  "poslodavac_zastupnik": "Ime zastupnika/direktora poslodavca ako je navedeno, inače prazno",
  "zaposleni_ime": "Puno ime zaposlenog",
  "zaposleni_jmbg": "JMBG zaposlenog — tačno 13 cifara ako je naveden, inače prazno",
  "zaposleni_adresa": "Adresa zaposlenog",
  "radno_mesto": "Naziv radnog mesta",
  "opis_posla": "Kratak opis posla",
  "mesto_rada": "Mesto/grad rada",
  "osnovna_zarada": "Iznos osnovne zarade u RSD",
  "rok_isplate": "Dan u mesecu za isplatu zarade",
  "datum_pocetka": "Datum početka rada u formatu DD.MM.YYYY bez trailing tačke",
  "trajanje_odredjeno": "Trajanje ugovora (npr. '12 meseci', '1 godina')",
  "razlog_odredjenog": "Razlog za određeno vreme — npr. zamena odsutnog radnika, sezonski posao, privremeni porast obima posla (ZR čl. 37)",
  "radno_vreme": "Broj radnih sati nedeljno (samo broj)",
  "otkazni_rok_zaposleni": "Otkazni rok zaposlenog",
  "otkazni_rok_poslodavac": "Otkazni rok poslodavca",
  "probni_rad": "Trajanje probnog rada ili prazno",
  "godisnji_odmor_dani": "Broj dana godišnjeg odmora (samo broj) ili prazno",
  "ima_tajnost": "true ako postoji klauzula o tajnosti, inače false",
  "tajnost_rok": "Trajanje tajnosti nakon prestanka ili prazno",
  "ima_konkurentsku": "true ako postoji konkurentska klauzula, inače false",
  "konkurentska_trajanje": "Trajanje zabrane ili prazno",
  "konkurentska_naknada_procenat": "Procenat zarade kao naknada (samo broj) ili prazno",
  "bonus_procenat": "Maks. bonus kao % zarade (samo broj) ili prazno",
  "datum": "Datum zaključenja u formatu DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto zaključenja"
}
""",

"aneks": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "zaposleni_ime": "Puno ime zaposlenog",
  "aneks_broj": "Broj aneksa (npr. I, II, 1/2026) ili prazno",
  "referenca_ugovora": "Referenca na osnovni ugovor (npr. 'br. 15/2024 od 01.03.2024')",
  "izmene_opis": "Opis izmena — šta se menja, novi uslovi",
  "datum_primene": "Datum od kojeg stupaju izmene na snagu, format DD.MM.YYYY bez trailing tačke",
  "datum": "Datum zaključenja aneksa, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto zaključenja"
}
""",

"sporazumni_raskid": _EKSTRAKCIONI_BAZA + """
{
  "poslodavac_ime": "Pun naziv poslodavca",
  "zaposleni_ime": "Puno ime zaposlenog",
  "datum_prestanka": "Datum prestanka radnog odnosa, format DD.MM.YYYY bez trailing tačke",
  "datum_zakljucenja_originalnog_ugovora": "Datum zaključenja originalnog ugovora o radu ako je pomenut (npr. '15.03.2024'), inače prazno",
  "ima_otpremninu": "true ako je otpremnina navedena, inače false",
  "otpremnina_iznos": "Iznos otpremnine u RSD (samo broj) ili prazno",
  "napomena": "Eventualna posebna napomena ili prazno",
  "datum": "Datum zaključenja sporazuma, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto zaključenja"
}
""",

"punomocje": _EKSTRAKCIONI_BAZA + """
{
  "vlastodavac_ime": "Puno ime vlastodavca",
  "vlastodavac_jmbg": "JMBG vlastodavca — tačno 13 cifara ako je naveden, inače prazno",
  "vlastodavac_adresa": "Adresa vlastodavca",
  "punomocnik_ime": "Puno ime punomoćnika",
  "punomocnik_adresa": "Adresa punomoćnika",
  "predmet_punomocja": "Opis radnji koje punomoćnik može preduzeti (noun phrase ili verb phrase — oba su gramatički ispravna)",
  "rok_vazenja": "Rok važenja punomoćja (npr. 'do opoziva', '6 meseci', 'do 31.12.2026')",
  "ima_supstituciju": "true ako punomoćnik sme dalje ovlašćivati, inače false",
  "datum": "Datum izdavanja punomoćja, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto izdavanja"
}
""",

"zalba_na_presudu": _EKSTRAKCIONI_BAZA + """
{
  "podnosilac_ime": "Puno ime podnosioca žalbe",
  "advokat_ime": "Puno ime advokata ako je naveden, inače prazno",
  "sud_naziv": "Naziv drugostepenog suda kome se žalba podnosi",
  "broj_predmeta": "Broj predmeta prvostepene presude (npr. P. 123/2024)",
  "datum_presude": "Datum prvostepene presude, format DD.MM.YYYY bez trailing tačke",
  "razlozi_zalbe": "Razlozi žalbe — slobodan tekst koji opisuje zašto se presuda pobija",
  "predlog": "Predlog drugostepenom sudu (npr. ukine presudu, preinači, vrati na ponovni postupak)",
  "datum": "Datum izjavljivanja žalbe, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto izjavljivanja žalbe"
}
""",

"zalba_na_resenje": _EKSTRAKCIONI_BAZA + """
{
  "podnosilac_ime": "Puno ime podnosioca žalbe",
  "organ_naziv": "Naziv organa koji je doneo rešenje",
  "broj_resenja": "Broj rešenja koje se pobija",
  "datum_resenja": "Datum rešenja, format DD.MM.YYYY bez trailing tačke",
  "razlozi_zalbe": "Razlozi žalbe — slobodan tekst koji opisuje razloge pobijanja rešenja",
  "predlog": "Predlog drugostepenom organu (npr. poništi rešenje, izmeni, vrati na ponovni postupak)",
  "datum": "Datum izjavljivanja žalbe, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto izjavljivanja žalbe"
}
""",

"tuzba_naknada_stete": _EKSTRAKCIONI_BAZA + """
{
  "tuzilac_ime": "Puno ime/naziv tužioca",
  "tuzeni_ime": "Puno ime/naziv tuženog",
  "sud_naziv": "Naziv suda kome se tužba podnosi",
  "opis_stete": "Opis štetnog događaja i nastale štete",
  "iznos_stete": "Iznos potraživane naknade u RSD (samo broj)",
  "pravni_osnov_clan": "Broj člana ZOO koji se primenjuje za naknadu (npr. 200 za nematerijalnu, 189 za materijalnu)",
  "dokazi": "Lista dokaza koje tužilac predlaže (slobodan tekst ili nabrajanje)",
  "datum": "Datum podnošenja tužbe, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto podnošenja tužbe"
}
""",

"tuzba_radni_spor": _EKSTRAKCIONI_BAZA + """
{
  "tuzilac_ime": "Puno ime zaposlenog (tužioca)",
  "poslodavac_ime": "Pun naziv poslodavca (tuženog)",
  "sud_naziv": "Naziv suda kome se tužba podnosi",
  "opis_povrede": "Opis povrede prava iz radnog odnosa (npr. nezakonit otkaz, neisplata zarade)",
  "zahtev": "Tužbeni zahtev zaposlenog (npr. vraćanje na rad, isplata zarade, naknada štete)",
  "datum_povrede": "Datum nastanka povrede prava, format DD.MM.YYYY bez trailing tačke",
  "datum": "Datum podnošenja tužbe, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto podnošenja tužbe"
}
""",

"opomena_duznik": _EKSTRAKCIONI_BAZA + """
{
  "poverilac_ime": "Puno ime/naziv poverioca",
  "duznik_ime": "Puno ime/naziv dužnika",
  "iznos_duga": "Iznos duga u RSD (samo broj)",
  "osnov_duga": "Osnov duga — npr. faktura br. X, ugovor od Y, neisplaćena zarada",
  "rok_placanja": "Krajnji rok za plaćanje, format DD.MM.YYYY bez trailing tačke",
  "datum_opomene": "Datum opomene, format DD.MM.YYYY bez trailing tačke"
}
""",

"zahtev_poslodavcu": _EKSTRAKCIONI_BAZA + """
{
  "zaposleni_ime": "Puno ime zaposlenog",
  "poslodavac_ime": "Pun naziv poslodavca",
  "predmet_zahteva": "Sadržaj zahteva — šta zaposleni traži od poslodavca",
  "pravni_osnov": "Zakonska osnova zahteva (npr. ZR čl. 40, ZR čl. 120, ZR čl. 145)",
  "rok_odgovora": "Rok za odgovor poslodavca (npr. '8 dana', '15 dana')",
  "datum": "Datum zahteva, format DD.MM.YYYY bez trailing tačke"
}
""",

"obaveštenje_o_otkazu": _EKSTRAKCIONI_BAZA + """
{
  "strana_koja_otkazuje": "Ime/naziv strane koja otkazuje ugovor",
  "druga_strana": "Ime/naziv druge ugovorne strane",
  "datum_otkaza": "Datum izjavljivanja otkaza, format DD.MM.YYYY bez trailing tačke",
  "otkazni_rok": "Dužina otkaznog roka (npr. '30 dana', '15 radnih dana')",
  "razlog": "Razlog otkaza — slobodan tekst"
}
""",

"ugovor_kupoprodaja": _EKSTRAKCIONI_BAZA + """
{
  "prodavac_ime": "Puno ime/naziv prodavca",
  "prodavac_adresa": "Adresa prodavca",
  "kupac_ime": "Puno ime/naziv kupca",
  "kupac_adresa": "Adresa kupca",
  "predmet_prodaje": "Opis predmeta prodaje",
  "kupoprodajna_cena": "Kupoprodajna cena u RSD (samo broj)",
  "nacin_placanja": "Način plaćanja (npr. gotovinom, virmanskim prenosom)",
  "rok_isporuke": "Rok isporuke predmeta (npr. '5 dana od uplate')",
  "datum": "Datum zaključenja ugovora, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto zaključenja ugovora"
}
""",

"ugovor_zakup": _EKSTRAKCIONI_BAZA + """
{
  "zakupodavac_ime": "Puno ime/naziv zakupodavca",
  "zakupodavac_adresa": "Adresa zakupodavca",
  "zakupac_ime": "Puno ime/naziv zakupca",
  "zakupac_adresa": "Adresa zakupca",
  "nekretnina_opis": "Opis nepokretnosti koja se daje u zakup (adresa, katastarska parcela, površina)",
  "zakupnina": "Mesečna zakupnina u RSD",
  "rok_placanja": "Rok za plaćanje zakupnine (npr. 'do 5. u mesecu')",
  "period_zakupa_od": "Početak zakupa, format DD.MM.YYYY",
  "period_zakupa_do": "Kraj zakupa (ili 'na neodređeno vreme')",
  "depozit": "Depozit u RSD ako je naveden, inače prazno",
  "datum": "Datum zaključenja ugovora, format DD.MM.YYYY bez trailing tačke",
  "mesto": "Mesto zaključenja"
}
""",

"prigovor_platni_nalog": _EKSTRAKCIONI_BAZA + """
{
  "sud_naziv": "Naziv suda koji je izdao platni nalog",
  "sud_adresa": "Adresa suda",
  "broj_predmeta": "Broj predmeta (Pl br. X/YYYY)",
  "duznik_ime": "Puno ime/naziv dužnika koji podnosi prigovor",
  "duznik_adresa": "Adresa dužnika",
  "poverilac_ime": "Ime/naziv poverioca",
  "iznos": "Iznos iz platnog naloga u RSD",
  "datum_dostave": "Datum dostave platnog naloga, format DD.MM.YYYY",
  "razlozi_prigovora": "Razlozi zbog kojih se podnosi prigovor",
  "datum": "Datum podnošenja prigovora, format DD.MM.YYYY bez trailing tačke"
}
""",

"predlog_privremena_mera": _EKSTRAKCIONI_BAZA + """
{
  "sud_naziv": "Naziv suda",
  "sud_adresa": "Adresa suda",
  "predlagac_ime": "Ime/naziv predlagača",
  "predlagac_adresa": "Adresa predlagača",
  "protivnik_ime": "Ime/naziv protivnika obezbeđenja",
  "protivnik_adresa": "Adresa protivnika",
  "potraživanje_opis": "Opis potraživanja koje se obezbeđuje",
  "iznos_potrazivanja": "Iznos potraživanja u RSD ako je naveden",
  "predlozena_mera": "Konkretna predložena privremena mera (npr. zabrana otuđenja imovine, zaplena računa)",
  "opasnost_opis": "Opis opasnosti i razlozi hitnosti",
  "datum": "Datum podnošenja predloga, format DD.MM.YYYY bez trailing tačke"
}
""",

"tuzba_razvod": _EKSTRAKCIONI_BAZA + """
{
  "sud_naziv": "Naziv porodičnog/osnovnog suda",
  "sud_adresa": "Adresa suda",
  "tuzilac_ime": "Puno ime tužioca",
  "tuzilac_adresa": "Adresa tužioca",
  "tuzeni_ime": "Puno ime tuženog",
  "tuzeni_adresa": "Adresa tuženog",
  "datum_braka": "Datum zaključenja braka, format DD.MM.YYYY",
  "maticna_opstina": "Matična opština gde je brak zaključen",
  "zajednicki_brak_trajao": "Koliko dugo je brak trajao (npr. '5 godina')",
  "deca_opis": "Podaci o zajedničkoj deci ako ima (ime, datum rodjenja), inače prazno",
  "razlozi": "Razlozi za razvod (slobodan tekst — ne navodi se konkretni razlog ako stranka ne želi)",
  "zahtev_deca": "Zahtev u pogledu staranja nad decom (ako ima dece)",
  "zahtev_imovina": "Zahtev u pogledu podele bračne tekovine (kratko)",
  "datum": "Datum podnošenja tužbe, format DD.MM.YYYY bez trailing tačke"
}
""",

"krivicna_prijava": _EKSTRAKCIONI_BAZA + """
{
  "podnosilac_ime": "Puno ime podnosioca krivične prijave",
  "podnosilac_adresa": "Adresa podnosioca",
  "podnosilac_jmbg": "JMBG podnosioca — 13 cifara ako je naveden, inače prazno",
  "okrivljeni_ime": "Puno ime osumnjičenog/okrivljenog",
  "okrivljeni_adresa": "Adresa okrivljenog ako je poznata",
  "krivicno_delo": "Naziv krivičnog dela (npr. prevara, kradja, teška telesna povreda)",
  "zakonski_clan": "Zakonski osnov — član KZ-a (npr. čl. 208 KZ)",
  "opis_dogadjaja": "Detaljan opis dogadjaja — šta se desilo, kada i gde",
  "datum_dogadjaja": "Datum kada se krivično delo desilo, format DD.MM.YYYY",
  "dokazi": "Dostupni dokazi (npr. svedoci, snimci, dokumenti)",
  "datum": "Datum podnošenja prijave, format DD.MM.YYYY bez trailing tačke"
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
    "zalba_na_presudu": {
        "label":      "Žalba na presudu",
        "opis_hint":  (
            "Npr. Podnosilac: Marko Marković, Beograd. Sud: Apelacioni sud u Beogradu. "
            "Predmet: P. 456/2024. Datum presude: 15.04.2025. "
            "Razlozi: pogrešno utvrđeno činjenično stanje, netačna primena materijalnog prava. "
            "Predlog: preinači presudu i usvoji tužbeni zahtev u celosti."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["zalba_na_presudu"],
        "sablon":     SABLON_ZALBA_NA_PRESUDU,
        "compliance_tip": None,
    },
    "zalba_na_resenje": {
        "label":      "Žalba na rešenje",
        "opis_hint":  (
            "Npr. Podnosilac: Ana Nikolić. Organ: Poreska uprava, Filijala Beograd. "
            "Rešenje br. 462-00-123/2025 od 10.03.2025. "
            "Razlozi: rešenje je zasnovano na pogrešnoj primeni Zakona o porezu na prihode. "
            "Predlog: poništiti rešenje i predmet vratiti na ponovni postupak."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["zalba_na_resenje"],
        "sablon":     SABLON_ZALBA_NA_RESENJE,
        "compliance_tip": None,
    },
    "tuzba_naknada_stete": {
        "label":      "Tužba za naknadu štete",
        "opis_hint":  (
            "Npr. Tužilac: Jovana Jovanović, Beograd. Tuženi: 'FastDriving' d.o.o. "
            "Saobraćajna nezgoda 20.01.2025, telesne povrede, naknada 500.000 RSD. "
            "Sud: Osnovi sud u Beogradu. Dokazi: policijski zapisnik, medicinska dokumentacija."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["tuzba_naknada_stete"],
        "sablon":     SABLON_TUZBA_NAKNADA_STETE,
        "compliance_tip": None,
    },
    "tuzba_radni_spor": {
        "label":      "Tužba — radni spor",
        "opis_hint":  (
            "Npr. Zaposleni: Petar Petrović. Poslodavac: 'Industrija AB' d.o.o., Novi Sad. "
            "Nezakonit otkaz od 05.03.2025, zahtev za vraćanje na rad i isplatu izgubljene zarade. "
            "Sud: Osnovni sud u Novom Sadu."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["tuzba_radni_spor"],
        "sablon":     SABLON_TUZBA_RADNI_SPOR,
        "compliance_tip": None,
    },
    "opomena_duznik": {
        "label":      "Opomena pre tužbe",
        "opis_hint":  (
            "Npr. Poverilac: 'ServisPlus' d.o.o., Beograd. Dužnik: Nikola Nikolić. "
            "Dug: 180.000 RSD po osnovu fakture br. 45/2025. "
            "Rok za plaćanje: 15.07.2025."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["opomena_duznik"],
        "sablon":     SABLON_OPOMENA_DUZNIK,
        "compliance_tip": None,
    },
    "zahtev_poslodavcu": {
        "label":      "Zahtev zaposlenog poslodavcu",
        "opis_hint":  (
            "Npr. Zaposleni: Milica Milić. Poslodavac: 'TechCorp' d.o.o. "
            "Zahtev: isplata neisplaćene zarade za mart 2025, pravni osnov ZR čl. 120. "
            "Rok za odgovor: 8 dana."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["zahtev_poslodavcu"],
        "sablon":     SABLON_ZAHTEV_POSLODAVCU,
        "compliance_tip": None,
    },
    "obaveštenje_o_otkazu": {
        "label":      "Obaveštenje o otkazu ugovora",
        "opis_hint":  (
            "Npr. Strana koja otkazuje: 'Uvoz-Izvoz' d.o.o. Druga strana: 'Distribucija' d.o.o. "
            "Datum otkaza: 01.06.2025. Otkazni rok: 30 dana. "
            "Razlog: obostrani sporazum o prestanku poslovne saradnje."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["obaveštenje_o_otkazu"],
        "sablon":     SABLON_OBAVEST_OTKAZ,
        "compliance_tip": None,
    },
    "ugovor_kupoprodaja": {
        "label":      "Ugovor o kupoprodaji",
        "opis_hint":  (
            "Npr. Prodavac: Marko Marković, Beograd. Kupac: 'Trgovina Plus' d.o.o. "
            "Predmet: laptop Lenovo ThinkPad X1, serijski br. 12345. Cena: 150.000 RSD. "
            "Plaćanje: virmanskim prenosom u roku od 3 dana."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["ugovor_kupoprodaja"],
        "sablon":     SABLON_UGOVOR_KUPOPRODAJA,
        "compliance_tip": None,
    },
    "ugovor_zakup": {
        "label":      "Ugovor o zakupu nepokretnosti",
        "opis_hint":  (
            "Npr. Zakupodavac: Jelena Jović, ul. Cara Lazara 5, Beograd. "
            "Zakupac: 'StartupCo' d.o.o. Stan: 60m², ul. Kneza Miloša 10, Beograd. "
            "Zakupnina: 60.000 RSD/mesečno. Period: 01.07.2026 – 01.07.2027. Depozit: 2 zakupnine."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["ugovor_zakup"],
        "sablon":     SABLON_UGOVOR_ZAKUP,
        "compliance_tip": None,
    },
    "prigovor_platni_nalog": {
        "label":      "Prigovor na platni nalog",
        "opis_hint":  (
            "Npr. Sud: Osnovni sud u Beogradu. Broj predmeta: Pl. 1234/2026. "
            "Dužnik: Nikola Nikolić, ul. Vojvode Mišića 3, Beograd. Iznos: 80.000 RSD. "
            "Dostava: 10.06.2026. Razlog prigovora: dug nije osnovan, faktura je sporna."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["prigovor_platni_nalog"],
        "sablon":     SABLON_PRIGOVOR_PLATNI_NALOG,
        "compliance_tip": None,
    },
    "predlog_privremena_mera": {
        "label":      "Predlog za privremenu meru",
        "opis_hint":  (
            "Npr. Predlagač: 'Pekara ABC' d.o.o. Protivnik: Petar Petrović. "
            "Potraživanje: 500.000 RSD iz ugovora o delu. Mera: zabrana otuđenja nekretnine. "
            "Opasnost: protivnik prodaje jedinu imovinu. Sud: Privredni sud Beograd."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["predlog_privremena_mera"],
        "sablon":     SABLON_PREDLOG_PRIVREMENA_MERA,
        "compliance_tip": None,
    },
    "tuzba_razvod": {
        "label":      "Tužba za razvod braka",
        "opis_hint":  (
            "Npr. Tužilac: Ana Anić, Novi Sad. Tuženi: Milan Anić, Novi Sad. "
            "Brak zaključen 15.06.2018 pred matičarom Novi Sad. Zajednička deca: Iva (2020). "
            "Razlozi: dugotrajni bračni nesporazumi, tražilac staranje nad detetom."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["tuzba_razvod"],
        "sablon":     SABLON_TUZBA_RAZVOD,
        "compliance_tip": None,
    },
    "krivicna_prijava": {
        "label":      "Krivična prijava",
        "opis_hint":  (
            "Npr. Podnosilac: Dragana Dragić, Beograd. Okrivljeni: Vuk Vukić, Beograd. "
            "Krivično delo: prevara (čl. 208 KZ). Dana 05.05.2026. prodao lažni stan. "
            "Dokazi: ugovor, priznanica, izjave svedoka."
        ),
        "ekstrakcioni_prompt": EKSTRAKCIONI_PROMPTOVI["krivicna_prijava"],
        "sablon":     SABLON_KRIVICNA_PRIJAVA,
        "compliance_tip": None,
    },
}


def get_types_list() -> list[dict]:
    """Vraća listu tipova za GET /api/nacrt/types."""
    return [
        {"vrsta": k, "label": v["label"], "opis_hint": v["opis_hint"]}
        for k, v in TEMPLATES.items()
    ]
