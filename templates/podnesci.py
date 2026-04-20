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
    "tuzba_naknada_stete":  "Tužba za naknadu štete",
    "zalba_parnicna":       "Žalba na prvostepenu presudu (parnični postupak)",
    "predlog_izvrsenje":    "Predlog za izvršenje",
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
"""

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

# ─── Mapa tip → šablon ────────────────────────────────────────────────────────
SABLONI: dict[str, str] = {
    "tuzba_naknada_stete": SABLON_TUZBA_NAKNADA,
    "zalba_parnicna":      SABLON_ZALBA_PARNICNA,
    "predlog_izvrsenje":   SABLON_PREDLOG_IZVRSENJE,
}

# ─── Ekstrakcioni promptovi po tipu ──────────────────────────────────────────
EKSTRAKCIONI_PROMPTOVI: dict[str, str] = {

"tuzba_naknada_stete": """\
Ti si asistent koji ekstraktuje pravne entitete iz opisa slučaja za tužbu radi naknade nematerijalne štete.
Iz teksta izvuci TAČNO sledeća polja i vrati ČIST JSON objekat — bez komentara, bez markdown blokova.

{
  "tuzilac_ime": "Puno ime tužioca",
  "tuzilac_adresa": "Adresa tužioca ili prazno",
  "tuzilac_jmbg": "JMBG tužioca ako je navedeno, inače prazno",
  "tuzeni_ime": "Puno ime/naziv tuženog (fizičko lice ili osiguravajuće društvo)",
  "tuzeni_adresa": "Adresa/sedište tuženog ili prazno",
  "sud_naziv": "Nadležni sud: za štete do 3.000.000 RSD — Osnovni sud, iznad — Viši sud u [grad]",
  "sud_adresa": "Adresa suda ili prazno",
  "vrednost_spora": "Ukupan zbir svih traženih iznosa u dinarima",
  "datum_dogadjaja": "Datum štetnog događaja u formatu DD.MM.YYYY",
  "cinjenicno_stanje_raw": "Sažet opis štetnog događaja u pravnom stilu (2-4 rečenice): ko, šta, kada, gde, uzrok",
  "dokazna_sredstva_raw": "Lista dokaza koji su pomenuti u opisu (zapisnici, nalaz lekara, fotografije...)",
  "fizicki_bolovi_raw": "Opis fizičkih povreda i bolova ako je navedeno, inače prazno",
  "iznos_fizicki_bolovi": "Traženi iznos za fizičke bolove u dinarima, ili prazno",
  "strah_raw": "Opis pretrpljenog straha (primarni/sekundarni) ako je navedeno, inače prazno",
  "iznos_strah": "Traženi iznos za strah u dinarima, ili prazno",
  "ima_umanjenje": "true ako je navedeno trajno smanjenje životnih aktivnosti ili trajni invaliditet, inače false",
  "umanjenje_raw": "Opis umanjenja opšte životne aktivnosti ako postoji, inače prazno",
  "iznos_umanjenje": "Traženi iznos za umanjenje životne aktivnosti u dinarima, ili prazno",
  "ima_naruzenost": "true ako su navedeni trajni ožiljci ili naruženost, inače false",
  "naruzenost_raw": "Opis naruženosti/ožiljaka ako postoji, inače prazno",
  "iznos_naruzenost": "Traženi iznos za naruženost u dinarima, ili prazno",
  "advokat_ime": "Ime advokata ako je navedeno, inače prazno",
  "advokat_adresa": "Adresa advokata ako je navedena, inače prazno",
  "mesto": "Mesto podnošenja tužbe",
  "datum": "Datum podnošenja u formatu [dan]. [mesec u slovima] [godina]. godine"
}

PRAVILA:
- Ako polje nije pomenuto, ostavi prazno string ili false — NIKAD ne izmišljaj podatke.
- Sud: za nematerijalne štete iz saobraćajnih nezgoda nadležan je Osnovni sud po mestu prebivališta tužioca.
- Vrednost spora = zbir svih iznosa nematerijalne štete. Ako iznosi nisu precizni, proceni na osnovu opisa.
- Ekavica, formalni pravni stil.
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
}

# ─── Promptovi za pravno obogaćivanje (RAG kontekst → šablon placeholder) ───
OBOGACIVANJE_PROMPTOVI: dict[str, str] = {

"tuzba_naknada_stete": """\
Ti si pravni pisac koji popunjava tužbu radi naknade nematerijalne štete pred srpskim sudom.
Na osnovu dostavljenih podataka (JSON entiteti) i zakonskog konteksta (RAG), napiši sadržaj sekcija.
Vrati ČIST JSON — bez komentara, bez markdown blokova.

{
  "cinjenicno_stanje": "Pravno formulisano činjenično stanje (3-5 paragrafa): ko je štetnik, kada i gde se desio događaj, mehanizam nastanka povrede, uzročno-posledična veza. Koristi formalne fraze i ekavicu.",
  "fizicki_bolovi_opis": "Opis fizičkih bolova: vrsta povreda, intenzitet (jak/srednji/blag), trajanje akutne faze, tok lečenja, zaostale tegobe. Referišaj na medicinsku dokumentaciju. NIKAD ne kvalifikuj povredu kao 'laku/tešku telesnu povredu' — to je isključivo sud.",
  "strah_opis": "Opis pretrpljenog straha: primarni strah (u trenutku događaja — intenzitet, trajanje) i sekundarni strah (tokom lečenja, operacija, mogućih komplikacija). Referišaj na psihijatrijsku/psihološku dokumentaciju ako postoji.",
  "umanjenje_sekcija": "Ako ima_umanjenje=true: napiši celu sekciju '3. Duševni bolovi zbog umanjenja opšte životne aktivnosti\\n\\n[opis: koji procenat invaliditeta, koje aktivnosti su pogođene, da li je trajno]. Inače: prazno string.",
  "naruzenost_sekcija": "Ako ima_naruzenost=true: napiši celu sekciju '4. Duševni bolovi zbog naruženosti\\n\\n[opis: lokacija, veličina i vidljivost ožiljaka, psihološki uticaj]. Inače: prazno string.",
  "pravna_kvalifikacija": "Pravna analiza: ZOO čl. 154 (osnov odgovornosti), čl. 155 (uzročna veza), čl. 200 (nematerijalna šteta) + odredbe iz RAG konteksta. KRITIČNO: ZOO je lex generalis — primenjuje se supsidijarno uz posebne zakone (ZOSOV za saobraćaj). Navedeni zakonski osnov mora biti iz dostavljenog konteksta.",
  "dokazna_sredstva": "Numerisana lista dokaznih sredstava na osnovu pomenutih dokaza + standardni dokazi za ovu vrstu spora (nalaz lekara, fotografije, svedoci, veštak medicinske struke)",
  "petitum_umanjenje": "Ako ima_umanjenje=true: '3. na ime duševnih bolova zbog umanjenja opšte životne aktivnosti iznos od [IZNOS UMANJENJE — POPUNITI] dinara;\\n'. Inače: prazno string.",
  "petitum_naruzenost": "Ako ima_naruzenost=true: '4. na ime duševnih bolova zbog naruženosti iznos od [IZNOS NARUŽENOST — POPUNITI] dinara;\\n'. Inače: prazno string.",
  "opcioni_petitum": "Eventualni dodatni zahtevi (privremena mera, osiguranje dokaza) ili prazno string"
}

KRITIČNA PRAVILA:
- NIKAD ne kvalifikuj telesnu povredu kao 'laku', 'tešku' ili 'naročito tešku' — to je isključivo sud.
- Iznos nematerijalne štete navodi se samo ako je korisnik eksplicitno naznačio željeni iznos — inače ostavi placeholder.
- Koristi ISKLJUČIVO zakone koji se pojavljuju u RAG kontekstu — ne izmišljaj brojeve Sl. glasnika.
- Ekavica, formalni pravni stil, latinski termini (in dubio pro reo, res iudicata) samo gde je uobičajeno.
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
}


# ─── Funkcija za popunjavanje šablona ────────────────────────────────────────
def popuni_sablon(tip: str, entiteti: dict, obogacivanje: dict) -> str:
    """
    Spaja ekstrahovane entitete i AI-obogaćene sekcije u finalni podnesak.
    Sve nepoznate {PLACEHOLDER} vrednosti ostaju vidljive kao [POPUNITI].
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

    # Popuni šablon — nepoznati placeholderi ostaju [POPUNITI]
    tekst = sablon
    for kljuc, vrednost in merged.items():
        tekst = tekst.replace("{" + kljuc + "}", vrednost or "")

    return tekst
