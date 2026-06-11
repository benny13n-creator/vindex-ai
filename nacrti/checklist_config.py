# -*- coding: utf-8 -*-
"""
Konfiguracija obaveznih elemenata po tipu podneska.

Svaki tip ima listu elemenata sa:
  - naziv          : kratko ime elementa (prikazuje se korisniku)
  - pitanje        : šta tražiti u unetim činjenicama
  - kljucne_reci   : lista reči/fraza čije prisustvo signalizira pokrivenost (lowercase)
  - kriticnost     : "visoka" | "srednja" | "niska"
  - razlog         : objašnjenje zašto je element važan ako nedostaje
"""

from typing import TypedDict


class ChecklistElement(TypedDict):
    naziv: str
    pitanje: str
    kljucne_reci: list[str]
    kriticnost: str   # "visoka" | "srednja" | "niska"
    razlog: str


class TipConfig(TypedDict):
    naziv: str
    vrsta_spora: str
    elementi: list[ChecklistElement]


# ─── Konfiguracija tipova ────────────────────────────────────────────────────

CHECKLIST: dict[str, TipConfig] = {

    "tuzba_naknada_stete": {
        "naziv": "Tužba za naknadu štete",
        "vrsta_spora": "obligacioni",
        "elementi": [
            {
                "naziv": "Identitet tužioca i tuženog",
                "pitanje": "Da li su navedeni puni nazivi/imena stranaka?",
                "kljucne_reci": ["tužilac", "tuženi", "stranka", "ime", "naziv", "jmbg", "pib", "mb"],
                "kriticnost": "visoka",
                "razlog": "Tužba bez identiteta stranaka nije procesno valjana (čl. 98 ZPP).",
            },
            {
                "naziv": "Opis štetnog događaja i datum",
                "pitanje": "Da li su opisani okolnosti i datum nastanka štete?",
                "kljucne_reci": ["datum", "dana", "godine", "dogodilo", "nastupila", "kada", "šteta nastala"],
                "kriticnost": "visoka",
                "razlog": "Bez datuma nastanka štete nije moguće proveriti zastarelost ni izračunati kamatu.",
            },
            {
                "naziv": "Vrsta i visina štete",
                "pitanje": "Da li je navedena konkretna visina tražene naknade (iznos u dinarima)?",
                "kljucne_reci": ["dinara", "rsd", "eur", "iznos", "vrednost", "visina", "tražim naknadu", "potraživanje"],
                "kriticnost": "visoka",
                "razlog": "Bez vrednosti spora sud ne može određivati nadležnost ni taksirati podnesak.",
            },
            {
                "naziv": "Uzročna veza",
                "pitanje": "Da li je opisana veza između radnje/propusta tuženog i nastale štete?",
                "kljucne_reci": ["usled", "zbog", "prouzrokovao", "uzrok", "posledica", "odgovoran", "krivicom"],
                "kriticnost": "visoka",
                "razlog": "Uzročna veza je uslov odgovornosti za štetu (čl. 154 ZOO).",
            },
            {
                "naziv": "Pravni osnov potraživanja",
                "pitanje": "Da li je naveden pravni osnov (zakon, ugovor, odgovornost)?",
                "kljucne_reci": ["zakon", "član", "ugovor", "odgovornost", "obaveza", "dužan", "zoo", "zr"],
                "kriticnost": "srednja",
                "razlog": "Pravni osnov se može izvesti iz činjenica, ali eksplicitno navođenje ubrzava postupak.",
            },
            {
                "naziv": "Zakonska zatezna kamata",
                "pitanje": "Da li je tražena zakonska zatezna kamata od datuma nastanka štete?",
                "kljucne_reci": ["kamata", "zatezna", "kamatu", "od dana", "zakonska kamatna stopa"],
                "kriticnost": "srednja",
                "razlog": "Kamata počinje teći od dana nastanka štete (čl. 186 ZOO) — propuštanje umanjuje naknadu.",
            },
            {
                "naziv": "Troškovi postupka",
                "pitanje": "Da li je stavljen predlog za troškove postupka?",
                "kljucne_reci": ["troškovi", "sudska taksa", "naknada troškova", "parničnih troškova"],
                "kriticnost": "srednja",
                "razlog": "Troškovi se ne dosudaju po službenoj dužnosti — moraju biti izričito traženi.",
            },
            {
                "naziv": "Dokazi",
                "pitanje": "Da li su navedeni konkretni dokazni predlozi (dokumenta, svedoci, veštaci)?",
                "kljucne_reci": ["dokaz", "prilaže", "svedok", "veštak", "medicinska", "nalaz", "fotografi", "video", "izveštaj"],
                "kriticnost": "srednja",
                "razlog": "Bez dokaznih predloga tužba slabi procesno — sud može odbiti izvođenje dokaza koji nisu predloženi.",
            },
        ],
    },

    "tuzba_radni_spor": {
        "naziv": "Tužba u radnom sporu",
        "vrsta_spora": "radni",
        "elementi": [
            {
                "naziv": "Identitet stranaka",
                "pitanje": "Da li su navedeni radnik (ime, JMBG) i poslodavac (naziv, PIB)?",
                "kljucne_reci": ["radnik", "zaposleni", "poslodavac", "ime", "naziv", "jmbg", "pib"],
                "kriticnost": "visoka",
                "razlog": "Procesna pretpostavka — identitet stranaka obavezan po čl. 98 ZPP.",
            },
            {
                "naziv": "Datum zasnivanja radnog odnosa",
                "pitanje": "Da li je naveden datum kada je radni odnos zasnovan?",
                "kljucne_reci": ["zaposlio", "zasnivanje", "radni odnos", "od dana", "ugovorom", "ugovor o radu"],
                "kriticnost": "visoka",
                "razlog": "Potrebno za utvrđivanje staža i primenu relevantnih propisa ZR.",
            },
            {
                "naziv": "Akt o prestanku/kršenju prava",
                "pitanje": "Da li je naveden konkretan akt poslodavca (rešenje o otkazu, odluka)?",
                "kljucne_reci": ["rešenje", "odluka", "otkaz", "otpuštanje", "diskriminaci", "disciplinski", "akt"],
                "kriticnost": "visoka",
                "razlog": "Tužba mora precizno napasti konkretan akt — inače je neodređena.",
            },
            {
                "naziv": "Tužbeni zahtev (šta se traži)",
                "pitanje": "Da li je jasno navedeno šta se traži (vraćanje, naknada, isplata)?",
                "kljucne_reci": ["tražim", "zahtevam", "vraćanje", "poništaj", "isplata", "naknada zarade", "otpremnina"],
                "kriticnost": "visoka",
                "razlog": "Sud presuđuje u granicama tužbenog zahteva — mora biti jasan i određen.",
            },
            {
                "naziv": "Iznos naknade (ako se traži novčano)",
                "pitanje": "Ako se traži isplata — da li je naveden konkretni iznos?",
                "kljucne_reci": ["dinara", "rsd", "iznos", "mesečna zarada", "naknada", "otpremnina iznos"],
                "kriticnost": "srednja",
                "razlog": "Neodređen novčani zahtev sud može odbaciti ili zahtevati preciziranje.",
            },
            {
                "naziv": "Rok za tužbu (30 dana od dostave rešenja)",
                "pitanje": "Da li je navedeno kada je rešenje dostavljeno (relevantno za prekluzivni rok)?",
                "kljucne_reci": ["dostavlja", "dostavljeno", "primio rešenje", "dan dostave", "30 dana"],
                "kriticnost": "visoka",
                "razlog": "Rok za tužbu u radnom sporu je 30 dana od dostave akta (čl. 195 ZR) — propuštanje = gubitak prava.",
            },
            {
                "naziv": "Dokazi",
                "pitanje": "Da li su navedeni dokazi (ugovor o radu, platni listići, rešenje)?",
                "kljucne_reci": ["ugovor o radu", "platni listić", "rešenje", "dokaz", "prilaže", "obračun"],
                "kriticnost": "srednja",
                "razlog": "Dokumentarni dokazi osnova su radnog spora — bez njih tužba je slaba.",
            },
        ],
    },

    "zalba_parnicna": {
        "naziv": "Žalba na presudu (parnica)",
        "vrsta_spora": "parnicni_postupak",
        "elementi": [
            {
                "naziv": "Oznaka presude koja se pobija",
                "pitanje": "Da li je navedena oznaka (broj, datum) presude na koju se žali?",
                "kljucne_reci": ["presuda", "rešenje", "broj", "p.", "r.", "od dana", "doneo sud"],
                "kriticnost": "visoka",
                "razlog": "Žalba mora precizno identifikovati pobijanu presudu (čl. 363 ZPP).",
            },
            {
                "naziv": "Žalbeni navodi — razlozi pobijanja",
                "pitanje": "Da li su navedeni konkretni razlozi žalbe (bitna povreda ZPP, pogrešno utvrđene činjenice, pogrešna primena prava)?",
                "kljucne_reci": ["bitna povreda", "pogrešno", "pogrešna primena", "nije utvrđeno", "prvostepeni sud", "razlog žalbe"],
                "kriticnost": "visoka",
                "razlog": "Žalba bez konkretnih razloga biće odbačena ili odbijena (čl. 374 ZPP).",
            },
            {
                "naziv": "Žalbeni predlog",
                "pitanje": "Da li je naveden konkretan predlog (ukidanje, preinačenje)?",
                "kljucne_reci": ["ukine", "preinači", "predlažem", "ukinuti", "preinačiti", "žalbeni predlog"],
                "kriticnost": "visoka",
                "razlog": "Bez žalbenog predloga sud ne zna šta se traži od drugostepenog suda.",
            },
            {
                "naziv": "Rok za žalbu (15 dana od dostave)",
                "pitanje": "Da li je navedeno kada je presuda dostavljena (prekluzivni rok 15 dana)?",
                "kljucne_reci": ["dostavljeno", "dan dostave", "datum dostave", "primio presudu"],
                "kriticnost": "visoka",
                "razlog": "Rok za žalbu u parnici je 15 dana od dostave (čl. 354 ZPP) — kasna žalba se odbacuje.",
            },
            {
                "naziv": "Dokazi uz žalbu (novi dokazi sa opravdanjem)",
                "pitanje": "Ako se predlažu novi dokazi — da li je objašnjeno zašto nisu mogli biti predloženi ranije?",
                "kljucne_reci": ["novi dokaz", "nisam znao", "nije bio poznat", "naknadno", "opravdanje"],
                "kriticnost": "niska",
                "razlog": "Novi dokazi u žalbi prihvataju se samo uz opravdanje zbog čega nisu mogli biti predloženi ranije.",
            },
        ],
    },

    "predlog_izvrsenje": {
        "naziv": "Predlog za izvršenje",
        "vrsta_spora": "izvrsni_postupak",
        "elementi": [
            {
                "naziv": "Izvršna isprava",
                "pitanje": "Da li je navedena izvršna isprava (presuda, rešenje, notarska isprava)?",
                "kljucne_reci": ["presuda", "rešenje", "izvršna isprava", "notarska", "sudsko poravnanje", "broj predmeta"],
                "kriticnost": "visoka",
                "razlog": "Bez izvršne isprave predlog se odbacuje (čl. 24 ZIO).",
            },
            {
                "naziv": "Klauzula izvršnosti",
                "pitanje": "Da li je navedeno da je isprava postala izvršna (klauzula izvršnosti)?",
                "kljucne_reci": ["izvršna", "klauzula", "pravosnažna", "pravnosnažna", "postala izvršna"],
                "kriticnost": "visoka",
                "razlog": "Predlog za izvršenje zahteva ispotvrđenu izvršnu ispravu.",
            },
            {
                "naziv": "Identitet izvršnog poverioca i dužnika",
                "pitanje": "Da li su navedeni puni podaci poverioca i dužnika?",
                "kljucne_reci": ["poverilac", "dužnik", "izvršni poverilac", "ime", "naziv", "adresa", "jmbg", "pib"],
                "kriticnost": "visoka",
                "razlog": "Procesna pretpostavka — stranke moraju biti precizno identifikovane.",
            },
            {
                "naziv": "Predmet i sredstvo izvršenja",
                "pitanje": "Da li je naveden predmet (šta se prinudno izvršava) i sredstvo (plata, nekretnina, račun)?",
                "kljucne_reci": ["sredstvo izvršenja", "plata", "račun", "nekretnina", "pokretna", "na računu", "plenidba"],
                "kriticnost": "visoka",
                "razlog": "Sud mora znati na čemu se sprovodi izvršenje — bez ovoga predlog je neodređen.",
            },
            {
                "naziv": "Iznos potraživanja",
                "pitanje": "Da li je naveden tačan iznos koji se prinudno naplaćuje?",
                "kljucne_reci": ["iznos", "dinara", "rsd", "potraživanje", "kamata", "ukupno"],
                "kriticnost": "visoka",
                "razlog": "Izvršenje se sprovodi do tačno određenog iznosa.",
            },
            {
                "naziv": "Troškovi izvršnog postupka",
                "pitanje": "Da li je stavljen predlog za naknadu troškova izvršnog postupka?",
                "kljucne_reci": ["troškovi", "naknade", "izvršnog postupka", "taksa"],
                "kriticnost": "niska",
                "razlog": "Troškovi se ne dosudaju automatski — moraju biti traženi.",
            },
        ],
    },

    "tuzba_razvod": {
        "naziv": "Tužba za razvod braka",
        "vrsta_spora": "porodicni",
        "elementi": [
            {
                "naziv": "Identitet stranaka i datum venčanja",
                "pitanje": "Da li su navedeni podaci supružnika i datum sklapanja braka?",
                "kljucne_reci": ["brak", "venčanje", "datum braka", "suprug", "supruga", "od dana", "zaključen"],
                "kriticnost": "visoka",
                "razlog": "Brak mora biti identifikovan datumom zaključenja za utvrđivanje zakonskog osnova.",
            },
            {
                "naziv": "Razlog za razvod (poremećaj bračnih odnosa)",
                "pitanje": "Da li su opisane okolnosti koje ukazuju na poremećaj bračnih odnosa?",
                "kljucne_reci": ["zajednički život", "prestali", "nije moguć", "razlog", "poremećaj", "nepodnošljiv"],
                "kriticnost": "visoka",
                "razlog": "Razvod je moguć samo ako su bračni odnosi trajno poremećeni (čl. 40-41 PZ).",
            },
            {
                "naziv": "Zajednička imovina i deoba",
                "pitanje": "Da li se traži deoba zajedničke imovine stečene tokom braka?",
                "kljucne_reci": ["zajednička imovina", "deoba", "udeo", "nekretnina", "stan", "automobile", "stekli"],
                "kriticnost": "srednja",
                "razlog": "Deoba imovine se mora tražiti u tužbi (ili posebnom tužbom) — može biti spojeno.",
            },
            {
                "naziv": "Vršenje roditeljskog prava",
                "pitanje": "Ako ima dece — da li je naveden predlog za vršenje roditeljskog prava?",
                "kljucne_reci": ["dete", "deca", "roditeljsko pravo", "starateljstvo", "poveri", "zajednički"],
                "kriticnost": "visoka",
                "razlog": "Ako ima maloletne dece, sud MORA odlučiti o vršenju roditeljskog prava (čl. 42 PZ).",
            },
            {
                "naziv": "Izdržavanje supružnika ili deteta",
                "pitanje": "Da li je stavljen zahtev za alimentaciju / izdržavanje?",
                "kljucne_reci": ["izdržavanje", "alimentacija", "mesečno", "doprinos", "plaćanje"],
                "kriticnost": "srednja",
                "razlog": "Zahtev za izdržavanje mora biti eksplicitan — sud ga ne dosuduje automatski.",
            },
        ],
    },

    "krivicna_prijava": {
        "naziv": "Krivična prijava",
        "vrsta_spora": "krivicni",
        "elementi": [
            {
                "naziv": "Identitet prijavljenog lica",
                "pitanje": "Da li su navedeni lični podaci prijavljenog?",
                "kljucne_reci": ["prijavljen", "osumnjičen", "ime", "prezime", "jmbg", "adresa", "identitet"],
                "kriticnost": "visoka",
                "razlog": "Prijava mora identifikovati lice ili dati dovoljno opisa za identifikaciju.",
            },
            {
                "naziv": "Opis krivičnog dela i okolnosti",
                "pitanje": "Da li su opisane radnje koje konstituišu krivično delo?",
                "kljucne_reci": ["učinio", "izvršio", "uradio", "radnja", "delo", "okolnosti", "kada", "gde"],
                "kriticnost": "visoka",
                "razlog": "Prijava mora opisati radnje koje bi mogle biti krivično delo — bez opisa je odbijaju.",
            },
            {
                "naziv": "Datum i mesto krivičnog dela",
                "pitanje": "Da li je naveden datum i mesto izvršenja?",
                "kljucne_reci": ["datum", "dana", "godine", "mesto", "adresa", "gde", "kada se desilo"],
                "kriticnost": "visoka",
                "razlog": "Temporalno i prostorno određenje dela nužno je za nadležnost tužilaštva.",
            },
            {
                "naziv": "Dokazi i svedoci",
                "pitanje": "Da li su navedeni dostupni dokazi (dokumenta, svedoci, video zapisi)?",
                "kljucne_reci": ["dokaz", "svedok", "video", "fotografija", "snimak", "izveštaj", "prilaže"],
                "kriticnost": "srednja",
                "razlog": "Prijava bez dokaza ne znači odbijanje, ali ubrzava istragu ako se dokazi navedu.",
            },
            {
                "naziv": "Naznaka štete (materijalne ili telesne)",
                "pitanje": "Da li je opisana šteta pretrpljena od strane podnosioca?",
                "kljucne_reci": ["pretrpeo", "šteta", "povreda", "gubitak", "iznos", "povređen"],
                "kriticnost": "niska",
                "razlog": "Relevantno za mogućnost imovinskopravnog zahteva u krivičnom postupku.",
            },
        ],
    },

    "tuzba_ugovorni_spor": {
        "naziv": "Tužba u ugovornom sporu",
        "vrsta_spora": "obligacioni",
        "elementi": [
            {
                "naziv": "Identitet ugovornih strana",
                "pitanje": "Da li su navedeni podaci tužioca i tuženog?",
                "kljucne_reci": ["tužilac", "tuženi", "ugovorna strana", "ime", "naziv", "jmbg", "pib"],
                "kriticnost": "visoka",
                "razlog": "Procesna pretpostavka — čl. 98 ZPP.",
            },
            {
                "naziv": "Opis ugovora i datum zaključenja",
                "pitanje": "Da li je naveden konkretan ugovor (tip, datum, predmet ugovora)?",
                "kljucne_reci": ["ugovor", "zaključen", "datum ugovora", "predmet", "ugovorena obaveza", "zaključili"],
                "kriticnost": "visoka",
                "razlog": "Tužba mora precizno identifikovati ugovor čije se ispunjenje traži ili čiji se raskid zahteva.",
            },
            {
                "naziv": "Kršenje ugovornih obaveza",
                "pitanje": "Da li je opisano konkretno kršenje — šta tuženi nije izvršio?",
                "kljucne_reci": ["nije ispunio", "odbio", "propustio", "kršio", "neispunjenje", "docnja", "nije platio"],
                "kriticnost": "visoka",
                "razlog": "Osnov tužbe je neispunjenje ili neuredno ispunjenje ugovornih obaveza.",
            },
            {
                "naziv": "Tužbeni zahtev (šta se traži)",
                "pitanje": "Da li je naveden konkretan zahtev (ispunjenje, raskid, naknada štete, vraćanje plaćenog)?",
                "kljucne_reci": ["tražim", "zahtevam", "isplatu", "raskid", "naknad", "vraćanje", "ispunjenje"],
                "kriticnost": "visoka",
                "razlog": "Sud presuđuje u granicama zahteva — mora biti jasan.",
            },
            {
                "naziv": "Iznos potraživanja",
                "pitanje": "Da li je naveden konkretan novčani iznos (ako se traži isplata)?",
                "kljucne_reci": ["dinara", "rsd", "eur", "iznos", "vrednost", "ukupno"],
                "kriticnost": "visoka",
                "razlog": "Vrednost spora određuje mesnu i stvarnu nadležnost suda.",
            },
            {
                "naziv": "Zakonska zatezna kamata",
                "pitanje": "Da li je tražena kamata od dana docnje?",
                "kljucne_reci": ["kamata", "zatezna", "od dana", "od dospeća", "kamatu"],
                "kriticnost": "srednja",
                "razlog": "Kamata teče od dana kada je dužnik pao u docnju (čl. 324 ZOO).",
            },
            {
                "naziv": "Dokazi",
                "pitanje": "Da li su navedeni dokazi (ugovor, fakture, prepiska, dokazne isprave)?",
                "kljucne_reci": ["prilaže", "ugovor", "faktura", "profaktura", "email", "dopis", "dokaz", "otpremnica"],
                "kriticnost": "srednja",
                "razlog": "Bez dokaza tužba je nepotporna.",
            },
        ],
    },
}

# Mapping: tipovi koji su prethodno bili u /api/podnesak → novi tipovi ovde
LEGACY_TIP_MAP: dict[str, str] = {
    "tuzba_naknada_stete": "tuzba_naknada_stete",
    "zalba_parnicna":      "zalba_parnicna",
    "predlog_izvrsenje":   "predlog_izvrsenje",
}

SVI_TIPOVI: list[str] = list(CHECKLIST.keys())


def get_config(tip: str) -> TipConfig:
    """Vraća konfiguraciju za dati tip podneska. KeyError ako ne postoji."""
    if tip not in CHECKLIST:
        raise KeyError(f"Nepoznat tip podneska: {tip!r}. Dozvoljeni: {SVI_TIPOVI}")
    return CHECKLIST[tip]
