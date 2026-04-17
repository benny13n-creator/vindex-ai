# -*- coding: utf-8 -*-
"""
Vindex AI — Centralna logika agenta
Odgovara isključivo na osnovu Pinecone baze srpskih zakona.
"""

import os
import re
import logging
from dotenv import load_dotenv
from openai import OpenAI
from app.services.retrieve import retrieve_documents

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vindex.agent")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Sl. glasnik mapa — službeni izvori srpskih zakona ───────────────────────

SL_GLASNIK_MAP = {
    "zakon o radu":
        "Sl. glasnik RS, br. 24/2005, 61/2005, 54/2009, 32/2013, 75/2014, 13/2017, 113/2017, 95/2018",
    "zakon o obligacionim odnosima":
        "Sl. list SFRJ, br. 29/78, 39/85, 57/89; Sl. list SRJ, br. 31/93; Sl. list SCG, br. 1/2003",
    "zakon o parnicnom postupku":
        "Sl. glasnik RS, br. 72/2011, 49/2013, 74/2013, 55/2014, 87/2018",
    "krivicni zakonik":
        "Sl. glasnik RS, br. 85/2005, 88/2005, 107/2005, 72/2009, 111/2009, 121/2012, 104/2013, 108/2014, 94/2016, 35/2019",
    "zakonik o krivicnom postupku":
        "Sl. glasnik RS, br. 72/2011, 101/2011, 121/2012, 32/2013, 45/2013, 55/2014, 35/2019",
    "porodicni zakon":
        "Sl. glasnik RS, br. 18/2005, 72/2011, 6/2015",
    "zakon o privrednim drustvima":
        "Sl. glasnik RS, br. 36/2011, 99/2011, 83/2014, 5/2015, 44/2018, 95/2018, 91/2019",
    "zakon o izvrsenju i obezbedjenju":
        "Sl. glasnik RS, br. 106/2015, 106/2016, 113/2017, 54/2019",
    "zakon o zastiti potrosaca":
        "Sl. glasnik RS, br. 62/2014, 6/2016, 44/2018",
    "zakon o nasledjivanju":
        "Sl. glasnik SRS, br. 52/74, 1/80; Sl. glasnik RS, br. 46/95, 101/2003, 6/2015",
    "zakon o vanparnicnom postupku":
        "Sl. glasnik SRS, br. 25/82, 48/88; Sl. glasnik RS, br. 46/95, 18/2005, 85/2012, 45/2013, 55/2014, 6/2015, 106/2015",
    "zakon o opstem upravnom postupku":
        "Sl. glasnik RS, br. 18/2016, 95/2018",
    "zakon o upravnim sporovima":
        "Sl. glasnik RS, br. 111/2009",
    "ustav republike srbije":
        "Sl. glasnik RS, br. 98/2006",
}

DISCLAIMER_TEKST = (
    "Ovaj odgovor je generisan AI alatom isključivo u informativne svrhe "
    "i ne predstavlja pravni savet. Vindex AI nije zamena za konsultaciju "
    "sa ovlašćenim advokatom. Pre preduzimanja bilo kakvih pravnih koraka, "
    "konsultujte licenciranog pravnog zastupnika."
)

# ─── Odgovor kada nema relevantnog sadržaja u bazi ───────────────────────────

ODGOVOR_NIJE_PRONADJEN = (
    "PRAVNI OSNOV: Nije pronađen u bazi podataka\n\n"
    "ODGOVOR: U dostavljenoj bazi zakona nema direktno primenljive odredbe za ovo pitanje. "
    "Moguće je da se radi o oblasti koja nije obuhvaćena trenutnom bazom, "
    "ili da pitanje zahteva specifičniju formulaciju.\n\n"
    "CITAT IZ ZAKONA: \"Nije dostupno\"\n\n"
    "PRAVNA POSLEDICA: Nije moguće utvrditi bez odgovarajuće zakonske osnove u bazi.\n\n"
    "POUZDANOST: 0% — Odredba nije pronađena. Preporučujemo konsultaciju sa advokatom.\n\n"
    f"VAŽNA NAPOMENA: {DISCLAIMER_TEKST}"
)

OBAVEZNE_SEKCIJE_QA = [
    "PRAVNI OSNOV:",
    "ODGOVOR:",
    "CITAT IZ ZAKONA:",
    "PRAVNA POSLEDICA:",
    "POUZDANOST:",
]

# ─── System promptovi ────────────────────────────────────────────────────────

SYSTEM_PROMPT_QA = """Ti si stručni AI pravni asistent za advokate u Srbiji.
Odgovaraš ISKLJUČIVO na osnovu dostavljenog KONTEKSTA iz baze srpskih zakona.
Jezik: srpska ekavica, srpski pravni termini. NIKADA ne koristiš: izvanparnični, odvjetnik, tisuća, stoga, ukoliko, sukladno, glede — umesto toga: vanparnični, advokat, hiljada, dakle, ako, u skladu.

══════════════════════════════════════════
OBAVEZNI FORMAT ODGOVORA — UVEK, BEZ IZUZETKA:
══════════════════════════════════════════

PRAVNI OSNOV: [naziv zakona i broj člana iz konteksta, npr. "Zakon o obligacionim odnosima, član 200"]

ODGOVOR: [direktan odgovor — počni odmah sa suštinom, bez uvodnih fraza. Ako postoje dva ili više relevantna zakona ili tumačenja, navedi SVA i objasni koji ima prednost (lex specialis).]

CITAT IZ ZAKONA: "[doslovni citat relevantnog dela teksta člana iz konteksta — bez izmena]"

PRAVNA POSLEDICA: [konkretna pravna posledica ili primena odredbe na situaciju iz pitanja]

POUZDANOST: [X%] — [kratko obrazloženje: zašto je taj procenat, šta pokriva kontekst]

══════════════════════════════════════════
STROGA PRAVILA — NIKADA IH NE KRŠI:
══════════════════════════════════════════
1. NIKADA ne izmišljaj zakone, članove, citiranja ili sadržaj koji NIJE u KONTEKSTU.
2. Citat mora biti DOSLOVAN — preuzet direktno iz KONTEKSTA, bez ikakvih izmena.
3. Ako KONTEKST ne sadrži relevantan odgovor, u SVIM poljima napiši odgovarajuću napomenu.
4. POUZDANOST: 0% ako nema relevantnog konteksta; maksimum je 85%. Skala: 30–50% = delimično poklapanje, 51–70% = dobro poklapanje, 71–85% = visoko poklapanje sa bazom. Uvek dodaj kratko obrazloženje.
5. Uvek piši sa srpskim dijakritičkim znacima (č, ć, ž, š, đ) i srpskom ekavicom.
6. Ako je relevantno više zakona, navedi sve u PRAVNOM OSNOVU.
7. Ne davaj pravne savete van onoga što piše u zakonu — samo tumači tekst.
8. Ako pitanje ima VIŠE MOGUĆIH TUMAČENJA ili postoje suprotni stavovi, eksplicitno navedi: "Postoje različita tumačenja: (a)... (b)..." i smanji POUZDANOST.
9. NIKADA ne ekstrapoluj pravne posledice koje nisu eksplicitno navedene u KONTEKSTU.
10. LEX SPECIALIS PRAVILO: Ako postoji opšti zakon (npr. ZOO) i posebni zakon za isti slučaj (npr. Zakon o osiguranju, Zakon o radu, Zakon o zaštiti potrošača) — UVEK primeni posebni zakon i EKSPLICITNO navedi da on ima prednost nad opštim.
11. TEMPORALNA VALIDNOST: Ako kontekst sadrži više verzija iste odredbe (različite izmene), primeni NAJNOVIJU verziju i navedi kada je stupila na snagu. Ako postoje prelazne odredbe koje određuju koji zakon se primenjuje na stare činjenice — obavezno to naglasi u ODGOVORU.
12. NIKADA ne koristi reč "automatski" u kontekstu pravnih posledica, osim ako zakon eksplicitno propisuje da određena posledica nastupa "po sili zakona" ili "automatski". U svim ostalim slučajevima piši "potrebna je tužba/zahtev/odluka suda".
13. PROCESNI ROKOVI — PAZI NA RAZLIKE:
    - Žalba u parničnom postupku (ZPP): 15 dana
    - Revizija (ZPP): 30 dana, vrednosni cenzus 40.000 EUR
    - Žalba u upravnom postupku (ZUP): 15 dana
    - Tužba u upravnom sporu (ZUS): 30 dana od dostavljanja
    - Prigovor na optužnicu (ZKP): 8 dana — to je PRIGOVOR, ne žalba
    - Rok za pobijanje skupštinske odluke privrednog društva (ZPD): 30 dana od saznanja

══════════════════════════════════════════
KRITIČNE PRAVNE GREŠKE — NIKADA NE SMEŠ TVRDITI:
══════════════════════════════════════════

[ZASTARELOST — ZOO čl. 360–393]
❌ ZABRANJENA TVRDNJA: "Opomena/dopis/email/pismo/poziv prekida zastarelost"
✅ TAČNO: Zastarelost prekida JEDINO: (1) tužba ili pokretanje izvršenja, (2) pisano priznanje duga od strane DUŽNIKA.
✅ IZUZETAK — OVO PREKIDA: Vansudsko poravnanje potpisano od strane dužnika = pisano priznanje = prekida zastarelost.
❌ ZABRANJENA TVRDNJA: "Komunalne usluge zastarevaju za 3 godine"
✅ TAČNO: Periodična potraživanja (struja, voda, gas, telefon, kirija) zastarevaju za 1 GODINU (ZOO čl. 374).

[OTKAZ UGOVORA O RADU — Zakon o radu]
❌ ZABRANJENA TVRDNJA: Otkaz se može dati usmeno
✅ TAČNO: Rešenje o otkazu mora biti u pisanoj formi (čl. 185 ZOR) i uručeno zaposlenom.

[IZDRŽAVANJE — Porodični zakon]
❌ ZABRANJENA TVRDNJA: "Alimentacija/izdržavanje automatski prestaje" kada se promene okolnosti
✅ TAČNO: Izdržavanje ne prestaje automatski. Potrebna je tužba za izmenu ili prestanak (PZ čl. 162). Sud donosi novu odluku.

[NAKNADA ŠTETE — ZOO]
❌ ZABRANJENA TVRDNJA: Emotivna ili moralna podrška sama po sebi daje pravo na naknadu
✅ TAČNO: Nematerijalna šteta zahteva utvrđivanje konkretne povrede ličnog dobra (čl. 200 ZOO).

[HIPOTEKA]
❌ ZABRANJENA TVRDNJA: Hipotekarni poverilac mora podneti tužbu za naplatu
✅ TAČNO: Zakon o hipoteci dozvoljava vansudsku naplatu — hipoteka je izvršna isprava (čl. 26).

[POBIJANJE SKUPŠTINSKE ODLUKE]
❌ ZABRANJENA TVRDNJA: Rok za pobijanje je 6 meseci
✅ TAČNO: Rok je 30 dana od dana saznanja, a NAJKASNIJE 6 meseci od donošenja (ZPD čl. 376). Oba roka su prekluzivna.

[OPŠTE PRAVILO]
Ako kontekst ne sadrži eksplicitnu potvrdu za tvrdnju — ne tvrditi. Bolje "kontekst ne pokriva ovaj aspekt" nego netačna informacija.

══════════════════════════════════════════
KADA NEMA ODGOVORA — koristi TAČNO ovaj format:
══════════════════════════════════════════
PRAVNI OSNOV: Nije pronađen u bazi podataka
ODGOVOR: U dostavljenoj bazi zakona nema direktno primenljive odredbe za ovo pitanje.
CITAT IZ ZAKONA: "Nije dostupno"
PRAVNA POSLEDICA: Nije moguće utvrditi bez odgovarajuće zakonske osnove u bazi.
POUZDANOST: 0% — Odredba nije pronađena u dostupnoj bazi zakona."""

SYSTEM_PROMPT_NACRT = """Ti si stručni AI pravni asistent za advokate u Srbiji.
Generišeš nacrte pravnih dokumenata na osnovu dostavljenih činjenica.

OBAVEZNI FORMAT ODGOVORA:

PRAVNI OSNOV: [zakoni i članovi koji se primenjuju na ovu vrstu dokumenta]

NACRT:
[potpuni tekst nacrta dokumenta — formalni pravni stil, srpska pravna terminologija]
[nepoznate podatke označi sa [PODATAK_KOJI_TREBA_POPUNITI]]

NAPOMENA: Ovaj nacrt je generisan uz pomoć AI i mora biti pregledan i potvrđen od strane ovlašćenog advokata pre upotrebe.

PRAVILA:
1. Koristi formalni pravni stil i srpsku pravnu terminologiju.
2. Uvek piši sa srpskim dijakritičkim znacima (č, ć, ž, š, đ).
3. Nacrt mora biti u skladu sa važećim srpskim zakonodavstvom.
4. Ne izmišljaj činjenice koje nisu navedene u pitanju."""

SYSTEM_PROMPT_ANALIZA = """Ti si stručni AI pravni asistent za advokate u Srbiji.
Analiziraš sadržaj pravnih dokumenata.

OBAVEZNI FORMAT ODGOVORA:

PRAVNI OSNOV: [relevantni zakoni i članovi koji se primenjuju na analizirani dokument]

ANALIZA: [detaljna pravna analiza sadržaja dokumenta]

IDENTIFIKOVANI RIZICI: [pravni rizici, sporne klauzule, potencijalni problemi]

PREPORUKE: [konkretne preporuke za postupanje ili izmene]

POUZDANOST: [X%] — [obrazloženje]

PRAVILA:
1. Uvek piši sa srpskim dijakritičkim znacima (č, ć, ž, š, đ).
2. Ako dostavljeni tekst nije pravne prirode, jasno to naglasi.
3. Na kraju dodaj: "Analiza je generisana uz pomoć AI i mora biti proverena od strane ovlašćenog advokata." """

# ─── Interne pomoćne funkcije ────────────────────────────────────────────────

def _normalizuj(tekst: str) -> str:
    """Uklanja dijakritike i pretvara u mala slova — za interno poređenje."""
    tekst = (tekst or "").lower()
    for src, dst in {"š": "s", "đ": "dj", "č": "c", "ć": "c", "ž": "z"}.items():
        tekst = tekst.replace(src, dst)
    return tekst


def _filtriraj_kontekst(docs: list[str]) -> list[str]:
    """Odbacuje prazne i prekratke dokumente."""
    return [d for d in docs if len(d.strip()) > 50]


def _ima_obavezne_sekcije(odgovor: str) -> bool:
    """Proveri da li odgovor sadrži sve obavezne sekcije."""
    return all(sekcija in odgovor for sekcija in OBAVEZNE_SEKCIJE_QA)


def _proveri_halucinaciju(odgovor: str, docs: list[str]) -> tuple[bool, str]:
    """
    Stroga anti-halucinacijska provera.
    Vraća (validan, razlog).

    Logika:
    - Ako odgovor kaže 'nije pronađeno' → uvek validan
    - Svaki citirani član zakona mora biti pronađen u kontekstu
    - Ako je citat u navodnicima, prvih 40 znakova mora biti u kontekstu
    """
    # Odgovor "nije pronađeno" je uvek validan
    markeri_nije_pronadjeno = [
        "nije pronađen u bazi",
        "nema direktno primenljive",
        "nije dostupno",
        "0% —",
    ]
    odgovor_lower = odgovor.lower()
    if any(m in odgovor_lower for m in markeri_nije_pronadjeno):
        return True, "ok"

    kontekst = " ".join(docs)
    kontekst_norm = _normalizuj(kontekst)

    # 1) Proveri sve citirane članove
    citirani_clanovi = re.findall(r"[Čč]lan\s+(\d+[a-zA-Z]?)", odgovor)
    for clan in citirani_clanovi:
        clan_norm = _normalizuj(clan)
        # Word-boundary: "lan 5" ne sme da matchuje "lan 50"
        pattern = rf"lan\s+{re.escape(clan_norm)}(?!\d)"
        if not re.search(pattern, kontekst_norm):
            logger.warning("HALUCINACIJA: član %s nije u kontekstu", clan)
            return False, f"Član {clan} nije pronađen u dostavljenom kontekstu"

    # 2) Proveri citat (prvih 40 znakova normalizovanog citata mora biti u kontekstu)
    match_citat = re.search(r'CITAT IZ ZAKONA:\s*"([^"]{20,})"', odgovor)
    if match_citat:
        citat_raw = match_citat.group(1)
        citat_norm = _normalizuj(citat_raw)[:50].strip()
        if citat_norm and citat_norm not in kontekst_norm:
            logger.warning("HALUCINACIJA: citat nije pronađen u kontekstu: %s...", citat_norm[:30])
            return False, f"Citat nije pronađen u dostavljenom kontekstu"

    return True, "ok"


# ─── Poznate kritične pravne greške — pattern → ispravka ─────────────────────
#
# Svaki unos: (regex_pattern, korekcija)
# Pattern se primenjuje na normalizovani (bez dijakritika, lowercase) odgovor.
# Ako se pogodi → odgovor se odbacuje i vraća se siguran fallback.

ZABRANJENE_GRESKE: list[tuple[str, str]] = [
    # Zastarelost: opomena / dopis / email ne prekida zastarelost
    (
        r"opomen\w*\s+\w{0,15}\s*prekid",
        "Opomena ne prekida zastarelost (ZOO čl. 388–393). "
        "Zastarelost se prekida samo: tužbom/izvršenjem ili pisanim priznavanjem duga od strane dužnika.",
    ),
    (
        r"slanj\w+\s+opomen\w*\s+\w{0,15}\s*(zastarel|rok)",
        "Slanje opomene nema pravno dejstvo na tok roka zastarelosti prema ZOO.",
    ),
    (
        r"opomen\w*\s+\w{0,20}\s*(zaustav|suspenduj|sprecav|odlag)\w*\s+zastarel",
        "Opomena ne zadržava niti suspenduje zastarelost prema ZOO.",
    ),
    (
        r"(dopis|email|pismo|poziv|obavestenj)\w*\s+\w{0,20}\s*prekid\w*\s+zastarel",
        "Dopis/email/pismo/poziv ne prekida zastarelost (ZOO čl. 388–393).",
    ),
    # Otkaz: usmeni otkaz nije validan
    (
        r"usmen\w+\s+\w{0,10}\s*otka[zž]",
        "Otkaz ugovora o radu mora biti u pisanoj formi (čl. 185 ZOR). Usmeni otkaz nije pravno validan.",
    ),
    # Alimentacija ne prestaje automatski
    (
        r"aliment\w*\s+\w{0,15}\s*automatsk\w*\s*(prestaj|gasi|ukida)",
        "Izdržavanje ne prestaje automatski (PZ čl. 162). Potrebna je tužba za izmenu ili prestanak izdržavanja.",
    ),
    (
        r"izdrzavanj\w*\s+\w{0,15}\s*automatsk\w*\s*(prestaj|gasi|ukida)",
        "Izdržavanje ne prestaje automatski (PZ čl. 162). Potrebna je tužba za izmenu ili prestanak izdržavanja.",
    ),
    # Komunalne usluge — rok je 1 godina, ne 3
    (
        r"komunaln\w*\s+\w{0,20}\s*(tri|3)\s*(god|mesec|rok|godin)\w*\s*(zastarel|zastarev)",
        "Potraživanja za komunalne i slične periodične usluge zastarevaju za 1 godinu (ZOO čl. 374), ne za 3 godine.",
    ),
    # Pobijanje skupštinske odluke — 30 dana, ne 6 meseci
    (
        r"pobijanj\w*\s+\w{0,20}\s*skupstin\w*\s+\w{0,20}\s*(sest|6)\s*(mesec|god)\w*",
        "Rok za pobijanje odluke skupštine privrednog društva je 30 dana od saznanja, a najkasnije 6 meseci od donošenja (ZPD čl. 376) — prekluzivni rok od 30 dana se ne sme izostaviti.",
    ),
    # Žalba na optužnicu — to je PRIGOVOR, ne žalba
    (
        r"zalb\w*\s+\w{0,15}\s*na\s+optuznic",
        "Na optužnicu se ne podnosi žalba već PRIGOVOR u roku od 8 dana od dostavljanja (ZKP čl. 335).",
    ),
    # Hrvatska/ijekavica terminologija
    (
        r"\b(izvanparnicn|odvjetnik|tisuc|stoga|ukoliko|kako\s+bi|glede|radi\s+cega|sukladno)\b",
        "Odgovor sadrži hrvatsku pravnu terminologiju. Vindex AI koristi isključivo srpsku ekavicu i srpske pravne termine (vanparnični, advokat, hiljada, dakle, ako, da bi, u pogledu, zbog čega, u skladu).",
    ),
    # Hipoteka — ne ide tužbom nego direktno izvršenjem
    (
        r"hipoteka\w*\s+\w{0,20}\s*(mora|treba|potrebno)\s+\w{0,15}\s*tuzb",
        "Hipotekarni poverilac NE mora podneti tužbu — Zakon o hipoteci (čl. 26) dozvoljava vansudsku naplatu direktnim izvršenjem na osnovu hipoteke kao izvršne isprave.",
    ),
]


def _verifikuj_pravne_greske(odgovor: str) -> tuple[bool, str]:
    """
    Skenira odgovor za poznate pravne greške.
    Vraća (validan, opis_greske).
    Greška se detektuje na normalizovanom tekstu (bez dijakritika).
    """
    # "Nije pronađeno" odgovori su uvek bezbedni
    if "nije pronadjen u bazi" in _normalizuj(odgovor) or "0% —" in odgovor:
        return True, "ok"

    tekst_norm = _normalizuj(odgovor)
    for pattern, opis in ZABRANJENE_GRESKE:
        if re.search(pattern, tekst_norm):
            logger.error("PRAVNA GREŠKA DETEKTOVANA | pattern='%s' | %s", pattern, opis)
            return False, opis
    return True, "ok"


# ─── Fallback za detektovanu pravnu grešku ───────────────────────────────────

def _odgovor_pravna_greska(opis: str) -> str:
    return (
        f"PRAVNI OSNOV: Nije moguće dati siguran odgovor na osnovu dostupnog konteksta\n\n"
        f"ODGOVOR: Sistem je detektovao potencijalnu pravnu grešku u odgovoru i odbio ga iz predostrožnosti.\n\n"
        f"NAPOMENA SISTEMA: {opis}\n\n"
        f"CITAT IZ ZAKONA: \"Nije primenljivo\"\n\n"
        f"PRAVNA POSLEDICA: Nije moguće utvrditi bez verifikovanog zakonskog osnova.\n\n"
        f"POUZDANOST: 0% — Odgovor odbijen zbog detektovane pravne neispravnosti.\n\n"
        f"VAŽNA NAPOMENA: {DISCLAIMER_TEKST}"
    )


def _izvuci_zakone_iz_docs(docs: list[str]) -> list[str]:
    """Parsira nazive zakona iz formatiranih dokumenata (ZAKON: linija)."""
    zakoni = []
    vidjeni: set[str] = set()
    for doc in docs:
        m = re.search(r"ZAKON:\s*(.+)", doc)
        if m:
            zakon = m.group(1).strip()
            kljuc = zakon.lower()
            if kljuc not in vidjeni:
                vidjeni.add(kljuc)
                zakoni.append(zakon)
    return zakoni


def _dodaj_izvor(odgovor: str, docs: list[str]) -> str:
    """Pronalazi Sl. glasnik referencu iz konteksta i dodaje SLUŽBENI IZVOR: sekciju."""
    zakoni = _izvuci_zakone_iz_docs(docs)
    if not zakoni:
        return odgovor
    reference = []
    for zakon in zakoni:
        zakon_norm = _normalizuj(zakon)
        for kljuc, glasnik in SL_GLASNIK_MAP.items():
            if kljuc in zakon_norm:
                reference.append(f"{zakon} ({glasnik})")
                break
    if not reference:
        return odgovor
    return odgovor + "\n\nSLUŽBENI IZVOR: " + " | ".join(reference)


def _ogranici_pouzdanost(odgovor: str) -> str:
    """Osigurava da procenat u NAPOMENI O POUZDANOSTI nije viši od 85%."""
    idx = odgovor.find("POUZDANOST:")
    if idx == -1:
        return odgovor

    def _cap(m: re.Match) -> str:
        broj = int(m.group(1))
        return f"{min(broj, 85)}%"

    pre  = odgovor[:idx]
    deo  = odgovor[idx:]
    deo  = re.sub(r"\b(\d{1,3})%", _cap, deo)
    return pre + deo


def _dodaj_disclaimer(odgovor: str) -> str:
    """Dodaje pravni disclaimer na kraj odgovora."""
    return odgovor + f"\n\nVAŽNA NAPOMENA: {DISCLAIMER_TEKST}"


def _pozovi_openai(system_prompt: str, user_content: str, model: str = "gpt-4o") -> str:
    """OpenAI poziv sa timeoutom. Baca izuzetak pri grešci."""
    odgovor = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        timeout=60.0,
    )
    return (odgovor.choices[0].message.content or "").strip()


# ─── Javne funkcije agenta ───────────────────────────────────────────────────

def ask_agent(pitanje: str) -> dict:
    """
    Pravno istraživanje — pretražuje Pinecone bazu i vraća strukturiran odgovor.

    Vraća:
        {"status": "success", "data": "<strukturiran odgovor>"}
        {"status": "error", "message": "<poruka greške>"}
    """
    pitanje = (pitanje or "").strip()
    if not pitanje:
        return {"status": "error", "message": "Pitanje ne može biti prazno."}

    try:
        # Korak 1: Dohvati relevantne dokumente
        docs = retrieve_documents(pitanje, k=10)
        filtrirani = _filtriraj_kontekst(docs)

        if not filtrirani:
            logger.info("Nema relevantnih dokumenata za: %.80s", pitanje)
            return {"status": "success", "data": ODGOVOR_NIJE_PRONADJEN}

        # Korak 2: Pozovi model
        kontekst = "\n\n---\n\n".join(filtrirani)
        user_content = (
            f"PITANJE: {pitanje}\n\n"
            f"KONTEKST IZ BAZE ZAKONA:\n{kontekst}"
        )
        odgovor = _pozovi_openai(SYSTEM_PROMPT_QA, user_content)

        # Korak 3: Proveri format
        if not _ima_obavezne_sekcije(odgovor):
            logger.warning("Odgovor nema propisanu strukturu — zamenjujem sa 'nije pronađeno'")
            return {"status": "success", "data": ODGOVOR_NIJE_PRONADJEN}

        # Korak 4: Anti-halucinacijska provera
        validan, razlog = _proveri_halucinaciju(odgovor, filtrirani)
        if not validan:
            logger.warning("Anti-halucinacija blokirala odgovor: %s", razlog)
            return {"status": "success", "data": ODGOVOR_NIJE_PRONADJEN}

        # Korak 5: Provera poznatih pravnih grešaka
        pravno_validan, pravna_greska = _verifikuj_pravne_greske(odgovor)
        if not pravno_validan:
            logger.error("Pravna greška blokirala odgovor: %s", pravna_greska)
            return {"status": "success", "data": _odgovor_pravna_greska(pravna_greska)}

        # Korak 6: Post-processing — cap pouzdanosti, dodaj izvor i disclaimer
        odgovor = _ogranici_pouzdanost(odgovor)
        odgovor = _dodaj_izvor(odgovor, filtrirani)
        odgovor = _dodaj_disclaimer(odgovor)

        logger.info("Uspešan odgovor za: %.80s", pitanje)
        return {"status": "success", "data": odgovor}

    except Exception:
        logger.exception("Greška u ask_agent")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}


def ask_nacrt(vrsta: str, opis: str) -> dict:
    """Generisanje nacrta pravnog dokumenta."""
    try:
        user_content = (
            f"Vrsta dokumenta: {vrsta}\n\n"
            f"Činjenice i okolnosti: {opis}"
        )
        odgovor = _pozovi_openai(SYSTEM_PROMPT_NACRT, user_content)
        odgovor = _dodaj_disclaimer(odgovor)
        return {"status": "success", "data": odgovor}
    except Exception:
        logger.exception("Greška u ask_nacrt")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}


def ask_analiza(tekst: str, pitanje: str = "") -> dict:
    """Analiza pravnog dokumenta."""
    try:
        user_content = ""
        if pitanje.strip():
            user_content += f"SPECIFIČNO PITANJE: {pitanje.strip()}\n\n"
        user_content += f"DOKUMENT ZA ANALIZU:\n{tekst}"
        odgovor = _pozovi_openai(SYSTEM_PROMPT_ANALIZA, user_content)
        odgovor = _ogranici_pouzdanost(odgovor)
        odgovor = _dodaj_disclaimer(odgovor)
        return {"status": "success", "data": odgovor}
    except Exception:
        logger.exception("Greška u ask_analiza")
        return {"status": "error", "message": "Sistem je trenutno zauzet. Pokušajte ponovo."}


# ─── CLI za testiranje ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Vindex AI — Pravni asistent (CLI mod)")
    print("Unesite 'exit' za izlaz.\n")
    while True:
        q = input("Pitanje: ").strip()
        if q.lower() == "exit":
            break
        if not q:
            continue
        rezultat = ask_agent(q)
        print("\n" + ("=" * 60))
        print(rezultat.get("data", rezultat.get("message", "Greška")))
        print("=" * 60 + "\n")
