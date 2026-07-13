# -*- coding: utf-8 -*-
"""
Ingest CARF (OECD) + DAC8 (EU Council Directive 2023/2226) u novi Pinecone
namespace "carf_dac8" — odvojen od "web3_zdi_mca" (ZDI/MiCA) jer je u pitanju
drugi pravni sistem (medjunarodno poresko izvestavanje, ne ZDI/MiCA compliance).

Izvori (preuzeti i verifikovani direktno, ne parafrazirani iz secanja):
  - CARF: OECD (2023), "International Standards for Automatic Exchange of
    Information in Tax Matters: Crypto-Asset Reporting Framework and 2023
    update to the Common Reporting Standard" — Part I, Section 2 "Rules"
    (str. 17-28), preuzeto sa oecd.org, PDF 2.1MB, tekst izvucen pdftotext-om.
  - DAC8: Council Directive (EU) 2023/2226 of 17 October 2023 — Article 8ad,
    Article 25a, Article 2, recital 44, i novi Annex VI (Section I-V) —
    dostavljen direktno od strane korisnika (EUR-Lex blokira automatsko
    preuzimanje AWS WAF captchom, pa je korisnik uradio copy-paste iz
    pregledaca).

Chunking granularnost: po Section/subparagraph granicama, isti pristup kao
postojeci ZDI ingest (vidi scripts/ingest_web3_addendum.py) — dovoljno malo
za precizan retrieval, dovoljno veliko da svaki chunk nosi kompletnu pravnu
misao.

Run: python scripts/ingest_carf_dac8.py --dry-run   (proveri bez upisa)
     python scripts/ingest_carf_dac8.py              (stvaran upsert)
"""

import os
import sys
import time
import argparse
import logging
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_carf_dac8")

NAMESPACE   = "carf_dac8"
EMBED_MODEL = "text-embedding-3-large"

# ── CARF chunkovi (OECD, Part I, Section 2 "Rules") ────────────────────────────

CARF_CHUNKOVI = [
    {
        "id": "carf_section1_obligations",
        "naslov": "CARF Section I — Obligations of Reporting Crypto-Asset Service Providers",
        "izvor": "OECD (2023) CARF, Part I, Section 2 Rules, Section I",
        "propis": "CARF",
        "tip": "carf_section",
        "tekst": (
            "CARF SECTION I: OBLIGATIONS OF REPORTING CRYPTO-ASSET SERVICE PROVIDERS\n\n"
            "A. A Reporting Crypto-Asset Service Provider is subject to the reporting and due "
            "diligence requirements in Sections II and III in a jurisdiction, if it is: "
            "1. an Entity or individual resident for tax purposes in that jurisdiction; "
            "2. an Entity that (a) is incorporated or organised under the laws of that jurisdiction "
            "and (b) either has legal personality there or has an obligation to file tax returns or "
            "tax information returns to the tax authorities there with respect to the income of the "
            "Entity; 3. an Entity managed from that jurisdiction; or 4. an Entity or individual that "
            "has a regular place of business in that jurisdiction.\n"
            "B. A Reporting Crypto-Asset Service Provider is subject to the requirements with "
            "respect to Relevant Transactions effectuated through a Branch based in that jurisdiction.\n"
            "C-G. A Reporting Crypto-Asset Service Provider is NOT required to duplicate the "
            "reporting and due diligence requirements in a jurisdiction if the equivalent "
            "requirements are already completed in a Partner Jurisdiction — a hierarchy exists "
            "among the four nexus criteria in paragraph A (tax residency > incorporation > "
            "management > regular place of business) specifically to prevent double reporting of "
            "the same user in multiple jurisdictions.\n"
            "H. Notification mechanism: a Reporting Crypto-Asset Service Provider may lodge a "
            "notification confirming that its requirements are completed under a Partner "
            "Jurisdiction's substantially similar nexus rules, to avoid duplicate reporting."
        ),
    },
    {
        "id": "carf_section2_reporting",
        "naslov": "CARF Section II — Reporting Requirements",
        "izvor": "OECD (2023) CARF, Part I, Section 2 Rules, Section II",
        "propis": "CARF",
        "tip": "carf_section",
        "tekst": (
            "CARF SECTION II: REPORTING REQUIREMENTS\n\n"
            "Za svaku kalendarsku godinu, Reporting Crypto-Asset Service Provider mora prijaviti "
            "sledece o Reportable Users (korisnicima koji su Reportable Person) i njihovim "
            "Controlling Persons ako su i oni Reportable Person:\n"
            "1. Ime, adresa, jurisdikcija(e) rezidentnosti, TIN, i (za fizicko lice) datum i mesto "
            "rodjenja svakog Reportable User; za Entity sa Controlling Persons koji su Reportable "
            "Person: isti podaci za Entity i za svaku takvu kontrolnu osobu, plus uloga po kojoj je "
            "kontrolna osoba.\n"
            "2. Ime, adresa i identifikacioni broj samog Reporting Crypto-Asset Service Providera.\n"
            "3. Za svaki tip Relevant Crypto-Asset sa Reportable Transactions u periodu:\n"
            "   a) puno ime tipa kripto-imovine;\n"
            "   b) agregatni bruto iznos placen, broj jedinica i broj transakcija za KUPOVINU za fiat;\n"
            "   c) agregatni bruto iznos primljen, broj jedinica i broj transakcija za PRODAJU za fiat;\n"
            "   d) fer trzisna vrednost i broj transakcija za KUPOVINU za drugu kripto-imovinu "
            "(crypto-to-crypto);\n"
            "   e) fer trzisna vrednost i broj transakcija za PRODAJU za drugu kripto-imovinu;\n"
            "   f) fer trzisna vrednost za Reportable Retail Payment Transactions (placanje robe/"
            "usluga kripto-imovinom preko USD 50.000);\n"
            "   g)-h) transferi KA i OD korisnika koji nisu obuhvaceni gornjim (npr. airdrop, "
            "staking prihod, zajam — kategorisano po tipu transfera ako je poznat);\n"
            "   i) agregatna vrednost transfera KA wallet adresama za koje se ne zna da su povezane "
            "sa VASP-om ili finansijskom institucijom — ovo je kljucna stavka za self-custody "
            "wallet transfere.\n"
            "Rok prijave: godisnje, sledece kalendarske godine posle perioda na koji se odnosi."
        ),
    },
    {
        "id": "carf_section3_duediligence",
        "naslov": "CARF Section III — Due Diligence Procedures",
        "izvor": "OECD (2023) CARF, Part I, Section 2 Rules, Section III",
        "propis": "CARF",
        "tip": "carf_section",
        "tekst": (
            "CARF SECTION III: DUE DILIGENCE PROCEDURES\n\n"
            "A. Za fizicka lica (Individual Crypto-Asset User): pri uspostavljanju odnosa, "
            "Reporting Crypto-Asset Service Provider mora pribaviti self-certification kojom "
            "korisnik potvrdjuje svoju poresku rezidentnost, i potvrditi razumnost te izjave na "
            "osnovu raspolozivih podataka (ukljucujuci AML/KYC dokumentaciju). Ako se okolnosti "
            "promene i izjava postane nepouzdana, mora se pribaviti nova.\n"
            "B. Za pravna lica (Entity Crypto-Asset User): isti princip — self-certification o "
            "rezidentnosti, PLUS utvrdjivanje da li Entity ima Controlling Persons koji su "
            "Reportable Person (osim ako je Entity 'Active Entity' — vidi Section IV.D.11 za "
            "kriterijume).\n"
            "C. Validnost self-certification: mora biti potpisana/pozitivno potvrdjena, datirana, "
            "i sadrzati (za fizicko lice) ime, adresu, jurisdikciju poreske rezidentnosti, TIN, "
            "datum rodjenja; (za pravno lice) pravni naziv, adresu, jurisdikciju rezidentnosti, "
            "TIN, i podatke o Controlling Persons ako je primenjivo.\n"
            "D. Opsta pravila: provajder koji je i Financial Institution za CRS svrhe moze "
            "koristiti vec sprovedenu CRS due diligence proceduru; provajder moze angazovati trecu "
            "stranu za due diligence ali odgovornost ostaje na njemu; evidencija se mora cuvati "
            "najmanje 5 godina."
        ),
    },
    {
        "id": "carf_section4_definicije_imovina",
        "naslov": "CARF Section IV.A-C — Definicije: kripto-imovina, provajder, transakcije",
        "izvor": "OECD (2023) CARF, Part I, Section 2 Rules, Section IV A-C",
        "propis": "CARF",
        "tip": "carf_definicije",
        "tekst": (
            "CARF SECTION IV — DEFINISANI POJMOVI (deo 1/2)\n\n"
            "'Crypto-Asset' — digitalna reprezentacija vrednosti koja se oslanja na kriptografski "
            "obezbedjen distribuirani registar (distributed ledger) ili slicnu tehnologiju da "
            "validira i obezbedi transakcije.\n\n"
            "'Relevant Crypto-Asset' — bilo koja Crypto-Asset koja NIJE Central Bank Digital "
            "Currency, Specified Electronic Money Product, ili kripto-imovina za koju je provajder "
            "adekvatno utvrdio da se ne moze koristiti za placanje ili investicione svrhe.\n\n"
            "'Reporting Crypto-Asset Service Provider' — bilo koje fizicko ili pravno lice koje "
            "kao delatnost pruza uslugu izvrsavanja Exchange Transactions za ili u ime korisnika "
            "(ukljucujuci kao suprotnu stranu, posrednika, ili operatera trgovacke platforme).\n\n"
            "'Relevant Transaction' = (a) Exchange Transaction ILI (b) Transfer relevantne "
            "kripto-imovine.\n"
            "'Exchange Transaction' = (a) razmena izmedju kripto-imovine i fiat valute, ILI "
            "(b) razmena izmedju razlicitih formi kripto-imovine (crypto-to-crypto).\n"
            "'Reportable Retail Payment Transaction' = Transfer kripto-imovine kao naknada za robu "
            "ili usluge cija vrednost prelazi USD 50.000.\n"
            "'Transfer' = transakcija koja pomera kripto-imovinu sa/na adresu drugog korisnika "
            "(ne istog), gde provajder na osnovu raspolozivog znanja NE MOZE utvrditi da je u "
            "pitanju Exchange Transaction — ovo je kategorija koja pokriva self-custody wallet "
            "transfere."
        ),
    },
    {
        "id": "carf_section4_definicije_korisnik",
        "naslov": "CARF Section IV.D-E — Definicije: Reportable User, Controlling Persons, izuzeci",
        "izvor": "OECD (2023) CARF, Part I, Section 2 Rules, Section IV D-E",
        "propis": "CARF",
        "tip": "carf_definicije",
        "tekst": (
            "CARF SECTION IV — DEFINISANI POJMOVI (deo 2/2)\n\n"
            "'Reportable User' — Crypto-Asset User koji je Reportable Person (tj. rezident "
            "Reportable Jurisdiction i NIJE Excluded Person).\n"
            "'Reportable Jurisdiction' — jurisdikcija sa kojom postoji aktivan sporazum o razmeni "
            "podataka po CARF-u.\n"
            "'Controlling Persons' — fizicka lica koja vrse kontrolu nad pravnim licem; kod trusta: "
            "osnivac, poverenik, zastitnik, korisnici; interpretira se u skladu sa FATF "
            "preporukama iz 2019. o VASP provajderima.\n"
            "'Active Entity' — pravno lice koje ispunjava jedan od nekoliko kriterijuma "
            "(pretezno aktivan prihod, holding kompanija operativnih subsidijara, startup u prve "
            "24 meseca, likvidacija/reorganizacija, interno finansiranje grupe, ili neprofitna "
            "organizacija) — ovakvi entiteti NE moraju prijaviti Controlling Persons.\n\n"
            "'Excluded Person' (izuzeti od izvestavanja kao korisnici) — javno trgovano pravno "
            "lice, njegov povezani entitet, Governmental Entity, International Organisation, "
            "Central Bank, ili Financial Institution (osim odredjenih Investment Entity).\n"
            "'Financial Institution' = Custodial Institution, Depository Institution, Investment "
            "Entity, ili Specified Insurance Company — svaka sa preciznim testovima udela prihoda "
            "(20% za Custodial, 50% za Investment Entity)."
        ),
    },
    {
        "id": "carf_section5_implementacija",
        "naslov": "CARF Section V — Effective Implementation",
        "izvor": "OECD (2023) CARF, Part I, Section 2 Rules, Section V",
        "propis": "CARF",
        "tip": "carf_section",
        "tekst": (
            "CARF SECTION V: EFFECTIVE IMPLEMENTATION\n\n"
            "Jurisdikcija mora imati pravila i administrativne procedure koje obezbedjuju "
            "efektivnu implementaciju izvestajnih i due diligence obaveza iz Section II i III — "
            "ovo je opsta obaveza jurisdikcije (drzave), za razliku od DAC8 Annex VI Section V koja "
            "sadrzi mnogo konkretnije EU-specificne mehanizme (npr. 60-dnevno zamrzavanje naloga, "
            "2 opomene pre brisanja registracije)."
        ),
    },
]

# ── DAC8 chunkovi (EU Council Directive 2023/2226) ─────────────────────────────

DAC8_CHUNKOVI = [
    {
        "id": "dac8_article8ad_scope",
        "naslov": "DAC8 Article 8ad — Scope and conditions of automatic exchange",
        "izvor": "Council Directive (EU) 2023/2226, Article 8ad",
        "propis": "DAC8",
        "tip": "dac8_clan",
        "tekst": (
            "DAC8 ČLAN 8ad — Obim i uslovi obavezne automatske razmene informacija koje "
            "prijavljuju Reporting Crypto-Asset Service Providers\n\n"
            "1. Svaka drzava clanica mora zahtevati od Reporting Crypto-Asset Service Providers da "
            "ispune izvestajne zahteve i sprovedu due diligence procedure iz Section II i III "
            "Annex VI.\n"
            "2-3. Nadlezni organ drzave clanice automatski razmenjuje podatke o svakom Reportable "
            "Person: ime, adresa, drzava(e) clanica(e) rezidentnosti, TIN, datum/mesto rodjenja; "
            "podaci o provajderu; i za svaki tip Reportable Crypto-Asset — agregatne iznose "
            "kupovine/prodaje za fiat, crypto-to-crypto razmene, retail payment transakcije, i "
            "transfere na nepoznate distributed ledger adrese (Regulation (EU) 2023/1114 — MiCA).\n"
            "6. Prva razmena podataka: za kalendarsku 2026. godinu, u roku od 9 meseci nakon kraja "
            "godine (do 30. septembra 2027).\n"
            "7. Crypto-Asset Operator (provajder koji NIJE vec autorizovan po MiCA Regulation "
            "2023/1114) mora se registrovati u JEDNOJ drzavi clanici radi ispunjenja izvestajnih "
            "obaveza."
        ),
    },
    {
        "id": "dac8_article2_rokovi",
        "naslov": "DAC8 Article 2 — Transpozicija i primena (rokovi)",
        "izvor": "Council Directive (EU) 2023/2226, Article 2",
        "propis": "DAC8",
        "tip": "dac8_clan",
        "tekst": (
            "DAC8 ČLAN 2 — Rokovi transpozicije\n\n"
            "1. Drzave clanice moraju usvojiti i objaviti zakone/propise potrebne za usaglasavanje "
            "sa ovom direktivom do 31. decembra 2025, i primenjivati ih od 1. januara 2026.\n"
            "2. Izuzetak — TIN izvestavanje (Article 27c(3) i (4)): rok transpozicije 31. decembar "
            "2027, primena od 1. januara 2028.\n"
            "3. Izuzetak — TIN izvestavanje (Article 27c(2)): rok transpozicije 31. decembar 2029, "
            "primena od 1. januara 2030.\n\n"
            "PRAKTICNA POSLEDICA: glavna obaveza prikupljanja podataka o kripto transakcijama "
            "vazi vec od 1. januara 2026, dok se odredjeni administrativni detalji oko TIN "
            "(poreski identifikacioni broj) uvode postepeno do 2030."
        ),
    },
    {
        "id": "dac8_advokat_privilegija",
        "naslov": "DAC8 — izuzetak za advokate (recital 44 + Article 25a)",
        "izvor": "Council Directive (EU) 2023/2226, recital 44 i Article 25a",
        "propis": "DAC8",
        "tip": "dac8_vodic",
        "tekst": (
            "DAC8 I ADVOKATSKA PRIVILEGIJA (Legal Professional Privilege)\n\n"
            "Recital 44 direktive izricito uzima u obzir presudu Suda pravde EU od 8. decembra "
            "2022. (predmet C-694/20, Orde van Vlaamse Balies and Others) i propisuje: odredbe "
            "DAC8 NE SMEJU imati efekat da zahtevaju od advokata koji deluju kao posrednici — kada "
            "su oslobodjeni obaveze izvestavanja zbog advokatske privilegije kojom su vezani — da "
            "obaveste BILO KOG DRUGOG posrednika (koji nije njihov klijent) o OBAVEZI IZVESTAVANJA "
            "TOG DRUGOG posrednika.\n\n"
            "MEDJUTIM: advokat koji je oslobodjen obaveze izvestavanja zbog privilegije I DALJE "
            "MORA bez odlaganja obavestiti SVOG KLIJENTA o klijentovoj sopstvenoj obavezi "
            "izvestavanja (Article 25a referencira ovu obavezu obavestavanja).\n\n"
            "ZNACAJ ZA ADVOKATE: ako advokat u Srbiji ili regionu savetuje EU klijenta o kripto "
            "transakcijama koje potpadaju pod DAC8 (npr. klijent koristi EU-autorizovanog CASP "
            "provajdera), advokat sam nije duzan da izvestava niti da upozorava treca lica — ali "
            "je duzan da obavesti svog klijenta o klijentovoj obavezi."
        ),
    },
    {
        "id": "dac8_annexvi_section1",
        "naslov": "DAC8 Annex VI Section I — Obaveze provajdera (EU verzija)",
        "izvor": "Council Directive (EU) 2023/2226, Annex III (novi Annex VI), Section I",
        "propis": "DAC8",
        "tip": "dac8_section",
        "tekst": (
            "DAC8 ANNEX VI, SECTION I — OBLIGATIONS OF REPORTING CRYPTO-ASSET SERVICE PROVIDERS\n\n"
            "A. Reporting Crypto-Asset Service Provider ima obaveze u drzavi clanici ako je:\n"
            "1. Entitet AUTORIZOVAN po clanu 63 MiCA Regulation (EU) 2023/1114, ili dozvoljen da "
            "pruza usluge po notifikaciji iz clana 60 MiCA; ILI\n"
            "2. Entitet koji NIJE MiCA-autorizovan ali je: (a) rezident za poreske svrhe u drzavi "
            "clanici; (b) inkorporiran po zakonima drzave clanice i ima pravni subjektivitet ili "
            "obavezu podnosenja poreskih prijava tamo; (c) upravljan iz drzave clanice; ili (d) ima "
            "redovno mesto poslovanja u drzavi clanici.\n"
            "B-H. Isti hijerarhijski mehanizam sprecavanja duplog izvestavanja kao CARF Section I, "
            "ali sa EU-specificnim pojmom 'Qualified Non-Union Jurisdiction' — jurisdikcija van EU "
            "koja ima efektivan sporazum o razmeni sa SVIM drzavama clanicama.\n\n"
            "KLJUCNA RAZLIKA OD CARF-a: DAC8 uvodi PRIMARNI kriterijum MiCA autorizacije (stavka "
            "A.1) koji CARF nema — jer EU vec ima jedinstven regulatorni sistem (MiCA) za CASP "
            "provajdere, pa se DAC8 nadovezuje na to umesto da gradi paralelan sistem."
        ),
    },
    {
        "id": "dac8_annexvi_section2",
        "naslov": "DAC8 Annex VI Section II — Izvestajni zahtevi (EU verzija)",
        "izvor": "Council Directive (EU) 2023/2226, Annex III (novi Annex VI), Section II",
        "propis": "DAC8",
        "tip": "dac8_section",
        "tekst": (
            "DAC8 ANNEX VI, SECTION II — REPORTING REQUIREMENTS\n\n"
            "Sadrzajno identicno CARF Section II (isti spisak podataka: identitet Reportable "
            "User-a i Controlling Persons, podaci o provajderu, agregatni iznosi po tipu "
            "transakcije — kupovina/prodaja za fiat, crypto-to-crypto, retail payment, transferi "
            "ka/od korisnika, transferi na nepoznate adrese).\n\n"
            "EU-SPECIFICNE RAZLIKE:\n"
            "- Threshold za Reportable Retail Payment Transaction: USD 50.000 (identicno CARF-u).\n"
            "- Transferi na nepoznate adrese referenciraju 'distributed ledger addresses' u smislu "
            "MiCA Regulation (EU) 2023/1114 — precizna EU pravna definicija, ne generican pojam.\n"
            "- Prvo izvestavanje: kalendarska 2026. godina, rok do 30. septembra 2027 (Section II, "
            "paragraf D + Article 8ad(6)).\n"
            "- Izuzetak od dupliranja: provajder ne mora prijaviti korisnika ako vec izvestava o "
            "njemu u jurisdikciji van EU koja ima Effective Qualifying Competent Authority "
            "Agreement sa drzavom clanicom rezidentnosti tog korisnika (Section II, paragraf E)."
        ),
    },
    {
        "id": "dac8_annexvi_section3",
        "naslov": "DAC8 Annex VI Section III — Due diligence procedure (EU verzija)",
        "izvor": "Council Directive (EU) 2023/2226, Annex III (novi Annex VI), Section III",
        "propis": "DAC8",
        "tip": "dac8_section",
        "tekst": (
            "DAC8 ANNEX VI, SECTION III — DUE DILIGENCE PROCEDURES\n\n"
            "Sadrzajno gotovo identicno CARF Section III — self-certification za fizicka i pravna "
            "lica, potvrda poreske rezidentnosti, identifikacija Controlling Persons.\n\n"
            "EU-SPECIFICNA RAZLIKA — rok za Pre-existing korisnike: Reporting Crypto-Asset Service "
            "Provider mora pribaviti self-certification za POSTOJECE korisnike (koji su uspostavili "
            "odnos pre 31. decembra 2025) NAJKASNIJE do 1. januara 2027 — CARF ostavlja taj datum "
            "otvorenim ([xx/xx/xxxx]) jer je to okvirni standard koji svaka jurisdikcija sama "
            "popunjava, dok DAC8 (kao pravno obavezujuca EU direktiva) daje TACAN datum.\n\n"
            "Reference na Customer Due Diligence Procedures upucuju na EU AML direktivu "
            "(Directive (EU) 2015/849), ne na opsti FATF standard kao CARF."
        ),
    },
    {
        "id": "dac8_annexvi_section4",
        "naslov": "DAC8 Annex VI Section IV — Definisani pojmovi (EU verzija)",
        "izvor": "Council Directive (EU) 2023/2226, Annex III (novi Annex VI), Section IV",
        "propis": "DAC8",
        "tip": "dac8_definicije",
        "tekst": (
            "DAC8 ANNEX VI, SECTION IV — DEFINED TERMS\n\n"
            "Kljucne definicije referenciraju direktno MiCA Regulation (EU) 2023/1114:\n"
            "- 'Crypto-Asset' = crypto-asset kako je definisan u clanu 3(1), tacka (5) MiCA.\n"
            "- 'Crypto-Asset Service Provider' = kako je definisan u clanu 3(1), tacka (15) MiCA.\n"
            "- 'Crypto-Asset Service' = kako je definisano u clanu 3(1), tacka (16) MiCA, "
            "ukljucujuci STAKING i LENDING (eksplicitno navedeno — CARF ovo ne pominje "
            "eksplicitno u definiciji usluge).\n"
            "- 'Reportable Retail Payment Transaction' = transfer kripto-imovine za robu/usluge "
            "preko USD 50.000 (identicno CARF-u).\n"
            "- 'Controlling Persons' interpretira se u skladu sa pojmom 'beneficial owner' iz "
            "clana 3, tacka (6) EU AML direktive (Directive (EU) 2015/849) — DAC8 koristi EU "
            "pravni okvir, ne FATF preporuke direktno kao CARF.\n"
            "- 'Qualified Non-Union Jurisdiction' — nov pojam koji CARF nema: jurisdikcija van EU "
            "koja ima Effective Qualifying Competent Authority Agreement sa SVIM drzavama "
            "clanicama istovremeno (ne pojedinacno)."
        ),
    },
    {
        "id": "dac8_annexvi_section5",
        "naslov": "DAC8 Annex VI Section V — Efektivna implementacija (EU verzija)",
        "izvor": "Council Directive (EU) 2023/2226, Annex III (novi Annex VI), Section V",
        "propis": "DAC8",
        "tip": "dac8_section",
        "tekst": (
            "DAC8 ANNEX VI, SECTION V — EFFECTIVE IMPLEMENTATION\n\n"
            "Za razliku od CARF Section V (opsta, jednorecenicna obaveza jurisdikcije), DAC8 "
            "Annex VI Section V je mnogo konkretniji i sadrzi stvarne mehanizme prinude:\n\n"
            "A. Ako Crypto-Asset User ne dostavi trazene podatke NAKON DVE OPOMENE, i ne pre isteka "
            "60 DANA od prve opomene, provajder MORA sprečiti tog korisnika da izvrsava Reportable "
            "Transactions (efektivno zamrzavanje naloga).\n"
            "B. Evidencija se mora cuvati najmanje 5 a najvise 10 godina.\n"
            "F. Registracija Crypto-Asset Operatora: registruje se u JEDNOJ drzavi clanici; ako ne "
            "ispuni izvestajnu obavezu nakon DVE OPOMENE, drzava clanica MORA opozvati registraciju "
            "— rok opoziva: ne pre 30 dana, ne posle 90 dana od druge opomene.\n\n"
            "PRAKTICNI ZNACAJ: ovo znaci da EU CASP provajder koji ignorise zahteve za "
            "self-certification moze doslovno blokirati nalog korisnika, a operator koji ignorise "
            "izvestajnu obavezu moze izgubiti pravo da posluje u EU u roku od najvise 90 dana."
        ),
    },
]

# ── Sinteza vodici (isti obrazac kao ZDI addendum "vodic" chunkovi) ────────────

SINTEZA_CHUNKOVI = [
    {
        "id": "carf_dac8_odnos_vodic",
        "naslov": "CARF vs DAC8 — koji se primenjuje i kada",
        "izvor": "Sinteza na osnovu OECD CARF (2023) i Council Directive (EU) 2023/2226",
        "propis": "CARF/DAC8",
        "tip": "vodic",
        "tekst": (
            "CARF vs DAC8 — PRAKTICNA RAZLIKA\n\n"
            "CARF (OECD Crypto-Asset Reporting Framework) je MEDJUNARODNI STANDARD — model pravila "
            "koji svaka drzava (uz izuzetak EU) transponuje pojedinacno u svoje domace pravo, uz "
            "bilateralne/multilateralne sporazume o razmeni (CARF MCAA).\n\n"
            "DAC8 je KONKRETNA EU DIREKTIVA koja implementira CARF standard za svih 27 drzava "
            "clanica ODJEDNOM, kroz jedinstven pravni instrument — DAC8 Annex VI je gotovo "
            "doslovna transpozicija CARF Section I-V, sa dodatkom EU-specificnih mehanizama "
            "(MiCA autorizacija kao primaran kriterijum, TIN rokovi do 2030, konkretni "
            "60-dnevni/90-dnevni rokovi prinude, izuzetak za advokatsku privilegiju).\n\n"
            "ZA SRPSKOG ADVOKATA/KLIJENTA: ako klijent koristi CASP provajdera registrovanog u EU "
            "(npr. nemacku ili irsku kripto-berzu), primenjuje se DAC8 (kroz tu berzu kao "
            "Reporting Crypto-Asset Service Provider). Ako klijent koristi provajdera u jurisdikciji "
            "koja je preuzela CARF ali NIJE EU clanica (npr. UK, Japan, Kanada), primenjuje se "
            "CARF kroz domace pravo te jurisdikcije. Srbija SAMA trenutno NIJE preuzela CARF "
            "obavezu (vidi poseban vodic o statusu Srbije), pa domaci srpski CASP provajderi "
            "(ako postoje) trenutno nemaju CARF/DAC8 izvestajnu obavezu prema OECD/EU mehanizmu — "
            "ali ZDI i domaci AML propisi i dalje vaze nezavisno od toga."
        ),
    },
    {
        "id": "carf_srbija_status_vodic",
        "naslov": "Srbija i CARF — trenutni status (zvanicna OECD lista)",
        "izvor": "OECD Global Forum, 'Jurisdictions committed to implement CARF', ažurirano 23.6.2026",
        "propis": "CARF",
        "tip": "vodic",
        "tekst": (
            "SRBIJA I CARF — TRENUTNI STATUS (proveren direktno u zvanicnom OECD dokumentu)\n\n"
            "Prema zvanicnoj OECD listi jurisdikcija koje su se obavezale da implementiraju CARF "
            "(azurirano 23. juna 2026, ukupno 76 jurisdikcija), SRBIJA SE NE POJAVLJUJE:\n"
            "- NE nalazi se medju 46 jurisdikcija sa prvom razmenom podataka do 2027 (cela EU, UK, "
            "Japan, Juzna Koreja, Brazil, Juzna Afrika i dr.);\n"
            "- NE nalazi se medju 29 jurisdikcija sa prvom razmenom do 2028 (Svajcarska, Singapur, "
            "UAE, Kanada, Hong Kong, Australija i dr.);\n"
            "- NE nalazi se medju jurisdikcijama do 2029 (samo SAD);\n"
            "- NE nalazi se ni medju 5 jurisdikcija 'identifikovanih kao relevantne, jos nisu "
            "preuzele obavezu' (Argentina, El Salvador, Gruzija, Indija, Vijetnam).\n\n"
            "ZAKLJUCAK: Srbija trenutno FORMALNO NEMA CARF obavezu izvestavanja prema OECD "
            "Global Forum mehanizmu. Ovo NE znaci da su transakcije srpskih rezidenata van domasaja "
            "medjunarodne poreske transparentnosti — ako srpski rezident koristi CASP provajdera "
            "registrovanog u jurisdikciji koja JESTE preuzela CARF/DAC8 (npr. EU berza), ta berza "
            "ce izvestavati o njemu prema svojoj domacoj CARF/DAC8 obavezi, bez obzira na status "
            "Srbije. Status Srbije je relevantan samo za DOMACE srpske CASP provajdere."
        ),
    },
    {
        "id": "carf_transakcije_kategorije_vodic",
        "naslov": "Koje transakcije su predmet CARF/DAC8 izvestavanja — pregled kategorija",
        "izvor": "Sinteza na osnovu CARF Section II i DAC8 Annex VI Section II",
        "propis": "CARF/DAC8",
        "tip": "vodic",
        "tekst": (
            "KOJE TRANSAKCIJE SU PREDMET CARF/DAC8 IZVESTAVANJA\n\n"
            "1. KUPOVINA kripto-imovine za fiat valutu — izvestava se agregatno (iznos, broj "
            "jedinica, broj transakcija).\n"
            "2. PRODAJA kripto-imovine za fiat valutu — isto agregatno.\n"
            "3. CRYPTO-TO-CRYPTO razmena (npr. Bitcoin za Ethereum) — izvestava se PO FER TRZISNOJ "
            "VREDNOSTI u trenutku transakcije, ne po nominalnoj kolicini.\n"
            "4. RETAIL PAYMENT — placanje robe/usluga kripto-imovinom preko USD 50.000 — "
            "provajder tretira KUPCA kao Crypto-Asset User ako je po AML pravilima duzan da "
            "verifikuje njegov identitet.\n"
            "5. TRANSFERI KA korisniku koji nisu kupovina/prodaja (npr. primljen airdrop, staking "
            "prihod, otplata zajma) — kategorisu se po tipu transfera AKO je provajder svestan "
            "tipa.\n"
            "6. TRANSFERI OD korisnika ka NEPOZNATIM adresama — ovo je kljucna kategorija za "
            "self-custody: kada korisnik povuce kripto-imovinu na sopstveni hardverski/software "
            "wallet koji NIJE povezan sa poznatim VASP-om ili finansijskom institucijom, provajder "
            "izvestava AGREGATNU vrednost i broj jedinica tih transfera — bez detalja o samoj "
            "adresi (adresa se ne prijavljuje, samo agregatna vrednost odliva).\n\n"
            "STA NIJE PREDMET IZVESTAVANJA: cista self-custody drzava kripto-imovine gde NIKAD nije "
            "ukljucen nijedan Reporting Crypto-Asset Service Provider (npr. mining nagrada koja "
            "nikad nije prosla kroz berzu) — CARF/DAC8 izvestavaju SAMO transakcije koje prolaze "
            "kroz reportable provajdera, ne cistu peer-to-peer aktivnost bez posrednika."
        ),
    },
]

ALL_CHUNKOVI = CARF_CHUNKOVI + DAC8_CHUNKOVI + SINTEZA_CHUNKOVI


def _embed(client, text: str) -> list:
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from pinecone import Pinecone
    import openai

    api_key_pc = os.environ.get("PINECONE_API_KEY", "")
    api_key_oa = os.environ.get("OPENAI_API_KEY", "")
    index_name = os.environ.get("PINECONE_INDEX_NAME", "vindex")

    if not api_key_pc or not api_key_oa:
        log.error("PINECONE_API_KEY ili OPENAI_API_KEY nedostaje.")
        sys.exit(1)

    pc    = Pinecone(api_key=api_key_pc)
    index = pc.Index(index_name)
    oa    = openai.OpenAI(api_key=api_key_oa)

    log.info(
        "Pocetak ingesta %d chunkova (%d CARF + %d DAC8 + %d sinteza) → namespace=%s",
        len(ALL_CHUNKOVI), len(CARF_CHUNKOVI), len(DAC8_CHUNKOVI), len(SINTEZA_CHUNKOVI), NAMESPACE,
    )

    vektori = []
    for chunk in ALL_CHUNKOVI:
        log.info("Embedding: %s", chunk["naslov"])
        vec = _embed(oa, chunk["tekst"])
        vektori.append({
            "id": chunk["id"],
            "values": vec,
            "metadata": {
                "naslov": chunk["naslov"],
                "izvor":  chunk["izvor"],
                "propis": chunk["propis"],
                "tip":    chunk["tip"],
                "tekst":  chunk["tekst"],
            },
        })
        time.sleep(0.3)

    if args.dry_run:
        log.info("[DRY-RUN] Preskacemo upsert. Vektori koji bi bili upisani:")
        for v in vektori:
            log.info("  ID=%s | tekst=%d znakova | propis=%s", v["id"], len(v["metadata"]["tekst"]), v["metadata"]["propis"])
        return

    index.upsert(vectors=vektori, namespace=NAMESPACE)
    log.info("Upsert zavrsen: %d vektora u %s", len(vektori), NAMESPACE)

    time.sleep(2)
    stats = index.describe_index_stats()
    ns_count = stats.namespaces.get(NAMESPACE, {})
    count = getattr(ns_count, "vector_count", "?")
    log.info("Namespace %s sada ima %s vektora.", NAMESPACE, count)


if __name__ == "__main__":
    main()
