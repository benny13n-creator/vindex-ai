# -*- coding: utf-8 -*-
"""
Vindex AI PRO — Šabloni za sudske podneske
Hardkodovane forme sa placeholderima.
AI popunjava placeholdere — NIKAD ne generiše pravnu strukturu.
"""

from __future__ import annotations
from typing import Optional

# ─── Tipovi podnesaka ─────────────────────────────────────────────────────────
TIPOVI = {
    "tuzba_naknada_stete":    "Tužba za naknadu štete",
    "zalba_parnicna":         "Žalba na prvostepenu presudu (parnični postupak)",
    "predlog_izvrsenje":      "Predlog za izvršenje",
    "tuzba_radni_spor":       "Tužba u radnom sporu",
    "tuzba_razvod":           "Tužba za razvod braka",
    "prigovor_platni_nalog":  "Prigovor na platni nalog",
    "krivicna_prijava":       "Krivična prijava",
    "predlog_privremena_mera":"Predlog za određivanje privremene mere",
}

# ─── ŠABLON 1: Tužba za naknadu nematerijalne štete ──────────────────────────
SABLON_TUZBA_NAKNADA = """\
{SUD_NAZIV}
{SUD_ADRESA}

                                                    Tužilac: {TUZILAC_IME},
                                                    iz {TUZILAC_ADRESA},
                                                    JMBG: {TUZILAC_JMBG}

                                                    Punomoćnik tužioca: {ADVOKAT_IME},
                                                    advokat iz {ADVOKAT_ADRESA}

                                                    Tuženi: {TUZENI_IME},
                                                    {TUZENI_ADRESA}

Vrednost spora: {VREDNOST_SPORA} dinara


              T U Ž B A
              radi naknade nematerijalne štete


I. ČINJENIČNO STANJE

{CINJENICNO_STANJE}


II. SPECIFIKACIJA NEMATERIJALNE ŠTETE

Tužilac je, kao direktna posledica predmetnog štetnog događaja, pretrpeo sledeće vidove nematerijalne štete:

1. Fizički bolovi

{FIZICKI_BOLOVI_OPIS}

2. Strah

{STRAH_OPIS}
{UMANJENJE_SEKCIJA}
{NARUZENOST_SEKCIJA}

III. PRAVNA KVALIFIKACIJA

{PRAVNA_KVALIFIKACIJA}


IV. DOKAZNA SREDSTVA

{DOKAZNA_SREDSTVA}


V. P E T I T U M

Na osnovu svega izloženog, predlaže se sudu da donese sledeću

P R E S U D U

Obavezuje se tuženi {TUZENI_IME} da tužiocu {TUZILAC_IME} na ime naknade nematerijalne štete isplati:

1. na ime fizičkih bolova iznos od {IZNOS_FIZICKI_BOLOVI} dinara;
2. na ime straha iznos od {IZNOS_STRAH} dinara;
{PETITUM_UMANJENJE}{PETITUM_NARUZENOST}
sve sa zakonskom zateznom kamatom počev od dana presuđenja pa do konačne isplate, kao i da tužiocu nadoknadi troškove parničnog postupka, sve u roku od 15 dana pod pretnjom prinudnog izvršenja.

{OPCIONI_PETITUM}

                                                    Tužilac, odnosno punomoćnik tužioca:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
{PRILOZI}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.
{VIKI_ANALIZA}"""

# ─── ŠABLON 2: Žalba na prvostepenu presudu (parnični postupak) ──────────────
SABLON_ZALBA_PARNICNA = """\
{DRUGOSTEPENI_SUD_NAZIV}
{DRUGOSTEPENI_SUD_ADRESA}

Putem:
{PRVOSTEPENI_SUD_NAZIV}
{PRVOSTEPENI_SUD_ADRESA}

                                                    Žalilac (tužilac/tuženi): {ZALILAC_IME}
                                                    {ZALILAC_ADRESA}
                                                    Zastupa: {ADVOKAT_IME}

                                                    Protivnik žalioca: {PROTIVNIK_IME}
                                                    {PROTIVNIK_ADRESA}

Predmet: {PRVOSTEPENI_SUD_NAZIV}, {BROJ_PREDMETA}


                                Ž A L B A

na presudu {PRVOSTEPENI_SUD_NAZIV} broj {BROJ_PREDMETA} od {DATUM_PRESUDE}


I. POBIJANA PRESUDA

Presudom {PRVOSTEPENI_SUD_NAZIV} broj {BROJ_PREDMETA} od {DATUM_PRESUDE}, {IZREKA_PRESUDE}

Presuda je dostavljena žaliocu dana {DATUM_DOSTAVLJANJA}, a žalba se podnosi dana {DATUM_ZALBE}, dakle u zakonskom roku od 15 dana (čl. 365 ZPP, Sl. glasnik RS, br. 72/2011).


II. ŽALBENI RAZLOZI

Pobijana presuda se napada zbog:

{ZALBA_RAZLOZI_LISTA}


III. OBRAZLOŽENJE ŽALBENIH RAZLOGA

{OBRAZLOZENJE_ZALBE}


IV. ŽALBENI PREDLOG

Na osnovu navedenih razloga, predlaže se {DRUGOSTEPENI_SUD_NAZIV} da:

{ZALBA_PREDLOG}

Alternativno, predlaže se da {DRUGOSTEPENI_SUD_NAZIV} ukine pobijanu presudu i vrati predmet prvostepenom sudu na ponovni postupak.


V. TROŠKOVI ŽALBENOG POSTUPKA

Predlaže se sudu da obaveže protivnika žalioca na naknadu troškova ovog žalbenog postupka.

                                                    Žalilac, odnosno punomoćnik žalioca:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
- Overena kopija pobijane presude
- Punomoćje
{DODATNI_PRILOZI}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.
"""

# ─── ŠABLON 3: Predlog za izvršenje ──────────────────────────────────────────
SABLON_PREDLOG_IZVRSENJE = """\
OSNOVNO/VIŠI SUD U {MESTO_SUDA}
{SUD_ADRESA}


                                                    Tražilac izvršenja: {TRAZILAC_IME}
                                                    {TRAZILAC_ADRESA}
                                                    Zastupa: {ADVOKAT_IME}

                                                    Izvršenik: {IZVRSENIK_IME}
                                                    {IZVRSENIK_ADRESA}
                                                    {IZVRSENIK_JMBG_PIB}


                        P R E D L O G
                        za izvršenje


I. IZVRŠNA ISPRAVA

Kao osnov za pokretanje izvršnog postupka predlaže se {VRSTA_IZVRSNE_ISPRAVE}: {NAZIV_ISPRAVE}, broj {BROJ_ISPRAVE} od {DATUM_ISPRAVE}, kojom je {IZVRSENIK_IME} obavezan da {SADRZAJ_OBAVEZE}.


II. POTRAŽIVANJE

Tražilac izvršenja {TRAZILAC_IME} potražuje od izvršenika {IZVRSENIK_IME}:

- Glavnica: {IZNOS_GLAVNICE} dinara
- Zatezna kamata po stopi {KAMATA_STOPA}% počev od {DATUM_POCETKA_KAMATE} do isplate
- Troškovi prethodnog postupka: {TROSKOVI_POSTUPKA} dinara
{OSTALA_POTRAZIVANJA}

Ukupno: {UKUPAN_IZNOS} dinara (sa kamatom do dana podnošenja predloga)


III. SREDSTVO I PREDMET IZVRŠENJA

Predlaže se sledeće sredstvo izvršenja:

{SREDSTVO_IZVRSENJA}

Predmet izvršenja:

{PREDMET_IZVRSENJA}


IV. ZAKONSKI OSNOV

Ovaj predlog se zasniva na odredbama Zakona o izvršenju i obezbeđenju (Sl. glasnik RS, br. 106/2015, 106/2016, 113/2017, 54/2019), a naročito čl. 34 (izvršna isprava), čl. 68 i dalje (izvršenje na novčanim potraživanjima), čl. 83 i dalje (izvršenje na pokretnim stvarima).


V. PREDLOG

Na osnovu navedenog, predlaže se sudu da donese


R E Š E N J E O I Z V R Š E N J U

kojim se određuje izvršenje radi naplate iznosa od {UKUPAN_IZNOS} dinara, sa zakonskom zateznom kamatom i troškovima izvršnog postupka, sprovođenjem {SREDSTVO_IZVRSENJA_KRATKO}.

                                                    Tražilac izvršenja, odnosno punomoćnik:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
- Original ili overena kopija izvršne isprave
- Potvrda o pravnosnažnosti/izvršnosti
- Punomoćje
{DODATNI_PRILOZI}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.
"""

# ─── ŠABLON 4: Tužba u radnom sporu ─────────────────────────────────────────
SABLON_TUZBA_RADNI_SPOR = """\
{SUD_NAZIV}
{SUD_ADRESA}

                                                    Tužilac (radnik): {TUZILAC_IME},
                                                    iz {TUZILAC_ADRESA},
                                                    JMBG: {TUZILAC_JMBG}

                                                    Punomoćnik tužioca: {ADVOKAT_IME},
                                                    advokat iz {ADVOKAT_ADRESA}

                                                    Tuženi (poslodavac): {TUZENI_IME},
                                                    {TUZENI_ADRESA}
                                                    PIB/MB: {TUZENI_PIB}

Vrednost spora: {VREDNOST_SPORA} dinara


              T U Ž B A
              radi poništaja odluke o otkazu / isplate zarade / naknade štete
              (radni spor)


I. STRANKE I RADNI ODNOS

{STRANKE_I_RADNI_ODNOS}


II. ČINJENIČNO STANJE

{CINJENICNO_STANJE}


III. RAZLOZI TUŽBE

{RAZLOZI_TUZBE}


IV. PRAVNA KVALIFIKACIJA

{PRAVNA_KVALIFIKACIJA}


V. DOKAZNA SREDSTVA

{DOKAZNA_SREDSTVA}


VI. TUŽBENI ZAHTEV

Na osnovu svega izloženog, predlaže se sudu da donese sledeću

P R E S U D U

{TUZBENI_ZAHTEV}

sve sa zakonskom zateznom kamatom od dana dospelosti do isplate, kao i da tuženi naknadi tužiocu troškove parničnog postupka, sve u roku od 15 dana pod pretnjom prinudnog izvršenja.

                                                    Tužilac, odnosno punomoćnik tužioca:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
- Ugovor o radu / rešenje o zasnivanju radnog odnosa
- Odluka o prestanku radnog odnosa (pobijani akt)
- Potvrda o zaradi / obračun zarade
- Punomoćje
{DODATNI_PRILOZI}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.
{VIKI_ANALIZA}"""

# ─── ŠABLON 5: Tužba za razvod braka ─────────────────────────────────────────
SABLON_TUZBA_RAZVOD = """\
{SUD_NAZIV}
{SUD_ADRESA}

                                                    Tužilac (bračni drug): {TUZILAC_IME},
                                                    iz {TUZILAC_ADRESA},
                                                    JMBG: {TUZILAC_JMBG}

                                                    Punomoćnik tužioca: {ADVOKAT_IME},
                                                    advokat iz {ADVOKAT_ADRESA}

                                                    Tuženi/a (bračni drug): {TUZENI_IME},
                                                    iz {TUZENI_ADRESA},
                                                    JMBG: {TUZENI_JMBG}


              T U Ž B A
              radi razvoda braka
              (porodičnopravni spor)


I. BRAK STRANAKA

Tužilac {TUZILAC_IME} i tuženi/a {TUZENI_IME} zaključili su brak dana {DATUM_BRAKA} pred {MATICNI_URED}, o čemu postoji upis u matičnu knjigu venčanih, izvod broj {BROJ_IZVODA}.
{DECA_SEKCIJA}

II. OKOLNOSTI RASPADA BRAKA

{CINJENICNO_STANJE}


III. RAZLOZI ZA RAZVOD BRAKA

{RAZLOZI_RAZVODA}

Na osnovu navedenih okolnosti, bračna zajednica između tužioca i tuženog/e je ozbiljno i trajno poremećena do mere koja onemogućava njeno dalje trajanje u smislu čl. 41 Porodičnog zakona (Sl. glasnik RS, br. 18/2005, 72/2011, 6/2015).


IV. VRŠENJE RODITELJSKOG PRAVA

{STARATELJSTVO_SEKCIJA}


V. IZDRŽAVANJE

{IZDRZAVANJE_SEKCIJA}


VI. PODELA ZAJEDNIČKE IMOVINE

{IMOVINA_SEKCIJA}


VII. DOKAZNA SREDSTVA

{DOKAZNA_SREDSTVA}


VIII. TUŽBENI ZAHTEV

Na osnovu svega izloženog, predlaže se sudu da donese sledeću

P R E S U D U

1. Razvodi se brak zaključen između {TUZILAC_IME} i {TUZENI_IME};

{PETITUM_STARATELJSTVO}

{PETITUM_IMOVINA}

Tuženi/a se obavezuje da tužiocu naknadi troškove parničnog postupka, u roku od 15 dana.

                                                    Tužilac, odnosno punomoćnik tužioca:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
- Izvod iz matične knjige venčanih
- Izvod iz matične knjige rodjenih za maloletnу decu
- Dokazi o imovinskom stanju
- Punomoćje
{DODATNI_PRILOZI}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.
"""

# ─── ŠABLON 6: Prigovor na platni nalog ──────────────────────────────────────
SABLON_PRIGOVOR_PLATNI_NALOG = """\
{SUD_NAZIV}
{SUD_ADRESA}

PREDMET: {BROJ_PREDMETA}


                                                    Tuženi (podnosilac prigovora): {TUZENI_IME},
                                                    iz {TUZENI_ADRESA},
                                                    JMBG/PIB: {TUZENI_JMBG_PIB}

                                                    Punomoćnik: {ADVOKAT_IME},
                                                    advokat iz {ADVOKAT_ADRESA}

                                                    Tužilac (poverilac): {TUZILAC_IME}


              P R I G O V O R
              na platni nalog

              (rok: 8 dana od dostavljanja — čl. 462 st. 1 ZPP)


I. PLATNI NALOG KOJI SE POBIJA

Platni nalog {SUD_NAZIV} broj {BROJ_PREDMETA} od {DATUM_PLATNOG_NALOGA}, dostavljen tuženom dana {DATUM_DOSTAVLJANJA}, kojim je tuženi obavezan da tužiocu isplati iznos od {IZNOS_PLATNOG_NALOGA} dinara sa troškovima.

Prigovor se podnosi blagovremeno — u zakonskom roku od 8 dana od dana dostavljanja platnog naloga (čl. 462 st. 1 ZPP, Sl. glasnik RS, br. 72/2011).


II. RAZLOZI PRIGOVORA

{RAZLOZI_PRIGOVORA}


III. PRAVNA KVALIFIKACIJA

{PRAVNA_KVALIFIKACIJA}


IV. DOKAZNA SREDSTVA

{DOKAZNA_SREDSTVA}


V. PRIGOVOR

Na osnovu navedenog, tuženi izjavljuje prigovor i predlaže sudu da:

{PRIGOVOR_PREDLOG}

Tužilac se obavezuje da tuženom naknadi troškove postupka po prigovoru.

                                                    Tuženi, odnosno punomoćnik tuženog:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
- Kopija pobijanog platnog naloga
- Dokazi uz prigovor
- Punomoćje
{DODATNI_PRILOZI}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.
"""

# ─── ŠABLON 7: Krivična prijava ──────────────────────────────────────────────
SABLON_KRIVICNA_PRIJAVA = """\
{TUZILAC_NAZIV}
{TUZILAC_ADRESA}


                                                    Prijavljivač: {PRIJAVLJIVAC_IME},
                                                    iz {PRIJAVLJIVAC_ADRESA}

                                                    Punomoćnik: {ADVOKAT_IME},
                                                    advokat iz {ADVOKAT_ADRESA}


              K R I V I Č N A   P R I J A V A

              (podneta na osnovu čl. 280 ZKP, Sl. glasnik RS, br. 72/2011)


I. PRIJAVLJENI

{OKRIVLJENI_IME}, {OKRIVLJENI_ADRESA}
{OKRIVLJENI_JMBG_RED}


II. KRIVIČNO DELO ZA KOJE SE PRIJAVLJUJE

{KZ_CLAN_NAZIV}

(kažnjivo po čl. {KZ_CLAN_BROJ} Krivičnog zakonika, Sl. glasnik RS, br. 85/2005)


III. OPIS KRIVIČNOG DELA — ČINJENIČNO STANJE

{CINJENICNO_STANJE}


IV. PRAVNA KVALIFIKACIJA

{PRAVNA_KVALIFIKACIJA}


V. DOKAZNA SREDSTVA

{DOKAZNA_SREDSTVA}


VI. PREDLOG

Na osnovu izloženog, prijavljivač predlaže {TUZILAC_NAZIV} da:

{PREDLOG_TUZILAC}

                                                    Prijavljivač, odnosno punomoćnik:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
{PRILOG_LISTA}

NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja. Krivična prijava obavezuje tužilaštvo na procesuiranje samo ako postoje osnovi sumnje.
"""

# ─── ŠABLON 8: Predlog za privremenu meru ─────────────────────────────────────
SABLON_PREDLOG_PRIVREMENA_MERA = """\
{SUD_NAZIV}
{SUD_ADRESA}


                                                    Predlagač: {PREDLAGAC_IME},
                                                    iz {PREDLAGAC_ADRESA}

                                                    Punomoćnik predlagača: {ADVOKAT_IME},
                                                    advokat iz {ADVOKAT_ADRESA}

                                                    Protivnik obezbeđenja: {PROTIVNIK_IME},
                                                    {PROTIVNIK_ADRESA}

Vrednost potraživanja: {VREDNOST_POTRAZIVANJA} dinara


              P R E D L O G
              za određivanje privremene mere

              (čl. 283-316 Zakona o izvršenju i obezbeđenju,
               Sl. glasnik RS, br. 106/2015)


I. POTRAŽIVANJE ČIJE SE OBEZBEĐENJE TRAŽI

{POTRAZIVANJE_SEKCIJA}


II. USLOVI ZA ODREĐIVANJE PRIVREMENE MERE

A) Fumus boni iuris — verovatnost potraživanja (čl. 285 ZIO)

{FUMUS_BONI_IURIS}

B) Periculum in mora — opasnost od onemogućavanja izvršenja (čl. 286 ZIO)

{PERICULUM_IN_MORA}


III. PREDLOŽENA PRIVREMENA MERA

{VRSTA_MERE}


IV. PRAVNA OSNOVA

{PRAVNA_OSNOVA}


V. DOKAZNA SREDSTVA

{DOKAZNA_SREDSTVA}


VI. PREDLOG

Na osnovu navedenog, predlagač predlaže {SUD_NAZIV} da donese sledeće

R E Š E N J E

{PREDLOG_RESENJA}

                                                    Predlagač, odnosno punomoćnik:
                                                    ____________________________
                                                    {ADVOKAT_IME}
                                                    {ADVOKAT_ADRESA}

{MESTO}, {DATUM}


Prilozi:
- Dokazi uz predlog (prema listi u tački V)
- Punomoćje
{DODATNI_PRILOZI}

NAPOMENA: Predlog za privremenu meru se podnosi HITNO. Sud odlučuje u roku od 3 dana (čl. 297 ZIO). Uz predlog se može priložiti i ponuda sredstva obezbeđenja (čl. 289 ZIO) radi bržeg usvajanja.
NAPOMENA SISTEMA: Ovaj nacrt je generisan uz pomoć Vindex AI i mora biti pregledan od strane ovlašćenog advokata pre podnošenja sudu.
"""

# ─── Mapa tip → šablon ────────────────────────────────────────────────────────
SABLONI: dict[str, str] = {
    "tuzba_naknada_stete":    SABLON_TUZBA_NAKNADA,
    "zalba_parnicna":         SABLON_ZALBA_PARNICNA,
    "predlog_izvrsenje":      SABLON_PREDLOG_IZVRSENJE,
    "tuzba_radni_spor":       SABLON_TUZBA_RADNI_SPOR,
    "tuzba_razvod":           SABLON_TUZBA_RAZVOD,
    "prigovor_platni_nalog":  SABLON_PRIGOVOR_PLATNI_NALOG,
    "krivicna_prijava":       SABLON_KRIVICNA_PRIJAVA,
    "predlog_privremena_mera":SABLON_PREDLOG_PRIVREMENA_MERA,
}

# ─── Ekstrakcioni promptovi po tipu ──────────────────────────────────────────
EKSTRAKCIONI_PROMPTOVI: dict[str, str] = {

"tuzba_naknada_stete": """\
Ti si pravni asistent koji ekstraktuje ISKLJUČIVO faktičke podatke iz opisa slučaja.
Vrati ČIST JSON objekat — bez komentara, bez markdown blokova, bez ikakvog teksta van JSON-a.

{
  "tuzilac_ime": "Puno ime tužioca (ime i prezime fizičkog lica ili naziv pravnog lica)",
  "tuzilac_adresa": "Ulica, broj, grad — ili prazno ako nije navedeno",
  "tuzilac_jmbg": "13-cifreni JMBG tužioca ako je eksplicitno naveden, inače prazno",
  "tuzeni_ime": "Puno ime/naziv tuženog (fizičko lice, pravno lice ili osiguravajuće društvo sa punim nazivom)",
  "tuzeni_adresa": "Adresa ili sedište tuženog, ili prazno",
  "sud_naziv": "Nadležni sud po sledećem pravilu: ukupna vrednost spora do 3.000.000 RSD → 'Osnovni sud u [grad]'; iznad → 'Viši sud u [grad]'. Grad = mesto prebivališta tužioca ili mesto gde se desio štetni događaj.",
  "sud_adresa": "Adresa suda ili prazno",
  "vrednost_spora": "Samo cifra u dinarima bez simbola i slova — zbir SVIH traženih iznosa naknade. Ako iznosi nisu navedeni, ostavi prazno.",
  "datum_dogadjaja": "Datum štetnog događaja u formatu DD.MM.YYYY — ako nije naveden, ostavi prazno",
  "cinjenicno_stanje_raw": "Kratki opis štetnog događaja direktno iz teksta (3-5 rečenica): ko, šta, kada, gde — bez pravnih kvalifikacija",
  "dokazna_sredstva_raw": "Eksplicitno pomenuti dokazi iz opisa (zapisnici, medicinska dokumentacija, fotografije, svedoci...)",
  "fizicki_bolovi_raw": "Opis fizičkih povreda i bolova koji je naveden u tekstu, ili prazno",
  "iznos_fizicki_bolovi": "Samo cifra u dinarima ako je korisnik eksplicitno naveo željeni iznos za fizičke bolove, inače prazno",
  "strah_raw": "Opis pretrpljenog straha naveden u tekstu, ili prazno",
  "iznos_strah": "Samo cifra u dinarima ako je korisnik eksplicitno naveo iznos za strah, inače prazno",
  "ima_umanjenje": true ili false — true SAMO ako je eksplicitno pomenuto trajno umanjenje opšte životne aktivnosti ili trajni invaliditet,
  "umanjenje_raw": "Opis umanjenja životne aktivnosti iz teksta, ili prazno",
  "iznos_umanjenje": "Samo cifra u dinarima ako je korisnik eksplicitno naveo iznos, inače prazno",
  "ima_naruzenost": true ili false — true SAMO ako su eksplicitno pomenuti trajni ožiljci, deformiteti ili naruženost,
  "naruzenost_raw": "Opis naruženosti iz teksta, ili prazno",
  "iznos_naruzenost": "Samo cifra u dinarima ako je korisnik eksplicitno naveo iznos, inače prazno",
  "advokat_ime": "Puno ime advokata sa titulom ako je naveden, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Grad u kome se podnosi tužba (po pravilu mesto suda)",
  "datum": "Datum podnošenja u formatu: '20. aprila 2026. godine' — ako nije naveden, koristi današnji datum"
}

APSOLUTNO ZABRANJENO:
- Izmišljati ili pretpostavljati podatke koji nisu u tekstu.
- Navoditi iznose koje korisnik nije eksplicitno naznačio.
- Vrednost spora mora biti samo zbir iznosa koje je korisnik naveo — nikad procena.
- JSON vrednosti moraju biti stringovi (osim ima_umanjenje i ima_naruzenost koji su boolean).
""",

"zalba_parnicna": """\
Ti si asistent koji ekstraktuje pravne entitete iz opisa slučaja za žalbu na prvostepenu presudu.
Iz teksta izvuci TAČNO sledeća polja i vrati ČIST JSON objekat — bez komentara, bez markdown blokova.

{
  "zalilac_ime": "Puno ime/naziv žalioca",
  "zalilac_adresa": "Adresa žalioca ili prazno",
  "protivnik_ime": "Puno ime/naziv protivnika žalioca",
  "protivnik_adresa": "Adresa protivnika ili prazno",
  "prvostepeni_sud_naziv": "Naziv prvostepenog suda",
  "prvostepeni_sud_adresa": "Adresa prvostepenog suda ili prazno",
  "drugostepeni_sud_naziv": "Pretpostavljeni drugostepeni sud (Apelacioni/Viši sud u [grad])",
  "drugostepeni_sud_adresa": "Adresa drugostepenog suda ili prazno",
  "broj_predmeta": "Broj predmeta u formatu P. 123/2024 ili slično",
  "datum_presude": "Datum presude u formatu DD.MM.YYYY",
  "datum_dostavljanja": "Datum dostavljanja presude ili prazno",
  "datum_zalbe": "Datum podnošenja žalbe ili danas",
  "izreka_presude_raw": "Šta je izrečeno presudom (kratko)",
  "zalba_razlozi": ["razlog 1", "razlog 2"],
  "obrazlozenje_raw": "Detaljno obrazloženje žalbenih razloga u pravnom stilu",
  "zalba_predlog_raw": "Šta žalilac predlaže da drugostepeni sud uradi",
  "advokat_ime": "Ime advokata ako je navedeno, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Mesto podnošenja",
  "datum": "Datum u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- Ako polje nije pomenuto, ostavi prazno — NE izmišljaj podatke.
- Žalbeni razlozi moraju biti pravno precizni: pogrešno utvrđeno činjenično stanje / pogrešna primena materijalnog prava / bitna povreda odredaba parničnog postupka.
- Ekavica, formalni pravni stil.
""",

"predlog_izvrsenje": """\
Ti si asistent koji ekstraktuje pravne entitete iz opisa slučaja za predlog za izvršenje.
Iz teksta izvuci TAČNO sledeća polja i vrati ČIST JSON objekat — bez komentara, bez markdown blokova.

{
  "trazilac_ime": "Puno ime/naziv tražioca izvršenja",
  "trazilac_adresa": "Adresa tražioca ili prazno",
  "izvrsenik_ime": "Puno ime/naziv izvršenika",
  "izvrsenik_adresa": "Adresa izvršenika ili prazno",
  "izvrsenik_jmbg_pib": "JMBG ili PIB izvršenika ili prazno",
  "mesto_suda": "Grad nadležnog suda",
  "sud_adresa": "Adresa suda ili prazno",
  "vrsta_izvrsne_isprave": "pravosnažna i izvršna presuda / rešenje / verodostojna isprava / itd.",
  "naziv_isprave": "Naziv isprave",
  "broj_isprave": "Broj isprave",
  "datum_isprave": "Datum isprave u formatu DD.MM.YYYY",
  "sadrzaj_obaveze_raw": "Šta je izvršenik obavezan da ispuni",
  "iznos_glavnice": "Iznos u dinarima",
  "kamata_stopa": "Stopa zatezne kamate (npr. zakonska)",
  "datum_pocetka_kamate": "Datum od kojeg teče kamata",
  "troskovi_postupka": "Iznos troškova prethodnog postupka ili 0",
  "ukupan_iznos": "Ukupan iznos potraživanja",
  "sredstvo_izvrsenja": "Opis sredstva: zaplemba zarade / zaplemba računa / zaplemba pokretnih stvari / hipoteka",
  "predmet_izvrsenja": "Konkretni predmet izvršenja (račun broj, nepokretnost, vozilo...)",
  "advokat_ime": "Ime advokata ako je navedeno, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Mesto podnošenja",
  "datum": "Datum u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- Ako polje nije pomenuto, ostavi prazno — NE izmišljaj podatke.
- Izvršna isprava mora biti navedena precizno — bez nje predlog nije validan.
- Ekavica, formalni pravni stil.
""",

"tuzba_radni_spor": """\
Ti si asistent koji ekstraktuje pravne entitete iz opisa radnog spora.
Iz teksta izvuci TAČNO sledeća polja i vrati ČIST JSON — bez markdown, bez komentara.

{
  "tuzilac_ime": "Puno ime radnika-tužioca",
  "tuzilac_adresa": "Adresa tužioca ili prazno",
  "tuzilac_jmbg": "JMBG tužioca ako je naveden, inače prazno",
  "tuzeni_ime": "Naziv poslodavca-tuženog (puno pravno ime firme ili preduzetnika)",
  "tuzeni_adresa": "Sedište poslodavca ili prazno",
  "tuzeni_pib": "PIB ili MB poslodavca ako je naveden, inače prazno",
  "sud_naziv": "Nadležni sud: radni sporovi — uvek 'Osnovni sud u [grad]' (čl. 22 ZPP). Grad = mesto sedišta poslodavca ili mesto rada.",
  "sud_adresa": "Adresa suda ili prazno",
  "vrednost_spora": "Cifra u dinarima — zbir potraživanja (zaostale zarade, naknada štete). Ako iznos nije naveden: prazno.",
  "datum_otkaza": "Datum donošenja odluke o otkazu u formatu DD.MM.YYYY, ili prazno",
  "datum_saznanja": "Datum kada je radnik primio odluku (rok 60 dana za tužbu teče od tada) u formatu DD.MM.YYYY, ili prazno",
  "vrsta_spora": "Tip: 'poništaj otkaza' / 'isplata zarade' / 'diskriminacija' / 'mobing' / 'naknada štete' / 'promena ugovora'",
  "osnov_otkaza_raw": "Razlog koji je poslodavac naveo u odluci o otkazu, iz teksta ili prazno",
  "radni_staz": "Period rada kod ovog poslodavca (npr. '5 godina') ako je naveden, inače prazno",
  "iznos_zarade": "Mesečni neto iznos zarade u dinarima ako je naveden, inače prazno",
  "cinjenicno_stanje_raw": "Opis spornih dogadjaja direktno iz teksta (3-5 rečenica)",
  "dokazna_sredstva_raw": "Eksplicitno pomenuti dokazi iz teksta",
  "advokat_ime": "Ime advokata ako je naveden, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Grad podnošenja tužbe",
  "datum": "Datum u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- Rok za tužbu zbog nezakonitog otkaza je 60 dana od saznanja (čl. 195 ZR) — ne navoditi u JSON.
- NE izmišljati podatke koji nisu eksplicitno u tekstu.
- Ekavica, formalni stil.
""",

"tuzba_razvod": """\
Ti si asistent koji ekstraktuje entitete iz opisa bračnog spora za razvod.
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "tuzilac_ime": "Puno ime bračnog druga koji tuži",
  "tuzilac_adresa": "Adresa tužioca ili prazno",
  "tuzilac_jmbg": "JMBG tužioca ako je naveden, inače prazno",
  "tuzeni_ime": "Puno ime drugog bračnog druga",
  "tuzeni_adresa": "Adresa tuženog ili prazno",
  "tuzeni_jmbg": "JMBG tuženog ako je naveden, inače prazno",
  "sud_naziv": "Nadležni sud: uvek 'Osnovni sud u [grad]' (čl. 263 PZ). Grad = zajedničko poslednje boravište ili boravište tužioca.",
  "sud_adresa": "Adresa suda ili prazno",
  "datum_braka": "Datum zaključenja braka u formatu DD.MM.YYYY",
  "maticni_ured": "Naziv matičnog ureda gde je brak zaključen, ili 'nadležnog matičnog ureda'",
  "broj_izvoda": "Broj izvoda iz knjige venčanih ako je naveden, inače prazno",
  "ima_dece": true ili false — true ako postoji maloletna deca iz ovog braka,
  "deca_raw": "Imena i datumi rodjenja maloletne dece ako su navedeni, inače prazno",
  "starateljstvo_predlog": "Ko traži staratelstvo i nad kojom decom iz teksta, ili prazno",
  "alimentacija_iznos": "Mesečni iznos alimentacije u dinarima ako je naveden, inače prazno",
  "ima_zajednicke_imovine": true ili false — true ako je pomenuta zajednička imovina za podelu,
  "imovina_raw": "Opis zajedničke imovine za podelu ako je naveden, inače prazno",
  "cinjenicno_stanje_raw": "Opis razloga raspada braka direktno iz teksta (3-5 rečenica)",
  "dokazna_sredstva_raw": "Eksplicitno pomenuti dokazi iz teksta",
  "advokat_ime": "Ime advokata ako je naveden, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Grad podnošenja tužbe",
  "datum": "Datum u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- NE izmišljati podatke koji nisu eksplicitno u tekstu.
- Ekavica, formalni stil.
""",

"prigovor_platni_nalog": """\
Ti si asistent koji ekstraktuje entitete za prigovor na platni nalog.
ROK JE 8 DANA OD DOSTAVLJANJA (čl. 462 st. 1 ZPP) — ovo je kritičan zakonski rok.
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "tuzeni_ime": "Puno ime/naziv dužnika (podnosioca prigovora)",
  "tuzeni_adresa": "Adresa dužnika ili prazno",
  "tuzeni_jmbg_pib": "JMBG ili PIB dužnika ako je naveden, inače prazno",
  "tuzilac_ime": "Puno ime/naziv poverioca",
  "tuzilac_adresa": "Adresa poverioca ili prazno",
  "sud_naziv": "Naziv suda koji je doneo platni nalog",
  "sud_adresa": "Adresa suda ili prazno",
  "broj_predmeta": "Broj predmeta platnog naloga (npr. Pl. 123/2024)",
  "datum_platnog_naloga": "Datum donošenja platnog naloga u formatu DD.MM.YYYY",
  "datum_dostavljanja": "Datum dostavljanja platnog naloga dužniku u formatu DD.MM.YYYY",
  "iznos_platnog_naloga": "Iznos koji je platnim nalogom određen (samo cifra u dinarima)",
  "razlog_prigovora": "Vrsta prigovora: 'nepostojanje duga' / 'zastarelost' / 'pogrešan iznos' / 'neuredna dostava' / 'nedostajuća dokumentacija' / 'prigovor nadležnosti'",
  "cinjenicno_stanje_raw": "Opis razloga prigovora direktno iz teksta",
  "dokazna_sredstva_raw": "Eksplicitno pomenuti dokazi iz teksta",
  "advokat_ime": "Ime advokata ako je naveden, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Grad podnošenja prigovora",
  "datum": "Datum u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- NE izmišljati podatke koji nisu eksplicitno u tekstu.
- Ekavica, formalni stil.
""",

"krivicna_prijava": """\
Ti si asistent koji ekstraktuje entitete iz opisa za krivičnu prijavu.
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "prijavljivac_ime": "Puno ime/naziv podnosioca prijave (fizičko ili pravno lice)",
  "prijavljivac_adresa": "Adresa prijavljivača ili prazno",
  "okrivljeni_ime": "Puno ime/naziv prijavljenog (fizičko ili pravno lice)",
  "okrivljeni_adresa": "Adresa prijavljenog ili prazno",
  "okrivljeni_jmbg": "JMBG prijavljenog ako je naveden, inače prazno",
  "tuzilac_naziv": "Naziv nadležnog javnog tužilaštva: 'Osnovno javno tužilaštvo u [grad]' za većinu krivičnih dela; 'Više javno tužilaštvo u [grad]' za dela kažnjiva iznad 8 god. zatvora ili specijalna; 'Tužilaštvo za organizovani kriminal' ako se pominje organizovani kriminal.",
  "tuzilac_adresa": "Adresa tužilaštva ili prazno",
  "kz_clan_naziv": "Naziv krivičnog dela (npr. 'Prevara' / 'Teška krađa' / 'Falsifikovanje isprave' / 'Ugrožavanje bezbednosti' / 'Zlostavljanje i mučenje')",
  "kz_clan_broj": "Broj člana KZ koji reguliše prijavljeno krivično delo (npr. '208' za prevaru, '204' za tešku krađu, '355' za falsifikovanje isprave)",
  "datum_dogadjaja": "Datum krivičnog dela u formatu DD.MM.YYYY ili opis perioda",
  "mesto_dogadjaja": "Mesto gde se krivično delo desilo",
  "cinjenicno_stanje_raw": "Opis krivičnog dela direktno iz teksta: ko je šta uradio, kada, gde, na koji način (3-5 rečenica)",
  "dokazna_sredstva_raw": "Eksplicitno pomenuti dokazi iz teksta (svedoci, dokumentacija, snimci, veštaci...)",
  "steta_raw": "Opis nastale štete ili posledica krivičnog dela, ako je naveden",
  "advokat_ime": "Ime advokata ako je naveden, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Grad podnošenja prijave",
  "datum": "Datum u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- NE izmišljati podatke koji nisu eksplicitno u tekstu.
- Krivično delo identifikovati ISKLJUČIVO iz opisa — ne pretpostavljati.
- Ekavica, formalni stil.
""",

"predlog_privremena_mera": """\
Ti si asistent koji ekstraktuje entitete za predlog privremene mere.
Privremena mera zahteva 2 uslova: fumus boni iuris (verovatnost potraživanja) + periculum in mora (opasnost od ometanja).
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "predlagac_ime": "Puno ime/naziv predlagača (poverilac čije se potraživanje obezbeđuje)",
  "predlagac_adresa": "Adresa predlagača ili prazno",
  "protivnik_ime": "Puno ime/naziv protivnika obezbeđenja (dužnik)",
  "protivnik_adresa": "Adresa protivnika ili prazno",
  "sud_naziv": "Nadležni sud: 'Osnovno/Viši sud u [grad]' — isti kao sud pred kojim teče ili će se pokrenuti parnica",
  "sud_adresa": "Adresa suda ili prazno",
  "vrednost_potrazivanja": "Cifra potraživanja čije se obezbeđenje traži (u dinarima), ili prazno",
  "vrsta_mere": "Vrsta predložene mere: 'zabrana otuđenja i opterećenja nepokretnosti' / 'privremena zaplena pokretnih stvari' / 'zabrana raspolaganja bankovnim računom' / 'privremena zabrana isplate iz osiguranja' / 'upis zabeležbe u katastar'",
  "osnov_potrazivanja": "Pravni osnov potraživanja: ugovor / šteta / restitucija / naknada zarade itd.",
  "fumus_raw": "Dokazi koji verovatno potvrđuju potraživanje — šta prijavljivač ima kao dokaz",
  "periculum_raw": "Razlozi hitnosti — zašto postoji opasnost da će dužnik osujeti izvršenje (prodaja imovine, bekstvo, rasipanje...)",
  "cinjenicno_stanje_raw": "Opis spora i razloga za meru direktno iz teksta",
  "dokazna_sredstva_raw": "Eksplicitno pomenuti dokazi iz teksta",
  "advokat_ime": "Ime advokata ako je naveden, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Grad podnošenja predloga",
  "datum": "Datum u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- NE izmišljati podatke koji nisu eksplicitno u tekstu.
- Ekavica, formalni stil.
""",
}

# ─── Promptovi za pravno obogaćivanje (RAG kontekst → šablon placeholder) ───
OBOGACIVANJE_PROMPTOVI: dict[str, str] = {

"tuzba_naknada_stete": """\
Ti si iskusni srpski advokat koji piše tužbu radi naknade nematerijalne štete pred srpskim redovnim sudom.
Na osnovu dostavljenih podataka (JSON entiteti) i zakonskog konteksta (RAG), napiši sadržaj sekcija.
Stil pisanja: procesno-pravni, jasan, koncizan, bez književnih ulepšavanja. Svaka rečenica mora imati pravni smisao.
Vrati ČIST JSON — bez komentara, bez markdown blokova, bez objašnjenja van JSON-a.

{
  "cinjenicno_stanje": "Pravno formulisano činjenično stanje u 3-5 paragrafa. Struktura: (1) identifikacija stranaka i odnos između njih; (2) opis štetnog događaja — datum, mesto, mehanizam nastanka, uzrok; (3) nastanak i vrsta povrede/štete sa uzročno-posledičnom vezom; (4) preduzete mere lečenja i njihov ishod; (5) trajanje i posledice. Fraze: 'Dana [datum], na [mestu], [štetnik] je [radnjom] prouzrokovao [posledicu].' — NIKAD ne pisati 'navodno' ili 'kako tužilac tvrdi'. Ekavica, formalni pravni stil.",
  "fizicki_bolovi_opis": "Pravni opis fizičkih bolova u 2-3 paragrafa: (1) vrsta i lokalizacija anatomskih povreda utvrđenih medicinskom dokumentacijom; (2) intenzitet bola prema standardnoj VAS skali ili opisno (intenzivan/umeren/blag), trajanje akutne faze i tok lečenja (hospitalizacija, operacije, rehabilitacija); (3) zaostale tegobe i funkcionalna ograničenja. OBAVEZNO: referišaj na medicinsku dokumentaciju ('što se utvrđuje iz nalaza medicinskih organa priloženih uz tužbu'). ZABRANJENO: kvalifikovati povredu kao 'laku', 'tešku' ili 'naročito tešku telesnu povredu' — to je isključivo nadležnost suda.",
  "strah_opis": "Pravni opis pretrpljenog straha u 2 paragrafa: (1) primarni strah — intenzitet i trajanje straha neposredno u trenutku i neposredno nakon štetnog događaja, sa opisom okolnosti koje su izazvale strah (neposredna opasnost po život, gubitak svesti, itd.); (2) sekundarni strah — strah tokom dijagnostičkih procedura, operativnih zahvata, straho od komplikacija i od trajnih posledica. Referišaj na psihijatrijsku ili psihološku dokumentaciju ako postoji. Koristiti formulaciju: 'Tužilac je, usled opisanog štetnog dogadjaja, pretrpeo primarni strah [opis], kao i sekundarni strah [opis].'",
  "umanjenje_sekcija": "Ako ima_umanjenje=true: napiši CELU sekciju počevši sa tačno ovim tekstom: '3. Duševni bolovi zbog umanjenja opšte životne aktivnosti\\n\\nTužilac je, kao trajna posledica zadobijenih povreda, pretrpeo umanjenje opšte životne aktivnosti. [Opis: koji aspekti svakodnevnog života su pogođeni — rad, kretanje, sport, socijalni život, porodični život; da li je umanjenje delimično ili potpuno; koji procenat umanjenja je utvrđen od strane lekara ili veštaka.] Navedeno umanjenje je [trajno/privremeno] i direktna je posledica predmetnog štetnog dogadjaja, što se utvrđuje iz priložene medicinske dokumentacije.' Ako ima_umanjenje=false: prazno string.",
  "naruzenost_sekcija": "Ako ima_naruzenost=true: napiši CELU sekciju počevši sa: '4. Duševni bolovi zbog naruženosti\\n\\nUsled zadobijenih povreda, tužilac je pretrpeo trajnu naruženost. [Opis: lokalizacija, dimenzije i morfologija vidljivih trajnih promena (ožiljci, deformiteti, amputacije); vidljivost u svakodnevnom životu; psihološki uticaj na samopouzdanje i socijalne odnose.] Naruženost je vidljiva i predstavlja trajnu estetsku i psihičku smetnju, što se utvrđuje iz fotografija i medicinske dokumentacije priložene uz tužbu.' Ako ima_naruzenost=false: prazno string.",
  "pravna_kvalifikacija": "Pravna analiza u 2-3 paragrafa sa eksplicitnim pozivanjem na zakone: (1) osnov odštetne odgovornosti — ZOO čl. 154 st. 1 (opšta deliktna odgovornost), čl. 155 (uzročna veza), uz navođenje posebnog zakona iz RAG konteksta ako postoji (ZOSOV za saobraćajne nezgode, ZOR za radne nezgode); (2) pravna osnova za naknadu nematerijalne štete — ZOO čl. 200 st. 1 (fizički bolovi), čl. 200 st. 1 (duševni bolovi zbog umanjenja životne aktivnosti), čl. 200 st. 1 (naruženost), čl. 200 st. 1 (strah); (3) nadležnost i mesna nadležnost suda prema ZPP čl. 22 (opšta mesna nadležnost) ili čl. 41 (posebna mesna nadležnost za štete). KRITIČNO: navesti ISKLJUČIVO zakone koji su prisutni u RAG kontekstu ili su opštepoznati (ZOO, ZPP) — ne izmišljati Sl. glasnik brojeve.",
  "dokazna_sredstva": "Numerisana lista dokaznih sredstava. Uvodni tekst: 'Tužilac predlaže izvođenje sledećih dokaza:'. Format svake stavke: '[redni broj]. [Vrsta dokaza] — [svrha dokazivanja]'. Standardni dokazi za ovu vrstu spora: 1. Medicinska dokumentacija (otpusna lista, RTG snimci, nalaz specijaliste) — radi dokazivanja vrste, obima i trajanja povreda; 2. Policijski/MUP zapisnik o uviđaju — radi dokazivanja mehanizma nastanka štete; 3. Svedoci [ili 'koje tužilac naknadno predloži'] — radi dokazivanja okolnosti štetnog dogadjaja; 4. Veštak medicinske struke — radi utvrđivanja uzročno-posledične veze i procene nematerijalne štete; 5. Fotografije — radi dokazivanja materijalnog i estetskog stanja. Dodaj i dokaze koji su eksplicitno pomenuti u opisu slučaja.",
  "petitum_umanjenje": "Ako ima_umanjenje=true: tačno ovaj tekst: '3. na ime duševnih bolova zbog umanjenja opšte životne aktivnosti iznos od [IZNOS UMANJENJE — POPUNITI] dinara;\\n'. Ako ima_umanjenje=false: prazno string.",
  "petitum_naruzenost": "Ako ima_naruzenost=true: tačno ovaj tekst: '4. na ime duševnih bolova zbog naruženosti iznos od [IZNOS NARUŽENOST — POPUNITI] dinara;\\n'. Ako ima_naruzenost=false: prazno string.",
  "opcioni_petitum": "Ako postoje osnovi: predlog za privremenu meru (čl. 448 ZPP) ili predlog za osiguranje dokaza pre pokretanja postupka. U suprotnom: prazno string."
}

APSOLUTNO ZABRANJENO:
- Kvalifikovati povredu kao 'laku', 'tešku' ili 'naročito tešku telesnu povredu' (isključivo nadležnost suda).
- Navoditi iznose nematerijalne štete koje korisnik nije eksplicitno naveo — ostavi placeholder [IZNOS — POPUNITI].
- Izmišljati brojeve Sl. glasnika ili zakone koji nisu u RAG kontekstu.
- Pisati u prvom licu ('tužilac kaže') — pisati u trećem licu procesnog stila ('tužilac je pretrpeo').
- Koristiti razgovorni ili književni stil.
""",

"zalba_parnicna": """\
Ti si pravni pisac koji popunjava žalbu na prvostepenu presudu.
Na osnovu dostavljenih podataka (JSON) i relevantnog zakonskog konteksta (RAG), napiši sadržaj za 2 sekcije.
Vrati ČIST JSON — bez komentara, bez markdown.

{
  "zalba_razlozi_lista": "Numerisana lista žalbenih razloga sa referencama na ZPP (čl. 374) i konkretnim razlozima",
  "obrazlozenje_zalbe": "Detaljno pravno obrazloženje sa referencama na zakone iz konteksta (3-5 paragrafa)",
  "zalba_predlog": "Konkretan žalbeni predlog — preinačenje u korist žalioca ili ukidanje i vraćanje"
}

PRAVILA:
- Žalbeni razlozi iz ZPP čl. 374: 1. bitna povreda odredaba parničnog postupka, 2. pogrešno ili nepotpuno utvrđeno činjenično stanje, 3. pogrešna primena materijalnog prava.
- Navedeni razlozi moraju odgovarati opisanom slučaju — ne koristiti sve razloge ako nisu primenljivi.
- Ekavica, formalni pravni stil.
""",

"predlog_izvrsenje": """\
Ti si pravni pisac koji popunjava predlog za izvršenje.
Na osnovu dostavljenih podataka (JSON) i relevantnog zakonskog konteksta (RAG), napiši sadržaj za 2 sekcije.
Vrati ČIST JSON — bez komentara, bez markdown.

{
  "ostala_potrazivanja": "Eventualna dodatna potraživanja (troškovi izvršnog postupka, naknada za zastupanje) ili prazno",
  "sredstvo_izvrsenja_kratko": "Kratko sredstvo: 'zaplembe zarade izvršenika' / 'zaplembe novčanih sredstava na računu' / itd.",
  "dodatni_prilozi": "Lista eventualnih dodatnih priloga ili prazno"
}

PRAVILA:
- Sredstvo izvršenja: zaplemba zarade (ZIO čl. 189), zaplemba računa (ZIO čl. 183), zaplemba pokretnih (ZIO čl. 195).
- Referišaj na ZIO (Sl. glasnik RS, br. 106/2015) samo ako je u kontekstu.
- Ekavica, formalni pravni stil.
""",

"tuzba_radni_spor": """\
Ti si iskusni srpski advokat koji piše tužbu u radnom sporu pred redovnim sudom.
Na osnovu dostavljenih podataka (JSON entiteti) i zakonskog konteksta (RAG), napiši sadržaj sekcija.
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "stranke_i_radni_odnos": "Uvodni paragraf: identifikacija stranaka i radnopravni odnos — od kada, na kojim poslovima, vrsta ugovora o radu, period trajanja radnog odnosa. Koristiti formulu: 'Tužilac [ime] zaposlen je kod tuženog [naziv] od [datum] na poslovima [opis], na osnovu Ugovora o radu br. [broj] od [datum].'",
  "cinjenicno_stanje": "Pravno formulisano činjenično stanje u 3-4 paragrafa: (1) tok radnog odnosa — relevantni dogadjaji koji prethode sporu; (2) pobijana odluka — datum donošenja, obrazloženje poslodavca iz pobijanog akta; (3) nezakonitost — formalni ili materijalni nedostaci odluke; (4) posledice za tužioca.",
  "razlozi_tuzbe": "Konkretni razlozi nezakonitosti sa zakonskim referencama: (1) procesni nedostaci — upozorenje pre otkaza (čl. 180 ZR), rok za izjašnjavanje, pravo na odbranu; (2) materijalni razlozi — da li zakonski osnov postoji (čl. 109, 110, 111 ZR za redovni otkaz; čl. 116 ZR za vanredni otkaz); (3) diskriminacija/mobing ako je relevantno (ZZD čl. 18, ZR čl. 7); (4) proceduralne povrede u postupku donošenja odluke.",
  "pravna_kvalifikacija": "Pravna analiza u 2-3 paragrafa: (1) zakonski osnov ZR (Sl. glasnik RS, br. 24/2005 sa izmenama — preciziraj iz RAG konteksta); (2) primenjeni član koji reguliše sporni otkaz; (3) VKS praksa iz RAG konteksta ako postoji. KRITIČNO: navoditi ISKLJUČIVO zakone iz RAG konteksta ili opštepoznate (ZR, ZPP, ZZD).",
  "dokazna_sredstva": "Numerisana lista: 1. Ugovor o radu — radi dokazivanja zasnivanja radnog odnosa; 2. Pobijana odluka o otkazu — predmet osporavanja; 3. Upozorenje pre otkaza (ili konstatacija da nije dostavljeno); 4. Potvrda o zaradi i obračun zaostale zarade; 5. Izjave svedoka — radi dokazivanja okolnosti; 6. Ostali dokazi iz opisa slučaja.",
  "tuzbeni_zahtev": "Konkretan tužbeni zahtev: (1) poništaj pobijane odluke o prestanku radnog odnosa kao nezakonite; (2) vraćanje na rad na iste ili odgovarajuće poslove (alternativno: isplata otpremnine po ZR čl. 158-160); (3) isplata zarada za period nezakonitog prestanka sa zakonskom kamatom; (4) naknada štete ako je relevantno; (5) troškovi postupka. Konkretni iznosi ili placeholder [IZNOS — POPUNITI]."
}

ZABRANA: Ne navoditi iznose koje korisnik nije naveo. Ekavica, formalni pravni stil.
""",

"tuzba_razvod": """\
Ti si iskusni srpski advokat koji piše tužbu za razvod braka.
Na osnovu dostavljenih podataka (JSON entiteti) i zakonskog konteksta (RAG), napiši sadržaj sekcija.
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "cinjenicno_stanje": "Pravno formulisan opis raspada braka u 3-4 paragrafa: (1) okolnosti zajedničkog života — period, mesto boravka; (2) početak poremećenih odnosa — uzroci opisani u tekstu bez pripisivanja krivice; (3) trenutno stanje — faktička separacija, prestanak bračne zajednice; (4) neuspeli pokušaji pomirenja ako su pomenuti. Referisati na PZ čl. 41.",
  "razlozi_razvoda": "Pravno formulisani razlozi u 2 paragrafa: (1) ozbiljnost i trajnost poremećaja bračnih odnosa (PZ čl. 41 — ne zahteva se krivica); (2) konkretni uzroci iz teksta; (3) konstatacija da brak ne može ispunjavati svoju funkciju.",
  "starateljstvo_sekcija": "Ako ima_dece=true: sekcija o vršenju roditeljskog prava — ko predlaže staratelstvo nad kojom decom (PZ čl. 77-80), predlog za regulisanje kontakta sa roditeljem koji ne vrši staratelstvo, predlog alimentacije sa iznosom ili placeholder-om (PZ čl. 160-164). Ako ima_dece=false: prazno string.",
  "izdrzavanje_sekcija": "Predlog za izdržavanje bivšeg bračnog druga ako je relevantno (PZ čl. 151-159), sa iznosima ili placeholder-om [IZNOS — POPUNITI]. Ako nije pomenuto: prazno string.",
  "imovina_sekcija": "Ako ima_zajednicke_imovine=true: predlog za podelu zajedničke imovine stečene u braku (PZ čl. 171-178) sa opisom imovine iz teksta. Ako nije relevantno: prazno string.",
  "dokazna_sredstva": "Numerisana lista: 1. Izvod iz matične knjige venčanih — dokaz braka; 2. Izvodi iz MKR za maloletnu decu; 3. Potvrda o boravištu stranaka; 4. Dokazi o imovinom stanju (izvod iz ZK, saobraćajna dozvola, bankarski izvodi) ako je relevantno; 5. Ostali dokazi iz teksta.",
  "petitum_starateljstvo": "Ako ima_dece=true: numerisani petitum — 2. Maloletno/a dete/ca [IME] poverava se na čuvanje, vaspitanje i vršenje roditeljskog prava [tužiocu/tuženom]; 3. Obavezuje se [drugi roditelj] da na ime alimentacije plaća iznos od [IZNOS — POPUNITI] mesečno. Ako ima_dece=false: prazno string.",
  "petitum_imovina": "Ako ima_zajednicke_imovine=true: numerisani petitum za podelu zajedničke imovine sa opisom. Ako nema: prazno string."
}

ZABRANA: Ekavica, formalni pravni stil. NE navoditi iznose koje korisnik nije naveo.
""",

"prigovor_platni_nalog": """\
Ti si iskusni srpski advokat koji piše prigovor na platni nalog.
Na osnovu dostavljenih podataka (JSON entiteti) i zakonskog konteksta (RAG), napiši sadržaj sekcija.
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "razlozi_prigovora": "Konkretni razlozi prigovora u 2-4 paragrafa: (1) meritorna osnovanost — da li dug postoji, da li je u navedenom iznosu, koji deo je sporan; (2) procesni prigovori — zastarelost (ZOO čl. 371 i dalje: opšti rok 10 god., ugovorni 3 god.), neuredna dostava platnog naloga (ZPP čl. 136-143), nedostatak verodostojne isprave; (3) prigovor mesne nadležnosti ako je relevantno (ZPP čl. 22-41); (4) prigovor stvarne nadležnosti. Svaki razlog sa referencom na zakon iz RAG konteksta ili opštepoznate zakone.",
  "pravna_kvalifikacija": "Pravna analiza u 2 paragrafa: (1) zakonski osnov — ZPP čl. 453-462 (platni nalog); (2) primena materijalnog prava na sporni dug — ZOO ili posebni zakon iz RAG konteksta; (3) VKS praksa iz RAG konteksta ako postoji. KRITIČNO: navoditi ISKLJUČIVO zakone iz RAG konteksta ili opštepoznate.",
  "dokazna_sredstva": "Numerisana lista dokaza kojima se potkrepljuju razlozi prigovora: 1. Kopija platnog naloga — predmet pobijanja; 2. Dokazi o plaćanju / izmirivanju duga (uplatnice, izvodi računa); 3. Korespondencija stranaka — radi dokazivanja spornih okolnosti; 4. Ugovor na osnovu kojeg se tvrdi dug — radi analize osnovanosti; 5. Ostali dokazi iz teksta.",
  "prigovor_predlog": "Konkretan predlog u 2-3 tačke: 1. Usvoji prigovor i ukine platni nalog broj [broj] u celini / u delu koji prelazi iznos od [IZNOS — POPUNITI]; 2. Predmet uputi u parnični postupak radi utvrdjivanja osnovanosti potraživanja; 3. Tužilac se obaveže da tuženom naknadi troškove postupka po prigovoru."
}

KRITIČNO: Zakonski rok 8 dana od dostavljanja (čl. 462 st. 1 ZPP) mora biti istaknut.
Ekavica, formalni pravni stil.
""",

"krivicna_prijava": """\
Ti si iskusni srpski advokat koji piše krivičnu prijavu.
Na osnovu dostavljenih podataka (JSON entiteti) i zakonskog konteksta (RAG), napiši sadržaj sekcija.
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "cinjenicno_stanje": "Pravno formulisan opis krivičnog dela u 3-4 paragrafa: (1) identifikacija stranaka i odnos; (2) tok događaja — datum, mesto, radnje prijavljenog; (3) nastala šteta/posledica za prijavljivača; (4) dokazi kojima prijavljivač raspolaže. Stil: hronološki, precizna faktika, bez pravnih kvalifikacija — te idu u sekciju IV.",
  "pravna_kvalifikacija": "Pravna analiza u 2 paragrafa: (1) elementi bića krivičnog dela — koji elementi (radnja, posledica, krivica) su ostvareni; (2) odredba KZ — čl. [broj] i zaprećena kazna; (3) eventualni otežavajući ili olakšavajući elementi; (4) procesni osnov — ZKP čl. 280. KRITIČNO: navoditi ISKLJUČIVO odredbe iz RAG konteksta ili opštepoznate (KZ, ZKP). Ne izmišljati Sl. glasnik.",
  "dokazna_sredstva": "Numerisana lista dokaznih sredstava: 1. [Vrsta] — radi dokazivanja [elementa]; 2. [Vrsta] — radi dokazivanja [elementa]; itd. Standardni dokazi: pisana dokumentacija, elektronska prepiska, svedoci, video/foto snimci, veštačenja. Dodati dokaze pomenute u tekstu.",
  "predlog_tuzilac": "Konkretan predlog tužilaštvu u 2-3 tačke: 1. Preduzme istražne radnje utvrdjivanja okolnosti krivičnog dela; 2. Prikupi dokaze navedene u tački V; 3. Ako postoje osnovi sumnje da je prijavljeni učinio krivično delo — podigne optužnicu. Referisati na ZKP čl. 280 st. 2 i čl. 284.",
  "prilog_lista": "Numerisana lista dokumenata koji se prilog uz prijavu: 1. [dokument]; 2. [dokument]. Ako nema dokaza uz prijavu: '1. Izjava prijavljivača'"
}

ZABRANA: Ne navoditi konkretne visine kazni osim ako su eksplicitno u KZ odredbi. Ekavica, formalni pravni stil.
""",

"predlog_privremena_mera": """\
Ti si iskusni srpski advokat koji piše predlog za privremenu meru prema ZIO.
Na osnovu dostavljenih podataka (JSON entiteti) i zakonskog konteksta (RAG), napiši sadržaj sekcija.
Dva OBAVEZNA uslova: (A) fumus boni iuris — verovatnost potraživanja (ZIO čl. 285), (B) periculum in mora — opasnost od onemogućavanja izvršenja (ZIO čl. 286).
Vrati ČIST JSON — bez markdown, bez komentara.

{
  "potrazivanje_sekcija": "Opis potraživanja koje se obezbeđuje: (1) pravni osnov (ugovor/šteta/druga osnova); (2) iznos potraživanja u dinarima ili opis nenovčanog potraživanja; (3) dospelost — da li je potraživanje dospelo ili tek treba da dospe; (4) konstatacija da parnica nije okončana ili tek treba da se pokrene (privremena mera može se tražiti pre i tokom parnice per čl. 291 ZIO).",
  "fumus_boni_iuris": "Dokazi koji čine verovatnim potraživanje (ZIO čl. 285): (1) navesti konkretne dokaze iz teksta kojima predlagač raspolaže — ugovor, fakture, prepiska, sudska presuda; (2) kratka pravna analiza — zašto ovi dokazi čine potraživanje verovatnim; (3) konstatacija: 'Priloženim dokazima predlagač je učinio verovatnim postojanje potraživanja...' Referisati na ZIO čl. 285.",
  "periculum_in_mora": "Razlozi hitnosti — zašto bez mere izvršenje ne bi bilo moguće ili bi bilo otežano (ZIO čl. 286): (1) konkretne okolnosti koje ukazuju na opasnost — protivnik rasprodaje imovinu, prenosi na treća lica, sprema bekstvo, ima evidenciju neplaćanja; (2) ili: vrednost spora je takva da bi budući izvršni postupak bio nemoguć bez obezbeđenja; (3) konstatacija: 'Postoji ozbiljna opasnost da će protivnik...'. Referisati na ZIO čl. 286.",
  "vrsta_mere": "Precizno definisana privremena mera jednim od zakonskih oblika: (1) 'zabrana otuđenja i opterećenja nepokretnosti [opis], uz upis zabeležbe u katastar nepokretnosti (čl. 291 ZIO, čl. 295 ZIO)'; (2) 'privremena zaplena pokretnih stvari [opis]'; (3) 'zabrana raspolaganja novčanim sredstvima na računu br. [broj] kod [banka] do iznosa od [iznos] dinara'; (4) druge mere. Mera mora biti SRAZMERNA potraživanju.",
  "pravna_osnova": "Zakonska osnova u 2 paragrafa: (1) ZIO čl. 283-295 — opšte odredbe o privremenim merama; (2) ZIO čl. 285 (fumus) i čl. 286 (periculum) — konkretni uslovi; (3) ZIO čl. 291 — rok trajanja mere; (4) eventualno: ZPP čl. 304 (ako je parnica već pokrenuta). Navesti Sl. glasnik RS 106/2015 samo ako je u RAG kontekstu.",
  "dokazna_sredstva": "Numerisana lista dokaza priloženih uz predlog: 1. [dokument] — radi dokazivanja [elementa]; 2. ... Obavezno: dokaz osnova potraživanja + dokaz periculum-a (prepiska, procena imovine, izjava svedoka).",
  "predlog_resenja": "Konkretan sadržaj predloženog rešenja u 2-4 tačke: 1. Određuje se privremena mera: [opis mere] prema protivniku obezbeđenja [ime]; 2. Mera važi do pravosnažnog okončanja parničnog postupka, odnosno do pravnosnažnosti i izvršnosti presude (čl. 291 ZIO); 3. Predlagač je dužan da u roku od [30 dana od dostave rešenja] pokrene parnicu. Alternativno: predlagač nudi sredstvo obezbeđenja u smislu čl. 289 ZIO."
}

KRITIČNO: Oba uslova (fumus + periculum) moraju biti jasno obrazložena. Mera mora biti srazmerna potraživanju.
Ekavica, formalni pravni stil.
""",
}


# ─── Funkcija za popunjavanje šablona ────────────────────────────────────────
def popuni_sablon(tip: str, entiteti: dict, obogacivanje: dict,
                  vks_analiza: str = "") -> str:
    """
    Spaja ekstrahovane entitete i AI-obogaćene sekcije u finalni podnesak.
    Sve nepoznate {PLACEHOLDER} vrednosti ostaju vidljive kao [POPUNITI].
    vks_analiza — opcioni tekst VIKI analize koji se dodaje na kraj tužbe.
    """
    sablon = SABLONI.get(tip, "")
    if not sablon:
        return "Nepoznat tip podneska."

    merged = {}

    if tip == "tuzba_naknada_stete":
        # Proceni iznos_fizički_bolovi iz entiteta ili ostavi placeholder
        iznos_fiz  = entiteti.get("iznos_fizicki_bolovi", "") or "[IZNOS FIZIČKI BOLOVI — POPUNITI]"
        iznos_str  = entiteti.get("iznos_strah", "") or "[IZNOS STRAH — POPUNITI]"

        # Kondicionalne sekcije specifikacije i petituma
        umanjenje_sek = obogacivanje.get("umanjenje_sekcija", "")
        naruzenost_sek = obogacivanje.get("naruzenost_sekcija", "")
        petitum_uma = obogacivanje.get("petitum_umanjenje", "")
        petitum_nar = obogacivanje.get("petitum_naruzenost", "")

        merged = {
            "SUD_NAZIV":              entiteti.get("sud_naziv", "[SUD — POPUNITI]"),
            "SUD_ADRESA":             entiteti.get("sud_adresa", ""),
            "TUZILAC_IME":            entiteti.get("tuzilac_ime", "[TUŽILAC — POPUNITI]"),
            "TUZILAC_ADRESA":         entiteti.get("tuzilac_adresa", "[ADRESA TUŽIOCA — POPUNITI]"),
            "TUZILAC_JMBG":           entiteti.get("tuzilac_jmbg", "[JMBG — POPUNITI]"),
            "TUZENI_IME":             entiteti.get("tuzeni_ime", "[TUŽENI — POPUNITI]"),
            "TUZENI_ADRESA":          entiteti.get("tuzeni_adresa", "[ADRESA TUŽENOG — POPUNITI]"),
            "VREDNOST_SPORA":         entiteti.get("vrednost_spora", "[VREDNOST SPORA — POPUNITI]"),
            "CINJENICNO_STANJE":      obogacivanje.get("cinjenicno_stanje", entiteti.get("cinjenicno_stanje_raw", "[ČINJENIČNO STANJE — POPUNITI]")),
            "FIZICKI_BOLOVI_OPIS":    obogacivanje.get("fizicki_bolovi_opis", entiteti.get("fizicki_bolovi_raw", "[OPIS FIZIČKIH BOLOVA — POPUNITI]")),
            "STRAH_OPIS":             obogacivanje.get("strah_opis", entiteti.get("strah_raw", "[OPIS STRAHA — POPUNITI]")),
            "UMANJENJE_SEKCIJA":      ("\n" + umanjenje_sek) if umanjenje_sek else "",
            "NARUZENOST_SEKCIJA":     ("\n" + naruzenost_sek) if naruzenost_sek else "",
            "PRAVNA_KVALIFIKACIJA":   obogacivanje.get("pravna_kvalifikacija", "[PRAVNA KVALIFIKACIJA — POPUNITI]"),
            "DOKAZNA_SREDSTVA":       obogacivanje.get("dokazna_sredstva", entiteti.get("dokazna_sredstva_raw", "[DOKAZNA SREDSTVA — POPUNITI]")),
            "IZNOS_FIZICKI_BOLOVI":   iznos_fiz,
            "IZNOS_STRAH":            iznos_str,
            "PETITUM_UMANJENJE":      petitum_uma,
            "PETITUM_NARUZENOST":     petitum_nar,
            "OPCIONI_PETITUM":        obogacivanje.get("opcioni_petitum", ""),
            "ADVOKAT_IME":            entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":         entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "MESTO":                  entiteti.get("mesto", "[MESTO — POPUNITI]"),
            "DATUM":                  entiteti.get("datum", "[DATUM — POPUNITI]"),
            "PRILOZI":                "1. Medicinska dokumentacija\n2. Fotografije sa mesta događaja\n3. Policijski/MUP zapisnik\n4. Punomoćje\n[DODATNI PRILOZI — POPUNITI]",
            "VIKI_ANALIZA":           vks_analiza,
        }

    elif tip == "zalba_parnicna":
        razlozi_raw = entiteti.get("zalba_razlozi", [])
        razlozi_lista = "\n".join(f"{i+1}. {r}" for i, r in enumerate(razlozi_raw)) if razlozi_raw else "[RAZLOZI — POPUNITI]"
        merged = {
            "DRUGOSTEPENI_SUD_NAZIV":  entiteti.get("drugostepeni_sud_naziv", "[DRUGOSTEPENI SUD — POPUNITI]"),
            "DRUGOSTEPENI_SUD_ADRESA": entiteti.get("drugostepeni_sud_adresa", ""),
            "PRVOSTEPENI_SUD_NAZIV":   entiteti.get("prvostepeni_sud_naziv", "[PRVOSTEPENI SUD — POPUNITI]"),
            "PRVOSTEPENI_SUD_ADRESA":  entiteti.get("prvostepeni_sud_adresa", ""),
            "ZALILAC_IME":             entiteti.get("zalilac_ime", "[ŽALILAC — POPUNITI]"),
            "ZALILAC_ADRESA":          entiteti.get("zalilac_adresa", "[ADRESA — POPUNITI]"),
            "PROTIVNIK_IME":           entiteti.get("protivnik_ime", "[PROTIVNIK — POPUNITI]"),
            "PROTIVNIK_ADRESA":        entiteti.get("protivnik_adresa", "[ADRESA — POPUNITI]"),
            "BROJ_PREDMETA":           entiteti.get("broj_predmeta", "[BROJ — POPUNITI]"),
            "DATUM_PRESUDE":           entiteti.get("datum_presude", "[DATUM — POPUNITI]"),
            "DATUM_DOSTAVLJANJA":      entiteti.get("datum_dostavljanja", "[DATUM — POPUNITI]"),
            "DATUM_ZALBE":             entiteti.get("datum_zalbe", "[DATUM — POPUNITI]"),
            "IZREKA_PRESUDE":          entiteti.get("izreka_presude_raw", "[IZREKA — POPUNITI]"),
            "ZALBA_RAZLOZI_LISTA":     obogacivanje.get("zalba_razlozi_lista", razlozi_lista),
            "OBRAZLOZENJE_ZALBE":      obogacivanje.get("obrazlozenje_zalbe", entiteti.get("obrazlozenje_raw", "[OBRAZLOŽENJE — POPUNITI]")),
            "ZALBA_PREDLOG":           obogacivanje.get("zalba_predlog", entiteti.get("zalba_predlog_raw", "[PREDLOG — POPUNITI]")),
            "ADVOKAT_IME":             entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":          entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "MESTO":                   entiteti.get("mesto", "[MESTO]"),
            "DATUM":                   entiteti.get("datum", "[DATUM]"),
            "DODATNI_PRILOZI":         "[DODATNI PRILOZI — POPUNITI]",
        }

    elif tip == "predlog_izvrsenje":
        merged = {
            "MESTO_SUDA":              entiteti.get("mesto_suda", "[MESTO SUDA — POPUNITI]"),
            "SUD_ADRESA":              entiteti.get("sud_adresa", ""),
            "TRAZILAC_IME":            entiteti.get("trazilac_ime", "[TRAŽILAC — POPUNITI]"),
            "TRAZILAC_ADRESA":         entiteti.get("trazilac_adresa", "[ADRESA — POPUNITI]"),
            "IZVRSENIK_IME":           entiteti.get("izvrsenik_ime", "[IZVRŠENIK — POPUNITI]"),
            "IZVRSENIK_ADRESA":        entiteti.get("izvrsenik_adresa", "[ADRESA — POPUNITI]"),
            "IZVRSENIK_JMBG_PIB":      entiteti.get("izvrsenik_jmbg_pib", ""),
            "ADVOKAT_IME":             entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":          entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "VRSTA_IZVRSNE_ISPRAVE":   entiteti.get("vrsta_izvrsne_isprave", "[VRSTA — POPUNITI]"),
            "NAZIV_ISPRAVE":           entiteti.get("naziv_isprave", "[NAZIV — POPUNITI]"),
            "BROJ_ISPRAVE":            entiteti.get("broj_isprave", "[BROJ — POPUNITI]"),
            "DATUM_ISPRAVE":           entiteti.get("datum_isprave", "[DATUM — POPUNITI]"),
            "SADRZAJ_OBAVEZE":         entiteti.get("sadrzaj_obaveze_raw", "[OBAVEZA — POPUNITI]"),
            "IZNOS_GLAVNICE":          entiteti.get("iznos_glavnice", "[IZNOS — POPUNITI]"),
            "KAMATA_STOPA":            entiteti.get("kamata_stopa", "zakonska"),
            "DATUM_POCETKA_KAMATE":    entiteti.get("datum_pocetka_kamate", "[DATUM — POPUNITI]"),
            "TROSKOVI_POSTUPKA":       entiteti.get("troskovi_postupka", "0"),
            "UKUPAN_IZNOS":            entiteti.get("ukupan_iznos", "[UKUPNO — POPUNITI]"),
            "SREDSTVO_IZVRSENJA":      entiteti.get("sredstvo_izvrsenja", "[SREDSTVO — POPUNITI]"),
            "PREDMET_IZVRSENJA":       entiteti.get("predmet_izvrsenja", "[PREDMET — POPUNITI]"),
            "OSTALA_POTRAZIVANJA":     obogacivanje.get("ostala_potrazivanja", ""),
            "SREDSTVO_IZVRSENJA_KRATKO": obogacivanje.get("sredstvo_izvrsenja_kratko", entiteti.get("sredstvo_izvrsenja", "[SREDSTVO]")),
            "MESTO":                   entiteti.get("mesto", "[MESTO]"),
            "DATUM":                   entiteti.get("datum", "[DATUM]"),
            "DODATNI_PRILOZI":         obogacivanje.get("dodatni_prilozi", "[DODATNI PRILOZI — POPUNITI]"),
        }

    elif tip == "tuzba_radni_spor":
        merged = {
            "SUD_NAZIV":             entiteti.get("sud_naziv", "[SUD — POPUNITI]"),
            "SUD_ADRESA":            entiteti.get("sud_adresa", ""),
            "TUZILAC_IME":           entiteti.get("tuzilac_ime", "[TUŽILAC — POPUNITI]"),
            "TUZILAC_ADRESA":        entiteti.get("tuzilac_adresa", "[ADRESA — POPUNITI]"),
            "TUZILAC_JMBG":          entiteti.get("tuzilac_jmbg", "[JMBG — POPUNITI]"),
            "TUZENI_IME":            entiteti.get("tuzeni_ime", "[TUŽENI — POPUNITI]"),
            "TUZENI_ADRESA":         entiteti.get("tuzeni_adresa", "[ADRESA — POPUNITI]"),
            "TUZENI_PIB":            entiteti.get("tuzeni_pib", ""),
            "VREDNOST_SPORA":        entiteti.get("vrednost_spora", "[VREDNOST SPORA — POPUNITI]"),
            "STRANKE_I_RADNI_ODNOS": obogacivanje.get("stranke_i_radni_odnos", "[RADNI ODNOS — POPUNITI]"),
            "CINJENICNO_STANJE":     obogacivanje.get("cinjenicno_stanje", entiteti.get("cinjenicno_stanje_raw", "[STANJE — POPUNITI]")),
            "RAZLOZI_TUZBE":         obogacivanje.get("razlozi_tuzbe", "[RAZLOZI — POPUNITI]"),
            "PRAVNA_KVALIFIKACIJA":  obogacivanje.get("pravna_kvalifikacija", "[PRAVNA KVALIFIKACIJA — POPUNITI]"),
            "DOKAZNA_SREDSTVA":      obogacivanje.get("dokazna_sredstva", entiteti.get("dokazna_sredstva_raw", "[DOKAZI — POPUNITI]")),
            "TUZBENI_ZAHTEV":        obogacivanje.get("tuzbeni_zahtev", "[ZAHTEV — POPUNITI]"),
            "ADVOKAT_IME":           entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":        entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "MESTO":                 entiteti.get("mesto", "[MESTO]"),
            "DATUM":                 entiteti.get("datum", "[DATUM]"),
            "DODATNI_PRILOZI":       "[DODATNI PRILOZI — POPUNITI]",
            "VIKI_ANALIZA":          vks_analiza,
        }

    elif tip == "tuzba_razvod":
        merged = {
            "SUD_NAZIV":              entiteti.get("sud_naziv", "[SUD — POPUNITI]"),
            "SUD_ADRESA":             entiteti.get("sud_adresa", ""),
            "TUZILAC_IME":            entiteti.get("tuzilac_ime", "[TUŽILAC — POPUNITI]"),
            "TUZILAC_ADRESA":         entiteti.get("tuzilac_adresa", "[ADRESA — POPUNITI]"),
            "TUZILAC_JMBG":           entiteti.get("tuzilac_jmbg", "[JMBG — POPUNITI]"),
            "TUZENI_IME":             entiteti.get("tuzeni_ime", "[TUŽENI — POPUNITI]"),
            "TUZENI_ADRESA":          entiteti.get("tuzeni_adresa", "[ADRESA — POPUNITI]"),
            "TUZENI_JMBG":            entiteti.get("tuzeni_jmbg", "[JMBG — POPUNITI]"),
            "DATUM_BRAKA":            entiteti.get("datum_braka", "[DATUM BRAKA — POPUNITI]"),
            "MATICNI_URED":           entiteti.get("maticni_ured", "nadležnog matičnog ureda"),
            "BROJ_IZVODA":            entiteti.get("broj_izvoda", "[BROJ — POPUNITI]"),
            "DECA_SEKCIJA":           ("\nIz ovog braka potiče: " + entiteti.get("deca_raw", "")) if entiteti.get("ima_dece") else "",
            "CINJENICNO_STANJE":      obogacivanje.get("cinjenicno_stanje", entiteti.get("cinjenicno_stanje_raw", "[STANJE — POPUNITI]")),
            "RAZLOZI_RAZVODA":        obogacivanje.get("razlozi_razvoda", "[RAZLOZI — POPUNITI]"),
            "STARATELJSTVO_SEKCIJA":  obogacivanje.get("starateljstvo_sekcija", "[STARATELSTVO — POPUNITI ako ima dece]"),
            "IZDRZAVANJE_SEKCIJA":    obogacivanje.get("izdrzavanje_sekcija", ""),
            "IMOVINA_SEKCIJA":        obogacivanje.get("imovina_sekcija", ""),
            "DOKAZNA_SREDSTVA":       obogacivanje.get("dokazna_sredstva", entiteti.get("dokazna_sredstva_raw", "[DOKAZI — POPUNITI]")),
            "PETITUM_STARATELJSTVO":  obogacivanje.get("petitum_starateljstvo", ""),
            "PETITUM_IMOVINA":        obogacivanje.get("petitum_imovina", ""),
            "ADVOKAT_IME":            entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":         entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "MESTO":                  entiteti.get("mesto", "[MESTO]"),
            "DATUM":                  entiteti.get("datum", "[DATUM]"),
            "DODATNI_PRILOZI":        "[DODATNI PRILOZI — POPUNITI]",
        }

    elif tip == "prigovor_platni_nalog":
        merged = {
            "SUD_NAZIV":             entiteti.get("sud_naziv", "[SUD — POPUNITI]"),
            "SUD_ADRESA":            entiteti.get("sud_adresa", ""),
            "BROJ_PREDMETA":         entiteti.get("broj_predmeta", "[BROJ — POPUNITI]"),
            "TUZENI_IME":            entiteti.get("tuzeni_ime", "[DUŽNIK — POPUNITI]"),
            "TUZENI_ADRESA":         entiteti.get("tuzeni_adresa", "[ADRESA — POPUNITI]"),
            "TUZENI_JMBG_PIB":       entiteti.get("tuzeni_jmbg_pib", ""),
            "ADVOKAT_IME":           entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":        entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "TUZILAC_IME":           entiteti.get("tuzilac_ime", "[POVERILAC — POPUNITI]"),
            "DATUM_PLATNOG_NALOGA":  entiteti.get("datum_platnog_naloga", "[DATUM — POPUNITI]"),
            "DATUM_DOSTAVLJANJA":    entiteti.get("datum_dostavljanja", "[DATUM — POPUNITI]"),
            "IZNOS_PLATNOG_NALOGA":  entiteti.get("iznos_platnog_naloga", "[IZNOS — POPUNITI]"),
            "RAZLOZI_PRIGOVORA":     obogacivanje.get("razlozi_prigovora", entiteti.get("cinjenicno_stanje_raw", "[RAZLOZI — POPUNITI]")),
            "PRAVNA_KVALIFIKACIJA":  obogacivanje.get("pravna_kvalifikacija", "[PRAVNA KVALIFIKACIJA — POPUNITI]"),
            "DOKAZNA_SREDSTVA":      obogacivanje.get("dokazna_sredstva", entiteti.get("dokazna_sredstva_raw", "[DOKAZI — POPUNITI]")),
            "PRIGOVOR_PREDLOG":      obogacivanje.get("prigovor_predlog", "[PREDLOG — POPUNITI]"),
            "MESTO":                 entiteti.get("mesto", "[MESTO]"),
            "DATUM":                 entiteti.get("datum", "[DATUM]"),
            "DODATNI_PRILOZI":       "[DODATNI PRILOZI — POPUNITI]",
        }

    elif tip == "krivicna_prijava":
        jmbg = entiteti.get("okrivljeni_jmbg", "")
        merged = {
            "TUZILAC_NAZIV":     entiteti.get("tuzilac_naziv", "[JAVNO TUŽILAŠTVO — POPUNITI]"),
            "TUZILAC_ADRESA":    entiteti.get("tuzilac_adresa", ""),
            "PRIJAVLJIVAC_IME":  entiteti.get("prijavljivac_ime", "[PRIJAVLJIVAČ — POPUNITI]"),
            "PRIJAVLJIVAC_ADRESA": entiteti.get("prijavljivac_adresa", "[ADRESA — POPUNITI]"),
            "ADVOKAT_IME":       entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":    entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "OKRIVLJENI_IME":    entiteti.get("okrivljeni_ime", "[PRIJAVLJENI — POPUNITI]"),
            "OKRIVLJENI_ADRESA": entiteti.get("okrivljeni_adresa", "[ADRESA — POPUNITI]"),
            "OKRIVLJENI_JMBG_RED": f"JMBG: {jmbg}" if jmbg else "",
            "KZ_CLAN_NAZIV":     entiteti.get("kz_clan_naziv", "[KRIVIČNO DELO — POPUNITI]"),
            "KZ_CLAN_BROJ":      entiteti.get("kz_clan_broj", "[ČLAN — POPUNITI]"),
            "CINJENICNO_STANJE": obogacivanje.get("cinjenicno_stanje", entiteti.get("cinjenicno_stanje_raw", "[STANJE — POPUNITI]")),
            "PRAVNA_KVALIFIKACIJA": obogacivanje.get("pravna_kvalifikacija", "[PRAVNA KVALIFIKACIJA — POPUNITI]"),
            "DOKAZNA_SREDSTVA":  obogacivanje.get("dokazna_sredstva", entiteti.get("dokazna_sredstva_raw", "[DOKAZI — POPUNITI]")),
            "PREDLOG_TUZILAC":   obogacivanje.get("predlog_tuzilac", "[PREDLOG — POPUNITI]"),
            "PRILOG_LISTA":      obogacivanje.get("prilog_lista", "1. Izjava prijavljivača"),
            "MESTO":             entiteti.get("mesto", "[MESTO]"),
            "DATUM":             entiteti.get("datum", "[DATUM]"),
        }

    elif tip == "predlog_privremena_mera":
        merged = {
            "SUD_NAZIV":              entiteti.get("sud_naziv", "[SUD — POPUNITI]"),
            "SUD_ADRESA":             entiteti.get("sud_adresa", ""),
            "PREDLAGAC_IME":          entiteti.get("predlagac_ime", "[PREDLAGAČ — POPUNITI]"),
            "PREDLAGAC_ADRESA":       entiteti.get("predlagac_adresa", "[ADRESA — POPUNITI]"),
            "ADVOKAT_IME":            entiteti.get("advokat_ime", "[IME ADVOKATA — POPUNITI]"),
            "ADVOKAT_ADRESA":         entiteti.get("advokat_adresa", "[ADRESA ADVOKATA — POPUNITI]"),
            "PROTIVNIK_IME":          entiteti.get("protivnik_ime", "[PROTIVNIK — POPUNITI]"),
            "PROTIVNIK_ADRESA":       entiteti.get("protivnik_adresa", "[ADRESA — POPUNITI]"),
            "VREDNOST_POTRAZIVANJA":  entiteti.get("vrednost_potrazivanja", "[VREDNOST — POPUNITI]"),
            "POTRAZIVANJE_SEKCIJA":   obogacivanje.get("potrazivanje_sekcija", entiteti.get("cinjenicno_stanje_raw", "[POTRAŽIVANJE — POPUNITI]")),
            "FUMUS_BONI_IURIS":       obogacivanje.get("fumus_boni_iuris", entiteti.get("fumus_raw", "[FUMUS BONI IURIS — POPUNITI]")),
            "PERICULUM_IN_MORA":      obogacivanje.get("periculum_in_mora", entiteti.get("periculum_raw", "[PERICULUM IN MORA — POPUNITI]")),
            "VRSTA_MERE":             obogacivanje.get("vrsta_mere", entiteti.get("vrsta_mere", "[MERA — POPUNITI]")),
            "PRAVNA_OSNOVA":          obogacivanje.get("pravna_osnova", "[PRAVNA OSNOVA — POPUNITI]"),
            "DOKAZNA_SREDSTVA":       obogacivanje.get("dokazna_sredstva", entiteti.get("dokazna_sredstva_raw", "[DOKAZI — POPUNITI]")),
            "PREDLOG_RESENJA":        obogacivanje.get("predlog_resenja", "[PREDLOG — POPUNITI]"),
            "MESTO":                  entiteti.get("mesto", "[MESTO]"),
            "DATUM":                  entiteti.get("datum", "[DATUM]"),
            "DODATNI_PRILOZI":        "[DODATNI PRILOZI — POPUNITI]",
        }

    # Popuni šablon — nepoznati placeholderi ostaju [POPUNITI]
    tekst = sablon
    for kljuc, vrednost in merged.items():
        tekst = tekst.replace("{" + kljuc + "}", vrednost or "")

    return tekst
