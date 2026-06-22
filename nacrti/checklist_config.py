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

    "zalba_na_presudu": {
        "naziv": "Žalba na presudu (parnični postupak)",
        "vrsta_spora": "parnicni_postupak",
        "elementi": [
            {
                "naziv": "Oznaka presude koja se pobija",
                "pitanje": "Da li je naveden broj i datum presude na koju se žali?",
                "kljucne_reci": ["presuda", "broj", "p.", "od dana", "doneo sud", "prvostepeni"],
                "kriticnost": "visoka",
                "razlog": "Žalba mora precizno identifikovati pobijanu presudu (čl. 363 ZPP).",
            },
            {
                "naziv": "Žalbeni razlozi (bitna povreda ZPP, pogrešne činjenice, pogrešna primena prava)",
                "pitanje": "Da li su navedeni konkretni razlozi pobijanja presude?",
                "kljucne_reci": ["bitna povreda", "pogrešno", "pogrešna primena", "pogrešno utvrđene", "žalbeni razlog", "prvostepeni sud je"],
                "kriticnost": "visoka",
                "razlog": "Žalba bez konkretnih razloga biće odbačena ili odbijena (čl. 374 ZPP).",
            },
            {
                "naziv": "Žalbeni predlog (ukidanje ili preinačenje)",
                "pitanje": "Da li je naveden konkretan predlog šta drugostepeni sud treba da uradi?",
                "kljucne_reci": ["ukine", "preinači", "predlažem", "ukinuti", "preinačiti", "vrati na ponovni"],
                "kriticnost": "visoka",
                "razlog": "Bez žalbenog predloga sud ne zna šta se traži.",
            },
            {
                "naziv": "Rok za žalbu — datum dostave presude",
                "pitanje": "Da li je navedeno kada je presuda dostavljena (15 dana od dostave)?",
                "kljucne_reci": ["dostavljeno", "dan dostave", "primio presudu", "dostavljena"],
                "kriticnost": "visoka",
                "razlog": "Rok za žalbu u parnici je 15 dana od dostave (čl. 354 ZPP) — kasna žalba se odbacuje.",
            },
        ],
    },

    "zalba_na_resenje": {
        "naziv": "Žalba na rešenje",
        "vrsta_spora": "parnicni_postupak",
        "elementi": [
            {
                "naziv": "Oznaka rešenja koje se pobija",
                "pitanje": "Da li je naveden broj i datum rešenja na koje se žali?",
                "kljucne_reci": ["rešenje", "broj", "r.", "od dana", "doneo", "prvostepeni"],
                "kriticnost": "visoka",
                "razlog": "Žalba mora identifikovati pobijano rešenje po broju i datumu (čl. 393 ZPP).",
            },
            {
                "naziv": "Razlozi pobijanja rešenja",
                "pitanje": "Da li su navedeni konkretni razlozi zašto je rešenje nezakonito ili neosnovano?",
                "kljucne_reci": ["razlog", "pogrešno", "nezakonito", "neosnovano", "povređuje", "jer"],
                "kriticnost": "visoka",
                "razlog": "Žalba bez razloga je procesno neuredna.",
            },
            {
                "naziv": "Rok za žalbu (15 dana od dostave)",
                "pitanje": "Da li je navedeno kad je rešenje dostavljeno?",
                "kljucne_reci": ["dostavljeno", "dan dostave", "primio rešenje"],
                "kriticnost": "visoka",
                "razlog": "Rok za žalbu na rešenje je 15 dana od dostave (čl. 395 ZPP).",
            },
            {
                "naziv": "Žalbeni predlog",
                "pitanje": "Da li je naveden predlog — ukidanje ili preinačenje rešenja?",
                "kljucne_reci": ["ukine", "preinači", "predlažem", "poništi"],
                "kriticnost": "srednja",
                "razlog": "Drugostepeni sud treba da zna šta se traži.",
            },
        ],
    },

    "prigovor_platni_nalog": {
        "naziv": "Prigovor na platni nalog",
        "vrsta_spora": "obligacioni",
        "elementi": [
            {
                "naziv": "Oznaka platnog naloga koji se pobija",
                "pitanje": "Da li je naveden broj i datum platnog naloga?",
                "kljucne_reci": ["platni nalog", "broj", "od dana", "doneo sud"],
                "kriticnost": "visoka",
                "razlog": "Prigovor mora identifikovati konkretan platni nalog (čl. 463 ZPP).",
            },
            {
                "naziv": "Razlozi prigovora",
                "pitanje": "Da li su navedeni razlozi zašto se ospori platni nalog?",
                "kljucne_reci": ["osporavam", "prigovor", "potraživanje ne postoji", "pogodba", "iznos", "razlog"],
                "kriticnost": "visoka",
                "razlog": "Prigovor bez razloga se tretira kao formalni prigovor — automatski prelazi u parnicu.",
            },
            {
                "naziv": "Rok za prigovor (8 dana od dostave)",
                "pitanje": "Da li je navedeno kada je platni nalog dostavljen?",
                "kljucne_reci": ["dostavljeno", "dan dostave", "primio"],
                "kriticnost": "visoka",
                "razlog": "Rok za prigovor je 8 dana od dostave (čl. 462 ZPP) — propuštanje = pravosnažan platni nalog.",
            },
            {
                "naziv": "Iznos koji se osporava",
                "pitanje": "Da li je naveden iznos ili deo iznosa koji se osporava?",
                "kljucne_reci": ["iznos", "dinara", "rsd", "deo", "celokupno", "potraživanje"],
                "kriticnost": "srednja",
                "razlog": "Parcijalni prigovor je moguć — treba navesti šta tačno.",
            },
        ],
    },

    "predlog_privremena_mera": {
        "naziv": "Predlog za privremenu meru",
        "vrsta_spora": "parnicni_postupak",
        "elementi": [
            {
                "naziv": "Potraživanje koje se obezbeđuje",
                "pitanje": "Da li je opisano potraživanje čije se obezbeđenje traži?",
                "kljucne_reci": ["potraživanje", "obezbeđenje", "tražim", "zahtev", "iznos", "pravo"],
                "kriticnost": "visoka",
                "razlog": "Privremena mera služi za obezbeđenje konkretnog potraživanja (čl. 302 ZIO).",
            },
            {
                "naziv": "Verovatnost postojanja potraživanja",
                "pitanje": "Da li su navedeni dokazi koji čine potraživanje verovatnim?",
                "kljucne_reci": ["verovatno", "dokaz", "ugovor", "izjava", "nalaz", "prilaže"],
                "kriticnost": "visoka",
                "razlog": "Sud mora biti ubеđen u verovatnost potraživanja (čl. 303 ZIO).",
            },
            {
                "naziv": "Opasnost od otežavanja naplate (periculum in mora)",
                "pitanje": "Da li je opisano zašto postoji opasnost da bez mere naplata ne bi bila moguća?",
                "kljucne_reci": ["opasnost", "otežano", "onemogućeno", "raspolaže", "iseliti", "skriti", "otuđiti"],
                "kriticnost": "visoka",
                "razlog": "Periculum in mora je uslov za privremenu meru (čl. 303 ZIO).",
            },
            {
                "naziv": "Predmet i sadržaj tražene mere",
                "pitanje": "Da li je konkretno navedeno šta treba zabraniti/naložiti (zabrana otuđenja, zabrana raspolaganja računom...)?",
                "kljucne_reci": ["zabranjuje se", "nalaže se", "zabrana otuđenja", "zabrana raspolaganja", "mera"],
                "kriticnost": "visoka",
                "razlog": "Predlog mora precizno navesti sadržaj tražene mere.",
            },
            {
                "naziv": "Predlog za obezbeđenje bez prethodnog obaveštenja protivnika",
                "pitanje": "Da li je traženo donošenje mere bez saslušanja protivnika (ex parte)?",
                "kljucne_reci": ["bez obaveštenja", "ex parte", "bez saslušanja", "hitno", "odmah"],
                "kriticnost": "niska",
                "razlog": "Moguće je tražiti privremenu meru bez saslušanja ako hitnost to nalaže (čl. 306 ZIO).",
            },
        ],
    },

    "opomena_duznik": {
        "naziv": "Opomena pre tužbe",
        "vrsta_spora": "obligacioni",
        "elementi": [
            {
                "naziv": "Identitet poverioca i dužnika",
                "pitanje": "Da li su navedeni podaci poverioca (ko šalje) i dužnika (kome se šalje)?",
                "kljucne_reci": ["poverilac", "dužnik", "ime", "naziv", "adresa", "od strane"],
                "kriticnost": "visoka",
                "razlog": "Opomena mora biti adresirana konkretnom dužniku od konkretnog poverioca.",
            },
            {
                "naziv": "Osnov i visina duga",
                "pitanje": "Da li je naveden osnov nastanka duga i konkretan iznos?",
                "kljucne_reci": ["dug", "potraživanje", "iznos", "dinara", "rsd", "eur", "osnov", "ugovor", "faktura"],
                "kriticnost": "visoka",
                "razlog": "Bez konkretnog iznosa i osnova opomena je neodređena.",
            },
            {
                "naziv": "Rok za ispunjenje",
                "pitanje": "Da li je naveden rok u kom dužnik treba da ispuni obavezu?",
                "kljucne_reci": ["rok", "dana od", "do datuma", "u roku od", "najkasnije"],
                "kriticnost": "visoka",
                "razlog": "Opomena bez roka ne stavlja dužnika u docnju — docnja počinje od isteka roka (čl. 324 ZOO).",
            },
            {
                "naziv": "Posledica neispunjenja (tužba, zatezna kamata)",
                "pitanje": "Da li je navedeno šta će se desiti ako dužnik ne ispuni u roku?",
                "kljucne_reci": ["tužba", "sudski put", "kamata", "zatezna", "prinudno", "posledica"],
                "kriticnost": "srednja",
                "razlog": "Navođenje posledica pojačava efikasnost opomene.",
            },
        ],
    },

    "zahtev_poslodavcu": {
        "naziv": "Zahtev zaposlenog poslodavcu",
        "vrsta_spora": "radni",
        "elementi": [
            {
                "naziv": "Identitet zaposlenog i poslodavca",
                "pitanje": "Da li su navedeni podaci zaposlenog (ime, radno mesto) i poslodavca?",
                "kljucne_reci": ["zaposleni", "radnik", "poslodavac", "ime", "radno mesto", "naziv firme"],
                "kriticnost": "visoka",
                "razlog": "Zahtev mora biti identifikovan — ko ga podnosi, kome.",
            },
            {
                "naziv": "Predmet zahteva (šta se traži)",
                "pitanje": "Da li je jasno navedeno šta se od poslodavca traži (zarada, pravo, izmena)?",
                "kljucne_reci": ["zahtevam", "tražim", "naknada", "zarada", "pravo", "isplata", "izmena"],
                "kriticnost": "visoka",
                "razlog": "Zahtev mora biti određen i konkretan.",
            },
            {
                "naziv": "Pravni osnov (zakon, ugovor, pravo)",
                "pitanje": "Da li je naveden pravni osnov zahteva (zakonska odredba ili ugovorna obaveza)?",
                "kljucne_reci": ["zakon o radu", "ugovor o radu", "član", "pravo", "obaveza poslodavca", "zr"],
                "kriticnost": "srednja",
                "razlog": "Pozivanje na zakonski osnov pojačava zahtev i obavezuje poslodavca na odgovor.",
            },
            {
                "naziv": "Rok za odgovor",
                "pitanje": "Da li je naveden rok u kom poslodavac treba da odgovori ili ispuni zahtev?",
                "kljucne_reci": ["rok", "dana od", "do datuma", "najkasnije"],
                "kriticnost": "srednja",
                "razlog": "Bez roka zahtev je informativnog karaktera — rok daje jasnu obavezu.",
            },
        ],
    },

    "ugovor_neodredjeno": {
        "naziv": "Ugovor o radu — neodređeno vreme",
        "vrsta_spora": "radni",
        "elementi": [
            {
                "naziv": "Identitet poslodavca i zaposlenog",
                "pitanje": "Da li su navedeni puni podaci poslodavca (naziv, PIB, adresa) i zaposlenog (ime, JMBG)?",
                "kljucne_reci": ["poslodavac", "zaposleni", "pib", "jmbg", "adresa", "matični broj"],
                "kriticnost": "visoka",
                "razlog": "Ugovor o radu mora sadržati identitet stranaka (čl. 33 ZR).",
            },
            {
                "naziv": "Radno mesto i opis poslova",
                "pitanje": "Da li je naveden naziv radnog mesta i opis poslova?",
                "kljucne_reci": ["radno mesto", "opis poslova", "pozicija", "naziv posla", "vrsta rada"],
                "kriticnost": "visoka",
                "razlog": "Obavezni element ugovora po čl. 33 st. 1 t. 4 ZR.",
            },
            {
                "naziv": "Mesto rada",
                "pitanje": "Da li je navedeno mesto gde se rad obavlja?",
                "kljucne_reci": ["mesto rada", "adresa", "poslovni prostor", "sedište", "teren"],
                "kriticnost": "visoka",
                "razlog": "Obavezni element ugovora po čl. 33 st. 1 t. 5 ZR.",
            },
            {
                "naziv": "Osnovna zarada",
                "pitanje": "Da li je naveden iznos osnovne zarade u dinarima?",
                "kljucne_reci": ["zarada", "bruto", "neto", "dinara", "mesečno", "osnovna plata"],
                "kriticnost": "visoka",
                "razlog": "Obavezni element ugovora po čl. 33 st. 1 t. 9 ZR.",
            },
            {
                "naziv": "Radno vreme (broj sati nedeljno)",
                "pitanje": "Da li je naveden broj radnih sati nedeljno ili dnevno?",
                "kljucne_reci": ["radno vreme", "sati", "40 sati", "nedeljno", "dnevno", "puno"],
                "kriticnost": "visoka",
                "razlog": "Obavezni element po čl. 33 st. 1 t. 7 ZR — puno ili nepuno radno vreme.",
            },
            {
                "naziv": "Datum početka rada",
                "pitanje": "Da li je naveden datum od kada zaposleni počinje sa radom?",
                "kljucne_reci": ["datum", "počinje", "od dana", "od datuma", "stupanje"],
                "kriticnost": "visoka",
                "razlog": "Obavezni element ugovora — od tog datuma teku prava i obaveze.",
            },
            {
                "naziv": "Godišnji odmor",
                "pitanje": "Da li je navedeno pravo na godišnji odmor (minimum 20 radnih dana)?",
                "kljucne_reci": ["godišnji odmor", "odmor", "radnih dana", "20 dana"],
                "kriticnost": "srednja",
                "razlog": "Zakonski minimum je 20 radnih dana (čl. 68 ZR) — mora biti u ugovoru.",
            },
        ],
    },

    "ugovor_odredjeno": {
        "naziv": "Ugovor o radu — određeno vreme",
        "vrsta_spora": "radni",
        "elementi": [
            {
                "naziv": "Identitet stranaka",
                "pitanje": "Da li su navedeni puni podaci poslodavca i zaposlenog?",
                "kljucne_reci": ["poslodavac", "zaposleni", "pib", "jmbg", "naziv"],
                "kriticnost": "visoka",
                "razlog": "Obavezni element po čl. 33 ZR.",
            },
            {
                "naziv": "Trajanje ugovora (datum početka i kraja)",
                "pitanje": "Da li su navedeni tačan datum početka i datum isteka ugovora?",
                "kljucne_reci": ["od dana", "do dana", "datum kraja", "ističe", "period", "godinu", "mesec"],
                "kriticnost": "visoka",
                "razlog": "Ugovor na određeno mora imati jasno definisan period (čl. 37 ZR).",
            },
            {
                "naziv": "Razlog za zasnivanje na određeno",
                "pitanje": "Da li je naveden razlog zašto se zasniva radni odnos na određeno (zamena, sezona, projekat)?",
                "kljucne_reci": ["zamena", "sezonski", "projekat", "povećan obim", "razlog", "privremeni"],
                "kriticnost": "visoka",
                "razlog": "Ugovor na određeno bez zakonskog razloga smatra se ugovorom na neodređeno (čl. 37 ZR).",
            },
            {
                "naziv": "Radno mesto, zarada, radno vreme",
                "pitanje": "Da li su navedeni radno mesto, osnovna zarada i radno vreme?",
                "kljucne_reci": ["radno mesto", "zarada", "sati", "nedeljno"],
                "kriticnost": "visoka",
                "razlog": "Isti obavezni elementi kao i za ugovor na neodređeno (čl. 33 ZR).",
            },
        ],
    },

    "sporazumni_raskid": {
        "naziv": "Sporazumni raskid radnog odnosa",
        "vrsta_spora": "radni",
        "elementi": [
            {
                "naziv": "Identitet stranaka",
                "pitanje": "Da li su navedeni podaci poslodavca i zaposlenog?",
                "kljucne_reci": ["poslodavac", "zaposleni", "ime", "naziv", "jmbg"],
                "kriticnost": "visoka",
                "razlog": "Sporazum mora identifikovati stranke.",
            },
            {
                "naziv": "Datum sporazumnog raskida",
                "pitanje": "Da li je naveden datum kada se raskida radni odnos?",
                "kljucne_reci": ["datum raskida", "od dana", "prestaje", "sa danom"],
                "kriticnost": "visoka",
                "razlog": "Datum prestanka mora biti jasan — od njega teku prava po osnovu prestanka.",
            },
            {
                "naziv": "Dobrovoljnost i saglasnost",
                "pitanje": "Da li je eksplicitno navedeno da je sporazum zaključen dobrovoljno?",
                "kljucne_reci": ["sporazumno", "dobrovoljno", "saglasno", "obe strane", "zajednički dogovor"],
                "kriticnost": "visoka",
                "razlog": "Sporazumni raskid mora biti dobrovoljan — prisilni se može osporiti.",
            },
            {
                "naziv": "Otpremnina (ako se isplaćuje)",
                "pitanje": "Da li je naveden iznos otpremnine ili je eksplicitno navedeno da se ne isplaćuje?",
                "kljucne_reci": ["otpremnina", "naknada", "isplaćuje", "iznos", "bez otpremnine"],
                "kriticnost": "srednja",
                "razlog": "Sporazumni raskid ne garantuje otpremninu automatski — mora se navesti.",
            },
            {
                "naziv": "Neiskorišćeni odmori i naknada",
                "pitanje": "Da li je regulisano pitanje neiskorišćenog godišnjeg odmora?",
                "kljucne_reci": ["godišnji odmor", "neiskorišćen", "naknada za odmor", "isplaćuje"],
                "kriticnost": "srednja",
                "razlog": "Neiskorišćeni odmor se isplaćuje kao naknada zarade (čl. 76 ZR).",
            },
        ],
    },

    "ugovor_kupoprodaja": {
        "naziv": "Ugovor o kupoprodaji",
        "vrsta_spora": "obligacioni",
        "elementi": [
            {
                "naziv": "Identitet prodavca i kupca",
                "pitanje": "Da li su navedeni puni podaci prodavca i kupca (ime/naziv, adresa, JMBG/PIB)?",
                "kljucne_reci": ["prodavac", "kupac", "ime", "naziv", "jmbg", "pib", "adresa"],
                "kriticnost": "visoka",
                "razlog": "Kupoprodajni ugovor mora precizno identifikovati stranke (čl. 454 ZOO).",
            },
            {
                "naziv": "Predmet kupoprodaje (šta se prodaje)",
                "pitanje": "Da li je jasno opisano šta je predmet kupoprodaje (nepokretnost, vozilo, roba...)?",
                "kljucne_reci": ["predmet", "prodaje se", "kupuje se", "stvar", "nepokretnost", "vozilo", "roba", "oprema"],
                "kriticnost": "visoka",
                "razlog": "Predmet mora biti određen ili odrediv (čl. 454 st. 1 ZOO).",
            },
            {
                "naziv": "Cena i način plaćanja",
                "pitanje": "Da li je navedena tačna cena i način plaćanja?",
                "kljucne_reci": ["cena", "dinara", "rsd", "eur", "plaćanje", "ugovorena cena", "iznos"],
                "kriticnost": "visoka",
                "razlog": "Cena je bitni element kupoprodajnog ugovora — bez nje ugovor je ništav (čl. 454 ZOO).",
            },
            {
                "naziv": "Rok i način predaje",
                "pitanje": "Da li je naveden rok kada se predmet predaje i na koji način?",
                "kljucne_reci": ["predaja", "rok", "preuzimanje", "datum", "na dan", "po potpisivanju"],
                "kriticnost": "visoka",
                "razlog": "Trenutak predaje određuje kada prelazi rizik i vlasništvo.",
            },
            {
                "naziv": "Garancija i odgovornost za skrivene nedostatke",
                "pitanje": "Da li je regulisana odgovornost prodavca za materijalne nedostatke?",
                "kljucne_reci": ["garancija", "nedostatak", "skriveni", "odgovornost prodavca", "mana", "ispravnost"],
                "kriticnost": "srednja",
                "razlog": "Odgovornost za skrivene nedostatke postoji po zakonu (čl. 480-499 ZOO), ali ugovor može urediti drugačije.",
            },
        ],
    },

    "ugovor_zakup": {
        "naziv": "Ugovor o zakupu nepokretnosti",
        "vrsta_spora": "obligacioni",
        "elementi": [
            {
                "naziv": "Identitet zakupodavca i zakupca",
                "pitanje": "Da li su navedeni puni podaci obe ugovorne strane?",
                "kljucne_reci": ["zakupodavac", "zakupac", "ime", "naziv", "jmbg", "pib", "adresa"],
                "kriticnost": "visoka",
                "razlog": "Obavezni element ugovora o zakupu.",
            },
            {
                "naziv": "Opis nepokretnosti koja se daje u zakup",
                "pitanje": "Da li je precizno opisana nepokretnost (adresa, površina, katastarska parcela)?",
                "kljucne_reci": ["nepokretnost", "adresa", "površina", "m²", "stan", "poslovni prostor", "katastarska", "broj parcele"],
                "kriticnost": "visoka",
                "razlog": "Predmet zakupa mora biti određen — čl. 567 ZOO.",
            },
            {
                "naziv": "Zakupnina i rok plaćanja",
                "pitanje": "Da li je navedena mesečna zakupnina i rok/dan kada se plaća?",
                "kljucne_reci": ["zakupnina", "kirija", "mesečno", "dinara", "rsd", "eur", "rok plaćanja", "do dana"],
                "kriticnost": "visoka",
                "razlog": "Zakupnina je bitni element ugovora — čl. 567 ZOO.",
            },
            {
                "naziv": "Trajanje zakupa (početak i kraj)",
                "pitanje": "Da li su navedeni datum početka i trajanje ili datum isteka zakupa?",
                "kljucne_reci": ["od dana", "na period", "godinu", "mesec", "do datuma", "ističe"],
                "kriticnost": "visoka",
                "razlog": "Trajanje određuje kada se nepokretnost mora vratiti.",
            },
            {
                "naziv": "Kaution (depozit) i uslovi povraćaja",
                "pitanje": "Da li je regulisan depozit i uslovi pod kojima se vraća?",
                "kljucne_reci": ["depozit", "kaution", "kaucija", "povraćaj", "obezbeđenje", "garancija"],
                "kriticnost": "srednja",
                "razlog": "Depozit je česta praksa — treba regulisati uslove za povraćaj i zadržavanje.",
            },
            {
                "naziv": "Komunalni troškovi i obaveze",
                "pitanje": "Da li je određeno ko snosi komunalne troškove (struja, voda, komunalije)?",
                "kljucne_reci": ["komunalije", "struja", "voda", "gas", "grejanje", "troškovi", "snosi"],
                "kriticnost": "srednja",
                "razlog": "Bez jasne podele troškova dolazi do sporova.",
            },
        ],
    },

    "punomocje": {
        "naziv": "Punomoćje",
        "vrsta_spora": "opste",
        "elementi": [
            {
                "naziv": "Identitet vlastodavca (ko daje ovlašćenje)",
                "pitanje": "Da li su navedeni puni podaci vlastodavca (ime, JMBG/PIB, adresa)?",
                "kljucne_reci": ["vlastodavac", "ovlašćujem", "dajem ovlašćenje", "ime", "jmbg", "adresa"],
                "kriticnost": "visoka",
                "razlog": "Punomoćje bez identifikacije vlastodavca nema pravno dejstvo.",
            },
            {
                "naziv": "Identitet punomoćnika (kome se daje ovlašćenje)",
                "pitanje": "Da li su navedeni puni podaci punomoćnika (ime, adresa, broj advokatske licence)?",
                "kljucne_reci": ["punomoćnik", "advokat", "ime", "adresa", "broj licence", "kome"],
                "kriticnost": "visoka",
                "razlog": "Punomoćnik mora biti precizno identifikovan.",
            },
            {
                "naziv": "Predmet ovlašćenja (za šta važi punomoćje)",
                "pitanje": "Da li je jasno navedeno za koje radnje ili predmete važi punomoćje?",
                "kljucne_reci": ["ovlašćuje se", "za zastupanje", "predmet", "svrha", "za radnje", "u svim"],
                "kriticnost": "visoka",
                "razlog": "Opšte ili posebno punomoćje — opseg mora biti jasan (čl. 90-94 ZOO).",
            },
            {
                "naziv": "Posebna ovlašćenja (ako postoje)",
                "pitanje": "Da li su navedena posebna ovlašćenja za zaključenje nagodbe, odricanje od tužbe, itd.?",
                "kljucne_reci": ["nagodba", "odricanje", "povlačenje", "posebno ovlašćuje", "konfesija"],
                "kriticnost": "srednja",
                "razlog": "Posebne radnje (nagodba, odricanje) zahtevaju izričito ovlašćenje (čl. 93 ZOO).",
            },
            {
                "naziv": "Datum i potpis vlastodavca",
                "pitanje": "Da li je navedeno mesto i datum, i da li se traži potpis?",
                "kljucne_reci": ["datum", "dana", "potpis", "potpisano", "mesto"],
                "kriticnost": "visoka",
                "razlog": "Punomoćje bez datuma i potpisa nema dokaznu snagu.",
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

    "aneks": {
        "naziv": "Aneks ugovora o radu",
        "vrsta_spora": "radni",
        "elementi": [
            {
                "naziv": "Referenca na osnovni ugovor",
                "pitanje": "Da li je naveden datum i naziv osnovnog ugovora o radu koji se menja?",
                "kljucne_reci": ["ugovor o radu", "zaključen", "od dana", "osnovi ugovor", "prethodni"],
                "kriticnost": "visoka",
                "razlog": "Aneks mora referencirati ugovor koji se menja.",
            },
            {
                "naziv": "Šta se menja (konkretna odredba)",
                "pitanje": "Da li je jasno navedeno koja odredba ugovora se menja i kako?",
                "kljucne_reci": ["menja se", "član", "odredba", "umesto", "novi tekst", "glasi"],
                "kriticnost": "visoka",
                "razlog": "Aneks mora precizno navesti šta se menja — čl. 171 ZR.",
            },
            {
                "naziv": "Datum od kada važi izmena",
                "pitanje": "Da li je naveden datum od kada izmena stupa na snagu?",
                "kljucne_reci": ["od dana", "počev od", "datum stupanja", "sa danom"],
                "kriticnost": "visoka",
                "razlog": "Izmena važi od navedenog datuma — bez datuma je neodređena.",
            },
            {
                "naziv": "Saglasnost zaposlenog",
                "pitanje": "Da li je navedeno da zaposleni pristaje na izmenu?",
                "kljucne_reci": ["saglasan", "pristaje", "prihvata", "potpis zaposlenog", "slaganje"],
                "kriticnost": "visoka",
                "razlog": "Aneks je dvostrani akt — mora imati saglasnost zaposlenog.",
            },
        ],
    },

    "obaveštenje_o_otkazu": {
        "naziv": "Obaveštenje o otkazu ugovora",
        "vrsta_spora": "obligacioni",
        "elementi": [
            {
                "naziv": "Identitet strana i reference na ugovor",
                "pitanje": "Da li su navedeni podaci o stranama i konkretan ugovor koji se otkazuje?",
                "kljucne_reci": ["ugovor", "zaključen", "datum", "strana", "između"],
                "kriticnost": "visoka",
                "razlog": "Obaveštenje mora identifikovati ugovor koji se otkazuje.",
            },
            {
                "naziv": "Razlog otkaza",
                "pitanje": "Da li je naveden razlog zbog kojeg se ugovor otkazuje?",
                "kljucne_reci": ["razlog", "zbog", "kršenje", "neispunjenje", "isteka roka", "okolnosti"],
                "kriticnost": "visoka",
                "razlog": "Razlog otkaza je posebno važan za ugovore sa zaštitom od neopravdanog raskida.",
            },
            {
                "naziv": "Datum otkaza / otkazni rok",
                "pitanje": "Da li je naveden datum kada otkaz stupa na snagu ili otkazni rok?",
                "kljucne_reci": ["otkazni rok", "od dana", "sa danom", "datum raskida", "stupa na snagu"],
                "kriticnost": "visoka",
                "razlog": "Otkazni rok ili datum stupanja na snagu mora biti jasan.",
            },
            {
                "naziv": "Zahtev za vraćanje stvari ili plaćanje",
                "pitanje": "Da li je naveden zahtev šta druga strana treba da vrati ili plati po raskidu?",
                "kljucne_reci": ["vraćanje", "isplata", "naknada", "duguje", "obavezuje"],
                "kriticnost": "srednja",
                "razlog": "Raskid ugovora ne povlači automatski vraćanje ispunjenog — mora biti traženo.",
            },
        ],
    },

    "odgovor_na_tuzbu": {
        "naziv": "Odgovor na tužbu",
        "vrsta_spora": "parnicni_postupak",
        "elementi": [
            {
                "naziv": "Identitet tuženog i oznaka predmeta",
                "pitanje": "Da li su navedeni podaci tuženog i broj/datum tužbe na koju se odgovara?",
                "kljucne_reci": ["tuženi", "ime", "naziv", "predmet", "tužba", "broj", "od dana"],
                "kriticnost": "visoka",
                "razlog": "Odgovor mora identifikovati tuženog i tužbu na koju se odgovara (čl. 98 i 274 ZPP).",
            },
            {
                "naziv": "Osporavanje tužbenih navoda",
                "pitanje": "Da li su konkretan navedeni tužbeni navodi koji se osporavaju?",
                "kljucne_reci": ["osporavam", "ne stoji", "pogrešno", "nije tačno", "neosnovano", "navod"],
                "kriticnost": "visoka",
                "razlog": "Neosporeni navodi smatraju se priznatim — svaki navod koji se osporava mora biti izričito naveden.",
            },
            {
                "naziv": "Rok za odgovor (30 dana od prijema tužbe)",
                "pitanje": "Da li je navedeno kada je tužba primljena (relevantno za prekluzivni rok od 30 dana)?",
                "kljucne_reci": ["primio tužbu", "dostava", "dan dostave", "dan prijema", "30 dana"],
                "kriticnost": "visoka",
                "razlog": "Rok za odgovor na tužbu je 30 dana od dostave (čl. 274 ZPP) — kasno podnesen odgovor se ne uzima u obzir.",
            },
            {
                "naziv": "Prigovor nadležnosti (ako se ističe)",
                "pitanje": "Da li se ističe prigovor stvarne ili mesne nadležnosti suda?",
                "kljucne_reci": ["nadležnost", "prigovor", "mesna nadležnost", "stvarna nadležnost", "nenadležan"],
                "kriticnost": "srednja",
                "razlog": "Prigovor nadležnosti mora biti istaknut najkasnije u odgovoru na tužbu — posle toga se gubi (čl. 16 ZPP).",
            },
            {
                "naziv": "Dokazi tuženog",
                "pitanje": "Da li su predloženi dokazi u odbranu (dokumenta, svedoci, veštaci)?",
                "kljucne_reci": ["dokaz", "prilaže", "svedok", "veštak", "prilog", "izjava"],
                "kriticnost": "srednja",
                "razlog": "Dokazi koji nisu predloženi u odgovoru mogu biti odbijeni u daljem toku postupka.",
            },
        ],
    },

    "zalba_krivicna": {
        "naziv": "Žalba na presudu (krivični postupak)",
        "vrsta_spora": "krivicni",
        "elementi": [
            {
                "naziv": "Oznaka presude koja se pobija",
                "pitanje": "Da li je naveden broj i datum krivične presude na koju se žali i sud koji ju je doneo?",
                "kljucne_reci": ["presuda", "broj", "k.", "od dana", "doneo sud", "prvostepeni"],
                "kriticnost": "visoka",
                "razlog": "Žalba mora precizno identifikovati pobijanu presudu (čl. 453 ZKP).",
            },
            {
                "naziv": "Identitet žalioca (optuženi, branilac ili oštećeni)",
                "pitanje": "Da li je jasno ko podnosi žalbu — optuženi, branilac ili oštećeni?",
                "kljucne_reci": ["optuženi", "okrivljeni", "branilac", "oštećeni", "žalilac", "ime"],
                "kriticnost": "visoka",
                "razlog": "Legitimacija za žalbu zavisi od statusa žalioca (čl. 441 ZKP).",
            },
            {
                "naziv": "Razlozi žalbe (ZKP osnovi pobijanja)",
                "pitanje": "Da li su navedeni zakonski razlozi žalbe (bitna povreda ZKP, pogrešno utvrđene činjenice, pogrešna primena krivičnog zakona, odluka o sankciji)?",
                "kljucne_reci": ["bitna povreda", "pogrešno utvrđene", "pogrešna primena", "sankcija", "kazna", "razlog žalbe", "zkp"],
                "kriticnost": "visoka",
                "razlog": "Žalba bez konkretnih zakonskih razloga biće odbačena — razlozi iz čl. 438 ZKP su taksativno nabrojani.",
            },
            {
                "naziv": "Žalbeni predlog",
                "pitanje": "Da li je naveden konkretan predlog (osloboditi, ukinuti presudu, preinačiti odluku o kazni)?",
                "kljucne_reci": ["osloboditi", "ukinuti", "preinačiti", "predlažem", "žalbeni predlog"],
                "kriticnost": "visoka",
                "razlog": "Drugostepeni sud presuđuje u granicama žalbenog predloga.",
            },
            {
                "naziv": "Rok za žalbu (15 dana od dostave presude)",
                "pitanje": "Da li je navedeno kada je presuda dostavljena (rok 15 dana)?",
                "kljucne_reci": ["dostavljena", "primio presudu", "dan dostave", "15 dana"],
                "kriticnost": "visoka",
                "razlog": "Rok za žalbu u krivičnom postupku je 15 dana od dostave presude (čl. 455 ZKP) — kasna žalba se odbacuje.",
            },
        ],
    },

    "urgencija_sudu": {
        "naziv": "Urgencija sudu (hitno postupanje)",
        "vrsta_spora": "parnicni_postupak",
        "elementi": [
            {
                "naziv": "Identitet stranke i broj predmeta",
                "pitanje": "Da li su navedeni podaci stranke koja podnosi urgenciju i broj predmeta kod suda?",
                "kljucne_reci": ["ime", "naziv", "stranka", "predmet", "broj predmeta", "sud"],
                "kriticnost": "visoka",
                "razlog": "Urgencija mora identifikovati predmet o kom se traži hitno postupanje.",
            },
            {
                "naziv": "Razlog urgencije i period nepostupanja",
                "pitanje": "Da li je opisano zašto se urgira i koliko dugo sud nije postupao?",
                "kljucne_reci": ["nije postupio", "zakašnjenje", "mesec", "dana", "period", "čekamo", "razlog"],
                "kriticnost": "visoka",
                "razlog": "Urgencija bez konkretnog razloga i perioda nepostupanja nema dejstvo.",
            },
            {
                "naziv": "Posledice nepostupanja (šteta stranci)",
                "pitanje": "Da li je opisano kakvu štetu ili nepovoljne posledice uzrokuje zakašnjenje?",
                "kljucne_reci": ["šteta", "gubitak", "zastarelost", "rok", "posledica", "ugroženo pravo"],
                "kriticnost": "visoka",
                "razlog": "Hitnost se pravda konkretnim posledicama — bez toga urgencija je formalna.",
            },
            {
                "naziv": "Konkretan predlog (šta se traži od suda)",
                "pitanje": "Da li je naveden konkretan zahtev (zakazati ročište, doneti odluku, dostaviti poziv)?",
                "kljucne_reci": ["tražim", "predlažem", "zakazati", "doneti", "dostaviti", "hitno"],
                "kriticnost": "visoka",
                "razlog": "Sud mora znati šta se od njega traži — urgencija bez predloga je informativna.",
            },
        ],
    },

    "prigovor_izvrsenje": {
        "naziv": "Prigovor na rešenje o izvršenju",
        "vrsta_spora": "izvrsni_postupak",
        "elementi": [
            {
                "naziv": "Oznaka rešenja o izvršenju (broj, datum, sud)",
                "pitanje": "Da li je naveden broj i datum rešenja o izvršenju koje se pobija?",
                "kljucne_reci": ["rešenje o izvršenju", "broj", "i.", "od dana", "sud doneo"],
                "kriticnost": "visoka",
                "razlog": "Prigovor mora precizno identifikovati pobijano rešenje (čl. 74 ZIO).",
            },
            {
                "naziv": "Identitet izvršnog dužnika (prigovarača)",
                "pitanje": "Da li su navedeni podaci izvršnog dužnika koji podnosi prigovor?",
                "kljucne_reci": ["dužnik", "izvršni dužnik", "ime", "naziv", "jmbg", "pib"],
                "kriticnost": "visoka",
                "razlog": "Prigovor može podneti samo izvršni dužnik ili treće lice (čl. 74 ZIO).",
            },
            {
                "naziv": "Razlozi prigovora",
                "pitanje": "Da li su navedeni konkretni razlozi zašto je rešenje o izvršenju nezakonito?",
                "kljucne_reci": ["razlog", "potraživanje ne postoji", "zastarelo", "ispunjeno", "nedopušteno", "nezakonito", "pogrešno"],
                "kriticnost": "visoka",
                "razlog": "Prigovor bez razloga nema suspenzivno dejstvo — moraju biti navedeni konkretni osnovi.",
            },
            {
                "naziv": "Rok za prigovor (8 dana od dostave rešenja)",
                "pitanje": "Da li je navedeno kada je rešenje o izvršenju dostavljeno?",
                "kljucne_reci": ["dostavljeno", "dan dostave", "primio rešenje", "8 dana"],
                "kriticnost": "visoka",
                "razlog": "Rok za prigovor je 8 dana od dostave rešenja (čl. 74 ZIO) — kasni prigovor se odbacuje.",
            },
            {
                "naziv": "Predlog (ukidanje rešenja o izvršenju)",
                "pitanje": "Da li je naveden predlog šta sud treba da uradi sa rešenjem?",
                "kljucne_reci": ["predlažem", "ukine", "poništi", "odbaci", "ukinuti rešenje"],
                "kriticnost": "visoka",
                "razlog": "Sud odlučuje u granicama prigovornog predloga.",
            },
            {
                "naziv": "Dokazi uz prigovor",
                "pitanje": "Da li su navedeni dokazi koji potkrepljuju prigovor (priznanica, sporazum, zastarelost)?",
                "kljucne_reci": ["dokaz", "prilaže", "priznanica", "potvrda", "sporazum", "otpis"],
                "kriticnost": "srednja",
                "razlog": "Prigovor bez dokaza je slabiji procesno — dokazi se predaju uz prigovor.",
            },
        ],
    },
}

# Mapping: tipovi koji su prethodno bili u /api/podnesak → novi tipovi ovde
LEGACY_TIP_MAP: dict[str, str] = {
    "tuzba_naknada_stete": "tuzba_naknada_stete",
    "zalba_parnicna":      "zalba_parnicna",
    "zalba_na_presudu":    "zalba_na_presudu",
    "predlog_izvrsenje":   "predlog_izvrsenje",
}

SVI_TIPOVI: list[str] = list(CHECKLIST.keys())


def get_config(tip: str) -> TipConfig:
    """Vraća konfiguraciju za dati tip podneska. KeyError ako ne postoji."""
    if tip not in CHECKLIST:
        raise KeyError(f"Nepoznat tip podneska: {tip!r}. Dozvoljeni: {SVI_TIPOVI}")
    return CHECKLIST[tip]
